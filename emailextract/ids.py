"""Turn 0.2 content-addressed identity (build spec, Turn 0.2; D12).

Identity is content-addressed and positional ids never are: the message id is
the sha256 of the raw container bytes (``container_hash``), and a part is
addressed by ``(container hash, raw byte span, its own content hash)``. The
``1.2.3`` part path is recorded as an explicitly **non-stable locator** only --
it renumbers when a sibling is inserted -- and is never used as identity.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

__all__ = [
    "FILE_OVER_CAP",
    "FILE_UNREADABLE",
    "NOT_BUILT_IN_PHASE0",
    "NOT_BUILT_IN_PHASE1",
    "RawSpan",
    "SPAN_NOT_RESOLVABLE",
    "SYMLINKED_DIRECTORY",
    "container_hash",
    "content_hash",
    "part_id",
    "sha256_hex",
    "walk_key",
]

NOT_BUILT_IN_PHASE0: Final[str] = "not_built_in_phase0"
"""The reason id every not-yet-built section carries (D9 tri-state unknowns)."""

NOT_BUILT_IN_PHASE1: Final[str] = "not_built_in_phase1"
"""The reason id a not-yet-built Phase 1 axis carries, beside ``NOT_BUILT_IN_PHASE0``.

The not-built idiom is exactly one value: ``TriValue(state=UNKNOWN,
reason_id=NOT_BUILT_IN_PHASE1)``. It is never encoded as ``None`` (which keeps its
single meaning: no such axis, or the input did not exercise the field) nor as an
empty list (genuinely empty). A union ``X | NotBuilt`` is forbidden, because the
core codec decodes a union by its first non-``None`` member and would not
round-trip.
"""

SPAN_NOT_RESOLVABLE: Final[str] = "span_not_resolvable"
"""The closed reason a citation is refused (Turn 1.9).

``assemble.resolve_span`` maps a view code-point span back to raw byte offsets
**only** where the part carries a within-part byte map (an identity-decoded,
statically-decodable text part). A flowed (``format=flowed``) part, a part whose
transport decode was not identity and an html-projection part have no such map, so
the citation returns this reason with the part id -- a recorded refusal, never a
guessed byte offset. It is not a gap id and not a status reason.
"""

FILE_UNREADABLE: Final[str] = "file_unreadable"
"""The closed per-file ingest outcome reason: the file could not be read (Turn 1.9).

A permission error, a vanished path or any other ``OSError`` while reading is a
recorded manifest row for that path; the run continues with the next file.
"""

FILE_OVER_CAP: Final[str] = "file_over_cap"
"""The closed per-file ingest outcome reason: the file is over the input cap (Turn 1.9).

The file's size exceeds the caller's ``Limits.max_input_bytes``, so it is never
read or assembled; the run continues with the next file.
"""

SYMLINKED_DIRECTORY: Final[str] = "symlinked_directory"
"""The closed ingest outcome reason: a symlinked directory is never recursed (Turn 1.9).

Directory ingest records the symlink as a skipped row and does not descend it, so
no symlink loop is possible; a symlinked **file** is read as its target.
"""


def sha256_hex(data: bytes) -> str:
    """Lowercase hex sha256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RawSpan:
    """A byte span into the content-addressed raw message: ``[offset, offset + length)``.

    A span is the verbatim layer (D2/D12): whatever it covers is recoverable
    byte-for-byte from the raw message. ``locator`` is the non-stable part path
    this span was measured under (``1.2.3``); it names the measurement, never
    the identity.
    """

    offset: int
    length: int
    locator: str = ""

    def __post_init__(self) -> None:
        for name, value in (("offset", self.offset), ("length", self.length)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"raw_span.{name} must be an int >= 0, got {value!r}")
        if not isinstance(self.locator, str):
            raise ValueError("raw_span.locator must be a str")

    @property
    def end(self) -> int:
        return self.offset + self.length

    def slice(self, raw: bytes) -> bytes:
        """The covered bytes of ``raw``; a span out of range is a defect, never padding."""
        if self.end > len(raw):
            raise ValueError(f"span {self} does not fit raw message of {len(raw)} bytes")
        return raw[self.offset : self.end]


def container_hash(raw: bytes) -> str:
    """The message id: sha256 of the raw container bytes (``container_hash``)."""
    return sha256_hex(raw)


def content_hash(data: bytes) -> str:
    """A part's own content hash: sha256 of its raw span bytes."""
    return sha256_hex(data)


def part_id(container_hash_value: str, span: RawSpan, content_hash_value: str) -> str:
    """The content-addressed id of one part: ``(container hash, raw span, content hash)``.

    All three members are content facts: the same part of the same message always
    gets this id, and no renumbering of the ``1.2.3`` locator can change it.
    """
    if not isinstance(container_hash_value, str) or not container_hash_value:
        raise ValueError("part_id: container_hash must be a non-empty str")
    if not isinstance(content_hash_value, str) or not content_hash_value:
        raise ValueError("part_id: content_hash must be a non-empty str")
    if not isinstance(span, RawSpan):
        raise ValueError(f"part_id: span must be a RawSpan, got {span!r}")
    payload = "\n".join(
        (container_hash_value, str(span.offset), str(span.length), content_hash_value)
    ).encode("utf-8")
    return sha256_hex(payload)


def walk_key(container_hash_value: str, *version_strings: str) -> str:
    """The store key of a walk artifact: the container hash plus the versions that shaped it.

    An artifact is keyed by exactly the inputs its bytes depend on, so re-ingest
    of unchanged input is a lookup, and a version bump is a new key rather than
    an overwrite of a cached shape.
    """
    if not isinstance(container_hash_value, str) or not container_hash_value:
        raise ValueError("walk_key: container_hash must be a non-empty str")
    payload = "\n".join((container_hash_value, *version_strings)).encode("utf-8")
    return sha256_hex(payload)
