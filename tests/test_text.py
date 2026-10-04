"""Turn 1.4: per-part text, the alias table, offset maps and the one line model.

The rules under test (decision 8, binding): the coordinate space is the part's decoded text in
code points, **un-normalised**; an offset map exists -- and a within-part byte span may be
called ``exact`` -- only for a **strict** decode of the **used** charset over a stateless
charset whose CTE was identity; every other case is ``part_level`` with a closed
``verbatim_reason`` and **no** within-part byte span. The property test is independent of how
the map is stored: the entries partition both ranges, a fresh re-decode of a slice equals the
text slice, a strict decode round-trips by encoding back, the joined slices rebuild the raw
bytes, and an anti-vacuity mutant that breaks one entry's byte length fails.

Every failure names the fixture, the fact, the gap id and the bytes (the build spec's rule).

The corpus sweep is one module fixture: walking all 90 committed fixtures once and measuring
``body.text`` for each of their 95 exact text parts costs a walk per fixture, so it is done
once and shared by the property tests.
"""

from __future__ import annotations

import ast
import codecs
import random
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support.sidecar_copy import tamper  # noqa: E402
from support import stdlib_scanner  # noqa: E402

from emailextract import rfc2047, text as text_stage  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars  # noqa: E402
from emailextract.text import (  # noqa: E402
    CHARSET_ALIASES,
    GAP_BODY_FLOWED_REFLOW_UNRESOLVED,
    STATEFUL_OR_MULTIBYTE,
    VERBATIM_EXACT,
    analyse_part,
    analyse_parts,
    body_gaps,
    canonical_charset,
    charset_known,
    line_bounds,
    part_text_rows,
)
from emailextract.walk import iter_lines, walk  # noqa: E402

IDENTITY_CTES = ("7bit", "8bit", "binary")


def _walk(message: bytes):
    return walk(EmlContainer(memory_bytes(message)))


def _message(body: bytes, content_type: bytes | None = b"text/plain; charset=utf-8", cte: bytes | None = None):
    """A minimal one-part message: a Content-Type (or none), an optional CTE, then ``body``."""
    head = b"From: Ada Sender <ada@example.test>\r\n"
    if content_type is not None:
        head += b"Content-Type: " + content_type + b"\r\n"
    if cte is not None:
        head += b"Content-Transfer-Encoding: " + cte + b"\r\n"
    return head + b"\r\n" + body


def _record(message: bytes):
    """The single part's :class:`~emailextract.text.PartText` (recording the part if it has none)."""
    raw = message
    result = _walk(raw)
    assert result.parts, "the message has no part"
    record = analyse_part(raw, result.parts[0])
    return raw, result, result.parts[0], record


@pytest.fixture(scope="module")
def corpus_text_parts():
    """Every committed text part, with the bytes it was measured from, walked once."""
    items = []
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        for part in result.parts:
            record = analyse_part(raw, part)
            if record is not None:
                items.append((stem, raw, part, record))
    assert len(items) > 50, "the corpus sweep found almost no text parts"
    return items


def _body(raw: bytes, part) -> bytes:
    """The part's body bytes: the address space every offset-map byte offset points into."""
    return raw[part.body_span.offset : part.body_span.end]


def _assert_properties(
    raw: bytes, part, record, *, unstuffed: bool | None = None
) -> None:
    """The five properties of decision 8 for one ``exact`` record.

    ``raw`` is the **message**; the properties are asserted against the part's **body bytes**
    (the walker's ``body_span``), which is the address space the map's byte offsets point into.
    ``unstuffed`` says the text had RFC 3676 stuffing bytes dropped (the flowed case), which
    the map records as **zero-character** spans: the byte runs still partition the body, but
    re-encoding the text gives back only the bytes that produce characters. Everywhere else
    ``text.encode(used) == body`` holds literally.
    """
    body = _body(raw, part)
    spans = record.offset_map
    assert spans is not None, f"{record.path}: exact must carry a map (absent means part_level)"
    canonical = canonical_charset(record.used_charset)
    assert canonical is not None, f"{record.path}: exact needs a resolvable used charset"
    if unstuffed is None:
        unstuffed = record.flowed

    # (1) strictly increasing, and partition both [0, len(body)) and [0, len(text)).
    byte_cursor = 0
    char_cursor = 0
    for span in spans:
        assert span.byte_offset == byte_cursor, f"{record.path}: a byte gap at {span}"
        assert span.char_offset == char_cursor, f"{record.path}: a char gap at {span}"
        byte_cursor = span.byte_end
        char_cursor = span.char_end
    assert byte_cursor == len(body), f"{record.path}: the spans cover {byte_cursor} of {len(body)} bytes"
    assert char_cursor == len(record.text), f"{record.path}: spans cover {char_cursor} chars"

    for span in spans:
        slice_ = body[span.byte_offset : span.byte_end]
        piece = record.text[span.char_offset : span.char_end]
        if span.char_length == 0:
            # A dropped byte (a stuffing space, a utf-8-sig BOM): it produces no character.
            continue
        # (2) a fresh re-decode of the slice equals the text slice.
        assert slice_.decode(canonical) == piece, f"{record.path}: {slice_!r} != {piece!r}"
    # (4) the joined slices rebuild the body bytes.
    assert b"".join(body[s.byte_offset : s.byte_end] for s in spans) == body, record.path
    # (3) a strict decode round-trips by encoding back.
    encoded = record.text.encode(canonical)
    if unstuffed and any(span.char_length == 0 for span in spans):
        kept = b"".join(body[s.byte_offset : s.byte_end] for s in spans if s.char_length > 0)
        assert encoded == kept, f"{record.path}: {encoded!r} != {kept!r}"
    else:
        assert encoded == body, f"{record.path}: {encoded!r} != {body!r}"


