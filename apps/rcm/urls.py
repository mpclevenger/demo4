"""The web addresses for the risk, control and driver pages, the explorer and the engine risks list."""

from django.urls import path, re_path

from . import urls_edit, views_read

app_name = "rcm"

urlpatterns = [
    path("", views_read.explorer, name="explorer"),
    path("sox/", views_read.sox_controls, name="sox"),
    re_path(r"^(?P<kind>control|risk)s/(?P<ident>(?:R-)?(?:MC|MA|OP)-\d+)/$", views_read.old_code_page),
    path("controls/<str:ident>/", views_read.control_detail, name="control"),
    path("risks/<str:ident>/", views_read.risk_detail, name="risk"),
    path("drivers/<str:ident>/", views_read.driver_detail, name="driver"),
    path("engine-risks/", views_read.engine_risks, name="engine_risks"),
    *urls_edit.urlpatterns,
]
