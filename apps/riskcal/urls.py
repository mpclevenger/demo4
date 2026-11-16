"""The web addresses for the risk and control calendar and the events proposed on it."""

from django.urls import path

from . import views

app_name = "riskcal"

urlpatterns = [
    path("", views.index, name="index"),
    path("event/new/", views.event_new, name="new"),
    path("event/<int:pk>/", views.event_detail, name="event"),
    path("event/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("in-progress/", views.items, name="items"),
    path("in-progress/new/", views.item_new, name="item_new"),
    path("in-progress/<int:pk>/", views.item_detail, name="item"),
    path("in-progress/<int:pk>/edit/", views.item_edit, name="item_edit"),
]