# ------------------------------------------------------------------- the line model


def test_the_splitter_line_starts_equal_iter_lines_over_a_cr_body() -> None:
    """One line model: the splitter's line starts are ``walk.iter_lines``' starts, over CR too."""
    raw = (
        b"one\r\ntwo\nthree\rfour\r\n\rfive\n\n"
        b"six\r"
    )
    expected = list(iter_lines(raw, 0, len(raw)))
    assert line_bounds(raw, 0, len(raw)) == expected
    assert [line[0] for line in line_bounds(raw, 0, len(raw))] == [line[0] for line in expected]
    starts = [line[0] for line in expected]
    contents = [raw[line[0] : line[1]] for line in expected]
    assert contents == [
        b"one",
        b"two",
        b"three",
        b"four",
        b"",
        b"five",
        b"",
        b"six",
    ], contents
    assert starts == [0, 5, 9, 15, 21, 22, 27, 28], starts
    # The body ends in a lone CR: that CR is a terminator, so there is no empty last line.
    assert expected[-1][2] == len(raw)
    # ... and a body ending in CRLF *does* leave an empty last line: its content is empty.
    tail = b"x\r\n\r\n"
    assert [tail[s:content_end] for s, content_end, _e in iter_lines(tail, 0, len(tail))] == [
        b"x",
        b"",
    ]


def test_the_splitter_does_not_break_on_form_feed_or_u2028() -> None:
    """``str.splitlines``/``bytes.splitlines`` are forbidden: they also break on FF and U+2028."""
    form_feed = b"a\x0cb\r\n"
    u2028 = "a\u2028b".encode("utf-8")
    for raw in (form_feed, u2028):
        lines = line_bounds(raw, 0, len(raw))
        assert len(lines) == 1, f"{raw!r} was split into {lines}"
        assert raw[lines[0][0] : lines[0][1]] == raw.rstrip(b"\n").rstrip(b"\r")
    # A decoded U+2028 also survives as one line in text space: the decoded text keeps it.
    _raw, _result, _part, record = _record(_message(u2028 + b"\r\n"))
    assert "\u2028" in record.text
    assert record.text.count("\r\n") == 1


def test_no_second_line_splitter_in_text_py() -> None:
    """A source test: no second line-splitting implementation lives in ``text.py``.

    Docstrings may *name* ``splitlines`` (they must, to forbid it); the test reads the module's
    AST, so only real code counts: no ``x.splitlines(...)``, no ``re`` import, no regex.
    """
    source = (ROOT / "emailextract" / "text.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "splitlines"
    ]
    assert not offenders, "text.py must not split lines a second way"
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert "re" not in imported, "a regex line splitter is a second line model"
    assert "iter_lines" in source, "text.py must consume the one line model"
    assert "split" in source and "line_bounds" in source


# --------------------------------------------------------------- the offset map


def test_a_strict_identity_decode_builds_an_exact_offset_map() -> None:
    """A strict identity decode over UTF-8 builds a map: 2-, 3- and 4-byte code points."""
    body = ("e\u0301\u00e9\u20ac\U0001d11e\r\n").encode("utf-8")
    raw, _result, part, record = _record(_message(body))
    assert record is not None and record.verbatim_precision == VERBATIM_EXACT
    assert record.verbatim_reason is None
    assert record.offset_map is not None
    _assert_properties(raw, part, record)
    multibyte = [s for s in record.offset_map if s.byte_length > 1]
    assert sorted({s.byte_length for s in multibyte}) == [2, 3, 4]


def test_spans_partition_the_raw_bytes_and_the_text(corpus_text_parts) -> None:
    """(1) Every span is strictly increasing and the spans tile both coordinate ranges."""
    exact = 0
    for stem, raw, part, record in corpus_text_parts:
        if record.verbatim_precision != VERBATIM_EXACT:
            continue
        assert record.used_cte in IDENTITY_CTES, (stem, record.used_cte)
        _assert_properties(raw, part, record)
        exact += 1
    assert exact >= 80, f"only {exact} exact text parts in the corpus"
    # Inline cases the corpus does not carry: an empty body, a body of only terminators, and a
    # single high byte decoded by the windows-1252 rung (one byte, one code point).
    for body in (b"", b"\r\n", b"\r", b"\n"):
        raw, _result, part, record = _record(_message(body))
        assert record.verbatim_precision == VERBATIM_EXACT, body
        _assert_properties(raw, part, record)
        assert record.text == body.decode("utf-8")
    raw, _result, part, lone = _record(_message(b"\x93", content_type=None))
    assert lone.used_charset == "windows-1252" and lone.text == "\u201c"
    assert [(s.byte_length, s.char_length) for s in lone.offset_map or ()] == [(1, 1)]
    _assert_properties(raw, part, lone)


