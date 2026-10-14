"""Turn 1b.2/1b.3: the first ``.msg`` fixtures, built from hand-typed descriptions.

Each fixture is described here as a storage tree of named streams with exact byte
content, handed to ``tools/cfb_writer.py`` (the deterministic minimal CFB writer).
The writer is deliberately *dumb about MAPI*: it never knows a property tag, a
``__substg1.0_`` name or a body stream. Everything MAPI-shaped -- the 32-byte
top-level property header, the ``(propType << 16) | propId`` property entries, a
``__nameid_version1.0`` storage's three binary streams -- is typed here as ordinary
bytes.

Turn 1b.3 adds the hostile fixtures at the bottom: the same writer's output with one
32-bit word patched, because the writer cannot produce a malformed file honestly. The
word's offset is derived here from the sector layout the writer fixes (FAT, directory,
miniFAT, mini stream, then the FAT streams), and every hand-typed offset is asserted
against the bytes at build time rather than trusted.

Two rules, matching ``tools/make_fixtures.py``:

* **Deterministic and clock-free.** No timestamps, no CLSIDs, no randomness, no
  dict-order dependence. The same description gives byte-identical output on 3.11
  and 3.14 and on any platform.
* **Synthetic only.** No real or employer mail, and no text from a real message. The
  `.msg` files this writes are tiny and hand-built.

The sidecars (``*.expected.json``) are typed by hand and independently; no code in
this file writes, reads or knows about a sidecar. The hostile fixtures deliberately
have none: their expectations are typed in ``tests/support/msg_construction.py``.

Usage::

    python tools/make_msg_fixtures.py           # write the fixtures + SHA256SUMS
    python tools/make_msg_fixtures.py --check   # exit 1 unless the bytes already match
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cfb_writer import (  # noqa: E402
    ENDOFCHAIN,
    FATSECT,
    FREESECT,
    NOSTREAM,
    Storage,
    build_cfb,
    storage,
    stream,
)

__all__ = [
    "ALL_FIXTURE_NAMES",
    "FIXTURE_NAMES",
    "HOSTILE_FIXTURE_NAMES",
    "build_all",
    "build_fixture",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
MSG = REPO_ROOT / "fixtures" / "msg"
SUMS = MSG / "SHA256SUMS"

sys.path.insert(0, str(REPO_ROOT / "tests"))

from support import mapi_table  # noqa: E402  (property-table bytes, typed from [MS-OXMSG])

#: The transport-header stream's UTF-16LE byte length, typed here so the fixtures'
#: construction tables can name it. It is a whole number of UTF-16 code units.
TRANSPORT_HEADER_BYTES = 518
#: The HTML body stream's byte length (``0102`` PT_BINARY).
HTML_BODY_BYTES = 160
#: The two ``__nameid_version1.0`` stream sizes B1 records (``160/440/3090`` bytes).
NAMEID_SIZES = (160, 440, 3090)

_TRANSPORT_HEADER_TEXT = (
    "Subject: turn 1b.2 synthetic fixture\r\n"
    "From: Ada Lovelace <ada@example.test>\r\n"
    "To: Grace Hopper <grace@example.test>\r\n"
    "Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
    "Message-ID: <turn-1b2-0001@example.test>\r\n"
    "MIME-Version: 1.0\r\n"
    'Content-Type: text/html; charset="utf-8"\r\n'
    "\r\n"
)
_HTML_BODY_TEXT = "<html><body><p>synthetic turn 1b.2 body</p></body></html>\r\n"

#: MAPI property types (MS-OXMSG 2.2.1.1): 0x0003 PT_LONG, 0x001F PT_UNICODE,
#: 0x0102 PT_BINARY.
PT_LONG = 0x0003
PT_UNICODE = 0x001F
PT_BINARY = 0x0102

# Property ids used by the hand-built Outlook-layout fixture.
PROP_INTERNET_CODEPAGE = 0x3FDE
PROP_MESSAGE_CODEPAGE = 0x3FFD
PROP_MESSAGE_CLASS = 0x001A
PROP_TRANSPORT_HEADERS = 0x007D
PROP_BODY_HTML = 0x1013
# The recipient tags, per [MS-OXPROPS] (B3 shows 0C15:0003 in real messages): 0x0C15 is
# the recipient *type*, 0x3001 the display name, 0x3002 the address type, 0x3003 the
# email address. Turn 1b.4 corrected the earlier per-fixture typing.
PROP_RECIPIENT_TYPE = 0x0C15
PROP_RECIPIENT_DISPLAY = 0x3001
PROP_RECIPIENT_ADDRESS_TYPE = 0x3002
PROP_RECIPIENT_EMAIL = 0x3003
PROP_ATTACH_METHOD = 0x3705
PROP_ATTACH_MIME = 0x370E
PROP_ATTACH_FILENAME = 0x3707
PROP_ATTACH_RENDERING = 0x370B
PROP_ATTACH_DATA = 0x3701
# Turn 1b.7's attachment tags ([MS-OXPROPS]).
PROP_ATTACH_FILENAME_SHORT = 0x3704
PROP_ATTACH_FILENAME_DISPLAY = 0x3001
PROP_ATTACH_CONTENT_ID = 0x3712
PROP_ATTACH_FLAGS = 0x3714
PROP_ATTACH_HIDDEN = 0x7FFE
#: The embedded-message storage (``0x3701`` ``PT_OBJECT``) and its property-table header.
EMBEDDED_STORAGE = "__substg1.0_3701000D"
EMBEDDED_HEADER_BYTES = 24
#: ``0x3714``'s ``ATT_MHTML_REF`` bit (the body references the attachment, D2).
ATT_MHTML_REF = 0x4
#: The attachment methods Turn 1b.7 exercises (D2/D4/D5).
METHOD_BY_VALUE = 1
METHOD_BY_REFERENCE = 2
METHOD_BY_REFERENCE_RESOLVE = 3
METHOD_BY_REFERENCE_ONLY = 4
METHOD_EMBEDDED_MESSAGE = 5
METHOD_OLE = 6


def _utf16(text: str, size: int) -> bytes:
    """``text`` as UTF-16LE, space-padded to exactly ``size`` bytes."""
    encoded = text.encode("utf-16-le")
    if len(encoded) > size:
        raise ValueError(f"{len(encoded)} bytes of UTF-16 does not fit in {size}")
    return encoded + (" " * ((size - len(encoded)) // 2)).encode("utf-16-le")


def _filler(size: int, seed: int) -> bytes:
    """A deterministic ``size``-byte filler (binary stream content, never a value)."""
    return bytes((seed + index) % 251 for index in range(size))


def _prop_entry(tag: int, prop_type: int, value: bytes) -> bytes:
    """One 16-byte property entry: tag, flags, then the value in eight bytes."""
    if len(value) > 8:
        raise ValueError("a fixed-size property value is at most 8 bytes")
    return struct.pack("<HH", prop_type, tag) + b"\x00" * 4 + value.ljust(8, b"\x00")


def _message_property_stream(recipients: int, attachments: int) -> bytes:
    """The 32-byte top-level header plus the two code-page fixed entries (B4)."""
    header = struct.pack("<IIIIII", 0, 0, recipients, attachments, recipients, attachments)
    header += b"\x00" * 8
    entries = _prop_entry(PROP_INTERNET_CODEPAGE, PT_LONG, struct.pack("<I", 1252))
    entries += _prop_entry(PROP_MESSAGE_CODEPAGE, PT_LONG, struct.pack("<I", 1252))
    return header + entries


def _sub_property_stream(entries: bytes) -> bytes:
    """An 8-byte sub-storage header (B2) plus 16 bytes per entry."""
    return b"\x00" * 8 + entries


def _html_body() -> bytes:
    return _utf16(_HTML_BODY_TEXT, HTML_BODY_BYTES)


# --------------------------------------------------------------- the fixtures


def _fixture_headers_only() -> bytes:
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", _message_property_stream(0, 0)),
            stream("__substg1.0_007D001F", _transport_header_stream()),
        )
    )


def _transport_header_stream() -> bytes:
    return _utf16(_TRANSPORT_HEADER_TEXT, TRANSPORT_HEADER_BYTES)


def _fixture_headers_html() -> bytes:
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", _message_property_stream(0, 0)),
            stream("__substg1.0_007D001F", _transport_header_stream()),
            stream("__substg1.0_10130102", _html_body()),
        )
    )


def _fixture_v4_sectors() -> bytes:
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", _message_property_stream(0, 0)),
            stream("__substg1.0_007D001F", _transport_header_stream()),
            stream("__substg1.0_10130102", _html_body()),
        ),
        version=4,
    )


def _fixture_mini_cutoff_boundary() -> bytes:
    """4095 (mini stream) versus 4096 and 4097 (FAT); the order is explicit."""
    return build_cfb(
        storage(
            "Root Entry",
            stream("boundary_4095", b"a" * 4095),
            stream("boundary_4096", b"b" * 4096),
            stream("boundary_4097", b"c" * 4097),
        ),
        sector_order=("boundary_4097", "boundary_4096"),
    )


def _fixture_outlook_layout_handbuilt() -> bytes:
    """Hand-built to the observed Outlook structure (B1-B4), never to a default.

    Turn 1b.4 fixes the recipient table to B3's typing -- ``0C15`` type, ``3001``
    display name, ``3002`` address type, ``3003`` email address -- and gives the
    top-level table a real ``0x001A`` class so the fixture follows the observed
    layout all the way through the gate.
    """
    nameid_20, nameid_30, nameid_40 = (
        _filler(size, seed=size) for size in NAMEID_SIZES
    )
    class_stream = "IPM.Note".encode("utf-16-le")
    display = _utf16("Ada Lovelace", 24)
    address_type = _utf16("SMTP", 8)
    email = _utf16("ada@example.test", 32)
    recipient = _sub_property_stream(
        _prop_entry(PROP_RECIPIENT_TYPE, PT_LONG, struct.pack("<I", 1))
        + _prop_entry(PROP_RECIPIENT_DISPLAY, PT_UNICODE, struct.pack("<I", len(display)))
        + _prop_entry(PROP_RECIPIENT_ADDRESS_TYPE, PT_UNICODE, struct.pack("<I", len(address_type)))
        + _prop_entry(PROP_RECIPIENT_EMAIL, PT_UNICODE, struct.pack("<I", len(email)))
    )
    attachment = _sub_property_stream(
        _prop_entry(PROP_ATTACH_METHOD, PT_LONG, struct.pack("<I", 1))
        + _prop_entry(PROP_ATTACH_MIME, PT_UNICODE, _utf16("text", 8))
        + _prop_entry(PROP_ATTACH_FILENAME, PT_UNICODE, b"")
        + _prop_entry(PROP_ATTACH_RENDERING, PT_LONG, struct.pack("<I", 0))
    )
    top_level = _message_property_stream(1, 1) + _prop_entry(
        PROP_MESSAGE_CLASS, PT_UNICODE, struct.pack("<I", len(class_stream))
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", top_level),
            storage(
                "__nameid_version1.0",
                stream("__substg1.0_00020102", nameid_20),
                stream("__substg1.0_00030102", nameid_30),
                stream("__substg1.0_00040102", nameid_40),
            ),
            stream("__substg1.0_007D001F", _transport_header_stream()),
            stream("__substg1.0_001A001F", class_stream),
            stream("__substg1.0_10130102", _html_body()),
            storage(
                "__recip_version1.0_#00000000",
                stream("__properties_version1.0", recipient),
                stream("__substg1.0_3001001F", display),
                stream("__substg1.0_3002001F", address_type),
                stream("__substg1.0_3003001F", email),
            ),
            storage(
                "__attach_version1.0_#00000000",
                stream("__properties_version1.0", attachment),
                stream("__substg1.0_37010102", _filler(40, seed=7)),
                stream("__substg1.0_3707001F", _utf16("report.txt", 40)),
            ),
        )
    )


# ------------------------------------------------------- the byte-patched fixtures

#: Every fixture in this file is version 3: 512-byte sectors, so sector *n* occupies
#: bytes ``(n + 1) * 512`` onwards (the header owns window 0). The one exception is
#: ``msg_v4_sectors``, which no offset below applies to.
SECTOR_BYTES = 512
#: [MS-CFB] 2.2: the 109 inline DIFAT entries begin right after the 76-byte header.
INLINE_DIFAT_OFFSET = 76
INLINE_DIFAT_SLOTS = 109
#: [MS-CFB] 2.3.1: a DIFAT sector holds 127 FAT ids and, in slot 127, the next DIFAT.
DIFAT_IDS_PER_SECTOR = SECTOR_BYTES // 4 - 1
#: [MS-CFB] 2.2 header field offsets, as the reader's ``HEADER`` struct orders them.
HEADER_NUM_FAT_SECTORS = 44
HEADER_FIRST_DIR_SECTOR = 48
HEADER_FIRST_MINIFAT_SECTOR = 60
HEADER_FIRST_DIFAT_SECTOR = 68
HEADER_NUM_DIFAT_SECTORS = 72
#: [MS-CFB] 2.6.1 field offsets inside one 128-byte directory entry.
DIR_ENTRY_BYTES = 128
DIR_ENTRY_LEFT = 68
DIR_ENTRY_START = 116
DIR_ENTRY_SIZE_LOW = 120

#: ``big_stream`` is exactly the 4096-byte cutoff, so the writer puts it in the FAT:
#: eight sectors. It is the base's only FAT-addressed stream, so the base lays out in
#: 12 sectors -- 0 FAT, 1 directory, 2 miniFAT, 3 mini stream (64 + 160 = 224 bytes),
#: 4..11 ``big_stream`` -- and is 6144 bytes.
HOSTILE_BIG_BYTES = 4096
HOSTILE_BIG_START = 4
HOSTILE_BASE_SECTORS = 12
#: Directory ids, in the declaration order the base's storage gives them.
HOSTILE_PROPERTIES_ENTRY = 1
HOSTILE_BIG_ENTRY = 3

#: The three words the hostile fixtures patch, each derived from the layout above.
#: The FAT is sector 0, so slot 4 of it is at window 1 + four 4-byte slots; the
#: directory is sector 1, so entry *n*'s field ``f`` is at window 2 + 128n + f.
HOSTILE_FAT_WORD = SECTOR_BYTES + HOSTILE_BIG_START * 4
HOSTILE_LOOP_WORD = (
    2 * SECTOR_BYTES + HOSTILE_PROPERTIES_ENTRY * DIR_ENTRY_BYTES + DIR_ENTRY_LEFT
)
HOSTILE_SIZE_WORD = 2 * SECTOR_BYTES + HOSTILE_BIG_ENTRY * DIR_ENTRY_BYTES + DIR_ENTRY_SIZE_LOW
#: ``msg_truncated_stream``'s declared size: two sectors more than the chain holds.
HOSTILE_SIZE_LIE = 2 * HOSTILE_BIG_BYTES


def _word(data: bytes, offset: int) -> int:
    """``data``'s little-endian 32-bit word at ``offset`` (for the asserts below)."""
    return struct.unpack_from("<L", data, offset)[0]


