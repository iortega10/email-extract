"""The text half of the resolution rule (Turn 1.6; build-spec decision 2, signed Q2/Q3).

This module turns :mod:`emailextract.quote.text_rules`' hits into the two frozen fact shapes,
and it owns the **derived** quantities decision 2 defines:

``ordinal``
    Only ``kind = quote`` boundaries advance the ordinal (1, 2, ... in document order within
    the view); ``forward``, ``signature``, ``list_footer`` and ``unknown`` carry 0. The order is
    the boundary's span start, so a nested reply counts outward-in.

``quote_level`` (a derived rank, never averaged)
    The view's level is the **highest** of any boundary's ordinal and the deepest per-line
    ``>`` depth in the view: ``level = ordinal`` where a structural ``quote`` rule fired in the
    span, else ``level = prefix_depth``. It carries the ``rule_id`` that resolved it (decision
    37), so no consumer has to re-derive it and nothing may threshold its magnitude (``new`` =
    0, ``quoted`` >= 1, ``full`` = all are the only tests).

``resolution_rule_id``
    The rule of the **first structural quote boundary** (any ``quote``-kind boundary whose rule
    is not ``gt_family``) in document order; else ``gt_family`` when the view has a quote run;
    else, when the view has boundaries but no quote boundary, the rule of the **first boundary
    of any kind** (a forward banner, the original-message dashes, a signature, a list footer).

``view.quote_level_disagreement``
    Recorded iff the view has a prefix line (depth >= 1 **anywhere**) **and** a structural
    ``quote`` ordinal >= 1 **and** the two resolved ranks differ. An all-zero depth beside a
    fired structural rule is a **normal state**, never a disagreement -- the measured
    Gmail-reply-quoting-Outlook case, where the plain alternative carries no ``>` `` at all.

A view with **any** recognised boundary has a ``body.view_levels`` row, its level 0 when every
boundary is a forward banner, the original-message dashes, a signature or a list footer
(decision 38); a view with **no** boundary at all -- nothing fired and no ``>`` line -- has no
row. A boundary of kind forward, signature or list_footer therefore reads as level 0 without
inventing a level (decision 15: the forward banner reads as level 0).

The absence answers ride the gap channel and are **not** wired into the oracle's
``gaps.later`` this turn: ``body.no_boundary_found`` fires for every text/plain view with no
rule and no prefix line, which is most of the corpus, so wiring it would turn a corpus-wide
addition into gate noise before the reviewer adjudicates the catalogue. The functions here
are what a caller (Turn 1.7's DOM half beside it, then the assembly turn) records with.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from .. import htmltext
from .. import text as text_stage
from ..model import BoundaryKind, QuoteBoundary, ViewLevel
from ..timeevent import Span
from ..walk import PartShape, WalkResult
from . import dom_rules, text_rules

__all__ = [
    "GAP_VIEW_QUOTE_LEVEL_DISAGREEMENT",
    "VIEW_HTML",
    "VIEW_PLAIN",
    "HtmlViewScan",
    "ViewRecord",
    "ViewScan",
    "all_quote_boundary_rows",
    "all_view_level_rows",
    "all_views",
    "disagreement",
    "gap_pairs",
    "html_gap_pairs",
    "html_views",
    "plain_views",
    "quote_boundary_rows",
    "quote_records",
    "scan_html_view",
    "scan_html_views",
    "scan_views",
    "view_level_rows",
    "view_records",
]

#: The view ids (``model.BodyView``): the TEXT family measures ``plain``; the DOM family
#: (Turn 1.7) measures ``html``, and this turn reports an ``html`` label row as a row of a
#: later turn rather than measuring it.
VIEW_PLAIN: Final[str] = "plain"
VIEW_HTML: Final[str] = "html"

#: The gap the resolution predicate records (``docs/design/phase0-gaps.md``, ``## view``).
GAP_VIEW_QUOTE_LEVEL_DISAGREEMENT: Final[str] = "view.quote_level_disagreement"


@dataclass(frozen=True)
class ViewScan:
    """One plain view: its part, its text, its lines, its hits and the derived level."""

    part: PartShape
    part_text: text_stage.PartText
    view: str
    scan: text_rules.ScanResult
    boundaries: tuple[QuoteBoundary, ...]
    level: ViewLevel | None
    disagreement: bool


def _media(part: PartShape) -> str:
    """The part's media type, exactly as the walker parsed it (parameters dropped)."""
    return (part.content_type or "").strip().lower()


