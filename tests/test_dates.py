"""Turn 1.3: the package's own RFC 5322 3.3 date-time parser (``emailextract/dates``).

The rules under test (decision 4, D2/D15, the "Turn 1.3" declaration): a Date field's value
bytes are one date-time; the zone has **three recorded states** (``zone_stated`` /
``zone_stated_minus_zero`` / ``zone_absent``) and ``-0000`` is never read as ``+0000``; an
optional day-name is accepted and **never** checked against the date; the obs-zone table (and
the military letters, which carry no reliable offset) is applied at the one legal zone
position; an out-of-range offset is recorded, not repaired; an impossible date returns a closed
reason and is **never** an epoch; a leap second is kept as ``:60`` and never rolled silently;
the parser never raises, is **linear**, and maps onto the facts document's ``headers.date`` row
(including the single absent row a missing Date is typed as).

Every failure names the fixture, the fact, the gap id and the reason id. The 10 tests the turn
declared are here; the extra tests are declared in the turn's block too.
"""

from __future__ import annotations

import dataclasses
import random
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import sidecar_copy  # noqa: E402
from support import stdlib_scanner  # noqa: E402

from emailextract import dates as date_stage  # noqa: E402
from emailextract import headers as header_stage  # noqa: E402
from emailextract.container import EmlContainer  # noqa: E402
from emailextract.evals import l1 as oracle  # noqa: E402
from emailextract.evals import l1_gate  # noqa: E402
from emailextract.walk import walk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
BUDGET = 64

GAP_NO_DATE = date_stage.GAP_HEADERS_NO_DATE
GAP_INVALID_DATE = date_stage.GAP_HEADERS_INVALID_DATE
GAP_DATE_NO_ZONE = date_stage.GAP_HEADERS_DATE_NO_ZONE

_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


def _fixture(stem: str) -> bytes:
    for directory in ("generated", "raw", "time"):
        path = FIXTURES / directory / f"{stem}.eml"
        if path.is_file():
            return path.read_bytes()
    raise AssertionError(f"no fixture {stem!r}")


