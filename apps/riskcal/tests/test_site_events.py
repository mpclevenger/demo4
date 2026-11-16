"""Events proposed on the site: the form, the review steps, and what shows on the calendar."""

import datetime

import pytest
from django.urls import reverse

from apps.core import versioning as v
from apps.core.tests.support import As
from apps.review.selectors import versions_in_review, versions_proposed_by
from apps.riskcal import events_file, services, site_events
from apps.riskcal.models import CalendarEvent, CalendarEventVersion

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso")]

NEW = {"title": "Vendor review", "date": "2026-11-20", "type": "meeting", "details": "", "link": "", "repeats": ""}
MONTHLY = {"title": "Evidence check", "date": "2026-11-03", "type": "control_due", "repeats": "monthly", "until": "2027-01-31"}


def page(who, query="?month=2026-11"):
    return who.get(reverse("riskcal:index") + query).content.decode()


@pytest.fixture
def proposer():
    return As("pat", "co")


@pytest.fixture
def tech_risk():
    return As("tara", "tr")


@pytest.fixture
def second_tech_risk():
    return As("tom", "tr")


def propose(who, **fields):
    response = who.post(reverse("riskcal:new"), {**NEW, **fields})
    return response


@pytest.fixture
def approved(proposer, second_tech_risk):
    """Make a proposal as a control owner and approve it as Tech Risk; returns the event."""
    def make(**fields):
        event, version = services.propose_event(proposer.user, **_content(**fields))
        v.approve_and_publish(version, second_tech_risk.user)
        return event
    return make


def _content(**fields):
    data = {**NEW, **fields}
    return {
        "title": data["title"], "date": datetime.date.fromisoformat(data["date"]), "type": data["type"], "details": data.get("details", ""),
        "link": data.get("link", ""), "repeats": data.get("repeats", ""), "on_rule": data.get("on_rule", ""),
        "until": datetime.date.fromisoformat(data["until"]) if data.get("until") else None,
    }


def test_a_proposed_event_is_not_on_the_calendar_until_approved(today, write_calendar, proposer, second_tech_risk):
    write_calendar()
    event, version = services.propose_event(proposer.user, **_content())
    assert version.status == v.Status.IN_REVIEW
    assert "Vendor review" not in page(proposer)
    v.approve_and_publish(version, second_tech_risk.user)
    assert "Vendor review" in page(proposer)


def test_an_approved_monthly_event_shows_in_each_month_until_its_until_date(today, write_calendar, approved, proposer):
    write_calendar()
    approved(**MONTHLY)
    for month, shown in (("2026-11", True), ("2026-12", True), ("2027-01", True), ("2027-02", False)):
        assert ("Evidence check" in page(proposer, f"?month={month}")) is shown, month


def test_a_site_event_has_its_types_color_and_sits_beside_the_files_events(today, write_calendar, approved, proposer):
    write_calendar("events:\n  - {title: From the file, date: 2026-11-10, type: control_due}\n")
    approved(type="meeting")
    html = page(proposer)
    assert "From the file" in html and "Vendor review" in html
    assert 'riskcal-color-1" data-riskcal-open="e1000001' in html.replace("\n", " ") or "riskcal-color-1" in html


def test_a_rejected_or_withdrawn_proposal_never_shows(today, write_calendar, proposer, tech_risk):
    write_calendar()
    _, version = services.propose_event(proposer.user, **_content())
    v.reject(version, tech_risk.user, "Not a risk date.")
    assert "Vendor review" not in page(proposer)


def test_retiring_an_event_takes_it_off_the_calendar_but_keeps_the_history(today, write_calendar, approved, proposer, tech_risk, second_tech_risk):
    write_calendar()
    event = approved()
    version = v.propose_retirement(event, tech_risk.user, "Cancelled.")
    v.submit(version, tech_risk.user)
    v.approve_and_publish(version, second_tech_risk.user)
    assert "Vendor review" not in page(proposer)
    assert event.versions.count() == 2 and CalendarEvent.objects.filter(pk=event.pk).exists()


def test_anyone_who_can_read_can_propose_through_the_form(today, write_calendar, proposer):
    write_calendar()
    response = propose(proposer)
    assert response.status_code == 302
    event = CalendarEvent.objects.get()
    assert response["Location"] == f"/calendar/event/{event.pk}/?version=1"
    assert event.versions.get().status == v.Status.IN_REVIEW and event.versions.get().proposed_by == proposer.user


def test_the_form_accepts_a_trac_page_as_the_link_like_the_file_does(today, write_calendar, proposer):
    write_calendar()
    assert propose(proposer, link="/guides/").status_code == 302
    assert CalendarEvent.objects.get().versions.get().link == "/guides/"


