"""The Risk site: engine bridge routes (see docs/design/21_risk_site.md, "Engine bridge and side by side").

    GET  /api/risk/groups/<id>/engine-input     the team's answers as a JSON download for the engine (layout Wanted: confirm)
    POST /api/risk/groups/<id>/engine-output    upload the engine's output file for the team (Tech Risk only)
    GET  /api/risk/groups/<id>/compare          the engine's rating beside the site's, risk by risk (Tech Risk only)
    GET  /api/risk/compare                      every team, with its last comparison result (Tech Risk only)

Comparing with the engine is for Tech Risk (owner, 16 Nov 2026), because it lists teams' results side by side.
While TRUST runs open, everyone may, as for every Tech Risk action. Registered at the end of web.py.
"""
import json

from flask import Blueprint, Response, g, jsonify, request

from trust import access, storage
from trust.lazy_web import stop_data_senders, trust_web
from trust.risk import assess, current_rules, engine_bridge, groups, questions as question_list, signoff, site
from trust.risk.registers import load_registers
from trust.words import today_text

bp = Blueprint("risk_engine_bridge", __name__)
bp.before_request(stop_data_senders)


def stop_unless_tech_risk():
    """The engine comparison is Tech Risk's: it sets teams' results side by side."""
    if not access.may_act_as_tech_risk(g.person):
        raise trust_web().NotAllowed()


def answers_the_engine_was_given(group_id, loaded):
    """The answers as the driver rules read them. The newest assessment's answers when there is one (the comparison
    is made against that assessment), otherwise the answers saved now."""
    kept = current_rules.assessments(group_id)
    saved = kept[-1]["result"]["answers"] if kept else assess.answer_text(assess.latest_answers(storage.risk_answers(group_id)))
    return question_list.answers_by_field(loaded["questions"], saved)


@bp.get("/api/risk/groups/<group_id>/engine-input")
def engine_input(group_id):
    group, _rights = site.group_for_person(group_id, "view")
    answers = answers_the_engine_was_given(group_id, load_registers())
    document = engine_bridge.engine_input_layout(group, answers)
    text = json.dumps(document, indent=2) + "\n"
    return Response(text, content_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="engine-input-{group_id}-{today_text()}.json"'})


def read_upload():
    """The uploaded file's bytes and who is uploading: a file in a form (field 'file', and 'by'), or a JSON body
    (the engine's output itself, with ?by=name; or {"by": name, "output": {...}})."""
    if request.mimetype == "multipart/form-data" and "file" in request.files:
        uploaded = request.files["file"]
        return uploaded.read(engine_bridge.LARGEST_FILE_BYTES + 1), {"by": request.form.get("by") or request.args.get("by")}
    raw = request.get_data()
    body = request.get_json(silent=True)
    if isinstance(body, dict) and isinstance(body.get("output"), dict):
        return json.dumps(body["output"]).encode("utf-8"), {"by": body.get("by") or request.args.get("by")}
    return raw, {"by": request.args.get("by") or (body.get("by") if isinstance(body, dict) else None)}


@bp.post("/api/risk/groups/<group_id>/engine-output")
def engine_output(group_id):
    stop_unless_tech_risk()
    group, _rights = site.group_for_person(group_id, "view")
    raw, who_body = read_upload()
    who = trust_web()._who(who_body)
    parsed = engine_bridge.read_engine_output(raw)             # raises CannotRead (a ValueError): TRUST answers 400 in plain words
    kept = storage.add_risk_engine_run(group_id, who, engine_bridge.file_hash(raw), parsed)
    answer = comparison_for(group, load_registers())
    return jsonify(ok=True, engine_run_id=kept["id"], problems=parsed["problems"], **answer)


def comparison_for(group, loaded):
    """The newest engine run beside the newest assessment: {"comparison": ..., "why_not": plain words or None}."""
    runs = storage.risk_engine_runs(group["id"])
    assessments = current_rules.assessments(group["id"])
    if not runs:
        return {"comparison": None, "why_not": "No engine file has been uploaded for this team yet."}
    if not assessments:
        return {"comparison": None, "why_not": "This team hasn't been submitted on the site yet, so there is no site rating to set beside the engine's."}
    names = {code: rule.get("rationale") or code for code, rule in loaded["driver_rules"].items()}
    made = engine_bridge.compare(runs[-1], assessments[-1], loaded["risks"], names)
    return {"comparison": made, "why_not": None}


@bp.get("/api/risk/groups/<group_id>/compare")
def compare(group_id):
    stop_unless_tech_risk()
    group, _rights = site.group_for_person(group_id, "view")
    return jsonify(ok=True, group={"id": group["id"], "name": group["name"]}, can_upload=True,
                   runs=len(storage.risk_engine_runs(group_id)), **comparison_for(group, load_registers()))


@bp.get("/api/risk/compare")
def compare_all():
    """Every team you may see, with the last comparison's counts (nothing for a team with no engine file yet)."""
    stop_unless_tech_risk()
    month = groups.hr_month()
    loaded = load_registers()
    shown = []
    for group in groups.load():
        if not signoff.rights_with_signoff(g.person, group, month)["view"]:
            continue
        found = comparison_for(group, loaded)
        made = found["comparison"]
        shown.append({"id": group["id"], "name": group["name"], "why_not": found["why_not"],
                      "summary": made["summary"] if made else None, "counts": made["counts"] if made else None,
                      "engine_at": made["engine_run"]["at"] if made else None,
                      "assessment_at": made["assessment"]["at"] if made else None})
    return jsonify(ok=True, groups=shown, can_upload=True)
