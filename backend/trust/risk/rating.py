"""How each risk is rated for one group, from the drivers that are on.

For one risk, in this order:

    1. Applicable?   Is at least one of the risk's own drivers on?
    2. Likelihood    Critical, High, Medium or Low
    3. Impact        rated three ways (financial, client, regulatory); the overall impact is the highest
    4. Elevated?     likelihood AND impact both at or above the Elevated level

The starting values are in config/risk_settings.json. What was picked and why:
docs/design/19_risk_rating.md.
"""
import json
import os
import pathlib

from trust.risk import expressions

# The four levels, lowest first, so a level's position in this list is its rank.
LOW, MEDIUM, HIGH, CRITICAL = "LOW", "MEDIUM", "HIGH", "CRITICAL"
LEVELS = [LOW, MEDIUM, HIGH, CRITICAL]
IMPACT_KINDS = ["financial_impact", "client_impact", "regulatory_impact"]
LIKELIHOOD_LEVELS_IN_FILES = ("critical", "high")        # a risk file gives a rule for these two; Medium and Low come from the share


def starting_settings():
    """The rating settings before anyone has changed them on the site (config/risk_settings.json).
    Keys starting with _ are notes for the reader and are left out."""
    path = pathlib.Path(os.environ.get("TRUST_RISK_SETTINGS")
                        or pathlib.Path(__file__).resolve().parents[3] / "config" / "risk_settings.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    settings = {name: value for name, value in saved.items() if not name.startswith("_")}
    check_settings(settings)
    return settings


def check_settings(settings):
    """Stop with a plain message when a rating setting is missing or can't be used."""
    share = settings.get("medium_share_above")
    if not isinstance(share, (int, float)) or isinstance(share, bool) or not 0 <= share <= 1:
        raise ValueError(f"medium_share_above must be a share from 0 to 1 (0.30 for 30%), not {share!r}.")
    switch = settings.get("rate_with_current_rules", True)
    if str(switch).strip().lower() not in ("true", "false", "yes", "no", "on", "off"):
        raise ValueError(f"rate_with_current_rules must be true or false (Yes or No), not {switch!r}.")
    pervasive = settings.get("pervasive_categories")
    if pervasive is not None and (isinstance(pervasive, bool) or not isinstance(pervasive, (int, float, str))
                                  or not str(pervasive).replace(".0", "").isdigit() or int(float(pervasive)) < 1):
        raise ValueError(f"pervasive_categories must be a whole number of 1 or more (3 means three categories), not {pervasive!r}.")
    for name in ("elevated_likelihood_at_least", "elevated_impact_at_least"):
        if settings.get(name) not in LEVELS:
            raise ValueError(f"{name} must be one of {', '.join(LEVELS)}, not {settings.get(name)!r}.")


def rank(level):
    """LOW is 0, MEDIUM 1, HIGH 2, CRITICAL 3."""
    return LEVELS.index(level)


def level_is_at_least(level, floor):
    """True when `level` is the same as `floor` or above it: HIGH is at least MEDIUM."""
    return rank(level) >= rank(floor)


def highest(levels):
    """The highest of some levels, or None when there are none."""
    levels = [level for level in levels if level]
    return max(levels, key=rank) if levels else None


# ---------------------------------------------------------------------------------------------------
# The three numbers every rule is worked out from
# ---------------------------------------------------------------------------------------------------

def likelihood_drivers(risk):
    """The drivers the risk lists for its likelihood."""
    return set(risk.get("likelihood_drivers") or [])


def own_drivers(risk):
    """Every driver listed on the risk, for likelihood or for impact."""
    return likelihood_drivers(risk) | set(risk.get("impact_drivers") or [])


def driver_count(risk, active_drivers):
    """How many of the risk's own drivers are on. Written "dc" in the risk files."""
    drivers_on = own_drivers(risk) & set(active_drivers)
    return len(drivers_on)


def driver_share(risk, active_drivers):
    """The share of the risk's likelihood drivers that are on, from 0 to 1.
    Two of three on is 2 / 3 = 0.67. A risk with no likelihood drivers has a share of 0."""
    listed = likelihood_drivers(risk)
    if not listed:
        return 0.0
    listed_and_on = listed & set(active_drivers)
    return len(listed_and_on) / len(listed)


# ---------------------------------------------------------------------------------------------------
# The four steps
# ---------------------------------------------------------------------------------------------------

def is_applicable(risk, active_drivers):
    """Step 1. A risk applies to a group when at least one of the risk's own drivers is on."""
    return driver_count(risk, active_drivers) > 0


def likelihood(risk, active_drivers, settings):
    """Step 2. Critical and High come from the risk's own rules, tested highest first. If neither is met,
    the risk is Medium when its driver share is above the Medium setting, and Low otherwise."""
    count = driver_count(risk, active_drivers)
    share = driver_share(risk, active_drivers)
    own_rules = risk.get("likelihood_scoring") or {}

    if expressions.text_is_met(own_rules.get("critical"), active_drivers, count, share):
        return CRITICAL
    if expressions.text_is_met(own_rules.get("high"), active_drivers, count, share):
        return HIGH
    if share > settings["medium_share_above"]:
        return MEDIUM
    return LOW


def impact_of_one_kind(rules_for_kind, active_drivers, count, share):
    """The highest level whose rule is met, for one kind of impact. None when no rule is met."""
    for level in reversed(LEVELS):                      # CRITICAL first, LOW last
        rule_text = (rules_for_kind or {}).get(level.lower())
        if expressions.text_is_met(rule_text, active_drivers, count, share):
            return level
    return None


def impact_by_kind(risk, active_drivers):
    """Step 3, first half. The impact rated three ways: {"financial_impact": "HIGH", ...}."""
    count = driver_count(risk, active_drivers)
    share = driver_share(risk, active_drivers)
    all_rules = risk.get("impact_scoring") or {}
    return {kind: impact_of_one_kind(all_rules.get(kind), active_drivers, count, share)
            for kind in IMPACT_KINDS}


def overall_impact(by_kind):
    """Step 3, second half. The overall impact is the highest of the three kinds.
    None when no impact rule is met for any kind: the risk applies but its impact is not rated, so it is
    never Elevated and has no trend."""
    return highest(by_kind.values())


def is_elevated(likelihood_level, impact_level, settings):
    """Step 4. Elevated when likelihood and impact are both at or above the Elevated level."""
    if not likelihood_level or not impact_level:
        return False
    likelihood_is_high_enough = level_is_at_least(likelihood_level, settings["elevated_likelihood_at_least"])
    impact_is_high_enough = level_is_at_least(impact_level, settings["elevated_impact_at_least"])
    return likelihood_is_high_enough and impact_is_high_enough


# ---------------------------------------------------------------------------------------------------
# One risk, then every risk, for one group
# ---------------------------------------------------------------------------------------------------

def rate_risk(risk, active_drivers, settings):
    """Everything the results page shows for one risk and one group."""
    active_drivers = set(active_drivers)
    if not is_applicable(risk, active_drivers):
        return {"applicable": False}

    likelihood_level = likelihood(risk, active_drivers, settings)
    by_kind = impact_by_kind(risk, active_drivers)
    impact_level = overall_impact(by_kind)
    return {
        "applicable": True,
        "likelihood": likelihood_level,
        "impact": impact_level,
        "impact_by_kind": by_kind,
        "elevated": is_elevated(likelihood_level, impact_level, settings),
        "driver_share": driver_share(risk, active_drivers),
        "likelihood_drivers_on": sorted(likelihood_drivers(risk) & active_drivers),
        "impact_drivers_on": sorted(set(risk.get("impact_drivers") or []) & active_drivers),
    }


def rate_group(risks, active_drivers, settings):
    """Rate every risk for one group. risks is {risk id: risk}, as trust.config.risks() gives them."""
    return {risk_id: rate_risk(risks[risk_id], active_drivers, settings) for risk_id in sorted(risks)}


# ---------------------------------------------------------------------------------------------------
# Better or worse since the last assessment
# ---------------------------------------------------------------------------------------------------

def trend(before, now):
    """How one risk moved between two assessments of the same group.

    "worse"      likelihood or impact went up and the other did not go down
    "better"     likelihood or impact went down and the other did not go up
    "mixed"      one went up and the other went down
    "no change"  both stayed where they were
    None         nothing to compare: no earlier rating, or the risk did not apply then or now
    """
    if not before or not now:
        return None                                      # a first assessment
    if not before.get("applicable") or not now.get("applicable"):
        return None                                      # the risk did not apply then, or does not now
    if not before.get("impact") or not now.get("impact"):
        return None                                      # the impact was not rated then, or is not now

    likelihood_move = rank(now["likelihood"]) - rank(before["likelihood"])
    impact_move = rank(now["impact"]) - rank(before["impact"])
    something_went_up = likelihood_move > 0 or impact_move > 0
    something_went_down = likelihood_move < 0 or impact_move < 0

    if something_went_up and something_went_down:
        return "mixed"
    if something_went_up:
        return "worse"
    if something_went_down:
        return "better"
    return "no change"
