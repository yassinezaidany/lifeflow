from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.challenges.models import Challenge
from apps.core.api.mixins import OwnedQuerysetMixin
from apps.core.dates import parse_date
from apps.planner.models import PlannedActivity

from . import services
from .models import ChallengeEntry


class EntrySerializer(serializers.ModelSerializer):
    values = serializers.SerializerMethodField()
    challenge_name = serializers.CharField(source="challenge.name", read_only=True)

    class Meta:
        model = ChallengeEntry
        fields = ["id", "challenge", "challenge_name", "date", "note", "source", "planned_activity", "values", "created_at", "updated_at"]

    def get_values(self, obj):
        return {v.field.key: v.value for v in obj.values.all()}


class EntryInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    values = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    source = serializers.ChoiceField(choices=ChallengeEntry.Source.choices, required=False, default=ChallengeEntry.Source.MANUAL)
    planned_activity = serializers.IntegerField(required=False, allow_null=True)


def _resolve_activity(user, activity_id):
    if not activity_id:
        return None
    activity = PlannedActivity.objects.filter(pk=activity_id, user=user).first()
    if activity is None:
        raise ValidationError({"planned_activity": _("Activity not found.")})
    if not activity.is_done:
        # Rule: planning is not succeeding. Only confirmed activities can feed a challenge.
        raise ValidationError({"planned_activity": _("Mark the activity as completed first.")})
    return activity


class EntryViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    """/api/entries/ (all) and /api/challenges/{challenge_pk}/entries/ (nested)."""

    queryset = ChallengeEntry.objects.select_related("challenge").prefetch_related("values__field")
    serializer_class = EntrySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if "challenge_pk" in self.kwargs:
            self._challenge(self.kwargs["challenge_pk"])  # 404 for a challenge the user doesn't own
            qs = qs.filter(challenge_id=self.kwargs["challenge_pk"])
        params = self.request.query_params
        if params.get("challenge"):
            qs = qs.filter(challenge_id=params["challenge"])
        if start := parse_date(params.get("start")):
            qs = qs.filter(date__gte=start)
        if end := parse_date(params.get("end")):
            qs = qs.filter(date__lte=end)
        return qs

    def _challenge(self, challenge_id):
        return get_object_or_404(Challenge.objects.prefetch_related("fields"), pk=challenge_id, user=self.request.user)

    def create(self, request, *args, **kwargs):
        challenge_id = self.kwargs.get("challenge_pk") or request.data.get("challenge")
        if not challenge_id:
            raise ValidationError({"challenge": _("Choose a challenge.")})
        challenge = self._challenge(challenge_id)
        data = EntryInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        activity = _resolve_activity(request.user, v.get("planned_activity"))
        source = ChallengeEntry.Source.PLANNER if activity else v["source"]
        entry = services.create_entry(request.user, challenge, v["date"], v["values"], v["note"], source, activity)
        entry = self.get_queryset().model.objects.prefetch_related("values__field").select_related("challenge").get(pk=entry.pk)
        return Response(EntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        entry = self.get_object()
        partial = kwargs.get("partial", False)
        payload = {
            "date": request.data.get("date", entry.date.isoformat()),
            "values": request.data.get("values", services.entry_values_dict(entry) if partial else {}),
            "note": request.data.get("note", entry.note),
        }
        data = EntryInputSerializer(data=payload)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        services.update_entry(entry, v["date"], v["values"], v["note"])
        entry = self.get_queryset().get(pk=entry.pk)
        return Response(EntrySerializer(entry).data)

    def perform_destroy(self, instance):
        services.delete_entry(instance)
