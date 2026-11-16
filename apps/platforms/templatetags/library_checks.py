"""Template pieces for the Library's audience marks and the "Proposed" mark on commands."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.platforms import audience
from apps.rcm.shape import PROPOSED_NOTE
from apps.ui.templatetags.trac_ui import links, read_lines

register = template.Library()


@register.simple_tag
def proposed_note():
    """The words shown on a command nobody has confirmed."""
    return PROPOSED_NOTE


@register.filter
def audience_key(name):
    """'Platform admins' becomes 'admins'; 'Platform users' becomes 'users'."""
    return audience.key_of(name)


@register.filter
def audience_bullets(text, active=""):
    """Guidance text as HTML, like `bullets`, with each tagged line marked for its audience.

    A line starting "- " is a bullet; a line starting with a space continues the bullet above; anything else
    is a paragraph. A tagged bullet shows its audience and carries `data-audience`, so the page can filter.
    `active` is the audience key the reader filtered to: other audiences' lines start out hidden.
    """
    html, bullets = [], []

    def close_list():
        if bullets:
            html.append(format_html("<ul>{}</ul>", mark_safe("".join(bullets))))
            bullets.clear()

    for item in read_lines(text):
        if item is None:
            close_list()
        elif item[0] == "li":
            bullets.append(_bullet(item[1], active))
        else:
            close_list()
            html.append(format_html("<p>{}</p>", links(item[1])))
    close_list()
    return mark_safe("".join(html))


def _bullet(line, active):
    name, rest = audience.split_tag(line)
    if name is None:
        return format_html("<li>{}</li>", links(rest))
    key = audience.key_of(name)
    off = " is-audience-off" if active and active != key else ""
    return format_html(
        '<li data-audience="{}" class="audience-line{}"><span class="audience-tag audience-{}">{}</span> {}</li>',
        key, off, key, name, links(rest),
    )
