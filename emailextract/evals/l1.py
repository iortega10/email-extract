"""The L1 exact oracle: the skeleton walker's output against the sidecar's labels (Turn 0.4).

L1 is the cheapest level in the eval ladder (D11): the facts a reader can measure from the
fixture bytes with the phase-0 components that exist. Here that is the **skeleton walker**
(``emailextract.walk``): ``container.sha256``, ``container.size_bytes``, ``headers.fields``,
``part.tree``, ``part.regions``, ``part.gaps``, ``body.preamble_epilogue``,
``body.content_sha256`` and ``decode.chain``. Each is measured from the walker's result and
compared, by equality, with the hand-typed value in the sidecar beside the fixture.

A fact whose phase has not shipped (``attach.manifest``, ``body.selection``,
``headers.decoded``, ``gaps.later``, every ``time.*`` fact, ``thread.claims``) is
**declared** in :data:`FACTS` with its phase and no measurer, so a sidecar labelling it is
reported ``not_yet`` with that phase -- never skipped silently. A label naming a fact the
oracle does not model at all is a hard failure (:class:`OracleError`), because a green run
over an unmodelled label would mean nothing.

The independence rule (D11): the labels were typed from the design rules and the fixture's
declared shape, never read out of the walker. So where a label and the walker disagree the
oracle **reports a mismatch** -- it is a finding about one of the two sides, never something
to reconcile by editing a label (``tests/test_label_structure.py`` and the Turn 0.4 report
carry the disagreements found over the committed corpus). ``emailextract.evals.labels`` still
imports nothing from this package; only this module imports the walker.

The oracle measures two facts about the labels rather than the message:

* ``container.sha256`` and ``container.size_bytes`` read the bytes and the walker's own hash;
* ``body.preamble_epilogue`` is a **sparse** fact -- a sidecar names only the parts it wants
  to assert (a leaf cannot hold preamble or epilogue bytes), so the comparison here is
  "every asserted row is right, and no part with non-zero preamble/epilogue is left out",
  not plain equality. This matches the convention the Turn 0.3 sidecars use
  (``plain_simple`` asserts only part ``1`` while ``preamble_epilogue`` asserts two parts);
* ``labels.undetermined`` is a **harness** fact: it names the questions the labels leave
  open, so this oracle measures it against the sidecar's own list (the structural tests and
  ``docs/design/label-questions.md`` decide whether the entries are shaped right).
"""

from __future__ import annotations

import enum
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Final, Mapping

from .. import attach as attach_stage
from .. import dates as date_stage
from .. import headers as header_stage
from .. import selection as selection_stage
from .. import text as text_stage
from ..container import EmlContainer
from ..parse import Limits
from ..walk import WalkResult, walk
from .labels import DEFAULT_FIXTURES, Fact, Sidecar, load_sidecar, load_sidecars

__all__ = [
    "CURRENT_PHASE",
    "FACTS",
    "FACT_PHASES",
    "Measured",
    "Measure",
    "OracleError",
    "Outcome",
    "Report",
    "Status",
    "check",
    "check_all",
    "check_path",
    "deferral_counts",
]

#: The phase this package claims to be at. Bumping it is what turns "not yet measurable"
#: facts into facts the gate compares, and it moves with the build, in the same commit as
#: the code that makes them measurable.
CURRENT_PHASE = 0


def _span(raw_span) -> list[int]:
    """``[offset, length]`` -- the shape every span takes in a sidecar."""
    return [raw_span.offset, raw_span.length]


# ------------------------------------------------------------------ measuring


@dataclass(frozen=True)
class Measured:
    """One fixture, walked once, ready to be measured fact by fact.

    ``result`` is the walker's output, or ``None`` when walking raised: a broken
    measurement is reported ``unmeasurable`` per fact, never allowed to escape as a crash.
    ``raw`` is the fixture's bytes (read once), the address space every span points into.
    """

    sidecar: Sidecar
    result: WalkResult | None
    raw: bytes = b""
    problem: str | None = None

    def walked(self) -> WalkResult:
        """The walker's result, or raise the failure walking produced (reported per fact)."""
        if self.result is None:
            raise RuntimeError(self.problem or "the walker produced no result")
        return self.result

    @property
    def parts(self):
        return self.walked().parts


def _container_sha256(measured: Measured) -> str:
    """The message id the walker measured: sha256 over the raw container bytes (D14)."""
    return measured.walked().container_hash


def _container_size_bytes(measured: Measured) -> int:
    """The address space every recorded span points into."""
    return measured.walked().total_bytes


def _headers_fields(measured: Measured) -> list[list[Any]]:
    """The top-level part's header fields, in order: ordinal, name, verbatim value, status, spans."""
    parts = measured.parts
    fields = parts[0].header_fields if parts else []
    return [
        [
            item.ordinal,
            item.name,
            item.raw_value,
            item.parse_status,
            _span(item.name_span),
            _span(item.value_span),
            _span(item.raw_span),
        ]
        for item in fields
    ]


def _part_tree(measured: Measured) -> list[list[Any]]:
    """Every part: path, parent path, content type, raw span, headers span, body span."""
    return [
        [
            part.path,
            part.parent_path,
            part.content_type,
            _span(part.raw_span),
            _span(part.headers_span),
            _span(part.body_span),
        ]
        for part in measured.parts
    ]


def _part_regions(measured: Measured) -> list[list[Any]]:
    """Every accounted region: kind, path, span (the regions tile the message, D9)."""
    return [[region.kind, region.path, _span(region.span)] for region in measured.walked().regions]


def _part_gaps(measured: Measured) -> list[list[Any]]:
    """Per part, the gap ids the walker recorded, in first-seen order."""
    return [[part.path, list(part.gaps)] for part in measured.parts]