def _all_fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*/*.eml"))


def _region(stem: str):
    raw = _fixture(stem)
    return raw, header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)


def _rows(stem: str) -> list[list[object]]:
    _raw, region = _region(stem)
    return header_stage.date_rows(region)


def _parse(value):
    return date_stage.parse_date(value)


def _is_well_formed_utc(text: str) -> bool:
    """A well-formed RFC 3339 instant in ``+00:00`` (a leap second's ``:60`` is allowed)."""
    if not _RFC3339_UTC.match(text):
        return False
    second = int(text[17:19])
    return second <= 60


# ----------------------------------------------------------------- the declared 10


def test_a_stated_zone_is_recorded_with_its_offset() -> None:
    """A numeric zone is ``zone_stated`` with its offset token and the RFC 3339 instant (D2)."""
    assert _rows("date_stated_zone") == [
        [3, " Tue, 4 Mar 2025 08:05:00 +0000", "zone_stated", "+0000", "2025-03-04T08:05:00+00:00"]
    ]

    # Any numeric offset is applied to the stated fields for the UTC instant.
    record = _parse(b"Mon, 3 Mar 2025 12:00:00 +0230")
    assert (record.zone_state, record.offset) == ("zone_stated", "+0230")
    assert record.utc == "2025-03-03T09:30:00+00:00"

    record = _parse(b"Mon, 3 Mar 2025 12:00:00 -0800")
    assert (record.zone_state, record.offset) == ("zone_stated", "-0800")
    assert record.utc == "2025-03-03T20:00:00+00:00"


def test_minus_zero_is_not_plus_zero() -> None:
    """``-0000`` is its own state, never ``+0000`` (the offset token is kept, D2)."""
    assert _rows("date_minus_zero") == [
        [
            3,
            " Tue, 4 Mar 2025 08:05:00 -0000",
            "zone_stated_minus_zero",
            "-0000",
            "2025-03-04T08:05:00+00:00",
        ]
    ]

    minus = _parse(b" Tue, 4 Mar 2025 08:05:00 -0000")
    plus = _parse(b" Tue, 4 Mar 2025 08:05:00 +0000")
    assert minus.zone_state != plus.zone_state, "the two states must not collapse"
    assert minus.zone_state == "zone_stated_minus_zero"
    assert plus.zone_state == "zone_stated"
    assert minus.offset == "-0000" and plus.offset == "+0000"


def test_an_absent_zone_is_zone_absent() -> None:
    """A value with no zone token is ``zone_absent``: offset null, instant unknown (D2/D15)."""
    record = _parse(b" Tue, 4 Mar 2025 08:05:00")
    assert record.zone_state == "zone_absent"
    assert record.offset is None
    assert record.utc is None
    assert record.reason_id == GAP_DATE_NO_ZONE
    assert record.gap == GAP_DATE_NO_ZONE
    assert record.utc_value() == ["unknown", GAP_DATE_NO_ZONE]

    # No Date field at all is the *absent* row the labels type: null ordinal/raw, no_date.
    absent = _parse(None)
    assert absent.as_fact_row(None) == [None, None, "zone_absent", None, ["unknown", GAP_NO_DATE]]
    assert _rows("date_absent") == [absent.as_fact_row(None)]


def test_an_optional_day_name_is_accepted() -> None:
    """A three-letter day-name plus comma may be present or absent, and is never checked."""
    without = _parse(b"4 Mar 2025 08:05:00 +0000")
    with_name = _parse(b"Tue, 4 Mar 2025 08:05:00 +0000")
    assert without.utc == with_name.utc == "2025-03-04T08:05:00+00:00"
    assert with_name.day_name == "Tue"
    assert without.day_name is None

    # 4 Mar 2025 is a Tuesday; a day-name that disagrees is recorded as stated, not repaired
    # and not rejected (the weekday is never computed).
    wrong = _parse(b"Sat, 4 Mar 2025 08:05:00 +0000")
    assert wrong.utc == "2025-03-04T08:05:00+00:00"
    assert wrong.day_name == "Sat"

    # The comma is part of the grammar: without it the first word is read as the day.
    assert _parse(b"Tue 4 Mar 2025 08:05:00 +0000").utc is None


def test_the_obs_zone_table_is_applied() -> None:
    """RFC 5322 4.3 obs-zones map to their offsets; a military letter carries no offset."""
    table = {
        b"UT": "+0000",
        b"GMT": "+0000",
        b"EST": "-0500",
        b"EDT": "-0400",
        b"CST": "-0600",
        b"CDT": "-0500",
        b"MST": "-0700",
        b"MDT": "-0600",
        b"PST": "-0800",
        b"PDT": "-0700",
    }
    for name, offset in table.items():
        record = _parse(b"Tue, 4 Mar 2025 08:05:00 " + name)
        assert (record.zone_state, record.offset) == ("zone_stated", offset), name
        assert record.ok, name

    assert set(date_stage.OBS_ZONES) == {name.decode().lower() for name in table}

    # A military letter has no reliable offset (RFC 5322 4.3: treated as -0000), so it is the
    # minus-zero state, never UTC (Turn 1.3 review decision).
    for letter in (b"Z", b"A", b"N", b"z"):
        record = _parse(b"Tue, 4 Mar 2025 08:05:00 " + letter)
        assert record.zone_state == "zone_stated_minus_zero", letter
        assert record.offset == "-0000", letter
        assert record.utc == "2025-03-04T08:05:00+00:00", letter
    # J/j are not military zones.
    assert _parse(b"Tue, 4 Mar 2025 08:05:00 J").utc is None


def test_an_offset_out_of_range_is_recorded_not_repaired() -> None:
    """A ``+9960`` offset keeps its token and state, and its instant is unknown -- no gap."""
    assert _rows("date_offset_out_of_range") == [
        [
            3,
            " Tue, 4 Mar 2025 08:05:00 +9960",
            "zone_stated",
            "+9960",
            ["unknown", GAP_INVALID_DATE],
        ]
    ]
    record = _parse(b" Tue, 4 Mar 2025 08:05:00 +9960")
    assert record.utc is None
    assert record.reason_id == GAP_INVALID_DATE
    assert record.gap is None, "the design names no registry id for an out-of-range offset"

    # The design's limit is MM 00-59 (so |HHMM| <= 9959); an obs- HH is still accepted.
    assert _parse(b"Mon, 3 Mar 2025 12:00:00 +9959").ok
    assert _parse(b"Mon, 3 Mar 2025 12:00:00 +0060").utc is None
    # A year-1 date with a +9959 offset lands before 0001, outside the representable range:
    # the value is a well-formed date-time, so the instant is unknown and no gap is invented.
    edge = _parse(b"1 Jan 0001 00:00:00 +9959")
    assert edge.utc is None and edge.reason_id == GAP_INVALID_DATE and edge.gap is None


def test_an_invalid_date_returns_a_reason_never_an_epoch() -> None:
    """An impossible date never becomes an epoch or ``now``: it carries a closed reason (D2)."""
    assert _rows("date_invalid") == [
        [3, " not a date at all", "zone_absent", None, ["unknown", GAP_INVALID_DATE]]
    ]

    for value in (
        b"not a date at all",
        b"31 Feb 2025 08:05:00 +0000",  # an impossible day
        b"32 Mar 2025 08:05:00 +0000",  # a day out of any month
        b"4 Foo 2025 08:05:00 +0000",  # month is not a month
        b"Tue, 4 Mar 2025 24:05:00 +0000",  # hour out of range
        b"Tue, 4 Mar 2025 08:60:00 +0000",  # minute out of range
        b"Tue, 4 Mar 2025 08:05:61 +0000",  # second out of range
        b"Tue, 4 Mar 2025 08:05:00 +0000 trailing",  # a left-over significant token
        b"",
    ):
        record = _parse(value)
        assert record.utc is None, value
        assert record.reason_id == GAP_INVALID_DATE, value
        assert record.gap == GAP_INVALID_DATE, value
        assert record.utc_value() == ["unknown", GAP_INVALID_DATE], value

    # 29 Feb exists only in a Gregorian leap year; 1900 and 2100 are not leap, 2000 and 2024 are.
    assert _parse(b"29 Feb 2024 00:00:00 +0000").ok
    assert _parse(b"29 Feb 2000 00:00:00 +0000").ok
    assert _parse(b"29 Feb 1900 00:00:00 +0000").utc is None
    assert _parse(b"29 Feb 2100 00:00:00 +0000").utc is None


def test_the_parser_never_raises_on_input_content() -> None:
    """Total over any bytes: NUL, lone CR/LF, 8-bit, huge runs and non-ASCII digits included."""
    for value in (
        b"",
        b"\x00" * 200,
        b"\x00\x01\x02",
        b"\r",
        b"\n",
        b"\r\n\r\n",
        b"\xff" * 50,
        b"\xd9\xa1\xd9\xa2",  # ARABIC-INDIC DIGIT THREE as UTF-8 bytes
        b"(" * 500,
        b"(" * 500 + b")" * 499,
        b")" * 100,
        b"\xff" * 200 + b" EST",
        b"9" * 10_000,
        b"+0000",
        b"-",
        b":",
        b",",
        b" ",
        b"Tue, 4 Mar 2025 08:05:00 +0000\x00trailing",
    ):
        record = _parse(value)
        assert isinstance(record, date_stage.DateRecord), value
        utc = record.utc_value()
        if isinstance(utc, list):
            assert utc[0] == "unknown" and utc[1] in date_stage.DATE_GAPS, value
        else:
            assert _is_well_formed_utc(utc), (value, utc)


def test_a_reason_id_where_parsedate_to_datetime_raises() -> None:
    """Wherever the stdlib raises or returns a naive datetime, the own parser names a reason.

    ``email.utils.parsedate_to_datetime`` raises on an invalid value and on a leap second, and
    returns a **naive** datetime for ``-0000`` and a missing zone. In each of those the own
    parser must return a record with a closed reason id or the correct zone state -- never an
    exception, and never an epoch. Over every Date field of every fixture.
    """
    compared = 0
    exercised = 0
    for path in _all_fixtures():
        for _name, value in stdlib_scanner.date_fields(path.read_bytes()):
            compared += 1
            stdlib = stdlib_scanner.stdlib_date(value)
            if stdlib.error is None and not stdlib.naive:
                continue
            exercised += 1
            record = _parse(value)  # never raises
            assert isinstance(record, date_stage.DateRecord), path.stem
            if stdlib.error is not None:
                assert record.utc is None, path.stem
                assert record.reason_id in date_stage.DATE_GAPS, path.stem
            else:  # a naive datetime: -0000 or a missing zone
                # The state is what must not be lost: minus-zero or absent. A -0000 keeps the
                # instant a +0000 would give (there is no local time to apply); a missing zone
                # has none -- and neither is ever the epoch.
                assert record.zone_state in ("zone_stated_minus_zero", "zone_absent"), path.stem
                if record.utc is None:
                    assert record.reason_id in date_stage.DATE_GAPS, path.stem
                else:
                    assert record.zone_state == "zone_stated_minus_zero", path.stem
                    assert record.utc != "1970-01-01T00:00:00+00:00", path.stem
    assert compared >= 80, "the comparison would be vacuous"
    assert exercised >= 2, "no stdlib raise/naive case: the property is not exercised"
    print(f"stdlib parity checked over {compared} Date field(s), {exercised} raising/naive")


def test_the_stdlib_date_diff_is_recorded_only(capsys) -> None:
    """Print the stdlib-versus-own date diff per fixture; assert no gate on it.

    The stdlib rewrites ``-0000`` to offset 0, returns a naive datetime for a missing zone,
    accepts an offset the design's limit rejects and raises where the design declines with a
    reason, so the diff is **advisory** -- printed for the record, never asserted against (the
    stdlib is wrong here by design). The only assertions are that the diff was computed over the
    whole corpus (not vacuous) and that the closed exclusion list is present.
    """
    table: dict[str, list[tuple[str, str, str]]] = {}
    total = 0
    for path in _all_fixtures():
        for name, value in stdlib_scanner.date_fields(path.read_bytes()):
            total += 1
            record = _parse(value)
            own_utc = record.utc if record.utc is not None else f"unknown({record.reason_id})"
            stdlib = stdlib_scanner.stdlib_date(value)
            if stdlib.error is not None:
                other = f"raised({stdlib.error.split(':')[0]})"
            elif stdlib.naive:
                other = f"naive({stdlib.moment})"
            else:
                other = stdlib.moment or "none"
            if own_utc != other:
                table.setdefault(path.stem, []).append((name, own_utc, other))

    print(f"advisory date diff (own parser vs email.utils) -- {stdlib_scanner.interpreter_label()}:")
    print(f"  Date field(s) compared: {total}")
    print(f"  fixture(s) with a disagreement: {len(table)}")
    for stem in sorted(table):
        for name, own, other in table[stem]:
            print(f"    {stem} {name}: own={own!r} stdlib={other!r}")
    print("  closed reasons the stdlib reads a date differently (never gated):")
    for reason, text in sorted(stdlib_scanner.SHARED_DATE_MISREADING.items()):
        print(f"    {reason}: {text}")

    assert total >= 80, "the advisory diff was not computed over the corpus"
    assert {"minus_zero_read_as_plus_zero", "no_zone_is_naive"} <= set(
        stdlib_scanner.SHARED_DATE_MISREADING
    )


# --------------------------------------------------------------- added to the declaration


def test_the_rfc5322_examples_and_obs_forms_parse() -> None:
    """RFC 5322 3.3 shapes, the obs- forms of 4.3, and the examples, all by hand."""
    examples = {
        b"Fri, 21 Nov 1997 09:55:06 -0600": "1997-11-21T15:55:06+00:00",
        b"Tue, 1 Jul 2003 10:52:37 +0200": "2003-07-01T08:52:37+00:00",
        b"Fri, 21 Nov 1997 09:55:06 -0000": "1997-11-21T09:55:06+00:00",
        b"Fri, 21 Nov 1997 09:55:06 GMT": "1997-11-21T09:55:06+00:00",
        b"21 Nov 1997 09:55:06 +0000": "1997-11-21T09:55:06+00:00",
        b"21 Nov 97 09:55:06 +0000": "1997-11-21T09:55:06+00:00",
        b"21 Nov 97 09:55 +0000": "1997-11-21T09:55:00+00:00",
        b" 21 Nov 1997 09:55:06 +0000": "1997-11-21T09:55:06+00:00",
    }
    for value, expected in examples.items():
        record = _parse(value)
        assert record.utc == expected, (value, record.utc)

    # The RFC 5322 4.3 obs-year rules: 00-49 -> 2000-2049, 50-99 and any 3-digit -> +1900.
    assert _parse(b"1 Jan 00 00:00:00 +0000").utc == "2000-01-01T00:00:00+00:00"
    assert _parse(b"1 Jan 49 00:00:00 +0000").utc == "2049-01-01T00:00:00+00:00"
    assert _parse(b"1 Jan 50 00:00:00 +0000").utc == "1950-01-01T00:00:00+00:00"
    assert _parse(b"1 Jan 99 00:00:00 +0000").utc == "1999-01-01T00:00:00+00:00"
    assert _parse(b"1 Jan 125 00:00:00 +0000").utc == "2025-01-01T00:00:00+00:00"
    assert _parse(b"1 Jan 00 00:00:00 +0000").obs_year is True
    assert _parse(b"1 Jan 2025 00:00:00 +0000").obs_year is False
    # Year 0000 is not a Gregorian year.
    assert _parse(b"1 Jan 0000 00:00:00 +0000").utc is None
    # A 1-digit year is not the RFC's 4- or obs- form.
    assert _parse(b"1 Jan 5 00:00:00 +0000").utc is None


def test_a_leap_second_is_recorded_not_silently_rolled() -> None:
    """Second 60 is legal (RFC 5322 3.3): it is kept as ``:60``, flagged, never rolled."""
    record = _parse(b"Tue, 4 Mar 2025 08:05:60 +0000")
    assert record.leap_second is True
    assert record.utc == "2025-03-04T08:05:60+00:00"

    ordinary = _parse(b"Tue, 4 Mar 2025 08:05:59 +0000")
    assert ordinary.leap_second is False
    assert ordinary.utc == "2025-03-04T08:05:59+00:00"

    # The offset still applies at minute resolution, and the :60 stays.
    shifted = _parse(b"Tue, 4 Mar 2025 08:05:60 +0100")
    assert shifted.utc == "2025-03-04T07:05:60+00:00"
    # Second 61 is not a leap second; it is invalid.
    assert _parse(b"Tue, 4 Mar 2025 08:05:61 +0000").utc is None


def test_cfws_and_comments_do_not_split_or_supply_the_zone() -> None:
    """A fold is skipped, a trailing comment is not the zone, and a comment is never a zone."""
    folded = _parse(b" Tue, 4\r\n Mar 2025 08:05:00 +0000")
    assert folded.utc == "2025-03-04T08:05:00+00:00"

    trailing = _parse(b"Tue, 4 Mar 2025 08:05:00 +0000 (UTC)")
    assert (trailing.zone_state, trailing.offset) == ("zone_stated", "+0000")
    assert trailing.utc == "2025-03-04T08:05:00+00:00"

    comment_as_zone = _parse(b"Tue, 4 Mar 2025 08:05:00 (EST)")
    assert comment_as_zone.zone_state == "zone_absent"
    assert comment_as_zone.reason_id == GAP_DATE_NO_ZONE

    nested = _parse(b"Tue, 4 Mar 2025 08:05:00 (a (b) c) +0000")
    assert (nested.zone_state, nested.offset) == ("zone_stated", "+0000")

    # Folding inside a token is not a place the RFC allows FWS, so it is not a date.
    assert _parse(b"Tue, 4 Mar 2025 08:\r\n05:00 +0000").utc is None


def test_the_calendar_table_matches_hand_checked_dates() -> None:
    """``_days_from_civil`` against 40 hand-checked dates, and ``_civil_from_days`` inverts it."""
    table = (
        (1, 1, 1, -719162),
        (1, 1, 2, -719161),
        (1, 12, 31, -718798),
        (2, 1, 1, -718797),
        (4, 2, 28, -718009),
        (4, 2, 29, -718008),
        (4, 3, 1, -718007),
        (100, 2, 28, -682945),
        (100, 3, 1, -682944),
        (400, 2, 29, -573372),
        (1582, 10, 15, -141427),
        (1899, 12, 31, -25568),
        (1900, 1, 1, -25567),
        (1900, 2, 28, -25509),
        (1900, 3, 1, -25508),
        (1901, 1, 1, -25202),
        (1900, 12, 31, -25203),
        (1969, 12, 31, -1),
        (1970, 1, 1, 0),
        (1970, 1, 2, 1),
        (1970, 12, 31, 364),
        (1971, 1, 1, 365),
        (1999, 12, 31, 10956),
        (2000, 1, 1, 10957),
        (2000, 2, 28, 11015),
        (2000, 2, 29, 11016),
        (2000, 3, 1, 11017),
        (2000, 12, 31, 11322),
        (2001, 1, 1, 11323),
        (2024, 2, 28, 19781),
        (2024, 2, 29, 19782),
        (2024, 3, 1, 19783),
        (2025, 3, 4, 20151),
        (2025, 12, 31, 20453),
        (2026, 1, 1, 20454),
        (2099, 12, 31, 47481),
        (2100, 1, 1, 47482),
        (2100, 2, 28, 47540),
        (2100, 3, 1, 47541),
        (9999, 12, 31, 2932896),
    )
    assert len(table) == 40
    for year, month, day, days in table:
        assert date_stage._days_from_civil(year, month, day) == days, (year, month, day)
        assert date_stage._civil_from_days(days) == (year, month, day), (year, month, day)

    # Every day in a two-year window inverts, and the sequence is strictly +1 a day.
    previous = None
    for offset in range(-800, 800):
        civil = date_stage._civil_from_days(offset)
        assert date_stage._days_from_civil(*civil) == offset
        if previous is not None:
            assert offset == previous + 1
        previous = offset


def test_the_date_row_maps_onto_the_facts_row_shape() -> None:
    """The frozen record projects onto ``headers.date``'s five members, with its invariants."""
    record = _parse(b" Tue, 4 Mar 2025 08:05:00 +0000")
    row = record.as_fact_row(3)
    assert row == [
        record.as_fact_row(3)[0],
        record.raw.decode("latin-1"),
        record.zone_state,
        record.offset,
        record.utc,
    ]
    assert len(row) == 5
    assert set(date_stage.ZONE_STATES) == {"zone_stated", "zone_stated_minus_zero", "zone_absent"}
    assert date_stage.DATE_GAPS == (GAP_NO_DATE, GAP_INVALID_DATE, GAP_DATE_NO_ZONE)

    # The record refuses a state outside the closed set, a reason outside the closed set, a
    # stated zone with no offset, and an instant beside a reason.
    with pytest.raises(ValueError):
        date_stage.DateRecord(b"x", "guessed", "+0000", None, GAP_INVALID_DATE, GAP_INVALID_DATE)
    with pytest.raises(ValueError):
        date_stage.DateRecord(b"x", "zone_absent", None, None, "headers.something_else", None)
    with pytest.raises(ValueError):
        date_stage.DateRecord(b"x", "zone_stated", None, None, GAP_INVALID_DATE, GAP_INVALID_DATE)
    with pytest.raises(ValueError):
        date_stage.DateRecord(b"x", "zone_stated", "+0000", "2025-03-04T08:05:00+00:00", GAP_INVALID_DATE, None)
    with pytest.raises(TypeError):
        _parse("not bytes")  # a str is a caller bug, not input content


def test_a_mutation_flips_the_gate_for_every_date_fact(tmp_path) -> None:
    """A wrong sidecar for either date fact fails the L1 gate, naming the fixture and the fact.

    Four mutations over the two live facts: a wrong offset, a wrong UTC instant, a wrong
    zone_state, and a missing gap id.
    """
    zoned = FIXTURES / "generated" / "date_stated_zone.expected.json"
    absent = FIXTURES / "generated" / "date_absent.expected.json"

    def date_row(payload):
        return payload["facts"]["headers.date"]["value"][0]

    def wrong_offset(payload):
        date_row(payload)[3] = "+0100"

    def wrong_utc(payload):
        date_row(payload)[4] = "2025-03-04T00:00:00+00:00"

    def wrong_zone_state(payload):
        date_row(payload)[2] = "zone_stated_minus_zero"

    def drop_gap(payload):
        payload["facts"]["gaps.later"]["value"] = []

    for mutate, source, fixture, fact in (
        (wrong_offset, zoned, "date_stated_zone", "headers.date"),
        (wrong_utc, zoned, "date_stated_zone", "headers.date"),
        (wrong_zone_state, zoned, "date_stated_zone", "headers.date"),
        (drop_gap, absent, "date_absent", "gaps.later"),
    ):
        name = mutate.__name__
        assert callable(mutate)  # the mutation is a real, patched observation
        sidecar_copy.tamper(tmp_path, source, mutate, name=name)
        gate = l1_gate(tmp_path / name)
        assert gate.passed is False, name
        assert any(
            fixture in line and fact in line for line in gate.evidence
        ), (name, gate.evidence)


def test_every_emitted_date_gap_id_has_a_mutation_case(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Each emitted gap id has a case with the anti-vacuity triple (patched, reached, differs).

    ``headers.no_date`` and ``headers.invalid_date`` are carried by committed fixtures;
    ``headers.date_no_zone`` is not, so its case is built from inline hand-typed bytes into a
    temporary corpus -- no fixture is added and no sidecar edited.
    """
    emitted = {GAP_NO_DATE, GAP_INVALID_DATE, GAP_DATE_NO_ZONE}
    catalogue = {
        GAP_NO_DATE: "a missing Date's headers.no_date gap dropped",
        GAP_INVALID_DATE: "an invalid Date's headers.invalid_date gap dropped",
        GAP_DATE_NO_ZONE: "a zone-absent Date's headers.date_no_zone gap dropped",
    }
    assert set(catalogue) == emitted == set(date_stage.DATE_GAPS)

    # The inline fixture for the gap no committed fixture carries.
    inline_raw = (
        b"From: Ada Sender <ada@example.test>\r\n"
        b"To: Ben Receiver <ben@example.test>\r\n"
        b"Subject: inline zone absent\r\n"
        b"Date: Tue, 4 Mar 2025 08:05:00\r\n"
        b"Message-ID: <inline-date-no-zone@example.test>\r\n"
        b"\r\n"
        b"a Date with no zone token\r\n"
    )
    inline_payload = {
        "fixture": "inline_date_no_zone.eml",
        "labels_provenance": "spec",
        "facts": {
            "headers.date": {
                "phase": 1,
                "value": [
                    [
                        3,
                        " Tue, 4 Mar 2025 08:05:00",
                        "zone_absent",
                        None,
                        ["unknown", GAP_DATE_NO_ZONE],
                    ]
                ],
            },
            "gaps.later": {
                "phase": 1,
                "value": [[GAP_DATE_NO_ZONE, "1", 1, "the Date field states no zone, so the UTC moment is unknown"]],
            },
        },
    }
    inline_dir = tmp_path / "inline"
    sidecar_copy.write_inline(inline_dir, "inline_date_no_zone", inline_raw, inline_payload)
    # (a) the faithful inline corpus is green, so the mutation is what is caught.
    assert l1_gate(inline_dir).passed is True, l1_gate(inline_dir).lines()

    real = header_stage.parse_date
    assert callable(real)  # (a) the patched symbol exists
    reached = {"count": 0}
    dropped = {"gap": GAP_NO_DATE}

    def careless(value):
        reached["count"] += 1  # (b) the patch is reached, never vacuously applied
        record = real(value)
        if record.gap == dropped["gap"]:
            return dataclasses.replace(record, gap=None)
        return record

    monkeypatch.setattr(header_stage, "parse_date", careless)

    for gap_id, directory, fixture in (
        (GAP_NO_DATE, FIXTURES, "date_absent"),
        (GAP_INVALID_DATE, FIXTURES, "date_invalid"),
        (GAP_DATE_NO_ZONE, inline_dir, "inline_date_no_zone"),
    ):
        dropped["gap"] = gap_id
        gate = l1_gate(directory)
        assert reached["count"] > 0, gap_id
        assert gate.passed is False, (gap_id, gate.lines())  # (c) the gate flips
        assert any(
            fixture in line and gap_id in line for line in gate.evidence
        ), (gap_id, gate.evidence)

    monkeypatch.setattr(header_stage, "parse_date", real)
    # Turn 1.6: the restored corpus is red for exactly the quote facts (see test_l1_gate.py).
    assert oracle.quote_only_mismatches(l1_gate()), "restoring the rule must leave only the quote facts red"


def test_a_seeded_fuzz_of_the_parser_never_raises() -> None:
    """A seeded, bounded fuzz over mutated Date values: total, with sound instants.

    Every result is a record; its utc is either a well-formed RFC 3339 ``+00:00`` instant or an
    ``["unknown", reason]`` pair naming a registered reason. No input raises, including NUL, a
    lone CR/LF, 8-bit bytes, a huge repeated-byte run, an enormous digit run and non-ASCII
    digits (which are bytes no ASCII scan accepts).
    """
    rng = random.Random(13_1003)
    sources: list[bytes] = []
    for path in _all_fixtures():
        for _name, value in stdlib_scanner.date_fields(path.read_bytes()):
            sources.append(value)
    for adversarial in (
        b"\x00" * 200,
        b"\r",
        b"\n",
        b"\r\n",
        b"\xff" * 50,
        b"\xd9\xa1\xd9\xa2",  # Arabic-Indic digits, as utf-8 bytes
        b"(" * 500,
        b")" * 500,
        b"9" * 4_000,
        b"+0000" * 100,
        b"Tue, 4 Mar 2025 08:05:00 +0000" * 20,
    ):
        sources.append(adversarial)

    per_source = 40
    seeds = 0
    for source in sources:
        for _ in range(per_source):
            data = bytearray(source)
            for _ in range(rng.randint(1, 6)):
                if not data:
                    break
                index = rng.randrange(len(data))
                op = rng.randint(0, 5)
                if op == 0:
                    data[index] = rng.choice(b"\r\n:+- \x00\xff()ESTeu9")
                elif op == 1:
                    del data[index:]
                elif op == 2:
                    data[index:index] = bytes(rng.choice([b"+", b"-", b":", b"(", b")", b" ", b",", b"Mar", b"2025"]))
                elif op == 3:
                    cut = rng.randrange(len(data))
                    data = bytearray(bytes(data[cut:]) + bytes(data[:cut]))
                elif op == 4:
                    data[index:index] = bytes([data[index]]) * rng.randint(1, 4)
                else:
                    junk = rng.choice([b"68", b"60", b"99", b"00", b"9959", b"9960"])
                    data[index:index] = junk

            record = _parse(bytes(data))
            assert isinstance(record, date_stage.DateRecord), (bytes(data), record)
            utc = record.utc_value()
            if isinstance(utc, list):
                assert utc[0] == "unknown", (bytes(data), utc)
                assert utc[1] in date_stage.DATE_GAPS, (bytes(data), utc)
            else:
                assert _is_well_formed_utc(utc), (bytes(data), utc)
            seeds += 1
    assert seeds == len(sources) * per_source, seeds


def test_the_parser_is_linear_in_the_input() -> None:
    """Doubling the input must less than triple the work: no quadratic blow-up (a bug if so)."""

    def best(data: bytes) -> float:
        fastest = None
        for _ in range(5):
            start = time.perf_counter()
            date_stage.parse_date(data)
            elapsed = time.perf_counter() - start
            fastest = elapsed if fastest is None else min(fastest, elapsed)
        return fastest

    # A run of '(' is one nested comment, a run of '(a)' is many comments, a run of digits is
    # one enormous word. A quadratic scanner would show ~4x on the doubled input; a linear ~2x.
    for label, chunk in (
        ("open paren run", b"("),
        ("comment run", b"(a)"),
        ("digit run", b"9"),
    ):
        small = chunk * (100_000 // len(chunk))
        large = small + small
        ratio = best(large) / max(best(small), 1e-9)
        assert ratio < 3.2, (label, ratio, "the parser looks quadratic in the input")


def test_the_date_facts_are_live_over_the_corpus() -> None:
    """Both new comparisons are live: every ``headers.date`` label and the date gaps match."""
    sidecars = oracle.load_sidecars()
    dated = [sidecar for sidecar in sidecars.values() if "headers.date" in sidecar.facts]
    assert len(dated) == 6, [sidecar.stem for sidecar in dated]
    for sidecar in dated:
        report = oracle.check(sidecar)
        outcome = next(o for o in report.outcomes if o.fact_id == "headers.date")
        assert outcome.status is oracle.Status.OK, (sidecar.stem, outcome.status, outcome.detail)

    # The projection's date_time column is live, so nothing is deferred any more.
    assert oracle.deferral_counts() == {}

    gate = l1_gate()
    # Turn 1.6: the corpus is red for exactly the quote facts (see test_l1_gate.py).
    assert oracle.quote_only_mismatches(gate), gate.lines()
