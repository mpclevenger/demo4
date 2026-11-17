"""Risk drivers answered from TRUST's own data (owner, 16 Nov 2026; per L4 team since 17 Nov 2026).

A driver the questionnaire doesn't ask about is answered from data. Five are calculated here, one calculation
each. For every Risk group (an L4 team: its leader and everyone under them in HR) and a month, each calculation says
ON, OFF or "not known", with the numbers behind it, where they came from, and one plain sentence.

    calculation          what it looks at                                              ON when
    legacy_languages     the languages of the L4 team's active repos (repos file)      any repo uses a listed language (Perl, C, C++, PHP)
    tcc_adoption         changes through TCC / all changes (TCC + Non-TCC) that month  the team's share is below the prevailing median
    headcount            the people in the L4 team (HR)                                below a share (70%) of the prevailing median headcount
    language_variety     distinct languages across the team's repos, less markup/config above the prevailing median
    other_teams          other L4 teams with contributors in the team's repos that month  more than a set number (2) of other teams

How an item is placed with an L4 team. A repo goes to the L4 team of its owner (the owner's work email, in HR). A
change, an incident or an action goes to the L4 team of each person named on it (the people TRUST keeps with the item,
found in HR by email or SAM_ACCOUNT). An item whose people are all outside any L4 team (for example the L3 lead) is
counted for no L4 team. The prevailing median is the median across the L4 teams that have a result.

Which driver code each calculation answers is in config/risk_data_drivers.json ("calculations"), so the owner can
re-point a calculation when a code changes. The starting values (the language lists, 70%, 2 teams) are in the same
file and on the Risk site's "Drivers answered from data" editing page; a change saved there wins.

The prevailing median is TRUST's own calculation, score_month.thresholds_for, used as it is: the median of the
teams' results that month, and it needs the same fewest teams as the scorecard (setting min_families_for_threshold).

Never guessed: a driver whose data isn't loaded, or whose team has none of it, is "not known" and says why. A driver
that is not known is never counted as on (drivers.py). This file changes no rating rule and no TRUST score.
"""
import json
import os
import pathlib

from trust import storage
from trust.risk import assess, code_places, drivers, files, groups, questions as question_list, team_figures
from trust.words import count_of

ROOT = pathlib.Path(__file__).resolve().parents[3]

LEGACY_LANGUAGES = "legacy_languages"
TCC_ADOPTION = "tcc_adoption"
HEADCOUNT = "headcount"
LANGUAGE_VARIETY = "language_variety"
OTHER_TEAMS = "other_teams"

BASIS_MEDIAN = "Prevailing median"
BASIS_SHARE = "Share of the prevailing median"
BASIS_FIXED = "Fixed number"
BASIS_LANGUAGES = "Any of these languages"
BASIS_LABELS = {BASIS_MEDIAN: "The prevailing median", BASIS_SHARE: "A share of the prevailing median",
                BASIS_FIXED: "A fixed number", BASIS_LANGUAGES: "Any of these languages"}
BASES_FOR = {LEGACY_LANGUAGES: (BASIS_LANGUAGES,),
             TCC_ADOPTION: (BASIS_MEDIAN, BASIS_FIXED),
             HEADCOUNT: (BASIS_SHARE, BASIS_MEDIAN, BASIS_FIXED),
             LANGUAGE_VARIETY: (BASIS_MEDIAN, BASIS_FIXED),
             OTHER_TEAMS: (BASIS_FIXED,)}

PERCENT = 100                                            # a share of 0.70 is 70%
SHOWN_REPOS = 5                                          # repos or teams named in a sentence before "and N more"
SHOWN_LANGUAGES = 10                                     # languages named in a sentence before "and N more"
FILE_NAME = "risk_data_drivers.json"


# ---------------------------------------------------------------------------------------------------
# The settings: the file's starting values, with the editing page's saved changes on top
# ---------------------------------------------------------------------------------------------------

def settings_file():
    path = pathlib.Path(os.environ.get("TRUST_RISK_DATA_DRIVERS") or ROOT / "config" / FILE_NAME)
    document = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in document.items() if not key.startswith("_")}


def calculation_of(code):
    """The calculation that answers this driver code, or None when no calculation is pointed at it."""
    return (settings_file().get("calculations") or {}).get(code)


