"""Turn 1b.2: the deterministic minimal MS-CFB test-file writer (build spec rule 3).

Writer and reader share an author, so they can agree on a wrong layout (build spec
rule 3). This module exists to be *typed against the format specification*, not
against any reader: it emits a valid Compound File Binary container from a
hand-typed description of a storage tree, and nothing here reads a ``.eml``, a
``.msg`` or an ``olefile`` object. It imports the standard library only, so the
package and the oracle stay independent of it.

Sources are [MS-CFB], cited by section:

* 2.1 Sector -- a sector is ``2**sector_shift`` bytes; the header is not sector 0,
  sector numbers start at the first sector after it.
* 2.2 Compound File Header -- the 512-byte header (fields at 24/26/28/30/32/40/44/48/
  56/60/64/68/72 and the 109-entry inline DIFAT at offset 76).
* 2.3.1 DIFAT, 2.3.2 File Allocation Table, 2.3.3 Mini FAT -- the sector chains and
  the ``FREESECT``/``ENDOFCHAIN``/``FATSECT``/``DIFSECT`` sentinels.
* 2.4 Compound File Mini Stream -- a stream *strictly smaller* than the 4096-byte
  cutoff lives in the root entry's mini stream, addressed through the mini FAT with
  64-byte mini sectors.
* 2.6 Compound File Directory, 2.6.1 Directory Entry, 2.6.4 Red-Black Tree -- the
  128-byte entries and the child tree ordered "by name length first, then by an
  uppercased name comparison".

What this writer deliberately does **not** produce:

* no hostile or malformed file (a cyclic FAT chain, a size lie, a truncated body) --
  those are the hand-written byte literals of Turn 1b.3 frozen in
  ``fixtures/msg/SHA256SUMS``, never writer output;
* no extended DIFAT chain -- the format needs one only past 109 FAT sectors (~7.1 MB
  at 512-byte sectors); ``msg_difat_extended`` reaches it by its own route in 1b.3;
* no transaction signature, DIFAT-past-109, CLSID or timestamp content: every such
  field is a fixed zero, so the same description is byte-identical on every
  interpreter and platform.

The layout is deterministic by construction: sector indices run header (implicit),
FAT sectors, directory sectors, mini-FAT sectors, the mini stream, then the ordinary
FAT streams; every unused FAT slot is ``FREESECT``; the file is a whole number of
sectors, so ``slack`` is always zero. ``build_cfb`` never reads a clock, a file on
disk or a dict's iteration order.
"""

from __future__ import annotations

import dataclasses
import struct
from typing import Sequence

__all__ = [
    "COLOR_BLACK",
    "COLOR_RED",
    "DIFSECT",
    "DIRECTORY_ENTRY_SIZE",
    "ENDOFCHAIN",
    "FATSECT",
    "FREESECT",
    "NOSTREAM",
    "SIGNATURE",
    "STGTY_ROOT",
    "STGTY_STORAGE",
    "STGTY_STREAM",
    "Storage",
    "Stream",
    "build_cfb",
    "storage",
    "stream",
]

# --- [MS-CFB] 2.2/2.3 sentinel sector values --------------------------------------
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
#: "No stream": a directory entry's left/right/child pointer when it is absent.
NOSTREAM = 0xFFFFFFFF

# --- [MS-CFB] 2.2 header constants -------------------------------------------------
SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
MINOR_VERSION = 0x003E  # [MS-CFB] 2.2 fixes the minor version at 0x003E.
BYTE_ORDER = 0xFFFE  # little-endian marker.
MINI_SECTOR_SHIFT = 6  # 64-byte mini sectors.
MINI_CUTOFF = 0x1000  # [MS-CFB] 2.4: strictly below this is a mini stream.
SECTOR_SIZE = {3: 512, 4: 4096}

