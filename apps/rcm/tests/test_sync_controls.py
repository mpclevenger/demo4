"""Content files in content/controls: check, sync and export."""

import io
from pathlib import Path
import re
import shutil

import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core import versioning as v
from apps.core.content_sync import recorded
from apps.rcm import control_files, levels
from apps.core.tests.support import make_user
from apps.rcm.models import ControlVersion, RiskControlLink, RiskVersion
from apps.rcm.control_files import DEFAULT_FOLDER
from apps.wiki.guide_checks import PRODUCT_TERMS

pytestmark = pytest.mark.django_db

BANNED = re.compile(
    r"standard|reach out|tech risk|route through|\bNIST\b|\bISO\b|COBIT|ITIL|\bCIS\b", re.IGNORECASE
)

GOOD = """
topic: Change management
risks:
  - id: R-CM-01
    title: A risk
    statement: Something goes wrong.
    owned_by: Application owner
    stage: Release
    covered_by:
      - {control: CM-01, coverage: full, why: It helps.}
controls:
  - id: CM-01
    title: A control
    why: Because.
    nature: preventive
    method: automated
    frequency: event
    owned_by: Owner
    level: key
    stage: Release
    categories: [application]
    platforms: [No Such Platform]
    steps:
      - do: Do the thing.
        how: Carefully.
"""


@pytest.fixture
def lead(db):
    call_command("seed_topics")
    call_command("seed_platforms")
    return make_user("lead", "tech_risk")


def folder_with(tmp_path, text, name="topic.yaml"):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return str(tmp_path)


def fails_with(tmp_path, text, *fragments):
    folder = folder_with(tmp_path, text)
    with pytest.raises(CommandError) as error:
        call_command("sync_controls", user="lead", folder=folder)
    message = str(error.value)
    assert "topic.yaml" in message
    for fragment in fragments:
        assert fragment in message
    assert not ControlVersion.objects.exists()


# These tests use the change management file on its own, so adding other topic files doesn't change them.
CHANGE_FILE = DEFAULT_FOLDER / "change-management.yaml"


def change_file():
    """The change management file as shipped. The tests below read what they expect from it, not from its wording."""
    return yaml.safe_load(CHANGE_FILE.read_text(encoding="utf-8"))


def first_control():
    return change_file()["controls"][0]


def counts():
    data = change_file()
    return len(data["controls"]), len(data["risks"])


def shipped_control_count():
    return sum(len(yaml.safe_load(path.read_text(encoding="utf-8")).get("controls", [])) for path in DEFAULT_FOLDER.glob("*.yaml"))


def test_creates_drafts_with_links_and_can_run_again(lead, folder):
    controls_in_file, risks_in_file = counts()
    call_command("sync_controls", user="lead", folder=folder)
    controls = ControlVersion.objects.filter(entity__ident__startswith="CM-")
    assert controls.count() == controls_in_file
    assert not controls.exclude(status="draft").exists()
    assert controls.get(title=first_control()["title"]).level in levels.keys()
    assert RiskVersion.objects.count() == risks_in_file
    risk = next(r for r in change_file()["risks"] if r.get("covered_by"))
    synced = RiskVersion.objects.get(title=risk["title"])
    assert synced.control_links.count() == len(risk["covered_by"])

    links = RiskControlLink.objects.count()
    call_command("sync_controls", user="lead", folder=folder)
    assert (ControlVersion.objects.count(), RiskVersion.objects.count(), RiskControlLink.objects.count()) == (
        controls_in_file, risks_in_file, links
    )


def test_setup_trac_syncs_the_controls():
    make_user("lead", "tech_risk")
    call_command("setup_trac", user="lead")
    assert ControlVersion.objects.count() == shipped_control_count()


def test_unknown_platform_is_skipped_with_a_warning(lead, tmp_path, capsys):
    call_command("sync_controls", user="lead", folder=folder_with(tmp_path, GOOD))
    assert "No Such Platform" in capsys.readouterr().err
    assert ControlVersion.objects.get().platforms.count() == 0


