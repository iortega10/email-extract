"""Turn 0.2 run record and the re-ingest-is-a-no-op harness (build spec, Turn 0.2).

One run record, :class:`IngestRun`, separates the two kinds of input honestly:

* **hashed inputs** -- everything an artifact's bytes depend on: the container
  hash and the version constants. These are the key members; a cache is only
  valid for them.
* **recorded-only inputs** -- the interpreter and the platform. They are
  recorded (a run is reproducible or it explains why not) and must **never**
  affect artifact bytes or keys, which is why the ledger fingerprints have to be
  identical across interpreters.

Per-artifact **hit/miss** is the third fact: a re-ingest of unchanged input is a
hit and writes nothing (``docextract_core.Collection.save`` is idempotent by
key), which :func:`reingest_is_noop` proves over a throwaway store. The store is
built on the core ``Collection`` -- the same substrate word-extract and
form-extract use -- and nothing here reads a file the caller did not hand it.

Turn 1.9 adds the **document** artifact beside the walk artifact:

* the walk artifact is unchanged in shape and still keyed by the versions it names
  (``EMAIL_PARSER_VERSION``, ``DECODE_CHAIN_VERSION``, ``OUTPUT_SCHEMA_VERSION``).
  ``OUTPUT_SCHEMA_VERSION`` moved to ``5`` this turn, so the walk key **does** move:
  the walk artifact names that constant, and a key must move with a version it names;
* :class:`DocumentArtifact` is keyed by ``assemble.document_key`` -- the container
  hash, ``OUTPUT_SCHEMA_VERSION``, ``EMAIL_PARSER_VERSION``, every projection version
  the record stamps and the ``Limits`` fingerprint. A raised cap is a different run
  and a different key; a path and the interpreter are recorded-only and never enter
  one.

The store layout is ``<root>/walks/``, ``<root>/documents/`` and (Turn 1.9's
ingest) ``<root>/manifests/``, each a core ``Collection`` with its own
``index.json``.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from docextract_core import Collection

from . import versions
from .assemble import assemble, document_key, limits_fingerprint, projection_versions
from .container import Container
from .ids import sha256_hex, walk_key
from .model import EmailDocument
from .parse import Limits
from .walk import WalkResult, walk

__all__ = [
    "ArtifactOutcome",
    "DocumentArtifact",
    "IngestRun",
    "RunInputs",
    "WalkArtifact",
    "artifact_key",
    "document_artifact",
    "document_store",
    "hashed_inputs",
    "ingest",
    "read_document",
    "recorded_only_inputs",
    "reingest_document_is_noop",
    "reingest_is_noop",
    "store_document",
    "store_snapshot",
    "walk_artifact",
    "walk_store",
]


@dataclass(frozen=True)
class RunInputs:
    """The two input classes, kept apart on purpose (see the module docstring)."""

    hashed: dict[str, str] = field(default_factory=dict)
    recorded_only: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactOutcome:
    """Per-artifact hit/miss: ``hit`` is what re-ingest must produce."""

    key: str
    hit: bool
    wrote: bool

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("artifact_outcome.key must be non-empty")
        if self.hit == self.wrote:
            raise ValueError("artifact_outcome: exactly one of hit/wrote is set")


@dataclass(frozen=True)
class WalkArtifact:
    """The stored artifact: one container's walk, keyed by its hashed inputs."""

    key: str
    container_hash: str
    email_parser_version: str
    decode_chain_version: str
    output_schema_version: str
    walk: WalkResult

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("walk_artifact.key must be non-empty")
        if not self.container_hash:
            raise ValueError("walk_artifact.container_hash must be non-empty")


@dataclass(frozen=True)
class IngestRun:
    """The run record: run inputs plus every artifact's hit/miss."""

    container_hash: str
    run_inputs: RunInputs
    artifacts: list[ArtifactOutcome]

    @property
    def writes(self) -> int:
        return sum(1 for outcome in self.artifacts if outcome.wrote)


def hashed_inputs(container: Container) -> dict[str, str]:
    """The inputs an artifact's bytes depend on: content hash plus versions."""
    return {
        "container_hash": container.container_hash(),
        "email_parser_version": versions.EMAIL_PARSER_VERSION,
        "decode_chain_version": versions.DECODE_CHAIN_VERSION,
        "output_schema_version": versions.OUTPUT_SCHEMA_VERSION,
    }


def recorded_only_inputs() -> dict[str, str]:
    """Recorded, never keyed on: interpreter and platform must not move bytes."""
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": sys.platform,
    }


def artifact_key(container: Container) -> str:
    """The artifact key: exactly the hashed inputs, nothing recorded-only."""
    return walk_key(
        container.container_hash(),
        versions.EMAIL_PARSER_VERSION,
        versions.DECODE_CHAIN_VERSION,
        versions.OUTPUT_SCHEMA_VERSION,
    )


def walk_artifact(container: Container) -> WalkArtifact:
    """Measure the container and package the result under its hashed inputs."""
    return WalkArtifact(
        key=artifact_key(container),
        container_hash=container.container_hash(),
        email_parser_version=versions.EMAIL_PARSER_VERSION,
        decode_chain_version=versions.DECODE_CHAIN_VERSION,
        output_schema_version=versions.OUTPUT_SCHEMA_VERSION,
        walk=walk(container),
    )


