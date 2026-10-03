"""Turn 0.2: the run record and the re-ingest-is-a-no-op harness (build spec, Turn 0.2).

The rules under test: hashed inputs (content + versions) are the key; recorded
only inputs (interpreter, platform) are recorded and can never touch a key; each
artifact reports hit/miss; re-ingest of unchanged input is a lookup that writes
nothing; and the same bytes give the same ids and a byte-identical store -- the
property the 3.14/3.11 comparison depends on.
"""

from __future__ import annotations

import pytest
from docextract_core.codec import from_json, to_json

from emailextract import versions
from emailextract.container import EmlContainer, memory_bytes
from emailextract.ids import sha256_hex, walk_key
from emailextract.store import (
    ArtifactOutcome,
    RunInputs,
    WalkArtifact,
    artifact_key,
    hashed_inputs,
    ingest,
    reingest_is_noop,
    recorded_only_inputs,
    store_snapshot,
    walk_artifact,
    walk_store,
)

MESSAGE = b"From: a@example.com\r\nSubject: store\r\n\r\nbody line\r\n"


def test_a_run_record_separates_hashed_inputs_from_recorded_only_inputs() -> None:
    container = EmlContainer(memory_bytes(MESSAGE))
    hashed = hashed_inputs(container)
    assert set(hashed) == {
        "container_hash",
        "email_parser_version",
        "decode_chain_version",
        "output_schema_version",
    }
    assert hashed["container_hash"] == sha256_hex(MESSAGE)
    recorded = recorded_only_inputs()
    assert set(recorded) == {"python", "implementation", "platform"}
    assert set(hashed).isdisjoint(recorded)
    # The key is the hashed inputs, exactly -- nothing recorded-only is an input to it.
    assert artifact_key(container) == walk_key(
        hashed["container_hash"],
        hashed["email_parser_version"],
        hashed["decode_chain_version"],
        hashed["output_schema_version"],
    )


def test_each_artifact_reports_hit_or_miss(tmp_path) -> None:
    store = walk_store(tmp_path)
    container = EmlContainer(memory_bytes(MESSAGE))
    first = ingest(container, store)
    assert first.artifacts == [ArtifactOutcome(key=artifact_key(container), hit=False, wrote=True)]
    assert first.writes == 1
    second = ingest(container, store)
    assert second.artifacts == [ArtifactOutcome(key=artifact_key(container), hit=True, wrote=False)]
    assert second.writes == 0
    assert second.run_inputs.hashed == first.run_inputs.hashed


def test_an_outcome_is_exactly_one_of_hit_and_wrote() -> None:
    with pytest.raises(ValueError):
        ArtifactOutcome(key="k", hit=True, wrote=True)
    with pytest.raises(ValueError):
        ArtifactOutcome(key="k", hit=False, wrote=False)
    with pytest.raises(ValueError):
        ArtifactOutcome(key="", hit=True, wrote=False)


def test_re_ingest_is_a_no_op_over_a_throwaway_store(tmp_path) -> None:
    store = walk_store(tmp_path)
    container = EmlContainer(memory_bytes(MESSAGE))
    ingest(container, store)
    before = store_snapshot(tmp_path)
    assert reingest_is_noop(container, store) is True
    assert store_snapshot(tmp_path) == before
    # The harness says False when a write really happened -- it is not a constant.
    assert reingest_is_noop(EmlContainer(memory_bytes(MESSAGE + b"!")), store) is False


def test_the_same_bytes_give_the_same_ids_and_a_byte_identical_store(tmp_path) -> None:
    first_root = tmp_path / "one"
    second_root = tmp_path / "two"
    for root in (first_root, second_root):
        store = walk_store(root)
        path = tmp_path / "message.eml"
        path.write_bytes(MESSAGE)
        ingest(EmlContainer(path), store)  # both input routes, same order
        ingest(EmlContainer(memory_bytes(MESSAGE)), store)
    assert store_snapshot(first_root) == store_snapshot(second_root)
    assert store_snapshot(first_root)["walks/index.json"]


def test_an_artifact_round_trips_through_the_strict_codec() -> None:
    artifact = walk_artifact(EmlContainer(memory_bytes(MESSAGE)))
    assert isinstance(artifact, WalkArtifact)
    assert from_json(WalkArtifact, to_json(artifact)) == artifact
    assert isinstance(artifact.walk.parts[0].raw_span.offset, int)


def test_a_version_bump_is_a_new_key_never_an_overwrite(tmp_path, monkeypatch) -> None:
    store = walk_store(tmp_path)
    container = EmlContainer(memory_bytes(MESSAGE))
    first = ingest(container, store)
    monkeypatch.setattr(
        versions, "EMAIL_PARSER_VERSION", versions.EMAIL_PARSER_VERSION + ".bumped"
    )
    second = ingest(container, store)
    assert second.writes == 1
    assert second.artifacts[0].key != first.artifacts[0].key
    assert store.find(first.artifacts[0].key) is not None
    assert store.find(second.artifacts[0].key) is not None


def test_a_run_inputs_shape_is_frozen() -> None:
    inputs = RunInputs(hashed={"a": "1"}, recorded_only={"b": "2"})
    assert inputs.hashed == {"a": "1"}
    with pytest.raises(Exception):
        inputs.hashed = {}  # type: ignore[misc]
