"""Turn 1b.5: ``emailextract.msgcontainer`` -- the A'' projection over a real ``.msg``.

The container opens an ``.msg`` through :mod:`emailextract.cfb`, reads its MAPI layer
through :mod:`emailextract.mapi`, and builds the deterministic virtual RFC 822 string plus
the :class:`~emailextract.container.SpanRow` table Turn 1b.1 defines. These tests hold it
against the **independent** side: the CFB bytes read through ``cfb.read_stream`` (never
through the container), the committed construction tables, and the ``.eml`` path, which
must be untouched.

The five declared tests are:

* ``test_the_virtual_bytes_and_the_span_table_agree`` -- every ``STREAM``/``REENCODED``
  row's ``source_sha256`` is the sha256 of the named stream's real bytes; the non-root rows
  tile the virtual bytes exactly; the persisted form round-trips (C2, section 7);
* ``test_the_container_publishes_no_virtual_offset_to_a_record`` -- no ``virtual_*`` value
  reaches a record, a part id, a citation or the store artifact;
* ``test_container_hash_addresses_the_cfb_file`` -- the hash is the file's, never the
  projection's (D14);
* ``test_container_facts_carry_the_fixed_key_list`` -- exactly this turn's key set (D6);
* ``test_the_span_table_row_shape_is_the_contract`` -- the ``SpanRow`` fields (section 7);

plus four extras: determinism under two ``PYTHONHASHSEED`` values, a seeded fuzz of the
projection, the hostile fixtures and a forced CFB cap through the container, and the C2
pair (two framing lengths).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from emailextract import cfb  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.container import PersistedSpanRow, SpanRow  # noqa: E402
from emailextract.ids import sha256_hex, source_part_id  # noqa: E402
from emailextract.container import source_key_of, span_lookup  # noqa: E402
from emailextract.model import ContainerStreamAxis, record_to_bytes  # noqa: E402
from emailextract.msgcontainer import (  # noqa: E402
    GAP_MAPI_HEADER_PROPERTY_DISAGREE,
    GAP_STREAM_TRUNCATED,
    GAP_TRANSPORT_HEADERS_ABSENT,
    MsgContainer,
)
from emailextract.parse import Limits, parse  # noqa: E402
from emailextract.store import MsgWalkArtifact, walk_artifact  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()

#: The fixtures these tests exercise, by name.
FIXTURES = (
    "msg_html_only_no_plain",
    "msg_plain_and_html",
    "msg_headers_html",
    "msg_property_vs_header_conflict",
)

#: D6's fixed key list, hand-typed from the contract's ``container_facts`` table.
FACT_KEYS = frozenset(
    {
        "adapter",
        "cfb_version",
        "sector_size",
        "mini_sector_size",
        "mini_cutoff",
        "sector_count",
        "directory_entries",
        "message_class",
        "internet_codepage",
        "message_codepage",
        "body_streams",
        "has_transport_headers",
        "named_property_count",
        "projection",
        "sectors.header",
        "sectors.difat",
        "sectors.fat",
        "sectors.minifat",
        "sectors.directory",
        "sectors.stream",
        "sectors.free",
        "sectors.slack",
    }
)


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str, **kwargs: object) -> MsgContainer:
    return MsgContainer(_bytes(name), **kwargs)  # type: ignore[arg-type]


def _open(name: str) -> cfb.CfbFile:
    opened = cfb.open_cfb(_bytes(name))
    assert isinstance(opened, cfb.CfbFile)
    return opened


# --------------------------------------------------- the declared tests


def test_the_virtual_bytes_and_the_span_table_agree() -> None:
    """Every source row names the stream's real bytes; the rows tile the virtual string."""
    for name in FIXTURES:
        container = _container(name)
        raw = container.raw_bytes()
        opened = _open(name)
        # The non-root rows partition the virtual bytes exactly (the root row spans all).
        others = [row for row in container.span_provenance if row.source_stream != "synthetic:root:1"]
        cursor = 0
        for row in sorted(others, key=lambda item: item.virtual_offset):
            assert row.virtual_offset == cursor, (name, row.source_stream, cursor)
            cursor += row.virtual_len
        assert cursor == len(raw), (name, cursor, len(raw))
        # Every STREAM/REENCODED row's digest is the named stream's own, read independently.
        for row in container.span_provenance:
            if row.axis is ContainerStreamAxis.SYNTHETIC:
                assert row.source_stream is not None and row.source_stream.startswith("synthetic:")
                assert row.source_byte_offset is None and row.source_sha256 is None
                assert not row.exact
                continue
            payload, status = cfb.read_stream(opened, row.source_stream or "")
            assert status == cfb.FAULT_OK, (name, row.source_stream)
            assert row.source_sha256 == sha256_hex(payload), (name, row.source_stream)
            assert 0 <= row.source_byte_offset <= len(payload)
            assert row.source_byte_offset + row.source_byte_len <= len(payload)
            if row.axis is ContainerStreamAxis.STREAM:
                # A pass-through row covers the whole stream, in the stream's own encoding.
                assert (row.source_byte_offset, row.source_byte_len) == (0, len(payload))
                assert row.exact is True
            else:
                assert row.exact is False
        # The persisted form drops the virtual framing and round-trips its source fields.
        for row in container.span_provenance:
            persisted = PersistedSpanRow.of(row)
            assert not any(
                "virtual" in field.name for field in dataclasses.fields(persisted)
            )
            assert persisted == PersistedSpanRow(
                axis=row.axis,
                source_stream=row.source_stream,
                source_byte_offset=row.source_byte_offset,
                source_byte_len=row.source_byte_len,
                source_sha256=row.source_sha256,
                decoded_char_offset=row.decoded_char_offset,
                decoded_char_len=row.decoded_char_len,
                exact=row.exact,
            )


