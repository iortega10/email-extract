"""Turn 1.7: the DOM quote family on the html view, and the resolution across both views.

Every message here is **built inline** from the design rules -- never copied from a catalogue
fixture or a sidecar. The rules under test are the DOM half of build-spec decision 3 and
decisions 2, 15 and 28-39, read on the **HTML projection** (:mod:`emailextract.htmltext`):
spans are the projection's code points taken from the tree's node-to-span map.

* ``gmail_quote``: a ``div`` or a ``blockquote`` matching the class **token**; one boundary,
  the inner ``blockquote`` and the ``gmail_attr`` wrapper adding no second ordinal;
* ``blockquote[type=cite]`` with the value compared case-insensitively;
* the Outlook marker ids ``divRplyFwdMsg``/``appendonsend`` with the ``x_`` rewrite form:
  ``divRplyFwdMsg`` is the element's own projected extent, ``appendonsend`` (a sentinel carrying
  no quoted words) starts at its first following element sibling and ends at its parent's
  projected extent;
* Thunderbird ``moz-cite-prefix`` (the prefix plus its following ``blockquote`` sibling, **with
  or without** ``type=cite``) and ``moz-forward-container`` (kind ``forward``, level 0, ordinal 0);
* the vendor-family gap and the absence answer;
* ordinals, nesting, the per-view level, the resolution rule and the disagreement -- and the
  oracle's **label-blind** evidence for the html rows.

Each failure names the rule, the element and the closed reason, and the walk is asserted to be
iterative, single-pass and linear with the deterministic
:data:`emailextract.quote.dom_rules.WORK` counter (never a clock).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from emailextract import htmltext, text as text_stage  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.evals import l1  # noqa: E402
from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars  # noqa: E402
from emailextract.quote import dom_rules, resolve  # noqa: E402
from emailextract.walk import walk  # noqa: E402

HEAD = b"From: Ada Sender <ada@example.test>\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"

MAX_DEPTH = 64
MAX_ELEMENTS = 200_000


def _message(html: bytes) -> bytes:
    """A minimal one-part ``text/html`` message: a Content-Type, then ``html`` exactly."""
    return HEAD + html


def _walk(html: bytes):
    message = _message(html)
    result = walk(EmlContainer(memory_bytes(message)))
    assert result.parts, "the inline message has no part"
    return message, result


def _view(html: bytes):
    """The one html view of an inline body (its scan, boundaries, level and gaps)."""
    message, result = _walk(html)
    views = resolve.scan_html_views(
        message, result, max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS
    )
    assert len(views) == 1, f"expected one html view, got {len(views)}"
    return views[0]


def _rows(html: bytes):
    """``body.quote_boundaries`` rows (RHS only: rule, kind, ordinal, depth, offset, length)."""
    message, result = _walk(html)
    return [
        row[2:]
        for row in resolve.all_quote_boundary_rows(
            message, result, max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS
        )
    ]


def _levels(html: bytes):
    message, result = _walk(html)
    return resolve.all_view_level_rows(
        message, result, max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS
    )


def _gaps(html: bytes):
    message, result = _walk(html)
    return resolve.html_gap_pairs(message, result, max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS)


def _projection(html: bytes):
    message, result = _walk(html)
    return resolve.html_views(message, result, max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS)[0][1]


# ------------------------------------------------------------------------ gmail_quote


def test_gmail_quote_on_a_div_fires_once() -> None:
    """A ``div`` with the class token ``gmail_quote`` is ONE boundary of kind quote."""
    html = b'<div class="gmail_quote">The earlier line.</div>\r\n'
    rows = _rows(html)
    assert len(rows) == 1, rows
    rule, kind, ordinal, depth, offset, length = rows[0]
    assert (rule, kind, ordinal) == ("gmail_quote", "quote", 1), rows[0]
    assert depth == [0], "the projection line carries no `>` prefix"
    projection = _projection(html)
    assert projection.text[offset : offset + length] == "The earlier line.", (
        "the span is the element's projected extent on the projection, exactly "
        "(no final-terminator extension; decision 40 as amended in 1.7b)"
    )

    # Token matching: a longer token list still matches by token, a superstring does not.
    assert len(_rows(b'<div class="gmail_quote gmail_quote_container">q</div>')) == 1
    assert _rows(b'<div class="my_gmail_quote_x">q</div>') == [], "matched by substring, not token"
    assert _rows(b'<div class="GMAIL_QUOTE">q</div>') == [], "class tokens are case-sensitive"


def test_gmail_quote_on_a_blockquote_adds_no_second_ordinal() -> None:
    """``blockquote.gmail_quote`` is the container; a ``div.gmail_quote`` around one is ONE."""
    blockquote = _rows(b'<blockquote class="gmail_quote">The earlier line.</blockquote>')
    assert len(blockquote) == 1, blockquote
    assert blockquote[0][0] == "gmail_quote" and blockquote[0][2] == 1, blockquote[0]

    nested = _rows(
        b'<div class="gmail_quote">attribution'
        b'<blockquote class="gmail_quote">The earlier line.</blockquote></div>'
    )
    assert len(nested) == 1, f"the inner blockquote is part of the container: {nested}"
    assert nested[0][2] == 1, nested[0]

    bare = _rows(
        b'<div class="gmail_quote">attribution<blockquote>The earlier line.</blockquote></div>'
    )
    assert len(bare) == 1, f"a bare blockquote inside the container is part of it: {bare}"


def test_the_attribution_wrapper_adds_no_second_ordinal() -> None:
    """``div.gmail_attr`` inside the container is part of it: no second boundary, no gap."""
    html = (
        b'<div class="gmail_quote">'
        b'<div class="gmail_attr">On Tue, 4 Mar 2025, Ada Sender wrote:</div>'
        b"<blockquote>The earlier line.</blockquote></div>"
    )
    rows = _rows(html)
    assert len(rows) == 1, f"the attribution wrapper is not its own boundary: {rows}"
    assert rows[0][2] == 1, rows
    assert _gaps(html) == [], "the named wrapper is never the vendor-family gap"


def test_blockquote_type_cite_is_a_boundary_and_its_value_is_case_insensitive() -> None:
    """A ``blockquote[type=cite]`` at top level is its own boundary; the value case-folds."""
    assert _rows(b'<blockquote type="cite">q</blockquote>')[0][0] == "blockquote_type_cite"
    assert _rows(b'<blockquote type="CITE">q</blockquote>')[0][0] == "blockquote_type_cite"
    assert _rows(b'<blockquote type="cite ">q</blockquote>')[0][0] == "blockquote_type_cite"
    assert _rows(b'<blockquote type="cite1">q</blockquote>') == []
    assert _rows(b"<blockquote>q</blockquote>") == [], "a bare blockquote is no table row"


def test_an_inner_container_is_part_of_the_outer_ordinal() -> None:
    """The mixed-origin case: a Gmail container wrapping an Outlook block is ONE ordinal."""
    html = (
        b'<div class="gmail_quote"><div id="divRplyFwdMsg">From: Ada</div>'
        b'<blockquote type="cite">The earlier line.</blockquote></div>'
    )
    rows = _rows(html)
    assert len(rows) == 1, f"one quote, one ordinal: {rows}"
    assert rows[0][0] == "gmail_quote" and rows[0][2] == 1, rows[0]
    assert _levels(html) == [["1", "html", 1, "gmail_quote"]], _levels(html)


# --------------------------------------------------------------------------- Outlook


def test_outlook_divrplyfwd_fires() -> None:
    """``divRplyFwdMsg`` is a quote boundary; its span is the element's own projected extent."""
    html = b'<div>Hi Ben.</div>\r\n<div id="divRplyFwdMsg">From: Ada</div>\r\n'
    rows = _rows(html)
    assert len(rows) == 1, rows
    rule, kind, ordinal, depth, offset, length = rows[0]
    assert (rule, kind, ordinal) == ("outlook_divrplyfwd", "quote", 1), rows[0]
    projection = _projection(html)
    assert projection.text[offset : offset + length] == "From: Ada", (
        "the element's own extent exactly, with no final-terminator extension (decision 40, 1.7b)"
    )

    # The header block is the marker's OWN extent: following siblings are not pulled in (only
    # ``appendonsend`` is a sentinel whose following siblings are the quoted history).
    sibling = _rows(b'<div id="divRplyFwdMsg">From: Ada</div>\r\n<div>more</div>\r\n')
    projection = _projection(b'<div id="divRplyFwdMsg">From: Ada</div>\r\n<div>more</div>\r\n')
    _rule, _kind, _ordinal, _depth, offset, length = sibling[0]
    assert projection.text[offset : offset + length] == "From: Ada", sibling[0]


