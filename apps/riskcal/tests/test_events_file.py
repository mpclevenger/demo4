"""Reading content/calendar/events.yaml: what is accepted and the plain-word message for each mistake."""

from datetime import date

import pytest

from apps.riskcal import events_file, schedule


def messages(write_calendar, events):
    return events_file.read_calendar(write_calendar(events)).problems


def test_the_shipped_file_reads_without_problems():
    calendar = events_file.read_calendar(events_file.FILE)
    assert calendar.problems == []
    assert [t.key for t in calendar.types][:2] == ["control_due", "evidence_due"]


def test_the_shipped_working_group_meets_on_the_second_thursday():
    events = events_file.read_calendar(events_file.FILE).events
    found = schedule.occurrences_between(events, date(2026, 12, 1), date(2027, 2, 28))
    assert [(o.event.title, o.start) for o in found] == [
        ("SOX working group", date(2026, 12, 3)), ("SOX working group", date(2027, 1, 14)), ("SOX working group", date(2027, 2, 11))]


def test_a_full_event_is_read(write_calendar):
    calendar = events_file.read_calendar(write_calendar("""\
    events:
      - title: Access review
        date: 2027-01-15
        end: "2027-01-31"
        type: control_due
        details: See [the guides](/guides/).
        link: https://example.com/page
        repeats: Quarterly
        until: 2028-12-31
    """))
    event = calendar.events[0]
    assert calendar.problems == []
    assert (event.title, event.date, event.end, event.type.label) == ("Access review", date(2027, 1, 15), date(2027, 1, 31), "Control due")
    assert (event.repeats, event.until, event.on_site) == ("quarterly", date(2028, 12, 31), False)


def test_an_event_with_only_the_needed_lines_lasts_one_day(write_calendar):
    event = events_file.read_calendar(write_calendar("""\
    events:
      - {title: Kickoff, date: 2027-02-01, type: meeting, link: /guides/}
    """)).events[0]
    assert event.end == event.date and event.on_site is True


def test_no_events_line_content_is_fine(write_calendar):
    assert events_file.read_calendar(write_calendar("events:\n")).problems == []


@pytest.mark.parametrize("text,expected", [
    ("- {date: 2027-01-01, type: meeting}", 'events.yaml: event 1: needs a title.'),
    ("- {title: Kickoff, type: meeting}", 'events.yaml: "Kickoff": needs a date, written YYYY-MM-DD.'),
    ("- {title: Kickoff, date: 2027-02-30, type: meeting}", "\"Kickoff\": the date '2027-02-30' isn't a real day. Write it as YYYY-MM-DD"),
    ("- {title: Kickoff, date: 1/2/2027, type: meeting}", "the date '1/2/2027' isn't a real day"),
    ("- {title: Kickoff, date: 2027-02-01, end: soon, type: meeting}", "the end 'soon' isn't a real day"),
    ("- {title: Kickoff, date: 2027-02-10, end: 2027-02-01, type: meeting}", '"Kickoff": the end date is before the date.'),
    ("- {title: Kickoff, date: 2027-02-01}", "\"Kickoff\": the type '' isn't in the types list. Use one of: control_due, meeting."),
    ("- {title: Kickoff, date: 2027-02-01, type: party}", "the type 'party' isn't in the types list"),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, colour: red}", "'colour' isn't a known line. Use: title, date, end, type, details, link, repeats, on, until."),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, link: guides}", "the link must be a TRAC page starting with / (like /guides/) or an https:// address."),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, link: http://example.com}", "the link must be a TRAC page"),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, link: '//example.com'}", "the link must be a TRAC page"),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, link: '/\\example.com'}", "the link must be a TRAC page"),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, repeats: weekly}", "'repeats' must be monthly, quarterly or annual."),
    ("- {title: Kickoff, date: 2027-02-01, type: meeting, until: 2027-12-31}", "'until' only makes sense together with 'repeats'."),
    ("- {title: Kickoff, date: 2027-02-10, type: meeting, repeats: monthly, until: 2027-02-01}", '"Kickoff": the until date is before the date.'),
    ("- just some words", "events.yaml: event 1: needs a title."),
])
def test_each_mistake_gets_a_plain_message_naming_the_event(write_calendar, text, expected):
    found = messages(write_calendar, f"events:\n  {text}\n")
    assert any(expected in message for message in found), found


