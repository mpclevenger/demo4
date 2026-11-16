"""The two audiences of Library guidance: Platform admins and Platform users.

This follows the firm's model: a platform team runs the platform with its own controls, and each team that
uses the platform owns the controls over its own use. Every line of Library guidance is for one of them.
A guidance line says which with a tag at the start: `- [Platform admins] The line.` or `- [Platform users] The line.`
A line with no tag is for both.
"""

import re

from apps.rcm.shape import AUDIENCE_ADMINS, AUDIENCE_USERS, AUDIENCES

KEY_ADMINS = "admins"
KEY_USERS = "users"
KEYS = {AUDIENCE_ADMINS: KEY_ADMINS, AUDIENCE_USERS: KEY_USERS}

# One line each, shown on the Library under the audience pills, so a reader knows which one they are.
WHO_YOU_ARE = {
    AUDIENCE_ADMINS: "you run or administer the platform.",
    AUDIENCE_USERS: "your team uses the platform.",
}

# A tag is square brackets at the start of a line's text that are not the start of a [text](link).
_TAG = re.compile(r"^\[([^\]]+)\](?!\()\s*")


def key_of(audience):
    """The short key used in addresses and on the page: 'admins' or 'users'. Empty for anything else."""
    return KEYS.get(audience, "")


def chosen_key(request):
    """The audience the visitor filtered to (from `?audience=`), or empty for both."""
    value = request.GET.get("audience", "")
    return value if value in KEYS.values() else ""


def split_tag(text):
    """(audience name or None, the text without its tag). An unknown tag is left in the text."""
    match = _TAG.match(text)
    if match and match.group(1) in AUDIENCES:
        return match.group(1), text[match.end():]
    return None, text


def tag_problems(text):
    """Plain-word problems with the tags in a guidance text: a tag that isn't one of the two audiences."""
    problems = []
    for raw in str(text).splitlines():
        line = raw.strip()
        line = line[2:].strip() if line.startswith("- ") else line
        match = _TAG.match(line)
        if match and match.group(1) not in AUDIENCES:
            problems.append(
                f"'[{match.group(1)}]' isn't an audience. Start the line with [{AUDIENCE_ADMINS}] or "
                f"[{AUDIENCE_USERS}], or with no tag for both."
            )
    return problems
