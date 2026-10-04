"""PDF rendering of a MonthlyReport snapshot (ReportLab, pure Python — no system deps).

The PDF is rendered from the frozen snapshot, so its figures are identical every time
it is downloaded, regardless of later data changes.

Text is set in DejaVu Sans (embedded TTF covering Latin, accents and Arabic). Arabic
strings are shaped (arabic-reshaper) and reordered (python-bidi) because ReportLab
has no complex-script layout engine; when the interface language is right-to-left
the layout is mirrored.
"""
from __future__ import annotations

import io
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from django.utils import formats
from django.utils.translation import get_language_bidi
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.analytics.services.progress.goals import format_value
from apps.core.dates import format_minutes

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
REGULAR, BOLD = "LF-Sans", "LF-Sans-Bold"

INK = colors.HexColor("#18181B")
MUTED = colors.HexColor("#71717A")
LINE = colors.HexColor("#E4E4E7")
SUBTLE = colors.HexColor("#F4F4F5")
TONES = {
    "slate": "#64748B", "indigo": "#6366F1", "blue": "#3B82F6", "sky": "#0EA5E9", "teal": "#14B8A6",
    "emerald": "#10B981", "lime": "#84CC16", "amber": "#F59E0B", "orange": "#F97316", "rose": "#F43F5E",
    "pink": "#EC4899", "violet": "#8B5CF6",
}
STATUS_COLORS = {
    "completed": "#059669", "ahead": "#059669", "on_track": "#4F46E5", "behind": "#D97706",
    "missed": "#DC2626", "paused": "#71717A", "not_started": "#71717A",
}
ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


