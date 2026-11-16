"""Values we fill in later (content/settings.yaml): filling in a link or word, the empty look, and the check."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.core import placeholders
from apps.core.tests.support import make_user
from apps.ui.templatetags.trac_ui import bullets, links
from apps.wiki.tests.support import make_page

POLICY_LINK = "See [the Access Control Policy](#todo-access-control-policy) and write to {{tech_risk_email}}."
EMPTY_FILE = """
access_control_policy:
  label: Access Control Policy
  kind: link
  value: ""
tech_risk_email:
  label: Tech Risk email address
  kind: email
  value: ""
"""
SET_FILE = EMPTY_FILE.replace('kind: link\n  value: ""', 'kind: link\n  value: "https://policies.example.com/access"').replace(
    'kind: email\n  value: ""', 'kind: email\n  value: "techrisk@example.com"')


@pytest.fixture
def values_file(tmp_path, monkeypatch):
    """A settings file in a temporary folder that the site reads instead of content/settings.yaml."""
    path = tmp_path / "settings.yaml"
    monkeypatch.setattr(placeholders, "FILE", path)

    def write(text):
        path.write_text(text, encoding="utf-8")
        return path

    return write


# Filling in

def test_a_value_that_is_set_becomes_a_real_link_and_a_mailto_link(values_file):
    values_file(SET_FILE)
    html = str(links(POLICY_LINK))
    assert '<a href="https://policies.example.com/access" rel="noopener noreferrer">the Access Control Policy</a>' in html
    assert '<a href="mailto:techrisk@example.com">techrisk@example.com</a>' in html
    assert "to be added" not in html


def test_an_empty_value_shows_the_words_plainly_with_a_note_and_no_link(values_file):
    values_file(EMPTY_FILE)
    html = str(links(POLICY_LINK))
    assert '<span class="todo-link">the Access Control Policy</span> <small class="todo-note text-body-secondary">(to be added)</small>' in html
    assert "<a " not in html and "#todo-" not in html
    assert '<span class="todo-link">Tech Risk email address</span>' in html


def test_a_link_with_no_entry_shows_the_empty_look_too(values_file):
    values_file(EMPTY_FILE)
    assert "(to be added)" in str(links("[Somewhere](#todo-not-in-the-file)"))


def test_the_same_filling_in_works_in_guidance_bullets(values_file):
    values_file(SET_FILE)
    assert 'href="https://policies.example.com/access"' in str(bullets("- Follow [the policy](#todo-access-control-policy)."))


def test_the_file_is_read_again_when_it_changes(values_file):
    path = values_file(EMPTY_FILE)
    assert "to be added" in str(links(POLICY_LINK))
    path.write_text(SET_FILE, encoding="utf-8")
    assert "to be added" not in str(links(POLICY_LINK))


def test_a_value_is_escaped(values_file):
    values_file('walkthrough_period:\n  label: Dates\n  kind: text\n  value: "<b>Jan</b> & Feb"\n')
    assert "&lt;b&gt;Jan&lt;/b&gt; &amp; Feb" in str(links("Dates: {{walkthrough_period}}"))


def test_guide_html_is_filled_in_but_diagrams_are_left_alone(values_file):
    values_file(SET_FILE)
    html = ('<p><a href="#todo-access-control-policy" rel="noopener noreferrer">the policy</a> or {{tech_risk_email}}</p>'
            '<pre class="mermaid">flowchart LR\nA{{tech_risk_email}} --&gt; B</pre>')
    out = str(placeholders.resolve_html(html))
    assert '<a href="https://policies.example.com/access" rel="noopener noreferrer">the policy</a>' in out
    assert 'mailto:techrisk@example.com' in out
    assert "A{{tech_risk_email}} --&gt; B" in out


@pytest.mark.django_db
def test_a_guide_page_shows_the_empty_look_then_the_real_link(client, values_file):
    tech_risk, approver = make_user("tr1", "tech_risk"), make_user("tr2", "tech_risk")
    page = make_page(tech_risk, approver, title="A policy guide",
                     body='<h2>Access</h2><p>See <a href="#todo-access-control-policy">the Access Control Policy</a>.</p>')
    client.force_login(tech_risk)
    url = reverse("wiki:page", args=[page.slug])
    values_file(EMPTY_FILE)
    body = client.get(url).content.decode()
    assert '<span class="todo-link">the Access Control Policy</span>' in body and "(to be added)" in body
    values_file(SET_FILE)
    body = client.get(url).content.decode()
    assert 'href="https://policies.example.com/access"' in body and "(to be added)" not in body


# The file's own checks

@pytest.mark.parametrize("entry, message", [
    ("a_link:\n  label: A\n  kind: link\n  value: \"not a link\"\n", "should be a web address"),
    ("a_link:\n  label: A\n  kind: link\n  value: \"//evil.example.com\"\n", "should be a web address"),
    ("a_link:\n  label: A\n  kind: link\n  value: \"/\\\\evil.example.com\"\n", "should be a web address"),
    ("a_mail:\n  label: A\n  kind: email\n  value: \"nobody\"\n", "should be an email address"),
    ("a_value:\n  label: A\n  kind: number\n  value: \"\"\n", "needs a kind of link, email, text"),
    ("a_value:\n  kind: text\n  value: \"\"\n", "needs a label"),
    ("A-Bad Key:\n  label: A\n  kind: text\n  value: \"\"\n", "is not a good key"),
    ("a_value: nothing\n", "needs three lines"),
])
def test_the_file_reports_a_mistake_in_plain_words(tmp_path, entry, message):
    path = tmp_path / "settings.yaml"
    path.write_text(entry, encoding="utf-8")
    assert any(message in problem for problem in placeholders.read_values(path).problems)


# The check

def run_check(tmp_path, capsys, content_files, settings_text):
    for name, text in content_files.items():
        path = tmp_path / "content" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    values = tmp_path / "settings.yaml"
    values.write_text(settings_text, encoding="utf-8")
    call_command("check_settings", content_folder=str(tmp_path / "content"), file=str(values))
    return capsys.readouterr().out


def test_empty_values_are_information_not_problems(tmp_path, capsys):
    out = run_check(tmp_path, capsys, {
        "guides/a.md": "Use [the policy](#todo-access-control-policy) and [it again](#todo-access-control-policy).",
        "controls/x.yaml": "text: Write to {{tech_risk_email}}.\n",
    }, EMPTY_FILE)
    assert "2 placeholder(s) waiting for a value: access_control_policy (used 2x), tech_risk_email (used 1x)" in out


def test_a_value_that_is_set_is_not_listed_as_waiting(tmp_path, capsys):
    out = run_check(tmp_path, capsys, {"guides/a.md": "[p](#todo-access-control-policy)"}, SET_FILE)
    assert "Every placeholder has a value." in out


def test_a_placeholder_with_no_entry_is_a_real_problem(tmp_path, capsys):
    with pytest.raises(CommandError, match="a.md: the placeholder 'records_retention_schedule' has no entry in settings.yaml"):
        run_check(tmp_path, capsys, {"guides/a.md": "[x](#todo-records-retention-schedule)"}, EMPTY_FILE)


def test_a_text_value_cannot_be_used_as_a_link(tmp_path, capsys):
    text_file = "walkthrough_period:\n  label: Dates\n  kind: text\n  value: \"\"\n"
    with pytest.raises(CommandError, match="used as a link but its kind is text"):
        run_check(tmp_path, capsys, {"guides/a.md": "[x](#todo-walkthrough-period)"}, text_file)


def test_diagram_text_and_readme_examples_are_not_read_as_placeholders(tmp_path, capsys):
    out = run_check(tmp_path, capsys, {
        "guides/a.md": "```mermaid\nflowchart LR\n  A{{decision}} --> B\n```\n",
        "controls/README.md": "An example: [x](#todo-name)",
    }, EMPTY_FILE)
    assert "waiting for a value" in out


def test_the_shipped_file_covers_every_placeholder_in_the_shipped_content(capsys):
    call_command("check_settings")
    out = capsys.readouterr().out
    assert "The values file is fine" in out
    for key in ("access_control_policy", "records_retention_schedule", "tech_risk_email", "walkthrough_period", "control_due_dates"):
        assert key in out
