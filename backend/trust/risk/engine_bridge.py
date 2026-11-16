"""The engine bridge: read what the risk engine rated for a group, and set it beside the site's own rating.

The site rates every risk itself. The risk engine stays as a bridge so the two can be compared; the list of
differences shows where they disagree.

Two files meet here:

    engine OUTPUT   one JSON per assessed group, schema_version "2.0". Read by read_engine_output.
    engine INPUT    the questionnaire answers the engine reads. Its exact layout is NOT known yet.
                    Wanted: confirm this layout with the engine's owner. It is built in one place: engine_input_layout.

The comparison, for each risk, gives one result:

    Same         the engine and the site agree
    Different    one of them says Critical or High and the other says something else (the reason is in words)
    Site only    the site rates it Medium or Low (or says it does not apply) and the engine has no rating to match.
                 Medium, Low and "does not apply" are new on the site, so they are not differences.
    Engine only  the engine rated a risk the site's risk files do not have

Nothing here changes how a rating is worked out. The site's reasons are read back from the steps explain.py wrote.
"""
import hashlib
import json

from trust.risk import drivers, rating
from trust.words import count_of

SCHEMA_VERSION = "2.0"
SAME = "Same"
DIFFERENT = "Different"
SITE_ONLY = "Site only"
ENGINE_ONLY = "Engine only"
RESULT_ORDER = [DIFFERENT, ENGINE_ONLY, SAME, SITE_ONLY]          # the order the page lists them in
SITE_ONLY_REASON = "The site rates this risk Medium or Low. The engine has no rating for it, and Medium and Low are new on the site."

# The levels the engine and the site must agree on. Medium and Low are new on the site.
MATCHED_LEVELS = ["HIGH", "CRITICAL"]
LARGEST_FILE_MEGABYTES = 5
LARGEST_FILE_BYTES = LARGEST_FILE_MEGABYTES * 1024 * 1024
NO_LEVEL_WORDS = ("N/A", "NA", "NONE", "NOT APPLICABLE")       # what an engine file may say for "not rated"
LAYOUT_STATUS = "Wanted: confirm this layout with the engine's owner."


class CannotRead(ValueError):
    """The engine's file can't be used. The message says why, in plain words."""


# ---------------------------------------------------------------------------------------------------
# Reading the engine's output
# ---------------------------------------------------------------------------------------------------

def file_hash(raw_bytes):
    """A fingerprint of the uploaded file, so the same file can be told apart from a different one."""
    return hashlib.sha256(raw_bytes).hexdigest()


def level_from(word, where, problems):
    """'high', 'HIGH' or ' High ' -> 'HIGH'. Nothing, or a word that is not a level, -> None (with a problem noted)."""
    if word is None or str(word).strip() == "":
        return None
    level = str(word).strip().upper()
    if level in rating.LEVELS:
        return level
    if level in NO_LEVEL_WORDS:
        return None
    problems.append(f"{where}: the level '{word}' isn't one of Low, Medium, High or Critical, so it was read as no rating.")
    return None


def yes_or_no_from(value):
    """True, False, or None when the engine didn't say."""
    return drivers.as_yes_no(value) if value is not None else None


def read_risk(risk_id, entry, problems):
    """One risk from the engine's file: {"likelihood", "impact", "applicable", "drivers"}."""
    if not isinstance(entry, dict):
        problems.append(f"Risk {risk_id}: the engine's entry isn't a set of fields, so it was left out.")
        return None
    likelihood = level_from(entry.get("likelihood"), f"Risk {risk_id} likelihood", problems)
    impact = level_from(entry.get("impact"), f"Risk {risk_id} impact", problems)
    applicable = yes_or_no_from(entry.get("applicable"))
    if applicable is None:                                # not said: it applies when the engine rated it
        applicable = bool(likelihood or impact)
    driver_notes = {}
    raw_drivers = entry.get("drivers")
    if isinstance(raw_drivers, dict):
        for code, detail in raw_drivers.items():
            detail = detail if isinstance(detail, dict) else {}
            driver_notes[str(code)] = {"name": detail.get("name"), "commentary": detail.get("commentary")}
    return {"likelihood": likelihood, "impact": impact, "applicable": applicable, "drivers": driver_notes}


