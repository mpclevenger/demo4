"""The things we measure and how they connect (owner, 15 Nov 2026).

The first layer of the shared core that the scorecard and the risk assessment both read. After a month is
mapped, this module lists the month's people, teams, applications and repositories (things), and how they
connect (links): who reports to whom, which teams a person is in, who owns a repository, which application
it serves, which product family an application is placed with. Each link says how it was made.

Nothing here decides anything new: every thing and link is read from the mapped month, exactly as mapping
placed it. Later layers (records, metric values) point at these rows instead of matching names again, and
any grouping (product family, department, L3, L4) is a roll-up of the same links.
"""
from . import linking, storage

UNPLACED = (None, "", "UNATTRIBUTED")


def _key(text):
    return str(text).strip()


def build(mapped):
    """(things, links) for a mapped month. A thing is (kind, key, name, details); a link is
    (from_kind, from_key, relation, to_kind, to_key, how, score)."""
    feeds = mapped.get("feeds") or {}
    rows = lambda feed, name="rows": (feeds.get(feed) or {}).get(name) or []
    things, links = {}, {}

    def thing(kind, key, name, **details):
        if key in (None, ""):
            return None
        k = (kind, _key(key))
        if k not in things:
            things[k] = (kind, k[1], str(name or key), {a: b for a, b in details.items() if b not in (None, "", [])})
        return k

    def link(frm, relation, to, how, score=None):
        if frm and to:
            links.setdefault((*frm, relation, *to), (*frm, relation, *to, how, score))

    # Teams: the product families (the owners file, or HR level 3 when that setting is on).
    fams = (feeds.get("hr_mapping") or {}).get("families") or rows("hr_mapping")
    family = {}
    for f in fams:
        family[f["family_id"]] = thing("team", "family:" + f["family_id"], f.get("family") or f["family_id"],
                                       band=f.get("band"), owner_emails=f.get("owner_emails"))

    def family_of(fid):
        if fid in UNPLACED:
            return None
        return family.get(fid) or family.setdefault(fid, thing("team", "family:" + fid, fid))

    # People, from HR: each person, their manager, their department, their L3 and L4 managers' teams, their family.
    people = rows("hr", "people")
    by_email = {p["email"].lower(): p["sam_account"] for p in people if p.get("email")}
    name_of = {p["sam_account"]: p.get("worker") or p["sam_account"] for p in people}
    whos = linking.who_table(people, linking.l3_level(mapped.get("settings_used")))
    for p in people:
        sam = p["sam_account"]
        thing("person", sam, name_of[sam], email=p.get("email"), department=p.get("department"),
              reporting_level=p.get("reporting_level"), worker_type=p.get("worker_type"),
              is_manager=p.get("is_manager"))
    for p in people:
        sam = p["sam_account"]
        me = ("person", _key(sam))
        if p.get("manager_sam") and ("person", _key(p["manager_sam"])) in things:
            link(me, "reports_to", ("person", _key(p["manager_sam"])), "HR reporting line")
        if p.get("department"):
            link(me, "member_of", thing("team", "department:" + p["department"], p["department"]), "HR department")
        for level in ("l3", "l4"):
            lead = by_email.get((whos.get(sam, {}).get(level + "_email") or "").lower())
            if lead:
                link(me, "member_of", thing("team", f"{level}:{lead}", name_of[lead], lead=lead), "HR reporting line")
        link(me, "member_of", family_of(p.get("family_id")),
             "HR reporting line" if mapped.get("team_grouping") == "l3" else "HR reporting line to a family owner")

    def person(sam=None, email=None):
        sam = sam or by_email.get((email or "").lower())
        k = ("person", _key(sam)) if sam else None
        return k if k in things else None

    # Applications, from the app inventory: placed with a family, owned by people.
    for a in rows("app_inventory"):
        app = thing("application", a.get("app_id"), a.get("app_name"), status=a.get("status"), active=a.get("active"),
                    org_group=a.get("org_group"), department=a.get("department"))
        if not app:
            continue
        how = {"org": "app inventory organization matched to a family", "owners": "app owners' families"}.get(
            a.get("family_how"), a.get("family_how") or "app inventory")
        link(app, "placed_with", family_of(a.get("family_id")),
             "approved claim" if a.get("claimed") else how, (a.get("org_match") or {}).get("score"))
        for o in a.get("owners") or []:
            link(app, "owned_by", person(o.get("sam"), o.get("email")), o.get("via") or "app inventory owner")
        if (a.get("itdr") or {}).get("ref") is not None:
            links[("itdr_application", _key(a["itdr"]["ref"]), "same_as", *app)] = (
                "itdr_application", _key(a["itdr"]["ref"]), "same_as", *app, "name match", a["itdr"].get("score"))

    # ITDR applications: their tier, and the family mapping placed them with.
    for r in rows("itdr"):
        it = thing("itdr_application", r.get("ref"), r.get("application_name"), tier=r.get("tier_label"),
                   recovery_tier=r.get("recovery_tier"), business_product_area=r.get("business_product_area"))
        m = r.get("family_match") or {}
        link(it, "placed_with", family_of(r.get("family_id")),
             "approved claim" if r.get("claimed") else (m.get("how") or "Business Product Area"), m.get("score"))
    links = {k: v for k, v in links.items() if (v[0], v[1]) in things}      # an ITDR Ref the ITDR file doesn't have

    # Repositories, from GitHub: owner, family, and the applications they serve.
    for r in rows("repos"):
        repo = thing("repository", r.get("repo"), r.get("repo"), active=r.get("active"), archived=r.get("archived"),
                     fork=r.get("fork"), default_branch=r.get("default_branch"), last_activity=r.get("last_activity"))
        link(repo, "owned_by", person(email=r.get("owner_email")),
             f"repo owner ({(mapped.get('settings_used') or {}).get('repo_owner_rule') or 'most_commits'}), found in HR by "
             f"{r.get('owner_matched_by') or 'email'}")
        link(repo, "placed_with", family_of(r.get("family_id")), "approved claim" if r.get("claimed") else "repo owner's family")
    for a in rows("app_inventory"):
        for name in a.get("repos") or []:
            if ("repository", _key(name)) in things and a.get("app_id"):
                link(("repository", _key(name)), "serves", ("application", _key(a["app_id"])), "app inventory service repo")

    return sorted(things.values()), sorted(links.values(), key=lambda v: v[:6])


def save(mapped):
    """Build and keep the month's things and links (replacing the month's earlier ones). Returns the counts."""
    things, links = build(mapped)
    storage.save_things(mapped["month"], things, links)
    counts = {}
    for t in things:
        counts[t[0]] = counts.get(t[0], 0) + 1
    counts["links"] = len(links)
    return counts


def members(month, team_key):
    """The SAM_ACCOUNTs of the people in a team (any kind of team) for a month: the roll-up every grouping uses."""
    return sorted(l["from_key"] for l in storage.thing_links(month)
                  if l["relation"] == "member_of" and l["from_kind"] == "person" and l["to_key"] == team_key)
