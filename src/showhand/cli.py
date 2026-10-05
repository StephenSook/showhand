"""Command-line entry points for deterministic Showhand stages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
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
    metrics_parser.add_argument("--sonic-console", required=True)
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

    validate_parser = sub.add_parser("validate-replay")
    validate_parser.add_argument("--replay-timing", required=True)
    validate_parser.add_argument("--sim-meta", required=True)
    validate_parser.add_argument("--telemetry", required=True)
    validate_parser.add_argument("--sonic-console", required=True)

    args = parser.parse_args()
    if args.command == "metrics":
        thresholds = load_thresholds(args.thresholds)
        timing = _read_json(args.replay_timing)
        sim_meta = _read_json(args.sim_meta)
        replay_start_ns = int(timing["replay_start_monotonic_ns"])
        replay_end_ns = int(timing["replay_end_monotonic_ns"])
        evaluation_end_ns = int(timing["simulator_last_telemetry_monotonic_ns"])
        _validate_completion(timing, sim_meta, args.telemetry, args.sonic_console)
        target = load_retargeted_motion(args.retarget_csv, args.source_fps)
        telemetry = load_sim_telemetry(
            args.telemetry,
            replay_start_ns,
            evaluation_end_ns,
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
            "last_publish_monotonic_ns": replay_end_ns,
            "evaluation_end_monotonic_ns": evaluation_end_ns,
            "post_roll_s": float(timing["post_roll_s"]),
            "artifacts_flushed_monotonic_ns": int(timing["artifacts_flushed_monotonic_ns"]),
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
    elif args.command == "validate-replay":
        timing = _read_json(args.replay_timing)
        validate_saved_replay(
            timing,
            _read_json(args.sim_meta),
            args.telemetry,
            args.sonic_console,
        )
        print(
            "replay gates passed "
            f"run_id={timing['run_id']} "
            f"frames={timing['output_frames']} "
            f"jitter_max_s={float(timing['publish_jitter_max_s']):.6f}"
        )


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


FROZEN_MAX_PUBLISH_JITTER_S = 0.01
FROZEN_MAX_TELEMETRY_GAP_S = 0.05


def validate_saved_replay(
    timing: dict,
    sim_meta: dict,
    telemetry_path: str | Path,
    sonic_console_path: str | Path,
) -> None:
    """Re-check a finished replay without loosening the frozen gates."""
    _validate_completion(timing, sim_meta, telemetry_path, sonic_console_path)
    try:
        allowed = float(timing["max_allowed_jitter_s"])
        observed = float(timing["publish_jitter_max_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("replay timing is missing publish jitter") from error
    if allowed <= 0 or allowed > FROZEN_MAX_PUBLISH_JITTER_S:
        raise ValueError(
            f"replay jitter limit {allowed:.6f}s is outside the frozen "
            f"{FROZEN_MAX_PUBLISH_JITTER_S:.6f}s gate"
        )
    if observed > allowed:
        raise ValueError(f"publish jitter {observed:.6f}s exceeds {allowed:.6f}s")
    release = sim_meta.get("elastic_band_release_monotonic_ns")
    if release is None:
        raise ValueError("simulator metadata is missing support release time")
    load_sim_telemetry(
        telemetry_path,
        int(timing["replay_start_monotonic_ns"]),
        int(timing["simulator_last_telemetry_monotonic_ns"]),
        int(release),
        max_gap_s=FROZEN_MAX_TELEMETRY_GAP_S,
    )


def _validate_completion(
    timing: dict, sim_meta: dict, telemetry_path: str | Path, sonic_console_path: str | Path
) -> None:
    replay_end_ns = int(timing["replay_end_monotonic_ns"])
    completion_request_ns = int(timing["completion_request_monotonic_ns"])
    if timing["completion_status"] != "completed" or sim_meta["completion_status"] != "completed":
        raise ValueError("simulator completion status is not completed")
    run_id = timing.get("run_id")
    if not isinstance(run_id, str) or not run_id or sim_meta.get("run_id") != run_id:
        raise ValueError("simulator run_id differs from replay timing")
    if completion_request_ns != int(sim_meta["completion_request_monotonic_ns"]):
        raise ValueError("simulator completion request provenance differs")
    if completion_request_ns < replay_end_ns:
        raise ValueError("simulator completion request predates replay end")
    if replay_end_ns != int(sim_meta["replay_end_monotonic_ns"]):
        raise ValueError("simulator replay end differs from replay timing")
    if int(timing["expected_final_frame_index"]) != int(timing["output_frames"]) - 1:
        raise ValueError("completion final frame index differs from replay output")
    if int(sim_meta["expected_final_frame_index"]) != int(timing["expected_final_frame_index"]):
        raise ValueError("simulator final frame index differs from replay output")
    if int(sim_meta["expected_output_frames"]) != int(timing["output_frames"]):
        raise ValueError("simulator expected frame count differs from replay output")
    if int(timing["simulator_telemetry_steps"]) != int(sim_meta["telemetry_steps"]):
        raise ValueError("simulator telemetry step count differs from metadata")
    telemetry_path = Path(telemetry_path)
    telemetry_sha256 = _sha256(telemetry_path)
    if telemetry_sha256 != timing["simulator_telemetry_sha256"]:
        raise ValueError("telemetry bytes differ from replay acknowledgement")
    if telemetry_sha256 != sim_meta["telemetry_sha256"]:
        raise ValueError("telemetry bytes differ from simulator metadata")
    telemetry_bytes = telemetry_path.stat().st_size
    if telemetry_bytes != int(timing["simulator_telemetry_bytes"]):
        raise ValueError("telemetry byte count differs from replay acknowledgement")
    if telemetry_bytes != int(sim_meta["telemetry_bytes"]):
        raise ValueError("telemetry byte count differs from simulator metadata")
    telemetry_rows = 0
    final_telemetry_ns = None
    with telemetry_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            telemetry_rows += 1
            final_telemetry_ns = int(row["monotonic_ns"])
    if telemetry_rows != int(sim_meta["telemetry_steps"]):
        raise ValueError("telemetry row count differs from simulator metadata")
    last_telemetry_ns = int(timing["simulator_last_telemetry_monotonic_ns"])
    if last_telemetry_ns != int(sim_meta["last_telemetry_monotonic_ns"]):
        raise ValueError("simulator final telemetry timestamp differs from metadata")
    if final_telemetry_ns != last_telemetry_ns:
        raise ValueError("telemetry final row timestamp differs from completion evidence")
    post_roll_s = float(timing["post_roll_s"])
    if post_roll_s != float(sim_meta["post_roll_s"]):
        raise ValueError("simulator post-roll differs from replay timing")
    required_drain_end_ns = max(replay_end_ns, completion_request_ns) + round(
        post_roll_s * 1_000_000_000
    )
    if last_telemetry_ns < required_drain_end_ns:
        raise ValueError("simulator telemetry does not cover the required controller drain")
    if int(timing["artifacts_flushed_monotonic_ns"]) <= last_telemetry_ns:
        raise ValueError("simulator acknowledged completion before artifacts were flushed")
    _validate_controller_receipt(
        sonic_console_path,
        output_frames=int(timing["output_frames"]),
        run_id=run_id,
    )


def _validate_controller_receipt(path: str | Path, *, output_frames: int, run_id: str) -> None:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    begin_marker = f"SHOWHAND_RUN_BEGIN={run_id}\n"
    end_marker = f"SHOWHAND_RUN_END={run_id} exit=0\n"
    if text.count(begin_marker) != 1 or text.count(end_marker) != 1:
        raise ValueError("SONIC log does not contain one successful run boundary")
    begin = text.index(begin_marker) + len(begin_marker)
    end = text.index(end_marker)
    if begin >= end:
        raise ValueError("SONIC log run boundaries are out of order")
    invocation = text[begin:end]
    received = [
        int(match)
        for match in re.findall(
            r"Protocol v3: Received SMPL action \(single\) - frame_index: (\d+)", invocation
        )
    ]
    expected = list(range(output_frames))
    if received != expected:
        first_difference = next(
            (
                index
                for index, pair in enumerate(zip(received, expected, strict=False))
                if pair[0] != pair[1]
            ),
            min(len(received), len(expected)),
        )
        raise ValueError(
            "SONIC controller receipt is incomplete or out of order: "
            f"received {len(received)} of {output_frames} frames; "
            f"first difference at position {first_difference}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: str, payload: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
