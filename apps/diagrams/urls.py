"""The web addresses for the diagram pages."""

from django.urls import path

from . import views

app_name = "diagrams"

urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:name>/", views.detail, name="detail"),
    path("<slug:name>/download/", views.download, name="download"),
]
