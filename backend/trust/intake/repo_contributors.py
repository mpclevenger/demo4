"""Read the repo contributors file on its own (feed "repo_contributors"; owner, 16 Nov 2026).

One row per repository, month and contributor: how many commits that person made to that repo in that month.
It feeds the Risk site's driver "Multiple teams contributing" (backend/trust/risk/data_drivers.py). Nothing
here is scored.

    Repository         the repo, the same name the GitHub repos file uses
    Month              the month the commits were made, like 2026-10
    Contributor login  the GitHub login (kept to show; never used to find the person)
    Contributor email  the commit email, matched to the person's HR work email (owner, 16 Nov 2026: by email only)
    Commits            how many commits that person made to that repo in that month

Who a contributor is, and which team they are in, is worked out later from HR (data_drivers.py). This reader
only cleans the rows. A row with no repo is set aside and listed. A row with no email is kept: its contributor
is later counted as "not matched", never guessed.
"""
import re

from .common import column_map, map_columns, parse_when, read_table

FIELDS = {f: (f,) for f in ("Repository", "Month", "Contributor login", "Contributor email", "Commits")}
NEEDED = ("Repository", "Month", "Commits")


def month_of(text):
    """'2026-10', '10/2026', 'October 2026' or any full date gives '2026-10'. None when it isn't a month."""
    text = str(text or "").strip()
    if not text:
        return None
    year_first = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
    if year_first:
        year, month = int(year_first.group(1)), int(year_first.group(2))
        return f"{year}-{month:02d}" if 1 <= month <= 12 else None
    month_first = re.fullmatch(r"(\d{1,2})[-/](\d{4})", text)
    if month_first:
        month, year = int(month_first.group(1)), int(month_first.group(2))
        return f"{year}-{month:02d}" if 1 <= month <= 12 else None
    when = parse_when(f"1 {text}") if re.fullmatch(r"[A-Za-z]+\.?\s+\d{4}", text) else parse_when(text)
    return when.isoformat()[:7] if when else None


def _count(text):
    digits = re.sub(r"[,\s]", "", str(text or ""))
    return int(float(digits)) if re.fullmatch(r"\d+(\.0+)?", digits) else None


def read(raw_bytes):
    """Returns dict(rows, set_aside, notes, summary). Each row: repo, month, login, email, commits."""
    notes, set_aside, rows, seen = [], [], [], set()
    cmap = column_map("repo_contributors", FIELDS)
    headers, table = read_table(raw_bytes, 1, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()
    missing = [f for f in NEEDED if col[f] is None]
    if missing:
        notes.append(f"No column for {', '.join(missing)}: the drivers that need it show 'not known'")
    if col["Contributor email"] is None:
        notes.append("No column for the contributor's email: nobody can be matched to a person in HR, so the "
                     "'Multiple teams contributing' driver shows 'not known'")

    bad_months, bad_counts = [], []
    for i, r in enumerate(table, start=2):
        repo = g(r, "Repository")
        login = g(r, "Contributor login").lower()
        email = g(r, "Contributor email").lower()
        if not repo:
            set_aside.append(dict(row=i, reason="no Repository"))
            continue
        if not (login or email):
            set_aside.append(dict(row=i, reason=f"no contributor for '{repo}'"))
            continue
        month = month_of(g(r, "Month"))
        if g(r, "Month") and month is None:
            bad_months.append(repo)
        commits = _count(g(r, "Commits"))
        if g(r, "Commits") and commits is None:
            bad_counts.append(repo)
        key = (repo.lower(), month, login or email)
        if key in seen:
            set_aside.append(dict(row=i, reason=f"'{login or email}' is on more than one row for '{repo}' in {month or 'no month'}; first kept"))
            continue
        seen.add(key)
        rows.append({"repo": repo, "month": month, "login": login or None, "email": email or None,
                     "commits": commits if commits is not None else 0})

    show = lambda names: ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    if bad_months:
        notes.append(f"Month isn't a month for {len(bad_months)} {'row' if len(bad_months) == 1 else 'rows'} ({show(bad_months)}); "
                     "those rows are counted for no month")
    if bad_counts:
        notes.append(f"Commits isn't a number for {len(bad_counts)} {'row' if len(bad_counts) == 1 else 'rows'} ({show(bad_counts)}); counted as 0")
    summary = dict(rows=len(rows), repos=len({x["repo"].lower() for x in rows}),
                   contributors=len({x["login"] or x["email"] for x in rows}),
                   months=sorted({x["month"] for x in rows if x["month"]}), set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)
