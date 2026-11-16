"""The rules for the two nested parts of a control: its steps and its "choosing people" notes.

The model, the content files and the edit form all use these checks, so a rule is written once.
Each check returns plain-word problems and never raises, because the data may have come from a
hand-edited file.

A step is {"do": text, "how": text, "weigh": [text], "policy": text,
"evidence": {"keep": text, "shows": [text]}, "commands": [{"platform": text, "note": text, "code": text,
"audience": text, "confirmed_by": text, "confirmed_on": date}], "checks": [{"platform": text, "audience": text,
"where": text, "good": [text], "keep": text, "shows": [text]}]}.
Only "do" is required. "evidence" needs "keep" when it is there. A command needs "platform" and "code".
A command nobody has confirmed is shown as Proposed; "confirmed_by" and "confirmed_on" together take the mark off.
A check is the Library's "how to check it" for one platform and one audience: where to look, what good looks
like and what to keep. It needs "platform" and "audience" and at least one of the three parts.
"""

import datetime

AUDIENCE_ADMINS = "Platform admins"
AUDIENCE_USERS = "Platform users"
AUDIENCES = (AUDIENCE_ADMINS, AUDIENCE_USERS)
COMMAND_DEFAULT_AUDIENCE = AUDIENCE_USERS  # a command with no "audience" counts for the people who use the platform
PROPOSED_NOTE = "Proposed: pending confirmation from the platform owner."

STEP_KEYS = ("do", "how", "weigh", "policy", "evidence", "commands", "checks")
EVIDENCE_KEYS = ("keep", "shows")
COMMAND_KEYS = ("platform", "note", "code", "audience", "confirmed_by", "confirmed_on")
CHECK_KEYS = ("platform", "audience", "where", "good", "keep", "shows")
CHECK_PARTS = ("where", "good", "keep")
PEOPLE_KEYS = ("performer", "reviewer", "small_team")
PEOPLE_LISTS = ("performer", "reviewer")


def is_text(value):
    """True for a string with something in it."""
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value):
    return isinstance(value, list) and bool(value) and all(is_text(item) for item in value)


def _list_of(keys):
    return ", ".join(keys[:-1]) + f" and {keys[-1]}"


def _unknown_keys(entry, allowed):
    return [f"'{key}' isn't a known field. Use {_list_of(allowed)}." for key in entry if key not in allowed]


def _evidence_problems(evidence):
    if not isinstance(evidence, dict):
        return ["'evidence' needs a 'keep' line and, if you like, a 'shows' list. Plain text isn't used any more."]
    problems = _unknown_keys(evidence, EVIDENCE_KEYS)
    if not is_text(evidence.get("keep")):
        problems.append("'evidence' needs a 'keep' line saying what to save.")
    if "shows" in evidence and not _is_text_list(evidence["shows"]):
        problems.append("'shows' under 'evidence' needs a list of lines, none left empty.")
    return problems


def _command_problems(commands):
    if not isinstance(commands, list) or not commands:
        return ["'commands' needs a list with at least one command."]
    problems = []
    for number, command in enumerate(commands, start=1):
        if not isinstance(command, dict):
            problems.append(f"command {number} needs a 'platform' and some 'code'.")
            continue
        problems += [f"command {number}: {text}" for text in _unknown_keys(command, COMMAND_KEYS)]
        for key in ("platform", "code"):
            if not is_text(command.get(key)):
                problems.append(f"command {number} needs a '{key}'.")
        if "note" in command and not is_text(command["note"]):
            problems.append(f"command {number}: 'note' needs text, or leave it out.")
        problems += [f"command {number}: {text}" for text in _command_extra_problems(command)]
    return problems


def _command_extra_problems(command):
    """Problems with a command's audience and its confirmation, which are all optional."""
    problems = []
    if "audience" in command and command["audience"] not in AUDIENCES:
        problems.append(f"'audience' is '{command['audience']}'. Use {AUDIENCE_ADMINS} or {AUDIENCE_USERS}.")
    if "confirmed_by" in command and not is_text(command["confirmed_by"]):
        problems.append("'confirmed_by' needs the name of the person who confirmed it, or leave it out.")
    if "confirmed_on" in command and not _is_date(command["confirmed_on"]):
        problems.append("'confirmed_on' needs a date written YYYY-MM-DD, or leave it out.")
    if ("confirmed_by" in command) != ("confirmed_on" in command):
        problems.append("'confirmed_by' and 'confirmed_on' go together: give both, or neither (it stays Proposed).")
    return problems


