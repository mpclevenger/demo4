"""Read-side pages: the RCM explorer and the engine risks list (Tech Risk only), the control, risk and driver pages,
and the published controls list (`controls_json`) that the Risk site reads."""

from django.db.models import Max
from django.http import HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers

from apps.accounts import permissions
from apps.core import detail
from apps.core.versioning import Status
from apps.pathfinder import answers
from apps.platforms.categories import Category
from apps.platforms.models import Platform
from apps.topics.models import Topic
from apps.ui.bands import make_band

from . import levels, selectors
from .models import Control, ControlVersion, Driver, EngineRisk, Risk

COVERAGE_CHOICES = [("covered", "Covered"), ("partial", "Partial"), ("unmapped", "Unmapped")]
COVERAGE_LABELS = dict(COVERAGE_CHOICES)

EVIDENCE_GUIDE = "what-good-evidence-looks-like"  # the guide the "How to build it" card links to; the page may not exist yet

can_view = permissions.permission_required_for(permissions.can_view)
tech_risk_only = permissions.permission_required_for(permissions.is_tech_risk)


def _matches(text, ident, title):
    text = text.strip().lower()
    return not text or text in ident.lower() or text in title.lower()


class Scope:
    """Topic, stage and theme lookups so rows can show 'Topic / Stage or theme' without per-row queries."""

    def __init__(self):
        self.topics = list(Topic.objects.filter(is_active=True).prefetch_related("stages", "themes"))
        self.topic_by_id = {t.pk: t for t in self.topics}
        self.stage_by_id = {s.pk: s for t in self.topics for s in t.stages.all()}
        self.theme_by_id = {th.pk: th for t in self.topics for th in t.themes.all()}

    def label(self, version):
        topic = self.topic_by_id.get(version.topic_id)
        stage = self.stage_by_id.get(version.stage_id) or self.theme_by_id.get(version.theme_id)
        return " / ".join(part.name for part in (topic, stage) if part)

    def parse(self, params):
        topic = next((t for t in self.topics if t.slug == params.get("topic")), None)
        stage = None
        if topic:
            stage = next((s for s in topic.stages.all() if str(s.pk) == params.get("stage")), None)
        return topic, stage


def _topic_url(topic):
    return reverse("topics:detail", args=[topic.slug])


def _strip_stages(topic, base):
    """Lifecycle strip links; `base` is a URL ending in "?" or "&" that `stage=<id>` is appended to."""
    return [{"name": s.name, "url": f"{base}stage={s.pk}"} for s in topic.stages.all()]


def _scope_crumbs(topic, stage_or_theme):
    """Item pages are readable by everyone, so their topic links go to the topic page, not the explorer."""
    crumbs = [("Home", "/")]
    if topic:
        crumbs.append((topic.name, _topic_url(topic) if stage_or_theme else None))
        if stage_or_theme:
            crumbs.append((stage_or_theme.name, None))
    return crumbs


def _item_band(topic, stage, theme=None):
    """Band for an item at a stage, or under a theme (the strip then has no active stage)."""
    return make_band(
        _scope_crumbs(topic, stage or theme),
        icon=topic.icon if topic else None,
        stages=_strip_stages(topic, f"{_topic_url(topic)}?") if topic else [],
        active_stage=stage.name if stage else None,
    )


def _resolve(request, model, ident):
    return detail.resolve_version(request, get_object_or_404(model, ident=ident))


def _new_buttons(request):
    if not permissions.can_propose(request.user):
        return []
    return [
        ("New control", reverse("rcm:control_new")),
        ("New risk", reverse("rcm:risk_new")),
    ]


def _my_platform_names(request):
    """Names of the platforms the visitor picked on My system. No query unless they have picked some."""
    slugs = answers.platform_slugs(request)
    if not slugs:
        return set()
    return set(Platform.objects.filter(slug__in=slugs, is_active=True).values_list("name", flat=True))


def _commands(commands, my_platforms):
    """A step's commands, each marked open when it is for one of the visitor's platforms or is the only one."""
    return [{**c, "is_open": len(commands) == 1 or c["platform"] in my_platforms} for c in commands]


