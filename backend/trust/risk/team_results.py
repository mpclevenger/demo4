"""A team's risk results page: the data, the insights and the CSV (owner, 17 Nov 2026).

Everyone who can open the Risk site can open any team's results page. The page shows WHAT is on and WHY (the answers,
and TRUST's own data). It never shows how drivers combine into a rating: no rules, thresholds or triggers.

A risk has NO single combined rating (owner, 17 Nov 2026). Each risk shows what the rating code already works out:
likelihood, impact (the highest of financial, client and regulatory), whether it is Elevated, and whether it applies.

Two kinds of team:
    L4 team   a Risk group. Its results are its newest submitted assessment, read through current_rules (so the
              "rate with today's rules" switch is honoured).
    L3 team   its L4 teams pooled. A driver is on for the L3 team when it is on in ANY of its L4 teams' newest submitted
              assessments (a driver answered from data too). The L3 team is then rated once, as one team, with the
              same rating code as every other team (rating.rate_group). There is no second rating logic here.

The routes are in site.py: GET /api/risk/teams, /api/risk/teams/<id>/results and /api/risk/teams/<id>/results.csv.
Design and decisions: docs/design/21_risk_site.md, "Team results pages".
"""
import csv
import io
import re

from trust import evidence, linking, storage
from trust.risk import assess, current_rules, groups, questions as question_list, rating, signoff
from trust.risk.registers import load_registers
from trust.words import count_of, moment_of, today_text

LIKELIHOOD_LEVELS = ["Critical", "High", "Medium", "Low"]           # highest first
DOESNT_APPLY = "Doesn't apply"
HIGH_LIKELIHOODS = ("Critical", "High")
PERVASIVE_CATEGORIES_IF_NOT_SET = 3                                # used only when the setting is missing from the settings
MOST_DRIVERS_NAMED = 3                                             # drivers named in a "what drives it" card
MOST_PERVASIVE_CARDS = 2
MOST_CARDS = 5
FEWEST_CARDS = 2
DIMENSION_OF_KIND = {"financial_impact": "financial", "client_impact": "client", "regulatory_impact": "regulatory"}
DIMENSIONS = list(DIMENSION_OF_KIND.values())
STATUS_WORDS = {assess.DRAFT: "In progress"}                       # the form's "Draft" reads "In progress" on these pages
CODE_IN_TEXT = re.compile(r"RD\d+", re.I)
CSV_HEADINGS = ["Team", "Category", "Risk ID", "Risk", "Elevated", "Likelihood", "Impact", "Driver for", "Driver",
                "Driver name", "Dimension", "Where it came from"]
L4_HEADING = "L4 team"


class NoSuchTeam(Exception):
    """The id is neither an L4 team nor an L3 team."""


# ---------------------------------------------------------------------------------------------------
# Small word helpers
# ---------------------------------------------------------------------------------------------------

def level_word(level):
    """HIGH -> High; None stays None."""
    return level.capitalize() if level else None


def category_of(domain):
    """A domain in title case. A word already written with capitals (IT, AI) is left alone."""
    words = str(domain or "Other").split()
    return " ".join(word.capitalize() if word.islower() else word for word in words)


def join_words(items):
    """['a', 'b', 'c'] -> 'a, b and c'."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def day_text(iso_text):
    """2026-11-12T09:30:00+00:00 -> 12 Nov 2026."""
    moment = moment_of(iso_text)
    return f"{moment.day} {moment:%b %Y}"


def month_text(month):
    """2026-10 -> October 2026."""
    year, number = month.split("-")
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
    return f"{names[int(number) - 1]} {year}"


def plain_name(name):
    """A driver's plain name without its closing full stop, so it reads well inside a sentence."""
    return str(name or "").strip().rstrip(".")


def likelihood_rank(likelihood):
    """Critical 3 ... Low 0; a risk that doesn't apply (None) is below Low."""
    return rating.rank(likelihood.upper()) if likelihood else -1


def empty_counts():
    return {"elevated": 0, "likelihood": {level: 0 for level in LIKELIHOOD_LEVELS}, "doesnt_apply": 0}


def counts_of(risk_rows):
    """{"elevated": n, "likelihood": {"Critical": n, ...}, "doesnt_apply": n} for a list of risk rows."""
    counts = empty_counts()
    for row in risk_rows:
        if not row["applies"]:
            counts["doesnt_apply"] += 1
            continue
        counts["likelihood"][row["likelihood"]] += 1
        if row["elevated"]:
            counts["elevated"] += 1
    return counts


