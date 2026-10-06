"""The DOM half of the quote rules (Turn 1.7; build-spec decision 3's DOM table).

This is the counterpart of :mod:`emailextract.quote.text_rules`: the same rules
vocabulary, but located on the **HTML view** rather than on the decoded text. The
view of a ``text/html`` part is its **HTML projection** (:mod:`emailextract.htmltext`):
spans are the projection's code points, taken straight from the tree's node-to-span
map (an element's ``projected_offset``/``projected_length`` in
:mod:`emailextract.htmltree`) and **never recomputed from the raw HTML**.

The rule table, each row with the id it is recorded under (the fact's ``rule_id``):

``gmail_quote``
    A ``div`` or a ``blockquote`` whose ``class`` attribute carries the **token**
    ``gmail_quote`` (tokens are space-separated and matched case-sensitively, so
    ``gmail_quote gmail_quote_container`` matches and ``my_gmail_quote_x`` does not).
    One boundary of kind ``quote``. An inner ``blockquote`` (``blockquote.gmail_quote``
    or a bare one) is **part of the container** -- one container, one ordinal -- and the
    Gmail attribution wrapper ``div.gmail_attr`` inside the container adds no second
    ordinal.

``blockquote_type_cite``
    A ``blockquote`` with ``type="cite"`` (the value compared case-insensitively). Kind
    ``quote``. A top-level one is its own boundary; one inside another quote container is
    part of that container (the absorption rule).

``outlook_divrplyfwd``
    An element whose ``id`` is exactly ``divRplyFwdMsg``/``x_divRplyFwdMsg`` (the ``x_``
    prefix is the one Outlook adds on rewrite). Kind ``quote``, level 1. The boundary span
    is the element's own projected extent, exactly, with no final-terminator extension
    (decision 40 as amended in 1.7b).

``outlook_appendonsend``
    An element whose ``id`` is exactly ``appendonsend``/``x_appendonsend``. Kind ``quote``,
    level 1. The marker is a **sentinel** and carries no quoted words (decision 41 as
    amended in 1.7b): the boundary **starts** at the projected offset of the marker's first
    following **element** sibling (the quoted history is the marker's following siblings)
    and **ends** at the end of the marker's parent's projected extent; when the marker has
    no following element sibling the span is the marker's own extent -- possibly zero
    length, kept and never invented away.

``thunderbird_moz_cite_prefix``
    An element with the class token ``moz-cite-prefix`` (the attribution). Kind ``quote``.
    The boundary covers the prefix element **and** its immediately following element sibling
    when that sibling is a ``blockquote`` -- with or without ``type=cite`` (decision 42 as
    amended in 1.7b): one boundary, one ordinal, the pulled-in blockquote adding neither a
    second boundary nor a second ordinal. A following sibling that is not a ``blockquote``
    leaves the boundary at the prefix element alone.

``thunderbird_moz_forward_container``
    An element with the class token ``moz-forward-container``. Kind ``forward`` at **level
    0, ordinal 0** (forwarded content is not the sender's quoted prior words); the span is
    the container element's projected span. A forward container does **not** suppress a
    quote container found inside it (that inner one is still recorded, nested).

``gt_family``
    The ``>``-family prefix depth of the plain view, over the projection's **physical
    lines** (the walker's one line model, run over the UTF-8 encoding of the projection so
    no second splitter exists). One boundary per maximal run of lines with depth >= 1,
    ``prefix_depth`` per line, the span following the same convention the plain view uses
    (a run that reaches the final line keeps that line's terminator).

``body.html_quote_rule_gap``
    A class token starting with ``gmail_``, ``moz-`` or ``yahoo_``, or an id/class
    containing ``RplyFwdMsg``, on an element that is **not** one of the table rows above
    (``gmail_attr`` is the one named helper: it is part of its container's boundary, never
    a gap). Recorded at the part locator; **no boundary is invented for it**. The tree's
    own gap for an **unclosed** quote container
    (:data:`emailextract.htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP`) is the same id and is kept.

``body.no_boundary_found``
    The absence answer: no DOM rule fired, no vendor-family element existed, and the
    projection has no ``>`` prefix line.

Work is counted deterministically on :data:`WORK` -- the
:class:`emailextract.walk.WorkCounter` pattern, a seam a test can reset and read, **never
a clock** -- one step per projection line read, one per element visited and one per class
token examined. The walk is a **loop over the element tuple** (never recursion), so a
100,000-deep nest that the tree already capped is handled, and every lookup is a single
pass or a bisect, so the scan is linear in the tree and the projection.
"""

