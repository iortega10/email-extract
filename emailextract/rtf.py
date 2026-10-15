"""Turn 1b.8: the ``0x1009`` (compressed RTF) decompress-and-record minimum.

Owner decision **O2** cut RTF *de-encapsulation*; what stays is this: the reader
decompresses a ``0x1009`` stream (``LZFu`` compressed, ``MELA`` uncompressed), checks it,
and **records what it found**. It produces **no body view**: ``BodyView`` is
``HTML``/``PLAIN`` only, and a view derived from RTF labelled either would be the
mislabelled digest D14 forbids. There is no RTF-to-text, no ``\\fromhtml``/``\\fromtext``
interpretation, no code-page reading from the RTF header: the decompressed bytes are
checked, hashed and counted, never read as RTF.

The format ([MS-OXRTFCP] 2.1), typed from the specification:

* a 16-byte header of four little-endian ``u32``s -- ``COMPSIZE`` (the size of the stream
  **after** this first field, i.e. ``stream_length - 4``), ``RAWSIZE`` (the decompressed
  length), ``COMPTYPE`` (``LZFu`` = ``0x75465A4C`` compressed, ``MELA`` = ``0x414C454D``
  uncompressed), ``CRC`` (for ``LZFu`` the :func:`crc32` of the compressed bytes after the
  header; for ``MELA`` the specification says ``0``, but the format's own reference writer
  stores the payload's :func:`crc32` -- both are accepted);
* ``LZFu`` data: a 4096-byte circular dictionary pre-loaded with :data:`PREBUF` (207 bytes)
  at the specification's initial write position; a control byte of eight flags (LSB first),
  a clear flag meaning one literal byte, a set flag meaning a 2-byte big-endian reference of
  a 12-bit dictionary offset and a 4-bit stored length (length minus 2); a reference whose
  offset equals the current write position is the **end marker**.

The two constants that Turn 1b.8 first guessed at are now pinned against real vectors from
a public, independent implementation (``delimitry/compressed_rtf``, its ``INIT_DICT`` and
README examples): :data:`PREBUF` is the 207-byte pre-load, and :func:`crc32` is the plain
table-driven CRC-32 with polynomial ``0xEDB88320``, **initial value 0 and no final XOR**
over the bytes after the header -- *not* :func:`zlib.crc32` (which uses an initial
``0xFFFFFFFF`` and a final XOR, and yields a different number). Two real streams decode
byte for byte under these constants (``tests/test_msg_rtf.py``).

The decoder is streaming and keeps nothing it does not need: the 4096-byte dictionary, a
running :func:`hashlib.sha256` and the running length. Output is never retained. It never
raises; a malformed stream is a recorded fault, never a repaired string. Work is charged
per output byte (:data:`WORK_UNITS_PER_OUTPUT_BYTE`) through the container's ``Work``
counter, bounded by :func:`work_bound`.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Final

__all__ = [
    "CN_COMPRESSED",
    "CN_UNCOMPRESSED",
    "DICTIONARY_SIZE",
    "FAULTS",
    "FAULT_COMPTYPE_UNKNOWN",
    "FAULT_COMPSIZE_MISMATCH",
    "FAULT_CRC_MISMATCH",
    "FAULT_DATA_SHORT",
    "FAULT_DICTIONARY_UNDERRUN",
    "FAULT_HEADER_SHORT",
    "FAULT_RAWSIZE_MISMATCH",
    "HEADER_SIZE",
    "INITIAL_WRITE_POSITION",
    "MAX_EXPANSION",
    "PREBUF",
    "RtfResult",
    "crc32",
    "decode",
    "work_bound",
]

HEADER_SIZE = 16
DICTIONARY_SIZE = 4096
#: ``COMPTYPE`` ``"LZFu"`` (compressed) and ``"MELA"`` (uncompressed) as little-endian u32.
CN_COMPRESSED = 0x75465A4C
CN_UNCOMPRESSED = 0x414C454D
_CN_BY_VALUE = {CN_COMPRESSED: "LZFu", CN_UNCOMPRESSED: "MELA"}
MIN_REFERENCE_LENGTH = 2
MAX_REFERENCE_LENGTH = 17
#: One 2-byte reference expands to at most 17 output bytes, so the whole stream stays under
#: this multiple of the compressed data (the brief's "~9x").
MAX_EXPANSION = 9
#: The hash buffer holds at most this many bytes, so no output is ever retained whole.
_HASH_CHUNK = 65536
#: :func:`work_bound` charges one step per output byte.
WORK_UNITS_PER_OUTPUT_BYTE = 1

#: [MS-OXRTFCP] 2.1's 207-byte dictionary pre-load, *verbatim* -- the ``INIT_DICT`` of the
#: public ``delimitry/compressed_rtf`` reference and the specification's own 207 bytes (the
#: ``<CR><LF>`` is a real CR LF pair). Its length is the initial write position. Verified
#: byte for byte against two real streams in ``tests/test_msg_rtf.py``.
PREBUF = (
    b"{\\rtf1\\ansi\\mac\\deff0\\deftab720{\\fonttbl;}{\\f0\\fnil "
    b"\\froman \\fswiss \\fmodern \\fscript \\fdecor MS Sans SerifSymbolArialTimes New RomanCourier"
    b"{\\colortbl\\red0\\green0\\blue0\r\n\\par \\pard\\plain\\f0\\fs20\\b\\i\\u\\tab\\tx"
)
INITIAL_WRITE_POSITION = len(PREBUF)


def _build_crc32_table() -> tuple[int, ...]:
    """The reflected CRC-32 table (polynomial ``0xEDB88320``), built once at import."""
    table: list[int] = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        table.append(value & 0xFFFFFFFF)
    return tuple(table)


#: The specification's table-driven CRC-32 table (256 entries, bounded, stdlib-only).
CRC32_TABLE: Final[tuple[int, ...]] = _build_crc32_table()


def crc32(data: "bytes | memoryview") -> int:
    """[MS-OXRTFCP]'s CRC-32: initial value ``0`` and **no final XOR** (not :func:`zlib.crc32`).

    ``crc = 0; for byte in data: crc = TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)``.
    """
    crc = 0
    for byte in data:
        crc = CRC32_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc & 0xFFFFFFFF


#: The closed fault list (D5). Every one maps to the existing ``msg.stream_truncated`` gap,
#: its detail ``0x1009:<fault>``, and a document ``Status`` of ``TRUNCATED``.
FAULT_HEADER_SHORT = "rtf_header_short"
FAULT_COMPTYPE_UNKNOWN = "rtf_comptype_unknown"
FAULT_COMPSIZE_MISMATCH = "rtf_compsize_mismatch"
FAULT_RAWSIZE_MISMATCH = "rtf_rawsize_mismatch"
FAULT_CRC_MISMATCH = "rtf_crc_mismatch"
FAULT_DATA_SHORT = "rtf_data_short"
FAULT_DICTIONARY_UNDERRUN = "rtf_dictionary_underrun"
FAULTS: Final[tuple[str, ...]] = (
    FAULT_HEADER_SHORT,
    FAULT_COMPTYPE_UNKNOWN,
    FAULT_COMPSIZE_MISMATCH,
    FAULT_RAWSIZE_MISMATCH,
    FAULT_CRC_MISMATCH,
    FAULT_DATA_SHORT,
    FAULT_DICTIONARY_UNDERRUN,
)


@dataclass(frozen=True)
class RtfResult:
    """What a ``0x1009`` stream was found to be -- plain data, never the RTF text (D3).

    ``comptype`` is ``"LZFu"``, ``"MELA"`` or the raw ``u32`` as 8-digit lowercase hex when
    unknown (``None`` for a stream too short to have one). ``decompressed_sha256`` is
    ``None`` whenever ``fault`` is set; ``decompressed_length`` is the number of output
    bytes produced before a fault (0 for a structural fault) or the whole length on
    success. ``crc_ok`` is ``None`` when no CRC could be checked. ``crc_kind`` records
    **which** CRC form was accepted (plain data, D3): ``"zero"`` for a ``MELA`` stream whose
    field is ``0``, ``"payload"`` when the field equalled :func:`crc32` of the payload (an
    ``LZFu`` stream, or the reference writer's ``MELA`` form), and ``"none"`` when no CRC
    was checked or the check failed.
    """

    comptype: "str | None"
    stream_length: int
    compsize_declared: "int | None"
    rawsize_declared: "int | None"
    crc_declared: "int | None"
    crc_ok: "bool | None"
    crc_kind: "str | None"
    decompressed_length: "int | None"
    decompressed_sha256: "str | None"
    fault: "str | None"


def work_bound(stream_length: int) -> int:
    """The most work :func:`decode` may charge for a stream this long (D4's declared bound)."""
    return HEADER_SIZE + MAX_EXPANSION * stream_length


def decode(data: bytes, *, work: "object | None" = None) -> RtfResult:
    """Decompress and check one ``0x1009`` stream, returning a frozen record (never raises).

    ``work`` is the container's ``Work`` counter (the ``cfb``/``mapi`` pattern); one step is
    charged per output byte, so a hostile stream hits :func:`work_bound` and not the clock.
    """
    stream_length = len(data)
    if stream_length < HEADER_SIZE:
        return RtfResult(
            None, stream_length, None, None, None, None, None, None, None, FAULT_HEADER_SHORT
        )

    compsize, rawsize, comptype_raw, crc = struct.unpack_from("<IIII", data, 0)
    comptype = _CN_BY_VALUE.get(comptype_raw)
    if comptype is None:
        return RtfResult(
            f"{comptype_raw:08x}", stream_length, compsize, rawsize, crc, None, "none", 0, None,
            FAULT_COMPTYPE_UNKNOWN,
        )
    if compsize != stream_length - 4:
        return RtfResult(
            comptype, stream_length, compsize, rawsize, crc, None, "none", 0, None,
            FAULT_COMPSIZE_MISMATCH,
        )

    payload = memoryview(data)[HEADER_SIZE:]
    if comptype == "MELA":
        return _decode_mela(payload, rawsize, compsize, stream_length, crc, work)
    return _decode_lzfu(payload, rawsize, compsize, stream_length, crc, work)


def _decode_mela(
    payload: "memoryview", rawsize: int, compsize: int, stream_length: int, crc: int, work: "object | None"
) -> RtfResult:
    """``MELA``: the sizes must agree and ``CRC`` is either ``0`` or the payload's :func:`crc32`.

    [MS-OXRTFCP] says an uncompressed stream's CRC is ``0``, but the format's own reference
    writer stores the payload's :func:`crc32`; both are accepted (``crc_kind`` records
    which). Any other value is :data:`FAULT_CRC_MISMATCH` (owner question, Turn 1b.8).
    """
    if crc == 0:
        crc_kind = "zero"
    elif crc == crc32(payload):
        crc_kind = "payload"
    else:
        return RtfResult(
            "MELA", stream_length, compsize, rawsize, crc, False, "none", 0, None,
            FAULT_CRC_MISMATCH,
        )
    if len(payload) != rawsize:
        return RtfResult(
            "MELA", stream_length, compsize, rawsize, crc, True, crc_kind, len(payload), None,
            FAULT_RAWSIZE_MISMATCH,
        )
    if work is not None:
        work.tick(WORK_UNITS_PER_OUTPUT_BYTE * len(payload))
    return RtfResult(
        "MELA", stream_length, compsize, rawsize, crc, True, crc_kind, len(payload),
        hashlib.sha256(payload).hexdigest(), None,
    )


def _decode_lzfu(
    payload: "memoryview", rawsize: int, compsize: int, stream_length: int, crc: int, work: "object | None"
) -> RtfResult:
    """The ``LZFu`` decompression: streaming, bounded by ``rawsize``, never raising."""
    crc_ok = crc32(payload) == crc
    if not crc_ok:
        return RtfResult(
            "LZFu", stream_length, compsize, rawsize, crc, False, "none", 0, None,
            FAULT_CRC_MISMATCH,
        )

    dictionary = bytearray(DICTIONARY_SIZE)
    dictionary[: len(PREBUF)] = PREBUF
    write_pos = INITIAL_WRITE_POSITION
    hasher = hashlib.sha256()
    buffer = bytearray()
    produced = 0
    total = len(payload)
    index = 0

    def flush() -> None:
        if buffer:
            hasher.update(buffer)
            buffer.clear()

    def fault(name: str) -> RtfResult:
        return RtfResult(
            "LZFu", stream_length, compsize, rawsize, crc, True, "payload", produced, None, name
        )

    while index < total:
        control = payload[index]
        index += 1
        if control == 0x00:
            # A fast path for eight literals: the committed fixtures are literal-only.
            if index + 8 > total:
                return fault(FAULT_DATA_SHORT)
            if produced + 8 > rawsize:
                return fault(FAULT_RAWSIZE_MISMATCH)
            run = payload[index : index + 8]
            index += 8
            if write_pos + 8 <= DICTIONARY_SIZE:
                dictionary[write_pos : write_pos + 8] = run
                write_pos += 8
            else:
                for byte in run:
                    dictionary[write_pos % DICTIONARY_SIZE] = byte
                    write_pos += 1
            buffer += run
            produced += 8
            if len(buffer) >= _HASH_CHUNK:
                flush()
            if work is not None:
                work.tick(WORK_UNITS_PER_OUTPUT_BYTE * 8)
            continue

        for bit in range(8):
            if not control & (1 << bit):
                if index >= total:
                    return fault(FAULT_DATA_SHORT)
                if produced >= rawsize:
                    return fault(FAULT_RAWSIZE_MISMATCH)
                byte = payload[index]
                index += 1
                dictionary[write_pos % DICTIONARY_SIZE] = byte
                write_pos += 1
                buffer.append(byte)
                produced += 1
                if len(buffer) >= _HASH_CHUNK:
                    flush()
                if work is not None:
                    work.tick(WORK_UNITS_PER_OUTPUT_BYTE)
                continue

            if index + 1 >= total:
                return fault(FAULT_DATA_SHORT)
            reference = (payload[index] << 8) | payload[index + 1]
            index += 2
            offset = reference >> 4
            length = (reference & 0x0F) + 2
            if offset == write_pos % DICTIONARY_SIZE:
                # The end marker: the stream stops here and the length must match RAWSIZE.
                if produced != rawsize:
                    return fault(FAULT_RAWSIZE_MISMATCH)
                flush()
                return RtfResult(
                    "LZFu", stream_length, compsize, rawsize, crc, True, "payload", produced,
                    hasher.hexdigest(), None,
                )
            for position in range(length):
                slot = (offset + position) % DICTIONARY_SIZE
                if write_pos < DICTIONARY_SIZE and slot >= write_pos:
                    # A byte that has not yet been written: never a guessed fill byte (D4).
                    return fault(FAULT_DICTIONARY_UNDERRUN)
                if produced >= rawsize:
                    return fault(FAULT_RAWSIZE_MISMATCH)
                byte = dictionary[slot]
                dictionary[write_pos % DICTIONARY_SIZE] = byte
                write_pos += 1
                buffer.append(byte)
                produced += 1
                if len(buffer) >= _HASH_CHUNK:
                    flush()
                if work is not None:
                    work.tick(WORK_UNITS_PER_OUTPUT_BYTE)

    # The input ended without the end marker.
    return fault(FAULT_DATA_SHORT)
