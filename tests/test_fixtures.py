"""Turn 0.3: the fixtures' bytes are stable, frozen and interpreter-independent (D11).

Two things are checked here: regeneration is byte-identical (the generated eight and the
five conflict fixtures rebuild to exactly the bytes on disk, so their sha256 is identity)
and the raw three match their frozen digests. The interpreter-independence is proven by
running this file on both CPython 3.14 and 3.11 and comparing the digests in the turn
report -- and by the two build-dependent defects this asserts against directly: no
attachment contains a compressed zip member and the png's IDAT is stored deflate, so
nothing here can differ between zlib 1.3.1 and zlib-ng.
"""

from __future__ import annotations

import hashlib
import io
import struct
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import make_fixtures  # noqa: E402  (the generator is a tool, imported by path)
import write_raw_fixtures  # noqa: E402

GENERATED = ROOT / "fixtures" / "generated"
TIME = ROOT / "fixtures" / "time"
RAW = ROOT / "fixtures" / "raw"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("name", sorted(make_fixtures.FIXTURE_NAMES))
def test_regeneration_is_byte_identical(name: str) -> None:
    on_disk = (GENERATED / f"{name}.eml").read_bytes()
    assert make_fixtures.build_fixture(name) == on_disk, f"{name} differs from its description"
    assert _sha(on_disk) == _sha(make_fixtures.build_fixture(name))


@pytest.mark.parametrize("name", sorted(make_fixtures.TIME_FIXTURE_NAMES))
def test_the_conflict_fixtures_regenerate_byte_identically(name: str) -> None:
    on_disk = (TIME / f"{name}.eml").read_bytes()
    assert make_fixtures.build_fixture(name) == on_disk, f"{name} differs from its description"


def test_the_raw_three_match_sha256sums() -> None:
    sums = {}
    for line in (RAW / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, _, name = line.partition("  ")
        sums[name] = digest
    assert sorted(sums) == ["bad_charset.eml", "malformed_mime.eml", "truncated_base64.eml"]
    for name, digest in sums.items():
        data = (RAW / name).read_bytes()
        assert _sha(data) == digest, f"{name} no longer matches its frozen digest"
        assert write_raw_fixtures.FIXTURES[name.removesuffix(".eml")] == data


def test_every_attachment_zip_member_is_stored_never_compressed() -> None:
    """zlib-ng (3.14) and zlib 1.3.1 (3.11) DEFLATE differently; nothing may depend on it."""
    for name, blob in (("tiny.xlsx", make_fixtures.tiny_xlsx()), ("tiny.docx", make_fixtures.tiny_docx())):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            assert infos, name
            for info in infos:
                assert info.compress_type == zipfile.ZIP_STORED, f"{name}:{info.filename} is compressed"
        position = 0
        while position < len(blob) and blob[position : position + 4] != b"PK\x01\x02":
            assert blob[position : position + 4] == b"PK\x03\x04", f"{name}: no local header at {position}"
            method = struct.unpack_from("<H", blob, position + 8)[0]
            assert method == 0, f"{name}: compression method {method}"
            name_len, extra_len = struct.unpack_from("<HH", blob, position + 26)
            size = struct.unpack_from("<I", blob, position + 18)[0]
            position += 30 + name_len + extra_len + size
        assert blob[position : position + 4] == b"PK\x01\x02", f"{name}: central directory not reached"


def test_the_png_uses_stored_deflate_blocks_never_a_compressed_one() -> None:
    png = make_fixtures.tiny_png(b"\x10\x20\x30")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    position = 8
    idat = b""
    while position < len(png):
        length = struct.unpack_from(">I", png, position)[0]
        kind = png[position + 4 : position + 8]
        if kind == b"IDAT":
            idat += png[position + 8 : position + 8 + length]
        position += 12 + length
    assert idat.startswith(b"\x78\x01"), "the zlib stream must be the uncompressed preset"
    blocks = idat[2:-4]
    offset = 0
    seen = 0
    while True:
        header = blocks[offset]
        assert (header >> 1) & 0x03 == 0, "a non-stored deflate block: bytes would depend on the zlib build"
        assert header & 0x01 in (0, 1)
        length = struct.unpack_from("<H", blocks, offset + 1)[0]
        inverse = struct.unpack_from("<H", blocks, offset + 3)[0]
        assert length ^ 0xFFFF == inverse
        offset += 5 + length
        seen += 1
        if header & 0x01:
            break
    assert seen >= 1 and offset == len(blocks)


def test_the_pdf_has_no_compressed_stream() -> None:
    pdf = make_fixtures.tiny_pdf("tiny fixture")
    assert b"/Filter" not in pdf, "a compressed stream would make the bytes build-dependent"
    assert pdf.startswith(b"%PDF-1.4") and pdf.endswith(b"%%EOF\n")
