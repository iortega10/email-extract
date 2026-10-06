"""Turn 0.2 skeleton walker over the container interface (build spec, Turn 0.2).

What this is, exactly: a **skeleton**. Per part it measures the raw byte span,
the headers span, the body span, the declared and used CTE/charset and
``fallback_fired``, and it accounts for the preamble and epilogue as their own
regions -- nothing else. It does **not** segment quotes, classify attachments,
route to siblings, build threads, render headers, match terms or read a CFB
file; every such section is recorded as ``unknown(not_built_in_phase0)``, never
as an absence and never as a guessed value.

Measured facts this is built on (``docs/design/email-spike.md``): stdlib ``email``
gives no raw byte offsets and never round-trips CRLF bytes (c01/c02/c04), so the
walker owns a small raw-header scanner over the raw bytes and stdlib is never
re-serialized to recover a span; defects and ``decode=True`` disagree (b02), so
the decode chain is recorded here rather than trusted from stdlib; unknown CTE
falls back to the raw payload **silently** in stdlib (d03), which this walker
records as ``body.decode_fallback_used``. A fold (obs-fold) is ONE field; a
non-blank line that is neither ``name: value`` nor a fold becomes its own
paragraph with ``parse_status: unknown`` and gap ``headers.malformed_line``, and
the header region does **not** end (D2 fail-open).

``errors="replace"`` is never the normal decode path -- it destroys byte
round-trip. The charset decision is a deterministic ladder (declared charset ->
all-ASCII -> strict UTF-8 -> strict windows-1252); only when no rung decodes
strictly is a replacement decode taken, and it is recorded as
``body.decode_destroyed_bytes``.

Part identity is content-addressed (:mod:`emailextract.ids`); the ``1.2.3``
``path`` recorded here is an explicitly non-stable locator (D12), never an id.

Turn 1.5c: the structural caps (``walk(container, *, limits=None)``)
--------------------------------------------------------------------

``walk`` takes the caller's :class:`~emailextract.parse.Limits` as a keyword. ``None``
means **unbounded** and exists only so the Phase 0 callers, the frozen corpus and every
test that predates the caps read exactly the bytes they always read; the entry point
(``parse``, wired in Turn 1.9) always passes a ``Limits``.

A cap hit is recorded with the vocabulary that already exists: the closed
:data:`emailextract.model.REASON_TABLE` ``skipped`` reason of the cap, on the accounted
bytes it stopped, plus the walker's own "unread, and here is why" entry. Concretely, and
this is the whole channel:

* the skipped bytes become **one** :class:`Region` whose ``kind`` *is* the closed cap
  reason (``size_cap``, ``total_size_cap``, ``depth_cap``, ``part_count_cap``,
  ``header_bytes_cap``), whose ``path`` is the locator of the part the cap stopped and
  whose ``span`` is the exact byte range. Regions still tile the message exactly, so the
  no-silent-drop gate needs no change to know about them.
* one :class:`UnknownSection` goes on :attr:`WalkResult.unknown_sections` with
  ``section`` set to that same locator and ``value = unknown(reason_id)``.

No new reason id, no new record, no exception and no ``Truncation``: a cap hit is a
*built* observation. ``cap_id`` is the reason id (the model's own convention,
``CapRecord(cap_id="depth_cap", ...)``), the cap value is the caller's ``Limits`` field
and the declared size is the skipped region's span length -- so a run that hits two caps
records both, and the triple a later turn puts on ``RunRecord.caps`` is reconstructible
from the result and the ``Limits`` that produced it. Phase 1 has no document to hang a
status on, and adding a field to ``WalkResult`` would move the behaviour ledger's
``contracts`` fingerprint (``tools/behavior_ledger.contract_records()`` hashes this
module's dataclasses), which this turn may not do.

The boundary rule is one rule for all five caps: **a value equal to the cap is allowed,
one over is a hit**.
"""

from __future__ import annotations

import base64
import binascii
import quopri
from dataclasses import dataclass, field
from typing import Final, Mapping

from .container import Container
from .ids import NOT_BUILT_IN_PHASE0, RawSpan, content_hash, part_id, sha256_hex
from .model import ContainerKind, DecodeChain, EncodingSource, TriState, TriValue
from . import parse

__all__ = [
    "CAP_LIMIT_FIELDS",
    "CAP_REASONS",
    "CAP_REASON_DEPTH",
    "CAP_REASON_HEADER_BYTES",
    "CAP_REASON_PART_COUNT",
    "CAP_REASON_SIZE",
    "CAP_REASON_TOTAL_SIZE",
    "DECODE_CHUNK",
    "PartShape",
    "RawHeaderField",
    "Region",
    "UnknownSection",
    "WORK",
    "WalkResult",
    "WorkCounter",
    "header_fields_at",
    "leading_prelude",
    "walk",
]

#: The sections this skeleton does not build. Each is recorded ``unknown`` with
#: the reason id ``not_built_in_phase0`` -- the honesty rule: nothing here may
#: report a status or a field for input it has not read, and nothing may look
#: like an absence.
UNBUILT_SECTIONS: tuple[str, ...] = (
    "quote_segmentation",
    "attachment_classification",
    "sibling_routing",
    "thread_edges",
    "header_text",
    "flag_hits",
)

