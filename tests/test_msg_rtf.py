"""Turn 1b.8: the ``0x1009`` (compressed RTF) decompress-and-record minimum.

Owner decision **O2** kept the decompress-and-record minimum and cut de-encapsulation:
:mod:`emailextract.rtf` decompresses a ``0x1009`` stream (``LZFu``/``MELA``), checks it and
records it, but **no body view derives from RTF**. These tests hold the decoder against the
**independent** side -- the test-side compressor of ``tests/support/rtf_compress.py``, hand
typed byte-by-byte vectors, the ``.eml`` path -- and never against itself.

The six declared tests are:

* ``test_lzfu_decompresses_and_checks_the_header_size_and_crc``;
* ``test_mela_uncompressed_is_accepted``;
* ``test_a_bad_crc_is_a_truncated_stream``;
* ``test_the_rtf_stream_is_recorded_with_no_body_view``;
* ``test_rtf_to_text_unsupported_is_emitted``;
* ``test_no_rtf_encapsulation_refused_id_exists``;

plus the extras the brief names: the constant cross-check, hand-typed vectors, round trips,
each fault, the hostile header, maximal expansion, the zero/short streams, plain-data
determinism, the no-body-view proof, a seeded fuzz and the memory bound -- and the Turn 1b.8
**fix** block: the 207-byte prebuf, the raw-table CRC (not ``zlib``), and the two **real**
``0x1009`` vectors asserted against :func:`emailextract.rtf.decode` alone.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
import tracemalloc
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import make_msg_fixtures  # noqa: E402  (the fixture generator, imported by path)

from emailextract import cfb, rtf  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.model import Selection  # noqa: E402
from emailextract.msgcontainer import GAP_RTF_TO_TEXT_UNSUPPORTED, GAP_STREAM_TRUNCATED, MsgContainer  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from emailextract.walk import walk  # noqa: E402

from support import rtf_compress  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()
RTF_STREAM = "__substg1.0_10090102"

#: The two **real** ``0x1009`` streams, hand-typed with provenance: from the README of
#: ``delimitry/compressed_rtf`` (public), also a worked example of the format; checked
#: 2026-10-14. They are asserted against :func:`emailextract.rtf.decode` **alone** -- no
#: encoder is involved -- so they pin the two constants (the prebuf and the CRC) that the
#: first Turn 1b.8 got wrong, which a compressor/decoder round trip could never catch.
#:
#: LZFu: header ``COMPSIZE`` 35, ``RAWSIZE`` 34, ``LZFu``, stored CRC ``0x74E85C33``.
REAL_LZFU_STREAM = (
    b'#\x00\x00\x00"\x00\x00\x00LZFu3\\\xe8t\x03\x00\n\x00rcpg125\x922\n\xf3 t\x07\x90t}\x0f\x10'
)
#: MELA: header ``COMPSIZE`` 46, ``RAWSIZE`` 34, ``MELA``, stored CRC ``0xCE12DF20``.
REAL_MELA_STREAM = (
    b'.\x00\x00\x00"\x00\x00\x00MELA \xdf\x12\xce{\\rtf1\\ansi\\ansicpg1252\\pard test}'
)
#: What both real streams decompress to (34 bytes).
REAL_DECOMPRESSED = b"{\\rtf1\\ansi\\ansicpg1252\\pard test}"

#: D6: the sha256 of every existing committed fixture's virtual bytes, pinned before this
#: turn's change and asserted unchanged after it (the RTF fixtures are the only new rows).
EXISTING_VIRTUAL_SHA256 = {
    "msg_headers_only": "232ffea0c8f40632c5eca6cae6c3a255d56e5aa479595136881c5f3ffd848ee2",
    "msg_headers_html": "d51b6baa676b37e573c6d1a8174fb1db2d61152d637f939b1e4e40c8ebdaacc0",
    "msg_v4_sectors": "d51b6baa676b37e573c6d1a8174fb1db2d61152d637f939b1e4e40c8ebdaacc0",
    "msg_mini_cutoff_boundary": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "msg_outlook_layout_handbuilt": "d1a6d84c79f37fe6e6c8b1b52a1a8a8af5d311f9e41428b2b95530a78a3ae827",
    "msg_difat_extended": "d51b6baa676b37e573c6d1a8174fb1db2d61152d637f939b1e4e40c8ebdaacc0",
    "msg_fat_cycle": "d6c571f95fbd27c4b448a3b543bca58888a480d7704c655956d1f2c2ad3019fa",
    "msg_directory_loop": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "msg_truncated_stream": "d6c571f95fbd27c4b448a3b543bca58888a480d7704c655956d1f2c2ad3019fa",
    "msg_non_ipm_note": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "msg_signed_class": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "msg_unknown_tags": "dd7c319d99a334a1f03a55762f0439bf0659a2a3a7c360ffc9a45862528b6209",
    "msg_named_properties": "dd7c319d99a334a1f03a55762f0439bf0659a2a3a7c360ffc9a45862528b6209",
    "msg_codepage_disagree": "dd7c319d99a334a1f03a55762f0439bf0659a2a3a7c360ffc9a45862528b6209",
    "msg_html_only_no_plain": "b304c32108ca51e15879052e39ad9994f1dc5a50ccc6a81f410d9ab3e1b68e63",
    "msg_plain_only": "e459119cb0c3274ed286af8994f7e1f54e593fdeab0dafa9e6787f3ccea38173",
    "msg_plain_and_html": "61d37abefbd357288848ed260b8cd603c06e6093efbee33b12ecd4546a6490d8",
    "msg_zero_length_body": "44952f8f996b24ee74dd48b837520fcb2c216241c90a6afb76f9bfc97a0e4c1d",
    "msg_html_meta_charset_contradicts": "c12b9ce39d0fb3a31d676e6428ef86f9ae32441c1ee7ca5a04a4fdd3058fc00c",
    "msg_no_transport_headers": "25921d868de8efeb1317ec6e1222505b7814cd110025d22755f4b289acc04177",
    "msg_transport_headers_utf8_bom": "a4b331bac0c2649db13d2af22f7fad8c63d5d485db31305d412dafec36994560",
    "msg_transport_headers_lf_only": "82638c1e425f463539bbb583ea9f1f7a9a7869b196864b57b910a20fcf3d4b6a",
    "msg_property_vs_header_conflict": "b304c32108ca51e15879052e39ad9994f1dc5a50ccc6a81f410d9ab3e1b68e63",
    "msg_recipients_display_only": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_recipients_ex_no_smtp": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_recipients_bcc_duplicates": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_time_property_vs_date_header": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_unicode_subject": "4c81fdd3b92478f19824f9944f1d12c0e8c1b1c6f474dce6dc54d3d399c6df22",
    "msg_embedded_message": "84a3280b0838126638052ada3197c47a6614152a6fdd4a1b0e510ac14ca35cc1",
    "msg_embedded_depth_two": "ed688a378f92187ae8d0051a7a1a5f2734367324f47b714ef21dbb042e5df0db",
    "msg_attachment_with_cid": "d6cbe6d7f594604e87c754d523235d5c16e116950feb120ac15c3f8128e74c5b",
    "msg_attachment_hidden": "b4dbf599efda542dfd636ce71016633c9f9f22fcd0af74f83f8813a146c5fe1b",
    "msg_attachment_ole": "ed5d45c2977f52505fb304e54145de9325fd3f545a4a3839f456ebf975b57f34",
    "msg_attachment_by_reference": "580b796e0a9c366109c3615462b5181bdc5e14af1de859b49b07b6a01387d51e",
    "msg_attachment_hostile_name": "f3e94052a75bff243423b4e68527aeb7a73c4c796d624d1cea37d38e5e59e9c5",
    "msg_attachment_zero_size": "06a0a6a7d624c1fc4d40c072efbac37b1af2d3e6d811baf01bf4b132697b9b46",
    "msg_attachments_4095_4096_4097": "d7926985973048c6ec18dd8b683b420450537cb0c6736932cb7f205f9ae60f9c",
    "msg_duplicate_filenames": "49c7a0e996ac95ea9f0f5b242c206f9384afc4aa5b94069d9b7119353b528e18",
}


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str) -> MsgContainer:
    return MsgContainer(_bytes(name))


def _stream_bytes(name: str) -> bytes:
    opened = cfb.open_cfb(_bytes(name))
    assert isinstance(opened, cfb.CfbFile)
    payload, status = cfb.read_stream(opened, RTF_STREAM)
    assert status == cfb.FAULT_OK
    return payload


def _gaps(container: MsgContainer) -> "list[tuple[str, str]]":
    return [(gap.gap_id, gap.detail) for gap in container.container_gaps]


def _lzfu_header(payload: bytes, rawsize: int, compsize: "int | None" = None) -> bytes:
    """A valid ``LZFu`` header over ``payload`` (``compsize`` counts from after its field)."""
    return struct.pack(
        "<IIII",
        12 + len(payload) if compsize is None else compsize,
        rawsize,
        rtf.CN_COMPRESSED,
        rtf.crc32(payload),
    ) + payload


# --------------------------------------------------------------- the declared tests


def test_lzfu_decompresses_and_checks_the_header_size_and_crc() -> None:
    """The committed ``LZFu`` stream decompresses to the typed text; a size or CRC lie faults."""
    facts = _container("msg_rtf_compressed_body").rtf_facts
    assert facts is not None
    assert facts.comptype == "LZFu"
    assert facts.stream_length == 226
    assert facts.compsize_declared == 222  # stream_length - 4
    assert facts.rawsize_declared == len(make_msg_fixtures.RTF_BODY_TEXT.encode("utf-8"))
    assert facts.crc_ok is True
    assert facts.crc_kind == "payload"
    assert facts.fault is None
    assert facts.decompressed_length == len(make_msg_fixtures.RTF_BODY_TEXT.encode("utf-8"))
    assert facts.decompressed_sha256 == hashlib.sha256(
        make_msg_fixtures.RTF_BODY_TEXT.encode("utf-8")
    ).hexdigest()
    # A COMPSIZE that disagrees with the stream length is the header-size fault.
    stream = _stream_bytes("msg_rtf_only")
    wrong_size = struct.pack("<I", struct.unpack_from("<I", stream, 0)[0] + 1) + stream[4:]
    assert rtf.decode(wrong_size).fault == rtf.FAULT_COMPSIZE_MISMATCH
    # A CRC over other bytes (here the whole header as well) is the CRC fault.
    wrong_crc = stream[:12] + (
        struct.unpack_from("<I", stream, 12)[0] ^ 0xFFFFFFFF
    ).to_bytes(4, "little") + stream[16:]
    assert rtf.decode(wrong_crc).fault == rtf.FAULT_CRC_MISMATCH


def test_mela_uncompressed_is_accepted() -> None:
    """A ``MELA`` stream is accepted when its CRC is ``0`` or the payload's raw CRC."""
    text = b"{\\rtf1\\ansi synthetic mela body}"
    message = make_msg_fixtures.rtf_message(rtf_compress.mela(text))
    facts = MsgContainer(message).rtf_facts
    assert facts is not None
    assert (facts.comptype, facts.fault, facts.crc_ok) == ("MELA", None, True)
    assert facts.crc_kind == "zero"  # the uncompressed writer's own CRC field is 0
    assert facts.decompressed_length == len(text)
    assert facts.decompressed_sha256 == hashlib.sha256(text).hexdigest()
    # The reference writer stores the *payload's* raw-table CRC instead of 0; that form is
    # accepted too, and which one it was is recorded (owner question, Turn 1b.8 fix).
    stored = bytearray(rtf_compress.mela(text))
    struct.pack_into("<I", stored, 12, rtf.crc32(text))
    accepted = rtf.decode(bytes(stored))
    assert (accepted.fault, accepted.crc_ok, accepted.crc_kind) == (None, True, "payload")
    assert accepted.decompressed_sha256 == hashlib.sha256(text).hexdigest()
    # Any *other* value (neither 0 nor the payload's CRC) is the CRC fault.
    bad = bytearray(rtf_compress.mela(text))
    struct.pack_into("<I", bad, 12, 0x1234)
    assert rtf.decode(bytes(bad)).fault == rtf.FAULT_CRC_MISMATCH
    # A data length that disagrees with RAWSIZE is the size fault.
    short = bytearray(rtf_compress.mela(text))
    struct.pack_into("<I", short, 4, len(text) + 1)
    assert rtf.decode(bytes(short)).fault == rtf.FAULT_RAWSIZE_MISMATCH


