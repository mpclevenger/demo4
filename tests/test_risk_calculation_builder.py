"""Calculations Tech Risk defines on the Risk site (owner, 16 Nov 2026): a team figure and a test, no code.

Every number here is made up. Each example can be followed by hand; the numbers are in the comments.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import score_month, storage, web  # noqa: E402
from trust.risk import data_drivers as dd, team_figures  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

DATA_DRIVER_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks_data_drivers"
HEADERS = {"X-TRUST": "1"}
MONTH = "2026-10"


def cfg_with(fewest_teams):
    cfg = dict(score_month.thresholds_config())
    cfg["min_families_for_threshold"] = fewest_teams
    return cfg


def feed(file, **more):
    return {"status": "mapped", "file": file, "uploaded_at": "2026-11-03T10:00:00", **more}


def who(team, suffix="-p"):
    """The person an item names. In the examples each L4 team "a" has one person, "a-p"."""
    return [{"sam": team + suffix}]


def facts_for_example(ids, headcount, feeds, shared=None):
    teams = [{"id": team_id, "name": team_id.title(), "leads": [], "shared_with": [], "members": [team_id + "-p"]} for team_id in ids]
    return {"month": MONTH, "feeds": feeds, "shared": shared or {}, "teams": teams,
            "group_of_sam": {team_id + "-p": team_id for team_id in ids},
            "team_name": {team["id"]: team["name"] for team in teams}, "headcount": headcount, "people_known": True,
            "repos_loaded": True, "languages_loaded": True, "repos_by_team": {team_id: [] for team_id in ids}}


def release_feeds(released, suffix="-p"):
    """Made-up TCC changes released in the month: {team: count}. Each change names its team's person (team + suffix)."""
    rows = [{"deployed": True, "month": MONTH, "ticket_id": f"{team}-T{n}", "family_id": team, "who": who(team, suffix)}
            for team, count in released.items() for n in range(count)]
    return {"tcc": feed("tcc.csv", rows=rows)}


def incident_feeds(incidents_by_team):
    """Made-up Critical incidents that ended in the month: {team: count}. Every incident has its own id."""
    incidents = {f"INC-{team}-{n}": {"risk_class": "Critical", "families": [team], "who_by_family": {team: who(team)}, "end_datetime": "2026-10-12T15:00:00+00:00"}
                 for team, count in incidents_by_team.items() for n in range(count)}
    return {"postmortems": feed("postmortems.csv", incidents=incidents), "hr": feed("hr.csv", people=[{"sam_account": "x"}])}


# ----------------------------------------------------------------------------- the figures

def test_releases_counts_the_changes_the_team_released_in_the_month():
    facts = facts_for_example(["a", "b"], {"a": 3, "b": 3}, release_feeds({"a": 4}))
    answers = team_figures.releases(facts)
    assert answers["a"]["number"] == 4 and answers["a"]["piece"] == "4 releases in October"
    assert answers["b"]["number"] == 0                                           # the file is loaded: no releases is a real 0
    assert answers["a"]["sources"][0]["feed"] == "tcc"


def test_releases_is_not_known_when_the_tcc_file_is_not_loaded():
    answers = team_figures.releases(facts_for_example(["a"], {"a": 3}, {}))
    assert answers["a"]["number"] is None and "TCC change file isn't loaded" in answers["a"]["why_not"]


def test_incidents_per_100_people_uses_the_postmortem_incidents_and_the_people_placed_with_the_team():
    # a: 3 incidents for 12 people = 25 per 100. b: 0 incidents for 8 people = 0. c: nobody is placed, so not known.
    facts = facts_for_example(["a", "b", "c"], {"a": 12, "b": 8, "c": 0}, incident_feeds({"a": 3}))
    answers = team_figures.incidents_per_100_people(facts)
    assert answers["a"]["number"] == 25 and answers["a"]["piece"] == "3 incidents in October for 12 people (25.0 per 100 people)"
    assert answers["b"]["number"] == 0
    assert answers["c"]["number"] is None and answers["c"]["why_not"] == "no people are placed with this team"


def test_incidents_per_100_people_is_not_known_without_the_postmortems_file_or_hr():
    assert team_figures.incidents_per_100_people(facts_for_example(["a"], {"a": 5}, {}))["a"]["number"] is None
    feeds = incident_feeds({"a": 1})
    facts = facts_for_example(["a"], {"a": 5}, feeds)
    facts["people_known"] = False
    answer = team_figures.incidents_per_100_people(facts)["a"]
    assert answer["number"] is None and answer["why_not"] == "HR isn't loaded"


# ----------------------------------------------------------------------------- the tests

