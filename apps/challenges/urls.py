from django.urls import path

from . import views

app_name = "challenges"
urlpatterns = [
    path("", views.challenge_list, name="list"),
    path("new/", views.challenge_create, name="create"),
    path("templates/", views.templates_gallery, name="templates"),
    path("<int:pk>/", views.challenge_detail, name="detail"),
    path("<int:pk>/settings/", views.challenge_settings, name="settings"),
]
