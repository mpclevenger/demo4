"""The plain YAML content files in content/controls: read, check, sync to the site, export.

`read_folder` checks every file against the live topics, stages and platforms and returns
Django-ready data plus plain-word problems and warnings. `sync` writes drafts or proposals from it,
and `export_topic` writes the site's published content back to a file.

Every control and risk carries its TRAC ID (`id:`). The site never makes one up: a sync
finds each item by its ID (or, failing that, by its title, and then gives it the file's ID).
The file keys are friendly; `CONTROL_KEYS` and `RISK_KEYS` map them to model fields.

Whether the site copy still matches its file entry is tracked by `apps.core.content_sync`, which
decides what each sync does with every control and risk.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.platforms.categories import Category
from apps.platforms.models import Platform
from apps.topics.models import Stage, Theme, Topic

from apps.core import content_sync as cs
from apps.core.content_sync import entry_hash
from apps.core import versioning as v
from apps.core.yaml_files import load_yaml

from . import levels, services
from .models import ID_PATTERN, Control, ControlVersion, Coverage, Frequency, Method, Nature, Risk, RiskVersion
from .shape import CHECK_KEYS, COMMAND_KEYS, EVIDENCE_KEYS, PEOPLE_KEYS, STEP_KEYS, people_problems, platform_names, step_problems

DEFAULT_FOLDER = Path(settings.BASE_DIR) / "content" / "controls"

# file key -> model field
CONTROL_KEYS = {
    "title": "title", "why": "why", "applies_when": "applies_when", "nature": "nature",
    "method": "method", "frequency": "frequency", "level": "level",
    "performed_by": "performer_role", "reviewed_by": "reviewer_role", "owned_by": "owner_role",
    "categories": "categories", "steps": "steps", "choosing_people": "choosing_people",
    "references": "references", "addresses": "addresses",
}
RISK_KEYS = {
    "title": "title", "statement": "statement", "owned_by": "owner_role", "in_sox_scope": "in_sox_scope",
    "references": "references",
}
CONTROL_ONLY_KEYS = {"id", "platforms", "stage", "theme"}
REMOVED_KEYS = {"key_control", "scope"}  # replaced by "level"; still allowed so the error can explain
RISK_ONLY_KEYS = {"id", "covered_by", "stage", "theme"}
REQUIRED_CONTROL = ("id", "title", "why", "nature", "method", "frequency", "owned_by", "level")
REQUIRED_RISK = ("id", "title", "statement", "owned_by")

ALIASES = {"frequency": {"per_event": "event", "per_change": "event", "per_occurrence": "event"}}


@dataclass
class Plan:
    """One parsed file."""

    path: Path
    topic: Topic = None
    controls: list = field(default_factory=list)  # (id, platforms, fields, entry)
    risks: list = field(default_factory=list)  # (id, fields, [(control id, coverage, why)], entry)


@dataclass
class Report:
    plans: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    ids: dict = field(default_factory=lambda: {"control": {}, "risk": {}})  # id -> where it was first used
    links: list = field(default_factory=list)  # (file name, where, control id) to check once every file is read


def read_folder(folder=None):
    folder = Path(folder or DEFAULT_FOLDER)
    report = Report()
    files = topic_files(folder)
    if problem := levels.problem():
        report.problems.append(problem)
    if not files:
        report.problems.append(f"No .yaml files found in {folder}.")
    for path in files:
        _read_file(path, report)
    for name, where, ident in report.links:
        if ident not in report.ids["control"]:
            report.problems.append(f"{name}, {where}: '{ident}' isn't the id of a control in the files.")
    return report


def topic_files(folder):
    """The topic files in a folder (levels.yaml is the levels list, not a topic)."""
    return [path for path in sorted(Path(folder).glob("*.yaml")) if path.name != levels.FILE_NAME]


def _read_file(path, report):
    def problem(where, message):
        report.problems.append(f"{path.name}, {where}: {message}")

    data, file_problem = load_yaml(path)
    if file_problem:
        report.problems.append(file_problem)
        return
    if not isinstance(data, dict):
        problem("top level", "expected a topic, risks and controls.")
        return
    for key in data.keys() - {"topic", "risks", "controls"}:
        problem(f"'{key}'", "isn't a known field. Use topic, risks and controls.")
    topic = Topic.objects.filter(name=data.get("topic")).first()
    if not topic:
        names = ", ".join(Topic.objects.values_list("name", flat=True)) or "none yet; run seed_topics first"
        problem("field 'topic'", f"'{data.get('topic')}' isn't a topic on this site. Topics: {names}.")
        return
    plan = Plan(path=path, topic=topic)
    for number, item in enumerate(_listed(data, "controls", problem), start=1):
        _read_control(plan, item, number, problem, report)
    for number, item in enumerate(_listed(data, "risks", problem), start=1):
        _read_risk(plan, item, number, problem, report)
    report.plans.append(plan)


def _listed(data, key, problem):
    value = data.get(key) or []
    if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
        problem(f"field '{key}'", "expected a list of entries.")
        return []
    return value


def _where(kind, item, number):
    label = item.get("id") or item.get("title") or f"number {number}"
    return f"{kind} '{label}'"


def _check_keys(item, allowed, where, problem):
    for key in item.keys() - allowed:
        problem(where, f"'{key}' isn't a known field.")
    return item.keys() <= allowed


def _choice(value, field_name, choices, where, problem):
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    text = ALIASES.get(field_name, {}).get(text, text)
    if text not in choices.values:
        problem(f"{where}, field '{field_name}'", f"'{value}' isn't allowed. Use one of: {', '.join(choices.values)}.")
        return None
    return text


def _place(item, topic, where, problem):
    """The stage or theme an item belongs to."""
    stage_name, theme_name = item.get("stage"), item.get("theme")
    if stage_name and theme_name:
        problem(where, "use a stage or a theme, not both.")
        return None, None
    if stage_name:
        stage = Stage.objects.filter(topic=topic, name=stage_name).first()
        if not stage:
            names = ", ".join(topic.stages.values_list("name", flat=True))
            problem(f"{where}, field 'stage'", f"'{stage_name}' isn't a stage of {topic.name}. Stages: {names}.")
        return stage, None
    if theme_name:
        theme = Theme.objects.filter(topic=topic, name=theme_name).first()
        if not theme:
            names = ", ".join(topic.themes.values_list("name", flat=True))
            problem(f"{where}, field 'theme'", f"'{theme_name}' isn't a theme of {topic.name}. Themes: {names}.")
        return None, theme
    return None, None


def _read_id(kind, item, where, problem, report, path):
    """The item's TRAC ID, checked for shape and for being used once across all files."""
    ident = item.get("id")
    if ident in (None, ""):
        return None
    ident = str(ident).strip()
    if not ID_PATTERN.match(ident):
        problem(f"{where}, field 'id'", f"'{ident}' isn't a usable ID. Use letters, numbers, dashes, dots or underscores, up to 40 characters.")
    elif ident in report.ids[kind]:
        problem(f"{where}, field 'id'", f"'{ident}' is already used by another {kind} ({report.ids[kind][ident]}).")
    else:
        report.ids[kind][ident] = f"{path.name}, {where}"
    return ident


