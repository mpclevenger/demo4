"""Seeding the Risk site from uploaded files (owner, 16 Nov 2026; docs/design/21_risk_site.md, "Uploading the risk files").

Tech Risk uploads three kinds of file. Each is read, checked, shown in plain words, and only then loaded:

    risks       the engine's own risk files (YAML, one or more, or a .zip of them), each holding risks keyed by id
    drivers     the engine's driver_mapping.yaml (risk_drivers: RD01: trigger, questionnaire_fields, rationale)
    questions   the owner's own questionnaire YAML, read with config/risk_questionnaire_map.json

The readers are tolerant, the way TRUST's column_maps.json is for the provider's files: the real file is the layout.
Case and punctuation in names don't matter, a close spelling is matched, an unknown key is a note and never a refusal.
A thing that can't be used (a trigger that can't be read, a question for a driver that doesn't exist) is a plain
problem sentence and that one item is left out; the rest still loads.

Loading makes the site the golden source:
    risks and drivers   every load is kept in risk_seed_upload with the registers after it; registers.load_registers
                        reads the newest load before the risk files folder. A load adds new items and replaces
                        changed ones; nothing is removed.
    questions           go into the "questions" editing list as rows with who, when and the reason (so they have
                        history there), the way editable.save does the first load from a file.

Nothing here changes how a rating is worked out.
"""
import difflib
import hashlib
import io
import json
import os
import pathlib
import re
import zipfile
import zlib

import yaml

from trust import config, editable, storage
from trust.intake.common import loads_tolerant
from trust.risk import drivers, expressions, files, questions as question_list, registers
from trust.risk.registers import DRIVERS, RISKS
from trust.words import count_of, tidy_spaces

QUESTIONS = "questions"
KINDS = (RISKS, DRIVERS, QUESTIONS)

LARGEST_FILE_BYTES = 2_000_000
MOST_UNPACKED_BYTES = 20_000_000                 # all the files of one .zip together, once unpacked
MOST_FILES_IN_ONE_UPLOAD = 500
MOST_ITEMS_SHOWN = 200                           # items listed on the page; the counts always cover all of them
CLOSE_SPELLING = 0.85                            # how alike two names must be to count as the same (0 to 1)
CLOSE_FIELD_NAME = 0.7                           # how alike a field name must be to be offered as "Did you mean ...?"
MAP_FILE_NAME = "risk_questionnaire_map.json"
READING_A_ZIP_FAILS = (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error)

NEW, CHANGED, SAME, RESTORED = "New", "Changed", "Same", "Restored"


# ---------------------------------------------------------------------------------------------------
# Small helpers: names, files, plain sentences
# ---------------------------------------------------------------------------------------------------

