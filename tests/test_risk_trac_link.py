"""The Risk site and TRAC (owner, 15 Nov 2026): the download in the engine's shape, and TRAC's list of controls.

Every example uses the made-up risks and groups in tools/test_risks (TEST data only).
"""
import http.server
import io
import json
import os
import pathlib
import sys
import threading
import zipfile

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, storage, web  # noqa: E402
from trust.risk import download, trac_controls  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
# TRAC's example engine files, when a copy of the TRAC repo sits beside this one (or set TRAC_REPO to its folder).
TRAC_ENGINE_FOLDER = pathlib.Path(os.environ.get("TRAC_REPO") or pathlib.Path(__file__).resolve().parents[2] / "trac") / "content" / "engine"
HEADERS = {"X-TRUST": "1"}
GROUP = "lending--lending-platform"

# What TRAC's reader (apps/rcm/engine_files.py) accepts. Copied here so the test does not need TRAC installed.
TRAC_MAPPING_KEYS = {"trigger", "questionnaire_fields", "rationale"}
TRAC_RISK_KEYS = {"domain", "category", "name", "description", "example", "likelihood_scoring", "likelihood_drivers",
                  "impact_drivers", "impact_scoring", "framework_mappings"}
TRAC_DRIVER_ID = "RD"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_RISKS", str(TEST_RISKS))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.delenv("TRAC_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    trac_controls._last_failed_at["time"] = None
    put_made_up_teams()
    return web.app.test_client()


def sample_list(addresses):
    return {"published_at": "2026-11-15T12:00:00Z",
            "controls": [{"code": "MO-02", "title": "Job failures are followed up", "url": "https://trac.example.test/controls/MO-02/",
                          "addresses": addresses},
                         {"code": "CH-01", "title": "Changes are approved", "url": "javascript:alert(1)", "addresses": []}]}


@pytest.fixture
def trac_server(monkeypatch):
    """A tiny local web server standing in for TRAC. Change served["document"] to change what it publishes."""
    served = {"document": sample_list([])}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/registers/controls.json":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(served["document"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("TRAC_URL", f"http://127.0.0.1:{server.server_port}/")
    served["stop"] = server.shutdown
    yield served
    server.shutdown()


def fill_in_and_submit(client):
    for question in ("RD01", "RD02", "RD03"):
        client.post(f"/api/risk/groups/{GROUP}/answers", json={"question": question, "answer": "yes", "by": "Rita Tester"}, headers=HEADERS)
    return client.post(f"/api/risk/groups/{GROUP}/submit", json={"by": "Rita Tester", "confirm_unanswered": True}, headers=HEADERS)


# ---------------------------------------------------------------------------------------------------
# (a) The download
# ---------------------------------------------------------------------------------------------------

def read_the_zip(client):
    answer = client.get("/api/risk/download")
    assert answer.status_code == 200
    assert answer.headers["Content-Type"] == "application/zip"
    assert "attachment" in answer.headers["Content-Disposition"]
    return zipfile.ZipFile(io.BytesIO(answer.data))


def test_the_zip_has_the_files_trac_expects(client):
    archive = read_the_zip(client)
    expected_risk_files = {f"risks/{risk_id}.yaml" for risk_id in config.risks()}
    assert set(archive.namelist()) == {"driver_mapping.yaml"} | expected_risk_files


def test_the_files_pass_the_checks_trac_makes(client):
    """TRAC's reader wants: a risk_drivers section of RDnn ids, each with known keys; risks with a domain, category
    and name, known keys only, and every driver a risk lists present in the drivers file."""
    archive = read_the_zip(client)
    mapping = yaml.safe_load(archive.read("driver_mapping.yaml"))
    assert list(mapping) == ["risk_drivers"]
    for code, entry in mapping["risk_drivers"].items():
        assert code.startswith(TRAC_DRIVER_ID) and code[2:].isdigit() and len(code) == 4, code
        assert set(entry) == TRAC_MAPPING_KEYS
        assert isinstance(entry["questionnaire_fields"], list)
    for name in archive.namelist():
        if not name.startswith("risks/"):
            continue
        risk = yaml.safe_load(archive.read(name))
        assert set(risk) <= TRAC_RISK_KEYS, name
        for key in ("domain", "category", "name"):
            assert isinstance(risk[key], str) and risk[key].strip(), (name, key)
        for key in ("likelihood_drivers", "impact_drivers"):
            assert set(risk[key]) <= set(mapping["risk_drivers"]), (name, key)


