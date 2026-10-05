"""Turn 1.5: the own stack-based HTML element tree (``htmltree.py``, decision 1).

The tree is candidate A: the stdlib ``html.parser.HTMLParser`` plus an own stack, with the
**named unclosed-container rule** (Turn 1.0d): an unclosed quote container is **recorded,
never closed**, and the part records the gap ``body.html_quote_rule_gap``. Caps are caller
parameters with no defaults and a cap hit is a **recorded truncated state**, never an
exception and never unbounded recursion.

Every failure names the input, the fact and the reason.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from emailextract import htmltree
from emailextract import selection as selection_stage
from emailextract.container import EmlContainer, memory_bytes
from emailextract.walk import walk

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "fixtures" / "generated"

DROP = frozenset({"style", "script", "head"})
IDENTITY = str  # the caller's text policy: verbatim


def _tree(text: str, *, max_depth: int = 64, max_elements: int = 1000):
    return htmltree.build_tree(
        text,
        max_depth=max_depth,
        max_elements=max_elements,
        drop_subtrees=DROP,
        text_filter=IDENTITY,
    )


def _spans(tree):
    return [(element.tag, element.projected_offset, element.projected_length) for element in tree.elements]


def test_the_tree_records_a_projected_span_per_element() -> None:
    """Every element carries tag, attributes, ordinal, parent ordinal and its span."""
    text = '<p>Hi <a href="mailto:ben@example.test">Ben</a></p>'
    tree = _tree(text)
    assert _spans(tree) == [("p", 0, 6), ("a", 3, 3)], _spans(tree)
    assert tree.projection == "Hi Ben", tree.projection
    p, a = tree.elements
    assert (p.ordinal, p.parent_ordinal) == (0, None)
    assert (a.ordinal, a.parent_ordinal) == (1, 0)
    assert a.attributes == (("href", "mailto:ben@example.test"),), a.attributes
    # a child lies inside its parent, and siblings are ordered and non-overlapping
    assert p.projected_offset <= a.projected_offset
    assert a.projected_end <= p.projected_end
    # every span is inside the projection, and a void element keeps a zero-length span
    for element in tree.elements:
        assert 0 <= element.projected_offset
        assert element.projected_end <= len(tree.projection), element
    void = _tree('<img src="http://example.test/pic.png" alt="pic"><br>')
    assert _spans(void) == [("img", 0, 0), ("br", 0, 0)], _spans(void)
    assert void.projection == "", void.projection


def test_an_unclosed_container_is_recorded_not_closed() -> None:
    """The named unclosed-container rule: recorded, never closed, never silently swallowed."""
    text = "<blockquote>Earlier message text.<p>New reply after the unclosed container.</p>"
    tree = _tree(text)
    assert tree.gaps == (htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP,), tree.gaps
    assert tree.unclosed_ordinals == (0,), tree.unclosed_ordinals
    blockquote = tree.elements[0]
    assert blockquote.unclosed is True
    assert blockquote.quote_container is True
    # the container stays open to the end: it covers every following text node
    assert (blockquote.projected_offset, blockquote.projected_length) == (0, len(tree.projection))
    assert tree.projection == "Earlier message text.New reply after the unclosed container."
    # a closed container records nothing
    closed = _tree("<blockquote>quoted</blockquote>reply")
    assert closed.gaps == () and closed.unclosed_ordinals == ()
    # an unclosed element that is NOT a quote container is recorded but emits no gap
    other = _tree("<b>bold and never closed")
    assert other.gaps == () and other.unclosed_ordinals == (0,)


def test_style_and_script_are_dropped_from_the_projection() -> None:
    """A dropped subtree's text never reaches the projection; its elements are still recorded."""
    text = (
        "<html><head><style>p { color: red; }</style>"
        "<script>var x = 1;</script></head><body><p>Hello Ben.</p></body></html>"
    )
    tree = _tree(text)
    assert tree.projection == "Hello Ben.", tree.projection
    assert _spans(tree) == [
        ("html", 0, 10),
        ("head", 0, 0),
        ("style", 0, 0),
        ("script", 0, 0),
        ("body", 0, 10),
        ("p", 0, 10),
    ], _spans(tree)
    # comments are dropped too, and the elements around them keep their positions
    commented = _tree("<p>a<!-- hidden -->b</p>")
    assert commented.projection == "ab", commented.projection


