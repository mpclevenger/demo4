"""A small GitHub helper for the export scripts: graphql(query, variables) and rest(path, params).

Set two things before running (Windows: setx NAME "value", then open a new window):
  GITHUB_HOST   your GitHub server, e.g. github.yourcompany.com (no https://). Leave unset for github.com.
  GITHUB_TOKEN  a personal access token that can read the orgs' repos (scopes: repo, read:org).

Optional:
  GITHUB_CA_BUNDLE  path to your company's certificate file, if the server's certificate isn't trusted
                    by Python (error mentions CERTIFICATE_VERIFY_FAILED).
  GITHUB_MAX_REQUESTS_PER_HOUR  how many requests to make per hour at most (default 900; the server allows
                    about 1000). Requests are spaced evenly. The export's --max-requests-per-hour option
                    overrides it.

Uses only Python's standard library, so there is nothing to install.
"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = os.environ.get("GITHUB_HOST", "").strip().removeprefix("https://").removeprefix("http://").strip("/")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

if HOST and HOST != "github.com":                 # GitHub Enterprise Server
    API = f"https://{HOST}/api/v3"
    GRAPHQL_URL = f"https://{HOST}/api/graphql"
else:                                             # github.com
    API = "https://api.github.com"
    GRAPHQL_URL = "https://api.github.com/graphql"

_CA = os.environ.get("GITHUB_CA_BUNDLE", "").strip()
_SSL = ssl.create_default_context(cafile=_CA) if _CA else ssl.create_default_context()

RETRIES = 4          # tries again on busy-server errors (502/503/504)
TIMEOUT = 120        # seconds per request
MAX_WAIT = 3900      # longest single wait for the rate limit to reset (GitHub resets it every hour)
MAX_RATE_WAITS = 5   # how many times to wait for a reset or a Retry-After before giving up

# ---- rate limiting: every request goes through _send(), so the limits are kept in one place ----
SECONDS_PER_HOUR = 3600
DEFAULT_MAX_REQUESTS_PER_HOUR = 900   # a safe margin under the roughly 1000 an hour the server allows
RATE_LIMIT_RESERVE = 10               # when GitHub says this few requests are left, wait for the reset
RESET_PADDING = 5                     # extra seconds after a reset time, so the new hour has really started
SECONDARY_FIRST_WAIT = 60             # seconds to wait after the first "secondary rate limit" answer
SECONDARY_MAX_RETRIES = 4             # waits (each twice as long as the last) before giving up
SECONDS_PER_MINUTE = 60
SECONDARY_WAIT_FACTOR = 2


def _read_requests_per_hour():
    """The hourly budget from GITHUB_MAX_REQUESTS_PER_HOUR, or the default when it isn't set."""
    text = os.environ.get("GITHUB_MAX_REQUESTS_PER_HOUR", "").strip()
    if not text:
        return DEFAULT_MAX_REQUESTS_PER_HOUR
    if not text.isdigit() or int(text) < 1:
        sys.exit(f"GITHUB_MAX_REQUESTS_PER_HOUR must be a whole number above 0 (it is \"{text}\").")
    return int(text)


MAX_REQUESTS_PER_HOUR = _read_requests_per_hour()


def set_max_requests_per_hour(budget):
    """Change the hourly budget (the --max-requests-per-hour option calls this)."""
    global MAX_REQUESTS_PER_HOUR
    if int(budget) < 1:
        sys.exit("--max-requests-per-hour must be a whole number above 0.")
    MAX_REQUESTS_PER_HOUR = int(budget)


def seconds_between_requests():
    """The smallest gap between two requests that keeps us inside the hourly budget."""
    return SECONDS_PER_HOUR / MAX_REQUESTS_PER_HOUR


# Clock, sleep and the network call are named here so the tests can swap them (no real waiting, no network).
def _now():
    return time.time()


def _sleep(seconds):
    time.sleep(seconds)


def _open(req):
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL)


_next_request_not_before = 0.0    # earliest time (seconds since 1970) the next request may go
_blocked_until = 0.0              # the server told us to wait until this time
_announced_pace = False


def _how_long(seconds):
    if seconds >= SECONDS_PER_MINUTE:
        return f"{round(seconds / SECONDS_PER_MINUTE)} min"
    return f"{round(seconds)} seconds"


def _wait(seconds, reason):
    """Say what we are waiting for and why, then wait."""
    seconds = min(max(seconds, 0), MAX_WAIT)
    until = time.strftime("%H:%M", time.localtime(_now() + seconds))
    print(f"Rate limit: waiting {_how_long(seconds)} until {until} {reason} "
          f"({MAX_REQUESTS_PER_HOUR} per hour). Leave this window open.", file=sys.stderr)
    _sleep(seconds)


def _pace():
    """Before every request: wait out any server-ordered pause, then keep the even gap between requests."""
    global _next_request_not_before, _announced_pace
    if not _announced_pace:
        _announced_pace = True
        print(f"Pacing requests at {MAX_REQUESTS_PER_HOUR} per hour "
              f"(one every {seconds_between_requests():g} seconds).", file=sys.stderr)
    if _blocked_until > _now():
        _wait(_blocked_until - _now(), "before the next request")
    gap_left = _next_request_not_before - _now()
    if gap_left > 0:
        _sleep(gap_left)
    _next_request_not_before = _now() + seconds_between_requests()


def _note_server_limits(headers):
    """After every answer: if GitHub says only the reserve is left, hold the next request until the reset."""
    global _blocked_until
    try:
        remaining = int(headers.get("X-RateLimit-Remaining"))
        reset = int(headers.get("X-RateLimit-Reset"))
    except (TypeError, ValueError):
        return
    if remaining <= RATE_LIMIT_RESERVE:
        _blocked_until = max(_blocked_until, reset + RESET_PADDING)


