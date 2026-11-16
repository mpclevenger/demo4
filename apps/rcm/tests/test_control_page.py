"""The control page: the two pills, the three cards, every optional part of a step, the command blocks
(which ones start open) and the pieces that are gone. Nothing here reads the shipped content files."""

import re

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.tests.support import publish, published_control
from apps.rcm import services

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso")]

SQL = {"platform": "SQL Server", "note": "Lists the jobs.", "code": "SELECT name\nFROM msdb.dbo.sysjobs;"}
WINDOWS = {"platform": "Windows Server", "code": "Get-ScheduledTask"}
SPLUNK = {"platform": "Splunk", "code": "index=jobs"}
FULL = {
    "do": "List your jobs.",
    "how": "Pull every job from the scheduler.",
    "weigh": ["Who is affected downstream", "Who can fix it out of hours"],
    "policy": "[Access Control Policy](#todo-access-control-policy)",
    "evidence": {"keep": "The job inventory", "shows": ["The date it was pulled", "Every job"]},
    "commands": [SQL, WINDOWS],
}
PEOPLE = {"performer": ["Sees the alerts"], "reviewer": ["Doesn't operate the jobs"], "small_team": "Ask another team."}


@pytest.fixture(autouse=True)
def platforms(access):
    call_command("seed_platforms")


def page(owner, reviewer, access, **content):
    control, _ = published_control(access, owner.user, reviewer.user, **content)
    return owner.get(control.get_absolute_url()).content.decode()


def card(html, card_id):
    """The HTML of one section card, from its heading to the start of the next card (or the end of the page)."""
    start = html.index(f'id="{card_id}"')
    end = html.find('<details class="section-card', start)
    return html[start:] if end == -1 else html[start:end]


def header(html):
    start = html.index('<header class="page-header">')
    return html[start:html.index("</header>", start)]


def blocks(html):
    """{platform: is_open} for the command blocks on the page."""
    return {
        name: " open" in tag
        for tag, name in re.findall(r'(<details class="step-command"[^>]*>)\s*<summary>([^<]*?): how to pull it</summary>', html)
    }


# Header

def test_header_has_only_the_nature_pill_and_the_key_pill_for_key_controls(owner, reviewer, access):
    html = page(owner, reviewer, access, level="key", categories=["database"], performer_role="Operations",
                reviewer_role="Application owner", owner_role="Identity and Access")
    top = header(html)
    assert top.count("attr-pill ") == 2 and "tone-detective" in top and "tone-key" in top and ">Key<" in top
    for gone in ("Manual", "Quarterly", "Database", "Identity and Access", "Performed by", "Reviewed by",
                 "Operations", "Key controls for SOX in-scope apps", reverse("rcm:sox")):
        assert gone not in top
    assert reverse("rcm:sox") not in html


def test_no_key_pill_below_the_first_level(owner, reviewer, access):
    top = header(page(owner, reviewer, access, level="non-key"))
    assert top.count("attr-pill ") == 1 and "tone-key" not in top and "Non-key" not in top


# Why card

def test_why_card_has_the_benefit_then_it_fits_when_then_addresses(owner, reviewer, access):
    html = page(owner, reviewer, access, why="Catches drift.", applies_when=["You approve access.", "You hold payroll data."])
    why = card(html, "why")
    assert "Why you'd want this control" in html and "section-card-why" in html
    assert why.index("Catches drift.") < why.index("It fits when:") < why.index("You approve access.") < why.index("You hold payroll data.")


def test_why_card_leaves_out_it_fits_when_without_statements(owner, reviewer, access):
    assert "It fits when:" not in page(owner, reviewer, access, applies_when=[])


def test_what_could_go_wrong_card_names_the_linked_risks(owner, reviewer, access):
    control, _ = published_control(access, owner.user, reviewer.user)
    entity, version = services.create_risk(owner.user, access, title="Leaver keeps access", statement="s", owner_role="IAM")
    services.set_risk_links(version, owner.user, controls=[(control, "full", "Removes leavers")])
    publish(version, reviewer.user)
    wrong = card(owner.get(control.get_absolute_url()).content.decode(), "wrong")
    assert "What could go wrong" in wrong and "Leaver keeps access" in wrong and entity.ident in wrong


def test_placeholders_are_filled_in_the_why_the_step_how_and_the_risk_statement(owner, reviewer, access):
    control, _ = published_control(access, owner.user, reviewer.user, why="Write to {{tech_risk_email}}.",
                                   steps=[{"do": "Do it", "how": "Ask {{tech_risk_email}} first."}])
    entity, version = services.create_risk(owner.user, access, title="Leaver", statement="Tell {{tech_risk_email}}.", owner_role="IAM")
    publish(version, reviewer.user)
    for url in (control.get_absolute_url(), entity.get_absolute_url()):
        html = owner.get(url).content.decode()
        assert "{{tech_risk_email}}" not in html and "Tech Risk email address" in html


