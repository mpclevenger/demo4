"""The "how to build it" steps and the "choosing people" notes: the rules, the edit form, the content files,
the export, the old-data conversion and search. Nothing here reads the shipped content files."""

import importlib
import io
import json
from html import unescape
from pathlib import Path

import pytest
import yaml
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.core import selectors
from apps.core.tests.support import control_fields, control_post, make_user, published_control
from apps.rcm import services
from apps.rcm.models import ControlVersion
from apps.rcm.shape import people_problems, step_problems

pytestmark = pytest.mark.django_db

FULL_STEP = {
    "do": "List your jobs.",
    "how": "Pull every job from the scheduler.",
    "weigh": ["Who is affected downstream", "Who can fix it out of hours"],
    "policy": "[Access Control Policy](#todo-access-control-policy)",
    "evidence": {"keep": "The job inventory", "shows": ["The date it was pulled", "Every job"]},
    "commands": [
        {"platform": "SQL Server", "note": "Lists the jobs.", "code": "SELECT name\nFROM msdb.dbo.sysjobs;\n"},
        {"platform": "Splunk", "code": "index=jobs"},
    ],
}
PEOPLE = {
    "performer": ["Sees the alerts daily"],
    "reviewer": ["Doesn't operate the jobs", "Can get a fix prioritized"],
    "small_team": "Ask someone from another team to look at a sample.",
}


# The rules

def test_a_step_with_every_part_is_fine_and_so_is_a_bare_do():
    assert step_problems([FULL_STEP, {"do": "Just this."}, {"do": "With evidence", "evidence": {"keep": "A list"}}]) == []
    assert step_problems([]) == []


@pytest.mark.parametrize("step, fragment", [
    ("loose text", "needs a 'do' line"),
    ({}, "needs a 'do' line"),
    ({"do": "  "}, "needs a 'do' line"),
    ({"do": "x", "who": "Owner"}, "'who' isn't a known field. Use do, how, weigh, policy, evidence, commands and checks."),
    ({"do": "x", "part": "monitoring"}, "'part' isn't a known field"),
    ({"do": "x", "how": ""}, "'how' needs text"),
    ({"do": "x", "policy": 5}, "'policy' needs text"),
    ({"do": "x", "weigh": "one thing"}, "'weigh' needs a list"),
    ({"do": "x", "weigh": []}, "'weigh' needs a list"),
    ({"do": "x", "weigh": ["fine", " "]}, "'weigh' needs a list"),
    ({"do": "x", "evidence": "Signed review"}, "Plain text isn't used any more"),
    ({"do": "x", "evidence": {"shows": ["a"]}}, "'evidence' needs a 'keep' line"),
    ({"do": "x", "evidence": {"keep": " "}}, "'evidence' needs a 'keep' line"),
    ({"do": "x", "evidence": {"keep": "k", "shows": "a"}}, "'shows' under 'evidence' needs a list"),
    ({"do": "x", "evidence": {"keep": "k", "extra": "a"}}, "'extra' isn't a known field. Use keep and shows."),
    ({"do": "x", "commands": "SELECT 1"}, "'commands' needs a list"),
    ({"do": "x", "commands": []}, "'commands' needs a list"),
    ({"do": "x", "commands": ["SELECT 1"]}, "command 1 needs a 'platform' and some 'code'"),
    ({"do": "x", "commands": [{"code": "SELECT 1"}]}, "command 1 needs a 'platform'"),
    ({"do": "x", "commands": [{"platform": "SQL Server"}]}, "command 1 needs a 'code'"),
    ({"do": "x", "commands": [{"platform": "SQL Server", "code": "x", "note": " "}]}, "command 1: 'note' needs text"),
    ({"do": "x", "commands": [{"platform": "SQL Server", "code": "x", "lang": "sql"}]}, "command 1: 'lang' isn't a known field"),
])
def test_step_rules_say_what_is_wrong_in_plain_words(step, fragment):
    problems = step_problems([{"do": "Fine"}, step])
    assert problems and all(number == 2 for number, _ in problems)
    assert fragment in " ".join(text for _, text in problems)


def test_steps_that_are_not_a_list():
    assert step_problems({"do": "x"}) == [(None, "expected a list of steps.")]


