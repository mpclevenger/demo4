"""Checks which risk areas apply for which answers, the Ready rule, the controls shown and the Next link target."""

import pytest
from django.core.management import call_command

from apps.pathfinder import paths
from apps.pathfinder.answers import Answers, clean
from apps.pathfinder.questions import Question
from apps.platforms.categories import Category
from apps.platforms.models import AspectQuestion, Platform
from apps.platforms.tests.support import publish_control, publish_guidance

pytestmark = pytest.mark.django_db

JOBS = Question("jobs", "Does it run jobs?", "it runs jobs", ("Jobs",))
VENDOR = Question("vendor", "Does a vendor run it?", "", ("vendor",))
ALSO_JOBS = Question("transfers", "Does it move files?", "it moves files", ("Jobs",))
ASKED = [JOBS, VENDOR]


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_topics")
    call_command("seed_platforms")


def aspect(label):
    return AspectQuestion.objects.get(label=label)


def platform(name):
    return Platform.objects.get(name=name)


def labels(path):
    return [area.question.label for area in path.areas]


# Which areas apply

def test_areas_no_question_names_always_apply_with_that_reason():
    applies, why = paths.decide(aspect("Access"), ASKED, Answers())
    assert applies and why == "Applies to every system"


def test_a_yes_adds_the_area_with_the_question_s_reason():
    assert paths.decide(aspect("Jobs"), ASKED, Answers(replies={"jobs": "yes"})) == (True, "Because it runs jobs")
    assert paths.decide(aspect("Vendor"), ASKED, Answers(replies={"vendor": "yes"})) == (
        True, "Because you said yes to: Does a vendor run it?"
    )


def test_an_unanswered_question_keeps_its_area_on_the_path():
    assert paths.decide(aspect("Jobs"), ASKED, Answers()) == (True, "Included until you answer: Does it run jobs?")


def test_a_no_leaves_the_area_out_unless_another_question_says_yes():
    assert paths.decide(aspect("Jobs"), ASKED, Answers(replies={"jobs": "no"})) == (False, "Does it run jobs?")
    both = [JOBS, ALSO_JOBS]
    assert paths.decide(aspect("Jobs"), both, Answers(replies={"jobs": "no", "transfers": "yes"}))[0]
    assert not paths.decide(aspect("Jobs"), both, Answers(replies={"jobs": "no", "transfers": "no"}))[0]


def test_the_path_keeps_catalog_order_numbers_the_areas_and_lists_what_was_left_out():
    path = paths.build(Answers(replies={"jobs": "no", "vendor": "yes"}), ASKED)
    expected = [a.label for a in AspectQuestion.objects.all() if a.label != "Jobs"]
    assert labels(path) == expected
    assert [area.number for area in path.areas] == list(range(1, len(expected) + 1))
    assert [(q.label, asked) for q, asked in path.skipped] == [("Jobs", "Does it run jobs?")]


def test_an_unknown_label_in_the_file_matches_nothing_and_breaks_nothing():
    odd = Question("odd", "Odd?", "", ("Not an area",))
    path = paths.build(Answers(replies={"odd": "no"}), [odd])
    assert len(path.areas) == AspectQuestion.objects.count() and path.skipped == []


# Ready or In progress

def test_ready_needs_published_guidance_for_the_area_on_every_picked_platform():
    sql, windows = platform("SQL Server"), platform("Windows Server")
    publish_guidance({"platform": sql}, tag="sql", lines={"Access": "On SQL Server.", "Jobs": "Agent jobs."})
    publish_guidance({"platform": windows}, tag="win", lines={"Access": "On Windows."})
    path = paths.build(Answers(platforms=[sql, windows]), ASKED)
    ready = {area.question.label: area.ready for area in path.areas}
    assert ready["Access"] is True
    assert ready["Jobs"] is False  # Windows Server has nothing for Jobs yet
    assert ready["Change"] is False


def test_with_no_platform_ready_means_some_category_practices_cover_the_area():
    publish_guidance({"category": "database"}, tag="db", lines={"Change": "Through change control."})
    ready = {area.question.label: area.ready for area in paths.build(Answers(), ASKED).areas}
    assert ready["Change"] is True and ready["Access"] is False