def _read_control(plan, item, number, problem, report):
    where = _where("control", item, number)
    allowed = CONTROL_KEYS.keys() | CONTROL_ONLY_KEYS | REMOVED_KEYS | {"ref"}
    _check_keys(item, allowed, where, problem)
    if "ref" in item:
        problem(f"{where}, field 'ref'", "is no longer used. Give the control a TRAC ID as 'id' instead.")
    for key in REQUIRED_CONTROL:
        if item.get(key) in (None, ""):
            problem(where, f"field '{key}' is missing.")
    ref = _read_id("control", item, where, problem, report, plan.path)
    fields = {model: item[key] for key, model in CONTROL_KEYS.items() if key in item}
    for name, choices in (("nature", Nature), ("method", Method), ("frequency", Frequency)):
        if item.get(name) is not None:
            fields[name] = _choice(item[name], name, choices, where, problem)
    for old in sorted(REMOVED_KEYS):
        if old in item:
            problem(f"{where}, field '{old}'", "is no longer used. Use 'level' instead (see levels.yaml).")
    if item.get("level") is not None and item["level"] not in levels.keys():
        problem(f"{where}, field 'level'", f"'{item['level']}' isn't a level. Use one of: {', '.join(levels.keys())}.")
    # What the file leaves out is empty, so removing a line from the file removes it from the site too.
    fields = {"performer_role": "", "reviewer_role": "", "applies_when": [], "addresses": [], **fields}
    fields["steps"] = _steps(item.get("steps") or [], where, problem)
    fields["choosing_people"] = _choosing_people(item.get("choosing_people") or {}, where, problem)
    fields["references"] = _references(item.get("references") or [], where, problem)
    fields["categories"] = item.get("categories") or []
    if not isinstance(fields["categories"], list):
        problem(f"{where}, field 'categories'", "expected a list.")
        fields["categories"] = []
    for key in fields["categories"]:
        if key not in Category.values:
            problem(f"{where}, field 'categories'", f"'{key}' isn't a category. Use: {', '.join(Category.values)}.")
    platforms = []
    for name in item.get("platforms") or []:
        platform = Platform.objects.filter(name=name).first()
        if platform:
            platforms.append(platform)
        else:
            report.warnings.append(f"{plan.path.name}, {where}, field 'platforms': no platform named '{name}'; skipped.")
    _check_command_platforms(fields["steps"], f"{plan.path.name}, {where}", report)
    stage, theme = _place(item, plan.topic, where, problem)
    fields["stage"], fields["theme"] = stage, theme
    _check_model(plan.topic, fields, ControlVersion, where, problem)
    plan.controls.append((ref, platforms, fields, item))


