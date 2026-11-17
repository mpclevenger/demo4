"""Step 2, MAP: read the stored files for a month and place their rows with people and families.

Re-run it as often as you like: after fixing a column name in config/column_maps.json, after HR or
the team-to-family mapping arrives, after changing config/settings.json. It reads the files kept
by step 1 (backend/trust/store.py), so nothing is ever uploaded twice. It never refuses: a file
that can't be read, a missing column or an unplaced row all become plain notes.

Output: store/mapped/<YYYY-MM>.json, which step 3 (scoring) reads.
"""
from collections import defaultdict

from . import config, feeds as feed_files, linking, lost, storage, store, things
from .intake import app_links, defects, dr_tests, itdr, repos

# The (feed, column) pairs that name the person a row belongs to: the author, the assignee or the repo owner.
PERSON_KEYS = (("tcc", "author_email"), ("ntcc", "author_email"), ("actions", "assignee_email"),
               ("repos", "owner_email"))
INCIDENT_IDS_LISTED = 10     # change ids named in a note before it stops listing


def _read_files(month, settings):
    """Read every feed's newest kept file with its reader. A file that can't be read becomes a note, never a failure."""
    uploads = store.latest(month)
    feeds = {}
    for feed in store.FEEDS:
        if feed not in uploads:
            feeds[feed] = {"status": "not received"}
            continue
        entry, raw = uploads[feed]
        base = {"status": "mapped", "file": entry["original_name"], "sha256": entry["sha256"],
                "original_sha256": entry.get("original_sha256"),
                "uploaded_at": entry["uploaded_at"], "uploaded_by": entry["uploaded_by"]}
        reader = feed_files.READERS.get(feed)
        if reader is None:
            feeds[feed] = {**base, "status": "received, no reader yet",
                           "notes": ["This feed's layout hasn't been given yet; the file is kept and will be mapped once it has."]}
            continue
        try:
            result = reader(raw, entry, settings)
        except ValueError as err:              # the file can't be read at all: say so, carry on with the rest
            feeds[feed] = {**base, "status": "could not be read", "notes": [str(err)]}
            continue
        feeds[feed] = {**base, **result}
    return feeds


def _retired_notes(month):
    """A file kept in this month for a retired feed is left alone: it stays in the month record, nothing reads it."""
    return [f"A '{feed}' file kept for this month is no longer used. {why}"
            for feed, why in store.RETIRED_FEEDS.items() if storage.register(month, feed)]


def _place_people_and_families(feeds, settings, notes):
    """Place people with product families (or level-3 teams). Returns (people, family_rows, family_of_sam,
    family_of_email, team_grouping); the two lookups are None when nobody could be placed."""
    people = feeds.get("hr", {}).get("people") or []
    family_rows = feeds.get("hr_mapping", {}).get("rows")
    family_of_sam = family_of_email = None
    # Which teams to report on (owner, 3 Nov 2026): product families from the owners file (the default),
    # or, with setting team_grouping = "l3", each level-3 person's org from HR, the owners file not used.
    team_grouping = linking.grouping(settings)
    if not people:
        notes.append("HR not loaded (or no people kept): everything shows as Not yet mapped.")
    if team_grouping == "l3":
        level = linking.l3_level(settings)
        notes.append(f"Teams this month: each level-{level} person in HR and everyone under them (setting team_grouping "
                     "= l3). The product family owners file isn't used while this is on.")
        if people:
            placed = linking.families_from_level(people, level)
            family_of_sam, family_of_email = placed["family_of_sam"], placed["family_of_email"]
            family_rows = placed["families"]
            feeds.setdefault("hr_mapping", {"feed": "hr_mapping", "status": "not used (level-3 teams)"})
            feeds["hr_mapping"]["families"] = placed["families"]
            feeds["hr_mapping"].setdefault("notes", []).extend(placed["notes"])
            for person in people:
                person["family_id"] = family_of_sam.get(person["sam_account"], linking.UNATTRIBUTED)
    elif family_rows is None:
        notes.append("Product family owners file not loaded: people are found in HR, but every row shows as "
                     "Not yet mapped until it is.")
    elif people:
        placed = linking.families_from_owners(people, family_rows)
        family_of_sam, family_of_email = placed["family_of_sam"], placed["family_of_email"]
        feeds["hr_mapping"]["families"] = placed["families"]
        feeds["hr_mapping"]["shared"] = placed["shared"]          # leads of several families (owner, 6 Nov 2026)
        feeds["hr_mapping"].setdefault("notes", []).extend(placed["notes"])
        for person in people:   # show each kept person's family on the HR result
            person["family_id"] = family_of_sam.get(person["sam_account"], linking.UNATTRIBUTED)
    return people, family_rows, family_of_sam, family_of_email, team_grouping


