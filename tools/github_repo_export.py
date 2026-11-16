"""Export the repo file for TRUST (feed "repos": TR-01 active repos, TR-02 hygiene; owner, 3 Nov 2026).

Run it monthly against GitHub Enterprise Server and upload repos.csv on the Data sources page.
It uses github_client.py next to it (set GITHUB_HOST and GITHUB_TOKEN); nothing here is part of the website.

One row per repo in the org. TRUST, not this script, decides what passes: the script only reports the
settings as GitHub has them, so the rules can change without running the export again.

Columns:
  Repo, Url, Archived, Fork, Empty, DefaultBranch, PushedAt, LastDefaultBranchCommit,
  ProtectionSource, BranchProtected, RequiredApprovals, LastPushApprovalRequired, ForcePushAllowed,
  DeletionsAllowed, AdminEnforced, BypassAllowed, StaleReviewsDismissed, CodeOwnerReviewRequired,
  StatusChecksRequired, CodeOwnersFile,
  LastHumanCommitterEmail, LastHumanCommitterLogin, LastHumanCommitDate,
  TopCommitterEmail, TopCommitterLogin, TopCommitterShare, HumanCommitsSampled,
  Languages          (only with --with-languages, which is on by default)

Languages reads "Perl:1200; C:340; Python:98000": language:bytes, largest first, empty when GitHub reports none.
It costs one extra request per repo.

A second file, repo_contributors_<YYYY-MM>.csv (with --with-contributors, on by default), lists who committed
to each repo's default branch in one month: Repository, Month, Contributor login, Contributor email, Commits.
See docs/wiki/data-sources/repo_contributors.md.

Protection can come from classic branch protection, from rulesets, or both. A setting counts as on
when either one turns it on for the default branch; BypassAllowed is true when either lets someone
skip the rules. Rulesets apply to admins unless they are listed as bypass actors.
"""
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import date

def graphql(query, variables=None):
    """Run a GraphQL query (github_client's graphql, with its rate limiter): returns the "data" part."""
    import github_client
    return github_client.graphql(query, variables)


def rest(path, params=None):
    """GET one REST page (github_client's rest, with its rate limiter). Looked up when called, not at start-up."""
    import github_client
    return github_client.rest(path, params)


def requests_per_hour():
    import github_client
    return github_client.MAX_REQUESTS_PER_HOUR

# Which orgs to export. The server itself (e.g. company.github.com) is the GITHUB_HOST setting, not here.
# ORG = ""                      every org the token's account belongs to (Repo is then "org/repo")
# ORG = "payments-eng"          just that one org (Repo is the repo name)
# ORG = ["payments-eng", "x"]   those orgs (Repo is "org/repo")
ORG = ""
INCLUDE_RULESETS = True    # set False if this GHES version rejects `rulesets` (older than 3.10)
PAGE_SIZE = 25             # lower it if the query times out
CONTRIBUTOR_MAX_PAGES = 10          # most pages of commits to read for one repo in one month
COMMITS_PER_PAGE = 100              # GitHub's largest page for commits
MINUTES_PER_HOUR = 60

# Bots and service accounts are never owners (TRUST also has its own list; this keeps the export clean).
BOT = re.compile(r"\[bot\]$|^(dependabot|renovate|github-actions|svc[-_]|jenkins)", re.I)

RULESETS = """
        rulesets(first: 20, includeParents: true) {
          nodes {
            enforcement
            bypassActors(first: 1) { totalCount }
            conditions { refName { include exclude } }
            rules(first: 50) {
              nodes {
                type
                parameters {
                  ... on PullRequestParameters {
                    requiredApprovingReviewCount requireCodeOwnerReview
                    requireLastPushApproval dismissStaleReviewsOnPush
                  }
                }
              }
            }
          }
        }"""