def _preamble_epilogue(measured: Measured) -> list[list[Any]]:
    """Per part, the preamble and epilogue byte counts the walker accounted for."""
    derived = {
        region.path: [0, 0] for region in measured.walked().regions
    }
    for region in measured.walked().regions:
        if region.kind == "preamble":
            derived[region.path][0] += region.span.length
        elif region.kind == "epilogue":
            derived[region.path][1] += region.span.length
    return [[part.path, derived[part.path][0], derived[part.path][1]] for part in measured.parts]


def _decode_chain(measured: Measured) -> list[list[Any]]:
    """Per part: path, declared/used CTE, declared/used charset, fallback_fired, encoding source."""
    return [
        [
            part.path,
            part.decode_chain.declared_cte,
            part.decode_chain.declared_charset,
            part.decode_chain.used_cte,
            part.decode_chain.used_charset,
            part.decode_chain.fallback_fired,
            part.encoding_source.value if part.encoding_source is not None else None,
        ]
        for part in measured.parts
    ]


def _body_content_sha256(measured: Measured) -> list[list[Any]]:
    """Per leaf part with a transfer-decoded body, the sha256 of those bytes."""
    return [
        [part.path, part.body_sha256] for part in measured.parts if part.body_sha256 is not None
    ]


def _labels_undetermined(measured: Measured) -> Any:
    """The labels' own open questions: measured against themselves (a harness fact, see module doc)."""
    return measured.sidecar.facts["labels.undetermined"].value


# ------------------------------------------------ Turn 1.1: the header-stage facts

#: The work budget the oracle hands the RFC 2047 decoder: the caller's own limit
#: (``Limits.max_field_work_units_per_byte``), never a module default the decoder chose.
WORK_UNITS_PER_INPUT_BYTE: Final[int] = Limits.untrusted().max_field_work_units_per_byte

#: The **live** gap ids of Turns 1.1-1.5b: the only ``gaps.later`` rows these turns'
#: components can emit. A label row naming any other id waits for its own turn (``not_yet``).
#: Turn 1.3 adds the three date gaps (``headers.no_date`` / ``headers.invalid_date`` /
#: ``headers.date_no_zone``); Turn 1.4 adds the body stage's ``body.flowed_reflow_unresolved``,
#: all carried in their stage's own gap channel (never the walker's ``part.gaps``). Turn 1.5b
#: adds the selection/HTML stage's four ids; ``body.html_quote_rule_gap`` is the tree's own
#: (Turn 1.5a) and joins the channel when the selection stage carries it. Turn 1.8 adds the
#: attachment stage's eight -- its ``attach.EMITTED_GAP_IDS`` -- and **not**
#: ``attach.cid_dangling``: the frozen ``html_href_img_remote_and_cid`` sidecar references a cid
#: with no matching part (its own annotation names the ``attach_cid_dangling`` case) and types no
#: such row, while ``attach_cid_dangling`` types one, so no live emission of that id can satisfy
#: both. The measured dangling list rides ``attach.Attachments.dangling`` instead, and the row
#: ``attach_cid_dangling`` types stays ``not_yet`` (the turn's finding, reported with its bytes).
LIVE_GAP_IDS: Final[frozenset[str]] = frozenset(
    {
        header_stage.GAP_HEADERS_DUPLICATE_HEADER,
        header_stage.GAP_HEADERS_LEADING_BOM,
        header_stage.GAP_HEADERS_MBOX_FROM_LINE,
        header_stage.GAP_BODY_LONE_CR_LINE_TERMINATOR,
        header_stage.GAP_HEADERS_ENCODED_WORD_INVALID,
        date_stage.GAP_HEADERS_NO_DATE,
        date_stage.GAP_HEADERS_INVALID_DATE,
        date_stage.GAP_HEADERS_DATE_NO_ZONE,
        text_stage.GAP_BODY_FLOWED_REFLOW_UNRESOLVED,
        selection_stage.GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED,
        selection_stage.GAP_BODY_NO_TEXT_PART,
        selection_stage.GAP_SECURITY_REMOTE_CONTENT_PRESENT,
        selection_stage.GAP_BODY_INLINE_DATA_URI,
        selection_stage.htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP,
        *attach_stage.EMITTED_GAP_IDS,
    }
)

#: The turn each deferred ``parsed_value`` column goes live in -- reported by name, never
#: computed here (no stdlib ``parseaddr``/``parsedate`` to make the gate pass). Turn 1.2 made
#: the ``address_list`` scalar live and Turn 1.3 the ``date_time`` scalar, so **no** column is
#: deferred: every ``headers.projection`` row is compared in full.
DEFERRED_PARSED_VALUE_TURNS: Final[Mapping[str, str]] = MappingProxyType({})


def _region(measured: Measured) -> header_stage.HeaderRegion:
    """The message's top-level header region, scanned once per fact (cheap; the walk is done)."""
    return header_stage.header_region(
        measured.raw, measured.walked(), max_work_units=WORK_UNITS_PER_INPUT_BYTE
    )


def _headers_projection(measured: Measured) -> list[list[Any]]:
    """``headers.projection`` rows: raw beside parsed, one row per field (folds kept)."""
    return header_stage.projection_rows(_region(measured))


def _headers_addresses(measured: Measured) -> list[list[Any]]:
    """``headers.addresses`` rows: one entry per address-list field, the tokenizer's rows in it."""
    return header_stage.address_rows(_region(measured))


def _headers_date(measured: Measured) -> list[list[Any]]:
    """``headers.date`` rows: ``[ordinal, raw, zone_state, offset, utc]`` per Date field.

    A message with no Date field is the single absent row the labels type (Turn 1.3).
    """
    return header_stage.date_rows(_region(measured))


