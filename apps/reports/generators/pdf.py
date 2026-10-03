"""PDF rendering of a MonthlyReport snapshot (ReportLab, pure Python — no system deps).

The PDF is rendered from the frozen snapshot, so it is identical every time it is
downloaded, regardless of later data changes.
"""
from __future__ import annotations

import io
from datetime import date

from django.utils import formats
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.analytics.services.progress.goals import format_value
from apps.core.dates import format_minutes

INK = colors.HexColor("#18181B")
MUTED = colors.HexColor("#71717A")
LINE = colors.HexColor("#E4E4E7")
SUBTLE = colors.HexColor("#F4F4F5")
BRAND = colors.HexColor("#4F46E5")
TONES = {
    "slate": "#64748B", "indigo": "#6366F1", "blue": "#3B82F6", "sky": "#0EA5E9", "teal": "#14B8A6",
    "emerald": "#10B981", "lime": "#84CC16", "amber": "#F59E0B", "orange": "#F97316", "rose": "#F43F5E",
    "pink": "#EC4899", "violet": "#8B5CF6",
}
STATUS_COLORS = {
    "completed": "#059669", "ahead": "#059669", "on_track": "#4F46E5", "behind": "#D97706",
    "missed": "#DC2626", "paused": "#71717A", "not_started": "#71717A",
}

styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=INK, spaceBefore=6, spaceAfter=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12, textColor=INK),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK, alignment=TA_LEFT),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=INK),
    "kpi": ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=INK),
    "kpil": ParagraphStyle("kpil", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED),
}


def _status_label(status: str) -> str:
    return {
        "completed": _("Completed"), "ahead": _("Ahead"), "on_track": _("On track"), "behind": _("Behind"),
        "missed": _("Missed"), "paused": _("Paused"), "not_started": _("Not started"),
    }.get(status, status)


class _Goalish:
    """Adapter so snapshot values reuse the engine's value formatting."""

    def __init__(self, is_duration):
        self.is_duration = is_duration


def _fmt(snapshot, value):
    return format_value(value, _Goalish(snapshot.is_duration))


def _progress_bar(pct: float | None, color: str, width=40 * mm) -> Drawing:
    d = Drawing(width, 6)
    d.add(Rect(0, 1, width, 4, fillColor=SUBTLE, strokeColor=None, rx=2, ry=2))
    if pct:
        d.add(Rect(0, 1, width * max(0, min(pct, 100)) / 100, 4, fillColor=colors.HexColor(color), strokeColor=None, rx=2, ry=2))
    return d


def _status_chip(status: str) -> Drawing:
    label = _status_label(status)
    w = 6 + len(label) * 4.3
    d = Drawing(w, 12)
    c = colors.HexColor(STATUS_COLORS.get(status, "#71717A"))
    d.add(Rect(0, 0, w, 12, fillColor=colors.Color(c.red, c.green, c.blue, alpha=0.12), strokeColor=None, rx=6, ry=6))
    d.add(String(w / 2, 3.2, label, fontName="Helvetica-Bold", fontSize=7, fillColor=c, textAnchor="middle"))
    return d


def _kpis(items):
    cells = [[Paragraph(str(v), styles["kpi"]) for _l, v in items], [Paragraph(l, styles["kpil"]) for l, _v in items]]
    t = Table(cells, colWidths=[(180 * mm) / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SUBTLE), ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white),
    ]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 10 * mm, "LifeFlow · " + _("Monthly report"))
    canvas.drawRightString(195 * mm, 10 * mm, _("Page %(n)s") % {"n": doc.page})
    canvas.setStrokeColor(LINE)
    canvas.line(15 * mm, 14 * mm, 195 * mm, 14 * mm)
    canvas.restoreState()


