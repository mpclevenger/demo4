"""next_on_path: the "Next on your path" link at the end of a control page reached from the visitor's path.

It shows only when the page address carries ?path=<risk area> (added by the links on the path) and the
visitor has answers, so other visitors see the control page unchanged and pay no extra queries.
"""

from django import template

from apps.pathfinder import answers, paths, questions

register = template.Library()


@register.inclusion_tag("pathfinder/_next.html", takes_context=True)
def next_on_path(context, control):
    request = context.get("request")
    slug = request.GET.get("path", "") if request else ""
    saved = answers.load(request, questions.questions()) if slug else None
    step = paths.next_step(paths.build(saved, questions.questions()), slug, control) if saved else None
    return {"step": step}