def test_appendonsend_and_the_x_prefix_fire() -> None:
    """``appendonsend``/``x_appendonsend`` are the same row; the ``x_`` rewrite form is recognised."""
    for identifier in (b"appendonsend", b"x_appendonsend"):
        html = (
            b'<div>Hi Ben.</div>\r\n<div id="' + identifier + b'"></div>\r\n'
            b"<div>On Tue, 4 Mar 2025, Ada Sender wrote:</div>\r\n"
        )
        rows = _rows(html)
        assert len(rows) == 1, (identifier, rows)
        assert rows[0][0] == "outlook_appendonsend" and rows[0][2] == 1, rows[0]
        projection = _projection(html)
        _rule, _kind, _ordinal, depth, offset, length = rows[0]
        assert projection.text[offset : offset + length] == "On Tue, 4 Mar 2025, Ada Sender wrote:", (
            "the marker is a sentinel; the span starts at its first following element sibling"
        )
        assert depth == [0], "the empty marker's own line is not part of the span (decision 41, 1.7b)"

    # The marker's own words are never the quoted history: the span starts at the NEXT element.
    marked = b'<div id="appendonsend">MARKER</div><div>quoted</div>'
    projection = _projection(marked)
    _rule, _kind, _ordinal, _depth, offset, length = _rows(marked)[0]
    assert projection.text[offset : offset + length] == "quoted", rows[0]

    # A marker with no following element sibling spans its own (here zero-length) extent, kept.
    lonely = _rows(b'<div id="appendonsend"></div>')
    assert len(lonely) == 1 and lonely[0][5] == 0, lonely

    assert _rows(b'<div id="appendonsend_extra"></div><div>q</div>') == [], "the id match is exact"


# ------------------------------------------------------------------------ Thunderbird


def test_thunderbird_moz_cite_prefix_fires() -> None:
    """The prefix covers itself and its following ``blockquote`` sibling, bare or ``type=cite``."""
    html = (
        b'<div class="moz-cite-prefix">On 2025-03-04 09:00, Ada Sender wrote:</div>\r\n'
        b'<blockquote type="cite">The earlier line.</blockquote>\r\n'
    )
    rows = _rows(html)
    assert len(rows) == 1, f"the prefix and its blockquote are ONE boundary: {rows}"
    rule, kind, ordinal, depth, offset, length = rows[0]
    assert (rule, kind, ordinal) == ("thunderbird_moz_cite_prefix", "quote", 1), rows[0]
    projection = _projection(html)
    assert projection.text[offset : offset + length] == (
        "On 2025-03-04 09:00, Ada Sender wrote:\r\nThe earlier line."
    ), "the span covers the prefix element AND that blockquote, one boundary"
    assert depth == [0, 0], "both the prefix line and the blockquote line are covered"

    # A BARE blockquote is the same quoted block (real Thunderbird emits ``type=cite``; decision
    # 42, amended in 1.7b): it is pulled in and adds no second boundary and no second ordinal.
    bare = _rows(
        b'<div class="moz-cite-prefix">On 2025-03-04 09:00, Ada Sender wrote:</div>\r\n'
        b"<blockquote>The earlier line.</blockquote>\r\n"
    )
    assert len(bare) == 1 and bare[0][0] == "thunderbird_moz_cite_prefix", bare
    assert bare[0][3] == [0, 0] and bare[0][5] == length, ("the bare blockquote is pulled in", bare)

    # A following sibling that is NOT a blockquote leaves the boundary at the prefix element.
    other = _rows(
        b'<div class="moz-cite-prefix">On 2025-03-04 09:00, Ada Sender wrote:</div>\r\n'
        b"<div>the earlier line</div>\r\n"
    )
    assert len(other) == 1 and other[0][0] == "thunderbird_moz_cite_prefix", other
    assert other[0][3] == [0] and other[0][5] < length, ("the prefix alone is a shorter span", other)