def _patch_u32(data: bytes, offset: int, value: int) -> bytes:
    """A copy of ``data`` with the little-endian 32-bit word at ``offset`` replaced."""
    patched = bytearray(data)
    struct.pack_into("<L", patched, offset, value)
    return bytes(patched)


def _window(data: bytes, index: int) -> bytes:
    """The bytes of sector ``index`` (sector *n* starts at byte ``(n + 1) * 512``)."""
    start = (index + 1) * SECTOR_BYTES
    return data[start : start + SECTOR_BYTES]


def _fixture_hostile_base() -> bytes:
    """The base every hostile fixture patches: a well-formed three-stream message."""
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", _message_property_stream(0, 0)),
            stream("__substg1.0_10130102", _html_body()),
            stream("big_stream", _filler(HOSTILE_BIG_BYTES, seed=11)),
        )
    )


def _checked_hostile_base() -> bytes:
    """The base, with every offset the three patches use asserted before patching."""
    base = _fixture_hostile_base()
    assert len(base) == (HOSTILE_BASE_SECTORS + 1) * SECTOR_BYTES, len(base)
    assert _word(base, HOSTILE_FAT_WORD) == HOSTILE_BIG_START + 1, "not big_stream's slot"
    assert _word(base, HOSTILE_SIZE_WORD) == HOSTILE_BIG_BYTES, "not big_stream's size"
    # The base's three siblings sort by (name length, name.upper()): the entry 1, 2, 3
    # insertion order gives a tree whose root is entry 2, over leaves 3 and 1. So
    # entry 1 -- the one whose link the loop patch overwrites -- is a leaf.
    assert _word(base, HOSTILE_LOOP_WORD) == NOSTREAM, "entry 1 is not a leaf"
    return base


