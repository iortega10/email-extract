"""Turn 1b.9: the Outlook-layout proof over the one hand-built family-D fixture.

``msg_outlook_layout_handbuilt`` (built in Turn 1b.2, corrected in Turn 1b.5) is the one
fixture whose *declaration* follows Outlook's observed structure (``docs/design/email-spike.md``
B1-B4) rather than the writer's minimal defaults: a ``__nameid_version1.0`` storage with three
binary streams, one ``__recip_version1.0_#00000000`` and one ``__attach_version1.0_#00000000``,
a 32-byte top-level property header with the counts ``1/1``, and 8-byte sub-tables.

The two declared tests are:

* ``test_the_handbuilt_layout_matches_the_construction_table`` -- the fixture's directory,
  streams, table headers, class, recipient tags and attachment layout equal the hand-typed
  construction table, read through **both** the package's reader and ``olefile``;
* ``test_the_handbuilt_layout_is_not_writer_defaults`` -- the properties that distinguish it
  from the writer's default declaration, each pinned to the B1-B4 observation it cites.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from emailextract import cfb  # noqa: E402
from support import msg_construction, olefile_oracle  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
NAME = "msg_outlook_layout_handbuilt"
TABLE = msg_construction.MSG_OUTLOOK_LAYOUT_HANDBUILT

_CLASS_STREAM = "__substg1.0_001A001F"
_CLASS_BYTES = "IPM.Note".encode("utf-16-le")


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _tags(blob: bytes, *, header: int) -> set[int]:
    """The property ids in one table: ``(propType, propId)`` words, so the tag is at ``+2``."""
    return {
        int.from_bytes(blob[offset + 2 : offset + 4], "little")
        for offset in range(header, len(blob), 16)
    }


def test_the_handbuilt_layout_matches_the_construction_table() -> None:
    """D6: the fixture's layout equals the hand-typed table, through two independent readers."""
    data = _bytes(NAME)
    assert olefile_oracle.compare(data, TABLE) == [], "the oracle disagrees with the table"

    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile), opened
    # The package's own reader agrees with the table's directory rows and stream map.
    assert [(entry.name, entry.entry_type, entry.size) for entry in opened.entries][: len(TABLE["directory"])] == [
        tuple(row) for row in TABLE["directory"]
    ]
    streams = {entry.path: entry for entry in opened.entries if entry.entry_type == cfb.STGTY_STREAM}
    assert set(streams) | {"<root>"} == set(TABLE["streams"])
    for path, want in TABLE["streams"].items():
        if path == "<root>":
            continue
        assert streams[path].size == want["size"], path
        assert (0 < want["size"] < TABLE["mini_cutoff"]) == want["mini"], path

    # The oracle's own reading: the same directory and the same stream sizes and mini flags.
    assert olefile_oracle.directory_rows(data) == [tuple(row) for row in TABLE["directory"]]
    sizes = olefile_oracle.stream_sizes(data)
    assert olefile_oracle.mini_flags(data) == {path: entry["mini"] for path, entry in TABLE["streams"].items() if path != "<root>"}
    for path, want in TABLE["streams"].items():
        if path != "<root>":
            assert sizes[path] == want["size"], path

    # B2: the top-level header is 32 bytes, the sub-tables 8 bytes; each is 16 bytes per entry.
    top = olefile_oracle.stream_bytes(data, "__properties_version1.0")
    assert len(top) == 32 + 3 * 16
    assert int.from_bytes(top[16:20], "little") == 1  # recipient count @16
    assert int.from_bytes(top[20:24], "little") == 1  # attachment count @20
    raw_recipient = olefile_oracle.stream_bytes(data, "__recip_version1.0_#00000000/__properties_version1.0")
    raw_attach = olefile_oracle.stream_bytes(data, "__attach_version1.0_#00000000/__properties_version1.0")
    assert len(raw_recipient) == 8 + 4 * 16
    assert len(raw_attach) == 8 + 4 * 16

    # B4: 0x3FDE/0x3FFD are fixed entries and the class (0x001A) is both an entry and a stream.
    assert {0x3FDE, 0x3FFD, 0x001A} <= _tags(top, header=32)
    assert olefile_oracle.stream_bytes(data, _CLASS_STREAM) == _CLASS_BYTES
    # B3: the recipient table's observed typing.
    assert {0x0C15, 0x3001, 0x3002, 0x3003} <= _tags(raw_recipient, header=8)

    # B1: the one attachment holds a by-value file (3701:0102) and a 3707:001F name.
    attach = {path for path in sizes if path.startswith("__attach_version1.0_#00000000/")}
    assert "__attach_version1.0_#00000000/__substg1.0_37010102" in attach
    assert "__attach_version1.0_#00000000/__substg1.0_3707001F" in attach
    # B1: __nameid_version1.0 holds the three binary streams.
    assert {
        "__nameid_version1.0/__substg1.0_00020102",
        "__nameid_version1.0/__substg1.0_00030102",
        "__nameid_version1.0/__substg1.0_00040102",
    } <= set(sizes)


