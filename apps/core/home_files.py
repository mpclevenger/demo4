"""The front page: two doors and a list of shortcuts. All the wording lives in content/home/.

- `index.md` holds the heading (the `title:` line) and the short line under it.
- `doors.md` holds the words for the two doors: a title, a line and a button or search hint for each.
- `shortcuts.md` holds the list of shortcuts, one per line, written as `Title | One line | /link/`
  (blank lines and lines starting with `#` are ignored).

A shortcut's link is a page in TRAC (`/guides/`) or an `https://` address. Nothing here is stored in the
database, so a change to these files shows once the site restarts with them.
"""

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.core.links import is_allowed_link
from apps.wiki.richtext import clean_html
from apps.wiki.starter_guides import markdown_to_html

FOLDER = Path(settings.BASE_DIR) / "content" / "home"
PAGE_FIELDS = {"title"}
DOOR_FIELDS = {"build_title", "build_line", "build_button", "run_title", "run_line", "run_button", "run_placeholder"}


class HomeFileError(ValueError):
    pass


@dataclass
class Page:
    title: str
    html: str


@dataclass
class Doors:
    build_title: str
    build_line: str
    build_button: str
    run_title: str
    run_line: str
    run_button: str
    run_placeholder: str


@dataclass
class Shortcut:
    title: str
    line: str
    url: str


@dataclass
class Shortcuts:
    title: str
    items: list


def _read(path, allowed, required):
    """Header fields and body text of one file, or HomeFileError saying what is wrong."""
    lines = path.read_text(encoding="utf-8").lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise HomeFileError(f"{path.name}: the file must start with a line of three dashes (---).")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise HomeFileError(f"{path.name}: the header has no closing line of three dashes (---).") from None
    fields = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, colon, value = line.partition(":")
        key = key.strip().lower()
        if not colon or key not in allowed:
            raise HomeFileError(f"{path.name}: '{line.strip()}' isn't a known header line. Use: {', '.join(sorted(allowed))}.")
        fields[key] = value.strip()
    for key in required:
        if not fields.get(key):
            raise HomeFileError(f"{path.name}: the header needs a '{key}:' line.")
    return fields, "\n".join(lines[end + 1:])


def _url(link, name):
    """The address for a link: a TRAC page or an https address, or HomeFileError."""
    if is_allowed_link(link):
        return link
    raise HomeFileError(f"{name}: the link '{link}' must be a TRAC page (like /guides/) or an https:// address.")


def landing(folder=None):
    fields, body = _read(Path(folder or FOLDER) / "index.md", PAGE_FIELDS, ("title",))
    return Page(title=fields["title"], html=clean_html(markdown_to_html(body)))


def doors(folder=None):
    fields, _ = _read(Path(folder or FOLDER) / "doors.md", DOOR_FIELDS, sorted(DOOR_FIELDS))
    return Doors(**fields)


def shortcuts(folder=None):
    path = Path(folder or FOLDER) / "shortcuts.md"
    fields, body = _read(path, PAGE_FIELDS, ("title",))
    items = []
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3 or not all(parts):
            raise HomeFileError(f"{path.name}: the line '{line.strip()}' should look like 'Title | One line | /link/'.")
        items.append(Shortcut(parts[0], parts[1], _url(parts[2], path.name)))
    if not items:
        raise HomeFileError(f"{path.name}: add at least one shortcut, written as 'Title | One line | /link/'.")
    return Shortcuts(title=fields["title"], items=items)


def problems(folder=None):
    """Plain-word problems with the home page files, for check_content."""
    try:
        landing(folder)
        doors(folder)
        shortcuts(folder)
    except (HomeFileError, OSError) as error:
        return [str(error)]
    return []
