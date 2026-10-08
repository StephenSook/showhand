#!/usr/bin/env python3
"""Write a privacy-safe, explicitly allowlisted summary of a visual result."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MODEL_FIELDS = ("model_id",)
JOB_FIELDS = (
    "job_id",
    "job_state",
    "gpu_type",
    "gpu_seconds",
    "cost_usd",
    "price_source",
)
TIMING_FIELDS = ("model_load_s", "job_wall_s")
WINDOW_FIELDS = ("start_s", "end_s", "match", "reason_codes", "summary", "latency_s")
FORBIDDEN_PATH = re.compile(
    r"(?:(?:^|[\\/])(?:clips|frames|images|pairs|renders|video)(?=[\\/]|$)"
    r"|(?<![A-Za-z0-9_])(?:clips|frames|images|pairs|renders|video)(?=[\\/]))",
    re.IGNORECASE,
)
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/mnt/c/|/home/)", re.IGNORECASE)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _copy_present(source: dict, fields: tuple[str, ...]) -> dict:
    return {field: source[field] for field in fields if field in source}


def build_summary(visual: dict) -> dict:
    """Return only the approved visual-result fields and reject unsafe kept strings."""
    if not isinstance(visual, dict):
        raise ValueError("visual result must be a JSON object")
    if not isinstance(visual.get("model_id"), str):
        raise ValueError("visual result must contain a string model_id")
    verdicts = visual.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        raise ValueError("visual result must contain at least one verdict")

    summary = _copy_present(visual, MODEL_FIELDS)

    job_source = visual.get("job")
    if not isinstance(job_source, dict):
        job_source = visual
    job = _copy_present(job_source, JOB_FIELDS)
    if job:
        summary["job"] = job

    timing = _copy_present(visual, TIMING_FIELDS)
    if timing:
        summary["timing"] = timing

    windows = []
    for index, verdict in enumerate(verdicts):
        if not isinstance(verdict, dict):
            raise ValueError(f"verdict {index} must be a JSON object")
        missing = {"start_s", "end_s", "match"} - verdict.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"verdict {index} is missing required fields: {names}")
        if not isinstance(verdict["match"], bool):
            raise ValueError(f"verdict {index} match must be a boolean")
        windows.append(_copy_present(verdict, WINDOW_FIELDS))

    match_count = sum(window["match"] for window in windows)
    summary["verdict_counts"] = {
        "match": match_count,
        "mismatch": len(windows) - match_count,
        "total": len(windows),
    }
    summary["windows"] = windows

    for value in _strings(summary):
        if FORBIDDEN_PATH.search(value) or LOCAL_PATH.search(value):
            raise ValueError("kept string contains a private artifact path")
    return summary


def summarize_visual(source: str | Path, destination: str | Path) -> None:
    visual = json.loads(Path(source).read_text(encoding="utf-8"))
    summary = build_summary(visual)
    Path(destination).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="local visual.json to summarize")
    parser.add_argument("destination", help="visual_summary.json to write")
    args = parser.parse_args()
    summarize_visual(args.source, args.destination)


if __name__ == "__main__":
    main()
