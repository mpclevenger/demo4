"""Checks the "References" list (label and link) that guides, controls and risks can carry."""

from django.core.exceptions import ValidationError

from .links import is_allowed_link

HELP = 'Optional links to the guidance this is based on: [{"label": str, "url": str}].'
MAX_REFERENCES = 10


def check_references(references, field="references"):
    """Validate a list of {"label", "url"} dicts; raises ValidationError keyed to `field`."""
    if not isinstance(references, list) or not all(isinstance(r, dict) for r in references):
        raise ValidationError({field: "Use a list of references."})
    if len(references) > MAX_REFERENCES:
        raise ValidationError({field: f"Add at most {MAX_REFERENCES} references."})
    for number, reference in enumerate(references, start=1):
        label, url = reference.get("label"), reference.get("url")
        if not isinstance(label, str) or not label.strip():
            raise ValidationError({field: f"Reference {number}: add a label."})
        if not isinstance(url, str) or not is_allowed_link(url, allow_http=True):
            raise ValidationError({field: f"Reference {number}: the link must start with https://, http://, or / for a page on TRAC."})
