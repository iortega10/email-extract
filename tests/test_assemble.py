"""Turn 1.9: ``assemble`` composes the stages into the one frozen ``EmailDocument``.

The rules under test: every axis Phase 1 does not build is the not-built idiom with
an empty value list (never ``None`` or ``[]`` standing in for "not built"); a built
axis is ``built_axis()``; the record round-trips through the strict codec; part ids
are content-addressed and unique within the document; the document key moves with a
projection version or a ``Limits`` field and never with a path or the environment;
the quote holder is exactly the rows the quote resolver produces; a hostile
container records its caps and never raises; and ``resolve_span`` maps a plain view
span to raw bytes where there is a within-part byte map and refuses, with its closed
reason, where there is none.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest
from docextract_core.codec import to_json

from emailextract import ids, store, versions
from emailextract.assemble import (
    Unresolvable,
    assemble,
    document_key,
    identity_projection,
    limits_fingerprint,
    projection_versions,
    resolve_span,
)
from emailextract.container import EmlContainer, memory_bytes
from emailextract.model import (
    EmailDocument,
    Span,
    Status,
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
    TimeEvent,
    TimeSource,
    TimeValue,
    Trust,
)
from emailextract.parse import Limits
from emailextract.quote import resolve as quote_resolve
from emailextract.walk import walk

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

#: The library modules themselves. ``from emailextract import assemble`` gives the
#: function (the package re-exports it), so the modules are fetched by name for the
#: mutations.
assemble_module = importlib.import_module("emailextract.assemble")

MESSAGE = (
    b"From: Ada <ada@example.com>\r\n"
    b"To: Ben <ben@example.com>\r\n"
    b"Subject: assemble\r\n"
    b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
    b"Message-ID: <assemble@example.com>\r\n"
    b"\r\n"
    b"Hello Ben.\r\n"
)

#: The four document axes Phase 1 declares and does not build.
AXES = ("times", "thread_edges", "children", "same_message_candidates")


def _fixture_paths() -> list[Path]:
    """Every committed ``.eml`` under ``fixtures/`` (``fixtures/real/`` is machine-local)."""
    return [
        path
        for path in sorted(FIXTURES.rglob("*.eml"))
        if "real" not in path.relative_to(FIXTURES).parts
    ]


def _limits() -> Limits:
    return Limits.untrusted()


def _time_event() -> TimeEvent:
    return TimeEvent(
        event_id="e1",
        doc_id="d1",
        kind="authored",
        when_raw="Tue, 4 Mar 2025 09:00:00 +0000",
        when_utc=TimeValue(value="2025-03-04T09:00:00+00:00"),
        offset=TimeValue(value="+00:00"),
        offset_origin=OffsetOrigin.STATED_IN_TEXT,
        precision=Precision.SECOND,
        ambiguity=Ambiguity.NONE,
        source=TimeSource(ordinal=0, field="Date", span=Span(start=0, end=9)),
        trust=Trust.CLAIMED,
        usable_for_arrival_ordering=True,
    )


# --------------------------------------------------------------- the axes


def test_every_document_axis_is_not_built_in_phase1() -> None:
    """Every axis Phase 1 does not build is the marker, with an empty value list."""
    document = assemble(EmlContainer(memory_bytes(MESSAGE)), limits=_limits())
    built = {
        "times": (document.times, document.times_axis),
        "thread_edges": (document.thread_edges, document.thread_edges_axis),
        "children": (document.children, document.children_axis),
        "same_message_candidates": (
            document.same_message_candidates,
            document.same_message_candidates_axis,
        ),
    }
    assert set(built) == set(AXES)
    for name, (value, axis) in built.items():
        axis_id(f"document.{name}")
        assert value == [], name
        assert axis == not_built_in_phase1(), name
        assert axis.state is TriState.UNKNOWN and axis.reason_id == ids.NOT_BUILT_IN_PHASE1


def test_a_built_axis_is_not_the_not_built_marker() -> None:
    """A built axis is ``built_axis()``: never the marker, and never a bare empty list."""
    assert built_axis() != not_built_in_phase1()
    assert built_axis().state is TriState.VALUE and built_axis().value == "built"

    assembled = assemble(EmlContainer(memory_bytes(MESSAGE)), limits=_limits())
    built = dataclasses.replace(assembled, times=[_time_event()], times_axis=built_axis())
    assert built.times_axis == built_axis()
    # A present value beside the not-built marker is unrepresentable: the contract refuses.
    with pytest.raises(Exception):
        dataclasses.replace(assembled, times=[_time_event()])
    # ... and so is an empty list beside the built marker ("empty but built").
    with pytest.raises(Exception):
        dataclasses.replace(assembled, times_axis=built_axis())


def test_no_record_claims_a_phase2_axis() -> None:
    """No axis of an assembled document is built: a Phase 1 build claims no Phase 2 fact."""
    for path in _fixture_paths():
        document = assemble(EmlContainer(path.read_bytes()), limits=_limits())
        for name in AXES:
            value = getattr(document, name)
            axis = getattr(document, f"{name}_axis")
            assert value == [], f"{path.name}: {name}"
            assert axis.state is TriState.UNKNOWN and axis.reason_id == ids.NOT_BUILT_IN_PHASE1, (
                f"{path.name}: {name} claims a built axis"
            )


# --------------------------------------------------------------- the codec


def test_the_record_round_trips_through_the_strict_codec() -> None:
    """The assembled document encodes and decodes byte-identically, strictly."""
    document = assemble(EmlContainer(memory_bytes(MESSAGE)), limits=_limits())
    payload = record_to_bytes(document)
    assert record_from_bytes(EmailDocument, payload) == document
    assert record_to_bytes(record_from_bytes(EmailDocument, payload)) == payload
    assert document.quote_boundaries == [] and document.view_levels == []


def test_the_quote_boundaries_round_trip_through_the_codec() -> None:
    """A document with quote rows survives the codec with the rows intact."""
    raw = (FIXTURES / "generated" / "gmail_short_reply_gt_and_on_wrote.eml").read_bytes()
    document = assemble(EmlContainer(memory_bytes(raw)), limits=_limits())
    assert document.quote_boundaries, "the fixture must carry at least one boundary"
    payload = record_to_bytes(document)
    decoded = record_from_bytes(EmailDocument, payload)
    assert decoded == document
    assert decoded.quote_boundaries == document.quote_boundaries
    assert decoded.view_levels == document.view_levels


def test_the_projection_versions_are_the_constants_names_and_values() -> None:
    """``RunRecord.projection_versions`` is keyed by each constant's own name."""
    stamped = projection_versions()
    assert set(stamped) == set(assemble_module.PROJECTION_VERSION_NAMES)
    for name, value in stamped.items():
        assert getattr(versions, name) == value
    document = assemble(EmlContainer(memory_bytes(MESSAGE)), limits=_limits())
    assert document.run_record is not None
    assert document.run_record.projection_versions == stamped
    assert document.output_schema_version == versions.OUTPUT_SCHEMA_VERSION == "5"