def test_a_bad_crc_is_a_truncated_stream() -> None:
    """``msg_rtf_bad_crc`` is TRUNCATED/stream_ended_early with the ``0x1009`` stream gap."""
    container = _container("msg_rtf_bad_crc")
    facts = container.rtf_facts
    assert facts is not None
    assert facts.fault == rtf.FAULT_CRC_MISMATCH
    assert facts.crc_ok is False
    assert facts.decompressed_sha256 is None
    assert (GAP_STREAM_TRUNCATED, f"{RTF_STREAM}:rtf_crc_mismatch") in _gaps(container)
    document = assemble(container, limits=LIMITS)
    assert (document.status.status.value, document.status.reason) == (
        "truncated",
        "stream_ended_early",
    )


def test_the_rtf_stream_is_recorded_with_no_body_view() -> None:
    """The record lives on ``rtf_facts``; no view, part or selection derives from the RTF."""
    only = _container("msg_rtf_only")
    facts = only.rtf_facts
    assert facts is not None and facts.fault is None
    assert only.container_facts()["body_streams"] == "rtf"
    # The record is the decoder's result, plain data (D3/D7), and nothing consumes it yet.
    assert isinstance(facts, rtf.RtfResult)
    document = assemble(only, limits=LIMITS)
    assert not any(
        getattr(record, "body_view", None) is not None for record in document.parts
    )
    assert all(record.selection is Selection.NOT_APPLICABLE for record in document.parts)
    # The decompressed text never enters the virtual bytes.
    assert b"fromtext" not in only.raw_bytes()
    assert b"synthetic turn 1b.8 rtf body" not in only.raw_bytes()
    # A plain body beside an RTF stream is projected exactly as in 1b.5, and the record is
    # the only addition.
    both = _container("msg_rtf_compressed_body")
    assert both.container_facts()["body_streams"] == "plain+rtf"
    assert both.rtf_facts is not None and both.rtf_facts.fault is None


