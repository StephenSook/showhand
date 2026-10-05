"""Take-record construction with explicit artifact and timing provenance."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


def write_take_record(path: str | Path, record: dict[str, Any]) -> None:
    materialized = deepcopy(record)
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
        "source",
        "artifacts",
        "timings_s",
        "metrics",
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
    for name, digest in record["artifact_sha256"].items():
        artifact_path = record["artifacts"].get(name)
        if not artifact_path or not Path(artifact_path).is_file():
            raise ValueError(f"artifact hash has no file: {name}")
        if not _is_hex_digest(digest, 64) or _sha256(Path(artifact_path)) != digest:
            raise ValueError(f"artifact hash mismatch: {name}")
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
