"""Nemotron 3.5 Lightning fusion call and raw-response accounting."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from showhand.guard import FUSION_SCHEMA, GroundingError, guard_fusion

MODEL = "nvidia/Nemotron-3_5-Lightning"
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
INPUT_USD_PER_M = 0.06
OUTPUT_USD_PER_M = 0.24
# One answer, then one retry that is told why the guard refused. Fixed on 2026-10-06, before
# any outside human grade existed, after the guard refused 2 of the first 3 real answers.
MAX_ATTEMPTS = 2
Poster = Callable[[dict[str, Any], str, float], tuple[dict[str, Any], str]]
SYSTEM = (
    "You grade one offline demonstration take. Use only the supplied evidence. "
    "Return accept or reshow. Every re-show reason must exactly equal '<reason_code> in cited "
    "evidence', using a reason code from cited negative evidence, such as "
    "tracking_mean_abs_error_rad, root_tilt_deg, foot_slip, fall, "
    "out_of_balance, upper_body_pose, lower_body_pose, orientation, occlusion, or "
    "insufficient_view. Each re-show window must exactly match a cited negative one-second "
    "evidence interval. Do not invent measurements or uncited seconds."
)


def request_fusion(
    metrics: dict[str, Any],
    visual_verdicts: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    timeout_s: float = 180.0,
    post: Poster | None = None,
) -> dict[str, Any]:
    """Ask Nemotron, guard the answer, retry once with the refusal, then fall back.

    Every attempt is kept with its request id, cost, raw response and guard result.
    """

    key = (api_key or os.environ.get("NEBIUS_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is missing")
    send = post or _post
    evidence_metrics, evidence_visual = _evidence(metrics, visual_verdicts)
    duration_s = float(metrics["duration_s"])
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "duration_s": metrics["duration_s"],
                    "overall_metrics": evidence_metrics["metrics:overall"],
                    "metric_windows": metrics["per_second"],
                    "visual_windows": visual_verdicts,
                },
                separators=(",", ":"),
            ),
        },
    ]
    attempts: list[dict[str, Any]] = []
    for attempt in range(MAX_ATTEMPTS):
        body = {
            "model": MODEL,
            "temperature": 0,
            "max_tokens": 1200,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "showhand_fusion",
                    "schema": FUSION_SCHEMA,
                    "strict": True,
                },
            },
            "chat_template_kwargs": {"enable_thinking": False},
        }
        started = time.perf_counter()
        raw, request_id = send(body, key, timeout_s)
        elapsed_s = time.perf_counter() - started
        choice = raw["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("Token Factory fusion output was truncated")
        content = choice["message"]["content"]
        record: dict[str, Any] = {
            "attempt": attempt + 1,
            "request_id": request_id,
            "latency_s": round(elapsed_s, 6),
            "usage": raw.get("usage"),
            "cost_usd": _cost(raw),
            "raw_response": raw,
        }
        try:
            guarded = guard_fusion(
                json.loads(content), evidence_metrics, evidence_visual, duration_s
            )
        except GroundingError as error:
            record["guard"] = "refused"
            record["guard_error"] = str(error)
            attempts.append(record)
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"The grounding guard refused that answer: {error}. "
                        "Answer again from the same evidence."
                    ),
                },
            ]
            continue
        record["guard"] = "passed"
        attempts.append(record)
        status = "passed_first" if attempt == 0 else "passed_after_retry"
        return _result(attempts, guarded, status, "nemotron", "passed")
    fallback = deterministic_fallback(metrics, visual_verdicts)
    try:
        guard_fusion(fallback, evidence_metrics, evidence_visual, duration_s)
        guard = "passed"
    except GroundingError as error:
        # A failing take with no failing second has no window to cite; it is still a re-show.
        guard = f"refused: {error}"
    return _result(
        attempts, fallback, "fallback_after_guard_refusals", "deterministic_fallback", guard
    )


def deterministic_fallback(
    metrics: dict[str, Any], visual_verdicts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Re-show every negative one-second window, citing it. Used only after two refusals."""

    windows: list[dict[str, Any]] = []
    refs: list[str] = []
    seen: set[tuple[float, float]] = set()
    for item in [*metrics["per_second"], *visual_verdicts]:
        negative = item.get("pass") is False or item.get("match") is False
        codes = item.get("reason_codes") or []
        if not negative or not codes:
            continue
        refs.append(item["evidence_ref"])
        interval = (float(item["start_s"]), float(item["end_s"]))
        if interval not in seen:
            seen.add(interval)
            windows.append(
                {
                    "start_s": interval[0],
                    "end_s": interval[1],
                    "reason": f"{codes[0]} in cited evidence",
                }
            )
    if not windows:
        overall_fails = metrics["overall"].get("pass") is False
        return {
            "decision": "reshow" if overall_fails else "accept",
            "reshow_windows": [],
            "evidence_refs": ["metrics:overall"],
        }
    return {"decision": "reshow", "reshow_windows": windows, "evidence_refs": refs}


def _evidence(
    metrics: dict[str, Any], visual_verdicts: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    evidence_metrics = {item["evidence_ref"]: item for item in metrics["per_second"]}
    evidence_metrics["metrics:overall"] = {**metrics["overall"], "evidence_ref": "metrics:overall"}
    return evidence_metrics, {item["evidence_ref"]: item for item in visual_verdicts}


def _cost(raw: dict[str, Any]) -> float:
    usage = raw.get("usage")
    if not isinstance(usage, dict) or not {"prompt_tokens", "completion_tokens"}.issubset(usage):
        raise RuntimeError("Token Factory response is missing token usage; cost is unknown")
    cost = (
        int(usage["prompt_tokens"]) / 1_000_000 * INPUT_USD_PER_M
        + int(usage["completion_tokens"]) / 1_000_000 * OUTPUT_USD_PER_M
    )
    return round(cost, 8)


def _result(
    attempts: list[dict[str, Any]],
    output: dict[str, Any],
    status: str,
    decided_by: str,
    guard: str,
) -> dict[str, Any]:
    last = attempts[-1]
    return {
        "model": MODEL,
        "status": status,
        "decided_by": decided_by,
        "attempts": attempts,
        "request_id": last["request_id"],
        "latency_s": round(sum(item["latency_s"] for item in attempts), 6),
        "cost_usd": round(sum(item["cost_usd"] for item in attempts), 8),
        "raw_response": last["raw_response"],
        "output": output,
        "guard": guard,
    }


def _post(body: dict[str, Any], key: str, timeout_s: float) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = json.load(response)
            request_id = response.headers.get("x-request-id", "")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"Token Factory HTTP {error.code}: {detail}") from error
    return raw, request_id
