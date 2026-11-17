"""The one way to edit things on the TRUST and Risk sites (owner, 15 Nov 2026; docs/design/22_editable_lists.md).

Every list a person edits is described once, in plain data (LISTS, below): its name, its fields, who may save,
the check that refuses a bad value, and, when a change can move a rating, the function that works out what would
move. This file gives every list the same table, add, edit, retire, reason, history, "See what would move" and
download. A new list is a new description, not new screens. Design in plain words: docs/design/22_editable_lists.md.

How a list is kept
    Every change is one row in the list_change table (storage.list_changes): never edited, never removed.
    The entries of a list now are worked out from its rows, oldest first (entries_now).
    A list that can grow (questions, building blocks) is read from its file ONCE: the first save writes one
    "load" row holding every entry from the file. After that the site is the golden source and the file is not read.
    A list with a fixed set of entries (rating settings, drivers answered from data) is the file's values with the
    site's changes on top, the way thresholds_config() keeps the scoring settings.
    Nothing is ever deleted: a retired entry stays in the list (greyed) and in the history, and can be restored.

Routes (registered in web.py as `bp`)
    GET  /api/edit                     the lists, for the "Edit" menu
    GET  /api/edit/<list>              one list: description, entries, history, whether you may save
    POST /api/edit/<list>/preview      check a change and show what it would move; saves nothing
    POST /api/edit/<list>/save         check and keep a change, with who and why
    GET  /api/edit/<list>/download     the current list, ?format=csv or json
"""
import csv
import io
import json

from flask import Blueprint, Response, g, jsonify, request

from trust import access, config, storage
from trust.lazy_web import stop_data_senders, trust_web
from trust.risk import data_drivers, drivers, groups, rating, team_figures, trigger_language
from trust.risk import questions as question_list
from trust.words import tidy_spaces

bp = Blueprint("editable", __name__)
bp.before_request(stop_data_senders)

# What a person may do to an entry.
ADD, EDIT, RETIRE, RESTORE, LOAD = "add", "edit", "retire", "restore", "load"
WHOLE_LIST = "*"                                         # the entry key of the first-load row

LONGEST_TEXT = 500                                       # characters in one text field
LONGEST_REASON = 1000
FIRST_LOAD_REASON = "First load from the file."
LEVEL_CHOICES = [{"value": level, "label": level.capitalize()} for level in rating.LEVELS]
ORDER_STEP = 10                                          # questions are numbered 10, 20, 30 so one can slip between two
LARGEST_WHOLE_NUMBER = 10 ** 15                          # a number this size or bigger is kept as a decimal, not a whole number
LARGEST_ORDER = 100_000                                  # the largest order a question may have
LARGEST_ANSWER_NUMBER = 1_000_000                        # the largest number that switches a question's driver on
LARGEST_FIXED_NUMBER = 1_000_000_000                     # the largest fixed number a data driver is compared with


# ---------------------------------------------------------------------------------------------------
# The registers the Risk site reads, from the risk files (the first load) and from the site's own changes
# ---------------------------------------------------------------------------------------------------

def _raw():
    """The registers as read from the files, with no saved change on top."""
    from trust.risk import registers                     # imported here: registers puts this file's saved changes on top
    return registers.load_registers()["from_files"]


def _in_force(slug, rows_by_list):
    """True when something has been saved for this list, so the site (not the file) is its source."""
    return bool(rows_by_list.get(slug))


def _group_rows(rows):
    by_list = {}
    for row in rows:
        by_list.setdefault(row["list_name"], []).append(row)
    return by_list


def with_saved_changes(loaded):
    """The Risk site's registers with the changes saved on the editing pages on top: the rating settings, the
    questions (and the answer or number that switches each driver on), and each risk's building block.
    `loaded` is {"risks","driver_rules","questions","settings","placements","notes"} as read from the files; what
    comes back has the same keys, and `from_files` too: what the files alone said (the editing pages show it)."""
    from_files = {name: loaded[name] for name in ("risks", "driver_rules", "questions", "settings", "placements")}
    rows_by_list = _group_rows(storage.list_changes())
    if not any(_in_force(slug, rows_by_list) for slug in ("rating-settings", "questions", "building-blocks", "driver-triggers")):
        return {**loaded, "from_files": from_files}
    registers = _registers_from(from_files, {}, rows_by_list)
    return {**loaded, **{name: registers[name] for name in ("driver_rules", "questions", "settings", "placements")},
            "from_files": from_files}


def _registers_from(from_files, replacing, rows_by_list):
    """The settings, questions, driver rules and placements the site uses. `replacing` swaps in proposed entries
    for a list ({slug: entries}), which is how "See what would move" tries a change without saving it."""
    def entries_of(slug):
        if slug in replacing:
            return replacing[slug]
        if _in_force(slug, rows_by_list):
            return entries_now(slug, from_files, rows_by_list[slug])
        return None                                      # nothing saved: the file's own value stands

    registers = dict(from_files)
    settings_entries = entries_of("rating-settings")
    if settings_entries is not None:
        registers["settings"] = {entry["key"]: entry["values"]["value"] for entry in settings_entries}
    trigger_entries = entries_of("driver-triggers")
    if trigger_entries is not None:
        registers["driver_rules"] = _rules_with_triggers(trigger_entries, from_files["driver_rules"])
        registers["questions"] = question_list.build(registers["driver_rules"], from_files["risks"])
    question_entries = entries_of("questions")
    if question_entries is not None:
        registers["questions"], registers["driver_rules"] = _questions_and_rules(question_entries, registers["driver_rules"])
    block_entries = entries_of("building-blocks")
    if block_entries is not None:
        registers["placements"] = _placements(block_entries)
    return registers


def _placements(entries):
    """{"by_domain": {...}, "by_risk": {...}} from the building-block entries that are not retired."""
    placements = {"by_domain": {}, "by_risk": {}}
    for entry in entries:
        if entry["retired"]:
            continue
        values = entry["values"]
        where = "by_risk" if values["applies_to"] == "risk" else "by_domain"
        placements[where][values["name"]] = values["block"]
    return placements


def _rules_with_triggers(entries, file_rules):
    """The driver rules with the triggers saved on the "Drivers with a full trigger" page put on. A driver with no
    entry keeps its rule."""
    rules = {code: dict(rule) for code, rule in file_rules.items()}
    trigger_keys = ("field", "test", "value", "trigger", "fields")
    for entry in entries:
        code = entry["values"]["driver"]
        if entry["retired"] or code not in rules:
            continue
        kept = {name: value for name, value in rules[code].items() if name not in trigger_keys}
        rules[code] = {**kept, **drivers.rule_from_trigger(entry["values"]["trigger"])}
    return rules


