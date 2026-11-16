"""Repeats, events that last several days, and the words for dates."""

from datetime import date

from apps.riskcal import schedule
from apps.riskcal.events_file import Event, EventType

KIND = EventType("meeting", "Meeting", 0)


def event(start, end=None, repeats="", until=None, number=1, on=""):
    return Event(number, "E", start, end or start, KIND, repeats=repeats, until=until, on=on)


def starts(item, first, last):
    return [o.start for o in schedule.occurrences_between([item], first, last)]


def test_a_single_event_shows_only_in_its_month():
    item = event(date(2027, 3, 10))
    assert starts(item, date(2027, 3, 1), date(2027, 3, 31)) == [date(2027, 3, 10)]
    assert starts(item, date(2027, 4, 1), date(2027, 4, 30)) == []


def test_monthly_repeats_start_at_the_first_date_not_before():
    item = event(date(2027, 3, 10), repeats="monthly")
    assert starts(item, date(2027, 2, 1), date(2027, 2, 28)) == []
    assert starts(item, date(2027, 3, 1), date(2027, 5, 31)) == [date(2027, 3, 10), date(2027, 4, 10), date(2027, 5, 10)]


def test_quarterly_repeats_every_three_months():
    item = event(date(2027, 1, 15), repeats="quarterly")
    assert starts(item, date(2027, 1, 1), date(2027, 12, 31)) == [date(2027, 1, 15), date(2027, 4, 15), date(2027, 7, 15), date(2027, 10, 15)]
    assert starts(item, date(2027, 2, 1), date(2027, 3, 31)) == []


def test_annual_repeats_once_a_year_far_into_the_future():
    item = event(date(2026, 6, 30), repeats="annual")
    assert starts(item, date(2031, 6, 1), date(2031, 6, 30)) == [date(2031, 6, 30)]
    assert starts(item, date(2031, 7, 1), date(2031, 7, 31)) == []


def test_the_31st_falls_on_the_last_day_of_a_shorter_month():
    item = event(date(2027, 1, 31), repeats="monthly")
    assert starts(item, date(2027, 2, 1), date(2027, 2, 28)) == [date(2027, 2, 28)]
    assert starts(item, date(2028, 2, 1), date(2028, 2, 29)) == [date(2028, 2, 29)]
    assert starts(item, date(2027, 4, 1), date(2027, 4, 30)) == [date(2027, 4, 30)]
    assert starts(item, date(2027, 3, 1), date(2027, 3, 31)) == [date(2027, 3, 31)]


def test_february_29_repeats_annually_on_the_28th_in_other_years():
    item = event(date(2028, 2, 29), repeats="annual")
    assert starts(item, date(2029, 2, 1), date(2029, 2, 28)) == [date(2029, 2, 28)]
    assert starts(item, date(2032, 2, 1), date(2032, 2, 29)) == [date(2032, 2, 29)]


def test_until_is_the_last_day_a_repeat_can_start():
    item = event(date(2027, 1, 10), repeats="monthly", until=date(2027, 3, 10))
    assert starts(item, date(2027, 1, 1), date(2027, 12, 31)) == [date(2027, 1, 10), date(2027, 2, 10), date(2027, 3, 10)]


def test_a_span_is_found_in_every_month_it_touches():
    item = event(date(2027, 1, 28), end=date(2027, 3, 3))
    for month_first, month_last in [(date(2027, 1, 1), date(2027, 1, 31)), (date(2027, 2, 1), date(2027, 2, 28)), (date(2027, 3, 1), date(2027, 3, 31))]:
        found = schedule.occurrences_between([item], month_first, month_last)
        assert [(o.start, o.end) for o in found] == [(date(2027, 1, 28), date(2027, 3, 3))]
    assert starts(item, date(2027, 4, 1), date(2027, 4, 30)) == []


