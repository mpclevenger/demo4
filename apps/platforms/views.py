"""Library pages: one page per category, where readers switch on a platform to add its specifics.

The Library is core:library; the front page is core:home. Old platform addresses open the platform's main category page.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify

from apps.accounts import permissions
from apps.diagrams.diagrams_file import diagrams_for_platform
from apps.pathfinder import answers as my_system
from apps.rcm.selectors import current_controls
from apps.ui.bands import make_band
from apps.wiki import selectors as wiki_selectors

from . import audience as audiences
from . import selectors
from .categories import CATEGORY_KEYS, Category, group_title
from .models import Platform

can_view = permissions.permission_required_for(permissions.can_view)


def _library_crumbs(category):
    group = group_title(category)
    return [("Library", reverse("core:library")), (group, f"{reverse('core:library')}#{slugify(group)}")]


@can_view
def index(request):
    return redirect("core:library")


@can_view
def category(request, key):
    if key not in CATEGORY_KEYS:
        raise Http404
    category = Category(key)
    guidance = selectors.current_guidance(category=key)
    members = list(selectors.category_platforms(key).select_related("runs_on"))
    chosen = _chosen_platforms(request)
    selected = [p.slug for p in members if p.slug in chosen]
    controls = selectors.applicable_controls(current_controls(), categories=[key], platforms=members)
    edit_url = reverse("platforms:guidance_edit", kwargs={"key": key})
    platform_guidance = [(p, selectors.current_guidance(platform=p)) for p in members]
    rows = selectors.add_platform_specifics(
        selectors.aspect_rows(controls, selectors.active_questions(), guidance), platform_guidance
    )
    rows = selectors.add_checks(rows, members)
    audience = audiences.chosen_key(request)
    context = {
        "nav_active": "library",
        "category": category,
        "band": make_band(
            [*_library_crumbs(category), (category.label, None)],
            title=category.label,
            summary=guidance.intro if guidance else "",
            action=_edit_button(request, edit_url),
        ),
        "toggles": [
            {"platform": p, "selected": p.slug in selected, "url": _toggle_url(key, selected, p.slug)}
            for p in members
        ],
        "panels": _platform_panels(request, platform_guidance, rows, selected),
        "selected": selected,
        "audience": audience,
        "audience_toggles": _audience_toggles(request, audience),
        "rows": rows,
        "references": guidance.references if guidance else [],
    }
    return render(request, "platforms/category.html", context)


def _chosen_platforms(request):
    """The platform slugs to switch on: the ones in the address, else the visitor's platforms from My system.

    A choice made on the page always wins, including switching every pill off (an empty `platform=`).
    """
    if "platform" in request.GET:
        return request.GET.getlist("platform")
    return my_system.platform_slugs(request)


def _toggle_url(key, selected, slug):
    """The page address with one platform switched on or off (used when scripts are off).

    With every pill off the address keeps an empty `platform=`, so the visitor's own platforms stay off.
    """
    chosen = [s for s in selected if s != slug] if slug in selected else [*selected, slug]
    query = "&".join(f"platform={s}" for s in chosen) or "platform="
    return reverse("platforms:category", args=[key]) + f"?{query}"


def _audience_toggles(request, chosen):
    """The two audience pills: each with its name, one-line "who you are", and the address that switches it
    on (or off, if it is the one chosen). The platforms chosen on the page stay in the address."""
    toggles = []
    for name, key in audiences.KEYS.items():
        query = request.GET.copy()
        query.pop("audience", None)
        if chosen != key:
            query["audience"] = key
        toggles.append({
            "name": name, "key": key, "selected": chosen == key, "who": audiences.WHO_YOU_ARE[name],
            "url": "?" + query.urlencode() if query else request.path,
        })
    return toggles


def _platform_panels(request, platform_guidance, rows, selected):
    """One short "about this platform" panel per platform on the page: intro, facts, documentation, guides."""
    guides = _guides_by_platform()
    panels = []
    for platform, guidance in platform_guidance:
        panels.append({
            "platform": platform,
            "selected": platform.slug in selected,
            "categories": [(Category(key), platform.url_in(key)) for key in platform.categories],
            "intro": guidance.intro if guidance else "",
            "references": guidance.references if guidance else [],
            "guides": guides.get(platform.pk, []),
            "has_specifics": any(p.pk == platform.pk for row in rows for p, _ in row.specifics),
            "edit": _edit_button(request, reverse("platforms:guidance_edit", kwargs={"slug": platform.slug})),
            "diagrams": diagrams_for_platform(platform.name),
        })
    return panels


def _edit_button(request, edit_url):
    """The band's "Edit guidance" button, for people who can propose changes."""
    return ("Edit guidance", edit_url) if permissions.can_propose(request.user) else None


def _guides_by_platform():
    """Published wiki pages, grouped by the platform they are about."""
    grouped = {}
    for page, version in wiki_selectors.current_pages():
        if version.platform_id:
            grouped.setdefault(version.platform_id, []).append(
                {"title": version.title, "section": version.section, "url": page.get_absolute_url()}
            )
    return grouped


@can_view
def detail(request, slug):
    """Platforms no longer have their own page: open the main category page with the platform switched on."""
    platform = get_object_or_404(Platform, slug=slug, is_active=True)
    return redirect(platform.get_absolute_url())
