"""Elevated risk markers on the CTO view (owner, 16 Nov 2026). Display only.

Risks are never compared between teams. This is the owner's opt-in exception: Tech Risk switches a metric On, and then
the CTO view marks each team whose own newest risk assessment has an Elevated risk that the metric watches. Each marker
is a pointer to a conversation. It never changes a score, a status, a threshold, a cap, a watch list or a letter.

The three questions, answered in this order:
  1. Which metrics are On? The "CTO view risk markers" list (editable.py): one entry per Measured metric, all Off to start.
  2. Which risks does a metric watch? The "Risks each metric watches" list (editable.py; starts from card.risks in config/metrics.json).
  3. Is one of those Elevated for a team? Read from the team's own newest assessment, as stored when it was submitted.
     Nothing is rated again. A Risk group IS a TRUST team (family_link.py), so the group id is the family id.

Only metrics that are On send anything. For an Off metric nothing at all leaves the server except, to Tech Risk, its
name and that it is Off (so Tech Risk can switch it On). Only the teams the person may see are included.
"""
from trust import access, editable, storage
from trust.risk import family_link, groups


def elevated_in_newest_assessment(team_id):
    """{risk id: risk name} for each risk that is Elevated in the team's newest assessment. Empty when never assessed."""
    assessments = storage.risk_assessments(team_id)
    if not assessments:
        return {}
    return {risk_id: entry.get("name") or risk_id for risk_id, entry in family_link.elevated_entries(assessments[-1]["result"])}


def markers_for(metric_ids, team_ids):
    """One marker per team and metric where the metric watches a risk that is Elevated for the team:
    {"family", "metric", "risks": [{"id", "name"}]}. Teams in the order given, then metrics in the order given."""
    found = []
    for team_id in team_ids:
        elevated_now = elevated_in_newest_assessment(team_id)
        if not elevated_now:
            continue
        for metric_id in metric_ids:
            watched = editable.metric_risks(metric_id)
            hits = [{"id": risk_id, "name": elevated_now[risk_id]} for risk_id in watched if risk_id in elevated_now]
            if hits:
                found.append({"family": team_id, "metric": metric_id, "risks": hits})
    return found


def answer_for(person):
    """What the CTO view reads: {"can_change", "metrics": [{"id","name","on", "watches"?}], "markers": [...]}.

    Tech Risk gets every Measured metric, to flip. Everyone else gets only the metrics that are On."""
    can_change = access.may_act_as_tech_risk(person)
    entries = editable.entries_now("cto-risk-markers")
    metrics = []
    for entry in entries:
        is_on = entry["values"].get("show") is True
        if not is_on and not can_change:
            continue
        chip = {"id": entry["key"], "name": entry["values"]["name"], "on": is_on}
        if can_change:
            chip["watches"] = len(editable.metric_risks(entry["key"]))
        metrics.append(chip)
    metric_ids_on = [chip["id"] for chip in metrics if chip["on"]]
    all_team_ids = [team["id"] for team in groups.teams_in(groups.hr_month())]
    team_ids = [team_id for team_id in all_team_ids if team_id in access.families_seen(person, all_team_ids)]
    markers = markers_for(metric_ids_on, team_ids) if metric_ids_on else []
    return {"ok": True, "can_change": can_change, "metrics": metrics, "markers": markers}