def test_rtf_to_text_unsupported_is_emitted() -> None:
    """A present ``0x1009`` stream always raises the registered gap, faulted or not."""
    for name in ("msg_rtf_compressed_body", "msg_rtf_only", "msg_rtf_bad_crc"):
        container = _container(name)
        assert GAP_RTF_TO_TEXT_UNSUPPORTED in {gap_id for gap_id, _detail in _gaps(container)}, name
    # A message with no `0x1009` stream never raises it.
    clean = _container("msg_plain_and_html")
    assert GAP_RTF_TO_TEXT_UNSUPPORTED not in {gap_id for gap_id, _detail in _gaps(clean)}
    # Even a damaged stream (a decoder fault) beside the truncation gap still emits it.
    faulted = MsgContainer(make_msg_fixtures.rtf_message(b"\x00" * 4))
    ids = [gap_id for gap_id, _detail in _gaps(faulted)]
    assert GAP_RTF_TO_TEXT_UNSUPPORTED in ids and GAP_STREAM_TRUNCATED in ids


def test_no_rtf_encapsulation_refused_id_exists() -> None:
    """O2: ``msg.rtf_encapsulation_refused`` is not created (the absence is the assertion)."""
    for module in (rtf, sys.modules[MsgContainer.__module__]):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "rtf_encapsulation_refused" not in source, module.__name__
    for name in ("msg_rtf_compressed_body", "msg_rtf_only", "msg_rtf_bad_crc"):
        assert "msg.rtf_encapsulation_refused" not in {
            gap_id for gap_id, _detail in _gaps(_container(name))
        }
    assert not any("encapsulation" in fault for fault in rtf.FAULTS)


