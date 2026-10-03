from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext as _
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.audit import audit
from apps.core.models import AuditLog

from . import ratelimit
from .models import Profile, UserSetting

User = get_user_model()


class AuthThrottle(ScopedRateThrottle):
    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["timezone", "language", "date_format", "time_format", "week_start", "theme", "bio",
                  "planner_slot_minutes", "planner_day_start", "planner_day_end", "onboarding_completed"]

    def validate(self, attrs):
        start = attrs.get("planner_day_start", getattr(self.instance, "planner_day_start", 5))
        end = attrs.get("planner_day_end", getattr(self.instance, "planner_day_end", 24))
        if not (0 <= start < end <= 24):
            raise serializers.ValidationError({"planner_day_end": _("The planner must end after it starts (0–24h).")})
        return attrs


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSetting
        exclude = ["id", "user", "created_at", "updated_at"]


class MeSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()
    settings = SettingsSerializer()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "profile", "settings", "date_joined"]
        read_only_fields = ["id", "date_joined"]

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError(_("This email is already used."))
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError(_("This username is taken."))
        return value

    def update(self, instance, validated_data):
        profile = validated_data.pop("profile", None)
        prefs = validated_data.pop("settings", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if profile:
            for k, v in profile.items():
                setattr(instance.profile, k, v)
            instance.profile.save()
        if prefs:
            for k, v in prefs.items():
                setattr(instance.settings, k, v)
            instance.settings.save()
        return instance


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[\w.@+-]{3,150}$", max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    timezone = serializers.CharField(required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(_("This username is taken."))
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("An account already exists with this email."))
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        return attrs


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    user = User.objects.create_user(username=d["username"], email=d["email"], password=d["password"], first_name=d.get("first_name", ""))
    tz = d.get("timezone")
    from apps.accounts.models import TIMEZONE_CHOICES
    if tz and tz in dict(TIMEZONE_CHOICES):
        user.profile.timezone = tz
        user.profile.save(update_fields=["timezone"])
    login(request, user, backend="apps.accounts.backends.EmailOrUsernameBackend")
    audit(user, AuditLog.Action.ACCOUNT, user, description="registered")
    return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([AuthThrottle])
def login_view(request):
    identifier = (request.data.get("username") or request.data.get("email") or "").strip()
    password = request.data.get("password") or ""
    if ratelimit.is_rate_limited(request, identifier):
        return Response({"detail": _("Too many attempts. Please wait a few minutes.")}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    user = authenticate(request, username=identifier, password=password)
    if user is None:
        ratelimit.register_failure(request, identifier)
        return Response({"detail": _("Invalid credentials.")}, status=status.HTTP_400_BAD_REQUEST)
    ratelimit.reset(request, identifier)
    login(request, user)
    return Response(MeSerializer(user).data)


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "PATCH"])
def me(request):
    if request.method == "PATCH":
        s = MeSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    return Response(MeSerializer(request.user).data)


@api_view(["POST"])
def change_password(request):
    current = request.data.get("current_password") or ""
    new = request.data.get("new_password") or ""
    if not request.user.check_password(current):
        return Response({"detail": _("Please correct the errors below."), "errors": {"current_password": [_("Incorrect password.")]}}, status=400)
    validate_password(new, request.user)
    request.user.set_password(new)
    request.user.save()
    update_session_auth_hash(request, request.user)
    audit(request.user, AuditLog.Action.ACCOUNT, request.user, description="password changed")
    return Response({"detail": _("Password updated.")})
