"""Turn 0.2 container layer: the container-neutral interface, the ``.eml``
adapter and an in-memory FAKE (build spec, Turn 0.2; D13/D14).

The walker (``emailextract.walk``) measures spans over whatever ``Container`` it
is handed; nothing in it knows a file path, a CFB sector or an ``.eml`` suffix.
Phase 0 must not depend on the hardest component (D13), so the ``cfb_msg`` route
is exercised by :class:`FakeContainer` -- a fixture double built from hand-made
bytes in memory -- and never by reading a CFB file. ``olefile`` is not imported
here and not needed to import this package.

Input arrives as a *FileMaterial* (``size()`` / ``open_text()`` / ``read_bytes()``)
or as the two shapes tests exercise it through: a :class:`pathlib.Path` and
:func:`memory_bytes`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .ids import container_hash, sha256_hex
from .model import (
    ContainerKind,
    ContainerStreamAxis,
    ContainerStreamRef,
    EncodingSource,
)

__all__ = [
    "CharsetOrigin",
    "Container",
    "EmlContainer",
    "FakeContainer",
    "FileMaterial",
    "MemoryMaterial",
    "PathMaterial",
    "PersistedSpanRow",
    "SpanRow",
    "memory_bytes",
    "source_key_of",
    "span_lookup",
    "stream_ref_of",
]


@runtime_checkable
class FileMaterial(Protocol):
    """The input protocol: a file's bytes, never its meaning."""

    def size(self) -> int: ...

    def open_text(self) -> io.TextIOBase: ...

    def read_bytes(self) -> bytes: ...


