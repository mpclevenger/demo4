"""The website's change endpoints: upload a file, then update (map, score, publish) a month."""
import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import web  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
H = {"X-TRUST": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    return web.app.test_client()


def up(client, feed, name, month="2026-09", by="Tester", headers=H):
    data = {"feed": feed, "month": month, "by": by, "file": (io.BytesIO((FIX / name).read_bytes()), name)}
    return client.post("/api/upload", data=data, headers=headers, content_type="multipart/form-data")


def test_upload_update_then_the_page_shows_it(client):
    r = up(client, "tcc", "tcc_export.csv")
    assert r.status_code == 200 and r.json["ok"] and "kept" in r.json["note"]
    assert up(client, "tcc", "tcc_export.csv").json["note"].startswith("already received")
    up(client, "hr", "hr_firmwide.csv")
    st = client.get("/api/month/2026-09").json
    assert st["feeds"]["tcc"]["uploaded_by"] == "Tester" and st["feeds"]["tcc"]["uploads"] == 1
    r = client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    assert r.status_code == 200 and "tcc" in r.json["received"]
    d = client.get("/data.json").json
    assert d["live"] is True and "2026-09" in d["periods"]


def test_changes_without_the_header_are_refused(client):
    assert up(client, "tcc", "tcc_export.csv", headers={}).status_code == 403
    assert client.post("/api/update", json={"month": "2026-09", "by": "T"}).status_code == 403


def test_plain_reasons_for_what_cant_be_done(client):
    assert "Type your name" in up(client, "tcc", "tcc_export.csv", by="  ").json["error"]
    assert "feed TRUST knows" in up(client, "nope", "tcc_export.csv").json["error"]
    assert "2026-10" in up(client, "tcc", "tcc_export.csv", month="Oct").json["error"]
    r = client.post("/api/upload", data={"feed": "tcc", "month": "2026-09", "by": "T"}, headers=H)
    assert "Choose a file" in r.json["error"]
    r = client.post("/api/update", json={"month": "2026-09", "by": "T"}, headers=H)
    assert r.status_code == 400 and "Nothing has been uploaded" in r.json["error"]


def ready(client, month="2026-09"):
    for feed, name in (("hr", "hr_firmwide.csv"), ("tcc", "tcc_export.csv")):
        up(client, feed, name, month)
    assert client.post("/api/update", json={"month": month, "by": "Tester"}, headers=H).status_code == 200


def ack_all(client, month="2026-09"):
    keys = [w["key"] for w in client.get(f"/api/month/{month}").json["warnings"] if not w["ack"] and not w["info"]]
    return client.post("/api/acknowledge", json={"month": month, "keys": keys, "by": "Rita", "reason": "read"}, headers=H)


def test_warnings_can_be_acknowledged_but_gate_nothing(client):
    ready(client)
    ws = [w for w in client.get("/api/month/2026-09").json["warnings"] if not w["info"]]     # information notes need none
    assert ws and all(w["ack"] is None for w in ws) and {"feed", "note", "key"} <= set(ws[0])
    first = client.post("/api/acknowledge", json={"month": "2026-09", "keys": [ws[0]["key"]], "by": "Rita"}, headers=H)
    assert first.json["acknowledged"] == 1
    assert [w for w in client.get("/api/month/2026-09").json["warnings"] if not w["info"]][0]["ack"]["by"] == "Rita"
    assert "Reload" in client.post("/api/acknowledge", json={"month": "2026-09", "keys": ["nope"], "by": "R"},
                                   headers=H).json["error"]
    assert ack_all(client).json["acknowledged"] == len(ws) - 1
    # a warning that nobody has acknowledged stops nothing: another file and another update still work
    assert up(client, "ntcc", "ntcc_export.csv").status_code == 200
    assert client.post("/api/update", json={"month": "2026-09", "by": "T"}, headers=H).status_code == 200
    assert any(w["ack"] is None for w in client.get("/api/month/2026-09").json["warnings"] if not w["info"])


def test_every_month_stays_open(client):
    """Owner, 17 Nov 2026: no month lock. Upload, update, comment and publish always work; the lock routes are gone."""
    ready(client)
    assert client.post("/api/lock", json={"month": "2026-09", "by": "T"}, headers=H).status_code == 404
    assert client.post("/api/reopen", json={"month": "2026-09", "by": "T", "reason": "x"}, headers=H).status_code == 404
    meta = client.get("/data.json").json["periods"]["2026-09"]["meta"]
    assert "status" not in meta and "locked_by" not in meta and "locked_at" not in meta
    assert "status" not in client.get("/api/month/2026-09").json
    assert up(client, "ntcc", "ntcc_export.csv").status_code == 200
    assert client.post("/api/update", json={"month": "2026-09", "by": "T"}, headers=H).status_code == 200
    c = client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation",
                                           "text": "Note", "by": "Lead"}, headers=H).json["comment"]
    assert "after_lock" not in c


