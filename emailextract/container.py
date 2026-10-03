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
from pathlib import Path
from typing import Protocol, runtime_checkable

from .ids import container_hash, sha256_hex
from .model import ContainerKind

__all__ = [
    "Container",
    "EmlContainer",
    "FakeContainer",
    "FileMaterial",
    "MemoryMaterial",
    "PathMaterial",
    "memory_bytes",
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
