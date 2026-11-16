"""The Risk site's front page (owner, 16 Nov 2026): Continue an assessment, Start a new assessment, View results.

Made-up teams from tests/risk_teams.py (TEST data only). Worked example: Lending has 17 questions on its form. After
a Submit, Start opens a new assessment; confirming 2 of the answers makes it "2 of 17 confirmed or changed".
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))
from test_risk_site import GROUP, HEADERS, WORKED_ANSWERS, answer_all, client, post, test_files  # noqa: E402,F401
from trust import storage  # noqa: E402

QUESTIONS_ON_THE_FORM = 17


def listed(client, group_id=GROUP, headers=HEADERS):
    return next(group for group in client.get("/api/risk/groups", headers=headers).json["groups"] if group["id"] == group_id)


def test_a_team_never_assessed_has_nothing_open_and_no_results(client):
    row = listed(client)
    assert row["open"] is None and row["assessments"] == 0 and row["results_status"] is None


def test_answering_without_pressing_start_still_shows_as_in_progress(client):
    post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD12", "answer": "2"})
    post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD01", "answer": "yes"})
    opened = listed(client)["open"]
    assert opened["status"] == "Draft" and opened["answered"] == 2 and opened["of"] == QUESTIONS_ON_THE_FORM
    assert opened["started"]["by"] == "Rita Tester" and opened["last_saved"]["by"] == "Rita Tester"


def test_start_records_who_and_when_and_there_is_one_open_assessment_per_team(client):
    first = post(client, f"/api/risk/groups/{GROUP}/start", {})
    assert first.json["started"] is True and first.json["start"]["by"] == "Rita Tester"
    again = post(client, f"/api/risk/groups/{GROUP}/start", {})
    assert again.json["started"] is False                                      # one open assessment per team
    assert len(storage.risk_starts(GROUP)) == 1
    opened = listed(client)["open"]
    assert opened["started"]["at"] == first.json["start"]["at"] and opened["answered"] == 0


def test_after_a_submit_a_new_assessment_starts_pre_filled_and_counts_what_was_confirmed(client):
    answer_all(client, WORKED_ANSWERS)
    post(client, f"/api/risk/groups/{GROUP}/submit", {})
    row = listed(client)
    assert row["open"] is None and row["results_status"] == "Submitted" and row["assessments"] == 1

    post(client, f"/api/risk/groups/{GROUP}/start", {})
    form = client.get(f"/api/risk/groups/{GROUP}").json
    pre_filled = {q["field"]: q["answer"] for section in form["sections"] for q in section["questions"] if q["answer"]}
    assert pre_filled == WORKED_ANSWERS                                        # the last submitted answers are in place
    assert form["group"]["submitted_at"] is not None                           # the form can say "Last confirmed"

    assert listed(client)["open"]["answered"] == 0
    post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD01", "answer": "yes"})      # "Still true"
    post(client, f"/api/risk/groups/{GROUP}/answers", {"question": "RD12", "answer": "3"})        # changed
    opened = listed(client)["open"]
    assert (opened["answered"], opened["of"], opened["counted_as"]) == (2, QUESTIONS_ON_THE_FORM, "confirmed or changed")

    post(client, f"/api/risk/groups/{GROUP}/submit", {})
    assert listed(client)["open"] is None                                      # a Submit closes it


def test_sent_back_is_open_with_the_reason_and_signed_off_shows_in_results(client):
    answer_all(client, WORKED_ANSWERS)
    post(client, f"/api/risk/groups/{GROUP}/submit", {})
    post(client, f"/api/risk/groups/{GROUP}/signoff", {"note": "Looks right."})
    assert listed(client)["results_status"] == "Signed off"
    post(client, f"/api/risk/groups/{GROUP}/submit", {})
    post(client, f"/api/risk/groups/{GROUP}/sendback", {"reason": "Check the DR test age."})
    row = listed(client)
    assert row["results_status"] == "Sent back" and row["open"]["status"] == "Sent back"
    assert row["signoff"]["note"] == "Check the DR test age."


def test_the_list_never_carries_ratings_or_counts_that_compare_teams(client):
    answer_all(client, WORKED_ANSWERS)
    post(client, f"/api/risk/groups/{GROUP}/submit", {})
    row = listed(client)
    for forbidden in ("elevated", "applicable", "counts", "risks"):
        assert forbidden not in row


def test_starting_needs_the_right_to_answer(client, tmp_path, monkeypatch):
    """With the access add-on on, the team's own people may start; someone outside the team may not (and nothing is kept)."""
    import json
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    outsider = {"X-User": "pay2", "X-Groups": "", "X-TRUST": "1"}
    refused = client.post(f"/api/risk/groups/{GROUP}/start", json={}, headers=outsider)
    assert refused.status_code == 403 and storage.risk_starts(GROUP) == []
    teammate = {"X-User": "pat1", "X-Groups": "", "X-TRUST": "1"}
    assert client.post(f"/api/risk/groups/{GROUP}/start", json={}, headers=teammate).json["started"] is True
    assert "pat1" in storage.risk_starts(GROUP)[0]["by"]
