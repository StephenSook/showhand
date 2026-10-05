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

REQUIRED_FILE_ARTIFACTS = (
    "sim_step_telemetry",
    "sim_metadata",
    "replay_timing",
    "sonic_console",
    "metrics",
)


def write_take_record(path: str | Path, record: dict[str, Any]) -> None:
    materialized = deepcopy(record)
    replay_timing_path = materialized.get("artifacts", {}).get("replay_timing")
    if not replay_timing_path or not Path(replay_timing_path).is_file():
        raise ValueError("replay_timing artifact is required before writing a take record")
    replay_timing = json.loads(Path(replay_timing_path).read_text(encoding="utf-8"))
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
    output.write_text(json.dumps(materialized, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    if record["label"] != "PLUMBING TEST":
        raise ValueError("Phase 1 stock clip records must be labeled PLUMBING TEST")
    sha = record["threshold_commit_sha"]
    if not _is_hex_digest(sha, 40):
        raise ValueError("threshold_commit_sha must be a full 40-character Git SHA")
    if not _is_hex_digest(record["threshold_sha256"], 64):
        raise ValueError("threshold_sha256 must be a 64-character SHA-256")
    if not _is_hex_digest(record["code_commit_sha"], 40):
        raise ValueError("code_commit_sha must be a full 40-character Git SHA")
    if record["code_tree_clean"] is not True:
        raise ValueError("code_tree_clean must be true for a Phase 1 take record")
    _verify_commit(record["code_commit_sha"])
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
    if visual_job.get("id") and visual_job.get("final_state") not in {
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    }:
        raise ValueError("Nebius visual job must have a terminal final_state")
    visual_status = record["visual_judge"].get("status")
    fusion_status = record["fusion"].get("status")
    if visual_status == "completed":
        if visual_job.get("final_state") != "SUCCEEDED":
            raise ValueError("completed visual result requires a SUCCEEDED job")
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


def _verify_commit(commit_sha: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("code_commit_sha does not name a commit in this repository")
