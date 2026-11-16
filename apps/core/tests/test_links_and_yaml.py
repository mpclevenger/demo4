"""The one link rule (apps/core/links.py) and the one YAML reader (apps/core/yaml_files.py)."""

from datetime import date

import pytest
from django.core.management.base import CommandError

from apps.core.links import is_allowed_link, is_trac_page, is_web_address
from apps.core.yaml_files import load_yaml, read_day
from apps.platforms.management.commands import commands_to_confirm


@pytest.mark.parametrize("url, allowed", [
    ("/guides/", True),
    ("https://example.com/a", True),
    ("http://example.com/a", False),
    ("//evil.example.com", False),
    ("/\\evil.example.com", False),
    ("javascript:alert(1)", False),
    ("guides/", False),
])
def test_one_rule_says_which_links_content_may_carry(url, allowed):
    assert is_allowed_link(url) is allowed


def test_http_is_allowed_only_where_asked_for():
    assert is_allowed_link("http://example.com", allow_http=True)
    assert is_web_address("http://example.com", allow_http=True) and not is_web_address("http://example.com")
    assert is_trac_page("/guides/") and not is_trac_page("https://example.com")


def test_load_yaml_returns_the_data_or_a_plain_problem(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text("a: 1\n", encoding="utf-8")
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [unclosed\n", encoding="utf-8")
    assert load_yaml(good) == ({"a": 1}, None)
    data, problem = load_yaml(broken)
    assert data is None and problem.startswith("broken.yaml: the file isn't valid YAML near line")
    assert load_yaml(tmp_path / "missing.yaml") == (None, "missing.yaml: the file can't be read.")


def test_load_yaml_can_leave_days_and_yes_no_words_as_text(tmp_path):
    path = tmp_path / "days.yaml"
    path.write_text("day: 2027-02-30\non: second thursday\n", encoding="utf-8")
    assert load_yaml(path, keep_as_text=("timestamp", "bool"))[0] == {"day": "2027-02-30", "on": "second thursday"}


def test_read_day_gives_a_date_only_for_a_real_day():
    assert read_day("2027-03-31") == date(2027, 3, 31)
    assert read_day(date(2027, 3, 31)) == date(2027, 3, 31)
    assert read_day("2027-02-30") is None and read_day("20270331") is None and read_day(5) is None


def test_commands_to_confirm_gives_a_plain_error_for_a_missing_line(tmp_path):
    (tmp_path / "t.yaml").write_text(
        "controls:\n  - id: AM-01\n    title: T\n    steps:\n      - do: Step\n        commands: [{platform: AWS}]\n", encoding="utf-8")
    with pytest.raises(CommandError, match=r"t.yaml: control AM-01, step 1: the command needs a 'code' line"):
        commands_to_confirm.commands_by_platform(tmp_path)
