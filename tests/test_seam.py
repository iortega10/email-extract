"""The matcher seam (design D8): the records round-trip, the stub checks the contract.

There is no matcher logic here to test beyond the stub -- the seam is frozen in Phase 0 and the
physical move (track S) is separate. What is checked is the contract: the frozen records decode
strictly, a term is searched **within** a caller-supplied closable run and never across a run
boundary (``view.gap_closing_contiguous``), a hit names the view that fired, an unknown view id is
refused, the stub's hits round-trip, a ``FlagSection`` holding a stub hit round-trips byte-for-byte,
and the walker never imports the stub.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields
from pathlib import Path

import pytest
from docextract_core.codec import CodecError

from emailextract import record_from_bytes, record_to_bytes
from emailextract.model import FLAG_SCHEMA_VERSION, FlagSection, HitLocation
from emailextract.seam import (
    MatchRules,
    MatchUnit,
    Matcher,
    MatcherView,
    Span,
    StubMatcher,
    TermHit,
    TermList,
    TextRun,
    UnitLocation,
    runs_from_texts,
    term_list_hash,
)

ROOT = Path(__file__).resolve().parent.parent
LOCATION = UnitLocation(part="1.1", view="plain", unit=0)
TERMS = TermList(terms=["revenue"])


def test_the_seam_records_round_trip_through_the_core_codec() -> None:
    runs = runs_from_texts(["Total ", "revenue"])
    records = (
        Span(start=0, end=5),
        TextRun(ordinal=0, text="Total ", span=Span(0, 6)),
        UnitLocation(part="1.1", view="plain", unit=2),
        MatchRules(whole_token=True, case_sensitive=True, match_types=["exact"]),
        TermList(terms=["revenue", "invoice"]),
        MatchUnit(view_id=MatcherView.PLAIN, text="Total revenue", runs=runs, location=LOCATION),
        TermHit(
            term="revenue",
            match_type="exact",
            view_id=MatcherView.PLAIN,
            span=Span(6, 13),
            location=LOCATION,
            term_list_hash=term_list_hash(["revenue"]),
        ),
    )
    for record in records:
        payload = record_to_bytes(record)
        assert record_from_bytes(type(record), payload) == record
        assert record_to_bytes(record_from_bytes(type(record), payload)) == payload


def test_an_undeclared_key_is_refused_strictly() -> None:
    """Strict decoding, like every other record: a key the contract does not declare raises."""
    payload = json.loads(record_to_bytes(TermList(terms=["revenue"])))
    payload["record"]["invented"] = "x"
    with pytest.raises(CodecError):
        record_from_bytes(TermList, json.dumps(payload).encode("utf-8"))


def test_the_stub_matcher_satisfies_the_protocol() -> None:
    assert isinstance(StubMatcher(), Matcher)


def test_a_hit_names_the_view_that_fired() -> None:
    unit = MatchUnit(
        view_id=MatcherView.HEADERS,
        text="Subject: revenue",
        runs=runs_from_texts(["Subject: revenue"]),
        location=UnitLocation(part="1", view="headers", unit=0),
    )
    (hit,) = StubMatcher().match(unit, TERMS)
    assert hit.view_id is MatcherView.HEADERS
    assert hit.to_flag_hit().view_id == "headers"


def test_a_run_boundary_stops_a_match_that_would_span_it() -> None:
    """``view.gap_closing_contiguous``: the same text matches as one run, not split at a boundary."""
    text = "revenue total"
    one_run = MatchUnit(
        view_id=MatcherView.PLAIN, text=text, runs=runs_from_texts([text]), location=LOCATION
    )
    spanning = TermList(terms=["revenue total"])
    assert [hit.term for hit in StubMatcher().match(one_run, spanning)] == ["revenue total"]

    split = MatchUnit(
        view_id=MatcherView.PLAIN,
        text=text,
        runs=runs_from_texts(["revenue ", "total"]),  # the caller split it at a boundary
        location=LOCATION,
    )
    assert StubMatcher().match(split, spanning) == []

    # A term that lies wholly inside one run still matches both ways.
    inside = TermList(terms=["revenue"])
    assert [hit.term for hit in StubMatcher().match(one_run, inside)] == ["revenue"]
    assert [hit.term for hit in StubMatcher().match(split, inside)] == ["revenue"]


def test_a_hit_span_lies_inside_one_run_and_names_its_view() -> None:
    unit = MatchUnit(
        view_id=MatcherView.PLAIN,
        text="Total revenue",
        runs=runs_from_texts(["Total ", "revenue"]),
        location=LOCATION,
    )
    (hit,) = StubMatcher().match(unit, TERMS)
    assert hit.span.start <= hit.span.end <= len(unit.text)
    assert unit.text[hit.span.start : hit.span.end] == "revenue"
    assert unit.run_at(hit.span.start) is unit.runs[1]
    assert hit.view_id is MatcherView.PLAIN
    assert hit.location == LOCATION


def test_the_stub_is_whole_token_exact_only() -> None:
    unit = MatchUnit(
        view_id=MatcherView.PLAIN,
        text="Revenue revenues",
        runs=runs_from_texts(["Revenue revenues"]),
        location=LOCATION,
    )
    matcher = StubMatcher()
    assert matcher.match(unit, TermList(terms=["revenue"])) == []  # no case folding
    assert [hit.term for hit in matcher.match(unit, TermList(terms=["revenues"]))] == ["revenues"]
    assert matcher.match(unit, TermList(terms=["even"])) == []  # not a substring inside a token


def test_the_stub_refuses_a_rule_it_does_not_implement() -> None:
    """No synonyms, no stems: a rule the stub cannot honour is refused, never faked."""
    unit = MatchUnit(
        view_id=MatcherView.PLAIN,
        text="revenue",
        runs=runs_from_texts(["revenue"]),
        location=LOCATION,
    )
    with pytest.raises(CodecError, match="exact only"):
        StubMatcher().match(unit, TermList(terms=["revenue"], rules=MatchRules(match_types=["stem"])))


def test_a_stub_hit_round_trips_and_so_does_a_flag_section_holding_it() -> None:
    unit = MatchUnit(
        view_id=MatcherView.PLAIN,
        text="Total revenue",
        runs=runs_from_texts(["Total revenue"]),
        location=LOCATION,
    )
    terms = TermList(terms=["revenue"])
    (hit,) = StubMatcher().match(unit, terms)

    hit_payload = record_to_bytes(hit)
    assert record_from_bytes(TermHit, hit_payload) == hit
    assert record_to_bytes(record_from_bytes(TermHit, hit_payload)) == hit_payload

    section = FlagSection(
        terms=list(terms.terms),
        term_list_hash=terms.hash(),
        matcher_version=hit.matcher_version,
        flag_schema_version=FLAG_SCHEMA_VERSION,
        hits=[hit.to_flag_hit()],
    )
    section_payload = record_to_bytes(section)
    assert record_from_bytes(FlagSection, section_payload) == section
    assert record_to_bytes(record_from_bytes(FlagSection, section_payload)) == section_payload

    empty_payload = record_to_bytes(FlagSection())
    assert record_from_bytes(FlagSection, empty_payload) == FlagSection()
    assert record_to_bytes(record_from_bytes(FlagSection, empty_payload)) == empty_payload


def test_an_unknown_view_id_is_refused_never_defaulted() -> None:
    with pytest.raises(CodecError, match="view_id"):
        MatchUnit(
            view_id="body",  # there is no such reading
            text="revenue",
            runs=runs_from_texts(["revenue"]),
            location=LOCATION,
        )
    with pytest.raises(CodecError, match="view_id"):
        TermHit(
            term="revenue",
            match_type="exact",
            view_id="body",
            span=Span(0, 7),
            location=LOCATION,
            term_list_hash=term_list_hash(["revenue"]),
        )


def test_runs_must_tile_the_text() -> None:
    with pytest.raises(CodecError, match="runs"):
        MatchUnit(
            view_id=MatcherView.PLAIN,
            text="Total revenue",
            runs=runs_from_texts(["Total "]),  # stops short of the text
            location=LOCATION,
        )
    with pytest.raises(CodecError, match="runs"):
        MatchUnit(view_id=MatcherView.PLAIN, text="x", runs=[], location=LOCATION)


def test_no_seam_record_has_an_excluded_field() -> None:
    """Flag, never filter: the seam (and the flag shape) carry no exclusion field anywhere."""
    for cls in (MatchUnit, MatchRules, TermList, TermHit, TextRun):
        assert "excluded" not in {field.name for field in fields(cls)}, cls.__name__
    for cls in (HitLocation, FlagSection):
        assert "excluded" not in {field.name for field in fields(cls)}, cls.__name__


def test_the_walker_does_not_import_the_stub() -> None:
    """The seam is a matcher-facing surface: importing the walker must not pull it in."""
    probe = (
        "import sys\n"
        "import emailextract.walk\n"
        "leaked = sorted(name for name in sys.modules if name.split('.')[0] == 'emailextract' "
        "and name.endswith('.seam'))\n"
        "print('clean' if not leaked else 'leaked:' + ','.join(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert result.stdout.strip() == "clean", result.stdout + result.stderr