def test_unpublished_guidance_does_not_count():
    from apps.core import versioning as v
    from apps.platforms.models import Guidance, GuidanceVersion
    from apps.platforms.tests.support import question, tech_risk_pair

    owner, _ = tech_risk_pair("draft")
    v.create_entity(Guidance, GuidanceVersion, owner, {"platform": platform("VPN")},
                    lines=[{"question": question("Access").pk, "text": "Draft only."}])
    ready = {area.question.label: area.ready for area in paths.build(Answers(platforms=[platform("VPN")]), ASKED).areas}
    assert ready["Access"] is False


# Controls and Library links

def test_controls_fit_the_picked_platforms_categories_and_come_from_the_area_s_topic():
    fits = publish_control("AM", title="Database access", categories=[Category.DATABASE])
    tagged = publish_control("AM", [platform("SQL Server")], title="Tagged to SQL Server")
    elsewhere = publish_control("AM", title="Network access", categories=[Category.NETWORK])
    publish_control("CM", title="A change control", categories=[Category.DATABASE])
    access = paths.build(Answers(platforms=[platform("SQL Server")]), ASKED).areas[0]
    shown = {control.pk for control, _, _ in access.controls}
    assert access.question.label == "Access"
    assert shown == {fits.pk, tagged.pk}
    assert all(url == f"{control.get_absolute_url()}?path=access" for control, _, url in access.controls)
    every = paths.build(Answers(), ASKED).areas[0]
    assert {control.pk for control, _, _ in every.controls} == {fits.pk, tagged.pk, elsewhere.pk}


def test_library_links_open_each_category_with_the_picked_platforms_at_the_area():
    sql, windows = platform("SQL Server"), platform("Windows Server")
    jobs = next(a for a in paths.build(Answers(platforms=[windows, sql]), ASKED).areas if a.question.label == "Jobs")
    links = [(category.value, url) for category, url in jobs.library]
    assert links == [
        ("database", "/platforms/category/database/?platform=sql-server#aspect-jobs"),
        ("operating_system", "/platforms/category/operating_system/?platform=windows-server#aspect-jobs"),
        ("jobs", "/platforms/category/jobs/?platform=windows-server&platform=sql-server#aspect-jobs"),
    ]
    assert paths.build(Answers(), ASKED).areas[0].library == []


# Next on your path

def test_next_goes_to_the_next_control_then_the_next_area_then_back_to_the_path():
    first = publish_control("AM", title="First access", categories=[Category.DATABASE])
    second = publish_control("AM", title="Second access", categories=[Category.DATABASE])
    change = publish_control("CM", title="A change control", categories=[Category.DATABASE])
    path = paths.build(Answers(replies={"jobs": "no", "vendor": "no"}), ASKED)
    access = [c for c, _, _ in path.areas[0].controls]
    step = paths.next_step(path, "access", access[0])
    assert step["url"] == f"{access[1].get_absolute_url()}?path=access"
    # Service accounts (also topic AM) is next on the path, so its first control follows.
    step = paths.next_step(path, "access", access[1])
    assert step["text"].startswith("Service accounts: ") and step["url"].endswith("?path=service-accounts")
    step = paths.next_step(path, "service-accounts", access[1])
    assert step["text"] == f"Change: {change.ident} A change control"
    last = [c for c, _, _ in path.areas[-1].controls]
    assert last == []
    assert paths.next_step(path, "change", change) == {"text": "Back to your path", "url": "/my-system/path/"}
    assert paths.next_step(path, "jobs", change) is None  # Jobs is not on this path
    assert {first.pk, second.pk} == set(c.pk for c in access)


# Cleaning saved answers

def test_clean_drops_unknown_platforms_questions_and_values():
    raw = {"platforms": ["sql-server", "gone", 3], "replies": {"jobs": "yes", "vendor": "maybe", "old": "no"},
           "sox": "perhaps", "tier": "2"}
    assert clean(raw, {"sql-server"}, {"jobs", "vendor"}) == {
        "platforms": ["sql-server"], "replies": {"jobs": "yes"}, "sox": "not_sure", "tier": "2",
    }
    assert clean("rubbish", set(), set()) == {"platforms": [], "replies": {}, "sox": "not_sure", "tier": "not_sure"}