def test_people_rules():
    assert people_problems(PEOPLE) == [] and people_problems({}) == [] and people_problems({"small_team": "One line"}) == []
    assert "isn't a known field" in people_problems({"backup": "x"})[0]
    assert "'performer' needs a list" in people_problems({"performer": "one"})[0]
    assert "'reviewer' needs a list" in people_problems({"reviewer": []})[0]
    assert "'small_team' needs a line of text" in people_problems({"small_team": ["a"]})[0]
    assert people_problems("loose") == ["expected 'performer', 'reviewer' and 'small_team'."]


def make_version(access, owner, **extra):
    return services.create_control(owner.user, access, **control_fields(**extra))[1]


def test_model_accepts_the_new_shape_and_defaults_to_none(access, owner):
    make_version(access, owner, steps=[FULL_STEP], choosing_people=PEOPLE).full_clean()
    plain = make_version(access, owner)
    assert plain.choosing_people == {}


def test_model_names_the_step_that_is_wrong(access, owner):
    version = make_version(access, owner, steps=[{"do": "Fine"}, {"do": "Bad", "evidence": "text"}])
    with pytest.raises(ValidationError) as error:
        version.full_clean()
    assert error.value.message_dict["steps"][0].startswith("Step 2: 'evidence' needs a 'keep' line")


def test_model_rejects_bad_people_and_non_list_steps(access, owner):
    with pytest.raises(ValidationError) as error:
        make_version(access, owner, choosing_people={"performer": "x"}).full_clean()
    assert "choosing_people" in error.value.message_dict
    with pytest.raises(ValidationError) as error:
        make_version(access, owner, steps={"do": "x"}).full_clean()
    assert error.value.message_dict["steps"] == ["Expected a list of steps."]


def test_criteria_and_timings_are_gone_from_the_model():
    names = {f.name for f in ControlVersion._meta.get_fields()}
    assert not names & {"criteria", "timings"} and "choosing_people" in names


# The old data

def test_the_migration_converts_old_steps_and_leaves_new_ones(access, owner):
    migration = importlib.import_module("apps.rcm.migrations.0008_control_build_steps")
    old = [
        {"role": "Owner", "text": "Review the list.", "evidence": "Signed review", "part": "monitoring"},
        {"role": "", "text": "Then file it.", "evidence": ""},
        {"role": "Owner", "text": "", "evidence": "no text, so dropped"},
    ]
    one = make_version(access, owner, steps=old)
    two = make_version(access, owner, steps=[{"do": "Already new"}])
    three = make_version(access, owner, steps=[])
    migration.convert_steps(django_apps, None)
    assert ControlVersion.objects.get(pk=one.pk).steps == [
        {"do": "Review the list.", "evidence": {"keep": "Signed review"}},
        {"do": "Then file it."},
    ]
    assert ControlVersion.objects.get(pk=two.pk).steps == [{"do": "Already new"}]
    assert ControlVersion.objects.get(pk=three.pk).steps == []
    for version in (one, two, three):
        ControlVersion.objects.get(pk=version.pk).full_clean(exclude=["topic", "entity"])


# The edit form

