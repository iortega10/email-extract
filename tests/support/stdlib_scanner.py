"""Turn 1.1: the independent stdlib header scanner -- **three comparisons and no more**.

This is an independent checker (build spec, "The independent checks"): it imports
**nothing** from ``emailextract``, has its own header/body split, its own field split and
its own charset resolution (``codecs.lookup``), and shares no boundary regex with the
package. Its three comparisons are:

* **(a) field names and order** from the ``compat32`` **raw** view only
  (``email.message_from_bytes(..., policy=email.policy.compat32)`` and ``.raw_items()``);
  never ``policy.default``'s ``headerregistry``, which re-types and re-orders;
* **(b) the content-type tree** (each part's ``get_content_type()`` in ``walk()`` order);
* **(c) the decoded text** of benign leaves -- a header value's RFC 2047 decode, valid words
  only (the stdlib decodes an invalid word **silently** with ``defects = []``).

Addresses and dates are deliberately **not** part of the three gated comparisons: they are an
**advisory** diff, owned by Turn 1.2 (addresses) and Turn 1.3 (dates). Where the stdlib is
authoritative (field order and duplicates, RFC 2045 5.2 defaults, RFC 2046 5.1.5 digest
children, ``message/rfc822`` nesting, valid RFC 2047) a disagreement is the package's bug.
Where the stdlib **shares the misreading** a comparison proves nothing and is excluded -- see
:data:`SHARED_MISREADING`, :data:`SHARED_ADDRESS_MISREADING` and :data:`SHARED_DATE_MISREADING`.
"""

from __future__ import annotations

import codecs
import email
import email.header
import email.policy
import email.utils
import sys
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "ADDRESS_FIELD_NAMES",
    "BENIGN_TEXT_CHARSETS",
    "DATE_FIELD_NAMES",
    "SHARED_ADDRESS_MISREADING",
    "SHARED_DATE_MISREADING",
    "SHARED_MISREADING",
    "SHARED_TEXT_MISREADING",
    "ScanResult",
    "StdlibDate",
    "StdlibLeafText",
    "addr_is_locatable",
    "address_fields",
    "date_fields",
    "decoded_header_value",
    "decoded_leaf_texts",
    "interpreter_label",
    "own_raw_fields",
    "scan",
    "split_header_block",
    "stdlib_address_pairs",
    "stdlib_date",
    "stdlib_parseaddr",
]

#: The cases where the stdlib shares the package's misreading, so a comparison proves
#: nothing and is excluded from any gate (build spec, "The independent checks"). Each is a
#: closed reason id.
SHARED_MISREADING: Final[dict[str, str]] = {
    "invalid_encoded_word": "the stdlib decodes an invalid encoded word silently, with defects = []",
    "defects_vs_bytes": "stdlib `defects` and the returned bytes disagree (email-spike b02)",
    "lone_cr_line_break": "the stdlib feedparser splits on a lone CR exactly as the walker does",
    "leading_bom": "the stdlib reads the BOM and the first header line as one defect",
    "mbox_from_line": "the stdlib reads the mbox `From ` line as a malformed header",
}

#: The RFC 5322 3.4 address-list field names (Turn 1.2): the fields an address diff covers.
ADDRESS_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
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
    }
)

#: The **closed** reasons the stdlib is known to read an address differently (Turn 1.2).
#: Each is a misreading a gate would prove nothing about, so the address diff is advisory:
#: printed, never asserted on. ``no_span`` is the one property the turn does assert around
#: (:func:`stdlib_parseaddr` returns no offsets at all, so the own tokenizer must never drop
#: an address the stdlib cannot locate).
SHARED_ADDRESS_MISREADING: Final[dict[str, str]] = {
    "group_flattened": "getaddresses flattens a group and drops its ':' ';' structure",
    "empty_group_lost": "'undisclosed-recipients:;' gives [('', '')]",
    "trailing_comma": "a trailing comma yields a spurious empty address",
    "garbage_passthrough": "garbage is returned as a bogus address rather than declined",
    "smtputf8_mangled": "the stdlib may not keep a non-ASCII local part or IDN domain verbatim",
    "route_kept": "an obs-route is not separated from the addr-spec",
    "no_span": "neither parseaddr nor getaddresses returns byte offsets (D2 needs a span per address)",
}


