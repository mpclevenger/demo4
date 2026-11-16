"""The trigger language (owner, 16 Nov 2026): the small rule language in a driver's trigger.

Part 1 tests the reader and the evaluator on their own, with the owner's own examples.
Part 2 uploads a made-up drivers file that uses them, through the Risk site's upload (check, preview, load), and
checks that a team's answers turn the drivers on the way the triggers say.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust.risk import drivers, questions as question_list, site, trigger_language as language  # noqa: E402
from test_risk_seed import RISK_FILES, client, send, write  # noqa: E402,F401
from test_risk_site import GROUP, answer_all  # noqa: E402,F401


def is_on(trigger, answers=None, prevailing=None):
    """The trigger worked out for one team's answers (a dictionary of code to answer)."""
    tree = language.read_trigger(trigger)
    return language.evaluate(tree, (answers or {}).get, (prevailing or {}).get)


# ----------------------------------------------------------------------------- the owner's examples

def test_to_int_of_an_answer_compared_with_a_number():
    trigger = "to_int(get('RD65')) >= 1"
    assert is_on(trigger, {"RD65": "1"}) is True
    assert is_on(trigger, {"RD65": 4}) is True
    assert is_on(trigger, {"RD65": "0"}) is False
    assert is_on(trigger, {}) is False                                 # to_int of a missing answer is 0


def test_an_answer_above_the_prevailing_median():
    trigger = "get(RD22)>prevailing(RD22)"
    assert is_on(trigger, {"RD22": 31}, {"RD22": 24}) is True
    assert is_on(trigger, {"RD22": 20}, {"RD22": 24}) is False
    assert is_on(trigger, {"RD22": 31}) is False                       # no median: False, never an error


def test_text_answers_with_commas_are_compared_as_text():
    trigger = "(get(RD35)=='Broadly used, across teams')"
    assert is_on(trigger, {"RD35": "Broadly used, across teams"}) is True
    assert is_on(trigger, {"RD35": "  BROADLY USED, across Teams "}) is True      # capitals and end spaces don't matter
    assert is_on(trigger, {"RD35": "Used by one team"}) is False


def test_a_yes_or_no_compared_with_true():
    trigger = "(get('RD01') == True)"
    assert is_on(trigger, {"RD01": True}) is True
    assert is_on(trigger, {"RD01": False}) is False
    assert is_on(trigger, {"RD01": "yes"}) is True
    assert is_on(trigger, {}) is False


# ----------------------------------------------------------------------------- the pieces

@pytest.mark.parametrize("trigger, answers, expected", [
    ("!get(A)", {"A": False}, True),
    ("!get(A)", {"A": True}, False),
    ("not get(A)", {"A": False}, True),
    ("get(A) != 3", {"A": 4}, True),
    ("get(A) != 3", {"A": 3}, False),
    ("get(A) and get(B)", {"A": True, "B": True}, True),
    ("get(A) and get(B)", {"A": True, "B": False}, False),
    ("get(A) && get(B)", {"A": True, "B": True}, True),
    ("get(A) or get(B)", {"A": False, "B": True}, True),
    ("get(A) || get(B)", {"A": False, "B": False}, False),
    ("get(A) OR get(B)", {"A": False, "B": True}, True),
    ("get(A) or get(B) and get(C)", {"A": True, "B": False, "C": False}, True),       # and binds tighter than or
    ("(get(A) or get(B)) and get(C)", {"A": True, "B": False, "C": False}, False),
    ("not (get(A) or get(B))", {"A": False, "B": False}, True),
    ("!(get(A) > 2) && get(B) <= 5", {"A": 1, "B": 5}, True),
    ("to_float(get(A)) < 0.5", {"A": "0.25"}, True),
    ("get(A) == .5", {"A": "0.5"}, True),
    ("get(A) > -2", {"A": -1}, True),
    ("get(A) >= 1", {"A": "1,200"}, True),
    ("get(A) > 0.2", {"A": "25%"}, True),                                          # 25% is read as 0.25
    ("get(A) == None", {}, True),
    ("get(A) == FALSE", {"A": False}, True),
    ("get(A) == true", {"A": True}, True),
    ("to_int(to_float(get(A))) == 3", {"A": "3.9"}, True),                         # functions inside functions
])
def test_every_piece_of_the_language(trigger, answers, expected):
    assert is_on(trigger, answers) is expected


