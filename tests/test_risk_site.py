"""The Risk site, first slice (owner, 15 Nov 2026): the questionnaire, the site rating a group, the results.

Every example uses the made-up risks and drivers in tools/test_risks and the made-up TRUST teams in tests/risk_teams.py
(TEST data only). The worked example below is one made-up team, "Lending", whose answers you can follow by hand.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, storage, web  # noqa: E402
from trust.risk import assess, blocks, files, groups, questions as question_list, rating  # noqa: E402
from risk_teams import PEOPLE, put_made_up_teams  # noqa: E402

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
HEADERS = {"X-TRUST": "1"}
GROUP = "lending--lending-platform"
MONTH = "2026-10"

# The answers for the worked example. "yes" means the sentence on the form is true for the group.
WORKED_ANSWERS = {
    "RD01": "yes",          # the application keeps its own user accounts
    "RD02": "yes",          # the team handles confidential client data
    "RD03": "yes",          # shared service accounts with broad access
    "RD23": "yes",          # some deployments need no change ticket
    "RD54": "yes",          # clients use the team's services directly
    "RD30": "no", "RD31": "no", "RD36": "no", "RD45": "no", "RD50": "no", "RD70": "no", "RD71": "no",
    "RD72": "no", "RD40": "no",
    "RD14_pct": "25%",      # 25% of the team: not more than 40%
    "RD12": "2",            # 2 critical processes: not 3 or more
    "RD41_days": "100",     # last DR test 100 days ago: not more than 365
}


@pytest.fixture
def test_files(monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))


@pytest.fixture
def client(tmp_path, monkeypatch, test_files):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()                                   # a group is a TRUST team, so TRUST must hold teams
    return web.app.test_client()


def post(client, path, body, headers=HEADERS):
    return client.post(path, json={"by": "Rita Tester", **body}, headers=headers)


def answer_all(client, answers, group=GROUP):
    for field, answer in answers.items():
        reply = post(client, f"/api/risk/groups/{group}/answers", {"question": field, "answer": answer})
        assert reply.status_code == 200, reply.json


def risk_names(assessment, key):
    return sorted(risk_id for risk_id, entry in assessment["risks"].items() if entry.get(key))


# ----------------------------------------------------------------------------- the questions

def test_the_form_is_built_from_the_drivers_file(test_files):
    """17 drivers have a questionnaire field, so 17 questions; the 4 answered from data are not asked.
    Sections are the risk domains: Change, Cyber, Data, Operational (four sections)."""
    loaded = {"rules": files.driver_rules(TEST_RISKS), "risks": config.risks()}
    form = question_list.build(loaded["rules"], loaded["risks"])
    assert len(form) == 17
    assert [section["name"] for section in question_list.sections(form)] == ["Change", "Cyber", "Data", "Operational"]
    asked = {question["field"] for question in form}
    assert {"RD22", "RD44", "RD63", "RD64"}.isdisjoint(asked)
    assert next(q for q in form if q["field"] == "RD12")["kind"] == "number"
    assert next(q for q in form if q["field"] == "RD01")["kind"] == "yes_no"


def test_yes_always_means_the_sentence_is_true_even_for_an_is_no_driver(test_files):
    """RD31 is on when its field is FALSE ("there are no automated tests"). Answering yes to that sentence turns it on."""
    rules = files.driver_rules(TEST_RISKS)
    form = question_list.build(rules, config.risks())
    for answer, driver_is_on in (("yes", True), ("no", False)):
        by_field = question_list.answers_by_field(form, {"RD31": answer})
        from trust.risk import drivers
        assert drivers.driver_is_on(rules["RD31"], by_field) is driver_is_on


def test_an_answer_that_is_not_a_yes_no_or_a_number_is_refused(test_files):
    form = question_list.build(files.driver_rules(TEST_RISKS), config.risks())
    yes_no = next(q for q in form if q["field"] == "RD01")
    number = next(q for q in form if q["field"] == "RD12")
    assert question_list.clean_answer(yes_no, " Yes ") == "yes"
    assert question_list.clean_answer(number, " 4 ") == "4"
    assert question_list.clean_answer(number, "") == ""                # clearing an answer
    with pytest.raises(ValueError, match="yes or no"):
        question_list.clean_answer(yes_no, "maybe")
    with pytest.raises(ValueError, match="Type a number"):
        question_list.clean_answer(number, "lots")


# ----------------------------------------------------------------------------- the rating, by hand

def worked_assessment(answers):
    risks = config.risks()
    rules = files.driver_rules(TEST_RISKS)
    form = question_list.build(rules, risks)
    return assess.assess_group(risks, rules, form, answers, rating.starting_settings(), blocks.load())


def test_one_group_rated_from_its_answers(test_files):
    """Drivers on: RD01, RD02, RD03, RD23, RD54 (the five "yes" answers). RD22, RD44, RD63, RD64 come from data
    and are not known. Then, for air.cyber.01 (the made-up "External data breach"):
      likelihood drivers RD01, RD03, RD36: two of three on = 67%, above its High rule's 60% and RD01 is on -> High
      client impact: RD02 and RD54 are both on -> Critical, so the overall impact is Critical
      High likelihood and Critical impact -> Elevated
    The other seven risks all apply, but each has a Medium or Low likelihood, so none is Elevated."""
    result = worked_assessment(WORKED_ANSWERS)
    assert [driver["code"] for driver in result["drivers"]["on"]] == ["RD01", "RD02", "RD03", "RD23", "RD54"]
    assert [driver["code"] for driver in result["drivers"]["not_known"]] == ["RD22", "RD44", "RD63", "RD64"]

    breach = result["risks"]["air.cyber.01"]
    assert (breach["likelihood"], breach["impact"], breach["elevated"]) == ("HIGH", "CRITICAL", True)
    assert breach["impact_by_kind"] == {"financial_impact": "MEDIUM", "client_impact": "CRITICAL", "regulatory_impact": "MEDIUM"}
    assert breach["block"] == "Security"

    assert risk_names(result, "elevated") == ["air.cyber.01"]
    assert result["counts"] == {"risks": 8, "applicable": 8, "not_applicable": 0, "elevated": 1}

    # one third of the likelihood drivers on is above the Medium share of 30%: Medium, not Low
    assert result["risks"]["air.change.01"]["likelihood"] == "MEDIUM"
    assert result["risks"]["air.change.02"]["likelihood"] == "LOW"       # none of RD22, RD31, RD63 is on


def test_the_steps_say_the_numbers_a_person_can_check(test_files):
    result = worked_assessment(WORKED_ANSWERS)
    steps = {step["title"]: step for step in result["risks"]["air.cyber.01"]["steps"]}
    assert steps["Likelihood"]["lines"][0] == "2 of 3 likelihood drivers on = 67%."
    assert "High needs: the driver share is more than 60% and (RD01 is on or RD03 is on). Met." in steps["Likelihood"]["lines"]
    assert steps["Likelihood"]["result"] == "High"
    assert steps["Impact"]["result"] == "Critical"
    assert steps["Elevated?"]["result"] == "Elevated"
    medium = {step["title"]: step for step in result["risks"]["air.change.01"]["steps"]}["Likelihood"]
    assert medium["lines"][-1] == "Neither rule is met, so the share decides: 33% is above the Medium share of 30%."


def test_nothing_answered_means_no_risk_applies(test_files):
    """No driver is on, so none of the eight risks applies; the results page lists them under "Does not apply"."""
    result = worked_assessment({})
    assert result["counts"] == {"risks": 8, "applicable": 0, "not_applicable": 8, "elevated": 0}
    assert result["risks"]["air.cyber.01"] == {**result["risks"]["air.cyber.01"], "applicable": False}
    assert [step["title"] for step in result["risks"]["air.cyber.01"]["steps"]] == ["Does it apply?"]
    assert len(result["drivers"]["not_known"]) == 21                        # nothing is known yet


def test_the_site_agrees_with_the_rating_rules_it_calls(test_files):
    risks = config.risks()
    settings = rating.starting_settings()
    result = worked_assessment(WORKED_ANSWERS)
    active = {driver["code"] for driver in result["drivers"]["on"]}
    expected = rating.rate_group(risks, active, settings)
    for risk_id, rated in expected.items():
        for key, value in rated.items():
            assert result["risks"][risk_id][key] == value, (risk_id, key)


def test_a_data_driver_is_never_guessed(test_files):
    """RD22 and RD44 come from data. With no data they are "not known", not on and not off."""
    result = worked_assessment(WORKED_ANSWERS)
    assert "RD22" not in [d["code"] for d in result["drivers"]["on"] + result["drivers"]["off"]]


# ----------------------------------------------------------------------------- saving, submitting, the trend

def test_saving_an_answer_twice_keeps_both_rows_and_the_later_one_stands(client):
    path = f"/api/risk/groups/{GROUP}/answers"
    first = post(client, path, {"question": "RD12", "answer": "2", "by": "Ana"}).json
    second = post(client, path, {"question": "RD12", "answer": "5", "by": "Ben"}).json
    assert first["ok"] and second["ok"]
    rows = storage.risk_answers(GROUP)
    assert [(row["question"], row["answer"], row["by"]) for row in rows] == [("RD12", "2", "Ana"), ("RD12", "5", "Ben")]
    form = client.get(f"/api/risk/groups/{GROUP}").json
    question = next(q for section in form["sections"] for q in section["questions"] if q["field"] == "RD12")
    assert (question["answer"], question["by"]) == ("5", "Ben")                  # "Last saved by Ben"
    assert form["unanswered"] == 16 and form["group"]["status"] == "Draft"


def test_a_change_needs_a_name_and_the_trust_header(client):
    path = f"/api/risk/groups/{GROUP}/answers"
    assert client.post(path, json={"question": "RD12", "answer": "2", "by": "Ana"}).status_code == 403   # no X-TRUST header
    nameless = client.post(path, json={"question": "RD12", "answer": "2", "by": " "}, headers=HEADERS)
    assert nameless.status_code == 400 and "Type your name" in nameless.json["error"]
    assert client.post(path, json={"question": "RD99", "answer": "2", "by": "A"}, headers=HEADERS).status_code == 400
    assert "Type a number" in post(client, path, {"question": "RD12", "answer": "lots"}).json["error"]
    assert storage.risk_answers(GROUP) == []                                     # nothing was kept


def test_submit_lists_the_unanswered_questions_first(client):
    answer_all(client, {"RD01": "yes", "RD12": "2"})
    reply = post(client, f"/api/risk/groups/{GROUP}/submit", {})
    assert reply.status_code == 409 and not reply.json["ok"]
    listed = [item["field"] for item in reply.json["unanswered"]]
    assert len(listed) == 15 and "RD01" not in listed and listed[0] == "RD02"       # in the order of the form
    assert "15 questions have no answer yet" in reply.json["error"]
    assert storage.risk_assessments(GROUP) == []                                  # nothing was submitted
    sent = post(client, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True})
    assert sent.status_code == 200 and sent.json["unanswered"] == 15


def test_a_second_submit_is_a_second_assessment_and_the_trend_compares_them(client):
    """First Submit: cyber.01 is High / Critical / Elevated. Then RD03 changes to no: two of three likelihood drivers
    become one of three = 33%, below High's 60% and above Medium's 30%, so cyber.01 is Medium / Critical.
    Likelihood went down and impact stayed: "better". air.data.02 has not moved: "no change"."""
    answer_all(client, WORKED_ANSWERS)
    first = post(client, f"/api/risk/groups/{GROUP}/submit", {})
    assert first.status_code == 200 and first.json["counts"]["elevated"] == 1
    first_assessment = client.get(f"/api/risk/groups/{GROUP}/assessment").json["assessment"]
    assert first_assessment["result"]["has_previous"] is False
    assert all(entry["trend"] is None for entry in first_assessment["result"]["risks"].values())     # a first one: no trend
    assert client.get(f"/api/risk/groups/{GROUP}").json["group"]["status"] == "Submitted"

    post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD03", "answer": "no"})
    assert client.get(f"/api/risk/groups/{GROUP}").json["group"]["status"] == "Draft"       # changed since the Submit
    second = post(client, f"/api/risk/groups/{GROUP}/submit", {})
    assert second.json["counts"]["elevated"] == 0 and second.json["assessment_id"] != first.json["assessment_id"]

    shown = client.get(f"/api/risk/groups/{GROUP}/assessment").json
    assert len(shown["earlier"]) == 2 and len(storage.risk_assessments(GROUP)) == 2           # both are kept
    risks = shown["assessment"]["result"]["risks"]
    assert (risks["air.cyber.01"]["likelihood"], risks["air.cyber.01"]["trend"]) == ("MEDIUM", "better")
    assert risks["air.data.02"]["trend"] == "no change"
    old = client.get(f"/api/risk/groups/{GROUP}/assessment?id={first.json['assessment_id']}").json["assessment"]
    assert old["result"]["risks"]["air.cyber.01"]["likelihood"] == "HIGH"                      # the first one is unchanged


def test_the_groups_page_shows_each_status_and_the_elevated_count(client):
    assert {g["id"]: g["status"] for g in client.get("/api/risk/groups").json["groups"]}[GROUP] == "Not started"
    post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD12", "answer": "2"})
    answer_all(client, WORKED_ANSWERS)
    shown = {g["id"]: g for g in client.get("/api/risk/groups").json["groups"]}
    assert shown[GROUP]["status"] == "Draft" and "elevated" not in shown[GROUP]
    post(client, f"/api/risk/groups/{GROUP}/submit", {})
    shown = {g["id"]: g for g in client.get("/api/risk/groups").json["groups"]}
    assert shown[GROUP]["status"] == "Submitted"
    assert "elevated" not in shown[GROUP] and "applicable" not in shown[GROUP]   # never listed beside other groups' results
    assert shown["payments--payments-core"]["status"] == "Not started"                          # other groups are separate forms


def test_the_registers_are_read_from_the_risk_files(client):
    got = client.get("/api/risk/registers").json
    assert len(got["risks"]) == 8 and len(got["drivers"]) == 21 and len(got["questions"]) == 17
    breach = next(risk for risk in got["risks"] if risk["id"] == "air.cyber.01")
    assert breach["block"] == "Security"
    assert {risk["id"]: risk["block"] for risk in got["risks"]} == {
        "air.cyber.01": "Security", "air.cyber.02": "Security", "air.change.01": "Releases", "air.change.02": "Releases",
        "air.ops.01": "Resiliency", "air.ops.02": "Stability", "air.data.01": "Accountability", "air.data.02": "Security"}


# ----------------------------------------------------------------------------- the pages

def test_the_page_and_its_own_files_are_served_and_nothing_else(client):
    page = client.get("/risk/")
    assert page.status_code == 200 and b"Risk assessment" in page.data and page.content_type.startswith("text/html")
    assert client.get("/risk/risk.css").content_type.startswith("text/css")
    assert client.get("/risk/risk-core.js").content_type.startswith("text/javascript")
    for refused in ("index.html", "nope.js", ".hidden.js", "..%2f..%2fconfig%2frisk_groups.json", "risk.py"):
        assert client.get(f"/risk/{refused}").status_code == 404, refused


def test_the_top_bar_knows_about_the_test_environment(client, monkeypatch):
    monkeypatch.setenv("TRUST_ENV", "test")
    shown = client.get("/api/risk/me").json
    assert shown["test_env"] is True and shown["open"] is True and "TEST" in shown["env_label"]
    monkeypatch.delenv("TRUST_ENV")
    assert client.get("/api/risk/me").json["test_env"] is False


# ----------------------------------------------------------------------------- who is in a group, and who may do what

@pytest.fixture
def signed_in_client(client, tmp_path, monkeypatch):
    """TRUST with the access add-on on: the person comes from the X-User header, Tech Risk from X-Groups."""
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups",
                                  "groups": {"tech_risk": ["TRUST-TR"], "auditor": ["TRUST-Audit"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    return client


def as_person(sam, groups_header=""):
    return {"X-User": sam, "X-Groups": groups_header, "X-TRUST": "1"}


def test_a_group_is_an_l4_team_with_its_leader_and_everyone_under_them(signed_in_client):
    group = groups.find(GROUP)
    assert groups.members(group, MONTH) == ["lford4", "pat1", "sam2"]
    assert groups.lead_name(group, MONTH) == "Lena Ford"
    assert (group["name"], group["l3_id"], group["l3_name"]) == ("Lending Platform", "lending", "Lending")   # named after its Supervisory Organization
    assert groups.managers_above(["lford4", "pat1", "sam2"], MONTH) == {"lford4", "erook6", "scrane1", "cto.demo"}
    assert "erook6" not in groups.members(group, MONTH)                         # the L3 lead is in no L4 team


def test_who_may_see_answer_and_submit(signed_in_client):
    client = signed_in_client
    shown = lambda who: [g["id"] for g in client.get("/api/risk/groups", headers=who).json["groups"]]
    assert shown(as_person("pat1")) == [GROUP]                                    # a member sees only their own group
    assert shown(as_person("zed9")) == ["cards--cards-risk"]                       # someone in another team sees only that team
    assert shown(as_person("erook6")) == ["lending--lending-platform", "lending--lending-servicing"]   # the L3 lead sees their L4 teams
    assert GROUP in shown(as_person("scrane1"))                                   # the manager above
    assert GROUP in shown(as_person("trisk", "TRUST-TR"))
    assert GROUP in shown(as_person("audit1", "TRUST-Audit"))                     # an auditor reads everything

    path = f"/api/risk/groups/{GROUP}"
    assert client.get(path, headers=as_person("zed9")).status_code == 403
    answer = {"question": "RD12", "answer": "2"}
    assert client.post(path + "/answers", json=answer, headers=as_person("zed9")).status_code == 403
    assert client.post(path + "/answers", json=answer, headers=as_person("audit1", "TRUST-Audit")).status_code == 403
    assert client.post(path + "/answers", json=answer, headers=as_person("pat1")).status_code == 200
    # Pat is in the group and may answer, but only the lead, the managers above, or Tech Risk submit
    assert client.post(path + "/submit", json={"confirm_unanswered": True}, headers=as_person("pat1")).status_code == 403
    assert client.post(path + "/submit", json={"confirm_unanswered": True}, headers=as_person("erook6")).status_code == 200


def test_tech_risk_answers_are_marked_from_tech_risk(signed_in_client):
    client = signed_in_client
    path = f"/api/risk/groups/{GROUP}/answers"
    client.post(path, json={"question": "RD12", "answer": "2"}, headers=as_person("pat1"))
    client.post(path, json={"question": "RD01", "answer": "yes"}, headers=as_person("trisk", "TRUST-TR"))
    rows = {row["question"]: row for row in storage.risk_answers(GROUP)}
    assert rows["RD12"]["from_tech_risk"] is False and rows["RD01"]["from_tech_risk"] is True
    form = client.get(f"/api/risk/groups/{GROUP}", headers=as_person("pat1")).json
    question = next(q for section in form["sections"] for q in section["questions"] if q["field"] == "RD01")
    assert question["from_tech_risk"] is True


def test_an_l3_team_with_no_l4_team_has_no_group(client):
    shown = {g["id"]: g for g in client.get("/api/risk/groups").json["groups"]}
    assert not [group_id for group_id in shown if group_id.startswith("print-services")]
    assert shown[GROUP]["people"] == 3 and shown[GROUP]["can"]["answer"] is True       # while TRUST runs open, anyone may answer
    assert client.get("/api/risk/groups").json["note"] is None
    assert client.get("/api/risk/family/print-services").json == {"ok": True, "groups": []}


def test_the_groups_are_the_l4_teams_under_their_l3_team_in_trusts_order(client):
    from risk_teams import ALL_GROUPS
    assert [group["id"] for group in groups.load()] == [group_id for group_id in ALL_GROUPS]
    assert [(group["name"], group["l3_name"]) for group in groups.load()] == [
        ("Payments Core", "Payments"), ("Cards Ops", "Cards"), ("Cards Risk", "Cards"), ("Lending Platform", "Lending"),
        ("Lending Servicing", "Lending"), ("Treasury Ops", "Treasury")]
    listed = client.get("/api/risk/groups").json["groups"]
    assert [group["id"] for group in listed] == [group["id"] for group in groups.load()]
    assert [(group["l3_id"], group["l3_name"]) for group in listed][:3] == [("payments", "Payments"), ("cards", "Cards"), ("cards", "Cards")]


def test_with_no_teams_in_trust_the_site_says_so_plainly(tmp_path, monkeypatch, test_files):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    empty = web.app.test_client()
    answer = empty.get("/api/risk/groups").json
    assert answer["groups"] == [] and answer["note"] == groups.NO_TEAMS_YET
    assert "TRUST has no L4 teams yet" in answer["note"]


def test_an_l4_team_of_a_shared_group_is_listed_under_both_family_names(client):
    """A person placed in a shared group (a lead of several families) has the shared group's id as their L3 team; its name
    is the family names joined."""
    mapped = storage.load_month("mapped", MONTH)
    mapped["feeds"]["hr_mapping"]["shared"] = {"shared:cards+lending": ["cards", "lending"]}
    for person in mapped["feeds"]["hr"]["people"]:
        if person["sam_account"] == "card1":
            person["family_id"] = "shared:cards+lending"
    storage.save_month("mapped", MONTH, mapped)
    group = groups.find("shared:cards+lending--cards-ops")
    assert group["l3_name"] == "Cards and Lending" and group["leads"] == ["card1"]


def test_the_l3_level_setting_decides_which_people_lead_an_l4_team(client):
    """With l3_level 2 the L4 teams are led by the people at level 3: Emery's team is Emery and everyone under her."""
    mapped = storage.load_month("mapped", MONTH)
    mapped["settings_used"] = {"l3_level": 2}
    storage.save_month("mapped", MONTH, mapped)
    emery = next(group for group in groups.load() if group["leads"] == ["erook6"])
    assert emery["name"] == "Lending" and emery["members"] == ["erook6", "lford4", "pat1", "rboyd5", "sam2"]
    assert groups.find(GROUP) is None


