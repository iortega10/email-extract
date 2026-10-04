"""Turn 1.0b: decision 6 -- the not-built idiom and the per-record axis fields.

One "not built" idiom, one representation: ``TriValue(state=UNKNOWN,
reason_id=NOT_BUILT_IN_PHASE1)``. ``None`` keeps its single meaning (no such axis,
or the input did not exercise the field) and an empty list keeps its single meaning
(genuinely empty); neither is ever the encoding of "not built". The pairing
invariant lives in the parent record's ``__post_init__`` and never in either
field's type, and a union ``X | NotBuilt`` is refused because the core codec
decodes a union by its first non-``None`` member.
"""

from __future__ import annotations

import dataclasses

import pytest
from docextract_core.codec import SCHEMA_VERSION, CodecError, from_json, to_json

from emailextract import ids
from emailextract.model import (
    AXIS_IDS,
    AttachmentOccurrence,
    BodyView,
    ContainerFacts,
    ContainerKind,
    ContentFingerprint,
    EmailDocument,
    Status,
    StatusOutcome,
    TriState,
    TriValue,
    axis_id,
    built_axis,
    not_built_in_phase1,
    record_from_bytes,
    record_to_bytes,
)
from emailextract.timeevent import (
    Ambiguity,
    OffsetOrigin,
    Precision,
    Span,
    TimeEvent,
    TimeSource,
    TimeValue,
    Trust,
)

#: (parent record, value field, axis field) -- decision 6's per-record axes.
AXIS_PAIRS = (
    (AttachmentOccurrence, "status", "status_axis"),
    (AttachmentOccurrence, "route", "route_axis"),
    (EmailDocument, "times", "times_axis"),
    (EmailDocument, "thread_edges", "thread_edges_axis"),
    (EmailDocument, "children", "children_axis"),
    (EmailDocument, "same_message_candidates", "same_message_candidates_axis"),
)

BUILT = TriValue(state=TriState.VALUE, value="built")


def _occurrence(**overrides) -> AttachmentOccurrence:
    fields: dict[str, object] = dict(
        attachment_id="a" * 64, occurrence_path="1.2@0", part_id="1.2"
    )
    fields.update(overrides)
    return AttachmentOccurrence(**fields)  # type: ignore[arg-type]


def test_axis_field_requires_its_value_field() -> None:
    """(I1) a record has an axis field iff it has the value field -- and no others."""
    for record, value_field, axis_field in AXIS_PAIRS:
        names = {field.name for field in dataclasses.fields(record)}
        assert value_field in names, f"{record.__name__} has {axis_field} but no {value_field}"
        assert axis_field in names, f"{record.__name__} has {value_field} but no {axis_field}"
    # The axis fields present on a record are exactly those with a value field: no
    # orphan axis, no wildcard id.
    for record in (AttachmentOccurrence, EmailDocument):
        names = {field.name for field in dataclasses.fields(record)}
        expected = {axis for cls, _value, axis in AXIS_PAIRS if cls is record}
        present = {name for name in names if name.endswith("_axis")}
        assert present == expected, record.__name__
    # Every declared axis id belongs to exactly one record family, and none is a wildcard.
    assert len(AXIS_IDS) == len(set(AXIS_IDS)) == 6
    assert not any("*" in name for name in AXIS_IDS)


def test_phase1_status_is_none_iff_the_axis_is_not_built() -> None:
    """(I2) in a Phase 1 build, ``status is None`` iff the axis is the not-built value."""
    empty = _occurrence()
    assert empty.status is None
    assert empty.status_axis == not_built_in_phase1()
    assert empty.status_axis.reason_id == ids.NOT_BUILT_IN_PHASE1

    # not-built implies no value: a value beside the not-built marker is unrepresentable.
    with pytest.raises(CodecError):
        _occurrence(status=StatusOutcome(status=Status.PARSED))

    # ... and None beside the built marker is unrepresentable too ("empty but built").
    with pytest.raises(CodecError):
        _occurrence(status_axis=BUILT)

    # The contract never depends on the current phase: a consulted-and-unknown axis
    # (a reason other than not-built) is a legal no-value state.
    consulted = _occurrence(status_axis=TriValue(state=TriState.UNKNOWN, reason_id="probe_failed"))
    assert consulted.status is None