@pytest.mark.parametrize("trigger, answer, expected", [
    ("get(A) == 'it\\'s'", "it's", True),
    ('get(A) == "it\'s"', "it's", True),
    ("get(A) == 'say \"hi\", then go'", 'say "hi", then go', True),
    ('get(A) == "Used by teams, mostly"', "used by teams, mostly", True),
    ("get(A) != 'No'", "Yes, partly", True),
])
def test_text_with_quotes_of_both_kinds_and_commas(trigger, answer, expected):
    assert is_on(trigger, {"A": answer}) is expected


def test_two_bracketed_comparisons_joined_by_or_on_different_questions():
    trigger = "(get(RD45)>1) or (get(RD12)>1)"
    assert is_on(trigger, {"RD45": 2}) is True
    assert is_on(trigger, {"RD12": "5"}) is True
    assert is_on(trigger, {"RD45": 1, "RD12": 1}) is False
    assert language.fields_used(language.read_trigger(trigger)) == {"RD45", "RD12"}


def test_text_not_equal_and_a_number_compared_with_text_is_never_an_error():
    trigger = "(get(RD45) != 'No variation')"
    assert is_on(trigger, {"RD45": "Some variation"}) is True
    assert is_on(trigger, {"RD45": "no VARIATION"}) is False
    assert is_on(trigger, {"RD45": 3}) is True                         # a number is "not equal" to text
    assert is_on("get(RD45) == 'No variation'", {"RD45": 3}) is False
    assert is_on(trigger, {}) is False


def test_to_int_reads_missing_text_and_yes_the_same_way_every_time():
    assert language.to_int(None) == 0 and language.to_int("") == 0
    assert language.to_int("3") == 3 and language.to_int(True) == 1 and language.to_int(False) == 0
    assert language.to_int("lots") == 0


def test_comparing_a_missing_answer_with_a_number_is_false_not_an_error():
    for sign in ("==", "!=", ">", ">=", "<", "<="):
        assert is_on(f"get(A) {sign} 3", {}) is False


# ----------------------------------------------------------------------------- not known

def test_a_trigger_whose_answers_are_all_missing_is_not_known():
    tree = language.read_trigger("get(A) == True or get(B) == True")
    assert language.evaluate_or_unknown(tree, {}.get) is None
    assert language.evaluate_or_unknown(tree, {"B": True}.get) is True
    assert language.evaluate_or_unknown(tree, {"B": False}.get) is False


def test_a_trigger_needing_a_median_that_is_not_there_is_not_known():
    tree = language.read_trigger("get(A) > prevailing(A)")
    assert language.evaluate_or_unknown(tree, {"A": 5}.get, {}.get) is None
    assert language.evaluate_or_unknown(tree, {"A": 5}.get, {"A": 3}.get) is True


# ----------------------------------------------------------------------------- reading back and what it uses

def test_fields_used_are_the_codes_given_to_get():
    tree = language.read_trigger("get('RD01') == True and (to_int(get(RD65)) >= 1 or get(RD22) > prevailing(RD90))")
    assert language.fields_used(tree) == {"RD01", "RD65", "RD22"}


@pytest.mark.parametrize("written, tidy", [
    ("(get(RD35)=='Broadly used, across teams')", "(get('RD35') == 'Broadly used, across teams')"),
    ("get( 'RD01' )==true", "(get('RD01') == True)"),
    ("to_int(get('RD65')) >= 1", "(to_int(get('RD65')) >= 1)"),
    ("get(A)>1 && !get(B) || get(C)", "((get('A') > 1) and not get('B')) or get('C')"),
    ("get(A) == \"it's\"", "(get('A') == 'it\\'s')"),
    ("get(A) >= 0.50", "(get('A') >= 0.5)"),
])
def test_to_text_writes_one_tidy_form_that_reads_back_the_same(written, tidy):
    tree = language.read_trigger(written)
    assert language.to_text(tree) == tidy
    assert language.read_trigger(tidy) == tree


def test_how_fields_are_used_says_which_are_text_yes_no_or_number():
    tree = language.read_trigger("get(A) == 'One, two' or get(A) == 'Three' or get(B) == True or to_int(get(C)) >= 1 or get(D)")
    uses = language.how_fields_are_used(tree)
    assert uses["A"]["text"] == ["One, two", "Three"]
    assert uses["B"]["yes_no"] and uses["D"]["yes_no"]
    assert uses["C"]["number"]


