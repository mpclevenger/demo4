"""Queries for My system: the platforms a visitor can pick and which published guidance covers which risk area."""

from apps.core.versioning import current_versions
from apps.platforms.models import Guidance, Platform


def active_platforms():
    return list(Platform.objects.filter(is_active=True))


def published_guidance_lines():
    """Which risk areas (aspect question ids) the published guidance writes about, from one query.

    Returns {"category": {key: {question id, ...}}, "platform": {platform id: {question id, ...}}}.
    Drafts and proposals never count: only what visitors can read.
    """
    found = {"category": {}, "platform": {}}
    for version in current_versions(Guidance):
        guidance = version.entity
        target = ("platform", guidance.platform_id) if guidance.platform_id else ("category", guidance.category)
        found[target[0]][target[1]] = set(version.line_map)
    return found
