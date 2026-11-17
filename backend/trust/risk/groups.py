"""The groups the Risk site assesses, and who belongs to each (owner, 17 Nov 2026).

A Risk group is an L4 team: one person at HR reporting level l3_level + 1, and everyone under them. Each L4 team fills
in its own assessment and signs it off. It belongs to an L3 team (the TRUST team its leader is placed with), and the
L3 team's page lists its L4 teams' results. The people are found by linking.l4_teams, the same function as the
TRUST L4 drill-down, so both sites cut the firm the same way.

    id       "<L3 team id>--<id made from the L4 team's name>" (stable and unique)
    name     the L4 leader's Supervisory Organization without "(Manager Name)", else the leader's name
    leads    the one L4 leader (a list of one SAM_ACCOUNT)
    l3_id    the L3 team's id (a TRUST team), and l3_name its name
    members  the L4 leader and everyone under them in HR

This file only READS the mapped month (the people, their managers and the teams TRUST placed them with); it never
places anybody itself. If TRUST holds no L4 teams yet, there are no groups, and the Risk site says so. The L3 lead is
in no L4 team: they may open their L4 teams (view) as the lead of the L3 team, and as a manager above, as before.
"""
from trust import access, linking, storage, things
from trust.intake.families import family_id as id_made_from

NO_TEAMS_YET = ("TRUST has no L4 teams yet, so there are none to answer for. The Risk site's teams are the L4 teams: they "
                "appear here once Tech Risk has loaded HR (with each person's reporting level) into TRUST.")
NOT_YET_MAPPED_ID = "not-yet-mapped"

_cache = {"key": None, "teams": [], "names": {}}


def hr_month():
    """The newest month that has been mapped (its people are the ones we know), or None before any."""
    mapped_months = storage.months("mapped")
    return mapped_months[-1] if mapped_months else None


# ---------------------------------------------------------------------------------------------------
# TRUST's teams, read from the mapped month
# ---------------------------------------------------------------------------------------------------

def teams_in(month):
    """The L4 teams for the month: [{"id", "name", "leads", "l3_id", "l3_name", "members"}], grouped by L3 team.
    [] when there is no month or no L4 team."""
    if month is None:
        return []
    _refresh_cache_for(month)
    return _cache["teams"]


def names_of_people(month):
    """{SAM_ACCOUNT: name} for everyone TRUST holds for the month. {} when there is no month."""
    if month is None:
        return {}
    _refresh_cache_for(month)
    return _cache["names"]


def _refresh_cache_for(month):
    """Read the teams and the people's names again when the month has been mapped again (or the store changed)."""
    run = storage.run_info("mapped", month) or {}
    key = (str(storage.store_dir()), storage.using_database(), month, run.get("at"))
    if _cache["key"] != key:
        names = {person["key"].lower(): person["name"] for person in storage.things(month, "person")}
        _cache.update(key=key, teams=_read_teams(month), names=names)


def _read_teams(month):
    """The L4 teams of the mapped month, grouped under their L3 team (L3 teams in TRUST's order, then by name)."""
    mapped = storage.load_month("mapped", month) or {}
    feeds = mapped.get("feeds") or {}
    mapping = feeds.get("hr_mapping") or {}
    people = (feeds.get("hr") or {}).get("people") or []
    l3_name_of = {family["family_id"]: family.get("family") or family["family_id"] for family in mapping.get("families") or []}
    shared = mapping.get("shared") or {}                 # {shared group id: [family ids]}
    for shared_id, family_ids in shared.items():
        l3_name_of[shared_id] = " and ".join(l3_name_of.get(family, family) for family in family_ids)
    l3_order = {family_id: position for position, family_id in enumerate(l3_name_of)}
    l4_teams = linking.l4_teams(people, linking.l3_level(mapped.get("settings_used")))

    found, used_ids = [], set()
    for leader_sam, team in l4_teams.items():
        l3_id = team["l3_id"]
        if l3_id == linking.UNATTRIBUTED:
            l3_id = NOT_YET_MAPPED_ID
        group_id = f"{l3_id}--{id_made_from(team['name'])}"
        if group_id in used_ids:                          # two L4 teams with the same name under one L3 team
            group_id = f"{group_id}-{id_made_from(leader_sam)}"
        used_ids.add(group_id)
        found.append({"id": group_id, "name": team["name"], "leads": [leader_sam.lower()],
                      "l3_id": l3_id, "l3_name": l3_name_of.get(l3_id) or "Not yet mapped",
                      "members": [sam.lower() for sam in team["members"]], "shared_with": [], "grouping": "l4"})
    found.sort(key=lambda group: (l3_order.get(group["l3_id"], len(l3_order)), group["l3_name"].lower(), group["name"].lower()))
    return found


def load():
    """Every group (every L4 team) the site has for the newest month. [] when TRUST holds no L4 teams yet."""
    return list(teams_in(hr_month()))


def in_l3_team(l3_id, month):
    """The L4 teams that belong to one L3 team, in order."""
    return [group for group in teams_in(month) if group["l3_id"] == l3_id]


def find(group_id):
    """The group with this id, or None when TRUST has no such L4 team (an old id, or one that was never there)."""
    return next((group for group in load() if group["id"] == group_id), None)


# ---------------------------------------------------------------------------------------------------
# Who is in a group, from the people TRUST already holds
# ---------------------------------------------------------------------------------------------------

def members(group, month):
    """The SAM_ACCOUNTs of everyone in the L4 team, sorted. [] when no month is mapped."""
    if month is None:
        return []
    return list(group["members"])


def lead_name(group, month):
    """The lead's name, or the leads' names joined with "and". None when the team has no lead we can find."""
    if month is None or not group["leads"]:
        return None
    name_of = names_of_people(month)
    return " and ".join(name_of.get(sam, sam) for sam in group["leads"])


def managers_above(sams, month):
    """Everyone above the people in sams on the HR reporting line, as SAM_ACCOUNTs."""
    if month is None:
        return set()
    manager_of = {link["from_key"].lower(): link["to_key"].lower()
                  for link in storage.thing_links(month) if link["relation"] == "reports_to"}
    above = set()
    for sam in sams:
        manager = manager_of.get(sam.lower())
        while manager and manager not in above:
            above.add(manager)
            manager = manager_of.get(manager)
    return above


def what_a_person_may_do(person, group, month):
    """{"view", "answer", "submit"} for one person and group.

    view    the roles that see everything (CTO and leadership, Tech Risk, auditors), the team's people, the
            managers above them, and the lead of the L3 team the group belongs to (read only)
    answer  Tech Risk, the team's people (the lead and everyone under them) and the managers above them
    submit  Tech Risk, the team's lead, and the managers above the team (delegates are Wanted)
    """
    if person["open"]:                                   # TRUST is running open: anyone can do everything
        return {"view": True, "answer": True, "submit": True}
    sams = set(members(group, month))
    above = managers_above(sams, month)
    in_group = person["sam"] in sams
    is_above = person["sam"] in above
    is_lead = person["sam"] in group["leads"]
    is_tech_risk = access.is_tech_risk(person)
    leads_the_l3_team = group["l3_id"] in person["lead_of"]
    return {"view": access.sees_all(person) or in_group or is_above or leads_the_l3_team,
            "answer": is_tech_risk or in_group or is_above,
            "submit": is_tech_risk or is_lead or is_above}
