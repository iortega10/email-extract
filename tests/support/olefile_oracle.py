"""Turn 1b.2/1b.3: the ``olefile`` oracle over the well-formed ``.msg`` fixtures.

``olefile`` is the independent comparator build spec rule 3 asks for -- the writer and
the package's future reader share an author, so a third party must agree the fixtures
have the layout their construction table claims. This module is **the only place
``olefile`` is imported**; nothing under ``emailextract/`` or in
``tools/cfb_writer.py`` may reach it.

Scope is **well-formed fixtures only**. E1 (``docs/design/msg-architecture.md``) measured
that ``olefile`` is silent on a cyclic FAT chain (it re-reads one sector and returns the
declared length) and clamps a ``2**40`` size claim, so it cannot judge a hostile mutant;
the package's own reader (Turn 1b.3) is the contract for those, not this oracle.

``compare(file_bytes, expectation)`` returns the disagreements (an empty list is
agreement) between ``olefile``'s reading and one construction table from
``tests/support/msg_construction.py``: the version, sector and mini sizes, the
directory entry count, every stream's path and size, whether each stream chose the
mini stream or the FAT, the directory's entries by id, and the root's mini stream size.

``cross_check(file_bytes, cfb_file)`` (Turn 1b.3) is the same view with the package's own
reader in the table's place: it compares ``emailextract.cfb``'s reading of a well-formed
container against ``olefile``'s, so the two readers must agree on the layout numbers, on
every stream's path, size and **bytes**, and on the directory's entries.
"""

from __future__ import annotations

import io
from typing import Any, Mapping

import olefile

__all__ = [
    "compare",
    "cross_check",
    "directory_rows",
    "mini_flags",
    "open_file",
    "reading",
    "stream_bytes",
    "stream_sizes",
]

STGTY_STORAGE = 1
STGTY_STREAM = 2  # [MS-CFB] 2.6.1 object type 2.
COLOR_RED = 0
COLOR_BLACK = 1
NOSTREAM = 0xFFFFFFFF


def open_file(file_bytes: bytes) -> "olefile.OleFileIO":
    """``olefile``'s handle over an in-memory container (the caller closes it)."""
    return olefile.OleFileIO(io.BytesIO(file_bytes))


def _tree(ole: "olefile.OleFileIO") -> dict[str, Any]:
    """Every entry under the root, keyed by its posix path."""
    entries: dict[str, Any] = {}

    def walk(node: Any, prefix: list[str]) -> None:
        for kid in node.kids:
            path = prefix + [kid.name]
            entries["/".join(path)] = kid
            walk(kid, path)

    walk(ole.root, [])
    return entries


def stream_sizes(file_bytes: bytes) -> dict[str, int]:
    """Every stream's path and declared size, as ``olefile`` reads them."""
    ole = open_file(file_bytes)
    return {path: entry.size for path, entry in _tree(ole).items() if entry.entry_type == STGTY_STREAM}


def mini_flags(file_bytes: bytes) -> dict[str, bool]:
    """Whether each stream is addressed through the mini stream (size < 4096)."""
    ole = open_file(file_bytes)
    return {path: entry.is_minifat for path, entry in _tree(ole).items() if entry.entry_type == STGTY_STREAM}


def stream_bytes(file_bytes: bytes, path: str) -> bytes:
    """The bytes ``olefile`` returns for one stream."""
    ole = open_file(file_bytes)
    return ole.openstream(path).read()


def directory_rows(file_bytes: bytes) -> list[tuple[str, int, int]]:
    """``(name, object type, size)`` for every loaded directory entry, by id."""
    ole = open_file(file_bytes)
    return [
        (entry.name, entry.entry_type, entry.size)
        for entry in ole.direntries
        if entry is not None
    ]


