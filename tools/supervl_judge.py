#!/usr/bin/env python3
"""Run Showhand's fixed visual question through Nemotron 3.5 Super VL."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.cosmos_job.visual_judge import FIXED_QUESTION, validate_verdict

MODEL_ID = "nvidia/Nemotron-3.5-Super-VL"
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
INPUT_USD_PER_MILLION = Decimal("0.30")
OUTPUT_USD_PER_MILLION = Decimal("0.90")
MAX_TOTAL_SPEND_USD = Decimal("0.10")
DEFAULT_MAX_TOKENS = 1200
MIN_MAX_TOKENS = 1000
RESERVED_PROMPT_TOKENS_PER_WINDOW = 10_000


class RequestFailure(RuntimeError):
    """A privacy-safe Token Factory request failure."""

    def __init__(self, code: str, request_id: str | None = None, http_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.request_id = request_id
        self.http_status = http_status


def parse_last_json_object(raw: str) -> dict:
    """Parse and validate the final complete JSON object in a model response."""

    decoder = json.JSONDecoder()
    objects: list[tuple[int, object]] = []
    for start, character in enumerate(raw):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        objects.append((start, value))
    if not objects:
        raise ValueError("Super VL output contains no complete JSON object")
    return validate_verdict(objects[-1][1], source="Super VL")


def _api_key() -> str:
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key and os.name == "nt":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment:
            value, _ = winreg.QueryValueEx(environment, "NEBIUS_API_KEY")
        key = str(value).strip()
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is missing")
    return key


def _data_url(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _body(image_path: Path, max_tokens: int) -> dict[str, Any]:
    return {
        "model": MODEL_ID,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_url(image_path)}},
                    {"type": "text", "text": FIXED_QUESTION},
                ],
            }
        ],
        "chat_template_kwargs": {"enable_thinking": False},
    }


def _post(body: dict[str, Any], key: str, timeout_s: float) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            request_id = response.headers.get("x-request-id", "")
            try:
                payload = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise RequestFailure(
                    "invalid_response_json", request_id, response.status
                ) from error
    except urllib.error.HTTPError as error:
        request_id = error.headers.get("x-request-id", "") if error.headers else ""
        raise RequestFailure("http_error", request_id or None, error.code) from error
    except (TimeoutError, urllib.error.URLError) as error:
        raise RequestFailure("transport_error") from error
    if not isinstance(payload, dict):
        raise RequestFailure("response_is_not_an_object", request_id or None, response.status)
    return payload, request_id or str(payload.get("id") or "")


def _usage_and_cost(payload: dict[str, Any]) -> tuple[dict[str, int], Decimal]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("missing_usage")
    try:
        prompt_tokens = int(usage["prompt_tokens"])
        completion_tokens = int(usage["completion_tokens"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid_usage") from error
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
    if min(prompt_tokens, completion_tokens, total_tokens) < 0:
        raise ValueError("invalid_usage")
    cost = (
        Decimal(prompt_tokens) * INPUT_USD_PER_MILLION
        + Decimal(completion_tokens) * OUTPUT_USD_PER_MILLION
    ) / Decimal(1_000_000)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }, cost


def judge_window(
    image_path: Path,
    *,
    key: str,
    max_tokens: int,
    timeout_s: float,
) -> tuple[dict[str, Any], Decimal]:
    """Issue one request and return a privacy-safe valid or invalid window record."""

    started = time.perf_counter()
    try:
        payload, request_id = _post(_body(image_path, max_tokens), key, timeout_s)
    except RequestFailure as error:
        latency_s = round(time.perf_counter() - started, 6)
        return (
            {
                "status": "invalid",
                "request_id": error.request_id,
                "http_status": error.http_status,
                "latency_s": latency_s,
                "tokens": None,
                "cost_usd": None,
                "error": error.code,
            },
            _reserved_call_cost(max_tokens),
        )

    latency_s = round(time.perf_counter() - started, 6)
    try:
        tokens, cost = _usage_and_cost(payload)
    except ValueError as error:
        return (
            {
                "status": "invalid",
                "request_id": request_id or None,
                "http_status": 200,
                "latency_s": latency_s,
                "tokens": None,
                "cost_usd": None,
                "error": str(error),
            },
            _reserved_call_cost(max_tokens),
        )

    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("content_is_not_text")
        verdict = parse_last_json_object(content)
        if choice.get("finish_reason") == "length":
            raise ValueError("truncated_output")
    except (KeyError, IndexError, TypeError, ValueError):
        return (
            {
                "status": "invalid",
                "request_id": request_id or None,
                "http_status": 200,
                "latency_s": latency_s,
                "tokens": tokens,
                "cost_usd": _decimal_number(cost),
                "error": "invalid_model_output",
            },
            cost,
        )

    return (
        {
            "status": "valid",
            **verdict,
            "request_id": request_id or None,
            "http_status": 200,
            "latency_s": latency_s,
            "tokens": tokens,
            "cost_usd": _decimal_number(cost),
        },
        cost,
    )


def _reserved_call_cost(max_tokens: int) -> Decimal:
    return (
        Decimal(RESERVED_PROMPT_TOKENS_PER_WINDOW) * INPUT_USD_PER_MILLION
        + Decimal(max_tokens) * OUTPUT_USD_PER_MILLION
    ) / Decimal(1_000_000)


def _decimal_number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000000000001")))


def _load_take(take_id: str, manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    windows = manifest.get("windows") if isinstance(manifest, dict) else None
    if not isinstance(windows, list) or not windows:
        raise ValueError(f"{take_id} visual manifest contains no windows")
    loaded_windows = []
    for expected_index, window in enumerate(windows):
        if not isinstance(window, dict) or int(window.get("window_index", -1)) != expected_index:
            raise ValueError(f"{take_id} visual manifest window indexes are not contiguous")
        image_path = Path(str(window.get("pair_path", "")))
        if not image_path.is_absolute():
            image_path = manifest_path.parent / image_path
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        start_s = float(window["start_s"])
        end_s = float(window["end_s"])
        if start_s < 0 or end_s <= start_s:
            raise ValueError(f"{take_id} window {expected_index} has an invalid interval")
        loaded_windows.append(
            {
                "window_index": expected_index,
                "start_s": start_s,
                "end_s": end_s,
                "image_path": image_path,
            }
        )
    if output_path.exists():
        raise FileExistsError(output_path)
    return {
        "take_id": take_id,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "output_path": output_path,
        "windows": loaded_windows,
    }


def _summary(
    spec: dict[str, Any], records: list[dict[str, Any]], wall_s: float, max_tokens: int
) -> dict:
    valid = [record for record in records if record["status"] == "valid"]
    token_records = [record["tokens"] for record in records if record["tokens"] is not None]
    costs = [
        Decimal(str(record["cost_usd"])) for record in records if record["cost_usd"] is not None
    ]
    return {
        "schema_version": 1,
        "take_id": spec["take_id"],
        "manifest_sha256": spec["manifest_sha256"],
        "model_id": MODEL_ID,
        "request": {
            "endpoint": ENDPOINT,
            "temperature": 0,
            "max_tokens": max_tokens,
            "enable_thinking": False,
            "fixed_question_sha256": hashlib.sha256(FIXED_QUESTION.encode("utf-8")).hexdigest(),
        },
        "pricing_usd_per_million_tokens": {
            "input": float(INPUT_USD_PER_MILLION),
            "output": float(OUTPUT_USD_PER_MILLION),
        },
        "verdict_counts": {
            "match": sum(record["match"] for record in valid),
            "mismatch": sum(not record["match"] for record in valid),
            "invalid": len(records) - len(valid),
            "total": len(records),
        },
        "timing": {
            "wall_s": round(wall_s, 6),
            "request_latency_s": round(sum(record["latency_s"] for record in records), 6),
        },
        "tokens": {
            "prompt_tokens": sum(item["prompt_tokens"] for item in token_records),
            "completion_tokens": sum(item["completion_tokens"] for item in token_records),
            "total_tokens": sum(item["total_tokens"] for item in token_records),
        },
        "cost_usd": _decimal_number(sum(costs, Decimal(0))),
        "cost_complete": len(costs) == len(records),
        "windows": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--take",
        action="append",
        nargs=3,
        metavar=("TAKE_ID", "MANIFEST", "OUTPUT"),
        required=True,
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--spend-cap-usd", type=Decimal, default=MAX_TOTAL_SPEND_USD)
    args = parser.parse_args()
    if args.max_tokens < MIN_MAX_TOKENS:
        raise ValueError(f"max_tokens must be at least {MIN_MAX_TOKENS}")
    if args.spend_cap_usd <= 0 or args.spend_cap_usd > MAX_TOTAL_SPEND_USD:
        raise ValueError(f"spend cap must be above 0 and at most {MAX_TOTAL_SPEND_USD}")

    specs = [
        _load_take(take_id, Path(manifest), Path(output)) for take_id, manifest, output in args.take
    ]
    total_windows = sum(len(spec["windows"]) for spec in specs)
    reserved_total = Decimal(total_windows) * _reserved_call_cost(args.max_tokens)
    if reserved_total > args.spend_cap_usd:
        raise RuntimeError(
            f"worst-case reservation {reserved_total} exceeds spend cap {args.spend_cap_usd}"
        )

    key = _api_key()
    budget_accounted = Decimal(0)
    for spec in specs:
        take_started = time.perf_counter()
        records = []
        for window in spec["windows"]:
            if budget_accounted + _reserved_call_cost(args.max_tokens) > args.spend_cap_usd:
                raise RuntimeError("spend cap leaves no room for the next window")
            result, budget_charge = judge_window(
                window["image_path"],
                key=key,
                max_tokens=args.max_tokens,
                timeout_s=args.timeout_s,
            )
            budget_accounted += budget_charge
            record = {
                "window_index": window["window_index"],
                "start_s": window["start_s"],
                "end_s": window["end_s"],
                "model_id": MODEL_ID,
                **result,
            }
            records.append(record)
            print(
                f"SUPER_VL_TAKE={spec['take_id']} WINDOW={window['window_index']} "
                f"STATUS={record['status']} LATENCY_S={record['latency_s']:.6f} "
                f"COST_USD={record['cost_usd']}",
                flush=True,
            )
        output = _summary(spec, records, time.perf_counter() - take_started, args.max_tokens)
        destination = spec["output_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )


if __name__ == "__main__":
    main()
