"""tools/github_repo_export.py: the Languages column, the monthly contributors file, the page cap,
the up-front estimate, carrying on after a stop, and how few requests it all takes. A fake GitHub answers;
no network."""
import csv
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import github_repo_export as exporter  # noqa: E402

MONTH = "2026-10"


def commit(login, email, name="Pat"):
    """One commit as GraphQL's history returns it."""
    return {"author": {"name": name, "email": email, "user": {"login": login} if login else None}}


def repo_node(name, **overrides):
    node = {"name": name, "url": f"https://git.example/org/{name}", "isArchived": False, "isFork": False,
            "isEmpty": False, "pushedAt": "2026-10-20T00:00:00Z",
            "defaultBranchRef": {"name": "main", "target": {"committedDate": "2026-10-20T00:00:00Z",
                                                            "history": {"nodes": []}},
                                 "branchProtectionRule": None}}
    node.update(overrides)
    return node


class FakeGitHub:
    """Answers GraphQL only (the count query, the repo pages, follow-up history pages and the email lookups),
    the way GitHub would. Remembers every request. Any REST call fails the test: none should be needed."""

    def __init__(self, nodes, languages=None, commits=None):
        self.nodes = nodes
        self.languages = languages or {}
        self.commits = commits or {}        # repo -> {page number: [commits]}
        self.calls = []                     # (kind, variables)
        self.public_emails = {}
        self.stop_after = None              # raise after this many history or email requests, to fake a stop

    def history_page(self, repo, number):
        pages = self.commits.get(repo, {})
        has_next = number + 1 in pages
        return {"pageInfo": {"hasNextPage": has_next, "endCursor": f"p{number + 1}" if has_next else None},
                "nodes": pages.get(number, [])}

    def extra(self, kind, variables):
        self.calls.append((kind, dict(variables or {})))
        if self.stop_after is not None and len(self.extra_calls()) > self.stop_after:
            raise KeyboardInterrupt

    def extra_calls(self):
        return [call for call in self.calls if call[0] in ("history", "emails")]

    def graphql(self, query, variables=None):
        variables = variables or {}
        if "everything" in query:
            self.calls.append(("count", variables))
            active = [n for n in self.nodes if not n["isArchived"] and not n["isFork"]]
            return {"organization": {"everything": {"totalCount": len(self.nodes)},
                                     "active": {"totalCount": len(active)},
                                     "members": {"totalCount": 4}}}
        if "repository(owner" in query:
            self.extra("history", variables)
            number = int(variables["cursor"][1:]) if variables.get("cursor") else 1
            return {"repository": {"ref": {"target": {"history": self.history_page(variables["name"], number)}}}}
        if "user(login" in query:
            self.extra("emails", variables)
            logins = {key: login for key, login in variables.items()}
            return {f"u{key[1:]}": {"email": self.public_emails.get(login)} for key, login in logins.items()}
        self.calls.append(("page", variables))
        nodes = []
        for node in self.nodes:
            node = {**node, "defaultBranchRef": {**node["defaultBranchRef"],
                                                 "target": dict(node["defaultBranchRef"]["target"])}}
            if "languages(" in query:
                node["languages"] = {"edges": [{"size": size, "node": {"name": language}} for language, size
                                               in sorted(self.languages.get(node["name"], {}).items(),
                                                         key=lambda pair: -pair[1])]}
            if "monthHistory" in query:
                node["defaultBranchRef"]["target"]["monthHistory"] = self.history_page(node["name"], 1)
            nodes.append(node)
        return {"rateLimit": {}, "organization": {"repositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}

    def rest(self, path, params=None, all_pages=False):
        raise AssertionError(f"no REST call expected, got {path}")


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
    assert [kind for kind, _ in fake.calls] == ["count", "page"]      # languages came with the page


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
    page_call = next(v for kind, v in fake.calls if kind == "page")
    assert page_call["since"] == "2026-10-01T00:00:00Z" and page_call["until"] == "2026-11-01T00:00:00Z"
    history_calls = [v for kind, v in fake.calls if kind == "history"]      # only the second page is extra
    assert [(v["name"], v["branch"], v["cursor"]) for v in history_calls] == [("alpha", "refs/heads/main", "p2")]


def test_quiet_repos_need_no_extra_requests(world):
    commits = {name: {1: [commit("ann", "ann@x.com")]} for name in ("alpha", "beta", "gamma")}
    fake = world(FakeGitHub([repo_node(n) for n in ("alpha", "beta", "gamma")], commits=commits))
    exporter.export(with_languages=True, with_contributors=True, month=MONTH)
    assert [kind for kind, _ in fake.calls] == ["count", "page"]
    assert len(read(f"repo_contributors_{MONTH}.csv")) == 3


def test_archived_forks_and_empty_repos_are_skipped(world):
    nodes = [repo_node("old", isArchived=True), repo_node("copy", isFork=True), repo_node("blank", isEmpty=True)]
    fake = world(FakeGitHub(nodes))
    exporter.export(with_contributors=True, month=MONTH)
    assert fake.extra_calls() == []
    assert not pathlib.Path(f"repo_contributors_{MONTH}.csv").exists()


def test_page_cap_stops_reading_and_is_noted(world, monkeypatch, capsys):
    monkeypatch.setattr(exporter, "CONTRIBUTOR_MAX_PAGES", 3)
    full_page = [commit("ann", "ann@x.com")] * exporter.COMMITS_PER_PAGE
    fake = world(FakeGitHub([repo_node("busy")], commits={"busy": {1: full_page, 2: full_page, 3: full_page, 4: full_page}}))
    exporter.export(with_contributors=True, month=MONTH)
    assert len([kind for kind, _ in fake.calls if kind == "history"]) == 2     # page 1 came with the repo page
    assert read(f"repo_contributors_{MONTH}.csv")[0]["Commits"] == "300"
    note = pathlib.Path(f"repo_contributors_{MONTH}.notes.txt").read_text()
    assert "busy: stopped after 3 pages" in note
    assert "stopped after 3 pages" in capsys.readouterr().err


def test_estimate_line():
    assert exporter.estimate_line(1840, 900) == "This takes about 1,840 requests, about 2 hours at 900 per hour"
    assert exporter.estimate_line(120, 900) == "This takes about 120 requests, about 8 minutes at 900 per hour"


def test_estimate_is_printed_before_starting(world, capsys):
    world(FakeGitHub([repo_node("alpha"), repo_node("old", isArchived=True)]))
    exporter.export(with_languages=True, with_contributors=True, month=MONTH)
    # 1 page of repos + 1 email lookup (4 members, 50 to a request)
    assert "This takes about 2 requests" in capsys.readouterr().err


def test_last_full_month():
    import datetime
    assert exporter.last_full_month(datetime.date(2026, 11, 16)) == "2026-10"
    assert exporter.last_full_month(datetime.date(2027, 1, 5)) == "2026-12"


def test_run_that_stopped_carries_on_without_repeating_finished_repos(world):
    two_pages = {1: [commit("ann", "ann@x.com")], 2: [commit("bob", "bob@x.com")]}
    fake = world(FakeGitHub([repo_node(n) for n in ("alpha", "beta", "gamma")],
                            commits={name: two_pages for name in ("alpha", "beta", "gamma")}))
    fake.stop_after = 2                      # alpha's second page, beta's second page, then it stops
    with pytest.raises(KeyboardInterrupt):
        exporter.export(with_contributors=True, month=MONTH)
    assert pathlib.Path("repos.progress.json").exists()
    fake.stop_after = None
    fake.calls.clear()
    exporter.export(with_contributors=True, month=MONTH)
    assert [v["name"] for kind, v in fake.calls if kind == "history"] == ["gamma"]
    assert [r["Repository"] for r in read(f"repo_contributors_{MONTH}.csv")] == ["alpha", "alpha", "beta", "beta",
                                                                                  "gamma", "gamma"]
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
    lookups = [sorted(v.values()) for kind, v in fake.calls if kind == "emails"]
    assert lookups == [["ann", "dee"]]      # one request for both; ann not again for beta; cy's own email is kept


def test_many_logins_are_looked_up_fifty_to_a_request(world):
    noreply = "1+x@users.noreply.git.example"
    people = [commit(f"p{i:03d}", noreply) for i in range(120)]
    fake = world(FakeGitHub([repo_node("alpha")], commits={"alpha": {1: people[:100], 2: people[100:]}}))
    exporter.export(with_contributors=True, month=MONTH)
    assert [len(v) for kind, v in fake.calls if kind == "emails"] == [50, 50, 20]
