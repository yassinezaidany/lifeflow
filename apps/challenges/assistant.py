"""Natural-language challenge assistant.

"Je veux apprendre Python 2 heures par jour pendant 30 jours" → a *suggested* wizard
payload (name, fields, goal, schedule, period). Nothing is ever created here: the
suggestion pre-fills the creation wizard and the user reviews and confirms each step.

Two engines:
* **Claude** (when ANTHROPIC_API_KEY is configured) — one schema-constrained call;
* **rule-based parser** (FR / EN / AR) — always available, used as fallback.
Every suggestion goes through `sanitize()` so the wizard only receives valid values.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata

from django.conf import settings

from apps.core.icons import picker_icons

from .defaults import DEFAULT_CHALLENGE_CATEGORIES
from .models import COLOR_CHOICES, Goal, Schedule, TrackingField

logger = logging.getLogger("lifeflow")

COLORS = [c for c, _l in COLOR_CHOICES]
CATEGORIES = [name for name, _i, _c in DEFAULT_CHALLENGE_CATEGORIES]
FIELD_TYPES = [t for t, _l in TrackingField.FieldType.choices]
MAX_TEXT = 500

# ---------------------------------------------------------------------------- Claude engine
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "description", "category", "icon", "color", "duration_days", "fields", "goal", "schedule"],
    "properties": {
        "name": {"type": "string", "description": "Short challenge name in the user's language, e.g. 'Learn Python'"},
        "description": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "icon": {"type": "string", "description": "One of the allowed icon names"},
        "color": {"type": "string", "enum": COLORS},
        "duration_days": {"type": ["integer", "null"], "description": "Challenge length in days, null if open-ended"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "label", "field_type", "unit", "options"],
                "properties": {
                    "key": {"type": "string", "description": "snake_case identifier"},
                    "label": {"type": "string"},
                    "field_type": {"type": "string", "enum": FIELD_TYPES},
                    "unit": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "goal": {
            "type": "object",
            "additionalProperties": False,
            "required": ["metric", "period", "aggregation", "target", "min_per_entry"],
            "properties": {
                "metric": {"type": ["string", "null"], "description": "key of the measured field, or null to count sessions"},
                "period": {"type": "string", "enum": [p for p, _l in Goal.Period.choices]},
                "aggregation": {"type": "string", "enum": [a for a, _l in Goal.Aggregation.choices]},
                "target": {"type": "number"},
                "min_per_entry": {"type": ["number", "null"]},
            },
        },
        "schedule": {
            "type": "object",
            "additionalProperties": False,
            "required": ["frequency", "weekdays", "interval_days"],
            "properties": {
                "frequency": {"type": "string", "enum": [f for f, _l in Schedule.Frequency.choices]},
                "weekdays": {"type": "array", "items": {"type": "integer"}, "description": "0=Monday … 6=Sunday"},
                "interval_days": {"type": "integer"},
            },
        },
    },
}

SYSTEM_PROMPT = """You turn a person's description of a personal goal into the configuration of a habit-tracking challenge.

How the tracker works:
- Each challenge has fields the person fills in each time they record progress. Types: boolean (done / not done), integer, decimal, duration (always in MINUTES), time (time of day), text, select (fixed options).
- The goal measures one field ("metric") or, with metric null, counts recorded sessions. aggregation "sum" adds up the metric's values; "count" counts entries (optionally only those reaching min_per_entry). A boolean metric always uses "count" with target 1 per day for "every day" habits.
- period: daily, weekly, monthly or total. Durations are in minutes: "2 hours per day" is a duration field with target 120.
- schedule: "daily" (every day), "weekdays" (specific days, 0=Monday … 6=Sunday) or "interval" (every N days). Use weekdays only when the person names days.
- duration_days: total length if stated ("for 30 days" → 30, "for 3 months" → 90, "for a year" → 365), otherwise null.

