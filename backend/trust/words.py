"""Small word and date helpers shared by the TRUST, Risk and metric intake code (owner, 16 Nov 2026)."""
import datetime


def tidy_spaces(value):
    """The text with its spaces tidied: no leading, trailing or doubled spaces. Nothing (None) gives ''."""
    return " ".join(str(value if value is not None else "").split())


def count_of(count, one, many=None):
    """'1 repo', '3 repos'. `many` is the plural when it is not simply `one` with an s on the end."""
    return f"{count} {one if count == 1 else (many or one + 's')}"


def today_text():
    """Today's date written 2026-11-16, for file names."""
    return datetime.date.today().isoformat()


def moment_of(iso_text):
    """A saved date and time ('2026-11-16T09:30:00.123456+00:00') as a real date, so two of them can be compared
    (as text, a missing fraction of a second would put them in the wrong order)."""
    return datetime.datetime.fromisoformat(iso_text)
