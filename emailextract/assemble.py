"""Turn 1.9: assemble the stages into the one frozen record, ``EmailDocument``.

:func:`assemble` is a **pure function of the container bytes and the ``Limits``**.
It composes the stages that already exist -- the walker, the header stage, the
attachment stage, the selection rule, the text and HTML projections and the quote
resolver -- and computes nothing new about the message:

* every axis the build spec says Phase 1 does **not** build (``children``,
  ``thread_edges``, ``same_message_candidates`` and ``times``) is the not-built
  idiom, ``TriValue(UNKNOWN, not_built_in_phase1)``, with an **empty** value list;
  a **built** axis is :func:`emailextract.model.built_axis`. ``None`` and ``[]``
  are never used to mean "not built" (decision 6);
* the parts' ``part_id`` is the walker's content-addressed id, so it is identical
  for identical bytes at the same tree position and unique within the document;
* the document's ``quote_boundaries``/``view_levels`` rows are exactly the rows
  ``quote/resolve.py`` produces, for every body view.

**No body text is stored on the record.** A view is derived on demand from the
container bytes (``text.analyse_part``, ``htmltext.project``); the record keeps
only the per-view evidence about it. That is why :func:`resolve_span` needs the
container, and why a document read from a store carries no text.

The record is a pure function of its inputs: nothing here reads a clock, a path
or the environment. ``RunRecord.environment`` is **recorded-only** -- this module
never reads it and never keys on it, so an assembled record is byte-identical on
every interpreter; a caller that wants interpreter provenance records it beside
the artifact (``store.recorded_only_inputs``).

Hostile input never raises out of :func:`assemble`: the walker accounts every cap
it hits, and the caps land in ``run_record.caps``. The stages are written never to
raise on input *content*; the one guard below turns an unexpected stage failure
into a recorded ``failed(extractor_error)`` document rather than an exception, and
every corpus fixture is asserted to assemble to a ``parsed`` document, so a
swallowed stage bug fails loudly there instead of hiding.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Final, Mapping

from . import versions
from .attach import attachments as attachment_stage
from .container import Container
from .headers import header_region
from .ids import NOT_BUILT_IN_PHASE1, RawSpan, SPAN_NOT_RESOLVABLE, sha256_hex, walk_key
from .model import (
    BodyView,
    CapRecord,
    Classification,
    ContainerFacts,
    ContentFingerprint,
    DecorativeHint,
    EmailDocument,
    FlagSection,
    HeaderField,
    PartRecord,
    QuoteBoundary,
    RunRecord,
    Selection,
    Status,
    StatusOutcome,
    TriState,
    TriValue,
    ViewLevel,
    not_built_in_phase1,
)
from .parse import Limits
from .quote import resolve as quote_resolve
from .selection import display_text, is_body_view, selection_rows
from .text import analyse_part
from .walk import CAP_LIMIT_FIELDS, CAP_REASONS, PartShape, WalkResult, walk

__all__ = [
    "PROJECTION_VERSION_NAMES",
    "Unresolvable",
    "assemble",
    "document_key",
    "identity_projection",
    "limits_fingerprint",
    "projection_versions",
    "resolve_span",
    "run_id",
]

#: The version constants whose values the record stamps on ``RunRecord``: the
#: projections that produced each derived view (build spec, Turn 1.9 B). The key is
#: the constant's **own name**, exactly as the prompt asks, so a reader can tell
#: what rendered a stored view.
PROJECTION_VERSION_NAMES: Final[tuple[str, ...]] = (
    "TEXTMODEL_VERSION",
    "TEXTPART_VERSION",
    "HEADERTEXT_VERSION",
    "HTMLTEXT_VERSION",
    "DECODE_CHAIN_VERSION",
    "QUOTE_RULES_VERSION",
)

#: The views a citation may name (``model.BodyView``); anything else is refused.
_VIEWS: Final[tuple[str, ...]] = (BodyView.PLAIN.value, BodyView.HTML.value)

_HTML: Final[str] = BodyView.HTML.value


def projection_versions() -> dict[str, str]:
    """``{constant name: version value}``, read off :mod:`emailextract.versions` now.

    Read at call time -- not captured at import -- so a bumped constant is seen
    without a reimport (the behavior ledger reads its versions the same way).
    """
    return {name: getattr(versions, name) for name in PROJECTION_VERSION_NAMES}


def limits_fingerprint(limits: Limits) -> str:
    """A canonical digest of the caller's ``Limits``, field by field.

    Every canonical field is in it, in declaration order, so a raised cap is a
    different run and therefore a different document key. ``Limits`` has no default
    set, so this is exactly the caller's own parameters.
    """
    if not isinstance(limits, Limits):
        raise TypeError(f"limits must be a Limits, got {limits!r}")
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in limits.__dataclass_fields__
    )
    return sha256_hex(payload.encode("utf-8"))


def document_key(container_hash_value: str, *, limits: Limits) -> str:
    """The document artifact's key: the hashed inputs, and nothing else.

    ``container hash + OUTPUT_SCHEMA_VERSION + EMAIL_PARSER_VERSION`` + every
    projection version + the ``Limits`` fingerprint. A path, an interpreter and the
    platform are **not** inputs (no path ever enters a document or a cache key), so
    the same bytes under two paths share one key and two interpreters agree.
    """
    if not isinstance(container_hash_value, str) or not container_hash_value:
        raise ValueError("document_key: container_hash must be a non-empty str")
    stamped = projection_versions()
    return walk_key(
        container_hash_value,
        versions.OUTPUT_SCHEMA_VERSION,
        versions.EMAIL_PARSER_VERSION,
        *(stamped[name] for name in PROJECTION_VERSION_NAMES),
        limits_fingerprint(limits),
    )


def run_id(container_hash_value: str, *, limits: Limits) -> str:
    """The run's identity: the container hash, the two record versions, the ``Limits``.

    The **projection versions are deliberately not in it**: ``HTMLTEXT_VERSION``
    stamps the CPython minor the projection ran under (decision 1), which is a
    recorded-only input, so a run id carrying it would turn one run into two runs
    across interpreters. They are stamped beside it
    (``RunRecord.projection_versions``) and are part of the document artifact's key.
    """
    if not isinstance(container_hash_value, str) or not container_hash_value:
        raise ValueError("run_id: container_hash must be a non-empty str")
    return walk_key(
        container_hash_value,
        versions.OUTPUT_SCHEMA_VERSION,
        versions.EMAIL_PARSER_VERSION,
        limits_fingerprint(limits),
    )


@dataclass(frozen=True)
class Unresolvable:
    """A refused citation: the closed ``reason_id`` and the ``part_id`` it is about.

    Returned (never raised) by :func:`resolve_span` where the part carries no
    within-part byte map. ``span_not_resolvable`` is the only reason Phase 1 emits.
    """

    reason_id: str
    part_id: str

    def __post_init__(self) -> None:
        if self.reason_id != SPAN_NOT_RESOLVABLE:
            raise ValueError(
                f"unresolvable.reason_id must be {SPAN_NOT_RESOLVABLE!r}, "
                f"the closed Phase 1 refusal, got {self.reason_id!r}"
            )
        if not isinstance(self.part_id, str) or not self.part_id:
            raise ValueError("unresolvable.part_id must be a non-empty str")


# --------------------------------------------------------------- the composition


def _media(part: PartShape) -> str:
    """The part's media type, exactly as the walker parsed it (parameters dropped)."""
    return (part.content_type or "").strip().lower()