@lru_cache(maxsize=1)
def _register_fonts() -> tuple[str, str]:
    """Embed DejaVu Sans; fall back to Helvetica if the font files are missing."""
    try:
        pdfmetrics.registerFont(TTFont(REGULAR, str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD, italic=REGULAR, boldItalic=BOLD)
        return REGULAR, BOLD
    except Exception:  # pragma: no cover - fonts are shipped in the repository
        return "Helvetica", "Helvetica-Bold"


def shape(text) -> str:
    """Visual-order Arabic for ReportLab (no-op for other scripts)."""
    text = "" if text is None else str(text)
    if not ARABIC.search(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:  # pragma: no cover - optional dependency
        return text
    return get_display(arabic_reshaper.reshape(text))


def S(text) -> str:
    """Shape then escape a plain string so it can be embedded in Paragraph markup."""
    return shape(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _styles(rtl: bool) -> dict:
    regular, bold = _register_fonts()
    align = TA_RIGHT if rtl else TA_LEFT

    def st(name, font, size, leading, color=INK, **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading, textColor=color, alignment=align, **kw)

    return {
        "title": st("title", bold, 20, 26),
        "subtitle": st("subtitle", regular, 10, 14, MUTED),
        "h2": st("h2", bold, 12, 16, spaceBefore=6, spaceAfter=6),
        "body": st("body", regular, 9, 12),
        "small": st("small", regular, 8, 10.5, MUTED),
        "cell": st("cell", regular, 8.5, 11),
        "cellb": st("cellb", bold, 9, 11),
        "kpi": st("kpi", bold, 16, 19),
        "kpil": st("kpil", regular, 8, 10, MUTED),
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


def _progress_bar(pct: float | None, color: str, width: float, rtl: bool) -> Drawing:
    d = Drawing(width, 6)
    d.add(Rect(0, 1, width, 4, fillColor=SUBTLE, strokeColor=None, rx=2, ry=2))
    if pct:
        filled = width * max(0, min(pct, 100)) / 100
        d.add(Rect(width - filled if rtl else 0, 1, filled, 4, fillColor=colors.HexColor(color), strokeColor=None, rx=2, ry=2))
    return d


def _status_chip(status: str) -> Drawing:
    _regular, bold = _register_fonts()
    label = shape(_status_label(status))
    w = 8 + pdfmetrics.stringWidth(label, bold, 7)
    d = Drawing(w, 12)
    c = colors.HexColor(STATUS_COLORS.get(status, "#71717A"))
    d.add(Rect(0, 0, w, 12, fillColor=colors.Color(c.red, c.green, c.blue, alpha=0.12), strokeColor=None, rx=6, ry=6))
    d.add(String(w / 2, 3.2, label, fontName=bold, fontSize=7, fillColor=c, textAnchor="middle"))
    return d


def _row(cells, rtl):
    return list(reversed(cells)) if rtl else list(cells)


def _kpis(items, styles, rtl):
    items = _row(items, rtl)
    cells = [[Paragraph(S(v), styles["kpi"]) for _l, v in items], [Paragraph(S(label), styles["kpil"]) for label, _v in items]]
    t = Table(cells, colWidths=[(180 * mm) / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SUBTLE), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white),
    ]))
    return t


def _footer_factory(rtl: bool):
    def footer(canvas, doc):
        regular, _bold = _register_fonts()
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(MUTED)
        left, right = "LifeFlow · " + shape(_("Monthly report")), shape(_("Page %(n)s") % {"n": doc.page})
        if rtl:
            left, right = right, left
        canvas.drawString(15 * mm, 10 * mm, left)
        canvas.drawRightString(195 * mm, 10 * mm, right)
        canvas.setStrokeColor(LINE)
        canvas.line(15 * mm, 14 * mm, 195 * mm, 14 * mm)
        canvas.restoreState()
    return footer


def render_monthly_report_pdf(report) -> bytes:
    rtl = get_language_bidi()
    styles = _styles(rtl)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
                            title=f"LifeFlow — {report.year}-{report.month:02d}", author="LifeFlow")
    period = formats.date_format(date(report.year, report.month, 1), "F Y")
    story = []

    brand = Paragraph("<font color='#4F46E5'>●</font> LifeFlow", styles["cellb"])
    generated = Paragraph(S(_("Generated %(d)s") % {"d": formats.date_format(report.generated_at, "DATETIME_FORMAT")}), styles["small"])
    head = Table([_row([brand, generated], rtl)], colWidths=[90 * mm, 90 * mm])
    head.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head, Spacer(1, 10 * mm)]
    story.append(Paragraph(S(_("Monthly report — %(period)s") % {"period": period}), styles["title"]))
    meta = f"{report.user_display_name} · {formats.date_format(report.period_start, 'SHORT_DATE_FORMAT')} – {formats.date_format(report.period_end, 'SHORT_DATE_FORMAT')} · {report.timezone}"
    if report.version > 1:
        meta += f" · v{report.version}"
    story += [Spacer(1, 2 * mm), Paragraph(S(meta), styles["subtitle"])]
    if report.summary.get("is_partial"):
        story += [Spacer(1, 2 * mm), Paragraph(S(_("Partial month: data up to %(d)s.") % {"d": report.summary.get("as_of")}), styles["small"])]
    story.append(Spacer(1, 7 * mm))

    s = report.summary
    avg = s.get("average_completion")
    story.append(_kpis([
        (_("Challenges"), s.get("challenges", 0)),
        (_("Active"), s.get("active", 0)),
        (_("Completed"), s.get("completed", 0)),
        (_("Avg. completion"), f"{avg:.0f}%" if avg is not None else "—"),
        (_("Entries"), s.get("entries", 0)),
    ], styles, rtl))
    story.append(Spacer(1, 8 * mm))

    snapshots = list(report.challenges.all())
    story.append(Paragraph(S(_("Challenges")), styles["h2"]))
    if not snapshots:
        story.append(Paragraph(S(_("No challenge was running during this month.")), styles["body"]))
    for snap in snapshots:
        tone = TONES.get(snap.color, "#6366F1")
        unit = "" if snap.is_duration else f" {snap.unit}"
        if snap.gap is None:
            gap = "—"
        else:
            gap = ("±" if abs(snap.gap) < 0.005 else ("+" if snap.gap > 0 else "−")) + _fmt(snap, abs(snap.gap))

        def streak_text(n, unit_name=snap.streak_unit):
            return {
                "week": ngettext("%(n)s week", "%(n)s weeks", n),
                "month": ngettext("%(n)s month", "%(n)s months", n),
            }.get(unit_name, ngettext("%(n)s day", "%(n)s days", n)) % {"n": n}

        title_markup = f"<font color='{tone}'>■</font>  <b>{S(snap.name)}</b>  <font color='#71717A' size='8'>{S(snap.category)}</font>"
        if rtl:
            title_markup = f"<font color='#71717A' size='8'>{S(snap.category)}</font>  <b>{S(snap.name)}</b>  <font color='{tone}'>■</font>"
        header = Table([_row([Paragraph(title_markup, styles["body"]), _status_chip(snap.status)], rtl)],
                       colWidths=[30 * mm, 150 * mm] if rtl else [150 * mm, 30 * mm])
        header.setStyle(TableStyle([("ALIGN", (0 if rtl else 1, 0), (0 if rtl else 1, 0), "LEFT" if rtl else "RIGHT"),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        rows = [
            [_("Goal"), snap.goal_description, _("Progress"), f"{snap.progress:.0f}%" if snap.progress is not None else "—"],
            [_("Target (month)"), _fmt(snap, snap.goal) + unit, _("Completion rate"), f"{snap.completion_rate:.0f}%" if snap.completion_rate is not None else "—"],
            [_("Actual"), _fmt(snap, snap.actual) + unit, _("Current streak"), streak_text(snap.current_streak)],
            [_("Expected"), (_fmt(snap, snap.expected) + unit) if snap.expected is not None else "—", _("Best streak"), streak_text(snap.best_streak)],
            [_("Gap"), gap, _("Average / active day"), (_fmt(snap, snap.average) + unit) if snap.average is not None else "—"],
        ]
        widths = [32 * mm, 58 * mm, 40 * mm, 50 * mm]
        table = Table(
            [_row([Paragraph(S(c), styles["small"] if i % 2 == 0 else styles["cell"]) for i, c in enumerate(r)], rtl) for r in rows],
            colWidths=_row(widths, rtl),
        )
        table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        block = [header, Spacer(1, 2 * mm), _progress_bar(snap.progress, tone, 180 * mm, rtl), Spacer(1, 2 * mm), table, Spacer(1, 7 * mm)]
        story.append(KeepTogether(block))

    p = report.planner or {}
    if p.get("planned"):
        story.append(Paragraph(S(_("Planner")), styles["h2"]))
        rate = p.get("completion_rate")
        story.append(_kpis([
            (_("Planned"), p.get("planned", 0)),
            (_("Completed"), p.get("completed", 0)),
            (_("Partial"), p.get("partial", 0)),
            (_("Missed"), p.get("missed", 0)),
            (_("Completion"), f"{rate:.0f}%" if rate is not None else "—"),
        ], styles, rtl))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(S(
            _("Planned time: %(p)s · Completed time: %(d)s") % {"p": format_minutes(p.get("planned_minutes", 0)), "d": format_minutes(p.get("done_minutes", 0))}
        ), styles["small"]))

    footer = _footer_factory(rtl)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
