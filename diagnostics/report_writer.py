"""
Report writer — saves all the text reports and the final summary.
===================================================================

Centralises the file-writing concerns of the v3 wrapper so the pipeline
orchestrator stays focused on flow rather than I/O details.
"""

import os
from datetime import datetime

from .constants import V3_VERSION
from .reporting_helpers import _line
from .health_check import HealthCheckReport
from .data_repair import RepairReport
from .outlier_handling import OutlierReport
from .auto_calibration import CalibrationReport


def _print_banner(mode: str, has_warnings: bool) -> str:
    lines = []
    lines.append(_line("═"))
    lines.append(f"  valve_diagnostics v{V3_VERSION}  —  "
                 f"calibration mode: {mode}")
    lines.append(_line("═"))
    if mode == "AUTO":
        lines.append("  This run used AUTO-CALIBRATED thresholds derived from "
                     "your data.")
        lines.append("  To use your manual DIAGNOSTIC_CONFIG values instead, "
                     "re-run with --manual.")
    else:
        lines.append("  This run used your MANUAL DIAGNOSTIC_CONFIG values.")
        lines.append("  To enable auto-calibration, re-run without --manual.")
    if has_warnings:
        lines.append("")
        lines.append("  ⚠️  Warnings were raised during the run — see "
                     "health_check_report.txt.")
    lines.append(_line("═"))
    return "\n".join(lines)


def write_health_report(output_dir: str, report: HealthCheckReport) -> str:
    """Write health_check_report.txt and return its path."""
    out = os.path.join(output_dir, "health_check_report.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report.render())
    return out


def write_repair_report(output_dir: str, report: RepairReport,
                        n_total: int) -> str:
    """Write data_repair_report.txt and return its path."""
    out = os.path.join(output_dir, "data_repair_report.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report.render(n_total=n_total))
    return out


def write_outlier_report(output_dir: str, report: OutlierReport) -> str:
    """Write outlier_handling_report.txt and return its path."""
    out = os.path.join(output_dir, "outlier_handling_report.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report.render())
    return out


def write_calibration_report(output_dir: str,
                             report: CalibrationReport) -> str:
    """Write auto_calibration_report.txt and return its path."""
    out = os.path.join(output_dir, "auto_calibration_report.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report.render())
    return out


def write_run_summary(output_dir: str, mode: str, has_warnings: bool,
                      input_path: str, started: datetime,
                      health: HealthCheckReport,
                      repair: RepairReport,
                      outlier: OutlierReport,
                      calib: CalibrationReport) -> str:
    """Write v3_run_summary.txt — one-page overview of the run."""
    summary_path = os.path.join(output_dir, "v3_run_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write(_print_banner(mode, has_warnings=has_warnings))
        fh.write("\n\n")
        fh.write(f"Input file:       {input_path}\n")
        fh.write(f"Output folder:    {output_dir}\n")
        fh.write(f"Run started:      {started}\n")
        fh.write(f"Run finished:     {datetime.now()}\n")
        fh.write(f"Health check:     {len(health.problems)} problems, "
                 f"{len(health.warnings)} warnings, "
                 f"{len(health.passed)} passed\n")
        fh.write(f"Repairs:          {len(repair.actions)} actions, "
                 f"{len(repair.skipped_loops)} loops skipped\n")
        fh.write(f"Outlier actions:  {len(outlier.actions)}\n")
        fh.write(f"Auto-calibration: "
                 f"{sum(1 for d in calib.decisions if d.mode == 'AUTO')} "
                 f"params calibrated, "
                 f"{sum(1 for d in calib.decisions if d.mode == 'FALLBACK')} "
                 f"fell back to manual\n")
        fh.write("\n")
        fh.write("Files produced:\n")
        for f in sorted(os.listdir(output_dir)):
            fh.write(f"  {f}\n")
    return summary_path
