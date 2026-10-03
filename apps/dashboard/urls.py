from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("dashboard/", views.home, name="home"),
    path("today/", views.today, name="today"),
    path("calendar/", views.calendar, name="calendar"),
    path("calendar/<str:value>/", views.day, name="day"),
]
