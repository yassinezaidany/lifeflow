from datetime import timedelta
from decimal import Decimal

from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.core.icons import all_icons

from .models import COLOR_CHOICES, Challenge, ChallengeCategory, ChallengeTemplate, Goal, Milestone, Schedule, TrackingField

COLORS = [c for c, _label in COLOR_CHOICES]
MAX_TARGET = Decimal("1000000")
MAX_DURATION_DAYS = 366 * 5


def validate_icon(value: str) -> str:
    if value and value not in all_icons():
        raise serializers.ValidationError(_("Unknown icon."))
    return value


class UserScopedPK(serializers.PrimaryKeyRelatedField):
    """PK field whose queryset is restricted to the requesting user's objects."""

    def __init__(self, model, **kwargs):
        self.model = model
        super().__init__(**kwargs)

    def get_queryset(self):
        request = self.context.get("request")
        if request is None:
            return self.model.objects.none()
        return self.model.objects.filter(user=request.user)


class ChallengeCategorySerializer(serializers.ModelSerializer):
    icon = serializers.CharField(validators=[validate_icon], required=False)
    color = serializers.ChoiceField(choices=COLORS, required=False)

    class Meta:
        model = ChallengeCategory
        fields = ["id", "name", "icon", "color", "order"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["name"] = _(data["name"])  # default (seeded) names in the user's language; custom names unchanged
        return data

    def validate_name(self, value):
        value = value.strip()
        user = self.context["request"].user
        qs = ChallengeCategory.objects.filter(user=user, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_("You already have a category with this name."))
        return value


# --- Wizard input -----------------------------------------------------------------------------
class FieldInputSerializer(serializers.Serializer):
    ref = serializers.CharField(required=False, allow_blank=True, max_length=60)
    key = serializers.CharField(required=False, allow_blank=True, max_length=40)
    label = serializers.CharField(max_length=60)
    field_type = serializers.ChoiceField(choices=TrackingField.FieldType.choices)
    unit = serializers.CharField(required=False, allow_blank=True, max_length=20, default="")
    options = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list, max_length=30)
    required = serializers.BooleanField(required=False, default=False)
    min_value = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    max_value = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)

    def validate(self, attrs):
        attrs["label"] = attrs["label"].strip()
        if attrs["field_type"] == TrackingField.FieldType.SELECT:
            options = [o.strip() for o in attrs.get("options", []) if o.strip()]
            if not options:
                raise serializers.ValidationError({"options": _("Add at least one option.")})
            if len(set(o.lower() for o in options)) != len(options):
                raise serializers.ValidationError({"options": _("Options must be unique.")})
            attrs["options"] = options
        else:
            attrs["options"] = []
        lo, hi = attrs.get("min_value"), attrs.get("max_value")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"max_value": _("Maximum must be greater than minimum.")})
        return attrs


class GoalInputSerializer(serializers.Serializer):
    metric = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    period = serializers.ChoiceField(choices=Goal.Period.choices)
    aggregation = serializers.ChoiceField(choices=Goal.Aggregation.choices, default=Goal.Aggregation.SUM)
    target = serializers.DecimalField(max_digits=12, decimal_places=2)
    min_per_entry = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    time_comparison = serializers.ChoiceField(choices=["before", "after", ""], required=False, allow_blank=True, default="")
    time_threshold = serializers.TimeField(required=False, allow_null=True, input_formats=["%H:%M", "%H:%M:%S"])

    def validate_target(self, value):
        if value <= 0:
            raise serializers.ValidationError(_("The target must be greater than zero."))
        if value > MAX_TARGET:
            raise serializers.ValidationError(_("This target is too large."))
        return value

    def validate_min_per_entry(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_("The minimum cannot be negative."))
        return value or None


class ScheduleInputSerializer(serializers.Serializer):
    frequency = serializers.ChoiceField(choices=Schedule.Frequency.choices, default=Schedule.Frequency.DAILY)
    weekdays = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False, default=list, max_length=7)
    interval_days = serializers.IntegerField(min_value=1, max_value=365, required=False, default=1)

    def validate(self, attrs):
        if attrs["frequency"] == Schedule.Frequency.WEEKDAYS and not attrs.get("weekdays"):
            raise serializers.ValidationError({"weekdays": _("Select at least one day of the week.")})
        if attrs["frequency"] != Schedule.Frequency.WEEKDAYS:
            attrs["weekdays"] = []
        if attrs["frequency"] != Schedule.Frequency.INTERVAL:
            attrs["interval_days"] = 1
        return attrs


class MilestoneInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=80)
    target_value = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


def normalise_goal(goal: dict, metric_field_type: str | None) -> dict:
    """Make the goal consistent whatever the client sent:
    no metric or boolean metric -> COUNT; min_per_entry only for numeric metrics;
    a time metric needs a before/after threshold and always counts qualifying days."""
    if metric_field_type == TrackingField.FieldType.TIME:
        if not goal.get("time_threshold"):
            raise serializers.ValidationError({"time_threshold": _("Choose the time to beat (e.g. before 05:30).")})
        goal["time_comparison"] = goal.get("time_comparison") or "before"
        goal["aggregation"] = Goal.Aggregation.COUNT
        goal["min_per_entry"] = None
        return goal
    goal["time_comparison"], goal["time_threshold"] = "", None
    if metric_field_type is None or metric_field_type == TrackingField.FieldType.BOOLEAN:
        goal["aggregation"] = Goal.Aggregation.COUNT
        goal["min_per_entry"] = None
    return goal


class ChallengeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    category = UserScopedPK(ChallengeCategory, required=False, allow_null=True)
    template = serializers.PrimaryKeyRelatedField(queryset=ChallengeTemplate.objects.all(), required=False, allow_null=True)
    icon = serializers.CharField(required=False, default="target", validators=[validate_icon])
    color = serializers.ChoiceField(choices=COLORS, required=False, default="indigo")
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    fields = FieldInputSerializer(many=True, required=False, default=list)
    goal = GoalInputSerializer()
    schedule = ScheduleInputSerializer(required=False)
    milestones = MilestoneInputSerializer(many=True, required=False, default=list)

    def validate_fields(self, value):
        if len(value) > 12:
            raise serializers.ValidationError(_("A challenge can have at most 12 fields."))
        labels = [f["label"].lower() for f in value]
        if len(set(labels)) != len(labels):
            raise serializers.ValidationError(_("Field names must be unique."))
        return value

    def validate_template(self, value):
        request = self.context.get("request")
        if value is not None and value.owner_id not in (None, getattr(request.user, "pk", None)) and not value.is_public:
            raise serializers.ValidationError(_("Template not found."))
        return value

    def validate(self, attrs):
        attrs["name"] = attrs["name"].strip()
        start, end = attrs["start_date"], attrs.get("end_date")
        if end and end < start:
            raise serializers.ValidationError({"end_date": _("End date must be on or after the start date.")})
        if end and (end - start) > timedelta(days=MAX_DURATION_DAYS):
            raise serializers.ValidationError({"end_date": _("A challenge can last at most 5 years.")})

        goal = attrs["goal"]
        metric_ref = (goal.get("metric") or "").strip() or None
        metric_type = None
        if metric_ref:
            match = next((f for f in attrs["fields"] if metric_ref in (f.get("ref"), f.get("key"), f["label"])), None)
            if match is None:
                raise serializers.ValidationError({"goal": {"metric": _("Choose one of the challenge's fields.")}})
            if match["field_type"] not in TrackingField.MEASURABLE_TYPES:
                raise serializers.ValidationError({"goal": {"metric": _("This field can't be measured (choose a number, duration, time or done/not done field).")}})
            metric_type = match["field_type"]
        goal["metric"] = metric_ref
        attrs["goal"] = normalise_goal(goal, metric_type)
        if goal["period"] == Goal.Period.TOTAL and attrs.get("schedule") is None:
            attrs["schedule"] = {"frequency": Schedule.Frequency.DAILY, "weekdays": [], "interval_days": 1}
        return attrs


