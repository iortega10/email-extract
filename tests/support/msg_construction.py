"""Turn 1b.2/1b.3: the hand-typed construction tables for the ``.msg`` fixtures.

A construction table is the *independent* side of the writer/reader comparison
(build spec rule 5): every number here was typed from [MS-CFB], from the observed
Outlook structure (`docs/design/email-spike.md` B1-B4) or from the fixture's
description in ``docs/design/phase1b-fixtures.md`` -- never read out of the writer's
output or an oracle's reading. If the writer and this table disagree, the
disagreement is the finding; the table is not edited to match.

Shape, per fixture:

* header fields as ``tests/test_msg_fixtures.py`` reads them at their [MS-CFB] 2.2
  offsets: version, sector size and shift, mini sector shift, mini cutoff, the FAT /
  directory / mini-FAT / DIFAT sector counts and first indices;
* ``file_length`` and ``sector_count`` (every sector-sized region, the header
  included) and ``directory_entries`` (the 128-byte entry slots the directory stream
  holds, i.e. ``directory_sectors * sector_size // 128``);
* ``sector_accounting`` -- the eight classes in the fixed order
  ``header, difat, fat, minifat, directory, stream, free, slack``, whose byte counts
  sum to ``file_length``;
* ``directory`` -- ``(name, object type, stream size)`` for every real entry, in
  directory-id order (the writer's pre-order assignment, children in declaration
  order);
* ``streams`` -- per stream name: whether it lives in the mini stream (``mini``,
  size strictly below the cutoff), its first sector / mini sector (``start``), its
  byte ``size`` and the number of sectors in its chain (``sectors``); plus the root
  entry's mini stream under ``"<root>"``.

Turn 1b.3 adds two things. ``MSG_DIFAT_EXTENDED`` is a sixth **well-formed** table
(the file ``msg_difat_extended``, whose FAT is reached through an extended DIFAT
chain). ``HOSTILE_EXPECTATIONS`` is the other kind of row: the three **hostile**
fixtures (``msg_fat_cycle``, ``msg_directory_loop``, ``msg_truncated_stream``) are
the base's bytes with one 32-bit word patched, so they have no construction table --
what they must do (open with a faulted stream, or refuse with a named reason) is typed
here instead.
"""

from __future__ import annotations

from typing import Any, Mapping

STGTY_STORAGE = 1
STGTY_STREAM = 2
STGTY_ROOT = 5

#: The eight sector classes, in the fixed order (``msg.sector_accounting``).
SECTOR_CLASSES = ("header", "difat", "fat", "minifat", "directory", "stream", "free", "slack")


def _accounting(
    header: int, fat: int, minifat: int, directory: int, stream: int
) -> list[list[Any]]:
    """The eight-class rows; ``difat``, ``free`` and ``slack`` are typed where used."""
    values = {
        "header": header,
        "difat": 0,
        "fat": fat,
        "minifat": minifat,
        "directory": directory,
        "stream": stream,
        "free": 0,
        "slack": 0,
    }
    return [[name, values[name]] for name in SECTOR_CLASSES]


MSG_HEADERS_ONLY: Mapping[str, Any] = {
    "version": 3,
    "sector_size": 512,
    "sector_shift": 9,
    "mini_sector_shift": 6,
    "mini_cutoff": 4096,
    "num_fat_sectors": 1,
    "num_dir_sectors": 0,
    "first_dir_sector": 1,
    "num_mini_fat_sectors": 1,
    "first_mini_fat_sector": 2,
    "num_difat_sectors": 0,
    "difat_used": [0],
    "file_length": 3072,
    "sector_count": 6,
    "directory_entries": 4,
    "sector_accounting": _accounting(512, 512, 512, 512, 1024),
    "directory": [
        ("Root Entry", STGTY_ROOT, 640),
        ("__properties_version1.0", STGTY_STREAM, 64),
        ("__substg1.0_007D001F", STGTY_STREAM, 518),
    ],
    "streams": {
        "__properties_version1.0": {"mini": True, "start": 0, "size": 64, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 1, "size": 518, "sectors": 9},
        "<root>": {"mini": False, "start": 3, "size": 640, "sectors": 2},
    },
}

MSG_HEADERS_HTML: Mapping[str, Any] = {
    "version": 3,
    "sector_size": 512,
    "sector_shift": 9,
    "mini_sector_shift": 6,
    "mini_cutoff": 4096,
    "num_fat_sectors": 1,
    "num_dir_sectors": 0,
    "first_dir_sector": 1,
    "num_mini_fat_sectors": 1,
    "first_mini_fat_sector": 2,
    "num_difat_sectors": 0,
    "difat_used": [0],
    "file_length": 3072,
    "sector_count": 6,
    "directory_entries": 4,
    "sector_accounting": _accounting(512, 512, 512, 512, 1024),
    "directory": [
        ("Root Entry", STGTY_ROOT, 832),
        ("__properties_version1.0", STGTY_STREAM, 64),
        ("__substg1.0_007D001F", STGTY_STREAM, 518),
        ("__substg1.0_10130102", STGTY_STREAM, 160),
    ],
    "streams": {
        "__properties_version1.0": {"mini": True, "start": 0, "size": 64, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 1, "size": 518, "sectors": 9},
        "__substg1.0_10130102": {"mini": True, "start": 10, "size": 160, "sectors": 3},
        "<root>": {"mini": False, "start": 3, "size": 832, "sectors": 2},
    },
}