def _steps(steps, where, problem):
    """The control's steps, in the order the file gives them. If any step has a problem, each is reported
    and no steps are kept, so the model check stays quiet about the same thing."""
    problems = step_problems(steps)
    for number, text in problems:
        problem(f"{where}, step {number}" if number else f"{where}, field 'steps'", text)
    if problems:
        return []
    return [_step_entry(step) for step in steps]


def _step_entry(step, code=str):
    """A checked step with its keys in the reading order. `code` is applied to each command's code."""
    entry = {key: step[key] for key in STEP_KEYS if key in step}
    if "evidence" in entry:
        entry["evidence"] = {key: step["evidence"][key] for key in EVIDENCE_KEYS if key in step["evidence"]}
    if "commands" in entry:
        entry["commands"] = [
            {key: _command_value(key, command[key], code) for key in COMMAND_KEYS if key in command}
            for command in step["commands"]
        ]
    if "checks" in entry:
        entry["checks"] = [{key: check[key] for key in CHECK_KEYS if key in check} for check in step["checks"]]
    return entry


def _command_value(key, value, code):
    """One value of a command as stored: the code through `code`, a date as YYYY-MM-DD text, the rest as written."""
    if key == "code":
        return code(value)
    if key == "confirmed_on":
        return str(value)  # a YAML file turns a bare date into a date; the site keeps plain text
    return value


def _check_command_platforms(steps, where, report):
    """Warn about a command written for a platform this site doesn't have. The command is kept."""
    wanted = platform_names(steps)
    if not wanted:
        return
    known = set(Platform.objects.values_list("name", flat=True))
    for number, name in wanted:
        if name not in known:
            report.warnings.append(
                f"{where}, step {number}, field 'commands' or 'checks': no platform named '{name}'; kept as written, "
                "but it won't open first for anyone."
            )


def _choosing_people(people, where, problem):
    """The notes on choosing people, or nothing when they have a problem (which is reported)."""
    problems = people_problems(people)
    for text in problems:
        problem(f"{where}, field 'choosing_people'", text)
    if problems:
        return {}
    return {key: people[key] for key in PEOPLE_KEYS if key in people}


def _references(references, where, problem):
    if not isinstance(references, list) or not all(isinstance(r, dict) for r in references):
        problem(f"{where}, field 'references'", "expected a list of label and link entries.")
        return []
    return [{"label": r.get("label"), "url": r.get("link")} for r in references]


def _read_risk(plan, item, number, problem, report):
    where = _where("risk", item, number)
    _check_keys(item, RISK_KEYS.keys() | RISK_ONLY_KEYS, where, problem)
    for key in REQUIRED_RISK:
        if item.get(key) in (None, ""):
            problem(where, f"field '{key}' is missing.")
    ident = _read_id("risk", item, where, problem, report, plan.path)
    fields = {"in_sox_scope": False, **{model: item[key] for key, model in RISK_KEYS.items() if key in item}}
    if "in_sox_scope" in item and not isinstance(item["in_sox_scope"], bool):
        problem(f"{where}, field 'in_sox_scope'", "use yes or no.")
    fields["references"] = _references(item.get("references") or [], where, problem)
    fields["stage"], fields["theme"] = _place(item, plan.topic, where, problem)
    links = []
    for link in item.get("covered_by") or []:
        spot = f"{where}, field 'covered_by'"
        if not isinstance(link, dict) or link.keys() - {"control", "coverage", "why"}:
            problem(spot, "each entry needs control, coverage and why.")
            continue
        report.links.append((plan.path.name, spot, str(link.get("control") or "").strip()))
        if not str(link.get("why") or "").strip():
            problem(spot, f"add a one-line reason for '{link.get('control')}'.")
        coverage = _choice(link.get("coverage", ""), "coverage", Coverage, spot, problem)
        links.append((str(link.get("control") or "").strip(), coverage, link.get("why", "")))
    _check_model(plan.topic, fields, RiskVersion, where, problem)
    plan.risks.append((ident, fields, links, item))


