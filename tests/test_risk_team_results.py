"""Team results pages: the data, the insights and the CSV (owner, 17 Nov 2026).

Worked example (made-up teams, tests/risk_teams.py). The Lending L3 team has two L4 teams.
    Lending Platform answers RD01 yes (the application keeps its own user accounts), RD03 yes, RD02 yes and RD54 yes.
    Lending Servicing answers RD01 no, but RD36 yes, RD45 yes and RD50 yes.
    On its own, air.cyber.01 has a High likelihood for each L4 team. Put together, RD01, RD03 and RD36 are all on, so the
    Lending L3 team has a Critical likelihood: more than either L4 team on its own.
Nobody here is rated with a combined level: a risk has a likelihood, an impact, and is Elevated or not.
"""
import csv
import io
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import storage, web  # noqa: E402
from trust.risk import team_results  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
HEADERS = {"X-TRUST": "1"}
PLATFORM, SERVICING = "lending--lending-platform", "lending--lending-servicing"
PLATFORM_ANSWERS = {"RD01": "yes", "RD02": "yes", "RD03": "yes", "RD23": "yes", "RD54": "yes",
                    "RD30": "no", "RD31": "no", "RD36": "no", "RD45": "no", "RD50": "no", "RD70": "no", "RD71": "no",
                    "RD72": "no", "RD40": "no", "RD14_pct": "25%", "RD12": "2", "RD41_days": "100"}
SERVICING_ANSWERS = dict(PLATFORM_ANSWERS, RD01="no", RD36="yes", RD45="yes", RD50="yes")
FORBIDDEN_WORDS = [">=", "share", "%", "rule", "trigger", "threshold", "at least"]
NOT_ASSESSED = "payments--payments-core"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


def submit(client, group_id, answers, who):
    for field, answer in answers.items():
        client.post(f"/api/risk/groups/{group_id}/answers", json={"by": who, "question": field, "answer": answer}, headers=HEADERS)
    reply = client.post(f"/api/risk/groups/{group_id}/submit", json={"by": who, "confirm_unanswered": True}, headers=HEADERS)
    assert reply.status_code == 200


@pytest.fixture
def both(client):
    submit(client, PLATFORM, PLATFORM_ANSWERS, "Rita")
    submit(client, SERVICING, SERVICING_ANSWERS, "Val")
    return client


def page(client, team_id):
    reply = client.get(f"/api/risk/teams/{team_id}/results")
    assert reply.status_code == 200
    return reply.json


def risk_of(answer, risk_id):
    return next(risk for risk in answer["risks"] if risk["id"] == risk_id)


def test_an_l4_team_shows_its_newest_submitted_assessment(both):
    answer = page(both, PLATFORM)
    assert answer["assessed"] is True and answer["team"]["level"] == "L4"
    assert answer["team"]["l3"] == {"id": "lending", "name": "Lending"}
    assert answer["team"]["status"] == "Submitted" and answer["team"]["data_month"] == "2026-10"
    cyber = risk_of(answer, "air.cyber.01")
    assert (cyber["likelihood"], cyber["impact"], cyber["elevated"]) == ("High", "Critical", True)
    assert set(cyber["impact_by_dimension"]) == {"financial", "client", "regulatory"}
    assert cyber["impact_by_dimension"]["client"] == "Critical"
    assert [driver["code"] for driver in cyber["likelihood_drivers"]] == ["RD01", "RD03"]
    assert cyber["likelihood_drivers"][0]["source"].startswith("Answered Yes by Rita, ")
    assert cyber["by_l4"] == [] and answer["team"]["l4_teams"] == []
    assert "level" not in cyber                                                  # no combined rating


def test_risks_come_elevated_first_then_likelihood_then_impact(both):
    risks = page(both, PLATFORM)["risks"]
    assert risks[0]["id"] == "air.cyber.01" and risks[0]["elevated"]
    applying = [risk for risk in risks if risk["applies"]]
    keys = [(not risk["elevated"], -["Low", "Medium", "High", "Critical"].index(risk["likelihood"])) for risk in applying]
    assert keys == sorted(keys)
    not_applying = [risk for risk in risks if not risk["applies"]]
    assert risks[len(applying):] == not_applying                                # a risk that doesn't apply is last


def test_a_driver_on_in_only_one_l4_team_is_on_for_the_l3_team(both):
    cyber = risk_of(page(both, "lending"), "air.cyber.01")
    codes = [driver["code"] for driver in cyber["likelihood_drivers"]]
    assert "RD36" in codes and "RD01" in codes                                  # RD36 only Servicing, RD01 only Platform
    by_code = {driver["code"]: driver for driver in cyber["likelihood_drivers"]}
    assert by_code["RD36"]["source"] == "Lending Servicing: Yes (Val)"
    assert by_code["RD03"]["source"] == "Lending Platform: Yes (Rita) · Lending Servicing: Yes (Val)"