def test_two_l4_teams_with_the_same_name_under_one_l3_team_keep_different_ids(client):
    mapped = storage.load_month("mapped", MONTH)
    for person in mapped["feeds"]["hr"]["people"]:
        if person["sam_account"] == "rboyd5":
            person["sup_org"] = "Lending Platform (Rae Boyd)"
    storage.save_month("mapped", MONTH, mapped)
    ids = [group["id"] for group in groups.load() if group["l3_id"] == "lending"]
    assert ids == ["lending--lending-platform", "lending--lending-platform-rboyd5"]


def test_the_l3_lead_may_view_their_l4_teams_but_a_member_of_another_l4_team_may_not(signed_in_client):
    client = signed_in_client
    path = f"/api/risk/groups/{GROUP}"
    assert client.get(path, headers=as_person("erook6")).status_code == 200
    assert client.get(path, headers=as_person("rboyd5")).status_code == 403            # same L3 team, different L4 team
    assert client.get("/api/risk/groups/lending", headers=as_person("erook6")).status_code == 404   # an old id: a plain message


def test_an_id_that_is_not_a_team_gives_a_plain_page_not_an_error(client):
    storage.add_risk_answer("old-group", "RD12", "2", "Rita", False)             # saved once, before TRUST's teams were used
    reply = client.get("/api/risk/groups/old-group")
    assert reply.status_code == 404 and reply.json["error"].startswith("There is no such team")
    assert client.get("/api/risk/groups/old-group/assessment").status_code == 404
    assert client.get("/api/risk/groups/old-group/signoff").status_code == 404
    assert client.get("/api/risk/groups/old-group/engine-input").status_code == 404
    assert client.get("/api/risk/groups").status_code == 200 and client.get("/api/risk/matrix").status_code == 200


