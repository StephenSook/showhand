#!/usr/bin/env python3
"""Run the pre-registered residual comparison on the outside human grades that exist.

Inputs, all committed: the human grades (results/residual/human_grades.json), each take's fused
decision (results/takes/<take>/fusion.json output.decision), each take's whole-take tracking error
(results/takes/<take>/metrics.json overall), the frozen thresholds and config/residual_prereg.yaml.
Writes results/residual/report.json, with the per-take labels it compared. Nothing here is tuned to
the grades: the baseline judge and the policy for an undefined kappa were fixed before any grade
existed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from showhand.residual import (  # noqa: E402
    ResidualInputError,
    ResidualRow,
    prereg_report,
    tracking_alone_accept,
)
from showhand.thresholds import load_thresholds  # noqa: E402

GRADE_FIELDS = {"take_id", "human_accept", "grade_text", "graded_utc", "how"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fused_accept(fusion: dict[str, Any], take_id: str) -> bool:
    decision = (fusion.get("output") or {}).get("decision")
    if decision not in {"accept", "reshow"}:
        raise ResidualInputError(f"{take_id}: fusion output.decision is {decision!r}")
    return decision == "accept"


def build_rows(grades: Path, takes: Path, thresholds: dict[str, Any]) -> list[ResidualRow]:
    graded = _read_json(grades).get("grades")
    if not isinstance(graded, list) or not graded:
        raise ResidualInputError(f"{grades} has no grades")
    rows = []
    for grade in graded:
        if not isinstance(grade, dict) or set(grade) != GRADE_FIELDS:
            raise ResidualInputError(f"each grade must have exactly {sorted(GRADE_FIELDS)}")
        take_id = grade["take_id"]
        if grade["human_accept"] not in {"accept", "reshow"}:
            raise ResidualInputError(f"{take_id}: human_accept must be accept or reshow")
        take = takes / take_id
        metrics = _read_json(take / "metrics.json")
        rows.append(
            ResidualRow(
                take_id=take_id,
                human_accept=grade["human_accept"] == "accept",
                fused_accept=fused_accept(_read_json(take / "fusion.json"), take_id),
                tracking_accept=tracking_alone_accept(metrics["overall"], thresholds),
            )
        )
    if len({row.take_id for row in rows}) != len(rows):
        raise ResidualInputError("take_id values must be unique")
    return rows


def _word(value: bool) -> str:
    return "accept" if value else "reshow"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grades", type=Path, default=Path("results/residual/human_grades.json"))
    parser.add_argument("--takes", type=Path, default=Path("results/takes"))
    parser.add_argument("--thresholds", type=Path, default=Path("config/thresholds.yaml"))
    parser.add_argument("--prereg", type=Path, default=Path("config/residual_prereg.yaml"))
    parser.add_argument("--out", type=Path, default=Path("results/residual/report.json"))
    args = parser.parse_args()

    rows = build_rows(args.grades, args.takes, load_thresholds(args.thresholds))
    prereg = yaml.safe_load(args.prereg.read_text(encoding="utf-8"))
    report = prereg_report(rows, prereg, label_source="human")
    report["labels"] = [
        {
            "take_id": row.take_id,
            "human": _word(row.human_accept),
            "fused_judge": _word(row.fused_accept),
            "tracking_alone": _word(row.tracking_accept),
        }
        for row in sorted(rows, key=lambda r: r.take_id)
    ]
    report["inputs"] = {
        "grades": args.grades.as_posix(),
        "grades_sha256": _sha256(args.grades),
        "prereg": args.prereg.as_posix(),
        "prereg_sha256": _sha256(args.prereg),
        "thresholds": args.thresholds.as_posix(),
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    summary = ("status", "n", "fused_agreement", "tracking_agreement")
    print(json.dumps({key: report[key] for key in summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