def _headers_decoded(measured: Measured) -> list[list[Any]]:
    """``headers.decoded`` rows: ``[ordinal, decoded_text]`` for fields with a decoded word."""
    return header_stage.decoded_rows(_region(measured))


def _headers_parameters(measured: Measured) -> list[list[Any]]:
    """``headers.parameters`` rows for the structured parameters the reader decodes."""
    return header_stage.parameter_rows(measured.raw, _region(measured))


def _gaps_later(measured: Measured) -> list[list[Any]]:
    """``gaps.later`` rows for this turn's live gap ids: ``[gap_id, locator, phase, reason]``.

    The header stage's gaps (Turn 1.1-1.3) and the body stage's (Turn 1.4, the flowed part's
    deferred reflow; Turn 1.5b, the digest/no-text/remote/``data:``/unclosed-quote gaps),
    each from its own channel -- never the walker's ``part.gaps``.
    """
    pairs = [
        *header_stage.later_gaps(_region(measured)),
        *text_stage.body_gaps(measured.raw, measured.walked()),
        *selection_stage.body_gaps(
            measured.raw,
            measured.walked(),
            max_depth=HTML_MAX_DEPTH,
            max_elements=HTML_MAX_ELEMENTS,
        ),
        *attach_stage.gap_pairs(_attachments(measured)),
    ]
    return [[gap_id, locator, 1, ""] for gap_id, locator in pairs]


def _body_text(measured: Measured) -> list[list[Any]]:
    """``body.text`` rows: ``[part, text, verbatim_precision, verbatim_reason]`` per text part.

    A part the walker did not read as text (a multipart, a pdf, a png, an office zip) has no
    row at all -- the walker's own text-part decision, reused, never widened.
    """
    return text_stage.part_text_rows(measured.raw, measured.walked())


# ------------------------------------------- Turn 1.5b: the HTML and selection facts

#: The caller's caps for the HTML projection the oracle runs: the approved untrusted
#: defaults (``Limits.untrusted()``), so the oracle's tree is built under the same bound a
#: real caller would use. ``htmltext.project``/``htmltree.build_tree`` take no default.
HTML_MAX_DEPTH: Final[int] = Limits.untrusted().max_depth
HTML_MAX_ELEMENTS: Final[int] = Limits.untrusted().max_parts


def _html_spans(measured: Measured) -> list[list[Any]]:
    """``body.html_spans`` rows: ``[part, element_ordinal, tag, offset, length]``.

    One row per element of the own tree (``htmltree``/``htmltext``), for every part the
    walker read as ``text/html``, in part-tree then document order -- the ``projected_offset``/
    ``projected_length`` span the element covers in the HTML projection.
    """
    rows: list[list[Any]] = []
    for locator, projection in selection_stage.html_projections(
        measured.raw, measured.walked(), max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS
    ):
        rows.extend(projection.html_spans_rows(locator))
    return rows


def _body_cid_refs(measured: Measured) -> list[list[Any]]:
    """``body.cid_refs`` rows: ``[part, [cid, ...]]`` for parts that reference any cid."""
    return selection_stage.cid_ref_rows(
        measured.raw, measured.walked(), max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS
    )


def _body_alternative_group(measured: Measured) -> list[list[Any]]:
    """``body.alternative_group`` rows: ``[part, group_id]`` for parts inside an alternative."""
    return selection_stage.alternative_group_rows(measured.raw, measured.walked())


def _body_selection(measured: Measured) -> list[list[Any]]:
    """``body.selection`` rows: ``[part, 'selected'|'alternative_not_selected'|'n/a']``.

    The walker carries no selection measurement of its own (Turn 1.5b found none), so this
    is the one measurer; the selection stage is a pure function of the part tree and the
    parts' declared types, never of the content.
    """
    return selection_stage.selection_rows(measured.raw, measured.walked())


def _body_plain_effectively_empty(measured: Measured) -> list[list[Any]]:
    """``body.plain_effectively_empty`` rows: ``[part, emptiness_rule]`` (D16, a fact)."""
    return selection_stage.plain_effectively_empty_rows(measured.raw, measured.walked())


def _attachments(measured: Measured) -> attach_stage.Attachments:
    """The whole attachment stage for this fixture, walked once per fact (cheap; the walk is done).

    The caller's caps for the referenced-cid set are the approved untrusted defaults (decision 9:
    a cap is a caller parameter), and ``limits`` is ``None`` -- the oracle walks **unbounded**
    (``walk(EmlContainer(raw))``), so no cap can have fired and nothing needs re-stating.
    """
    return attach_stage.attachments(
        measured.raw,
        measured.walked(),
        max_depth=HTML_MAX_DEPTH,
        max_elements=HTML_MAX_ELEMENTS,
    )


def _attach_manifest(measured: Measured) -> list[list[Any]]:
    """``attach.manifest`` rows: the occurrences' ``[part, filename, declared_mime, cid, ...]``.

    The walker measures no manifest of its own (Turn 1.8 found none), so this measurer *is* the
    attachment stage's, and the three Phase 0 sidecars that typed the fact stay compared against
    it (the facts document's finding 1: the ``declared_mime`` column is the declared verdict's
    projected value, which is why those labels keep their plain string).
    """
    return attach_stage.manifest_rows(_attachments(measured))


def _attach_types(measured: Measured) -> list[list[Any]]:
    """``attach.types`` rows: the three verdicts, the winner and the disagreement (decision 6)."""
    return attach_stage.type_rows(_attachments(measured))


def _attach_filename(measured: Measured) -> list[list[Any]]:
    """``attach.filename`` rows: the raw filename, its decode state and the recorded fallback."""
    return attach_stage.filename_rows(_attachments(measured))


