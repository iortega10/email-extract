"""Turn 1.3: the package's own RFC 5322 3.3 date-time parser (decision 4, D2/D15).

The package **owns** date parsing the way :mod:`emailextract.addresses` owns addresses: this
module is a byte-oriented, hand-written, **linear** scanner over one field's *value bytes*, in
one file with one public entry point, :func:`parse_date`. It imports neither the stdlib
``email`` nor ``datetime`` and uses **only integers and its own proleptic Gregorian arithmetic**
(the Howard Hinnant ``days_from_civil`` / ``civil_from_days`` pair), so a year the stdlib
``datetime`` could not hold still parses and the result is identical on 3.11 and 3.14. There is
no timezone database and no locale.

Grammar (RFC 5322 3.3, with the obs- forms of 4.3):

* optional ``day-of-week ","`` -- a case-insensitive three-letter weekday name. A day-name that
  does not match the date's *actual* weekday is **not** an error and is **not** repaired: it is
  recorded as stated and the weekday is never computed (computing it would be the one way to
  "repair" the value);
* ``day`` (1 or 2 digits; an obs- leading zero is kept as stated), ``month`` (three letters,
  case-insensitive), ``year`` -- 4 digits per the RFC, or an **obs-year**: 2 digits map 00-49 ->
  2000-2049 and 50-99 -> 1950-1999, and any 3-digit year maps to +1900, exactly as RFC 5322 4.3
  states;
* ``time-of-day`` = ``hour ":" minute [ ":" second ]`` (second 60 is a **leap second**: it is
  kept as stated, never rolled into the next minute -- see :func:`_utc_instant`);
* ``zone`` -- a numeric ``+HHMM``/``-HHMM`` or an RFC 5322 4.3 obs-zone name;
* ``CFWS`` (comments, nested, quoted-pair aware, and folding whitespace including obs-fold)
  between all tokens and after the zone. A trailing ``(UTC)``-style comment is CFWS and is
  **kept out of the zone**: a comment is never read as the zone, so a comment that merely looks
  like a zone name (``(EST)``) is not one.

The **three recorded zone states** (decision 4) are :data:`ZONE_STATES`: ``zone_stated`` (a
numeric ``+HHMM``/``-HHMM`` other than ``-0000``, or an obs-zone name), ``zone_stated_minus_zero``
(the literal ``-0000``: "no information about local time", **never** read as ``+0000`` -- the
offset token is kept), and ``zone_absent`` (no zone token at all).

Calendar validity is checked by this module's own table (days in month with the Gregorian leap
rule; hour 0-23, minute 0-59, second 0-60). An impossible date (31 Feb, hour 24, month ``Foo``)
is :data:`GAP_HEADERS_INVALID_DATE`, never normalised, never an epoch.

The frozen :class:`DateRecord` is what :func:`parse_date` returns; the oracle projects it onto
``headers.date`` (``docs/design/phase1-facts.md``): ``[ordinal, raw, zone_state, offset, utc]``,
where ``utc`` is the RFC 3339 UTC instant (``+00:00``) or a ``["unknown", reason_id]`` pair. **The
record carries no sort key**: an ordering is a later turn's (Phase 3, ``TimeEvent``) concern,
and a missing or invalid date must never sort as an epoch, so nothing here invents one.

Nothing raises on input content: :func:`parse_date` is **total** over every bytes value (and
``None``, the absent-field case), carrying a closed reason id for a recorded failure and never
library or exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "DATE_GAPS",
    "DateRecord",
    "GAP_HEADERS_DATE_NO_ZONE",
    "GAP_HEADERS_INVALID_DATE",
    "GAP_HEADERS_NO_DATE",
    "OBS_ZONES",
    "ZONE_STATES",
    "parse_date",
]

#: The closed ``zone_state`` triple (decision 4).
ZONE_STATES: Final[tuple[str, ...]] = ("zone_stated", "zone_stated_minus_zero", "zone_absent")

#: The closed reason ids a date records (``docs/design/phase0-gaps.md``). A recorded failure
#: carries one of these; nothing else.
GAP_HEADERS_NO_DATE: Final[str] = "headers.no_date"
GAP_HEADERS_INVALID_DATE: Final[str] = "headers.invalid_date"
GAP_HEADERS_DATE_NO_ZONE: Final[str] = "headers.date_no_zone"
DATE_GAPS: Final[tuple[str, ...]] = (
    GAP_HEADERS_NO_DATE,
    GAP_HEADERS_INVALID_DATE,
    GAP_HEADERS_DATE_NO_ZONE,
)

#: The **named** RFC 5322 4.3 obs-zones and the numeric offset each stands for. ``UT`` and
#: ``GMT`` are ``+0000``; the US zones are the RFC's own table. A name is matched
#: case-insensitively. The single-letter military zones are **not** here: they carry no
#: reliable offset (see :func:`_zone_token`).
OBS_ZONES: Final[dict[str, str]] = {
    "ut": "+0000",
    "gmt": "+0000",
    "est": "-0500",
    "edt": "-0400",
    "cst": "-0600",
    "cdt": "-0500",
    "mst": "-0700",
    "mdt": "-0600",
    "pst": "-0800",
    "pdt": "-0700",
}

#: The RFC 5322 4.3 single-letter military zones carry **no reliable offset**: RFC 5322 says
#: they are to be treated as ``-0000`` ("no information about local time"). A military letter is
#: therefore recorded ``zone_stated_minus_zero`` with the offset ``-0000`` (Turn 1.3 review: a
#: consumer must never read ``Z`` as UTC, which is exactly what the minus-zero state protects);
#: the raw value keeps the letter. ``J``/``j`` are not military zones (RFC 5322 4.3 excludes
#: ``%d74``/``%d106``).
_MILITARY_BYTES: Final[frozenset[int]] = frozenset(
    list(range(0x41, 0x49 + 1))       # A-I
    + list(range(0x4B, 0x5A + 1))     # K-Z
    + list(range(0x61, 0x69 + 1))     # a-i
    + list(range(0x6B, 0x7A + 1))     # k-z
)

_WEEKDAYS: Final[frozenset[str]] = frozenset(
    {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
)

_MONTHS: Final[dict[str, int]] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MONTH_DAYS: Final[tuple[int, ...]] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_WSP: Final[frozenset[int]] = frozenset({0x20, 0x09, 0x0D, 0x0A})
_DELIM: Final[frozenset[int]] = frozenset({0x20, 0x09, 0x0D, 0x0A, 0x28, 0x29, 0x2C})


@dataclass(frozen=True)
class DateRecord:
    """One Date field parsed, as the value bytes plus what the parser read from them.

    ``raw`` is the **verbatim value bytes** (``None`` only for the absent-field case), so a
    reader can always recover what was written. ``zone_state`` is one of :data:`ZONE_STATES`;
    ``offset`` is the stated offset text (``"+HHMM"``/``"-HHMM"`` or an obs-zone name's numeric
    form) or ``None`` when the zone is absent. ``utc`` is the RFC 3339 UTC instant (``+00:00``)
    or ``None``, in which case ``reason_id`` is the closed reason the instant is unknown.

    ``gap`` is the id this record contributes to the header stage's gap channel (``None`` when
    the value is a trustworthy instant, or when only the *instant* is untrustworthy rather than
    the value -- an out-of-range offset records ``reason_id`` but invents no gap, since the
    design names no registry id for it). ``obs_year``, ``leap_second`` and ``day_name`` record
    the obs- forms and the leap second as stated. The record deliberately carries **no sort
    key**: ordering is Phase 3's concern and a missing/invalid date must never sort as an epoch.
    """

    raw: bytes | None
    zone_state: str
    offset: str | None
    utc: str | None
    reason_id: str | None
    gap: str | None
    day_name: str | None = None
    obs_year: bool = False
    leap_second: bool = False

    def __post_init__(self) -> None:
        if self.zone_state not in ZONE_STATES:
            raise ValueError(f"date_record.zone_state must be one of {ZONE_STATES}, got {self.zone_state!r}")
        if (self.offset is None) != (self.zone_state == "zone_absent"):
            raise ValueError(
                f"a {self.zone_state!r} date carries an offset text and an absent one carries none, "
                f"got {self.offset!r}"
            )
        if self.raw is not None and not isinstance(self.raw, bytes):
            raise ValueError(f"date_record.raw must be bytes or None, got {type(self.raw).__name__}")
        if self.utc is None:
            if self.reason_id not in DATE_GAPS:
                raise ValueError(
                    f"a date with no UTC instant must carry a closed reason id of {DATE_GAPS}, "
                    f"got {self.reason_id!r}"
                )
        elif self.reason_id is not None or self.gap is not None:
            raise ValueError("a date with a UTC instant carries no reason id and no gap")
        if self.gap is not None and self.gap not in DATE_GAPS:
            raise ValueError(f"a date gap must be one of {DATE_GAPS}, got {self.gap!r}")

    @property
    def ok(self) -> bool:
        """Whether a UTC instant was derived (the value parsed *and* a zone applied)."""
        return self.utc is not None

    def utc_value(self) -> str | list[str]:
        """The fact's ``utc`` column: the RFC 3339 instant, or ``["unknown", reason_id]``."""
        if self.utc is not None:
            return self.utc
        return ["unknown", self.reason_id]

    def as_fact_row(self, ordinal: int | None) -> list[object]:
        """The ``headers.date`` row: ``[ordinal, raw, zone_state, offset, utc]``.

        ``raw`` is the value in the latin-1 view the other header facts use; the absent-field
        record carries ``None`` for both ``ordinal`` and ``raw`` (the labels type it that way).
        """
        raw = None if self.raw is None else self.raw.decode("latin-1")
        return [ordinal, raw, self.zone_state, self.offset, self.utc_value()]


