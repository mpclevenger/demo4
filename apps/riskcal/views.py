"""The risk and control calendar page, and the pages for proposing, reading and changing an event.

Events come from content/calendar/events.yaml and, once Tech Risk has approved them, from the database.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.vary import vary_on_headers

from apps.accounts.permissions import (
    can_propose,
    can_see_version,
    can_view,
    can_view_history,
    permission_required_for,
)
from apps.core import versioning as v
from apps.core.retire import retire_url
from apps.ui.bands import make_band

from . import events_file, month, schedule, services, site_events, work_items
from .forms import EventForm, ItemForm
from .models import CalendarEvent, WorkItem

view_allowed = permission_required_for(can_view)
propose_allowed = permission_required_for(can_propose)
TITLE = "Risk and control calendar"
ADD_TITLE = "Add an event"


def _crumbs(last):
    return [("Home", "/"), (TITLE, reverse("riskcal:index")), (last, None)]


@view_allowed
@vary_on_headers("HX-Request")
def index(request):
    """One month of the calendar. Previous, Next and the type chips send only the month part when HTMX asks."""
    today = timezone.localdate()
    cal = site_events.add_site_events(events_file.read_calendar())
    shown_month = month.parse_month(request.GET.get("month"), today)
    filters = work_items.read_filters(request.GET)
    work = work_items.panel(filters, *month.month_days(shown_month))
    context = month.build(
        cal, shown_month, month.chosen_types(request.GET.getlist("type"), cal.types), today,
        extra=filters.query(), markers=work["work_markers"])
    context.update(work)
    context.update({
        "cal": cal,
        "nav_active": "calendar",
        "band": make_band(
            [("Home", "/"), (TITLE, None)], title=TITLE,
            summary="Dates that matter for risks and controls. Select an event to see its details.",
            action=(ADD_TITLE, reverse("riskcal:new"))),
    })
    template = "riskcal/_month.html" if request.headers.get("HX-Request") else "riskcal/index.html"
    return render(request, template, context)


def _form_page(request, form, heading, cancel_url, intro, template="riskcal/event_form.html", adding=""):
    """The page that holds a form, with its heading, a way back and a short intro. `adding` marks a new event or item."""
    context = {
        "nav_active": "calendar", "form": form, "heading": heading, "cancel_url": cancel_url, "intro": intro, "adding": adding,
        "band": make_band(_crumbs(heading), title=heading),
    }
    return render(request, template, context)


@view_allowed
def event_new(request):
    """The short form for proposing an event. A valid answer is sent to Tech Risk and shows nowhere until they approve it."""
    types = events_file.read_calendar().types
    form = EventForm(request.POST or None, types=types)
    if request.method == "POST" and form.is_valid():
        event, version = services.propose_event(request.user, **form.content())
        messages.success(request, "Thanks. Your event was sent to Tech Risk. It shows on the calendar once they approve it.")
        return redirect(f"{event.get_absolute_url()}?version={version.number}")
    intro = "Fill in the lines below. Tech Risk looks at every new event before it shows on the calendar."
    return _form_page(request, form, ADD_TITLE, reverse("riskcal:index"), intro, adding="event")


def _shown_version(request, event):
    """The version to show: the one asked for, else the live one, else the latest proposal the user may see. 404 if none."""
    if "version" in request.GET:
        try:
            wanted = event.versions.filter(number=int(request.GET["version"])).first()
        except ValueError:
            wanted = None
        if wanted is None or not can_see_version(request.user, wanted):
            raise Http404
        return wanted
    for version in (event.current(), *event.versions.order_by("-number")):
        if version is not None and can_see_version(request.user, version):
            return version
    raise Http404


def _facts(version, types):
    """The version's lines in words, for the page."""
    labels = {t.key: t.label for t in types}
    last = version.end or version.date
    facts = {
        "when": schedule.describe_days(version.date, last),
        "type": labels.get(version.type, version.type),
    }
    event, _ = site_events.event_from(version, types)
    facts["repeat_note"] = schedule.repeat_note(event) if event and event.repeats else ""
    return facts


def _status_word(version, retired):
    """The version's state in words (Proposed until Tech Risk decides); a published retirement, or any version of a retired event, reads Retired."""
    if version.status == v.Status.PUBLISHED and (version.kind == v.Kind.RETIRE or retired):
        return "Retired"
    return v.STATUS_WORDS[version.status]


@view_allowed
def event_detail(request, pk):
    """One event as proposed or published, with the buttons for its next step."""
    event = get_object_or_404(CalendarEvent, pk=pk)
    version = _shown_version(request, event)
    types = events_file.read_calendar().types
    proposal = event.open_proposal()
    is_hidden = proposal is not None and (proposal.pk == version.pk or not can_see_version(request.user, proposal))
    waiting = None if is_hidden else proposal
    retired = event.is_retired()
    context = {
        "nav_active": "calendar", "event": event, "version": version, "facts": _facts(version, types), "waiting": waiting,
        "retired": retired, "status_word": _status_word(version, retired), "wf_type_id": ContentType.objects.get_for_model(event).pk,
        "can_change": can_propose(request.user) and not retired and proposal is None,
        "retire_url": retire_url(event) if can_propose(request.user) else None,
        "can_see_history": can_view_history(request.user),
        "band": make_band(_crumbs(version.title), title=version.title),
    }
    return render(request, "riskcal/event_detail.html", context)


