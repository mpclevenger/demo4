"""Query counts stay flat as data grows; Tech Risk-only edit helpers."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.tests.support import As, publish, published_control, published_driver
from apps.rcm import services

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso")]


def add_register_items(topic, owner, reviewer, count, start=0):
    """`count` more controls, drivers and risks, each risk linked to its own control and driver."""
    for n in range(start, start + count):
        control = published_control(topic, owner.user, reviewer.user, title=f"Control {n}")[0]
        driver = published_driver(owner.user, reviewer.user, title=f"Driver {n}")[0]
        entity, version = services.create_risk(
            owner.user, topic, title=f"Risk {n}", statement="s", owner_role="IAM"
        )
        services.set_risk_links(version, owner.user, controls=[(control, "full", "Covers it")], drivers=[driver])
        publish(version, reviewer.user)


def query_count(user, url):
    user.get(url)  # the first request signs the user in, which has its own queries
    with CaptureQueriesContext(connection) as queries:
        assert user.get(url).status_code == 200
    return len(queries)


def pages(topic):
    """URLs to measure: the explorer in both views, the matrix-driven detail pages."""
    return [
        reverse("rcm:explorer"),
        reverse("rcm:explorer") + "?view=controls",
        reverse("rcm:control", args=["AM-01"]),
        reverse("rcm:risk", args=["R-AM-01"]),
        reverse("rcm:driver", args=["RD01"]),
    ]


def test_query_counts_do_not_grow_with_data(owner, reviewer, access):
    add_register_items(access, owner, reviewer, 5)
    small = [query_count(owner, url) for url in pages(access)]
    add_register_items(access, owner, reviewer, 10, start=5)
    large = [query_count(owner, url) for url in pages(access)]
    assert large == small


def test_explorer_query_count_has_a_fixed_ceiling(owner, reviewer, access):
    add_register_items(access, owner, reviewer, 5)
    assert query_count(owner, reverse("rcm:explorer")) <= 20


# Permissions: every rcm edit-side page is Tech Risk only

@pytest.mark.parametrize("group", ["co", "ro", "aud"])
def test_edit_side_pages_are_tech_risk_only(owner, reviewer, access, group):
    control, _ = published_control(access, owner.user, reviewer.user)
    urls = [
        reverse("rcm:control_new"),
        reverse("rcm:control_edit", args=[control.ident]),
        reverse("rcm:topic_options"),
    ]
    other = As(f"other-{group}", group)
    assert [other.get(url).status_code for url in urls] == [403] * len(urls)


def test_tech_risk_reaches_edit_side_pages(owner):
    assert owner.get(reverse("rcm:topic_options")).status_code == 200
