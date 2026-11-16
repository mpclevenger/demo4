"""Checks the My system pages: the form, the answers in the session, the bar, category pages and Next on your path."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.core.tests.support import As
from apps.pathfinder import questions
from apps.pathfinder.answers import SESSION_KEY
from apps.platforms.categories import Category
from apps.platforms.tests.support import publish_control
from apps.wiki.tests.support import count_queries

pytestmark = pytest.mark.django_db

INDEX, PATH, START_OVER = "/my-system/", "/my-system/path/", "/my-system/start-over/"
JOBS = questions.questions()[0]


@pytest.fixture(autouse=True)
def seeded(sso):
    call_command("seed_topics")
    call_command("seed_platforms")


@pytest.fixture
def visitor():
    return As("visitor", "ro")


def answer(who, **extra):
    data = {"platform": ["sql-server", "windows-server"], f"q-{JOBS.key}": "yes", "sox": "yes", "tier": "0-1"}
    data.update(extra)
    return who.post(INDEX, data)


def html(response):
    return response.content.decode()


# The two screens

def test_the_routes_are_my_system():
    assert reverse("pathfinder:index") == INDEX and reverse("pathfinder:path") == PATH


def test_the_questions_page_has_real_controls_and_one_button(visitor):
    page = html(visitor.get(INDEX))
    assert "Tell us about your system" in page and "css/pathfinder.css" in page
    assert 'type="checkbox" name="platform" value="sql-server"' in page
    for q in questions.questions():
        assert q.text in page and f'name="q-{q.key}" value="yes"' in page and f'name="q-{q.key}" value="no"' in page
    assert 'name="sox" value="not_sure" checked' in page and 'name="tier" value="not_sure" checked' in page
    form = page[page.index('class="my-system-form"'):page.index("</form>", page.index('class="my-system-form"'))]
    assert form.count('type="submit"') == 1 and ">Show my path</button>" in form


def test_saving_answers_opens_the_path_and_keeps_only_known_values(visitor):
    response = answer(visitor, platform=["sql-server", "nope"], tier="7")
    assert response.status_code == 302 and response["Location"] == PATH
    assert visitor.client.session[SESSION_KEY] == {
        "platforms": ["sql-server"], "replies": {JOBS.key: "yes"}, "sox": "yes", "tier": "not_sure",
    }


def test_the_path_without_answers_goes_back_to_the_questions(visitor):
    response = visitor.get(PATH)
    assert response.status_code == 302 and response["Location"] == INDEX


def test_the_path_shows_answers_tier_sox_and_numbered_areas(visitor):
    answer(visitor, **{f"q-{JOBS.key}": "no"})
    page = html(visitor.get(PATH))
    assert "Showing guidance for: <strong>Windows Server, SQL Server, Tier 0 or 1, SOX in scope</strong>" in page
    assert "the same question usually gets a shorter answer" in page and "/guides/timings-your-team-sets/" in page
    assert reverse("rcm:sox") in page
    assert 'id="area-access"' in page and "Applies to every system" in page
    assert 'id="area-jobs"' not in page and "Left out because of your answers" in page
    assert f'you said no to "{JOBS.text}"' in page
    assert ">In progress<" in page  # no platform guidance is published in this test


def test_sox_no_and_not_sure_read_differently(visitor):
    answer(visitor, sox="no", tier="3+")
    page = html(visitor.get(PATH))
    assert "On the SOX in-scope list" not in page and "SOX scope not sure" not in page
    assert "Your system is tier 3 or higher" in page and "/guides/timings-your-team-sets/" in page
    answer(visitor, sox="not_sure")
    assert "SOX scope not sure" in html(visitor.get(PATH))


def test_change_shows_the_answers_filled_in(visitor):
    answer(visitor)
    page = html(visitor.get(INDEX))
    assert 'value="sql-server" checked' in page and 'value="aws" checked' not in page
    assert f'name="q-{JOBS.key}" value="yes" checked' in page
    assert 'name="sox" value="yes" checked' in page and 'name="tier" value="0-1" checked' in page


def test_start_over_clears_the_answers_and_needs_a_post(visitor):
    answer(visitor)
    assert visitor.get(START_OVER).status_code == 405
    response = visitor.post(START_OVER)
    assert response.status_code == 302 and response["Location"] == INDEX
    assert SESSION_KEY not in visitor.client.session


def test_a_platform_switched_off_since_is_ignored(visitor):
    from apps.platforms.models import Platform

    answer(visitor)
    Platform.objects.filter(slug="windows-server").update(is_active=False)
    assert "Showing guidance for: <strong>SQL Server, Tier 0 or 1" in html(visitor.get(PATH))


def test_every_role_can_use_my_system():
    for group in ("tr", "co", "aud", "ro"):
        who = As(f"user-{group}", group)
        assert who.get(INDEX).status_code == 200
        assert answer(who).status_code == 302 and who.get(PATH).status_code == 200


# The bar

def test_the_bar_shows_on_other_pages_once_answered_but_not_on_my_system(visitor):
    library = reverse("core:library")
    assert "my-system-bar" not in html(visitor.get(library))
    answer(visitor)
    page = html(visitor.get(library))
    assert "Showing guidance for: <strong>Windows Server, SQL Server, Tier 0 or 1, SOX in scope</strong>" in page
    assert f'href="{PATH}">Your path</a>' in page and f'href="{INDEX}">Change</a>' in page
    assert "my-system-bar" not in html(visitor.get(PATH))


def test_the_bar_costs_no_query_without_answers_and_one_with_them(visitor):
    url = reverse("core:library")
    without = count_queries(visitor.client, url, **visitor.headers)
    answer(visitor)
    assert count_queries(visitor.client, url, **visitor.headers) == without + 1


# Library category pages

def test_category_pages_open_with_the_visitor_s_platforms_switched_on(visitor):
    url = reverse("platforms:category", args=["database"])
    assert 'aria-pressed="true"' not in html(visitor.get(url))
    answer(visitor)
    page = html(visitor.get(url))
    assert 'aria-pressed="true" data-platform-toggle="sql-server"' in page
    assert 'id="aspect-access"' in page


def test_a_choice_made_on_the_category_page_wins(visitor):
    answer(visitor)
    url = reverse("platforms:category", args=["database"])
    assert 'aria-pressed="true"' not in html(visitor.get(url + "?platform="))
    page = html(visitor.get(url + "?platform=aws"))
    assert 'aria-pressed="true" data-platform-toggle="aws"' in page
    assert 'aria-pressed="true" data-platform-toggle="sql-server"' not in page


# Next on your path

def test_a_control_reached_from_the_path_offers_the_next_step(visitor):
    first = publish_control("AM", title="First access", categories=[Category.DATABASE])
    second = publish_control("AM", title="Second access", categories=[Category.DATABASE])
    answer(visitor)
    path_page = html(visitor.get(PATH))
    assert f"{first.get_absolute_url()}?path=access" in path_page
    page = html(visitor.get(f"{first.get_absolute_url()}?path=access"))
    assert "Next on your path" in page and f'href="{second.get_absolute_url()}?path=access"' in page


def test_the_next_link_stays_off_for_other_visitors(visitor):
    control = publish_control("AM", title="First access", categories=[Category.DATABASE])
    assert "Next on your path" not in html(visitor.get(f"{control.get_absolute_url()}?path=access"))
    answer(visitor)
    assert "Next on your path" not in html(visitor.get(control.get_absolute_url()))
    assert visitor.get(f"{control.get_absolute_url()}?path=not-an-area").status_code == 200
