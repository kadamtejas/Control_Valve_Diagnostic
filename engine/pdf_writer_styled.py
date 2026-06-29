"""
PDF writer (styled) — builds the Diagnostic_Report_styled.pdf.
===============================================================

Layer 4, module 3b. Same content as pdf_writer.py but with APC-style
visual formatting: navy header, color-coded KPI table with status badges,
per-loop mini chip row, alternating row colours, and section dividers.

Call write_pdf_summary_styled() in place of (or alongside) write_pdf_summary()
from engine.py to produce the styled report.
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, PageBreak, HRFlowable,
)

from .time_context import TimeContext
from .capabilities import Capabilities
from .plant_kpis import PlantKPIs


# ── Colour palette (mirrors APC HTML report) ──────────────────────────────────
NAVY      = colors.HexColor("#0F2744")   # header / section rule
TEAL      = colors.HexColor("#0D6E7E")   # loop headings
BLUE_BG   = colors.HexColor("#DBEAFE")   # On Track bg
BLUE_FG   = colors.HexColor("#1D4ED8")   # On Track text
YELLOW_BG = colors.HexColor("#FEF3C7")   # Watch bg
YELLOW_FG = colors.HexColor("#92400E")   # Watch text
RED_BG    = colors.HexColor("#FEE2E2")   # Needs Work bg
RED_FG    = colors.HexColor("#991B1B")   # Needs Work text
SLATE     = colors.HexColor("#475569")   # body text
BORDER    = colors.HexColor("#D1DDE8")   # table grid lines
ROW_ALT   = colors.HexColor("#F0F6FF")   # alternating row tint
WHITE     = colors.white


# ── Helpers ───────────────────────────────────────────────────────────────────

def _severity_colors(severity: str):
    """Return (bg, fg) for a severity value."""
    return {
        "OK":       (BLUE_BG,   BLUE_FG),
        "WARN":     (YELLOW_BG, YELLOW_FG),
        "FAIL":     (RED_BG,    RED_FG),
        "CRITICAL": (RED_BG,    RED_FG),
    }.get(severity, (BLUE_BG, BLUE_FG))


def _health_colors(score: float):
    """Return (bg, fg) for a numeric health score."""
    if score >= 75:
        return BLUE_BG, BLUE_FG
    if score >= 50:
        return YELLOW_BG, YELLOW_FG
    return RED_BG, RED_FG


def _score_verdict(score: float):
    """Return (bg, fg, badge_text) for a percentage score."""
    if score >= 75:
        return BLUE_BG, BLUE_FG, "\u25b2 On Track"
    if score >= 50:
        return YELLOW_BG, YELLOW_FG, "\u25c6 Watch"
    return RED_BG, RED_FG, "\u25bc Needs Work"


def _hex(color):
    """Return 6-char hex string from a ReportLab color (no leading #)."""
    return color.hexval()[2:]


def _section_heading(title: str, styles):
    """Teal bold heading + navy horizontal rule."""
    return [
        Paragraph(title, styles["_SectionHead"]),
        HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=6),
    ]


def _navy_table(rows, col_widths):
    """
    Build a table with a navy header row, alternating light-blue row tint,
    and a thin border grid.  All cells use 8pt Helvetica.
    """
    n_rows = len(rows)
    style_cmds = [
        # Header row
        ("BACKGROUND",     (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",      (0, 0), (-1, 0), WHITE),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, 0), 8),
        ("ALIGN",          (0, 0), (-1, 0), "CENTER"),
        # Body
        ("FONTSIZE",       (0, 1), (-1, -1), 8),
        ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",           (0, 0), (-1, -1), 0.4, BORDER),
    ]
    for r in range(1, n_rows):
        if r % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, r), (-1, r), ROW_ALT))
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle(style_cmds))
    return t


# ── Main entry point ──────────────────────────────────────────────────────────

