"""Pre-registered residual harness for real take labels when they exist."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class ResidualInputError(ValueError):
    """Raised when real-label residual input is incomplete or invalid."""


@dataclass(frozen=True)
class ResidualRow:
    take_id: str
    human_accept: bool
    fused_accept: bool
    tracking_accept: bool


def load_rows(path: str | Path) -> list[ResidualRow]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"take_id", "human_accept", "fused_accept", "tracking_accept"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ResidualInputError(f"labels CSV must include {sorted(required)}")
        for raw in reader:
            rows.append(
                ResidualRow(
                    take_id=raw["take_id"],
                    human_accept=_parse_bool(raw["human_accept"]),
                    fused_accept=_parse_bool(raw["fused_accept"]),
                    tracking_accept=_parse_bool(raw["tracking_accept"]),
                )
            )
    if not rows:
        raise ResidualInputError("labels CSV contains no rows")
    if len({row.take_id for row in rows}) != len(rows):
        raise ResidualInputError("take_id values must be unique")
    return rows


def paired_agreement_residual(
    rows: list[ResidualRow],
    *,
    replicates: int = 10_000,
    seed: int = 20_261_005,
    label_source: str,
    minimum_valid_fraction: float = 0.95,
) -> dict[str, object]:
    if not rows:
        raise ResidualInputError("at least one labeled take is required")
    if replicates <= 0:
        raise ResidualInputError("bootstrap replicates must be positive")
    if label_source not in {"human", "synthetic"}:
        raise ResidualInputError("label_source must be human or synthetic")
    if not 0 < minimum_valid_fraction <= 1:
        raise ResidualInputError("minimum_valid_fraction must be in (0, 1]")
    ordered = sorted(rows, key=lambda row: row.take_id)
    human = np.asarray([row.human_accept for row in ordered], dtype=bool)
    fused = np.asarray([row.fused_accept for row in ordered], dtype=bool)
    tracking = np.asarray([row.tracking_accept for row in ordered], dtype=bool)
    fused_match = fused == human
    tracking_match = tracking == human
    fused_kappa = _cohen_kappa(human, fused)
    tracking_kappa = _cohen_kappa(human, tracking)
    observed = fused_kappa - tracking_kappa
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(ordered), size=(replicates, len(ordered)))
    deltas = []
    invalid = 0
    for sample in indices:
        try:
            deltas.append(
                _cohen_kappa(human[sample], fused[sample])
                - _cohen_kappa(human[sample], tracking[sample])
            )
        except ResidualInputError:
            invalid += 1
    minimum_valid = math.ceil(replicates * minimum_valid_fraction)
    if len(deltas) < minimum_valid:
        raise ResidualInputError(
            f"only {len(deltas)} of {replicates} bootstrap replicates had defined Cohen kappa; "
            f"minimum is {minimum_valid}"
        )
    low, high = np.percentile(deltas, [2.5, 97.5])
    return {
        "schema_version": 1,
        "n": len(ordered),
        "fused_agreement": round(float(fused_match.mean()), 6),
        "tracking_agreement": round(float(tracking_match.mean()), 6),
        "fused_kappa": round(fused_kappa, 6),
        "tracking_kappa": round(tracking_kappa, 6),
        "paired_kappa_difference": round(observed, 6),
        "bootstrap_95_percentile": [round(float(low), 6), round(float(high), 6)],
        "bootstrap_replicates": replicates,
        "bootstrap_invalid_replicates": invalid,
        "bootstrap_seed": seed,
        "minimum_valid_bootstrap_fraction": minimum_valid_fraction,
        "label_source": label_source,
        "fused_confusion": _confusion(human, fused),
        "tracking_confusion": _confusion(human, tracking),
    }


def tracking_alone_accept(overall: dict[str, object], thresholds: dict[str, object]) -> bool:
    """The pre-registered baseline judge: accept a whole take on tracking error alone, at the frozen
    limits, failing only above a limit as src/showhand/metrics.py does."""
    tracking = thresholds["tracking"]
    assert isinstance(tracking, dict)
    mean_ok = float(overall["tracking_mean_abs_error_rad"]) <= tracking["max_mean_abs_error_rad"]
    p95_ok = float(overall["tracking_p95_abs_error_rad"]) <= tracking["max_p95_abs_error_rad"]
    return mean_ok and p95_ok


def agreement_summary(rows: list[ResidualRow]) -> dict[str, object]:
    """The pre-registered secondary results: n, each judge's agreement rate and confusion matrix."""
    if not rows:
        raise ResidualInputError("at least one labeled take is required")
    ordered = sorted(rows, key=lambda row: row.take_id)
    human = np.asarray([row.human_accept for row in ordered], dtype=bool)
    fused = np.asarray([row.fused_accept for row in ordered], dtype=bool)
    tracking = np.asarray([row.tracking_accept for row in ordered], dtype=bool)
    return {
        "n": len(ordered),
        "fused_agreement": round(float((fused == human).mean()), 6),
        "tracking_agreement": round(float((tracking == human).mean()), 6),
        "fused_confusion": _confusion(human, fused),
        "tracking_confusion": _confusion(human, tracking),
    }


