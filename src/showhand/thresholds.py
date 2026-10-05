"""Load and validate the frozen deterministic grading thresholds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ThresholdError(ValueError):
    """Raised when the threshold file is incomplete or not frozen."""


def load_thresholds(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ThresholdError("threshold file must contain a mapping")
    if data.get("frozen") is not True:
        raise ThresholdError("threshold file must have frozen: true before grading")
    required = {
        "tracking.max_mean_abs_error_rad",
        "tracking.max_p95_abs_error_rad",
        "balance.fall_root_height_m",
        "balance.max_root_tilt_deg",
        "balance.max_out_of_balance_seconds",
        "foot_slip.contact_speed_threshold_m_s",
        "foot_slip.max_slip_seconds",
    }
    missing = [key for key in sorted(required) if _get_path(data, key) is None]
    if missing:
        raise ThresholdError(f"missing thresholds: {', '.join(missing)}")
    return data


def _get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
