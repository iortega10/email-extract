"""Turn 0.3: the three RAW hand-written fixtures (build spec, Turn 0.3; D11).

``bad_charset``, ``truncated_base64`` and ``malformed_mime`` are hand-written
bytes: shapes a generator cannot honestly produce, because what they exercise is
broken encoding and broken MIME. The bytes live here as **byte literals, typed by
hand** -- this module copies those literals to ``fixtures/raw/`` verbatim and
nothing else; it has no description language and computes nothing about the
messages. It exists because the repository's file-writing tools write UTF-8 text
and these fixtures need raw ``\\xe9`` / ``\\x81`` bytes and CRLF line endings.

Once on disk the bytes are frozen: ``fixtures/raw/SHA256SUMS`` pins each sha256
and ``tests/test_fixtures.py`` fails if a byte changes. Regeneration is not the
identity rule here (unlike the generated eight); the frozen digest is.

Usage::

    python tools/write_raw_fixtures.py           # write the three fixtures
    python tools/write_raw_fixtures.py --check   # exit 1 unless bytes match
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "fixtures" / "raw"

# Hand-typed bytes. Nothing below is derived from anything: the line endings are
# CRLF, the 8-bit bytes are exactly the bytes named, and every broken shape is
# intentional (see the design registry for the gaps each one is expected to
# record).

BAD_CHARSET = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: bad charset\r\n"
    b"Date: Tue, 4 Mar 2025 10:00:00 +0000\r\n"
    b"Message-ID: <bad-charset-1001@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/alternative; boundary="b1-bad-charset"\r\n'
    b"\r\n"
    b"--b1-bad-charset\r\n"
    b"Content-Type: text/plain; charset=x-no-such-charset\r\n"
    b"\r\n"
    b"Caf\xe9 in a page that does not exist.\r\n"
    b"--b1-bad-charset\r\n"
    b"Content-Type: text/plain; charset=x-no-such-charset\r\n"
    b"\r\n"
    b"byte \x81 broke the round trip.\r\n"
    b"--b1-bad-charset--\r\n"
)

TRUNCATED_BASE64 = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: truncated base64\r\n"
    b"Date: Tue, 4 Mar 2025 10:05:00 +0000\r\n"
    b"Message-ID: <truncated-base64-1002@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    b"SGVsbG8gQmVuLg0KDQpBIHRydW5jYXRlZCBiYXNlNjQgYm9keS4NC\r\n"
)

MALFORMED_MIME = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"Subject: malformed mime\r\n"
    b"not a header line\r\n"
    b"X-After: still recorded\r\n"
    b"Date: Tue, 4 Mar 2025 10:10:00 +0000\r\n"
    b"Message-ID: <malformed-mime-1003@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1-malformed"\r\n'
    b"\r\n"
    b"--b1-malformed\r\n"
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"first part\r\n"
    b"--b1-malformed\r\n"
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"second part, and the close delimiter is missing\r\n"
)

DUPLICATE_CONTENT_TYPE_HEADER = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: duplicate content type header\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <dup-content-type-2001@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"The first Content-Type field wins.\r\n"
)

LEADING_UTF8_BOM = (
    b"\xef\xbb\xbf"
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: leading utf8 bom\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <leading-bom-2002@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"A UTF-8 BOM precedes the first header line.\r\n"
)

MBOX_FROM_LINE_AT_ZERO = (
    b"From ben@example.test Tue Mar 4 08:00:00 2025\r\n"
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: mbox from line at zero\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <mbox-from-2003@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"An mbox From line precedes the first header line.\r\n"
)

LONE_CR_IN_HEADER_REGION = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"X-Lone: one\rX-Next: two\r\n"
    b"Subject: lone cr in header region\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <lone-cr-2004@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"A lone CR terminates a header line.\r\n"
)

HEADER_LINE_OVER_998_BYTES = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: header line over 998 bytes\r\n"
    b"X-Long: " + b"a" * 1000 + b"\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <long-line-2005@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"One header line is longer than 998 bytes.\r\n"
)

NUL_IN_HEADER_VALUE = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: nul in header value\r\n"
    b"X-Nul: be\x00fore\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <nul-value-2006@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"A NUL in a header value; the field still parses.\r\n"
)

NUL_IN_HEADER_NAME = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: nul in header name\r\n"
    b"X-Nul\x00Name: value\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <nul-name-2007@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"A NUL in a field name makes it an unknown paragraph.\r\n"
)

HEADER_8BIT_RAW_BYTES = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: header 8bit raw bytes\r\n"
    b"X-8bit: caf\xe9 \x81 end\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <header-8bit-2008@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"8-bit bytes in a header value, viewed losslessly as latin-1.\r\n"
)

ENCODED_WORD_INVALID = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: =?utf-8?b?SGVsbG8?= and =?utf-8?q?a=b?=\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <encoded-word-invalid-2009@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"A B-word with wrong padding and a Q-word with a stray equals.\r\n"
)

DATE_INVALID = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: date invalid\r\n"
    b"Date: not a date at all\r\n"
    b"Message-ID: <date-invalid-2010@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"An invalid Date is never repaired.\r\n"
)

DATE_OFFSET_OUT_OF_RANGE = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: date offset out of range\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +9960\r\n"
    b"Message-ID: <date-offset-2011@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"An offset outside plus or minus 9959.\r\n"
)

ADDRESS_UNPARSABLE = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: not-an-address at all\r\n"
    b"Subject: address unparsable\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <address-unparsable-2012@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"An unparseable address, with the raw value kept beside it.\r\n"
)

BASE64_WHITESPACE_BAD_PADDING = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: base64 with whitespace and bad padding\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <base64-bad-padding-3017@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    b"SGVs bG8\r\n"
)

QP_RAW_8BIT = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: qp raw 8bit\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <qp-raw-8bit-3018@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=iso-8859-1\r\n"
    b"Content-Transfer-Encoding: quoted-printable\r\n"
    b"\r\n"
    b"Caf\xe9 =3D ok\r\n"
)

ISO_2022_JP_STATEFUL = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: iso 2022 jp stateful\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <iso-2022-jp-3019@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=iso-2022-jp\r\n"
    b"\r\n"
    b"\x1b$B$\"\x24$\x24&\x24(\x24*\x1b(B\r\n"
)

GB2312_DECLARED_GBK_BYTES = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: gb2312 declared gbk bytes\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <gb2312-gbk-3020@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=gb2312\r\n"
    b"\r\n"
    b"\xa1\x40\r\n"
)

WINDOWS_1252_DECLARED_ISO_8859_1 = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: windows 1252 declared iso 8859 1\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <windows-1252-3021@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=iso-8859-1\r\n"
    b"\r\n"
    b"\x93Hi\x94\r\n"
)

PREAMBLE_ONLY_MESSAGE = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: preamble only message\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <preamble-only-3022@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1-pre-only"\r\n'
    b"\r\n"
    b"The whole body is preamble, and no part follows.\r\n"
    b"--b1-pre-only--\r\n"
)

ATTACH_UNRECOGNIZED_MAGIC = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: attach unrecognized magic\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <c-unrecognized-4201@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1-c-unrecognized"\r\n'
    b"\r\n"
    b"--b1-c-unrecognized\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"One unrecognized attachment.\r\n"
    b"--b1-c-unrecognized\r\n"
    b"Content-Type: application/octet-stream\r\n"
    b'Content-Disposition: attachment; filename="blob.bin"\r\n'
    b"\r\n"
    b"nope: no signature here\r\n"
    b"--b1-c-unrecognized--\r\n"
)

ATTACH_OLE_CFB_MAGIC = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: attach ole cfb magic\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <c-ole-cfb-4202@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1-c-ole"\r\n'
    b"\r\n"
    b"--b1-c-ole\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"One OLE-CFB attachment.\r\n"
    b"--b1-c-ole\r\n"
    b"Content-Type: application/octet-stream\r\n"
    b'Content-Disposition: attachment; filename="legacy.doc"\r\n'
    b"\r\n"
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16 + b"invented ole bytes\r\n"
    b"--b1-c-ole--\r\n"
)

ATTACH_TNEF_WINMAIL = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: attach tnef winmail\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <c-tnef-4203@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1-c-tnef"\r\n'
    b"\r\n"
    b"--b1-c-tnef\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"One TNEF attachment.\r\n"
    b"--b1-c-tnef\r\n"
    b"Content-Type: application/ms-tnef\r\n"
    b'Content-Disposition: attachment; filename="winmail.dat"\r\n'
    b"\r\n"
    b"\x78\x9f\x3e\x22invented tnef bytes\r\n"
    b"--b1-c-tnef--\r\n"
)

#: The docm payload: a ZIP_STORED container (struct fields pinned, zlib.crc32 only)
#: holding a stored ``[Content_Types].xml`` and a stored ``word/vbaProject.bin``
#: stub. It is INERT -- never opened as a document, and the macro is a claim.
ATTACH_MACRO_DOCM = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: attach macro docm\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <c-macro-docm-4204@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1-c-docm"\r\n'
    b"\r\n"
    b"--b1-c-docm\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"One macro-bearing document.\r\n"
    b"--b1-c-docm\r\n"
    b"Content-Type: application/vnd.ms-word.document.macroEnabled.12\r\n"
    b'Content-Disposition: attachment; filename="macro.docm"\r\n'
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    b"UEsDBBQAAAAAAABAZFob8JhblQEAAJUBAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbDw/eG1sIHZl\r\n"
    b"cnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz4KPFR5cGVzIHht\r\n"
    b"bG5zPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvcGFja2FnZS8yMDA2L2NvbnRl\r\n"
    b"bnQtdHlwZXMiPjxEZWZhdWx0IEV4dGVuc2lvbj0icmVscyIgQ29udGVudFR5cGU9ImFwcGxpY2F0\r\n"
    b"aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1wYWNrYWdlLnJlbGF0aW9uc2hpcHMreG1sIi8+PERlZmF1\r\n"
    b"bHQgRXh0ZW5zaW9uPSJ4bWwiIENvbnRlbnRUeXBlPSJhcHBsaWNhdGlvbi94bWwiLz48T3ZlcnJp\r\n"
    b"ZGUgUGFydE5hbWU9Ii93b3JkL2RvY3VtZW50LnhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9u\r\n"
    b"L3ZuZC5tcy13b3JkLmRvY3VtZW50Lm1hY3JvRW5hYmxlZC5tYWluK3htbCIvPjwvVHlwZXM+ClBL\r\n"
    b"AwQUAAAAAAAAQGRaOkkbgCsBAAArAQAACwAAAF9yZWxzLy5yZWxzPD94bWwgdmVyc2lvbj0iMS4w\r\n"
    b"IiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9InllcyI/Pgo8UmVsYXRpb25zaGlwcyB4bWxu\r\n"
    b"cz0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL3BhY2thZ2UvMjAwNi9yZWxhdGlv\r\n"
    b"bnNoaXBzIj48UmVsYXRpb25zaGlwIElkPSJySWQxIiBUeXBlPSJodHRwOi8vc2NoZW1hcy5vcGVu\r\n"
    b"eG1sZm9ybWF0cy5vcmcvb2ZmaWNlRG9jdW1lbnQvMjAwNi9yZWxhdGlvbnNoaXBzL29mZmljZURv\r\n"
    b"Y3VtZW50IiBUYXJnZXQ9IndvcmQvZG9jdW1lbnQueG1sIi8+PC9SZWxhdGlvbnNoaXBzPgpQSwME\r\n"
    b"FAAAAAAAAEBkWvEZlaXSAAAA0gAAABEAAAB3b3JkL2RvY3VtZW50LnhtbDw/eG1sIHZlcnNpb249\r\n"
    b"IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz4KPHc6ZG9jdW1lbnQgeG1s\r\n"
    b"bnM6dz0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL3dvcmRwcm9jZXNzaW5nbWwv\r\n"
    b"MjAwNi9tYWluIj48dzpib2R5Pjx3OnA+PHc6cj48dzp0PmZpeHR1cmU8L3c6dD48L3c6cj48L3c6\r\n"
    b"cD48L3c6Ym9keT48L3c6ZG9jdW1lbnQ+ClBLAwQUAAAAAAAAQGRatERzRBEAAAARAAAAEwAAAHdv\r\n"
    b"cmQvdmJhUHJvamVjdC5iaW4BAgMEaW52ZW50ZWQgc3R1YlBLAQIUABQAAAAAAABAZFob8JhblQEA\r\n"
    b"AJUBAAATAAAAAAAAAAAAAAAAAAAAAABbQ29udGVudF9UeXBlc10ueG1sUEsBAhQAFAAAAAAAAEBk\r\n"
    b"WjpJG4ArAQAAKwEAAAsAAAAAAAAAAAAAAAAAxgEAAF9yZWxzLy5yZWxzUEsBAhQAFAAAAAAAAEBk\r\n"
    b"WvEZlaXSAAAA0gAAABEAAAAAAAAAAAAAAAAAGgMAAHdvcmQvZG9jdW1lbnQueG1sUEsBAhQAFAAA\r\n"
    b"AAAAAEBkWrREc0QRAAAAEQAAABMAAAAAAAAAAAAAAAAAGwQAAHdvcmQvdmJhUHJvamVjdC5iaW5Q\r\n"
    b"SwUGAAAAAAQABAD6AAAAXQQAAAAA\r\n"
    b"--b1-c-docm--\r\n"
)

CAP_ENCODED_WORD_BOMB = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: =?utf-8?b?PT91dGYtOD9iP1BUOTFkR1l0T0Q5aVAxbHRPWFJaYVVKMllYYzlQVDg5Pz0=?=\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <c-ew-bomb-4205@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"\r\n"
    b"A nested encoded word in the Subject.\r\n"
)

CAP_VERY_LONG_BASE64_RUN = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: cap very long base64 run\r\n"
    b"Date: Tue, 4 Mar 2025 08:05:00 +0000\r\n"
    b"Message-ID: <c-b64-run-4206@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    + (b"QkJC" * 1365)
    + b"Qg==\r\n"
)

FIXTURES = {
    "bad_charset": BAD_CHARSET,
    "truncated_base64": TRUNCATED_BASE64,
    "malformed_mime": MALFORMED_MIME,
    "duplicate_content_type_header": DUPLICATE_CONTENT_TYPE_HEADER,
    "leading_utf8_bom": LEADING_UTF8_BOM,
    "mbox_from_line_at_zero": MBOX_FROM_LINE_AT_ZERO,
    "lone_cr_in_header_region": LONE_CR_IN_HEADER_REGION,
    "header_line_over_998_bytes": HEADER_LINE_OVER_998_BYTES,
    "nul_in_header_value": NUL_IN_HEADER_VALUE,
    "nul_in_header_name": NUL_IN_HEADER_NAME,
    "header_8bit_raw_bytes": HEADER_8BIT_RAW_BYTES,
    "encoded_word_invalid": ENCODED_WORD_INVALID,
    "date_invalid": DATE_INVALID,
    "date_offset_out_of_range": DATE_OFFSET_OUT_OF_RANGE,
    "address_unparsable": ADDRESS_UNPARSABLE,
    # Family B: body and HTML (Turn 1.0c, commit 2)
    "base64_with_whitespace_and_bad_padding": BASE64_WHITESPACE_BAD_PADDING,
    "qp_raw_8bit": QP_RAW_8BIT,
    "iso_2022_jp_stateful": ISO_2022_JP_STATEFUL,
    "gb2312_declared_gbk_bytes": GB2312_DECLARED_GBK_BYTES,
    "windows_1252_declared_iso_8859_1": WINDOWS_1252_DECLARED_ISO_8859_1,
    "preamble_only_message": PREAMBLE_ONLY_MESSAGE,
    # Family C: attachments and caps (Turn 1.0c, commit 3)
    "attach_unrecognized_magic": ATTACH_UNRECOGNIZED_MAGIC,
    "attach_ole_cfb_magic": ATTACH_OLE_CFB_MAGIC,
    "attach_tnef_winmail": ATTACH_TNEF_WINMAIL,
    "attach_macro_docm": ATTACH_MACRO_DOCM,
    "cap_encoded_word_bomb": CAP_ENCODED_WORD_BOMB,
    "cap_very_long_base64_run": CAP_VERY_LONG_BASE64_RUN,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="write the hand-typed raw fixtures")
    parser.add_argument("--check", action="store_true", help="exit 1 unless the files on disk already match")
    args = parser.parse_args()

    failures = []
    RAW.mkdir(parents=True, exist_ok=True)
    for name, data in FIXTURES.items():
        path = RAW / f"{name}.eml"
        if args.check:
            on_disk = path.read_bytes() if path.exists() else None
            if on_disk != data:
                failures.append(name)
                print(f"DIFFERS  {path}")
            else:
                print(f"ok       {path}")
        else:
            path.write_bytes(data)
            print(f"wrote    {path}  ({len(data)} bytes)")
    if failures:
        print(f"hand-written bytes differ for: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
