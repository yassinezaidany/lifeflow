"""Built-in challenge templates. They are plain data for the generic engine:
nothing in the code depends on these names."""

SYSTEM_TEMPLATES = [
    {
        "slug": "30-days-fitness", "name": "30 Days Fitness", "icon": "dumbbell", "color": "rose",
        "category_name": "Health & Fitness", "duration_days": 30,
        "description": "One workout a day for 30 days — gym, running, football or at home.",
        "definition": {
            "fields": [
                {"key": "type", "label": "Activity type", "field_type": "select", "options": ["Gym", "Running", "Football", "Home workout"]},
                {"key": "duration", "label": "Duration", "field_type": "duration"},
            ],
            "goal": {"metric": None, "period": "daily", "aggregation": "count", "target": 1},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "running-3-week", "name": "Running 3×/week", "icon": "footprints", "color": "orange",
        "category_name": "Health & Fitness", "duration_days": 90,
        "description": "Three runs a week, each one at least 30 minutes.",
        "definition": {
            "fields": [
                {"key": "duration", "label": "Duration", "field_type": "duration"},
                {"key": "distance", "label": "Distance", "field_type": "decimal", "unit": "km"},
            ],
            "goal": {"metric": "duration", "period": "weekly", "aggregation": "count", "target": 3, "min_per_entry": 30},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "30-days-reading", "name": "30 Days Reading", "icon": "book-open", "color": "indigo",
        "category_name": "Learning", "duration_days": 30,
        "description": "Read 20 pages every day and keep track of your books.",
        "definition": {
            "fields": [
                {"key": "pages", "label": "Pages", "field_type": "integer", "unit": "pages", "required": True},
                {"key": "book", "label": "Book", "field_type": "text"},
            ],
            "goal": {"metric": "pages", "period": "daily", "aggregation": "sum", "target": 20},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "30-days-coding", "name": "30 Days Coding", "icon": "code", "color": "violet",
        "category_name": "Learning", "duration_days": 30,
        "description": "Two hours of focused coding a day.",
        "definition": {
            "fields": [
                {"key": "duration", "label": "Duration", "field_type": "duration", "required": True},
                {"key": "topic", "label": "Topic", "field_type": "text"},
            ],
            "goal": {"metric": "duration", "period": "daily", "aggregation": "sum", "target": 120},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "learn-english", "name": "Learn English", "icon": "languages", "color": "blue",
        "category_name": "Learning", "duration_days": 90,
        "description": "30 minutes of English practice per day, across all skills.",
        "definition": {
            "fields": [
                {"key": "duration", "label": "Duration", "field_type": "duration", "required": True},
                {"key": "skill", "label": "Skill", "field_type": "select", "options": ["Vocabulary", "Grammar", "Listening", "Speaking", "Reading", "Writing"]},
            ],
            "goal": {"metric": "duration", "period": "daily", "aggregation": "sum", "target": 30},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "quran-reading", "name": "Qur'an Reading", "icon": "book-marked", "color": "emerald",
        "category_name": "Spiritual", "duration_days": None,
        "description": "Read a few pages of the Qur'an every day.",
        "definition": {
            "fields": [
                {"key": "pages", "label": "Pages", "field_type": "integer", "unit": "pages", "required": True},
                {"key": "surah", "label": "Surah", "field_type": "text"},
                {"key": "juz", "label": "Juz", "field_type": "integer"},
            ],
            "goal": {"metric": "pages", "period": "daily", "aggregation": "sum", "target": 2},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "fajr-on-time", "name": "Fajr on time", "icon": "sunrise", "color": "teal",
        "category_name": "Spiritual", "duration_days": 30,
        "description": "Pray Fajr on time every day and track your wake-up time.",
        "definition": {
            "fields": [
                {"key": "done", "label": "Prayed on time", "field_type": "boolean", "required": True},
                {"key": "wake_up", "label": "Wake-up time", "field_type": "time"},
            ],
            "goal": {"metric": "done", "period": "daily", "aggregation": "count", "target": 1},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "early-riser", "name": "Early riser", "icon": "alarm-clock", "color": "amber",
        "category_name": "Productivity", "duration_days": 30,
        "description": "Wake up before 06:00 every day — log your wake-up time.",
        "definition": {
            "fields": [{"key": "wake_up", "label": "Wake-up time", "field_type": "time", "required": True}],
            "goal": {"metric": "wake_up", "period": "daily", "aggregation": "count", "target": 1,
                     "time_comparison": "before", "time_threshold": "06:00"},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "screen-time-limit", "name": "Screen time limit", "icon": "smartphone", "color": "violet",
        "category_name": "Digital Wellbeing", "duration_days": 30,
        "description": "Keep your recreational screen time under 2 hours a day.",
        "definition": {
            "fields": [{"key": "screen_time", "label": "Screen time", "field_type": "duration", "required": True}],
            "goal": {"metric": "screen_time", "period": "daily", "aggregation": "sum", "target": 120, "direction": "at_most"},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "digital-detox", "name": "Digital Detox", "icon": "smartphone", "color": "sky",
        "category_name": "Digital Wellbeing", "duration_days": 30,
        "description": "A day without social media counts as a win.",
        "definition": {
            "fields": [
                {"key": "done", "label": "No social media", "field_type": "boolean", "required": True},
                {"key": "screen_time", "label": "Screen time", "field_type": "duration"},
            ],
            "goal": {"metric": "done", "period": "daily", "aggregation": "count", "target": 1},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "daily-walking", "name": "Daily Walking", "icon": "footprints", "color": "lime",
        "category_name": "Health & Fitness", "duration_days": 30,
        "description": "10,000 steps a day.",
        "definition": {
            "fields": [{"key": "steps", "label": "Steps", "field_type": "integer", "unit": "steps", "required": True}],
            "goal": {"metric": "steps", "period": "daily", "aggregation": "sum", "target": 10000},
            "schedule": {"frequency": "daily"},
        },
    },
    {
        "slug": "water-challenge", "name": "Water Challenge", "icon": "glass-water", "color": "sky",
        "category_name": "Wellness", "duration_days": 30,
        "description": "Drink 2 litres of water every day.",
        "definition": {
            "fields": [{"key": "water", "label": "Water", "field_type": "decimal", "unit": "L", "required": True}],
            "goal": {"metric": "water", "period": "daily", "aggregation": "sum", "target": 2},
            "schedule": {"frequency": "daily"},
        },
    },
]


def sync_system_templates(ChallengeTemplate) -> int:
    for order, t in enumerate(SYSTEM_TEMPLATES):
        ChallengeTemplate.objects.update_or_create(
            owner=None, slug=t["slug"],
            defaults={**{k: v for k, v in t.items() if k != "slug"}, "order": order, "is_public": True},
        )
    return len(SYSTEM_TEMPLATES)
