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


def test_committed_residual_is_the_report_byte_for_byte() -> None:
    report = ROOT / "results" / "residual" / "report.json"
    committed = (ROOT / "web" / "public" / "replay" / "residual.json").read_bytes()
    assert committed == replay_grades.residual_bytes(report)
    assert committed == report.read_bytes()


def test_residual_export_refuses_labels_that_are_not_human(tmp_path: Path) -> None:
    report = _json(ROOT / "results" / "residual" / "report.json")
    synthetic = tmp_path / "report.json"
    synthetic.write_text(json.dumps({**report, "label_source": "synthetic"}), encoding="utf-8")
    with pytest.raises(ValueError, match="not 'human'"):
        replay_grades.residual_bytes(synthetic)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({**report, "labels": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="no per-take labels"):
        replay_grades.residual_bytes(empty)


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