def plain_name(name):
    """A key as compared: no case, spaces, dashes, underscores or other marks. 'Switches-On' -> 'switcheson'."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def find_key(document, names):
    """The key of `document` (a dict) that is one of `names`, best name first. Returns (key, spelled_differently).
    Exact (ignoring case and marks) first, then a close spelling. (None, False) when nothing matches."""
    if not isinstance(document, dict):
        return None, False
    by_plain = {}
    for key in document:
        by_plain.setdefault(plain_name(key), key)
    for name in names:
        if plain_name(name) in by_plain:
            return by_plain[plain_name(name)], False
    for name in names:
        close = difflib.get_close_matches(plain_name(name), list(by_plain), n=1, cutoff=CLOSE_SPELLING)
        if close:
            return by_plain[close[0]], True
    return None, False


def json_safe(value):
    """The value as it will be kept: dates and other YAML types become text."""
    return json.loads(json.dumps(value, default=str))


def file_hash(documents):
    """SHA-256 of the uploaded files (name and text of each, in name order), so the same upload is recognized."""
    digest = hashlib.sha256()
    for name, text in sorted(documents):
        digest.update(name.encode("utf-8") + b"\0" + text.encode("utf-8") + b"\0")
    return digest.hexdigest()


def documents_from_uploads(uploads):
    """The uploaded files as [(name, text)], with .zip files opened. Returns (documents, problems, notes)."""
    documents, problems, notes = [], [], []
    for name, raw in uploads:
        is_zip = name.lower().endswith(".zip") or raw[:2] == b"PK"
        if not is_zip:
            _add_document(documents, problems, name, raw)
            continue
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            problems.append(f"{name} is not a .zip file this page can open.")
            continue
        left_out = 0
        unpacked_total = 0
        listed = [info for info in archive.infolist() if not info.is_dir()]
        if len(listed) > MOST_FILES_IN_ONE_UPLOAD:
            problems.append(f"{name} holds {len(listed):,} files. This page reads at most {MOST_FILES_IN_ONE_UPLOAD}.")
            continue
        for info in listed:
            inner = info.filename
            leaf = inner.rsplit("/", 1)[-1]
            if inner.startswith("__MACOSX") or leaf.startswith("."):
                continue
            if not leaf.lower().endswith((".yaml", ".yml")):
                left_out += 1
                continue
            if info.file_size > LARGEST_FILE_BYTES:
                problems.append(f"{name}: {inner} is bigger than {LARGEST_FILE_BYTES // 1_000_000} MB, so it was not read.")
                continue
            unpacked_total += info.file_size
            if unpacked_total > MOST_UNPACKED_BYTES:
                problems.append(f"{name} unpacks to more than {MOST_UNPACKED_BYTES // 1_000_000} MB, so the rest of it was not read.")
                break
            try:
                raw = archive.read(info)
            except READING_A_ZIP_FAILS:
                problems.append(f"{name}: {inner} can't be read from the .zip (it may be damaged or need a password), so it was not read.")
                continue
            _add_document(documents, problems, f"{name}: {inner}", raw)
        if left_out:
            notes.append(f"{name}: {count_of(left_out, 'file that is', 'files that are')} not YAML, so left out.")
    return documents, problems, notes


def _add_document(documents, problems, name, raw):
    if len(raw) > LARGEST_FILE_BYTES:
        problems.append(f"{name} is bigger than {LARGEST_FILE_BYTES // 1_000_000} MB, so it was not read.")
        return
    try:
        documents.append((name, raw.decode("utf-8-sig")))
    except UnicodeDecodeError:
        problems.append(f"{name} is not plain text (UTF-8), so it was not read.")


class AnchorsNotAllowed(yaml.YAMLError):
    """The file uses a YAML anchor or alias (&name, *name)."""


class LoaderWithoutAliases(yaml.SafeLoader):
    """YAML's safe reader, except that it refuses aliases. A few lines of aliases can expand to gigabytes
    (the "billion laughs" file), and the engine's files have no use for them."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise AnchorsNotAllowed("anchors and aliases are not allowed")
        return super().compose_node(parent, index)


def yaml_documents(name, text, problems):
    """Every YAML document in one file, or [] with a plain problem when it can't be read."""
    try:
        return [document for document in yaml.load_all(text, Loader=LoaderWithoutAliases) if document is not None]
    except AnchorsNotAllowed:
        problems.append(f"{name} uses YAML anchors or aliases (&name, *name), which this page doesn't read. Write each value out in full.")
        return []
    except yaml.YAMLError as trouble:
        mark = getattr(trouble, "problem_mark", None)
        where = f" (near line {mark.line + 1})" if mark is not None else ""
        problems.append(f"{name} can't be read as YAML{where}.")
        return []


def stem_of(name):
    """The file name without folders or extension: 'a.zip: risks/air.ops.02.yaml' -> 'air.ops.02'."""
    leaf = name.rsplit(":", 1)[-1].strip().rsplit("/", 1)[-1]
    return leaf.rsplit(".", 1)[0] if leaf.lower().endswith((".yaml", ".yml", ".json")) else leaf


# ---------------------------------------------------------------------------------------------------
# What the site holds now, and the registers the site reads
# ---------------------------------------------------------------------------------------------------

def _same_rule(one, other):
    keys = ("field", "test", "value", "rationale", "questionnaire_fields")
    return all(one.get(key) == other.get(key) for key in keys)


# ---------------------------------------------------------------------------------------------------
# 1. Risk files
# ---------------------------------------------------------------------------------------------------

def read_risks(documents, problems, notes):
    """The risks in the uploaded files: {id: risk}. Anything wrong is added to `problems` or `notes`."""
    found = {}
    for name, text in documents:
        stem = stem_of(name)
        if stem == "driver_mapping":
            notes.append(f"{name} is the drivers file. Upload it under Driver rules, not here.")
            continue
        read_any = False
        for document in yaml_documents(name, text, problems):
            for risk_id, risk in config.risks_in_file(stem, document):
                read_any = True
                risk_id = str(risk_id).strip()
                if risk_id in found:
                    notes.append(f"{risk_id} is in more than one file. The last one read is used ({name}).")
                risk = {plain_name_key(key): value for key, value in risk.items()}
                found[risk_id], driver_problems = config.tidy_driver_lists(risk_id, risk)
                problems.extend(driver_problems)
                if not found[risk_id].get("name"):
                    notes.append(f"{risk_id} has no name, so its id is shown instead.")
        if not read_any and not any(name in problem for problem in problems):
            notes.append(f"{name} holds no risks. A risk has at least one of domain, category, name or description.")
    return json_safe(found)


