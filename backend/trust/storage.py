"""Where TRUST keeps things: the database add-on when DATABASE_URL is set, otherwise the store/ folder.

On the platform the app's own disk is wiped on every restart and isn't shared between the website and
one-off commands, so everything kept (the cut-down files, the upload register, the mapped and scored
months and the published page) goes in Postgres. Locally and in tests, with no DATABASE_URL, it goes
in the folder named by TRUST_STORE_DIR (default ./store), exactly as before.

Everything else in TRUST goes through these few functions, so it doesn't care which one is in use.
"""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import threading

from . import config

# Rows kept in files (no database) are added one writer at a time, so two requests never take the same id.
_line_lock = threading.RLock()


def database_url():
    """The add-on's connection string (DATABASE_URL), or TRUST_DATABASE_URL for local use."""
    return os.environ.get("DATABASE_URL") or os.environ.get("TRUST_DATABASE_URL") or None


def using_database():
    return database_url() is not None


def store_dir():
    return pathlib.Path(os.environ.get("TRUST_STORE_DIR", "store"))


def connect():
    import psycopg                      # only needed when the database is in use
    return psycopg.connect(database_url(), autocommit=True)


def _jsonb(value):
    """A value wrapped to be saved in a jsonb column."""
    from psycopg.types.json import Jsonb        # only needed when the database is in use
    return Jsonb(value)


# ---- the upload register (one list per feed and month, newest last) and the kept files ----

def register(month, feed):
    if using_database():
        with connect() as c:
            rows = c.execute("SELECT entry FROM submission WHERE month = %s AND feed = %s ORDER BY id",
                             (month, feed)).fetchall()
        return [r[0] for r in rows]
    path = store_dir() / "uploads" / month / feed / "register.json"
    return json.loads(path.read_text()) if path.exists() else []


def add_upload(month, feed, entry, file_bytes):
    """Keep the cut-down file and add its entry to the register."""
    if using_database():
        with connect() as c, c.transaction():
            c.execute("INSERT INTO kept_file (sha256, content) VALUES (%s, %s) ON CONFLICT (sha256) DO NOTHING",
                      (entry["sha256"], file_bytes))
            c.execute("INSERT INTO submission (month, feed, entry) VALUES (%s, %s, %s)", (month, feed, _jsonb(entry)))
        return
    folder = store_dir() / "uploads" / month / feed
    folder.mkdir(parents=True, exist_ok=True)
    (folder / entry["file"]).write_bytes(file_bytes)
    reg = register(month, feed)
    reg.append(entry)
    (folder / "register.json").write_text(json.dumps(reg, indent=2))


def kept_file(month, feed, entry):
    """The cut-down file kept for an upload (its register entry)."""
    if using_database():
        with connect() as c:
            row = c.execute("SELECT content FROM kept_file WHERE sha256 = %s", (entry["sha256"],)).fetchone()
        return bytes(row[0]) if row else None
    return (store_dir() / "uploads" / month / feed / entry["file"]).read_bytes()


# ---- mapped and scored months (every run kept; the newest is current) ----