MSG_V4_SECTORS: Mapping[str, Any] = {
    "version": 4,
    "sector_size": 4096,
    "sector_shift": 12,
    "mini_sector_shift": 6,
    "mini_cutoff": 4096,
    "num_fat_sectors": 1,
    "num_dir_sectors": 1,
    "first_dir_sector": 1,
    "num_mini_fat_sectors": 1,
    "first_mini_fat_sector": 2,
    "num_difat_sectors": 0,
    "difat_used": [0],
    "file_length": 20480,
    "sector_count": 5,
    "directory_entries": 32,
    "sector_accounting": _accounting(4096, 4096, 4096, 4096, 4096),
    "directory": [
        ("Root Entry", STGTY_ROOT, 832),
        ("__properties_version1.0", STGTY_STREAM, 64),
        ("__substg1.0_007D001F", STGTY_STREAM, 518),
        ("__substg1.0_10130102", STGTY_STREAM, 160),
    ],
    "streams": {
        "__properties_version1.0": {"mini": True, "start": 0, "size": 64, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 1, "size": 518, "sectors": 9},
        "__substg1.0_10130102": {"mini": True, "start": 10, "size": 160, "sectors": 3},
        "<root>": {"mini": False, "start": 3, "size": 832, "sectors": 1},
    },
}

MSG_MINI_CUTOFF_BOUNDARY: Mapping[str, Any] = {
    "version": 3,
    "sector_size": 512,
    "sector_shift": 9,
    "mini_sector_shift": 6,
    "mini_cutoff": 4096,
    "num_fat_sectors": 1,
    "num_dir_sectors": 0,
    "first_dir_sector": 1,
    "num_mini_fat_sectors": 1,
    "first_mini_fat_sector": 2,
    "num_difat_sectors": 0,
    "difat_used": [0],
    "file_length": 14848,
    "sector_count": 29,
    "directory_entries": 4,
    "sector_accounting": _accounting(512, 512, 512, 512, 12800),
    "directory": [
        ("Root Entry", STGTY_ROOT, 4096),
        ("boundary_4095", STGTY_STREAM, 4095),
        ("boundary_4096", STGTY_STREAM, 4096),
        ("boundary_4097", STGTY_STREAM, 4097),
    ],
    "streams": {
        "boundary_4095": {"mini": True, "start": 0, "size": 4095, "sectors": 64},
        "boundary_4097": {"mini": False, "start": 11, "size": 4097, "sectors": 9},
        "boundary_4096": {"mini": False, "start": 20, "size": 4096, "sectors": 8},
        "<root>": {"mini": False, "start": 3, "size": 4096, "sectors": 8},
    },
}

MSG_OUTLOOK_LAYOUT_HANDBUILT: Mapping[str, Any] = {
    "version": 3,
    "sector_size": 512,
    "sector_shift": 9,
    "mini_sector_shift": 6,
    "mini_cutoff": 4096,
    "num_fat_sectors": 1,
    "num_dir_sectors": 0,
    "first_dir_sector": 1,
    "num_mini_fat_sectors": 1,
    "first_mini_fat_sector": 5,
    "num_difat_sectors": 0,
    "difat_used": [0],
    "file_length": 8704,
    "sector_count": 17,
    "directory_entries": 16,
    "sector_accounting": _accounting(512, 512, 512, 2048, 5120),
    "directory": [
        ("Root Entry", STGTY_ROOT, 4928),
        ("__properties_version1.0", STGTY_STREAM, 64),
        ("__nameid_version1.0", STGTY_STORAGE, 0),
        ("__substg1.0_00020102", STGTY_STREAM, 160),
        ("__substg1.0_00030102", STGTY_STREAM, 440),
        ("__substg1.0_00040102", STGTY_STREAM, 3090),
        ("__substg1.0_007D001F", STGTY_STREAM, 518),
        ("__substg1.0_10130102", STGTY_STREAM, 160),
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 56),
        ("__attach_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_37010102", STGTY_STREAM, 40),
        ("__substg1.0_3707001F", STGTY_STREAM, 40),
    ],
    "streams": {
        "__properties_version1.0": {"mini": True, "start": 0, "size": 64, "sectors": 1},
        "__nameid_version1.0/__substg1.0_00020102":
            {"mini": True, "start": 1, "size": 160, "sectors": 3},
        "__nameid_version1.0/__substg1.0_00030102":
            {"mini": True, "start": 4, "size": 440, "sectors": 7},
        "__nameid_version1.0/__substg1.0_00040102":
            {"mini": True, "start": 11, "size": 3090, "sectors": 49},
        "__substg1.0_007D001F": {"mini": True, "start": 60, "size": 518, "sectors": 9},
        "__substg1.0_10130102": {"mini": True, "start": 69, "size": 160, "sectors": 3},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 72, "size": 56, "sectors": 1},
        "__attach_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 73, "size": 72, "sectors": 2},
        "__attach_version1.0_#00000000/__substg1.0_37010102":
            {"mini": True, "start": 75, "size": 40, "sectors": 1},
        "__attach_version1.0_#00000000/__substg1.0_3707001F":
            {"mini": True, "start": 76, "size": 40, "sectors": 1},
        "<root>": {"mini": False, "start": 6, "size": 4928, "sectors": 10},
    },
}

