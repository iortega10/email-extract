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
PROP_TRANSPORT_HEADERS = 0x007D
PROP_BODY_HTML = 0x1013
PROP_RECIPIENT_TYPE = 0x3001
PROP_RECIPIENT_EMAIL_TYPE = 0x3003
PROP_RECIPIENT_DISPLAY = 0x3002
PROP_ATTACH_METHOD = 0x3705
PROP_ATTACH_MIME = 0x370E
PROP_ATTACH_FILENAME = 0x3707
PROP_ATTACH_RENDERING = 0x370B
PROP_ATTACH_DATA = 0x3701


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
    """Hand-built to the observed Outlook structure (B1-B4), never to a default."""
    nameid_20, nameid_30, nameid_40 = (
        _filler(size, seed=size) for size in NAMEID_SIZES
    )
    recipient = _sub_property_stream(
        _prop_entry(PROP_RECIPIENT_TYPE, PT_LONG, struct.pack("<I", 1))
        + _prop_entry(PROP_RECIPIENT_EMAIL_TYPE, PT_UNICODE, b"")
        + _prop_entry(PROP_RECIPIENT_DISPLAY, PT_UNICODE, _utf16("Ada", 8))
    )
    attachment = _sub_property_stream(
        _prop_entry(PROP_ATTACH_METHOD, PT_LONG, struct.pack("<I", 1))
        + _prop_entry(PROP_ATTACH_MIME, PT_UNICODE, _utf16("text", 8))
        + _prop_entry(PROP_ATTACH_FILENAME, PT_UNICODE, b"")
        + _prop_entry(PROP_ATTACH_RENDERING, PT_LONG, struct.pack("<I", 0))
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", _message_property_stream(1, 1)),
            storage(
                "__nameid_version1.0",
                stream("__substg1.0_00020102", nameid_20),
                stream("__substg1.0_00030102", nameid_30),
                stream("__substg1.0_00040102", nameid_40),
            ),
            stream("__substg1.0_007D001F", _transport_header_stream()),
            stream("__substg1.0_10130102", _html_body()),
            storage(
                "__recip_version1.0_#00000000",
                stream("__properties_version1.0", recipient),
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