from __future__ import annotations

import bisect
import codecs
from dataclasses import dataclass
from typing import Final, Iterable

from .. import htmltext
from ..walk import WorkCounter, iter_lines
from . import text_rules

__all__ = [
    "DOM_RULES",
    "DomScan",
    "GAP_BODY_HTML_QUOTE_RULE_GAP",
    "GAP_BODY_NO_BOUNDARY_FOUND",
    "NAMED_HELPERS",
    "RULE_BLOCKQUOTE_TYPE_CITE",
    "RULE_GMAIL_QUOTE",
    "RULE_GT_FAMILY",
    "RULE_OUTLOOK_APPENDONSEND",
    "RULE_OUTLOOK_DIVRPLYFWD",
    "RULE_THUNDERBIRD_MOZ_CITE_PREFIX",
    "RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER",
    "VENDOR_ID_MARKER",
    "VENDOR_PREFIXES",
    "WORK",
    "projection_lines",
    "scan_projection",
    "vendor_family_gap",
]

#: The work counter (the :class:`~emailextract.walk.WorkCounter` pattern): deterministic,
#: resettable and readable, never a clock. A test resets it, scans, and reads it back.
WORK: Final[WorkCounter] = WorkCounter()

#: The rule ids the DOM table can emit (the fact's ``rule_id`` column). ``gt_family`` is
#: shared with the TEXT half: it is the same rule over the projection's physical lines.
RULE_GMAIL_QUOTE: Final[str] = "gmail_quote"
RULE_BLOCKQUOTE_TYPE_CITE: Final[str] = "blockquote_type_cite"
RULE_OUTLOOK_DIVRPLYFWD: Final[str] = "outlook_divrplyfwd"
RULE_OUTLOOK_APPENDONSEND: Final[str] = "outlook_appendonsend"
RULE_THUNDERBIRD_MOZ_CITE_PREFIX: Final[str] = "thunderbird_moz_cite_prefix"
RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER: Final[str] = "thunderbird_moz_forward_container"
RULE_GT_FAMILY: Final[str] = text_rules.RULE_GT_FAMILY

#: The rules whose hits this module can emit, in the order the table states them.
DOM_RULES: Final[tuple[str, ...]] = (
    RULE_GMAIL_QUOTE,
    RULE_BLOCKQUOTE_TYPE_CITE,
    RULE_OUTLOOK_DIVRPLYFWD,
    RULE_OUTLOOK_APPENDONSEND,
    RULE_THUNDERBIRD_MOZ_CITE_PREFIX,
    RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER,
    RULE_GT_FAMILY,
)

#: The class-token prefixes of a **known vendor prefix family** (an id/class containing
#: :data:`VENDOR_ID_MARKER` is the fourth member, checked separately).
VENDOR_PREFIXES: Final[tuple[str, ...]] = ("gmail_", "moz-", "yahoo_")

#: The id/class substring of the Outlook reply/forward family (matched anywhere).
VENDOR_ID_MARKER: Final[str] = "RplyFwdMsg"

#: The Outlook marker ids, exactly: the bare form and the ``x_`` form Outlook adds on rewrite.
OUTLOOK_DIVRPLYFWD_IDS: Final[frozenset[str]] = frozenset({"divRplyFwdMsg", "x_divRplyFwdMsg"})
OUTLOOK_APPENDONSEND_IDS: Final[frozenset[str]] = frozenset({"appendonsend", "x_appendonsend"})

#: The one named helper class token that is **part of a table row** rather than a gap: the
#: Gmail attribution wrapper rule ``gmail_quote`` names ("adds no second ordinal").
NAMED_HELPERS: Final[frozenset[str]] = frozenset({"gmail_attr"})

