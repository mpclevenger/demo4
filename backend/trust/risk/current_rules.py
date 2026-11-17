"""Rate every team's newest answers with today's rules (owner, 17 Nov 2026).

The switch is the setting `rate_with_current_rules` (config/risk_settings.json; Tech Risk changes it at Edit, Rating
settings). It exists so that a change to the risks, the drivers, the questions, the rating settings or the data shows
up on the results pages right away, without every team submitting again. It is meant for now, until more history has
built up.

    Switch OFF: every page shows the result kept when the team submitted. Nothing here runs.
    Switch ON:  every page that shows or uses a team's assessment gets that assessment's result worked out again, from
                the answers kept with it (the answers as they were at its Submit) with today's risks, driver rules,
                questions, rating settings and data drivers. It is the same function the Submit uses
                (data_drivers.assess_with_data). The kept result is never changed or deleted.

Every place that read `storage.risk_assessments` to SHOW a result now reads `assessments()` here instead. The rows have
the same shape. Two keys are added to a worked-out result:
    rated_with_current_rules   True
    differs_from_kept          True when today's rating (which risks apply, their likelihood, impact and whether they
                               are Elevated) is not the one kept at Submit. The sign-off box says so.

Speed: a page asks for the rows of one team or of all teams. The registers are loaded once and each assessment is worked
out once per request (kept on Flask's `g`), so a page of 15 teams works them out one time each.
"""
from flask import g, has_request_context

from trust import storage
from trust.risk import data_drivers
from trust.risk.registers import load_registers

SETTING_NAME = "rate_with_current_rules"
SWITCH_IS_ON_WORDS = ("yes", "true", "on")
THE_LINE = "Rated with today's questions and rules (setting rate_with_current_rules is on)."
ASSESSMENT_FACTS = ("applicable", "likelihood", "impact", "elevated")


def switch_is_on(settings):
    """True when the setting is on. The file holds true or false; the editing page holds yes or no."""
    value = settings.get(SETTING_NAME)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in SWITCH_IS_ON_WORDS


def _request_memory():
    """A dictionary kept for this request only, or a fresh one when there is no request (a command or a test)."""
    if not has_request_context():
        return {}
    if not hasattr(g, "current_rules_memory"):
        g.current_rules_memory = {}
    return g.current_rules_memory


def _registers(memory):
    if "registers" not in memory:
        memory["registers"] = load_registers()
    return memory["registers"]


def facts_of(result):
    """The parts of a result a person would call "the rating": for each risk, whether it applies and its levels."""
    return {risk_id: tuple(entry.get(name) for name in ASSESSMENT_FACTS) for risk_id, entry in result["risks"].items()}


def rate_again(kept_result, previous_result, loaded, data_answers):
    """One kept result worked out again from the answers kept with it, with today's rules."""
    answers = kept_result.get("answers") or {}
    worked_out = data_drivers.assess_with_data(loaded["risks"], loaded["driver_rules"], loaded["questions"], answers,
                                               loaded["settings"], loaded["placements"], previous_result, data_answers)
    worked_out["controls_fetched_at"] = kept_result.get("controls_fetched_at")
    worked_out["rated_with_current_rules"] = True
    worked_out["differs_from_kept"] = facts_of(worked_out) != facts_of(kept_result)
    return worked_out


def _rate_a_group(group_id, kept_rows, memory):
    """The group's rows, oldest first, each with its result worked out again. Each row's trend is read against the
    row before it, as it is at Submit."""
    loaded = _registers(memory)
    if "data" not in memory:
        memory["data"] = data_drivers.current(loaded["driver_rules"], loaded.get("from_files"))
    data_answers = memory["data"].get(group_id) or {}
    rated_rows = []
    previous_result = None
    for kept_row in kept_rows:
        result = rate_again(kept_row["result"], previous_result, loaded, data_answers)
        rated_rows.append({**kept_row, "result": result, "kept_result": kept_row["result"]})
        previous_result = result
    return rated_rows


def assessments(group_id=None):
    """The same rows as storage.risk_assessments (oldest first, for one team or for all), with each result worked out
    with today's rules when the switch is on. With the switch off these are the kept rows, untouched."""
    kept_rows = storage.risk_assessments(group_id)
    memory = _request_memory()
    if not switch_is_on(_registers(memory)["settings"]):
        return kept_rows
    by_group = {}
    for row in kept_rows:
        by_group.setdefault(row["group_id"], []).append(row)
    worked_out = []
    for one_group_id, rows in by_group.items():
        key = ("rated", one_group_id, rows[-1]["id"], len(rows))
        if key not in memory:
            memory[key] = _rate_a_group(one_group_id, rows, memory)
        worked_out.extend(memory[key])
    return sorted(worked_out, key=lambda row: row["id"])


def line_for(settings=None):
    """The one short line the pages show when the switch is on, else None."""
    if settings is None:
        settings = _registers(_request_memory())["settings"]
    return THE_LINE if switch_is_on(settings) else None
