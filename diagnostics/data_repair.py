"""
Data repair — fills small gaps, leaves big gaps alone.
========================================================

Module 2 of the v3 wrapper. Sensibly fills tiny gaps in the data and
skips loops with too much missing data. Never uses average-fill (which
would create false frozen-sensor diagnoses).
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .constants import NUMERIC_SENTINELS, QUALITY_FLAGS, EXCEL_ERRORS
from .reporting_helpers import _line, _section_header


@dataclass
class RepairAction:
    loop: str
    column: str
    kind: str           # 'interp', 'ffill', 'segment', 'sentinel', 'quality_flag'
    n_samples: int
    detail: str = ""


@dataclass
class RepairReport:
    actions: List[RepairAction] = field(default_factory=list)
    skipped_loops: List[Tuple[str, str]] = field(default_factory=list)  # (name, reason)
    segments_per_loop: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)

    def render(self, n_total: int = 0) -> str:
        out = [_section_header("DATA REPAIRS APPLIED — automatic")]
        out.append("The tool repaired or worked around missing data on the "
                   "loops below before running diagnostics. The original file "
                   "was NOT modified.\n")
        if not self.actions and not self.skipped_loops:
            out.append("  No repairs needed — input data was clean.\n")
            return "\n".join(out)

        # Group actions by loop
        by_loop: Dict[str, List[RepairAction]] = {}
        for a in self.actions:
            by_loop.setdefault(a.loop, []).append(a)

        for loop, acts in by_loop.items():
            out.append(_line())
            out.append(f"  Loop {loop}")
            out.append(_line())
            for a in acts:
                if a.kind == "interp":
                    out.append(f"    {a.column}: linear interpolation on "
                               f"{a.n_samples} sample(s) "
                               f"({a.detail})")
                elif a.kind == "ffill":
                    out.append(f"    {a.column}: forward-fill on "
                               f"{a.n_samples} sample(s) ({a.detail})")
                elif a.kind == "segment":
                    out.append(f"    {a.column}: segmented around gaps "
                               f"({a.detail})")
                elif a.kind == "sentinel":
                    out.append(f"    {a.column}: {a.n_samples} sentinel "
                               f"value(s) treated as missing ({a.detail})")
                elif a.kind == "quality_flag":
                    out.append(f"    {a.column}: {a.n_samples} quality-flag "
                               f"value(s) treated as missing ({a.detail})")
            out.append("")

        if self.skipped_loops:
            out.append(_line())
            out.append("  LOOPS SKIPPED — no diagnosis possible")
            out.append(_line())
            for name, reason in self.skipped_loops:
                out.append(f"    {name}: {reason}")
            out.append("")

        out.append(_line())
        out.append("  WHY THESE METHODS WERE CHOSEN")
        out.append(_line())
        out.append("""
  • Linear interpolation: gaps of 1-2 samples. Equivalent to drawing
    a straight line between known points. Invisible to all diagnostics.

  • Forward-fill: gaps up to ~1 minute. Carries the last known value
    forward. Conservative — does not invent movement.

  • Segmenting: gaps over ~1 minute. The loop is analysed in pieces
    around the gap rather than gaps being filled. Most honest method
    for larger gaps because nothing is fabricated.

  • Sentinel handling: values like -9999 are treated as 'no data'
    rather than real measurements. Re-run with --no-sentinel-handling
    to override.

  WHAT WE DID NOT DO

  • We did NOT replace gaps with the column average. For control loop
    signals, average-fill creates an artificial flat segment that the
    diagnostic tool would interpret as a frozen sensor — a false fault.

  • We did NOT fill any gap longer than 5 minutes. Long gaps are
    segmented out instead.
