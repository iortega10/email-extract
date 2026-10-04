"""Turn 1.5: the HTML projection and the node-to-span map (decision 1, item 2).

The **projection** is the deterministic text a reader sees, in one coordinate space: the
decoded part's code points, **un-normalised** (no CRLF/LF folding), the same space the
``>``-depth spans will use, so "structural wins" has something to win against (decision 1).

The rule, stated once
---------------------

The projection is the concatenation, in document order, of the part's **text nodes**,
verbatim, with the subtrees of ``style``/``script``/``head`` **dropped** and comments
dropped. Nothing else: no element (``<p>``, ``<br>``, ``<img>``) inserts a character, and
whitespace is neither collapsed nor re-wrapped. That is what the frozen labels'
``body.html_spans`` spans imply -- ``p { color: red; }`` and ``var x = 1;`` are absent from
``html_style_and_script``'s spans while the trailing ``\\r\\n`` is present (``body`` covers
12 code points of ``"Hello Ben.\\r\\n"``), an ``<img>`` keeps a **zero-length** span at the
offset of its start tag, and the ``\\r\\n`` between ``<img>`` and ``<img>`` counts. The turn
prompt's *recommended* whitespace-collapse/block-newline rule is **contradicted by the
labels** (an open ``<p>`` adds nothing: ``html_href_img_remote_and_cid``'s ``p`` span is
``[0, 6)`` = ``"Hi Ben"``), so the label-consistent verbatim rule is the one implemented --
reported as a resolution, never bent silently to fit a label.

Character references are decoded in exactly **one** place: the stdlib parser's
``convert_charrefs=True`` (``htmltree``), which keeps every offset a code point of the
already-decoded text. The package therefore never calls :func:`html.unescape` -- calling it
here would decode twice and could split a reference across a text-node boundary.

The node-to-span map
--------------------

For **every** element: ``projected_offset`` and ``projected_length`` in code points of the
projection. A container's span covers its descendants' projected text; an element that
projects nothing has length 0 at the offset where it would sit; spans nest and siblings are
ordered and non-overlapping (that follows from the parse, and is asserted). ``body.html_spans``
rows are ``[part, element_ordinal, tag, projected_offset, projected_length]``, one per
element, in document order. HTML is ``part_level`` for the **byte** side (decision 8: no
within-part byte span for HTML); it is exact only inside this projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from . import htmltree
from .versions import HTMLTEXT_VERSION

__all__ = [
    "DROPPED_SUBTREES",
    "HtmlProjection",
    "PROJECTION_BLOCK_RULE",
    "PROJECTION_DROPPED_RULE",
    "PROJECTION_RULE_ID",
    "PROJECTION_WHITESPACE_RULE",
    "project",
    "project_text",
]

#: The subtrees whose text never reaches the projection: their elements are still recorded
#: (with an empty projected span), only their content is dropped.
DROPPED_SUBTREES: Final[frozenset[str]] = frozenset({"style", "script", "head"})

#: The whitespace rule id: text nodes are verbatim, no collapsing.
PROJECTION_WHITESPACE_RULE: Final[str] = "verbatim"

#: The dropped-set rule id (subtrees and comment content that never reaches the text).
PROJECTION_DROPPED_RULE: Final[str] = "drop=style,script,head,comment"

#: The block rule id: no element inserts a character (no block-boundary or ``<br>`` newline).
PROJECTION_BLOCK_RULE: Final[str] = "noelementtext"

#: The three rule ids as one string: the ``projection`` input of ``HTMLTEXT_VERSION``'s key.
PROJECTION_RULE_ID: Final[str] = "+".join(
    (PROJECTION_WHITESPACE_RULE, PROJECTION_DROPPED_RULE, PROJECTION_BLOCK_RULE)
)


def project_text(data: str) -> str:
    """One text node's contribution to the projection: verbatim (character references are
    already decoded by the parser's ``convert_charrefs=True``; ``html.unescape`` is never
    called anywhere in the package)."""
    return data


@dataclass(frozen=True)
class HtmlProjection:
    """The projection text, its version, and the node-to-span map over the tree."""

    tree: htmltree.HtmlTree
    text: str
    version: str

    @property
    def spans(self) -> tuple[tuple[int, str, int, int], ...]:
        """``(element_ordinal, tag, projected_offset, projected_length)``, document order."""
        return tuple(
            (element.ordinal, element.tag, element.projected_offset, element.projected_length)
            for element in self.tree.elements
        )

    def html_spans_rows(self, part: str) -> list[list[object]]:
        """The ``body.html_spans`` rows for one part locator, in document order."""
        return [element.as_html_spans_row(part) for element in self.tree.elements]

    def element(self, ordinal: int) -> htmltree.Element:
        return self.tree.elements[ordinal]


def project(html_text: str, *, max_depth: int, max_elements: int) -> HtmlProjection:
    """Project one part's decoded HTML text under the caller's caps.

    The tree is built by :func:`emailextract.htmltree.build_tree` with this module's rules;
    the projection is the tree's own text, stamped with :data:`HTMLTEXT_VERSION`, and the
    node-to-span map is read straight off the tree's per-element spans. Never raises on any
    input: caps are recorded, not raised (``htmltree``).
    """
    tree = htmltree.build_tree(
        html_text,
        max_depth=max_depth,
        max_elements=max_elements,
        drop_subtrees=DROPPED_SUBTREES,
        text_filter=project_text,
    )
    return HtmlProjection(tree=tree, text=tree.projection, version=HTMLTEXT_VERSION)