def test_thunderbird_moz_forward_container_is_a_forward_banner() -> None:
    """A ``moz-forward-container`` is kind ``forward`` at level 0 with ordinal 0, and it nests."""
    html = b'<div class="moz-forward-container">The forwarded note.</div>\r\n'
    rows = _rows(html)
    assert len(rows) == 1, rows
    assert rows[0][0] == "thunderbird_moz_forward_container", rows[0]
    assert rows[0][1] == "forward" and rows[0][2] == 0, f"forward, ordinal 0: {rows[0]}"
    assert _levels(html) == [["1", "html", 0, "thunderbird_moz_forward_container"]], _levels(html)

    # A forward does not suppress a quote container found inside it (both are recorded).
    nested = _rows(
        b'<div class="moz-forward-container">'
        b'<div class="gmail_quote">The earlier line.</div></div>'
    )
    assert len(nested) == 2, f"the inner quote is still recorded: {nested}"
    assert {row[0] for row in nested} == {
        "thunderbird_moz_forward_container",
        "gmail_quote",
    }, nested
    assert sorted(row[2] for row in nested) == [0, 1], nested


# ----------------------------------------------------------- the gap and the absence


def test_a_known_vendor_prefix_without_a_row_is_the_html_gap() -> None:
    """A vendor-prefix class/id with no table row is ``body.html_quote_rule_gap``, never a boundary."""
    cases = (
        b'<div class="moz-custom-quote">The earlier line.</div>',
        b'<div class="yahoo_quoted">The earlier line.</div>',
        b'<div class="gmail_extra">The earlier line.</div>',
        b'<div id="divRplyFwdMsg_extra">The earlier line.</div>',
    )
    for html in cases:
        view = _view(html)
        assert view.boundaries == (), f"no boundary is invented for the gap: {html!r}"
        assert view.scan.no_boundary is False, (
            "a vendor-family element is not the absence answer (decision 3)"
        )
        assert view.scan.gaps == (dom_rules.GAP_BODY_HTML_QUOTE_RULE_GAP,), (html, view.scan.gaps)
        assert _levels(html) == [], "a view with no boundary and no `>` line has no level row"


def test_the_absence_answer_is_a_bare_html_body() -> None:
    """No DOM rule, no vendor family and no ``>` `` line is ``body.no_boundary_found``."""
    html = b"<p>Hello Ben. No quoting here at all.</p>\r\n"
    view = _view(html)
    assert view.scan.no_boundary is True, view.scan
    assert view.scan.gaps == (dom_rules.GAP_BODY_NO_BOUNDARY_FOUND,), view.scan.gaps
    assert _gaps(html) == [("body.no_boundary_found", "1")], _gaps(html)
    assert _rows(html) == [] and _levels(html) == [], "the controls record nothing else"

    # A `>` prefix line is the gt rule, so it is never the absence answer.
    marked = _view(b"<div>x\r\n&gt; the earlier line\r\n</div>")
    assert marked.scan.no_boundary is False, marked.scan
    assert dom_rules.GAP_BODY_NO_BOUNDARY_FOUND not in marked.scan.gaps, marked.scan.gaps


# ----------------------------------------------------------------- levels and ordinals


def test_structural_and_prefix_ranks_resolve_per_span() -> None:
    """The view's level is the highest of the quote ordinal and the deepest per-line depth."""
    html = b'<div class="gmail_quote">x\r\n&gt; one\r\n&gt;&gt; two\r\n</div>\r\n'
    rows = _rows(html)
    assert len(rows) == 1, f"a `>` run inside the container is part of it (one quote): {rows}"
    rule, kind, ordinal, depth, offset, length = rows[0]
    assert (rule, kind, ordinal) == ("gmail_quote", "quote", 1), rows[0]
    assert depth == [0, 1, 2], f"one depth per covered projection line: {depth}"
    assert _levels(html) == [["1", "html", 2, "gmail_quote"]], (
        "the level is max(quote ordinal, deepest depth) and carries the structural rule"
    )

    # A `>` run with no container at all is its own gt_family boundary and sets the level.
    loose = b"<p>x</p>\r\n&gt;&gt; one\r\n"
    loose_rows = _rows(loose)
    assert [row[0] for row in loose_rows] == ["gt_family"], loose_rows
    assert loose_rows[0][3] == [2], loose_rows[0]
    assert _levels(loose) == [["1", "html", 2, "gt_family"]], _levels(loose)


def test_an_all_zero_depth_beside_a_structural_rule_is_normal() -> None:
    """A structural quote with no ``>` `` line is level 1 and no disagreement (decision 2)."""
    html = b'<div class="gmail_quote">The earlier line.</div>\r\n'
    view = _view(html)
    assert view.boundaries and all(boundary.prefix_depth == [0] for boundary in view.boundaries)
    assert view.disagreement is False, "an all-zero depth beside a structural rule is normal"
    assert _levels(html) == [["1", "html", 1, "gmail_quote"]], _levels(html)
    assert resolve.disagreement(1, 0) is False
    assert resolve.disagreement(2, 1) is True
    assert resolve.disagreement(2, 2) is False


