"""Reading content/calendar/control-dates.csv: the date forms, the header rules and the plain-word message for each bad row."""

import io
from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.riskcal import events_file

HEADER = "control_id,period,due_date,note\n"


@pytest.fixture
def write_dates(write_calendar):
    """Write control-dates.csv (bytes or text) beside a calendar file and return the calendar read from them."""

    def write(content, events="events: []\n", types=None):
        path = write_calendar(events, **({"types": types} if types else {}))
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        events_file.control_dates_path(path).write_bytes(data)
        return events_file.read_calendar(path)

    return write


def test_a_row_becomes_a_control_due_event_with_a_search_link(write_dates):
    calendar = write_dates(HEADER + "MA-04,Q1 2027,2027-03-31,Attach the evidence\n")
    event = calendar.events[0]
    assert calendar.problems == [] and calendar.control_dates == 1
    assert (event.title, event.date, event.end, event.type.key) == ("MA-04 due (Q1 2027)", date(2027, 3, 31), date(2027, 3, 31), "control_due")
    assert event.details == "Attach the evidence" and event.repeats == ""
    assert event.link == reverse("core:search") + "?q=MA-04" and event.on_site


def test_without_a_period_the_title_is_only_the_control_and_the_link_is_encoded(write_dates):
    event = write_dates(HEADER + "  OP 02/b & c ,,2027-03-31,\n").events[0]
    assert event.title == "OP 02/b & c due" and event.details == ""
    assert event.link == "/search/?q=OP+02%2Fb+%26+c"


@pytest.mark.parametrize("text,expected", [
    ("2027-03-31", date(2027, 3, 31)), ("3/31/2027", date(2027, 3, 31)), ("03/05/2027", date(2027, 3, 5)),
    ("1/2/2027", date(2027, 1, 2)), (" 12/31/2027 ", date(2027, 12, 31))])
def test_each_date_form_is_read(write_dates, text, expected):
    calendar = write_dates(HEADER + f"MC-01,,{text},\n")
    assert calendar.problems == [] and calendar.events[0].date == expected


def test_a_byte_order_mark_from_excel_is_handled(write_dates):
    calendar = write_dates(b"\xef\xbb\xbf" + (HEADER + "MC-01,,3/31/2027,\r\nMC-02,,4/30/2027,\r\n").encode())
    assert calendar.problems == [] and [e.title for e in calendar.events] == ["MC-01 due", "MC-02 due"]


def test_header_names_ignore_capitals_spaces_and_order_and_extra_columns_are_ignored(write_dates):
    calendar = write_dates(" Due_Date , Owner,CONTROL_ID ,Note\n2027-03-31,Pat,MA-04,Do it\n")
    event = calendar.events[0]
    assert calendar.problems == [] and event.title == "MA-04 due" and event.details == "Do it"


def test_period_and_note_columns_are_optional(write_dates):
    calendar = write_dates("control_id,due_date\nMA-04,2027-03-31\n")
    assert calendar.problems == [] and calendar.events[0].title == "MA-04 due"


def test_blank_rows_are_skipped_but_still_counted_in_row_numbers(write_dates):
    calendar = write_dates(HEADER + "MC-01,,2027-03-31,\n\n , , ,\n,,,\nMC-02,,nonsense,\n")
    assert len(calendar.events) == 1
    assert calendar.problems == ["control-dates.csv: row 6 (MC-02): the due_date 'nonsense' isn't a real day. Write it as YYYY-MM-DD or M/D/YYYY, for example 2027-03-31."]


@pytest.mark.parametrize("row,expected", [
    (",Q1,2027-03-31,", "control-dates.csv: row 2: needs a control_id, like MA-04."),
    ("MA-04,Q1,,", "row 2 (MA-04): the due_date '' isn't a real day"),
    ("MA-04,Q1,2027-02-30,", "the due_date '2027-02-30' isn't a real day"),
    ("MA-04,Q1,13/1/2027,", "the due_date '13/1/2027' isn't a real day"),
    ("MA-04,Q1,31/03/2027,", "the due_date '31/03/2027' isn't a real day"),
    ("MA-04,Q1,3/31/27,", "the due_date '3/31/27' isn't a real day"),
    ("MA-04", "row 2 (MA-04): the due_date '' isn't a real day"),
])
def test_each_bad_row_is_named_by_its_row_number(write_dates, row, expected):
    calendar = write_dates(HEADER + row + "\n")
    assert calendar.events == [] and any(expected in message for message in calendar.problems), calendar.problems


