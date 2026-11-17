"""The Risk front page puts a person's own teams first (owner, 17 Nov 2026).

A team is "mine" when the person is in that L4 team, or leads the L3 team it sits under. Managers above, Tech Risk
and auditors can open teams but pick one themselves. Made-up teams from tests/risk_teams.py (TEST data only).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))
from test_risk_site import GROUP, as_person, client, signed_in_client, test_files  # noqa: E402,F401


def my_teams(client, who):
    shown = client.get("/api/risk/groups", headers=who).json["groups"]
    return [team["id"] for team in shown if team["mine"]]


def test_a_team_member_has_their_own_team_as_mine(signed_in_client):
    assert my_teams(signed_in_client, as_person("pat1")) == [GROUP]


def test_an_l3_lead_has_every_l4_team_under_them_as_mine(signed_in_client):
    assert my_teams(signed_in_client, as_person("erook6")) == ["lending--lending-platform", "lending--lending-servicing"]


def test_a_manager_above_and_tech_risk_pick_their_own_team(signed_in_client):
    """Sage Crane leads Cards and is the manager above Lending: Lending's teams are listed for her but are not hers."""
    hers = my_teams(signed_in_client, as_person("scrane1"))
    assert hers and all(team.startswith("cards--") for team in hers)
    assert GROUP in [team["id"] for team in signed_in_client.get("/api/risk/groups", headers=as_person("scrane1")).json["groups"]]
    assert my_teams(signed_in_client, as_person("trisk", "TRUST-TR")) == []


def test_open_access_knows_nobody_so_no_team_is_mine(client):
    shown = client.get("/api/risk/groups").json["groups"]
    assert shown and not any(team["mine"] for team in shown)
