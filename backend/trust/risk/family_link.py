"""An L3 team's own risk results, for its own team page (owner, 17 Nov 2026).

Risks are raised so the right treatment can be agreed. They are never compared between teams. This answers for ONE
L3 team at a time, and only that team's own page draws it. Nothing here adds up, ranks or sets teams side by side.

A Risk group is an L4 team (groups.py) and belongs to one L3 team. The L3 team's page lists its own L4 teams, each with
its own newest assessment. The L3 team's id is the family id on the page, and each group carries it as "l3_id", so
nothing is matched or guessed.

What is shown, for each L4 team of the L3 team. Its newest assessment: each risk that is Elevated (the rating was
decided when the team submitted; nothing is rated again), with its plain description, likelihood and impact. Also when
it was assessed and the sign-off status. An L4 team never assessed is listed as not assessed. The answer keeps its
shape, {"groups": [...]}: one entry per L4 team, each naming itself ("name") and its L3 team ("l3_name"). An id that
is not one of TRUST's L3 teams, or an L3 team with no L4 teams, gets no entries.
"""
from trust import storage
from trust.risk import current_rules, groups, signoff


def elevated_entries(result):
    """(risk id, its entry) for each risk the assessment found Elevated, in risk id order."""
    return [(risk_id, entry) for risk_id, entry in sorted(result["risks"].items())
            if entry.get("applicable") and entry.get("elevated")]


def elevated_risks(result, risk_descriptions):
    """The risks the assessment found Elevated: name, plain description, likelihood, impact. In risk id order."""
    found = []
    for risk_id, entry in elevated_entries(result):
        found.append({"id": risk_id, "name": entry.get("name") or risk_id,
                      "description": risk_descriptions.get(risk_id, ""),
                      "likelihood": entry.get("likelihood"), "impact": entry.get("impact")})
    return found


def group_view(group, assessment_rows, answer_rows, signoff_rows, risk_descriptions):
    """One group as the family page shows it."""
    status = signoff.status_of(group["id"], answer_rows, assessment_rows, signoff_rows)
    page = f"/risk/#/group/{group['id']}/results"
    form = f"/risk/#/group/{group['id']}"
    if not assessment_rows:
        return {"id": group["id"], "name": group["name"], "l3_name": group.get("l3_name"), "assessed": False, "status": status,
                "page": form, "elevated": []}
    newest = assessment_rows[-1]
    decision = signoff.short_summary(group["id"], assessment_rows, signoff_rows)
    return {"id": group["id"], "name": group["name"], "l3_name": group.get("l3_name"), "assessed": True, "assessed_at": newest["at"],
            "status": status, "signoff": decision, "page": page,
            "elevated": elevated_risks(newest["result"], risk_descriptions)}


def for_family(family_id, risk_descriptions):
    """{"groups": [group_view, ...]}: one entry for each L4 team of the L3 team `family_id`, in the site's order."""
    views = []
    for group in groups.in_l3_team(family_id, groups.hr_month()):
        assessment_rows = current_rules.assessments(group["id"])
        answer_rows = storage.risk_answers(group["id"])
        signoff_rows = storage.risk_signoffs(group["id"])
        views.append(group_view(group, assessment_rows, answer_rows, signoff_rows, risk_descriptions))
    answer = {"groups": views}
    if views and current_rules.line_for():               # the one line that says results are rated with today's rules
        answer["rated_with_current_rules"] = current_rules.line_for()
    return answer
