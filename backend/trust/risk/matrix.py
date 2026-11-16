"""The current risk heat map: totals across the newest assessment of every assessed group
(see docs/design/21_risk_site.md, "Risk heat map").

Owner's decision, 16 Nov 2026: risks are raised so a treatment can be agreed. They are not compared between teams.
So this file adds everything up HERE, on the server, and the answer holds no group id, no group name and nothing per
group. Each team's own results are on that team's page.

This file only READS. It takes each group's newest assessment and the one before it, as they were kept. It never
rates a risk again. The one thing it works out is how a risk moved since the group's own previous assessment, and
that is rating.trend(), the same rule the results page uses.

The Elevated cells of the grid come from the rating settings (elevated_likelihood_at_least and
elevated_impact_at_least), read from the settings the site has loaded. Nothing is typed here.
"""
from trust.risk import rating

TREND_WORDS = ["better", "worse", "mixed", "no change"]


def risk_entry(risk_id, newest_risk, previous_risk):
    """One risk for one group, before adding up. Only a risk that applies to the group has a rating."""
    name = newest_risk.get("name") or risk_id
    if not newest_risk.get("applicable"):
        return {"id": risk_id, "name": name, "block": newest_risk.get("block"), "applies": False,
                "likelihood": None, "impact": None, "elevated": False, "trend": None}
    return {"id": risk_id, "name": name, "block": newest_risk.get("block"), "applies": True,
            "likelihood": newest_risk.get("likelihood"), "impact": newest_risk.get("impact"),
            # Elevated as it was decided when the group submitted, so the matrix always agrees with the group's results page.
            "elevated": newest_risk["elevated"],
            "trend": rating.trend(previous_risk, newest_risk)}


def group_entry(assessment_rows):
    """One group: its newest assessment's risks and the trend since the one before. A group never assessed has
    assessed False and no risks."""
    if not assessment_rows:
        return {"assessed": False, "has_previous": False, "risks": []}
    newest = assessment_rows[-1]["result"]
    previous = assessment_rows[-2]["result"] if len(assessment_rows) > 1 else None
    previous_risks = (previous or {}).get("risks", {})
    entries = [risk_entry(risk_id, newest_risk, previous_risks.get(risk_id))
               for risk_id, newest_risk in sorted(newest["risks"].items())]
    return {"assessed": True, "has_previous": previous is not None, "risks": entries}


def seriousness(likelihood, impact):
    """How serious a rated risk is: its likelihood rank plus its impact rank, then the impact rank alone."""
    likelihood_rank = rating.rank(likelihood)
    impact_rank = rating.rank(impact)
    return (likelihood_rank + impact_rank, impact_rank)


def place_in_cells(cells, entry):
    """Count one risk of one group in its box of the grid. Returns the box's entry for the risk."""
    box = cells[entry["likelihood"]][entry["impact"]]
    placed = box.setdefault(entry["id"], {"risk_id": entry["id"], "risk_name": entry["name"], "block": entry["block"],
                                          "assessments": 0, "elevated_assessments": 0})
    placed["assessments"] += 1
    return placed


def note_elevated(elevated_by_risk, entry):
    """Count one Elevated risk of one group, and keep the most serious box any group put it in."""
    worst = elevated_by_risk.setdefault(entry["id"], {"risk_id": entry["id"], "risk_name": entry["name"], "block": entry["block"],
                                                      "elevated_assessments": 0, "likelihood": entry["likelihood"],
                                                      "impact": entry["impact"]})
    worst["elevated_assessments"] += 1
    if seriousness(entry["likelihood"], entry["impact"]) > seriousness(worst["likelihood"], worst["impact"]):
        worst["likelihood"] = entry["likelihood"]
        worst["impact"] = entry["impact"]


def note_movement(movement_by_risk, entry):
    """Count which way one risk of one group moved since that group's previous assessment."""
    moved = movement_by_risk.setdefault(entry["id"], {"risk_id": entry["id"], "block": entry["block"],
                                                      **{word: 0 for word in TREND_WORDS}})
    moved[entry["trend"]] += 1


def add_up(group_entries):
    """Add every group's risks up into totals. Group ids and names stop here: nothing below holds them.

    cells:    for each likelihood and impact, the risks in that box, each with how many assessments put it there
    focus:    the Elevated risks, each with how many assessments have it Elevated (worst first)
    movement: for each risk, how many assessments say better, worse, mixed or no change
    """
    cells = {likelihood_level: {impact_level: {} for impact_level in rating.LEVELS} for likelihood_level in rating.LEVELS}
    elevated_by_risk = {}
    movement_by_risk = {}
    for group in group_entries:
        for entry in group["risks"]:
            if not entry["applies"] or not entry["impact"]:
                continue
            placed = place_in_cells(cells, entry)
            if entry["elevated"]:
                placed["elevated_assessments"] += 1
                note_elevated(elevated_by_risk, entry)
            if entry["trend"] in TREND_WORDS:
                note_movement(movement_by_risk, entry)
    boxes = {likelihood_level: {impact_level: sorted(box.values(), key=lambda item: (-item["elevated_assessments"], -item["assessments"], item["risk_name"]))
                                for impact_level, box in row.items()} for likelihood_level, row in cells.items()}
    focus = sorted(elevated_by_risk.values(),
                   key=lambda item: (-seriousness(item["likelihood"], item["impact"])[0], -seriousness(item["likelihood"], item["impact"])[1],
                                     -item["elevated_assessments"], item["risk_name"]))
    return boxes, focus, list(movement_by_risk.values())


def build(assessment_rows_by_group, settings, risk_details=None):
    """The whole heat map answer. assessment_rows_by_group is one list of assessment rows (oldest first) for each team.
    risk_details is {risk id: description, example, controls}, kept for the risks that appear.
    Only counts leave this function: no team id, no team name."""
    group_entries = [group_entry(rows) for rows in assessment_rows_by_group]
    assessed = [group for group in group_entries if group["assessed"]]
    cells, focus, movement = add_up(group_entries)
    risk_ids_shown = {item["risk_id"] for row in cells.values() for box in row.values() for item in box}
    details = {risk_id: detail for risk_id, detail in (risk_details or {}).items() if risk_id in risk_ids_shown}
    blocks = sorted({item["block"] for row in cells.values() for box in row.values() for item in box if item["block"]})
    return {"levels": rating.LEVELS,
            "elevated_likelihood_at_least": settings["elevated_likelihood_at_least"],
            "elevated_impact_at_least": settings["elevated_impact_at_least"],
            "groups_assessed": len(assessed),
            "groups_with_a_previous_assessment": len([group for group in assessed if group["has_previous"]]),
            "blocks": blocks,
            "risk_details": details,
            "cells": cells,
            "focus": focus,
            "movement": movement}
