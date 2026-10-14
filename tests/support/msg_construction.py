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
    "first_mini_fat_sector": 6,
    "num_difat_sectors": 0,
    "difat_used": [0],
    "file_length": 9728,
    "sector_count": 19,
    "directory_entries": 20,
    "sector_accounting": _accounting(512, 512, 512, 2560, 5632),
    "directory": [
        ("Root Entry", STGTY_ROOT, 5312),
        ("__properties_version1.0", STGTY_STREAM, 80),
        ("__nameid_version1.0", STGTY_STORAGE, 0),
        ("__substg1.0_00020102", STGTY_STREAM, 160),
        ("__substg1.0_00030102", STGTY_STREAM, 440),
        ("__substg1.0_00040102", STGTY_STREAM, 3090),
        ("__substg1.0_007D001F", STGTY_STREAM, 518),
        ("__substg1.0_001A001F", STGTY_STREAM, 16),
        ("__substg1.0_10130102", STGTY_STREAM, 160),
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_3001001F", STGTY_STREAM, 24),
        ("__substg1.0_3002001F", STGTY_STREAM, 8),
        ("__substg1.0_3003001F", STGTY_STREAM, 32),
        ("__attach_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_37010102", STGTY_STREAM, 40),
        ("__substg1.0_3707001F", STGTY_STREAM, 40),
    ],
    "streams": {
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__nameid_version1.0/__substg1.0_00020102":
            {"mini": True, "start": 2, "size": 160, "sectors": 3},
        "__nameid_version1.0/__substg1.0_00030102":
            {"mini": True, "start": 5, "size": 440, "sectors": 7},
        "__nameid_version1.0/__substg1.0_00040102":
            {"mini": True, "start": 12, "size": 3090, "sectors": 49},
        "__substg1.0_007D001F": {"mini": True, "start": 61, "size": 518, "sectors": 9},
        "__substg1.0_001A001F": {"mini": True, "start": 70, "size": 16, "sectors": 1},
        "__substg1.0_10130102": {"mini": True, "start": 71, "size": 160, "sectors": 3},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 74, "size": 72, "sectors": 2},
        "__recip_version1.0_#00000000/__substg1.0_3001001F":
            {"mini": True, "start": 76, "size": 24, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3002001F":
            {"mini": True, "start": 77, "size": 8, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3003001F":
            {"mini": True, "start": 78, "size": 32, "sectors": 1},
        "__attach_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 79, "size": 72, "sectors": 2},
        "__attach_version1.0_#00000000/__substg1.0_37010102":
            {"mini": True, "start": 81, "size": 40, "sectors": 1},
        "__attach_version1.0_#00000000/__substg1.0_3707001F":
            {"mini": True, "start": 82, "size": 40, "sectors": 1},
        "<root>": {"mini": False, "start": 7, "size": 5312, "sectors": 11},
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

#: Turn 1b.4 (the five property-layer fixtures). All five are version 3, 512-byte
#: sectors, mini-cutoff 4096 and entirely mini-resident (no stream reaches the cutoff),
#: so the writer lays out: header, one FAT sector, the directory, one miniFAT sector,
#: then the root's mini stream in the FAT ([MS-CFB] 2.4). Every number below is typed
#: from that layout, never read out of a reader.
def _property_layer_table(
    *,
    directory: list[tuple[str, int, int]],
    streams: dict[str, dict[str, Any]],
    dir_sectors: int,
    mini_fat_sector: int,
    stream_bytes: int,
    file_length: int,
) -> Mapping[str, Any]:
    """One all-mini v3 property-layer fixture's construction table (Turn 1b.4)."""
    return {
        "version": 3,
        "sector_size": 512,
        "sector_shift": 9,
        "mini_sector_shift": 6,
        "mini_cutoff": 4096,
        "num_fat_sectors": 1,
        "num_dir_sectors": 0,
        "first_dir_sector": 1,
        "num_mini_fat_sectors": 1,
        "first_mini_fat_sector": mini_fat_sector,
        "num_difat_sectors": 0,
        "difat_used": [0],
        "file_length": file_length,
        "sector_count": file_length // 512,
        "directory_entries": dir_sectors * 4,
        "sector_accounting": _accounting(512, 512, 512, dir_sectors * 512, stream_bytes),
        "directory": directory,
        "streams": streams,
    }


#: ``msg_non_ipm_note``: ``IPM.Appointment``, plus a subject and a recipient the gate
#: never opens. Layout: FAT 0, directory 1-2, miniFAT 3, mini stream 4.
MSG_NON_IPM_NOTE_TABLE: Mapping[str, Any] = _property_layer_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 320),
        ("__properties_version1.0", STGTY_STREAM, 96),
        ("__substg1.0_001A001F", STGTY_STREAM, 30),
        ("__substg1.0_0037001E", STGTY_STREAM, 27),
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 24),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 96, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 30, "sectors": 1},
        "__substg1.0_0037001E": {"mini": True, "start": 3, "size": 27, "sectors": 1},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 4, "size": 24, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 320, "sectors": 1},
    },
    dir_sectors=2,
    mini_fat_sector=3,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_signed_class``: the same shape with ``IPM.Note.SMIME.MultipartSigned`` (60 bytes).
