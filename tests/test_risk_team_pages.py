"""The team results pages on the Risk site: the page is loaded, the router knows #/team and #/teams,
and the page's own code draws the made-up fixtures (tests/fixtures/team_results_*.json). Runs the page code with Node."""
import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RISK = ROOT / "frontend" / "risk"
FIXTURES = ROOT / "tests" / "fixtures"


def test_index_loads_the_team_page():
    index = (RISK / "index.html").read_text()
    assert '<script src="risk-team.js"></script>' in index
    assert 'href="risk-team.css"' in index
    assert "risk-team-dev.js" not in index


def run_in_node(checks):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node isn't installed here")
    l3 = json.loads((FIXTURES / "team_results_l3.json").read_text())
    l4 = json.loads((FIXTURES / "team_results_l4.json").read_text())
    script = "\n".join([
        "globalThis.window = {}; globalThis.document = {}; globalThis.localStorage = {getItem(){ return ''; }};",
        (ROOT / "frontend" / "shared" / "text.js").read_text(),
        (RISK / "risk-core.js").read_text(),
        (RISK / "risk-team.js").read_text(),
        "const l3 = %s; const l4 = %s;" % (json.dumps(l3), json.dumps(l4)),
        checks,
    ])
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_router_knows_team_and_teams():
    answer = run_in_node("console.log(JSON.stringify({"
                         "team: riskPages.some(page => page.matches(['team', 'lending'])),"
                         "teams: riskPages.some(page => page.matches(['teams'])),"
                         "bare: riskPages.some(page => page.matches(['team'])),"
                         "link: riskTopBarLinks.some(link => link.href === '#/teams')}));")
    assert answer == {"team": True, "teams": True, "bare": False, "link": True}


def test_the_pages_draw_the_fixtures_with_elevated_and_no_rating():
    answer = run_in_node("console.log(JSON.stringify({"
                         "summary: riskTeamSummaryHtml(l3), detail: riskTeamDetailHtml(l3), strip: riskTeamL4StripHtml(l3.team),"
                         "l4summary: riskTeamSummaryHtml(l4)}));")
    assert "3 Elevated" in answer["summary"] and "L4 teams on their own" in answer["summary"]
    assert "2 Elevated" in answer["strip"]
    assert "1 doesn't apply" in answer["l4summary"]
    assert ">Rating<" not in answer["summary"] + answer["detail"] + answer["l4summary"]
    assert "Download (.csv)" in answer["detail"] and 'id="rt-print"' in answer["detail"]
    assert "Controls in TRAC" not in answer["detail"]