def _attach_decorative(measured: Measured) -> list[list[Any]]:
    """``attach.decorative`` rows: the decorative hint (``rule_id | null``), never a removal."""
    return attach_stage.decorative_rows(_attachments(measured))


def _attach_cid_use(measured: Measured) -> list[list[Any]]:
    """``attach.cid_use`` rows: the cid and whether any body view references it."""
    return attach_stage.cid_use_rows(_attachments(measured))


def _projection_compare(expected: Any, actual: Any) -> tuple[bool, str | None]:
    """Compare ``headers.projection`` row by row, deferring the parsed scalar by name.

    Columns 0-3 (ordinal, name, raw_value, parsed_kind) are compared for every row; the parsed
    scalar (column 4) is compared for every kind whose parser exists -- ``text``,
    ``message_id``, ``message_id_list``, ``address_list`` (Turn 1.2) and ``date_time``
    (Turn 1.3). :data:`DEFERRED_PARSED_VALUE_TURNS` is now empty, so **every** row's scalar is
    compared in full; a kind deferred by a later turn would still be reported by name here,
    never silently skipped (and never computed with a stdlib parser to make it pass).
    """
    if not isinstance(expected, list) or not isinstance(actual, list):
        return expected == actual, None
    if len(expected) != len(actual):
        return False, f"{len(expected)} labelled row(s), {len(actual)} measured"
    deferred: Counter[str] = Counter()
    for labelled, measured in zip(expected, actual):
        if list(labelled[:4]) != list(measured[:4]):
            return False, f"row {labelled[0]}: labelled {labelled[:4]}, measured {measured[:4]}"
        kind = labelled[3]
        if kind in DEFERRED_PARSED_VALUE_TURNS:
            deferred[kind] += 1
            continue
        if labelled[4] != measured[4]:
            return (
                False,
                f"row {labelled[0]} ({labelled[1]}): parsed_value labelled {labelled[4]!r}, "
                f"measured {measured[4]!r}",
            )
    if not deferred:
        return True, None
    return True, "parsed_value not compared this turn: " + ", ".join(
        f"{count} {kind} row(s) (live in Turn {DEFERRED_PARSED_VALUE_TURNS[kind]})"
        for kind, count in sorted(deferred.items())
    )


def _address_rows_compare(expected: Any, actual: Any) -> tuple[bool, str | None]:
    """Compare ``headers.addresses``: every field entry the label names, exactly.

    The measured value is one entry per **address-list field** (``[ordinal, field_name,
    [address rows]]``). The six Family-A ``address_*`` sidecars label only their ``To``
    field while the fixture also carries an identical ``From`` mailbox (and
    ``headers_plain_baseline`` labels ``From, To, Cc``), so no uniform measurer can include
    the ``From`` row in one and not the other: the comparison is therefore the
    ``body.preamble_epilogue`` sparse-row rule -- **every entry the label names must equal
    its measured entry**, and a measured entry the label does not name is reported, not
    failed. This is a reported finding (the facts doc says a new fact's sidecar names its
    rows in full); the labels stay untouched.

    A wrong span, addr-spec, membership or state inside a labelled field still fails here,
    so the comparison is not vacuous.
    """
    if not isinstance(expected, list) or not isinstance(actual, list):
        return expected == actual, None
    measured: dict[tuple[Any, Any], Any] = {}
    for row in actual:
        if isinstance(row, list) and len(row) >= 3:
            measured[(row[0], row[1])] = row[2]
    for row in expected:
        if not isinstance(row, list) or len(row) < 3:
            return False, f"labelled row is not [ordinal, field_name, [addresses]]: {row!r}"
        key = (row[0], row[1])
        if key not in measured:
            return False, f"{row[1]!r} (ordinal {row[0]}) is not measured"
        if measured[key] != row[2]:
            return False, f"{row[1]!r}: labelled {row[2]}, measured {measured[key]}"
    extra = len(measured) - len({(row[0], row[1]) for row in expected if isinstance(row, list)})
    detail = f"{extra} measured address field(s) the label does not name" if extra > 0 else None
    return True, detail


def _gaps_later_compare(expected: Any, actual: Any) -> tuple[bool, str | None]:
    """Compare ``gaps.later`` on this turn's live ids only; other rows wait for their turn.

    A live row is compared on ``(gap_id, locator, phase)`` -- its ``reason`` is prose the
    package does not write, so it is not compared. A label row naming an id outside
    :data:`LIVE_GAP_IDS` is reported deferred, never silently dropped.
    """
    if not isinstance(expected, list) or not isinstance(actual, list):
        return expected == actual, None
    live = sorted(
        tuple(row[:3]) for row in expected if row and row[0] in LIVE_GAP_IDS
    )
    measured = sorted(tuple(row[:3]) for row in actual)
    if live != measured:
        return False, f"labelled {live}, measured {measured}"
    deferred = sum(1 for row in expected if row and row[0] not in LIVE_GAP_IDS)
    detail = f"{deferred} row(s) name a gap of a later turn (not compared)" if deferred else None
    return True, detail


def _gaps_later_is_deferred(value: Any) -> bool:
    """A ``gaps.later`` label whose every row names a later turn is deferred whole."""
    if not isinstance(value, list):
        return False
    return not any(isinstance(row, list) and row and row[0] in LIVE_GAP_IDS for row in value)


# ----------------------------------------------------------- comparison rules


def _equal(expected: Any, actual: Any) -> bool:
    return expected == actual


