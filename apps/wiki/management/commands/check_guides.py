"""Checks the guide files in content/guides and explains any mistake in plain words."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.platforms.models import Platform
from apps.wiki.guide_checks import guide_problems
from apps.wiki.starter_guides import GUIDES_DIR, GuideFileError, parse_guide


class Command(BaseCommand):
    help = "Check the starter guide files in content/guides and report problems in plain words."

    def add_arguments(self, parser):
        parser.add_argument("--folder", default=str(GUIDES_DIR), help="Folder of guide files (default: content/guides).")

    def handle(self, *args, folder, **options):
        paths = sorted(Path(folder).glob("*.md"))
        if not paths:
            raise CommandError(f"No .md guide files found in {folder}.")
        platform_names = set(Platform.objects.values_list("name", flat=True))
        failed = 0
        for path in paths:
            try:
                problems = guide_problems(parse_guide(path), platform_names)
            except GuideFileError as error:
                problems = [str(error).removeprefix(f"{path.name}: ")]
            if problems:
                failed += 1
                self.stdout.write(self.style.ERROR(f"{path.name}"))
                for problem in problems:
                    self.stdout.write(f"  - {problem}")
            else:
                self.stdout.write(f"{path.name}: OK")
        if failed:
            raise CommandError(f"{failed} of {len(paths)} guide files have problems (see above).")
        self.stdout.write(self.style.SUCCESS(f"All {len(paths)} guide files are fine."))
