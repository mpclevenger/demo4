"""Check content/settings.yaml (the values we fill in later) and every placeholder the content uses."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core import placeholders

# The content folders whose files can hold a placeholder. README files only show examples, so they are skipped.
CONTENT_FOLDERS = ("guides", "controls", "platforms", "home", "my-system", "calendar")
CONTENT_SUFFIXES = (".md", ".yaml", ".yml")


def content_files(content_folder):
    """Every content file that can hold a placeholder."""
    root = Path(content_folder)
    files = []
    for folder in CONTENT_FOLDERS:
        files += [p for p in sorted((root / folder).rglob("*")) if p.suffix in CONTENT_SUFFIXES and p.name != "README.md"]
    return files


def settings_report(content_folder, settings_file):
    """(problems, waiting) for the settings file and the placeholders in the content.

    problems: plain sentences for the things to fix. waiting: [(key, times used)] for each key with no value yet.
    """
    read = placeholders.read_values(settings_file)
    problems = list(read.problems)
    used = {}
    for path in content_files(content_folder):
        text = path.read_text(encoding="utf-8")
        for key, count in placeholders.keys_used(text).items():
            used[key] = used.get(key, 0) + count
            if key not in read.items:
                problems.append(f"{path.name}: the placeholder '{key}' has no entry in {Path(settings_file).name}. Add one, or fix the spelling.")
            elif key in placeholders.links_used(text) and read.items[key].kind == "text":
                problems.append(f"{path.name}: '{key}' is used as a link but its kind is text. Use kind link or email.")
    waiting = [(key, used.get(key, 0)) for key, item in read.items.items() if not item.is_set]
    return list(dict.fromkeys(problems)), waiting


class Command(BaseCommand):
    help = "Check content/settings.yaml and the placeholders used in the content. Changes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--content-folder", default=str(Path(settings.BASE_DIR) / "content"))
        parser.add_argument("--file", default=str(placeholders.FILE))

    def handle(self, *args, content_folder, file, **options):
        problems, waiting = settings_report(content_folder, file)
        if problems:
            raise CommandError("\n".join(problems))
        self.stdout.write(self.style.SUCCESS(f"The values file is fine ({len(placeholders.read_values(file).items)} values)."))
        if waiting:
            names = ", ".join(f"{key} (used {count}x)" if count else f"{key} (not used yet)" for key, count in waiting)
            self.stdout.write(f"{len(waiting)} placeholder(s) waiting for a value: {names}")
        else:
            self.stdout.write("Every placeholder has a value.")
