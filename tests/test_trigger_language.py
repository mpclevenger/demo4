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
    ("get(RD01 == 3", "character 4", "not closed"),
    ("(get(RD01) == 3", "character 1 ", "closing bracket"),
    ("get(RD01) == 3)", "character 15", "no opening bracket"),
    ("get(RD01) > 1 >", "its end", "value was expected"),
    ("get(RD01) == Yes", "character 14", "quotes"),
    ("get(RD01) == 'open", "character 14", "quote is never closed"),
    ("shout(RD01)", "character 1 ", "not a function"),
    ("get(RD01) @ 3", "character 1 ", "only + - * / %"),
    ("get(RD01, RD02)", "character 11", "quotes"),
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
        drivers.rule_from_trigger("get(RD01) is 3")
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


# ----------------------------------------------------------------------------- every line the owner's engine writes (17 Nov 2026)
# Python-style triggers, read with Python's own reader (ast) and walked by us. Each line is read AND worked out on
# two or three sets of answers. None means "not known" (evaluate_or_unknown): never True, never a crash.

def known(trigger, answers=None, prevailing=None):
    tree = language.read_trigger(trigger)
    return language.evaluate_or_unknown(tree, (answers or {}).get, (prevailing or {}).get)


YES, NO = {"RD01": True}, {"RD01": False}

