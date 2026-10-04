"""Turn 0.3: the declarative ``.eml`` fixture generator (build spec, Turn 0.3; D11).

Each fixture is a Python description -- headers, parts, boundaries, encodings and
attachment bytes inline in this file -- rendered to ``.eml`` by this module's own
renderer. Two rules make regeneration byte-identical on every interpreter, both
learned from defects found in the sibling repository (build spec, Turn 0.3):

* **The renderer is ours.** Every header line, boundary and CRLF is written
  explicitly here. ``email.message`` / ``email.generator`` serialization is never
  used to produce the bytes: the stdlib ``email`` package changed folding, line
  ending and boundary behaviour between Python 3.11 and 3.14 (email-spike c02),
  and a fixture that re-serializes through it would differ by interpreter.
  ``base64`` and ``quopri`` transfer encoding of a payload is deterministic and
  is used.
* **Attachment bytes never depend on the zlib build.** CPython 3.14 on Windows
  ships zlib-ng and 3.11 ships zlib 1.3.1, which DEFLATE the same bytes
  differently. So the xlsx and docx attachments are zips written ``ZIP_STORED``
  with pinned timestamps, ``create_system`` and ``external_attr`` and a fixed
  member order, the png is a hand-built zlib stream of *stored* deflate blocks,
  and the pdf carries no compressed stream. Nothing here compresses anything.

The generator writes only ``fixtures/generated/*.eml``. The sidecars
(``*.expected.json``) are typed by hand and independently (D11): no code in this
file writes, reads or knows about a sidecar.

Usage::

    python tools/make_fixtures.py           # write the eight fixtures
    python tools/make_fixtures.py --check   # exit 1 unless bytes already match
"""

from __future__ import annotations

import argparse
import base64
import quopri
import struct
import sys
import zlib
from pathlib import Path

__all__ = [
    "FIXTURE_NAMES",
    "TIME_FIXTURE_NAMES",
    "build_all",
    "build_fixture",
    "build_time_all",
]

CRLF = b"\r\n"
REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED = REPO_ROOT / "fixtures" / "generated"
TIME = REPO_ROOT / "fixtures" / "time"

#: Pinned once and forever: a regenerated fixture is the same bytes, so its
#: sha256 is identity, not a timestamp of when it was built.
PINNED_DATE_0800 = "Tue, 4 Mar 2025 08:00:00 +0000"
PINNED_DATE_0805 = "Tue, 4 Mar 2025 08:05:00 +0000"
PINNED_DATE_0758 = "Tue, 4 Mar 2025 07:58:00 +0000"
PINNED_DATE_0759 = "Tue, 4 Mar 2025 07:59:00 +0000"
PINNED_DATE_0900 = "Tue, 4 Mar 2025 09:00:00 +0000"
PINNED_DATE_0903 = "Tue, 4 Mar 2025 09:03:00 +0000"


# --------------------------------------------------------------- the renderer


class Leaf:
    """One non-multipart part: header pairs and the exact payload bytes."""

    def __init__(self, headers: list[tuple[str, str]], payload: bytes) -> None:
        self.headers = tuple(headers)
        self.payload = payload


class Multi:
    """One multipart part: header pairs, a pinned boundary, its children.

    ``preamble`` is the exact preamble text without its line ending; the CRLF in
    front of the first delimiter is written by the renderer. ``epilogue=None``
    ends the part at the close delimiter; ``epilogue=b""`` writes one final CRLF
    after it (a top-level message that ends cleanly); any other value is the
    exact epilogue text.
    """

    def __init__(
        self,
        headers: list[tuple[str, str]],
        boundary: str,
        children: list,
        preamble: bytes | None = None,
        epilogue: bytes | None = None,
    ) -> None:
        self.headers = tuple(headers)
        self.boundary = boundary
        self.children = tuple(children)
        self.preamble = preamble
        self.epilogue = epilogue


def _header_block(headers: tuple[tuple[str, str], ...]) -> bytes:
    # Values are encoded UTF-8: byte-identical to ASCII for every pure-ASCII
    # value (so the Turn 0.3 fixtures are unchanged), and it lets a fixture
    # carry the non-ASCII header bytes an IDN or SMTPUTF8 address needs.
    return b"".join(name.encode("ascii") + b": " + value.encode("utf-8") + CRLF for name, value in headers)


