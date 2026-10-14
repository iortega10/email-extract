"""Turn 1b.2: the writer output is frozen and matches its hand-typed construction table.

The writer and the future reader share an author, so these tests do not trust the
writer's own idea of the layout: they read the fixture *bytes* at their [MS-CFB]
offsets and compare them with ``tests/support/msg_construction.py``, a table typed by
hand from the format specification and the observed Outlook structure. The
``olefile`` oracle (``tests/test_olefile_oracle.py``) is the other independent side.

The six declared tests are:

* ``test_the_writer_output_is_frozen_by_sha256`` -- every fixture equals its
  ``SHA256SUMS`` line, ``--check`` exits 0, and two subprocesses under different
  ``PYTHONHASHSEED`` values rebuild the very same bytes (determinism);
* ``test_every_fixture_matches_its_construction_table`` -- the raw header fields, the
  directory entries, the sector classes and the red-black child trees;
* ``test_the_v4_file_uses_4096_byte_sectors``;
* ``test_the_mini_cutoff_trio_is_4095_4096_4097``;
* ``test_the_outlook_layout_fixture_is_typed_from_b1_b4``;
* ``test_the_writer_imports_no_reader_and_no_olefile``.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import make_msg_fixtures  # noqa: E402  (the generator is a tool, imported by path)

from support import cfb_raw, msg_construction  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
SUMS = MSG / "SHA256SUMS"
WRITER = ROOT / "tools" / "cfb_writer.py"
GENERATOR = ROOT / "tools" / "make_msg_fixtures.py"

FIXTURE_NAMES = make_msg_fixtures.FIXTURE_NAMES
ALL_FIXTURE_NAMES = make_msg_fixtures.ALL_FIXTURE_NAMES
CONSTRUCTION = msg_construction.CONSTRUCTION

# [MS-CFB] 2.6.1 object types, as this test reads them out of the directory.
STGTY_STORAGE = 1
COLOR_RED = 0
COLOR_BLACK = 1


def _sum_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        digest, _, filename = line.partition("  ")
        rows[filename] = digest
    return rows


def test_the_writer_output_is_frozen_by_sha256() -> None:
    rows = _sum_rows()
    assert set(rows) == {f"{name}.msg" for name in ALL_FIXTURE_NAMES}, sorted(rows)
    for name in ALL_FIXTURE_NAMES:
        built = make_msg_fixtures.build_fixture(name)
        on_disk = (MSG / f"{name}.msg").read_bytes()
        assert on_disk == built, f"{name}: the committed file moved from the generator's bytes"
        assert hashlib.sha256(built).hexdigest() == rows[f"{name}.msg"], name

    # The generator's own gate exits 0 against the committed tree.
    check = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_the_writer_rebuilds_the_same_bytes_under_any_hash_seed() -> None:
    # Determinism, beyond the frozen file: two fresh interpreters whose dict/str hash
    # order differs must produce byte-identical fixtures (no dict-order dependence).
    baseline = {name: hashlib.sha256(make_msg_fixtures.build_fixture(name)).hexdigest() for name in ALL_FIXTURE_NAMES}
    assert _hash_seed_run("0") == baseline
    assert _hash_seed_run("1234567") == baseline


def _hash_seed_run(seed: str) -> dict[str, str]:
    script = (
        "import hashlib, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import make_msg_fixtures as mk\n"
        "for name in mk.ALL_FIXTURE_NAMES:\n"
        "    print(name, hashlib.sha256(mk.build_fixture(name)).hexdigest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT / "tools")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {line.split()[0]: line.split()[1] for line in result.stdout.splitlines()}


def test_every_fixture_matches_its_construction_table() -> None:
    for name, table in CONSTRUCTION.items():
        data = make_msg_fixtures.build_fixture(name)
        problems = _table_problems(data, table)
        assert not problems, (name, problems)


def _table_problems(data: bytes, table) -> list[str]:
    problems: list[str] = []
    fields = cfb_raw.header(data)
    size = fields["sector_size"]

    if fields["signature"] != cfb_raw.SIGNATURE:
        problems.append("the file does not open with the [MS-CFB] 2.2 signature")
    for measured, key in (
        ("dll_version", "version"),
        ("sector_shift", "sector_shift"),
        ("mini_sector_shift", "mini_sector_shift"),
        ("mini_cutoff", "mini_cutoff"),
        ("num_fat_sectors", "num_fat_sectors"),
        ("num_dir_sectors", "num_dir_sectors"),
        ("first_dir_sector", "first_dir_sector"),
        ("num_mini_fat_sectors", "num_mini_fat_sectors"),
        ("first_mini_fat_sector", "first_mini_fat_sector"),
        ("num_difat_sectors", "num_difat_sectors"),
    ):
        if fields[measured] != table[key]:
            problems.append(f"{measured}: file={fields[measured]} table={table[key]}")

    used_difat = table["difat_used"]
    if fields["difat"][: len(used_difat)] != used_difat:
        problems.append(f"difat: file={fields['difat'][: len(used_difat)]} table={used_difat}")
    # A header whose inline DIFAT is not full must pad the rest with FREESECT; when it is
    # full (``msg_difat_extended``, whose 110th FAT id lives in an extended DIFAT sector)
    # there is no padding slot to check.
    padding = fields["difat"][len(used_difat):]
    if padding and set(padding) != {cfb_raw.FREESECT}:
        problems.append("an unused header DIFAT slot is not FREESECT")

    if len(data) != table["file_length"]:
        problems.append(f"file length: file={len(data)} table={table['file_length']}")
    if len(data) % size:
        problems.append("the file is not a whole number of sectors")
    if len(data) // size != table["sector_count"]:
        problems.append(f"sector count: file={len(data) // size} table={table['sector_count']}")

    fat = cfb_raw.fat(data, fields)
    entries = cfb_raw.directory(data, fields, fat)
    if len(entries) != table["directory_entries"]:
        problems.append(f"directory entries: file={len(entries)} table={table['directory_entries']}")
    real = entries[: len(table["directory"])]
    rows = [(entry["name"], entry["type"], entry["size"]) for entry in real]
    expected = [tuple(row) for row in table["directory"]]
    if rows != expected:
        problems.append(f"directory rows: file={rows} table={expected}")
    for entry in entries[len(table["directory"]):]:
        if entry["name"] or entry["type"] != 0:
            problems.append("a directory slot past the real entries is not an EMPTY entry")

    problems.extend(_class_problems(data, fields, fat, table))
    problems.extend(_stream_problems(data, fields, fat, entries, table))
    return problems


def _class_problems(data, fields, fat, table) -> list[str]:
    """The eight sector classes, computed from the chains, must close to the file."""
    size = fields["sector_size"]
    total = len(data) // size
    directory = set(cfb_raw.chain(fat, fields["first_dir_sector"]))
    minifat = (
        set(cfb_raw.chain(fat, fields["first_mini_fat_sector"]))
        if fields["num_mini_fat_sectors"]
        else set()
    )
    fat_sectors = set(range(fields["num_fat_sectors"]))
    streams: set[int] = set()
    for entry in cfb_raw.directory(data, fields, fat):
        if entry["type"] == cfb_raw.STGTY_STREAM and entry["size"] >= fields["mini_cutoff"]:
            streams |= set(cfb_raw.chain(fat, entry["start"]))
        if entry["type"] == cfb_raw.STGTY_ROOT and entry["size"]:
            streams |= set(cfb_raw.chain(fat, entry["start"]))
    difat = set(cfb_raw.difat_sectors(data, fields))
    free = {index for index, value in enumerate(fat) if value == cfb_raw.FREESECT} - difat

    problems: list[str] = []
    groups = {
        "difat": difat,
        "fat": fat_sectors,
        "directory": directory,
        "minifat": minifat,
        "stream": streams,
        "free": free,
    }
    seen: dict[int, str] = {}
    for label, sectors in groups.items():
        for index in sectors:
            if index in seen:
                problems.append(f"sector {index} is claimed by both {seen[index]} and {label}")
            seen[index] = label
    missing = set(range(total - 1)) - set(seen)
    if missing:
        problems.append(f"sectors {sorted(missing)} are in no class at all")

    classes = {
        "header": size,
        "difat": len(difat) * size,
        "fat": len(fat_sectors) * size,
        "minifat": len(minifat) * size,
        "directory": len(directory) * size,
        "stream": len(streams) * size,
        "free": len(free) * size,
        "slack": len(data) - total * size,
    }
    measured = [[name, classes[name]] for name in msg_construction.SECTOR_CLASSES]
    expected = [list(row) for row in table["sector_accounting"]]
    if measured != expected:
        problems.append(f"sector classes: file={measured} table={expected}")
    if sum(classes.values()) != len(data):
        problems.append(f"the eight classes sum to {sum(classes.values())}, not {len(data)}")
    return problems


def _stream_problems(data, fields, fat, entries, table) -> list[str]:
    """Every stream's chain, and every storage's red-black child tree."""
    problems: list[str] = []
    paths = _paths_by_tree(entries)
    by_path = {path: entries[index] for path, index in paths.items()}
    root = table["streams"]["<root>"]
    mini_sector_count = root["size"] // 64  # the root's stream is a whole mini-sector count
    for path, spec in table["streams"].items():
        if path == "<root>":
            continue
        entry = by_path.get(path)
        if entry is None:
            problems.append(f"{path}: not reachable in the directory tree")
            continue
        if entry["size"] != spec["size"]:
            problems.append(f"{path}: size file={entry['size']} table={spec['size']}")
        if spec["mini"]:
            if entry["start"] != spec["start"]:
                problems.append(f"{path}: mini start file={entry['start']} table={spec['start']}")
            if entry["start"] + spec["sectors"] > mini_sector_count:
                problems.append(
                    f"{path}: mini chain {entry['start']}+{spec['sectors']} past the "
                    f"{mini_sector_count}-mini-sector root stream"
                )
        else:
            chain = cfb_raw.chain(fat, entry["start"])
            expected_chain = list(range(spec["start"], spec["start"] + spec["sectors"]))
            if chain != expected_chain:
                problems.append(f"{path}: FAT chain file={chain} table={expected_chain}")
    root_entry = entries[0]
    if root_entry["start"] != root["start"] or root_entry["size"] != root["size"]:
        problems.append(f"<root>: start/size file={root_entry['start']}/{root_entry['size']} table={root['start']}/{root['size']}")
    problems.extend(_red_black_problems(entries))
    return problems


def _paths_by_tree(entries) -> dict[str, int]:
    """``{path: directory id}``, walking the child/left/right pointers from the root.

    The root entry ("Root Entry") is the storage the walk starts from, not a path
    component, so a top-level child is keyed by its bare name.
    """
    out: dict[str, int] = {}

    def walk(node_id: int, prefix: list[str]) -> None:
        if node_id == cfb_raw.NOSTREAM:
            return
        entry = entries[node_id]
        walk(entry["left"], prefix)
        path = prefix + [entry["name"]]
        out["/".join(path)] = node_id
        walk(entry["child"], path)
        walk(entry["right"], prefix)

    walk(entries[0]["child"], [])
    return out


def _red_black_problems(entries) -> list[str]:
    """[MS-CFB] 2.6.4: every storage's child tree is ordered and properly coloured."""
    problems: list[str] = []
    reached: set[int] = set()

    def check(storage_id: int, label: str) -> None:
        root_id = entries[storage_id]["child"]
        if root_id == cfb_raw.NOSTREAM:
            return
        nodes: set[int] = set()

        def collect(node_id: int) -> None:
            if node_id == cfb_raw.NOSTREAM or node_id in nodes:
                if node_id != cfb_raw.NOSTREAM:
                    problems.append(f"{label}: directory id {node_id} is reached twice")
                return
            if node_id >= len(entries):
                problems.append(f"{label}: the child tree points past the directory ({node_id})")
                return
            nodes.add(node_id)
            collect(entries[node_id]["left"])
            collect(entries[node_id]["right"])

        collect(root_id)
        order: list[int] = []

        def inorder(node_id: int) -> None:
            if node_id == cfb_raw.NOSTREAM:
                return
            inorder(entries[node_id]["left"])
            order.append(node_id)
            inorder(entries[node_id]["right"])

        inorder(root_id)
        keys = [(len(entries[i]["name"]), entries[i]["name"].upper()) for i in order]
        if keys != sorted(keys):
            problems.append(f"{label}: the child tree is not ordered by (length, name)")
        if entries[root_id]["colour"] != COLOR_BLACK:
            problems.append(f"{label}: the child tree's root is not black")
        problems.extend(_black_height_problems(root_id, entries, set()))
        for node_id in order:
            reached.add(node_id)
            if entries[node_id]["type"] == STGTY_STORAGE:
                check(node_id, f"{label}/{entries[node_id]['name']}")

    check(0, "Root Entry")
    for index in range(1, len(entries)):
        if entries[index]["name"] and index not in reached:
            problems.append(f"directory id {index} ({entries[index]['name']!r}) is unreachable")
    return problems