def _fixture_fat_cycle() -> bytes:
    """``big_stream``'s FAT chain re-enters its own first sector ([MS-CFB] 2.3.2)."""
    base = _checked_hostile_base()
    return _patch_u32(base, HOSTILE_FAT_WORD, HOSTILE_BIG_START)


def _fixture_directory_loop() -> bytes:
    """``__properties_version1.0``'s left link re-enters its own entry ([MS-CFB] 2.6.4)."""
    base = _checked_hostile_base()
    return _patch_u32(base, HOSTILE_LOOP_WORD, HOSTILE_PROPERTIES_ENTRY)


def _fixture_truncated_stream() -> bytes:
    """``big_stream`` declares 8192 bytes over a chain that holds 4096 ([MS-CFB] 2.5)."""
    base = _checked_hostile_base()
    return _patch_u32(base, HOSTILE_SIZE_WORD, HOSTILE_SIZE_LIE)


#: ``msg_difat_extended`` is reassembled from ``_fixture_headers_html`` rather than
#: appended to, so that every byte of it is written here. That base has no
#: FAT-addressed stream at all -- 0 FAT, 1 directory, 2 miniFAT, 3..4 the 742-byte
#: mini stream -- and it is the bytes of sectors 1, 2, 3 and 4 that move. The header
#: then claims 110 FAT sectors, the first real and 1..109 all ``FREESECT`` padding,
#: and puts the 110th FAT id in one extended DIFAT sector, which is why the file
#: needs it: 115 sectors, 59392 bytes.
DIFAT_FAT_SECTORS = 110
DIFAT_DIR_SECTOR = 110
DIFAT_MINIFAT_SECTOR = 111
DIFAT_MINI_START = 112
DIFAT_MINI_SECTORS = 2
DIFAT_SECTOR = 114
DIFAT_EXTENDED_FATS = 1
DIFAT_SECTORS = 115
#: ``_fixture_headers_html``'s own layout, which the reassembly reads from.
DIFAT_BASE_SECTORS = 5
DIFAT_BASE_DIR_SECTOR = 1
DIFAT_BASE_MINIFAT_SECTOR = 2
DIFAT_BASE_MINI_START = 3


def _difat_fat() -> bytes:
    """The one real FAT sector: it covers its own declared sectors and the four used.

    The sector's remaining slots are zero, as the writer's own padding is, because the
    reader cuts the table to the file's sector count anyway.
    """
    values = [FATSECT] * DIFAT_FAT_SECTORS
    values += [FREESECT] * (DIFAT_SECTORS - DIFAT_FAT_SECTORS)
    values[DIFAT_DIR_SECTOR] = ENDOFCHAIN
    values[DIFAT_MINIFAT_SECTOR] = ENDOFCHAIN
    values[DIFAT_MINI_START] = DIFAT_MINI_START + 1
    values[DIFAT_MINI_START + DIFAT_MINI_SECTORS - 1] = ENDOFCHAIN
    return struct.pack("<%dL" % len(values), *values).ljust(SECTOR_BYTES, b"\x00")