def _rule_for_question(values, rule):
    """The driver's rule, with what the question says about it put on. The test and the number a question gives
    are data of the rule (RD12 is on when the answer is at least 3); how a rule is read is not changed here.
    A rule with a full trigger is left as it is: its trigger says when the driver is on."""
    rule = dict(rule)
    if rule["test"] == drivers.MATCHES_TRIGGER:
        return rule
    if values["kind"] == "number":
        rule["test"], rule["value"] = values["test"], values["number"]
    elif rule["test"] not in (drivers.IS_YES, drivers.IS_NO):
        rule["test"], rule["value"] = drivers.IS_YES, None
    return rule


OPTION_SEPARATOR = " | "                                  # between the options typed or loaded for a tick-any question


def _listed_options(values):
    """The options written on the question itself (the questionnaire file's list, or typed on the Edit page)."""
    return [option.strip() for option in str(values.get("options") or "").split(OPTION_SEPARATOR.strip()) if option.strip()]


def _question_from_entry(entry, rule, all_rules=None):
    """One question as the form uses it: {"field","driver","section","text","kind","yes_means_field_is"}.
    A yes answer means the sentence is true. If "Yes" is the answer that switches the driver on, a yes turns it on
    when the rule is "is yes", and a no turns it on when the rule is "is no"; "No" switches it on the other way."""
    values = entry["values"]
    question = {"field": entry["key"], "driver": values["driver"], "section": values["section"],
                "text": values["text"], "kind": values["kind"], "yes_means_field_is": None,
                "help": values.get("help_text") or ""}
    if rule["test"] == drivers.MATCHES_TRIGGER:
        question["yes_means_field_is"] = True if values["kind"] == "yes_no" else None
        if values["kind"] == "text":
            uses = question_list.uses_across_rules(all_rules or {rule["field"]: rule}, entry["key"])
            question["choices"] = uses.get("text", [])
            if uses.get("number") and question["choices"]:
                question["accepts_number"] = True
        if values["kind"] == "tick_any":
            uses = question_list.uses_across_rules(all_rules or {rule["field"]: rule}, entry["key"])
            question["choices"] = question_list.with_none_of_these(
                _listed_options(values) + uses.get("tick_any", []) + uses.get("text", []))
    elif values["kind"] == "tick_any":
        question["choices"] = question_list.with_none_of_these(_listed_options(values))
    elif values["kind"] == "yes_no":
        rule_is_yes = rule["test"] == drivers.IS_YES
        yes_switches_it_on = values["switches_on"] == "yes"
        question["yes_means_field_is"] = yes_switches_it_on == rule_is_yes
    return question


def _questions_and_rules(entries, file_rules):
    """The form's questions in order, and the driver rules with each question's test and number on them."""
    rules = {code: dict(rule) for code, rule in file_rules.items()}
    active = [entry for entry in entries if not entry["retired"] and entry["values"]["driver"] in rules]
    first_order = {}
    for entry in active:
        section = entry["values"]["section"]
        first_order[section] = min(first_order.get(section, entry["values"]["order"]), entry["values"]["order"])
    active.sort(key=lambda entry: (first_order[entry["values"]["section"]], entry["values"]["order"]))
    questions = []
    for entry in active:
        driver = entry["values"]["driver"]
        rules[driver] = _rule_for_question(entry["values"], rules[driver])
        if entry["key"] not in (rules[driver].get("questionnaire_fields") or []):
            rules[driver]["questionnaire_fields"] = list(rules[driver].get("questionnaire_fields") or []) + [entry["key"]]
        questions.append(_question_from_entry(entry, rules[driver], rules))
    return questions, rules


# ---------------------------------------------------------------------------------------------------
# What would move: every group's latest assessment, rated again with the proposed values
# ---------------------------------------------------------------------------------------------------

def _word(level):
    return level.capitalize() if level else "Not rated"


def rating_moves(from_files, slug, proposed_entries):
    """Every rating that would change if `proposed_entries` replaced the saved ones of list `slug`.

    For each team with an assessment, the answers of its newest assessment are rated twice, with the values in use
    and with the proposed ones (the way site.submit_group rates). Returns [{group, risk, name, what, before, after}].
    """
    rows_by_list = _group_rows(storage.list_changes())
    in_use = _registers_from(from_files, {}, rows_by_list)
    proposed = _registers_from(from_files, {slug: proposed_entries}, rows_by_list)
    return rating_moves_between(in_use, proposed)


def _rate_with(registers, answers, data_answers):
    """Every risk rated with these registers: the team's saved answers, and the data drivers' answers as they were
    when it was submitted."""
    return data_drivers.assess_with_data(registers["risks"], registers["driver_rules"], registers["questions"], answers,
                                         registers["settings"], registers["placements"], None, data_answers)["risks"]


def rating_moves_between(in_use, proposed):
    """Every rating that would change between two sets of registers (the values in use and a proposed set), for each
    team's newest assessment. The one place this re-rating is done: the editing lists and the risk-file uploads
    both call it. Returns [{group, risk, name, what, before, after}]."""
    moves = []
    for group in groups.load():
        assessments = storage.risk_assessments(group["id"])
        if not assessments:
            continue
        answers = assessments[-1]["result"]["answers"]
        data_answers = assessments[-1]["result"].get("data_drivers") or {}
        ratings_now = _rate_with(in_use, answers, data_answers)
        ratings_then = _rate_with(proposed, answers, data_answers)
        for risk_id in sorted(set(ratings_now) | set(ratings_then)):
            moves.extend(_moves_for_one_risk(group, risk_id, ratings_now.get(risk_id), ratings_then.get(risk_id)))
    return moves


def _moves_for_one_risk(group, risk_id, now, then):
    """The moves of one risk for one team. `now` and `then` are its ratings with the values in use and the proposed
    ones; either is None when that set of registers doesn't have the risk."""
    if then is None:                                     # a risk the proposed set no longer has
        return []
    if now is None:                                      # a risk the proposed set adds
        return _moves_for_new_risk(group, risk_id, then)
    if now["applicable"] != then["applicable"]:
        return [_move(group, risk_id, now, "Applies", _yes_no(now["applicable"]), _yes_no(then["applicable"]))]
    if now["applicable"]:
        return _moves_for_levels(group, risk_id, now, then)
    return []


def _moves_for_new_risk(group, risk_id, then):
    if not then["applicable"]:
        return []
    after = f"Likelihood {_word(then.get('likelihood'))}, impact {_word(then.get('impact'))}"
    return [_move(group, risk_id, then, "New risk", "Not on the site", after)]


def _moves_for_levels(group, risk_id, now, then):
    """Elevated, likelihood and impact of a risk that applies both ways: one move for each that differs."""
    moves = []
    for what, field, show in (("Elevated", "elevated", _yes_no), ("Likelihood", "likelihood", _word), ("Impact", "impact", _word)):
        if now[field] != then[field]:
            moves.append(_move(group, risk_id, now, what, show(now[field]), show(then[field])))
    return moves


