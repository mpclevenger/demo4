"""Checks the control form's level, categories and platforms, and the platform chips on a control page."""


import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.platforms.models import Platform
from apps.rcm import services
from apps.rcm.models import Control

from apps.core.tests.support import control_post, publish

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso")]


@pytest.fixture
def platforms():
    call_command("seed_platforms")
    return Platform.objects


def tagged_control(access, owner, reviewer, platform_list, **content):
    base = dict(title="Tagged", why="w", owner_role="o", nature="detective", method="manual", frequency="monthly")
    base.update(content)
    entity, version = services.create_control(owner.user, access, **base)
    version.platforms.set(platform_list)
    publish(version, reviewer.user)
    return entity


def test_control_page_header_shows_no_platforms(access, owner, reviewer, platforms):
    azure, sql = platforms.get(name="Azure"), platforms.get(name="SQL Server")
    entity = tagged_control(access, owner, reviewer, [azure, sql], level="key", categories=["database"])
    html = reviewer.get(entity.get_absolute_url()).content.decode()
    start = html.index('<header class="page-header">')
    header = html[start:html.index("</header>", start)]
    assert "Applies to:" not in header and "Azure" not in header and "SQL Server" not in header


# Control form

def test_form_renders_new_fields(owner, access, platforms):
    html = owner.get(reverse("rcm:control_new")).content.decode()
    assert 'name="level"' in html and "Non-key" in html and 'name="scope"' not in html and "Required for SOX" not in html
    assert 'name="categories"' in html and "Logging and monitoring" in html
    assert 'name="platforms"' in html and "<optgroup" in html and 'label="Cloud and containers"' in html
    assert 'data-field="part"' not in html and 'data-field="sox_only"' not in html


def test_form_offers_only_active_platforms(owner, access, platforms):
    Platform.objects.filter(name="Splunk").update(is_active=False)
    html = owner.get(reverse("rcm:control_new")).content.decode()
    assert ">Splunk<" not in html and 'label="Logging and monitoring"' not in html and ">AWS<" in html


def test_create_round_trips_categories_and_platforms(owner, access, platforms):
    azure, sql = platforms.get(name="Azure"), platforms.get(name="SQL Server")
    post = control_post(
        access, level="key", categories=["database", "network"], platforms=[azure.pk, sql.pk],
    )
    response = owner.post(reverse("rcm:control_new"), post)
    assert response.status_code == 302
    version = Control.objects.get().versions.get()
    assert version.level == "key" and version.categories == ["database", "network"]
    assert set(version.platforms.all()) == {azure, sql}
    form = owner.get(f"{reverse('rcm:control_edit', args=[version.entity.ident])}").context["form"]
    assert set(form.initial["platforms"]) == {azure.pk, sql.pk}
    assert form.initial["categories"] == ["database", "network"]


def test_level_is_saved_from_the_form(owner, access):
    owner.post(reverse("rcm:control_new"), control_post(access, level="supporting"))
    assert Control.objects.get().versions.get().level == "supporting"


def test_unknown_level_is_rejected(owner, access):
    response = owner.post(reverse("rcm:control_new"), control_post(access, level="made-up"))
    assert response.status_code == 200 and not Control.objects.exists()


def test_invalid_category_and_platform_are_rejected(owner, access, platforms):
    response = owner.post(reverse("rcm:control_new"), control_post(access, categories=["mainframe"], platforms=[99999]))
    form = response.context["form"]
    assert "categories" in form.errors and "platforms" in form.errors


def test_editing_published_control_copies_platforms_then_updates_draft(owner, reviewer, access, platforms):
    azure, sql = platforms.get(name="Azure"), platforms.get(name="SQL Server")
    entity, v1 = services.create_control(
        owner.user, access, title="T", why="w", owner_role="o", nature="detective", method="manual", frequency="monthly",
    )
    v1.platforms.set([azure])
    publish(v1, reviewer.user)
    response = owner.get(reverse("rcm:control_edit", args=[entity.ident]))
    assert response.context["form"].initial["platforms"] == [azure.pk]
    post = control_post(access, platforms=[sql.pk], change_summary="Retag")
    assert owner.post(reverse("rcm:control_edit", args=[entity.ident]), post).status_code == 302
    draft = entity.versions.get(number=2)
    assert list(draft.platforms.all()) == [sql]
    assert list(entity.versions.get(number=1).platforms.all()) == [azure]
