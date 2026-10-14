"""Turn 1b.1: the eight provenance points, gated, against the hand-made ``.msg`` fake.

Each point is gated on ``cfb_msg`` or on the presence of a span table, and each default
branch is the current ``.eml`` expression unchanged. The net is the committed golden
(``tests/golden/eml_golden.json``): the ``.eml`` ids, spans, caps and store bytes it pins
are byte-identical after the bump. This module proves the two halves: a span-table
container gets real provenance (source keys, stream refs, the CFB caps, the source-only
store table), and a container without one takes today's path exactly.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from support import fake_msg_container as F  # noqa: E402

from emailextract.assemble import assemble, resolve_span, Unresolvable  # noqa: E402
from emailextract.container import (  # noqa: E402
    EmlContainer,
    PersistedSpanRow,
    memory_bytes,
    source_key_of,
)
from emailextract.ids import RawSpan, content_hash, part_id, source_part_id  # noqa: E402
from emailextract.model import (  # noqa: E402
    ContainerStreamAxis,
    ContainerStreamRef,
    EncodingSource,
)
from emailextract.parse import Limits, NAMED_ERROR_REASONS, parse  # noqa: E402
from emailextract.store import MsgWalkArtifact, WalkArtifact, walk_artifact  # noqa: E402
from emailextract.text import analyse_part  # noqa: E402
from emailextract.walk import _part_shape_id, walk  # noqa: E402

LIMITS = Limits(**F.CALLER_VALUES)
GOLDEN_PATH = ROOT / "tests" / "golden" / "eml_golden.json"

#: The four CFB bytes are refused without an opener; ``MAGIC`` is the CFB signature.
MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
CFB_BYTES = MAGIC + b"\x00" * 32


def _row_for(container: F.FakeMsgContainer, part_id_value: str):
    parts = {p.part_id: p for p in walk(container, limits=LIMITS).parts}
    part = parts[part_id_value]
    lookup = {(r.virtual_offset, r.virtual_len): r for r in container.span_provenance}
    return part, lookup[(part.raw_span.offset, part.raw_span.length)]


# --------------------------------------------------------------- point 1: the assembler


def test_the_assembler_fills_stream_ref_from_the_span_table() -> None:
    """Every record whose virtual span is a source region carries its ``ContainerStreamRef``."""
    container = F.attach_message(0)
    document = assemble(container, limits=LIMITS)
    rows = {(r.virtual_offset, r.virtual_len): r for r in container.span_provenance}

    by_path = {p.path: p for p in walk(container, limits=LIMITS).parts}
    refs = {record.part_id: record.stream_ref for record in document.parts}
    # The multipart root is synthetic (the projection's own framing): no source offsets.
    root = by_path["1"]
    assert refs[root.part_id] == ContainerStreamRef(stream="synthetic:multipart:1", axis=ContainerStreamAxis.SYNTHETIC)
    # The html child is re-encoded from a 001F stream; the attachment passes a stream through.
    html_leaf = by_path["1.1"]
    assert refs[html_leaf.part_id] == ContainerStreamRef(
        stream="__substg1.0_10130102", byte_offset=0, byte_len=len(F.HTML_STREAM), axis=ContainerStreamAxis.REENCODED
    )
    att = by_path["1.2"]
    assert refs[att.part_id] == ContainerStreamRef(
        stream="__substg1.0_37010102", byte_offset=0, byte_len=len(F.BINARY_PAYLOAD), axis=ContainerStreamAxis.STREAM
    )
    # A header field whose own raw span is a source region carries its re-encoded ref.
    subject = next(field for field in document.headers if field.name == "Subject")
    assert subject.stream_ref is not None
    assert subject.stream_ref.axis is ContainerStreamAxis.REENCODED
    assert subject.stream_ref.stream == "__substg1.0_0037001F"
    # A header field with no source row keeps None.
    assert next(field for field in document.headers if field.name == "Content-Type").stream_ref is None

    # The size/digest rule (contract section 5): a pass-through leaf's are its stream's, a
    # re-encoded leaf's describe the re-encoding, and a synthetic leaf has none.
    assert (att.part_id, refs[att.part_id].byte_len) != (None, None)
    att_record = next(record for record in document.parts if record.part_id == att.part_id)
    assert att_record.size_bytes == len(F.BINARY_PAYLOAD)
    assert att_record.sha256 == rows[(att.raw_span.offset, att.raw_span.length)].source_sha256
    root_record = next(record for record in document.parts if record.part_id == root.part_id)
    assert root_record.size_bytes is None and root_record.sha256 is None


# --------------------------------------------------------------- point 2: the part id


def test_part_id_is_kind_gated_and_framing_length_independent() -> None:
    """A framed part's id is its source key and digest, not a virtual span."""
    for builder in (F.html_message, F.attach_message):
        container = builder(0)
        walked = walk(container, limits=LIMITS)
        lookup = {(r.virtual_offset, r.virtual_len): r for r in container.span_provenance}
        for part in walked.parts:
            row = lookup[(part.raw_span.offset, part.raw_span.length)]
            expected = source_part_id(container.container_hash(), source_key_of(row), row.source_sha256)
            assert part.part_id == expected, part.path
    # Non-vacuity: the ungated (virtual-span) id moves with the framing length (the C2 finding).
    a = F.attach_message(0)
    b = F.attach_message(500)
    walked_a = walk(a, limits=LIMITS)
    walked_b = walk(b, limits=LIMITS)
    default_a = [part_id(a.container_hash(), p.raw_span, content_hash(p.raw_span.slice(a.raw_bytes()))) for p in walked_a.parts]
    default_b = [part_id(b.container_hash(), p.raw_span, content_hash(p.raw_span.slice(b.raw_bytes()))) for p in walked_b.parts]
    assert default_a != default_b, "the default expression must depend on the framing (the C2 finding)"
    assert [p.part_id for p in walked_a.parts] == [p.part_id for p in walked_b.parts]


