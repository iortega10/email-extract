"""Turn 0.1 tests: the D15 TimeEvent shape stays frozen and semantically strict.

The frozen shape imports nothing from the core; the only import is the codec
entry point. Its version is ``TIMEEVENT_VERSION`` and must never be the record's
``OUTPUT_SCHEMA_VERSION``.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re

import pytest

from docextract_core.codec import CodecError

import emailextract.versions as versions
from emailextract import (
    Ambiguity,
    OffsetOrigin,
    Precision,
    Span,
    TimeEvent,
    TimeSource,
    TimeValue,
    Trust,
    record_from_bytes,
    record_to_bytes,
)


def _event(**overrides: object) -> TimeEvent:
    fields: dict[str, object] = dict(
        event_id="ev-1",
        doc_id="doc-1",
        kind="received_hop",
        when_raw="Thu, 01 Jan 2026 12:00:00 +0200",
        when_utc=TimeValue(value="2026-01-01T10:00:00Z"),
        offset=TimeValue(value="+02:00"),
        offset_origin=OffsetOrigin.STATED_IN_TEXT,
        precision=Precision.SECOND,
        ambiguity=Ambiguity.NONE,
        source=TimeSource(ordinal=0, field="Received"),
        trust=Trust.CLAIMED,
        usable_for_arrival_ordering=True,
    )
    fields.update(overrides)
    return TimeEvent(**fields)  # type: ignore[arg-type]


def test_timeevent_shape_is_frozen_field_for_field() -> None:
    """A field added, removed or reordered is a shape change -- a version bump, not a tweak."""
    assert [f.name for f in dataclasses.fields(TimeEvent)] == [
        "event_id",
        "doc_id",
        "kind",
        "when_raw",
        "when_utc",
        "offset",
        "offset_origin",
        "precision",
        "ambiguity",
        "source",
        "trust",
        "usable_for_arrival_ordering",
        "parent_event_id",
    ]


def test_unknown_relative_event_round_trips_byte_identically() -> None:
    """The spec's example: an order asserted but no absolute time is usable."""
    event = _event(
        when_utc=TimeValue(unknown_reason="relative"),
        offset=TimeValue(unknown_reason="absent"),
        offset_origin=OffsetOrigin.ABSENT,
        ambiguity=Ambiguity.RELATIVE,
    )
    payload = record_to_bytes(event)
    decoded = record_from_bytes(TimeEvent, payload)
    assert decoded == event
    assert record_to_bytes(decoded) == payload
    assert decoded.when_utc.is_unknown
    assert decoded.when_utc.value is None
    assert decoded.when_utc.unknown_reason == "relative"
    assert decoded.offset.unknown_reason == "absent"


def test_when_utc_cannot_also_carry_a_value() -> None:
    with pytest.raises(CodecError):
        TimeValue(value="2026-01-01T10:00:00Z", unknown_reason="relative")
    with pytest.raises(CodecError):
        _event(when_utc=TimeValue(value="2026-01-01T10:00:00Z", unknown_reason="relative"))


def test_when_utc_requires_exactly_one_of_value_or_unknown_reason() -> None:
    with pytest.raises(CodecError):
        TimeValue()
    with pytest.raises(CodecError):
        TimeValue(value=None, unknown_reason=None)


def test_offset_requires_exactly_one_of_value_or_unknown_reason() -> None:
    with pytest.raises(CodecError):
        _event(offset=TimeValue())
    with pytest.raises(CodecError):
        _event(offset=TimeValue(value="+02:00", unknown_reason="absent"))


def test_offset_origin_absent_requires_an_unknown_offset() -> None:
    with pytest.raises(CodecError):
        _event(offset=TimeValue(value="+02:00"), offset_origin=OffsetOrigin.ABSENT)
    assert _event(
        offset=TimeValue(unknown_reason="absent"), offset_origin=OffsetOrigin.ABSENT
    ).offset_origin is OffsetOrigin.ABSENT


