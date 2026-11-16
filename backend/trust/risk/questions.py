"""The questionnaire: which questions the form asks, and how the answers turn into driver answers.

The risk files give every driver a rule (RD12 is on when the answer is at least 3) and a plain reason
(rationale). They don't give the questions' own wording or sections, so build() makes a first form from the
drivers file:

    one question for each questionnaire field of a driver
    the question reads as the driver's rationale, a sentence about the team
    a question is yes or no when its driver's rule is "is yes" or "is no", and a number otherwise
    a question sits in the section named after the domain of the first risk that lists its driver

That first form is only the starting point. Tech Risk can load the owner's own questionnaire (seed.py) and edit
the questions (the "Questions" list in editable.py); once either has saved something, the site uses those
questions, with their own wording, sections, order and answer that switches the driver on.

Drivers with no questionnaire field are answered from data, so they have no question here. A question's
field is the name the driver's rule reads (RD12, RD14_pct), so the answer reaches the rule by that name.

"Yes" always means the sentence is true for the team, which is when the driver is on. For a driver whose
rule is "is no" (the driver is on when the field's answer is no), the answer is turned around before the
rule is read. That turning is done in one place: answers_by_field.
"""
from trust.risk import drivers, expressions, rating
from trust.words import tidy_spaces

YES_NO = "yes_no"
NUMBER = "number"
OTHER_SECTION = "Other questions"

LONGEST_ANSWER = 40                                      # characters; a number or a yes or a no
SHARE_FIELD_ENDING = "_pct"                              # the driver rules name a share field this way, e.g. RD14_pct


def section_for_driver(driver_code, risks):
    """The domain of the first risk (in risk ID order) that lists the driver, or OTHER_SECTION."""
    for risk_id in sorted(risks):
        risk = risks[risk_id]
        if driver_code in rating.own_drivers(risk):
            return str(risk.get("domain") or OTHER_SECTION)
    return OTHER_SECTION


def build(driver_rules, risks):
    """Every question, in section order, then driver order.

    driver_rules  as files.driver_rules gives them: {"RD01": {"field": "RD01", "test": "is yes", ...}, ...}
    risks         as trust.config.risks() gives them

    Each question: {"field", "driver", "section", "text", "kind", "yes_means_field_is"}
    """
    found = []
    for driver_code in sorted(driver_rules):
        rule = driver_rules[driver_code]
        for field in rule.get("questionnaire_fields") or []:
            is_yes_no = rule["test"] in (drivers.IS_YES, drivers.IS_NO)
            found.append({
                "field": field,
                "driver": driver_code,
                "section": section_for_driver(driver_code, risks),
                "text": rule.get("rationale") or driver_code,
                "kind": YES_NO if is_yes_no else NUMBER,
                "yes_means_field_is": rule["test"] == drivers.IS_YES if is_yes_no else None,
            })
    section_names = sorted({q["section"] for q in found}, key=lambda name: (name == OTHER_SECTION, name))
    found.sort(key=lambda q: (section_names.index(q["section"]), q["driver"], q["field"]))
    return found


def sections(questions):
    """The questions grouped for the form, in order: [{"name": "Change", "questions": [...]}, ...]"""
    grouped = []
    for question in questions:
        if not grouped or grouped[-1]["name"] != question["section"]:
            grouped.append({"name": question["section"], "questions": []})
        grouped[-1]["questions"].append(question)
    return grouped


def clean_answer(question, typed):
    """The answer as it will be kept, or a ValueError saying what is wrong. An empty answer clears the question."""
    text = tidy_spaces(typed)
    if text == "":
        return ""
    if len(text) > LONGEST_ANSWER:
        raise ValueError(f"That answer is longer than {LONGEST_ANSWER} characters.")
    if question["kind"] == YES_NO:
        yes_or_no = drivers.as_yes_no(text)
        if yes_or_no is None:
            raise ValueError("Answer yes or no.")
        return "yes" if yes_or_no else "no"
    number = drivers.as_number(text)
    if number is None:
        raise ValueError("Type a number. For a percent, type the % sign, for example 25%.")
    # A share is read as a part of one (0.25 = 25%). A plain number above one, like "25", was meant as a percent
    # but would be read as 25 whole shares, so it is refused rather than guessed.
    if is_share(question) and number > expressions.WHOLE_SHARE:
        raise ValueError(f"This answer is a share. Type it with the % sign, for example {text}%, or as a part of one, for example 0.25.")
    return text


def is_share(question):
    """A question whose driver rule reads a share (its field ends in _pct, for example RD14_pct)."""
    return question["field"].lower().endswith(SHARE_FIELD_ENDING)


def is_answered(answer):
    return answer not in (None, "")


def answers_by_field(questions, saved):
    """The group's answers, as the driver rules read them: {"RD01": True, "RD12": "4", ...}.

    saved  {question field: answer text} for the group, the latest answer of each question
    """
    by_field = {}
    for question in questions:
        answer = saved.get(question["field"])
        if not is_answered(answer):
            continue
        if question["kind"] == NUMBER:
            by_field[question["field"]] = answer
            continue
        sentence_is_true = drivers.as_yes_no(answer)
        if sentence_is_true is None:                      # not a yes or no: treat the question as not answered
            continue
        field_is_true = sentence_is_true if question["yes_means_field_is"] else not sentence_is_true
        by_field[question["field"]] = field_is_true
    return by_field


def unanswered(questions, saved):
    """The questions with no answer yet, in form order."""
    return [question for question in questions if not is_answered(saved.get(question["field"]))]

