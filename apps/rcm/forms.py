"""Edit forms for the risk and control registers.

The repeatable sections (statements, steps, control links) travel as JSON in
hidden inputs that static/js/trac-rows.js fills in on submit. Each field below parses
and checks that JSON, so a hand-made request can't store a malformed shape.
"""

import json

from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import reverse

from apps.core.forms import BootstrapFormMixin
from apps.core.versioning import WORKFLOW_FIELDS
from apps.platforms.categories import Category
from apps.platforms.models import Platform
from apps.topics.models import Stage, Theme, Topic

from . import levels, selectors
from .models import (
    ID_PATTERN,
    Control,
    ControlVersion,
    Coverage,
    Driver,
    EngineRisk,
    Frequency,
    Method,
    Nature,
    OWNER_ROLE_HELP,
    Risk,
    RiskVersion,
)

REASON_MAX = 300  # characters allowed in "why it covers this risk"
BAD_ROWS = "Something went wrong with this section. Reload the page and try again."


# Repeatable rows

class RowsField(forms.Field):
    """Hidden JSON list built from rows on the page."""

    widget = forms.HiddenInput

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def widget_attrs(self, widget):
        return {"data-rows-output": ""}

    def prepare_value(self, value):
        return value if isinstance(value, str) else json.dumps(value)

    def to_python(self, value):
        if value in self.empty_values:
            return []
        try:
            data = json.loads(value)
        except ValueError:
            raise _bad_rows()
        if not isinstance(data, list):
            raise _bad_rows()
        return self.parse(data)

    def parse(self, data):
        raise NotImplementedError


def _bad_rows():
    return ValidationError(BAD_ROWS, code="invalid")


def _text(value):
    """A stripped string. Anything else means the request was not made by our page."""
    if not isinstance(value, str):
        raise _bad_rows()
    return value.strip()


COMMAND_KEYS_KEPT_AS_THEY_ARE = ("audience", "confirmed_by", "confirmed_on")


def _row(entry):
    """A row that must be a dict."""
    if not isinstance(entry, dict):
        raise _bad_rows()
    return entry


class StatementsField(RowsField):
    """One plain statement per row."""

    def parse(self, data):
        return [text for text in (_text(entry) for entry in data) if text]


class RiskIdsField(forms.CharField):
    """Risk engine ids, one per line (for example air.ops.02). Cleans to a list of ids, each once."""

    widget = forms.Textarea

    def prepare_value(self, value):
        return "\n".join(value) if isinstance(value, list) else value

    def to_python(self, value):
        return list(dict.fromkeys(_lines(value or "")))


def _lines(text):
    """The non-empty lines of a text box, each stripped."""
    return [line.strip() for line in _text(text).splitlines() if line.strip()]


class StepsField(RowsField):
    """The steps of a control, as the edit page sends them.

    A row holds do, how, weigh (one item per line), policy, evidence_keep, evidence_shows (one item per
    line) and commands (platform, note, code). It cleans to the stored shape; the model checks the rules.
    """

    @staticmethod
    def _command(entry):
        entry = _row(entry)
        platform, note, code = (_text(entry.get(key, "")) for key in ("platform", "note", "code"))
        if not (platform or note or code):
            return None
        command = {"platform": platform, **({"note": note} if note else {}), "code": entry.get("code", "").strip("\n")}
        # Who the command is for and whether its platform owner confirmed it are edited in the control file;
        # the form carries them through a save unchanged.
        for key in COMMAND_KEYS_KEPT_AS_THEY_ARE:
            if text := _text(entry.get(key, "")):
                command[key] = text
        return command

    def prepare_value(self, value):
        if isinstance(value, str):
            return value
        return json.dumps([self._row_for_page(step) for step in value or []])

    @staticmethod
    def _row_for_page(step):
        evidence = step.get("evidence", {})
        return {
            "do": step.get("do", ""), "how": step.get("how", ""), "weigh": "\n".join(step.get("weigh", [])),
            "policy": step.get("policy", ""), "evidence_keep": evidence.get("keep", ""),
            "evidence_shows": "\n".join(evidence.get("shows", [])), "commands": step.get("commands", []),
            **({"checks_json": json.dumps(step["checks"])} if step.get("checks") else {}),
        }

    def parse(self, data):
        steps = []
        for entry in data:
            entry = _row(entry)
            step = {"do": _text(entry.get("do", ""))}
            for key in ("how", "policy"):
                if text := _text(entry.get(key, "")):
                    step[key] = text
            if weigh := _lines(entry.get("weigh", "")):
                step["weigh"] = weigh
            keep, shows = _text(entry.get("evidence_keep", "")), _lines(entry.get("evidence_shows", ""))
            if keep or shows:
                step["evidence"] = {"keep": keep, **({"shows": shows} if shows else {})}
            commands = entry.get("commands", [])
            if not isinstance(commands, list):
                raise _bad_rows()
            if commands := [c for c in map(self._command, commands) if c]:
                step["commands"] = commands
            # The Library's "how to check it" parts are edited in the control file; a save keeps them unchanged.
            if checks_text := entry.get("checks_json", ""):
                try:
                    checks = json.loads(checks_text)
                except (TypeError, ValueError):
                    raise _bad_rows()
                if not isinstance(checks, list):
                    raise _bad_rows()
                step["checks"] = checks
            if len(step) > 1 or step["do"]:
                steps.append(step)
        return steps