def test_the_tree_is_bounded_and_a_cap_hit_is_a_recorded_state() -> None:
    """A depth or element-count cap is a recorded truncated state, never an exception."""
    bomb = "<div>" * 100_000
    tree = _tree(bomb, max_depth=8)
    assert tree.truncation is not None
    assert tree.truncation.reason_id == htmltree.REASON_DEPTH_CAP, tree.truncation
    assert tree.truncation.limit == 8
    assert len(tree.elements) == 8, len(tree.elements)
    wide = "<p>x</p>" * 10
    capped = _tree(wide, max_elements=3)
    assert capped.truncation is not None
    assert capped.truncation.reason_id == htmltree.REASON_ELEMENT_COUNT_CAP, capped.truncation
    assert capped.truncation.limit == 3
    # under the caps, nothing is truncated
    assert _tree(wide, max_elements=10).truncation is None


def test_a_stray_end_tag_a_mis_nesting_and_a_duplicate_attribute_are_recorded() -> None:
    """Recording, never repair by reordering: stray ends, crossed elements, duplicate names."""
    stray = _tree("</div><p>text</p>")
    assert stray.stray_end_tags == ("div",), stray.stray_end_tags
    crossed = _tree("<p><b>bold <i>and italic</b> still italic</i> tail</p>")
    assert crossed.misnested_closures == (2,), crossed.misnested_closures
    assert crossed.stray_end_tags == ("i",), crossed.stray_end_tags
    assert [element.tag for element in crossed.elements] == ["p", "b", "i"]
    duplicate = _tree('<div id="first" id="second">x</div>')
    assert duplicate.elements[0].attributes == (("id", "first"),), duplicate.elements[0].attributes
    assert duplicate.duplicate_attributes == ((0, "id"),), duplicate.duplicate_attributes


def test_the_implied_end_table_closes_the_open_element() -> None:
    """The closed implied-end set (the HTML optional-end-tag list) closes what a start implies."""
    for text, tags in (
        ("<p>one<p>two", ["p", "p"]),
        ("<ul><li>a<li>b</ul>", ["ul", "li", "li"]),
        ("<p>para<div>block</div>", ["p", "div"]),
        ("<table><tr><td>a<td>b</table>", ["table", "tr", "td", "td"]),
    ):
        tree = _tree(text)
        assert [element.tag for element in tree.elements] == tags, (text, _spans(tree))
        # the implied end really closed the earlier element: it is not the unclosed one at EOF
        assert 0 not in tree.unclosed_ordinals, (text, tree.unclosed_ordinals)
    # "<p>one<p>two" leaves only the *second* p open to EOF; "</ul>" closes everything above it
    assert _tree("<p>one<p>two").unclosed_ordinals == (1,)
    assert _tree("<ul><li>a<li>b</ul>").unclosed_ordinals == ()
    # the implied-end tags really are the closed set the prompt names
    assert set(htmltree.IMPLIED_END) == {
        "p",
        "li",
        "dt",
        "dd",
        "tr",
        "td",
        "th",
        "thead",
        "tbody",
        "tfoot",
        "option",
        "optgroup",
    }


def test_the_tree_never_raises_over_a_seeded_mutation_set() -> None:
    """A small seeded sweep: no exception, spans nest, every span stays in range."""
    bases = [
        "<blockquote>quoted<p>new</p></blockquote>",
        '<div class="gmail_quote">quoted</div>',
        "<html><head><title>t</title></head><body><table><tr><td>c</td></tr></table></body></html>",
        '<p>Hi <a href="mailto:ben@example.test">Ben</a></p>',
    ]
    injections = ["<div>", "<blockquote>", "<p>", "<b>", "<!--", "<script>", '"', "<", "&amp;", "\\x00"]
    rng = random.Random(20250315)
    for base in bases:
        for _ in range(60):
            text = base
            for _ in range(rng.randint(1, 4)):
                kind = rng.randint(0, 2)
                if kind == 0 and text:
                    position = rng.randrange(len(text))
                    text = text[:position] + rng.choice(injections) + text[position:]
                elif kind == 1 and text:
                    text = text[: rng.randrange(len(text))]
                else:
                    text = text + text
            tree = _tree(text, max_depth=16, max_elements=200)
            by_ordinal = {element.ordinal: element for element in tree.elements}
            for element in tree.elements:
                assert 0 <= element.projected_offset <= len(tree.projection), (text, element)
                assert element.projected_end <= len(tree.projection), (text, element)
                if element.parent_ordinal is not None:
                    parent = by_ordinal[element.parent_ordinal]
                    assert parent.projected_offset <= element.projected_offset, (text, element)
                    assert element.projected_end <= parent.projected_end, (text, element)


