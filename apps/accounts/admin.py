"""Admin: user & system management only.

By design, private user content (entries, journal, planner, reports) is NOT
registered in the admin, so administrators don't browse personal data.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count

from .models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ["timezone", "language", "theme", "week_start", "onboarding_completed"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ["username", "email", "first_name", "is_active", "is_staff", "is_demo", "challenge_count", "date_joined"]
    list_filter = ["is_active", "is_staff", "is_demo"]
    fieldsets = BaseUserAdmin.fieldsets + (("LifeFlow", {"fields": ["is_demo"]}),)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_challenges=Count("challenges"))

    @admin.display(description="Challenges", ordering="_challenges")
    def challenge_count(self, obj):
        return obj._challenges