OWNER_LINES = [
    ("(get('RD01') == True)", YES, True), ("(get('RD01') == True)", NO, False), ("(get('RD01') == True)", {}, None),
    ("(get('RD01') == true)", YES, True), ("(get('RD01') == TRUE)", NO, False),
    ("(get('RD01') == 'True')", YES, True), ("(get('RD01') == 'True')", NO, False),
    ('(get(\'RD01\') == "Yes")', {"RD01": "yes"}, True), ('(get(\'RD01\') == "Yes")', NO, False),
    ("(get('RD01'))", YES, True), ("get('RD01')", NO, False), ("get('RD01')", {}, None),
    ("(get('RD01') is True)", YES, True), ("(get('RD01') is True)", NO, False),
    ("(get('RD01') is not None)", YES, True), ("(get('RD01') is not None)", NO, True), ("(get('RD01') is not None)", {}, None),
    ("(get('RD01') != None)", YES, True), ("(get('RD01') != None)", {}, None),
    ("(get('RD01') in ['A', 'B'])", {"RD01": "a"}, True), ("(get('RD01') in ['A', 'B'])", {"RD01": "C"}, False),
    ("(get('RD01') not in ['A', 'B'])", {"RD01": "C"}, True), ("(get('RD01') not in ['A', 'B'])", {"RD01": "B"}, False),
    ("(get('RD01') in ('A', 'B'))", {"RD01": "B"}, True), ("(get('RD01') in ('A', 'B'))", {}, None),
    ("(to_int(get('RD65')) >= 1)", {"RD65": "2"}, True), ("(to_int(get('RD65')) >= 1)", {"RD65": "0"}, False),
    ("(to_int(get('RD65')) >= 1)", {"RD65": "abc"}, False), ("(to_int(get('RD65')) >= 1)", {}, None),
    ("to_int(get('RD65')) >= 1", {"RD65": 3}, True),
    ("(to_int(get('RD65'))>=1)", {"RD65": "1"}, True),
    ("(int(get('RD65')) >= 1)", {"RD65": "5"}, True), ("(int(get('RD65')) >= 1)", {"RD65": "abc"}, False),
    ("(float(get('RD65')) > 0.5)", {"RD65": "0.6"}, True), ("(float(get('RD65')) > 0.5)", {"RD65": "0.5"}, False),
    ("(to_float(get('RD65')) > 0.5)", {"RD65": "0.7"}, True), ("(to_float(get('RD65')) > 0.5)", {"RD65": "x"}, False),
    ("(get('RD22') > prevailing('RD22'))", {"RD22": 15}, True), ("(get('RD22') > prevailing('RD22'))", {"RD22": 5}, False),
    ("(get('RD22') > prevailing_median('RD22'))", {"RD22": 15}, True),
    ("(get('RD22') > 1.5 * prevailing('RD22'))", {"RD22": 16}, True),
    ("(get('RD22') >= 0.7*prevailing('RD22'))", {"RD22": 7}, True), ("(get('RD22') >= 0.7*prevailing('RD22'))", {"RD22": 6}, False),
    ("(get('RD35') == 'Broadly, yes')", {"RD35": "broadly, yes"}, True), ("(get('RD35') == 'Broadly, yes')", {"RD35": "No"}, False),
    ("(get('RD45') > 1) or (get('RD12') > 1)", {"RD45": 0, "RD12": 2}, True), ("(get('RD45') > 1) or (get('RD12') > 1)", {"RD45": 0, "RD12": 0}, False),
    ("(get('RD45') > 1) or (get('RD12') > 1)", {}, None),
    ("(get('RD45') != 'No variation')", {"RD45": "Some"}, True), ("(get('RD45') != 'No variation')", {"RD45": "no variation"}, False),
    ("!(get('RD01') == True) and (get('RD02') == True)", {"RD01": False, "RD02": True}, True),
    ("!(get('RD01') == True) and (get('RD02') == True)", {"RD01": True, "RD02": True}, False),
    ("(not get('RD01'))", NO, True), ("(not get('RD01'))", YES, False),
    ("(get('RD01') == True) & (get('RD02') == True)", {"RD01": True, "RD02": True}, True),
    ("(get('RD01') == True) & (get('RD02') == True)", {"RD01": True, "RD02": False}, False),
    ("(get('RD01') == True) | (get('RD02') == True)", {"RD01": False, "RD02": True}, True),
    ("(get('RD01') == True) | (get('RD02') == True)", {"RD01": False, "RD02": False}, False),
    ("(get('RD01') == True) AND (get('RD02') == True)", {"RD01": True, "RD02": True}, True),
    ("(get('RD01') == True) OR (get('RD02') == True)", {"RD01": False, "RD02": True}, True),
    ("(len(get('RD70')) > 0)", {"RD70": "abc"}, True), ("(len(get('RD70')) > 0)", {}, None),
    ("(get('RD70').lower() == 'yes')", {"RD70": "YES"}, True), ("(get('RD70').lower() == 'yes')", {"RD70": "no"}, False),
    ("(get('RD70').lower() == 'yes')", {"RD70": 5}, False),
    ("(str(get('RD70')).lower() == 'yes')", {"RD70": "Yes"}, True), ("(str(get('RD70')).lower() == 'yes')", {"RD70": True}, False),
    ("(get('RD70') == '')", {"RD70": "x"}, False),
    ("(get('RD70') != '')", {"RD70": "x"}, True),
    ("(get('RD70', 0) > 3)", {"RD70": 5}, True), ("(get('RD70', 0) > 3)", {}, False), ("(get('RD70', 0) > 3)", {"RD70": 1}, False),
    ("(get('RD70') >= 3 and get('RD70') <= 10)", {"RD70": 5}, True), ("(get('RD70') >= 3 and get('RD70') <= 10)", {"RD70": 11}, False),
    ("(3 <= get('RD70') <= 10)", {"RD70": 3}, True), ("(3 <= get('RD70') <= 10)", {"RD70": 10}, True),
    ("(3 <= get('RD70') <= 10)", {"RD70": 11}, False), ("(3 <= get('RD70') <= 10)", {"RD70": "abc"}, False),
    ("(get('RD70') - get('RD71') > 2)", {"RD70": 9, "RD71": 6}, True), ("(get('RD70') - get('RD71') > 2)", {"RD70": 9, "RD71": 8}, False),
    ("(get('RD70') / get('RD71') > 0.5)", {"RD70": 3, "RD71": 4}, True), ("(get('RD70') / get('RD71') > 0.5)", {"RD70": 3, "RD71": 0}, False),
    ("(get('RD70') % 2 == 0)", {"RD70": 4}, True), ("(get('RD70') % 2 == 0)", {"RD70": 5}, False),
    ("(get('RD70') == -1)", {"RD70": -1}, True), ("(get('RD70') == -1)", {"RD70": 1}, False),
    ("(get('RD70') == 1e3)", {"RD70": 1000}, True), ("(get('RD70') == 1e3)", {"RD70": 10}, False),
    ("(get(“RD70”) == 1)", {"RD70": 1}, True),
    ("(get('RD70') == ‘Yes’)", {"RD70": "yes"}, True),
    ("(get('rd70') == 1)", {"RD70": 1}, True),
    ("(get('RD70')==1) # comment", {"RD70": 1}, True), ("(get('RD70')==1) # comment", {"RD70": 2}, False),
    ("get(RD70) == 1 && get(RD71) == 2 || get(RD72) == 3", {"RD70": 1, "RD71": 9, "RD72": 3}, True),
    ("abs(get('RD70')) == 2 and min(get('RD70'), 5) < 0 and max(1, get('RD70')) == 1 and round(get('RD70') * 1.5) == -3", {"RD70": -2}, True),
    ("get('RD70').strip().title() == 'Yes Please'", {"RD70": "  yes please "}, True),
    ("get('RD70').startswith('Yes') and not get('RD70').endswith('no')", {"RD70": "Yes sir"}, True),
    ("bool(get('RD70'))", {"RD70": "yes"}, True),
    ("get('RD70') / 0 > 1", {"RD70": 4}, False),
    ("-get('RD70') < 0", {"RD70": 4}, True),
]


