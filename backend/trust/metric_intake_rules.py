"""Metric intake: the plain checks and calculations. No Flask, no storage.

A metric starts as Wanted (we want it and it isn't there yet), becomes In progress (agreed and being built)
and, only after the usual metric approval, Measured (counted and scored). This file holds:

  - the record's fields and which stage needs which (A);
  - the standard layout version 1, a team sends its numbers in (B): the Totals shape and the Items shape,
    and the checks each row goes through.

Nothing here scores anything. A record, a send and a check never change a score or put a metric on the scorecard.
Every check is one small function with a sentence above it, and a worked example in tests/test_metric_intake.py.
"""
import datetime
import re

from .words import tidy_spaces

# ---- the stages ----

WANTED = "Wanted"
IN_PROGRESS = "In progress"
MEASURED = "Measured"
STAGES = (WANTED, IN_PROGRESS, MEASURED)
STAGES_THAT_CAN_RECEIVE = (IN_PROGRESS, MEASURED)

# ---- the choices ----

UNITS = ("%", "per 10 apps", "per 100 releases")                    # the same three the metric proposal form offers
DIRECTIONS = {"higher": "Higher is better", "lower": "Lower is better"}
KEY_TYPES = ("application", "repository", "person")
KEY_TYPE_WORDS = {"application": "an application", "repository": "a repository", "person": "a person"}
SHAPES = {"totals": "Totals", "items": "Items"}
CADENCES = {"monthly": "Monthly", "quarterly": "Quarterly"}
DEFAULT_CADENCE = "monthly"
ARRIVALS = {"api": "The team sends it (API)", "pull": "Tech Risk collects it (pull)", "file": "File, for now"}
ARRIVAL_THAT_NEEDS_A_SERVICE_ACCOUNT = "api"
CHOICE_FIELDS = {"direction": DIRECTIONS, "key_type": KEY_TYPES, "shape": SHAPES, "cadence": CADENCES, "arrival": ARRIVALS}

# ---- the limits, by name ----

MAX_NAME_LENGTH = 200
MAX_SENTENCE_LENGTH = 400
MAX_LABEL_LENGTH = 200
MAX_SHORT_TEXT_LENGTH = 200
MAX_NOTE_LENGTH = 1000
MAX_KEY_LENGTH = 300
MAX_ROWS_IN_ONE_SEND = 200000
SERVICE_ACCOUNT_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._$-]{0,63}"
MONTH_PATTERN = r"\d{4}-(0[1-9]|1[0-2])"

# ---- the record's fields: (key, plain label), by the stage that needs them ----

WANTED_FIELDS = (
    ("name", "Metric name"),
    ("tells_leadership", "What it tells leadership"),
    ("building_block", "Building block"),
    ("provider_team", "Provider team"),
    ("contact_name", "Contact name"),
    ("system", "System the data lives in"),
)
IN_PROGRESS_FIELDS = (
    ("counted_label", "What is counted"),
    ("measured_against_label", "What it is measured against"),
    ("unit", "Unit"),
    ("direction", "Direction (higher or lower is better)"),
    ("key_type", "What ties each row to a team (application, repository or person)"),
    ("shape", "Shape (Totals or Items)"),
    ("cadence", "How often it is sent"),
    ("arrival", "How it arrives"),
    ("service_account", "Service account that will send it"),
    ("approved_by", "Who approved on the provider's side"),
    ("approved_on", "Date the provider approved"),
)
ALL_FIELD_KEYS = tuple(k for k, _ in WANTED_FIELDS + IN_PROGRESS_FIELDS)
FIELD_LABELS = dict(WANTED_FIELDS + IN_PROGRESS_FIELDS)
FIELD_LIMITS = {"name": MAX_NAME_LENGTH, "tells_leadership": MAX_SENTENCE_LENGTH, "provider_team": MAX_SHORT_TEXT_LENGTH,
                "contact_name": MAX_SHORT_TEXT_LENGTH, "system": MAX_SHORT_TEXT_LENGTH,
                "counted_label": MAX_LABEL_LENGTH, "measured_against_label": MAX_LABEL_LENGTH,
                "approved_by": MAX_SHORT_TEXT_LENGTH}


def user_name_only(sam_account):
    """'CORP\\svc-lending' or 'svc-lending@corp' -> 'svc-lending', lower case, the same way access.py reads a name."""
    text = tidy_spaces(sam_account)
    text = text.split("\\")[-1].split("@")[0]
    return text.lower()


