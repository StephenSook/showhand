import json
from pathlib import Path

from tools.judge_agreement import build_report, print_table


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_agreement_excludes_invalid_supervl_only_from_its_comparisons(
    tmp_path: Path, capsys
) -> None:
    take = tmp_path / "take_demo"
    take.mkdir()
    intervals = [(0.0, 1.0), (1.0, 2.0)]
    _write(
        take / "visual_summary.json",
        {
            "windows": [
                {"start_s": a, "end_s": b, "match": match}
                for (a, b), match in zip(intervals, [True, False], strict=True)
            ]
        },
    )
    _write(
        take / "supervl_summary.json",
        {
            "windows": [
                {"window_index": 0, "start_s": 0.0, "end_s": 1.0, "status": "valid", "match": True},
                {"window_index": 1, "start_s": 1.0, "end_s": 2.0, "status": "invalid"},
            ]
        },
    )
    _write(
        take / "metrics.json",
        {"per_second": [{"start_s": a, "end_s": b, "pass": True} for a, b in intervals]},
    )

    report = build_report(tmp_path)
    summary = report["overall"]
    assert summary["cosmos_vs_supervl"] == {
        "agreements": 1,
        "compared": 1,
        "agreement_rate": 1.0,
    }
    assert summary["cosmos_vs_deterministic"] == {
        "agreements": 1,
        "compared": 2,
        "agreement_rate": 0.5,
    }
    assert summary["supervl_vs_deterministic"] == {
        "agreements": 1,
        "compared": 1,
        "agreement_rate": 1.0,
    }

    print_table(report)
    assert (
        "| overall | 2 | 1 | 1/1 (100.0%) | 1/2 (50.0%) | 1/1 (100.0%) |" in capsys.readouterr().out
    )
