"""Design-system template helpers."""
from __future__ import annotations

import math

from django import template
from django.templatetags.static import static
from django.utils import formats
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.core.dates import format_minutes

register = template.Library()

STATUS_META = {
    # progress statuses
    "not_started": ("badge-neutral", "Not started"),
    "on_track": ("badge-brand", "On track"),
    "ahead": ("badge-success", "Ahead"),
    "behind": ("badge-warning", "Behind"),
    "completed": ("badge-success", "Completed"),
    "missed": ("badge-danger", "Missed"),
    "paused": ("badge-neutral", "Paused"),
    "rest_day": ("badge-info", "Rest day"),
    # challenge statuses
    "active": ("badge-brand", "Active"),
    "archived": ("badge-neutral", "Archived"),
    # planner statuses
    "planned": ("badge-neutral", "Planned"),
    "in_progress": ("badge-info", "In progress"),
    "partial": ("badge-warning", "Partially done"),
    "cancelled": ("badge-neutral", "Cancelled"),
    "rescheduled": ("badge-neutral", "Rescheduled"),
    # day statuses
    "done": ("badge-success", "Done"),
    "pending": ("badge-neutral", "To do"),
    "rest": ("badge-info", "Rest day"),
}


# Icons that point in a reading direction are mirrored in right-to-left languages.
DIRECTIONAL_ICONS = {"chevron-left", "chevron-right", "arrow-left", "arrow-right", "arrow-up-right", "log-out", "undo-2", "external-link"}


@register.simple_tag
def icon(name: str, css: str = "") -> str:
    if name in DIRECTIONAL_ICONS:
        css = f"{css} rtl-flip"
    return format_html(
        '<svg class="icon {}" aria-hidden="true" focusable="false"><use href="{}#i-{}"></use></svg>',
        css, static("icons/sprite.svg"), name,
    )


@register.simple_tag
def sprite_url() -> str:
    return static("icons/sprite.svg")


@register.filter
def status_class(status) -> str:
    return STATUS_META.get(getattr(status, "value", status), ("badge-neutral", ""))[0]


@register.filter
def status_label(status) -> str:
    key = getattr(status, "value", status)
    return _(STATUS_META.get(key, ("", str(key).replace("_", " ").capitalize()))[1])


@register.simple_tag
def status_badge(status) -> str:
    return format_html('<span class="badge {}">{}</span>', status_class(status), status_label(status))


@register.simple_tag
def ring(value, size: int = 56, stroke: int = 6, label: str | None = None, css: str = "") -> str:
    """SVG progress ring; colour follows the surrounding `tone-*` class."""
    pct = max(0.0, min(float(value or 0), 100.0))
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    offset = circ * (1 - pct / 100)
    text = label if label is not None else (f"{round(float(value))}%" if value is not None else "—")
    font = max(10, size // 4.2)
    return format_html(
        '<div class="relative inline-flex shrink-0 items-center justify-center {css}" style="width:{s}px;height:{s}px" role="img" aria-label="{t}">'
        '<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}" class="-rotate-90">'
        '<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="rgb(var(--c-subtle))" stroke-width="{w}"/>'
        '<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="rgb(var(--tone))" stroke-width="{w}" stroke-linecap="round" '
        'stroke-dasharray="{circ}" stroke-dashoffset="{off}" style="transition:stroke-dashoffset .6s ease"/></svg>'
        '<span class="absolute font-semibold tabular text-ink" style="font-size:{f}px">{t}</span></div>',
        css=css, s=size, c=size / 2, r=f"{r:.2f}", w=stroke, circ=f"{circ:.2f}", off=f"{offset:.2f}", t=text, f=int(font),
    )


@register.filter
def minutes(value) -> str:
    return format_minutes(value)


@register.filter
def trans_default(value) -> str:
    """Translate default (seeded) names; custom user names are returned unchanged."""
    return _(str(value)) if value else ""


@register.filter
def streak_label(result) -> str:
    n = result.current_streak if hasattr(result, "current_streak") else int(result or 0)
    unit = getattr(result, "streak_unit", "day")
    if unit == "week":
        return ngettext("%(n)s week", "%(n)s weeks", n) % {"n": n}
    if unit == "month":
        return ngettext("%(n)s month", "%(n)s months", n) % {"n": n}
    return ngettext("%(n)s day", "%(n)s days", n) % {"n": n}


@register.simple_tag
def streak_text(n, unit="day") -> str:
    n = int(n or 0)
    if unit == "week":
        return ngettext("%(n)s week", "%(n)s weeks", n) % {"n": n}
    if unit == "month":
        return ngettext("%(n)s month", "%(n)s months", n) % {"n": n}
    return ngettext("%(n)s day", "%(n)s days", n) % {"n": n}


@register.filter
def udate(value, user=None) -> str:
    """Date in the user's preferred format."""
    if not value:
        return ""
    fmt = "d/m/Y"
    profile = getattr(user, "profile", None) if user else None
    if profile is not None:
        fmt = profile.date_format
    return formats.date_format(value, fmt)


@register.filter
def utime(value, user=None) -> str:
    if not value:
        return ""
    profile = getattr(user, "profile", None) if user else None
    if profile is not None and profile.time_format == "12h":
        return value.strftime("%I:%M %p").lstrip("0")
    return value.strftime("%H:%M")


@register.filter
def pct(value, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{int(digits)}f}%"


@register.filter
def abs_value(value):
    try:
        return abs(value)
    except TypeError:
        return value


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def active(context, *names) -> str:
    match = getattr(context.get("request"), "resolver_match", None)
    if match is None:
        return ""
    current = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
    for n in names:
        if current == n or (n.endswith(":*") and match.namespace == n[:-2]):
            return "is-active"
    return ""


@register.filter
def json_attr(value) -> str:
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    return mark_safe(json.dumps(value, cls=DjangoJSONEncoder).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("'", "\\u0027").replace('"', "&quot;"))
