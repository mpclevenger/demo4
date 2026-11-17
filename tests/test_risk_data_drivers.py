"""Risk drivers answered from TRUST's data (owner, 16 Nov 2026): one worked example for each of the five drivers.

Every number here is made up. Each example can be followed by hand; the numbers are in the comments.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import score_month, storage, web  # noqa: E402
from trust.intake import repo_contributors, repos  # noqa: E402
from trust.risk import data_drivers as dd  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

DATA_DRIVER_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks_data_drivers"
HEADERS = {"X-TRUST": "1"}
MONTH = "2026-10"


def cfg_with(fewest_teams):
    """TRUST's own threshold settings, with the fewest teams a prevailing median needs set for the example."""
    cfg = dict(score_month.thresholds_config())
    cfg["min_families_for_threshold"] = fewest_teams
    return cfg


def start(code):
    """The starting values from the file, as the editing page would hold them."""
    return {"calculation": dd.calculation_of(code), **dd.default_values(code)}


def team_list(*ids):
    """Made-up L4 teams. Each has one person, "<id>-p" (email "<id>-p@example.test"), who is placed on the items."""
    return [{"id": team_id, "name": team_id.title(), "leads": [], "shared_with": [], "members": [team_id + "-p"]} for team_id in ids]


def repo(name, languages):
    return {"repo": name, "active": True, "languages": languages}


def facts_for_example(ids, headcount=None, repos_by_team=None, feeds=None, shared=None):
    teams = team_list(*ids)
    return {"month": MONTH, "feeds": feeds or {}, "shared": shared or {}, "teams": teams,
            "group_of_sam": {team_id + "-p": team_id for team_id in ids},
            "group_of_email": {team_id + "-p@example.test": team_id for team_id in ids},
            "team_name": {team["id"]: team["name"] for team in teams},
            "headcount": headcount or {team_id: 0 for team_id in ids}, "people_known": True,
            "repos_loaded": True, "languages_loaded": True,
            "repos_by_team": repos_by_team or {team_id: [] for team_id in ids}}


def mapped_feed(file, what_rows=None, **more):
    return {"status": "mapped", "file": file, "uploaded_at": "2026-11-03T10:00:00", **({"rows": what_rows} if what_rows is not None else {}), **more}


# ----------------------------------------------------------------------------- the settings file

def test_each_calculation_is_pointed_at_a_driver_code_in_the_settings_file():
    assert {dd.calculation_of(code) for code in ("RD21", "RD15", "RD53", "RD11", "RD25")} == set(dd.CALCULATION_FUNCTIONS)
    assert dd.calculation_of("RD99") is None                                    # a code nobody points at: not calculated


def test_the_starting_values_are_in_the_file():
    assert dd.words_in(start("RD21")["languages"]) == ["Perl", "C", "C++", "PHP"]
    assert start("RD53")["share_of_median"] == 70                               # 70% of the prevailing median
    assert start("RD25")["fixed_number"] == 2                                   # more than 2 other teams
    assert "HTML" in start("RD11")["left_out_languages"]


# ----------------------------------------------------------------------------- the repos file's new Languages column

def test_the_languages_column_is_read():
    assert repos.languages_in("Perl:1200; C:340; Python:98000") == {"Perl": 1200, "C": 340, "Python": 98000}
    assert repos.languages_in("C++:12; C#:1,200") == {"C++": 12, "C#": 1200}
    assert repos.languages_in("Perl") == {"Perl": 0}                            # no size: still used
    assert repos.languages_in("") == {}


def test_a_repos_file_that_calls_the_column_language_is_still_read():
    header = "Repo,Archived,Language\n"
    result = repos.read((header + "demo/a,False,Perl:5; Go:9\n").encode())
    assert result["rows"][0]["languages"] == {"Perl": 5, "Go": 9}


# ----------------------------------------------------------------------------- the contributors file

