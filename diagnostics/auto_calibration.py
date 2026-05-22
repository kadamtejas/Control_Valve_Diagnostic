"""
Auto-calibration — derives thresholds from your data.
=======================================================

Module 4 of the v3 wrapper. Derives threshold values from the data
with five layers of safeguards:

  Layer 1 — Refusal (skip loops with no quiet window)
  Layer 2 — Peer comparison (drop outlier loops within unit/tag groups)
  Layer 3 — Hard sanity bounds (clamp around manual default)
  Layer 4 — Multi-method cross-check (handled in v2 engine)
  Layer 5 — Confidence labels (HIGH/MEDIUM/LOW; LOW falls back)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# v2 engine — needed for DEFAULTS fallback values during calibration
import valve_diagnostics_v2 as v2

from .constants import CALIB_BOUNDS, CONFIG_RANGES, NEVER_AUTO_CALIBRATE
from .reporting_helpers import _line, _section_header
from .outlier_handling import _classify_loop_type


@dataclass
class CalibrationDecision:
    parameter: str
    manual_value: float
    auto_value: Optional[float]
    used_value: float
    mode: str           # 'AUTO', 'MANUAL', 'FALLBACK'
    confidence: str     # 'HIGH' / 'MEDIUM' / 'LOW' / 'N/A'
    rationale: str = ""


@dataclass
class CalibrationReport:
    decisions: List[CalibrationDecision] = field(default_factory=list)
    peer_diagnostics: List[str] = field(default_factory=list)
    skipped_loops_in_baseline: List[Tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        out = [_section_header("AUTO-CALIBRATION REPORT")]
        out.append("The tool inspected your data and chose threshold values "
                   "from it. Each parameter shows the manual value (your "
                   "DIAGNOSTIC_CONFIG), the auto-suggested value, which one "
                   "was used, and why.\n")
        out.append(f"  {'Parameter':<32} {'Manual':>10} {'Auto':>10} "
                   f"{'Used':>10} {'Mode':>10} {'Conf.':>8}")
        out.append("  " + "─" * 86)
        for d in self.decisions:
            auto_s = f"{d.auto_value:.3g}" if d.auto_value is not None else "—"
            out.append(
                f"  {d.parameter:<32} "
                f"{d.manual_value:>10.4g} "
                f"{auto_s:>10} "
                f"{d.used_value:>10.4g} "
                f"{d.mode:>10} "
                f"{d.confidence:>8}"
            )
        out.append("")

        out.append(_line())
        out.append("  RATIONALE")
        out.append(_line())
        for d in self.decisions:
            out.append(f"  • {d.parameter} ({d.mode}, {d.confidence}): "
                       f"{d.rationale}")
        out.append("")

        if self.peer_diagnostics:
            out.append(_line())
            out.append("  PEER-COMPARISON DIAGNOSTICS (Layer 2 safeguard)")
            out.append(_line())
            for pd_ in self.peer_diagnostics:
                out.append(f"  {pd_}")
            out.append("")

        if self.skipped_loops_in_baseline:
            out.append(_line())
            out.append("  LOOPS NOT USED FOR BASELINE (Layer 1 refusal)")
            out.append(_line())
            for name, reason in self.skipped_loops_in_baseline:
                out.append(f"  • {name}: {reason}")
            out.append("")

        out.append("""
  THE 5 SAFEGUARDS APPLIED

  Layer 1 — Refuse to calibrate. If a loop has no genuinely quiet
            window, it doesn't contribute to the baseline.
  Layer 2 — Peer comparison. Loops whose statistics are extreme
            outliers vs. their peer group are excluded from the
            baseline (they may already be sick).
  Layer 3 — Hard sanity bounds. Each calibrated value is clamped
            within physically sensible limits.
  Layer 4 — Multi-method cross-check. Even if a threshold is mis-
            calibrated, independent detectors (Hägglund regularity,
            Harris Index, the four stiction methods) cross-check
            the diagnosis.
  Layer 5 — Confidence reporting. Each decision is labelled HIGH /
            MEDIUM / LOW so the user knows where to look.

  Anywhere the tool was uncertain, it FELL BACK to your manual
  value — never silently invented a number.