# ---------------------------------------------------------------------------------------------------
# What a team's newest submitted assessment says
# ---------------------------------------------------------------------------------------------------

def snapshot_of(group, assessment_rows, answer_rows):
    """One L4 team's newest submitted assessment with what is needed to say where each driver came from. None when the
    team has not submitted."""
    if not assessment_rows:
        return None
    newest = assessment_rows[-1]
    drivers_on = {entry["code"] for entry in newest["result"]["drivers"]["on"]}
    return {"group": group, "assessment": newest, "result": newest["result"], "active": drivers_on,
            "answer_rows": [row for row in answer_rows if row["group_id"] == group["id"]]}


def rows_by_team(rows):
    """{group id: [rows, oldest first]}."""
    found = {}
    for row in rows:
        found.setdefault(row["group_id"], []).append(row)
    return found


def snapshots_for(group_list):
    """{group id: snapshot or None} for some L4 teams, reading the saved rows once."""
    assessments = rows_by_team(current_rules.assessments())
    answers = storage.risk_answers()
    return {group["id"]: snapshot_of(group, assessments.get(group["id"], []), answers) for group in group_list}


def status_of_team(group, assessment_rows, answer_rows, signoff_rows):
    """Not started, In progress, Submitted, Signed off or Sent back."""
    status = signoff.status_of(group["id"], answer_rows, assessment_rows, signoff_rows)
    return STATUS_WORDS.get(status, status)


# ---------------------------------------------------------------------------------------------------
# One risk as the page shows it
# ---------------------------------------------------------------------------------------------------

def dimensions_of(risk, code):
    """The kinds of impact whose scoring mentions this driver, in the usual order: ['financial', 'regulatory']."""
    found = []
    scoring = risk.get("impact_scoring") or {}
    for kind, dimension in DIMENSION_OF_KIND.items():
        for rule_text in (scoring.get(kind) or {}).values():
            if rule_text and code.upper() in [match.upper() for match in CODE_IN_TEXT.findall(str(rule_text))]:
                found.append(dimension)
                break
    return found


def risk_row(risk_id, risk, rated):
    """One risk with what the rating code worked out. `rated` is rating.rate_risk's answer (or a kept entry's)."""
    applies = bool(rated.get("applicable"))
    by_kind = rated.get("impact_by_kind") or {}
    return {"id": risk_id, "name": rated.get("name") or risk.get("name") or risk_id,
            "category": category_of(risk.get("domain") or rated.get("domain")),
            "description": " ".join(str(risk.get("description") or "").split()),
            "applies": applies,
            "likelihood": level_word(rated.get("likelihood")) if applies else None,
            "impact": level_word(rated.get("impact")) if applies else None,
            "impact_by_dimension": {DIMENSION_OF_KIND[kind]: level_word(by_kind.get(kind)) if applies else None
                                    for kind in DIMENSION_OF_KIND},
            "elevated": bool(rated.get("elevated")) if applies else False,
            "likelihood_codes": list(rated.get("likelihood_drivers_on") or []) if applies else [],
            "impact_codes": list(rated.get("impact_drivers_on") or []) if applies else [],
            "risk": risk}


def order_key(row):
    """Elevated first, then likelihood (Critical to Low), then impact, then category; a risk that doesn't apply is last."""
    return (not row["applies"], not row["elevated"], -likelihood_rank(row["likelihood"]), -likelihood_rank(row["impact"]),
            row["category"].lower(), row["id"])


# ---------------------------------------------------------------------------------------------------
# Where each driver came from
# ---------------------------------------------------------------------------------------------------

def answer_words(question, answer):
    """An answer as a person reads it: Yes, No, 4, or "Partly" in quotes."""
    if isinstance(answer, list):
        return join_words([f'"{item}"' for item in answer])
    kind = (question or {}).get("kind")
    if kind == question_list.YES_NO:
        return "Yes" if str(answer).strip().lower() in ("yes", "true", "y", "1") else "No"
    if kind == question_list.NUMBER:
        return str(answer)
    return f'"{answer}"'