# How to build it

def test_steps_are_numbered_in_order_with_the_guide_link_at_the_foot(owner, reviewer, access):
    html = page(owner, reviewer, access, steps=[{"do": "First thing."}, {"do": "Second thing."}, {"do": "Third thing."}])
    build = card(html, "build")
    assert "How to build it" in html and "section-card-how" in html
    assert build.count('class="step-list-item"') == 3 and 'class="step-list"' in build
    assert build.index("First thing.") < build.index("Second thing.") < build.index("Third thing.")
    assert 'href="/guides/what-good-evidence-looks-like/">What good evidence looks like</a>' in build
    assert build.index("Third thing.") < build.index("What good evidence looks like")


def test_a_step_with_only_a_do_line_shows_nothing_else(owner, reviewer, access):
    build = card(page(owner, reviewer, access, steps=[{"do": "Just this."}]), "build")
    assert "Just this." in build
    for absent in ("step-how", "Set by:", "Consider these", "Evidence to keep", "It should show", "step-command"):
        assert absent not in build


def test_every_optional_part_of_a_step_shows(owner, reviewer, access):
    build = card(page(owner, reviewer, access, steps=[FULL]), "build")
    assert "Pull every job from the scheduler." in build
    assert 'Set by: <span class="todo-link">Access Control Policy</span>' in build and "(to be added)" in build
    assert "Consider these when setting your thresholds:" in build and "<li>Who can fix it out of hours</li>" in build
    assert "Evidence to keep:</strong> The job inventory" in build
    assert "It should show:" in build and "<li>The date it was pulled</li>" in build
    assert "SQL Server: how to pull it" in build and "Windows Server: how to pull it" in build
    assert "Lists the jobs." in build
    assert "TRAC doesn&#x27;t set" not in build


def test_evidence_without_shows_has_no_should_show_list(owner, reviewer, access):
    build = card(page(owner, reviewer, access, steps=[{"do": "x", "evidence": {"keep": "A list"}}]), "build")
    assert "Evidence to keep:" in build and "It should show" not in build


def test_text_is_escaped(owner, reviewer, access):
    step = {"do": "<i>do</i>", "how": "<b>how</b>", "weigh": ["<u>w</u>"], "policy": "<s>p</s>",
            "evidence": {"keep": "<em>k</em>", "shows": ["<mark>s</mark>"]}}
    build = card(page(owner, reviewer, access, steps=[step]), "build")
    for tag in ("<i>", "<b>", "<u>", "<s>", "<em>", "<mark>"):
        assert tag not in build
    assert "&lt;b&gt;how&lt;/b&gt;" in build


def test_code_is_escaped_and_scrolls_in_a_monospace_block(owner, reviewer, access):
    code = "SELECT '<script>alert(1)</script>' AS x, a & b FROM t WHERE c > 1;"
    html = page(owner, reviewer, access, steps=[{"do": "x", "commands": [{"platform": "SQL Server", "code": code}]}])
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "a &amp; b" in html and "c &gt; 1" in html
    assert '<pre class="step-command-code"><code>' in html
    css = open("static/css/trac.css").read()
    rule = re.search(r"\.step-command-code \{([^}]*)\}", css).group(1)
    assert "overflow-x: auto" in rule
    assert "var(--trac-mono)" in re.search(r"\.step-command-code code \{([^}]*)\}", css).group(1)


def test_a_step_with_one_command_block_has_it_open(owner, reviewer, access):
    html = page(owner, reviewer, access, steps=[{"do": "x", "commands": [SQL]}])
    assert blocks(html) == {"SQL Server": True}


def test_a_step_with_several_blocks_has_them_closed_for_a_visitor_without_answers(owner, reviewer, access):
    html = page(owner, reviewer, access, steps=[{"do": "x", "commands": [SQL, WINDOWS, SPLUNK]}])
    assert blocks(html) == {"SQL Server": False, "Windows Server": False, "Splunk": False}


def answer(visitor, *slugs):
    visitor.post(reverse("pathfinder:index"), {"platform": list(slugs), "sox": "no", "tier": "2"})