#: The Thunderbird class **tokens** the table rows are keyed on (distinct from the rule ids).
TOKEN_MOZ_CITE_PREFIX: Final[str] = "moz-cite-prefix"
TOKEN_MOZ_FORWARD_CONTAINER: Final[str] = "moz-forward-container"
TOKEN_GMAIL_QUOTE: Final[str] = "gmail_quote"

#: The gap the known-vendor-prefix-but-no-row trigger records (registry: ``phase0-gaps.md``).
GAP_BODY_HTML_QUOTE_RULE_GAP: Final[str] = "body.html_quote_rule_gap"

#: The absence answer, the same id the TEXT half records from the other side.
GAP_BODY_NO_BOUNDARY_FOUND: Final[str] = text_rules.GAP_NO_BOUNDARY_FOUND


@dataclass(frozen=True)
class DomScan:
    """Everything the DOM family measured for one HTML view, and the absence answers.

    ``boundaries`` are the accepted rule hits in document order (span start order);
    ``gaps`` are the gap ids this scan records (the tree's unclosed-container gap plus the
    vendor-family gap and the absence answer); ``no_boundary`` is the
    :data:`GAP_BODY_NO_BOUNDARY_FOUND` answer; ``max_depth`` is the deepest per-line
    ``>``-family depth in the view and ``has_prefix`` whether any line carries one.
    ``steps`` is the deterministic count read off :data:`WORK` around the scan.
    """

    boundaries: tuple[text_rules.Boundary, ...] = ()
    gaps: tuple[str, ...] = ()
    no_boundary: bool = False
    max_depth: int = 0
    has_prefix: bool = False
    lines: tuple[text_rules.Line, ...] = ()
    steps: int = 0


# ------------------------------------------------------------------ the line model


def _code_point_reader(payload: bytes):
    """A UTF-8 byte-offset -> code-point reader over the projection's own bytes.

    The projection's physical lines are the walker's one line model
    (:func:`emailextract.walk.iter_lines`) over the projection encoded as UTF-8: no code
    point's UTF-8 bytes are ``0x0D``/``0x0A``, so the line breaks are exactly the text's
    (CRLF, LF, lone CR) and mapping the byte offsets back is exact. The reader replays the
    same decode incrementally, one increasing offset at a time (a non-monotonic offset
    restarts it), so the answer stays a function of the projection.
    """
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    state = {"position": 0, "characters": 0}

    def read(offset: int) -> int:
        position = state["position"]
        if offset < position:  # non-monotonic: restart, so the answer is still a function
            decoder.reset()
            state["position"] = 0
            state["characters"] = 0
            position = 0
        state["characters"] += len(decoder.decode(payload[position:offset]))
        state["position"] = offset
        return state["characters"]

    return read


def projection_lines(text: str) -> tuple[text_rules.Line, ...]:
    """The projection's physical lines, with code-point offsets and their ``>`` depths.

    The same one line model the plain view uses, over the projection's UTF-8 bytes; the
    content of each line is sliced out of the projection itself, so ``Line.text`` is in the
    projection's code points. Work is counted on :data:`WORK`, one step per line.
    """
    payload = text.encode("utf-8")
    if not payload:
        return ()
    reader = _code_point_reader(payload)
    lines: list[text_rules.Line] = []
    for index, (start, content_end, term_end) in enumerate(iter_lines(payload, 0, len(payload))):
        WORK.add()
        char_start = reader(start)
        content_end_char = reader(content_end)
        content = text[char_start:content_end_char]
        lines.append(
            text_rules.Line(
                index=index,
                start=char_start,
                content_end=content_end_char,
                term_end=reader(term_end),
                text=content,
                depth=text_rules.prefix_depth(content),
            )
        )
    return tuple(lines)


# ------------------------------------------------------------------ element reading


def _attributes(element) -> dict[str, str]:
    """The element's attributes as a dict, first-wins (the tree keeps duplicates)."""
    result: dict[str, str] = {}
    for name, value in element.attributes:
        if name not in result:
            result[name] = value
    return result