def _sparse_rows(expected: Any, actual: Any) -> bool:
    """``body.preamble_epilogue``: the label asserts a subset, and no non-zero part is omitted.

    The sidecars name only the parts whose preamble/epilogue they want to assert (a leaf
    part cannot hold either), so plain equality would call every such label a mismatch. The
    rule is the one the Turn 0.3 sidecars were written to: each row the label names must be
    right, and every part the walker measured a non-zero count for must be named.
    """
    if not isinstance(expected, list) or not isinstance(actual, list):
        return expected == actual
    derived = {row[0]: (row[1], row[2]) for row in actual}
    asserted = set()
    for row in expected:
        path = row[0]
        if derived.get(path) != (row[1], row[2]):
            return False
        asserted.add(path)
    return all(
        not (pre or epi) or path in asserted for path, (pre, epi) in derived.items()
    )


# ------------------------------------------------------------- the registry


@dataclass(frozen=True)
class Measure:
    """How (and when) one fact is measured.

    ``function`` is absent for a fact whose phase has not arrived: the fact is still
    *declared*, with its phase, so a sidecar labelling it is checked for agreement instead
    of being skipped, and so a later phase cannot silently forget it. ``compare`` defaults
    to equality; only a fact whose sidecar convention is not plain equality overrides it
    (a partial comparison returns ``(agrees, detail | None)``).

    ``live`` marks a fact whose measurer has **shipped while its phase has not arrived**:
    ``CURRENT_PHASE`` stays 0, so a declared phase-1 fact is ``not_yet`` -- unless it is
    ``live``, which is how a turn makes a subset of a phase's facts measurable without
    claiming the whole phase. ``defer`` lets a live fact still defer per sidecar (a
    ``gaps.later`` whose every row names a later turn's gap).
    """

    phase: int
    function: Callable[[Measured], Any] | None = None
    compare: Callable[[Any, Any], Any] = _equal
    note: str | None = None
    live: bool = False
    defer: Callable[[Any], bool] | None = None