def test_a_mistake_in_one_event_leaves_the_others(write_calendar):
    calendar = events_file.read_calendar(write_calendar("""\
    events:
      - {title: Good, date: 2027-02-01, type: meeting}
      - {title: Bad, date: nonsense, type: meeting}
    """))
    assert [e.title for e in calendar.events] == ["Good"] and len(calendar.problems) == 1


def test_the_event_number_is_its_place_in_the_file(write_calendar):
    calendar = events_file.read_calendar(write_calendar("""\
    events:
      - {title: One, date: 2027-02-01, type: meeting}
      - {title: Two, date: 2027-02-02, type: meeting}
    """))
    assert [e.number for e in calendar.events] == [1, 2]


def test_every_mistake_is_listed_not_only_the_first(write_calendar):
    found = messages(write_calendar, "events:\n  - {title: Bad, date: nonsense, type: party, link: nope}\n")
    assert len(found) == 3


@pytest.mark.parametrize("types,expected", [
    ("types: []\n", "'types' needs a list"),
    ("types:\n  - {key: Bad Key, label: Oops}\n", "type 1 needs a 'key'"),
    ("types:\n  - {key: a, label: A}\n  - {key: a, label: B}\n", "the type key 'a' is used twice."),
    ("types:\n" + "".join(f"  - {{key: t{n}, label: T{n}}}\n" for n in range(9)), "there are 9 event types"),
])
def test_type_list_mistakes(write_calendar, types, expected):
    found = events_file.read_calendar(write_calendar(types=types)).problems
    assert any(expected in message for message in found), found


def test_a_file_with_the_wrong_shape_or_broken_yaml_is_explained(write_calendar, tmp_path):
    path = write_calendar(types="just: words\n")
    assert "expected two lists, 'types' and 'events'" in events_file.read_calendar(path).problems[0]
    path.write_text("types: [unclosed\n", encoding="utf-8")
    assert "isn't valid YAML" in events_file.read_calendar(path).problems[0]
    assert "can't be read" in events_file.read_calendar(tmp_path / "missing.yaml").problems[0]


def test_an_unknown_top_level_key_is_reported(write_calendar):
    path = write_calendar(types=events_file_types() + "extras: []\n")
    assert any("'extras' isn't a known part" in p for p in events_file.read_calendar(path).problems)


def events_file_types():
    from .conftest import TYPES

    return TYPES


WEEKDAY_EVENT = "events:\n  - {{title: Meeting, date: {day}, type: meeting, repeats: {repeats}, on: {on}}}\n"


@pytest.mark.parametrize("on,day", [
    ("second thursday", "2027-01-14"), ("Second Thursday", "2027-01-14"), ("  LAST   friday ", "2027-01-29"),
    ("first monday", "2027-01-04"), ("third wednesday", "2027-01-20"), ("fourth sunday", "2027-01-24")])
def test_each_form_of_on_is_read(write_calendar, on, day):
    calendar = events_file.read_calendar(write_calendar(WEEKDAY_EVENT.format(day=day, repeats="monthly", on=f'"{on}"')))
    assert calendar.problems == []
    assert calendar.events[0].on == " ".join(on.lower().split())


def test_the_line_named_on_is_not_mistaken_for_yes(write_calendar):
    calendar = events_file.read_calendar(write_calendar("events:\n  - {title: No, date: 2027-01-14, type: meeting, repeats: monthly, on: second thursday}\n"))
    assert calendar.problems == [] and calendar.events[0].title == "No"


@pytest.mark.parametrize("on", ["thursday", "fifth thursday", "second thurs", "every thursday", "second thursday of the month"])
def test_a_bad_on_is_explained(write_calendar, on):
    found = messages(write_calendar, WEEKDAY_EVENT.format(day="2027-01-14", repeats="monthly", on=f'"{on}"'))
    assert len(found) == 1 and '"Meeting": \'on\' must be a place and a weekday, like \'second thursday\'' in found[0]


def test_on_needs_a_monthly_repeat(write_calendar):
    for repeats in ("quarterly", "''"):
        found = messages(write_calendar, WEEKDAY_EVENT.format(day="2027-01-14", repeats=repeats, on="second thursday"))
        assert found == ["events.yaml: \"Meeting\": 'on' only works together with 'repeats: monthly'."]


def test_the_date_must_be_the_weekday_the_rule_names(write_calendar):
    found = messages(write_calendar, WEEKDAY_EVENT.format(day="2027-01-15", repeats="monthly", on="second thursday"))
    assert found == ['events.yaml: "Meeting": the date 2027-01-15 is not the second thursday of its month. '
                     "Change the date to 2027-01-14 (the first time it happens), or change 'on'."]