def test_a_nested_record_read_from_a_store_carries_its_own_axes(tmp_path: Path) -> None:
    """A document read back keeps its axes, and each nested occurrence keeps its own."""
    raw = (FIXTURES / "generated" / "attach_manifest_baseline.eml").read_bytes()
    container = EmlContainer(memory_bytes(raw))
    limits = _limits()
    store_root = tmp_path / "store"
    collection = store.document_store(store_root)
    artifact, created = store.store_document(container, collection, limits=limits)
    assert created is True
    assert artifact.document.attachments, "the fixture must carry occurrences"

    read_back = store.read_document(collection, artifact.key)
    assert read_back is not None
    assert read_back == artifact.document
    # The document's own axes survive the round trip through the store.
    for name in AXES:
        assert getattr(read_back, name) == []
        assert getattr(read_back, f"{name}_axis") == not_built_in_phase1()
    # ... and so does each nested occurrence's own axis pair (decision 6: a record has
    # an axis field iff it has the value field -- there is no document-level "deferred").
    for occurrence in read_back.attachments:
        assert occurrence.status_axis.state is TriState.UNKNOWN
        assert occurrence.status_axis.reason_id == ids.NOT_BUILT_IN_PHASE1
        assert occurrence.route_axis == not_built_in_phase1()
        assert occurrence.status is None and occurrence.route is None