def render_part(node) -> bytes:
    """One part's bytes: its header block, the blank line, then its body."""
    body = b""
    if isinstance(node, Leaf):
        body = node.payload
    else:
        if node.preamble is not None:
            body += node.preamble + CRLF
        for child in node.children:
            body += b"--" + node.boundary.encode("ascii") + CRLF + render_part(child) + CRLF
        body += b"--" + node.boundary.encode("ascii") + b"--"
        if node.epilogue is not None:
            body += CRLF + node.epilogue
    return _header_block(node.headers) + CRLF + body


def render_message(node) -> bytes:
    """The message bytes: exactly what lands in the ``.eml`` file."""
    return render_part(node)


def _b64(data: bytes) -> bytes:
    """Transfer-encoded base64, wrapped at 76 columns with CRLF (RFC 2045)."""
    encoded = base64.b64encode(data)
    lines = [encoded[index : index + 76] for index in range(0, len(encoded), 76)]
    return CRLF.join(lines) + CRLF


def _qp(data: bytes) -> bytes:
    return quopri.encodestring(data)


def _encoded_word(text: str) -> str:
    """An RFC 2047 ``=?utf-8?b?...?=`` word for a header value (deterministic)."""
    return "=?utf-8?b?" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "?="


# ------------------------------------------------- attachment bytes (stored only)


def _crc(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _dos_time_date(ymd_hms: tuple[int, int, int, int, int, int]) -> tuple[int, int]:
    year, month, day, hour, minute, second = ymd_hms
    dos_time = (hour << 11) | (minute << 5) | (second // 2)
    dos_date = ((year - 1980) << 9) | (month << 5) | day
    return dos_time, dos_date


def zip_stored(members: list[tuple[str, bytes]]) -> bytes:
    """A zip with every member ``ZIP_STORED``: no deflate, nothing build-dependent.

    Timestamps, ``create_system``, ``external_attr`` and the member order are
    pinned by this function, so the same members always give the same bytes on
    any interpreter and any zlib build. ``zlib.crc32`` is a checksum, not a
    compressor, and is deterministic everywhere.
    """
    dos_time, dos_date = _dos_time_date((2025, 3, 4, 8, 0, 0))
    create_system = 0
    external_attr = 0
    locals_blob = b""
    centrals_blob = b""
    offset = 0
    for name, data in members:
        name_bytes = name.encode("utf-8")
        crc = _crc(data)
        local = (
            struct.pack(
                "<IHHHHHIIIHH",
                0x04034B50,
                20,
                0,
                0,
                dos_time,
                dos_date,
                crc,
                len(data),
                len(data),
                len(name_bytes),
                0,
            )
            + name_bytes
            + data
        )
        central = (
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                (create_system << 8) | 20,
                20,
                0,
                0,
                dos_time,
                dos_date,
                crc,
                len(data),
                len(data),
                len(name_bytes),
                0,
                0,
                0,
                0,
                external_attr,
                offset,
            )
            + name_bytes
        )
        locals_blob += local
        centrals_blob += central
        offset += len(local)
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(members),
        len(members),
        len(centrals_blob),
        len(locals_blob),
        0,
    )
    return locals_blob + centrals_blob + eocd


def _deflate_stored(data: bytes) -> bytes:
    """A zlib (RFC 1950) stream of uncompressed (stored) deflate blocks."""
    out = bytearray(b"\x78\x01")
    position = 0
    while position < len(data) or position == 0:
        block = data[position : position + 65535]
        final = position + 65535 >= len(data)
        out += b"\x01" if final else b"\x00"
        out += struct.pack("<HH", len(block), (~len(block)) & 0xFFFF)
        out += block
        position += 65535
        if len(data) == 0:
            break
    out += struct.pack(">I", zlib.adler32(data) & 0xFFFFFFFF)
    return bytes(out)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", _crc(kind + data))


def tiny_png(pixel: bytes, width: int = 2, height: int = 2) -> bytes:
    """A real PNG whose IDAT is stored (uncompressed) deflate -- never zlib-ng's."""
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", _deflate_stored(raw))
        + _png_chunk(b"IEND", b"")
    )


def tiny_pdf(text: str) -> bytes:
    """A minimal valid one-page PDF: no compressed stream, offsets computed here."""
    content = f"BT /F1 12 Tf 8 40 Td ({text}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(index).encode("ascii") + b" 0 obj\n" + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode("ascii") + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode("ascii")
    out += (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_at).encode("ascii")
        + b"\n%%EOF\n"
    )
    return bytes(out)


_CONTENT_TYPES_XLSX = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    b'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    b"</Types>\n"
)

_RELS_ROOT = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    b"</Relationships>\n"
)