def _black_height_problems(node_id: int, entries, seen: set[int]) -> list[str]:
    """A red node has no red child, and every path carries the same black count."""
    if node_id == cfb_raw.NOSTREAM:
        return []
    if node_id in seen:
        return [f"a cycle in the child tree at directory id {node_id}"]
    seen.add(node_id)
    entry = entries[node_id]
    problems: list[str] = []
    if entry["colour"] == COLOR_RED:
        for child in (entry["left"], entry["right"]):
            if child != cfb_raw.NOSTREAM and entries[child]["colour"] == COLOR_RED:
                problems.append(f"directory id {node_id} is red and has a red child")
    left_height = _black_height(entry["left"], entries)
    right_height = _black_height(entry["right"], entries)
    if left_height != right_height:
        problems.append(
            f"directory id {node_id}: black height {left_height} on the left, {right_height} on the right"
        )
    problems.extend(_black_height_problems(entry["left"], entries, seen))
    problems.extend(_black_height_problems(entry["right"], entries, seen))
    return problems


def _black_height(node_id: int, entries) -> int:
    if node_id == cfb_raw.NOSTREAM:
        return 0
    return _black_height(entries[node_id]["left"], entries) + (
        0 if entries[node_id]["colour"] == COLOR_RED else 1
    )


def test_the_v4_file_uses_4096_byte_sectors() -> None:
    data = make_msg_fixtures.build_fixture("msg_v4_sectors")
    fields = cfb_raw.header(data)
    assert fields["dll_version"] == 4
    assert fields["sector_shift"] == 12
    assert fields["sector_size"] == 4096
    assert fields["num_dir_sectors"] == 1, "a v4 file sets the directory-sector count"
    # [MS-CFB] 2.2: the 512-byte header is zero-padded to a whole 4096-byte sector.
    assert data[:8] == cfb_raw.SIGNATURE
    assert data[76 + 436 : 4096] == b"\x00" * (4096 - 512)
    # The FAT slot for sector 0 (the first FAT sector) is FATSECT, and the file is
    # exactly five sectors long.
    assert len(data) == 5 * 4096
    assert CONSTRUCTION["msg_v4_sectors"]["sector_size"] == 4096
    assert CONSTRUCTION["msg_v4_sectors"]["version"] == 4


