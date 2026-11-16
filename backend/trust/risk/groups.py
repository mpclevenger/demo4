"""The groups the Risk site assesses, and who belongs to each (owner, 16 Nov 2026).

A Risk group IS a TRUST team. The Risk site has no groups of its own: it uses the teams TRUST reports on, so both
sites break the firm down the same way.

    id       the TRUST team's id (the product family id, or in level-3 mode the id made from the lead's name)
    name     the TRUST team's name
    leads    the team's lead or leads, the way TRUST finds them: the people whose work email is one of the team's
             owners in the product family owners file (in level-3 mode, the level-3 person)
    members  the people TRUST placed with the team for the newest month it holds, including the people of a shared
             group (a lead of several families) that includes this team

Which teams there are, and who is in them, was decided when TRUST mapped the month (setting team_grouping in
config/settings.json: product_family or l3). This file only READS that result (the mapped month and its things);
it never works a team out again. If TRUST holds no teams yet, there are no groups, and the Risk site says so.

A team's lead is who signs its assessment off (signoff.py). Each team also says how TRUST grouped it ("grouping").
"""
from trust import access, storage, things

NO_TEAMS_YET = ("TRUST has no teams yet, so there are none to answer for. The Risk site uses TRUST's teams: they appear "
                "here once Tech Risk has loaded HR (and the product family owners file) into TRUST.")

_cache = {"key": None, "teams": [], "names": {}}


def hr_month():
    """The newest month that has been mapped (its people are the ones we know), or None before any."""
    mapped_months = storage.months("mapped")
    return mapped_months[-1] if mapped_months else None


# ---------------------------------------------------------------------------------------------------
# TRUST's teams, read from the mapped month
# ---------------------------------------------------------------------------------------------------

def teams_in(month):
    """TRUST's teams for the month: [{"id", "name", "leads": [SAM_ACCOUNT, ...], "shared_with": [group ids]}].
    The order is TRUST's own (the order of the families the mapping kept). [] when there is no month or no team."""
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
    mapped = storage.load_month("mapped", month) or {}
    feeds = mapped.get("feeds") or {}
    mapping = feeds.get("hr_mapping") or {}
    people = (feeds.get("hr") or {}).get("people") or []
    sam_of_email = {(person.get("email") or "").lower(): person["sam_account"].lower()
                    for person in people if person.get("email") and person.get("sam_account")}
    shared = mapping.get("shared") or {}                 # {shared group id: [family ids]}
    grouping = mapped.get("team_grouping") or "product_family"
    found = []
    for family in mapping.get("families") or []:
        family_id = family["family_id"]
        leads = []
        for email in family.get("owner_emails") or []:
            sam = sam_of_email.get(email.lower())
            if sam and sam not in leads:
                leads.append(sam)
        lead_sam = (family.get("lead_sam") or "").lower()
        if lead_sam and lead_sam not in leads:
            leads.append(lead_sam)
        shared_with = [group_id for group_id, family_ids in shared.items() if family_id in family_ids]
        found.append({"id": family_id, "name": family.get("family") or family_id, "leads": leads,
                      "shared_with": shared_with, "grouping": grouping})
    return found


def load():
    """Every group (every TRUST team) the site has for the newest month. [] when TRUST holds no teams yet."""
    return list(teams_in(hr_month()))


def find(group_id):
    """The group with this id, or None when TRUST has no such team."""
    return next((group for group in load() if group["id"] == group_id), None)


# ---------------------------------------------------------------------------------------------------
# Who is in a group, from the people TRUST already holds
# ---------------------------------------------------------------------------------------------------

def members(group, month):
    """The SAM_ACCOUNTs of everyone in the team, sorted. [] when nobody is placed or no month is mapped."""
    if month is None:
        return []
    sams = set(things.members(month, "family:" + group["id"]))
    for shared_id in group.get("shared_with") or []:
        sams.update(things.members(month, "family:" + shared_id))
    return sorted(sams)


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

    view    the roles that see everything (CTO and leadership, Tech Risk, auditors), the team's people, and
            the managers above them
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
    return {"view": access.sees_all(person) or in_group or is_above,
            "answer": is_tech_risk or in_group or is_above,
            "submit": is_tech_risk or is_lead or is_above}