def read_scope(document):
    """Which business unit and processes the engine was told about. All optional."""
    assessment = document.get("assessment")
    scope = (assessment or {}).get("selected_scope") if isinstance(assessment, dict) else None
    scope = scope if isinstance(scope, dict) else {}
    business_unit = scope.get("business_unit") or scope.get("business_units") or scope.get("business unit")
    if isinstance(business_unit, list):
        business_unit = ", ".join(str(part) for part in business_unit)
    return {"business_unit": business_unit,
            "processes": [str(name) for name in scope.get("processes") or []]}


def read_engine_output(raw_bytes):
    """Read and check an engine output file. Returns the parsed result, or raises CannotRead in plain words.

    Only the risks are needed. Anything else that is missing is left out and noted in "problems".
    """
    if len(raw_bytes) > LARGEST_FILE_BYTES:
        raise CannotRead(f"That file is larger than {LARGEST_FILE_MEGABYTES} MB, so it doesn't look like an engine output file.")
    try:
        document = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise CannotRead("That file isn't JSON the site can read. Upload the engine's output file for one team, as it came out of the engine.")
    if not isinstance(document, dict):
        raise CannotRead("That file is JSON, but it isn't an engine output file (it should be one set of fields with a 'risks' section).")
    raw_risks = document.get("risks")
    if not isinstance(raw_risks, dict) or not raw_risks:
        raise CannotRead("That file has no 'risks' section, so there is nothing to compare. Is it the engine's output file for one team?")

    problems = []
    version = document.get("schema_version")
    if version is None:
        problems.append("The file doesn't say its schema_version. The site expects 2.0 and read it that way.")
    elif str(version) != SCHEMA_VERSION:
        problems.append(f"The file's schema_version is {version}, and the site expects {SCHEMA_VERSION}. It was read as {SCHEMA_VERSION}; check the differences with that in mind.")

    risks = {}
    for risk_id, entry in raw_risks.items():
        read = read_risk(str(risk_id), entry, problems)
        if read is not None:
            risks[str(risk_id)] = read

    active = document.get("active_drivers")
    if isinstance(active, list):
        active_drivers = sorted({str(code).strip().upper() for code in active})
    else:
        active_drivers = None
        problems.append("The file has no list of active_drivers, so the drivers can't be compared.")

    return {"schema_version": str(version) if version is not None else None,
            "active_drivers": active_drivers, "scope": read_scope(document), "risks": risks,
            "summary": document.get("summary") if isinstance(document.get("summary"), (dict, str)) else None,
            "problems": problems}


# ---------------------------------------------------------------------------------------------------
# The engine's input (the layout is Wanted: confirm with the engine's owner)
# ---------------------------------------------------------------------------------------------------

def engine_input_layout(group, answers_by_field):
    """The one place that decides what the download looks like. Change it here when the engine's owner says what it reads.

    group              the team: id, name
    answers_by_field   {"RD01": True, "RD12": "4"}, as questions.answers_by_field gives them (the driver rules' own reading)
    """
    answers = {}
    for field, answer in sorted(answers_by_field.items()):
        number = drivers.as_number(answer)
        answers[field] = answer if isinstance(answer, bool) else (number if number is not None else answer)
    return {"_layout": LAYOUT_STATUS,
            "group": {"id": group["id"], "name": group["name"]},
            "answers": answers}


# ---------------------------------------------------------------------------------------------------
# Comparing with the site
# ---------------------------------------------------------------------------------------------------

def say(level):
    return level.title() if level else "no rating"


