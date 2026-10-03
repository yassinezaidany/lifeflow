from datetime import timedelta

from django.utils.translation import gettext as _
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.api.mixins import OwnedQuerysetMixin
from apps.core.audit import audit
from apps.core.dates import parse_date, user_now, user_today, week_start_for
from apps.core.models import AuditLog
from apps.tracking.models import ChallengeEntry

from . import services
from .models import ActivityCategory, PlannedActivity, PlannerTemplate, RecurringRule
from .serializers import (
    ActivityCategorySerializer,
    HHMMField,
    PlannedActivitySerializer,
    PlannerTemplateSerializer,
    RecurringRuleSerializer,
)

ACTIVITY_QS = PlannedActivity.objects.select_related("category", "challenge")


def _activity_context(request, activities) -> dict:
    ids = [a.pk for a in activities]
    with_entry = set(ChallengeEntry.objects.filter(planned_activity_id__in=ids).values_list("planned_activity_id", flat=True))
    return {"request": request, "activity_ids_with_entry": with_entry}


def serialize_activities(request, activities):
    activities = list(activities)
    data = PlannedActivitySerializer(activities, many=True, context=_activity_context(request, activities)).data
    now = user_now(request.user)
    for item, activity in zip(data, activities):
        item["overdue"] = services.is_overdue(activity, now)
    return data


def _parse_time(value, field):
    if value in (None, ""):
        return None
    try:
        return HHMMField().to_internal_value(value)
    except Exception:
        raise ValidationError({field: _("Enter a valid time (HH:MM).")})


class ActivityCategoryViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ActivityCategory.objects.all()
    serializer_class = ActivityCategorySerializer
    pagination_class = None


class PlannedActivityViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ACTIVITY_QS
    serializer_class = PlannedActivitySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        start, end = parse_date(params.get("start")), parse_date(params.get("end"))
        if start and end and self.action == "list":
            services.ensure_occurrences(self.request.user, start, end)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("challenge"):
            qs = qs.filter(challenge_id=params["challenge"])
        return qs

    def _respond(self, activity, code=status.HTTP_200_OK, **extra):
        activity = ACTIVITY_QS.get(pk=activity.pk)
        data = serialize_activities(self.request, [activity])[0]
        overlaps = services.find_overlaps(activity.user, activity.date, activity.start_time, activity.end_time, exclude_id=activity.pk)
        data["overlaps"] = [{"id": o.pk, "title": o.title, "start_time": o.start_time.strftime("%H:%M"), "end_time": o.end_time.strftime("%H:%M")} for o in overlaps]
        data.update(extra)
        return Response(data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity = serializer.save(user=request.user)
        audit(request.user, AuditLog.Action.ACTIVITY_CREATED, activity)
        return self._respond(activity, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        activity = self.get_object()
        serializer = self.get_serializer(activity, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        activity = serializer.save()
        if activity.recurring_rule_id and not activity.is_detached:
            activity.is_detached = True
            activity.save(update_fields=["is_detached", "updated_at"])
        audit(request.user, AuditLog.Action.ACTIVITY_UPDATED, activity, fields=list(serializer.validated_data))
        return self._respond(activity)

    def destroy(self, request, *args, **kwargs):
        services.delete_activity(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        activity = self.get_object()
        new_date = parse_date(request.data.get("date"), activity.date)
        start = _parse_time(request.data.get("start_time"), "start_time") or activity.start_time
        end = _parse_time(request.data.get("end_time"), "end_time") or activity.end_time
        try:
            services.move_activity(activity, new_date, start, end)
        except Exception as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(exc.message_dict)
            raise
        return self._respond(activity)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        activity = self.get_object()
        target = parse_date(request.data.get("date"), activity.date)
        return self._respond(services.duplicate_activity(activity, target), status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        activity = self.get_object()
        actual = request.data.get("actual_minutes")
        try:
            actual = int(actual) if actual not in (None, "") else None
        except (TypeError, ValueError):
            raise ValidationError({"actual_minutes": _("Enter a whole number of minutes.")})
        services.set_status(activity, request.data.get("status", ""), actual_minutes=actual, notes=request.data.get("notes"))
        suggestion = services.entry_suggestion(activity) if activity.is_done else None
        return self._respond(activity, entry_suggestion=suggestion)

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        activity = self.get_object()
        new_date = parse_date(request.data.get("date"))
        if new_date is None:
            raise ValidationError({"date": _("Choose a new date.")})
        start = _parse_time(request.data.get("start_time"), "start_time")
        end = _parse_time(request.data.get("end_time"), "end_time")
        new = services.reschedule_activity(activity, new_date, start, end)
        return self._respond(new, status.HTTP_201_CREATED)


class RecurringRuleViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = RecurringRule.objects.select_related("category", "challenge")
    serializer_class = RecurringRuleSerializer
    pagination_class = None

    def perform_create(self, serializer):
        rule = RecurringRule(user=self.request.user, **serializer.validated_data)
        services.save_rule(rule, created=True)
        serializer.instance = rule

    def perform_update(self, serializer):
        rule = serializer.instance
        for k, v in serializer.validated_data.items():
            setattr(rule, k, v)
        services.save_rule(rule, created=False)

    def perform_destroy(self, instance):
        services.delete_rule(instance)


class PlannerTemplateViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PlannerTemplate.objects.prefetch_related("items__category")
    serializer_class = PlannerTemplateSerializer
    pagination_class = None

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        template = self.get_object()
        raw = request.data.get("dates") or []
        dates = [parse_date(d) for d in raw]
        if not raw or any(d is None for d in dates):
            raise ValidationError({"dates": _("Choose at least one valid day.")})
        created = services.apply_template(template, dates, replace=bool(request.data.get("replace")))
        return Response({"created": len(created)}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="from-day")
    def from_day(self, request):
        day = parse_date(request.data.get("date"))
        name = (request.data.get("name") or "").strip()
        if day is None or not name:
            raise ValidationError({"name": _("Give the template a name.")})
        template = services.template_from_day(request.user, day, name[:80], (request.data.get("description") or "")[:255])
        return Response(PlannerTemplateSerializer(template, context={"request": request}).data, status=status.HTTP_201_CREATED)


def _day_payload(request, day, activities):
    items = [a for a in activities if a.date == day]
    return {"date": day.isoformat(), "activities": serialize_activities(request, items), "summary": services.summarize(items, request.user)}


@api_view(["GET"])
def planner_day(request):
    day = parse_date(request.query_params.get("date"), user_today(request.user))
    services.ensure_occurrences(request.user, day, day)
    activities = list(ACTIVITY_QS.filter(user=request.user, date=day))
    return Response(_day_payload(request, day, activities))


@api_view(["GET"])
def planner_today(request):
    day = user_today(request.user)
    services.ensure_occurrences(request.user, day, day)
    activities = list(ACTIVITY_QS.filter(user=request.user, date=day))
    payload = _day_payload(request, day, activities)
    now = user_now(request.user).time()
    payload["next"] = next(
        (a for a in payload["activities"] if a["status"] == "planned" and a["start_time"] >= now.strftime("%H:%M")), None
    )
    return Response(payload)


@api_view(["GET"])
def planner_week(request):
    profile = request.user.profile
    anchor = parse_date(request.query_params.get("start"), user_today(request.user))
    start = week_start_for(anchor, profile.week_start)
    end = start + timedelta(days=6)
    services.ensure_occurrences(request.user, start, end)
    activities = list(ACTIVITY_QS.filter(user=request.user, date__range=(start, end)))
    days = [_day_payload(request, start + timedelta(days=i), activities) for i in range(7)]
    return Response({
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "summary": services.summarize(activities, request.user),
    })
