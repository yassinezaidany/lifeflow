from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("welcome/", views.onboarding, name="onboarding"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/notifications/", views.notifications_view, name="notifications"),
    path("settings/security/", views.security_view, name="security"),
    path("settings/categories/", views.categories_view, name="categories"),
    path("settings/delete/", views.delete_account, name="delete"),
    path("password/reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
