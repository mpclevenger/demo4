"""TRAC's published list of controls, kept as a copy so the Risk site works when TRAC is down.

TRAC publishes GET <TRAC_URL>/registers/controls.json:

    {"published_at": "2026-11-15T12:00:00Z",
     "controls": [{"code": "MO-02", "title": "...", "url": "https://trac.../controls/MO-02/", "addresses": ["air.ops.02"]}]}

"addresses" lists the IDs of the risks a control addresses. It starts empty for every control; the owner maps it later.

The site fetches the list, keeps the copy with the date it was fetched, and always reads the kept copy. A new copy
is fetched when someone in Tech Risk asks for one, and when a team submits with no copy yet. Looking at a page never
fetches anything. Nothing here touches a rating.
"""
import json
import os
import time
import urllib.error
import urllib.request

from trust import storage

CONTROLS_PATH = "/registers/controls.json"
WEB_SCHEMES = ("http://", "https://")
SECONDS_BEFORE_GIVING_UP = 5                 # a short wait: the page must not hang because TRAC is slow
LARGEST_LIST_IN_BYTES = 2_000_000
SECONDS_BEFORE_TRYING_AGAIN = 60             # after a failed fetch, don't make every page load wait again

_last_failed_at = {"time": None}


class CouldNotFetch(Exception):
    """TRAC's list could not be fetched or read. The message is a plain sentence."""


class OnlyWebRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to a web address (http or https), never to an ftp:// or file:// one."""

    def redirect_request(self, request, fp, code, message, headers, new_url):
        if not new_url.lower().startswith(WEB_SCHEMES):
            raise urllib.error.URLError("redirected to an address that is not a web address")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def trac_url():
    """TRAC's address from the TRAC_URL setting, without a closing slash. Empty when it isn't set."""
    return (os.environ.get("TRAC_URL") or "").strip().rstrip("/")


def clean(document):
    """The list as the site keeps it: {"published_at", "controls": [{"code", "title", "url", "addresses"}]}.
    A control with no code is left out. A link that isn't http or https is dropped, so it can't be a script."""
    if not isinstance(document, dict) or not isinstance(document.get("controls"), list):
        raise CouldNotFetch("TRAC's list of controls is not in the shape the Risk site expects.")
    kept = []
    for control in document["controls"]:
        if not isinstance(control, dict) or not str(control.get("code") or "").strip():
            continue
        link = str(control.get("url") or "").strip()
        addresses = control.get("addresses")
        kept.append({"code": str(control["code"]).strip(),
                     "title": str(control.get("title") or "").strip(),
                     "url": link if link.lower().startswith(WEB_SCHEMES) else "",
                     "addresses": [str(risk_id) for risk_id in addresses] if isinstance(addresses, list) else []})
    published_at = document.get("published_at")
    return {"published_at": str(published_at) if published_at else None, "controls": kept}


def fetch_from_trac():
    """Ask TRAC for its list of controls. Returns the cleaned list. Raises CouldNotFetch with a plain sentence."""
    base = trac_url()
    if not base:
        raise CouldNotFetch("TRAC's address is not set (TRAC_URL), so its list of controls can't be fetched.")
    if not base.lower().startswith(WEB_SCHEMES):
        raise CouldNotFetch("TRAC's address (TRAC_URL) must start with http:// or https://, so its list of controls can't be fetched.")
    web_only = urllib.request.build_opener(OnlyWebRedirects)
    try:
        with web_only.open(base + CONTROLS_PATH, timeout=SECONDS_BEFORE_GIVING_UP) as response:
            text = response.read(LARGEST_LIST_IN_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        raise CouldNotFetch("TRAC could not be reached, so the Risk site is using the copy it already has.") from None
    if len(text) > LARGEST_LIST_IN_BYTES:
        raise CouldNotFetch("TRAC's list of controls is far bigger than expected, so it was not kept.")
    try:
        document = json.loads(text)
    except ValueError:
        raise CouldNotFetch("TRAC's list of controls could not be read.") from None
    return clean(document)


def refresh():
    """Fetch a new copy and keep it. Returns the kept copy. Raises CouldNotFetch."""
    try:
        fetched = fetch_from_trac()
    except CouldNotFetch:
        _last_failed_at["time"] = time.monotonic()
        raise
    _last_failed_at["time"] = None
    return storage.add_risk_controls_copy(fetched["published_at"], fetched["controls"])


def copy_in_use():
    """The kept copy, fetching the first one when there is none yet. Returns (copy or None, a sentence or None).
    The sentence says why there is no copy, or that TRAC could not be reached."""
    copy = storage.risk_controls_copy()
    if copy is not None:
        return copy, None
    just_failed = (_last_failed_at["time"] is not None
                   and time.monotonic() - _last_failed_at["time"] < SECONDS_BEFORE_TRYING_AGAIN)
    if just_failed or not trac_url():
        return None, "TRAC's list of controls has not been fetched yet."
    try:
        return refresh(), None
    except CouldNotFetch as problem:
        return None, str(problem)


def controls_by_risk(copy):
    """{risk id: [{"code", "title", "url"}]} for every risk some control addresses. Risks no control names are left out."""
    by_risk = {}
    for control in (copy or {}).get("controls", []):
        for risk_id in control["addresses"]:
            by_risk.setdefault(risk_id, []).append({"code": control["code"], "title": control["title"], "url": control["url"]})
    return by_risk
