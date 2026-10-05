from pathlib import Path

import pytest

from showhand.thresholds import ThresholdError, load_thresholds


def test_frozen_thresholds_load() -> None:
    values = load_thresholds("config/thresholds.yaml")
    assert values["frozen"] is True
    assert values["window_seconds"] == 1.0


def test_unfrozen_thresholds_refuse(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.yaml"
    path.write_text("frozen: false\n", encoding="utf-8")
    with pytest.raises(ThresholdError, match="frozen"):
        load_thresholds(path)