def plain_name_key(key):
    """'Framework Mappings' and 'framework-mappings' are kept as framework_mappings, as TRAC reads them."""
    return str(key).strip().lower().replace(" ", "_").replace("-", "_")


def check_risk_upload(uploads):
    """Read and check uploaded risk files. Returns the result the page shows, and what a load would keep."""
    documents, problems, notes = documents_from_uploads(uploads)
    uploaded = read_risks(documents, problems, notes)
    current = registers.load_registers()
    held = current["from_files"]["risks"]
    rules = current["from_files"]["driver_rules"]

    merged = dict(held)
    items = []
    for risk_id, risk in sorted(uploaded.items()):
        if risk_id not in held:
            status = NEW
        elif json_safe(held[risk_id]) == risk:
            status = SAME
        else:
            status = CHANGED
        merged[risk_id] = risk
        items.append({"id": risk_id, "name": risk.get("name") or risk_id, "detail": risk.get("domain") or "", "status": status})
    notes.extend(files.check_risks(uploaded, rules) if uploaded else [])

    counts = status_counts(items)
    summary = f"{count_of(len(items), 'risk', 'risks')} read: {counts_words(counts)}." if items else "No risks were found."
    result = result_document(RISKS, documents, items, problems, notes, summary)
    return result, {"registers": merged, "changed": counts[NEW] + counts[CHANGED], "documents": documents}


def status_counts(items):
    counts = {NEW: 0, CHANGED: 0, SAME: 0, RESTORED: 0}
    for item in items:
        counts[item["status"]] += 1
    return counts


def counts_words(counts):
    parts = [f"{counts[NEW]} new", f"{counts[CHANGED]} changed", f"{counts[SAME]} the same as now"]
    if counts[RESTORED]:
        parts.append(f"{counts[RESTORED]} brought back")
    return ", ".join(parts)


def result_document(kind, documents, items, problems, notes, summary):
    """What the page is sent after a check."""
    return {"kind": kind, "files": [name for name, _text in documents], "summary": summary,
            "items": items[:MOST_ITEMS_SHOWN], "items_total": len(items),
            "problems": problems, "notes": notes, "file_hash": file_hash(documents),
            "counts": status_counts(items)}


# ---------------------------------------------------------------------------------------------------
# 2. Driver rules
# ---------------------------------------------------------------------------------------------------

TRIGGER_KEYS = ["trigger", "rule", "when", "turns_on"]
QUESTIONNAIRE_KEYS = ["questionnaire_fields", "questionnaire_field", "questions", "fields", "question_fields"]
RATIONALE_KEYS = ["rationale", "reason", "description", "meaning", "name"]
DRIVER_LIST_KEYS = ["risk_drivers", "drivers"]
LOOKS_LIKE_A_DRIVER_CODE = re.compile(r"^[A-Za-z]{1,4}\d{1,4}$")


def drivers_in_document(document):
    """The {code: details} part of a driver file: under risk_drivers, or the file's top level when it looks like one."""
    key, _spelled = find_key(document, DRIVER_LIST_KEYS)
    if key is not None and isinstance(document[key], dict):
        return document[key]
    if isinstance(document, dict) and document and all(LOOKS_LIKE_A_DRIVER_CODE.match(str(code)) for code in document):
        return document
    return None


def read_one_driver_rule(code, details, problems):
    """(the rule, the names of the keys that are not read) for one driver of the file. (None, []) with a problem
    added to `problems` when the driver can't be used."""
    if not isinstance(details, dict):
        problems.append(f"{code}: expected a trigger, questionnaire fields and a rationale, so it was left out.")
        return None, []
    keys_read = set()
    trigger_key, _spelled = find_key(details, TRIGGER_KEYS)
    if trigger_key is None:
        problems.append(f"{code} has no trigger, so it was left out.")
        return None, []
    keys_read.add(trigger_key)
    try:
        rule = drivers.rule_from_trigger(details[trigger_key])
    except ValueError:
        problems.append(f"{code}: the trigger {str(details[trigger_key])!r} can't be read, so it was left out. "
                        f"A trigger looks like (get('RD01') == True), (get(RD12)>=3) or (get(RD22)>prevailing(RD22)).")
        return None, []
    fields_key, _spelled = find_key(details, QUESTIONNAIRE_KEYS)
    fields = details.get(fields_key) if fields_key is not None else []
    if fields_key is not None:
        keys_read.add(fields_key)
    if isinstance(fields, str):
        fields = [piece.strip() for piece in fields.split(",") if piece.strip()]
    rationale_key, _spelled = find_key(details, RATIONALE_KEYS)
    if rationale_key is not None:
        keys_read.add(rationale_key)
    rule["rationale"] = tidy_spaces(details.get(rationale_key))
    rule["questionnaire_fields"] = [str(field) for field in (fields or [])]
    keys_not_read = [other for other in details if other not in keys_read and not str(other).startswith("_")]
    return rule, keys_not_read