def git_sha():
    """The commit of the running code: TRUST_GIT_SHA, the platform's SOURCE_VERSION, or git itself."""
    sha = os.environ.get("TRUST_GIT_SHA") or os.environ.get("SOURCE_VERSION")
    if sha:
        return sha
    try:
        out = subprocess.run(["git", "-C", str(config.ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def settings_sha256():
    """One hash over the settings, thresholds and column maps in use, so a run says which version it used."""
    h = hashlib.sha256()
    for variable, name in (("TRUST_SETTINGS", "settings.json"), ("TRUST_THRESHOLDS", "thresholds.json"),
                           ("TRUST_COLUMN_MAPS", "column_maps.json")):
        path = config.config_file(variable, name)
        h.update(name.encode() + b"\0" + (path.read_bytes() if path.exists() else b"") + b"\0")
    # thresholds and caps changed on the site (owner, 15 Nov 2026) are part of the version too
    edits = [[c["path"], c["after"]] for c in setting_changes()]
    if edits:
        h.update(b"setting_change\0" + json.dumps(edits, sort_keys=True).encode() + b"\0")
    return h.hexdigest()


def save_month(kind, month, doc, by="command line"):
    """kind is 'mapped' or 'scored'. Adds a run; the newest is the current one."""
    text = json.dumps(doc, indent=2, default=str)       # default=str writes dates as text (Jsonb() alone would refuse them)
    if using_database():
        with connect() as c:
            c.execute("""INSERT INTO month_result (kind, month, doc, by, git_sha, settings_sha256)
                         VALUES (%s, %s, %s::jsonb, %s, %s, %s)""",
                      (kind, month, text, by, git_sha(), settings_sha256()))
        return
    path = store_dir() / kind / f"{month}.json"         # the folder keeps only the newest run
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    (path.parent / f"{month}.run").write_text(json.dumps(
        {"by": by, "at": _now(), "git_sha": git_sha(), "settings_sha256": settings_sha256()}))


def run_info(kind, month):
    """Who ran the newest mapping or scoring of a month, when, and with which code and settings (or None)."""
    if using_database():
        with connect() as c:
            r = c.execute("""SELECT by, run_at, git_sha, settings_sha256 FROM month_result
                             WHERE kind = %s AND month = %s ORDER BY id DESC LIMIT 1""", (kind, month)).fetchone()
        return {"by": r[0], "at": r[1].isoformat(), "git_sha": r[2], "settings_sha256": r[3]} if r else None
    path = store_dir() / kind / f"{month}.run"
    return json.loads(path.read_text()) if path.exists() else None


def load_month(kind, month):
    """The newest run's document, or None if that month hasn't been mapped/scored."""
    if using_database():
        with connect() as c:
            row = c.execute("SELECT doc FROM month_result WHERE kind = %s AND month = %s ORDER BY id DESC LIMIT 1",
                            (kind, month)).fetchone()
        return row[0] if row else None
    path = store_dir() / kind / f"{month}.json"
    return json.loads(path.read_text()) if path.exists() else None


def months(kind):
    if using_database():
        with connect() as c:
            rows = c.execute("SELECT DISTINCT month FROM month_result WHERE kind = %s ORDER BY month",
                             (kind,)).fetchall()
        return [r[0] for r in rows]
    folder = store_dir() / kind
    return sorted(p.stem for p in folder.glob("*.json")) if folder.exists() else []


def upload_months():
    """Every month that has at least one stored upload (refused files are never stored), oldest first."""
    if using_database():
        with connect() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT month FROM submission ORDER BY month").fetchall()]
    folder = store_dir() / "uploads"
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and any(p.iterdir())) if folder.exists() else []


# ---- month status (open or locked) ----

def _jsonl(name):
    return store_dir() / name


def _read_lines(name):
    """The rows kept in one of the store folder's .jsonl files, oldest first ([] when there is no file yet)."""
    path = _jsonl(name)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_line(name, row):
    """Add one row to the end of a .jsonl file."""
    path = _jsonl(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _rewrite_lines(name, rows):
    """Replace the rows of a .jsonl file with these."""
    _jsonl(name).write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
                            encoding="utf-8")


def _append_numbered_line(name, row):
    """Add a row to a .jsonl file with the next id and the time. Returns the row as kept."""
    with _line_lock:
        kept = {**row, "id": len(_read_lines(name)) + 1, "at": _now()}
        _append_line(name, kept)
    return kept


def month_status(month):
    """{status, locked_by, locked_at, seal}. A month never locked is open."""
    blank = {"status": "open", "locked_by": None, "locked_at": None, "seal": None}
    if using_database():
        with connect() as c:
            row = c.execute("SELECT status, locked_by, locked_at, seal FROM month WHERE month = %s",
                            (month,)).fetchone()
        if not row:
            return blank
        return {"status": row[0], "locked_by": row[1], "locked_at": row[2].isoformat() if row[2] else None,
                "seal": row[3]}
    path = store_dir() / "months.json"
    return {**blank, **(json.loads(path.read_text()).get(month, {}) if path.exists() else {})}


def set_month_status(month, status, locked_by=None, locked_at=None, seal=None):
    if using_database():
        with connect() as c:
            c.execute("""INSERT INTO month (month, status, locked_by, locked_at, seal) VALUES (%s, %s, %s, %s, %s)
                         ON CONFLICT (month) DO UPDATE SET status = EXCLUDED.status, locked_by = EXCLUDED.locked_by,
                             locked_at = EXCLUDED.locked_at, seal = EXCLUDED.seal, updated_at = now()""",
                      (month, status, locked_by, locked_at, _jsonb(seal) if seal is not None else None))
        return
    path = store_dir() / "months.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    allm = json.loads(path.read_text()) if path.exists() else {}
    allm[month] = {"status": status, "locked_by": locked_by, "locked_at": locked_at, "seal": seal}
    path.write_text(json.dumps(allm, indent=2))


def ensure_open(month):
    """Refuse a change to a locked month, in plain words."""
    st = month_status(month)
    if st["status"] == "locked":
        raise ValueError(f"{month} is locked (by {st['locked_by']}), so it can't be changed. "
                         "Reopen it on the Tech Risk console first, with a reason.")


# ---- the event log (one line per action, never edited) ----

def log(action, by, month=None, note="", detail=None):
    if using_database():
        with connect() as c:
            c.execute("INSERT INTO event_log (month, action, by, note, detail) VALUES (%s, %s, %s, %s, %s)",
                      (month, action, by, note, _jsonb(detail) if detail is not None else None))
        return
    _append_line("events.jsonl", {"at": _now(), "month": month, "action": action, "by": by, "note": note,
                                  "detail": detail})


def events(month=None, limit=200):
    """Newest first."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT at, month, action, by, note, detail FROM event_log
                                WHERE %s::text IS NULL OR month = %s OR month IS NULL
                                ORDER BY id DESC LIMIT %s""", (month, month, limit)).fetchall()
        return [{"at": r[0].isoformat(), "month": r[1], "action": r[2], "by": r[3], "note": r[4], "detail": r[5]}
                for r in rows]
    rows = [r for r in _read_lines("events.jsonl") if month is None or r["month"] in (month, None)]
    return rows[::-1][:limit]


# ---- comments (never edited; a reply is a new row) ----

COMMENT_FIELDS = ("month", "family", "metric", "block", "kind", "text", "by", "reply_to", "status", "after_lock")


def add_comment(new_comment):
    """new_comment has COMMENT_FIELDS. Returns the stored comment with its id and time."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO comment (month, family, metric, block, kind, text, by, reply_to, status,
                                   after_lock) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            tuple(new_comment[k] for k in COMMENT_FIELDS)).fetchone()
        return {**new_comment, "id": row[0], "at": row[1].isoformat()}
    return _append_numbered_line("comments.jsonl", new_comment)


def comments(month):
    """Every comment for a month, oldest first."""
    if using_database():
        with connect() as c:
            rows = c.execute(f"""SELECT id, at, {", ".join(COMMENT_FIELDS)} FROM comment WHERE month = %s ORDER BY id""",
                             (month,)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), **dict(zip(COMMENT_FIELDS, r[2:]))} for r in rows]
    return [r for r in _read_lines("comments.jsonl") if r["month"] == month]


def comment(cid):
    if using_database():
        with connect() as c:
            r = c.execute(f"SELECT id, at, {', '.join(COMMENT_FIELDS)} FROM comment WHERE id = %s", (cid,)).fetchone()
        return {"id": r[0], "at": r[1].isoformat(), **dict(zip(COMMENT_FIELDS, r[2:]))} if r else None
    return next((r for r in _read_lines("comments.jsonl") if r["id"] == cid), None)


# ---- warning acknowledgements (never edited) ----

def add_ack(month, feed, note_key, note, by, reason=""):
    if using_database():
        with connect() as c:
            c.execute("INSERT INTO warning_ack (month, feed, note_key, note, by, reason) VALUES (%s, %s, %s, %s, %s, %s)",
                      (month, feed, note_key, note, by, reason))
        return
    _append_line("acks.jsonl", {"month": month, "feed": feed, "note_key": note_key, "note": note, "by": by,
                                "at": _now(), "reason": reason})


def acks(month):
    """{note_key: the first acknowledgement} for a month."""
    if using_database():
        with connect() as c:
            rows = c.execute("SELECT note_key, by, at, reason FROM warning_ack WHERE month = %s ORDER BY id",
                             (month,)).fetchall()
        rows = [{"note_key": r[0], "by": r[1], "at": r[2].isoformat(), "reason": r[3]} for r in rows]
    else:
        rows = [r for r in _read_lines("acks.jsonl") if r["month"] == month]
    out = {}
    for r in rows:
        out.setdefault(r["note_key"], {k: r[k] for k in ("by", "at", "reason")})
    return out


# ---- dictionary proposals and decisions (never edited; a decision is a new row) ----

def _with_status(p, decs):
    return {**p, "decisions": decs, "status": decs[-1]["decision"] if decs else "open"}


def add_proposal(p):
    """p has kind, metric, title, detail, by. Returns the stored proposal with its id and time."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO proposal (kind, metric, title, detail, by) VALUES (%s, %s, %s, %s, %s)
                               RETURNING id, at""",
                            (p["kind"], p["metric"], p["title"], _jsonb(p["detail"]), p["by"])).fetchone()
        return {**p, "id": row[0], "at": row[1].isoformat()}
    return _append_numbered_line("proposals.jsonl", p)


def add_decision(d):
    """d has proposal_id, decision, reason, by. Returns the stored decision with its id and time."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO proposal_decision (proposal_id, decision, reason, by)
                               VALUES (%s, %s, %s, %s) RETURNING id, at""",
                            (d["proposal_id"], d["decision"], d["reason"], d["by"])).fetchone()
        return {**d, "id": row[0], "at": row[1].isoformat()}
    return _append_numbered_line("decisions.jsonl", d)


def _all_proposals():
    """(proposals oldest first, decisions oldest first)."""
    if using_database():
        with connect() as c:
            ps = c.execute("SELECT id, at, kind, metric, title, detail, by FROM proposal ORDER BY id").fetchall()
            ds = c.execute("SELECT id, at, proposal_id, decision, reason, by FROM proposal_decision ORDER BY id").fetchall()
        return ([{"id": r[0], "at": r[1].isoformat(), "kind": r[2], "metric": r[3], "title": r[4], "detail": r[5],
                  "by": r[6]} for r in ps],
                [{"id": r[0], "at": r[1].isoformat(), "proposal_id": r[2], "decision": r[3], "reason": r[4],
                  "by": r[5]} for r in ds])
    return _read_lines("proposals.jsonl"), _read_lines("decisions.jsonl")


def proposals():
    """Every proposal, newest first, each with its status and its decisions (oldest first)."""
    ps, ds = _all_proposals()
    return [_with_status(p, [d for d in ds if d["proposal_id"] == p["id"]]) for p in reversed(ps)]


def proposal(pid):
    return next((p for p in proposals() if p["id"] == pid), None)


# ---- requests that someone decides: data contracts and Lost and Found claims ----
# A request is never edited; the decision is filled in on it (once for a contract, once or twice for a claim).
# Both kinds are kept the same way, so one pair of helpers reads and decides them.

def _request_rows(table, fields, file_name):
    """Every request of one kind, oldest first, each with its decision (status, decided_by, decided_at, reason)."""
    if using_database():
        with connect() as c:
            rows = c.execute(f"""SELECT id, at, {", ".join(fields)}, status, decided_by, decided_at, reason
                                 FROM {table} ORDER BY id""").fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), **dict(zip(fields, r[2:2 + len(fields)])),
                 "status": r[-4], "decided_by": r[-3], "decided_at": r[-2].isoformat() if r[-2] else None,
                 "reason": r[-1]} for r in rows]
    return _read_lines(file_name)


def _add_request_in_file(file_name, request):
    """Without the database: keep a new request, waiting for a decision (status draft). Returns it as kept."""
    return _append_numbered_line(file_name, {**request, "status": "draft", "decided_by": None, "decided_at": None,
                                             "reason": ""})


def _decide_request_in_file(file_name, request_id, may_move_from, status, by, reason):
    """Without the database: fill in the decision on a request whose status allows it. Returns it, or None."""
    rows = _read_lines(file_name)
    for row in rows:
        if row["id"] == request_id and row["status"] in may_move_from:
            row.update(status=status, decided_by=by, decided_at=_now(), reason=reason)
            _rewrite_lines(file_name, rows)
            return row
    return None


# ---- data contracts (owner, 4 Nov 2026) ----

CONTRACT_FIELDS = ("feed", "version", "provider", "contact", "what", "cadence", "columns", "metrics", "note", "by")


def add_contract(new_contract):
    """new_contract has CONTRACT_FIELDS. Returns the stored request (status draft) with its id and time."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO data_contract (feed, version, provider, contact, what, cadence, columns,
                                   metrics, note, by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            (new_contract["feed"], new_contract["version"], new_contract["provider"],
                             new_contract["contact"], new_contract["what"], new_contract["cadence"],
                             _jsonb(new_contract["columns"]), _jsonb(new_contract["metrics"]), new_contract["note"],
                             new_contract["by"])).fetchone()
        return {**new_contract, "id": row[0], "at": row[1].isoformat(), "status": "draft", "decided_by": None,
                "decided_at": None, "reason": ""}
    return _add_request_in_file("contracts.jsonl", new_contract)


