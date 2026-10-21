import json
import subprocess
import sys
from pathlib import Path

import yaml

from showhand.residual import (
    ResidualRow,
    paired_agreement_residual,
    prereg_report,
    tracking_alone_accept,
)

ROOT = Path(__file__).resolve().parents[1]
PREREG = yaml.safe_load((ROOT / "config" / "residual_prereg.yaml").read_text(encoding="utf-8"))
LIMITS = {"tracking": {"max_mean_abs_error_rad": 0.5, "max_p95_abs_error_rad": 1.0}}


def test_residual_harness_on_synthetic_labels_only() -> None:
    pattern = [
        (True, True, False),
        (False, False, True),
        (True, True, True),
        (False, True, False),
    ]
    synthetic = [
        ResidualRow(f"synthetic-{index:02d}", *pattern[index % len(pattern)]) for index in range(20)
    ]
    first = paired_agreement_residual(synthetic, replicates=200, seed=7, label_source="synthetic")
    second = paired_agreement_residual(synthetic, replicates=200, seed=7, label_source="synthetic")
    assert first == second
    assert first["n"] == 20
    assert first["label_source"] == "synthetic"
    assert "fused_kappa" in first
    assert "paired_kappa_difference" in first


def test_tracking_baseline_fails_only_above_a_frozen_limit() -> None:
    at_limits = {"tracking_mean_abs_error_rad": 0.5, "tracking_p95_abs_error_rad": 1.0}
    assert tracking_alone_accept(at_limits, LIMITS)
    over_p95 = {**at_limits, "tracking_p95_abs_error_rad": 1.0001}
    assert not tracking_alone_accept(over_p95, LIMITS)
    over_mean = {**at_limits, "tracking_mean_abs_error_rad": 0.5001}
    assert not tracking_alone_accept(over_mean, LIMITS)


def test_an_undefined_observed_kappa_makes_the_evaluation_invalid_and_keeps_secondaries() -> None:
    rows = [ResidualRow(f"take-{index}", True, False, True) for index in range(3)]
    report = prereg_report(rows, PREREG, label_source="synthetic")
    assert report["status"] == "evaluation_invalid"
    assert report["tracking_kappa"] is None and report["fused_kappa"] == 0.0
    assert report["n"] == 3
    assert report["fused_agreement"] == 0.0 and report["tracking_agreement"] == 1.0
    assert report["fused_confusion"]["human_accept_judge_reshow"] == 3
    assert "primary" not in report


def test_defined_kappas_run_the_pre_registered_primary() -> None:
    pattern = [(True, True, False), (False, False, True), (True, True, True), (False, True, False)]
    rows = [ResidualRow(f"synthetic-{i:02d}", *pattern[i % len(pattern)]) for i in range(20)]
    report = prereg_report(rows, PREREG, label_source="synthetic")
    assert report["status"] == "evaluated"
    assert report["primary"]["bootstrap_replicates"] == PREREG["primary"]["bootstrap_replicates"]
    assert report["primary"]["bootstrap_seed"] == PREREG["primary"]["bootstrap_seed"]


def _run_report(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/residual_report.py", *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_the_committed_residual_report_is_what_its_inputs_produce(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    result = _run_report("--out", str(out))
    assert result.returncode == 0, result.stderr
    committed = json.loads((ROOT / "results/residual/report.json").read_text(encoding="utf-8"))
    assert json.loads(out.read_text(encoding="utf-8")) == committed
    assert committed["label_source"] == "human" and committed["n"] == 3
    assert [label["take_id"] for label in committed["labels"]] == [
        "take_0525",
        "take_0526",
        "take_0527",
    ]


def test_a_grade_that_is_not_accept_or_reshow_is_refused(tmp_path: Path) -> None:
    grades = tmp_path / "grades.json"
    grade = {
        "take_id": "take_0525",
        "human_accept": "keep",
        "grade_text": "keep",
        "graded_utc": "2026-10-21T07:52:01Z",
        "how": "x",
    }
    grades.write_text(json.dumps({"grades": [grade]}), encoding="utf-8")
    result = _run_report("--grades", str(grades), "--out", str(tmp_path / "report.json"))
    assert result.returncode != 0
    assert "human_accept must be accept or reshow" in result.stderr
