"""Turn 1.5: the HTML projection and the node-to-span map (``htmltext.py``).

The projection is the concatenation of the part's text nodes, verbatim, with the
``style``/``script``/``head`` subtrees and comments dropped -- nothing else inserted. That
is what the frozen ``body.html_spans`` labels' spans imply, and it is stamped with
``HTMLTEXT_VERSION``. It is the same coordinate space (un-normalised code points) the
``>``-depth spans will use.

**FINDINGS (Turn 1.5).** Five frozen ``body.html_spans`` rows disagree with the bytes and
with the projection rule the four labelled fixtures otherwise state. The label is frozen and
never edited; the bytes are the judge; both values are pinned here:

* ``html_style_and_script`` rows 0 (``html``) and 4 (``body``) type length 12 where the tree
  gives 10: they count the trailing ``\\r\\n`` (offsets 10-12, a text node **after**
  ``</html>``, outside the element's subtree) as inside the element.
* ``html_href_img_remote_and_cid`` row 1 (``a``) types length 6 where the bytes give 3
  (``"Ben"``), and rows 2/3 (``img``) type offsets 6/8 where the bytes give 8/10 -- the
  ``\\r\\n`` between ``</p>`` and the first ``<img>`` was not counted.

Every failure names the fixture, the fact and the reason.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from emailextract import htmltext
from emailextract.container import EmlContainer, memory_bytes
from emailextract.text import analyse_parts
from emailextract.versions import HTMLTEXT_VERSION, _htmltext_version_key
from emailextract.walk import walk

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "fixtures" / "generated"

#: fixture -> the locator of its labelled ``text/html`` part.
LABELLED = {
    "content_location_in_related": "1.1",
    "html_data_uri_and_tracking_pixel": "1",
    "html_href_img_remote_and_cid": "1",
    "html_style_and_script": "1",
}

#: The five known label/byte disagreements: ``(fixture, ordinal) -> (label row, byte row)``.
FINDING_ROWS = {
    ("html_style_and_script", 0): (["1", 0, "html", 0, 12], ["1", 0, "html", 0, 10]),
    ("html_style_and_script", 4): (["1", 4, "body", 0, 12], ["1", 4, "body", 0, 10]),
    ("html_href_img_remote_and_cid", 1): (["1", 1, "a", 3, 6], ["1", 1, "a", 3, 3]),
    ("html_href_img_remote_and_cid", 2): (["1", 2, "img", 6, 0], ["1", 2, "img", 8, 0]),
    ("html_href_img_remote_and_cid", 3): (["1", 3, "img", 8, 0], ["1", 3, "img", 10, 0]),
}


def _parts(name: str):
    raw = (GENERATED / f"{name}.eml").read_bytes()
    result = walk(EmlContainer(memory_bytes(raw)))
    return {record.path: record.text for record in analyse_parts(raw, result)}


def _project(name: str, locator: str) -> htmltext.HtmlProjection:
    return htmltext.project(_parts(name)[locator], max_depth=64, max_elements=1000)


def _label(name: str) -> list[list[object]]:
    sidecar = json.loads((GENERATED / f"{name}.expected.json").read_text(encoding="utf-8"))
    return sidecar["facts"]["body.html_spans"]["value"]


def test_the_projection_is_stamped_with_htmltext_version() -> None:
    """The projection carries the version of its four recorded inputs, never a bare string."""
    projection = htmltext.project("<p>Hello</p>", max_depth=8, max_elements=8)
    assert projection.version == HTMLTEXT_VERSION, projection.version
    assert projection.version.startswith("1+htmlparser+"), projection.version
    assert projection.text == "Hello", projection.text


def test_an_img_and_an_href_projection_match_the_tree_spans() -> None:
    """An ``<img>`` and an ``<a href>`` project to what the frozen labels' spans imply."""
    body = (
        '<p>Hi <a href="mailto:ben@example.test">Ben</a></p>\r\n'
        '<img src="http://example.test/pic.png" alt="pic">\r\n'
        '<img src="cid:logo@example.test" alt="logo">\r\n'
    )
    projection = htmltext.project(body, max_depth=16, max_elements=64)
    # the projection is the text nodes verbatim: an <img> adds nothing (no alt text), the
    # CRLFs between the tags are text nodes and count.
    assert projection.text == "Hi Ben\r\n\r\n\r\n", repr(projection.text)
    by_tag = {tag: (offset, length) for _, tag, offset, length in projection.spans}
    assert by_tag["a"] == (3, 3), by_tag  # "Ben", not the whole <p>
    assert [
        (offset, length) for _, tag, offset, length in projection.spans if tag == "img"
    ] == [(8, 0), (10, 0)], by_tag
    # the fixture bytes give exactly the same arithmetic
    from_fixture = _project("html_href_img_remote_and_cid", "1")
    assert from_fixture.text == projection.text, repr(from_fixture.text)
    assert from_fixture.spans == projection.spans, from_fixture.spans
    # the frozen label disagrees on three of these rows (FINDING above); both values pinned
    rows = _label("html_href_img_remote_and_cid")
    assert rows[1] == FINDING_ROWS[("html_href_img_remote_and_cid", 1)][0]
    assert from_fixture.html_spans_rows("1")[1] == FINDING_ROWS[("html_href_img_remote_and_cid", 1)][1]


