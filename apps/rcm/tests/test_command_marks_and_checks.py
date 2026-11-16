"""The Proposed mark on commands, the confirmation lines, the "how to check it" parts, the audience tags on
Library lines and the commands list. Nothing here reads the shipped content files except the list test."""

import datetime
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.template import Context, Template

from apps.core.tests.support import published_control
from apps.platforms import audience
from apps.platforms.management.commands import commands_to_confirm as listing
from apps.platforms.selectors import AspectRow, add_checks
from apps.rcm.shape import PROPOSED_NOTE, checks_of, commands_of, is_proposed, step_problems

SQL = {"platform": "SQL Server", "code": "SELECT 1;"}
CHECK = {"platform": "SQL Server", "audience": "Platform users", "where": "Jobs in SQL Server Agent.",
         "good": ["Every job has an owner."], "keep": "The job list", "shows": ["The date"]}


def test_a_command_is_proposed_until_a_name_and_a_date_are_written_on_it():
    assert is_proposed(SQL)
    assert not is_proposed({**SQL, "confirmed_by": "A. Admin", "confirmed_on": "2027-01-05"})


def test_confirmation_needs_both_lines_and_a_real_date():
    only_name = [{"do": "x", "commands": [{**SQL, "confirmed_by": "A. Admin"}]}]
    assert any("go together" in text for _, text in step_problems(only_name))
    bad_date = [{"do": "x", "commands": [{**SQL, "confirmed_by": "A", "confirmed_on": "soon"}]}]
    assert any("YYYY-MM-DD" in text for _, text in step_problems(bad_date))
    good = [{"do": "x", "commands": [{**SQL, "confirmed_by": "A", "confirmed_on": datetime.date(2027, 1, 5)}]}]
    assert step_problems(good) == []


def test_a_check_needs_a_platform_an_audience_and_one_part():
    assert step_problems([{"do": "x", "checks": [CHECK]}]) == []
    assert step_problems([{"do": "x", "checks": [{"platform": "SQL Server", "audience": "Your team", "keep": "a"}]}])
    assert step_problems([{"do": "x", "checks": [{"platform": "SQL Server", "audience": "Platform users"}]}])


def test_commands_belong_to_the_platform_users_unless_marked():
    admin = {**SQL, "audience": "Platform admins", "code": "SELECT 2;"}
    steps = [{"do": "x", "commands": [SQL, admin], "checks": [CHECK]}]
    assert commands_of(steps, "SQL Server", "Platform users") == [SQL]
    assert commands_of(steps, "SQL Server", "Platform admins") == [admin]
    assert checks_of(steps) == [CHECK]


def test_a_tagged_line_shows_its_audience_and_an_untagged_line_has_none():
    html = Template("{% load library_checks %}{{ text|audience_bullets:'users' }}").render(Context({
        "text": "- [Platform admins] Admin line.\n- [Platform users] User line.\n- Both lines."}))
    assert 'data-audience="admins" class="audience-line is-audience-off"' in html
    assert 'data-audience="users" class="audience-line"' in html
    assert "<li>Both lines.</li>" in html


def test_an_unknown_audience_tag_is_reported_but_a_link_at_the_start_is_fine():
    assert audience.tag_problems("- [Platform team] A line.")
    assert audience.tag_problems("- [Platform admins] A line.\n- [Policy](#todo-x) sets it.") == []


def test_checks_are_added_only_for_the_platforms_on_the_page():
    sql, aws = SimpleNamespace(name="SQL Server"), SimpleNamespace(name="AWS")
    control = SimpleNamespace(ident="MO-02")
    version = SimpleNamespace(steps=[{"do": "x", "checks": [CHECK, {**CHECK, "platform": "AWS"}]}])
    row = AspectRow(question=None, controls=[(control, version)])
    add_checks([row], [sql])
    assert [(c.platform, c.audience, c.keep) for c in row.checks] == [(sql, "Platform users", "The job list")]
    assert aws not in [c.platform for c in row.checks]


@pytest.mark.django_db
@pytest.mark.usefixtures("sso")
def test_the_control_page_marks_unconfirmed_commands_and_draws_checks(owner, reviewer, access):
    call_command("seed_platforms")
    confirmed = {"platform": "Windows Server", "code": "Get-ScheduledTask",
                 "confirmed_by": "A. Admin", "confirmed_on": "2027-01-05"}
    control, _ = published_control(access, owner.user, reviewer.user,
                                   steps=[{"do": "List jobs.", "commands": [SQL, confirmed], "checks": [CHECK]}])
    html = owner.get(control.get_absolute_url()).content.decode()
    assert html.count('class="proposed-mark"') == 1 and PROPOSED_NOTE in html
    assert "Confirmed by A. Admin on 2027-01-05." in html
    for words in ("How to check it on SQL Server", "Where to look", "What good looks like", "What to keep"):
        assert words in html
    assert html.index("Where to look") < html.index("What good looks like") < html.index("What to keep")


def test_the_commands_list_counts_proposed_and_confirmed():
    found = {"SQL Server": [{"control_id": "MO-01", "control_title": "t", "step": 1, "do": "d", "command": SQL},
                            {"control_id": "MO-01", "control_title": "t", "step": 2, "do": "d",
                             "command": {**SQL, "confirmed_by": "A", "confirmed_on": "2027-01-05"}}]}
    text = listing.render(found)
    assert "2 commands: 1 proposed, 1 confirmed." in text and "Confirmed by A on 2027-01-05." in text


def test_the_shipped_list_matches_the_control_files():
    assert listing.LIST_FILE.read_text(encoding="utf-8") == listing.render(listing.commands_by_platform())


def test_the_edit_form_keeps_checks_and_command_marks_through_a_save():
    import json
    from apps.rcm.forms import StepsField
    field = StepsField()
    step = {"do": "Check it on each platform.",
            "commands": [{"platform": "SQL Server", "code": "SELECT 1", "audience": "Platform admins",
                          "confirmed_by": "A DBA", "confirmed_on": "2026-11-15"}],
            "checks": [{"platform": "SQL Server", "audience": "Platform users", "where": "SQL Server Agent", "good": ["Every job has an owner."]}]}
    page_rows = json.loads(field.prepare_value([step]))
    assert field.parse(page_rows) == [step]