def test_the_contributors_file_is_read_one_row_per_repo_month_and_person():
    text = ("Repository,Month,Contributor login,Contributor email,Commits\n"
            "demo/a,2026-10,jo,Jo@Example.test,4\n"
            "demo/a,2026-10,jo,jo@example.test,9\n"          # the same person again in the same month: set aside
            "demo/a,2026-10,kim,,2\n"                        # no email: kept, and counted as not matched later
            ",2026-10,x,x@example.test,1\n")                 # no repo: set aside
    result = repo_contributors.read(text.encode())
    assert [(row["repo"], row["email"], row["commits"]) for row in result["rows"]] == [("demo/a", "jo@example.test", 4), ("demo/a", None, 2)]
    assert len(result["set_aside"]) == 2
    assert repo_contributors.month_of("October 2026") == "2026-10" and repo_contributors.month_of("10/2026") == "2026-10"


# ----------------------------------------------------------------------------- RD21 legacy languages

def test_rd21_is_on_when_any_repo_uses_perl_c_cplusplus_or_php():
    # Billing has 3 repos and one uses C. Lending has 2 repos, none legacy. Cards has no repo.
    facts = facts_for_example(["billing", "lending", "cards"], repos_by_team={
        "billing": [repo("legacy-billing", {"C": 340, "Python": 98000}), repo("billing-ui", {"TypeScript": 5}), repo("billing-api", {"Go": 5})],
        "lending": [repo("lending-api", {"Java": 5}), repo("lending-ui", {"TypeScript": 5})], "cards": []},
        feeds={"repos": mapped_feed("repos.csv")})
    answers = dd.legacy_languages(facts, start("RD21"), "RD21", True)
    assert answers["billing"]["on"] is True
    assert answers["billing"]["sentence"].startswith("1 of 3 repos use Perl, C, C++ or PHP (starting value): legacy-billing.")
    assert answers["billing"]["sources"][0]["file"] == "repos.csv"
    assert answers["lending"]["on"] is False
    assert answers["cards"]["on"] is None and "no active repos" in answers["cards"]["sentence"]    # never guessed


def test_rd21_changes_with_the_language_list_the_owner_sets():
    facts = facts_for_example(["a"], repos_by_team={"a": [repo("r", {"Ruby": 1})]})
    assert dd.legacy_languages(facts, start("RD21"), "RD21", True)["a"]["on"] is False
    owner_list = {**start("RD21"), "languages": "Ruby, Perl"}
    assert dd.legacy_languages(facts, owner_list, "RD21", False)["a"]["on"] is True


def test_rd21_is_not_known_without_languages():
    facts = facts_for_example(["a"], repos_by_team={"a": [repo("r", {})]})
    facts["languages_loaded"] = False
    assert dd.legacy_languages(facts, start("RD21"), "RD21", True)["a"]["on"] is None


# ----------------------------------------------------------------------------- RD53 headcount

def test_rd53_four_teams_of_12_9_6_and_4_people():
    # The median of 12, 9, 6, 4 is 7.5. 70% of 7.5 is 5.25. Only the 4-person team is below 5.25.
    facts = facts_for_example(["a", "b", "c", "d"], headcount={"a": 12, "b": 9, "c": 6, "d": 4}, feeds={"hr": mapped_feed("hr.csv")})
    answers = dd.headcount(facts, start("RD53"), "RD53", True, cfg_with(4))
    assert [answers[team]["on"] for team in "abcd"] == [False, False, False, True]
    assert "7.5 people" in answers["d"]["sentence"] and "5.25 people" in answers["d"]["sentence"]
    assert "starting value" in answers["d"]["sentence"]


def test_rd53_a_big_org_with_many_small_teams_is_not_flagged():
    # Five teams of 5 people: the median is 5, 70% of it is 3.5, and nobody is below 3.5.
    facts = facts_for_example(list("abcde"), headcount={team: 5 for team in "abcde"})
    answers = dd.headcount(facts, start("RD53"), "RD53", True, cfg_with(5))
    assert {answers[team]["on"] for team in "abcde"} == {False}


def test_rd53_is_not_known_with_too_few_teams_or_nobody_placed():
    facts = facts_for_example(["a", "b", "c"], headcount={"a": 5, "b": 5, "c": 0})
    answers = dd.headcount(facts, start("RD53"), "RD53", True, cfg_with(5))
    assert answers["a"]["on"] is None and "needs 5 teams" in answers["a"]["sentence"]    # TRUST's own fewest-teams rule
    assert answers["c"]["on"] is None and "no people" in answers["c"]["sentence"]


# ----------------------------------------------------------------------------- RD11 variety of languages