# ----------------------------------------------------------------------------- a trigger that can't be read

@pytest.mark.parametrize("trigger, near, words", [
    ("get(RD01) = 3", "character 11", "=="),
    ("get(RD01) == ", "its end", "value was expected"),
    ("get(RD01 == 3", "character 10", "not closed"),
    ("(get(RD01) == 3", "its end", "closing bracket"),
    ("get(RD01) == 3)", "character 15", "does not fit"),
    ("get(RD01) > 1 > 2", "character 15", "one comparison at a time"),
    ("get(RD01) == Yes", "character 14", "quotes"),
    ("get(RD01) == 'open", "character 14", "quote is never closed"),
    ("shout(RD01)", "character 1 ", "not a function"),
    ("get(RD01) @ 3", "character 11", "not part of the trigger language"),
    ("get(RD01, RD02)", "character 15", "takes 1 value"),
    ("get(3)", "character 5", "needs a code"),
    ("True == True", "", "doesn't look at any answer"),
    ("", "", "empty"),
])
def test_a_trigger_that_cannot_be_read_says_where(trigger, near, words):
    with pytest.raises(language.TriggerProblem) as problem:
        language.read_trigger(trigger)
    assert near in str(problem.value) and words in str(problem.value)


def test_a_trigger_is_never_run_as_code():
    with pytest.raises(language.TriggerProblem):
        language.read_trigger("__import__('os').system('echo hi')")
    with pytest.raises(language.TriggerProblem):
        language.read_trigger("get('RD01') == 1; print(2)")


def test_a_very_long_or_deeply_bracketed_trigger_is_refused_plainly():
    with pytest.raises(language.TriggerProblem, match="longer than"):
        language.read_trigger("get(A) == 1 or " * 400 + "get(B) == 1")
    with pytest.raises((language.TriggerProblem, RecursionError)):
        language.read_trigger("(" * 900 + "get(A)" + ")" * 900)


# ----------------------------------------------------------------------------- the rule the Risk site keeps

def test_one_simple_comparison_keeps_the_simple_rule_shape():
    assert drivers.rule_from_trigger("(get('RD01') == True)") == {"field": "RD01", "test": drivers.IS_YES, "value": None}
    assert drivers.rule_from_trigger("(get(RD12)>=3)") == {"field": "RD12", "test": drivers.AT_LEAST, "value": 3.0}
    assert drivers.rule_from_trigger("get(RD22)>prevailing(RD22)")["test"] == drivers.ABOVE_PREVAILING


def test_anything_more_is_kept_as_its_tidy_trigger():
    rule = drivers.rule_from_trigger("to_int(get('RD65')) >= 1")
    assert rule == {"field": "RD65", "test": drivers.MATCHES_TRIGGER, "value": None,
                    "trigger": "(to_int(get('RD65')) >= 1)", "fields": ["RD65"]}
    assert drivers.trigger_from_rule(rule) == "(to_int(get('RD65')) >= 1)"
    assert drivers.rule_from_trigger(drivers.trigger_from_rule(rule)) == rule


def test_driver_is_on_reads_a_full_trigger_and_says_not_known_with_no_answers():
    rule = drivers.rule_from_trigger("(get(RD35)=='Broadly used, across teams') or get(RD01) == True")
    assert drivers.driver_is_on(rule, {"RD35": "Broadly used, across teams"}) is True
    assert drivers.driver_is_on(rule, {"RD35": "Other", "RD01": False}) is False
    assert drivers.driver_is_on(rule, {}) is None
    sorted_out = drivers.drivers_for_group({"RD35": rule}, {"RD01": True})
    assert sorted_out == {"on": ["RD35"], "off": [], "not_known": []}


def test_the_unreadable_trigger_error_still_names_the_trigger_and_the_place():
    with pytest.raises(ValueError, match="Can't read this driver trigger") as problem:
        drivers.rule_from_trigger("get(RD01) is TRUE")
    assert "near character" in str(problem.value)


# ----------------------------------------------------------------------------- end to end: upload, then answers