def _build_steps(steps, my_platforms):
    return [{**step, "commands": _commands(step.get("commands", []), my_platforms)} for step in steps]


def _control_page_context(request, version):
    return {
        "key_label": levels.label(version.level) if version.level == levels.first_key() else "",
        "steps": _build_steps(version.steps or [], _my_platform_names(request)),
        "evidence_guide_url": reverse("wiki:page", args=[EVIDENCE_GUIDE]),
    }


# Explorer

def _explorer_filters(params, scope, drivers):
    topic, stage = scope.parse(params)
    coverage = params.get("coverage", "")
    driver = params.get("driver", "")
    return {
        "topic": topic,
        "stage": stage,
        "coverage": coverage if coverage in COVERAGE_LABELS else "",
        "driver": driver if driver in {d.ident for d, _ in drivers} else "",
        "level": params.get("level") if params.get("level") in levels.keys() else "",
        "sox": params.get("sox") == "1",
        "q": params.get("q", "").strip(),
        "view": "controls" if params.get("view") == "controls" else "risks",
    }


def _scope_ok(version, f):
    if f["topic"] and version.topic_id != f["topic"].pk:
        return False
    if f["stage"] and version.stage_id != f["stage"].pk:
        return False
    return True


def _control_passes(version, f):
    """Topic, stage and level filters for a control (the search text is checked by the caller)."""
    if not _scope_ok(version, f):
        return False
    return not (f["level"] and version.level != f["level"])


def _risk_rows(matrix, f, scope):
    rows = []
    for row in matrix:
        version = row.version
        if not _scope_ok(version, f) or (f["sox"] and not version.in_sox_scope):
            continue
        if f["coverage"] and row.coverage != f["coverage"]:
            continue
        if f["driver"] and not any(d["driver"].ident == f["driver"] for d in row.drivers):
            continue
        controls = row.controls
        if f["level"]:
            controls = [c for c in controls if c["version"].level == f["level"]]
            if not controls:
                continue
        if f["q"] and not (
            _matches(f["q"], row.risk.ident, version.title)
            or any(_matches(f["q"], c["control"].ident, c["version"].title) for c in row.controls)
        ):
            continue
        rows.append({"row": row, "controls": controls, "scope": scope.label(version)})
    return rows


def _control_rows(controls, matrix, f, scope):
    engine_by_ident = {risk.ident: risk for risk in EngineRisk.objects.exclude(ident="")}
    risks_by_control = {}
    for row in matrix:
        for link in row.controls:
            risks_by_control.setdefault(link["control"].pk, []).append((row, link["coverage"]))
    rows = []
    for control, version in controls:
        if not _control_passes(version, f):
            continue
        risks = risks_by_control.get(control.pk, [])
        if f["q"] and not (
            _matches(f["q"], control.ident, version.title)
            or any(_matches(f["q"], r.risk.ident, r.version.title) for r, _ in risks)
        ):
            continue
        rows.append(
            {
                "control": control, "version": version, "risks": risks, "scope": scope.label(version),
                "level_label": levels.label(version.level),
                "engine_addresses": selectors.engine_addresses(version.addresses, engine_by_ident),
            }
        )
    # The explorer is a full register (nothing folded); the most important level comes first.
    return selectors.sort_by_level(rows, lambda row: row["version"].level)


def _unlinked_rows(unlinked, f):
    return [
        {"control": control, "version": version}
        for control, version in unlinked
        if _control_passes(version, f) and _matches(f["q"], control.ident, version.title)
    ]


def _explorer_summary(matrix, controls, unlinked):
    return {
        "risks": len(matrix),
        "controls": len(controls),
        "unmapped": sum(1 for row in matrix if row.coverage == "unmapped"),
        "unlinked": len(unlinked),
    }


def _explorer_band(f):
    """Breadcrumbs and, when a topic is picked, its icon and lifecycle strip."""
    topic = f["topic"]
    if topic is None:
        return make_band([("Home", "/"), ("Risks and controls", None)])
    return make_band(
        [("Home", "/"), ("Risks and controls", reverse("rcm:explorer")), (topic.name, None)],
        icon=topic.icon,
        stages=_strip_stages(topic, f"{reverse('rcm:explorer')}?topic={topic.slug}&"),
        active_stage=f["stage"].name if f["stage"] else None,
    )