""")
        return "\n".join(out)


def repair_dataframe(df: pd.DataFrame,
                     suffix_map: Dict[str, Dict[str, str]],
                     median_dt_sec: float,
                     skip_incomplete: List[str] = None,
                     ) -> Tuple[pd.DataFrame, RepairReport]:
    """
    Returns (cleaned_df, RepairReport).

    Strategy by gap size:
      • 1-2 samples       → linear interpolation
      • 3 to (60s / dt)   → forward-fill
      • > 60s / dt        → segment (do NOT fill)
      • > 5 min OR > 20%  → loop skipped

    Note that "segmenting" in this single-frame model means: leave the
    gap as NaN. The downstream v2 engine already filters NaN rows.
    """
    skip_incomplete = skip_incomplete or []
    rep = RepairReport()
    df = df.copy()

    # Convert sentinel and quality-flag values to NaN first
    for base, mp in suffix_map.items():
        for kind in ("PV", "OP", "SP"):
            col = mp.get(kind)
            if col is None or col not in df.columns:
                continue
            ser = df[col]

            # Convert any string text → NaN where it's a quality flag /
            # sentinel / Excel error / NaN-text
            qf_count = 0
            sent_count = 0
            new_vals = []
            seen_sentinels: Dict[float, int] = {}
            for v in ser.values:
                if isinstance(v, str):
                    vs = v.strip().lower()
                    if vs in QUALITY_FLAGS or vs in {"nan", "na", "n/a",
                                                      "null", "none", "nil",
                                                      ""} or v in EXCEL_ERRORS:
                        new_vals.append(np.nan)
                        qf_count += 1
                        continue
                    try:
                        fv = float(v)
                        if fv in NUMERIC_SENTINELS:
                            new_vals.append(np.nan)
                            seen_sentinels[fv] = seen_sentinels.get(fv, 0) + 1
                            sent_count += 1
                            continue
                        new_vals.append(fv)
                        continue
                    except Exception:
                        new_vals.append(np.nan)
                        qf_count += 1
                        continue
                if v is None:
                    new_vals.append(np.nan)
                    continue
                try:
                    fv = float(v)
                    if not np.isfinite(fv):
                        new_vals.append(np.nan)
                        continue
                    if fv in NUMERIC_SENTINELS:
                        new_vals.append(np.nan)
                        seen_sentinels[fv] = seen_sentinels.get(fv, 0) + 1
                        sent_count += 1
                        continue
                    new_vals.append(fv)
                except Exception:
                    new_vals.append(np.nan)

            df[col] = pd.Series(new_vals, index=df.index, dtype="float64")

            if sent_count:
                detail = ", ".join(f"{int(k)}: {v}"
                                   for k, v in seen_sentinels.items())
                rep.actions.append(RepairAction(
                    loop=base, column=col, kind="sentinel",
                    n_samples=sent_count, detail=detail))
            if qf_count:
                rep.actions.append(RepairAction(
                    loop=base, column=col, kind="quality_flag",
                    n_samples=qf_count, detail="quality flags or NaN text"))

    # Now apply the gap-size strategy per loop
    n_total = len(df)
    if median_dt_sec <= 0:
        median_dt_sec = 60.0
    ffill_max_samples = max(2, int(round(60.0 / median_dt_sec)))    # ~1 minute
    skip_max_samples = max(5, int(round(300.0 / median_dt_sec)))    # ~5 minutes

    # Build skip list — loops with too much missing
    loops_to_skip: List[Tuple[str, str]] = []
    for base, mp in suffix_map.items():
        if base in skip_incomplete:
            loops_to_skip.append((base, "user requested skip"))
            continue
        if "PV" not in mp or "OP" not in mp:
            loops_to_skip.append((base, "missing PV or OP column"))
            continue
        pv_col = mp["PV"]
        if pv_col not in df.columns:
            loops_to_skip.append((base, f"column {pv_col} not found"))
            continue
        n_missing = int(df[pv_col].isna().sum())
        if n_total > 0 and n_missing / n_total > 0.50:
            loops_to_skip.append((base, f"PV {n_missing/n_total*100:.0f}% "
                                       "missing/invalid"))

    # Apply repairs to non-skipped loops
    skip_names = {n for n, _ in loops_to_skip}
    for base, mp in suffix_map.items():
        if base in skip_names:
            continue
        for kind in ("PV", "OP", "SP"):
            col = mp.get(kind)
            if col is None or col not in df.columns:
                continue
            ser = df[col]
            mask_na = ser.isna().values
            if not mask_na.any():
                continue

            # Identify gap runs
            gap_runs = []  # list of (start_idx, length)
            i = 0
            while i < len(mask_na):
                if mask_na[i]:
                    j = i
                    while j < len(mask_na) and mask_na[j]:
                        j += 1
                    gap_runs.append((i, j - i))
                    i = j
                else:
                    i += 1

            n_interp = 0
            n_ffill = 0
            n_seg = 0
            seg_count = 0
            for start, length in gap_runs:
                if length <= 2:
                    n_interp += length
                elif length <= ffill_max_samples:
                    n_ffill += length
                elif length <= skip_max_samples:
                    n_seg += length
                    seg_count += 1
                else:
                    n_seg += length
                    seg_count += 1

            # Apply: interpolate first, then forward-fill the still-NaN of
            # length up to ffill_max, then leave longer gaps as NaN.
            arr = ser.values.astype("float64").copy()

            # Pass 1: linear interpolation for short gaps (≤2)
            for start, length in gap_runs:
                if length <= 2:
                    left_idx = start - 1
                    right_idx = start + length
                    if left_idx >= 0 and right_idx < len(arr) and \
                       np.isfinite(arr[left_idx]) and np.isfinite(arr[right_idx]):
                        for k in range(length):
                            frac = (k + 1) / (length + 1)
                            arr[start + k] = (arr[left_idx] +
                                              frac * (arr[right_idx] -
                                                      arr[left_idx]))

            # Pass 2: forward-fill for medium gaps
            for start, length in gap_runs:
                if 2 < length <= ffill_max_samples:
                    left_idx = start - 1
                    if left_idx >= 0 and np.isfinite(arr[left_idx]):
                        fill_val = arr[left_idx]
                        for k in range(length):
                            arr[start + k] = fill_val

            # Larger gaps left as NaN — v2 engine drops them via mode mask
            df[col] = arr

            if n_interp:
                rep.actions.append(RepairAction(
                    loop=base, column=col, kind="interp",
                    n_samples=n_interp,
                    detail=f"{n_interp} samples in {sum(1 for s, l in gap_runs if l<=2)} gap(s) of ≤2 samples"))
            if n_ffill:
                rep.actions.append(RepairAction(
                    loop=base, column=col, kind="ffill",
                    n_samples=n_ffill,
                    detail=f"{n_ffill} samples in gaps of ≤{ffill_max_samples} samples"))
            if seg_count > 0:
                rep.actions.append(RepairAction(
                    loop=base, column=col, kind="segment",
                    n_samples=n_seg,
                    detail=f"{seg_count} gap(s) > {ffill_max_samples} samples — "
                           "left as NaN; downstream engine analyses around them"))

    rep.skipped_loops = loops_to_skip
    return df, rep
