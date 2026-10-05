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
