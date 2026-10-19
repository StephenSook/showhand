#!/usr/bin/env python3
"""Export a recorded SONIC run for the browser replay: per-frame world poses of every visual mesh.

The robot state is rebuilt from telemetry exactly as render_sim_telemetry.py does for render.mp4
(same simulator environment, same qpos layout, same 30 fps frame selection), so the browser shows
the same motion the recorded video shows. MuJoCo's own forward kinematics places every geom; the
browser only moves meshes.

Outputs, in --out:
  meshes.npz   compiled mesh vertices and faces in each geom's local frame, plus geom colors
  frames.bin   float32 [frame][geom][x, y, z, qw, qx, qy, qz]
  replay.json  geom list, frame times, and the run's identity
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from gear_sonic.utils.mujoco_sim.base_sim import BaseSimulator
from gear_sonic.utils.mujoco_sim.configs import SimLoopConfig

ROOT_FIELDS = ("root_x_m", "root_y_m", "root_height_m", "root_qw", "root_qx", "root_qy", "root_qz")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--replay-timing", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
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

    config = SimLoopConfig(interface="eth0", enable_onscreen=False, enable_offscreen=False)
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
    model = env.mj_model
    data = env.mj_data

    # Visual mesh geoms only, the ones the observer camera draws (collision geoms are group 3).
    geoms = [
        index
        for index in range(model.ngeom)
        if model.geom_type[index] == mujoco.mjtGeom.mjGEOM_MESH
        and model.geom_group[index] in (0, 1, 2)
        and model.geom_rgba[index][3] > 0
    ]
    if not geoms:
        raise RuntimeError("the model has no visual mesh geoms")

    mesh_arrays: dict[str, np.ndarray] = {}
    geom_meta = []
    for order, index in enumerate(geoms):
        mesh_id = int(model.geom_dataid[index])
        vert_start, vert_count = int(model.mesh_vertadr[mesh_id]), int(model.mesh_vertnum[mesh_id])
        face_start, face_count = int(model.mesh_faceadr[mesh_id]), int(model.mesh_facenum[mesh_id])
        mesh_arrays[f"v{order}"] = np.asarray(
            model.mesh_vert[vert_start : vert_start + vert_count], dtype=np.float32
        )
        mesh_arrays[f"f{order}"] = np.asarray(
            model.mesh_face[face_start : face_start + face_count], dtype=np.int32
        )
        body = int(model.geom_bodyid[index])
        geom_meta.append(
            {
                "order": order,
                "geom": index,
                "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index) or "",
                "body": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body) or "",
                "mesh": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, mesh_id) or "",
                "rgba": [round(float(value), 4) for value in model.geom_rgba[index]],
            }
        )

    first_ns = int(rows[0]["monotonic_ns"])
    last_ns = int(rows[-1]["monotonic_ns"])
    frame_count = round((last_ns - first_ns) / 1_000_000_000 * args.fps) + 1
    frames = np.zeros((frame_count, len(geoms), 7), dtype=np.float32)
    frame_times = []
    quat = np.zeros(4)
    row_index = 0
    for frame_index in range(frame_count):
        target_ns = first_ns + round(frame_index * 1_000_000_000 / args.fps)
        while row_index + 1 < len(rows) and int(rows[row_index + 1]["monotonic_ns"]) <= target_ns:
            row_index += 1
        row = rows[row_index]
        data.qpos[:7] = [float(row[name]) for name in ROOT_FIELDS]
        data.qpos[env.body_joint_index + env.qpos_offset - 1] = [
            float(row[f"q_{index}"]) for index in range(29)
        ]
        mujoco.mj_forward(model, data)
        for order, index in enumerate(geoms):
            mujoco.mju_mat2Quat(quat, data.geom_xmat[index])
            frames[frame_index, order, :3] = data.geom_xpos[index]
            frames[frame_index, order, 3:] = quat
        frame_times.append(
            {
                "frame": frame_index,
                "sim_time_s": float(row["sim_time_s"]),
                "out_of_balance": row.get("out_of_balance"),
                "fall_event": row.get("fall_event"),
            }
        )
    simulator.close()

    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "meshes.npz", **mesh_arrays)
    frames_path = args.out / "frames.bin"
    frames_path.write_bytes(frames.tobytes())
    replay = {
        "schema_version": 1,
        "fps": args.fps,
        "frames": frame_count,
        "geoms": geom_meta,
        "frame_layout": "float32 [frame][geom][x, y, z, qw, qx, qy, qz], MuJoCo world frame, z up",
        "frames_sha256": hashlib.sha256(frames_path.read_bytes()).hexdigest(),
        "telemetry_sha256": hashlib.sha256(args.telemetry.read_bytes()).hexdigest(),
        "selection": "previous telemetry row by monotonic timestamp, as render_sim_telemetry.py",
        "frame_times": frame_times,
    }
    (args.out / "replay.json").write_text(json.dumps(replay, indent=1) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"frames": frame_count, "geoms": len(geoms), "frames_bytes": frames_path.stat().st_size}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