MSG_SIGNED_CLASS_TABLE: Mapping[str, Any] = _property_layer_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 320),
        ("__properties_version1.0", STGTY_STREAM, 96),
        ("__substg1.0_001A001F", STGTY_STREAM, 60),
        ("__substg1.0_0037001E", STGTY_STREAM, 27),
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 24),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 96, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 60, "sectors": 1},
        "__substg1.0_0037001E": {"mini": True, "start": 3, "size": 27, "sectors": 1},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 4, "size": 24, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 320, "sectors": 1},
    },
    dir_sectors=2,
    mini_fat_sector=3,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_unknown_tags``: ``IPM.Note`` plus four unmodelled tag:type pairs (D4).
MSG_UNKNOWN_TAGS_TABLE: Mapping[str, Any] = _property_layer_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 384),
        ("__properties_version1.0", STGTY_STREAM, 144),
        ("__substg1.0_001A001F", STGTY_STREAM, 16),
        ("__substg1.0_6827001F", STGTY_STREAM, 36),
        ("__substg1.0_65230102", STGTY_STREAM, 4),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 144, "sectors": 3},
        "__substg1.0_001A001F": {"mini": True, "start": 3, "size": 16, "sectors": 1},
        "__substg1.0_6827001F": {"mini": True, "start": 4, "size": 36, "sectors": 1},
        "__substg1.0_65230102": {"mini": True, "start": 5, "size": 4, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 384, "sectors": 1},
    },
    dir_sectors=2,
    mini_fat_sector=3,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_named_properties``: ``__nameid_version1.0`` (160/440/3090 bytes, B1) and a
#: named property (``0x8005``) whose stream carries the ``-00000000`` suffix.
MSG_NAMED_PROPERTIES_TABLE: Mapping[str, Any] = _property_layer_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 4032),
        ("__properties_version1.0", STGTY_STREAM, 96),
        ("__nameid_version1.0", STGTY_STORAGE, 0),
        ("__substg1.0_00020102", STGTY_STREAM, 160),
        ("__substg1.0_00030102", STGTY_STREAM, 440),
        ("__substg1.0_00040102", STGTY_STREAM, 3090),
        ("__substg1.0_001A001F", STGTY_STREAM, 16),
        ("__substg1.0_8005001F-00000000", STGTY_STREAM, 40),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 96, "sectors": 2},
        "__nameid_version1.0/__substg1.0_00020102":
            {"mini": True, "start": 2, "size": 160, "sectors": 3},
        "__nameid_version1.0/__substg1.0_00030102":
            {"mini": True, "start": 5, "size": 440, "sectors": 7},
        "__nameid_version1.0/__substg1.0_00040102":
            {"mini": True, "start": 12, "size": 3090, "sectors": 49},
        "__substg1.0_001A001F": {"mini": True, "start": 61, "size": 16, "sectors": 1},
        "__substg1.0_8005001F-00000000": {"mini": True, "start": 62, "size": 40, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 4032, "sectors": 8},
    },
    dir_sectors=2,
    mini_fat_sector=3,
    stream_bytes=4096,
    file_length=6656,
)

#: ``msg_codepage_disagree``: internet 28591 against message 1252, disagreeing on ``0x93``.
MSG_CODEPAGE_DISAGREE_TABLE: Mapping[str, Any] = _property_layer_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 256),
        ("__properties_version1.0", STGTY_STREAM, 96),
        ("__substg1.0_001A001F", STGTY_STREAM, 16),
        ("__substg1.0_0037001E", STGTY_STREAM, 19),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 96, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_0037001E": {"mini": True, "start": 3, "size": 19, "sectors": 1},
        "<root>": {"mini": False, "start": 3, "size": 256, "sectors": 1},
    },
    dir_sectors=1,
    mini_fat_sector=2,
    stream_bytes=512,
    file_length=2560,
)

#: Turn 1b.5 (the nine body/header fixtures). Every one is version 3, 512-byte sectors,
#: mini-cutoff 4096 and entirely mini-resident, so the writer lays out: header, one FAT
#: sector, the directory, one miniFAT sector, then the root's mini stream. Every number
#: below is typed from ``phase1b-fixtures.md``'s fixture descriptions and the writer's
#: fixed layout rule, then cross-checked against the independent raw reader and ``olefile``.
T15_ENDOFCHAIN = 0xFFFFFFFE


def _t15_table(
    *,
    directory: list[tuple[str, int, int]],
    streams: dict[str, dict[str, Any]],
    dir_sectors: int,
    stream_bytes: int,
    file_length: int,
) -> Mapping[str, Any]:
    """One all-mini v3 Turn 1b.5 fixture's construction table."""
    return _property_layer_table(
        directory=directory,
        streams=streams,
        dir_sectors=dir_sectors,
        mini_fat_sector=1 + dir_sectors,
        stream_bytes=stream_bytes,
        file_length=file_length,
    )