def test_rd11_counts_distinct_languages_without_markup_and_compares_with_the_median():
    # a: Go, Java, Rust (HTML left out) = 3. b: Go = 1. c: Go, Java = 2. d: Go, Java, Rust, Perl = 4. e: Go = 1.
    # The median of 3, 1, 2, 4, 1 is 2, so a and d are above it.
    sets = {"a": {"Go": 1, "Java": 1, "Rust": 1, "HTML": 9}, "b": {"Go": 1}, "c": {"Go": 1, "Java": 1},
            "d": {"Go": 1, "Java": 1, "Rust": 1, "Perl": 1}, "e": {"Go": 1, "CSS": 3}}
    facts = facts_for_example(list(sets), repos_by_team={team: [repo(team + "-r", langs)] for team, langs in sets.items()},
                              feeds={"repos": mapped_feed("repos.csv")})
    answers = dd.language_variety(facts, start("RD11"), "RD11", True, cfg_with(5))
    assert {team: answers[team]["value"] for team in sets} == {"a": 3, "b": 1, "c": 2, "d": 4, "e": 1}
    assert [team for team in sets if answers[team]["on"]] == ["a", "d"]
    assert "leaving out HTML" in answers["a"]["sentence"]


# ----------------------------------------------------------------------------- RD15 TCC adoption

def change_feeds(through_tcc, not_through_tcc):
    """Made-up changes per team: {team: count}. TCC changes and Non-TCC changes, all deployed in the month."""
    who = lambda team: [{"sam": team + "-p"}]                                  # each change names its team's person
    tcc_rows = [{"deployed": True, "month": MONTH, "ticket_id": f"{team}-T{n}", "family_id": team, "who": who(team)}
                for team, count in through_tcc.items() for n in range(count)]
    ntcc_rows = [{"deployed": True, "month": MONTH, "rpd_id": f"{team}-N{n}", "family_id": team, "also_in_tcc": False, "who": who(team)}
                 for team, count in not_through_tcc.items() for n in range(count)]
    return {"tcc": mapped_feed("tcc.csv", tcc_rows), "ntcc": mapped_feed("ntcc.csv", ntcc_rows)}


def test_rd15_is_on_for_a_team_below_the_prevailing_median_tcc_adoption():
    # a 9 of 10 = 90%, b 8 of 10 = 80%, c 5 of 10 = 50%, d 7 of 10 = 70%, e 10 of 10 = 100%. The median is 80%.
    # Only c (50%) and d (70%) are below it; b is exactly at it.
    facts = facts_for_example(list("abcde"), feeds=change_feeds(dict(a=9, b=8, c=5, d=7, e=10), dict(a=1, b=2, c=5, d=3, e=0)))
    answers = dd.tcc_adoption(facts, start("RD15"), "RD15", True, cfg_with(5))
    assert [team for team in "abcde" if answers[team]["on"]] == ["c", "d"]
    assert answers["c"]["sentence"].startswith("5 changes out of 10 went through TCC in 2026-10 (50.0%), below the prevailing median of 80.0%")
    assert [source["feed"] for source in answers["c"]["sources"]] == ["tcc", "ntcc"]


def test_rd15_is_not_known_when_the_change_files_are_not_loaded_or_the_team_had_no_changes():
    facts = facts_for_example(["a"])
    assert dd.tcc_adoption(facts, start("RD15"), "RD15", True, cfg_with(1))["a"]["on"] is None
    facts = facts_for_example(["a", "b"], feeds=change_feeds(dict(a=1), dict(a=1)))
    assert dd.tcc_adoption(facts, start("RD15"), "RD15", True, cfg_with(1))["b"]["on"] is None


# ----------------------------------------------------------------------------- RD25 multiple teams contributing

