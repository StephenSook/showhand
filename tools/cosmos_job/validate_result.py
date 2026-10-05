#!/usr/bin/env python3
"""Validate terminal job state and Cosmos result provenance before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MODEL_ID = "nvidia/Cosmos-Reason1-7B"
MODEL_REVISION = "375e24000b24baed78f4618d3dd779e47cd96323"
CONTAINER_IMAGE_DIGEST = "sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be"


def _job_state(job: dict) -> str:
    candidates = [
        job.get("state"),
        (job.get("status") or {}).get("state"),
        (job.get("status") or {}).get("phase"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate.rsplit(".", 1)[-1].upper()
    raise ValueError("Nebius job JSON contains no recognized state field")


def validate(job: dict, result: dict, manifest_bytes: bytes, take_id: str) -> None:
    state = _job_state(job)
    if state != "SUCCEEDED":
        raise ValueError(f"Nebius job final state is {state}, not SUCCEEDED")
    manifest = json.loads(manifest_bytes)
    windows = manifest.get("windows")
    if not isinstance(windows, list) or not windows:
        raise ValueError("visual manifest contains no windows")
    expected = {
        "take_id": take_id,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "container_image_digest": CONTAINER_IMAGE_DIGEST,
        "precision": "bfloat16",
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"Cosmos result {key} does not match expected provenance")
    verdicts = result.get("verdicts")
    if not isinstance(verdicts, list) or len(verdicts) != len(windows):
        raise ValueError("Cosmos verdict count does not match manifest")
    for index, (window, verdict) in enumerate(zip(windows, verdicts, strict=True)):
        for key in ("window_index", "start_s", "end_s"):
            if verdict.get(key) != window.get(key):
                raise ValueError(f"Cosmos verdict {index} {key} does not match manifest")
        if not isinstance(verdict.get("raw_output"), str) or not verdict["raw_output"]:
            raise ValueError(f"Cosmos verdict {index} has no raw output")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--take-id", required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    manifest_bytes = args.manifest.read_bytes()
    validate(job, result, manifest_bytes, args.take_id)
    print(result["model_id"], result["model_revision"], len(result["verdicts"]))


if __name__ == "__main__":
    main()
