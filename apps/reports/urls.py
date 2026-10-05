from django.urls import path

from . import views

app_name = "reports"
urlpatterns = [
    path("", views.report_list, name="list"),
    path("generate/", views.generate, name="generate"),
    path("export/", views.export, name="export"),
    path("import/", views.import_entries, name="import"),
    path("<int:pk>/", views.report_detail, name="detail"),
    path("<int:pk>/pdf/", views.report_pdf, name="pdf"),
    path("<int:pk>/delete/", views.report_delete, name="delete"),
]
