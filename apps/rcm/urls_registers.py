"""The published, read-only registers other sites read. Included at /registers/ by config/urls.py."""

from django.urls import path

from . import views_read

urlpatterns = [
    path("controls.json", views_read.controls_json, name="controls_json"),
]
