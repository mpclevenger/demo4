"""Elevated risk markers on the CTO view (owner, 16 Nov 2026): an opt-in exception to "risks are never compared between
teams". Tech Risk switches a metric On; then each team whose own newest assessment has an Elevated risk that the metric
watches is marked. Display only.

Worked example, made-up teams (tests/risk_teams.py): Lending submits an assessment whose Elevated risk is air.cyber.01.
Metric SE-01 watches air.cyber.01, metric TE-01 watches air.ops.01 (not Elevated for Lending), RE-01 watches nothing.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, mapping, score_month, storage, store, web  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_RISKS = ROOT / "tools" / "test_risks"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
HEADERS = {"X-TRUST": "1"}
MARKERS = "/api/cto/risk-markers"
SAVE = "/api/edit/cto-risk-markers/save"
ANSWERS = {"RD01": "yes", "RD02": "yes", "RD03": "yes", "RD23": "yes", "RD54": "yes",
           "RD30": "no", "RD31": "no", "RD36": "no", "RD45": "no", "RD50": "no", "RD70": "no", "RD71": "no",
           "RD72": "no", "RD40": "no", "RD14_pct": "25%", "RD12": "2", "RD41_days": "100"}
WATCHES = {"SE-01": ["air.cyber.01"], "TE-01": ["air.ops.01"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A site with made-up teams, the made-up risk files, and a copy of the metrics file in which two metrics watch risks."""
    metrics = json.loads((ROOT / "config" / "metrics.json").read_text(encoding="utf-8"))
    for metric_id, risk_ids in WATCHES.items():
        metrics["metrics"][metric_id]["card"]["risks"] = risk_ids
    (tmp_path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    monkeypatch.setenv("TRUST_METRICS", str(tmp_path / "metrics.json"))
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


def submit_assessment(client, team_id):
    for field, answer in ANSWERS.items():
        client.post(f"/api/risk/groups/{team_id}/answers", json={"by": "Rita", "question": field, "answer": answer}, headers=HEADERS)
    assert client.post(f"/api/risk/groups/{team_id}/submit", json={"by": "Rita", "confirm_unanswered": True}, headers=HEADERS).status_code == 200


def switch(client, metric_id, on, reason="Trying the markers"):
    return client.post(SAVE, json={"by": "Tess", "action": "edit", "key": metric_id, "values": {"show": "yes" if on else "no"},
                                   "reason": reason}, headers=HEADERS)


def test_every_metric_starts_off_and_an_off_metric_sends_nothing(client):
    submit_assessment(client, "lending")
    reply = client.get(MARKERS).json
    assert reply["markers"] == []
    assert reply["can_change"] is True                                   # open site: Tech Risk's view lists every Measured metric
    assert reply["metrics"] and all(chip["on"] is False for chip in reply["metrics"])
    assert "air.cyber" not in json.dumps(reply) and "lending" not in json.dumps(reply)


def test_only_measured_metrics_are_listed(client):
    listed = {chip["id"] for chip in client.get(MARKERS).json["metrics"]}
    measured = {metric_id for metric_id, metric in config.metrics().items() if metric["status"] == "Measured"}
    assert listed == measured and "TR-03" not in listed                  # TR-03 is Wanted


def test_switching_a_metric_on_marks_the_team_with_an_elevated_risk_it_watches(client):
    submit_assessment(client, "lending")
    assert switch(client, "SE-01", True).status_code == 200
    reply = client.get(MARKERS).json
    assert reply["markers"] == [{"family": "lending", "metric": "SE-01",
                                 "risks": [{"id": "air.cyber.01", "name": reply["markers"][0]["risks"][0]["name"]}]}]
    assert reply["markers"][0]["risks"][0]["name"]


def test_a_metric_whose_watched_risk_is_not_elevated_marks_nobody(client):
    submit_assessment(client, "lending")
    switch(client, "TE-01", True)                                        # watches air.ops.01, not Elevated for Lending
    switch(client, "RE-01", True)                                        # watches nothing
    assert client.get(MARKERS).json["markers"] == []


def test_a_team_with_no_assessment_is_not_marked(client):
    submit_assessment(client, "lending")
    switch(client, "SE-01", True)
    families = {marker["family"] for marker in client.get(MARKERS).json["markers"]}
    assert families == {"lending"}                                       # Payments and Cards were never assessed


def test_switching_off_again_sends_nothing(client):
    submit_assessment(client, "lending")
    switch(client, "SE-01", True)
    switch(client, "SE-01", False, "Not needed now")
    assert client.get(MARKERS).json["markers"] == []


def test_a_change_needs_a_reason_and_is_kept_in_the_history(client):
    refused = client.post(SAVE, json={"by": "Tess", "action": "edit", "key": "SE-01", "values": {"show": "yes"}, "reason": " "}, headers=HEADERS)
    assert refused.status_code == 400
    switch(client, "SE-01", True, "The CTO asked to see it")
    history = client.get("/api/edit/cto-risk-markers").json["history"]
    assert [(row["by"], row["reason"]) for row in history] == [("Tess", "The CTO asked to see it")]
    assert history[0]["what"] == [{"label": "Show Elevated risk markers", "before": "No", "after": "Yes"}]


def test_metrics_cannot_be_added_or_retired_here(client):
    added = client.post("/api/edit/cto-risk-markers/save", json={"by": "Tess", "action": "retire", "key": "SE-01", "reason": "x"}, headers=HEADERS)
    assert added.status_code == 400


def test_the_newest_assessment_is_the_one_that_counts(client):
    submit_assessment(client, "lending")
    switch(client, "SE-01", True)
    for field in ANSWERS:                                                # a newer assessment with every answer No: nothing Elevated
        client.post("/api/risk/groups/lending/answers", json={"by": "Rita", "question": field, "answer": "0" if field in ("RD12",) or field.startswith(("RD14", "RD41")) else "no"}, headers=HEADERS)
    client.post("/api/risk/groups/lending/submit", json={"by": "Rita", "confirm_unanswered": True}, headers=HEADERS)
    assert client.get(MARKERS).json["markers"] == []


def access_file(tmp_path, monkeypatch):
    path = tmp_path / "access.json"
    path.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(path))