# --------------------------------------------------------------- the extras


def test_the_decoder_and_compressor_agree_on_the_constants() -> None:
    """The compressor takes the constants from the decoder, and the CRC is the raw table CRC.

    The compressor now *imports* :data:`PREBUF`, the CRC and the header values from
    :mod:`emailextract.rtf` (one place), so this asserts identity rather than equality -- and
    it pins that the CRC is the raw-table form, **not** :func:`zlib.crc32` (the two disagree
    on every non-empty sample, so a regression to ``zlib`` fails here).
    """
    assert rtf_compress.PREBUF is rtf.PREBUF
    assert rtf_compress.INITIAL_WRITE_POSITION == rtf.INITIAL_WRITE_POSITION
    assert rtf_compress.DICTIONARY_SIZE == rtf.DICTIONARY_SIZE
    assert rtf_compress.LZFU == rtf.CN_COMPRESSED
    assert rtf_compress.MELA == rtf.CN_UNCOMPRESSED
    assert rtf_compress.crc32 is rtf.crc32
    samples = [b"a", b"hello world", bytes(range(256)), b"{\\rtf1\\ansi}"]
    for sample in samples:
        assert rtf_compress.crc32(sample) == rtf.crc32(sample)
        assert rtf.crc32(sample) != zlib.crc32(sample) & 0xFFFFFFFF
    # The empty input is the one coincidence (both definitions give 0).
    assert rtf.crc32(b"") == 0 and zlib.crc32(b"") == 0


