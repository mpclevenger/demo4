"""Turns a draw.io SVG file into safe markup for the page, and reads what the diagram links to.

draw.io saves the picture as SVG and keeps the diagram's own XML in the `content` attribute of the top element
(that is what makes the file editable again). The page shows the picture inline so that its links work. Before it
does, `clean_picture` takes out everything that could run code or load something from elsewhere:

- elements that can run code or pull in other pages (script, iframe, object, embed, link, base, animations...);
- every attribute whose name starts with "on" (onclick and friends);
- every link or source that doesn't start with "/", "#", "https://" or "http://" (so javascript: is gone);
- the large `content` attribute, which the browser never needs.

Text labels sit inside `foreignObject` (draw.io draws them as small web pages); they are cleaned the same way.
The picture is built with the standard library only.
"""

import base64
import re
import zlib
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
KEPT_NAMESPACES = (SVG_NAMESPACE, XHTML_NAMESPACE)

DROPPED_ELEMENTS = {
    "script", "iframe", "frame", "frameset", "object", "embed", "applet", "link", "meta", "base", "form", "input",
    "button", "textarea", "select", "audio", "video", "source", "track", "animate", "set", "animatetransform",
    "animatemotion", "handler", "listener",
}
VOID_ELEMENTS = {"br", "hr", "img", "wbr"}
LINK_ATTRIBUTES = {"href", "src", "action", "formaction", "data", "poster"}
ALLOWED_LINK_STARTS = ("/", "#", "https://", "http://")
EMBEDDED_IMAGE_START = re.compile(r"data:image/(png|jpeg|gif|webp);base64,", re.I)
RISKY_STYLE = re.compile(r"@import|expression\(|javascript:|behavior:", re.I)
SITE_LINK = re.compile(r"/rcm/(controls|risks)/([^/?#\s]+)/?")
MIN_READABLE_WIDTH = 900  # pixels: a big diagram never shrinks below this; the box scrolls sideways instead
MAX_XML_BYTES = 5 * 1024 * 1024  # the most a diagram's packed XML may unpack to (a small packed file could unpack to gigabytes)


@dataclass(frozen=True)
class SiteLink:
    kind: str  # "controls" or "risks"
    ident: str  # the TRAC ID, for example AM-04 or R-AM-04


@dataclass
class Picture:
    markup: str = ""
    links: list = field(default_factory=list)  # SiteLink, once each, in the order the picture first names them
    proposed: list = field(default_factory=list)  # labels of dashed bubbles that link nowhere
    problems: list = field(default_factory=list)


def _local(name):
    """(namespace, plain name) of an ElementTree tag or attribute name like {uri}name."""
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return namespace, local
    return "", name


def _safe_link(value, tag):
    """True when a link or source value may stay."""
    value = value.strip()
    if value.startswith("//"):
        return False
    if value.startswith(ALLOWED_LINK_STARTS):
        return True
    return tag in ("image", "img") and bool(EMBEDDED_IMAGE_START.match(value))


def _clean_attributes(element, tag):
    """The element's attributes as (name, value) pairs, without anything unsafe."""
    kept = []
    for raw_name, value in element.attrib.items():
        namespace, name = _local(raw_name)
        if namespace not in ("", XLINK_NAMESPACE, XML_NAMESPACE):
            continue
        if namespace == XML_NAMESPACE:
            name = f"xml:{name}"
        lowered = name.lower()
        is_event_handler = lowered.startswith("on")
        is_editing_copy = lowered == "content" and tag == "svg"  # draw.io's own XML: big, and the browser never needs it
        if is_event_handler or is_editing_copy:
            continue
        if lowered in LINK_ATTRIBUTES and not _safe_link(value, tag):
            continue
        if lowered == "style" and RISKY_STYLE.search(value):
            continue
        kept.append((name, value))
    return kept


def _write(element, out, links):
    """Add the cleaned element, and everything inside it, to `out` (a list of text pieces)."""
    namespace, tag = _local(element.tag)
    if namespace not in KEPT_NAMESPACES or tag.lower() in DROPPED_ELEMENTS:
        return
    lowered = tag.lower()
    attributes = _clean_attributes(element, lowered)
    if lowered == "a":
        attributes = [(n, v) for n, v in attributes if n != "target"] + [("rel", "noopener noreferrer")]
        for name, value in attributes:
            if name == "href" and (found := SITE_LINK.fullmatch(value.strip())):
                link = SiteLink(*found.groups())
                if link not in links:
                    links.append(link)
    if lowered == "style" and RISKY_STYLE.search("".join(element.itertext())):
        return
    out.append("<" + tag + "".join(f' {name}="{escape(value, quote=True)}"' for name, value in attributes) + ">")
    if lowered in VOID_ELEMENTS:
        return
    if element.text:
        out.append(escape(element.text, quote=False))
    for child in element:
        _write(child, out, links)
        if child.tail:
            out.append(escape(child.tail, quote=False))
    out.append(f"</{tag}>")


