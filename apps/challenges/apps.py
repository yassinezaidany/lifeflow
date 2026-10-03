from django.apps import AppConfig


class ChallengesConfig(AppConfig):
    name = "apps.challenges"
    label = "challenges"
    verbose_name = "Challenges"

    def ready(self):
        from . import signals  # noqa: F401
