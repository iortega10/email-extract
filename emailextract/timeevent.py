"""D15 TimeEvent -- the frozen time-evidence shape.

Fields exactly as design D15: ``{event_id, doc_id, parent_event_id|null, kind,
when_raw, when_utc | unknown(reason), offset | unknown, offset_origin, precision,
ambiguity, source {field|property|part, ordinal, span}, trust,
usable_for_arrival_ordering}``.

``when_utc`` and ``offset`` are each a value OR an unknown with a named reason --
never both and never neither (:class:`TimeValue`). ``SEQUENCE``, ``UID`` and
``METHOD`` are calendar facts, NOT TimeEvents; only
``DTSTART/DTEND/DTSTAMP/CREATED/LAST-MODIFIED`` emit events.

The shape's invariants are **enforced at construction**, not only documented
(``__post_init__``): ``ambiguity=relative`` requires an unknown ``when_utc`` (a
relative time is never resolved), ``trust=filesystem`` forbids
``usable_for_arrival_ordering``, and the four enum fields coerce from their string
values so a value outside the vocabulary raises there rather than only when a
record is decoded from JSON. This mirrors ``workbookextract/timeevent.py`` (the
second producer) so the two copies stay shape-equal; it is a mirror, not an
import: neither package depends on the other.

The shape version is ``TIMEEVENT_VERSION`` in :mod:`emailextract.versions`; this
type lives here until a second producer exists, and moves to ``docextract-core``
only when a third producer or a cross-package consumer appears (D15).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from docextract_core.codec import CodecError

__all__ = [
    "Ambiguity",
    "OffsetOrigin",
    "Precision",
    "Span",
    "TimeEvent",
    "TimeSource",
    "TimeValue",
    "Trust",
]


class OffsetOrigin(str, Enum):
    """Where the UTC offset came from (D15)."""

    STATED_IN_TEXT = "stated_in_text"
    DERIVED_BY_NAMED_RULE = "derived_by_named_rule"
    ABSENT = "absent"


class Precision(str, Enum):
    """How fine the timestamp is; ambiguity is not precision (D15)."""

    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    SECOND = "second"


class Ambiguity(str, Enum):
    """What is unresolved about the timestamp (D15)."""

    NONE = "none"
    DAY_MONTH = "day_month"
    TIMEZONE = "timezone"
    RELATIVE = "relative"


class Trust(str, Enum):
    """Who or what asserts the timestamp (D15)."""

    CLAIMED = "claimed"
    DERIVED = "derived"
    USER_SUPPLIED = "user_supplied"
    FILESYSTEM = "filesystem"


def _non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CodecError(f"timeevent.{name} must be a non-empty str")
    return value


@dataclass(frozen=True)
class Span:
    """A structured source span: ``[start, end)`` in the source's own space."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise CodecError("span.start must be int")
        if isinstance(self.end, bool) or not isinstance(self.end, int):
            raise CodecError("span.end must be int")
        if self.start > self.end:
            raise CodecError("span.start must not be after span.end")


@dataclass(frozen=True)
class TimeValue:
    """``when_utc`` / ``offset``: a value OR an unknown(reason), never both, never neither."""

    value: str | None = None
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None and self.unknown_reason is not None:
            raise CodecError("time value: value and unknown_reason are mutually exclusive")
        if self.value is None and self.unknown_reason is None:
            raise CodecError("time value: requires a value or an unknown_reason")
        if self.value is not None:
            _non_empty(self.value, "value")
        if self.unknown_reason is not None:
            _non_empty(self.unknown_reason, "unknown_reason")

    @property
    def is_unknown(self) -> bool:
        return self.unknown_reason is not None


@dataclass(frozen=True)
class TimeSource:
    """``source``: exactly one of ``field | property | part``, plus ordinal and span."""

    ordinal: int
    field: str | None = None
    property: str | None = None
    part: str | None = None
    span: Span | None = None

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int):
            raise CodecError("time source: ordinal must be int")
        if self.ordinal < 0:
            raise CodecError("time source: ordinal must be >= 0")
        named = [name for name in ("field", "property", "part") if getattr(self, name) is not None]
        if len(named) != 1:
            raise CodecError("time source: exactly one of field|property|part is required")
        _non_empty(getattr(self, named[0]), f"source.{named[0]}")


@dataclass(frozen=True)
class TimeEvent:
    """One timestamp claim (D15). ``kind`` is an open vocabulary:
    ``sent | received_hop | authored | modified | revision | comment |
    calendar_start | calendar_end | calendar_stamp | mentioned_in_text |
    fs_mtime | ...``.
    """

    event_id: str
    doc_id: str
    kind: str
    when_raw: str
    when_utc: TimeValue
    offset: TimeValue
    offset_origin: OffsetOrigin
    precision: Precision
    ambiguity: Ambiguity
    source: TimeSource
    trust: Trust
    usable_for_arrival_ordering: bool
    parent_event_id: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.event_id, "event_id")
        _non_empty(self.doc_id, "doc_id")
        _non_empty(self.kind, "kind")
        _non_empty(self.when_raw, "when_raw")
        if not isinstance(self.usable_for_arrival_ordering, bool):
            raise CodecError("timeevent.usable_for_arrival_ordering must be bool")
        if self.parent_event_id is not None:
            _non_empty(self.parent_event_id, "parent_event_id")
        if not isinstance(self.when_utc, TimeValue):
            raise CodecError("timeevent.when_utc must be a TimeValue")
        if not isinstance(self.offset, TimeValue):
            raise CodecError("timeevent.offset must be a TimeValue")
        if not isinstance(self.source, TimeSource):
            raise CodecError("timeevent.source must be a TimeSource")
        # Records are canonical on construction: a string is coerced to its enum member and a value
        # outside the vocabulary raises here, not only when a record is decoded from JSON.
        for name, enum_type in (
            ("offset_origin", OffsetOrigin),
            ("precision", Precision),
            ("ambiguity", Ambiguity),
            ("trust", Trust),
        ):
            value = getattr(self, name)
            if not isinstance(value, enum_type):
                try:
                    object.__setattr__(self, name, enum_type(value))
                except ValueError:
                    allowed = ", ".join(member.value for member in enum_type)
                    raise CodecError(f"timeevent.{name}: {value!r} is not one of: {allowed}") from None
        if self.offset_origin == OffsetOrigin.ABSENT and not self.offset.is_unknown:
            raise CodecError("timeevent: offset_origin=absent requires offset to be unknown")
        # The shape's invariants, enforced rather than merely documented:
        if self.ambiguity == Ambiguity.RELATIVE and not self.when_utc.is_unknown:
            raise CodecError("timeevent: a relative time is unknown(reason) and is never resolved")
        if self.trust == Trust.FILESYSTEM and self.usable_for_arrival_ordering:
            raise CodecError("timeevent: a filesystem time is never usable for arrival ordering")
