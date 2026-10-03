from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with either username or email (case-insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or not password:
            return None
        lookup = {"email__iexact": username.strip()} if "@" in username else {"username__iexact": username.strip()}
        user = User.objects.filter(**lookup).first()
        if user is None:
            User().set_password(password)  # equalise timing to mitigate user enumeration
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