_T15_PROPS = ("__properties_version1.0", STGTY_STREAM, 80)
_T15_CLASS = ("__substg1.0_001A001F", STGTY_STREAM, 16)
_T15_TRANSPORT = ("__substg1.0_007D001F", STGTY_STREAM, 218)
_T15_HTML = ("__substg1.0_10130102", STGTY_STREAM, 59)
_T15_PLAIN = ("__substg1.0_1000001F", STGTY_STREAM, 4)

#: ``msg_html_only_no_plain``: the 10-of-11 real shape.
MSG_HTML_ONLY_NO_PLAIN: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 512),
        _T15_PROPS,
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 512, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_plain_only``: a ``0x1000`` ``001F`` body and nothing else.
MSG_PLAIN_ONLY: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 512),
        _T15_PROPS,
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_PLAIN,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_1000001F": {"mini": True, "start": 7, "size": 4, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 512, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_plain_and_html``: both bodies, so the selection rule has something to pick.
MSG_PLAIN_AND_HTML: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 576),
        _T15_PROPS,
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_PLAIN,
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_1000001F": {"mini": True, "start": 7, "size": 4, "sectors": 1},
        "__substg1.0_10130102": {"mini": True, "start": 8, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 576, "sectors": 2},
    },
    dir_sectors=2,
    stream_bytes=1024,
    file_length=3584,
)

#: ``msg_zero_length_body``: a present-but-empty ``0x1000`` stream (start is ENDOFCHAIN).
MSG_ZERO_LENGTH_BODY: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 448),
        _T15_PROPS,
        _T15_CLASS,
        _T15_TRANSPORT,
        ("__substg1.0_1000001F", STGTY_STREAM, 0),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_1000001F": {"mini": False, "start": T15_ENDOFCHAIN, "size": 0, "sectors": 0},
        "<root>": {"mini": False, "start": 4, "size": 448, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_html_meta_charset_contradicts``: ``<meta charset="utf-8">`` against internet 1252.
MSG_HTML_META_CHARSET_CONTRADICTS: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 576),
        _T15_PROPS,
        _T15_CLASS,
        _T15_TRANSPORT,
        ("__substg1.0_10130102", STGTY_STREAM, 94),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 94, "sectors": 2},
        "<root>": {"mini": False, "start": 4, "size": 576, "sectors": 2},
    },
    dir_sectors=2,
    stream_bytes=1024,
    file_length=3584,
)

#: ``msg_no_transport_headers``: no ``0x007D`` at all (a four-entry directory).
MSG_NO_TRANSPORT_HEADERS: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 256),
        _T15_PROPS,
        _T15_CLASS,
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_10130102": {"mini": True, "start": 3, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 3, "size": 256, "sectors": 1},
    },
    dir_sectors=1,
    stream_bytes=512,
    file_length=2560,
)

#: ``msg_transport_headers_utf8_bom``: ``0x007D`` as ``001E``, UTF-8 BOM first.
MSG_TRANSPORT_HEADERS_UTF8_BOM: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 384),
        _T15_PROPS,
        _T15_CLASS,
        ("__substg1.0_007D001E", STGTY_STREAM, 112),
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001E": {"mini": True, "start": 3, "size": 112, "sectors": 2},
        "__substg1.0_10130102": {"mini": True, "start": 5, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 384, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_transport_headers_lf_only``: the transport text uses bare LF line endings.
MSG_TRANSPORT_HEADERS_LF_ONLY: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 448),
        _T15_PROPS,
        _T15_CLASS,
        ("__substg1.0_007D001F", STGTY_STREAM, 136),
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 136, "sectors": 3},
        "__substg1.0_10130102": {"mini": True, "start": 6, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 448, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)

#: ``msg_property_vs_header_conflict``: a ``0x0037`` subject property beside ``0x007D``.
MSG_PROPERTY_VS_HEADER_CONFLICT: Mapping[str, Any] = _t15_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 640),
        ("__properties_version1.0", STGTY_STREAM, 96),
        _T15_CLASS,
        ("__substg1.0_0037001F", STGTY_STREAM, 72),
        _T15_TRANSPORT,
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 96, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_0037001F": {"mini": True, "start": 3, "size": 72, "sectors": 2},
        "__substg1.0_007D001F": {"mini": True, "start": 5, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 9, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 640, "sectors": 2},
    },
    dir_sectors=2,
    stream_bytes=1024,
    file_length=3584,
)


#: Turn 1b.6 (the five message-fact fixtures). Every one is version 3, 512-byte sectors,
#: mini-cutoff 4096 and entirely mini-resident, so the writer lays out: header, one FAT
#: sector, the directory, one miniFAT sector, then the root's mini stream. Every number
#: below is typed from ``phase1b-fixtures.md``'s fixture descriptions and the writer's
#: fixed layout rule, then cross-checked against the independent raw reader and ``olefile``.
def _t16_table(
    *,
    directory: list[tuple[str, int, int]],
    streams: dict[str, dict[str, Any]],
    dir_sectors: int,
    stream_bytes: int,
    file_length: int,
) -> Mapping[str, Any]:
    """One all-mini v3 Turn 1b.6 fixture's construction table."""
    return _property_layer_table(
        directory=directory,
        streams=streams,
        dir_sectors=dir_sectors,
        mini_fat_sector=1 + dir_sectors,
        stream_bytes=stream_bytes,
        file_length=file_length,
    )


