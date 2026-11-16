"""TRAC's own codes (CM, AM, MO): renaming old sites, old addresses, and keeping the old codes out of the content."""

import importlib
import io
import re
import shutil

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command

from apps.core.tests.support import As, make_user, published_control, published_driver
from apps.rcm import services
from apps.rcm.control_files import DEFAULT_FOLDER
from apps.rcm.models import Control, DriverVersion, IdSequence, Risk
from apps.topics.models import Topic

migration = importlib.import_module("apps.rcm.migrations.0009_trac_own_codes")

pytestmark = pytest.mark.django_db

CONTENT = DEFAULT_FOLDER.parent
OLD_ID = re.compile(r"\b(MC|MA|OP)-\d|R-(MC|MA|OP)-")


@pytest.fixture
def lead(db, settings):
    settings.ALLOW_SELF_APPROVAL = True
    call_command("seed_topics")
    call_command("seed_platforms")
    return make_user("lead", "tech_risk")


def idents(model):
    return sorted(model.objects.values_list("ident", flat=True))


def put_back_old_codes():
    """Make the database look like a site from before the change."""
    migration.backwards(django_apps, None)


def test_a_site_with_old_ids_is_renamed(lead):
    call_command("sync_controls", user="lead", publish=True, folder=str(DEFAULT_FOLDER))
    controls, risks = idents(Control), idents(Risk)
    topic = Topic.objects.get(id_prefix="AM")
    IdSequence.objects.create(key="R-AM", last=3)
    published_driver(lead, make_user("second", "tech_risk"), trac_risks=["R-AM-03", "R-LA-01", "RD-free-text"])

    put_back_old_codes()
    assert "MA-01" in idents(Control) and "R-MC-01" in idents(Risk)
    assert Topic.objects.get(pk=topic.pk).id_prefix == "MA" and IdSequence.objects.filter(key="R-MA").exists()
    assert DriverVersion.objects.get().trac_risks == ["R-MA-03", "R-LA-01", "RD-free-text"]

    migration.forwards(django_apps, None)
    assert (idents(Control), idents(Risk)) == (controls, risks)
    assert Topic.objects.get(pk=topic.pk).id_prefix == "AM" and IdSequence.objects.filter(key="R-AM").exists()
    assert DriverVersion.objects.get().trac_risks == ["R-AM-03", "R-LA-01", "RD-free-text"]
    assert not [i for i in controls + risks if OLD_ID.match(i)]


def test_the_migration_agrees_with_seed_topics(lead):
    put_back_old_codes()
    call_command("seed_topics")
    assert {t.name: t.id_prefix for t in Topic.objects.filter(name__in=["Access management", "Operations and jobs"])} == {
        "Access management": "AM", "Operations and jobs": "MO"
    }
    assert Topic.objects.count() == len(set(Topic.objects.values_list("name", flat=True)))


def test_a_database_that_already_has_the_new_ids_is_left_alone(lead):
    topic = Topic.objects.get(id_prefix="AM")
    for ident in ("MA-02", "AM-02", "MA-03"):
        published_control(topic, lead, lead, ident=ident, title=ident)
    migration.forwards(django_apps, None)
    assert idents(Control) == ["AM-02", "AM-03", "MA-02"]  # MA-02 is skipped because AM-02 exists


def test_ids_from_the_earlier_ojs_draft_become_mo(lead):
    topic = Topic.objects.get(id_prefix="MO")
    Topic.objects.filter(pk=topic.pk).update(id_prefix="OJ")
    services.create_risk(lead, topic, ident="R-OJ-01", title="r", statement="s", owner_role="x")
    published_control(topic, lead, lead, ident="OJ-01", title="c")
    migration.forwards(django_apps, None)
    assert idents(Control) == ["MO-01"] and idents(Risk) == ["R-MO-01"]
    assert Topic.objects.get(pk=topic.pk).id_prefix == "MO"


def test_the_migration_runs_on_an_empty_database(db):
    migration.forwards(django_apps, None)
    migration.backwards(django_apps, None)


def test_sync_treats_a_renamed_control_as_the_same_one(lead, tmp_path):
    shutil.copy(DEFAULT_FOLDER / "change-management.yaml", tmp_path)
    call_command("sync_controls", user="lead", publish=True, folder=str(tmp_path))
    before = {c.pk: c.ident for c in Control.objects.all()}
    put_back_old_codes()
    migration.forwards(django_apps, None)

    out = io.StringIO()
    call_command("sync_controls", user="lead", publish=True, folder=str(tmp_path), stdout=out)
    assert {c.pk: c.ident for c in Control.objects.all()} == before
    assert "0 new, 0 updated" in out.getvalue() and "unchanged" in out.getvalue()


@pytest.mark.parametrize("old, new", [
    ("/rcm/controls/MC-02/", "/rcm/controls/CM-02/"),
    ("/rcm/controls/MA-01/?version=2", "/rcm/controls/AM-01/?version=2"),
    ("/rcm/controls/OP-03/", "/rcm/controls/MO-03/"),
    ("/rcm/risks/R-MC-01/", "/rcm/risks/R-CM-01/"),
    ("/rcm/risks/R-OP-02/", "/rcm/risks/R-MO-02/"),
])
def test_old_addresses_move_permanently_to_the_new_code(sso, old, new):
    response = As("reader").get(old)
    assert response.status_code == 301 and response["Location"] == new


def test_other_codes_are_not_redirected(sso):
    assert As("reader").get("/rcm/controls/LA-01/").status_code != 301
    assert As("reader").get("/rcm/controls/CM-02/").status_code != 301


def test_old_codes_do_not_creep_back_into_the_content():
    files = [p for folder in ("controls", "guides", "platforms", "home") for p in (CONTENT / folder).rglob("*") if p.is_file()]
    assert files
    found = [f"{p.relative_to(CONTENT)}:{n}" for p in files for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if OLD_ID.search(line) and not line.lstrip().startswith("TRAC codes are not")]
    assert found == []