@pytest.mark.parametrize("trigger, answers, expected", OWNER_LINES)
def test_every_line_the_owners_engine_writes_reads_and_works_out(trigger, answers, expected):
    prevailing = {"RD22": 10}
    assert known(trigger, answers, prevailing) is expected


def test_the_battery_of_owner_lines_all_read():
    lines = [trigger for trigger, _answers, _expected in OWNER_LINES]
    for line in lines:
        assert language.read_trigger(line)
    assert len(set(lines)) >= 49


@pytest.mark.parametrize("trigger", [
    "(get('RD01') == True)", "get(RD70) >= 3 and get(RD70) <= 10", "(3 <= get('RD70') <= 10)", "(get('RD70') in ['A', 'B'])",
    "('Option A' in get('RD40'))", "(get('RD70').lower() == 'yes')", "(get('RD70', 0) > 3)",
    "to_int(get('RD65')) >= 1 or -get('RD70') < 2 * prevailing('RD22')", "get('RD70') is not None",
])
def test_the_tidy_form_reads_back_the_same(trigger):
    tree = language.read_trigger(trigger)
    assert language.read_trigger(language.to_text(tree)) == tree


@pytest.mark.parametrize("trigger", [
    "__import__('os').system('echo hi')", "get('RD01').__class__", "open('x')", "(lambda: 1)()", "[x for x in get('RD01')]",
    "{x for x in get('RD01')}", "f'{get(1)}'", "get('RD01').__dict__", "get('RD01').format('x')", "get('RD01').lower.__self__",
    "get('RD01')[0]", "eval('1')", "exec('1')", "compile('1', 'a', 'eval')", "getattr(get('RD01'), 'x')",
    "get('RD01') ** 2 > 1", "get('RD01') // 2 > 1", "get('RD01') if 1 else 2", "(x := 3) > get('RD01')", "get('RD01') == {1: 2}",
    "get('RD01') in get('RD02') in x", "get('RD01') is 3", "get('RD01') is 'a'", "get('RD01', x=1)", "get(*['RD01'])",
    "get('RD01') == 1; print(2)", "import os", "get('RD01') == 1\nprint(2)", "get('RD01') == b'x'", "get('RD01') == 1j",
    "get('RD 01') == 1", "get(1) == 1", "get('RD01', get('RD02')) == 1", "round(1, 2, 3) == get('RD01')", "min(1) == get('RD01')",
    "get('RD01').lower(1) == 'a'", "True == True", "RD01 == 1", "get('RD01') == [1, 2]", "get('RD01') in [get('RD02')]",
    "get('RD01') == 1\x00", "a.b.c",
])
def test_nothing_unsafe_or_unknown_is_read_and_nothing_is_run(trigger):
    with pytest.raises(language.TriggerProblem):
        language.read_trigger(trigger)


def test_very_long_or_deeply_nested_input_is_refused_never_run():
    for text in ("get(A) == 1 or " * 400 + "get(B) == 1", "(" * 900 + "get(A)" + ")" * 900, "not " * 500 + "get(A)",
                 "get(A) == " + "-" * 900 + "1", "get(A)" + " + 1" * 500 + " > 1", "get(A) == 1" + " or get(A) == 1" * 120):
        with pytest.raises(language.TriggerProblem):
            language.read_trigger(text)


def test_a_trigger_with_a_quote_that_python_would_treat_as_code_is_only_text():
    tree = language.read_trigger("get('RD01') == \"__import__('os')\"")
    assert language.evaluate(tree, {"RD01": "__import__('os')"}.get) is True


