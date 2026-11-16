"""Checks the My system questions file and explains any mistake in plain words."""

from django.core.management.base import BaseCommand, CommandError

from apps.pathfinder import questions
from apps.wiki.guide_checks import file_wording_problems


class Command(BaseCommand):
    help = "Check the My system questions (content/my-system/questions.yaml). Changes nothing."

    def handle(self, *args, **options):
        path = questions.QUESTIONS_FILE
        problems = questions.check(path)
        if path.exists():
            problems += file_wording_problems([path])
        if problems:
            raise CommandError("\n".join(problems))
        self.stdout.write(f"All good: {len(questions.read(path)[0])} My system question(s).")