class PathMaterial:
    """A file on disk, read as bytes; the text view decodes UTF-8 strictly."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def size(self) -> int:
        return self.path.stat().st_size

    def open_text(self) -> io.TextIOBase:
        return self.path.open("r", encoding="utf-8", newline="")

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


class MemoryMaterial:
    """Bytes held in memory -- the second route every input test also takes."""

    def __init__(self, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError(f"memory material takes bytes, got {type(data).__name__}")
        self._data = data

    def size(self) -> int:
        return len(self._data)

    def open_text(self) -> io.TextIOBase:
        return io.StringIO(self._data.decode("utf-8"))

    def read_bytes(self) -> bytes:
        return self._data


def memory_bytes(data: bytes) -> MemoryMaterial:
    """The in-memory FileMaterial, named the way tests call it."""
    return MemoryMaterial(data)


def _material_of(source: FileMaterial | Path | str | bytes) -> FileMaterial:
    if isinstance(source, bytes):
        return memory_bytes(source)
    if isinstance(source, (str, Path)):
        return PathMaterial(source)
    if not isinstance(source, FileMaterial):
        raise TypeError(f"not a FileMaterial, Path or bytes: {type(source).__name__}")
    return source


@runtime_checkable
class Container(Protocol):
    """What the walker measures: raw bytes, their hash and what opened them.

    ``container_hash()`` is the message id (D14: it addresses the *file*);
    ``raw_bytes()`` is the address space every recorded span points into. The
    container states its ``kind``; the walker reports it and never invents one.
    """

    kind: ContainerKind

    def container_hash(self) -> str: ...

    def raw_bytes(self) -> bytes: ...

    def container_facts(self) -> dict[str, str]: ...


class EmlContainer:
    """The ``.eml`` adapter: one RFC 822 byte string, hashed and served.

    ``container_kind`` is ``rfc822`` and ``raw_bytes()`` is the file verbatim --
    spans measured against it are verbatim spans (D12).
    """

    kind = ContainerKind.RFC822

    def __init__(self, source: FileMaterial | Path | str | bytes) -> None:
        self._material = _material_of(source)

    def container_hash(self) -> str:
        return container_hash(self.raw_bytes())

    def raw_bytes(self) -> bytes:
        return self._material.read_bytes()

    def container_facts(self) -> dict[str, str]:
        raw = self.raw_bytes()
        return {
            "adapter": "eml",
            "material": type(self._material).__name__,
            "size_bytes": str(len(raw)),
            "raw_sha256": sha256_hex(raw),
        }


class FakeContainer:
    """The in-memory FAKE: the second ``container_kind``, exercised with zero CFB code.

    A fixture double, hand-built by a test or a tool -- **nothing in the package
    constructs one from a file**, and it is not a parsed ``.msg``: its bytes are
    whatever the caller supplies and the walker measures them exactly as
    measured input (the honesty rule: a field is reported only for bytes that
    were read). It exists so the walker's ``cfb_msg`` route can be exercised
    before the Phase 1b reader exists (D13), and its facts say ``synthetic`` so
    no consumer mistakes it for a real container.
    """

    def __init__(
        self,
        raw: bytes,
        *,
        kind: ContainerKind = ContainerKind.CFB_MSG,
        facts: dict[str, str] | None = None,
    ) -> None:
        if not isinstance(kind, ContainerKind):
            raise TypeError(f"kind must be a ContainerKind, got {kind!r}")
        self.kind = kind
        self._raw = memory_bytes(raw)
        self._facts = {"adapter": "fake", "synthetic": "in_memory"}
        if facts:
            self._facts.update(facts)

    def container_hash(self) -> str:
        return container_hash(self.raw_bytes())

    def raw_bytes(self) -> bytes:
        return self._raw.read_bytes()

    def container_facts(self) -> dict[str, str]:
        return dict(self._facts)


# --------------------------------------------------------------------------
# Turn 1b.1: the span table (producer-internal), the source key, the record ref
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SpanRow:
    """One virtual region's provenance (contract section 7).

    Producer-internal: not a member of the ``Container`` Protocol, so ``EmlContainer``
    and ``FakeContainer`` stay valid. A container that projects a ``.msg`` publishes a
    ``tuple[SpanRow, ...]`` through ``getattr(container, "span_provenance", None)``.
    ``virtual_offset``/``virtual_len`` never leave the producer: no record and no citation
    carries them (C2). ``source_stream`` holds the CFB stream name for a ``STREAM``/
    ``REENCODED`` row and the synthetic label ``synthetic:<role>:<ordinal>`` for a
    ``SYNTHETIC`` row (the label is the only source identity a synthetic region has, and
    it is what :func:`source_key_of` and :func:`stream_ref_of` read).
    """

    axis: ContainerStreamAxis
    source_stream: str | None
    source_byte_offset: int | None
    source_byte_len: int | None
    source_sha256: str | None
    virtual_offset: int
    virtual_len: int
    decoded_char_offset: int | None = None
    decoded_char_len: int | None = None
    exact: bool = False


@dataclass(frozen=True)
class PersistedSpanRow:
    """The stored span row: source-only, no virtual framing (contract section 7).

    C2: a persisted virtual offset would make the stored bytes depend on the projection's
    framing length. The virtual offsets are recomputed deterministically from the CFB bytes
    and ``MSG_PROJECTION_VERSION`` whenever they are needed, so nothing is lost.
    """

    axis: ContainerStreamAxis
    source_stream: str | None
    source_byte_offset: int | None
    source_byte_len: int | None
    source_sha256: str | None
    decoded_char_offset: int | None
    decoded_char_len: int | None
    exact: bool

    @classmethod
    def of(cls, row: SpanRow) -> "PersistedSpanRow":
        """The source-only projection of a :class:`SpanRow` (drops ``virtual_*``)."""
        return cls(
            axis=row.axis,
            source_stream=row.source_stream,
            source_byte_offset=row.source_byte_offset,
            source_byte_len=row.source_byte_len,
            source_sha256=row.source_sha256,
            decoded_char_offset=row.decoded_char_offset,
            decoded_char_len=row.decoded_char_len,
            exact=row.exact,
        )


@dataclass(frozen=True)
class CharsetOrigin:
    """One part's authoritatively-known charset provenance (point 5).

    A ``.msg`` projection's virtual bytes carry a charset the walker's ladder reads, but
    the real character set of a MAPI string is a property of the message (``internet_cpid``
    / ``message_cpid`` / the ``001E`` vs ``001F`` stream), which only the reader knows. A
    container that knows it publishes ``getattr(container, "charset_sources", None)`` as a
    ``Mapping[part_path, CharsetOrigin]``; the assembler overwrites the ``PartRecord``'s
    ``encoding_source`` and decode-chain charset fields from it, so the record never claims
    a ladder rung the walker guessed from virtual bytes.
    """

    used_charset: str | None
    declared_charset: str | None
    encoding_source: "EncodingSource | None" = None


def source_key_of(row: SpanRow) -> str:
    """The framing-length-independent key of one span row (point 2).

    ``<stream>:<byte_offset>:<byte_len>`` for a pass-through or re-encoded region, the
    synthetic label verbatim for a ``SYNTHETIC`` row. It names the part by its **source**
    (the CFB stream and the range of it), never by a virtual offset.
    """
    if row.axis is ContainerStreamAxis.SYNTHETIC:
        return row.source_stream or ""
    return f"{row.source_stream}:{row.source_byte_offset}:{row.source_byte_len}"


def stream_ref_of(row: SpanRow) -> ContainerStreamRef:
    """The :class:`ContainerStreamRef` one span row records (points 1, 3).

    A synthetic row yields the no-offset ref; a pass-through / re-encoded row yields the
    source range in the stream's own encoding. ``fault`` is ``None``: the fine-grained CFB
    chain fault rides the span row's own account, not this record.
    """
    if row.axis is ContainerStreamAxis.SYNTHETIC:
        return ContainerStreamRef(stream=row.source_stream or "synthetic:unknown:0", axis=row.axis)
    return ContainerStreamRef(
        stream=row.source_stream or "",
        byte_offset=row.source_byte_offset,
        byte_len=row.source_byte_len,
        axis=row.axis,
    )


def span_lookup(container: object) -> dict[tuple[int, int], SpanRow] | None:
    """``{(virtual_offset, virtual_len): SpanRow}`` for a span-table container, else ``None``.

    ``None`` for every ``.eml`` container (and every container that publishes no
    ``span_provenance``): that is the signal every gated provenance point keys on, so the
    ``.eml`` path takes its current expression unchanged.
    """
    rows = getattr(container, "span_provenance", None)
    if not rows:
        return None
    return {(row.virtual_offset, row.virtual_len): row for row in rows}
