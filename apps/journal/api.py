from django.utils.translation import gettext as _
from rest_framework import serializers, viewsets

from apps.challenges.models import Challenge
from apps.challenges.serializers import UserScopedPK
from apps.core.api.mixins import OwnedQuerysetMixin
from apps.core.dates import parse_date, week_start_for

from .models import JournalEntry, WeeklyReview


class JournalEntrySerializer(serializers.ModelSerializer):
    challenge = UserScopedPK(Challenge, required=False, allow_null=True)
    challenge_name = serializers.CharField(source="challenge.name", read_only=True, default=None)

    class Meta:
        model = JournalEntry
        fields = ["id", "date", "scope", "challenge", "challenge_name", "title", "content", "mood", "created_at", "updated_at"]

    def validate(self, attrs):
        if attrs.get("scope") == JournalEntry.Scope.CHALLENGE and not attrs.get("challenge", getattr(self.instance, "challenge", None)):
            raise serializers.ValidationError({"challenge": _("Choose the challenge this note is about.")})
        if not (attrs.get("content") or getattr(self.instance, "content", "")).strip():
            raise serializers.ValidationError({"content": _("Write something first.")})
        return attrs


class WeeklyReviewSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)

    class Meta:
        model = WeeklyReview
        fields = ["id", "week_start", "went_well", "difficult", "improve", "rating", "updated_at"]

    def validate_week_start(self, value):
        request = self.context["request"]
        return week_start_for(value, request.user.profile.week_start)


class JournalEntryViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = JournalEntry.objects.select_related("challenge")
    serializer_class = JournalEntrySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if start := parse_date(p.get("start")):
            qs = qs.filter(date__gte=start)
        if end := parse_date(p.get("end")):
            qs = qs.filter(date__lte=end)
        if p.get("challenge"):
            qs = qs.filter(challenge_id=p["challenge"])
        if p.get("q"):
            qs = qs.filter(content__icontains=p["q"])
        return qs


class WeeklyReviewViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = WeeklyReview.objects.all()
    serializer_class = WeeklyReviewSerializer

    def perform_create(self, serializer):
        # Upsert: one review per week
        week = serializer.validated_data["week_start"]
        existing = WeeklyReview.objects.filter(user=self.request.user, week_start=week).first()
        if existing:
            serializer.instance = existing
            serializer.save()
        else:
            serializer.save(user=self.request.user)