OWNER_DRIVERS = """\
risk_drivers:
  RD01:
    trigger: "(get('RD01') == True)"
    questionnaire_fields: [RD01]
    rationale: "The application keeps its own user accounts."
  RD65:
    trigger: "to_int(get('RD65')) >= 1"
    questionnaire_fields: [RD65]
    rationale: "The team has at least one unsupported component."
  RD22:
    trigger: "get(RD22)>prevailing(RD22)"
    questionnaire_fields: []
    rationale: "The team releases more often than the prevailing average."
  RD35:
    trigger: "(get(RD35)=='Broadly used, across teams')"
    questionnaire_fields: [RD35]
    rationale: "The shared platform is broadly used, across teams."
  RD36:
    trigger: "!get(RD02) && (get(RD03) != True || get(RD12) >= 3)"
    questionnaire_fields: [RD02, RD03, RD12]
    rationale: "Access is not reviewed and the estate is large."
  RD45:
    trigger: "(get(RD45)>1) or (get(RD12)>1)"
    questionnaire_fields: [RD45]
    rationale: "There are several unsupported libraries."
  RD46:
    trigger: "(get(RD45) != 'No variation')"
    questionnaire_fields: [RD45]
    rationale: "Release practice varies."
"""


@pytest.fixture
def owner_site(client, tmp_path):
    send(client, "risks", "load", RISK_FILES)
    path = write(tmp_path, "driver_mapping.yaml", OWNER_DRIVERS)
    checked = send(client, "drivers", "check", [path]).json
    assert checked["problems"] == [] and checked["items_total"] == 7 and checked["can_load"]
    moves = send(client, "drivers", "preview", [path]).json
    assert moves["ok"]
    assert send(client, "drivers", "load", [path]).json["ok"]
    return client


def test_the_owners_triggers_upload_with_no_problems_and_read_back(owner_site):
    rules = site.load_registers()["driver_rules"]
    assert rules["RD01"]["test"] == drivers.IS_YES
    assert rules["RD35"]["test"] == drivers.MATCHES_TRIGGER
    assert rules["RD36"]["fields"] == ["RD02", "RD03", "RD12"]
    assert rules["RD36"]["trigger"] == "not get('RD02') and ((get('RD03') != True) or (get('RD12') >= 3))"


def test_the_form_asks_a_choice_question_for_a_field_compared_with_text(owner_site):
    questions = {question["field"]: question for question in site.load_registers()["questions"]}
    assert questions["RD35"]["kind"] == question_list.TEXT
    assert questions["RD35"]["choices"] == ["Broadly used, across teams"]
    assert questions["RD65"]["kind"] == question_list.NUMBER
    assert questions["RD01"]["kind"] == question_list.YES_NO
    assert questions["RD03"]["kind"] == question_list.YES_NO and questions["RD12"]["kind"] == question_list.NUMBER


def test_a_text_answer_must_be_one_of_the_choices_or_other(owner_site):
    path = f"/api/risk/groups/{GROUP}/answers"
    from test_risk_site import post
    assert post(owner_site, path, {"question": "RD35", "answer": "broadly used, across teams"}).json["saved"]["answer"] == "Broadly used, across teams"
    assert post(owner_site, path, {"question": "RD35", "answer": "Other"}).json["saved"]["answer"] == "Other"
    assert "Choose one of the answers" in post(owner_site, path, {"question": "RD35", "answer": "something made up"}).json["error"]


def drivers_for_the_team(answers):
    answer_all_text = {field: value for field, value in answers.items()}
    loaded = site.load_registers()
    by_field = question_list.answers_by_field(loaded["questions"], answer_all_text)
    return drivers.drivers_for_group(loaded["driver_rules"], by_field)


def test_a_teams_answers_turn_the_uploaded_drivers_on_the_way_the_triggers_say(owner_site):
    answers = {"RD01": "yes", "RD65": "2", "RD35": "Broadly used, across teams", "RD02": "no", "RD03": "yes", "RD12": "4"}
    state = drivers_for_the_team(answers)
    assert state["on"] == ["RD01", "RD35", "RD36", "RD45", "RD65"]     # RD45: RD12 is 4, which is more than 1
    assert state["not_known"] == ["RD22", "RD46"]                              # a data driver: no median, so not known

    answers = {"RD01": "no", "RD65": "0", "RD35": "Other", "RD02": "yes", "RD03": "no", "RD12": "1"}
    state = drivers_for_the_team(answers)
    assert state["on"] == [] and "RD01" in state["off"] and "RD36" in state["off"]

    state = drivers_for_the_team({})
    assert state["on"] == [] and state["off"] == []                    # nothing answered: nobody is guessed on