def test_a_repeating_span_that_started_last_month_still_shows():
    item = event(date(2027, 1, 30), end=date(2027, 2, 2), repeats="monthly")
    found = schedule.occurrences_between([item], date(2027, 3, 1), date(2027, 3, 31))
    assert [(o.start, o.end) for o in found] == [(date(2027, 2, 28), date(2027, 3, 3)), (date(2027, 3, 30), date(2027, 4, 2))]


def test_happenings_are_in_date_order_then_file_order():
    late, early_b, early_a = event(date(2027, 3, 20), number=1), event(date(2027, 3, 2), number=3), event(date(2027, 3, 2), number=2)
    found = schedule.occurrences_between([late, early_b, early_a], date(2027, 3, 1), date(2027, 3, 31))
    assert [o.event.number for o in found] == [2, 3, 1]


def test_dates_are_described_in_words():
    assert schedule.describe_days(date(2027, 3, 5), date(2027, 3, 5)) == "Mar 5, 2027"
    assert schedule.describe_days(date(2027, 3, 5), date(2027, 4, 2)) == "Mar 5 to Apr 2, 2027"
    assert schedule.describe_days(date(2026, 12, 30), date(2027, 1, 2)) == "Dec 30, 2026 to Jan 2, 2027"


def test_repeat_notes():
    assert schedule.repeat_note(event(date(2027, 1, 1))) == ""
    assert schedule.repeat_note(event(date(2027, 1, 1), repeats="quarterly")) == "Repeats every three months"
    assert schedule.repeat_note(event(date(2027, 1, 1), repeats="annual", until=date(2030, 1, 1))) == "Repeats every year, until Jan 1, 2030"


def test_the_second_thursday_of_each_month():
    item = event(date(2027, 1, 14), repeats="monthly", on="second thursday")
    assert starts(item, date(2026, 12, 1), date(2027, 4, 30)) == [date(2027, 1, 14), date(2027, 2, 11), date(2027, 3, 11), date(2027, 4, 8)]


def test_a_month_with_five_thursdays_has_a_fourth_and_a_last_that_differ():
    # May 2025 has five Thursdays: 1, 8, 15, 22, 29.
    first = event(date(2025, 5, 1), repeats="monthly", on="first thursday")
    fourth = event(date(2025, 5, 22), repeats="monthly", on="fourth thursday")
    last = event(date(2025, 5, 29), repeats="monthly", on="last thursday")
    for item, expected in [(first, date(2025, 5, 1)), (fourth, date(2025, 5, 22)), (last, date(2025, 5, 29))]:
        assert starts(item, date(2025, 5, 1), date(2025, 5, 31)) == [expected]
    assert starts(last, date(2025, 6, 1), date(2025, 6, 30)) == [date(2025, 6, 26)]


def test_last_is_right_when_the_month_ends_on_that_weekday():
    assert schedule.nth_weekday(2027, 1, "last sunday") == date(2027, 1, 31)
    assert schedule.nth_weekday(2027, 2, "last sunday") == date(2027, 2, 28)
    assert schedule.nth_weekday(2027, 2, "first monday") == date(2027, 2, 1)


def test_a_weekday_repeat_follows_until_and_a_far_future_month():
    item = event(date(2027, 1, 14), repeats="monthly", on="second thursday", until=date(2027, 2, 11))
    assert starts(item, date(2027, 1, 1), date(2027, 12, 31)) == [date(2027, 1, 14), date(2027, 2, 11)]
    forever = event(date(2027, 1, 14), repeats="monthly", on="second thursday")
    assert starts(forever, date(2031, 6, 1), date(2031, 6, 30)) == [date(2031, 6, 12)]


def test_the_weekday_repeat_note():
    item = event(date(2027, 1, 14), repeats="monthly", on="second thursday")
    assert schedule.repeat_note(item) == "Repeats on the second Thursday of each month"
    until = event(date(2027, 1, 14), repeats="monthly", on="last friday", until=date(2028, 1, 1))
    assert schedule.repeat_note(until) == "Repeats on the last Friday of each month, until Jan 1, 2028"
