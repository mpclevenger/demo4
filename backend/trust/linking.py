"""Join files at scoring time (DEVELOPER_GUIDE.md rule 0: uploads never join; scoring joins whatever is loaded).

Postmortems and action items (doc 15): only action items have an owner, so the chain is
    assignee email -> HR -> team -> family   (the action's family)
    action -> incident_id                    (each incident takes the families of its actions)
An incident with no actions falls back to its user_stakeholders (SAM_ACCOUNT -> HR), then to
UNATTRIBUTED, shown on Firm position as "Not yet mapped" (D-73). Nothing is dropped.
"""
import re
from collections import Counter, defaultdict

UNATTRIBUTED = "UNATTRIBUTED"


def _lookup(table, key):
    """Accept a dict or a function for the HR lookups; a missing table means 'not loaded yet'."""
    if table is None or key is None:
        return None
    return table(key) if callable(table) else table.get(key)


def link_actions_to_incidents(actions, postmortems=None, family_of_email=None, family_of_sam=None):
    """Place every action and incident with a family, from whatever is loaded.

    actions:        rows from intake.actions.read (required; this is the file with people on it)
    postmortems:    rows from intake.postmortems.read, or None if that file isn't loaded
    family_of_email: email -> family_id (built from HR + the team-to-family mapping), or None
    family_of_sam:   SAM_ACCOUNT -> family_id, for the incident fallback, or None

    Returns dict(actions=[...], incidents={incident_id: {...}}, notes=[...]).
    """
    notes = []
    pm_by_incident = defaultdict(list)
    for p in postmortems or []:
        pm_by_incident[p["incident_id"]].append(p)

    if postmortems is None:
        notes.append("postmortem file not loaded: every action is counted (scope can't be checked yet)")
    if family_of_email is None:
        notes.append("HR not loaded: every action shows as Not yet mapped until it is")

    placed, not_in_pm = [], []
    for a in actions:
        fam = _lookup(family_of_email, a.get("assignee_email")) or UNATTRIBUTED
        inc = a.get("incident_id")
        if postmortems is None:
            in_scope, why = True, "postmortem file not loaded"
        elif inc not in pm_by_incident:
            # The postmortem file lists the true critical incidents, so an action whose incident
            # isn't there is out of scope (this replaces the owner's hand filtering), and listed.
            in_scope, why = False, "incident not in the postmortem file"
            not_in_pm.append(a["item_ref"])
        elif not any(p["in_scope"] for p in pm_by_incident[inc]):
            in_scope, why = False, "incident is DEFCON 0"
        else:
            in_scope, why = True, "in scope"
        # The incident's rating (Critical / SWE / None = not rated), when the postmortem file is loaded.
        pms_a = pm_by_incident.get(inc, [])
        rating = _most_severe_class(pms_a)
        placed.append({**a, "family_id": fam, "in_scope": in_scope, "scope_reason": why,
                       "incident_rated": (rating is not None) if pms_a else None, "incident_class": rating,
                       "placed_by": "assignee email" if fam != UNATTRIBUTED else None})
    if not_in_pm:
        notes.append(f"{len(not_in_pm)} {'action belongs' if len(not_in_pm) == 1 else 'actions belong'} to an incident "
                     f"not in the postmortem file (left out of UN-02, listed): {', '.join(not_in_pm[:10])}")

    # Each incident takes the families of all its actions (an incident can belong to several families).
    fams_by_incident = defaultdict(set)
    for a in placed:
        if a.get("incident_id"):
            fams_by_incident[a["incident_id"]].add(a["family_id"])

    incidents = {}
    actions_of = Counter(a.get("incident_id") for a in placed)      # counted once, not per incident (speed)
    for inc in sorted(set(pm_by_incident) | set(fams_by_incident)):     # sorted: the same order on every run
        fams = fams_by_incident.get(inc, set()) - {UNATTRIBUTED}
        via = "action assignees" if fams else None
        if not fams:
            # No placed actions: fall back to the people named on the postmortem (SAM_ACCOUNTs).
            for p in pm_by_incident.get(inc, []):
                for sam in p.get("user_stakeholders", []):
                    f = _lookup(family_of_sam, sam)
                    if f:
                        fams.add(f)
            via = "user_stakeholders" if fams else None
        pms = pm_by_incident.get(inc, [])
        incidents[inc] = {
            "incident_id": inc,
            "families": sorted(fams) or [UNATTRIBUTED],
            "placed_by": via,
            "in_postmortem_file": bool(pms),
            "in_scope": any(p["in_scope"] for p in pms) if pms else None,
            "postmortems": len(pms),
            # Critical or SWE (UN-01): the most severe class on any of the incident's postmortems.
            "risk_class": _most_severe_class(pms),
            # When the incident ended: the primary postmortem's end_datetime, else the earliest one (UN-01 month).
            "end_datetime": (next((p.get("end_datetime") for p in pms if p.get("is_primary") and p.get("end_datetime")), None)
                             or min((p["end_datetime"] for p in pms if p.get("end_datetime")), default=None)),
            "actions": actions_of[inc],
        }
    unplaced = sorted(i for i, v in incidents.items() if v["families"] == [UNATTRIBUTED])
    incident_notes = []     # about the postmortems file, so they are shown on that file, not on Action items
    if unplaced and family_of_email is not None:
        incident_notes.append(f"{len(unplaced)} {'incident' if len(unplaced) == 1 else 'incidents'} could not be placed with an L3 team "
                     f"(shown as Not yet mapped): {', '.join(unplaced[:10])}")
    return dict(actions=placed, incidents=incidents, notes=notes, incident_notes=incident_notes)


