"""Platform and category pages: guidance lines and the control patterns that answer each aspect question."""

from dataclasses import dataclass, field

from django.db.models import prefetch_related_objects

from apps.rcm.selectors import fold_pairs
from apps.rcm.shape import checks_of, commands_of

from .models import AspectQuestion, Guidance, Platform


def category_platforms(category):
    return Platform.objects.filter(categories__contains=[category], is_active=True)


def applicable_controls(controls, categories=(), platforms=()):
    """The (control, version) pairs from `controls` tagged with one of the categories or platforms."""
    platform_ids = {platform.pk for platform in platforms}
    prefetch_related_objects([version for _, version in controls], "platforms")  # no-op once fetched
    return [
        (control, version)
        for control, version in controls
        if set(categories).intersection(version.categories or [])
        or any(p.pk in platform_ids for p in version.platforms.all())
    ]


def current_guidance(**target):
    """The published guidance version for `category=<key>` or `platform=<Platform>`, or None."""
    guidance = Guidance.objects.filter(**target).first()
    return guidance.current() if guidance else None


def active_questions():
    return list(AspectQuestion.objects.select_related("topic").filter(topic__is_active=True))


@dataclass
class AspectRow:
    question: AspectQuestion
    line: str = ""
    controls: list = field(default_factory=list)  # controls at open levels, most important first
    more: list = field(default_factory=list)  # LevelGroups folded under "More controls"
    specifics: list = field(default_factory=list)  # (platform, line) for platforms with their own line here
    checks: list = field(default_factory=list)  # Check for each control, platform and audience with a "how to check it"

    @property
    def has_content(self):
        return bool(self.line or self.controls or self.more)


def aspect_rows(controls, questions, guidance=None):
    """One row per aspect question: the guidance line and the controls on the same topic.

    `questions` is active_questions(); pass the same list to every call on a page.
    """
    lines = guidance.line_map if guidance else {}
    rows = []
    for question in questions:
        shown, more = fold_pairs([(c, v) for c, v in controls if v.topic_id == question.topic_id])
        rows.append(AspectRow(question=question, line=lines.get(question.pk, ""), controls=shown, more=more))
    return rows


def add_platform_specifics(rows, platform_guidance):
    """Attach each platform's own line to the matching row, in the order the platforms are given.

    `platform_guidance` is a list of (platform, published guidance or None).
    """
    for platform, guidance in platform_guidance:
        lines = guidance.line_map if guidance else {}
        for row in rows:
            if lines.get(row.question.pk):
                row.specifics.append((platform, lines[row.question.pk]))
    return rows


@dataclass
class Check:
    """One control's "how to check it" on one platform for one audience, ready to show in the Library."""

    control: object
    version: object
    platform: Platform
    audience: str
    where: str
    good: list
    keep: str
    shows: list
    commands: list  # the control's commands for this platform and audience


def add_checks(rows, platforms):
    """Attach to each row the "how to check it" of its controls, for the platforms on the page.

    A control shows a check for a platform only when its steps have one; nothing to say means nothing drawn.
    """
    by_name = {platform.name: platform for platform in platforms}
    for row in rows:
        pairs = [*row.controls, *(pair for group in row.more for pair in group.items)]
        for control, version in pairs:
            for check in checks_of(version.steps):
                platform = by_name.get(check["platform"])
                if platform is None:
                    continue
                row.checks.append(Check(
                    control=control, version=version, platform=platform, audience=check["audience"],
                    where=check.get("where", ""), good=check.get("good", []), keep=check.get("keep", ""),
                    shows=check.get("shows", []),
                    commands=commands_of(version.steps, platform.name, check["audience"]),
                ))
        row.checks.sort(key=lambda found: (found.platform.name, found.control.ident, found.audience))
    return rows
