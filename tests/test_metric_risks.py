"""The list "Risks each metric watches" (owner, 16 Nov 2026): Tech Risk picks the risks each metric watches, and
everything that reads them (the CTO view markers, the metric dictionary card) uses the edited value.

Worked example, made-up teams: nothing is mapped to start. Tech Risk maps SE-01 to air.cyber.01. Lending's Elevated
risk is air.cyber.01, so with SE-01's marker On, the CTO view marks Lending.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, editable, score_month, web  # noqa: E402
from test_cto_risk_markers import MARKERS, ROOT, TEST_RISKS, submit_assessment  # noqa: E402,F401
from risk_teams import put_made_up_teams  # noqa: E402

SAVE = "/api/edit/metric-risks/save"
LIST = "/api/edit/metric-risks"
HEADERS = {"X-TRUST": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A site with made-up teams and risk files, and the real metrics file (no metric watches a risk to start)."""
    monkeypatch.setenv("TRUST_METRICS", str(ROOT / "config" / "metrics.json"))
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


def pick(client, metric_id, risk_ids, reason="Mapping the risks"):
    return client.post(SAVE, json={"by": "Tess", "action": "edit", "key": metric_id, "values": {"risk_ids": risk_ids},
                                   "reason": reason}, headers=HEADERS)


def test_every_metric_is_listed_and_starts_with_the_files_value(client):
    entries = client.get(LIST).json["entries"]
    in_file = config.metrics()
    assert [entry["key"] for entry in entries] == list(in_file)          # Measured, In progress and Wanted
    assert {"Wanted", "In progress"} & {metric.get("status") for metric in in_file.values()}
    assert all(entry["values"]["risk_ids"] == "" for entry in entries)   # the file maps nothing yet
    assert editable.metric_risks("SE-01") == []


def test_picked_risks_are_what_the_cto_markers_use(client):
    submit_assessment(client, "lending--lending-platform")
    assert pick(client, "SE-01", "air.cyber.01").status_code == 200
    assert editable.metric_risks("SE-01") == ["air.cyber.01"]
    markers = client.get(MARKERS).json["markers"]
    assert [(marker["family"], marker["metric"]) for marker in markers] == [("lending", "SE-01")]
    assert markers[0]["risks"][0]["id"] == "air.cyber.01"
    assert pick(client, "SE-01", "air.ops.01").status_code == 200           # a risk Lending does not have Elevated
    assert client.get(MARKERS).json["markers"] == []


def test_the_dictionary_card_shows_the_edited_list(client):
    assert pick(client, "SE-01", "air.cyber.01, air.ops.01").status_code == 200
    card = score_month.template()["dictionary"]["metrics"]["SE-01"]
    assert [detail["id"] for detail in card["risks_detail"]] == ["air.cyber.01", "air.ops.01"]
    assert score_month.template()["dictionary"]["metrics"]["SE-02"]["risks_detail"] == []


def test_an_unknown_risk_id_is_refused_with_a_reason(client):
    reply = pick(client, "SE-01", "air.cyber.01, not.a.risk")
    assert reply.status_code == 400
    assert "'not.a.risk' is not one of the Risk site's risks" in reply.json["error"]
    assert editable.metric_risks("SE-01") == []
    assert "twice" in pick(client, "SE-01", "air.cyber.01, air.cyber.01").json["error"]


def test_a_reason_is_needed_and_history_and_download_show_the_change(client):
    assert pick(client, "SE-01", "air.cyber.01", reason="").status_code == 400
    assert pick(client, "SE-01", "air.cyber.01", reason="Cyber risk drives this metric").status_code == 200
    history = client.get(LIST).json["history"]
    assert history[0]["by"] == "Tess" and history[0]["reason"] == "Cyber risk drives this metric"
    assert history[0]["what"] == [{"label": "Risks it watches (risk IDs)", "before": "", "after": "air.cyber.01"}]
    assert "SE-01" in client.get(LIST + "/download").get_data(as_text=True)


def test_metrics_are_not_added_or_retired_here(client):
    for action in ("add", "retire"):
        reply = client.post(SAVE, json={"by": "Tess", "action": action, "key": "SE-01", "values": {}, "reason": "x"}, headers=HEADERS)
        assert reply.status_code == 400 and "fixed" in reply.json["error"]