@pytest.mark.usefixtures("sso")
class TestEditForm:
    def row(self, **extra):
        return {"do": "List your jobs.", "how": "", "weigh": "", "policy": "", "evidence_keep": "",
                "evidence_shows": "", "commands": [], **extra}

    def post(self, owner, access, rows, **extra):
        return owner.post(reverse("rcm:control_new"), control_post(access, steps=json.dumps(rows), **extra))

    def test_rows_are_saved_without_empty_parts(self, owner, access):
        rows = [
            self.row(
                how=" Pull them. ", weigh="Who is hit\n\n Who fixes it ", policy="[P](#todo-p)",
                evidence_keep="The list", evidence_shows="The date\n  \nThe system",
                commands=[
                    {"platform": "SQL Server", "note": " Lists them. ", "code": "\nSELECT 1;\nSELECT 2;\n"},
                    {"platform": "", "note": "", "code": ""},
                ],
            ),
            self.row(do="Just this."),
            self.row(do=""),
        ]
        assert self.post(owner, access, rows).status_code == 302
        assert ControlVersion.objects.get().steps == [
            {
                "do": "List your jobs.", "how": "Pull them.", "weigh": ["Who is hit", "Who fixes it"], "policy": "[P](#todo-p)",
                "evidence": {"keep": "The list", "shows": ["The date", "The system"]},
                "commands": [{"platform": "SQL Server", "note": "Lists them.", "code": "SELECT 1;\nSELECT 2;"}],
            },
            {"do": "Just this."},
        ]

    @pytest.mark.parametrize("rows, message", [
        ([{"do": "", "how": "Words"}], "Step 1: each step needs a 'do' line."),
        ([{"do": "Go", "evidence_shows": "The date"}], "Step 1: 'evidence' needs a 'keep' line"),
        ([{"do": "Go", "commands": [{"platform": "SQL Server", "code": ""}]}], "Step 1: command 1 needs a 'code'."),
        ([{"do": "Go", "commands": [{"platform": "", "code": "x"}]}], "Step 1: command 1 needs a 'platform'."),
    ])
    def test_rule_breaks_are_named_by_step(self, owner, access, rows, message):
        response = self.post(owner, access, rows)
        assert response.status_code == 200 and not ControlVersion.objects.exists()
        assert message in unescape(response.content.decode())

    @pytest.mark.parametrize("rows", [{"do": "x"}, ["loose"], [{"do": 5}], [{"do": "x", "commands": "no"}], [{"do": "x", "commands": ["no"]}]])
    def test_hand_made_shapes_are_refused(self, owner, access, rows):
        response = self.post(owner, access, rows)
        assert response.status_code == 200 and not ControlVersion.objects.exists()
        assert "Something went wrong with this section" in response.content.decode()

    def test_the_form_shows_the_new_sections_and_nested_editor(self, owner, access):
        html = owner.get(reverse("rcm:control_new")).content.decode()
        assert "How to build it" in html and 'data-name="commands"' in html and 'data-field="evidence_keep"' in html
        assert "Choosing who performs and who reviews" in html and 'name="people_performer"' in html
        for gone in ("What good looks like", "Timings your team sets", 'data-field="role"', 'data-field="part"', 'data-field="sox_only"'):
            assert gone not in html

    def test_people_notes_are_saved_and_come_back_on_edit(self, owner, reviewer, access):
        data = control_post(
            access, people_performer="Sees the alerts\n\n Can rerun a job ", people_reviewer="Doesn't operate it",
            people_small_team=" Ask another team. ",
        )
        assert owner.post(reverse("rcm:control_new"), data).status_code == 302
        version = ControlVersion.objects.get()
        assert version.choosing_people == {
            "performer": ["Sees the alerts", "Can rerun a job"], "reviewer": ["Doesn't operate it"],
            "small_team": "Ask another team.",
        }
        form = owner.get(reverse("rcm:control_edit", args=[version.entity.ident])).context["form"]
        assert form.initial["people_performer"] == "Sees the alerts\nCan rerun a job"
        assert form.initial["people_small_team"] == "Ask another team."

    def test_empty_people_boxes_store_nothing(self, owner, access):
        owner.post(reverse("rcm:control_new"), control_post(access))
        assert ControlVersion.objects.get().choosing_people == {}

    def test_editing_shows_stored_steps_in_the_form_shape(self, owner, reviewer, access):
        control, _ = published_control(access, owner.user, reviewer.user, steps=[FULL_STEP])
        form = owner.get(reverse("rcm:control_edit", args=[control.ident])).context["form"]
        row = json.loads(form["steps"].value())[0]
        assert row["weigh"] == "Who is affected downstream\nWho can fix it out of hours"
        assert row["evidence_keep"] == "The job inventory" and row["evidence_shows"] == "The date it was pulled\nEvery job"
        assert row["commands"] == FULL_STEP["commands"]
        # Saving what the form shows gives the same steps back (the code loses only its closing blank line).
        posted = control_post(access, steps=json.dumps([row]), change_summary="Same")
        assert owner.post(reverse("rcm:control_edit", args=[control.ident]), posted).status_code == 302
        saved = control.versions.get(number=2).steps[0]
        assert saved == {**FULL_STEP, "commands": [
            {**FULL_STEP["commands"][0], "code": "SELECT name\nFROM msdb.dbo.sysjobs;"}, FULL_STEP["commands"][1],
        ]}


# The content files

FILE = """
topic: Access management
controls:
  - id: AM-90
    title: A control
    why: Because.
    nature: preventive
    method: automated
    frequency: event
    owned_by: Owner
    level: key
    stage: Provisioning
    categories: [application]
    steps:
      - do: List your jobs.
        how: Pull every job.
        weigh:
          - Who is affected downstream
        policy: "[Access Control Policy](#todo-access-control-policy)"
        evidence:
          keep: The job inventory
          shows:
            - The date it was pulled
        commands:
          - platform: SQL Server
            note: Lists the jobs.
            code: |
              SELECT name
              FROM msdb.dbo.sysjobs;
          - platform: Splunk
            code: index=jobs
      - do: Review it regularly.
    choosing_people:
      performer:
        - Sees the alerts daily
      reviewer:
        - Doesn't operate the jobs
      small_team: Ask another team.
"""


