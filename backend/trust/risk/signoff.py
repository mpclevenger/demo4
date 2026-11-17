"""Sign-off on the Risk site (owner, 16 Nov 2026: whoever leads the unit being assessed signs off).

After a group submits, the team's lead signs the assessment off, or sends it back with a reason.

    Who signs off      The L4 leader (owner, 17 Nov 2026): the one HR person at level l3_level + 1 the group is built
                       around (groups.py). Each L4 team signs off its own assessment. A lead may name a delegate, who may sign off too.
                       If no lead is found, Tech Risk signs off. Tech Risk may always sign off.
    Status words       Not started, Draft, Submitted, Signed off, Sent back.
    The flag           When the person signing off also changed answers in this assessment, the sign-off carries a
                       flag. It never blocks the sign-off.
    While TRUST runs open (access not set up), anyone may sign off, with a typed name.

Every decision is a row that is never edited (storage.add_risk_signoff). The newest decision on an assessment stands.
Nothing here changes how a risk is rated.
"""
import re

from trust import access, storage
from trust.risk import assess, groups
from trust.words import count_of, moment_of, tidy_spaces

SIGNED_OFF = "Signed off"
SENT_BACK = "Sent back"
REPLACED = "Replaced by a newer submit"
NOTE_LONGEST = 500

SIGNOFF = "signoff"
SENDBACK = "sendback"
DELEGATE = "delegate"


# ---------------------------------------------------------------------------------------------------
# Who is who, from the people TRUST already holds
# ---------------------------------------------------------------------------------------------------

def leads_of_group(group, month):
    """[{"sam", "name"}, ...] for the team's lead or leads, or [] when none can be found.

    The group is a TRUST team, and TRUST knows its leads (groups.py): the one person the team is built around. This only adds their names."""
    if month is None:
        return []
    name_of = groups.names_of_people(month)
    return [{"sam": lead_sam, "name": name_of.get(lead_sam, lead_sam)} for lead_sam in group["leads"]]


def delegate_of_lead(lead_sam, rows):
    """The SAM_ACCOUNT the lead named to sign off for them, or None (nobody named, or the delegate was cleared).
    rows are the sign-off rows, oldest first; the newest delegate row of this lead stands.
    (The row keeps the lead in its l3_sam column; the column was named before leads were.)"""
    chosen = None
    for row in rows:
        if row["kind"] == DELEGATE and (row["l3_sam"] or "").lower() == (lead_sam or "").lower():
            chosen = (row["delegate_sam"] or "").lower() or None
    return chosen


def leads_this_person_speaks_for(person, group, month):
    """The leads this person may name a delegate for: themself when they are a lead; every lead for Tech Risk;
    every lead while TRUST runs open."""
    leads = leads_of_group(group, month)
    if person["open"] or access.is_tech_risk(person):
        return leads
    return [lead for lead in leads if lead["sam"] == person["sam"]]


def _who_leads_words(group, leads):
    """Plain words for who the lead is, by how TRUST groups its teams."""
    names = " or ".join(lead["name"] for lead in leads)
    if group.get("grouping") == "l4":
        return f"{names} leads this L4 team in HR, so {names} signs this off."
    if group.get("grouping") == "l3":
        return f"{names} leads this team in HR, so {names} signs this off."
    if len(leads) == 1:
        return f"The L3 team owner, {names}, signs this off."
    return f"An L3 team owner signs this off: {names}. Any one of them can sign it off or send it back."


def who_signs(group, month, rows):
    """Who should sign this group off, and who else may.

    Returns {"leads", "delegates", "first", "sentence"}; leads and delegates are lists of {"sam", "name"};
    `first` says whose job it is: "lead" or "tech_risk"."""
    names = groups.names_of_people(month)
    leads = leads_of_group(group, month)
    delegates = []
    for lead in leads:
        delegate_sam = delegate_of_lead(lead["sam"], rows)
        if delegate_sam:
            delegates.append({"sam": delegate_sam, "name": names.get(delegate_sam, delegate_sam)})
    if leads:
        first = "lead"
        sentence = _who_leads_words(group, leads)
        if delegates:
            sentence += " " + " and ".join(delegate["name"] for delegate in delegates) + " may sign it off for them."
        sentence += " Tech Risk may too."
    else:
        first = "tech_risk"
        sentence = "We couldn't find who leads this team, so Tech Risk signs this off."
    return {"leads": leads, "delegates": delegates, "first": first, "sentence": sentence}


def may_sign_off(person, group, month, rows):
    """(True, "") when this person may sign off or send back this group's assessment, else (False, the plain reason).
    While TRUST runs open, everyone may."""
    if person["open"]:
        return True, ""
    who = who_signs(group, month, rows)
    allowed = {entry["sam"] for entry in who["leads"] + who["delegates"]}
    if person["sam"] in allowed or access.is_tech_risk(person):
        return True, ""
    return False, "You can't sign this off. " + who["sentence"] + " If you think you should, ask Tech Risk."


def may_name_a_delegate(person, group, month, rows):
    """(True, "") for a lead of the team, and for Tech Risk. While TRUST runs open, everyone."""
    if person["open"]:
        return True, ""
    leads = leads_of_group(group, month)
    if not leads:
        return False, "We couldn't find who leads this team, so there is nobody to name a delegate for."
    if leads_this_person_speaks_for(person, group, month):
        return True, ""
    names = " or ".join(lead["name"] for lead in leads)
    return False, f"Only {names}, who lead this team, can name a delegate. If you think you should, ask Tech Risk."


