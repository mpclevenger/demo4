"""The one way to edit things (owner, 15 Nov 2026): the five first lists, with worked examples.

Every example uses the made-up risks and drivers in tools/test_risks and the made-up TRUST teams in tests/risk_teams.py
(TEST data only). The worked
assessment is Payments answering WORKED_ANSWERS, the same answers test_risk_site.py rates by hand.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust import editable, storage, web  # noqa: E402
from trust.risk import groups, site  # noqa: E402
from test_risk_site import HEADERS, TEST_RISKS, WORKED_ANSWERS, answer_all, client, post, test_files  # noqa: E402,F401

PAYMENTS = "payments"


def edit(client, slug, action, key, values, reason="Because the owner asked.", path="save"):
    return post(client, f"/api/edit/{slug}/{path}", {"action": action, "key": key, "values": values, "reason": reason})


def submit_payments(client):
    answer_all(client, WORKED_ANSWERS, PAYMENTS)
    reply = post(client, f"/api/risk/groups/{PAYMENTS}/submit", {"confirm_unanswered": True})
    assert reply.status_code == 200, reply.json
    return client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["assessment"]["result"]["risks"]


# ----------------------------------------------------------------------------- nothing saved yet

def test_with_nothing_saved_the_site_reads_the_files(client):
    loaded = site.load_registers()
    assert loaded["settings"] == {"medium_share_above": 0.3, "elevated_likelihood_at_least": "HIGH", "elevated_impact_at_least": "HIGH"}
    assert loaded["questions"] == loaded["from_files"]["questions"]
    assert [group["id"] for group in groups.load()] == ["payments", "cards", "lending", "treasury", "print-services"]
    for slug in editable.SLUGS:
        reply = client.get(f"/api/edit/{slug}")
        assert reply.status_code == 200 and reply.json["history"] == []
    assert client.get("/api/edit/rating-settings").json["can_save"] is True      # TRUST runs open in the tests


# ----------------------------------------------------------------------------- 1. rating settings

def test_raising_the_medium_share_moves_two_risks_for_payments_from_medium_to_low(client):
    """Payments' worked assessment: air.change.01 and air.data.02 each have one likelihood driver of three on, 33%.
    That is above the Medium share of 30%, so Medium. Raise the share to 50% and 33% is no longer above it: Low."""
    before = submit_payments(client)
    assert before["air.change.01"]["likelihood"] == before["air.data.02"]["likelihood"] == "MEDIUM"

    shown = edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.5"}, path="preview").json
    assert shown["differences"] == [{"label": "Value", "before": "0.3", "after": "0.5"}]
    assert [(move["group"], move["risk"], move["what"], move["before"], move["after"]) for move in shown["moves"]] == [
        ("Payments", "air.change.01", "Likelihood", "Medium", "Low"),
        ("Payments", "air.data.02", "Likelihood", "Medium", "Low")]

    assert edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.5"}).status_code == 200
    assert site.load_registers()["settings"]["medium_share_above"] == 0.5
    assert client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["assessment"]["result"]["risks"]["air.change.01"]["likelihood"] == "MEDIUM"   # saved ratings don't change
    post(client, f"/api/risk/groups/{PAYMENTS}/submit", {"confirm_unanswered": True})
    after = client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["assessment"]["result"]["risks"]
    assert after["air.change.01"]["likelihood"] == after["air.data.02"]["likelihood"] == "LOW"


def test_lowering_the_elevated_levels_moves_elevated(client):
    """air.cyber.01 is High likelihood and Critical impact: Elevated. Asking for a Critical likelihood to be Elevated moves it to No."""
    submit_payments(client)
    shown = edit(client, "rating-settings", "edit", "elevated_likelihood_at_least", {"value": "CRITICAL"}, path="preview").json
    assert [(move["risk"], move["what"], move["before"], move["after"]) for move in shown["moves"]] == [("air.cyber.01", "Elevated", "Yes", "No")]


def test_a_setting_that_can_not_be_used_is_refused_with_a_plain_reason(client):
    reply = edit(client, "rating-settings", "edit", "medium_share_above", {"value": "1.5"})
    assert reply.status_code == 400 and "give a number from 0 to 1" in reply.json["error"]
    reply = edit(client, "rating-settings", "edit", "elevated_impact_at_least", {"value": "SEVERE"})
    assert reply.status_code == 400 and "choose one of the choices" in reply.json["error"]
    reply = edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.3"})
    assert reply.status_code == 400 and "Nothing is different" in reply.json["error"]
    assert client.get("/api/edit/rating-settings").json["history"] == []


def test_every_change_needs_a_reason_and_a_name(client):
    reply = edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.4"}, reason="  ")
    assert reply.status_code == 400 and "Say why" in reply.json["error"]
    reply = client.post("/api/edit/rating-settings/save", headers=HEADERS,
                        json={"action": "edit", "key": "medium_share_above", "values": {"value": "0.4"}, "reason": "Why not."})
    assert reply.status_code == 400 and "Type your name" in reply.json["error"]


def test_the_history_says_who_when_old_new_and_why(client):
    edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.4"}, reason="Try a higher share.")
    history = client.get("/api/edit/rating-settings").json["history"]
    assert len(history) == 1
    assert (history[0]["by"], history[0]["reason"], history[0]["action"]) == ("Rita Tester", "Try a higher share.", "edit")
    assert history[0]["what"] == [{"label": "Value", "before": "0.3", "after": "0.4"}]
    assert history[0]["at"]


def test_the_scoring_settings_page_is_not_touched(client):
    edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.4"})
    assert storage.setting_changes() == []


# (The Sign-off approvers list was retired on 16 Nov 2026: whoever leads the team signs off. See test_risk_signoff.py.)


# ----------------------------------------------------------------------------- 3. questions

def question(client, field):
    return next(entry for entry in client.get("/api/edit/questions").json["entries"] if entry["key"] == field)


def test_the_questions_are_loaded_from_the_risk_files_in_order(client):
    entries = client.get("/api/edit/questions").json["entries"]
    assert len(entries) == 17
    asked = [q["field"] for q in site.load_registers()["from_files"]["questions"]]
    assert [entry["key"] for entry in entries] == asked
    rd12 = question(client, "RD12")["values"]
    assert (rd12["kind"], rd12["test"], rd12["number"]) == ("number", "at least", 3)


def test_changing_the_wording_and_the_section_moves_the_question(client):
    values = dict(question(client, "RD01")["values"], text="The app keeps its own accounts.", section="Access", order=5)
    assert edit(client, "questions", "edit", "RD01", values).status_code == 200
    form = site.load_registers()["questions"]
    assert form[0]["field"] == "RD01" and form[0]["section"] == "Access" and form[0]["text"] == "The app keeps its own accounts."


def test_the_number_a_driver_must_reach_is_a_value_of_the_question(client):
    """RD12 is on at 3 or more critical processes. Move it to 2: an answer of 2 now turns it on, and the preview says so."""
    answers = dict(WORKED_ANSWERS)                                        # RD12 is 2: not on today
    answer_all(client, answers, PAYMENTS)
    post(client, f"/api/risk/groups/{PAYMENTS}/submit", {"confirm_unanswered": True})
    values = dict(question(client, "RD12")["values"], number=2)
    shown = edit(client, "questions", "edit", "RD12", values, path="preview").json
    assert shown["differences"] == [{"label": "The number", "before": "3", "after": "2"}]
    edit(client, "questions", "edit", "RD12", values)
    assert site.load_registers()["driver_rules"]["RD12"]["value"] == 2
    post(client, f"/api/risk/groups/{PAYMENTS}/submit", {"confirm_unanswered": True})
    on = [driver["code"] for driver in client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["assessment"]["result"]["drivers"]["on"]]
    assert "RD12" in on


def test_which_answer_switches_a_driver_on_can_be_turned_round(client):
    """RD01 is on when the answer is yes. Make it no: the 'yes' of the worked assessment now leaves RD01 off."""
    answer_all(client, WORKED_ANSWERS, PAYMENTS)
    post(client, f"/api/risk/groups/{PAYMENTS}/submit", {"confirm_unanswered": True})
    values = dict(question(client, "RD01")["values"], switches_on="no")
    shown = edit(client, "questions", "edit", "RD01", values, path="preview").json
    assert any(move["what"] == "Elevated" and move["risk"] == "air.cyber.01" for move in shown["moves"])
    edit(client, "questions", "edit", "RD01", values)
    assert next(q for q in site.load_registers()["questions"] if q["field"] == "RD01")["yes_means_field_is"] is False


def test_retiring_a_question_takes_it_off_the_form_and_it_can_come_back(client):
    assert edit(client, "questions", "retire", "RD02", None, reason="No longer asked.").status_code == 200
    assert "RD02" not in [q["field"] for q in site.load_registers()["questions"]]
    assert question(client, "RD02")["retired"] is True
    reply = edit(client, "questions", "add", "", dict(question(client, "RD02")["values"]))
    assert reply.status_code == 400 and "Restore it" in reply.json["error"]
    edit(client, "questions", "restore", "RD02", None, reason="Needed after all.")
    assert "RD02" in [q["field"] for q in site.load_registers()["questions"]]


def test_a_driver_answered_from_data_has_no_question(client):
    values = {"driver": "RD22", "section": "Change", "order": 500, "text": "How often?", "kind": "number", "test": "at least", "number": 1}
    reply = edit(client, "questions", "add", "", values)
    assert reply.status_code == 400 and "prevailing median" in reply.json["error"]


# ----------------------------------------------------------------------------- 4. building blocks

def test_a_risk_can_be_placed_in_another_building_block(client):
    """air.ops.02 is placed in Stability by its own id. Place it in Security: the registers show it, and the history keeps the reason."""
    assert edit(client, "building-blocks", "edit", "risk:air.ops.02", {"applies_to": "risk", "name": "air.ops.02", "block": "Security"}).status_code == 200
    registers = client.get("/api/risk/registers").json
    assert next(risk for risk in registers["risks"] if risk["id"] == "air.ops.02")["block"] == "Security"
    shown = edit(client, "building-blocks", "edit", "risk:air.ops.01", {"applies_to": "risk", "name": "air.ops.01", "block": "Releases"}, path="preview").json
    assert shown["can_move_ratings"] is False


def test_a_placement_for_a_risk_or_domain_that_does_not_exist_is_refused(client):
    reply = edit(client, "building-blocks", "add", "", {"applies_to": "risk", "name": "air.nope.01", "block": "Security"})
    assert reply.status_code == 400 and "There is no risk 'air.nope.01'" in reply.json["error"]
    reply = edit(client, "building-blocks", "add", "", {"applies_to": "domain", "name": "Weather", "block": "Security"})
    assert reply.status_code == 400 and "No risk has the domain 'Weather'" in reply.json["error"]
    reply = edit(client, "building-blocks", "add", "", {"applies_to": "domain", "name": "Cyber", "block": "Made Up"})
    assert reply.status_code == 400 and "Building block: choose one of the choices" in reply.json["error"]


def test_retiring_a_risks_own_placement_falls_back_to_its_domain(client):
    edit(client, "building-blocks", "retire", "risk:air.data.02", None, reason="Use the domain's.")
    registers = client.get("/api/risk/registers").json
    assert next(risk for risk in registers["risks"] if risk["id"] == "air.data.02")["block"] == "Not placed yet"   # Data has no domain placement in the test file


# ----------------------------------------------------------------------------- 5. drivers answered from data

def test_a_data_driver_keeps_median_or_a_fixed_number(client):
    # Every data driver in the made-up risks is answered by "Calculations you define", so none shows as "not calculated" here.
    assert client.get("/api/edit/data-drivers").json["entries"] == []
    # Retire two of those calculations: their drivers come back to this list, with the engine's rule as the start.
    for code in ("RD22", "RD44"):
        assert edit(client, "calculations", "retire", code, None).status_code == 200
    entries = client.get("/api/edit/data-drivers").json["entries"]
    assert [entry["key"] for entry in entries] == ["RD22", "RD44"]
    assert entries[0]["values"]["basis"] == "Prevailing median"
    values = dict(entries[0]["values"], basis="Fixed number", fixed_number="12")
    assert edit(client, "data-drivers", "edit", "RD22", values).status_code == 200
    saved = next(entry for entry in client.get("/api/edit/data-drivers").json["entries"] if entry["key"] == "RD22")
    assert (saved["values"]["basis"], saved["values"]["fixed_number"]) == ("Fixed number", 12)
    reply = edit(client, "data-drivers", "edit", "RD44", dict(entries[1]["values"], basis="Fixed number", fixed_number=""))
    assert reply.status_code == 400 and "The fixed number" in reply.json["error"]
    assert edit(client, "data-drivers", "retire", "RD22", None).status_code == 400            # a fixed list: no retiring
    assert "not known" in client.get("/api/edit/data-drivers").json["list"]["notes"][0]      # a driver no calculation answers
    assert site.load_registers()["driver_rules"]["RD22"]["test"] == "above the prevailing median"   # the engine's rule is not changed


# ----------------------------------------------------------------------------- the download

# ----------------------------------------------------------------------------- who may save

@pytest.fixture
def enforced(client, tmp_path, monkeypatch):
    access_file = tmp_path / "access.json"
    access_file.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups",
                                       "groups": {"tech_risk": ["TR"], "cto_leadership": ["CTO"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access_file))
    return client


def test_tech_risk_saves_and_everyone_who_can_see_the_page_reads_the_history(enforced):
    tech_risk = {"X-User": "tr1", "X-Groups": "TR", **HEADERS}
    leader = {"X-User": "cto1", "X-Groups": "CTO", **HEADERS}
    body = {"action": "edit", "key": "medium_share_above", "values": {"value": "0.4"}, "reason": "Try."}
    assert enforced.post("/api/edit/rating-settings/save", json=body, headers=leader).status_code == 403
    assert enforced.post("/api/edit/rating-settings/preview", json=body, headers=leader).status_code == 403
    saved = enforced.post("/api/edit/rating-settings/save", json=body, headers=tech_risk)
    assert saved.status_code == 200 and saved.json["history"][0]["by"] == "tr1"
    read = enforced.get("/api/edit/rating-settings", headers=leader).json
    assert read["can_save"] is False and len(read["history"]) == 1


def test_the_menu_lists_every_list_after_changes_are_saved(client):
    edit(client, "rating-settings", "edit", "medium_share_above", {"value": "0.4"})
    menu = client.get("/api/edit").json
    assert [item["slug"] for item in menu["lists"]] == editable.SLUGS
    assert "sign-off-approvers" not in [item["slug"] for item in menu["lists"]]          # retired


def test_a_csv_cell_that_starts_like_a_formula_is_kept_as_text():
    assert editable._safe_in_a_spreadsheet(-5) == -5 and editable._safe_in_a_spreadsheet(None) == ""
    assert editable._safe_in_a_spreadsheet("=cmd|x") == "'=cmd|x"
    assert editable._safe_in_a_spreadsheet("@sum") == "'@sum" and editable._safe_in_a_spreadsheet("boss1") == "boss1"