def test_a_month_marked_locked_in_an_old_database_is_open(client, tmp_path):
    """Old stores may hold a month marked locked, with a seal and a lock event. The mark is ignored: nothing crashes."""
    import json
    store_dir = tmp_path / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    seal = {"files": [{"feed": "tcc", "uploaded_by": "x"}], "scored_sha256": "abc", "shown": {"families": {}}}
    (store_dir / "months.json").write_text(json.dumps({"2026-09": {
        "status": "locked", "locked_by": "Old Lock", "locked_at": "2026-10-01T00:00:00+00:00", "seal": seal}}))
    (store_dir / "events.jsonl").write_text(json.dumps({"id": 1, "at": "2026-10-01T00:00:00+00:00", "month": "2026-09",
                                                        "action": "lock", "by": "Old Lock", "note": "locked", "detail": seal}) + "\n")
    for feed, name in (("hr", "hr_firmwide.csv"), ("tcc", "tcc_export.csv")):
        assert up(client, feed, name).status_code == 200                      # upload works
    r = client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)   # map, score, publish work
    assert r.status_code == 200 and "tcc" in r.json["received"]
    periods = client.get("/data.json").json["periods"]
    assert "2026-09" in periods and "status" not in periods["2026-09"]["meta"] and "seal" not in periods["2026-09"]
    page = client.get("/api/month/2026-09").json                              # the old lock event is still listed
    assert page["ok"] and any(e["action"] == "lock" for e in page["events"])
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation",
                                              "text": "Note", "by": "Lead"}, headers=H).status_code == 200


def test_comments_threads_and_checks(client):
    ready(client)
    post = lambda **kw: client.post("/api/comments", json={"month": "2026-09", "by": "Lead", **kw}, headers=H)
    q = post(family="payments", metric="TE-02", kind="query", text="Is the revert real?").json["comment"]
    assert q["status"] == "open"
    a = post(family="payments", reply_to=q["id"], text="Yes, see CHG-1", status="closed").json["comment"]
    assert a["kind"] == "query" and a["metric"] == "TE-02" and a["status"] == "closed"
    e = post(family="payments", block="REL", kind="explanation", text="Two releases only").json["comment"]
    assert e["status"] is None
    assert "isn't on the scorecard" in post(family="nope", kind="explanation", text="x").json["error"]
    assert "isn't on the scorecard" in post(family="payments", metric="XX-99", kind="explanation", text="x").json["error"]
    assert "Write something" in post(family="payments", kind="explanation", text="  ").json["error"]
    assert "Choose explanation" in post(family="payments", kind="note", text="x").json["error"]
    assert [c["id"] for c in client.get("/api/comments/2026-09").json["comments"]] == [q["id"], a["id"], e["id"]]