def _reads_as_text(part: PartShape) -> bool:
    """The walker's own text decision: the charset ladder ran over this part."""
    return part.decode_chain.used_charset is not None


def _header_fields(raw: bytes, result: WalkResult, limits: Limits) -> list[HeaderField]:
    """The top-level header region as frozen :class:`HeaderField` records.

    The header stage measures the region; this only re-shapes its fields. ``value``
    is the stage's RFC 2047 decode of a text-kind field (absent when there is none
    or it is empty); every other kind keeps its raw value and an absent ``value``,
    because the stage's parsed rows for those live beside the region, not in a
    single decoded scalar.

    A **malformed paragraph** (``parse_status != "ok"``: a non-blank line that is
    neither a field nor a fold) has no name, and ``HeaderField`` requires a
    non-empty one, so it is not a field and is not in ``headers``. That is a
    reported gap, not a silent drop: the paragraph's bytes are still accounted by
    the walker's regions (the no-silent-drop property), and the header stage
    records ``headers.malformed_line`` on its own gap channel.
    """
    region = header_region(raw, result, max_work_units=limits.max_field_work_units_per_byte)
    fields: list[HeaderField] = []
    for item in region.fields:
        if item.parse_status != "ok":
            continue
        decoded = region.text_decodes.get(item.ordinal)
        text = decoded.text if decoded is not None else None
        value = TriValue(state=TriState.VALUE, value=text) if text else TriValue()
        fields.append(
            HeaderField(
                name=item.name,
                raw_value=item.raw_value,
                ordinal=item.ordinal,
                value=value,
                flags=FlagSection(),
            )
        )
    return fields


