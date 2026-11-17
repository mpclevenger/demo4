"""The Apps menu's addresses: GET /api/apps."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import web  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    for variable in ("TRUST_URL", "RISK_URL", "TRAC_URL"):
        monkeypatch.delenv(variable, raising=False)
    return web.app.test_client()


def test_defaults_when_nothing_is_set(client):
    assert client.get("/api/apps").json == {"TRUST": "/", "Risk": "/risk/", "TRAC": ""}


def test_the_three_addresses_when_set(client, monkeypatch):
    monkeypatch.setenv("TRUST_URL", "https://trust.example.test/")
    monkeypatch.setenv("RISK_URL", "https://risk.example.test/")
    monkeypatch.setenv("TRAC_URL", "https://trac.example.test/")
    assert client.get("/api/apps").json == {"TRUST": "https://trust.example.test/",
                                            "Risk": "https://risk.example.test/",
                                            "TRAC": "https://trac.example.test/"}


def test_an_unset_trac_address_is_empty(client, monkeypatch):
    monkeypatch.setenv("RISK_URL", "https://risk.example.test/")
    assert client.get("/api/apps").json["TRAC"] == ""


def test_data_as_of_never_overstates():
    """An October file with no date of its own, uploaded on 5 Nov, is good to 31 Oct, not 5 Nov."""
    from trust.score_month import data_as_of
    assert data_as_of(None, "2026-11-05T09:30:00+00:00", "2026-10") == "2026-10-31"
    # uploaded before the month ended: the upload day, because the file can't hold later data
    assert data_as_of(None, "2026-10-20T09:30:00+00:00", "2026-10") == "2026-10-20"
    # a file that states its own date keeps it
    assert data_as_of("2026-10-28", "2026-11-05T09:30:00+00:00", "2026-10") == "2026-10-28"


def test_a_file_dated_by_its_upload_has_no_date_of_its_own():
    """A Checkmarx file with no report date is good to the end of its month, not to the day it was uploaded."""
    from trust.score_month import data_as_of, own_date_of
    no_report_date = {"as_of": "2026-11-15T10:00:00+00:00", "as_of_source": "upload date"}
    assert own_date_of(no_report_date) is None
    assert data_as_of(own_date_of(no_report_date), "2026-11-15T10:00:00+00:00", "2026-10") == "2026-10-31"
    with_report_date = {"as_of": "2026-10-29T00:00:00+00:00", "as_of_source": "report date in the file"}
    assert data_as_of(own_date_of(with_report_date), "2026-11-15T10:00:00+00:00", "2026-10") == "2026-10-29"


def test_the_menu_accepts_this_sites_own_paths():
    """TRUST and Risk default to "/" and "/risk/" (one app). The menu must list them, and must still refuse "//other.site"
    and anything that isn't a web address. Runs the menu's own code with Node; skipped where Node isn't installed."""
    import json
    import pathlib
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node isn't installed here")
    frontend = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "shared"
    script = "\n".join([
        "globalThis.document = {addEventListener(){}, querySelectorAll(){ return []; }, documentElement: {}};"
        " globalThis.MutationObserver = class { observe(){} };",
        (frontend / "text.js").read_text(),
        (frontend / "apps-menu.js").read_text().replace('"use strict";', ""),
        "console.log(JSON.stringify(['/', '/risk/', 'https://trac.example.test/', '//evil.test/', 'javascript:alert(1)', '', null]"
        ".map(appsmLink)));",
    ])
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["/", "/risk/", "https://trac.example.test/", "", "", "", ""]
