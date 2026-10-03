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
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from docextract_core import Collection

from . import versions
from .container import Container
from .ids import sha256_hex, walk_key
from .walk import WalkResult, walk

__all__ = [
    "ArtifactOutcome",
    "IngestRun",
    "RunInputs",
    "WalkArtifact",
    "artifact_key",
    "hashed_inputs",
    "ingest",
    "reingest_is_noop",
    "recorded_only_inputs",
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