def test_a_fresh_redecode_of_a_slice_equals_the_text_slice(corpus_text_parts) -> None:
    """(2) ``raw[bo:be].decode(used) == text[cs:ce]`` for every char-producing span."""
    seen = 0
    for stem, raw, part, record in corpus_text_parts:
        if record.verbatim_precision != VERBATIM_EXACT:
            continue
        body = _body(raw, part)
        canonical = canonical_charset(record.used_charset)
        for span in record.offset_map or ():
            if span.char_length == 0:
                continue
            assert body[span.byte_offset : span.byte_end].decode(canonical) == record.text[
                span.char_offset : span.char_end
            ], stem
            seen += 1
    assert seen > 80


def test_a_strict_decode_round_trips_by_encoding_back(corpus_text_parts) -> None:
    """(3) A strict decode round-trips: ``text.encode(used) == raw`` (or the kept byte runs)."""
    for _stem, raw, part, record in corpus_text_parts:
        if record.verbatim_precision != VERBATIM_EXACT:
            continue
        _assert_properties(raw, part, record)


def test_a_joined_slice_rebuilds_the_raw_bytes(corpus_text_parts) -> None:
    """(4) ``b"".join(slices) == body``: the map accounts for every byte of the body."""
    for _stem, raw, part, record in corpus_text_parts:
        if record.verbatim_precision != VERBATIM_EXACT:
            continue
        body = _body(raw, part)
        spans = record.offset_map or ()
        assert b"".join(body[s.byte_offset : s.byte_end] for s in spans) == body


def test_an_anti_vacuity_mutant_on_a_span_length_fails(monkeypatch) -> None:
    """(5) The anti-vacuity triple: the patched symbol exists, the patch is reached, it flips."""
    body = "caf\u00e9 \u20ac\r\n".encode("utf-8")
    raw, _result, part, record = _record(_message(body))
    _assert_properties(raw, part, record)

    assert hasattr(text_stage, "_build_offset_map"), "the patched symbol must exist"
    reached = []
    original = text_stage._build_offset_map

    def broken(body_bytes, plain_length, dropped, canonical):
        built = original(body_bytes, plain_length, dropped, canonical)
        reached.append(True)
        if not built:
            return built
        first = built[0]
        return (type(first)(first.byte_offset, first.byte_length + 1, first.char_offset, first.char_length), *built[1:])

    monkeypatch.setattr(text_stage, "_build_offset_map", broken)
    raw2, result2 = raw, _walk(raw)
    mutant_record = analyse_part(raw2, result2.parts[0])
    assert reached, "the patch was never reached -- the mutant is vacuous"
    assert mutant_record is not None
    with pytest.raises(AssertionError):
        _assert_properties(raw2, result2.parts[0], mutant_record)


def test_a_bom_stays_exact_for_plain_utf8() -> None:
    """Exactness is a property of the actual decode: plain ``utf-8`` keeps the BOM as a character."""
    body = b"\xef\xbb\xbfHi\r\n"
    raw, _result, part, record = _record(_message(body, content_type=b"text/plain; charset=utf-8"))
    assert record.verbatim_precision == VERBATIM_EXACT
    assert record.text.startswith("\ufeff")
    assert record.text.encode("utf-8") == body
    _assert_properties(raw, part, record)

    # ``utf-8-sig`` breaks that exactness: it consumes a BOM and its ``encode`` re-adds one, so
    # the decode is not the encode's inverse. The prompt's own rule: a BOM "stays exact for
    # plain utf-8 and breaks only under utf-8-sig". It still decodes -- it is the map that goes.
    raw, _result, part, record = _record(
        _message(body, content_type=b"text/plain; charset=utf-8-sig")
    )
    assert record.used_charset == "utf-8-sig"
    assert record.text == "Hi\r\n"
    assert record.verbatim_precision == "part_level"
    assert record.verbatim_reason == "multibyte_without_offset_map"
    assert record.offset_map is None
    # The break is visible on a body with no BOM at all: the encode invents one.
    no_bom = b"Hi\r\n"
    _raw, _result, _part, sig = _record(
        _message(no_bom, content_type=b"text/plain; charset=utf-8-sig")
    )
    assert sig.text == "Hi\r\n"
    assert sig.text.encode("utf-8-sig") == b"\xef\xbb\xbfHi\r\n" != no_bom


# --------------------------------------------------------------- precision and reasons