def _difat_sector() -> bytes:
    """One extended DIFAT sector: the 110th FAT id, then ``FREESECT``, then the end."""
    values = [FREESECT] * DIFAT_IDS_PER_SECTOR
    values[0] = DIFAT_FAT_SECTORS - 1
    values.append(ENDOFCHAIN)
    return struct.pack("<%dL" % (SECTOR_BYTES // 4), *values)


def _fixture_difat_extended() -> bytes:
    """A FAT reached through an extended DIFAT chain ([MS-CFB] 2.2, 2.3.1)."""
    base = _fixture_headers_html()
    assert len(base) == (DIFAT_BASE_SECTORS + 1) * SECTOR_BYTES, len(base)
    directory = bytearray(_window(base, DIFAT_BASE_DIR_SECTOR))
    assert _word(directory, DIR_ENTRY_START) == DIFAT_BASE_MINI_START, "root start"

    header = bytearray(base[:SECTOR_BYTES])
    for offset, value in (
        (HEADER_NUM_FAT_SECTORS, DIFAT_FAT_SECTORS),
        (HEADER_FIRST_DIR_SECTOR, DIFAT_DIR_SECTOR),
        (HEADER_FIRST_MINIFAT_SECTOR, DIFAT_MINIFAT_SECTOR),
        (HEADER_FIRST_DIFAT_SECTOR, DIFAT_SECTOR),
        (HEADER_NUM_DIFAT_SECTORS, DIFAT_EXTENDED_FATS),
    ):
        struct.pack_into("<L", header, offset, value)
    for slot in range(INLINE_DIFAT_SLOTS):
        struct.pack_into("<L", header, INLINE_DIFAT_OFFSET + 4 * slot, slot)
    # The mini stream keeps its bytes and moves; only the root entry's start changes.
    struct.pack_into("<L", directory, DIR_ENTRY_START, DIFAT_MINI_START)

    body = {index: bytes(SECTOR_BYTES) for index in range(1, DIFAT_FAT_SECTORS)}
    body[0] = _difat_fat()
    body[DIFAT_DIR_SECTOR] = bytes(directory)
    body[DIFAT_MINIFAT_SECTOR] = _window(base, DIFAT_BASE_MINIFAT_SECTOR)
    for offset in range(DIFAT_MINI_SECTORS):
        body[DIFAT_MINI_START + offset] = _window(base, DIFAT_BASE_MINI_START + offset)
    body[DIFAT_SECTOR] = _difat_sector()
    assert sorted(body) == list(range(DIFAT_SECTORS)), "one 512-byte sector per index"
    data = bytes(header) + b"".join(body[index] for index in range(DIFAT_SECTORS))
    assert len(data) == (DIFAT_SECTORS + 1) * SECTOR_BYTES, len(data)
    return data


# --------------------------------------- the Turn 1b.4 property-layer fixtures

#: The class strings the class-gate fixtures carry (D6).
CLASS_IPM_NOTE = "IPM.Note"
CLASS_APPOINTMENT = "IPM.Appointment"
CLASS_SIGNED = "IPM.Note.SMIME.MultipartSigned"
#: ``msg_codepage_disagree``'s two code pages: internet 28591, then message 1252 (B4).
DISAGREE_CODEPAGES = (28591, 1252)
#: ``msg_codepage_disagree``'s subject: byte ``0x93`` is a C1 control in iso-8859-1 and a
#: curly quote in cp1252, so the two code pages decode it differently (the internet wins).
DISAGREE_SUBJECT = b"synthetic \x93 subject"
#: The recipient storage the stopped-class fixtures carry, to prove the gate never reads it.
STOPPED_RECIPIENT = "__recip_version1.0_#00000000"


def _property_stream(entries, *, recipients=0, attachments=0, codepages=(1252, 1252)) -> bytes:
    """A top-level table: the 32-byte header, the code pages, then ``entries``."""
    return mapi_table.message_table(
        entries, recipients=recipients, attachments=attachments, codepages=codepages
    )


def _class_bytes(class_text: str) -> bytes:
    return class_text.encode("utf-16-le")


def _class_entry(class_text: str) -> bytes:
    return mapi_table.variable_entry(
        mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE, len(_class_bytes(class_text))
    )


def _class_stream_name() -> str:
    return mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE)


def _class_gate_fixture(class_text: str) -> bytes:
    """A stopped-class fixture: the class, plus a subject and a recipient the gate never reads."""
    subject = b"synthetic turn 1b.4 subject"
    table = _property_stream(
        [
            _class_entry(class_text),
            mapi_table.variable_entry(mapi_table.PROP_SUBJECT, mapi_table.PT_STRING8, len(subject)),
        ],
        recipients=1,
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(_class_stream_name(), _class_bytes(class_text)),
            stream(mapi_table.substg_name(mapi_table.PROP_SUBJECT, mapi_table.PT_STRING8), subject),
            storage(
                STOPPED_RECIPIENT,
                stream(
                    "__properties_version1.0",
                    mapi_table.sub_table([mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 1)]),
                ),
            ),
        )
    )


def _fixture_non_ipm_note() -> bytes:
    """The class gate's ``not_ipm_note`` case: an appointment (D6, ``msg_non_ipm_note``)."""
    return _class_gate_fixture(CLASS_APPOINTMENT)


def _fixture_signed_class() -> bytes:
    """The class gate's ``signed_or_encrypted`` case (D6/O8, ``msg_signed_class``)."""
    return _class_gate_fixture(CLASS_SIGNED)


def _fixture_unknown_tags() -> bytes:
    """``IPM.Note`` plus property entries whose tags are not modelled (hex only, D4)."""
    unicode_stream = mapi_table.utf16("unmodelled unicode")
    binary_stream = b"\xde\xad\xbe\xef"
    table = _property_stream(
        [
            _class_entry(CLASS_IPM_NOTE),
            mapi_table.long_entry(0x6200, 7),
            mapi_table.fixed_entry(0x6748, mapi_table.PT_I8, struct.pack("<q", 1234)),
            mapi_table.variable_entry(0x6827, mapi_table.PT_UNICODE, len(unicode_stream)),
            mapi_table.variable_entry(0x6523, mapi_table.PT_BINARY, len(binary_stream)),
        ]
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(_class_stream_name(), _class_bytes(CLASS_IPM_NOTE)),
            stream("__substg1.0_6827001F", unicode_stream),
            stream("__substg1.0_65230102", binary_stream),
        )
    )


def _fixture_named_properties() -> bytes:
    """``__nameid_version1.0`` present; a named property (``0x8005``) is not resolved (D5)."""
    named_stream = mapi_table.utf16("named property value")
    table = _property_stream(
        [
            _class_entry(CLASS_IPM_NOTE),
            mapi_table.variable_entry(0x8005, mapi_table.PT_UNICODE, len(named_stream)),
        ]
    )
    nameid = {size: _filler(size, seed=size) for size in NAMEID_SIZES}
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            storage(
                mapi_table.NAMEID_STORAGE,
                stream("__substg1.0_00020102", nameid[160]),
                stream("__substg1.0_00030102", nameid[440]),
                stream("__substg1.0_00040102", nameid[3090]),
            ),
            stream(_class_stream_name(), _class_bytes(CLASS_IPM_NOTE)),
            stream("__substg1.0_8005001F-00000000", named_stream),
        )
    )


# --------------------------------------- the Turn 1b.5 body fixtures

