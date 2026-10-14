"""Turn 1b.3: the hostile set -- ``cfb.py`` refuses or faults, but never raises.

Each committed hostile fixture is the hostile base's bytes with one 32-bit word patched
(``tools/make_msg_fixtures.py``); what it must do is typed in
``tests/support/msg_construction.py`` (``HOSTILE_EXPECTATIONS``) from [MS-CFB] and the E2
table (``docs/design/msg-architecture.md``) **before** the reader runs. ``olefile`` is
never asked about one: E1 measured that it is silent on a cyclic chain and clamps a size
lie, so the package's own reader is the contract here.

The five declared tests are ``test_a_fat_cycle_is_one_streams_fault``,
``test_a_directory_loop_is_a_named_error``, ``test_an_unsupported_header_is_a_named_error``,
``test_magic_without_properties_is_not_a_message`` and
``test_the_extended_difat_is_read_through_and_flagged``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import make_msg_fixtures  # noqa: E402

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb, parse  # noqa: E402
from support import cfb_raw, msg_construction  # noqa: E402

HOSTILE = msg_construction.HOSTILE_EXPECTATIONS
CONSTRUCTION = msg_construction.CONSTRUCTION


def _fixture(name: str) -> bytes:
    return make_msg_fixtures.build_fixture(name)


def test_a_fat_cycle_is_one_streams_fault() -> None:
    data = _fixture("msg_fat_cycle")
    expected = HOSTILE["msg_fat_cycle"]
    assert len(data) == expected["file_length"]
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile), "a cyclic stream chain is a fault, not a refusal"

    # The one faulted stream is the one whose chain points back at itself; the rest read.
    for path, fault in expected["stream_faults"].items():
        payload, actual = cfb.read_stream(opened, path)
        assert actual == fault, (path, actual)
        assert isinstance(payload, bytes)
    for path in expected["intact_streams"]:
        assert cfb.read_stream(opened, path)[1] == cfb.FAULT_OK, path
    faults = {row[0]: row for row in opened.faults}
    assert set(faults) == set(expected["stream_faults"])
    assert faults["big_stream"] == ("big_stream", "cycle", "declared_length_mismatch")
    # The cycle is caught by the visited set, not only by the E2 step bound: the chain is
    # the single sector before the revisit, so the payload is one sector, never the bound's
    # worth of the same sector repeated.
    big = {stream.path: stream for stream in opened.streams}["big_stream"]
    assert big.sectors == (make_msg_fixtures.HOSTILE_BIG_START,)
    assert big.available == 512
    # The sectors the cycle put out of reach are visible, never absorbed.
    assert opened.unaccounted == expected["unaccounted"] > 0


def test_a_directory_loop_is_a_named_error() -> None:
    data = _fixture("msg_directory_loop")
    expected = HOSTILE["msg_directory_loop"]
    assert len(data) == expected["file_length"]
    refused = cfb.open_cfb(data)
    assert isinstance(refused, cfb.CfbRefusal)
    assert refused.reason == expected["reason"] == cfb.CFB_DIRECTORY_LOOP
    assert cfb.CFB_DIRECTORY_LOOP in parse.NAMED_ERROR_REASONS


def test_an_unsupported_header_is_a_named_error() -> None:
    v3 = _fixture("msg_headers_only")
    # A sector shift of 13 is legal in no version ([MS-CFB] 2.2).
    bad_shift = cfb_raw.patch_u32(v3, 26, 13)
    # A v4 header may only use shift 12, so a v4 file with shift 9 is unsupported.
    v4 = _fixture("msg_v4_sectors")
    v4_bad_shift = cfb_raw.patch_u32(v4, 26, 9)
    for name, data in (("shift 13", bad_shift), ("v4 shift 9", v4_bad_shift)):
        refused = cfb.open_cfb(data)
        assert isinstance(refused, cfb.CfbRefusal), name
        assert refused.reason == cfb.CFB_HEADER_UNSUPPORTED, name
        assert cfb.CFB_HEADER_UNSUPPORTED in parse.NAMED_ERROR_REASONS


def test_magic_without_properties_is_not_a_message() -> None:
    # A well-formed container the writer builds from scratch: CFB magic, real streams, no
    # top-level ``__properties_version1.0``. It is a message only if that stream is there.
    data = build_cfb(
        storage(
            "Root Entry",
            stream("Subject", b"synthetic, but not a MAPI message"),
        )
    )
    refused = cfb.open_cfb(data)
    assert isinstance(refused, cfb.CfbRefusal)
    assert refused.reason == cfb.NOT_A_MESSAGE
    assert cfb.NOT_A_MESSAGE in parse.NAMED_ERROR_REASONS
    # ... and it is a *message* rule, not a CFB rule: the container itself opens cleanly.
    opened = cfb.open_cfb(data, require_properties=False)
    assert isinstance(opened, cfb.CfbFile)
    assert opened.unaccounted == 0
    # The committed boundary fixture is the same case: three plain streams, no properties.
    boundary = _fixture("msg_mini_cutoff_boundary")
    boundary_refusal = cfb.open_cfb(boundary)
    assert isinstance(boundary_refusal, cfb.CfbRefusal)
    assert boundary_refusal.reason == cfb.NOT_A_MESSAGE


def test_the_extended_difat_is_read_through_and_flagged() -> None:
    data = _fixture("msg_difat_extended")
    table = CONSTRUCTION["msg_difat_extended"]
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    # The observation behind ``msg.cfb_difat_extended`` is exposed, not recomputed.
    assert opened.extended_difat is True
    assert opened.difat_fault is None
    assert opened.difat_sectors == (114,)
    assert opened.fat_sector_ids == tuple(range(table["num_fat_sectors"]))
    assert opened.sector_count == table["sector_count"]
    assert cfb.read_stream(opened, "__substg1.0_007D001F")[1] == cfb.FAULT_OK

    # Owner decision O1: the chain is read through, and only a *broken* chain faults.
    # Point the DIFAT sector's next pointer back at itself.
    header = cfb.parse_header(data)
    body = max(cfb.sector_windows(len(data), header.sector_size) - 1, 0)
    walk = cfb.walk_difat(header, data, body_sectors=body)
    difat_sector = walk.difat_sectors[0]
    slot = (difat_sector + 1) * header.sector_size + (header.sector_size // 4 - 1) * 4
    broken = cfb_raw.patch_u32(data, slot, difat_sector)
    broken_walk = cfb.walk_difat(cfb.parse_header(broken), broken, body_sectors=body)
    assert broken_walk.extended is False
    assert broken_walk.fault == cfb.FAULT_CYCLE
    assert difat_sector == 114
