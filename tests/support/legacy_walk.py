"""A frozen reference: the **recursive** walker ``_walk_part`` that Turn 1.11 replaced.

``emailextract/walk.py::_walk_part`` used to call itself to descend into a nested multipart child
(``walk.py:709`` at Turn 1.10b). Turn 1.11 rewrote it as an explicit-stack loop that must produce
byte-for-byte the same :class:`~emailextract.walk.WalkResult`. This module is that old traversal,
copied verbatim so it cannot drift, with a ``walk`` driver that mirrors the live one. It is a
**test-only** reference: the library never imports it, and it is never imported by anything but
``tests/test_walk_iterative.py``.

Only the traversal is frozen here; the byte-level helpers that measure one part's spans, headers,
segments and decode chain are the live ones, imported from :mod:`emailextract.walk`. That is
deliberate: it isolates the one thing Turn 1.11 changed -- the stack discipline -- so the
differential test compares the recursive descent against the iterative one over the *same*
measurement code, and the record shapes are the live classes, so the two results compare equal
field by field (and by ``==``).
"""

from __future__ import annotations

from emailextract.container import Container
from emailextract.ids import NOT_BUILT_IN_PHASE0, RawSpan, content_hash, part_id, sha256_hex
from emailextract.model import TriState, TriValue
from emailextract.walk import (
    CAP_REASON_DEPTH,
    CAP_REASON_HEADER_BYTES,
    CAP_REASON_PART_COUNT,
    GAP_BODY_EPILOGUE_BYTES,
    GAP_BODY_NO_BOUNDARY_FOUND,
    GAP_BODY_PREAMBLE_BYTES,
    UNBUILT_SECTIONS,
    WORK,
    DecodeChain,
    PartShape,
    Region,
    UnknownSection,
    WalkResult,
    _WalkState,
    _cap_hit,
    _charset_ladder,
    _decode_budget,
    _decode_cte,
    _dedup,
    _depth_allows,
    _header_bytes_allows,
    _norm_cte,
    _part_count_allows,
    _segment,
    _split_headers_body,
    _split_params,
    _header_value,
    header_fields_at,
    leading_prelude,
)

__all__ = ["walk"]


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
    """The recursive body (frozen, Turn 1.10b): it descends by calling itself."""
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


def walk(container: Container, *, limits=None) -> WalkResult:
    """The recursive driver (frozen): the same output as :func:`emailextract.walk.walk`."""
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