#: Named gap ids (design registry, ``docs/design/email-extraction-design.md``).
GAP_HEADERS_MALFORMED_LINE = "headers.malformed_line"
GAP_BODY_HEADERS_ONLY = "body.headers_only"
GAP_BODY_NO_BOUNDARY_FOUND = "body.no_boundary_found"
GAP_BODY_BOUNDARY_DISAGREEMENT = "body.boundary_disagreement"
GAP_BODY_PREAMBLE_BYTES = "body.preamble_bytes"
GAP_BODY_EPILOGUE_BYTES = "body.epilogue_bytes"
GAP_BODY_DECODE_FALLBACK_USED = "body.decode_fallback_used"
GAP_BODY_DECODE_DESTROYED_BYTES = "body.decode_destroyed_bytes"

_FOLD_PREFIXES = (b" ", b"\t")
_NAME_STOP = 58  # ':' -- RFC 5322 ftext is %d33-57 / %d59-126
#: The tolerated leading prelude (decision 14): a UTF-8 BOM and an mbox ``From `` line.
_UTF8_BOM = b"\xef\xbb\xbf"
_MBOX_PREFIX = b"From "
_TEXT_LADDER = ("us-ascii", "utf-8", "windows-1252")

# ------------------------------------------------------------- the caps (1.5c)

#: The five closed cap reason ids -- ``model.REASON_TABLE[Status.SKIPPED]``, spelled here
#: as their own names so a test can prove the two sets are equal rather than restate one.
CAP_REASON_SIZE: Final[str] = "size_cap"
CAP_REASON_TOTAL_SIZE: Final[str] = "total_size_cap"
CAP_REASON_DEPTH: Final[str] = "depth_cap"
CAP_REASON_PART_COUNT: Final[str] = "part_count_cap"
CAP_REASON_HEADER_BYTES: Final[str] = "header_bytes_cap"

#: The closed cap reasons, in the model's own order: a cap hit is one of these, never a
#: new id and never a dotted one.
CAP_REASONS: Final[tuple[str, ...]] = (
    CAP_REASON_SIZE,
    CAP_REASON_TOTAL_SIZE,
    CAP_REASON_DEPTH,
    CAP_REASON_PART_COUNT,
    CAP_REASON_HEADER_BYTES,
)

#: The ``Limits`` field each cap reason is the hit of: **the cap value a reader records is
#: always the caller's own**, never a module default (there is none: ``Limits`` has no
#: defaults). This is also the map from a recorded reason back to its ``CapRecord``
#: ``cap_value_bytes``.
CAP_LIMIT_FIELDS: Final[Mapping[str, str]] = {
    CAP_REASON_SIZE: "max_decoded_part_bytes",
    CAP_REASON_TOTAL_SIZE: "max_decoded_total_bytes",
    CAP_REASON_DEPTH: "max_depth",
    CAP_REASON_PART_COUNT: "max_parts",
    CAP_REASON_HEADER_BYTES: "max_header_bytes",
}

#: The chunk of input bytes the bounded decoders read at a time (item 4). Base64 groups
#: are decoded as they complete and quoted-printable is cut at a boundary no escape or
#: line ending spans, so the streamed decode of a part *under* the cap equals the
#: whole-buffer decode byte for byte, and a part *over* it never expands past the cap.
DECODE_CHUNK: Final[int] = 8192

#: The single hex digits, as one-byte ``bytes``: a quoted-printable ``=XX`` escape's second
#: and third bytes, used to keep a decode chunk boundary out of an escape.
_HEX_DIGITS: Final[tuple[bytes, ...]] = tuple(bytes([byte]) for byte in b"0123456789abcdef")


class WorkCounter:
    """A deterministic work counter -- the linearity seam (never a clock).

    :data:`WORK` is the walker's own instance. A test resets it, walks, and reads it back:
    ``WORK.reset(); walk(...); steps = WORK.count()``. The count is a pure function of the
    bytes read and the caps applied -- no timing, no environment -- so a linearity claim
    ("doubling the hostile input less than doubles the steps") is reproducible.
    """

    __slots__ = ("steps",)

    def __init__(self) -> None:
        self.steps = 0

    def reset(self) -> None:
        self.steps = 0

    def add(self, count: int = 1) -> None:
        self.steps += count

    def count(self) -> int:
        return self.steps


#: The walker's work counter (the linearity seam). Swappable by a test.
WORK: Final[WorkCounter] = WorkCounter()


class _WalkState:
    """One walk's mutable cap state: the caller's ``limits`` and what the caps stopped.

    Not a record: nothing here is serialized and nothing here is a contract. ``limits`` is
    ``None`` for the unbounded walk (see the module docstring). ``decoded_total`` is the
    running sum of decoded body bytes across the message (``max_decoded_total_bytes``), and
    ``caps`` collects the ``unknown(reason)`` entries that join
    :attr:`WalkResult.unknown_sections`.
    """

    __slots__ = ("caps", "decoded_total", "limits")

    def __init__(self, limits: parse.Limits | None) -> None:
        self.limits = limits
        self.decoded_total = 0
        self.caps: list[UnknownSection] = []


def _part_count_allows(limits: parse.Limits | None, emitted: int) -> bool:
    """The ``max_parts`` test: a part count equal to the cap is allowed, one over is a hit."""
    return limits is None or emitted < limits.max_parts