def prereg_report(
    rows: list[ResidualRow], prereg: dict[str, object], *, label_source: str
) -> dict[str, object]:
    """Apply config/residual_prereg.yaml to labeled takes.

    The primary result is the paired kappa difference. When either judge's kappa is undefined on the
    observed labels, the pre-registered policy makes the evaluation invalid: the report says so and
    why, and still gives the secondary results, which are always defined.
    """
    primary = prereg["primary"]
    assert isinstance(primary, dict)
    ordered = sorted(rows, key=lambda row: row.take_id)
    human = np.asarray([row.human_accept for row in ordered], dtype=bool)
    kappas: dict[str, object] = {}
    undefined = []
    for judge in ("fused", "tracking"):
        values = np.asarray([getattr(row, f"{judge}_accept") for row in ordered], dtype=bool)
        try:
            kappas[f"{judge}_kappa"] = round(_cohen_kappa(human, values), 6)
        except ResidualInputError:
            kappas[f"{judge}_kappa"] = None
            undefined.append(judge)
    report: dict[str, object] = {
        "schema_version": 1,
        "label_source": label_source,
        **agreement_summary(rows),
        **kappas,
    }
    if undefined:
        if prereg["observed_undefined_kappa"] != "evaluation_invalid":
            raise ResidualInputError("unknown policy for an undefined observed kappa")
        report["status"] = "evaluation_invalid"
        report["why"] = (
            f"Cohen kappa is undefined for the {' and '.join(undefined)} judge on these labels: "
            "the human and that judge each gave every take the same label, so expected "
            "agreement is 1"
        )
        return report
    report["status"] = "evaluated"
    report["primary"] = paired_agreement_residual(
        rows,
        replicates=int(primary["bootstrap_replicates"]),
        seed=int(primary["bootstrap_seed"]),
        label_source=label_source,
        minimum_valid_fraction=float(prereg["minimum_valid_bootstrap_fraction"]),
    )
    return report


def _cohen_kappa(reference: np.ndarray, judge: np.ndarray) -> float:
    observed = float((reference == judge).mean())
    reference_positive = float(reference.mean())
    judge_positive = float(judge.mean())
    expected = reference_positive * judge_positive + (1.0 - reference_positive) * (
        1.0 - judge_positive
    )
    if math.isclose(expected, 1.0):
        raise ResidualInputError("Cohen kappa is undefined for degenerate labels")
    return (observed - expected) / (1.0 - expected)


def _confusion(reference: np.ndarray, judge: np.ndarray) -> dict[str, int]:
    return {
        "human_accept_judge_accept": int((reference & judge).sum()),
        "human_accept_judge_reshow": int((reference & ~judge).sum()),
        "human_reshow_judge_accept": int((~reference & judge).sum()),
        "human_reshow_judge_reshow": int((~reference & ~judge).sum()),
    }


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "accept", "yes"}:
        return True
    if normalized in {"0", "false", "reshow", "no"}:
        return False
    raise ResidualInputError(f"invalid binary label: {value!r}")