def test_hand_typed_vectors_decode_byte_for_byte() -> None:
    """Byte-by-byte vectors whose expected bytes are derived by hand in each comment.

    Every offset below is derived from the corrected ``INITIAL_WRITE_POSITION`` = **207**
    (``len(PREBUF)``), so the literals are typed from the numbers and, if the code disagrees,
    the disagreement is a finding, not a value to patch.
    """
    assert rtf.INITIAL_WRITE_POSITION == 207  # the derivation below assumes this

    # 1. literals only: "AB". flags 0b00000100 = literal, literal, end marker. The write
    #    position is 207 + 2 = 209 (0xD1), so the marker reference is (209 << 4) = 0x0D10.
    payload = bytes([0b00000100, 0x41, 0x42]) + b"\x0d\x10"
    result = rtf.decode(_lzfu_header(payload, 2))
    assert result.fault is None and result.decompressed_length == 2
    assert result.decompressed_sha256 == hashlib.sha256(b"AB").hexdigest()

    # 2. one reference, no overlap: "ABAB". literal 'A', literal 'B', then a reference to the
    #    two written bytes at offset 207 (0xCF) with stored length 0 (length 2), then the
    #    marker at write position 207 + 4 = 211: reference = (207 << 4) | 0 = 0x0CF0,
    #    marker = (211 << 4) = 0x0D30.
    payload = bytes([0b00001100, 0x41, 0x42]) + b"\x0c\xf0" + b"\x0d\x30"
    result = rtf.decode(_lzfu_header(payload, 4))
    assert result.fault is None
    assert result.decompressed_sha256 == hashlib.sha256(b"ABAB").hexdigest()

    # 3. an overlapping reference (run-length): "AAAAA". literal 'A' (write position 208),
    #    then a reference to offset 207 (0xCF) with stored length 2 (length 4), which reads
    #    the byte it is itself writing (offset + length > the write position):
    #    reference = (207 << 4) | 2 = 0x0CF2, marker at 212 = (212 << 4) = 0x0D40.
    payload = bytes([0b00000110, 0x41]) + b"\x0c\xf2" + b"\x0d\x40"
    result = rtf.decode(_lzfu_header(payload, 5))
    assert result.fault is None
    assert result.decompressed_sha256 == hashlib.sha256(b"AAAAA").hexdigest()

    # 4. end-marker position: offset == the write position ends the stream (vectors 1-3); an
    #    offset one short (207 + 1 = 208, marker = (208 << 4) = 0x0D00) is an ordinary
    #    reference to a written byte, so the stream does not end there and the running length
    #    overshoots RAWSIZE.
    bad_marker = bytes([0b00000100, 0x41, 0x42]) + b"\x0d\x00"
    assert rtf.decode(_lzfu_header(bad_marker, 2)).fault == rtf.FAULT_RAWSIZE_MISMATCH


# ---------------------------------------------------------- the Turn 1b.8 fix vectors


def test_the_prebuf_is_the_207_byte_text_of_the_specification() -> None:
    """``PREBUF`` is the specification's 207 bytes: its length, both ends, and its sha256."""
    assert len(rtf.PREBUF) == 207
    assert rtf.INITIAL_WRITE_POSITION == 207
    # The first 40 bytes (the {\rtf1\ansi\mac... prelude) and the last 20 (typed by hand).
    assert rtf.PREBUF[:40] == b"{\\rtf1\\ansi\\mac\\deff0\\deftab720{\\fonttbl"
    assert rtf.PREBUF[-20:] == b"f0\\fs20\\b\\i\\u\\tab\\tx"
    # The <CR><LF> is a real pair, not an escape.
    assert rtf.PREBUF.count(b"\r\n") == 1
    # The sha256 of the whole constant, typed in the test against the reference's INIT_DICT.
    assert hashlib.sha256(rtf.PREBUF).hexdigest() == (
        "64949fe166f29da3ab21d1739247557565795c7cfed9227f377e890ce5cfa92d"
    )


def test_the_crc_is_the_raw_table_crc_not_zlib() -> None:
    """The real vector's stored CRC is the raw table CRC, and it is **not** :func:`zlib.crc32`."""
    stored = struct.unpack_from("<I", REAL_LZFU_STREAM, 12)[0]
    assert stored == 0x74E85C33
    assert rtf.crc32(REAL_LZFU_STREAM[16:]) == stored
    assert rtf.crc32(REAL_LZFU_STREAM[16:]) != zlib.crc32(REAL_LZFU_STREAM[16:]) & 0xFFFFFFFF
    # A hand-typed check value for a **different** input, so the agreement above is not a
    # coincidence of one payload (init 0, no final XOR -- reflected ``0xEDB88320``).
    assert rtf.crc32(b"123456789") == 0x2DFD2D88
    assert zlib.crc32(b"123456789") & 0xFFFFFFFF == 0xCBF43926  # the init/XOR form differs


def test_a_real_lzfu_vector_decodes_exactly() -> None:
    """The real 39-byte ``LZFu`` stream decodes to its 34 bytes -- through ``decode`` alone."""
    assert len(REAL_LZFU_STREAM) == 39
    result = rtf.decode(REAL_LZFU_STREAM)  # no encoder is involved anywhere here
    assert result.comptype == "LZFu"
    assert (result.compsize_declared, result.rawsize_declared) == (35, 34)
    assert result.crc_declared == 0x74E85C33
    assert (result.crc_ok, result.crc_kind, result.fault) == (True, "payload", None)
    assert result.decompressed_length == 34
    assert result.decompressed_sha256 == hashlib.sha256(REAL_DECOMPRESSED).hexdigest()
    # Through a built .msg: PARSED, no truncation, the RTF gap, and the recorded 34 bytes.
    container = MsgContainer(make_msg_fixtures.rtf_message(REAL_LZFU_STREAM))
    assert container.rtf_facts == result
    assert container.container_facts()["body_streams"] == "rtf"
    gaps = _gaps(container)
    assert GAP_RTF_TO_TEXT_UNSUPPORTED in {gap_id for gap_id, _detail in gaps}
    assert not any(gap_id == GAP_STREAM_TRUNCATED for gap_id, _detail in gaps)
    document = assemble(container, limits=LIMITS)
    assert document.status.status.value == "parsed"
    assert document.status.reason is None