def _header_bytes_allows(limits: parse.Limits | None, length: int) -> bool:
    """The ``max_header_bytes`` test: a region equal to the cap is allowed, one over is a hit."""
    return limits is None or length <= limits.max_header_bytes


def _depth_allows(limits: parse.Limits | None, depth: int) -> bool:
    """The ``max_depth`` test: a nesting depth equal to the cap is allowed, one over is a hit."""
    return limits is None or depth <= limits.max_depth


def _decode_budget(state: _WalkState) -> tuple[int | None, str | None]:
    """The decoded-byte budget for the next leaf and the cap a stop would be a hit of.

    ``(None, None)`` for the unbounded walk. Otherwise the budget is the tighter of the
    part's own cap and what is left of the message-wide cap, and the *reason* is the cap
    that is tighter (a tie is the part's own cap, ``size_cap``: it is the part-local
    reading). A message whose total is exactly reached leaves a budget of 0, so a later
    part with any decoded bytes at all is skipped with ``total_size_cap``.
    """
    limits = state.limits
    if limits is None:
        return None, None
    remaining = limits.max_decoded_total_bytes - state.decoded_total
    if limits.max_decoded_part_bytes <= remaining:
        return limits.max_decoded_part_bytes, CAP_REASON_SIZE
    return remaining, CAP_REASON_TOTAL_SIZE


def _cap_hit(
    regions: list[Region],
    caps: list[UnknownSection],
    reason: str,
    locator: str,
    span: RawSpan,
) -> None:
    """Record one cap hit: the accounted bytes and the walker's unread-and-why entry.

    The region's ``kind`` is the closed cap reason, so the reason rides the bytes it
    applies to and the regions still tile the message exactly; the ``UnknownSection``
    carries the same reason as a ``TriValue`` on the walker's own channel. Nothing is
    dropped and nothing is guessed: the bytes are accounted, and the reason is recorded.
    """
    regions.append(Region(reason, locator, RawSpan(span.offset, span.length, locator)))
    caps.append(
        UnknownSection(
            section=locator, value=TriValue(state=TriState.UNKNOWN, reason_id=reason)
        )
    )


@dataclass(frozen=True)
class RawHeaderField:
    """One raw header field, with its verbatim spans (D2).

    ``parse_status`` is ``ok`` for a parsed ``name: value`` field and
    ``unknown`` for a non-blank line that is neither a field nor a fold -- such a
    line becomes its own paragraph (``name`` empty, ``raw_value`` the line), the
    header region does not end, and the gap ``headers.malformed_line`` is
    recorded on the part. ``raw_value`` is the verbatim value bytes, folds kept,
    decoded latin-1 (a lossless byte->str mapping; the raw message is the source
    of truth).
    """

    ordinal: int
    name: str
    raw_value: str
    parse_status: str
    name_span: RawSpan
    value_span: RawSpan
    raw_span: RawSpan


@dataclass(frozen=True)
class PartShape:
    """What the skeleton measures for one part: spans, decode chain, gaps.

    ``part_id`` is content-addressed (container hash + raw span + content hash);
    ``path`` is the ``1.2.3`` locator and is explicitly non-stable (D12).
    ``decode_chain.declared_*`` comes from the headers, ``used_*`` from the
    decode that actually ran; ``body_sha256`` is over the transfer-decoded body
    bytes (``None`` for a multipart, whose bytes are its children's regions).
    """

    path: str
    part_id: str
    parent_path: str | None
    content_type: str | None
    raw_span: RawSpan
    headers_span: RawSpan
    body_span: RawSpan
    header_fields: list[RawHeaderField] = field(default_factory=list)
    decode_chain: DecodeChain = field(default_factory=DecodeChain)
    encoding_source: EncodingSource | None = None
    body_sha256: str | None = None
    gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Region:
    """One accounted byte region (D9 no-silent-drop).

    ``kind`` is ``headers`` (a part's header block, its closing blank line
    included), ``body`` (a leaf body), ``preamble`` / ``epilogue`` (a multipart's
    own accounted bytes), ``delimiter`` (a boundary line, its preceding CRLF
    attached per RFC 2046) or ``prelude`` (the tolerated leading BOM / mbox line,
    decision 14). The regions tile the raw message exactly.
    """

    kind: str
    path: str
    span: RawSpan


@dataclass(frozen=True)
class UnknownSection:
    """A section this turn does not build: ``unknown(reason_id)``, never absent."""

    section: str
    value: TriValue

    def __post_init__(self) -> None:
        if not self.section:
            raise ValueError("unknown_section.section must be non-empty")
        if self.value.state is not TriState.UNKNOWN or not self.value.reason_id:
            raise ValueError("unknown_section.value must be unknown with its reason id")


@dataclass(frozen=True)
class WalkResult:
    """Everything the skeleton measured, and the honest boundary of what it did not."""

    container_kind: ContainerKind
    container_hash: str
    container_facts: dict[str, str]
    parts: list[PartShape]
    regions: list[Region]
    unknown_sections: list[UnknownSection]
    total_bytes: int