def words_in(text_or_list):
    """A language list as a list of words. "Perl, C, C++" and ["Perl", "C", "C++"] both give ["Perl", "C", "C++"]."""
    if isinstance(text_or_list, str):
        text_or_list = text_or_list.split(",")
    return [word.strip() for word in text_or_list or [] if str(word).strip()]


def default_values(code):
    """The editing page's values for one driver, from the file. None when no calculation answers this code."""
    calculation = calculation_of(code)
    if calculation is None:
        return None
    file = settings_file()
    values = {"basis": BASES_FOR[calculation][0], "fixed_number": None, "share_of_median": None,
              "languages": "", "left_out_languages": ""}
    if calculation == LEGACY_LANGUAGES:
        values["languages"] = ", ".join(file["legacy_languages"])
    elif calculation == HEADCOUNT:
        values["share_of_median"] = round(file["headcount_share_of_median"] * PERCENT, 6)
    elif calculation == LANGUAGE_VARIETY:
        values["left_out_languages"] = ", ".join(file["left_out_languages"])
    elif calculation == OTHER_TEAMS:
        values["fixed_number"] = file["other_teams_more_than"]
    return values


def settings_by_code(entries, driver_codes):
    """What each calculation uses, by driver code: the file's values, with each saved entry's values on top.
    entries are the "Drivers answered from data" entries as editable.entries_now gives them."""
    saved = {entry["key"]: entry["values"] for entry in entries or []}
    found = {}
    for code in driver_codes:
        values = default_values(code)
        if values is None:
            continue
        values = {**values, **{name: value for name, value in (saved.get(code) or {}).items() if name in values}}
        found[code] = {"calculation": calculation_of(code), **values}
    return found


def check_values(code, values):
    """A ValueError in plain words when the editing page's values for a driver can't be used."""
    calculation = calculation_of(code)
    if calculation is None:
        return
    if values["basis"] not in BASES_FOR[calculation]:
        raise ValueError(f"{code} can be compared this way: {' or '.join(BASES_FOR[calculation]).lower()}.")
    if values["basis"] == BASIS_LANGUAGES and not words_in(values.get("languages")):
        raise ValueError("Give at least one language, separated by commas, for example Perl, C, C++, PHP.")
    if values["basis"] == BASIS_SHARE:
        share = values.get("share_of_median")
        if share is None or not 0 < share <= PERCENT:
            raise ValueError("Give the share of the prevailing median as a percent from 1 to 100.")
    if values["basis"] == BASIS_FIXED and values.get("fixed_number") is None:
        raise ValueError("Give the fixed number.")


# ---------------------------------------------------------------------------------------------------
# What TRUST holds for a month
# ---------------------------------------------------------------------------------------------------

def _shown(names, limit=SHOWN_REPOS):
    names = list(names)
    text = ", ".join(names[:limit])
    return text + (f", and {len(names) - limit} more" if len(names) > limit else "")


def _source(feeds, feed, what):
    """Where a figure came from: the feed, the file and the day it was uploaded."""
    return team_figures.source_of(feeds, feed, what)


def facts_for(month):
    """Everything the calculations need, read from the mapped month: the teams, who is in them, their repos, the
    changes and the contributors. Nothing is worked out here beyond placing items with teams."""
    mapped = storage.load_month("mapped", month) or {}
    feeds = mapped.get("feeds") or {}
    teams = groups.teams_in(month)
    team_ids = [team["id"] for team in teams]
    hr_people = (feeds.get("hr") or {}).get("people") or []
    group_of_sam = {sam: team["id"] for team in teams for sam in team["members"]}
    group_of_email = {person["email"].strip().lower(): group_of_sam[person["sam_account"].lower()] for person in hr_people
                      if person.get("email") and person["sam_account"].lower() in group_of_sam}

    repos_by_team = {team_id: [] for team_id in team_ids}
    repo_rows = (feeds.get("repos") or {}).get("rows")
    for row in repo_rows or []:
        if not row.get("active"):
            continue
        team_id = group_of_email.get((row.get("owner_email") or "").strip().lower())      # the repo goes to its owner's L4 team
        if team_id:
            repos_by_team[team_id].append(row)

    return {"month": month, "feeds": feeds, "teams": teams, "group_of_sam": group_of_sam, "group_of_email": group_of_email,
            "shared": (feeds.get("hr_mapping") or {}).get("shared") or {},
            "team_name": {team["id"]: team["name"] for team in teams},
            "headcount": {team["id"]: len(groups.members(team, month)) for team in teams},
            "people_known": bool((feeds.get("hr") or {}).get("people")),
            "repos_loaded": repo_rows is not None and (feeds.get("repos") or {}).get("status") == "mapped",
            "languages_loaded": any(row.get("languages") for row in repo_rows or []),
            "repos_by_team": repos_by_team}


