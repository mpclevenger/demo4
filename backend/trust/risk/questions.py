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
from trust.risk import drivers, expressions, rating, trigger_language
from trust.words import tidy_spaces

YES_NO = "yes_no"
NUMBER = "number"
TEXT = "text"                                            # an answer picked from the texts the driver's trigger compares it with
OTHER_ANSWER = "Other"                                   # the form's last choice for a text question: none of the choices
OTHER_SECTION = "Other questions"

LONGEST_ANSWER = 40                                      # characters; a number or a yes or a no
LONGEST_TEXT_ANSWER = 200                                # characters; a chosen text answer
SHARE_FIELD_ENDING = "_pct"                              # the driver rules name a share field this way, e.g. RD14_pct


def section_for_driver(driver_code, risks):
    """The domain of the first risk (in risk ID order) that lists the driver, or OTHER_SECTION."""
    for risk_id in sorted(risks):
        risk = risks[risk_id]
        if driver_code in rating.own_drivers(risk):
            return str(risk.get("domain") or OTHER_SECTION)
    return OTHER_SECTION


def uses_of_field(rule, field):
    """How a driver's full trigger uses one field: {"text": [choices], "yes_no": bool, "number": bool}. A rule that is
    one simple comparison has no full trigger, so it is {} (its test decides the kind)."""
    if rule.get("test") != drivers.MATCHES_TRIGGER:
        return {}
    return trigger_language.how_fields_are_used(drivers.tree_of(rule["trigger"])).get(field, {})


def uses_across_rules(driver_rules, field):
    """How every driver's trigger uses one field, together: a field may be compared with a number in one trigger and
    with text in another. {"text": [choices, in order], "yes_no": bool, "number": bool}."""
    together = {"text": [], "yes_no": False, "number": False}
    for code in sorted(driver_rules):
        rule = driver_rules[code]
        if rule.get("test") == drivers.MATCHES_TRIGGER:
            uses = uses_of_field(rule, field)
        elif rule["field"] == field and rule["test"] not in (drivers.IS_YES, drivers.IS_NO):
            uses = {"number": True}
        else:
            uses = {}
        together["text"].extend(choice for choice in uses.get("text", []) if choice not in together["text"])
        together["yes_no"] = together["yes_no"] or bool(uses.get("yes_no"))
        together["number"] = together["number"] or bool(uses.get("number"))
    return together


def kind_of_question(rule, field, driver_rules=None):
    """(kind, choices) for the question that feeds `field` of a driver with this rule.
    A simple rule: yes or no for "is yes" / "is no", a number otherwise. A full trigger: text when a trigger compares
    the field with text (the texts are the choices), yes or no when it only compares with True or False, else a number.
    `driver_rules` (all of them) lets a text comparison in another driver's trigger count too."""
    uses = uses_across_rules(driver_rules, field) if driver_rules else uses_of_field(rule, field)
    if uses.get("text"):
        return TEXT, list(uses["text"])
    if rule["test"] == drivers.MATCHES_TRIGGER:
        if uses.get("yes_no") and not uses.get("number"):
            return YES_NO, []
        return NUMBER, []
    if rule["test"] in (drivers.IS_YES, drivers.IS_NO):
        return YES_NO, []
    return NUMBER, []


def build(driver_rules, risks):
    """Every question, in section order, then driver order.

    driver_rules  as files.driver_rules gives them: {"RD01": {"field": "RD01", "test": "is yes", ...}, ...}
    risks         as trust.config.risks() gives them

    Each question: {"field", "driver", "section", "text", "kind", "yes_means_field_is"}
    """
    found = []
    made_fields = set()
    for driver_code in sorted(driver_rules):
        rule = driver_rules[driver_code]
        for field in rule.get("questionnaire_fields") or []:
            if field in made_fields:
                continue                                  # two drivers read one field: it is asked once
            made_fields.add(field)
            kind, choices = kind_of_question(rule, field, driver_rules)
            if kind == YES_NO:
                yes_means_field_is = True if rule["test"] == drivers.MATCHES_TRIGGER else rule["test"] == drivers.IS_YES
            else:
                yes_means_field_is = None
            question = {
                "field": field,
                "driver": driver_code,
                "section": section_for_driver(driver_code, risks),
                "text": rule.get("rationale") or driver_code,
                "kind": kind,
                "yes_means_field_is": yes_means_field_is,
            }
            if kind == TEXT:
                question["choices"] = choices
                if uses_across_rules(driver_rules, field).get("number"):
                    question["accepts_number"] = True      # compared with numbers in one trigger and text in another
            found.append(question)
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
    longest = LONGEST_TEXT_ANSWER if question["kind"] == TEXT else LONGEST_ANSWER
    if len(text) > longest:
        raise ValueError(f"That answer is longer than {longest} characters.")
    if question["kind"] == YES_NO:
        yes_or_no = drivers.as_yes_no(text)
        if yes_or_no is None:
            raise ValueError("Answer yes or no.")
        return "yes" if yes_or_no else "no"
    if question["kind"] == TEXT:
        return clean_text_answer(question, text)
    number = drivers.as_number(text)
    if number is None:
        raise ValueError("Type a number. For a percent, type the % sign, for example 25%.")
    # A share is read as a part of one (0.25 = 25%). A plain number above one, like "25", was meant as a percent
    # but would be read as 25 whole shares, so it is refused rather than guessed.
    if is_share(question) and number > expressions.WHOLE_SHARE:
        raise ValueError(f"This answer is a share. Type it with the % sign, for example {text}%, or as a part of one, for example 0.25.")
    return text


def clean_text_answer(question, text):
    """A text answer is one of the question's choices (capitals and spaces don't matter), or Other, or a number when
    the field is also compared with numbers. A question with
    no choices takes any text."""
    choices = question.get("choices") or []
    if not choices:
        return text
    if question.get("accepts_number") and drivers.as_number(text) is not None:
        return text
    for choice in choices + [OTHER_ANSWER]:
        if trigger_language.plain_text(choice) == trigger_language.plain_text(text):
            return choice
    raise ValueError("Choose one of the answers shown.")


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
        if question["kind"] in (NUMBER, TEXT):
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