def _seconds_to_reset(headers):
    """Seconds until X-RateLimit-Reset (a time in seconds since 1970); a minute if the server doesn't say."""
    try:
        reset = int(headers.get("X-RateLimit-Reset") or 0)
    except (TypeError, ValueError):
        reset = 0
    if not reset:
        return SECONDS_PER_MINUTE
    return max(reset - _now(), 0) + RESET_PADDING


def _wait_for_reset(headers, why):
    """Wait until GitHub's rate limit resets, then carry on."""
    _wait(_seconds_to_reset(headers), f"({why}) before the next request")


def _send(req):
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set. Set it (Windows: setx GITHUB_TOKEN \"your-token\") and open a new window.")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "trust-repo-export")
    server_tries = 0       # busy-server errors and network drops so far
    rate_waits = 0         # waits for a reset or a Retry-After so far
    secondary_waits = 0    # backoffs for the secondary rate limit so far
    while True:
        _pace()
        try:
            with _open(req) as r:
                _note_server_limits(r.headers)
                return json.loads(r.read().decode("utf-8") or "null"), r.headers
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            _note_server_limits(e.headers)
            retry_after = e.headers.get("Retry-After")
            says_rate_limit = "rate limit" in body.lower()
            if e.code in (403, 429) and (retry_after or says_rate_limit):
                if retry_after:
                    rate_waits += 1
                    if rate_waits > MAX_RATE_WAITS:
                        sys.exit("GitHub keeps asking us to slow down. Stopped after waiting several times; "
                                 "run again later (the export carries on where it stopped).")
                    _wait(int(retry_after), "because GitHub asked us to slow down")
                elif str(e.headers.get("X-RateLimit-Remaining")) == "0":
                    rate_waits += 1
                    if rate_waits > MAX_RATE_WAITS:
                        sys.exit("GitHub's hourly allowance was still used up after waiting several times. "
                                 "Run again later (the export carries on where it stopped).")
                    _wait_for_reset(e.headers, "GitHub's hourly allowance is used up")
                else:
                    secondary_waits += 1
                    if secondary_waits > SECONDARY_MAX_RETRIES:
                        sys.exit("GitHub's secondary rate limit (too many requests too fast) is still on after "
                                 f"{SECONDARY_MAX_RETRIES} waits. Stopped. Try again later, or lower "
                                 "--max-requests-per-hour (the export carries on where it stopped).")
                    wait = SECONDARY_FIRST_WAIT * SECONDARY_WAIT_FACTOR ** (secondary_waits - 1)
                    _wait(wait, "because GitHub's secondary rate limit was hit")
                continue
            server_tries += 1
            if e.code in (502, 503, 504) and server_tries < RETRIES:
                wait = 10 * server_tries
                print(f"GitHub said {e.code}; trying again in {wait}s ({server_tries}/{RETRIES - 1})", file=sys.stderr)
                _sleep(wait)
                continue
            if e.code == 401:
                sys.exit("GitHub refused the token (401). Check GITHUB_TOKEN is right and not expired.")
            sys.exit(f"GitHub error {e.code} for {req.full_url}: {body}")
        except urllib.error.URLError as e:
            server_tries += 1
            if server_tries < RETRIES:
                _sleep(5 * server_tries)
                continue
            sys.exit(f"Couldn't reach {req.full_url}: {e.reason}. Check GITHUB_HOST, the network/VPN, "
                     "or set GITHUB_CA_BUNDLE if it mentions a certificate.")


def graphql(query, variables=None):
    """Run a GraphQL query; returns its "data" part. Waits and tries again when the rate limit is used up;
    stops with GitHub's message for any other error."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for _ in range(MAX_RATE_WAITS + 1):
        req = urllib.request.Request(GRAPHQL_URL, method="POST", data=body)
        req.add_header("Content-Type", "application/json")
        out, headers = _send(req)
        errors = out.get("errors") or []
        limited = any(e.get("type") == "RATE_LIMITED" or "rate limit" in str(e.get("message", "")).lower()
                      for e in errors)
        if limited:
            _wait_for_reset(headers, "GitHub's hourly API allowance is used up")
            continue
        if errors:
            msgs = "; ".join(e.get("message", str(e)) for e in errors)
            if not out.get("data"):
                sys.exit(f"GitHub GraphQL error: {msgs}")
            print(f"GitHub GraphQL warning (some fields missing): {msgs}", file=sys.stderr)
        return out["data"]
    sys.exit("GitHub's rate limit was still used up after waiting several times. Try again later.")


def rest(path, params=None, all_pages=False):
    """GET a REST path such as "/orgs/my-org/repos". With all_pages=True, follows every page and returns one list."""
    url = path if path.startswith("http") else API + "/" + path.lstrip("/")
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    items = []
    while url:
        data, headers = _send(urllib.request.Request(url))
        if not all_pages:
            return data
        items += data if isinstance(data, list) else [data]
        url = None
        for part in (headers.get("Link") or "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip(" <>")
        # Only follow a next page on the same server: the token goes with every request, so it must never be
        # sent to a different host a response names.
        if url and urllib.parse.urlparse(url).hostname != urllib.parse.urlparse(API).hostname:
            sys.exit(f"GitHub's next page points to a different server ({urllib.parse.urlparse(url).hostname}), "
                     "so it was not followed. Check GITHUB_HOST.")
    return items


if __name__ == "__main__":       # quick check:  python github_client.py
    me = graphql("query { viewer { login } }")["viewer"]["login"]
    print(f"Connected to {GRAPHQL_URL} as {me}")