def _caps(result: WalkResult, limits: Limits) -> list[CapRecord]:
    """Every cap the walk recorded, as ``CapRecord``s, in walk order.

    The walker's own ``UnknownSection`` entries on the cap reason channel are the
    source; the accounted region under the same locator carries the skipped size,
    and ``walk.CAP_LIMIT_FIELDS`` maps the reason to the caller's own ``Limits``
    field, so the triple is reconstructible from the result and the ``Limits``.
    """
    declared: dict[tuple[str, str], int] = {}
    for region in result.regions:
        if region.kind in CAP_REASONS:
            declared[(region.kind, region.path)] = region.span.length
    caps: list[CapRecord] = []
    for section in result.unknown_sections:
        reason = section.value.reason_id
        if reason not in CAP_REASONS:
            continue
        field_name = CAP_LIMIT_FIELDS[reason]
        caps.append(
            CapRecord(
                cap_id=reason,
                cap_value_bytes=getattr(limits, field_name),
                declared_size_bytes=declared.get((reason, section.section)),
            )
        )
    return caps


def _document_status(result: WalkResult) -> StatusOutcome:
    """``skipped(reason)`` when the message's own part was capped, else ``parsed``.

    A cap on the top-level part means the message itself was not read to the end, so
    the document says so with the walker's own closed reason; any other cap is a
    per-part fact and leaves the document ``parsed``.
    """
    for section in result.unknown_sections:
        if section.section == "1" and section.value.reason_id in CAP_REASONS:
            return StatusOutcome(status=Status.SKIPPED, reason=section.value.reason_id)
    return StatusOutcome(status=Status.PARSED)


def _content_fingerprint(
    raw: bytes,
    result: WalkResult,
    *,
    limits: Limits,
) -> ContentFingerprint:
    """D14's labeled fingerprint: the selected body view's text, ``HTML`` if present.

    The digest is over the view's **code points** encoded UTF-8 -- the
    transport-encoding-independent body content -- never over the transfer bytes,
    which differ between the same message stored as ``.eml`` and as ``.msg``. The
    view is ``html`` when the message has a displayable ``text/html`` body view
    (the design's "HTML if present, else plain"); the digested part is the one the
    selection stage selected within that view, else the first such view in part
    order. A message with no text body view digests the empty string.
    """
    by_path = {part.path: part for part in result.parts}
    views = [
        part
        for part in result.parts
        if is_body_view(part, by_path) and _reads_as_text(part)
    ]
    plain_text = display_text(raw, result)
    html_text = {
        part.path: projection.text
        for part, projection in quote_resolve.html_views(
            raw, result, max_depth=limits.max_depth, max_elements=limits.max_parts
        )
    }
    selected = {
        row[0] for row in selection_rows(raw, result) if row[1] == Selection.SELECTED.value
    }

    def choose(candidates: list[PartShape]) -> PartShape | None:
        if not candidates:
            return None
        for part in candidates:
            if part.path in selected:
                return part
        return candidates[0]

    html_views = [part for part in views if _media(part) == "text/html"]
    if html_views:
        chosen = choose(html_views)
        assert chosen is not None
        text = html_text.get(chosen.path, "")
        view = BodyView.HTML
    else:
        plain_views = [part for part in views if _media(part) == "text/plain"]
        chosen = choose(plain_views)
        text = plain_text.get(chosen.path, "") if chosen is not None else ""
        view = BodyView.PLAIN
    return ContentFingerprint(
        body_digest=sha256_hex(text.encode("utf-8")), body_digest_view=view
    )


