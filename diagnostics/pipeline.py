"""
Pipeline — top-level orchestration of the v3 wrapper.
=======================================================

Runs each stage in order:

  1. Health check  (5 sub-stages)
  2. Build dataframe
  3. Data repair
  4. Outlier handling
  5. Auto-calibration
  6. Write the cleaned-and-calibrated workbook
  7. Hand off to the v2 engine
  8. Write the run summary

Returns an exit code: 0 on success, 2 on health-check failure, 3 on
v2 engine failure.
"""

import os
import traceback
from datetime import datetime
import sys
import io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from column_normaliser import normalise_columns
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# v2 engine — imported here so the rest of the package stays decoupled
import valve_diagnostics_v2 as v2

from .constants import PROBLEM
from .health_check import (
    HealthCheckReport,
    _stage1_file_checks,
    _stage2_sheet_checks,
    _stage3_config_checks,
    _stage4_data_checks,
    _stage5_cross_checks,
)
from .data_repair import repair_dataframe
from .outlier_handling import handle_outliers
from .auto_calibration import calibrate
from .io_helpers import (
    _build_dataframe,
    _read_unit_mapping,
    _write_processed_workbook,
)
from .report_writer import (
    _print_banner,
    write_health_report,
    write_repair_report,
    write_outlier_report,
    write_calibration_report,
    write_run_summary,
)


def run_v3(input_path: str, output_dir: str, mode: str = "AUTO",
           verbose: bool = True,
           skip_incomplete: bool = False,
           force_run_with_problems: bool = False) -> int:
    """
    Top-level orchestration. Returns exit code (0 = success).
    """
    os.makedirs(output_dir, exist_ok=True)
    started = datetime.now()

    report = HealthCheckReport(file_path=input_path,
                               run_at=started.strftime("%Y-%m-%d %H:%M:%S"))

    # ══ Stage 1
    ok = _stage1_file_checks(input_path, report)
    if not ok:
        write_health_report(output_dir, report)
        if verbose:
            print(report.render())
            print("\n❌  Health check found a fatal problem — see "
                  f"{os.path.join(output_dir, 'health_check_report.txt')}")
        return 2

    # ══ Stage 2
    ok, sheet_info = _stage2_sheet_checks(input_path, report)
    if not ok or sheet_info is None:
        write_health_report(output_dir, report)
        if verbose:
            print(report.render())
            print("\n❌  Health check found a fatal sheet/column problem — see "
                  f"{os.path.join(output_dir, 'health_check_report.txt')}")
        return 2

    # ══ Stage 3
    manual_config = _stage3_config_checks(input_path, report)

    # ══ Stage 4
    data_info = _stage4_data_checks(input_path, sheet_info, report)
    has_data_problem = any(r.severity == PROBLEM and r.check_id.startswith("4")
                           for r in report.results)

    # ══ Stage 5
    _stage5_cross_checks(input_path, sheet_info, data_info, report)

    if report.has_problems and not force_run_with_problems:
        write_health_report(output_dir, report)
        if verbose:
            print(report.render())
            print(f"\n❌  Health check found {len(report.problems)} "
                  "problem(s). Fix them and re-run.")
            print(f"  Full report: "
                  f"{os.path.join(output_dir, 'health_check_report.txt')}")
            print(f"  To run anyway (NOT recommended), add --force.")
        return 2

    write_health_report(output_dir, report)
    if verbose:
        print(report.render())

    # ── Build dataframe
    df = _build_dataframe(input_path, sheet_info)

    # ── Normalise column names (_PV / .PV / bare-tag formats → standard _PV)
    df, norm_report = normalise_columns(df)

    # Rebuild suffix_map from the now-normalised column names so that all
    # downstream modules (data_repair, outlier_handling, auto_calibration)
    # reference the correct renamed columns.
    suffix_map = {}
    for col in df.columns:
        if col == "TIMESTAMP":
            continue
        for sig in ("_PV", "_OP", "_SP", "_MODE"):
            if col.upper().endswith(sig):
                base = col[: -len(sig)]
                suffix_map.setdefault(base, {})[sig[1:]] = col
                break

    median_dt = float(data_info.get("median_dt_sec", 60.0))

    # ── Module 2: data repair
    skip_list = []
    if skip_incomplete:
        skip_list.extend(b for b, _, _ in data_info.get("miss_problems", []))
    skip_list.extend(data_info.get("pv_loops_no_data", []))

    cleaned_df, repair_report = repair_dataframe(
        df, suffix_map, median_dt_sec=median_dt,
        skip_incomplete=skip_list)

    # ── Module 3: outliers
    skipped_loop_names = [n for n, _ in repair_report.skipped_loops]
    cleaned_df, outlier_report = handle_outliers(
        cleaned_df, suffix_map, skipped_loops=skipped_loop_names)

    # ── Module 4: auto-calibration
    unit_mapping = _read_unit_mapping(input_path)
    calib_report = calibrate(
        cleaned_df, suffix_map, manual_config,
        median_dt_sec=median_dt,
        skipped_loops=skipped_loop_names,
        unit_mapping=unit_mapping,
        mode=mode)

    # ── Write reports
    write_repair_report(output_dir, repair_report, n_total=len(df))
    write_outlier_report(output_dir, outlier_report)
    write_calibration_report(output_dir, calib_report)

    # ── Write the cleaned + calibrated workbook (this is what v2 will read)
    processed_path = os.path.join(output_dir, "data_v3_processed.xlsx")
    _write_processed_workbook(input_path, processed_path,
                              cleaned_df, calib_report, run_mode=mode)

    # ── Run the v2 engine on the cleaned, calibrated workbook
    if verbose:
        print(_print_banner(mode, has_warnings=len(report.warnings) > 0))
        print("\n  Running v2 diagnostic engine on processed data ...")

    try:
        v2.run_diagnostics(processed_path, output_dir, verbose=verbose)
    except Exception as e:
        msg = (f"\n❌  v2 engine failed: {e}\n\n"
               "The earlier modules completed successfully but the diagnostic\n"
               "engine raised an unexpected error. The cleaned data and\n"
               "calibration reports are in the output folder.\n\n"
               "Full traceback in v3_engine_error.txt")
        if verbose:
            print(msg)
        with open(os.path.join(output_dir, "v3_engine_error.txt"), "w") as fh:
            fh.write(traceback.format_exc())
        return 3

    # ── Final summary
    summary_path = write_run_summary(
        output_dir, mode=mode,
        has_warnings=len(report.warnings) > 0,
        input_path=input_path, started=started,
        health=report, repair=repair_report,
        outlier=outlier_report, calib=calib_report,
    )

    if verbose:
        print(f"\n✅  Done. Outputs in: {output_dir}")
        print(f"   • {os.path.basename(summary_path)} ......... overall summary")
        print(f"   • health_check_report.txt .......... input checks")
        print(f"   • data_repair_report.txt ........... what was repaired")
        print(f"   • outlier_handling_report.txt ...... outlier actions")
        print(f"   • auto_calibration_report.txt ...... how each param was set")
        print(f"   • Loop_diagnostics_v2.xlsx ......... per-loop results")
        print(f"   • Executive_summary.pdf ............ PDF summary")
    return 0