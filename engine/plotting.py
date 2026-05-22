"""
Plotting — matplotlib charts for per-loop, plant dashboard, and heatmap.
=========================================================================

Layer 4, module 1. Three plot functions:

  * `make_loop_diagnostic_plot`  — per-loop chart (PV/OP/SP, mode, diag)
  * `make_plant_dashboard_plot`  — plant-wide overview
  * `make_diagnostic_heatmap`    — diagnosis-by-loop coloured grid
"""

import os
from typing import Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .utils import logger, safe_float, safe_pos, DEFAULTS
from .time_context import TimeContext
from .loop_metrics import LoopMetrics
from .stiction_detection import StictionResult
from .diagnosis import Diagnosis
from .plant_kpis import PlantKPIs


def make_loop_diagnostic_plot(name: str, ts: pd.Series, pv, op, sp, mode_arr,
                              tc: TimeContext, diag: Diagnosis, sr: StictionResult,
                              metrics: LoopMetrics, hi: float, osc_reg: float,
                              save_path: str, config: dict):
    """4-panel diagnostic plot: PV/SP, OP, PV-OP scatter, error histogram."""
    fig, axes = plt.subplots(2, 2,
                             figsize=(safe_pos(config.get("PLOT_WIDTH", 11)),
                                      safe_pos(config.get("PLOT_HEIGHT", 7))))
    fig.suptitle(f"{name} — {diag.primary} (health {diag.health_score:.0f}/100)",
                 fontsize=12, fontweight="bold")

    # Panel 1: PV/SP over time
    ax = axes[0, 0]
    ax.plot(ts, pv, "b-", lw=0.8, label="PV")
    ax.plot(ts, sp, "r--", lw=1.0, label="SP")
    if mode_arr is not None:
        man_mask = (mode_arr == "MAN")
        if man_mask.any():
            ax.fill_between(ts, ax.get_ylim()[0], ax.get_ylim()[1],
                            where=man_mask, color="orange", alpha=0.15,
                            label="MAN")
    ax.set_xlabel("Time")
    ax.set_ylabel("PV / SP")
    ax.set_title("Process Variable & Setpoint")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    # Panel 2: OP over time
    ax = axes[0, 1]
    ax.plot(ts, op, "g-", lw=0.8)
    ax.set_xlabel("Time")
    ax.set_ylabel("OP %")
    ax.set_title(f"Controller Output (activity = {metrics.op_activity:.2f})")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="gray", lw=0.5, alpha=0.5)
    ax.axhline(100, color="gray", lw=0.5, alpha=0.5)

    # Panel 3: PV-OP scatter (valve signature)
    ax = axes[1, 0]
    ax.scatter(op, pv, s=2, alpha=0.5, c="purple")
    ax.set_xlabel("OP %")
    ax.set_ylabel("PV")
    ax.set_title(f"Valve Signature ({sr.yamashita_shape})")
    ax.grid(True, alpha=0.3)

    # Panel 4: error histogram with metrics text
    ax = axes[1, 1]
    err = pv - sp
    ax.hist(err[np.isfinite(err)], bins=40, color="steelblue", alpha=0.7)
    ax.set_xlabel("PV − SP")
    ax.set_ylabel("count")
    ax.set_title("Error Distribution")
    ax.grid(True, alpha=0.3)
    txt = (f"Harris Index : {hi:.2f}\n"
           f"Hägglund Reg : {osc_reg:.2f}\n"
           f"IAE / hour   : {metrics.iae_per_hour:.0f}\n"
           f"Stiction conf: {sr.consensus_score:.0f} ({sr.consensus_label})\n"
           f"  S est      : {sr.estimated_S:.2f}% OP\n"
           f"  J est      : {sr.estimated_J:.2f}% OP")
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, fontsize=8,
            family="monospace", verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.6))

    plt.tight_layout()
    plt.savefig(save_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def make_plant_dashboard_plot(kpi: PlantKPIs, save_path: str):
    """Plant-level health dashboard plot."""
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fig.suptitle("Plant Control Loop Health Dashboard",
                 fontsize=13, fontweight="bold")

    # Panel 1: PHI gauge
    ax = axes[0]
    phi = kpi.plant_health_index
    color = "#27ae60" if phi >= 75 else ("#f39c12" if phi >= 50 else "#c0392b")
    ax.barh([0], [phi], color=color, height=0.5)
    ax.barh([0], [100], color="lightgray", height=0.5, zorder=0)
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xlabel("Plant Health Index (0–100)")
    ax.set_title(f"PHI = {phi}")
    ax.text(phi, 0, f" {phi:.0f}", va="center", fontsize=14, fontweight="bold")

    # Panel 2: bucket pie
    ax = axes[1]
    buckets = [kpi.pct_good, kpi.pct_poor, kpi.pct_critical]
    labels = [f"Good ({kpi.pct_good:.0f}%)",
              f"Poor ({kpi.pct_poor:.0f}%)",
              f"Critical ({kpi.pct_critical:.0f}%)"]
    colors = ["#27ae60", "#f39c12", "#c0392b"]
    nz = [(b, l, c) for b, l, c in zip(buckets, labels, colors) if b > 0]
    if nz:
        ax.pie([b for b, _, _ in nz], labels=[l for _, l, _ in nz],
               colors=[c for _, _, c in nz], autopct="", startangle=90)
    ax.set_title("Loop Health Distribution")

    # Panel 3: diagnosis distribution
    ax = axes[2]
    if kpi.diagnosis_counts:
        items = sorted(kpi.diagnosis_counts.items(), key=lambda x: -x[1])
        names = [k[:30] for k, _ in items]
        counts = [v for _, v in items]
        ax.barh(range(len(names)), counts, color="steelblue")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Loop count")
        ax.set_title("Diagnosis Distribution")
    plt.tight_layout()
    plt.savefig(save_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def make_diagnostic_heatmap(per_loop: dict, save_path: str,
                            unit_mapping: dict = None):
    """
    Per-loop diagnostic heatmap: rows = diagnosis categories, columns = loops.
    Each cell is coloured by severity (Healthy / Borderline / Problem /
    Skipped) and shows a signature metric inside. Loops are sorted worst-
    first (lowest health score). When unit_mapping is provided, a thin
    separator row at the top labels the unit each column belongs to.
    """
    # ── Y-axis: 8 diagnosis categories. For each, derive (severity, metric)
    # from the loop's diagnosis + per-loop info.
    rows = [
        ("Stiction",            "stiction"),
        ("Aggressive tuning",   "aggressive"),
        ("Sluggish tuning",     "sluggish"),
        ("External oscillation","external"),
        ("Saturation",          "saturation"),
        ("Sensor issue",        "sensor"),
        ("Loop in MAN",         "man"),
        ("Data quality",        "dq"),
    ]
    row_labels = [r[0] for r in rows]
    row_keys = [r[1] for r in rows]

    # ── X-axis: loops sorted by health score, worst first.
    loops_sorted = sorted(
        [(name, info) for name, info in per_loop.items()
         if info.get("diagnosis") is not None],
        key=lambda kv: kv[1]["diagnosis"].health_score,
    )
    if not loops_sorted:
        # Nothing to plot
        return False

    n_loops = len(loops_sorted)
    n_rows = len(rows)
    loop_names = [n for n, _ in loops_sorted]

    # ── Severity codes: 0=Healthy(green), 1=Borderline(yellow),
    # 2=Problem(red), 3=Skipped(grey)
    SEV_HEALTHY, SEV_BORDER, SEV_FAIL, SEV_SKIP = 0, 1, 2, 3
    COLORS = {
        SEV_HEALTHY: "#27ae60",
        SEV_BORDER:  "#f39c12",
        SEV_FAIL:    "#c0392b",
        SEV_SKIP:    "#9e9e9e",
    }

    def _cell(name, info, key):
        """Return (severity, metric_text) for one (loop, diagnosis_row) cell."""
        diag = info["diagnosis"]
        m = info.get("metrics")
        s = info.get("stiction")
        dq = info.get("data_quality")
        sf = info.get("service_factor", 100.0)
        hi = info.get("harris", float("nan"))
        osc = info.get("osc_reg", float("nan"))
        primary = (diag.primary or "").lower()

        # FIX 2: oscillation-family diagnoses are mutually exclusive at the
        # diagnosis level. If the primary is already one of them, the OTHER
        # oscillation rows show "n/a" rather than misleading green/yellow.
        oscillation_family = {"stiction", "aggressive", "sluggish", "external"}
        primary_kind = None
        if "stiction" in primary:
            primary_kind = "stiction"
        elif "aggressive" in primary:
            primary_kind = "aggressive"
        elif "sluggish" in primary:
            primary_kind = "sluggish"
        elif "external" in primary:
            primary_kind = "external"

        # FIX 1: oscillation-family checks need meaningful PV amplitude.
        # A barely-moving loop with regular noise crossings shouldn't borderline.
        # Use the same 5%-relative threshold the diagnosis logic uses.
        amp_ok = False
        if m is not None:
            amp_ok = (m.pv_amplitude_pct > 5.0) or (m.pv_amplitude > 5.0)

        if key == "stiction":
            if s is None:
                return SEV_SKIP, "skip"
            if primary_kind == "stiction":
                return SEV_FAIL, f"S={s.estimated_S:.1f}%"
            if primary_kind in oscillation_family:
                # Another oscillation-family diagnosis owns this loop
                return SEV_SKIP, "n/a"
            if s.consensus_label == "Possible" and amp_ok:
                return SEV_BORDER, f"S={s.estimated_S:.1f}%"
            return SEV_HEALTHY, f"cons={s.consensus_score:.0f}"

        if key == "aggressive":
            if primary_kind == "aggressive":
                return SEV_FAIL, f"HI={hi:.2f}" if not np.isnan(hi) else "fail"
            if primary_kind in oscillation_family:
                return SEV_SKIP, "n/a"
            # borderline only if oscillating with meaningful amplitude
            if (amp_ok and not np.isnan(osc) and osc >= 0.6
                    and not np.isnan(hi) and hi < 0.4):
                return SEV_BORDER, f"Reg={osc:.2f}"
            return SEV_HEALTHY, f"HI={hi:.2f}" if not np.isnan(hi) else "—"

        if key == "sluggish":
            if primary_kind == "sluggish":
                return SEV_FAIL, f"HI={hi:.2f}" if not np.isnan(hi) else "fail"
            if primary_kind in oscillation_family:
                return SEV_SKIP, "n/a"
            if (not np.isnan(hi) and hi < 0.4 and m is not None and
                    m.iae_per_hour > 100):
                return SEV_BORDER, f"HI={hi:.2f}"
            return SEV_HEALTHY, f"HI={hi:.2f}" if not np.isnan(hi) else "—"

        if key == "external":
            if primary_kind == "external":
                return SEV_FAIL, f"Reg={osc:.2f}" if not np.isnan(osc) else "fail"
            if primary_kind in oscillation_family:
                return SEV_SKIP, "n/a"
            # borderline only if amplitude is meaningful + OP barely moving
            if (amp_ok and not np.isnan(osc) and osc >= 0.85
                    and m is not None and m.op_activity < 0.5):
                return SEV_BORDER, f"Reg={osc:.2f}"
            return SEV_HEALTHY, f"Reg={osc:.2f}" if not np.isnan(osc) else "—"

        if key == "saturation":
            if m is None:
                return SEV_SKIP, "—"
            if "saturation" in primary:
                pct = max(m.op_pct_at_full, m.op_pct_at_zero)
                return SEV_FAIL, f"OP={pct:.0f}%"
            if m.op_pct_at_full > 15 or m.op_pct_at_zero > 15:
                pct = max(m.op_pct_at_full, m.op_pct_at_zero)
                return SEV_BORDER, f"OP={pct:.0f}%"
            return SEV_HEALTHY, "OK"

        if key == "sensor":
            if dq is None:
                return SEV_SKIP, "—"
            if "sensor" in primary or dq.is_frozen:
                return SEV_FAIL, f"frozen={dq.longest_frozen_run}"
            if dq.is_quantised:
                return SEV_BORDER, f"q={dq.pv_unique_values}vals"
            return SEV_HEALTHY, "OK"

        if key == "man":
            if "in MAN" in (diag.primary or "") or "MAN" in primary:
                return SEV_FAIL, f"SF={sf:.0f}%"
            if sf < 85:
                return SEV_BORDER, f"SF={sf:.0f}%"
            return SEV_HEALTHY, f"SF={sf:.0f}%"

        if key == "dq":
            if dq is None:
                return SEV_SKIP, "—"
            if dq.severity == "FAIL":
                return SEV_FAIL, dq.severity
            if dq.severity == "WARN":
                return SEV_BORDER, dq.severity
            return SEV_HEALTHY, "OK"

        return SEV_SKIP, "—"

    # Build matrices
    sev_grid = np.full((n_rows, n_loops), SEV_SKIP, dtype=int)
    text_grid = [["" for _ in range(n_loops)] for _ in range(n_rows)]
    for j, (name, info) in enumerate(loops_sorted):
        for i, key in enumerate(row_keys):
            sev, txt = _cell(name, info, key)
            sev_grid[i, j] = sev
            text_grid[i][j] = txt

    # ── Plot. Width scales with loop count, height fixed.
    # Cell width target = 1.0 inch; min 0.6" so labels stay readable.
    cell_w = max(1.0, min(1.4, 14.0 / max(n_loops, 1)))
    fig_w = max(8.0, n_loops * cell_w + 3.0)
    fig_h = max(5.0, n_rows * 0.55 + 2.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    for i in range(n_rows):
        for j in range(n_loops):
            sev = sev_grid[i, j]
            ax.add_patch(plt.Rectangle((j, i), 1, 1,
                facecolor=COLORS[sev], edgecolor="white", linewidth=2))
            txt = text_grid[i][j]
            if txt:
                ax.text(j + 0.5, i + 0.5, txt,
                        ha="center", va="center",
                        fontsize=8, color="white", fontweight="bold")

    ax.set_xlim(0, n_loops); ax.set_ylim(0, n_rows)
    ax.set_xticks(np.arange(n_loops) + 0.5)
    ax.set_xticklabels(loop_names, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(np.arange(n_rows) + 0.5)
    ax.set_yticklabels(row_labels, fontsize=10)
    ax.invert_yaxis()
    ax.tick_params(left=False, bottom=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Optional unit row above the column labels
    if unit_mapping:
        units = [unit_mapping.get(n, "Unknown") for n in loop_names]
        # Place unit text above the heatmap
        for j, u in enumerate(units):
            ax.text(j + 0.5, -0.15, u, ha="center", va="bottom",
                    fontsize=7.5, color="#555", style="italic", rotation=0)

    title = ("Per-loop diagnostic heatmap" +
             ("  (with units)" if unit_mapping else ""))
    ax.set_title(title, fontsize=13, fontweight="bold",
                 loc="left", pad=24)

    # Legend — placed below the chart
    legend_patches = [
        plt.Rectangle((0,0), 1, 1, facecolor=COLORS[SEV_HEALTHY], label="Healthy"),
        plt.Rectangle((0,0), 1, 1, facecolor=COLORS[SEV_BORDER], label="Borderline / watch"),
        plt.Rectangle((0,0), 1, 1, facecolor=COLORS[SEV_FAIL], label="Problem detected"),
        plt.Rectangle((0,0), 1, 1, facecolor=COLORS[SEV_SKIP], label="Not applicable / skipped"),
    ]
    ax.legend(handles=legend_patches, loc="upper center",
              bbox_to_anchor=(0.5, -0.18 - 0.02 * (n_loops > 8)),
              ncol=4, frameon=False, fontsize=9)

    plt.tight_layout()
    plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True
