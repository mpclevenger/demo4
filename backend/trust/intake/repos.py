"""Read the GitHub repo file on its own (feed "repos"; owner, 3 Nov 2026). Feeds TR-02 (wanted).

The file comes from tools/github_repo_export.py: one row per repo with its settings as GitHub has them
and its recent human committers. TRUST, not the export, decides what passes, here:

TR-02 hygiene checks (owner, 3 Nov 2026), one point each; a repo's score = checks passed / 5:
  1. Main branch protected      branch protection or an active ruleset covers the default branch
  2. Review required            at least 1 approving review before merge
  3. Independent approval       the most recent push must be approved by someone other than its pusher
  4. History can't be rewritten force pushes and branch deletion both blocked
  5. No one can skip the rules  admins held to the rules and nobody has bypass rights
Checks 2 to 5 are settings of the protection, so an unprotected repo scores 0 of 5.
Shown, not scored: CODEOWNERS file, required status checks, stale approvals dismissed.

Which team a repo belongs to is worked out at mapping (backend/trust/mapping.py): the app inventory first (the
team of the active app it is linked to), then the GitHub committer -> HR -> team (owner, 17 Nov 2026).
"""
import re

from ..numbers import percent
from .common import as_bool, column_map, map_columns, norm, parse_when, read_table

FIELDS = {f: (f,) for f in (
    "Repo", "Url", "Archived", "Fork", "Empty", "DefaultBranch", "PushedAt", "LastDefaultBranchCommit",
    "ProtectionSource", "BranchProtected", "RequiredApprovals", "LastPushApprovalRequired", "ForcePushAllowed",
    "DeletionsAllowed", "AdminEnforced", "BypassAllowed", "StaleReviewsDismissed", "CodeOwnerReviewRequired",
    "StatusChecksRequired", "CodeOwnersFile", "LastHumanCommitterEmail", "LastHumanCommitterLogin",
    "LastHumanCommitDate", "TopCommitterEmail", "TopCommitterLogin", "TopCommitterShare", "HumanCommitsSampled",
    "Languages")}

CHECKS = (("protected", "Main branch protected"), ("review", "Review required"),
          ("independent", "Independent approval"), ("history", "History can't be rewritten"),
          ("no_bypass", "No one can skip the rules"))
INFO = (("codeowners", "CODEOWNERS file"), ("status_checks", "Required status checks"),
        ("stale_dismissed", "Stale approvals dismissed"))
SETTINGS = ("BranchProtected", "RequiredApprovals", "LastPushApprovalRequired", "ForcePushAllowed",
            "DeletionsAllowed", "AdminEnforced", "BypassAllowed")


def checks_for(s):
    """The 5 scored checks and the 3 shown ones from a repo's settings (booleans; None counts as not set)."""
    on = lambda k: s.get(k) is True
    prot = on("BranchProtected")
    passed = {
        "protected": prot,
        "review": prot and (s.get("RequiredApprovals") or 0) >= 1,
        "independent": prot and on("LastPushApprovalRequired"),
        "history": prot and s.get("ForcePushAllowed") is False and s.get("DeletionsAllowed") is False,
        "no_bypass": prot and on("AdminEnforced") and s.get("BypassAllowed") is False,
    }
    info = {"codeowners": on("CodeOwnersFile"), "status_checks": on("StatusChecksRequired"),
            "stale_dismissed": on("StaleReviewsDismissed")}
    return passed, info


def _int(v):
    m = re.fullmatch(r"\s*(\d+)(\.0+)?\s*", str(v or ""))
    return int(m.group(1)) if m else None


def languages_in(text):
    """The languages a repo uses, from the file's Languages cell: "Perl:1200; C:340; Python:98000" gives
    {"Perl": 1200, "C": 340, "Python": 98000} (the number is the size of the code in that language).
    A language with no size ("Perl") is kept with size 0: it is still used. Empty or missing gives {}.
    The list may be separated by semicolons or commas."""
    found = {}
    for part in re.split(r";|,(?!\s*\d{3}\b)", str(text or "")):       # a comma inside 1,200 is not a separator
        part = part.strip()
        if not part:
            continue
        name, _, size = part.rpartition(":") if ":" in part else (part, "", "")
        name = name.strip()
        if not name:
            continue
        size_digits = re.sub(r"[,\s]", "", size)
        found[name] = int(size_digits) if size_digits.isdigit() else 0
    return found


