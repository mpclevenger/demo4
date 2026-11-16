"""A visitor's path: the risk areas that apply to their system, in catalog order.

Each risk area (an aspect question from the catalog, such as Access or Jobs) is on the path unless the
visitor said No to every question that names it. For each area on the path the page shows why it
applies, whether it is Ready (see `is_ready`), the published controls that fit the visitor's platforms,
and links to the Library category pages with those platforms switched on.
"""

from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.text import slugify

from apps.platforms import selectors as platform_selectors
from apps.platforms.categories import Category
from apps.rcm.selectors import current_controls, sort_by_level

from . import selectors

EVERY_SYSTEM = "Applies to every system"


@dataclass
class Area:
    question: object  # the AspectQuestion
    number: int
    why: str
    ready: bool
    controls: list = field(default_factory=list)  # (control, version, url on the path), most important level first
    library: list = field(default_factory=list)  # (Category, url): category pages with the platforms switched on

    @property
    def slug(self):
        return area_slug(self.question)


@dataclass
class Path:
    areas: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # (AspectQuestion, the question answered No)


def area_slug(question):
    return slugify(question.label)


def control_url(control, slug):
    """The control page, marked as reached from the area `slug` so it can offer "Next on your path"."""
    return f"{control.get_absolute_url()}?path={slug}"


def decide(question, questions, answers):
    """(applies, why) for one risk area, from the visitor's answers.

    Areas no question names apply to every system. Otherwise a Yes to any question naming the area puts
    it on the path, and so does leaving such a question unanswered. Only a No to every one leaves it out;
    `why` is then the first of those questions.
    """
    naming = [q for q in questions if q.names(question.label)]
    if not naming:
        return True, EVERY_SYSTEM
    for q in naming:
        if answers.reply(q) == "yes":
            return True, f"Because {q.because}" if q.because else f"Because you said yes to: {q.text}"
    for q in naming:
        if answers.reply(q) != "no":
            return True, f"Included until you answer: {q.text}"
    return False, naming[0].text


def is_ready(question, platforms, guidance):
    """Is this risk area Ready on the visitor's path? Otherwise it shows In progress.

    The rule: Ready when every platform the visitor picked has published guidance for the risk area.
    With no platform picked, Ready when at least one category's published practices cover it.
    `guidance` is selectors.published_guidance_lines(). This is the only place the rule lives.
    """
    if platforms:
        return all(question.pk in guidance["platform"].get(p.pk, ()) for p in platforms)
    return any(question.pk in lines for lines in guidance["category"].values())


def platform_categories(platforms):
    """The categories of the picked platforms, in the site's category order."""
    picked = {key for platform in platforms for key in platform.categories}
    return [Category(key) for key in Category.values if key in picked]


def library_links(question, platforms):
    """(Category, url) for each category of the picked platforms, opened at this risk area with them switched on."""
    links = []
    for category in platform_categories(platforms):
        query = "&".join(f"platform={p.slug}" for p in platforms if category.value in p.categories)
        url = reverse("platforms:category", args=[category.value])
        links.append((category, f"{url}?{query}#aspect-{area_slug(question)}"))
    return links


def fitting_controls(platforms):
    """Published controls for the picked platforms' categories (or tagged to the platforms); all with none picked."""
    controls = current_controls()
    if not platforms:
        return controls
    categories = [category.value for category in platform_categories(platforms)]
    return platform_selectors.applicable_controls(controls, categories=categories, platforms=platforms)


def build(answers, questions):
    """The visitor's Path for their Answers and the questions from the file."""
    guidance = selectors.published_guidance_lines()
    controls = sort_by_level(fitting_controls(answers.platforms), lambda pair: pair[1].level)
    path = Path()
    for question in platform_selectors.active_questions():
        applies, why = decide(question, questions, answers)
        if not applies:
            path.skipped.append((question, why))
            continue
        path.areas.append(Area(
            question=question,
            number=len(path.areas) + 1,
            why=why,
            ready=is_ready(question, answers.platforms, guidance),
            controls=[
                (c, v, control_url(c, area_slug(question)))
                for c, v in controls
                if v.topic_id == question.topic_id
            ],
            library=library_links(question, answers.platforms),
        ))
    return path


def next_step(path, slug, control):
    """Where "Next on your path" goes from a control reached from the area `slug`.

    The next control in the same area; else the first control of the next area that has one; else back
    to the path. Returns {"text", "url"}, or None when the area is not on the visitor's path.
    """
    position = next((i for i, area in enumerate(path.areas) if area.slug == slug), None)
    if position is None:
        return None
    area = path.areas[position]
    ids = [c.pk for c, _, _ in area.controls]
    if control.pk in ids and ids.index(control.pk) + 1 < len(ids):
        following, version, url = area.controls[ids.index(control.pk) + 1]
        return {"text": f"{following.ident} {version.title}", "url": url}
    for later in path.areas[position + 1:]:
        if later.controls:
            following, version, url = later.controls[0]
            return {"text": f"{later.question.label}: {following.ident} {version.title}", "url": url}
    return {"text": "Back to your path", "url": reverse("pathfinder:path")}
