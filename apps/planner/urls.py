from django.urls import path

from . import views

app_name = "planner"
urlpatterns = [
    path("", views.week, name="week"),
    path("routines/", views.rules, name="rules"),
    path("templates/", views.templates, name="templates"),
]