@pytest.mark.parametrize("old, new, fragments", [
    ("categories: [application]", "categories: [applications]", ("'applications'", "categories")),
    ("stage: Release\n    categories", "stage: Ship it\n    categories", ("'Ship it'", "Stages:")),
    ("nature: preventive", "nature: preventative", ("'preventative'", "nature", "preventive")),
    ("coverage: full", "coverage: mostly", ("'mostly'", "coverage")),
    ("control: CM-01", "control: CM-99", ("'CM-99'", "isn't the id of a control")),
    ("topic: Change management", "topic: Nonsense", ("'Nonsense'", "topic")),
    ("    why: Because.\n", "", ("field 'why' is missing",)),
    ("    title: A control", "    title: A control\n    colour: red", ("'colour'", "isn't a known field")),
    ("- do: Do the thing.", "- do: Do the thing.\n        who: Owner", ("control 'CM-01'", "step 1", "'who' isn't a known field")),
])
def test_mistakes_get_plain_messages_naming_the_file(lead, tmp_path, old, new, fragments):
    assert old in GOOD
    fails_with(tmp_path, GOOD.replace(old, new, 1), *fragments)


def test_broken_yaml_is_reported_in_plain_words(lead, tmp_path):
    fails_with(tmp_path, "topic: [unclosed\n", "isn't valid YAML")


def test_check_controls_passes_on_the_shipped_files(lead, capsys):
    call_command("check_controls")
    assert "All good" in capsys.readouterr().out


def test_check_controls_fails_on_a_bad_file_and_writes_nothing(lead, tmp_path, capsys):
    folder = folder_with(tmp_path, GOOD.replace("nature: preventive", "nature: sometimes"))
    with pytest.raises(SystemExit) as stop:
        call_command("check_controls", folder=folder)
    assert stop.value.code == 1
    assert "topic.yaml" in capsys.readouterr().out
    assert not ControlVersion.objects.exists()


def test_shipped_yaml_avoids_banned_phrases():
    for path in DEFAULT_FOLDER.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        for term in PRODUCT_TERMS:
            text = re.sub(re.escape(term), " ", text, flags=re.IGNORECASE)
        assert not BANNED.findall(text), path.name


def test_check_controls_flags_banned_wording(lead, tmp_path, capsys):
    folder = folder_with(tmp_path, GOOD.replace("why: Because.", "why: Because it is standard."))
    with pytest.raises(SystemExit):
        call_command("check_controls", folder=folder)
    assert 'topic.yaml: the text contains "standard"' in capsys.readouterr().out


# ---- keeping the site and the files in step ----

def sync(*args, **options):
    out = io.StringIO()
    call_command("sync_controls", *args, stdout=out, **{"user": "lead", **options})
    return out.getvalue()


@pytest.fixture
def folder(tmp_path):
    shutil.copy(CHANGE_FILE, tmp_path)
    return str(tmp_path)


@pytest.fixture
def single(settings):
    settings.ALLOW_SELF_APPROVAL = True


def edit_file(folder, **changes):
    """Change fields of the first control in the file."""
    path = next(iter(sorted(Path(folder).glob("*.yaml"))))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["controls"][0].update(changes)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def total():
    return sum(counts())


def test_second_sync_says_unchanged(lead, folder):
    sync(folder=folder)
    out = sync(folder=folder)
    assert f"{first_control()['title']}: unchanged." in out
    assert f"0 new, 0 updated, {total()} unchanged, 0 skipped." in out


def test_a_changed_entry_becomes_a_proposal(lead, folder, single):
    sync(folder=folder, publish=True)
    edit_file(folder, why="A second pair of eyes catches mistakes.")
    out = sync(folder=folder)
    first = first_control()
    assert f"Proposed a change to {first['id']}: {first['title']}." in out
    assert f"1 updated, {total() - 1} unchanged" in out
    draft = ControlVersion.objects.get(title=first["title"], status="draft")
    assert draft.number == 2 and "second pair of eyes" in draft.why
    assert draft.change_summary.startswith("Updated from content/controls/")
    assert recorded(draft.entity).version_id == draft.pk


def test_changed_risk_links_follow_the_file(lead, folder, single):
    sync(folder=folder, publish=True)
    risk = next(r for r in change_file()["risks"] if r.get("covered_by"))
    link = risk["covered_by"][0]
    path = next(iter(sorted(Path(folder).glob("*.yaml"))))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    next(r for r in data["risks"] if r["id"] == risk["id"])["covered_by"][0]["why"] = "Catches it, after the fact."
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    sync(folder=folder)
    draft = RiskVersion.objects.get(title=risk["title"], status="draft")
    assert draft.control_links.count() == len(risk["covered_by"])
    assert draft.control_links.get(control__ident=link["control"]).rationale == "Catches it, after the fact."


def test_open_proposal_blocks_the_update(lead, folder):
    sync(folder=folder)
    edit_file(folder, why="Changed wording for mistakes.")
    out = sync(folder=folder)
    title = first_control()["title"]
    assert f"{title}: a change is already in progress in the site; finish or discard it first." in out
    assert ControlVersion.objects.filter(title=title).count() == 1


