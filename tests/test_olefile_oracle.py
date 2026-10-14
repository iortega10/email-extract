"""Turn 1b.2: the ``olefile`` oracle -- the independent comparator over the fixtures.

The writer and the future reader share an author, so a third party must agree the
fixtures have the layout their construction table claims. ``olefile`` is that third
party, and ``tests/support/olefile_oracle.py`` is the only place it is imported.

Three declared tests:

* ``test_olefile_agrees_on_every_well_formed_fixture`` -- ``compare`` is empty for
  every committed fixture, on the in-memory build and on the bytes on disk;
* ``test_the_oracle_scope_excludes_hostile_mutants`` -- two hostile mutants built
  here by patching hand-typed offsets show the oracle cannot judge a hostile file,
  so it is only ever asked about the well-formed ones;
* ``test_the_oracle_records_where_it_is_lenient`` -- the two E1 leniencies
  (``docs/design/msg-architecture.md``), asserted explicitly so a future ``olefile``
  that changes them is noticed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import make_msg_fixtures  # noqa: E402

from support import cfb_raw, msg_construction, olefile_oracle  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
BOUNDARY = "msg_mini_cutoff_boundary"


def test_olefile_agrees_on_every_well_formed_fixture() -> None:
    for name in make_msg_fixtures.FIXTURE_NAMES:
        table = msg_construction.CONSTRUCTION[name]
        built = make_msg_fixtures.build_fixture(name)
        assert olefile_oracle.compare(built, table) == [], name
        on_disk = (MSG / f"{name}.msg").read_bytes()
        assert olefile_oracle.compare(on_disk, table) == [], f"{name} (committed bytes)"


def _cycle_first_sector() -> "tuple[bytes, dict]":
    """``msg_mini_cutoff_boundary`` with a self-cyclic FAT chain on ``boundary_4096``."""
    data = make_msg_fixtures.build_fixture(BOUNDARY)
    table = msg_construction.CONSTRUCTION[BOUNDARY]
    fields = cfb_raw.header(data)
    start = table["streams"]["boundary_4096"]["start"]
    offset = (fields["difat"][0] + 1) * fields["sector_size"] + 4 * start
    return cfb_raw.patch_u32(data, offset, start), table


def _size_lie_2pow40() -> "tuple[bytes, dict]":
    """``msg_mini_cutoff_boundary`` with a ``2**40`` size claim on ``boundary_4097``."""
    data = make_msg_fixtures.build_fixture(BOUNDARY)
    fields = cfb_raw.header(data)
    # boundary_4097 is the fourth directory entry (id 3) of a single-directory-sector file.
    entry = (fields["first_dir_sector"] + 1) * fields["sector_size"] + 3 * 128
    lying = cfb_raw.patch_u32(data, entry + 120, 0)  # sizeLow = 0
    return cfb_raw.patch_u32(lying, entry + 124, 0x100), msg_construction.CONSTRUCTION[BOUNDARY]


def test_the_oracle_scope_excludes_hostile_mutants() -> None:
    cyclic, table = _cycle_first_sector()
    fields = cfb_raw.header(cyclic)
    start = table["streams"]["boundary_4096"]["start"]
    raw_fat = cfb_raw.fat(cyclic, fields)
    assert raw_fat[start] == start, "the mutant's FAT entry really points at itself"
    assert olefile_oracle.compare(cyclic, table) == [], (
        "the oracle reports AGREEMENT on a cyclic chain: olefile re-reads the one sector "
        "`nb_sectors` times and returns the declared length with no signal (E1), so it "
        "cannot be asked to judge a hostile file -- that is the own reader's job (1b.3)"
    )

    lying, table = _size_lie_2pow40()
    raw_entry = cfb_raw.directory(lying, cfb_raw.header(lying), cfb_raw.fat(lying, cfb_raw.header(lying)))[3]
    assert raw_entry["size"] == 2**40, raw_entry["size"]
    assert olefile_oracle.reading(lying)["streams"]["boundary_4097"] == 0, (
        "olefile keeps only the low 32 bits of a v3 stream size, so it reports 0 for a "
        "2**40 claim rather than the declared value: it cannot report a hostile file's "
        "true size, so the oracle is scoped to well-formed fixtures only"
    )
    # The oracle is only ever applied to the well-formed fixtures: the mutants above are
    # built here and are in no construction table.
    assert set(table) and BOUNDARY in msg_construction.CONSTRUCTION


def test_the_oracle_records_where_it_is_lenient() -> None:
    """E1's two leniencies, asserted so an ``olefile`` that changes them is noticed."""
    cyclic, table = _cycle_first_sector()
    start = table["streams"]["boundary_4096"]["start"]
    # (1) A cyclic FAT chain is SILENT: no parsing issue, and the stream is returned at
    # its declared length (the one sector read `nb_sectors` times).
    assert olefile_oracle.reading(cyclic)["issues"] == [], "E1: a cycle used to be silent"
    assert len(olefile_oracle.stream_bytes(cyclic, "boundary_4096")) == 4096, (
        "E1: olefile used to clamp a cyclic chain to the declared length, silently"
    )

    lying, _ = _size_lie_2pow40()
    seen = olefile_oracle.reading(lying)
    # (2) A 2**40 size claim is CLAMPED: the high 32 bits vanish and only a recorded
    # (non-fatal) issue remains, so the reader sees size 0 rather than the declared size.
    assert seen["streams"]["boundary_4097"] == 0, "E1: the size lie used to clamp to 0"
    assert any("stream size" in str(message) for _kind, message in seen["issues"]), (
        f"E1: a size lie used to be a recorded issue, got {seen['issues']}"
    )
