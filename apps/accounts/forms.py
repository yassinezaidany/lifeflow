from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _

from .models import TIMEZONE_CHOICES, Profile, UserSetting

User = get_user_model()


class StyledFormMixin:
    """Apply design-system classes to widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "checkbox")
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "select")
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault("class", "textarea")
                w.attrs.setdefault("rows", 3)
            elif isinstance(w, forms.ClearableFileInput):
                w.attrs.setdefault("class", "block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-subtle file:px-3 file:py-2 file:text-sm file:font-medium file:text-ink hover:file:bg-line")
            else:
                w.attrs.setdefault("class", "input")
            if self.errors.get(name):
                w.attrs["class"] += " is-invalid"
                w.attrs["aria-invalid"] = "true"


class RegisterForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(label=_("First name"), max_length=150, required=False)
    username = forms.RegexField(label=_("Username"), regex=r"^[\w.@+-]{3,150}$", max_length=150,
                                error_messages={"invalid": _("3+ characters: letters, numbers and . @ + - _ only.")})
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                               help_text=_("At least 8 characters, not too common."))
    timezone = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=value).exists():
            raise forms.ValidationError(_("This username is taken."))
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError(_("An account already exists with this email."))
        return value

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("username") and data.get("email"):
            try:
                password_validation.validate_password(data["password"], User(username=data["username"], email=data["email"]))
            except forms.ValidationError as e:
                self.add_error("password", e)
        return data

    def clean_timezone(self):
        tz = self.cleaned_data.get("timezone")
        return tz if tz in dict(TIMEZONE_CHOICES) else None


class LoginForm(StyledFormMixin, forms.Form):
    username = forms.CharField(label=_("Email or username"), max_length=254, widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    remember = forms.BooleanField(label=_("Keep me signed in"), required=False, initial=True)


class AccountForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("This email is already used."))
        return value

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("This username is taken."))
        return value


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar", "bio", "timezone", "language", "date_format", "time_format", "week_start", "theme",
                  "planner_slot_minutes", "planner_day_start", "planner_day_end"]
        widgets = {"bio": forms.TextInput()}

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size") and avatar.size > 2 * 1024 * 1024:
            raise forms.ValidationError(_("The image must be smaller than 2 MB."))
        return avatar

    def clean(self):
        data = super().clean()
        start, end = data.get("planner_day_start"), data.get("planner_day_end")
        if start is not None and end is not None and not (0 <= start < end <= 24):
            self.add_error("planner_day_end", _("The planner must end after it starts (0–24h)."))
        return data


class NotificationSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = UserSetting
        exclude = ["user", "created_at", "updated_at"]
        widgets = {"end_of_day_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass
