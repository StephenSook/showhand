#!/usr/bin/env python3
"""Run stock SONIC MuJoCo with a per-step physics trace."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np
from gear_sonic.utils.mujoco_sim.base_sim import BaseSimulator
from gear_sonic.utils.mujoco_sim.configs import SimLoopConfig


def _contact_state(model, data, floor_geom: int, foot_body: int) -> bool:
    for contact in data.contact[: data.ncon]:
        if contact.geom1 == floor_geom:
            other = contact.geom2
        elif contact.geom2 == floor_geom:
            other = contact.geom1
        else:
            continue
        if int(model.geom_bodyid[other]) == foot_body:
            return True
    return False


def _foot_corners(data, body_id: int, half_length: float, half_width: float) -> list[np.ndarray]:
    center = data.xpos[body_id]
    rotation = data.xmat[body_id].reshape(3, 3)
    corners = []
    for x in (-half_length, half_length):
        for y in (-half_width, half_width):
            corners.append((center + rotation @ np.asarray([x, y, 0.0]))[:2])
    return corners


def _convex_hull(points: list[np.ndarray]) -> list[np.ndarray]:
    unique = sorted({(float(point[0]), float(point[1])) for point in points})
    if len(unique) <= 1:
        return [np.asarray(point) for point in unique]

    def cross(origin, a, b):
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return [np.asarray(point) for point in lower[:-1] + upper[:-1]]


def _inside_convex(point: np.ndarray, polygon: list[np.ndarray], tolerance: float = 1e-9) -> bool:
    if len(polygon) < 3:
        return False
    signs = []
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        edge = second - first
        offset = point - first
        signs.append(float(edge[0] * offset[1] - edge[1] * offset[0]))
    return all(value >= -tolerance for value in signs) or all(value <= tolerance for value in signs)


def _root_tilt_deg(quaternion_wxyz: np.ndarray) -> float:
    _, x, y, _ = (float(value) for value in quaternion_wxyz)
    up_z = 1.0 - 2.0 * (x * x + y * y)
    return math.degrees(math.acos(max(-1.0, min(1.0, up_z))))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", required=True)
    parser.add_argument("--sim-meta", required=True)
    parser.add_argument("--release-file", required=True)
    parser.add_argument("--interface", default="eth0")
    parser.add_argument("--foot-half-length-m", default=0.12, type=float)
    parser.add_argument("--foot-half-width-m", default=0.06, type=float)
    parser.add_argument("--support-margin-m", default=0.02, type=float)
    args = parser.parse_args()

    for output in (args.telemetry, args.sim_meta):
        Path(output).parent.mkdir(parents=True, exist_ok=True)

    config = SimLoopConfig(
        interface=args.interface,
        enable_onscreen=True,
        enable_offscreen=False,
    )
    values = config.load_wbc_yaml()
    values["ENV_NAME"] = config.env_name
    simulator = BaseSimulator(
        config=values,
        env_name=config.env_name,
        onscreen=True,
        offscreen=False,
        enable_image_publish=False,
    )
    env = simulator.sim_env
    if env.elastic_band is None:
        raise RuntimeError("stock simulator did not create the expected elastic band")
    release_file = Path(args.release_file)
    if release_file.exists():
        raise RuntimeError(f"release marker already exists: {release_file}")
    print("SHOWHAND_ELASTIC_BAND=startup_enabled")
    model = env.mj_model
    data = env.mj_data
    floor_geom = model.geom("floor").id
    left_body = model.body("left_ankle_roll_link").id
    right_body = model.body("right_ankle_roll_link").id

    fields = [
        "step_index",
        "monotonic_ns",
        "sim_time_s",
        "root_x_m",
        "root_y_m",
        "root_height_m",
        "root_qw",
        "root_qx",
        "root_qy",
        "root_qz",
        "root_tilt_deg",
        "com_x_m",
        "com_y_m",
        "com_z_m",
        "left_contact",
        "right_contact",
        "left_foot_slip_m_s",
        "right_foot_slip_m_s",
        "out_of_balance",
        "fall_event",
        *[f"q_{index}" for index in range(29)],
    ]
    handles = ExitStack()
    telemetry_handle = handles.enter_context(
        Path(args.telemetry).open("w", newline="", encoding="utf-8")  # noqa: SIM115
    )
    telemetry_writer = csv.DictWriter(telemetry_handle, fieldnames=fields)
    telemetry_writer.writeheader()
    old_check_fall = env.check_fall
    state = {
        "step": 0,
        "previous_left": None,
        "previous_right": None,
        "elastic_release_ns": None,
    }

    def record_then_check_fall() -> None:
        stamp = time.monotonic_ns()
        if state["elastic_release_ns"] is None and release_file.exists():
            env.elastic_band.enable = False
            state["elastic_release_ns"] = stamp
            print(f"SHOWHAND_ELASTIC_BAND=released monotonic_ns={stamp}")
        root = data.qpos[:7].copy()
        joints = data.qpos[env.body_joint_index + env.qpos_offset - 1].copy()
        com = data.subtree_com[env.root_body_id].copy()
        left_position = data.xpos[left_body].copy()
        right_position = data.xpos[right_body].copy()
        left_contact = _contact_state(model, data, floor_geom, left_body)
        right_contact = _contact_state(model, data, floor_geom, right_body)
        left_slip = 0.0
        right_slip = 0.0
        if left_contact and state["previous_left"] is not None:
            left_slip = float(
                np.linalg.norm((left_position - state["previous_left"])[:2]) / env.sim_dt
            )
        if right_contact and state["previous_right"] is not None:
            right_slip = float(
                np.linalg.norm((right_position - state["previous_right"])[:2]) / env.sim_dt
            )
        support = []
        half_length = args.foot_half_length_m + args.support_margin_m
        half_width = args.foot_half_width_m + args.support_margin_m
        if left_contact:
            support.extend(_foot_corners(data, left_body, half_length, half_width))
        if right_contact:
            support.extend(_foot_corners(data, right_body, half_length, half_width))
        out_of_balance = not _inside_convex(com[:2], _convex_hull(support))
        fall_event = bool(root[2] < 0.2)
        row = {
            "step_index": state["step"],
            "monotonic_ns": stamp,
            "sim_time_s": float(data.time),
            "root_x_m": float(root[0]),
            "root_y_m": float(root[1]),
            "root_height_m": float(root[2]),
            "root_qw": float(root[3]),
            "root_qx": float(root[4]),
            "root_qy": float(root[5]),
            "root_qz": float(root[6]),
            "root_tilt_deg": _root_tilt_deg(root[3:7]),
            "com_x_m": float(com[0]),
            "com_y_m": float(com[1]),
            "com_z_m": float(com[2]),
            "left_contact": int(left_contact),
            "right_contact": int(right_contact),
            "left_foot_slip_m_s": left_slip,
            "right_foot_slip_m_s": right_slip,
            "out_of_balance": int(out_of_balance),
            "fall_event": int(fall_event),
            **{f"q_{index}": float(value) for index, value in enumerate(joints)},
        }
        telemetry_writer.writerow(row)
        state["step"] += 1
        if fall_event:
            state["previous_left"] = None
            state["previous_right"] = None
        else:
            state["previous_left"] = left_position
            state["previous_right"] = right_position
        old_check_fall()

    env.check_fall = record_then_check_fall
    print("SHOWHAND_SIM_INSTRUMENTATION=active")
    try:
        simulator.start()
    finally:
        handles.close()
        metadata = {
            "schema_version": 1,
            "telemetry_steps": state["step"],
            "sim_frequency_hz": 1.0 / env.sim_dt,
            "offscreen_render_during_control": False,
            "elastic_band_startup_enabled": True,
            "elastic_band_release_monotonic_ns": state["elastic_release_ns"],
            "fall_condition": "root_height_m < 0.2 before stock reset",
            "balance_proxy": (
                "COM projection inside convex hull of oriented contact-foot rectangles"
            ),
        }
        Path(args.sim_meta).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
