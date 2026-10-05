import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from showhand.records import validate_take_record, write_take_record


def _record(tmp_path: Path) -> dict:
    threshold = Path("config/thresholds.yaml")
    threshold_commit_sha = subprocess.check_output(
        ["git", "rev-list", "-1", "HEAD", "--", threshold.as_posix()], text=True
    ).strip()
    threshold_sha256 = hashlib.sha256(threshold.read_bytes()).hexdigest()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text("monotonic_ns\n1000000000\n1610000000\n", encoding="utf-8")
    telemetry_sha256 = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    sim_metadata = tmp_path / "sim_meta.json"
    sim_metadata.write_text(
        json.dumps(
            {
                "run_id": "test-run",
                "completion_request_monotonic_ns": 1_010_000_000,
                "completion_status": "completed",
                "expected_final_frame_index": 2,
                "expected_output_frames": 3,
                "telemetry_steps": 2,
                "last_telemetry_monotonic_ns": 1_610_000_000,
                "replay_end_monotonic_ns": 1_000_000_000,
                "telemetry_sha256": telemetry_sha256,
                "telemetry_bytes": telemetry.stat().st_size,
                "post_roll_s": 0.6,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    metric_values = {
        "tracking_mean_abs_error_rad": 0.1,
        "tracking_p95_abs_error_rad": 0.2,
        "root_height_min_m": 0.5,
        "root_tilt_max_deg": 2.0,
        "foot_slip_max_m_s": 0.0,
        "foot_slip_seconds": 0.0,
        "out_of_balance_seconds": 0.0,
        "falls": 0,
        "pass": True,
        "reason_codes": [],
    }
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "overall": metric_values,
                "post_roll_evaluated_s": 0.61,
                "retargeter": "test-retargeter",
                "threshold_sha256": threshold_sha256,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sonic_console = tmp_path / "sonic.log"
    sonic_console.write_text(
        "SHOWHAND_RUN_BEGIN=test-run\n"
        "Protocol v3: Received SMPL action (single) - frame_index: 0\n"
        "Protocol v3: Received SMPL action (single) - frame_index: 1\n"
        "Protocol v3: Received SMPL action (single) - frame_index: 2\n"
        "SHOWHAND_RUN_END=test-run exit=0\n",
        encoding="utf-8",
    )
    code_commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    replay_timing = tmp_path / "replay_timing.json"
    replay_timing.write_text(
        json.dumps(
            {
                "run_id": "test-run",
                "code_commit_sha": code_commit_sha,
                "code_tree_clean": True,
                "source_frames": 3,
                "source_fps": 2.0,
                "source_duration_s": 1.0,
                "output_frames": 3,
                "expected_final_frame_index": 2,
                "replay_end_monotonic_ns": 1_000_000_000,
                "completion_request_monotonic_ns": 1_010_000_000,
                "completion_status": "completed",
                "simulator_telemetry_steps": 2,
                "simulator_last_telemetry_monotonic_ns": 1_610_000_000,
                "simulator_telemetry_sha256": telemetry_sha256,
                "simulator_telemetry_bytes": telemetry.stat().st_size,
                "post_roll_s": 0.6,
                "artifacts_flushed_monotonic_ns": 1_620_000_000,
                "publisher_warmup_s": 0.5,
                "max_allowed_jitter_s": 0.01,
                "publish_jitter_max_s": 0.001,
                "publish_jitter_p95_s": 0.0001,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "schema_version": 1,
        "take_id": "stock-1",
        "label": "PLUMBING TEST",
        "threshold_commit_sha": threshold_commit_sha,
        "threshold_path": str(threshold),
        "threshold_sha256": threshold_sha256,
        "code_commit_sha": code_commit_sha,
        "code_tree_clean": True,
        "source": {
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "frames": 3,
            "fps": 2.0,
            "pose_duration_s": 1.0,
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
        "metrics": {**metric_values, "retargeter": "test-retargeter"},
        "replay_validation": {
            "run_id": "test-run",
            "publisher_warmup_s": 0.5,
            "max_allowed_jitter_s": 0.01,
            "publish_jitter_max_s": 0.001,
            "publish_jitter_p95_s": 0.0001,
            "sonic_received_frames": 3,
            "sonic_first_frame": 0,
            "sonic_final_frame": 2,
            "telemetry_steps": 2,
            "telemetry_bytes": telemetry.stat().st_size,
            "telemetry_sha256": telemetry_sha256,
            "replay_timing_sha256": hashlib.sha256(replay_timing.read_bytes()).hexdigest(),
            "post_roll_evaluated_s": 0.61,
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


def test_take_record_accepts_stephen_take(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["label"] = "Stephen's take"
    output = tmp_path / "record.json"
    write_take_record(output, record)
    assert '"label": "Stephen\'s take"' in output.read_text(encoding="utf-8")


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


def test_take_record_rejects_supplied_run_identity_mismatch(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["replay_validation"]["run_id"] = "other-run"
    with pytest.raises(ValueError, match="supplied run_id differs"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_rejects_metric_artifact_mismatch(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["metrics"]["falls"] = 1
    record["metrics"]["pass"] = False
    record["metrics"]["reason_codes"] = ["fall"]
    with pytest.raises(ValueError, match="differs from metrics artifact"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_rejects_mirrored_but_wrong_metric_verdict(tmp_path: Path) -> None:
    record = _record(tmp_path)
    metrics_path = Path(record["artifacts"]["metrics"])
    artifact_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    artifact_metrics["overall"]["tracking_mean_abs_error_rad"] = 9.0
    metrics_path.write_text(json.dumps(artifact_metrics) + "\n", encoding="utf-8")
    record["metrics"]["tracking_mean_abs_error_rad"] = 9.0
    with pytest.raises(ValueError, match="reason codes disagree with frozen thresholds"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_rejects_wrong_pass_with_correct_reason_codes(tmp_path: Path) -> None:
    record = _record(tmp_path)
    metrics_path = Path(record["artifacts"]["metrics"])
    artifact_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    artifact_metrics["overall"]["tracking_mean_abs_error_rad"] = 9.0
    artifact_metrics["overall"]["reason_codes"] = ["tracking_mean_abs_error_rad"]
    metrics_path.write_text(json.dumps(artifact_metrics) + "\n", encoding="utf-8")
    record["metrics"]["tracking_mean_abs_error_rad"] = 9.0
    record["metrics"]["reason_codes"] = ["tracking_mean_abs_error_rad"]
    with pytest.raises(ValueError, match="pass verdict disagrees with frozen thresholds"):
        write_take_record(tmp_path / "record.json", record)


def test_validate_take_record_rejects_direct_run_id_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "record.json"
    write_take_record(output, _record(tmp_path))
    record = json.loads(output.read_text(encoding="utf-8"))
    record["replay_validation"]["run_id"] = "other-run"
    with pytest.raises(ValueError, match="run_id differs from replay timing"):
        validate_take_record(record)


def test_take_record_rejects_uncommitted_threshold_claim(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["threshold_commit_sha"] = "0" * 40
    with pytest.raises(ValueError, match="threshold_commit_sha does not name a commit"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_rejects_threshold_commit_after_replay_commit(tmp_path: Path) -> None:
    record = _record(tmp_path)
    replay_timing_path = Path(record["artifacts"]["replay_timing"])
    replay_timing = json.loads(replay_timing_path.read_text(encoding="utf-8"))
    replay_commit = subprocess.check_output(["git", "rev-parse", "HEAD^"], text=True).strip()
    replay_timing["code_commit_sha"] = replay_commit
    replay_timing_path.write_text(json.dumps(replay_timing) + "\n", encoding="utf-8")
    record["code_commit_sha"] = replay_commit
    record["threshold_commit_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    record["replay_validation"]["replay_timing_sha256"] = hashlib.sha256(
        replay_timing_path.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="not an ancestor"):
        write_take_record(tmp_path / "record.json", record)


def test_take_record_rejects_wrong_threshold_blob_at_replay_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path)
    code_commit_sha = record["code_commit_sha"]
    assert record["threshold_commit_sha"] != code_commit_sha
    original_run = subprocess.run

    def fake_run(
        args: list[str], *positional: object, **keywords: object
    ) -> subprocess.CompletedProcess:
        replay_threshold_ref = f"{code_commit_sha}:{Path(record['threshold_path']).as_posix()}"
        if args == ["git", "show", replay_threshold_ref]:
            return subprocess.CompletedProcess(args, 0, stdout=b"different threshold bytes\n")
        return original_run(args, *positional, **keywords)

    monkeypatch.setattr("showhand.records.subprocess.run", fake_run)
    with pytest.raises(ValueError, match="replay code commit contains different threshold bytes"):
        write_take_record(tmp_path / "record.json", record)