def contribution_example():
    people = [{"sam_account": sam, "email": f"{sam}@example.test", "family_id": team}
              for sam, team in [("a1", "alpha"), ("b1", "beta"), ("c1", "gamma"), ("d1", "delta"), ("a2", "alpha"), ("n1", "UNATTRIBUTED")]]
    rows = [{"repo": "alpha-api", "month": MONTH, "login": "a1", "email": "a1@example.test", "commits": 5},        # the team's own
            {"repo": "alpha-api", "month": MONTH, "login": "b1", "email": "B1@example.test ", "commits": 3},      # beta (case and space ignored)
            {"repo": "alpha-api", "month": MONTH, "login": "c1", "email": "c1@example.test", "commits": 1},       # gamma
            {"repo": "alpha-ui", "month": MONTH, "login": "d1", "email": "d1@example.test", "commits": 2},        # delta
            {"repo": "alpha-ui", "month": MONTH, "login": "b1", "email": "b1@example.test", "commits": 2},        # beta again: one team
            {"repo": "alpha-ui", "month": MONTH, "login": "a2", "email": "nobody@outside.test", "commits": 4},    # login is a SAM account, email is not in HR
            {"repo": "alpha-ui", "month": MONTH, "login": "n1", "email": "n1@example.test", "commits": 1},        # in HR, placed with no team
            {"repo": "alpha-ui", "month": "2026-09", "login": "z", "email": "z@example.test", "commits": 8},      # another month: not counted
            {"repo": "beta-api", "month": MONTH, "login": "a1", "email": "a1@example.test", "commits": 1}]
    feeds = {"hr": mapped_feed("hr.csv", people=people), "repo_contributors": mapped_feed("repo_contributors.csv", rows)}
    facts = facts_for_example(["alpha", "beta", "gamma", "delta"], feeds=feeds, repos_by_team={
        "alpha": [repo("alpha-api", {}), repo("alpha-ui", {})], "beta": [repo("beta-api", {})], "gamma": [], "delta": []})
    facts["group_of_email"] = {person["email"]: person["family_id"] for person in people if person["family_id"] != "UNATTRIBUTED"}
    return facts


def test_rd25_counts_the_other_teams_by_email_and_is_on_above_two():
    # Alpha's repos had commits from beta, gamma and delta: 3 other teams, more than 2, so it is ON.
    answers = dd.other_teams(contribution_example(), start("RD25"), "RD25", True)
    assert (answers["alpha"]["on"], answers["alpha"]["value"]) == (True, 3)
    assert "3 other teams (Beta, Delta, Gamma)" in answers["alpha"]["sentence"]
    # Beta's one repo had commits from alpha only: 1 other team, OFF.
    assert (answers["beta"]["on"], answers["beta"]["value"]) == (False, 1)


def test_rd25_never_matches_a_contributor_by_login_and_says_who_could_not_be_matched():
    answers = dd.other_teams(contribution_example(), start("RD25"), "RD25", True)
    # a2's login is a SAM account in HR, but the email isn't in HR: not matched, not guessed.
    assert "1 contributor couldn't be matched to a person in HR by email address" in answers["alpha"]["sentence"]
    assert answers["alpha"]["not_matched"] == 1
    assert "1 contributor is in HR but not in an L4 team" in answers["alpha"]["sentence"]


def test_rd25_is_not_known_without_the_file_or_without_commits_that_month():
    facts = facts_for_example(["a"], repos_by_team={"a": [repo("r", {})]})
    assert dd.other_teams(facts, start("RD25"), "RD25", True)["a"]["on"] is None
    facts["feeds"] = {"hr": mapped_feed("hr.csv", people=[]), "repo_contributors": mapped_feed("c.csv", [{"repo": "r", "month": "2026-09", "login": None, "email": "x@y.test", "commits": 3}])}
    assert "no commits for 2026-10" in dd.other_teams(facts, start("RD25"), "RD25", True)["a"]["sentence"]


# ----------------------------------------------------------------------------- the editing page's values win over the file

def test_a_saved_value_replaces_the_files_starting_value():
    entries = [{"key": "RD21", "values": {**dd.default_values("RD21"), "languages": "Ruby"}}]
    assert dd.settings_by_code(entries, ["RD21", "RD53"])["RD21"]["languages"] == "Ruby"
    assert dd.settings_by_code(entries, ["RD21", "RD53"])["RD53"]["share_of_median"] == 70       # untouched: the file's value
    with pytest.raises(ValueError):
        dd.check_values("RD21", {**dd.default_values("RD21"), "languages": ""})