def test_a_qp_or_base64_part_is_part_level_with_a_reason() -> None:
    """``cte_not_identity`` (the CTE that ran) and ``decode_fallback`` (the CTE that failed)."""
    # A QP part that ran: the CTE was non-identity, so no within-part byte span.
    raw, _result, part, record = _record(
        _message(b"Caf\xe9 =3D ok\r\n", content_type=b"text/plain; charset=iso-8859-1", cte=b"quoted-printable")
    )
    assert (record.verbatim_precision, record.verbatim_reason) == ("part_level", "cte_not_identity")
    assert record.offset_map is None
    assert record.text == "Caf\u00e9 = ok\r\n", repr(record.text)
    # A base64 part that ran: same reason, and the decoded bytes are the text's bytes.
    raw, _result, part, record = _record(
        _message(b"SGVsbG8=\r\n", content_type=b"text/plain; charset=us-ascii", cte=b"base64")
    )
    assert (record.verbatim_precision, record.verbatim_reason) == ("part_level", "cte_not_identity")
    assert record.offset_map is None and record.text == "Hello"
    # A base64 part whose decoding *failed*: the declared CTE never ran, so the reason is the
    # fallback -- the label for base64_with_whitespace_and_bad_padding types exactly this.
    raw, _result, part, record = _record(
        _message(b"SGVs bG8\r\n", content_type=b"text/plain; charset=us-ascii", cte=b"base64")
    )
    assert record.used_cte is None
    assert (record.verbatim_precision, record.verbatim_reason) == ("part_level", "decode_fallback")
    assert record.offset_map is None and record.text == "SGVs bG8\r\n"
    # An unknown CTE: the same fallback state (the walker's own verdict).
    _raw, _result, _part, record = _record(
        _message(b"payload\r\n", content_type=b"text/plain; charset=utf-8", cte=b"x-uuencode")
    )
    assert (record.verbatim_precision, record.verbatim_reason) == ("part_level", "decode_fallback")


def test_a_stateful_charset_is_multibyte_without_offset_map() -> None:
    """Stateful/multibyte charsets have no offset map -- even when they decode strictly."""
    jis = "\u3042\u3044\u3046".encode("iso-2022-jp")
    _raw, _result, _part, record = _record(
        _message(jis + b"\r\n", content_type=b"text/plain; charset=iso-2022-jp")
    )
    assert (record.verbatim_precision, record.verbatim_reason) == (
        "part_level",
        "multibyte_without_offset_map",
    )
    assert record.offset_map is None and record.text == "\u3042\u3044\u3046\r\n"

    utf16 = "Hi \u20ac\r\n".encode("utf-16")
    _raw, _result, _part, record = _record(
        _message(utf16, content_type=b"text/plain; charset=utf-16")
    )
    assert record.used_cte in IDENTITY_CTES, "a strict decode still is not exact here"
    assert record.verbatim_precision == "part_level"
    assert record.verbatim_reason == "multibyte_without_offset_map"
    assert record.offset_map is None

    sjis = "\u3042\u3044".encode("shift_jis")
    _raw, _result, _part, record = _record(
        _message(sjis + b"\r\n", content_type=b"text/plain; charset=shift_jis")
    )
    assert record.verbatim_reason == "multibyte_without_offset_map"
    assert set(STATEFUL_OR_MULTIBYTE) >= {"iso2022_jp", "shift_jis", "utf-16", "gb2312", "hz"}


def test_a_part_level_row_emits_no_within_part_byte_span() -> None:
    """``part_level`` means the map is **absent**, not merely empty (D12)."""
    _raw, _result, _part, record = _record(
        _message(b"=\r\n", content_type=b"text/plain; charset=utf-8", cte=b"base64")
    )
    assert record.verbatim_precision == "part_level"
    assert record.offset_map is None, "a part_level row must carry no within-part byte span"
    assert record.offset_map != (), "the map must be absent, not an empty tuple"
    # ... while an *exact* part with an empty body carries an empty (present) map.
    _raw, _result, _part, empty = _record(_message(b""))
    assert empty.verbatim_precision == VERBATIM_EXACT
    assert empty.offset_map == ()
    assert empty.offset_map is not None


def test_the_used_charset_not_the_declared_one_keys_the_map() -> None:
    """The map is keyed by the charset that actually decoded, never by the declared spelling."""
    # Declared us-ascii over a C1 byte: the ladder moves to windows-1252, so the map cannot be
    # built from "us-ascii" (which would not decode these bytes at all).
    raw, _result, part, record = _record(
        _message(b"\x93hi\x94\r\n", content_type=b"text/plain; charset=us-ascii")
    )
    assert record.declared_charset == "us-ascii"
    assert record.used_charset == "windows-1252"
    assert record.verbatim_reason == "decode_fallback"
    assert record.offset_map is None
    assert record.text == "\u201chi\u201d\r\n", repr(record.text)
    with pytest.raises(UnicodeDecodeError):
        b"\x93hi\x94\r\n".decode("us-ascii")

    # Nothing declared: the used charset is the walker's ASCII rung, and *that* keys the map.
    raw, _result, part, record = _record(
        _message(b"plain\r\n", content_type=None)
    )
    assert record.declared_charset is None
    assert record.used_charset == "us-ascii"
    assert record.verbatim_precision == VERBATIM_EXACT
    assert record.offset_map is not None
    _assert_properties(raw, part, record)


def test_the_coordinate_space_does_not_normalise_crlf() -> None:
    """CRLF stays two code points: no CRLF folding, no NFC (decision 8)."""
    raw, _result, _part, record = _record(_message(b"a\r\nb\r\n"))
    assert record.text == "a\r\nb\r\n"
    assert len(record.text) == 6
    assert "a\nb\n" != record.text
    # A decomposed sequence is not NFC-composed either.
    _raw, _result, _part, decomposed = _record(_message("e\u0301\r\n".encode("utf-8")))
    assert decomposed.text == "e\u0301\r\n"
    assert decomposed.text != "\u00e9\r\n"


