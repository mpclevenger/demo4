"""The link from a control to the engine risks it addresses: the engine ids, the field, the form, the pages,
the content check and the published list at /registers/controls.json."""

import io
import json

import pytest
import yaml
from django.core.management import call_command
from django.urls import include, path, reverse

from apps.core.tests.support import As, anonymous, control_post, publish, published_control
from apps.rcm import engine_files, services
from apps.rcm.models import ControlVersion, EngineRisk

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sso")]

ENGINE_RISK = {
    "domain": "Operational", "category": "Repeat incidents", "name": "The same incident keeps happening",
    "likelihood_drivers": [], "impact_drivers": [],
}


def engine_risk(ident="air.ops.02", name="The same incident keeps happening"):
    return EngineRisk.objects.create(
        key=f"operational-repeat-{ident}", ident=ident, domain="Operational", category="Repeat incidents", name=name
    )


# The engine files carry an id

def write_engine(folder, risks_yaml):
    (folder / "risks").mkdir(parents=True)
    (folder / "risks" / "air.ops.yaml").write_text(risks_yaml, encoding="utf-8")
    (folder / "driver_mapping.yaml").write_text("risk_drivers: {}\n", encoding="utf-8")


def read(folder, tmp_path):
    return engine_files.read_engine(folder, tmp_path / "none.json")


def test_engine_file_keyed_by_risk_id_gives_each_risk_its_id(tmp_path):
    write_engine(tmp_path, yaml.safe_dump({"air.ops.01": {**ENGINE_RISK, "name": "A"}, "air.ops.02": ENGINE_RISK}))
    report = read(tmp_path, tmp_path)
    assert [r["ident"] for r in report.risks] == ["air.ops.01", "air.ops.02"]
    assert not [p for p in report.problems if "air.ops" in p]


def test_engine_file_list_may_give_an_id_field(tmp_path):
    write_engine(tmp_path, yaml.safe_dump([{**ENGINE_RISK, "id": "air.ops.02"}]))
    assert [r["ident"] for r in read(tmp_path, tmp_path).risks] == ["air.ops.02"]


def test_engine_risk_without_an_id_still_loads_with_an_empty_id(tmp_path):
    write_engine(tmp_path, yaml.safe_dump([ENGINE_RISK]))
    report = read(tmp_path, tmp_path)
    assert [r["ident"] for r in report.risks] == [""] and not any("id" in p for p in report.problems)


def test_the_same_engine_risk_id_twice_is_a_problem(tmp_path):
    write_engine(
        tmp_path,
        yaml.safe_dump([{**ENGINE_RISK, "id": "air.ops.02"}, {**ENGINE_RISK, "name": "Other", "id": "air.ops.02"}]),
    )
    assert any("the id air.ops.02 is already used" in p for p in read(tmp_path, tmp_path).problems)


def test_a_bad_engine_risk_id_is_a_problem(tmp_path):
    write_engine(tmp_path, yaml.safe_dump([{**ENGINE_RISK, "id": "air ops 2"}]))
    assert any("the id 'air ops 2' can use letters" in p for p in read(tmp_path, tmp_path).problems)


def test_address_problems_in_plain_words():
    known = {"air.ops.02"}
    assert engine_files.address_problems([], known) == []
    assert engine_files.address_problems(["air.ops.02"], known) == []
    assert engine_files.address_problems("air.ops.02", known) == ["expected a list of risk ids, for example [air.ops.02]."]
    assert "'air.ops.09' isn't the id of a risk" in engine_files.address_problems(["air.ops.09"], known)[0]
    assert "'air.ops.02' is listed twice." in engine_files.address_problems(["air.ops.02", "air.ops.02"], known)


# The field on the control

def test_a_control_has_no_addresses_until_the_owner_maps_them(access, owner, reviewer):
    _, version = published_control(access, owner.user, reviewer.user)
    assert version.addresses == []