class ReferencesField(RowsField):
    """Rows of (label, link). Blank rows are dropped; the model checks the rest."""

    def parse(self, data):
        references = []
        for entry in data:
            entry = _row(entry)
            label, url = _text(entry.get("label", "")), _text(entry.get("url", ""))
            if label or url:
                references.append({"label": label, "url": url})
        return references


class ControlLinksField(RowsField):
    """Rows of (control, coverage, reason). Cleans to [(Control, coverage, reason)]."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.controls = {}

    def parse(self, data):
        links, errors, seen = [], [], set()
        for number, entry in enumerate(data, start=1):
            entry = _row(entry)
            ident = _text(entry.get("control", ""))
            coverage = _text(entry.get("coverage", Coverage.FULL))
            reason = _text(entry.get("rationale", ""))
            if not ident and not reason:
                continue
            if not ident:
                errors.append(f"Control {number}: pick a control.")
            elif ident not in self.controls:
                errors.append(f"Control {number}: {ident} isn't a published control you can link to.")
            elif ident in seen:
                errors.append(f"Control {number}: {ident} is already linked above.")
            elif coverage not in Coverage.values:
                errors.append(f"Control {number} ({ident}): choose full or partial coverage.")
            elif not reason:
                errors.append(f"Control {number} ({ident}): say why it covers this risk.")
            elif len(reason) > REASON_MAX:
                errors.append(f"Control {number} ({ident}): keep the reason under {REASON_MAX} characters.")
            else:
                seen.add(ident)
                links.append((self.controls[ident], coverage, reason))
        if errors:
            raise ValidationError(errors)
        return links


# Shared form behavior

def textarea_widget(rows=3):
    return forms.Textarea(attrs={"rows": rows})


class EditForm(BootstrapFormMixin, forms.Form):
    """Base: Bootstrap classes and help text (from the mixin) and model-level validation."""

    version_model = None
    # Model fields the form doesn't collect.
    model_exclude = list(WORKFLOW_FIELDS)
    # Form fields saved outside the version's own columns (links, many-to-many).
    link_fields = ()

    def __init__(self, *args, with_summary=False, **kwargs):
        super().__init__(*args, **kwargs)
        if "change_summary" in self.fields and not with_summary:
            del self.fields["change_summary"]

    def content_keys(self):
        return [name for name in self.fields if name != "change_summary" and name not in self.link_fields]

    def content(self):
        return {name: self.cleaned_data[name] for name in self.content_keys()}

    def clean(self):
        data = super().clean()
        if not self.errors and self.version_model is not None:
            self.check_model(data)
        return data

    def candidate_values(self, data):
        return {name: data[name] for name in self.content_keys() if name in data}

    def check_model(self, data):
        candidate = self.version_model(**self.candidate_values(data))
        try:
            candidate.full_clean(exclude=self.model_exclude)
        except ValidationError as error:
            for field, messages in error.message_dict.items():
                self.add_error(field if field in self.fields else None, messages)


CHANGE_SUMMARY = forms.CharField(
    label="What are you changing, and why?",
    max_length=500,
    help_text="One or two sentences for the reviewer.",
    widget=textarea_widget(rows=2),
)


class GovernedForm(EditForm):
    """Fields every governed page shares: title, owner role, review date, references and change summary."""

    title = forms.CharField(
        max_length=160,
        label="Title",
    )
    owner_role = forms.CharField(
        max_length=120,
        label="Owner role",
        help_text=OWNER_ROLE_HELP,
    )
    review_by = forms.DateField(
        label="Review by",
        help_text="When this must be reviewed again. Usually one year from now.",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    references = ReferencesField(label="References")
    change_summary = CHANGE_SUMMARY

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _default_review(self)


class ScopedForm(GovernedForm):
    """Fields shared by risks and controls. A new one also asks for its TRAC ID."""

    entity_model = None
    ident = forms.CharField(
        max_length=40,
        label="ID",
        help_text="The TRAC ID, for example CM-01. It can't be changed here later; change it in the content file.",
    )

    topic = forms.ModelChoiceField(
        queryset=Topic.objects.none(),
        label="Topic",
        empty_label="Select a topic",
    )
    stage = forms.ModelChoiceField(
        queryset=Stage.objects.none(),
        required=False,
        label="Stage",
        empty_label="No specific stage",
        help_text="Optional. Where this sits in the topic's lifecycle. The list changes when you pick a topic.",
        error_messages={"invalid_choice": "Pick a stage from the selected topic."},
    )
    theme = forms.ModelChoiceField(
        queryset=Theme.objects.none(),
        required=False,
        label="Theme",
        empty_label="No theme",
        help_text="Use a theme instead of a stage when this applies across the whole lifecycle.",
        error_messages={"invalid_choice": "Pick a theme from the selected topic."},
    )

    def __init__(self, *args, with_ident=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not with_ident:
            del self.fields["ident"]
        keep = self.initial.get("topic")
        active = Q(is_active=True)
        if keep:
            active |= Q(pk=getattr(keep, "pk", keep))
        self.fields["topic"].queryset = Topic.objects.filter(active)
        self.fields["topic"].widget.attrs.update(
            {
                "hx-get": reverse("rcm:topic_options"),
                "hx-trigger": "change",
                "hx-target": "#id_stage",
                "hx-swap": "innerHTML",
            }
        )
        topic_id = self.data.get("topic") if self.is_bound else getattr(keep, "pk", keep)
        try:
            topic_id = int(topic_id)
        except (TypeError, ValueError):
            topic_id = None
        self.fields["stage"].queryset = Stage.objects.filter(topic_id=topic_id)
        self.fields["theme"].queryset = Theme.objects.filter(topic_id=topic_id)

    def content_keys(self):
        return [name for name in super().content_keys() if name != "ident"]

    def clean_ident(self):
        ident = self.cleaned_data["ident"].strip()
        if not ID_PATTERN.match(ident):
            raise forms.ValidationError("Use letters, numbers, dashes, dots or underscores, up to 40 characters.")
        if self.entity_model.objects.filter(ident=ident).exists():
            raise forms.ValidationError(f"{ident} is already used. Check the content files for the right ID.")
        return ident


def _default_review(form):
    if not form.is_bound and not form.initial.get("review_by"):
        today = timezone.localdate()
        try:
            form.initial["review_by"] = today.replace(year=today.year + 1)
        except ValueError:
            form.initial["review_by"] = today.replace(year=today.year + 1, day=28)


# Controls

class ControlForm(ScopedForm):
    version_model = ControlVersion
    entity_model = Control
    link_fields = ("platforms",)

    title = forms.CharField(
        max_length=160,
        label="Title",
        help_text="A short name that says what the control does, for example: Quarterly review of user access.",
    )
    performer_role = forms.CharField(
        max_length=120,
        required=False,
        label="Performed by (role)",
        help_text="The role that does the work day to day, for example Database administrator.",
    )
    reviewer_role = forms.CharField(
        max_length=120,
        required=False,
        label="Reviewed by (role)",
        help_text="The role that checks the work, for example Application owner. Leave empty if nobody reviews it.",
    )
    nature = forms.ChoiceField(
        choices=[("", "Select")] + Nature.choices,
        label="Type",
        help_text="Preventive stops a problem before it happens. Detective finds a problem after it happened.",
    )
    method = forms.ChoiceField(
        choices=[("", "Select")] + Method.choices,
        label="How it is done",
        help_text="Manual is done by a person. Automated runs in a system. IT-dependent manual is done by a person using system reports.",
    )
    frequency = forms.ChoiceField(
        choices=[("", "Select")] + Frequency.choices,
        label="How often",
    )
    level = forms.ChoiceField(
        choices=levels.choices,
        initial=levels.default_key,
        label="Level",
        help_text="How important the control is. Pages show the first level by default and fold the rest under More controls.",
    )
    why = forms.CharField(
        label="Why you'd want this control",
        help_text="Two or three sentences on the benefit: the problem it prevents or catches.",
        widget=textarea_widget(rows=4),
    )
    applies_when = StatementsField(label="It fits when")
    steps = StepsField(label="How to build it")
    addresses = RiskIdsField(
        required=False,
        label="Risks it addresses",
        help_text="The risks this control helps with, one ID per line, for example air.ops.02. They come from the risk engine files, so the ID must exist there. Leave empty until the risks are mapped.",
        widget=textarea_widget(rows=3),
    )
    people_performer = forms.CharField(
        required=False,
        label="Choosing the performer",
        help_text="One note per line, for example: Has the access to rerun a job.",
        widget=textarea_widget(rows=3),
    )
    people_reviewer = forms.CharField(
        required=False,
        label="Choosing the reviewer",
        help_text="One note per line, for example: Doesn't operate the jobs.",
        widget=textarea_widget(rows=3),
    )
    people_small_team = forms.CharField(
        required=False,
        label="If the team is small",
        help_text="One line on what to do when no one is independent.",
    )
    categories = forms.MultipleChoiceField(
        choices=Category.choices,
        required=False,
        label="Categories",
        help_text="The parts of the technology stack and the shared services this control applies to.",
        widget=forms.CheckboxSelectMultiple,
    )
    platforms = forms.ModelMultipleChoiceField(
        queryset=Platform.objects.none(),
        required=False,
        label="Platforms",
        help_text="Hold Ctrl or Cmd to pick more than one. Leave empty if the control is not tied to a platform.",
        widget=forms.SelectMultiple(attrs={"size": 10}),
    )

    field_order = [
        "title", "topic", "stage", "theme", "owner_role", "performer_role", "reviewer_role",
        "nature", "method", "frequency", "level", "categories", "platforms", "why", "applies_when", "steps",
        "people_performer", "people_reviewer", "people_small_team", "addresses", "references", "change_summary",
    ]
    people_fields = {"people_performer": "performer", "people_reviewer": "reviewer", "people_small_team": "small_team"}

    def __init__(self, *args, kept_addresses=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.kept_addresses = set(kept_addresses)  # the risk IDs the control already has
        active = Platform.objects.filter(is_active=True)
        field = self.fields["platforms"]
        field.queryset = active
        field.widget.choices = platform_choices(active)

    def content_keys(self):
        return [name for name in super().content_keys() if name not in self.people_fields]

    def clean_addresses(self):
        """Each ID must be one the engine files have. An ID the control already had is let through, so an
        old link to a risk the engine has since dropped never stops an unrelated edit."""
        addresses = self.cleaned_data["addresses"]
        already = self.kept_addresses
        known = set(EngineRisk.objects.exclude(ident="").values_list("ident", flat=True))
        unknown = [a for a in addresses if a not in known and a not in already]
        if unknown:
            raise forms.ValidationError(
                f"Not in the risk engine files: {', '.join(unknown)}. Check the ID on the Engine risks page."
            )
        return addresses

    def choosing_people(self, data):
        """The "choosing people" notes the three people boxes hold; boxes left empty are left out."""
        people = {
            "performer": _lines(data.get("people_performer", "")),
            "reviewer": _lines(data.get("people_reviewer", "")),
            "small_team": data.get("people_small_team", "").strip(),
        }
        return {key: value for key, value in people.items() if value}

    def content(self):
        return {**super().content(), "choosing_people": self.choosing_people(self.cleaned_data)}

    def candidate_values(self, data):
        return {**super().candidate_values(data), "choosing_people": self.choosing_people(data)}


def platform_choices(platforms):
    """Option groups for a platform picker: each platform once, under the label of its first category."""
    grouped = {}
    for platform in platforms:
        grouped.setdefault(platform.primary_category, []).append((platform.pk, platform.name))
    return [(category.label, grouped[category.value]) for category in Category if category.value in grouped]


# Risks

class RiskForm(ScopedForm):
    version_model = RiskVersion
    entity_model = Risk
    link_fields = ("controls", "drivers")

    title = forms.CharField(
        max_length=160,
        label="Title",
        help_text="A short name for what could go wrong, for example: Leavers keep access after they go.",
    )
    statement = forms.CharField(
        label="Risk statement",
        help_text="What could go wrong, why it could happen, and what it would lead to.",
        widget=textarea_widget(rows=4),
    )
    in_sox_scope = forms.BooleanField(
        required=False,
        label="In SOX scope",
        help_text="Tick this if the risk affects financial reporting.",
    )
    controls = ControlLinksField(label="Controls that cover this risk")
    drivers = forms.ModelMultipleChoiceField(
        queryset=Driver.objects.none(),
        required=False,
        label="Drivers",
        help_text="Conditions that make this risk more likely. Hold Ctrl or Cmd to pick more than one.",
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )

    field_order = [
        "title", "topic", "stage", "theme", "owner_role", "in_sox_scope", "statement", "controls", "drivers",
        "references", "change_summary",
    ]

    def __init__(self, *args, linked_controls=(), **kwargs):
        super().__init__(*args, **kwargs)
        drivers = selectors.current_drivers()
        field = self.fields["drivers"]
        field.queryset = Driver.objects.filter(pk__in=[d.pk for d, _ in drivers])
        field.widget.choices = [(d.pk, f"{d.ident} {version.title}") for d, version in drivers]
        titles = {}
        for control, version in selectors.current_controls():
            titles[control.ident] = (control, version.title)
        self.control_choices = []
        for control in linked_controls:
            if control.ident not in titles:
                version = control.versions.order_by("-number").first()
                titles[control.ident] = (control, f"{version.title} (retired)")
        for ident in sorted(titles):
            self.control_choices.append((ident, f"{ident} {titles[ident][1]}"))
        self.fields["controls"].controls = {ident: pair[0] for ident, pair in titles.items()}
