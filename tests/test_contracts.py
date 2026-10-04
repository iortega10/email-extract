"""Turn 0.1 tests: every frozen record round-trips byte-identically through the core codec.

Hand-typed ground truth: no record shape is imported from a table and no expected
value is copied from an implementation. Covers the round-trip of every record,
unknown-key rejection at every depth, and the reserved FlagSection being
present-but-empty and round-tripping.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from docextract_core.codec import CodecError, SCHEMA_VERSION

import emailextract.model as model
import emailextract.timeevent as timeevent
from emailextract import (
    Ambiguity,
    AttachmentOccurrence,
    BodyView,
    ChildLink,
    ChildLinkState,
    Classification,
    ClassificationClaim,
    ContainerFacts,
    ContainerKind,
    ContentFingerprint,
    DecodeChain,
    DecorativeHint,
    DecorativeHintState,
    EmailDocument,
    EncodingSource,
    FlagHit,
    FlagRollup,
    FlagSection,
    GroupCount,
    HeaderField,
    HitLocation,
    MatchType,
    OffsetOrigin,
    PartRecord,
    Precision,
    QuoteCrossCheck,
    RollupScope,
    RunRecord,
    Selection,
    SameMessageCandidate,
    Span,
    Status,
    StatusOutcome,
    ThreadEdge,
    ThreadSource,
    TimeEvent,
    TimeSource,
    TimeValue,
    TriState,
    TriValue,
    Trust,
    TypeVerdicts,
    TypeVerdictSource,
    record_from_bytes,
    record_to_bytes,
)
from emailextract.model import (
    BoundaryKind,
    CapRecord,
    QuoteBoundary,
    ViewLevel,
    built_axis,
)


def _flag_hit() -> FlagHit:
    return FlagHit(
        term_group_id="group-1",
        term_form="invoice",
        match_type=MatchType.EXACT,
        location=HitLocation(part="1.2", view="body.html", span=Span(start=10, end=17), unit=3),
        view_id="body.html",
        quote_boundary_ordinal=2,
        quote_kind="quoted",
        matcher_version="1",
    )


def _flag_section() -> FlagSection:
    return FlagSection(
        terms=["invoice", "payment"],
        term_list_hash="9" * 64,
        matcher_version="1",
        hits=[_flag_hit()],
        rollup=FlagRollup(
            scope=RollupScope.BODY_VIEW,
            counts_by_group=[GroupCount(term_group_id="group-1", count=2, ordinal=3, quote_kind="quoted")],
            quoted_counts_by_group=[GroupCount(term_group_id="group-1", count=1, ordinal=3, quote_kind="quoted")],
        ),
    )


def _time_event() -> TimeEvent:
    return TimeEvent(
        event_id="ev-2",
        doc_id="doc-1",
        parent_event_id="ev-1",
        kind="received_hop",
        when_raw="Thu, 01 Jan 2026 12:00:00 +0200",
        when_utc=TimeValue(value="2026-01-01T10:00:00Z"),
        offset=TimeValue(value="+02:00"),
        offset_origin=OffsetOrigin.STATED_IN_TEXT,
        precision=Precision.SECOND,
        ambiguity=Ambiguity.NONE,
        source=TimeSource(ordinal=1, field="Received", span=Span(start=5, end=45)),
        trust=Trust.CLAIMED,
        usable_for_arrival_ordering=True,
    )


def _email_document() -> EmailDocument:
    return EmailDocument(
        container_kind=ContainerKind.CFB_MSG,
        container_hash="a" * 64,
        container_facts=ContainerFacts({"sector_size": "512", "streams": "12", "property_set": "nameid"}),
        content_fingerprint=ContentFingerprint(body_digest="b" * 64, body_digest_view=BodyView.HTML),
        status=StatusOutcome(status=Status.PARSED),
        headers=[
            HeaderField(
                name="Date",
                raw_value="Thu, 01 Jan 2026 12:00:00 +0200",
                ordinal=0,
                value=TriValue(state=TriState.VALUE, value="2026-01-01T10:00:00Z"),
            )
        ],
        parts=[
            PartRecord(
                part_id="1",
                content_type="multipart/alternative",
                role="container",
                classification=Classification.UNKNOWN,
                selection=Selection.NOT_APPLICABLE,
                decorative_hint=DecorativeHint(),
            ),
            PartRecord(
                part_id="1.2",
                parent_part_id="1",
                content_type="text/html",
                role="body",
                classification=Classification.INLINE,
                selection=Selection.SELECTED,
                size_bytes=2048,
                sha256="c" * 64,
                encoding_source=EncodingSource.DECLARED_CHARSET,
                decode_chain=DecodeChain(
                    declared_cte="quoted-printable",
                    declared_charset="utf-8",
                    used_cte="quoted-printable",
                    used_charset="utf-8",
                    fallback_fired=False,
                ),
                decorative_hint=DecorativeHint(state=DecorativeHintState.RULE_ID, rule_id="decorative.rule.border"),
                type_verdicts=TypeVerdicts(
                    declared_mime=TriValue(state=TriState.VALUE, value="text/html"),
                    magic=TriValue(state=TriState.VALUE, value="text/html"),
                    winner=TypeVerdictSource.DECLARED_MIME,
                    disagreement=False,
                ),
            ),
        ],
        attachments=[
            AttachmentOccurrence(
                attachment_id="d" * 64,
                occurrence_path="1.3@0",
                part_id="1.3",
                classification=Classification.ATTACHMENT,
                selection=Selection.NOT_APPLICABLE,
                status=StatusOutcome(status=Status.SKIPPED, reason="size_cap"),
                status_axis=built_axis(),
                filename_raw="=?utf-8?b?ZmlsZS56aXA=?=",
                filename_decoded=TriValue(state=TriState.UNKNOWN, reason_id="decode_failed"),
                cid="<img-1@example>",
                size_bytes=1234,
                sha256="e" * 64,
                route="mime",
                route_axis=built_axis(),
                encoding_source=EncodingSource.FALLBACK,
                decode_chain=DecodeChain(used_charset="windows-1252", fallback_fired=True),
                decorative_hint=DecorativeHint(),
                type_verdicts=TypeVerdicts(
                    magic=TriValue(state=TriState.VALUE, value="application/zip"),
                    winner=TypeVerdictSource.MAGIC,
                    disagreement=True,
                ),
            )
        ],
        children=[
            ChildLink(
                state=ChildLinkState.RESOLVED,
                child_id="child-1",
                store_id="store-1",
                expected_version="1",
                found_version="1",
            )
        ],
        children_axis=built_axis(),
        thread_edges=[
            ThreadEdge(
                child_message_id="<b@example>",
                parent_message_id="<a@example>",
                source=ThreadSource.REFERENCES,
                trust=Trust.CLAIMED,
                cross_check=QuoteCrossCheck.CONFLICTS,
            )
        ],
        thread_edges_axis=built_axis(),
        times=[_time_event()],
        times_axis=built_axis(),
        same_message_candidates=[
            SameMessageCandidate(
                left_container_hash="f" * 64,
                right_container_hash="g" * 64,
                message_id_claimed="<a@example>",
                body_digest="b" * 64,
                body_digest_view=BodyView.HTML,
            )
        ],
        same_message_candidates_axis=built_axis(),
        classification_hint=ClassificationClaim(hint="msip.label", source="exchange_property"),
        run_record=RunRecord(
            run_id="run-1",
            caps=[
                CapRecord(
                    cap_id="attachment_size", cap_value_bytes=262144, declared_size_bytes=1234
                )
            ],
            environment={"olefile": "installed"},
        ),
        output_schema_version="1",
        flags=FlagSection(),
    )


# One hand-typed instance per record contract.
RECORDS = {
    Span: Span(start=12, end=34),
    TimeValue: TimeValue(unknown_reason="relative"),
    TimeSource: TimeSource(ordinal=0, part="1.2", span=Span(start=0, end=9)),
    TimeEvent: _time_event(),
    TriValue: TriValue(state=TriState.UNKNOWN, reason_id="decode_failed"),
    DecorativeHint: DecorativeHint(state=DecorativeHintState.RULE_ID, rule_id="decorative.rule.border"),
    StatusOutcome: StatusOutcome(status=Status.FAILED, reason="extractor_error"),
    ClassificationClaim: ClassificationClaim(hint="msip.label", source="exchange_property"),
    DecodeChain: DecodeChain(declared_cte="base64", used_cte="base64", fallback_fired=True),
    TypeVerdicts: TypeVerdicts(
        magic=TriValue(state=TriState.VALUE, value="application/pdf"),
        winner=TypeVerdictSource.MAGIC,
        disagreement=True,
    ),
    CapRecord: CapRecord(
        cap_id="attachment_size", cap_value_bytes=262144, declared_size_bytes=1234
    ),
    QuoteBoundary: QuoteBoundary(
        rule_id="on_wrote_en",
        kind=BoundaryKind.QUOTE,
        span=Span(start=30, end=290),
        ordinal=1,
        prefix_depth=[0, 0, 0, 0],
    ),
    ViewLevel: ViewLevel(
        view_id="plain",
        span=Span(start=0, end=300),
        quote_level=1,
        resolution_rule_id="on_wrote_en",
        disagreement=False,
    ),
    ContainerFacts: ContainerFacts({"line_endings": "crlf"}),
    ContentFingerprint: ContentFingerprint(body_digest="b" * 64, body_digest_view=BodyView.PLAIN),
    SameMessageCandidate: SameMessageCandidate("a" * 64, "b" * 64, "<a@example>", "c" * 64, BodyView.PLAIN),
    HeaderField: HeaderField(name="From", raw_value="A <a@example>", ordinal=3),
    PartRecord: PartRecord(part_id="1.2.3", parent_part_id="1.2", content_type="text/plain"),
    AttachmentOccurrence: AttachmentOccurrence(
        attachment_id="d" * 64, occurrence_path="1.4@1", part_id="1.4"
    ),
    ChildLink: ChildLink(state=ChildLinkState.VERSION_MISMATCH, child_id="child-2", expected_version="1", found_version="2"),
    ThreadEdge: ThreadEdge(child_message_id="<b@example>", parent_message_id=None, source=ThreadSource.IN_REPLY_TO),
    HitLocation: HitLocation(part="1", view="headers", unit=0),
    FlagHit: _flag_hit(),
    GroupCount: GroupCount(term_group_id="group-1", count=1, ordinal=0, quote_kind="unquoted"),
    FlagRollup: FlagRollup(scope=RollupScope.MESSAGE),
    FlagSection: FlagSection(),
    RunRecord: RunRecord(run_id="run-2"),
    EmailDocument: _email_document(),
}


def test_every_record_round_trips_byte_identically() -> None:
    """Bytes -> record -> bytes is the spec's exit criterion, for every record."""
    for cls, instance in RECORDS.items():
        payload = record_to_bytes(instance)
        decoded = record_from_bytes(cls, payload)
        assert decoded == instance, cls.__name__
        assert record_to_bytes(decoded) == payload, cls.__name__


