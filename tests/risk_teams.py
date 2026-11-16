"""Made-up TRUST teams for the Risk site's tests (16 Nov 2026).

A Risk group IS a TRUST team, so a test that uses a group first needs TRUST to hold teams. This puts one mapped month
in the store: some made-up people, five teams (the product families TRUST would map), and who is in each.

    Lending (id "lending")      led by Emery Rook (erook6), with Pat Lee and Sam Ito. Emery reports to Sage Crane
                                (scrane1), who reports to Cass Top (cto.demo).
    Payments ("payments")       led by Pia Yu (pay1), with Pat Yates (pay2)
    Cards ("cards")             led by Sage Crane (scrane1), with Cal Ross and Zed Moss
    Treasury ("treasury")       led by Jo Calder (jcalder3), with Tom Ash (tom1)
    Print Services              on purpose, nobody is placed with it and its owner isn't in HR, so it shows how a team
    ("print-services")          with nobody in it looks
"""
from trust import storage

MONTH = "2026-10"

# (SAM_ACCOUNT, name, manager)
PEOPLE = [("cto.demo", "Cass Top", None), ("scrane1", "Sage Crane", "cto.demo"),
          ("erook6", "Emery Rook", "scrane1"), ("pat1", "Pat Lee", "erook6"), ("sam2", "Sam Ito", "erook6"),
          ("zed9", "Zed Moss", "scrane1"),
          ("pay1", "Pia Yu", "scrane1"), ("pay2", "Pat Yates", "pay1"),
          ("card1", "Cal Ross", "scrane1"),
          ("jcalder3", "Jo Calder", "scrane1"), ("tom1", "Tom Ash", "jcalder3")]

# (team id, team name, the owner's email in the family owners file, the people placed with the team)
TEAMS = [("payments", "Payments", "pay1@example.test", ["pay1", "pay2"]),
         ("cards", "Cards", "scrane1@example.test", ["scrane1", "card1", "zed9"]),
         ("lending", "Lending", "erook6@example.test", ["erook6", "pat1", "sam2"]),
         ("treasury", "Treasury", "jcalder3@example.test", ["jcalder3", "tom1"]),
         ("print-services", "Print Services", "nobody@example.test", [])]


def put_made_up_teams(month=MONTH):
    """Save the made-up mapped month and its things (people, teams, who reports to whom, who is in each team)."""
    team_of = {sam: team_id for team_id, _name, _owner, placed in TEAMS for sam in placed}
    hr_people = [{"sam_account": sam, "worker": name, "email": f"{sam}@example.test", "manager_sam": manager,
                  "family_id": team_of.get(sam, "UNATTRIBUTED")} for sam, name, manager in PEOPLE]
    families = [{"family_id": team_id, "family": name, "owner_emails": [owner]} for team_id, name, owner, _people in TEAMS]
    storage.save_month("mapped", month, {"month": month, "feeds": {"hr": {"people": hr_people},
                                                                    "hr_mapping": {"families": families}}})
    things = [("person", sam, name, {}) for sam, name, _manager in PEOPLE]
    things += [("team", "family:" + team_id, name, {}) for team_id, name, _owner, _people in TEAMS]
    links = [("person", sam, "reports_to", "person", manager, "HR reporting line", None)
             for sam, _name, manager in PEOPLE if manager]
    for team_id, _name, _owner, placed in TEAMS:
        links += [("person", sam, "member_of", "team", "family:" + team_id, "HR reporting line", None) for sam in placed]
    storage.save_things(month, things, links)
