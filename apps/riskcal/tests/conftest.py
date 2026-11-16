"""Fixtures for the calendar tests: a calendar file of their own, never the shipped one."""

import textwrap

import pytest

from apps.riskcal import events_file

TYPES = """\
types:
  - key: control_due
    label: Control due
  - key: meeting
    label: Meeting
"""


@pytest.fixture
def write_calendar(tmp_path, monkeypatch):
    """Write a calendar file with the given events text (after the two sample types) and use it for the site."""
    path = tmp_path / "events.yaml"
    monkeypatch.setattr(events_file, "FILE", path)

    def write(events="events: []\n", types=TYPES):
        path.write_text(types + textwrap.dedent(events), encoding="utf-8")
        return path

    return write


@pytest.fixture
def today(monkeypatch):
    """Pretend today is 2026-11-15 (a Sunday); the month range is then 2024-11 to 2031-11."""
    import datetime

    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda: datetime.date(2026, 11, 15))
    return datetime.date(2026, 11, 15)