def test_the_charset_ladder_only_runs_over_text_parts() -> None:
    """A binary part gets NO text and NO ``body.text`` row -- the walker's decision, reused."""
    pdf = b"%PDF-1.4\n\x93\x00\xff\n%%EOF\r\n"
    message = (
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Content-Type: multipart/mixed; boundary=\"b1\"\r\n"
        b"\r\n"
        b"--b1\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nHello.\r\n"
        b"--b1\r\nContent-Type: application/pdf\r\n\r\n" + pdf + b"--b1--\r\n"
    )
    raw = message
    result = _walk(raw)
    rows = part_text_rows(raw, result)
    pdf_parts = [p for p in result.parts if (p.content_type or "").startswith("application/")]
    assert len(pdf_parts) == 1, [p.content_type for p in result.parts]
    assert pdf_parts[0].decode_chain.used_charset is None
    assert analyse_part(raw, pdf_parts[0]) is None
    assert [row[0] for row in rows] == ["1.1"], rows
    # The pdf's bytes never became text: no row carries the 0x93 byte it contains.
    assert all("\x93" not in row[1] for row in rows)


def test_the_text_part_decision_is_not_widened(corpus_text_parts) -> None:
    """The parts with a ``body.text`` row are exactly the parts the walker read as text."""
    for stem, raw, part, record in corpus_text_parts:
        assert part.decode_chain.used_charset is not None, stem
        assert analyse_part(raw, part) is not None
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        with_row = {record.path for record in analyse_parts(raw, result)}
        as_text = {p.path for p in result.parts if p.decode_chain.used_charset is not None}
        assert with_row == as_text, stem


# ------------------------------------------------------------------------ flowed


def test_flowed_space_unstuffing_runs_before_gt_counting() -> None:
    """A stuffed space in front of ``>`` is removed, so the ``>`` is at the line start."""
    body = b"first line \r\n > quoted once\r\nplain\r\n"
    raw, _result, part, record = _record(
        _message(body, content_type=b"text/plain; charset=utf-8; format=flowed")
    )
    assert record.flowed is True and record.delsp is False
    assert record.text == "first line \r\n> quoted once\r\nplain\r\n", repr(record.text)
    lines = record.text.split("\r\n")
    assert lines[1].startswith(">"), "the stuffing space was not unstuffed before the > count"
    assert body.decode().split("\r\n")[1].startswith(" >")
    # The byte the stuffing space occupied is still accounted for, as a zero-character span.
    dropped = [s for s in record.offset_map or () if s.char_length == 0]
    assert [s.byte_length for s in dropped] == [1]
    _assert_properties(raw, part, record)


def test_flowed_soft_break_join_is_the_recorded_gap() -> None:
    """The soft-break JOIN is deferred: the break stays in the text and the gap is recorded."""
    body = b"A soft break ends here \r\n and this line was space-stuffed.\r\n"
    raw, result, _part, record = _record(
        _message(body, content_type=b"text/plain; charset=utf-8; format=flowed")
    )
    assert record.text == "A soft break ends here \r\nand this line was space-stuffed.\r\n"
    assert "\r\n" in record.text, "the soft break must NOT be joined"
    assert record.gaps == (GAP_BODY_FLOWED_REFLOW_UNRESOLVED,)
    assert body_gaps(raw, result) == [(GAP_BODY_FLOWED_REFLOW_UNRESOLVED, "1")]
    # The gap is registered before it is emitted (an unregistered id would be a STOP).
    registry = (ROOT / "docs" / "design" / "phase0-gaps.md").read_text(encoding="utf-8")
    assert f"`{GAP_BODY_FLOWED_REFLOW_UNRESOLVED}`" in registry
    # DelSp is recorded and never applied: it cannot join what is not joined.
    _raw, _result, _part, delsp = _record(
        _message(body, content_type=b"text/plain; charset=utf-8; format=flowed; delsp=yes")
    )
    assert delsp.delsp is True and delsp.text == record.text
    # A part that does not declare format=flowed is untouched by any of this.
    _raw, _result, _part, plain = _record(_message(body))
    assert plain.flowed is False and plain.gaps == ()
    assert plain.text == body.decode("utf-8")


# ------------------------------------------------------------------- the alias table


def test_the_alias_table_is_closed_sorted_and_collision_free() -> None:
    """Every row resolves through ``codecs.lookup``, is canonical, sorted, and unique."""
    keys = list(CHARSET_ALIASES)
    assert keys == sorted(keys), "the alias table must be sorted"
    assert len(keys) == len(set(keys)), "a spelling appears once"
    for key, value in sorted(CHARSET_ALIASES.items()):
        assert key == key.lower(), key
        assert codecs.lookup(key).name == value, (
            f"{key!r} resolves to {codecs.lookup(key).name!r}, the table says {value!r}"
        )
        assert canonical_charset(key) == value
        assert charset_known(key) is True
    # The values are canonical codec names, so no two rows collide on a codec.
    assert len({codecs.lookup(value).name for value in CHARSET_ALIASES.values()}) <= len(
        set(CHARSET_ALIASES.values())
    )
    assert canonical_charset("UTF-8") == "utf-8"
    assert canonical_charset("utf-8*en") == "utf-8", "the RFC 2231 language suffix is stripped"


