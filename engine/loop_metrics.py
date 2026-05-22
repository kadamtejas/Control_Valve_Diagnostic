"""
Loop metrics — steady-state detection, basic per-loop stats, dead-time.
========================================================================

Layer 2, module 1. The "easy" per-loop math: steady-state detection,
oscillation amplitude, IAE, OP activity, dead-time estimation.
"""

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd

from .utils import safe_float, safe_pos, DEFAULTS
from .time_context import TimeContext


def detect_steady_state(pv: np.ndarray, sp: np.ndarray, window: int,
                        std_threshold: float) -> np.ndarray:
    """
    Returns boolean mask: True for samples in steady-state regions.
    A sample is steady-state if (a) the SP has not changed in the previous
    `window` samples, and (b) the rolling std of (PV-SP) is below threshold.
    Cao-Rhinehart simplified.
    """
    n = len(pv)
    if n < window * 2:
        return np.ones(n, dtype=bool)

    # SP-change regions: exclude `window` samples after each SP change
    sp_changed = np.zeros(n, dtype=bool)
    sp_diff = np.abs(np.diff(sp, prepend=sp[0]))
    if np.any(sp_diff > 1e-9):
        change_threshold = max(np.std(sp), 0.5)
        for i in np.where(sp_diff > change_threshold)[0]:
            sp_changed[i: min(i + window, n)] = True

    # Rolling std of PV-SP
    err = pv - sp
    err_series = pd.Series(err)
    roll_std = err_series.rolling(window=window, min_periods=window // 2).std().values

    # Adaptive threshold: relative to overall PV std
    pv_std = np.nanstd(pv) if np.nanstd(pv) > 0 else 1.0
    is_steady = roll_std < (std_threshold * pv_std)
    is_steady = np.nan_to_num(is_steady, nan=0).astype(bool)
    is_steady &= ~sp_changed
    return is_steady


# ═══════════════════════════════════════════════════════════════════════
# CORE LOOP METRICS
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LoopMetrics:
    iae_total: float = 0.0
    iae_per_hour: float = 0.0
    iae_per_hour_norm: float = 0.0   # IAE/hr normalised to PV operating range (%)
    pv_amplitude: float = 0.0
    pv_amplitude_pct: float = 0.0   # peak-to-peak as % of |pv_mean| (or pv_range)
    pv_std: float = 0.0
    pv_mean: float = 0.0
    op_activity: float = 0.0
    op_min: float = 0.0
    op_max: float = 100.0
    op_pct_at_zero: float = 0.0      # % time OP < 2%
    op_pct_at_full: float = 0.0      # % time OP > 98%
    op_range_used: float = 0.0
    saturated: bool = False


def compute_loop_metrics(pv, op, sp, tc: TimeContext) -> LoopMetrics:
    m = LoopMetrics()
    n = len(pv)
    if n == 0:
        return m
    err = pv - sp
    m.iae_total = float(np.nansum(np.abs(err)))
    duration_hr = max(n * tc.dt_seconds / 3600.0, 1e-6)
    m.iae_per_hour = round(m.iae_total / duration_hr, 2)
    # Normalised IAE: express IAE/hr as a percentage of the PV operating
    # range so the threshold works at any engineering-unit scale.
    pv_scale = max(abs(float(np.nanmean(pv))), float(np.nanstd(pv)) * 4, 1.0)
    m.iae_per_hour_norm = round(m.iae_per_hour / pv_scale * 100.0, 2)
    m.pv_amplitude = float(np.nanmax(pv) - np.nanmin(pv))
    m.pv_std = float(np.nanstd(pv))
    m.pv_mean = float(np.nanmean(pv))
    # Relative amplitude: percent of |mean|, falling back to a robust scale
    scale = max(abs(m.pv_mean), m.pv_std * 4, 1.0)
    m.pv_amplitude_pct = round(100.0 * m.pv_amplitude / scale, 1)
    if n > 1:
        m.op_activity = float(np.nanmean(np.abs(np.diff(op))))
    m.op_min = float(np.nanmin(op))
    m.op_max = float(np.nanmax(op))
    m.op_range_used = m.op_max - m.op_min
    m.op_pct_at_zero = round(100.0 * np.mean(op < 2.0), 1)
    m.op_pct_at_full = round(100.0 * np.mean(op > 98.0), 1)
    m.saturated = m.op_pct_at_zero > 30 or m.op_pct_at_full > 30
    return m


# ─── Harris Index (Minimum Variance benchmark) ─────────────────────────
def estimate_dead_time_samples(op: np.ndarray, pv: np.ndarray, max_lag: int = 40) -> int:
    """Estimate process dead-time in samples via cross-correlation."""
    if len(op) < 20 or np.std(op) < 1e-9 or np.std(pv) < 1e-9:
        return 1
    op_d = op - np.mean(op)
    pv_d = pv - np.mean(pv)
    max_lag = min(max_lag, len(op) // 4)
    cors = []
    for lag in range(1, max_lag):
        if lag >= len(op):
            break
        c = np.corrcoef(op_d[: -lag], pv_d[lag:])[0, 1]
        cors.append((lag, c if np.isfinite(c) else 0.0))
    if not cors:
        return 1
    best = max(cors, key=lambda x: abs(x[1]))
    return max(int(best[0]), 1)