def test_the_disagreement_predicate_fires_only_when_the_ranks_differ() -> None:
    """The html view's own predicate: ordinal 2 beside depth 1 disagrees, 1 beside 1 does not."""
    two = (
        b'<div class="gmail_quote">first</div>\r\n'
        b'<blockquote type="cite">second</blockquote>\r\n'
    )
    view = _view(two)
    ordinals = [boundary.ordinal for boundary in view.boundaries]
    assert ordinals == [1, 2], ordinals
    assert view.scan.max_depth == 0, "no `>` line in this body"
    assert view.disagreement is False, "an all-zero depth is normal"

    interleaved = (
        b'<div class="gmail_quote">first</div>\r\n'
        b"&gt; the earlier line\r\n"
        b'<blockquote type="cite">third</blockquote>\r\n'
    )
    mixed = _view(interleaved)
    quote_ordinals = [b.ordinal for b in mixed.boundaries if b.kind.value == "quote"]
    assert sorted(quote_ordinals) == [1, 2, 3], mixed.boundaries
    assert mixed.scan.max_depth == 1, mixed.scan
    assert mixed.disagreement is True, "3 quote ordinals beside a depth of 1"
    assert "view.quote_level_disagreement" in [
        gap for gap, _locator in _gaps(interleaved)
    ], _gaps(interleaved)


def test_the_view_level_carries_its_resolution_rule_id() -> None:
    """``resolution_rule_id`` is the first structural quote boundary's, never the last one's."""
    html = (
        b'<div class="gmail_quote">first</div>\r\n'
        b'<div id="divRplyFwdMsg">second</div>\r\n'
    )
    rows = _rows(html)
    assert [row[0] for row in rows] == ["gmail_quote", "outlook_divrplyfwd"], rows
    assert _levels(html) == [["1", "html", 2, "gmail_quote"]], _levels(html)

    # A forward-only view still has a row, level 0, with the forward's own rule (decision 38).
    assert _levels(b'<div class="moz-forward-container">q</div>') == [
        ["1", "html", 0, "thunderbird_moz_forward_container"]
    ]

    # A view with no boundary and no `>` line has no row at all (the controls).
    assert _levels(b"<p>Hi.</p>") == []


# ================================================= item 7a: the step budget and mutants


def _steps(html: bytes) -> int:
    """The deterministic work count of one projection scan (never a clock)."""
    dom_rules.WORK.reset()
    dom_rules.scan_projection(htmltext.project(html.decode("utf-8"),
                                               max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS))
    return dom_rules.WORK.count()


def test_the_dom_walk_is_iterative_and_survives_a_capped_tree() -> None:
    """A capped tree (the depth cap recorded, not raised) is walked without recursion."""
    deep = b"<div>" * 5000
    message = _message(deep)
    body = message.split(b"\r\n\r\n", 1)[1]
    projection = htmltext.project(body.decode("utf-8"), max_depth=8, max_elements=MAX_ELEMENTS)
    scan = dom_rules.scan_projection(projection)
    assert scan.boundaries == ()
    assert projection.tree.truncation is not None, "the cap is a recorded state, not a raise"


def test_the_dom_walk_step_count_is_exact_and_linear() -> None:
    """Exact reproducible counts for fixed hostile inputs, and less than a doubling when doubled.

    ``dom_rules.WORK`` is the walker's own ``WorkCounter`` pattern (a test resets and reads it,
    never a clock): one step per element, one per class token and one per projection line read.
    """
    # A single element with a 1,000,000-character class attribute (one token, one line).
    giant = b'<div class="' + b"x" * 1_000_000 + b'">q</div>'
    assert _steps(giant) == 3, "one element, one token, one projection line: a fixed count"

    # 100,000 sibling containers: linear in elements, and the count is a function of the bytes.
    siblings = b'<blockquote class="gmail_quote">q</blockquote>' * 1000
    small = _steps(siblings)
    assert small == 2001, "one element and one class token each, one projection line"
    large = _steps(siblings * 2)
    assert large == 4001, large
    ratio = large / small
    assert ratio < 2.2, f"the walk is not linear: {small} -> {large} (ratio {ratio})"

    # A 1,000-token class attribute is linear in tokens (500 x 1,000 and half of it).
    tokens = b"t " * 999 + b"t"
    many = (b'<div class="' + tokens + b'">q</div>') * 500
    assert _steps(many) == 500_501, "500 elements x 1,000 tokens, plus the elements and the line"
    assert _steps((b'<div class="' + tokens + b'">q</div>') * 250) == 250_251

    # The other hostile shapes: bounded work, no exception, exact reproducible counts.
    assert _steps(b"<blockquote></blockquote>" * 1000) == 1000, "no tokens, no projection text"
    assert _steps(b'<div class="moz-cite-prefix">x</div>' * 1000) == 2001
    # A deep nest is bounded by the tree's recorded depth cap, not by the walk (decision 9).
    assert _steps(b"<div>" * 1000) == 64, "the depth cap (64) stops the tree, and the walk with it"


@dataclasses.dataclass(frozen=True)
class Mutant:
    """One careless reading: the rule it breaks, how, and the observation it must move."""

    rule_id: str
    description: str
    apply: Callable[[pytest.MonkeyPatch, dict], None]
    observe: Callable[[], Any]


def _patch(monkeypatch: pytest.MonkeyPatch, name: str, wrapper: Callable, flags: dict) -> None:
    """Replace ``dom_rules.<name>`` with a wrapper that counts its calls (anti-vacuity (b))."""
    real = getattr(dom_rules, name)

    def counted(*args: Any, **kwargs: Any) -> Any:
        flags["reached"] += 1
        return wrapper(real, *args, **kwargs)

    monkeypatch.setattr(dom_rules, name, counted)


