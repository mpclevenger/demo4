"""One way to read a YAML file for the content files, and one way to read a day written in them."""

import re
from datetime import date
from functools import cache
from pathlib import Path

import yaml

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


@cache
def _loader_keeping_as_text(tags):
    """A YAML reader that leaves the kinds of value named in `tags` (like "timestamp" or "bool") as plain text."""
    full_tags = {f"tag:yaml.org,2002:{tag}" for tag in tags}

    class Loader(yaml.SafeLoader):
        pass

    Loader.yaml_implicit_resolvers = {
        first: [(tag, pattern) for tag, pattern in resolvers if tag not in full_tags]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    return Loader


def load_yaml(path, keep_as_text=()):
    """(the file's contents, None), or (None, a plain-words problem).

    `keep_as_text` names kinds of value to leave as text: "timestamp" keeps 2027-03-31 as text, so a day that doesn't
    exist is reported against its entry; "bool" keeps on, off, yes and no as text.
    """
    path = Path(path)
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_loader_keeping_as_text(tuple(sorted(keep_as_text)))), None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = f" near line {mark.line + 1}" if mark else ""
        return None, f"{path.name}: the file isn't valid YAML{line}. Check the indentation and colons."
    except OSError:
        return None, f"{path.name}: the file can't be read."


def read_day(value):
    """A date from a YYYY-MM-DD text (or a date the YAML reader already made), or None when it is not a real day."""
    if isinstance(value, date):
        return value
    if isinstance(value, str) and _DAY.fullmatch(value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None