def read_driver_rules(documents, problems, notes):
    """{code: rule} for every driver in the uploaded files that can be read. A rule is as files.driver_rules gives it."""
    rules = {}
    extra_keys = {}
    for name, text in documents:
        for document in yaml_documents(name, text, problems):
            listed = drivers_in_document(document)
            if listed is None:
                notes.append(f"{name} has no risk_drivers list, so no drivers were read from it.")
                continue
            for code, details in listed.items():
                code = str(code).strip().upper()          # rd01 and RD01 are the same driver; the rules write RD01
                rule, keys_not_read = read_one_driver_rule(code, details, problems)
                if rule is None:
                    continue
                if code in rules:
                    notes.append(f"{code} is in more than one place. The last one read is used.")
                rules[code] = rule
                for other in keys_not_read:
                    extra_keys[other] = extra_keys.get(other, 0) + 1
    for key, count in sorted(extra_keys.items()):
        notes.append(f"The key '{key}' is in {count_of(count, 'driver', 'drivers')} and isn't read, so it was ignored.")
    return rules


def check_driver_upload(uploads):
    documents, problems, notes = documents_from_uploads(uploads)
    uploaded = read_driver_rules(documents, problems, notes)
    current = registers.load_registers()
    held = current["from_files"]["driver_rules"]

    merged = dict(held)
    items = []
    for code, rule in sorted(uploaded.items()):
        if code not in held:
            status = NEW
        elif _same_rule(held[code], rule):
            status = SAME
        else:
            status = CHANGED
        merged[code] = rule
        items.append({"id": code, "name": rule["rationale"] or code, "detail": drivers.trigger_from_rule(rule), "status": status})
    if uploaded:
        notes.extend(files.check_risks(current["from_files"]["risks"], merged))
    counts = status_counts(items)
    from_data = sum(1 for rule in uploaded.values() if files.answered_from_data(rule))
    summary = (f"{count_of(len(items), 'driver', 'drivers')} read: {counts_words(counts)}. "
               f"{from_data} of them {'is' if from_data == 1 else 'are'} answered from data, with no question.") if items else "No drivers were found."
    new_with_questions = [code for code in uploaded if code not in held and uploaded[code]["questionnaire_fields"]]
    if new_with_questions and storage.list_changes(QUESTIONS):
        notes.append(f"{count_of(len(new_with_questions), 'new driver has', 'new drivers have')} a questionnaire field, but the "
                     f"questions list is already kept on the site, so a question for it is added from the questionnaire upload "
                     f"or on the Edit page.")
    result = result_document(DRIVERS, documents, items, problems, notes, summary)
    return result, {"registers": merged, "changed": counts[NEW] + counts[CHANGED], "documents": documents}


# ---------------------------------------------------------------------------------------------------
# 3. The questionnaire, read with config/risk_questionnaire_map.json
# ---------------------------------------------------------------------------------------------------

def map_path():
    return pathlib.Path(os.environ.get("TRUST_RISK_QUESTIONNAIRE_MAP")
                        or pathlib.Path(__file__).resolve().parents[3] / "config" / MAP_FILE_NAME)


def read_map():
    """The mapping file as a dict. Raises ValueError with a plain sentence when it can't be read."""
    path = map_path()
    try:
        document = loads_tolerant(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"config/{MAP_FILE_NAME} can't be read. Keep it valid JSON, or put the file back as it was.") from None
    if not isinstance(document, dict):
        raise ValueError(f"config/{MAP_FILE_NAME} should be one set of names in curly brackets.")
    return document


def names_in(mapping, what):
    """The names the mapping lists for `what`, best first. A single word is a list of one."""
    names = mapping.get(what) or []
    return [names] if isinstance(names, str) else [str(name) for name in names]


def question_list_in(document, mapping):
    """(the questions as a list or a dict, the key it was under) or (None, None)."""
    if isinstance(document, list):
        return document, "the file itself"
    for path in names_in(mapping, "question_list"):
        place = document
        for step in path.split("."):
            step_key, _spelled = find_key(place, [step])
            if step_key is None:
                place = None
                break
            place = place[step_key]
        if isinstance(place, (list, dict)):
            return place, path
    return None, None