def tiny_xlsx() -> bytes:
    """A minimal but valid xlsx: one sheet, one cell, every member stored."""
    return zip_stored(
        [
            ("[Content_Types].xml", _CONTENT_TYPES_XLSX),
            ("_rels/.rels", _RELS_ROOT),
            (
                "xl/workbook.xml",
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                b'<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>\n',
            ),
            (
                "xl/_rels/workbook.xml.rels",
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                b"</Relationships>\n",
            ),
            (
                "xl/worksheets/sheet1.xml",
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>fixture</t></is></c></row></sheetData>'
                b"</worksheet>\n",
            ),
        ]
    )


def tiny_docx() -> bytes:
    """A minimal but valid docx: one paragraph, every member stored."""
    return zip_stored(
        [
            (
                "[Content_Types].xml",
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                b'<Default Extension="xml" ContentType="application/xml"/>'
                b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                b"</Types>\n",
            ),
            ("_rels/.rels", _RELS_ROOT_DOCX := (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                b"</Relationships>\n"
            )),
            (
                "word/document.xml",
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                b"<w:body><w:p><w:r><w:t>fixture</w:t></w:r></w:p></w:body></w:document>\n",
            ),
        ]
    )


# ----------------------------------------------------------- the eight fixtures


def _plain_leaf(ctype: str, text: bytes) -> Leaf:
    return Leaf([("Content-Type", ctype)], text)


def _attachment_leaf(ctype: str, filename: str, data: bytes) -> Leaf:
    return Leaf(
        [
            ("Content-Type", ctype),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Transfer-Encoding", "base64"),
        ],
        _b64(data),
    )


def _fixture_plain_simple() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "plain simple"),
                ("Date", PINNED_DATE_0800),
                ("Message-ID", "<plain-simple-0001@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"Hello Ben.\r\n\r\nThis is the plain simple fixture.\r\n",
        )
    )


def _fixture_alternative_text_html() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "alternative text html"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<alt-text-html-0002@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/alternative; boundary="b0-alt-20250304"'),
            ],
            "b0-alt-20250304",
            [
                _plain_leaf("text/plain; charset=utf-8", b"Hello Ben.\r\n\r\nA plain view.\r\n"),
                _plain_leaf("text/html; charset=utf-8", b"<p>Hello Ben.</p>\r\n<p>A plain view.</p>\r\n"),
            ],
            epilogue=b"",
        )
    )


def _fixture_multipart_mixed_wraps_alternative() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "mixed wraps alternative"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<mixed-wraps-alt-0003@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-mixed-20250304"'),
            ],
            "b0-mixed-20250304",
            [
                Multi(
                    [("Content-Type", 'multipart/alternative; boundary="b0-inner-alt-20250304"')],
                    "b0-inner-alt-20250304",
                    [
                        _plain_leaf("text/plain; charset=utf-8", b"Hello Ben.\r\n\r\nA plain view.\r\n"),
                        _plain_leaf("text/html; charset=utf-8", b"<p>Hello Ben.</p>\r\n<p>A plain view.</p>\r\n"),
                    ],
                ),
                _attachment_leaf("application/pdf", "report.pdf", tiny_pdf("tiny fixture")),
            ],
            epilogue=b"",
        )
    )


def _fixture_rfc2047_folded_duplicate_received() -> bytes:
    subject_word = _encoded_word("Hello \u2605")
    subject_word_two = _encoded_word(" folded subject")
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 07:58:00 +0000"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 07:59:00 +0000"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 07:59:00 +0000"),
                ("Subject", f"{subject_word}\r\n {subject_word_two}"),
                ("X-Folded-Note", "a plain value that\r\n\tcontinues on a folded line"),
                ("Date", PINNED_DATE_0900),
                ("Message-ID", "<rfc2047-folded-0004@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=utf-8"),
            ],
            b"Hello Ben.\r\n\r\nOne folded encoded word, three Received fields.\r\n",
        )
    )


def _fixture_attachments_mixed() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "attachments mixed"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<attachments-mixed-0005@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-attach-20250304"'),
            ],
            "b0-attach-20250304",
            [
                _plain_leaf("text/plain; charset=us-ascii", b"Hello Ben.\r\n\r\nFour tiny attachments.\r\n"),
                _attachment_leaf("application/pdf", "tiny.pdf", tiny_pdf("tiny fixture")),
                _attachment_leaf(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "tiny.xlsx",
                    tiny_xlsx(),
                ),
                _attachment_leaf(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "tiny.docx",
                    tiny_docx(),
                ),
                _attachment_leaf("image/png", "tiny.png", tiny_png(b"\x10\x20\x30")),
            ],
            epilogue=b"",
        )
    )