@tech_risk_only
@vary_on_headers("HX-Request")
def explorer(request):
    scope = Scope()
    drivers = selectors.current_drivers()
    f = _explorer_filters(request.GET, scope, drivers)
    matrix = selectors.risk_control_matrix()
    controls = selectors.current_controls()
    unlinked = selectors.unlinked_controls(controls, matrix)
    context = {
        "nav_active": "rcm",
        "f": f,
        "summary": _explorer_summary(matrix, controls, unlinked),
        "has_data": bool(matrix or controls),
        "topics": scope.topics,
        "stage_options": list(f["topic"].stages.all()) if f["topic"] else [],
        "coverage_choices": COVERAGE_CHOICES,
        "level_options": levels.choices(),
        "driver_options": [(d.ident, f"{d.ident} {version.title}") for d, version in drivers],
        "new_buttons": _new_buttons(request),
        "band": _explorer_band(f),
    }
    if f["view"] == "risks":
        context["rows"] = _risk_rows(matrix, f, scope)
        context["unlinked"] = _unlinked_rows(unlinked, f)
    else:
        context["rows"] = _control_rows(controls, matrix, f, scope)
    context["is_partial"] = bool(request.headers.get("HX-Request"))
    template = "rcm/_results.html" if context["is_partial"] else "rcm/explorer.html"
    return render(request, template, context)


# Engine risks

@tech_risk_only
def engine_risks(request):
    groups = selectors.engine_risks_by_domain()
    context = {
        "nav_active": "rcm",
        "groups": groups,
        "risk_count": sum(len(risks) for _, categories in groups for _, risks in categories),
        "drivers": selectors.current_drivers(),
        "band": make_band([("Home", "/"), ("Risks and controls", reverse("rcm:explorer")), ("Engine risks", None)]),
    }
    return render(request, "rcm/engine_risks.html", context)


# Key controls for SOX in-scope apps

@can_view
def sox_controls(request):
    category = request.GET.get("category")
    category = category if category in Category.values else ""
    by_topic = {}
    for control, version in selectors.top_level_controls(category):
        by_topic.setdefault(version.topic_id, []).append(
            {"ident": control.ident, "version": version}
        )
    # Topics in Library order (Topic's default ordering).
    groups = [
        {"topic": topic, "controls": by_topic[topic.pk]}
        for topic in Topic.objects.filter(is_active=True)
        if topic.pk in by_topic
    ]
    context = {
        "nav_active": "library",  # linked from the Library; the Risks and controls menu is Tech Risk only
        "groups": groups,
        "category": category,
        "category_choices": Category.choices,
        "band": make_band([("Home", "/"), ("Key controls for SOX in-scope apps", None)], title="Key controls for SOX in-scope apps"),
    }
    return render(request, "rcm/sox_controls.html", context)


# Detail pages

# TRAC's codes before they were changed so they could not be mixed up with the firm's SOX control IDs.
OLD_CODES = {"MC": "CM", "MA": "AM", "OP": "MO"}


def old_code_page(request, kind, ident):
    """Send an address that uses an old code (controls/MC-02/) to the same page under the new code."""
    prefix = ident.removeprefix("R-").partition("-")[0]
    url = reverse(f"rcm:{kind}", args=[ident.replace(prefix, OLD_CODES[prefix], 1)])
    query = request.META["QUERY_STRING"]
    return HttpResponsePermanentRedirect(f"{url}?{query}" if query else url)

@can_view
def control_detail(request, ident):
    item = _resolve(request, Control, ident)
    version = item.version
    topic, stage = version.topic, version.stage
    matrix = selectors.risk_control_matrix()
    context = {
        "nav_active": "rcm",
        "item": item,
        "v": version,
        "ident": item.entity.ident,
        "own_risks": selectors.risks_for_control(item.entity, matrix),
        "engine_addresses": selectors.addressed_engine_risks(version.addresses),
        "can_open_engine_risks": permissions.is_tech_risk(request.user),
        **_control_page_context(request, version),
        "footer": detail.footer(item),
        **detail.page_actions(request, item, reverse("rcm:control_edit", args=[item.entity.ident])),
        "history_url": detail.history_url(request, item.entity),
        "band": _item_band(topic, stage, version.theme),
    }
    return render(request, "rcm/control_detail.html", context)