def _place_itdr_by_area(feeds, family_rows, people, family_of_sam, settings):
    """ITDR applications placed with families by Business Product Area: a family name, or an HR Department
    whose people are mostly in one family; close spellings accepted above area_match_min (owner, 3 Nov 2026).
    DR tests then take their application's family. Returns what the notes step needs later, or None."""
    if feeds.get("itdr", {}).get("rows") is None or family_rows is None:
        return None
    area_people = people if family_of_sam is not None else None
    minimum_match = itdr.area_match_min(settings)
    placed = itdr.match_families(feeds["itdr"]["rows"], family_rows, area_people, minimum_match)
    feeds["itdr"]["families"] = {k: placed[k] for k in ("placed", "not_placed", "exact", "fuzzy",
                                                        "by_family_name", "by_department")}
    return {"notes": placed["notes"], "family_rows": family_rows, "people": area_people, "minimum_match": minimum_match}


def _place_repos_and_issues(feeds, month, people, family_of_sam, settings):
    """Repos placed with families through their committer (owner, 3 Nov 2026) and the TR-02 hygiene figures;
    Checkmarx repos take the family of the GitHub repo they match; Jira issues go to the family of the person who
    closed them. Without HR or the owners file every one is Not yet mapped."""
    if feeds.get("repos", {}).get("rows") is not None:
        placed_repos = repos.place_and_score(feeds["repos"]["rows"], month, people, family_of_sam or {}, settings)
        feeds["repos"]["hygiene"] = {k: v for k, v in placed_repos.items() if k != "notes"}
        feeds["repos"].setdefault("notes", []).extend(placed_repos["notes"])
        # Checkmarx repos take the family of the GitHub repo they match (owner, 4 Nov 2026), so SE-01 / SE-02
        # can reach families. Without the GitHub file for the month they stay Not yet mapped.
        for cx in ("cx_sast", "cx_sca"):
            if feeds.get(cx, {}).get("rows") is not None:
                matched = repos.match_checkmarx(feeds[cx]["rows"], feeds["repos"]["rows"], repos.checkmarx_match_min(settings))
                feeds[cx]["repo_match"] = {k: v for k, v in matched.items() if k != "notes"}
                feeds[cx].setdefault("notes", []).extend(matched["notes"])

    # Jira issues placed with the family of the person who closed them (owner, 3 Nov 2026), and the month's
    # defect and delivery figures (TE-03 wanted, not scored yet).
    if feeds.get("defects", {}).get("rows") is not None:
        placed_jira = defects.place_and_measure(feeds["defects"]["rows"], month, people, family_of_sam or {})
        feeds["defects"]["figures"] = {k: v for k, v in placed_jira.items() if k != "notes"}
        feeds["defects"].setdefault("notes", []).extend(placed_jira["notes"])


def _link_app_inventory(feeds, people, family_of_sam, settings):
    """App inventory (owner, 6 Nov 2026): family from the org (golden source), else its owners' HR family; owners
    through HR, then the AD owner groups file; linked to ITDR by name and to GitHub repos by service repo.
    Not scored: it gives the drill-down its apps and owners. Runs after Checkmarx is matched to GitHub repos."""
    if feeds.get("app_inventory", {}).get("rows") is None:
        return
    linked = app_links.link(
        feeds["app_inventory"]["rows"], people if family_of_sam is not None else [],
        feeds.get("app_owner_members") if "members" in (feeds.get("app_owner_members") or {}) else None,
        (feeds.get("itdr") or {}).get("rows"),
        (feeds.get("repos") or {}).get("rows"),
        [(feeds.get(cx) or {}).get("rows") for cx in ("cx_sast", "cx_sca")], settings)
    feeds["app_inventory"]["placed"] = {k: linked[k] for k in ("summary", "by_family")}
    feeds["app_inventory"].setdefault("notes", []).extend(linked["notes"])
    if linked["itdr_notes"]:
        feeds["itdr"].setdefault("notes", []).extend(linked["itdr_notes"])


