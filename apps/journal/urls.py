from django.urls import path

from . import views

app_name = "journal"
urlpatterns = [
    path("", views.journal_list, name="list"),
    path("new/", views.journal_detail, name="new"),
    path("review/", views.weekly_review, name="review"),
    path("<int:pk>/", views.journal_detail, name="detail"),
    path("<int:pk>/delete/", views.journal_delete, name="delete"),
]