# --- Read / update ----------------------------------------------------------------------------
class TrackingFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingField
        fields = ["id", "key", "label", "field_type", "unit", "options", "required", "min_value", "max_value", "order", "is_active"]
        read_only_fields = ["id", "key", "order"]

    def validate(self, attrs):
        data = FieldInputSerializer(data={
            "label": attrs.get("label", getattr(self.instance, "label", "")),
            "field_type": attrs.get("field_type", getattr(self.instance, "field_type", "")),
            "unit": attrs.get("unit", getattr(self.instance, "unit", "")),
            "options": attrs.get("options", getattr(self.instance, "options", [])),
            "min_value": attrs.get("min_value", getattr(self.instance, "min_value", None)),
            "max_value": attrs.get("max_value", getattr(self.instance, "max_value", None)),
        })
        data.is_valid(raise_exception=True)
        attrs["options"] = data.validated_data["options"]
        attrs["label"] = data.validated_data["label"]
        if self.instance and "field_type" in attrs and attrs["field_type"] != self.instance.field_type and self.instance.values.exists():
            raise serializers.ValidationError({"field_type": _("The type can't change once values were recorded.")})
        return attrs


class GoalSerializer(serializers.ModelSerializer):
    metric_key = serializers.CharField(source="metric.key", read_only=True, default=None)

    class Meta:
        model = Goal
        fields = ["id", "metric", "metric_key", "period", "aggregation", "target", "min_per_entry", "time_comparison", "time_threshold", "effective_from", "effective_to"]


class ScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schedule
        fields = ["id", "frequency", "weekdays", "interval_days", "effective_from", "effective_to"]


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ["id", "title", "target_value"]


class ChallengeSerializer(serializers.ModelSerializer):
    category = ChallengeCategorySerializer(read_only=True)
    category_id = UserScopedPK(ChallengeCategory, source="category", required=False, allow_null=True, write_only=True)
    icon = serializers.CharField(required=False, validators=[validate_icon])
    color = serializers.ChoiceField(choices=COLORS, required=False)
    tracking_fields = TrackingFieldSerializer(source="fields", many=True, read_only=True)
    goal = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()
    goals_history = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            "id", "name", "description", "category", "category_id", "icon", "color", "status",
            "start_date", "end_date", "closed_on", "reminder_time", "tracking_fields", "goal", "schedule", "goals_history",
            "progress", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "closed_on", "created_at", "updated_at"]

    def get_goal(self, obj):
        goal = obj.current_goal
        return GoalSerializer(goal).data if goal else None

    def get_schedule(self, obj):
        schedule = obj.current_schedule
        return ScheduleSerializer(schedule).data if schedule else None

    def get_goals_history(self, obj):
        return GoalSerializer(obj._prefetched("goals"), many=True).data

    def get_progress(self, obj):
        results = self.context.get("progress") or {}
        result = results.get(obj.pk)
        return result.as_dict(include_series=False) if result else None

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": _("End date must be on or after the start date.")})
        if self.instance and "start_date" in attrs and attrs["start_date"] > self.instance.start_date:
            if self.instance.entries.filter(date__lt=attrs["start_date"]).exists():
                raise serializers.ValidationError({"start_date": _("Some entries are recorded before this date.")})
        return attrs



class GoalUpdateSerializer(GoalInputSerializer):
    effective_from = serializers.DateField(required=False)

    def validate(self, attrs):
        challenge = self.context["challenge"]
        metric_ref = (attrs.get("metric") or "").strip() or None
        metric = None
        if metric_ref:
            metric = challenge.fields.filter(is_active=True).filter(key=metric_ref).first()
            if metric is None and metric_ref.isdigit():
                metric = challenge.fields.filter(is_active=True, pk=int(metric_ref)).first()
            if metric is None:
                raise serializers.ValidationError({"metric": _("Choose one of the challenge's fields.")})
            if not metric.is_measurable:
                raise serializers.ValidationError({"metric": _("This field can't be measured.")})
        attrs["metric"] = metric
        normalise_goal(attrs, metric.field_type if metric else None)
        eff = attrs.get("effective_from")
        if eff and eff < challenge.start_date:
            raise serializers.ValidationError({"effective_from": _("This date is before the challenge starts.")})
        return attrs


class ScheduleUpdateSerializer(ScheduleInputSerializer):
    effective_from = serializers.DateField(required=False)


class ChallengeTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChallengeTemplate
        fields = ["id", "slug", "name", "description", "icon", "color", "category_name", "duration_days", "definition", "is_public"]
