"""The risk rating rules, checked with worked examples a person can follow by hand.

Every example uses the made-up risks and drivers in tools/test_risks (TEST data only, not real risks).
The long example at the end is one made-up group, "Payments Engineering", rated risk by risk.
"""
import pathlib

import pytest

from trust import config
from trust.risk import drivers, expressions, files, rating

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"


@pytest.fixture
def risks(monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    return config.risks()


@pytest.fixture
def rules():
    return files.driver_rules(TEST_RISKS)


@pytest.fixture
def settings():
    return rating.starting_settings()


# ----------------------------------------------------------------------------- is a driver on?

def test_a_yes_or_no_driver():
    rule = {"field": "RD01", "test": drivers.IS_YES, "value": None}
    assert drivers.driver_is_on(rule, {"RD01": True}) is True
    assert drivers.driver_is_on(rule, {"RD01": "No"}) is False
    assert drivers.driver_is_on(rule, {}) is None                      # not answered yet: can't be told


def test_a_driver_that_is_on_when_the_answer_is_no():
    """RD31: "Do automated tests run before a release?" The driver is on when the answer is No."""
    rule = {"field": "RD31", "test": drivers.IS_NO, "value": None}
    assert drivers.driver_is_on(rule, {"RD31": False}) is True
    assert drivers.driver_is_on(rule, {"RD31": True}) is False


def test_a_number_driver():
    """RD12 is on when the team supports 3 or more critical processes."""
    rule = {"field": "RD12", "test": drivers.AT_LEAST, "value": 3}
    assert drivers.driver_is_on(rule, {"RD12": 4}) is True
    assert drivers.driver_is_on(rule, {"RD12": 3}) is True
    assert drivers.driver_is_on(rule, {"RD12": 2}) is False


def test_a_driver_compared_with_the_prevailing_median():
    """RD22 is on when the group releases more than the middle group: 31 releases against a median of 24."""
    rule = {"field": "RD22", "test": drivers.ABOVE_PREVAILING, "value": None}
    assert drivers.driver_is_on(rule, {"RD22": 31}, {"RD22": 24}) is True
    assert drivers.driver_is_on(rule, {"RD22": 20}, {"RD22": 24}) is False
    assert drivers.driver_is_on(rule, {"RD22": 31}, {}) is None        # no median to compare with


def test_every_made_up_driver_trigger_can_be_read_and_written_back(rules):
    import yaml
    saved = yaml.safe_load((TEST_RISKS / files.DRIVERS_FILE).read_text(encoding="utf-8"))["risk_drivers"]
    assert len(rules) == len(saved) == 21
    for code, details in saved.items():
        # Written back and read again, the rule is the same (0.40 may come back written as 0.4).
        written_back = drivers.trigger_from_rule(rules[code])
        assert drivers.rule_from_trigger(written_back) == drivers.rule_from_trigger(details["trigger"]), code


def test_a_trigger_that_cannot_be_read_says_so():
    with pytest.raises(ValueError, match="Can't read this driver trigger"):
        drivers.rule_from_trigger("get(RD01) is 3")


def test_drivers_answered_from_data_have_no_questionnaire_field(rules):
    from_data = sorted(code for code, rule in rules.items() if files.answered_from_data(rule))
    assert from_data == ["RD22", "RD44", "RD63", "RD64"]


# ----------------------------------------------------------------------------- reading a risk's rule

def test_a_rule_asking_for_two_drivers():
    text = "RD02 in ad and RD54 in ad"
    assert expressions.text_is_met(text, {"RD02", "RD54"}, 2, 1.0) is True
    assert expressions.text_is_met(text, {"RD02"}, 1, 0.5) is False


def test_a_rule_asking_for_the_driver_count():
    assert expressions.text_is_met("dc >= 1", {"RD02"}, 1, 0.0) is True
    assert expressions.text_is_met("dc >= 1", set(), 0, 0.0) is False


def test_a_rule_asking_for_the_driver_share():
    """Two of three likelihood drivers on is 67%: above 60%, not above 80%."""
    assert expressions.text_is_met(">.60 and RD22 in ad", {"RD22"}, 2, 2 / 3) is True
    assert expressions.text_is_met(">.80 and RD22 in ad", {"RD22"}, 2, 2 / 3) is False


def test_and_is_worked_out_before_or():
    """A and B or C means (A and B) or C: with A off, the rule is still met through C."""
    text = ">.80 and RD01 in ad or RD16 in ad"
    assert expressions.text_is_met(text, {"RD16"}, 1, 0.0) is True


def test_brackets_group_a_choice():
    text = ">.60 and (RD01 in ad or RD03 in ad)"
    assert expressions.text_is_met(text, {"RD03"}, 2, 0.67) is True
    assert expressions.text_is_met(text, {"RD36"}, 2, 0.67) is False


def test_an_empty_rule_is_never_met():
    assert expressions.text_is_met(None, {"RD01"}, 1, 1.0) is False


def test_a_rule_with_a_typo_says_where():
    with pytest.raises(ValueError, match="Can't read this rule"):
        expressions.read_rule("RD02 in ad and RD54 is on")
    with pytest.raises(ValueError, match="bracket is not closed"):
        expressions.read_rule("(RD02 in ad and RD54 in ad")


def test_every_rule_in_the_made_up_risk_files_can_be_read(risks, rules):
    """The notes also list the two gaps known in the made-up files: rules naming a driver that is not in
    the risk's lists (RD50, RD02), and two drivers that are in no drivers file (RD16, RD39)."""
    notes = files.check_risks(risks, rules)
    assert not [n for n in notes if "Can't read" in n]
    assert any("RD16, which is not in the drivers file" in n for n in notes)
    assert any("air.cyber.01" in n and "RD50, which is not in the risk's driver lists" in n for n in notes)


# ----------------------------------------------------------------------------- rating one risk

def test_driver_share_is_drivers_on_out_of_likelihood_drivers(risks):
    """air.ops.01 has three likelihood drivers: RD40, RD41, RD14. Two on is 2 / 3."""
    assert rating.driver_share(risks["air.ops.01"], {"RD40", "RD41"}) == pytest.approx(2 / 3)
    assert rating.driver_share(risks["air.ops.01"], set()) == 0


def test_a_risk_with_no_driver_on_does_not_apply(risks, settings):
    assert rating.rate_risk(risks["air.ops.01"], {"RD01"}, settings) == {"applicable": False}


def test_medium_is_one_driver_of_three(risks, settings):
    """air.ops.02: one of its three likelihood drivers on is 33%, above the 30% setting, so Medium."""
    rated = rating.rate_risk(risks["air.ops.02"], {"RD12", "RD54"}, settings)
    assert rated["driver_share"] == pytest.approx(1 / 3)
    assert rated["likelihood"] == "MEDIUM"


def test_low_when_only_an_impact_driver_is_on(risks, settings):
    """air.ops.02 with only its impact driver on: no likelihood driver, share 0%, so Low."""
    rated = rating.rate_risk(risks["air.ops.02"], {"RD54"}, settings)
    assert rated["applicable"] is True
    assert rated["likelihood"] == "LOW"


def test_changing_the_medium_setting_changes_the_rating(risks, settings):
    stricter = dict(settings, medium_share_above=0.50)
    assert rating.rate_risk(risks["air.ops.02"], {"RD12", "RD54"}, stricter)["likelihood"] == "LOW"


def test_overall_impact_is_the_highest_of_the_three_kinds():
    by_kind = {"financial_impact": "HIGH", "client_impact": "CRITICAL", "regulatory_impact": "MEDIUM"}
    assert rating.overall_impact(by_kind) == "CRITICAL"


def test_elevated_needs_both_likelihood_and_impact(settings):
    assert rating.is_elevated("HIGH", "CRITICAL", settings) is True
    assert rating.is_elevated("MEDIUM", "CRITICAL", settings) is False
    assert rating.is_elevated("CRITICAL", "MEDIUM", settings) is False


# ----------------------------------------------------------------------------- better or worse

def rated(likelihood, impact):
    return {"applicable": True, "likelihood": likelihood, "impact": impact}


def test_trend_between_two_assessments():
    assert rating.trend(rated("HIGH", "HIGH"), rated("CRITICAL", "HIGH")) == "worse"
    assert rating.trend(rated("HIGH", "HIGH"), rated("MEDIUM", "HIGH")) == "better"
    assert rating.trend(rated("HIGH", "HIGH"), rated("CRITICAL", "MEDIUM")) == "mixed"
    assert rating.trend(rated("HIGH", "HIGH"), rated("HIGH", "HIGH")) == "no change"
    assert rating.trend(None, rated("HIGH", "HIGH")) is None           # a first assessment has no trend


# ----------------------------------------------------------------------------- one whole group

PAYMENTS_ANSWERS = {
    # Access                       # Data
    "RD01": True, "RD03": True,    "RD02": True, "RD70": True, "RD71": False, "RD72": True,
    "RD36": True,
    # Change                       # Resilience
    "RD23": False, "RD30": True,   "RD40": True, "RD41_days": 410,
    "RD31": True, "RD45": False,
    # Team and scope
    "RD12": 4, "RD14_pct": 0.25, "RD50": True, "RD54": True,
    # From data
    "RD22": 31, "RD44": 3, "RD63": 2.1, "RD64": 0,
}
PAYMENTS_PREVAILING = {"RD22": 24, "RD63": 3.0}


def test_one_group_from_answers_to_ratings(risks, rules, settings):
    sorted_drivers = drivers.drivers_for_group(rules, PAYMENTS_ANSWERS, PAYMENTS_PREVAILING)
    assert sorted_drivers["on"] == ["RD01", "RD02", "RD03", "RD12", "RD22", "RD30", "RD36",
                                    "RD40", "RD41", "RD44", "RD50", "RD54", "RD72"]
    assert sorted_drivers["not_known"] == []

    result = rating.rate_group(risks, sorted_drivers["on"], settings)
    summary = {risk_id: (r["likelihood"], r["impact"], r["elevated"]) for risk_id, r in result.items()}
    assert summary == {
        "air.cyber.01":  ("CRITICAL", "CRITICAL", True),     # 3 of 3 likelihood drivers on
        "air.cyber.02":  ("MEDIUM",   "HIGH",     False),    # 1 of 3
        "air.change.01": ("HIGH",     "CRITICAL", True),     # 2 of 3, and RD22 is on
        "air.change.02": ("MEDIUM",   "CRITICAL", False),    # 1 of 3
        "air.ops.01":    ("HIGH",     "CRITICAL", True),     # 2 of 3, and RD40 is on
        "air.ops.02":    ("MEDIUM",   "HIGH",     False),    # 1 of 3
        "air.data.01":   ("MEDIUM",   "CRITICAL", False),    # 1 of 3
        "air.data.02":   ("CRITICAL", "CRITICAL", True),     # 3 of 3
    }
    assert result["air.cyber.01"]["impact_by_kind"] == {
        "financial_impact": "HIGH", "client_impact": "CRITICAL", "regulatory_impact": "HIGH"}


# ----------------------------------------------------------------------------- answers and files that are off

def test_a_percent_answer_is_read_as_a_share():
    """RD14 is on above 40% of the team on legacy platforms. "25%" is 0.25, so the driver stays off."""
    rule = {"field": "RD14_pct", "test": drivers.MORE_THAN, "value": 0.40}
    assert drivers.driver_is_on(rule, {"RD14_pct": "25%"}) is False
    assert drivers.driver_is_on(rule, {"RD14_pct": "45%"}) is True
    assert drivers.driver_is_on(rule, {"RD14_pct": 0.45}) is True


def test_an_answer_that_is_not_a_number_is_not_known():
    rule = {"field": "RD12", "test": drivers.AT_LEAST, "value": 3}
    for answer in ("inf", "nan", "many", ""):
        assert drivers.driver_is_on(rule, {"RD12": answer}) is None, answer


def test_a_share_written_as_80_instead_of_point_80_is_refused():
    with pytest.raises(ValueError, match="written from 0 to 1"):
        expressions.read_rule(">80 and RD01 in ad")


def test_a_very_long_or_deeply_bracketed_rule_is_refused_plainly():
    with pytest.raises(ValueError):
        expressions.read_rule("(" * 400 + "RD01 in ad" + ")" * 400)
    with pytest.raises(ValueError, match="longer than"):
        expressions.read_rule("RD01 in ad and " * 100 + "RD02 in ad")
    with pytest.raises(ValueError):
        drivers.rule_from_trigger("get(RD12)>" + "0" * 5000 + "x")


def test_a_level_written_in_capitals_is_listed(risks, rules):
    risk = dict(risks["air.ops.02"], impact_scoring={"client_impact": {"CRITICAL": "RD54 in ad"}})
    notes = files.check_risks({"air.ops.02": risk}, rules)
    assert any("level 'CRITICAL' is not read" in n for n in notes)


def test_a_risk_can_apply_with_no_impact_rated(risks, settings):
    risk = dict(risks["air.ops.02"], impact_scoring={})
    result = rating.rate_risk(risk, {"RD12"}, settings)
    assert result["applicable"] is True and result["impact"] is None and result["elevated"] is False
    assert rating.trend(result, result) is None


def test_a_setting_that_cannot_be_used_stops_with_a_plain_message():
    with pytest.raises(ValueError, match="medium_share_above"):
        rating.check_settings({"medium_share_above": 30, "elevated_likelihood_at_least": "HIGH",
                               "elevated_impact_at_least": "HIGH"})
    with pytest.raises(ValueError, match="elevated_impact_at_least"):
        rating.check_settings({"medium_share_above": 0.3, "elevated_likelihood_at_least": "HIGH",
                               "elevated_impact_at_least": "Severe"})