def test_each_test_on_a_number_and_a_median_of_2_5():
    f = team_figures
    assert f.above_median(4, 2.5, None) and not f.above_median(2.5, 2.5, None)
    assert f.below_median(2, 2.5, None) and not f.below_median(2.5, 2.5, None)
    assert f.below_share_of_median(1.7, 2.5, 0.70) and not f.below_share_of_median(1.75, 2.5, 0.70)   # 70% of 2.5 = 1.75
    assert f.above_number(5, None, 4) and not f.above_number(4, None, 4)
    assert f.below_number(3, None, 4) and not f.below_number(4, None, 4)


def test_a_test_that_needs_a_number_or_share_says_so_in_plain_words():
    with pytest.raises(ValueError, match="Give the number"):
        team_figures.check_setting("above_number", None)
    with pytest.raises(ValueError, match="part of one"):
        team_figures.check_setting("below_share_of_median", 70)
    with pytest.raises(ValueError, match="uses no number"):
        team_figures.check_setting("above_median", 3)
    team_figures.check_setting("below_share_of_median", 0.70)
    team_figures.check_setting("above_median", None)


# ----------------------------------------------------------------------------- a defined driver

def defined(figure, test, number_or_share=None):
    return {"figure": figure, "test": test, "number_or_share": number_or_share}


def test_a_defined_driver_says_on_or_off_with_the_sentence_the_owner_asked_for():
    # Eight teams released 1, 2, 2, 3, 3, 4, 4, 5 changes... the median of 8 teams is 3. Team h released 4: above it.
    released = dict(a=1, b=2, c=2, d=3, e=3, f=4, g=4, h=5)
    facts = facts_for_example(list(released), {team: 5 for team in released}, release_feeds(released))
    answers = dd.defined_calculation(facts, defined("releases", "above_median"), "RD22", cfg_with(5))
    assert answers["h"]["on"] is True and answers["a"]["on"] is False and answers["d"]["on"] is False
    assert answers["h"]["sentence"] == "5 releases in October; the prevailing median is 3 across 8 teams, so this is ON."
    assert answers["a"]["sentence"].endswith("so this is OFF.")
    assert answers["h"]["value_text"] == "5 releases" and answers["h"]["sources"][0]["feed"] == "tcc"


def test_a_defined_driver_with_a_fixed_number_needs_no_median():
    facts = facts_for_example(["a", "b"], {"a": 5, "b": 5}, release_feeds({"a": 6, "b": 1}))
    answers = dd.defined_calculation(facts, defined("releases", "above_number", 4), "RD22", cfg_with(5))
    assert (answers["a"]["on"], answers["b"]["on"]) == (True, False)             # only 2 teams, but no median is needed
    assert "the number to compare with is 4" in answers["a"]["sentence"]


def test_a_defined_driver_is_not_known_with_too_few_teams_or_no_data():
    facts = facts_for_example(["a", "b"], {"a": 5, "b": 5}, release_feeds({"a": 6}))
    assert dd.defined_calculation(facts, defined("releases", "above_median"), "RD22", cfg_with(5))["a"]["on"] is None
    nothing = facts_for_example(["a"], {"a": 5}, {})
    answer = dd.defined_calculation(nothing, defined("releases", "above_median"), "RD22", cfg_with(1))["a"]
    assert answer["on"] is None and answer["sentence"].startswith("Not known:")


def test_a_share_of_the_median_test_names_the_share_in_the_sentence():
    # Incidents per 100 people: a 0, b 10, c 20, d 30, e 40. The median is 20; 70% of it is 14.
    incidents = dict(a=0, b=1, c=2, d=3, e=4)
    facts = facts_for_example(list(incidents), {team: 10 for team in incidents}, incident_feeds(incidents))
    answers = dd.defined_calculation(facts, defined("incidents_per_100_people", "below_share_of_median", 0.70), "RD63", cfg_with(5))
    assert [team for team in incidents if answers[team]["on"]] == ["a", "b"]
    assert "70% of the prevailing median is 14" in answers["a"]["sentence"]


def test_the_places_name_the_figure_and_the_test():
    places = dd.defined_places("RD22", {"RD22": defined("releases", "above_median")})
    assert [place["function"] for place in places] == ["releases", "above_median"]
    assert all(place["from"] <= place["to"] for place in places)
    assert dd.defined_places("RD99", {}) is None


def finding_feeds():
    """Made-up Checkmarx files: one repo that fails the policy. They carry no first-found date, as the real ones don't."""
    rows = [{"key": "repo-a", "compliant": False, "open": 5, "overdue": 2, "overdue_by_severity": {"CRITICAL": 2}}]
    return {"cx_sast": feed("cx_sast.json", rows=rows), "cx_sca": feed("cx_sca.json", rows=rows)}