def how_answered(snapshot, code, loaded):
    """How one driver came to be on for one L4 team: {"data": value text} or {"answer": words, "by", "on"}."""
    data = (snapshot["result"].get("data_drivers") or {}).get(code)
    if data and data.get("on") is True:
        return {"data": data["value_text"]}
    rule = loaded["driver_rules"].get(code) or {}
    fields = list(rule.get("fields") or [rule.get("field")])
    fields += [question["field"] for question in loaded["questions"] if question["driver"] == code]
    saved = snapshot["result"].get("answers") or {}
    fields = [field for index, field in enumerate(fields) if field and field in saved and field not in fields[:index]]
    if not fields:
        return {"answer": None, "by": None, "on": None}
    question_of = {question["field"]: question for question in loaded["questions"]}
    words = join_words([answer_words(question_of.get(field), saved[field]) for field in fields])
    assessed_at = moment_of(snapshot["assessment"]["at"])
    rows = [row for row in snapshot["answer_rows"] if row["question"] in fields and moment_of(row["at"]) <= assessed_at]
    newest = max(rows, key=lambda row: moment_of(row["at"])) if rows else None
    return {"answer": words, "by": newest["by"] if newest else None, "on": day_text(newest["at"]) if newest else None}


def sentence_for_one_team(found, month):
    """'Answered Yes by Emery Rook, 12 Nov 2026' or 'From TRUST data: 41 releases in October 2026'."""
    if "data" in found:
        return f"From TRUST data: {found['data']} in {month_text(month)}"
    if found["answer"] is None:
        return "Answered in the team's assessment"
    if found["by"] is None:
        return f"Answered {found['answer']}"
    return f"Answered {found['answer']} by {found['by']}, {found['on']}"


def piece_for_one_of_many(team_name, found, month):
    """'Lending Engineering: Yes (Emery Rook)' or 'Lending Engineering, from TRUST data: 41 releases in October 2026'."""
    if "data" in found:
        return f"{team_name}, from TRUST data: {found['data']} in {month_text(month)}"
    if found["answer"] is None:
        return f"{team_name}: answered"
    return f"{team_name}: {found['answer']}" + (f" ({found['by']})" if found["by"] else "")


# ---------------------------------------------------------------------------------------------------
# Building the page for any set of risk rows
# ---------------------------------------------------------------------------------------------------

class Context:
    """What the page needs once: the registers, the data month, the teams behind the page and who each driver is on in."""

    def __init__(self, loaded, month, snapshots):
        self.loaded = loaded
        self.month = month
        self.snapshots = snapshots                                  # the L4 teams that have submitted (an L4 page has one)

    def pervasive_at_least(self):
        value = self.loaded["settings"].get("pervasive_categories", PERVASIVE_CATEGORIES_IF_NOT_SET)
        return int(float(value))

    def driver_name(self, code):
        rule = self.loaded["driver_rules"].get(code) or {}
        return rule.get("rationale") or code

    def teams_with(self, code):
        """The L4 teams the driver is on in, in order."""
        return [s["group"]["name"] for s in self.snapshots if code in s["active"]]

    def source_of(self, code, pooled):
        """The plain sentence saying who answered, or which TRUST data said it."""
        on_in = [s for s in self.snapshots if code in s["active"]]
        if not pooled:
            return sentence_for_one_team(how_answered(on_in[0], code, self.loaded), self.month) if on_in else ""
        pieces = [piece_for_one_of_many(s["group"]["name"], how_answered(s, code, self.loaded), self.month) for s in on_in]
        return " · ".join(pieces)

    def is_from_data(self, code):
        return any(((s["result"].get("data_drivers") or {}).get(code) or {}).get("on") is True for s in self.snapshots
                   if code in s["active"])


def risk_with_drivers(row, context, pooled):
    """The risk row as the API sends it: its drivers with name, source (and dimension for impact)."""
    risk = row["risk"]
    likelihood_drivers = [{"code": code, "name": context.driver_name(code), "source": context.source_of(code, pooled)}
                          for code in row["likelihood_codes"]]
    impact_drivers = []
    for code in row["impact_codes"]:
        dimensions = dimensions_of(risk, code)
        impact_drivers.append({"code": code, "name": context.driver_name(code),
                               "dimension": dimensions[0] if dimensions else None, "dimensions": dimensions,
                               "source": context.source_of(code, pooled)})
    if pooled:
        for driver in likelihood_drivers + impact_drivers:
            driver["teams"] = context.teams_with(driver["code"])
    return {"id": row["id"], "name": row["name"], "category": row["category"], "description": row["description"],
            "applies": row["applies"], "likelihood": row["likelihood"], "impact": row["impact"],
            "impact_by_dimension": row["impact_by_dimension"], "elevated": row["elevated"],
            "likelihood_drivers": likelihood_drivers, "impact_drivers": impact_drivers, "by_l4": []}