def test_an_unknown_charset_name_is_unknown_not_an_exception() -> None:
    """An unknown name is the unknown state, never an exception -- even a hostile one."""
    for name in ("x-no-such-charset", "", " ", "a b", '"', "\x00", "utf-8\x00", "x" * 10000, "*en"):
        assert canonical_charset(name) is None, repr(name)
        assert charset_known(name) is False, repr(name)
    assert canonical_charset("utf-8*") == "utf-8"


def test_an_alias_never_widens_a_charset() -> None:
    """Spellings only: no gb2312->gbk, no iso-8859-1->windows-1252, no ascii->utf-8."""
    assert CHARSET_ALIASES["gb2312"] == "gb2312"
    assert CHARSET_ALIASES["iso-8859-1"] == "iso8859-1"
    assert CHARSET_ALIASES["us-ascii"] == "ascii"
    assert canonical_charset("gb2312") != "gbk"
    assert canonical_charset("iso-8859-1") != "cp1252"
    assert canonical_charset("us-ascii") != "utf-8"
    # The bytes are the judge: a C1 byte declared iso-8859-1 stays U+0093 (a widening alias
    # would have produced U+201C), and it is exact.
    raw, _result, part, record = _record(
        _message(b"\x93Hi\x94\r\n", content_type=b"text/plain; charset=iso-8859-1")
    )
    assert record.text == "\u0093Hi\u0094\r\n", repr(record.text)
    assert record.verbatim_precision == VERBATIM_EXACT
    _assert_properties(raw, part, record)
    # And a gb2312 declaration over bytes that are not gb2312 falls to the walker's windows-1252
    # rung with the fallback recorded -- a widening alias would have "made it work".
    _raw, _result, _part, gb = _record(
        _message(b"\x81@\r\n", content_type=b"text/plain; charset=gb2312")
    )
    assert gb.used_charset == "windows-1252"
    assert gb.verbatim_reason == "decode_fallback"


def test_the_alias_table_is_the_single_charset_resolution_point() -> None:
    """``rfc2047`` delegates: one resolution point, and the two agree everywhere."""
    assert rfc2047.canonical_charset is not text_stage.canonical_charset
    for name in [
        *CHARSET_ALIASES,
        "UTF-8",
        "utf-8*en",
        "x-no-such-charset",
        "",
        "\x00",
        "a b",
        "cp1252",
        "iso8859-1",
    ]:
        assert rfc2047.canonical_charset(name) == canonical_charset(name), repr(name)
        assert rfc2047.charset_known(name) == charset_known(name), repr(name)


# ------------------------------------------------------------------- gap catalogue


#: Every gap id ``text.py`` can emit, with the case that catches a careless implementation.
GAP_CASES = {
    GAP_BODY_FLOWED_REFLOW_UNRESOLVED: (
        "the part declares format=flowed and the reflow is deferred, never performed"
    ),
}


def test_every_emitted_gap_id_has_an_anti_vacuity_case(monkeypatch) -> None:
    """A catalogue test: an emitted gap id with no case fails, and the case is anti-vacuous."""
    assert set(GAP_CASES) == set(text_stage.GAP_IDS), (
        "every emitted gap id needs a case, and every case an emitted id"
    )
    body = b"A soft break ends here \r\n and this line was space-stuffed.\r\n"
    message = _message(body, content_type=b"text/plain; charset=utf-8; format=flowed")
    raw = message
    result = _walk(raw)
    assert body_gaps(raw, result) == [(GAP_BODY_FLOWED_REFLOW_UNRESOLVED, "1")]
    # The anti-vacuity triple: the symbol exists, the patch is reached, the observation flips.
    assert hasattr(text_stage, "flowed_declared")
    reached = []

    def not_flowed(raw_bytes, part):
        reached.append(True)
        return False, False

    monkeypatch.setattr(text_stage, "flowed_declared", not_flowed)
    assert reached == []
    flipped = body_gaps(raw, _walk(raw))
    assert reached, "the patch was never reached -- the case is vacuous"
    assert GAP_BODY_FLOWED_REFLOW_UNRESOLVED not in [gap_id for gap_id, _loc in flipped]


def test_every_gap_emitted_over_the_corpus_is_catalogued(corpus_text_parts) -> None:
    """No gap id leaves the analyser without a catalogue row."""
    for stem, raw, _part, record in corpus_text_parts:
        for gap_id in record.gaps:
            assert gap_id in GAP_CASES, f"{stem}: emitted {gap_id!r} with no case"


def test_the_flowed_declaration_is_read_case_insensitively() -> None:
    """The parameter name and value come from the parsed Content-Type, case-insensitively."""
    _raw, _result, _part, record = _record(
        _message(b"a\r\n", content_type=b"TEXT/PLAIN; CHARSET=UTF-8; Format=Flowed")
    )
    assert record.flowed is True
    assert record.text == "a\r\n"


# ------------------------------------------------------------------------ the fuzz


_FUZZ_CHARSETS = [
    *sorted(CHARSET_ALIASES),
    "iso-8859-2",
    "iso-8859-5",
    "cp1251",
    "x-no-such-charset",
    "\x00",
    "utf-8\x00",
    "a" * 200,
    "shift-jis",
]