def test_every_dataclass_contract_has_a_round_trip_test() -> None:
    """A record added to the contract layer cannot skip round-trip coverage."""
    for module in (model, timeevent):
        for obj in vars(module).values():
            if isinstance(obj, type) and dataclasses.is_dataclass(obj):
                assert obj in RECORDS, f"{obj.__name__} has no hand-typed round-trip instance"


def test_envelope_is_the_core_schema_version() -> None:
    payload = record_to_bytes(RECORDS[EmailDocument])
    envelope = json.loads(payload)
    assert set(envelope) == {"schema_version", "record"}
    assert envelope["schema_version"] == SCHEMA_VERSION


def test_unknown_key_at_top_level_raises() -> None:
    envelope = json.loads(record_to_bytes(_email_document()))
    envelope["record"]["unexpected_field"] = "boom"
    with pytest.raises(CodecError):
        record_from_bytes(EmailDocument, json.dumps(envelope).encode("utf-8"))


def test_unknown_key_inside_a_nested_record_raises() -> None:
    envelope = json.loads(record_to_bytes(_email_document()))
    envelope["record"]["parts"][1]["extra"] = 1
    with pytest.raises(CodecError):
        record_from_bytes(EmailDocument, json.dumps(envelope).encode("utf-8"))


def test_unknown_key_inside_a_timeevent_raises() -> None:
    envelope = json.loads(record_to_bytes(_email_document()))
    envelope["record"]["times"][0]["not_in_shape"] = True
    with pytest.raises(CodecError):
        record_from_bytes(EmailDocument, json.dumps(envelope).encode("utf-8"))