def decide_contract(cid, status, by, reason=""):
    """Fill in the decision on a draft: approved, returned or withdrawn. Returns the contract, or None."""
    if using_database():
        with connect() as c:
            row = c.execute("""UPDATE data_contract SET status = %s, decided_by = %s, decided_at = now(), reason = %s
                               WHERE id = %s AND status = 'draft' RETURNING id""", (status, by, reason, cid)).fetchone()
        return contract(cid) if row else None
    return _decide_request_in_file("contracts.jsonl", cid, ("draft",), status, by, reason)


def contracts():
    """Every data contract request, oldest first."""
    return _request_rows("data_contract", CONTRACT_FIELDS, "contracts.jsonl")


def contract(cid):
    return next((c for c in contracts() if c["id"] == cid), None)


def approved_contracts():
    """The current (highest approved version) contract per feed: {feed: contract}."""
    out = {}
    for c in contracts():
        if c["status"] == "approved" and (c["feed"] not in out or c["version"] > out[c["feed"]]["version"]):
            out[c["feed"]] = c
    return out


# ---- Lost and Found claims (owner, 9 Nov 2026) ----

CLAIM_FIELDS = ("feed", "item", "label", "family_id", "month", "why", "by")
# which status a decision may move a claim from
CLAIM_MOVES = {"approved": ("draft",), "returned": ("draft",), "withdrawn": ("draft",), "released": ("approved",)}


