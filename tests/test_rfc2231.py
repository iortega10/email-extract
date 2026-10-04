"""Turn 1.1: RFC 2231 parameter continuations, ext-values and their recorded fallbacks (decision 5).

The rules under test: numbered continuations reassemble **by index**; a missing or duplicate
index is a recorded ``fallback`` with its closed reason; ``charset'language'`` is legal on
segment **zero** only; a ``name*`` parameter shadows the plain ``name``; an RFC 2047 word
inside a parameter is a recorded ``fallback`` (``encoded_word_in_parameter``), never decoded;
and the parser is total on hostile input (a seeded fuzz).
"""

from __future__ import annotations

import random
from pathlib import Path

from emailextract import headers as header_stage
from emailextract import rfc2231
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


def _rows(stem: str) -> list[list]:
    raw = _fixture(stem)
    region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)
    return header_stage.parameter_rows(raw, region)


def _params(text: str) -> list[rfc2231.Parameter]:
    return rfc2231.parse_parameters(text.encode("latin-1"), 0)


def test_continuations_reassemble_by_index() -> None:
    """Numbered continuations ``name*0``, ``name*1`` reassemble by index."""
    rows = _rows("rfc2231_continuations")
    assert rows == [[7, "Content-Disposition", "filename", "report-part.pdf", "decoded", None]]
    params = _params('attachment; filename*0="report-"; filename*1="part.pdf"')
    assert [p.value for p in params] == ["report-part.pdf"]


def test_a_missing_or_duplicate_index_is_an_error() -> None:
    """A gap in, or two of, a continuation index is a recorded fallback, never a guess."""
    missing = _params('attachment; filename*0="a"; filename*2="c"')
    assert missing[0].state == "fallback"
    assert missing[0].fallback_reason == "missing_continuation_index"
    duplicate = _params('attachment; filename*0="a"; filename*0="b"')
    assert duplicate[0].state == "fallback"
    assert duplicate[0].fallback_reason == "duplicate_continuation_index"


def test_a_charset_on_segment_zero_only_is_legal() -> None:
    """``charset'language'`` on segment zero is legal and percent-decoded; the fixture decodes."""
    rows = _rows("rfc2231_segment0_charset")
    assert rows == [
        [6, "Content-Type", "charset", "utf-8", "decoded", None],
        [6, "Content-Type", "name", "résumé.txt", "decoded", None],
    ]
    params = _params("text/plain; name*0*=utf-8''r%C3%A9sum%C3%A9; name*1*=.txt")
    assert params[0].value == "résumé.txt" and params[0].state == "decoded"


def test_a_star_name_shadows_the_plain_name() -> None:
    """A ``name*`` parameter shadows the plain ``name`` (the extended form wins)."""
    params = _params("attachment; filename=\"plain.txt\"; filename*=utf-8''real%2Etxt")
    assert len(params) == 1
    assert params[0].name == "filename" and params[0].value == "real.txt"
    # An empty charset on the ``*`` form is the recorded fallback (fixture).
    rows = _rows("rfc2231_empty_charset_fallback")
    assert rows == [[7, "Content-Disposition", "filename", "run.log", "fallback", "empty_charset"]]


def test_an_encoded_word_in_a_parameter_is_a_recorded_fallback() -> None:
    """An RFC 2047 word inside a parameter is a recorded fallback, never decoded."""
    params = _params('text/plain; name="=?utf-8?b?QQ==?="')
    assert params[0].state == "fallback"
    assert params[0].fallback_reason == "encoded_word_in_parameter"
    assert params[0].value == "=?utf-8?b?QQ==?="


def test_a_seeded_fuzz_of_the_parameter_parser_never_raises() -> None:
    """A seeded, bounded fuzz over mutated parameter text: the parser is total (never raises)."""
    rng = random.Random(11_2231)
    alphabet = b"*0*1=;'%\"\\ abc/=?\xff\x00\x80"
    seeds = 0
    for _ in range(400):
        length = rng.randint(0, 80)
        body = bytes(rng.choice(alphabet) for _ in range(length))
        for candidate in (body, b"attachment; " + body, b"text/plain; name" + body):
            params = rfc2231.parse_parameters(candidate, 0)
            for parameter in params:
                assert parameter.state in rfc2231.DECODE_STATES
            seeds += 1
    assert seeds == 1200