def _fixture_inline_cid_referenced_and_not() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "inline cid referenced and not"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<inline-cid-0006@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/related; boundary="b0-cid-20250304"'),
            ],
            "b0-cid-20250304",
            [
                _plain_leaf(
                    "text/html; charset=utf-8",
                    b'<p>Hello Ben.</p>\r\n<img src="cid:logo@example.test" alt="logo">\r\n',
                ),
                Leaf(
                    [
                        ("Content-Type", "image/png"),
                        ("Content-ID", "<logo@example.test>"),
                        ("Content-Disposition", 'inline; filename="logo.png"'),
                        ("Content-Transfer-Encoding", "base64"),
                    ],
                    _b64(tiny_png(b"\x10\x20\x30")),
                ),
                Leaf(
                    [
                        ("Content-Type", "image/png"),
                        ("Content-ID", "<spare@example.test>"),
                        ("Content-Disposition", 'inline; filename="spare.png"'),
                        ("Content-Transfer-Encoding", "base64"),
                    ],
                    _b64(tiny_png(b"\x40\x50\x60")),
                ),
            ],
            epilogue=b"",
        )
    )


def _fixture_thread_three_refs_chain() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 09:00:00 +0000"),
                ("Received", "from c.example by a.example; Tue, 4 Mar 2025 09:01:00 +0000"),
                ("Subject", "thread three refs chain"),
                ("Date", PINNED_DATE_0903),
                ("Message-ID", "<thread-child-0007@example.test>"),
                ("In-Reply-To", "<thread-parent-0002@example.test>"),
                (
                    "References",
                    "<thread-root-0000@example.test> <thread-mid-0001@example.test> <thread-parent-0002@example.test>",
                ),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"Hello Ben.\r\n\r\nThe third message in a chain.\r\n",
        )
    )


def _fixture_preamble_epilogue() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "preamble epilogue"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<preamble-epilogue-0008@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-pre-20250304"'),
            ],
            "b0-pre-20250304",
            [
                _plain_leaf("text/plain; charset=us-ascii", b"Hello Ben.\r\n\r\nOne part.\r\n"),
            ],
            preamble=b"This is the preamble text.",
            epilogue=b"And this is the epilogue text.\r\n",
        )
    )


# ------------------------------- Family A : headers, date and address fixtures


def _fixture_headers_plain_baseline() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Cc", "Cara Copy <cara@example.test>"),
                ("Subject", _encoded_word("baseline \u2605")),
                ("Date", PINNED_DATE_0800),
                ("Message-ID", "<headers-baseline-1001@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"Baseline body.\r\n",
        )
    )


def _fixture_duplicate_header_mime_version() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "duplicate mime version"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<dup-mime-version-1002@example.test>"),
                ("MIME-Version", "1.0"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"Two MIME-Version fields.\r\n",
        )
    )


def _fixture_mime_version_missing() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "mime version missing"),
                ("Date", PINNED_DATE_0800),
                ("Message-ID", "<mime-version-missing-1003@example.test>"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"No MIME-Version field here.\r\n",
        )
    )


def _fixture_mixed_case_header_and_param_names() -> bytes:
    return render_message(
        Multi(
            [
                ("FROM", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("SUBJECT", "mixed case header and param names"),
                ("DATE", PINNED_DATE_0805),
                ("Message-ID", "<mixed-case-names-1004@example.test>"),
                ("mime-version", "1.0"),
                ("CONTENT-TYPE", 'multipart/MIXED; Boundary="b0-MixedCase-20250304"'),
            ],
            "b0-MixedCase-20250304",
            [
                Leaf([("content-type", "text/PLAIN; CHARSET=UTF-8")], b"Mixed case body.\r\n"),
            ],
            epilogue=b"",
        )
    )


def _fixture_encoded_word_valid() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", _encoded_word("valid \u2605 word")),
                ("Date", PINNED_DATE_0800),
                ("Message-ID", "<encoded-word-valid-1005@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"One valid encoded word.\r\n",
        )
    )


def _fixture_encoded_word_mixed_charsets() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "=?utf-8?b?TWl4ZWQg?= =?iso-8859-1?q?charsets?="),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<encoded-word-mixed-1006@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"Two adjacent encoded words, two charsets.\r\n",
        )
    )


def _fixture_encoded_word_split_across_fold() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "=?utf-8?b?4g==?=\r\n =?utf-8?b?mIU=?="),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<encoded-word-split-1007@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"One multibyte character split across two words over a fold.\r\n",
        )
    )