# --- [MS-CFB] 2.6.1 directory entry ------------------------------------------------
DIRECTORY_ENTRY_SIZE = 128
_NAME_FIELD = 64  # 31 UTF-16 code units plus a terminating NUL.
STGTY_EMPTY = 0
STGTY_STORAGE = 1
STGTY_STREAM = 2
STGTY_ROOT = 5
COLOR_RED = 0  # [MS-CFB] 2.6.1: 0x00 is red.
COLOR_BLACK = 1  # 0x01 is black.

_HEADER_STRUCT = struct.Struct("<8s16sHHHHHHLLLLLLLLLL")
_DIR_ENTRY_STRUCT = struct.Struct("<64sHBBIII16sIQQIII")
assert _HEADER_STRUCT.size == 76
assert _DIR_ENTRY_STRUCT.size == DIRECTORY_ENTRY_SIZE


@dataclasses.dataclass(frozen=True)
class Stream:
    """One stream: a name and the raw bytes the container stores for it."""

    name: str
    data: bytes = b""


@dataclasses.dataclass(frozen=True)
class Storage:
    """One storage: a name and its ordered children (storages and streams)."""

    name: str
    children: tuple = ()


def stream(name: str, data: bytes = b"") -> Stream:
    """A stream whose bytes are exactly ``data`` (the writer never inspects them)."""
    return Stream(name=name, data=bytes(data))


def storage(name: str, *children: "Storage | Stream") -> Storage:
    """A storage over ``children``, visited in the order given (that fixes the ids)."""
    return Storage(name=name, children=tuple(children))


class _Entry:
    """One flattened directory entry, occupying the id the pre-order walk gives it."""

    __slots__ = ("name", "kind", "data", "children", "parent", "start")

    def __init__(self, name: str, kind: str, parent: int) -> None:
        self.name = name
        self.kind = kind  # "root" | "storage" | "stream"
        self.data = b""
        self.children: list[int] = []
        self.parent = parent
        self.start = 0


def _sort_key(name: str) -> tuple:
    """[MS-CFB] 2.6.4: order siblings by name length, then by uppercased name.

    The shorter name sorts first; ties break on a case-insensitive code-point
    comparison. Every name this writer sees is ASCII, for which ``str.upper`` is the
    simple uppercase mapping the spec names.
    """
    return (len(name), name.upper())


def _flatten(root: Storage) -> list[_Entry]:
    """Assign directory ids in pre-order, children visited in declaration order."""
    if not isinstance(root, Storage):
        raise TypeError("build_cfb: the tree root must be a Storage")
    entries: list[_Entry] = []

    def add(node: "Storage | Stream", parent: int) -> int:
        if isinstance(node, Storage):
            here = len(entries)
            entries.append(_Entry(node.name, "root" if parent < 0 else "storage", parent))
            entries[here].children = [add(child, here) for child in node.children]
            return here
        if not isinstance(node, Stream):
            raise TypeError(f"build_cfb: {node!r} is neither a Storage nor a Stream")
        here = len(entries)
        entry = _Entry(node.name, "stream", parent)
        entry.data = node.data
        entries.append(entry)
        return here

    add(root, -1)

    seen: dict[tuple, int] = {}
    for index, entry in enumerate(entries):
        key = (entry.parent, _sort_key(entry.name))
        if key in seen:
            raise ValueError(
                f"build_cfb: {entry.name!r} appears twice in one storage "
                f"(ids {seen[key]} and {index})"
            )
        seen[key] = index
    return entries


def _ceil(numerator: int, denominator: int) -> int:
    if numerator <= 0:
        return 0
    return (numerator + denominator - 1) // denominator


def _pad(data: bytes, block: int) -> bytes:
    remainder = len(data) % block
    return data + b"\x00" * (block - remainder) if remainder else data


# --------------------------------------------------------------- red-black tree


class _Node:
    __slots__ = ("key", "entry_id", "left", "right", "parent", "red")

    def __init__(self, key: tuple, entry_id: int) -> None:
        self.key = key
        self.entry_id = entry_id
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.parent: _Node | None = None
        self.red = True


