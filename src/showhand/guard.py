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
    overall = metrics_by_ref.get("metrics:overall")
    if not overall:
        raise GroundingError("metrics:overall evidence is required")
    mandatory_negative = overall.get("pass") is False or any(
        verdict.get("match") is False for verdict in visual_by_ref.values()
    )
    if output["decision"] == "accept" and mandatory_negative:
        raise GroundingError("accept contradicts mandatory negative evidence")
    if output["decision"] == "accept" and any(_is_negative(evidence[ref]) for ref in refs):
        raise GroundingError("accept cannot cite negative evidence")

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
            if ref != "metrics:overall"
            and _same_interval(start_s, end_s, evidence[ref]["start_s"], evidence[ref]["end_s"])
            and _is_negative(evidence[ref])
        ]
        if not supporting:
            raise GroundingError(
                f"re-show window [{start_s}, {end_s}] must exactly match cited negative evidence"
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


def _same_interval(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return abs(a_start - float(b_start)) <= 1e-6 and abs(a_end - float(b_end)) <= 1e-6
