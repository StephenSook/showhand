#!/usr/bin/env python3
"""Compare Cosmos, Super VL, and deterministic per-second verdicts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return value


def _list(value: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{source} contains no windows")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{source} contains a non-object window")
    return value


def _comparison(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    comparable = [
        row for row in rows if isinstance(row.get(left), bool) and isinstance(row.get(right), bool)
    ]
    agreements = sum(row[left] == row[right] for row in comparable)
    compared = len(comparable)
    return {
        "agreements": agreements,
        "compared": compared,
        "agreement_rate": round(agreements / compared, 6) if compared else None,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "windows_total": len(rows),
        "supervl_valid": sum(row["supervl_status"] == "valid" for row in rows),
        "supervl_invalid": sum(row["supervl_status"] == "invalid" for row in rows),
        "cosmos_vs_supervl": _comparison(rows, "cosmos_match", "supervl_match"),
        "cosmos_vs_deterministic": _comparison(rows, "cosmos_match", "deterministic_pass"),
        "supervl_vs_deterministic": _comparison(rows, "supervl_match", "deterministic_pass"),
    }


def compare_take(take_dir: Path) -> dict[str, Any]:
    cosmos = _read_object(take_dir / "visual_summary.json")
    supervl = _read_object(take_dir / "supervl_summary.json")
    metrics = _read_object(take_dir / "metrics.json")
    cosmos_windows = _list(cosmos.get("windows"), "Cosmos summary")
    supervl_windows = _list(supervl.get("windows"), "Super VL summary")
    metric_windows = _list(metrics.get("per_second"), "deterministic metrics")
    counts = {len(cosmos_windows), len(supervl_windows), len(metric_windows)}
    if len(counts) != 1:
        raise ValueError(f"{take_dir.name} window counts differ")

    rows = []
    for index, (cosmos_window, supervl_window, metric_window) in enumerate(
        zip(cosmos_windows, supervl_windows, metric_windows, strict=True)
    ):
        intervals = {
            (float(cosmos_window["start_s"]), float(cosmos_window["end_s"])),
            (float(supervl_window["start_s"]), float(supervl_window["end_s"])),
            (float(metric_window["start_s"]), float(metric_window["end_s"])),
        }
        if len(intervals) != 1 or int(supervl_window.get("window_index", -1)) != index:
            raise ValueError(f"{take_dir.name} window {index} is not aligned")
        if not isinstance(cosmos_window.get("match"), bool):
            raise ValueError(f"{take_dir.name} Cosmos window {index} has no boolean match")
        if not isinstance(metric_window.get("pass"), bool):
            raise ValueError(f"{take_dir.name} metric window {index} has no boolean pass")
        status = supervl_window.get("status")
        if status not in {"valid", "invalid"}:
            raise ValueError(f"{take_dir.name} Super VL window {index} has an unknown status")
        supervl_match = supervl_window.get("match") if status == "valid" else None
        if status == "valid" and not isinstance(supervl_match, bool):
            raise ValueError(f"{take_dir.name} Super VL window {index} has no boolean match")
        start_s, end_s = intervals.pop()
        rows.append(
            {
                "window_index": index,
                "start_s": start_s,
                "end_s": end_s,
                "cosmos_match": cosmos_window["match"],
                "supervl_status": status,
                "supervl_match": supervl_match,
                "deterministic_pass": metric_window["pass"],
                "cosmos_supervl_agree": (
                    cosmos_window["match"] == supervl_match if supervl_match is not None else None
                ),
                "cosmos_deterministic_agree": cosmos_window["match"] == metric_window["pass"],
                "supervl_deterministic_agree": (
                    supervl_match == metric_window["pass"] if supervl_match is not None else None
                ),
            }
        )
    return {"summary": _summary(rows), "windows": rows}


def build_report(results_dir: Path) -> dict[str, Any]:
    take_dirs = sorted(path.parent for path in results_dir.glob("take_*/supervl_summary.json"))
    if not take_dirs:
        raise ValueError("no Super VL summaries found")
    takes = {take_dir.name: compare_take(take_dir) for take_dir in take_dirs}
    all_rows = [row for take in takes.values() for row in take["windows"]]
    return {
        "schema_version": 1,
        "method": {
            "cosmos_value": "visual_summary.json windows.match",
            "supervl_value": "supervl_summary.json windows.match",
            "deterministic_value": "metrics.json per_second.pass",
            "invalid_handling": (
                "Exclude invalid Super VL windows only from comparisons using Super VL"
            ),
        },
        "overall": _summary(all_rows),
        "takes": takes,
    }


def _cell(comparison: dict[str, Any]) -> str:
    rate = comparison["agreement_rate"]
    if rate is None:
        return "0/0"
    return f"{comparison['agreements']}/{comparison['compared']} ({rate:.1%})"


def print_table(report: dict[str, Any]) -> None:
    print(
        "| Take | Windows | Super VL valid | Cosmos vs Super VL | "
        "Cosmos vs deterministic | Super VL vs deterministic |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    rows = [(name, take["summary"]) for name, take in report["takes"].items()]
    rows.append(("overall", report["overall"]))
    for name, summary in rows:
        print(
            f"| {name} | {summary['windows_total']} | {summary['supervl_valid']} | "
            f"{_cell(summary['cosmos_vs_supervl'])} | "
            f"{_cell(summary['cosmos_vs_deterministic'])} | "
            f"{_cell(summary['supervl_vs_deterministic'])} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path("results/takes"))
    parser.add_argument("--output", type=Path, default=Path("results/judge_agreement.json"))
    args = parser.parse_args()
    report = build_report(args.results_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print_table(report)


if __name__ == "__main__":
    main()
