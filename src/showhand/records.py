"""Take-record construction with explicit artifact and timing provenance."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from showhand.metrics import metric_reason_codes
from showhand.thresholds import parse_thresholds

REQUIRED_FILE_ARTIFACTS = (
    "sim_step_telemetry",
    "sim_metadata",
    "replay_timing",
    "sonic_console",
    "metrics",
)

ALLOWED_TAKE_LABELS = frozenset({"PLUMBING TEST", "Stephen's take"})


def write_take_record(path: str | Path, record: dict[str, Any]) -> None:
    materialized = deepcopy(record)
    replay_timing_path = materialized.get("artifacts", {}).get("replay_timing")
    if not replay_timing_path or not Path(replay_timing_path).is_file():
        raise ValueError("replay_timing artifact is required before writing a take record")
    replay_timing = json.loads(Path(replay_timing_path).read_text(encoding="utf-8"))
    _reject_identity_mismatch(materialized, replay_timing)
    materialized["code_commit_sha"] = replay_timing["code_commit_sha"]
    materialized["code_tree_clean"] = replay_timing["code_tree_clean"]
    materialized.setdefault("replay_validation", {})["run_id"] = replay_timing["run_id"]
    materialized["artifact_sha256"] = {
        name: _sha256(Path(artifact_path))
        for name, artifact_path in materialized["artifacts"].items()
        if artifact_path is not None and Path(artifact_path).is_file()
    }
    validate_take_record(materialized)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(materialized, indent=2, sort_keys=True) + "\n")


def validate_take_record(record: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "take_id",
        "label",
        "threshold_commit_sha",
        "threshold_path",
        "threshold_sha256",
        "code_commit_sha",
        "code_tree_clean",
        "source",
        "artifacts",
        "timings_s",
        "metrics",
        "replay_validation",
        "visual_judge",
        "fusion",
        "cost_usd",
        "cleanup",
        "artifact_sha256",
    }
    missing = required.difference(record)
    if missing:
        raise ValueError(f"take record missing fields: {', '.join(sorted(missing))}")
    if record["label"] not in ALLOWED_TAKE_LABELS:
        raise ValueError(
            "take label must be PLUMBING TEST for a stock clip "
            "or Stephen's take for a builder recording"
        )
    sha = record["threshold_commit_sha"]
    if not _is_hex_digest(sha, 40):
        raise ValueError("threshold_commit_sha must be a full 40-character Git SHA")
    if not _is_hex_digest(record["threshold_sha256"], 64):
        raise ValueError("threshold_sha256 must be a 64-character SHA-256")
    if not _is_hex_digest(record["code_commit_sha"], 40):
        raise ValueError("code_commit_sha must be a full 40-character Git SHA")
    if record["code_tree_clean"] is not True:
        raise ValueError("code_tree_clean must be true for a Phase 1 take record")
    _verify_commit(record["code_commit_sha"], "code_commit_sha")
    threshold_path = Path(record["threshold_path"])
    if not threshold_path.is_file() or _sha256(threshold_path) != record["threshold_sha256"]:
        raise ValueError("threshold file does not match threshold_sha256")
    source_path = Path(record["source"]["path"])
    if not source_path.is_file() or _sha256(source_path) != record["source"].get("sha256"):
        raise ValueError("source file does not match source.sha256")
    missing_artifacts = [
        name
        for name, artifact_path in record["artifacts"].items()
        if artifact_path is not None and not Path(artifact_path).exists()
    ]
    if missing_artifacts:
        raise ValueError(f"artifact paths do not exist: {', '.join(sorted(missing_artifacts))}")
    for name in REQUIRED_FILE_ARTIFACTS:
        artifact_path = record["artifacts"].get(name)
        if not artifact_path or not Path(artifact_path).is_file():
            raise ValueError(f"required file artifact is missing: {name}")
        digest = record["artifact_sha256"].get(name)
        if not _is_hex_digest(digest, 64):
            raise ValueError(f"required artifact hash is missing or invalid: {name}")
    for name, digest in record["artifact_sha256"].items():
        artifact_path = record["artifacts"].get(name)
        if not artifact_path or not Path(artifact_path).is_file():
            raise ValueError(f"artifact hash has no file: {name}")
        if not _is_hex_digest(digest, 64) or _sha256(Path(artifact_path)) != digest:
            raise ValueError(f"artifact hash mismatch: {name}")
    replay_validation = record["replay_validation"]
    if not isinstance(replay_validation.get("run_id"), str) or not replay_validation["run_id"]:
        raise ValueError("replay_validation.run_id must be a non-empty string")
    decisive_hashes = {
        "sim_step_telemetry": "telemetry_sha256",
        "replay_timing": "replay_timing_sha256",
    }
    for artifact_name, replay_key in decisive_hashes.items():
        replay_digest = replay_validation.get(replay_key)
        if not _is_hex_digest(replay_digest, 64):
            raise ValueError(f"replay validation hash is missing or invalid: {replay_key}")
        if record["artifact_sha256"][artifact_name] != replay_digest:
            raise ValueError(f"replay validation hash differs for {artifact_name}")
    replay_timing = json.loads(
        Path(record["artifacts"]["replay_timing"]).read_text(encoding="utf-8")
    )
    if replay_timing.get("run_id") != replay_validation["run_id"]:
        raise ValueError("take record run_id differs from replay timing")
    if replay_timing.get("code_commit_sha") != record["code_commit_sha"]:
        raise ValueError("take record code commit differs from replay timing")
    if replay_timing.get("code_tree_clean") is not True:
        raise ValueError("replay timing does not prove a clean code tree")
    _validate_artifact_semantics(record, replay_timing)
    if any(float(value) < 0 for value in record["timings_s"].values()):
        raise ValueError("stage timings cannot be negative")
    costs = record["cost_usd"]
    if any(not isinstance(value, (int, float)) or value < 0 for value in costs.values()):
        raise ValueError("cost values must be non-negative numbers")
    components = [float(value) for key, value in costs.items() if key != "total"]
    if not math.isclose(float(costs["total"]), sum(components), abs_tol=1e-8):
        raise ValueError("cost total does not equal its components")
    metrics = record["metrics"]
    if bool(metrics.get("pass")) == bool(metrics.get("reason_codes")):
        raise ValueError("metrics pass and reason_codes disagree")
    visual_job = record["visual_judge"].get("job", {})
    # Terminal job states as Nebius documents them; COMPLETED is the success state.
    if visual_job.get("id") and visual_job.get("final_state") not in {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "ERROR",
    }:
        raise ValueError("Nebius visual job must have a terminal final_state")
    visual_status = record["visual_judge"].get("status")
    fusion_status = record["fusion"].get("status")
    if visual_status == "completed":
        if visual_job.get("final_state") != "COMPLETED":
            raise ValueError("completed visual result requires a COMPLETED job")
        if record["artifacts"].get("visual_output") is None:
            raise ValueError("completed visual result requires a visual artifact")
    elif visual_status == "blocked_before_job_create":
        if visual_job.get("id") or fusion_status != "not_run_missing_visual_verdicts":
            raise ValueError("blocked visual state is inconsistent with job or fusion state")
    else:
        raise ValueError(f"unsupported visual status: {visual_status}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_hex_digest(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and re.fullmatch("[0-9a-f]+", value) is not None
    )


def _verify_commit(commit_sha: str, field_name: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"{field_name} does not name a commit in this repository")


def _reject_identity_mismatch(record: dict[str, Any], replay_timing: dict[str, Any]) -> None:
    expected = {
        "code_commit_sha": replay_timing.get("code_commit_sha"),
        "code_tree_clean": replay_timing.get("code_tree_clean"),
    }
    for key, derived in expected.items():
        if key in record and record[key] != derived:
            raise ValueError(f"supplied {key} differs from replay timing")
    supplied_run_id = record.get("replay_validation", {}).get("run_id")
    if supplied_run_id is not None and supplied_run_id != replay_timing.get("run_id"):
        raise ValueError("supplied run_id differs from replay timing")


def _validate_artifact_semantics(record: dict[str, Any], replay_timing: dict[str, Any]) -> None:
    from showhand.cli import _validate_completion

    artifacts = record["artifacts"]
    sim_meta = json.loads(Path(artifacts["sim_metadata"]).read_text(encoding="utf-8"))
    artifact_metrics = json.loads(Path(artifacts["metrics"]).read_text(encoding="utf-8"))
    _validate_completion(
        replay_timing,
        sim_meta,
        artifacts["sim_step_telemetry"],
        artifacts["sonic_console"],
    )

    threshold_commit_sha = record["threshold_commit_sha"]
    _verify_commit(threshold_commit_sha, "threshold_commit_sha")
    threshold_path = Path(record["threshold_path"])
    if threshold_path.is_absolute() or ".." in threshold_path.parts:
        raise ValueError("threshold_path must be a repository-relative path")
    committed = subprocess.run(
        ["git", "show", f"{threshold_commit_sha}:{threshold_path.as_posix()}"],
        capture_output=True,
    )
    if committed.returncode != 0:
        raise ValueError("threshold_path does not exist at threshold_commit_sha")
    if hashlib.sha256(committed.stdout).hexdigest() != record["threshold_sha256"]:
        raise ValueError("threshold commit bytes differ from threshold_sha256")
    ancestry = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            threshold_commit_sha,
            record["code_commit_sha"],
        ],
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise ValueError("threshold commit is not an ancestor of the replay code commit")
    replay_commit_threshold = subprocess.run(
        ["git", "show", f"{record['code_commit_sha']}:{threshold_path.as_posix()}"],
        capture_output=True,
    )
    if replay_commit_threshold.returncode != 0:
        raise ValueError("threshold_path does not exist at replay code commit")
    if hashlib.sha256(replay_commit_threshold.stdout).hexdigest() != record["threshold_sha256"]:
        raise ValueError("replay code commit contains different threshold bytes")

    overall = artifact_metrics.get("overall")
    if not isinstance(overall, dict):
        raise ValueError("metrics artifact has no overall object")
    metric_fields = {
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
    }
    for key in metric_fields:
        if key not in overall or record["metrics"].get(key) != overall[key]:
            raise ValueError(f"take record metric differs from metrics artifact: {key}")
    if record["metrics"].get("retargeter") != artifact_metrics.get("retargeter"):
        raise ValueError("take record retargeter differs from metrics artifact")
    if artifact_metrics.get("threshold_sha256") != record["threshold_sha256"]:
        raise ValueError("metrics artifact threshold differs from take record")
    try:
        thresholds = parse_thresholds(replay_commit_threshold.stdout.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("threshold blob at replay code commit is not UTF-8") from error
    derived_reasons = metric_reason_codes(overall, thresholds)
    if overall["reason_codes"] != derived_reasons:
        raise ValueError("metrics artifact reason codes disagree with frozen thresholds")
    if overall["pass"] is not (not derived_reasons):
        raise ValueError("metrics artifact pass verdict disagrees with frozen thresholds")

    replay_validation = record["replay_validation"]
    replay_fields = {
        "publisher_warmup_s": "publisher_warmup_s",
        "max_allowed_jitter_s": "max_allowed_jitter_s",
        "publish_jitter_max_s": "publish_jitter_max_s",
        "publish_jitter_p95_s": "publish_jitter_p95_s",
        "telemetry_steps": "simulator_telemetry_steps",
        "telemetry_bytes": "simulator_telemetry_bytes",
        "telemetry_sha256": "simulator_telemetry_sha256",
    }
    for record_key, replay_key in replay_fields.items():
        if replay_validation.get(record_key) != replay_timing.get(replay_key):
            raise ValueError(f"replay validation differs from replay timing: {record_key}")
    if replay_validation.get("sonic_received_frames") != replay_timing.get("output_frames"):
        raise ValueError("SONIC received frame count differs from replay timing")
    if replay_validation.get("sonic_first_frame") != 0:
        raise ValueError("SONIC first frame must be zero")
    if replay_validation.get("sonic_final_frame") != replay_timing.get(
        "expected_final_frame_index"
    ):
        raise ValueError("SONIC final frame differs from replay timing")
    if replay_validation.get("post_roll_evaluated_s") != artifact_metrics.get(
        "post_roll_evaluated_s"
    ):
        raise ValueError("post-roll evidence differs from metrics artifact")

    source = record["source"]
    source_fields = {
        "frames": "source_frames",
        "fps": "source_fps",
        "pose_duration_s": "source_duration_s",
    }
    for source_key, replay_key in source_fields.items():
        if source.get(source_key) != replay_timing.get(replay_key):
            raise ValueError(f"source metadata differs from replay timing: {source_key}")