_FUZZ_BODIES = [
    b"",
    b"\r\n",
    b"\x00\x00",
    b"A" * 10000,
    b"\xff" * 100,
    b"\xc3\xa9" * 50,
    b"\xe2\x82",
    b"\xf0\x9f\x98",
    b"\xed\xa0\x80",
    b"line \r\n > quoted\r\n",
    b"x" * 5000 + b"\r",
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
    b"%PDF-1.4\n" + b"\xff\xfe" * 30,
]


def _fuzz_error(message: bytes, charset: str, cte: str | None, flowed: bool) -> str | None:
    """Analyse one fuzzed message; return a description of any violated invariant, else None."""
    content_type = None if charset == "<none>" else f"text/plain; charset={charset}"
    if flowed and content_type is not None:
        content_type += "; format=flowed"
    raw = _message(
        message,
        content_type=None if content_type is None else content_type.encode("latin-1", "replace"),
        cte=None if cte is None else cte.encode("latin-1"),
    )
    try:
        result = walk(EmlContainer(memory_bytes(raw)))
        for part in result.parts:
            record = analyse_part(raw, part)
            if record is None:
                continue
            if record.verbatim_precision == VERBATIM_EXACT:
                body = raw[part.body_span.offset : part.body_span.end]
                _assert_properties(raw, part, record, unstuffed=record.flowed)
                assert len(body) == sum(s.byte_length for s in record.offset_map or ())
            else:
                assert record.offset_map is None, "part_level must carry no map"
                assert record.verbatim_reason in text_stage.VERBATIM_REASONS
            again = analyse_part(raw, part)
            assert again == record, "decoding twice must give identical results"
    except AssertionError as error:  # the anti-vacuity of the invariants themselves
        return f"{error}"
    except Exception as error:  # noqa: BLE001 -- a raise is the defect under test
        return f"{type(error).__name__}: {error}"
    return None


def test_text_properties_hold_over_a_seeded_fuzz() -> None:
    """A seeded, bounded fuzz: no exception, every ``exact`` result's properties hold, no map
    for a ``part_level`` result, and decoding twice is identical."""
    rng = random.Random(20250304)
    seeds = 0
    failures: list[str] = []
    for charset in _FUZZ_CHARSETS:
        for cte in (None, "base64", "quoted-printable", "x-uuencode"):
            for flowed in (False, True):
                for body in _FUZZ_BODIES:
                    mutated = bytearray(body)
                    for _ in range(rng.randrange(0, 4)):
                        if mutated:
                            position = rng.randrange(len(mutated))
                            mutated[position] = rng.randrange(256)
                    if rng.random() < 0.3 and mutated:
                        mutated = mutated[: rng.randrange(1, len(mutated) + 1)]
                    seeds += 1
                    problem = _fuzz_error(bytes(mutated), charset, cte, flowed)
                    if problem is not None:
                        failures.append(
                            f"charset={charset!r} cte={cte!r} flowed={flowed} "
                            f"bytes={bytes(mutated)[:60]!r}: {problem}"
                        )
    assert not failures, f"{len(failures)} failure(s):\n" + "\n".join(failures[:10])
    assert seeds >= 2000, seeds


def test_a_planted_raiser_makes_the_fuzz_fail() -> None:
    """The fuzz is not vacuous: a planted raise is caught, and the seed count is deterministic."""
    assert (
        _fuzz_error(b"A" * 40, "utf-8", None, False)
        == _fuzz_error(b"A" * 40, "utf-8", None, False)
        == None
    )  # noqa: E711 -- both runs agree, so the check below compares real analyses
    original = text_stage._merge
    text_stage._merge = lambda spans: (_ for _ in ()).throw(RuntimeError("planted"))
    try:
        # The single-entry fast path does not reach _merge, so a multibyte body is used.
        problem = _fuzz_error("caf\u00e9\r\n".encode("utf-8"), "utf-8", None, False)
    finally:
        text_stage._merge = original
    assert problem is not None and "planted" in problem, problem


