"""Metric intake: the record a metric follows from Wanted to Measured, and the standard layout a team sends its
numbers in. Registered at the end of web.py.

  GET  /api/metric-intake            Tech Risk: the records, their history, and what was received per month.
  GET  /api/metric-intake/<id>/<month>   one record's month: the rows kept and set aside.
  POST /api/metric-intake            Tech Risk: add a record, change one, or move its stage.
  POST /api/metric-values            a team's service account (or Tech Risk) sends numbers, as JSON or a CSV file.

A record counts in no score. Sending numbers stores them and nothing more: no score changes and no metric reaches
the scorecard. The checks are in metric_intake_rules.py; this file is the doors and the record keeping.
"""
import csv
import io

from flask import Blueprint, g, jsonify, request

from . import access, score_month, storage
from . import metric_intake_rules as rules
from .lazy_web import trust_web
from .words import tidy_spaces

bp = Blueprint("metric_intake", __name__)

MAX_SET_ASIDE_SHOWN = 500          # rows set aside listed per month on the page
MAX_ROWS_SHOWN = 500               # kept rows listed per month on the page


def block_names():
    """The six building blocks, by name, from the scorecard's own definitions."""
    return [b["name"] for b in score_month.template().get("blocks", [])]


# ---- what the page is shown ----

def public_record(record):
    """One record as the page reads it: its fields side by side, plus what it still needs for In progress."""
    fields = rules.with_defaults(record["fields"])
    return {"id": record["id"], "stage": record["stage"], **fields,
            "created_at": record["created_at"], "created_by": record["created_by"],
            "changed_at": record["changed_at"], "changed_by": record["changed_by"],
            "missing_for_in_progress": rules.missing_fields(fields, rules.IN_PROGRESS)}


def received_summary(sends):
    """What was received for each month, newest send first: {month: {latest send's summary, sends: how many}}."""
    by_month = {}
    for send in sends:
        by_month.setdefault(send["month"], []).append(send)
    summary = {}
    for month, month_sends in by_month.items():
        latest = month_sends[-1]
        summary[month] = {"send_id": latest["id"], "at": latest["at"], "by": latest["by"], "shape": latest["shape"],
                          "rows_kept": latest["kept_count"], "rows_set_aside": latest["set_aside_count"],
                          "set_aside": latest["rows_set_aside"][:MAX_SET_ASIDE_SHOWN],
                          "teams": len(latest["totals"]), "totals": latest["totals"],
                          "sends": len(month_sends),
                          "earlier": [{"send_id": s["id"], "at": s["at"], "by": s["by"], "rows_kept": s["kept_count"],
                                       "rows_set_aside": s["set_aside_count"]} for s in reversed(month_sends[:-1])]}
    return summary


def choices():
    """The lists the forms offer, so the page and the checks never disagree."""
    return {"stages": list(rules.STAGES), "building_blocks": block_names(), "units": list(rules.UNITS),
            "directions": rules.DIRECTIONS, "key_types": list(rules.KEY_TYPES), "shapes": rules.SHAPES,
            "cadences": rules.CADENCES, "arrivals": rules.ARRIVALS,
            "wanted_fields": [{"key": k, "label": label} for k, label in rules.WANTED_FIELDS],
            "in_progress_fields": [{"key": k, "label": label} for k, label in rules.IN_PROGRESS_FIELDS],
            "columns": {shape: list(columns) for shape, columns in rules.COLUMNS_OF.items()}}


@bp.get("/api/metric-intake")
def intake_list():
    """Tech Risk (and auditors, read only): every record, every change, and what was received."""
    web = trust_web()
    web.require("console_read")
    records = storage.intake_records()
    history = {}
    for row in storage.intake_history():
        history.setdefault(row["code"], []).append(row)
    sends = {}
    for send in storage.intake_sends():
        sends.setdefault(send["intake_id"], []).append(send)
    received = {record["id"]: received_summary(sends.get(record["id"], [])) for record in records}
    return jsonify(ok=True, records=[public_record(r) for r in records], history=history, received=received,
                   choices=choices(), can_edit=access.can(g.person, "run_month"))


@bp.get("/api/metric-intake/<code>/<month>")
def intake_month(code, month):
    """One record's month: the numbers per team and the rows kept (the newest send), and every send."""
    web = trust_web()
    web.require("console_read")
    record = storage.intake_record(code)
    if record is None:
        raise web.Refused(f"There is no metric {code}.")
    sends = storage.intake_sends(code, month)
    if not sends:
        raise web.Refused(f"Nothing has been received for {code} in {month}.")
    latest = sends[-1]
    return jsonify(ok=True, intake_id=code, month=month, shape=latest["shape"], at=latest["at"], by=latest["by"],
                   totals=latest["totals"], rows_kept=latest["rows_kept"][:MAX_ROWS_SHOWN],
                   rows_kept_count=latest["kept_count"], rows_set_aside=latest["rows_set_aside"][:MAX_SET_ASIDE_SHOWN],
                   rows_set_aside_count=latest["set_aside_count"],
                   sends=[{"send_id": s["id"], "at": s["at"], "by": s["by"], "rows_kept": s["kept_count"],
                           "rows_set_aside": s["set_aside_count"]} for s in reversed(sends)])