def test_the_projection_rule_id_is_the_htmltext_versions_projection_input() -> None:
    """``HTMLTEXT_VERSION``'s ``projection`` input is this module's stated rule ids, and a
    move of any one of the three inputs moves the key."""
    rule_id = htmltext.PROJECTION_RULE_ID
    assert rule_id == "+".join(
        (
            htmltext.PROJECTION_WHITESPACE_RULE,
            htmltext.PROJECTION_DROPPED_RULE,
            htmltext.PROJECTION_BLOCK_RULE,
        )
    )
    base = dict(
        candidate="htmlparser",
        cpython=".".join(str(part) for part in __import__("sys").version_info[:2]),
        projection=rule_id,
        unclosed="recorded-not-closed",
    )
    assert _htmltext_version_key(**base) == HTMLTEXT_VERSION
    for move in (
        {"projection": "collapse-whitespace+" + htmltext.PROJECTION_DROPPED_RULE},
        {"projection": htmltext.PROJECTION_WHITESPACE_RULE + "+drop=style,script"},
        {"projection": htmltext.PROJECTION_WHITESPACE_RULE + "+block=newlines"},
    ):
        assert _htmltext_version_key(**{**base, **move}) != HTMLTEXT_VERSION, move


def test_the_node_to_span_map_nests_and_siblings_are_ordered() -> None:
    """Every element's span nests inside its parent's and siblings are ordered, over real HTML."""
    for name, locator in LABELLED.items():
        projection = _project(name, locator)
        by_ordinal = {element.ordinal: element for element in projection.tree.elements}
        for element in projection.tree.elements:
            assert 0 <= element.projected_offset <= len(projection.text), (name, element)
            assert element.projected_end <= len(projection.text), (name, element)
            if element.parent_ordinal is None:
                continue
            parent = by_ordinal[element.parent_ordinal]
            assert parent.projected_offset <= element.projected_offset, (name, element)
            assert element.projected_end <= parent.projected_end, (name, element)
        ordered = [
            element.projected_offset
            for element in projection.tree.elements
            if element.projected_length == 0
        ]
        assert ordered == sorted(ordered), (name, ordered)


def test_the_committed_html_spans_labels_agree_except_the_reported_findings() -> None:
    """The projection rule reproduces the labels row for row, bar the five pinned findings."""
    disagreements: list[tuple[str, list, list]] = []
    for name, locator in LABELLED.items():
        projection = _project(name, locator)
        rows = _label(name)
        mine = projection.html_spans_rows(locator)
        assert len(rows) == len(mine), (name, len(rows), len(mine))
        for index, (label_row, byte_row) in enumerate(zip(rows, mine)):
            if label_row == byte_row:
                continue
            disagreements.append((name, label_row, byte_row))
            assert FINDING_ROWS[(name, index)] == (label_row, byte_row), (
                f"{name} body.html_spans row {index}: the label and the bytes disagree in a "
                f"way this turn did not report: label={label_row} bytes={byte_row}"
            )
    assert {(name, row[1]) for name, row, _ in disagreements} == set(FINDING_ROWS), disagreements


def test_the_projection_never_touches_the_network_or_the_filesystem(monkeypatch) -> None:
    """The HTML path does no I/O: no socket, no file open, no fetch, ever (D10)."""

    def _refuse(*args, **kwargs):  # pragma: no cover - reached only on a defect
        raise AssertionError("the HTML path touched the outside world")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr("builtins.open", _refuse)
    bodies = {name: _parts(name)[locator] for name, locator in LABELLED.items()}
    for body in bodies.values():
        projection = htmltext.project(body, max_depth=64, max_elements=1000)
        assert isinstance(projection.text, str)


def test_a_remote_or_data_uri_alt_is_not_projected() -> None:
    """A tracking pixel and a ``data:`` URI project nothing; no alt text, no fetch, no decode."""
    body = (
        '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=" '
        'width="1" height="1">\r\n<img src="http://example.test/pixel.gif" width="1" height="1">\r\n'
    )
    projection = htmltext.project(body, max_depth=8, max_elements=8)
    assert projection.text == "\r\n\r\n", repr(projection.text)
    assert projection.spans == ((0, "img", 0, 0), (1, "img", 2, 0)), projection.spans


def test_a_project_cap_is_a_recorded_state_not_an_exception() -> None:
    """A cap hit over the projection is recorded on the tree, and the projection still returns."""
    projection = htmltext.project("<div>" * 1000, max_depth=4, max_elements=1000)
    assert projection.tree.truncation is not None
    assert projection.tree.truncation.reason_id == "depth_cap"
    assert isinstance(projection.text, str)


@pytest.mark.parametrize("body", ["", "<", "<p", "&#x41;<!-- x --><style>s</style>tail"])
def test_odd_inputs_project_without_raising(body: str) -> None:
    """The projection never raises on odd input: references decode once, comments and style drop."""
    projection = htmltext.project(body, max_depth=8, max_elements=8)
    assert isinstance(projection.text, str)
