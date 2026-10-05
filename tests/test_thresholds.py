from pathlib import Path

import pytest

from showhand.thresholds import ThresholdError, load_thresholds, parse_thresholds


def test_frozen_thresholds_load() -> None:
    values = load_thresholds("config/thresholds.yaml")
    assert values["frozen"] is True
    assert values["window_seconds"] == 1.0


def test_frozen_thresholds_parse_from_verified_text() -> None:
    values = parse_thresholds(Path("config/thresholds.yaml").read_text(encoding="utf-8"))
    assert values["frozen"] is True
    assert values["tracking"]["max_mean_abs_error_rad"] == 0.5


def test_unfrozen_thresholds_refuse(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.yaml"
    path.write_text("frozen: false\n", encoding="utf-8")
    with pytest.raises(ThresholdError, match="frozen"):
        load_thresholds(path)


def test_frozen_thresholds_require_decision_keys(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.yaml"
    path.write_text("frozen: true\nschema_version: 1\nwindow_seconds: 1.0\n", encoding="utf-8")
    with pytest.raises(ThresholdError, match="missing thresholds"):
        load_thresholds(path)
