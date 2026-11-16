"""Checks the control and risk files in content/controls and explains any mistake in plain words."""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.rcm import control_files, engine_files
from apps.wiki.guide_checks import file_wording_problems


class Command(BaseCommand):
    help = "Check the YAML files in content/controls without changing anything. Exits with 1 if any file has a problem."

    def add_arguments(self, parser):
        parser.add_argument("--folder", help="Folder of .yaml files. Defaults to content/controls.")

    def handle(self, *args, folder=None, **options):
        report = control_files.read_folder(folder)
        report.problems += _address_problems(report)
        report.problems += file_wording_problems(sorted(Path(folder or control_files.DEFAULT_FOLDER).glob("*.yaml")))
        for warning in report.warnings:
            self.stdout.write(f"Warning: {warning}")
        for problem in report.problems:
            self.stdout.write(f"Problem: {problem}")
        if report.problems:
            self.stdout.write(f"{len(report.problems)} problem(s) found. Fix them and run this again.")
            sys.exit(1)
        controls = sum(len(p.controls) for p in report.plans)
        risks = sum(len(p.risks) for p in report.plans)
        self.stdout.write(self.style.SUCCESS(f"All good: {len(report.plans)} file(s), {controls} controls, {risks} risks."))


def _address_problems(report):
    """Plain-word problems with a control's `addresses`: not a list of ids, or ids the risk engine files don't have.
    Controls with no `addresses` (the usual case for now) are skipped, and then the engine files are not even read."""
    listed = [(plan, ref, item) for plan in report.plans for ref, _, _, item in plan.controls if "addresses" in item]
    if not listed:
        return []
    known = engine_files.engine_risk_ids()
    return [
        f"{plan.path.name}, control '{ref}', field 'addresses': {text}"
        for plan, ref, item in listed
        for text in engine_files.address_problems(item["addresses"], known)
    ]
