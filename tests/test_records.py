import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from showhand.records import validate_take_record, write_take_record


def _record(tmp_path: Path) -> dict:
    threshold = tmp_path / "thresholds.yaml"
    threshold.write_text("frozen: true\n", encoding="utf-8")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text("monotonic_ns\n1\n", encoding="utf-8")
    sim_metadata = tmp_path / "sim_meta.json"
    sim_metadata.write_text("{}\n", encoding="utf-8")
    metrics = tmp_path / "metrics.json"
    metrics.write_text("{}\n", encoding="utf-8")
    sonic_console = tmp_path / "sonic.log"
    sonic_console.write_text("controller evidence\n", encoding="utf-8")
    code_commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    replay_timing = tmp_path / "replay_timing.json"
    replay_timing.write_text(
        json.dumps(
            {
                "run_id": "test-run",
                "code_commit_sha": code_commit_sha,
                "code_tree_clean": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "schema_version": 1,
        "take_id": "stock-1",
        "label": "PLUMBING TEST",
        "threshold_commit_sha": "0" * 40,
        "threshold_path": str(threshold),
        "threshold_sha256": hashlib.sha256(threshold.read_bytes()).hexdigest(),
        "code_commit_sha": code_commit_sha,
        "code_tree_clean": True,
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "artifacts": {
            "sim_step_telemetry": str(telemetry),
            "sim_metadata": str(sim_metadata),
            "replay_timing": str(replay_timing),
            "sonic_console": str(sonic_console),
            "metrics": str(metrics),
            "visual_output": None,
        },
        "timings_s": {"gem_x": 1.0},
        "metrics": {"pass": True, "reason_codes": []},
        "replay_validation": {
            "run_id": "test-run",
            "telemetry_sha256": hashlib.sha256(telemetry.read_bytes()).hexdigest(),
            "replay_timing_sha256": hashlib.sha256(replay_timing.read_bytes()).hexdigest(),
        },
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
    assert b"\r\n" not in output.read_bytes()


def test_take_record_refuses_unlabeled_stock_output(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["label"] = "evidence"
    with pytest.raises(ValueError, match="PLUMBING TEST"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_requires_decisive_artifacts(tmp_path: Path) -> None:
    record = _record(tmp_path)
    del record["artifacts"]["sim_step_telemetry"]
    with pytest.raises(ValueError, match="required file artifact is missing"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_requires_decisive_artifact_hashes(tmp_path: Path) -> None:
    output = tmp_path / "record.json"
    write_take_record(output, _record(tmp_path))
    record = json.loads(output.read_text(encoding="utf-8"))
    del record["artifact_sha256"]["sim_step_telemetry"]
    with pytest.raises(ValueError, match="required artifact hash"):
        validate_take_record(record)


def test_take_record_rejects_replay_hash_mismatch(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["replay_validation"]["telemetry_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="replay validation hash differs"):
        write_take_record(tmp_path / "record.json", record)