def add_claim(new_claim):
    if using_database():
        with connect() as c:
            row = c.execute(f"""INSERT INTO claim ({", ".join(CLAIM_FIELDS)}) VALUES ({", ".join(["%s"] * len(CLAIM_FIELDS))})
                                RETURNING id, at""", tuple(new_claim[k] for k in CLAIM_FIELDS)).fetchone()
        return {**new_claim, "id": row[0], "at": row[1].isoformat(), "status": "draft", "decided_by": None,
                "decided_at": None, "reason": ""}
    return _add_request_in_file("claims.jsonl", new_claim)


def decide_claim(cid, status, by, reason=""):
    """approved / returned / withdrawn (from draft) or released (from approved). Returns the claim, or None."""
    may_move_from = CLAIM_MOVES[status]
    if using_database():
        with connect() as c:
            row = c.execute("""UPDATE claim SET status = %s, decided_by = %s, decided_at = now(), reason = %s
                               WHERE id = %s AND status = ANY(%s) RETURNING id""",
                            (status, by, reason, cid, list(may_move_from))).fetchone()
        return claim(cid) if row else None
    return _decide_request_in_file("claims.jsonl", cid, may_move_from, status, by, reason)


def claims():
    """Every claim, oldest first."""
    return _request_rows("claim", CLAIM_FIELDS, "claims.jsonl")


def claim(cid):
    return next((c for c in claims() if c["id"] == cid), None)


def doc_sha256(doc):
    """A fingerprint of a JSON document that doesn't depend on key order or spacing."""
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---- the published page (index.html, data.json, evidence.json) ----

PUBLISHED = ("index.html", "data.json", "evidence.json")


def save_published(files):
    """files: {name: text}. Returns where they went (a folder, or 'database')."""
    if using_database():
        with connect() as c, c.transaction():
            for name, body in files.items():
                c.execute("""INSERT INTO published_file (name, body) VALUES (%s, %s)
                             ON CONFLICT (name) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
                          (name, body))
        return "database"
    out = store_dir() / "published"
    out.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (out / name).write_text(body, encoding="utf-8")
    return out


def published(name):
    """The published file's text, or None if nothing has been published."""
    if name not in PUBLISHED:
        return None
    if using_database():
        with connect() as c:
            row = c.execute("SELECT body FROM published_file WHERE name = %s", (name,)).fetchone()
        return row[0] if row else None
    path = store_dir() / "published" / name
    return path.read_text(encoding="utf-8") if path.exists() else None


# ---- thresholds and caps changed on the site: the audit trail (owner, 15 Nov 2026) ----

def add_setting_changes(rows, by, reason):
    """Record one save: rows of (path, before, after). All or nothing. Never edited afterwards."""
    if using_database():
        with connect() as c, c.transaction():
            for path, before, after in rows:
                c.execute("INSERT INTO setting_change (by, path, before, after, reason) VALUES (%s, %s, %s, %s, %s)",
                          (by, path, _jsonb(before), _jsonb(after), reason))
        return
    with _line_lock:
        for path, before, after in rows:
            _append_numbered_line("setting_changes.jsonl", {"by": by, "path": path, "before": before,
                                                                    "after": after, "reason": reason})


def setting_changes():
    """Every change, oldest first: id, at, by, path, before, after, reason."""
    if using_database():
        with connect() as c:
            rs = c.execute("SELECT id, at, by, path, before, after, reason FROM setting_change ORDER BY id").fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "by": r[2], "path": r[3], "before": r[4], "after": r[5],
                 "reason": r[6]} for r in rs]
    return _read_lines("setting_changes.jsonl")


def old_setting_changes(before_iso):
    """Ids of audit-trail rows saved before a date that are safe to remove: never the newest row of a setting,
    because that row is the value in use (owner, 15 Nov 2026: the trail is kept 24 months like everything else)."""
    newest, old = {}, []
    for c in setting_changes():
        newest[c["path"]] = c["id"]
    for c in setting_changes():
        if c["at"] < before_iso and newest[c["path"]] != c["id"]:
            old.append(c["id"])
    return old


def remove_setting_changes(ids):
    if not ids:
        return
    if using_database():
        with connect() as c, c.transaction():
            c.execute("DELETE FROM setting_change WHERE id = ANY(%s)", (list(ids),))
        return
    _rewrite_lines("setting_changes.jsonl", [row for row in _read_lines("setting_changes.jsonl") if row["id"] not in set(ids)])


# ---- the things we measure and their links (owner, 15 Nov 2026; written by backend/trust/things.py) ----

THING_COLS = ("kind", "key", "name", "details")
LINK_COLS = ("from_kind", "from_key", "relation", "to_kind", "to_key", "how", "score")


def save_things(month, things, links):
    """Replace a month's things and links with these, all or nothing."""
    if using_database():
        with connect() as c, c.transaction():
            c.execute("DELETE FROM thing_link WHERE month = %s", (month,))
            c.execute("DELETE FROM thing WHERE month = %s", (month,))
            with c.cursor() as cur:
                cur.executemany("INSERT INTO thing (month, kind, key, name, details) VALUES (%s, %s, %s, %s, %s)",
                                [(month, k, key, name, _jsonb(d)) for k, key, name, d in things])
                cur.executemany("INSERT INTO thing_link (month, from_kind, from_key, relation, to_kind, to_key, how, score) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", [(month, *l) for l in links])
        return
    path = store_dir() / "things" / f"{month}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"things": [list(t) for t in things], "links": [list(l) for l in links]}))


