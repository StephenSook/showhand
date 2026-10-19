"""Re-read MEASURED FACTS.md rows whose source is a JSON or YAML key."""

import datetime
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RE = re.compile(r"^(\S+\.(?:json|yaml|yml)) ([A-Za-z0-9_.]+)$")
MIN_MEASURED_TAKE_ROWS = 146
REQUIRED_VISUAL_SUMMARY_ROWS = {
    ("results/takes/take_0525/visual_summary.json", "timing.model_load_s"),
    ("results/takes/take_0525/visual_summary.json", "verdict_counts.match"),
    ("results/takes/take_0525/visual_summary.json", "verdict_counts.mismatch"),
    ("results/takes/take_0525/visual_summary.json", "verdict_counts.total"),
    ("results/takes/take_0526/visual_summary.json", "timing.model_load_s"),
    ("results/takes/take_0526/visual_summary.json", "verdict_counts.match"),
    ("results/takes/take_0526/visual_summary.json", "verdict_counts.mismatch"),
    ("results/takes/take_0526/visual_summary.json", "verdict_counts.total"),
    ("results/takes/take_0527/visual_summary.json", "timing.model_load_s"),
    ("results/takes/take_0527/visual_summary.json", "verdict_counts.match"),
    ("results/takes/take_0527/visual_summary.json", "verdict_counts.mismatch"),
    ("results/takes/take_0527/visual_summary.json", "verdict_counts.total"),
}
REQUIRED_SUPERVL_SUMMARY_ROWS = {
    (f"results/takes/take_{take}/supervl_summary.json", key)
    for take in ("0525", "0526", "0527")
    for key in (
        "cost_usd",
        "model_id",
        "verdict_counts.invalid",
        "verdict_counts.match",
        "verdict_counts.mismatch",
        "verdict_counts.total",
    )
}
REQUIRED_AGREEMENT_ROWS = {
    ("results/judge_agreement.json", key)
    for key in (
        "overall.windows_total",
        "overall.supervl_valid",
        "overall.supervl_invalid",
        "overall.cosmos_vs_supervl.agreements",
        "overall.cosmos_vs_supervl.compared",
        "overall.cosmos_vs_supervl.agreement_rate",
        "overall.cosmos_vs_deterministic.agreements",
        "overall.cosmos_vs_deterministic.compared",
        "overall.cosmos_vs_deterministic.agreement_rate",
        "overall.supervl_vs_deterministic.agreements",
        "overall.supervl_vs_deterministic.compared",
        "overall.supervl_vs_deterministic.agreement_rate",
    )
}


def _cells(line: str) -> list[str] | None:
    if not line.startswith("|"):
        return None
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _walk(data, key: str):
    value = data
    for part in key.split("."):
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise KeyError(key)
    return value


def _matches(actual, expected) -> bool:
    # PyYAML parses an unquoted YYYY-MM-DD scalar as a date. The sheet stores that day.
    if type(actual) is datetime.date:
        return type(expected) is str and actual.isoformat() == expected
    return actual == expected and type(actual) is type(expected)


def test_measured_json_and_yaml_rows_match_files() -> None:
    mismatches = []
    checked = 0
    checked_take_rows = 0
    checked_sources = set()
    for line in (ROOT / "FACTS.md").read_text(encoding="utf-8").splitlines():
        cells = _cells(line)
        if cells is None or len(cells) != 4 or cells[3] != "MEASURED":
            continue
        match = SOURCE_RE.fullmatch(cells[2])
        if match is None:
            continue
        rel, key = match.groups()
        actual = _walk(_load(ROOT / rel), key)
        expected = json.loads(cells[1])
        checked += 1
        checked_sources.add((rel, key))
        if rel.startswith("results/takes/"):
            checked_take_rows += 1
        if not _matches(actual, expected):
            mismatches.append(f"{cells[0]}: {rel} {key} is {actual!r}, FACTS.md has {expected!r}")
    assert checked > 0
    assert checked_take_rows >= MIN_MEASURED_TAKE_ROWS
    assert checked_sources >= REQUIRED_VISUAL_SUMMARY_ROWS
    assert checked_sources >= REQUIRED_SUPERVL_SUMMARY_ROWS
    assert checked_sources >= REQUIRED_AGREEMENT_ROWS
    assert not mismatches, "\n".join(mismatches)
