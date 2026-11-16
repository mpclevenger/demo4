"""The calendar's In progress list: proposing items, what shows beside the month, the filters and the colors."""

import datetime
import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core import versioning as v
from apps.core.tests.support import As, published_control
from apps.riskcal import services, work_items
from apps.riskcal.models import ItemStatus, WorkItem
from apps.topics.models import Topic
from apps.ui.tests.test_colors import contrast

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso", "today")]

DEC_15 = datetime.date(2026, 12, 15)


@pytest.fixture
def jobs():
    return Topic.objects.create(name="Operations and jobs", slug="operations-and-jobs", id_prefix="MO", icon="clock", position=6)


@pytest.fixture
def access():
    return Topic.objects.create(name="Access management", slug="access-management", id_prefix="AM", icon="key", position=1)


@pytest.fixture
def anyone():
    return As("rita", "ro")


@pytest.fixture
def tech_risk():
    return As("tara", "tr")


@pytest.fixture
def make(anyone, tech_risk, write_calendar, jobs):
    """Propose an item as a read-only visitor and approve it as Tech Risk; returns the item."""
    write_calendar()

    def make_item(**fields):
        content = {"title": "Job inventory guidance", "covers": "", "progress": ItemStatus.IN_PROGRESS, "topic": jobs,
                   "control": "", "team": "Tech Risk", "expected_on": DEC_15, "went_live_on": None, "runs_passed": 0, **fields}
        item, version = services.propose_item(anyone.user, **content)
        v.approve_and_publish(version, tech_risk.user)
        return item

    return make_item


def page(who, query="?month=2026-12"):
    return who.get(reverse("riskcal:index") + query).content.decode()


def panel_of(html):
    return html[html.index('id="riskcal-work-title"'):html.index("</aside>")]


def form_post(**fields):
    data = {"title": "Audit-log feed checks", "covers": "", "progress": "in_progress", "control": "", "topic": "",
            "team": "Database team", "expected_on": "2026-12-18", "went_live_on": "", "runs_passed": "0"}
    data.update(fields)
    return data


def test_anyone_can_propose_an_item_and_it_shows_only_once_tech_risk_approves(anyone, tech_risk, write_calendar, jobs):
    write_calendar()
    response = anyone.post(reverse("riskcal:item_new"), form_post(topic=jobs.pk))
    assert response.status_code == 302
    version = WorkItem.objects.get().versions.get()
    assert version.status == v.Status.IN_REVIEW
    assert "Audit-log feed checks" not in page(anyone)
    v.approve_and_publish(version, tech_risk.user)
    assert "Audit-log feed checks" in panel_of(page(anyone))


def test_a_box_shows_the_name_code_team_date_and_chip_in_its_topic_color(anyone, make):
    make()
    panel = panel_of(page(anyone))
    box = panel[panel.index("riskcal-work-card"):]
    assert "riskcal-topic-MO" in box[:80]
    assert "MO · Proposed" in box and "Tech Risk" in box and "Expected go-live" in box and "Dec 15, 2026" in box
    assert ">In progress<" in box


def test_a_linked_control_shows_its_code_and_links_to_it(anyone, make, jobs):
    make(control="MO-02")
    assert "MO-02" in panel_of(page(anyone))


def test_the_expected_go_live_is_marked_on_its_day_in_the_same_color(anyone, make):
    make()
    html = page(anyone)
    marker = html[html.index('class="riskcal-golive '):]
    assert marker.startswith('class="riskcal-golive riskcal-topic-MO"')
    assert "Go-live (expected): </span>Job inventory guidance" in marker[:400]
    assert "riskcal-golive" not in page(anyone, "?month=2027-01")


def test_a_live_item_stays_until_two_runs_without_an_issue(anyone, make):
    make(title="Access walkthrough", progress=ItemStatus.LIVE, went_live_on=datetime.date(2026, 12, 2), runs_passed=1)
    make(title="Settled control", progress=ItemStatus.LIVE, went_live_on=datetime.date(2026, 12, 3), runs_passed=2)
    panel = panel_of(page(anyone))
    assert "Access walkthrough" in panel and ">Live<" in panel and "1 of 2 runs without an issue" in panel and "Went live" in panel
    assert "Settled control" not in panel


def test_wanted_items_without_a_date_say_not_set_yet(anyone, make):
    make(title="Cloud-only admin accounts", progress=ItemStatus.WANTED, expected_on=None)
    panel = panel_of(page(anyone))
    assert ">Wanted<" in panel and "Not set yet" in panel