def _things_file(month):
    path = store_dir() / "things" / f"{month}.json"
    return json.loads(path.read_text()) if path.exists() else {"things": [], "links": []}


def things(month, kind=None):
    """A month's things as dicts (kind, key, name, details), optionally one kind only, in key order."""
    if using_database():
        with connect() as c:
            got = c.execute("SELECT kind, key, name, details FROM thing WHERE month = %s ORDER BY kind, key", (month,)).fetchall()
    else:
        got = _things_file(month)["things"]
    return [dict(zip(THING_COLS, r)) for r in got if kind is None or r[0] == kind]


def thing_links(month):
    """A month's links as dicts (from_kind, from_key, relation, to_kind, to_key, how, score)."""
    if using_database():
        with connect() as c:
            got = c.execute("SELECT from_kind, from_key, relation, to_kind, to_key, how, score FROM thing_link "
                            "WHERE month = %s ORDER BY from_kind, from_key, relation, to_kind, to_key", (month,)).fetchall()
        got = [(*r[:6], float(r[6]) if r[6] is not None else None) for r in got]
    else:
        got = _things_file(month)["links"]
    return [dict(zip(LINK_COLS, r)) for r in got]


# ---- retention (D-86): remove a month's data, and old runs that aren't the newest ----

MONTH_TABLES = ("thing_link", "thing", "itdr_application", "dr_test", "warning_ack", "comment", "submission", "event_log", "month")


def month_footprint(month):
    """What the store holds for a month: {table_or_kind: count}. Used by the retention dry run."""
    out = {}
    if using_database():
        with connect() as c:
            for t in MONTH_TABLES:
                out["month_status" if t == "month" else t] = c.execute(
                    f"SELECT count(*) FROM {t} WHERE month = %s", (month,)).fetchone()[0]
            out["month_result"] = c.execute("SELECT count(*) FROM month_result WHERE month = %s",
                                            (month,)).fetchone()[0]
            out["kept_bytes"] = c.execute(
                """SELECT coalesce(sum(length(k.content)), 0) FROM kept_file k
                   WHERE k.sha256 IN (SELECT entry->>'sha256' FROM submission WHERE month = %s)
                     AND k.sha256 NOT IN (SELECT entry->>'sha256' FROM submission
                                          WHERE month <> %s AND entry->>'sha256' IS NOT NULL)""",
                (month, month)).fetchone()[0]
        return out
    up = store_dir() / "uploads" / month
    out["submission"] = sum(len(register(month, f.name)) for f in up.iterdir() if f.is_dir()) if up.exists() else 0
    out["kept_bytes"] = sum(p.stat().st_size for p in up.rglob("*") if p.is_file() and p.name != "register.json") if up.exists() else 0
    out["month_result"] = sum(1 for k in ("mapped", "scored") if (store_dir() / k / f"{month}.json").exists())
    for name, key in (("events.jsonl", "event_log"), ("comments.jsonl", "comment"), ("acks.jsonl", "warning_ack")):
        out[key] = sum(1 for row in _read_lines(name) if row.get("month") == month)
    out["month_status"] = 1 if (_jsonl("months.json").exists() and month in json.loads(_jsonl("months.json").read_text())) else 0
    return out


def remove_month(month):
    """Delete everything kept for one month (files, register, rows, results, comments, acknowledgements,
    activity and the lock record). A kept file is removed only when no other month uses it. All or nothing."""
    if using_database():
        with connect() as c, c.transaction():
            for t in MONTH_TABLES:
                c.execute(f"DELETE FROM {t} WHERE month = %s", (month,))
            c.execute("DELETE FROM month_result WHERE month = %s", (month,))
            # a NULL in a NOT IN list would make it match nothing, so leave out any upload without a hash
            c.execute("DELETE FROM kept_file WHERE sha256 NOT IN (SELECT entry->>'sha256' FROM submission "
                      "WHERE entry->>'sha256' IS NOT NULL)")
        return
    shutil.rmtree(store_dir() / "uploads" / month, ignore_errors=True)
    for k in ("mapped", "scored"):
        for ext in ("json", "run"):
            (store_dir() / k / f"{month}.{ext}").unlink(missing_ok=True)
    (store_dir() / "things" / f"{month}.json").unlink(missing_ok=True)
    for name in ("events.jsonl", "comments.jsonl", "acks.jsonl"):
        if _jsonl(name).exists():
            _rewrite_lines(name, [row for row in _read_lines(name) if row.get("month") != month])
    p = _jsonl("months.json")
    if p.exists():
        d = json.loads(p.read_text())
        if month in d:
            del d[month]
            p.write_text(json.dumps(d, indent=2))


def old_runs(grace_days):
    """Mapping and scoring runs that are not the newest of their month and are older than grace_days:
    [(kind, month, run_at)]. Without the database the folder only ever holds the newest run, so []."""
    if not using_database():
        return []
    with connect() as c:
        rows = c.execute(
            """SELECT r.kind, r.month, r.run_at FROM month_result r
               WHERE r.id < (SELECT max(id) FROM month_result n WHERE n.kind = r.kind AND n.month = r.month)
                 AND r.run_at < now() - make_interval(days => %s) ORDER BY r.month, r.kind, r.id""",
            (int(grace_days),)).fetchall()
    return [(k, m, t.isoformat()) for k, m, t in rows]


def remove_old_runs(grace_days):
    """Delete the runs old_runs() lists. Returns how many went."""
    if not using_database():
        return 0
    with connect() as c:
        return c.execute(
            """DELETE FROM month_result r
               WHERE r.id < (SELECT max(id) FROM month_result n WHERE n.kind = r.kind AND n.month = r.month)
                 AND r.run_at < now() - make_interval(days => %s)""", (int(grace_days),)).rowcount


# ==== Metric intake (owner, 15 Nov 2026; backend/trust/metric_intake.py) ====
# Records (MI-001...), their history (never edited) and the numbers teams sent (every send kept). Nothing here is
# scored. In the database: tables metric_intake, metric_intake_history, metric_value_send (migration 0014).
# Without a database: intake_records.json, intake_history.jsonl and intake_sends.jsonl in the store folder.

