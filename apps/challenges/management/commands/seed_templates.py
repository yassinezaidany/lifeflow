from django.core.management.base import BaseCommand

from apps.challenges.models import ChallengeTemplate
from apps.challenges.system_templates import sync_system_templates


class Command(BaseCommand):
    help = "Create or refresh the built-in challenge templates."

    def handle(self, *args, **options):
        n = sync_system_templates(ChallengeTemplate)
        self.stdout.write(self.style.SUCCESS(f"{n} system templates synced"))