def test_filters_narrow_the_list_and_the_markers_and_the_month_links_keep_them(anyone, make, access):
    make()
    make(title="Admin accounts review", topic=access, team="Identity team", expected_on=datetime.date(2026, 12, 9))
    html = page(anyone, "?month=2026-12&topic=AM")
    assert "Admin accounts review" in panel_of(html) and "Job inventory guidance" not in html
    assert re.search(r'href="\?month=2027-01&amp;topic=AM"', html)
    assert "Job inventory guidance" in panel_of(page(anyone, "?month=2026-12&team=Tech+Risk"))
    assert "Nothing matches these filters" in page(anyone, "?month=2026-12&progress=live")


def test_the_list_shows_ten_then_links_to_the_full_page_ten_to_a_page(anyone, make):
    for n in range(11):
        make(title=f"Item {n:02d}")
    panel = panel_of(page(anyone))
    assert panel.count('class="riskcal-work-card ') == 10 and "See all 11" in panel
    second = anyone.get(reverse("riskcal:items") + "?page=2").content.decode()
    assert second.count('class="riskcal-work-card ') == 1 and "Page 2 of 2" in second


def test_live_needs_its_day_and_a_topic_is_needed_without_a_control(anyone, write_calendar):
    write_calendar()
    html = anyone.post(reverse("riskcal:item_new"), form_post(progress="live")).content.decode()
    assert "Add the day it went live." in html and "Pick a topic, or pick a TRAC control." in html
    assert not WorkItem.objects.exists()


def test_picking_a_control_sets_the_topic(anyone, tech_risk, write_calendar, access):
    write_calendar()
    control, _ = published_control(access, As("cora", "tr").user, tech_risk.user)
    anyone.post(reverse("riskcal:item_new"), form_post(control=control.ident))
    version = WorkItem.objects.get().versions.get()
    assert version.control == control.ident and version.topic == access


def test_anyone_can_propose_a_change_and_the_old_date_is_not_listed_on_the_page(anyone, tech_risk, make):
    item = make()
    response = anyone.post(reverse("riskcal:item_edit", args=[item.pk]),
                           form_post(title="Job inventory guidance", topic=item.current().topic.pk, expected_on="2027-01-20",
                                     change_summary="Waiting on the scheduler team"))
    assert response.status_code == 302
    assert "Dec 15, 2026" in panel_of(page(anyone))  # the current item shows until Tech Risk approves
    again = anyone.get(reverse("riskcal:item_edit", args=[item.pk]))
    assert again.status_code == 302  # changes go one at a time
    v.approve_and_publish(item.open_proposal(), tech_risk.user)
    detail = anyone.get(item.get_absolute_url()).content.decode()
    assert "Jan 20, 2027" in detail and "Dec 15, 2026" not in detail
    assert item.versions.count() == 2  # the earlier date stays in the history


def test_both_add_forms_offer_the_choice_between_an_event_and_work_in_progress(anyone, write_calendar):
    write_calendar()
    for name in ("riskcal:new", "riskcal:item_new"):
        html = anyone.get(reverse(name)).content.decode()
        assert "What are you adding?" in html and reverse("riskcal:new") in html and reverse("riskcal:item_new") in html


def test_live_items_order_after_in_progress_and_wanted(make):
    make(title="Live one", progress=ItemStatus.LIVE, went_live_on=datetime.date(2026, 11, 1), runs_passed=0)
    make(title="Wanted one", progress=ItemStatus.WANTED, expected_on=None)
    make(title="Building one")
    assert [i.title for i in work_items.live_items()] == ["Building one", "Wanted one", "Live one"]


CSS_DIR = Path(__file__).resolve().parents[3] / "static" / "css"
CSS = (CSS_DIR / "riskcal.css").read_text()
PAPER = re.search(r"--trac-paper: (#[0-9a-fA-F]{6})", (CSS_DIR / "trac.css").read_text()).group(1).lower()


@pytest.mark.parametrize("prefix", ["AM", "CM", "LA", "VM", "PI", "MO", "DR", "NW", "TP", "DP", "CD"])
def test_each_topic_color_reads_on_its_tint_and_on_paper(prefix):
    rule = re.search(rf"\.riskcal-topic-{prefix} \{{ --tc: (#[0-9a-f]{{6}}); --tc-tint: (#[0-9a-f]{{6}}); \}}", CSS)
    assert rule, f"no color for {prefix}"
    ink, tint = rule.groups()
    assert contrast(ink, tint) >= 4.5 and contrast(ink, PAPER) >= 4.5


def test_operations_and_jobs_is_indigo_never_gold():
    assert ".riskcal-topic-MO { --tc: #46489a;" in CSS
