"""The things we measure and how they connect (owner, 15 Nov 2026): written by every mapping run from the
mapped month, and matching it exactly: the same people, teams, applications and repositories, placed the same way."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, retention, storage, things  # noqa: E402
from testdata import seed_store  # noqa: E402

MONTH = "2026-10"


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "cto.demo"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    seed_store([MONTH], families=8)
    return storage.load_month("mapped", MONTH)


def test_every_mapped_person_app_and_repo_is_a_thing(seeded):
    feeds = seeded["feeds"]
    keys = lambda kind: {t["key"] for t in storage.things(MONTH, kind)}
    assert keys("person") == {p["sam_account"] for p in feeds["hr"]["people"]}
    assert keys("application") == {a["app_id"] for a in feeds["app_inventory"]["rows"]}
    assert keys("repository") == {r["repo"] for r in feeds["repos"]["rows"]}
    assert keys("itdr_application") == {str(r["ref"]) for r in feeds["itdr"]["rows"]}
    assert {k for k in keys("team") if k.startswith("family:")} >= {"family:" + f["family_id"] for f in feeds["hr_mapping"]["rows"]}


def test_family_placements_match_the_mapped_month(seeded):
    """The side-by-side check: placing by the links gives the same families as the mapped rows."""
    feeds, links = seeded["feeds"], storage.thing_links(MONTH)

    def placed(kind, relation):
        return {l["from_key"]: l["to_key"][len("family:"):] for l in links
                if l["from_kind"] == kind and l["relation"] == relation and l["to_key"].startswith("family:")}

    want = lambda rows, key: {str(r[key]): r["family_id"] for r in rows if r.get("family_id") not in things.UNPLACED}
    assert placed("person", "member_of") == want(feeds["hr"]["people"], "sam_account")
    assert placed("repository", "placed_with") == want(feeds["repos"]["rows"], "repo")
    assert placed("application", "placed_with") == want(feeds["app_inventory"]["rows"], "app_id")
    assert placed("itdr_application", "placed_with") == want(feeds["itdr"]["rows"], "ref")
    # the roll-up used by every grouping gives the same head count as the owners file's own count
    for f in feeds["hr_mapping"]["families"]:
        assert len(things.members(MONTH, "family:" + f["family_id"])) == f["people"]


def test_every_link_joins_two_things_and_says_how(seeded):
    have = {(t["kind"], t["key"]) for t in storage.things(MONTH)}
    links = storage.thing_links(MONTH)
    assert links
    for l in links:
        assert (l["from_kind"], l["from_key"]) in have and (l["to_kind"], l["to_key"]) in have, l
        assert l["how"]
    rel = {l["relation"] for l in links}
    assert {"reports_to", "member_of", "placed_with", "owned_by", "serves", "same_as"} <= rel
    # departments and L3 / L4 teams are there for the risk assessment's groups
    kinds = {t["key"].split(":")[0] for t in storage.things(MONTH, "team")}
    assert {"family", "department", "l3", "l4"} <= kinds


def test_mapping_again_replaces_and_a_removed_month_leaves_nothing(seeded):
    before = (storage.things(MONTH), storage.thing_links(MONTH))
    mapping.map_month(MONTH, "Tester")
    assert (storage.things(MONTH), storage.thing_links(MONTH)) == before        # same files, same things: no doubles
    storage.remove_month(MONTH)
    assert storage.things(MONTH) == [] and storage.thing_links(MONTH) == []


def test_a_month_with_no_files_has_no_things(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    assert things.build({"month": "2026-07", "feeds": {}}) == ([], [])
    mapping.map_month("2026-07", "Tester")
    assert storage.things("2026-07") == []