def test_the_mini_cutoff_trio_is_4095_4096_4097() -> None:
    """4095 lives in the mini stream; 4096 and 4097 come from the FAT."""
    from support import olefile_oracle

    data = make_msg_fixtures.build_fixture("msg_mini_cutoff_boundary")
    fields = cfb_raw.header(data)
    cutoff = fields["mini_cutoff"]
    assert cutoff == 4096

    fat = cfb_raw.fat(data, fields)
    entries = {entry["name"]: entry for entry in cfb_raw.directory(data, fields, fat)}
    mini = olefile_oracle.mini_flags(data)
    for name, size, on_mini in (
        ("boundary_4095", 4095, True),
        ("boundary_4096", 4096, False),
        ("boundary_4097", 4097, False),
    ):
        assert entries[name]["size"] == size
        assert (size < cutoff) is on_mini
        assert mini[name] is on_mini, f"{name} is on the wrong side of the {cutoff}-byte cutoff"

    # The hand-typed chain lists: 4095's mini sector chain and the two FAT chains.
    table = CONSTRUCTION["msg_mini_cutoff_boundary"]["streams"]
    for name in ("boundary_4095", "boundary_4096", "boundary_4097"):
        spec = table[name]
        assert entries[name]["start"] == spec["start"], name
        assert entries[name]["size"] == spec["size"], name
    assert cfb_raw.chain(fat, entries["boundary_4097"]["start"]) == list(range(11, 20))
    assert cfb_raw.chain(fat, entries["boundary_4096"]["start"]) == list(range(20, 28))
    assert entries["boundary_4095"]["start"] == 0  # the first mini sector


