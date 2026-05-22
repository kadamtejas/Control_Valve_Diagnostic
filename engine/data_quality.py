"""
Data quality — per-loop quality assessment and AUTO/CAS mode filter.
=====================================================================

Layer 1, module 3. Detects:

  * frozen sensors          (long runs of identical samples)
  * quantisation             (too few unique values in a window)
  * compression artefacts    (long flat segments, PI/IP21-style)
  * outliers / NaNs / gaps

Also exposes `apply_mode_filter` which masks each loop's PV/OP/SP arrays
to only the AUTO/CAS samples — the only samples meaningful for analysis.
"""

from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

from .utils import logger, safe_float, safe_pos, DEFAULTS
from .input_loading import (
    _MODE_ANALYZABLE,
    _MODE_DEFAULT_MAPPING,
    _classify_mode_value,
)


@dataclass
class DataQualityReport:
    """Per-loop data quality findings. All booleans are 'is this a problem?'"""
    n_samples: int = 0
    n_finite: int = 0
    pct_missing: float = 0.0
    pv_unique_values: int = 0
    is_quantised: bool = False
    longest_frozen_run: int = 0
    is_frozen: bool = False
    compression_fraction: float = 0.0
    is_compressed: bool = False
    n_outliers: int = 0
    pct_outliers: float = 0.0
    issues: list = field(default_factory=list)
    severity: str = "OK"   # OK / WARN / FAIL

    def summary(self) -> str:
        if not self.issues:
            return "Data quality: OK"
        return "Data quality issues: " + "; ".join(self.issues)


def assess_data_quality(pv: np.ndarray, config: dict) -> DataQualityReport:
    rep = DataQualityReport()
    rep.n_samples = len(pv)
    finite_mask = np.isfinite(pv)
    rep.n_finite = int(finite_mask.sum())
    rep.pct_missing = round(100.0 * (1 - rep.n_finite / max(rep.n_samples, 1)), 2)

    pv_clean = pv[finite_mask]
    if len(pv_clean) == 0:
        rep.issues.append("All PV values missing/non-finite")
        rep.severity = "FAIL"
        return rep

    # Quantisation
    rep.pv_unique_values = int(len(np.unique(np.round(pv_clean, 6))))
    qmax = int(safe_pos(config.get("QUANTISATION_UNIQUE_VALS_MAX", 20)))
    if rep.pv_unique_values <= qmax and (np.max(pv_clean) - np.min(pv_clean)) > 0:
        rep.is_quantised = True
        rep.issues.append(f"PV is quantised ({rep.pv_unique_values} unique values)")

    # Frozen sensor
    if len(pv_clean) > 1:
        diffs = np.diff(pv_clean)
        # find longest run of zeros
        runs = []
        run = 0
        for d in diffs:
            if d == 0:
                run += 1
            else:
                if run > 0:
                    runs.append(run)
                run = 0
        if run > 0:
            runs.append(run)
        rep.longest_frozen_run = max(runs) if runs else 0
        fmin = int(safe_pos(config.get("FROZEN_SAMPLES_MIN", 10)))
        if rep.longest_frozen_run >= fmin:
            rep.is_frozen = True
            rep.issues.append(f"Frozen sensor (max run = {rep.longest_frozen_run} samples)")

    # Compression artefact (Choudhury & Shah simplified):
    # Fraction of points that are part of a flat run of length >= 3
    # bracketed by jumps. PI-style compression produces this pattern.
    if len(pv_clean) > 5:
        flat_pts = 0
        total_pts = len(pv_clean)
        i = 0
        while i < total_pts - 1:
            j = i
            while j < total_pts - 1 and pv_clean[j + 1] == pv_clean[i]:
                j += 1
            run_len = j - i + 1
            if run_len >= 3:
                flat_pts += run_len
            i = j + 1
        rep.compression_fraction = round(flat_pts / total_pts, 3)
        cmax = safe_float(config.get("COMPRESSION_FLAT_FRACTION_MAX", 0.30))
        if rep.compression_fraction > cmax:
            rep.is_compressed = True
            rep.issues.append(
                f"Possible compression artefact ({100*rep.compression_fraction:.0f}% flat segments)"
            )

    # Outliers via robust z-score (MAD)
    if len(pv_clean) > 10:
        med = np.median(pv_clean)
        mad = np.median(np.abs(pv_clean - med))
        if mad > 1e-9:
            z = 0.6745 * (pv_clean - med) / mad
            rep.n_outliers = int(np.sum(np.abs(z) > 6))
            rep.pct_outliers = round(100.0 * rep.n_outliers / len(pv_clean), 2)
            if rep.pct_outliers > 1.0:
                rep.issues.append(f"{rep.pct_outliers:.1f}% outliers (|robust-z|>6)")

    if any([rep.is_frozen, rep.is_compressed]):
        rep.severity = "FAIL"
    elif rep.is_quantised or rep.pct_outliers > 1.0 or rep.pct_missing > 5.0:
        rep.severity = "WARN"
    return rep


# ═══════════════════════════════════════════════════════════════════════
# MODE FILTERING & SERVICE FACTOR
# ═══════════════════════════════════════════════════════════════════════

def apply_mode_filter(loop_data: dict, df: pd.DataFrame,
                      mode_mapping: dict = None) -> tuple:
    """
    Returns (pv, op, sp, mode_array, service_factor_pct, n_total, n_used).
    mode_array is the original full-length MODE series (canonical labels);
    pv/op/sp are masked to AUTO/CAS/RCAS samples only.

    `mode_mapping` is a dict mapping raw plant-specific MODE values (as
    uppercase strings) to canonical {AUTO, CAS, RCAS, MAN}. If None, the
    built-in default mapping is used. Unrecognised values are treated as
    MAN with a one-time warning per distinct value.
    """
    pv = df[loop_data["PV"]].values.astype(float)
    op = df[loop_data["OP"]].values.astype(float)
    sp = df[loop_data["SP"]].values.astype(float)
    n_total = len(pv)

    if mode_mapping is None:
        mode_mapping = _MODE_DEFAULT_MAPPING

    if "MODE" in loop_data:
        raw_mode = df[loop_data["MODE"]].values
        mode = np.array([_classify_mode_value(v, mode_mapping) for v in raw_mode])
        in_auto = np.isin(mode, list(_MODE_ANALYZABLE))
        sf = round(100.0 * in_auto.sum() / max(n_total, 1), 1)
    else:
        # No MODE column – assume always AUTO
        in_auto = np.ones(n_total, dtype=bool)
        mode = np.array(["AUTO"] * n_total)
        sf = 100.0

    pv_used = pv[in_auto]
    op_used = op[in_auto]
    sp_used = sp[in_auto]
    return pv, op, sp, mode, sf, n_total, int(in_auto.sum()), in_auto, pv_used, op_used, sp_used
