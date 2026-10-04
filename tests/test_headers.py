"""Turn 1.1: the header region -- field paragraphs, folds, raw spans, the kind table, gaps.

The rules under test (decision 4, D2, the "Turn 1.1" declaration): fields are ordered with
duplicates kept; an obs-fold is **one** field; every field carries its verbatim byte spans;
the region ends at the first empty line; a malformed line **fails open**; a leading BOM or
mbox ``From `` line is a tolerated **prelude** whose first real header is still read; a
second unique-named field records ``headers.duplicate_header``; 8-bit bytes render
verbatim; lookup is by the lowercased name while display keeps its case; a lone CR in the
header region records ``body.lone_cr_line_terminator``; the tolerance bumps
``EMAIL_PARSER_VERSION``; and the two new gaps are falsifiable with the anti-vacuity triple.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emailextract import headers as header_stage
from emailextract import walk as walk_module
from emailextract.container import EmlContainer
from emailextract.evals import l1_gate
from emailextract.versions import EMAIL_PARSER_VERSION
from emailextract.walk import leading_prelude, walk

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

GAP_DUP = header_stage.GAP_HEADERS_DUPLICATE_HEADER
GAP_BOM = header_stage.GAP_HEADERS_LEADING_BOM
GAP_MBOX = header_stage.GAP_HEADERS_MBOX_FROM_LINE
GAP_LONE_CR = header_stage.GAP_BODY_LONE_CR_LINE_TERMINATOR


def _fixture(stem: str) -> bytes:
    for directory in ("generated", "raw", "time"):
        path = FIXTURES / directory / f"{stem}.eml"
        if path.is_file():
            return path.read_bytes()
    raise AssertionError(f"no fixture {stem!r}")


def _region(stem: str):
    raw = _fixture(stem)
    return raw, header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=64)


def test_field_paragraphs_keep_order_and_duplicates() -> None:
    """Fields are ordered, duplicates kept, identity by ordinal (D2)."""
    _raw, region = _region("duplicate_header_mime_version")
    names = [item.name for item in region.fields]
    assert names == ["From", "To", "Subject", "Date", "Message-ID", "MIME-Version", "MIME-Version", "Content-Type"]
    # Ordinals are the identity: two MIME-Version fields, ordinals 5 and 6, not name-keyed.
    assert [item.ordinal for item in region.fields] == list(range(len(region.fields)))


def test_an_obs_fold_is_one_field() -> None:
    """A continuation line starting with SP/HTAB belongs to the previous field, as one field."""
    raw = _fixture("rfc2047_folded_duplicate_received")
    result = walk(EmlContainer(raw))
    region = header_stage.header_region(raw, result, max_work_units=64)
    subjects = [item for item in region.fields if item.name == "Subject"]
    assert len(subjects) == 1, "the folded Subject must be one field"
    folded = subjects[0]
    # The fold (CRLF + SP) is kept in the verbatim value, and the raw span covers both lines.
    assert "\r\n " in folded.raw_value
    assert raw[folded.raw_span.offset : folded.raw_span.end] == (
        b"Subject: =?utf-8?b?SGVsbG8g4piF?=\r\n =?utf-8?b?IGZvbGRlZCBzdWJqZWN0?=\r\n"
    )


def test_each_field_carries_its_raw_byte_span() -> None:
    """name_span / value_span / raw_span slice the raw bytes to what they claim."""
    raw, region = _region("headers_plain_baseline")
    assert region.fields
    for item in region.fields:
        assert raw[item.name_span.offset : item.name_span.end] == item.name.encode("latin-1")
        assert raw[item.value_span.offset : item.value_span.end] == item.raw_value.encode("latin-1")
        assert item.value_span.offset == item.name_span.end + 1  # starts just after the colon
        assert item.value_span.offset - item.name_span.offset == len(item.name) + 1
        assert item.raw_span.offset <= item.name_span.offset
        assert item.value_span.end <= item.raw_span.end


def test_the_header_region_ends_at_the_first_empty_line() -> None:
    """The header region is the bytes before the first empty line; the body follows."""
    raw, region = _region("headers_plain_baseline")
    last = region.fields[-1]
    assert region.fields[0].raw_span.offset == 0
    # The body begins after the empty line that closes the header region.
    assert raw[last.raw_span.end : last.raw_span.end + 2] == b"\r\n"
    assert b"Baseline body." in raw[last.raw_span.end :]


def test_a_malformed_line_fails_open() -> None:
    """A non-field, non-fold line is its own paragraph; the region does not end (D2)."""
    raw, region = _region("malformed_mime")
    malformed = [item for item in region.fields if item.parse_status == "unknown"]
    assert len(malformed) == 1 and malformed[0].name == ""
    assert malformed[0].raw_value == "not a header line"
    # The fields after it are still parsed (fail-open), not swallowed into the body.
    assert header_stage.fields_named(region.fields, "X-After"), "the region must fail open"


def test_leading_bom_is_a_prelude_and_the_first_field_is_read() -> None:
    """A UTF-8 BOM is its own prelude region; the first real header is read."""
    raw = _fixture("leading_utf8_bom")
    assert raw[:3] == b"\xef\xbb\xbf"
    result = walk(EmlContainer(raw))
    preludes = [region for region in result.regions if region.kind == "prelude"]
    assert [(region.span.offset, region.span.length) for region in preludes] == [(0, 3)]
    # The regions still tile: prelude then headers then body.
    assert [region.kind for region in result.regions] == ["prelude", "headers", "body"]
    region = header_stage.header_region(raw, result, max_work_units=64)
    assert region.prelude == [GAP_BOM]
    assert region.fields[0].name == "From", "the BOM must not swallow the first real header"


def test_mbox_from_line_is_a_prelude_and_the_first_field_is_read() -> None:
    """An mbox ``From `` line is its own prelude region; the first real header is read."""
    raw = _fixture("mbox_from_line_at_zero")
    assert raw.startswith(b"From ")
    result = walk(EmlContainer(raw))
    preludes = [region for region in result.regions if region.kind == "prelude"]
    assert len(preludes) == 1 and preludes[0].span.offset == 0
    assert raw[preludes[0].span.offset : preludes[0].span.end].startswith(b"From ")
    region = header_stage.header_region(raw, result, max_work_units=64)
    assert region.prelude == [GAP_MBOX]
    assert region.fields[0].name == "From", "the mbox line must not become the first field"


def test_a_duplicate_header_records_the_gap() -> None:
    """A second unique-named field records the gap; a repeatable name never fires it."""
    _raw, mime = _region("duplicate_header_mime_version")
    assert GAP_DUP in mime.gaps
    _raw, ctype = _region("duplicate_content_type_header")
    assert GAP_DUP in ctype.gaps
    # Received repeats by design (RFC 5322 3.6.5): it is not unique and never fires it.
    _raw, received = _region("rfc2047_folded_duplicate_received")
    assert [item.name for item in received.fields].count("Received") == 3
    assert GAP_DUP not in received.gaps


def test_eight_bit_header_bytes_render_verbatim() -> None:
    """8-bit bytes render verbatim (latin-1 view); a NUL in a name is recorded, never raised."""
    raw, region = _region("header_8bit_raw_bytes")
    eightbit = header_stage.fields_named(region.fields, "X-8bit")[0]
    assert eightbit.raw_value == " caf\xe9 \x81 end"
    assert raw[eightbit.value_span.offset : eightbit.value_span.end] == b" caf\xe9 \x81 end"
    _raw, nul = _region("nul_in_header_name")
    assert any(item.name == "" and item.parse_status == "unknown" for item in nul.fields)


def test_mixed_case_names_are_lowercased_for_lookup_not_for_display() -> None:
    """Lookup is by the lowercased name; the displayed name keeps its case."""
    _raw, region = _region("mixed_case_header_and_param_names")
    displayed = [item.name for item in region.fields]
    assert displayed[:4] == ["FROM", "To", "SUBJECT", "DATE"]
    assert header_stage.fields_named(region.fields, "from")[0].name == "FROM"
    assert header_stage.fields_named(region.fields, "From")[0].name == "FROM"
    assert header_stage.classify("FROM") == "address_list"
    assert header_stage.classify("MiMe-VeRsIoN") == "text"


def test_the_lone_cr_gap_is_recorded_in_the_header_region() -> None:
    """A lone CR in the header region records the gap (decision 17 keeps the line model)."""
    _raw, region = _region("lone_cr_in_header_region")
    assert GAP_LONE_CR in region.gaps
    # It rides this stage's own gaps, never the walker's Phase 0 ``part.gaps`` channel.
    result = walk(EmlContainer(_fixture("lone_cr_in_header_region")))
    assert result.parts[0].gaps == []


def test_the_walker_tolerance_bumps_the_parser_version() -> None:
    """The tolerance is a versioned walker behaviour change: EMAIL_PARSER_VERSION is 2."""
    assert EMAIL_PARSER_VERSION == "2"
    # The helper both the walker and the header stage use.
    assert leading_prelude(b"\xef\xbb\xbfFrom: a\r\n", 0) == (3, 0)
    assert leading_prelude(b"From a@b Tue\r\nFrom: x\r\n", 0) == (0, 14)
    assert leading_prelude(b"From: x\r\n", 0) == (0, 0)  # a ``From:`` field is not mbox
    assert leading_prelude(b"From a@b no terminator", 0) == (0, 0)  # unterminated: not mbox


def test_gap_falsification_duplicate_header_and_leading_bom(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each new gap flips the L1 gate, with the anti-vacuity triple (patched, reached, differs)."""
    reached = {"duplicate": 0, "prelude": 0}

    real_conflicts = header_stage._unique_conflicts

    def naive_conflicts(fields):
        reached["duplicate"] += 1
        return []

    monkeypatch.setattr(header_stage, "_unique_conflicts", naive_conflicts)
    gate = l1_gate()
    assert reached["duplicate"] > 0, "the duplicate mutant's patch was never reached (vacuous)"
    assert gate.passed is False
    assert any(
        "duplicate_header_mime_version" in line and "gaps.later" in line
        for line in gate.evidence
    ), gate.evidence

    monkeypatch.setattr(header_stage, "_unique_conflicts", real_conflicts)

    real_prelude = header_stage.leading_prelude

    def naive_prelude(raw, start):
        reached["prelude"] += 1
        return 0, 0

    monkeypatch.setattr(header_stage, "leading_prelude", naive_prelude)
    gate = l1_gate()
    assert reached["prelude"] > 0, "the prelude mutant's patch was never reached (vacuous)"
    assert gate.passed is False
    assert any(
        "leading_utf8_bom" in line and "gaps.later" in line for line in gate.evidence
    ), gate.evidence

    monkeypatch.setattr(header_stage, "leading_prelude", real_prelude)
    assert l1_gate().passed is True, "restoring the rules must restore green"

    # The tag the emitter uses is the one the walker module owns (they must agree).
    assert walk_module.leading_prelude is real_prelude


