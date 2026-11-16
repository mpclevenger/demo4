"""The diagram pages: the list, one diagram with its picture and links, and the download of the original file.

Diagrams come from content/diagrams/diagrams.yaml. With no file there, the list says there are no diagrams yet.
"""

from django.http import FileResponse, Http404
from django.shortcuts import render
from django.urls import reverse

from apps.accounts.permissions import can_view, permission_required_for
from apps.ui.bands import make_band

from . import diagrams_file, register, svg

view_allowed = permission_required_for(can_view)
TITLE = "Diagrams"
SUMMARY = "Pictures of how platforms work and how our own setup is joined up. Red and blue bubbles link to the risks and controls."
PROPOSED_NOTE = "Proposed: written by Tech Risk, not in TRAC yet."


def _crumbs(title=None):
    """Library > Diagrams, and the diagram's own title on its page."""
    library = ("Library", reverse("core:library"))
    if title is None:
        return [library, (TITLE, None)]
    return [library, (TITLE, reverse("diagrams:index")), (title, None)]


@view_allowed
def index(request):
    found = diagrams_file.read_diagrams()
    sections = [
        {"kind": kind, "label": label, "diagrams": [_card(d) for d in found.of_kind(kind)]}
        for kind, label in diagrams_file.KINDS.items()
    ]
    context = {
        "nav_active": "library",
        "band": make_band(_crumbs(None), title=TITLE, summary=SUMMARY),
        "sections": [s for s in sections if s["diagrams"]],
        "has_problems": bool(found.problems),
    }
    return render(request, "diagrams/index.html", context)


def _card(diagram):
    """One diagram on the list page: the diagram and the address of its page."""
    return {"diagram": diagram, "url": reverse("diagrams:detail", args=[diagram.name])}


def _linked(picture):
    """The controls and risks the picture links to, each with its title and address; unknown IDs are marked."""
    controls, risks = register.titles_in_files()
    wanted = {(link.kind, link.ident) for link in picture.links}
    if any(ident not in (controls if kind == "controls" else risks) for kind, ident in wanted):
        site_controls, site_risks = register.titles_on_site()
        controls, risks = {**site_controls, **controls}, {**site_risks, **risks}
    rows = {"controls": [], "risks": []}
    for link in picture.links:
        titles = controls if link.kind == "controls" else risks
        rows[link.kind].append({
            "ident": link.ident, "title": titles.get(link.ident, ""), "known": link.ident in titles,
            "url": reverse("rcm:control" if link.kind == "controls" else "rcm:risk", args=[link.ident]),
        })
    return rows


@view_allowed
def detail(request, name):
    diagram = diagrams_file.read_diagrams().named(name)
    if diagram is None:
        raise Http404
    picture = svg.read_picture(diagram.path)
    linked = _linked(picture)
    context = {
        "nav_active": "library",
        "diagram": diagram,
        "band": make_band(_crumbs(diagram.title), title=diagram.title, summary=diagram.intro),
        "picture": picture,
        "controls": linked["controls"],
        "risks": linked["risks"],
        "proposed_note": PROPOSED_NOTE,
        "download_url": reverse("diagrams:download", args=[diagram.name]),
    }
    return render(request, "diagrams/detail.html", context)


@view_allowed
def download(request, name):
    """The original .drawio.svg file, to open and edit in draw.io."""
    diagram = diagrams_file.read_diagrams().named(name)
    if diagram is None or not diagram.path.is_file():
        raise Http404
    return FileResponse(diagram.path.open("rb"), as_attachment=True, filename=diagram.file, content_type="image/svg+xml")