def _check_model(topic, fields, model, where, problem):
    """Run the same checks the site's forms run."""
    try:
        model(topic=topic, **fields).clean()
    except ValidationError as error:
        for name, messages in error.message_dict.items():
            problem(f"{where}, field '{name}'", " ".join(messages))


def _latest(entity):
    return entity.versions.order_by("-number").first()


def _find(entity_model, version_model, ident, title, topic):
    """The site's item for a file entry: the one with this ID, or else the one whose latest title is this one
    (in this topic first). An item found by title gets the file's ID during the sync."""
    entity = entity_model.objects.filter(ident=ident).first()
    if entity is not None:
        return entity
    candidates = []
    for version in version_model.objects.filter(title=title).select_related("entity"):
        latest = _latest(version.entity)
        if latest.title == title and version.entity not in candidates:
            candidates.append(version.entity)
    candidates.sort(key=lambda e: _latest(e).topic_id != topic.pk)
    return candidates[0] if candidates else None


def _give_ids(matches, dry_run, say):
    """Give items found by title the IDs from the files. Two items may swap IDs, so each first gets a
    temporary one. An ID held by an item that isn't in the files stops the sync with a plain message."""
    renames = [(entity, ident) for entity, ident in matches if entity is not None and entity.ident != ident]
    moving = {entity.pk for entity, _ in renames}
    for entity, ident in renames:
        holder = type(entity).objects.filter(ident=ident).exclude(pk=entity.pk).first()
        if holder is not None and holder.pk not in moving:
            raise CommandError(
                f"The ID {ident} is already used on the site by '{_latest(holder).title}'. "
                "Give that item a different ID in its file, or retire it, then sync again."
            )
    for entity, ident in renames:
        say(f"{'Would change' if dry_run else 'Changed'} the ID of '{_latest(entity).title}' from {entity.ident} to {ident}.")
    if dry_run:
        return
    for entity, _ in renames:
        type(entity).objects.filter(pk=entity.pk).update(ident=f"~{entity.pk}")
    for entity, ident in renames:
        type(entity).objects.filter(pk=entity.pk).update(ident=ident)
        entity.ident = ident


def sync(report, user, say, publish=False, force=False, dry_run=False):
    """Bring the site in line with the files. Returns a list of cs.Outcome."""
    cs.ensure_can_publish(publish)
    outcomes = []
    with transaction.atomic():
        found = {}
        for plan in report.plans:
            for ident, _, fields, _ in plan.controls:
                found[("control", ident)] = _find(Control, ControlVersion, ident, fields["title"], plan.topic)
            for ident, fields, _, _ in plan.risks:
                found[("risk", ident)] = _find(Risk, RiskVersion, ident, fields["title"], plan.topic)
        _give_ids([(entity, ident) for (_, ident), entity in found.items()], dry_run, say)
        controls = {}
        for plan in report.plans:
            for ident, platforms, fields, entry in plan.controls:
                outcome, entity = _sync_item(
                    Control, plan, ident, found[("control", ident)], fields, entry, user, publish, force, dry_run,
                    after=lambda version, platforms=platforms: version.platforms.set(platforms),
                )
                controls[ident] = entity
                outcomes.append(outcome)
                say(outcome.message)
        for plan in report.plans:
            for ident, fields, links, entry in plan.risks:
                def set_links(version, links=links):
                    drivers = [link.driver for link in version.driver_links.all()]
                    services.set_risk_links(
                        version, user, drivers=drivers,
                        controls=[(controls[c], coverage, why) for c, coverage, why in links if controls.get(c)],
                    )
                outcome, _ = _sync_item(
                    Risk, plan, ident, found[("risk", ident)], fields, entry, user, publish, force, dry_run,
                    after=set_links,
                )
                outcomes.append(outcome)
                say(outcome.message)
    return outcomes


