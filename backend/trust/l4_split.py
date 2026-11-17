"""Each L4 leader's share of a team's numbers: counts only (owner, 17 Nov 2026).

On a team page, "By L4" shows how many of the team's items sit under each L4 leader, in the metric's own
counts ("3 of 20 releases ..."). An L4 leader is the person at HR reporting level l3_level + 1 on the manager chain of
someone on the item (linking.who_table puts "l4" and "l4_email" on every person).

What this module never does: score, rate, colour or compare. No status, no letter, no threshold.

The rules:
- An item is counted for each L4 its people sit under, once per L4, however many of its people sit under that L4.
  An item with people under two L4s therefore counts once for each; the rows can add up to more than the team's
  total. The page says so (`counted_twice`).
- An item whose people have no L4 at all (the team lead's own, or nobody placed) is counted under "Not under an L4".
- A metric is split only when its figure is made of the items themselves. A figure with a team-level part
  (UN-01's apps) is not split: it comes back with the plain reason, never a guess.
"""

NOT_UNDER_AN_L4 = "Not under an L4"


def can_split(metric):
    """(True, "") when the metric's numerator and denominator are both made of its items, else (False, reason).
    A "per 10 apps" figure counts incidents, but its apps are counted for the whole team, not by person."""
    unit = metric.get("unit") or ""
    if unit.startswith("per "):
        denominator = metric.get("denominator_label") or "denominator"
        return False, f"its {denominator.lower()} are counted for the whole team, not by person."
    return True, ""


def _l4_leaders_of(item):
    """{L4 key: (name, email)} for the L4 leaders of the people on one item, each once.
    The key is the L4's email, or their name when there is no email."""
    leaders = {}
    for person in item.get("who") or []:
        name = person.get("l4") or ""
        email = person.get("l4_email") or ""
        if name or email:
            leaders[(email or name).lower()] = (name or email, email)
    return leaders


def split_metric(metric, items, count_item, lead_name="", lead_email=""):
    """Split one metric's items by L4 leader.

    metric: the metric's entry in config/metrics.json (unit, denominator_label).
    items: the items behind the team's number (each with a "who" list of people).
    count_item(item) -> (numerator, denominator): what that item adds to the metric.
    lead_name, lead_email: the team's L3 lead, named as the owner of "Not under an L4".

    Returns {"split": bool, "reason": str, "counted_twice": bool,
             "rows": [{"l4", "l4_email", "num", "den"}], "not_under": {"l4", "l4_email", "num", "den"} or None}."""
    allowed, reason = can_split(metric)
    if not allowed:
        return {"split": False, "reason": reason, "counted_twice": False, "rows": [], "not_under": None}
    rows = {}
    not_under = {"l4": NOT_UNDER_AN_L4, "l4_email": "", "owner": lead_name, "owner_email": lead_email, "num": 0, "den": 0}
    counted_twice = False
    for item in items:
        numerator, denominator = count_item(item)
        leaders = _l4_leaders_of(item)
        if not leaders:
            not_under["num"] += numerator
            not_under["den"] += denominator
            continue
        if len(leaders) > 1:
            counted_twice = True
        for key, (name, email) in leaders.items():
            row = rows.setdefault(key, {"l4": name, "l4_email": email, "num": 0, "den": 0})
            row["num"] += numerator
            row["den"] += denominator
    ordered = sorted(rows.values(), key=lambda row: (-row["den"], row["l4"].lower()))
    return {"split": True, "reason": "", "counted_twice": counted_twice, "rows": ordered,
            "not_under": not_under if not_under["den"] else None}


def team_lead(family, items_by_metric):
    """(name, email) of a team's L3 lead: the family's accountable person, with their email read from the
    "l3" and "l3_email" on the people of its items. Blank when it isn't known."""
    name = (family or {}).get("accountable") or ""
    email = ""
    for items in items_by_metric.values():
        for item in items:
            for person in item.get("who") or []:
                if person.get("l3_email") and (not name or person.get("l3") == name):
                    name = name or person.get("l3") or ""
                    return name, person["l3_email"]
    return name, email
