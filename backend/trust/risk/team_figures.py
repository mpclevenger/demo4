"""Team figures and tests that Tech Risk can pick from to define a driver (owner, 16 Nov 2026).

A TEAM FIGURE is one number TRUST already works out for a team in a month, for example "changes released". A TEST
is one way to compare a figure: above the prevailing median, below 70% of it, above a number. On the Risk site's
"Calculations you define" page, Tech Risk picks a driver, a figure and a test. No code is needed for that.
A brand-new figure still needs code: add one function below and one line in FIGURES.

    figure                      what it counts                                                         where it comes from
    releases                    changes released by the team in the month (TCC changes)                the TCC file (the same count as TCC adoption)
    incidents_per_100_people    the team's Critical and SWE incidents in the month, per 100 people     the postmortems file and HR (the same count as UN-01)
    aged_critical_high_findings the team's open Critical or High Checkmarx findings older than         the Checkmarx SAST and SCA files (NOT KNOWN today: they carry
                                finding_age_days (config/risk_data_drivers.json) at month end           no first-found date)
    overdue_postmortem_actions  the team's postmortem actions past their due date at month end          the action items file (the same count as UN-02)

Every figure function gets the month's facts (data_drivers.facts_for) and gives, for each team:
    {"number": a number or None, "why_not": why it is not known, "value_text": short words for the number,
    "piece": a plain sentence piece, "sources": [where it came from]}

A figure is None ("not known") when its data isn't loaded. It is never guessed.
This file changes no rating rule and no TRUST score. The prevailing median itself is worked out in data_drivers.py.
"""
import calendar

from trust import measure, score_month
from trust.words import count_of

PEOPLE_PER_RATE = 100                                    # incidents are shown per 100 people
FIRST_MONTH_NUMBER = 1
SHARE_LARGEST = 1                                        # a share is a part of one: 0.70 is 70%
PERCENT = 100


def source_of(feeds, feed, what):
    """Where a figure came from: the feed, the file and the day it was uploaded. None when the feed isn't mapped."""
    held = feeds.get(feed) or {}
    if held.get("status") != "mapped":
        return None
    return {"feed": feed, "what": what, "file": held.get("file"), "as_of": str(held.get("uploaded_at") or "")[:10] or None}


def month_name(month):
    """'2026-10' -> 'October'."""
    return calendar.month_name[int(month.split("-")[1])]


def _nobody_knows(facts, why, sources=()):
    return {team["id"]: {"number": None, "why_not": why, "piece": None, "sources": [one for one in sources if one]}
            for team in facts["teams"]}


# ---------------------------------------------------------------------------------------------------
# Figure: releases = the changes the team released (through TCC) in the month
# ---------------------------------------------------------------------------------------------------

def releases(facts):
    """Changes released by each team in the month: the TCC changes deployed that month, counted as TCC adoption counts them."""
    feeds, month = facts["feeds"], facts["month"]
    tcc_source = source_of(feeds, "tcc", "changes released through TCC")
    if tcc_source is None:
        return _nobody_knows(facts, "the TCC change file isn't loaded")
    counts = score_month.expand_shared({"TE-01": measure.te01(feeds, month)}, facts["shared"])["TE-01"]
    answers = {}
    for team in facts["teams"]:
        found = counts.get(team["id"]) or {}
        released = found.get("numerator") or 0
        answers[team["id"]] = {"number": released, "why_not": None, "sources": [tcc_source],
                               "value_text": count_of(released, "release", "releases"),
                               "piece": f"{count_of(released, 'release', 'releases')} in {month_name(month)}"}
    return answers


# ---------------------------------------------------------------------------------------------------
# Figure: incidents_per_100_people = incidents * 100 / people placed with the team
# ---------------------------------------------------------------------------------------------------

