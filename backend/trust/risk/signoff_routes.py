"""The Risk site: sign-off routes (docs/design/21_risk_site.md, "Sign-off"). Registered at the end of web.py.

    GET  /api/risk/groups/<id>/signoff    who should sign off, the status, whether you may, and every decision so far
    POST /api/risk/groups/<id>/signoff    {"note", "by"}            sign the newest assessment off
    POST /api/risk/groups/<id>/sendback   {"reason", "by"}          send it back to the team, with the reason
    POST /api/risk/groups/<id>/delegate   {"delegate_sam", "by"}    a lead names who signs off for them ("" clears it)

Every POST needs the header X-TRUST: 1 (web.py checks it). While TRUST runs open, "by" is the typed name.
"""
from flask import Blueprint, g, jsonify, request

from trust import storage
from trust.lazy_web import stop_data_senders, trust_web
from trust.risk import assess, groups, signoff, site
from trust.words import tidy_spaces

bp = Blueprint("risk_signoff", __name__)
bp.before_request(stop_data_senders)


def _clean_note(text, what):
    """The note or reason, one tidy line of words. Required."""
    note = tidy_spaces(text)
    if not note:
        raise trust_web().Refused(f"Write {what} first.")
    if len(note) > signoff.NOTE_LONGEST:
        raise trust_web().Refused(f"That is too long ({signoff.NOTE_LONGEST} characters at most). Please shorten it.")
    return note


def _decide(group_id, kind, note_text, note_name, body):
    """Sign off or send back the newest assessment. Returns the answer to send."""
    group, _rights = site.group_for_person(group_id, "view")          # only a person who may open the team may decide on it
    signer = trust_web()._who(body)
    month = groups.hr_month()
    rows = storage.risk_signoffs(group_id)
    allowed, why_not = signoff.may_sign_off(g.person, group, month, rows)
    if not allowed:
        raise site.NotYourGroup(why_not)

    answer_rows = storage.risk_answers(group_id)
    assessment_rows = storage.risk_assessments(group_id)
    status = signoff.status_of(group_id, answer_rows, assessment_rows, rows)
    if status == assess.NOT_STARTED or not assessment_rows:
        raise trust_web().Refused("Nothing has been submitted for this team yet, so there is nothing to sign off.")
    if status == signoff.SIGNED_OFF:
        raise trust_web().Refused("The newest assessment is already signed off.")
    if status == signoff.SENT_BACK:
        raise trust_web().Refused("The newest assessment was sent back. It can be signed off once the team submits again.")
    if status == assess.DRAFT:
        raise trust_web().Refused("Answers have changed since the last Submit. The team needs to submit again before it can be signed off.")

    note = _clean_note(note_text, note_name)
    newest = assessment_rows[-1]
    changed = signoff.answers_changed_by(signer, newest, assessment_rows, answer_rows) if kind == signoff.SIGNOFF else 0
    kept = storage.add_risk_signoff({"kind": kind, "group_id": group_id, "assessment_id": newest["id"], "by": signer,
                                     "signer_sam": g.person["sam"], "note": note,
                                     "also_changed": changed > 0, "changed_answers": changed})
    new_status = signoff.group_status(group_id, answer_rows, assessment_rows)
    return {"ok": True, "status": new_status, "decision": kept,
            "flag": signoff.flag_sentence(signer, changed) if changed else None}


@bp.get("/api/risk/groups/<group_id>/signoff")
def show(group_id):
    group, _rights = site.group_for_person(group_id, "view")
    month = groups.hr_month()
    rows = storage.risk_signoffs(group_id)
    answer_rows = storage.risk_answers(group_id)
    assessment_rows = storage.risk_assessments(group_id)
    status = signoff.status_of(group_id, answer_rows, assessment_rows, rows)
    who = signoff.who_signs(group, month, rows)
    may, why_not = signoff.may_sign_off(g.person, group, month, rows)
    may_delegate, why_no_delegate = signoff.may_name_a_delegate(g.person, group, month, rows)
    waiting = bool(assessment_rows) and status == assess.SUBMITTED
    newest_decision = signoff.decision_on(assessment_rows[-1]["id"], group_id, rows) if assessment_rows else None
    return jsonify(ok=True, status=status, open=g.person["open"], who=who,
                   can_sign_off=may and waiting, may_sign_off=may, why_not=None if may else why_not,
                   can_name_delegate=may_delegate and bool(who["leads"]),
                   why_no_delegate=None if may_delegate and who["leads"] else (why_no_delegate or None),
                   waiting=waiting,
                   sent_back_reason=newest_decision["note"] if newest_decision and newest_decision["kind"] == signoff.SENDBACK else None,
                   history=signoff.history(group_id, assessment_rows, rows))


@bp.post("/api/risk/groups/<group_id>/signoff")
def sign_off(group_id):
    body = request.get_json(silent=True) or {}
    return jsonify(_decide(group_id, signoff.SIGNOFF, body.get("note"), "a short note for the sign-off", body))


@bp.post("/api/risk/groups/<group_id>/sendback")
def send_back(group_id):
    body = request.get_json(silent=True) or {}
    return jsonify(_decide(group_id, signoff.SENDBACK, body.get("reason"), "the reason for sending it back", body))


@bp.post("/api/risk/groups/<group_id>/delegate")
def name_delegate(group_id):
    """A lead names who signs off for them, or clears it with an empty delegate_sam. It covers all of that lead's teams.
    Tech Risk (or anyone, while TRUST runs open) names one for every lead of the team."""
    group, _rights = site.group_for_person(group_id, "view")
    body = request.get_json(silent=True) or {}
    namer = trust_web()._who(body)
    month = groups.hr_month()
    rows = storage.risk_signoffs(group_id)
    allowed, why_not = signoff.may_name_a_delegate(g.person, group, month, rows)
    if not allowed:
        raise site.NotYourGroup(why_not)
    speaking_for = signoff.leads_this_person_speaks_for(g.person, group, month)
    if not speaking_for:
        raise trust_web().Refused("We couldn't find who leads this team, so there is nobody to name a delegate for.")

    delegate_sam = str(body.get("delegate_sam") or "").strip().lower()
    if delegate_sam:
        if delegate_sam in {lead["sam"] for lead in speaking_for}:
            raise trust_web().Refused("That is the lead already. Name someone else, or leave it empty to clear the delegate.")
        if delegate_sam not in groups.names_of_people(month):
            raise trust_web().Refused(f"{delegate_sam} isn't in the HR data. Check the SAM_ACCOUNT and try again.")
    kept = None
    for lead in speaking_for:
        kept = storage.add_risk_signoff({"kind": signoff.DELEGATE, "group_id": group_id, "by": namer, "signer_sam": g.person["sam"],
                                         "l3_sam": lead["sam"], "delegate_sam": delegate_sam or None})
    who = signoff.who_signs(group, month, storage.risk_signoffs(group_id))
    return jsonify(ok=True, decision=kept, who=who)
