"""The diagrams' list file: content/diagrams/diagrams.yaml, and the draw.io pictures it names.

The file has one list, `diagrams`. Each entry names a picture (a `.drawio.svg` file in the same folder), gives it a
title and a short intro, says whether it is a `common` diagram (how a kind of platform usually works) or a
`footprint` diagram (the firm's own setup), and names the platforms it is about. Nothing is stored in the database:
the owner edits a diagram in draw.io, saves it over the old file, and the site shows it on the next page load.

`read_diagrams` never stops at the first mistake: it keeps every entry it can read and collects a plain-word message
for each one it can't, so the pages keep working and `check_diagrams` can list everything to fix.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from apps.core.yaml_files import load_yaml, read_day

FOLDER = Path(settings.BASE_DIR) / "content" / "diagrams"
FILE = FOLDER / "diagrams.yaml"
PICTURE_SUFFIX = ".drawio.svg"
KINDS = {"common": "Common", "footprint": "Our footprint"}
ENTRY_LINES = ("file", "title", "intro", "kind", "platforms", "as_of")
MAX_PICTURE_BYTES = 5 * 1024 * 1024
_FILE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*" + re.escape(PICTURE_SUFFIX))


@dataclass(frozen=True)
class Diagram:
    file: str
    title: str
    intro: str
    kind: str
    platforms: tuple = ()
    as_of: date | None = None

    @property
    def name(self):
        """The short name used in the address: the file name without .drawio.svg."""
        return self.file[: -len(PICTURE_SUFFIX)]

    @property
    def kind_label(self):
        return KINDS[self.kind]

    @property
    def path(self):
        return FOLDER / self.file


@dataclass
class Diagrams:
    items: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    def named(self, name):
        """The diagram with this short name, or None."""
        return next((d for d in self.items if d.name == name), None)

    def of_kind(self, kind):
        return [d for d in self.items if d.kind == kind]

    def for_platform(self, platform_name):
        """The diagrams that name this platform, in the file's order."""
        return [d for d in self.items if platform_name in d.platforms]


def _text(raw, line):
    return str(raw.get(line) or "").strip()


def _read_entry(raw, folder):
    """(the Diagram, []) for an entry that is all right, or (None, a plain-word reason for each mistake)."""
    found = []
    say = found.append
    if not isinstance(raw, dict):
        return None, ["needs a file, a title, an intro and a kind."]
    file_name, title, intro, kind = (_text(raw, line) for line in ("file", "title", "intro", "kind"))
    for line in raw.keys() - set(ENTRY_LINES):
        say(f"'{line}' isn't a known line. Use: {', '.join(ENTRY_LINES)}.")
    if not file_name:
        say("needs a 'file' (for example aws-login-access-flow.drawio.svg).")
    elif not _FILE_NAME.fullmatch(file_name):
        say(f"the file name '{file_name}' should use lowercase letters, digits and dashes, and end in {PICTURE_SUFFIX}.")
    elif not (folder / file_name).is_file():
        say(f"the file '{file_name}' isn't in content/diagrams. Save the picture there first.")
    elif (folder / file_name).stat().st_size > MAX_PICTURE_BYTES:
        say(f"the file '{file_name}' is bigger than {MAX_PICTURE_BYTES // (1024 * 1024)} MB.")
    if not title:
        say("needs a 'title'.")
    if not intro:
        say("needs an 'intro' (one or two plain sentences).")
    if kind not in KINDS:
        say(f"'kind' should be {' or '.join(KINDS)}, not '{kind}'." if kind else f"needs a 'kind': {' or '.join(KINDS)}.")
    platforms = raw.get("platforms") or []
    if not isinstance(platforms, list) or not all(isinstance(p, str) and p.strip() for p in platforms):
        say("'platforms' should be a list of platform names, like [AWS, Entra ID].")
        platforms = []
    as_of = None
    if raw.get("as_of") not in (None, ""):
        as_of = read_day(raw["as_of"])
        if as_of is None:
            say("'as_of' should be a real day written YYYY-MM-DD, like 2026-11-13.")
    if found:
        return None, found
    return Diagram(file_name, title, intro, kind, tuple(p.strip() for p in platforms), as_of), []


def read_diagrams(path=None):
    """Every diagram in the list file that can be read, and a plain-word problem for each that can't."""
    path = Path(path or FILE)
    result = Diagrams()
    if not path.exists():  # no file means there are no diagrams yet, which is not a problem
        return result
    data, problem = load_yaml(path, keep_as_text=("timestamp",))
    if problem:
        result.problems.append(problem)
        return result
    if data is None:
        return result
    entries = data.get("diagrams") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        result.problems.append(f"{path.name}: expected one list called 'diagrams'.")
        return result
    seen = set()
    for number, raw in enumerate(entries, start=1):
        diagram, found = _read_entry(raw, path.parent)
        label = f"{path.name}, diagram {number}" + (f" ({raw['title']})" if isinstance(raw, dict) and raw.get("title") else "")
        if diagram and diagram.file in seen:
            found = [f"the file '{diagram.file}' is listed twice."]
        if found:
            result.problems.extend(f"{label}: {message}" for message in found)
            continue
        seen.add(diagram.file)
        result.items.append(diagram)
    return result


def diagrams_for_platform(platform_name):
    """The diagrams that name this platform, as (title, address) pairs for the platform's page."""
    return [(d.title, reverse("diagrams:detail", args=[d.name])) for d in read_diagrams().for_platform(platform_name)]