def test_two_framing_lengths_give_identical_part_ids() -> None:
    """The fake at ``framing=0`` and ``framing=500`` gives the same ids, records and citations."""
    for builder, twin in ((F.html_message, F.html_twin), (F.attach_message, F.attach_twin)):
        a = builder(0)
        b = builder(500)
        walk_a = walk(a, limits=LIMITS)
        walk_b = walk(b, limits=LIMITS)
        assert [p.part_id for p in walk_a.parts] == [p.part_id for p in walk_b.parts]
        doc_a = assemble(a, limits=LIMITS)
        doc_b = assemble(b, limits=LIMITS)
        assert [(r.part_id, r.parent_part_id, r.stream_ref, r.size_bytes, r.sha256) for r in doc_a.parts] == [
            (r.part_id, r.parent_part_id, r.stream_ref, r.size_bytes, r.sha256) for r in doc_b.parts
        ]
        for record in doc_a.parts:
            cite_a = resolve_span(a, record.part_id, "plain", 0, 1)
            cite_b = resolve_span(b, record.part_id, "plain", 0, 1)
            assert cite_a == cite_b
        _ = twin


# --------------------------------------------------------------- the .eml identity guard


def test_the_eml_part_ids_are_byte_identical() -> None:
    """Every ``.eml`` fixture's part ids are exactly the committed golden's."""
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    # The golden was recorded under its own declared Limits (the header cap lowered to 4096).
    golden_limits = replace(Limits.untrusted(), max_header_bytes=4096)
    for name, payload in golden["fixtures"].items():
        raw = (ROOT / "fixtures" / name).read_bytes()
        walked = walk(EmlContainer(memory_bytes(raw)), limits=golden_limits)
        pinned = [part["part_id"] for part in payload["document"]["record"]["parts"]]
        assert [p.part_id for p in walked.parts] == pinned, name
    assert golden["fixtures"], "the golden pins no fixture"


# --------------------------------------------------------------- point 3: the citation


def test_resolve_span_returns_a_stream_ref_for_a_span_table_container() -> None:
    """A citation against a projected part names the source stream and range, not the framing."""
    container = F.attach_message(0)
    part, row = _row_for(container, _part_id_at(container, "1.2"))
    answer = resolve_span(container, part.part_id, "plain", 0, 1)
    assert isinstance(answer, ContainerStreamRef)
    assert answer == ContainerStreamRef(
        stream="__substg1.0_37010102", byte_offset=0, byte_len=len(F.BINARY_PAYLOAD), axis=ContainerStreamAxis.STREAM
    )
    assert source_key_of(row) == "__substg1.0_37010102:0:20"
    # A part with no row is refused as usual.
    missing = resolve_span(container, "no-such-part", "plain", 0, 1)
    assert isinstance(missing, Unresolvable)


