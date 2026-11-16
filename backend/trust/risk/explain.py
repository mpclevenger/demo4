"""Writes out, in plain words, how one risk was rated for one group: "How this was rated" on the results page.

The calculations are not done here. rating.py works out each rating. This file only reads the same numbers back
(through rating.driver_count, rating.driver_share and rating.impact_of_one_kind) and says them in sentences, so
a person can check each step by hand.

Each step is {"title": "Likelihood", "lines": ["..."], "result": "High"}.
"""
from trust.risk import expressions, rating
from trust.words import count_of

PERCENT = 100
SIGN_WORDS = {">=": "at least", ">": "more than", "<=": "at most", "<": "fewer than", "==": "exactly"}


def word(level):
    """'HIGH' -> 'High'. A missing level reads 'not rated'."""
    return level.title() if level else "not rated"


def percent(share):
    """0.75 -> '75%'."""
    return f"{round(share * PERCENT)}%"


def rule_in_words(tree, inside_and=False):
    """A rule from a risk file, read back in words: 'RD01 is on or the driver share is more than 80%'."""
    step = tree[0]
    if step in ("and", "or"):
        left, right = rule_in_words(tree[1], step == "and"), rule_in_words(tree[2], step == "and")
        joined = f"{left} {step} {right}"
        return f"({joined})" if step == "or" and inside_and else joined
    if step == "driver_on":
        return f"{tree[1]} is on"
    if step == "driver_off":
        return f"{tree[1]} is off"
    if step == "driver_count":
        return f"{SIGN_WORDS[tree[1]]} {count_of(tree[2], 'driver')} of the risk's own drivers on"
    if step == "driver_share":
        return f"the driver share is {SIGN_WORDS[tree[1]]} {percent(tree[2])}"
    raise ValueError(f"Unknown step in a rule: {step!r}")


def rule_check(rule_text, active_drivers, count, share, level_name):
    """One line: what the rule needs, and whether this team meets it."""
    if rule_text is None or str(rule_text).strip() == "":
        return f"{level_name} has no rule in the risk's file."
    needs = rule_in_words(expressions.read_rule(rule_text))
    is_met = expressions.text_is_met(rule_text, active_drivers, count, share)
    return f"{level_name} needs: {needs}. {'Met.' if is_met else 'Not met.'}"


def step_applies(risk, active_drivers):
    """The step "Does it apply?": how many of the risk's own drivers are on."""
    own_drivers_on = sorted(rating.own_drivers(risk) & set(active_drivers))
    own_drivers = rating.own_drivers(risk)
    lines = [f"{count_of(len(own_drivers_on), 'driver')} of this risk's {len(own_drivers)} drivers "
             f"{'is' if len(own_drivers_on) == 1 else 'are'} on" + (f" ({', '.join(own_drivers_on)})." if own_drivers_on else ".")]
    applies = rating.is_applicable(risk, active_drivers)            # the same call the rating uses
    lines.append("At least one is on, so the risk applies." if applies else "None is on, so the risk does not apply to this team.")
    return {"title": "Does it apply?", "lines": lines, "result": "Applies" if applies else "Does not apply"}


def step_likelihood(risk, active_drivers, rated, settings):
    """The step "Likelihood": the driver share, then each rule in the order the rating tests them."""
    count = rating.driver_count(risk, active_drivers)
    share = rating.driver_share(risk, active_drivers)
    listed = rating.likelihood_drivers(risk)
    drivers_on = len(listed & set(active_drivers))
    lines = [f"{drivers_on} of {len(listed)} likelihood drivers on = {percent(share)}."]
    own_rules = risk.get("likelihood_scoring") or {}
    for level in rating.LIKELIHOOD_LEVELS_IN_FILES:
        lines.append(rule_check(own_rules.get(level), active_drivers, count, share, word(level.upper())))
        if rated["likelihood"] == level.upper():
            break
    if rated["likelihood"] in (rating.MEDIUM, rating.LOW):
        medium_share = settings["medium_share_above"]
        verdict = "above" if share > medium_share else "not above"
        lines.append(f"Neither rule is met, so the share decides: {percent(share)} is {verdict} the Medium share "
                     f"of {percent(medium_share)}.")
    return {"title": "Likelihood", "lines": lines, "result": word(rated["likelihood"])}


def step_impact(risk, active_drivers, rated):
    """The step "Impact": the level of each kind of impact and the rule that gave it."""
    lines = []
    all_rules = risk.get("impact_scoring") or {}
    for kind in rating.IMPACT_KINDS:
        name = kind.replace("_", " ").capitalize()
        level = rated["impact_by_kind"][kind]
        if level is None:
            lines.append(f"{name}: not rated, none of its rules is met.")
            continue
        rule_text = (all_rules.get(kind) or {}).get(level.lower())
        needs = rule_in_words(expressions.read_rule(rule_text))
        lines.append(f"{name}: {word(level)}, because {needs}.")
    lines.append("The overall impact is the highest of the three.")
    return {"title": "Impact", "lines": lines, "result": word(rated["impact"])}


def step_elevated(rated, settings):
    """The step "Elevated?": likelihood and impact each against the Elevated level."""
    likelihood_floor = settings["elevated_likelihood_at_least"]
    impact_floor = settings["elevated_impact_at_least"]
    if not rated["impact"]:
        lines = ["The impact is not rated, so the risk cannot be Elevated."]
    else:
        likelihood_is_enough = rating.level_is_at_least(rated["likelihood"], likelihood_floor)
        impact_is_enough = rating.level_is_at_least(rated["impact"], impact_floor)
        lines = [f"Likelihood {word(rated['likelihood'])} is {'at least' if likelihood_is_enough else 'below'} {word(likelihood_floor)}.",
                 f"Impact {word(rated['impact'])} is {'at least' if impact_is_enough else 'below'} {word(impact_floor)}."]
    return {"title": "Elevated?", "lines": lines, "result": "Elevated" if rated.get("elevated") else "Not Elevated"}


def steps_for_risk(risk, active_drivers, rated, settings):
    """All the steps for one risk, in the order the rating follows them."""
    steps = [step_applies(risk, active_drivers)]
    if not rated["applicable"]:
        return steps
    steps.append(step_likelihood(risk, active_drivers, rated, settings))
    steps.append(step_impact(risk, active_drivers, rated))
    steps.append(step_elevated(rated, settings))
    return steps