# ----------------------------------------------------------------------------- through the Risk site

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("TRUST_RISKS", str(DATA_DRIVER_RISKS))
    put_made_up_teams()
    mapped = storage.load_month("mapped", MONTH)
    mapped["feeds"]["repos"] = mapped_feed("repos.csv", [
        {"repo": "lending-core", "active": True, "owner_email": "pat1@example.test", "languages": {"Perl": 10, "Python": 90}},
        {"repo": "payments-api", "active": True, "owner_email": "pay2@example.test", "languages": {"Go": 10}}], status="mapped")
    storage.save_month("mapped", MONTH, mapped)
    return web.app.test_client()


def test_the_form_shows_each_data_driver_and_submit_uses_them(client):
    form = client.get("/api/risk/groups/lending--lending-platform").json
    by_code = {driver["code"]: driver for driver in form["answered_from_data"]}
    assert by_code["RD21"]["state"] is True and "lending-core" in by_code["RD21"]["sentence"]
    assert by_code["RD21"]["sources"][0]["file"] == "repos.csv" and by_code["RD21"]["sources"][0]["as_of"] == "2026-11-03"
    assert by_code["RD53"]["state"] is False and "median is 1 people across 6 teams" in by_code["RD53"]["sentence"]   # 3 people, median of the 6 L4 teams
    assert by_code["RD25"]["state"] is None and by_code["RD25"]["sentence"].startswith("Not known:")   # no contributors file loaded
    payments = {driver["code"]: driver for driver in client.get("/api/risk/groups/payments--payments-core").json["answered_from_data"]}
    assert payments["RD21"]["state"] is False and payments["RD21"]["sentence"].startswith("The team's 1 repo doesn't use Perl, C, C++ or PHP")

    submitted = client.post("/api/risk/groups/lending--lending-platform/submit", headers=HEADERS, json={"by": "Tester", "confirm_unanswered": True})
    assert submitted.status_code == 200
    result = client.get("/api/risk/groups/lending--lending-platform/assessment").json["assessment"]["result"]
    assert result["data_drivers"]["RD21"]["on"] is True and result["data_drivers"]["RD21"]["sources"][0]["feed"] == "repos"
    assert "RD21" in [driver["code"] for driver in result["drivers"]["on"]]                       # the rating used it
    assert "RD25" in [driver["code"] for driver in result["drivers"]["not_known"]]               # never counted as on
    assert result["answers"] == {}                                                               # answers are only what people typed
    assert client.get("/api/risk/groups/lending--lending-platform").json["group"]["status"] == "Submitted"        # the data answers don't make it a Draft


def test_the_editing_list_offers_the_extra_values_for_the_drivers_that_have_them(client):
    entries = {entry["key"]: entry for entry in client.get("/api/edit/data-drivers").json["entries"]}
    assert entries["RD21"]["values"]["languages"] == "Perl, C, C++, PHP"
    assert entries["RD53"]["values"]["share_of_median"] == 70 and entries["RD25"]["values"]["fixed_number"] == 2
    assert [choice["value"] for choice in next(f for f in entries["RD25"]["fields"] if f["name"] == "basis")["choices"]] == ["Fixed number"]
    edited = dict(entries["RD21"]["values"], languages="Perl, Ruby")
    reply = client.post("/api/edit/data-drivers/save", headers=HEADERS, json={"action": "edit", "key": "RD21", "values": edited, "reason": "Ruby counts too.", "by": "Tester"})
    assert reply.status_code == 200
    form = client.get("/api/risk/groups/lending--lending-platform").json
    assert "Perl or Ruby" in next(d for d in form["answered_from_data"] if d["code"] == "RD21")["sentence"]
    assert "starting value" not in next(d for d in form["answered_from_data"] if d["code"] == "RD21")["sentence"]    # the owner set it


def test_the_cache_notices_a_driver_that_is_now_answered_from_data(client):
    """Same driver codes both times: RD21 first has a question (so it is answered on the form), then none (so it is
    answered from data). The kept answers must follow, not the ones kept for the first set of rules."""
    from trust.risk import registers
    rules = registers.load_registers()["driver_rules"]
    with_a_question = {code: dict(rule, questionnaire_fields=["RD21"] if code == "RD21" else rule["questionnaire_fields"])
                       for code, rule in rules.items()}
    assert "RD21" not in dd.current(with_a_question, None)["lending--lending-platform"]
    assert dd.current(rules, None)["lending--lending-platform"]["RD21"]["on"] is True
