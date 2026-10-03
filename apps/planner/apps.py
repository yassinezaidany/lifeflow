from django.apps import AppConfig


class PlannerConfig(AppConfig):
    name = "apps.planner"
    label = "planner"
    verbose_name = "Planner"

    def ready(self):
        from . import signals  # noqa: F401