@dataclass(frozen=True)
class ScanResult:
    """The stdlib's own reading: field names in order, the content-type tree, decoded values."""

    field_names: tuple[str, ...]
    content_types: tuple[str, ...]
    decoded: tuple[tuple[str, str], ...]


def split_header_block(data: bytes) -> bytes:
    """This scanner's own header/body split: the bytes before the first empty line.

    Its own rule (no shared regex): the earliest of ``\\r\\n\\r\\n``, ``\\n\\n`` or
    ``\\r\\r`` ends the header block; input with no empty line is headers-to-EOF.
    """
    ends = [
        index
        for index in (data.find(b"\r\n\r\n"), data.find(b"\n\n"), data.find(b"\r\r"))
        if index != -1
    ]
    return data[: min(ends)] if ends else data


def own_raw_fields(block: bytes) -> list[tuple[bytes, bytes]]:
    """This scanner's own field split: ``(name bytes, value bytes)`` in order, folds joined.

    A line starting with SP or HTAB continues the previous field; a line with a colon is a
    ``name: value`` field; anything else is skipped (this scanner never gates on malformed
    lines -- that is the package's own gap).
    """
    fields: list[tuple[bytes, bytes]] = []
    for line in block.split(b"\n"):
        if line.endswith(b"\r"):
            line = line[:-1]
        if line[:1] in (b" ", b"\t") and fields:
            name, value = fields[-1]
            fields[-1] = (name, value + b"\r\n" + line)
        elif b":" in line:
            name, _, value = line.partition(b":")
            fields.append((name, value))
    return fields


def decoded_header_value(value: bytes) -> str:
    """Decode one header value with the stdlib and join the pieces (its own charset lookup).

    The stdlib resolves a charset through its own alias table; a charset it cannot resolve
    is decoded as latin-1. Only valid words are compared.
    """
    pieces = email.header.decode_header(value.decode("latin-1"))
    out: list[str] = []
    for text, charset in pieces:
        if isinstance(text, bytes):
            name = charset or "latin-1"
            try:
                codecs.lookup(name)
            except LookupError:
                name = "latin-1"
            out.append(text.decode(name, "replace"))
        else:
            out.append(text)
    return "".join(out)


def scan(data: bytes) -> ScanResult:
    """The stdlib's reading of ``data``: (a) names/order, (b) content-type tree, (c) decodes."""
    message = email.message_from_bytes(data, policy=email.policy.compat32)
    names = tuple(name for name, _value in message.raw_items())
    content_types = tuple(part.get_content_type() for part in message.walk())
    decoded = tuple(
        (name.decode("latin-1"), decoded_header_value(value))
        for name, value in own_raw_fields(split_header_block(data))
        if b"=?" in value
    )
    return ScanResult(field_names=names, content_types=content_types, decoded=decoded)


def address_fields(data: bytes) -> list[tuple[str, bytes]]:
    """This scanner's own reading of the address fields: ``(lowercased name, value bytes)``.

    Uses its own :func:`split_header_block` / :func:`own_raw_fields` (no shared regex) and its
    own field-name list (:data:`ADDRESS_FIELD_NAMES`); the value is the raw bytes, so the
    advisory diff is over the same bytes the package's tokenizer reads.
    """
    fields: list[tuple[str, bytes]] = []
    for name, value in own_raw_fields(split_header_block(data)):
        lowered = name.decode("latin-1").lower()
        if lowered in ADDRESS_FIELD_NAMES:
            fields.append((lowered, value))
    return fields


def stdlib_address_pairs(value: bytes) -> list[tuple[str, str]]:
    """``email.utils.getaddresses`` on one field value (the stdlib's advisory reading)."""
    return [(name, addr) for name, addr in email.utils.getaddresses([value.decode("latin-1")])]


def stdlib_parseaddr(value: bytes) -> tuple[str, str]:
    """``email.utils.parseaddr`` on one field value -- the entry point D2 cannot use."""
    return email.utils.parseaddr(value.decode("latin-1"))


