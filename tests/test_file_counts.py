"""Validation checks, Files table (owner, 17 Nov 2026): every received file shows its row count, and the share of
its rows not yet placed with an L3 team where the file places rows with teams."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, score_month, store  # noqa: E402
from test_dr_tests import workbook as dr_workbook  # noqa: E402
from test_itdr import workbook as itdr_workbook  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    return tmp_path


def test_every_received_file_has_its_row_count(tmp_store):
    for feed, name in (("hr", "hr_firmwide.csv"), ("tcc", "tcc_export.csv"), ("app_inventory", "app_inventory.csv")):
        store.upload(feed, "2026-10", (FIX / name).read_bytes(), name, "Tester")
    store.upload("itdr", "2026-10", itdr_workbook(), "itdr.xlsx", "Tester")
    store.upload("dr_tests", "2026-10", dr_workbook(), "dr.xlsx", "Tester")
    mapped = mapping.map_month("2026-10")
    counts = score_month.score_month(mapped)["period"]["file_counts"]
    assert set(counts) == {"hr", "tcc", "app_inventory", "itdr", "dr_tests"}
    assert counts["hr"]["rows"] == 6                                              # the people TRUST kept
    assert counts["app_inventory"]["rows"] == len(mapped["feeds"]["app_inventory"]["rows"])
    assert counts["itdr"]["rows"] == len(mapped["feeds"]["itdr"]["rows"])
    assert counts["dr_tests"]["rows"] == len(mapped["feeds"]["dr_tests"]["rows"]) == 5
    assert all(c["rows"] > 0 for c in counts.values())


def test_not_yet_mapped_share_is_filled_where_a_file_places_rows_with_teams(tmp_store):
    for feed, name in (("hr", "hr_firmwide.csv"),):
        store.upload(feed, "2026-10", (FIX / name).read_bytes(), name, "Tester")
    store.upload("itdr", "2026-10", itdr_workbook(), "itdr.xlsx", "Tester")
    mapped = mapping.map_month("2026-10")
    rows = mapped["feeds"]["itdr"]["rows"]
    not_placed = sum(1 for row in rows if row["family_id"] == "UNATTRIBUTED")
    counts = score_month.score_month(mapped)["period"]["file_counts"]
    assert counts["itdr"]["unattributed_pct"] == round(100 * not_placed / len(rows), 1)
    assert counts["hr"]["unattributed_pct"] == 16.7                                # 1 of 6 people (the CTO) is above the L3 teams
    store.upload("app_owner_members", "2026-10", b"owner_email,owner_kind,group_sam,member_sam,member_email,member_name,member_enabled,included,reason\nDL@x.com,group,DL,AB1,a@x.com,A B,True,Yes,\n", "m.csv", "Tester")
    counts = score_month.score_month(mapping.map_month("2026-10"))["period"]["file_counts"]
    assert counts["app_owner_members"]["rows"] == 1 and counts["app_owner_members"]["unattributed_pct"] is None   # a dash