#: The published fact ids and the phase each becomes checkable at -- the one place allowed
#: to decide that. A label naming an id that is not here is a hard failure (see
#: :func:`check`), not a skipped fact. Kept in one block so the fact list reads as a list.
FACTS: Mapping[str, Measure] = MappingProxyType(
    {
        # Phase 0: what the skeleton walker measures today (D2/D9/D14).
        "container.sha256": Measure(0, _container_sha256),
        "container.size_bytes": Measure(0, _container_size_bytes),
        "headers.fields": Measure(0, _headers_fields),
        "part.tree": Measure(0, _part_tree),
        "part.regions": Measure(0, _part_regions),
        "part.gaps": Measure(0, _part_gaps),
        "body.preamble_epilogue": Measure(
            0,
            _preamble_epilogue,
            compare=_sparse_rows,
            note="[[path, preamble_bytes, epilogue_bytes]]; the label may name a subset "
            "(a leaf cannot hold either), but every non-zero part must be named",
        ),
        "decode.chain": Measure(0, _decode_chain),
        "body.content_sha256": Measure(0, _body_content_sha256),
        # A harness fact, not a message fact: the questions the labels leave open. Labelled
        # phase 0 by the sidecars and measured against themselves; the structure tests and
        # docs/design/label-questions.md own whether the entries are shaped right.
        "labels.undetermined": Measure(
            0,
            _labels_undetermined,
            note="[['<fact id>', '<locator>', '<what is undecided>']] the questions this "
            "sidecar does not settle -- a harness fact (the labels' own review)",
        ),
        # Phase 1: the parser's facts (identity, then body views and the attachment manifest).
        "attach.manifest": Measure(
            1,
            _attach_manifest,
            live=True,
            note="[[part, filename, declared_mime, cid, disposition, transfer_encoding, "
            "content_sha256, size]] the attachment occurrences (D4); the walker measures no "
            "manifest of its own, so this measurer is the attachment stage's (Turn 1.8): "
            "filename is the DECODED name or null, declared_mime is the declared verdict's "
            "projected value (the header's own media type, parameters dropped), cid keeps the "
            "Content-ID header's value, disposition is the header's disposition token or null, "
            "transfer_encoding is the declared CTE or null and size is the decoded payload size",
        ),
        "body.selection": Measure(
            1,
            _body_selection,
            live=True,
            note="[[part, 'selected'|'alternative_not_selected'|'n/a']] the recorded "
            "alternative display rule (D3/D16); the walker measures no selection of its own, so "
            "this measurer is the selection stage's (Turn 1.5b): a group member is "
            "selected/alternative_not_selected by the closed preference order (text/plain, then "
            "text/html, then text/calendar; an effectively-empty text/plain is skipped), and a "
            "displayable text view outside any group is n/a",
        ),
        "headers.decoded": Measure(
            1,
            _headers_decoded,
            live=True,
            note="[[ordinal, decoded_text]] the RFC 2047-decoded header values (live from Turn 1.1)",
        ),
        "gaps.later": Measure(
            1,
            _gaps_later,
            compare=_gaps_later_compare,
            defer=_gaps_later_is_deferred,
            live=True,
            note="[[gap_id, locator, phase, reason]] gaps a later phase records, named so a "
            "later phase cannot mistake silence for agreement; Turn 1.1 compares only its own "
            "live gap ids (headers.duplicate_header / headers.leading_bom / "
            "headers.mbox_from_line / body.lone_cr_line_terminator / "
            "headers.encoded_word_invalid) and defers the rest by name",
        ),
        # Phase 1: the parser's fact ids (Turn 1.0b declaration). Every one is declared
        # here at phase 1 with its exact value shape and **no measurer** until its turn
        # ships, so a sidecar that labels it is reported ``not_yet`` (CURRENT_PHASE is 0)
        # instead of being skipped, and an unmodelled label is still a hard failure.
        "document.axes": Measure(
            1,
            note="[[axis_id, state, reason_id | null], ...] one row per axis the record carries; "
            "axis_id is one of attachment.status/attachment.route/document.times/"
            "document.thread_edges/document.children/document.same_message_candidates (a wildcard "
            "id is banned); state is value|absent|unknown; reason_id is not_built_in_phase1 or "
            "'built' when state=unknown, else null",
        ),
        "headers.projection": Measure(
            1,
            _headers_projection,
            compare=_projection_compare,
            live=True,
            note="[[ordinal, name, raw_value, parsed_kind, parsed_value], ...] raw beside parsed, "
            "one row per field; the raw value keeps its folds (latin-1 view); parsed_kind is "
            "text|address_list|date_time|message_id|message_id_list|unparsed; parsed_value is null "
            "where parsed_kind=unparsed; live from Turn 1.1, and the parsed_value column is compared "
            "for every kind whose parser exists (text/message_id/message_id_list, and address_list "
            "from Turn 1.2 -- date_time is Turn 1.3)",
        ),
        "headers.addresses": Measure(
            1,
            _headers_addresses,
            compare=_address_rows_compare,
            live=True,
            note="[[ordinal, field_name, [[raw_offset, raw_length, display_name, addr_spec, state, "
            "reason_id], ...]], ...]; raw spans are BYTES into the raw message; state is "
            "parsed|group|unparsed; a group's members are the flat rows beside the group row (the "
            "sidecars type them flat) and a zero-member group is one group row; reason_id is null "
            "unless state=unparsed (headers.address_unparsable); IDN and SMTPUTF8 stay verbatim. "
            "Live from Turn 1.2; compared as a sparse-row fact (every field entry the label names "
            "must match -- the Family-A address_* sidecars label only To, a reported finding)",
        ),
        "headers.date": Measure(
            1,
            _headers_date,
            live=True,
            note="[[ordinal, raw, zone_state, offset, utc], ...]; zone_state is "
            "zone_stated|zone_stated_minus_zero|zone_absent; offset is '+HHMM'/'-HHMM' or null; "
            "utc is the RFC 3339 instant or ['unknown', reason_id] (headers.no_date/"
            "headers.invalid_date) -- a missing or invalid date never sorts as an epoch; live "
            "from Turn 1.3; a message with no Date field is the single absent row the labels type",
        ),
        "headers.parameters": Measure(
            1,
            _headers_parameters,
            live=True,
            note="[[ordinal, field_name, parameter, decoded_value, decode_state, fallback_reason], "
            "...] one row per structured parameter (a boundary, a charset, a name, a filename); "
            "decode_state is decoded|fallback|undecodable; fallback_reason is null unless "
            "decode_state=fallback, then encoded_word_in_parameter|empty_charset|"
            "missing_continuation_index|duplicate_continuation_index; live from Turn 1.1",
        ),
        "body.text": Measure(
            1,
            _body_text,
            live=True,
            note="[[part, text, verbatim_precision, verbatim_reason], ...]; verbatim_precision is "
            "exact|part_level; verbatim_reason is null when exact, else cte_not_identity|"
            "multibyte_without_offset_map|decode_fallback; a part_level row carries no within-part "
            "byte span; the coordinate space is the decoded text in code points, un-normalised. "
            "Live from Turn 1.4 (text.py); a part the walker does not read as text has no row",
        ),
        "body.alternative_group": Measure(
            1,
            _body_alternative_group,
            live=True,
            note="[[part, group_id], ...] one row per part inside a multipart/alternative; group_id "
            "is a message-local stable id (the multipart's part locator plus an ordinal). Live "
            "from Turn 1.5b: the locator itself is the message-local ordinal path the frozen "
            "labels type ('1' for the group at part 1, '1.1.1' for the group at part 1.1.1)",
        ),
        "body.html_spans": Measure(
            1,
            _html_spans,
            live=True,
            note="[[part, element_ordinal, tag, projected_offset, projected_length], ...] one row "
            "per element of the own element tree, in document order; the span is the element's span "
            "in the HTML projection (htmltext); live from Turn 1.5b",
        ),
        "body.cid_refs": Measure(
            1,
            _body_cid_refs,
            live=True,
            note="[[part, [cid, ...]], ...] one row per part that references any cid: (an HTML img "
            "src or a href); the list is the de-duplicated set of cids the part references, in "
            "first-occurrence order; the cid comes from the element TREE, never a regex over raw "
            "HTML; live from Turn 1.5b",
        ),
        "body.plain_effectively_empty": Measure(
            1,
            _body_plain_effectively_empty,
            live=True,
            note="[[part, emptiness_rule], ...] one row per text/plain part present but effectively "
            "empty (D16, a FACT not a gap); emptiness_rule is whitespace_only|stub_only, and only "
            "whitespace_only is emitted (no frozen sidecar types stub_only); live from Turn 1.5b",
        ),
        "body.quote_boundaries": Measure(
            1,
            note="[[part, view, rule_id, kind, ordinal, [prefix_depth, ...], span_offset, "
            "span_length], ...] one row per boundary per view; kind is quote|forward|signature|"
            "list_footer|unknown and only kind=quote advances ordinal (the rank within the view); "
            "prefix_depth is per line; span is in the view's code points",
        ),
        "body.view_levels": Measure(
            1,
            note="[[part, view, level, resolution_rule_id], ...] one row per view (not per span); "
            "level is the derived rank and carries the rule that resolved it; ordinal and depth are "
            "stored, never averaged",
        ),
        "attach.types": Measure(
            1,
            _attach_types,
            live=True,
            note="[[part, declared_mime, magic, container_introspection, winner, disagreement], ...] "
            "one row per attachment occurrence; each verdict is a triple [state, value | null, "
            "reason_id | null] with state value|absent|unknown (magic consulted and clean is "
            "['value', 'unrecognized', null]; not computed is ['unknown', null, reason_id] with a "
            "member of the closed magic reason tuple, the zero-length body among them); winner is "
            "magic|declared_mime|container_introspection|null; disagreement is a bool, true iff the "
            "verdicts name two CONTAINER families (Turn 1.8's decision 25: a declared OOXML type "
            "names the zip container it is and a generic application/octet-stream claim names none)",
        ),
        "attach.filename": Measure(
            1,
            _attach_filename,
            live=True,
            note="[[part, filename_raw, decode_state, decoded_value, fallback_reason], ...] one row "
            "per occurrence that carries a filename; filename_raw is the parameter's value as "
            "written (''run.log); decode_state is decoded|fallback|absent|unparsable (absent has no "
            "row); fallback_reason is null unless decode_state=fallback, then "
            "encoded_word_in_parameter|empty_charset|missing_continuation_index|"
            "duplicate_continuation_index (an empty charset is a recorded fallback, never "
            "'unparsable'); live from Turn 1.8",
        ),
        "attach.decorative": Measure(
            1,
            _attach_decorative,
            live=True,
            note="[[part, rule_id | null], ...] one row per attachment occurrence; rule_id is a "
            "recorded hint rule (inline_unreferenced_small_image|inline_unreferenced_tracking_pixel) "
            "or null; the hint never removes an occurrence. Turn 1.8 fires only "
            "inline_unreferenced_tracking_pixel (an inline, unreferenced png/gif whose declared "
            "dimensions are 1x1); inline_unreferenced_small_image is the empty set in Phase 1",
        ),
        "attach.cid_use": Measure(
            1,
            _attach_cid_use,
            live=True,
            note="[[part, cid, referenced], ...] one row per occurrence; cid keeps the Content-ID "
            "header's value (angle brackets included) and referenced is referenced|unreferenced|n/a, "
            "decided against body.cid_refs case-sensitively on the normalised cid (whitespace and one "
            "angle-bracket pair stripped); a cid-less occurrence is ['<part>', null, 'n/a']; live "
            "from Turn 1.8",
        ),
        # Phase 3: threading and time evidence (D7/D15).
        "thread.claims": Measure(
            3, note="[[message_id, [references], parent_claim_or_null]] header edges as claims (needs D7)"
        ),
        "time.evidence": Measure(
            3, note="[<TimeEvent shape, emailextract/timeevent.py>] (D15; needs the time layer)"
        ),
        "time.owner_manifest": Measure(3, note="[[event_id, ...]] the caller's labelled total order (D15)"),
        "time.orders": Measure(
            3, note="[[policy, [event_id], [not_placed]]] the order under each named policy (D15)"
        ),
        "time.unresolved_pairs": Measure(
            3, note="[[event_a, event_b, reason]] every pair of claims that disagrees (D15)"
        ),
        "time.evidence_conflicts": Measure(
            3, note="bool: whether the fixture's evidence conflicts at all (D15)"
        ),
    }
)

