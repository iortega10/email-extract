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

FIXTURES = {
    "bad_charset": BAD_CHARSET,
    "truncated_base64": TRUNCATED_BASE64,
    "malformed_mime": MALFORMED_MIME,
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
