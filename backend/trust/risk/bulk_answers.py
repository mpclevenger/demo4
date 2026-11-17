"""Questionnaire answers in bulk, as a CSV file (owner, 17 Nov 2026: "csv file please. it loads as a draft and it
should show as proposed so we can see the results").

    GET  /api/risk/answers.csv              every team's questions with their newest answers: fill in, upload back
    POST /api/risk/answers/check            read an uploaded CSV and say what would be saved; saves nothing
    POST /api/risk/answers/load             check again and save the answers as drafts (nothing is submitted)

One row per L4 team and question. Only the "answer" column is read back (with "team_id" and "question_code" to say
where it goes); the other columns are there to help the person filling it in. A blank answer leaves the saved answer as
it is. An answer the same as the saved one is skipped. Saved answers are drafts: the team (or Tech Risk) still submits
the form, and until then the team's results page shows the rating worked out from them as "Proposed".

Tech Risk only (anyone while TRUST runs open), the same people who upload the risk files.
"""
import csv
import io

from flask import Blueprint, Response, g, jsonify, request

from trust import access, storage
from trust.lazy_web import stop_data_senders, trust_web
from trust.risk import assess, groups, questions as question_list
from trust.risk.registers import load_registers

bp = Blueprint("risk_bulk_answers", __name__)
bp.before_request(stop_data_senders)

HEADINGS = ["team_id", "team", "l3_team", "l4_leader", "question_code", "section", "question", "answer_kind",
            "choices", "answer"]
KIND_WORDS = {question_list.YES_NO: "yes or no", question_list.NUMBER: "number", question_list.TEXT: "one of the choices",
              question_list.TICK_ANY: "any of the choices, separated by ;"}
LARGEST_CSV_BYTES = 5_000_000
UPLOAD_NOTE = "bulk upload"


def _safe(text):
    """A cell can't start a spreadsheet formula when the file is opened in Excel."""
    text = "" if text is None else str(text)
    return "'" + text if text[:1] in ("=", "+", "-", "@") and not _is_number(text) else text


def _is_number(text):
    try:
        float(text.replace("%", ""))
        return True
    except ValueError:
        return False


def _kind_word(question):
    if question["kind"] == question_list.NUMBER and question_list.is_share(question):
        return "share (25% or 0.25)"
    return KIND_WORDS.get(question["kind"], question["kind"])


def download_text(group_list, questions, answer_rows, month):
    """The CSV: one row per team and question, the newest saved answer filled in."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADINGS)
    by_group = {}
    for row in answer_rows:
        by_group.setdefault(row["group_id"], []).append(row)
    for group in sorted(group_list, key=lambda g_: (str(g_.get("l3_name") or ""), g_["name"])):
        saved = assess.answer_text(assess.latest_answers(by_group.get(group["id"], [])))
        lead = groups.lead_name(group, month) or ""
        for question in questions:
            writer.writerow([_safe(group["id"]), _safe(group["name"]), _safe(group.get("l3_name")), _safe(lead),
                             _safe(question["field"]), _safe(question.get("section")), _safe(question.get("text")),
                             _kind_word(question), _safe("; ".join(question.get("choices") or [])),
                             _safe(question_list.answer_as_text(saved.get(question["field"])))])
    return out.getvalue()


def read_upload(raw, group_list, questions, answer_rows):
    """What an uploaded CSV would save: {"changes": [...], "problems": [...], "counts": {...}}. Saves nothing.

    A change is {"group_id", "team", "field", "answer", "before", "row"}. Every row the file can't use is a problem
    in plain words with its row number; the rest can still be saved."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")              # saved from Excel on Windows
    reader = csv.DictReader(io.StringIO(text))
    names = {(name or "").strip().lower(): name for name in (reader.fieldnames or [])}
    missing = [name for name in ("team_id", "question_code", "answer") if name not in names]
    if missing:
        raise trust_web().Refused("This file is missing the column " + " and ".join(missing)
                                  + ". Start from the download on this page, fill in the answer column, and upload it back.")
    group_of = {group["id"]: group for group in group_list}
    question_of = {question["field"].lower(): question for question in questions}
    latest = {}
    for row in answer_rows:
        latest.setdefault(row["group_id"], []).append(row)
    saved_of = {group_id: assess.answer_text(assess.latest_answers(rows)) for group_id, rows in latest.items()}
    changes, problems, counts = [], [], {"rows": 0, "blank": 0, "same": 0, "to_save": 0, "teams": 0}
    seen = set()
    for number, row in enumerate(reader, start=2):                 # row 1 is the headings
        counts["rows"] += 1
        cell = lambda name: str(row.get(names[name]) or "").strip().lstrip("'")
        group_id, field, typed = cell("team_id"), cell("question_code"), cell("answer")
        if not typed:
            counts["blank"] += 1
            continue
        group = group_of.get(group_id)
        if group is None:
            problems.append(f"Row {number}: there is no team '{group_id}' now. Download the file again for the current teams.")
            continue
        question = question_of.get(field.lower())
        if question is None:
            problems.append(f"Row {number}: '{field}' isn't a question on the form (it may be switched off).")
            continue
        if (group_id, question["field"]) in seen:
            problems.append(f"Row {number}: {group['name']} answers {question['field']} twice in this file; the first one is used.")
            continue
        seen.add((group_id, question["field"]))
        try:
            answer = question_list.clean_answer(question, typed)
        except ValueError as problem:
            problems.append(f"Row {number}: {group['name']}, {question['field']}: {problem} (got '{typed[:60]}')")
            continue
        before = (saved_of.get(group_id) or {}).get(question["field"])
        if question_list.answer_as_text(answer) == question_list.answer_as_text(before):
            counts["same"] += 1
            continue
        changes.append({"group_id": group_id, "team": group["name"], "field": question["field"], "answer": answer,
                        "before": question_list.answer_as_text(before), "row": number})
    counts["to_save"] = len(changes)
    counts["teams"] = len({change["group_id"] for change in changes})
    return {"changes": changes, "problems": problems, "counts": counts}


