"""The Risk site's own pages and routes (its front end is frontend/risk/). Registered at the end of web.py.

The pages are served under /risk/. The data and the changes are under /api/risk/, so they get the same
checks as every other change in TRUST (web.py's before_request: the person comes from the access add-on, and
a change must carry the header X-TRUST: 1). A team's service account that only sends metric numbers is refused here.

    GET  /risk/                                  the page
    GET  /risk/<file>.js, .css                   the page's own scripts and styles
    GET  /api/risk/me                            what the top bar shows: TEST or not, who you are, whether you are Tech Risk
    GET  /api/risk/registers                     the risks, drivers and questions as the site reads them (read only here;
                                                 Tech Risk edits them at /risk/#/edit and uploads them at /risk/#/seed)
    GET  /api/risk/groups                        the teams you may open, each with its status
    GET  /api/risk/groups/<id>                   one team: the form with each question's newest answer
    POST /api/risk/groups/<id>/start             start a new assessment (who and when are kept; one open at a time)
    POST /api/risk/groups/<id>/answers           save one answer (a new row; the newest stands)
    POST /api/risk/groups/<id>/submit            rate every risk from the saved answers and keep it as an assessment
    GET  /api/risk/groups/<id>/assessment        the newest assessment (or ?id=N), with the earlier ones listed
    GET  /api/risk/download                      the risks and drivers as a .zip in the risk engine's file shape
    GET  /api/risk/controls                      the kept copy of TRAC's controls, and which address each risk
    POST /api/risk/controls/refresh              Tech Risk: fetch a new copy of TRAC's controls
    GET  /api/risk/teams                         every L3 team with its L4 teams and their counts (team results pages)
    GET  /api/risk/teams/<id>/results            one L4 or L3 team's results page data (open to everyone who can open the site)
    GET  /api/risk/teams/<id>/results.csv        the same, one row per risk and driver
    GET  /api/risk/family/<id>                   one family's own team results, for its family page
    GET  /api/cto/risk-markers                   the Elevated risk markers on the CTO view (no switches)

The sign-off routes are in signoff_routes.py, the engine comparison in engine_bridge_routes.py, the heat map in
matrix_routes.py and the file uploads in seed_routes.py. The editing lists are in backend/trust/editable.py.

Design and wording: docs/design/21_risk_site.md.
"""
import pathlib

from flask import Blueprint, Response, current_app, g, jsonify, request

from trust import access, publish, storage
from trust.lazy_web import stop_data_senders, trust_web
from trust.risk import assess, blocks, code_places, cto_markers, current_rules, data_drivers, download, family_link, files, groups, home, questions as question_list, signoff, team_results, trac_controls
from trust.risk.registers import load_registers
from trust.words import tidy_spaces, today_text

bp = Blueprint("risk_site", __name__)

ROOT = pathlib.Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "risk"
ASSET_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


class NoSuchGroup(Exception):
    """The id is not one of TRUST's teams."""


class NotYourGroup(Exception):
    """The person may not do this on this team."""


@bp.app_errorhandler(NoSuchGroup)
def no_such_group(_error):
    """For every Risk route: an id that is not a TRUST team."""
    return jsonify(ok=False, error="There is no such team. The Risk site uses TRUST's teams."), 404


@bp.app_errorhandler(NotYourGroup)
def not_your_group(error):
    return jsonify(ok=False, error=str(error)), 403


bp.before_request(stop_data_senders)


# ---------------------------------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------------------------------

@bp.get("/risk/")
def page():
    return Response((FRONTEND / "index.html").read_bytes(), content_type="text/html; charset=utf-8")


@bp.get("/risk/<name>")
def page_asset(name):
    """Only .js and .css files from frontend/risk/, to people who may open TRUST."""
    path = FRONTEND / name
    kind = ASSET_TYPES.get(path.suffix)
    if kind is None or "/" in name or "\\" in name or name.startswith(".") or not path.is_file():
        return Response("Not found", status=404, content_type="text/plain")
    return Response(path.read_bytes(), content_type=kind)


@bp.get("/api/risk/me")
def me():
    """What the top bar needs: TEST or not, whether TRUST runs open (so people type their name), who you are."""
    person = g.person
    return jsonify(ok=True, test_env=publish.is_test_env(), env_label=publish.env_label(), open=person["open"],
                   name=person["name"], sam=person["sam"],
                   tech_risk=access.is_a_signed_in_tech_risk_person(person))