def _intake_iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def intake_records():
    """Every record, oldest first: {id, stage, fields, created_at, created_by, changed_at, changed_by}."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT code, stage, fields, created_at, created_by, changed_at, changed_by
                                FROM metric_intake ORDER BY code""").fetchall()
        return [{"id": r[0], "stage": r[1], "fields": r[2], "created_at": _intake_iso(r[3]), "created_by": r[4],
                 "changed_at": _intake_iso(r[5]), "changed_by": r[6]} for r in rows]
    path = _jsonl("intake_records.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def intake_record(code):
    return next((r for r in intake_records() if r["id"] == code), None)


def intake_add(fields, by):
    """Add a Wanted record and give it the next short ID (MI-001, MI-002, ...). Returns the record."""
    if using_database():
        with connect() as c:
            number = c.execute("SELECT nextval('metric_intake_number')").fetchone()[0]
            code = f"MI-{number:03d}"
            c.execute("""INSERT INTO metric_intake (code, stage, fields, created_by, changed_by)
                         VALUES (%s, 'Wanted', %s, %s, %s)""", (code, _jsonb(fields), by, by))
        return intake_record(code)
    records = intake_records()
    number = 1 + max([int(r["id"].split("-")[1]) for r in records] or [0])
    now = _now()
    record = {"id": f"MI-{number:03d}", "stage": "Wanted", "fields": fields, "created_at": now, "created_by": by,
              "changed_at": now, "changed_by": by}
    path = _jsonl("intake_records.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records + [record], ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def intake_update(code, stage, fields, by):
    """Save a record's stage and fields as they now are. Returns the record, or None if there is no such record."""
    if using_database():
        with connect() as c:
            row = c.execute("""UPDATE metric_intake SET stage = %s, fields = %s, changed_at = now(), changed_by = %s
                               WHERE code = %s RETURNING code""", (stage, _jsonb(fields), by, code)).fetchone()
        return intake_record(code) if row else None
    records = intake_records()
    for record in records:
        if record["id"] == code:
            record.update(stage=stage, fields=fields, changed_at=_now(), changed_by=by)
            _jsonl("intake_records.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
            return record
    return None


def intake_history_add(code, by, action, note="", before=None, after=None):
    """One row in a record's history. Never edited afterwards."""
    if using_database():
        with connect() as c:
            c.execute("""INSERT INTO metric_intake_history (code, by, action, note, before, after)
                         VALUES (%s, %s, %s, %s, %s, %s)""",
                      (code, by, action, note, _jsonb(before), _jsonb(after)))
        return
    _append_line("intake_history.jsonl", {"code": code, "at": _now(), "by": by, "action": action, "note": note,
                                          "before": before, "after": after})


def intake_history(code=None):
    """The history rows, oldest first, for one record or all."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT code, at, by, action, note, before, after FROM metric_intake_history
                                WHERE (%s::text IS NULL OR code = %s) ORDER BY id""", (code, code)).fetchall()
        return [{"code": r[0], "at": _intake_iso(r[1]), "by": r[2], "action": r[3], "note": r[4], "before": r[5],
                 "after": r[6]} for r in rows]
    return [r for r in _read_lines("intake_history.jsonl") if code is None or r["code"] == code]


def intake_send_add(send):
    """Keep one send of numbers: {intake_id, month, shape, by, rows_kept, rows_set_aside, totals}. Returns it with
    its id and time. Earlier sends for the same record and month are kept."""
    kept, aside = send["rows_kept"], send["rows_set_aside"]
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO metric_value_send (intake_id, month, shape, by, kept_count, set_aside_count,
                                   rows_kept, rows_set_aside, totals)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            (send["intake_id"], send["month"], send["shape"], send["by"], len(kept), len(aside),
                             _jsonb(kept), _jsonb(aside), _jsonb(send["totals"]))).fetchone()
        return {**send, "id": row[0], "at": _intake_iso(row[1]), "kept_count": len(kept), "set_aside_count": len(aside)}
    return _append_numbered_line("intake_sends.jsonl",
                                 {**send, "kept_count": len(kept), "set_aside_count": len(aside)})


def intake_sends(code=None, month=None):
    """Every send, oldest first, for one record (and month) or all."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT id, intake_id, month, shape, at, by, kept_count, set_aside_count, rows_kept,
                                       rows_set_aside, totals
                                FROM metric_value_send
                                WHERE (%s::text IS NULL OR intake_id = %s) AND (%s::text IS NULL OR month = %s)
                                ORDER BY id""", (code, code, month, month)).fetchall()
        return [{"id": r[0], "intake_id": r[1], "month": r[2], "shape": r[3], "at": _intake_iso(r[4]), "by": r[5],
                 "kept_count": r[6], "set_aside_count": r[7], "rows_kept": r[8], "rows_set_aside": r[9],
                 "totals": r[10]} for r in rows]
    return [s for s in _read_lines("intake_sends.jsonl")
            if (code is None or s["intake_id"] == code) and (month is None or s["month"] == month)]
# ==== end of Metric intake ====


# ==== Risk site (owner, 15 Nov 2026): saved answers and assessments; written by backend/trust/risk/site.py ====
# Both are only ever added to. The newest answer of a question is the one in use; every assessment is kept.

def add_risk_answer(group_id, question, answer, by, from_tech_risk=False):
    """Keep one answer for one group's question. Returns it as kept: id, at, group_id, question, answer, by, from_tech_risk."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO risk_answer (group_id, question, answer, by, from_tech_risk)
                               VALUES (%s, %s, %s, %s, %s) RETURNING id, at""",
                            (group_id, question, answer, by, from_tech_risk)).fetchone()
        return {"id": row[0], "at": row[1].isoformat(), "group_id": group_id, "question": question,
                "answer": answer, "by": by, "from_tech_risk": from_tech_risk}
    return _append_numbered_line("risk_answers.jsonl", {"group_id": group_id, "question": question, "answer": answer,
                                                        "by": by, "from_tech_risk": from_tech_risk})