# --------------------------------------------------------------- part ids


def test_part_ids_are_stable_unique_and_content_addressed() -> None:
    """Every part carries ``ids.part_id(container hash, raw span, content hash)``."""
    raw = (FIXTURES / "generated" / "nested_alternative_in_related_in_mixed.eml").read_bytes()
    limits = _limits()
    first = assemble(EmlContainer(memory_bytes(raw)), limits=limits)
    second = assemble(EmlContainer(memory_bytes(raw)), limits=limits)
    assert len(first.parts) > 2
    assert [part.part_id for part in first.parts] == [part.part_id for part in second.parts]
    ids_ = [part.part_id for part in first.parts]
    assert len(ids_) == len(set(ids_)), "a part id must be unique within the document"
    # The id is content-addressed, not a locator: it is not the ``1.2.3`` path, and it
    # equals ids.part_id over the walker's own raw span and content hash.
    result = walk(EmlContainer(memory_bytes(raw)))
    for part in result.parts:
        expected = ids.part_id(
            result.container_hash, part.raw_span, ids.content_hash(part.raw_span.slice(raw))
        )
        assert part.part_id == expected
    assert set(ids_).isdisjoint({part.path for part in result.parts})
    # The parent link names the parent's id, resolved through the tree.
    by_id = {part.part_id: part for part in first.parts}
    for record in first.parts:
        if record.parent_part_id is not None:
            assert record.parent_part_id in by_id


def test_every_committed_fixture_assembles_to_a_parsed_record() -> None:
    """Every fixture assembles, round-trips and says ``parsed`` -- no fixture is skipped."""
    paths = _fixture_paths()
    assert len(paths) >= 100, len(paths)
    for path in paths:
        raw = path.read_bytes()
        document = assemble(EmlContainer(memory_bytes(raw)), limits=_limits())
        assert isinstance(document, EmailDocument), path.name
        assert document.status.status is Status.PARSED, (path.name, document.status)
        assert document.container_hash == ids.container_hash(raw), path.name
        payload = record_to_bytes(document)
        assert record_from_bytes(EmailDocument, payload) == document, path.name
        assert document.parts, path.name
        for record in document.parts:
            assert record.part_id, path.name


def test_a_hostile_container_records_its_caps_and_does_not_raise() -> None:
    """A cap fixture under tight limits records every cap and never raises."""
    tight = Limits(
        max_input_bytes=64 * 1024 * 1024,
        max_depth=2,
        max_parts=3,
        max_header_bytes=64,
        max_decoded_part_bytes=64,
        max_decoded_total_bytes=128,
        max_field_work_units_per_byte=1,
    )
    for name in ("cap_deep_nesting.eml", "cap_large_part_count.eml", "cap_enormous_header_block.eml"):
        raw = (FIXTURES / "generated" / name).read_bytes()
        document = assemble(EmlContainer(memory_bytes(raw)), limits=tight)
        assert document.run_record is not None
        assert document.run_record.caps, name
        assert document.status.status in (Status.PARSED, Status.SKIPPED), name
        for cap in document.run_record.caps:
            assert cap.cap_id in walk_cap_reasons()
            assert cap.cap_value_bytes > 0
        # The record still round-trips with the caps in it.
        payload = record_to_bytes(document)
        assert record_from_bytes(EmailDocument, payload) == document, name


def walk_cap_reasons() -> tuple[str, ...]:
    from emailextract.walk import CAP_REASONS

    return CAP_REASONS


# --------------------------------------------------------------- the document key


def test_the_document_key_moves_with_a_projection_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """A moved projection version is a different key, and so is a moved record version."""
    container = EmlContainer(memory_bytes(MESSAGE))
    limits = _limits()
    before = document_key(container.container_hash(), limits=limits)
    monkeypatch.setattr(versions, "QUOTE_RULES_VERSION", versions.QUOTE_RULES_VERSION + ".bumped")
    assert document_key(container.container_hash(), limits=limits) != before