def _most_severe_class(postmortems):
    """SWE if any postmortem is rated SWE, else critical if any is rated critical, else None (not rated)."""
    classes = {p.get("risk_class") for p in postmortems}
    if "SWE" in classes:
        return "SWE"
    if "critical" in classes:
        return "critical"
    return None


def _place_along_manager_line(by_sam, group_of_lead):
    """Place each person with the group of the nearest lead above them, or themselves, walking up the manager line.
    group_of_lead is {lead SAM: group id}. Returns ({sam: group id}, [sams with no lead above them])."""
    group_of_sam, unplaced = {}, []
    for sam in by_sam:
        current, group, seen = sam, None, set()
        while current and current not in seen:
            seen.add(current)
            if current in group_of_lead:
                group = group_of_lead[current]
                break
            current = by_sam[current]["manager_sam"] if current in by_sam else None
        if group:
            group_of_sam[sam] = group
        else:
            unplaced.append(sam)
    return group_of_sam, unplaced


def _family_of_email(people, family_of_sam):
    """{work email: family id} for every placed person who has an email."""
    return {p["email"]: family_of_sam[p["sam_account"]] for p in people
            if p.get("email") and p["sam_account"] in family_of_sam}


def family_id(name):
    """A stable id from a team name: 'Order Routing & Risk' -> 'order-routing-risk'."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def l3_level(settings):
    v = (settings or {}).get("l3_level")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 3


def families_from_level(people, level=3):
    """Teams from HR alone (owner, 3 Nov 2026; the only way since 17 Nov 2026).

    Every person whose "Management reporting level from top" is `level` leads a team named after their
    Supervisory Organization (without the "(Manager Name)"), then their Department, then their own name,
    and everyone reporting up to them (directly or not) is rolled into it. People above that level,
    or with no such person above them, are Not yet mapped and listed.

    Returns dict(family_of_sam, family_of_email, families, notes), with `families` rows of
    (family_id, family, owner_emails, lead_sam, people), so scoring, the page and team-lead access read them.
    """
    from .intake.app_links import sup_org_name
    notes = []
    by_sam = {p["sam_account"]: p for p in people}
    leads = [p for p in people if p.get("reporting_level") == level]

    def team_name(lead):
        # The team is named after the lead's Supervisory Organization without "(Manager Name)";
        # if that is empty, the lead's Department; if that is empty too, the lead's name (owner, 17 Nov 2026).
        return sup_org_name(lead.get("sup_org")) or sup_org_name(lead.get("department")) or lead.get("worker") or lead["sam_account"]

    team_of_lead, rows, used = {}, [], set()
    for p in sorted(leads, key=lambda x: (team_name(x).lower(), x["sam_account"])):
        name = team_name(p)
        fid = family_id(name)
        if fid in used:                                   # two leads with the same name: keep them apart
            fid = f"{fid}-{family_id(p['sam_account'])}"
            name = f"{name} ({p['sam_account']})"
        used.add(fid)
        team_of_lead[p["sam_account"]] = fid
        rows.append({"family_id": fid, "family": name,
                     "owner_emails": [p["email"]] if p.get("email") else [], "lead_sam": p["sam_account"]})
    if not leads:
        notes.append(f"Nobody in the HR file is at level {level} from the top, so no teams can be made "
                     "(check the HR column 'Management reporting level from top' and the setting l3_level)")
    family_of_sam, unplaced = _place_along_manager_line(by_sam, team_of_lead)
    if unplaced:
        notes.append(f"{len(unplaced)} {'person isn\'t' if len(unplaced) == 1 else 'people aren\'t'} under a level-{level} lead "
                     f"(Not yet mapped): {', '.join(sorted(unplaced)[:15])}{' …' if len(unplaced) > 15 else ''}")
    family_of_email = _family_of_email(people, family_of_sam)
    counts = {}
    for f in family_of_sam.values():
        counts[f] = counts.get(f, 0) + 1
    families = [{**f, "people": counts.get(f["family_id"], 0)} for f in rows]
    return dict(family_of_sam=family_of_sam, family_of_email=family_of_email, families=families, notes=notes)


def who_table(people, l3=3):
    """{sam: who} for every kept person, for the drill-down (owner, 9 Nov 2026): name, SAM_ACCOUNT (their ID),
    work email, team, and the L4 and L3 managers on their HR manager chain (the people at reporting levels
    l3 + 1 and l3 from the top; a person at that level is their own). Above a level, that manager is blank."""
    by_sam = {p["sam_account"]: p for p in people}
    out = {}
    for sam, p in by_sam.items():
        found, cur, seen = {}, sam, set()
        while cur in by_sam and cur not in seen:
            seen.add(cur)
            lvl = by_sam[cur].get("reporting_level")
            if lvl in (l3, l3 + 1):
                found.setdefault(lvl, by_sam[cur])
            cur = by_sam[cur].get("manager_sam")
        l4, l3p = found.get(l3 + 1) or {}, found.get(l3) or {}
        out[sam] = {"name": p.get("worker") or sam, "sam": sam, "email": p.get("email") or "",
                    "l4": l4.get("worker") or "", "l4_email": l4.get("email") or "",
                    "l3": l3p.get("worker") or "", "l3_email": l3p.get("email") or ""}
    return out


def l4_teams(people, level=3):
    """The L4 teams (owner, 17 Nov 2026): {L4 leader's SAM_ACCOUNT: {"name", "l3_id", "members"}}.

    An L4 team is a person at HR reporting level `level` + 1 and everyone under them. Each person's L4 is found the
    way who_table finds it: the first person at that level on their manager chain, starting with themself.
    A person above that level (the L3 lead and up) is in no L4 team.

    name     the leader's Supervisory Organization without "(Manager Name)", else the leader's name
    l3_id    the team id of the L3 team the leader is placed with (their family_id from the mapping), or UNATTRIBUTED
    members  every SAM_ACCOUNT in the team, the leader included, sorted
    """
    from .intake.app_links import sup_org_name
    by_sam = {p["sam_account"]: p for p in people}
    l4_level = level + 1
    members_of = defaultdict(list)
    for sam in by_sam:
        current, seen = sam, set()
        while current in by_sam and current not in seen:
            seen.add(current)
            if by_sam[current].get("reporting_level") == l4_level:
                members_of[current].append(sam)
                break
            current = by_sam[current].get("manager_sam")
    teams = {}
    for leader_sam, member_sams in members_of.items():
        leader = by_sam[leader_sam]
        name = sup_org_name(leader.get("sup_org")) or leader.get("worker") or leader_sam
        teams[leader_sam] = {"name": name, "l3_id": leader.get("family_id") or UNATTRIBUTED,
                             "members": sorted(member_sams)}
    return teams


def who_of(table, sams=(), emails=(), sam_of_email=None):
    """The people behind one item, each once, in order: by SAM_ACCOUNT, or by work email through HR. A SAM not
    in HR still shows, as its SAM alone, so nobody silently disappears from the drill-down."""
    sam_of_email = sam_of_email or {}
    keys = [s.lower() for s in sams if s] + [sam_of_email.get((e or "").lower()) or ("@" + e.lower()) for e in emails if e]
    out, seen = [], set()
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        if k in table:
            out.append(table[k])
        elif k.startswith("@"):
            out.append({"name": "", "sam": "", "email": k[1:], "l4": "", "l4_email": "", "l3": "", "l3_email": ""})
        else:
            out.append({"name": "", "sam": k, "email": "", "l4": "", "l4_email": "", "l3": "", "l3_email": ""})
    return out