def write_pdf_summary_styled(path: str, kpi: PlantKPIs, per_loop: dict,
                              tc: TimeContext, dashboard_png: str,
                              capabilities: Capabilities,
                              heatmap_png: str = None):
    """
    Styled PDF executive summary — same content as write_pdf_summary()
    but formatted like the APC Performance Report (navy header, colour-coded
    KPI badges, per-loop chip rows).
    """

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    # ── Register custom paragraph styles ─────────────────────────────
    base = getSampleStyleSheet()
    body = base["BodyText"]

    base.add(ParagraphStyle("_ReportTitle", parent=body,
                             fontSize=18, fontName="Helvetica-Bold",
                             textColor=NAVY, spaceAfter=2))
    base.add(ParagraphStyle("_SubTitle", parent=body,
                             fontSize=9, textColor=SLATE, spaceAfter=6))
    base.add(ParagraphStyle("_SectionHead", parent=body,
                             fontSize=11, fontName="Helvetica-Bold",
                             textColor=NAVY, spaceBefore=14, spaceAfter=2))
    base.add(ParagraphStyle("_LoopHead", parent=body,
                             fontSize=10, fontName="Helvetica-Bold",
                             textColor=TEAL, spaceBefore=10, spaceAfter=3))
    base.add(ParagraphStyle("_Detail", parent=body,
                             fontSize=8, leading=11,
                             textColor=SLATE, spaceAfter=3))

    elements = []
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")

    # ── Header ────────────────────────────────────────────────────────
    elements.append(Paragraph("Plant Control Loop Diagnostics", base["_ReportTitle"]))
    elements.append(Paragraph(
        f"Generated: {now_str}  |  "
        f"Sample interval: {tc.dt_str()}  |  "
        f"Data span: {tc.duration_hours:.1f} h  |  "
        f"Loops: {kpi.n_loops_analysed} analysed, {kpi.n_skipped} skipped",
        base["_SubTitle"],
    ))
    elements.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=12))

    # ── 1. Executive Summary — KPI table ─────────────────────────────
    elements += _section_heading("1. Executive Summary", base)

    phi = kpi.plant_health_index
    phi_bg, phi_fg, phi_verdict = _score_verdict(phi)
    pct_good_bg,  pct_good_fg,  pct_good_verd  = _score_verdict(kpi.pct_good)
    pct_crit_bg,  pct_crit_fg,  pct_crit_verd  = _score_verdict(100 - kpi.pct_critical)

    def _p(text, align=0, bold=False, color=None, size=9):
        st = ParagraphStyle(
            f"_p_{id(text)}", parent=body,
            fontSize=size, alignment=align,
            textColor=color or SLATE,
            fontName="Helvetica-Bold" if bold else "Helvetica",
        )
        return Paragraph(text, st)

    kpi_rows = [
        # Header
        [_p("<b>KPI</b>"),
         _p("<b>Score</b>",  align=1),
         _p("<b>Status</b>", align=1),
         _p("<b>Target</b>", align=1)],
        # Plant Health Index
        [_p("<b>Plant Health Index</b>"),
         _p(f"<b>{phi:.1f}/100</b>", align=1, color=phi_fg),
         _p(phi_verdict,             align=1, color=phi_fg),
         _p("100",                   align=1)],
        # Loops Good
        [_p("<b>Loops \u2014 Good</b>"),
         _p(f"<b>{kpi.pct_good:.1f}%</b>",  align=1, color=pct_good_fg),
         _p(pct_good_verd,                   align=1, color=pct_good_fg),
         _p("100%",                          align=1)],
        # Loops Poor
        [_p("<b>Loops \u2014 Poor</b>"),
         _p(f"<b>{kpi.pct_poor:.1f}%</b>",  align=1, color=YELLOW_FG),
         _p("\u25c6 Watch",                  align=1, color=YELLOW_FG),
         _p("0%",                            align=1)],
        # Loops Critical
        [_p("<b>Loops \u2014 Critical</b>"),
         _p(f"<b>{kpi.pct_critical:.1f}%</b>", align=1, color=pct_crit_fg),
         _p(pct_crit_verd,                      align=1, color=pct_crit_fg),
         _p("0%",                               align=1)],
    ]

    kpi_table = Table(kpi_rows, colWidths=[7*cm, 3*cm, 3.5*cm, 2.5*cm])
    kpi_ts = [
        ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
    ]
    # Colour score + status columns per data row
    for ri, (rbg, _) in enumerate([
        (phi_bg,      phi_fg),
        (pct_good_bg, pct_good_fg),
        (YELLOW_BG,   YELLOW_FG),
        (pct_crit_bg, pct_crit_fg),
    ], start=1):
        kpi_ts += [
            ("BACKGROUND", (1, ri), (1, ri), rbg),
            ("BACKGROUND", (2, ri), (2, ri), rbg),
        ]
    kpi_table.setStyle(TableStyle(kpi_ts))
    elements.append(kpi_table)
    elements.append(Spacer(1, 8))

    # Dashboard image
    if dashboard_png and os.path.exists(dashboard_png):
        try:
            elements.append(Image(dashboard_png, width=18*cm, height=6*cm))
            elements.append(Spacer(1, 8))
        except Exception:
            pass

    # ── 2. Diagnosis Distribution ─────────────────────────────────────
    elements += _section_heading("2. Diagnosis Distribution", base)
    total = sum(kpi.diagnosis_counts.values()) or 1
    drows = [["Diagnosis", "Count", "Share"]]
    for k, v in sorted(kpi.diagnosis_counts.items(), key=lambda x: -x[1]):
        drows.append([k, str(v), f"{100*v/total:.1f}%"])
    elements.append(_navy_table(drows, [10*cm, 2*cm, 4*cm]))
    elements.append(Spacer(1, 6))

    # ── 3. Heatmap ────────────────────────────────────────────────────
    if heatmap_png and os.path.exists(heatmap_png):
        elements.append(PageBreak())
        elements += _section_heading("3. Per-Loop Diagnostic Heatmap", base)
        elements.append(Paragraph(
            "Each row is a diagnosis category; each column is a loop sorted worst-first. "
            "Cell colour shows severity; the small text shows the metric that drove the result.",
            base["_Detail"],
        ))
        elements.append(Spacer(1, 6))
        try:
            elements.append(Image(heatmap_png, width=18*cm, height=11*cm))
        except Exception:
            pass
        elements.append(Spacer(1, 8))

    # ── 4. Top 10 Worst Loops ─────────────────────────────────────────
    elements += _section_heading("4. Top 10 Worst-Performing Loops", base)
    worst_rows = [["Rank", "Loop", "Health", "Severity", "Primary Diagnosis"]]
    for i, (n, h, diag_label) in enumerate(kpi.top_n_worst[:10], 1):
        sev = "—"
        info = per_loop.get(n)
        if info and info.get("diagnosis"):
            sev = info["diagnosis"].severity
        worst_rows.append([str(i), n, f"{h:.0f}", sev, diag_label])
    if len(worst_rows) == 1:
        worst_rows.append(["—", "—", "—", "—", "All loops healthy"])

    t = Table(worst_rows, colWidths=[1.2*cm, 4*cm, 2.2*cm, 2.2*cm, 6.4*cm])
    ts = [
        ("BACKGROUND",    (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
    ]
    for r in range(1, len(worst_rows)):
        row_bg = ROW_ALT if r % 2 == 0 else WHITE
        ts.append(("BACKGROUND", (0, r), (-1, r), row_bg))
        try:
            h_bg, h_fg = _health_colors(float(worst_rows[r][2]))
            ts += [
                ("BACKGROUND", (2, r), (2, r), h_bg),
                ("TEXTCOLOR",  (2, r), (2, r), h_fg),
                ("FONTNAME",   (2, r), (2, r), "Helvetica-Bold"),
                ("ALIGN",      (2, r), (2, r), "CENTER"),
            ]
        except ValueError:
            pass
        sev_bg, sev_fg = _severity_colors(worst_rows[r][3])
        ts += [
            ("BACKGROUND", (3, r), (3, r), sev_bg),
            ("TEXTCOLOR",  (3, r), (3, r), sev_fg),
            ("FONTNAME",   (3, r), (3, r), "Helvetica-Bold"),
            ("ALIGN",      (3, r), (3, r), "CENTER"),
        ]
    t.setStyle(TableStyle(ts))
    elements.append(t)
    elements.append(Spacer(1, 8))

    # ── 5. Capability notes ───────────────────────────────────────────
    if any(not v for v in [capabilities.can_stiction, capabilities.can_oscillation,
                           capabilities.can_harris, capabilities.can_propagation]):
        elements += _section_heading("5. Diagnostics Skipped (data resolution)", base)
        for k, reason in capabilities.skip_reasons.items():
            elements.append(Paragraph(f"\u2022 {k}: {reason}", base["_Detail"]))
        elements.append(Spacer(1, 6))

    # ── 6. Detailed per-loop findings ─────────────────────────────────
    elements.append(PageBreak())
    elements += _section_heading("6. Detailed Findings per Loop", base)
    elements.append(Paragraph(
        "Comprehensive analysis for each control loop \u2014 what was detected, "
        "how it was diagnosed, and the recommended action.",
        base["_Detail"],
    ))
    elements.append(Spacer(1, 8))

    for name, info in per_loop.items():
        d = info.get("diagnosis")
        if d is None:
            continue

        sev_bg, sev_fg = _severity_colors(d.severity)
        h_bg,   h_fg   = _health_colors(d.health_score)

        # Loop title in teal
        elements.append(Paragraph(f"{name} \u2014 {d.primary}", base["_LoopHead"]))

        # Mini chip row: Health | Severity | Confidence
        chip_rows = [[
            Paragraph(
                f'<font color="#{_hex(h_fg)}"><b>{d.health_score:.0f}/100</b></font>'
                f'<br/><font size="6" color="#{_hex(SLATE)}">Health</font>',
                ParagraphStyle("_ch", parent=body, fontSize=9, alignment=1),
            ),
            Paragraph(
                f'<font color="#{_hex(sev_fg)}"><b>{d.severity}</b></font>'
                f'<br/><font size="6" color="#{_hex(SLATE)}">Severity</font>',
                ParagraphStyle("_cs", parent=body, fontSize=9, alignment=1),
            ),
            Paragraph(
                f'<font color="#{_hex(BLUE_FG)}"><b>{d.confidence:.0f}%</b></font>'
                f'<br/><font size="6" color="#{_hex(SLATE)}">Confidence</font>',
                ParagraphStyle("_cc", parent=body, fontSize=9, alignment=1),
            ),
        ]]
        chip_table = Table(chip_rows, colWidths=[3*cm, 3*cm, 3*cm])
        chip_table.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("BOX",           (0, 0), (-1, -1), 0.4, BORDER),
            ("LINEAFTER",     (0, 0), (1, 0),   0.4, BORDER),
            ("BACKGROUND",    (0, 0), (0, 0), h_bg),
            ("BACKGROUND",    (1, 0), (1, 0), sev_bg),
            ("BACKGROUND",    (2, 0), (2, 0), BLUE_BG),
        ]))
        elements.append(chip_table)
        elements.append(Spacer(1, 4))

        # Summary + action
        elements.append(Paragraph(f"<b>Summary:</b> {d.rationale}", base["_Detail"]))
        elements.append(Paragraph(
            f"<b>Recommended Action:</b> {d.recommended_action}", base["_Detail"]))

        # Detailed explanation paragraphs
        if d.detailed_explanation:
            for para in d.detailed_explanation.split("\n\n"):
                para = para.strip()
                if para:
                    elements.append(Paragraph(para, base["_Detail"]))

        # Loop diagnostic plot
        loop_plot = info.get("plot_path")
        if loop_plot and os.path.exists(loop_plot):
            elements.append(Spacer(1, 6))
            try:
                elements.append(Image(loop_plot, width=17*cm, height=10.5*cm))
            except Exception:
                elements.append(Paragraph(
                    "<i>[Diagnostic plot could not be embedded]</i>",
                    base["_Detail"],
                ))
        elements.append(Spacer(1, 10))

    doc.build(elements)
