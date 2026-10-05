"""Command-line entry points for deterministic Showhand stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from showhand.fusion import request_fusion
from showhand.metrics import compute_take_metrics, load_retargeted_motion, load_sim_telemetry
from showhand.records import write_take_record
from showhand.residual import load_rows, paired_agreement_residual
from showhand.thresholds import load_thresholds, threshold_sha256
from showhand.visual import load_visual_results


def main() -> None:
    parser = argparse.ArgumentParser(prog="showhand")
    sub = parser.add_subparsers(dest="command", required=True)

    metrics_parser = sub.add_parser("metrics")
    metrics_parser.add_argument("--retarget-csv", required=True)
    metrics_parser.add_argument("--source-fps", required=True, type=float)
    metrics_parser.add_argument("--telemetry", required=True)
    metrics_parser.add_argument("--replay-timing", required=True)
    metrics_parser.add_argument("--sim-meta", required=True)
    metrics_parser.add_argument("--thresholds", default="config/thresholds.yaml")
    metrics_parser.add_argument("--out", required=True)

    fusion_parser = sub.add_parser("fusion")
    fusion_parser.add_argument("--metrics", required=True)
    fusion_parser.add_argument("--visual", required=True)
    fusion_parser.add_argument("--out", required=True)

    residual_parser = sub.add_parser("residual")
    residual_parser.add_argument("--labels", required=True)
    residual_parser.add_argument("--replicates", type=int, default=10_000)
    residual_parser.add_argument("--seed", type=int, default=20_261_005)
    residual_parser.add_argument("--label-source", choices=("human", "synthetic"), required=True)
    residual_parser.add_argument("--out", required=True)

    record_parser = sub.add_parser("write-record")
    record_parser.add_argument("--input", required=True)
    record_parser.add_argument("--out", required=True)

    args = parser.parse_args()
    if args.command == "metrics":
        thresholds = load_thresholds(args.thresholds)
        timing = _read_json(args.replay_timing)
        sim_meta = _read_json(args.sim_meta)
        replay_start_ns = int(timing["replay_start_monotonic_ns"])
        replay_end_ns = int(timing["replay_end_monotonic_ns"])
        finish_ns = int(timing["simulator_finish_monotonic_ns"])
        if finish_ns < replay_end_ns:
            raise ValueError("simulator finish acknowledgement predates replay completion")
        if int(sim_meta["replay_finish_request_monotonic_ns"]) != finish_ns:
            raise ValueError("simulator finish provenance differs between timing and metadata")
        if not sim_meta["self_terminated_after_finish_request"]:
            raise ValueError("simulator did not self-terminate after the replay finish request")
        target = load_retargeted_motion(args.retarget_csv, args.source_fps)
        telemetry = load_sim_telemetry(
            args.telemetry,
            replay_start_ns,
            replay_end_ns,
            int(sim_meta["elastic_band_release_monotonic_ns"]),
        )
        result = compute_take_metrics(target, telemetry, replay_start_ns, thresholds)
        result["threshold_sha256"] = threshold_sha256(args.thresholds)
        result["timeline"] = {
            "interpretation": (
                "target publish wall time compared with measured simulator state wall time; "
                "SONIC transport and controller latency remain inside tracking error"
            ),
            "release_before_replay": True,
            "replay_start_monotonic_ns": replay_start_ns,
            "replay_end_monotonic_ns": replay_end_ns,
            "elastic_band_release_monotonic_ns": int(sim_meta["elastic_band_release_monotonic_ns"]),
        }
        _write_json(args.out, result)
    elif args.command == "fusion":
        metrics = _read_json(args.metrics)
        visual = load_visual_results(args.visual)
        _write_json(args.out, request_fusion(metrics, visual))
    elif args.command == "residual":
        result = paired_agreement_residual(
            load_rows(args.labels),
            replicates=args.replicates,
            seed=args.seed,
            label_source=args.label_source,
        )
        _write_json(args.out, result)
    elif args.command == "write-record":
        write_take_record(args.out, _read_json(args.input))


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str, payload: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
