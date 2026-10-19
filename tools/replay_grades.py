"""Write the browser replay's per-take grades from the committed take results.

Reads results/takes/<take>/{metrics.json, visual_summary.json, supervl_summary.json, fusion.json}
and writes <web>/<take>/grades.json: one row per second with the deterministic grade, the Cosmos
Reason1 verdict and the Nemotron Super VL verdict, plus every fusion attempt (the proposal Nemotron
made and whether the guard passed or refused it) and the final decision.

  python tools/replay_grades.py --results results/takes --web web/public/replay
    --takes take_0525 take_0526 take_0527

The frozen cutoffs from config/thresholds.yaml ride along, so the page prints each limit beside its
measured value without keeping a second copy of the numbers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from showhand.thresholds import load_thresholds

RULE_FIELDS = (
    "tracking_mean_abs_error_rad",
    "tracking_p95_abs_error_rad",
    "root_tilt_max_deg",
    "root_height_min_m",
    "foot_slip_max_m_s",
    "foot_slip_seconds",
    "out_of_balance_seconds",
    "falls",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def window_for(windows: list[dict], start: float) -> dict | None:
    for window in windows:
        if abs(float(window["start_s"]) - start) < 1e-6:
            return window
    return None


def verdict(window: dict | None) -> dict | None:
    if window is None:
        return None
    return {
        "match": window.get("match"),
        "status": window.get("status", "valid"),
        "reason_codes": window.get("reason_codes", []),
        "summary": window.get("summary", ""),
    }


def proposal(attempt: dict) -> dict | None:
    try:
        content = attempt["raw_response"]["choices"][0]["message"]["content"]
        value = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return {"decision": value.get("decision"), "reshow_windows": value.get("reshow_windows", [])}


def cutoffs(thresholds: dict[str, Any]) -> dict[str, float]:
    return {
        "tracking_mean_abs_error_rad": thresholds["tracking"]["max_mean_abs_error_rad"],
        "tracking_p95_abs_error_rad": thresholds["tracking"]["max_p95_abs_error_rad"],
        "root_height_min_m": thresholds["balance"]["fall_root_height_m"],
        "root_tilt_max_deg": thresholds["balance"]["max_root_tilt_deg"],
        "foot_slip_seconds": thresholds["foot_slip"]["max_slip_seconds"],
        "out_of_balance_seconds": thresholds["balance"]["max_out_of_balance_seconds"],
    }


def grades(results: Path, take: str, thresholds: dict[str, Any]) -> dict:
    base = results / take
    metrics = load(base / "metrics.json")
    cosmos = load(base / "visual_summary.json")
    supervl = load(base / "supervl_summary.json")
    fusion = load(base / "fusion.json")
    seconds = []
    for second in metrics["per_second"]:
        start = float(second["start_s"])
        seconds.append(
            {
                "start_s": start,
                "end_s": float(second["end_s"]),
                "rules": {
                    "pass": second["pass"],
                    "reason_codes": second["reason_codes"],
                    **{field: second.get(field) for field in RULE_FIELDS},
                },
                "cosmos": verdict(window_for(cosmos["windows"], start)),
                "supervl": verdict(window_for(supervl["windows"], start)),
            }
        )
    return {
        "schema_version": 1,
        "take": take,
        "duration_s": metrics["duration_s"],
        "overall": {
            "pass": metrics["overall"]["pass"],
            "reason_codes": metrics["overall"]["reason_codes"],
        },
        "cutoffs": cutoffs(thresholds),
        "models": {
            "cosmos": cosmos["model_id"],
            "supervl": supervl["model_id"],
            "fusion": fusion["model"],
        },
        "seconds": seconds,
        "fusion": {
            "decided_by": fusion["decided_by"],
            "status": fusion["status"],
            "request_id": fusion["request_id"],
            "cost_usd": fusion["cost_usd"],
            "attempts": [
                {
                    "attempt": attempt["attempt"],
                    "guard": attempt["guard"],
                    "guard_error": attempt.get("guard_error"),
                    "proposal": proposal(attempt),
                    "latency_s": attempt.get("latency_s"),
                }
                for attempt in fusion["attempts"]
            ],
            "final": fusion["output"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--takes", nargs="+", required=True)
    parser.add_argument("--thresholds", type=Path, default=Path("config/thresholds.yaml"))
    args = parser.parse_args()
    thresholds = load_thresholds(args.thresholds)
    index = []
    for take in args.takes:
        record = grades(args.results, take, thresholds)
        out = args.web / take / "grades.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
        label = load(args.results / take / "take_record.json")["label"]
        index.append(
            {"take": take, "label": label, "decision": record["fusion"]["final"]["decision"]}
        )
        print(out)
    (args.web / "index.json").write_text(
        json.dumps({"schema_version": 1, "takes": index}, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