def test_my_system_platforms_open_first(owner, reviewer, access):
    control, _ = published_control(
        access, owner.user, reviewer.user,
        steps=[{"do": "a", "commands": [SQL, WINDOWS, SPLUNK]}, {"do": "b", "commands": [SQL]}, {"do": "c", "commands": [WINDOWS, SPLUNK]}],
    )
    answer(owner, "windows-server", "splunk")
    html = owner.get(control.get_absolute_url()).content.decode()
    first, second, third = (card(html, "build").split('class="step-list-item"')[n] for n in (1, 2, 3))
    assert blocks(first) == {"SQL Server": False, "Windows Server": True, "Splunk": True}
    assert blocks(second) == {"SQL Server": True}  # the only block in its step
    assert blocks(third) == {"Windows Server": True, "Splunk": True}


def test_answers_for_other_platforms_leave_blocks_closed(owner, reviewer, access):
    control, _ = published_control(access, owner.user, reviewer.user, steps=[{"do": "a", "commands": [SQL, WINDOWS]}])
    answer(owner, "azure")
    assert blocks(owner.get(control.get_absolute_url()).content.decode()) == {"SQL Server": False, "Windows Server": False}


def test_visitors_without_answers_cost_no_extra_query_for_platforms(owner, reviewer, access):
    control, _ = published_control(access, owner.user, reviewer.user, steps=[{"do": "a", "commands": [SQL, WINDOWS]}])
    url = control.get_absolute_url()
    owner.get(url)
    with CaptureQueriesContext(connection) as without:
        owner.get(url)
    plain = [q["sql"] for q in without.captured_queries]
    answer(owner, "windows-server")
    owner.get(url)
    with CaptureQueriesContext(connection) as with_answers:
        owner.get(url)
    asked = [q["sql"] for q in with_answers.captured_queries]
    looks_up_my_platforms = lambda sql: '"platforms_platform"."slug" IN' in sql
    assert not any(looks_up_my_platforms(sql) for sql in plain)
    assert any(looks_up_my_platforms(sql) for sql in asked)


def test_no_how_to_build_card_without_steps(owner, reviewer, access):
    assert "How to build it" not in page(owner, reviewer, access, steps=[])


# Choosing people

def test_choosing_people_card(owner, reviewer, access):
    html = page(owner, reviewer, access, choosing_people=PEOPLE)
    people = card(html, "people")
    assert "Choosing who performs and who reviews" in html
    assert people.index("Performer") < people.index("Sees the alerts") < people.index("Reviewer") < people.index("Doesn&#x27;t operate")
    assert "Small team?" in people and "Ask another team." in people
    assert people.index("Ask another team.") < people.index("Name a backup for both.")


def test_choosing_people_card_parts_are_each_optional(owner, reviewer, access):
    people = card(page(owner, reviewer, access, choosing_people={"reviewer": ["Independent"]}), "people")
    assert "Reviewer" in people and "Performer" not in people and "Small team?" not in people
    assert "Name a backup for both." in people


def test_no_choosing_people_card_without_notes(owner, reviewer, access):
    html = page(owner, reviewer, access)
    assert "Choosing who performs" not in html and "Name a backup" not in html


# Kept and removed pieces

def test_the_kept_pieces_are_still_there(owner, reviewer, access):
    stage = access.stages.first()
    control, _ = published_control(access, owner.user, reviewer.user, stage=stage, steps=[FULL], choosing_people=PEOPLE)
    html = owner.get(control.get_absolute_url()).content.decode()
    assert "lifecycle-strip" in html and f'aria-current="step">{stage.name}<' in html
    assert "data-section-toolbar" in html and "Expand all" in html and "Collapse all" in html
    assert "Version" in html and "Approver" in html  # the version footer
    assert "data-comment" in html or "comment" in html.lower()


def test_the_removed_pieces_are_gone(owner, reviewer, access):
    html = page(owner, reviewer, access, steps=[FULL], choosing_people=PEOPLE, level="key", performer_role="Ops")
    for gone in (
        "What good looks like", "Timings your team sets", "Do I need this?", "Why this control exists", "How to run it",
        "For SOX apps", "sox-only-pill", "criteria", "part-heading", "Independent review", "Before you send evidence",
        "A complete review record", "Where evidence lives", "Keep:</strong>", "step-list-role", "sod-line",
    ):
        assert gone not in html, gone


def test_next_on_your_path_still_shows(owner, reviewer, access):
    control, _ = published_control(access, owner.user, reviewer.user)
    html = owner.get(control.get_absolute_url(), {"path": "anything"}).content.decode()
    assert "Next on your path" not in html  # only with answers and a real next step: the tag is on the page, not erroring
    assert owner.get(control.get_absolute_url(), {"path": "anything"}).status_code == 200