def addr_is_locatable(value: bytes, addr: str) -> bool:
    """Whether ``addr``'s bytes can be located in the raw value (the span-loss test).

    A stdlib result that cannot be located is exactly what D2 forbids: the package must then
    carry a byte span of its own (or decline the address with a reason), never drop it.
    """
    if not addr:
        return False
    for encoded in (addr.encode("utf-8", "ignore"), addr.encode("latin-1", "ignore")):
        if encoded and encoded in value:
            return True
    return False


#: The RFC 5322 3.3 date-time field names (Turn 1.3): the fields the advisory date diff covers.
DATE_FIELD_NAMES: Final[frozenset[str]] = frozenset({"date", "resent-date"})

#: The **closed** reasons the stdlib is known to read a Date differently (Turn 1.3). A
#: disagreement behind one of these proves nothing about the package, so the date diff is
#: advisory: printed, never asserted on.
SHARED_DATE_MISREADING: Final[dict[str, str]] = {
    "minus_zero_read_as_plus_zero": "parsedate_tz rewrites the '-0000' token to offset 0 (0), "
    "so the zone STATE the design's D2 preserves is lost",
    "no_zone_is_naive": "parsedate_to_datetime returns a NAIVE datetime for a missing zone "
    "(and for '-0000'), so no UTC instant is claimed at all",
    "naive_read_as_utc": "reading that naive datetime as UTC would invent a zone the field "
    "never stated",
    "invalid_repaired": "parsedate_tz returns a 9-tuple with the fields it could guess rather "
    "than declining an unparseable value the design names headers.invalid_date",
    "offset_out_of_range_applied": "the stdlib accepts any 4-digit offset (e.g. +9960) that "
    "the design's +/-9959 limit rejects",
    "obs_year_mapping": "the stdlib's obs- (2- and 3-digit) year mapping is its own, so a year "
    "it agrees on is not evidence the package's RFC 5322 4.3 rule is right",
    "obs_zone_table": "the stdlib maps the US obs-zone names, like the package does, so "
    "agreement on EST/PDT proves nothing",
}


@dataclass(frozen=True)
class StdlibDate:
    """The stdlib's advisory reading of one Date value: recorded-only run input, never a gate.

    ``parsed_tz`` is ``email.utils.parsedate_tz``'s tuple (or ``None``); ``moment`` is
    ``parsedate_to_datetime``'s ISO rendering (or ``None`` when it raised); ``naive`` says that
    the datetime came back with no ``tzinfo``; ``error`` is the exception text, kept so a diff
    row can show it.
    """

    parsed_tz: tuple[Any, ...] | None
    moment: str | None
    naive: bool
    error: str | None


def date_fields(data: bytes) -> list[tuple[str, bytes]]:
    """This scanner's own reading of the Date fields: ``(lowercased name, value bytes)``.

    Its own :func:`split_header_block` / :func:`own_raw_fields` and its own field-name list
    (:data:`DATE_FIELD_NAMES`); the value is the raw bytes, so the advisory diff is over the
    same bytes the package's parser reads.
    """
    fields: list[tuple[str, bytes]] = []
    for name, value in own_raw_fields(split_header_block(data)):
        lowered = name.decode("latin-1").lower()
        if lowered in DATE_FIELD_NAMES:
            fields.append((lowered, value))
    return fields


def stdlib_date(value: bytes) -> StdlibDate:
    """Run both stdlib date entry points over one value and keep everything, including a raise."""
    text = value.decode("latin-1")
    parsed_tz = email.utils.parsedate_tz(text)
    try:
        moment = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError) as error:  # the stdlib's own failure mode
        return StdlibDate(parsed_tz=parsed_tz, moment=None, naive=False, error=f"{type(error).__name__}: {error}")
    return StdlibDate(
        parsed_tz=parsed_tz, moment=moment.isoformat(), naive=moment.tzinfo is None, error=None
    )


def interpreter_label() -> str:
    """The interpreter and patch level, as a recorded-only run input.

    The stdlib's date behaviour differs across versions and patch levels (operating rule 2), so
    the advisory diff is printed with the interpreter that produced it; it is never keyed on.
    """
    return f"CPython {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