def test_a_real_mela_vector_is_accepted() -> None:
    """The real 50-byte ``MELA`` stream is accepted: its CRC is the payload's raw CRC."""
    assert len(REAL_MELA_STREAM) == 50
    result = rtf.decode(REAL_MELA_STREAM)  # decode alone
    assert result.comptype == "MELA"
    assert (result.compsize_declared, result.rawsize_declared) == (46, 34)
    assert result.crc_declared == 0xCE12DF20
    assert result.crc_declared == rtf.crc32(REAL_MELA_STREAM[16:])  # the "payload" form
    assert (result.crc_ok, result.crc_kind, result.fault) == (True, "payload", None)
    assert result.decompressed_length == 34
    assert result.decompressed_sha256 == hashlib.sha256(REAL_DECOMPRESSED).hexdigest()
    # Through a built .msg: PARSED, no truncation, the RTF gap, and the recorded 34 bytes.
    container = MsgContainer(make_msg_fixtures.rtf_message(REAL_MELA_STREAM))
    assert container.rtf_facts == result
    gaps = _gaps(container)
    assert GAP_RTF_TO_TEXT_UNSUPPORTED in {gap_id for gap_id, _detail in gaps}
    assert not any(gap_id == GAP_STREAM_TRUNCATED for gap_id, _detail in gaps)
    document = assemble(container, limits=LIMITS)
    assert document.status.status.value == "parsed"
    assert document.status.reason is None


def test_a_round_trip_through_both_encoders() -> None:
    """``decode(encode(x))`` preserves x's sha256 and length, for both encoders."""
    rng = random.Random(20261014)
    cases = [
        b"",
        b"Z",
        b"run:" + b"Q" * 40,
        (b"turn 1b.8 dictionary wrap " * 400),  # longer than the 4096-byte window
        bytes(rng.randrange(256) for _ in range(3000)),
    ]
    for encoder in (rtf_compress.compress_literal, rtf_compress.compress_greedy):
        for case in cases:
            result = rtf.decode(encoder(case))
            assert result.fault is None, (encoder.__name__, len(case), result)
            assert result.decompressed_length == len(case)
            assert result.decompressed_sha256 == hashlib.sha256(case).hexdigest()


def test_each_fault_is_named_with_its_reason_and_gap() -> None:
    """Every D5 fault is recorded, raises ``0x1009:<fault>`` and maps to its reason."""
    good = _stream_bytes("msg_rtf_only")
    text = make_msg_fixtures.RTF_BODY_TEXT.encode("utf-8")
    cases = {
        rtf.FAULT_HEADER_SHORT: b"\x00" * 15,
        rtf.FAULT_COMPTYPE_UNKNOWN: good[:8] + struct.pack("<I", 0xDEADBEEF) + good[12:],
        rtf.FAULT_COMPSIZE_MISMATCH: struct.pack("<I", 999999) + good[4:],
        rtf.FAULT_RAWSIZE_MISMATCH: good[:4] + struct.pack("<I", len(text) + 1) + good[8:],
        rtf.FAULT_CRC_MISMATCH: good[:12] + struct.pack("<I", 0) + good[16:],
        rtf.FAULT_DATA_SHORT: _lzfu_header(bytes([0x00]) + b"abc", 8),
        rtf.FAULT_DICTIONARY_UNDERRUN: _lzfu_header(
            bytes([0b00000001]) + (((rtf.INITIAL_WRITE_POSITION + 500) << 4) | 0).to_bytes(2, "big"),
            10,
        ),
    }
    reasons = {
        rtf.FAULT_HEADER_SHORT: "declared_length_mismatch",
        rtf.FAULT_COMPTYPE_UNKNOWN: "declared_length_mismatch",
        rtf.FAULT_COMPSIZE_MISMATCH: "declared_length_mismatch",
        rtf.FAULT_RAWSIZE_MISMATCH: "declared_length_mismatch",
        rtf.FAULT_CRC_MISMATCH: "stream_ended_early",
        rtf.FAULT_DATA_SHORT: "stream_ended_early",
        rtf.FAULT_DICTIONARY_UNDERRUN: "stream_ended_early",
    }
    for fault, stream in cases.items():
        assert rtf.decode(stream).fault == fault, fault
        container = MsgContainer(make_msg_fixtures.rtf_message(stream))
        assert (GAP_STREAM_TRUNCATED, f"{RTF_STREAM}:{fault}") in _gaps(container), fault
        assert GAP_RTF_TO_TEXT_UNSUPPORTED in {gap_id for gap_id, _detail in _gaps(container)}
        document = assemble(container, limits=LIMITS)
        assert (document.status.status.value, document.status.reason) == (
            "truncated",
            reasons[fault],
        ), fault


