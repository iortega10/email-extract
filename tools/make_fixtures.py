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
    return b"".join(name.encode("ascii") + b": " + value.encode("ascii") + CRLF for name, value in headers)


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
