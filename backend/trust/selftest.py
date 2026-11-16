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
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith("TRUST_") and k not in KEEP_OUT}
        env.update(TRUST_STORE_DIR=str(pathlib.Path(tmp) / "store"), PYTHONDONTWRITEBYTECODE="1")
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(ROOT / "tests")],
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