def site_edit(user):
    entity = ControlVersion.objects.get(title=first_control()["title"]).entity
    draft = v.propose_change(entity, user, "Edited in the site", why="Edited in the site.")
    v.submit(draft, user)
    v.approve_and_publish(draft, user)
    return draft


def test_site_edits_are_not_recorded_as_synced_and_block_the_sync(lead, folder, single):
    sync(folder=folder, publish=True)
    edited = site_edit(lead)
    assert recorded(edited.entity).version_id != edited.pk
    edit_file(folder, why="Changed wording for mistakes.")
    out = sync(folder=folder)
    assert f"{first_control()['title']}: edited in the site since the file was last synced. Run export_controls first to bring that edit into the file, or use --force to replace it." in out
    assert not ControlVersion.objects.filter(status="draft").exists()


def test_force_replaces_a_site_edit(lead, folder, single):
    sync(folder=folder, publish=True)
    site_edit(lead)
    edit_file(folder, why="Changed wording for mistakes.")
    assert f"Proposed a change to {first_control()['id']}" in sync(folder=folder, force=True)
    assert "Changed wording" in ControlVersion.objects.get(title=first_control()["title"], status="draft").why


def test_publish_is_allowed_in_single_approver_mode(lead, folder, single):
    sync(folder=folder, publish=True)
    assert not ControlVersion.objects.exclude(status="published").exists()
    assert not RiskVersion.objects.exclude(status="published").exists()


def test_publish_is_blocked_otherwise(lead, folder, settings):
    settings.ALLOW_SELF_APPROVAL = False
    with pytest.raises(CommandError, match="single-approver mode"):
        sync(folder=folder, publish=True)
    assert not ControlVersion.objects.exists()


def test_dry_run_changes_nothing_and_says_what_would_happen(lead, folder):
    out = sync(folder=folder, dry_run=True)
    first = first_control()
    assert f"Would create control draft {first['id']}: {first['title']}." in out
    assert f"Would change: {total()} new" in out
    assert not ControlVersion.objects.exists() and not RiskVersion.objects.exists()


def test_dry_run_on_a_changed_entry(lead, folder, single):
    sync(folder=folder, publish=True)
    edit_file(folder, why="Changed wording for mistakes.")
    first = first_control()
    assert f"Would propose a change to {first['id']}: {first['title']}." in sync(folder=folder, dry_run=True)
    assert not ControlVersion.objects.filter(status="draft").exists()


def test_export_then_sync_says_unchanged_for_everything(lead, folder, single, tmp_path_factory):
    sync(folder=folder, publish=True)
    site_edit(lead)
    out_folder = str(tmp_path_factory.mktemp("export"))
    call_command("export_controls", topic="Change management", folder=out_folder, stdout=io.StringIO())
    exported = next(iter(Path(out_folder).glob("*.yaml"))).read_text(encoding="utf-8")
    assert exported.startswith("#")
    assert "Edited in the site." in exported
    out = sync(folder=out_folder)
    assert f"0 new, 0 updated, {total()} unchanged, 0 skipped." in out
    call_command("check_controls", folder=out_folder, stdout=io.StringIO())


def test_export_of_unknown_topic_is_a_plain_error(lead, tmp_path):
    with pytest.raises(CommandError, match="No topic named"):
        call_command("export_controls", topic="Nonsense", folder=str(tmp_path))


def test_ids_come_from_the_file_and_a_new_id_renames_the_same_control(lead, tmp_path, single):
    from apps.rcm.models import Control

    path = tmp_path / "topic.yaml"
    path.write_text(GOOD, encoding="utf-8")
    report = control_files.read_folder(tmp_path)
    assert not report.problems
    control_files.sync(report, lead, lambda m: None, publish=True)
    control = Control.objects.get(ident="CM-01")
    path.write_text(GOOD.replace("id: CM-01", "id: CHG-001").replace("control: CM-01", "control: CHG-001"), encoding="utf-8")
    control_files.sync(control_files.read_folder(tmp_path), lead, lambda m: None, publish=True)
    control.refresh_from_db()
    assert control.ident == "CHG-001"
    assert Control.objects.count() == 1


def test_a_repeated_id_is_a_problem(lead, tmp_path):
    fails_with(tmp_path, GOOD + GOOD.split("controls:\n", 1)[1], "'CM-01' is already used by another control")
