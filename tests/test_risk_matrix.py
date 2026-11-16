"""The current risk heat map: GET /api/risk/matrix (read only; nothing is rated again; totals only, never by team).

Worked example, with the made-up risks in tools/test_risks and the made-up TRUST teams in tests/risk_teams.py. Two
teams (the Risk site's groups) answer the same way:
  Lending submits once.
  Payments submits, then changes RD03 to "no" and submits again (the same change as in test_risk_site.py).
That change takes air.cyber.01 from High / Critical to Medium / Critical, which is "better". Nothing else moves.
Newest ratings (likelihood / impact), eight risks each:
  Payments:  Medium/Critical x2 (change.01, cyber.01)  Low/Critical x2 (change.02, ops.01)
             Low/High x3 (cyber.02, data.01, ops.02)    Medium/High x1 (data.02)
  Lending:   the same, except cyber.01 stays High / Critical.
Grid, both groups together (16 risks): Low/High 6, Low/Critical 4, Medium/High 2, Medium/Critical 3, High/Critical 1.
Total: 1 Elevated risk of 16 assessed risks, 2 groups assessed, 1 risk better.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import web  # noqa: E402
from trust.risk import groups, matrix  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
HEADERS = {"X-TRUST": "1"}

ANSWERS = {
    "RD01": "yes", "RD02": "yes", "RD03": "yes", "RD23": "yes", "RD54": "yes",
    "RD30": "no", "RD31": "no", "RD36": "no", "RD45": "no", "RD50": "no", "RD70": "no", "RD71": "no",
    "RD72": "no", "RD40": "no", "RD14_pct": "25%", "RD12": "2", "RD41_days": "100",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


def post(client, path, body):
    return client.post(path, json={"by": "Rita Tester", **body}, headers=HEADERS)


def answer_and_submit(client, group, answers):
    for field, answer in answers.items():
        assert post(client, f"/api/risk/groups/{group}/answers", {"question": field, "answer": answer}).status_code == 200
    assert post(client, f"/api/risk/groups/{group}/submit", {"confirm_unanswered": True}).status_code == 200


@pytest.fixture
def two_groups(client):
    answer_and_submit(client, "lending", ANSWERS)
    answer_and_submit(client, "payments", ANSWERS)
    answer_and_submit(client, "payments", {"RD03": "no"})
    return client


def count_in(answer, likelihood, impact):
    return sum(item["assessments"] for item in answer["cells"][likelihood][impact])


def test_the_grid_counts_risks_in_each_cell(two_groups):
    answer = two_groups.get("/api/risk/matrix").json
    counts = {(likelihood, impact): count_in(answer, likelihood, impact)
              for likelihood in answer["cells"] for impact in answer["cells"][likelihood] if count_in(answer, likelihood, impact)}
    assert counts == {("LOW", "HIGH"): 6, ("LOW", "CRITICAL"): 4, ("MEDIUM", "HIGH"): 2,
                      ("MEDIUM", "CRITICAL"): 3, ("HIGH", "CRITICAL"): 1}
    assert sum(counts.values()) == 16                        # two groups with eight risks each


def test_a_risk_in_a_box_says_how_many_assessments_put_it_there(two_groups):
    answer = two_groups.get("/api/risk/matrix").json
    low_high = {item["risk_id"]: item["assessments"] for item in answer["cells"]["LOW"]["HIGH"]}
    assert sorted(low_high.values()) == [2, 2, 2]            # three risks, each in both assessments
    assert all(item["block"] for row in answer["cells"].values() for box in row.values() for item in box)


def test_the_headline_totals(two_groups):
    answer = two_groups.get("/api/risk/matrix").json
    assert (answer["elevated_likelihood_at_least"], answer["elevated_impact_at_least"]) == ("HIGH", "HIGH")
    assert answer["groups_assessed"] == 2
    assert answer["groups_with_a_previous_assessment"] == 1
    assert [(item["risk_id"], item["elevated_assessments"]) for item in answer["focus"]] == [("air.cyber.01", 1)]
    assert sum(item["elevated_assessments"] for item in answer["focus"]) == 1


def test_movement_is_a_total_per_risk_and_never_per_group(two_groups):
    answer = two_groups.get("/api/risk/matrix").json
    better = sum(item["better"] for item in answer["movement"])
    worse = sum(item["worse"] for item in answer["movement"])
    assert (better, worse) == (1, 0)
    assert [item["risk_id"] for item in answer["movement"] if item["better"]] == ["air.cyber.01"]


def test_the_answer_holds_no_group_id_or_name(two_groups):
    text = two_groups.get("/api/risk/matrix").get_data(as_text=True).lower()
    for group in groups.load():
        assert group["id"].lower() not in text
        assert group["name"].lower() not in text
    assert '"group' not in text.replace("groups_assessed", "").replace("groups_with_a_previous_assessment", "")


def test_everyone_who_can_open_the_site_gets_the_heat_map(two_groups, monkeypatch):
    """Totals only, so no role is refused (owner, 16 Nov 2026)."""
    def a_family_member(_headers=None):
        return {"sam": "x", "name": "X", "roles": set(), "lead_of": {"payments"}, "member_of": set(), "open": False}
    monkeypatch.setattr(web.access, "person", a_family_member)
    assert two_groups.get("/api/risk/matrix").status_code == 200


def test_each_risk_carries_its_description_and_its_controls(two_groups, monkeypatch):
    from trust import storage
    storage.add_risk_controls_copy("2026-11-15T12:00:00Z", [{"code": "MO-02", "title": "Jobs", "url": "https://trac.example/controls/MO-02/",
                                                              "addresses": ["air.cyber.01"]}])
    answer = two_groups.get("/api/risk/matrix").json
    cyber = answer["risk_details"]["air.cyber.01"]
    assert "confidential data" in cyber["description"] and cyber["example"]
    assert [control["code"] for control in cyber["controls"]] == ["MO-02"]
    assert answer["risk_details"]["air.ops.01"]["controls"] == []


def test_a_group_never_assessed_adds_nothing(client):
    answer = client.get("/api/risk/matrix").json
    assert answer["groups_assessed"] == 0 and answer["focus"] == [] and answer["movement"] == []


def test_a_group_that_is_not_a_trust_team_is_left_out(two_groups, monkeypatch):
    """Payments is no longer one of TRUST's teams (its assessments are kept, but not counted)."""
    shown = [group for group in groups.load() if group["id"] != "payments"]
    monkeypatch.setattr(groups, "load", lambda: shown)
    answer = two_groups.get("/api/risk/matrix").json
    assert answer["groups_assessed"] == 1
    assert sum(count_in(answer, likelihood, impact) for likelihood in answer["cells"] for impact in answer["cells"][likelihood]) == 8


def test_a_settings_change_after_submit_does_not_change_what_was_elevated(two_groups, tmp_path, monkeypatch):
    """Elevated is kept as decided at submit, so the heat map agrees with the group's results page."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"medium_share_above": 0.30, "elevated_likelihood_at_least": "CRITICAL",
                                "elevated_impact_at_least": "HIGH"}), encoding="utf-8")
    monkeypatch.setenv("TRUST_RISK_SETTINGS", str(path))
    answer = two_groups.get("/api/risk/matrix").json
    assert [item["risk_id"] for item in answer["focus"]] == ["air.cyber.01"]


def test_nothing_is_rated_again(two_groups):
    """The heat map reads the kept assessments: asking twice changes nothing and adds no assessment."""
    from trust import storage
    before = len(storage.risk_assessments())
    first = two_groups.get("/api/risk/matrix").json
    second = two_groups.get("/api/risk/matrix").json
    assert first == second and len(storage.risk_assessments()) == before == 3


def test_the_page_and_its_script_are_served(client):
    assert b"risk-heatmap.js" in client.get("/risk/").data
    assert b"riskHeatmapDrawPage" in client.get("/risk/risk-heatmap.js").data