def _number(text):
    """A whole number of pixels from text like '1200px' or '1200.5', or None."""
    found = re.match(r"\s*(\d+(?:\.\d+)?)", text or "")
    return round(float(found.group(1))) if found else None


def _unpack(text):
    """The XML inside a compressed <diagram> (base64, then deflate, then a web address escape), or None when it unpacks to more than MAX_XML_BYTES."""
    unpacker = zlib.decompressobj(-zlib.MAX_WBITS)
    xml = unpacker.decompress(base64.b64decode(text), MAX_XML_BYTES)
    return None if unpacker.unconsumed_tail else unquote(xml.decode("utf-8"))


def _editable_cells(content, problems):
    """The (cell, the object around it or None) pairs of draw.io's own XML (the `content` attribute).

    A diagram packed bigger than MAX_XML_BYTES is skipped, with a plain-words message added to `problems`.
    """
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return []
    for diagram in root.iter("diagram"):
        if len(diagram) == 0 and (diagram.text or "").strip():  # the XML was saved compressed
            try:
                xml = _unpack(diagram.text.strip())
                if xml is None:
                    problems.append("the picture's editing copy is too big to read, so its Proposed bubbles are not listed. Save it again from draw.io.")
                    continue
                diagram.append(ElementTree.fromstring(xml))
            except (ValueError, zlib.error, ElementTree.ParseError):
                continue
    pairs = []
    for parent in root.iter():
        for child in parent:
            if child.tag == "mxCell":
                pairs.append((child, parent if parent.tag in ("object", "UserObject") else None))
    return pairs


def _plain_label(text):
    """A bubble's label without any web-page markup."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def proposed_labels(content, problems):
    """Labels of the dashed round shapes (ellipses) in the diagram's own XML that have no link: the Proposed controls."""
    labels = []
    for cell, around in _editable_cells(content, problems):
        style = cell.get("style") or ""
        if cell.get("vertex") != "1" or "ellipse" not in style or "dashed=1" not in style:
            continue
        link = cell.get("link") or (around.get("link") if around is not None else "")
        label = _plain_label(cell.get("value") or (around.get("label") if around is not None else ""))
        if not link and label:
            labels.append(label)
    return labels


def clean_picture(text):
    """The safe markup for a draw.io SVG file's text, plus what it links to and its Proposed bubbles."""
    picture = Picture()
    if "<!ENTITY" in text or "<!DOCTYPE" in text:
        picture.problems.append("the picture has a DOCTYPE or ENTITY line, which isn't allowed. Save it again from draw.io.")
        return picture
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        picture.problems.append("the picture isn't a readable SVG file. Save it again from draw.io (File > Export as > SVG).")
        return picture
    if root.tag != f"{{{SVG_NAMESPACE}}}svg":
        picture.problems.append("the file isn't an SVG picture.")
        return picture
    picture.proposed = proposed_labels(root.get("content") or "", picture.problems)
    width, height = _number(root.get("width")), _number(root.get("height"))
    if "viewBox" not in root.attrib and width and height:
        root.set("viewBox", f"0 0 {width} {height}")
    for name in ("width", "height"):
        root.attrib.pop(name, None)
    root.set("class", "diagram-svg")
    own_style = "" if RISKY_STYLE.search(root.get("style") or "") else (root.get("style") or "").strip().rstrip(";")
    minimum = f"min-width: {min(width or MIN_READABLE_WIDTH, MIN_READABLE_WIDTH)}px"
    root.set("style", f"{own_style}; {minimum}" if own_style else minimum)
    out = []
    _write(root, out, picture.links)
    picture.markup = "".join(out)
    return picture


def read_picture(path):
    """The cleaned picture for a diagram file; a plain-words problem when the file can't be read."""
    try:
        return clean_picture(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        picture = Picture()
        picture.problems.append("the picture can't be read.")
        return picture
