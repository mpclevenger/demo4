"""Elevated risk markers on the CTO view (owner, 16 Nov 2026). Display only.

Risks are never compared between teams. This is the owner's exception: the markers follow the risk assessments by
themselves, with no switches (owner, 16 Nov 2026). The CTO view marks each team whose own newest risk assessment has an
Elevated risk that a metric watches. Each marker is a pointer to a conversation. It never changes a score, a status, a
threshold, a cap, a watch list or a letter.

The two questions, answered in this order:
  1. Which risks does a metric watch? The "Risks each metric watches" list (editable.py; starts from card.risks in config/metrics.json).
  2. Is one of those Elevated for a team? Read from the team's own newest assessment, as stored when it was submitted.
     Nothing is rated again. A Risk group IS a TRUST team (family_link.py), so the group id is the family id.

No assessment, nothing Elevated, or a metric that watches no risk: nothing is marked and nothing is sent.
Only the teams the person may see are included.
"""
from trust import access, config, editable, storage
from trust.risk import family_link, groups


def elevated_in_newest_assessment(team_id):
    """{risk id: risk name} for each risk that is Elevated in the team's newest assessment. Empty when never assessed."""
    assessments = storage.risk_assessments(team_id)
    if not assessments:
        return {}
    return {risk_id: entry.get("name") or risk_id for risk_id, entry in family_link.elevated_entries(assessments[-1]["result"])}


def markers_for(metric_ids, team_ids):
    """One marker per team and metric where the metric watches a risk that is Elevated for the team:
    {"family", "metric", "metric_name", "risks": [{"id", "name"}]}. Teams in the order given, then metrics in the order given."""
    metric_name_of = {metric_id: metric["name"] for metric_id, metric in config.metrics().items()}
    found = []
    for team_id in team_ids:
        elevated_now = elevated_in_newest_assessment(team_id)
        if not elevated_now:
            continue
        for metric_id in metric_ids:
            watched = editable.metric_risks(metric_id)
            hits = [{"id": risk_id, "name": elevated_now[risk_id]} for risk_id in watched if risk_id in elevated_now]
            if hits:
                found.append({"family": team_id, "metric": metric_id, "metric_name": metric_name_of.get(metric_id, metric_id), "risks": hits})
    return found


def answer_for(person):
    """What the CTO view reads: {"ok": True, "markers": [...]}. Only the teams the person may see."""
    metric_ids = [metric_id for metric_id, metric in config.metrics().items() if (metric.get("status") or "Measured") == "Measured"]
    all_team_ids = [team["id"] for team in groups.teams_in(groups.hr_month())]
    seen_team_ids = access.families_seen(person, all_team_ids)
    team_ids = [team_id for team_id in all_team_ids if team_id in seen_team_ids]
    return {"ok": True, "markers": markers_for(metric_ids, team_ids)}
