"""Where in the code each Risk calculation lives, for the "See the code" lines on the Risk site (owner, 16 Nov 2026).

Every place is built with codelinks.place(), so the line numbers are read from the running source and a link is
added when the repo address is set. This is the one list of which functions to show. If a function is renamed,
tests/test_risk_code_places.py fails, so the list can't go stale. Nothing here changes a rating or a value.
"""
from trust import codelinks

# The rules that decide a rating, in the order a risk is worked through (file under backend/trust/, function, what it does).
RATING_RULES = [
    ("risk/rating.py", "is_applicable", "Whether the risk applies to the team"),
    ("risk/rating.py", "likelihood", "How likely the risk is, from the drivers that are on"),
    ("risk/rating.py", "overall_impact", "How big the impact is, the highest of the impact kinds"),
    ("risk/rating.py", "rate_risk", "Puts applies, likelihood and impact together into one rating"),
    ("risk/rating.py", "is_elevated", "Whether the rating is Elevated"),
    ("risk/explain.py", "steps_for_risk", "Writes the plain-words steps shown under 'How this was rated'"),
]

# Each data-driver calculation (the names in config/risk_data_drivers.json) and the function that works it out.
DRIVER_CALCULATIONS = {
    "legacy_languages": "Counts the team's repos that use a legacy language",
    "tcc_adoption": "Checks how much of the team's change work uses TCC",
    "headcount": "Compares the team's headcount with the prevailing median",
    "language_variety": "Counts the different languages the team runs",
    "other_teams": "Counts other teams committing in the team's repos",
}


def rating_places():
    """The rating rules as places for the results page (a rule that can't be found is left out; the test catches that)."""
    places = [codelinks.place(file, function, what) for file, function, what in RATING_RULES]
    return [one for one in places if one]


def driver_place(calculation):
    """The place of one data-driver calculation (by name, e.g. "legacy_languages"), or None if there isn't one."""
    what = DRIVER_CALCULATIONS.get(calculation)
    if not calculation or what is None:
        return None
    return codelinks.place("risk/data_drivers.py", calculation, what)


def driver_place_for_code(driver_code, defined=None):
    """The place for a driver code such as RD21, through the calculation config/risk_data_drivers.json points at it.
    A driver Tech Risk defined ("Calculations you define") gives two places instead: its figure and its test."""
    from trust.risk import data_drivers                  # imported here: data_drivers calls this module for the form
    built_in = data_drivers.calculation_of(driver_code)
    if built_in is None:
        return data_drivers.defined_places(driver_code, defined)
    return driver_place(built_in)


def with_places(data_driver_answers):
    """A copy of a result's data_drivers ({code: answer}) where each answer also carries its "place"."""
    return {code: {**answer, "place": driver_place_for_code(code)} for code, answer in (data_driver_answers or {}).items()}