def _rotate_left(root: list, x: _Node) -> None:
    y = x.right
    x.right = y.left
    if y.left is not None:
        y.left.parent = x
    y.parent = x.parent
    if x.parent is None:
        root[0] = y
    elif x is x.parent.left:
        x.parent.left = y
    else:
        x.parent.right = y
    y.left = x
    x.parent = y


def _rotate_right(root: list, x: _Node) -> None:
    y = x.left
    x.left = y.right
    if y.right is not None:
        y.right.parent = x
    y.parent = x.parent
    if x.parent is None:
        root[0] = y
    elif x is x.parent.right:
        x.parent.right = y
    else:
        x.parent.left = y
    y.right = x
    x.parent = y


def _insert_fixup(root: list, node: _Node) -> None:
    while node.parent is not None and node.parent.red:
        parent = node.parent
        grand = parent.parent
        if parent is grand.left:
            uncle = grand.right
            if uncle is not None and uncle.red:
                parent.red = False
                uncle.red = False
                grand.red = True
                node = grand
            else:
                if node is parent.right:
                    node = parent
                    _rotate_left(root, node)
                node.parent.red = False
                node.parent.parent.red = True
                _rotate_right(root, node.parent.parent)
        else:
            uncle = grand.left
            if uncle is not None and uncle.red:
                parent.red = False
                uncle.red = False
                grand.red = True
                node = grand
            else:
                if node is parent.left:
                    node = parent
                    _rotate_right(root, node)
                node.parent.red = False
                node.parent.parent.red = True
                _rotate_left(root, node.parent.parent)
    root[0].red = False


def _red_black_tree(pairs: list[tuple[tuple, int]]) -> tuple[int, dict[int, tuple[int, int, int]]]:
    """A valid red-black tree over ``pairs``, by CLRS insert + fix-up.

    ``pairs`` are ``(sort_key, entry_id)`` and the nodes are inserted in sorted
    order, so the tree's *shape* is a function of the keys alone -- never of the
    order the storage declared its children in.

    Returns ``(child_root_id, {entry_id: (left_id, right_id, colour)})``.
    """
    root: list[_Node | None] = [None]
    nodes: dict[int, _Node] = {}
    for pair in sorted(pairs, key=lambda item: item[0]):
        key, entry_id = pair
        node = _Node(key, entry_id)
        nodes[entry_id] = node
        parent: _Node | None = None
        current = root[0]
        while current is not None:
            parent = current
            current = current.left if key < current.key else current.right
        node.parent = parent
        if parent is None:
            root[0] = node
        elif key < parent.key:
            parent.left = node
        else:
            parent.right = node
        _insert_fixup(root, node)
    links = {
        entry_id: (
            node.left.entry_id if node.left is not None else NOSTREAM,
            node.right.entry_id if node.right is not None else NOSTREAM,
            COLOR_BLACK if not node.red else COLOR_RED,
        )
        for entry_id, node in nodes.items()
    }
    child_root = root[0].entry_id if root[0] is not None else NOSTREAM
    return child_root, links


# --------------------------------------------------------------- the builder


