#!/usr/bin/env python3
"""Run stock SONIC MuJoCo with a per-step physics trace."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import socket
import time
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", required=True)
    parser.add_argument("--sim-meta", required=True)
    parser.add_argument("--handshake-socket", required=True)
    parser.add_argument("--interface", default="eth0")
    parser.add_argument("--foot-half-length-m", default=0.12, type=float)
    parser.add_argument("--foot-half-width-m", default=0.06, type=float)
    parser.add_argument("--support-margin-m", default=0.02, type=float)
    args = parser.parse_args()

    for output in (args.telemetry, args.sim_meta):
        Path(output).parent.mkdir(parents=True, exist_ok=True)

    config = SimLoopConfig(
        interface=args.interface,
        enable_onscreen=False,
        enable_offscreen=False,
    )
    values = config.load_wbc_yaml()
    values["ENV_NAME"] = config.env_name
    simulator = BaseSimulator(
        config=values,
        env_name=config.env_name,
        onscreen=False,
        offscreen=False,
        enable_image_publish=False,
    )
    env = simulator.sim_env
    if env.elastic_band is None:
        raise RuntimeError("stock simulator did not create the expected elastic band")
    handshake_path = Path(args.handshake_socket)
    handshake_path.parent.mkdir(parents=True, exist_ok=True)
    handshake_path.unlink(missing_ok=True)
    handshake = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    handshake.bind(str(handshake_path))
    handshake.listen(1)
    handshake.setblocking(False)
    print(f"SHOWHAND_HANDSHAKE_READY={handshake_path}")
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
    telemetry_rows: list[dict[str, float | int]] = []
    old_check_fall = env.check_fall
    state = {
        "step": 0,
        "previous_left": None,
        "previous_right": None,
        "elastic_release_ns": None,
        "completion_connection": None,
        "completion_request_ns": None,
        "completion_status": None,
        "drain_deadline_ns": None,
        "expected_final_frame_index": None,
        "expected_output_frames": None,
        "replay_end_monotonic_ns": None,
        "post_roll_s": None,
        "run_id": None,
        "was_below_fall_height": False,
    }

    def record_then_check_fall() -> None:
        stamp = time.monotonic_ns()
        try:
            connection, _ = handshake.accept()
        except BlockingIOError:
            connection = None
        if connection is not None:
            try:
                with connection.makefile("r", encoding="utf-8") as request_stream:
                    line = request_stream.readline()
                if not line:
                    raise RuntimeError("empty simulator control request")
                request = json.loads(line)
                command = request.get("command")
                request_ns = time.monotonic_ns()
                if command == "release" and state["elastic_release_ns"] is None:
                    run_id = request.get("run_id")
                    if not isinstance(run_id, str) or not run_id:
                        raise RuntimeError("release request is missing run_id")
                    env.elastic_band.enable = False
                    state["elastic_release_ns"] = request_ns
                    state["run_id"] = run_id
                    acknowledgement = {
                        "run_id": run_id,
                        "release_monotonic_ns": request_ns,
                        "release_step_index": state["step"],
                        "release_sim_time_s": float(data.time),
                    }
                    connection.sendall((json.dumps(acknowledgement) + "\n").encode())
                    print(f"SHOWHAND_ELASTIC_BAND=released monotonic_ns={request_ns}")
                elif command in {"finish", "abort"} and state["elastic_release_ns"] is not None:
                    if request.get("run_id") != state["run_id"]:
                        raise RuntimeError("simulator control request run_id differs from release")
                    if state["completion_connection"] is not None:
                        raise RuntimeError("simulator already has a pending completion request")
                    if command == "finish":
                        output_frames = int(request["output_frames"])
                        final_frame_index = int(request["final_frame_index"])
                        replay_end_ns = int(request["replay_end_monotonic_ns"])
                        post_roll_s = float(request["post_roll_s"])
                        if output_frames <= 0 or final_frame_index != output_frames - 1:
                            raise RuntimeError("finish request has inconsistent frame count")
                        if replay_end_ns > request_ns:
                            raise RuntimeError("finish request predates replay end")
                        if not 0.1 <= post_roll_s <= 2.0:
                            raise RuntimeError(
                                "finish post-roll must be between 0.1 and 2.0 seconds"
                            )
                        state["completion_status"] = "completed"
                        state["expected_final_frame_index"] = final_frame_index
                        state["expected_output_frames"] = output_frames
                        state["replay_end_monotonic_ns"] = replay_end_ns
                        state["post_roll_s"] = post_roll_s
                        state["drain_deadline_ns"] = max(request_ns, replay_end_ns) + round(
                            post_roll_s * 1_000_000_000
                        )
                        print(
                            "SHOWHAND_REPLAY=draining "
                            f"final_frame_index={final_frame_index} post_roll_s={post_roll_s}"
                        )
                    else:
                        state["completion_status"] = "aborted"
                        state["drain_deadline_ns"] = request_ns
                        print("SHOWHAND_REPLAY=aborting")
                    state["completion_request_ns"] = request_ns
                    state["completion_connection"] = connection
                    connection = None
                else:
                    raise RuntimeError(f"invalid simulator control request: {request!r}")
            finally:
                if connection is not None:
                    connection.close()
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
            previous_position, previous_sim_time = state["previous_left"]
            elapsed_sim_s = float(data.time) - previous_sim_time
            if elapsed_sim_s <= 0:
                raise RuntimeError("non-positive simulator time delta for left foot slip")
            left_slip = float(
                np.linalg.norm((left_position - previous_position)[:2]) / elapsed_sim_s
            )
        if right_contact and state["previous_right"] is not None:
            previous_position, previous_sim_time = state["previous_right"]
            elapsed_sim_s = float(data.time) - previous_sim_time
            if elapsed_sim_s <= 0:
                raise RuntimeError("non-positive simulator time delta for right foot slip")
            right_slip = float(
                np.linalg.norm((right_position - previous_position)[:2]) / elapsed_sim_s
            )
        support = []
        half_length = args.foot_half_length_m + args.support_margin_m
        half_width = args.foot_half_width_m + args.support_margin_m
        if left_contact:
            support.extend(_foot_corners(data, left_body, half_length, half_width))
        if right_contact:
            support.extend(_foot_corners(data, right_body, half_length, half_width))
        out_of_balance = not _inside_convex(com[:2], _convex_hull(support))
        below_fall_height = bool(root[2] < 0.2)
        fall_event = below_fall_height and not state["was_below_fall_height"]
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
        telemetry_rows.append(row)
        state["step"] += 1
        state["previous_left"] = (
            (left_position, float(data.time)) if left_contact and not below_fall_height else None
        )
        state["previous_right"] = (
            (right_position, float(data.time)) if right_contact and not below_fall_height else None
        )
        state["was_below_fall_height"] = below_fall_height
        old_check_fall()
        if state["drain_deadline_ns"] is not None and stamp >= state["drain_deadline_ns"]:
            simulator._running = False

    env.check_fall = record_then_check_fall
    print("SHOWHAND_SIM_INSTRUMENTATION=active")
    try:
        simulator.start()
    finally:
        handshake.close()
        handshake_path.unlink(missing_ok=True)
        telemetry_path = Path(args.telemetry)
        telemetry_temp = telemetry_path.with_suffix(telemetry_path.suffix + ".tmp")
        with telemetry_temp.open("w", newline="", encoding="utf-8") as handle:
            telemetry_writer = csv.DictWriter(handle, fieldnames=fields)
            telemetry_writer.writeheader()
            telemetry_writer.writerows(telemetry_rows)
            handle.flush()
            os.fsync(handle.fileno())
        telemetry_temp.replace(telemetry_path)
        telemetry_sha256 = _sha256(telemetry_path)
        telemetry_bytes = telemetry_path.stat().st_size
        metadata_write_ns = time.monotonic_ns()
        metadata = {
            "schema_version": 1,
            "telemetry_steps": state["step"],
            "last_telemetry_monotonic_ns": (
                int(telemetry_rows[-1]["monotonic_ns"]) if telemetry_rows else None
            ),
            "sim_frequency_hz": 1.0 / env.sim_dt,
            "onscreen_viewer_during_control": False,
            "offscreen_render_during_control": False,
            "elastic_band_startup_enabled": True,
            "elastic_band_release_monotonic_ns": state["elastic_release_ns"],
            "completion_request_monotonic_ns": state["completion_request_ns"],
            "completion_status": state["completion_status"],
            "expected_final_frame_index": state["expected_final_frame_index"],
            "expected_output_frames": state["expected_output_frames"],
            "replay_end_monotonic_ns": state["replay_end_monotonic_ns"],
            "post_roll_s": state["post_roll_s"],
            "run_id": state["run_id"],
            "metadata_write_monotonic_ns": metadata_write_ns,
            "telemetry_sha256": telemetry_sha256,
            "telemetry_bytes": telemetry_bytes,
            "fall_condition": "transition into root_height_m < 0.2 before stock reset",
            "foot_slip_definition": (
                "horizontal contact-foot displacement divided by measured simulator time; "
                "both adjacent samples must be in contact"
            ),
            "balance_proxy": (
                "COM projection inside convex hull of oriented contact-foot rectangles"
            ),
        }
        metadata_path = Path(args.sim_meta)
        metadata_temp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        with metadata_temp.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(metadata, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        metadata_temp.replace(metadata_path)
        artifacts_flushed_ns = time.monotonic_ns()
        completion_connection = state["completion_connection"]
        if completion_connection is not None:
            acknowledgement = {
                "completion_status": state["completion_status"],
                "run_id": state["run_id"],
                "completion_request_monotonic_ns": state["completion_request_ns"],
                "artifacts_flushed_monotonic_ns": artifacts_flushed_ns,
                "telemetry_steps": state["step"],
                "last_telemetry_monotonic_ns": metadata["last_telemetry_monotonic_ns"],
                "expected_final_frame_index": state["expected_final_frame_index"],
                "expected_output_frames": state["expected_output_frames"],
                "telemetry_sha256": telemetry_sha256,
                "telemetry_bytes": telemetry_bytes,
            }
            try:
                completion_connection.sendall((json.dumps(acknowledgement) + "\n").encode())
            except BrokenPipeError as error:
                print(f"SHOWHAND_ACK_DELIVERY=failed error={type(error).__name__}: {error}")
            finally:
                completion_connection.close()
        print(f"SHOWHAND_ARTIFACTS_FLUSHED={artifacts_flushed_ns}")
        print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