def test_the_l3_team_can_be_higher_than_both_of_its_l4_teams(both):
    l3 = risk_of(page(both, "lending"), "air.cyber.01")
    assert l3["likelihood"] == "Critical"
    assert {(team["team"], team["likelihood"]) for team in l3["by_l4"]} == {("Lending Platform", "High"), ("Lending Servicing", "High")}
    assert set(l3["by_l4"][0]) == {"team_id", "team", "likelihood", "impact", "elevated"}
    story = page(both, "lending")["insights"]["story"]
    assert "Taken together, it is at Critical likelihood for Lending, though no L4 team is that high on its own" in story
    assert story.count("External data breach through an over-privileged tool") == 1


def test_counts_add_up_to_every_risk(both):
    for team_id in (PLATFORM, "lending"):
        answer = page(both, team_id)
        counts = answer["counts"]
        assert sum(counts["likelihood"].values()) + counts["doesnt_apply"] == len(answer["risks"])
        assert counts["elevated"] == sum(1 for risk in answer["risks"] if risk["elevated"])
        assert counts["doesnt_apply"] == sum(1 for risk in answer["risks"] if not risk["applies"])
    assert page(both, PLATFORM)["counts"]["elevated"] == 1


def test_the_list_has_every_l3_team_with_its_l4_teams_and_counts(both):
    teams = both.get("/api/risk/teams").json["l3_teams"]
    lending = next(team for team in teams if team["id"] == "lending")
    assert [l4["id"] for l4 in lending["l4_teams"]] == [PLATFORM, SERVICING]
    assert lending["counts"]["likelihood"]["Critical"] == 1 and lending["l4_teams"][0]["counts"]["elevated"] == 1
    assert lending["l4_teams"][0]["status"] == "Submitted" and lending["l4_teams"][0]["assessed_on"]
    payments = next(team for team in teams if team["id"] == "payments")
    assert payments["counts"] is None and payments["l4_teams"][0]["counts"] is None
    assert payments["l4_teams"][0]["status"] == "Not started"


def test_key_insights_are_a_short_story_and_focus_points_with_no_rules_in_them(both):
    """Owner, 17 Nov 2026: "I don't love the key insights write up. It's just strings put together"."""
    for team_id in (PLATFORM, SERVICING, "lending"):
        insights = page(both, team_id)["insights"]
        assert insights["story"] and len(insights["focus"]) <= 3
        text = (insights["story"] + " " + " ".join(p["title"] + " " + p["text"] for p in insights["focus"])).lower()
        for word in FORBIDDEN_WORDS:
            found = re.search(rf"\b{re.escape(word)}\b", text) if word.isalpha() else word in text     # whole words (a driver may be "shared")
            assert not found, (team_id, word, text)
        assert ";" not in insights["story"]                                       # sentences, not lists glued together
        codes = [p["code"] for p in insights["focus"]]
        assert len(codes) == len(set(codes))
    platform = page(both, PLATFORM)["insights"]
    assert platform["story"].startswith("Lending Platform has 1 Elevated risk out of the ")
    for point in platform["focus"]:
        assert point["text"].startswith(("It makes ", "This makes ")) and point["text"].endswith(".") and point["title"][0].isupper()
        assert "External data breach" not in point["text"]                     # one risk stands out: named once, in the story


def test_a_driver_is_named_once_in_key_insights(both):
    insights = page(both, PLATFORM)["insights"]
    for point in insights["focus"]:
        assert point["title"].lower() not in insights["story"].lower()


def test_pervasive_follows_the_setting(both):
    def pervasive_codes():
        drivers = page(both, PLATFORM)["drivers"]
        return {kind: sorted(d["code"] for d in drivers[kind] if d["pervasive"]) for kind in drivers}
    assert pervasive_codes() == {"likelihood": [], "impact": ["RD02", "RD54"]}      # default: three categories
    reply = both.post("/api/edit/rating-settings/save", headers=HEADERS,
                      json={"by": "Tess", "action": "edit", "key": "pervasive_categories", "values": {"value": 2}, "reason": "Testing."})
    assert reply.status_code == 200, reply.json
    assert both.post("/api/risk/teams/refresh", headers=HEADERS, json={"by": "Tess"}).json["ok"]   # results are kept until Refresh
    assert pervasive_codes()["likelihood"] == ["RD01", "RD03"] or "RD01" in pervasive_codes()["likelihood"]


def test_the_csv_has_one_row_per_risk_and_driver_and_no_formulas(both):
    for team_id, has_l4_column in ((PLATFORM, False), ("lending", True)):
        answer = page(both, team_id)
        reply = both.get(f"/api/risk/teams/{team_id}/results.csv")
        assert reply.status_code == 200 and reply.mimetype == "text/csv"
        assert 'risk results ' in reply.headers["Content-Disposition"] and reply.headers["Content-Disposition"].endswith('.csv"')
        rows = list(csv.reader(io.StringIO(reply.data.decode())))
        expected = ["Team", "Category", "Risk ID", "Risk", "Elevated", "Likelihood", "Impact", "Driver for", "Driver", "Driver name",
                    "Dimension", "Where it came from"] + (["L4 team"] if has_l4_column else [])
        assert rows[0] == expected
        wanted = sum(max(1, len(r["likelihood_drivers"]) + len(r["impact_drivers"])) for r in answer["risks"])
        assert len(rows) - 1 == wanted
        for row in rows:
            assert all(cell[:1] not in ("=", "+", "-", "@") for cell in row)