def read(raw_bytes):
    """Returns dict(rows, set_aside, notes, summary). Each row has the repo's settings, its committers,
    `checks` (the 5 scored, True/False), `info` (the 3 shown) and `score` (passed / 5)."""
    notes, set_aside, rows, seen = [], [], [], set()
    cmap = column_map("repos", FIELDS)
    headers, table = read_table(raw_bytes, 1, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()
    missing = [f for f in SETTINGS if col[f] is None]
    if missing:
        notes.append(f"No column for {', '.join(missing)}: the checks that need it fail for every repo until it is found")

    if col["Languages"] is None:
        notes.append("No Languages column: the risk drivers that look at the languages a team's repos use show "
                     "'not known' until the file has it")

    blanks, bad_dates = {}, {}
    for i, r in enumerate(table, start=2):
        name = g(r, "Repo")
        if not name:
            set_aside.append(dict(row=i, reason="no Repo"))
            continue
        if name.lower() in seen:
            set_aside.append(dict(row=i, reason=f"repo '{name}' is on more than one row; first kept"))
            continue
        seen.add(name.lower())
        s = {}
        for f in ("Archived", "Fork", "Empty", "BranchProtected", "LastPushApprovalRequired", "ForcePushAllowed",
                  "DeletionsAllowed", "AdminEnforced", "BypassAllowed", "StaleReviewsDismissed",
                  "CodeOwnerReviewRequired", "StatusChecksRequired", "CodeOwnersFile"):
            s[f] = as_bool(g(r, f)) if g(r, f) else None
            if col[f] and s[f] is None and f in SETTINGS:
                blanks.setdefault(f, []).append(name)
        s["RequiredApprovals"] = _int(g(r, "RequiredApprovals"))
        when = {}
        for f in ("PushedAt", "LastDefaultBranchCommit", "LastHumanCommitDate"):
            when[f] = parse_when(g(r, f))
            if g(r, f) and when[f] is None:
                bad_dates.setdefault(f, []).append(name)
        passed, info = checks_for(s)
        activity = max((d for d in (when["PushedAt"], when["LastDefaultBranchCommit"]) if d), default=None)
        rows.append({
            "repo": name, "url": g(r, "Url") or None, "default_branch": g(r, "DefaultBranch") or None,
            "archived": s["Archived"] is True, "fork": s["Fork"] is True, "empty": s["Empty"] is True,
            "last_activity": activity.isoformat() if activity else None,
            "protection_source": g(r, "ProtectionSource") or None,
            "settings": s,
            "last_committer": {"email": g(r, "LastHumanCommitterEmail").lower() or None,
                               "login": g(r, "LastHumanCommitterLogin").lower() or None,
                               "at": when["LastHumanCommitDate"].isoformat() if when["LastHumanCommitDate"] else None},
            "top_committer": {"email": g(r, "TopCommitterEmail").lower() or None,
                              "login": g(r, "TopCommitterLogin").lower() or None,
                              "share": g(r, "TopCommitterShare") or None},
            "human_commits_sampled": _int(g(r, "HumanCommitsSampled")) or 0,
            "languages": languages_in(g(r, "Languages")),
            "checks": passed, "info": info, "passed": sum(passed.values()),
            "score": percent(sum(passed.values()), len(CHECKS)),
        })

    show = lambda names: (", ".join(names[:5]) + (f", and {len(names) - 5} more" if len(names) > 5 else ""))
    for f, names in blanks.items():
        notes.append(f"{len(names)} {'repo has' if len(names) == 1 else 'repos have'} no value in {f}; "
                     f"counted as not set ({show(names)})")
    for f, names in bad_dates.items():
        notes.append(f"{f} isn't a date for {len(names)} {'repo' if len(names) == 1 else 'repos'} ({show(names)})")
    no_human = [x for x in rows if not (x["last_committer"]["email"] or x["last_committer"]["login"])]
    if no_human:
        # Why, so the count can be checked (owner, 4 Nov 2026): most are usually empty, archived or forks.
        why = {}
        for x in no_human:
            k = ("empty (no commits)" if x["empty"] else "archived" if x["archived"] else "forks" if x["fork"]
                 else "only bots or service accounts in the last 20 commits")
            why.setdefault(k, []).append(x["repo"])
        parts = "; ".join(f"{len(v)} {k} (e.g. {show(v)})" for k, v in sorted(why.items(), key=lambda kv: -len(kv[1])))
        notes.append(f"{len(no_human)} {'repo has' if len(no_human) == 1 else 'repos have'} no human committer in "
                     f"the last 20 commits, so no owner: {parts}. Only active repos ever count for an L3 team.")
    summary = dict(repos=len(rows), archived=sum(x["archived"] for x in rows), forks=sum(x["fork"] for x in rows),
                   unprotected=sum(not x["checks"]["protected"] for x in rows), set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)


ACTIVE_DAYS = 90             # default for the setting repo_active_days
OWNER_RULES = ("last_commit", "most_commits")
UNMATCHED = "UNATTRIBUTED"   # the same "Not yet mapped" every feed uses


def _next_month_start(month):
    y, m = int(month[:4]), int(month[5:7])
    return parse_when(f"{y + (m == 12)}-{(m % 12) + 1:02d}-01")


MATCH_BY = ("email", "email_then_login")     # how a repo owner is found in HR (owner, 4 Nov 2026: email)


def team_from_inventory(repo_row):
    """The team a repo takes from the app inventory (owner, 17 Nov 2026), or why it can't.
    Returns (family_id, app label, None) when the apps linked to the repo settle it, else (None, None, note or None).
    Only apps placed with a team count. One team: that team. Several teams: the team with the most apps; a tie
    settles nothing, and the note says so (the committer rule then applies)."""
    placements = [p for p in repo_row.get("app_placements") or [] if p.get("family_id")]
    if not placements:
        return None, None, None
    apps_per_team = {}
    for placement in placements:
        apps_per_team.setdefault(placement["family_id"], []).append(placement["app"])
    most_apps = max(len(apps) for apps in apps_per_team.values())
    leaders = [team for team, apps in apps_per_team.items() if len(apps) == most_apps]
    if len(leaders) > 1:
        return None, None, f"{repo_row['repo']} (apps in {len(apps_per_team)} teams, a tie)"
    winner = leaders[0]
    return winner, ", ".join(apps_per_team[winner]), None


def place_and_score(rows, month, people, family_of_sam, settings=None):
    """Give each repo its team and work out the hygiene figures (owner, 3 Nov 2026).

    Team (owner, 17 Nov 2026: app inventory first, then the GitHub committer): a repo linked to an active app
    in the app inventory that is placed with a team takes that app's team (how: "app inventory"); linked to
    several apps in different teams, the team of the most of them; a tie falls back to the committer, with a
    note. Otherwise the committer rule below (how: "committer"). Sets family_how, placed_by and family_app.

    Owner (owner, 3 Nov 2026): the human with the most of the last 20 main-branch commits, a tie going
    to the most recent (setting repo_owner_rule "most_commits", the default), or the last human
    committer ("last_commit"). Matched to HR by the commit's email address = HR work email (owner, 4 Nov
    2026: setting repo_match_by "email", the default); "email_then_login" also tries GitHub login =
    SAM_ACCOUNT. No match, or no human committer: unmatched (Not yet mapped).
    Active: not archived, not a fork, and a push or default-branch commit within repo_active_days
    (90) before the end of the month. Only active, placed repos count for a family.
    Family figure: checks passed / checks possible across its active repos (= the average repo score).

    Sets on each row: owner_email, owner_login, owner_matched_by, family_id, active, inactive_reason.
    Returns dict(families={fid: {...}}, unmatched_active, notes).
    """
    from .common import add_days
    s = settings or {}
    rule = s.get("repo_owner_rule") if s.get("repo_owner_rule") in OWNER_RULES else "most_commits"
    match_by = s.get("repo_match_by") if s.get("repo_match_by") in MATCH_BY else "email"
    days = s.get("repo_active_days")
    days = days if isinstance(days, int) and not isinstance(days, bool) and days > 0 else ACTIVE_DAYS
    end = _next_month_start(month)
    since = add_days(end, -days)
    by_email = {(p.get("email") or "").lower(): p["sam_account"].lower() for p in people if p.get("email")}
    sams = {p["sam_account"].lower() for p in people}
    fam = {k.lower(): v for k, v in (family_of_sam or {}).items()}

    notes, owners, ties = [], {}, []
    for x in rows:
        who = x["last_committer"] if rule == "last_commit" else x["top_committer"]
        email, login = who.get("email"), who.get("login")
        sam, how = None, None
        if email and email in by_email:
            sam, how = by_email[email], "email"
        elif match_by == "email_then_login" and login and login in sams:
            sam, how = login, "login = SAM_ACCOUNT"
        x["owner_email"], x["owner_login"], x["owner_matched_by"] = email, login, how
        committer_team = fam.get(sam, UNMATCHED) if sam else UNMATCHED
        x["committer_family"] = committer_team          # kept: the people shown on the repo follow it when it is the same team
        inventory_team, inventory_app, tie_note = team_from_inventory(x)
        if tie_note:
            ties.append(tie_note)
        if inventory_team:
            x["family_id"], x["family_how"], x["family_app"] = inventory_team, "app inventory", inventory_app
            x["placed_by"] = f"app inventory ({inventory_app})"
        else:
            x["family_id"], x["family_app"] = committer_team, None
            x["family_how"] = "committer" if committer_team != UNMATCHED else None
            x["placed_by"] = "committer" if committer_team != UNMATCHED else None
        last = parse_when(x["last_activity"]) if x["last_activity"] else None
        x["inactive_reason"] = ("archived" if x["archived"] else "fork" if x["fork"] else
                                "no activity" if last is None or last < since else None)
        x["active"] = x["inactive_reason"] is None
        if x["active"] and sam:
            owners.setdefault(sam, []).append(x["repo"])

    families = {}
    for x in rows:
        if not x["active"] or x["family_id"] == UNMATCHED:
            continue
        f = families.setdefault(x["family_id"], {"repos": 0, "checks_passed": 0, "checks_possible": 0,
                                                  "unprotected": [], "fails": {k: 0 for k, _ in CHECKS},
                                                  "info": {k: 0 for k, _ in INFO}})
        f["repos"] += 1
        f["checks_passed"] += x["passed"]
        f["checks_possible"] += len(CHECKS)
        if not x["checks"]["protected"]:
            f["unprotected"].append(x["repo"])
        for k, _ in CHECKS:
            f["fails"][k] += not x["checks"][k]
        for k, _ in INFO:
            f["info"][k] += x["info"][k]
    for f in families.values():
        f["score"] = percent(f["checks_passed"], f["checks_possible"])
        f["unprotected_count"] = len(f["unprotected"])

    active_rows = [x for x in rows if x["active"]]
    by_inventory = sum(1 for x in active_rows if x["family_how"] == "app inventory")
    by_committer = sum(1 for x in active_rows if x["family_how"] == "committer")
    not_placed = len(active_rows) - by_inventory - by_committer
    notes.append(f"For information: {by_inventory} of {len(active_rows)} active repos placed by the app inventory; "
                 f"{by_committer} by committer; {not_placed} not placed")
    if ties:
        notes.append(f"{len(ties)} {'repo is' if len(ties) == 1 else 'repos are'} linked to apps in different teams with "
                     f"no team having the most, so the committer rule was used: {', '.join(ties[:8])}"
                     f"{f', and {len(ties) - 8} more' if len(ties) > 8 else ''}")
    unmatched = [x["repo"] for x in rows if x["active"] and x["family_id"] == UNMATCHED]
    if unmatched:
        no_email = sum(1 for x in rows if x["active"] and x["family_id"] == UNMATCHED and not x["owner_email"])
        how = "by email address" if match_by == "email" else "by email address or login"
        notes.append(f"{len(unmatched)} active {'repo has' if len(unmatched) == 1 else 'repos have'} an owner TRUST "
                     f"couldn't match to HR {how}"
                     f"{f' ({no_email} with no human committer or no email)' if no_email else ''}, so "
                     f"{'it is' if len(unmatched) == 1 else 'they are'} Not yet mapped: {', '.join(unmatched[:8])}"
                     f"{f', and {len(unmatched) - 8} more' if len(unmatched) > 8 else ''}")
    big = s.get("repo_owner_flag_count")
    big = big if isinstance(big, int) and not isinstance(big, bool) and big > 0 else 20
    for sam, repos in sorted(owners.items()):
        if len(repos) >= big:
            notes.append(f"{sam} is the owner of {len(repos)} active repos; check this person really owns them "
                         "(a bulk change can make one person the last committer everywhere)")
    inactive = {}
    for x in rows:
        if not x["active"]:
            inactive[x["inactive_reason"]] = inactive.get(x["inactive_reason"], 0) + 1
    return dict(families=families, unmatched_active=len(unmatched), owner_rule=rule, match_by=match_by, active_days=days,
                active=sum(x["active"] for x in rows), inactive=inactive, notes=notes,
                placed_by_inventory=by_inventory, placed_by_committer=by_committer, not_placed=not_placed)


# ---- Checkmarx repos tied to GitHub repos (owner, 4 Nov 2026) ----
# A Checkmarx repo takes the family of the GitHub repo it matches. Checkmarx names are often
# "leading/reponame" while GitHub's are "org/repo" or just "repo", so the match is tried in order:
#   1. the same full name;                      2. the same repo name (the part after the last "/");
#   3. a close spelling of the repo name, scored 0 to 1, at least checkmarx_match_min (setting, 0.9), and
#      with the same numbers in it ('service2' is never 'service' or 'service3').
# A repo name shared by several GitHub repos (same name in two orgs) is matched on the leading part if
# that settles it; otherwise it is left unmatched and listed, never guessed. Every close match is
# listed with its score so it can be checked.

CX_MATCH_MIN = 0.9


def checkmarx_match_min(settings):
    v = (settings or {}).get("checkmarx_match_min")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 <= v <= 1 else CX_MATCH_MIN


def _repo_path(name):
    """A repo name tidied for matching: lower case, no web address, no '.git', no spare slashes."""
    s = str(name or "").strip().lower()
    s = re.sub(r"^[a-z]+://[^/]+/", "", s)          # https://github.example.com/org/repo -> org/repo
    s = re.sub(r"\.git$", "", s).strip("/")
    return "/".join(p for p in re.split(r"[/\\]+", s) if p)


def _tail(path):
    return path.rsplit("/", 1)[-1]


_ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"


def _letter_counts(key):
    return tuple(key.count(c) for c in _ALNUM)


class _Shortlist:
    """The GitHub repo names that could score close enough to a Checkmarx name, found without scoring them all.

    Speed only (owner, 4 Nov 2026: mapping took minutes with thousands of repos); the matches are exactly the
    same. A close-spelling score can't be higher than 2 x (letters the two names share) / (their total length),
    for the name as written and with its words reordered alike (both use the same letters). A name that can't
    reach min_score - 0.02 can neither win nor be "too close to call" with the winner, so it's skipped.
    Names must also have the same numbers in them, as before."""

    def __init__(self, by_tail, min_score):
        self.floor = min_score - 0.02 - 1e-9
        self.by_len = {}
        for t in by_tail:
            key = norm(t)
            self.by_len.setdefault(len(key), []).append((t, tuple(re.findall(r"\d+", t)), _letter_counts(key)))

    def for_name(self, name):
        key, digits, f = norm(name), tuple(re.findall(r"\d+", name)), self.floor
        n, mine = len(key), _letter_counts(key)
        for m, names in self.by_len.items():
            if n + m and 2 * min(n, m) / (n + m) < f:                # lengths alone too far apart
                continue
            need = f * (n + m) / 2                                   # letters the two must share
            for t, d, theirs in names:
                if d == digits and (not n + m or sum(map(min, mine, theirs)) >= need):
                    yield t


def match_checkmarx(cx_rows, gh_rows, min_score=CX_MATCH_MIN, what="Checkmarx", setting="checkmarx_match_min"):
    """Give each Checkmarx row the family of its GitHub repo. Sets on each cx row: gh_repo, matched_by,
    match_score, family_id. Returns dict(counts, unmatched, fuzzy, notes). The app inventory's service repos
    use the same matching (owner, 6 Nov 2026): what and setting only change the wording of the notes."""
    from .common import similarity
    full, by_tail, paths = {}, {}, {}
    for g in gh_rows:
        p = _repo_path(g["repo"])
        full[p] = g
        by_tail.setdefault(_tail(p), []).append(g)
        paths[id(g)] = p                                 # tidied once (speed)
    shortlist = _Shortlist(by_tail, min_score)
    counts = {"exact": 0, "repo name": 0, "close spelling": 0, "not matched": 0}
    unmatched, fuzzy, shared, not_placed, shared_keys = [], [], [], [], set()
    for x in cx_rows:
        p = _repo_path(x["key"])
        g, how, score = None, None, None
        if p in full:
            g, how = full[p], "exact"
        elif len(by_tail.get(_tail(p), [])) == 1:
            g, how = by_tail[_tail(p)][0], "repo name"
        elif len(by_tail.get(_tail(p), [])) > 1:
            lead = p.rsplit("/", 1)[0] if "/" in p else ""
            hits = [c for c in by_tail[_tail(p)] if lead and lead in paths[id(c)]]
            if len(hits) == 1:
                g, how = hits[0], "repo name"
            else:
                shared.append(x["key"])
                shared_keys.add(x["key"])
        else:
            ranked = sorted(((similarity(_tail(p), t), t) for t in shortlist.for_name(_tail(p))), reverse=True)
            if ranked and ranked[0][0] >= min_score:
                best, t = ranked[0]
                close = len(ranked) > 1 and best - ranked[1][0] < 0.02
                if len(by_tail[t]) == 1 and not close:
                    g, how, score = by_tail[t][0], "close spelling", round(best, 2)
                    fuzzy.append(f"{x['key']} -> {g['repo']} ({score:.2f})")
                else:
                    shared.append(x["key"])
                    shared_keys.add(x["key"])
        if g is None:
            counts["not matched"] += 1
            if x["key"] not in shared_keys:
                unmatched.append(x["key"])
            x.update(gh_repo=None, matched_by=None, match_score=None, family_id=UNMATCHED)
            continue
        counts[how] += 1
        fam = g.get("family_id") or UNMATCHED
        if fam == UNMATCHED:
            not_placed.append(x["key"])
        x.update(gh_repo=g["repo"], matched_by=how, match_score=score, family_id=fam)

    show = lambda names: ", ".join(names[:8]) + (f", and {len(names) - 8} more" if len(names) > 8 else "")
    n = len(cx_rows)
    matched = n - counts["not matched"]
    notes = [f"{matched} of {n} {what} {'repo' if n == 1 else 'repos'} matched to a GitHub repo "
             f"({counts['exact']} same name, {counts['repo name']} same repo name, "
             f"{counts['close spelling']} close spelling)"]
    if fuzzy:
        notes.append(f"Close spellings, check these (setting {setting} {min_score}): {show(fuzzy)}")
    if unmatched:
        notes.append(f"{len(unmatched)} {what} {'repo has' if len(unmatched) == 1 else 'repos have'} no matching "
                     f"GitHub repo, so {'it is' if len(unmatched) == 1 else 'they are'} Not yet mapped: {show(unmatched)}")
    if shared:
        notes.append(f"{len(shared)} {what} {'repo matches' if len(shared) == 1 else 'repos match'} more than one "
                     f"GitHub repo equally well, so not matched (never guessed): {show(shared)}")
    if not_placed:
        notes.append(f"{len(not_placed)} matched {'repo has' if len(not_placed) == 1 else 'repos have'} a GitHub owner "
                     f"TRUST couldn't place with an L3 team, so Not yet mapped: {show(not_placed)}")
    return dict(counts=counts, matched=matched, total=n, unmatched=unmatched, fuzzy=fuzzy, shared=shared,
                not_placed=not_placed, notes=notes)
