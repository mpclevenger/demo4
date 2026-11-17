"""The "By L4" split of a team's numbers (owner, 17 Nov 2026): counts only, made-up people."""
from backend.trust import access, evidence, l4_split, linking

ANNA = {"l4": "Anna Lee", "l4_email": "anna@example.com", "l3": "Lena Team", "l3_email": "lena@example.com"}
BEN = {"l4": "Ben Ray", "l4_email": "ben@example.com", "l3": "Lena Team", "l3_email": "lena@example.com"}
LENA = {"l4": "", "l4_email": "", "l3": "Lena Team", "l3_email": "lena@example.com"}


def release(ticket, reverted, who):
    return {"id": ticket, "revert": reverted, "no_revert": not reverted, "who": who}


def team_scored(items_by_metric, team="sage"):
    return {"families": [{"id": team, "name": "Sage", "accountable": "Lena Team"}], "items": {team: items_by_metric}}


def releases():
    return [release("R1", False, [ANNA]), release("R2", True, [ANNA]), release("R3", False, [BEN]),
            release("R4", False, [LENA]), release("R5", True, [])]


def test_items_are_split_between_two_l4s_and_the_rest():
    """Anna has 2 releases (1 without a revert), Ben 1 (1), and 2 are not under an L4 (1)."""
    ev = evidence.page_evidence(team_scored({"TE-02": releases()}))["sage"]["TE-02"]["by_l4"]
    assert ev["split"] is True
    by_name = {row["l4"]: (row["num"], row["den"]) for row in ev["rows"]}
    assert by_name == {"Anna Lee": (1, 2), "Ben Ray": (1, 1)}
    assert ev["rows"][0]["l4_email"] == "anna@example.com"
    assert (ev["not_under"]["num"], ev["not_under"]["den"]) == (1, 2)


def test_not_under_an_l4_is_owned_by_the_team_lead():
    ev = evidence.page_evidence(team_scored({"TE-02": releases()}))["sage"]["TE-02"]["by_l4"]
    assert ev["not_under"]["l4"] == "Not under an L4"
    assert (ev["not_under"]["owner"], ev["not_under"]["owner_email"]) == ("Lena Team", "lena@example.com")


def test_l4_rows_and_not_under_add_up_to_the_teams_count():
    """5 releases, 3 without a revert: the rows plus Not under an L4 give 3 out of 5 again."""
    items = releases()
    ev = evidence.page_evidence(team_scored({"TE-02": items}))["sage"]["TE-02"]["by_l4"]
    assert ev["counted_twice"] is False
    total_num = sum(row["num"] for row in ev["rows"]) + ev["not_under"]["num"]
    total_den = sum(row["den"] for row in ev["rows"]) + ev["not_under"]["den"]
    assert (total_num, total_den) == (sum(i["no_revert"] for i in items), len(items))


def test_the_sum_holds_for_the_hygiene_checks_too():
    """TR-02 counts checks: 4 of 5 for one repo and 2 of 5 for another gives 6 of 10 in all."""
    repos = [{"id": "a", "passed_checks": 4, "of": 5, "who": [ANNA]}, {"id": "b", "passed_checks": 2, "of": 5, "who": []}]
    ev = evidence.page_evidence(team_scored({"TR-02": repos}))["sage"]["TR-02"]["by_l4"]
    assert (ev["rows"][0]["num"], ev["rows"][0]["den"]) == (4, 5)
    assert (ev["not_under"]["num"], ev["not_under"]["den"]) == (2, 5)


def test_an_item_under_two_l4s_counts_once_for_each_and_is_flagged():
    shared = release("R9", False, [ANNA, BEN, ANNA])
    ev = evidence.page_evidence(team_scored({"TE-02": [shared]}))["sage"]["TE-02"]["by_l4"]
    assert ev["counted_twice"] is True
    assert sorted((row["l4"], row["num"], row["den"]) for row in ev["rows"]) == [("Anna Lee", 1, 1), ("Ben Ray", 1, 1)]
    assert ev["not_under"] is None


def test_a_metric_with_a_team_level_part_is_not_split_and_says_why():
    incidents = [{"id": "INC1", "who": [ANNA]}]
    ev = evidence.page_evidence(team_scored({"UN-01": incidents}))["sage"]["UN-01"]["by_l4"]
    assert ev["split"] is False and ev["rows"] == []
    assert "whole team" in ev["reason"]


def test_an_l4_comes_from_the_who_table():
    """The L4 on each person is the one linking.who_table works out (reporting level 4 on the manager chain)."""
    people = [{"sam_account": "cto", "worker": "Cy To", "email": "cy@example.com", "reporting_level": 2, "manager_sam": None},
              {"sam_account": "lena", "worker": "Lena Team", "email": "lena@example.com", "reporting_level": 3, "manager_sam": "cto"},
              {"sam_account": "anna", "worker": "Anna Lee", "email": "anna@example.com", "reporting_level": 4, "manager_sam": "lena"},
              {"sam_account": "dev", "worker": "Dev One", "email": "dev@example.com", "reporting_level": 5, "manager_sam": "anna"}]
    who = linking.who_table(people, l3=3)
    item = {"id": "R1", "no_revert": True, "who": [who["dev"]]}
    ev = evidence.page_evidence(team_scored({"TE-02": [item]}))["sage"]["TE-02"]["by_l4"]
    assert (ev["rows"][0]["l4"], ev["rows"][0]["l4_email"]) == ("Anna Lee", "anna@example.com")


def test_a_team_lead_cannot_see_another_teams_split():
    scored = team_scored({"TE-02": releases()})
    scored["items"]["cards"] = {"TE-02": [release("C1", False, [BEN])]}
    scored["families"].append({"id": "cards", "name": "Cards", "accountable": "Cy Lead"})
    everything = {"may": evidence.page_evidence(scored)}
    lead = {"roles": set(), "lead_of": {"sage"}, "member_of": set(), "open": False}
    seen = access.filter_evidence(everything, lead)["may"]
    assert set(seen) == {"sage"}
    assert "by_l4" in seen["sage"]["TE-02"]


def test_pure_split_with_no_people_puts_everything_under_not_an_l4():
    result = l4_split.split_metric({"unit": "%"}, [{"id": 1}, {"id": 2}], lambda item: (1, 1), "Lena Team", "lena@example.com")
    assert result["rows"] == [] and result["not_under"]["den"] == 2
