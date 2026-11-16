"""My system: two screens. "Tell us about your system" asks a few questions; "Your path" shows what applies.

The answers live in the visitor's session (see answers.py); nothing is stored in the database. Everyone
who can read the site can use these pages.
"""

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts import permissions
from apps.ui.bands import make_band

from . import answers, paths, questions, selectors

can_view = permissions.permission_required_for(permissions.can_view)

TIMELINES_GUIDE = "timings-your-team-sets"


def _band(title, summary, current=None):
    crumbs = [("Home", "/"), ("My system", reverse("pathfinder:index") if current else None)]
    if current:
        crumbs.append((current, None))
    return make_band(crumbs, title=title, summary=summary)


@can_view
def index(request):
    """Screen 1: the questions, filled in with the visitor's earlier answers. Saving opens their path."""
    asked = questions.questions()
    if request.method == "POST":
        answers.save(request, answers.from_form(request.POST, asked), asked)
        return redirect("pathfinder:path")
    saved = answers.load(request, asked) or answers.Answers()
    context = {
        "nav_active": "my_system",
        "show_comment_box": False,
        "band": _band(
            "Tell us about your system",
            "A few quick answers, and we'll show the risk areas and controls that apply to it, in order.",
        ),
        "platforms": [(p, p in saved.platforms) for p in selectors.active_platforms()],
        "questions": [(q, saved.reply(q)) for q in asked],
        "sox_choices": answers.SOX_CHOICES.items(),
        "tier_choices": answers.TIER_CHOICES.items(),
        "saved": saved,
    }
    return render(request, "pathfinder/index.html", context)


@can_view
def path(request):
    """Screen 2: the risk areas that apply, numbered, then the ones the answers left out."""
    asked = questions.questions()
    saved = answers.load(request, asked)
    if saved is None:
        return redirect("pathfinder:index")
    context = {
        "nav_active": "my_system",
        "band": _band("Your path", "The risk areas that apply to your system, in order.", current="Your path"),
        "answers": saved,
        "path": paths.build(saved, asked),
        "timelines_url": reverse("wiki:page", args=[TIMELINES_GUIDE]),
    }
    return render(request, "pathfinder/path.html", context)


@can_view
@require_POST
def start_over(request):
    answers.clear(request)
    return redirect("pathfinder:index")