def rights_with_signoff(person, group, month):
    """What groups.what_a_person_may_do says, except that a person who may sign the group off can also open it
    (a delegate is not always in the group's reporting line, and still needs to see what they sign)."""
    rights = groups.what_a_person_may_do(person, group, month)
    if rights["view"] or person["open"]:
        return rights
    allowed, _why = may_sign_off(person, group, month, storage.risk_signoffs(group["id"]))
    return dict(rights, view=rights["view"] or allowed)


# ---------------------------------------------------------------------------------------------------
# Decisions and the status
# ---------------------------------------------------------------------------------------------------

def decision_on(assessment_id, group_id, rows):
    """The newest sign-off or send-back row for one assessment, or None."""
    decided = [row for row in rows if row["kind"] in (SIGNOFF, SENDBACK)
               and row["group_id"] == group_id and row["assessment_id"] == assessment_id]
    return decided[-1] if decided else None


def status_of(group_id, answer_rows, assessment_rows, rows):
    """Not started, Draft, Submitted, Signed off or Sent back.

    The newest assessment decides. Sent back stays until the group submits again (the reason is shown meanwhile, and
    the team is free to answer). Changed answers after a Submit or a sign-off make the group a Draft again."""
    basic = assess.status_of(answer_rows, assessment_rows)
    if not assessment_rows:
        return basic
    decision = decision_on(assessment_rows[-1]["id"], group_id, rows)
    if decision and decision["kind"] == SENDBACK:
        return SENT_BACK
    if basic != assess.SUBMITTED:
        return basic
    return SIGNED_OFF if decision else assess.SUBMITTED


def group_status(group_id, answer_rows, assessment_rows):
    """status_of, reading the sign-off rows itself. This is what the groups list and the form's header show."""
    return status_of(group_id, answer_rows, assessment_rows, storage.risk_signoffs(group_id))


def short_summary(group_id, assessment_rows, rows):
    """The newest assessment's decision as the groups list shows it, or None: {"state", "by", "at", "note", "also_changed"}."""
    if not assessment_rows:
        return None
    decision = decision_on(assessment_rows[-1]["id"], group_id, rows)
    if decision is None:
        return None
    return {"state": SIGNED_OFF if decision["kind"] == SIGNOFF else SENT_BACK, "by": decision["by"],
            "at": decision["at"], "note": decision["note"], "also_changed": decision["also_changed"],
            "rated_again": bool(assessment_rows[-1]["result"].get("differs_from_kept"))}


# ---------------------------------------------------------------------------------------------------
# "Also changed answers"
# ---------------------------------------------------------------------------------------------------

def _sam_in(label):
    """The SAM_ACCOUNT in "Name (sam)", or the label itself when it has no brackets."""
    found = re.search(r"\(([^()]+)\)\s*$", label or "")
    return (found.group(1) if found else label or "").strip().lower()


def same_person(label_one, label_two):
    """Two "by" labels name the same person: the same typed name, or the same SAM_ACCOUNT."""
    one = tidy_spaces(label_one).lower()
    two = tidy_spaces(label_two).lower()
    return bool(one) and (one == two or _sam_in(label_one) == _sam_in(label_two))


def answers_changed_by(signer, assessment, assessment_rows, answer_rows):
    """How many questions the signer saved an answer for in the period this assessment covers: after the group's
    earlier assessment (or from the start) up to this assessment."""
    position = next(index for index, row in enumerate(assessment_rows) if row["id"] == assessment["id"])
    period_starts = moment_of(assessment_rows[position - 1]["at"]) if position > 0 else None
    period_ends = moment_of(assessment["at"])
    questions = set()
    for row in answer_rows:
        saved_at = moment_of(row["at"])
        in_the_period = (period_starts is None or saved_at > period_starts) and saved_at <= period_ends
        if in_the_period and same_person(row["by"], signer):
            questions.add(row["question"])
    return len(questions)


def flag_sentence(signer, count):
    return f"{signer} also changed {count_of(count, 'answer')} in this assessment."


# ---------------------------------------------------------------------------------------------------
# The sign-off box's data
# ---------------------------------------------------------------------------------------------------

def history(group_id, assessment_rows, rows):
    """Every assessment, newest first, with its decision: [{"assessment_id", "at", "by", "state", ...}]."""
    kept = []
    for position, assessment in enumerate(assessment_rows):
        decision = decision_on(assessment["id"], group_id, rows)
        is_newest = position == len(assessment_rows) - 1
        if decision:
            state = SIGNED_OFF if decision["kind"] == SIGNOFF else SENT_BACK
        else:
            state = assess.SUBMITTED if is_newest else REPLACED
        entry = {"assessment_id": assessment["id"], "at": assessment["at"], "by": assessment["by"], "state": state,
                 "decided_by": None, "decided_at": None, "note": None, "also_changed": False, "flag": None,
                 "rated_again": False}
        if decision:
            entry.update(decided_by=decision["by"], decided_at=decision["at"], note=decision["note"],
                         also_changed=decision["also_changed"],
                         flag=flag_sentence(decision["by"], decision["changed_answers"]) if decision["also_changed"] else None,
                         # With rate_with_current_rules on (current_rules.py): today's rating is not the one the decision was given on.
                         rated_again=bool(assessment["result"].get("differs_from_kept")))
        kept.append(entry)
    kept.reverse()
    return kept