MSG_RECIPIENTS_DISPLAY_ONLY: Mapping[str, Any] = _t16_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 704),
        ("__properties_version1.0", STGTY_STREAM, 80),
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_HTML,
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 56),
        ("__substg1.0_3001001F", STGTY_STREAM, 24),
        ("__substg1.0_3002001F", STGTY_STREAM, 8),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 59, "sectors": 1},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 8, "size": 56, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3001001F":
            {"mini": True, "start": 9, "size": 24, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3002001F":
            {"mini": True, "start": 10, "size": 8, "sectors": 1},
        "<root>": {"mini": False, "start": 5, "size": 704, "sectors": 2},
    },
    dir_sectors=3,
    stream_bytes=1024,
    file_length=4096,
)

MSG_RECIPIENTS_EX_NO_SMTP: Mapping[str, Any] = _t16_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 896),
        ("__properties_version1.0", STGTY_STREAM, 80),
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_HTML,
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_3001001F", STGTY_STREAM, 24),
        ("__substg1.0_3002001F", STGTY_STREAM, 4),
        ("__substg1.0_3003001F", STGTY_STREAM, 72),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 59, "sectors": 1},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 8, "size": 72, "sectors": 2},
        "__recip_version1.0_#00000000/__substg1.0_3001001F":
            {"mini": True, "start": 10, "size": 24, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3002001F":
            {"mini": True, "start": 11, "size": 4, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3003001F":
            {"mini": True, "start": 12, "size": 72, "sectors": 2},
        "<root>": {"mini": False, "start": 5, "size": 896, "sectors": 2},
    },
    dir_sectors=3,
    stream_bytes=1024,
    file_length=4096,
)

MSG_RECIPIENTS_BCC_DUPLICATES: Mapping[str, Any] = _t16_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 1472),
        ("__properties_version1.0", STGTY_STREAM, 80),
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_HTML,
        ("__recip_version1.0_#00000000", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_3001001F", STGTY_STREAM, 24),
        ("__substg1.0_3002001F", STGTY_STREAM, 8),
        ("__substg1.0_3003001F", STGTY_STREAM, 32),
        ("__recip_version1.0_#00000001", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_3001001F", STGTY_STREAM, 24),
        ("__substg1.0_3002001F", STGTY_STREAM, 8),
        ("__substg1.0_3003001F", STGTY_STREAM, 36),
        ("__recip_version1.0_#00000002", STGTY_STORAGE, 0),
        ("__properties_version1.0", STGTY_STREAM, 72),
        ("__substg1.0_3001001F", STGTY_STREAM, 24),
        ("__substg1.0_3002001F", STGTY_STREAM, 8),
        ("__substg1.0_3003001F", STGTY_STREAM, 32),
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 80, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 59, "sectors": 1},
        "__recip_version1.0_#00000000/__properties_version1.0":
            {"mini": True, "start": 8, "size": 72, "sectors": 2},
        "__recip_version1.0_#00000000/__substg1.0_3001001F":
            {"mini": True, "start": 10, "size": 24, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3002001F":
            {"mini": True, "start": 11, "size": 8, "sectors": 1},
        "__recip_version1.0_#00000000/__substg1.0_3003001F":
            {"mini": True, "start": 12, "size": 32, "sectors": 1},
        "__recip_version1.0_#00000001/__properties_version1.0":
            {"mini": True, "start": 13, "size": 72, "sectors": 2},
        "__recip_version1.0_#00000001/__substg1.0_3001001F":
            {"mini": True, "start": 15, "size": 24, "sectors": 1},
        "__recip_version1.0_#00000001/__substg1.0_3002001F":
            {"mini": True, "start": 16, "size": 8, "sectors": 1},
        "__recip_version1.0_#00000001/__substg1.0_3003001F":
            {"mini": True, "start": 17, "size": 36, "sectors": 1},
        "__recip_version1.0_#00000002/__properties_version1.0":
            {"mini": True, "start": 18, "size": 72, "sectors": 2},
        "__recip_version1.0_#00000002/__substg1.0_3001001F":
            {"mini": True, "start": 20, "size": 24, "sectors": 1},
        "__recip_version1.0_#00000002/__substg1.0_3002001F":
            {"mini": True, "start": 21, "size": 8, "sectors": 1},
        "__recip_version1.0_#00000002/__substg1.0_3003001F":
            {"mini": True, "start": 22, "size": 32, "sectors": 1},
        "<root>": {"mini": False, "start": 7, "size": 1472, "sectors": 3},
    },
    dir_sectors=5,
    stream_bytes=1536,
    file_length=5632,
)

