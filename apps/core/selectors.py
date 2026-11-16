"""What the site search can look through: published, current content only, never drafts.

Each source is read with one or two queries however much content there is, then
turned into plain SearchItem objects (see search.py for the matching rules).
"""

from django.db.models import prefetch_related_objects
from django.urls import reverse

from apps.platforms.categories import Category
from apps.platforms.models import Guidance, Platform
from apps.rcm.selectors import current_controls, current_risks
from apps.topics.models import Topic
from apps.wiki.selectors import current_pages

from .search import SearchItem, plain_text
from .versioning import current_versions


def _step_text(step):
    """What a step says that a visitor might search for: the lines, the evidence and the command notes (never the code)."""
    evidence = step.get("evidence", {})
    return [
        step.get("do", ""), step.get("how", ""), *step.get("weigh", []), step.get("policy", ""),
        evidence.get("keep", ""), *evidence.get("shows", []),
        *(command.get("note", "") for command in step.get("commands", [])),
    ]


def _people_text(people):
    return [*people.get("performer", []), *people.get("reviewer", []), people.get("small_team", "")]


def guide_items():
    return [
        SearchItem("guide", version.title, page.get_absolute_url(), plain_text(version.body), pill=version.section)
        for page, version in current_pages()
    ]


def control_items():
    items = []
    for control, version in current_controls():
        text = [
            version.why, *(version.applies_when or []),
            *(part for step in version.steps or [] for part in _step_text(step)),
            *_people_text(version.choosing_people or {}),
        ]
        items.append(SearchItem(
            "control", f"{control.ident} {version.title}", control.get_absolute_url(), plain_text(" ".join(text)),
            pill=control.ident,
        ))
    return items


def risk_items():
    return [
        SearchItem("risk", f"{risk.ident} {version.title}", risk.get_absolute_url(), plain_text(version.statement), pill=risk.ident)
        for risk, version in current_risks()
    ]


def library_items():
    """One entry per category and per active platform, with their published guidance lines."""
    lines_for = {}
    versions = current_versions(Guidance)
    prefetch_related_objects(versions, "entity__platform")
    for version in versions:
        text = [version.intro, *(line["text"] for line in version.lines)]
        guidance = version.entity
        key = ("platform", guidance.platform_id) if guidance.platform_id else ("category", guidance.category)
        lines_for[key] = plain_text(" ".join(text))
    items = []
    for category in Category:
        text = " ".join([category.heading, lines_for.get(("category", category.value), "")])
        items.append(SearchItem(
            "library", category.label, reverse("platforms:category", args=[category.value]), plain_text(text), pill="Category"
        ))
    for platform in Platform.objects.filter(is_active=True):
        url = platform.get_absolute_url()
        if not url:
            continue
        text = " ".join([platform.summary, lines_for.get(("platform", platform.pk), "")])
        items.append(SearchItem("library", platform.name, url, plain_text(text), pill="Platform"))
    return items


def topic_items():
    return [
        SearchItem("topic", topic.name, topic.get_absolute_url(), plain_text(topic.summary), pill="Topic")
        for topic in Topic.objects.filter(is_active=True)
    ]


def search_items():
    """Everything the search can find, as one list (about ten queries in total)."""
    return guide_items() + control_items() + risk_items() + library_items() + topic_items()