@pytest.mark.skipif(not TRAC_ENGINE_FOLDER.exists(), reason="TRAC's example files are not on this machine")
def test_the_keys_match_trac_example_files(client):
    archive = read_the_zip(client)
    trac_mapping = yaml.safe_load((TRAC_ENGINE_FOLDER / "driver_mapping.yaml").read_text(encoding="utf-8"))
    ours = yaml.safe_load(archive.read("driver_mapping.yaml"))
    first_trac_driver = next(iter(trac_mapping["risk_drivers"].values()))
    first_driver = next(iter(ours["risk_drivers"].values()))
    assert list(first_driver) == list(first_trac_driver)
    trac_example = yaml.safe_load(next((TRAC_ENGINE_FOLDER / "risks").glob("*.yaml")).read_text(encoding="utf-8"))
    our_risk = yaml.safe_load(archive.read(next(n for n in archive.namelist() if n.startswith("risks/"))))
    trac_keys = {key.replace(" ", "_") for key in trac_example}
    assert set(our_risk) <= TRAC_RISK_KEYS
    assert {"domain", "category", "name", "likelihood_scoring", "impact_scoring"} <= set(our_risk)
    assert {"domain", "category", "name", "likelihood_scoring", "impact_scoring"} <= trac_keys


def test_what_is_downloaded_reads_back_the_same(client, tmp_path, monkeypatch):
    """Unzipped into a folder, the Risk site reads the same risks and the same driver rules."""
    archive = read_the_zip(client)
    folder = tmp_path / "unzipped"
    archive.extractall(folder)
    drivers_before = client.get("/api/risk/registers").get_json()
    risks_before = config.risks()
    monkeypatch.setenv("TRUST_RISKS", str(folder / "risks"))
    (folder / "risks" / "driver_mapping.yaml").write_bytes((folder / "driver_mapping.yaml").read_bytes())
    again = web.app.test_client().get("/api/risk/registers").get_json()
    assert set(config.risks()) == set(risks_before)
    assert again["drivers"] == drivers_before["drivers"]
    assert again["risks"] == [{**risk, "block": again_risk["block"]} for risk, again_risk in zip(drivers_before["risks"], again["risks"])]


def test_the_download_keeps_the_trigger_wording_of_the_drivers_file(client):
    archive = read_the_zip(client)
    ours = yaml.safe_load(archive.read("driver_mapping.yaml"))["risk_drivers"]
    original = yaml.safe_load((TEST_RISKS / "driver_mapping.yaml").read_text(encoding="utf-8"))["risk_drivers"]
    assert {code: entry["trigger"] for code, entry in ours.items()} == {code: entry["trigger"] for code, entry in original.items()}


# ---------------------------------------------------------------------------------------------------
# (b) TRAC's controls
# ---------------------------------------------------------------------------------------------------

def test_a_link_that_is_not_http_is_dropped_and_a_control_with_no_code_is_left_out():
    cleaned = trac_controls.clean({"published_at": "2026-11-15T12:00:00Z", "controls": [
        {"code": "CH-01", "title": "x", "url": "javascript:alert(1)", "addresses": ["air.ops.02"]}, {"title": "no code"}]})
    assert cleaned["controls"] == [{"code": "CH-01", "title": "x", "url": "", "addresses": ["air.ops.02"]}]


def test_with_no_trac_address_there_is_no_copy_and_the_site_still_works(client):
    answer = client.get("/api/risk/controls").get_json()
    assert answer["ok"] and answer["copy"] is None and answer["by_risk"] == {}
    assert fill_in_and_submit(client).status_code == 200


def refresh(client):
    return client.post("/api/risk/controls/refresh", json={"by": "Rita Tester"}, headers=HEADERS)


def test_looking_at_the_controls_fetches_nothing_and_a_refresh_keeps_the_first_copy(client, trac_server):
    trac_server["document"] = sample_list(["air.ops.02"])
    before = client.get("/api/risk/controls").get_json()
    assert before["copy"] is None and "not been fetched" in before["note"] and storage.risk_controls_copy() is None
    refreshed = refresh(client).get_json()
    assert refreshed["refreshed_by"] == "Rita Tester"
    answer = client.get("/api/risk/controls").get_json()
    assert answer["copy"]["controls"] == 2
    assert answer["by_risk"] == {"air.ops.02": [{"code": "MO-02", "title": "Job failures are followed up",
                                                 "url": "https://trac.example.test/controls/MO-02/"}]}
    assert storage.risk_controls_copy()["published_at"] == "2026-11-15T12:00:00Z"


