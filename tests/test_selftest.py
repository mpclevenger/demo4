"""The tests run before a deploy goes live (owner, 15 Nov 2026): away from the site's data, and a failure
stops the release before the database step."""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import __main__ as cli, migrate, selftest  # noqa: E402


class Done:
    def __init__(self, code, text=""):
        self.returncode, self.stdout, self.stderr = code, text, ""


def test_the_tests_get_no_database_and_none_of_the_sites_settings(monkeypatch):
    seen = {}
    monkeypatch.setenv("DATABASE_URL", "postgres://the-real-one")
    monkeypatch.setenv("TRUST_ENV", "test")
    monkeypatch.setenv("TRUST_SETTINGS", "/somewhere/settings.json")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, **kw) or Done(0, "294 passed in 25s"))
    said = []
    assert selftest.run(said.append) is True and said == ["Tests passed: 294 passed in 25s"]
    env = seen["env"]
    assert "DATABASE_URL" not in env and [k for k in env if k.startswith("TRUST_")] == ["TRUST_STORE_DIR"]
    assert "pytest" in seen["cmd"] and seen["cmd"][-1].endswith("tests")


def test_a_failing_test_stops_the_release_before_the_database_step(monkeypatch, capsys):
    ran = []
    monkeypatch.setattr(migrate, "run", lambda: ran.append("migrate") or [])
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Done(1, "FAILED tests/test_x.py::test_y\n1 failed, 293 passed"))
    assert cli.main(["release"]) == 1 and ran == []
    out = capsys.readouterr().out
    assert "Tests FAILED" in out and "test_x.py::test_y" in out and "TRUST_SKIP_TESTS=1" in out
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Done(0, "294 passed"))
    assert cli.main(["release"]) == 0 and ran == ["migrate"]


def test_the_emergency_switch_skips_the_tests(monkeypatch):
    monkeypatch.setenv("TRUST_SKIP_TESTS", "1")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    said = []
    assert selftest.run(said.append) is True and "skipped" in said[0]