def plain_views(raw: bytes, result: WalkResult) -> tuple[tuple[PartShape, text_stage.PartText], ...]:
    """Every ``text/plain`` view of the message, in part order.

    The walker's own text-part decision is reused, never widened: a part has a text record
    only when the charset ladder ran over it (:func:`emailextract.text.analyse_part`), and the
    view is ``plain`` only when the parsed media type is ``text/plain`` (``model.BodyView``).
    """
    views: list[tuple[PartShape, text_stage.PartText]] = []
    for part in result.parts:
        record = text_stage.analyse_part(raw, part)
        if record is None or _media(part) != "text/plain":
            continue
        views.append((part, record))
    return tuple(views)


def _ordinals(boundaries: Sequence[text_rules.Boundary]) -> list[int]:
    """The ordinal of each boundary: 1, 2, ... over ``kind = quote`` only, else 0."""
    ordinals: list[int] = []
    quote_rank = 0
    for boundary in boundaries:
        if boundary.kind == BoundaryKind.QUOTE.value:
            quote_rank += 1
            ordinals.append(quote_rank)
        else:
            ordinals.append(0)
    return ordinals


def disagreement(max_quote_ordinal: int, max_depth: int) -> bool:
    """The ``view.quote_level_disagreement`` predicate (decision 2), as a pure function.

    True iff the view has a prefix line (``max_depth >= 1``) **and** a structural quote
    ordinal (``>= 1``) **and** the two resolved ranks differ. An all-zero depth beside a
    fired structural rule is normal and never a disagreement.
    """
    if max_depth < 1 or max_quote_ordinal < 1:
        return False
    return max_depth != max_quote_ordinal


def _resolution_rule(boundaries: Sequence[QuoteBoundary]) -> str:
    """The ``rule_id`` that determined the view's level (decisions 37 and 38).

    The rule of the **first structural quote boundary** (any ``quote``-kind boundary whose
    rule is not ``gt_family``) in document order; else ``gt_family`` when the view has a
    quote run; else, when the view has boundaries but no quote boundary, the rule of the
    **first boundary of any kind** (a forward banner, the original-message dashes, a
    signature, a list footer).
    """
    structural = [
        boundary
        for boundary in boundaries
        if boundary.kind == BoundaryKind.QUOTE.value
        and boundary.rule_id != text_rules.RULE_GT_FAMILY
    ]
    if structural:
        return structural[0].rule_id
    if any(boundary.kind == BoundaryKind.QUOTE.value for boundary in boundaries):
        return text_rules.RULE_GT_FAMILY
    if boundaries:
        return boundaries[0].rule_id
    return text_rules.RULE_GT_FAMILY


def scan_view(raw: bytes, part: PartShape, part_text: text_stage.PartText) -> ViewScan:
    """Scan one plain view: hits, ordinals, the derived level and the disagreement."""
    model = text_rules.view_lines(part_text, part, raw)
    scan = text_rules.scan_view(model.lines, truncated=model.truncated)
    ordinals = _ordinals(scan.boundaries)
    boundaries = tuple(
        QuoteBoundary(
            rule_id=boundary.rule_id,
            kind=BoundaryKind(boundary.kind),
            span=Span(boundary.start, boundary.end),
            ordinal=ordinal,
            prefix_depth=list(boundary.prefix_depth),
        )
        for boundary, ordinal in zip(scan.boundaries, ordinals)
    )
    max_quote = max((boundary.ordinal or 0 for boundary in boundaries), default=0)
    max_depth = max((line.depth for line in model.lines), default=0)
    level: ViewLevel | None = None
    if boundaries or max_quote >= 1 or max_depth >= 1:
        level = ViewLevel(
            view_id=VIEW_PLAIN,
            span=Span(0, len(part_text.text)),
            quote_level=max(max_quote, max_depth),
            resolution_rule_id=_resolution_rule(boundaries),
            disagreement=disagreement(max_quote, max_depth),
        )
    return ViewScan(
        part=part,
        part_text=part_text,
        view=VIEW_PLAIN,
        scan=scan,
        boundaries=boundaries,
        level=level,
        disagreement=disagreement(max_quote, max_depth),
    )


def scan_views(raw: bytes, result: WalkResult) -> tuple[ViewScan, ...]:
    """Every plain view of the message, scanned once."""
    return tuple(scan_view(raw, part, record) for part, record in plain_views(raw, result))


