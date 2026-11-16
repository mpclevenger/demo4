"""Rates every risk for one group from its saved answers, and tells where a group's form stands.

The ratings come from drivers.py and rating.py (nothing is worked out again here). This file puts them in order:

    saved answers -> driver answers -> which drivers are on -> each risk rated -> how it reads for a person

Nothing here reads or writes the database. The caller gives it the answers and keeps the result.
"""
from trust.risk import blocks, drivers, explain, questions as question_list, rating

NOT_STARTED = "Not started"
DRAFT = "Draft"
SUBMITTED = "Submitted"


# ---------------------------------------------------------------------------------------------------
# The group's saved answers
# ---------------------------------------------------------------------------------------------------

def latest_answers(answer_rows):
    """The newest saved answer of each question: {"RD01": {"answer", "by", "at", "from_tech_risk"}, ...}.
    answer_rows is every saved answer for the group, oldest first, so a later save replaces an earlier one."""
    latest = {}
    for row in answer_rows:
        latest[row["question"]] = {"answer": row["answer"], "by": row["by"], "at": row["at"],
                                   "from_tech_risk": row.get("from_tech_risk", False)}
    return latest


def answer_text(latest):
    """{question: answer} for the answered questions only."""
    return {question: saved["answer"] for question, saved in latest.items()
            if question_list.is_answered(saved["answer"])}


def status_of(answer_rows, assessment_rows):
    """Not started, Draft, or Submitted.

    Submitted means the group's newest assessment was made from the answers it has now. An answer changed after
    the Submit makes it a Draft again, until it is submitted again."""
    answers_now = answer_text(latest_answers(answer_rows))
    if assessment_rows and assessment_rows[-1]["result"]["answers"] == answers_now:
        return SUBMITTED
    if answer_rows or assessment_rows:
        return DRAFT
    return NOT_STARTED


# ---------------------------------------------------------------------------------------------------
# One assessment
# ---------------------------------------------------------------------------------------------------

def named(codes, driver_rules):
    """Driver codes with their plain names: [{"code": "RD01", "text": "..."}]."""
    return [{"code": code, "text": driver_rules[code].get("rationale") or code} for code in codes]


def assess_group(risks, driver_rules, form_questions, saved, settings, placements, previous_result=None):
    """Every risk rated for one group.

    risks            as trust.config.risks() gives them
    driver_rules     as files.driver_rules gives them
    form_questions   as questions.build gives them
    saved            the group's answered questions, {question field: answer text}, as answer_text gives them
    settings         as rating.starting_settings gives them
    placements       as blocks.load gives them
    previous_result  the group's last assessment's result, for the trend; None for a first assessment
    """
    # 1. The saved answers, as the driver rules read them. Drivers answered from data have none yet.
    answers = question_list.answers_by_field(form_questions, saved)

    # 2. Which drivers are on, off, or not known yet. A driver not known yet is never counted as on.
    driver_states = drivers.drivers_for_group(driver_rules, answers)
    active_drivers = set(driver_states["on"])

    # 3. Each risk: applies, likelihood, impact by kind, overall impact, Elevated.
    ratings = rating.rate_group(risks, active_drivers, settings)

    # 4. Each risk as the results page shows it.
    result_risks = {}
    for risk_id, rated in ratings.items():
        risk = risks[risk_id]
        drivers_on = sorted((rating.own_drivers(risk) & active_drivers))
        entry = {**rated,
                 "name": risk.get("name") or risk_id,
                 "domain": risk.get("domain"),
                 "block": blocks.block_of(risk_id, risk, placements),
                 "drivers_on": named(drivers_on, driver_rules),
                 "steps": explain.steps_for_risk(risk, active_drivers, rated, settings)}
        before = (previous_result or {}).get("risks", {}).get(risk_id)
        entry["trend"] = rating.trend(before, entry)
        result_risks[risk_id] = entry

    applicable = [entry for entry in result_risks.values() if entry["applicable"]]
    elevated = [entry for entry in applicable if entry["elevated"]]
    return {
        "answers": dict(saved),
        "settings": settings,
        "drivers": {state: named(codes, driver_rules) for state, codes in driver_states.items()},
        "risks": result_risks,
        "counts": {"risks": len(result_risks), "applicable": len(applicable),
                   "not_applicable": len(result_risks) - len(applicable), "elevated": len(elevated)},
        "has_previous": previous_result is not None,
    }