# ---------------------------------------------------------------------------------------------------
# The risks, drivers and questions, read only
# ---------------------------------------------------------------------------------------------------

@bp.get("/api/risk/registers")
def registers():
    """The risks, drivers and questions as the site reads them."""
    loaded = load_registers()
    drivers_list = [{"code": code, "field": rule["field"], "test": rule["test"], "value": rule["value"], "trigger": rule.get("trigger"),
                     "plain_name": rule.get("rationale") or code,
                     "answered_from": "data" if files.answered_from_data(rule) else "questionnaire"}
                    for code, rule in sorted(loaded["driver_rules"].items())]
    risks_list = [{"id": risk_id, "name": risk.get("name"), "domain": risk.get("domain"),
                   "category": risk.get("category"), "description": risk.get("description"),
                   "block": blocks.block_of(risk_id, risk, loaded["placements"]),
                   "likelihood_drivers": risk.get("likelihood_drivers") or [],
                   "impact_drivers": risk.get("impact_drivers") or []}
                  for risk_id, risk in sorted(loaded["risks"].items())]
    return jsonify(ok=True, risks=risks_list, drivers=drivers_list, questions=loaded["questions"],
                   settings=loaded["settings"], notes=loaded["notes"])


# ---------------------------------------------------------------------------------------------------
# Teams (the routes keep "groups" in their addresses)
# ---------------------------------------------------------------------------------------------------

def group_for_person(group_id, what):
    """The team, when this person may do `what` ("view", "answer" or "submit") on it. Otherwise raises. The one place
    that decides who may open a team (the sign-off and engine routes use it too)."""
    group = groups.find(group_id)
    if group is None:
        raise NoSuchGroup()
    rights = signoff.rights_with_signoff(g.person, group, groups.hr_month())      # sign-off: whoever signs off may open it
    if not rights[what]:
        said = {"view": "see", "answer": "answer the questions for", "submit": "submit"}[what]
        raise NotYourGroup(f"You can't {said} this team. Ask Tech Risk if you think you should.")
    return group, rights


def rows_of(group_id, rows):
    """The saved rows (answers, assessments or starts) that belong to one team, in the order they were saved."""
    return [row for row in rows if row["group_id"] == group_id]


def group_summary(group, month, answer_rows, assessment_rows, rights):
    """One team as the front page and the form's header show it."""
    status = signoff.group_status(group["id"], answer_rows, assessment_rows)      # adds Signed off and Sent back
    decision = signoff.short_summary(group["id"], assessment_rows, storage.risk_signoffs(group["id"]))
    return {"id": group["id"], "name": group["name"], "l3_id": group.get("l3_id"), "l3_name": group.get("l3_name"),
            "lead": groups.lead_name(group, month),
            "people": len(groups.members(group, month)),
            "status": status, "signoff": decision,
            "submitted_at": assessment_rows[-1]["at"] if assessment_rows else None,
            "assessments": len(assessment_rows),
            # No Elevated counts here (owner, 16 Nov 2026): this summary is listed beside other teams', and risk
            # results are never compared across teams. A team's results are on its own results page.
            "can": rights}


def is_one_of_my_teams(person, group):
    """True when the person is in this L4 team, or leads the L3 team it belongs to. Managers above, Tech Risk and
    readers are not "mine": they pick a team themselves. TRUST running open knows nobody, so nothing is "mine"."""
    if person["open"]:
        return False
    person_is_in_the_team = person["sam"] in group["members"]
    person_leads_the_l3_team = group["l3_id"] in person["lead_of"]
    return person_is_in_the_team or person_leads_the_l3_team


