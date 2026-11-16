"""The diagram list file, the picture cleaner, the pages and the check."""

import html

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.diagrams import diagrams_file, svg
from apps.diagrams.management.commands import check_diagrams
from apps.diagrams.tests.conftest import make_svg

pytestmark = pytest.mark.django_db


# --- the cleaner -------------------------------------------------------------------------------------------------

def test_the_cleaner_removes_scripts_handlers_and_unsafe_links():
    picture = svg.clean_picture(make_svg())
    page = picture.markup
    assert "<script" not in page and "alert(" not in page
    assert "onclick" not in page and "onmouseover" not in page
    assert "javascript:" not in page
    assert "content=" not in page


def test_the_cleaner_keeps_site_links_outside_links_and_labels():
    picture = svg.clean_picture(make_svg())
    assert 'href="/rcm/controls/AM-04/"' in picture.markup
    assert 'href="https://example.com/doc"' in picture.markup
    assert "<div>Label<br>" in picture.markup  # the label inside foreignObject is plain HTML, cleaned
    assert [(l.kind, l.ident) for l in picture.links] == [("controls", "AM-04"), ("risks", "R-AM-01")]


def test_the_cleaner_makes_the_picture_scale_but_not_shrink_below_a_readable_width():
    picture = svg.clean_picture(make_svg())
    assert 'viewBox="0 0 1700 1000"' in picture.markup
    assert f"min-width: {svg.MIN_READABLE_WIDTH}px" in picture.markup
    assert 'width="1700' not in picture.markup


def test_the_cleaner_finds_dashed_bubbles_that_link_nowhere():
    picture = svg.clean_picture(make_svg())
    assert picture.proposed == ["Proposed: review the logs"]  # C9 is dashed but linked, so it isn't Proposed


def test_the_cleaner_refuses_what_is_not_an_svg_or_has_entities():
    assert svg.clean_picture("not xml").problems
    assert svg.clean_picture('<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>').problems
    assert svg.clean_picture("<html/>").problems


def test_a_link_that_starts_with_two_slashes_is_removed():
    text = '<svg xmlns="http://www.w3.org/2000/svg"><a href="//evil.example/x"><text>t</text></a></svg>'
    assert "evil" not in svg.clean_picture(text).markup


def test_style_text_is_always_escaped_so_a_cdata_payload_cannot_become_markup():
    text = ('<svg xmlns="http://www.w3.org/2000/svg"><style><![CDATA[ <img src=x onerror=alert(1)> ]]></style>'
            "<style><![CDATA[ </style><script>alert(2)</script> ]]></style></svg>")
    markup = svg.clean_picture(text).markup
    assert "<img" not in markup and "<script" not in markup
    assert "&lt;img src=x onerror=alert(1)&gt;" in markup


def test_a_packed_diagram_still_gives_its_proposed_bubbles():
    import base64
    import urllib.parse
    import zlib

    xml = urllib.parse.quote('<mxGraphModel><root><mxCell id="c" value="Packed bubble" style="ellipse;dashed=1;" vertex="1"/></root></mxGraphModel>')
    packer = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    packed = base64.b64encode(packer.compress(xml.encode()) + packer.flush()).decode()
    content = f'<mxfile><diagram id="a">{packed}</diagram></mxfile>'
    text = f'<svg xmlns="http://www.w3.org/2000/svg" content="{html.escape(content, quote=True)}"><text>t</text></svg>'
    assert svg.clean_picture(text).proposed == ["Packed bubble"]


def test_a_packed_diagram_that_unpacks_too_big_is_skipped_with_a_problem():
    import base64
    import zlib

    packer = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    packed = packer.compress(b"<mxGraphModel>" + b" " * (svg.MAX_XML_BYTES + 10) + b"</mxGraphModel>") + packer.flush()
    content = f'<mxfile><diagram id="a">{base64.b64encode(packed).decode()}</diagram></mxfile>'
    text = f'<svg xmlns="http://www.w3.org/2000/svg" content="{html.escape(content, quote=True)}"><text>t</text></svg>'
    picture = svg.clean_picture(text)
    assert picture.proposed == []
    assert any("too big" in problem for problem in picture.problems)


# --- the list file -----------------------------------------------------------------------------------------------

def test_no_file_means_no_diagrams(diagrams_folder):
    found = diagrams_file.read_diagrams()
    assert found.items == [] and found.problems == []


def test_a_good_entry_is_read(diagrams_folder):
    diagrams_folder()
    found = diagrams_file.read_diagrams()
    assert found.problems == []
    only = found.items[0]
    assert (only.name, only.kind, only.platforms, str(only.as_of)) == ("a", "footprint", ("AWS",), "2026-11-13")
    assert found.for_platform("AWS") == [only] and found.for_platform("Azure") == []