def test_a_seeded_fuzz_of_the_header_stage_never_raises() -> None:
    """A seeded, bounded fuzz over mutated header regions: the stage is total on bytes."""
    import random

    rng = random.Random(11_1001)
    sources = [
        _fixture("headers_plain_baseline"),
        _fixture("duplicate_header_mime_version"),
        _fixture("lone_cr_in_header_region"),
        _fixture("leading_utf8_bom"),
        _fixture("mixed_case_header_and_param_names"),
    ]
    seeds = 0
    for source in sources:
        for _ in range(120):
            data = bytearray(source)
            for _ in range(rng.randint(1, 6)):
                op = rng.randint(0, 4)
                if not data:
                    break
                index = rng.randrange(len(data))
                if op == 0:  # byte flip
                    data[index] = rng.choice(b"\r\n: \t=\xff\x00?<>")
                elif op == 1:  # truncate
                    del data[index:]
                elif op == 2:  # duplicate a chunk
                    data[index:index] = bytes(rng.choice([b"\r\n", b" ", b"\t", b":", b"From ", b"=?utf-8?b?"]))
                elif op == 3:  # swap two chunks
                    cut = rng.randrange(len(data))
                    data = bytearray(bytes(data[cut:]) + bytes(data[:cut]))
                else:  # a repeated fold
                    data[index:index] = b"\r\n "
            raw = bytes(data)
            result = walk(EmlContainer(raw))
            region = header_stage.header_region(raw, result, max_work_units=64)
            for item in region.fields:
                assert raw[item.name_span.offset : item.name_span.end] == item.name.encode("latin-1")
            seeds += 1
    assert seeds == 600