def test_the_document_key_moves_with_a_limits_field() -> None:
    """A raised cap is a different run: every canonical ``Limits`` field is in the key."""
    container = EmlContainer(memory_bytes(MESSAGE))
    base = _limits()
    before = document_key(container.container_hash(), limits=base)
    for name in dataclasses.fields(Limits):
        raised = dataclasses.replace(base, **{name.name: getattr(base, name.name) + 1})
        assert limits_fingerprint(raised) != limits_fingerprint(base), name.name
        assert document_key(container.container_hash(), limits=raised) != before, name.name
    # The fingerprint is a digest of the fields, in declaration order.
    assert len(limits_fingerprint(base)) == 64


def test_a_path_or_the_environment_never_moves_the_document_key(tmp_path: Path) -> None:
    """A path is provenance, not identity: one key for the same bytes under two paths."""
    path_a = tmp_path / "one.eml"
    path_b = tmp_path / "nested" / "two.eml"
    path_b.parent.mkdir()
    for path in (path_a, path_b):
        path.write_bytes(MESSAGE)
    limits = _limits()
    keys = {
        document_key(EmlContainer(path).container_hash(), limits=limits)
        for path in (path_a, path_b)
    }
    keys.add(document_key(EmlContainer(memory_bytes(MESSAGE)).container_hash(), limits=limits))
    assert len(keys) == 1
    # The key is the hashed inputs and nothing else -- no path, no interpreter.
    assert keys.pop() == document_key(ids.container_hash(MESSAGE), limits=limits)


def test_the_identity_projection_drops_the_recorded_only_inputs() -> None:
    """The identity projection keeps the evidence and drops what rendered it."""
    raw = (FIXTURES / "generated" / "attach_manifest_baseline.eml").read_bytes()
    document = assemble(EmlContainer(memory_bytes(raw)), limits=_limits())
    projection = identity_projection(document)
    assert projection.run_record is not None and document.run_record is not None
    assert projection.run_record.projection_versions == {}
    assert projection.run_record.environment == {}
    assert projection.run_record.caps == document.run_record.caps
    assert projection.run_record.run_id == document.run_record.run_id
    assert projection.parts == document.parts
    assert projection.quote_boundaries == document.quote_boundaries
    assert to_json(projection) != to_json(document)


# --------------------------------------------------------------- the quote holder


def test_the_quote_holder_rows_equal_the_resolvers_rows() -> None:
    """The holder cannot drift from the oracle: its rows are the resolver's rows."""
    limits = _limits()
    seen = 0
    for path in _fixture_paths():
        raw = path.read_bytes()
        result = walk(EmlContainer(memory_bytes(raw)))
        document = assemble(EmlContainer(memory_bytes(raw)), limits=limits)
        rows = quote_resolve.all_quote_boundary_rows(
            raw, result, max_depth=limits.max_depth, max_elements=limits.max_parts
        )
        holder = [
            (
                b.rule_id,
                b.kind.value,
                b.ordinal,
                list(b.prefix_depth),
                b.span.start,
                b.span.end - b.span.start,
            )
            for b in document.quote_boundaries
        ]
        assert holder == [tuple(row[2:]) for row in rows], path.name
        levels = quote_resolve.all_view_level_rows(
            raw, result, max_depth=limits.max_depth, max_elements=limits.max_parts
        )
        assert [(lvl.quote_level, lvl.resolution_rule_id) for lvl in document.view_levels] == [
            tuple(row[2:]) for row in levels
        ], path.name
        seen += len(rows)
    assert seen > 0, "no fixture carries a quote boundary: the comparison would be vacuous"


# --------------------------------------------------------------- resolve_span


def test_resolve_span_maps_a_plain_view_span_to_the_raw_bytes() -> None:
    """A plain span of an identity-decoded part maps to exactly those raw bytes."""
    raw = (FIXTURES / "generated" / "plain_simple.eml").read_bytes()
    container = EmlContainer(memory_bytes(raw))
    document = assemble(container, limits=_limits())
    part = document.parts[0]
    span = resolve_span(container, part.part_id, "plain", 0, 5)
    assert not isinstance(span, Unresolvable)
    assert span.slice(raw) == b"Hello"
    assert span.locator == "1"
    # The whole view maps to the whole (identity-decoded) body.
    whole = resolve_span(container, part.part_id, "plain", 0, span_text_length(raw))
    assert not isinstance(whole, Unresolvable)
    assert whole.length > 0
    # An empty span at the end of the view is an empty span, not a refusal.
    empty = resolve_span(container, part.part_id, "plain", 0, 0)
    assert not isinstance(empty, Unresolvable) and empty.length == 0