def reading(file_bytes: bytes) -> Mapping[str, Any]:
    """``olefile``'s whole reading of one container, for a test to inspect directly."""
    ole = open_file(file_bytes)
    entries = _tree(ole)
    return {
        "version": ole.dll_version,
        "sector_size": ole.sector_size,
        "mini_sector_size": ole.mini_sector_size,
        "mini_cutoff": ole.mini_stream_cutoff_size,
        "directory_entries": len(ole.direntries),
        "fat_length": len(ole.fat),
        "streams": {p: e.size for p, e in entries.items() if e.entry_type == STGTY_STREAM},
        "mini": {p: e.is_minifat for p, e in entries.items() if e.entry_type == STGTY_STREAM},
        "directory": [
            (e.name, e.entry_type, e.size) for e in ole.direntries if e is not None
        ],
        "root_size": ole.root.size,
        "issues": list(ole.parsing_issues),
    }


def _child_tree_problems(ole: "olefile.OleFileIO") -> list[str]:
    """[MS-CFB] 2.6.4: every storage's child tree is ordered and properly coloured.

    ``olefile`` never checks the tree (it re-walks the left/right pointers and re-sorts
    the kids), so a wrong colour or a broken order is invisible to a plain read -- this
    is the oracle's "directory shape" check, read from ``olefile``'s own entry objects.
    """
    problems: list[str] = []

    def check(storage: Any, label: str) -> None:
        root_id = storage.sid_child
        if root_id == NOSTREAM:
            return
        nodes: set[int] = set()

        def collect(node_id: int) -> None:
            if node_id == NOSTREAM:
                return
            if node_id in nodes:
                problems.append(f"{label}: directory id {node_id} is reached twice")
                return
            nodes.add(node_id)
            entry = ole.direntries[node_id]
            collect(entry.sid_left)
            collect(entry.sid_right)

        collect(root_id)
        names: list[str] = []

        def inorder(node_id: int) -> None:
            if node_id == NOSTREAM:
                return
            entry = ole.direntries[node_id]
            inorder(entry.sid_left)
            names.append(entry.name)
            inorder(entry.sid_right)

        inorder(root_id)
        if names != sorted(names, key=lambda name: (len(name), name.upper())):
            problems.append(f"{label}: the child tree is not ordered by (length, name)")
        if ole.direntries[root_id].color != COLOR_BLACK:
            problems.append(f"{label}: the child tree's root is not black")
        problems.extend(_colour_problems(ole, root_id, set()))
        for entry in (ole.direntries[node_id] for node_id in nodes):
            if entry.entry_type == STGTY_STORAGE:
                check(entry, f"{label}/{entry.name}")

    check(ole.root, "Root Entry")
    return problems


def _colour_problems(ole: "olefile.OleFileIO", node_id: int, seen: set[int]) -> list[str]:
    if node_id == NOSTREAM:
        return []
    if node_id in seen:
        return [f"a cycle in the child tree at directory id {node_id}"]
    seen.add(node_id)
    entry = ole.direntries[node_id]
    problems: list[str] = []
    if entry.color == COLOR_RED:
        for child in (entry.sid_left, entry.sid_right):
            if child != NOSTREAM and ole.direntries[child].color == COLOR_RED:
                problems.append(f"directory id {node_id} is red and has a red child")
    left = _black_height(ole, entry.sid_left)
    right = _black_height(ole, entry.sid_right)
    if left != right:
        problems.append(f"directory id {node_id}: black height {left} vs {right}")
    problems.extend(_colour_problems(ole, entry.sid_left, seen))
    problems.extend(_colour_problems(ole, entry.sid_right, seen))
    return problems


def _black_height(ole: "olefile.OleFileIO", node_id: int) -> int:
    if node_id == NOSTREAM:
        return 0
    entry = ole.direntries[node_id]
    return _black_height(ole, entry.sid_left) + (0 if entry.color == COLOR_RED else 1)