@dataclass(frozen=True)
class _Token:
    kind: str  # "cfws" | "word" | "comma" | "paren"
    start: int
    end: int


def _tokenize(value: bytes) -> list[_Token]:
    """The bytes as a **linear** token stream (one pass, no regex, no backtracking).

    Tokens: ``cfws`` (a run of SP/HTAB/CR/LF -- obs-fold included -- or a ``(`` ... ``)``
    comment, nested and quoted-pair aware), ``comma``, ``paren`` (a stray ``)``), or ``word``
    (a maximal run of anything else, so ``08:05:00`` and ``+0000`` are each one word). An
    unterminated comment runs to the end of the value.
    """
    tokens: list[_Token] = []
    index = 0
    size = len(value)
    while index < size:
        byte = value[index]
        if byte in _WSP:
            end = index + 1
            while end < size and value[end] in _WSP:
                end += 1
            tokens.append(_Token("cfws", index, end))
            index = end
        elif byte == 0x28:  # '(' -- a comment, nested, quoted-pair aware
            end = index + 1
            depth = 1
            while end < size and depth:
                here = value[end]
                if here == 0x5C:
                    end += 2
                    continue
                if here == 0x28:
                    depth += 1
                elif here == 0x29:
                    depth -= 1
                end += 1
            end = min(end, size)
            tokens.append(_Token("cfws", index, end))
            index = end
        elif byte == 0x29:  # a stray ')'
            tokens.append(_Token("paren", index, index + 1))
            index += 1
        elif byte == 0x2C:  # ','
            tokens.append(_Token("comma", index, index + 1))
            index += 1
        else:
            end = index + 1
            while end < size and value[end] not in _DELIM:
                end += 1
            tokens.append(_Token("word", index, end))
            index = end
    return tokens