@bp.get("/api/risk/groups")
def list_groups():
    """The teams you may open, each with what the front page needs: where its form stands, the open (in progress)
    assessment if there is one, the last submitted date, and what you may do. No ratings or counts here."""
    month = groups.hr_month()
    form_questions = load_registers()["questions"]
    everything = {"answers": storage.risk_answers(), "assessments": storage.risk_assessments(), "starts": storage.risk_starts()}
    shown = []
    for group in groups.load():
        rights = signoff.rights_with_signoff(g.person, group, month)
        if not rights["view"]:
            continue
        answer_rows = rows_of(group["id"], everything["answers"])
        assessment_rows = rows_of(group["id"], everything["assessments"])
        start_rows = rows_of(group["id"], everything["starts"])
        summary = group_summary(group, month, answer_rows, assessment_rows, rights)
        summary["mine"] = is_one_of_my_teams(g.person, group)           # the front page puts the person's own teams first
        summary["open"] = home.open_assessment(form_questions, answer_rows, assessment_rows, start_rows, summary["status"])
        # What the team's newest submitted assessment stands at: Submitted, Signed off or Sent back.
        summary["results_status"] = None
        if assessment_rows:
            decision = summary["signoff"]
            summary["results_status"] = decision["state"] if decision else assess.SUBMITTED
        shown.append(summary)
    return jsonify(ok=True, groups=shown, hr_month=month,
                   note=None if groups.teams_in(month) else groups.NO_TEAMS_YET)


@bp.post("/api/risk/groups/<group_id>/start")
def start_assessment(group_id):
    """Start a new assessment for the team and record who and when. A team has one open assessment at a time, so when
    one is already open nothing is added and that one is returned (started: false). The form is pre-filled with the
    team's last answers because saved answers are kept."""
    group, _rights = group_for_person(group_id, "answer")
    body = request.get_json(silent=True) or {}
    who = trust_web()._who(body)
    answer_rows = storage.risk_answers(group_id)
    assessment_rows = storage.risk_assessments(group_id)
    status = signoff.group_status(group_id, answer_rows, assessment_rows)
    already = home.open_assessment(load_registers()["questions"], answer_rows, assessment_rows, storage.risk_starts(group_id), status)
    if already:
        return jsonify(ok=True, started=False, open=already)
    kept = storage.add_risk_start(group_id, who)
    return jsonify(ok=True, started=True, start={"by": kept["by"], "at": kept["at"]})


def question_with_answer(question, latest):
    saved = latest.get(question["field"]) or {}
    return {**question, "answer": saved.get("answer") or "", "by": saved.get("by"), "at": saved.get("at"),
            "from_tech_risk": saved.get("from_tech_risk", False)}


@bp.get("/api/risk/groups/<group_id>")
def one_group(group_id):
    """The form for one group: its sections, each question with the newest answer, who saved it and when."""
    group, rights = group_for_person(group_id, "view")
    loaded = load_registers()
    answer_rows = storage.risk_answers(group_id)
    assessment_rows = storage.risk_assessments(group_id)
    latest = assess.latest_answers(answer_rows)
    saved = assess.answer_text(latest)

    form_sections = [{"name": section["name"], "questions": [question_with_answer(q, latest) for q in section["questions"]]}
                     for section in question_list.sections(loaded["questions"])]
    # Each data driver: ON, OFF or not known, with its numbers, source and date (backend/trust/risk/data_drivers.py).
    answered_from_data = data_drivers.for_the_form(loaded["driver_rules"], group_id, loaded.get("from_files"))
    summary = group_summary(group, groups.hr_month(), answer_rows, assessment_rows, rights)
    return jsonify(ok=True, group=summary, sections=form_sections, answered_from_data=answered_from_data,
                   data_month=groups.hr_month(),
                   unanswered=len(question_list.unanswered(loaded["questions"], saved)),
                   questions=len(loaded["questions"]), notes=loaded["notes"])


@bp.post("/api/risk/groups/<group_id>/answers")
def save_answer(group_id):
    """Save one answer the moment it is changed: a new row (group, question, answer, who, when)."""
    group, _rights = group_for_person(group_id, "answer")
    body = request.get_json(silent=True) or {}
    who = trust_web()._who(body)
    loaded = load_registers()
    question = next((q for q in loaded["questions"] if q["field"] == str(body.get("question") or "")), None)
    if question is None:
        raise trust_web().Refused("That question isn't on the form.")
    answer = question_list.clean_answer(question, body.get("answer"))
    from_tech_risk = access.is_a_signed_in_tech_risk_person(g.person)
    row = storage.add_risk_answer(group_id, question["field"], answer, who, from_tech_risk)

    saved = assess.answer_text(assess.latest_answers(storage.risk_answers(group_id)))
    return jsonify(ok=True, saved=row, unanswered=len(question_list.unanswered(loaded["questions"], saved)),
                   status=signoff.group_status(group_id, storage.risk_answers(group_id), storage.risk_assessments(group_id)))