def test_a_hostile_header_is_bounded_and_quick() -> None:
    """A hostile ``RAWSIZE``/``COMPSIZE`` faults quickly without a declared-size allocation."""
    good = _stream_bytes("msg_rtf_only")
    huge_raw = good[:4] + struct.pack("<I", 0xFFFFFFFF) + good[8:]
    huge_comp = struct.pack("<I", 0xFFFFFF) + good[4:]
    for stream, expected in (
        (huge_raw, rtf.FAULT_RAWSIZE_MISMATCH),
        (huge_comp, rtf.FAULT_COMPSIZE_MISMATCH),
    ):
        tracemalloc.start()
        try:
            result = rtf.decode(stream)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert result.fault == expected
        assert peak < 1 << 20, (expected, peak)  # never the declared RAWSIZE


def test_the_maximal_expansion_stays_within_the_work_bound() -> None:
    """The worst case (all references) stays under ~9x and inside the declared work bound."""
    blocks = 8  # 8 control bytes, 8 references each, 17 output bytes per reference.
    reference = ((100 << 4) | (17 - 2)).to_bytes(2, "big")
    payload = (bytes([0xFF]) + reference * 8) * blocks
    rawsize = 8 * 17 * blocks
    payload += bytes([0b00000001]) + (
        ((rtf.INITIAL_WRITE_POSITION + rawsize) % 4096) << 4
    ).to_bytes(2, "big")
    stream = _lzfu_header(payload, rawsize)
    work = cfb.Work()
    result = rtf.decode(stream, work=work)
    assert result.fault is None
    assert result.decompressed_length == rawsize
    assert result.decompressed_length <= rtf.MAX_EXPANSION * len(stream)
    assert work.steps == result.decompressed_length
    assert work.steps <= rtf.work_bound(len(stream))


def test_zero_and_short_rtf_streams() -> None:
    """0/1/15 bytes are ``rtf_header_short``; a header-only ``LZFu`` is ``rtf_data_short``."""
    for length in (0, 1, 15):
        stream = b"\x00" * length
        assert rtf.decode(stream).fault == rtf.FAULT_HEADER_SHORT
    header_only = _lzfu_header(b"", 0)
    assert len(header_only) == 16
    assert rtf.decode(header_only).fault == rtf.FAULT_DATA_SHORT
    for stream in (b"", b"\x00", b"\x00" * 15, header_only):
        container = MsgContainer(make_msg_fixtures.rtf_message(stream))
        assert container.container_facts()["body_streams"] == "rtf"
        assert GAP_RTF_TO_TEXT_UNSUPPORTED in {gap_id for gap_id, _detail in _gaps(container)}
        assert container.rtf_facts is not None and container.rtf_facts.fault is not None


