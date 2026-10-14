"""Turn 1b.1: the ``.msg`` contract additions -- the one schema bump and its shapes.

The bump is exactly three things (`phase1b-contract.md` section 1): (X) the optional
``stream_ref`` (a :class:`~emailextract.model.ContainerStreamRef`) on ``PartRecord`` and
``HeaderField``; (Y) the three CFB reasons on ``REASON_TABLE[Status.SKIPPED]`` plus the
``NAMED_ERROR_REASONS`` / ``text.VERBATIM_REASONS`` edits; (Z) the optional ``embedded``
(a :class:`~emailextract.model.EmbeddedSummary`) on ``AttachmentOccurrence``. And the one
version that moves: ``OUTPUT_SCHEMA_VERSION`` ``"5"`` -> ``"6"``.

Ground truth is hand-typed from the contract: no expected value is copied from the module
under test. The round-trip proof is the core codec's own (bytes -> record -> bytes).
"""

from __future__ import annotations

import pytest
from docextract_core.codec import CodecError

from emailextract import versions
from emailextract.model import (
    REASON_TABLE,
    AttachmentOccurrence,
    BodyView,
    ContainerFacts,
    ContainerKind,
    ContainerStreamAxis,
    ContainerStreamRef,
    ContentFingerprint,
    EmailDocument,
    EmbeddedSummary,
    EncodingSource,
    HeaderField,
    PartRecord,
    RunRecord,
    Status,
    StatusOutcome,
    StreamFault,
    TriState,
    TriValue,
    record_from_bytes,
    record_to_bytes,
)
from emailextract.parse import NAMED_ERROR_REASONS, ParseResult
from emailextract.text import REASON_CONTAINER_STREAM, VERBATIM_REASONS
from emailextract.walk import CFB_CAP_REASONS

#: The three CFB cap reasons, hand-typed from `phase1b-contract.md` section 1(Y).
CFB_REASONS = ("sector_count_cap", "directory_entries_cap", "difat_chain_length_cap")


def test_container_stream_ref_shape_and_round_trip() -> None:
    """A real ref round-trips byte-identically, alone and as a record's field."""
    ref = ContainerStreamRef(
        stream="__substg1.0_10130102",
        byte_offset=0,
        byte_len=4095,
        axis=ContainerStreamAxis.STREAM,
        fault=StreamFault.CYCLE,
    )
    assert ref.stream == "__substg1.0_10130102"
    assert (ref.byte_offset, ref.byte_len) == (0, 4095)
    assert ref.axis is ContainerStreamAxis.STREAM
    assert ref.fault is StreamFault.CYCLE

    payload = record_to_bytes(ref)
    decoded = record_from_bytes(ContainerStreamRef, payload)
    assert decoded == ref
    assert record_to_bytes(decoded) == payload

    # The re-encoded form carries the source range of its 001F stream.
    reencoded = ContainerStreamRef(
        stream="__substg1.0_007D001F",
        byte_offset=248,
        byte_len=46,
        axis=ContainerStreamAxis.REENCODED,
    )
    assert record_from_bytes(ContainerStreamRef, record_to_bytes(reencoded)) == reencoded

    # As the last field of both records, positional construction is unaffected, and the
    # field round-trips through the record the store persists.
    field = HeaderField(name="Subject", raw_value="Caf\u00e9", ordinal=0, stream_ref=reencoded)
    assert HeaderField("Subject", "Caf\u00e9", 0).stream_ref is None
    assert record_from_bytes(HeaderField, record_to_bytes(field)) == field

    record = PartRecord(part_id="1.2", content_type="text/html", stream_ref=ref)
    assert record_from_bytes(PartRecord, record_to_bytes(record)) == record


def test_container_stream_ref_invariants_raise() -> None:
    """Every invariant in contract section 1(X) raises ``CodecError``, at construction."""
    # A STREAM/REENCODED ref needs both offsets as ints >= 0.
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", axis=ContainerStreamAxis.STREAM)
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", byte_offset=0, byte_len=None, axis=ContainerStreamAxis.REENCODED)
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", byte_offset=-1, byte_len=4)
    # A bool is not an int, here as everywhere.
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", byte_offset=True, byte_len=4)
    # A synthetic ref carries no offsets and a synthetic: label.
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="synthetic:x:1", byte_offset=0, byte_len=4, axis=ContainerStreamAxis.SYNTHETIC)
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", axis=ContainerStreamAxis.SYNTHETIC)
    # A non-synthetic ref is not labelled synthetic:.
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="synthetic:x:1", byte_offset=0, byte_len=1)
    # The stream is non-empty and the fault is a StreamFault member.
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="", byte_offset=0, byte_len=1)
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", byte_offset=0, byte_len=1, fault="cycle")
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="S", byte_offset=0, byte_len=1, axis="stream")
    # The parent enforces the invariant too, and only a ref or None is legal.
    with pytest.raises(CodecError):
        PartRecord(part_id="1", stream_ref="nope")
    with pytest.raises(CodecError):
        HeaderField(name="X", raw_value="y", ordinal=0, stream_ref="nope")
    ok = PartRecord(part_id="1", stream_ref=None)
    assert ok.stream_ref is None


def test_a_synthetic_ref_carries_no_offsets() -> None:
    """A synthetic ref is the label and nothing else -- no virtual offset ever enters a record."""
    ref = ContainerStreamRef(stream="synthetic:boundary:1", axis=ContainerStreamAxis.SYNTHETIC)
    assert ref.byte_offset is None and ref.byte_len is None
    assert ref.fault is None
    assert ref.stream == "synthetic:boundary:1"
    with pytest.raises(CodecError):
        ContainerStreamRef(stream="synthetic:boundary:1", axis=ContainerStreamAxis.SYNTHETIC, fault=StreamFault.CYCLE)