def test_resolve_span_still_refuses_a_virtual_offset() -> None:
    """No answer for the fake carries a virtual offset -- on every field and in the bytes."""
    container = F.attach_message(0)
    raw_len = len(container.raw_bytes())
    for part in walk(container, limits=LIMITS).parts:
        answer = resolve_span(container, part.part_id, "plain", 0, 1)
        assert isinstance(answer, ContainerStreamRef), part.path
        assert not isinstance(answer, RawSpan)
        # A source offset, never the virtual one; a synthetic ref has neither.
        if answer.byte_offset is not None:
            assert answer.byte_offset + answer.byte_len <= raw_len
        # The serialized form carries no virtual_* token (C2).
        from emailextract.model import record_to_bytes

        blob = record_to_bytes(answer)
        assert b"virtual" not in blob


# --------------------------------------------------------------- point 4: the precompute


def test_analyse_part_forces_container_stream_part_level() -> None:
    """A projected leaf is ``part_level``/``container_stream``; the default stays ``exact``."""
    container = F.attach_message(0)
    raw = container.raw_bytes()
    part, _row = _row_for(container, _part_id_at(container, "1.1"))
    forced = analyse_part(raw, part, container_stream=True)
    assert forced is not None
    assert forced.verbatim_precision == "part_level"
    assert forced.verbatim_reason == "container_stream"
    assert forced.offset_map is None
    # The default branch is untouched: this identity leaf is exact without the flag.
    default = analyse_part(raw, part)
    assert default is not None
    assert default.verbatim_precision == "exact"
    assert default.verbatim_reason is None


# --------------------------------------------------------------- point 5: the charset


def test_encoding_source_is_overwritten_from_the_ladder_map() -> None:
    """The assembler writes the producer's MAPI ladder, not the charset the virtual bytes declare."""
    container = F.attach_message(0)
    shaped = {p.path: p for p in walk(container, limits=LIMITS).parts}
    # The walker only ever says declared_charset / utf-8 on the virtual bytes.
    assert shaped["1.1"].encoding_source is EncodingSource.DECLARED_CHARSET
    assert shaped["1.1"].decode_chain.used_charset == "utf-8"
    record = next(r for r in assemble(container, limits=LIMITS).parts if r.content_type == "text/html")
    # The producer's own ladder overrides it.
    assert record.encoding_source is EncodingSource.MESSAGE_CPID
    assert record.decode_chain.used_charset == "windows-1252"
    assert record.decode_chain.declared_charset == "windows-1252"


# --------------------------------------------------------------- point 6: the caps


def test_cap_declared_size_copies_the_real_stream_size() -> None:
    """A CFB cap's ``declared_size_bytes`` is the producer's real count, never a virtual length."""
    container = F.html_message(0)
    tight = replace(LIMITS, max_decoded_part_bytes=1)
    document = assemble(container, limits=tight)
    cap = next(c for c in document.run_record.caps if c.cap_id == "size_cap")
    # The virtual body region is 45 bytes; the publisher's observed stream is 92.
    assert cap.cap_value_bytes == 1
    assert cap.declared_size_bytes == len(F.HTML_STREAM) == 92


# --------------------------------------------------------------- point 7: the store


def test_the_store_persists_sectors_and_the_source_only_span_table() -> None:
    """A projected container's artifact carries the eight sector classes and a source-only table."""
    container = F.attach_message(0)
    artifact = walk_artifact(container)
    assert isinstance(artifact, MsgWalkArtifact)
    provenance = artifact.msg_provenance
    assert provenance.projection == "virtual_rfc822"
    assert len(provenance.spans) == len(container.span_provenance)
    for row in provenance.spans:
        assert isinstance(row, PersistedSpanRow)
        assert not hasattr(row, "virtual_offset")
        assert not hasattr(row, "virtual_len")
    sectors = provenance.sectors
    assert set(sectors) == {
        "sectors.header",
        "sectors.difat",
        "sectors.fat",
        "sectors.minifat",
        "sectors.directory",
        "sectors.stream",
        "sectors.free",
        "sectors.slack",
    }
    assert sum(sectors.values()) == 512 * 5 + 4096 + 1024 + 137
    from emailextract.model import record_to_bytes

    blob = record_to_bytes(artifact)
    assert b"virtual_offset" not in blob and b"virtual_len" not in blob
    # The .eml artifact is a different type and gains nothing.
    assert isinstance(walk_artifact(F.attach_twin(0)), WalkArtifact)


