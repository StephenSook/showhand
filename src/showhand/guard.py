"""Fail-closed grounding guard for Nemotron fusion output."""

from __future__ import annotations

from typing import Any


class GroundingError(ValueError):
    """Raised when a fusion claim is not supported by cited evidence."""


FUSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "reshow"]},
        "reshow_windows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number", "minimum": 0},
                    "end_s": {"type": "number", "exclusiveMinimum": 0},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 300},
                },
                "required": ["start_s", "end_s", "reason"],
                "additionalProperties": False,
            },
        },
        "evidence_refs": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
    },
    "required": ["decision", "reshow_windows", "evidence_refs"],
    "additionalProperties": False,
}


def guard_fusion(
    output: dict[str, Any],
    metrics_by_ref: dict[str, dict[str, Any]],
    visual_by_ref: dict[str, dict[str, Any]],
    duration_s: float,
) -> dict[str, Any]:
    if set(output) != {"decision", "reshow_windows", "evidence_refs"}:
        raise GroundingError("fusion output keys do not match the strict schema")
    if output["decision"] not in {"accept", "reshow"}:
        raise GroundingError("fusion decision must be accept or reshow")
    windows = output["reshow_windows"]
    refs = output["evidence_refs"]
    if not isinstance(windows, list) or not isinstance(refs, list):
        raise GroundingError("reshow_windows and evidence_refs must be lists")
    if output["decision"] == "accept" and windows:
        raise GroundingError("accept decision cannot include re-show windows")
    if output["decision"] == "reshow" and not windows:
        raise GroundingError("reshow decision requires at least one window")
    if not refs:
        raise GroundingError("fusion decision must cite at least one evidence ref")
    if len(refs) != len(set(refs)):
        raise GroundingError("fusion evidence refs must be unique")

    evidence = {**metrics_by_ref, **visual_by_ref}
    unknown_refs = set(refs).difference(evidence)
    if unknown_refs:
        raise GroundingError(f"unknown evidence refs: {sorted(unknown_refs)}")

    for window in windows:
        if set(window) != {"start_s", "end_s", "reason"}:
            raise GroundingError("re-show window keys do not match the strict schema")
        start_s = float(window["start_s"])
        end_s = float(window["end_s"])
        if start_s < 0 or end_s <= start_s or end_s > duration_s + 1e-6:
            raise GroundingError(f"re-show window [{start_s}, {end_s}] is outside the take")
        supporting = [
            evidence[ref]
            for ref in refs
            if _overlaps(start_s, end_s, evidence[ref]["start_s"], evidence[ref]["end_s"])
            and _is_negative(evidence[ref])
        ]
        if not supporting:
            raise GroundingError(
                f"re-show window [{start_s}, {end_s}] has no cited negative evidence"
            )
        allowed_codes = {code for item in supporting for code in item.get("reason_codes", [])}
        reason_text = str(window["reason"])
        if not reason_text.strip():
            raise GroundingError("re-show reason cannot be empty")
        allowed_reasons = {f"{code} in cited evidence" for code in allowed_codes}
        if reason_text not in allowed_reasons:
            raise GroundingError(
                f"reason for [{start_s}, {end_s}] must equal one of {sorted(allowed_reasons)}"
            )
    return output


def _is_negative(evidence: dict[str, Any]) -> bool:
    if "pass" in evidence:
        return evidence["pass"] is False
    if "match" in evidence:
        return evidence["match"] is False
    return False


def _overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return max(a_start, float(b_start)) < min(a_end, float(b_end))
