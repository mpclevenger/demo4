"""Proposing, changing and retiring a calendar event, through the same draft, review and publish steps as other items.

Anyone who can read TRAC may propose a new event. The engine's own `create_entity` is for Tech Risk only, so a new
event is created here and then submitted at once (submitting needs only that you are the proposer). Changing or
retiring an approved event is for Tech Risk, with the engine's `propose_change` and `propose_retirement`.
"""

from django.db import transaction

from apps.core import versioning as v

from .models import CalendarEvent, CalendarEventVersion, WorkItem, WorkItemVersion


@transaction.atomic
def propose_event(user, **content):
    """Save a new event as a proposal and send it to Tech Risk. Returns (event, version); the version is in review."""
    event = CalendarEvent.objects.create(created_by=user)
    version = CalendarEventVersion.objects.create(entity=event, number=1, proposed_by=user, **content)
    v.version_transitioned.send(
        sender=CalendarEventVersion, version=version, from_status=None, to_status=v.Status.DRAFT, user=user, comment="")
    return event, v.submit(version, user)


@transaction.atomic
def propose_edit(event, user, change_summary="", **content):
    """Send a change to an event to Tech Risk. Uses the user's own draft if they have one. Returns the version in review."""
    draft = event.open_proposal()
    if draft is not None and draft.status == v.Status.DRAFT and draft.proposed_by_id == user.pk:
        version = v.update_draft(draft, user, change_summary=change_summary, **content)
    else:
        version = v.propose_change(event, user, change_summary, **content)
    return v.submit(version, user)


# In progress items. Anyone who can read TRAC may propose one, or a change to one (owner, 16 Nov 2026: the owning
# team keeps its item up to date; Tech Risk approves each change in the review queue, which is where it spot checks).

@transaction.atomic
def propose_item(user, **content):
    """Save a new In progress item as a proposal and send it to Tech Risk. Returns (item, version in review)."""
    item = WorkItem.objects.create(created_by=user)
    version = WorkItemVersion.objects.create(entity=item, number=1, proposed_by=user, **content)
    v.version_transitioned.send(
        sender=WorkItemVersion, version=version, from_status=None, to_status=v.Status.DRAFT, user=user, comment="")
    return item, v.submit(version, user)


@transaction.atomic
def propose_item_change(item, user, change_summary="", **content):
    """Send a change to an item to Tech Risk. Changes go one at a time. Returns the version in review."""
    WorkItem.objects.select_for_update().get(pk=item.pk)
    if item.open_proposal() is not None:
        raise v.TransitionNotAllowed("A change to this item is already waiting for Tech Risk.")
    if item.is_retired():
        raise v.TransitionNotAllowed("This item is retired.")
    number = (item.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    version = WorkItemVersion.objects.create(
        entity=item, number=number, proposed_by=user, change_summary=change_summary, **content)
    v.version_transitioned.send(
        sender=WorkItemVersion, version=version, from_status=None, to_status=v.Status.DRAFT, user=user, comment="")
    return v.submit(version, user)
