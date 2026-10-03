from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .defaults import DEFAULT_CHALLENGE_CATEGORIES
from .models import ChallengeCategory


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def seed_challenge_categories(sender, instance, created, **kwargs):
    if not created:
        return
    ChallengeCategory.objects.bulk_create(
        [
            ChallengeCategory(user=instance, name=name, icon=icon, color=color, order=i)
            for i, (name, icon, color) in enumerate(DEFAULT_CHALLENGE_CATEGORIES)
        ],
        ignore_conflicts=True,
    )
