"""Turn 0.2: the run record and the re-ingest-is-a-no-op harness (build spec, Turn 0.2).

The rules under test: hashed inputs (content + versions) are the key; recorded
only inputs (interpreter, platform) are recorded and can never touch a key; each
artifact reports hit/miss; re-ingest of unchanged input is a lookup that writes
nothing; and the same bytes give the same ids and a byte-identical store -- the
property the 3.14/3.11 comparison depends on.

Turn 1.9 adds the **document** artifact beside the walk artifact: the walk key is
still exactly the versions the walk artifact names (and it moves with
``OUTPUT_SCHEMA_VERSION``, which it names and which moved to ``5`` this turn), and
the document key is the container hash plus the two record versions, every
projection version and the ``Limits`` fingerprint -- never a path, never the
interpreter.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest
from docextract_core.codec import from_json, to_json

from emailextract import ids, versions
from emailextract.assemble import document_key, projection_versions
from emailextract.container import EmlContainer, memory_bytes
from emailextract.ids import sha256_hex, walk_key
from emailextract.parse import Limits
from emailextract.store import (
    ArtifactOutcome,
    DocumentArtifact,
    RunInputs,
    WalkArtifact,
    artifact_key,
    document_artifact,
    document_store,
    hashed_inputs,
    ingest,
    read_document,
    recorded_only_inputs,
    reingest_document_is_noop,
    reingest_is_noop,
    store_document,
    store_snapshot,
    walk_artifact,
    walk_store,
)

store_module = importlib.import_module("emailextract.store")

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


# --------------------------------------------------------------- the walk artifact (1.9)


def test_a_walk_artifact_is_keyed_by_its_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    """The walk key is exactly the versions the walk artifact names -- and only those."""
    container = EmlContainer(memory_bytes(MESSAGE))
    key = artifact_key(container)
    assert key == walk_key(
        container.container_hash(),
        versions.EMAIL_PARSER_VERSION,
        versions.DECODE_CHAIN_VERSION,
        versions.OUTPUT_SCHEMA_VERSION,
    )
    # Turn 1.9 moved ``OUTPUT_SCHEMA_VERSION`` to 5; the walk artifact names it, so the
    # walk key moves with it -- a key moves with every version it names.
    assert versions.OUTPUT_SCHEMA_VERSION == "5"
    artifact = walk_artifact(container)
    assert artifact.key == key
    assert artifact.output_schema_version == "5"
    # The projections the walker does NOT run are not in it: bumping one leaves the walk
    # key exactly where it was (``DECODE_CHAIN_VERSION`` is in both, on purpose: the
    # walker's decode chain is what the walk artifact measures).
    for name in (
        "TEXTMODEL_VERSION",
        "TEXTPART_VERSION",
        "HEADERTEXT_VERSION",
        "HTMLTEXT_VERSION",
        "QUOTE_RULES_VERSION",
    ):
        monkeypatch.setattr(versions, name, getattr(versions, name) + ".bumped")
    assert artifact_key(container) == key
    # ... and each version it does name moves it.
    for name in ("EMAIL_PARSER_VERSION", "DECODE_CHAIN_VERSION", "OUTPUT_SCHEMA_VERSION"):
        monkeypatch.setattr(versions, name, getattr(versions, name) + ".bumped")
    assert artifact_key(container) != key
    assert set(projection_versions()) == {
        "TEXTMODEL_VERSION",
        "TEXTPART_VERSION",
        "HEADERTEXT_VERSION",
        "HTMLTEXT_VERSION",
        "DECODE_CHAIN_VERSION",
        "QUOTE_RULES_VERSION",
    }


# --------------------------------------------------------------- the document artifact (1.9)


def test_the_document_key_is_the_hashed_inputs_and_nothing_else(tmp_path: Path) -> None:
    """The document key is content plus versions plus the Limits -- no path, no interpreter."""
    limits = Limits.untrusted()
    path = tmp_path / "message.eml"
    path.write_bytes(MESSAGE)
    by_path = document_key(EmlContainer(path).container_hash(), limits=limits)
    by_memory = document_key(EmlContainer(memory_bytes(MESSAGE)).container_hash(), limits=limits)
    assert by_path == by_memory
    artifact = document_artifact(EmlContainer(memory_bytes(MESSAGE)), limits=limits)
    assert artifact.key == by_path
    assert artifact.output_schema_version == "5"
    assert artifact.projection_versions == projection_versions()
    assert artifact.email_parser_version == versions.EMAIL_PARSER_VERSION


def test_a_document_round_trips_through_the_store(tmp_path: Path) -> None:
    """A stored document reads back equal, and a re-ingest writes nothing."""
    collection = document_store(tmp_path / "store")
    container = EmlContainer(memory_bytes(MESSAGE))
    limits = Limits.untrusted()
    artifact, created = store_document(container, collection, limits=limits)
    assert created is True and isinstance(artifact, DocumentArtifact)
    assert read_document(collection, artifact.key) == artifact.document
    before = store_snapshot(tmp_path / "store")
    assert reingest_document_is_noop(container, collection, limits=limits) is True
    assert store_snapshot(tmp_path / "store") == before
    assert reingest_document_is_noop(
        EmlContainer(memory_bytes(MESSAGE + b"!")), collection, limits=limits
    ) is False
    # The stored bytes are the strict codec's, and the artifact round-trips through it.
    stored = (tmp_path / "store" / "documents" / f"{artifact.key}.json").read_text("utf-8")
    assert from_json(DocumentArtifact, stored) == artifact


def test_two_stores_built_from_the_same_inputs_are_byte_identical(tmp_path: Path) -> None:
    """The same inputs give byte-identical stores, and a path or the environment is not one."""
    limits = Limits.untrusted()
    for name in ("one", "two"):
        collection = document_store(tmp_path / name)
        path = tmp_path / f"{name}.eml"
        path.write_bytes(MESSAGE)
        store_document(EmlContainer(path), collection, limits=limits)
        store_document(EmlContainer(memory_bytes(MESSAGE)), collection, limits=limits)
    assert store_snapshot(tmp_path / "one") == store_snapshot(tmp_path / "two")
    # A raised cap is a different run: a different Limits is a different key.
    raised = dataclasses.replace(limits, max_parts=limits.max_parts + 1)
    assert document_key(ids.container_hash(MESSAGE), limits=raised) != document_key(
        ids.container_hash(MESSAGE), limits=limits
    )


def test_the_projection_version_dropped_from_the_key_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutation: drop the projection versions from the key; the key stops moving with them.

    The anti-vacuity triple: (a) the patched symbol exists, (b) the patch is reached
    (the counter), (c) the observation differs -- clean, bumping ``QUOTE_RULES_VERSION``
    moves the key; mutated, the same bump leaves the key exactly where it was.
    """
    real = store_module.document_key
    assert callable(real)
    limits = Limits.untrusted()
    container = EmlContainer(memory_bytes(MESSAGE))
    original_rules = versions.QUOTE_RULES_VERSION
    baseline = document_key(container.container_hash(), limits=limits)

    reached = {"count": 0}

    def key_without_projections(container_hash_value: str, *, limits: Limits) -> str:
        reached["count"] += 1
        return walk_key(
            container_hash_value,
            versions.OUTPUT_SCHEMA_VERSION,
            versions.EMAIL_PARSER_VERSION,
            store_module.limits_fingerprint(limits),
        )

    monkeypatch.setattr(store_module, "document_key", key_without_projections)
    unbumped = document_artifact(container, limits=limits).key
    assert reached["count"] > 0, "the mutation's patch was never entered (vacuous)"
    monkeypatch.setattr(versions, "QUOTE_RULES_VERSION", original_rules + ".bumped")
    bumped = document_artifact(container, limits=limits).key
    # The control: the real key moves with the projection version...
    assert document_key(container.container_hash(), limits=limits) != baseline
    # ... and the mutated one does not, which is exactly the drift the mutation hides.
    assert bumped == unbumped, "the mutated key did not drop the projection versions"
