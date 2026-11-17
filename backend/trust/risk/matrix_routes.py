"""The Risk site: heat map route (see docs/design/21_risk_site.md, "Risk heat map"). Registered at the end of web.py.

    GET  /api/risk/matrix     the current risk heat map: totals only, no team ids or names

Everyone who can open the Risk site sees it, because it holds totals only (owner, 16 Nov 2026).
"""
from flask import Blueprint, jsonify

from trust import storage
from trust.lazy_web import stop_data_senders
from trust.risk import current_rules, groups, matrix, site, trac_controls
from trust.risk.registers import load_registers
from trust.words import tidy_spaces

bp = Blueprint("risk_matrix", __name__)
bp.before_request(stop_data_senders)


@bp.get("/api/risk/matrix")
def risk_matrix():
    """Totals across the newest assessment of every assessed team. Nothing per team."""
    loaded = load_registers()
    every_assessment = current_rules.assessments()
    rows_by_group = [site.rows_of(group["id"], every_assessment) for group in groups.load()]
    controls_by_risk = trac_controls.controls_by_risk(storage.risk_controls_copy())   # the kept copy only
    risk_details = {}
    for risk_id, risk in loaded["risks"].items():
        risk_details[risk_id] = {"description": tidy_spaces(risk.get("description")),
                                 "example": tidy_spaces(risk.get("example")),
                                 "controls": controls_by_risk.get(risk_id, [])}
    return jsonify(ok=True, rated_with_current_rules=current_rules.line_for(loaded["settings"]),
                   **matrix.build(rows_by_group, loaded["settings"], risk_details))