def _part_records(
    result: WalkResult,
    attachments: Mapping[str, Any],
    selections: Mapping[str, str],
) -> list[PartRecord]:
    """The parts tree as frozen :class:`PartRecord` rows, in the walker's order.

    ``part_id`` is the walker's content-addressed id; ``parent_part_id`` is the
    parent's (resolved through the tree, since the frozen record names the id, not
    the locator); ``role`` is ``container`` for a multipart, ``body`` for a
    displayable text view, ``attachment`` for an occurrence and ``None`` otherwise.
    An attachment's classification, decorative hint and type verdicts are the
    attachment stage's own facts for that part, never a second classification.
    """
    by_path = {part.path: part for part in result.parts}
    capped = {
        section.section
        for section in result.unknown_sections
        if section.value.reason_id in CAP_REASONS
    }
    records: list[PartRecord] = []
    for part in result.parts:
        media = _media(part)
        parent = by_path.get(part.parent_path or "")
        if part.path in attachments:
            occurrence = attachments[part.path]
            role = "attachment"
            classification = occurrence.classification
            hint = occurrence.hint
            verdicts = occurrence.verdicts
        elif media.startswith("multipart/"):
            role = "container"
            classification = Classification.UNKNOWN
            hint = DecorativeHint()
            verdicts = None
        elif is_body_view(part, by_path):
            role = "body"
            classification = Classification.UNKNOWN
            hint = DecorativeHint()
            verdicts = None
        else:
            role = None
            classification = Classification.UNKNOWN
            hint = DecorativeHint()
            verdicts = None
        status = (
            StatusOutcome(status=Status.SKIPPED, reason=_cap_reason(result, part.path))
            if part.path in capped
            else StatusOutcome(status=Status.PARSED)
        )
        records.append(
            PartRecord(
                part_id=part.part_id,
                content_type=part.content_type,
                parent_part_id=parent.part_id if parent is not None else None,
                role=role,
                classification=classification,
                selection=Selection(selections.get(part.path, Selection.NOT_APPLICABLE.value)),
                status=status,
                size_bytes=part.body_span.length,
                sha256=part.body_sha256,
                encoding_source=part.encoding_source,
                decode_chain=part.decode_chain,
                decorative_hint=hint,
                type_verdicts=verdicts,
                flags=FlagSection(),
            )
        )
    return records


def _cap_reason(result: WalkResult, locator: str) -> str:
    """The closed cap reason the walker recorded for ``locator`` (first one wins)."""
    for section in result.unknown_sections:
        if section.section == locator and section.value.reason_id in CAP_REASONS:
            return section.value.reason_id
    raise ValueError(f"no cap recorded for {locator!r}")


def _compose(container: Container, *, limits: Limits) -> EmailDocument:
    """The composition proper; :func:`assemble` is its failure guard."""
    raw = container.raw_bytes()
    container_id = container.container_hash()
    result = walk(container, limits=limits)
    attach = attachment_stage(
        raw,
        result,
        max_depth=limits.max_depth,
        max_elements=limits.max_parts,
        limits=limits,
    )
    facts = {item.part.path: item for item in attach.facts}
    selections = {row[0]: row[1] for row in selection_rows(raw, result)}
    caps = _caps(result, limits)
    views = quote_resolve.all_views(
        raw, result, max_depth=limits.max_depth, max_elements=limits.max_parts
    )
    boundaries: list[QuoteBoundary] = [
        boundary for record in views for boundary in record.boundaries
    ]
    levels: list[ViewLevel] = [
        record.level for record in views if record.level is not None
    ]
    run_record = RunRecord(
        run_id=run_id(container_id, limits=limits),
        email_parser_version=versions.EMAIL_PARSER_VERSION,
        output_schema_version=versions.OUTPUT_SCHEMA_VERSION,
        caps=caps,
        environment={},
        projection_versions=projection_versions(),
        flags=FlagSection(),
    )
    return EmailDocument(
        container_kind=container.kind,
        container_hash=container_id,
        container_facts=ContainerFacts(container.container_facts()),
        content_fingerprint=_content_fingerprint(raw, result, limits=limits),
        status=_document_status(result),
        headers=_header_fields(raw, result, limits),
        parts=_part_records(result, facts, selections),
        attachments=list(attach.occurrences),
        children=[],
        children_axis=not_built_in_phase1(),
        thread_edges=[],
        thread_edges_axis=not_built_in_phase1(),
        times=[],
        times_axis=not_built_in_phase1(),
        same_message_candidates=[],
        same_message_candidates_axis=not_built_in_phase1(),
        quote_boundaries=boundaries,
        view_levels=levels,
        classification_hint=None,
        run_record=run_record,
        output_schema_version=versions.OUTPUT_SCHEMA_VERSION,
        flags=FlagSection(),
    )