def _yes_no(value):
    return "Yes" if value else "No"


def _move(group, risk_id, rated, what, before, after):
    return {"group": group["name"], "risk": risk_id, "name": rated.get("name") or risk_id,
            "what": what, "before": before, "after": after}


# ---------------------------------------------------------------------------------------------------
# The seven lists, each described once
# ---------------------------------------------------------------------------------------------------
# A list:   slug, name, intro, grows (can entries be added and retired?), who_text, fields, notes,
#           from_file(from_files) -> [{"key","values"}], title_of(values), check(action, key, values, entries, from_files),
#           moves(from_files, proposed entries) -> what would move (leave out when a change can't move a rating)
# A field:  name, label, kind (text, number, yes_no, pick), help, choices (for pick; a list or a function),
#           required (default yes), readonly, once (set when added, fixed after), only_when ({"field", "is"}),
#           min, max (number), table (show in the table; default yes)

def _file_settings(from_files):
    labels = {"medium_share_above": "A risk is Medium when more than this share of its likelihood drivers are on",
              "elevated_likelihood_at_least": "A risk is Elevated when its likelihood is at least",
              "elevated_impact_at_least": "...and its impact is at least"}
    return [{"key": name, "values": {"label": labels.get(name, name), "value": value}}
            for name, value in from_files["settings"].items()]


def _setting_fields(key, from_files):
    """How the Value field reads for each setting."""
    if key == "medium_share_above":
        return {"value": {"kind": "number", "min": 0, "max": 1,
                          "help": "A share from 0 to 1. 0.30 means 30%, which is one driver of three."}}
    return {"value": {"kind": "pick", "choices": LEVEL_CHOICES}}


def _check_settings(action, key, values, entries, from_files):
    proposed = {entry["key"]: entry["values"]["value"] for entry in entries}
    proposed[key] = values["value"]
    try:
        rating.check_settings(proposed)
    except ValueError as problem:
        raise ValueError(f"Those rating settings can't be used. {problem}") from None


def _split_risk_ids(text):
    """'air.cyber.01, air.ops.01' -> ['air.cyber.01', 'air.ops.01']. Empty text gives no risks."""
    return [piece.strip() for piece in str(text or "").replace(";", ",").split(",") if piece.strip()]


def _file_metric_risks(from_files):
    """One entry per metric (Measured, In progress and Wanted). The starting value is the metrics file's card.risks."""
    return [{"key": metric_id,
             "values": {"metric_id": metric_id, "name": metric["name"],
                        "risk_ids": ", ".join((metric.get("card") or {}).get("risks") or [])}}
            for metric_id, metric in config.metrics().items()]


def _current_metrics_only(entries):
    """The metric risk entries, kept to the metrics in the metrics file now, each with its id and name as that file gives them."""
    metrics = config.metrics()
    return [dict(entry, values=dict(entry["values"], metric_id=entry["key"], name=metrics[entry["key"]]["name"]))
            for entry in entries if entry["key"] in metrics]


def _check_metric_risks(action, key, values, entries, from_files):
    """Every risk ID must be one of the Risk site's current risks, and none may be listed twice."""
    known = _raw()["risks"] if from_files is None else from_files["risks"]
    listed = _split_risk_ids(values.get("risk_ids"))
    for risk_id in listed:
        if risk_id not in known:
            raise ValueError(f"'{risk_id}' is not one of the Risk site's risks. Use the risk's ID exactly as the Risk site shows it, "
                             f"for example {next(iter(sorted(known)), 'air.cyber.01')}.")
    for risk_id in listed:
        if listed.count(risk_id) > 1:
            raise ValueError(f"'{risk_id}' is in the list twice. Name each risk once.")


def all_metric_risks():
    """{metric id: [risk ids it watches]} for every metric, as Tech Risk has it on the site (the file's value until changed).
    The one place anything reads which risks a metric watches."""
    return {entry["key"]: _split_risk_ids(entry["values"].get("risk_ids")) for entry in entries_now("metric-risks")}


def metric_risks(metric_id):
    """The risk IDs one metric watches, as Tech Risk has them on the site. Empty for a metric that watches none."""
    return all_metric_risks().get(metric_id, [])


def _file_questions(from_files):
    entries = []
    for number, question in enumerate(from_files["questions"], 1):
        rule = from_files["driver_rules"].get(question["driver"]) or {}
        is_number = question["kind"] == "number" and rule.get("test") != drivers.MATCHES_TRIGGER
        entries.append({"key": question["field"], "values": {
            "driver": question["driver"], "section": question["section"], "order": number * ORDER_STEP,
            "text": question["text"], "kind": question["kind"], "switches_on": "yes" if question["kind"] == "yes_no" else None,
            "test": rule.get("test") if is_number else None, "number": rule.get("value") if is_number else None,
            **({"options": OPTION_SEPARATOR.join(c for c in question.get("choices", []) if c != question_list.NONE_OF_THESE)}
               if question["kind"] == "tick_any" else {})}})
    return entries


def _driver_choices(from_files=None):
    rules = (from_files or _raw())["driver_rules"]
    return [{"value": code, "label": f"{code}: {rules[code].get('rationale') or code}"} for code in sorted(rules)]


def _section_names(from_files=None):
    return sorted({entry["values"]["section"] for entry in entries_now("questions", from_files)})


def _rule_asking(key, from_files):
    """The driver rule that a question's field belongs to, or None."""
    wanted = str(key).lower()
    for _code, rule in sorted(from_files["driver_rules"].items()):
        names = [rule["field"]] + list(rule.get("fields") or []) + list(rule.get("questionnaire_fields") or [])
        if wanted in [str(name).lower() for name in names]:
            return rule
    return None


def _question_fields(key, from_files):
    """A question for a driver with a full trigger has no answer or number that switches it on: the trigger decides."""
    rule = _rule_asking(key, from_files) if from_files else None
    if rule is None or rule["test"] != drivers.MATCHES_TRIGGER:
        return {}
    hidden = {"only_when": {"field": "kind", "is": NEVER}}
    return {"switches_on": hidden, "test": hidden, "number": hidden}


def _question_table_text(values):
    if values["kind"] == "yes_no" and values.get("switches_on"):
        switches_on = "Yes" if values["switches_on"] == "yes" else "No"
    elif values["kind"] == "number" and values.get("test") and values.get("number") is not None:
        switches_on = f"{values['test'].capitalize()} {values['number']:g}"
    else:
        switches_on = "Its trigger decides"
    return {"driver": values["driver"], "switches_on": switches_on}


def _question_key(values, from_files):
    """A question is named by the field its driver's rule reads (RD12), so its answer reaches the rule."""
    return from_files["driver_rules"][values["driver"]]["field"]