def summary_of(counts, saved=False):
    words = (f"{counts['to_save']} {'answer' if counts['to_save'] == 1 else 'answers'} {'saved' if saved else 'to save'} for "
             f"{counts['teams']} {'team' if counts['teams'] == 1 else 'teams'}")
    extra = []
    if counts["same"]:
        extra.append(f"{counts['same']} already saved")
    if counts["blank"]:
        extra.append(f"{counts['blank']} blank (left as they are)")
    return words + (f"; {', '.join(extra)}" if extra else "") + "."


# ---------------------------------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------------------------------

def stop_unless_tech_risk():
    if not access.may_act_as_tech_risk(g.person):
        raise trust_web().NotAllowed()


def _uploaded():
    sent = request.files.get("file")
    if sent is None:
        raise trust_web().Refused("Choose the CSV file first.")
    raw = sent.read(LARGEST_CSV_BYTES + 1)
    if len(raw) > LARGEST_CSV_BYTES:
        raise trust_web().Refused("This file is too big. Split it into a few files of fewer teams.")
    return raw, trust_web()._who({"by": request.form.get("by")})


@bp.get("/api/risk/answers.csv")
def download():
    stop_unless_tech_risk()
    loaded = load_registers()
    month = groups.hr_month()
    text = download_text(groups.load(), loaded["questions"], storage.risk_answers(), month)
    return Response("﻿" + text, content_type="text/csv; charset=utf-8",          # the mark lets Excel read accents
                    headers={"Content-Disposition": f'attachment; filename="questionnaire-answers-{month or "teams"}.csv"'})


@bp.post("/api/risk/answers/check")
def check():
    stop_unless_tech_risk()
    raw, _who = _uploaded()
    loaded = load_registers()
    found = read_upload(raw, groups.load(), loaded["questions"], storage.risk_answers())
    return jsonify(ok=True, summary=summary_of(found["counts"]), counts=found["counts"], problems=found["problems"],
                   changes=found["changes"][:200], more=max(0, len(found["changes"]) - 200))


@bp.post("/api/risk/answers/load")
def load():
    stop_unless_tech_risk()
    raw, who = _uploaded()
    loaded = load_registers()
    found = read_upload(raw, groups.load(), loaded["questions"], storage.risk_answers())
    from_tech_risk = access.is_a_signed_in_tech_risk_person(g.person)
    for change in found["changes"]:
        storage.add_risk_answer(change["group_id"], change["field"], change["answer"], f"{who} ({UPLOAD_NOTE})", from_tech_risk)
    storage.log("risk answers upload", who, None, summary_of(found["counts"], saved=True),
                {"teams": sorted({change["group_id"] for change in found["changes"]}), "answers": len(found["changes"])})
    return jsonify(ok=True, summary=summary_of(found["counts"], saved=True), counts=found["counts"], problems=found["problems"])
