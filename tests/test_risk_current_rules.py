"""The switch "rate_with_current_rules" (owner, 17 Nov 2026): rate every team's newest answers with today's rules.

Worked example (made-up teams and risks, TEST data only): Payments submits the worked answers. RD01 ("the application
keeps its own user accounts") is on when the answer is yes, so air.cyber.01 is Elevated. Tech Risk then turns the
answer round (yes no longer switches RD01 on) WITHOUT Payments submitting again.
    Switch on:  the results page, the team page's "Risks we have raised" and the CTO markers say air.cyber.01 is no
                longer Elevated.
    Switch off: they still show what was kept at Submit (Elevated).
    Either way: the rows kept in the store are exactly as they were.
"""
import copy
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust import storage, web  # noqa: E402
from trust.risk import cto_markers, current_rules  # noqa: E402
from test_risk_site import WORKED_ANSWERS, answer_all, client, post, test_files  # noqa: E402,F401
from test_editable import PAYMENTS, edit, submit_payments  # noqa: E402

RISK = "air.cyber.01"
THE_LINE = "Rated with today's questions and rules (setting rate_with_current_rules is on)."


def turn_the_switch(client, answer):
    assert edit(client, "rating-settings", "edit", "rate_with_current_rules", {"value": answer}).status_code == 200


def turn_driver_round(client):
    """RD01 is on when the answer is yes; now it is on when the answer is no. Nobody submits again."""
    row = next(entry for entry in client.get("/api/edit/questions").json["entries"] if entry["key"] == "RD01")
    assert edit(client, "questions", "edit", "RD01", dict(row["values"], switches_on="no")).status_code == 200


def results_elevated(client):
    risks = client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["assessment"]["result"]["risks"]
    return risks[RISK]["elevated"]


def team_page_names(client):
    groups = client.get("/api/risk/family/payments").json["groups"]
    return [risk["id"] for group in groups for risk in group["elevated"]]


def marker_names(client):
    with web.app.test_request_context():
        return list(cto_markers.elevated_in_newest_assessment("payments"))


def heat_map_elevated_assessments(client):
    focus = client.get("/api/risk/matrix").json["focus"]
    return sum(item["elevated_assessments"] for item in focus if item["risk_id"] == RISK)


def test_the_switch_starts_on_and_is_on_the_rating_settings_list(client):
    assert current_rules.switch_is_on(client.get("/api/risk/registers").json["settings"]) is True
    entries = client.get("/api/edit/rating-settings").json["entries"]
    assert any(entry["key"] == "rate_with_current_rules" for entry in entries)


def test_switch_on_a_changed_driver_rule_changes_every_page_without_a_new_submit(client):
    submit_payments(client)
    assert results_elevated(client) is True and team_page_names(client) == [RISK]
    assert marker_names(client) == [RISK] and heat_map_elevated_assessments(client) == 1

    turn_driver_round(client)

    assert results_elevated(client) is False
    assert team_page_names(client) == []
    assert marker_names(client) == []
    assert heat_map_elevated_assessments(client) == 0


def test_switch_off_nothing_changes_until_the_team_submits_again(client):
    submit_payments(client)
    turn_the_switch(client, "no")
    turn_driver_round(client)
    assert results_elevated(client) is True and team_page_names(client) == [RISK]
    assert marker_names(client) == [RISK] and heat_map_elevated_assessments(client) == 1
    assert client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["rated_with_current_rules"] is None
    post(client, f"/api/risk/groups/{PAYMENTS}/submit", {"confirm_unanswered": True})
    assert results_elevated(client) is False


def test_the_kept_rows_are_never_changed(client):
    submit_payments(client)
    kept_before = copy.deepcopy(storage.risk_assessments())
    turn_driver_round(client)
    client.get(f"/api/risk/groups/{PAYMENTS}/assessment")
    client.get("/api/risk/matrix")
    client.get("/api/risk/family/payments")
    assert storage.risk_assessments() == kept_before
    assert kept_before[-1]["result"]["risks"][RISK]["elevated"] is True


def test_the_one_line_is_shown_where_results_are_shown_only_when_the_switch_is_on(client):
    submit_payments(client)
    assert client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["rated_with_current_rules"] == THE_LINE
    assert client.get("/api/risk/matrix").json["rated_with_current_rules"] == THE_LINE
    assert client.get("/api/risk/family/payments").json["rated_with_current_rules"] == THE_LINE
    turn_the_switch(client, "no")
    assert client.get("/api/risk/matrix").json["rated_with_current_rules"] is None
    assert "rated_with_current_rules" not in client.get("/api/risk/family/payments").json


def test_a_sign_off_stays_with_its_assessment_and_says_when_it_is_rated_again(client):
    submit_payments(client)
    assessment_id = client.get(f"/api/risk/groups/{PAYMENTS}/assessment").json["assessment"]["id"]
    assert post(client, f"/api/risk/groups/{PAYMENTS}/signoff", {"note": "Looks right."}).status_code == 200
    shown = client.get(f"/api/risk/groups/{PAYMENTS}/signoff").json
    assert shown["history"][0]["rated_again"] is False

    turn_driver_round(client)

    shown = client.get(f"/api/risk/groups/{PAYMENTS}/signoff").json
    assert shown["status"] == "Signed off"                                  # still the same assessment, still signed off
    assert shown["history"][0]["assessment_id"] == assessment_id and shown["history"][0]["rated_again"] is True
    team_group = client.get("/api/risk/family/payments").json["groups"][0]
    assert team_group["signoff"]["rated_again"] is True


def test_fifteen_groups_are_rated_again_in_under_a_second(client):
    """The same kept assessment copied to 15 teams, worked out again for all of them in one go."""
    kept = submit_payments(client)
    row = storage.risk_assessments(PAYMENTS)[-1]
    for number in range(14):
        storage.add_risk_assessment(f"speed-test-{number}", "Rita Tester", row["result"])
    with web.app.test_request_context():
        started = time.perf_counter()
        rows = current_rules.assessments()
        seconds = time.perf_counter() - started
    assert len(rows) == 15 and seconds < 1.0, f"{seconds:.2f} seconds"
    assert kept[RISK]["elevated"] is True
