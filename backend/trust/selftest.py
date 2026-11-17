"""Run the tests before a deploy goes live (owner, 15 Nov 2026).

The Procfile's release line runs `python manage.py release`: the tests first, then the database tables. If
a test fails, the release stops, so the new version never takes traffic and the site stays on the version
before it.

The tests run in a separate process that is given no database address and none of the site's TRUST_
settings, with an empty temporary folder to work in: they can't read or change the site's data.

To deploy without the tests in an emergency, set the config var TRUST_SKIP_TESTS=1 (and remove it afterwards).
"""
import os
import pathlib
import subprocess
import sys
import tempfile

from .config import ROOT

KEEP_OUT = ("DATABASE_URL",)
STRAY = ("conftest.py", "pytest.ini", "apps", "content", "docker")   # not TRUST's: TRAC has these at its top
TEST_LIST = "test_files.txt"   # tests/test_files.txt: this version's test files, one per line (written with each zip)


def count_words(n):
    return f"{n} test file" if n == 1 else f"{n} test files"


def test_files(tests):
    """(files to run, leftovers). The list in tests/test_files.txt decides which test files belong to this version, so a
    test file left behind from an older version (a zip unzipped over the folder never deletes files) isn't run.
    Without the list, every test_*.py runs, as before."""
    listed = tests / TEST_LIST
    present = sorted(path.name for path in tests.glob("test_*.py"))
    if not listed.exists():
        return [tests / name for name in present], []
    wanted = [line.strip() for line in listed.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")]
    run = [tests / name for name in wanted if (tests / name).exists()]
    return run, [name for name in present if name not in wanted]


def run(out=print):
    """True when the tests passed (or were skipped on purpose); False when any failed or couldn't be run."""
    if os.environ.get("TRUST_SKIP_TESTS", "").strip() == "1":
        out("Tests skipped: TRUST_SKIP_TESTS=1 is set. Remove it once the deploy is done.")
        return True
    try:
        import pytest  # noqa: F401
    except ImportError:
        out("The tests can't run: pytest isn't installed (it is in requirements.txt).")
        return False
    stray = [name for name in STRAY if (ROOT / name).exists()]
    if stray:
        out(f"Note: {', '.join(stray)} at the top of the repo {'is' if len(stray) == 1 else 'are'}n't TRUST's (they look like "
            "another app's files left behind when a zip was unzipped over this folder). The tests ignore them; remove "
            "them from the repo when you can.")
    run_files, leftovers = test_files(ROOT / "tests")
    if leftovers:
        out(f"Note: {count_words(len(leftovers))} in tests/ {'isn' if len(leftovers) == 1 else 'aren'}'t part of this version "
            f"(left behind from an older one, because unzipping over the folder never deletes files), so "
            f"{'it is' if len(leftovers) == 1 else 'they are'} not run: {', '.join(leftovers)}. Remove "
            f"{'it' if len(leftovers) == 1 else 'them'} from the repo when you can.")
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith("TRUST_") and k not in KEEP_OUT}
        env.update(TRUST_STORE_DIR=str(pathlib.Path(tmp) / "store"), PYTHONDONTWRITEBYTECODE="1")
        try:
            # Only TRUST's own tests and settings: tests/pytest.ini, with nothing above tests/ read. A stray
            # pytest.ini or conftest.py at the top of the repo (e.g. another app's files left behind) can't take over.
            tests = ROOT / "tests"
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "-c", str(tests / "pytest.ini"), "--rootdir", str(tests), "--confcutdir", str(tests),
                                *[str(path) for path in run_files]],
                               env=env, cwd=tmp, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            out("The tests didn't finish in 15 minutes, so the release stops.")
            return False
    tail = [x for x in (r.stdout + r.stderr).splitlines() if x.strip()]
    if r.returncode == 0:
        out(f"Tests passed: {tail[-1] if tail else 'ok'}")
        return True
    out("Tests FAILED, so the release stops and the site stays on the version before this one.")
    for line in tail[-40:]:
        out("  " + line)
    out("Fix the failing tests and deploy again. In an emergency only: set the config var TRUST_SKIP_TESTS=1.")
    return False