# ---- add a record, change one, move its stage ----

def _changed_fields(before, after):
    """{field: (was, now)} for the fields whose value differs."""
    return {key: (before.get(key, ""), after.get(key, "")) for key in rules.ALL_FIELD_KEYS
            if before.get(key, "") != after.get(key, "")}


def _refuse_if_missing(missing, intro):
    if missing:
        raise trust_web().Refused(f"{intro} {'; '.join(missing)}.")


@bp.post("/api/metric-intake")
def intake_save():
    """Add a record (no id), or change a record and/or move its stage (with its id). Tech Risk only."""
    web = trust_web()
    web.require("run_month")
    body = request.get_json(silent=True) or {}
    by = web._who(body)
    note = tidy_spaces(body.get("note"))[:rules.MAX_NOTE_LENGTH]
    given = body.get("fields") if isinstance(body.get("fields"), dict) else {}
    fields_in = rules.tidy_fields(given)
    code = tidy_spaces(body.get("id")).upper()
    problems = rules.problems_with_values(fields_in, block_names())
    if problems:
        raise web.Refused(" ".join(problems))
    if not code:
        return add_record(body, fields_in, note, by)
    return change_or_move_record(code, body, fields_in, note, by)


def add_record(body, fields_in, note, by):
    """Add a record. A new record always starts as Wanted."""
    if body.get("stage") not in (None, "", rules.WANTED):
        raise trust_web().Refused("A new metric starts as Wanted. Move it on once it is added.")
    _refuse_if_missing(rules.missing_fields(fields_in, rules.WANTED), "To add a metric, fill in:")
    record = storage.intake_add(rules.with_defaults(fields_in), by)
    storage.intake_history_add(record["id"], by, "added", note, None, {"stage": rules.WANTED, **record["fields"]})
    return jsonify(ok=True, record=public_record(record),
                   message=f"Added {record['id']} as Wanted. It counts in no score.")


def change_or_move_record(code, body, fields_in, note, by):
    """Change a record's fields, move it to another stage, or both. The history gets one line for each."""
    web = trust_web()
    record = storage.intake_record(code)
    if record is None:
        raise web.Refused(f"There is no metric {code}.")
    current_stage = record["stage"]
    target_stage = tidy_spaces(body.get("stage")) or current_stage
    merged = rules.with_defaults({**record["fields"], **fields_in})
    changes = _changed_fields(record["fields"], merged)
    moving = target_stage != current_stage

    for locked_key in ("shape", "key_type"):               # numbers already received would no longer fit
        if locked_key in changes and changes[locked_key][0] and storage.intake_sends(code):
            raise web.Refused(f"Numbers have already been received for {code}, so its {rules.FIELD_LABELS[locked_key].lower()} "
                              "can't change now. Add a new metric instead.")
    problem = rules.move_problem(current_stage, target_stage, merged)
    if problem:
        raise web.Refused(problem)
    if not moving:
        _refuse_if_missing(rules.missing_fields(merged, current_stage), "These can't be left empty:")
    if moving and target_stage == rules.MEASURED and not note:
        raise web.Refused("Measured is set by hand after the usual metric approval. Say which approval in the note, "
                          "so the record shows it. (This doesn't create the metric.)")
    if not changes and not moving:
        return jsonify(ok=True, record=public_record(record), message="Nothing changed.")

    saved = storage.intake_update(code, target_stage, merged, by)
    if changes:
        storage.intake_history_add(code, by, "changed", note,
                                   {k: was for k, (was, _) in changes.items()}, {k: now for k, (_, now) in changes.items()})
    if moving:
        storage.intake_history_add(code, by, "moved", note, {"stage": current_stage}, {"stage": target_stage})
    message = f"Moved {code} to {target_stage}." if moving else f"Saved the changes to {code}."
    if moving and target_stage == rules.MEASURED:
        message += " This only records the stage. It does not create a metric or change any score."
    return jsonify(ok=True, record=public_record(saved), message=message)


# ---- a team sends its numbers ----