def _fixture_rfc2231_segment0_charset() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "rfc2231 segment0 charset"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<rfc2231-segment0-1008@example.test>"),
                ("MIME-Version", "1.0"),
                (
                    "Content-Type",
                    "text/plain; charset=utf-8; name*0*=utf-8''r%C3%A9sum%C3%A9; name*1*=.txt",
                ),
            ],
            b"RFC 2231 charset on segment 0 only.\r\n",
        )
    )


def _fixture_rfc2231_continuations() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "rfc2231 continuations"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<rfc2231-continuations-1009@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "application/octet-stream"),
                (
                    "Content-Disposition",
                    'attachment; filename*0="report-"; filename*1="part.pdf"',
                ),
                ("Content-Transfer-Encoding", "base64"),
            ],
            _b64(b"RFC 2231 numbered continuations.\n"),
        )
    )


def _fixture_rfc2231_empty_charset_fallback() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "rfc2231 empty charset fallback"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<rfc2231-empty-charset-1010@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "application/octet-stream"),
                ("Content-Disposition", "attachment; filename*=''run.log"),
                ("Content-Transfer-Encoding", "base64"),
            ],
            _b64(b"An empty charset is a recorded fallback.\n"),
        )
    )


def _fixture_date_stated_zone() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "date stated zone"),
                ("Date", "Tue, 4 Mar 2025 08:05:00 +0000"),
                ("Message-ID", "<date-stated-zone-1011@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"A Date with a stated zone.\r\n",
        )
    )


def _fixture_date_minus_zero() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "date minus zero"),
                ("Date", "Tue, 4 Mar 2025 08:05:00 -0000"),
                ("Message-ID", "<date-minus-zero-1012@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"A Date whose zone token is -0000.\r\n",
        )
    )


def _fixture_date_absent() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "date absent"),
                ("Message-ID", "<date-absent-1013@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"There is no Date field at all.\r\n",
        )
    )


def _fixture_address_group() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Friends: ben@example.test, cara@example.test;"),
                ("Subject", "address group"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<address-group-1014@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"A To field that is a group with two members.\r\n",
        )
    )


def _fixture_address_undisclosed_recipients() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "undisclosed-recipients:;"),
                ("Subject", "address undisclosed recipients"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<address-undisclosed-1015@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"A zero-member group in the To field.\r\n",
        )
    )


def _fixture_address_quoted_comma_display_name() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", '"Doe, Jane" <jane@example.test>'),
                ("Subject", "address quoted comma display name"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<address-quoted-comma-1016@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"A quoted display name that contains a comma.\r\n",
        )
    )


def _fixture_address_idn_domain() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ada Sender <ada@b\u00fcro.example.test>"),
                ("Subject", "address idn domain"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<address-idn-1017@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"An IDN domain kept verbatim.\r\n",
        )
    )


def _fixture_address_smtputf8_local_part() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Jos\u00e9 <jos\u00e9@example.test>"),
                ("Subject", "address smtputf8 local part"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<address-smtputf8-1018@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"An SMTPUTF8 local part kept verbatim.\r\n",
        )
    )


# ---------------------------------------------- Family B : body and HTML fixtures


def _fixture_body_plain_multipart_baseline() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "body plain multipart baseline"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<body-plain-baseline-3001@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/alternative; boundary="b0-body-20250304"'),
            ],
            "b0-body-20250304",
            [
                _plain_leaf("text/plain; charset=utf-8", b"Hello Ben.\r\n\r\nThis is the plain baseline.\r\n"),
                _plain_leaf(
                    "text/plain; charset=utf-8",
                    b"Hello Ben.\r\n\r\nThis is the plain baseline, second view.\r\n",
                ),
            ],
            epilogue=b"",
        )
    )


def _fixture_plain_effectively_empty() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "plain effectively empty"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<plain-empty-3002@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/alternative; boundary="b0-empty-20250304"'),
            ],
            "b0-empty-20250304",
            [
                _plain_leaf("text/plain; charset=utf-8", b"   \r\n"),
                _plain_leaf("text/html; charset=utf-8", b"<p>Hi Ben.</p>\r\n"),
            ],
            epilogue=b"",
        )
    )


def _fixture_nested_alternative_in_related_in_mixed() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "nested alternative in related in mixed"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<nested-alt-3003@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-outer-20250304"'),
            ],
            "b0-outer-20250304",
            [
                Multi(
                    [("Content-Type", 'multipart/related; boundary="b0-related-20250304"')],
                    "b0-related-20250304",
                    [
                        Multi(
                            [("Content-Type", 'multipart/alternative; boundary="b0-inner-20250304"')],
                            "b0-inner-20250304",
                            [
                                _plain_leaf("text/plain; charset=utf-8", b"Plain view.\r\n"),
                                _plain_leaf("text/html; charset=utf-8", b"<p>HTML view.</p>\r\n"),
                            ],
                            epilogue=b"",
                        )
                    ],
                    epilogue=b"",
                )
            ],
            epilogue=b"",
        )
    )