def test_offset_origin_is_one_of_three_states() -> None:
    assert {o.value for o in OffsetOrigin} == {"stated_in_text", "derived_by_named_rule", "absent"}
    assert len(OffsetOrigin.__members__) == 3


def test_source_requires_exactly_one_of_field_property_part() -> None:
    with pytest.raises(CodecError):
        _event(source=TimeSource(ordinal=0))
    with pytest.raises(CodecError):
        _event(source=TimeSource(ordinal=0, field="Date", property="0x0039"))
    with pytest.raises(CodecError):
        _event(source=TimeSource(ordinal=0, field="Date", part="1.2"))
    with pytest.raises(CodecError):
        _event(source=TimeSource(ordinal=0, property="0x0039", part="1.2"))


def test_source_signatures_are_closed() -> None:
    assert {p.value for p in Precision} == {"year", "month", "day", "second"}
    assert len(Precision.__members__) == 4
    assert {a.value for a in Ambiguity} == {"none", "day_month", "timezone", "relative"}
    assert len(Ambiguity.__members__) == 4
    assert {t.value for t in Trust} == {"claimed", "derived", "user_supplied", "filesystem"}
    assert len(Trust.__members__) == 4


def test_calendar_facts_are_not_timeevents() -> None:
    """SEQUENCE/UID/METHOD are calendar facts, not TimeEvents; only DT* timestamps emit events."""
    shape = {f.name for f in dataclasses.fields(TimeEvent)}
    assert not (shape & {"sequence", "uid", "method", "attendee", "rsvp", "status", "recurrence_id"})


def test_timeevent_shape_has_its_own_version_constant() -> None:
    """D15: the TimeEvent shape is versioned by TIMEEVENT_VERSION, its own constant --
    it is not the record's OUTPUT_SCHEMA_VERSION and never rides on it."""
    assert "TIMEEVENT_VERSION" in vars(versions)
    assert versions.TIMEEVENT_VERSION == "1"
    source = pathlib.Path(versions.__file__).read_text(encoding="utf-8")
    assert re.search(r"^TIMEEVENT_VERSION\s*[:=]", source, re.MULTILINE)
    assert not re.search(r"^TIMEEVENT_VERSION\s*=\s*OUTPUT_SCHEMA_VERSION", source, re.MULTILINE)


# --------------------------------------------------- the invariants, enforced


def test_a_relative_time_is_never_resolved() -> None:
    """D15: a relative time is unknown(reason) *and* the shape refuses the other.

    The invariant is enforced at construction (mirroring workbookextract's copy),
    not only documented.
    """
    with pytest.raises(CodecError):
        _event(when_utc=TimeValue(value="2026-01-01T10:00:00Z"), ambiguity=Ambiguity.RELATIVE)
    with pytest.raises(CodecError):
        _event(when_utc=TimeValue(value="2026-01-01T10:00:00Z"), ambiguity="relative")
    # The legal neighbour: relative with an unknown when_utc constructs.
    event = _event(
        when_utc=TimeValue(unknown_reason="relative"),
        offset=TimeValue(unknown_reason="absent"),
        offset_origin=OffsetOrigin.ABSENT,
        ambiguity=Ambiguity.RELATIVE,
    )
    assert event.ambiguity is Ambiguity.RELATIVE
    assert event.when_utc.is_unknown


def test_a_filesystem_time_is_never_usable_for_arrival_ordering() -> None:
    """D15: the filesystem clock is not arrival evidence; the shape forbids the pair."""
    with pytest.raises(CodecError):
        _event(trust=Trust.FILESYSTEM, usable_for_arrival_ordering=True)
    with pytest.raises(CodecError):
        _event(trust="filesystem", usable_for_arrival_ordering=True)
    # The legal neighbour: recorded, but no policy may place it.
    event = _event(trust=Trust.FILESYSTEM, usable_for_arrival_ordering=False)
    assert event.trust is Trust.FILESYSTEM
    assert event.usable_for_arrival_ordering is False


