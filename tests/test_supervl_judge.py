import json
from pathlib import Path

import pytest

from tools import supervl_judge
from tools.cosmos_job import visual_judge


def test_last_json_parser_uses_final_object_after_reasoning_leak() -> None:
    raw = (
        'I should inspect the pose first. {"note": "not the answer"}\n'
        '{"match": false, "reason_codes": ["orientation"], '
        '"summary": "The orientations differ."}'
    )

    assert supervl_judge.parse_last_json_object(raw) == {
        "match": False,
        "reason_codes": ["orientation"],
        "summary": "The orientations differ.",
    }


def test_last_json_parser_rejects_truncated_answer() -> None:
    raw = 'Reasoning finished. {"match": true, "reason_codes": [], "summary": "same"'

    with pytest.raises(ValueError, match="no complete JSON object"):
        supervl_judge.parse_last_json_object(raw)


def test_supervl_reuses_cosmos_schema_validator() -> None:
    assert supervl_judge.validate_verdict is visual_judge.validate_verdict

    with pytest.raises(ValueError, match="unknown reason codes"):
        supervl_judge.parse_last_json_object(
            '{"match": false, "reason_codes": ["invented"], "summary": "Mismatch."}'
        )


def test_invalid_model_output_fails_closed_without_raw_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "window.jpg"
    image.write_bytes(b"not-a-real-jpeg")

    def fake_post(body, key, timeout_s):
        assert body["messages"][0]["content"][0]["type"] == "image_url"
        assert key == "secret"
        assert timeout_s == 1.0
        return (
            {
                "id": "request-1",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"match": true'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 1200,
                    "total_tokens": 1300,
                },
            },
            "request-1",
        )

    monkeypatch.setattr(supervl_judge, "_post", fake_post)
    result, cost = supervl_judge.judge_window(
        image,
        key="secret",
        max_tokens=1200,
        timeout_s=1.0,
    )

    assert result["status"] == "invalid"
    assert result["error"] == "invalid_model_output"
    assert "match" not in result
    assert "raw" not in json.dumps(result)
    assert cost > 0