def compare(file_bytes: bytes, expectation: Mapping[str, Any]) -> list[str]:
    """Every disagreement between ``olefile``'s reading and one construction table."""
    ole = open_file(file_bytes)
    seen = reading(file_bytes)
    problems: list[str] = []
    problems.extend(_child_tree_problems(ole))
    for field, actual in (
        ("version", seen["version"]),
        ("sector_size", seen["sector_size"]),
        ("mini_sector_size", seen["mini_sector_size"]),
        ("mini_cutoff", seen["mini_cutoff"]),
        ("directory_entries", seen["directory_entries"]),
    ):
        expected = expectation.get(field)
        if field == "mini_sector_size":
            expected = 1 << expectation["mini_sector_shift"]
        if actual != expected:
            problems.append(f"{field}: olefile={actual} table={expected}")

    if seen["fat_length"] != expectation["sector_count"] - 1:
        problems.append(
            f"fat length: olefile={seen['fat_length']} table={expectation['sector_count'] - 1}"
        )

    expected_streams = {
        path: spec["size"]
        for path, spec in expectation["streams"].items()
        if path != "<root>"
    }
    if seen["streams"] != expected_streams:
        problems.append(f"stream names/sizes: olefile={seen['streams']} table={expected_streams}")

    for path, spec in expectation["streams"].items():
        if path == "<root>":
            continue
        if seen["mini"].get(path) != spec["mini"]:
            problems.append(
                f"{path}: mini flag olefile={seen['mini'].get(path)} table={spec['mini']}"
            )

    if seen["root_size"] != expectation["streams"]["<root>"]["size"]:
        problems.append(
            f"root mini stream size: olefile={seen['root_size']} "
            f"table={expectation['streams']['<root>']['size']}"
        )

    expected_rows = [tuple(row) for row in expectation["directory"]]
    if seen["directory"] != expected_rows:
        problems.append(f"directory rows: olefile={seen['directory']} table={expected_rows}")

    if seen["issues"]:
        problems.append(f"olefile recorded parsing issues: {seen['issues']}")
    return problems


def cross_check(file_bytes: bytes, cfb_file: Any) -> list[str]:
    """Every disagreement between the package's CFB reader and ``olefile`` (Turn 1b.3).

    ``cfb_file`` is an ``emailextract.cfb.CfbFile`` opened from ``file_bytes`` (the caller
    opens it; the import is local so this module stays free of a module-scope
    ``emailextract`` dependency). The two readers must agree on the layout numbers, on
    every stream's path, size and **bytes**, and on the directory's entries -- the same
    view :func:`compare` takes of a construction table. Scope is well-formed fixtures
    only: E1's two leniencies make ``olefile`` silent on a hostile one.
    """
    from emailextract import cfb

    seen = reading(file_bytes)
    problems: list[str] = []

    version, sector_size, mini_sector_size, mini_cutoff, _sectors, directory_entries = (
        cfb_file.layout()
    )
    for field, mine, theirs in (
        ("version", version, seen["version"]),
        ("sector_size", sector_size, seen["sector_size"]),
        ("mini_sector_size", mini_sector_size, seen["mini_sector_size"]),
        ("mini_cutoff", mini_cutoff, seen["mini_cutoff"]),
        ("directory_entries", directory_entries, seen["directory_entries"]),
    ):
        if mine != theirs:
            problems.append(f"{field}: cfb={mine} olefile={theirs}")

    mine_streams = {
        stream.path: stream.size for stream in cfb_file.streams if stream.path != "<root>"
    }
    if mine_streams != seen["streams"]:
        problems.append(f"stream paths/sizes: cfb={mine_streams} olefile={seen['streams']}")
    for path in sorted(set(mine_streams) & set(seen["streams"])):
        payload, fault = cfb.read_stream(cfb_file, path)
        if fault != cfb.FAULT_OK:
            problems.append(f"{path}: cfb reports {fault} on a fixture olefile reads clean")
        theirs = stream_bytes(file_bytes, path)
        if payload != theirs:
            problems.append(
                f"{path}: bytes differ, cfb={len(payload)} olefile={len(theirs)}"
            )

    mine_rows = [
        (entry.name, entry.entry_type, entry.size)
        for entry in cfb_file.entries
        if entry.entry_type != cfb.STGTY_EMPTY
    ]
    if mine_rows != seen["directory"]:
        problems.append(f"directory rows: cfb={mine_rows} olefile={seen['directory']}")

    if seen["issues"]:
        problems.append(f"olefile recorded parsing issues: {seen['issues']}")
    return problems
