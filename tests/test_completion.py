import csv
import hashlib
from pathlib import Path

import pytest

from showhand.cli import _validate_completion, validate_saved_replay


def _evidence(tmp_path: Path) -> tuple[dict, dict, Path, Path]:
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text("monotonic_ns\n1000000000\n1610000000\n", encoding="utf-8")
    telemetry_sha256 = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    sonic_console = tmp_path / "sonic.log"
    sonic_console.write_text(
        "SHOWHAND_RUN_BEGIN=test-run\n"
        + "\n".join(
            f"[ZMQEndpointInterface] Protocol v3: Received SMPL action (single) - frame_index: {i}"
            for i in range(3)
        )
        + "\nSHOWHAND_RUN_END=test-run exit=0\n",
        encoding="utf-8",
    )
    timing = {
        "run_id": "test-run",
        "replay_end_monotonic_ns": 1_000_000_000,
        "completion_request_monotonic_ns": 1_010_000_000,
        "completion_status": "completed",
        "output_frames": 3,
        "expected_final_frame_index": 2,
        "simulator_telemetry_steps": 2,
        "simulator_last_telemetry_monotonic_ns": 1_610_000_000,
        "simulator_telemetry_sha256": telemetry_sha256,
        "simulator_telemetry_bytes": telemetry.stat().st_size,
        "post_roll_s": 0.6,
        "artifacts_flushed_monotonic_ns": 1_620_000_000,
    }
    metadata = {
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
    return timing, metadata, telemetry, sonic_console


def test_completion_requires_flushed_full_drain(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_short_controller_drain(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    telemetry.write_text("monotonic_ns\n1000000000\n1609999999\n", encoding="utf-8")
    digest = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    timing["simulator_telemetry_sha256"] = digest
    timing["simulator_telemetry_bytes"] = telemetry.stat().st_size
    metadata["telemetry_sha256"] = digest
    metadata["telemetry_bytes"] = telemetry.stat().st_size
    timing["simulator_last_telemetry_monotonic_ns"] = 1_609_999_999
    metadata["last_telemetry_monotonic_ns"] = 1_609_999_999
    with pytest.raises(ValueError, match="controller drain"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_pre_flush_acknowledgement(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    timing["artifacts_flushed_monotonic_ns"] = 1_610_000_000
    with pytest.raises(ValueError, match="before artifacts were flushed"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_changed_telemetry(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    telemetry.write_text("monotonic_ns\n1000000000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="telemetry bytes differ"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_claimed_tail_after_actual_csv_tail(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    telemetry.write_text("monotonic_ns\n1000000000\n1500000000\n", encoding="utf-8")
    digest = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    timing["simulator_telemetry_sha256"] = digest
    timing["simulator_telemetry_bytes"] = telemetry.stat().st_size
    metadata["telemetry_sha256"] = digest
    metadata["telemetry_bytes"] = telemetry.stat().st_size
    with pytest.raises(ValueError, match="final row timestamp"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_missing_controller_frame(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    sonic_console.write_text(
        "SHOWHAND_RUN_BEGIN=test-run\n"
        "[ZMQEndpointInterface] Protocol v3: Received SMPL action (single) - frame_index: 2\n"
        "SHOWHAND_RUN_END=test-run exit=0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="receipt is incomplete"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_stale_sonic_run_id(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    sonic_console.write_text(
        sonic_console.read_text(encoding="utf-8").replace("test-run", "stale-run"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="successful run boundary"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_only_receipts_outside_run_boundaries(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    stale_receipts = "\n".join(
        f"[ZMQEndpointInterface] Protocol v3: Received SMPL action (single) - frame_index: {i}"
        for i in range(3)
    )
    sonic_console.write_text(
        stale_receipts
        + "\nSHOWHAND_RUN_BEGIN=test-run\n"
        + "controller active\nSHOWHAND_RUN_END=test-run exit=0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="receipt is incomplete"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_ignores_conflicting_receipts_outside_run_boundaries(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    valid_receipts = "\n".join(
        f"Protocol v3: Received SMPL action (single) - frame_index: {i}" for i in range(3)
    )
    sonic_console.write_text(
        "Protocol v3: Received SMPL action (single) - frame_index: 99\n"
        "Protocol v3: Received SMPL action (single) - frame_index: 2\n"
        "SHOWHAND_RUN_BEGIN=test-run\n" + valid_receipts + "\nSHOWHAND_RUN_END=test-run exit=0\n"
        "Protocol v3: Received SMPL action (single) - frame_index: 0\n"
        "Protocol v3: Received SMPL action (single) - frame_index: 100\n",
        encoding="utf-8",
    )
    _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_duplicate_run_boundaries(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    sonic_console.write_text(
        sonic_console.read_text(encoding="utf-8")
        + "SHOWHAND_RUN_BEGIN=test-run\nSHOWHAND_RUN_END=test-run exit=0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="one successful run boundary"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_reversed_run_boundaries(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    sonic_console.write_text(
        "SHOWHAND_RUN_END=test-run exit=0\nSHOWHAND_RUN_BEGIN=test-run\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="out of order"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def test_completion_rejects_nonzero_end_marker(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _evidence(tmp_path)
    sonic_console.write_text(
        sonic_console.read_text(encoding="utf-8").replace("exit=0", "exit=1"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="successful run boundary"):
        _validate_completion(timing, metadata, telemetry, sonic_console)


def _dense_replay(tmp_path: Path) -> tuple[dict, dict, Path, Path]:
    telemetry = tmp_path / "telemetry.csv"
    names = [
        "monotonic_ns",
        "sim_time_s",
        "root_height_m",
        "root_tilt_deg",
        "left_foot_slip_m_s",
        "right_foot_slip_m_s",
        "out_of_balance",
        "fall_event",
        *[f"q_{index}" for index in range(29)],
    ]
    start_ns = 1_000_000_000
    last_ns = 1_610_000_000
    stamps = list(range(start_ns, last_ns + 1, 5_000_000))
    with telemetry.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for index, stamp in enumerate(stamps):
            writer.writerow(
                {
                    "monotonic_ns": stamp,
                    "sim_time_s": index * 0.005,
                    "root_height_m": 0.8,
                    "root_tilt_deg": 0.0,
                    "left_foot_slip_m_s": 0.0,
                    "right_foot_slip_m_s": 0.0,
                    "out_of_balance": 0,
                    "fall_event": 0,
                    **{f"q_{joint}": 0.0 for joint in range(29)},
                }
            )
    digest = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    sonic_console = tmp_path / "sonic.log"
    sonic_console.write_text(
        "SHOWHAND_RUN_BEGIN=test-run\n"
        + "\n".join(
            f"Protocol v3: Received SMPL action (single) - frame_index: {i}" for i in range(3)
        )
        + "\nSHOWHAND_RUN_END=test-run exit=0\n",
        encoding="utf-8",
    )
    timing = {
        "run_id": "test-run",
        "replay_start_monotonic_ns": start_ns,
        "replay_end_monotonic_ns": start_ns,
        "completion_request_monotonic_ns": 1_010_000_000,
        "completion_status": "completed",
        "output_frames": 3,
        "expected_final_frame_index": 2,
        "simulator_telemetry_steps": len(stamps),
        "simulator_last_telemetry_monotonic_ns": last_ns,
        "simulator_telemetry_sha256": digest,
        "simulator_telemetry_bytes": telemetry.stat().st_size,
        "post_roll_s": 0.6,
        "artifacts_flushed_monotonic_ns": last_ns + 10_000_000,
        "max_allowed_jitter_s": 0.01,
        "publish_jitter_max_s": 0.001,
    }
    metadata = {
        "run_id": "test-run",
        "completion_request_monotonic_ns": 1_010_000_000,
        "completion_status": "completed",
        "expected_final_frame_index": 2,
        "expected_output_frames": 3,
        "telemetry_steps": len(stamps),
        "last_telemetry_monotonic_ns": last_ns,
        "replay_end_monotonic_ns": start_ns,
        "telemetry_sha256": digest,
        "telemetry_bytes": telemetry.stat().st_size,
        "post_roll_s": 0.6,
        "elastic_band_release_monotonic_ns": start_ns - 1_000_000,
    }
    return timing, metadata, telemetry, sonic_console


def test_saved_replay_accepts_a_trace_inside_the_frozen_gates(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _dense_replay(tmp_path)
    validate_saved_replay(timing, metadata, telemetry, sonic_console)


def test_saved_replay_rejects_a_loosened_jitter_limit(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _dense_replay(tmp_path)
    timing["max_allowed_jitter_s"] = 0.02
    with pytest.raises(ValueError, match="outside the frozen"):
        validate_saved_replay(timing, metadata, telemetry, sonic_console)


def test_saved_replay_rejects_a_telemetry_gap(tmp_path: Path) -> None:
    timing, metadata, telemetry, sonic_console = _dense_replay(tmp_path)
    with telemetry.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys())
    kept = [row for row in rows if not (1_200_000_000 <= int(row["monotonic_ns"]) < 1_260_000_000)]
    with telemetry.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    digest = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    timing["simulator_telemetry_sha256"] = digest
    timing["simulator_telemetry_bytes"] = telemetry.stat().st_size
    timing["simulator_telemetry_steps"] = len(kept)
    metadata["telemetry_sha256"] = digest
    metadata["telemetry_bytes"] = telemetry.stat().st_size
    metadata["telemetry_steps"] = len(kept)
    with pytest.raises(ValueError, match="telemetry gap"):
        validate_saved_replay(timing, metadata, telemetry, sonic_console)
