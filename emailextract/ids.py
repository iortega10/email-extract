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
    "NOT_BUILT_IN_PHASE0",
    "RawSpan",
    "container_hash",
    "content_hash",
    "part_id",
    "sha256_hex",
    "walk_key",
]

NOT_BUILT_IN_PHASE0: Final[str] = "not_built_in_phase0"
"""The reason id every not-yet-built section carries (D9 tri-state unknowns)."""


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