def flatten_questions(container, mapping, section_name=None):
    """Every question as (item, section name or None), in file order. Sections that hold their own
    list of questions are opened. `container` is a list of items, or a dict keyed by the question's field."""
    flat = []
    if isinstance(container, dict):
        items = []
        for key, value in container.items():
            if isinstance(value, dict):
                items.append({**value, "_key": key})
            elif isinstance(value, str):
                items.append({"_key": key, "_text": value})
            else:
                items.append(value)
    else:
        items = container
    for item in items:
        if not isinstance(item, dict):
            flat.append((item, section_name))
            continue
        nested_key, _s = find_key(item, names_in(mapping, "question_list"))
        has_own_field = find_key(item, names_in(mapping, "field"))[0] is not None or "_key" in item
        if nested_key is not None and isinstance(item[nested_key], (list, dict)) and not has_own_field:
            name_key, _s = find_key(item, names_in(mapping, "section_name"))
            name = str(item[name_key]) if name_key is not None else section_name
            flat.extend(flatten_questions(item[nested_key], mapping, name))
        else:
            flat.append((item, section_name))
    return flat


def number_from_text(text):
    """(number, written as a percent) from '3', '40%', '1,200', or None."""
    found = re.search(r"-?\d[\d,]*\.?\d*|-?\.\d+", text)
    if not found:
        return None
    number = float(found.group(0).replace(",", ""))
    is_percent = "%" in text[found.end():found.end() + 2]
    return (number / 100 if is_percent else number), is_percent


# What is said before or after the number, checked in this order ("no more than" before "more than").
TEST_WORDS = (
    (drivers.AT_MOST, ("<=", "≤", "=<", "at most", "no more than", "up to", "maximum", "or fewer", "or less", "or below")),
    (drivers.AT_LEAST, (">=", "≥", "=>", "at least", "no less than", "minimum", "or more", "or above", "reaches", "reach")),
    (drivers.LESS_THAN, ("<", "less than", "fewer than", "under", "below")),
    (drivers.MORE_THAN, (">", "more than", "greater than", "over", "above", "exceeds", "exceed")),
)


def read_switch_number(raw, is_share):
    """What switches a number question's driver on: (test, number, notes). `raw` is '>= 3', 'more than 40%' or 3.
    Returns None when there is no number in it."""
    notes = []
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        test, number, is_percent = drivers.AT_LEAST, float(raw), False
    else:
        text = str(raw).strip().lower()
        found = number_from_text(text)
        if found is None:
            return None
        number, is_percent = found
        test = drivers.AT_LEAST
        for candidate, words in TEST_WORDS:
            if any(word in text for word in words):
                test = candidate
                break
    if is_share and not is_percent and number > expressions.WHOLE_SHARE:
        notes.append(f"{raw} was read as {raw}%.")
        number = number / 100
    return test, number, notes


def driver_for_field(field, rules):
    """The driver code a question's field feeds: by its questionnaire field, then the rule's field, then the code."""
    wanted = field.strip().lower()
    for code, rule in sorted(rules.items()):
        if wanted in [str(name).lower() for name in rule.get("questionnaire_fields") or []]:
            return code
    for code, rule in sorted(rules.items()):
        if str(rule["field"]).lower() == wanted:
            return code
    for code in sorted(rules):
        if code.lower() == wanted:
            return code
    return None


def kind_from_word(word, mapping):
    """'yes_no', 'number' or 'share' for the word the file used, or None when it isn't one of the kind_words."""
    wanted = plain_name(word)
    for kind, words in (mapping.get("kind_words") or {}).items():
        if wanted in [plain_name(candidate) for candidate in words]:
            return kind
    return None


