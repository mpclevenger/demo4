"""Checks reading the My system questions file and its plain-word problems."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.pathfinder import questions

LABELS = ["Access", "Service accounts", "Jobs", "Reports", "Vendor"]


def write(tmp_path, text):
    path = tmp_path / "questions.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_shipped_file_has_no_problems_and_names_only_catalog_areas():
    assert questions.check() == []
    found = questions.questions()
    assert 4 <= len(found) <= 6
    known = {label.lower() for label in questions.catalog_labels()}
    assert all(label.lower() in known for q in found for label in q.shows)


def test_an_entry_is_read_with_its_key_reason_and_areas(tmp_path):
    path = write(tmp_path, "questions:\n  - question: Does it run jobs?\n    because: it runs jobs\n    shows: [Jobs, reports]\n")
    found, problems = questions.read(path)
    assert problems == []
    assert found[0].key == "does-it-run-jobs" and found[0].because == "it runs jobs"
    assert found[0].names("Reports") and found[0].names("jobs") and not found[0].names("Access")


def test_because_is_optional(tmp_path):
    found, problems = questions.read(write(tmp_path, "questions:\n  - question: Does it run jobs?\n    shows: [Jobs]\n"))
    assert problems == [] and found[0].because == ""


@pytest.mark.parametrize("text,message", [
    ("questions: nope\n", "expected a list called 'questions'"),
    ("questions:\n  - question: Runs jobs\n    shows: [Jobs]\n", "ending with a question mark"),
    ("questions:\n  - question: Runs jobs?\n    shows: []\n", "'shows' needs at least one risk area"),
    ("questions:\n  - question: Runs jobs?\n    shows: [Jobs]\n    colour: blue\n", "'colour' isn't a known field"),
    ("questions:\n  - question: Runs jobs?\n    shows: [Jobs]\n  - question: Runs jobs?\n    shows: [Jobs]\n", "asked twice"),
    ("questions:\n  - question: Runs jobs?\n   shows: [Jobs]\n", "isn't valid YAML"),
])
def test_mistakes_are_named_in_plain_words(tmp_path, text, message):
    assert any(message in problem for problem in questions.check(write(tmp_path, text), LABELS))


def test_an_unknown_risk_area_is_reported_but_the_question_is_still_read(tmp_path):
    path = write(tmp_path, "questions:\n  - question: Does it run jobs?\n    shows: [Jobz]\n")
    problems = questions.check(path, LABELS)
    assert len(problems) == 1 and "'Jobz' isn't a risk area in catalog.yaml" in problems[0]
    assert len(questions.read(path)[0]) == 1


def test_an_entry_with_a_mistake_is_skipped_and_the_rest_are_kept(tmp_path):
    path = write(tmp_path, "questions:\n  - question: No mark\n    shows: [Jobs]\n  - question: Fine?\n    shows: [Jobs]\n")
    found, problems = questions.read(path)
    assert [q.text for q in found] == ["Fine?"] and len(problems) == 1


def test_check_my_system_reports_problems(tmp_path, monkeypatch, capsys):
    call_command("check_my_system")
    assert "All good: 5 My system question(s)." in capsys.readouterr().out
    monkeypatch.setattr(questions, "QUESTIONS_FILE", write(tmp_path, "questions:\n  - question: Route it?\n    shows: [Jobz]\n"))
    with pytest.raises(CommandError) as error:
        call_command("check_my_system")
    assert "'Jobz' isn't a risk area" in str(error.value) and 'contains "route"' in str(error.value)


@pytest.mark.django_db
def test_check_content_includes_the_my_system_check():
    out = io.StringIO()
    try:
        call_command("check_content", stdout=out)
    except CommandError:
        pass  # other parts need seeded topics; only the My system part matters here
    assert "My system questions (content/my-system)" in out.getvalue()
    assert "All good: 5 My system question(s)." in out.getvalue()