@propose_allowed
def event_edit(request, pk):
    """Tech Risk changes an approved event (or the user's own withdrawn draft). The change goes to review like a new one."""
    event = get_object_or_404(CalendarEvent, pk=pk)
    back = event.get_absolute_url()
    open_ = event.open_proposal()
    own_draft = open_ is not None and open_.status == v.Status.DRAFT and open_.proposed_by_id == request.user.pk
    if event.is_retired():
        messages.error(request, "This event is retired, so it can't be changed.")
        return redirect(back)
    if open_ is not None and not own_draft:
        messages.error(request, "A change to this event is already waiting. Changes go one at a time, so wait until it is approved or sent back.")
        return redirect(f"{back}?version={open_.number}")
    types = events_file.read_calendar().types
    start = open_ if own_draft else event.current() or event.versions.order_by("-number").first()
    form = EventForm(request.POST or None, initial=EventForm.initial_from(start), types=types, with_summary=True)
    if request.method == "POST" and form.is_valid():
        content = form.content()
        summary = form.cleaned_data["change_summary"]
        try:
            version = services.propose_edit(event, request.user, summary, **content)
        except ValidationError as problem:
            form.add_error(None, problem.messages)
        else:
            messages.success(request, "Your change was sent for approval. The calendar keeps showing the current event until it is approved.")
            return redirect(f"{back}?version={version.number}")
    return _form_page(request, form, f"Change {event}", back, "Change the lines below. The calendar keeps showing the current event until Tech Risk approves the change.")


# In progress items: controls and guidance on the way. Anyone may propose one or a change; Tech Risk approves.

ITEM_ADD_TITLE = "Add work in progress"
ITEM_INTRO = "Fill in the lines below. Tech Risk looks at it before it shows on the calendar."


def _controls():
    """[(TRAC ID, topic)] for every live TRAC control, for the form's list."""
    from apps.rcm.models import Control

    return sorted(((version.entity.ident, version.topic) for version in v.current_versions(Control)), key=lambda pair: pair[0])


@view_allowed
def items(request):
    """Every item on the In progress list, 10 to a page, with the same filters as the calendar."""
    filters = work_items.read_filters(request.GET)
    picked = work_items.chosen(work_items.live_items(), filters)
    page = Paginator([work_items.card(version) for version in picked], work_items.SHOWN_IN_PANEL).get_page(request.GET.get("page"))
    context = {
        "nav_active": "calendar", "page": page, "work_filters": filters, "filter_query": urlencode(filters.query()),
        "band": make_band(_crumbs("In progress"), title="In progress",
                          summary="Controls and guidance on the way, with the date each team expects to go live.",
                          action=("Propose an item", reverse("riskcal:item_new"))),
    }
    return render(request, "riskcal/item_list.html", context)


@view_allowed
def item_new(request):
    """The short form for proposing an In progress item. It shows nowhere until Tech Risk approves it."""
    form = ItemForm(request.POST or None, controls=_controls())
    if request.method == "POST" and form.is_valid():
        item, version = services.propose_item(request.user, **form.content())
        messages.success(request, "Thanks. Your item was sent to Tech Risk. It shows on the calendar once they approve it.")
        return redirect(f"{item.get_absolute_url()}?version={version.number}")
    return _form_page(request, form, ITEM_ADD_TITLE, reverse("riskcal:index"), ITEM_INTRO, "riskcal/item_form.html", adding="item")


@view_allowed
def item_detail(request, pk):
    """One In progress item as proposed or published, with the buttons for its next step. Its date history is
    kept in the item's history (for Tech Risk and auditors) but not listed here (owner, 16 Nov 2026)."""
    item = get_object_or_404(WorkItem, pk=pk)
    version = _shown_version(request, item)
    proposal = item.open_proposal()
    is_hidden = proposal is not None and (proposal.pk == version.pk or not can_see_version(request.user, proposal))
    retired = item.is_retired()
    context = {
        "nav_active": "calendar", "event": item, "version": version, "card": work_items.card(version),
        "waiting": None if is_hidden else proposal, "retired": retired, "status_word": _status_word(version, retired),
        "wf_type_id": ContentType.objects.get_for_model(item).pk,
        "can_change": not retired and proposal is None and version.status == v.Status.PUBLISHED,
        "retire_url": retire_url(item) if can_propose(request.user) else None,
        "can_see_history": can_view_history(request.user),
        "band": make_band(_crumbs(version.title), title=version.title),
    }
    return render(request, "riskcal/item_detail.html", context)


@view_allowed
def item_edit(request, pk):
    """Anyone proposes a change to a published item (a new date, Live, a run without an issue). It goes to review."""
    item = get_object_or_404(WorkItem, pk=pk)
    back = item.get_absolute_url()
    current = item.current()
    if current is None or item.is_retired() or item.open_proposal() is not None:
        messages.error(request, "This item can't be changed right now. A change may already be waiting for Tech Risk.")
        return redirect(back)
    form = ItemForm(request.POST or None, initial=ItemForm.initial_from(current), controls=_controls(), with_summary=True)
    if request.method == "POST" and form.is_valid():
        try:
            version = services.propose_item_change(item, request.user, form.cleaned_data["change_summary"], **form.content())
        except ValidationError as problem:
            form.add_error(None, problem.messages)
        else:
            messages.success(request, "Your change was sent to Tech Risk. The calendar keeps showing the current item until it is approved.")
            return redirect(f"{back}?version={version.number}")
    intro = "Change the lines below. The calendar keeps showing the current item until Tech Risk approves the change."
    return _form_page(request, form, f"Change {item}", back, intro, "riskcal/item_form.html")
