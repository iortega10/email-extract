"""Turn 1b.8: the test-side LZFu compressor for ``0x1009`` streams.

The decoder lives in :mod:`emailextract.rtf`. This module is the other side of the
comparison (build spec rule 5): it is written *independently of the decoder's logic*, so a
round-trip proves two implementations agree rather than one agreeing with itself. It
imports the standard library only for its work, and -- since the 1b.8 fix -- it **imports
the two format constants from exactly one place**, :mod:`emailextract.rtf` (:data:`PREBUF`
and :func:`crc32`), instead of typing a second, silently-diverging copy. Bundling a wrong
copy on both sides is what let the first Turn 1b.8 land a wrong prebuf and a wrong CRC and
still pass every round trip; the two **real** vectors in ``tests/test_msg_rtf.py`` (from a
public, independent implementation, asserted against :func:`emailextract.rtf.decode` alone)
are now the external check that pins those constants.

The format ([MS-OXRTFCP] 2.1), typed here:

* a 16-byte header of four little-endian ``u32``s -- ``COMPSIZE`` (the stream length
  after the first field, i.e. ``stream_length - 4``), ``RAWSIZE`` (the decompressed
  length), ``COMPTYPE`` (``LZFu`` = ``0x75465A4C`` compressed, ``MELA`` = ``0x414C454D``
  uncompressed), ``CRC`` (the raw-table CRC-32 of bytes after the header; ``0`` for
  ``MELA``);
* ``LZFu`` data: a control byte of eight flags (LSB first) -- a clear flag is one literal
  byte, a set flag is a 2-byte big-endian reference (12-bit dictionary offset, 4-bit
  stored length = length - 2), and a reference whose offset equals the current write
  position is the end marker;
* the 4096-byte circular dictionary is pre-loaded with :data:`PREBUF` at the initial
  write position.

Two encoders: :func:`compress_literal` (literals only -- the deterministic small form the
committed fixtures use) and :func:`compress_greedy` (a plain longest-match encoder, for
the round-trip fuzz). :func:`mela` is the uncompressed form.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from emailextract.rtf import (  # noqa: E402  (the one place the constants live)
    CN_COMPRESSED,
    CN_UNCOMPRESSED,
    CRC32_TABLE,
    DICTIONARY_SIZE,
    HEADER_SIZE,
    INITIAL_WRITE_POSITION,
    PREBUF,
    crc32,
)

LZFU = CN_COMPRESSED
MELA = CN_UNCOMPRESSED
MAX_REFERENCE_LENGTH = 17
MIN_REFERENCE_LENGTH = 2

__all__ = [
    "CRC32_TABLE",
    "DICTIONARY_SIZE",
    "HEADER_SIZE",
    "INITIAL_WRITE_POSITION",
    "LZFU",
    "MELA",
    "PREBUF",
    "compress_greedy",
    "compress_literal",
    "crc32",
    "mela",
]


# ------------------------------------------------------------------- the encoders

def _header(rawsize: int, payload: bytes) -> bytes:
    """The 16-byte header over ``payload`` (``COMPSIZE`` counts from after its own field)."""
    return struct.pack(
        "<IIII", 12 + len(payload), rawsize, LZFU, crc32(bytes(payload))
    ) + bytes(payload)


class _Flags:
    """One control byte's eight LSB-first flags, emitted lazily before each item."""

    def __init__(self) -> None:
        self.payload = bytearray()
        self.control: "int | None" = None
        self.bits = 0
        self.used = 0

    def _room(self) -> None:
        if self.used == 8:
            self._close()
        if self.control is None:
            self.control = len(self.payload)
            self.payload.append(0)

    def _close(self) -> None:
        if self.control is not None:
            self.payload[self.control] = self.bits
        self.control = None
        self.bits = 0
        self.used = 0

    def literal(self, byte: int) -> None:
        self._room()
        self.used += 1
        self.payload.append(byte)

    def reference(self, offset: int, length: int) -> None:
        self._room()
        self.bits |= 1 << self.used
        self.used += 1
        reference = ((offset << 4) | (length - 2)) & 0xFFFF
        self.payload.append((reference >> 8) & 0xFF)
        self.payload.append(reference & 0xFF)

    def finish(self, write_pos: int) -> bytes:
        """Close the stream with the end marker (offset == the current write position).

        The marker takes the current control byte's next free flag when there is one (the
        flags after it are never read); a full control byte starts a fresh one.
        """
        if self.used == 8:
            self._close()
        if self.control is None:
            self.control = len(self.payload)
            self.payload.append(0)
        self.bits |= 1 << self.used
        self.used += 1
        marker = ((write_pos % DICTIONARY_SIZE) << 4) & 0xFFFF
        self.payload.append((marker >> 8) & 0xFF)
        self.payload.append(marker & 0xFF)
        self.payload[self.control] = self.bits
        return bytes(self.payload)


def compress_literal(text: bytes) -> bytes:
    """A literal-only ``LZFu`` stream: deterministic and cheap to hand-derive."""
    text = bytes(text)
    flags = _Flags()
    for byte in text:
        flags.literal(byte)
    payload = flags.finish(INITIAL_WRITE_POSITION + len(text))
    return _header(len(text), payload)


def compress_greedy(text: bytes) -> bytes:
    """A simple longest-match ``LZFu`` encoder (matches never overlap their own write)."""
    text = bytes(text)
    flags = _Flags()
    history = bytearray(PREBUF)
    position = 0
    length = len(text)
    while position < length:
        best_length = 0
        best_offset = 0
        window_start = max(0, len(history) - DICTIONARY_SIZE)
        cap = min(MAX_REFERENCE_LENGTH, length - position)
        if cap >= MIN_REFERENCE_LENGTH:
            here = len(history) % DICTIONARY_SIZE
            for start in range(window_start, len(history)):
                if start % DICTIONARY_SIZE == here:
                    # Reading the slot the next byte will be written to is the end marker's
                    # meaning, never a reference (the format's own ambiguity).
                    continue
                limit = min(cap, len(history) - start)
                run = 0
                while run < limit and history[start + run] == text[position + run]:
                    run += 1
                if run > best_length:
                    best_length = run
                    best_offset = start % DICTIONARY_SIZE
                    if best_length == cap:
                        break
        if best_length >= MIN_REFERENCE_LENGTH:
            flags.reference(best_offset, best_length)
            history += text[position : position + best_length]
            position += best_length
        else:
            flags.literal(text[position])
            history.append(text[position])
            position += 1
    payload = flags.finish(INITIAL_WRITE_POSITION + length)
    return _header(length, payload)


def mela(text: bytes) -> bytes:
    """An uncompressed ``MELA`` stream (``CRC`` is ``0``)."""
    text = bytes(text)
    return struct.pack("<IIII", 12 + len(text), len(text), MELA, 0) + text
