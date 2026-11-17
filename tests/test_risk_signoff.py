"""Risk site sign-off (owner, 16 Nov 2026): whoever leads the unit being assessed signs off or sends it back.

Every example is one made-up TRUST team, "Lending" (the Risk site's groups are TRUST's teams), led by Emery Rook (erook6),
its product family owner. In the made-up HR, Emery reports to Lee Moss (lmoss3), the L3, who does NOT sign off any more.
Dee Park (dpark4) is the person Emery may name as delegate. Sam Ito (sam2) is a second owner in the many-owners test.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import storage, web  # noqa: E402
from trust.risk import groups, signoff  # noqa: E402

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
GROUP = "lending--lending-platform"
MONTH = "2026-10"
BASE = f"/api/risk/groups/{GROUP}"

# (SAM_ACCOUNT, name, manager, reporting level from the top)
PEOPLE = [("cto.demo", "Cass Top", None, 1), ("lmoss3", "Lee Moss", "cto.demo", 3), ("erook6", "Emery Rook", "lmoss3", 4),
          ("pat1", "Pat Lee", "erook6", 5), ("sam2", "Sam Ito", "erook6", 5), ("dpark4", "Dee Park", "lmoss3", 4),
          ("zed9", "Zed Moss", "cto.demo", 2)]


def put_hr_in_the_store(with_the_l3_link=True):
    """Lee Moss (level 3) leads the L3 team Lending. Emery Rook (level 4) leads the L4 team "Lending Platform" with Pat
    and Sam under her. Dee Park (level 4) leads another L4 team, and Zed Moss is above the L3 level (in no L4 team)."""
    sup_org = {"erook6": "Lending Platform (Emery Rook)", "pat1": "Lending Platform (Emery Rook)",
               "sam2": "Lending Platform (Emery Rook)", "dpark4": "Lending Reporting (Dee Park)"}
    hr_people = [{"sam_account": sam, "worker": name, "family_id": "lending", "email": f"{sam}@example.test",
                  "manager_sam": manager, "reporting_level": level, "sup_org": sup_org.get(sam, "")}
                 for sam, name, manager, level in PEOPLE]
    lending = {"family_id": "lending", "family": "Lending", "owner_emails": ["lmoss3@example.test"]}
    storage.save_month("mapped", MONTH, {"month": MONTH, "team_grouping": "l3", "settings_used": {"l3_level": 3},
                                         "feeds": {"hr": {"people": hr_people}, "teams": {"families": [lending]}}})
    things = [("person", sam, name, {}) for sam, name, _manager, _level in PEOPLE]
    things.append(("team", "family:lending", "Lending", {}))
    links = [("person", sam, "reports_to", "person", manager, "HR reporting line", None)
             for sam, _name, manager, _level in PEOPLE if manager]
    links += [("person", sam, "member_of", "team", "family:lending", "HR reporting line", None)
              for sam in ("lmoss3", "erook6", "pat1", "sam2", "dpark4")]
    storage.save_things(MONTH, things, links)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_hr_in_the_store()                                 # the group is a TRUST team, so TRUST must hold it
    return web.app.test_client()


@pytest.fixture
def signed_in(client, tmp_path, monkeypatch):
    """TRUST with the access add-on on: the person comes from the X-User header, Tech Risk from X-Groups."""
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    put_hr_in_the_store()
    return client


def as_person(sam, groups_header=""):
    return {"X-User": sam, "X-Groups": groups_header, "X-TRUST": "1"}


TECH_RISK = as_person("trisk", "TRUST-TR")


def answer(client, who, question, text):
    reply = client.post(BASE + "/answers", json={"question": question, "answer": text}, headers=who)
    assert reply.status_code == 200, reply.json


def submit(client, who):
    reply = client.post(BASE + "/submit", json={"confirm_unanswered": True}, headers=who)
    assert reply.status_code == 200, reply.json
    return reply.json


def status(client, who=None):
    return client.get(BASE + "/signoff", headers=who or as_person("erook6")).json["status"]


def submitted_by_the_lead(client):
    answer(client, as_person("pat1"), "RD12", "2")
    answer(client, as_person("pat1"), "RD01", "yes")
    submit(client, as_person("erook6"))


# ----------------------------------------------------------------------------- the lead signs off

def test_the_lead_is_the_l4_leader_found_in_hr(signed_in):
    group = groups.find(GROUP)
    assert group["grouping"] == "l4" and group["l3_id"] == "lending" and group["name"] == "Lending Platform"
    assert signoff.leads_of_group(group, MONTH) == [{"sam": "erook6", "name": "Emery Rook"}]


def test_the_lead_signs_off_and_everyone_who_can_see_the_group_sees_who_when_and_the_note(signed_in):
    client = signed_in
    submitted_by_the_lead(client)
    assert status(client) == "Submitted"

    reply = client.post(BASE + "/signoff", json={"note": "Reviewed with the team."}, headers=as_person("erook6"))
    assert reply.status_code == 200 and reply.json["status"] == "Signed off" and reply.json["flag"] is None

    seen_by_a_member = client.get(BASE + "/signoff", headers=as_person("pat1")).json
    assert seen_by_a_member["status"] == "Signed off"
    entry = seen_by_a_member["history"][0]
    assert entry["state"] == "Signed off" and entry["decided_by"] == "Emery Rook (erook6)"
    assert entry["note"] == "Reviewed with the team." and entry["decided_at"] and entry["flag"] is None

    listed = client.get("/api/risk/groups", headers=as_person("pat1")).json["groups"][0]
    assert listed["status"] == "Signed off" and listed["signoff"]["by"] == "Emery Rook (erook6)"
    again = client.post(BASE + "/signoff", json={"note": "Again."}, headers=as_person("erook6"))
    assert again.status_code == 400 and "already signed off" in again.json["error"]


def test_a_sign_off_needs_a_note(signed_in):
    submitted_by_the_lead(signed_in)
    reply = signed_in.post(BASE + "/signoff", json={"note": "  "}, headers=as_person("erook6"))
    assert reply.status_code == 400 and "Write a short note" in reply.json["error"]
    assert status(signed_in) == "Submitted"


def test_changing_an_answer_after_a_sign_off_makes_the_group_a_draft_again(signed_in):
    submitted_by_the_lead(signed_in)
    signed_in.post(BASE + "/signoff", json={"note": "ok"}, headers=as_person("erook6"))
    answer(signed_in, as_person("pat1"), "RD12", "5")
    assert status(signed_in) == "Draft"
    refused = signed_in.post(BASE + "/signoff", json={"note": "ok"}, headers=as_person("erook6"))
    assert refused.status_code == 400 and "submit again" in refused.json["error"]


# ----------------------------------------------------------------------------- a delegate

def test_a_delegate_signs_off_for_the_lead_and_can_be_cleared(signed_in):
    client = signed_in
    submitted_by_the_lead(client)
    no_delegate_yet = client.post(BASE + "/signoff", json={"note": "ok"}, headers=as_person("dpark4"))
    assert no_delegate_yet.status_code == 403

    named = client.post(BASE + "/delegate", json={"delegate_sam": "dpark4"}, headers=as_person("erook6"))
    assert named.status_code == 200 and named.json["who"]["delegates"][0]["name"] == "Dee Park"
    shown = client.get(BASE + "/signoff", headers=as_person("dpark4")).json          # a delegate can open the group to sign it
    assert shown["can_sign_off"] is True and "Dee Park may sign it off for them" in shown["who"]["sentence"]
    assert GROUP in [g["id"] for g in client.get("/api/risk/groups", headers=as_person("dpark4")).json["groups"]]

    cleared = client.post(BASE + "/delegate", json={"delegate_sam": ""}, headers=as_person("erook6"))
    assert cleared.status_code == 200 and cleared.json["who"]["delegates"] == []
    assert client.post(BASE + "/signoff", json={"note": "ok"}, headers=as_person("dpark4")).status_code == 403

    client.post(BASE + "/delegate", json={"delegate_sam": "dpark4"}, headers=as_person("erook6"))
    done = client.post(BASE + "/signoff", json={"note": "Signing for Emery."}, headers=as_person("dpark4"))
    assert done.status_code == 200
    assert client.get(BASE + "/signoff", headers=as_person("erook6")).json["history"][0]["decided_by"] == "Dee Park (dpark4)"


def test_only_the_lead_names_a_delegate_and_the_delegate_must_be_in_hr(signed_in):
    client = signed_in
    refused = client.post(BASE + "/delegate", json={"delegate_sam": "dpark4"}, headers=as_person("pat1"))
    assert refused.status_code == 403 and "Only Emery Rook" in refused.json["error"]
    unknown = client.post(BASE + "/delegate", json={"delegate_sam": "nobody"}, headers=as_person("erook6"))
    assert unknown.status_code == 400 and "isn't in the HR data" in unknown.json["error"]
    assert client.post(BASE + "/delegate", json={"delegate_sam": "dpark4"}, headers=TECH_RISK).status_code == 200


# ----------------------------------------------------------------------------- someone else is refused

def test_someone_else_is_refused_with_a_plain_reason(signed_in):
    client = signed_in
    submitted_by_the_lead(client)
    for who in (as_person("pat1"), as_person("lmoss3")):          # a team member, and the L3 above the team: neither leads it
        reply = client.post(BASE + "/signoff", json={"note": "ok"}, headers=who)
        assert reply.status_code == 403
        assert "Emery Rook leads this L4 team in HR, so Emery Rook signs this off" in reply.json["error"]
    assert client.post(BASE + "/sendback", json={"reason": "no"}, headers=as_person("pat1")).status_code == 403
    assert status(client) == "Submitted"
    assert client.post(BASE + "/signoff", json={"note": "Checked."}, headers=TECH_RISK).status_code == 200      # Tech Risk may


def test_someone_who_may_not_open_the_team_is_refused_without_being_told_who_signs_off(signed_in):
    """zed9 is not in the team and not above it: signing off, sending back and naming a delegate all refuse at the door."""
    client = signed_in
    submitted_by_the_lead(client)
    stranger = as_person("zed9")
    for path, body in (("/signoff", {"note": "ok"}), ("/sendback", {"reason": "no"}), ("/delegate", {"delegate_sam": "dpark4"})):
        reply = client.post(BASE + path, json=body, headers=stranger)
        assert reply.status_code == 403
        assert reply.json["error"].startswith("You can't see this team") and "Emery Rook" not in reply.json["error"]
    assert status(client) == "Submitted"


# ----------------------------------------------------------------------------- send back

def test_send_back_returns_it_to_the_team_with_the_reason_and_keeps_the_earlier_assessment(signed_in):
    client = signed_in
    submitted_by_the_lead(client)
    no_reason = client.post(BASE + "/sendback", json={"reason": ""}, headers=as_person("erook6"))
    assert no_reason.status_code == 400 and "reason" in no_reason.json["error"]

    sent = client.post(BASE + "/sendback", json={"reason": "RD12 looks too low."}, headers=as_person("erook6"))
    assert sent.status_code == 200 and sent.json["status"] == "Sent back"
    form = client.get(BASE, headers=as_person("pat1")).json["group"]
    assert form["status"] == "Sent back" and form["signoff"]["note"] == "RD12 looks too low."
    shown = client.get(BASE + "/signoff", headers=as_person("pat1")).json
    assert shown["sent_back_reason"] == "RD12 looks too low." and shown["can_sign_off"] is False
    assert client.post(BASE + "/answers", json={"question": "RD12", "answer": "4"}, headers=as_person("pat1")).json["status"] == "Sent back"

    submit(client, as_person("erook6"))                                         # a new assessment, as today
    assert status(client) == "Submitted"
    assert len(storage.risk_assessments(GROUP)) == 2
    states = [(entry["assessment_id"], entry["state"]) for entry in client.get(BASE + "/signoff", headers=as_person("erook6")).json["history"]]
    assert states == [(2, "Submitted"), (1, "Sent back")]
    assert client.post(BASE + "/signoff", json={"note": "Better."}, headers=as_person("erook6")).status_code == 200


# ----------------------------------------------------------------------------- the flag

def test_the_flag_when_the_signer_also_changed_answers_in_this_assessment_and_it_does_not_block(signed_in):
    client = signed_in
    answer(client, as_person("pat1"), "RD12", "2")
    answer(client, as_person("erook6"), "RD01", "yes")                        # the lead may answer too
    answer(client, as_person("erook6"), "RD02", "no")
    answer(client, as_person("erook6"), "RD02", "yes")                        # the same question twice counts once
    submit(client, as_person("erook6"))

    signed = client.post(BASE + "/signoff", json={"note": "Fine."}, headers=as_person("erook6"))
    assert signed.status_code == 200 and signed.json["status"] == "Signed off"
    assert signed.json["flag"] == "Emery Rook (erook6) also changed 2 answers in this assessment."
    entry = client.get(BASE + "/signoff", headers=as_person("pat1")).json["history"][0]
    assert entry["also_changed"] is True and entry["flag"] == signed.json["flag"]


def test_answers_from_an_earlier_assessment_do_not_count(signed_in):
    client = signed_in
    answer(client, as_person("erook6"), "RD01", "yes")
    submit(client, as_person("erook6"))
    client.post(BASE + "/sendback", json={"reason": "again"}, headers=as_person("erook6"))
    answer(client, as_person("pat1"), "RD12", "3")
    submit(client, as_person("erook6"))
    signed = client.post(BASE + "/signoff", json={"note": "ok"}, headers=as_person("erook6"))
    assert signed.json["flag"] is None
    assert client.get(BASE + "/signoff", headers=as_person("pat1")).json["history"][1]["state"] == "Sent back"


def test_two_names_for_the_same_person():
    assert signoff.same_person("Lee Moss (lmoss3)", "lmoss3")
    assert signoff.same_person("  rita  tester ", "Rita Tester")
    assert not signoff.same_person("Emery Rook (erook6)", "Pat Lee (pat1)")
    assert not signoff.same_person("", "")


# ----------------------------------------------------------------------------- the other ways to find the lead

def with_access(tmp_path, monkeypatch):
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))


def test_the_l3_lead_may_open_the_l4_team_but_does_not_sign_it_off(client, tmp_path, monkeypatch):
    """Lee Moss leads the L3 team Lending. Emery Rook leads the L4 team, so only Emery (or a delegate, or Tech Risk) signs."""
    with_access(tmp_path, monkeypatch)
    submitted_by_the_lead(client)
    shown = client.get(BASE + "/signoff", headers=as_person("erook6")).json
    assert shown["who"]["first"] == "lead" and shown["who"]["sentence"].startswith("Emery Rook leads this L4 team in HR")
    assert client.get(BASE, headers=as_person("lmoss3")).status_code == 200                      # the L3 lead may open it
    assert client.post(BASE + "/signoff", json={"note": "no"}, headers=as_person("lmoss3")).status_code == 403
    assert client.post(BASE + "/signoff", json={"note": "no"}, headers=as_person("dpark4")).status_code == 403   # another L4 leader
    assert client.post(BASE + "/signoff", json={"note": "Mine."}, headers=as_person("erook6")).json["status"] == "Signed off"


def test_when_no_lead_is_found_only_tech_risk_signs_off(client, tmp_path, monkeypatch):
    """An L4 team always has its leader, so this is the safety net: a group with no lead falls back to Tech Risk."""
    with_access(tmp_path, monkeypatch)
    group = dict(groups.find(GROUP), leads=[])
    who = signoff.who_signs(group, MONTH, [])
    assert who["first"] == "tech_risk" and who["sentence"] == "We couldn't find who leads this team, so Tech Risk signs this off."
    ok, _why = signoff.may_sign_off({"open": False, "sam": "erook6", "roles": set(), "lead_of": set(), "member_of": set()}, group, MONTH, [])
    assert ok is False


def test_a_stranger_cannot_sign_off_or_name_a_delegate_with_a_lead_found(signed_in):
    submitted_by_the_lead(signed_in)
    assert signed_in.post(BASE + "/signoff", json={"note": "ok"}, headers=as_person("zed9")).status_code == 403
    assert signed_in.post(BASE + "/delegate", json={"delegate_sam": "zed9"}, headers=as_person("zed9")).status_code == 403
    assert status(signed_in) == "Submitted"


# ----------------------------------------------------------------------------- open

def test_while_trust_runs_open_anyone_signs_off_with_a_typed_name(client):
    answer_reply = client.post(BASE + "/answers", json={"question": "RD12", "answer": "2", "by": "Rita"}, headers={"X-TRUST": "1"})
    assert answer_reply.status_code == 200
    client.post(BASE + "/submit", json={"by": "Rita", "confirm_unanswered": True}, headers={"X-TRUST": "1"})

    headers = {"X-TRUST": "1"}
    assert client.post(BASE + "/signoff", json={"note": "ok"}, headers=headers).status_code == 400          # needs a name
    assert client.post(BASE + "/signoff", json={"note": "ok", "by": "Rita"}, headers={}).status_code != 200   # needs the header
    signed = client.post(BASE + "/signoff", json={"note": "ok", "by": "Sam Typed"}, headers=headers)
    assert signed.status_code == 200 and signed.json["flag"] is None
    shown = client.get(BASE + "/signoff").json
    assert shown["open"] is True and shown["history"][0]["decided_by"] == "Sam Typed"


def test_a_group_nobody_submitted_has_nothing_to_sign_off(client):
    reply = client.post(BASE + "/signoff", json={"note": "ok", "by": "Rita"}, headers={"X-TRUST": "1"})
    assert reply.status_code == 400 and "Nothing has been submitted" in reply.json["error"]


# ----------------------------------------------------------------------------- the database

PG_BIN = pathlib.Path(os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin"))
SIGNOFF_PG_PORT = 8731


@pytest.mark.skipif(not (PG_BIN / "initdb").exists(), reason="Postgres programs not installed")
def test_sign_offs_are_kept_in_the_database_too(monkeypatch):
    from trust import migrate
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    base = pathlib.Path(tempfile.mkdtemp(prefix="trust-signoff-pg-"))
    data, sock = base / "data", base / "sock"
    sock.mkdir()
    as_user = []
    if os.geteuid() == 0:
        shutil.chown(base, "postgres")
        shutil.chown(sock, "postgres")
        as_user = ["runuser", "-u", "postgres", "--"]
    run = lambda *command: subprocess.run([*as_user, *command], check=True, capture_output=True)
    run(str(PG_BIN / "initdb"), "-D", str(data), "-U", "trust", "--auth=trust", "-E", "UTF8")
    run(str(PG_BIN / "pg_ctl"), "-D", str(data), "-w", "-l", str(base / "log"),
        "-o", f"-k {sock} -c listen_addresses='' -p {SIGNOFF_PG_PORT}", "start")
    try:
        monkeypatch.setenv("DATABASE_URL", f"postgresql://trust@/postgres?host={sock}&port={SIGNOFF_PG_PORT}")
        migrate.run()
        put_hr_in_the_store()
        client = web.app.test_client()
        headers = {"X-TRUST": "1"}
        client.post(BASE + "/answers", json={"question": "RD12", "answer": "2", "by": "Rita"}, headers=headers)
        client.post(BASE + "/submit", json={"by": "Rita", "confirm_unanswered": True}, headers=headers)
        assert client.post(BASE + "/signoff", json={"note": "ok", "by": "Rita"}, headers=headers).status_code == 200
        rows = storage.risk_signoffs(GROUP)
        assert [(row["kind"], row["by"], row["also_changed"]) for row in rows] == [("signoff", "Rita", True)]
        listed = client.get("/api/risk/groups").json["groups"]
        assert {entry["id"]: entry["status"] for entry in listed}[GROUP] == "Signed off"
    finally:
        run(str(PG_BIN / "pg_ctl"), "-D", str(data), "-w", "-m", "immediate", "stop")
        shutil.rmtree(base, ignore_errors=True)


# ----------------------------------------------------------------------------- who may use what else on the Risk site

def test_comparing_with_the_engine_is_for_tech_risk(signed_in):
    client = signed_in
    for path in (BASE + "/compare", "/api/risk/compare"):
        assert client.get(path, headers=as_person("erook6")).status_code == 403
        assert client.get(path, headers=TECH_RISK).status_code == 200
    uploaded = client.post(BASE + "/engine-output?by=Erin", data=b"{}", headers=as_person("erook6"))
    assert uploaded.status_code == 403


def test_a_service_account_that_only_sends_metric_numbers_is_kept_off_the_risk_site(signed_in, tmp_path, monkeypatch):
    access = tmp_path / "access-with-senders.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups",
                                  "groups": {"tech_risk": ["TRUST-TR"], "data_sender": ["TRUST-SENDERS"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    sender = as_person("svc-lending", "TRUST-SENDERS")
    for path in ("/api/risk/registers", "/api/risk/download", "/api/risk/matrix", "/api/risk/seed", "/api/edit", "/api/edit/questions"):
        assert signed_in.get(path, headers=sender).status_code == 403, path
    assert signed_in.get("/api/risk/registers", headers=TECH_RISK).status_code == 200