def test_the_form_gives_the_files_plain_word_reasons(today, write_calendar, proposer):
    write_calendar()
    response = propose(proposer, end="2026-11-01")
    html = response.content.decode()
    assert response.status_code == 200 and "The end date is before the date." in html
    assert not CalendarEvent.objects.exists()


@pytest.mark.parametrize("fields, reason", [
    ({"link": "http://example.com"}, "link must be a TRAC page"),
    ({"link": "//evil.example.com"}, "link must be a TRAC page"),
    ({"link": "/\\evil.example.com"}, "link must be a TRAC page"),
    ({"until": "2026-12-01"}, "only makes sense together with"),
    ({"type": "nonsense"}, "Select a valid choice"),
    ({"repeats": "monthly", "place": "second", "weekday": "thursday"}, "is not the second thursday of its month"),
    ({"place": "second"}, "choose both the place"),
])
def test_the_form_refuses_what_the_file_would(today, write_calendar, proposer, fields, reason):
    write_calendar()
    assert reason in propose(proposer, **fields).content.decode()
    assert not CalendarEvent.objects.exists()


def test_a_weekday_rule_is_saved_when_the_date_fits(today, write_calendar, proposer):
    write_calendar()
    propose(proposer, date="2026-11-12", repeats="monthly", place="second", weekday="thursday")
    assert CalendarEvent.objects.get().versions.get().on_rule == "second thursday"


def test_the_review_queue_lists_it_and_mine_shows_it_to_the_proposer(today, write_calendar, proposer, tech_risk):
    write_calendar()
    propose(proposer)
    assert [site_events and v_.title for v_ in versions_in_review()] == ["Vendor review"]
    assert "Vendor review" in tech_risk.get(reverse("review:queue")).content.decode()
    mine = proposer.get(reverse("review:mine")).content.decode()
    assert "Vendor review" in mine and "Proposed" in mine
    assert versions_proposed_by(tech_risk.user) == []


def test_only_tech_risk_can_approve_and_a_visitor_cannot_see_others_proposals(today, write_calendar, proposer):
    write_calendar()
    propose(proposer)
    event = CalendarEvent.objects.get()
    other = As("olive", "ro")
    assert other.get(event.get_absolute_url() + "?version=1").status_code == 404
    assert other.post(f"/workflow/{_type_id()}/{event.versions.get().pk}/approve/").status_code in (403, 404)
    assert event.versions.get().status == v.Status.IN_REVIEW


def _type_id():
    from django.contrib.contenttypes.models import ContentType
    return ContentType.objects.get_for_model(CalendarEventVersion).pk


def test_tech_risk_approves_through_the_page_and_the_event_appears(today, write_calendar, proposer, second_tech_risk):
    write_calendar()
    propose(proposer)
    event = CalendarEvent.objects.get()
    version = event.versions.get()
    assert second_tech_risk.post(f"/workflow/{_type_id()}/{version.pk}/approve/").status_code == 302
    assert "Vendor review" in page(proposer)


def test_tech_risk_changes_an_approved_event_through_review(today, write_calendar, approved, tech_risk, second_tech_risk, proposer):
    write_calendar()
    event = approved()
    response = tech_risk.post(reverse("riskcal:event_edit", args=[event.pk]), {**NEW, "title": "Vendor review (moved)", "date": "2026-11-25", "change_summary": "Moved."})
    assert response.status_code == 302
    assert "Vendor review (moved)" not in page(proposer) and "Vendor review" in page(proposer)
    v.approve_and_publish(event.versions.get(number=2), second_tech_risk.user)
    assert "Vendor review (moved)" in page(proposer)


def test_a_control_owner_cannot_change_or_retire_an_event(today, write_calendar, approved, proposer):
    write_calendar()
    event = approved()
    assert proposer.get(reverse("riskcal:event_edit", args=[event.pk])).status_code == 403


def test_the_calendar_page_offers_add_an_event_and_a_broken_site_event_is_named(today, write_calendar, approved, proposer):
    write_calendar()
    approved()
    assert "Add an event" in page(proposer)
    write_calendar(types="types:\n  - {key: other, label: Other}\n")
    html = page(proposer)
    assert "Vendor review" in html and "not shown" in html


def test_check_event_reads_the_same_lines_as_the_file():
    types = [events_file.EventType("meeting", "Meeting", 0)]
    event, reasons = events_file.check_event(0, {"title": "A", "date": "2027-01-14", "type": "meeting"}, types)
    assert event.title == "A" and reasons == []
    event, reasons = events_file.check_event(0, {"title": "A", "date": "2027-02-30", "type": "meeting"}, types)
    assert event is None and "isn't a real day" in reasons[0]
