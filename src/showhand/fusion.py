"""Nemotron 3.5 Lightning fusion call and raw-response accounting."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from showhand.guard import FUSION_SCHEMA, guard_fusion

MODEL = "nvidia/Nemotron-3_5-Lightning"
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
INPUT_USD_PER_M = 0.06
OUTPUT_USD_PER_M = 0.24
SYSTEM = (
    "You grade one offline demonstration take. Use only the supplied evidence. "
    "Return accept or reshow. Every re-show reason must exactly equal '<reason_code> in cited "
    "evidence', using a reason code from cited negative evidence, such as "
    "tracking_mean_abs_error_rad, root_tilt_deg, foot_slip, fall, "
    "out_of_balance, upper_body_pose, lower_body_pose, timing, orientation, occlusion, or "
    "insufficient_view. Do not invent measurements or uncited seconds."
)


def request_fusion(
    metrics: dict[str, Any],
    visual_verdicts: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    key = (api_key or os.environ.get("NEBIUS_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is missing")
    evidence_metrics = {item["evidence_ref"]: item for item in metrics["per_second"]}
    evidence_visual = {item["evidence_ref"]: item for item in visual_verdicts}
    body = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "duration_s": metrics["duration_s"],
                        "metric_windows": metrics["per_second"],
                        "visual_windows": visual_verdicts,
                    },
                    separators=(",", ":"),
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "showhand_fusion", "schema": FUSION_SCHEMA, "strict": True},
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = json.load(response)
            request_id = response.headers.get("x-request-id", "")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"Token Factory HTTP {error.code}: {detail}") from error
    elapsed_s = time.perf_counter() - started
    choice = raw["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("Token Factory fusion output was truncated")
    parsed = json.loads(choice["message"]["content"])
    guarded = guard_fusion(
        parsed,
        evidence_metrics,
        evidence_visual,
        float(metrics["duration_s"]),
    )
    usage = raw.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    cost_usd = (
        prompt_tokens / 1_000_000 * INPUT_USD_PER_M
        + completion_tokens / 1_000_000 * OUTPUT_USD_PER_M
    )
    return {
        "model": MODEL,
        "request_id": request_id,
        "latency_s": round(elapsed_s, 6),
        "usage": usage,
        "cost_usd": round(cost_usd, 8),
        "raw_response": raw,
        "output": guarded,
        "guard": "passed",
    }
