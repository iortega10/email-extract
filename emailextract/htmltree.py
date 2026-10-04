"""Turn 1.5: the own stack-based HTML element tree (phase1-build-spec decision 1).

The HTML parser is **decided** (Turn 1.0d, ``docs/design/html-parser-experiment.md``):
candidate A, the stdlib :class:`html.parser.HTMLParser` plus **this** stack-based element
tree. ``lxml``/``bs4``/``html5lib`` are not dependencies and are never imported.

What this module is, and what it is not
---------------------------------------

* It is the **element tree**: per element its lowercased tag, its attributes (names
  lowercased, values verbatim, duplicates kept **first-wins** with the duplicate
  recorded), its document-order ordinal, its parent ordinal, and -- because the tree is
  what a DOM quote rule locates itself by -- the **projected-text span** it covers.
* It is **not** the projection: the projection rule (which subtrees are dropped, how a
  text node becomes projection text) is the *caller's* (:mod:`emailextract.htmltext`), and
  it arrives as two required keyword parameters so this module carries no text policy of
  its own. That keeps one direction of dependency: ``htmltext`` imports ``htmltree``.
* The caps are **caller parameters with no defaults** (decision 9): a caller who wants a
  bound passes one, and "untrusted" is the caller's knowledge, not this module's.

The named unclosed-container rule (decision 1)
---------------------------------------------

An unclosed **quote container** is **recorded, never closed**: it stays open to the end of
the input, the tree keeps ``unclosed=True`` on it, its span ends at the end of the
projection, every following text node stays inside that span, and the part records the gap
:data:`GAP_BODY_HTML_QUOTE_RULE_GAP` instead of a synthetic end tag. libxml2's repair
(which auto-closes the element and can move the following text out of the container) is
deliberately not used.

Mis-nesting and stray ends
--------------------------

An end tag closes up to the **nearest matching open element**; the elements it closes on
the way are recorded in ``misnested_closures``, never repaired by reordering. An end tag
with no open match is recorded in ``stray_end_tags`` and ignored. On top of that, the
**implied-end** cases (the HTML optional-end-tag list: ``p``, ``li``, ``dt``/``dd``,
``tr``/``td``/``th``, ``thead``/``tbody``/``tfoot``, ``option``/``optgroup``, and a
block-level start closing an open ``p``) close the open element a start tag implies the end
of.

Caps and the closed reason ids
------------------------------

A cap hit is a **recorded truncated state**, never an exception and never unbounded
recursion (the walk is a loop over a Python stack). The turn prompt names "the existing
``large.cap_*`` family"; **no such family exists in this repo**. The closed reason table
(``emailextract/model.py`` :data:`REASON_TABLE`) offers ``skipped`` reasons
``size_cap``/``total_size_cap``/``depth_cap``/``part_count_cap``/``header_bytes_cap`` and
``truncated`` reasons ``stream_ended_early``/``declared_length_mismatch``/
``cap_hit_mid_stream``, and adding a new id is out of this turn's allow-list. The two caps
are therefore recorded with the closest closed ids, mirroring ``parse.Limits``'
``max_depth``/``max_parts``: :data:`REASON_DEPTH_CAP` for the nesting-depth cap and
:data:`REASON_ELEMENT_COUNT_CAP` for the element-count cap, with the cap kind and the
limit recorded on :class:`Truncation` so a reader is never left guessing. This ambiguity
is reported as a resolution (the "stop and ask" the prompt named) rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Final, Mapping

__all__ = [
    "BLOCK_LEVEL_STARTS",
    "Element",
    "GAP_BODY_HTML_QUOTE_RULE_GAP",
    "HtmlTree",
    "IMPLIED_END",
    "QUOTE_CONTAINER_SELECTORS",
    "REASON_DEPTH_CAP",
    "REASON_ELEMENT_COUNT_CAP",
    "Truncation",
    "VOID_ELEMENTS",
    "build_tree",
    "is_quote_container",
]

#: The closed void-element list (HTML5: an element with no end tag and no children).
VOID_ELEMENTS: Final[frozenset[str]] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)

#: The closed implied-end table: a **start** tag whose arrival ends an open element.
#:
#: Source: the HTML optional-end-tag list (WHATWG HTML "Optional tags"; HTML 4.01 DTD
#: ``%block;`` content models), which the turn prompt names as the closed set
#: ``p, li, dt, dd, tr, td, th, option, thead/tbody/tfoot``. ``optgroup`` is included
#: because it shares ``option``'s table row. A start tag closes the **topmost** open
#: element while that element's tag is in the set.
IMPLIED_END: Final[Mapping[str, frozenset[str]]] = {
    "p": frozenset({"p"}),
    "li": frozenset({"li"}),
    "dt": frozenset({"dt", "dd"}),
    "dd": frozenset({"dt", "dd"}),
    "tr": frozenset({"tr", "td", "th"}),
    "td": frozenset({"td", "th"}),
    "th": frozenset({"td", "th"}),
    "thead": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "tbody": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "tfoot": frozenset({"thead", "tbody", "tfoot", "tr", "td", "th"}),
    "option": frozenset({"option"}),
    "optgroup": frozenset({"option", "optgroup"}),
}

#: Block-level start tags that imply the end of an open ``p`` (HTML 4.01 DTD ``%block;``).
BLOCK_LEVEL_STARTS: Final[frozenset[str]] = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "center",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)

#: The quote containers the experiment document names (Turn 1.0d decision 1): the closed
#: set is ``blockquote``, ``div.gmail_quote`` and ``div#divRplyFwdMsg``. Recorded here as
#: selectors so the "which container" fact is readable, and matched by
#: :func:`is_quote_container`.
QUOTE_CONTAINER_SELECTORS: Final[tuple[str, ...]] = (
    "blockquote",
    "div.gmail_quote",
    "div#divRplyFwdMsg",
)

#: The gap the named unclosed-container rule records (registered in ``phase0-gaps.md``).
GAP_BODY_HTML_QUOTE_RULE_GAP: Final[str] = "body.html_quote_rule_gap"

#: The closed reason id for the nesting-depth cap hit (``parse.Limits.max_depth``).
REASON_DEPTH_CAP: Final[str] = "depth_cap"

#: The closed reason id for the element-count cap hit (``parse.Limits.max_parts`` analogue).
REASON_ELEMENT_COUNT_CAP: Final[str] = "part_count_cap"


def is_quote_container(tag: str, attributes: tuple[tuple[str, str], ...]) -> bool:
    """True for the closed quote-container set (:data:`QUOTE_CONTAINER_SELECTORS`)."""
    if tag == "blockquote":
        return True
    if tag != "div":
        return False
    for name, value in attributes:
        if name == "class" and "gmail_quote" in value.split():
            return True
        if name == "id" and value == "divRplyFwdMsg":
            return True
    return False


@dataclass(frozen=True)
class Element:
    """One element of the tree, in its recorded shape.

    ``projected_offset``/``projected_length`` are code points into the caller's projection
    (``htmltext``'s), the same coordinate space the ``>``-depth spans use. A container's
    span covers its descendants' projected text; an element that projects nothing keeps a
    zero-length span **at the offset where it would sit**.
    """

    ordinal: int
    tag: str
    attributes: tuple[tuple[str, str], ...]
    parent_ordinal: int | None
    projected_offset: int
    projected_length: int
    unclosed: bool
    quote_container: bool

    @property
    def projected_end(self) -> int:
        return self.projected_offset + self.projected_length

    def as_html_spans_row(self, part: str) -> list[object]:
        """The ``body.html_spans`` row: ``[part, element_ordinal, tag, offset, length]``."""
        return [part, self.ordinal, self.tag, self.projected_offset, self.projected_length]


@dataclass(frozen=True)
class Truncation:
    """A cap hit, recorded: the closed reason id, the limit and the ordinal reached."""

    reason_id: str
    limit: int
    at_ordinal: int


@dataclass(frozen=True)
class HtmlTree:
    """The element tree over one part's decoded HTML text, plus what was recorded.

    ``elements`` is in document order (``ordinal`` 0 is the first start tag). ``gaps`` are
    the Phase 1 gap ids this tree emits -- only
    :data:`GAP_BODY_HTML_QUOTE_RULE_GAP`, deduplicated, in first-occurrence order -- and
    ride in the Phase 1 gap channel, never the walker's Phase 0 ``part.gaps``.
    """

    elements: tuple[Element, ...]
    projection: str
    gaps: tuple[str, ...]
    truncation: Truncation | None
    stray_end_tags: tuple[str, ...]
    misnested_closures: tuple[int, ...]
    duplicate_attributes: tuple[tuple[int, str], ...]
    unclosed_ordinals: tuple[int, ...]


class _Truncated(Exception):
    """Internal: the cap was hit; unwinds ``feed`` without escaping the module."""


class _Node:
    """The mutable build-time element; :class:`Element` is the frozen record."""

    __slots__ = (
        "attributes",
        "closed",
        "drops",
        "end",
        "ordinal",
        "parent",
        "quote_container",
        "start",
        "tag",
        "unclosed",
    )

    def __init__(
        self,
        tag: str,
        attributes: tuple[tuple[str, str], ...],
        parent: "_Node | None",
        ordinal: int,
        start: int,
        quote_container: bool,
        drops: bool,
    ) -> None:
        self.tag = tag
        self.attributes = attributes
        self.parent = parent
        self.ordinal = ordinal
        self.start = start
        self.end = start
        self.closed = False
        self.unclosed = False
        self.quote_container = quote_container
        self.drops = drops


class _TreeBuilder(HTMLParser):
    """``HTMLParser`` plus the stack tree; every traversal is a loop, never recursion."""

    def __init__(
        self,
        *,
        max_depth: int,
        max_elements: int,
        drop_subtrees: frozenset[str],
        text_filter: Callable[[str], str],
    ) -> None:
        # ``convert_charrefs=True`` is what keeps offsets trackable: a character
        # reference is resolved *once*, by the parser, so every offset this tree records
        # is a code point of the decoded projection. The package never calls
        # ``html.unescape`` (`htmltext` states the same rule from the other side).
        super().__init__(convert_charrefs=True)
        self._max_depth = max_depth
        self._max_elements = max_elements
        self._drop_subtrees = drop_subtrees
        self._text_filter = text_filter
        self._root = _Node("#document", (), None, -1, 0, False, False)
        self._stack: list[_Node] = [self._root]
        self._chunks: list[str] = []
        self._length = 0
        self._skip = 0
        self._nodes: list[_Node] = []
        self._truncation: Truncation | None = None
        self._stray: list[str] = []
        self._misnested: list[int] = []
        self._duplicates: list[tuple[int, str]] = []
        self._unclosed: list[int] = []

    # ------------------------------------------------------------------ the parser

    def handle_starttag(self, tag: str, attrs) -> None:
        self._start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._start(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        if self._truncation is not None:
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                while len(self._stack) > index:
                    node = self._stack.pop()
                    if not node.closed:
                        if node.tag != tag:
                            # an element the end tag closed on the way is mis-nested:
                            # recorded, never repaired by reordering.
                            self._misnested.append(node.ordinal)
                        self._close(node)
                return
        self._stray.append(tag)

    def handle_data(self, data: str) -> None:
        if self._truncation is not None or self._skip:
            return
        projected = self._text_filter(data)
        if projected:
            self._chunks.append(projected)
            self._length += len(projected)

    # Declarations, processing instructions and comments carry no projected text, and the
    # character-reference callbacks never fire under ``convert_charrefs=True``.

    def _start(self, tag: str, attrs, *, self_closing: bool) -> None:
        if self._truncation is not None:
            return
        duplicates, pairs = self._attributes(attrs)
        self._apply_implied_end(tag)
        void = self_closing or tag in VOID_ELEMENTS
        if not void and len(self._stack) - 1 >= self._max_depth:
            self._truncation = Truncation(
                REASON_DEPTH_CAP, self._max_depth, len(self._nodes)
            )
            raise _Truncated
        if len(self._nodes) >= self._max_elements:
            self._truncation = Truncation(
                REASON_ELEMENT_COUNT_CAP, self._max_elements, len(self._nodes)
            )
            raise _Truncated
        node = _Node(
            tag,
            pairs,
            self._stack[-1],
            len(self._nodes),
            self._length,
            is_quote_container(tag, pairs),
            tag in self._drop_subtrees,
        )
        self._nodes.append(node)
        for name in duplicates:
            self._duplicates.append((node.ordinal, name))
        if void:
            node.end = node.start
            node.closed = True
            return
        self._stack.append(node)
        if node.drops:
            self._skip += 1

    def _attributes(self, attrs) -> tuple[list[str], tuple[tuple[str, str], ...]]:
        """First-wins attribute pairs (names lowercased by the parser, values verbatim)."""
        seen: set[str] = set()
        pairs: list[tuple[str, str]] = []
        duplicates: list[str] = []
        for name, value in attrs:
            lowered = name.lower()
            if lowered in seen:
                duplicates.append(lowered)
                continue
            seen.add(lowered)
            pairs.append((lowered, "" if value is None else value))
        return duplicates, tuple(pairs)

    def _apply_implied_end(self, tag: str) -> None:
        closes = IMPLIED_END.get(tag, frozenset())
        if tag in BLOCK_LEVEL_STARTS:
            closes = closes | frozenset({"p"})
        if not closes:
            return
        while len(self._stack) > 1 and self._stack[-1].tag in closes:
            self._close(self._stack.pop())

    def _close(self, node: _Node) -> None:
        node.end = self._length
        node.closed = True
        if node.drops:
            self._skip -= 1

    def finalize(self) -> None:
        """Close the walk: every element still open is recorded ``unclosed``, not closed."""
        while len(self._stack) > 1:
            node = self._stack.pop()
            if not node.closed:
                node.end = self._length
                node.unclosed = True
                self._unclosed.append(node.ordinal)
                if node.drops:
                    self._skip -= 1
        self._root.end = self._length

    def html_tree(self) -> HtmlTree:
        elements = tuple(
            Element(
                ordinal=node.ordinal,
                tag=node.tag,
                attributes=node.attributes,
                parent_ordinal=_parent_ordinal(node),
                projected_offset=node.start,
                projected_length=node.end - node.start,
                unclosed=node.unclosed,
                quote_container=node.quote_container,
            )
            for node in self._nodes
        )
        gaps: list[str] = []
        for node in self._nodes:
            if (
                node.unclosed
                and node.quote_container
                and GAP_BODY_HTML_QUOTE_RULE_GAP not in gaps
            ):
                gaps.append(GAP_BODY_HTML_QUOTE_RULE_GAP)
        return HtmlTree(
            elements=elements,
            projection="".join(self._chunks),
            gaps=tuple(gaps),
            truncation=self._truncation,
            stray_end_tags=tuple(self._stray),
            misnested_closures=tuple(self._misnested),
            duplicate_attributes=tuple(self._duplicates),
            unclosed_ordinals=tuple(self._unclosed),
        )


def _parent_ordinal(node: _Node) -> int | None:
    parent = node.parent
    if parent is None or parent.ordinal < 0:
        return None
    return parent.ordinal


def build_tree(
    text: str,
    *,
    max_depth: int,
    max_elements: int,
    drop_subtrees: frozenset[str],
    text_filter: Callable[[str], str],
) -> HtmlTree:
    """Parse ``text`` into an :class:`HtmlTree` under the caller's caps and text policy.

    All four keywords are required: the caps are caller parameters with **no defaults**
    (decision 9), and the projection policy belongs to the caller (``htmltext``) so this
    module is the tree and nothing else. It never raises on any input: a cap hit unwinds
    to a recorded :class:`Truncation`, and the walk is a loop over a Python stack.
    """
    if not isinstance(text, str):
        raise TypeError(f"build_tree expects decoded text (str), got {type(text).__name__}")
    builder = _TreeBuilder(
        max_depth=max_depth,
        max_elements=max_elements,
        drop_subtrees=drop_subtrees,
        text_filter=text_filter,
    )
    try:
        builder.feed(text)
    except _Truncated:
        pass
    builder.close()
    builder.finalize()
    return builder.html_tree()