def test_the_kept_copy_is_used_when_trac_is_down(client, trac_server):
    trac_server["document"] = sample_list(["air.ops.02"])
    refresh(client)
    trac_server["stop"]()
    answer = client.get("/api/risk/controls").get_json()
    assert "air.ops.02" in answer["by_risk"]
    refreshed = client.post("/api/risk/controls/refresh", json={"by": "Rita Tester"}, headers=HEADERS)
    assert refreshed.status_code == 502
    assert "air.ops.02" in client.get("/api/risk/controls").get_json()["by_risk"]


def test_a_refresh_needs_the_header_and_brings_a_new_copy(client, trac_server):
    assert client.post("/api/risk/controls/refresh", json={"by": "Rita Tester"}).status_code == 403
    refresh(client)
    trac_server["document"] = sample_list(["air.ops.02", "air.cyber.01"])
    refreshed = client.post("/api/risk/controls/refresh", json={"by": "Rita Tester"}, headers=HEADERS).get_json()
    assert set(refreshed["by_risk"]) == {"air.ops.02", "air.cyber.01"}
    assert len(storage._read_lines("risk_trac_controls.jsonl")) == 2


def test_a_new_assessment_notes_the_copy_and_the_rating_is_the_same(client, trac_server):
    without_controls = fill_in_and_submit(client).get_json()
    result_before = storage.risk_assessments(GROUP)[-1]["result"]
    assert result_before["controls_fetched_at"] == storage.risk_controls_copy()["fetched_at"]   # the first copy was fetched at this Submit

    trac_server["document"] = sample_list(["air.ops.02"])
    client.post("/api/risk/controls/refresh", json={"by": "Rita Tester"}, headers=HEADERS)
    copy = storage.risk_controls_copy()
    with_controls = fill_in_and_submit(client).get_json()
    result_after = storage.risk_assessments(GROUP)[-1]["result"]
    assert result_after["controls_fetched_at"] == copy["fetched_at"]
    assert copy["fetched_at"] != result_before["controls_fetched_at"]
    assert with_controls["counts"] == without_controls["counts"]
    rated_before = {key: value for key, value in result_before.items() if key not in ("controls_fetched_at", "trend", "has_previous", "risks")}
    rated_after = {key: value for key, value in result_after.items() if key not in ("controls_fetched_at", "trend", "has_previous", "risks")}
    assert rated_before == rated_after
    for risk_id, entry in result_before["risks"].items():
        later = result_after["risks"][risk_id]
        for key in ("applicable", "likelihood", "impact", "elevated"):
            assert entry.get(key) == later.get(key), (risk_id, key)


def test_a_trac_address_that_is_not_a_web_address_is_not_used(client, monkeypatch):
    for address in ("file:///etc/passwd", "ftp://trac.example.test/", "trac.example.test"):
        monkeypatch.setenv("TRAC_URL", address)
        with pytest.raises(trac_controls.CouldNotFetch, match="http://"):
            trac_controls.fetch_from_trac()


def test_a_redirect_to_something_that_is_not_a_web_address_is_refused():
    handler = trac_controls.OnlyWebRedirects()
    with pytest.raises(trac_controls.urllib.error.URLError):
        handler.redirect_request(trac_controls.urllib.request.Request("http://trac.example.test/"), None, 302, "Found", {}, "ftp://elsewhere/")


def test_an_odd_risk_id_cannot_place_a_file_outside_the_folder(client):
    names = {risk_id: download.risk_file_name(risk_id) for risk_id in ("air.ops.02", "../../evil", ".hidden", "air/ops 01", "a\\b", "")}
    assert names == {"air.ops.02": "air.ops.02", "../../evil": "_._.._evil", ".hidden": "_hidden",
                     "air/ops 01": "air_ops_01", "a\\b": "a_b", "": "_"}
    zipped = zipfile.ZipFile(io.BytesIO(download.build_zip({"risks": {"../../evil": {"domain": "Cyber", "name": "x"}}, "driver_rules": {}})))
    assert [name for name in zipped.namelist() if name.startswith("risks/")] == ["risks/_._.._evil.yaml"]
