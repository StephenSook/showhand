#!/usr/bin/env python3
"""Run NVIDIA's stock SOMA-to-G1 retargeter on a saved GEM-X result."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from scripts.demo.retarget_utils import run_retarget


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hpe-results", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--timing-json", type=Path, required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    prediction = torch.load(args.hpe_results, map_location="cpu", weights_only=False)
    body_params = prediction["body_params_global"]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    run_retarget(body_params, args.fps, str(args.output_csv))
    wall_s = time.perf_counter() - started

    timing = {
        "stage": "nvidia_soma_retargeter_recovery",
        "input": str(args.hpe_results.resolve()),
        "output": str(args.output_csv.resolve()),
        "frames": int(body_params["body_pose"].shape[0]),
        "source_fps": args.fps,
        "wall_s": wall_s,
    }
    args.timing_json.write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(timing, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