def _note_itdr_areas(feeds, itdr_area):
    """Business Product Area notes, written only now (owner, 6 Nov 2026): an application the app inventory placed
    doesn't need an area, so the notes cover only the applications still to be placed by their area.
    The ITDR notes have their own name, so the month's own notes (above) are never overwritten."""
    if itdr_area is None:
        return
    area_notes = itdr_area["notes"]
    rows = feeds["itdr"]["rows"]
    placed_by_inventory = [r for r in rows if (r.get("family_match") or {}).get("how") == "app inventory"]
    if placed_by_inventory:
        rest = [dict(r) for r in rows if (r.get("family_match") or {}).get("how") != "app inventory"]
        if rest:
            area_notes = itdr.match_families(rest, itdr_area["family_rows"], itdr_area["people"],
                                             itdr_area["minimum_match"])["notes"]
        else:
            area_notes = []
        placed = sum(1 for r in rows if r.get("family_id"))
        feeds["itdr"]["families"].update(placed=placed, not_placed=len(rows) - placed, by_inventory=len(placed_by_inventory))
        area_notes = [f"For information: {len(placed_by_inventory)} of {len(rows)} ITDR applications were placed by the app inventory; "
                      f"{placed - len(placed_by_inventory)} by Business Product Area; {len(rows) - placed} not placed"] + area_notes
    feeds["itdr"].setdefault("notes", []).extend(area_notes)


def _link_dr_tests(feeds):
    """DR tests linked to ITDR applications by name, when both files are loaded (owner, 3 Nov 2026)."""
    if feeds.get("dr_tests", {}).get("rows") is None or feeds.get("itdr", {}).get("rows") is None:
        return
    linked = dr_tests.match_applications(feeds["dr_tests"]["rows"], feeds["itdr"]["rows"])
    feeds["dr_tests"]["linked_to_applications"] = {k: linked[k] for k in ("matched", "not_matched", "tier_differs")}
    feeds["dr_tests"].setdefault("notes", []).extend(linked["notes"])


def _link_actions_and_incidents(feeds, family_of_email, family_of_sam, email_to_sam):
    """Actions and postmortem incidents placed with families, and each action's assignee checked against HR."""
    action_rows = feeds.get("actions", {}).get("rows")
    postmortem_rows = feeds.get("postmortems", {}).get("rows")
    if postmortem_rows is not None and action_rows is None:
        # Postmortems alone: incidents are placed through user_stakeholders only (UN-01).
        linked = linking.link_actions_to_incidents([], postmortem_rows, family_of_email, family_of_sam)
        feeds["postmortems"]["incidents"] = linked["incidents"]
        feeds["postmortems"].setdefault("notes", []).extend(linked["incident_notes"])
    if action_rows is not None:
        linked = linking.link_actions_to_incidents(action_rows, postmortem_rows, family_of_email, family_of_sam)
        if postmortem_rows is not None:
            feeds["postmortems"]["incidents"] = linked["incidents"]
            feeds["postmortems"].setdefault("notes", []).extend(linked["incident_notes"])
        # Also record whether each assignee was found in HR at all, so Tech Risk can see who is missing.
        for action in linked["actions"]:
            action["assignee_in_hr"] = action.get("assignee_email") in email_to_sam
        feeds["actions"]["rows"] = linked["actions"]
        feeds["actions"]["incidents"] = linked["incidents"]
        feeds["actions"].setdefault("notes", []).extend(linked["notes"])


def _note_changes_in_both_files(feeds):
    """Cross-file check (Q-NTCC-06): a change in both TCC and Non-TCC is counted once, as TCC."""
    tcc_ids = {x["ticket_id"] for x in feeds.get("tcc", {}).get("rows") or []}
    ntcc_rows = feeds.get("ntcc", {}).get("rows")
    if ntcc_rows is None or not tcc_ids:
        return
    in_both = [x["rpd_id"] for x in ntcc_rows if x["rpd_id"] in tcc_ids]
    for x in ntcc_rows:
        x["also_in_tcc"] = x["rpd_id"] in tcc_ids
    if in_both:
        feeds["ntcc"].setdefault("notes", []).append(
            f"{len(in_both)} {'change is' if len(in_both) == 1 else 'changes are'} in both TCC and Non-TCC; counted once, "
            f"as TCC: {', '.join(in_both[:INCIDENT_IDS_LISTED])}")


def _place_rows_with_people(feeds, people, family_of_email, settings, notes):
    """Every row that names a person gets that person's family (or UNATTRIBUTED), so scoring only counts. Then the
    person and their team (HR supervisory organization), for the item detail families drill into."""
    for feed in ("tcc", "ntcc"):
        for x in feeds.get(feed, {}).get("rows") or []:
            x["family_id"] = (family_of_email or {}).get(x.get("author_email")) or linking.UNATTRIBUTED
    # A person's sub-team within the family: the HR column named by the setting subteam_hr_column
    # (owner, 3 Nov 2026: Department by default; Supervisory Organization also works).
    column = (settings.get("subteam_hr_column") or "Department").strip()
    field = {"department": "department", "supervisory organization": "sup_org"}.get(column.lower())
    if field is None:
        notes.append(f"subteam_hr_column '{column}' isn't one TRUST keeps (Department or Supervisory Organization); "
                     "using Department.")
        field = "department"
    who = {p["email"]: (p.get("worker"), p.get(field), p.get(field)) for p in people if p.get("email")}
    for feed, key in PERSON_KEYS:
        for x in feeds.get(feed, {}).get("rows") or []:
            x["person"], x["team"], x["team_key"] = who.get(x.get(key), (None, None, None))


