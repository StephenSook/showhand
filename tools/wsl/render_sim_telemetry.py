#!/usr/bin/env python3
"""Render a recorded SONIC MuJoCo trajectory without slowing the control loop."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import mujoco
import numpy as np
from gear_sonic.utils.mujoco_sim.base_sim import BaseSimulator
from gear_sonic.utils.mujoco_sim.configs import SimLoopConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--replay-timing", type=Path, required=True)
    parser.add_argument("--render", type=Path, required=True)
    parser.add_argument("--render-timestamps", type=Path, required=True)
    parser.add_argument("--render-meta", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()

    timing = json.loads(args.replay_timing.read_text(encoding="utf-8"))
    start_ns = int(timing["replay_start_monotonic_ns"])
    end_ns = int(timing["replay_end_monotonic_ns"])
    with args.telemetry.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle) if start_ns <= int(row["monotonic_ns"]) <= end_ns
        ]
    if not rows:
        raise RuntimeError("no telemetry rows overlap the replay timing window")

    config = SimLoopConfig(interface="eth0", enable_onscreen=False, enable_offscreen=True)
    values = config.load_wbc_yaml()
    values["ENV_NAME"] = config.env_name
    simulator = BaseSimulator(
        config=values,
        env_name=config.env_name,
        onscreen=False,
        offscreen=True,
        enable_image_publish=False,
        camera_configs={"observer": {"height": 480, "width": 640}},
    )
    env = simulator.sim_env
    model = env.mj_model
    data = env.mj_data
    renderer = env.renderers["observer"]
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
    camera.trackbodyid = env.root_body_id
    camera.azimuth = 120
    camera.elevation = -20
    camera.distance = 2.5
    camera.lookat[:] = np.asarray([0.0, 0.0, 0.6])

    args.render.parent.mkdir(parents=True, exist_ok=True)
    args.render_timestamps.parent.mkdir(parents=True, exist_ok=True)
    args.render_meta.parent.mkdir(parents=True, exist_ok=True)
    video = cv2.VideoWriter(str(args.render), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (640, 480))
    if not video.isOpened():
        raise RuntimeError("OpenCV could not open the observer MP4 writer")

    first_ns = int(rows[0]["monotonic_ns"])
    last_ns = int(rows[-1]["monotonic_ns"])
    frame_count = round((last_ns - first_ns) / 1_000_000_000 * args.fps) + 1
    row_index = 0
    started = time.perf_counter()
    with args.render_timestamps.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame_index", "monotonic_ns", "sim_time_s"])
        writer.writeheader()
        for frame_index in range(frame_count):
            target_ns = first_ns + round(frame_index * 1_000_000_000 / args.fps)
            while (
                row_index + 1 < len(rows) and int(rows[row_index + 1]["monotonic_ns"]) <= target_ns
            ):
                row_index += 1
            row = rows[row_index]
            data.qpos[:7] = [
                float(row[name])
                for name in (
                    "root_x_m",
                    "root_y_m",
                    "root_height_m",
                    "root_qw",
                    "root_qx",
                    "root_qy",
                    "root_qz",
                )
            ]
            data.qpos[env.body_joint_index + env.qpos_offset - 1] = [
                float(row[f"q_{index}"]) for index in range(29)
            ]
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera=camera)
            frame = renderer.render()
            video.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            writer.writerow(
                {
                    "frame_index": frame_index,
                    "monotonic_ns": row["monotonic_ns"],
                    "sim_time_s": row["sim_time_s"],
                }
            )
    video.release()
    simulator.close()
    wall_s = time.perf_counter() - started
    metadata = {
        "schema_version": 1,
        "source_telemetry": str(args.telemetry.resolve()),
        "source_replay_timing": str(args.replay_timing.resolve()),
        "render_fps": args.fps,
        "frames": frame_count,
        "width": 640,
        "height": 480,
        "selection": "previous telemetry row by monotonic timestamp",
        "wall_s": wall_s,
    }
    args.render_meta.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