QUERY = """
query($org: String!, $cursor: String) {
  rateLimit { cost remaining resetAt }
  organization(login: $org) {
    repositories(first: %d, after: $cursor, orderBy: {field: NAME, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        url
        isArchived
        isFork
        isEmpty
        pushedAt
        defaultBranchRef {
          name
          target {
            ... on Commit {
              committedDate
              history(first: 20) {
                nodes { committedDate author { name email user { login } } }
              }
            }
          }
          branchProtectionRule {
            requiresApprovingReviews
            requiredApprovingReviewCount
            requireLastPushApproval
            dismissesStaleReviews
            requiresCodeOwnerReviews
            requiresStatusChecks
            isAdminEnforced
            allowsForcePushes
            allowsDeletions
            bypassPullRequestAllowances(first: 1) { totalCount }
            bypassForcePushAllowances(first: 1) { totalCount }
          }
        }
        codeownersRoot:   object(expression: "HEAD:CODEOWNERS")         { ... on Blob { byteSize } }
        codeownersGithub: object(expression: "HEAD:.github/CODEOWNERS") { ... on Blob { byteSize } }
        codeownersDocs:   object(expression: "HEAD:docs/CODEOWNERS")    { ... on Blob { byteSize } }
        %s
      }
    }
  }
}
""" % (PAGE_SIZE, RULESETS if INCLUDE_RULESETS else "")


def rulesets_for(repo, branch):
    """What the active rulesets that cover the default branch turn on, combined. None if none cover it."""
    found = None
    for rs in ((repo.get("rulesets") or {}).get("nodes") or []):
        if rs.get("enforcement") != "ACTIVE":
            continue
        ref = (rs.get("conditions") or {}).get("refName") or {}
        include, exclude = set(ref.get("include") or []), set(ref.get("exclude") or [])
        mine = {"~DEFAULT_BRANCH", "~ALL", f"refs/heads/{branch}"}
        if exclude & mine or not include & mine:
            continue
        f = found or {"approvals": 0, "last_push": False, "stale": False, "code_owner": False,
                      "status_checks": False, "no_force_push": False, "no_deletion": False, "bypass": False}
        f["bypass"] |= ((rs.get("bypassActors") or {}).get("totalCount") or 0) > 0
        for rule in ((rs.get("rules") or {}).get("nodes") or []):
            t, p = rule.get("type"), rule.get("parameters") or {}
            if t == "PULL_REQUEST":
                f["approvals"] = max(f["approvals"], p.get("requiredApprovingReviewCount") or 0)
                f["last_push"] |= bool(p.get("requireLastPushApproval"))
                f["stale"] |= bool(p.get("dismissStaleReviewsOnPush"))
                f["code_owner"] |= bool(p.get("requireCodeOwnerReview"))
            elif t == "REQUIRED_STATUS_CHECKS":
                f["status_checks"] = True
            elif t == "NON_FAST_FORWARD":
                f["no_force_push"] = True
            elif t == "DELETION":
                f["no_deletion"] = True
        found = f
    return found


def protection(repo, ref):
    bpr = ref.get("branchProtectionRule")
    rs = rulesets_for(repo, ref.get("name") or "") if INCLUDE_RULESETS else None
    if not bpr and not rs:
        return {"ProtectionSource": "none", "BranchProtected": False, "RequiredApprovals": 0,
                "LastPushApprovalRequired": False, "ForcePushAllowed": True, "DeletionsAllowed": True,
                "AdminEnforced": False, "BypassAllowed": False, "StaleReviewsDismissed": False,
                "CodeOwnerReviewRequired": False, "StatusChecksRequired": False}
    b = bpr or {}
    r = rs or {}
    count = lambda x: ((b.get(x) or {}).get("totalCount") or 0)
    return {
        "ProtectionSource": " + ".join(s for s, on in (("branch protection", bpr), ("ruleset", rs)) if on),
        "BranchProtected": True,
        "RequiredApprovals": max((b.get("requiredApprovingReviewCount") or 0) if b.get("requiresApprovingReviews") else 0,
                                 r.get("approvals", 0)),
        "LastPushApprovalRequired": bool(b.get("requireLastPushApproval")) or r.get("last_push", False),
        "ForcePushAllowed": (bool(b.get("allowsForcePushes")) if bpr else True) and not r.get("no_force_push", False),
        "DeletionsAllowed": (bool(b.get("allowsDeletions")) if bpr else True) and not r.get("no_deletion", False),
        "AdminEnforced": bool(b.get("isAdminEnforced")) if bpr else True,
        "BypassAllowed": count("bypassPullRequestAllowances") > 0 or count("bypassForcePushAllowances") > 0
                         or r.get("bypass", False),
        "StaleReviewsDismissed": bool(b.get("dismissesStaleReviews")) or r.get("stale", False),
        "CodeOwnerReviewRequired": bool(b.get("requiresCodeOwnerReviews")) or r.get("code_owner", False),
        "StatusChecksRequired": bool(b.get("requiresStatusChecks")) or r.get("status_checks", False),
    }