def _check_question(action, key, values, entries, from_files):
    rule = from_files["driver_rules"].get(values["driver"])
    if rule is None:
        raise ValueError(f"There is no driver {values['driver']}.")
    if action == ADD:
        if rule["test"] in (drivers.ABOVE_PREVAILING, drivers.BELOW_PREVAILING):
            raise ValueError(f"{values['driver']} is compared with the prevailing median, which the site works out "
                             f"from data. It has no question.")
        if any(entry["key"] == key and not entry["retired"] for entry in entries):
            raise ValueError(f"{values['driver']} already has a question.")
        if any(entry["key"] == key and entry["retired"] for entry in entries):
            raise ValueError(f"The question for {values['driver']} was retired. Restore it from the list instead of adding it again.")
    if values["kind"] == "yes_no" and key.lower().endswith("_pct"):
        raise ValueError(f"{key} is a share, so its answer is a number.")
    if values["kind"] == "text" and not question_list.uses_across_rules(from_files["driver_rules"], key).get("text"):
        raise ValueError(f"{values['driver']}'s trigger doesn't compare {key} with text, so this can't be a choice of answers. "
                         f"Edit the trigger first, on 'Drivers with a full trigger'.")
    if values["kind"] == "tick_any":
        uses = question_list.uses_across_rules(from_files["driver_rules"], key)
        if not (_listed_options(values) or uses.get("tick_any") or uses.get("text")):
            raise ValueError(f"{values['driver']}'s trigger doesn't look for any chosen answer in {key}, and no options are listed, "
                             f"so there is nothing to tick. List the options, or edit the trigger first, on 'Drivers with a full trigger'.")


def _file_driver_triggers(from_files):
    """One entry for each driver whose trigger is more than one simple comparison (it has and, or, not, text or a function)."""
    return [{"key": code, "values": {"driver": code, "what": rule.get("rationale") or code, "trigger": rule["trigger"]}}
            for code, rule in sorted(from_files["driver_rules"].items()) if rule["test"] == drivers.MATCHES_TRIGGER]


def _check_driver_trigger(action, key, values, entries, from_files):
    """The trigger must be readable. The refusal says where it stopped."""
    try:
        trigger_language.read_trigger(values["trigger"])
    except trigger_language.TriggerProblem as problem:
        raise ValueError(f"{key}: {problem}") from None


def _file_blocks(from_files):
    entries = []
    for domain, block in sorted(from_files["placements"]["by_domain"].items()):
        entries.append({"key": f"domain:{domain}", "values": {"applies_to": "domain", "name": domain, "block": block}})
    for risk_id, block in sorted(from_files["placements"]["by_risk"].items()):
        entries.append({"key": f"risk:{risk_id}", "values": {"applies_to": "risk", "name": risk_id, "block": block}})
    return entries


def _block_choices(from_files=None):
    try:
        from trust import score_month
        names = [block["name"] for block in score_month.template()["blocks"]]
    except Exception:                                    # no scorecard template to read: the names already in use
        names = sorted({entry["values"]["block"] for entry in entries_now("building-blocks", from_files)})
    return names


def _check_block(action, key, values, entries, from_files):
    risks = from_files["risks"]
    if values["applies_to"] == "risk" and values["name"] not in risks:
        raise ValueError(f"There is no risk '{values['name']}'. Use its id, for example {sorted(risks)[0] if risks else 'air.ops.01'}.")
    domains = {risk.get("domain") for risk in risks.values()}
    if values["applies_to"] == "domain" and values["name"] not in domains:
        raise ValueError(f"No risk has the domain '{values['name']}'. The domains are: {', '.join(sorted(d for d in domains if d))}.")
    if values["block"] not in _block_choices(from_files):
        raise ValueError(f"'{values['block']}' isn't a TRUST building block.")
    if action == ADD:
        for entry in entries:
            if entry["key"] == key:
                what = "was retired. Restore it from the list instead" if entry["retired"] else "is already placed. Edit it instead"
                raise ValueError(f"{values['name']} {what}.")


def _file_data_drivers(from_files):
    """One entry per driver the site answers from data. A driver a calculation answers (config/risk_data_drivers.json)
    starts with that file's values; any other starts as the engine's rule says (not calculated yet). A driver that
    "Calculations you define" answers is left out: it is not "not calculated", and it is edited on that page."""
    entries = []
    defined = data_drivers.defined_settings(from_files)
    for code, rule in sorted(from_files["driver_rules"].items()):
        if rule.get("questionnaire_fields"):
            continue                                     # this driver is answered on the form
        if code in defined:
            continue                                     # answered by a calculation Tech Risk defined
        values = data_drivers.default_values(code)
        if values is None:
            from_median = rule["test"] in (drivers.ABOVE_PREVAILING, drivers.BELOW_PREVAILING)
            values = {"basis": data_drivers.BASIS_MEDIAN if from_median else data_drivers.BASIS_FIXED,
                      "fixed_number": None if from_median else rule.get("value"),
                      "share_of_median": None, "languages": "", "left_out_languages": ""}
        entries.append({"key": code, "values": {"driver": code, "what": rule.get("rationale") or code, **values}})
    return entries


NEVER = "(not used for this driver)"                     # an only_when that is never true: the field is hidden


def _data_driver_fields(key, from_files):
    """How each field of a data driver reads: only the ways of comparing its calculation can use, and only the extra
    fields (a language list, a share) that its calculation has."""
    calculation = data_drivers.calculation_of(key)
    if calculation is None:
        return {}
    ways = data_drivers.BASES_FOR[calculation]
    shown = {"basis": {"choices": [{"value": way, "label": data_drivers.BASIS_LABELS[way]} for way in ways]}}
    if calculation != data_drivers.LEGACY_LANGUAGES:
        shown["languages"] = {"only_when": {"field": "basis", "is": NEVER}}
    if calculation != data_drivers.LANGUAGE_VARIETY:
        shown["left_out_languages"] = {"only_when": {"field": "basis", "is": NEVER}}
    return shown


def _check_data_driver(action, key, values, entries, from_files):
    data_drivers.check_values(key, values)


def _file_defined_calculations(from_files):
    """The calculations the settings file starts with (config/risk_data_drivers.json, "defined_calculations")."""
    starting = data_drivers.settings_file().get("defined_calculations") or {}
    return [{"key": code, "values": {"driver": code, "figure": values["figure"], "test": values["test"],
                                     "number_or_share": values.get("number_or_share")}}
            for code, values in sorted(starting.items())]


