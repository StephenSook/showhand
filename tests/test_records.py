from pathlib import Path

import pytest

from showhand.records import write_take_record


def _record() -> dict:
    return {
        "schema_version": 1,
        "take_id": "stock-1",
        "label": "PLUMBING TEST",
        "threshold_commit_sha": "0" * 40,
        "threshold_sha256": "0" * 64,
        "code_commit_sha": "0" * 40,
        "source": {},
        "artifacts": {},
        "timings_s": {"gem_x": 1.0},
        "metrics": {},
        "visual_judge": {},
        "fusion": {},
        "cost_usd": {"total": 0.0},
        "cleanup": {},
    }


def test_take_record_written(tmp_path: Path) -> None:
    output = tmp_path / "record.json"
    write_take_record(output, _record())
    assert "PLUMBING TEST" in output.read_text(encoding="utf-8")


def test_take_record_refuses_unlabeled_stock_output(tmp_path: Path) -> None:
    record = _record()
    record["label"] = "evidence"
    with pytest.raises(ValueError, match="PLUMBING TEST"):
        write_take_record(tmp_path / "record.json", record)
