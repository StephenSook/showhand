"""Schema and deterministic helpers for the Cosmos visual judge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VISUAL_REASON_CODES = {
    "upper_body_pose",
    "lower_body_pose",
    "timing",
    "orientation",
    "occlusion",
    "insufficient_view",
}

FIXED_QUESTION = (
    "The left image is the human demonstration and the right image is the simulated Unitree G1. "
    "For this one-second window, does the robot pose match the human pose? Judge pose and timing, "
    "not appearance. Return only the requested JSON object."
)

VISUAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "window_index": {"type": "integer", "minimum": 0},
        "start_s": {"type": "number", "minimum": 0},
        "end_s": {"type": "number", "exclusiveMinimum": 0},
        "match": {"type": "boolean"},
        "reason_codes": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(VISUAL_REASON_CODES)},
            "uniqueItems": True,
        },
        "summary": {"type": "string", "minLength": 1, "maxLength": 300},
    },
    "required": ["window_index", "start_s", "end_s", "match", "reason_codes", "summary"],
    "additionalProperties": False,
}


def validate_visual_verdict(value: dict[str, Any], expected_index: int) -> None:
    required = {"window_index", "start_s", "end_s", "match", "reason_codes", "summary"}
    allowed_metadata = {"raw_output", "latency_s", "pair_path"}
    if not required.issubset(value) or set(value).difference(required | allowed_metadata):
        raise ValueError(f"visual verdict keys differ from schema: {sorted(value)}")
    if value["window_index"] != expected_index:
        raise ValueError(
            f"visual window_index {value['window_index']} does not match {expected_index}"
        )
    if not isinstance(value["match"], bool):
        raise ValueError("visual match must be a boolean")
    if float(value["start_s"]) < 0:
        raise ValueError("visual start_s cannot be negative")
    if value["end_s"] <= value["start_s"]:
        raise ValueError("visual end_s must be after start_s")
    unknown = set(value["reason_codes"]).difference(VISUAL_REASON_CODES)
    if unknown:
        raise ValueError(f"unknown visual reason codes: {sorted(unknown)}")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("visual summary must be a non-empty string")
    if value["match"] and value["reason_codes"]:
        raise ValueError("matching visual verdict cannot carry mismatch reason codes")
    if not value["match"] and not value["reason_codes"]:
        raise ValueError("mismatch visual verdict must carry at least one reason code")


def load_visual_results(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    verdicts = payload.get("verdicts") if isinstance(payload, dict) else None
    if not isinstance(verdicts, list):
        raise ValueError("visual results must contain a verdicts list")
    normalized = []
    fields = ("window_index", "start_s", "end_s", "match", "reason_codes", "summary")
    for index, verdict in enumerate(verdicts):
        validate_visual_verdict(verdict, index)
        normalized.append(
            {
                **{field: verdict[field] for field in fields},
                "evidence_ref": f"visual:second:{index}",
            }
        )
    return normalized