def _sync_item(entity_model, plan, ident, entity, fields, entry, user, publish, force, dry_run, after):
    kind = "control" if entity_model is Control else "risk"
    title, digest = fields["title"], entry_hash(entry)
    decision = cs.decide(entity, title, digest, force=force, export_command="export_controls")
    if decision.kind == cs.IS_NEW:
        if dry_run:
            return cs.Outcome(cs.NEW, f"Would create {kind} draft {ident}: {title}."), None
        make = services.create_control if kind == "control" else services.create_risk
        entity, version = make(user, plan.topic, ident=ident, **fields)
        cs.record(entity, version, digest)
        after(version)
        cs.finish(version, user, publish)
        return cs.Outcome(cs.NEW, f"Created {kind} {entity.ident} as a draft: {title}."), entity
    if decision.kind != cs.UPDATE:
        return cs.Outcome(decision.outcome, decision.message), entity
    if dry_run:
        return cs.Outcome(cs.UPDATED, f"Would propose a change to {ident}: {title}."), entity
    version = v.propose_change(
        entity, user, f"Updated from content/controls/{plan.path.name}", topic=plan.topic, **fields)
    cs.record(entity, version, digest)
    after(version)
    cs.finish(version, user, publish)
    return cs.Outcome(cs.UPDATED, f"Proposed a change to {entity.ident}: {title}."), entity


# ---- export ----

class Block(str):
    """Multi-line text that is written to the file as a YAML block, so code stays readable."""


yaml.SafeDumper.add_representer(
    Block, lambda dumper, text: dumper.represent_scalar("tag:yaml.org,2002:str", text, style="|")
)


def _export_code(code):
    return Block(code) if "\n" in code else code


def _control_entry(version):
    entry = {
        "id": version.entity.ident, "title": version.title, "why": version.why, "applies_when": list(version.applies_when),
        "nature": version.nature, "method": version.method, "frequency": version.frequency,
        "level": version.level, "owned_by": version.owner_role, "performed_by": version.performer_role,
        "reviewed_by": version.reviewer_role,
        "stage": version.stage.name if version.stage_id else None,
        "theme": version.theme.name if version.theme_id else None,
        "categories": list(version.categories),
        "platforms": [p.name for p in version.platforms.order_by("name")],
        "steps": [_step_entry(step, _export_code) for step in version.steps],
        "choosing_people": {key: version.choosing_people[key] for key in PEOPLE_KEYS if key in version.choosing_people},
        "references": [{"label": r["label"], "link": r["url"]} for r in version.references],
        "addresses": list(version.addresses),
    }
    return {k: val for k, val in entry.items() if val not in ("", None, [], {})}


def _risk_entry(version):
    entry = {
        "id": version.entity.ident, "title": version.title, "statement": version.statement, "owned_by": version.owner_role,
        "stage": version.stage.name if version.stage_id else None,
        "theme": version.theme.name if version.theme_id else None,
        "in_sox_scope": version.in_sox_scope,
        "covered_by": [
            {"control": link.control.ident, "coverage": link.coverage, "why": link.rationale}
            for link in version.control_links.select_related("control").order_by("control__ident")
        ],
        "references": [{"label": r["label"], "link": r["url"]} for r in version.references],
    }
    return {k: val for k, val in entry.items() if val not in ("", None, [])}


def _header(path):
    """The comment block at the top of an existing file, or the shipped default."""
    for candidate in (path, *topic_files(DEFAULT_FOLDER)):
        if candidate.exists():
            lines = []
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if not line.startswith("#"):
                    break
                lines.append(line)
            if lines:
                return "\n".join(lines) + "\n\n"
    return ""


def export_topic(topic, folder, say):
    """Write a topic's published controls and risks to <folder>/<topic-slug>.yaml and mark them in sync."""
    path = Path(folder) / f"{slugify(topic.name)}.yaml"
    controls = [c.current() for c in Control.objects.all()]
    controls = [c for c in controls if c and c.kind != v.Kind.RETIRE and c.topic_id == topic.pk]
    controls.sort(key=lambda c: c.entity.ident)
    risks = [r.current() for r in Risk.objects.all()]
    risks = [r for r in risks if r and r.kind != v.Kind.RETIRE and r.topic_id == topic.pk]
    risks.sort(key=lambda r: r.entity.ident)
    control_entries = [_control_entry(c) for c in controls]
    risk_entries = [_risk_entry(r) for r in risks]
    body = yaml.safe_dump(
        {"topic": topic.name, "risks": risk_entries, "controls": control_entries},
        sort_keys=False, allow_unicode=True, width=100,
    )
    path.write_text(_header(path) + body, encoding="utf-8")
    # Hash what a reader of the file will see, so the next sync says "unchanged".
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    for version, entry in [*zip(controls, written["controls"]), *zip(risks, written["risks"])]:
        cs.record(version.entity, version, entry_hash(entry))
    say(f"Wrote {path.name}: {len(controls)} controls, {len(risks)} risks.")
    return path