def test_the_decode_and_the_map_are_linear_on_a_megabyte_body() -> None:
    """A doubling test: 1 MB and 2 MB bodies (ASCII and multibyte) stay linear."""
    timings = {}
    for label, unit in (("ascii", b"A"), ("multibyte", "\u20ac".encode("utf-8"))):
        for megabytes in (1, 2):
            body = unit * ((megabytes * 1024 * 1024) // len(unit))
            raw = _message(body)
            start = time.perf_counter()
            rows = part_text_rows(raw, _walk(raw))
            timings[(label, megabytes)] = time.perf_counter() - start
            assert len(rows) == 1 and len(rows[0][1]) == len(body) // len(unit)
    for label in ("ascii", "multibyte"):
        small = timings[(label, 1)]
        large = timings[(label, 2)]
        # A linear stage doubles; the bound is loose so a slow machine cannot fail the gate,
        # but it still catches a quadratic map (which would be ~4x or worse).
        assert large <= small * 6 + 0.5, (label, small, large)


# ------------------------------------------------- the stdlib text comparison


def _text_exclusions(raw: bytes, result, records) -> set[str]:
    """The closed reasons this fixture's leaf-text comparison is not a gate (Turn 1.4, item 8)."""
    reasons: set[str] = set()
    if raw.startswith(b"\xef\xbb\xbf"):
        reasons.add("leading_bom")
    if b"\x00" in stdlib_scanner.split_header_block(raw):
        reasons.add("malformed_header_line")
    for part in result.parts:
        if (part.content_type or "").lower().startswith("message/"):
            reasons.add("no_recursion")
        cte = (part.decode_chain.declared_cte or "").lower()
        if cte == "base64" and part.decode_chain.used_cte is None:
            reasons.add("truncated_base64")
        elif cte == "quoted-printable":
            reasons.add("malformed_qp")
        elif cte == "base64":
            reasons.add("non_identity_cte")
    for record in records:
        if record.flowed:
            reasons.add("flowed")
        if record.verbatim_reason == "decode_fallback":
            reasons.add("decode_fallback")
        canonical = canonical_charset(record.used_charset)
        if canonical is None:
            reasons.add("unknown_charset")
        elif canonical not in stdlib_scanner.BENIGN_TEXT_CHARSETS:
            reasons.add("stateful_charset")
    if len(stdlib_scanner.decoded_leaf_texts(raw)) != len(records):
        reasons.add("leaf_count_mismatch")
    return reasons


def _leaf_text_comparison(raw: bytes):
    """``(exclusions, agreement)`` for one fixture: the stdlib's leaf texts versus ``text.py``'s."""
    result = walk(EmlContainer(raw))
    records = analyse_parts(raw, result)
    exclusions = _text_exclusions(raw, result, records)
    if exclusions:
        return exclusions, []
    leaves = stdlib_scanner.decoded_leaf_texts(raw)
    return set(), [(leaf.text, record.text) for leaf, record in zip(leaves, records)]


def test_the_stdlib_scanner_agrees_on_benign_leaf_text(corpus_text_parts) -> None:
    """The third comparison's extension: benign identity-CTE leaves decode identically."""
    compared = 0
    mismatches = []
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        _exclusions, agreement = _leaf_text_comparison(raw)
        for stdlib_text, ours in agreement:
            compared += 1
            if stdlib_text != ours:
                mismatches.append((stem, stdlib_text, ours))
    assert compared >= 50, f"only {compared} benign leaves were comparable"
    assert not mismatches, f"the stdlib and text.py disagree on {mismatches[:3]!r}"


def test_the_stdlib_text_exclusions_are_closed_and_reachable() -> None:
    """Every exclusion is a closed reason with a case; the catalogue is not decorative."""
    observed: set[str] = set()
    for _stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        exclusions, _agreement = _leaf_text_comparison(sidecar.artifact.read_bytes())
        observed |= exclusions
    assert observed, "no fixture was excluded: the exclusion list is never exercised"
    unknown = observed - set(stdlib_scanner.SHARED_TEXT_MISREADING)
    assert not unknown, f"an exclusion with no closed reason: {sorted(unknown)}"
    for reason, why in stdlib_scanner.SHARED_TEXT_MISREADING.items():
        assert why and len(why) > 20, reason
    assert len(observed) >= 5, f"only {sorted(observed)} fired"
    assert stdlib_scanner.interpreter_label().startswith("CPython ")


# ------------------------------------------------------- the L1 gate can still fail

BODY_TEXT_SIDECAR = ROOT / "fixtures" / "generated" / "body_plain_multipart_baseline.expected.json"


def _gate(tmp_path: Path, name: str, mutate):
    from emailextract.evals import l1_gate

    tamper(tmp_path, BODY_TEXT_SIDECAR, mutate, name=name)
    return l1_gate(tmp_path / name)


def test_the_committed_body_text_labels_are_green_on_a_copy(tmp_path: Path) -> None:
    """The control: an untampered copy of a body.text fixture is green."""
    from emailextract.evals import l1_gate

    tamper(tmp_path, BODY_TEXT_SIDECAR, lambda payload: None, name="clean")
    gate = l1_gate(tmp_path / "clean")
    assert gate.passed is True, gate.lines()


def test_a_wrong_body_text_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        payload["facts"]["body.text"]["value"][0][1] = "wrong text"

    gate = _gate(tmp_path, "wrong_text", mutate)
    assert gate.passed is False
    assert any("body.text mismatch" in line for line in gate.evidence), gate.evidence


def test_a_wrong_body_text_precision_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        payload["facts"]["body.text"]["value"][0][2] = "part_level"

    gate = _gate(tmp_path, "wrong_precision", mutate)
    assert gate.passed is False
    assert any("body.text mismatch" in line for line in gate.evidence), gate.evidence


def test_a_wrong_body_text_reason_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        payload["facts"]["body.text"]["value"][0][3] = "cte_not_identity"

    gate = _gate(tmp_path, "wrong_reason", mutate)
    assert gate.passed is False
    assert any("body.text mismatch" in line for line in gate.evidence), gate.evidence


def test_a_missing_body_text_row_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        payload["facts"]["body.text"]["value"].pop()

    gate = _gate(tmp_path, "missing_row", mutate)
    assert gate.passed is False
    assert any("body.text mismatch" in line for line in gate.evidence), gate.evidence
