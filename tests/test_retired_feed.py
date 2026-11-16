"""The risk assessments file is retired (owner, 16 Nov 2026): risk results come from the Risk site.
A month that already holds an uploaded file for it must still map, score and publish, and the file is left alone."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

OLD_FILE = (b"Group,Departments,Assessment date,Risk ID,Applicable,Likelihood,Impact,Drivers\n"
            b"Ops A,Payments Ops,03/02/2026,air.cyber.01,,high,Med,RD01 own accounts\n")


def _plain_store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "cto.demo"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))


def test_the_feed_is_no_longer_offered_and_an_upload_says_why():
    from trust import store
    assert "risk_assessments" not in store.FEEDS and "risk_assessments" in store.RETIRED_FEEDS
    with pytest.raises(ValueError, match="Retired 16 Nov 2026: risk results come from the Risk site"):
        store.upload("risk_assessments", "2026-10", OLD_FILE, "risk_assessments.csv", "Test")


def test_an_old_month_holding_the_retired_file_still_maps_scores_and_publishes(tmp_path, monkeypatch):
    import testdata
    from trust import mapping, publish, score_month, storage, store
    _plain_store(tmp_path, monkeypatch)
    testdata.seed_store(["2026-10"], families=4)
    with monkeypatch.context() as old_days:        # put the file in, as the old site did
        old_days.setattr(store, "FEEDS", store.FEEDS + ("risk_assessments",))
        old_days.setattr(store, "RETIRED_FEEDS", {})
        store.upload("risk_assessments", "2026-10", OLD_FILE, "risk_assessments.csv", "Test")
    assert storage.register("2026-10", "risk_assessments")        # kept in the month record
    mapped = mapping.map_month("2026-10", "Test")
    assert "risk_assessments" not in mapped["feeds"]
    assert any("risk_assessments" in note and "no longer used" in note for note in mapped["notes"])
    score_month.run("2026-10", "Test")
    assert "inherent_risk" not in storage.load_month("scored", "2026-10")["period"]
    publish.run("Test")
    assert storage.register("2026-10", "risk_assessments")        # still kept, only ignored


def test_the_made_up_risk_files_for_test_are_complete(monkeypatch):
    """tools/test_risks (TEST only): made-up risk files in the engine's shape; every driver a risk names is in
    the made-up driver_mapping.yaml."""
    import yaml
    from trust import config
    folder = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
    monkeypatch.setenv("TRUST_RISKS", str(folder))
    risks = config.risks()
    assert len(risks) == 8
    assert all(r.get("name") and r.get("description") and r.get("domain") for r in risks.values())
    drivers = yaml.safe_load((folder / "driver_mapping.yaml").read_text())["risk_drivers"]
    named = {d for r in risks.values() for d in r["likelihood_drivers"] + r["impact_drivers"]}
    assert named <= set(drivers), sorted(named - set(drivers))
    assert all(v.get("rationale") and "trigger" in v for v in drivers.values())