def driver_summary(rows, context, pooled):
    """The drivers that are on, and where each one lands: {"likelihood": [...], "impact": [...]}."""
    threshold = context.pervasive_at_least()
    summary = {"likelihood": [], "impact": []}
    for kind, codes_name in (("likelihood", "likelihood_codes"), ("impact", "impact_codes")):
        where_of = {}
        for row in rows:
            for code in row[codes_name]:
                place = where_of.setdefault(code, {}).setdefault(row["category"], {"risks": 0, "dimensions": []})
                place["risks"] += 1
                if kind == "impact":
                    for dimension in dimensions_of(row["risk"], code):
                        if dimension not in place["dimensions"]:
                            place["dimensions"].append(dimension)
        for code in sorted(where_of):
            where = []
            for category, place in sorted(where_of[code].items()):
                entry = {"category": category, "risks": place["risks"]}
                if kind == "impact":
                    entry["dimensions"] = place["dimensions"]
                where.append(entry)
            summary[kind].append({"code": code, "name": context.driver_name(code), "source": context.source_of(code, pooled),
                                  "pervasive": len(where) >= threshold, "where": where,
                                  "teams": context.teams_with(code) if pooled else []})
    return summary


def totals_of_drivers(loaded):
    """How many different likelihood and impact drivers the risks list, for '7 of 14'."""
    likelihood, impact = set(), set()
    for risk in loaded["risks"].values():
        likelihood |= set(risk.get("likelihood_drivers") or [])
        impact |= set(risk.get("impact_drivers") or [])
    return {"likelihood": len(likelihood), "impact": len(impact)}


def categories_of(rows):
    """[{"name", "likelihood_drivers", "impact_drivers", "risks"}] for every category: the drivers on in it and the risks that apply."""
    found = {}
    for row in rows:
        entry = found.setdefault(row["category"], {"name": row["category"], "likelihood": set(), "impact": set(), "risks": 0})
        if row["applies"]:
            entry["risks"] += 1
            entry["likelihood"] |= set(row["likelihood_codes"])
            entry["impact"] |= set(row["impact_codes"])
    return [{"name": entry["name"], "likelihood_drivers": len(entry["likelihood"]), "impact_drivers": len(entry["impact"]),
             "risks": entry["risks"]} for _name, entry in sorted(found.items())]


# ---------------------------------------------------------------------------------------------------
# Insights: 2 to 5 cards in plain words. They never mention how a rating is worked out.
# ---------------------------------------------------------------------------------------------------

def named(context, code):
    return f"{plain_name(context.driver_name(code))} ({code})"


def top_drivers(focus, codes_name, context):
    """The drivers on in most of the focus risks (top few), as 'name (code)'."""
    seen = {}
    for row in focus:
        for code in row[codes_name]:
            seen[code] = seen.get(code, 0) + 1
    best = sorted(seen, key=lambda code: (-seen[code], code))[:MOST_DRIVERS_NAMED]
    return [named(context, code) for code in best]


def card_counts(applying, elevated, high_likelihood):
    """The first card: how many risks are Elevated or have a Critical or High likelihood, and which."""
    if not elevated and not high_likelihood:
        return {"head": "No Elevated risks", "body": f"{count_of(len(applying), 'risk')} apply to this team. None has a Critical or High likelihood."}
    likelihood_text = f"{count_of(len(high_likelihood), 'risk')} with a Critical or High likelihood"
    if elevated:
        head = f"{count_of(len(elevated), 'Elevated risk')} and {likelihood_text}"
    else:
        head = f"No Elevated risks; {likelihood_text}"
    body_pieces = []
    if elevated:
        body_pieces.append("Elevated: " + "; ".join(row["name"] for row in elevated) + ".")
    others = [row for row in high_likelihood if not row["elevated"]]
    if others:
        body_pieces.append("Critical or High likelihood: " + "; ".join(row["name"] for row in others) + ".")
    return {"head": head, "body": " ".join(body_pieces)}


def card_what_drives(focus, context):
    likelihood = top_drivers(focus, "likelihood_codes", context)
    impact = top_drivers(focus, "impact_codes", context)
    if not likelihood and not impact:
        return None
    pieces = []
    if likelihood:
        pieces.append("Likelihood: " + "; ".join(likelihood) + ".")
    if impact:
        pieces.append("Impact: " + "; ".join(impact) + ".")
    return {"head": "What drives the Elevated and High-likelihood risks", "body": " ".join(pieces)}