class QuestionnaireReader:
    """Reads the owner's questionnaire one question at a time. What it finds goes in `made` (the questions that can be
    used), `problems` (a question left out, and why) and `notes` (worth a look, nothing refused). What it notices
    across all the questions is counted, and said once at the end (notes_from_counters)."""

    def __init__(self, mapping, rules, risks, entries, from_files):
        self.mapping, self.rules, self.risks, self.from_files = mapping, rules, risks, from_files
        self.entries_by_key = {entry["key"]: entry for entry in entries}
        self.entries = entries
        self.description = editable.describe(QUESTIONS)
        self.known_keys = {"key", "text"}
        for what in ("field", "text", "section", "order", "kind", "switches_on", "help", "section_name", "question_list"):
            self.known_keys.update(plain_name(name) for name in names_in(mapping, what))
        self.problems, self.notes, self.made = [], [], []
        self.label_of_key = {}                           # the question that holds each driver field so far
        self.unknown_keys, self.spelled_differently = {}, set()
        self.section_from_driver, self.no_switch, self.no_order = 0, 0, 0

    def read_one_question(self, number, item, container_section):
        """Read one question and add it to `made`, or say in `problems` why it was left out."""
        if not isinstance(item, dict):
            self.problems.append(f"Question {number} is not a set of keys, so it was left out.")
            return

        def pick(what):
            key, close = find_key(item, names_in(self.mapping, what))
            if close:
                self.spelled_differently.add(f"'{key}' was read as {what}")
            return item.get(key) if key is not None else None

        raw_field = pick("field")
        if raw_field in (None, "") and "_key" in item:
            raw_field = item["_key"]
        text = tidy_spaces(pick("text") or item.get("_text"))
        label = f"Question {number}" + (f" ({raw_field})" if raw_field else "")
        for key in item:
            if plain_name(key) not in self.known_keys and not str(key).startswith("_"):
                self.unknown_keys[key] = self.unknown_keys.get(key, 0) + 1
        if raw_field in (None, ""):
            self.problems.append(f"{label} names no driver field, so it was left out.")
            return
        code = driver_for_field(str(raw_field), self.rules)
        if code is None:
            close = difflib.get_close_matches(str(raw_field).lower(), [code.lower() for code in self.rules], n=1, cutoff=CLOSE_FIELD_NAME)
            hint = f" Did you mean {close[0].upper()}?" if close else ""
            self.problems.append(f"{label} feeds {raw_field}, and there is no driver with that field in the driver rules, so it was left out.{hint}")
            return
        if not text:
            self.problems.append(f"{label} has no wording, so it was left out.")
            return
        rule = self.rules[code]
        key = rule["field"]
        if key in self.label_of_key:
            self.notes.append(f"{key} has two questions ({self.label_of_key[key]} and {label}). The last one is used.")
            self.made = [question for question in self.made if question["key"] != key]
        self.label_of_key[key] = label

        section = pick("section") or container_section
        if section in (None, ""):
            section = question_list.section_for_driver(code, self.risks)
            self.section_from_driver += 1
        order_raw = pick("order")
        order_number = drivers.as_number(order_raw) if order_raw not in (None, "") else None
        if order_number is None:
            order_number = number * editable.ORDER_STEP
            self.no_order += 1

        kind_word = pick("kind")
        kind = kind_from_word(kind_word, self.mapping) if kind_word not in (None, "") else None
        if kind_word not in (None, "") and kind is None:
            self.notes.append(f"{label}: the kind of answer '{kind_word}' is not one of the kind_words, so the driver's own rule decides.")
        if kind is None:
            kind = "yes_no" if rule["test"] in (drivers.IS_YES, drivers.IS_NO) else "number"
        is_share = key.lower().endswith(question_list.SHARE_FIELD_ENDING) or kind == "share"
        switches_raw = pick("switches_on")

        values = {"driver": code, "section": str(section), "order": order_number, "text": text,
                  "kind": "yes_no" if kind == "yes_no" else "number", "switches_on": None, "test": None, "number": None}
        if values["kind"] == "yes_no":
            answer = drivers.as_yes_no(switches_raw)
            if answer is None:
                self.no_switch += 1
                answer = True
            values["switches_on"] = "yes" if answer else "no"
        else:
            read = read_switch_number(switches_raw, is_share)
            if read is None:
                self.no_switch += 1
                values["test"], values["number"] = rule["test"], rule["value"]
                if rule["test"] in (drivers.IS_YES, drivers.IS_NO) or rule["value"] is None:
                    self.problems.append(f"{label} is a number, but its driver {code} is switched on by a yes or no and the file gives no number, so it was left out.")
                    return
            else:
                values["test"], values["number"], more = read
                self.notes.extend(f"{label}: {sentence}" for sentence in more)

        help_text = tidy_spaces(pick("help"))
        if help_text:
            values["help_text"] = help_text                  # shown under the question on the form
        existing = self.entries_by_key.get(key)
        action = editable.EDIT if existing else editable.ADD
        try:
            cleaned = editable.clean_values(QUESTIONS, key, values, existing["values"] if existing else None, action, self.from_files)
            self.description["check"](action, key, cleaned, self.entries, self.from_files)
        except ValueError as trouble:
            self.problems.append(f"{label}: {trouble}")
            self.label_of_key.pop(key, None)
            return
        if existing is None:
            status = NEW
        elif existing["retired"]:
            status = RESTORED
        elif existing["values"] == cleaned:
            status = SAME
        else:
            status = CHANGED
        self.made.append({"key": key, "values": cleaned, "help": help_text, "label": label, "status": status, "existing": existing})

    def notes_from_counters(self):
        """What was noticed across all the questions, as notes."""
        for key, count in sorted(self.unknown_keys.items()):
            self.notes.append(f"The key '{key}' is in {count_of(count, 'question', 'questions')} and is not in the map, so it was ignored.")
        for sentence in sorted(self.spelled_differently):
            self.notes.append(f"{sentence} (a close spelling).")
        if self.section_from_driver:
            self.notes.append(f"{count_of(self.section_from_driver, 'question has', 'questions have')} no section, so the driver's domain is used.")
        if self.no_order:
            self.notes.append(f"{count_of(self.no_order, 'question has', 'questions have')} no order, so file order is used.")
        if self.no_switch:
            self.notes.append(f"{count_of(self.no_switch, 'question gives', 'questions give')} no clear answer that switches the driver on, "
                              f"so yes is used for a yes or no question, and the driver's own rule for a number.")