def _uint(token: bytes, low: int, high: int) -> int | None:
    """The ASCII digits of ``token`` as an int, or ``None`` unless its length is in ``[low, high]``.

    An explicit ASCII scan, never ``int()`` or ``str.isdigit()`` on unvalidated text, and the
    length is bounded **before** any conversion, so a huge digit run cannot build a huge int.
    """
    size = len(token)
    if size < low or size > high:
        return None
    value = 0
    for byte in token:
        if byte < 0x30 or byte > 0x39:
            return None
        value = value * 10 + (byte - 0x30)
    return value


def _is_alpha(token: bytes) -> bool:
    if not token:
        return False
    return all(0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A for byte in token)


def _is_leap(year: int) -> bool:
    """The Gregorian leap rule (a leap year is divisible by 4, but not by 100 unless by 400)."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return _MONTH_DAYS[month - 1]


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Days since 1970-01-01, proleptic Gregorian, all-integer (Hinnant's days_from_civil)."""
    year -= month <= 2
    era = (year if year >= 0 else year - 399) // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(days: int) -> tuple[int, int, int]:
    """The inverse of :func:`_days_from_civil` (Hinnant's civil_from_days), all-integer."""
    days += 719468
    era = (days if days >= 0 else days - 146096) // 146097
    doe = days - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    year = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + (3 if mp < 10 else -9)
    return (year + (month <= 2), month, day)


