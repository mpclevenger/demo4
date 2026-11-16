"""The web addresses for My system: the questions, the visitor's path and Start over."""

from django.urls import path

from . import views

app_name = "pathfinder"

urlpatterns = [
    path("", views.index, name="index"),
    path("path/", views.path, name="path"),
    path("start-over/", views.start_over, name="start_over"),
]
