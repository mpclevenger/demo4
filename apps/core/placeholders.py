"""Values that are filled in later: a policy link, the Tech Risk email address, the walkthrough dates.

The values live in one plain file, content/settings.yaml. Content refers to a value in one of two ways:

- a link written `[Access Control Policy](#todo-access-control-policy)` (the key has dashes in the text, underscores in the file)
- a word written `{{tech_risk_email}}`

When the value is filled in, the page shows the real link or text. While it is empty, the page shows the words plainly with a
small "to be added" note, so there is never a broken link. The file is read again whenever it changes, so an edit shows without a restart.
Nothing here is stored in the database.
"""

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

import yaml
from django.conf import settings
from django.utils.safestring import mark_safe

from .links import is_allowed_link

FILE = Path(settings.BASE_DIR) / "content" / "settings.yaml"
KINDS = ("link", "email", "text")
FILE_LINES = {"label", "kind", "value"}
NOTE_WORDS = "to be added"
_KEY = re.compile(r"[a-z][a-z0-9_]*")
_UNSAFE_IN_LINK = re.compile(r'[\s"<>]')
_EMAIL_VALUE = re.compile(r"[^\s@\"<>]+@[^\s@\"<>]+\.[^\s@\"<>]+")

# In content text: [words](#todo-some-key) and {{some_key}}. The same two patterns find them in guide HTML.
TODO_LINK_IN_TEXT = re.compile(r"\[([^\]]+)\]\(#todo-([a-z][a-z0-9-]*)\)")
TODO_LINK_IN_HTML = re.compile(r'<a\s+href="#todo-([a-z][a-z0-9-]*)"[^>]*>(.*?)</a>', re.S)
TOKEN = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
_MERMAID_TEXT = re.compile(r"```mermaid.*?```", re.S)
_MERMAID_HTML = re.compile(r'<pre class="mermaid">.*?</pre>', re.S)


@dataclass
class Value:
    key: str
    label: str
    kind: str
    value: str

    @property
    def is_set(self):
        return bool(self.value)


@dataclass
class Values:
    items: dict
    problems: list


def key_of(link_key):
    """The file key for the key written in a link: access-control-policy becomes access_control_policy."""
    return link_key.replace("-", "_")


def _read_value(key, raw, name, problems):
    """One Value from one entry of the file, or None with the problem recorded."""
    if not _KEY.fullmatch(key):
        problems.append(f"{name}: '{key}' is not a good key. Use lowercase words joined by underscores, like tech_risk_email.")
        return None
    if not isinstance(raw, dict):
        problems.append(f"{name}: '{key}' needs three lines under it: label, kind and value.")
        return None
    for extra in raw.keys() - FILE_LINES:
        problems.append(f"{name}: '{key}' has a line '{extra}' that isn't used. The lines are label, kind and value.")
    label = str(raw.get("label") or "").strip()
    kind = str(raw.get("kind") or "").strip()
    value = "" if raw.get("value") is None else str(raw["value"]).strip()
    if not label:
        problems.append(f"{name}: '{key}' needs a label (a plain name for it).")
    if kind not in KINDS:
        problems.append(f"{name}: '{key}' needs a kind of {', '.join(KINDS)}.")
        return None
    if value and kind == "link" and not (is_allowed_link(value) and not _UNSAFE_IN_LINK.search(value)):
        problems.append(f"{name}: '{key}' should be a web address starting with https:// (or a TRAC page starting with /).")
        return None
    if value and kind == "email" and not _EMAIL_VALUE.fullmatch(value):
        problems.append(f"{name}: '{key}' should be an email address like name@company.com.")
        return None
    return Value(key=key, label=label or key, kind=kind, value=value)


def read_values(path=None):
    """Every value in the file, with a plain-words message for anything wrong. A missing file means no values."""
    path = Path(path or FILE)
    result = Values(items={}, problems=[])
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return result
    except (yaml.YAMLError, OSError):
        result.problems.append(f"{path.name}: the file can't be read. Check the indentation and colons.")
        return result
    if data is None:
        return result
    if not isinstance(data, dict):
        result.problems.append(f"{path.name}: expected a list of keys, each with a label, kind and value.")
        return result
    for key, raw in data.items():
        item = _read_value(str(key), raw, path.name, result.problems)
        if item:
            result.items[item.key] = item
    return result


_cache = {}


def values():
    """The values for rendering: {key: Value}. Read again only when the file changes."""
    try:
        stamp = (str(FILE), FILE.stat().st_mtime_ns)
    except OSError:
        stamp = (str(FILE), None)
    if stamp not in _cache:
        _cache.clear()
        _cache[stamp] = read_values(FILE).items
    return _cache[stamp]


def _href(item):
    return f"mailto:{item.value}" if item.kind == "email" else item.value


def _waiting(words_html):
    """The words as they are, with the small note that the value is not there yet."""
    return f'<span class="todo-link">{words_html}</span> <small class="todo-note text-body-secondary">({NOTE_WORDS})</small>'


def link_html(link_key, words_html):
    """Safe HTML for a #todo- link: a real link when its value is set, otherwise the words plainly with a note."""
    item = values().get(key_of(link_key))
    if not item or not item.is_set or item.kind == "text":
        return _waiting(words_html)
    rel = ' rel="noopener noreferrer"' if item.value.startswith("https://") else ""
    return f'<a href="{escape(_href(item))}"{rel}>{words_html}</a>'


def token_html(key):
    """Safe HTML for a {{key}} word: its value (an email address as a mailto link), or its label with the note. None if the key is unknown."""
    item = values().get(key)
    if not item:
        return None
    if not item.is_set:
        return _waiting(escape(item.label))
    if item.kind == "text":
        return escape(item.value)
    return link_html(key, escape(item.label if item.kind == "link" else item.value))


def fill_tokens(html):
    """HTML with each known {{key}} replaced. Unknown keys are left as they are (the check reports them)."""
    return TOKEN.sub(lambda match: token_html(match.group(1)) or match.group(0), html)


def resolve_html(html):
    """Guide HTML with its #todo- links and {{key}} words filled in. Diagram blocks are left alone."""
    if not html or ("#todo-" not in html and "{{" not in html):
        return html
    held = []

    def hold(match):
        held.append(match.group(0))
        return f"\x00DIAGRAM{len(held) - 1}\x00"

    text = _MERMAID_HTML.sub(hold, html)
    text = TODO_LINK_IN_HTML.sub(lambda match: link_html(match.group(1), match.group(2)), text)
    text = fill_tokens(text)
    for number, block in enumerate(held):
        text = text.replace(f"\x00DIAGRAM{number}\x00", block)
    return mark_safe(text)


def keys_used(text):
    """{file key: how many times} for every placeholder link and {{key}} word in a content file's text."""
    text = _MERMAID_TEXT.sub("", text)
    counts = {}
    for _words, link_key in TODO_LINK_IN_TEXT.findall(text):
        counts[key_of(link_key)] = counts.get(key_of(link_key), 0) + 1
    for key in TOKEN.findall(text):
        counts[key] = counts.get(key, 0) + 1
    return counts


def links_used(text):
    """The file keys written as #todo- links (not {{key}} words) in a content file's text."""
    return {key_of(link_key) for _words, link_key in TODO_LINK_IN_TEXT.findall(text)}