def action_feeds(overdue_by_team):
    """Made-up postmortem actions, open at the end of October. Each team has its overdue ones, due 1 Oct, and one not due until 1 Dec."""
    rows = []
    for team, count in overdue_by_team.items():
        rows += [{"item_ref": f"{team}-late-{n}", "open": True, "created": "2026-09-01T00:00:00+00:00",
                  "due": "2026-10-01T00:00:00+00:00", "family_id": team, "incident_rated": True, "who": who(team)} for n in range(count)]
        rows.append({"item_ref": f"{team}-later", "open": True, "created": "2026-09-01T00:00:00+00:00",
                     "due": "2026-12-01T00:00:00+00:00", "family_id": team, "incident_rated": True, "who": who(team)})
    return {"actions": feed("actions.csv", rows=rows)}


def test_aged_findings_are_not_known_because_the_files_carry_no_first_found_date():
    facts = facts_for_example(["a", "b"], {"a": 3, "b": 3}, finding_feeds())
    answers = team_figures.aged_critical_high_findings(facts)
    assert answers["a"]["number"] is None and answers["a"]["piece"] is None
    assert "don't say when each finding was first found" in answers["a"]["why_not"]
    assert "older than 30 days" in answers["a"]["why_not"]                      # the 30 comes from finding_age_days in the file
    assert [one["feed"] for one in answers["a"]["sources"]] == ["cx_sast", "cx_sca"]


def test_aged_findings_say_so_when_no_checkmarx_file_is_loaded():
    answers = team_figures.aged_critical_high_findings(facts_for_example(["a"], {"a": 3}, {}))
    assert answers["a"]["number"] is None and "aren't loaded" in answers["a"]["why_not"]


def test_the_finding_age_is_a_setting_in_the_file():
    assert dd.settings_file()["finding_age_days"] == 30


def test_overdue_postmortem_actions_counts_the_actions_past_due_at_month_end():
    # a: 2 overdue and 1 not yet due; b: 0 overdue and 1 not yet due. UN-02 counts the 2 and the 0.
    facts = facts_for_example(["a", "b"], {"a": 3, "b": 3}, action_feeds({"a": 2, "b": 0}))
    answers = team_figures.overdue_postmortem_actions(facts)
    assert answers["a"]["number"] == 2 and answers["a"]["piece"] == "2 postmortem actions past due at the end of October"
    assert answers["b"]["number"] == 0 and answers["b"]["value_text"] == "0 overdue actions"
    assert answers["a"]["sources"][0]["feed"] == "actions"


def test_overdue_postmortem_actions_is_not_known_without_the_action_items_file():
    answers = team_figures.overdue_postmortem_actions(facts_for_example(["a"], {"a": 3}, {}))
    assert answers["a"]["number"] is None and "isn't loaded" in answers["a"]["why_not"]


def test_a_defined_driver_on_overdue_actions_is_on_above_zero_and_findings_are_not_known():
    facts = facts_for_example(["a", "b"], {"a": 3, "b": 3}, {**action_feeds({"a": 2, "b": 0}), **finding_feeds()})
    overdue = dd.defined_calculation(facts, defined("overdue_postmortem_actions", "above_number", 0), "RD64", cfg_with(2))
    assert overdue["a"]["on"] is True and overdue["b"]["on"] is False
    findings = dd.defined_calculation(facts, defined("aged_critical_high_findings", "above_number", 0), "RD44", cfg_with(2))
    assert findings["a"]["on"] is None and "first found" in findings["a"]["sentence"]


def test_the_two_new_figures_have_their_places():
    for code, figure in (("RD44", "aged_critical_high_findings"), ("RD64", "overdue_postmortem_actions")):
        places = dd.defined_places(code, {code: defined(figure, "above_number", 0)})
        assert [place["function"] for place in places] == [figure, "above_number"]


def test_a_driver_a_calculation_answers_is_left_off_the_drivers_answered_from_data_list(client):
    def listed():
        return [entry["key"] for entry in client.get("/api/edit/data-drivers").json["entries"]]
    assert not {"RD22", "RD44", "RD63", "RD64"} & set(listed())                  # all four are defined, so none is "not calculated"
    assert edit(client, "retire", "RD64", None, reason="Not wanted.").status_code == 200
    assert "RD64" in listed()                                                    # retired: back on the list


def test_the_starting_entries_are_in_the_file():
    starting = dd.settings_file()["defined_calculations"]
    assert starting["RD22"] == defined("releases", "above_median")
    assert starting["RD63"] == defined("incidents_per_100_people", "above_median")
    assert starting["RD44"] == defined("aged_critical_high_findings", "above_number", 0)
    assert starting["RD64"] == defined("overdue_postmortem_actions", "above_number", 0)


