"""Calendar events proposed on the site. Each is a governed item: proposed, approved by Tech Risk, then published.

The file content/calendar/events.yaml keeps working as before. These events are read in beside it, and only once
Tech Risk has approved them. A retired event leaves the calendar but stays in the history; nothing is deleted.
"""

from django.db import models
from django.urls import reverse

from apps.core.versioning import GovernedEntity, GovernedVersion

from .schedule import iso_or_blank


class CalendarEvent(GovernedEntity):
    """One event on the calendar that was proposed on the site (the stable thing; its versions hold the lines)."""

    class Meta:
        verbose_name = "calendar event"

    def __str__(self):
        version = self.current() or self.versions.order_by("-number").first()
        return version.title if version else f"Calendar event {self.pk}"

    def get_absolute_url(self):
        return reverse("riskcal:event", args=[self.pk])

    def get_list_url(self):
        return reverse("riskcal:index")


class CalendarEventVersion(GovernedVersion):
    """The lines of an event, the same ones an event has in events.yaml."""

    entity = models.ForeignKey(CalendarEvent, on_delete=models.PROTECT, related_name="versions")
    title = models.CharField(max_length=160)
    date = models.DateField(help_text="The day it happens (the first day, for an event that lasts several days).")
    end = models.DateField(null=True, blank=True, help_text="The last day, for an event that lasts several days.")
    type = models.CharField(max_length=40, help_text="A key from the types list at the top of events.yaml.")
    details = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    repeats = models.CharField(max_length=10, blank=True)
    on_rule = models.CharField(max_length=30, blank=True, help_text="A weekday rule like 'second thursday'.")
    until = models.DateField(null=True, blank=True)

    class Meta(GovernedVersion.Meta):  # keeps the parent's ordering and its one-number-per-event rule
        pass

    def lines(self):
        """The version as the lines an events.yaml entry has, with days written YYYY-MM-DD."""
        return {
            "title": self.title, "date": iso_or_blank(self.date), "end": iso_or_blank(self.end), "type": self.type,
            "details": self.details, "link": self.link, "repeats": self.repeats, "on": self.on_rule, "until": iso_or_blank(self.until),
        }


class ItemStatus(models.TextChoices):
    """Where a piece of work stands. The words are the shared ones used in TRUST, Risk and TRAC."""

    WANTED = "wanted", "Wanted"
    IN_PROGRESS = "in_progress", "In progress"
    LIVE = "live", "Live"


RUNS_TO_SETTLE = 2  # a live item leaves the In progress list after this many runs without an issue (owner, 16 Nov 2026)


class WorkItem(GovernedEntity):
    """A control or piece of guidance on the way, shown in the calendar's In progress list (the stable thing)."""

    class Meta:
        verbose_name = "in progress item"

    def __str__(self):
        version = self.current() or self.versions.order_by("-number").first()
        return version.title if version else f"In progress item {self.pk}"

    def get_absolute_url(self):
        return reverse("riskcal:item", args=[self.pk])

    def get_list_url(self):
        return reverse("riskcal:items")


class WorkItemVersion(GovernedVersion):
    """The lines of an In progress item. Every version is kept, so date changes stay in the history."""

    entity = models.ForeignKey(WorkItem, on_delete=models.PROTECT, related_name="versions")
    title = models.CharField(max_length=160)
    covers = models.CharField(max_length=300, blank=True, help_text="One line on what it covers.")
    progress = models.CharField(max_length=12, choices=ItemStatus.choices, default=ItemStatus.IN_PROGRESS,
                                help_text="Wanted, In progress or Live.")
    topic = models.ForeignKey("topics.Topic", on_delete=models.PROTECT, related_name="+")
    control = models.CharField(max_length=40, blank=True, help_text="The TRAC control ID, like MO-02. Blank while it has none (Proposed).")
    team = models.CharField(max_length=120, help_text="The team that owns the work.")
    expected_on = models.DateField(null=True, blank=True, help_text="The day the team expects it to go live.")
    went_live_on = models.DateField(null=True, blank=True)
    runs_passed = models.PositiveSmallIntegerField(default=0, help_text="Runs of the control since going live without an issue.")

    class Meta(GovernedVersion.Meta):
        pass

    def is_settled(self):
        """True once a live item has had enough runs without an issue to leave the In progress list."""
        return self.progress == ItemStatus.LIVE and self.runs_passed >= RUNS_TO_SETTLE