#: The Turn 1b.5 fixtures' short transport-header text: ASCII, CRLF, one trailing blank.
T15_TRANSPORT_TEXT = (
    "Subject: turn 1b.5 synthetic\r\n"
    "From: Ada Lovelace <ada@example.test>\r\n"
    "Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
    "\r\n"
)
#: The LF-only variant (bare LF, a bare ``\n`` blank line): the walker's own line model.
T15_TRANSPORT_LF_TEXT = (
    "Subject: turn 1b.5 synthetic\n"
    "From: Ada Lovelace <ada@example.test>\n"
    "\n"
)
#: The 8-bit HTML body (a ``0102`` PT_BINARY stream, the real shape).
T15_HTML_BODY = b"<html><body><p>synthetic turn 1b.5 body</p></body></html>\r\n"
#: HTML whose own ``<meta charset>`` contradicts the message's internet code page.
T15_HTML_META = (
    b'<html><head><meta charset="utf-8">'
    b"</head><body><p>synthetic turn 1b.5 body</p></body></html>\r\n"
)
#: The plain body text: a whitespace-only stub, the real-world shape that lets the
#: selection stage prefer the HTML alternative (``body.plain_effectively_empty``, D16).
T15_PLAIN_TEXT = "\r\n"
#: The disputed property subject: it does **not** equal the transport header's Subject.
T15_CONFLICT_SUBJECT = "synthetic turn 1b.5 property subject"


def _t15_fixture(
    *,
    transport_name: str | None,
    transport_bytes: bytes | None,
    subject_stream: bytes | None = None,
    plain: bytes | None = None,
    html: bytes | None = None,
    codepages: tuple[int, int] = (1252, 1252),
) -> bytes:
    """One Turn 1b.5 fixture: ``IPM.Note`` plus the named streams, in a fixed order."""
    entries = [_class_entry(CLASS_IPM_NOTE)]
    if subject_stream is not None:
        entries.append(
            mapi_table.variable_entry(
                mapi_table.PROP_SUBJECT, mapi_table.PT_UNICODE, len(subject_stream)
            )
        )
    table = _property_stream(entries, codepages=codepages)
    children = [
        stream("__properties_version1.0", table),
        stream(_class_stream_name(), _class_bytes(CLASS_IPM_NOTE)),
    ]
    if subject_stream is not None:
        children.append(stream("__substg1.0_0037001F", subject_stream))
    if transport_bytes is not None:
        children.append(stream(transport_name, transport_bytes))
    if plain is not None:
        children.append(stream("__substg1.0_1000001F", plain))
    if html is not None:
        children.append(stream("__substg1.0_10130102", html))
    return build_cfb(storage("Root Entry", *children))


def _fixture_html_only_no_plain() -> bytes:
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_TEXT.encode("utf-16-le"),
        html=T15_HTML_BODY,
    )


def _fixture_plain_only() -> bytes:
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_TEXT.encode("utf-16-le"),
        plain=T15_PLAIN_TEXT.encode("utf-16-le"),
    )


def _fixture_plain_and_html() -> bytes:
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_TEXT.encode("utf-16-le"),
        plain=T15_PLAIN_TEXT.encode("utf-16-le"),
        html=T15_HTML_BODY,
    )


def _fixture_zero_length_body() -> bytes:
    """A ``0x1000`` stream of length 0: present-but-empty, never absent (D5)."""
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_TEXT.encode("utf-16-le"),
        plain=b"",
    )


def _fixture_html_meta_charset_contradicts() -> bytes:
    """The HTML's ``<meta charset>`` says utf-8; the message's internet code page is 1252."""
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_TEXT.encode("utf-16-le"),
        html=T15_HTML_META,
    )


def _fixture_no_transport_headers() -> bytes:
    return _t15_fixture(transport_name=None, transport_bytes=None, html=T15_HTML_BODY)


def _fixture_transport_headers_utf8_bom() -> bytes:
    """``0x007D`` as ``001E`` whose bytes begin with the UTF-8 BOM the scan tolerates."""
    return _t15_fixture(
        transport_name="__substg1.0_007D001E",
        transport_bytes=b"\xef\xbb\xbf" + T15_TRANSPORT_TEXT.encode("utf-8"),
        html=T15_HTML_BODY,
    )


def _fixture_transport_headers_lf_only() -> bytes:
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_LF_TEXT.encode("utf-16-le"),
        html=T15_HTML_BODY,
    )


def _fixture_property_vs_header_conflict() -> bytes:
    """The ``0x0037`` subject property and the transport header's ``Subject:`` disagree."""
    return _t15_fixture(
        transport_name="__substg1.0_007D001F",
        transport_bytes=T15_TRANSPORT_TEXT.encode("utf-16-le"),
        subject_stream=T15_CONFLICT_SUBJECT.encode("utf-16-le"),
        html=T15_HTML_BODY,
    )


def _fixture_codepage_disagree() -> bytes:
    """Internet 28591 against message 1252, disagreeing on one byte (D2, B4)."""
    table = _property_stream(
        [
            _class_entry(CLASS_IPM_NOTE),
            mapi_table.variable_entry(
                mapi_table.PROP_SUBJECT, mapi_table.PT_STRING8, len(DISAGREE_SUBJECT)
            ),
        ],
        codepages=DISAGREE_CODEPAGES,
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(_class_stream_name(), _class_bytes(CLASS_IPM_NOTE)),
            stream(mapi_table.substg_name(mapi_table.PROP_SUBJECT, mapi_table.PT_STRING8), DISAGREE_SUBJECT),
        )
    )


# --------------------------------------- the Turn 1b.6 message-fact fixtures

#: The Turn 1b.6 fixtures' transport-header text (ASCII, CRLF, one trailing blank).
T16_TRANSPORT_TEXT = (
    "Subject: turn 1b.6 synthetic\r\n"
    "From: Ada Lovelace <ada@example.test>\r\n"
    "Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
    "\r\n"
)
#: ``msg_unicode_subject`` has no ``Subject:`` field, so the ``0x0037`` property is canonical.
T16_TRANSPORT_NO_SUBJECT = (
    "From: Ada Lovelace <ada@example.test>\r\n"
    "Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
    "\r\n"
)
#: The 8-bit HTML body (a ``0102`` PT_BINARY stream, the real shape).
T16_HTML_BODY = b"<html><body><p>synthetic turn 1b.6 body</p></body></html>\r\n"

PROP_CLIENT_SUBMIT_TIME = 0x0039
PROP_DELIVERY_TIME = 0x0E06
#: ``0x01DD597CEBED5800`` is 2026-10-11T12:34:56Z (whole seconds): the MAPI time the
#: ``Date`` header (2025-03-04T08:00:00Z) deliberately disagrees with.
T16_SUBMIT_FILETIME = 0x01DD597CEBED5800

T16_ADA_DISPLAY = "Ada Lovelace"
T16_ADA_SMTP = "ada@example.test"
T16_GRACE_DISPLAY = "Grace Hopper"
T16_GRACE_SMTP = "grace@example.test"
T16_EX_ADDRESS = "/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2"
#: A non-ASCII subject: Latin-1, CJK, and a non-BMP emoji (a UTF-16 surrogate pair).
T16_UNICODE_SUBJECT = "synthetic \u00fcnicode \u4e16\u754c subject \U0001f30d"


