"""A team's own risk results on its own family page (owner, 16 Nov 2026).

A Risk group IS a TRUST team, so the family page reads the assessment whose group id is the family id directly.
Worked example, made-up people (tests/risk_teams.py): the Lending team is Emery Rook (erook6) with Pat Lee and Sam Ito.
Payments and Cards are other teams, and "print-services" has nobody in it.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import storage, web  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
MONTH = "2026-10"
HEADERS = {"X-TRUST": "1"}
ANSWERS = {"RD01": "yes", "RD02": "yes", "RD03": "yes", "RD23": "yes", "RD54": "yes",
           "RD30": "no", "RD31": "no", "RD36": "no", "RD45": "no", "RD50": "no", "RD70": "no", "RD71": "no",
           "RD72": "no", "RD40": "no", "RD14_pct": "25%", "RD12": "2", "RD41_days": "100"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


def submit_lending(client):
    for field, answer in ANSWERS.items():
        client.post("/api/risk/groups/lending--lending-platform/answers", json={"by": "Rita", "question": field, "answer": answer}, headers=HEADERS)
    assert client.post("/api/risk/groups/lending--lending-platform/submit", json={"by": "Rita", "confirm_unanswered": True}, headers=HEADERS).status_code == 200


def test_a_group_not_assessed_yet_is_one_plain_line(client):
    reply = client.get("/api/risk/family/lending").json
    assert [(g["id"], g["assessed"], g["elevated"]) for g in reply["groups"]] == [("lending--lending-platform", False, []), ("lending--lending-servicing", False, [])]
    assert [g["l3_name"] for g in reply["groups"]] == ["Lending", "Lending"]               # each L4 line names its L3 team
    assert reply["groups"][0]["page"] == "/risk/#/group/lending--lending-platform"


def test_the_elevated_risk_of_the_newest_assessment_is_listed_with_its_page(client):
    submit_lending(client)
    group = client.get("/api/risk/family/lending").json["groups"][0]
    other = client.get("/api/risk/family/lending").json["groups"][1]
    assert other["id"] == "lending--lending-servicing" and not other["assessed"]               # the other L4 team has not assessed
    assert group["assessed"] and group["status"] == "Submitted"
    assert group["page"] == "/risk/#/group/lending--lending-platform/results"
    assert [(r["id"], r["likelihood"], r["impact"]) for r in group["elevated"]] == [("air.cyber.01", "HIGH", "CRITICAL")]
    assert group["elevated"][0]["description"]


def test_another_family_gets_nothing_and_nothing_names_other_families(client):
    submit_lending(client)
    reply = client.get("/api/risk/family/payments").json
    assert [(g["id"], g["assessed"]) for g in reply["groups"]] == [("payments--payments-core", False)]      # its own L4 teams only
    assert "lending" not in json.dumps(reply)
    assert client.get("/api/risk/family/not-a-team").json == {"ok": True, "groups": []}


def test_only_the_familys_own_people_and_the_roles_that_see_every_family(client, tmp_path, monkeypatch):
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    tech_risk = {"X-User": "trisk", "X-Groups": "TRUST-TR", "X-TRUST": "1"}
    stranger = {"X-User": "nobody7", "X-Groups": "", "X-TRUST": "1"}
    assert client.get("/api/risk/family/lending", headers=tech_risk).status_code == 200
    assert client.get("/api/risk/family/lending", headers=stranger).status_code in (401, 403)