def incidents_per_100_people(facts):
    """The team's Critical and SWE incidents in the month, per 100 people placed with the team. The incidents are
    counted exactly as UN-01 counts them (measure.un01); the people are the ones HR places with the team."""
    feeds, month = facts["feeds"], facts["month"]
    incident_source = source_of(feeds, "postmortems", "Critical and SWE incidents")
    people_source = source_of(feeds, "hr", "people placed with each team")
    if incident_source is None:
        return _nobody_knows(facts, "the postmortems file isn't loaded", [people_source])
    if not facts["people_known"] or people_source is None:
        return _nobody_knows(facts, "HR isn't loaded", [incident_source])
    sources = [incident_source, people_source]
    counts = score_month.expand_shared({"UN-01": measure.un01(feeds, month)}, facts["shared"])["UN-01"]
    answers = {}
    for team in facts["teams"]:
        people = facts["headcount"][team["id"]]
        if not people:
            answers[team["id"]] = {"number": None, "why_not": "no people are placed with this team", "piece": None, "sources": sources}
            continue
        incidents = (counts.get(team["id"]) or {}).get("numerator") or 0
        incidents_per_100_people_found = incidents / people * PEOPLE_PER_RATE
        answers[team["id"]] = {
            "number": incidents_per_100_people_found, "why_not": None, "sources": sources,
            "value_text": f"{incidents_per_100_people_found:.1f} incidents per {PEOPLE_PER_RATE} people",
            "piece": (f"{count_of(incidents, 'incident', 'incidents')} in {month_name(month)} for "
                      f"{count_of(people, 'person', 'people')} ({incidents_per_100_people_found:.1f} per {PEOPLE_PER_RATE} people)")}
    return answers

# ---------------------------------------------------------------------------------------------------
# Figure: aged_critical_high_findings = open Critical or High Checkmarx findings older than finding_age_days
# ---------------------------------------------------------------------------------------------------

FINDING_AGE_SETTING = "finding_age_days"                # the setting's name in config/risk_data_drivers.json
NO_FIRST_FOUND_DATE = "the Checkmarx files TRUST keeps don't say when each finding was first found"


def finding_age_days():
    """The age, in days, after which an open finding counts as aged (a setting in config/risk_data_drivers.json)."""
    from trust.risk import data_drivers                   # imported here: data_drivers reads this file's figures
    return data_drivers.settings_file()[FINDING_AGE_SETTING]


def aged_critical_high_findings(facts):
    """The team's open Critical or High Checkmarx findings (SAST and SCA) older than finding_age_days at month end.
    A finding's age needs the day it was first found. The Checkmarx files carry only a count of findings past the
    policy's limit, with no first-found date, so this is not known. It is never guessed from that count. When Cyber
    adds the date to the files, this is the one place to count the findings."""
    feeds = facts["feeds"]
    sast_source = source_of(feeds, "cx_sast", "Checkmarx SAST findings")
    sca_source = source_of(feeds, "cx_sca", "Checkmarx SCA findings")
    age_in_days = finding_age_days()
    if sast_source is None and sca_source is None:
        return _nobody_knows(facts, "the Checkmarx files aren't loaded")
    why_not = f"{NO_FIRST_FOUND_DATE}, so findings older than {age_in_days} days can't be counted"
    return _nobody_knows(facts, why_not, [sast_source, sca_source])


# ---------------------------------------------------------------------------------------------------
# Figure: overdue_postmortem_actions = the team's open postmortem actions past their due date at month end
# ---------------------------------------------------------------------------------------------------

def overdue_postmortem_actions(facts):
    """The team's postmortem actions past their due date at month end, counted exactly as UN-02 counts them
    (measure.un02: open actions on an incident in scope and rated; a blank due date is 30 days after it was created)."""
    feeds, month = facts["feeds"], facts["month"]
    action_source = source_of(feeds, "actions", "postmortem action items")
    if action_source is None:
        return _nobody_knows(facts, "the postmortem action items file isn't loaded")
    counts = score_month.expand_shared({"UN-02": measure.un02(feeds, month)}, facts["shared"])["UN-02"]
    answers = {}
    for team in facts["teams"]:
        found = counts.get(team["id"]) or {}
        overdue = found.get("numerator") or 0
        answers[team["id"]] = {"number": overdue, "why_not": None, "sources": [action_source],
                               "value_text": count_of(overdue, "overdue action", "overdue actions"),
                               "piece": f"{count_of(overdue, 'postmortem action', 'postmortem actions')} past due at the end of {month_name(month)}"}
    return answers


