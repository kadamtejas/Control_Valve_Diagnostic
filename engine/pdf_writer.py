"""
PDF writer — builds the Executive_summary.pdf.
================================================

Layer 4, module 3. Builds a one-page management-friendly PDF with the
plant dashboard image, top-N worst loops, key recommendations, and the
diagnostic heatmap.
"""

import os
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, PageBreak,
)

from .utils import logger
from .time_context import TimeContext
from .capabilities import Capabilities
from .plant_kpis import PlantKPIs


def write_pdf_summary(path: str, kpi: PlantKPIs, per_loop: dict,
                      tc: TimeContext, dashboard_png: str, capabilities: Capabilities,
                      heatmap_png: str = None):
    """One-page PDF executive summary for plant management."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                    Table, TableStyle, PageBreak)
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"],
                                  fontSize=16, spaceAfter=10)
    body = styles["BodyText"]
    elements = []

    elements.append(Paragraph("Plant Control Loop Diagnostics — Executive Summary",
                              title_style))
    elements.append(Paragraph(
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"Sample interval: {tc.dt_str()} | "
        f"Data span: {tc.duration_hours:.1f} hours | "
        f"Loops: {kpi.n_loops_analysed} analysed, {kpi.n_skipped} skipped",
        body))
    elements.append(Spacer(1, 8))

    # Headline
    phi = kpi.plant_health_index
    if phi >= 75:
        verdict = "HEALTHY"
        verdict_color = colors.green
    elif phi >= 50:
        verdict = "ATTENTION REQUIRED"
        verdict_color = colors.orange
    else:
        verdict = "CRITICAL"
        verdict_color = colors.red
    headline = ParagraphStyle("Headline", parent=styles["Heading2"],
                              textColor=verdict_color, fontSize=14)
    elements.append(Paragraph(
        f"Plant Health Index: {phi:.0f}/100 — {verdict}", headline))
    elements.append(Paragraph(
        f"Good: {kpi.pct_good:.0f}%   Poor: {kpi.pct_poor:.0f}%   "
        f"Critical: {kpi.pct_critical:.0f}%", body))
    elements.append(Spacer(1, 8))

    # Embed plant dashboard plot
    if dashboard_png and os.path.exists(dashboard_png):
        try:
            elements.append(Image(dashboard_png, width=18 * cm, height=6 * cm))
            elements.append(Spacer(1, 8))
        except Exception:
            pass

    # Heatmap goes on its own page so it isn't squeezed
    if heatmap_png and os.path.exists(heatmap_png):
        elements.append(PageBreak())
        elements.append(Paragraph("Per-loop diagnostic heatmap", styles["Heading2"]))
        elements.append(Paragraph(
            "Each row is a diagnosis category; each column is a loop, sorted "
            "worst-first. Cell colour shows severity; the small text inside "
            "shows the underlying metric that drove the result.", body))
        elements.append(Spacer(1, 6))
        try:
            # Maintain aspect ratio (heatmap is wider than tall)
            elements.append(Image(heatmap_png, width=18 * cm, height=11 * cm))
            elements.append(Spacer(1, 8))
        except Exception:
            pass

    # Top 10 worst loops table
    elements.append(Paragraph("Top 10 worst-performing loops", styles["Heading3"]))
    rows = [["Rank", "Loop", "Health", "Diagnosis"]]
    for i, (n, h, d) in enumerate(kpi.top_n_worst[:10], 1):
        rows.append([str(i), n, f"{h:.0f}", d])
    if len(rows) == 1:
        rows.append(["—", "—", "—", "All loops healthy"])
    t = Table(rows, colWidths=[1.5 * cm, 4 * cm, 2 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))

    # Diagnosis distribution
    elements.append(Paragraph("Diagnosis distribution", styles["Heading3"]))
    drows = [["Diagnosis", "Count"]]
    for k, v in sorted(kpi.diagnosis_counts.items(), key=lambda x: -x[1]):
        drows.append([k, str(v)])
    t = Table(drows, colWidths=[12 * cm, 2 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))

    # Capability gating
    if any(not v for v in [capabilities.can_stiction, capabilities.can_oscillation,
                           capabilities.can_harris, capabilities.can_propagation]):
        elements.append(Paragraph("Diagnostics skipped (data resolution too coarse)",
                                  styles["Heading3"]))
        for k, reason in capabilities.skip_reasons.items():
            elements.append(Paragraph(f"• {k}: {reason}", body))

    # ── Detailed findings per loop ──────────────────────────────────
    elements.append(PageBreak())
    elements.append(Paragraph("Detailed Findings per Loop", styles["Heading2"]))
    elements.append(Paragraph(
        "Below is a comprehensive analysis for each control loop, covering what "
        "was detected, how the diagnosis was reached, and the expected process impact.",
        body))
    elements.append(Spacer(1, 8))

    detail_style = ParagraphStyle("DetailBody", parent=body, fontSize=8,
                                   leading=11, spaceAfter=4)
    loop_title_style = ParagraphStyle("LoopTitle", parent=styles["Heading3"],
                                       fontSize=11, spaceAfter=4, spaceBefore=10)

    for name, info in per_loop.items():
        d = info.get("diagnosis")
        if d is None:
            continue
        sev_color = {
            "FAIL": colors.red, "WARN": colors.orange,
            "CRITICAL": colors.red, "OK": colors.green,
        }.get(d.severity, colors.black)
        loop_style = ParagraphStyle(f"Loop_{name}", parent=loop_title_style,
                                     textColor=sev_color)
        elements.append(Paragraph(
            f"{name} — {d.primary}  (Health: {d.health_score:.0f}/100, "
            f"Severity: {d.severity})", loop_style))

        # Rationale summary
        elements.append(Paragraph(f"<b>Summary:</b> {d.rationale}", detail_style))
        elements.append(Paragraph(
            f"<b>Recommended Action:</b> {d.recommended_action}", detail_style))

        # Full detailed explanation
        if d.detailed_explanation:
            for para in d.detailed_explanation.split("\n\n"):
                para = para.strip()
                if para:
                    elements.append(Paragraph(para, detail_style))

        # Embed the per-loop diagnostic plot
        loop_plot = info.get("plot_path")
        if loop_plot and os.path.exists(loop_plot):
            elements.append(Spacer(1, 6))
            try:
                elements.append(Image(loop_plot, width=17 * cm, height=10.5 * cm))
            except Exception:
                elements.append(Paragraph(
                    "<i>[Diagnostic plot could not be embedded]</i>", detail_style))
        elements.append(Spacer(1, 10))

    doc.build(elements)