def test_every_mistake_is_reported_in_plain_words(diagrams_folder):
    diagrams_folder("""diagrams:
  - {file: missing.drawio.svg, title: T, intro: I, kind: common}
  - {file: a.drawio.svg, title: T, intro: I, kind: weird}
  - {file: a.drawio.svg, intro: I, kind: common, as_of: 2026-02-30, colour: red}
  - {file: ../x.drawio.svg, title: T, intro: I, kind: common}
""")
    text = "\n".join(diagrams_file.read_diagrams().problems)
    assert "'missing.drawio.svg' isn't in content/diagrams" in text
    assert "'kind' should be common or footprint, not 'weird'" in text
    assert "needs a 'title'" in text
    assert "'as_of' should be a real day" in text
    assert "'colour' isn't a known line" in text
    assert "should use lowercase letters" in text


def test_a_file_listed_twice_is_reported(diagrams_folder):
    entry = "  - {file: a.drawio.svg, title: T, intro: I, kind: common}\n"
    diagrams_folder("diagrams:\n" + entry + entry)
    assert "listed twice" in "\n".join(diagrams_file.read_diagrams().problems)


def test_a_broken_yaml_file_is_reported(diagrams_folder):
    diagrams_folder("diagrams: [unclosed\n")
    assert "isn't valid YAML" in diagrams_file.read_diagrams().problems[0]


# --- the pages ---------------------------------------------------------------------------------------------------

def test_the_list_says_when_there_are_no_diagrams(client, diagrams_folder):
    page = client.get("/diagrams/").content.decode()
    assert "There are no diagrams yet." in page


def test_the_list_groups_by_kind(client, diagrams_folder):
    diagrams_folder()
    page = client.get(reverse("diagrams:index")).content.decode()
    assert "Our footprint" in page and "A diagram" in page and "How it works." in page
    assert 'id="diagrams-common"' not in page  # no common diagram, so no empty section
    assert "Checked November 13, 2026" in page


def test_a_diagram_page_shows_the_clean_picture_key_and_links(client, diagrams_folder):
    diagrams_folder()
    page = client.get("/diagrams/a/").content.decode()
    assert '<svg' in page and "alert(" not in page and "javascript:" not in page
    assert "Download to edit in draw.io" in page and "/diagrams/a/download/" in page
    assert "A red bubble is what could go wrong" in page and "A dashed line is unconfirmed" in page
    assert "R-AM-01</a>: Inappropriate access is granted" in page
    assert "AM-04</a>: Access is reviewed" in page
    assert "Proposed: review the logs" in page


def test_an_unknown_diagram_is_not_found(client, diagrams_folder):
    diagrams_folder()
    assert client.get("/diagrams/nope/").status_code == 404
    assert client.get("/diagrams/nope/download/").status_code == 404


def test_the_download_serves_the_original_file(client, diagrams_folder):
    diagrams_folder()
    response = client.get("/diagrams/a/download/")
    body = b"".join(response.streaming_content).decode()
    assert response.status_code == 200 and 'filename="a.drawio.svg"' in response["Content-Disposition"]
    assert "alert(1)" in body  # the original file is untouched


def test_the_library_tabs_link_to_diagrams(client, diagrams_folder):
    assert 'href="/diagrams/"' in client.get("/topics/").content.decode()


def test_a_platform_names_its_diagrams(diagrams_folder):
    from apps.diagrams.diagrams_file import diagrams_for_platform

    diagrams_folder()
    assert diagrams_for_platform("AWS") == [("A diagram", "/diagrams/a/")]
    assert diagrams_for_platform("Azure") == []


# --- the check ---------------------------------------------------------------------------------------------------

@pytest.fixture
def known_platforms(monkeypatch):
    monkeypatch.setattr(check_diagrams, "platform_names", lambda: {"AWS"})


def test_the_check_passes_for_a_good_file(diagrams_folder, known_platforms):
    diagrams_folder()
    call_command("check_diagrams")


def test_the_check_passes_with_no_file(diagrams_folder, known_platforms):
    call_command("check_diagrams")


def test_the_check_names_an_unknown_platform_and_unknown_ids(diagrams_folder, known_platforms, tmp_path):
    diagrams_folder("""diagrams:
  - {file: a.drawio.svg, title: T, intro: I, kind: common, platforms: [AWS, Nope]}
""")
    (tmp_path / "controls" / "t.yaml").write_text("controls:\n  - {id: XX-01, title: Other}\nrisks: []\n", encoding="utf-8")
    with pytest.raises(CommandError) as error:
        call_command("check_diagrams")
    text = str(error.value)
    assert "the platform 'Nope' isn't in content/platforms/catalog.yaml" in text
    assert "links to the control 'AM-04'" in text and "links to the risk 'R-AM-01'" in text