def build_cfb(
    root: Storage,
    *,
    version: int = 3,
    mini_cutoff: int = MINI_CUTOFF,
    mini_sector_size: int = 1 << MINI_SECTOR_SHIFT,
    sector_order: Sequence[str] | None = None,
) -> bytes:
    """Render ``root`` as one MS-CFB file and return its exact bytes.

    ``version`` is 3 (512-byte sectors) or 4 (4096-byte sectors). ``sector_order``,
    when given, is the order in which the ordinary FAT streams are laid out; it must
    name exactly the streams whose size is at or above ``mini_cutoff`` (the mini
    stream is always laid out first), and it exists so a fixture that pins a
    stream's sector index can ask for one.
    """
    if version not in SECTOR_SIZE:
        raise ValueError(f"version must be 3 or 4, not {version!r}")
    if mini_sector_size != 1 << MINI_SECTOR_SHIFT:
        raise ValueError("the mini sector shift is fixed at 6 (64-byte mini sectors)")
    sector_size = SECTOR_SIZE[version]
    slots_per_sector = sector_size // 4  # one FAT/miniFAT slot per four bytes.

    entries = _flatten(root)

    # [MS-CFB] 2.4: a stream strictly smaller than the cutoff is a mini stream. A
    # zero-size stream is neither: it needs no chain and its start is ENDOFCHAIN.
    mini_ids = [
        i for i, e in enumerate(entries) if e.kind == "stream" and 0 < len(e.data) < mini_cutoff
    ]
    mini_blocks = {i: _ceil(len(entries[i].data), mini_sector_size) for i in mini_ids}
    mini_bytes = b"".join(_pad(entries[i].data, mini_sector_size) for i in mini_ids)
    mini_sector_count = len(mini_bytes) // mini_sector_size
    mini_fat = [FREESECT] * mini_sector_count
    cursor = 0
    for entry_id in mini_ids:
        blocks = mini_blocks[entry_id]
        entries[entry_id].start = cursor
        for offset in range(blocks):
            mini_fat[cursor + offset] = (
                cursor + offset + 1 if offset + 1 < blocks else ENDOFCHAIN
            )
        cursor += blocks
    entries[0].data = mini_bytes

    fat_ids = [
        i for i, e in enumerate(entries) if e.kind == "stream" and len(e.data) >= mini_cutoff
    ]
    if sector_order is not None:
        by_name = {entries[i].name: i for i in fat_ids}
        if sorted(sector_order) != sorted(by_name):
            raise ValueError(
                f"sector_order must name exactly the {len(fat_ids)} FAT streams, "
                f"got {list(sector_order)}"
            )
        fat_ids = [by_name[name] for name in sector_order]

    # (entry id, byte size); a ``None`` id is the root entry's mini stream.
    stream_plan: list[tuple[int | None, int]] = []
    if mini_bytes:
        stream_plan.append((None, len(mini_bytes)))
    stream_plan.extend((i, len(entries[i].data)) for i in fat_ids)

    directory_sectors = max(1, _ceil(len(entries) * DIRECTORY_ENTRY_SIZE, sector_size))
    minifat_sectors = _ceil(mini_sector_count * 4, sector_size)
    stream_sectors = sum(_ceil(size, sector_size) for _, size in stream_plan)
    fat_sectors = _fat_sector_count(directory_sectors, minifat_sectors, stream_sectors, slots_per_sector)

    # --- assign sector indices, in the fixed layout order ----------------------
    directory_start = fat_sectors
    minifat_start = directory_start + directory_sectors
    cursor = minifat_start + minifat_sectors
    starts: dict[int | None, int] = {}
    for entry_id, size in stream_plan:
        count = _ceil(size, sector_size)
        if count:
            starts[entry_id] = cursor
            cursor += count
    if mini_bytes:
        entries[0].start = starts[None]
    for entry_id, _size in stream_plan:
        if entry_id is not None:
            entries[entry_id].start = starts[entry_id]
    total_sectors = cursor

    # --- the FAT ([MS-CFB] 2.3.2): one slot per sector, header excluded --------
    fat = [FREESECT] * total_sectors
    for index in range(fat_sectors):
        fat[index] = FATSECT
    _mark_chain(fat, directory_start, directory_sectors)
    _mark_chain(fat, minifat_start, minifat_sectors)
    for entry_id, size in stream_plan:
        _mark_chain(fat, starts[entry_id], _ceil(size, sector_size))

    # --- assemble the sectors in index order -----------------------------------
    header = _render_header(
        version=version,
        sector_size=sector_size,
        mini_cutoff=mini_cutoff,
        fat_sectors=fat_sectors,
        directory_start=directory_start,
        directory_sectors=directory_sectors,
        minifat_start=minifat_start if minifat_sectors else ENDOFCHAIN,
        minifat_sectors=minifat_sectors,
    )
    body = bytearray(header)
    body += _pad(b"".join(struct.pack("<L", value) for value in fat), sector_size)
    body += _render_directory(entries, sector_size)
    body += _pad(b"".join(struct.pack("<L", value) for value in mini_fat), sector_size)
    body += _pad(mini_bytes, sector_size)
    for entry_id, size in stream_plan:
        if entry_id is None or not size:
            continue
        body += _pad(entries[entry_id].data, sector_size)
    return bytes(body)


