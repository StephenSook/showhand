#!/usr/bin/env python3
"""Replay saved GEM-X SOMA frames through stock SONIC Protocol v3 at 50 Hz."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import time
from pathlib import Path

import numpy as np
import torch


def wait_until(deadline_s: float, spin_margin_s: float = 0.003) -> None:
    """Sleep most of an interval, then use a bounded spin for the final margin."""
    remaining_s = deadline_s - time.monotonic()
    if remaining_s > spin_margin_s:
        time.sleep(remaining_s - spin_margin_s)
    while time.monotonic() < deadline_s:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pt", required=True)
    parser.add_argument("--source-fps", required=True, type=float)
    parser.add_argument("--output-fps", default=50.0, type=float)
    parser.add_argument("--smpl-output", required=True)
    parser.add_argument("--timing-output", required=True)
    parser.add_argument("--handshake-socket", required=True)
    parser.add_argument("--handshake-timeout-s", default=5.0, type=float)
    parser.add_argument("--completion-timeout-s", default=30.0, type=float)
    parser.add_argument("--max-jitter-s", default=0.01, type=float)
    parser.add_argument("--post-roll-s", default=0.6, type=float)
    parser.add_argument("--publisher-warmup-s", default=0.5, type=float)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--port", default=5556, type=int)
    args = parser.parse_args()
    if args.source_fps <= 0 or args.output_fps <= 0:
        raise SystemExit("source and output fps must be positive")
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", args.run_id) is None:
        raise SystemExit(
            "run id must use 1-128 ASCII letters, digits, dots, underscores, or hyphens"
        )

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
    if args.publisher_warmup_s < 0:
        raise SystemExit("publisher warmup must be non-negative")
    time.sleep(args.publisher_warmup_s)
    print(
        f"REPLAY_SOURCE_FRAMES={source_frames} SOURCE_FPS={args.source_fps} "
        f"OUTPUT_FRAMES={output_frames} OUTPUT_FPS={args.output_fps} "
        f"CONVERSION_WALL_S={conversion_wall_s:.6f}",
        flush=True,
    )
    acknowledgement = _exchange(
        args.handshake_socket,
        {"command": "release", "run_id": args.run_id},
        args.handshake_timeout_s,
    )
    if acknowledgement.get("run_id") != args.run_id:
        raise RuntimeError("simulator release acknowledgement run_id differs")
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
            wait_until(deadline)
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
    except BaseException as error:
        publisher.close()
        try:
            _exchange(
                args.handshake_socket,
                {
                    "command": "abort",
                    "run_id": args.run_id,
                    "error_type": type(error).__name__,
                    "published_frames": len(publish_monotonic_ns),
                },
                args.completion_timeout_s,
            )
        except Exception as cleanup_error:
            error.add_note(f"simulator abort also failed: {cleanup_error}")
        raise
    else:
        publisher.close()
    end_ns = publish_monotonic_ns[-1]
    completion = _exchange(
        args.handshake_socket,
        {
            "command": "finish",
            "run_id": args.run_id,
            "output_frames": output_frames,
            "final_frame_index": output_frames - 1,
            "replay_end_monotonic_ns": end_ns,
            "post_roll_s": args.post_roll_s,
        },
        args.completion_timeout_s,
    )
    if completion.get("completion_status") != "completed":
        raise RuntimeError(
            f"simulator returned completion status {completion.get('completion_status')!r}"
        )
    if completion.get("run_id") != args.run_id:
        raise RuntimeError("simulator completion acknowledgement run_id differs")

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
        "run_id": args.run_id,
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
        "completion_status": completion["completion_status"],
        "completion_request_monotonic_ns": int(completion["completion_request_monotonic_ns"]),
        "artifacts_flushed_monotonic_ns": int(completion["artifacts_flushed_monotonic_ns"]),
        "simulator_last_telemetry_monotonic_ns": int(completion["last_telemetry_monotonic_ns"]),
        "simulator_telemetry_steps": int(completion["telemetry_steps"]),
        "simulator_telemetry_sha256": str(completion["telemetry_sha256"]),
        "simulator_telemetry_bytes": int(completion["telemetry_bytes"]),
        "expected_final_frame_index": int(completion["expected_final_frame_index"]),
        "post_roll_s": args.post_roll_s,
        "publisher_warmup_s": args.publisher_warmup_s,
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


def _exchange(socket_path: str, request: dict, timeout_s: float) -> dict:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(timeout_s)
    try:
        connection.connect(socket_path)
        connection.sendall((json.dumps(request) + "\n").encode())
        with connection.makefile("r", encoding="utf-8") as response:
            line = response.readline()
        if not line:
            raise RuntimeError(f"simulator returned no acknowledgement for {request!r}")
        return json.loads(line)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