def test_answering_through_the_site_gives_the_same_drivers(owner_site):
    answer_all(owner_site, {"RD01": "yes", "RD65": "2", "RD35": "Broadly used, across teams"})
    from trust import storage
    from trust.risk import assess
    saved = assess.answer_text(assess.latest_answers(storage.risk_answers(GROUP)))
    loaded = site.load_registers()
    result = assess.assess_group(loaded["risks"], loaded["driver_rules"], loaded["questions"], saved, loaded["settings"], loaded["placements"])
    on = [item["code"] for item in result["drivers"]["on"]]
    assert on == ["RD01", "RD35", "RD65"]


def test_a_trigger_that_cannot_be_read_is_one_problem_with_its_place_and_the_rest_load(client, tmp_path):
    text = OWNER_DRIVERS.replace("to_int(get('RD65')) >= 1", "to_int(get('RD65')) >=")
    path = write(tmp_path, "driver_mapping.yaml", text)
    checked = send(client, "drivers", "check", [path]).json
    assert checked["items_total"] == 6
    assert len(checked["problems"]) == 1
    assert checked["problems"][0].startswith("RD65: the trigger") and "its end" in checked["problems"][0]


def test_the_download_writes_a_full_trigger_back_and_it_reads_again(owner_site):
    from trust.risk import download
    text = download.drivers_file_text(site.load_registers()["driver_rules"])
    assert "to_int(get('RD65')) >= 1" in text
    import yaml
    again = {code: drivers.rule_from_trigger(entry["trigger"]) for code, entry in yaml.safe_load(text.split("\n", 1)[1])["risk_drivers"].items()}
    assert again["RD35"]["trigger"] == site.load_registers()["driver_rules"]["RD35"]["trigger"]


# ----------------------------------------------------------------------------- the Edit page

def test_a_full_trigger_is_edited_as_text_and_checked_before_it_is_saved(owner_site):
    from trust import editable
    listed = editable.entries_now("driver-triggers", editable._raw())
    assert sorted(entry["key"] for entry in listed) == ["RD35", "RD36", "RD45", "RD46", "RD65"]

    refused = owner_site.post("/api/edit/driver-triggers/preview", headers={"X-TRUST": "1"},
                              json={"by": "Rita Tester", "action": "edit", "key": "RD65",
                                    "values": {"trigger": "to_int(get('RD65')) >="}})
    assert refused.status_code == 400 and "its end" in refused.json["error"]

    saved = owner_site.post("/api/edit/driver-triggers/save", headers={"X-TRUST": "1"},
                            json={"by": "Rita Tester", "reason": "Two or more now.", "action": "edit", "key": "RD65",
                                  "values": {"trigger": "to_int(get('RD65')) >= 2"}})
    assert saved.status_code == 200, saved.json
    rule = site.load_registers()["driver_rules"]["RD65"]
    assert rule["trigger"] == "(to_int(get('RD65')) >= 2)"
    assert drivers.driver_is_on(rule, {"RD65": "1"}) is False and drivers.driver_is_on(rule, {"RD65": "2"}) is True


def test_a_field_compared_with_numbers_and_with_text_is_a_choice_question_that_also_takes_a_number(owner_site):
    questions = {question["field"]: question for question in site.load_registers()["questions"]}
    assert questions["RD45"]["kind"] == question_list.TEXT
    assert questions["RD45"]["choices"] == ["No variation"] and questions["RD45"]["accepts_number"] is True
    path = f"/api/risk/groups/{GROUP}/answers"
    from test_risk_site import post
    assert post(owner_site, path, {"question": "RD45", "answer": "3"}).json["saved"]["answer"] == "3"
    assert post(owner_site, path, {"question": "RD45", "answer": "no variation"}).json["saved"]["answer"] == "No variation"
    assert "Choose one" in post(owner_site, path, {"question": "RD45", "answer": "lots"}).json["error"]
    state = drivers_for_the_team({"RD45": "3"})
    assert "RD45" in state["on"] and "RD46" in state["on"]
    state = drivers_for_the_team({"RD45": "No variation"})
    assert "RD45" not in state["on"] and "RD46" in state["off"]
