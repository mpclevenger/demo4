"""Elevated risk markers on the CTO view (owner, 16 Nov 2026): an exception to "risks are never compared between
teams". No switches: each team whose own newest assessment has an Elevated risk that a metric watches is marked.
Display only.

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


def test_a_team_with_an_elevated_watched_risk_is_marked_with_no_switching(client):
    submit_assessment(client, "lending")
    reply = client.get(MARKERS).json
    assert set(reply) == {"ok", "markers"}                               # no switches, no can_change, no metric list
    assert len(reply["markers"]) == 1
    marker = reply["markers"][0]
    assert (marker["family"], marker["metric"]) == ("lending", "SE-01")
    assert marker["risks"][0]["id"] == "air.cyber.01" and marker["risks"][0]["name"]
    assert marker["metric_name"]


def test_nothing_is_sent_before_any_assessment(client):
    assert client.get(MARKERS).json["markers"] == []


def test_a_metric_whose_watched_risk_is_not_elevated_or_that_watches_nothing_gives_none(client):
    submit_assessment(client, "lending")
    metrics_marked = {marker["metric"] for marker in client.get(MARKERS).json["markers"]}
    assert "TE-01" not in metrics_marked                                 # watches air.ops.01, not Elevated for Lending
    assert "RE-01" not in metrics_marked                                 # watches nothing


def test_a_team_with_no_assessment_is_not_marked(client):
    submit_assessment(client, "lending")
    families = {marker["family"] for marker in client.get(MARKERS).json["markers"]}
    assert families == {"lending"}                                       # Payments and Cards were never assessed


def test_the_switch_list_is_gone_and_says_so(client):
    assert client.get("/api/edit/cto-risk-markers").status_code == 400
    assert client.post("/api/edit/cto-risk-markers/save", json={"by": "Tess", "action": "edit", "key": "SE-01", "values": {"show": "yes"},
                                                                 "reason": "x"}, headers=HEADERS).status_code == 400


def test_the_newest_assessment_is_the_one_that_counts(client):
    submit_assessment(client, "lending")
    for field in ANSWERS:                                                # a newer assessment with every answer No: nothing Elevated
        client.post("/api/risk/groups/lending/answers", json={"by": "Rita", "question": field, "answer": "0" if field in ("RD12",) or field.startswith(("RD14", "RD41")) else "no"}, headers=HEADERS)
    client.post("/api/risk/groups/lending/submit", json={"by": "Rita", "confirm_unanswered": True}, headers=HEADERS)
    assert client.get(MARKERS).json["markers"] == []


def access_file(tmp_path, monkeypatch):
    path = tmp_path / "access.json"
    path.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(path))


def test_a_family_lead_sees_only_their_own_family(client, tmp_path, monkeypatch):
    submit_assessment(client, "lending")
    access_file(tmp_path, monkeypatch)
    tech_risk = {"X-User": "trisk", "X-Groups": "TRUST-TR", "X-TRUST": "1"}
    lead = {"X-User": "erook6", "X-Groups": "", "X-TRUST": "1"}
    other_lead = {"X-User": "pay1", "X-Groups": "", "X-TRUST": "1"}
    assert [marker["family"] for marker in client.get(MARKERS, headers=lead).json["markers"]] == ["lending"]
    from_other = client.get(MARKERS, headers=other_lead).json            # Payments' lead doesn't see Lending
    assert from_other["markers"] == [] and "lending" not in json.dumps(from_other)
    assert [marker["family"] for marker in client.get(MARKERS, headers=tech_risk).json["markers"]] == ["lending"]


def test_no_score_changes_when_markers_appear(client, tmp_path, monkeypatch):
    """Score a month from the fixtures, an assessment makes a marker appear, score it again: the scored month is the same."""
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    month = "2026-09"
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("cx_sast", "final_checkmarx_sast_report.json"),
                       ("cx_sca", "final_checkmarx_sca_report 1.json"), ("tcc", "tcc_export.csv")):
        store.upload(feed, month, (FIXTURES / name).read_bytes(), name, "Tester")
    mapping.map_month(month)
    before = json.dumps(score_month.run(month), sort_keys=True, default=str)
    submit_assessment(client, "payments")
    assert client.get(MARKERS).json["markers"], "the marker is there"
    after = json.dumps(score_month.run(month), sort_keys=True, default=str)
    assert before == after
