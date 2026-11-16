"""The calendar's In progress list: controls and guidance on the way, and when each is expected to go live.

Only approved and published items show. A live item stays in the list until it has had two runs without an
issue (the owning team says so; Tech Risk spot checks). Items can be filtered by progress, topic and team, and
the same filters decide which go-live markers show on the month.
"""

from dataclasses import dataclass
from datetime import date

from apps.core.versioning import current_versions
from apps.topics.models import Topic

from . import schedule
from .models import RUNS_TO_SETTLE, ItemStatus, WorkItem

SHOWN_IN_PANEL = 10  # the 10-row rule: more than this and the list links to the full page
ORDER = {ItemStatus.IN_PROGRESS: 0, ItemStatus.WANTED: 1, ItemStatus.LIVE: 2}
FAR_FUTURE = date.max


@dataclass
class Filters:
    """What the visitor chose. Blank means everything."""

    progress: str = ""
    topic: str = ""  # a topic's ID prefix, like MO
    team: str = ""

    def query(self):
        """The filters as address pairs, leaving out the blank ones."""
        return [(name, value) for name, value in (("progress", self.progress), ("topic", self.topic), ("team", self.team)) if value]

    def any(self):
        return bool(self.query())


def read_filters(params):
    """Filters from the page address. Unknown progress words are ignored."""
    progress = params.get("progress", "")
    return Filters(
        progress=progress if progress in ItemStatus.values else "",
        topic=params.get("topic", "").strip().upper()[:3],
        team=params.get("team", "").strip()[:120],
    )


def live_items():
    """Every published item still on the list (settled live items are left out), in list order."""
    items = [version for version in current_versions(WorkItem) if not version.is_settled()]
    items.sort(key=lambda v: (ORDER[v.progress], v.expected_on or v.went_live_on or FAR_FUTURE, v.title.lower()))
    return items


def chosen(items, filters):
    """The items that match the filters."""
    return [
        v for v in items
        if (not filters.progress or v.progress == filters.progress)
        and (not filters.topic or v.topic.id_prefix == filters.topic)
        and (not filters.team or v.team == filters.team)
    ]


def date_line(version):
    """("Expected go-live", "Dec 15, 2026") or ("Went live", ...); "Not set yet" when there is no date."""
    if version.progress == ItemStatus.LIVE:
        day = version.went_live_on
        return "Went live", schedule.describe_days(day, day) if day else "Not set yet"
    day = version.expected_on
    return "Expected go-live", schedule.describe_days(day, day) if day else "Not set yet"


def runs_line(version):
    """For a live item, "1 of 2 runs without an issue"; otherwise an empty text."""
    if version.progress != ItemStatus.LIVE:
        return ""
    return f"{version.runs_passed} of {RUNS_TO_SETTLE} runs without an issue"


def card(version):
    """What the list shows for one item."""
    label, when = date_line(version)
    return {
        "version": version, "item": version.entity, "topic": version.topic, "code": version.control or f"{version.topic.id_prefix} · Proposed",
        "date_label": label, "date": when, "chip": version.get_progress_display(), "runs": runs_line(version), "progress": version.progress,
    }


def markers_by_day(items, first, last):
    """{day: [marker]} for the expected go-live and went-live days inside first..last."""
    markers = {}
    for version in items:
        live = version.progress == ItemStatus.LIVE
        day = version.went_live_on if live else version.expected_on
        if day and first <= day <= last:
            words = "Went live" if live else "Go-live (expected)"
            markers.setdefault(day, []).append({"version": version, "words": words, "live": live})
    return markers


def panel(filters, first, last):
    """The context for the In progress list and the month's markers."""
    everything = live_items()
    picked = chosen(everything, filters)
    return {
        "work_cards": [card(v) for v in picked[:SHOWN_IN_PANEL]],
        "work_total": len(picked),
        "work_more": len(picked) > SHOWN_IN_PANEL,
        "work_markers": markers_by_day(picked, first, last),
        "work_filters": filters,
        "work_topics": Topic.objects.order_by("position", "name"),
        "work_teams": sorted({v.team for v in everything}, key=str.lower),
        "work_progress": ItemStatus.choices,
        "work_any": bool(everything),
    }
