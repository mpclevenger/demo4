"""A TRUST team's own risk results, for its own family page (owner, 16 Nov 2026).

Risks are raised so the right treatment can be agreed. They are never compared between teams. So this answers for ONE
team at a time, and only that team's own page draws it. Nothing here adds up, ranks or sets teams side by side.

A Risk group IS a TRUST team (groups.py), so the group's id is the family id on the family page: the family page reads
the assessment whose group id is the family id directly. Nothing is matched or guessed.

What is shown. The team's newest assessment: each risk that is Elevated (the rating was decided when the team
submitted; nothing is rated again), with its plain description, likelihood and impact. Also when it was assessed and the
sign-off status. A team never assessed is listed as not assessed. The answer keeps its old shape, {"groups": [...]},
with at most one entry: the team itself. A family that isn't one of TRUST's teams gets no entry.
"""
from trust import storage
from trust.risk import groups, signoff


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
        return {"id": group["id"], "name": group["name"], "assessed": False, "status": status,
                "page": form, "elevated": []}
    newest = assessment_rows[-1]
    decision = signoff.short_summary(group["id"], assessment_rows, signoff_rows)
    return {"id": group["id"], "name": group["name"], "assessed": True, "assessed_at": newest["at"],
            "status": status, "signoff": decision, "page": page,
            "elevated": elevated_risks(newest["result"], risk_descriptions)}


def for_family(family_id, risk_descriptions):
    """{"groups": [group_view]} for one team, or {"groups": []} when the id is not one of TRUST's teams."""
    group = groups.find(family_id)
    if group is None:
        return {"groups": []}
    assessment_rows = storage.risk_assessments(group["id"])
    answer_rows = storage.risk_answers(group["id"])
    signoff_rows = storage.risk_signoffs(group["id"])
    return {"groups": [group_view(group, assessment_rows, answer_rows, signoff_rows, risk_descriptions)]}
