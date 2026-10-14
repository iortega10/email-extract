"""Turn 1b.2: a tiny raw-bytes CFB inspector for the tests.

The writer and the reader share an author (build spec rule 3), so the tests read the
fixtures' *bytes* directly at their [MS-CFB] offsets rather than asking any library
what it thinks. This module parses a well-formed container's header, FAT and
directory from raw bytes; it is not the writer (``tools/cfb_writer.py``) and it is
not the oracle (``tests/support/olefile_oracle.py``), and it imports neither
``olefile`` nor ``emailextract``.
"""

from __future__ import annotations

import struct
from typing import Any, Mapping

# [MS-CFB] 2.2/2.3 sentinels.
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF

STGTY_EMPTY = 0
STGTY_STORAGE = 1
STGTY_STREAM = 2
STGTY_ROOT = 5

SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
DIRECTORY_ENTRY_SIZE = 128

HEADER = struct.Struct("<8s16sHHHHHHLLLLLLLLLL")
DIR_ENTRY = struct.Struct("<64sHBBIII16sIQQIII")


def header(data: bytes) -> Mapping[str, Any]:
    """The 512-byte header's fields, at their fixed [MS-CFB] 2.2 offsets."""
    (
        signature,
        _clsid,
        minor,
        dll_version,
        byte_order,
        sector_shift,
        mini_sector_shift,
        _reserved1,
        _reserved2,
        num_dir_sectors,
        num_fat_sectors,
        first_dir_sector,
        _transaction,
        mini_cutoff,
        first_mini_fat_sector,
        num_mini_fat_sectors,
        first_difat_sector,
        num_difat_sectors,
    ) = HEADER.unpack(data[: HEADER.size])
    return {
        "signature": signature,
        "minor_version": minor,
        "dll_version": dll_version,
        "byte_order": byte_order,
        "sector_shift": sector_shift,
        "sector_size": 1 << sector_shift,
        "mini_sector_shift": mini_sector_shift,
        "mini_sector_size": 1 << mini_sector_shift,
        "num_dir_sectors": num_dir_sectors,
        "num_fat_sectors": num_fat_sectors,
        "first_dir_sector": first_dir_sector,
        "mini_cutoff": mini_cutoff,
        "first_mini_fat_sector": first_mini_fat_sector,
        "num_mini_fat_sectors": num_mini_fat_sectors,
        "first_difat_sector": first_difat_sector,
        "num_difat_sectors": num_difat_sectors,
        "difat": list(struct.unpack_from("<109L", data, 76)),
    }


def sector(data: bytes, size: int, index: int) -> bytes:
    """The bytes of sector ``index`` (sector 0 is the first sector after the header)."""
    return data[(index + 1) * size : (index + 2) * size]


def fat(data: bytes, fields: Mapping[str, Any]) -> list[int]:
    """The FAT: the header DIFAT's FAT sectors, concatenated, cut to the sector count."""
    size = fields["sector_size"]
    slots = size // 4
    values: list[int] = []
    for index in fields["difat"]:
        if index in (FREESECT, ENDOFCHAIN):
            break
        values.extend(struct.unpack("<%dL" % slots, sector(data, size, index)))
    return values[: len(data) // size - 1]


def chain(fat_table: list[int], start: int) -> list[int]:
    """The sectors of a chain starting at ``start`` (stop at ENDOFCHAIN/FREESECT)."""
    sectors: list[int] = []
    seen: set[int] = set()
    while start not in (ENDOFCHAIN, FREESECT):
        if start in seen or start >= len(fat_table):
            break
        seen.add(start)
        sectors.append(start)
        start = fat_table[start]
    return sectors


def directory(data: bytes, fields: Mapping[str, Any], fat_table: list[int]) -> list[Mapping[str, Any]]:
    """Every 128-byte directory entry, in directory-id order."""
    size = fields["sector_size"]
    entries: list[Mapping[str, Any]] = []
    for index in chain(fat_table, fields["first_dir_sector"]):
        block = sector(data, size, index)
        for offset in range(0, size, DIRECTORY_ENTRY_SIZE):
            (
                name_raw,
                name_length,
                entry_type,
                colour,
                left,
                right,
                child,
                _clsid,
                _state,
                _created,
                _modified,
                start,
                size_low,
                size_high,
            ) = DIR_ENTRY.unpack(block[offset : offset + DIRECTORY_ENTRY_SIZE])
            entries.append(
                {
                    "name": name_raw[: max(name_length - 2, 0)].decode("utf-16-le"),
                    "name_length": name_length,
                    "type": entry_type,
                    "colour": colour,
                    "left": left,
                    "right": right,
                    "child": child,
                    "start": start,
                    "size": size_low + (size_high << 32),
                }
            )
    return entries


def patch_u32(data: bytes, offset: int, value: int) -> bytes:
    """A copy of ``data`` with the little-endian 32-bit word at ``offset`` replaced."""
    patched = bytearray(data)
    struct.pack_into("<L", patched, offset, value & 0xFFFFFFFF)
    return bytes(patched)