def _risk_links(item):
    """Controls linked to the risk, with their live version (None when not live).

    A draft shows every link so the author sees what they chose; a published risk
    shows only links to live controls.
    """
    live = {c.pk: v for c, v in selectors.current_controls()}
    links = [
        {"control": link.control, "version": live.get(link.control_id), "coverage": link.coverage,
         "rationale": link.rationale}
        for link in item.version.control_links.select_related("control").order_by("control__ident")
    ]
    if item.is_draft:
        return links
    return [link for link in links if link["version"] is not None]


@can_view
def risk_detail(request, ident):
    item = _resolve(request, Risk, ident)
    version = item.version
    links = _risk_links(item)
    coverage = selectors.MatrixRow(
        risk=item.entity, version=version, controls=[link for link in links if link["version"]]
    ).coverage
    current_drivers = selectors.current_drivers()
    live_drivers = {d.pk: v for d, v in current_drivers}
    drivers = [
        {"driver": link.driver, "version": live_drivers[link.driver_id]}
        for link in version.driver_links.select_related("driver")
        if link.driver_id in live_drivers
    ]
    linked = {d["driver"].pk for d in drivers}
    drivers += [  # drivers whose drivers.json entry names this risk
        {"driver": d, "version": dv}
        for d, dv in selectors.drivers_naming_risk(item.entity.ident, current_drivers) if d.pk not in linked
    ]
    context = {
        "nav_active": "rcm",
        "item": item,
        "v": version,
        "ident": item.entity.ident,
        "links": links,
        "drivers": drivers,
        "coverage": coverage,
        "coverage_label": COVERAGE_LABELS[coverage],
        "footer": detail.footer(item),
        **detail.page_actions(request, item, reverse("rcm:risk_edit", args=[item.entity.ident])),
        "history_url": detail.history_url(request, item.entity),
        "band": _item_band(version.topic, version.stage, version.theme),
    }
    return render(request, "rcm/risk_detail.html", context)


@can_view
def driver_detail(request, ident):
    item = _resolve(request, Driver, ident)
    crumbs = [("Home", "/")]
    tech_risk = permissions.is_tech_risk(request.user)
    if tech_risk:
        crumbs.append(("Risks and controls", reverse("rcm:explorer")))
    context = {
        "nav_active": "rcm",
        "item": item,
        "v": item.version,
        "ident": item.entity.ident,
        "risks": selectors.risks_for_driver(item.entity, selectors.risk_control_matrix()),
        # The engine's details and risks are Tech Risk's; other readers get the TRAC wording only.
        "show_engine": tech_risk,
        "engine_risks": selectors.engine_risks_for_driver(item.entity) if tech_risk else [],
        "footer": detail.footer(item),
        **detail.page_actions(request, item, None),
        "history_url": detail.history_url(request, item.entity),
        "band": make_band([*crumbs, ("Drivers", None)]),
    }
    return render(request, "rcm/driver_detail.html", context)


# The published list of controls, for the Risk site to read

@can_view
def controls_json(request):
    """Every published control as JSON: {"published_at": ..., "controls": [{code, title, url, addresses}]}.

    `published_at` is the time of the newest published control version (a retirement counts), or null when
    nothing is published. Controls are sorted by code. It is read only, and needs the same access as any page.
    """
    newest = ControlVersion.objects.filter(status=Status.PUBLISHED).aggregate(newest=Max("published_at"))["newest"]
    controls = [
        {
            "code": control.ident,
            "title": version.title,
            "url": request.build_absolute_uri(control.get_absolute_url()),
            "addresses": list(version.addresses or []),
        }
        for control, version in selectors.current_controls()
    ]
    return JsonResponse({"published_at": newest.isoformat() if newest else None, "controls": controls})
