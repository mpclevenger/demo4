"""The Risk site's engine bridge (R8): reading the engine's output file and setting it beside the site's rating.

Every example uses the made-up risks in tools/test_risks and the made-up engine output next to them
(engine_output_example.json). The worked group is the "Lending" team, answered as in test_risk_site.py.
"""
import copy
import io
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, storage, web  # noqa: E402
from trust.risk import engine_bridge  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402
from test_risk_site import GROUP, HEADERS, WORKED_ANSWERS, answer_all, post  # noqa: E402,F401

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
EXAMPLE = json.loads((TEST_RISKS / "engine_output_example.json").read_text())


@pytest.fixture
def test_files(monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))


@pytest.fixture
def client(tmp_path, monkeypatch, test_files):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


@pytest.fixture
def submitted(client):
    answer_all(client, WORKED_ANSWERS)
    assert post(client, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True}).status_code == 200
    return client


def as_bytes(document):
    return json.dumps(document).encode("utf-8")


def upload(client, document, path=f"/api/risk/groups/{GROUP}/engine-output"):
    return client.post(path + "?by=Rita%20Tester", data=as_bytes(document), headers={**HEADERS, "Content-Type": "application/json"})


def row_for(comparison, risk_id):
    return next(row for row in comparison["rows"] if row["risk_id"] == risk_id)


# ----------------------------------------------------------------------------- reading the engine's file

def test_the_example_file_reads_cleanly():
    """8 risks, 5 active drivers, nothing to complain about."""
    parsed = engine_bridge.read_engine_output(as_bytes(EXAMPLE))
    assert len(parsed["risks"]) == 8
    assert parsed["active_drivers"] == ["RD01", "RD02", "RD03", "RD23", "RD54"]
    assert parsed["problems"] == []


def test_level_words_can_be_any_case_and_optional_sections_can_be_missing():
    parsed = engine_bridge.read_engine_output(as_bytes({"risks": {"air.cyber.01": {"likelihood": " high ", "impact": "CRITICAL"}}}))
    assert parsed["risks"]["air.cyber.01"] == {"likelihood": "HIGH", "impact": "CRITICAL", "applicable": True, "drivers": {}}
    assert parsed["active_drivers"] is None
    assert len(parsed["problems"]) == 2                  # no schema_version, no active_drivers


def test_an_unknown_level_word_is_noted_in_plain_words_and_read_as_no_rating():
    parsed = engine_bridge.read_engine_output(as_bytes({"schema_version": "2.0", "active_drivers": [],
                                                       "risks": {"air.cyber.01": {"likelihood": "Severe", "impact": "High"}}}))
    assert parsed["risks"]["air.cyber.01"]["likelihood"] is None
    assert "'Severe' isn't one of Low, Medium, High or Critical" in parsed["problems"][0]


@pytest.mark.parametrize("raw, words", [(b"not json", "isn't JSON"), (b"[1, 2]", "isn't an engine output file"),
                                        (b'{"schema_version": "2.0"}', "no 'risks' section")])
def test_a_file_that_cannot_be_read_says_why(raw, words):
    with pytest.raises(engine_bridge.CannotRead) as problem:
        engine_bridge.read_engine_output(raw)
    assert words in str(problem.value)


# ----------------------------------------------------------------------------- the worked comparisons

def test_engine_high_and_site_high_is_the_same(submitted):
    """air.cyber.02: the engine says Low likelihood and High impact; the site says the same, so it is Same.
    air.cyber.01 is High / Critical on both sides."""
    document = copy.deepcopy(EXAMPLE)
    document["risks"]["air.cyber.02"] = {"likelihood": "Low", "impact": "High", "applicable": True}
    reply = upload(submitted, document)
    comparison = reply.json["comparison"]
    assert row_for(comparison, "air.cyber.02")["result"] == "Same"          # engine Low = site Low, engine High = site High
    assert row_for(comparison, "air.cyber.01")["result"] == "Same"          # High / Critical on both sides


def test_engine_critical_and_site_high_is_different_with_the_reason(submitted):
    """air.cyber.02 impact: the engine says Critical, the site says High. The reason repeats the site's own steps."""
    document = copy.deepcopy(EXAMPLE)
    document["risks"]["air.cyber.02"]["impact"] = "CRITICAL"
    comparison = upload(submitted, document).json["comparison"]
    row = row_for(comparison, "air.cyber.02")
    assert row["result"] == "Different"
    assert "The engine says Critical impact; the site says High." in row["reasons"]
    assert any(line.startswith("How the site rated impact:") for line in row["reasons"])


def test_a_driver_on_in_only_one_place_is_named_in_the_reason(submitted):
    """The engine says RD36 is on; the site says it is off. air.cyber.01 lists RD36, so the reason names it."""
    document = copy.deepcopy(EXAMPLE)
    document["active_drivers"].append("RD36")
    document["risks"]["air.cyber.01"]["likelihood"] = "Critical"
    comparison = upload(submitted, document).json["comparison"]
    row = row_for(comparison, "air.cyber.01")
    assert row["result"] == "Different"
    assert "RD36 is on in the engine but not on the site" in " ".join(row["reasons"])
    assert [entry["code"] for entry in comparison["drivers"]["on_in_engine_only"]] == ["RD36"]
    assert comparison["drivers"]["on_on_site_only"] == []


