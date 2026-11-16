"""When events happen: repeats, events that last several days, and the words that describe a date.

An event can repeat monthly, quarterly or annually from its first date. On a day the month lacks (the 31st in
a 30-day month, February 29 in other years) it falls on the last day of that month.

A monthly event can instead repeat on the same weekday ("second thursday"): the first, second, third, fourth or last
one of that weekday in each month.
"""

from calendar import day_name, monthrange
from dataclasses import dataclass
from datetime import date, timedelta

STEP_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}
REPEAT_WORDS = {"monthly": "every month", "quarterly": "every three months", "annual": "every year"}
PLACES = ("first", "second", "third", "fourth", "last")
WEEKDAYS = tuple(name.lower() for name in day_name)  # Monday first, like date.weekday()


def iso_or_blank(value):
    """A day as YYYY-MM-DD text, or "" when there is no day."""
    return value.isoformat() if value else ""


@dataclass(frozen=True)
class Occurrence:
    """One happening of an event: the event, and the first and last day of this time around."""

    event: object
    start: date
    end: date

    @property
    def ident(self):
        """A short name that is unique on a page, used to link a button to its pop-up."""
        return f"e{self.event.number}-{self.start:%Y%m%d}"

    @property
    def when(self):
        return describe_days(self.start, self.end)

    @property
    def repeat_note(self):
        return repeat_note(self.event)


def _clamped(year, month, day):
    return date(year, month, min(day, monthrange(year, month)[1]))


def nth_weekday(year, month, rule):
    """The day a rule like "second thursday" points to in a month."""
    place, name = rule.split()
    weekday = WEEKDAYS.index(name)
    if place == "last":
        last = date(year, month, monthrange(year, month)[1])
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * PLACES.index(place))


def _start_in(event, year, month):
    """The day an event starts in a month: its weekday rule, or its day number (kept inside short months)."""
    return nth_weekday(year, month, event.on) if event.on else _clamped(year, month, event.date.day)


def _starts_between(event, first, last):
    """The start days of an event's happenings that fall from `first` to `last`."""
    if not event.repeats:
        return [event.date] if first <= event.date <= last else []
    step = STEP_MONTHS[event.repeats]
    origin = event.date.year * 12 + event.date.month - 1
    skip = max(0, (first.year * 12 + first.month - 1 - origin) // step - 1)
    starts = []
    while True:
        year, month = divmod(origin + skip * step, 12)
        start = _start_in(event, year, month + 1)
        if start > last or (event.until and start > event.until):
            return starts
        if start >= first:
            starts.append(start)
        skip += 1


def occurrences_between(events, first, last):
    """Every happening that touches the days `first` to `last`, earliest first."""
    found = []
    for event in events:
        length = event.end - event.date
        for start in _starts_between(event, first - length, last):
            found.append(Occurrence(event, start, start + length))
    return sorted(found, key=lambda o: (o.start, o.event.number))


def describe_days(start, end):
    """A day or a span of days in words, like "Mar 5, 2027" or "Mar 5 to Apr 2, 2027"."""
    if start == end:
        return f"{start:%b} {start.day}, {start.year}"
    first = f"{start:%b} {start.day}" + (f", {start.year}" if start.year != end.year else "")
    return f"{first} to {end:%b} {end.day}, {end.year}"


def repeat_note(event):
    """A sentence about how an event repeats, or an empty text for one that does not."""
    if not event.repeats:
        return ""
    note = f"Repeats {REPEAT_WORDS[event.repeats]}"
    if event.on:
        place, name = event.on.split()
        note = f"Repeats on the {place} {name.title()} of each month"
    return note + (f", until {describe_days(event.until, event.until)}" if event.until else "")


def days_in(first, last):
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]