def _failed_document(container: Container, *, limits: Limits) -> EmailDocument:
    """A recorded failure: ``status=failed(extractor_error)`` and no claimed evidence.

    The container identity is real (it was read); everything a stage would have
    measured is empty, and the axes keep the not-built idiom. Nothing is guessed.
    The marker here is built directly rather than through the module-level helper the
    composition uses, so the failure path cannot itself fail.
    """
    container_id = container.container_hash()
    marker = TriValue(state=TriState.UNKNOWN, reason_id=NOT_BUILT_IN_PHASE1)
    return EmailDocument(
        container_kind=container.kind,
        container_hash=container_id,
        container_facts=ContainerFacts(container.container_facts()),
        content_fingerprint=ContentFingerprint(
            body_digest=sha256_hex(b""), body_digest_view=BodyView.PLAIN
        ),
        status=StatusOutcome(status=Status.FAILED, reason="extractor_error"),
        headers=[],
        parts=[],
        attachments=[],
        children=[],
        children_axis=marker,
        thread_edges=[],
        thread_edges_axis=marker,
        times=[],
        times_axis=marker,
        same_message_candidates=[],
        same_message_candidates_axis=marker,
        quote_boundaries=[],
        view_levels=[],
        classification_hint=None,
        run_record=RunRecord(
            run_id=run_id(container_id, limits=limits),
            output_schema_version=versions.OUTPUT_SCHEMA_VERSION,
            environment={},
            projection_versions=projection_versions(),
            flags=FlagSection(),
        ),
        output_schema_version=versions.OUTPUT_SCHEMA_VERSION,
        flags=FlagSection(),
    )


def assemble(container: Container, *, limits: Limits) -> EmailDocument:
    """Assemble one container into the one frozen :class:`EmailDocument`.

    A pure function of the container bytes and ``limits``: no clock, no path, no
    environment, no exception to the caller. ``limits`` carries the input cap
    (``max_input_bytes``) the *caller* enforces -- an over-cap file is an ingest
    outcome (``ids.FILE_OVER_CAP``), not an assembly one.
    """
    if not isinstance(limits, Limits):
        raise TypeError(f"limits must be a Limits, got {limits!r}")
    try:
        return _compose(container, limits=limits)
    except Exception:  # noqa: BLE001 - a stage must never raise on input *content*
        return _failed_document(container, limits=limits)


def identity_projection(document: EmailDocument) -> EmailDocument:
    """The document with the **recorded-only** inputs stripped (build spec, Phase 1 exit).

    A record read from a store is reproducible or it says why not: the run record's
    ``environment`` and its ``projection_versions`` are the two inputs that depend on
    *who* rendered the record (``HTMLTEXT_VERSION`` stamps the CPython minor the
    projection ran under, decision 1), and they are recorded-only, never keyed on.
    Everything else -- the axes, the caps, the parts, the quote rows -- is the
    document's own evidence and is untouched, so the identity projection is what
    two runs, two hash seeds and two interpreters must agree on byte for byte.
    """
    if document.run_record is None:
        return document
    stripped = replace(
        document.run_record, environment={}, projection_versions={}
    )
    return replace(document, run_record=stripped)