def walk(container: Container, *, limits: parse.Limits | None = None) -> WalkResult:
    """Measure ``container``: parts, spans, decode chains, accounted regions.

    ``limits`` is the caller's :class:`~emailextract.parse.Limits`, or ``None`` for the
    **unbounded** walk (tests, fixtures and the Phase 0 callers; the entry point always
    passes a ``Limits``). Each cap it hits is recorded as the closed ``skipped`` reason of
    the cap on the accounted bytes it stopped, plus the walker's own unread-and-why entry
    -- see the module docstring. A cap hit never raises and never produces a part that
    looks complete.
    """
    raw = container.raw_bytes()
    container_id = container.container_hash()
    parts: list[PartShape] = []
    regions: list[Region] = []
    state = _WalkState(limits)
    _walk_part(raw, container_id, RawSpan(0, len(raw), "1"), "1", None, parts, regions, state, 1)
    unknowns = [
        UnknownSection(
            section, TriValue(state=TriState.UNKNOWN, reason_id=NOT_BUILT_IN_PHASE0)
        )
        for section in UNBUILT_SECTIONS
    ]
    unknowns.extend(state.caps)
    return WalkResult(
        container_kind=container.kind,
        container_hash=container_id,
        container_facts=container.container_facts(),
        parts=parts,
        regions=regions,
        unknown_sections=unknowns,
        total_bytes=len(raw),
    )


# --------------------------------------------------------------------- lines


def leading_prelude(raw: bytes, start: int) -> tuple[int, int]:
    """``(bom_bytes, mbox_bytes)`` for the tolerated leading prelude (decision 14).

    A UTF-8 BOM (``EF BB BF``) at ``start`` and/or an mbox ``From `` envelope line (a first
    line starting with ``From `` and terminated by LF or CRLF, after the optional BOM) is a
    leading **prelude**: its own region, so spans still tile exactly, and the header scan
    starts after it. The mbox line must be terminated -- a ``From `` prefix at EOF with no
    line ending is not an envelope line. This is the one definition both the walker and
    :mod:`emailextract.headers` use.
    """
    bom = len(_UTF8_BOM) if raw[start : start + len(_UTF8_BOM)] == _UTF8_BOM else 0
    position = start + bom
    mbox = 0
    if raw[position : position + len(_MBOX_PREFIX)] == _MBOX_PREFIX:
        newline = raw.find(b"\n", position)
        if newline != -1:
            mbox = newline + 1 - position
    return bom, mbox


def _iter_lines(raw: bytes, start: int, end: int):
    """Yield ``(line_start, content_end, term_end)`` over ``[start, end)``.

    ``content`` is the line without its terminator; the terminator is ``CRLF``,
    ``LF`` or ``CR``, and a last line at EOF may have none. Each line read is one step
    on :data:`WORK`, so a test can state what a hostile input costs (a boundary storm is
    one pass: linear in the lines, never quadratic in the delimiters).
    """
    position = start
    while position < end:
        WORK.add()
        newline = raw.find(b"\n", position, end)
        carriage = raw.find(b"\r", position, end)
        if newline == -1 and carriage == -1:
            yield position, end, end
            return
        if newline == -1:
            cut = carriage
        elif carriage == -1:
            cut = newline
        else:
            cut = min(newline, carriage)
        if cut < end - 1 and raw[cut] == 13 and raw[cut + 1] == 10:
            yield position, cut, cut + 2
        else:
            yield position, cut, cut + 1
        position = cut + 2 if (cut < end - 1 and raw[cut : cut + 2] == b"\r\n") else cut + 1


def iter_lines(raw: bytes, start: int, end: int):
    """The **public** name of the one line model (decision 8): :func:`_iter_lines`.

    The quote splitter, the ``>``-depth counter, the offset map and the quote rules all
    consume this model and no other -- it lives here, once, and
    :mod:`emailextract.text` re-exports it rather than copying it. A lone CR is a line
    terminator, CRLF is one terminator, LF is one; ``str.splitlines``/``bytes.splitlines``
    are **forbidden** for body text (they also break on form feed, vertical tab, U+2028 and
    -- after decoding -- U+0085).
    """
    return _iter_lines(raw, start, end)