def test_drill_down_and_excel_download(client):
    ready(client)
    for feed, name in (("actions", "actions_export.csv"), ("postmortems", "postmortems_export.csv"),
                       ("ntcc", "ntcc_export.csv")):                        # TE-01 needs both change files
        up(client, feed, name)
    client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    ev = client.get("/evidence.json").json["2026-09"]
    te01 = ev["payments"]["TE-01"]
    assert len(te01["items"]) == 3 and sum(t["den"] for t in te01["by_team"]) == 3            # 2 TCC + 1 Non-TCC
    it = te01["items"][0]
    assert it["item_type"] == "change" and it["item_id"]
    assert all(t["team_key"] and t["team_name"] for f in ev.values() for e in f.values() for t in e["by_team"])
    un02 = next(e for f in ev.values() for m, e in f.items() if m == "UN-02")
    assert all(i["item_type"] == "action" for i in un02["items"])
    r = client.get("/api/items/2026-09/payments.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert client.get("/api/items/2026-09/nope.xlsx").status_code == 404


def test_each_metric_has_its_data_table_and_downloads(client):
    """Owner, 9 Nov 2026: drill into the data on the page (a table per metric, its own key details, items that
    need attention first), download one table as a CSV, and download everything as Excel, one tab per metric."""
    import io
    from openpyxl import load_workbook
    ready(client)
    for feed, name in (("actions", "actions_export.csv"), ("postmortems", "postmortems_export.csv"),
                       ("ntcc", "ntcc_export.csv")):
        up(client, feed, name)
    client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    ev = client.get("/evidence.json").json["2026-09"]
    t = ev["payments"]["TE-01"]["table"]
    assert t["columns"] == ["Change", "Route", "Created", "Deployed"] and t["types"][2] == "date"
    assert len(t["rows"]) == 3 and all(len(r["cells"]) == 4 for r in t["rows"])
    r0 = t["rows"][0]                                                         # owner, 9 Nov 2026: the minimum
    assert r0["who"] and r0["who"][0]["name"] and r0["who"][0]["sam"] and r0["who"][0]["email"]
    assert set(r0["who"][0]) >= {"l4", "l4_email", "l3", "l3_email"} and r0["as_of"] and r0["detail"]
    att = [r["attention"] for r in t["rows"]]
    assert att == sorted(att, reverse=True)                                   # needs attention first
    assert [r["cells"][1] for r in t["rows"] if r["attention"]] == ["Outside TCC (Non-TCC)"]
    r = client.get("/api/items/2026-09/payments/TE-01.csv")
    assert r.status_code == 200 and "trust-TE-01-payments-2026-09.csv" in r.headers["Content-Disposition"]
    lines = r.data.decode("utf-8-sig").splitlines()
    assert lines[1] == ("Contributing,Change,Route,Created,Deployed,Detail,Name,ID (SAM account),Email,L4 manager,"
                        "L4 manager email,L3 manager,L3 manager email,Team,L3 team,As of (file uploaded),Link")
    assert len(lines) == 5 and ",Payments," in lines[2]
    team = t["rows"][0]["team_key"]
    some = client.get(f"/api/items/2026-09/payments/TE-01.csv?team={team}").data.decode("utf-8-sig").splitlines()
    assert 2 < len(some) <= len(lines)
    assert client.get("/api/items/2026-09/payments/XX-99.csv").status_code == 404
    x = client.get("/api/items/2026-09/payments.xlsx")
    assert x.status_code == 200 and "spreadsheetml" in x.headers["Content-Type"]
    wb = load_workbook(io.BytesIO(x.data))
    assert wb.sheetnames[0] == "About" and "TE-01" in wb.sheetnames and "UN-02" in wb.sheetnames
    assert [c.value for c in wb["TE-01"][2]][:3] == ["Contributing", "Change", "Route"]
    assert client.get("/api/items/2026-09/nope.xlsx").status_code == 404


def test_every_measured_metric_lists_columns_that_its_items_carry():
    """counting.columns in config/metrics.json name fields the measure step really puts on each item."""
    from trust import config, evidence
    for mid, m in config.metrics().items():
        cols = (m.get("counting") or {}).get("columns")
        if m.get("status") != "Measured":
            continue
        assert cols, f"{mid} has no counting.columns"
        for c in cols:
            assert c.get("label") and c.get("field"), (mid, c)
            assert c.get("as") in (None, "yes_no", "date", "list", "map", "of"), (mid, c)
        assert evidence.table(mid, [])["columns"] == [c["label"] for c in cols]


def test_csv_cells_that_excel_would_run_are_quoted():
    from trust import evidence
    assert evidence._cell('=HYPERLINK("http://bad")') == '\'=HYPERLINK("http://bad")'
    assert [evidence._cell(x) for x in ("-1", "@me", "+t", "plain", None)] == ["'-1", "'@me", "'+t", "plain", ""]


def test_the_site_shows_the_deployed_definitions_not_the_saved_copy(client):
    """Owner, 8 Nov 2026: a definition changed in config/metrics.json shows once deployed, before any Update.
    Scores stay as published until the month is updated."""
    import json
    from trust import storage
    ready(client)
    saved = json.loads(storage.published("data.json"))
    old = saved["periods"]["2026-09"]["families"]["payments"]["metrics"]["TE-01"]
    saved["dictionary"]["metrics"]["TE-01"] = {"definition": "an old write-up"}          # as saved by an earlier version
    saved["metrics"] = [dict(m, name="Old name") if m["id"] == "TE-01" else m for m in saved["metrics"]]
    storage.save_published({"data.json": json.dumps(saved), "index.html": "", "evidence.json": "{}"})
    d = client.get("/data.json").json
    card = d["dictionary"]["metrics"]["TE-01"]
    assert "through TCC" in card["definition"] and card["wording"]["counts"]["verb_one"] == "went through TCC"
    assert next(m for m in d["metrics"] if m["id"] == "TE-01")["name"] == "Change ticket adoption"
    assert d["periods"]["2026-09"]["families"]["payments"]["metrics"]["TE-01"] == old     # results untouched
    assert "through TCC" in client.get("/").get_data(as_text=True)


def test_the_page_is_split_into_shared_files_and_one_file_per_page(client):
    """Owner, 15 Nov 2026: index.html is the frame; styles and code are in frontend/shared and frontend/pages."""
    import pathlib
    import re
    front = pathlib.Path(__file__).resolve().parents[1] / "frontend"
    html = client.get("/").get_data(as_text=True)
    srcs = re.findall(r'<script src="([^"]+)"></script>', html)
    assert srcs[0] == "shared/core.js" and srcs[-1] == "shared/start.js" and len(srcs) == len(set(srcs))
    on_disk = {f"{p.parent.name}/{p.name}" for d in ("shared", "pages") for p in (front / d).glob("*.js")}
    assert set(srcs) == on_disk                                        # every file is loaded, and nothing loaded is missing
    assert "<style>" not in html and 'href="shared/site.css"' in html
    for src in srcs + ["shared/site.css"]:
        r = client.get("/" + src)
        assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store" and len(r.data) > 20
    assert client.get("/shared/core.js").headers["Content-Type"].startswith("text/javascript")
    for bad in ("/shared/nope.js", "/pages/..%2Findex.html", "/shared/.hidden.js", "/pages/family.py"):
        assert client.get(bad).status_code == 404


def test_a_json_list_instead_of_an_object_is_refused_not_a_crash(client):
    for path in ("/api/update", "/api/acknowledge", "/api/comments", "/api/proposals",
                 "/api/thresholds"):
        r = client.post(path, json=[1, 2], headers=H)
        assert r.status_code == 400 and r.json["error"] == "The request must be a JSON object.", path


def test_a_file_added_in_a_newer_version_can_be_uploaded_before_the_next_update(client):
    """Owner, 17 Nov 2026: page data published by an older version listed the files that version knew, so Repo
    contributors had no upload row until someone pressed Update. The page always gets the running code's list."""
    import json as _json
    from trust import storage, store
    up(client, "tcc", "tcc_export.csv")
    client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    old = _json.loads(storage.published("data.json"))
    old["feeds"] = [feed for feed in old["feeds"] if feed != "repo_contributors"]     # as an older version saved it
    storage.save_published({"data.json": _json.dumps(old)})
    assert "repo_contributors" not in _json.loads(storage.published("data.json"))["feeds"]
    assert sorted(client.get("/data.json").json["feeds"]) == sorted(store.FEEDS)


def test_kept_page_data_never_hides_a_new_upload(client):
    """Owner, 17 Nov 2026 ("super slow"): page data for months not yet published is kept between visits, but an
    upload (or update) is seen on the very next visit."""
    first = client.get("/data.json").json
    assert "2026-09" not in first["periods"]
    up(client, "tcc", "tcc_export.csv")                                  # a month with uploads, not yet scored
    assert "2026-09" in client.get("/data.json").json["periods"]


def test_metrics_file_is_read_again_when_it_changes(tmp_path, monkeypatch):
    from trust import config
    path = tmp_path / "metrics.json"
    path.write_text('{"metrics": {"AA-01": {"counting": {"items_name": "x"}}}}')
    monkeypatch.setenv("TRUST_METRICS", str(path))
    assert config.counting("AA-01") == {"items_name": "x"}
    got = config.metrics()
    got["AA-01"]["counting"]["items_name"] = "changed by a caller"     # a caller's copy never changes the kept one
    assert config.counting("AA-01") == {"items_name": "x"}
    import os
    path.write_text('{"metrics": {"AA-01": {"counting": {"items_name": "yz"}}}}')
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))
    assert config.counting("AA-01") == {"items_name": "yz"}