def _recipient_storage(
    index: int,
    *,
    kind: int,
    display: str | None = None,
    address_type: str | None = None,
    email: str | None = None,
) -> Storage:
    """One ``__recip_version1.0_#XXXXXXXX`` row, its table and its ``__substg1.0`` streams."""
    entries = [mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, kind)]
    children = []
    for tag, text in (
        (mapi_table.PROP_RECIPIENT_DISPLAY, display),
        (mapi_table.PROP_RECIPIENT_ADDRESS_TYPE, address_type),
        (mapi_table.PROP_RECIPIENT_EMAIL, email),
    ):
        if text is None:
            continue
        data = mapi_table.utf16(text)
        entries.append(mapi_table.variable_entry(tag, mapi_table.PT_UNICODE, len(data)))
        children.append(stream(mapi_table.substg_name(tag, mapi_table.PT_UNICODE), data))
    return storage(
        f"__recip_version1.0_#{index:08X}",
        stream("__properties_version1.0", mapi_table.sub_table(entries)),
        *children,
    )


def _t16_fixture(
    *,
    transport: str | None,
    entries=(),
    recipients: int = 0,
    recipient_storages=(),
    subject: str | None = None,
    html: bytes | None = T16_HTML_BODY,
) -> bytes:
    """One Turn 1b.6 fixture: ``IPM.Note`` plus the named streams, in a fixed order."""
    table_entries = [_class_entry(CLASS_IPM_NOTE)]
    children = []
    if subject is not None:
        subject_stream = subject.encode("utf-16-le")
        table_entries.append(
            mapi_table.variable_entry(
                mapi_table.PROP_SUBJECT, mapi_table.PT_UNICODE, len(subject_stream)
            )
        )
        children.append(stream("__substg1.0_0037001F", subject_stream))
    table_entries.extend(entries)
    table = _property_stream(table_entries, recipients=recipients)
    children = [
        stream("__properties_version1.0", table),
        stream(_class_stream_name(), _class_bytes(CLASS_IPM_NOTE)),
        *children,
    ]
    if transport is not None:
        children.append(stream("__substg1.0_007D001F", transport.encode("utf-16-le")))
    if html is not None:
        children.append(stream("__substg1.0_10130102", html))
    children.extend(recipient_storages)
    return build_cfb(storage("Root Entry", *children))


def _fixture_recipients_display_only() -> bytes:
    """One ``to`` row with a display name and no SMTP address (D5's display-only case)."""
    return _t16_fixture(
        transport=T16_TRANSPORT_TEXT,
        recipients=1,
        recipient_storages=(
            _recipient_storage(0, kind=1, display=T16_ADA_DISPLAY, address_type="SMTP"),
        ),
    )


def _fixture_recipients_ex_no_smtp() -> bytes:
    """One Exchange row: its ``/O=`` address in ``0x3003``, no ``0x39FE`` form (D5)."""
    return _t16_fixture(
        transport=T16_TRANSPORT_TEXT,
        recipients=1,
        recipient_storages=(
            _recipient_storage(
                0, kind=1, display=T16_GRACE_DISPLAY, address_type="EX", email=T16_EX_ADDRESS
            ),
        ),
    )


def _fixture_recipients_bcc_duplicates() -> bytes:
    """A ``bcc`` row and a duplicated ``to`` row: three records, index order, never merged."""
    return _t16_fixture(
        transport=T16_TRANSPORT_TEXT,
        recipients=3,
        recipient_storages=(
            _recipient_storage(
                0, kind=1, display=T16_ADA_DISPLAY, address_type="SMTP", email=T16_ADA_SMTP
            ),
            _recipient_storage(
                1, kind=3, display=T16_GRACE_DISPLAY, address_type="SMTP", email=T16_GRACE_SMTP
            ),
            _recipient_storage(
                2, kind=1, display=T16_ADA_DISPLAY, address_type="SMTP", email=T16_ADA_SMTP
            ),
        ),
    )


def _fixture_time_property_vs_date_header() -> bytes:
    """``0x0039``/``0x0E06`` disagree with the ``Date`` header; kept apart (D6/D7)."""
    return _t16_fixture(
        transport=T16_TRANSPORT_TEXT,
        entries=[
            mapi_table.fixed_entry(
                PROP_CLIENT_SUBMIT_TIME, mapi_table.PT_SYSTIME, struct.pack("<Q", T16_SUBMIT_FILETIME)
            ),
            mapi_table.fixed_entry(
                PROP_DELIVERY_TIME, mapi_table.PT_SYSTIME, struct.pack("<Q", T16_SUBMIT_FILETIME)
            ),
        ],
    )


def _fixture_unicode_subject() -> bytes:
    """A ``001F`` subject with non-ASCII (a surrogate pair included) and no header ``Subject:``."""
    return _t16_fixture(transport=T16_TRANSPORT_NO_SUBJECT, subject=T16_UNICODE_SUBJECT)


# ------------------------------------------------ Turn 1b.7: the Family G fixtures


G_TRANSPORT_TEXT = (
    "Subject: synthetic turn 1b.7 fixture\r\n"
    "From: Ada Lovelace <ada@example.test>\r\n"
    "To: Grace Hopper <grace@example.test>\r\n"
    "Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
    "Message-ID: <turn-1b7-0001@example.test>\r\n"
    "\r\n"
)
G_HTML_BODY = b"<html><body><p>synthetic turn 1b.7 body</p></body></html>\r\n"
#: A by-value attachment's bytes, typed so its digest is checkable.
G_ATTACH_BYTES = b"turn 1b.7 synthetic attachment bytes\r\n"


def _embedded_table(entries) -> bytes:
    """An embedded message's property stream: the 24-byte header plus ``entries`` (D4)."""
    return b"\x00" * EMBEDDED_HEADER_BYTES + b"".join(entries)


def _embedded_storage(
    *,
    message_class: str = CLASS_IPM_NOTE,
    subject: str | None = None,
    transport: str | None = None,
    recipient_storages=(),
    attachment_storages=(),
) -> Storage:
    """One embedded message's storage (``0x3701`` ``PT_OBJECT``): read at depth 1, never recursed."""
    entries = [_class_entry(message_class)]
    body = [stream(_class_stream_name(), _class_bytes(message_class))]
    if subject is not None:
        payload = subject.encode("utf-16-le")
        entries.append(
            mapi_table.variable_entry(mapi_table.PROP_SUBJECT, mapi_table.PT_UNICODE, len(payload))
        )
        body.append(stream("__substg1.0_0037001F", payload))
    children = [stream("__properties_version1.0", _embedded_table(entries)), *body]
    if transport is not None:
        children.append(stream("__substg1.0_007D001F", transport.encode("utf-16-le")))
    children.extend(recipient_storages)
    children.extend(attachment_storages)
    return storage(EMBEDDED_STORAGE, *children)