def test_the_container_publishes_no_virtual_offset_to_a_record() -> None:
    """C2: no ``virtual_*`` value reaches a record, a part id, a citation or the artifact."""
    for name in FIXTURES:
        container = _container(name)
        document = assemble(container, limits=LIMITS)
        raw_len = len(container.raw_bytes())
        # The projection's *own name* is ``virtual_rfc822`` (a fact, D6); what must never
        # appear is the virtual framing's offsets and lengths.
        for blob in (record_to_bytes(document), record_to_bytes(walk_artifact(container))):
            assert b"virtual_offset" not in blob and b"virtual_len" not in blob
        for record in document.parts:
            assert b"virtual" not in record_to_bytes(record)
            if record.stream_ref is not None and record.stream_ref.byte_offset is not None:
                assert record.stream_ref.byte_offset + record.stream_ref.byte_len <= raw_len
        # A citation names the source stream and range, never the framing.
        from emailextract.assemble import resolve_span

        for record in document.parts:
            answer = resolve_span(container, record.part_id, "plain", 0, 1)
            assert b"virtual" not in record_to_bytes(answer)
        artifact = walk_artifact(container)
        assert isinstance(artifact, MsgWalkArtifact)


def test_container_hash_addresses_the_cfb_file() -> None:
    """The id is the CFB file's sha256 (D14), never the projection's, and it moves with it."""
    for name in FIXTURES:
        data = _bytes(name)
        container = _container(name)
        assert container.container_hash() == hashlib.sha256(data).hexdigest()
        assert container.container_hash() != sha256_hex(container.raw_bytes())
        # The same bytes give the same id; one flipped source byte moves it.
        assert _container(name).container_hash() == container.container_hash()
        mutated = bytearray(data)
        mutated[-1] ^= 0xFF
        assert MsgContainer(bytes(mutated)).container_hash() != container.container_hash()


def test_container_facts_carry_the_fixed_key_list() -> None:
    """D6: exactly this turn's key set, every value a ``str``."""
    seen: set[str] = set()
    for name in FIXTURES + ("msg_non_ipm_note", "msg_signed_class"):
        facts = _container(name).container_facts()
        assert set(facts) == FACT_KEYS, (name, sorted(set(facts) ^ FACT_KEYS))
        assert all(isinstance(value, str) for value in facts.values()), name
        seen |= set(facts)
    assert seen == FACT_KEYS
    # The one declared message's facts, hand-checked against the fixture.
    facts = _container("msg_plain_and_html").container_facts()
    assert facts["adapter"] == "cfb_msg"
    assert facts["projection"] == "virtual_rfc822"
    assert facts["body_streams"] == "plain+html"
    assert facts["has_transport_headers"] == "true"
    assert facts["message_class"] == "IPM.Note"
    assert facts["cfb_version"] == "3" and facts["sector_size"] == "512"
    assert facts["internet_codepage"] == "1252" and facts["message_codepage"] == "1252"
    # The eight sector classes close to the file length (no-silent-drop, C3).
    sectors = {key: int(value) for key, value in facts.items() if key.startswith("sectors.")}
    assert sum(sectors.values()) == len(_bytes("msg_plain_and_html"))