# --------------------------------------- the cid set read off the tree (Turn 1.5b)


def _cid_fixture(name: str):
    """``(referenced cids, Content-IDs, the sidecar's typed attach cid gaps)`` for one fixture."""
    raw = (GENERATED / f"{name}.eml").read_bytes()
    result = walk(EmlContainer(memory_bytes(raw)))
    referenced = [
        cid
        for _part, cids in selection_stage.cid_ref_rows(
            raw, result, max_depth=16, max_elements=1000
        )
        for cid in cids
    ]
    content_ids = [
        field.raw_value.strip().strip("<>").strip()
        for part in result.parts
        for field in part.header_fields
        if field.name.lower() == "content-id"
    ]
    sidecar = json.loads((GENERATED / f"{name}.expected.json").read_text(encoding="utf-8"))
    typed = [
        row[0]
        for row in sidecar["facts"].get("gaps.later", {}).get("value", [])
        if row[0].startswith("attach.cid_")
    ]
    return referenced, content_ids, typed


def test_the_cid_reference_set_feeds_cid_dangling_and_unreferenced() -> None:
    """The tree's cid set plus the walked ``Content-ID``s drive Turn 1.8's helper.

    ``attach.cid_dangling`` / ``attach.cid_unreferenced`` stay in ``gaps.later`` (Turn 1.8
    emits them), so this turn only proves the two inputs the helper will take are the ones
    the frozen sidecars type -- and that a cid is compared as an RFC 2392 addr-spec.
    """
    cases = {
        "attach_cid_dangling": (
            ["missing@example.test"],
            [],
            ["missing@example.test"],
            [],
            ["attach.cid_dangling"],
        ),
        "attach_inline_unreferenced": (
            [],
            ["spare@example.test"],
            [],
            ["spare@example.test"],
            ["attach.cid_unreferenced"],
        ),
        "attach_decoration_tracking_pixel": (
            [],
            ["pixel@example.test"],
            [],
            ["pixel@example.test"],
            ["attach.cid_unreferenced"],
        ),
        "attach_inline_referenced": (["logo@example.test"], ["logo@example.test"], [], [], []),
    }
    for name, (referenced_expected, content_ids_expected, dangling, unreferenced, typed_gaps) in cases.items():
        referenced, content_ids, typed = _cid_fixture(name)
        assert referenced == referenced_expected, (name, referenced)
        assert content_ids == content_ids_expected, (name, content_ids)
        assert typed == typed_gaps, (name, typed)
        assert selection_stage.dangling_and_unreferenced(referenced, content_ids) == (
            dangling,
            unreferenced,
        ), name
    # the comparison is case-sensitive as an addr-spec (RFC 2392), so a fold is not applied
    assert selection_stage.dangling_and_unreferenced(
        ["Logo@example.test"], ["logo@example.test"]
    ) == (["Logo@example.test"], ["logo@example.test"])


def test_the_tree_records_the_referenced_cid_set() -> None:
    """The cid set is read from the element tree's own attributes, never a regex over the HTML.

    A ``cid:`` inside a dropped subtree or a comment is not an element and never reaches the
    set; a cid url is normalized once (brackets/whitespace stripped, percent-decoded once,
    a ``?``/``#`` suffix kept verbatim, RFC 2392 has neither).
    """
    tree = _tree(
        '<img src=" cid:a%2Fb@example.test ">'
        '<img src="cid:logo@example.test?x=1#frag">'
        '<!-- <img src="cid:comment@example.test"> -->'
        "<style>p{background:url(cid:style@example.test)}</style>"
    )
    sources = [value for element in tree.elements for name, value in element.attributes if name == "src"]
    assert sources == [" cid:a%2Fb@example.test ", "cid:logo@example.test?x=1#frag"], sources
    values = [selection_stage._cid_value(source) for source in sources]
    assert values == ["a/b@example.test", "logo@example.test?x=1#frag"], values