def _add_who(feeds, people, email_to_sam, settings):
    """Who each item belongs to, for the drill-down (owner, 9 Nov 2026): the person's name, SAM_ACCOUNT and work
    email, with their L4 and L3 managers from the HR manager chain. Changes: the author. Actions: the assignee.
    Repos: the repo owner. Checkmarx: the matched GitHub repo's owner, else the app owners. ITDR applications:
    the app owners. Incidents: the assignees of the incident's actions in each family."""
    who_table = linking.who_table(people, linking.l3_level(settings))
    who_of = lambda sams=(), emails=(): linking.who_of(who_table, sams, emails, email_to_sam)
    for feed, key in PERSON_KEYS:
        for x in feeds.get(feed, {}).get("rows") or []:
            x["who"] = who_of(emails=[x.get(key)])
    repo_owner = {r["repo"]: r.get("owner_email") for r in feeds.get("repos", {}).get("rows") or []}
    for cx in ("cx_sast", "cx_sca"):
        for x in feeds.get(cx, {}).get("rows") or []:
            if repo_owner.get(x.get("gh_repo")):
                x["who"] = who_of(emails=[repo_owner.get(x.get("gh_repo"))])
            else:
                x["who"] = who_of(sams=x.get("app_owner_sams") or [])
    for x in feeds.get("itdr", {}).get("rows") or []:
        x["who"] = who_of(sams=x.get("app_owner_sams") or [])
    incidents = (feeds.get("postmortems") or {}).get("incidents")
    if incidents:
        assignees_by_incident = defaultdict(list)
        for a in feeds.get("actions", {}).get("rows") or []:
            if a.get("incident_id") and a.get("assignee_email"):
                assignees_by_incident[(a["incident_id"], a.get("family_id"))].append(a["assignee_email"])
        for incident_id, incident in incidents.items():
            incident["who_by_family"] = {family: who_of(emails=assignees_by_incident.get((incident_id, family), []))
                                         for family in incident.get("families") or []}


def map_month(month, by="command line"):
    """Map every stored file for a month. Returns the mapped result (also saved)."""
    store.check_month(month)
    settings = config.settings()
    notes = []
    feeds = _read_files(month, settings)
    retired_notes = _retired_notes(month)

    # Place rows with people and families, from whatever is loaded (DEVELOPER_GUIDE.md rule 0).
    people, family_rows, family_of_sam, family_of_email, team_grouping = _place_people_and_families(feeds, settings, notes)
    email_to_sam = {p["email"]: p["sam_account"] for p in people if p.get("email")}

    itdr_area = _place_itdr_by_area(feeds, family_rows, people, family_of_sam, settings)
    _place_repos_and_issues(feeds, month, people, family_of_sam, settings)
    _link_app_inventory(feeds, people, family_of_sam, settings)
    _note_itdr_areas(feeds, itdr_area)

    # The AD members aren't saved with the mapped month: they can be hundreds of thousands of rows, and each app
    # already carries its owners (6 Nov 2026: the web process ran out of memory).
    for k in ("members", "kinds"):
        (feeds.get("app_owner_members") or {}).pop(k, None)

    _link_dr_tests(feeds)
    _link_actions_and_incidents(feeds, family_of_email, family_of_sam, email_to_sam)
    _note_changes_in_both_files(feeds)
    _place_rows_with_people(feeds, people, family_of_email, settings, notes)

    # Lost and Found (owner, 9 Nov 2026): approved claims place items no source file placed. A claim never
    # overrides a file, and carries over to every month mapped after it is approved.
    claims_used, claim_note = lost.apply_claims(feeds, storage.claims())
    if claim_note:
        notes.append(claim_note)

    _add_who(feeds, people, email_to_sam, settings)

    out = {"month": month, "settings_used": settings, "team_grouping": team_grouping, "feeds": feeds,
           "notes": notes + retired_notes, "claims_used": claims_used,
           "received": sorted(f for f, v in feeds.items() if v["status"] != "not received")}
    storage.save_month("mapped", month, out, by)
    things.save(out)          # the month's people, teams, applications and repositories, and how they connect
    storage.log("map", by, month, f"{len(out['received'])} files read")
    return out
