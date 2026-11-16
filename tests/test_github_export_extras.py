"""tools/github_repo_export.py: the Languages column, the monthly contributors file, the page cap,
the up-front estimate and carrying on after a stop. A fake GitHub answers; no network."""
import csv
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import github_repo_export as exporter  # noqa: E402

MONTH = "2026-10"


def commit(login, email, name="Pat"):
    return {"author": {"login": login} if login else None, "commit": {"author": {"email": email, "name": name}}}


def repo_node(name, **overrides):
    node = {"name": name, "url": f"https://git.example/org/{name}", "isArchived": False, "isFork": False,
            "isEmpty": False, "pushedAt": "2026-10-20T00:00:00Z",
            "defaultBranchRef": {"name": "main", "target": {"committedDate": "2026-10-20T00:00:00Z",
                                                            "history": {"nodes": []}},
                                 "branchProtectionRule": None}}
    node.update(overrides)
    return node


class FakeGitHub:
    """Answers the count query, the repo page query, /languages and /commits. Remembers every request."""

    def __init__(self, nodes, languages=None, commits=None):
        self.nodes = nodes
        self.languages = languages or {}
        self.commits = commits or {}
        self.rest_calls = []
        self.public_emails = {}
        self.stop_after = None      # raise after this many rest calls, to fake a stopped run

    def graphql(self, query, variables=None):
        if "everything" in query:
            active = [n for n in self.nodes if not n["isArchived"] and not n["isFork"]]
            return {"organization": {"everything": {"totalCount": len(self.nodes)},
                                     "active": {"totalCount": len(active)},
                                     "members": {"totalCount": 4}}}
        return {"rateLimit": {}, "organization": {"repositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.nodes}}}

    def rest(self, path, params=None, all_pages=False):
        self.rest_calls.append((path, dict(params or {})))
        if self.stop_after is not None and len(self.rest_calls) > self.stop_after:
            raise KeyboardInterrupt
        if path.endswith("/languages"):
            return self.languages.get(path.split("/")[3], {})
        if path.startswith("/users/"):
            return {"email": self.public_emails.get(path.split("/")[2])}
        repo = path.split("/")[3]
        return self.commits.get(repo, {}).get(params["page"], [])


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(exporter, "ORG", "org")
    exporter.PUBLIC_EMAILS.clear()

    def install(fake):
        monkeypatch.setattr(exporter, "graphql", fake.graphql)
        monkeypatch.setattr(exporter, "rest", fake.rest)
        return fake
    return install


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_languages_text_is_largest_first():
    assert exporter.languages_text({"Perl": 1200, "C": 340, "Python": 98000}) == "Python:98000; Perl:1200; C:340"
    assert exporter.languages_text({}) == ""


def test_languages_column_in_repos_file(world, capsys):
    fake = world(FakeGitHub([repo_node("alpha"), repo_node("beta")],
                            languages={"alpha": {"Perl": 1200, "C": 340, "Python": 98000}}))
    exporter.export(with_languages=True)
    rows = read("repos.csv")
    assert rows[0]["Languages"] == "Python:98000; Perl:1200; C:340"
    assert rows[1]["Languages"] == ""
    assert [path for path, _ in fake.rest_calls] == ["/repos/org/alpha/languages", "/repos/org/beta/languages"]


def test_no_languages_column_when_switched_off(world):
    world(FakeGitHub([repo_node("alpha")]))
    exporter.export()
    assert "Languages" not in read("repos.csv")[0]


def test_contributors_from_two_pages_of_commits(world):
    first_page = [commit("ann", "ann@x.com")] * 60 + [commit("bob", "bob@x.com")] * 40
    second_page = [commit("ann", "ann@x.com")] * 5 + [commit(None, "Zed@X.com")] * 2 + [commit(None, "bot@x.com", "dependabot[bot]")]
    fake = world(FakeGitHub([repo_node("alpha")], commits={"alpha": {1: first_page, 2: second_page}}))
    exporter.export(with_contributors=True, month=MONTH)
    rows = read(f"repo_contributors_{MONTH}.csv")
    assert [(r["Contributor login"], r["Contributor email"], r["Commits"]) for r in rows] == [
        ("ann", "ann@x.com", "65"), ("bob", "bob@x.com", "40"), ("", "zed@x.com", "2")]
    assert rows[0]["Repository"] == "alpha" and rows[0]["Month"] == MONTH
    commit_calls = [params for path, params in fake.rest_calls if path.endswith("/commits")]
    assert [call["page"] for call in commit_calls] == [1, 2]
    assert commit_calls[0]["since"] == "2026-10-01T00:00:00Z" and commit_calls[0]["until"] == "2026-11-01T00:00:00Z"
    assert commit_calls[0]["sha"] == "main"


def test_archived_forks_and_empty_repos_are_skipped(world):
    nodes = [repo_node("old", isArchived=True), repo_node("copy", isFork=True), repo_node("blank", isEmpty=True)]
    fake = world(FakeGitHub(nodes))
    exporter.export(with_contributors=True, month=MONTH)
    assert fake.rest_calls == []


def test_page_cap_stops_reading_and_is_noted(world, monkeypatch, capsys):
    monkeypatch.setattr(exporter, "CONTRIBUTOR_MAX_PAGES", 3)
    full_page = [commit("ann", "ann@x.com")] * exporter.COMMITS_PER_PAGE
    fake = world(FakeGitHub([repo_node("busy")], commits={"busy": {1: full_page, 2: full_page, 3: full_page, 4: full_page}}))
    exporter.export(with_contributors=True, month=MONTH)
    assert len([p for p, _ in fake.rest_calls if p.endswith("/commits")]) == 3
    assert read(f"repo_contributors_{MONTH}.csv")[0]["Commits"] == "300"
    note = pathlib.Path(f"repo_contributors_{MONTH}.notes.txt").read_text()
    assert "busy: stopped after 3 pages" in note
    assert "stopped after 3 pages" in capsys.readouterr().err


def test_estimate_line():
    assert exporter.estimate_line(1840, 900) == "This adds about 1,840 requests, about 2 hours at 900 per hour"
    assert exporter.estimate_line(450, 900) == "This adds about 450 requests, about 30 minutes at 900 per hour"


def test_estimate_is_printed_before_starting(world, capsys):
    world(FakeGitHub([repo_node("alpha"), repo_node("old", isArchived=True)]))
    exporter.export(with_languages=True, with_contributors=True, month=MONTH)
    # 2 repos for languages + 1 active repo and up to 4 email lookups (one per member) for contributors
    assert "This adds about 7 requests" in capsys.readouterr().err


def test_last_full_month():
    import datetime
    assert exporter.last_full_month(datetime.date(2026, 11, 16)) == "2026-10"
    assert exporter.last_full_month(datetime.date(2027, 1, 5)) == "2026-12"


def test_run_that_stopped_carries_on_without_repeating_finished_repos(world):
    commits = {name: {1: [commit("ann", "ann@x.com")]} for name in ("alpha", "beta", "gamma")}
    fake = world(FakeGitHub([repo_node(n) for n in ("alpha", "beta", "gamma")], commits=commits))
    fake.stop_after = 2                      # alpha's commits, beta's commits, then it stops
    with pytest.raises(KeyboardInterrupt):
        exporter.export(with_contributors=True, month=MONTH)
    assert pathlib.Path("repos.progress.json").exists()
    fake.stop_after = None
    fake.rest_calls.clear()
    exporter.export(with_contributors=True, month=MONTH)
    assert [p for p, _ in fake.rest_calls] == ["/repos/org/gamma/commits"]
    assert [r["Repository"] for r in read(f"repo_contributors_{MONTH}.csv")] == ["alpha", "beta", "gamma"]
    assert not pathlib.Path("repos.progress.json").exists()
    assert not pathlib.Path(f"repo_contributors_{MONTH}.progress.json").exists()


def test_no_reply_email_is_replaced_by_the_public_email_once_per_login(world):
    noreply = "12+ann@users.noreply.git.example"
    commits = {"alpha": {1: [commit("ann", noreply)] * 2 + [commit("cy", "cy@x.com"), commit("dee", noreply)]},
               "beta": {1: [commit("ann", noreply)]}}
    fake = world(FakeGitHub([repo_node("alpha"), repo_node("beta")], commits=commits))
    fake.public_emails = {"ann": "Ann@Corp.com"}          # dee has no public email
    exporter.export(with_contributors=True, month=MONTH)
    people = {(r["Repository"], r["Contributor login"]): r["Contributor email"]
              for r in read(f"repo_contributors_{MONTH}.csv")}
    assert people == {("alpha", "ann"): "ann@corp.com", ("alpha", "cy"): "cy@x.com",
                      ("alpha", "dee"): noreply, ("beta", "ann"): "ann@corp.com"}
    lookups = [path for path, _ in fake.rest_calls if path.startswith("/users/")]
    assert sorted(lookups) == ["/users/ann", "/users/dee"]     # ann once, though in two repos; cy's own email is kept