def test_the_groups_files_are_gone():
    """The Risk site uses TRUST's teams, so the old files that listed groups are not kept."""
    root = pathlib.Path(__file__).resolve().parents[1]
    for path in (root / "config" / "risk_groups.json", TEST_RISKS / "risk_groups.json", root / "tools" / "test_risks_data_drivers" / "risk_groups.json"):
        assert not path.exists()


# ----------------------------------------------------------------------------- the same, kept in the database

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

PG_BIN = pathlib.Path(os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin"))
RISK_PG_PORT = 8716                                       # servers started in tests use ports 8700 to 8719


@pytest.mark.skipif(not (PG_BIN / "initdb").exists(), reason="Postgres programs not installed")
def test_answers_and_assessments_are_kept_in_the_database_too(test_files, monkeypatch):
    """Starts its own throwaway Postgres, builds the tables from the migrations, and checks the same things are kept."""
    from trust import migrate
    base = pathlib.Path(tempfile.mkdtemp(prefix="trust-risk-pg-"))
    data, sock = base / "data", base / "sock"
    sock.mkdir()
    as_user = []
    if os.geteuid() == 0:                                 # initdb won't run as root: use the postgres account
        shutil.chown(base, "postgres")
        shutil.chown(sock, "postgres")
        as_user = ["runuser", "-u", "postgres", "--"]
    run = lambda *command: subprocess.run([*as_user, *command], check=True, capture_output=True)
    run(str(PG_BIN / "initdb"), "-D", str(data), "-U", "trust", "--auth=trust", "-E", "UTF8")
    run(str(PG_BIN / "pg_ctl"), "-D", str(data), "-w", "-l", str(base / "log"),
        "-o", f"-k {sock} -c listen_addresses='' -p {RISK_PG_PORT}", "start")
    try:
        monkeypatch.setenv("DATABASE_URL", f"postgresql://trust@/postgres?host={sock}&port={RISK_PG_PORT}")
        migrate.run()
        put_made_up_teams()
        client = web.app.test_client()
        answer_all(client, {"RD12": "2", "RD01": "yes"})
        post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD12", "answer": "5"})
        assert [(row["question"], row["answer"]) for row in storage.risk_answers(GROUP)] == [
            ("RD12", "2"), ("RD01", "yes"), ("RD12", "5")]
        assert post(client, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True}).status_code == 200
        post(client, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True})
        kept = storage.risk_assessments(GROUP)
        assert len(kept) == 2 and kept[1]["result"]["has_previous"] is True
        listed = client.get("/api/risk/groups").json["groups"]
        assert {entry["id"]: entry["status"] for entry in listed}[GROUP] == "Submitted"
    finally:
        run(str(PG_BIN / "pg_ctl"), "-D", str(data), "-w", "-m", "immediate", "stop")
        shutil.rmtree(base, ignore_errors=True)