def committers(ref):
    """The last human committer and the most frequent one in the last 20 default-branch commits."""
    nodes = (((ref.get("target") or {}).get("history") or {}).get("nodes")) or []
    humans = []
    for c in nodes:
        a = c.get("author") or {}
        login = ((a.get("user") or {}).get("login") or "").strip().lower()
        email = (a.get("email") or "").strip().lower()
        name = a.get("name") or ""
        if (login or email) and not any(BOT.search(x) for x in (login, email, name) if x):
            humans.append((email, login, c.get("committedDate") or ""))
    if not humans:
        return {"LastHumanCommitterEmail": "", "LastHumanCommitterLogin": "", "LastHumanCommitDate": "",
                "TopCommitterEmail": "", "TopCommitterLogin": "", "TopCommitterShare": "", "HumanCommitsSampled": 0}
    counts = Counter((e, l) for e, l, _ in humans)
    most = max(counts.values())
    top = next((e, l) for e, l, _ in humans if counts[(e, l)] == most)      # a tie goes to the most recent
    return {"LastHumanCommitterEmail": humans[0][0], "LastHumanCommitterLogin": humans[0][1],
            "LastHumanCommitDate": humans[0][2], "TopCommitterEmail": top[0], "TopCommitterLogin": top[1],
            "TopCommitterShare": round(most / len(humans), 2), "HumanCommitsSampled": len(humans)}


ORGS_QUERY = """
query($cursor: String) {
  viewer { organizations(first: 100, after: $cursor) { pageInfo { hasNextPage endCursor } nodes { login } } }
}"""


def orgs():
    """The orgs to export: ORG as set, or every org the token's account belongs to."""
    if isinstance(ORG, (list, tuple)):
        return [o for o in ORG if o]
    if ORG:
        return [ORG]
    found, cursor = [], None
    while True:
        page = graphql(ORGS_QUERY, {"cursor": cursor})["viewer"]["organizations"]
        found += [o["login"] for o in page["nodes"]]
        if not page["pageInfo"]["hasNextPage"]:
            return found
        cursor = page["pageInfo"]["endCursor"]


def pause_until(reset_at):
    """Wait until GitHub's rate limit resets (resetAt, e.g. 2026-11-04T15:00:00Z) so the next page doesn't fail."""
    from datetime import datetime, timezone
    import time
    try:
        reset = datetime.fromisoformat(str(reset_at).replace("Z", "+00:00"))
        wait = max(int((reset - datetime.now(timezone.utc)).total_seconds()), 0) + 5
    except ValueError:
        wait = 60
    wait = min(wait, 3900)
    print(f"Nearly out of GitHub's hourly allowance: waiting {wait // 60} min {wait % 60} s for it to reset, "
          "then carrying on (leave this window open)", file=sys.stderr)
    time.sleep(wait)


def plan():
    """The orgs to export, each with the prefix its repo names get."""
    names = orgs()
    if not names:
        sys.exit("No orgs found: set ORG, or check the token's account belongs to at least one org.")
    one = len(names) == 1 and not isinstance(ORG, (list, tuple)) and bool(ORG)
    return [(org, "" if one else f"{org}/") for org in names]


def rows():
    """Every repo row, all orgs (no saving as it goes; the command line uses export())."""
    for org, prefix in plan():
        yield from org_rows(org, prefix)


def org_rows(org, prefix=""):
    for page_rows, _ in org_pages(org, prefix):
        yield from page_rows


def repo_row(r, prefix):
    ref = r.get("defaultBranchRef") or {}
    return {
        "Repo": prefix + r["name"], "Url": r["url"], "Archived": r["isArchived"], "Fork": r["isFork"],
        "Empty": r["isEmpty"], "DefaultBranch": ref.get("name") or "", "PushedAt": r.get("pushedAt") or "",
        "LastDefaultBranchCommit": ((ref.get("target") or {}).get("committedDate") or ""),
        **protection(r, ref),
        "CodeOwnersFile": any(r.get(k) for k in ("codeownersRoot", "codeownersGithub", "codeownersDocs")),
        **committers(ref),
        "Languages": "",      # filled by export() with --with-languages; left out of the file otherwise
    }


