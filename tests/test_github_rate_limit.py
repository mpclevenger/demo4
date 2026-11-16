"""tools/github_client.py keeps to the hourly request budget and the server's own rate-limit signals.
No network and no real waiting: the clock, the sleep and the network call are swapped for fakes."""
import email.message
import io
import json
import pathlib
import sys
import urllib.error

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import github_client as client  # noqa: E402

START_TIME = 1_800_000_000      # a made-up "now", seconds since 1970


def headers_of(**pairs):
    message = email.message.Message()
    for name, value in pairs.items():
        message[name.replace("_", "-")] = str(value)
    return message


class FakeAnswer:
    def __init__(self, headers):
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps({"ok": True}).encode()


class FakeWorld:
    """A clock that moves only when the code sleeps, and a server that answers from a list."""

    def __init__(self, answers):
        self.now = START_TIME
        self.sleeps = []
        self.answers = list(answers)
        self.requests_made = 0

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def open(self, req):
        self.requests_made += 1
        answer = self.answers.pop(0) if self.answers else ("ok", {})
        kind, extra = answer
        if kind == "ok":
            return FakeAnswer(headers_of(**extra))
        body = io.BytesIO(extra.get("body", "").encode())
        raise urllib.error.HTTPError("https://x/api", kind, "error", headers_of(**extra.get("headers", {})), body)


@pytest.fixture
def world(monkeypatch):
    def make(answers=(), budget=900):
        fake = FakeWorld(answers)
        monkeypatch.setattr(client, "TOKEN", "test-token")
        monkeypatch.setattr(client, "_now", lambda: fake.now)
        monkeypatch.setattr(client, "_sleep", fake.sleep)
        monkeypatch.setattr(client, "_open", fake.open)
        monkeypatch.setattr(client, "MAX_REQUESTS_PER_HOUR", budget)
        monkeypatch.setattr(client, "_next_request_not_before", 0.0)
        monkeypatch.setattr(client, "_blocked_until", 0.0)
        monkeypatch.setattr(client, "_announced_pace", False)
        return fake
    return make


def test_at_900_an_hour_requests_are_four_seconds_apart(world):
    # 3600 seconds in an hour / 900 requests = 4 seconds between requests
    fake = world()
    client.rest("/a")
    client.rest("/b")
    client.rest("/c")
    assert client.seconds_between_requests() == 4
    assert fake.sleeps == [4, 4]
    assert fake.requests_made == 3


def test_a_different_budget_changes_the_gap(world):
    world(budget=360)       # 3600 / 360 = 10 seconds
    assert client.seconds_between_requests() == 10


def test_when_remaining_reaches_the_reserve_it_waits_until_the_reset(world):
    reset = START_TIME + 600
    fake = world([("ok", {"X_RateLimit_Remaining": client.RATE_LIMIT_RESERVE, "X_RateLimit_Reset": reset})])
    client.rest("/a")
    client.rest("/b")
    waited_until = fake.now
    assert waited_until == reset + client.RESET_PADDING
    assert fake.requests_made == 2


def test_plenty_remaining_means_no_long_wait(world):
    fake = world([("ok", {"X_RateLimit_Remaining": 500, "X_RateLimit_Reset": START_TIME + 600})])
    client.rest("/a")
    client.rest("/b")
    assert fake.sleeps == [4]


def test_a_429_with_retry_after_waits_that_long_and_tries_again(world, capsys):
    fake = world([(429, {"headers": {"Retry_After": 30}, "body": "slow down"}), ("ok", {})])
    out = client.rest("/a")
    assert out == {"ok": True}
    assert fake.sleeps == [30]
    assert fake.requests_made == 2
    assert "Rate limit: waiting 30 seconds" in capsys.readouterr().err


def test_a_secondary_limit_403_backs_off_with_growing_waits(world):
    limited = (403, {"body": "You have exceeded a secondary rate limit."})
    fake = world([limited, limited, ("ok", {})])
    client.rest("/a")
    first, second = client.SECONDARY_FIRST_WAIT, client.SECONDARY_FIRST_WAIT * client.SECONDARY_WAIT_FACTOR
    assert [s for s in fake.sleeps if s >= first] == [first, second]


def test_a_secondary_limit_that_never_clears_gives_up_with_a_plain_error(world):
    limited = (403, {"body": "You have exceeded a secondary rate limit."})
    fake = world([limited] * 20)
    with pytest.raises(SystemExit) as stopped:
        client.rest("/a")
    assert "secondary rate limit" in str(stopped.value)
    assert fake.requests_made == client.SECONDARY_MAX_RETRIES + 1


def test_the_hourly_budget_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_MAX_REQUESTS_PER_HOUR", "600")
    assert client._read_requests_per_hour() == 600
    monkeypatch.delenv("GITHUB_MAX_REQUESTS_PER_HOUR")
    assert client._read_requests_per_hour() == 900
    monkeypatch.setenv("GITHUB_MAX_REQUESTS_PER_HOUR", "lots")
    with pytest.raises(SystemExit):
        client._read_requests_per_hour()