MSG_TIME_PROPERTY_VS_DATE_HEADER: Mapping[str, Any] = _t16_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 512),
        ("__properties_version1.0", STGTY_STREAM, 112),
        _T15_CLASS,
        _T15_TRANSPORT,
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 112, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 3, "size": 218, "sectors": 4},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 512, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)

MSG_UNICODE_SUBJECT: Mapping[str, Any] = _t16_table(
    directory=[
        ("Root Entry", STGTY_ROOT, 512),
        ("__properties_version1.0", STGTY_STREAM, 96),
        _T15_CLASS,
        ("__substg1.0_0037001F", STGTY_STREAM, 62),
        ("__substg1.0_007D001F", STGTY_STREAM, 158),
        _T15_HTML,
    ],
    streams={
        "__properties_version1.0": {"mini": True, "start": 0, "size": 96, "sectors": 2},
        "__substg1.0_001A001F": {"mini": True, "start": 2, "size": 16, "sectors": 1},
        "__substg1.0_0037001F": {"mini": True, "start": 3, "size": 62, "sectors": 1},
        "__substg1.0_007D001F": {"mini": True, "start": 4, "size": 158, "sectors": 3},
        "__substg1.0_10130102": {"mini": True, "start": 7, "size": 59, "sectors": 1},
        "<root>": {"mini": False, "start": 4, "size": 512, "sectors": 1},
    },
    dir_sectors=2,
    stream_bytes=512,
    file_length=3072,
)


#: Turn 1b.4: what ``mapi.py`` must read from each property-layer fixture, typed from
#: B1-B4 and the fixture description **before** ``mapi.py`` ran. There are no ``.msg``
#: sidecars (``evals/labels.py`` still accepts only ``.eml``; 1b.10's file set), so this
#: is the ``HOSTILE_EXPECTATIONS``-style literal the tests hold the reader against.
MAPI_EXPECTATIONS: Mapping[str, Mapping[str, Any]] = {
    "msg_non_ipm_note": {
        "class_verdict": "not_ipm_note",
        "message_class": "IPM.Appointment",
        "stopped": True,
        "recipient_rows": 0,
        "unknown_tags": [],
        "named_tags": [],
        "observations": ["msg.class_not_ipm_note"],
    },
    "msg_signed_class": {
        "class_verdict": "signed_or_encrypted",
        "message_class": "IPM.Note.SMIME.MultipartSigned",
        "stopped": True,
        "recipient_rows": 0,
        "unknown_tags": [],
        "named_tags": [],
        "observations": ["msg.class_not_ipm_note"],
    },
    "msg_unknown_tags": {
        "class_verdict": "ipm_note",
        "message_class": "IPM.Note",
        "stopped": False,
        "unknown_tags": ["6200:0003", "6523:0102", "6748:0014", "6827:001f"],
        "named_tags": [],
        "observations": ["msg.property_tag_unknown"],
    },
    "msg_named_properties": {
        "class_verdict": "ipm_note",
        "message_class": "IPM.Note",
        "stopped": False,
        "unknown_tags": [],
        "named_tags": ["8005"],
        "nameid_present": True,
        "nameid_sizes": [160, 440, 3090],
        "observations": ["msg.named_property_unresolved"],
    },
    "msg_codepage_disagree": {
        "class_verdict": "ipm_note",
        "message_class": "IPM.Note",
        "stopped": False,
        "internet_codepage": 28591,
        "message_codepage": 1252,
        "subject_text": "synthetic \u0093 subject",
        "subject_source": "internet_cpid",
        "unknown_tags": [],
        "named_tags": [],
        "observations": [],
    },
}

#: Every **well-formed** committed fixture, keyed by stem (the five from Turn 1b.2 plus
#: ``msg_difat_extended``). The three hostile mutants are deliberately absent: they are
#: the base's bytes with one word patched, and their expectations are below.