def read_questionnaire(document, mapping, rules, risks, entries, from_files):
    """Read the owner's questionnaire. Returns (questions, problems, notes): each question is
    {"key", "values", "help", "label", "status"}; `entries` are the questions list as it is now (editable.entries_now)."""
    container, found_under = question_list_in(document, mapping)
    if container is None:
        looked = ", ".join(names_in(mapping, "question_list"))
        problem = (f"The question list was not found. The map looks for: {looked}. Add the name your file uses at the start "
                   f"of question_list in config/{MAP_FILE_NAME}.")
        return [], [problem], []

    reader = QuestionnaireReader(mapping, rules, risks, entries, from_files)
    if isinstance(document, dict):
        for top_key in document:
            if plain_name(top_key) != plain_name(str(found_under).split(".")[0]) and not str(top_key).startswith("_"):
                reader.notes.append(f"The top-level key '{top_key}' is not in the map, so it was ignored.")
    for number, (item, container_section) in enumerate(flatten_questions(container, mapping), 1):
        reader.read_one_question(number, item, container_section)
    reader.notes_from_counters()
    return reader.made, reader.problems, reader.notes


def check_question_upload(uploads):
    """Read and check an uploaded questionnaire. Returns the result the page shows, and what a load would keep."""
    documents, problems, notes = documents_from_uploads(uploads)
    try:
        mapping = read_map()
    except ValueError as trouble:
        problems.append(str(trouble))
        return result_document(QUESTIONS, documents, [], problems, notes, "No questions were read."), {"changed": 0, "documents": documents}

    current = registers.load_registers()
    from_files = current["from_files"]
    entries = editable.entries_now(QUESTIONS, from_files)
    made = []
    for name, text in documents:
        for document in yaml_documents(name, text, problems):
            read, more_problems, more_notes = read_questionnaire(document, mapping, from_files["driver_rules"], from_files["risks"], entries, from_files)
            made.extend(read)
            problems.extend(f"{name}: {sentence}" if len(documents) > 1 else sentence for sentence in more_problems)
            notes.extend(more_notes)

    items = [{"id": question["key"], "name": question["values"]["text"], "status": question["status"],
              "section": question["values"]["section"], "order": question["values"]["order"],
              "switches": switch_words(question["values"]), "help": question["help"], "driver": question["values"]["driver"]}
             for question in made]
    counts = status_counts(items)
    not_in_file = len([entry for entry in entries if not entry["retired"] and entry["key"] not in {question["key"] for question in made}])
    if made and not_in_file:
        notes.append(f"{count_of(not_in_file, 'question already on the site is', 'questions already on the site are')} not in this file "
                     f"and stays as it is.")
    summary = f"{count_of(len(items), 'question', 'questions')} read: {counts_words(counts)}." if items else "No questions were read."
    proposed = proposed_entries(entries, made)
    changed = [question for question in made if question["status"] != SAME]
    result = result_document(QUESTIONS, documents, items, problems, notes, summary)
    return result, {"made": made, "changed": len(changed), "documents": documents, "proposed": proposed,
                    "entries": entries, "from_files": from_files}


def switch_words(values):
    if values["kind"] == "yes_no":
        return "Yes" if values["switches_on"] == "yes" else "No"
    return f"{values['test'].capitalize()} {values['number']:g}"


def proposed_entries(entries, made):
    """The questions list as it would be after the load: every entry now, with the file's questions put on."""
    by_key = {question["key"]: question for question in made}
    proposed = []
    for entry in entries:
        question = by_key.get(entry["key"])
        if question is None:
            proposed.append(entry)
        else:
            proposed.append({"key": entry["key"], "values": question["values"], "retired": False})
    known = {entry["key"] for entry in entries}
    proposed.extend({"key": question["key"], "values": question["values"], "retired": False}
                    for question in made if question["key"] not in known)
    return proposed