@pytest.fixture
def lead(db):
    call_command("seed_topics")
    call_command("seed_platforms")
    return make_user("lead", "tech_risk")


def sync(folder, **options):
    out = io.StringIO()
    call_command("sync_controls", stdout=out, **{"user": "lead", "folder": str(folder), **options})
    return out.getvalue()


def write(folder, text, name="topic.yaml"):
    (Path(folder) / name).write_text(text, encoding="utf-8")


def problems(folder):
    with pytest.raises(CommandError) as error:
        sync(folder)
    assert not ControlVersion.objects.exists()
    return str(error.value)


def test_sync_reads_steps_and_people(lead, tmp_path):
    write(tmp_path, FILE)
    sync(tmp_path)
    version = ControlVersion.objects.get()
    assert version.steps[0]["do"] == "List your jobs." and version.steps[1] == {"do": "Review it regularly."}
    assert version.steps[0]["evidence"] == {"keep": "The job inventory", "shows": ["The date it was pulled"]}
    assert version.steps[0]["commands"][0] == {
        "platform": "SQL Server", "note": "Lists the jobs.", "code": "SELECT name\nFROM msdb.dbo.sysjobs;\n",
    }
    assert version.choosing_people["small_team"] == "Ask another team."


@pytest.mark.parametrize("old, new, fragments", [
    ("      - do: Review it regularly.\n", "      - how: No title.\n", ("control 'AM-90'", "step 2", "needs a 'do' line")),
    ("        how: Pull every job.\n", "        how: Pull every job.\n        who: Owner\n", ("step 1", "'who' isn't a known field")),
    ("        how: Pull every job.\n", "        how: Pull every job.\n        part: monitoring\n", ("step 1", "'part' isn't a known field")),
    ("          keep: The job inventory\n", "          shows: [x]\n", ("step 1", "'evidence' needs a 'keep' line")),
    ("        evidence:\n          keep: The job inventory\n          shows:\n            - The date it was pulled\n",
     "        evidence: Signed review\n", ("step 1", "Plain text isn't used any more")),
    ("          - Who is affected downstream\n", "          - ''\n", ("step 1", "'weigh' needs a list")),
    ("          - platform: Splunk\n", "          - note: No platform\n", ("step 1", "command 2 needs a 'platform'")),
    ("            code: index=jobs\n", "            note: No code\n", ("step 1", "command 2 needs a 'code'")),
    ("      small_team: Ask another team.\n", "      small_team: Ask.\n      backup: Name one.\n", ("choosing_people", "'backup' isn't a known field")),
    ("      performer:\n        - Sees the alerts daily\n", "      performer: Sees alerts\n", ("choosing_people", "'performer' needs a list")),
    ("    steps:\n", "    criteria:\n      - heading: Old\n        items: [x]\n    steps:\n", ("control 'AM-90'", "'criteria' isn't a known field")),
    ("    steps:\n", "    timings:\n      - set: x\n        policy: y\n    steps:\n", ("'timings' isn't a known field",)),
])
def test_mistakes_get_plain_messages_naming_file_control_and_step(lead, tmp_path, old, new, fragments):
    assert old in FILE
    write(tmp_path, FILE.replace(old, new, 1))
    message = problems(tmp_path)
    assert "topic.yaml" in message
    for fragment in fragments:
        assert fragment in message


def test_steps_that_are_not_a_list_is_a_plain_message(lead, tmp_path):
    write(tmp_path, FILE.split("    steps:")[0] + "    steps: first do this\n")
    message = problems(tmp_path)
    assert "control 'AM-90'" in message and "field 'steps'" in message and "expected a list of steps" in message


def test_a_command_for_an_unknown_platform_warns_and_is_kept(lead, tmp_path, capsys):
    write(tmp_path, FILE.replace("platform: Splunk", "platform: Splonk"))
    sync(tmp_path)
    warning = capsys.readouterr().err
    assert "topic.yaml, control 'AM-90', step 1, field 'commands' or 'checks': no platform named 'Splonk'" in warning
    assert [c["platform"] for c in ControlVersion.objects.get().steps[0]["commands"]] == ["SQL Server", "Splonk"]


