"""Roles on TRUST's side (owner, 3 Nov 2026): the add-on passes the SAM_ACCOUNT and AD groups; TRUST checks
every page, file and change against docs/wiki/roles-and-permissions.md."""
import io
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import storage, web  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
CFG = {"user_header": "X-User", "groups_header": "X-Groups",
       "groups": {"cto_leadership": ["TRUST-Leaders"], "tech_risk": ["TRUST-TR"],
                  "head_of_tech_risk": ["TRUST-HoTR"], "auditor": ["TRUST-Audit"]},
       "family_lead_groups": {"cards": ["TRUST-Cards-Delegates"]}}


def who(sam, groups=""):
    return {"X-User": sam, "X-Groups": groups, "X-TRUST": "1"}


TR, HOTR, AUD, CTO = who("trisk", "TRUST-TR"), who("hotr", "TRUST-HoTR"), who("auditr", "TRUST-Audit"), who("boss", "TRUST-Leaders")
LEAD, MEMBER = who("CORP\\amoreno"), who("slee")          # owner of Payments; placed in Payments through HR


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    acc = tmp_path / "access.json"
    acc.write_text(json.dumps(CFG))
    monkeypatch.setenv("TRUST_ACCESS", str(acc))
    c = web.app.test_client()
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv"),
                       ("postmortems", "postmortems_export.csv"), ("actions", "actions_export.csv")):
        data = {"feed": feed, "month": "2026-09", "file": (io.BytesIO((FIX / name).read_bytes()), name)}
        assert c.post("/api/upload", data=data, headers=TR, content_type="multipart/form-data").status_code == 200
    assert c.post("/api/update", json={"month": "2026-09"}, headers=TR).status_code == 200
    return c


def test_no_role_no_entry(client):
    assert client.get("/").status_code == 403
    assert client.get("/", headers=who("stranger")).status_code == 403
    assert "access to TRUST" in client.get("/data.json", headers=who("stranger")).get_data(as_text=True)
    assert client.get("/healthz").status_code == 200


def test_tech_risk_runs_the_month_and_is_recorded_by_account(client):
    st = client.get("/api/month/2026-09", headers=TR).json
    assert st["feeds"]["tcc"]["uploaded_by"] == "trisk"          # not a typed name
    assert client.post("/api/update", json={"month": "2026-09"}, headers=MEMBER).status_code == 403


def test_auditor_reads_and_downloads_but_cannot_change(client):
    assert client.get("/api/month/2026-09", headers=AUD).status_code == 200
    assert client.post("/api/update", json={"month": "2026-09"}, headers=AUD).status_code == 403
    # owner, 9 Nov 2026: whoever is logged in can drill into the data and export it
    assert client.get("/api/items/2026-09/payments.xlsx", headers=AUD).status_code != 403
    me = client.get("/data.json", headers=AUD).json["access"]["me"]
    assert me["read_only"] and me["page_role"] == "tr"


def test_cto_sees_and_exports_every_family_but_no_console(client):
    d = client.get("/data.json", headers=CTO).json
    assert all("reason" in r for f in d["periods"]["2026-09"]["families"].values() for r in f["metrics"].values())
    assert client.get("/api/month/2026-09", headers=CTO).status_code == 403
    assert client.get("/api/items/2026-09/payments.xlsx", headers=CTO).status_code != 403        # owner, 9 Nov 2026
    assert d["access"]["me"]["page_role"] == "cto"


def test_family_lead_gets_their_family_only(client):
    d = client.get("/data.json", headers=LEAD).json
    fams = d["periods"]["2026-09"]["families"]
    assert "reason" in fams["payments"]["metrics"]["TE-01"]                    # own family in full
    assert set(fams["cards"]["metrics"]["TE-01"]) <= {"status", "points", "override", "behind_peers", "history", "delta", "provisional"}
    assert d["periods"]["2026-09"]["submissions"] == []
    assert d["access"]["me"]["lead_of"] == ["payments"] and d["access"]["me"]["page_role"] == "fl:payments"
    ev = client.get("/evidence.json", headers=LEAD).json
    assert set(ev["2026-09"]) <= {"payments"}
    assert storage.events(None, 5)[0]["action"] == "view"
    assert client.get("/api/items/2026-09/payments.xlsx", headers=LEAD).status_code == 200
    assert client.get("/api/items/2026-09/cards.xlsx", headers=LEAD).status_code == 403
    ok = client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation", "text": "Why"}, headers=LEAD)
    assert ok.status_code == 200 and ok.json["comment"]["by"] == "Alex Moreno (amoreno)"
    no = client.post("/api/comments", json={"month": "2026-09", "family": "cards", "kind": "explanation", "text": "x"}, headers=LEAD)
    assert no.status_code == 403
    # the page itself carries the cut-down data and who they are
    html = client.get("/", headers=LEAD).get_data(as_text=True)
    assert '"page_role": "fl:payments"' in html


