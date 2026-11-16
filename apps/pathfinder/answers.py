"""The visitor's answers on My system, kept in their session under one key. Nothing is stored in the database.

The session holds plain values: platform slugs, "yes" or "no" for each question (by its key), the SOX
answer and the BCP tier. They are checked every time they are read, so a platform switched off since,
a question removed from the file or a value typed by hand is simply ignored.
"""

from dataclasses import dataclass, field

from apps.platforms.models import Platform

SESSION_KEY = "my_system"

SOX_CHOICES = {"yes": "Yes", "no": "No", "not_sure": "Not sure"}
TIER_CHOICES = {"0-1": "0 or 1", "2": "2", "3+": "3 or higher", "not_sure": "Not sure"}
NOT_SURE = "not_sure"
YES_NO = ("yes", "no")


@dataclass
class Answers:
    platforms: list = field(default_factory=list)  # Platform objects, in site order
    replies: dict = field(default_factory=dict)  # question key -> "yes" or "no"; unanswered questions are absent
    sox: str = NOT_SURE
    tier: str = NOT_SURE

    def reply(self, question):
        return self.replies.get(question.key, "")

    @property
    def tier_label(self):
        return "Tier not sure" if self.tier == NOT_SURE else f"Tier {TIER_CHOICES[self.tier]}"

    @property
    def sox_label(self):
        """How the SOX answer reads in the bar; empty when the system is not on the list."""
        return {"yes": "SOX in scope", "not_sure": "SOX scope not sure"}.get(self.sox, "")

    @property
    def summary(self):
        """The bar's "Showing guidance for: ..." items, as a list of short phrases."""
        names = [platform.name for platform in self.platforms] or ["Any platform"]
        return [*names, self.tier_label, *filter(None, [self.sox_label])]


def clean(raw, platform_slugs, question_keys):
    """The session value for raw answers: unknown platforms, questions and values are dropped.

    `raw` is a dict like the one saved (from the form or the session). Returns a plain dict.
    """
    raw = raw if isinstance(raw, dict) else {}
    platforms = raw.get("platforms")
    replies = raw.get("replies")
    return {
        "platforms": [s for s in platforms if s in platform_slugs] if isinstance(platforms, list) else [],
        "replies": {
            key: value for key, value in replies.items() if key in question_keys and value in YES_NO
        } if isinstance(replies, dict) else {},
        "sox": raw.get("sox") if raw.get("sox") in SOX_CHOICES else NOT_SURE,
        "tier": raw.get("tier") if raw.get("tier") in TIER_CHOICES else NOT_SURE,
    }


def from_form(post, questions):
    """The raw answers in a submitted questions form (checked by `clean` when saved)."""
    return {
        "platforms": post.getlist("platform"),
        "replies": {q.key: post.get(f"q-{q.key}", "") for q in questions},
        "sox": post.get("sox", ""),
        "tier": post.get("tier", ""),
    }


def has_answers(request):
    """Has the visitor answered the questions? Reads the session only, so it costs no query."""
    return isinstance(request.session.get(SESSION_KEY), dict)


def platform_slugs(request):
    """The slugs of the visitor's platforms as saved, without a query. Callers keep only the ones they know."""
    saved = request.session.get(SESSION_KEY)
    platforms = saved.get("platforms") if isinstance(saved, dict) else None
    return [s for s in platforms if isinstance(s, str)] if isinstance(platforms, list) else []


def save(request, raw, questions):
    active = set(Platform.objects.filter(is_active=True).values_list("slug", flat=True))
    request.session[SESSION_KEY] = clean(raw, active, {q.key for q in questions})


def load(request, questions):
    """The visitor's Answers, or None when they have not answered. One query, for their platforms."""
    if not has_answers(request):
        return None
    saved = request.session[SESSION_KEY]
    slugs = platform_slugs(request)
    platforms = list(Platform.objects.filter(slug__in=slugs, is_active=True)) if slugs else []
    data = clean(saved, {p.slug for p in platforms}, {q.key for q in questions})
    return Answers(platforms=platforms, replies=data["replies"], sox=data["sox"], tier=data["tier"])


def clear(request):
    request.session.pop(SESSION_KEY, None)