def pervasive_cards(applying, context, pooled):
    """Up to two drivers that reach at least `pervasive_categories` categories."""
    categories_with_a_risk = {row["category"] for row in applying}
    reach = {}
    for row in applying:
        for code in set(row["likelihood_codes"]) | set(row["impact_codes"]):
            entry = reach.setdefault(code, {"categories": set(), "risks": 0})
            entry["categories"].add(row["category"])
            entry["risks"] += 1
    threshold = context.pervasive_at_least()
    chosen = sorted((code for code in reach if len(reach[code]["categories"]) >= threshold),
                    key=lambda code: (-len(reach[code]["categories"]), -reach[code]["risks"], code))[:MOST_PERVASIVE_CARDS]
    cards = []
    for code in chosen:
        found = reach[code]
        body = (f"On in {len(found['categories'])} of {count_of(len(categories_with_a_risk), 'category', 'categories')} "
                f"({join_words(sorted(found['categories']))}). It is behind {found['risks']} of the "
                f"{count_of(len(applying), 'risk')} that apply.")
        if pooled:
            teams = context.teams_with(code)
            body += f" On in {len(teams)} of {count_of(len(context.snapshots), 'L4 team')}."
        if context.is_from_data(code):
            body += " This one comes from TRUST's own data, not the questionnaire."
        cards.append({"head": f"Pervasive: {named(context, code)}", "body": body})
    return cards


def own_rows_of_each_team(context, rows_of_team):
    """{risk id: [{"team_id", "team", "likelihood", "impact", "elevated", "applies"}]} for the L4 teams, each on its own."""
    found = {}
    for snapshot in context.snapshots:
        for risk_id, row in rows_of_team[snapshot["group"]["id"]].items():
            found.setdefault(risk_id, []).append({"team_id": snapshot["group"]["id"], "team": snapshot["group"]["name"],
                                                  "likelihood": row["likelihood"], "impact": row["impact"],
                                                  "elevated": row["elevated"], "applies": row["applies"]})
    return found


def higher_together_card(rows, own, context, l3_name):
    """A risk that is more serious for the L3 team than for any L4 team on its own, and why: each team brings drivers."""
    best = None
    for row in rows:
        if not row["applies"] or not own.get(row["id"]):
            continue
        teams = own[row["id"]]
        newly_elevated = row["elevated"] and not any(team["elevated"] for team in teams)
        higher_likelihood = likelihood_rank(row["likelihood"]) > max(likelihood_rank(team["likelihood"]) for team in teams)
        if not (newly_elevated or higher_likelihood):
            continue
        score = (newly_elevated, likelihood_rank(row["likelihood"]) - max(likelihood_rank(team["likelihood"]) for team in teams))
        if best is None or score > best[0]:
            best = (score, row, newly_elevated)
    if best is None:
        return None
    _score, row, newly_elevated = best
    brought = []
    for snapshot in context.snapshots:
        only_here = [code for code in row["likelihood_codes"] + row["impact_codes"]
                     if code in snapshot["active"] and context.teams_with(code) == [snapshot["group"]["name"]]]
        if only_here:
            brought.append(f"{snapshot['group']['name']}: " + "; ".join(named(context, code) for code in only_here[:MOST_DRIVERS_NAMED]))
    what = "Elevated" if newly_elevated else f"{row['likelihood']} likelihood"
    body = (f"{row['name']} is {what} for {l3_name} as a whole, though no L4 team is that high on its own. "
            "Drivers from different L4 teams add up when they are put together.")
    if brought:
        body += " What each team brings: " + " · ".join(brought) + "."
    return {"head": f"Higher together: {row['name']}", "body": body}


def carries_card(rows, own, context, l3_name):
    """The L4 team that clearly carries a category: it alone matches the L3 team's rating of the risks that stand out there."""
    standing_out = [row for row in rows if row["applies"] and (row["elevated"] or row["likelihood"] in HIGH_LIKELIHOODS)]
    if len(context.snapshots) < 2:
        return None
    for category in sorted({row["category"] for row in standing_out}):
        risks_here = [row for row in standing_out if row["category"] == category]
        matches = {snapshot["group"]["name"]: [] for snapshot in context.snapshots}
        for row in risks_here:
            for team in own.get(row["id"], []):
                same_elevated = team["elevated"] == row["elevated"]
                if team["applies"] and likelihood_rank(team["likelihood"]) >= likelihood_rank(row["likelihood"]) and same_elevated:
                    matches[team["team"]].append(row)
        teams_that_match = [team for team, found in matches.items() if found]
        if len(teams_that_match) != 1:
            continue
        team_name = teams_that_match[0]
        carried = matches[team_name]
        snapshot = next(s for s in context.snapshots if s["group"]["name"] == team_name)
        own_drivers = []
        for row in carried:
            own_drivers += [code for code in row["likelihood_codes"] + row["impact_codes"] if code in snapshot["active"]]
        best = sorted(set(own_drivers), key=lambda code: (-own_drivers.count(code), code))[:MOST_DRIVERS_NAMED]
        names = join_words([row["name"] for row in carried])
        body = (f"In {category}, {names} stand{'s' if len(carried) == 1 else ''} out for {l3_name}, and {team_name} is the only "
                f"L4 team that is that high on its own.")
        if best:
            body += " Its drivers: " + "; ".join(named(context, code) for code in best) + "."
        return {"head": f"{team_name} carries {category}", "body": body}
    return None