def test_rtf_facts_is_plain_data_and_hash_seed_independent() -> None:
    """``rtf_facts`` is a frozen record of primitives, carries no RTF text, and is stable."""
    container = _container("msg_rtf_only")
    facts = container.rtf_facts
    assert facts is not None
    assert dataclasses.is_dataclass(facts)
    for field in dataclasses.fields(facts):
        assert field.type is not None
    for value in dataclasses.astuple(facts):
        assert value is None or isinstance(value, (str, int, bool))
    # No substring of the decompressed text reaches a published record.
    for value in container.container_facts().values():
        assert "synthetic turn 1b.8 rtf body" not in value
        assert "fromtext" not in value
    document = assemble(container, limits=LIMITS)
    assert "synthetic turn 1b.8 rtf body" not in json.dumps(
        [record.part_id for record in document.parts]
    )
    # Determinism under two hash seeds.
    script = (
        "import dataclasses, json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "from emailextract.msgcontainer import MsgContainer\n"
        "msg = Path(sys.argv[1]) / 'fixtures' / 'msg'\n"
        "out = {}\n"
        "for name in ('msg_rtf_compressed_body', 'msg_rtf_only', 'msg_rtf_bad_crc'):\n"
        "    c = MsgContainer((msg / (name + '.msg')).read_bytes())\n"
        "    out[name] = [dataclasses.astuple(c.rtf_facts),\n"
        "                 [[g.gap_id, g.detail] for g in c.container_gaps]]\n"
        "print(json.dumps(out, sort_keys=True))\n"
    )
    baseline = None
    for seed in ("0", "987654"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        if baseline is None:
            baseline = payload
        else:
            assert payload == baseline, seed


def test_no_body_view_derives_from_rtf() -> None:
    """The RTF content never appears in a part, a body view or the virtual bytes."""
    for name in ("msg_rtf_only", "msg_rtf_compressed_body"):
        container = _container(name)
        assert b"fromtext" not in container.raw_bytes()
        document = assemble(container, limits=LIMITS)
        for record in document.parts:
            assert record.stream_ref is None or record.stream_ref.stream != RTF_STREAM, name
        assert not any(
            getattr(record, "body_view", None) is not None for record in document.parts
        ), name
        for part in walk(container, limits=LIMITS).parts:
            assert part.content_type != "application/rtf", name


def test_a_seeded_fuzz_of_the_rtf_stream_closes() -> None:
    """Mutants of the RTF header, data and the two committed fixtures always close."""
    rng = random.Random(20261014)
    bases = [_stream_bytes("msg_rtf_compressed_body"), _stream_bytes("msg_rtf_only")]
    produced = 0
    mutants = 0
    for base in bases:
        # The clean base is the control: it must decode (so the fuzz reached the decoder).
        clean = MsgContainer(make_msg_fixtures.rtf_message(base))
        assert clean.rtf_facts is not None and clean.rtf_facts.fault is None
        produced += 1
        for _ in range(85):
            mutant = bytearray(base)
            for _ in range(rng.randrange(1, 4)):
                mutant[rng.randrange(len(mutant))] = rng.randrange(256)
            mutant = bytes(mutant)
            mutants += 1
            container = MsgContainer(make_msg_fixtures.rtf_message(mutant))
            document = assemble(container, limits=LIMITS)
            assert document.container_kind.value == "cfb_msg"
            for value in container.container_facts().values():
                value.encode("utf-8")
            if container.rtf_facts is not None and container.rtf_facts.fault is None:
                produced += 1
    assert mutants >= 150
    assert produced > 0, "no stream decoded cleanly"


def _literal_stream(blocks: int) -> "tuple[bytes, int]":
    """A valid literal-only ``LZFu`` stream of ``8 * blocks`` decompressed bytes, and its length."""
    rawsize = 8 * blocks
    payload = b"\x00" * (9 * blocks)
    payload += bytes([0b00000001]) + (
        ((rtf.INITIAL_WRITE_POSITION + rawsize) % 4096) << 4
    ).to_bytes(2, "big")
    return _lzfu_header(payload, rawsize), rawsize


def test_the_rtf_decode_memory_is_bounded() -> None:
    """The decoder retains no output, and reading a 40 MiB stream once dominates the pipeline."""
    # The decoder's own peak is scale-invariant (it keeps a hash buffer and the 4096-byte
    # dictionary, never the output), so an 8 MiB stream measures it cheaply.
    small, small_rawsize = _literal_stream((8 * 1024 * 1024) // 8)
    tracemalloc.start()
    try:
        result = rtf.decode(small)
        _current, decode_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.fault is None and result.decompressed_length == small_rawsize
    assert decode_peak < len(small) // 8, decode_peak

    # Through the whole pipeline, on the brief's 40 MiB stream. Version 4 sectors keep the
    # FAT inside the header's inline DIFAT (the writer emits no extended chain).
    from cfb_writer import build_cfb, storage, stream  # the deterministic CFB writer

    stream_bytes, rawsize = _literal_stream((40 * 1024 * 1024) // 8)
    assert len(stream_bytes) >= 40 * 1024 * 1024
    message = build_cfb(
        storage(
            "Root Entry",
            stream(
                "__properties_version1.0",
                make_msg_fixtures._property_stream(
                    [make_msg_fixtures._class_entry(make_msg_fixtures.CLASS_IPM_NOTE)]
                ),
            ),
            stream(
                make_msg_fixtures._class_stream_name(),
                make_msg_fixtures._class_bytes(make_msg_fixtures.CLASS_IPM_NOTE),
            ),
            stream(RTF_STREAM, stream_bytes),
        ),
        version=4,
    )
    tracemalloc.start()
    try:
        container = MsgContainer(message)
        document = assemble(container, limits=LIMITS)
        parts = walk(container, limits=LIMITS).parts
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert document.container_kind.value == "cfb_msg"
    assert container.rtf_facts is not None and container.rtf_facts.fault is None
    assert container.rtf_facts.decompressed_length == rawsize
    assert container.container_facts()["body_streams"] == "rtf"
    assert parts
    # Reading the stream once dominates; the decoder adds no output copy (report the multiple).
    assert peak < 4 * len(stream_bytes), (peak, len(stream_bytes))


def test_the_existing_fixtures_projection_is_unchanged() -> None:
    """D6: this turn moves no existing fixture's virtual bytes (only the three RTF rows)."""
    for name, digest in EXISTING_VIRTUAL_SHA256.items():
        got = hashlib.sha256(_container(name).raw_bytes()).hexdigest()
        assert got == digest, name
    # ... and the new rows are exactly the three RTF fixtures.
    for name in ("msg_rtf_compressed_body", "msg_rtf_only", "msg_rtf_bad_crc"):
        assert (MSG / f"{name}.msg").is_file(), name