def _fixture_content_location_in_related() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "content location in related"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<content-location-3004@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/related; boundary="b0-cl-20250304"'),
            ],
            "b0-cl-20250304",
            [
                Leaf(
                    [
                        ("Content-Type", "text/html; charset=utf-8"),
                        ("Content-ID", "<page@example.test>"),
                    ],
                    b'<p>Photo below.</p>\r\n<img src="cid:photo@example.test">\r\n'
                    b'<img src="http://example.test/banner.png">\r\n',
                ),
                Leaf(
                    [
                        ("Content-Type", "application/octet-stream"),
                        ("Content-ID", "<photo@example.test>"),
                        ("Content-Location", "http://example.test/photo.png"),
                        ("Content-Transfer-Encoding", "base64"),
                    ],
                    _b64(b"photo bytes\n"),
                ),
            ],
            epilogue=b"",
        )
    )


def _fixture_text_calendar_alternative() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "text calendar alternative"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<text-calendar-3005@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/alternative; boundary="b0-cal-20250304"'),
            ],
            "b0-cal-20250304",
            [
                _plain_leaf("text/plain; charset=utf-8", b"Plain view.\r\n"),
                _plain_leaf("text/html; charset=utf-8", b"<p>HTML view.</p>\r\n"),
                _plain_leaf(
                    "text/calendar; charset=utf-8",
                    b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
                ),
            ],
            epilogue=b"",
        )
    )


def _fixture_html_style_and_script() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "html style and script"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<html-style-script-3006@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/html; charset=utf-8"),
            ],
            b"<html><head><style>p { color: red; }</style><script>var x = 1;</script></head>"
            b"<body><p>Hello Ben.</p></body></html>\r\n",
        )
    )


def _fixture_html_href_img_remote_and_cid() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "html href img remote and cid"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<html-href-img-3007@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/html; charset=utf-8"),
            ],
            b'<p>Hi <a href="mailto:ben@example.test">Ben</a></p>\r\n'
            b'<img src="http://example.test/pic.png" alt="pic">\r\n'
            b'<img src="cid:logo@example.test" alt="logo">\r\n',
        )
    )


def _fixture_html_data_uri_and_tracking_pixel() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "html data uri and tracking pixel"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<html-data-uri-3008@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/html; charset=utf-8"),
            ],
            b'<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs=" '
            b'width="1" height="1">\r\n'
            b'<img src="http://example.test/pixel.gif" width="1" height="1">\r\n',
        )
    )


def _fixture_boundary_with_tspecials() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "boundary with tspecials"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<boundary-tspecials-3009@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-tspec+ial/20250304"'),
            ],
            "b0-tspec+ial/20250304",
            [_plain_leaf("text/plain; charset=utf-8", b"A part in a quoted boundary.\r\n")],
            epilogue=b"",
        )
    )


def _fixture_multipart_with_cte() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "multipart with cte"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<multipart-cte-3010@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-cte-20250304"'),
                ("Content-Transfer-Encoding", "base64"),
            ],
            "b0-cte-20250304",
            [_plain_leaf("text/plain; charset=utf-8", b"A part under a multipart CTE claim.\r\n")],
            epilogue=b"",
        )
    )


def _fixture_multipart_signed() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "multipart signed"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<multipart-signed-3011@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/signed; boundary="b0-signed-20250304"'),
            ],
            "b0-signed-20250304",
            [
                _plain_leaf("text/plain; charset=utf-8", b"Signed body.\r\n"),
                Leaf(
                    [("Content-Type", "application/pkcs7-signature")],
                    _b64(b"not a real signature\n"),
                ),
            ],
            epilogue=b"",
        )
    )


def _fixture_multipart_digest_content_type_less_child() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "multipart digest content type less child"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<digest-no-ctype-3012@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/digest; boundary="b0-digest-20250304"'),
            ],
            "b0-digest-20250304",
            [Leaf([], b"Plain digest body.\r\n")],
            epilogue=b"",
        )
    )


def _fixture_flowed_unstuffed_soft_break() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "flowed unstuffed soft break"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<flowed-unstuffed-3013@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=utf-8; format=flowed"),
            ],
            b"A soft break ends here \r\n and this line was space-stuffed.\r\n",
        )
    )


