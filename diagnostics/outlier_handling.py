"""
Outlier handling — removes physically impossible values.
==========================================================

Module 3 of the v3 wrapper. Removes physically impossible values
(OP > 110 %, negative absolute pressure, etc.) and isolated single-sample
spikes. Keeps everything else, including step changes and sustained
excursions, because those are usually real plant events.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .reporting_helpers import _line, _section_header


@dataclass
class OutlierAction:
    loop: str
    column: str
    kind: str            # 'physical', 'spike', 'kept', 'flagged'
    n_samples: int
    detail: str = ""


@dataclass
class OutlierReport:
    actions: List[OutlierAction] = field(default_factory=list)

    def render(self) -> str:
        out = [_section_header("OUTLIER HANDLING REPORT — automatic")]
        out.append("The tool examined every value for physical plausibility "
                   "and statistical consistency. Below is exactly what was "
                   "removed, what was kept, and why. Original file unchanged.\n")
        removed = [a for a in self.actions if a.kind in ("physical", "spike")]
        kept = [a for a in self.actions if a.kind == "kept"]
        flagged = [a for a in self.actions if a.kind == "flagged"]

        if not self.actions:
            out.append("  No outliers detected.\n")
            return "\n".join(out)

        if removed:
            out.append(_line())
            out.append("  REMOVED — physically impossible / single-sample spikes")
            out.append(_line())
            for a in removed:
                kind_label = ("physical impossibility" if a.kind == "physical"
                              else "single-sample spike")
                out.append(f"    {a.loop} / {a.column}: {a.n_samples} value(s) "
                           f"removed — {kind_label}")
                if a.detail:
                    out.append(f"        {a.detail}")
            out.append("")

        if kept:
            out.append(_line())
            out.append("  KEPT — looked unusual but is real plant data")
            out.append(_line())
            out.append("  These values were considered for removal but kept "
                       "because they appear to be genuine events.")
            for a in kept:
                out.append(f"    {a.loop} / {a.column}: {a.detail}")
            out.append("")

        if flagged:
            out.append(_line())
            out.append("  FLAGGED for review — could not decide")
            out.append(_line())
            for a in flagged:
                out.append(f"    {a.loop} / {a.column}: {a.detail}")
            out.append("")

        out.append("""
  PRINCIPLES APPLIED

  • Default: PRESERVE, not REMOVE. If there's any reasonable chance a
    value is real, it is kept.
  • Physical impossibilities (e.g. negative absolute pressure, OP > 100%)
    are removed firmly — there's no scenario where they are real.
  • Single-sample spikes (one bad value with healthy neighbours) are
    replaced by interpolation between the neighbours.
  • Sustained excursions are kept — they may be real upsets that the
    diagnostic should detect.
  • Step changes that coincide with SP changes are kept — these are
    operator setpoint moves, not sensor faults.