def test_empty_flag_section_round_trips() -> None:
    """D8: reserved, present-but-empty, round-tripping -- on its own and on a record."""
    empty = FlagSection()
    assert empty.hits == []
    assert empty.rollup is None
    assert empty.term_list_hash is None
    assert empty.matcher_version is None
    payload = record_to_bytes(empty)
    decoded = record_from_bytes(FlagSection, payload)
    assert decoded == empty
    assert record_to_bytes(decoded) == payload

    doc = _email_document()
    doc_flags = EmailDocument(
        container_kind=doc.container_kind,
        container_hash=doc.container_hash,
        container_facts=doc.container_facts,
        content_fingerprint=doc.content_fingerprint,
        status=doc.status,
    )
    decoded_doc = record_from_bytes(EmailDocument, record_to_bytes(doc_flags))
    assert decoded_doc.flags == FlagSection()
    assert record_to_bytes(decoded_doc) == record_to_bytes(doc_flags)


def test_flag_section_present_on_every_record() -> None:
    """'Every record carries a FlagSection' (D8) for the records a matcher can hit."""
    expected = {
        model.EmailDocument,
        model.PartRecord,
        model.HeaderField,
        model.AttachmentOccurrence,
        model.ChildLink,
        model.ThreadEdge,
        model.RunRecord,
    }
    for cls in expected:
        flags_field = {f.name: f for f in dataclasses.fields(cls)}["flags"]
        assert flags_field.default is dataclasses.MISSING
        assert flags_field.default_factory() == FlagSection()
    # FlagHit is the shape inside FlagSection.hits and TimeEvent is the separately
    # frozen D15 shape; neither carries its own FlagSection.
    for cls in (model.FlagHit, timeevent.TimeEvent):
        assert "flags" not in {f.name for f in dataclasses.fields(cls)}


