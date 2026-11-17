"""Links from each metric's dictionary card to the code that measures and scores it (owner, 5 Nov 2026).

Setting `code_repo_url` in config/settings.json is the repo's web address on GitHub (or GitHub Enterprise
Server), e.g. https://github.example.com/tech-risk/trust. With it set, publish adds `code_links` to the page
data: for every metric, the file, function and real line numbers of the code behind it, and a link of the form
<repo>/blob/<commit>/backend/trust/measure.py#L66-L81 that GitHub opens with those lines highlighted. Line
numbers are read from the source that is running (Python's ast), so they can't go stale; the commit is the
platform's build commit when it is known (TRUST_GIT_SHA or SOURCE_VERSION), else `main` (setting `code_ref`).
Without the setting the same places still show, as plain text, and `url` is None (owner, 16 Nov 2026).
"""
import ast

from . import config, storage

# Shared steps (thresholds, statuses, block and TRUST maths) are linked on every card after the metric's own.
SHARED = [("score_month.py", "thresholds_for", "Tolerance thresholds: policy or prevailing median"),
          ("score_month.py", "status_of", "Green, Amber or Red from the result and thresholds"),
          ("scoring.py", "score_block", "Building block score from its metrics, with caps"),
          ("scoring.py", "score_family", "TRUST from the building blocks")]


def metric_code():
    """What to link for each metric: {metric id: [(file under backend/trust/, function, what it does in plain words
    [, marker])]}, from counting.code in config/metrics.json, read each time so an edit shows without a restart."""
    return {mid: [tuple(c[k] for k in ("file", "function", "what", "find") if c.get(k)) for c in x["counting"]["code"]]
            for mid, x in config.metrics().items() if (x.get("counting") or {}).get("code")}


def _lines(file, func, marker=None):
    """(first, last) line of a top-level function in backend/trust/<file>, or None if it isn't there.
    With a marker (a piece of code text), the lines from the marker's first line inside that function to the
    end of that statement (5 lines at most), so the link lands on the rule rather than the whole function."""
    path = config.ROOT / "backend" / "trust" / file
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            if not marker:
                return node.lineno, node.end_lineno
            lines = text.splitlines()
            for n in range(node.lineno, node.end_lineno + 1):
                if marker in lines[n - 1]:
                    return n, min(n + 4, node.end_lineno)
            return node.lineno, node.end_lineno
    return None


def repo_url():
    return (config.settings().get("code_repo_url") or "").strip().rstrip("/")


def ref():
    return storage.git_sha() or (config.settings().get("code_ref") or "main").strip() or "main"


def place(file, function, what, marker=None):
    """One place in the code, ready for a page: {file, function, what, from, to, url}, or None when the function
    isn't in backend/trust/<file>. `url` is filled only when the repo address is set; else the page shows plain text.
    Example: place("risk/rating.py", "is_applicable", "Whether the risk applies to the team")."""
    lines = _lines(file, function, marker)
    if not lines:
        return None
    base, path = repo_url(), f"backend/trust/{file}"
    return {"file": path, "function": function, "what": what, "from": lines[0], "to": lines[1],
            "url": f"{base}/blob/{ref()}/{path}#L{lines[0]}-L{lines[1]}" if base else None}


def links():
    """{metric id: [{file, function, what, from, to, url}]} for the page. The places always show; `url` is
    filled only when a repo address is set, else it is None and the page shows plain text."""
    out = {}
    for mid, places in metric_code().items():
        rows = [place(file, func, what, marker[0] if marker else None) for file, func, what, *marker in places + SHARED]
        out[mid] = [row for row in rows if row]
    return {"ref": ref(), "repo": repo_url() or None, "metrics": out}


# The reading function of each data feed (file under backend/trust/, function). One reader per feed.
FEED_READERS = {"hr": ("intake/hr.py", "read"), "cx_sast": ("intake/checkmarx.py", "read"), "cx_sca": ("intake/checkmarx.py", "read"),
                "tcc": ("intake/tcc.py", "read"), "ntcc": ("intake/ntcc.py", "read"),
                "postmortems": ("intake/postmortems.py", "read"), "actions": ("intake/actions.py", "read"),
                "itdr": ("intake/itdr.py", "read"), "dr_tests": ("intake/dr_tests.py", "read"),
                "repos": ("intake/repos.py", "read"), "repo_contributors": ("intake/repo_contributors.py", "read"),
                "defects": ("intake/defects.py", "read"), "app_inventory": ("intake/app_inventory.py", "read"),
                "app_owner_members": ("intake/owner_groups.py", "read")}


def page_places():
    """Places in the code that pages explain in words (owner, 16 Nov 2026): {watch_list: [place], feed_readers:
    {feed id: place}, upload_checks: [place], mapping: [place]}, each place as place() gives it. A function that
    has been renamed is left out here, and tests/test_codelinks.py fails until the list is fixed."""
    def listed(rows):
        return [p for p in (place(*row) for row in rows) if p]
    watch_list = listed([
        ("publish.py", "_watch", "Which items the watch list gets: Red rules, new and chronic Red, sharp drops, declining blocks, Behind peers"),
        ("publish.py", "build", "Trend: this month's change in TRUST and in each building block, and each metric's recent statuses", "fr[\"delta\"]"),
        ("publish.py", "_blocks_scored", "How many building blocks a month's TRUST rests on (trend rules need enough of them)"),
        ("score_month.py", "flag_behind_peers", "Typical L3 team and the Behind peers flag for each metric"),
    ])
    readers = {feed: place(file, func, "Reads this file") for feed, (file, func) in FEED_READERS.items()}
    return {"watch_list": watch_list,
            "feed_readers": {feed: row for feed, row in readers.items() if row},
            "upload_checks": listed([
                ("checks.py", "check_upload", "Checks every upload: readable, right file, columns, rows set aside, no rows"),
                ("feeds.py", "fields_needed", "The columns TRUST needs from each file, which the checks compare against")]),
            "mapping": listed([("mapping.py", "map_month", "Places people, repos, apps and rows into L3 teams for the month")])}
