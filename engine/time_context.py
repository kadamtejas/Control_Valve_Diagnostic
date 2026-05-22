"""
Time context — sample rate detection and lag-formatting helpers.
==================================================================

Layer 1, module 1. Auto-detects the sample rate from the timestamp
column and reports lags in human-readable units (sec/min/hr) regardless
of data resolution.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .utils import logger


@dataclass
class TimeContext:
    """Encapsulates the temporal characteristics of the dataset."""
    dt_seconds: float           # native sample interval (seconds)
    n_samples: int              # number of rows
    duration_seconds: float     # total span of data
    irregular: bool             # True if timestamps are non-uniform
    gap_count: int              # number of gaps detected
    display_unit: str           # "sec", "min", or "hr"
    display_factor: float       # multiply seconds by this to get display-unit value

    @property
    def duration_hours(self) -> float:
        return self.duration_seconds / 3600.0

    def samples_to_display_str(self, n_samples: int) -> str:
        """Convert a sample-count lag into a string in the chosen display unit."""
        secs = n_samples * self.dt_seconds
        val = secs * self.display_factor
        return f"{val:.1f} {self.display_unit}"

    def dt_str(self) -> str:
        return self.samples_to_display_str(1)


def detect_time_context(timestamps: pd.Series) -> TimeContext:
    """Auto-detect sample interval, irregularity, and choose display unit."""
    ts = pd.to_datetime(timestamps, errors="coerce").dropna()
    if len(ts) < 2:
        # Fallback: assume 1 minute
        return TimeContext(60.0, len(ts), 0.0, False, 0, "min", 1 / 60)

    diffs = ts.diff().dt.total_seconds().dropna()
    if len(diffs) == 0:
        return TimeContext(60.0, len(ts), 0.0, False, 0, "min", 1 / 60)

    median_dt = float(diffs.median())
    if median_dt <= 0:
        median_dt = 60.0

    # Count gaps: any diff more than 2x the median
    gap_count = int((diffs > 2 * median_dt).sum())
    # Irregular: more than 5% of diffs vary by >10% from median
    irregular = float((np.abs(diffs - median_dt) / median_dt > 0.1).mean()) > 0.05

    duration = float((ts.iloc[-1] - ts.iloc[0]).total_seconds())

    # Choose display unit
    if median_dt < 60:
        unit, factor = "sec", 1.0
    elif median_dt < 3600:
        unit, factor = "min", 1 / 60.0
    else:
        unit, factor = "hr", 1 / 3600.0

    return TimeContext(
        dt_seconds=median_dt,
        n_samples=len(ts),
        duration_seconds=duration,
        irregular=irregular,
        gap_count=gap_count,
        display_unit=unit,
        display_factor=factor,
    )