def _check_defined_calculation(action, key, values, entries, from_files):
    code = values["driver"]
    rule = from_files["driver_rules"].get(code)
    if action == ADD:
        if rule is None:
            raise ValueError(f"There is no driver {code}.")
        for entry in entries:
            if entry["key"] == code:
                what = ("was retired. Restore it from the list instead of adding it again" if entry["retired"]
                        else "already has a calculation you defined. Edit it instead")
                raise ValueError(f"{code} {what}.")
    if rule is not None and not data_drivers.files.answered_from_data(rule):
        raise ValueError(f"{code} is answered by a question on the form, so it has no calculation to define.")
    built_in = data_drivers.calculation_of(code)
    if built_in is not None:
        raise ValueError(f"{code} is already answered by a built-in calculation ({built_in.replace('_', ' ')}). "
                         f"Change it on 'Drivers answered from data' instead.")
    team_figures.check_setting(values["test"], values["number_or_share"])


def _table_text_defined_calculation(values):
    rule = (_raw()["driver_rules"]).get(values["driver"])
    note = "" if rule is not None else " (not in the drivers file in use: not used yet)"
    return {"driver": values["driver"] + note,
            "number_or_share": "" if values["number_or_share"] is None else f"{values['number_or_share']:g}"}


LISTS = {
    "rating-settings": {
        "name": "Rating settings",
        "intro": "The three settings that decide Medium and Elevated. Before you save a change, see which ratings it would move.",
        "grows": False, "who_text": "Tech Risk", "needs_registers": True,
        "fields": [
            {"name": "label", "label": "Setting", "kind": "text", "readonly": True},
            {"name": "value", "label": "Value", "kind": "number"}],       # how Value reads is given for each setting
        "entry_fields": _setting_fields,
        "title_of": lambda values: values["label"],
        "from_file": _file_settings, "check": _check_settings, "moves": rating_moves,
        "notes": ["The rating rules themselves don't change here. Only these three values do."]},
    "questions": {
        "name": "Questions",
        "intro": "The questionnaire: the wording, the section, the order, the kind of answer, and which answer switches the driver on.",
        "grows": True, "who_text": "Tech Risk",
        "needs_registers": True,
        "fields": [
            {"name": "driver", "label": "Driver it feeds", "kind": "pick", "choices": _driver_choices, "once": True},
            {"name": "section", "label": "Section", "kind": "text", "suggestions": _section_names, "max_length": 60},
            {"name": "order", "label": "Order", "kind": "number", "min": 0, "max": LARGEST_ORDER,
             "help": "Questions are asked from the lowest number up, within their section."},
            {"name": "text", "label": "Wording", "kind": "text",
             "help": "A sentence about the team. Yes means the sentence is true."},
            {"name": "help_text", "label": "Help text", "kind": "text", "required": False, "table": False,
             "help": "Optional. A short line under the question that helps people answer it."},
            {"name": "kind", "label": "Kind of answer", "kind": "pick", "table": False,
             "choices": [{"value": "yes_no", "label": "Yes or no"}, {"value": "number", "label": "A number"},
                         {"value": "text", "label": "A choice of answers (from the trigger)"},
                         {"value": "tick_any", "label": "Tick any that apply (options from the trigger or listed here)"}]},
            {"name": "options", "label": "Options to tick", "kind": "text", "required": False, "table": False, "max_length": 1000,
             "only_when": {"field": "kind", "is": "tick_any"},
             "help": "Optional. Separate the options with | (a bar). Options the trigger asks for are added. None of these is always last."},
            {"name": "switches_on", "label": "The driver is on when the answer is", "kind": "pick", "table_label": "Driver is on when",
             "choices": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}],
             "only_when": {"field": "kind", "is": "yes_no"}},
            {"name": "test", "label": "The driver is on when the number is", "kind": "pick",
             "choices": [{"value": test, "label": test.capitalize()} for test in (drivers.AT_LEAST, drivers.MORE_THAN, drivers.AT_MOST, drivers.LESS_THAN)],
             "only_when": {"field": "kind", "is": "number"}, "table": False},
            {"name": "number", "label": "The number", "kind": "number", "min": -LARGEST_ANSWER_NUMBER, "max": LARGEST_ANSWER_NUMBER, "table": False,
             "only_when": {"field": "kind", "is": "number"},
             "help": "For a share, give a part of one: 0.40 means 40%."}],
        "make_key": _question_key, "title_of": lambda values: values["text"],
        "entry_fields": _question_fields, "table_text": _question_table_text,
        "sort": lambda entry: (entry["values"]["section"], entry["values"]["order"]),
        "from_file": _file_questions, "check": _check_question, "moves": rating_moves,
        "notes": ["The driver rules themselves are not changed: only the answer or number that switches a driver on."]},
    "driver-triggers": {
        "name": "Drivers with a full trigger",
        "intro": "A driver's trigger says when it is on. Most are one simple comparison, edited on the Questions page. These ones use more of the trigger language (and, or, not, text answers, to_int), so they are edited here as text.",
        "grows": False, "who_text": "Tech Risk",
        "needs_registers": True,
        "fields": [
            {"name": "driver", "label": "Driver", "kind": "text", "readonly": True},
            {"name": "what", "label": "What it says", "kind": "text", "readonly": True},
            {"name": "trigger", "label": "Trigger", "kind": "text", "max_length": trigger_language.LONGEST_TRIGGER,
             "help": "For example: (get('RD35') == 'Broadly used, across teams') or (to_int(get('RD65')) >= 1) and not get('RD01'). "
                     "Text goes in quotes. Join tests with and, or; use not or ! for the opposite; brackets group."}],
        "title_of": lambda values: values["driver"],
        "from_file": _file_driver_triggers, "check": _check_driver_trigger, "moves": rating_moves,
        "notes": ["The trigger is checked before it is saved: if it can't be read, you are told where it stops.",
                  "A driver is on exactly when its trigger is true. If every answer it looks at is missing, the driver is 'not known' and is never counted as on."]},
    "building-blocks": {
        "name": "Each risk's building block",
        "intro": "Which TRUST building block each risk belongs to. A risk's own placement wins; otherwise its domain's placement is used.",
        "grows": True, "who_text": "Tech Risk",
        "needs_registers": True,
        "fields": [
            {"name": "applies_to", "label": "Placed by", "kind": "pick", "once": True,
             "choices": [{"value": "risk", "label": "One risk"}, {"value": "domain", "label": "A whole domain"}]},
            {"name": "name", "label": "Risk id or domain", "kind": "text", "once": True,
             "help": "A risk's id (air.ops.01) or a domain (Cyber)."},
            {"name": "block", "label": "Building block", "kind": "pick", "choices": _block_choices}],
        "make_key": lambda values, from_files: f"{values['applies_to']}:{values['name']}",
        "title_of": lambda values: f"{values['name']} ({'risk' if values['applies_to'] == 'risk' else 'domain'})",
        "from_file": _file_blocks, "check": _check_block,
        "notes": ["Display only: this changes no TRUST score."]},
    "data-drivers": {
        "name": "Drivers answered from data",
        "intro": "For each driver the site answers from TRUST's data: what it is compared with, and the starting values (a language list, a share, a number of teams). These are starting values for Tech Risk to tune.",
        "grows": False, "who_text": "Tech Risk",
        "needs_registers": True,
        "fields": [
            {"name": "driver", "label": "Driver", "kind": "text", "readonly": True},
            {"name": "what", "label": "What it says", "kind": "text", "readonly": True},
            {"name": "basis", "label": "Compared with", "kind": "pick",
             "choices": [{"value": basis, "label": label} for basis, label in data_drivers.BASIS_LABELS.items()]},
            {"name": "share_of_median", "label": "Share of the prevailing median (%)", "kind": "number", "min": 1, "max": 100,
             "only_when": {"field": "basis", "is": data_drivers.BASIS_SHARE},
             "help": "A team is flagged when it is below this share of the prevailing median. 70 means 70%. Starting value."},
            {"name": "fixed_number", "label": "The fixed number", "kind": "number", "min": -LARGEST_FIXED_NUMBER, "max": LARGEST_FIXED_NUMBER,
             "only_when": {"field": "basis", "is": data_drivers.BASIS_FIXED},
             "help": "For the number of other teams, a team is flagged when more than this many made commits. Starting value."},
            {"name": "languages", "label": "Languages that switch it on", "kind": "text", "required": False,
             "only_when": {"field": "basis", "is": data_drivers.BASIS_LANGUAGES},
             "help": "Separated by commas, for example Perl, C, C++, PHP. Starting value."},
            {"name": "left_out_languages", "label": "Languages left out of the count", "kind": "text", "required": False, "table": False,
             "help": "Markup and configuration languages that are not a running process type, separated by commas. Starting value."}],
        "entry_fields": _data_driver_fields,
        "title_of": lambda values: values["driver"],
        "from_file": _file_data_drivers, "check": _check_data_driver,
        "notes": ["The calculations are in config/risk_data_drivers.json (which driver code each one answers). A driver with no calculation shows 'not known' on the form.",
                  "A saved change is used the next time a team's form is opened or submitted. Saved assessments don't change."]},
    "calculations": {
        "name": "Calculations you define",
        "intro": "Define how a driver is answered from data, with no code: pick the driver, pick a team figure TRUST already works out, and pick a test. A brand-new figure still needs code.",
        "grows": True, "who_text": "Tech Risk",
        "needs_registers": True,
        "fields": [
            {"name": "driver", "label": "Driver", "kind": "pick", "choices": _driver_choices, "once": True},
            {"name": "figure", "label": "Team figure", "kind": "pick",
             "choices": [{"value": name, "label": figure["label"]} for name, figure in team_figures.FIGURES.items()]},
            {"name": "test", "label": "The driver is on when the team's figure", "kind": "pick", "table_label": "Driver is on when the figure",
             "choices": [{"value": name, "label": test["label"]} for name, test in team_figures.TESTS.items()]},
            {"name": "number_or_share", "label": "Number or share", "kind": "number", "required": False,
             "min": -LARGEST_FIXED_NUMBER, "max": LARGEST_FIXED_NUMBER,
             "help": "Only for the last three tests. A share is a part of one: 0.70 means 70% of the prevailing median. A number is compared as it is. Leave empty for the two median tests."}],
        "make_key": lambda values, from_files: values["driver"],
        "title_of": lambda values: values["driver"],
        "table_text": _table_text_defined_calculation,
        "from_file": _file_defined_calculations, "check": _check_defined_calculation,
        "notes": ["Each driver has one calculation. A driver answered by a built-in calculation or by a question can't be defined here.",
                  "The prevailing median is TRUST's own: the median of the teams' figures that month, and it needs the same fewest teams as the scorecard.",
                  "A figure whose data isn't loaded shows 'not known' and is never counted as on. A saved change is used the next time a team's form is opened or submitted. Saved assessments don't change.",
                  "The rating rules don't change here: the driver is answered ON or OFF, and the rating reads it as before."]},
    "metric-risks": {
        "name": "Risks each metric watches",
        "intro": "For each metric, the risks it watches, named by the Risk site's risk IDs. They drive the CTO view's Elevated risk markers and the risks shown on the metric's dictionary card. The metrics themselves are not added or retired here.",
        "grows": False, "who_text": "Tech Risk",
        "fields": [
            {"name": "metric_id", "label": "Metric", "kind": "text", "readonly": True},
            {"name": "name", "label": "Name (from the metrics file)", "kind": "text", "readonly": True},
            {"name": "risk_ids", "label": "Risks it watches (risk IDs)", "kind": "text", "required": False, "max_length": 500,
             "help": "Risk IDs from the Risk site, separated by commas, for example air.cyber.01, air.ops.01. Leave empty for none."}],
        "title_of": lambda values: f"{values['metric_id']} {values['name']}",
        "from_file": _file_metric_risks, "current": _current_metrics_only, "check": _check_metric_risks,
        "notes": ["The metrics file's values are the starting point. A change saved here wins over the file.",
                  "Display only: nothing here changes a TRUST score, status or threshold."]},
}
SLUGS = list(LISTS)


