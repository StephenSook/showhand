#!/usr/bin/env python3
"""Extract synchronized human and robot frames for one-second visual windows."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human", required=True)
    parser.add_argument("--robot", required=True)
    parser.add_argument("--render-timestamps", required=True)
    parser.add_argument("--replay-timing", required=True)
    parser.add_argument("--duration", required=True, type=float)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    timing = json.loads(Path(args.replay_timing).read_text(encoding="utf-8"))
    replay_start_ns = int(timing["replay_start_monotonic_ns"])
    with Path(args.render_timestamps).open(newline="", encoding="utf-8") as handle:
        render_rows = list(csv.DictReader(handle))
    if not render_rows:
        raise RuntimeError("render timestamp CSV contains no frames")
    render_times = [int(row["monotonic_ns"]) for row in render_rows]
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    window_count = int(args.duration) + (1 if args.duration % 1 else 0)
    for index in range(window_count):
        start_s = float(index)
        end_s = min(float(index + 1), args.duration)
        center_s = (start_s + end_s) / 2
        target_stamp = replay_start_ns + int(center_s * 1_000_000_000)
        frame_index = min(
            range(len(render_times)), key=lambda item: abs(render_times[item] - target_stamp)
        )
        robot_s = frame_index / 30.0
        destination = output / f"window-{index:03d}.jpg"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{center_s:.6f}",
            "-i",
            args.human,
            "-ss",
            f"{robot_s:.6f}",
            "-i",
            args.robot,
            "-filter_complex",
            "[0:v]scale=640:-2,setsar=1[h];[1:v]scale=640:-2,setsar=1[r];[h][r]hstack=inputs=2",
            "-frames:v",
            "1",
            str(destination),
        ]
        subprocess.run(command, check=True)
        manifest.append(
            {
                "window_index": index,
                "start_s": start_s,
                "end_s": end_s,
                "center_s": center_s,
                "robot_frame_index": frame_index,
                "robot_video_s": robot_s,
                "pair_path": destination.name,
            }
        )
    (output / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "windows": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