def where_the_risks_are_card(rows, applying):
    by_category = {}
    for row in applying:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
    listed = join_words([f"{category} {number}" for category, number in sorted(by_category.items())]) or "none"
    return {"head": f"{len(applying)} of {count_of(len(rows), 'risk')} apply", "body": f"By category: {listed}."}


def insights_for(rows, context, pooled, own=None, l3_name=None):
    """The cards, in the order a person reads them, 2 to 5."""
    applying = [row for row in rows if row["applies"]]
    elevated = [row for row in applying if row["elevated"]]
    high_likelihood = [row for row in applying if row["likelihood"] in HIGH_LIKELIHOODS]
    focus = [row for row in applying if row["elevated"] or row["likelihood"] in HIGH_LIKELIHOODS]
    cards = [card_counts(applying, elevated, high_likelihood)]
    if focus:
        drives = card_what_drives(focus, context)
        if drives:
            cards.append(drives)
    pervasive = pervasive_cards(applying, context, pooled)
    together = higher_together_card(rows, own, context, l3_name) if pooled else None
    carries = carries_card(rows, own, context, l3_name) if pooled else None
    for card in pervasive[:1] + [together] + pervasive[1:] + [carries]:
        if card:
            cards.append(card)
    if len(cards) < FEWEST_CARDS:
        cards.append(where_the_risks_are_card(rows, applying))
    return cards[:MOST_CARDS]


# ---------------------------------------------------------------------------------------------------
# The teams
# ---------------------------------------------------------------------------------------------------

def hr_people(month):
    """(people, l3 level) of the newest HR month."""
    mapped = storage.load_month("mapped", month) or {}
    people = (((mapped.get("feeds") or {}).get("hr")) or {}).get("people") or []
    return people, linking.l3_level(mapped.get("settings_used"))


def l3_teams():
    """{L3 id: {"id", "name", "groups": [the L4 teams]}} in the site's order."""
    found = {}
    for group in groups.load():
        entry = found.setdefault(group["l3_id"], {"id": group["l3_id"], "name": group["l3_name"], "groups": []})
        entry["groups"].append(group)
    return found


def l4_entry(group, month, snapshot, status, risk_rows):
    """An L4 team as the list shows it."""
    return {"id": group["id"], "name": group["name"], "lead": groups.lead_name(group, month),
            "people": len(groups.members(group, month)), "status": status,
            "assessed_on": snapshot["assessment"]["at"][:10] if snapshot else None,
            "counts": counts_of(risk_rows) if snapshot else None}


def rows_from_result(result, loaded):
    """{risk id: risk row} from one L4 assessment result."""
    return {risk_id: risk_row(risk_id, loaded["risks"].get(risk_id) or {}, rated) for risk_id, rated in result["risks"].items()}


def rows_pooled(active, loaded):
    """{risk id: risk row} for an L3 team: every risk rated once with the pooled drivers, by the normal rating code."""
    rated_all = rating.rate_group(loaded["risks"], active, loaded["settings"])
    return {risk_id: risk_row(risk_id, loaded["risks"][risk_id], rated) for risk_id, rated in rated_all.items()}


def l3_overall_status(statuses):
    if statuses and all(status == signoff.SIGNED_OFF for status in statuses):
        return signoff.SIGNED_OFF
    if signoff.SENT_BACK in statuses:
        return signoff.SENT_BACK
    if any(status in (assess.SUBMITTED, signoff.SIGNED_OFF) for status in statuses):
        return assess.SUBMITTED
    if any(status == "In progress" for status in statuses):
        return "In progress"
    return assess.NOT_STARTED