def _rows_from_csv(raw_bytes):
    """The rows of a CSV file: comma, semicolon, tab or pipe delimited, with or without a byte-order mark."""
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    first_lines = "\n".join(text.splitlines()[:5])
    try:
        dialect = csv.Sniffer().sniff(first_lines, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [{k: v for k, v in row.items() if k} for row in reader if any((v or "").strip() for v in row.values())]


def _the_send_from_the_request():
    """(intake_id, month, shape, rows, who-body) from a JSON body, or from a CSV file in the field `file`.
    A CSV may leave intake_id and month to its rows."""
    web = trust_web()
    upload = request.files.get("file")
    if upload is not None:
        rows = _rows_from_csv(upload.read())
        asked = request.form
        body_for_name = request.form
    else:
        asked = request.get_json(silent=True)
        if not isinstance(asked, dict):
            raise web.Refused("Send a JSON body like {\"intake_id\": \"MI-001\", \"month\": \"2026-10\", "
                              "\"shape\": \"totals\", \"rows\": [...]}, or a CSV file in the field 'file'.")
        rows = asked.get("rows")
        body_for_name = asked
    if not isinstance(rows, list) or not rows:
        raise web.Refused("There are no rows in this send. Put the rows in the 'rows' list, or send a CSV file with a header row and at least one row.")
    if len(rows) > rules.MAX_ROWS_IN_ONE_SEND:
        raise web.Refused(f"That is more than {rules.MAX_ROWS_IN_ONE_SEND} rows in one send. Please send it in smaller parts.")
    if not all(isinstance(row, dict) for row in rows):
        raise web.Refused("Each row must be an object with the column names, like {\"key\": \"APP-1\", \"count\": 3, ...}.")
    first = rules.normalize_row(rows[0])
    intake_id = tidy_spaces(asked.get("intake_id")) or first.get("intake_id", "")
    month = tidy_spaces(asked.get("month")) or first.get("month", "")
    shape = tidy_spaces(asked.get("shape")).lower()
    return intake_id.upper(), month, shape, rows, body_for_name


def _sender_problem(record):
    """Why this person may not send for this record, or None. With roles on, a data sender's own account must be the
    service account on the record; Tech Risk is exempt. While TRUST runs open, anyone may send."""
    person = g.person
    if access.may_act_as_tech_risk(person):
        return None
    named = rules.user_name_only(record["fields"].get("service_account", ""))
    if not named:
        return f"{record['id']} has no service account named yet, so only Tech Risk can send for it. Ask Tech Risk to add it."
    if person["sam"] != named:
        return (f"You are signed in as {person['sam']}, which is not the service account named on {record['id']}. "
                "Numbers for a metric are accepted only from its own service account. Ask Tech Risk to check the record.")
    return None


@bp.post("/api/metric-values")
def send_values():
    """Receive a team's numbers: check every row, keep the good ones and set the rest aside with the reason, and
    store the send. Nothing is scored."""
    web = trust_web()
    web.require("send_metric_values")
    intake_id, month, shape, rows, body_for_name = _the_send_from_the_request()
    record = storage.intake_record(intake_id)
    problem = rules.record_can_receive(record, intake_id)
    if record is None:
        raise web.Refused(problem)
    # The sender is checked before the record's own problem (say, a Wanted record that can't receive numbers yet), so
    # a person who may not send for this record is not told about the record's state.
    sender_problem = _sender_problem(record)
    if sender_problem:
        return jsonify(ok=False, error=sender_problem), 403
    if problem:
        raise web.Refused(problem)
    by = web._who(body_for_name)
    if not rules.month_is_well_formed(month):
        raise web.Refused(f"month must be written like 2026-10 (it was '{month}').")
    record_shape = record["fields"].get("shape", "")
    if shape and shape != record_shape:
        raise web.Refused(f"{intake_id} is set up for the {rules.SHAPES.get(record_shape, record_shape)} shape, "
                          f"but this send says '{shape}'. Send it in the {rules.SHAPES.get(record_shape, record_shape)} shape.")

    kept, set_aside, totals = rules.check_rows(record_shape, rows, record["fields"], intake_id, month)
    set_aside_listed = [{"row_number": s["row_number"], "reason": s["reason"], "row": s["row"]} for s in set_aside]
    if not kept:
        return jsonify(ok=False, error="None of the rows could be kept, so nothing was stored. The reasons are listed below.",
                       intake_id=intake_id, month=month, rows_received=len(rows), rows_kept=0,
                       rows_set_aside=len(set_aside), set_aside=set_aside_listed), 400
    replaced = bool(storage.intake_sends(intake_id, month))
    stored = storage.intake_send_add({"intake_id": intake_id, "month": month, "shape": record_shape, "by": by,
                                      "rows_kept": kept, "rows_set_aside": set_aside_listed, "totals": totals})
    return jsonify(ok=True, message=rules.summary_sentence(len(kept), len(set_aside), replaced), intake_id=intake_id,
                   month=month, shape=record_shape, send_id=stored["id"], received_at=stored["at"], received_from=by,
                   rows_received=len(rows), rows_kept=len(kept), rows_set_aside=len(set_aside),
                   set_aside=set_aside_listed, totals=totals, replaced_earlier_send=replaced, scored=False)
