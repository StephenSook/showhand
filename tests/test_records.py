import hashlib
from pathlib import Path

import pytest

from showhand.records import write_take_record


def _record(tmp_path: Path) -> dict:
    threshold = tmp_path / "thresholds.yaml"
    threshold.write_text("frozen: true\n", encoding="utf-8")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    artifact = tmp_path / "metrics.json"
    artifact.write_text("{}\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "take_id": "stock-1",
        "label": "PLUMBING TEST",
        "threshold_commit_sha": "0" * 40,
        "threshold_path": str(threshold),
        "threshold_sha256": hashlib.sha256(threshold.read_bytes()).hexdigest(),
        "code_commit_sha": "0" * 40,
        "code_tree_clean": True,
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "artifacts": {"metrics": str(artifact), "visual_output": None},
        "timings_s": {"gem_x": 1.0},
        "metrics": {"pass": True, "reason_codes": []},
        "replay_validation": {"run_id": "test-run"},
        "visual_judge": {"status": "blocked_before_job_create", "job": {}},
        "fusion": {"status": "not_run_missing_visual_verdicts"},
        "cost_usd": {"nebius_gpu": 0.0, "token_factory": 0.0, "total": 0.0},
        "cleanup": {},
    }


def test_take_record_written(tmp_path: Path) -> None:
    output = tmp_path / "record.json"
    write_take_record(output, _record(tmp_path))
    assert "PLUMBING TEST" in output.read_text(encoding="utf-8")
    assert "artifact_sha256" in output.read_text(encoding="utf-8")


def test_take_record_refuses_unlabeled_stock_output(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["label"] = "evidence"
    with pytest.raises(ValueError, match="PLUMBING TEST"):
        write_take_record(tmp_path / "record.json", record)