#: Turn 1b.7 (the ten Family G fixtures). Every one is version 3, 512-byte sectors, a
#: 4096-byte mini cutoff. The numbers are the writer's fixed layout rule (header, one FAT
#: sector, the directory, one miniFAT sector, then the mini stream) cross-checked by the
#: independent raw reader and the ``olefile`` oracle.
# msg_embedded_message
MSG_EMBEDDED_MESSAGE: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 6,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 6144,
    'sector_count': 12,
    'directory_entries': 20,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 2560],
                             ['stream', 2048],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1792),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_3707001F', 2, 26),
                     ('__substg1.0_3701000D', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_0037001F', 2, 20),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__recip_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3001001F', 2, 24),
                     ('__substg1.0_3002001F', 2, 8),
                     ('__substg1.0_3003001F', 2, 32)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_001A001F': {   'mini': True,
                                                                                                  'start': 14,
                                                                                                  'size': 16,
                                                                                                  'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_0037001F': {   'mini': True,
                                                                                                  'start': 15,
                                                                                                  'size': 20,
                                                                                                  'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_007D001F': {   'mini': True,
                                                                                                  'start': 16,
                                                                                                  'size': 396,
                                                                                                  'sectors': 7},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__properties_version1.0': {   'mini': True,
                                                                                                     'start': 13,
                                                                                                     'size': 56,
                                                                                                     'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__recip_version1.0_#00000000/__substg1.0_3001001F': {   'mini': True,
                                                                                                                               'start': 25,
                                                                                                                               'size': 24,
                                                                                                                               'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__recip_version1.0_#00000000/__substg1.0_3002001F': {   'mini': True,
                                                                                                                               'start': 26,
                                                                                                                               'size': 8,
                                                                                                                               'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__recip_version1.0_#00000000/__substg1.0_3003001F': {   'mini': True,
                                                                                                                               'start': 27,
                                                                                                                               'size': 32,
                                                                                                                               'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__recip_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                                                                  'start': 23,
                                                                                                                                  'size': 72,
                                                                                                                                  'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 12,
                                                                             'size': 26,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 56,
                                                                                'sectors': 1},
                   '<root>': {'mini': False, 'start': 7, 'size': 1792, 'sectors': 4}}}

# msg_embedded_depth_two
MSG_EMBEDDED_DEPTH_TWO: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 6,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 5632,
    'sector_count': 11,
    'directory_entries': 20,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 2560],
                             ['stream', 1536],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1344),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_3707001F', 2, 18),
                     ('__substg1.0_3701000D', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_0037001F', 2, 10),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_3707001F', 2, 20),
                     ('__substg1.0_3701000D', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_0037001F', 2, 14)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_001A001F': {   'mini': True,
                                                                                                  'start': 14,
                                                                                                  'size': 16,
                                                                                                  'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_0037001F': {   'mini': True,
                                                                                                  'start': 15,
                                                                                                  'size': 10,
                                                                                                  'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__properties_version1.0': {   'mini': True,
                                                                                                     'start': 13,
                                                                                                     'size': 56,
                                                                                                     'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_001A001F': {   'mini': True,
                                                                                                                                                     'start': 19,
                                                                                                                                                     'size': 16,
                                                                                                                                                     'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_0037001F': {   'mini': True,
                                                                                                                                                     'start': 20,
                                                                                                                                                     'size': 14,
                                                                                                                                                     'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__attach_version1.0_#00000000/__substg1.0_3701000D/__properties_version1.0': {   'mini': True,
                                                                                                                                                        'start': 18,
                                                                                                                                                        'size': 56,
                                                                                                                                                        'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                                                                                'start': 17,
                                                                                                                                'size': 20,
                                                                                                                                'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                                                                   'start': 16,
                                                                                                                                   'size': 56,
                                                                                                                                   'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 12,
                                                                             'size': 18,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 56,
                                                                                'sectors': 1},
                   '<root>': {'mini': False, 'start': 7, 'size': 1344, 'sectors': 3}}}

# msg_attachment_with_cid
MSG_ATTACHMENT_WITH_CID: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 4,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 4608,
    'sector_count': 9,
    'directory_entries': 12,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 1536],
                             ['stream', 1536],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1088),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 88),
                     ('__substg1.0_3707001F', 2, 20),
                     ('__substg1.0_370E001F', 2, 30),
                     ('__substg1.0_3712001F', 2, 34),
                     ('__substg1.0_37010102', 2, 38)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_37010102': {   'mini': True,
                                                                             'start': 16,
                                                                             'size': 38,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 30,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3712001F': {   'mini': True,
                                                                             'start': 15,
                                                                             'size': 34,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 88,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 5, 'size': 1088, 'sectors': 3}}}

# msg_attachment_hidden
MSG_ATTACHMENT_HIDDEN: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 4,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 4096,
    'sector_count': 8,
    'directory_entries': 12,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 1536],
                             ['stream', 1024],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1024),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 104),
                     ('__substg1.0_3707001F', 2, 32),
                     ('__substg1.0_370E001F', 2, 18),
                     ('__substg1.0_37010102', 2, 17)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_37010102': {   'mini': True,
                                                                             'start': 15,
                                                                             'size': 17,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 32,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 18,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 104,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 5, 'size': 1024, 'sectors': 2}}}

# msg_attachment_ole
MSG_ATTACHMENT_OLE: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 4,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 4096,
    'sector_count': 8,
    'directory_entries': 12,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 1536],
                             ['stream', 1024],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1024),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 20),
                     ('__substg1.0_370E001F', 2, 48),
                     ('__substg1.0_3701000D', 1, 0),
                     ('__substg1.0_37010102', 2, 17)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_3701000D/__substg1.0_37010102': {   'mini': True,
                                                                                                  'start': 15,
                                                                                                  'size': 17,
                                                                                                  'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 48,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 5, 'size': 1024, 'sectors': 2}}}