# ---------------------------------------------------------------------------------------------------
# See what would move: every team's newest ratings, rated again with what the load would put in
# ---------------------------------------------------------------------------------------------------

def moves_for_questions(applying):
    """Uses editable's own re-rate preview."""
    if not applying["made"]:
        return []
    return editable.rating_moves(applying["from_files"], QUESTIONS, applying["proposed"])


def moves_for_registers(kind, applying):
    """For risks and drivers: the same re-rating as the editing lists (editable.rating_moves_between), between the
    registers now and the registers with the load on."""
    current = registers.load_registers()
    from_files = dict(current["from_files"])
    proposed_files = dict(from_files)
    if kind == RISKS:
        proposed_files["risks"] = applying["registers"]
    else:
        proposed_files["driver_rules"] = applying["registers"]
    proposed_files["questions"] = question_list.build(proposed_files["driver_rules"], proposed_files["risks"])
    proposed = editable.with_saved_changes({**proposed_files, "notes": []})

    return editable.rating_moves_between(current, proposed)


def moves_summary(moves):
    teams = len({entry["group"] for entry in moves})
    if not moves:
        return "No team's newest ratings would change."
    return f"{count_of(len(moves), 'rating would', 'ratings would')} change, in {count_of(teams, 'team', 'teams')}."


# ---------------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------------

CHECKERS = {RISKS: check_risk_upload, DRIVERS: check_driver_upload, QUESTIONS: check_question_upload}


def check(kind, uploads):
    """Read and check. Returns (what the page shows, what a load would keep)."""
    if kind not in CHECKERS:
        raise ValueError("Choose risks, drivers or questions.")
    if not uploads:
        raise ValueError("Choose a file first.")
    result, applying = CHECKERS[kind](uploads)
    result["can_load"] = applying.get("changed", 0) > 0
    if not result["can_load"]:
        result["why_not"] = ("Nothing here is different from what the site holds, so there is nothing to load."
                             if result["items_total"] and not result["problems"] else
                             "Nothing could be used from these files. Read the problems, fix the file and choose it again.")
    return result, applying


def preview(kind, uploads):
    """The check, and which teams' newest ratings would change. Saves nothing."""
    result, applying = check(kind, uploads)
    moves = moves_for_questions(applying) if kind == QUESTIONS else moves_for_registers(kind, applying) if applying.get("changed") else []
    result["moves"] = moves
    result["moves_summary"] = moves_summary(moves)
    return result


def load(kind, uploads, by):
    """Check again and keep what can be used. Returns the check's result with what was kept."""
    result, applying = check(kind, uploads)
    if not result["can_load"]:
        raise ValueError(result["why_not"])
    names = ", ".join(result["files"])
    read = {"files": result["files"], "summary": result["summary"], "items": [item["id"] for item in result["items"]],
            "counts": result["counts"], "problems": result["problems"], "notes": result["notes"]}
    if kind == QUESTIONS:
        kept_registers = [{"key": question["key"], "values": question["values"], "help": question["help"], "status": question["status"]}
                          for question in applying["made"]]
        read["help_texts"] = {question["key"]: question["help"] for question in applying["made"] if question["help"]}
        keep_questions(applying, by, names)
    else:
        kept_registers = applying["registers"]
    kept = storage.add_risk_seed_upload(kind, by, names, result["file_hash"], read, kept_registers)
    result["kept"] = kept
    return result


def keep_questions(applying, by, names):
    """Put the questions in the "questions" editing list, with who and why, so they have history there.
    The first load from the file is kept first when the list has never been saved, as editable.save does."""
    reason = f"Loaded from the uploaded questionnaire {names}."
    rows = []
    if not storage.list_changes(QUESTIONS):
        whole = [{"key": entry["key"], "values": entry["values"]} for entry in applying["entries"]]
        rows.append({"key": editable.WHOLE_LIST, "action": editable.LOAD, "before": None, "after": whole, "reason": editable.FIRST_LOAD_REASON})
    for question in applying["made"]:
        if question["status"] == SAME:
            continue
        was = question["existing"]
        before = {"values": was["values"], "retired": was["retired"]} if was else None
        action = editable.EDIT if was else editable.ADD
        rows.append({"key": question["key"], "action": action, "reason": reason, "before": before,
                     "after": {"values": question["values"], "retired": False}})
        if was and was["retired"]:
            rows.append({"key": question["key"], "action": editable.RESTORE, "reason": reason,
                         "before": {"values": question["values"], "retired": True},
                         "after": {"values": question["values"], "retired": False}})
    storage.add_list_changes(QUESTIONS, rows, by)
