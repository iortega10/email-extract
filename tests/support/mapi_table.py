"""Turn 1b.4: property-table bytes, typed from [MS-OXMSG] -- a test-support builder.

This is the *independent* side of the ``mapi.py`` comparison (build spec rule 5): every
entry here is typed from [MS-OXMSG] 2.2.1.1, from the observed Outlook layout
(``docs/design/email-spike.md`` B1-B4) or from a fixture's description in
``docs/design/phase1b-fixtures.md`` -- never read out of ``mapi.py`` and never out of a
reader's output. ``tools/make_msg_fixtures.py`` builds the committed ``.msg`` fixtures
through it, and the tests use it to build property tables in memory. It imports no
``emailextract`` module.

The layout, once more ([MS-OXMSG] 2.2.1.1):

* the top-level ``__properties_version1.0`` opens on a **32-byte** header whose
  ``@16``/``@20`` words are the recipient and attachment counts (B2); a recipient,
  attachment or embedded-message table opens on an **8-byte** header;
* each entry is 16 bytes: the ``u32 = (tag << 16) | type`` word, a ``u32`` flags word,
  then 8 value bytes;
* a fixed-size value lives inline; a variable-size entry puts its declared size in the
  first word (``d0``) of the value field; a storage-backed entry (``000D``) has no value.
"""

from __future__ import annotations

import struct
from typing import Iterable

# [MS-OXMSG] 2.2.1.1 property types.
PT_NULL = 0x0001
PT_I2 = 0x0002
PT_LONG = 0x0003
PT_R4 = 0x0004
PT_DOUBLE = 0x0005
PT_CURRENCY = 0x0006
PT_APPTIME = 0x0007
PT_ERROR = 0x000A
PT_BOOLEAN = 0x000B
PT_OBJECT = 0x000D
PT_I8 = 0x0014
PT_STRING8 = 0x001E
PT_UNICODE = 0x001F
PT_SYSTIME = 0x0040
PT_BINARY = 0x0102

#: [MS-OXMSG] 2.2.1.1: the multi-valued flag; the base type is ``type & 0x0FFF``.
MV_FLAG = 0x1000

#: The two header sizes (B2).
HEADER_SIZE_TOP = 32
HEADER_SIZE_SUB = 8

#: The observed tags the fixtures use.
PROP_MESSAGE_CLASS = 0x001A
PROP_SUBJECT = 0x0037
PROP_TRANSPORT_HEADERS = 0x007D
PROP_BODY_PLAIN = 0x1000
PROP_BODY_HTML = 0x1013
PROP_INTERNET_CODEPAGE = 0x3FDE
PROP_MESSAGE_CODEPAGE = 0x3FFD
PROP_RECIPIENT_TYPE = 0x0C15
PROP_RECIPIENT_DISPLAY = 0x3001
PROP_RECIPIENT_ADDRESS_TYPE = 0x3002
PROP_RECIPIENT_EMAIL = 0x3003
PROP_RECIPIENT_SMTP = 0x39FE

SUBSTG_PREFIX = "__substg1.0_"
RECIPIENT_PREFIX = "__recip_version1.0_#"
NAMEID_STORAGE = "__nameid_version1.0"


def substg_name(tag: int, prop_type: int) -> str:
    """The stream name for a single-valued property: ``__substg1.0_<TAG><TYPE>`` (B1)."""
    return f"{SUBSTG_PREFIX}{tag:04X}{prop_type:04X}"


def multi_substg_name(tag: int, base_type: int, index: int) -> str:
    """The stream name for one value of a multi-valued property (B1's ``-NNNNNNNN``)."""
    return f"{SUBSTG_PREFIX}{tag:04X}{base_type:04X}-{index:08X}"


def utf16(text: str, size: "int | None" = None) -> bytes:
    """``text`` as UTF-16LE, space-padded to exactly ``size`` bytes when given."""
    encoded = text.encode("utf-16-le")
    if size is None:
        return encoded
    if len(encoded) > size:
        raise ValueError(f"{len(encoded)} bytes of UTF-16 does not fit in {size}")
    return encoded + (" " * ((size - len(encoded)) // 2)).encode("utf-16-le")


def entry(tag: int, prop_type: int, value: bytes = b"", *, flags: int = 0) -> bytes:
    """One 16-byte entry with an explicit 8-byte value field."""
    if len(value) > 8:
        raise ValueError("an entry's value field is at most 8 bytes")
    return struct.pack("<HH", prop_type, tag) + struct.pack("<I", flags) + value.ljust(8, b"\x00")


def fixed_entry(tag: int, prop_type: int, value: bytes, *, flags: int = 0) -> bytes:
    """A fixed-size entry whose value is inline."""
    return entry(tag, prop_type, value, flags=flags)


def long_entry(tag: int, value: int, *, flags: int = 0) -> bytes:
    """A ``PT_LONG`` fixed entry."""
    return fixed_entry(tag, PT_LONG, struct.pack("<I", value), flags=flags)


def variable_entry(tag: int, prop_type: int, size: int, *, flags: int = 0) -> bytes:
    """A variable-size entry: the declared size in the value field's first word (``d0``)."""
    return entry(tag, prop_type, struct.pack("<I", size), flags=flags)


def storage_entry(tag: int, prop_type: int = PT_OBJECT, *, flags: int = 0) -> bytes:
    """A storage-backed entry (``000D``): no value, never read by Turn 1b.4."""
    return entry(tag, prop_type, b"", flags=flags)


def message_header(*, recipients: int = 0, attachments: int = 0) -> bytes:
    """The 32-byte top-level header: the counts at ``@16``/``@20`` (and the ``@24``/``@28`` twins)."""
    return struct.pack("<IIIIII", 0, 0, recipients, attachments, recipients, attachments) + b"\x00" * 8


def message_table(
    entries: Iterable[bytes],
    *,
    recipients: int = 0,
    attachments: int = 0,
    codepages: "tuple[int, int] | None" = (1252, 1252),
) -> bytes:
    """A top-level ``__properties_version1.0``: the 32-byte header, the code pages, ``entries``."""
    body = b"".join(entries)
    if codepages is None:
        return message_header(recipients=recipients, attachments=attachments) + body
    internet, message = codepages
    prefix = long_entry(PROP_INTERNET_CODEPAGE, internet) + long_entry(PROP_MESSAGE_CODEPAGE, message)
    return message_header(recipients=recipients, attachments=attachments) + prefix + body


def sub_table(entries: Iterable[bytes]) -> bytes:
    """A recipient/attachment/embedded table: the 8-byte header plus ``entries``."""
    return b"\x00" * HEADER_SIZE_SUB + b"".join(entries)
