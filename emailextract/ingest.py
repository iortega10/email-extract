"""Turn 1.9: ingest a file or a directory into a store, and record what happened.

``ingest_path(path_or_dir, store, *, limits, listing=None) -> IngestManifest``
visits files **one at a time** (a document is never held for the whole run), stores
each one as a document artifact and returns a deterministic manifest. It never
follows or fetches anything.

The policies, each with its own named test:

1. **Order.** Directory ingest visits files in the order of the POSIX-normalised
   relative path compared as **UTF-8 bytes, bytewise** -- so ``A.eml`` sorts before
   ``a.eml`` and a non-ASCII name sorts by its bytes. Case-differing names cannot
   coexist on Windows, so ``listing`` is an injectable seam (a callable taking the
   root and returning relative names) that the ordering test drives directly; a real
   non-ASCII name is exercised in ``tmp_path``.
2. **Symlinks.** A symlinked **directory** is never recursed: it is a recorded
   ``skipped(symlinked_directory)`` row, so no loop is possible. A symlinked **file**
   is read as its target.
3. **Per-file outcomes.** An unreadable file (a permission error, a vanished path) is
   ``skipped(file_unreadable)``; one over ``Limits.max_input_bytes`` is
   ``skipped(file_over_cap)``; one the entry point refuses is ``skipped(<named
   error>)`` (``parse``'s closed vocabulary: ``not_a_message``,
   ``cfb_msg_unsupported``, ...). The run **continues** in every case.
4. **Re-ingest is a no-op.** Unchanged bytes give the same document key, so the store
   writes nothing the second time: the row says ``hit``.
5. **A path is never identity.** The same bytes under two paths are **one document and
   two manifest rows**: no path enters a cache key or the document, and path
   provenance lives only in this manifest.
6. **The same Message-ID with different bytes is not merged.** Both documents are
   stored, neither is merged, and **nothing about the relation is recorded** -- the
   ``same_message_candidates`` axis stays not built. "Not merged" must never be read
   as "recorded".

The manifest is deterministic: byte-identical across runs, interpreters and
directory-listing orders, and it is itself a stored, codec-encoded record.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final

from docextract_core import Collection
from docextract_core.codec import to_json

from . import parse
from .assemble import limits_fingerprint
from .container import EmlContainer, memory_bytes
from .ids import FILE_OVER_CAP, FILE_UNREADABLE, SYMLINKED_DIRECTORY, sha256_hex
from .parse import Limits
from .store import DocumentArtifact, store_document

__all__ = [
    "HIT",
    "OUTCOMES",
    "SKIPPED",
    "SKIP_REASONS",
    "WRITTEN",
    "IngestManifest",
    "ManifestRow",
    "ingest_path",
    "manifest_store",
    "read_manifest",
]

#: The three manifest outcomes: exactly one per row.
WRITTEN: Final[str] = "written"
HIT: Final[str] = "hit"
SKIPPED: Final[str] = "skipped"
OUTCOMES: Final[tuple[str, ...]] = (WRITTEN, HIT, SKIPPED)

#: The closed reason vocabulary a ``skipped`` row carries: the three file-level
#: outcomes this module owns (``ids``) plus the entry point's own named errors
#: (``parse.NAMED_ERROR_REASONS``), which is where a refused *content* is named.
SKIP_REASONS: Final[tuple[str, ...]] = (
    FILE_UNREADABLE,
    FILE_OVER_CAP,
    SYMLINKED_DIRECTORY,
    *parse.NAMED_ERROR_REASONS,
)

#: How this module walks a directory when no ``listing`` seam is supplied.
Listing = Callable[[Path], "list[str]"]

_MANIFESTS: Final[str] = "manifests"


@dataclass(frozen=True)
class ManifestRow:
    """One file's provenance: ``path -> container_hash -> outcome`` (policy 5).

    ``path`` is the POSIX-normalised path **relative to the ingested root**, never
    absolute (the manifest is compared byte for byte across machines). A row that
    wrote or hit a document names the container hash it read; a ``skipped`` row read
    nothing, so its hash is empty and its closed ``reason_id`` is set instead.
    """

    path: str
    container_hash: str
    outcome: str
    reason_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("manifest_row.path must be a non-empty str")
        if self.path.startswith("/") or "\\" in self.path:
            raise ValueError(
                f"manifest_row.path must be a POSIX-normalised relative path, got {self.path!r}"
            )
        if self.outcome not in OUTCOMES:
            raise ValueError(f"manifest_row.outcome must be one of {OUTCOMES}, got {self.outcome!r}")
        if self.outcome == SKIPPED:
            if self.reason_id not in SKIP_REASONS:
                raise ValueError(
                    f"manifest_row.reason_id must be one of {SKIP_REASONS} when skipped, "
                    f"got {self.reason_id!r}"
                )
            if self.container_hash:
                raise ValueError("manifest_row: a skipped row read no bytes, so its hash is empty")
        else:
            if self.reason_id is not None:
                raise ValueError("manifest_row: only a skipped row carries a reason_id")
            if not self.container_hash:
                raise ValueError("manifest_row: a written/hit row names its container hash")


@dataclass(frozen=True)
class IngestManifest:
    """One ingest run: the sorted rows and the ``Limits`` the run was made under."""

    rows: list[ManifestRow] = field(default_factory=list)
    limits_fingerprint: str = ""

    def __post_init__(self) -> None:
        for row in self.rows:
            if not isinstance(row, ManifestRow):
                raise ValueError(f"ingest_manifest.rows must hold ManifestRows, got {row!r}")
        expected = sorted(self.rows, key=lambda row: row.path.encode("utf-8"))
        if list(self.rows) != expected:
            raise ValueError("ingest_manifest.rows are not in UTF-8-bytewise path order")

    def __iter__(self):
        return iter(self.rows)

    @property
    def written(self) -> int:
        return sum(1 for row in self.rows if row.outcome == WRITTEN)

    @property
    def hits(self) -> int:
        return sum(1 for row in self.rows if row.outcome == HIT)

    @property
    def skipped(self) -> int:
        return sum(1 for row in self.rows if row.outcome == SKIPPED)


def _manifest_id(manifest: IngestManifest) -> str:
    """The manifest's own content-addressed id: the sha256 of its codec bytes.

    The id depends on the rows and nothing else, so two runs that saw the same
    files collide on purpose and the store's idempotent ``save`` writes once.
    """
    return sha256_hex(to_json(manifest).encode("utf-8"))


def manifest_store(root: str | Path, *, read_only: bool = False) -> Collection[IngestManifest]:
    """The manifest collection of a store: ``<root>/manifests``, keyed by content."""
    return Collection(
        Path(root) / _MANIFESTS,
        IngestManifest,
        id_of=_manifest_id,
        key_of=_manifest_id,
        read_only=read_only,
    )


def read_manifest(store: Collection[IngestManifest], manifest: IngestManifest) -> IngestManifest | None:
    """The stored copy of ``manifest``, for a caller that wants to compare two runs."""
    return store.find(_manifest_id(manifest))


def _relative(root: Path, path: Path) -> str:
    """The POSIX-normalised path of ``path`` relative to ``root``."""
    return path.relative_to(root).as_posix()


def _scan(root: Path) -> list[tuple[str, bool]]:
    """``(relative path, is_symlinked_directory)`` for everything under ``root``.

    A symlinked directory is reported and **not** descended (policy 2), so the walk
    is finite even over a directory that links to itself. Nothing here follows a
    symlink itself; a symlinked file is reported as a file and read as its target.
    """
    found: list[tuple[str, bool]] = []
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink() and entry.is_dir():
                    found.append((_relative(root, path), True))
                    continue
                if entry.is_dir():
                    pending.append(path)
                    continue
                found.append((_relative(root, path), False))
    return found


def _entries(root: Path, listing: Listing | None) -> list[tuple[str, bool]]:
    """``(relative path, is_symlinked_directory)`` in UTF-8-bytewise path order."""
    if listing is not None:
        found = [(Path(name).as_posix(), False) for name in listing(root)]
    elif root.is_dir():
        found = _scan(root)
    else:
        found = [(_relative(root.parent, root), False)]
    return sorted(found, key=lambda item: item[0].encode("utf-8"))


def _row_for(root: Path, relative: str, store: Collection[DocumentArtifact], *, limits: Limits) -> ManifestRow:
    """One file's manifest row: read it, assemble it, store it (or record why not)."""
    path = root / relative
    try:
        size = path.stat().st_size
    except OSError:
        return ManifestRow(path=relative, container_hash="", outcome=SKIPPED, reason_id=FILE_UNREADABLE)
    if size > limits.max_input_bytes:
        return ManifestRow(path=relative, container_hash="", outcome=SKIPPED, reason_id=FILE_OVER_CAP)
    try:
        raw = path.read_bytes()
    except OSError:
        return ManifestRow(path=relative, container_hash="", outcome=SKIPPED, reason_id=FILE_UNREADABLE)
    decision = parse.parse(raw, limits=limits)
    if decision.error is not None:
        return ManifestRow(
            path=relative, container_hash="", outcome=SKIPPED, reason_id=decision.error.reason_id
        )
    container = EmlContainer(memory_bytes(raw))
    artifact, created = store_document(container, store, limits=limits)
    return ManifestRow(
        path=relative,
        container_hash=artifact.container_hash,
        outcome=WRITTEN if created else HIT,
    )


def ingest_path(
    path_or_dir: str | Path,
    store: Collection[DocumentArtifact],
    *,
    limits: Limits,
    listing: Listing | None = None,
) -> IngestManifest:
    """Ingest one file or one directory tree into ``store`` and return the manifest.

    ``store`` is the document collection (``store.document_store(root)``); the
    manifest itself is written beside it (``manifest_store(store.root.parent)``),
    keyed by its own content, so a re-ingest of unchanged bytes writes nothing at
    all. ``listing`` is the ordering seam: a callable returning relative names, used
    instead of a real directory scan.
    """
    if not isinstance(limits, Limits):
        raise TypeError(f"limits must be a Limits, got {limits!r}")
    root = Path(path_or_dir)
    rows = [
        ManifestRow(path=relative, container_hash="", outcome=SKIPPED, reason_id=SYMLINKED_DIRECTORY)
        if symlinked_directory
        else _row_for(root, relative, store, limits=limits)
        for relative, symlinked_directory in _entries(root, listing)
    ]
    manifest = IngestManifest(
        rows=rows, limits_fingerprint=limits_fingerprint(limits)
    )
    manifest_store(store.root.parent).save(manifest)
    return manifest