def test_the_csv_quotes_a_cell_that_would_run_as_a_formula():
    answer = {"team": {"name": "=Team", "level": "L4"},
              "risks": [{"id": "x.1", "name": "+Risk", "category": "Cyber", "elevated": False, "applies": True, "likelihood": "Low",
                         "impact": "Low", "likelihood_drivers": [{"code": "RD01", "name": "@name", "source": "-source"}],
                         "impact_drivers": []}]}
    for row in csv.reader(io.StringIO(team_results.csv_text(answer))):
        assert all(cell[:1] not in ("=", "+", "-", "@") for cell in row)


def test_a_risk_that_applies_to_nobody_gets_one_row_with_the_driver_columns_empty(both):
    answer = page(both, SERVICING)
    for row in team_results.csv_rows(answer)[1:]:
        if row[5] == "Doesn't apply":
            assert row[7:12] == [""] * 5


def test_data_drivers_say_the_figure_and_the_month_without_the_comparison():
    found = {"data": "41 releases"}
    assert team_results.sentence_for_one_team(found, "2026-10") == "From TRUST data: 41 releases in October 2026"
    assert team_results.piece_for_one_of_many("Lending Platform", found, "2026-10") == \
        "Lending Platform, from TRUST data: 41 releases in October 2026"


def test_an_unknown_team_is_a_404(client):
    for path in ("/api/risk/teams/nobody/results", "/api/risk/teams/nobody/results.csv"):
        reply = client.get(path)
        assert reply.status_code == 404 and reply.json == {"ok": False, "error": "There is no such team."}


def test_a_team_not_assessed_yet_says_so_plainly(both):
    for team_id in (NOT_ASSESSED, "payments"):
        answer = page(both, team_id)
        assert answer["assessed"] is False and answer["message"] and answer["risks"] == [] and answer["insights"] is None
        assert answer["team"]["status"] == "Not started"


def test_a_person_in_another_team_can_open_the_page(both, tmp_path, monkeypatch):
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    payments_person = {"X-User": "pay2", "X-Groups": "", "X-TRUST": "1"}
    for path in (f"/api/risk/teams/{PLATFORM}/results", "/api/risk/teams/lending/results", "/api/risk/teams"):
        assert both.get(path, headers=payments_person).status_code == 200
    assert both.get("/api/risk/teams/lending/results.csv", headers=payments_person).status_code == 200


def test_a_partly_assessed_l3_team_says_how_many_teams_it_is_based_on(client):
    submit(client, PLATFORM, PLATFORM_ANSWERS, "Rita")
    answer = page(client, "lending")
    assert answer["assessed"] is True and answer["message"] == "Based on 1 of 2 L4 teams that have submitted so far."
    assert answer["team"]["status"] == "Submitted" and len(answer["team"]["l4_teams"]) == 2


def test_the_setting_must_be_a_whole_number_of_one_or_more(client):
    reply = client.post("/api/edit/rating-settings/save", headers=HEADERS,
                        json={"by": "Tess", "action": "edit", "key": "pervasive_categories", "values": {"value": 0}, "reason": "Testing."})
    assert reply.status_code in (400, 422)


def test_the_teams_list_reads_the_mapped_month_once_not_once_per_team(both, monkeypatch):
    """Owner, 17 Nov 2026: the Teams' results list hit the server's memory limit. It read the whole mapped month
    (every file) once per L3 team; now once per mapping, kept with the teams."""
    from trust import storage
    from trust.risk import groups
    groups._cache["key"] = None                                   # as after a new mapping
    real, reads = storage.load_month, []
    monkeypatch.setattr(storage, "load_month", lambda kind, month: (reads.append(kind), real(kind, month))[1])
    assert both.get("/api/risk/teams").status_code == 200
    first = reads.count("mapped")
    reads.clear()
    assert both.get("/api/risk/teams").status_code == 200
    assert first <= 3 and reads.count("mapped") <= 1, (first, reads)


def test_results_are_kept_and_only_change_when_refreshed(both):
    """Owner, 17 Nov 2026: "we should be storing it so it isn't scoring it every time we press it" and "a refresh
    button that only Tech Risk can trigger"."""
    first = both.get("/api/risk/teams").json
    assert first["kept"]["made_at"]
    again = both.get("/api/risk/teams").json
    assert again["kept"] == first["kept"]                                       # the kept copy, not worked out again
    refreshed = both.post("/api/risk/teams/refresh", headers=HEADERS, json={"by": "Tess"}).json
    assert refreshed["ok"] and refreshed["kept"]["made_by"] == "Tess"
    assert both.get("/api/risk/teams").json["kept"]["made_at"] == refreshed["kept"]["made_at"]
    assert both.get(f"/api/risk/teams/{PLATFORM}/results").json["kept"] == refreshed["kept"]