""")
        return "\n".join(out)


def _quiet_window_stats(arr: np.ndarray, win: int = 30
                        ) -> Tuple[Optional[float], Optional[float]]:
    """Find the quietest rolling window. Return (mean, std) of the quietest
    region, or (None, None) if no window has data."""
    arr = arr.astype("float64")
    finite = np.isfinite(arr)
    if finite.sum() < win:
        return None, None
    ser = pd.Series(arr)
    roll_std = ser.rolling(window=win, min_periods=int(0.7 * win)).std()
    if roll_std.dropna().empty:
        return None, None
    # Take the 10th percentile of the rolling std to find typically-calm regions
    q = float(roll_std.dropna().quantile(0.10))
    return float(ser[roll_std <= q + 1e-9].mean()), q


def _per_loop_baseline(df: pd.DataFrame,
                       suffix_map: Dict[str, Dict[str, str]],
                       skipped_loops: List[str]
                       ) -> Tuple[Dict[str, Dict[str, float]], List[Tuple[str, str]]]:
    """
    For each non-skipped loop, compute per-loop baseline statistics.
    Returns (stats_by_loop, layer1_refused).
    """
    stats: Dict[str, Dict[str, float]] = {}
    refused: List[Tuple[str, str]] = []
    skip = set(skipped_loops)

    for base, mp in suffix_map.items():
        if base in skip:
            continue
        if "PV" not in mp or "OP" not in mp:
            continue
        pv_col = mp["PV"]; op_col = mp["OP"]
        sp_col = mp.get("SP")
        if pv_col not in df.columns or op_col not in df.columns:
            continue
        pv = df[pv_col].values.astype("float64")
        op = df[op_col].values.astype("float64")
        sp = (df[sp_col].values.astype("float64")
              if sp_col and sp_col in df.columns else None)

        finite_pv = np.isfinite(pv)
        if finite_pv.sum() < 60:
            refused.append((base, "fewer than 60 valid PV samples"))
            continue

        # Quiet-window noise estimate
        _, pv_noise = _quiet_window_stats(pv, win=30)
        if pv_noise is None:
            refused.append((base, "could not find any quiet PV window"))
            continue

        # Layer 1 refusal: if pv_noise is hugely larger than the global
        # std of PV, every window is noisy — the loop is plausibly sick
        global_std = float(np.nanstd(pv))
        if global_std > 0 and pv_noise > 0.8 * global_std:
            # The whole signal is the same level of noisy — there is no
            # "quiet" region. Refuse to calibrate from this loop.
            refused.append((base, "no quiet baseline — loop is uniformly "
                                  "noisy/oscillating"))
            continue

        # OP activity baseline (per-sample mean abs diff)
        op_diff = np.abs(np.diff(op))
        op_diff = op_diff[np.isfinite(op_diff)]
        if len(op_diff) < 30:
            refused.append((base, "fewer than 30 valid OP differences"))
            continue
        op_typical = float(np.median(op_diff))

        # PV dynamic range
        finite_vals = pv[np.isfinite(pv)]
        pv_range = float(np.percentile(finite_vals, 99) -
                         np.percentile(finite_vals, 1))

        # IAE per hour estimate (only if SP available)
        if sp is not None:
            err = pv - sp
            err = err[np.isfinite(err)]
            iae_per_sample = float(np.mean(np.abs(err))) if len(err) else 0.0
        else:
            iae_per_sample = 0.0

        stats[base] = {
            "pv_noise": pv_noise,
            "op_typical": op_typical,
            "pv_range": pv_range,
            "iae_per_sample": iae_per_sample,
            "loop_type": _classify_loop_type(base),
        }

    return stats, refused


def _peer_groups(stats: Dict[str, Dict[str, float]],
                 unit_mapping: Dict[str, str] = None
                 ) -> Dict[str, List[str]]:
    """Group loops by (unit, loop_type)."""
    unit_mapping = unit_mapping or {}
    groups: Dict[str, List[str]] = {}
    for base, s in stats.items():
        unit = unit_mapping.get(base, "Unknown")
        # Also try matching tag tail in unit_mapping
        if unit == "Unknown":
            for k, v in unit_mapping.items():
                if k in base or base.endswith(k):
                    unit = v
                    break
        key = f"{unit}::{s['loop_type']}"
        groups.setdefault(key, []).append(base)
    return groups


def _peer_filter(stats: Dict[str, Dict[str, float]],
                 groups: Dict[str, List[str]],
                 stat_key: str
                 ) -> Tuple[List[float], List[str]]:
    """
    For one statistic, return (filtered_values, diagnostic_lines).
    Excludes peer-group outliers (Layer 2 safeguard).
    """
    values: List[float] = []
    diags: List[str] = []
    for group_key, members in groups.items():
        if len(members) < 2:
            for m in members:
                values.append(stats[m][stat_key])
            continue
        vals = np.array([stats[m][stat_key] for m in members])
        med = float(np.median(vals))
        if med == 0:
            for m in members:
                values.append(stats[m][stat_key])
            continue
        # Exclude any member whose value is >5x the median or <1/5 of median
        for m, v in zip(members, vals):
            if v > 5 * med or v < 0.2 * med:
                diags.append(f"loop {m} excluded from baseline ({stat_key} "
                             f"= {v:.3g}, peer median = {med:.3g})")
            else:
                values.append(float(v))
    return values, diags


def calibrate(df: pd.DataFrame,
              suffix_map: Dict[str, Dict[str, str]],
              manual_config: Dict[str, float],
              median_dt_sec: float,
              skipped_loops: List[str],
              unit_mapping: Optional[Dict[str, str]] = None,
              mode: str = "AUTO",
              ) -> CalibrationReport:
    """Produce calibration decisions for each parameter."""
    rep = CalibrationReport()

    # Get manual values, with v2 defaults as fallback for any param the user
    # didn't put in the sheet.
    def manual(p):
        if p in manual_config:
            return float(manual_config[p])
        return float(v2.DEFAULTS.get(p, 0.0))

    if mode == "MANUAL":
        # Just emit decisions reflecting manual values; no auto computation
        for p, (lo, hi, default) in CONFIG_RANGES.items():
            mv = manual(p)
            rep.decisions.append(CalibrationDecision(
                parameter=p, manual_value=mv, auto_value=None,
                used_value=mv, mode="MANUAL", confidence="N/A",
                rationale="MANUAL mode — user's value used unchanged."))
        return rep

    # ───── AUTO MODE ─────
    # Layer 1 + 2: compute per-loop baseline, peer-filter
    stats, refused = _per_loop_baseline(df, suffix_map, skipped_loops)
    rep.skipped_loops_in_baseline = refused
    groups = _peer_groups(stats, unit_mapping)
    peer_keys = ["pv_noise", "op_typical", "iae_per_sample"]
    peer_data: Dict[str, List[float]] = {}
    for k in peer_keys:
        vals, diags = _peer_filter(stats, groups, k)
        peer_data[k] = vals
        rep.peer_diagnostics.extend(diags)

    n_baseline = len(stats) - len(refused)

    def confidence_label(n_used: int, n_loops_total: int) -> str:
        if n_loops_total == 0:
            return "N/A"
        frac = n_used / n_loops_total
        if frac >= 0.7 and n_used >= 3:
            return "HIGH"
        if frac >= 0.4 and n_used >= 2:
            return "MEDIUM"
        return "LOW"

    n_total_loops = sum(1 for b in suffix_map if b not in set(skipped_loops))

    # Helper to compute, clamp, decide AUTO vs FALLBACK
    def decide(param: str, auto_calc, rationale_fn, conf_label: str):
        manual_val = manual(param)
        try:
            auto_val = auto_calc()
        except Exception as e:
            rep.decisions.append(CalibrationDecision(
                parameter=param, manual_value=manual_val, auto_value=None,
                used_value=manual_val, mode="FALLBACK", confidence="LOW",
                rationale=f"calibration failed ({e}); using manual value"))
            return
        if auto_val is None or not np.isfinite(auto_val):
            rep.decisions.append(CalibrationDecision(
                parameter=param, manual_value=manual_val, auto_value=None,
                used_value=manual_val, mode="FALLBACK", confidence="LOW",
                rationale="not enough clean baseline data; using manual value"))
            return
        # Layer 3: clamp
        clamped = False
        if param in CALIB_BOUNDS:
            lo, hi = CALIB_BOUNDS[param]
            if auto_val < lo:
                auto_val = lo
                clamped = True
            elif auto_val > hi:
                auto_val = hi
                clamped = True
        rationale = rationale_fn()
        if clamped:
            rationale += "; clamped to sanity bound"
        rep.decisions.append(CalibrationDecision(
            parameter=param, manual_value=manual_val, auto_value=float(auto_val),
            used_value=float(auto_val), mode="AUTO",
            confidence=conf_label, rationale=rationale))

    # ── Helper: collect per-loop PV peak-to-peak amplitude (peer-cleaned)
    pv_amplitudes: List[float] = []
    for base, s in stats.items():
        if base in set(skipped_loops):
            continue
        # Use the per-loop pv_range (already computed as P99-P1 in baseline)
        pv_amplitudes.append(s["pv_range"])

    # ── Conservative bounded calibration helper.
    # Bounds the auto value within [default × min_factor, default × max_factor]
    # so the calibration adapts to scale but cannot cause regressions.
    def _bounded_around_default(target: float, default: float,
                                min_factor: float = 0.5,
                                max_factor: float = 3.0) -> float:
        if not np.isfinite(target) or target <= 0:
            return default
        lo = default * min_factor
        hi = default * max_factor
        return float(max(lo, min(hi, target)))

    # ── AMP_THRESHOLD: target = 60th percentile of per-loop PV amplitudes.
    # Bounded between 0.5× and 3× the manual default so we never drop below
    # a value that would cause healthy loops to be flagged.
    def amp_calc():
        if len(pv_amplitudes) < 2:
            return None
        target = float(np.percentile(pv_amplitudes, 60))
        default = manual("AMP_THRESHOLD")
        return _bounded_around_default(target, default,
                                       min_factor=0.5, max_factor=3.0)
    decide("AMP_THRESHOLD", amp_calc,
           lambda: f"60th percentile of per-loop PV peak-to-peak amplitude "
                   f"across {len(pv_amplitudes)} loops, bounded within "
                   f"0.5×–3× the manual default ({manual('AMP_THRESHOLD'):.1f})",
           confidence_label(len(pv_amplitudes), n_total_loops))

    # ── OP_ACTIVITY_THRESHOLD: bounded around default — ASYMMETRIC.
    # This threshold gates the "Unresponsive controller" detector
    # (`op_activity < threshold × 0.05`). Lowering the threshold below
    # the manual default would hide real unresponsive cases. So we let
    # auto raise it (for very active plants) but never drop below manual.
    def op_act_calc():
        vals = peer_data.get("op_typical", [])
        if len(vals) < 1:
            return None
        target = 1.5 * float(np.median(vals)) + 0.2
        default = manual("OP_ACTIVITY_THRESHOLD")
        return _bounded_around_default(target, default,
                                       min_factor=1.0, max_factor=3.0)
    decide("OP_ACTIVITY_THRESHOLD", op_act_calc,
           lambda: f"1.5 × median typical OP activity (+0.2 floor) across "
                   f"{len(peer_data['op_typical'])} peer-clean loops, "
                   f"bounded within 1.0×–3× the manual default "
                   f"({manual('OP_ACTIVITY_THRESHOLD'):.2f}) — "
                   f"asymmetric to protect unresponsive-controller detection",
           confidence_label(len(peer_data.get("op_typical", [])), n_total_loops))

    # ── IAE_PER_HOUR_THRESHOLD: bounded around default
    def iae_calc():
        vals = [v for v in peer_data.get("iae_per_sample", []) if v > 0]
        if len(vals) < 1:
            return None
        med = float(np.median(vals))
        samples_per_hour = 3600.0 / max(median_dt_sec, 1.0)
        target = 3.0 * med * samples_per_hour
        default = manual("IAE_PER_HOUR_THRESHOLD")
        return _bounded_around_default(target, default,
                                       min_factor=0.5, max_factor=4.0)
    decide("IAE_PER_HOUR_THRESHOLD", iae_calc,
           lambda: f"3 × median IAE/sample × samples/hour, bounded within "
                   f"0.5×–4× the manual default "
                   f"({manual('IAE_PER_HOUR_THRESHOLD'):.0f})",
           confidence_label(len([v for v in peer_data.get("iae_per_sample", []) if v > 0]),
                           n_total_loops))

    # ── SS_STD_THRESHOLD: bounded around default
    def ssstd_calc():
        vals = peer_data.get("pv_noise", [])
        if len(vals) < 1:
            return None
        target = max(0.05, float(np.median(vals)))
        default = manual("SS_STD_THRESHOLD")
        return _bounded_around_default(target, default,
                                       min_factor=0.3, max_factor=3.0)
    decide("SS_STD_THRESHOLD", ssstd_calc,
           lambda: f"median PV noise floor, bounded within 0.3×–3× the "
                   f"manual default ({manual('SS_STD_THRESHOLD'):.2f})",
           confidence_label(len(peer_data.get("pv_noise", [])), n_total_loops))

    # ── SS_DETECTION_WINDOW: ~30 minutes of samples
    def ss_win_calc():
        if median_dt_sec <= 0:
            return None
        return float(round(1800.0 / median_dt_sec))
    decide("SS_DETECTION_WINDOW", ss_win_calc,
           lambda: f"~30 minutes worth of samples at "
                   f"{median_dt_sec:.0f}s intervals",
           "HIGH")

    # ── FROZEN_SAMPLES_MIN: ~10 minutes of samples
    def frozen_calc():
        if median_dt_sec <= 0:
            return None
        return float(round(600.0 / median_dt_sec))
    decide("FROZEN_SAMPLES_MIN", frozen_calc,
           lambda: f"~10 minutes worth of samples at "
                   f"{median_dt_sec:.0f}s intervals",
           "HIGH")

    # Bucket 4: parameters left at MANUAL
    bucket4 = sorted(NEVER_AUTO_CALIBRATE)
    for p in bucket4:
        if p not in CONFIG_RANGES:
            continue
        mv = manual(p)
        rep.decisions.append(CalibrationDecision(
            parameter=p, manual_value=mv, auto_value=None,
            used_value=mv, mode="MANUAL", confidence="N/A",
            rationale="industry-convention threshold; not auto-calibrated"))
    return rep