def _tokens(attributes: dict[str, str]) -> tuple[str, ...]:
    """The ``class`` attribute's space-separated tokens (matched case-sensitively)."""
    return tuple(attributes.get("class", "").split())


def _line_of(starts: tuple[int, ...], position: int) -> int:
    """The index of the line containing ``position`` (the last line past the end)."""
    if not starts:
        return 0
    index = bisect.bisect_right(starts, position) - 1
    return index if index >= 0 else 0


def _lines_in_span(
    lines: tuple[text_rules.Line, ...], starts: tuple[int, ...], start: int, end: int
) -> tuple[int, ...]:
    """The projection line indices a span ``[start, end)`` covers.

    A zero-length span covers no line (the element projects nothing), so its
    ``prefix_depth`` is empty rather than a depth for a line the span does not reach.
    """
    if not lines or end <= start:
        return ()
    first = _line_of(starts, start)
    last = _line_of(starts, end - 1)
    if last < first:
        last = first
    return tuple(range(first, last + 1))


def _depths(lines: tuple[text_rules.Line, ...], indices: Iterable[int]) -> tuple[int, ...]:
    return tuple(lines[index].depth for index in indices)


# ------------------------------------------------------------------ rule detection


def _id_of(attributes: dict[str, str]) -> str:
    return attributes.get("id", "")


def _is_blockquote(element, attributes: dict[str, str]) -> bool:
    """Whether the element is a ``blockquote``, with or without ``type=cite``.

    The ``thunderbird_moz_cite_prefix`` row pulls in its following element sibling when that
    sibling is a ``blockquote`` (decision 42 as amended in 1.7b: real Thunderbird emits
    ``type=cite``, a bare one is the same quoted block).
    """
    return element.tag == "blockquote"


def _is_blockquote_cite(element, attributes: dict[str, str]) -> bool:
    return element.tag == "blockquote" and attributes.get("type", "").strip().lower() == "cite"


def _table_row(element, attributes: dict[str, str], tokens: tuple[str, ...]) -> str | None:
    """The table rule this element matches, or ``None``.

    The order is the table's: ``gmail_quote``, ``blockquote_type_cite``, the two Outlook
    ids and the two Thunderbird class tokens.
    """
    if element.tag in ("div", "blockquote") and TOKEN_GMAIL_QUOTE in tokens:
        return RULE_GMAIL_QUOTE
    if _is_blockquote_cite(element, attributes):
        return RULE_BLOCKQUOTE_TYPE_CITE
    identifier = _id_of(attributes)
    if identifier in OUTLOOK_DIVRPLYFWD_IDS:
        return RULE_OUTLOOK_DIVRPLYFWD
    if identifier in OUTLOOK_APPENDONSEND_IDS:
        return RULE_OUTLOOK_APPENDONSEND
    if TOKEN_MOZ_CITE_PREFIX in tokens:
        return RULE_THUNDERBIRD_MOZ_CITE_PREFIX
    if TOKEN_MOZ_FORWARD_CONTAINER in tokens:
        return RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER
    return None


def vendor_family_gap(attributes: dict[str, str], tokens: tuple[str, ...]) -> bool:
    """Whether an element matches a known vendor prefix family with no table row.

    A class **token** starting with ``gmail_``/``moz-``/``yahoo_``, or an id/class
    containing :data:`VENDOR_ID_MARKER`. This is the trigger of
    :data:`GAP_BODY_HTML_QUOTE_RULE_GAP`; a caller checks the table row first, because an
    element that *is* a row is never a gap.
    """
    if any(token.startswith(prefix) for token in tokens for prefix in VENDOR_PREFIXES):
        return True
    if VENDOR_ID_MARKER in _id_of(attributes):
        return True
    return any(VENDOR_ID_MARKER in token for token in tokens)


def _dom_span(
    lines: tuple[text_rules.Line, ...], starts: tuple[int, ...], start: int, end: int
) -> tuple[int, int]:
    """The DOM boundary's span: the element extent ``[start, end)`` **exactly** (decision 40 as
    amended in 1.7b).

    A DOM boundary is an element's projected extent, nothing else: decision 34's
    final-terminator clause is the **line-based** families' (the plain view's rules and the
    html view's ``gt_family``), and it is deliberately **not** applied here. ``lines`` and
    ``starts`` are kept as the seam a mutation case re-adds the extension through.
    """
    return start, end