def describe(slug):
    """The description of a list, or ValueError. Plain data only, so it can be sent to the page."""
    if slug not in LISTS:
        raise ValueError("There is no such list.")
    return LISTS[slug]


# ---------------------------------------------------------------------------------------------------
# The entries of a list now
# ---------------------------------------------------------------------------------------------------

def _from_file(slug, from_files):
    description = describe(slug)
    if description.get("needs_registers") and from_files is None:
        from_files = _raw()
    return [{"key": entry["key"], "values": entry["values"], "retired": False}
            for entry in description["from_file"](from_files)]


def entries_now(slug, from_files=None, rows=None):
    """The entries of a list as the site has them: [{"key", "values", "retired"}], in the order they were added.
    from_files is read only for a list that needs the risk registers and has nothing saved yet."""
    description = describe(slug)
    rows = storage.list_changes(slug) if rows is None else rows
    if description["grows"] and rows:
        entries = {}
    else:
        entries = {entry["key"]: entry for entry in _from_file(slug, from_files)}
    for row in rows:
        _apply_row(entries, row)
    kept = list(entries.values())
    return description["current"](kept) if description.get("current") else kept


def _apply_row(entries, row):
    """Put one saved change on the entries (a dict by key)."""
    if row["action"] == LOAD:
        entries.clear()
        for entry in row["after"]:
            entries[entry["key"]] = {"key": entry["key"], "values": entry["values"], "retired": False}
    elif row["action"] in (ADD, EDIT) and row["after"]:
        retired = entries[row["key"]]["retired"] if row["key"] in entries and row["action"] == EDIT else False
        entries[row["key"]] = {"key": row["key"], "values": row["after"]["values"], "retired": retired}
    elif row["action"] in (RETIRE, RESTORE) and row["key"] in entries:
        entries[row["key"]]["retired"] = row["action"] == RETIRE