def quote_records(raw: bytes, result: WalkResult) -> tuple[tuple[str, str, QuoteBoundary], ...]:
    """``(part path, view id, record)`` for every text-family boundary, in document order."""
    rows: list[tuple[str, str, QuoteBoundary]] = []
    for view in scan_views(raw, result):
        for boundary in view.boundaries:
            rows.append((view.part.path, view.view, boundary))
    return tuple(rows)


def view_records(raw: bytes, result: WalkResult) -> tuple[tuple[str, str, ViewLevel], ...]:
    """``(part path, view id, record)`` for every plain view that has a level."""
    return tuple(
        (view.part.path, view.view, view.level)
        for view in scan_views(raw, result)
        if view.level is not None
    )


# --------------------------------------------------------------- the HTML (DOM) view

#: The view id of a ``text/html`` part (``model.BodyView``). The DOM family measures it.
#: ``VIEW_HTML`` is re-exported from the top of this module (the plain half names it too).


@dataclass(frozen=True)
class HtmlViewScan:
    """One HTML view: its part, its projection, its DOM hits and the derived level."""

    part: PartShape
    projection: htmltext.HtmlProjection
    scan: dom_rules.DomScan
    boundaries: tuple[QuoteBoundary, ...]
    level: ViewLevel | None
    disagreement: bool

    @property
    def view(self) -> str:
        return VIEW_HTML


@dataclass(frozen=True)
class ViewRecord:
    """One view of either family, in one shape, so the rows can be built in part order."""

    path: str
    view: str
    boundaries: tuple[QuoteBoundary, ...]
    level: ViewLevel | None
    disagreement: bool
    gaps: tuple[str, ...] = ()