def test_embedded_summary_shape_and_defaults() -> None:
    """``EmbeddedSummary`` has the contract's defaults and validators; ``None`` keeps its meaning."""
    assert EmbeddedSummary(message_class="IPM.Note", has_transport_headers=False) == EmbeddedSummary(
        message_class="IPM.Note",
        has_transport_headers=False,
        subject=None,
        recipient_count=0,
        attachment_count=0,
    )
    full = EmbeddedSummary(
        message_class="IPM.Note.SMIME",
        has_transport_headers=True,
        subject="nested",
        recipient_count=2,
        attachment_count=3,
    )
    assert record_from_bytes(EmbeddedSummary, record_to_bytes(full)) == full

    with pytest.raises(CodecError):
        EmbeddedSummary(message_class="", has_transport_headers=True)
    with pytest.raises(CodecError):
        EmbeddedSummary(message_class="IPM.Note", has_transport_headers=True, subject="")
    with pytest.raises(CodecError):
        EmbeddedSummary(message_class="IPM.Note", has_transport_headers=True, recipient_count=-1)
    # A bool is not an int; the counts are ints >= 0.
    with pytest.raises(CodecError):
        EmbeddedSummary(message_class="IPM.Note", has_transport_headers=True, attachment_count=True)
    with pytest.raises(CodecError):
        EmbeddedSummary(message_class="IPM.Note", has_transport_headers="yes")  # type: ignore[arg-type]

    # On the occurrence: the last field, defaulting to None ("not an embedded message").
    assert AttachmentOccurrence(attachment_id="a" * 64, occurrence_path="1@0", part_id="1").embedded is None
    with pytest.raises(CodecError):
        AttachmentOccurrence(
            attachment_id="a" * 64, occurrence_path="1@0", part_id="1", embedded="nope"  # type: ignore[arg-type]
        )
    occurrence = AttachmentOccurrence(
        attachment_id="a" * 64,
        occurrence_path="1@0",
        part_id="1",
        embedded=EmbeddedSummary(message_class="IPM.Note", has_transport_headers=True, subject="s"),
    )
    assert record_from_bytes(AttachmentOccurrence, record_to_bytes(occurrence)) == occurrence


def test_the_cfb_cap_reasons_join_the_skipped_row() -> None:
    """The three CFB reasons are ``skipped`` reasons, and the walker's own two tuples agree."""
    assert REASON_TABLE[Status.SKIPPED] == (
        "size_cap",
        "total_size_cap",
        "depth_cap",
        "part_count_cap",
        "header_bytes_cap",
        *CFB_REASONS,
    )
    assert tuple(CFB_CAP_REASONS) == CFB_REASONS
    for reason in CFB_REASONS:
        assert StatusOutcome(status=Status.SKIPPED, reason=reason).reason == reason
        # They are skip reasons only: another status refuses them.
        with pytest.raises(CodecError):
            StatusOutcome(status=Status.TRUNCATED, reason=reason)


def test_named_error_reasons_gain_the_two_cfb_faults() -> None:
    """The closed tuple swaps to the two whole-file CFB faults; ``cfb_msg_unsupported`` stays for now."""
    assert NAMED_ERROR_REASONS == (
        "invalid_input",
        "input_over_cap",
        "invalid_container_kind",
        "cfb_directory_loop",
        "cfb_header_unsupported",
        "cfb_msg_unsupported",
        "not_a_message",
        "invalid_limits",
    )
    assert "cfb_msg_unsupported" in NAMED_ERROR_REASONS  # interim: deleted in Turn 1b.5
    # A success result may now name the projected container kind.
    assert ParseResult(kind="cfb_msg", prelude_bom_bytes=0, prelude_mbox_bytes=0, error=None).kind == "cfb_msg"
    with pytest.raises(CodecError):
        ParseResult(kind="nope", prelude_bom_bytes=0, prelude_mbox_bytes=0, error=None)


def test_verbatim_reasons_gain_container_stream() -> None:
    """``container_stream`` is the fourth closed ``verbatim_reason``; it is never ``exact``."""
    assert REASON_CONTAINER_STREAM == "container_stream"
    assert VERBATIM_REASONS == (
        "cte_not_identity",
        "decode_fallback",
        "multibyte_without_offset_map",
        "container_stream",
    )
    assert VERBATIM_REASONS.count(REASON_CONTAINER_STREAM) == 1


def test_output_schema_version_is_six() -> None:
    """``OUTPUT_SCHEMA_VERSION`` moved 5 -> 6; the record defaults follow the constant."""
    assert versions.OUTPUT_SCHEMA_VERSION == "6"
    # ``EMAIL_PARSER_VERSION`` does not move with it, and no CFB reader version is added here.
    assert versions.EMAIL_PARSER_VERSION == "2"
    assert not hasattr(versions, "CFB_VERSION")
    assert not hasattr(versions, "MSG_READER_VERSION")
    assert RunRecord(run_id="r").output_schema_version == "6"
    assert RunRecord(run_id="r").email_parser_version == "2"
    assert EmailDocument(
        container_kind=ContainerKind.RFC822,
        container_hash="a" * 64,
        container_facts=ContainerFacts({}),
        content_fingerprint=ContentFingerprint(body_digest="b" * 64, body_digest_view=BodyView.PLAIN),
        status=StatusOutcome(status=Status.PARSED),
    ).output_schema_version == "6"
    # A TriValue is untouched by the bump: the not-built idiom still round-trips.
    assert TriValue(state=TriState.UNKNOWN, reason_id="not_built_in_phase1").reason_id == "not_built_in_phase1"
    assert EncodingSource.INTERNET_CPID.value == "internet_cpid"
