"""Why each "not known" driver is not known, in plain words, for Tech Risk (owner, 17 Nov 2026: "it shows 14 drivers
are not answered yet" after filling in the questionnaire).

Read only: nothing is saved and no rating changes. Used by  python manage.py risk_unknown  .
The reasons name the driver's own questions and data, never the rating rules, so they can be shared with a team.
"""
from trust.risk import drivers, files, questions as question_list, trigger_language


def fields_of(rule):
    """The answer fields a driver's rule reads, in the order written."""
    if rule.get("test") == drivers.MATCHES_TRIGGER:
        return trigger_language.fields_in_order(drivers.tree_of(rule["trigger"]))
    return [rule["field"]] if rule.get("field") else []


def reason(code, rule, form_questions, saved, data_results):
    """One sentence: why this driver has no ON or OFF for this team."""
    if files.answered_from_data(rule):
        found = (data_results or {}).get(code)
        if found and found.get("sentence"):
            return f"Answered from data: {found['sentence']}"
        return ("Answered from data, but no calculation answers it yet (the drivers file gives it no questionnaire "
                "field, so the form never asks it)")
    asked = {question["field"]: question for question in form_questions}
    answers = question_list.answers_by_field(form_questions, saved)
    fields = fields_of(rule)
    if not fields:
        return "Its rule reads no answer, so nothing can switch it on or off"
    missing = []
    for field in fields:
        if field not in asked:
            missing.append(f"no question on the form asks for {field} (not in the questionnaire, or switched off)")
        elif not question_list.is_answered(saved.get(field)):
            missing.append(f"the question for {field} wasn't answered")
        elif field not in answers:
            missing.append(f"the answer for {field} ('{saved.get(field)}') isn't read as a yes or a no")
    if missing:
        text = "; ".join(missing)
        return text[0].upper() + text[1:]
    if "prevailing" in str(rule.get("trigger") or rule.get("test") or ""):
        return "Every answer is in, but the rule compares it with other teams' answers, and too few teams have answered"
    return "Every answer is in, but the rule still can't be told on or off (worth a look on the Edit page)"


def reasons(not_known_codes, driver_rules, form_questions, saved, data_results):
    """{code: sentence} for each not-known driver."""
    return {code: reason(code, driver_rules[code], form_questions, saved or {}, data_results)
            for code in not_known_codes if code in driver_rules}
