"""The replay page's grades.json files must be exactly what tools/replay_grades.py writes."""

import json
from pathlib import Path

import pytest

from showhand.thresholds import load_thresholds
from tools import replay_grades

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "takes"
TAKES = ("take_0525", "take_0526", "take_0527")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("take", TAKES)
def test_committed_grades_match_a_fresh_export(take: str) -> None:
    thresholds = load_thresholds(ROOT / "config" / "thresholds.yaml")
    fresh = replay_grades.grades(RESULTS, take, thresholds)
    committed = _json(ROOT / "web" / "public" / "replay" / take / "grades.json")
    assert committed == fresh


@pytest.mark.parametrize("take", TAKES)
def test_runtime_copies_the_recorded_times_unrounded(take: str) -> None:
    base = RESULTS / take
    stages = _json(base / "driver" / "stage_timings.json")
    cosmos = _json(base / "visual_summary.json")
    supervl = _json(base / "supervl_summary.json")
    assert replay_grades.runtime(base, cosmos, supervl) == {
        "gem_x_offline_s": stages["gem_x_offline_s"],
        "replay_process_wall_s": stages["replay_process_wall_s"],
        "cosmos_model_load_s": cosmos["timing"]["model_load_s"],
        "supervl_wall_s": supervl["timing"]["wall_s"],
        "supervl_cost_usd": supervl["cost_usd"],
    }
