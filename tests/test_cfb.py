"""Turn 1b.3: ``emailextract.cfb`` opens the committed fixtures and reports what they hold.

The reader and the writer share an author, so these tests do not take the reader's word:
the header, the DIFAT/FAT/miniFAT tables, the directory and every stream are compared with
``tests/support/msg_construction.py`` (typed by hand from [MS-CFB]) and with
``tests/support/olefile_oracle.py`` (the independent third party). Where structure is
random, ``tests/test_cfb_fuzz.py`` covers it.

The declared tests are:

* ``test_parse_header_reads_v3_and_v4`` -- the version, the sector/mini sizes, the fixed
  mini cutoff and the DIFAT counts, on a v3 and a v4 file, and a refusal on anything else;
* ``test_walk_difat_and_read_fat`` -- the inline DIFAT, the extended chain and the FAT,
  against ``cfb_raw``'s raw reading;
* ``test_read_minifat_and_the_cutoff`` -- 4095 / 4096 / 4097 bytes land on the side of the
  mini-stream cutoff the construction table says;
* ``test_walk_directory_and_case_insensitive_lookup`` -- every entry, and [MS-CFB] 2.6.4
  case-insensitive lookup by posix path;
* ``test_read_stream_returns_bytes_and_fault`` -- ``(bytes, fault)`` for both stream kinds
  and a closed fault for a missing path;
* ``test_read_stream_never_raises`` -- every fixture, every seed and every cut length of one
  fixture return ``(bytes, closed fault)`` or a closed refusal, never an exception;
* ``test_classify_sectors_assigns_every_sector`` -- the eight classes (plus ``unaccounted``)
  sum to the file length on every fixture;
* ``test_check_caps_reports_the_three_cfb_caps`` -- both sides of each cap boundary.

Two checks beyond the declaration:

* ``test_the_cfb_reader_and_olefile_agree_on_every_well_formed_fixture`` -- the cross-check
  of Turn 1b.3 (C): the package's reader and ``olefile`` agree on every well-formed fixture;
* ``test_the_cfb_vocabulary_matches_the_walk_and_parse_contract`` -- the cap ids equal
  ``walk.CFB_CAP_REASONS``, the named reasons are in ``parse.NAMED_ERROR_REASONS``, and
  ``cfb.py`` is a leaf (stdlib imports only, no ``olefile`` at import time).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import make_msg_fixtures  # noqa: E402

from emailextract import cfb  # noqa: E402
from support import cfb_raw, msg_construction, olefile_oracle  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
CFB_PATH = ROOT / "emailextract" / "cfb.py"
CONSTRUCTION = msg_construction.CONSTRUCTION
BOUNDARY = "msg_mini_cutoff_boundary"


def _fixture(name: str) -> bytes:
    return make_msg_fixtures.build_fixture(name)


def _layout(data: bytes) -> "tuple[cfb.CfbHeader, int]":
    """The parsed header and the body sector count (everything but the header's window)."""
    header = cfb.parse_header(data)
    return header, max(cfb.sector_windows(len(data), header.sector_size) - 1, 0)


def test_parse_header_reads_v3_and_v4() -> None:
    v3 = _fixture("msg_headers_only")
    header = cfb.parse_header(v3)
    table = CONSTRUCTION["msg_headers_only"]
    assert isinstance(header, cfb.CfbHeader)
    assert header.version == 3 and header.sector_shift == 9
    assert header.sector_size == 512 and header.mini_sector_size == 64
    assert header.mini_cutoff == cfb.MINI_CUTOFF == 4096
    for measured, key in (
        (header.num_fat_sectors, "num_fat_sectors"),
        (header.num_dir_sectors, "num_dir_sectors"),
        (header.first_dir_sector, "first_dir_sector"),
        (header.num_mini_fat_sectors, "num_mini_fat_sectors"),
        (header.first_mini_fat_sector, "first_mini_fat_sector"),
        (header.num_difat_sectors, "num_difat_sectors"),
    ):
        assert measured == table[key], key
    assert list(header.difat[: len(table["difat_used"])]) == table["difat_used"]
    assert set(header.difat[len(table["difat_used"]):]) == {cfb.FREESECT}

    v4 = cfb.parse_header(_fixture("msg_v4_sectors"))
    v4table = CONSTRUCTION["msg_v4_sectors"]
    assert v4.version == 4 and v4.sector_shift == 12 and v4.sector_size == 4096
    assert v4.byte_order == 0xFFFE and v4.mini_sector_shift == 6 and v4.mini_cutoff == 4096
    assert v4.num_dir_sectors == v4table["num_dir_sectors"] == 1

    # Anything else is refused, never guessed: too short, no signature, a bad shift.
    for broken, needle in (
        (v3[:200], "shorter than a CFB header"),
        (b"x" * 512, "no CFB signature"),
        (cfb_raw.patch_u32(v3, 26, 13), "sector shift 13 is not one of"),
    ):
        refused = cfb.parse_header(broken)
        assert isinstance(refused, cfb.CfbRefusal), needle
        assert refused.reason == cfb.CFB_HEADER_UNSUPPORTED, needle


def test_walk_difat_and_read_fat() -> None:
    data = _fixture("msg_headers_only")
    header, body = _layout(data)
    walk = cfb.walk_difat(header, data, body_sectors=body)
    assert isinstance(walk, cfb.DifatWalk)
    assert walk.extended is False and walk.fault is None
    assert walk.difat_sectors == ()
    assert walk.fat_sector_ids == tuple(CONSTRUCTION["msg_headers_only"]["difat_used"])
    fat = cfb.read_fat(data, header, walk.fat_sector_ids, body_sectors=body)
    assert fat == tuple(cfb_raw.fat(data, cfb_raw.header(data)))

    # The extended chain: the 110th FAT id lives in a DIFAT sector, and the walk finds it.
    ext = _fixture("msg_difat_extended")
    eheader, ebody = _layout(ext)
    ewalk = cfb.walk_difat(eheader, ext, body_sectors=ebody)
    assert ewalk.extended is True and ewalk.fault is None
    assert ewalk.difat_sectors == (114,)
    assert ewalk.fat_sector_ids == tuple(range(110))
    efat = cfb.read_fat(ext, eheader, ewalk.fat_sector_ids, body_sectors=ebody)
    assert efat == tuple(cfb_raw.fat(ext, cfb_raw.header(ext)))
    assert efat[110] == cfb.ENDOFCHAIN  # the directory's own slot


def test_read_minifat_and_the_cutoff() -> None:
    data = _fixture(BOUNDARY)
    header = cfb.parse_header(data)
    opened = cfb.open_cfb(data, require_properties=False)
    assert isinstance(opened, cfb.CfbFile)
    streams = {stream.path: stream for stream in opened.streams}
    table = CONSTRUCTION[BOUNDARY]["streams"]
    for name, spec in table.items():
        if name == "<root>":
            continue
        stream = streams[name]
        assert stream.mini is (spec["size"] < opened.mini_cutoff), name
        payload, fault = cfb.read_stream(opened, name)
        assert fault == cfb.FAULT_OK and len(payload) == spec["size"], name

    # 4095 is addressed through the miniFAT; 4096 and 4097 through the FAT.
    assert streams["boundary_4095"].mini is True
    assert streams["boundary_4096"].mini is False
    assert streams["boundary_4097"].mini is False

    # The miniFAT chains the 4095 stream's 64 mini sectors.
    minifat = cfb.read_minifat(data, header, body_sectors=max(len(data) // 512 - 1, 0))
    assert minifat == tuple(cfb.read_minifat(data, header))
    walk = cfb.chain_sectors(minifat, table["boundary_4095"]["start"], 64)
    assert walk.fault == cfb.FAULT_OK
    assert walk.sectors == tuple(range(table["boundary_4095"]["sectors"]))


def test_walk_directory_and_case_insensitive_lookup() -> None:
    data = _fixture("msg_outlook_layout_handbuilt")
    header, body = _layout(data)
    fat = cfb.read_fat(
        data, header, cfb.walk_difat(header, data, body_sectors=body).fat_sector_ids, body_sectors=body
    )
    walk = cfb.walk_directory(data, header, fat, body_sectors=body)
    assert isinstance(walk, cfb.DirectoryWalk)
    table = CONSTRUCTION["msg_outlook_layout_handbuilt"]
    rows = [
        (entry.name, entry.entry_type, entry.size)
        for entry in walk.entries
        if entry.entry_type != cfb.STGTY_EMPTY
    ]
    assert rows == [tuple(row) for row in table["directory"]]
    assert walk.directory_entries == table["directory_entries"]

    entries = walk.entries
    exact = cfb.lookup_entry(entries, "__substg1.0_007D001F")
    assert exact is not None and exact.size == 518
    # [MS-CFB] 2.6.4: the comparison is by uppercased name, so case does not matter.
    assert cfb.lookup_entry(entries, "__SUBSTG1.0_007d001f") is not None
    nested = cfb.lookup_entry(entries, "__NAMEID_version1.0/__SUBSTG1.0_00020102")
    assert nested is not None and nested.path.endswith("__substg1.0_00020102")
    assert nested.start == 2 and nested.size == 160
    # A wrong length does not match, and an absent path is ``None``.
    assert cfb.lookup_entry(entries, "__substg1.0_007D00") is None
    assert cfb.lookup_entry(entries, "no/such/stream") is None


def test_read_stream_returns_bytes_and_fault() -> None:
    data = _fixture("msg_headers_only")
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    table = CONSTRUCTION["msg_headers_only"]["streams"]

    payload, fault = cfb.read_stream(opened, "__properties_version1.0")
    assert fault == cfb.FAULT_OK and len(payload) == table["__properties_version1.0"]["size"]
    root_payload, root_fault = cfb.read_stream(opened, "<root>")
    assert root_fault == cfb.FAULT_OK and len(root_payload) == table["<root>"]["size"]
    # An entry object reads the same as its path.
    entry = cfb.lookup_entry(opened.entries, "__substg1.0_007D001F")
    assert cfb.read_stream(opened, entry) == cfb.read_stream(opened, "__substg1.0_007D001F")
    # A missing path is an empty stream with a closed fault, not an exception.
    assert cfb.read_stream(opened, "nope") == (b"", cfb.FAULT_OUT_OF_RANGE)
    # Every fault in the table is a member of the closed vocabulary.
    assert set(cfb.FAULT_REASON_IDS) <= set(cfb.FAULT_KINDS)
    assert cfb.FAULT_STATUS == "TRUNCATED"


def test_read_stream_never_raises() -> None:
    # Every committed fixture and every test-only seed.
    samples = [(name, _fixture(name)) for name in make_msg_fixtures.ALL_FIXTURE_NAMES]
    samples += list(_seeds().items())
    for name, data in samples:
        _read_every_stream(name, data)
    # ... and every cut length of one fixture, from 0 to its full size.
    base = _fixture("msg_headers_only")
    for cut in range(len(base) + 1):
        _read_every_stream(f"msg_headers_only[:{cut}]", base[:cut])


def _read_every_stream(name: str, data: bytes) -> None:
    """Open ``data`` and read every stream; nothing may raise and every result is closed."""
    opened = cfb.open_cfb(data, require_properties=False)
    if isinstance(opened, cfb.CfbRefusal):
        assert opened.reason in cfb.CFB_REFUSAL_REASONS, (name, opened.reason)
        return
    assert opened.unaccounted >= 0, name
    for stream in opened.streams:
        payload, fault = cfb.read_stream(opened, stream.path)
        assert isinstance(payload, bytes), (name, stream.path)
        assert fault in cfb.FAULT_KINDS, (name, stream.path, fault)


def _seeds() -> "dict[str, bytes]":
    """The test-only seeds from ``docs/design/phase1b-fixtures.md`` (never committed).

    Each is built from a fixture by patching one hand-typed field; the offsets come from
    ``cfb_raw.header`` so the seed says *what* it lies about, not where the field is.
    """
    boundary = _fixture(BOUNDARY)
    fields = cfb_raw.header(boundary)
    first = (fields["first_dir_sector"] + 1) * fields["sector_size"]
    entry = first + 3 * 128  # boundary_4097 is directory entry 3.
    lie_2pow40 = cfb_raw.patch_u32(boundary, entry + 120, 0)
    lie_2pow40 = cfb_raw.patch_u32(lie_2pow40, entry + 124, 0x100)
    lie_ffff = cfb_raw.patch_u32(boundary, entry + 120, 0xFFFFFFFF)
    lie_ffff = cfb_raw.patch_u32(lie_ffff, entry + 124, 0xFFFFFFFF)
    root_self = cfb_raw.patch_u32(boundary, first + 68, 0)  # the root's left link -> the root
    return {
        "seed_size_lie_2pow40": lie_2pow40,
        "seed_size_lie_ffffffff": lie_ffff,
        "seed_root_self_reference": root_self,
    }


def test_classify_sectors_assigns_every_sector() -> None:
    for name in make_msg_fixtures.ALL_FIXTURE_NAMES:
        data = _fixture(name)
        opened = cfb.open_cfb(data, require_properties=False)
        if isinstance(opened, cfb.CfbRefusal):
            assert opened.reason in cfb.CFB_REFUSAL_REASONS, name
            continue
        assert [name_ for name_, _ in opened.accounting] == list(cfb.SECTOR_CLASSES)
        total = sum(bytes_ for _, bytes_ in opened.accounting) + opened.unaccounted
        assert total == len(data), (name, total, len(data))
        if opened.unaccounted == 0:
            assert sum(bytes_ for _, bytes_ in opened.accounting) == len(data), name
        # No sector is counted twice: the classes partition the windows.
        assert len(opened.accounting_map()) == len(cfb.SECTOR_CLASSES), name


def test_check_caps_reports_the_three_cfb_caps() -> None:
    limits = cfb.CfbLimits(max_sector_count=10, max_directory_entries=4, max_difat_chain_length=2)
    # The cap itself is legal; one past it is a hit carrying both numbers.
    assert cfb.check_caps(limits, sector_count=10) == ()
    sector = cfb.check_caps(limits, sector_count=11)
    assert len(sector) == 1
    assert sector[0] == cfb.CapObservation(cfb.CFB_CAP_SECTOR_COUNT, 10, 11)
    assert cfb.check_caps(limits, directory_entries=4) == ()
    assert cfb.check_caps(limits, directory_entries=5)[0].cap_id == cfb.CFB_CAP_DIRECTORY_ENTRIES
    assert cfb.check_caps(limits, difat_chain_length=2) == ()
    assert cfb.check_caps(limits, difat_chain_length=3)[0].cap_id == cfb.CFB_CAP_DIFAT_CHAIN_LENGTH
    # A measure left out is not measured, and the order is ``CFB_CAP_IDS``.
    assert cfb.check_caps(limits, sector_count=11, directory_entries=5, difat_chain_length=3) == (
        cfb.CapObservation(cfb.CFB_CAP_SECTOR_COUNT, 10, 11),
        cfb.CapObservation(cfb.CFB_CAP_DIRECTORY_ENTRIES, 4, 5),
        cfb.CapObservation(cfb.CFB_CAP_DIFAT_CHAIN_LENGTH, 2, 3),
    )

    # A real hit refuses at the boundary, before the structure it guards is walked.
    small = _fixture("msg_headers_only")
    refused = cfb.open_cfb(small, limits=cfb.CfbLimits(max_sector_count=3))
    assert isinstance(refused, cfb.CfbRefusal) and refused.reason == cfb.CFB_CAP_SECTOR_COUNT
    assert refused.observation.observed == cfb.sector_windows(len(small), 512) == 6

    v4 = _fixture("msg_v4_sectors")
    entries = cfb.open_cfb(v4, limits=cfb.CfbLimits(max_directory_entries=16))
    assert isinstance(entries, cfb.CfbRefusal)
    assert entries.reason == cfb.CFB_CAP_DIRECTORY_ENTRIES

    ext = _fixture("msg_difat_extended")
    chain = cfb.open_cfb(ext, limits=cfb.CfbLimits(max_difat_chain_length=0))
    assert isinstance(chain, cfb.CfbRefusal)
    assert chain.reason == cfb.CFB_CAP_DIFAT_CHAIN_LENGTH


def test_the_cfb_reader_and_olefile_agree_on_every_well_formed_fixture() -> None:
    for name in make_msg_fixtures.FIXTURE_NAMES:
        built = _fixture(name)
        opened = cfb.open_cfb(built, require_properties=False)
        assert isinstance(opened, cfb.CfbFile), name
        assert olefile_oracle.cross_check(built, opened) == [], name
        on_disk = (MSG / f"{name}.msg").read_bytes()
        assert olefile_oracle.cross_check(
            on_disk, cfb.open_cfb(on_disk, require_properties=False)
        ) == [], f"{name} (committed bytes)"


def _top_level_imports(path: Path) -> "set[str]":
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("<relative>" if node.level else (node.module or "").split(".")[0])
    return names


def test_the_cfb_vocabulary_matches_the_walk_and_parse_contract() -> None:
    from emailextract import parse, walk

    # The cap ids are the walker's CFB cap reasons, and the refusal names are members of
    # the closed named-error vocabulary (or the cap vocabulary).
    assert cfb.CFB_CAP_IDS == tuple(walk.CFB_CAP_REASONS)
    assert set(cfb.CFB_REFUSAL_REASONS) <= set(parse.NAMED_ERROR_REASONS) | set(cfb.CFB_CAP_IDS)
    for reason in (cfb.CFB_HEADER_UNSUPPORTED, cfb.CFB_DIRECTORY_LOOP, cfb.NOT_A_MESSAGE):
        assert reason in parse.NAMED_ERROR_REASONS, reason
    assert {cfb.FAULT_CYCLE, cfb.FAULT_OUT_OF_RANGE, cfb.FAULT_SHORT_CHAIN} <= set(cfb.FAULT_KINDS)

    # ``cfb.py`` is a leaf: its own imports are stdlib only ...
    assert _top_level_imports(CFB_PATH) <= {"__future__", "struct", "dataclasses", "typing"}
    # ... so a fresh interpreter that loads the module pulls in nothing else. (Importing
    # the *package* would run ``emailextract/__init__.py``, which imports ``model``/``walk``
    # by design -- the leaf claim is about this module, so it is loaded by path.)
    script = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('cfb_under_test', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['cfb_under_test'] = module\n"
        "spec.loader.exec_module(module)\n"
        "print(sorted(m for m in sys.modules if m == 'olefile' or m.startswith('emailextract')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(CFB_PATH)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "[]", result.stdout
