import csv
from pathlib import Path

import pytest

from showhand.metrics import (
    EXPECTED_RETARGET_COLUMNS,
    MetricsInputError,
    compute_take_metrics,
    load_retargeted_motion,
    load_sim_telemetry,
)
from showhand.thresholds import load_thresholds


def _write_target(path: Path) -> None:
    names = list(EXPECTED_RETARGET_COLUMNS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        writer.writerow([0.0] * 29)
        writer.writerow([0.0] * 29)
        writer.writerow([0.0] * 29)


def _write_telemetry(path: Path, *, bad: bool = False) -> None:
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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for index, stamp in enumerate((1_000_000_000, 1_500_000_000, 2_000_000_000)):
            row = {
                "monotonic_ns": stamp,
                "sim_time_s": index * 0.5,
                "root_height_m": 0.1 if bad and index == 1 else 0.8,
                "root_tilt_deg": 40.0 if bad and index == 1 else 0.0,
                "left_foot_slip_m_s": 0.2 if bad else 0.0,
                "right_foot_slip_m_s": 0.0,
                "out_of_balance": int(bad and index == 1),
                "fall_event": int(bad and index == 1),
                **{f"q_{joint}": 1.2 if bad else 0.0 for joint in range(29)},
            }
            writer.writerow(row)


def test_metrics_are_deterministic_and_flag_measured_failures(tmp_path: Path) -> None:
    target_path = tmp_path / "target.csv"
    telemetry_path = tmp_path / "telemetry.csv"
    _write_target(target_path)
    _write_telemetry(telemetry_path, bad=True)
    target = load_retargeted_motion(target_path, fps=2.0)
    telemetry = load_sim_telemetry(
        telemetry_path, 1_000_000_000, 2_000_000_000, 999_000_000, max_gap_s=0.5
    )
    thresholds = load_thresholds("config/thresholds.yaml")
    first = compute_take_metrics(target, telemetry, 1_000_000_000, thresholds)
    second = compute_take_metrics(target, telemetry, 1_000_000_000, thresholds)
    assert first == second
    assert first["overall"]["pass"] is False
    assert "fall" in first["overall"]["reason_codes"]
    assert "tracking_mean_abs_error_rad" in first["overall"]["reason_codes"]


def test_metrics_refuse_empty_replay_interval(tmp_path: Path) -> None:
    target_path = tmp_path / "target.csv"
    telemetry_path = tmp_path / "telemetry.csv"
    _write_target(target_path)
    _write_telemetry(telemetry_path)
    with pytest.raises(MetricsInputError, match="cover the complete replay interval"):
        load_sim_telemetry(
            telemetry_path, 3_000_000_000, 4_000_000_000, 2_000_000_000, max_gap_s=0.5
        )


def test_metrics_grade_post_roll_against_final_target_pose(tmp_path: Path) -> None:
    target_path = tmp_path / "target.csv"
    telemetry_path = tmp_path / "telemetry.csv"
    _write_target(target_path)
    _write_telemetry(telemetry_path)
    target = load_retargeted_motion(target_path, fps=2.0)
    telemetry = load_sim_telemetry(
        telemetry_path, 1_000_000_000, 2_000_000_000, 999_000_000, max_gap_s=0.5
    )
    late = dict(telemetry[-1])
    late.update(
        {
            "monotonic_ns": 2_500_000_000,
            "root_height_m": 0.0,
            "fall_event": 1.0,
            **{f"q_{joint}": 2.0 for joint in range(29)},
        }
    )
    telemetry.append(late)

    result = compute_take_metrics(
        target, telemetry, 1_000_000_000, load_thresholds("config/thresholds.yaml")
    )

    assert result["telemetry_samples"] == 4
    assert result["post_roll_evaluated_s"] == 0.5
    assert result["overall"]["pass"] is False
    assert "fall" in result["overall"]["reason_codes"]


def test_metrics_refuse_support_release_after_replay_start(tmp_path: Path) -> None:
    telemetry_path = tmp_path / "telemetry.csv"
    _write_telemetry(telemetry_path)
    with pytest.raises(MetricsInputError, match="support was released after"):
        load_sim_telemetry(
            telemetry_path,
            1_000_000_000,
            2_000_000_000,
            1_000_000_001,
            max_gap_s=0.5,
        )


def test_tracking_p95_is_flattened_across_joint_time_errors(tmp_path: Path) -> None:
    target_path = tmp_path / "target.csv"
    telemetry_path = tmp_path / "telemetry.csv"
    _write_target(target_path)
    _write_telemetry(telemetry_path)
    rows = list(csv.DictReader(telemetry_path.open(newline="", encoding="utf-8")))
    rows[1]["q_0"] = "1.0"
    rows[1]["q_1"] = "1.0"
    with telemetry_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    target = load_retargeted_motion(target_path, fps=2.0)
    telemetry = load_sim_telemetry(
        telemetry_path, 1_000_000_000, 2_000_000_000, 999_000_000, max_gap_s=0.5
    )
    result = compute_take_metrics(
        target, telemetry, 1_000_000_000, load_thresholds("config/thresholds.yaml")
    )
    assert result["overall"]["tracking_p95_abs_error_rad"] == 0.0


def test_retargeted_joint_order_is_enforced(tmp_path: Path) -> None:
    target_path = tmp_path / "target.csv"
    names = list(EXPECTED_RETARGET_COLUMNS)
    names[0], names[1] = names[1], names[0]
    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        writer.writerow([0.0] * 29)
    with pytest.raises(MetricsInputError, match="joint names or order"):
        load_retargeted_motion(target_path, fps=25.0)
