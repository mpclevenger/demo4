"""The Risk site: uploads that seed the risks, drivers and questionnaire (see docs/design/21_risk_site.md, "Uploading the risk files").
Registered at the end of web.py.

    GET  /api/risk/seed                     what the site holds now, the earlier uploads, the kept copy of TRAC's controls
    POST /api/risk/seed/<kind>/check        read the files and say what was found (kind: risks, drivers or questions)
    POST /api/risk/seed/<kind>/preview      the same, and which teams' newest ratings would change; saves nothing
    POST /api/risk/seed/<kind>/load         check again and load; the site is then where those registers come from

Files go in a form (field "file", more than one allowed) with "by". Every POST needs the header X-TRUST: 1, and a name
while TRUST runs open. Tech Risk loads (anyone while TRUST runs open), decided the way the editing lists decide it.
"""
import logging

from flask import Blueprint, g, jsonify, request

from trust import access, storage
from trust.lazy_web import stop_data_senders, trust_web
from trust.risk import registers, seed, trac_controls

bp = Blueprint("risk_seed", __name__)
bp.before_request(stop_data_senders)

MOST_UPLOAD_BYTES = 20_000_000
log = logging.getLogger(__name__)


def read_safely(step, *args):
    """Run one reading step (check, preview or load). A file the checks didn't expect gets a plain answer, never a
    server error page; the full error goes to the log so the reader can be taught the new shape."""
    try:
        return step(*args)
    except (trust_web().Refused, trust_web().NotAllowed):
        raise
    except Exception as trouble:
        log.exception("A risk upload could not be read")
        raise trust_web().Refused("This file has something the page doesn't know how to read yet, so nothing was "
                                  "saved. Send the file (or one risk from it) to whoever looks after TRUST, with this "
                                  f"note: {type(trouble).__name__}: {str(trouble)[:200]}") from trouble


EARLIER_UPLOADS_SHOWN = 30


def may_upload():
    """Tech Risk, and everyone while TRUST runs open: the same people who may save the editing lists."""
    return access.may_act_as_tech_risk(g.person)


def stop_unless_allowed():
    if not may_upload():
        raise trust_web().NotAllowed()


def uploaded_files():
    """The files in the form as [(name, bytes)], and who is uploading."""
    uploads = []
    total = 0
    for sent in request.files.getlist("file"):
        raw = sent.read(seed.LARGEST_FILE_BYTES * 2 + 1)
        total += len(raw)
        uploads.append((sent.filename or "file", raw))
    if total > MOST_UPLOAD_BYTES:
        raise trust_web().Refused("These files are too big to read together. Upload fewer at a time.")
    who = trust_web()._who({"by": request.form.get("by")})
    return uploads, who


def held_now():
    """How many risks, drivers and questions the site holds, and where the risks and drivers come from."""
    loaded = registers.load_registers()
    uploaded_risks, uploaded_drivers = registers.uploaded_registers()
    return {"risks": len(loaded["risks"]), "drivers": len(loaded["driver_rules"]), "questions": len(loaded["questions"]),
            "risks_from": "an upload" if uploaded_risks is not None else "the risk files folder",
            "drivers_from": "an upload" if uploaded_drivers is not None else "the risk files folder"}


def controls_now():
    """The kept copy of TRAC's controls (never fetched here), for the Refresh button's line."""
    copy = storage.risk_controls_copy()
    return {"copy": None if copy is None else {"fetched_at": copy["fetched_at"], "published_at": copy["published_at"],
                                               "controls": len(copy["controls"])},
            "trac_address_set": bool(trac_controls.trac_url())}


@bp.get("/api/risk/seed")
def seed_status():
    earlier = [{"id": row["id"], "at": row["at"], "by": row["by"], "kind": row["kind"], "file_name": row["file_name"],
                "file_hash": row["file_hash"], "summary": (row["read"] or {}).get("summary")}
               for row in reversed(storage.risk_seed_uploads())][:EARLIER_UPLOADS_SHOWN]
    try:
        mapping = seed.read_map()
        mapping_problem = None
    except ValueError as trouble:
        mapping, mapping_problem = None, str(trouble)
    return jsonify(ok=True, can_upload=may_upload(), held=held_now(), earlier=earlier, controls=controls_now(),
                   mapping={"file": f"config/{seed.MAP_FILE_NAME}", "content": mapping, "problem": mapping_problem})


@bp.post("/api/risk/seed/<kind>/check")
def seed_check(kind):
    stop_unless_allowed()
    uploads, _who = uploaded_files()
    result, _applying = read_safely(seed.check, kind, uploads)
    return jsonify(ok=True, **result)


@bp.post("/api/risk/seed/<kind>/preview")
def seed_preview(kind):
    stop_unless_allowed()
    uploads, _who = uploaded_files()
    return jsonify(ok=True, **read_safely(seed.preview, kind, uploads))


@bp.post("/api/risk/seed/<kind>/load")
def seed_load(kind):
    stop_unless_allowed()
    uploads, who = uploaded_files()
    result = read_safely(seed.load, kind, uploads, who)
    return jsonify(ok=True, held=held_now(), **result)