def _sorted(slug, entries):
    sorter = describe(slug).get("sort")
    return sorted(entries, key=sorter) if sorter else entries


# ---------------------------------------------------------------------------------------------------
# Fields: what each kind accepts
# ---------------------------------------------------------------------------------------------------

def fields_for(slug, key=None, from_files=None):
    """The list's fields with their choices worked out. A setting can say how its Value reads (entry_fields)."""
    description = describe(slug)
    overrides = description["entry_fields"](key, from_files) if description.get("entry_fields") and key else {}
    fields = []
    for field in description["fields"]:
        field = {**field, **overrides.get(field["name"], {})}
        if callable(field.get("choices")):
            field["choices"] = field["choices"](from_files)
        field["choices"] = [choice if isinstance(choice, dict) else {"value": choice, "label": choice}
                            for choice in field.get("choices") or []] or None
        if callable(field.get("suggestions")):
            field["suggestions"] = field["suggestions"](from_files)
        fields.append(field)
    return fields


def _clean_number(value, field):
    label = field["label"]
    if value in (None, "") and not field.get("required", True):
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError(f"{label}: give a number.") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label}: give a number.")
    low, high = field.get("min"), field.get("max")
    if (low is not None and number < low) or (high is not None and number > high):
        raise ValueError(f"{label}: give a number from {low:g} to {high:g}.")
    return int(number) if number == int(number) and abs(number) < LARGEST_WHOLE_NUMBER else number


def _clean_one(field, value):
    """One typed value, as it will be kept; a ValueError says what is wrong in plain words."""
    kind, label = field["kind"], field["label"]
    if kind == "number":
        return _clean_number(value, field)
    if kind == "yes_no":
        answer = drivers.as_yes_no(value)
        if answer is None:
            raise ValueError(f"{label}: choose Yes or No.")
        return answer
    text = tidy_spaces(value)
    if text == "":
        if field.get("required", True):
            raise ValueError(f"{label}: fill this in.")
        return ""
    if kind == "pick":
        allowed = [choice["value"] for choice in field["choices"] or []]
        if text not in allowed:
            raise ValueError(f"{label}: choose one of the choices.")
        return text
    longest = field.get("max_length") or LONGEST_TEXT
    if len(text) > longest:
        raise ValueError(f"{label}: {longest} characters at most.")
    return text.lower() if field.get("lowercase") else text


def clean_values(slug, key, typed, existing, action, from_files=None):
    """The typed values, tidied. A read-only field, and a field fixed once added, keep the value they have.
    A field that doesn't apply (a number for a yes-or-no question) is empty."""
    typed = typed if isinstance(typed, dict) else {}
    cleaned = {}
    for field in fields_for(slug, key, from_files):
        name = field["name"]
        applies = True
        if field.get("only_when"):
            applies = cleaned.get(field["only_when"]["field"]) == field["only_when"]["is"]
        if not applies:
            cleaned[name] = None
        elif field.get("readonly") or (field.get("once") and action == EDIT):
            cleaned[name] = (existing or {}).get(name)
        else:
            cleaned[name] = _clean_one(field, typed.get(name))
    return cleaned


# ---------------------------------------------------------------------------------------------------
# A change: check it, show it, keep it
# ---------------------------------------------------------------------------------------------------

def _shown(field, value):
    if value is None or value == "":
        return ""
    if field["kind"] == "yes_no":
        return "Yes" if value else "No"
    if field["kind"] == "pick":
        label = {choice["value"]: choice["label"] for choice in field.get("choices") or []}.get(value)
        return label or str(value)
    if field["kind"] == "number":
        return f"{value:g}" if isinstance(value, (int, float)) else str(value)
    return str(value)


def _differences(slug, key, before, after, from_files=None):
    """What differs between two sets of values: [{"label", "before", "after"}], in the list's field order."""
    differences = []
    for field in fields_for(slug, key, from_files):
        old, new = (before or {}).get(field["name"]), (after or {}).get(field["name"])
        if old != new and not (old in (None, "") and new in (None, "")):
            differences.append({"label": field["label"], "before": _shown(field, old), "after": _shown(field, new)})
    return differences


def check_change(slug, action, key, typed, from_files=None):
    """Check one change and say what it is: {"action","key","entries","before","after","differences"}.
    `entries` are all the entries as they would be after it. Raises ValueError with a plain reason."""
    description = describe(slug)
    if description.get("needs_registers") and from_files is None:
        from_files = _raw()
    if action not in (ADD, EDIT, RETIRE, RESTORE):
        raise ValueError("Choose add, edit, retire or restore.")
    if action in (ADD, RETIRE, RESTORE) and not description["grows"]:
        raise ValueError(f"The entries of '{description['name']}' are fixed: you can edit them, not add or retire them.")
    entries = entries_now(slug, from_files)
    by_key = {entry["key"]: entry for entry in entries}
    if action == ADD:
        values = clean_values(slug, None, typed, None, ADD, from_files)
        key = description["make_key"](values, from_files)
    else:
        if key not in by_key:
            raise ValueError("That entry isn't in the list.")
        if action == RETIRE and by_key[key]["retired"]:
            raise ValueError("That entry is already retired.")
        if action == RESTORE and not by_key[key]["retired"]:
            raise ValueError("That entry isn't retired.")
        values = clean_values(slug, key, typed, by_key[key]["values"], action, from_files) if action == EDIT else by_key[key]["values"]
    if action in (ADD, EDIT) and description.get("check"):
        description["check"](action, key, values, entries, from_files)
    before = by_key[key]["values"] if key in by_key else None
    if action == EDIT and before == values:
        raise ValueError("Nothing is different from what is saved.")
    return {"action": action, "key": key, "entries": _entries_after(entries, action, key, values), "before": before, "after": values,
            "differences": _differences(slug, key, before, values if action in (ADD, EDIT) else before, from_files)}


def _entries_after(entries, action, key, values):
    """All the entries as they would be once this one change is made."""
    if action == ADD:
        return entries + [{"key": key, "values": values, "retired": False}]
    after = []
    for entry in entries:
        if entry["key"] == key:
            if action == EDIT:
                entry = dict(entry, values=values)
            elif action == RETIRE:
                entry = dict(entry, retired=True)
            elif action == RESTORE:
                entry = dict(entry, retired=False)
        after.append(entry)
    return after


