"""Turn 0.2: the skeleton walker (build spec, Turn 0.2; D2/D9/D11-D14).

The rules under test: the same part shape over the ``.eml`` adapter and the fake
container; every byte accounted for by exactly one region; preamble and epilogue
as their own recorded regions; one field per obs-fold chain with duplicates kept
and the header region failing open past a malformed line; the decode chain
declared-versus-used with ``fallback_fired``; the recorded lossy decode (never
the normal path); content-addressed part identity; and the six unbuilt sections
recorded as ``unknown(not_built_in_phase0)``.
"""

from __future__ import annotations

import base64
import hashlib

import pytest

from emailextract.container import EmlContainer, FakeContainer, memory_bytes
from emailextract.ids import NOT_BUILT_IN_PHASE0, RawSpan, content_hash, part_id
from emailextract.model import ContainerKind, EncodingSource, TriState
from emailextract.walk import (
    GAP_BODY_BOUNDARY_DISAGREEMENT,
    GAP_BODY_DECODE_DESTROYED_BYTES,
    GAP_BODY_DECODE_FALLBACK_USED,
    GAP_BODY_EPILOGUE_BYTES,
    GAP_BODY_HEADERS_ONLY,
    GAP_BODY_NO_BOUNDARY_FOUND,
    GAP_BODY_PREAMBLE_BYTES,
    GAP_HEADERS_MALFORMED_LINE,
    UNBUILT_SECTIONS,
    UnknownSection,
    header_fields_at,
    walk,
)

SCANNER = (
    b"Received: from a.example by b.example; Tue, 4 Mar 2025 08:59:00 +0000\r\n"
    b"Received: from c.example by a.example; Tue, 4 Mar 2025 08:58:00 +0000\r\n"
    b"Subject: a folded value\r\n"
    b"\tcontinues here\r\n"
    b"not a header line\r\n"
    b"X-After: still recorded\r\n"
    b"\r\n"
    b"body after the headers\r\n"
)

MULTIPART = (
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="B-1"\r\n'
    b"\r\n"
    b"preamble text\r\n"
    b"--B-1\r\n"
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    + base64.b64encode(b"part two")
    + b"\r\n"
    b"--B-1--\r\n"
    b"epilogue text\r\n"
)

NESTED = (
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: multipart/alternative; boundary=OUTER\r\n"
    b"\r\n"
    b"--OUTER\r\n"
    b"Content-Type: text/plain; charset=iso-8859-1\r\n"
    b"\r\n"
    b"Caf\xe9 na\xefve\r\n"
    b"--OUTER\r\n"
    b"Content-Type: multipart/alternative; boundary=INNER\r\n"
    b"\r\n"
    b"--INNER\r\n"
    b"Content-Type: text/html\r\n"
    b"\r\n"
    b"<p>view</p>\r\n"
    b"--INNER--\r\n"
    b"--OUTER--\r\n"
)

QUOTED_BOUNDARY = (
    b"Content-Type: multipart/mixed; boundary=\"x;y\"\r\n"
    b"\r\n"
    b"--x;y\r\n"
    b"\r\n"
    b"part\r\n"
    b"--x;y--\r\n"
)

UNKNOWN_CTE = (
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Transfer-Encoding: x-no-such-cte\r\n"
    b"\r\n"
    b"payload kept verbatim\r\n"
)

BROKEN_BASE64 = (
    b"Content-Type: text/plain; charset=us-ascii\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    b"not*valid*base64==\r\n"
)

LOSSY = (
    b"Content-Type: text/plain; charset=x-no-such-charset\r\n"
    b"\r\n"
    b"byte \x81 broke the round trip\r\n"
)

UTF8 = (
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Transfer-Encoding: quoted-printable\r\n"
    b"\r\n"
    b"Caf=C3=A9 na=C3=AFve\r\n"
)

UTF8_UNDECLARED = (
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"Caf\xc3\xa9 na\xc3\xafve\r\n"
)

WINDOWS_1252_UNDECLARED = (
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"price \x80 9\r\n"
)

HEADERS_ONLY = b"Subject: no blank line follows\r\nX-Last: to end of file"

NO_BOUNDARY = (
    b"Content-Type: multipart/mixed\r\n"
    b"\r\n"
    b"--missing\r\n"
    b"\r\n"
    b"body\r\n"
)

NO_CLOSE = (
    b"Content-Type: multipart/mixed; boundary=B\r\n"
    b"\r\n"
    b"--B\r\n"
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"one\r\n"
    b"--B\r\n"
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"two\r\n"
)

