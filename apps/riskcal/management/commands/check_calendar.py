"""Check the risk and control calendar files in content/calendar."""

from django.core.management.base import BaseCommand, CommandError

from apps.riskcal import events_file
from apps.wiki.guide_checks import file_wording_problems


class Command(BaseCommand):
    help = "Check the risk and control calendar files (events.yaml and control-dates.csv, if there is one). Changes nothing."

    def handle(self, *args, **options):
        calendar = events_file.read_calendar()
        dates = events_file.control_dates_path(events_file.FILE)
        problems = calendar.problems + file_wording_problems([events_file.FILE] + ([dates] if dates.exists() else []))
        if problems:
            raise CommandError("\n".join(problems))
        events = len(calendar.events) - calendar.control_dates
        self.stdout.write(
            f"All good: {events} event(s), {calendar.control_dates} control due date(s) and {len(calendar.types)} event type(s).")