def test_only_tech_risk_can_switch_and_others_see_only_what_is_on(client, tmp_path, monkeypatch):
    submit_assessment(client, "lending")
    access_file(tmp_path, monkeypatch)
    tech_risk = {"X-User": "trisk", "X-Groups": "TRUST-TR", "X-TRUST": "1"}
    lead = {"X-User": "erook6", "X-Groups": "", "X-TRUST": "1"}
    other_lead = {"X-User": "pay1", "X-Groups": "", "X-TRUST": "1"}
    assert client.post(SAVE, json={"by": "Emery", "action": "edit", "key": "SE-01", "values": {"show": "yes"}, "reason": "Me"}, headers=lead).status_code == 403
    assert client.get(MARKERS, headers=lead).json["metrics"] == []       # all off: nothing to say
    assert client.post(SAVE, json={"by": "Tess", "action": "edit", "key": "SE-01", "values": {"show": "yes"}, "reason": "Trial"}, headers=tech_risk).status_code == 200
    from_lead = client.get(MARKERS, headers=lead).json
    assert from_lead["can_change"] is False
    assert [chip["id"] for chip in from_lead["metrics"]] == ["SE-01"] and "watches" not in from_lead["metrics"][0]
    assert [marker["family"] for marker in from_lead["markers"]] == ["lending"]
    from_other = client.get(MARKERS, headers=other_lead).json            # Payments' lead doesn't see Lending
    assert from_other["markers"] == [] and "lending" not in json.dumps(from_other)
    assert client.get(MARKERS, headers=tech_risk).json["can_change"] is True


def test_no_score_changes_when_markers_are_switched_on(client, tmp_path, monkeypatch):
    """Score a month from the fixtures, switch markers On, score it again: the scored month is the same."""
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    month = "2026-09"
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("cx_sast", "final_checkmarx_sast_report.json"),
                       ("cx_sca", "final_checkmarx_sca_report 1.json"), ("tcc", "tcc_export.csv")):
        store.upload(feed, month, (FIXTURES / name).read_bytes(), name, "Tester")
    mapping.map_month(month)
    before = json.dumps(score_month.run(month), sort_keys=True, default=str)
    submit_assessment(client, "payments")
    assert switch(client, "SE-01", True).status_code == 200
    assert client.get(MARKERS).json["markers"], "the marker is there"
    after = json.dumps(score_month.run(month), sort_keys=True, default=str)
    assert before == after
