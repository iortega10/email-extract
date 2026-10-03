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
"""

from __future__ import annotations

import base64
import binascii
import quopri
from dataclasses import dataclass, field

from .container import Container
from .ids import NOT_BUILT_IN_PHASE0, RawSpan, content_hash, part_id, sha256_hex
from .model import ContainerKind, DecodeChain, EncodingSource, TriState, TriValue

__all__ = [
    "PartShape",
    "RawHeaderField",
    "Region",
    "UnknownSection",
    "WalkResult",
    "header_fields_at",
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
_TEXT_LADDER = ("us-ascii", "utf-8", "windows-1252")


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
    own accounted bytes) or ``delimiter`` (a boundary line, its preceding CRLF
    attached per RFC 2046). The regions tile the raw message exactly.
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


def walk(container: Container) -> WalkResult:
    """Measure ``container``: parts, spans, decode chains, accounted regions."""
    raw = container.raw_bytes()
    container_id = container.container_hash()
    parts: list[PartShape] = []
    regions: list[Region] = []
    _walk_part(raw, container_id, RawSpan(0, len(raw), "1"), "1", None, parts, regions)
    unknowns = [
        UnknownSection(
            section, TriValue(state=TriState.UNKNOWN, reason_id=NOT_BUILT_IN_PHASE0)
        )
        for section in UNBUILT_SECTIONS
    ]
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


def _iter_lines(raw: bytes, start: int, end: int):
    """Yield ``(line_start, content_end, term_end)`` over ``[start, end)``.

    ``content`` is the line without its terminator; the terminator is ``CRLF``,
    ``LF`` or ``CR``, and a last line at EOF may have none.
    """
    position = start
    while position < end:
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
) -> None:
    headers, body, gaps = _split_headers_body(raw, span.offset, span.end)
    fields, field_gaps = header_fields_at(raw, span.offset, headers.end)
    gaps.extend(field_gaps)

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
                _walk_part(raw, container_id, child_span, child_span.locator, path, parts, regions)
            for tail in delimiters[len(chunks) :]:
                regions.append(Region("delimiter", path, tail))
            if epilogue.length:
                regions.append(Region("epilogue", path, epilogue))
            return

    if not is_multipart:
        regions.append(Region("headers", path, headers))
        payload = raw[body.offset : body.end]
        used_cte, decoded, cte_fired, cte_gap = _decode_cte(payload, declared_cte)
        used_charset, encoding_source, charset_fired, charset_gap = _charset_ladder(
            decoded, declared_charset
        )
        if cte_gap:
            gaps.append(cte_gap)
        if charset_gap:
            gaps.append(charset_gap)
        regions.append(Region("body", path, body))
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
                body_sha256=sha256_hex(decoded),
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


def _decode_cte(payload: bytes, declared: str | None) -> tuple[str | None, bytes, bool, str | None]:
    """Transfer decoding, recording the chain instead of trusting stdlib.

    No declared CTE means the RFC default ``7bit`` (identity). An unknown CTE is
    stdlib's *silent* raw-payload fallback (spike d03) -- here it is recorded:
    ``used_cte = None``, ``fallback_fired``, gap ``body.decode_fallback_used``.
    """
    if declared is None:
        return "7bit", payload, False, None
    cte = declared.strip().lower()
    if cte in ("7bit", "8bit", "binary"):
        return cte, payload, False, None
    if cte == "quoted-printable":
        return "quoted-printable", quopri.decodestring(payload), False, None
    if cte == "base64":
        try:
            compact = b"".join(payload.split())
            return "base64", base64.b64decode(compact, validate=True), False, None
        except (binascii.Error, ValueError):
            return None, payload, True, GAP_BODY_DECODE_FALLBACK_USED
    return None, payload, True, GAP_BODY_DECODE_FALLBACK_USED


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
        except (LookupError, UnicodeDecodeError):
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