def date_is_well_formed(text):
    """A date written YYYY-MM-DD that exists on the calendar: '2026-10-31' yes, '2026-02-30' no."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(text or "")):
        return False
    try:
        datetime.date.fromisoformat(str(text))
    except ValueError:
        return False
    return True


def month_is_well_formed(month):
    """A month written YYYY-MM: '2026-10' yes, '2026-13' and 'Oct 2026' no."""
    return bool(re.fullmatch(MONTH_PATTERN, str(month or "")))


# ---- (A) the record ----

def tidy_fields(given):
    """Only the fields a record has, with the spaces tidied. Anything else is left out."""
    tidy = {}
    for key in ALL_FIELD_KEYS:
        if key in given and given[key] is not None:
            tidy[key] = user_name_only(given[key]) if key == "service_account" else tidy_spaces(given[key])
    for key, choices in CHOICE_FIELDS.items():
        if tidy.get(key):
            tidy[key] = as_choice_key(tidy[key], choices)
    return tidy


def as_choice_key(value, choices):
    """A pick-one value as its key: "Totals", "totals" and "TOTALS" all become "totals". The key or the word shown
    on screen is accepted, in any capitals. Anything else is returned as it was, for the check to refuse."""
    wanted = value.strip().lower()
    for key in choices:
        word = choices[key] if isinstance(choices, dict) else key
        if wanted in (key.lower(), word.lower()):
            return key
    return value


def problems_with_values(fields, block_names):
    """What is wrong with the values given (not what is missing): a plain sentence each. Empty fields are not
    checked here; `missing_fields` says what is missing."""
    problems = []
    for key, limit in FIELD_LIMITS.items():
        if len(fields.get(key, "")) > limit:
            problems.append(f"{FIELD_LABELS[key]} is longer than {limit} characters. Please shorten it.")
    if fields.get("building_block") and fields["building_block"] not in block_names:
        problems.append(f"Building block must be one of: {', '.join(block_names)}.")
    if fields.get("unit") and fields["unit"] not in UNITS:
        problems.append(f"Unit must be one of: {', '.join(UNITS)}.")
    if fields.get("direction") and fields["direction"] not in DIRECTIONS:
        problems.append("Direction must be 'higher is better' or 'lower is better'.")
    if fields.get("key_type") and fields["key_type"] not in KEY_TYPES:
        problems.append(f"What ties each row to a team must be one of: {', '.join(KEY_TYPES)}.")
    if fields.get("shape") and fields["shape"] not in SHAPES:
        problems.append("Shape must be Totals or Items.")
    if fields.get("cadence") and fields["cadence"] not in CADENCES:
        problems.append(f"How often it is sent must be one of: {', '.join(CADENCES.values())}.")
    if fields.get("arrival") and fields["arrival"] not in ARRIVALS:
        problems.append(f"How it arrives must be one of: {'; '.join(ARRIVALS.values())}.")
    if fields.get("service_account") and not re.fullmatch(SERVICE_ACCOUNT_PATTERN, fields["service_account"]):
        problems.append("The service account is its SAM account name, for example svc-lending (letters, numbers, dots, dashes).")
    if fields.get("approved_on") and not date_is_well_formed(fields["approved_on"]):
        problems.append("The approval date must be written like 2026-11-15.")
    return problems


def missing_fields(fields, stage):
    """The plain labels of what a record still needs before it can be at this stage. Wanted needs the six Wanted
    fields; In progress and Measured also need the In progress fields (the data contract). The service account is
    only needed when the team sends the numbers itself."""
    needed = list(WANTED_FIELDS)
    if stage in STAGES_THAT_CAN_RECEIVE:
        needed += list(IN_PROGRESS_FIELDS)
    missing = []
    for key, label in needed:
        if key == "service_account" and fields.get("arrival") != ARRIVAL_THAT_NEEDS_A_SERVICE_ACCOUNT:
            continue
        if key == "cadence":
            continue                                                  # monthly unless said otherwise
        if not tidy_spaces(fields.get(key, "")):
            missing.append(label)
    return missing


def with_defaults(fields):
    """The fields with the cadence filled in (monthly) when nobody chose one."""
    filled = dict(fields)
    if not filled.get("cadence"):
        filled["cadence"] = DEFAULT_CADENCE
    return filled


def move_problem(current_stage, new_stage, fields):
    """Why a record can't move to this stage, in plain words, or None when it can. A record moves one step at a
    time; going back is allowed. In progress needs the In progress fields complete."""
    if new_stage not in STAGES:
        return f"The stage must be one of: {', '.join(STAGES)}."
    if new_stage == current_stage:
        return None
    if current_stage == WANTED and new_stage == MEASURED:
        return "A metric goes from Wanted to In progress first. Measured comes after the usual metric approval."
    missing = missing_fields(fields, new_stage)
    if missing:
        return f"To move this to {new_stage}, fill in: {'; '.join(missing)}."
    return None


# ---- (B) the standard layout, version 1 ----

TOTALS_COLUMNS = ("intake_id", "month", "key_type", "key", "count", "total", "as_of")
ITEMS_COLUMNS = ("intake_id", "month", "item_id", "item_name", "key_type", "key", "counted", "as_of")
COLUMNS_OF = {"totals": TOTALS_COLUMNS, "items": ITEMS_COLUMNS}
COLUMNS_A_ROW_MAY_LEAVE_OUT = ("intake_id", "month")                 # taken from the send itself when left out


def normalize_row(row):
    """A row with its column names tidied (capitals, spaces and dashes don't matter) and its values as text."""
    tidy = {}
    for name, value in (row or {}).items():
        key = re.sub(r"[\s\-]+", "_", str(name).strip().lower())
        tidy[key] = tidy_spaces(value) if not isinstance(value, bool) else ("yes" if value else "no")
    return tidy


def whole_number(value, column):
    """(number, None) when the value is a whole number of 0 or more ('12'), else (None, the reason)."""
    text = tidy_spaces(value)
    if not re.fullmatch(r"\d{1,12}", text):
        return None, f"{column} must be a whole number such as 7 (it was '{text}')."
    return int(text), None


def count_is_not_more_than_total(count, total):
    """The reason when the count is more than the total ('9 counted out of 7' is not possible), else None."""
    if count > total:
        return f"The count ({count}) is more than the total ({total}). The count is the part of the total that was counted."
    return None


def key_type_is_known_and_matches(row_key_type, record_key_type):
    """The reason when the row's key_type is not application, repository or person, or is not the one on the
    record, else None."""
    if row_key_type not in KEY_TYPES:
        return f"key_type must be application, repository or person (it was '{row_key_type}')."
    if row_key_type != record_key_type:
        return f"key_type is {row_key_type}, but this metric ties each row to {KEY_TYPE_WORDS[record_key_type]}. Use key_type {record_key_type}."
    return None


def record_can_receive(record, intake_id):
    """The reason when this intake_id can't take numbers: it doesn't exist, or it is still Wanted. Else None."""
    if record is None:
        return f"There is no metric {intake_id or '(no intake_id given)'}. Check the intake_id with Tech Risk."
    if record["stage"] not in STAGES_THAT_CAN_RECEIVE:
        return (f"{record['id']} is {record['stage']}, which means it isn't agreed yet, so TRUST can't take numbers for it. "
                "Ask Tech Risk to move it to In progress first.")
    return None


def counted_is_yes_or_no(value):
    """(True, None) for yes, (False, None) for no, else (None, the reason)."""
    text = tidy_spaces(value).lower()
    if text == "yes":
        return True, None
    if text == "no":
        return False, None
    return None, f"counted must be yes or no (it was '{text}')."


def count_and_total_from_items(items):
    """(count, total) for a list of Items rows: count = the rows with counted = yes, total = all the rows.
    Four rows, three of them yes, give a count of 3 and a total of 4."""
    count = 0
    total = 0
    for item in items:
        total = total + 1
        if item["counted"]:
            count = count + 1
    return count, total


def _common_row_problem(row, columns, record, send_intake_id, send_month):
    """The reason a row can't be used for the parts every shape shares, else None."""
    for column in columns:
        if column in COLUMNS_A_ROW_MAY_LEAVE_OUT:
            continue
        if not tidy_spaces(row.get(column, "")):
            return f"{column} is empty."
    row_intake_id = str(row.get("intake_id") or send_intake_id).strip().upper()   # mi-002 is MI-002
    if row_intake_id != send_intake_id:
        return f"intake_id is {row_intake_id}, but this send is for {send_intake_id}."
    row_month = row.get("month") or send_month
    if not month_is_well_formed(row_month):
        return f"month must be written like 2026-10 (it was '{row_month}')."
    if row_month != send_month:
        return f"month is {row_month}, but this send is for {send_month}."
    problem = key_type_is_known_and_matches(row["key_type"].lower(), record["key_type"])
    if problem:
        return problem
    if len(row["key"]) > MAX_KEY_LENGTH:
        return f"key is longer than {MAX_KEY_LENGTH} characters."
    if not date_is_well_formed(row["as_of"]):
        return f"as_of must be written like 2026-11-02 and be a real date (it was '{row['as_of']}')."
    return None


def check_totals_rows(rows, record, send_intake_id, send_month):
    """Check a Totals send, one row at a time. Returns (kept rows, rows set aside). A row set aside carries its
    reason and its position in the file; none is dropped without being listed. One row per team per month: a
    second row for the same key is set aside."""
    kept = []
    set_aside = []
    seen_keys = set()
    for position, given in enumerate(rows, start=1):
        row = normalize_row(given)
        problem = _common_row_problem(row, TOTALS_COLUMNS, record, send_intake_id, send_month)
        count = total = None
        if problem is None:
            count, problem = whole_number(row["count"], "count")
        if problem is None:
            total, problem = whole_number(row["total"], "total")
        if problem is None:
            problem = count_is_not_more_than_total(count, total)
        key_for_duplicates = (row.get("key_type", "").lower(), row.get("key", "").lower())
        if problem is None and key_for_duplicates in seen_keys:
            problem = f"{row['key']} already has a row in this send. Send one row per team per month."
        if problem is not None:
            set_aside.append({"row_number": position, "row": given, "reason": problem})
            continue
        seen_keys.add(key_for_duplicates)
        kept.append({"row_number": position, "key_type": row["key_type"].lower(), "key": row["key"],
                     "count": count, "total": total, "as_of": row["as_of"]})
    return kept, set_aside


def check_items_rows(rows, record, send_intake_id, send_month):
    """Check an Items send, one row at a time. Returns (kept rows, rows set aside). An item_id may appear once
    in a send; a second row with the same item_id is set aside."""
    kept = []
    set_aside = []
    seen_items = set()
    for position, given in enumerate(rows, start=1):
        row = normalize_row(given)
        problem = _common_row_problem(row, ITEMS_COLUMNS, record, send_intake_id, send_month)
        counted = None
        if problem is None:
            counted, problem = counted_is_yes_or_no(row["counted"])
        if problem is None and row["item_id"].lower() in seen_items:
            problem = f"item_id {row['item_id']} already has a row in this send. Send each item once."
        if problem is not None:
            set_aside.append({"row_number": position, "row": given, "reason": problem})
            continue
        seen_items.add(row["item_id"].lower())
        kept.append({"row_number": position, "item_id": row["item_id"], "item_name": row["item_name"],
                     "key_type": row["key_type"].lower(), "key": row["key"], "counted": counted,
                     "as_of": row["as_of"]})
    return kept, set_aside


def totals_from_items(kept_items):
    """One count and total per team from the kept Items rows (what the team's number is made of):
    [{key_type, key, count, total, as_of}], in the order the teams first appear. as_of is the newest date in the group."""
    groups = {}
    for item in kept_items:
        groups.setdefault((item["key_type"], item["key"].lower()), []).append(item)
    totals = []
    for (key_type, _), items in groups.items():
        count, total = count_and_total_from_items(items)
        totals.append({"key_type": key_type, "key": items[0]["key"], "count": count, "total": total,
                       "as_of": max(item["as_of"] for item in items)})
    return totals


def check_rows(shape, rows, record, send_intake_id, send_month):
    """Check a send in either shape. Returns (kept rows, rows set aside, totals per team)."""
    if shape == "items":
        kept, set_aside = check_items_rows(rows, record, send_intake_id, send_month)
        totals = totals_from_items(kept)
    else:
        kept, set_aside = check_totals_rows(rows, record, send_intake_id, send_month)
        totals = [{k: v for k, v in row.items() if k != "row_number"} for row in kept]
    return kept, set_aside, totals


def summary_sentence(kept_count, set_aside_count, replaced):
    """The plain one-line answer to a send."""
    rows = "row" if kept_count == 1 else "rows"
    text = f"Received. {kept_count} {rows} kept"
    if set_aside_count:
        aside = "row was" if set_aside_count == 1 else "rows were"
        text += f", {set_aside_count} {aside} set aside (see the reasons below)"
    text += "."
    if replaced:
        text += " This replaces the earlier send for this month; the earlier one is kept in the history."
    return text + " Nothing here changes any score."