def submit_group(group, who, loaded):
    """Rate every risk for the group from its saved answers and keep the result as a new assessment."""
    saved = assess.answer_text(assess.latest_answers(storage.risk_answers(group["id"])))
    earlier = storage.risk_assessments(group["id"])
    previous_result = earlier[-1]["result"] if earlier else None
    data_answers = data_drivers.current(loaded["driver_rules"], loaded.get("from_files")).get(group["id"]) or {}
    result = data_drivers.assess_with_data(loaded["risks"], loaded["driver_rules"], loaded["questions"], saved,
                                           loaded["settings"], loaded["placements"], previous_result, data_answers)
    # Which copy of TRAC's controls was in use is only noted here (the first copy is fetched now, when there is none).
    # It changes no rating.
    controls_copy, _why_not = trac_controls.copy_in_use()
    result["controls_fetched_at"] = controls_copy["fetched_at"] if controls_copy else None
    return storage.add_risk_assessment(group["id"], who, result)


@bp.post("/api/risk/groups/<group_id>/submit")
def submit(group_id):
    """Submit the form. Questions with no answer are listed first; send confirm_unanswered: true to submit anyway."""
    group, _rights = group_for_person(group_id, "submit")
    body = request.get_json(silent=True) or {}
    who = trust_web()._who(body)
    loaded = load_registers()
    saved = assess.answer_text(assess.latest_answers(storage.risk_answers(group_id)))
    missing = question_list.unanswered(loaded["questions"], saved)
    if missing and body.get("confirm_unanswered") is not True:
        listed = [{"field": q["field"], "driver": q["driver"], "section": q["section"], "text": q["text"]} for q in missing]
        word = "question has" if len(missing) == 1 else "questions have"
        return jsonify(ok=False, unanswered=listed,
                       error=f"{len(missing)} {word} no answer yet. Answer them, or submit anyway."), 409
    kept = submit_group(group, who, loaded)
    return jsonify(ok=True, assessment_id=kept["id"], at=kept["at"], unanswered=len(missing),
                   counts=kept["result"]["counts"])


@bp.get("/api/risk/groups/<group_id>/assessment")
def assessment(group_id):
    """A group's newest assessment, or the one asked for with ?id=N, and the list of its earlier ones."""
    group, rights = group_for_person(group_id, "view")
    kept = current_rules.assessments(group_id)         # today's rating when rate_with_current_rules is on (current_rules.py)
    if not kept:
        summary = group_summary(group, groups.hr_month(), storage.risk_answers(group_id), [], rights)
        return jsonify(ok=True, assessment=None, earlier=[], group=summary)
    wanted = request.args.get("id", type=int)
    chosen = next((row for row in kept if row["id"] == wanted), None) if wanted else kept[-1]
    if chosen is None:
        raise trust_web().Refused("There is no such assessment for this team.")
    earlier = [{"id": row["id"], "at": row["at"], "by": row["by"], "elevated": row["result"]["counts"]["elevated"]}
               for row in reversed(kept)]
    summary = group_summary(group, groups.hr_month(), storage.risk_answers(group_id), kept, rights)
    # Where the rating and each data driver are worked out in the code. Read now, not kept with the assessment, so the lines stay true.
    shown = {key: value for key, value in chosen.items() if key != "kept_result"}
    shown = {**shown, "result": {**chosen["result"], "data_drivers": code_places.with_places(chosen["result"].get("data_drivers"))}}
    return jsonify(ok=True, assessment=shown, earlier=earlier, group=summary, code_places=code_places.rating_places(),
                   rated_with_current_rules=current_rules.line_for())


# ---------------------------------------------------------------------------------------------------
# Download in the engine's shape, and TRAC's controls
# ---------------------------------------------------------------------------------------------------