def render_monthly_report_pdf(report) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
                            title=f"LifeFlow — {report.year}-{report.month:02d}", author="LifeFlow")
    period = formats.date_format(date(report.year, report.month, 1), "F Y")
    story = []

    head = Table([[
        Paragraph(f"<font color='#4F46E5'>●</font> LifeFlow", styles["cellb"]),
        Paragraph(_("Generated %(d)s") % {"d": formats.date_format(report.generated_at, "DATETIME_FORMAT")}, styles["small"]),
    ]], colWidths=[90 * mm, 90 * mm])
    head.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head, Spacer(1, 10 * mm)]
    story.append(Paragraph(_("Monthly report — %(period)s") % {"period": period}, styles["title"]))
    meta = f"{report.user_display_name} · {formats.date_format(report.period_start, 'SHORT_DATE_FORMAT')} – {formats.date_format(report.period_end, 'SHORT_DATE_FORMAT')} · {report.timezone}"
    if report.version > 1:
        meta += f" · v{report.version}"
    story += [Spacer(1, 2 * mm), Paragraph(meta, styles["subtitle"])]
    if report.summary.get("is_partial"):
        story += [Spacer(1, 2 * mm), Paragraph(_("Partial month: data up to %(d)s.") % {"d": report.summary.get("as_of")}, styles["small"])]
    story.append(Spacer(1, 7 * mm))

    s = report.summary
    avg = s.get("average_completion")
    story.append(_kpis([
        (_("Challenges"), s.get("challenges", 0)),
        (_("Active"), s.get("active", 0)),
        (_("Completed"), s.get("completed", 0)),
        (_("Avg. completion"), f"{avg:.0f}%" if avg is not None else "—"),
        (_("Entries"), s.get("entries", 0)),
    ]))
    story.append(Spacer(1, 8 * mm))

    snapshots = list(report.challenges.all())
    story.append(Paragraph(_("Challenges"), styles["h2"]))
    if not snapshots:
        story.append(Paragraph(_("No challenge was running during this month."), styles["body"]))
    for snap in snapshots:
        tone = TONES.get(snap.color, "#6366F1")
        unit = "" if snap.is_duration else f" {snap.unit}"
        if snap.gap is None:
            gap = "—"
        else:
            gap = ("±" if abs(snap.gap) < 0.005 else ("+" if snap.gap > 0 else "−")) + _fmt(snap, abs(snap.gap))

        def streak_text(n):
            return {
                "week": ngettext("%(n)s week", "%(n)s weeks", n),
                "month": ngettext("%(n)s month", "%(n)s months", n),
            }.get(snap.streak_unit, ngettext("%(n)s day", "%(n)s days", n)) % {"n": n}
        header = Table([[
            Paragraph(f"<font color='{tone}'>■</font>  <b>{_esc(snap.name)}</b>  <font color='#71717A' size='8'>{_esc(snap.category)}</font>", styles["body"]),
            _status_chip(snap.status),
        ]], colWidths=[150 * mm, 30 * mm])
        header.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        rows = [
            [_("Goal"), _esc(snap.goal_description), _("Progress"), f"{snap.progress:.0f}%" if snap.progress is not None else "—"],
            [_("Target (month)"), _fmt(snap, snap.goal) + unit, _("Completion rate"), f"{snap.completion_rate:.0f}%" if snap.completion_rate is not None else "—"],
            [_("Actual"), _fmt(snap, snap.actual) + unit, _("Current streak"), streak_text(snap.current_streak)],
            [_("Expected"), (_fmt(snap, snap.expected) + unit) if snap.expected is not None else "—", _("Best streak"), streak_text(snap.best_streak)],
            [_("Gap"), gap, _("Average / active day"), (_fmt(snap, snap.average) + unit) if snap.average is not None else "—"],
        ]
        table = Table([[Paragraph(str(c), styles["small"] if i % 2 == 0 else styles["cell"]) for i, c in enumerate(r)] for r in rows],
                      colWidths=[32 * mm, 58 * mm, 40 * mm, 50 * mm])
        table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        block = [header, Spacer(1, 2 * mm), _progress_bar(snap.progress, tone, 180 * mm), Spacer(1, 2 * mm), table, Spacer(1, 7 * mm)]
        story.append(KeepTogether(block))

    p = report.planner or {}
    if p.get("planned"):
        story.append(Paragraph(_("Planner"), styles["h2"]))
        rate = p.get("completion_rate")
        story.append(_kpis([
            (_("Planned"), p.get("planned", 0)),
            (_("Completed"), p.get("completed", 0)),
            (_("Partial"), p.get("partial", 0)),
            (_("Missed"), p.get("missed", 0)),
            (_("Completion"), f"{rate:.0f}%" if rate is not None else "—"),
        ]))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            _("Planned time: %(p)s · Completed time: %(d)s") % {"p": format_minutes(p.get("planned_minutes", 0)), "d": format_minutes(p.get("done_minutes", 0))},
            styles["small"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