def _gmail_token_substring(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def row(real, element, attributes, tokens):
        if element.tag in ("div", "blockquote") and "gmail_quote" in attributes.get("class", ""):
            return dom_rules.RULE_GMAIL_QUOTE
        return real(element, attributes, tokens)

    _patch(monkeypatch, "_table_row", row, flags)


def _attribution_wrapper_ordinal(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def row(real, element, attributes, tokens):
        if dom_rules.NAMED_HELPERS & set(tokens):
            return dom_rules.RULE_GMAIL_QUOTE
        return real(element, attributes, tokens)

    _patch(monkeypatch, "_table_row", row, flags)


def _nested_container_second_ordinal(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    _patch(monkeypatch, "_contains", lambda real, stack, start, end: False, flags)


def _cite_value_case_sensitive(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def cite(real, element, attributes):
        return element.tag == "blockquote" and attributes.get("type", "") == "cite"

    _patch(monkeypatch, "_is_blockquote_cite", cite, flags)


def _x_prefix_unrecognised(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def row(real, element, attributes, tokens):
        if attributes.get("id", "").startswith("x_"):
            return None
        return real(element, attributes, tokens)

    _patch(monkeypatch, "_table_row", row, flags)


def _forward_container_ordinal(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def candidates(real, elements, by_ordinal, next_sibling, projection_length):
        found, fired, vendor = real(elements, by_ordinal, next_sibling, projection_length)
        return [
            (rule, "quote" if kind == "forward" else kind, start, end, ordinal)
            for rule, kind, start, end, ordinal in found
        ], fired, vendor

    _patch(monkeypatch, "_candidates", candidates, flags)


def _forward_suppresses_quote(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def candidates(real, elements, by_ordinal, next_sibling, projection_length):
        found, fired, vendor = real(elements, by_ordinal, next_sibling, projection_length)
        forwards = [(s, e) for _r, kind, s, e, _o in found if kind == "forward"]
        kept = [
            item
            for item in found
            if item[1] != "quote"
            or not any(first <= item[2] and last >= item[3] for first, last in forwards)
        ]
        return kept, fired, vendor

    _patch(monkeypatch, "_candidates", candidates, flags)


def _vendor_prefix_ignored(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def candidates(real, elements, by_ordinal, next_sibling, projection_length):
        found, fired, _vendor = real(elements, by_ordinal, next_sibling, projection_length)
        return found, fired, False

    _patch(monkeypatch, "_candidates", candidates, flags)


def _yahoo_class_boundary(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def row(real, element, attributes, tokens):
        if "yahoo_quoted" in tokens:
            return dom_rules.RULE_GMAIL_QUOTE
        return real(element, attributes, tokens)

    _patch(monkeypatch, "_table_row", row, flags)


def _span_from_raw_html(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Take the boundary's offset from the element's raw-HTML ordinal, not the node-to-span map."""

    def candidates(real, elements, by_ordinal, next_sibling, projection_length):
        found, fired, vendor = real(elements, by_ordinal, next_sibling, projection_length)
        return [
            (rule, kind, ordinal, end, ordinal)
            for rule, kind, _start, end, ordinal in found
        ], fired, vendor

    _patch(monkeypatch, "_candidates", candidates, flags)


def _gt_run_inside_a_container(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    _patch(monkeypatch, "_gt_absorbed", lambda real, spans, start, end: False, flags)


def _recursive_walk(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Walk the tree by recursion over parent/child links: a deep nest must blow the stack."""
    real = dom_rules.scan_projection

    def scanning(projection):
        flags["reached"] += 1
        result = real(projection)
        children: dict[Any, list[int]] = {}
        for element in projection.tree.elements:
            children.setdefault(element.parent_ordinal, []).append(element.ordinal)
        by_ordinal = {element.ordinal: element for element in projection.tree.elements}

        def descend(ordinal: Any) -> None:
            for child in children.get(ordinal, ()):
                descend(by_ordinal[child].ordinal)

        descend(None)
        return result

    monkeypatch.setattr(dom_rules, "scan_projection", scanning)


def _resolution_from_last_boundary(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    def last(boundaries):
        flags["reached"] += 1
        return boundaries[-1].rule_id if boundaries else "gt_family"

    monkeypatch.setattr(resolve, "_resolution_rule", last)


def _view_row_dropped(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    real = resolve.scan_html_view

    def dropping(part, projection):
        flags["reached"] += 1
        view = real(part, projection)
        if any(boundary.kind.value == "quote" for boundary in view.boundaries):
            return view
        return dataclasses.replace(view, level=None)

    monkeypatch.setattr(resolve, "scan_html_view", dropping)


def _deep_nest_scan_ok(depth: int = 2000) -> bool:
    """Whether scanning a ``depth``-deep nest returns (a RecursionError is the mutant's failure)."""
    html = b"<div>" * depth
    message, result = _walk(html)
    try:
        resolve.scan_html_views(message, result, max_depth=depth + 4, max_elements=MAX_ELEMENTS)
    except RecursionError:
        return False
    return True


def _cite_prefix_span_prefix_only(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """The prefix boundary keeps only the prefix element, dropping its blockquote sibling."""

    def candidates(real, elements, by_ordinal, next_sibling, projection_length):
        found, fired, vendor = real(elements, by_ordinal, next_sibling, projection_length)
        shortened = []
        for rule, kind, start, end, ordinal in found:
            if rule == dom_rules.RULE_THUNDERBIRD_MOZ_CITE_PREFIX:
                element = by_ordinal[ordinal]
                end = element.projected_offset + element.projected_length
            shortened.append((rule, kind, start, end, ordinal))
        return shortened, fired, vendor

    _patch(monkeypatch, "_candidates", candidates, flags)


def _terminator_extension_re_added(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Re-add the final-terminator extension to a DOM span (decision 40's old clause)."""

    def span(real, lines, starts, start, end):
        start, end = real(lines, starts, start, end)
        if lines and end > start:
            last = dom_rules._line_of(starts, end - 1)
            if last == len(lines) - 1 and lines[last].term_end > end:
                end = lines[last].term_end
        return start, end

    _patch(monkeypatch, "_dom_span", span, flags)


def _appendonsend_span_from_marker(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Start the appendonsend span at the marker itself (decision 41's old reading)."""

    def span(real, elements, by_ordinal, next_sibling, projection_length, element):
        start, end = real(elements, by_ordinal, next_sibling, projection_length, element)
        return element.projected_offset, end

    _patch(monkeypatch, "_appendonsend_span", span, flags)


def _cite_prefix_requires_type(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Require ``blockquote[type=cite]`` for the prefix's following sibling (decision 42's old)."""

    def blockquote(real, element, attributes):
        return real(element, attributes) and attributes.get("type", "").strip().lower() == "cite"

    _patch(monkeypatch, "_is_blockquote", blockquote, flags)


#: mutant id -> the case. Every rule id the DOM stage can emit has at least one case
#: (:func:`test_every_dom_rule_id_has_a_mutation_case`); the extras cover the nesting, the span
#: source, the recursion hazard and the resolution/level-row rules.
MUTANTS: dict[str, Mutant] = {
    "gmail_token_substring": Mutant(
        dom_rules.RULE_GMAIL_QUOTE,
        "matched the class by substring instead of by token",
        _gmail_token_substring,
        observe=lambda: _rows(b'<div class="my_gmail_quote_x">q</div>'),
    ),
    "gmail_blockquote_two_boundaries": Mutant(
        dom_rules.RULE_GMAIL_QUOTE,
        "gave a blockquote inside a gmail container its own ordinal",
        _nested_container_second_ordinal,
        observe=lambda: _rows(
            b'<div class="gmail_quote">a<blockquote class="gmail_quote">b</blockquote></div>'
        ),
    ),
    "attribution_wrapper_ordinal": Mutant(
        dom_rules.RULE_GMAIL_QUOTE,
        "treated the gmail_attr attribution wrapper as its own container",
        _attribution_wrapper_ordinal,
        observe=lambda: _rows(b'<div class="gmail_attr">q</div>'),
    ),
    "cite_value_case_sensitive": Mutant(
        dom_rules.RULE_BLOCKQUOTE_TYPE_CITE,
        "compared blockquote type=cite case-sensitively on the value",
        _cite_value_case_sensitive,
        observe=lambda: _rows(b'<blockquote type="CITE">q</blockquote>'),
    ),
    "outlook_span_from_raw_html": Mutant(
        dom_rules.RULE_OUTLOOK_DIVRPLYFWD,
        "took the span from a raw-HTML coordinate instead of the node-to-span map",
        _span_from_raw_html,
        observe=lambda: _rows(b'<p>Hi</p><div id="divRplyFwdMsg">From: Ada</div>\r\n'),
    ),
    "x_prefix_unrecognised": Mutant(
        dom_rules.RULE_OUTLOOK_APPENDONSEND,
        "did not recognise the x_ prefix Outlook adds on rewrite",
        _x_prefix_unrecognised,
        observe=lambda: _rows(
            b'<div id="x_appendonsend"></div><div>On Mon, Ada wrote:</div>'
        ),
    ),
    "moz_cite_prefix_span": Mutant(
        dom_rules.RULE_THUNDERBIRD_MOZ_CITE_PREFIX,
        "ended the prefix boundary at the prefix element, dropping its blockquote sibling",
        _cite_prefix_span_prefix_only,
        observe=lambda: _rows(
            b'<div class="moz-cite-prefix">On 2025-03-04 09:00, Ada Sender wrote:</div>\r\n'
            b'<blockquote type="cite">The earlier line.</blockquote>\r\n'
        ),
    ),
    "forward_container_ordinal": Mutant(
        dom_rules.RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER,
        "gave a forward container an ordinal (kind quote, level >= 1)",
        _forward_container_ordinal,
        observe=lambda: _rows(b'<div class="moz-forward-container">q</div>'),
    ),
    "forward_suppresses_quote": Mutant(
        dom_rules.RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER,
        "let a forward container suppress the quote container inside it",
        _forward_suppresses_quote,
        observe=lambda: _rows(
            b'<div class="moz-forward-container">'
            b'<div class="gmail_quote">q</div></div>'
        ),
    ),
    "vendor_prefix_ignored": Mutant(
        "body.html_quote_rule_gap",
        "ignored a vendor-prefix element with no row instead of recording the gap",
        _vendor_prefix_ignored,
        observe=lambda: _gaps(b'<div class="moz-custom-quote">q</div>'),
    ),
    "yahoo_class_boundary": Mutant(
        "body.html_quote_rule_gap",
        "gave a yahoo_ class a boundary instead of the vendor-family gap",
        _yahoo_class_boundary,
        observe=lambda: _rows(b'<div class="yahoo_quoted">q</div>'),
    ),
    "gt_run_inside_a_container": Mutant(
        dom_rules.RULE_GT_FAMILY,
        "counted a `>` run inside a quote boundary as a second ordinal",
        _gt_run_inside_a_container,
        observe=lambda: _rows(b'<div class="gmail_quote">x\r\n&gt; q\r\n</div>'),
    ),
    "recursive_walk": Mutant(
        "walk shape",
        "walked the tree recursively; a deep nest must fail it",
        _recursive_walk,
        observe=_deep_nest_scan_ok,
    ),
    "resolution_from_last_boundary": Mutant(
        "body.view_levels",
        "took the html view's resolution rule from the LAST boundary",
        _resolution_from_last_boundary,
        observe=lambda: _levels(
            b'<div class="gmail_quote">first</div>\r\n'
            b'<div id="divRplyFwdMsg">second</div>\r\n'
        ),
    ),
    "view_row_dropped": Mutant(
        "body.view_levels",
        "dropped the view row for a forward-only html view",
        _view_row_dropped,
        observe=lambda: _levels(b'<div class="moz-forward-container">q</div>'),
    ),
    "dom_span_terminator_extension": Mutant(
        dom_rules.RULE_GMAIL_QUOTE,
        "re-added the final-terminator extension to a DOM span",
        _terminator_extension_re_added,
        observe=lambda: _rows(b'<div class="gmail_quote">q</div>\r\n'),
    ),
    "appendonsend_span_from_marker": Mutant(
        dom_rules.RULE_OUTLOOK_APPENDONSEND,
        "started the appendonsend span at the marker instead of its first following sibling",
        _appendonsend_span_from_marker,
        observe=lambda: _rows(b'<div id="appendonsend">MARKER</div><div>quoted</div>'),
    ),
    "moz_cite_prefix_requires_type_cite": Mutant(
        dom_rules.RULE_THUNDERBIRD_MOZ_CITE_PREFIX,
        "required blockquote[type=cite] for the prefix's following sibling",
        _cite_prefix_requires_type,
        observe=lambda: _rows(
            b'<div class="moz-cite-prefix">On 2025-03-04 09:00, Ada Sender wrote:</div>\r\n'
            b"<blockquote>The earlier line.</blockquote>\r\n"
        ),
    ),
}


def test_every_dom_rule_id_has_a_mutation_case() -> None:
    """No rule id the DOM stage can emit is left without a careless reading (item 7a)."""
    covered = {mutant.rule_id for mutant in MUTANTS.values()}
    missing = sorted(set(dom_rules.DOM_RULES) - covered)
    assert not missing, f"rule id(s) with no mutation case: {missing}"
    assert len(MUTANTS) == 18, sorted(MUTANTS)


@pytest.mark.parametrize("mutant_id", sorted(MUTANTS))
def test_a_careless_dom_mutant_is_caught(mutant_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each careless reading is reached, and it moves a label-blind observation.

    The anti-vacuity triple: (a) the patched symbol exists, (b) it was **reached**, and (c) the
    measured observation differs from the baseline.
    """
    mutant = MUTANTS[mutant_id]
    flags = {"reached": 0}
    baseline = mutant.observe()
    mutant.apply(monkeypatch, flags)
    mutated = mutant.observe()
    assert mutated != baseline, (
        f"{mutant_id}: {mutant.description} did not move the observation "
        f"({baseline!r} -> {mutated!r})"
    )
    assert flags["reached"] > 0, f"{mutant_id}: the patch was never reached (vacuous)"


# ================================================ item 7b: the seeded fuzz

#: The seed of the fuzz's positions and lengths (the mutation KINDS are fixed, not seeded).
FUZZ_SEED = 20250304

#: How many mutated variants each html part contributes.
FUZZ_SEEDS = 9


def _mutated_variants(text: str, rng: random.Random) -> list[bytes]:
    """The nine seeded mutations of one html part's bytes (the DOM fuzz corpus)."""
    data = text.encode("utf-8")
    if not data:
        return []
    index = lambda: rng.randrange(len(data))  # noqa: E731 - a seeded position

    flipped = bytearray(data)
    for _ in range(3):
        flipped[index()] = rng.randrange(256)
    repeated = bytearray(data)
    start = index()
    repeated[start:start] = data[start : start + rng.randint(1, 64)]
    cut = index()
    fragment = bytearray(data)
    fragment[index():0] = b"<div class=" + b"x" * rng.randint(1, 8)
    unclosed = bytearray(data)
    unclosed[index():0] = b'<blockquote class="gmail_quote">'
    weird = bytearray(data)
    weird[index():0] = b"\x00" * rng.randint(1, 8) + b'id="divRplyFwdMsg'
    giant = bytearray(data)
    giant[index():0] = b'<div class="' + b"y" * rng.randint(1, 2000) + b'">'
    digits = bytearray(data)
    digits[index():0] = "\u0661\u0662\u0663".encode("utf-8") * rng.randint(1, 4)
    return [
        bytes(flipped),  # byte flips
        bytes(data[: rng.randrange(len(data) + 1)]),  # truncation
        bytes(repeated),  # a repeated chunk
        bytes(data[cut:] + data[:cut]),  # swapped chunks
        bytes(fragment),  # an injected `<div class=` fragment
        bytes(unclosed),  # an unclosed container
        bytes(weird),  # NULs and an injected `id=`
        bytes(giant),  # a giant attribute value
        bytes(digits),  # non-ASCII digits
    ]


def _html_parts() -> list[tuple[str, str]]:
    """``(stem, decoded html text)`` for every ``text/html`` part of every fixture."""
    parts: list[tuple[str, str]] = []
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        for part in result.parts:
            if (part.content_type or "").lower() != "text/html":
                continue
            record = text_stage.analyse_part(raw, part)
            if record is not None:
                parts.append((stem, record.text))
    return parts


def _fuzz_html_parts() -> tuple[int, list[tuple]]:
    """Walk every ``text/html`` message built from a mutated html part; ``(cases, failures)``.

    Each failure names the fixture, the variant number and the seed, so a planted raiser is
    reported **with its seed**.
    """
    rng = random.Random(FUZZ_SEED)
    cases = 0
    failures: list[tuple] = []
    for stem, text in _html_parts():
        for number, data in enumerate(_mutated_variants(text, rng)):
            cases += 1
            where = f"{stem}#{number} seed={FUZZ_SEED}"
            try:
                message = _message(data)
                result = walk(EmlContainer(memory_bytes(message)))
                for view in resolve.scan_html_views(
                    message, result, max_depth=MAX_DEPTH, max_elements=MAX_ELEMENTS
                ):
                    length = len(view.projection.text)
                    for boundary in view.boundaries:
                        if not 0 <= boundary.span.start <= boundary.span.end <= length:
                            failures.append((where, "span outside the projection", boundary))
                    ordinals = [
                        boundary.ordinal
                        for boundary in view.boundaries
                        if boundary.kind.value == "quote"
                    ]
                    if ordinals != list(range(1, len(ordinals) + 1)):
                        failures.append((where, "ordinals do not increase from 1", ordinals))
            except Exception as error:  # noqa: BLE001 - the fuzz must catch anything
                failures.append((where, type(error).__name__, str(error)))
    return cases, failures


def test_the_seeded_fuzz_over_mutated_html_parts_is_bounded() -> None:
    """No exception, every span inside the projection, every quote ordinal a 1-based rank."""
    began = time.monotonic()
    cases, failures = _fuzz_html_parts()
    elapsed = time.monotonic() - began
    assert cases == len(_html_parts()) * FUZZ_SEEDS, cases
    assert not failures, failures[:3]
    assert elapsed < 60, f"the seeded fuzz took {elapsed:.1f}s"


def test_a_planted_raiser_fails_the_fuzz_with_the_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fuzz is able to fail: a planted raiser is reported, with the seed that found it."""

    def raising(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("planted raiser")

    monkeypatch.setattr(resolve, "scan_html_view", raising)
    cases, failures = _fuzz_html_parts()
    assert cases, "the fuzz ran no case"
    assert failures, "the planted raiser must fail the fuzz"
    assert any("RuntimeError" in failure for failure in failures), failures[:3]
    assert f"seed={FUZZ_SEED}" in failures[0][0], failures[0]


# ================================================ item 7d: the cross-interpreter digest

#: sha256 of the JSON of ``{stem: [all_quote_boundary_rows, all_view_level_rows]}`` (both views)
#: over the 119 committed fixtures, with ``sort_keys=True`` and ``ensure_ascii=False``. The html
#: projection's line model and ``html.parser`` can differ across CPython patch levels, so this
#: digest is the check that no DOM rule moves with them: it must be **identical** on both
#: interpreters and is recorded in ``docs/design/phase1-empirical.md`` with the command that
#: produced it.
DOM_ROWS_DIGEST = "7e4c417a64fb6563b33200c010d43180c7f79ebdeb7d7e71183f0c75889e72f7"


def test_the_dom_rows_are_identical_on_both_interpreters() -> None:
    """The whole corpus's quote output (both views) has one digest, so no rule moves."""
    rows: dict[str, list[object]] = {}
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        rows[stem] = [
            resolve.all_quote_boundary_rows(
                raw, result, max_depth=l1.HTML_MAX_DEPTH, max_elements=l1.HTML_MAX_ELEMENTS
            ),
            resolve.all_view_level_rows(
                raw, result, max_depth=l1.HTML_MAX_DEPTH, max_elements=l1.HTML_MAX_ELEMENTS
            ),
        ]
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
    assert len(rows) == 119, len(rows)
    digest = hashlib.sha256(blob).hexdigest()
    assert digest == DOM_ROWS_DIGEST, (
        f"the quote output moved: {digest} != {DOM_ROWS_DIGEST}; if a rule changed on purpose, "
        "record the new digest in docs/design/phase1-empirical.md and bump QUOTE_RULES_VERSION"
    )


# ============================================ the oracle's label-blind html evidence


def test_the_oracle_reports_the_html_rows_label_blind() -> None:
    """The measurers compare the catalogue's html rows, and the evidence never prints a label.

    Turn 1.7's blind run disagreed with the catalogue on eight html rows; the reviewer's adjudication
    (decisions 40-42 as amended in 1.7b) makes the rules agree, so the corpus is green -- the html rows
    are still measured and compared **live**, which the second block pins (a family the oracle did not
    measure would still be green and mean nothing). The evidence format is the comparison's own
    guarantee (``tests/test_quote_resolve.py``), restated here on a planted html row.
    """
    report = l1.check_all(DEFAULT_FIXTURES)
    assert not report.mismatches, report.mismatches

    # The html rows are live: the measured rows carry the html view.
    measured_html = 0
    for _stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        measured_html += sum(
            1
            for row in resolve.all_quote_boundary_rows(
                raw, result, max_depth=l1.HTML_MAX_DEPTH, max_elements=l1.HTML_MAX_ELEMENTS
            )
            if row[1] == "html"
        )
    assert measured_html > 0, "no html row is measured; a green corpus would be vacuous"

    # The evidence names the view, the row and the column's NAME plus the MEASURED value, never a
    # labelled one (independence rule 3).
    compare = l1._quote_rows_compare("body.quote_boundaries")
    agrees, detail = compare(
        [["1.2", "html", "gmail_quote", "quote", 1, [0], 9, 999]],
        [["1.2", "html", "gmail_quote", "quote", 1, [0], 9, 65]],
    )
    assert agrees is False and detail is not None, detail
    assert "view 'html' row 0: column 'span_length' -- measured 65" in detail, detail
    assert "the labelled value is never printed" in detail, detail
    assert "999" not in detail, "a labelled value must never appear in the evidence"


def test_the_html_gaps_are_not_wired_into_the_oracle() -> None:
    """The DOM gap triggers are implemented and reported, not wired into ``gaps.later`` (32)."""
    # The tree's unclosed-container gap rides the walker's channel already (Turn 1.5b); the DOM
    # vendor-family trigger is the same id and is NOT separately wired.
    assert dom_rules.GAP_BODY_HTML_QUOTE_RULE_GAP == l1.selection_stage.htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP
    assert dom_rules.GAP_BODY_HTML_QUOTE_RULE_GAP in l1.LIVE_GAP_IDS
    # The absence answers and the html disagreement are not wired this turn (decision 32).
    assert dom_rules.GAP_BODY_NO_BOUNDARY_FOUND not in l1.LIVE_GAP_IDS
    assert resolve.GAP_VIEW_QUOTE_LEVEL_DISAGREEMENT not in l1.LIVE_GAP_IDS