def build_everything():
    """The things every answer needs, read once: registers, month, snapshots, statuses and L4 rows."""
    loaded = load_registers()
    month = groups.hr_month()
    teams = l3_teams()
    all_groups = [group for team in teams.values() for group in team["groups"]]
    assessments = rows_by_team(current_rules.assessments())
    answers = storage.risk_answers()
    signoffs = storage.risk_signoffs()
    snapshots, statuses, rows = {}, {}, {}
    for group in all_groups:
        assessment_rows = assessments.get(group["id"], [])
        snapshots[group["id"]] = snapshot_of(group, assessment_rows, answers)
        statuses[group["id"]] = status_of_team(group, assessment_rows, [a for a in answers if a["group_id"] == group["id"]],
                                               [s for s in signoffs if s["group_id"] == group["id"]])
        if snapshots[group["id"]]:
            rows[group["id"]] = rows_from_result(snapshots[group["id"]]["result"], loaded)
    return {"loaded": loaded, "month": month, "teams": teams, "snapshots": snapshots, "statuses": statuses, "rows": rows,
            "signoffs": signoffs, "assessments": assessments}


def l3_rows(team, everything):
    """(context, rows) for an L3 team, pooled from its L4 teams that have submitted. (None, {}) when none has."""
    submitted = [everything["snapshots"][group["id"]] for group in team["groups"] if everything["snapshots"][group["id"]]]
    if not submitted:
        return None, {}
    pooled_active = set().union(*(snapshot["active"] for snapshot in submitted))
    context = Context(everything["loaded"], everything["month"], submitted)
    return context, rows_pooled(pooled_active, everything["loaded"])


def l3_entry(team, everything, month):
    """An L3 team as the list shows it, with its L4 teams."""
    people, l3_level = hr_people(month) if month else ([], 3)
    placed = [person for person in people if person.get("family_id") == team["id"]]
    leaders = [person.get("worker") or person["sam_account"] for person in placed if person.get("reporting_level") == l3_level]
    l4_entries = [l4_entry(group, month, everything["snapshots"][group["id"]], everything["statuses"][group["id"]],
                           list(everything["rows"].get(group["id"], {}).values())) for group in team["groups"]]
    _context, rows = l3_rows(team, everything)
    return {"id": team["id"], "name": team["name"], "lead": " and ".join(leaders) or None, "people": len(placed),
            "l4_teams": l4_entries, "counts": counts_of(rows.values()) if rows else None}


def list_teams():
    """GET /api/risk/teams: the L3 teams with their L4 teams and counts."""
    everything = build_everything()
    return {"ok": True, "l3_teams": [l3_entry(team, everything, everything["month"]) for team in everything["teams"].values()]}


def signed_off_of(group, everything):
    """{"by", "on"} when the team's newest assessment is signed off, else None."""
    assessment_rows = everything["assessments"].get(group["id"], [])
    decision = signoff.short_summary(group["id"], assessment_rows, [s for s in everything["signoffs"] if s["group_id"] == group["id"]])
    if decision and decision["state"] == signoff.SIGNED_OFF:
        return {"by": decision["by"], "on": decision["at"][:10]}
    return None


def not_assessed_answer(team_block, message):
    return {"ok": True, "team": team_block, "assessed": False, "message": message, "counts": empty_counts(), "insights": [],
            "risks": [], "drivers": {"likelihood": [], "impact": []}, "drivers_total": {"likelihood": 0, "impact": 0},
            "categories": []}


def results_for(team_id):
    """GET /api/risk/teams/<id>/results. Raises NoSuchTeam for an id that is neither an L4 team nor an L3 team."""
    everything = build_everything()
    group = next((g for team in everything["teams"].values() for g in team["groups"] if g["id"] == team_id), None)
    if group is not None:
        return results_for_l4(group, everything)
    if team_id in everything["teams"]:
        return results_for_l3(everything["teams"][team_id], everything)
    raise NoSuchTeam()


def results_for_l4(group, everything):
    loaded, month = everything["loaded"], everything["month"]
    team = everything["teams"][group["l3_id"]]
    snapshot = everything["snapshots"][group["id"]]
    status = everything["statuses"][group["id"]]
    entry = l4_entry(group, month, snapshot, status, list(everything["rows"].get(group["id"], {}).values()))
    block = {"id": group["id"], "name": group["name"], "level": "L4", "lead": entry["lead"], "people": entry["people"],
             "l3": {"id": team["id"], "name": team["name"]}, "assessed_on": entry["assessed_on"],
             "signed_off": signed_off_of(group, everything), "status": status, "data_month": month,
             "rated_with_current_rules": current_rules.switch_is_on(loaded["settings"]), "l4_teams": []}
    if snapshot is None:
        return not_assessed_answer(block, f"{group['name']} has not submitted an assessment yet, so there are no results to show.")
    context = Context(loaded, month, [snapshot])
    rows = sorted(everything["rows"][group["id"]].values(), key=order_key)
    return finished_answer(block, rows, context, pooled=False, own=None, l3_name=None, message=None)