def html_views(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> tuple[tuple[PartShape, htmltext.HtmlProjection], ...]:
    """Every ``text/html`` view of the message, in part order.

    The walker's own text decision is reused (:func:`emailextract.text.analyse_part`), and
    the projection is built by :func:`emailextract.htmltext.project` under the caller's
    caps (decision 9: no default here). A part the walker read no text for has nothing to
    project and is skipped.
    """
    views: list[tuple[PartShape, htmltext.HtmlProjection]] = []
    for part in result.parts:
        if _media(part) != "text/html":
            continue
        record = text_stage.analyse_part(raw, part)
        if record is None:
            continue
        projection = htmltext.project(record.text, max_depth=max_depth, max_elements=max_elements)
        views.append((part, projection))
    return tuple(views)


def scan_html_view(part: PartShape, projection: htmltext.HtmlProjection) -> HtmlViewScan:
    """Scan one HTML view: DOM hits, ordinals, the derived level and the disagreement."""
    scan = dom_rules.scan_projection(projection)
    ordinals = _ordinals(scan.boundaries)
    boundaries = tuple(
        QuoteBoundary(
            rule_id=boundary.rule_id,
            kind=BoundaryKind(boundary.kind),
            span=Span(boundary.start, boundary.end),
            ordinal=ordinal,
            prefix_depth=list(boundary.prefix_depth),
        )
        for boundary, ordinal in zip(scan.boundaries, ordinals)
    )
    max_quote = max((boundary.ordinal or 0 for boundary in boundaries), default=0)
    max_depth = scan.max_depth
    level: ViewLevel | None = None
    if boundaries or max_quote >= 1 or max_depth >= 1:
        level = ViewLevel(
            view_id=VIEW_HTML,
            span=Span(0, len(projection.text)),
            quote_level=max(max_quote, max_depth),
            resolution_rule_id=_resolution_rule(boundaries),
            disagreement=disagreement(max_quote, max_depth),
        )
    return HtmlViewScan(
        part=part,
        projection=projection,
        scan=scan,
        boundaries=boundaries,
        level=level,
        disagreement=disagreement(max_quote, max_depth),
    )


def scan_html_views(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> tuple[HtmlViewScan, ...]:
    """Every HTML view of the message, scanned once, in part order."""
    return tuple(
        scan_html_view(part, projection)
        for part, projection in html_views(
            raw, result, max_depth=max_depth, max_elements=max_elements
        )
    )


def all_views(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> tuple[ViewRecord, ...]:
    """Every view of the message -- plain and html -- in **part order**.

    A part is one view (its media type decides which family owns it), so the merged
    sequence is the document order of the views.
    """
    records: dict[str, ViewRecord] = {}
    for view in scan_views(raw, result):
        records[view.part.path] = ViewRecord(
            path=view.part.path,
            view=view.view,
            boundaries=view.boundaries,
            level=view.level,
            disagreement=view.disagreement,
        )
    for view in scan_html_views(raw, result, max_depth=max_depth, max_elements=max_elements):
        records[view.part.path] = ViewRecord(
            path=view.part.path,
            view=VIEW_HTML,
            boundaries=view.boundaries,
            level=view.level,
            disagreement=view.disagreement,
            gaps=view.scan.gaps,
        )
    return tuple(records[part.path] for part in result.parts if part.path in records)


def all_quote_boundary_rows(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> list[list[object]]:
    """The ``body.quote_boundaries`` rows for **both** views, in part order.

    ``[part, view, rule_id, kind, ordinal, [prefix_depth, ...], span_offset, span_length]``
    -- the same frozen eight columns; the html rows carry the DOM family's rule ids.
    """
    return [
        [
            record.path,
            record.view,
            boundary.rule_id,
            boundary.kind.value,
            boundary.ordinal,
            list(boundary.prefix_depth),
            boundary.span.start,
            boundary.span.end - boundary.span.start,
        ]
        for record in all_views(raw, result, max_depth=max_depth, max_elements=max_elements)
        for boundary in record.boundaries
    ]


def all_view_level_rows(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> list[list[object]]:
    """The ``body.view_levels`` rows for **both** views: ``[part, view, level, rule_id]``."""
    return [
        [record.path, record.view, record.level.quote_level, record.level.resolution_rule_id]
        for record in all_views(raw, result, max_depth=max_depth, max_elements=max_elements)
        if record.level is not None
    ]


def html_gap_pairs(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> list[tuple[str, str]]:
    """The HTML family's ``(gap_id, locator)`` pairs, in part order.

    The registry's answers for the html view: ``body.html_quote_rule_gap`` (a vendor
    prefix with no row, or the tree's unclosed container), ``body.no_boundary_found`` (no
    DOM rule, no vendor family, no ``>`` line) and ``view.quote_level_disagreement`` (the
    decision-2 predicate per view). Kept apart from :func:`gap_pairs`, whose output the
    plain-view digest pins.
    """
    pairs: list[tuple[str, str]] = []
    for view in scan_html_views(raw, result, max_depth=max_depth, max_elements=max_elements):
        locator = view.part.path
        for gap in view.scan.gaps:
            pairs.append((gap, locator))
        if view.disagreement:
            pairs.append((GAP_VIEW_QUOTE_LEVEL_DISAGREEMENT, locator))
    return pairs


def quote_boundary_rows(raw: bytes, result: WalkResult) -> list[list[object]]:
    """The ``body.quote_boundaries`` rows for this turn's views (plain only).

    ``[part, view, rule_id, kind, ordinal, [prefix_depth, ...], span_offset, span_length]`` --
    the frozen eight columns of ``docs/design/phase1-facts.md``; the span is in the view's code
    points.
    """
    return [
        [
            path,
            view,
            boundary.rule_id,
            boundary.kind.value,
            boundary.ordinal,
            list(boundary.prefix_depth),
            boundary.span.start,
            boundary.span.end - boundary.span.start,
        ]
        for path, view, boundary in quote_records(raw, result)
    ]


def view_level_rows(raw: bytes, result: WalkResult) -> list[list[object]]:
    """The ``body.view_levels`` rows for this turn's views: ``[part, view, level, rule_id]``."""
    return [
        [path, view, level.quote_level, level.resolution_rule_id]
        for path, view, level in view_records(raw, result)
    ]


def gap_pairs(raw: bytes, result: WalkResult) -> list[tuple[str, str]]:
    """The text family's ``(gap_id, locator)`` pairs, in part order.

    The registry's answers, each on its own condition: ``body.no_boundary_found`` (no rule
    fired **and** no prefix line), ``body.i18n_reply_marker`` (a label-shaped
    unknown-language block directly after a boundary-looking line), 
    ``body.inline_reply_interleaved`` (two or more separate quote runs separated by real text)
    and ``view.quote_level_disagreement`` (the decision-2 predicate).
    """
    pairs: list[tuple[str, str]] = []
    for view in scan_views(raw, result):
        locator = view.part.path
        if view.scan.no_boundary:
            pairs.append((text_rules.GAP_NO_BOUNDARY_FOUND, locator))
        if view.scan.i18n_line is not None:
            pairs.append((text_rules.GAP_I18N_REPLY_MARKER, locator))
        if view.scan.interleaved:
            pairs.append((text_rules.GAP_INLINE_REPLY_INTERLEAVED, locator))
        if view.disagreement:
            pairs.append((GAP_VIEW_QUOTE_LEVEL_DISAGREEMENT, locator))
    return pairs
