import pytest

from showhand.guard import GroundingError, guard_fusion

METRIC = {
    "metrics:second:0": {
        "start_s": 0.0,
        "end_s": 1.0,
        "pass": False,
        "reason_codes": ["root_tilt_deg"],
    }
}
VISUAL = {
    "visual:second:0": {
        "start_s": 0.0,
        "end_s": 1.0,
        "match": False,
        "reason_codes": ["upper_body_pose"],
    }
}


def test_guard_accepts_grounded_reshow() -> None:
    output = {
        "decision": "reshow",
        "reshow_windows": [
            {"start_s": 0.0, "end_s": 1.0, "reason": "root_tilt_deg in cited evidence"}
        ],
        "evidence_refs": ["metrics:second:0"],
    }
    assert guard_fusion(output, METRIC, VISUAL, 1.0) == output


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (
            {
                "decision": "reshow",
                "reshow_windows": [{"start_s": 0.0, "end_s": 1.0, "reason": "looks wrong"}],
                "evidence_refs": ["metrics:second:0"],
            },
            "must equal",
        ),
        (
            {"decision": "accept", "reshow_windows": [], "evidence_refs": []},
            "at least one",
        ),
        (
            {
                "decision": "reshow",
                "reshow_windows": [
                    {"start_s": 1.0, "end_s": 2.0, "reason": "root_tilt_deg in cited evidence"}
                ],
                "evidence_refs": ["metrics:second:0"],
            },
            "outside",
        ),
    ],
)
def test_guard_rejects_ungrounded_claims(output: dict, message: str) -> None:
    with pytest.raises(GroundingError, match=message):
        guard_fusion(output, METRIC, VISUAL, 1.0)
