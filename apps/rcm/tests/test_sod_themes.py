"""Segregation of duties, themes and nav highlighting."""

import re

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.rcm import services
from apps.rcm.models import Control, ControlVersion, Risk
from apps.core.tests.support import control_post, publish, published_control, risk_post

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso")]

# Scope merge migration

# Roles and the independence guidance

def control_page(viewer, approver, topic, **content):
    control, _ = published_control(topic, viewer.user, approver.user, **content)
    return viewer.get(control.get_absolute_url()).content.decode()


def test_role_fields_round_trip_through_the_form(owner, access):
    data = control_post(access, performer_role="Database administrator", reviewer_role="Application owner")
    assert owner.post(reverse("rcm:control_new"), data).status_code == 302
    version = ControlVersion.objects.get()
    assert (version.owner_role, version.performer_role, version.reviewer_role) == (
        "Identity and Access", "Database administrator", "Application owner"
    )
    html = owner.get(reverse("rcm:control_edit", args=[version.entity.ident])).content.decode()
    assert 'value="Database administrator"' in html and 'value="Application owner"' in html
    for label in ("Owner role", "Performed by (role)", "Reviewed by (role)"):
        assert label in html


def test_independence_fields_are_gone_from_form_and_model(owner):
    html = owner.get(reverse("rcm:control_new")).content.decode()
    for name in ("reviewer_independent", "compensating_check", "trac-sod"):
        assert name not in html
    names = {f.name for f in ControlVersion._meta.get_fields()}
    assert not names & {"reviewer_independent", "compensating_check", "owner", "performer", "reviewer"}


def test_control_page_does_not_show_the_role_line(owner, reviewer, access):
    html = control_page(owner, reviewer, access, performer_role="Operations", reviewer_role="Application owner")
    assert "Performed by" not in html and "Reviewed by" not in html and "Operations" not in html


# One SOX flag per kind

def test_control_shows_the_key_pill_only_for_key_controls(owner, reviewer, access):
    html = control_page(owner, reviewer, access, level="key")
    assert "tone-key" in html and ">Key<" in html and "SOX scope" not in html
    plain = control_page(owner, reviewer, access, title="Plain", level="supporting")
    assert "tone-key" not in plain and ">Supporting<" not in plain and "SOX scope" not in plain
    assert "Required for SOX" not in html + plain


def test_control_form_has_no_sox_checkbox_but_risk_form_does(owner):
    assert "In SOX scope" not in owner.get(reverse("rcm:control_new")).content.decode()
    assert "In SOX scope" in owner.get(reverse("rcm:risk_new")).content.decode()


def test_explorer_shows_level_column_not_scope(owner, reviewer, access):
    published_control(access, owner.user, reviewer.user, level="key", title="Top one")
    published_control(access, owner.user, reviewer.user, level="supporting", title="Helper one")
    html = owner.get(reverse("rcm:explorer"), {"view": "controls"}).content.decode()
    assert '<th scope="col">Level</th>' in html
    assert "Required for SOX" not in html and "Recommended for all" not in html


def test_risk_page_and_explorer_keep_the_risk_flag(owner, reviewer, access):
    flagged, version = services.create_risk(owner.user, access, title="Flagged", statement="s", owner_role="o",
                                            in_sox_scope=True)
    publish(version, reviewer.user)
    _, other = services.create_risk(owner.user, access, title="Unflagged", statement="s", owner_role="o")
    publish(other, reviewer.user)
    assert "SOX scope" in owner.get(flagged.get_absolute_url()).content.decode()
    html = owner.get(reverse("rcm:explorer"), {"sox": "1"}).content.decode()
    assert "Flagged" in html and "Unflagged" not in html


# Themes

def test_stage_and_theme_together_are_rejected(owner, access):
    theme = access.themes.first()
    stage = access.stages.first()
    for url, post in (
        (reverse("rcm:control_new"), control_post(access, stage, theme=theme.pk)),
        (reverse("rcm:risk_new"), risk_post(access, stage=stage.pk, theme=theme.pk)),
    ):
        response = owner.post(url, post)
        assert response.status_code == 200
        assert "Choose a stage or a theme, not both." in response.context["form"].errors["theme"]
    assert not Control.objects.exists() and not Risk.objects.exists()


def test_theme_must_belong_to_topic(owner, access, other_topic):
    foreign = other_topic.themes.first()
    response = owner.post(reverse("rcm:control_new"), control_post(access, theme=foreign.pk))
    assert response.status_code == 200
    assert "Pick a theme from the selected topic." in response.context["form"].errors["theme"]


def test_theme_is_saved_and_shown_on_forms(owner, access):
    theme = access.themes.get(name="Privileged access")
    owner.post(reverse("rcm:control_new"), control_post(access, theme=theme.pk))
    owner.post(reverse("rcm:risk_new"), risk_post(access, theme=theme.pk))
    assert ControlVersion.objects.get().theme == theme
    risk = Risk.objects.get()
    assert risk.versions.get().theme == theme
    html = owner.get(reverse("rcm:risk_edit", args=[risk.ident])).content.decode()
    assert "Use a theme instead of a stage when this applies across the whole lifecycle." in html
    assert f'<option value="{theme.pk}" selected>' in html


def test_topic_options_endpoint_is_signed_in_only(access):
    from django.test import Client

    assert Client().get(reverse("rcm:topic_options"), {"topic": access.pk}).status_code == 403


def test_detail_band_shows_theme_instead_of_stage(owner, reviewer, access):
    theme = access.themes.get(name="Privileged access")
    control, _ = published_control(access, owner.user, reviewer.user, theme=theme)
    html = owner.get(control.get_absolute_url()).content.decode()
    band = html.split('class="page-header"')[0]
    assert 'aria-current="page">Privileged access<' in band
    assert "lifecycle-strip" in band and 'aria-current="step"' not in band
    stage = access.stages.first()
    staged, _ = published_control(access, owner.user, reviewer.user, title="Staged", stage=stage)
    band = owner.get(staged.get_absolute_url()).content.decode().split('class="page-header"')[0]
    assert f'aria-current="step">{stage.name}<' in band


def test_explorer_row_shows_theme_name(owner, reviewer, access):
    theme = access.themes.get(name="Privileged access")
    published_control(access, owner.user, reviewer.user, theme=theme)
    assert f"{access.name} / Privileged access" in owner.get(reverse("rcm:explorer"), {"view": "controls"}).content.decode()


# Navigation

def active_nav(response):
    html = response.content.decode()
    nav = html.split('aria-label="Primary"')[1].split("</nav>")[0]
    return re.findall(r'aria-current="page">([^<]+)<', nav)


def test_every_rcm_page_highlights_risks_and_controls(owner, reviewer, access, live_control):
    risk, version = services.create_risk(owner.user, access, title="R", statement="s", owner_role="o")
    publish(version, reviewer.user)
    urls = [
        reverse("rcm:explorer"), live_control.get_absolute_url(), risk.get_absolute_url(),
        reverse("rcm:control_new"), reverse("rcm:risk_new"),
        reverse("rcm:control_edit", args=[live_control.ident]),
    ]
    for url in urls:
        assert active_nav(owner.get(url)) == ["Risks and controls"], url


def test_platform_pages_highlight_library(owner, topics):
    from apps.platforms.models import Platform

    call_command("seed_platforms")
    platform = Platform.objects.first()
    for url in (reverse("core:library"), platform.get_absolute_url()):
        assert active_nav(owner.get(url)) == ["Controls"], url
