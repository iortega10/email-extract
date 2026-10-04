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

Addresses and dates are deliberately **not** here: they are an advisory diff owned by Turn
1.2 / 1.3. Where the stdlib is authoritative (field order and duplicates, RFC 2045 5.2
defaults, RFC 2046 5.1.5 digest children, ``message/rfc822`` nesting, valid RFC 2047) a
disagreement is the package's bug. Where the stdlib **shares the misreading** a comparison
proves nothing and is excluded -- see :data:`SHARED_MISREADING`.
"""

from __future__ import annotations

import codecs
import email
import email.header
import email.policy
from dataclasses import dataclass
from typing import Final

__all__ = [
    "SHARED_MISREADING",
    "ScanResult",
    "decoded_header_value",
    "own_raw_fields",
    "scan",
    "split_header_block",
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
