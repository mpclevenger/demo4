"""The controls and risks a diagram can link to: their IDs and titles, read from content/controls/*.yaml.

The check and the pages both use this. The check needs no database, so the files are read directly. The pages fall
back to the site's own list for an item added on the site and not yet in a file.
"""

from pathlib import Path

import yaml
from django.conf import settings

CONTROLS_FOLDER = Path(settings.BASE_DIR) / "content" / "controls"
NOT_TOPIC_FILES = {"levels.yaml"}


def _items(data, key):
    entries = data.get(key) if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict) and e.get("id")] if isinstance(entries, list) else []


def titles_in_files(folder=None):
    """({control ID: title}, {risk ID: title}) from the topic files. A file that can't be read is skipped."""
    controls, risks = {}, {}
    for path in sorted(Path(folder or CONTROLS_FOLDER).glob("*.yaml")):
        if path.name in NOT_TOPIC_FILES:
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        controls.update({str(e["id"]).strip(): str(e.get("title") or "").strip() for e in _items(data, "controls")})
        risks.update({str(e["id"]).strip(): str(e.get("title") or "").strip() for e in _items(data, "risks")})
    return controls, risks


def titles_on_site():
    """The same two lists from the site's published controls and risks (needs the database)."""
    from apps.rcm import selectors

    controls = {entity.ident: version.title for entity, version in selectors.current_controls()}
    risks = {entity.ident: version.title for entity, version in selectors.current_risks()}
    return controls, risks