#: fact id -> its phase, for callers that report ``not_yet`` by phase.
FACT_PHASES: Mapping[str, int] = MappingProxyType(
    {fact_id: measure.phase for fact_id, measure in FACTS.items()}
)


class OracleError(ValueError):
    """The oracle and the labels disagree about what is being checked.

    Raised for an unmodelled fact id and for a phase disagreement. Both are harness defects:
    with either, a green run would mean nothing, so the oracle refuses to report at all.
    """


class Status(enum.Enum):
    """What happened to one fact."""

    OK = "ok"
    MISMATCH = "mismatch"
    NOT_YET = "not_yet"
    UNMEASURABLE = "unmeasurable"


@dataclass(frozen=True)
class Outcome:
    """One fact, measured (or not) and compared."""

    fact_id: str
    phase: int
    status: Status
    where: str = ""
    expected: Any = None
    actual: Any = None
    detail: str | None = None

    @property
    def failed(self) -> bool:
        """A mismatch, or a measurement that blew up. ``not_yet`` is neither pass nor failure."""
        return self.status in (Status.MISMATCH, Status.UNMEASURABLE)


@dataclass(frozen=True)
class Report:
    """Every outcome for one fixture (or for a whole corpus), plus the verdict."""

    fixture: str
    phase: int
    outcomes: tuple[Outcome, ...] = ()

    @property
    def compared(self) -> int:
        """How many facts were actually measured and compared."""
        return sum(1 for outcome in self.outcomes if outcome.status in (Status.OK, Status.MISMATCH))

    @property
    def not_yet(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is Status.NOT_YET)

    def not_yet_by_phase(self) -> dict[int, int]:
        """``not_yet`` counted by the phase each fact is due at, never as one total."""
        counts: dict[int, int] = {}
        for outcome in self.outcomes:
            if outcome.status is Status.NOT_YET:
                counts[outcome.phase] = counts.get(outcome.phase, 0) + 1
        return counts

    @property
    def failures(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.failed)

    @property
    def mismatches(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.status is Status.MISMATCH)

    @property
    def ok(self) -> bool:
        """Green means *something was compared*, and none of it failed.

        A report that compared nothing is not green: a gate that passes because no label was
        due would stay green through any regression, which is exactly the emptiness the
        ledger and the corpus exist to make visible.
        """
        return self.compared > 0 and not self.failures

    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for outcome in self.outcomes:
            counts[outcome.status.value] += 1
        return counts

    def lines(self) -> list[str]:
        """The report, one line per fact, for a terminal or a log."""
        lines = [f"L1 phase {self.phase}: {self.fixture} ({len(self.outcomes)} fact(s))"]
        for outcome in self.outcomes:
            line = f"  {outcome.status.value:<13} {outcome.fact_id}"
            if outcome.detail:
                line += f" -- {outcome.detail}"
            lines.append(line)
        counts = ", ".join(f"{name}={count}" for name, count in sorted(self.counts().items()))
        lines.append(f"  compared={self.compared} ({counts})")
        lines.append("  ok" if self.ok else "  NOT OK -- see the failures above")
        return lines


