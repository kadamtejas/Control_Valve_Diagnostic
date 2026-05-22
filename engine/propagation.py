"""
Propagation — cross-loop cause-and-effect analysis.
=====================================================

Layer 3, module 1. Identifies which loops upset which using:

  * cross-correlation lag (best lag and peak |correlation|)
  * Granger causality      (does X help predict Y?)
  * spectral coherence     (frequency-domain similarity)

Combined into a directed list of `PropagationLink` objects.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import warnings

import numpy as np
import pandas as pd
from scipy import signal as sp_signal

from .utils import logger, safe_float, safe_pos, DEFAULTS
from .time_context import TimeContext


def cross_correlation_lag(x: np.ndarray, y: np.ndarray, max_lag: int) -> tuple:
    """Best lag (positive = x leads y) and peak |correlation|."""
    if len(x) < 30 or np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return 0, 0.0
    x = x - np.mean(x)
    y = y - np.mean(y)
    max_lag = min(max_lag, len(x) // 4)
    best = (0, 0.0)
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xx = x[: len(x) - lag]
            yy = y[lag:]
        else:
            xx = x[-lag:]
            yy = y[: len(y) + lag]
        if len(xx) < 10:
            continue
        c = np.corrcoef(xx, yy)[0, 1]
        if not np.isfinite(c):
            continue
        if abs(c) > abs(best[1]):
            best = (lag, c)
    return best


def granger_p_value(driver: np.ndarray, target: np.ndarray, max_lag: int) -> float:
    """
    Returns the smallest p-value across lags 1..max_lag for the test
    H0: driver does NOT Granger-cause target.
    Lower p = stronger evidence of causation.
    """
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except Exception:
        return 1.0
    if len(driver) < 30 or np.std(driver) < 1e-9 or np.std(target) < 1e-9:
        return 1.0
    # Detrend / difference if non-stationary (simple approach: difference)
    d = np.diff(driver)
    t = np.diff(target)
    df = pd.DataFrame({"target": t, "driver": d}).dropna()
    if len(df) < 30 or len(df) <= max_lag * 4:
        return 1.0
    max_lag = min(max_lag, max(2, len(df) // 10))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = grangercausalitytests(df[["target", "driver"]], maxlag=max_lag,
                                        verbose=False)
        ps = [res[k][0]["ssr_ftest"][1] for k in res]
        return float(min(ps)) if ps else 1.0
    except Exception:
        return 1.0


def spectral_coherence_score(x: np.ndarray, y: np.ndarray, fs: float) -> float:
    """Average coherence in the low-frequency band 0.001fs–0.1fs.
       Returns 0–100."""
    if len(x) < 64 or np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return 0.0
    nperseg = min(len(x) // 4, 256)
    nperseg = max(nperseg, 32)
    try:
        f, Cxy = sp_signal.coherence(x, y, fs=fs, nperseg=nperseg)
    except Exception:
        return 0.0
    band = (f > fs * 0.001) & (f < fs * 0.1)
    if not np.any(band):
        return 0.0
    return round(float(np.mean(Cxy[band])) * 100, 1)


@dataclass
class PropagationLink:
    source: str
    target: str
    source_unit: str
    target_unit: str
    same_unit: bool
    cc_correlation: float
    cc_lag_samples: int
    cc_lag_str: str
    granger_p: float
    coherence_score: float
    raw_score: float        # before cross-unit downweight
    combined_score: float   # after cross-unit downweight


def propagation_analysis(loop_data: dict, df: pd.DataFrame, tc: TimeContext,
                         unit_mapping: dict, config: dict,
                         selection=None) -> list:
    """
    Compute pairwise propagation indicators between all loops.

    Cross-unit pairs (where the two loops belong to different plant units
    per the UNIT_MAPPING sheet) are tested but their combined score is
    multiplied by CROSS_UNIT_DOWNWEIGHT (default 0.5) — physically distant
    loops correlated by chance get pushed below the reporting threshold,
    while genuinely strong cross-unit links still surface.

    Loops not in the unit mapping are placed in unit 'Unknown'; pairs
    involving an Unknown loop are treated as same-unit (no downweight)
    so we don't penalise users who haven't filled the sheet in fully.
    """
    names = list(loop_data.keys())
    if len(names) < 2:
        return []

    # Build PV array dict (mode-filtered, finite)
    pv_dict = {}
    for n in names:
        pv = df[loop_data[n]["PV"]].values.astype(float)
        finite = np.isfinite(pv)
        if finite.sum() > 30:
            pv_dict[n] = pv[finite]

    # All-pairs (we no longer use a topology filter)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
             if a in pv_dict and b in pv_dict]

    fs = 1.0 / max(tc.dt_seconds, 1e-6)
    max_lag = int(safe_float(config.get("MAX_LAG_SAMPLES", 50)))
    g_max_lag = int(safe_float(config.get("GRANGER_MAX_LAG", 5)))
    cross_unit_w = safe_float(config.get("CROSS_UNIT_DOWNWEIGHT", 0.5))

    # Method gates (None selection = all enabled)
    use_cc = selection is None or selection.prop_cross_correlation
    use_granger = selection is None or selection.prop_granger
    use_coh = selection is None or selection.prop_coherence
    # Re-normalise weights over enabled methods
    raw_w = np.array([0.4 if use_cc else 0.0,
                      0.3 if use_granger else 0.0,
                      0.3 if use_coh else 0.0])
    if raw_w.sum() <= 0:
        return []
    w_cc, w_g, w_coh = raw_w / raw_w.sum()

    def _unit_of(loop):
        return unit_mapping.get(loop, "Unknown")

    links = []
    for a, b in pairs:
        x = pv_dict[a]
        y = pv_dict[b]
        n_use = min(len(x), len(y))
        if n_use < 50:
            continue
        x = x[:n_use]
        y = y[:n_use]
        # Always compute cross-correlation to get the lag/direction (cheap and
        # used elsewhere). If user disabled CC scoring, its weight is 0 above.
        lag, corr = cross_correlation_lag(x, y, max_lag)
        if lag >= 0:
            src, tgt = a, b
            lag_signed = lag
            xs, ys = x, y
        else:
            src, tgt = b, a
            lag_signed = -lag
            xs, ys = y, x
        gp = granger_p_value(xs, ys, g_max_lag) if use_granger else 1.0
        coh = spectral_coherence_score(xs, ys, fs) if use_coh else 0.0
        cc_score = abs(corr) * 100 if use_cc else 0.0
        granger_score = (max(0.0, 100.0 * (1.0 - gp / 0.05)) if gp < 0.05 else 0.0) if use_granger else 0.0
        raw = round(w_cc * cc_score + w_g * granger_score + w_coh * coh, 1)

        u_src = _unit_of(src)
        u_tgt = _unit_of(tgt)
        # Same-unit if either loop is Unknown OR they're in the same unit
        same_unit = (u_src == u_tgt) or (u_src == "Unknown") or (u_tgt == "Unknown")
        combined = raw if same_unit else round(raw * cross_unit_w, 1)

        links.append(PropagationLink(
            source=src, target=tgt,
            source_unit=u_src, target_unit=u_tgt,
            same_unit=same_unit,
            cc_correlation=round(corr, 3),
            cc_lag_samples=lag_signed,
            cc_lag_str=tc.samples_to_display_str(lag_signed),
            granger_p=round(gp, 4),
            coherence_score=coh,
            raw_score=raw,
            combined_score=combined,
        ))
    min_score = safe_float(config.get("PROP_CONF_MIN", 50))
    links = [l for l in links if l.combined_score >= min_score]
    links.sort(key=lambda l: -l.combined_score)
    return links