def test_the_source_only_span_table_recomputes_the_virtual_offsets() -> None:
    """The persisted source-only rows recompute the same virtual offsets from the source."""
    container = F.attach_message(0)
    artifact = walk_artifact(container)
    assert isinstance(artifact, MsgWalkArtifact)
    rebuilt = F.attach_message(0)  # re-project the source with the projection label
    assert rebuilt.container_facts()["projection"] == artifact.msg_provenance.projection
    recomputed = {(row.source_stream, row.source_byte_offset): (row.virtual_offset, row.virtual_len)
                  for row in rebuilt.span_provenance}
    original = {(row.source_stream, row.source_byte_offset): (row.virtual_offset, row.virtual_len)
                for row in container.span_provenance}
    assert recomputed == original
    # And the persisted rows carry exactly the source half of each original row.
    for persisted, row in zip(artifact.msg_provenance.spans, container.span_provenance):
        assert persisted.source_stream == row.source_stream
        assert persisted.source_byte_offset == row.source_byte_offset
        assert persisted.source_byte_len == row.source_byte_len
        assert persisted.source_sha256 == row.source_sha256
        assert persisted.axis is row.axis


def test_adding_a_cfb_msg_document_changes_no_eml_store_byte() -> None:
    """Storing a projected container leaves every ``.eml`` artifact's bytes exactly where they were."""
    from emailextract.model import record_to_bytes

    eml = F.attach_twin(0)
    before = record_to_bytes(walk_artifact(eml))
    msg_artifact = walk_artifact(F.attach_message(0))
    assert isinstance(msg_artifact, MsgWalkArtifact)
    after = record_to_bytes(walk_artifact(eml))
    assert before == after


# --------------------------------------------------------------- point 8: the parse seam


def test_parse_opens_a_cfb_container_instead_of_refusing() -> None:
    """A CFB magic opens (Turn 1b.5); a caller's opener seam still overrides the default."""
    def opener(data: bytes):
        from emailextract.parse import ParseResult

        return ParseResult(kind="cfb_msg", prelude_bom_bytes=0, prelude_mbox_bytes=0, error=None)

    # The package's own opener now reads the CFB: a bare magic without a property stream
    # is a named error (never ``cfb_msg_unsupported``, which Turn 1b.5 deletes).
    refused = parse(CFB_BYTES, limits=LIMITS)
    assert refused.error is not None
    assert refused.error.reason_id in NAMED_ERROR_REASONS
    assert "cfb_msg_unsupported" not in NAMED_ERROR_REASONS
    # Sniffed: the magic opens through the opener.
    sniffed = parse(CFB_BYTES, limits=LIMITS, open_cfb=opener)
    assert sniffed.error is None and sniffed.kind == "cfb_msg"
    # Claimed: the same opener is honoured.
    claimed = parse(b"anything", container_kind="cfb_msg", limits=LIMITS, open_cfb=opener)
    assert claimed.error is None and claimed.kind == "cfb_msg"
    # ... and the default opener still refuses the same non-CFB bytes.
    assert parse(b"anything", container_kind="cfb_msg", limits=LIMITS).error is not None


# --------------------------------------------------------------- the default branches


def test_the_eml_default_branch_is_unchanged() -> None:
    """Every gated point, called with no span table, equals today's expression verbatim."""
    raw = (ROOT / "fixtures" / "generated" / "alternative_text_html.eml").read_bytes()
    container = EmlContainer(memory_bytes(raw))
    walked = walk(container, limits=LIMITS)
    part = walked.parts[0]
    # Point 2: the default is ``part_id(container_id, span, content_hash(span.slice(raw)))``.
    assert _part_shape_id(walked.container_hash, raw, part.raw_span, None) == part_id(
        walked.container_hash, part.raw_span, content_hash(part.raw_span.slice(raw))
    )
    # Points 1/5/6/7: no span table, no charset map, no cap observations -> today's records.
    document = assemble(container, limits=LIMITS)
    assert all(record.stream_ref is None for record in document.parts)
    assert all(field.stream_ref is None for field in document.headers)
    assert isinstance(walk_artifact(container), WalkArtifact)
    # Point 3: an .eml citation never takes the span-table branch -- no ContainerStreamRef.
    answer = resolve_span(container, document.parts[0].part_id, "plain", 0, 1)
    assert not isinstance(answer, ContainerStreamRef)
    assert isinstance(answer, (RawSpan, Unresolvable))