def test_enum_fields_coerce_from_strings_at_construction() -> None:
    """A string value is coerced to its member, so a decoded record is canonical too."""
    event = _event(
        offset_origin="stated_in_text",
        precision="second",
        ambiguity="none",
        trust="claimed",
    )
    assert event.offset_origin is OffsetOrigin.STATED_IN_TEXT
    assert event.precision is Precision.SECOND
    assert event.ambiguity is Ambiguity.NONE
    assert event.trust is Trust.CLAIMED


def test_a_value_outside_the_vocabulary_raises_at_construction() -> None:
    """Not only when decoded from JSON: the vocabulary is closed on construction."""
    with pytest.raises(CodecError):
        _event(precision="fortnight")
    with pytest.raises(CodecError):
        _event(ambiguity="maybe")
    with pytest.raises(CodecError):
        _event(trust="everyone")
    with pytest.raises(CodecError):
        _event(offset_origin="somewhere")


# ------------------------------------- the doc-freeze cannot drift from the code

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIME_DOC = ROOT / "docs" / "design" / "timeevent.md"

_DATACLASSES = {"Span": Span, "TimeValue": TimeValue, "TimeSource": TimeSource, "TimeEvent": TimeEvent}
_ENUMS = {
    "OffsetOrigin": OffsetOrigin,
    "Precision": Precision,
    "Ambiguity": Ambiguity,
    "Trust": Trust,
}


def _shape_doc() -> dict:
    """The machine-readable JSON block ``docs/design/timeevent.md`` freezes the shape in."""
    text = TIME_DOC.read_text(encoding="utf-8")
    start = text.index("```json") + len("```json")
    start = text.index("\n", start) + 1
    end = text.index("```", start)
    return json.loads(text[start:end])


def test_the_dataclass_is_field_for_field_the_documented_shape() -> None:
    """A field added, removed or reordered is a shape change -- a doc change and a version bump."""
    declared = _shape_doc()["dataclasses"]
    assert set(declared) == set(_DATACLASSES), (
        "the document names a dataclass this module does not have (or misses one)"
    )
    for name, cls in _DATACLASSES.items():
        assert [field.name for field in dataclasses.fields(cls)] == declared[name]["fields"], name


def test_every_enum_is_member_for_member_the_documented_shape() -> None:
    declared = _shape_doc()["enums"]
    assert set(declared) == set(_ENUMS), "the document names an enum this module does not have"
    for name, cls in _ENUMS.items():
        assert [member.value for member in cls] == declared[name], name


def test_the_document_states_the_tri_state_the_one_of_and_the_version() -> None:
    doc = _shape_doc()
    assert doc["shape"] == "TimeEvent"
    assert doc["version_constant"] == "TIMEEVENT_VERSION"
    assert doc["dataclasses"]["TimeValue"]["tri_state"] is True
    assert doc["dataclasses"]["TimeSource"]["one_of"] == ["field", "property", "part"]
    assert doc["dataclasses"]["TimeValue"]["used_by"] == ["when_utc", "offset"]


def test_the_document_lists_the_open_kind_vocabulary() -> None:
    kind = _shape_doc()["open_vocabularies"]["kind"]
    assert kind["closed"] is False
    assert kind["shared_members"][-1] == "..."
    assert TimeEvent.__doc__ and kind["shared_members"][0] in TimeEvent.__doc__


def test_the_document_names_the_three_policies_and_no_implicit_policy() -> None:
    """D15: three named policies, and nothing runs by omission."""
    flat = " ".join(TIME_DOC.read_text(encoding="utf-8").split())
    for policy_id in ("header_date_claimed", "received_chain_header_order", "owner_manifest"):
        assert policy_id in flat, policy_id
    assert "header order and never by timestamp" in flat
    assert "nothing runs by omission" in flat