def _zone_token(text: bytes) -> tuple[str, str | None, int | None, bool] | None:
    """``(zone_state, offset_text, offset_minutes, usable)`` for one token, or ``None``.

    A numeric ``+HHMM``/``-HHMM`` (the design's offset limit: ``MM`` 00-59, so the 4-digit
    magnitude can never exceed 9959), an obs-zone name, or a military letter. ``usable`` is
    ``False`` for a numeric zone whose ``MM`` is out of range -- the token is kept as stated but
    the instant cannot be trusted. ``None`` means the token is not a zone at all.
    """
    if len(text) == 5 and text[0] in (0x2B, 0x2D):  # '+' or '-'
        hours = _uint(text[1:3], 2, 2)
        minutes = _uint(text[3:5], 2, 2)
        if hours is None or minutes is None:
            return None
        if text[0] == 0x2D and hours == 0 and minutes == 0:
            return ("zone_stated_minus_zero", "-0000", 0, True)
        stated = text.decode("latin-1")
        if minutes > 59:
            return ("zone_stated", stated, None, False)
        sign = -1 if text[0] == 0x2D else 1
        return ("zone_stated", stated, sign * (hours * 60 + minutes), True)
    if len(text) == 1 and text[0] in _MILITARY_BYTES:
        return ("zone_stated_minus_zero", "-0000", 0, True)
    if len(text) <= 3 and _is_alpha(text):
        offset = OBS_ZONES.get(text.decode("latin-1").lower())
        if offset is not None:
            hours = _uint(offset[1:3].encode("ascii"), 2, 2)
            minutes = _uint(offset[3:5].encode("ascii"), 2, 2)
            sign = -1 if offset[0] == "-" else 1
            assert hours is not None and minutes is not None  # the table is a literal
            return ("zone_stated", offset, sign * (hours * 60 + minutes), True)
    return None


def _numeric_zone_from(tokens: list[_Token], value: bytes) -> tuple[str, str | None, int | None, bool]:
    """The **last** numeric zone-looking word token, else zone_absent.

    Used only when the value does not parse: a numeric ``+HHMM``/``-HHMM`` token is unambiguous
    wherever it sits, so it is still recorded (an out-of-range offset keeps its state and text).
    An obs-zone **name** is not guessed here, because a bare word could be almost anything -- it
    is read only at the zone position, by :func:`_strict`.
    """
    for token in reversed(tokens):
        if token.kind != "word":
            continue
        text = value[token.start : token.end]
        if len(text) == 5 and text[0] in (0x2B, 0x2D):
            found = _zone_token(text)
            if found is not None:
                return found
    return ("zone_absent", None, None, True)


