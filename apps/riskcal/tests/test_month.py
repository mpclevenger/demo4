"""The month parameter, the type filter, the grid shape and the "+N more" rule."""

from datetime import date

import pytest

from apps.riskcal import events_file, month

TODAY = date(2026, 11, 15)


def types(*keys):
    return [events_file.EventType(key, key.title(), n) for n, key in enumerate(keys)]


def cal_with(*days, kind="meeting", repeats=""):
    kinds = types("meeting", "deadline")
    chosen = next(t for t in kinds if t.key == kind)
    events = [events_file.Event(n, f"E{n}", d, d, chosen, repeats=repeats) for n, d in enumerate(days, start=1)]
    return events_file.Calendar(types=kinds, events=events)


@pytest.mark.parametrize("text,expected", [
    ("2027-03", (2027, 3)),
    (None, (2026, 11)),
    ("", (2026, 11)),
    ("banana", (2026, 11)),
    ("2027-13", (2026, 11)),
    ("2027-00", (2026, 11)),
    ("0000-05", (2026, 11)),
    ("2027-3", (2026, 11)),
    ("2024-11", (2024, 11)),
    ("2024-10", (2024, 11)),
    ("1999-01", (2024, 11)),
    ("2031-11", (2031, 11)),
    ("2031-12", (2031, 11)),
    ("9999-12", (2031, 11)),
])
def test_the_month_is_this_month_unless_valid_and_is_kept_within_the_range(text, expected):
    assert month.parse_month(text, TODAY) == expected


def test_no_types_chosen_or_only_unknown_ones_means_every_type():
    kinds = types("meeting", "deadline")
    assert month.chosen_types([], kinds) == {"meeting", "deadline"}
    assert month.chosen_types(["nonsense"], kinds) == {"meeting", "deadline"}
    assert month.chosen_types(["deadline", "nonsense"], kinds) == {"deadline"}


def test_november_2026_starts_on_sunday_and_has_five_weeks():
    context = month.build(cal_with(), (2026, 11), {"meeting", "deadline"}, TODAY)
    assert len(context["weeks"]) == 5
    first = context["weeks"][0]
    assert first[0]["date"] == date(2026, 11, 1) and first[0]["in_month"]
    assert all(cell["in_month"] for week in context["weeks"][:4] for cell in week)
    assert [c["date"].day for c in context["weeks"][-1]] == [29, 30, 1, 2, 3, 4, 5]
    assert [c["in_month"] for c in context["weeks"][-1]] == [True, True, False, False, False, False, False]
    assert [c["today"] for week in context["weeks"] for c in week].count(True) == 1


def test_a_month_that_starts_midweek_is_padded_with_days_from_the_month_before():
    context = month.build(cal_with(), (2027, 1), {"meeting"}, TODAY)  # January 1, 2027 is a Friday
    assert [c["date"] for c in context["weeks"][0]][0] == date(2026, 12, 27)
    assert [c["in_month"] for c in context["weeks"][0]] == [False] * 5 + [True, True]
    assert len(context["weeks"]) == 6


def test_february_2026_fits_exactly_four_weeks_and_august_2026_needs_six():
    assert len(month.build(cal_with(), (2026, 2), {"meeting"}, TODAY)["weeks"]) == 4
    assert len(month.build(cal_with(), (2026, 8), {"meeting"}, TODAY)["weeks"]) == 6


def test_events_show_in_their_day_and_not_in_outside_days():
    cal = cal_with(date(2026, 11, 30), date(2026, 12, 1))
    context = month.build(cal, (2026, 11), {"meeting", "deadline"}, TODAY)
    cells = {c["date"]: c for week in context["weeks"] for c in week}
    assert [o.event.title for o in cells[date(2026, 11, 30)]["shown"]] == ["E1"]
    assert cells[date(2026, 12, 1)]["shown"] == [] and not cells[date(2026, 12, 1)]["in_month"]
    assert [o.event.title for o in context["happenings"]] == ["E1"]


def test_three_events_fit_a_day_and_more_become_a_count():
    day = date(2026, 11, 10)
    for count, more in [(1, 0), (3, 0), (4, 1), (7, 4)]:
        context = month.build(cal_with(*[day] * count), (2026, 11), {"meeting"}, TODAY)
        cell = next(c for week in context["weeks"] for c in week if c["date"] == day)
        assert (len(cell["shown"]), cell["more"], len(cell["all"])) == (min(count, 3), more, count)


def test_a_span_fills_every_day_it_covers():
    kinds = types("meeting")
    span = events_file.Event(1, "Audit", date(2026, 10, 30), date(2026, 11, 2), kinds[0])
    context = month.build(events_file.Calendar(types=kinds, events=[span]), (2026, 11), {"meeting"}, TODAY)
    busy = [c["date"].day for week in context["weeks"] for c in week if c["in_month"] and c["all"]]
    assert busy == [1, 2]
    assert len(context["happenings"]) == 1


def test_the_type_filter_hides_other_types():
    cal = cal_with(date(2026, 11, 10))
    cal.events.append(events_file.Event(2, "Due", date(2026, 11, 12), date(2026, 11, 12), cal.types[1]))
    context = month.build(cal, (2026, 11), {"deadline"}, TODAY)
    assert [o.event.title for o in context["happenings"]] == ["Due"] and context["filtered"]
    assert not month.build(cal, (2026, 11), {"meeting", "deadline"}, TODAY)["filtered"]


def test_addresses_keep_the_month_and_the_types_and_leave_out_defaults():
    cal = cal_with()
    everything = {"meeting", "deadline"}
    context = month.build(cal, (2026, 11), everything, TODAY)
    assert context["today_url"] == "?" and context["previous_url"] == "?month=2026-10" and context["next_url"] == "?month=2026-12"
    assert [(c["on"], c["url"]) for c in context["chips"]] == [(True, "?type=deadline"), (True, "?type=meeting")]
    only = month.build(cal, (2027, 1), {"deadline"}, TODAY)
    assert only["previous_url"] == "?month=2026-12&type=deadline"
    assert only["today_url"] == "?type=deadline"
    assert [(c["on"], c["url"]) for c in only["chips"]] == [(False, "?month=2027-01"), (True, "?month=2027-01")]


def test_there_is_no_arrow_past_the_ends_of_the_range():
    first = month.build(cal_with(), (2024, 11), {"meeting"}, TODAY)
    last = month.build(cal_with(), (2031, 11), {"meeting"}, TODAY)
    assert first["previous_url"] is None and first["next_url"]
    assert last["next_url"] is None and last["previous_url"]
