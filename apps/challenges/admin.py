from django.contrib import admin

from .models import ChallengeTemplate


@admin.register(ChallengeTemplate)
class ChallengeTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "category_name", "duration_days", "is_public", "owner", "order"]
    list_filter = ["is_public", "category_name"]
    search_fields = ["name", "slug"]
    list_editable = ["order", "is_public"]

    def get_queryset(self, request):
        # System templates only: user-owned templates are private content.
        return super().get_queryset(request).filter(owner__isnull=True)
