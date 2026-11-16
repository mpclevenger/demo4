"""What the Risk site's front page shows for one team: is an assessment open, how far has it got, and what can the
person do. It only reads rows the caller gives it. Nothing here reads the database or rates anything.

An assessment is OPEN (in progress) for a team when, since the team's last Submit, any of these happened:
    - someone pressed Start (a risk_start row),
    - someone saved an answer (a risk_answer row),
    - or the last assessment was sent back.
There is at most one open assessment per team: Start does nothing when one is open.

A new assessment starts pre-filled: the team's answers are kept, so the newest saved answer of each question is
simply what the form shows. Each answer says when it was last confirmed (its own saved date).
"""
from trust.risk import assess, questions as question_list
from trust.risk.signoff import SENT_BACK
from trust.words import moment_of


def _after(rows, moment):
    """The rows saved after `moment` (all of them when moment is None), oldest first."""
    if moment is None:
        return list(rows)
    return [row for row in rows if moment_of(row["at"]) > moment_of(moment)]


def open_assessment(form_questions, answer_rows, assessment_rows, start_rows, status):
    """None when the team has no open assessment. Otherwise how it stands:

        {"status": "Draft" or "Sent back", "started": {"by", "at"} or None, "last_saved": {"by", "at"} or None,
         "answered": 12, "of": 17, "counted_as": "answered" or "confirmed or changed"}
    """
    last_submitted = assessment_rows[-1]["at"] if assessment_rows else None
    starts_since = _after(start_rows, last_submitted)
    answers_since = _after(answer_rows, last_submitted)
    is_open = bool(starts_since or answers_since or status == SENT_BACK)
    if not is_open:
        return None

    # Who started it: the newest Start; when nobody pressed Start (answers saved straight away), the first answer saved.
    if starts_since:
        started = {"by": starts_since[-1]["by"], "at": starts_since[-1]["at"]}
    elif answers_since:
        started = {"by": answers_since[0]["by"], "at": answers_since[0]["at"]}
    else:
        started = None

    # Who saved last: the newest answer or Start since the last Submit.
    saved_since = sorted(starts_since + answers_since, key=lambda row: moment_of(row["at"]))
    last_saved = {"by": saved_since[-1]["by"], "at": saved_since[-1]["at"]} if saved_since else None

    # Progress. First assessment: the questions answered. Later ones start pre-filled, so count the questions
    # answered, confirmed ("Still true") or changed since the last Submit.
    form_fields = {question["field"] for question in form_questions}
    latest_this_time = assess.latest_answers(answers_since)
    this_time = {field for field, saved in latest_this_time.items()
                 if field in form_fields and question_list.is_answered(saved["answer"])}
    latest_ever = assess.latest_answers(answer_rows)
    ever = {field for field, saved in latest_ever.items()
            if field in form_fields and question_list.is_answered(saved["answer"])}
    if last_submitted is None:
        answered, counted_as = len(ever), "answered"
    else:
        answered, counted_as = len(this_time), "confirmed or changed"
    return {"status": SENT_BACK if status == SENT_BACK else assess.DRAFT, "started": started, "last_saved": last_saved,
            "answered": answered, "of": len(form_questions), "counted_as": counted_as}
