"""Metric intake (owner, 15 Nov 2026): the record and its three stages, the standard layout (version 1) with each
rule and a worked example, and the door teams send their numbers through. Nothing here scores anything."""
import io
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import metric_intake_rules as rules  # noqa: E402
from trust import storage, web  # noqa: E402

OPEN = {"X-TRUST": "1"}
SERVICE = "svc-lending"
WANTED = {"name": "Apps with a tested restore", "tells_leadership": "Whether we could get an application back after a failure.",
          "building_block": "Resiliency", "provider_team": "Lending Platform", "contact_name": "Pat Doe",
          "system": "Restore test tracker"}
IN_PROGRESS = {"counted_label": "applications with a restore test in the last 12 months",
               "measured_against_label": "applications in the inventory", "unit": "%", "direction": "higher",
               "key_type": "application", "shape": "totals", "cadence": "monthly", "arrival": "api",
               "service_account": SERVICE, "approved_by": "Sam Lee", "approved_on": "2026-11-10"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    return web.app.test_client()


def post(client, path, body, headers=None):
    return client.post(path, json=body, headers=headers or OPEN)


def add_record(client, fields=None, headers=None, by="Tech Risk"):
    r = post(client, "/api/metric-intake", {"by": by, "fields": fields or WANTED}, headers)
    assert r.status_code == 200, r.json
    return r.json["record"]


def make_in_progress(client, shape="totals", key_type="application", headers=None, by="Tech Risk", account=SERVICE):
    record = add_record(client, headers=headers, by=by)
    fields = {**IN_PROGRESS, "shape": shape, "key_type": key_type, "service_account": account}
    r = post(client, "/api/metric-intake", {"by": by, "id": record["id"], "fields": fields, "stage": "In progress"}, headers)
    assert r.status_code == 200, r.json
    return r.json["record"]


def totals_row(key="APP-1", count=3, total=4, month="2026-10", **more):
    return {"intake_id": "MI-001", "month": month, "key_type": "application", "key": key, "count": count,
            "total": total, "as_of": "2026-11-02", **more}


def items_row(item_id, counted, key="APP-1", month="2026-10"):
    return {"intake_id": "MI-001", "month": month, "item_id": item_id, "item_name": f"Item {item_id}",
            "key_type": "application", "key": key, "counted": counted, "as_of": "2026-11-02"}


# ---- (A) the record: stages and the plain missing-field messages ----

def test_a_new_record_starts_as_wanted_with_a_short_id_and_counts_in_no_score(client):
    record = add_record(client)
    assert record["id"] == "MI-001" and record["stage"] == "Wanted"
    assert add_record(client)["id"] == "MI-002"
    assert record["created_by"] == "Tech Risk"


def test_adding_a_record_names_what_is_missing(client):
    r = post(client, "/api/metric-intake", {"by": "Tech Risk", "fields": {"name": "Something"}})
    assert r.status_code == 400
    for label in ("What it tells leadership", "Building block", "Provider team", "Contact name", "System the data lives in"):
        assert label in r.json["error"]
    assert "Metric name" not in r.json["error"]


def test_building_block_must_be_one_of_the_six(client):
    r = post(client, "/api/metric-intake", {"by": "Tech Risk", "fields": {**WANTED, "building_block": "Vibes"}})
    assert r.status_code == 400 and "Building block must be one of" in r.json["error"]


def test_moving_to_in_progress_says_plainly_what_is_missing(client):
    record = add_record(client)
    r = post(client, "/api/metric-intake", {"by": "Tech Risk", "id": record["id"], "stage": "In progress"})
    assert r.status_code == 400
    error = r.json["error"]
    assert error.startswith("To move this to In progress, fill in:")
    assert "What is counted" in error and "Service account that will send it" not in error   # not needed until the team sends by API
    assert "Who approved on the provider's side" in error


def test_the_service_account_is_needed_only_when_the_team_sends_by_api(client):
    record = add_record(client)
    fields = {**IN_PROGRESS, "service_account": "", "arrival": "api"}
    r = post(client, "/api/metric-intake", {"by": "TR", "id": record["id"], "fields": fields, "stage": "In progress"})
    assert r.status_code == 400 and "Service account that will send it" in r.json["error"]
    fields["arrival"] = "file"
    r = post(client, "/api/metric-intake", {"by": "TR", "id": record["id"], "fields": fields, "stage": "In progress"})
    assert r.status_code == 200 and r.json["record"]["stage"] == "In progress"


def test_a_complete_record_moves_to_in_progress_and_history_keeps_who_and_when(client):
    record = make_in_progress(client, by="Ana Tech")
    assert record["stage"] == "In progress" and record["missing_for_in_progress"] == []
    history = client.get("/api/metric-intake").json["history"]["MI-001"]
    assert [h["action"] for h in history] == ["added", "changed", "moved"]
    assert history[-1]["by"] == "Ana Tech" and history[-1]["at"]
    assert history[-1]["before"] == {"stage": "Wanted"} and history[-1]["after"] == {"stage": "In progress"}


def test_a_change_adds_history_and_never_overwrites_it(client):
    record = make_in_progress(client)
    post(client, "/api/metric-intake", {"by": "Bo", "id": record["id"], "fields": {"contact_name": "Lee Roe"}})
    post(client, "/api/metric-intake", {"by": "Bo", "id": record["id"], "fields": {"contact_name": "Kim Poe"}})
    history = client.get("/api/metric-intake").json["history"]["MI-001"]
    contact_changes = [h for h in history if h["action"] == "changed" and "contact_name" in (h["after"] or {})]
    assert [(h["before"]["contact_name"], h["after"]["contact_name"]) for h in contact_changes][-2:] == [("Pat Doe", "Lee Roe"), ("Lee Roe", "Kim Poe")]


def test_wanted_cannot_skip_to_measured_and_measured_needs_a_note(client):
    wanted = add_record(client)
    r = post(client, "/api/metric-intake", {"by": "TR", "id": wanted["id"], "stage": "Measured"})
    assert r.status_code == 400 and "In progress first" in r.json["error"]
    record = make_in_progress(client)
    r = post(client, "/api/metric-intake", {"by": "TR", "id": record["id"], "stage": "Measured"})
    assert r.status_code == 400 and "usual metric approval" in r.json["error"]
    r = post(client, "/api/metric-intake", {"by": "TR", "id": record["id"], "stage": "Measured", "note": "Approved in proposal 12"})
    assert r.status_code == 200 and r.json["record"]["stage"] == "Measured"
    assert "does not create a metric" in r.json["message"]


def test_the_page_must_type_a_name_while_trust_runs_open(client):
    r = post(client, "/api/metric-intake", {"fields": WANTED})
    assert r.status_code == 400 and "Type your name" in r.json["error"]


def test_the_header_is_needed_like_every_other_change(client):
    r = client.post("/api/metric-intake", json={"by": "x", "fields": WANTED})
    assert r.status_code == 403
    r = client.post("/api/metric-values", json={"by": "x"})
    assert r.status_code == 403


def test_shape_cannot_change_once_numbers_were_received(client):
    record = make_in_progress(client)
    assert post(client, "/api/metric-values", {"by": "x", "intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]}).status_code == 200
    r = post(client, "/api/metric-intake", {"by": "TR", "id": record["id"], "fields": {"shape": "items"}})
    assert r.status_code == 400 and "already been received" in r.json["error"]


# ---- (B) the layout rules, one worked example each ----

def test_rule_count_is_not_more_than_total():
    assert rules.count_is_not_more_than_total(3, 4) is None
    assert rules.count_is_not_more_than_total(4, 4) is None
    assert "more than the total" in rules.count_is_not_more_than_total(9, 7)


def test_rule_a_count_is_a_whole_number():
    assert rules.whole_number("12", "count") == (12, None)
    assert rules.whole_number("1.5", "count")[0] is None
    assert rules.whole_number("-3", "count")[0] is None
    assert "whole number" in rules.whole_number("seven", "total")[1]


def test_rule_month_is_well_formed():
    assert rules.month_is_well_formed("2026-10")
    for bad in ("2026-13", "Oct 2026", "2026-1", "", None, "2026-10-01"):
        assert not rules.month_is_well_formed(bad)


def test_rule_as_of_is_a_real_date():
    assert rules.date_is_well_formed("2026-10-31")
    assert not rules.date_is_well_formed("2026-02-30")
    assert not rules.date_is_well_formed("31/10/2026")


def test_rule_key_type_is_one_of_the_three_and_matches_the_record():
    assert rules.key_type_is_known_and_matches("application", "application") is None
    assert "must be application, repository or person" in rules.key_type_is_known_and_matches("team", "application")
    assert "ties each row to a repository" in rules.key_type_is_known_and_matches("application", "repository")


def test_rule_the_intake_id_exists_and_is_in_progress_or_measured():
    assert "There is no metric MI-009" in rules.record_can_receive(None, "MI-009")
    assert "is Wanted" in rules.record_can_receive({"id": "MI-001", "stage": "Wanted"}, "MI-001")
    assert rules.record_can_receive({"id": "MI-001", "stage": "In progress"}, "MI-001") is None
    assert rules.record_can_receive({"id": "MI-001", "stage": "Measured"}, "MI-001") is None


def test_rule_an_items_file_counts_the_yes_rows_out_of_all_rows():
    items = [{"counted": True}, {"counted": True}, {"counted": False}, {"counted": True}]
    assert rules.count_and_total_from_items(items) == (3, 4)      # three of four items counted


def test_rule_counted_is_yes_or_no():
    assert rules.counted_is_yes_or_no("Yes") == (True, None)
    assert rules.counted_is_yes_or_no(" no ") == (False, None)
    assert rules.counted_is_yes_or_no("maybe")[0] is None


def test_a_totals_file_sets_aside_each_bad_row_with_its_reason():
    record = {"key_type": "application"}
    rows = [totals_row("APP-1", 3, 4), totals_row("APP-2", 9, 7), totals_row("APP-3", "x", 5),
            totals_row("APP-4", 1, 2, as_of="soon"), totals_row("APP-1", 1, 1), totals_row("APP-5", 1, 2, month="2026-09"),
            {**totals_row("APP-6"), "key_type": "repository"}]
    kept, aside = rules.check_totals_rows(rows, record, "MI-001", "2026-10")
    assert [r["key"] for r in kept] == ["APP-1"]
    assert [a["row_number"] for a in aside] == [2, 3, 4, 5, 6, 7]
    reasons = " | ".join(a["reason"] for a in aside)
    for fragment in ("more than the total", "whole number", "as_of must be", "already has a row", "this send is for 2026-10", "ties each row to an application"):
        assert fragment in reasons


# ---- (C) the door: a Totals send and an Items send, end to end ----

def test_a_totals_send_is_checked_stored_and_answered(client):
    make_in_progress(client)
    rows = [totals_row("APP-1", 3, 4), totals_row("APP-2", 9, 7)]
    r = post(client, "/api/metric-values", {"by": "Svc", "intake_id": "MI-001", "month": "2026-10", "shape": "totals", "rows": rows})
    assert r.status_code == 200, r.json
    assert (r.json["rows_received"], r.json["rows_kept"], r.json["rows_set_aside"]) == (2, 1, 1)
    assert r.json["set_aside"][0]["row_number"] == 2 and "more than the total" in r.json["set_aside"][0]["reason"]
    assert r.json["scored"] is False and r.json["replaced_earlier_send"] is False
    listing = client.get("/api/metric-intake").json
    month = listing["received"]["MI-001"]["2026-10"]
    assert (month["rows_kept"], month["rows_set_aside"], month["by"]) == (1, 1, "Svc")
    assert month["totals"] == [{"key_type": "application", "key": "APP-1", "count": 3, "total": 4, "as_of": "2026-11-02"}]


def test_a_second_send_replaces_the_first_for_display_and_both_are_kept(client):
    make_in_progress(client)
    send = lambda n: post(client, "/api/metric-values", {"by": "Svc", "intake_id": "MI-001", "month": "2026-10",
                                                          "rows": [totals_row("APP-1", n, 10)]})
    assert send(2).json["replaced_earlier_send"] is False
    second = send(5)
    assert second.json["replaced_earlier_send"] is True and "replaces the earlier send" in second.json["message"]
    month = client.get("/api/metric-intake").json["received"]["MI-001"]["2026-10"]
    assert month["totals"][0]["count"] == 5 and month["sends"] == 2 and len(month["earlier"]) == 1
    assert len(storage.intake_sends("MI-001", "2026-10")) == 2
    detail = client.get("/api/metric-intake/MI-001/2026-10").json
    assert detail["rows_kept"][0]["count"] == 5 and len(detail["sends"]) == 2


def test_an_items_send_works_out_count_and_total_from_the_rows(client):
    make_in_progress(client, shape="items")
    rows = [items_row("a", "yes"), items_row("b", "yes"), items_row("c", "no"), items_row("d", "yes"),
            items_row("e", "maybe"), items_row("a", "no"), items_row("f", "yes", key="APP-2")]
    r = post(client, "/api/metric-values", {"by": "Svc", "intake_id": "MI-001", "month": "2026-10", "shape": "items", "rows": rows})
    assert r.status_code == 200, r.json
    assert (r.json["rows_kept"], r.json["rows_set_aside"]) == (5, 2)
    reasons = " | ".join(a["reason"] for a in r.json["set_aside"])
    assert "counted must be yes or no" in reasons and "already has a row" in reasons
    by_key = {t["key"]: (t["count"], t["total"]) for t in r.json["totals"]}
    assert by_key == {"APP-1": (3, 4), "APP-2": (1, 1)}


def test_a_csv_file_is_accepted_in_the_field_called_file(client):
    make_in_progress(client)
    csv_text = ("intake_id,month,key_type,key,count,total,as_of\n"
                "MI-001,2026-10,application,APP-1,3,4,2026-11-02\nMI-001,2026-10,application,APP-2,0,2,2026-11-02\n")
    r = client.post("/api/metric-values", data={"by": "Svc", "file": (io.BytesIO(csv_text.encode()), "x.csv")},
                    headers=OPEN, content_type="multipart/form-data")
    assert r.status_code == 200, r.json
    assert (r.json["intake_id"], r.json["month"], r.json["rows_kept"]) == ("MI-001", "2026-10", 2)


def test_a_send_for_a_wanted_record_is_refused(client):
    add_record(client)
    r = post(client, "/api/metric-values", {"by": "Svc", "intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]})
    assert r.status_code == 400 and "is Wanted" in r.json["error"] and "In progress first" in r.json["error"]
    assert storage.intake_sends() == []


def test_a_send_for_an_unknown_record_or_a_wrong_shape_or_a_bad_month_is_refused(client):
    make_in_progress(client)
    send = lambda **body: post(client, "/api/metric-values", {"by": "Svc", "rows": [totals_row()], **body})
    assert "There is no metric MI-077" in send(intake_id="MI-077", month="2026-10").json["error"]
    assert "Totals shape" in send(intake_id="MI-001", month="2026-10", shape="items").json["error"]
    assert "month must be written like 2026-10" in send(intake_id="MI-001", month="October").json["error"]
    assert "no rows" in post(client, "/api/metric-values", {"by": "x", "intake_id": "MI-001", "month": "2026-10", "rows": []}).json["error"]


def test_when_no_row_can_be_kept_nothing_is_stored_and_every_reason_is_listed(client):
    make_in_progress(client)
    r = post(client, "/api/metric-values", {"by": "Svc", "intake_id": "MI-001", "month": "2026-10", "rows": [totals_row(count=9, total=1)]})
    assert r.status_code == 400 and r.json["rows_set_aside"] == 1 and "more than the total" in r.json["set_aside"][0]["reason"]
    assert storage.intake_sends() == []


def test_sending_scores_nothing(client):
    make_in_progress(client)
    post(client, "/api/metric-values", {"by": "Svc", "intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]})
    assert storage.published("data.json") is None
    assert storage.months("scored") == []


# ---- who may send, with roles on ----

CFG = {"user_header": "X-User", "groups_header": "X-Groups",
       "groups": {"cto_leadership": ["TRUST-Leaders"], "tech_risk": ["TRUST-TR"], "head_of_tech_risk": ["TRUST-HoTR"],
                  "auditor": ["TRUST-Audit"], "data_sender": ["TRUST-Senders"]},
       "family_lead_groups": {}}


def who(sam, groups=""):
    return {"X-User": sam, "X-Groups": groups, "X-TRUST": "1"}


@pytest.fixture
def roles_client(client, tmp_path, monkeypatch):
    path = tmp_path / "access.json"
    path.write_text(json.dumps(CFG))
    monkeypatch.setenv("TRUST_ACCESS", str(path))
    return client


def test_with_roles_on_the_matching_service_account_is_accepted(roles_client):
    tech_risk = who("trisk", "TRUST-TR")
    make_in_progress(roles_client, headers=tech_risk)
    body = {"intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]}
    r = post(roles_client, "/api/metric-values", body, who(SERVICE, "TRUST-Senders"))
    assert r.status_code == 200, r.json
    assert r.json["received_from"] == SERVICE                       # the account, not a typed name
    r = post(roles_client, "/api/metric-values", body, who("CORP\\" + SERVICE.upper(), "TRUST-Senders"))
    assert r.status_code == 200                                     # domain and capitals don't matter


def test_with_roles_on_a_different_service_account_is_refused_with_a_plain_reason(roles_client):
    make_in_progress(roles_client, headers=who("trisk", "TRUST-TR"))
    r = post(roles_client, "/api/metric-values", {"intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]},
             who("svc-other", "TRUST-Senders"))
    assert r.status_code == 403
    assert "not the service account named on MI-001" in r.json["error"]
    assert storage.intake_sends() == []


def test_with_roles_on_someone_with_no_role_is_refused(roles_client):
    make_in_progress(roles_client, headers=who("trisk", "TRUST-TR"))
    body = {"intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]}
    assert post(roles_client, "/api/metric-values", body, who("stranger")).status_code == 403
    assert post(roles_client, "/api/metric-values", body, who("boss", "TRUST-Leaders")).status_code == 403   # a role, but not a sender
    assert storage.intake_sends() == []


def test_tech_risk_may_send_for_any_record_and_a_sender_may_do_nothing_else(roles_client):
    make_in_progress(roles_client, headers=who("trisk", "TRUST-TR"))
    body = {"intake_id": "MI-001", "month": "2026-10", "rows": [totals_row()]}
    assert post(roles_client, "/api/metric-values", body, who("trisk", "TRUST-TR")).status_code == 200
    sender = who(SERVICE, "TRUST-Senders")
    assert roles_client.get("/api/metric-intake", headers=sender).status_code == 403
    assert post(roles_client, "/api/metric-intake", {"fields": WANTED}, sender).status_code == 403
    assert roles_client.get("/data.json", headers=sender).json["families"] == []        # a sender sees no family's data


def test_only_tech_risk_changes_a_record_and_an_auditor_reads(roles_client):
    assert post(roles_client, "/api/metric-intake", {"fields": WANTED}, who("boss", "TRUST-Leaders")).status_code == 403
    add_record(roles_client, headers=who("trisk", "TRUST-TR"))
    assert roles_client.get("/api/metric-intake", headers=who("auditr", "TRUST-Audit")).json["can_edit"] is False
    assert post(roles_client, "/api/metric-intake", {"fields": WANTED}, who("auditr", "TRUST-Audit")).status_code == 403
    assert roles_client.get("/api/metric-intake", headers=who("boss", "TRUST-Leaders")).status_code == 403


# ---- fixes from the independent review (15 Nov 2026) ----

def test_a_pick_one_value_is_accepted_as_its_key_or_its_word_in_any_capitals():
    from trust import metric_intake_rules as rules
    tidy = rules.tidy_fields({"shape": "Totals", "cadence": "MONTHLY", "direction": "Higher is better", "key_type": "Application"})
    assert tidy["shape"] == "totals" and tidy["cadence"] == "monthly"
    assert tidy["direction"] == "higher" and tidy["key_type"] == "application"
    assert rules.tidy_fields({"shape": "sideways"})["shape"] == "sideways"     # left for the check to refuse