def _next_sibling_ordinals(elements) -> dict[int, int]:
    """For each element ordinal, the ordinal of the next element with the same parent."""
    following: dict[int, int] = {}
    last_seen: dict[int | None, int] = {}
    for element in elements:
        parent = element.parent_ordinal
        if parent in last_seen:
            following[last_seen[parent]] = element.ordinal
        last_seen[parent] = element.ordinal
    return following


def _parent_extent_end(elements, by_ordinal, element, projection_length: int) -> int:
    """The end of the marker's parent's projected extent (decision 41's end, amended in 1.7b).

    An **element** parent's own projected extent when there is one; otherwise the marker is a
    top-level element and its parent is the implicit root, whose projected extent is the block
    of top-level **elements** -- trailing text outside every element (the part's last newline)
    is not part of the quoted block. The projection's raw end is the last fallback.
    """
    parent = element.parent_ordinal
    if parent is not None and parent in by_ordinal:
        parent_element = by_ordinal[parent]
        return parent_element.projected_offset + parent_element.projected_length
    ends = [
        item.projected_offset + item.projected_length
        for item in elements
        if item.parent_ordinal is None
    ]
    return max(ends) if ends else projection_length


def _appendonsend_span(
    elements, by_ordinal, next_sibling, projection_length: int, element
) -> tuple[int, int]:
    """The ``appendonsend`` span: from the marker's first following element sibling to the end.

    The marker is a **sentinel** that carries no quoted words, so the span **starts** at the
    projected offset of its first following **element** sibling (decision 41 as amended in
    1.7b) and **ends** at the end of the marker's parent's projected extent. With no following
    element sibling the span is the marker's own extent (zero length kept, never invented
    away).
    """
    sibling = next_sibling.get(element.ordinal)
    if sibling is None:
        return element.projected_offset, element.projected_offset + element.projected_length
    follower = by_ordinal[sibling]
    return follower.projected_offset, _parent_extent_end(
        elements, by_ordinal, element, projection_length
    )


def _candidates(
    elements, by_ordinal, next_sibling, projection_length: int
) -> tuple[list[tuple[str, str, int, int, int]], bool, bool]:
    """``(rule_id, kind, start, end, element_ordinal)`` for every table hit.

    The second value says a DOM rule fired at all; the third says a vendor-family element
    with no row was seen (the :data:`GAP_BODY_HTML_QUOTE_RULE_GAP` trigger).
    """
    found: list[tuple[str, str, int, int, int]] = []
    fired = False
    vendor_gap = False
    for element in elements:
        WORK.add()
        attributes = _attributes(element)
        tokens = _tokens(attributes)
        WORK.add(len(tokens))
        rule = _table_row(element, attributes, tokens)
        if rule is None:
            if vendor_family_gap(attributes, tokens) and not (NAMED_HELPERS & set(tokens)):
                vendor_gap = True
            continue
        fired = True
        start = element.projected_offset
        end = element.projected_offset + element.projected_length
        kind = "quote"
        if rule == RULE_OUTLOOK_APPENDONSEND:
            start, end = _appendonsend_span(
                elements, by_ordinal, next_sibling, projection_length, element
            )
        elif rule == RULE_THUNDERBIRD_MOZ_CITE_PREFIX:
            sibling = next_sibling.get(element.ordinal)
            candidate = by_ordinal.get(sibling) if sibling is not None else None
            if candidate is not None and _is_blockquote(candidate, _attributes(candidate)):
                end = candidate.projected_offset + candidate.projected_length
        elif rule == RULE_THUNDERBIRD_MOZ_FORWARD_CONTAINER:
            kind = "forward"
            # Decision 28: a forward banner spans the banner line **through the end of the
            # part**, so it keeps the final terminator -- unlike an element-extent quote span
            # (decision 40 as amended in 1.7b). The plain forward banner does the same.
            end = projection_length
        found.append((rule, kind, start, end, element.ordinal))
    return found, fired, vendor_gap


