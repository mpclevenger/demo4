"""The front page asks what the visitor is working on and offers two doors and shortcuts; the Library has its own address."""

import shutil

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils.html import escape

from apps.core import home_files
from apps.core.links import reverse_if_exists
from apps.wiki.starter_guides import GUIDES_DIR

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seeded():
    call_command("seed_topics")
    call_command("seed_platforms")


@pytest.fixture
def home_copy(tmp_path, monkeypatch):
    """A copy of the shipped front page files that a test can change."""
    folder = tmp_path / "home"
    shutil.copytree(home_files.FOLDER, folder)
    monkeypatch.setattr(home_files, "FOLDER", folder)
    return folder


def test_front_page_asks_the_question_and_has_two_doors_and_shortcuts(client):
    html = client.get("/").content.decode()
    assert "What are you working on?" in html
    assert html.count('class="home-door"') == 2
    doors = home_files.doors()
    assert escape(doors.build_title) in html and escape(doors.run_title) in html
    assert html.count('class="start-list"') == 1
    for shortcut in home_files.shortcuts().items:
        assert f'<a href="{shortcut.url}">{escape(shortcut.title)}</a>' in html


def test_door_two_is_a_search_box_that_submits_to_site_search(client):
    html = client.get("/").content.decode()
    assert f'method="get" action="{reverse("core:search")}"' in html
    assert 'name="q" placeholder="AM-03 or access review"' in html


def test_door_one_goes_to_my_system_when_it_exists_and_to_the_library_otherwise(client):
    target = reverse_if_exists("pathfinder:index") or reverse("core:library")
    html = client.get("/").content.decode()
    assert f'<a class="btn btn-primary" href="{target}">Start with my system</a>' in html


def test_front_page_has_no_tool_cards_and_the_tool_address_is_gone(client):
    html = client.get("/").content.decode()
    assert "home-tool" not in html and "Under construction" not in html and "Coming soon" not in html
    assert client.get("/tools/trust/").status_code == 404


def test_the_library_no_longer_has_the_start_box(client):
    html = client.get("/library/").content.decode()
    assert "Start from what you're working on" not in html and "start-list" not in html


def test_library_has_its_own_address_and_the_old_one_redirects(client):
    assert reverse("core:library") == "/library/"
    response = client.get(reverse("platforms:index"))
    assert response.status_code == 302 and response["Location"] == "/library/"
    html = client.get("/library/").content.decode()
    assert '<a class="trac-wordmark" href="/">' in html
    assert '<a href="/library/" aria-current="page">Controls</a>' in html


def test_home_marks_start_in_the_menu(client):
    assert '<a href="/" aria-current="page">Start</a>' in client.get("/").content.decode()


def test_the_wording_comes_from_the_home_files(client, home_copy):
    doors = home_copy / "doors.md"
    doors.write_text(doors.read_text().replace("run_placeholder: AM-03 or access review", "run_placeholder: ZZ-99 or a topic"))
    (home_copy / "index.md").write_text("---\ntitle: Where to?\n---\nA different line.\n")
    html = client.get("/").content.decode()
    assert "Where to?" in html and "A different line." in html and 'placeholder="ZZ-99 or a topic"' in html


def test_the_shipped_home_files_are_valid():
    assert home_files.problems() == []


def test_every_shipped_shortcut_goes_to_a_guide_file_or_the_library():
    for shortcut in home_files.shortcuts().items:
        if shortcut.url.startswith("/guides/"):
            slug = shortcut.url.strip("/").split("/")[1]
            assert (GUIDES_DIR / f"{slug}.md").exists(), shortcut.url
        else:
            assert shortcut.url == reverse("core:library")


def test_home_reader_without_tech_risk_role_can_open_it(sso):
    from apps.core.tests.support import As

    assert As("reader", "ro").get("/").status_code == 200


def write_files(folder, shortcuts="A | B | /library/\n", doors=None):
    doors = doors if doors is not None else (home_files.FOLDER / "doors.md").read_text()
    (folder / "index.md").write_text("---\ntitle: Tech Risk\n---\nHello.\n")
    (folder / "doors.md").write_text(doors)
    (folder / "shortcuts.md").write_text(f"---\ntitle: Shortcuts\n---\n{shortcuts}")


def test_a_bad_shortcut_link_is_explained(tmp_path):
    write_files(tmp_path, "A | B | ftp://x\n")
    assert "must be a TRAC page" in home_files.problems(tmp_path)[0]


def test_a_shortcut_line_missing_a_part_is_explained(tmp_path):
    write_files(tmp_path, "Only a title | /library/\n")
    assert "should look like 'Title | One line | /link/'" in home_files.problems(tmp_path)[0]


def test_shortcut_comments_and_blank_lines_are_ignored(tmp_path):
    write_files(tmp_path, "# a note\n\nA | B | /library/\n")
    assert [s.title for s in home_files.shortcuts(tmp_path).items] == ["A"]


def test_an_empty_shortcut_list_is_explained(tmp_path):
    write_files(tmp_path, "# nothing yet\n")
    assert "add at least one shortcut" in home_files.problems(tmp_path)[0]


def test_a_door_line_that_is_missing_is_explained(tmp_path):
    doors = "\n".join(line for line in (home_files.FOLDER / "doors.md").read_text().splitlines() if not line.startswith("run_line"))
    write_files(tmp_path, doors=doors + "\n")
    assert "needs a 'run_line:' line" in home_files.problems(tmp_path)[0]


def test_an_unknown_door_line_is_explained(tmp_path):
    write_files(tmp_path, doors="---\nbuild_titel: x\n---\n")
    assert "isn't a known header line" in home_files.problems(tmp_path)[0]


def test_a_missing_file_is_reported_not_a_crash(tmp_path):
    assert home_files.problems(tmp_path)


def test_check_home_reports_all_good(capsys):
    call_command("check_home")
    assert "All good" in capsys.readouterr().out
