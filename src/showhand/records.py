"""Take-record construction with explicit artifact and timing provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_take_record(path: str | Path, record: dict[str, Any]) -> None:
    validate_take_record(record)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_take_record(record: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "take_id",
        "label",
        "threshold_commit_sha",
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
    }
    missing = required.difference(record)
    if missing:
        raise ValueError(f"take record missing fields: {', '.join(sorted(missing))}")
    if record["label"] != "PLUMBING TEST":
        raise ValueError("Phase 1 stock clip records must be labeled PLUMBING TEST")
    sha = record["threshold_commit_sha"]
    if not isinstance(sha, str) or len(sha) != 40:
        raise ValueError("threshold_commit_sha must be a full 40-character Git SHA")
    if len(str(record["threshold_sha256"])) != 64:
        raise ValueError("threshold_sha256 must be a 64-character SHA-256")
    if len(str(record["code_commit_sha"])) != 40:
        raise ValueError("code_commit_sha must be a full 40-character Git SHA")
    if any(float(value) < 0 for value in record["timings_s"].values()):
        raise ValueError("stage timings cannot be negative")
    if float(record["cost_usd"]["total"]) < 0:
        raise ValueError("cost cannot be negative")
    visual_job = record["visual_judge"].get("job", {})
    if visual_job.get("id") and visual_job.get("final_state") not in {
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    }:
        raise ValueError("Nebius visual job must have a terminal final_state")