def header_fields_at(raw: bytes, start: int, end: int) -> tuple[list[RawHeaderField], list[str]]:
    """The raw-header scanner (spike c01: stdlib offers no byte offsets at all).

    Returns the ordered fields -- duplicates kept, identity by ordinal, one
    field per obs-fold chain -- and the gap ids the scan recorded. A non-blank
    line that is neither ``name: value`` nor a fold becomes its own paragraph
    with ``parse_status: unknown`` (D2) and the scan continues fail-open.
    """
    fields: list[RawHeaderField] = []
    gaps: list[str] = []
    open_field: dict | None = None

    def flush() -> None:
        nonlocal open_field
        if open_field is None:
            return
        fields.append(
            RawHeaderField(
                ordinal=len(fields),
                name=open_field["name"],
                raw_value=raw[open_field["value_start"] : open_field["content_end"]].decode(
                    "latin-1"
                ),
                parse_status="ok",
                name_span=RawSpan(open_field["name_start"], open_field["name_len"], ""),
                value_span=RawSpan(
                    open_field["value_start"], open_field["content_end"] - open_field["value_start"], ""
                ),
                raw_span=RawSpan(
                    open_field["line_start"], open_field["term_end"] - open_field["line_start"], ""
                ),
            )
        )
        open_field = None

    for line_start, content_end, term_end in _iter_lines(raw, start, end):
        content = raw[line_start:content_end]
        if content == b"":
            break  # the empty line ends the region (the caller already excludes it)
        if content[:1] in _FOLD_PREFIXES and open_field is not None:
            open_field["content_end"] = content_end
            open_field["term_end"] = term_end
            continue
        name_bytes, value_start = _split_field(content, line_start)
        if name_bytes is not None:
            flush()
            open_field = {
                "name": name_bytes.decode("latin-1"),
                "name_start": line_start,
                "name_len": len(name_bytes),
                "value_start": value_start,
                "line_start": line_start,
                "content_end": content_end,
                "term_end": term_end,
            }
            continue
        flush()
        gaps.append(GAP_HEADERS_MALFORMED_LINE)
        fields.append(
            RawHeaderField(
                ordinal=len(fields),
                name="",
                raw_value=content.decode("latin-1"),
                parse_status="unknown",
                name_span=RawSpan(line_start, 0, ""),
                value_span=RawSpan(line_start, content_end - line_start, ""),
                raw_span=RawSpan(line_start, term_end - line_start, ""),
            )
        )
    flush()
    return fields, gaps


def _split_field(content: bytes, line_start: int) -> tuple[bytes | None, int]:
    """``(name bytes, value start)`` for a ``name: value`` line, else ``(None, 0)``."""
    colon = content.find(b":")
    if colon <= 0:
        return None, 0
    name = content[:colon]
    if any(byte < 33 or byte > 126 or byte == _NAME_STOP for byte in name):
        return None, 0
    return name, line_start + colon + 1


def _header_value(fields: list[RawHeaderField], raw: bytes, name: str) -> str | None:
    wanted = name.lower()
    for item in fields:
        if item.parse_status == "ok" and item.name.lower() == wanted:
            return raw[item.value_span.offset : item.value_span.end].decode("latin-1")
    return None


def _split_headers_body(raw: bytes, start: int, end: int) -> tuple[RawSpan, RawSpan, list[str]]:
    """Headers span (its closing empty line included), body span, gaps.

    No empty line at all means the message is headers-to-EOF (spike a04: stdlib
    takes this silently): the whole span is headers, the body is empty, and the
    gap ``body.headers_only`` is recorded.
    """
    for line_start, _content_end, term_end in _iter_lines(raw, start, end):
        if raw[line_start:_content_end] == b"":
            return RawSpan(start, term_end - start, ""), RawSpan(term_end, end - term_end, ""), []
    return RawSpan(start, end - start, ""), RawSpan(end, 0, ""), [GAP_BODY_HEADERS_ONLY]


# ------------------------------------------------------------- content types