def _is_date(value):
    """True for a date, or for text written YYYY-MM-DD that is a real day (a YAML file turns a bare date into a date)."""
    if isinstance(value, datetime.date):
        return True
    try:
        datetime.date.fromisoformat(str(value))
    except ValueError:
        return False
    return isinstance(value, str)


def _check_problems(checks):
    if not isinstance(checks, list) or not checks:
        return ["'checks' needs a list with at least one check."]
    problems = []
    for number, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            problems.append(f"check {number} needs a 'platform' and an 'audience'.")
            continue
        problems += [f"check {number}: {text}" for text in _unknown_keys(check, CHECK_KEYS)]
        if not is_text(check.get("platform")):
            problems.append(f"check {number} needs a 'platform'.")
        if check.get("audience") not in AUDIENCES:
            problems.append(f"check {number} needs an 'audience': {AUDIENCE_ADMINS} or {AUDIENCE_USERS}.")
        if not any(part in check for part in CHECK_PARTS):
            problems.append(f"check {number} needs at least one of 'where', 'good' or 'keep'.")
        for key in ("where", "keep"):
            if key in check and not is_text(check[key]):
                problems.append(f"check {number}: '{key}' needs text, or leave it out.")
        for key in ("good", "shows"):
            if key in check and not _is_text_list(check[key]):
                problems.append(f"check {number}: '{key}' needs a list of lines, none left empty.")
        if "shows" in check and "keep" not in check:
            problems.append(f"check {number}: 'shows' goes with a 'keep' line.")
    return problems


def _one_step_problems(step):
    if not isinstance(step, dict):
        return ["each step needs a 'do' line."]
    problems = _unknown_keys(step, STEP_KEYS)
    if not is_text(step.get("do")):
        problems.append("each step needs a 'do' line.")
    for key in ("how", "policy"):
        if key in step and not is_text(step[key]):
            problems.append(f"'{key}' needs text, or leave it out.")
    if "weigh" in step and not _is_text_list(step["weigh"]):
        problems.append("'weigh' needs a list of lines, none left empty.")
    if "evidence" in step:
        problems += _evidence_problems(step["evidence"])
    if "commands" in step:
        problems += _command_problems(step["commands"])
    if "checks" in step:
        problems += _check_problems(step["checks"])
    return problems


def step_problems(steps):
    """[(step number or None, message)] for everything wrong with a list of steps. Empty when it is fine."""
    if not isinstance(steps, list):
        return [(None, "expected a list of steps.")]
    return [(number, text) for number, step in enumerate(steps, start=1) for text in _one_step_problems(step)]


def people_problems(people):
    """Plain-word problems with a "choosing people" mapping. Empty when it is fine (an empty mapping means none)."""
    if not isinstance(people, dict):
        return ["expected 'performer', 'reviewer' and 'small_team'."]
    problems = _unknown_keys(people, PEOPLE_KEYS)
    for key in PEOPLE_LISTS:
        if key in people and not _is_text_list(people[key]):
            problems.append(f"'{key}' needs a list of lines, none left empty.")
    if "small_team" in people and not is_text(people["small_team"]):
        problems.append("'small_team' needs a line of text, or leave it out.")
    return problems


def platform_names(steps):
    """[(step number, platform name)] for every command and check in valid steps."""
    return [
        (number, entry["platform"])
        for number, step in enumerate(steps, start=1)
        for entry in (*step.get("commands", []), *step.get("checks", []))
    ]


def checks_of(steps):
    """Every check in a control's steps, in step order. Each is the check as written."""
    return [check for step in steps or [] if isinstance(step, dict) for check in step.get("checks", [])]


def commands_of(steps, platform, audience):
    """The commands in a control's steps for one platform and audience, in step order.

    A command with no audience counts for COMMAND_DEFAULT_AUDIENCE.
    """
    return [
        command
        for step in steps or [] if isinstance(step, dict)
        for command in step.get("commands", [])
        if command.get("platform") == platform and command.get("audience", COMMAND_DEFAULT_AUDIENCE) == audience
    ]


def is_proposed(command):
    """True until the platform owner has confirmed the command (a name and a date are written on it)."""
    return not (command.get("confirmed_by") and command.get("confirmed_on"))