def _fat_sector_count(
    directory_sectors: int,
    minifat_sectors: int,
    stream_sectors: int,
    slots_per_sector: int,
) -> int:
    """The fixed point of "the FAT must cover its own sectors" ([MS-CFB] 2.3.2)."""
    fat_sectors = 0
    while True:
        total = fat_sectors + directory_sectors + minifat_sectors + stream_sectors
        needed = max(1, _ceil(total, slots_per_sector))
        if needed == fat_sectors:
            return fat_sectors
        fat_sectors = needed


def _mark_chain(fat: list[int], start: int, count: int) -> None:
    for offset in range(count):
        fat[start + offset] = start + offset + 1 if offset + 1 < count else ENDOFCHAIN


def _render_directory(entries: Sequence[_Entry], sector_size: int) -> bytes:
    """Render every directory entry, then pad the last sector with EMPTY entries."""
    child_root: dict[int, int] = {}
    links: dict[int, tuple[int, int, int]] = {}
    for index, entry in enumerate(entries):
        if entry.kind in ("root", "storage"):
            tree_root, node_links = _red_black_tree(
                [(_sort_key(entries[cid].name), cid) for cid in entry.children]
            )
            child_root[index] = tree_root
            links.update(node_links)
    rendered = bytearray()
    for index, entry in enumerate(entries):
        if entry.kind == "root":
            entry_type, start, size, child = STGTY_ROOT, entry.start, len(entry.data), child_root[index]
        elif entry.kind == "storage":
            entry_type, start, size, child = STGTY_STORAGE, 0, 0, child_root[index]
        else:
            entry_type = STGTY_STREAM
            start = entry.start if entry.data else ENDOFCHAIN
            size = len(entry.data)
            child = NOSTREAM
        left, right, colour = links.get(index, (NOSTREAM, NOSTREAM, COLOR_BLACK))
        name = entry.name.encode("utf-16-le")
        rendered += _DIR_ENTRY_STRUCT.pack(
            (name + b"\x00\x00").ljust(_NAME_FIELD, b"\x00"),
            len(name) + 2,
            entry_type,
            colour,
            left,
            right,
            child,
            b"\x00" * 16,
            0,
            0,
            0,
            start & 0xFFFFFFFF,
            size & 0xFFFFFFFF,
            size >> 32,
        )
    empty = -len(entries) % (sector_size // DIRECTORY_ENTRY_SIZE)
    rendered += b"\x00" * DIRECTORY_ENTRY_SIZE * empty
    return bytes(rendered)


def _render_header(
    *,
    version: int,
    sector_size: int,
    mini_cutoff: int,
    fat_sectors: int,
    directory_start: int,
    directory_sectors: int,
    minifat_start: int,
    minifat_sectors: int,
) -> bytes:
    """The 512-byte header, zero-padded to a whole sector for version 4."""
    difat = [FREESECT] * 109
    for index in range(fat_sectors):
        difat[index] = index
    header = _HEADER_STRUCT.pack(
        SIGNATURE,
        b"\x00" * 16,
        MINOR_VERSION,
        version,
        BYTE_ORDER,
        sector_size.bit_length() - 1,
        MINI_SECTOR_SHIFT,
        0,
        0,
        0 if version == 3 else directory_sectors,
        fat_sectors,
        directory_start,
        0,
        mini_cutoff,
        minifat_start,
        minifat_sectors,
        ENDOFCHAIN,  # no extended DIFAT chain.
        0,
    )
    header += struct.pack("<109L", *difat)
    return _pad(header, sector_size)
