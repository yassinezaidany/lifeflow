from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.challenges.models import ChallengeTemplate
from apps.core.audit import audit
from apps.core.icons import picker_icons
from apps.core.models import AuditLog

from . import ratelimit
from .forms import (
    AccountForm,
    LoginForm,
    NotificationSettingsForm,
    ProfileForm,
    RegisterForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)

User = get_user_model()


def _safe_next(request, fallback="dashboard:home"):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return fallback


def localize_default_categories(user, language: str) -> None:
    """Default categories are seeded in English; rename them in the user's language
    so they become ordinary, editable user data."""
    from django.utils import translation

    from apps.challenges.models import ChallengeCategory
    from apps.planner.models import ActivityCategory

    if language == "en":
        return
    with translation.override(language):
        for model in (ChallengeCategory, ActivityCategory):
            for cat in model.objects.filter(user=user):
                localized = _(cat.name)
                if localized != cat.name and not model.objects.filter(user=user, name=localized).exists():
                    cat.name = localized
                    cat.save(update_fields=["name", "updated_at"])


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(username=d["username"], email=d["email"], password=d["password"], first_name=d.get("first_name", ""))
        profile = user.profile
        if d.get("timezone"):
            profile.timezone = d["timezone"]
        lang = getattr(request, "LANGUAGE_CODE", "en")
        profile.language = "fr" if lang.startswith("fr") else "en"
        profile.save()
        localize_default_categories(user, profile.language)
        login(request, user, backend="apps.accounts.backends.EmailOrUsernameBackend")
        audit(user, AuditLog.Action.ACCOUNT, user, description="registered")
        return redirect("accounts:onboarding")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth import authenticate

        identifier = form.cleaned_data["username"].strip()
        if ratelimit.is_rate_limited(request, identifier):
            form.add_error(None, _("Too many attempts. Please wait a few minutes and try again."))
        else:
            user = authenticate(request, username=identifier, password=form.cleaned_data["password"])
            if user is None:
                ratelimit.register_failure(request, identifier)
                form.add_error(None, _("The email/username or password is incorrect."))
            else:
                ratelimit.reset(request, identifier)
                login(request, user)
                if not form.cleaned_data.get("remember"):
                    request.session.set_expiry(0)
                return redirect(_safe_next(request))
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, _("You have been signed out."))
    return redirect("accounts:login")


@login_required
def settings_view(request):
    account_form = AccountForm(request.POST or None, instance=request.user, prefix="account")
    profile_form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile, prefix="profile")
    if request.method == "POST":
        if account_form.is_valid() and profile_form.is_valid():
            account_form.save()
            profile_form.save()
            messages.success(request, _("Your settings were saved."))
            return redirect("accounts:settings")
        messages.error(request, _("Please correct the errors below."))
    return render(request, "accounts/settings.html", {"account_form": account_form, "profile_form": profile_form, "tab": "profile"})


@login_required
def notifications_view(request):
    form = NotificationSettingsForm(request.POST or None, instance=request.user.settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Notification preferences saved."))
        return redirect("accounts:notifications")
    return render(request, "accounts/notifications.html", {"form": form, "tab": "notifications"})


@login_required
def security_view(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        audit(user, AuditLog.Action.ACCOUNT, user, description="password changed")
        messages.success(request, _("Your password was changed."))
        return redirect("accounts:security")
    return render(request, "accounts/security.html", {"form": form, "tab": "security"})


@login_required
@require_POST
def delete_account(request):
    if not request.user.check_password(request.POST.get("password", "")):
        messages.error(request, _("Incorrect password. Your account was not deleted."))
        return redirect("accounts:security")
    user = request.user
    logout(request)
    user.delete()
    messages.info(request, _("Your account and all your data were deleted."))
    return redirect("accounts:login")


@login_required
def categories_view(request):
    return render(request, "accounts/categories.html", {"tab": "categories", "icons": picker_icons()})


@login_required
def onboarding(request):
    if request.method == "POST":
        profile = request.user.profile
        profile.onboarding_completed = True
        profile.save(update_fields=["onboarding_completed"])
        return redirect("dashboard:home")
    templates = ChallengeTemplate.objects.filter(owner__isnull=True)
    return render(request, "accounts/onboarding.html", {
        "templates": [
            {"slug": t.slug, "name": t.name, "description": t.description, "icon": t.icon, "color": t.color, "category": t.category_name}
            for t in templates
        ],
        "step": request.GET.get("step", "welcome"),
    })


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset.txt"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    form_class = StyledPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