def check(sidecar: Sidecar, *, phase: int = CURRENT_PHASE) -> Report:
    """Measure every fact the sidecar labels, at ``phase``.

    Raises :class:`OracleError` if a label is unmodelled or the phases disagree; a measurer
    (or the walk itself) that raises is reported ``unmeasurable`` rather than allowed to
    escape, because "the measurement itself is broken" is a gate failure and has to be
    visible in the report.
    """
    if not isinstance(sidecar, Sidecar):
        raise OracleError(f"check(): {sidecar!r} is not a loaded Sidecar")
    measured = _measure(sidecar)
    outcomes = [_check_one(measured, fact, phase=phase) for fact in _ordered(sidecar)]
    return Report(fixture=sidecar.stem, phase=phase, outcomes=tuple(outcomes))


def check_all(root: Path | str = DEFAULT_FIXTURES, *, phase: int = CURRENT_PHASE) -> Report:
    """Measure every sidecar under ``root`` and merge them into one corpus report."""
    sidecars = load_sidecars(root)
    outcomes = tuple(
        outcome
        for sidecar in sidecars.values()
        for outcome in check(sidecar, phase=phase).outcomes
    )
    return Report(fixture=f"corpus ({len(sidecars)} sidecar(s))", phase=phase, outcomes=outcomes)


def check_path(
    path: Path | str, *, phase: int = CURRENT_PHASE
) -> Report:
    """Convenience: load one sidecar from a path and check it."""
    return check(load_sidecar(path), phase=phase)


def deferral_counts(root: Path | str = DEFAULT_FIXTURES) -> dict[str, int]:
    """How many ``parsed_value`` columns the live ``headers.projection`` left **deferred**.

    Keyed ``headers.projection.<kind>:<turn>`` so the gate can print the counts by name:
    a ``parsed_value`` comparison deferred to a later turn is reported, never skipped.
    """
    counts: Counter[str] = Counter()
    for sidecar in load_sidecars(root).values():
        fact = sidecar.facts.get("headers.projection")
        if fact is None or not isinstance(fact.value, list):
            continue
        for row in fact.value:
            if isinstance(row, list) and len(row) >= 4 and row[3] in DEFERRED_PARSED_VALUE_TURNS:
                counts[f"headers.projection.{row[3]}:{DEFERRED_PARSED_VALUE_TURNS[row[3]]}"] += 1
    return dict(counts)


def _measure(sidecar: Sidecar) -> Measured:
    """Walk the fixture once; a failure walking is recorded, not raised."""
    try:
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
    except Exception as error:  # noqa: BLE001 -- reported per fact, see Measured
        return Measured(sidecar=sidecar, result=None, problem=f"{type(error).__name__}: {error}")
    return Measured(sidecar=sidecar, result=result, raw=raw)


def _ordered(sidecar: Sidecar) -> list[Fact]:
    return [sidecar.facts[fact_id] for fact_id in sorted(sidecar.facts)]


def _check_one(measured: Measured, fact: Fact, *, phase: int) -> Outcome:
    sidecar = measured.sidecar
    measure = FACTS.get(fact.id)
    if measure is None:
        raise OracleError(
            f"{sidecar.path}: the sidecar labels {fact.id!r}, which the oracle does not model -- "
            "add it to FACTS with the phase it becomes checkable at (an unmodelled label is "
            "never skipped, because that would report a pass for something nothing measured)"
        )
    if fact.phase != measure.phase:
        raise OracleError(
            f"{sidecar.path}: {fact.id!r} is labelled phase {fact.phase} and the oracle says "
            f"phase {measure.phase} -- the labels and the harness are out of step, so neither "
            "the pass nor the failure would mean anything"
        )
    if fact.phase > phase and not measure.live:
        return Outcome(
            fact_id=fact.id,
            phase=fact.phase,
            status=Status.NOT_YET,
            where=sidecar.stem,
            expected=fact.value,
            detail=f"due at phase {fact.phase}, the oracle is at phase {phase}",
        )
    if measure.defer is not None and measure.defer(fact.value):
        return Outcome(
            fact_id=fact.id,
            phase=fact.phase,
            status=Status.NOT_YET,
            where=sidecar.stem,
            expected=fact.value,
            detail="every row this sidecar asserts belongs to a later turn",
        )
    if measure.function is None:
        raise OracleError(
            f"{sidecar.path}: {fact.id!r} is due at phase {fact.phase}, which the oracle claims "
            f"to be at, but nothing measures it ({measure.note or 'no measurer registered'})"
        )
    try:
        actual = measure.function(measured)
    except Exception as error:  # noqa: BLE001 -- reported, not swallowed: see Measured
        return Outcome(
            fact_id=fact.id,
            phase=fact.phase,
            status=Status.UNMEASURABLE,
            where=sidecar.stem,
            expected=fact.value,
            detail=f"{type(error).__name__}: {error}",
        )
    return _compare(measured, fact, measure, actual)


def _compare(measured: Measured, fact: Fact, measure: Measure, actual: Any) -> Outcome:
    outcome = measure.compare(fact.value, actual)
    if isinstance(outcome, tuple):
        agrees, detail = outcome
    else:
        agrees, detail = outcome, None
    if agrees:
        status = Status.OK
    else:
        status = Status.MISMATCH
        detail = detail or f"labelled {_short(fact.value)}, measured {_short(actual)}"
    return Outcome(
        fact_id=fact.id,
        phase=fact.phase,
        status=status,
        where=measured.sidecar.stem,
        expected=fact.value,
        actual=actual,
        detail=detail,
    )


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 200 else text[:197] + "..."
