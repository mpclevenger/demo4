"""Everything the calendar page shows for one month: the grid, the type chips, the arrows and the month's list.

The month comes from `?month=YYYY-MM` and the chosen types from `?type=key` (repeated). Both are forgiving: a
missing or unreadable month is this month, a month outside the range is moved to the nearest end of it, and
unknown types are ignored. No types chosen means every type.
"""

import calendar
import re
from datetime import date
from urllib.parse import urlencode

from . import schedule

YEARS_BACK = 2
YEARS_AHEAD = 5
SHOWN_PER_DAY = 3  # more events than this in a day become "+N more"
_MONTH = re.compile(r"(\d{4})-(\d{2})")


def _index(year, month):
    return year * 12 + month - 1


def _from_index(index):
    year, month = divmod(index, 12)
    return year, month + 1


def month_range(today):
    """The first and last month that can be shown, as (year, month) pairs."""
    now = _index(today.year, today.month)
    return _from_index(now - YEARS_BACK * 12), _from_index(now + YEARS_AHEAD * 12)


def parse_month(text, today):
    """(year, month) for "YYYY-MM", or this month when the text is missing or not a month."""
    found = _MONTH.fullmatch((text or "").strip())
    year, month = (int(found.group(1)), int(found.group(2))) if found else (today.year, today.month)
    if not 1 <= month <= 12 or year < 1:
        year, month = today.year, today.month
    low, high = month_range(today)
    return _from_index(min(max(_index(year, month), _index(*low)), _index(*high)))


def chosen_types(keys, types):
    """The set of type keys to show: the known ones asked for, or all of them."""
    known = {t.key for t in types}
    wanted = set(keys) & known
    return wanted or known


def _address(month, today, chosen, types, extra=()):
    """The page address for a month and a set of types, plus `extra` pairs (the In progress filters); defaults are left out."""
    query = _query_pairs(month, today, chosen, types) + list(extra)
    return "?" + urlencode(query) if query else "?"


def _query_pairs(month, today, chosen, types):
    """The month and type pairs of the address, for forms that must keep them (the In progress filters form)."""
    pairs = []
    if month != (today.year, today.month):
        pairs.append(("month", f"{month[0]:04d}-{month[1]:02d}"))
    if chosen != {t.key for t in types}:
        pairs += [("type", t.key) for t in types if t.key in chosen]
    return pairs


def _step(month, change, today):
    """The month next to this one, or None past the end of the range."""
    low, high = month_range(today)
    index = _index(*month) + change
    return _from_index(index) if _index(*low) <= index <= _index(*high) else None


def _cell(day, month, today, by_day, markers):
    in_month = day.month == month
    happening = by_day.get(day, []) if in_month else []
    return {
        "date": day,
        "in_month": in_month,
        "today": day == today,
        "shown": happening[:SHOWN_PER_DAY],
        "more": len(happening) - SHOWN_PER_DAY if len(happening) > SHOWN_PER_DAY else 0,
        "all": happening,
        "markers": markers.get(day, []) if in_month else [],
    }


def month_days(month):
    """The first and last day of a (year, month)."""
    year, number = month
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


def build(cal, month, chosen, today, extra=(), markers=None):
    """The page's context for one month of the calendar.

    `extra` are address pairs every link keeps (the In progress filters). `markers` are {day: [go-live marker]}.
    """
    markers = markers or {}
    year, number = month
    first, last = month_days(month)
    events = [e for e in cal.events if e.type.key in chosen]
    happenings = schedule.occurrences_between(events, first, last)
    by_day = {day: [o for o in happenings if o.start <= day <= o.end] for day in schedule.days_in(first, last)}
    weeks = [[_cell(day, number, today, by_day, markers) for day in week]
             for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, number)]
    chips = []
    for t in cal.types:
        chips.append({"type": t, "on": t.key in chosen, "url": _address(month, today, chosen ^ {t.key}, cal.types, extra)})
    previous, following = _step(month, -1, today), _step(month, 1, today)
    return {
        "heading": f"{first:%B} {year}",
        "weeks": weeks,
        "happenings": happenings,
        "chips": chips,
        "filtered": chosen != {t.key for t in cal.types},
        "previous_url": _address(previous, today, chosen, cal.types, extra) if previous else None,
        "next_url": _address(following, today, chosen, cal.types, extra) if following else None,
        "today_url": _address((today.year, today.month), today, chosen, cal.types, extra),
        "month_query": _query_pairs(month, today, chosen, cal.types),
    }