def test_the_value_codec_seam_defaults_to_latin_1() -> None:
    """The header seam's default is the current latin-1 expression; utf-8 reads real text."""
    from emailextract.headers import header_region
    from emailextract.walk import header_fields_at

    raw = (ROOT / "fixtures" / "generated" / "alternative_text_html.eml").read_bytes()
    container = EmlContainer(memory_bytes(raw))
    walked = walk(container)
    region_default = header_region(raw, walked, max_work_units=64)
    region_latin = header_region(raw, walked, max_work_units=64, value_codec="latin-1")
    assert [(f.name, f.raw_value) for f in region_default.fields] == [(f.name, f.raw_value) for f in region_latin.fields]
    # The default binary result matches the golden's own headers for this fixture.
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    pinned = golden["fixtures"]["generated/alternative_text_html.eml"]["document"]["record"]["headers"]
    assert [f.name for f in region_default.fields] == [h["name"] for h in pinned]
    assert [f.raw_value for f in region_default.fields] == [h["raw_value"] for h in pinned]

    # utf-8 on a UTF-8 virtual header returns the real text.
    container = F.html_message(0)
    subject = next(row for row in container.span_provenance if row.source_stream == "__substg1.0_0037001F")
    virtual = container.raw_bytes()
    start = subject.virtual_offset
    end = subject.virtual_offset + subject.virtual_len
    fields_utf8, _g1 = header_fields_at(virtual, start, end, value_codec="utf-8")
    assert fields_utf8[0].raw_value.strip() == F.SUBJECT_TEXT
    fields_latin, _g2 = header_fields_at(virtual, start, end)
    assert fields_latin[0].raw_value.strip() != F.SUBJECT_TEXT


# --------------------------------------------------------------- the twin comparison


def _shape_fingerprint(result) -> list:
    """The walker's structural fingerprint, with the container-addressed fields removed."""
    return [
        (
            part.path,
            part.parent_path,
            part.content_type,
            (part.raw_span.offset, part.raw_span.length),
            (part.headers_span.offset, part.headers_span.length),
            (part.body_span.offset, part.body_span.length),
            [(f.ordinal, f.name, f.raw_value, f.parse_status) for f in part.header_fields],
            (
                part.decode_chain.declared_cte,
                part.decode_chain.declared_charset,
                part.decode_chain.used_cte,
                part.decode_chain.used_charset,
                part.decode_chain.fallback_fired,
            ),
            getattr(part.encoding_source, "value", None),
            part.body_sha256,
            list(part.gaps),
        )
        for part in result.parts
    ]


def test_walk_msg_matches_walk_of_the_equivalent_eml_modulo_provenance() -> None:
    """``walk(msg)`` equals ``walk(twin)`` except the container-addressed fields, and nothing else."""
    # The only fields a projected walk may differ in: the container identity (kind/hash/facts)
    # and the source-keyed part id. The twin's WALK has no records, so nothing else may move.
    allowed = {"container_kind", "container_hash", "container_facts", "part_id"}
    for builder, twin in ((F.html_message, F.html_twin), (F.attach_message, F.attach_twin)):
        msg = walk(builder(0), limits=LIMITS)
        eml = walk(twin(0), limits=LIMITS)
        assert len(msg.parts) == len(eml.parts)
        assert _shape_fingerprint(msg) == _shape_fingerprint(eml)
        assert [(r.kind, r.path, r.span.offset, r.span.length) for r in msg.regions] == [
            (r.kind, r.path, r.span.offset, r.span.length) for r in eml.regions
        ]
        # The named, allowed differences really are the only ones that differ.
        assert msg.container_kind != eml.container_kind
        assert msg.container_hash != eml.container_hash
        assert msg.container_facts != eml.container_facts
        assert [p.part_id for p in msg.parts] != [p.part_id for p in eml.parts]
        assert allowed == {"container_kind", "container_hash", "container_facts", "part_id"}


def _part_id_at(container: F.FakeMsgContainer, path: str) -> str:
    return next(part.part_id for part in walk(container, limits=LIMITS).parts if part.path == path)


# --------------------------------------------------------------- the D1 characterization pin


def test_limits_fingerprint_is_unchanged_by_the_bump() -> None:
    """Characterization: ``limits_fingerprint`` is byte-identical to its pre-bump value.

    ``Limits`` does **not** gain a field in Turn 1b.1 (D1): the CFB caps live in the
    container's own observations, so the walker's ``Limits`` -- and therefore every
    ``.eml`` document key -- is unmoved. The two literals were computed on the pre-bump
    tree (``33f1409``); a new ``Limits`` field would move them and this test would fail.
    """
    from emailextract.assemble import limits_fingerprint

    assert limits_fingerprint(Limits.untrusted()) == (
        "3475b245bae7a418d6b5b22fa8d224452c1c666d96785f866fe5b85c7f6a05f5"
    )
    golden_limits = replace(Limits.untrusted(), max_header_bytes=4096)
    assert limits_fingerprint(golden_limits) == (
        "2238d89dfcf38c4cac493272d598ff158cd4e1f4a0e9ec14778f854c70101a07"
    )