def _fixture_body_no_text_part() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "body no text part"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<body-no-text-3014@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-notext-20250304"'),
            ],
            "b0-notext-20250304",
            [
                Leaf(
                    [
                        ("Content-Type", "application/pdf"),
                        ("Content-Disposition", 'attachment; filename="doc.pdf"'),
                        ("Content-Transfer-Encoding", "base64"),
                    ],
                    _b64(b"%PDF-1.4\nfixture\n%%EOF\n"),
                )
            ],
            epilogue=b"",
        )
    )


def _fixture_inline_interleaved_reply_body() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "inline interleaved reply body"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<inline-interleaved-3015@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=utf-8"),
            ],
            b"Thanks, answers below.\r\n\r\n"
            b"On Tue, 4 Mar 2025 at 09:00, Ada Sender wrote:\r\n"
            b"> first point\r\n\r\n"
            b"My answer to the first point.\r\n\r\n"
            b"> second point\r\n\r\n"
            b"My answer to the second point.\r\n",
        )
    )


def _fixture_text_part_with_body_parts_tree() -> bytes:
    return render_message(
        Multi(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "text part with body parts tree"),
                ("Date", PINNED_DATE_0805),
                ("Message-ID", "<body-parts-tree-3016@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", 'multipart/mixed; boundary="b0-rfc822-20250304"'),
            ],
            "b0-rfc822-20250304",
            [
                Leaf(
                    [("Content-Type", "message/rfc822")],
                    b"From: Ada Sender <ada@example.test>\r\n"
                    b"Subject: inner message\r\n"
                    b"\r\n"
                    b"Inner body, never recursed.\r\n",
                )
            ],
            epilogue=b"",
        )
    )


# ------------------------------------------- the five TimeEvent conflict fixtures


def _fixture_date_before_hops() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Received", "from b.example by c.example; Tue, 4 Mar 2025 12:05:00 +0000"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 12:00:00 +0000"),
                ("Subject", "date before every hop"),
                ("Date", "Tue, 4 Mar 2025 08:00:00 +0000"),
                ("Message-ID", "<time-date-before-hops@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"The claimed Date is four hours before the chain entry.\r\n",
        )
    )


def _fixture_received_clock_skew() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Received", "from b.example by c.example; Tue, 4 Mar 2025 10:05:00 +0000"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 10:10:00 +0000"),
                ("Subject", "received timestamps out of header order"),
                ("Date", "Tue, 4 Mar 2025 10:00:00 +0000"),
                ("Message-ID", "<time-received-clock-skew@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"The first hop claims a later timestamp than the last hop.\r\n",
        )
    )


def _fixture_date_no_zone() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Received", "from a.example by b.example; Tue, 4 Mar 2025 15:00:00 +0000"),
                ("Subject", "date with no local time"),
                ("Date", "Tue, 4 Mar 2025 14:30:00 -0000"),
                ("Message-ID", "<time-date-no-zone@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"The Date says -0000: no local time is known, and it is not +0000.\r\n",
        )
    )


def _fixture_date_vs_mtime() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "date versus file mtime"),
                ("Date", "Tue, 4 Mar 2025 16:00:00 +0000"),
                ("Message-ID", "<time-date-vs-mtime@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"The file mtime beside this message is simulated: 2025-03-06T09:12:00Z.\r\n",
        )
    )


def _fixture_future_date_in_text() -> bytes:
    return render_message(
        Leaf(
            [
                ("From", "Ada Sender <ada@example.test>"),
                ("To", "Ben Receiver <ben@example.test>"),
                ("Subject", "a future date mentioned in the text"),
                ("Date", "Tue, 4 Mar 2025 17:00:00 +0000"),
                ("Message-ID", "<time-future-date-in-text@example.test>"),
                ("MIME-Version", "1.0"),
                ("Content-Type", "text/plain; charset=us-ascii"),
            ],
            b"Our records show 15 Jun 2030 as the renewal date.\r\n",
        )
    )


TIME_FIXTURES = {
    "date_before_hops": _fixture_date_before_hops,
    "received_clock_skew": _fixture_received_clock_skew,
    "date_no_zone": _fixture_date_no_zone,
    "date_vs_mtime": _fixture_date_vs_mtime,
    "future_date_in_text": _fixture_future_date_in_text,
}

TIME_FIXTURE_NAMES: tuple[str, ...] = tuple(TIME_FIXTURES)