ALL_MESSAGES = (
    SCANNER,
    MULTIPART,
    NESTED,
    QUOTED_BOUNDARY,
    UNKNOWN_CTE,
    BROKEN_BASE64,
    LOSSY,
    UTF8,
    UTF8_UNDECLARED,
    WINDOWS_1252_UNDECLARED,
    HEADERS_ONLY,
    NO_BOUNDARY,
    NO_CLOSE,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root(message: bytes):
    return walk(EmlContainer(memory_bytes(message))).parts[0]


def _part(result, path: str):
    for item in result.parts:
        if item.path == path:
            return item
    raise AssertionError(f"no part {path!r} in {[item.path for item in result.parts]}")


def assert_tiles(result, message: bytes) -> None:
    """Every input byte is accounted for by exactly one region (D9, no silent drop)."""
    assert result.total_bytes == len(message)
    position = 0
    for span in sorted((region.span for region in result.regions), key=lambda item: item.offset):
        assert span.offset == position, f"gap or overlap at byte {position}"
        assert span.slice(message) == message[span.offset : span.end]
        position = span.end
    assert position == len(message)


@pytest.mark.parametrize("message", ALL_MESSAGES)
def test_every_byte_is_accounted_for_by_exactly_one_region(message: bytes) -> None:
    assert_tiles(walk(EmlContainer(memory_bytes(message))), message)


def test_the_same_part_shape_over_the_eml_adapter_and_the_fake() -> None:
    on_eml = walk(EmlContainer(memory_bytes(SCANNER)))
    on_fake = walk(FakeContainer(SCANNER))
    assert on_eml.container_kind is ContainerKind.RFC822
    assert on_fake.container_kind is ContainerKind.CFB_MSG
    # Measured shape identical; only the container's own, recorded facts differ.
    assert on_eml.parts == on_fake.parts
    assert on_eml.regions == on_fake.regions
    assert on_eml.unknown_sections == on_fake.unknown_sections


def test_a_fold_is_one_field_with_duplicates_kept_and_the_region_failing_open() -> None:
    result = walk(EmlContainer(memory_bytes(SCANNER)))
    root = result.parts[0]
    fields = root.header_fields
    assert [item.name for item in fields] == ["Received", "Received", "Subject", "", "X-After"]

    # Duplicates are kept, identity by ordinal (spike c01).
    assert fields[0].ordinal == 0 and fields[1].ordinal == 1
    assert fields[0].raw_value.endswith("08:59:00 +0000")

    # The obs-fold chain is ONE field (D2), its raw span covering the fold verbatim.
    folded = fields[2]
    assert folded.parse_status == "ok"
    assert folded.raw_span.slice(SCANNER) == b"Subject: a folded value\r\n\tcontinues here\r\n"
    assert folded.raw_value == " a folded value\r\n\tcontinues here"
    assert folded.value_span.slice(SCANNER).endswith(b"continues here")

    # The malformed line is its own paragraph, parse_status unknown (D2) ...
    bad = fields[3]
    assert bad.parse_status == "unknown"
    assert bad.name == ""
    assert bad.raw_value == "not a header line"
    assert GAP_HEADERS_MALFORMED_LINE in root.gaps

    # ... and the region does NOT end: the header after it is still recorded.
    assert fields[4].name == "X-After"
    assert fields[4].parse_status == "ok"


def test_the_header_scanner_reports_fields_with_their_spans_into_the_raw_message() -> None:
    fields, gaps = header_fields_at(SCANNER, 0, SCANNER.index(b"\r\n\r\n") + 2)
    assert gaps == [GAP_HEADERS_MALFORMED_LINE]
    assert len(fields) == 5
    for item in fields:
        assert isinstance(item.raw_span, RawSpan)
        assert item.raw_span.slice(SCANNER)


def test_the_decode_chain_records_what_was_declared_against_what_ran() -> None:
    result = walk(EmlContainer(memory_bytes(MULTIPART)))
    child = _part(result, "1.1")
    chain = child.decode_chain
    assert chain.declared_cte == "base64"
    assert chain.used_cte == "base64"
    assert chain.declared_charset == "us-ascii"
    assert chain.used_charset == "us-ascii"
    assert chain.fallback_fired is False
    assert child.encoding_source is EncodingSource.DECLARED_CHARSET
    assert child.body_sha256 == _sha256(b"part two")


def test_quoted_printable_is_decoded_and_recorded() -> None:
    root = _root(UTF8)
    assert root.decode_chain.declared_cte == "quoted-printable"
    assert root.decode_chain.used_cte == "quoted-printable"
    assert root.decode_chain.used_charset == "utf-8"
    assert root.decode_chain.fallback_fired is False
    assert root.encoding_source is EncodingSource.DECLARED_CHARSET
    assert root.body_sha256 == _sha256(b"Caf\xc3\xa9 na\xc3\xafve\r\n")


def test_the_charset_ladder_uses_its_named_rungs_when_nothing_was_declared() -> None:
    utf8 = _root(UTF8_UNDECLARED)
    assert utf8.decode_chain.declared_charset is None
    assert utf8.decode_chain.used_charset == "utf-8"
    assert utf8.encoding_source is EncodingSource.UTF8_STRICT
    assert utf8.decode_chain.fallback_fired is False

    windows = _root(WINDOWS_1252_UNDECLARED)
    assert windows.decode_chain.used_charset == "windows-1252"
    assert windows.encoding_source is EncodingSource.WINDOWS_1252
    assert windows.decode_chain.fallback_fired is False

    ascii_only = _root(SCANNER)
    assert ascii_only.decode_chain.used_charset == "us-ascii"
    assert ascii_only.encoding_source is EncodingSource.ASCII


def test_an_unknown_cte_records_the_fallback_and_keeps_the_payload() -> None:
    root = _root(UNKNOWN_CTE)
    chain = root.decode_chain
    assert chain.declared_cte == "x-no-such-cte"
    assert chain.used_cte is None  # stdlib silently returns the raw payload (spike d03)
    assert chain.fallback_fired is True
    assert GAP_BODY_DECODE_FALLBACK_USED in root.gaps
    assert root.body_sha256 == _sha256(b"payload kept verbatim\r\n")


def test_a_broken_base64_payload_is_not_a_quiet_partial_decode() -> None:
    root = _root(BROKEN_BASE64)
    assert root.decode_chain.used_cte is None
    assert root.decode_chain.fallback_fired is True
    assert GAP_BODY_DECODE_FALLBACK_USED in root.gaps
    assert root.body_sha256 == _sha256(b"not*valid*base64==\r\n")


def test_a_lossy_decode_is_recorded_and_replacement_is_never_the_normal_path() -> None:
    lossy = _root(LOSSY)
    assert lossy.decode_chain.fallback_fired is True
    assert lossy.encoding_source is EncodingSource.FALLBACK
    assert GAP_BODY_DECODE_DESTROYED_BYTES in lossy.gaps

    # The normal path is a strict rung: no replacement, no destroyed-bytes gap.
    for message in (UTF8, MULTIPART, SCANNER):
        for item in walk(EmlContainer(memory_bytes(message))).parts:
            assert item.encoding_source is not EncodingSource.FALLBACK
            assert GAP_BODY_DECODE_DESTROYED_BYTES not in item.gaps
            assert item.decode_chain.fallback_fired is False


def test_the_preamble_and_the_epilogue_are_their_own_accounted_regions() -> None:
    result = walk(EmlContainer(memory_bytes(MULTIPART)))
    root = result.parts[0]
    kinds = {region.kind for region in result.regions}
    assert {"headers", "preamble", "delimiter", "body", "epilogue"} <= kinds

    preamble = next(region for region in result.regions if region.kind == "preamble")
    epilogue = next(region for region in result.regions if region.kind == "epilogue")
    # RFC 2046: the CRLF before a delimiter belongs to the delimiter, not the
    # preamble -- what is recorded is exactly the bytes that region covers.
    assert preamble.span.slice(MULTIPART) == b"preamble text"
    assert epilogue.span.slice(MULTIPART) == b"epilogue text\r\n"
    assert GAP_BODY_PREAMBLE_BYTES in root.gaps
    assert GAP_BODY_EPILOGUE_BYTES in root.gaps


def test_a_quoted_boundary_is_one_parameter_not_a_semicolon_split() -> None:
    result = walk(EmlContainer(memory_bytes(QUOTED_BOUNDARY)))
    assert [item.path for item in result.parts] == ["1", "1.1"]
    assert result.parts[0].content_type == "multipart/mixed"
    assert_tiles(result, QUOTED_BOUNDARY)


def test_nested_parts_carry_their_path_and_parent_as_locators() -> None:
    result = walk(EmlContainer(memory_bytes(NESTED)))
    assert [item.path for item in result.parts] == ["1", "1.1", "1.2", "1.2.1"]
    assert [item.parent_path for item in result.parts] == [None, "1", "1", "1.2"]
    assert result.parts[0].content_type == "multipart/alternative"
    cafe = _part(result, "1.1")
    assert cafe.content_type == "text/plain"
    assert cafe.decode_chain.used_charset == "iso-8859-1"
    assert cafe.body_sha256 == _sha256(b"Caf\xe9 na\xefve")
    assert _part(result, "1.2.1").content_type == "text/html"
    assert_tiles(result, NESTED)


def test_a_part_id_is_the_content_addressed_triple_not_the_locator() -> None:
    result = walk(EmlContainer(memory_bytes(NESTED)))
    container_id = result.container_hash
    for item in result.parts:
        assert item.part_id == part_id(
            container_id, item.raw_span, content_hash(item.raw_span.slice(NESTED))
        )
    # The locator is explicitly not an identity: it is not even an input to the id.
    child = _part(result, "1.1")
    assert child.part_id == part_id(
        container_id,
        RawSpan(child.raw_span.offset, child.raw_span.length, "9.9.9"),
        content_hash(child.raw_span.slice(NESTED)),
    )


def test_a_headers_only_message_records_its_state_by_name() -> None:
    root = _root(HEADERS_ONLY)
    assert root.body_span.length == 0
    assert GAP_BODY_HEADERS_ONLY in root.gaps
    assert root.header_fields[-1].name == "X-Last"


def test_a_multipart_without_a_boundary_names_the_gap_and_invents_no_parts() -> None:
    result = walk(EmlContainer(memory_bytes(NO_BOUNDARY)))
    assert [item.path for item in result.parts] == ["1"]
    assert GAP_BODY_NO_BOUNDARY_FOUND in result.parts[0].gaps
    assert_tiles(result, NO_BOUNDARY)


def test_a_missing_close_boundary_is_a_named_disagreement_not_a_guessed_stop() -> None:
    result = walk(EmlContainer(memory_bytes(NO_CLOSE)))
    assert [item.path for item in result.parts] == ["1", "1.1", "1.2"]
    assert GAP_BODY_BOUNDARY_DISAGREEMENT in result.parts[0].gaps
    # The tail runs to the end of the body -- no byte is dropped, none invented.
    assert _part(result, "1.2").body_span.slice(NO_CLOSE) == b"two\r\n"
    assert_tiles(result, NO_CLOSE)


def test_every_unbuilt_section_is_unknown_with_its_reason_id() -> None:
    result = walk(EmlContainer(memory_bytes(SCANNER)))
    assert [item.section for item in result.unknown_sections] == list(UNBUILT_SECTIONS)
    assert len(result.unknown_sections) == 6
    for item in result.unknown_sections:
        assert item.value.state is TriState.UNKNOWN
        assert item.value.reason_id == NOT_BUILT_IN_PHASE0
    # The honesty rule in the shape itself: unknown cannot exist without its reason.
    with pytest.raises(ValueError):
        UnknownSection("thread_edges", _absent())
    with pytest.raises(ValueError):
        UnknownSection("", result.unknown_sections[0].value)


def _absent():
    from emailextract.model import TriValue

    return TriValue(state=TriState.ABSENT, reason_id=NOT_BUILT_IN_PHASE0)


def _single_part(content_type_line: bytes, body: bytes) -> bytes:
    head = b"From: a@example.test\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
    return head + content_type_line + b"Content-Transfer-Encoding: base64\r\n\r\n" + body


@pytest.mark.parametrize(
    "content_type_line",
    [
        b"Content-Type: application/pdf\r\n",
        b"Content-Type: image/png\r\n",
        b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n",
    ],
)
def test_a_binary_part_has_no_charset_reading_and_no_false_destroyed_bytes(
    content_type_line: bytes,
) -> None:
    """A charset belongs to text. Bytes that are not valid text in any rung (the PNG signature, a zip
    header) used to be run through the text ladder: a windows-1252 reading, fallback_fired, and a
    false body.decode_destroyed_bytes for content that was never text."""
    payload = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x81\x8d\x8f\x90\x9d\xff\xfe").decode() + "\r\n"
    result = walk(EmlContainer(_single_part(content_type_line, payload.encode())))
    part = result.parts[0]
    assert part.decode_chain.used_cte == "base64"
    assert part.decode_chain.used_charset is None
    assert part.decode_chain.fallback_fired is False
    assert part.encoding_source is None
    assert GAP_BODY_DECODE_DESTROYED_BYTES not in part.gaps


def test_a_text_part_and_a_part_with_no_content_type_still_get_the_ladder() -> None:
    """The fix is scoped to non-text: text/* and the RFC default (no Content-Type = text/plain) keep it."""
    lossy = base64.b64encode(b"caf\x81\x8d").decode() + "\r\n"
    for line in (b"Content-Type: text/plain\r\n", b""):
        part = walk(EmlContainer(_single_part(line, lossy.encode()))).parts[0]
        assert part.decode_chain.used_charset is not None, line
        assert part.encoding_source is not None, line
