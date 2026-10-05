#!/usr/bin/env python3
"""Replay saved GEM-X SOMA frames through stock SONIC Protocol v3 at 50 Hz."""

from __future__ import annotations

import argparse
import json
import socket
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
    parser.add_argument("--handshake-socket", required=True)
    parser.add_argument("--handshake-timeout-s", default=5.0, type=float)
    parser.add_argument("--max-jitter-s", default=0.01, type=float)
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
    acknowledgement = _handshake(args.handshake_socket, b"release\n", args.handshake_timeout_s)
    release_ns = int(acknowledgement["release_monotonic_ns"])

    saved: dict[str, list[np.ndarray]] = {
        "smpl_joints": [],
        "body_quat": [],
        "smpl_pose": [],
        "wrists": [],
    }
    source_indices: list[int] = []
    publish_monotonic_ns: list[int] = []
    publish_jitter_s: list[float] = []
    start_ns = time.monotonic_ns()
    start_clock = start_ns / 1_000_000_000
    try:
        for output_index in range(output_frames):
            deadline = start_clock + output_index / args.output_fps
            sleep_s = deadline - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
            publish_ns = time.monotonic_ns()
            jitter_s = publish_ns / 1_000_000_000 - deadline
            if jitter_s > args.max_jitter_s:
                raise RuntimeError(
                    f"50 Hz publish jitter {jitter_s:.6f}s exceeds {args.max_jitter_s:.6f}s "
                    f"at frame {output_index}"
                )
            source_index = min(
                int((output_index / args.output_fps) * args.source_fps),
                source_frames - 1,
            )
            converted = converted_by_source[source_index]
            publisher.publish(converted)
            for key in saved:
                saved[key].append(converted[key].copy())
            source_indices.append(source_index)
            publish_monotonic_ns.append(publish_ns)
            publish_jitter_s.append(jitter_s)
    finally:
        end_ns = time.monotonic_ns()
        publisher.close()
        finish_acknowledgement = _handshake(
            args.handshake_socket, b"finish\n", args.handshake_timeout_s
        )

    smpl_output = Path(args.smpl_output)
    smpl_output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        smpl_output,
        source_indices=np.asarray(source_indices, dtype=np.int32),
        publish_monotonic_ns=np.asarray(publish_monotonic_ns, dtype=np.int64),
        publish_jitter_s=np.asarray(publish_jitter_s, dtype=np.float64),
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
        "elastic_band_release_monotonic_ns": release_ns,
        "release_to_replay_start_s": (start_ns - release_ns) / 1_000_000_000,
        "resampling": "zero_order_hold_by_source_timestamp",
        "replay_start_monotonic_ns": start_ns,
        "replay_end_monotonic_ns": end_ns,
        "simulator_finish_monotonic_ns": int(finish_acknowledgement["finish_monotonic_ns"]),
        "simulator_finish_step_index": int(finish_acknowledgement["finish_step_index"]),
        "wall_duration_s": (end_ns - start_ns) / 1_000_000_000,
        "publish_jitter_max_s": max(publish_jitter_s, default=0.0),
        "publish_jitter_p95_s": float(np.percentile(publish_jitter_s, 95)),
        "deadline_misses": sum(jitter > 1.0 / args.output_fps for jitter in publish_jitter_s),
        "max_allowed_jitter_s": args.max_jitter_s,
    }
    timing_output = Path(args.timing_output)
    timing_output.parent.mkdir(parents=True, exist_ok=True)
    timing_output.write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(timing, sort_keys=True))


def _handshake(socket_path: str, request: bytes, timeout_s: float) -> dict:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(timeout_s)
    try:
        connection.connect(socket_path)
        connection.sendall(request)
        with connection.makefile("r", encoding="utf-8") as response:
            line = response.readline()
        if not line:
            raise RuntimeError(f"simulator returned no acknowledgement for {request!r}")
        return json.loads(line)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
