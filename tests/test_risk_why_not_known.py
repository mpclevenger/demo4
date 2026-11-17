"""Why a driver is "not known" (owner, 17 Nov 2026): plain reasons for Tech Risk, read only."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust.risk import drivers, questions, why_not_known  # noqa: E402
from test_risk_site import client, test_files  # noqa: E402,F401  (the Risk site with made-up files)

YES = {"field": "RD01", "test": drivers.IS_YES, "value": None, "questionnaire_fields": ["RD01"]}
FORM = [{"field": "RD01", "driver": "RD01", "kind": questions.YES_NO, "yes_means_field_is": True, "text": "x"}]


def test_a_driver_with_no_questionnaire_field_is_answered_from_data_and_says_so():
    rule = {"field": "RD09", "test": drivers.IS_YES, "value": None}
    assert "no questionnaire field" in why_not_known.reason("RD09", rule, FORM, {}, {})
    said = {"RD09": {"sentence": "Not known: HR isn't loaded."}}
    assert "HR isn't loaded" in why_not_known.reason("RD09", rule, FORM, {}, said)


def test_a_question_missing_from_the_form_or_unanswered_is_named():
    assert "No question on the form asks for RD01" in why_not_known.reason("RD01", YES, [], {}, {})
    assert "wasn't answered" in why_not_known.reason("RD01", YES, FORM, {}, {})
    assert "isn't read as a yes or a no" in why_not_known.reason("RD01", YES, FORM, {"RD01": "maybe"}, {})


def test_only_not_known_drivers_get_a_reason():
    assert why_not_known.reasons(["RD01"], {"RD01": YES}, FORM, {}, {}) == {"RD01": why_not_known.reason("RD01", YES, FORM, {}, {})}


def test_the_command_lists_each_teams_not_known_drivers_with_a_reason(client):
    from test_risk_site import GROUP, post
    from trust import __main__ as cli
    post(client, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True})     # nothing answered
    lines = cli.risk_unknown_report()
    assert lines[0].endswith("questions on the form.") and any(line.startswith(f"{GROUP}:") for line in lines)
    assert any("wasn't answered" in line for line in lines)


def test_the_risk_site_uses_the_month_set_in_trust_data_month(monkeypatch):
    """Owner, 17 Nov 2026: "I need it to use October since that's what I have populated"."""
    from trust import storage
    from trust.risk import groups
    with_people = {"2026-09", "2026-10", "2026-11"}
    monkeypatch.setattr(storage, "months", lambda kind: ["2026-09", "2026-10", "2026-11", "2026-12"])
    monkeypatch.setattr(storage, "run_info", lambda kind, month: {"at": "x"})
    monkeypatch.setattr(storage, "load_month", lambda kind, month: {"feeds": {"hr": {"people": [1] if month in with_people else []}}})
    for chosen, used in (("", "2026-11"), ("2026-10", "2026-10"), ("2026-12", "2026-11"), ("2027-01", "2026-11")):
        monkeypatch.setattr(groups, "chosen_month", lambda chosen=chosen: chosen)
        assert groups.hr_month() == used, chosen


def test_trust_data_month_must_be_empty_or_a_month():
    from trust.risk import rating
    settings = rating.starting_settings()
    assert settings["trust_data_month"] == ""
    import pytest
    with pytest.raises(ValueError):
        rating.check_settings({**settings, "trust_data_month": "October"})
    rating.check_settings({**settings, "trust_data_month": "2026-10"})


def test_a_drivers_words_say_its_code_once_and_leave_out_a_copied_trigger():
    """Owner, 17 Nov 2026: the detailed view's "Likelihood drivers on" had too much text; "RD01" once."""
    from trust.risk.team_results import driver_label
    assert driver_label("RD01", "RD01: The app keeps its own accounts.") == "The app keeps its own accounts."
    assert driver_label("RD01", "RD01 - RD01 The app keeps its own accounts") == "The app keeps its own accounts"
    assert driver_label("RD01", "(get('RD01') == True) The app") == "The app"
    assert driver_label("RD65", "to_int(get('RD65')) >= 1: more than one site") == "more than one site"
    assert driver_label("RD35", "(get(RD35)=='Broadly, mostly') The team") == "The team"
    assert driver_label("RD01", "Unlike RD02 teams, the app keeps its own accounts.") == "Unlike RD02 teams, the app keeps its own accounts."
    assert driver_label("RD01", "") == "RD01"
