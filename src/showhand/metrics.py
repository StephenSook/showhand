"""Deterministic tracking and balance metrics for one offline take."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

RETARGETER_NAME = "NVIDIA SOMA Retargeter NewtonPipeline soma_to_unitree_g1"
JOINT_SUFFIX = "_joint_dof"
G1_JOINT_NAMES = (
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)
EXPECTED_RETARGET_COLUMNS = tuple(f"{name}_dof" for name in G1_JOINT_NAMES)


class MetricsInputError(ValueError):
    """Raised when a metrics input is missing required measured fields."""


@dataclass(frozen=True)
class TargetMotion:
    fps: float
    joint_names: tuple[str, ...]
    joint_angles_rad: np.ndarray

    @property
    def duration_s(self) -> float:
        return max(0.0, (len(self.joint_angles_rad) - 1) / self.fps)


def load_retargeted_motion(path: str | Path, fps: float) -> TargetMotion:
    if fps <= 0:
        raise MetricsInputError("retargeted motion fps must be positive")
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise MetricsInputError("retargeted CSV has no header")
        joint_names = tuple(name for name in reader.fieldnames if name.endswith(JOINT_SUFFIX))
        if joint_names != EXPECTED_RETARGET_COLUMNS:
            raise MetricsInputError(
                "retargeted G1 joint names or order differ from the frozen 29-DoF mapping"
            )
        rows = [[float(row[name]) for name in joint_names] for row in reader]
    if not rows:
        raise MetricsInputError("retargeted CSV has no frames")
    return TargetMotion(
        fps=fps,
        joint_names=joint_names,
        joint_angles_rad=np.deg2rad(np.asarray(rows, dtype=np.float64)),
    )


def load_sim_telemetry(
    path: str | Path,
    replay_start_monotonic_ns: int,
    replay_end_monotonic_ns: int,
) -> list[dict[str, float | int]]:
    if replay_end_monotonic_ns <= replay_start_monotonic_ns:
        raise MetricsInputError("replay end must be after replay start")
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise MetricsInputError("telemetry CSV has no header")
        required = {
            "monotonic_ns",
            "sim_time_s",
            "root_height_m",
            "root_tilt_deg",
            "left_foot_slip_m_s",
            "right_foot_slip_m_s",
            "out_of_balance",
            "fall_event",
            *(f"q_{i}" for i in range(29)),
        }
        missing = required.difference(reader.fieldnames)
        if missing:
            raise MetricsInputError(f"telemetry missing fields: {', '.join(sorted(missing))}")
        rows = []
        for raw in reader:
            stamp = int(raw["monotonic_ns"])
            if replay_start_monotonic_ns <= stamp <= replay_end_monotonic_ns:
                row = {name: float(raw[name]) for name in required if name != "monotonic_ns"}
                row["monotonic_ns"] = stamp
                rows.append(row)
    if not rows:
        raise MetricsInputError("no telemetry samples fall inside the replay interval")
    return rows


def compute_take_metrics(
    target: TargetMotion,
    telemetry: list[dict[str, float | int]],
    replay_start_monotonic_ns: int,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    elapsed_s = np.asarray(
        [(row["monotonic_ns"] - replay_start_monotonic_ns) / 1_000_000_000 for row in telemetry],
        dtype=np.float64,
    )
    measured = np.asarray(
        [[row[f"q_{i}"] for i in range(29)] for row in telemetry], dtype=np.float64
    )
    target_angles = _interpolate_target(target, elapsed_s)
    abs_error = np.abs(_wrapped_angle_delta(measured, target_angles))
    sample_error_mean = abs_error.mean(axis=1)
    sample_error_p95 = np.percentile(abs_error, 95, axis=1)
    root_height = np.asarray([row["root_height_m"] for row in telemetry])
    root_tilt = np.asarray([row["root_tilt_deg"] for row in telemetry])
    foot_slip = np.maximum(
        np.asarray([row["left_foot_slip_m_s"] for row in telemetry]),
        np.asarray([row["right_foot_slip_m_s"] for row in telemetry]),
    )
    out_of_balance = np.asarray([bool(row["out_of_balance"]) for row in telemetry])
    falls = np.asarray([bool(row["fall_event"]) for row in telemetry])
    dt = _sample_durations(elapsed_s)
    slip_active = foot_slip > float(thresholds["foot_slip"]["contact_speed_threshold_m_s"])

    window_s = float(thresholds["window_seconds"])
    duration_s = min(float(elapsed_s[-1]), target.duration_s)
    per_second = []
    for start_s in np.arange(0.0, max(duration_s, 1e-12), window_s):
        end_s = min(start_s + window_s, duration_s)
        mask = (elapsed_s >= start_s) & (elapsed_s < end_s)
        if not mask.any():
            continue
        window_dt = np.minimum(dt[mask], np.maximum(0.0, end_s - elapsed_s[mask]))
        summary = _summarize_window(
            start_s,
            end_s,
            sample_error_mean[mask],
            sample_error_p95[mask],
            root_height[mask],
            root_tilt[mask],
            foot_slip[mask],
            falls[mask],
            out_of_balance[mask],
            slip_active[mask],
            window_dt,
            thresholds,
        )
        summary["evidence_ref"] = f"metrics:second:{len(per_second)}"
        per_second.append(summary)

    overall = _summarize_window(
        0.0,
        duration_s,
        sample_error_mean,
        sample_error_p95,
        root_height,
        root_tilt,
        foot_slip,
        falls,
        out_of_balance,
        slip_active,
        dt,
        thresholds,
    )
    return {
        "schema_version": 1,
        "retargeter": RETARGETER_NAME,
        "tracking_reference": "parallel_newtonpipeline_g1_reference_not_sonic_commands",
        "actual_joint_order": list(G1_JOINT_NAMES),
        "target_fps": target.fps,
        "target_frames": len(target.joint_angles_rad),
        "telemetry_samples": len(telemetry),
        "duration_s": round(duration_s, 6),
        "overall": overall,
        "per_second": per_second,
    }


def _interpolate_target(target: TargetMotion, elapsed_s: np.ndarray) -> np.ndarray:
    source_t = np.arange(len(target.joint_angles_rad), dtype=np.float64) / target.fps
    clipped = np.clip(elapsed_s, source_t[0], source_t[-1])
    output = np.empty((len(clipped), target.joint_angles_rad.shape[1]), dtype=np.float64)
    for index in range(target.joint_angles_rad.shape[1]):
        output[:, index] = np.interp(clipped, source_t, target.joint_angles_rad[:, index])
    return output


def _wrapped_angle_delta(measured: np.ndarray, target: np.ndarray) -> np.ndarray:
    return (measured - target + math.pi) % (2 * math.pi) - math.pi


def _sample_durations(elapsed_s: np.ndarray) -> np.ndarray:
    if len(elapsed_s) == 1:
        return np.asarray([0.0])
    deltas = np.diff(elapsed_s, append=elapsed_s[-1])
    deltas[-1] = 0.0
    return np.maximum(deltas, 0.0)


def _summarize_window(
    start_s: float,
    end_s: float,
    mean_error: np.ndarray,
    p95_error: np.ndarray,
    root_height: np.ndarray,
    root_tilt: np.ndarray,
    foot_slip: np.ndarray,
    falls: np.ndarray,
    out_of_balance: np.ndarray,
    slip_active: np.ndarray,
    dt: np.ndarray,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    values = {
        "start_s": round(float(start_s), 6),
        "end_s": round(float(end_s), 6),
        "tracking_mean_abs_error_rad": round(float(mean_error.mean()), 6),
        "tracking_p95_abs_error_rad": round(float(np.percentile(p95_error, 95)), 6),
        "root_height_min_m": round(float(root_height.min()), 6),
        "root_tilt_max_deg": round(float(root_tilt.max()), 6),
        "foot_slip_max_m_s": round(float(foot_slip.max()), 6),
        "foot_slip_seconds": round(float(dt[slip_active].sum()), 6),
        "falls": int(falls.sum()),
        "out_of_balance_seconds": round(float(dt[out_of_balance].sum()), 6),
    }
    reasons = metric_reason_codes(values, thresholds)
    values["pass"] = not reasons
    values["reason_codes"] = reasons
    return values


def metric_reason_codes(values: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    reasons = []
    if values["tracking_mean_abs_error_rad"] > thresholds["tracking"]["max_mean_abs_error_rad"]:
        reasons.append("tracking_mean_abs_error_rad")
    if values["tracking_p95_abs_error_rad"] > thresholds["tracking"]["max_p95_abs_error_rad"]:
        reasons.append("tracking_p95_abs_error_rad")
    if values["root_height_min_m"] < thresholds["balance"]["fall_root_height_m"]:
        reasons.append("root_height_m")
    if values["root_tilt_max_deg"] > thresholds["balance"]["max_root_tilt_deg"]:
        reasons.append("root_tilt_deg")
    if values["foot_slip_seconds"] > thresholds["foot_slip"]["max_slip_seconds"]:
        reasons.append("foot_slip")
    if values["out_of_balance_seconds"] > thresholds["balance"]["max_out_of_balance_seconds"]:
        reasons.append("out_of_balance")
    if thresholds["decision"]["any_fall_is_reshow"] and values["falls"] > 0:
        reasons.append("fall")
    return reasons


def collect_evidence(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["evidence_ref"]: item for item in metrics["per_second"]}


def iter_failed_windows(metrics: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return (item for item in metrics["per_second"] if not item["pass"])