def test_family_member_comments_and_downloads_own_family_but_cannot_reply(client):
    q = client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "query", "text": "Is this right?"}, headers=TR).json["comment"]
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation", "text": "Context"}, headers=MEMBER).status_code == 200
    assert client.get("/api/items/2026-09/payments.xlsx", headers=MEMBER).status_code != 403     # own family (owner, 9 Nov 2026)
    assert client.get("/api/items/2026-09/cards.xlsx", headers=MEMBER).status_code == 403          # not another family's
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "reply_to": q["id"], "text": "Yes"}, headers=MEMBER).status_code == 403
    # the lead replies but can't close; Tech Risk can
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "reply_to": q["id"], "text": "Yes", "status": "closed"}, headers=LEAD).status_code == 403
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "reply_to": q["id"], "text": "Yes"}, headers=LEAD).status_code == 200
    seen = client.get("/api/comments/2026-09", headers=MEMBER).json["comments"]
    assert {c["family"] for c in seen} == {"payments"}


def test_proposals_tech_risk_proposes_head_of_tech_risk_decides(client):
    body = {"kind": "change", "metric": "TE-01", "title": "TE-01 wording", "detail": {"field": "Population", "wording": "w", "reason": "r"}}
    assert client.post("/api/proposals", json=body, headers=LEAD).status_code == 403
    pid = client.post("/api/proposals", json=body, headers=TR).json["proposal"]["id"]
    assert client.post(f"/api/proposals/{pid}/decide", json={"decision": "approved"}, headers=TR).status_code == 403
    r = client.post(f"/api/proposals/{pid}/decide", json={"decision": "approved"}, headers=HOTR)
    assert r.status_code == 200 and r.json["proposal"]["decisions"][0]["by"] == "hotr"
    assert client.get("/api/proposals", headers=AUD).status_code == 200
    assert client.get("/api/proposals", headers=CTO).status_code == 403


def test_groups_as_distinguished_names_and_delegates(client):
    dn = who("someone", "CN=TRUST-Audit,OU=Groups,DC=corp,DC=example,CN=Other,OU=Groups,DC=corp")
    assert client.get("/data.json", headers=dn).json["access"]["me"]["roles"] == ["auditor"]
    dele = who("helper", "trust-cards-delegates")                                # any capitals
    assert client.get("/data.json", headers=dele).json["access"]["me"]["lead_of"] == ["cards"]
    assert client.get("/api/items/2026-09/cards.xlsx", headers=dele).status_code in (200, 404)


def test_lost_and_found_is_a_tech_risk_page(client):
    # owner, 15 Nov 2026: only Tech Risk sees Lost and found (auditors read only); nobody else, and only Tech Risk claims
    assert client.get("/api/lost/2026-09", headers=TR).status_code == 200
    assert client.get("/api/lost/2026-09", headers=AUD).status_code == 200
    for other in (CTO, LEAD, MEMBER):
        assert client.get("/api/lost/2026-09", headers=other).status_code == 403
    claim = {"month": "2026-09", "family": "payments", "feed": "tcc", "item": "X-1", "why": "ours"}
    assert client.post("/api/claims", json=claim, headers=LEAD).status_code == 403
    assert client.post("/api/claims", json=claim, headers=AUD).status_code == 403