# msg_attachment_by_reference
MSG_ATTACHMENT_BY_REFERENCE: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 6,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 5632,
    'sector_count': 11,
    'directory_entries': 20,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 2560],
                             ['stream', 1536],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1280),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_3707001F', 2, 18),
                     ('__substg1.0_370E001F', 2, 20),
                     ('__attach_version1.0_#00000001', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_3707001F', 2, 18),
                     ('__substg1.0_370E001F', 2, 20),
                     ('__attach_version1.0_#00000002', 1, 0),
                     ('__properties_version1.0', 2, 56),
                     ('__substg1.0_3707001F', 2, 18),
                     ('__substg1.0_370E001F', 2, 20)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 12,
                                                                             'size': 18,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 56,
                                                                                'sectors': 1},
                   '__attach_version1.0_#00000001/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 15,
                                                                             'size': 18,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 16,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__properties_version1.0': {   'mini': True,
                                                                                'start': 14,
                                                                                'size': 56,
                                                                                'sectors': 1},
                   '__attach_version1.0_#00000002/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 18,
                                                                             'size': 18,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000002/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 19,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000002/__properties_version1.0': {   'mini': True,
                                                                                'start': 17,
                                                                                'size': 56,
                                                                                'sectors': 1},
                   '<root>': {'mini': False, 'start': 7, 'size': 1280, 'sectors': 3}}}

# msg_attachment_hostile_name
MSG_ATTACHMENT_HOSTILE_NAME: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 4,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 4096,
    'sector_count': 8,
    'directory_entries': 12,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 1536],
                             ['stream', 1024],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1024),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 34),
                     ('__substg1.0_370E001F', 2, 48),
                     ('__substg1.0_37010102', 2, 7)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_37010102': {   'mini': True,
                                                                             'start': 15,
                                                                             'size': 7,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 34,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 48,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 5, 'size': 1024, 'sectors': 2}}}

# msg_attachment_zero_size
MSG_ATTACHMENT_ZERO_SIZE: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 4,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 4096,
    'sector_count': 8,
    'directory_entries': 12,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 1536],
                             ['stream', 1024],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 960),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 18),
                     ('__substg1.0_370E001F', 2, 48),
                     ('__substg1.0_37010102', 2, 0)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_37010102': {   'mini': False,
                                                                             'start': 4294967294,
                                                                             'size': 0,
                                                                             'sectors': 0},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 18,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 48,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 5, 'size': 960, 'sectors': 2}}}

# msg_attachments_4095_4096_4097
MSG_ATTACHMENTS_4095_4096_4097: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 6,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 18432,
    'sector_count': 36,
    'directory_entries': 20,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 2560],
                             ['stream', 14336],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 5568),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 10),
                     ('__substg1.0_370E001F', 2, 48),
                     ('__substg1.0_37010102', 2, 4095),
                     ('__attach_version1.0_#00000001', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 10),
                     ('__substg1.0_370E001F', 2, 48),
                     ('__substg1.0_37010102', 2, 4096),
                     ('__attach_version1.0_#00000002', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 10),
                     ('__substg1.0_370E001F', 2, 48),
                     ('__substg1.0_37010102', 2, 4097)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_37010102': {   'mini': True,
                                                                             'start': 15,
                                                                             'size': 4095,
                                                                             'sectors': 64},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 10,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 48,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '__attach_version1.0_#00000001/__substg1.0_37010102': {   'mini': False,
                                                                             'start': 18,
                                                                             'size': 4096,
                                                                             'sectors': 8},
                   '__attach_version1.0_#00000001/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 81,
                                                                             'size': 10,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 82,
                                                                             'size': 48,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__properties_version1.0': {   'mini': True,
                                                                                'start': 79,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '__attach_version1.0_#00000002/__substg1.0_37010102': {   'mini': False,
                                                                             'start': 26,
                                                                             'size': 4097,
                                                                             'sectors': 9},
                   '__attach_version1.0_#00000002/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 85,
                                                                             'size': 10,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000002/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 86,
                                                                             'size': 48,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000002/__properties_version1.0': {   'mini': True,
                                                                                'start': 83,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 7, 'size': 5568, 'sectors': 11}}}