FIXTURES = {
    "plain_simple": _fixture_plain_simple,
    "alternative_text_html": _fixture_alternative_text_html,
    "multipart_mixed_wraps_alternative": _fixture_multipart_mixed_wraps_alternative,
    "rfc2047_folded_duplicate_received": _fixture_rfc2047_folded_duplicate_received,
    "attachments_mixed": _fixture_attachments_mixed,
    "inline_cid_referenced_and_not": _fixture_inline_cid_referenced_and_not,
    "thread_three_refs_chain": _fixture_thread_three_refs_chain,
    "preamble_epilogue": _fixture_preamble_epilogue,
    "headers_plain_baseline": _fixture_headers_plain_baseline,
    "duplicate_header_mime_version": _fixture_duplicate_header_mime_version,
    "mime_version_missing": _fixture_mime_version_missing,
    "mixed_case_header_and_param_names": _fixture_mixed_case_header_and_param_names,
    "encoded_word_valid": _fixture_encoded_word_valid,
    "encoded_word_mixed_charsets": _fixture_encoded_word_mixed_charsets,
    "encoded_word_split_across_fold": _fixture_encoded_word_split_across_fold,
    "rfc2231_segment0_charset": _fixture_rfc2231_segment0_charset,
    "rfc2231_continuations": _fixture_rfc2231_continuations,
    "rfc2231_empty_charset_fallback": _fixture_rfc2231_empty_charset_fallback,
    "date_stated_zone": _fixture_date_stated_zone,
    "date_minus_zero": _fixture_date_minus_zero,
    "date_absent": _fixture_date_absent,
    "address_group": _fixture_address_group,
    "address_undisclosed_recipients": _fixture_address_undisclosed_recipients,
    "address_quoted_comma_display_name": _fixture_address_quoted_comma_display_name,
    "address_idn_domain": _fixture_address_idn_domain,
    "address_smtputf8_local_part": _fixture_address_smtputf8_local_part,
    # Family B: body and HTML (Turn 1.0c, commit 2)
    "body_plain_multipart_baseline": _fixture_body_plain_multipart_baseline,
    "plain_effectively_empty": _fixture_plain_effectively_empty,
    "nested_alternative_in_related_in_mixed": _fixture_nested_alternative_in_related_in_mixed,
    "content_location_in_related": _fixture_content_location_in_related,
    "text_calendar_alternative": _fixture_text_calendar_alternative,
    "html_style_and_script": _fixture_html_style_and_script,
    "html_href_img_remote_and_cid": _fixture_html_href_img_remote_and_cid,
    "html_data_uri_and_tracking_pixel": _fixture_html_data_uri_and_tracking_pixel,
    "boundary_with_tspecials": _fixture_boundary_with_tspecials,
    "multipart_with_cte": _fixture_multipart_with_cte,
    "multipart_signed": _fixture_multipart_signed,
    "multipart_digest_content_type_less_child": _fixture_multipart_digest_content_type_less_child,
    "flowed_unstuffed_soft_break": _fixture_flowed_unstuffed_soft_break,
    "body_no_text_part": _fixture_body_no_text_part,
    "inline_interleaved_reply_body": _fixture_inline_interleaved_reply_body,
    "text_part_with_body_parts_tree": _fixture_text_part_with_body_parts_tree,
}

FIXTURE_NAMES: tuple[str, ...] = tuple(FIXTURES)


def build_fixture(name: str) -> bytes:
    """The ``.eml`` bytes of one fixture, from its description."""
    if name in FIXTURES:
        return FIXTURES[name]()
    return TIME_FIXTURES[name]()


def build_all() -> dict[str, bytes]:
    """Every fixture's bytes, keyed by name (no file is touched)."""
    return {name: build_fixture(name) for name in FIXTURE_NAMES}


def build_time_all() -> dict[str, bytes]:
    """Every TimeEvent conflict fixture's bytes, keyed by name."""
    return {name: build_fixture(name) for name in TIME_FIXTURE_NAMES}


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
    parser = argparse.ArgumentParser(description="generate the Turn 0.3 .eml fixtures")
    parser.add_argument("--check", action="store_true", help="exit 1 unless the files on disk already match")
    args = parser.parse_args()

    failures = []
    GENERATED.mkdir(parents=True, exist_ok=True)
    TIME.mkdir(parents=True, exist_ok=True)
    for name, data in build_all().items():
        if not _emit(GENERATED / f"{name}.eml", data, args.check):
            failures.append(name)
    for name, data in build_time_all().items():
        if not _emit(TIME / f"{name}.eml", data, args.check):
            failures.append(name)
    if failures:
        print(f"regeneration differs for: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