# ---- fixes from the independent review (15 Nov 2026) ----

def test_a_share_typed_without_the_percent_sign_is_refused_with_a_plain_reason():
    from trust.risk import questions
    share_question = {"field": "RD14_pct", "kind": questions.NUMBER}
    assert questions.clean_answer(share_question, "25%") == "25%"
    assert questions.clean_answer(share_question, "0.25") == "0.25"
    try:
        questions.clean_answer(share_question, "25")
        raise AssertionError("25 without a % sign should be refused")
    except ValueError as problem:
        assert "25%" in str(problem)
    count_question = {"field": "RD12", "kind": questions.NUMBER}
    assert questions.clean_answer(count_question, "25") == "25"      # a count is not a share


def test_l4_teams_worked_example():
    """Level 3 is the L3 lead. Ann (level 4) leads Platform, with Bo (5) and Cy (6, under Bo). Dee (level 4) leads
    Reports on her own. Lee (level 3) is the L3 lead and is in no L4 team. Platform has Ann, Bo and Cy: 3 people."""
    from trust import linking
    people = [
        {"sam_account": "lee", "worker": "Lee", "manager_sam": None, "reporting_level": 3, "sup_org": "Lending (Lee)", "family_id": "lending"},
        {"sam_account": "ann", "worker": "Ann", "manager_sam": "lee", "reporting_level": 4, "sup_org": "Platform (Ann)", "family_id": "lending"},
        {"sam_account": "bo", "worker": "Bo", "manager_sam": "ann", "reporting_level": 5, "sup_org": "Platform (Ann)", "family_id": "lending"},
        {"sam_account": "cy", "worker": "Cy", "manager_sam": "bo", "reporting_level": 6, "sup_org": "Platform (Ann)", "family_id": "lending"},
        {"sam_account": "dee", "worker": "Dee", "manager_sam": "lee", "reporting_level": 4, "sup_org": "", "family_id": "lending"}]
    teams = linking.l4_teams(people, 3)
    assert teams == {"ann": {"name": "Platform", "l3_id": "lending", "members": ["ann", "bo", "cy"]},
                     "dee": {"name": "Dee", "l3_id": "lending", "members": ["dee"]}}          # no Supervisory Organization: the leader's name
    who = linking.who_table(people, 3)
    assert {sam: who[sam]["l4"] for sam in ("ann", "bo", "cy", "dee", "lee")} == {"ann": "Ann", "bo": "Ann", "cy": "Ann", "dee": "Dee", "lee": ""}
