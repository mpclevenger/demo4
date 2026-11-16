"""Writes docs/COMMANDS_TO_CONFIRM.md: every command on a control page, by platform, for the platform owners.

The list is made from the control files in content/controls, so run this again after a command changes or after
an owner confirms one (add `confirmed_by` and `confirmed_on` to the command in its control file).
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.yaml_files import load_yaml
from apps.rcm.control_files import topic_files
from apps.rcm.shape import PROPOSED_NOTE, is_proposed

CONTROLS_DIR = Path(settings.BASE_DIR) / "content" / "controls"
LIST_FILE = Path(settings.BASE_DIR) / "docs" / "COMMANDS_TO_CONFIRM.md"

INTRO = """# Commands to confirm with each platform owner

Every query and command shown on a control page, grouped by platform. Each one is read-only.
Until someone who runs the platform confirms a command works on the firm's version and returns what the
step says, the control page shows it marked "{proposed}"
To record a confirmation, add two lines to the command in its control file (content/controls/*.yaml):
`confirmed_by: <name>` and `confirmed_on: YYYY-MM-DD`. The mark comes off, and this list shows it as confirmed.
This list is made from the control files by `manage.py commands_to_confirm`; run it again after a change.

{summary}
"""


def commands_by_platform(folder=CONTROLS_DIR):
    """{platform name: [one entry per command]} from the control files, platforms in name order.

    An entry holds the control's id and title, the step number and its `do` line, and the command as written.
    """
    found = {}
    for path in topic_files(folder):
        data, problem = load_yaml(path)
        if problem:
            raise CommandError(problem)
        for control in (data or {}).get("controls") or []:
            for number, step in enumerate(control.get("steps") or [], start=1):
                for command in step.get("commands") or []:
                    entry = _entry(path, control, number, step, command)
                    found.setdefault(command["platform"], []).append(entry)
    return dict(sorted(found.items()))


def _entry(path, control, number, step, command):
    """One command's entry for `commands_by_platform`, or a plain CommandError when a line it needs is missing."""
    wanted = {"control": (control, ("id", "title")), "step": (step, ("do",)), "command": (command, ("platform", "code"))}
    for what, (item, keys) in wanted.items():
        for key in keys:
            if key not in item:
                raise CommandError(f"{path.name}: control {control.get('id', '(no id)')}, step {number}: the {what} needs a '{key}' line. Run check_controls to see every problem.")
    return {"control_id": control["id"], "control_title": control["title"], "step": number, "do": step["do"], "command": command}


def render(found):
    """The text of the list for `commands_by_platform` output."""
    every = [entry["command"] for entries in found.values() for entry in entries]
    proposed = sum(is_proposed(command) for command in every)
    summary = f"{len(every)} commands: {proposed} proposed, {len(every) - proposed} confirmed."
    lines = [INTRO.format(proposed=PROPOSED_NOTE, summary=summary)]
    for platform, entries in found.items():
        lines.append(f"## {platform} ({len(entries)})\n")
        for entry in entries:
            lines.append(_entry_text(entry))
    return "\n".join(lines).rstrip("\n") + "\n"


def _entry_text(entry):
    command = entry["command"]
    status = PROPOSED_NOTE if is_proposed(command) else f"Confirmed by {command['confirmed_by']} on {command['confirmed_on']}."
    parts = [f"### {entry['control_id']}, step {entry['step']}: {entry['do']}\n",
             f"Control: {entry['control_title']}\n", f"Status: {status}\n"]
    if command.get("note"):
        parts.append(f"{command['note'].strip()}\n")
    parts.append(f"```\n{command['code'].rstrip()}\n```\n")
    return "\n".join(parts)


class Command(BaseCommand):
    help = "Write docs/COMMANDS_TO_CONFIRM.md from the control files."

    def handle(self, *args, **options):
        found = commands_by_platform()
        LIST_FILE.write_text(render(found), encoding="utf-8")
        self.stdout.write(f"Wrote {LIST_FILE.name}: {sum(len(e) for e in found.values())} commands.")
