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
    monkeypatch.setattr(selftest, "STRAY", ())             # whatever else sits at the top of this repo copy
    monkeypatch.setattr(selftest, "test_files", lambda tests: ([tests / "test_web.py"], []))   # and any leftover tests
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, **kw) or Done(0, "294 passed in 25s"))
    said = []
    assert selftest.run(said.append) is True and said == ["Tests passed: 294 passed in 25s"]
    env = seen["env"]
    assert "DATABASE_URL" not in env and [k for k in env if k.startswith("TRUST_")] == ["TRUST_STORE_DIR"]
    assert "pytest" in seen["cmd"] and seen["cmd"][-1].endswith(".py")              # the listed test files
    tests = str(selftest.ROOT / "tests")                  # only TRUST's own tests folder and settings are read
    assert ["--rootdir", tests] == seen["cmd"][seen["cmd"].index("--rootdir"):][:2]
    assert ["--confcutdir", tests] == seen["cmd"][seen["cmd"].index("--confcutdir"):][:2]
    assert seen["cmd"][seen["cmd"].index("-c") + 1].endswith("pytest.ini")


def test_another_apps_files_at_the_top_are_named_and_ignored(monkeypatch, tmp_path):
    """Owner, 17 Nov 2026: TRAC's conftest.py and pytest.ini were left in the TRUST repo and stopped the deploy."""
    (tmp_path / "conftest.py").write_text("import django\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    monkeypatch.setattr(selftest, "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Done(0, "294 passed"))
    said = []
    assert selftest.run(said.append) is True
    assert "conftest.py, pytest.ini" in said[0] and "ignore them" in said[0] and said[-1] == "Tests passed: 294 passed"


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


def test_old_test_files_left_in_the_repo_are_named_and_not_run(monkeypatch, tmp_path):
    """Owner, 17 Nov 2026: test_families.py and test_lost_and_found.py, removed in this version, were still in the repo
    (unzipping over the folder never deletes files) and stopped the deploy. Only the listed test files run."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pytest.ini").write_text("[pytest]\n")
    for name in ("test_kept.py", "test_families.py", "test_lost_and_found.py"):
        (tests / name).write_text("")
    (tests / "test_files.txt").write_text("# this version's tests\ntest_kept.py\n")
    monkeypatch.setattr(selftest, "ROOT", tmp_path)
    monkeypatch.setattr(selftest, "STRAY", ())
    seen = {}
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd) or Done(0, "1 passed"))
    said = []
    assert selftest.run(said.append) is True
    ran = [part for part in seen["cmd"] if part.endswith(".py")]
    assert ran == [str(tests / "test_kept.py")]
    assert "2 test files" in said[0] and "test_families.py, test_lost_and_found.py" in said[0]


def test_the_list_of_test_files_matches_this_version():
    """tests/test_files.txt names every test file shipped with this version (it is rewritten with each zip)."""
    tests = selftest.ROOT / "tests"
    listed = {line.strip() for line in (tests / "test_files.txt").read_text().splitlines()
              if line.strip() and not line.startswith("#")}
    assert listed and all((tests / name).exists() for name in listed)