def test_the_handbuilt_layout_is_not_writer_defaults() -> None:
    """D6: the properties that distinguish the hand-built declaration from a default one.

    The default is ``msg_headers_html`` -- what the writer emits for the declaration every
    other fixture uses (the properties table plus the data streams, no named-property storage,
    no recipient, no attachment). Each difference is pinned to the B1-B4 observation it cites;
    the properties that *do* coincide with the writer's defaults are stated, not hidden.
    """
    handbuilt = _bytes(NAME)
    default = _bytes("msg_headers_html")

    def storages(data: bytes) -> set[str]:
        opened = cfb.open_cfb(data)
        assert isinstance(opened, cfb.CfbFile)
        return {entry.path for entry in opened.entries if entry.entry_type == cfb.STGTY_STORAGE}

    def leaves(data: bytes) -> set[str]:
        opened = cfb.open_cfb(data)
        assert isinstance(opened, cfb.CfbFile)
        return {entry.path for entry in opened.entries if entry.entry_type == cfb.STGTY_STREAM}

    # B1: the observed layout carries three storages the writer's default declaration has none of
    # -- __nameid_version1.0 with its three binary streams, one recipient and one attachment.
    handbuilt_storages, default_storages = storages(handbuilt), storages(default)
    assert handbuilt_storages == {"__nameid_version1.0", "__recip_version1.0_#00000000", "__attach_version1.0_#00000000"}
    assert default_storages == set()
    assert "__nameid_version1.0" not in default_storages
    assert len([p for p in handbuilt_storages if p.startswith("__recip_version1.0_")]) == 1
    assert len([p for p in handbuilt_storages if p.startswith("__attach_version1.0_")]) == 1
    # ... and the sub-storages' own tables are named streams, so the leaf set differs too.
    assert any(path.startswith("__nameid_version1.0/") for path in leaves(handbuilt))
    assert not any(path.startswith("__nameid_version1.0/") for path in leaves(default))

    # B2: the top-level counts are 1/1 (the writer's default declares 0/0).
    top = olefile_oracle.stream_bytes(handbuilt, "__properties_version1.0")
    default_top = olefile_oracle.stream_bytes(default, "__properties_version1.0")
    assert (int.from_bytes(top[16:20], "little"), int.from_bytes(top[20:24], "little")) == (1, 1)
    assert (
        int.from_bytes(default_top[16:20], "little"),
        int.from_bytes(default_top[20:24], "little"),
    ) == (0, 0)

    # B1/B2: the named-property storage is present, and the sub-tables open on 8 bytes.
    for path in ("__recip_version1.0_#00000000/__properties_version1.0", "__attach_version1.0_#00000000/__properties_version1.0"):
        assert (len(olefile_oracle.stream_bytes(handbuilt, path)) - 8) % 16 == 0

    # The layout arithmetic the fixture shares with the writer's defaults -- stated, so the
    # "not writer defaults" claim is only about the declaration, not the CFB scaffold.
    opened = cfb.open_cfb(handbuilt)
    assert isinstance(opened, cfb.CfbFile)
    assert opened.sector_count == TABLE["sector_count"] == 19
    assert len(handbuilt) == TABLE["file_length"] == 19 * 512  # no tail slack
    assert dict(opened.accounting)["slack"] == 0
    assert opened.unaccounted == 0
    # Every stream but the root is mini-resident, and the root's mini stream is regular: the
    # writer's own mini rule (size < cutoff), which the observation B1's small streams follow.
    for path, flag in olefile_oracle.mini_flags(handbuilt).items():
        assert flag is True, path
    assert TABLE["streams"]["<root>"]["mini"] is False
