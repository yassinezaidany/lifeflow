from datetime import date

from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.challenges.models import COLOR_CHOICES, Challenge
from apps.challenges.serializers import UserScopedPK, validate_icon

from .models import ActivityCategory, PlannedActivity, PlannerTemplate, PlannerTemplateItem, Priority, RecurringRule, validate_time_range

COLORS = [c for c, _l in COLOR_CHOICES]
MIN_DATE, MAX_DATE = date(2000, 1, 1), date(2100, 12, 31)


def check_date(value):
    if value and not (MIN_DATE <= value <= MAX_DATE):
        raise serializers.ValidationError(_("Enter a realistic date."))
    return value


class HHMMField(serializers.TimeField):
    def __init__(self, **kwargs):
        super().__init__(format="%H:%M", input_formats=["%H:%M", "%H:%M:%S"], **kwargs)


class ActivityCategorySerializer(serializers.ModelSerializer):
    icon = serializers.CharField(required=False, validators=[validate_icon])
    color = serializers.ChoiceField(choices=COLORS, required=False)

    class Meta:
        model = ActivityCategory
        fields = ["id", "name", "icon", "color", "order"]

    def validate_name(self, value):
        value = value.strip()
        qs = ActivityCategory.objects.filter(user=self.context["request"].user, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_("You already have a category with this name."))
        return value


class _MiniChallenge(serializers.ModelSerializer):
    class Meta:
        model = Challenge
        fields = ["id", "name", "color", "icon"]


class TimedSerializerMixin(serializers.Serializer):
    start_time = HHMMField()
    end_time = HHMMField()
    color = serializers.ChoiceField(choices=COLORS + [""], required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        try:
            validate_time_range(start, end)
        except Exception:
            raise serializers.ValidationError({"end_time": _("End time must be after start time.")})
        return attrs


class PlannedActivitySerializer(TimedSerializerMixin, serializers.ModelSerializer):
    category = ActivityCategorySerializer(read_only=True)
    category_id = UserScopedPK(ActivityCategory, source="category", required=False, allow_null=True, write_only=True)
    challenge = _MiniChallenge(read_only=True)
    challenge_id = UserScopedPK(Challenge, source="challenge", required=False, allow_null=True, write_only=True)
    duration_minutes = serializers.IntegerField(read_only=True)
    effective_color = serializers.CharField(read_only=True)
    is_recurring = serializers.SerializerMethodField()
    has_entry = serializers.SerializerMethodField()
    date = serializers.DateField(validators=[check_date])

    class Meta:
        model = PlannedActivity
        fields = [
            "id", "title", "description", "date", "start_time", "end_time", "duration_minutes",
            "category", "category_id", "priority", "status", "notes", "color", "effective_color",
            "challenge", "challenge_id", "recurring_rule", "is_recurring", "is_detached",
            "actual_minutes", "completed_at", "rescheduled_from", "has_entry", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "recurring_rule", "is_detached", "actual_minutes", "completed_at", "rescheduled_from"]

    def get_is_recurring(self, obj):
        return obj.recurring_rule_id is not None

    def get_has_entry(self, obj):
        ids = self.context.get("activity_ids_with_entry")
        if ids is not None:
            return obj.pk in ids
        return obj.entries.exists()


class RecurringRuleSerializer(TimedSerializerMixin, serializers.ModelSerializer):
    category = ActivityCategorySerializer(read_only=True)
    category_id = UserScopedPK(ActivityCategory, source="category", required=False, allow_null=True, write_only=True)
    challenge = _MiniChallenge(read_only=True)
    challenge_id = UserScopedPK(Challenge, source="challenge", required=False, allow_null=True, write_only=True)
    weekdays = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False, max_length=7)
    interval_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    start_date = serializers.DateField(validators=[check_date])
    end_date = serializers.DateField(required=False, allow_null=True, validators=[check_date])
    duration_minutes = serializers.IntegerField(read_only=True)

    class Meta:
        model = RecurringRule
        fields = [
            "id", "title", "description", "start_time", "end_time", "duration_minutes", "category", "category_id",
            "challenge", "challenge_id", "frequency", "weekdays", "interval_days", "start_date", "end_date",
            "priority", "color", "notes", "is_active", "created_at",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        freq = attrs.get("frequency", getattr(self.instance, "frequency", RecurringRule.Frequency.WEEKLY))
        weekdays = attrs.get("weekdays", getattr(self.instance, "weekdays", []))
        if freq == RecurringRule.Frequency.WEEKLY and not weekdays:
            raise serializers.ValidationError({"weekdays": _("Select at least one day of the week.")})
        attrs["weekdays"] = sorted(set(weekdays)) if freq == RecurringRule.Frequency.WEEKLY else []
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": _("End date must be on or after the start date.")})
        return attrs


class PlannerTemplateItemSerializer(TimedSerializerMixin, serializers.ModelSerializer):
    category_id = serializers.IntegerField(required=False, allow_null=True)
    challenge_id = serializers.IntegerField(required=False, allow_null=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    effective_color = serializers.SerializerMethodField()

    class Meta:
        model = PlannerTemplateItem
        fields = ["id", "title", "start_time", "end_time", "category_id", "category_name", "challenge_id", "color", "effective_color", "priority", "notes"]

    def get_effective_color(self, obj):
        return obj.color or (obj.category.color if obj.category else "slate")


class PlannerTemplateSerializer(serializers.ModelSerializer):
    items = PlannerTemplateItemSerializer(many=True, required=False)
    icon = serializers.CharField(required=False, validators=[validate_icon])
    color = serializers.ChoiceField(choices=COLORS, required=False)

    class Meta:
        model = PlannerTemplate
        fields = ["id", "name", "description", "icon", "color", "items", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        qs = PlannerTemplate.objects.filter(user=self.context["request"].user, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_("You already have a template with this name."))
        return value

    def validate_items(self, items):
        if len(items) > 60:
            raise serializers.ValidationError(_("A template can contain at most 60 activities."))
        user = self.context["request"].user
        cat_ids = {i.get("category_id") for i in items if i.get("category_id")}
        ch_ids = {i.get("challenge_id") for i in items if i.get("challenge_id")}
        if cat_ids and ActivityCategory.objects.filter(user=user, pk__in=cat_ids).count() != len(cat_ids):
            raise serializers.ValidationError(_("Unknown category."))
        if ch_ids and Challenge.objects.filter(user=user, pk__in=ch_ids).count() != len(ch_ids):
            raise serializers.ValidationError(_("Unknown challenge."))
        return items

    def _save_items(self, template, items):
        template.items.all().delete()
        PlannerTemplateItem.objects.bulk_create([PlannerTemplateItem(template=template, **i) for i in items])

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        template = PlannerTemplate.objects.create(**validated_data)
        self._save_items(template, items)
        return template

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if items is not None:
            self._save_items(instance, items)
        return instance
