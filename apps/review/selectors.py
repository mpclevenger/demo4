"""Finds everything waiting for review, with readable names, for the Review queue."""

from django.apps import apps

from apps.core.versioning import STATUS_WORDS, GovernedVersion, Status


def versions_in_review():
    """Every governed version waiting for approval, oldest submission first."""
    versions = []
    for model in apps.get_models():
        if issubclass(model, GovernedVersion):
            versions += model.objects.filter(status=Status.IN_REVIEW).select_related("entity", "proposed_by")
    return sorted(versions, key=lambda version: version.submitted_at)


def type_label(version):
    return version._meta.get_field("entity").related_model._meta.verbose_name.capitalize()


def view_url(version):
    entity = version.entity
    if hasattr(entity, "get_absolute_url"):
        return f"{entity.get_absolute_url()}?version={version.number}"
    return None


def item_name(version):
    """The version's own title, question or name; the entity string when it has none."""
    for field in ("title", "question", "name"):
        value = getattr(version, field, "")
        if value:
            return value
    return str(version.entity)


def versions_proposed_by(user):
    """Every governed version this person proposed, newest first, with the name and page the list needs."""
    versions = []
    for model in apps.get_models():
        if issubclass(model, GovernedVersion):
            versions += model.objects.filter(proposed_by=user).select_related("entity")
    versions.sort(key=lambda version: version.proposed_at, reverse=True)
    return [
        {"version": version, "name": item_name(version), "type": type_label(version), "url": view_url(version),
         "status": STATUS_WORDS[version.status]}
        for version in versions
    ]