def _embedded_recipient(index: int, *, kind: int, display: str, address_type: str, email: str = "") -> Storage:
    """A minimal ``__recip_version1.0_#XXXXXXXX`` row for an embedded message's summary."""
    entries = [mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, kind)]
    children = []
    for tag, text in (
        (mapi_table.PROP_RECIPIENT_DISPLAY, display),
        (mapi_table.PROP_RECIPIENT_ADDRESS_TYPE, address_type),
        (mapi_table.PROP_RECIPIENT_EMAIL, email),
    ):
        payload = text.encode("utf-16-le")
        entries.append(mapi_table.variable_entry(tag, mapi_table.PT_UNICODE, len(payload)))
        children.append(stream(mapi_table.substg_name(tag, mapi_table.PT_UNICODE), payload))
    return storage(
        f"__recip_version1.0_#{index:08X}",
        stream("__properties_version1.0", mapi_table.sub_table(entries)),
        *children,
    )


def _attach_storage(
    index: int,
    *,
    method: int,
    long: str | None = None,
    short: str | None = None,
    display: str | None = None,
    mime: str | None = None,
    cid: str | None = None,
    hidden: bool | None = None,
    flags: int | None = None,
    data: bytes | None = None,
    embedded: Storage | None = None,
) -> Storage:
    """One ``__attach_version1.0_#XXXXXXXX`` storage (D2-D5)."""
    entries = [mapi_table.long_entry(PROP_ATTACH_METHOD, method)]
    children = []

    def add_text(tag: int, text: str | None) -> None:
        if text is None:
            return
        payload = text.encode("utf-16-le")
        entries.append(mapi_table.variable_entry(tag, mapi_table.PT_UNICODE, len(payload)))
        children.append(stream(mapi_table.substg_name(tag, mapi_table.PT_UNICODE), payload))

    add_text(PROP_ATTACH_FILENAME, long)
    add_text(PROP_ATTACH_FILENAME_SHORT, short)
    add_text(PROP_ATTACH_FILENAME_DISPLAY, display)
    add_text(PROP_ATTACH_MIME, mime)
    add_text(PROP_ATTACH_CONTENT_ID, cid)
    if hidden is not None:
        entries.append(
            mapi_table.fixed_entry(
                PROP_ATTACH_HIDDEN, mapi_table.PT_BOOLEAN, struct.pack("<H", 1 if hidden else 0)
            )
        )
    if flags is not None:
        entries.append(mapi_table.long_entry(PROP_ATTACH_FLAGS, flags))
    if data is not None:
        entries.append(mapi_table.variable_entry(PROP_ATTACH_DATA, mapi_table.PT_BINARY, len(data)))
        children.append(stream("__substg1.0_37010102", data))
    if embedded is not None:
        entries.append(mapi_table.storage_entry(PROP_ATTACH_DATA))
        children.append(embedded)
    return storage(
        f"__attach_version1.0_#{index:08X}",
        stream("__properties_version1.0", mapi_table.sub_table(entries)),
        *children,
    )


def _g_fixture(*, attachments=(), attachment_count: "int | None" = None, html: "bytes | None" = G_HTML_BODY) -> bytes:
    """One Turn 1b.7 fixture: an ``IPM.Note`` with a transport header, a body and attachments."""
    count = len(attachments) if attachment_count is None else attachment_count
    table = _property_stream(
        [_class_entry(CLASS_IPM_NOTE)], attachments=count
    )
    children = [
        stream("__properties_version1.0", table),
        stream(_class_stream_name(), _class_bytes(CLASS_IPM_NOTE)),
        stream("__substg1.0_007D001F", G_TRANSPORT_TEXT.encode("utf-16-le")),
    ]
    if html is not None:
        children.append(stream("__substg1.0_10130102", html))
    children.extend(attachments)
    return build_cfb(storage("Root Entry", *children))


def _fixture_embedded_message() -> bytes:
    """One method-5 attachment whose embedded message carries a subject and a recipient (D4)."""
    return _g_fixture(
        attachments=(
            _attach_storage(
                0,
                method=METHOD_EMBEDDED_MESSAGE,
                long="forwarded.msg",
                embedded=_embedded_storage(
                    subject="Fwd: hello",
                    transport=G_TRANSPORT_TEXT,
                    recipient_storages=(
                        _embedded_recipient(0, kind=1, display="Ada Lovelace", address_type="SMTP", email="ada@example.test"),
                    ),
                ),
            ),
        )
    )


def _fixture_embedded_depth_two() -> bytes:
    """An embedded message that itself embeds one: depth 1 read, the nested embed capped (D4)."""
    inner = _embedded_storage(
        subject="inner",
        attachment_storages=(
            _attach_storage(0, method=METHOD_EMBEDDED_MESSAGE, long="nested.msg", embedded=_embedded_storage(subject="deepest")),
        ),
    )
    return _g_fixture(
        attachments=(
            _attach_storage(0, method=METHOD_EMBEDDED_MESSAGE, long="outer.msg", embedded=inner),
        )
    )


def _fixture_attachment_with_cid() -> bytes:
    """A by-value attachment carrying a ``0x3712`` Content-ID (D2)."""
    return _g_fixture(
        attachments=(
            _attach_storage(
                0,
                method=METHOD_BY_VALUE,
                long="report.pdf",
                mime="application/pdf",
                cid="cid1@example.test",
                data=G_ATTACH_BYTES,
            ),
        )
    )


def _fixture_attachment_hidden() -> bytes:
    """A by-value attachment with the hidden flag and the ``ATT_MHTML_REF`` bit (D2)."""
    return _g_fixture(
        attachments=(
            _attach_storage(
                0,
                method=METHOD_BY_VALUE,
                long="inline-image.png",
                mime="image/png",
                hidden=True,
                flags=ATT_MHTML_REF,
                data=b"\x89PNG\r\n\x1a\nsynthetic",
            ),
        )
    )


def _fixture_attachment_ole() -> bytes:
    """A method-6 OLE object, recorded without parsing it (D4)."""
    return _g_fixture(
        attachments=(
            _attach_storage(
                0,
                method=METHOD_OLE,
                long="object.bin",
                mime="application/octet-stream",
                embedded=storage(EMBEDDED_STORAGE, stream("__substg1.0_37010102", b"\xd0\xcf\x11\xe0synthetic ole")),
            ),
        )
    )


def _fixture_attachment_by_reference() -> bytes:
    """Methods 2/3/4: recorded and dropped, no path followed (D5)."""
    return _g_fixture(
        attachments=(
            _attach_storage(0, method=METHOD_BY_REFERENCE, long="ref-2.txt", mime="text/plain"),
            _attach_storage(1, method=METHOD_BY_REFERENCE_RESOLVE, long="ref-3.txt", mime="text/plain"),
            _attach_storage(2, method=METHOD_BY_REFERENCE_ONLY, long="ref-4.txt", mime="text/plain"),
        )
    )


