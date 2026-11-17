"""The data behind the "All metrics" page (owner, 17 Nov 2026): every team's L4 counts at once, open to every role."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import access, evidence, publish, storage  # noqa: E402

from test_l4_split import ANNA, BEN, release, releases, team_scored  # noqa: E402
from test_score_and_publish import load, tmp_store  # noqa: E402,F401  (the store fixture)


def two_team_scored():
    scored = team_scored({"TE-02": releases()})
    scored["items"]["cards"] = {"TE-02": [release("C1", False, [BEN])]}
    scored["families"].append({"id": "cards", "name": "Cards", "accountable": "Cy Lead"})
    return scored


def test_every_teams_by_l4_is_the_same_as_the_team_pages():
    """The page's data and each team's evidence come from one calculation."""
    scored = two_team_scored()
    all_teams = evidence.by_l4_of_month(scored)
    team_pages = evidence.page_evidence(scored)
    assert set(all_teams) == {"sage", "cards"}
    for team_id in all_teams:
        for metric_id in all_teams[team_id]:
            assert all_teams[team_id][metric_id] == team_pages[team_id][metric_id]["by_l4"]


def test_the_block_holds_each_teams_result_and_counts():
    """Sage has 5 releases: Anna 1 of 2 without a revert, Ben 1 of 1, and 1 of 2 under no L4."""
    scored = two_team_scored()
    period = {"families": {"sage": {"metrics": {"TE-02": {"value": 60.0, "status": "Red", "numerator": 3, "denominator": 5,
                                                          "reason": "kept private", "history": ["Red"]}}},
                           "cards": {"metrics": {}}}}
    block = publish.all_metrics_block(scored, period, "2026-10")
    sage = block["teams"]["sage"]["TE-02"]
    assert sage["result"] == {"value": 60.0, "status": "Red", "numerator": 3, "denominator": 5}
    assert {row["l4"]: (row["num"], row["den"]) for row in sage["by_l4"]["rows"]} == {"Anna Lee": (1, 2), "Ben Ray": (1, 1)}
    assert (sage["by_l4"]["not_under"]["num"], sage["by_l4"]["not_under"]["den"]) == (1, 2)
    assert block["teams"]["cards"] == {}
    assert set(block) == {"teams", "l4_team_names"}


def test_published_data_has_the_block_equal_to_the_team_pages(tmp_store):
    load("2026-09")
    data = publish.build()
    block = data["all_metrics"]["2026-09"]["teams"]
    team_pages = evidence.page_evidence(storage.load_month("scored", "2026-09"))
    assert block and set(block) == set(data["periods"]["2026-09"]["families"])
    seen_a_split = False
    for team_id, metrics in team_pages.items():
        if team_id not in block:           # items no team owns have no team page, so no row
            continue
        for metric_id, entry in metrics.items():
            assert block[team_id][metric_id]["by_l4"] == entry["by_l4"]
            seen_a_split = True
    assert seen_a_split


def test_a_team_lead_gets_the_whole_block(tmp_store):
    """Everyone sees everything on this page: filtering the data for a team lead leaves the block as it is, and
    still hides other teams' numbers elsewhere in the data."""
    load("2026-09")
    data = json.loads(json.dumps(publish.build()))
    lead = {"roles": set(), "lead_of": {"payments"}, "member_of": set(), "open": False}
    seen = access.filter_data(data, lead)
    assert seen["all_metrics"] == data["all_metrics"]
    other = seen["periods"]["2026-09"]["families"]["cards"]["metrics"]
    assert all("value" not in result for result in other.values())
