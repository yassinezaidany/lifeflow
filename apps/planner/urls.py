from django.urls import path

from . import views

app_name = "planner"
urlpatterns = [
    path("", views.week, name="week"),
    path("routines/", views.rules, name="rules"),
    path("templates/", views.templates, name="templates"),
    path("export.ics", views.export_ics, name="export_ics"),
    path("feed/<str:token>.ics", views.calendar_feed, name="feed"),
    path("feed/regenerate/", views.regenerate_feed, name="regenerate_feed"),
]