def test_addresses_must_be_a_list_of_ids_each_once(access, owner):
    _, version = services.create_control(
        owner.user, access, title="T", why="w", owner_role="Ops", nature="detective", method="manual", frequency="monthly",
    )
    for bad in ("air.ops.02", [1], ["a", "a"]):
        version.addresses = bad
        with pytest.raises(Exception) as error:
            version.full_clean(exclude=["entity", "proposed_by", "number"])
        assert "addresses" in str(error.value)


def post_with(access, owner, **over):
    return owner.post(reverse("rcm:control_new"), control_post(access, **over))


def test_the_form_saves_addresses_one_id_per_line(access, owner):
    engine_risk()
    response = post_with(access, owner, addresses="air.ops.02\n\n air.ops.02 \n")
    assert response.status_code == 302
    assert ControlVersion.objects.get().addresses == ["air.ops.02"]


def test_the_form_says_which_id_the_engine_files_lack(access, owner):
    engine_risk()
    response = post_with(access, owner, addresses="air.ops.02\nair.ops.77")
    assert response.status_code == 200
    assert "Not in the risk engine files: air.ops.77." in response.content.decode()
    assert not ControlVersion.objects.exists()


def test_the_form_leaves_addresses_empty_when_the_box_is_empty(access, owner):
    assert post_with(access, owner).status_code == 302
    assert ControlVersion.objects.get().addresses == []


def test_a_change_is_proposed_and_approved_like_other_fields(access, owner, reviewer):
    engine_risk()
    control, first = published_control(access, owner.user, reviewer.user)
    form = control_post(access, addresses="air.ops.02", change_summary="Map the risk.")
    form.pop("ident")
    response = owner.post(reverse("rcm:control_edit", args=[control.ident]), form)
    assert response.status_code == 302
    draft = control.versions.exclude(pk=first.pk).get()
    assert draft.status == "draft" and draft.addresses == ["air.ops.02"]
    assert first.addresses == []
    publish(draft, reviewer.user)
    assert control.current().addresses == ["air.ops.02"]


def test_an_old_id_the_engine_dropped_does_not_block_another_edit(access, owner, reviewer):
    control, _ = published_control(access, owner.user, reviewer.user, addresses=["air.gone.01"])
    form = control_post(access, addresses="air.gone.01", change_summary="Fix a typo.")
    form.pop("ident")
    assert owner.post(reverse("rcm:control_edit", args=[control.ident]), form).status_code == 302


# The pages

def test_control_page_lists_the_risks_it_addresses(access, owner, reviewer):
    engine_risk()
    control, _ = published_control(access, owner.user, reviewer.user, addresses=["air.ops.02"])
    html = owner.get(control.get_absolute_url()).content.decode()
    assert "Risks it addresses" in html and "air.ops.02" in html and "The same incident keeps happening" in html


def test_control_page_draws_nothing_when_it_addresses_no_risk(access, owner, reviewer):
    control, _ = published_control(access, owner.user, reviewer.user)
    assert "Risks it addresses" not in owner.get(control.get_absolute_url()).content.decode()


def test_control_page_calls_its_own_risk_statement_what_could_go_wrong(access, owner, reviewer):
    control, _ = published_control(access, owner.user, reviewer.user)
    _, version = services.create_risk(owner.user, access, title="Leaver keeps access", statement="A leaver signs in later.", owner_role="IAM")
    services.set_risk_links(version, owner.user, controls=[(control, "full", "Removes leavers")])
    publish(version, reviewer.user)
    html = owner.get(control.get_absolute_url()).content.decode()
    assert "What could go wrong" in html and "A leaver signs in later." in html and "Addresses:" not in html


def test_engine_risks_page_lists_the_controls_that_address_each_risk(access, owner, reviewer):
    engine_risk()
    engine_risk("air.ops.03", "Another")
    control, _ = published_control(access, owner.user, reviewer.user, title="Review jobs", addresses=["air.ops.02"])
    html = owner.get(reverse("rcm:engine_risks")).content.decode()
    assert html.count("Controls that address this risk") == 1
    assert control.ident in html and "Review jobs" in html and "air.ops.02" in html and "air.ops.03" in html