def test_text_that_looks_like_a_keyword_is_left_alone():
    assert is_on("get(A) == 'TRUE AND false || null'", {"A": "true and false || null"}) is True


# ----------------------------------------------------------------------------- tick-any: 'Option A' in get('RD40')

TICK_LINES = [
    ("('Option A' in get('RD40'))", {"RD40": ["Option A", "Option B"]}, True),
    ("('Option A' in get('RD40'))", {"RD40": ["option a  "]}, True),                    # capitals and outer spaces don't matter
    ("('Option A' in get('RD40'))", {"RD40": ["Option B"]}, False),
    ("('Option A' in get('RD40'))", {"RD40": "Option A"}, True),                         # one text: equals the option
    ("('Option A' in get('RD40'))", {"RD40": "Option B; option a"}, True),              # items between semicolons
    ("('Option A' in get('RD40'))", {"RD40": "Option B, Option A"}, True),              # or commas
    ("('Option A' in get('RD40'))", {"RD40": "Option AB"}, False),                      # not a part-word match
    ("('Yes' in get('RD40'))", {"RD40": "Yes, partly"}, True),                          # "Yes" is one of its items
    ("('Yes' in get('RD40'))", {"RD40": "Mostly yes"}, False),
    ("('es' in get('RD40'))", {"RD40": "Yes, partly"}, False),
    ("('Option A' in get('RD40'))", {}, None),                                          # no answer: not known
    ("('Option A' in get('RD40'))", {"RD40": []}, None),                                # nothing ticked is no answer
    ("('Option A' not in get('RD40'))", {"RD40": ["Option B"]}, True),
    ("('Option A' not in get('RD40'))", {"RD40": ["Option A"]}, False),
    ("('Option A' not in get('RD40'))", {}, None),
    ("(get('RD40') == 'Option A')", {"RD40": ["Option A", "Option C"]}, True),          # a list answer equals an option it holds
    ("(get('RD40') == 'Option A')", {"RD40": ["Option C"]}, False),
    ("(get('RD40') == 'Option A')", {"RD40": "Option A"}, True),
    ("(get('RD40') != 'Option A')", {"RD40": ["Option C"]}, True),
    ("(get('RD40') in ['A', 'B'])", {"RD40": "B"}, True),                               # one of these
    ("(get('RD40') in ['A', 'B'])", {"RD40": ["C", "B"]}, True),
    ("(get('RD40') in ['A', 'B'])", {"RD40": ["C"]}, False),
    ("('A' in get('RD40')) and ('B' in get('RD40'))", {"RD40": ["A", "B"]}, True),
    ("('A' in get('RD40')) and ('B' in get('RD40'))", {"RD40": ["A"]}, False),
    ("('A' in get('RD40')) or get('RD01')", {"RD40": ["C"], "RD01": True}, True),
    ("get('RD40')", {"RD40": ["None of these"]}, False),
    ("get('RD40')", {"RD40": ["A"]}, True),
]


@pytest.mark.parametrize("trigger, answers, expected", TICK_LINES)
def test_a_tick_any_answer_says_whether_an_option_was_selected(trigger, answers, expected):
    assert known(trigger, answers) is expected


def test_how_a_field_is_used_when_options_are_looked_for_in_it():
    tree = language.read_trigger("('Option A' in get('RD40')) or ('Option B' in get('RD40')) or get('RD41') == 'One' or get('RD42') in ['X', 'Y']")
    uses = language.how_fields_are_used(tree)
    assert uses["RD40"]["tick_any"] == ["Option A", "Option B"] and uses["RD40"]["text"] == []
    assert uses["RD41"]["text"] == ["One"] and uses["RD41"]["tick_any"] == []
    assert uses["RD42"]["text"] == ["X", "Y"]


def test_how_fields_are_used_for_lists_numbers_and_yes_no():
    uses = language.how_fields_are_used(language.read_trigger(
        "(get('A') in ['x', 'y']) and (get('B') is True) and (3 <= get('C') <= 10) and (get('D') - get('E') > 2) and (get('F').lower() == 'yes')"))
    assert uses["A"]["text"] == ["x", "y"]
    assert uses["B"]["yes_no"] and not uses["B"]["number"]
    assert uses["C"]["number"] and uses["D"]["number"] and uses["E"]["number"]
    assert uses["F"]["text"] == ["yes"]


