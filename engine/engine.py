"""
Engine orchestrator — runs the four engine layers end-to-end.
===============================================================

Calls each layer in order and returns a result dict containing
references to all the per-loop and plant-level artifacts.
"""

import os

import numpy as np

from .utils import logger, safe_float, setup_logging
from .input_loading import (
    load_clean_dataframe, detect_loops,
    load_config, load_unit_mapping,
    load_mode_mapping, _reset_mode_warnings,
    load_diagnostic_selection, load_detection_exclusions,
)
from .time_context import detect_time_context
from .data_quality import assess_data_quality, apply_mode_filter
from .capabilities import determine_capabilities
from .loop_metrics import compute_loop_metrics
from .performance_indices import harris_index, haglund_oscillation_index
from .stiction_detection import StictionResult, stiction_consensus
from .diagnosis import diagnose_loop
from .propagation import propagation_analysis
from .plant_kpis import compute_plant_kpis
from .plotting import (
    make_loop_diagnostic_plot,
    make_plant_dashboard_plot,
    make_diagnostic_heatmap,
)
from .excel_writer import write_excel_report
from .pdf_writer import write_pdf_summary


def run_diagnostics(input_path: str, output_dir: str, verbose: bool = True) -> dict:
    """Top-level: run end-to-end. Returns a result dict."""
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "diagnostics.log")
    setup_logging(log_path, verbose=verbose)
    logger.info(f"Starting valve diagnostics on {input_path}")

    df = load_clean_dataframe(input_path)
    logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    tc = detect_time_context(df["TIMESTAMP"])
    logger.info(f"Sample rate: {tc.dt_str()} | duration: {tc.duration_hours:.2f} h | "
                f"irregular={tc.irregular} | gaps={tc.gap_count}")

    config = load_config(input_path)
    capabilities = determine_capabilities(tc, config)
    for k, v in capabilities.skip_reasons.items():
        logger.warning(f"Diagnostic '{k}' DISABLED: {v}")

    selection = load_diagnostic_selection(input_path)
    detection_exclusions = load_detection_exclusions(input_path)
    if detection_exclusions:
        logger.info(f"Detection exclusions loaded: { {k: list(v) for k, v in detection_exclusions.items()} }")
    mode_mapping = load_mode_mapping(input_path)
    _reset_mode_warnings()

    loops = detect_loops(df)
    logger.info(f"Detected {len(loops)} control loops: {list(loops.keys())}")
    if not loops:
        raise RuntimeError("No PV/OP/SP triplets found in input file.")

    unit_mapping = load_unit_mapping(input_path)
    if unit_mapping:
        unmapped = [n for n in loops if n not in unit_mapping]
        if unmapped:
            logger.warning(
                f"{len(unmapped)} loop(s) not in UNIT_MAPPING (will be treated "
                f"as unit 'Unknown'): {', '.join(unmapped)}"
            )

    # ── per-loop analysis ──
    per_loop = {}
    plot_dir = os.path.join(output_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)

    # Stiction-as-a-whole runs only if user selected it AND the data supports it
    run_stiction = capabilities.can_stiction and selection.stiction_detection
    run_harris = capabilities.can_harris and selection.harris_index
    run_hagglund = capabilities.can_oscillation and selection.hagglund_oscillation

    for name, cols in loops.items():
        try:
            (pv, op, sp, mode_arr, sf, n_total, n_used, mask,
             pv_u, op_u, sp_u) = apply_mode_filter(cols, df, mode_mapping)
            ts_full = df["TIMESTAMP"]
            if len(pv_u) < 30:
                per_loop[name] = {"diagnosis": None,
                                  "skip_reason": f"only {len(pv_u)} AUTO samples"}
                logger.warning(f"{name}: skipped — insufficient AUTO/CAS data")
                continue

            dq = assess_data_quality(pv, config)
            metrics = compute_loop_metrics(pv_u, op_u, sp_u, tc)
            hi = harris_index(pv_u, sp_u, op_u) if run_harris else float("nan")
            # FIX: Invalidate Harris when OP is nearly static — the AR model
            # produces misleadingly high HI when the controller barely moves.
            op_act_thr_main = safe_float(config.get("OP_ACTIVITY_THRESHOLD", 1.5))
            if not np.isnan(hi) and metrics.op_activity < op_act_thr_main * 0.1:
                logger.debug(f"{name}: Harris {hi:.2f} invalidated — OP activity "
                             f"{metrics.op_activity:.4f} too low for reliable estimate")
                hi = float("nan")
            if run_hagglund:
                osc_reg, osc_period = haglund_oscillation_index(pv_u - sp_u)
            else:
                osc_reg, osc_period = float("nan"), 0
            if run_stiction:
                sr = stiction_consensus(pv_u, op_u, sp_u, metrics, config, selection)
            else:
                sr = StictionResult()

            diag = diagnose_loop(metrics, sr, hi, osc_reg, osc_period, dq, sf,
                                 capabilities, config, tc, selection,
                                 detection_exclusions=detection_exclusions.get(name, set()))
            # Per-loop plot
            plot_path = os.path.join(plot_dir, f"{name}.png")
            try:
                make_loop_diagnostic_plot(name, ts_full, pv, op, sp, mode_arr,
                                          tc, diag, sr, metrics, hi, osc_reg,
                                          plot_path, config)
            except Exception as e:
                logger.warning(f"{name}: plot generation failed ({e})")
                plot_path = None

            per_loop[name] = {
                "diagnosis": diag,
                "metrics": metrics,
                "stiction": sr,
                "harris": hi,
                "osc_reg": osc_reg,
                "osc_period_str": tc.samples_to_display_str(osc_period) if osc_period > 0 else "",
                "data_quality": dq,
                "service_factor": sf,
                "plot_path": plot_path if plot_path and os.path.exists(plot_path) else None,
            }
            logger.info(f"{name}: {diag.primary} (health {diag.health_score:.0f}, {diag.severity})")

        except Exception as e:
            logger.error(f"{name}: analysis FAILED — {e}", exc_info=True)
            per_loop[name] = {"diagnosis": None, "skip_reason": f"error: {e}"}

    # ── propagation ──
    if capabilities.can_propagation and selection.cross_loop_propagation:
        try:
            links = propagation_analysis(loops, df, tc, unit_mapping, config, selection)
            logger.info(f"Propagation: {len(links)} significant links")
        except Exception as e:
            logger.error(f"Propagation analysis failed: {e}", exc_info=True)
            links = []
    else:
        links = []

    # ── plant KPIs ──
    kpi = compute_plant_kpis(per_loop, config)
    logger.info(f"Plant Health Index = {kpi.plant_health_index}")

    # ── plots & reports ──
    dashboard_png = os.path.join(output_dir, "plant_dashboard.png")
    try:
        make_plant_dashboard_plot(kpi, dashboard_png)
    except Exception as e:
        logger.warning(f"Dashboard plot failed: {e}")
        dashboard_png = None

    heatmap_png = os.path.join(output_dir, "diagnostic_heatmap.png")
    try:
        ok = make_diagnostic_heatmap(per_loop, heatmap_png, unit_mapping or None)
        if not ok:
            heatmap_png = None
        else:
            logger.info(f"Diagnostic heatmap: {heatmap_png}")
    except Exception as e:
        logger.warning(f"Heatmap generation failed: {e}")
        heatmap_png = None

    excel_path = os.path.join(output_dir, "Loop_diagnostics_v2.xlsx")
    write_excel_report(excel_path, df, tc, capabilities, per_loop, links, kpi,
                       config, dashboard_png=dashboard_png, selection=selection,
                       heatmap_png=heatmap_png)
    logger.info(f"Excel report: {excel_path}")

    pdf_path = os.path.join(output_dir, "Executive_summary.pdf")
    try:
        write_pdf_summary(pdf_path, kpi, per_loop, tc, dashboard_png, capabilities,
                          heatmap_png=heatmap_png)
        logger.info(f"PDF summary: {pdf_path}")
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        pdf_path = None

    return {
        "df": df, "tc": tc, "loops": loops, "config": config,
        "capabilities": capabilities, "per_loop": per_loop, "links": links,
        "kpi": kpi, "excel_path": excel_path, "pdf_path": pdf_path,
        "dashboard_png": dashboard_png,
    }
