"""Shared test set-up."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))


@pytest.fixture(autouse=True)
def default_settings(monkeypatch):
    """Tests use the settings and access files in tests/config (the defaults), never the site's own
    config/settings.json and config/access.json, so a site's settings can't make a test fail. A test that
    needs its own file sets TRUST_SETTINGS or TRUST_ACCESS itself."""
    here = pathlib.Path(__file__).resolve().parent / "config"
    monkeypatch.setenv("TRUST_SETTINGS", str(here / "settings.json"))
    monkeypatch.setenv("TRUST_ACCESS", str(here / "access.json"))


@pytest.fixture(autouse=True)
def update_waits(monkeypatch):
    """Tests see a finished update straight away; test_update_in_background.py checks the real background path."""
    from trust import jobs
    monkeypatch.setattr(jobs, "WAIT", True)