# ----------------------------------------------------------------------------- through the Risk site

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("TRUST_RISKS", str(DATA_DRIVER_RISKS))
    put_made_up_teams()
    mapped = storage.load_month("mapped", MONTH)
    # Six L4 teams: Lending Platform released 6, Payments Core 2, Cards Ops 1, and Lending Servicing, Cards Risk and
    # Treasury Ops 0. The median of 6, 2, 1, 0, 0, 0 is 0.5.
    mapped["feeds"]["tcc"] = release_feeds(dict(lford4=6, pay2=2, card1=1), suffix="")["tcc"]
    storage.save_month("mapped", MONTH, mapped)
    return web.app.test_client()


def edit(client, action, key, values, reason="Because Tech Risk asked."):
    return client.post("/api/edit/calculations/save", headers=HEADERS,
                       json={"action": action, "key": key, "values": values, "reason": reason, "by": "Tester"})


def form_driver(client, team, code):
    return next(driver for driver in client.get(f"/api/risk/groups/{team}").json["answered_from_data"] if driver["code"] == code)


def test_a_defined_driver_shows_on_the_form_with_sentence_source_and_place(client):
    shown = form_driver(client, "lending--lending-platform", "RD22")
    assert shown["state"] is True
    assert shown["sentence"] == "6 releases in October; the prevailing median is 0.5 across 6 teams, so this is ON."
    assert shown["sources"][0]["feed"] == "tcc"
    assert [place["function"] for place in shown["place"]] == ["releases", "above_median"]
    assert form_driver(client, "treasury--treasury-ops", "RD22")["state"] is False
    assert form_driver(client, "lending--lending-platform", "RD63")["state"] is None               # the postmortems file isn't loaded: not known


def test_the_list_starts_with_the_files_entries_and_keeps_history(client):
    entries = {entry["key"]: entry for entry in client.get("/api/edit/calculations").json["entries"]}
    assert entries["RD22"]["values"]["figure"] == "releases" and entries["RD63"]["values"]["test"] == "above_median"
    values = dict(entries["RD22"]["values"], test="above_number", number_or_share=3)
    assert edit(client, "edit", "RD22", values, reason="A fixed bar of 3 releases.").status_code == 200
    assert form_driver(client, "lending--lending-platform", "RD22")["sentence"].endswith("the number to compare with is 3, so this is ON.")   # the cache saw the change
    assert form_driver(client, "payments--payments-core", "RD22")["state"] is False             # 2 releases is not above 3
    history = client.get("/api/edit/calculations").json["history"]
    assert history[0]["reason"] == "A fixed bar of 3 releases."
    assert edit(client, "retire", "RD22", None, reason="Not wanted.").status_code == 200
    assert form_driver(client, "lending--lending-platform", "RD22")["state"] is None               # retired: no calculation answers it again
    assert client.get("/api/edit/calculations/download?format=csv").status_code == 200


def test_the_list_refuses_in_plain_words(client):
    ok = {"driver": "RD44", "figure": "releases", "test": "above_number", "number_or_share": 2}
    reply = edit(client, "add", "", dict(ok, driver="RD99"))
    assert reply.status_code == 400 and "choose one of the choices" in reply.json["error"]                  # not a driver at all
    reply = edit(client, "edit", "RD44", dict(ok, number_or_share=None))
    assert reply.status_code == 400 and "Give the number" in reply.json["error"]
    reply = edit(client, "edit", "RD44", dict(ok, test="below_share_of_median", number_or_share=70))
    assert reply.status_code == 400 and "part of one" in reply.json["error"]
    reply = edit(client, "add", "", dict(ok, driver="RD22"))
    assert reply.status_code == 400 and "already has a calculation" in reply.json["error"]
    reply = edit(client, "add", "", dict(ok, driver="RD15"))
    assert reply.status_code == 400 and "RD15" in reply.json["error"]
    assert edit(client, "edit", "RD44", ok, reason="").status_code == 400            # a reason is needed
    assert edit(client, "edit", "RD44", ok).status_code == 200
    assert edit(client, "retire", "RD44", None).status_code == 200
    assert edit(client, "add", "", ok).status_code == 400                           # retired: restore it from the list instead


def test_a_driver_with_a_built_in_calculation_or_a_question_cannot_be_defined(client):
    from trust import editable
    from trust.risk import registers
    from_files = registers.load_registers()["from_files"]
    rules = {**from_files["driver_rules"], "RD21": {**from_files["driver_rules"]["RD22"]},
             "RD90": {**from_files["driver_rules"]["RD22"], "questionnaire_fields": ["RD90"]}}
    files = dict(from_files, driver_rules=rules)
    ok = {"driver": "RD21", "figure": "releases", "test": "above_median", "number_or_share": None}
    with pytest.raises(ValueError, match="built-in calculation"):
        editable._check_defined_calculation("add", "RD21", ok, [], files)
    with pytest.raises(ValueError, match="question on the form"):
        editable._check_defined_calculation("add", "RD90", dict(ok, driver="RD90"), [], files)