def _gt_runs(lines: tuple[text_rules.Line, ...]) -> list[tuple[int, int]]:
    """The maximal runs of consecutive lines with depth >= 1, as ``(first, last)`` pairs."""
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if lines[index].depth < 1:
            index += 1
            continue
        last = index
        while last + 1 < len(lines) and lines[last + 1].depth >= 1:
            last += 1
        runs.append((index, last))
        index = last + 1
    return runs


def _contains(stack: list[tuple[int, int]], start: int, end: int) -> bool:
    """Whether an accepted quote boundary's span contains ``[start, end)``.

    The stack holds the accepted quote boundaries whose start is <= this candidate's, in
    order; because the candidates arrive in span-start order, the enclosing one, if any,
    is the innermost stack entry that still reaches the candidate's start.
    """
    while stack and stack[-1][1] <= start:
        stack.pop()
    return bool(stack) and stack[-1][1] >= end


def _gt_absorbed(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    """Whether a ``>` run lies inside an accepted quote boundary's span (one quote, one ordinal)."""
    return any(first <= start and last >= end for first, last in spans)


def scan_projection(projection: htmltext.HtmlProjection) -> DomScan:
    """Run every DOM rule over one HTML projection, once, in one pass order.

    The tree's elements are visited in document order (never recursion); table hits are
    accepted in span-start order and a quote container inside another quote boundary's
    span is absorbed (one quote, one ordinal). The ``>``-family runs are then added for the
    lines no accepted boundary covers, the boundaries are sorted into document order and
    the absence answers are decided.
    """
    before = WORK.count()
    elements = projection.tree.elements
    by_ordinal = {element.ordinal: element for element in elements}
    next_sibling = _next_sibling_ordinals(elements)
    lines = projection_lines(projection.text)
    starts = tuple(line.start for line in lines)

    candidates, fired, vendor_gap = _candidates(
        elements, by_ordinal, next_sibling, len(projection.text)
    )
    candidates.sort(key=lambda item: (item[2], -item[3], item[0]))

    boundaries: list[text_rules.Boundary] = []
    stack: list[tuple[int, int]] = []
    for rule_id, kind, start, end, _ordinal in candidates:
        start, end = _dom_span(lines, starts, start, end)
        if kind == "quote" and _contains(stack, start, end):
            continue
        indices = _lines_in_span(lines, starts, start, end)
        boundaries.append(
            text_rules.Boundary(
                rule_id=rule_id,
                kind=kind,
                start=start,
                end=end,
                lines=indices,
                prefix_depth=_depths(lines, indices),
            )
        )
        if kind == "quote":
            stack.append((start, end))

    quote_spans = [(item.start, item.end) for item in boundaries if item.kind == "quote"]
    for first, last in _gt_runs(lines):
        run_start = lines[first].start
        run_end = lines[last].term_end if last == len(lines) - 1 else lines[last].content_end
        if _gt_absorbed(quote_spans, run_start, run_end):
            continue
        indices = tuple(range(first, last + 1))
        boundaries.append(
            text_rules.Boundary(
                rule_id=RULE_GT_FAMILY,
                kind="quote",
                start=run_start,
                end=run_end,
                lines=indices,
                prefix_depth=_depths(lines, indices),
            )
        )

    boundaries.sort(key=lambda item: (item.start, item.end, item.rule_id))

    has_prefix = any(line.depth >= 1 for line in lines)
    max_depth = max((line.depth for line in lines), default=0)
    no_boundary = not fired and not vendor_gap and not has_prefix

    gaps: list[str] = []
    for gap in (
        *projection.tree.gaps,
        GAP_BODY_HTML_QUOTE_RULE_GAP if vendor_gap else None,
        GAP_BODY_NO_BOUNDARY_FOUND if no_boundary else None,
    ):
        if gap is not None and gap not in gaps:
            gaps.append(gap)

    return DomScan(
        boundaries=tuple(boundaries),
        gaps=tuple(gaps),
        no_boundary=no_boundary,
        max_depth=max_depth,
        has_prefix=has_prefix,
        lines=lines,
        steps=WORK.count() - before,
    )