def test_a_question_that_looks_for_options_is_tick_any_with_none_of_these_last():
    from trust.risk import questions as question_list
    rules = {"RD40": drivers.rule_from_trigger("('Option A' in get('RD40')) or ('Option B' in get('RD40'))"),
             "RD41": drivers.rule_from_trigger("('Option C' in get('RD40')) and get('RD40') != 'Option A'")}
    kind, options = question_list.kind_of_question(rules["RD40"], "RD40", rules)
    assert kind == question_list.TICK_ANY
    assert options == ["Option A", "Option B", "Option C", "None of these"]
    single = {"RD50": drivers.rule_from_trigger("get('RD50') == 'One' or get('RD50') == 'Two'")}
    assert question_list.kind_of_question(single["RD50"], "RD50", single)[0] == question_list.TEXT


def test_tick_any_answers_are_cleaned_saved_as_a_list_and_none_of_these_clears_the_rest():
    from trust.risk import questions as question_list
    question = {"field": "RD40", "kind": "tick_any", "choices": ["Option A", "Option B", "None of these"]}
    assert question_list.clean_answer(question, ["option a ", "Option B"]) == ["Option A", "Option B"]
    assert question_list.clean_answer(question, "Option B; Option A") == ["Option B", "Option A"]
    assert question_list.clean_answer(question, ["Option A", "None of these"]) == ["None of these"]
    assert question_list.clean_answer(question, []) == ""
    with pytest.raises(ValueError, match="Choose from the answers shown"):
        question_list.clean_answer(question, ["Option Z"])
    assert question_list.answer_as_text(["Option A", "Option B"]) == "Option A; Option B"
    assert question_list.is_answered(["Option A"]) and not question_list.is_answered([])
    answers = question_list.answers_by_field([question], {"RD40": ["Option A"]})
    assert answers == {"RD40": ["Option A"]}


# ----------------------------------------------------------------------------- end to end: one driver for every owner line

def drivers_file_with_every_line():
    """A driver_mapping.yaml with one driver for each distinct line, and the fields each line reads as its questionnaire fields."""
    import json
    lines = []
    for trigger, _answers, _expected in OWNER_LINES + TICK_LINES:
        if trigger not in lines:
            lines.append(trigger)
    text = "risk_drivers:\n"
    for number, trigger in enumerate(lines, 1):
        fields = language.fields_in_order(language.read_trigger(trigger))
        text += (f"  RD{200 + number}:\n    trigger: {json.dumps(trigger, ensure_ascii=False)}\n"
                 f"    questionnaire_fields: {json.dumps(fields)}\n    rationale: \"Made-up driver {number}.\"\n")
    return text, lines


def test_a_drivers_file_with_every_owner_line_checks_with_no_problems_and_loads(client, tmp_path):
    text, lines = drivers_file_with_every_line()
    assert len(lines) >= 49
    send(client, "risks", "load", RISK_FILES)
    path = write(tmp_path, "driver_mapping.yaml", text)
    checked = send(client, "drivers", "check", [path]).json
    assert checked["problems"] == [] and checked["items_total"] == len(lines) and checked["can_load"]
    assert send(client, "drivers", "load", [path]).json["ok"]
    loaded = site.load_registers()
    by_field = {question["field"]: question for question in loaded["questions"]}
    assert by_field["RD40"]["kind"] == question_list.TICK_ANY
    assert "Option A" in by_field["RD40"]["choices"]
    assert by_field["RD40"]["choices"][-1] == "None of these"
    assert by_field["RD65"]["kind"] == question_list.NUMBER
    assert by_field["RD02"]["kind"] in (question_list.YES_NO, question_list.NUMBER)
    assert by_field["RD35"]["kind"] == question_list.TEXT and by_field["RD35"]["choices"] == ["Broadly, yes"]


