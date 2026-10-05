#!/usr/bin/env python3
"""Build a take-record input by copying measured artifact fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

FROZEN_THRESHOLD_COMMIT = "0c3a5cebddfa1b8fcac32b5ac2f64d1f2c9675f9"
FROZEN_THRESHOLD_SHA256 = "206c194a8863e9a7aa2ac2c9bb88edff10271aad224d34194fad215fe2076b76"
LABEL = "Stephen's take"
METRIC_FIELDS = (
    "tracking_mean_abs_error_rad",
    "tracking_p95_abs_error_rad",
    "root_height_min_m",
    "root_tilt_max_deg",
    "foot_slip_max_m_s",
    "foot_slip_seconds",
    "out_of_balance_seconds",
    "falls",
    "pass",
    "reason_codes",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--take-id", required=True)
    parser.add_argument("--source-path", type=Path, required=True)
    parser.add_argument("--original-wsl-path", required=True)
    parser.add_argument("--replay-timing", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--sim-meta", type=Path, required=True)
    parser.add_argument("--sonic-console", type=Path, required=True)
    parser.add_argument("--sonic-logs", type=Path, required=True)
    parser.add_argument("--smpl-sequence", type=Path, required=True)
    parser.add_argument("--render", type=Path, required=True)
    parser.add_argument("--render-timestamps", type=Path, required=True)
    parser.add_argument("--render-meta", type=Path, required=True)
    parser.add_argument("--retarget-csv", type=Path, required=True)
    parser.add_argument("--hpe-results", type=Path, required=True)
    parser.add_argument("--stage-timings", type=Path, required=True)
    parser.add_argument("--sim-final-state", required=True)
    parser.add_argument("--sonic-final-state", required=True)
    parser.add_argument("--container-duration-s", type=float)
    parser.add_argument("--container-frames", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    args = parser.parse_args()
    if args.take_id.lower().startswith("pexels"):
        raise SystemExit("refusing to label a Pexels clip as Stephen's take")

    repo = args.repo.resolve()
    timing = _read_json(args.replay_timing)
    metrics = _read_json(args.metrics)
    stage_timings = _read_json(args.stage_timings)
    overall = metrics.get("overall")
    if not isinstance(overall, dict):
        raise SystemExit("metrics artifact has no overall object")
    copied_metrics = {key: overall[key] for key in METRIC_FIELDS}
    copied_metrics["retargeter"] = metrics["retargeter"]
    stage_timings["soma_to_smpl_precompute_s"] = timing["conversion_wall_s"]
    stage_timings["sonic_replay_50_hz_s"] = timing["wall_duration_s"]
    if any(float(value) < 0 for value in stage_timings.values()):
        raise SystemExit("stage timings cannot be negative")

    threshold_path = repo / "config" / "thresholds.yaml"
    threshold_sha256 = _sha256(threshold_path)
    threshold_commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-list", "-1", "HEAD", "--", "config/thresholds.yaml"],
        text=True,
    ).strip()
    if threshold_commit != FROZEN_THRESHOLD_COMMIT or threshold_sha256 != FROZEN_THRESHOLD_SHA256:
        raise SystemExit("frozen threshold commit or bytes differ from the registered values")
    if metrics.get("threshold_sha256") != threshold_sha256:
        raise SystemExit("metrics artifact threshold hash differs from the frozen file")

    source = {
        "path": _relative(repo, args.source_path),
        "sha256": _sha256(args.source_path),
        "frames": timing["source_frames"],
        "fps": timing["source_fps"],
        "pose_duration_s": timing["source_duration_s"],
        "original_wsl_path": args.original_wsl_path,
    }
    if args.container_duration_s is not None:
        source["container_duration_s"] = args.container_duration_s
    if args.container_frames is not None:
        source["container_frames"] = args.container_frames
    if args.width is not None:
        source["width"] = args.width
    if args.height is not None:
        source["height"] = args.height

    record = {
        "schema_version": 1,
        "take_id": args.take_id,
        "label": LABEL,
        "threshold_commit_sha": threshold_commit,
        "threshold_path": "config/thresholds.yaml",
        "threshold_sha256": threshold_sha256,
        "code_commit_sha": timing["code_commit_sha"],
        "code_tree_clean": timing["code_tree_clean"],
        "source": source,
        "artifacts": {
            "sim_step_telemetry": _relative(repo, args.telemetry),
            "sim_metadata": _relative(repo, args.sim_meta),
            "replay_timing": _relative(repo, args.replay_timing),
            "sonic_console": _relative(repo, args.sonic_console),
            "metrics": _relative(repo, args.metrics),
            "sim_render": _relative(repo, args.render),
            "render_timestamps": _relative(repo, args.render_timestamps),
            "render_meta": _relative(repo, args.render_meta),
            "sonic_input_sequence": _relative(repo, args.smpl_sequence),
            "sonic_csv_logs": _relative(repo, args.sonic_logs),
            "retarget_csv": _relative(repo, args.retarget_csv),
            "hpe_results": _relative(repo, args.hpe_results),
            "visual_output": None,
        },
        "timings_s": stage_timings,
        "metrics": copied_metrics,
        "replay_validation": {
            "run_id": timing["run_id"],
            "publisher_warmup_s": timing["publisher_warmup_s"],
            "max_allowed_jitter_s": timing["max_allowed_jitter_s"],
            "publish_jitter_max_s": timing["publish_jitter_max_s"],
            "publish_jitter_p95_s": timing["publish_jitter_p95_s"],
            "sonic_received_frames": timing["output_frames"],
            "sonic_first_frame": 0,
            "sonic_final_frame": timing["expected_final_frame_index"],
            "telemetry_steps": timing["simulator_telemetry_steps"],
            "telemetry_bytes": timing["simulator_telemetry_bytes"],
            "telemetry_sha256": timing["simulator_telemetry_sha256"],
            "replay_timing_sha256": _sha256(args.replay_timing),
            "post_roll_evaluated_s": metrics["post_roll_evaluated_s"],
        },
        "visual_judge": {
            "status": "blocked_before_job_create",
            "job": {},
            "model_id": "nvidia/Cosmos-Reason1-7B",
        },
        "fusion": {
            "status": "not_run_missing_visual_verdicts",
            "model_id": "nvidia/Nemotron-3_5-Lightning",
        },
        "cost_usd": {"nebius_gpu": 0.0, "token_factory": 0.0, "total": 0.0},
        "cleanup": {
            "gpu_hours_used": 0.0,
            "nebius_endpoints_started": 0,
            "nebius_jobs_started": 0,
            "sim_process_final_state": args.sim_final_state,
            "sonic_process_final_state": args.sonic_final_state,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path} is not a JSON object")
    return value


def _relative(repo: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repo)
    except ValueError as error:
        raise SystemExit(f"{path} is outside the repository") from error
    text = relative.as_posix()
    if text.startswith("../") or text == ".." or Path(text).is_absolute():
        raise SystemExit(f"refusing non-relative artifact path: {text}")
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
