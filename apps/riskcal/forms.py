"""The short form for proposing a calendar event (or changing one). The checks are the file's own (events_file.check_event)."""

from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.topics.models import Topic

from . import events_file, schedule
from .models import RUNS_TO_SETTLE, ItemStatus

SUMMARY_MAX = 500
BLANK = ("", "---------")


def _day_widget():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class EventForm(BootstrapFormMixin, forms.Form):
    """The lines of an event. `types` are the event types from the file; `with_summary` adds "what changed" for an edit."""

    title = forms.CharField(max_length=160)
    date = forms.DateField(widget=_day_widget(), help_text="The day it happens, or the first day if it lasts several days.")
    end = forms.DateField(widget=_day_widget(), required=False, help_text="The last day, if it lasts several days.")
    type = forms.ChoiceField(choices=[])
    details = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False,
                              help_text="A few plain sentences. [link text](/guides/) makes a link.")
    link = forms.CharField(max_length=300, required=False, help_text="A TRAC page starting with / (like /guides/) or a web address starting with https://. It becomes a button in the pop-up.")
    repeats = forms.ChoiceField(choices=[BLANK] + [(word, word.title()) for word in events_file.REPEATS], required=False,
                                help_text="Leave blank for an event that happens once.")
    place = forms.ChoiceField(choices=[BLANK] + [(word, word.title()) for word in schedule.PLACES], required=False, label="On the")
    weekday = forms.ChoiceField(choices=[BLANK] + [(word, word.title()) for word in schedule.WEEKDAYS], required=False, label="Weekday",
                                help_text="Only for a monthly event that falls on the same weekday, like the second Thursday. "
                                          "The date above must be the first one.")
    until = forms.DateField(widget=_day_widget(), required=False, help_text="The last day a repeating event can happen.")
    change_summary = forms.CharField(max_length=SUMMARY_MAX, required=False, label="What changed",
                                     help_text="One line for Tech Risk and the history.")

    def __init__(self, *args, types=(), with_summary=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.types = list(types)
        self.fields["type"].choices = [(t.key, t.label) for t in self.types]
        if not with_summary:
            del self.fields["change_summary"]
        self.style_fields()

    def lines(self):
        """The form's answers as the lines of an events.yaml entry."""
        data = self.cleaned_data
        place, weekday = data.get("place", ""), data.get("weekday", "")
        return {
            "title": data.get("title", ""), "date": schedule.iso_or_blank(data.get("date")), "end": schedule.iso_or_blank(data.get("end")), "type": data.get("type", ""),
            "details": data.get("details", ""), "link": data.get("link", ""), "repeats": data.get("repeats", ""),
            "on": f"{place} {weekday}".strip(), "until": schedule.iso_or_blank(data.get("until")),
        }

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        place, weekday = data.get("place"), data.get("weekday")
        if bool(place) != bool(weekday):
            raise forms.ValidationError("For a weekday rule, choose both the place (like second) and the weekday.")
        _, reasons = events_file.check_event(0, self.lines(), self.types)
        if reasons:
            raise forms.ValidationError([reason[:1].upper() + reason[1:] for reason in reasons])
        return data

    def content(self):
        """The answers as the fields of a CalendarEventVersion."""
        lines = self.lines()
        return {
            "title": lines["title"].strip(), "date": self.cleaned_data["date"], "end": self.cleaned_data.get("end"), "type": lines["type"],
            "details": lines["details"].strip(), "link": lines["link"], "repeats": lines["repeats"],
            "on_rule": " ".join(lines["on"].split()), "until": self.cleaned_data.get("until"),
        }

    @staticmethod
    def initial_from(version):
        """The form's starting answers for an existing version."""
        place, _, weekday = version.on_rule.partition(" ")
        return {
            "title": version.title, "date": version.date, "end": version.end, "type": version.type, "details": version.details,
            "link": version.link, "repeats": version.repeats, "place": place, "weekday": weekday, "until": version.until,
        }


class ItemForm(BootstrapFormMixin, forms.Form):
    """The lines of an In progress item. `controls` is [(ident, topic)] for the TRAC controls that exist."""

    title = forms.CharField(max_length=160, label="Name", help_text="For example: Job inventory guidance.")
    covers = forms.CharField(max_length=300, required=False, label="What it covers", help_text="One line.")
    progress = forms.ChoiceField(choices=ItemStatus.choices, label="Status", initial=ItemStatus.IN_PROGRESS,
                                 help_text="Wanted: agreed it's needed, not started. In progress: being built. Live: in use.")
    control = forms.ChoiceField(choices=[], required=False, label="TRAC control",
                                help_text="Leave blank if it has no TRAC ID yet. It then shows as Proposed.")
    topic = forms.ModelChoiceField(queryset=Topic.objects.order_by("position", "name"), required=False,
                                   help_text="Only needed when no TRAC control is picked. Sets the item's color.")
    team = forms.CharField(max_length=120, label="Owning team")
    expected_on = forms.DateField(widget=_day_widget(), required=False, label="Expected go-live",
                                  help_text="The team's best estimate. It can change later.")
    went_live_on = forms.DateField(widget=_day_widget(), required=False, label="Went live on", help_text="Only for Live.")
    runs_passed = forms.TypedChoiceField(
        choices=[(n, str(n)) for n in range(RUNS_TO_SETTLE + 1)], coerce=int, empty_value=0, required=False,
        label="Runs without an issue since going live",
        help_text=f"Only for Live. Each run of the control counts once. At {RUNS_TO_SETTLE} it leaves the In progress list.")
    change_summary = forms.CharField(max_length=SUMMARY_MAX, required=False, label="What changed",
                                     help_text="One line for Tech Risk and the history.")

    def __init__(self, *args, controls=(), with_summary=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.control_topics = dict(controls)
        self.fields["control"].choices = [BLANK] + [(ident, ident) for ident, _ in controls]
        if not with_summary:
            del self.fields["change_summary"]
        self.style_fields()

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        live = data["progress"] == ItemStatus.LIVE
        if data.get("control"):
            data["topic"] = self.control_topics[data["control"]]
        elif data.get("topic") is None:
            self.add_error("topic", "Pick a topic, or pick a TRAC control.")
        if live and not data.get("went_live_on"):
            self.add_error("went_live_on", "Add the day it went live.")
        if not live:
            data["went_live_on"], data["runs_passed"] = None, 0
        return data

    def content(self):
        """The answers as the fields of a WorkItemVersion."""
        data = self.cleaned_data
        return {
            "title": data["title"].strip(), "covers": data.get("covers", "").strip(), "progress": data["progress"],
            "topic": data["topic"], "control": data.get("control", ""), "team": data["team"].strip(),
            "expected_on": data.get("expected_on"), "went_live_on": data.get("went_live_on"), "runs_passed": data.get("runs_passed") or 0,
        }

    @staticmethod
    def initial_from(version):
        """The form's starting answers for an existing version."""
        return {
            "title": version.title, "covers": version.covers, "progress": version.progress, "control": version.control,
            "topic": version.topic_id, "team": version.team, "expected_on": version.expected_on,
            "went_live_on": version.went_live_on, "runs_passed": version.runs_passed,
        }