def risk_answers(group_id=None):
    """Every saved answer, oldest first, for one group or (group_id None) for all of them."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT id, at, group_id, question, answer, by, from_tech_risk FROM risk_answer
                                WHERE %s::text IS NULL OR group_id = %s ORDER BY id""", (group_id, group_id)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "group_id": r[2], "question": r[3], "answer": r[4],
                 "by": r[5], "from_tech_risk": r[6]} for r in rows]
    return [row for row in _read_lines("risk_answers.jsonl") if group_id is None or row["group_id"] == group_id]


def add_risk_assessment(group_id, by, result):
    """Keep one assessment (result is a JSON document). Returns it as kept: id, at, group_id, by, result."""
    if using_database():
        with connect() as c:
            row = c.execute("INSERT INTO risk_assessment (group_id, by, result) VALUES (%s, %s, %s) RETURNING id, at",
                            (group_id, by, _jsonb(result))).fetchone()
        return {"id": row[0], "at": row[1].isoformat(), "group_id": group_id, "by": by, "result": result}
    return _append_numbered_line("risk_assessments.jsonl", {"group_id": group_id, "by": by, "result": result})


def risk_assessments(group_id=None):
    """Every assessment, oldest first, for one group or (group_id None) for all of them."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT id, at, group_id, by, result FROM risk_assessment
                                WHERE %s::text IS NULL OR group_id = %s ORDER BY id""", (group_id, group_id)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "group_id": r[2], "by": r[3], "result": r[4]} for r in rows]
    return [row for row in _read_lines("risk_assessments.jsonl") if group_id is None or row["group_id"] == group_id]
# ==== end of Risk site ====


# ==== Risk site: the copy of TRAC's list of controls (owner, 15 Nov 2026); written by backend/trust/risk/trac_controls.py ====
# Every copy fetched is kept; the newest is the one in use. Each assessment records the fetched date of the copy it used.

def add_risk_controls_copy(published_at, controls):
    """Keep a copy of TRAC's list of controls. Returns it as kept: id, fetched_at, published_at, controls."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO risk_trac_controls (published_at, controls) VALUES (%s, %s)
                               RETURNING id, fetched_at""", (published_at, _jsonb(controls))).fetchone()
        return {"id": row[0], "fetched_at": row[1].isoformat(), "published_at": published_at, "controls": controls}
    row = _append_numbered_line("risk_trac_controls.jsonl", {"published_at": published_at, "controls": controls})
    return {"id": row["id"], "fetched_at": row["at"], "published_at": published_at, "controls": controls}


def risk_controls_copy():
    """The newest copy of TRAC's list of controls, or None when none has been fetched yet."""
    if using_database():
        with connect() as c:
            row = c.execute("""SELECT id, fetched_at, published_at, controls FROM risk_trac_controls
                               ORDER BY id DESC LIMIT 1""").fetchone()
        if row is None:
            return None
        return {"id": row[0], "fetched_at": row[1].isoformat(), "published_at": row[2], "controls": row[3]}
    rows = _read_lines("risk_trac_controls.jsonl")
    if not rows:
        return None
    newest = rows[-1]
    return {"id": newest["id"], "fetched_at": newest["at"], "published_at": newest["published_at"],
            "controls": newest["controls"]}
# ==== end of the copy of TRAC's controls ====


# ==== the lists edited on the site (backend/trust/editable.py) ====
# Every change to an entry of an editable list is one row, never edited or removed. The current entries of a list
# are worked out from its rows, oldest first (editable.entries_now). A list read from a file once has one first-load row.

def add_list_changes(list_name, rows, by):
    """Keep one save: every row is {"key", "action", "before", "after", "reason"}. All or nothing, in this order."""
    if using_database():
        with connect() as c, c.transaction():
            for row in rows:
                c.execute("""INSERT INTO list_change (by, list_name, entry_key, action, before, after, reason)
                             VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                          (by, list_name, row["key"], row["action"], _jsonb(row["before"]), _jsonb(row["after"]), row["reason"]))
        return
    with _line_lock:
        for row in rows:
            _append_numbered_line("list_changes.jsonl", {"by": by, "list_name": list_name, "key": row["key"],
                                                         "action": row["action"], "before": row["before"],
                                                         "after": row["after"], "reason": row["reason"]})


def list_changes(list_name=None):
    """Every kept change, oldest first, for one list or (list_name None) for all of them:
    id, at, by, list_name, key, action, before, after, reason."""
    if using_database():
        with connect() as c:
            found = c.execute("""SELECT id, at, by, list_name, entry_key, action, before, after, reason FROM list_change
                                 WHERE %s::text IS NULL OR list_name = %s ORDER BY id""", (list_name, list_name)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "by": r[2], "list_name": r[3], "key": r[4], "action": r[5],
                 "before": r[6], "after": r[7], "reason": r[8]} for r in found]
    return [row for row in _read_lines("list_changes.jsonl") if list_name is None or row["list_name"] == list_name]
# ==== end of the lists edited on the site ====


# ==== Risk site: sign-off (owner, 15 Nov 2026); written by backend/trust/risk/signoff_routes.py ====
# Sign-offs, send-backs and delegates. Only ever added to; the newest row decides (backend/trust/risk/signoff.py).

SIGNOFF_COLUMNS = ("kind", "group_id", "assessment_id", "by", "signer_sam", "note", "l3_sam", "delegate_sam",
                   "also_changed", "changed_answers")
SIGNOFF_DEFAULTS = {"group_id": None, "assessment_id": None, "signer_sam": None, "note": None, "l3_sam": None,
                    "delegate_sam": None, "also_changed": False, "changed_answers": 0}


def add_risk_signoff(row):
    """Keep one sign-off, send-back or delegate row. row has `kind` and `by`, and any of the other SIGNOFF_COLUMNS.
    Returns it as kept, with id and at."""
    row = {**SIGNOFF_DEFAULTS, **{key: row[key] for key in SIGNOFF_COLUMNS if key in row}}
    if using_database():
        with connect() as c:
            kept = c.execute("""INSERT INTO risk_signoff (kind, group_id, assessment_id, by, signer_sam, note, l3_sam,
                                                          delegate_sam, also_changed, changed_answers)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            tuple(row[key] for key in SIGNOFF_COLUMNS)).fetchone()
        return {"id": kept[0], "at": kept[1].isoformat(), **row}
    return _append_numbered_line("risk_signoffs.jsonl", row)