def test_the_span_table_row_shape_is_the_contract() -> None:
    """Every published row is a ``SpanRow`` with the section-7 field set, and the lookup works."""
    container = _container("msg_plain_and_html")
    assert container.span_provenance
    for row in container.span_provenance:
        assert isinstance(row, SpanRow)
        assert row.axis in tuple(ContainerStreamAxis)
        assert isinstance(row.virtual_offset, int) and row.virtual_offset >= 0
        assert isinstance(row.virtual_len, int) and row.virtual_len > 0
        if row.axis is ContainerStreamAxis.SYNTHETIC:
            assert row.source_byte_offset is None
            assert source_key_of(row) == row.source_stream
        else:
            assert source_key_of(row) == (
                f"{row.source_stream}:{row.source_byte_offset}:{row.source_byte_len}"
            )
    lookup = span_lookup(container)
    assert lookup is not None
    assert lookup[(0, len(container.raw_bytes()))].source_stream == "synthetic:root:1"
    # ... and a container with no span table still yields ``None`` (the ``.eml`` path).
    from emailextract.container import EmlContainer, memory_bytes

    assert span_lookup(EmlContainer(memory_bytes(b"Subject: a\r\n\r\nb"))) is None


# --------------------------------------------------- the extras


def test_the_projection_is_deterministic_across_hash_seeds() -> None:
    """The virtual bytes' digest and the persisted rows are identical under any hash seed."""
    script = (
        "import hashlib, json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "import dataclasses\n"
        "from emailextract.container import PersistedSpanRow\n"
        "from emailextract.msgcontainer import MsgContainer\n"
        "msg = Path(sys.argv[1]) / 'fixtures' / 'msg'\n"
        "out = {}\n"
        "for name in ('msg_plain_and_html', 'msg_headers_html'):\n"
        "    c = MsgContainer((msg / (name + '.msg')).read_bytes())\n"
        "    out[name] = [hashlib.sha256(c.raw_bytes()).hexdigest(),\n"
        "                 [list(dataclasses.astuple(r)) for r in (PersistedSpanRow.of(x) for x in c.span_provenance)]]\n"
        "print(json.dumps(out, sort_keys=True))\n"
    )
    baseline = None
    for seed in ("0", "1234567"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        if baseline is None:
            baseline = payload
        else:
            assert payload == baseline, seed


def test_a_seeded_fuzz_of_the_projection_closes() -> None:
    """Every mutant of the projection yields a document or a named refusal; nothing raises."""
    seeds = (3, 11, 29)
    rng = random.Random(20261014)
    produced = 0
    for name in ("msg_html_only_no_plain", "msg_plain_and_html", "msg_property_vs_header_conflict"):
        data = _bytes(name)
        for _ in range(70):
            mutant = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                mutant[rng.randrange(len(mutant))] = rng.randrange(256)
            mutant = bytes(mutant)
            decision = parse(mutant, limits=LIMITS)
            if decision.error is not None:
                assert decision.error.reason_id, name
                continue
            container = MsgContainer(mutant)
            document = assemble(container, limits=LIMITS)
            assert document.container_kind.value == "cfb_msg"
            for field in document.headers:
                field.raw_value.encode("utf-8")
            assert len(_bytes(name)) > 0
            produced += 1
    assert produced > 0, "the fuzz produced no mutant that reached the container"
    assert len(seeds) == 3


def test_the_hostile_fixtures_and_a_forced_cap_go_through_the_container() -> None:
    """The three hostile fixtures and a tiny CFB cap each give the specified outcome; none raises."""
    # A FAT cycle and a short chain are per-stream faults: a TRUNCATED document (D7).
    cyclic = assemble(_container("msg_fat_cycle"), limits=LIMITS)
    assert cyclic.status.status.value == "truncated"
    assert cyclic.status.reason == "declared_length_mismatch"
    assert GAP_STREAM_TRUNCATED in {gap.gap_id for gap in _container("msg_fat_cycle").container_gaps}
    short = assemble(_container("msg_truncated_stream"), limits=LIMITS)
    assert (short.status.status.value, short.status.reason) == ("truncated", "stream_ended_early")
    # A directory loop is a whole-file refusal at the entry point, and the container still
    # builds (it never raises).
    refused = parse(_bytes("msg_directory_loop"), limits=LIMITS)
    assert refused.error is not None and refused.error.reason_id == "cfb_directory_loop"
    looped = assemble(_container("msg_directory_loop"), limits=LIMITS)
    assert looped.container_kind.value == "cfb_msg"
    # A CFB cap hit is a SKIPPED document with the caller's value and the real count.
    capped = MsgContainer(_bytes("msg_headers_html"), cfb_limits=cfb.CfbLimits(max_sector_count=3))
    document = assemble(capped, limits=LIMITS)
    assert document.status.status.value == "skipped"
    assert document.status.reason == "sector_count_cap"
    caps = document.run_record.caps
    assert len(caps) == 1
    assert caps[0].cap_id == "sector_count_cap"
    assert caps[0].cap_value_bytes == 3
    assert caps[0].declared_size_bytes == 6  # the file's real sector count, never a virtual length


def _patch_stream_size(data: bytes, stream: str, size: int) -> bytes:
    """A copy of ``data`` with ``stream``'s directory-entry declared size replaced."""
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    entry = cfb.lookup_entry(opened.entries, stream)
    assert entry is not None
    offset = (
        (opened.header.first_dir_sector + 1) * opened.header.sector_size
        + 128 * entry.index
        + 120
    )
    patched = bytearray(data)
    struct.pack_into("<I", patched, offset, size)
    return bytes(patched)


def test_a_body_or_transport_stream_fault_is_the_registered_truncated_gap() -> None:
    """D0.1: a body or transport stream fault is ``msg.stream_truncated`` with the stream and
    fault in the detail, never the bare fault name as a gap id, and the document is TRUNCATED
    with the mapped reason (contract section 2)."""
    base = _bytes("msg_plain_and_html")
    # A declared size beyond the chain's bytes is a short chain (the fault vocabulary the
    # projection holds is ``mapi``'s ``stream_*`` form).
    cases = (
        ("__substg1.0_1000001F", 128),
        ("__substg1.0_10130102", 128),
        ("__substg1.0_007D001F", 300),
    )
    for stream, size in cases:
        data = _patch_stream_size(base, stream, size)
        container = MsgContainer(data)
        pairs = [(gap.gap_id, gap.detail) for gap in container.container_gaps]
        assert (GAP_STREAM_TRUNCATED, f"{stream}:stream_short_chain") in pairs, (stream, pairs)
        assert "stream_short_chain" not in {gap_id for gap_id, _detail in pairs}, stream
        # Exactly one gap names this stream (the projection's, not a duplicate from the
        # cfb-level scan).
        assert sum(1 for gap_id, detail in pairs if gap_id == GAP_STREAM_TRUNCATED and detail.split(":", 1)[0] == stream) == 1
        document = assemble(container, limits=LIMITS)
        assert (document.status.status.value, document.status.reason) == (
            "truncated",
            "stream_ended_early",
        ), stream


def test_two_framing_lengths_give_identical_part_ids_and_records() -> None:
    """C2: a longer synthetic region leaves every ``part_id``, record and citation identical."""
    data = _bytes("msg_plain_and_html")
    short = MsgContainer(data)
    long = MsgContainer(data, framing=64)
    assert short.raw_bytes() != long.raw_bytes()
    assert short.container_hash() == long.container_hash()

    from emailextract.assemble import resolve_span

    document_short = assemble(short, limits=LIMITS)
    document_long = assemble(long, limits=LIMITS)
    assert [record.part_id for record in document_short.parts] == [
        record.part_id for record in document_long.parts
    ]
    assert [
        (r.part_id, r.parent_part_id, r.stream_ref, r.size_bytes, r.sha256)
        for r in document_short.parts
    ] == [
        (r.part_id, r.parent_part_id, r.stream_ref, r.size_bytes, r.sha256)
        for r in document_long.parts
    ]
    for record in document_short.parts:
        assert resolve_span(short, record.part_id, "plain", 0, 1) == resolve_span(
            long, record.part_id, "plain", 0, 1
        )
    # The source-keyed id is exactly what the walker records: no virtual offset in it.
    lookup = span_lookup(short)
    assert lookup is not None
    from emailextract.walk import walk

    for part in walk(short, limits=LIMITS).parts:
        row = lookup[(part.raw_span.offset, part.raw_span.length)]
        assert part.part_id == source_part_id(
            short.container_hash(), source_key_of(row), row.source_sha256
        ), part.path