def results_for_l3(team, everything):
    loaded, month = everything["loaded"], everything["month"]
    entry = l3_entry(team, everything, month)
    statuses = [everything["statuses"][group["id"]] for group in team["groups"]]
    assessed_days = [l4["assessed_on"] for l4 in entry["l4_teams"] if l4["assessed_on"]]
    block = {"id": team["id"], "name": team["name"], "level": "L3", "lead": entry["lead"], "people": entry["people"], "l3": None,
             "assessed_on": max(assessed_days) if assessed_days else None, "signed_off": None,
             "status": l3_overall_status(statuses), "data_month": month,
             "rated_with_current_rules": current_rules.switch_is_on(loaded["settings"]), "l4_teams": entry["l4_teams"]}
    context, pooled_rows = l3_rows(team, everything)
    if context is None:
        return not_assessed_answer(block, f"None of {team['name']}'s L4 teams has submitted an assessment yet, so there are no results to show.")
    rows = sorted(pooled_rows.values(), key=order_key)
    own = own_rows_of_each_team(context, {s["group"]["id"]: everything["rows"][s["group"]["id"]] for s in context.snapshots})
    waiting = len(team["groups"]) - len(context.snapshots)
    message = None
    if waiting:
        message = f"Based on {len(context.snapshots)} of {count_of(len(team['groups']), 'L4 team')} that have submitted so far."
    return finished_answer(block, rows, context, pooled=True, own=own, l3_name=team["name"], message=message)


def finished_answer(block, rows, context, pooled, own, l3_name, message):
    """The page's data once the rows are in order."""
    risks = []
    for row in rows:
        shown = risk_with_drivers(row, context, pooled)
        if pooled:
            shown["by_l4"] = [{"team_id": team["team_id"], "team": team["team"], "likelihood": team["likelihood"],
                               "impact": team["impact"], "elevated": team["elevated"]} for team in (own or {}).get(row["id"], [])]
        risks.append(shown)
    answer = {"ok": True, "team": block, "assessed": True, "message": message, "counts": counts_of(rows),
              "insights": insights_for(rows, context, pooled, own, l3_name), "risks": risks,
              "drivers": driver_summary(rows, context, pooled), "drivers_total": totals_of_drivers(context.loaded),
              "categories": categories_of(rows)}
    return answer


# ---------------------------------------------------------------------------------------------------
# The CSV: one row per risk and driver
# ---------------------------------------------------------------------------------------------------

def csv_rows(answer):
    """The CSV as a list of rows (headings first). A risk with no driver on gets one row with the driver columns empty."""
    team = answer["team"]
    is_l3 = team["level"] == "L3"
    headings = CSV_HEADINGS + ([L4_HEADING] if is_l3 else [])
    out = [headings]
    for risk in answer["risks"]:
        base = [team["name"], risk["category"], risk["id"], risk["name"], "Yes" if risk["elevated"] else "No",
                risk["likelihood"] or DOESNT_APPLY, risk["impact"] or ("" if not risk["applies"] else "Not rated")]
        driver_lines = [("Likelihood", driver) for driver in risk["likelihood_drivers"]]
        driver_lines += [("Impact", driver) for driver in risk["impact_drivers"]]
        if not driver_lines:
            out.append(base + ["", "", "", "", ""] + ([""] if is_l3 else []))
            continue
        for kind, driver in driver_lines:
            dimension = ", ".join(word.capitalize() for word in driver.get("dimensions") or []) if kind == "Impact" else ""
            line = base + [kind, driver["code"], driver["name"], dimension, driver["source"]]
            if is_l3:
                line.append(", ".join(driver.get("teams") or []))
            out.append(line)
    return out


def csv_text(answer):
    """The CSV as text. No cell can start with = + - @ (a spreadsheet would run it as a formula)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for row in csv_rows(answer):
        writer.writerow([evidence._cell(cell) for cell in row])
    return buffer.getvalue()


def csv_file_name(answer):
    """'<team name> risk results <yyyy-mm-dd>.csv', with anything a file name can't hold taken out."""
    clean = "".join(letter for letter in answer["team"]["name"] if letter.isalnum() or letter in " -&_.").strip()
    return f"{clean or 'Team'} risk results {today_text()}.csv"