def test_site_medium_where_the_engine_has_no_rating_is_site_only(submitted):
    """air.change.01: the site says Medium likelihood; the engine has none. Impact Critical matches."""
    comparison = upload(submitted, EXAMPLE).json["comparison"]
    row = row_for(comparison, "air.change.01")
    assert row["result"] == "Site only"
    assert "Medium and Low are new on the site" in row["reasons"][0]


def test_the_example_gives_one_same_and_seven_site_only(submitted):
    comparison = upload(submitted, EXAMPLE).json["comparison"]
    assert comparison["counts"] == {"same": 1, "different": 0, "site_only": 7, "engine_only": 0}
    assert comparison["summary"] == "1 risk the same, 0 different, 7 site only"


def test_a_risk_the_site_does_not_have_is_engine_only(submitted):
    document = copy.deepcopy(EXAMPLE)
    document["risks"]["air.made.99"] = {"likelihood": "High", "impact": "High"}
    comparison = upload(submitted, document).json["comparison"]
    assert row_for(comparison, "air.made.99")["result"] == "Engine only"
    assert comparison["counts"]["engine_only"] == 1


def test_a_risk_the_engine_says_does_not_apply_while_the_site_rates_it_high_is_different(submitted):
    document = copy.deepcopy(EXAMPLE)
    document["risks"]["air.cyber.02"] = {"applicable": False}
    row = row_for(upload(submitted, document).json["comparison"], "air.cyber.02")
    assert row["result"] == "Different"
    assert row["reasons"][0].startswith("The engine says this risk does not apply; the site says it does")


def test_the_differences_are_listed_first(submitted):
    document = copy.deepcopy(EXAMPLE)
    document["risks"]["air.ops.02"]["impact"] = "Critical"
    rows = upload(submitted, document).json["comparison"]["rows"]
    assert rows[0]["risk_id"] == "air.ops.02" and rows[0]["result"] == "Different"


# ----------------------------------------------------------------------------- the routes

def test_nothing_to_compare_before_a_file_or_a_submit(client):
    reply = client.get(f"/api/risk/groups/{GROUP}/compare")
    assert reply.json["comparison"] is None and "No engine file" in reply.json["why_not"]
    document = upload(client, EXAMPLE).json
    assert document["comparison"] is None and "hasn't been submitted" in document["why_not"]


def test_an_unreadable_upload_is_refused_in_plain_words(client):
    reply = client.post(f"/api/risk/groups/{GROUP}/engine-output?by=Rita", data=b"nope", headers=HEADERS)
    assert reply.status_code == 400 and "isn't JSON" in reply.json["error"]
    assert storage.risk_engine_runs(GROUP) == []


def test_an_upload_needs_a_name_and_the_header(client):
    assert client.post(f"/api/risk/groups/{GROUP}/engine-output", data=as_bytes(EXAMPLE), headers=HEADERS).status_code == 400
    assert client.post(f"/api/risk/groups/{GROUP}/engine-output?by=Rita", data=as_bytes(EXAMPLE)).status_code in (400, 403)


def test_a_file_upload_is_kept_with_who_and_a_hash(submitted):
    reply = submitted.post(f"/api/risk/groups/{GROUP}/engine-output", headers=HEADERS,
                           data={"by": "Rita Tester", "file": (io.BytesIO(as_bytes(EXAMPLE)), "engine.json")},
                           content_type="multipart/form-data")
    assert reply.status_code == 200
    kept = storage.risk_engine_runs(GROUP)
    assert len(kept) == 1 and kept[0]["by"] == "Rita Tester"
    assert kept[0]["file_hash"] == engine_bridge.file_hash(as_bytes(EXAMPLE))
    assert reply.json["comparison"]["assessment"]["id"] == 1


def test_the_download_is_the_groups_answers_as_the_driver_rules_read_them(submitted):
    reply = submitted.get(f"/api/risk/groups/{GROUP}/engine-input")
    assert "attachment" in reply.headers["Content-Disposition"]
    document = reply.json
    assert "Wanted: confirm this layout" in document["_layout"]
    assert document["group"]["id"] == GROUP
    assert document["answers"]["RD01"] is True and document["answers"]["RD12"] == 2 and document["answers"]["RD14_pct"] == 0.25


def test_the_all_groups_page_lists_each_groups_last_result(submitted):
    upload(submitted, EXAMPLE)
    groups = submitted.get("/api/risk/compare").json["groups"]
    lending = next(group for group in groups if group["id"] == GROUP)
    assert lending["summary"] == "1 risk the same, 0 different, 7 site only"
    assert next(group for group in groups if group["id"] == "payments")["summary"] is None