# The figures to pick from: name -> the plain words Tech Risk sees, and the function that works it out.
FIGURES = {
    "releases": {"label": "Changes released in the month", "function": releases},
    "incidents_per_100_people": {"label": "Incidents in the month per 100 people", "function": incidents_per_100_people},
    "aged_critical_high_findings": {"label": "Critical or High Checkmarx findings open longer than the age limit",
                                    "function": aged_critical_high_findings},
    "overdue_postmortem_actions": {"label": "Postmortem actions past their due date", "function": overdue_postmortem_actions},
}


# ---------------------------------------------------------------------------------------------------
# Tests: each says ON or OFF for one team's number. median is the prevailing median (None for a fixed-number test).
# setting is the number or share Tech Risk gave for the test (None for a test that needs none).
# ---------------------------------------------------------------------------------------------------

NEEDS_NOTHING, NEEDS_NUMBER, NEEDS_SHARE = "nothing", "number", "share"


def above_median(number, median, setting):
    """ON when the team's number is above the prevailing median."""
    return number > median


def below_median(number, median, setting):
    """ON when the team's number is below the prevailing median."""
    return number < median


def below_share_of_median(number, median, setting):
    """ON when the team's number is below the share (0.70 = 70%) of the prevailing median."""
    share_of_median = median * setting
    return number < share_of_median


def above_number(number, median, setting):
    """ON when the team's number is above the number Tech Risk gave."""
    return number > setting


def below_number(number, median, setting):
    """ON when the team's number is below the number Tech Risk gave."""
    return number < setting


def _median_words(median, team_count):
    return f"the prevailing median is {median:g} across {count_of(team_count, 'team', 'teams')}"


def _words_above_median(median, team_count, setting):
    return _median_words(median, team_count)


def _words_below_share_of_median(median, team_count, setting):
    share_of_median = median * setting
    return (f"{setting * PERCENT:g}% of the prevailing median is {share_of_median:g} "
            f"(the median is {median:g} across {count_of(team_count, 'team', 'teams')})")


def _words_number(median, team_count, setting):
    return f"the number to compare with is {setting:g}"


TESTS = {
    "above_median": {"label": "Is above the prevailing median", "function": above_median, "needs": NEEDS_NOTHING,
                     "words": _words_above_median},
    "below_median": {"label": "Is below the prevailing median", "function": below_median, "needs": NEEDS_NOTHING,
                     "words": _words_above_median},
    "below_share_of_median": {"label": "Is below a share of the prevailing median", "function": below_share_of_median,
                              "needs": NEEDS_SHARE, "words": _words_below_share_of_median},
    "above_number": {"label": "Is above a number", "function": above_number, "needs": NEEDS_NUMBER, "words": _words_number},
    "below_number": {"label": "Is below a number", "function": below_number, "needs": NEEDS_NUMBER, "words": _words_number},
}
MEDIAN_TESTS = ("above_median", "below_median", "below_share_of_median")     # the two number tests don't use the median


def uses_the_median(test_name):
    return test_name in MEDIAN_TESTS


def check_setting(test_name, setting):
    """A ValueError in plain words when the number or share doesn't fit the test."""
    needs = TESTS[test_name]["needs"]
    label = TESTS[test_name]["label"].lower()
    if needs == NEEDS_NOTHING and setting is not None:
        raise ValueError(f"The test '{label}' uses no number. Leave the number or share empty.")
    if needs == NEEDS_NUMBER and setting is None:
        raise ValueError(f"Give the number for the test '{label}'.")
    if needs == NEEDS_SHARE and (setting is None or not 0 < setting <= SHARE_LARGEST):
        raise ValueError("Give the share as a part of one, for example 0.70 for 70%.")