def _time_parts(word: bytes) -> tuple[int, int, int, bool, bytes] | None:
    """``(hour, minute, second, leap_second, rest)`` for a ``HH:MM[:SS]`` word, or ``None``.

    ``rest`` is whatever trails the seconds (a zone suffix written with no space, or junk).
    """
    if len(word) < 5 or word[2:3] != b":":
        return None
    hour = _uint(word[0:2], 2, 2)
    minute = _uint(word[3:5], 2, 2)
    if hour is None or minute is None:
        return None
    if len(word) == 5 or word[5:6] != b":":
        return hour, minute, 0, False, word[5:]
    second = _uint(word[6:8], 2, 2)
    if second is None:
        return None
    return hour, minute, second, second == 60, word[8:]


def _strict(
    value: bytes, tokens: list[_Token]
) -> tuple[int, int, int, int, int, int, bool, str | None, bool, tuple[str, str | None, int | None, bool]] | None:
    """The strict RFC 5322 3.3 read of the significant tokens, or ``None`` if it fails.

    Returns ``(year, month, day, hour, minute, second, leap_second, day_name, obs_year, zone)``
    on success, where ``zone`` is the ``(state, offset, minutes, usable)`` tuple read at the
    expected zone position. The value is rejected (never normalised) on a missing or unparsable
    field, a calendar-impossible day/hour/minute/second, a month that is not a month, a day-name
    that is not a weekday, a zone token where none is expected, or any significant token left
    over. The zone is read **here, at the one legal position**, so a comment or a stray word is
    never mistaken for it.
    """
    sig = [token for token in tokens if token.kind != "cfws"]
    index = 0
    total = len(sig)

    def word() -> bytes | None:
        nonlocal index
        if index < total and sig[index].kind == "word":
            token = sig[index]
            index += 1
            return value[token.start : token.end]
        return None

    day_name: str | None = None
    if index + 1 < total and sig[index].kind == "word" and sig[index + 1].kind == "comma":
        name = value[sig[index].start : sig[index].end]
        if len(name) == 3 and _is_alpha(name) and name.decode("latin-1").lower() in _WEEKDAYS:
            day_name = name.decode("latin-1")
            index += 2

    day_token = word()
    month_token = word()
    year_token = word()
    time_token = word()
    if day_token is None or month_token is None or year_token is None or time_token is None:
        return None

    day = _uint(day_token, 1, 2)
    if day is None or day == 0:
        return None

    if len(month_token) != 3 or not _is_alpha(month_token):
        return None
    month = _MONTHS.get(month_token.decode("latin-1").lower())
    if month is None:
        return None

    obs_year = False
    if len(year_token) == 4:
        year = _uint(year_token, 4, 4)
    elif len(year_token) == 2:
        short = _uint(year_token, 2, 2)
        year = None if short is None else (short + 2000 if short <= 49 else short + 1900)
        obs_year = True
    elif len(year_token) == 3:
        short = _uint(year_token, 3, 3)
        year = None if short is None else short + 1900
        obs_year = True
    else:
        year = None
    if year is None or year < 1 or year > 9999:
        return None

    time = _time_parts(time_token)
    if time is None:
        return None
    hour, minute, second, leap_second, rest = time
    if hour > 23 or minute > 59 or second > 60:
        return None
    if day > _days_in_month(year, month):
        return None

    zone: tuple[str, str | None, int | None, bool] = ("zone_absent", None, None, True)
    if rest:
        found = _zone_token(rest)
        if found is None:
            return None
        zone = found
    elif index < total and sig[index].kind == "word":
        found = _zone_token(value[sig[index].start : sig[index].end])
        if found is not None:
            zone = found
            index += 1
    if index != total:
        return None

    return year, month, day, hour, minute, second, leap_second, day_name, obs_year, zone


