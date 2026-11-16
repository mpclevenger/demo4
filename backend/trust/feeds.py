"""The files TRUST reads, in one place: each feed's reader, and the fields it needs from the file's columns.

Upload (store.py), the checks at upload (checks.py) and mapping (mapping.py) all need these. Keeping them here,
apart from all three, lets each of those import this file at the top without importing each other in a circle.
"""
from .intake import (actions, app_inventory, checkmarx, defects, dr_tests, families, hr, itdr, ntcc, owner_groups,
                     postmortems, repo_contributors, repos, tcc)

# Each feed with a reader. Feeds without one yet are recorded as "received, no reader yet".
READERS = {
    "hr": lambda raw, e, s: hr.read(raw, s.get("hr_root_sam_account", "")),
    "hr_mapping": lambda raw, e, s: families.read(raw),
    "cx_sast": lambda raw, e, s: checkmarx.read(raw, "SAST", e["uploaded_at"]),
    "cx_sca": lambda raw, e, s: checkmarx.read(raw, "SCA", e["uploaded_at"]),
    "tcc": lambda raw, e, s: tcc.read(raw),
    "ntcc": lambda raw, e, s: ntcc.read(raw),
    "postmortems": lambda raw, e, s: postmortems.read(raw),
    "actions": lambda raw, e, s: actions.read(raw),
    "itdr": lambda raw, e, s: itdr.read(raw),
    "dr_tests": lambda raw, e, s: dr_tests.read(raw),
    "repos": lambda raw, e, s: repos.read(raw),
    "repo_contributors": lambda raw, e, s: repo_contributors.read(raw),
    "defects": lambda raw, e, s: defects.read(raw),
    "app_inventory": lambda raw, e, s: app_inventory.read(raw, s),
    "app_owner_members": lambda raw, e, s: owner_groups.read(raw),
}

# Delimited files and the reader fields that decide which columns are kept.
TABLE_FIELDS = {"tcc": tcc.FIELDS, "ntcc": ntcc.FIELDS, "actions": actions.FIELDS,
                "postmortems": postmortems.FIELDS, "hr_mapping": families.FIELDS, "itdr": itdr.FIELDS,
                "dr_tests": dr_tests.FIELDS, "repos": repos.FIELDS, "repo_contributors": repo_contributors.FIELDS,
                "defects": defects.FIELDS, "app_inventory": app_inventory.FIELDS,
                "app_owner_members": owner_groups.FIELDS}
# Files whose header spans more than one row (ITDR: merged over rows 1 and 2, owner 3 Nov 2026).
HEADER_ROWS = {"itdr": itdr.HEADER_ROWS, "dr_tests": dr_tests.HEADER_ROWS}


def fields_needed(feed):
    """The reader fields a feed's file must give, or {} for a feed whose layout hasn't been given yet."""
    if feed in TABLE_FIELDS:
        return TABLE_FIELDS[feed]
    if feed == "hr":
        return hr.FIELDS
    if feed in ("cx_sast", "cx_sca"):
        return checkmarx.FIELDS
    return {}
