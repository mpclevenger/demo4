"""The levels command and the map note that say when l3_level doesn't sit just below the CTO."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from trust import linking, mapping, score_month


def people(cto_level):
    rows = [{"sam_account": "cto", "manager_sam": None, "reporting_level": cto_level, "email": "cto@x"}]
    for i in range(3):
        rows.append({"sam_account": f"l3_{i}", "manager_sam": "cto", "reporting_level": cto_level + 1, "email": f"l3{i}@x"})
        rows.append({"sam_account": f"p_{i}", "manager_sam": f"l3_{i}", "reporting_level": cto_level + 2, "email": f"p{i}@x"})
    return rows


def test_note_when_level_is_off():
    notes = []
    feeds = {"hr": {"people": people(4)}}
    mapping._place_people_and_families(feeds, {"hr_root_sam_account": "cto", "l3_level": 3}, notes)
    assert any("CTO is at HR reporting level 4" in n for n in notes)


def test_no_note_when_level_fits():
    notes = []
    feeds = {"hr": {"people": people(2)}}
    _p, rows, _s, _e = mapping._place_people_and_families(feeds, {"hr_root_sam_account": "cto", "l3_level": 3}, notes)
    assert not any("CTO is at HR reporting level" in n for n in notes)
    assert len(rows) == 3


def test_levels_report(monkeypatch):
    monkeypatch.setattr(mapping.storage, "load_month", lambda kind, month: {
        "feeds": {"hr": {"people": people(2)}}, "settings_used": {"hr_root_sam_account": "cto", "l3_level": 3}})
    text = "\n".join(mapping.levels_report("2026-10"))
    assert "own HR level (Organization Level from Top): 2" in text
    assert "3 L3 teams, 6 of 7 people placed" in text


def test_why_not_scored_counts_teams():
    period = {"families": {"a": {"metrics": {"UN-01": {"value": 50, "status": "N/A"}}}},
              "firm": {"UN-01": {"value": 50}}, "thresholds": {}, "unattributed_pct": {}}
    text = "\n".join(score_month.why_not_scored(period))
    assert "Only 1 L3 team in total" in text
    assert "UN-01: 1 of 5 L3 teams needed have a result" in text