def _utc_instant(
    year: int, month: int, day: int, hour: int, minute: int, second: int, offset_minutes: int, leap: bool
) -> str | None:
    """The RFC 3339 UTC instant, or ``None`` when it leaves the representable 0001-9999 range.

    The offset is applied with integer arithmetic (UTC = local - offset). A **leap second**
    (second 60) is kept as ``:60`` in the rendering and contributes **zero** seconds to the
    arithmetic, so it is never silently rolled into the next minute; the record's
    ``leap_second`` flag says the ``:60`` was written.
    """
    seconds = 0 if leap else second
    total = (
        _days_from_civil(year, month, day) * 86400
        + hour * 3600
        + minute * 60
        + seconds
        - offset_minutes * 60
    )
    days, rem = divmod(total, 86400)
    utc_year, utc_month, utc_day = _civil_from_days(days)
    if utc_year < 1 or utc_year > 9999:
        return None
    utc_hour, rem2 = divmod(rem, 3600)
    utc_minute, utc_second = divmod(rem2, 60)
    tail = "60" if leap else f"{utc_second:02d}"
    return (
        f"{utc_year:04d}-{utc_month:02d}-{utc_day:02d}"
        f"T{utc_hour:02d}:{utc_minute:02d}:{tail}+00:00"
    )


def parse_date(value: bytes | None) -> DateRecord:
    """Parse one Date field's **value bytes** into a frozen :class:`DateRecord`.

    ``None`` is the **absent** case -- no Date field at all -- and yields the labelled
    ``zone_absent`` record with reason :data:`GAP_HEADERS_NO_DATE` (a missing date never becomes
    an epoch, ``now`` or the file time). The function is **total**: it never raises on input
    content and returns a fresh record for any bytes, including NUL, a lone CR/LF, 8-bit bytes,
    a huge repeated-byte run, an enormous digit run and non-ASCII digits.
    """
    if value is None:
        return DateRecord(
            raw=None,
            zone_state="zone_absent",
            offset=None,
            utc=None,
            reason_id=GAP_HEADERS_NO_DATE,
            gap=GAP_HEADERS_NO_DATE,
        )
    if not isinstance(value, bytes):
        raise TypeError(f"value must be bytes or None, got {type(value).__name__}")

    tokens = _tokenize(value)
    parsed = _strict(value, tokens)
    if parsed is None:
        zone_state, offset, _minutes, _usable = _numeric_zone_from(tokens, value)
        return DateRecord(
            raw=value,
            zone_state=zone_state,
            offset=offset,
            utc=None,
            reason_id=GAP_HEADERS_INVALID_DATE,
            gap=GAP_HEADERS_INVALID_DATE,
        )

    year, month, day, hour, minute, second, leap_second, day_name, obs_year, zone = parsed
    zone_state, offset, offset_minutes, usable = zone

    if not usable:
        # The value parses; only the offset is out of the design's range. The token is kept as
        # stated and the instant is unknown -- and no gap is invented (the design names none).
        return DateRecord(
            raw=value,
            zone_state=zone_state,
            offset=offset,
            utc=None,
            reason_id=GAP_HEADERS_INVALID_DATE,
            gap=None,
            day_name=day_name,
            obs_year=obs_year,
            leap_second=leap_second,
        )

    if zone_state == "zone_absent":
        return DateRecord(
            raw=value,
            zone_state="zone_absent",
            offset=None,
            utc=None,
            reason_id=GAP_HEADERS_DATE_NO_ZONE,
            gap=GAP_HEADERS_DATE_NO_ZONE,
            day_name=day_name,
            obs_year=obs_year,
            leap_second=leap_second,
        )

    assert offset_minutes is not None  # a stated zone always carries its minutes
    instant = _utc_instant(year, month, day, hour, minute, second, offset_minutes, leap_second)
    if instant is None:
        # The instant leaves the representable 0001-9999 range (e.g. a year-1 date with a +9959
        # offset). No gap: the value itself is a well-formed date-time.
        return DateRecord(
            raw=value,
            zone_state=zone_state,
            offset=offset,
            utc=None,
            reason_id=GAP_HEADERS_INVALID_DATE,
            gap=None,
            day_name=day_name,
            obs_year=obs_year,
            leap_second=leap_second,
        )

    return DateRecord(
        raw=value,
        zone_state=zone_state,
        offset=offset,
        utc=instant,
        reason_id=None,
        gap=None,
        day_name=day_name,
        obs_year=obs_year,
        leap_second=leap_second,
    )
