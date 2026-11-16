"""The "Showing guidance for: ..." bar under the top bar, on every page once the visitor has answered My system.

No query at all when they have not answered; one small query for their platforms' names when they have.
The My system pages show the answers themselves, so the bar is left off there.
"""

from . import answers, questions


def my_system_bar(request):
    match = getattr(request, "resolver_match", None)
    on_my_system = match is not None and match.namespace == "pathfinder"
    if on_my_system or not hasattr(request, "session") or not answers.has_answers(request):
        return {}
    return {"my_system_bar": answers.load(request, questions.questions())}