#: The siblings' address spaces: a page, a cell/sheet, a slide. Email-extract never fabricates one.
_SIBLING_ADDRESS_WORDS = ("page", "cell", "sheet", "slide")


def test_hit_location_is_opaque_and_producer_shaped() -> None:
    """D8: email's location names its own space (part/view/span/unit), never a sibling's.

    Written so it fails the moment a page, cell, sheet or slide field is added to ``HitLocation`` or
    ``FlagHit``: email-extract has no page and no cell to put there.
    """
    assert [field.name for field in dataclasses.fields(HitLocation)] == ["part", "view", "span", "unit"]
    for cls in (HitLocation, FlagHit):
        offenders = [
            field.name
            for field in dataclasses.fields(cls)
            if any(word in field.name for word in _SIBLING_ADDRESS_WORDS)
        ]
        assert not offenders, f"{cls.__name__} carries a sibling's address field: {offenders}"


def test_no_email_module_declares_a_sibling_address_field() -> None:
    """No email-side record fabricates a page/cell/sheet/slide.

    The only place those words may appear is ``SiblingDerivedFacts.page_count`` /
    ``sheet_count`` -- the **child's own** counts, carried on the citation and never copied (D12).
    Every other class-level field is checked: a page, cell, sheet or slide added to any record --
    ``HitLocation`` and ``FlagHit`` above all -- fails here.
    """
    allowed = {("SiblingDerivedFacts", "page_count"), ("SiblingDerivedFacts", "sheet_count")}
    package = Path(model.__file__).resolve().parent
    found: set[tuple[str, str]] = set()
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    name = statement.target.id
                    if any(word in name for word in _SIBLING_ADDRESS_WORDS):
                        found.add((node.name, name))
    assert found == allowed, f"an email-side record declares a sibling's address field: {found - allowed}"
