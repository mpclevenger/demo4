"""The My system questions, content/my-system/questions.yaml: read once and checked.

Each entry is a yes/no question and the risk areas (aspect labels from content/platforms/catalog.yaml)
that a Yes puts on the visitor's path. A risk area no question names applies to every system. The file
is read the first time it is needed and kept, so a change shows once the site restarts. `check_my_system`
reports mistakes in plain words; the page itself never fails on this file: an entry with a mistake is
skipped, and a label that is not a risk area simply matches nothing.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings
from django.utils.text import slugify

from apps.core.yaml_files import load_yaml
from apps.platforms.catalog_file import CATALOG_FILE

QUESTIONS_FILE = Path(settings.BASE_DIR) / "content" / "my-system" / "questions.yaml"
FIELDS = {"question", "because", "shows"}


@dataclass(frozen=True)
class Question:
    key: str  # made from the question's words; answers in the visitor's session are kept under it
    text: str
    because: str
    shows: tuple  # risk-area labels, as written in the file

    def names(self, label):
        """Does this question switch on the risk area with this label? Capital letters do not matter."""
        return label.lower() in {shown.lower() for shown in self.shows}


def read(path=QUESTIONS_FILE):
    """(questions, problems): the entries without mistakes, and a plain-word line for each mistake."""
    name = Path(path).name
    data, problem = load_yaml(path)
    if problem:
        return [], [problem]
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        return [], [f"{name}: expected a list called 'questions'."]
    problems = [f"{name}: '{key}' isn't a known field. Use questions." for key in data.keys() - {"questions"}]
    found, keys = [], set()
    for number, entry in enumerate(data["questions"], start=1):
        where = f"{name}, question {number}"
        question = _entry(entry, where, problems)
        if question is None:
            continue
        if question.key in keys:
            problems.append(f"{where}: the same question is asked twice.")
            continue
        keys.add(question.key)
        found.append(question)
    return found, problems


def _entry(entry, where, problems):
    """One Question from a file entry, or None after adding what is wrong to `problems`."""
    if not isinstance(entry, dict):
        problems.append(f"{where}: expected 'question', 'shows' and an optional 'because'.")
        return None
    for key in entry.keys() - FIELDS:
        problems.append(f"{where}: '{key}' isn't a known field. Use question, because and shows.")
    text, because, shows = entry.get("question"), entry.get("because", ""), entry.get("shows")
    if not isinstance(text, str) or not text.strip().endswith("?"):
        problems.append(f"{where}: 'question' needs a yes/no question ending with a question mark.")
        return None
    if not isinstance(because, str):
        problems.append(f"{where}: 'because' should be a short line of text.")
        return None
    if not isinstance(shows, list) or not shows or not all(isinstance(s, str) and s.strip() for s in shows):
        problems.append(f"{where}: 'shows' needs at least one risk area, for example [Jobs].")
        return None
    return Question(slugify(text)[:60], text.strip(), because.strip(), tuple(s.strip() for s in shows))


def check(path=QUESTIONS_FILE, labels=None):
    """Plain-word problems with the questions file, including labels that are not risk areas.

    `labels` are the known risk-area labels; by default the aspects in content/platforms/catalog.yaml.
    """
    if labels is None:
        labels = catalog_labels()
    known = {label.lower() for label in labels}
    found, problems = read(path)
    for question in found:
        for label in question.shows:
            if label.lower() not in known:
                problems.append(
                    f"{Path(path).name}, question '{question.text}': '{label}' isn't a risk area in catalog.yaml. "
                    f"Use one of: {', '.join(labels)}."
                )
    return problems


def catalog_labels(path=CATALOG_FILE):
    """The risk-area labels under "aspects" in the catalog file (the catalog's own check reports its mistakes)."""
    data, _ = load_yaml(path)
    aspects = data.get("aspects") if isinstance(data, dict) else None
    return [a["label"] for a in aspects or [] if isinstance(a, dict) and isinstance(a.get("label"), str)]


@cache
def questions():
    """The questions the site shows, read from the file the first time they are needed."""
    return read()[0]