#: Turn 1b.3 (D3): a file whose FAT is reached through an **extended** DIFAT chain
#: ([MS-CFB] 2.2, 2.3.1). It is ``MSG_HEADERS_HTML``'s content moved past a padding run:
#: the header declares 110 FAT sectors -- only the first is real, the other 109 are
#: ``FREESECT`` padding the file does not hold -- so the directory, the miniFAT and the
#: mini stream shift to 110 / 111 / 112, and the 110th FAT id lives in one extended DIFAT
#: sector at 114. 115 body sectors, 59392 bytes; the DIFAT sector is what makes the
#: extended chain necessary (`msg.cfb_difat_extended`).
MSG_DIFAT_EXTENDED: Mapping[str, Any] = {
    "version": 3,
    "sector_size": 512,
    "sector_shift": 9,
    "mini_sector_shift": 6,
    "mini_cutoff": 4096,
    "num_fat_sectors": 110,
    "num_dir_sectors": 0,
    "first_dir_sector": 110,
    "num_mini_fat_sectors": 1,
    "first_mini_fat_sector": 111,
    "num_difat_sectors": 1,
    "difat_used": list(range(109)),
    "file_length": 59392,
    "sector_count": 116,
    "directory_entries": 4,
    "sector_accounting": [
        ["header", 512],
        ["difat", 512],
        ["fat", 56320],
        ["minifat", 512],
        ["directory", 512],
        ["stream", 1024],
        ["free", 0],
        ["slack", 0],
    ],
    "directory": [
        ("Root Entry", STGTY_ROOT, 832),
        ("__properties_version1.0", STGTY_STREAM, 64),
        ("__substg1.0_007D001F", STGTY_STREAM, 518),
        ("__substg1.0_10130102", STGTY_STREAM, 160),
    ],
    "streams": {
        "__properties_version1.0": {"mini": True, "start": 0, "size": 64, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 1, "size": 518, "sectors": 9},
        "__substg1.0_10130102": {"mini": True, "start": 10, "size": 160, "sectors": 3},
        "<root>": {"mini": False, "start": 112, "size": 832, "sectors": 2},
    },
}

#: Every **well-formed** committed fixture, keyed by stem (the five from Turn 1b.2 plus
#: ``msg_difat_extended``). The three hostile mutants are deliberately absent: they are
#: the base's bytes with one word patched, and their expectations are below.
CONSTRUCTION: Mapping[str, Mapping[str, Any]] = {
    "msg_headers_only": MSG_HEADERS_ONLY,
    "msg_headers_html": MSG_HEADERS_HTML,
    "msg_v4_sectors": MSG_V4_SECTORS,
    "msg_mini_cutoff_boundary": MSG_MINI_CUTOFF_BOUNDARY,
    "msg_outlook_layout_handbuilt": MSG_OUTLOOK_LAYOUT_HANDBUILT,
    "msg_difat_extended": MSG_DIFAT_EXTENDED,
}

#: Turn 1b.3: what each **hostile** fixture must do, typed from [MS-CFB] and the E2 table
#: (`docs/design/msg-architecture.md`) before the reader runs. ``outcome`` is ``opens`` (a
#: ``cfb.CfbFile``) or ``refusal`` (a ``cfb.CfbRefusal`` with ``reason``); for an opened
#: file ``stream_faults`` is the closed per-stream fault, ``intact_streams`` are the ones
#: that must still read ``ok``, and ``unaccounted`` is the byte count no sector class
#: claims (0 when every chain is intact).
HOSTILE_EXPECTATIONS: Mapping[str, Mapping[str, Any]] = {
    "msg_fat_cycle": {
        "outcome": "opens",
        "file_length": 6656,
        "stream_faults": {"big_stream": "cycle"},
        "intact_streams": ("__properties_version1.0", "__substg1.0_10130102"),
        "unaccounted": 3584,
    },
    "msg_directory_loop": {
        "outcome": "refusal",
        "reason": "cfb_directory_loop",
        "file_length": 6656,
    },
    "msg_truncated_stream": {
        "outcome": "opens",
        "file_length": 6656,
        "stream_faults": {"big_stream": "short_chain"},
        "intact_streams": ("__properties_version1.0", "__substg1.0_10130102"),
        "unaccounted": 0,
    },
}