def levels_of(entry):
    """The likelihood and impact the engine or the site gave a risk, or None for each when it doesn't apply."""
    if not entry or not entry.get("applicable"):
        return {"applicable": False, "likelihood": None, "impact": None}
    return {"applicable": True, "likelihood": entry.get("likelihood"), "impact": entry.get("impact")}


def judge_one_level(engine_level, site_level):
    """Same, Different or Site only for likelihood (or impact) of one risk.

    Critical and High must match. When neither side says Critical or High, the engine's lack of a rating is
    not a difference: Medium and Low are new on the site."""
    if engine_level == site_level:
        return SAME
    one_side_is_matched = engine_level in MATCHED_LEVELS or site_level in MATCHED_LEVELS
    if one_side_is_matched:
        return DIFFERENT
    if engine_level is None:
        return SITE_ONLY
    return DIFFERENT                                     # the engine rated something the site doesn't (or rated it differently)


def site_step_lines(site_entry, title):
    """The site's own words for a step (explain.py wrote them), for the reason."""
    for step in (site_entry or {}).get("steps") or []:
        if step.get("title") == title:
            return list(step.get("lines") or [])
    return []


def driver_hint(risk, engine_active, site_active):
    """Drivers of this risk that are on in only one of the two: often the cause of a difference."""
    if risk is None or engine_active is None:
        return None
    own = rating.own_drivers(risk)
    engine_only = sorted((own & set(engine_active)) - set(site_active))
    site_only = sorted((own & set(site_active)) - set(engine_active))
    parts = []
    if engine_only:
        parts.append(f"{', '.join(engine_only)} {'is' if len(engine_only) == 1 else 'are'} on in the engine but not on the site")
    if site_only:
        parts.append(f"{', '.join(site_only)} {'is' if len(site_only) == 1 else 'are'} on on the site but not in the engine")
    if not parts:
        return "The same drivers are on in both, so the difference is in the rules, not the answers."
    return "Drivers that differ for this risk: " + "; ".join(parts) + "."


def reasons_for(kind, engine, site, site_entry, risk, engine_active, site_active):
    """Plain sentences for a risk whose likelihood or impact is Different."""
    reasons = []
    if engine["applicable"] != site["applicable"]:
        if site["applicable"]:
            reasons.append(f"The engine says this risk does not apply; the site says it does (likelihood {say(site['likelihood'])}, impact {say(site['impact'])}).")
            reasons.extend(site_step_lines(site_entry, "Does it apply?"))
        else:
            reasons.append("The engine rates this risk; the site says it does not apply to this team.")
            reasons.extend(site_step_lines(site_entry, "Does it apply?"))
    for dimension, title in (("likelihood", "Likelihood"), ("impact", "Impact")):
        if kind[dimension] != DIFFERENT or engine["applicable"] != site["applicable"]:
            continue
        reasons.append(f"The engine says {say(engine[dimension])} {dimension}; the site says {say(site[dimension])}.")
        site_lines = site_step_lines(site_entry, title)
        if site_lines:
            reasons.append(f"How the site rated {dimension}: " + " ".join(site_lines))
    hint = driver_hint(risk, engine_active, site_active)
    if hint:
        reasons.append(hint)
    return reasons