def span_text_length(raw: bytes) -> int:
    from emailextract.text import analyse_part

    return len(analyse_part(raw, walk(EmlContainer(memory_bytes(raw))).parts[0]).text)


def test_resolve_span_refuses_where_there_is_no_within_part_byte_map() -> None:
    """Flow, a non-identity decode, the html view, a bad part and a bad span all refuse."""
    limits = _limits()
    flowed_raw = (FIXTURES / "generated" / "flowed_unstuffed_soft_break.eml").read_bytes()
    flowed = EmlContainer(memory_bytes(flowed_raw))
    flowed_doc = assemble(flowed, limits=limits)
    refused = resolve_span(flowed, flowed_doc.parts[0].part_id, "plain", 0, 3)
    assert isinstance(refused, Unresolvable)
    assert refused.reason_id == ids.SPAN_NOT_RESOLVABLE
    assert refused.part_id == flowed_doc.parts[0].part_id

    html_raw = (FIXTURES / "generated" / "html_only.eml").read_bytes()
    html = EmlContainer(memory_bytes(html_raw))
    html_doc = assemble(html, limits=limits)
    html_part = next(part for part in html_doc.parts if part.content_type == "text/html")
    assert isinstance(resolve_span(html, html_part.part_id, "html", 0, 3), Unresolvable)

    # A non-identity transport decode: the offset map is absent (``cte_not_identity``).
    encoded = EmlContainer(
        memory_bytes(
            b"From: a@example.com\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"SGVsbG8gQmVuLg0K\r\n"
        )
    )
    encoded_doc = assemble(encoded, limits=limits)
    assert encoded_doc.parts[0].content_type == "text/plain"
    refused_cte = resolve_span(encoded, encoded_doc.parts[0].part_id, "plain", 0, 3)
    assert isinstance(refused_cte, Unresolvable)
    assert refused_cte.reason_id == ids.SPAN_NOT_RESOLVABLE

    # An unknown part, an unknown view and a span outside the view all refuse.
    plain_raw = (FIXTURES / "generated" / "plain_simple.eml").read_bytes()
    plain = EmlContainer(memory_bytes(plain_raw))
    plain_part = assemble(plain, limits=limits).parts[0].part_id
    assert isinstance(resolve_span(plain, "not-a-part-id", "plain", 0, 3), Unresolvable)
    assert isinstance(resolve_span(plain, plain_part, "html", 0, 3), Unresolvable)
    assert isinstance(resolve_span(plain, plain_part, "plain", 0, 10**9), Unresolvable)


def test_resolve_span_refuses_a_document_because_it_stores_no_body_text() -> None:
    """A document carries no text: a citation must be made against the container."""
    raw = (FIXTURES / "generated" / "plain_simple.eml").read_bytes()
    document = assemble(EmlContainer(memory_bytes(raw)), limits=_limits())
    with pytest.raises(TypeError):
        resolve_span(document, document.parts[0].part_id, "plain", 0, 3)  # type: ignore[arg-type]


# --------------------------------------------------------------- mutations


def test_a_not_built_axis_without_the_marker_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: return the axis as a bare ``TriValue()`` (no marker); the record differs.

    The anti-vacuity triple: (a) the patched symbol exists -- ``monkeypatch.setattr``
    would raise otherwise; (b) the patch is **reached**, proved by the counter; (c) the
    observation differs -- the contract refuses the empty-list-without-the-marker pair,
    so the guard records a failure instead of a parsed document.
    """
    real = assemble_module.not_built_in_phase1
    assert callable(real)
    reached = {"count": 0}

    def unmarked() -> TriValue:
        reached["count"] += 1
        return TriValue()

    monkeypatch.setattr(assemble_module, "not_built_in_phase1", unmarked)
    document = assemble(EmlContainer(memory_bytes(MESSAGE)), limits=_limits())
    assert reached["count"] > 0, "the mutation's patch was never entered (vacuous)"
    assert document.status.status is Status.FAILED
    assert document.status.reason == "extractor_error"
    assert document.times == []
    assert document.times_axis != built_axis()

