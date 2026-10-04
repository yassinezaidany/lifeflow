from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.analytics.services.progress import ProgressEngine
from apps.core.api.mixins import OwnedQuerysetMixin
from apps.core.audit import audit
from apps.core.dates import parse_date
from apps.core.models import AuditLog

from rest_framework.throttling import ScopedRateThrottle

from . import assistant, services


class AssistantThrottle(ScopedRateThrottle):
    scope = "assistant"
from .models import Challenge, ChallengeCategory, ChallengeTemplate, Milestone, RestDay, TrackingField
from .serializers import (
    ChallengeCategorySerializer,
    ChallengeCreateSerializer,
    ChallengeSerializer,
    ChallengeTemplateSerializer,
    FieldInputSerializer,
    GoalUpdateSerializer,
    MilestoneSerializer,
    ScheduleUpdateSerializer,
    TrackingFieldSerializer,
)


class ChallengeCategoryViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ChallengeCategory.objects.all()
    serializer_class = ChallengeCategorySerializer
    pagination_class = None


class ChallengeViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD + business actions. Deleting is allowed, but archiving is the default UX."""

    queryset = Challenge.objects.all()
    serializer_class = ChallengeSerializer

    def get_queryset(self):
        qs = ProgressEngine.prefetch(super().get_queryset()).prefetch_related("fields")
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__in=status_param.split(","))
        search = self.request.query_params.get("q")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["progress"] = getattr(self, "_progress", {})
        return ctx

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        items = page if page is not None else list(queryset)
        self._progress = ProgressEngine(request.user).evaluate_many(items)
        serializer = self.get_serializer(items, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._progress = {instance.pk: ProgressEngine(request.user).evaluate(instance)}
        return Response(self.get_serializer(instance).data)

    def create(self, request, *args, **kwargs):
        serializer = ChallengeCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        challenge = services.create_challenge(request.user, serializer.validated_data)
        instance = self.get_queryset().get(pk=challenge.pk)
        self._progress = {instance.pk: ProgressEngine(request.user).evaluate(instance)}
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        challenge = serializer.save()
        audit(self.request.user, AuditLog.Action.CHALLENGE_UPDATED, challenge, fields=list(serializer.validated_data))

    def perform_destroy(self, instance):
        audit(self.request.user, AuditLog.Action.CHALLENGE_DELETED, None, description=instance.name, challenge=instance.pk)
        instance.delete()

    # --- business actions ---------------------------------------------------------------
    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        challenge = self.get_object()
        new_status = request.data.get("status")
        if new_status not in Challenge.Status.values:
            raise ValidationError({"status": _("Unknown status.")})
        services.change_status(challenge, new_status)
        return Response(self.get_serializer(self.get_queryset().get(pk=challenge.pk)).data)

    @action(detail=True, methods=["put"])
    def goal(self, request, pk=None):
        challenge = self.get_object()
        serializer = GoalUpdateSerializer(data=request.data, context={"challenge": challenge, "request": request})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        effective_from = data.pop("effective_from", None)
        services.update_goal(challenge, data, effective_from)
        return Response(self.get_serializer(self.get_queryset().get(pk=challenge.pk)).data)

    @action(detail=True, methods=["put"])
    def schedule(self, request, pk=None):
        challenge = self.get_object()
        serializer = ScheduleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        effective_from = data.pop("effective_from", None)
        services.update_schedule(challenge, data, effective_from)
        return Response(self.get_serializer(self.get_queryset().get(pk=challenge.pk)).data)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        challenge = self.get_object()
        result = ProgressEngine(request.user).evaluate(challenge, include_series=True)
        return Response(result.as_dict(include_series=True))

    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        challenge = self.get_object()
        start = parse_date(request.query_params.get("start"))
        end = parse_date(request.query_params.get("end"))
        window = (start, end) if start and end and start <= end else None
        result = ProgressEngine(request.user).evaluate(challenge, include_series=True, window=window)
        return Response({"statistics": result.statistics, "buckets": result.buckets, "days": [d.as_dict() for d in result.days]})

    @action(detail=True, methods=["post"])
    def fields(self, request, pk=None):
        challenge = self.get_object()
        serializer = FieldInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if challenge.fields.count() >= 12:
            raise ValidationError({"detail": _("A challenge can have at most 12 fields.")})
        if challenge.fields.filter(label__iexact=data["label"]).exists():
            raise ValidationError({"label": _("Field names must be unique.")})
        taken = set(challenge.fields.values_list("key", flat=True))
        field = TrackingField.objects.create(
            challenge=challenge, key=services.unique_field_key(data["label"], taken), label=data["label"],
            field_type=data["field_type"], unit=data.get("unit", ""), options=data.get("options", []),
            required=data.get("required", False), min_value=data.get("min_value"), max_value=data.get("max_value"),
            order=challenge.fields.count(),
        )
        return Response(TrackingFieldSerializer(field).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"fields/(?P<field_id>\d+)")
    def field_detail(self, request, pk=None, field_id=None):
        challenge = self.get_object()
        field = get_object_or_404(TrackingField, pk=field_id, challenge=challenge)
        if request.method == "DELETE":
            if field.goals.exists() or field.values.exists():
                field.is_active = False  # keep history; hide from forms
                field.save(update_fields=["is_active", "updated_at"])
            else:
                field.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = TrackingFieldSerializer(field, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post", "delete"], url_path="milestones")
    def milestones(self, request, pk=None):
        challenge = self.get_object()
        if request.method == "DELETE":
            Milestone.objects.filter(challenge=challenge, pk=request.data.get("id")).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = MilestoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(challenge=challenge)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rest-day")
    def rest_day(self, request, pk=None):
        challenge = self.get_object()
        day = parse_date(request.data.get("date"))
        if day is None:
            raise ValidationError({"date": _("Enter a valid date.")})
        is_rest = services.toggle_rest_day(request.user, day, challenge)
        return Response({"date": day.isoformat(), "rest": is_rest})

    @action(detail=False, methods=["post"], throttle_classes=[AssistantThrottle])
    def suggest(self, request):
        """Turn a natural-language description into a *suggested* wizard payload.
        Nothing is created: the wizard is pre-filled and the user confirms."""
        text = (request.data.get("text") or "").strip()
        if len(text) < 3:
            raise ValidationError({"text": _("Describe your challenge first.")})
        if len(text) > assistant.MAX_TEXT:
            raise ValidationError({"text": _("Keep it under 500 characters.")})
        return Response(assistant.suggest_challenge(text))

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        source = self.get_object()
        definition = services.challenge_definition(source)
        payload = {
            "name": request.data.get("name") or _("%(name)s (copy)") % {"name": source.name},
            "description": source.description, "category": source.category_id, "icon": source.icon,
            "color": source.color, "start_date": request.data.get("start_date") or source.start_date.isoformat(),
            "end_date": request.data.get("end_date") or (source.end_date.isoformat() if source.end_date else None),
            **definition,
        }
        serializer = ChallengeCreateSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        challenge = services.create_challenge(request.user, serializer.validated_data)
        return Response(self.get_serializer(self.get_queryset().get(pk=challenge.pk)).data, status=status.HTTP_201_CREATED)


class ChallengeTemplateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ChallengeTemplateSerializer
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        return ChallengeTemplate.objects.filter(Q(owner__isnull=True) | Q(owner=user) | Q(is_public=True))


class RestDayViewSet(OwnedQuerysetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Global rest days (all challenges). Toggle with POST {date}."""

    queryset = RestDay.objects.filter(challenge__isnull=True)
    pagination_class = None

    def list(self, request, *args, **kwargs):
        days = self.get_queryset().values_list("date", flat=True)
        return Response([d.isoformat() for d in days])

    def create(self, request, *args, **kwargs):
        day = parse_date(request.data.get("date"))
        if day is None:
            raise ValidationError({"date": _("Enter a valid date.")})
        return Response({"date": day.isoformat(), "rest": services.toggle_rest_day(request.user, day)})