def test_a_tick_any_question_is_ticked_saved_as_a_list_and_turns_its_driver_on(client, tmp_path):
    send(client, "risks", "load", RISK_FILES)
    drivers_text = ("risk_drivers:\n  RD40:\n    trigger: \"('Option A' in get('RD40')) and not ('Option B' in get('RD40'))\"\n"
                    "    questionnaire_fields: [RD40]\n    rationale: \"Option A is used, and not Option B.\"\n"
                    "  RD41:\n    trigger: \"('Option C' in get('RD40'))\"\n    questionnaire_fields: [RD40]\n    rationale: \"Option C is used.\"\n")
    assert send(client, "drivers", "load", [write(tmp_path, "driver_mapping.yaml", drivers_text)]).json["ok"]
    question = {item["field"]: item for item in site.load_registers()["questions"]}["RD40"]
    assert question["kind"] == question_list.TICK_ANY
    assert question["choices"] == ["Option A", "Option B", "Option C", "None of these"]
    from test_risk_site import post
    path = f"/api/risk/groups/{GROUP}/answers"
    saved = post(client, path, {"question": "RD40", "answer": ["option a", "Option C"]}).json
    assert saved["ok"] and saved["saved"]["answer"] == ["Option A", "Option C"]
    form = client.get(f"/api/risk/groups/{GROUP}").json
    shown = [q for section in form["sections"] for q in section["questions"] if q["field"] == "RD40"][0]
    assert shown["answer"] == ["Option A", "Option C"] and shown["kind"] == "tick_any"
    loaded = site.load_registers()
    by_field = question_list.answers_by_field(loaded["questions"], {"RD40": ["Option A", "Option C"]})
    state = drivers.drivers_for_group(loaded["driver_rules"], by_field)
    assert state["on"] == ["RD40", "RD41"]
    state = drivers.drivers_for_group(loaded["driver_rules"], question_list.answers_by_field(loaded["questions"], {"RD40": ["Option A", "Option B"]}))
    assert state["on"] == [] and state["off"] == ["RD40", "RD41"]
    assert post(client, path, {"question": "RD40", "answer": ["Option A", "None of these"]}).json["saved"]["answer"] == ["None of these"]
    assert post(client, path, {"question": "RD40", "answer": []}).json["saved"]["answer"] == ""
    assert "Choose from the answers shown" in post(client, path, {"question": "RD40", "answer": ["Option Z"]}).json["error"]
    from trust.risk import engine_bridge
    assert engine_bridge.engine_input_layout({"id": "x", "name": "X"}, {"RD40": ["Option A", "Option C"]})["answers"]["RD40"] == "Option A; Option C"


def test_an_older_saved_text_answer_still_counts_for_a_tick_any_question():
    question = {"field": "RD40", "kind": "tick_any", "choices": ["Option A", "None of these"]}
    assert question_list.answers_by_field([question], {"RD40": "Option A"}) == {"RD40": "Option A"}
    tree = language.read_trigger("'Option A' in get('RD40')")
    assert language.evaluate(tree, {"RD40": "Option A"}.get) is True


@pytest.mark.parametrize("word", ["MultiSelect", "Multi-select", "Multiple choice", "Checkbox", "Checkboxes", "List", "multi_select"])
def test_questionnaire_words_for_several_answers_mean_tick_any(word):
    import json
    mapping = json.loads((pathlib.Path(__file__).resolve().parents[1] / "config" / "risk_questionnaire_map.json").read_text())
    from trust.risk import seed
    assert seed.kind_from_word(word, mapping) == "tick_any"


def test_an_uploaded_questionnaire_makes_a_tick_any_question_with_options_from_the_file_or_the_trigger(client, tmp_path):
    send(client, "risks", "load", RISK_FILES)
    drivers_text = ("risk_drivers:\n  RD40:\n    trigger: \"('Option A' in get('RD40'))\"\n    questionnaire_fields: [RD40]\n    rationale: \"Option A is used.\"\n"
                    "  RD42:\n    trigger: \"get('RD42') == 'Used' or get('RD42') == 'Other'\"\n    questionnaire_fields: [RD42]\n    rationale: \"Used.\"\n")
    send(client, "drivers", "load", [write(tmp_path, "driver_mapping.yaml", drivers_text)])
    text = ("questions:\n  - field: RD40\n    question: Which of these are used?\n    type: MultiSelect\n    options: [Option A, Option B]\n"
            "  - field: RD42\n    question: Which are used here?\n    type: Checkboxes\n")
    checked = send(client, "questions", "check", [write(tmp_path, "q.yaml", text)]).json
    assert checked["problems"] == []
    assert send(client, "questions", "load", [write(tmp_path, "q.yaml", text)]).json["ok"]
    by_field = {question["field"]: question for question in site.load_registers()["questions"]}
    assert by_field["RD40"]["kind"] == "tick_any" and by_field["RD40"]["choices"] == ["Option A", "Option B", "None of these"]
    assert by_field["RD42"]["kind"] == "tick_any" and by_field["RD42"]["choices"] == ["Used", "Other", "None of these"]