# ---------------------------------------------------------------------------------------------------
# The prevailing median: TRUST's own calculation, used as it is
# ---------------------------------------------------------------------------------------------------

def prevailing_median(code, values, cfg=None):
    """(median, None), or (None, why not) when too few teams have a result. The same calculation and the same
    fewest-teams rule as the scorecard's tolerance thresholds (score_month.thresholds_for)."""
    from trust import score_month
    cfg = cfg or score_month.thresholds_config()
    found = score_month.thresholds_for(code, list(values), True, cfg)
    if found is None:
        need = score_month.min_families(cfg)
        return None, (f"The prevailing median needs {count_of(need, 'team', 'teams')} with a result, and "
                      f"{count_of(len(values), 'team has', 'teams have')} one")
    return found["green"], None


def _not_known(why, sources=()):
    return {"on": None, "value": None, "value_text": "not known", "sentence": f"Not known: {why}.",
            "sources": [source for source in sources if source]}


def _or_list(names):
    """["Perl", "C", "PHP"] -> "Perl, C or PHP"."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _tag(text, is_starting_value):
    return f"{text} (starting value)" if is_starting_value else text


# ---------------------------------------------------------------------------------------------------
# RD21 legacy application architecture: ON when any repo of the team uses Perl, C, C++ or PHP
# ---------------------------------------------------------------------------------------------------

def legacy_languages(facts, setting, code, starting, cfg=None):
    """`cfg` is not used here: every calculation is called with the same arguments."""
    listed = words_in(setting["languages"])
    listed_lower = {name.lower() for name in listed}
    list_text = _tag(_or_list(listed), starting)
    source = _source(facts["feeds"], "repos", "languages of each repo")
    answers = {}
    for team in facts["teams"]:
        repos = facts["repos_by_team"][team["id"]]
        if not facts["repos_loaded"]:
            answers[team["id"]] = _not_known("the GitHub repos file isn't loaded")
        elif not facts["languages_loaded"]:
            answers[team["id"]] = _not_known("the GitHub repos file has no Languages column, or it is empty")
        elif not repos:
            answers[team["id"]] = _not_known("no active repos are placed with this team")
        else:
            using = sorted(row["repo"] for row in repos if listed_lower & {name.lower() for name in row["languages"]})
            all_repos = len(repos)
            on = bool(using)
            verb = "uses" if all_repos == 1 else "use"
            if on:
                sentence = f"{len(using)} of {count_of(all_repos, 'repo', 'repos')} {verb} {list_text}: {_shown(using)}."
            elif all_repos == 1:
                sentence = f"The team's 1 repo doesn't use {list_text}."
            else:
                sentence = f"None of {all_repos} repos use {list_text}."
            answers[team["id"]] = {"on": on, "value": len(using), "value_text": count_of(len(using), "repo", "repos"),
                                   "sentence": sentence, "sources": [source]}
    return answers


# ---------------------------------------------------------------------------------------------------
# RD15 lack of formal change process: ON when the team's TCC adoption is below the prevailing median
# ---------------------------------------------------------------------------------------------------

def tcc_adoption(facts, setting, code, starting, cfg=None):
    from trust import measure
    feeds, month = facts["feeds"], facts["month"]
    sources = [_source(feeds, "tcc", "changes through TCC"), _source(feeds, "ntcc", "changes not through TCC")]
    if not all(sources):
        return {team["id"]: _not_known("the TCC and Non-TCC change files aren't both loaded", sources) for team in facts["teams"]}
    items_of_team = team_figures.items_by_group(measure.te01(feeds, month), facts)

    adoption = {}
    for team in facts["teams"]:
        changes = items_of_team.get(team["id"]) or []
        all_changes = len(changes)
        through_tcc = sum(1 for change in changes if change["through_tcc"])
        if all_changes:
            adoption[team["id"]] = {"through_tcc": through_tcc, "all_changes": all_changes,
                                    "percent": through_tcc / all_changes * PERCENT}
    limit, median, why_not = _limit(setting, code, [found["percent"] for found in adoption.values()], cfg)
    answers = {}
    for team in facts["teams"]:
        found = adoption.get(team["id"])
        if not found:
            answers[team["id"]] = _not_known(f"no changes were recorded for this team in {month}", sources)
            continue
        if limit is None:
            answers[team["id"]] = _not_known(why_not, sources)
            continue
        percent = found["percent"]
        on = percent < limit
        where = "below" if on else "at or above"
        if setting["basis"] == BASIS_MEDIAN:
            compared = f"{where} the prevailing median of {limit:.1f}% across {count_of(len(adoption), 'team', 'teams')}"
        else:
            compared = f"{where} the fixed {limit:g}%"
        sentence = (f"{count_of(found['through_tcc'], 'change', 'changes')} out of {found['all_changes']} went through TCC in {month} "
                    f"({percent:.1f}%), {compared}.")
        answers[team["id"]] = {"on": on, "value": round(percent, 1), "value_text": f"{percent:.1f}% through TCC",
                               "sentence": sentence, "sources": sources}
    return answers


def _limit(setting, code, values, cfg):
    """(the number a team's value is compared with, the prevailing median, why not).
    Prevailing median: TRUST's median of the teams' values. Share: that median times the share. Fixed: the number.
    The number is None, with the reason, when the median can't be worked out (too few teams)."""
    if setting["basis"] == BASIS_FIXED:
        return float(setting["fixed_number"]), None, None
    median, why_not = prevailing_median(code, values, cfg)
    if median is None:
        return None, None, why_not
    if setting["basis"] == BASIS_SHARE:
        share = setting["share_of_median"] / PERCENT
        return median * share, median, None
    return median, median, None


# ---------------------------------------------------------------------------------------------------
# RD53 inadequate team capacity: ON when the team's headcount is below 70% of the prevailing median headcount
# ---------------------------------------------------------------------------------------------------

def headcount(facts, setting, code, starting, cfg=None):
    source = _source(facts["feeds"], "hr", "people in each L4 team")
    if not facts["people_known"]:
        return {team["id"]: _not_known("HR isn't loaded") for team in facts["teams"]}
    people = {team_id: count for team_id, count in facts["headcount"].items() if count}
    limit, median, why_not = _limit(setting, code, people.values(), cfg)
    answers = {}
    for team in facts["teams"]:
        count = facts["headcount"][team["id"]]
        if not count:
            answers[team["id"]] = _not_known("no people are placed with this team", [source])
            continue
        if limit is None:
            answers[team["id"]] = _not_known(why_not, [source])
            continue
        on = count < limit
        if setting["basis"] == BASIS_SHARE:
            share_text = _tag(f"{setting['share_of_median']:g}%", starting)
            compared = (f"The prevailing median is {median:g} people across {count_of(len(people), 'team', 'teams')}; "
                        f"{share_text} of it is {limit:g} people.")
        elif setting["basis"] == BASIS_MEDIAN:
            compared = f"The prevailing median is {median:g} people across {count_of(len(people), 'team', 'teams')}."
        else:
            compared = f"The fixed number is {limit:g} people."
        sentence = f"{count_of(count, 'person', 'people')} is {'below' if on else 'not below'} {limit:g}. {compared}"
        answers[team["id"]] = {"on": on, "value": count, "value_text": count_of(count, "person", "people"),
                               "sentence": sentence, "sources": [source]}
    return answers


# ---------------------------------------------------------------------------------------------------
# RD11 diversity of running process types: ON when the team uses more distinct languages than the prevailing median
# ---------------------------------------------------------------------------------------------------

def language_variety(facts, setting, code, starting, cfg=None):
    source = _source(facts["feeds"], "repos", "languages of each repo")
    left_out = {name.lower() for name in words_in(setting["left_out_languages"])}
    in_use = {}
    for team in facts["teams"]:
        names = {}
        for row in facts["repos_by_team"][team["id"]]:
            for name in row["languages"]:
                if name.lower() not in left_out:
                    names.setdefault(name.lower(), name)
        if names:
            in_use[team["id"]] = sorted(names.values())
    limit, _median, why_not = _limit(setting, code, [len(names) for names in in_use.values()], cfg)
    answers = {}
    for team in facts["teams"]:
        names = in_use.get(team["id"])
        if not facts["repos_loaded"]:
            answers[team["id"]] = _not_known("the GitHub repos file isn't loaded")
        elif not facts["languages_loaded"]:
            answers[team["id"]] = _not_known("the GitHub repos file has no Languages column, or it is empty")
        elif not names:
            answers[team["id"]] = _not_known("none of this team's active repos has a language to count")
        elif limit is None:
            answers[team["id"]] = _not_known(why_not, [source])
        else:
            on = len(names) > limit
            basis = (f"the prevailing median of {limit:g} across {count_of(len(in_use), 'team', 'teams')}"
                     if setting["basis"] == BASIS_MEDIAN else f"the fixed number {limit:g}")
            left_text = _tag(f"leaving out {_shown(words_in(setting['left_out_languages']), SHOWN_REPOS)}", starting)
            sentence = (f"{count_of(len(names), 'language', 'languages')} in use ({_shown(names, SHOWN_LANGUAGES)}), "
                        f"{'above' if on else 'not above'} {basis}; {left_text}.")
            answers[team["id"]] = {"on": on, "value": len(names), "value_text": count_of(len(names), "language", "languages"),
                                   "sentence": sentence, "sources": [source]}
    return answers


# ---------------------------------------------------------------------------------------------------
# RD25 multiple teams contributing: ON when more than 2 other teams made commits in the team's repos that month
# ---------------------------------------------------------------------------------------------------

def other_teams(facts, setting, code, starting, cfg=None):
    feeds, month = facts["feeds"], facts["month"]
    sources = [_source(feeds, "repo_contributors", "commits by contributor"), _source(feeds, "hr", "each contributor's team")]
    contributions = (feeds.get("repo_contributors") or {}).get("rows")
    if not all(sources) or contributions is None:
        return {team["id"]: _not_known("the repo contributors file and HR aren't both loaded", sources) for team in facts["teams"]}
    month_rows = [row for row in contributions if row["month"] in (month, None) and row["commits"] > 0]
    if not month_rows:
        return {team["id"]: _not_known(f"the repo contributors file has no commits for {month}", sources) for team in facts["teams"]}
    person_of_email = {person["email"].strip().lower(): person
                       for person in (feeds.get("hr") or {}).get("people") or [] if person.get("email")}
    group_of_email = facts["group_of_email"]
    limit = float(setting["fixed_number"])

    answers = {}
    for team in facts["teams"]:
        repo_names = {row["repo"].lower() for row in facts["repos_by_team"][team["id"]]}
        if not repo_names:
            answers[team["id"]] = _not_known("no active repos are placed with this team", sources)
            continue
        other_team_ids, not_matched, not_placed = set(), set(), set()
        for row in month_rows:
            if row["repo"].lower() not in repo_names:
                continue
            person = person_of_email.get((row["email"] or "").strip().lower())      # by email address only
            if person is None:
                not_matched.add(row["email"] or row["login"])
                continue
            contributor_team_id = group_of_email.get((row["email"] or "").strip().lower())
            if contributor_team_id is None:
                not_placed.add(row["email"])
                continue
            if contributor_team_id == team["id"]:
                continue                                                          # one of the team's own people
            other_team_ids.add(contributor_team_id)
        names = sorted(_team_name(facts, team_id) for team_id in other_team_ids)
        on = len(other_team_ids) > limit
        limit_text = _tag(f"more than {limit:g} other {'team' if limit == 1 else 'teams'}", starting)
        sentence = (f"Contributors from {count_of(len(other_team_ids), 'other team', 'other teams')}"
                    f"{' (' + _shown(names) + ')' if names else ''} made commits in this team's "
                    f"{count_of(len(repo_names), 'repo', 'repos')} in {month}. The driver is ON when {limit_text} do.")
        if not_matched:
            sentence += (f" {count_of(len(not_matched), 'contributor', 'contributors')} couldn't be matched to a person in HR "
                         f"by email address, so {'is' if len(not_matched) == 1 else 'are'} not counted.")
        if not_placed:
            sentence += (f" {count_of(len(not_placed), 'contributor is', 'contributors are')} in HR but not in an L4 team, "
                         "so not counted.")
        answers[team["id"]] = {"on": on, "value": len(other_team_ids), "value_text": count_of(len(other_team_ids), "other team", "other teams"),
                               "sentence": sentence, "sources": sources, "not_matched": len(not_matched)}
    return answers


def _team_name(facts, team_id):
    return facts["team_name"].get(team_id, team_id)


# ---------------------------------------------------------------------------------------------------
# A driver Tech Risk defines on the Risk site: a team figure and a test (list "Calculations you define")
# ---------------------------------------------------------------------------------------------------

def defined_settings(from_files=None):
    """{driver code: {"figure", "test", "number_or_share"}} for the calculations Tech Risk has defined and not retired."""
    from trust import editable                           # imported here: editable reads the drivers through this file
    return {entry["key"]: entry["values"] for entry in editable.entries_now("calculations", from_files) if not entry["retired"]}


def defined_places(code, defined=None):
    """[the figure's place, the test's place] for a defined driver, or None when the driver isn't one."""
    from trust import codelinks
    values = (defined if defined is not None else defined_settings()).get(code)
    if values is None or values["figure"] not in team_figures.FIGURES or values["test"] not in team_figures.TESTS:
        return None
    figure = team_figures.FIGURES[values["figure"]]
    test = team_figures.TESTS[values["test"]]
    places = [codelinks.place("risk/team_figures.py", figure["function"].__name__, f"Works out: {figure['label'].lower()}"),
              codelinks.place("risk/team_figures.py", test["function"].__name__, f"Test: {test['label'].lower()}")]
    return [place for place in places if place]


def defined_calculation(facts, values, code, cfg=None):
    """One defined driver for every team: the figure, then the test, then ON, OFF or not known with a sentence.

        figure = the team figure Tech Risk picked        test = the test Tech Risk picked
        driver is ON when the team's figure passes the test (against the prevailing median or a number)
    """
    figure_found = team_figures.FIGURES[values["figure"]]["function"](facts)
    test_name, setting = values["test"], values.get("number_or_share")
    test_function = team_figures.TESTS[test_name]["function"]
    words_for = team_figures.TESTS[test_name]["words"]

    known = {team_id: found["number"] for team_id, found in figure_found.items() if found["number"] is not None}
    median, why_not = None, None
    if team_figures.uses_the_median(test_name):
        median, why_not = prevailing_median(code, list(known.values()), cfg)
    answers = {}
    for team in facts["teams"]:
        found = figure_found[team["id"]]
        number = found["number"]
        if number is None:
            answers[team["id"]] = _not_known(found["why_not"], found["sources"])
        elif team_figures.uses_the_median(test_name) and median is None:
            answers[team["id"]] = _not_known(why_not, found["sources"])
        else:
            on = test_function(number, median, setting)
            sentence = f"{found['piece']}; {words_for(median, len(known), setting)}, so this is {'ON' if on else 'OFF'}."
            answers[team["id"]] = {"on": on, "value": round(number, 1), "value_text": found["value_text"],
                                   "sentence": sentence, "sources": found["sources"]}
    return answers


CALCULATION_FUNCTIONS = {LEGACY_LANGUAGES: legacy_languages, TCC_ADOPTION: tcc_adoption, HEADCOUNT: headcount,
                         LANGUAGE_VARIETY: language_variety, OTHER_TEAMS: other_teams}


# ---------------------------------------------------------------------------------------------------
# All of it for a month
# ---------------------------------------------------------------------------------------------------

def compute(month, driver_rules, entries=None, changed_codes=(), cfg=None, defined=None):
    """Each team's answer for each driver the site answers from data:

        {team id: {driver code: {"on": True/False/None, "value", "value_text", "sentence", "sources", ...}}}

    driver_rules  as files.driver_rules gives them (a driver with no questionnaire field is answered from data)
    entries       the "Drivers answered from data" entries (editable.entries_now); None = the file's starting values
    changed_codes drivers whose values were changed on the editing page: their numbers are no longer "starting values"
    defined       {driver code: figure, test and number} from "Calculations you define". A driver with a built-in
                  calculation is never taken from here.
    """
    if month is None:
        return {}
    data_codes = [code for code, rule in sorted(driver_rules.items()) if files.answered_from_data(rule)]
    facts = facts_for(month)
    settings = settings_by_code(entries, data_codes)
    defined = defined or {}
    results = {team["id"]: {} for team in facts["teams"]}
    for code in data_codes:
        setting = settings.get(code)
        if setting is None and code in defined:
            for team_id, answer in defined_calculation(facts, defined[code], code, cfg).items():
                results[team_id][code] = answer
            continue
        if setting is None:
            for team in facts["teams"]:
                results[team["id"]][code] = _not_known("no calculation answers this driver yet")
            continue
        starting = code not in changed_codes
        for team_id, answer in CALCULATION_FUNCTIONS[setting["calculation"]](facts, setting, code, starting, cfg).items():
            results[team_id][code] = answer
    return results


def states_of(results_for_team):
    """{driver code: True, False or None}: what the rating reads."""
    return {code: answer["on"] for code, answer in (results_for_team or {}).items()}


_cache = {"key": None, "results": {}}


def current(driver_rules, from_files=None):
    """{team id: {code: answer}} for the newest mapped month with the settings in force (the file's values, then the
    editing page's saved changes). Cached until the month is mapped again, a setting changes, or the drivers change
    (which drivers there are, and which of them are answered from data)."""
    from trust import editable                           # imported here: editable reads the drivers through this file
    month = groups.hr_month()
    rows = storage.list_changes("data-drivers")
    entries = editable.entries_now("data-drivers", from_files) if rows else None
    defined = defined_settings(from_files)
    run = storage.run_info("mapped", month) or {}
    codes_answered_from_data = tuple(code for code, rule in sorted(driver_rules.items()) if files.answered_from_data(rule))
    key = (str(storage.store_dir()), storage.using_database(), month, run.get("at"), len(rows),
           json.dumps(settings_file(), sort_keys=True), tuple(sorted(driver_rules)), codes_answered_from_data,
           json.dumps(defined, sort_keys=True))
    if _cache["key"] != key:
        changed = {row["key"] for row in rows}
        _cache.update(key=key, results=compute(month, driver_rules, entries, changed, defined=defined))
    return _cache["results"]


# ---------------------------------------------------------------------------------------------------
# Handing the answers to the rating, which reads them like any other driver answer
# ---------------------------------------------------------------------------------------------------

def assess_with_data(risks, driver_rules, form_questions, saved, settings, placements, previous_result, results_for_team):
    """assess.assess_group, with the data drivers' ON or OFF given as their answers. A driver that is not known gets
    no answer, so it is never counted as on. The rating rules are not touched: each data driver is read as "is yes".
    The result also keeps what each data driver said (result["data_drivers"]), so a past result still names its source."""
    states = states_of(results_for_team)
    rules, extra_questions, extra_answers = dict(driver_rules), [], {}
    for code, state in states.items():
        rule = driver_rules.get(code)
        if rule is None or not files.answered_from_data(rule):
            continue
        rules[code] = {**rule, "field": code, "test": drivers.IS_YES, "value": None}
        extra_questions.append({"field": code, "driver": code, "section": "", "text": rule.get("rationale") or code,
                                "kind": question_list.YES_NO, "yes_means_field_is": True})
        if state is not None:
            extra_answers[code] = "yes" if state else "no"
    result = assess.assess_group(risks, rules, list(form_questions) + extra_questions, {**saved, **extra_answers},
                                 settings, placements, previous_result)
    result["answers"] = dict(saved)                      # only what people answered: the form's status compares this
    result["data_drivers"] = {code: {"on": answer["on"], "value_text": answer["value_text"], "sentence": answer["sentence"],
                                     "sources": answer["sources"]} for code, answer in (results_for_team or {}).items()}
    return result


def for_the_form(driver_rules, team_id, from_files=None):
    """What the form's "answered from data" box shows for one team: one entry per data driver."""
    results = current(driver_rules, from_files).get(team_id) or {}
    defined = defined_settings(from_files)
    shown = []
    for code, rule in sorted(driver_rules.items()):
        if not files.answered_from_data(rule):
            continue
        answer = results.get(code) or _not_known("no calculation answers this driver yet")
        shown.append({"code": code, "plain_name": rule.get("rationale") or code, "state": answer["on"], "value_text": answer["value_text"],
                      "sentence": answer["sentence"], "sources": answer["sources"],
                      "place": code_places.driver_place_for_code(code, defined)})
    return shown
