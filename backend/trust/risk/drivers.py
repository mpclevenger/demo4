"""Is a risk driver on or off for a group?

A driver (RD01, RD02, ...) is one fact about a group that raises a risk. Each driver has one rule:

    field   which answer to look at        "RD12"
    test    how to compare it              "at least"
    value   what to compare it with        3

So RD12 is on when the group's answer to RD12 is at least 3.

An answer comes from a question on the form or from data the site holds. Both arrive here the same way:
a dictionary of field name to answer, for example {"RD01": True, "RD12": 4, "RD22": 31}.
"""
import math
import re

# The tests a rule can use. The wording is what the Rating settings page shows.
IS_YES = "is yes"
IS_NO = "is no"
AT_LEAST = "at least"
MORE_THAN = "more than"
AT_MOST = "at most"
LESS_THAN = "less than"
ABOVE_PREVAILING = "above the prevailing median"
BELOW_PREVAILING = "below the prevailing median"

YES_WORDS = {"true", "yes", "y", "1"}
NO_WORDS = {"false", "no", "n", "0"}


def as_yes_no(answer):
    """True for yes, False for no, None when the answer is neither (or missing)."""
    if isinstance(answer, bool):
        return answer
    word = str(answer).strip().lower() if answer is not None else ""
    if word in YES_WORDS:
        return True
    if word in NO_WORDS:
        return False
    return None


def as_number(answer):
    """The answer as a number, or None when it isn't one (or is missing)."""
    if answer is None or isinstance(answer, bool):
        return None
    text = str(answer).strip()
    text = text.replace(",", "")                         # 1,200 -> 1200
    is_percent = text.endswith("%")                      # "25%" is read as 0.25
    text = text.rstrip("%").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):                        # "inf" and "nan" are not answers
        return None
    return number / 100 if is_percent else number


def driver_is_on(rule, answers, prevailing=None):
    """True when the driver is on, False when it is off, None when it can't be told (no answer yet, or no
    prevailing median to compare with). A driver that can't be told is never counted as on.

    rule        {"field": "RD12", "test": "at least", "value": 3}
    answers     {"RD12": 4, ...}                the group's answers, by field
    prevailing  {"RD22": 24, ...}               the prevailing median for each data field
    """
    answer = answers.get(rule["field"])
    test = rule["test"]

    if test in (IS_YES, IS_NO):
        yes = as_yes_no(answer)
        if yes is None:
            return None
        return yes if test == IS_YES else not yes

    number = as_number(answer)
    if number is None:
        return None

    if test in (ABOVE_PREVAILING, BELOW_PREVAILING):
        median = as_number((prevailing or {}).get(rule["field"]))
        if median is None:
            return None
        return number > median if test == ABOVE_PREVAILING else number < median

    limit = as_number(rule["value"])
    if limit is None:
        return None
    if test == AT_LEAST:
        return number >= limit
    if test == MORE_THAN:
        return number > limit
    if test == AT_MOST:
        return number <= limit
    if test == LESS_THAN:
        return number < limit
    raise ValueError(f"Unknown test in a driver rule: {test!r}")


def drivers_for_group(driver_rules, answers, prevailing=None):
    """Sort every driver into on, off, or not known yet, for one group.

    driver_rules  {"RD01": {"field": ..., "test": ..., "value": ...}, ...}
    Returns       {"on": [...], "off": [...], "not_known": [...]}, each a sorted list of driver codes.
    """
    result = {"on": [], "off": [], "not_known": []}
    for code in sorted(driver_rules):
        state = driver_is_on(driver_rules[code], answers, prevailing)
        if state is True:
            result["on"].append(code)
        elif state is False:
            result["off"].append(code)
        else:
            result["not_known"].append(code)
    return result


# ---------------------------------------------------------------------------------------------------
# The engine's own way of writing a rule, used for the first load from driver_mapping.yaml and for the
# download in the engine's shape:   (get(RD12)>=3)   (get(RD01)==TRUE)   (get(RD22)>prevailing(RD22))
# ---------------------------------------------------------------------------------------------------

TRIGGER = re.compile(r"""^\(?\s*get\(\s*(?P<field>\w+)\s*\)\s*
                         (?P<sign>==|>=|<=|>|<)\s*
                         (?P<value>TRUE|FALSE|prevailing\(\s*\w+\s*\)|-?(?:\d+(?:\.\d+)?|\.\d+))\s*\)?$""", re.X | re.I)
LONGEST_TRIGGER = 200                                    # characters; a real trigger is about 20

TEST_FOR_SIGN = {">=": AT_LEAST, ">": MORE_THAN, "<=": AT_MOST, "<": LESS_THAN}
SIGN_FOR_TEST = {test: sign for sign, test in TEST_FOR_SIGN.items()}


def rule_from_trigger(trigger):
    """Turn the engine's trigger text into a rule. "(get(RD12)>=3)" -> RD12, at least, 3."""
    text = str(trigger).strip()
    found = TRIGGER.match(text) if len(text) <= LONGEST_TRIGGER else None
    if not found:
        raise ValueError(f"Can't read this driver trigger: {trigger!r}")
    field, sign, value = found["field"], found["sign"], found["value"]
    word = value.upper()

    if word in ("TRUE", "FALSE"):
        if sign != "==":
            raise ValueError(f"A yes/no trigger must use ==: {trigger!r}")
        return {"field": field, "test": IS_YES if word == "TRUE" else IS_NO, "value": None}

    if word.startswith("PREVAILING"):
        if sign not in (">", "<"):
            raise ValueError(f"A prevailing-median trigger must use > or <: {trigger!r}")
        return {"field": field, "test": ABOVE_PREVAILING if sign == ">" else BELOW_PREVAILING, "value": None}

    if sign == "==":
        raise ValueError(f"A number trigger can't use ==: {trigger!r}")
    return {"field": field, "test": TEST_FOR_SIGN[sign], "value": float(value)}


def trigger_from_rule(rule):
    """Turn a rule back into the engine's trigger text (the opposite of rule_from_trigger)."""
    field, test = rule["field"], rule["test"]
    if test == IS_YES:
        return f"(get({field})==TRUE)"
    if test == IS_NO:
        return f"(get({field})==FALSE)"
    if test == ABOVE_PREVAILING:
        return f"(get({field})>prevailing({field}))"
    if test == BELOW_PREVAILING:
        return f"(get({field})<prevailing({field}))"
    value = float(rule["value"])
    is_whole_number = value == int(value)
    shown = str(int(value)) if is_whole_number else str(value)      # 3.0 is written as 3
    return f"(get({field}){SIGN_FOR_TEST[test]}{shown})"