def test_known_platforms_give_no_warning(lead, tmp_path, capsys):
    write(tmp_path, FILE)
    sync(tmp_path)
    assert "no platform named" not in capsys.readouterr().err


def test_check_controls_reports_problems_and_warnings(lead, tmp_path, capsys):
    write(tmp_path, FILE.replace("platform: Splunk", "platform: Splonk"))
    call_command("check_controls", folder=str(tmp_path))
    assert "Warning: topic.yaml, control 'AM-90', step 1" in capsys.readouterr().out


def test_changing_a_step_proposes_a_change_and_removing_people_removes_them(lead, tmp_path, settings):
    settings.ALLOW_SELF_APPROVAL = True
    write(tmp_path, FILE)
    sync(tmp_path, publish=True)
    assert "unchanged" in sync(tmp_path)
    write(tmp_path, FILE.replace("Who is affected downstream", "Who is affected next"))
    assert "Proposed a change to AM-90" in sync(tmp_path)
    assert ControlVersion.objects.get(status="draft").steps[0]["weigh"] == ["Who is affected next"]


def test_leaving_people_out_of_the_file_clears_them(lead, tmp_path, settings):
    settings.ALLOW_SELF_APPROVAL = True
    write(tmp_path, FILE)
    sync(tmp_path, publish=True)
    write(tmp_path, FILE.split("    choosing_people:")[0])
    sync(tmp_path)
    assert ControlVersion.objects.get(status="draft").choosing_people == {}


def export(tmp_path, source_text, settings):
    settings.ALLOW_SELF_APPROVAL = True
    source, out = tmp_path / "in", tmp_path / "out"
    source.mkdir()
    out.mkdir()
    write(source, source_text)
    sync(source, publish=True)
    call_command("export_controls", topic="Access management", folder=str(out), stdout=io.StringIO())
    return out, (out / "access-management.yaml").read_text(encoding="utf-8")


def test_export_round_trips_keeps_key_order_and_writes_code_as_a_block(lead, tmp_path, settings):
    out, text = export(tmp_path, FILE, settings)
    exported = yaml.safe_load(text)["controls"][0]
    assert exported["steps"] == yaml.safe_load(FILE)["controls"][0]["steps"]
    assert exported["choosing_people"] == yaml.safe_load(FILE)["controls"][0]["choosing_people"]
    first = text[text.index("- do: List your jobs."):]
    order = ["how:", "weigh:", "policy:", "evidence:", "keep:", "shows:", "commands:", "platform:", "note:", "code:"]
    positions = [first.index(word) for word in order]
    assert positions == sorted(positions)
    assert "code: |\n" in text and "SELECT name\n" in text and "code: index=jobs" in text
    assert "criteria" not in text and "timings" not in text
    assert "unchanged" in sync(out)


def test_export_leaves_out_what_is_empty(lead, tmp_path, settings):
    _, text = export(tmp_path, FILE.split("    choosing_people:")[0].replace("      - do: Review it regularly.\n", ""), settings)
    assert "choosing_people" not in text and "weigh:" in text


# Search

def test_search_finds_every_step_part_but_not_the_code(owner, reviewer, access):
    published_control(access, owner.user, reviewer.user, steps=[FULL_STEP], choosing_people=PEOPLE)
    text = " ".join(item.text for item in selectors.control_items())
    for phrase in (
        "List your jobs.", "Pull every job from the scheduler.", "Who can fix it out of hours", "Access Control Policy",
        "The job inventory", "The date it was pulled", "Lists the jobs.", "Sees the alerts daily",
        "Doesn't operate the jobs", "Ask someone from another team",
    ):
        assert phrase in text, phrase
    assert "msdb.dbo.sysjobs" not in text and "index=jobs" not in text


# The guide in content/controls/README.md

def test_the_readme_example_passes_the_check(lead, tmp_path):
    readme = (Path(__file__).resolve().parents[3] / "content" / "controls" / "README.md").read_text(encoding="utf-8")
    example = readme.split("```yaml\n", 1)[1].split("```", 1)[0]
    control = yaml.safe_load(example)[0]
    control.update(nature="detective", method="it_dependent", frequency="event", owned_by="Owner", level="key", stage="Provisioning")
    write(tmp_path, yaml.safe_dump({"topic": "Access management", "controls": [control]}, sort_keys=False))
    sync(tmp_path)
    assert len(ControlVersion.objects.get().steps) == 2
