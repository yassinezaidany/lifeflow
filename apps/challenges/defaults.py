"""Default data copied to each new user (so they can freely rename/delete it)."""
from django.utils.translation import gettext_noop as _

DEFAULT_CHALLENGE_CATEGORIES = [
    (_("Health & Fitness"), "heart-pulse", "rose"),
    (_("Learning"), "graduation-cap", "indigo"),
    (_("Spiritual"), "sparkles", "emerald"),
    (_("Productivity"), "zap", "amber"),
    (_("Wellness"), "leaf", "teal"),
    (_("Digital Wellbeing"), "smartphone", "sky"),
    (_("Finance"), "wallet", "lime"),
    (_("Lifestyle"), "sun", "orange"),
    (_("Social"), "users", "violet"),
    (_("Other"), "tag", "slate"),
]
