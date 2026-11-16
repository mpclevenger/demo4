"""The calendar page: the grid, the pop-up data, the filter, the HTMX piece and who can open it."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.core.tests.support import As

pytestmark = pytest.mark.django_db

EVENTS = """\
events:
  - {title: Access review, date: 2026-11-10, type: control_due, details: "Read [the guides](/guides/) <b>now</b>", link: /guides/}
  - {title: Vendor call, date: 2026-11-10, end: 2026-11-12, type: meeting, link: "https://example.com/x"}
  - {title: Evidence <script>alert(1)</script>, date: 2026-11-03, type: control_due, repeats: monthly, until: 2027-01-31}
"""


def get(client, query="", **headers):
    return client.get(reverse("riskcal:index") + query, **headers).content.decode()


def test_the_address_is_calendar(client, today):
    assert reverse("riskcal:index") == "/calendar/"
    assert client.get("/calendar/").status_code == 200


def test_the_empty_shipped_style_file_shows_a_friendly_note(client, today, write_calendar):
    write_calendar()
    html = get(client)
    assert "<h1" in html and "Risk and control calendar" in html
    assert "No events yet" in html and "November 2026" in html


def test_the_grid_is_a_table_with_sunday_first_and_today_marked(client, today, write_calendar):
    write_calendar()
    html = get(client)
    assert html.count('<th scope="col">') == 7 and html.index(">Sun<") < html.index(">Sat<")
    assert html.count("<tr>") == 6  # header plus five weeks
    assert html.count('aria-current="date"') == 1 and 'riskcal-today' in html
    assert html.count("riskcal-outside") == 5  # Dec 1 to 5 fill the last week; Nov 1 is a Sunday


def test_the_month_comes_from_the_address_and_bad_months_fall_back(client, today, write_calendar):
    write_calendar()
    assert "December 2026" in get(client, "?month=2026-12")
    assert "November 2026" in get(client, "?month=junk")
    assert "November 2024" in get(client, "?month=1990-01")
    assert "November 2031" in get(client, "?month=2100-01")


def test_events_appear_in_cells_the_list_and_popup_data(client, today, write_calendar):
    write_calendar(EVENTS)
    html = get(client)
    assert html.count('class="riskcal-event ') == 5  # review, vendor call over three days, evidence
    assert 'data-riskcal-open="e1-20261110"' in html and '<template id="riskcal-e1-20261110" data-title="Access review">' in html
    assert "Nov 10 to Nov 12, 2026" in html and "Control due" in html and "Meeting" in html
    assert "Repeats every month, until Jan 31, 2027" in html
    assert '<a href="/guides/">the guides</a>' in html
    assert 'href="/guides/">Go to the page<' in html
    assert 'href="https://example.com/x" rel="noopener">Open the link<' in html


def test_everything_from_the_file_is_escaped(client, today, write_calendar):
    write_calendar(EVENTS)
    html = get(client)
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html
    assert "<b>now</b>" not in html and "&lt;b&gt;now&lt;/b&gt;" in html


def test_a_day_with_four_events_shows_three_and_plus_one_more(client, today, write_calendar):
    write_calendar("events:\n" + "".join(f"  - {{title: Item {n}, date: 2026-11-20, type: meeting}}\n" for n in range(1, 5)))
    html = get(client)
    assert html.count('class="riskcal-event ') == 3
    assert "+1 more" in html and 'data-riskcal-open="day-2026-11-20"' in html
    assert '<template id="riskcal-day-2026-11-20" data-title="Friday, November 20, 2026">' in html
    assert html.count('data-riskcal-from="day-2026-11-20"') == 4


def test_a_quiet_day_has_no_more_button(client, today, write_calendar):
    write_calendar(EVENTS)
    assert "more</button>" not in get(client)


def test_the_type_filter_keeps_the_month_and_works_from_the_address(client, today, write_calendar):
    write_calendar(EVENTS)
    html = get(client, "?month=2026-12&type=meeting")
    assert "Vendor call" not in html  # a November span does not reach December
    assert "Evidence" in get(client, "?type=control_due") and "Vendor call" not in get(client, "?type=control_due")
    assert "Access review" not in get(client, "?type=meeting")
    chips = get(client, "?month=2026-12&type=meeting")
    assert 'href="?month=2026-12"' in chips and "Previous" in chips
    assert 'href="?type=meeting"' in chips and 'href="?month=2027-01&amp;type=meeting"' in chips


def test_a_filtered_empty_month_says_so(client, today, write_calendar):
    write_calendar(EVENTS)
    assert "No events of the chosen types this month" in get(client, "?type=meeting&month=2026-12")
    assert "No events this month" in get(client, "?month=2027-02")  # the repeat ended on January 31
    assert "Evidence" in get(client, "?month=2027-01")


def test_the_htmx_request_gets_only_the_month_and_the_full_page_gets_everything(client, today, write_calendar):
    write_calendar(EVENTS)
    full, part = get(client), get(client, "?month=2026-12", HTTP_HX_REQUEST="true")
    assert "<html" in full and 'id="riskcal-modal"' in full and 'id="riskcal"' in full
    assert "<html" not in part and "December 2026" in part and "riskcal-modal" not in part
    assert 'hx-get="?month=2027-01"' in part and 'hx-push-url="true"' in part and 'hx-target="#riskcal"' in part
    assert 'href="?month=2027-01"' in part  # plain links work without JavaScript


def test_the_page_loads_its_own_styles_and_script_only(client, today, write_calendar):
    write_calendar()
    html = get(client)
    assert "css/riskcal.css" in html and "js/riskcal.js" in html
    assert "css/riskcal.css" not in client.get("/guides/").content.decode()


def test_a_broken_file_still_opens_and_says_what_is_wrong(client, today, write_calendar):
    write_calendar("events:\n  - {title: Bad, date: nonsense, type: meeting}\n  - {title: Good, date: 2026-11-04, type: meeting}\n")
    html = get(client)
    assert "Some of the calendar file could not be read" in html and "&quot;Bad&quot;: the date" in html
    assert "Good" in html


@pytest.mark.parametrize("group", ["tr", "co", "aud", "ro"])
def test_every_role_can_open_the_calendar(sso, group, today):
    assert As(f"user-{group}", group).get("/calendar/").status_code == 200


def test_a_signed_out_visitor_is_turned_away_when_sso_is_on(sso, today):
    from apps.core.tests.support import anonymous

    assert anonymous().get("/calendar/").status_code == 403


def test_check_calendar_passes_for_a_good_file_and_names_each_problem(write_calendar):
    write_calendar(EVENTS)
    out = io.StringIO()
    call_command("check_calendar", stdout=out)
    assert "All good: 3 event(s), 0 control due date(s) and 2 event type(s)." in out.getvalue()
    write_calendar("events:\n  - {title: Bad, date: 2026-02-30, type: party}\n")
    with pytest.raises(CommandError) as error:
        call_command("check_calendar", stdout=io.StringIO())
    assert '"Bad": the date' in str(error.value) and "the type 'party'" in str(error.value)


def test_check_calendar_flags_banned_wording(write_calendar):
    write_calendar("events:\n  - {title: Reach out to owners, date: 2026-11-04, type: meeting}\n")
    with pytest.raises(CommandError, match="reach out"):
        call_command("check_calendar", stdout=io.StringIO())


def test_check_content_runs_the_calendar_check(write_calendar):
    write_calendar("events:\n  - {title: Bad, date: nonsense, type: meeting}\n")
    out = io.StringIO()
    with pytest.raises(CommandError):
        call_command("check_content", stdout=out, stderr=io.StringIO())
    assert "Risk and control calendar (content/calendar)" in out.getvalue() and '"Bad"' in out.getvalue()
