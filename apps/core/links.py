"""Helpers for links: build a page address only when the page exists, and the one rule for which links may be written in content."""

from django.urls import NoReverseMatch, reverse

WEB_START = "https://"
INSECURE_WEB_START = "http://"
TRAC_PAGE_START = "/"  # a page on TRAC itself, for example /guides/
OTHER_SITE_STARTS = ("//", "/\\")  # browsers read these as an address on another site


def reverse_if_exists(name):
    """The URL for `name`, or None when no such route exists yet."""
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def is_web_address(url, allow_http=False):
    """True for an https:// address (and an http:// one when `allow_http` is True)."""
    return url.startswith(WEB_START) or (allow_http and url.startswith(INSECURE_WEB_START))


def is_trac_page(url):
    """True for a page on TRAC itself ("/guides/..."). "//" and "/\\" would lead to another site, so they are not allowed."""
    return url.startswith(TRAC_PAGE_START) and not url.startswith(OTHER_SITE_STARTS)


def is_allowed_link(url, allow_http=False):
    """True for a link content may carry: a TRAC page or a web address. Example: "/guides/" yes, "//evil.com" no."""
    return is_trac_page(url) or is_web_address(url, allow_http)
