import hashlib
from pathlib import Path

import pytest

from showhand.cli import _validate_completion


def _evidence(tmp_path: Path) -> tuple[dict, dict, Path, Path]:
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text("monotonic_ns\n1000000000\n1610000000\n", encoding="utf-8")
    telemetry_sha256 = hashlib.sha256(telemetry.read_bytes()).hexdigest()
    sonic_console = tmp_path / "sonic.log"
    sonic_console.write_text(
        "SHOWHAND_RUN_ID=test-run\n"
        + "\n".join(
            f"[ZMQEndpointInterface] Protocol v3: Received SMPL action (single) - frame_index: {i}"
            for i in range(3)
        )
        + "\n",
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
        "SHOWHAND_RUN_ID=test-run\n"
        "[ZMQEndpointInterface] Protocol v3: Received SMPL action (single) - frame_index: 2\n",
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
    with pytest.raises(ValueError, match="SONIC log run_id differs"):
        _validate_completion(timing, metadata, telemetry, sonic_console)