Write name, description, labels and options in the same language as the person (French, English or Arabic). Keep the name short (2–5 words). Add one or two useful optional fields only when they clearly help (e.g. a "Subject" text field for learning). Pick the closest category, an icon from the allowed list, and a fitting color."""


def _claude_suggest(text: str) -> dict | None:
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic(api_key=api_key, timeout=30.0, max_retries=1)
    user = f"Allowed icons: {', '.join(picker_icons())}\n\nDescription:\n{text}"
    try:
        response = client.beta.messages.create(
            model=settings.ASSISTANT_MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIConnectionError:
        logger.warning("Assistant: Claude unreachable, using rule-based parser")
        return None
    except anthropic.RateLimitError:
        logger.warning("Assistant: rate limited, using rule-based parser")
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("Assistant: Claude API error %s, using rule-based parser", exc.status_code)
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        return None
    payload = next((b.text for b in response.content if b.type == "text"), None)
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------- rule-based engine
def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text).strip()


NUM = r"(\d+(?:[.,]\d+)?)"
WORD_NUMBERS = {
    "un": 1, "une": 1, "one": 1, "deux": 2, "two": 2, "trois": 3, "three": 3, "quatre": 4, "four": 4,
    "cinq": 5, "five": 5, "six": 6, "sept": 7, "seven": 7, "huit": 8, "eight": 8, "dix": 10, "ten": 10, "twenty": 20, "vingt": 20,
    "واحد": 1, "مرة": 1, "مرتين": 2, "ثلاث": 3, "ثلاثة": 3, "أربع": 4, "خمس": 5, "عشر": 10,
}

UNITS = [  # (regex, kind, label key, unit, multiplier)
    (r"(heures?|hours?|hrs?|h|ساعات|ساعة)\b", "duration", "duration", "", 60),
    (r"(minutes?|mins?|mn|دقائق|دقيقة)\b", "duration", "duration", "", 1),
    (r"(pages?|صفحات|صفحة)\b", "integer", "pages", "pages", 1),
    (r"(pas|steps?|خطوات|خطوة)\b", "integer", "steps", "steps", 1),
    (r"(litres?|liters?|l|لترات|لتر)\b", "decimal", "water", "L", 1),
    (r"(verres?|glasses?|أكواب|كوب)\b", "integer", "glasses", "glasses", 1),
    (r"(km|kilom[eè]tres?|kilometers?|كلم|كيلومتر)\b", "decimal", "distance", "km", 1),
    (r"(fois|times?|s[ée]ances?|sessions?|workouts?|entra[iî]nements?|مرات|مرة|حصص|حصة)\b", "sessions", None, "", 1),
]
LABELS = {
    "fr": {"duration": "Durée", "pages": "Pages", "steps": "Pas", "water": "Eau", "glasses": "Verres", "distance": "Distance", "done": "Fait", "notes": "Notes"},
    "en": {"duration": "Duration", "pages": "Pages", "steps": "Steps", "water": "Water", "glasses": "Glasses", "distance": "Distance", "done": "Done", "notes": "Notes"},
    "ar": {"duration": "المدة", "pages": "الصفحات", "steps": "الخطوات", "water": "الماء", "glasses": "الأكواب", "distance": "المسافة", "done": "تم", "notes": "ملاحظات"},
}
PERIODS = [
    (r"(par jour|chaque jour|tous les jours|quotidien\w*|/ ?jour|per day|a day|every day|daily|each day|/ ?day|يوميا|يومياً|في اليوم|كل يوم)", "daily"),
    (r"(par semaine|chaque semaine|hebdo\w*|/ ?semaine|per week|a week|every week|weekly|/ ?week|أسبوعيا|في الأسبوع|كل أسبوع)", "weekly"),
    (r"(par mois|chaque mois|mensuel\w*|/ ?mois|per month|a month|every month|monthly|شهريا|في الشهر|كل شهر)", "monthly"),
    (r"(au total|en tout|in total|overall|altogether|في المجموع|إجمالا)", "total"),
]
SPAN = [
    (r"(\d+)\s*(jours?|days?|أيام|يوما|يوم)", 1),
    (r"(\d+)\s*(semaines?|weeks?|أسابيع|أسبوع)", 7),
    (r"(\d+)\s*(mois|months?|أشهر|شهور|شهر)", 30),
    (r"(\d+)\s*(ans?|ann[ée]es?|years?|سنوات|سنة)", 365),
    (r"(un an|une ann[ée]e|a year|one year|سنة كاملة)", 365),
    (r"(un mois|a month|one month|شهر واحد)", 30),
]
WEEKDAYS = [
    (r"\b(lundis?|mondays?)\b|الاثنين|الإثنين", 0), (r"\b(mardis?|tuesdays?)\b|الثلاثاء", 1),
    (r"\b(mercredis?|wednesdays?)\b|الأربعاء", 2), (r"\b(jeudis?|thursdays?)\b|الخميس", 3),
    (r"\b(vendredis?|fridays?)\b|الجمعة", 4), (r"\b(samedis?|saturdays?)\b|السبت", 5),
    (r"\b(dimanches?|sundays?)\b|الأحد", 6),
]
THEMES = [  # keyword regex → (category, icon, color)
    (r"python|code|coder|coding|program|développ|javascript|django|برمج", ("Learning", "code", "violet")),
    (r"anglais|english|langue|language|espagnol|spanish|arabe|vocab|إنجليزي|لغة", ("Learning", "languages", "blue")),
    (r"coran|quran|qur'?an|القرآن|قرآن", ("Spiritual", "book-marked", "emerald")),
    (r"fajr|pri[eè]re|prayer|pray|salat|صلاة|الفجر", ("Spiritual", "sunrise", "teal")),
    (r"lire|lecture|livre|read|book|قراءة|كتاب|اقرأ", ("Learning", "book-open", "indigo")),
    (r"courir|course|run|jogging|جري", ("Health & Fitness", "footprints", "orange")),
    (r"marcher|marche|walk|steps|\bpas\b|مشي|خطوات", ("Health & Fitness", "footprints", "lime")),
    (r"eau|water|boire|drink|ماء|شرب", ("Wellness", "glass-water", "sky")),
    (r"sport|gym|muscu|workout|entraîn|fitness|football|رياضة|تمرين", ("Health & Fitness", "dumbbell", "rose")),
    (r"dormir|sommeil|sleep|نوم", ("Wellness", "bed", "slate")),
    (r"méditer|méditation|meditat|تأمل", ("Wellness", "leaf", "teal")),
    (r"réseaux|social media|instagram|tiktok|écran|screen|téléphone|phone|هاتف", ("Digital Wellbeing", "smartphone", "sky")),
    (r"[ée]conom|épargn|save money|saving|budget|argent|money|مال|ادخار", ("Finance", "piggy-bank", "lime")),
    (r"étudier|study|réviser|revise|cours|exam|دراسة|مراجعة", ("Learning", "graduation-cap", "indigo")),
]
LEAD_INS = [
    r"^(je (veux|voudrais|souhaite|vais)|j'?aimerais|j'?ai envie de|objectif ?:?|mon objectif est de)\s+",
    r"^(i (want|would like|wanna|need|plan) to|i'?d like to|goal ?:?|my goal is to)\s+",
    r"^(أريد أن|أريد|أود أن|هدفي أن|هدفي)\s*",
]


def detect_language(text: str) -> str:
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    t = f" {_norm(text)} "
    fr_markers = [" je ", " par ", " jour", " pendant ", " semaine", " heures", " lire ", " apprendre ", " fois ", " chaque ", " j'"]
    return "fr" if sum(m in t for m in fr_markers) >= 1 else "en"


def _to_float(value: str) -> float:
    return float(value.replace(",", "."))


def rule_based_suggest(text: str) -> dict:
    lang = detect_language(text)
    labels = LABELS[lang]
    t = _norm(text)
    for word, n in WORD_NUMBERS.items():  # "deux heures" → "2 heures"
        t = re.sub(rf"(?<![\w؀-ۿ]){re.escape(word)}(?=\s)", str(n), t)

    # Period length ("pendant 30 jours") — removed before reading the main quantity.
    duration_days = None
    span_text = t
    for rx, mult in SPAN:
        m = re.search(r"(pendant|durant|sur|for|during|over|لمدة|خلال)\s+" + rx, t) or (re.search(rx, t) if mult > 1 else None)
        if m:
            groups = [g for g in m.groups() if g and g.isdigit()]
            duration_days = int(groups[0]) * mult if groups else mult
            span_text = t.replace(m.group(0), " ")
            break

    period = next((p for rx, p in PERIODS if re.search(rx, span_text)), None)
    weekdays = sorted({d for rx, d in WEEKDAYS if re.search(rx, span_text)})

    minimum = None
    m_min = re.search(r"(au moins|minimum|at least|min\.?|على الأقل)\s*" + NUM + r"\s*(minutes?|mins?|mn|heures?|hours?|h|دقيقة|ساعة)", span_text)
    if m_min:
        minimum = _to_float(m_min.group(2)) * (60 if re.match(r"h|heure|hour|ساعة", m_min.group(3)) else 1)
        span_text = span_text.replace(m_min.group(0), " ")

    quantity = None
    for m in re.finditer(NUM + r"\s*", span_text):
        rest = span_text[m.end():]
        for rx, kind, key, unit, mult in UNITS:
            if re.match(rx, rest):
                quantity = (_to_float(m.group(1)) * mult, kind, key, unit)
                break
        if quantity:
            break

    fields, metric, aggregation, target = [], None, Goal.Aggregation.SUM, 1.0
    if quantity is None:  # a yes/no habit ("méditer chaque jour", "no social media")
        fields.append({"key": "done", "label": labels["done"], "field_type": "boolean", "unit": "", "options": []})
        metric, aggregation, target = "done", Goal.Aggregation.COUNT, 1.0
    else:
        value, kind, key, unit = quantity
        target = value
        if kind == "sessions":
            aggregation = Goal.Aggregation.COUNT
            if minimum:
                fields.append({"key": "duration", "label": labels["duration"], "field_type": "duration", "unit": "", "options": []})
                metric = "duration"
        else:
            fields.append({"key": key, "label": labels[key], "field_type": kind, "unit": unit, "options": []})
            metric = key
            if minimum and kind == "duration":
                aggregation = Goal.Aggregation.COUNT
    if period is None:
        period = "weekly" if (quantity and quantity[1] == "sessions") else "daily"

    category, icon, color = next((theme for rx, theme in THEMES if re.search(rx, t)), ("Other", "target", "indigo"))
    if any(f["field_type"] == "duration" for f in fields) and category == "Learning":
        fields.append({"key": "subject", "label": {"fr": "Sujet", "en": "Subject", "ar": "الموضوع"}[lang], "field_type": "text", "unit": "", "options": []})

    return {
        "name": _guess_name(text),
        "description": text.strip()[:300],
        "category": category, "icon": icon, "color": color,
        "duration_days": duration_days,
        "fields": fields,
        "goal": {"metric": metric, "period": period, "aggregation": aggregation, "target": target, "min_per_entry": minimum},
        "schedule": {"frequency": "weekdays" if weekdays else "daily", "weekdays": weekdays, "interval_days": 1},
    }


def _guess_name(text: str) -> str:
    name = text.strip().rstrip(".!")
    for rx in LEAD_INS:
        name = re.sub(rx, "", name, flags=re.IGNORECASE)
    # cut at the first quantity / period expression
    cut = re.search(r"\s(\d|chaque|tous|par|pendant|every|per|for|daily|each|a day|كل|لمدة|يوميا)", name, flags=re.IGNORECASE)
    if cut and cut.start() > 2:
        name = name[: cut.start()]
    name = re.sub(r"\s+", " ", name).strip(" ,;:-")
    words = name.split(" ")
    name = " ".join(words[:5]) if words else ""
    return (name[:1].upper() + name[1:])[:100] if name else "My challenge"


# ---------------------------------------------------------------------------- sanitizer
def _slug(value: str, fallback: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()).strip("_")
    return (value or fallback)[:36]


def sanitize(data: dict) -> dict:
    """Coerce any engine output into values the wizard accepts (never trust model output)."""
    icons = set(picker_icons())
    fields, seen = [], set()
    for i, f in enumerate((data.get("fields") or [])[:8]):
        ftype = f.get("field_type") if f.get("field_type") in FIELD_TYPES else "text"
        label = str(f.get("label") or f"Field {i + 1}")[:60]
        key = _slug(str(f.get("key") or label), f"field_{i + 1}")
        while key in seen:
            key = f"{key}_{i}"
        seen.add(key)
        options = [str(o)[:60] for o in (f.get("options") or []) if str(o).strip()][:20] if ftype == "select" else []
        if ftype == "select" and not options:
            ftype = "text"
        fields.append({"key": key, "ref": key, "label": label, "field_type": ftype, "unit": str(f.get("unit") or "")[:20], "options": options})
    by_key = {f["key"]: f for f in fields}

    goal = data.get("goal") or {}
    metric = _slug(str(goal.get("metric")), "") if goal.get("metric") else None
    if metric not in by_key or by_key[metric]["field_type"] not in TrackingField.MEASURABLE_TYPES or by_key[metric]["field_type"] == "time":
        metric = None
    period = goal.get("period") if goal.get("period") in Goal.Period.values else "daily"
    aggregation = goal.get("aggregation") if goal.get("aggregation") in Goal.Aggregation.values else "sum"
    if metric is None or by_key[metric]["field_type"] == "boolean":
        aggregation = "count"
    try:
        target = max(min(float(goal.get("target") or 1), 1_000_000), 0.01)
    except (TypeError, ValueError):
        target = 1.0
    try:
        minimum = float(goal["min_per_entry"]) if goal.get("min_per_entry") not in (None, "") else None
    except (TypeError, ValueError):
        minimum = None
    if metric is None or by_key[metric]["field_type"] == "boolean":
        minimum = None

    sched = data.get("schedule") or {}
    frequency = sched.get("frequency") if sched.get("frequency") in Schedule.Frequency.values else "daily"
    weekdays = sorted({int(d) for d in (sched.get("weekdays") or []) if str(d).lstrip("-").isdigit() and 0 <= int(d) <= 6})
    if frequency == "weekdays" and not weekdays:
        frequency = "daily"
    try:
        interval = max(min(int(sched.get("interval_days") or 1), 365), 1)
    except (TypeError, ValueError):
        interval = 1
    if frequency == "interval" and interval < 2:
        interval = 2

    try:
        duration = int(data["duration_days"]) if data.get("duration_days") not in (None, "") else None
        duration = duration if duration and 1 <= duration <= 366 * 5 else None
    except (TypeError, ValueError):
        duration = None

    return {
        "name": str(data.get("name") or "My challenge").strip()[:100],
        "description": str(data.get("description") or "")[:2000],
        "category_name": data.get("category") if data.get("category") in CATEGORIES else "Other",
        "icon": data.get("icon") if data.get("icon") in icons else "target",
        "color": data.get("color") if data.get("color") in COLORS else "indigo",
        "duration_days": duration,
        "definition": {
            "fields": fields,
            "goal": {"metric": metric, "period": period, "aggregation": aggregation, "target": round(target, 2), "min_per_entry": minimum},
            "schedule": {"frequency": frequency, "weekdays": weekdays if frequency == "weekdays" else [], "interval_days": interval if frequency == "interval" else 1},
        },
    }


def suggest_challenge(text: str) -> dict:
    text = (text or "").strip()[:MAX_TEXT]
    raw = _claude_suggest(text)
    source = "ai" if raw else "rules"
    if raw is None:
        raw = rule_based_suggest(text)
    result = sanitize(raw)
    result["source"] = source
    return result