def resolve_span(
    document_or_container: Container,
    part_id: str,
    view: str,
    start: int,
    end: int,
) -> RawSpan | Unresolvable:
    """Cite a view span as raw byte offsets, or refuse with a closed reason.

    ``document_or_container`` is the **container** the citation is against: an
    assembled document stores no body text (a view is derived on demand), so the
    bytes have to be in hand. ``part_id`` is the frozen, content-addressed part id;
    ``view`` is ``plain`` or ``html``; ``[start, end)`` are **code points** of that
    view's text.

    A positive answer is an :class:`~emailextract.ids.RawSpan` into the raw message
    (``locator`` is the part's non-stable path). It is only given where the part has
    a within-part byte map -- an identity-decoded, statically-decodable text part,
    so ``decoded`` bytes *are* the part's payload bytes and the map is exact.
    Everything else is refused with ``Unresolvable(span_not_resolvable, part_id)``,
    never a guess:

    * ``view='html'`` -- the HTML projection is its own coordinate space with no
      byte map;
    * a ``format=flowed`` part -- the map covers the unstuffing, but the reflow is
      deferred (RFC 3676 4.4 is not applied in v1), so the view's coordinate space
      is not final;
    * a part whose transport decode was not identity (base64/QP) or whose charset
      has no sound map -- ``PartText.offset_map`` is absent;
    * an unknown part id, an unknown view or a span outside the view's text.
    """
    raw, result = _bytes_and_parts(document_or_container)
    for name, value in (("start", start), ("end", end)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"resolve_span: {name} must be an int, got {value!r}")
    part = next((item for item in result.parts if item.part_id == part_id), None)
    if part is None or view not in _VIEWS or view == _HTML:
        return Unresolvable(reason_id=SPAN_NOT_RESOLVABLE, part_id=part_id)
    record = analyse_part(raw, part)
    if record is None or record.flowed or record.offset_map is None:
        return Unresolvable(reason_id=SPAN_NOT_RESOLVABLE, part_id=part_id)
    if not (0 <= start <= end <= len(record.text)):
        return Unresolvable(reason_id=SPAN_NOT_RESOLVABLE, part_id=part_id)
    span = _map_span(record, part, start, end)
    if span is None:
        return Unresolvable(reason_id=SPAN_NOT_RESOLVABLE, part_id=part_id)
    return span


def _bytes_and_parts(source: Any) -> tuple[bytes, WalkResult]:
    """``(raw bytes, walk result)`` for a citation target.

    The target is a :class:`~emailextract.container.Container` (anything that serves
    ``raw_bytes()``). An :class:`~emailextract.model.EmailDocument` is refused with a
    ``TypeError``: it deliberately stores no body text, so a citation has to be made
    against the container it was assembled from.
    """
    raw_bytes = getattr(source, "raw_bytes", None)
    if not callable(raw_bytes):
        raise TypeError(
            "resolve_span takes a Container: a citation needs the raw bytes, and an "
            f"EmailDocument stores no body text (got {type(source).__name__})"
        )
    raw = source.raw_bytes()
    return raw, walk(source)


def _char_to_byte(record: Any) -> dict[int, int]:
    """``{char index: byte offset}`` from a part's within-part byte map.

    The map's entries partition ``[0, len(decoded))`` and the unstuffed text's code
    points, so every code-point boundary maps to one byte offset: a 1:1 entry steps
    one byte per character, a multibyte entry (one character, several bytes) starts
    at its own byte offset, and a zero-character entry (a dropped RFC 3676 stuffing
    space, a ``utf-8-sig`` BOM) consumes bytes that produce no character.
    """
    byte_at: dict[int, int] = {}
    for entry in record.offset_map:
        step_size = entry.byte_length // entry.char_length if entry.char_length else 0
        for step in range(entry.char_length):
            byte_at[entry.char_offset + step] = entry.byte_offset + step * step_size
        byte_at[entry.char_end] = entry.byte_end
    if 0 not in byte_at:
        byte_at[0] = 0
    return byte_at


def _map_span(record: Any, part: PartShape, start: int, end: int) -> RawSpan | None:
    """The raw span for a view code-point range, or ``None`` when it does not map."""
    byte_at = _char_to_byte(record)
    if start not in byte_at or end not in byte_at:
        return None
    offset = part.body_span.offset + byte_at[start]
    length = byte_at[end] - byte_at[start]
    return RawSpan(offset=offset, length=length, locator=part.path)
