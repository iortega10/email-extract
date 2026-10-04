"""Turn 1.1: the header region -- field paragraphs, folds, raw spans, the kind table.

This is the Phase 1 header stage over the **walker's one line model** (decision 8). It
does not introduce a second scanner: it reuses ``walk.header_fields_at`` for the field
paragraphs (duplicates kept, identity by ordinal, one field per obs-fold chain, a
malformed line fails open) and ``walk._iter_lines`` for the line boundaries, and adds the
things Phase 1 owns:

* the **tolerated leading prelude** (a UTF-8 BOM and/or an mbox ``From `` line, decision
  14) as its own region: the real headers start after it, and the gaps
  ``headers.leading_bom`` / ``headers.mbox_from_line`` are recorded here (never in the
  walker's Phase 0 ``part.gaps`` channel);
* the **duplicate-header** gap (a second field of a name that is unique per RFC 5322 3.6);
* the **lone-CR** gap (``body.lone_cr_line_terminator``) when the header region's line model
  split on a bare CR (decision 17 keeps the line model);
* the **kind table** (a closed header-NAME table) that assigns ``headers.projection``'s
  ``parsed_kind``;
* the RFC 2047 decode of unstructured text fields, which drives ``headers.decoded`` and the
  ``headers.encoded_word_invalid`` gap.

Decision 12: a label that disagrees with what this produces is a **finding**, never an
edit to the label. The kind table's default is ``text`` because the committed labels type
``Content-Type``, ``MIME-Version`` and every ``X-*`` field as ``text``; ``unparsed`` is the
explicit claimed-never-verified trace set (plus a malformed line), not "everything else".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from .addresses import AddressRow, parse_address_list
from .rfc2047 import DecodedValue, decode_encoded_words
from .rfc2231 import STRUCTURED_PARAMETERS, parse_parameters
from .walk import RawHeaderField, WalkResult, _iter_lines, header_fields_at, leading_prelude

__all__ = [
    "DUPLICATE_UNIQUE_HEADERS",
    "GAP_BODY_LONE_CR_LINE_TERMINATOR",
    "GAP_HEADERS_DUPLICATE_HEADER",
    "GAP_HEADERS_ENCODED_WORD_INVALID",
    "GAP_HEADERS_LEADING_BOM",
    "GAP_HEADERS_MBOX_FROM_LINE",
    "HeaderRegion",
    "address_rows",
    "classify",
    "decoded_rows",
    "fields_named",
    "header_region",
    "later_gaps",
    "parameter_rows",
    "projection_rows",
]

#: The Phase 1 gaps this stage records (design registry, ``docs/design/phase0-gaps.md``).
#: They ride in this module's own ``gaps`` field, **never** in the walker's Phase 0
#: ``part.gaps`` channel (the Phase 0 sidecars type ``part.gaps`` and are frozen).
GAP_HEADERS_DUPLICATE_HEADER: Final[str] = "headers.duplicate_header"
GAP_HEADERS_LEADING_BOM: Final[str] = "headers.leading_bom"
GAP_HEADERS_MBOX_FROM_LINE: Final[str] = "headers.mbox_from_line"
GAP_BODY_LONE_CR_LINE_TERMINATOR: Final[str] = "body.lone_cr_line_terminator"
GAP_HEADERS_ENCODED_WORD_INVALID: Final[str] = "headers.encoded_word_invalid"

#: The header names that must be **unique** per RFC 5322 3.6 and its MIME extensions
#: (RFC 2045 3/5.1): a second field of one of these fires ``headers.duplicate_header``.
#: ``Received``, ``Resent-*``, ``Comments``, ``Keywords``, ``Return-Path`` and the
#: ``Authentication-Results`` / ``DKIM-Signature`` / ``ARC-*`` trace fields are **not**
#: unique and never fire it (3.6.5/3.6.6).
DUPLICATE_UNIQUE_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "date",
        "from",
        "sender",
        "reply-to",
        "to",
        "cc",
        "bcc",
        "message-id",
        "in-reply-to",
        "references",
        "subject",
        "mime-version",
        "content-type",
        "content-transfer-encoding",
        "content-id",
        "content-description",
        "content-disposition",
    }
)

#: The closed header-NAME table: a lowercased field name to its ``parsed_kind``. The default
#: (not listed) is ``text`` -- the unstructured reading. A field whose name the table maps to
#: ``unparsed`` is a *claimed, never verified* trace field, and a malformed line is unparsed.
_KIND_TABLE: Final[dict[str, str]] = {
    # RFC 5322 3.4 address-list fields.
    **{
        name: "address_list"
        for name in (
            "from",
            "to",
            "cc",
            "bcc",
            "reply-to",
            "sender",
            "resent-from",
            "resent-to",
            "resent-cc",
            "resent-bcc",
            "resent-sender",
            "resent-reply-to",
        )
    },
    # RFC 5322 3.3 date-time fields.
    "date": "date_time",
    "resent-date": "date_time",
    # RFC 5322 3.6.4 message-id / list fields.
    "message-id": "message_id",
    "resent-message-id": "message_id",
    "content-id": "message_id",
    "in-reply-to": "message_id_list",
    "references": "message_id_list",
    # Claimed-never-verified trace fields (D2): recorded, never interpreted.
    "received": "unparsed",
    "return-path": "unparsed",
    "authentication-results": "unparsed",
    "dkim-signature": "unparsed",
    "arc-seal": "unparsed",
    "arc-message-signature": "unparsed",
    "arc-authentication-results": "unparsed",
}

_MESSAGE_ID: Final[re.Pattern[str]] = re.compile(r"<[^<>]*>")


@dataclass(frozen=True)
class HeaderRegion:
    """What Phase 1 measures from one part's header region.

    ``fields`` are the walker's field paragraphs, in order. ``gaps`` are this stage's own
    gap ids (duplicate / lone-CR / invalid encoded word), in first-seen order; ``prelude``
    are the tolerated-prelude gap ids. ``text_decodes`` maps a text-kind field's ordinal to
    its RFC 2047 decode; ``addresses`` maps an address-list field's ordinal to its parsed
    rows (Turn 1.2, :mod:`emailextract.addresses`). None of these are the walker's
    ``part.gaps``.
    """

    fields: list[RawHeaderField] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    prelude: list[str] = field(default_factory=list)
    text_decodes: dict[int, DecodedValue] = field(default_factory=dict)
    addresses: dict[int, list[AddressRow]] = field(default_factory=dict)

    def value_bytes(self, raw: bytes, item: RawHeaderField) -> bytes:
        """The verbatim value bytes of one field (between the colon and the content end)."""
        return raw[item.value_span.offset : item.value_span.end]


def classify(name: str) -> str:
    """The ``parsed_kind`` of a header name: the closed table, defaulting to ``text``.

    A malformed line (the walker's ``name == ""`` paragraph) is ``unparsed``.
    """
    if not name:
        return "unparsed"
    return _KIND_TABLE.get(name.lower(), "text")


def fields_named(fields: list[RawHeaderField], name: str) -> list[RawHeaderField]:
    """Every parsed field whose name matches ``name`` **case-insensitively**, in order.

    Lookup is by the lowercased name; the field's own ``name`` keeps its case for display
    (``mixed_case_header_and_param_names``). Duplicates are all returned -- nothing is
    reduced to "the" value silently (that reduction is the ``headers.duplicate_header`` gap).
    """
    wanted = name.lower()
    return [item for item in fields if item.parse_status == "ok" and item.name.lower() == wanted]


def _unique_conflicts(fields: list[RawHeaderField]) -> list[str]:
    """One ``headers.duplicate_header`` per unique-name field that appears more than once."""
    counts: dict[str, int] = {}
    for item in fields:
        if item.parse_status != "ok":
            continue
        lowered = item.name.lower()
        if lowered in DUPLICATE_UNIQUE_HEADERS:
            counts[lowered] = counts.get(lowered, 0) + 1
    return [
        GAP_HEADERS_DUPLICATE_HEADER
        for _name, count in sorted(counts.items())
        if count > 1
    ]


def _lone_cr(raw: bytes, start: int, end: int) -> bool:
    """Whether the header region's line model split on a bare CR (before the empty line)."""
    for line_start, content_end, term_end in _iter_lines(raw, start, end):
        if raw[line_start:content_end] == b"":
            return False
        if term_end - content_end == 1 and raw[content_end : content_end + 1] == b"\r":
            return True
    return False


def header_region(raw: bytes, result: WalkResult, *, max_work_units: int) -> HeaderRegion:
    """Scan the message's **top-level** header region (the part ``result.parts[0]``).

    The walker has already accounted the tolerated prelude as its own region and started
    the headers after it; the prelude gaps are re-derived here from the part's raw span so
    the walker's ``part.gaps`` channel stays untouched (decision 14).
    """
    if not result.parts:
        return HeaderRegion()
    part = result.parts[0]
    start = part.headers_span.offset
    end = part.headers_span.end
    fields, malformed = header_fields_at(raw, start, end)

    gaps: list[str] = []
    gaps.extend(_unique_conflicts(fields))
    if _lone_cr(raw, start, end):
        gaps.append(GAP_BODY_LONE_CR_LINE_TERMINATOR)

    text_decodes: dict[int, DecodedValue] = {}
    for item in fields:
        if classify(item.name) != "text":
            continue
        decoded = decode_encoded_words(
            raw[item.value_span.offset : item.value_span.end], max_work_units=max_work_units
        )
        text_decodes[item.ordinal] = decoded
        if decoded.invalid:
            gaps.append(GAP_HEADERS_ENCODED_WORD_INVALID)

    bom, mbox = leading_prelude(raw, part.raw_span.offset)
    prelude: list[str] = []
    if bom:
        prelude.append(GAP_HEADERS_LEADING_BOM)
    if mbox:
        prelude.append(GAP_HEADERS_MBOX_FROM_LINE)

    _ = malformed  # the walker already carries headers.malformed_line in part.gaps
    address_lists: dict[int, list[AddressRow]] = {}
    for item in fields:
        if item.parse_status != "ok" or classify(item.name) != "address_list":
            continue
        address_lists[item.ordinal] = parse_address_list(
            raw[item.value_span.offset : item.value_span.end],
            base_offset=item.value_span.offset,
            max_work_units=max_work_units,
        )
    return HeaderRegion(
        fields=fields,
        gaps=_dedup(gaps),
        prelude=prelude,
        text_decodes=text_decodes,
        addresses=address_lists,
    )


def _dedup(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _parsed_value(item: RawHeaderField, region: HeaderRegion) -> str | None:
    """The scalar a field's kind yields this turn, or ``None`` where it is deferred.

    ``text`` yields the RFC 2047-decoded value, ``message_id`` the trimmed id token,
    ``address_list`` the first addr-spec the tokenizer read (Turn 1.2); the ``date_time``
    scalar needs the Turn 1.3 parser and is **not** computed here (never with the stdlib)
    -- the caller reports it deferred by name.
    """
    kind = classify(item.name)
    if kind == "text":
        decoded = region.text_decodes.get(item.ordinal)
        if decoded is None:
            return item.raw_value.strip()
        return decoded.text.strip()
    if kind == "message_id":
        return item.raw_value.strip()
    if kind == "message_id_list":
        found = _MESSAGE_ID.findall(item.raw_value)
        return found[-1] if found else item.raw_value.strip()
    if kind == "address_list":
        for row in region.addresses.get(item.ordinal, []):
            if row.addr_spec is not None:
                return row.addr_spec
        return None
    return None


def address_rows(region: HeaderRegion) -> list[list[object]]:
    """``headers.addresses`` rows: ``[ordinal, field_name, [[row, ...], ...]], ...``.

    One entry per **address-list field** the header region carries, in ordinal order, each
    holding the tokenizer's rows (Turn 1.2). A group's members are the flat rows beside the
    group row (the sidecars type them flat); each row is
    ``[raw_offset, raw_length, display_name, addr_spec, state, reason_id]``.
    """
    return [
        [item.ordinal, item.name, [row.as_fact_row() for row in region.addresses[item.ordinal]]]
        for item in region.fields
        if item.ordinal in region.addresses
    ]


def projection_rows(region: HeaderRegion) -> list[list[object]]:
    """``headers.projection`` rows: ``[ordinal, name, raw_value, parsed_kind, parsed_value]``.

    ``raw_value`` keeps its folds (latin-1 view); ``parsed_value`` is ``None`` where the kind
    is ``unparsed`` or needs a later parser (``date_time``).
    """
    return [
        [item.ordinal, item.name, item.raw_value, classify(item.name), _parsed_value(item, region)]
        for item in region.fields
    ]


def decoded_rows(region: HeaderRegion) -> list[list[object]]:
    """``headers.decoded`` rows: ``[ordinal, decoded_text]`` for fields with a decoded word."""
    return [
        [ordinal, decoded.text.strip()]
        for ordinal, decoded in sorted(region.text_decodes.items())
        if decoded.decoded
    ]


def parameter_rows(raw: bytes, region: HeaderRegion) -> list[list[object]]:
    """``headers.parameters`` rows for the top-level ``Content-Type``/``Content-Disposition``.

    One row per structured parameter (the closed set: a boundary, a charset, a name, a
    filename) the reader decodes: ``[ordinal, field_name, parameter, decoded_value,
    decode_state, fallback_reason]``.
    """
    rows: list[list[object]] = []
    for item in region.fields:
        if item.parse_status != "ok":
            continue
        if item.name.lower() not in ("content-type", "content-disposition"):
            continue
        value = raw[item.value_span.offset : item.value_span.end]
        for parameter in parse_parameters(value, item.value_span.offset):
            if parameter.name not in STRUCTURED_PARAMETERS:
                continue
            rows.append(
                [
                    item.ordinal,
                    item.name,
                    parameter.name,
                    parameter.value,
                    parameter.state,
                    parameter.fallback_reason,
                ]
            )
    return rows


def later_gaps(region: HeaderRegion) -> list[tuple[str, str]]:
    """The ``(gap_id, locator)`` pairs this stage records for ``gaps.later`` (all on ``1``).

    The prelude gaps and this stage's own gaps ride the Phase 1 ``gaps.later`` fact, never
    the walker's Phase 0 ``part.gaps`` (decision 3).
    """
    return [(gap_id, "1") for gap_id in [*region.prelude, *region.gaps]]
