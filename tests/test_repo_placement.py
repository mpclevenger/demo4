"""Which team a repo belongs to (owner, 17 Nov 2026): the app inventory first, then the GitHub committer.

The rows here are made up for the tests (synthetic data stays in tests)."""
import csv
import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, store  # noqa: E402
from trust.intake import repos  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
PEOPLE = [{"sam_account": "amoreno", "email": "alex.moreno@example.com"}]
TEAM_OF_PERSON = {"amoreno": "payments"}          # the committer is in Payments


def repo_rows(*names_and_apps):
    """Repo rows as the reader gives them (committer Alex Moreno, active), each with the apps linked to it:
    ("name", [("App label", "team or None"), ...])."""
    header = ",".join(repos.FIELDS)
    lines = [header]
    for name, _apps in names_and_apps:
        row = {"Repo": name, "Archived": "False", "Fork": "False", "PushedAt": "2026-10-20T10:00:00Z",
               "TopCommitterEmail": "alex.moreno@example.com", "TopCommitterLogin": "amoreno"}
        out = io.StringIO()
        csv.writer(out).writerow([row.get(field, "") for field in repos.FIELDS])
        lines.append(out.getvalue().strip())
    rows = repos.read(("\n".join(lines) + "\n").encode())["rows"]
    for row, (_name, apps) in zip(rows, names_and_apps):
        row["app_placements"] = [{"app": label, "family_id": team} for label, team in apps]
    return {row["repo"]: row for row in rows}


def place(rows, settings=None):
    out = repos.place_and_score(list(rows.values()), "2026-10", PEOPLE, TEAM_OF_PERSON, settings or {})
    return out, rows


def test_inventory_placed_repo_wins_over_a_committer_on_another_team():
    out, rows = place(repo_rows(("pay-api", [("Ledger (A2)", "cards")])))
    repo = rows["pay-api"]
    assert repo["family_id"] == "cards" and repo["family_how"] == "app inventory"
    assert repo["placed_by"] == "app inventory (Ledger (A2))"
    assert repo["owner_email"] == "alex.moreno@example.com"          # still kept and shown
    assert out["families"]["cards"]["repos"] == 1 and "payments" not in out["families"]


def test_repo_not_in_the_inventory_uses_the_committer():
    out, rows = place(repo_rows(("loner", [])))
    assert rows["loner"]["family_id"] == "payments" and rows["loner"]["family_how"] == "committer"
    assert rows["loner"]["placed_by"] == "committer"


def test_an_app_with_no_team_is_ignored_and_the_committer_is_used():
    """An inactive app, or one placed with no team, has family_id None in the placements."""
    out, rows = place(repo_rows(("old-app-repo", [("Old Thing (A3)", None)])))
    assert rows["old-app-repo"]["family_id"] == "payments" and rows["old-app-repo"]["family_how"] == "committer"


def test_apps_on_several_teams_the_team_with_most_apps_wins():
    out, rows = place(repo_rows(("shared", [("One (A1)", "cards"), ("Two (A2)", "cards"), ("Three (A3)", "lending")])))
    assert rows["shared"]["family_id"] == "cards" and rows["shared"]["family_how"] == "app inventory"


def test_a_tie_falls_back_to_the_committer_with_a_note():
    out, rows = place(repo_rows(("tied", [("One (A1)", "cards"), ("Two (A2)", "lending")])))
    assert rows["tied"]["family_id"] == "payments" and rows["tied"]["family_how"] == "committer"
    assert any("tied" in n and "committer rule was used" in n for n in out["notes"])


def test_for_information_note_counts_each_way():
    out, rows = place(repo_rows(("a", [("One (A1)", "cards")]), ("b", []), ("c", [])))
    rows["c"]["top_committer"] = {"email": "nobody@example.com", "login": None, "share": None}
    out = repos.place_and_score(list(rows.values()), "2026-10", PEOPLE, TEAM_OF_PERSON, {})
    assert "For information: 1 of 3 active repos placed by the app inventory; 1 by committer; 1 not placed" in out["notes"]
    assert (out["placed_by_inventory"], out["placed_by_committer"], out["not_placed"]) == (1, 1, 1)


INVENTORY = (b"app_id,app_name,app_status,app_department,app_sbu,app_org_hierarchy,app_owner_raw,app_owner_type,"
             b"app_owner_email,bcp_tier,bcp_tier_source,itdr_match,service_id,service_name,service_owner_email,"
             b"service_repo,unmapped_reasons\n"
             b"A1,Ledger,Confirmed,Cards,SBU1,Tech > Cards,x,Person,pat.kim@example.com,1,src,,S1,api,,org/ledger,\n")


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    settings = tmp_path / "settings.json"
    settings.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(settings))
    return tmp_path


def test_mapping_places_the_inventory_first_so_repos_can_use_it(tmp_store):
    """org/ledger is committed by Alex Moreno (Payments) but is the service repo of an app in Cards."""
    header = ",".join(repos.FIELDS)
    lines = [header]
    for name in ("org/ledger", "org/other"):
        row = {"Repo": name, "Archived": "False", "Fork": "False", "PushedAt": "2026-10-20T10:00:00Z",
               "TopCommitterEmail": "alex.moreno@example.com", "TopCommitterLogin": "amoreno"}
        out = io.StringIO()
        csv.writer(out).writerow([row.get(field, "") for field in repos.FIELDS])
        lines.append(out.getvalue().strip())
    for feed, data, name in (("hr", (FIX / "hr_firmwide.csv").read_bytes(), "hr.csv"),
                             ("app_inventory", INVENTORY, "inventory.csv"),
                             ("repos", ("\n".join(lines) + "\n").encode(), "repos.csv")):
        store.upload(feed, "2026-10", data, name, "Tester")
    mapped = mapping.map_month("2026-10")
    by_name = {r["repo"]: r for r in mapped["feeds"]["repos"]["rows"]}
    app_team = mapped["feeds"]["app_inventory"]["rows"][0]["family_id"]
    assert app_team and by_name["org/ledger"]["family_how"] == "app inventory"
    assert by_name["org/ledger"]["family_id"] == app_team
    assert by_name["org/other"]["family_how"] == "committer" and by_name["org/other"]["family_id"] != app_team
    assert any("1 of 2 active repos placed by the app inventory; 1 by committer" in n
               for n in mapped["feeds"]["repos"]["notes"])
