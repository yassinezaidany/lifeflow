from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .defaults import DEFAULT_ACTIVITY_CATEGORIES
from .models import ActivityCategory


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def seed_activity_categories(sender, instance, created, **kwargs):
    if not created:
        return
    ActivityCategory.objects.bulk_create(
        [
            ActivityCategory(user=instance, name=name, icon=icon, color=color, order=i)
            for i, (name, icon, color) in enumerate(DEFAULT_ACTIVITY_CATEGORIES)
        ],
        ignore_conflicts=True,
    )