#: The **closed** reasons the stdlib is known to read a leaf's decoded **text** differently
#: (Turn 1.4). Each is a case where a comparison proves nothing -- either the stdlib shares the
#: package's misreading, or the two read different trees -- so the text diff is a gated
#: comparison only over the benign leaves this list leaves out.
SHARED_TEXT_MISREADING: Final[dict[str, str]] = {
    "unknown_charset": "an unresolvable charset is decoded latin-1 by the stdlib and declined "
    "by the package's ladder, so the two texts are not readings of the same rule",
    "non_identity_cte": "a base64/quoted-printable part has no within-part byte span, so the "
    "package's text is not a re-decode of the bytes the stdlib hands back",
    "truncated_base64": "the stdlib's base64 is lenient exactly where the package's falls back "
    "and keeps the raw payload verbatim",
    "malformed_qp": "the stdlib repairs a stray '=' or a bad hex pair exactly where the package "
    "keeps the bytes verbatim",
    "decode_fallback": "the package's ladder took a fallback rung (or the lossy replacement "
    "decode); the stdlib's own repair is not that rung",
    "stateful_charset": "a stateful charset (ISO-2022-*, HZ) and the stdlib disagree on how "
    "much of the escape state belongs to a leaf's slice",
    "flowed": "a format=flowed part is space-unstuffed by the package; the stdlib never is",
    "no_recursion": "a message/rfc822 child is recursed by the stdlib and is a leaf for the "
    "package, so the leaf lists differ",
    "leaf_count_mismatch": "the two walkers found a different number of text leaves, so there "
    "is nothing to pair up (a structural difference, never a text difference)",
    "leading_bom": "the stdlib reads a leading UTF-8 BOM and the first header line as the "
    "body, so the two read different bytes",
    "malformed_header_line": "a field name the stdlib refuses (a NUL, a non-ASCII byte) ends "
    "its header block earlier than the walker's fail-open rule does",
    "non_text_leaf": "the part is not a text leaf for the package (no charset ladder ran)",
}


@dataclass(frozen=True)
class StdlibLeafText:
    """The stdlib's own reading of one leaf's text: recorded-only run input, never a gate."""

    content_type: str
    charset: str | None
    transfer_encoding: str | None
    text: str | None
    error: str | None


def decoded_leaf_texts(data: bytes) -> tuple[StdlibLeafText, ...]:
    """The stdlib's decoded **text** for every text leaf, in ``walk()`` order.

    Its own reading through ``email.message_from_bytes`` (compat32) and ``get_payload`` with
    ``decode=True``: the charset is the stdlib's own resolution, and a part the stdlib cannot
    decode records the exception text rather than raising. This is the third comparison's
    input (the text analogue of :func:`scan`'s decoded header values); the *exclusions* are
    :data:`SHARED_TEXT_MISREADING`, applied by the test, never here.
    """
    message = email.message_from_bytes(data, policy=email.policy.compat32)
    leaves: list[StdlibLeafText] = []
    for part in message.walk():
        if part.get_content_maintype() != "text":
            continue
        content_type = part.get_content_type()
        charset = part.get_content_charset()
        encoding = part.get("Content-Transfer-Encoding")
        try:
            payload = part.get_payload(decode=True)
            if payload is None:  # a multipart or an undecodable part: no leaf text at all
                continue
            name = charset or "latin-1"
            try:
                codecs.lookup(name)
            except (LookupError, ValueError, TypeError):
                name = "latin-1"
            leaves.append(
                StdlibLeafText(
                    content_type=content_type,
                    charset=charset,
                    transfer_encoding=encoding,
                    text=payload.decode(name, "replace"),
                    error=None,
                )
            )
        except Exception as error:  # noqa: BLE001 -- recorded, never raised (advisory diff)
            leaves.append(
                StdlibLeafText(
                    content_type=content_type,
                    charset=charset,
                    transfer_encoding=encoding,
                    text=None,
                    error=f"{type(error).__name__}: {error}",
                )
            )
    return tuple(leaves)


#: The charsets whose decode the stdlib and the package must agree on for the text comparison
#: to be a gate: the single-byte and UTF-8 leaves, resolved to the same codec on both sides.
BENIGN_TEXT_CHARSETS: Final[frozenset[str]] = frozenset(
    {"ascii", "utf-8", "iso8859-1", "cp1252"}
)