def org_pages(org, prefix="", cursor=None):
    """One org's repos a page at a time: yields (rows, cursor for the next page or None at the end)."""
    while True:
        data = graphql(QUERY, {"org": org, "cursor": cursor})
        page = data["organization"]["repositories"]
        rl = data.get("rateLimit") or {}
        nxt = page["pageInfo"]["endCursor"] if page["pageInfo"]["hasNextPage"] else None
        yield [repo_row(r, prefix) for r in page["nodes"]], nxt
        print(f"{org}: page done (cost {rl.get('cost')}, remaining {rl.get('remaining')})", file=sys.stderr)
        if not nxt:
            return
        cursor = nxt
        if rl.get("remaining") is not None and rl.get("cost") is not None and rl["remaining"] < 2 * rl["cost"]:
            pause_until(rl.get("resetAt"))      # not enough allowance left for the next page: wait for the reset


# ---- languages and contributors (extra requests, so each can be switched off) ----

def languages_text(language_bytes):
    """{"Perl": 1200, "C": 340} as "Perl:1200; C:340", largest first. Empty when GitHub reports none."""
    largest_first = sorted((language_bytes or {}).items(), key=lambda pair: (-pair[1], pair[0]))
    return "; ".join(f"{name}:{size}" for name, size in largest_first)


def fetch_languages(org, repo_name):
    """One request: the repo's languages as text."""
    return languages_text(rest(f"/repos/{org}/{repo_name}/languages"))


def month_window(month):
    """"2026-10" gives ("2026-10-01T00:00:00Z", "2026-11-01T00:00:00Z"): since is included, until is not."""
    year, month_number = (int(part) for part in month.split("-"))
    next_year, next_month_number = (year + 1, 1) if month_number == 12 else (year, month_number + 1)
    return (f"{year:04d}-{month_number:02d}-01T00:00:00Z",
            f"{next_year:04d}-{next_month_number:02d}-01T00:00:00Z")


def last_full_month(today=None):
    """The month before today's, as "YYYY-MM"."""
    today = today or date.today()
    year, month_number = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{year:04d}-{month_number:02d}"


def check_month(text):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text or ""):
        sys.exit(f'The month must look like 2026-10 (it is "{text}").')
    return text


NO_REPLY = re.compile(r"@users\.noreply\.", re.I)      # GitHub's hidden-address form, e.g. 123+ann@users.noreply...
PUBLIC_EMAILS = {}      # login -> public email ("" if none): each login is looked up once per run


def public_email(login):
    """The email on the person's GitHub profile (one request the first time, then remembered). "" if none."""
    if login not in PUBLIC_EMAILS:
        profile = rest(f"/users/{login}") or {}
        PUBLIC_EMAILS[login] = (profile.get("email") or "").strip().lower()
    return PUBLIC_EMAILS[login]


def best_email(login, commit_email):
    """The commit's own email. If it is empty or a GitHub no-reply address and we know the login, the profile's
    public email when there is one; otherwise the no-reply address stays as it is."""
    if login and (not commit_email or NO_REPLY.search(commit_email)):
        return public_email(login) or commit_email
    return commit_email


def contributors_in(commits, repo, month):
    """Rows for one repo: one per person, with how many commits they made. Bots are left out.
    A person is their GitHub login when the commit has one, otherwise their commit email."""
    commit_counts = Counter()
    email_of = {}
    for commit in commits:
        author_login = ((commit.get("author") or {}).get("login") or "").strip().lower()
        details = (commit.get("commit") or {}).get("author") or {}
        author_email = (details.get("email") or "").strip().lower()
        author_name = details.get("name") or ""
        if not (author_login or author_email):
            continue
        if any(BOT.search(text) for text in (author_login, author_email, author_name) if text):
            continue
        person = (author_login, "" if author_login else author_email)
        commit_counts[person] += 1
        email_of.setdefault(person, author_email)
    people = sorted(commit_counts, key=lambda person: (-commit_counts[person], person))
    return [{"Repository": repo, "Month": month, "Contributor login": person[0],
             "Contributor email": best_email(person[0], email_of[person]), "Commits": commit_counts[person]} for person in people]


def fetch_contributors(org, repo_name, branch, repo, month):
    """Reads the month's commits on the default branch, a page at a time, up to CONTRIBUTOR_MAX_PAGES pages.
    Returns (rows, capped): capped is True when there were more commits than the pages we were willing to read."""
    since, until = month_window(month)
    commits = []
    capped = False
    for page_number in range(1, CONTRIBUTOR_MAX_PAGES + 1):
        page = rest(f"/repos/{org}/{repo_name}/commits",
                    {"sha": branch, "since": since, "until": until,
                     "per_page": COMMITS_PER_PAGE, "page": page_number}) or []
        commits += page
        if len(page) < COMMITS_PER_PAGE:
            break
        if page_number == CONTRIBUTOR_MAX_PAGES:
            capped = True
    return contributors_in(commits, repo, month), capped