def test_the_outlook_layout_fixture_is_typed_from_b1_b4() -> None:
    """Every number traces to an ``email-spike.md`` B1-B4 row, not to the writer."""
    from support import olefile_oracle

    data = make_msg_fixtures.build_fixture("msg_outlook_layout_handbuilt")
    fields = cfb_raw.header(data)
    assert (fields["dll_version"], fields["sector_size"]) == (3, 512)
    assert fields["mini_sector_shift"] == 6  # 64-byte mini sectors
    assert fields["mini_cutoff"] == 4096

    tree = _paths_by_tree(cfb_raw.directory(data, fields, cfb_raw.fat(data, fields)))
    storages = {path for path in tree if path.count("/") == 0}
    # B1: the top-level children are the properties table, __nameid_version1.0, the
    # __substg1.0_* data streams, one recipient and one attachment storage.
    assert "__properties_version1.0" in storages
    assert "__nameid_version1.0" in storages
    assert "__recip_version1.0_#00000000" in storages
    assert "__attach_version1.0_#00000000" in storages
    recipients = [p for p in storages if p.startswith("__recip_version1.0_")]
    attachments = [p for p in storages if p.startswith("__attach_version1.0_")]
    assert len(recipients) == 1 and len(attachments) == 1

    sizes = olefile_oracle.stream_sizes(data)
    # B1: __nameid_version1.0 holds three binary streams of 160/440/3090 bytes.
    for suffix, expected in (("00020102", 160), ("00030102", 440), ("00040102", 3090)):
        assert sizes[f"__nameid_version1.0/__substg1.0_{suffix}"] == expected

    # B2: the top-level __properties_version1.0 is a 32-byte header plus 16 per entry.
    # Turn 1b.4 gives it three entries: the two fixed code pages and 0x001A (the class).
    properties = sizes["__properties_version1.0"]
    assert properties == 32 + 3 * 16
    blob = olefile_oracle.stream_bytes(data, "__properties_version1.0")
    assert int.from_bytes(blob[16:20], "little") == 1  # recipient count @16
    assert int.from_bytes(blob[20:24], "little") == 1  # attachment count @20

    # B4: 0x3FDE / 0x3FFD are fixed entries in the table, never streams. A property
    # entry is (propType, propId) as two little-endian words, so the tag is at +2.
    tags = {
        int.from_bytes(blob[offset + 2 : offset + 4], "little")
        for offset in range(32, properties, 16)
    }
    assert {0x3FDE, 0x3FFD, 0x001A} <= tags
    assert not any("3FDE" in path.upper() or "3FFD" in path.upper() for path in sizes)

    # B3: the recipient table uses the observed typing -- 0C15 type, 3001 display name,
    # 3002 address type, 3003 email address -- and its three streams are present.
    recipient_blob = olefile_oracle.stream_bytes(
        data, "__recip_version1.0_#00000000/__properties_version1.0"
    )
    tags_seen = {
        int.from_bytes(recipient_blob[offset + 2 : offset + 4], "little")
        for offset in range(8, len(recipient_blob), 16)
    }
    assert {0x0C15, 0x3001, 0x3002, 0x3003} <= tags_seen
    for suffix in ("3001001F", "3002001F", "3003001F"):
        assert f"__recip_version1.0_#00000000/__substg1.0_{suffix}" in sizes

    # B1: the one attachment holds a by-value file (3701:0102) and a 3707:001F name.
    assert "__attach_version1.0_#00000000/__substg1.0_37010102" in sizes
    assert "__attach_version1.0_#00000000/__substg1.0_3707001F" in sizes


