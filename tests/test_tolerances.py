"""Scoring settings changed on the site (owner, 15 Nov 2026): Tech Risk only, every change in the audit
trail, the preview lists exactly the scores that move, and a change applies at the next Update."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import score_month, storage, tolerances  # noqa: E402
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


def test_the_page_starts_from_the_file_values(seeded):
    f = tolerances.fields()
    te02 = next(m for m in f["metrics"] if m["id"] == "TE-02")
    assert (te02["basis"], te02["green"], te02["red"]) == ("Policy", 95, 90)
    caps = {g["path"]: g["value"] for g in f["general"]}
    assert caps["caps.red_metric_block"] == 79 and caps["min_families_for_threshold"] == 5
    assert tolerances.history() == [] and tolerances.preview({})["changes"] == []


def test_values_that_make_no_sense_are_refused_in_plain_words(seeded):
    bad = [({"metrics.TE-02.green": 80}, "must be higher than the Red limit"),          # higher is better
           ({"metrics.TE-02.green": 120}, "from 0 to 100"),
           ({"metrics.TE-01.basis": "Policy"}, "needs both a Green tolerance and a Red limit"),
           ({"metrics.TE-02.basis": "Guess"}, "Policy (fixed) or Prevailing median"),
           ({"caps.red_metric_block": 79.5}, "whole number"), ({"caps.red_metric_block": 101}, "from 0 to 100"),
           ({"caps.red_metric_block": "abc"}, "give a number"), ({"min_families_for_threshold": 0}, "from 1 to 50"),
           ({"switched_on": []}, "isn't a setting this page can change"), ({"metrics.XX-99.green": 1}, "isn't a setting")]
    for changes, words in bad:
        with pytest.raises(ValueError, match=words.replace("(", r"\(").replace(")", r"\)")):
            tolerances.check(changes)
    assert tolerances.check({"metrics.TE-02.green": "95.0", "caps.red_metric_block": 79}) == {}      # nothing differs
    assert storage.setting_changes() == []


def test_the_preview_is_exactly_what_the_next_update_does(seeded):
    before = storage.load_month("scored", MONTH)["period"]
    red = [f for f, r in before["families"].items() if r["metrics"]["TE-02"]["status"] == "Red"]
    assert red, "the made-up month needs a family Red on TE-02"
    changes = {"metrics.TE-02.red": 50, "caps.red_block_trust": 60}
    pv = tolerances.preview(changes)
    assert [c["path"] for c in pv["changes"]] == list(changes) and pv["changes"][0]["before"] == 90
    moves = pv["months"][0]["moves"]
    assert pv["months"][0]["month"] == MONTH and moves
    assert storage.setting_changes() == []                                             # a preview saves nothing
    with pytest.raises(ValueError, match="Say why"):
        tolerances.save(changes, "Pat (pat1)", "  ")
    saved = tolerances.save(changes, "Pat (pat1)", "Agreed with the Head of Tech Risk")
    assert {s["path"] for s in saved} == set(changes)
    assert storage.load_month("scored", MONTH)["period"]["families"] == before["families"]   # nothing moves until an Update
    after = score_month.run(MONTH, "Tester")["period"]
    names = {f["id"]: f["name"] for f in storage.load_month("scored", MONTH)["families"]}
    for fid in red:                                                                     # 50 is far below every family
        assert after["families"][fid]["metrics"]["TE-02"]["status"] == "Amber"
        assert {"who": names[fid], "what": "Releases without a revert (7 days)", "before": "Red", "after": "Amber"} in moves \
            or any(m["who"] == names[fid] and m["before"] == "Red" and m["after"] == "Amber" for m in moves)
    for m in moves:                                                                     # every listed TRUST move happened
        if m["what"] == "TRUST" and m["who"] != "Firm":
            fid = next(k for k, v in names.items() if v == m["who"])
            assert str(before["families"][fid]["trust"]) == m["before"] and str(after["families"][fid]["trust"]) == m["after"]
    assert after["caps"]["red_block_trust"] == 60
    assert after["thresholds"]["TE-02"]["red"] == 50 and "Pat (pat1)" in after["thresholds"]["TE-02"]["reason"]
    assert tolerances.preview(changes)["changes"] == []                                 # now in use: nothing left to change


def test_the_audit_trail_keeps_every_change(seeded):
    sha = storage.settings_sha256()
    tolerances.save({"caps.red_metric_block": 70}, "Pat", "First")
    tolerances.save({"caps.red_metric_block": 75, "metrics.UN-01.amber_band_min": 1}, "Rita", "Second")
    h = tolerances.history()
    assert [(c["by"], c["path"], c["before"], c["after"], c["reason"]) for c in h if c["path"].startswith("caps")] == [
        ("Rita", "caps.red_metric_block", 70, 75, "Second"), ("Pat", "caps.red_metric_block", 79, 70, "First")]
    assert all(c["at"] and c["label"] for c in h) and len(h) == 3
    assert score_month.thresholds_config()["caps"]["red_metric_block"] == 75
    assert storage.settings_sha256() != sha                                             # the lock's seal sees the change
    tolerances.save({"metrics.UN-01.amber_band_min": ""}, "Rita", "Back to the general band")
    assert "amber_band_min" not in score_month.thresholds_config()["metrics"]["UN-01"]


def test_switching_a_metric_to_a_fixed_threshold_and_back(seeded):
    tolerances.save({"metrics.TE-01.basis": "Policy", "metrics.TE-01.green": 90, "metrics.TE-01.red": 70}, "Pat", "Fixed")
    t = score_month.run(MONTH, "Tester")["period"]["thresholds"]["TE-01"]
    assert (t["basis"], t["green"], t["red"]) == ("Policy", 90, 70) and "Set by Pat" in t["reason"]
    tolerances.save({"metrics.TE-01.basis": "Prevailing median"}, "Pat", "Back")
    assert score_month.run(MONTH, "Tester")["period"]["thresholds"]["TE-01"]["basis"] != "Policy"


def test_a_locked_month_is_listed_and_never_previewed(seeded):
    storage.set_month_status(MONTH, "locked", "Pat", "2026-11-15T00:00:00+00:00", {})
    pv = tolerances.preview({"metrics.TE-02.red": 50})
    assert pv["months"] == [] and pv["locked"] == ["October 2026"]


def test_rules_coverage_and_switches_are_settings_too(seeded):
    """Owner, 15 Nov 2026: not only caps and thresholds. Every scoring setting in the file is changed on the site."""
    v = tolerances.fields()["values"]
    assert v["automatic_red_rules"] is False and v["switched_on.TR-02"] is True and v["low_confidence_below_items.UN-02"] == 3
    assert "switched_on.TE-01" not in v                                    # only the metrics that can be switched
    for changes, words in (({"automatic_red_rules": "maybe"}, "choose On or Off"), ({"switched_on.TE-01": False}, "isn't a setting"),
                           ({"coverage.block_min_share": 2}, "from 0 to 1"), ({"low_confidence_below_items.UN-02": 1.5}, "whole number")):
        with pytest.raises(ValueError, match=words):
            tolerances.check(changes)
    pv = tolerances.preview({"switched_on.TR-02": "false", "automatic_red_rules": "true"})
    assert {c["label"] for c in pv["changes"]} == {"Repo good-hygiene rate: scored", "Automatic Red rules"}
    assert any(m["what"] == "Repo good-hygiene rate" for m in pv["months"][0]["moves"])       # it stops being scored
    tolerances.save({"switched_on.TR-02": "false", "automatic_red_rules": "true", "firm_tolerance": 80,
                     "coverage.trust_min_blocks": 3}, "Pat", "Trying it")
    cfg = score_month.thresholds_config()
    assert "TR-02" not in cfg["switched_on"] and set(cfg["switched_on"]) == {"TR-01", "RE-01", "RE-03"}
    assert cfg["automatic_red_rules"] is True and cfg["firm_tolerance"] == 80 and cfg["coverage"]["trust_min_blocks"] == 3
    p = score_month.run(MONTH, "Tester")["period"]
    assert all(f["metrics"]["TR-02"]["status"] == "DNR" for f in p["families"].values())
    tolerances.save({"switched_on.TR-02": True, "firm_tolerance": ""}, "Pat", "Back")
    cfg = score_month.thresholds_config()
    assert "TR-02" in cfg["switched_on"] and cfg.get("firm_tolerance") is None


def test_the_audit_trail_is_kept_24_months_but_never_loses_the_value_in_use(seeded, monkeypatch):
    """Owner, 15 Nov 2026: cut the trail after 24 months, like everything else. The newest row of a setting
    is the value in use, so it always stays."""
    import datetime
    from trust import retention
    times = iter(["2024-01-10T00:00:00+00:00", "2024-02-10T00:00:00+00:00", "2026-11-01T00:00:00+00:00"])
    monkeypatch.setattr(storage, "_now", lambda: next(times, "2026-11-15T00:00:00+00:00"))
    tolerances.save({"caps.red_metric_block": 70}, "Pat", "old, replaced later")
    tolerances.save({"caps.red_block_trust": 60}, "Pat", "old, still in use")
    tolerances.save({"caps.red_metric_block": 75}, "Pat", "recent")
    today = datetime.date(2026, 11, 15)
    assert len(retention.plan(today)["setting_changes"]) == 1
    retention.run(write=False, today=today, out=lambda *_: None)
    assert len(storage.setting_changes()) == 3                                         # a dry run removes nothing
    retention.run(write=True, today=today, out=lambda *_: None)
    assert [(c["path"], c["after"]) for c in storage.setting_changes()] == [("caps.red_block_trust", 60), ("caps.red_metric_block", 75)]
    cfg = score_month.thresholds_config()["caps"]
    assert (cfg["red_block_trust"], cfg["red_metric_block"]) == (60, 75)


def test_compare_shows_each_metric_judged_both_ways_and_changes_nothing(seeded):
    """Owner, 15 Nov 2026: compare the prevailing median with the fixed threshold before deciding."""
    before = storage.load_month("scored", MONTH)
    c = tolerances.compare(MONTH)
    assert c["label"] == "October 2026" and tolerances.compare("2026-07") is None
    by = {m["id"]: m for m in c["metrics"]}
    te02, te01 = by["TE-02"], by["TE-01"]
    assert te02["basis"] == "Policy" and (te02["by_fixed"]["green"], te02["by_fixed"]["red"]) == (95, 90)
    assert te02["by_median"]["green"] is not None and te02["by_median"]["green"] != 95        # the median's own value
    assert te01["basis"] == "Prevailing median" and te01["by_fixed"] is None
    for m in c["metrics"]:
        assert m["lowest"] <= m["middle"] <= m["highest"] and m["families"] >= 1
        assert sum(m["by_median"]["counts"].values()) == m["by_median"]["scored"] <= m["families"]
    # what "as it is now" says matches the scored month exactly
    red_now = sum(1 for f in before["period"]["families"].values() if f["metrics"]["TE-02"]["status"] == "Red")
    assert te02["by_fixed"]["counts"]["Red"] == red_now
    assert te02["smallest_count"] <= te02["largest_count"] and by["UN-02"]["min_items"] == 3 and by["UN-02"]["too_few"] >= 0
    assert "RE-02" not in by                                                              # not measured: not listed
    assert storage.load_month("scored", MONTH) == before and storage.setting_changes() == []


def test_a_large_team_is_flagged_on_the_firm_figure_and_no_score_moves(seeded):
    """Owner, 15 Nov 2026: a large team can skew the firm's figure. A note only, set for every metric or one."""
    before = storage.load_month("scored", MONTH)["period"]
    f = tolerances.fields()
    assert {g["path"]: g["value"] for g in f["general"]}["large_share_flag_default"] == 50
    assert next(m for m in f["metrics"] if m["id"] == "TE-02")["large_share"] is None
    with pytest.raises(ValueError):
        tolerances.check({"large_share_flag_percent.TE-02": 0})
    with pytest.raises(ValueError):
        tolerances.check({"large_share_flag_default": 101})
    # a share of 1% flags every metric the firm has items for; the family named holds the most items
    low = score_month.score_month(storage.load_month("mapped", MONTH), tolerances.effective(
        score_month.thresholds_config(), {"large_share_flag_default": 1}))["period"]
    flag = low["large_share"]["TE-02"]
    sizes = {fid: fr["metrics"]["TE-02"]["denominator"] for fid, fr in low["families"].items()
             if fr["metrics"]["TE-02"].get("denominator")}
    assert flag["family"] == max(sizes, key=lambda k: (sizes[k], k)) and flag["limit"] == 1
    assert flag["percent"] == score_month.r1(100 * sizes[flag["family"]] / low["firm"]["TE-02"]["denominator"])
    # one metric can have its own share; an empty default means no note anywhere else
    one = score_month.score_month(storage.load_month("mapped", MONTH), tolerances.effective(
        score_month.thresholds_config(), {"large_share_flag_default": None, "large_share_flag_percent.TE-02": 1}))["period"]
    assert list(one["large_share"]) == ["TE-02"]
    # nothing is scored differently
    for fid, fr in before["families"].items():
        assert low["families"][fid]["trust"] == fr["trust"]
        assert {m: x["status"] for m, x in low["families"][fid]["metrics"].items()} == {m: x["status"] for m, x in fr["metrics"].items()}
    assert all(m["moves"] == [] for m in tolerances.preview({"large_share_flag_default": 1})["months"])
    tolerances.save({"large_share_flag_percent.TE-02": 40}, "tr.demo", "Releases are concentrated in one family")
    assert next(m for m in tolerances.fields()["metrics"] if m["id"] == "TE-02")["large_share"] == 40