""")
        return "\n".join(out)


# Physical limits per signal type (loose — only catch the clearly impossible)
PHYS_LIMITS = {
    "OP":  (-5.0, 110.0),     # OP is %, allow tiny overshoot for clamps
    "PV_temperature": (-273.15, 2000.0),
    "PV_pressure":    (-5.0, 1000.0),
    "PV_flow":        (-1e6, 1e9),
    "PV_level":       (-5.0, 110.0),
    "PV_analyser":    (-1e6, 1e9),
    "PV_default":     (-1e8, 1e8),
}


def _classify_loop_type(loop_name: str) -> str:
    """Best-effort guess of the signal type from the tag prefix."""
    name = loop_name.upper()
    # Pull last segment of dotted tag (e.g. YN.ETH1.15FC311 → 15FC311)
    last = name.split(".")[-1]
    # Grab letters before any digits
    letters = ""
    for ch in last:
        if ch.isalpha():
            letters += ch
        elif ch.isdigit() and letters:
            break
    letters = letters.upper()
    if "T" in letters and "I" in letters:
        return "temperature"
    if "P" in letters and "I" in letters:
        return "pressure"
    if "F" in letters and "I" in letters:
        return "flow"
    if "L" in letters and "I" in letters:
        return "level"
    if "A" in letters and "I" in letters:
        return "analyser"
    return "default"


def handle_outliers(df: pd.DataFrame,
                    suffix_map: Dict[str, Dict[str, str]],
                    skipped_loops: List[str]) -> Tuple[pd.DataFrame, OutlierReport]:
    """Conservative outlier removal."""
    rep = OutlierReport()
    df = df.copy()
    skip = set(skipped_loops)

    for base, mp in suffix_map.items():
        if base in skip:
            continue
        sig_type = _classify_loop_type(base)

        # OP column — apply OP physical limits
        op_col = mp.get("OP")
        if op_col and op_col in df.columns:
            arr = df[op_col].values.astype("float64").copy()
            lo, hi = PHYS_LIMITS["OP"]
            mask = np.isfinite(arr) & ((arr < lo) | (arr > hi))
            n_phys = int(mask.sum())
            if n_phys > 0:
                # Show a few example values
                example_vals = arr[mask][:3]
                detail = (f"observed values: " +
                          ", ".join(f"{v:.1f}" for v in example_vals))
                arr[mask] = np.nan
                df[op_col] = arr
                rep.actions.append(OutlierAction(
                    loop=base, column=op_col, kind="physical",
                    n_samples=n_phys,
                    detail=f"OP must be 0-100%; {detail}"))

        # PV column — apply PV physical limits (signal-type aware)
        pv_col = mp.get("PV")
        sp_col = mp.get("SP")
        if pv_col and pv_col in df.columns:
            arr = df[pv_col].values.astype("float64").copy()
            lo, hi = PHYS_LIMITS.get(f"PV_{sig_type}", PHYS_LIMITS["PV_default"])
            mask = np.isfinite(arr) & ((arr < lo) | (arr > hi))
            n_phys = int(mask.sum())
            if n_phys > 0:
                example_vals = arr[mask][:3]
                detail = ", ".join(f"{v:.2f}" for v in example_vals)
                arr[mask] = np.nan
                df[pv_col] = arr
                rep.actions.append(OutlierAction(
                    loop=base, column=pv_col, kind="physical",
                    n_samples=n_phys,
                    detail=f"PV outside physical limits "
                           f"({sig_type}, range [{lo:.0f}, {hi:.0f}]); "
                           f"examples: {detail}"))

            # Single-sample spike detection (only on PV)
            valid_arr = arr.copy()
            finite = np.isfinite(valid_arr)
            if finite.sum() < 100:
                continue

            # Compute robust scale: median abs deviation around rolling median
            ser = pd.Series(valid_arr)
            roll_med = ser.rolling(window=11, min_periods=3, center=True).median()
            roll_dev = (ser - roll_med).abs()
            mad = roll_dev.median()
            if not np.isfinite(mad) or mad == 0:
                continue
            scale = 1.4826 * mad   # MAD → sigma estimate

            # A point is a candidate spike if:
            #   (1) it's > 8*scale from rolling median  AND
            #   (2) its immediate predecessor and successor are NOT
            #   AND (3) SP didn't change at the same instant.
            sp_arr = (df[sp_col].values.astype("float64")
                      if sp_col and sp_col in df.columns
                      else np.zeros_like(valid_arr))
            sp_change = np.zeros_like(valid_arr, dtype=bool)
            if sp_col and sp_col in df.columns:
                sp_diff = np.abs(np.diff(sp_arr, prepend=sp_arr[0]))
                sp_change = sp_diff > 5 * scale

            spike_idx = []
            for i in range(1, len(valid_arr) - 1):
                if not finite[i] or not finite[i-1] or not finite[i+1]:
                    continue
                rm = roll_med.iloc[i]
                if not np.isfinite(rm):
                    continue
                d_self = abs(valid_arr[i] - rm)
                d_prev = abs(valid_arr[i-1] - rm)
                d_next = abs(valid_arr[i+1] - rm)
                if d_self > 8 * scale and d_prev < 3 * scale and d_next < 3 * scale:
                    if not sp_change[i]:
                        spike_idx.append(i)

            n_spikes = len(spike_idx)
            if n_spikes > 0 and n_spikes < 0.005 * finite.sum():
                # Replace with linear interpolation between neighbours
                example_lines = []
                for i in spike_idx[:3]:
                    example_lines.append(
                        f"value {valid_arr[i]:.2f} (neighbours "
                        f"{valid_arr[i-1]:.2f}, {valid_arr[i+1]:.2f})")
                for i in spike_idx:
                    valid_arr[i] = 0.5 * (valid_arr[i-1] + valid_arr[i+1])
                df[pv_col] = valid_arr
                rep.actions.append(OutlierAction(
                    loop=base, column=pv_col, kind="spike",
                    n_samples=n_spikes,
                    detail=f"e.g. {'; '.join(example_lines)}"))
            elif n_spikes >= 0.005 * finite.sum() and n_spikes > 0:
                # Many spike candidates — likely real noisy signal, do NOT
                # remove. Just flag.
                rep.actions.append(OutlierAction(
                    loop=base, column=pv_col, kind="flagged",
                    n_samples=n_spikes,
                    detail=f"{n_spikes} spike-shaped samples found — too many "
                           "to be glitches. Likely real high-noise behaviour. "
                           "Kept as-is."))

    return df, rep