def _split_params(value: str) -> tuple[str, dict[str, str]]:
    """Media type and parameters, quotes respected (a ``;`` inside a quoted
    boundary parameter is not a separator)."""
    pieces: list[str] = []
    current = ""
    quoted = False
    escaped = False
    for char in value:
        if escaped:
            current += char
            escaped = False
        elif char == "\\" and quoted:
            current += char
            escaped = True
        elif char == '"':
            quoted = not quoted
            current += char
        elif char == ";" and not quoted:
            pieces.append(current)
            current = ""
        else:
            current += char
    pieces.append(current)
    media = pieces[0].strip().lower()
    params: dict[str, str] = {}
    for piece in pieces[1:]:
        if "=" not in piece:
            continue
        key, _, raw_param = piece.partition("=")
        key = key.strip().lower()
        raw_param = raw_param.strip()
        if len(raw_param) >= 2 and raw_param[0] == '"' and raw_param[-1] == '"':
            raw_param = raw_param[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if key and key not in params:
            params[key] = raw_param
    return media, params


# ----------------------------------------------------------------- the walk


def _walk_part(
    raw: bytes,
    container_id: str,
    span: RawSpan,
    path: str,
    parent_path: str | None,
    parts: list[PartShape],
    regions: list[Region],
    state: _WalkState,
    depth: int,
) -> None:
    limits = state.limits
    WORK.add()
    if not _part_count_allows(limits, len(parts)):
        # Beyond the part cap: the part is not emitted, and its bytes are accounted as one
        # unread region. Checked first, so nothing of the part is read to decide it.
        _cap_hit(regions, state.caps, CAP_REASON_PART_COUNT, path, span)
        return
    headers, body, gaps = _split_headers_body(raw, span.offset, span.end)
    fields, field_gaps = header_fields_at(raw, span.offset, headers.end)
    prelude_span = None
    header_start = span.offset
    if path == "1":
        bom, mbox = leading_prelude(raw, span.offset)
        prelude_len = bom + mbox
        if prelude_len:
            prelude_span = RawSpan(span.offset, prelude_len, path)
            header_start = span.offset + prelude_len
            headers, body, gaps = _split_headers_body(raw, header_start, span.end)
            fields, field_gaps = header_fields_at(raw, header_start, headers.end)
    gaps.extend(field_gaps)
    if prelude_span is not None:
        regions.append(Region("prelude", path, prelude_span))

    if not _header_bytes_allows(limits, headers.length):
        # The header region is over the cap: it is not parsed field by field, the whole
        # part is skipped and its bytes are one unread region (the prelude, if any, was
        # already accounted, so the region starts at the headers).
        _cap_hit(
            regions,
            state.caps,
            CAP_REASON_HEADER_BYTES,
            path,
            RawSpan(header_start, span.end - header_start, path),
        )
        return

    content_type_value = _header_value(fields, raw, "content-type")
    media, params = _split_params(content_type_value) if content_type_value else ("", {})
    content_type = media or None
    declared_cte = _header_value(fields, raw, "content-transfer-encoding")
    declared_charset = params.get("charset")

    is_multipart = media.startswith("multipart/") and body.length > 0
    if is_multipart:
        boundary = params.get("boundary")
        raw_boundary = boundary.encode("latin-1", errors="replace") if boundary else b""
        segments = _segment(raw, body, raw_boundary) if raw_boundary else None
        if segments is None:
            gaps.append(GAP_BODY_NO_BOUNDARY_FOUND)
            is_multipart = False
        else:
            preamble, delimiters, chunks, epilogue, _closed, segment_gaps = segments
            gaps.extend(segment_gaps)
            if preamble.length:
                gaps.append(GAP_BODY_PREAMBLE_BYTES)
            if epilogue.length:
                gaps.append(GAP_BODY_EPILOGUE_BYTES)
            regions.append(Region("headers", path, headers))
            if preamble.length:
                regions.append(Region("preamble", path, preamble))
            parts.append(
                PartShape(
                    path=path,
                    part_id=part_id(container_id, span, content_hash(span.slice(raw))),
                    parent_path=parent_path,
                    content_type=content_type,
                    raw_span=span,
                    headers_span=headers,
                    body_span=body,
                    header_fields=fields,
                    decode_chain=DecodeChain(
                        declared_cte=_norm_cte(declared_cte),
                        declared_charset=declared_charset,
                    ),
                    gaps=_dedup(gaps),
                )
            )
            for index, chunk in enumerate(chunks):
                regions.append(Region("delimiter", path, delimiters[index]))
                child_span = RawSpan(chunk.offset, chunk.length, f"{path}.{index + 1}")
                if not _depth_allows(limits, depth + 1):
                    # Deeper than the nesting cap: the child is not descended into at all,
                    # and its bytes (the delimiters around it are accounted separately) are
                    # one unread region.
                    _cap_hit(regions, state.caps, CAP_REASON_DEPTH, child_span.locator, child_span)
                    continue
                _walk_part(
                    raw,
                    container_id,
                    child_span,
                    child_span.locator,
                    path,
                    parts,
                    regions,
                    state,
                    depth + 1,
                )
            for tail in delimiters[len(chunks) :]:
                regions.append(Region("delimiter", path, tail))
            if epilogue.length:
                regions.append(Region("epilogue", path, epilogue))
            return

    if not is_multipart:
        regions.append(Region("headers", path, headers))
        payload = raw[body.offset : body.end]
        budget, cap_reason = _decode_budget(state)
        used_cte, decoded, cte_fired, cte_gap = _decode_cte(payload, declared_cte, limit=budget)
        if decoded is None:
            # A cap stopped the decode: the part is SKIPPED, never truncated. Its decoded
            # size is not computed past the cap, its content sha256 is unknown (the
            # walker's existing idiom for a body it did not read: ``None``), no decode gap
            # is recorded and the bytes are accounted as one unread region -- the cap
            # region *is* the body region, so nothing is counted twice.
            _cap_hit(regions, state.caps, cap_reason, path, body)
            used_cte, cte_fired, cte_gap = None, False, None
            used_charset, encoding_source, charset_fired, charset_gap = None, None, False, None
        else:
            state.decoded_total += len(decoded)
            # A charset belongs to TEXT: a part with no Content-Type is text/plain by default
            # (RFC 2045), and anything else (a pdf, a png, an office zip) is bytes with no
            # charset. Running the text ladder over a binary part reported a windows-1252
            # reading and a false body.decode_destroyed_bytes for content that was never text.
            if content_type is None or content_type.lower().startswith("text/"):
                used_charset, encoding_source, charset_fired, charset_gap = _charset_ladder(
                    decoded, declared_charset
                )
            else:
                used_charset, encoding_source, charset_fired, charset_gap = None, None, False, None
            regions.append(Region("body", path, body))
        if cte_gap:
            gaps.append(cte_gap)
        if charset_gap:
            gaps.append(charset_gap)
        parts.append(
            PartShape(
                path=path,
                part_id=part_id(container_id, span, content_hash(span.slice(raw))),
                parent_path=parent_path,
                content_type=content_type,
                raw_span=span,
                headers_span=headers,
                body_span=body,
                header_fields=fields,
                decode_chain=DecodeChain(
                    declared_cte=_norm_cte(declared_cte),
                    declared_charset=declared_charset,
                    used_cte=used_cte,
                    used_charset=used_charset,
                    fallback_fired=cte_fired or charset_fired,
                ),
                encoding_source=encoding_source,
                body_sha256=None if decoded is None else sha256_hex(decoded),
                gaps=_dedup(gaps),
            )
        )


def _dedup(gaps: list[str]) -> list[str]:
    seen: list[str] = []
    for gap in gaps:
        if gap not in seen:
            seen.append(gap)
    return seen


def _norm_cte(declared: str | None) -> str | None:
    return declared.strip().lower() if declared else None


def _segment(
    raw: bytes, body: RawSpan, boundary: bytes
) -> tuple[RawSpan, list[RawSpan], list[RawSpan], RawSpan, bool, list[str]] | None:
    """Split a multipart body into preamble, delimiter regions, chunks, epilogue.

    Returns ``None`` when the declared boundary never appears. The CRLF that
    precedes a delimiter line is attached to the delimiter (RFC 2046), so the
    regions tile the body exactly. A missing close delimiter is recorded as
    ``body.boundary_disagreement`` (the declared grammar is not what the bytes
    say) and the tail runs to the end of the body; nothing is guessed.
    """
    lines = list(_iter_lines(raw, body.offset, body.end))
    delimiters: list[RawSpan] = []
    kinds: list[str] = []
    for index, (line_start, content_end, term_end) in enumerate(lines):
        content = raw[line_start:content_end]
        if not content.startswith(b"--" + boundary):
            continue
        rest = content[2 + len(boundary) :]
        if rest == b"" or rest.strip(b" \t") == b"":
            kind = "open"
        elif rest.startswith(b"--") and rest[2:].strip(b" \t") == b"":
            kind = "close"
        else:
            continue
        region_start = line_start
        if index > 0:
            prev_start, prev_content_end, prev_term_end = lines[index - 1]
            if prev_term_end == line_start and prev_content_end < prev_term_end:
                region_start = prev_content_end
        if delimiters and region_start < delimiters[-1].end:
            # Two adjacent delimiters (an empty part): the line ending in front of this one is
            # already inside the previous delimiter's region, so the part between them is empty
            # and nothing is attached twice. Without this the regions overlap and the chunk's
            # length goes negative.
            region_start = delimiters[-1].end
        delimiters.append(RawSpan(region_start, term_end - region_start, ""))
        kinds.append(kind)
    if not delimiters:
        return None
    gaps: list[str] = []
    preamble = RawSpan(body.offset, delimiters[0].offset - body.offset, "")
    closed = "close" in kinds
    if closed:
        close_at = kinds.index("close")
        delimiters = delimiters[: close_at + 1]
        kinds = kinds[: close_at + 1]
        epilogue = RawSpan(delimiters[-1].end, body.end - delimiters[-1].end, "")
    else:
        close_at = len(delimiters)
        epilogue = RawSpan(body.end, 0, "")
        gaps.append(GAP_BODY_BOUNDARY_DISAGREEMENT)
    chunks: list[RawSpan] = []
    for index in range(close_at):
        chunk_start = delimiters[index].end
        chunk_end = delimiters[index + 1].offset if index + 1 < len(delimiters) else body.end
        chunks.append(RawSpan(chunk_start, chunk_end - chunk_start, ""))
    return preamble, delimiters[: len(chunks) + 1], chunks, epilogue, closed, gaps


# ------------------------------------------------------------------ decoding


def _decode_cte(
    payload: bytes, declared: str | None, *, limit: int | None = None
) -> tuple[str | None, bytes | None, bool, str | None]:
    """Transfer decoding, recording the chain instead of trusting stdlib.

    No declared CTE means the RFC default ``7bit`` (identity). An unknown CTE is
    stdlib's *silent* raw-payload fallback (spike d03) -- here it is recorded:
    ``used_cte = None``, ``fallback_fired``, gap ``body.decode_fallback_used``.

    ``limit`` is the **caller's** decoded-byte budget for this part (item 4), or ``None``
    for the unbounded walk: ``None`` decodes the whole payload exactly as Phase 0 always
    has (so the frozen corpus cannot move), while a number decodes it in ``DECODE_CHUNK``
    -byte chunks and stops the moment the decoded count would exceed the budget -- a
    base64 or quoted-printable bomb is never expanded past the cap. A stopped decode
    returns ``used_cte = None`` and ``decoded = None``: the part is *skipped*, so the
    caller records the cap and never reports a body, not even a prefix, as the part's.

    The default ``None`` is the unbounded reading every caller that predates the caps
    (``emailextract.text`` re-decodes a part's body for its own text projection) already
    had, and is what it keeps: a caller that never sees a limit cannot change.
    """
    if declared is None:
        cte: str | None = "7bit"
    else:
        cte = declared.strip().lower()
    if cte in ("7bit", "8bit", "binary"):
        if limit is not None and len(payload) > limit:
            return None, None, False, None
        return cte, payload, False, None
    if cte == "quoted-printable":
        if limit is None:
            return "quoted-printable", quopri.decodestring(payload), False, None
        decoded, stopped = _quoted_printable_bounded(payload, limit)
        if stopped:
            return None, None, False, None
        return "quoted-printable", decoded, False, None
    if cte == "base64":
        if limit is None:
            try:
                compact = b"".join(payload.split())
                return "base64", base64.b64decode(compact, validate=True), False, None
            except (binascii.Error, ValueError):
                return None, payload, True, GAP_BODY_DECODE_FALLBACK_USED
        try:
            decoded, stopped = _base64_bounded(payload, limit)
        except (binascii.Error, ValueError):
            # The same rejection the whole-string ``validate=True`` decode makes: the bytes
            # are not base64, so the raw payload is the recorded fallback reading.
            if len(payload) > limit:
                return None, None, False, None
            return None, payload, True, GAP_BODY_DECODE_FALLBACK_USED
        if stopped:
            return None, None, False, None
        return "base64", decoded, False, None
    if limit is not None and len(payload) > limit:
        return None, None, False, None
    return None, payload, True, GAP_BODY_DECODE_FALLBACK_USED


def _base64_bounded(payload: bytes, limit: int) -> tuple[bytes, bool]:
    """``(decoded, stopped)``: the base64 payload decoded in ``DECODE_CHUNK``-byte chunks.

    Whitespace is dropped and complete 4-byte groups are decoded as they arrive (so the
    groups stay aligned across a chunk boundary), and the loop stops as soon as the decoded
    count exceeds ``limit`` -- so a base64 bomb is never expanded past the cap, and
    ``stopped`` says the part is skipped rather than decoded. It raises ``binascii.Error``
    on exactly the input ``base64.b64decode(compact, validate=True)`` rejects over the
    whole string: a compact length that is not a multiple of 4, or padding that is not on
    the last group.
    """
    out = bytearray()
    carry = b""
    held = b""
    for start in range(0, len(payload), DECODE_CHUNK):
        WORK.add()
        chunk = carry + b"".join(payload[start : start + DECODE_CHUNK].split())
        whole = len(chunk) - len(chunk) % 4
        for position in range(0, whole, 4):
            group = chunk[position : position + 4]
            if held:
                if b"=" in held:
                    raise binascii.Error("padding is not on the last group")
                out.extend(base64.b64decode(held, validate=True))
                if len(out) > limit:
                    return bytes(out), True
            held = group
        carry = chunk[whole:]
    if held:
        out.extend(base64.b64decode(held, validate=True))
    if carry:
        out.extend(base64.b64decode(carry, validate=True))
    return bytes(out), len(out) > limit


def _quoted_printable_bounded(payload: bytes, limit: int) -> tuple[bytes, bool]:
    """``(decoded, stopped)``: the QP payload decoded in ``DECODE_CHUNK``-byte chunks.

    Quoted-printable decoding is local -- an ``=XX`` escape or a line ending is at most
    three bytes -- so the payload is cut only at a boundary no escape and no CRLF spans.
    The chunks' decodes therefore concatenate to the whole payload's decode, and the loop
    stops as soon as the decoded count exceeds ``limit``.
    """
    out = bytearray()
    end = len(payload)
    start = 0
    while start < end:
        WORK.add()
        cut = _qp_chunk_end(payload, start, min(start + DECODE_CHUNK, end))
        out.extend(quopri.decodestring(payload[start:cut]))
        if len(out) > limit:
            return bytes(out), True
        start = cut
    return bytes(out), False


def _qp_chunk_end(payload: bytes, start: int, cut: int) -> int:
    """The first boundary at or after ``cut`` that no escape and no line ending straddles.

    A boundary is safe when the byte before it is neither ``=`` nor ``\\r`` and the two
    bytes before it are not ``=<hex>``; walking forward at most two bytes lands on one.
    """
    end = len(payload)
    while cut < end:
        if payload[cut - 1 : cut] in (b"=", b"\r") or (
            payload[cut - 2 : cut - 1] == b"=" and payload[cut - 1 : cut].lower() in _HEX_DIGITS
        ):
            cut += 1
            continue
        break
    return cut


def _charset_ladder(
    body: bytes, declared_charset: str | None
) -> tuple[str | None, EncodingSource | None, bool, str | None]:
    """The deterministic charset ladder (D13); never statistical, never chardet.

    Rungs run strictly. Only when no rung decodes is a replacement decode taken,
    and that lossy decode is recorded as ``body.decode_destroyed_bytes`` with
    ``encoding_source = fallback`` -- it is never the normal path, because it
    destroys byte round-trip.
    """
    if not body:
        return "us-ascii", EncodingSource.ASCII, False, None
    fallback_fired = False
    if declared_charset:
        try:
            body.decode(declared_charset, "strict")
            return declared_charset, EncodingSource.DECLARED_CHARSET, False, None
        except (LookupError, UnicodeDecodeError, ValueError):
            # ValueError: a name the codec registry refuses outright (a NUL in it)
            # is the same state as an unknown name -- the rung is not usable.
            fallback_fired = True
    if all(byte < 128 for byte in body):
        return "us-ascii", EncodingSource.ASCII, fallback_fired, (
            GAP_BODY_DECODE_FALLBACK_USED if fallback_fired else None
        )
    for rung in ("utf-8", "windows-1252"):
        try:
            body.decode(rung, "strict")
            source = (
                EncodingSource.UTF8_STRICT if rung == "utf-8" else EncodingSource.WINDOWS_1252
            )
            return rung, source, fallback_fired, (
                GAP_BODY_DECODE_FALLBACK_USED if fallback_fired else None
            )
        except UnicodeDecodeError:
            continue
    body.decode("windows-1252", "replace")  # the recorded last resort, never the normal path
    return (
        "windows-1252",
        EncodingSource.FALLBACK,
        True,
        GAP_BODY_DECODE_DESTROYED_BYTES,
    )
