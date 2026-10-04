"""Turn 1.0b: the Phase 1 contract additions (decision 6 + the quote records).

The quote-boundary and view-level records freeze the per-boundary and per-view facts
(decision 2), the multi-cap ``RunRecord`` records every cap a run hit, the two new
``Status.SKIPPED`` reasons exist, and ``OUTPUT_SCHEMA_VERSION`` is 4.
"""

from __future__ import annotations

import pytest
from docextract_core.codec import CodecError

from emailextract import model, versions
from emailextract.model import (
    REASON_TABLE,
    BoundaryKind,
    CapRecord,
    QuoteBoundary,
    RunRecord,
    Span,
    Status,
    StatusOutcome,
    ViewLevel,
    record_from_bytes,
    record_to_bytes,
)


def test_quote_boundary_and_view_level_records_freeze() -> None:
    """Only ``kind = quote`` advances the ordinal; the records round-trip byte-identically."""
    quote = QuoteBoundary(
        rule_id="on_wrote_en",
        kind=BoundaryKind.QUOTE,
        span=Span(start=30, end=290),
        ordinal=1,
        prefix_depth=[0, 0, 0, 0],
    )
    assert quote.ordinal == 1
    assert quote.prefix_depth == [0, 0, 0, 0]
    for kind, ordinal in (
        (BoundaryKind.FORWARD, 0),
        (BoundaryKind.SIGNATURE, 0),
        (BoundaryKind.LIST_FOOTER, None),
        (BoundaryKind.UNKNOWN, None),
    ):
        boundary = QuoteBoundary(
            rule_id=f"{kind.value}_rule", kind=kind, span=Span(start=0, end=1), ordinal=ordinal
        )
        assert boundary.ordinal in (0, None)
    # Only quote advances the ordinal: a non-quote at >= 1 is refused, and a quote at 0
    # (or None) is refused.
    with pytest.raises(CodecError):
        QuoteBoundary(
            rule_id="dash_dash_space",
            kind=BoundaryKind.SIGNATURE,
            span=Span(start=0, end=1),
            ordinal=1,
        )
    with pytest.raises(CodecError):
        QuoteBoundary(
            rule_id="on_wrote_en", kind=BoundaryKind.QUOTE, span=Span(start=0, end=1), ordinal=0
        )
    with pytest.raises(CodecError):
        QuoteBoundary(
            rule_id="gt_family", kind=BoundaryKind.QUOTE, span=Span(start=0, end=1)
        )
    # prefix_depth is per line and never negative.
    with pytest.raises(CodecError):
        QuoteBoundary(
            rule_id="gt_family",
            kind=BoundaryKind.QUOTE,
            span=Span(start=0, end=1),
            ordinal=1,
            prefix_depth=[0, -1],
        )

    level = ViewLevel(
        view_id="plain",
        span=Span(start=0, end=300),
        quote_level=1,
        resolution_rule_id="on_wrote_en",
        disagreement=False,
    )
    assert level.quote_level == 1
    # quote_level is a derived rank: nothing thresholds its magnitude in the contract.
    assert ViewLevel(
        view_id="html", span=Span(start=0, end=5), quote_level=0, resolution_rule_id="gmail_quote"
    ).quote_level == 0

    for record, instance in (
        (QuoteBoundary, quote),
        (ViewLevel, level),
    ):
        payload = record_to_bytes(instance)
        assert record_from_bytes(record, payload) == instance
        assert record_to_bytes(record_from_bytes(record, payload)) == payload


def test_run_record_carries_every_cap_and_the_two_new_reasons() -> None:
    """A run records every cap; the two new ``skipped`` reasons exist."""
    # The two new reasons belong to Status.SKIPPED (the existing cap family).
    assert REASON_TABLE[Status.SKIPPED] == (
        "size_cap",
        "total_size_cap",
        "depth_cap",
        "part_count_cap",
        "header_bytes_cap",
    )
    assert StatusOutcome(status=Status.SKIPPED, reason="part_count_cap").reason == "part_count_cap"
    assert (
        StatusOutcome(status=Status.SKIPPED, reason="header_bytes_cap").reason == "header_bytes_cap"
    )
    # They are skip reasons only: another status refuses them.
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.FAILED, reason="part_count_cap")
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.TRUNCATED, reason="header_bytes_cap")

    # A run that hits depth and total bytes records both (migration: the single
    # cap_id/cap_value_bytes/declared_size_bytes triple is now one CapRecord).
    one_cap = RunRecord(run_id="run-1")
    assert one_cap.caps == []
    migrated = RunRecord(
        run_id="run-1",
        caps=[CapRecord(cap_id="attachment_size", cap_value_bytes=262144, declared_size_bytes=1234)],
    )
    assert migrated.caps[0].cap_id == "attachment_size"
    assert migrated.caps[0].cap_value_bytes == 262144
    assert migrated.caps[0].declared_size_bytes == 1234
    multi = RunRecord(
        run_id="run-2",
        caps=[
            CapRecord(cap_id="depth_cap", cap_value_bytes=32, declared_size_bytes=40),
            CapRecord(cap_id="total_size_cap", cap_value_bytes=1048576, declared_size_bytes=2097152),
        ],
    )
    assert [cap.cap_id for cap in multi.caps] == ["depth_cap", "total_size_cap"]
    with pytest.raises(CodecError):
        RunRecord(run_id="run-3", caps=["not-a-cap"])  # type: ignore[list-item]
    with pytest.raises(CodecError):
        CapRecord(cap_id="attachment_size", cap_value_bytes=-1)

    for instance in (one_cap, migrated, multi):
        payload = record_to_bytes(instance)
        assert record_from_bytes(RunRecord, payload) == instance
        assert record_to_bytes(record_from_bytes(RunRecord, payload)) == payload


def test_output_schema_version_is_four() -> None:
    """``OUTPUT_SCHEMA_VERSION`` moved 3 to 4; the records default to the constant."""
    assert versions.OUTPUT_SCHEMA_VERSION == "4"
    assert model.EMAIL_PARSER_VERSION == versions.EMAIL_PARSER_VERSION == "1"
    assert model.RunRecord(run_id="r").output_schema_version == "4"
    assert model.RunRecord(run_id="r").email_parser_version == "1"
