"""The risk and control calendar's file: the event types and the events. The text lives in content/calendar/events.yaml.

The file has two lists. `types` gives each kind of event a short key and a label; `events` holds the events
themselves (see the comments at the top of the file for the lines an event can have). Nothing here is stored in the
database, and the file is read again on every page load, so a change to it shows on the next page load.

A second, optional file, content/calendar/control-dates.csv, lists control due dates exported from a spreadsheet. Each
row becomes a `control_due` event that links to the site search for the control's ID.

`read_calendar` never stops at the first mistake: it keeps every event it can read and collects a plain-word message
for each one it can't, so the page keeps working and `check_calendar` can list everything to fix.
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from apps.core.links import is_allowed_link
from apps.core.yaml_files import load_yaml, read_day

from . import schedule

FILE = Path(settings.BASE_DIR) / "content" / "calendar" / "events.yaml"
EVENT_LINES = ("title", "date", "end", "type", "details", "link", "repeats", "on", "until")
REPEATS = ("monthly", "quarterly", "annual")
DATES_FILE_NAME = "control-dates.csv"
DATES_COLUMNS = ("control_id", "due_date")  # the others (period, note) are optional
DATES_TYPE = "control_due"
MAX_TYPES = 8  # each type has its own color in static/css/riskcal.css
_KEY = re.compile(r"[a-z][a-z0-9_]*")
_WHITESPACE = re.compile(r"\s")
_US_DAY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


@dataclass(frozen=True)
class EventType:
    key: str
    label: str
    color: int  # 0 to MAX_TYPES - 1: which color in riskcal.css


@dataclass(frozen=True)
class Event:
    number: int  # the event's place in the file, starting at 1
    title: str
    date: date
    end: date  # the same as `date` for a one-day event
    type: EventType
    details: str = ""
    link: str = ""
    repeats: str = ""
    until: date | None = None
    on: str = ""  # a weekday rule like "second thursday", for a monthly event

    @property
    def on_site(self):
        """True when the link goes to a TRAC page rather than another address."""
        return self.link.startswith("/")


@dataclass
class Calendar:
    types: list = field(default_factory=list)
    events: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    control_dates: int = 0  # how many of the events came from control-dates.csv


def _read_types(data, name, problems):
    types, seen = [], set()
    if not isinstance(data, list) or not data:
        problems.append(f"{name}: 'types' needs a list of event types, each with a key and a label.")
        return types
    for number, raw in enumerate(data, start=1):
        key = str(raw.get("key") or "").strip() if isinstance(raw, dict) else ""
        label = str(raw.get("label") or "").strip() if isinstance(raw, dict) else ""
        if not _KEY.fullmatch(key) or not label:
            problems.append(f"{name}: type {number} needs a 'key' (lowercase letters, digits and underscores, like control_due) and a 'label'.")
        elif key in seen:
            problems.append(f"{name}: the type key '{key}' is used twice.")
        else:
            seen.add(key)
            types.append(EventType(key, label, len(types)))
    if len(types) > MAX_TYPES:
        problems.append(f"{name}: there are {len(types)} event types; the calendar has colors for {MAX_TYPES}.")
    return types




def _check_days(raw, found):
    """{"date", "end", "until": the day} for each of those lines that is a real day; adds a reason to `found` for each that is not."""
    days = {}
    for line in ("date", "end", "until"):
        if raw.get(line) in (None, ""):
            if line == "date":
                found.append("needs a date, written YYYY-MM-DD.")
        elif read_day(raw[line]) is None:
            found.append(f"the {line} '{raw[line]}' isn't a real day. Write it as YYYY-MM-DD, for example 2027-03-31.")
        else:
            days[line] = read_day(raw[line])
    if "end" in days and "date" in days and days["end"] < days["date"]:
        found.append("the end date is before the date.")
    return days


def _check_repeat(raw, days, found):
    """(repeats, on) as the file writes them; adds a reason to `found` for each mistake in repeats, on and until."""
    say = found.append
    repeats = str(raw.get("repeats") or "").strip().lower()
    if repeats and repeats not in REPEATS:
        say(f"'repeats' must be {', '.join(REPEATS[:-1])} or {REPEATS[-1]}.")
    on = " ".join(str(raw.get("on") or "").lower().split())
    if on and not _weekday_rule(on):
        say(f"'on' must be a place and a weekday, like 'second thursday' (first, second, third, fourth or last, then {', '.join(w.title() for w in schedule.WEEKDAYS[:-1])} or Sunday).")
        on = ""
    if on and repeats != "monthly":
        say("'on' only works together with 'repeats: monthly'.")
    elif on and "date" in days and schedule.nth_weekday(days["date"].year, days["date"].month, on) != days["date"]:
        say(f"the date {days['date']} is not the {on} of its month. Change the date to {schedule.nth_weekday(days['date'].year, days['date'].month, on)} "
            "(the first time it happens), or change 'on'.")
    if "until" in days and not repeats:
        say("'until' only makes sense together with 'repeats'.")
    if "until" in days and "date" in days and days["until"] < days["date"]:
        say("the until date is before the date.")
    return repeats, on


def _check_link_line(raw, found):
    """The event's link, or "" when there is none; adds a reason to `found` when it isn't a TRAC page or an https:// address."""
    link = str(raw.get("link") or "").strip()
    if link and not (is_allowed_link(link) and not _WHITESPACE.search(link)):
        found.append("the link must be a TRAC page starting with / (like /guides/) or an https:// address.")
    return link


