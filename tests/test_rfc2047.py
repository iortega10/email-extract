"""Turn 1.1: RFC 2047 encoded words -- validated before decoding (decision 5).

The rules under test: a valid word decodes; an invalid word is **not** decoded, is kept
verbatim and records ``headers.encoded_word_invalid``; whitespace between adjacent encoded
words is dropped (RFC 2047 5(1)); a character split across two adjacent words joins only for
the **same** charset; unfolding removes the CRLF and keeps the whitespace (RFC 5322 2.2.3);
and the decoder never raises on hostile input (a seeded fuzz).
"""

from __future__ import annotations

import base64
import random
from pathlib import Path

from emailextract import rfc2047
from emailextract import headers as header_stage
from emailextract.container import EmlContainer
from emailextract.walk import walk

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
BUDGET = 64


def _fixture(stem: str) -> bytes:
    for directory in ("generated", "raw", "time"):
        path = FIXTURES / directory / f"{stem}.eml"
        if path.is_file():
            return path.read_bytes()
    raise AssertionError(f"no fixture {stem!r}")


def test_a_valid_word_decodes() -> None:
    """A valid B- and Q-word decodes to the text the fixture labels."""
    decoded = rfc2047.decode_encoded_words(b"=?utf-8?b?dmFsaWQg4piFIHdvcmQ=?=", max_work_units=BUDGET)
    assert decoded.text == "valid ★ word"
    assert decoded.decoded is True and decoded.invalid is False
    q = rfc2047.decode_encoded_words(b"=?iso-8859-1?q?caf=E9?=", max_work_units=BUDGET)
    assert q.text == "café"
    # The fixture's own Subject decodes to the labelled text.
    raw = _fixture("encoded_word_valid")
    region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)
    assert header_stage.decoded_rows(region) == [[2, "valid ★ word"]]


def test_an_invalid_word_records_the_gap() -> None:
    """An invalid word is kept verbatim and records the gap with the field ordinal."""
    # A B-word whose base64 is not well formed; a Q-word with a stray '='.
    bad_b = rfc2047.decode_encoded_words(b"=?utf-8?b?SGVsbG8?=", max_work_units=BUDGET)
    assert bad_b.invalid is True and bad_b.decoded is False
    assert bad_b.text == "=?utf-8?b?SGVsbG8?="
    bad_q = rfc2047.decode_encoded_words(b"=?utf-8?q?a=b?=", max_work_units=BUDGET)
    assert bad_q.invalid is True and bad_q.text == "=?utf-8?q?a=b?="
    # An unknown charset is invalid too.
    assert rfc2047.decode_encoded_words(b"=?made-up?b?QQ==?=", max_work_units=BUDGET).invalid is True
    # The fixture's Subject carries both, and the gap is recorded by the header stage.
    raw = _fixture("encoded_word_invalid")
    region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)
    assert header_stage.GAP_HEADERS_ENCODED_WORD_INVALID in region.gaps
    assert header_stage.decoded_rows(region) == []


def test_whitespace_between_encoded_words_is_dropped() -> None:
    """Whitespace between adjacent encoded words is dropped; two charsets never join."""
    raw = _fixture("encoded_word_mixed_charsets")
    region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)
    assert header_stage.decoded_rows(region) == [[2, "Mixed charsets"]]
    # Literal text between a word and non-word text is kept.
    joined = rfc2047.decode_encoded_words(
        b"=?utf-8?b?QQ==?= and =?utf-8?b?Qg==?=", max_work_units=BUDGET
    )
    assert joined.text == "A and B"


def test_a_split_character_joins_only_for_the_same_charset() -> None:
    """A multibyte character split across two same-charset words joins; two charsets do not."""
    raw = _fixture("encoded_word_split_across_fold")
    region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)
    assert header_stage.decoded_rows(region) == [[2, "★"]]
    # A '★' (E2 98 85) split across two adjacent utf-8 words joins to one character.
    same = rfc2047.decode_encoded_words(b"=?utf-8?b?4g==?= =?utf-8?b?mIU=?=", max_work_units=BUDGET)
    assert same.text == "★"
    # Different charsets never join: each decodes on its own (a lone utf-8 lead byte falls
    # back to latin-1, the iso-8859-1 byte stays é) -- the two are concatenated, not joined.
    mixed = rfc2047.decode_encoded_words(
        b"=?utf-8?b?4g==?= =?iso-8859-1?q?=E9?=", max_work_units=BUDGET
    )
    assert mixed.text == "\u00e2\u00e9"
    assert mixed.fallback_charset is True


def test_unfold_keeps_the_whitespace() -> None:
    """Unfolding removes the CRLF of a fold and keeps the WSP that followed it."""
    assert rfc2047.unfold(b"a\r\n b") == b"a b"
    assert rfc2047.unfold(b"a\r\n\tb") == b"a\tb"
    assert rfc2047.unfold(b"a\n b") == b"a b"
    assert rfc2047.unfold(b"plain") == b"plain"


def test_a_seeded_fuzz_of_the_word_decoder_never_raises() -> None:
    """A seeded, bounded fuzz: the decoder is total on hostile bytes (never raises)."""
    rng = random.Random(11_2047)
    seeds = 0
    for _ in range(400):
        length = rng.randint(0, 120)
        chunk = bytes(rng.choice(b"=?utf-8?b?qQABCD1234 \t\r\n'\x00\xff\\") for _ in range(length))
        for candidate in (chunk, b"=?" + chunk, b"=?utf-8?b?" + chunk + b"?="):
            result = rfc2047.decode_encoded_words(candidate, max_work_units=4)
            assert isinstance(result.text, str)
            seeds += 1
    assert seeds == 1200


def test_a_split_character_joins_across_spellings_of_one_charset() -> None:
    """``utf8``, ``UTF-8`` and ``utf-8`` name ONE charset: the split bytes E2 98 | 85 join (found in review)."""
    first = base64.b64encode(bytes([0xE2, 0x98])).decode()
    second = base64.b64encode(bytes([0x85])).decode()
    value = f"=?utf8?B?{first}?= =?UTF-8?B?{second}?=".encode()
    result = rfc2047.decode_encoded_words(value, max_work_units=1000)
    assert result.text == "★"
    assert result.fallback_charset is False


def test_an_rfc2231_language_suffix_on_the_charset_is_accepted() -> None:
    """RFC 2231 section 5: ``=?UTF-8*en?Q?hi?=`` is a valid word, not a refused one (found in review)."""
    result = rfc2047.decode_encoded_words(b"=?UTF-8*en?Q?hi?=", max_work_units=1000)
    assert (result.text, result.decoded, result.invalid) == ("hi", True, False)
    bare = rfc2047.decode_encoded_words(b"=?*en?Q?hi?=", max_work_units=1000)
    assert bare.invalid is True and bare.decoded is False
