from __future__ import annotations

import json
from typing import Any

import pytest

from showhand.fusion import MAX_ATTEMPTS, deterministic_fallback, request_fusion


def _metrics(*, overall_pass: bool, failing: dict[int, str]) -> dict[str, Any]:
    per_second = []
    for index in range(3):
        code = failing.get(index)
        per_second.append(
            {
                "evidence_ref": f"metrics:second:{index}",
                "start_s": float(index),
                "end_s": float(index + 1),
                "pass": code is None,
                "reason_codes": [code] if code else [],
            }
        )
    return {
        "duration_s": 3.0,
        "overall": {
            "pass": overall_pass,
            "reason_codes": [] if overall_pass else ["out_of_balance"],
        },
        "per_second": per_second,
    }


def _visual(mismatch: dict[int, str]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_ref": f"visual:second:{index}",
            "start_s": float(index),
            "end_s": float(index + 1),
            "match": index not in mismatch,
            "reason_codes": [mismatch[index]] if index in mismatch else [],
        }
        for index in range(3)
    ]


def _raw(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
    }


class FakePost:
    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, body: dict[str, Any], key: str, timeout_s: float) -> tuple[dict, str]:
        self.bodies.append(json.loads(json.dumps(body)))
        return _raw(self.answers.pop(0)), f"req-{len(self.bodies)}"


ACCEPT = {"decision": "accept", "reshow_windows": [], "evidence_refs": ["metrics:overall"]}
RESHOW_1 = {
    "decision": "reshow",
    "reshow_windows": [
        {"start_s": 1.0, "end_s": 2.0, "reason": "tracking_p95_abs_error_rad in cited evidence"}
    ],
    "evidence_refs": ["metrics:second:1"],
}


def test_a_grounded_first_answer_is_used() -> None:
    post = FakePost([RESHOW_1])
    result = request_fusion(
        _metrics(overall_pass=False, failing={1: "tracking_p95_abs_error_rad"}),
        _visual({}),
        api_key="test-key",
        post=post,
    )
    assert result["status"] == "passed_first"
    assert result["decided_by"] == "nemotron"
    assert result["output"] == RESHOW_1
    assert [item["guard"] for item in result["attempts"]] == ["passed"]
    assert result["cost_usd"] == pytest.approx(1000 / 1e6 * 0.06 + 100 / 1e6 * 0.24)


def test_a_refused_answer_is_retried_with_the_refusal() -> None:
    post = FakePost([ACCEPT, RESHOW_1])
    result = request_fusion(
        _metrics(overall_pass=False, failing={1: "tracking_p95_abs_error_rad"}),
        _visual({}),
        api_key="test-key",
        post=post,
    )
    assert result["status"] == "passed_after_retry"
    assert [item["guard"] for item in result["attempts"]] == ["refused", "passed"]
    assert "mandatory negative evidence" in result["attempts"][0]["guard_error"]
    retry_messages = post.bodies[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": json.dumps(ACCEPT)}
    assert "The grounding guard refused that answer" in retry_messages[-1]["content"]
    assert result["request_id"] == "req-2"
    assert len(result["attempts"]) == MAX_ATTEMPTS


def test_two_refusals_fall_back_to_every_negative_window() -> None:
    post = FakePost([ACCEPT, ACCEPT])
    metrics = _metrics(overall_pass=False, failing={0: "out_of_balance"})
    result = request_fusion(metrics, _visual({2: "orientation"}), api_key="test-key", post=post)
    assert result["status"] == "fallback_after_guard_refusals"
    assert result["decided_by"] == "deterministic_fallback"
    assert result["guard"] == "passed"
    assert result["output"] == {
        "decision": "reshow",
        "reshow_windows": [
            {"start_s": 0.0, "end_s": 1.0, "reason": "out_of_balance in cited evidence"},
            {"start_s": 2.0, "end_s": 3.0, "reason": "orientation in cited evidence"},
        ],
        "evidence_refs": ["metrics:second:0", "visual:second:2"],
    }
    assert len(post.bodies) == MAX_ATTEMPTS


def test_a_failing_take_with_no_failing_second_still_re_shows() -> None:
    post = FakePost([ACCEPT, ACCEPT])
    result = request_fusion(
        _metrics(overall_pass=False, failing={}), _visual({}), api_key="test-key", post=post
    )
    assert result["output"]["decision"] == "reshow"
    assert result["output"]["reshow_windows"] == []
    assert result["guard"].startswith("refused:")


def test_the_fallback_accepts_only_when_nothing_is_negative() -> None:
    clean = deterministic_fallback(_metrics(overall_pass=True, failing={}), _visual({}))
    assert clean["decision"] == "accept"


def test_missing_usage_is_an_error() -> None:
    def post(body: dict[str, Any], key: str, timeout_s: float) -> tuple[dict, str]:
        raw = _raw(RESHOW_1)
        del raw["usage"]
        return raw, "req-1"

    with pytest.raises(RuntimeError, match="missing token usage"):
        request_fusion(
            _metrics(overall_pass=False, failing={1: "tracking_p95_abs_error_rad"}),
            _visual({}),
            api_key="test-key",
            post=post,
        )
