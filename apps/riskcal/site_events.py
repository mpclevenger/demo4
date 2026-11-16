"""Calendar events proposed on the site, turned into the same Event objects the file's events are.

Only approved and published events come in; a proposal waiting for Tech Risk, a rejected one and a retired one never
show on the calendar. The lines are checked again with the file's own checks, so one bad event can't break the page.
"""

from apps.core.versioning import current_versions

from . import events_file
from .models import CalendarEvent

FIRST_NUMBER = 1_000_000  # an event's number is this plus its id, so it never matches a number from the file


def event_from(version, types):
    """(Event, []) for a version that reads cleanly, or (None, the reasons)."""
    return events_file.check_event(FIRST_NUMBER + version.entity_id, version.lines(), types)


def add_site_events(calendar):
    """Add every live site event to `calendar.events`; say in `calendar.problems` which ones could not be shown."""
    for version in current_versions(CalendarEvent):
        event, reasons = event_from(version, calendar.types)
        if event:
            calendar.events.append(event)
        else:
            calendar.problems.append(f'The event "{version.title}" (added on the site) is not shown: ' + " ".join(reasons))
    return calendar
