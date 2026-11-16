"""The starter guide files in content/guides, their loader and `manage.py check_guides`."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.wiki.guide_checks import HELP_LINE, file_wording_problems, guide_problems
from apps.wiki.starter_guides import GUIDES_DIR, GuideFileError, load_guides, parse_guide

pytestmark = pytest.mark.django_db

HEADER = "---\ntitle: A guide\nsection: build\n---\n"
GOOD_BODY = f"An intro.\n\n## First\n\n- One\n- Two\n\n{HELP_LINE}\n"


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# Loader

def test_parse_reads_the_header_and_turns_markdown_into_clean_html(tmp_path):
    path = write(tmp_path, "a-guide.md", "---\ntitle: A guide: with a colon\nsection: best_practice\nplatform: AWS\norder: 3\n---\n"
                 "Intro with **bold** and a [link](/guides/x/).\n\n## Heading\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script>\n")
    guide = parse_guide(path)
    assert (guide.slug, guide.title, guide.section, guide.platform, guide.order) == ("a-guide", "A guide: with a colon", "best_practice", "AWS", 3)
    assert "<strong>bold</strong>" in guide.body and "<h2>Heading</h2>" in guide.body and "<th>A</th>" in guide.body
    assert 'href="/guides/x/"' in guide.body and "<script" not in guide.body


def test_optional_fields_default(tmp_path):
    guide = parse_guide(write(tmp_path, "a-guide.md", HEADER + "Text.\n"))
    assert guide.platform is None and guide.order > 1000


@pytest.mark.parametrize("text, message", [
    ("Just text.\n", "must start with a line of three dashes"),
    ("---\ntitle: A\nsection: build\nText.\n", "no closing line"),
    ("---\nsection: build\n---\nText.\n", "needs a 'title:' line"),
    ("---\ntitle: A\n---\nText.\n", "needs a 'section:' line"),
    ("---\ntitle: A\nsection: nonsense\n---\nText.\n", "unknown section 'nonsense'"),
    ("---\ntitle: A\nsection: build\norder: soon\n---\nText.\n", "'order' must be a whole number"),
    ("---\ntitle: A\nsecton: build\nsection: build\n---\nText.\n", "unknown header 'secton'"),
    ("---\ntitle A\nsection: build\n---\nText.\n", "should look like 'title: Your title'"),
    ("---\ntitle: A\nsection: build\n---\n\n", "no text after the header"),
])
def test_broken_files_raise_an_error_that_names_the_file(tmp_path, text, message):
    path = write(tmp_path, "broken-one.md", text)
    with pytest.raises(GuideFileError, match=f"broken-one.md: .*{message}"):
        parse_guide(path)


def test_file_name_must_be_a_slug(tmp_path):
    with pytest.raises(GuideFileError, match="file name"):
        parse_guide(write(tmp_path, "Bad Name.md", HEADER + "Text.\n"))


def test_load_orders_by_order_then_title(tmp_path):
    write(tmp_path, "b.md", "---\ntitle: B\nsection: build\norder: 2\n---\nText.\n")
    write(tmp_path, "a.md", "---\ntitle: A\nsection: build\norder: 2\n---\nText.\n")
    write(tmp_path, "c.md", "---\ntitle: C\nsection: build\norder: 1\n---\nText.\n")
    write(tmp_path, "d.md", "---\ntitle: D\nsection: build\n---\nText.\n")
    write(tmp_path, "notes.txt", "ignored")
    assert [g.title for g in load_guides(tmp_path)] == ["C", "A", "B", "D"]


# Every shipped file

def guide_files():
    return sorted(GUIDES_DIR.glob("*.md"))


def test_there_are_guide_files():
    assert len(guide_files()) >= 10


@pytest.mark.parametrize("path", guide_files(), ids=lambda p: p.name)
def test_every_guide_file_loads_and_passes_the_checks(path):
    guide = parse_guide(path)
    assert guide.body
    assert guide_problems(guide) == []


def test_titles_and_slugs_are_unique():
    guides = load_guides()
    assert len({g.title for g in guides}) == len(guides) == len(guide_files())


# guide_problems

def make(tmp_path, body, name="a-guide.md"):
    return parse_guide(write(tmp_path, name, HEADER + body))


def test_problems_flags_a_missing_or_repeated_help_line(tmp_path):
    assert any("exactly once" in p and "found 0" in p for p in guide_problems(make(tmp_path, "Text.\n")))
    assert any("found 2" in p for p in guide_problems(make(tmp_path, f"{HELP_LINE}\n\nText.\n\n{HELP_LINE}\n")))
    assert guide_problems(make(tmp_path, GOOD_BODY)) == []


@pytest.mark.parametrize("phrase", ["standard", "reach out", "tell tech risk", "agree it with tech risk", "route",
                                    "through tech risk", "agreed channel"])
def test_problems_flags_each_banned_phrase(tmp_path, phrase):
    problems = guide_problems(make(tmp_path, f"Please {phrase.upper()} soon.\n\n{HELP_LINE}\n"))
    assert problems == [f'The text contains "{phrase}". Reword it.']


def test_a_vendor_product_term_passes_but_the_same_word_elsewhere_fails(tmp_path):
    assert guide_problems(make(tmp_path, f"Clusters use Standard Access Mode.\n\n{HELP_LINE}\n")) == []
    problems = guide_problems(make(tmp_path, f"Clusters use standard access mode, the standard choice.\n\n{HELP_LINE}\n"))
    assert problems == ['The text contains "standard". Reword it.']


def test_file_wording_problems_name_the_file_and_allow_product_terms_across_line_breaks(tmp_path):
    good = write(tmp_path, "good.yaml", "items:\n  - Clusters use standard\n    access mode.\n")
    bad = write(tmp_path, "bad.yaml", "items:\n  - A standard build.\n")
    assert file_wording_problems([good]) == []
    assert len(file_wording_problems([good, bad])) == 1 and file_wording_problems([bad])[0].startswith('bad.yaml: the text contains "standard"')


def test_standard_is_allowed_only_in_the_oversight_levels_guide(tmp_path):
    body = f"The Standard level.\n\n{HELP_LINE}\n"
    assert guide_problems(make(tmp_path, body, "oversight-levels.md")) == []
    assert guide_problems(make(tmp_path, body, "other-guide.md"))


def test_problems_flags_an_unknown_platform_only_when_platforms_are_known(tmp_path):
    guide = parse_guide(write(tmp_path, "a-guide.md", "---\ntitle: A\nsection: build\nplatform: Nope\n---\n" + GOOD_BODY))
    assert guide_problems(guide) == []
    assert guide_problems(guide, {"AWS"}) and "Nope" in guide_problems(guide, {"AWS"})[0]


# manage.py check_guides

def test_check_guides_passes_on_the_shipped_files(capsys):
    call_command("check_guides")
    assert "guide files are fine" in capsys.readouterr().out


def test_check_guides_reports_every_problem_and_fails(tmp_path, capsys):
    write(tmp_path, "good.md", HEADER + GOOD_BODY)
    write(tmp_path, "no-help.md", HEADER + "Text.\n")
    write(tmp_path, "no-header.md", "Text.\n")
    with pytest.raises(CommandError, match="2 of 3 guide files have problems"):
        call_command("check_guides", folder=str(tmp_path))
    out = capsys.readouterr().out
    assert "good.md: OK" in out and "no-help.md" in out and "exactly once" in out
    assert "no-header.md" in out and "must start with a line of three dashes" in out


def test_check_guides_fails_on_an_empty_folder(tmp_path):
    with pytest.raises(CommandError, match="No .md guide files"):
        call_command("check_guides", folder=str(tmp_path))


# in_progress

def test_in_progress_defaults_to_no_and_reads_yes(tmp_path):
    assert parse_guide(write(tmp_path, "a-guide.md", HEADER + "Text.\n")).in_progress is False
    path = write(tmp_path, "b-guide.md", "---\ntitle: B\nsection: build\nin_progress: yes\n---\nText.\n")
    assert parse_guide(path).in_progress is True
    path = write(tmp_path, "c-guide.md", "---\ntitle: C\nsection: build\nin_progress: No\n---\nText.\n")
    assert parse_guide(path).in_progress is False


def test_in_progress_must_be_yes_or_no(tmp_path):
    path = write(tmp_path, "a-guide.md", "---\ntitle: A\nsection: build\nin_progress: soon\n---\nText.\n")
    with pytest.raises(GuideFileError, match="a-guide.md: 'in_progress' must be yes or no, not 'soon'"):
        parse_guide(path)


def test_check_guides_accepts_an_in_progress_guide(tmp_path, capsys):
    write(tmp_path, "a-guide.md", "---\ntitle: A guide\nsection: build\nin_progress: yes\n---\n" + GOOD_BODY)
    call_command("check_guides", folder=str(tmp_path))
    assert "a-guide.md: OK" in capsys.readouterr().out


def test_no_shipped_guide_is_marked_in_progress():
    assert not [guide.title for guide in load_guides() if guide.in_progress]


def test_key_terms_is_a_reference_guide():
    assert {guide.slug: guide.section for guide in load_guides()}["key-terms"] == "best_practice"
