"""Supplies the links to TRUST and Risk to every page."""

from django.conf import settings


def suite(request):
    return {"suite_links": {k: v for k, v in settings.SUITE_LINKS.items() if v}}