def check_event(number, raw, types):
    """(the Event, []) for lines that are all right, or (None, a plain-word reason for each mistake).

    `raw` holds the lines of one event as the file would (title, date, end, type, details, link, repeats, on, until),
    with days written YYYY-MM-DD. The file reader and the site's "Add an event" form both use this.
    """
    raw = raw if isinstance(raw, dict) else {}
    found = []
    title = str(raw.get("title") or "").strip()
    if not title:
        found.append("needs a title.")
    for line in raw.keys() - set(EVENT_LINES):
        found.append(f"'{line}' isn't a known line. Use: {', '.join(EVENT_LINES)}.")
    days = _check_days(raw, found)
    by_key = {t.key: t for t in types}
    event_type = by_key.get(str(raw.get("type") or "").strip())
    if event_type is None:
        found.append(f"the type '{raw.get('type') or ''}' isn't in the types list. Use one of: {', '.join(by_key) or 'none are defined'}.")
    link = _check_link_line(raw, found)
    repeats, on = _check_repeat(raw, days, found)
    if found:
        return None, found
    return Event(number, title, days["date"], days.get("end", days["date"]), event_type,
                 details=str(raw.get("details") or "").strip(), link=link, repeats=repeats, until=days.get("until"), on=on), []


def _read_event(number, raw, types, name, problems):
    """One Event, or None after adding a message to `problems` for each mistake in it."""
    event, reasons = check_event(number, raw, types)
    title = str(raw.get("title") or "").strip() if isinstance(raw, dict) else ""
    who = f'"{title}"' if title else f"event {number}"
    problems.extend(f"{name}: {who}: {reason}" for reason in reasons)
    return event


def _weekday_rule(text):
    """True for a rule like "second thursday": first, second, third, fourth or last, then a weekday name."""
    words = text.split()
    return len(words) == 2 and words[0] in schedule.PLACES and words[1] in schedule.WEEKDAYS


def control_dates_path(events_path):
    """Where control-dates.csv is: beside the events file."""
    return Path(events_path).with_name(DATES_FILE_NAME)


def _due_day(text):
    """A date from YYYY-MM-DD or the US forms Excel writes (M/D/YYYY, MM/DD/YYYY), or None."""
    found = _US_DAY.fullmatch(text)
    if not found:
        return read_day(text)
    month, day, year = (int(part) for part in found.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _read_rows(path):
    """The rows of the CSV as lists of text (Excel's "CSV UTF-8" starts with a byte-order mark), or (None, a problem)."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle)), None
    except UnicodeDecodeError:
        return None, f"{path.name}: the file isn't UTF-8 text. In Excel, use Save As and choose \"CSV UTF-8\"."
    except OSError:
        return None, f"{path.name}: the file can't be read."


def _control_event(row_number, number, row, columns, kind, path_name, problems):
    """One Event (called `number` among all events) from the CSV's row `row_number`, or None after adding a message to `problems`."""

    def cell(name):
        index = columns.get(name)
        return row[index].strip() if index is not None and index < len(row) else ""

    control_id, period, note = cell("control_id"), cell("period"), cell("note")
    who = f"row {row_number}" + (f" ({control_id})" if control_id else "")
    if not control_id:
        problems.append(f"{path_name}: {who}: needs a control_id, like MA-04.")
        return None
    due = _due_day(cell("due_date"))
    if due is None:
        problems.append(f"{path_name}: {who}: the due_date '{cell('due_date')}' isn't a real day. Write it as YYYY-MM-DD or M/D/YYYY, for example 2027-03-31.")
        return None
    search = reverse("core:search") + "?" + urlencode({"q": control_id})
    return Event(number, f"{control_id} due" + (f" ({period})" if period else ""), due, due, kind, details=note, link=search)


def _read_control_dates(path, types, first_number, problems):
    """The events in control-dates.csv (none when the file isn't there), adding a message to `problems` for each row it skips."""
    if not path.exists():
        return []
    rows, problem = _read_rows(path)
    if problem:
        problems.append(problem)
        return []
    columns = {}
    for index, name in enumerate(rows[0] if rows else []):
        columns.setdefault(name.strip().lower(), index)
    missing = [name for name in DATES_COLUMNS if name not in columns]
    if missing:
        problems.append(f"{path.name}: the first row must name the columns control_id, period, due_date and note. Missing: {', '.join(missing)}.")
        return []
    kind = next((t for t in types if t.key == DATES_TYPE), None)
    if kind is None:
        problems.append(f"{path.name}: its rows are shown as the '{DATES_TYPE}' event type, but that type is missing from the types list in events.yaml. Add it there.")
        return []
    events = []
    for number, row in enumerate(rows, start=1):
        if number > 1 and any(value.strip() for value in row):
            event = _control_event(number, first_number + number, row, columns, kind, path.name, problems)
            if event:
                events.append(event)
    return events


def read_calendar(path=None):
    """The types and events in the file, with a plain-word message for anything that could not be read."""
    path = Path(path or FILE)
    calendar = Calendar()
    data, problem = load_yaml(path, keep_as_text=("timestamp", "bool"))
    if problem:
        calendar.problems.append(problem)
        return calendar
    if not isinstance(data, dict) or "types" not in data or "events" not in data:
        calendar.problems.append(f"{path.name}: expected two lists, 'types' and 'events'.")
        return calendar
    for key in data.keys() - {"types", "events"}:
        calendar.problems.append(f"{path.name}: '{key}' isn't a known part of the file. Use 'types' and 'events'.")
    calendar.types = _read_types(data["types"], path.name, calendar.problems)
    events = data["events"] or []
    if not isinstance(events, list):
        calendar.problems.append(f"{path.name}: 'events' must be a list.")
        return calendar
    for number, raw in enumerate(events, start=1):
        event = _read_event(number, raw, calendar.types, path.name, calendar.problems)
        if event:
            calendar.events.append(event)
    dates = _read_control_dates(control_dates_path(path), calendar.types, len(events), calendar.problems)
    calendar.events += dates
    calendar.control_dates = len(dates)
    return calendar
