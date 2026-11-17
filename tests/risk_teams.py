"""Made-up L4 teams for the Risk site's tests (17 Nov 2026).

A Risk group is an L4 team, shown under its L3 team (the TRUST team). A test that uses a group first needs TRUST to hold
people with reporting levels. This puts one mapped month in the store: made-up people, five L3 teams (the product
families TRUST would map), and the L4 teams under them. Reporting level from the top: 3 leads an L3 team, 4 leads an L4 team.

    L3 team Lending ("lending")      led by Emery Rook (erook6, level 3)
        L4 Lending Platform          Lena Ford (lford4, level 4), with Pat Lee (pat1) and Sam Ito (sam2) under her
        L4 Lending Servicing         Rae Boyd (rboyd5, level 4), on her own
    L3 team Payments ("payments")    led by Pia Yu (pay1, level 3)
        L4 Payments Core             Pat Yates (pay2, level 4), on his own
    L3 team Cards ("cards")          led by Sage Crane (scrane1, level 3)
        L4 Cards Ops                 Cal Ross (card1, level 4)
        L4 Cards Risk                Zed Moss (zed9, level 4)
    L3 team Treasury ("treasury")    led by Jo Calder (jcalder3, level 3)
        L4 Treasury Ops              Tom Ash (tom1, level 4)
    Print Services                   on purpose, nobody is placed with it and its owner isn't in HR, so it shows how a
    ("print-services")               team with nobody in it looks (it has no L4 teams)

Sage Crane (scrane1) is the CTO's direct report and also Emery's manager, so she is a manager above Lending's L4 teams.
The group ids are the constants below.
"""
from trust import storage

MONTH = "2026-10"

LENDING_PLATFORM = "lending--lending-platform"
LENDING_SERVICING = "lending--lending-servicing"
PAYMENTS_CORE = "payments--payments-core"
CARDS_OPS = "cards--cards-ops"
CARDS_RISK = "cards--cards-risk"
TREASURY_OPS = "treasury--treasury-ops"
# in the site's order: L3 teams in the order of TEAMS below, then L4 teams by name
ALL_GROUPS = [PAYMENTS_CORE, CARDS_OPS, CARDS_RISK, LENDING_PLATFORM, LENDING_SERVICING, TREASURY_OPS]

# (SAM_ACCOUNT, name, manager, reporting level from the top, Supervisory Organization)
PEOPLE = [("cto.demo", "Cass Top", None, 1, "Technology (Cass Top)"),
          ("scrane1", "Sage Crane", "cto.demo", 3, "Cards (Sage Crane)"),
          ("erook6", "Emery Rook", "scrane1", 3, "Lending (Emery Rook)"),
          ("lford4", "Lena Ford", "erook6", 4, "Lending Platform (Lena Ford)"),
          ("pat1", "Pat Lee", "lford4", 5, "Lending Platform (Lena Ford)"),
          ("sam2", "Sam Ito", "lford4", 5, "Lending Platform (Lena Ford)"),
          ("rboyd5", "Rae Boyd", "erook6", 4, "Lending Servicing (Rae Boyd)"),
          ("zed9", "Zed Moss", "scrane1", 4, "Cards Risk (Zed Moss)"),
          ("pay1", "Pia Yu", "scrane1", 3, "Payments (Pia Yu)"),
          ("pay2", "Pat Yates", "pay1", 4, "Payments Core (Pat Yates)"),
          ("card1", "Cal Ross", "scrane1", 4, "Cards Ops (Cal Ross)"),
          ("jcalder3", "Jo Calder", "scrane1", 3, "Treasury (Jo Calder)"),
          ("tom1", "Tom Ash", "jcalder3", 4, "Treasury Ops (Tom Ash)")]

# (team id, team name, the owner's email in the family owners file, the people placed with the team)
TEAMS = [("payments", "Payments", "pay1@example.test", ["pay1", "pay2"]),
         ("cards", "Cards", "scrane1@example.test", ["scrane1", "card1", "zed9"]),
         ("lending", "Lending", "erook6@example.test", ["erook6", "lford4", "pat1", "sam2", "rboyd5"]),
         ("treasury", "Treasury", "jcalder3@example.test", ["jcalder3", "tom1"]),
         ("print-services", "Print Services", "nobody@example.test", [])]


def put_made_up_teams(month=MONTH):
    """Save the made-up mapped month and its things (people, teams, who reports to whom, who is in each team)."""
    team_of = {sam: team_id for team_id, _name, _owner, placed in TEAMS for sam in placed}
    hr_people = [{"sam_account": sam, "worker": name, "email": f"{sam}@example.test", "manager_sam": manager,
                  "reporting_level": level, "sup_org": sup_org,
                  "family_id": team_of.get(sam, "UNATTRIBUTED")} for sam, name, manager, level, sup_org in PEOPLE]
    families = [{"family_id": team_id, "family": name, "owner_emails": [owner]} for team_id, name, owner, _people in TEAMS]
    storage.save_month("mapped", month, {"month": month, "feeds": {"hr": {"people": hr_people},
                                                                    "teams": {"families": families}}, "settings_used": {"l3_level": 3}})
    things = [("person", sam, name, {}) for sam, name, _manager, _level, _sup_org in PEOPLE]
    things += [("team", "family:" + team_id, name, {}) for team_id, name, _owner, _people in TEAMS]
    links = [("person", sam, "reports_to", "person", manager, "HR reporting line", None)
             for sam, _name, manager, _level, _sup_org in PEOPLE if manager]
    for team_id, _name, _owner, placed in TEAMS:
        links += [("person", sam, "member_of", "team", "family:" + team_id, "HR reporting line", None) for sam in placed]
    storage.save_things(month, things, links)
