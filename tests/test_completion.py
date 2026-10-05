import pytest

from showhand.cli import _validate_completion


def _evidence() -> tuple[dict, dict]:
    timing = {
        "replay_end_monotonic_ns": 1_000_000_000,
        "completion_request_monotonic_ns": 1_010_000_000,
        "completion_status": "completed",
        "output_frames": 3,
        "expected_final_frame_index": 2,
        "simulator_telemetry_steps": 400,
        "simulator_last_telemetry_monotonic_ns": 1_610_000_000,
        "post_roll_s": 0.6,
        "artifacts_flushed_monotonic_ns": 1_620_000_000,
    }
    metadata = {
        "completion_request_monotonic_ns": 1_010_000_000,
        "completion_status": "completed",
        "expected_final_frame_index": 2,
        "expected_output_frames": 3,
        "telemetry_steps": 400,
        "last_telemetry_monotonic_ns": 1_610_000_000,
        "post_roll_s": 0.6,
    }
    return timing, metadata


def test_completion_requires_flushed_full_drain() -> None:
    timing, metadata = _evidence()
    _validate_completion(timing, metadata)


def test_completion_rejects_short_controller_drain() -> None:
    timing, metadata = _evidence()
    timing["simulator_last_telemetry_monotonic_ns"] = 1_609_999_999
    metadata["last_telemetry_monotonic_ns"] = 1_609_999_999
    with pytest.raises(ValueError, match="controller drain"):
        _validate_completion(timing, metadata)


def test_completion_rejects_pre_flush_acknowledgement() -> None:
    timing, metadata = _evidence()
    timing["artifacts_flushed_monotonic_ns"] = 1_610_000_000
    with pytest.raises(ValueError, match="before artifacts were flushed"):
        _validate_completion(timing, metadata)