def test_the_writer_imports_no_reader_and_no_olefile() -> None:
    tree = ast.parse(WRITER.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "olefile" not in imported, sorted(imported)
    assert "emailextract" not in imported, sorted(imported)

    # A fresh interpreter that blocks both the package and the oracle still builds a
    # container: the writer is loadable and usable with neither present.
    script = (
        "import importlib.abc, sys\n"
        "BLOCKED = {'olefile', 'emailextract'}\n"
        "class Blocker(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in BLOCKED:\n"
        "            raise ImportError('blocked: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import cfb_writer\n"
        "data = cfb_writer.build_cfb(cfb_writer.storage('Root Entry', cfb_writer.stream('s', b'x')))\n"
        "assert data[:8] == cfb_writer.SIGNATURE\n"
        "print(len(data))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT / "tools")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_real_message_enters_the_repository() -> None:
    """Build-spec rule 1: real mail never enters the repo -- a listing check, not policy.

    ``fixtures/real/`` is where the owner's machine-local samples would live; it is
    git-ignored, so it must be absent or empty. The only committed ``.msg`` files are the
    five this turn generated under ``fixtures/msg/``.
    """
    real = ROOT / "fixtures" / "real"
    if real.exists():
        assert [path.name for path in real.iterdir()] == [], (
            "fixtures/real/ holds files; real email must never enter the repository"
        )
    committed = sorted(
        path.relative_to(ROOT / "fixtures").as_posix()
        for path in (ROOT / "fixtures").rglob("*.msg")
    )
    assert committed == sorted(f"msg/{name}.msg" for name in ALL_FIXTURE_NAMES), committed
