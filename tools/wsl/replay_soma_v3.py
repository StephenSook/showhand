#!/usr/bin/env python3
"""Replay saved GEM-X SOMA frames through stock SONIC Protocol v3 at 50 Hz."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pt", required=True)
    parser.add_argument("--source-fps", required=True, type=float)
    parser.add_argument("--output-fps", default=50.0, type=float)
    parser.add_argument("--smpl-output", required=True)
    parser.add_argument("--timing-output", required=True)
    parser.add_argument("--port", default=5556, type=int)
    args = parser.parse_args()
    if args.source_fps <= 0 or args.output_fps <= 0:
        raise SystemExit("source and output fps must be positive")

    gemx_root = Path("/home/stephensookra/showhand/GEM-X")
    sonic_root = Path("/home/stephensookra/showhand/GR00T-WholeBodyControl")
    sys.path.insert(0, str(gemx_root))
    bridge_dir = sonic_root / "gear_sonic/examples/live_camera_teleop"
    sys.path.insert(0, str(bridge_dir))

    from gem.utils.soma_utils.soma_layer import SomaLayer
    from soma_to_smpl import SomaToSmpl, SonicV3Publisher

    pred = torch.load(args.pt, weights_only=False)
    global_params = pred["body_params_global"]
    required = {"body_pose", "global_orient", "identity_coeffs", "scale_params"}
    missing = required.difference(global_params)
    if missing:
        raise KeyError(f"body_params_global missing {sorted(missing)}")
    source_frames = int(global_params["body_pose"].shape[0])
    source_duration_s = (source_frames - 1) / args.source_fps
    output_frames = round(source_duration_s * args.output_fps) + 1

    soma = SomaLayer(
        data_root=str(gemx_root / "inputs/soma_assets"),
        low_lod=True,
        device="cuda",
        identity_model_type="mhr",
        mode="warp",
    )
    converter = SomaToSmpl(
        soma,
        device="cuda",
        smooth=0.0,
        sonic_root=str(sonic_root),
    )
    conversion_started = time.perf_counter()
    converted_by_source: dict[int, dict[str, np.ndarray]] = {}
    for source_index in range(source_frames):
        frame = {key: global_params[key][source_index] for key in required}
        converted_by_source[source_index] = converter.convert(frame)
    conversion_wall_s = time.perf_counter() - conversion_started

    publisher = SonicV3Publisher(port=args.port, sonic_root=str(sonic_root))
    print(
        f"REPLAY_SOURCE_FRAMES={source_frames} SOURCE_FPS={args.source_fps} "
        f"OUTPUT_FRAMES={output_frames} OUTPUT_FPS={args.output_fps} "
        f"CONVERSION_WALL_S={conversion_wall_s:.6f}",
        flush=True,
    )
    input("REPLAY_READY press ENTER to start the 50 Hz clock\n")

    saved: dict[str, list[np.ndarray]] = {
        "smpl_joints": [],
        "body_quat": [],
        "smpl_pose": [],
        "wrists": [],
    }
    source_indices: list[int] = []
    start_ns = time.monotonic_ns()
    next_deadline = time.monotonic()
    try:
        for output_index in range(output_frames):
            source_index = min(
                int((output_index / args.output_fps) * args.source_fps),
                source_frames - 1,
            )
            converted = converted_by_source[source_index]
            publisher.publish(converted)
            for key in saved:
                saved[key].append(converted[key].copy())
            source_indices.append(source_index)
            next_deadline += 1.0 / args.output_fps
            sleep_s = next_deadline - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
    finally:
        end_ns = time.monotonic_ns()
        publisher.close()

    smpl_output = Path(args.smpl_output)
    smpl_output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        smpl_output,
        source_indices=np.asarray(source_indices, dtype=np.int32),
        **{key: np.concatenate(value, axis=0) for key, value in saved.items()},
    )
    timing = {
        "schema_version": 1,
        "source_pt": str(Path(args.pt).resolve()),
        "source_frames": source_frames,
        "source_fps": args.source_fps,
        "source_duration_s": source_duration_s,
        "output_frames": output_frames,
        "output_fps": args.output_fps,
        "conversion_wall_s": conversion_wall_s,
        "resampling": "zero_order_hold_by_source_timestamp",
        "replay_start_monotonic_ns": start_ns,
        "replay_end_monotonic_ns": end_ns,
        "wall_duration_s": (end_ns - start_ns) / 1_000_000_000,
    }
    timing_output = Path(args.timing_output)
    timing_output.parent.mkdir(parents=True, exist_ok=True)
    timing_output.write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(timing, sort_keys=True))


if __name__ == "__main__":
    main()