def wants_contributors(row):
    """Archived repos, forks and empty repos are skipped."""
    return not (row["Archived"] or row["Fork"] or row["Empty"]) and bool(row["DefaultBranch"])


def extra_request_estimate(org_names, with_languages, with_contributors):
    """Counts the repos (one cheap request per org) and returns (language requests, contributor requests).
    Contributors count one request per active repo (busy repos need more, up to the page cap), plus at most
    one profile lookup per org member for the public email (the most people there can be to look up)."""
    all_repos = active_repos = members = 0
    for org in org_names:
        data = graphql(COUNT_QUERY, {"org": org})["organization"]
        all_repos += data["everything"]["totalCount"]
        active_repos += data["active"]["totalCount"]
        members += (data.get("members") or {}).get("totalCount") or 0
    return (all_repos if with_languages else 0), (active_repos + members if with_contributors else 0)


COUNT_QUERY = """
query($org: String!) {
  organization(login: $org) {
    everything: repositories { totalCount }
    active: repositories(isArchived: false, isFork: false) { totalCount }
    members: membersWithRole { totalCount }
  }
}"""


def estimate_line(extra_requests, per_hour):
    """"This adds about 1,840 requests, about 2 hours at 900 per hour"."""
    hours = extra_requests / per_hour
    if hours >= 1:
        how_long = f"about {round(hours)} hour{'' if round(hours) == 1 else 's'}"
    else:
        minutes = max(round(hours * MINUTES_PER_HOUR), 1)
        how_long = f"about {minutes} minute{'' if minutes == 1 else 's'}"
    return f"This adds about {extra_requests:,} requests, {how_long} at {per_hour} per hour"


# ---- saving as it goes, so a stopped run carries on where it left off ----

OUT = "repos.csv"
PROGRESS = "repos.progress.json"     # exists only while a run is unfinished
CONTRIBUTOR_COLUMNS = ["Repository", "Month", "Contributor login", "Contributor email", "Commits"]


def contributors_file(month):
    return f"repo_contributors_{month}.csv"


def contributors_progress_file(month):
    return f"repo_contributors_{month}.progress.json"     # the repos already finished, exists only while unfinished


def contributors_notes_file(month):
    return f"repo_contributors_{month}.notes.txt"         # repos where the page cap cut the month short


def _save_progress(state):
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, PROGRESS)


def _load_finished(month):
    path = contributors_progress_file(month)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)["finished"]


def _save_finished(month, finished):
    path = contributors_progress_file(month)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"finished": finished}, f)
    os.replace(path + ".tmp", path)


def _tidy_contributors(month, finished):
    """After a stop, drop rows of a repo that was not marked finished (it will be read again, so no doubles)."""
    path = contributors_file(month)
    if not os.path.exists(path):
        return
    with open(path, newline="", encoding="utf-8") as f:
        kept = [r for r in csv.DictReader(f) if r["Repository"] in set(finished)]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CONTRIBUTOR_COLUMNS)
        writer.writeheader()
        writer.writerows(kept)


def _add_contributors(org, prefix, page_rows, month):
    """For each active repo on this page not yet finished: read its month, append rows, mark it finished."""
    finished = _load_finished(month)
    path = contributors_file(month)
    for row in page_rows:
        if row["Repo"] in finished or not wants_contributors(row):
            continue
        repo_name = row["Repo"][len(prefix):]
        rows_found, capped = fetch_contributors(org, repo_name, row["DefaultBranch"], row["Repo"], month)
        new_file = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CONTRIBUTOR_COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerows(rows_found)
            f.flush()
            os.fsync(f.fileno())
        if capped:
            note = (f"{row['Repo']}: stopped after {CONTRIBUTOR_MAX_PAGES} pages of {COMMITS_PER_PAGE} commits; "
                    f"people with only older commits that month may be missing.")
            print("Note: " + note, file=sys.stderr)
            with open(contributors_notes_file(month), "a", encoding="utf-8") as f:
                f.write(note + "\n")
        finished.append(row["Repo"])
        _save_finished(month, finished)


