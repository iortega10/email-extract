"""Turn 1b.2: the first ``.msg`` fixtures, built from hand-typed descriptions.

Each fixture is described here as a storage tree of named streams with exact byte
content, handed to ``tools/cfb_writer.py`` (the deterministic minimal CFB writer).
The writer is deliberately *dumb about MAPI*: it never knows a property tag, a
``__substg1.0_`` name or a body stream. Everything MAPI-shaped -- the 32-byte
top-level property header, the ``(propType << 16) | propId`` property entries, a
``__nameid_version1.0`` storage's three binary streams -- is typed here as ordinary
bytes.

Two rules, matching ``tools/make_fixtures.py``:

* **Deterministic and clock-free.** No timestamps, no CLSIDs, no randomness, no
  dict-order dependence. The same description gives byte-identical output on 3.11
  and 3.14 and on any platform.
* **Synthetic only.** No real or employer mail, and no text from a real message. The
  `.msg` files this writes are tiny and hand-built.

The sidecars (``*.expected.json``) are typed by hand and independently; no code in
this file writes, reads or knows about a sidecar.

Usage::

    python tools/make_msg_fixtures.py           # write the five fixtures + SHA256SUMS
    python tools/make_msg_fixtures.py --check   # exit 1 unless the bytes already match
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cfb_writer import Storage, build_cfb, storage, stream  # noqa: E402

__all__ = ["FIXTURE_NAMES", "build_all", "build_fixture"]

REPO_ROOT = Path(__file__).resolve().parent.parent
MSG = REPO_ROOT / "fixtures" / "msg"
SUMS = MSG / "SHA256SUMS"

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


FIXTURES = {
    "msg_headers_only": _fixture_headers_only,
    "msg_headers_html": _fixture_headers_html,
    "msg_v4_sectors": _fixture_v4_sectors,
    "msg_mini_cutoff_boundary": _fixture_mini_cutoff_boundary,
    "msg_outlook_layout_handbuilt": _fixture_outlook_layout_handbuilt,
}

FIXTURE_NAMES: tuple[str, ...] = tuple(FIXTURES)


def build_fixture(name: str) -> bytes:
    """The ``.msg`` bytes of one fixture, from its description (no file touched)."""
    return FIXTURES[name]()


def build_all() -> dict[str, bytes]:
    """Every fixture's bytes, keyed by name."""
    return {name: build_fixture(name) for name in FIXTURE_NAMES}


def _sha256(name: str, data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sums_text() -> str:
    return "".join(f"{_sha256(name, build_fixture(name))}  {name}.msg\n" for name in FIXTURE_NAMES)


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
    parser = argparse.ArgumentParser(description="generate the Turn 1b.2 .msg fixtures")
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
