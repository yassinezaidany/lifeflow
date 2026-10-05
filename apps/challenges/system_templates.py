"""Built-in challenge templates. They are plain data for the generic engine:
nothing in the code depends on these names.

Strings are marked with N() (gettext_noop) so they are extracted for translation; they are
stored in English and translated at display time (see localize_template)."""
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop as N

SYSTEM_TEMPLATES = [
    {
        "slug": "30-days-fitness", "name": N("30 Days Fitness"), "icon": "dumbbell", "color": "rose",
        "category_name": N("Health & Fitness"), "duration_days": 30,
        "description": N("One workout a day for 30 days — gym, running, football or at home."),
        "definition": {
            "fields": [
                {"key": "type", "label": N("Activity type"), "field_type": "select", "options": [N("Gym"), N("Running"), N("Football"), N("Home workout")]},
                {"key": "duration", "label": N("Duration"), "field_type": "duration"},
            ],
            "goal": {"metric": None, "period": "daily", "aggregation": "count", "target": 1},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "running-3-week", "name": N("Running 3×/week"), "icon": "footprints", "color": "orange",
        "category_name": N("Health & Fitness"), "duration_days": 90,
        "description": N("Three runs a week, each one at least 30 minutes."),
        "definition": {
            "fields": [
                {"key": "duration", "label": N("Duration"), "field_type": "duration"},
                {"key": "distance", "label": N("Distance"), "field_type": "decimal", "unit": "km"},
            ],
            "goal": {"metric": "duration", "period": "weekly", "aggregation": "count", "target": 3, "min_per_entry": 30},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "30-days-reading", "name": N("30 Days Reading"), "icon": "book-open", "color": "indigo",
        "category_name": N("Learning"), "duration_days": 30,
        "description": N("Read 20 pages every day and keep track of your books."),
        "definition": {
            "fields": [
                {"key": "pages", "label": N("Pages"), "field_type": "integer", "unit": "pages", "required": True},
                {"key": "book", "label": N("Book"), "field_type": "text"},
            ],
            "goal": {"metric": "pages", "period": "daily", "aggregation": "sum", "target": 20},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "30-days-coding", "name": N("30 Days Coding"), "icon": "code", "color": "violet",
        "category_name": N("Learning"), "duration_days": 30,
        "description": N("Two hours of focused coding a day."),
        "definition": {
            "fields": [
                {"key": "duration", "label": N("Duration"), "field_type": "duration", "required": True},
                {"key": "topic", "label": N("Topic"), "field_type": "text"},
            ],
            "goal": {"metric": "duration", "period": "daily", "aggregation": "sum", "target": 120},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "learn-english", "name": N("Learn English"), "icon": "languages", "color": "blue",
        "category_name": N("Learning"), "duration_days": 90,
        "description": N("30 minutes of English practice per day, across all skills."),
        "definition": {
            "fields": [
                {"key": "duration", "label": N("Duration"), "field_type": "duration", "required": True},
                {"key": "skill", "label": N("Skill"), "field_type": "select", "options": [N("Vocabulary"), N("Grammar"), N("Listening"), N("Speaking"), N("Reading"), N("Writing")]},
            ],
            "goal": {"metric": "duration", "period": "daily", "aggregation": "sum", "target": 30},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "quran-reading", "name": N("Qur'an Reading"), "icon": "book-marked", "color": "emerald",
        "category_name": N("Spiritual"), "duration_days": None,
        "description": N("Read a few pages of the Qur'an every day."),
        "definition": {
            "fields": [
                {"key": "pages", "label": N("Pages"), "field_type": "integer", "unit": "pages", "required": True},
                {"key": "surah", "label": N("Surah"), "field_type": "text"},
                {"key": "juz", "label": N("Juz"), "field_type": "integer"},
            ],
            "goal": {"metric": "pages", "period": "daily", "aggregation": "sum", "target": 2},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "fajr-on-time", "name": N("Fajr on time"), "icon": "sunrise", "color": "teal",
        "category_name": N("Spiritual"), "duration_days": 30,
        "description": N("Pray Fajr on time every day and track your wake-up time."),
        "definition": {
            "fields": [
                {"key": "done", "label": N("Prayed on time"), "field_type": "boolean", "required": True},
                {"key": "wake_up", "label": N("Wake-up time"), "field_type": "time"},
            ],
            "goal": {"metric": "done", "period": "daily", "aggregation": "count", "target": 1},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "early-riser", "name": N("Early riser"), "icon": "alarm-clock", "color": "amber",
        "category_name": N("Productivity"), "duration_days": 30,
        "description": N("Wake up before 06:00 every day — log your wake-up time."),
        "definition": {
            "fields": [{"key": "wake_up", "label": N("Wake-up time"), "field_type": "time", "required": True}],
            "goal": {"metric": "wake_up", "period": "daily", "aggregation": "count", "target": 1,
                     "time_comparison": "before", "time_threshold": "06:00"},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "screen-time-limit", "name": N("Screen time limit"), "icon": "smartphone", "color": "violet",
        "category_name": N("Digital Wellbeing"), "duration_days": 30,
        "description": N("Keep your recreational screen time under 2 hours a day."),
        "definition": {
            "fields": [{"key": "screen_time", "label": N("Screen time"), "field_type": "duration", "required": True}],
            "goal": {"metric": "screen_time", "period": "daily", "aggregation": "sum", "target": 120, "direction": "at_most"},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "digital-detox", "name": N("Digital Detox"), "icon": "smartphone", "color": "sky",
        "category_name": N("Digital Wellbeing"), "duration_days": 30,
        "description": N("A day without social media counts as a win."),
        "definition": {
            "fields": [
                {"key": "done", "label": N("No social media"), "field_type": "boolean", "required": True},
                {"key": "screen_time", "label": N("Screen time"), "field_type": "duration"},
            ],
            "goal": {"metric": "done", "period": "daily", "aggregation": "count", "target": 1},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "daily-walking", "name": N("Daily Walking"), "icon": "footprints", "color": "lime",
        "category_name": N("Health & Fitness"), "duration_days": 30,
        "description": N("10,000 steps a day."),
        "definition": {
            "fields": [{"key": "steps", "label": N("Steps"), "field_type": "integer", "unit": "steps", "required": True}],
            "goal": {"metric": "steps", "period": "daily", "aggregation": "sum", "target": 10000},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "water-challenge", "name": N("Water Challenge"), "icon": "glass-water", "color": "sky",
        "category_name": N("Wellness"), "duration_days": 30,
        "description": N("Drink 2 litres of water every day."),
        "definition": {
            "fields": [{"key": "water", "label": N("Water"), "field_type": "decimal", "unit": "L", "required": True}],
            "goal": {"metric": "water", "period": "daily", "aggregation": "sum", "target": 2},
            "schedule": {"frequency": "daily"},
        },
    },
]


def localize_template(data: dict) -> dict:
    """Translate a built-in template's texts into the active language (copy; the DB keeps English)."""
    description = data.get("description") or ""
    data = {**data, "name": _(data["name"]), "description": _(description) if description else ""}
    if data.get("category_name"):
        data["category_name"] = _(data["category_name"])
    definition = dict(data.get("definition") or {})
    definition["fields"] = [
        {**f, "label": _(f["label"]), **({"options": [_(o) for o in f["options"]]} if f.get("options") else {})}
        for f in definition.get("fields", [])
    ]
    data["definition"] = definition
    return data


def sync_system_templates(ChallengeTemplate) -> int:
    for order, t in enumerate(SYSTEM_TEMPLATES):
        ChallengeTemplate.objects.update_or_create(
            owner=None, slug=t["slug"],
            defaults={**{k: v for k, v in t.items() if k != "slug"}, "order": order, "is_public": True},
        )
    return len(SYSTEM_TEMPLATES)