def walk_store(root: str | Path, *, read_only: bool = False) -> Collection[WalkArtifact]:
    """The throwaway store: one ``Collection`` of walk artifacts, keyed by id."""
    return Collection(
        Path(root) / "walks",
        WalkArtifact,
        id_of=lambda artifact: artifact.key,
        key_of=lambda artifact: artifact.key,
        read_only=read_only,
    )


def ingest(container: Container, store: Collection[WalkArtifact]) -> IngestRun:
    """Store this container's walk and report each artifact's hit/miss.

    A hit is an artifact the store already held under the same key: nothing is
    written and the stored record wins, so re-ingest of unchanged input cannot
    rewrite, reorder or re-encode a store.
    """
    artifact = walk_artifact(container)
    _saved, created = store.save(artifact)
    outcome = ArtifactOutcome(key=artifact.key, hit=not created, wrote=created)
    return IngestRun(
        container_hash=container.container_hash(),
        run_inputs=RunInputs(
            hashed=hashed_inputs(container), recorded_only=recorded_only_inputs()
        ),
        artifacts=[outcome],
    )


def store_snapshot(root: str | Path) -> dict[str, str]:
    """``{relative path: sha256}`` of everything in the store, for byte comparison."""
    base = Path(root)
    return {
        path.relative_to(base).as_posix(): sha256_hex(path.read_bytes())
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def reingest_is_noop(container: Container, store: Collection[WalkArtifact]) -> bool:
    """The re-ingest-is-a-no-op harness: the second ingest writes nothing.

    True only when the second run is all hits, reports no write, and leaves the
    store byte-identical (``store_snapshot`` before and after).
    """
    before = store_snapshot(store.root.parent)
    second = ingest(container, store)
    after = store_snapshot(store.root.parent)
    return (
        second.writes == 0
        and all(outcome.hit for outcome in second.artifacts)
        and before == after
    )


# --------------------------------------------------------------- the document (1.9)


@dataclass(frozen=True)
class DocumentArtifact:
    """The assembled :class:`EmailDocument`, keyed by exactly its hashed inputs.

    ``key`` is ``assemble.document_key``: container hash, the two record versions,
    every projection version and the ``Limits`` fingerprint. ``projection_versions``
    and ``limits_fingerprint`` are restated beside the document so a reader can see
    what the key was made of without decoding the record. A record read back from a
    store equals the record assembled, with its own axes intact.
    """

    key: str
    container_hash: str
    email_parser_version: str
    output_schema_version: str
    projection_versions: dict[str, str]
    limits_fingerprint: str
    document: EmailDocument

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("document_artifact.key must be non-empty")
        if not self.container_hash:
            raise ValueError("document_artifact.container_hash must be non-empty")
        if not isinstance(self.document, EmailDocument):
            raise ValueError("document_artifact.document must be an EmailDocument")
        if not self.projection_versions:
            raise ValueError("document_artifact.projection_versions must not be empty")


def document_artifact(container: Container, *, limits: Limits) -> DocumentArtifact:
    """Assemble the container and package the result under its hashed inputs."""
    document = assemble(container, limits=limits)
    return DocumentArtifact(
        key=document_key(container.container_hash(), limits=limits),
        container_hash=container.container_hash(),
        email_parser_version=versions.EMAIL_PARSER_VERSION,
        output_schema_version=versions.OUTPUT_SCHEMA_VERSION,
        projection_versions=projection_versions(),
        limits_fingerprint=limits_fingerprint(limits),
        document=document,
    )


def document_store(root: str | Path, *, read_only: bool = False) -> Collection[DocumentArtifact]:
    """The document collection of a store: ``<root>/documents``, keyed by its id."""
    return Collection(
        Path(root) / "documents",
        DocumentArtifact,
        id_of=lambda artifact: artifact.key,
        key_of=lambda artifact: artifact.key,
        read_only=read_only,
    )


def store_document(
    container: Container, store: Collection[DocumentArtifact], *, limits: Limits
) -> tuple[DocumentArtifact, bool]:
    """Store this container's document; ``(artifact, created)``.

    A hit is an artifact the store already held under the same key: nothing is
    written and the stored record wins, so a re-ingest of unchanged bytes cannot
    rewrite, reorder or re-encode a store.
    """
    artifact = document_artifact(container, limits=limits)
    _saved, created = store.save(artifact)
    return artifact, created


def read_document(store: Collection[DocumentArtifact], key: str) -> EmailDocument | None:
    """The document stored under ``key``, or ``None`` -- with its own axes intact."""
    artifact = store.find(key)
    return None if artifact is None else artifact.document


def reingest_document_is_noop(
    container: Container, store: Collection[DocumentArtifact], *, limits: Limits
) -> bool:
    """The document-level no-op harness: the second ingest writes nothing at all."""
    before = store_snapshot(store.root.parent)
    _artifact, created = store_document(container, store, limits=limits)
    after = store_snapshot(store.root.parent)
    return created is False and before == after