def test_thresholds_and_caps_are_changed_by_tech_risk_only(client):
    # owner, 15 Nov 2026: Tech Risk edits; auditors read the values and the audit trail; nobody else sees the page
    change = {"changes": {"caps.red_metric_block": 70}, "reason": "Agreed"}
    assert client.get("/api/thresholds", headers=AUD).json["can_edit"] is False
    for other in (CTO, LEAD, MEMBER):
        assert client.get("/api/thresholds", headers=other).status_code == 403
    for other in (AUD, CTO, LEAD, MEMBER):
        assert client.post("/api/thresholds/preview", json=change, headers=other).status_code == 403
        assert client.post("/api/thresholds", json=change, headers=other).status_code == 403
    assert client.post("/api/thresholds", json={"changes": change["changes"]}, headers=TR).status_code == 400   # no reason
    pv = client.post("/api/thresholds/preview", json=change, headers=TR).json
    assert pv["ok"] and pv["changes"][0]["before"] == 79
    got = client.post("/api/thresholds", json=change, headers=TR).json
    assert got["ok"] and got["history"][0]["by"] == "trisk" or "trisk" in got["history"][0]["by"]
    assert client.get("/api/thresholds", headers=TR).json["can_edit"] is True


def test_a_family_lead_gets_no_other_familys_behind_peers_line_and_no_seal_files():
    # Behind peers lines quote other families' values; a page published before the lock was removed may carry a seal that lists files and uploaders.
    from trust import access
    data = {"periods": {"2026-09": {
        "families": {},
        "watch_list": [
            {"kind": "Behind peers", "family_id": "cards", "text": "Cards: TE-01 40 vs typical 80"},
            {"kind": "Behind peers", "family_id": "payments", "text": "Payments: TE-01 50 vs typical 80"},
            {"kind": "New red", "family_id": "cards", "text": "Cards: TE-01 turned Red"}],
        "seal": {"locked_by": "trisk", "files": [{"feed": "tcc", "uploaded_by": "someone"}], "scored_sha256": "abc"}}}}
    lead = {"roles": set(), "lead_of": {"payments"}, "member_of": set(), "open": False}
    shown = access.filter_data(data, lead)["periods"]["2026-09"]
    assert [w["text"] for w in shown["watch_list"]] == ["Payments: TE-01 50 vs typical 80", "Cards: TE-01 turned Red"]
    assert shown["seal"] == {"locked_by": "trisk", "scored_sha256": "abc"}
    assert len(data["periods"]["2026-09"]["watch_list"]) == 3          # the published copy is untouched


PROXY_HEADER = "X-Proxy-Secret"
PROXY_VALUE = "a-long-random-test-value"


def _write_access_file(extra):
    # rewrites the access file the client fixture points at, with the proxy secret settings added (or not)
    path = pathlib.Path(os.environ["TRUST_ACCESS"])
    path.write_text(json.dumps(dict(CFG, **extra)))


def test_proxy_secret_refuses_a_request_without_the_header(client):
    # with the secret set, a person who names themselves but lacks the header is turned away
    _write_access_file({"proxy_secret_header": PROXY_HEADER, "proxy_secret_value": PROXY_VALUE})
    assert client.get("/data.json", headers=TR).status_code == 403


def test_proxy_secret_refuses_a_wrong_value(client):
    _write_access_file({"proxy_secret_header": PROXY_HEADER, "proxy_secret_value": PROXY_VALUE})
    wrong = dict(TR, **{PROXY_HEADER: "not-the-secret"})
    assert client.get("/data.json", headers=wrong).status_code == 403


def test_proxy_secret_lets_in_a_request_with_the_header(client):
    _write_access_file({"proxy_secret_header": PROXY_HEADER, "proxy_secret_value": PROXY_VALUE})
    right = dict(TR, **{PROXY_HEADER: PROXY_VALUE})
    assert client.get("/data.json", headers=right).status_code == 200
    assert client.get("/api/month/2026-09", headers=right).status_code == 200


def test_without_the_proxy_secret_setting_nothing_changes(client):
    # the keys are empty in config/access.json: no header is needed, and the same person gets the same entry
    _write_access_file({"proxy_secret_header": "", "proxy_secret_value": ""})
    assert client.get("/data.json", headers=TR).status_code == 200
    _write_access_file({})                                  # the keys missing altogether behaves the same
    assert client.get("/data.json", headers=TR).status_code == 200


def test_every_response_says_no_framing_from_other_sites(client):
    # X-Frame-Options: SAMEORIGIN on pages, data, and refusals alike
    for path, headers in (("/healthz", {}), ("/data.json", TR), ("/data.json", who("stranger"))):
        resp = client.get(path, headers=headers)
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN", path
