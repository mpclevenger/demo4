"""Fixtures for the diagram tests: a diagrams folder of their own, never the shipped one."""

import html
import textwrap

import pytest

from apps.diagrams import diagrams_file, register

DIAGRAM_XML = """<mxfile><diagram id="a" name="A"><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="r" value="R1" style="ellipse;fillColor=#e51400;" vertex="1" parent="1"/>
<mxCell id="c3" value="Proposed: review the logs" style="ellipse;dashed=1;strokeColor=#006EAF;" vertex="1" parent="1"/>
<object id="c9" label="C9" link="/rcm/controls/AM-04/"><mxCell style="ellipse;dashed=1;" vertex="1" parent="1"/></object>
</root></mxGraphModel></diagram></mxfile>"""

SVG = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1700px" height="1000px" content="{content}">
<script>alert(1)</script>
<g onclick="alert(2)"><a xlink:href="/rcm/controls/AM-04/"><ellipse cx="10" cy="10" rx="5" ry="5" onmouseover="x()"/></a></g>
<a xlink:href="/rcm/risks/R-AM-01/"><ellipse cx="30" cy="10" rx="5" ry="5"/></a>
<a xlink:href="javascript:alert(3)"><text x="1" y="1">bad link</text></a>
<a href="https://example.com/doc"><text x="1" y="2">outside</text></a>
<switch><foreignObject width="100" height="20"><div xmlns="http://www.w3.org/1999/xhtml" onclick="x()">Label<br/><script>y()</script>
<a href="javascript:z()">js</a></div></foreignObject><text x="5" y="5">fallback</text></switch>
</svg>"""

CATALOG_PLATFORM = "AWS"


def make_svg(**changes):
    return SVG.replace("{content}", html.escape(DIAGRAM_XML, quote=True))


@pytest.fixture
def diagrams_folder(tmp_path, monkeypatch):
    """A folder for diagrams.yaml and pictures; `write(yaml_text)` writes the list file. A picture `a.drawio.svg` is already there."""
    monkeypatch.setattr(diagrams_file, "FOLDER", tmp_path)
    monkeypatch.setattr(diagrams_file, "FILE", tmp_path / "diagrams.yaml")
    (tmp_path / "a.drawio.svg").write_text(make_svg(), encoding="utf-8")
    controls = tmp_path / "controls"
    controls.mkdir()
    (controls / "t.yaml").write_text(textwrap.dedent("""\
        controls:
          - {id: AM-04, title: Access is reviewed}
        risks:
          - {id: R-AM-01, title: Inappropriate access is granted}
        """), encoding="utf-8")
    monkeypatch.setattr(register, "CONTROLS_FOLDER", controls)

    def write(text="""diagrams:
  - file: a.drawio.svg
    title: A diagram
    intro: How it works.
    kind: footprint
    platforms: [AWS]
    as_of: 2026-11-13
"""):
        (tmp_path / "diagrams.yaml").write_text(text, encoding="utf-8")
        return tmp_path

    return write