# msg_duplicate_filenames
MSG_DUPLICATE_FILENAMES: Mapping[str, Any] = {   'version': 3,
    'sector_size': 512,
    'sector_shift': 9,
    'mini_sector_shift': 6,
    'mini_cutoff': 4096,
    'num_fat_sectors': 1,
    'num_dir_sectors': 0,
    'first_dir_sector': 1,
    'num_mini_fat_sectors': 1,
    'first_mini_fat_sector': 5,
    'num_difat_sectors': 0,
    'difat_used': [0],
    'file_length': 5120,
    'sector_count': 10,
    'directory_entries': 16,
    'sector_accounting': [   ['header', 512],
                             ['difat', 0],
                             ['fat', 512],
                             ['minifat', 512],
                             ['directory', 2048],
                             ['stream', 1536],
                             ['free', 0],
                             ['slack', 0]],
    'directory': [   ('Root Entry', 5, 1344),
                     ('__properties_version1.0', 2, 80),
                     ('__substg1.0_001A001F', 2, 16),
                     ('__substg1.0_007D001F', 2, 396),
                     ('__substg1.0_10130102', 2, 59),
                     ('__attach_version1.0_#00000000', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 16),
                     ('__substg1.0_370E001F', 2, 20),
                     ('__substg1.0_37010102', 2, 5),
                     ('__attach_version1.0_#00000001', 1, 0),
                     ('__properties_version1.0', 2, 72),
                     ('__substg1.0_3707001F', 2, 16),
                     ('__substg1.0_370E001F', 2, 20),
                     ('__substg1.0_37010102', 2, 6)],
    'streams': {   '__substg1.0_001A001F': {'mini': True, 'start': 2, 'size': 16, 'sectors': 1},
                   '__substg1.0_007D001F': {'mini': True, 'start': 3, 'size': 396, 'sectors': 7},
                   '__substg1.0_10130102': {'mini': True, 'start': 10, 'size': 59, 'sectors': 1},
                   '__properties_version1.0': {'mini': True, 'start': 0, 'size': 80, 'sectors': 2},
                   '__attach_version1.0_#00000000/__substg1.0_37010102': {   'mini': True,
                                                                             'start': 15,
                                                                             'size': 5,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 13,
                                                                             'size': 16,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 14,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000000/__properties_version1.0': {   'mini': True,
                                                                                'start': 11,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '__attach_version1.0_#00000001/__substg1.0_37010102': {   'mini': True,
                                                                             'start': 20,
                                                                             'size': 6,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__substg1.0_3707001F': {   'mini': True,
                                                                             'start': 18,
                                                                             'size': 16,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__substg1.0_370E001F': {   'mini': True,
                                                                             'start': 19,
                                                                             'size': 20,
                                                                             'sectors': 1},
                   '__attach_version1.0_#00000001/__properties_version1.0': {   'mini': True,
                                                                                'start': 16,
                                                                                'size': 72,
                                                                                'sectors': 2},
                   '<root>': {'mini': False, 'start': 6, 'size': 1344, 'sectors': 3}}}


CONSTRUCTION: Mapping[str, Mapping[str, Any]] = {
    "msg_headers_only": MSG_HEADERS_ONLY,
    "msg_headers_html": MSG_HEADERS_HTML,
    "msg_v4_sectors": MSG_V4_SECTORS,
    "msg_mini_cutoff_boundary": MSG_MINI_CUTOFF_BOUNDARY,
    "msg_outlook_layout_handbuilt": MSG_OUTLOOK_LAYOUT_HANDBUILT,
    "msg_difat_extended": MSG_DIFAT_EXTENDED,
    "msg_non_ipm_note": MSG_NON_IPM_NOTE_TABLE,
    "msg_signed_class": MSG_SIGNED_CLASS_TABLE,
    "msg_unknown_tags": MSG_UNKNOWN_TAGS_TABLE,
    "msg_named_properties": MSG_NAMED_PROPERTIES_TABLE,
    "msg_codepage_disagree": MSG_CODEPAGE_DISAGREE_TABLE,
    "msg_html_only_no_plain": MSG_HTML_ONLY_NO_PLAIN,
    "msg_plain_only": MSG_PLAIN_ONLY,
    "msg_plain_and_html": MSG_PLAIN_AND_HTML,
    "msg_zero_length_body": MSG_ZERO_LENGTH_BODY,
    "msg_html_meta_charset_contradicts": MSG_HTML_META_CHARSET_CONTRADICTS,
    "msg_no_transport_headers": MSG_NO_TRANSPORT_HEADERS,
    "msg_transport_headers_utf8_bom": MSG_TRANSPORT_HEADERS_UTF8_BOM,
    "msg_transport_headers_lf_only": MSG_TRANSPORT_HEADERS_LF_ONLY,
    "msg_property_vs_header_conflict": MSG_PROPERTY_VS_HEADER_CONFLICT,
    "msg_recipients_display_only": MSG_RECIPIENTS_DISPLAY_ONLY,
    "msg_recipients_ex_no_smtp": MSG_RECIPIENTS_EX_NO_SMTP,
    "msg_recipients_bcc_duplicates": MSG_RECIPIENTS_BCC_DUPLICATES,
    "msg_time_property_vs_date_header": MSG_TIME_PROPERTY_VS_DATE_HEADER,
    "msg_unicode_subject": MSG_UNICODE_SUBJECT,
    "msg_embedded_message": MSG_EMBEDDED_MESSAGE,
    "msg_embedded_depth_two": MSG_EMBEDDED_DEPTH_TWO,
    "msg_attachment_with_cid": MSG_ATTACHMENT_WITH_CID,
    "msg_attachment_hidden": MSG_ATTACHMENT_HIDDEN,
    "msg_attachment_ole": MSG_ATTACHMENT_OLE,
    "msg_attachment_by_reference": MSG_ATTACHMENT_BY_REFERENCE,
    "msg_attachment_hostile_name": MSG_ATTACHMENT_HOSTILE_NAME,
    "msg_attachment_zero_size": MSG_ATTACHMENT_ZERO_SIZE,
    "msg_attachments_4095_4096_4097": MSG_ATTACHMENTS_4095_4096_4097,
    "msg_duplicate_filenames": MSG_DUPLICATE_FILENAMES,
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