def export(fresh=False, with_languages=False, with_contributors=False, month=None):
    """The command line turns both extras on by default; a call from code asks for them by name."""
    month = check_month(month) if month else last_full_month()
    flags = {"with_languages": with_languages, "with_contributors": with_contributors,
             "month": month if with_contributors else ""}
    state = None
    if not fresh and os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("org_setting") != repr(ORG) or not os.path.exists(OUT):
            sys.exit(f"The unfinished run in {PROGRESS} was for a different ORG setting, or {OUT} is missing. "
                     "To start over, run again with --fresh.")
        if any(state.get(name) != value for name, value in flags.items()):
            sys.exit(f"The unfinished run in {PROGRESS} used different options (languages, contributors or month). "
                     "Run again with the same options, or start over with --fresh.")
        print(f"Carrying on from where the last run stopped ({state['org']}). "
              "To start over instead: --fresh", file=sys.stderr)
        if with_contributors:
            _tidy_contributors(month, _load_finished(month))
    if state is None:
        targets = plan()
        state = {"org_setting": repr(ORG), "orgs": targets, "done": [], "org": targets[0][0], "cursor": None, **flags}
        if os.path.exists(OUT):
            os.remove(OUT)
        for stale in (contributors_file(month), contributors_progress_file(month), contributors_notes_file(month)):
            if os.path.exists(stale):
                os.remove(stale)
        if with_languages or with_contributors:
            language_requests, contributor_requests = extra_request_estimate(
                [o for o, _ in targets], with_languages, with_contributors)
            print(estimate_line(language_requests + contributor_requests, requests_per_hour()),
                  file=sys.stderr)
        _save_progress(state)
    print(f"exporting {len(state['orgs'])} org(s): {', '.join(o for o, _ in state['orgs'])}", file=sys.stderr)

    seen, header = set(), None
    if os.path.exists(OUT) and os.path.getsize(OUT):
        with open(OUT, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            header = rd.fieldnames
            seen = {r["Repo"] for r in rd}
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header) if header else None
        for org, prefix in state["orgs"]:
            if org in state["done"]:
                continue
            cursor = state["cursor"] if org == state["org"] else None
            for page_rows, nxt in org_pages(org, prefix, cursor):
                new = [r for r in page_rows if r["Repo"] not in seen]   # a page fetched twice isn't written twice
                for r in new:
                    if with_languages:
                        r["Languages"] = fetch_languages(org, r["Repo"][len(prefix):])
                    else:
                        del r["Languages"]
                if new and w is None:
                    w = csv.DictWriter(f, fieldnames=list(new[0]))
                    w.writeheader()
                if new:
                    w.writerows(new)
                f.flush()
                os.fsync(f.fileno())
                seen.update(r["Repo"] for r in new)
                if with_contributors:
                    _add_contributors(org, prefix, page_rows, month)
                state.update(org=org, cursor=nxt)
                if nxt is None:
                    state["done"].append(org)
                _save_progress(state)
    os.remove(PROGRESS)
    if with_contributors and os.path.exists(contributors_progress_file(month)):
        os.remove(contributors_progress_file(month))
    if not seen:
        sys.exit("No repos returned: check ORG and the token's access.")
    print(f"{len(seen)} repos written to {OUT}")
    if with_contributors:
        print(f"Contributors for {month} written to {contributors_file(month)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export the repo file for TRUST.")
    parser.add_argument("--fresh", action="store_true", help="start over instead of carrying on an unfinished run")
    parser.add_argument("--max-requests-per-hour", type=int, default=None,
                        help="most requests to make per hour (default 900, or GITHUB_MAX_REQUESTS_PER_HOUR)")
    parser.add_argument("--with-languages", action=argparse.BooleanOptionalAction, default=True,
                        help="add the Languages column (one extra request per repo); on by default, "
                             "turn off with --no-with-languages")
    parser.add_argument("--with-contributors", action=argparse.BooleanOptionalAction, default=True,
                        help="also write repo_contributors_<month>.csv; on by default, "
                             "turn off with --no-with-contributors")
    parser.add_argument("--month", default=None, help="month for the contributors file, like 2026-10 "
                                                      "(default: the last full month)")
    options = parser.parse_args()
    if options.max_requests_per_hour is not None:
        from github_client import set_max_requests_per_hour
        set_max_requests_per_hour(options.max_requests_per_hour)
    export(fresh=options.fresh, with_languages=options.with_languages,
           with_contributors=options.with_contributors, month=options.month)
