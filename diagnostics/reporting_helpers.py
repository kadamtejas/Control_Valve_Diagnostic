"""
Reporting helpers — text formatting utilities used by every report.
====================================================================

These tiny functions draw the boxes and section headers that appear in
the health-check, repair, outlier, and calibration text reports.
"""

from typing import List

from .constants import PROBLEM, WARNING, INFO


def _line(char: str = "─", width: int = 65) -> str:
    return char * width


def _box(title: str, severity: str, body_lines: List[str]) -> str:
    """Render a single problem/warning/info box in the user-facing format."""
    icon = {
        PROBLEM: "❌  PROBLEM",
        WARNING: "⚠️   WARNING",
        INFO:    "ℹ️   INFO",
    }.get(severity, severity)
    out = []
    out.append(_line())
    out.append(f"  {icon}: {title}")
    out.append(_line())
    out.append("")
    for ln in body_lines:
        out.append("  " + ln if ln else "")
    out.append(_line())
    out.append("")
    return "\n".join(out)


def _section_header(text: str) -> str:
    return f"\n{_line('═')}\n  {text}\n{_line('═')}\n"