def risk_signoffs(group_id=None):
    """Every sign-off, send-back and delegate row, oldest first. With a group_id: that group's decisions and every
    delegate row (a delegate covers all of an L3's groups). With None: all rows."""
    if using_database():
        with connect() as c:
            found = c.execute("""SELECT id, at, kind, group_id, assessment_id, by, signer_sam, note, l3_sam,
                                        delegate_sam, also_changed, changed_answers FROM risk_signoff
                                 WHERE %s::text IS NULL OR group_id = %s OR kind = 'delegate' ORDER BY id""",
                              (group_id, group_id)).fetchall()
        names = ("id", "at", "kind", "group_id", "assessment_id", "by", "signer_sam", "note", "l3_sam",
                 "delegate_sam", "also_changed", "changed_answers")
        rows = [dict(zip(names, record)) for record in found]
        for row in rows:
            row["at"] = row["at"].isoformat()
        return rows
    return [row for row in _read_lines("risk_signoffs.jsonl")
            if group_id is None or row["group_id"] == group_id or row["kind"] == "delegate"]
# ==== end of Risk site: sign-off ====


# ==== Risk site, engine bridge (R8): the engine output files uploaded for a group; written by backend/trust/risk/engine_bridge_routes.py ====
# Only ever added to. The newest run of a group is the one the side-by-side page compares.

def add_risk_engine_run(group_id, by, file_hash, parsed):
    """Keep one uploaded engine output (parsed is a JSON document). Returns it as kept: id, at, group_id, by, file_hash, parsed."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO risk_engine_run (group_id, by, file_hash, parsed) VALUES (%s, %s, %s, %s)
                               RETURNING id, at""", (group_id, by, file_hash, _jsonb(parsed))).fetchone()
        return {"id": row[0], "at": row[1].isoformat(), "group_id": group_id, "by": by, "file_hash": file_hash, "parsed": parsed}
    return _append_numbered_line("risk_engine_runs.jsonl", {"group_id": group_id, "by": by, "file_hash": file_hash, "parsed": parsed})


def risk_engine_runs(group_id=None):
    """Every kept engine run, oldest first, for one group or (group_id None) for all of them."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT id, at, group_id, by, file_hash, parsed FROM risk_engine_run
                                WHERE %s::text IS NULL OR group_id = %s ORDER BY id""", (group_id, group_id)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "group_id": r[2], "by": r[3], "file_hash": r[4], "parsed": r[5]} for r in rows]
    return [row for row in _read_lines("risk_engine_runs.jsonl") if group_id is None or row["group_id"] == group_id]
# ==== end of Risk site, engine bridge ====


# ==== Risk site: uploads that seed the risks, drivers and questionnaire (owner, 16 Nov 2026); written by backend/trust/risk/seed_routes.py ====
# Every load is kept: who, when, hash, what was read, and what the site holds after it. Only ever added to.
# The newest load of "risks" and of "drivers" is where the site reads them from (backend/trust/risk/seed.py).

def add_risk_seed_upload(kind, by, file_name, file_hash, read, registers):
    """Keep one load. kind is risks, drivers or questions; read and registers are JSON documents.
    Returns it as kept (id, at, kind, by, file_name, file_hash, read)."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO risk_seed_upload (kind, by, file_name, file_hash, read, registers)
                               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            (kind, by, file_name, file_hash, _jsonb(read), _jsonb(registers))).fetchone()
        return {"id": row[0], "at": row[1].isoformat(), "kind": kind, "by": by, "file_name": file_name,
                "file_hash": file_hash, "read": read}
    row = _append_numbered_line("risk_seed_uploads.jsonl", {"kind": kind, "by": by, "file_name": file_name, "file_hash": file_hash,
                                                      "read": read, "registers": registers})
    return {key: value for key, value in row.items() if key != "registers"}


def risk_seed_uploads(kind=None):
    """Every kept load, oldest first, for one kind or (kind None) all of them. Without what the site holds after it."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT id, at, kind, by, file_name, file_hash, read FROM risk_seed_upload
                                WHERE %s::text IS NULL OR kind = %s ORDER BY id""", (kind, kind)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "kind": r[2], "by": r[3], "file_name": r[4],
                 "file_hash": r[5], "read": r[6]} for r in rows]
    return [{key: value for key, value in row.items() if key != "registers"}
            for row in _read_lines("risk_seed_uploads.jsonl") if kind is None or row["kind"] == kind]


def risk_seed_newest_registers(kind):
    """What the site holds after the newest load of this kind (every risk, or every driver rule), or None when
    nothing of this kind was ever loaded."""
    if using_database():
        with connect() as c:
            row = c.execute("SELECT registers FROM risk_seed_upload WHERE kind = %s ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
        return row[0] if row else None
    rows = [row for row in _read_lines("risk_seed_uploads.jsonl") if row["kind"] == kind]
    return rows[-1]["registers"] if rows else None
# ==== end of Risk site: uploads that seed the registers ====


# ==== Risk site: starting an assessment (owner, 16 Nov 2026); written by backend/trust/risk/site.py ====
# One row each time someone presses Start for a team. Only ever added to.

def add_risk_start(group_id, by):
    """Keep that `by` started an assessment for the team. Returns it as kept: id, at, group_id, by."""
    if using_database():
        with connect() as c:
            row = c.execute("INSERT INTO risk_start (group_id, by) VALUES (%s, %s) RETURNING id, at",
                            (group_id, by)).fetchone()
        return {"id": row[0], "at": row[1].isoformat(), "group_id": group_id, "by": by}
    return _append_numbered_line("risk_starts.jsonl", {"group_id": group_id, "by": by})


def risk_starts(group_id=None):
    """Every start, oldest first, for one team or (group_id None) for all of them."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT id, at, group_id, by FROM risk_start
                                WHERE %s::text IS NULL OR group_id = %s ORDER BY id""", (group_id, group_id)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), "group_id": r[2], "by": r[3]} for r in rows]
    return [row for row in _read_lines("risk_starts.jsonl") if group_id is None or row["group_id"] == group_id]
# ==== end of Risk site: starting an assessment ====