def _fixture_attachment_hostile_name() -> bytes:
    """A hostile filename (path separators, ``..``, NUL): data, never a path (D3)."""
    return _g_fixture(
        attachments=(
            _attach_storage(
                0,
                method=METHOD_BY_VALUE,
                long="..\\evil/../../x\x00y",
                mime="application/octet-stream",
                data=b"hostile",
            ),
        )
    )


def _fixture_attachment_zero_size() -> bytes:
    """A zero-length by-value attachment (D2)."""
    return _g_fixture(
        attachments=(
            _attach_storage(0, method=METHOD_BY_VALUE, long="empty.bin", mime="application/octet-stream", data=b""),
        )
    )


def _fixture_attachments_4095_4096_4097() -> bytes:
    """Three by-value attachments at the mini-cutoff sizes (D2)."""
    return _g_fixture(
        attachments=(
            _attach_storage(0, method=METHOD_BY_VALUE, long="a.bin", mime="application/octet-stream", data=_filler(4095, seed=1)),
            _attach_storage(1, method=METHOD_BY_VALUE, long="b.bin", mime="application/octet-stream", data=_filler(4096, seed=2)),
            _attach_storage(2, method=METHOD_BY_VALUE, long="c.bin", mime="application/octet-stream", data=_filler(4097, seed=3)),
        )
    )


def _fixture_duplicate_filenames() -> bytes:
    """Two attachments with the same filename (D2; the attach stage's duplicate gaps)."""
    return _g_fixture(
        attachments=(
            _attach_storage(0, method=METHOD_BY_VALUE, long="same.txt", mime="text/plain", data=b"first"),
            _attach_storage(1, method=METHOD_BY_VALUE, long="same.txt", mime="text/plain", data=b"second"),
        )
    )


FIXTURES = {
    "msg_headers_only": _fixture_headers_only,
    "msg_headers_html": _fixture_headers_html,
    "msg_v4_sectors": _fixture_v4_sectors,
    "msg_mini_cutoff_boundary": _fixture_mini_cutoff_boundary,
    "msg_outlook_layout_handbuilt": _fixture_outlook_layout_handbuilt,
    "msg_difat_extended": _fixture_difat_extended,
    "msg_fat_cycle": _fixture_fat_cycle,
    "msg_directory_loop": _fixture_directory_loop,
    "msg_truncated_stream": _fixture_truncated_stream,
    "msg_non_ipm_note": _fixture_non_ipm_note,
    "msg_signed_class": _fixture_signed_class,
    "msg_unknown_tags": _fixture_unknown_tags,
    "msg_named_properties": _fixture_named_properties,
    "msg_codepage_disagree": _fixture_codepage_disagree,
    "msg_html_only_no_plain": _fixture_html_only_no_plain,
    "msg_plain_only": _fixture_plain_only,
    "msg_plain_and_html": _fixture_plain_and_html,
    "msg_zero_length_body": _fixture_zero_length_body,
    "msg_html_meta_charset_contradicts": _fixture_html_meta_charset_contradicts,
    "msg_no_transport_headers": _fixture_no_transport_headers,
    "msg_transport_headers_utf8_bom": _fixture_transport_headers_utf8_bom,
    "msg_transport_headers_lf_only": _fixture_transport_headers_lf_only,
    "msg_property_vs_header_conflict": _fixture_property_vs_header_conflict,
    "msg_recipients_display_only": _fixture_recipients_display_only,
    "msg_recipients_ex_no_smtp": _fixture_recipients_ex_no_smtp,
    "msg_recipients_bcc_duplicates": _fixture_recipients_bcc_duplicates,
    "msg_time_property_vs_date_header": _fixture_time_property_vs_date_header,
    "msg_unicode_subject": _fixture_unicode_subject,
    "msg_embedded_message": _fixture_embedded_message,
    "msg_embedded_depth_two": _fixture_embedded_depth_two,
    "msg_attachment_with_cid": _fixture_attachment_with_cid,
    "msg_attachment_hidden": _fixture_attachment_hidden,
    "msg_attachment_ole": _fixture_attachment_ole,
    "msg_attachment_by_reference": _fixture_attachment_by_reference,
    "msg_attachment_hostile_name": _fixture_attachment_hostile_name,
    "msg_attachment_zero_size": _fixture_attachment_zero_size,
    "msg_attachments_4095_4096_4097": _fixture_attachments_4095_4096_4097,
    "msg_duplicate_filenames": _fixture_duplicate_filenames,
}

#: Every committed fixture, in build order: the writer's five, ``msg_difat_extended``,
#: then the three hostile mutants.
ALL_FIXTURE_NAMES: tuple[str, ...] = tuple(FIXTURES)
#: The fixtures that are the hostile base's bytes with one 32-bit word patched. They have
#: **no** construction table -- their expected behaviour is hand-typed in
#: ``tests/support/msg_construction.py`` (``HOSTILE_EXPECTATIONS``) -- and the ``olefile``
#: oracle never judges one (E1).
HOSTILE_FIXTURE_NAMES: tuple[str, ...] = (
    "msg_fat_cycle",
    "msg_directory_loop",
    "msg_truncated_stream",
)
#: The well-formed fixtures: the five from Turn 1b.2 plus ``msg_difat_extended``. Every one
#: has a construction table and is judged by the oracle; this is the set the ``olefile``
#: tests iterate.
FIXTURE_NAMES: tuple[str, ...] = tuple(
    name for name in ALL_FIXTURE_NAMES if name not in HOSTILE_FIXTURE_NAMES
)


def build_fixture(name: str) -> bytes:
    """The ``.msg`` bytes of one fixture, from its description (no file touched)."""
    return FIXTURES[name]()


def build_all() -> dict[str, bytes]:
    """Every committed fixture's bytes, keyed by name."""
    return {name: build_fixture(name) for name in ALL_FIXTURE_NAMES}


def _sha256(name: str, data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sums_text() -> str:
    return "".join(
        f"{_sha256(name, build_fixture(name))}  {name}.msg\n" for name in ALL_FIXTURE_NAMES
    )


def _emit(target: Path, data: bytes, check: bool) -> bool:
    if check:
        on_disk = target.read_bytes() if target.exists() else None
        if on_disk != data:
            print(f"DIFFERS  {target}")
            return False
        print(f"ok       {target}")
        return True
    target.write_bytes(data)
    print(f"wrote    {target}  ({len(data)} bytes)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="generate the .msg fixtures")
    parser.add_argument("--check", action="store_true", help="exit 1 unless the files on disk already match")
    args = parser.parse_args()

    MSG.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, data in build_all().items():
        if not _emit(MSG / f"{name}.msg", data, args.check):
            failures.append(name)
    sums = _sums_text()
    if args.check:
        on_disk = SUMS.read_text(encoding="utf-8") if SUMS.is_file() else None
        if on_disk != sums:
            print(f"DIFFERS  {SUMS}")
            failures.append("SHA256SUMS")
        else:
            print(f"ok       {SUMS}")
    else:
        SUMS.write_text(sums, encoding="utf-8")
        print(f"wrote    {SUMS}")
    if failures:
        print(f"regeneration differs for: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