def test_a_bad_row_leaves_the_good_ones(write_dates):
    calendar = write_dates(HEADER + "MC-01,,2027-03-31,\nMC-02,,soon,\nMC-03,,2027-04-30,\n")
    assert [e.title for e in calendar.events] == ["MC-01 due", "MC-03 due"] and len(calendar.problems) == 1
    assert calendar.problems[0].startswith("control-dates.csv: row 3 (MC-02)")


@pytest.mark.parametrize("header,missing", [("period,due_date,note\n", "control_id"), ("control_id,period,note\n", "due_date"), ("a,b\n", "control_id, due_date")])
def test_missing_columns_are_named(write_dates, header, missing):
    calendar = write_dates(header + "MA-04,Q1,2027-03-31\n")
    assert calendar.events == []
    assert calendar.problems == [f"control-dates.csv: the first row must name the columns control_id, period, due_date and note. Missing: {missing}."]


def test_an_empty_file_is_reported_as_missing_columns(write_dates):
    assert "Missing: control_id, due_date" in write_dates("").problems[0]


def test_a_file_that_is_not_utf8_gets_a_plain_message(write_dates):
    calendar = write_dates(HEADER.encode() + b"MA-04,Caf\xe9,2027-03-31,\n")
    assert calendar.events == [] and calendar.problems == ["control-dates.csv: the file isn't UTF-8 text. In Excel, use Save As and choose \"CSV UTF-8\"."]


def test_a_missing_control_due_type_is_reported_once(write_dates):
    calendar = write_dates(HEADER + "MA-04,,2027-03-31,\nMC-01,,2027-04-30,\n", types="types:\n  - key: meeting\n    label: Meeting\n")
    assert calendar.events == []
    assert calendar.problems == ["control-dates.csv: its rows are shown as the 'control_due' event type, but that type is missing from the types list in events.yaml. Add it there."]


def test_no_file_changes_nothing(write_calendar):
    calendar = events_file.read_calendar(write_calendar("events:\n  - {title: Kickoff, date: 2027-02-01, type: meeting}\n"))
    assert calendar.problems == [] and calendar.control_dates == 0 and len(calendar.events) == 1


def test_csv_events_are_numbered_after_the_yaml_ones_so_their_pop_ups_never_clash(write_dates):
    calendar = write_dates(HEADER + "MA-04,,2027-02-01,\nMC-01,,2027-02-01,\n", events="events:\n  - {title: Kickoff, date: 2027-02-01, type: meeting}\n")
    assert [e.number for e in calendar.events] == [1, 3, 4]


@pytest.mark.django_db
def test_check_calendar_counts_both_sources_and_names_csv_rows(write_dates):
    write_dates(HEADER + "MA-04,,2027-02-01,\nMC-01,,2027-02-02,\n", events="events:\n  - {title: Kickoff, date: 2027-02-01, type: meeting}\n")
    out = io.StringIO()
    call_command("check_calendar", stdout=out)
    assert "All good: 1 event(s), 2 control due date(s) and 2 event type(s)." in out.getvalue()
    write_dates(HEADER + "MA-04,,2027-02-01,\nMC-01,,never,\n")
    with pytest.raises(CommandError, match=r"control-dates.csv: row 3 \(MC-01\)"):
        call_command("check_calendar", stdout=io.StringIO())


@pytest.mark.django_db
def test_check_calendar_flags_banned_wording_in_the_csv(write_dates):
    write_dates(HEADER + "MA-04,,2027-02-01,Reach out to owners\n")
    with pytest.raises(CommandError, match="control-dates.csv.*reach out"):
        call_command("check_calendar", stdout=io.StringIO())


@pytest.mark.django_db
def test_thirty_controls_due_on_one_day_stay_readable(client, today, write_dates):
    rows = "".join(f"MA-{n:02d},Q4 2026,11/20/2026,\n" for n in range(1, 31))
    write_dates(HEADER + rows)
    html = client.get(reverse("riskcal:index")).content.decode()
    assert html.count('class="riskcal-event ') == 3 and "+27 more" in html
    day_list = html.split('<template id="riskcal-day-2026-11-20"')[1].split("</template>")[0]
    assert day_list.count("<li ") == 30 and 'data-riskcal-from="day-2026-11-20"' in day_list and "MA-30 due (Q4 2026)" in day_list
    month_list = html.split("This month")[1].split("<template")[0]
    assert month_list.count("<li ") == 30 and month_list.count("Nov 20, 2026") == 30
    assert html.count('<template id="riskcal-e') == 30
    assert 'href="/search/?q=MA-30"' in html