def compare_risk(risk_id, engine_entry, site_entry, risk, engine_active, site_active):
    """One row of the comparison."""
    engine = levels_of(engine_entry)
    site = levels_of(site_entry)
    name = (site_entry or {}).get("name") or (risk or {}).get("name") or risk_id
    row = {"risk_id": risk_id, "name": name, "engine": engine if engine_entry else None, "site": site if site_entry else None,
           "reasons": [], "result": SAME}

    if site_entry is None:
        row["result"] = ENGINE_ONLY
        row["reasons"] = ["The engine rated this risk, but the site's risk files don't have it. Download the risks and drivers from the site, or check they are the same set."]
        return row

    if not engine_entry and not site["applicable"]:
        return row                                       # neither side rates it
    if engine["applicable"] != site["applicable"]:
        # One side says it applies and the other says it doesn't.
        the_rating_is_matched = any(level in MATCHED_LEVELS for level in (engine["likelihood"], engine["impact"], site["likelihood"], site["impact"]))
        row["result"] = DIFFERENT if (the_rating_is_matched or engine["applicable"]) else SITE_ONLY
        if row["result"] == DIFFERENT:
            row["reasons"] = reasons_for({"likelihood": DIFFERENT, "impact": DIFFERENT}, engine, site, site_entry, risk, engine_active, site_active)
        else:
            row["reasons"] = [SITE_ONLY_REASON]
        return row

    kind = {"likelihood": judge_one_level(engine["likelihood"], site["likelihood"]),
            "impact": judge_one_level(engine["impact"], site["impact"])}
    if DIFFERENT in kind.values():
        row["result"] = DIFFERENT
        row["reasons"] = reasons_for(kind, engine, site, site_entry, risk, engine_active, site_active)
    elif SITE_ONLY in kind.values():
        row["result"] = SITE_ONLY
        row["reasons"] = [SITE_ONLY_REASON]
    return row


def compare_drivers(engine_active, site_on, driver_names):
    """Drivers on in one and not the other. driver_names is {code: plain name}."""
    if engine_active is None:
        return None
    engine_set, site_set = set(engine_active), set(site_on)
    return {"on_in_engine_only": [{"code": code, "text": driver_names.get(code, code)} for code in sorted(engine_set - site_set)],
            "on_on_site_only": [{"code": code, "text": driver_names.get(code, code)} for code in sorted(site_set - engine_set)]}


def counts_of(rows):
    counts = {SAME: 0, DIFFERENT: 0, SITE_ONLY: 0, ENGINE_ONLY: 0}
    for row in rows:
        counts[row["result"]] += 1
    return {"same": counts[SAME], "different": counts[DIFFERENT], "site_only": counts[SITE_ONLY], "engine_only": counts[ENGINE_ONLY]}


def sentence_for(counts):
    """'7 risks the same, 1 different, 2 site only' (units on every count)."""
    parts = [f"{count_of(counts['same'], 'risk')} the same", f"{counts['different']} different", f"{counts['site_only']} site only"]
    if counts["engine_only"]:
        parts.append(f"{counts['engine_only']} engine only")
    return ", ".join(parts)


def compare(engine_run, assessment, risks, driver_names=None):
    """The side-by-side for one team.

    engine_run   the kept engine run: {"id", "at", "by", "file_hash", "parsed"}
    assessment   the group's newest site assessment: {"id", "at", "by", "result"}
    risks        the risk files, {risk id: risk}, for the drivers of each risk
    """
    parsed = engine_run["parsed"]
    result = assessment["result"]
    site_on = [entry["code"] for entry in result["drivers"]["on"]]
    engine_active = parsed["active_drivers"]
    driver_names = driver_names or {entry["code"]: entry["text"] for entry in result["drivers"]["on"]}

    rows = []
    for risk_id in sorted(set(parsed["risks"]) | set(result["risks"])):
        rows.append(compare_risk(risk_id, parsed["risks"].get(risk_id), result["risks"].get(risk_id),
                                 (risks or {}).get(risk_id), engine_active, site_on))
    rows.sort(key=lambda row: (RESULT_ORDER.index(row["result"]), row["risk_id"]))

    counts = counts_of(rows)
    notes = list(parsed["problems"])
    return {"engine_run": {"id": engine_run["id"], "at": engine_run["at"], "by": engine_run["by"],
                           "file_hash": engine_run["file_hash"], "scope": parsed["scope"]},
            "assessment": {"id": assessment["id"], "at": assessment["at"], "by": assessment["by"]},
            "rows": rows, "counts": counts, "summary": sentence_for(counts),
            "drivers": compare_drivers(engine_active, site_on, driver_names), "notes": notes}
