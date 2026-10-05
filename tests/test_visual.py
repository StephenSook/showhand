import pytest

from showhand.visual import validate_visual_verdict


def test_visual_verdict_validates() -> None:
    validate_visual_verdict(
        {
            "window_index": 0,
            "start_s": 0.0,
            "end_s": 1.0,
            "match": False,
            "reason_codes": ["orientation"],
            "summary": "The robot orientation differs.",
        },
        0,
    )


def test_visual_match_cannot_include_mismatch_reason() -> None:
    with pytest.raises(ValueError, match="cannot carry"):
        validate_visual_verdict(
            {
                "window_index": 0,
                "start_s": 0.0,
                "end_s": 1.0,
                "match": True,
                "reason_codes": ["orientation"],
                "summary": "Contradictory output.",
            },
            0,
        )
