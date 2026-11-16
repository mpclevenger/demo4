"""Check the diagram files in content/diagrams."""

from django.core.management.base import BaseCommand, CommandError

from apps.diagrams import diagrams_file, register, svg
from apps.core.yaml_files import load_yaml
from apps.platforms import catalog_file
from apps.wiki.guide_checks import file_wording_problems


def platform_names():
    """The platform names in content/platforms/catalog.yaml (read from the file, no database needed)."""
    data, _ = load_yaml(catalog_file.CATALOG_FILE)
    entries = data.get("platforms") if isinstance(data, dict) else None
    return {e["name"] for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)} if isinstance(entries, list) else set()


def picture_problems(diagram, controls, risks):
    """Plain-word problems with one diagram's picture: unreadable, or a bubble that links to nothing real."""
    picture = svg.read_picture(diagram.path)
    problems = [f"{diagram.file}: {text}" for text in picture.problems]
    for link in picture.links:
        known = controls if link.kind == "controls" else risks
        kind_word = "control" if link.kind == "controls" else "risk"
        if link.ident not in known:
            problems.append(f"{diagram.file}: a bubble links to the {kind_word} '{link.ident}', which isn't in content/controls. Check the ID.")
    return problems


def all_problems():
    """Every problem in the list file and the pictures, in plain words, plus the diagrams that were read."""
    found = diagrams_file.read_diagrams()
    problems = list(found.problems)
    controls, risks = register.titles_in_files()
    known_platforms = platform_names()
    for diagram in found.items:
        for name in diagram.platforms:
            if name not in known_platforms:
                problems.append(f"{diagram.file}: the platform '{name}' isn't in content/platforms/catalog.yaml. Use the name exactly as TRAC shows it.")
        problems += picture_problems(diagram, controls, risks)
    if diagrams_file.FILE.exists():
        problems += file_wording_problems([diagrams_file.FILE])
    return problems, found


class Command(BaseCommand):
    help = "Check content/diagrams: the list file, each picture, the platform names and the links to controls and risks. Changes nothing."

    def handle(self, *args, **options):
        problems, found = all_problems()
        if problems:
            raise CommandError("\n".join(problems))
        if not diagrams_file.FILE.exists():
            self.stdout.write("All good: there is no diagrams.yaml yet, so there are no diagrams.")
            return
        self.stdout.write(f"All good: {len(found.items)} diagram(s).")