@bp.get("/api/risk/download")
def download_risks_and_drivers():
    """The risks and drivers as a .zip laid out like TRAC's content/engine/ folder. Whoever may open the Risk site may download it."""
    archive = download.build_zip(load_registers())
    return Response(archive, content_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="risks-and-drivers-{today_text()}.zip"'})


def controls_answer(copy, problem):
    """What the results page needs: the copy's dates, and for each risk the controls that address it."""
    return {"ok": True, "copy": None if copy is None else {"fetched_at": copy["fetched_at"], "published_at": copy["published_at"],
                                                           "controls": len(copy["controls"])},
            "by_risk": trac_controls.controls_by_risk(copy), "note": problem}


@bp.get("/api/risk/controls")
def controls():
    """The kept copy of TRAC's controls and the controls that address each risk. Nothing is fetched here: the first
    copy is fetched when a team submits, and Tech Risk can refresh it."""
    copy = storage.risk_controls_copy()
    problem = None if copy else "TRAC's list of controls has not been fetched yet."
    return jsonify(controls_answer(copy, problem))


@bp.post("/api/risk/controls/refresh")
def refresh_controls():
    """Tech Risk: fetch a new copy of TRAC's controls. If TRAC can't be reached the copy already kept stays in use."""
    if not access.may_act_as_tech_risk(g.person):
        raise trust_web().NotAllowed()
    who = trust_web()._who(request.get_json(silent=True) or {})
    try:
        copy = trac_controls.refresh()
    except trac_controls.CouldNotFetch as problem:
        return jsonify(ok=False, error=str(problem)), 502
    current_app.logger.info("TRAC's list of controls was refreshed by %s.", who)
    return jsonify({**controls_answer(copy, None), "refreshed_by": who})


# ---------------------------------------------------------------------------------------------------
# A product family's own risk results, for its own family page (owner, 16 Nov 2026)
# ---------------------------------------------------------------------------------------------------

@bp.get("/api/risk/family/<family_id>")
def family_results(family_id):
    """One family's own team and the Elevated risks of its newest assessment. Only for the family's own people, Tech
    Risk and the roles that see every family (the same people who may open that family's page). This is the family
    page's rule, not group_for_person's: a manager above a team may open the team, but is not the family's own people.
    Nothing is added up or compared between families."""
    person = g.person
    may_open_family = access.sees_all(person) or family_id in person["lead_of"] or family_id in person["member_of"]
    if not may_open_family:
        raise NotYourGroup("This team's risk results are for the team's own people and Tech Risk.")
    descriptions = {risk_id: tidy_spaces(risk.get("description"))
                    for risk_id, risk in load_registers()["risks"].items()}
    return jsonify(ok=True, **family_link.for_family(family_id, descriptions))


# ---------------------------------------------------------------------------------------------------
# Elevated risk markers on the CTO view (owner, 16 Nov 2026)
# ---------------------------------------------------------------------------------------------------

@bp.get("/api/cto/risk-markers")
def cto_risk_markers():
    """The Elevated risk markers: each team whose own newest assessment has an Elevated risk a metric watches. Read live.
    Only the teams the person may see. Display only: no score is touched."""
    return jsonify(cto_markers.answer_for(g.person))


# ---------------------------------------------------------------------------------------------------
# Team results pages (owner, 17 Nov 2026): the data, the insights and the CSV. Code: team_results.py
# ---------------------------------------------------------------------------------------------------

@bp.get("/api/risk/teams")
def team_list():
    """Every L3 team with its L4 teams, each with its status, date and counts. Open to everyone who can open the Risk site."""
    return jsonify(team_results.kept_list())





@bp.get("/api/risk/teams/<team_id>/results")
def team_page(team_id):
    """One L4 or L3 team's results: counts, insights, risks with their drivers, the driver summary. Open to everyone."""
    try:
        return jsonify(team_results.kept_results(team_id))
    except team_results.NotWorkedOut:
        return jsonify(ok=False, error=team_results.NOT_WORKED_OUT), 404
    except team_results.NoSuchTeam:
        return jsonify(ok=False, error="There is no such team."), 404


@bp.get("/api/risk/teams/<team_id>/results.csv")
def team_page_csv(team_id):
    """The team's results as a .csv: one row per risk and driver."""
    try:
        answer = team_results.kept_results(team_id)
    except team_results.NotWorkedOut:
        return jsonify(ok=False, error=team_results.NOT_WORKED_OUT), 404
    except team_results.NoSuchTeam:
        return jsonify(ok=False, error="There is no such team."), 404
    return Response(team_results.csv_text(answer), content_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{team_results.csv_file_name(answer)}"'})