def test_built_status_carries_the_built_axis_marker() -> None:
    """(I3) ``status`` is a ``StatusOutcome`` iff ``status_axis`` is ``VALUE("built")``."""
    occurrence = _occurrence(status=StatusOutcome(status=Status.PARSED), status_axis=built_axis())
    assert occurrence.status_axis.state is TriState.VALUE
    assert occurrence.status_axis.value == "built"
    payload = record_to_bytes(occurrence)
    assert record_from_bytes(AttachmentOccurrence, payload) == occurrence
    assert record_to_bytes(record_from_bytes(AttachmentOccurrence, payload)) == payload

    # A built marker that names anything other than "built" is refused.
    with pytest.raises(CodecError):
        _occurrence(
            status=StatusOutcome(status=Status.PARSED),
            status_axis=TriValue(state=TriState.VALUE, value="not-built"),
        )
    # A winner-less built verdict still needs its value; the marker is not the value.
    with pytest.raises(CodecError):
        _occurrence(status_axis=TriValue(state=TriState.ABSENT))


@dataclasses.dataclass(frozen=True)
class _UnionHolder:
    """A throwaway record whose field is a union, to prove a union would not round-trip."""

    field: StatusOutcome | TriValue | None = None


def test_an_impossible_axis_pair_raises() -> None:
    """(I4) any pair other than the two legal ones raises, and a union is not the way out."""
    # A value with the not-built marker (the "forgot the marker" record).
    with pytest.raises(CodecError):
        _occurrence(
            status=StatusOutcome(status=Status.PARSED),
            status_axis=not_built_in_phase1(),
        )
    # An absence with a marker that is not unknown.
    with pytest.raises(CodecError):
        _occurrence(status_axis=TriValue(state=TriState.ABSENT))
    # The route axis is symmetric.
    with pytest.raises(CodecError):
        _occurrence(route="mime")
    # A populated document axis with the not-built marker: unrepresentable.
    with pytest.raises(CodecError):
        EmailDocument(
            container_kind=_container_kind(),
            container_hash="a" * 64,
            container_facts=_container_facts(),
            content_fingerprint=_fingerprint(),
            status=StatusOutcome(status=Status.PARSED),
            times=[_time_event()],
        )

    # A union ``X | NotBuilt`` is forbidden exactly because the core codec decodes a
    # union by its first non-None member: a TriValue in a StatusOutcome | TriValue
    # field decodes as a StatusOutcome and raises. This test exists so nobody
    # reintroduces the union.
    holder = _UnionHolder(field=not_built_in_phase1())
    payload = to_json(holder, schema_version=SCHEMA_VERSION, indent=None)
    with pytest.raises(CodecError):
        from_json(_UnionHolder, payload, strict=True, schema_version=SCHEMA_VERSION)


def test_not_built_in_phase1_is_registered_and_the_axis_ids_are_closed() -> None:
    """The constant is registered beside the phase-0 one, and the axis-id tuple is closed."""
    assert ids.NOT_BUILT_IN_PHASE1 == "not_built_in_phase1"
    assert ids.NOT_BUILT_IN_PHASE1 != ids.NOT_BUILT_IN_PHASE0
    assert "NOT_BUILT_IN_PHASE1" in ids.__all__
    for name in AXIS_IDS:
        assert axis_id(name) == name
    # A wildcard id (and any id outside the tuple) is refused.
    for bad in ("*", "attachment.*", "document.axes", ""):
        with pytest.raises(CodecError):
            axis_id(bad)


# -- tiny valid constructors for the impossible-pair checks -----------------


def _container_kind() -> ContainerKind:
    return ContainerKind.RFC822


def _container_facts() -> ContainerFacts:
    return ContainerFacts({})


def _fingerprint() -> ContentFingerprint:
    return ContentFingerprint(body_digest="b" * 64, body_digest_view=BodyView.PLAIN)


def _time_event() -> TimeEvent:
    return TimeEvent(
        event_id="e1",
        doc_id="d1",
        kind="authored",
        when_raw="Tue, 4 Mar 2025 08:05:00 +0000",
        when_utc=TimeValue(value="2025-03-04T08:05:00+00:00"),
        offset=TimeValue(value="+00:00"),
        offset_origin=OffsetOrigin.STATED_IN_TEXT,
        precision=Precision.SECOND,
        ambiguity=Ambiguity.NONE,
        source=TimeSource(ordinal=0, field="Date", span=Span(start=0, end=9)),
        trust=Trust.CLAIMED,
        usable_for_arrival_ordering=True,
    )