def preview(slug, action, key, typed):
    """What saving would do: the change, and every rating that would move when the list can move a rating.
    Nothing is saved."""
    description = describe(slug)
    from_files = _raw()
    checked = check_change(slug, action, key, typed, from_files)
    result = {"action": action, "key": checked["key"], "title": description["title_of"](checked["after"] or checked["before"]),
              "differences": checked["differences"], "can_move_ratings": bool(description.get("moves"))}
    if description.get("moves"):
        result["moves"] = description["moves"](from_files, slug, checked["entries"])
    return result


def save(slug, action, key, typed, by, reason):
    """Check and keep one change, with who and why. Returns what was kept (see history_of)."""
    reason = tidy_spaces(reason)
    from_files = _raw()
    checked = check_change(slug, action, key, typed, from_files)
    if not reason:
        raise ValueError("Say why, so the record shows the reason for the change.")
    if len(reason) > LONGEST_REASON:
        raise ValueError(f"That reason is too long ({LONGEST_REASON:,} characters at most).")
    rows = []
    description = describe(slug)
    if description["grows"] and not storage.list_changes(slug):
        loaded = [{"key": entry["key"], "values": entry["values"]} for entry in entries_now(slug, from_files)]
        rows.append({"key": WHOLE_LIST, "action": LOAD, "before": None, "after": loaded, "reason": FIRST_LOAD_REASON})
    was = next((entry for entry in entries_now(slug, from_files) if entry["key"] == checked["key"]), None)
    rows.append({"key": checked["key"], "action": action, "reason": reason,
                 "before": {"values": was["values"], "retired": was["retired"]} if was else None,
                 "after": {"values": checked["after"], "retired": action == RETIRE}})
    storage.add_list_changes(slug, rows, by)
    return checked["differences"]


# ---------------------------------------------------------------------------------------------------
# What the page is sent
# ---------------------------------------------------------------------------------------------------

def description_for_page(slug, from_files):
    """The list's description with everything the page draws from, and no functions."""
    description = describe(slug)
    return {"slug": slug, "name": description["name"], "intro": description["intro"], "grows": description["grows"],
            "who_text": description["who_text"], "notes": description.get("notes") or [],
            "can_move_ratings": bool(description.get("moves")), "fields": fields_for(slug, None, from_files)}


def entries_for_page(slug, from_files):
    description = describe(slug)
    entries = []
    for entry in _sorted(slug, entries_now(slug, from_files)):
        fields = fields_for(slug, entry["key"], from_files)
        entries.append({"key": entry["key"], "title": description["title_of"](entry["values"]), "retired": entry["retired"],
                        "values": entry["values"], "fields": fields,
                        "shown": {**{field["name"]: _shown(field, entry["values"].get(field["name"])) for field in fields},
                                  **(description["table_text"](entry["values"]) if description.get("table_text") else {})}})
    return entries


def history_of(slug, from_files=None):
    """Every change to the list, newest first, for everyone who can see the page."""
    description = describe(slug)
    shown = []
    for row in reversed(storage.list_changes(slug)):
        if row["action"] == LOAD:
            title, what = "The whole list", [{"label": "First load from the file",
                                              "before": "", "after": f"{len(row['after'])} entries"}]
        else:
            now = (row["after"] or {}).get("values") or (row["before"] or {}).get("values") or {}
            title = description["title_of"](now) if now else row["key"]
            if row["action"] in (RETIRE, RESTORE):
                what = [{"label": "Status", "before": "Retired" if row["action"] == RESTORE else "In use",
                         "after": "Retired" if row["action"] == RETIRE else "In use"}]
            else:
                what = _differences(slug, row["key"], (row["before"] or {}).get("values"), now, from_files)
        shown.append({"id": row["id"], "at": row["at"], "by": row["by"], "key": row["key"], "title": title,
                      "action": row["action"], "what": what, "reason": row["reason"]})
    return shown


def list_payload(slug):
    from_files = _raw()
    return {"list": description_for_page(slug, from_files), "entries": entries_for_page(slug, from_files),
            "history": history_of(slug, from_files),
            "can_save": access.may_act_as_tech_risk(g.person), "open": g.person["open"]}


# ---------------------------------------------------------------------------------------------------
# The download: the current list, with retired entries marked
# ---------------------------------------------------------------------------------------------------

def download_rows(slug):
    from_files = _raw()
    rows = []
    for entry in _sorted(slug, entries_now(slug, from_files)):
        rows.append({"key": entry["key"], "retired": entry["retired"], **entry["values"]})
    return rows


def _safe_in_a_spreadsheet(value):
    """A value for a CSV cell. Text that starts with = + - @ would run as a formula when the file is opened in Excel,
    so it gets an apostrophe in front. Numbers and yes or no stay as they are."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def download_text(slug, kind):
    rows = download_rows(slug)
    if kind == "json":
        return json.dumps({"list": slug, "entries": rows}, indent=2), "application/json; charset=utf-8", "json"
    columns = ["key", "retired"] + [field["name"] for field in describe(slug)["fields"]]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: _safe_in_a_spreadsheet(row.get(name)) for name in columns})
    return out.getvalue(), "text/csv; charset=utf-8", "csv"


# ---------------------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------------------

@bp.get("/api/edit")
def lists_index():
    """The lists, for the Edit menu."""
    return jsonify(ok=True, can_save=access.may_act_as_tech_risk(g.person), open=g.person["open"],
                   lists=[{"slug": slug, "name": LISTS[slug]["name"], "intro": LISTS[slug]["intro"],
                           "entries": sum(1 for entry in entries_now(slug) if not entry["retired"])} for slug in SLUGS])


@bp.get("/api/edit/<slug>")
def list_get(slug):
    describe(slug)
    return jsonify(ok=True, **list_payload(slug))


def _may_save_or_stop(slug):
    """Every list is Tech Risk's to change (and anyone's while TRUST runs open)."""
    describe(slug)
    if not access.may_act_as_tech_risk(g.person):
        raise trust_web().NotAllowed()


@bp.post("/api/edit/<slug>/preview")
def list_preview(slug):
    _may_save_or_stop(slug)
    body = request.get_json(silent=True) or {}
    return jsonify(ok=True, **preview(slug, str(body.get("action") or ""), str(body.get("key") or ""), body.get("values")))


@bp.post("/api/edit/<slug>/save")
def list_save(slug):
    _may_save_or_stop(slug)
    body = request.get_json(silent=True) or {}
    saved = save(slug, str(body.get("action") or ""), str(body.get("key") or ""), body.get("values"),
                 trust_web()._who(body), body.get("reason"))
    return jsonify(ok=True, saved=saved, **list_payload(slug))


@bp.get("/api/edit/<slug>/download")
def list_download(slug):
    describe(slug)
    text, content_type, extension = download_text(slug, "json" if request.args.get("format") == "json" else "csv")
    return Response(text, content_type=content_type,
                    headers={"Content-Disposition": f'attachment; filename="{slug}.{extension}"'})