def test_explorer_by_control_shows_the_risks_it_addresses(access, owner, reviewer):
    engine_risk()
    published_control(access, owner.user, reviewer.user, addresses=["air.ops.02"])
    html = owner.get(reverse("rcm:explorer") + "?view=controls").content.decode()
    assert "Risks it addresses" in html and "air.ops.02" in html


# The content check

def check(folder):
    out = io.StringIO()
    try:
        call_command("check_controls", folder=str(folder), stdout=out)
    except SystemExit:
        pass
    return out.getvalue()


def test_check_controls_ignores_controls_without_addresses(tmp_path, topics):
    (tmp_path / "t.yaml").write_text("topic: Access management\nrisks: []\ncontrols: []\n", encoding="utf-8")
    assert "Problem" not in check(tmp_path)


# The published list

@pytest.fixture
def registers(settings):
    """Serve /registers/ from a test URL list, so the test doesn't depend on config/urls.py."""
    import types, sys

    module = types.ModuleType("registers_test_urls")
    from config import urls as base

    module.urlpatterns = [*base.urlpatterns, path("registers/", include("apps.rcm.urls_registers"))]
    sys.modules["registers_test_urls"] = module
    settings.ROOT_URLCONF = "registers_test_urls"
    yield
    del sys.modules["registers_test_urls"]


def test_controls_json_has_exactly_the_agreed_shape_sorted_by_code(registers, access, owner, reviewer):
    engine_risk()
    published_control(access, owner.user, reviewer.user, title="Second")  # a code the system makes
    _, last = published_control(access, owner.user, reviewer.user, title="Third", addresses=["air.ops.02"])
    services.create_control(owner.user, access, title="Draft only", why="w", owner_role="Ops", nature="detective", method="manual", frequency="monthly")
    body = json.loads(owner.get("/registers/controls.json").content)
    assert list(body) == ["published_at", "controls"]
    codes = [c["code"] for c in body["controls"]]
    assert codes == sorted(codes) and len(codes) == 2
    assert all(list(c) == ["code", "title", "url", "addresses"] for c in body["controls"])
    third = next(c for c in body["controls"] if c["title"] == "Third")
    assert third["addresses"] == ["air.ops.02"] and third["url"] == f"http://testserver/rcm/controls/{third['code']}/"
    assert body["published_at"] == last.published_at.isoformat()


def test_controls_json_with_nothing_published(registers, owner):
    assert json.loads(owner.get("/registers/controls.json").content) == {"published_at": None, "controls": []}


def test_controls_json_needs_the_same_access_as_a_page(registers):
    assert anonymous().get("/registers/controls.json").status_code == 403


def test_controls_json_is_readable_by_any_signed_in_reader(registers, access, owner, reviewer):
    published_control(access, owner.user, reviewer.user)
    assert As("someone", "ro").get("/registers/controls.json").status_code == 200


def test_a_risk_file_from_the_risk_sites_download_takes_its_id_from_its_file_name(tmp_path):
    from apps.rcm.engine_files import _id_from_file_name
    one_risk = [{"domain": "Operations", "category": "Jobs", "name": "A job fails unnoticed"}]
    assert _id_from_file_name(tmp_path / "air.ops.02.yaml", one_risk) == "air.ops.02"
    assert _id_from_file_name(tmp_path / "cyber-unauthorized-access.yaml", one_risk) is None   # a topic name, not an id
    assert _id_from_file_name(tmp_path / "air.ops.yaml", one_risk) is None                    # a file of several risks
    assert _id_from_file_name(tmp_path / "air.ops.02.yaml", [{**one_risk[0], "id": "air.ops.09"}]) is None   # the file says
