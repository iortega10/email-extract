"""Turn 1b.3: the package's own CFB (Compound File Binary) reader.

``cfb.py`` is a **leaf**: it imports the stdlib, ``struct`` and ``dataclasses`` only, and
never ``walk``/``model``/``parse``/``olefile``. It opens a CFB container's bytes and
reports what it holds; it does not read MAPI (Turn 1b.4), it is not wired into
``parse``/``container``/``walk`` (Turn 1b.5), and it neither writes a file nor an oracle.
Every citation is to [MS-CFB] (public); no ``olefile`` code is copied.

**The fault contract.** :func:`open_cfb` *returns*, it never raises, on any input: a
``CfbRefusal`` whose ``reason`` is one of exactly
:data:`CFB_REFUSAL_REASONS` -- ``cfb_header_unsupported``, ``cfb_directory_loop``,
``not_a_message`` (CFB magic with no top-level ``__properties_version1.0``) or one of the
three cap ids -- or a :class:`CfbFile`. Per-stream faults come back from
:func:`read_stream` as ``(bytes, fault)`` with ``fault`` one of
:data:`FAULT_KINDS` (``ok``, ``cycle``, ``out_of_range``, ``short_chain``), for both
stream kinds: a stream whose declared size is **strictly below** the mini cutoff is
addressed through the miniFAT inside the root's mini stream ([MS-CFB] 2.4), any other
through the FAT. **No allocation is ever sized from a declared length**: a ``2**40`` or
``0xFFFFFFFF`` size claim on a one-sector chain returns that one sector's bytes plus
``short_chain``, and the declared length is never fabricated.

**The caps** (:class:`CfbLimits`, and the reason ids are ``walk.CFB_CAP_REASONS``, pinned
by a test):

* ``max_sector_count = 1_048_576``: 512-byte sectors, so 512 MiB -- comfortably above the
  64 MiB input gate, which makes it a guard against a lying header rather than a second
  size gate. The count is taken from the *file's* length, so a header cannot lie about it.
* ``max_directory_entries = 65_536``: a 65_536-entry directory is 8 MiB; the eleven real
  files have a few hundred entries.
* ``max_difat_chain_length = 256``: 256 DIFAT sectors address ``256 * 127`` FAT sectors,
  i.e. ``32_512 * 128 = 4_161_536`` sectors -- about 2 GiB at 512-byte sectors, past the
  sector cap, so the chain cap is reached only by a constructed input.

A cap hit is an observation carrying the caller's value and the **real** observed count
(:class:`CapObservation`); building ``CapRecord``s from it is Turn 1b.5. The comparison is
``observed > cap``, and the check runs **before** the structure it guards is allocated or
walked: the sector count before the FAT is read, the directory entry count before entries
are parsed, the DIFAT length as the chain is walked.

**The work-per-byte budget.** Work is counted in *steps* (one per header parse, table-entry
read, directory-entry visit or chain step), never in wall clock, through :class:`Work`.
Derived from the structure: the FAT and the miniFAT are at most ``sectors_per_table_sector
= 128`` slot reads per sector they occupy, the directory at most 4 entries per sector, and
every chain is bounded by ``4 * sector_count + 16`` steps (the E2 bound of
``docs/design/msg-architecture.md``); no table is read from more sectors than the file
holds, and a refused input stops at its cap. So ``open_cfb`` plus a full read of every
stream is at most :data:`WORK_PER_SECTOR` * sector_count + :data:`WORK_BASE` steps --
measured over every fixture, seed and fuzz mutant by ``tests/test_cfb_fuzz.py``.

**What it deliberately does not do**: no MAPI property, no ``__substg1.0_`` name, no body,
no virtual byte, no ``olefile``, no exception, no wall-clock assertion, and it does not key
sector classification on the FAT's ``FATSECT``/``DIFSECT`` markers (``msg-architecture.md``
point 6: ``olefile`` does not validate them, and a marker can be a lie while the chain that
reaches the sector is the truth).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace
from typing import NamedTuple, Sequence

__all__ = [
    "CFB_CAP_DIRECTORY_ENTRIES",
    "CFB_CAP_DIFAT_CHAIN_LENGTH",
    "CFB_CAP_IDS",
    "CFB_CAP_SECTOR_COUNT",
    "CFB_DIRECTORY_LOOP",
    "CFB_HEADER_UNSUPPORTED",
    "CFB_REFUSAL_REASONS",
    "DEFAULT_CFB_LIMITS",
    "FAULT_CYCLE",
    "FAULT_KINDS",
    "FAULT_OK",
    "FAULT_OUT_OF_RANGE",
    "FAULT_REASON_IDS",
    "FAULT_SHORT_CHAIN",
    "FAULT_STATUS",
    "HEADER_BYTES",
    "MINI_CUTOFF",
    "MINI_SECTOR_BYTES",
    "NOT_A_MESSAGE",
    "PROPERTIES_STREAM",
    "SECTOR_CLASSES",
    "WORK_BASE",
    "WORK_PER_SECTOR",
    "CapObservation",
    "CfbEntry",
    "CfbFile",
    "CfbHeader",
    "CfbLimits",
    "CfbRefusal",
    "ChainWalk",
    "DifatWalk",
    "DirectoryWalk",
    "StreamResult",
    "Work",
    "chain_sectors",
    "check_caps",
    "classify_sectors",
    "lookup_entry",
    "open_cfb",
    "parse_header",
    "read_fat",
    "read_minifat",
    "read_stream",
    "walk_difat",
    "walk_directory",
]

# --- [MS-CFB] 2.2/2.3 sentinels ------------------------------------------------
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC
NOSTREAM = 0xFFFFFFFF

# --- [MS-CFB] 2.6.1 object types ----------------------------------------------
STGTY_EMPTY = 0
STGTY_STORAGE = 1
STGTY_STREAM = 2
STGTY_ROOT = 5

#: [MS-CFB] 2.2: the eight-byte signature that opens every CFB file.
MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
#: [MS-CFB] 2.2/2.6.1 fixed sizes.
HEADER_BYTES = 512
DIRECTORY_ENTRY_BYTES = 128
#: [MS-CFB] 2.2: the header DIFAT holds 109 sector ids (76 + 4 * 109 = 512).
DIFAT_SLOTS = 109
#: [MS-CFB] 2.2: the big-endian marker 0xFFFE for a little-endian file.
BYTE_ORDER = 0xFFFE
#: [MS-CFB] 2.2: the mini sector shift is 6 (64-byte mini sectors) and the mini stream
#: cutoff is 0x1000; both are fixed, so anything else is an unsupported header.
MINI_SECTOR_SHIFT = 6
MINI_SECTOR_BYTES = 1 << MINI_SECTOR_SHIFT
MINI_CUTOFF = 0x1000
#: [MS-CFB] 2.2: the legal sector shifts per major version.
SECTOR_SHIFTS = {3: (9, 10, 11, 12), 4: (12,)}
#: [MS-CFB] 2.2: the major versions this reader supports.
VERSIONS = (3, 4)
#: The stream that makes a CFB file an Outlook message (D14).
PROPERTIES_STREAM = "__properties_version1.0"

# --- the closed refusal vocabulary --------------------------------------------
CFB_HEADER_UNSUPPORTED = "cfb_header_unsupported"
CFB_DIRECTORY_LOOP = "cfb_directory_loop"
NOT_A_MESSAGE = "not_a_message"
CFB_CAP_SECTOR_COUNT = "sector_count_cap"
CFB_CAP_DIRECTORY_ENTRIES = "directory_entries_cap"
CFB_CAP_DIFAT_CHAIN_LENGTH = "difat_chain_length_cap"

#: The three cap reasons, in the order ``walk.CFB_CAP_REASONS`` fixes them.
CFB_CAP_IDS = (CFB_CAP_SECTOR_COUNT, CFB_CAP_DIRECTORY_ENTRIES, CFB_CAP_DIFAT_CHAIN_LENGTH)
#: Every reason :func:`open_cfb` may refuse with. The three names are members of
#: ``parse.NAMED_ERROR_REASONS``; the three cap ids are ``walk.CFB_CAP_REASONS``.
CFB_REFUSAL_REASONS = (CFB_HEADER_UNSUPPORTED, CFB_DIRECTORY_LOOP, NOT_A_MESSAGE) + CFB_CAP_IDS

# --- the closed stream-fault vocabulary ---------------------------------------
FAULT_OK = "ok"
FAULT_CYCLE = "cycle"
FAULT_OUT_OF_RANGE = "out_of_range"
FAULT_SHORT_CHAIN = "short_chain"
FAULT_KINDS = (FAULT_OK, FAULT_CYCLE, FAULT_OUT_OF_RANGE, FAULT_SHORT_CHAIN)
#: The `msg.stream_faults` row's mapped ``Status.TRUNCATED`` reason id
#: (``docs/design/phase1b-facts.md``): a cycle is a declared-length mismatch, an
#: out-of-range sector or a chain shorter than the claim ended the stream early.
FAULT_REASON_IDS = {
    FAULT_CYCLE: "declared_length_mismatch",
    FAULT_OUT_OF_RANGE: "stream_ended_early",
    FAULT_SHORT_CHAIN: "stream_ended_early",
}
#: The status a faulted stream maps to (`Status.TRUNCATED.value`); a test pins it.
FAULT_STATUS = "TRUNCATED"

#: The eight sector classes, in the fixed order `msg.sector_accounting` uses.
SECTOR_CLASSES = ("header", "difat", "fat", "minifat", "directory", "stream", "free", "slack")

#: The declared work bound: see the module docstring for its derivation.
WORK_PER_SECTOR = 300
WORK_BASE = 4096

_HEADER_STRUCT = struct.Struct("<8s16sHHHHHHLLLLLLLLLL")
_DIRECTORY_STRUCT = struct.Struct("<64sHBBIII16sIQQIII")
_NAME_FIELD = 64
_MINI_SLOTS_PER_SECTOR = 4


class Work:
    """The step counter the budget is stated in: one step per structural action."""

    __slots__ = ("steps",)

    def __init__(self) -> None:
        self.steps = 0

    def tick(self, count: int = 1) -> None:
        self.steps += count

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Work(steps={self.steps})"


@dataclass(frozen=True)
class CfbLimits:
    """The CFB reader's three caps (D1: ``walk.Limits`` must not move)."""

    max_sector_count: int = 1_048_576
    max_directory_entries: int = 65_536
    max_difat_chain_length: int = 256

    def __post_init__(self) -> None:
        for name in ("max_sector_count", "max_directory_entries", "max_difat_chain_length"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative int, not {value!r}")


#: The defaults above, derived in the module docstring.
DEFAULT_CFB_LIMITS = CfbLimits()


class CapObservation(NamedTuple):
    """One cap hit: the reason id, the caller's value and the real observed count."""

    cap_id: str
    value: int
    observed: int


@dataclass(frozen=True)
class CfbRefusal:
    """A closed refusal: the reason id, a hand-readable detail and any cap hit."""

    reason: str
    detail: str
    observation: "CapObservation | None" = None

    def __post_init__(self) -> None:
        if self.reason not in CFB_REFUSAL_REASONS:
            raise ValueError(f"refusal reason {self.reason!r} is not one of {CFB_REFUSAL_REASONS}")


class CfbHeader(NamedTuple):
    """The 512-byte header's fields ([MS-CFB] 2.2), read verbatim."""

    version: int
    byte_order: int
    sector_shift: int
    mini_sector_shift: int
    mini_cutoff: int
    num_dir_sectors: int
    num_fat_sectors: int
    first_dir_sector: int
    first_mini_fat_sector: int
    num_mini_fat_sectors: int
    first_difat_sector: int
    num_difat_sectors: int
    difat: tuple[int, ...]

    @property
    def sector_size(self) -> int:
        return 1 << self.sector_shift

    @property
    def mini_sector_size(self) -> int:
        return 1 << self.mini_sector_shift


class CfbEntry(NamedTuple):
    """One 128-byte directory entry ([MS-CFB] 2.6.1) with its posix path.

    ``path`` is ``""`` for the root entry and for an entry no tree reaches; a
    ``fault`` is recorded (never raised) for a name whose declared length is not a
    whole number of UTF-16 code units, or for a link that points outside the
    directory.
    """

    index: int
    name: str
    entry_type: int
    colour: int
    left: int
    right: int
    child: int
    start: int
    size: int
    path: str
    faults: tuple[str, ...]

    @property
    def is_stream(self) -> bool:
        return self.entry_type == STGTY_STREAM


class ChainWalk(NamedTuple):
    """A chain walk's sectors and its closed fault."""

    sectors: tuple[int, ...]
    fault: str


class DifatWalk(NamedTuple):
    """The DIFAT walk: the FAT sector ids, the DIFAT sectors, and whether the
    extended chain was present and walked cleanly."""

    fat_sector_ids: tuple[int, ...]
    difat_sectors: tuple[int, ...]
    extended: bool
    fault: "str | None"


class DirectoryWalk(NamedTuple):
    """The directory walk: every entry, the sectors it was read from, its slot count."""

    entries: tuple[CfbEntry, ...]
    sectors: tuple[int, ...]
    directory_entries: int


class StreamResult(NamedTuple):
    """One stream's chain walk: its kind, chain, available bytes and closed fault."""

    path: str
    mini: bool
    start: int
    size: int
    sectors: tuple[int, ...]
    available: int
    fault: str


@dataclass(frozen=True)
class CfbFile:
    """An opened CFB container: the layout, the tables, the entries and the accounting.

    ``accounting`` is the eight ``(class, bytes)`` rows in :data:`SECTOR_CLASSES` order;
    ``unaccounted`` is the byte count no class claimed (0 on every well-formed file, and
    never absorbed into another class). ``faults`` is the per-stream list shaped like
    ``msg.stream_faults``.
    """

    data: bytes
    header: CfbHeader
    fat_sector_ids: tuple[int, ...]
    difat_sectors: tuple[int, ...]
    extended_difat: bool
    difat_fault: "str | None"
    fat: tuple[int, ...]
    minifat: tuple[int, ...]
    entries: tuple[CfbEntry, ...]
    directory_sectors: tuple[int, ...]
    directory_entries: int
    sector_count: int
    streams: tuple[StreamResult, ...]
    faults: tuple[tuple[str, str, str], ...]
    accounting: tuple[tuple[str, int], ...]
    unaccounted: int
    work: Work

    @property
    def version(self) -> int:
        return self.header.version

    @property
    def sector_size(self) -> int:
        return self.header.sector_size

    @property
    def mini_sector_size(self) -> int:
        return self.header.mini_sector_size

    @property
    def mini_cutoff(self) -> int:
        return self.header.mini_cutoff

    @property
    def body_sectors(self) -> int:
        """The sector count without the header's own sector-sized window."""
        return max(self.sector_count - 1, 0)

    @property
    def root(self) -> CfbEntry:
        return self.entries[0]

    @property
    def steps(self) -> int:
        return self.work.steps

    def layout(self) -> tuple[int, int, int, int, int, int]:
        """`msg.container_layout`'s six values, in that order."""
        return (
            self.version,
            self.sector_size,
            self.mini_sector_size,
            self.mini_cutoff,
            self.sector_count,
            self.directory_entries,
        )

    def accounting_map(self) -> dict[str, int]:
        """The eight classes as a ``class -> bytes`` mapping."""
        return dict(self.accounting)


# --------------------------------------------------------------- the header


def parse_header(data: bytes) -> "CfbHeader | CfbRefusal":
    """The 512-byte header, or ``cfb_header_unsupported``.

    Version, byte order, sector shift (v3: one of 9, 10, 11, 12; v4: exactly 12) and the
    fixed mini sector shift/cutoff are checked; anything else is refused rather than
    guessed. A v4 file's header occupies a whole 4096-byte sector.
    """
    if len(data) < HEADER_BYTES:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, f"{len(data)} bytes is shorter than a CFB header")
    if data[:8] != MAGIC:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, "no CFB signature")
    (
        signature,
        _clsid,
        _minor,
        version,
        byte_order,
        sector_shift,
        mini_shift,
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
    ) = _HEADER_STRUCT.unpack(data[: _HEADER_STRUCT.size])
    if signature != MAGIC:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, "no CFB signature")
    if version not in VERSIONS:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, f"CFB version {version} is not 3 or 4")
    if byte_order != BYTE_ORDER:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, f"byte order marker {byte_order:#06x} is not 0xFFFE")
    if sector_shift not in SECTOR_SHIFTS[version]:
        return CfbRefusal(
            CFB_HEADER_UNSUPPORTED,
            f"sector shift {sector_shift} is not one of {SECTOR_SHIFTS[version]} for version {version}",
        )
    if mini_shift != MINI_SECTOR_SHIFT:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, f"mini sector shift {mini_shift} is not 6")
    if mini_cutoff != MINI_CUTOFF:
        return CfbRefusal(CFB_HEADER_UNSUPPORTED, f"mini stream cutoff {mini_cutoff} is not {MINI_CUTOFF}")
    difat = struct.unpack_from("<%dL" % DIFAT_SLOTS, data, 76)
    return CfbHeader(
        version=version,
        byte_order=byte_order,
        sector_shift=sector_shift,
        mini_sector_shift=mini_shift,
        mini_cutoff=mini_cutoff,
        num_dir_sectors=num_dir_sectors,
        num_fat_sectors=num_fat_sectors,
        first_dir_sector=first_dir_sector,
        first_mini_fat_sector=first_mini_fat_sector,
        num_mini_fat_sectors=num_mini_fat_sectors,
        first_difat_sector=first_difat_sector,
        num_difat_sectors=num_difat_sectors,
        difat=tuple(difat),
    )


def sector_windows(byte_length: int, sector_size: int) -> int:
    """The number of sector-sized windows a file of ``byte_length`` bytes holds.

    Window 0 is the header's own window, so a well-formed v3 file of ``n`` sectors plus
    its header reports ``n + 1``; the last window may be partial (a truncated file).
    """
    if byte_length <= 0:
        return 1
    return (byte_length + sector_size - 1) // sector_size


def _sector_bytes(data: bytes, sector_size: int, index: int) -> bytes:
    """Sector ``index``'s bytes (window ``index + 1``); short if the file ends there."""
    start = (index + 1) * sector_size
    return data[start : start + sector_size]


def _window_bytes(data: bytes, sector_size: int, index: int) -> int:
    """How many bytes of window ``index`` are actually present in the file."""
    return max(min((index + 1) * sector_size, len(data)) - index * sector_size, 0)


# --------------------------------------------------------------- the caps


def _cap_detail(hit: CapObservation) -> str:
    return f"{hit.cap_id}: observed {hit.observed} exceeds the cap {hit.value}"


def check_caps(
    limits: CfbLimits,
    *,
    sector_count: "int | None" = None,
    directory_entries: "int | None" = None,
    difat_chain_length: "int | None" = None,
) -> tuple[CapObservation, ...]:
    """The cap observations for the measures given, in :data:`CFB_CAP_IDS` order.

    Only a measure that **exceeds** its cap is reported (``observed > cap``, so the
    boundary itself is legal); the caller's value and the real observed count are both
    carried. A measure left out is not measured, so a caller checks each cap at the
    moment the structure it guards would be allocated or walked.
    """
    measured = {
        CFB_CAP_SECTOR_COUNT: (sector_count, limits.max_sector_count),
        CFB_CAP_DIRECTORY_ENTRIES: (directory_entries, limits.max_directory_entries),
        CFB_CAP_DIFAT_CHAIN_LENGTH: (difat_chain_length, limits.max_difat_chain_length),
    }
    return tuple(
        CapObservation(cap_id, cap, observed)
        for cap_id in CFB_CAP_IDS
        for observed, cap in (measured[cap_id],)
        if observed is not None and observed > cap
    )


# --------------------------------------------------------------- the DIFAT


def walk_difat(
    header: CfbHeader,
    data: bytes,
    *,
    limits: CfbLimits = DEFAULT_CFB_LIMITS,
    body_sectors: "int | None" = None,
    work: "Work | None" = None,
) -> "DifatWalk | CfbRefusal":
    """The 109 inline DIFAT entries, then the extended chain.

    The extended chain is walked with a visited set and **bounded** by
    ``limits.max_difat_chain_length`` (a chain longer than the cap is a
    ``difat_chain_length_cap`` refusal). A repeated or out-of-range DIFAT sector is a
    **broken chain**: the walk stops, ``extended`` is False and the fault is recorded --
    the file still opens, and whatever the chain failed to reach shows up in
    :func:`classify_sectors` as unaccounted rather than being silently absorbed. So
    ``extended`` is the presence observation behind ``msg.cfb_difat_extended``
    (owner decision O1: read through, fault only on a broken chain).
    """
    if work is None:
        work = Work()
    work.tick(1)
    inline: list[int] = []
    for value in header.difat:
        if value in (FREESECT, ENDOFCHAIN):
            break
        inline.append(value)
    if header.num_difat_sectors == 0 or header.first_difat_sector in (ENDOFCHAIN, FREESECT):
        return DifatWalk(tuple(inline), (), False, None)

    limit = body_sectors if body_sectors is not None else 0
    chain: list[int] = []
    seen: set[int] = set()
    fat_ids = list(inline)
    isect = header.first_difat_sector
    fault: "str | None" = None
    while True:
        work.tick(2)
        if isect in seen:
            fault = FAULT_CYCLE
            break
        if isect >= limit:
            fault = FAULT_OUT_OF_RANGE
            break
        seen.add(isect)
        chain.append(isect)
        hits = check_caps(limits, difat_chain_length=len(chain))
        if hits:
            return CfbRefusal(hits[0].cap_id, _cap_detail(hits[0]), hits[0])
        slots = _sector_slots(data, header.sector_size, isect)
        for value in slots[: _slots_per_sector(header)]:
            if value in (FREESECT, ENDOFCHAIN):
                continue
            if value in fat_ids:
                continue
            fat_ids.append(value)
        isect = slots[-1] if slots else ENDOFCHAIN
        if isect in (FREESECT, ENDOFCHAIN):
            break
    return DifatWalk(tuple(fat_ids), tuple(chain), fault is None, fault)


def _slots_per_sector(header: CfbHeader) -> int:
    return header.sector_size // 4


def _sector_slots(data: bytes, sector_size: int, index: int) -> tuple[int, ...]:
    """Sector ``index`` as 32-bit little-endian slots (fewer if the file ends short)."""
    raw = _sector_bytes(data, sector_size, index)
    return struct.unpack("<%dL" % (len(raw) // 4), raw[: (len(raw) // 4) * 4])


def read_fat(
    data: bytes,
    header: CfbHeader,
    fat_sector_ids: Sequence[int],
    *,
    body_sectors: "int | None" = None,
    work: "Work | None" = None,
) -> tuple[int, ...]:
    """The FAT: the FAT sectors' slots, concatenated and cut to the file's own sectors.

    A FAT sector past the end of the file is an out-of-range **entry**: it contributes
    nothing, and no exception is raised. The table is cut to ``body_sectors`` because the
    FAT is read from fixed-size sectors and may describe sectors the file does not hold
    (which is exactly how ``msg_difat_extended`` declares more FAT sectors than it has).
    """
    if work is None:
        work = Work()
    slots_per_sector = _slots_per_sector(header)
    values: list[int] = []
    for index in fat_sector_ids:
        work.tick(1)
        if body_sectors is not None and index >= body_sectors:
            continue
        values.extend(_sector_slots(data, header.sector_size, index))
    if body_sectors is not None:
        return tuple(values[:body_sectors])
    return tuple(values)


def read_minifat(
    data: bytes, header: CfbHeader, *, body_sectors: "int | None" = None, work: "Work | None" = None
) -> tuple[int, ...]:
    """The miniFAT: the header-declared miniFAT sectors' slots, concatenated.

    [MS-CFB] 2.3.2 notes two sizes for a miniFAT sector -- the header's
    ``num_mini_fat_sectors`` and the number the root mini stream actually needs
    (``ceil(mini_sectors * 4 / sector_size)``); the reader takes the header's count, since
    it is the one a writer commits to, and reads from at most ``body_sectors`` sectors
    whatever the header declares, so a lying count cannot ask for more table reads than the
    file has sectors.
    """
    if work is None:
        work = Work()
    declared = header.num_mini_fat_sectors
    available = declared if body_sectors is None else min(declared, body_sectors)
    values: list[int] = []
    for offset in range(available):
        work.tick(1)
        index = header.first_mini_fat_sector + offset
        if body_sectors is not None and index >= body_sectors:
            break
        values.extend(_sector_slots(data, header.sector_size, index))
    return tuple(values)


# --------------------------------------------------------------- chains


def chain_sectors(
    fat: Sequence[int],
    start: int,
    sector_count: int,
    *,
    bound: "int | None" = None,
    work: "Work | None" = None,
) -> ChainWalk:
    """Walk one sector chain and report a closed fault.

    ``OK`` ends at ``ENDOFCHAIN``/``FREESECT``; a sector already visited is ``CYCLE``; a
    sector the file does not hold is ``OUT_OF_RANGE`` (and is not reported as a member of
    the chain, because it is not a sector of the file); the step bound
    ``4 * sector_count + 16`` (E2's declared bound) catches a runaway a visited set cannot
    (a chain that never repeats but never ends).
    """
    if work is None:
        work = Work()
    limit = 4 * sector_count + 16 if bound is None else bound
    seen: set[int] = set()
    sectors: list[int] = []
    current = start
    for _ in range(limit + 1):
        if current in (ENDOFCHAIN, FREESECT):
            return ChainWalk(tuple(sectors), FAULT_OK)
        work.tick(1)
        if current in seen:
            return ChainWalk(tuple(sectors), FAULT_CYCLE)
        if current >= sector_count:
            return ChainWalk(tuple(sectors), FAULT_OUT_OF_RANGE)
        seen.add(current)
        sectors.append(current)
        current = fat[current] if current < len(fat) else ENDOFCHAIN
    return ChainWalk(tuple(sectors), FAULT_CYCLE)


# --------------------------------------------------------------- the directory


def walk_directory(
    data: bytes,
    header: CfbHeader,
    fat: Sequence[int],
    *,
    limits: CfbLimits = DEFAULT_CFB_LIMITS,
    body_sectors: "int | None" = None,
    work: "Work | None" = None,
) -> "DirectoryWalk | CfbRefusal":
    """The directory: its sector chain, then every 128-byte entry, then the red-black links.

    A revisited directory **sector** is ``cfb_directory_loop``; so is a red-black link that
    re-enters its own tree, a self-reference, or an entry reached from two different
    storages ("a duplicate root"). The entry count is checked against
    ``limits.max_directory_entries`` **before** the entries are parsed, so a lying header
    cannot ask for more parsing than the cap allows. A bad entry name length is a recorded
    entry fault, never an exception.
    """
    if work is None:
        work = Work()
    count = body_sectors if body_sectors is not None else 0
    walk = chain_sectors(fat, header.first_dir_sector, count, work=work)
    if walk.fault == FAULT_CYCLE:
        return CfbRefusal(
            CFB_DIRECTORY_LOOP,
            f"the directory chain revisits sector {header.first_dir_sector}",
        )
    sectors = list(walk.sectors)
    entries_per_sector = header.sector_size // DIRECTORY_ENTRY_BYTES
    directory_entries = 0
    for index in sectors:
        work.tick(1)
        present = _sector_bytes(data, header.sector_size, index)
        directory_entries += len(present) // DIRECTORY_ENTRY_BYTES
    hits = check_caps(limits, directory_entries=directory_entries)
    if hits:
        return CfbRefusal(hits[0].cap_id, _cap_detail(hits[0]), hits[0])

    raw: list[tuple] = []
    for index in sectors:
        present = _sector_bytes(data, header.sector_size, index)
        for offset in range(0, len(present) - DIRECTORY_ENTRY_BYTES + 1, DIRECTORY_ENTRY_BYTES):
            work.tick(1)
            raw.append(_DIRECTORY_STRUCT.unpack(present[offset : offset + DIRECTORY_ENTRY_BYTES]))

    names: list[str] = []
    faults: list[list[str]] = []
    for fields in raw:
        name_length = fields[1]
        entry_faults: list[str] = []
        if name_length and (name_length - 2) % 2:
            entry_faults.append("odd_name_length")
        names.append(_decode_name(fields))
        faults.append(entry_faults)

    total = len(raw)
    links = [(fields[4], fields[5], fields[6]) for fields in raw]
    paths, tree_faults = _entry_paths(raw, names, links, total, work)
    entries = tuple(
        CfbEntry(
            index=index,
            name=names[index],
            entry_type=raw[index][2],
            colour=raw[index][3],
            left=links[index][0],
            right=links[index][1],
            child=links[index][2],
            start=raw[index][11],
            size=raw[index][12] + (raw[index][13] << 32),
            path=paths[index],
            faults=tuple(faults[index]) + tree_faults[index],
        )
        for index in range(total)
    )
    return DirectoryWalk(entries, tuple(sectors), directory_entries)


def _entry_paths(
    raw: Sequence[tuple],
    names: Sequence[str],
    links: Sequence[tuple[int, int, int]],
    total: int,
    work: Work,
) -> "tuple[list[str], list[tuple[str, ...]]]":
    """Posix paths and link faults for every entry, by walking each storage's child tree.

    A node reached twice -- from one tree or from two ("a duplicate root") -- sets the loop
    flag and is not walked again, so the walk always terminates; that is the whole-file
    ``cfb_directory_loop``. A node id **outside** the directory is a lie, not a loop
    ([MS-CFB] 2.6.4): it is skipped and recorded as a stray-link observation, and the file
    still opens (E2's ``mutant_truncated_1200`` is ``out_of_range``, never a directory loop).
    """
    paths = ["" for _ in range(total)]
    faults: list[tuple[str, ...]] = [() for _ in range(total)]
    if total == 0 or raw[0][2] != STGTY_ROOT:
        return paths, faults
    claimed: set[int] = set()
    looped = False
    stray = False

    def walk_tree(root_id: int, prefix: str) -> None:
        nonlocal looped, stray
        stack: list[tuple[int, str]] = [(root_id, prefix)]
        seen: set[int] = set()
        while stack:
            node, parent = stack.pop()
            if node == NOSTREAM:
                continue
            work.tick(1)
            if node in seen or node in claimed:
                looped = True
                continue
            if node >= total:
                stray = True
                continue
            seen.add(node)
            claimed.add(node)
            # The root entry is the container, not a component of a path: its own path is
            # "" and its children are the *top-level* names (`msg-architecture.md`, B1).
            paths[node] = "" if node == 0 else (f"{parent}/{names[node]}" if parent else names[node])
            left, right, child = links[node]
            if child != NOSTREAM and raw[node][2] in (STGTY_STORAGE, STGTY_ROOT):
                walk_tree(child, paths[node])
            stack.append((left, parent))
            stack.append((right, parent))

    walk_tree(0, "")
    for index in range(1, total):
        if raw[index][2] == STGTY_STORAGE and index not in claimed:
            claimed.add(index)
            paths[index] = names[index]
            if links[index][2] != NOSTREAM:
                walk_tree(links[index][2], names[index])
    if looped:
        faults[0] = faults[0] + (_LOOP_FLAG,)
    if stray:
        faults[0] = faults[0] + (_STRAY_LINK_FLAG,)
    return paths, faults


def _decode_name(fields: tuple) -> str:
    """An entry name's best-effort decode: the declared length, capped at the 64-byte field."""
    name_raw, name_length = fields[0], fields[1]
    wanted = max(min(name_length - 2, _NAME_FIELD) // 2 * 2, 0)
    return name_raw[:wanted].decode("utf-16-le", "replace")


_LOOP_FLAG = "directory_loop"
_STRAY_LINK_FLAG = "directory_link_out_of_range"


def _has_loop(walk: DirectoryWalk) -> bool:
    return any(_LOOP_FLAG in entry.faults for entry in walk.entries)


def lookup_entry(entries: Sequence[CfbEntry], path: str) -> "CfbEntry | None":
    """An entry by posix path, case-insensitively ([MS-CFB] 2.6.4 comparator).

    The comparator is "compare the character count first, then the uppercased name", which
    for an exact lookup is the same as requiring the same segment count and an uppercase
    match. ``None`` when nothing matches.
    """
    if not path:
        return None
    wanted = [segment.upper() for segment in path.strip("/").split("/") if segment]
    for entry in entries:
        if not entry.path or entry.path == "<root>":
            continue
        parts = [segment for segment in entry.path.split("/") if segment]
        if len(parts) != len(wanted):
            continue
        if all(left.upper() == right for left, right in zip(parts, wanted)):
            return entry
    return None


# --------------------------------------------------------------- streams


def _root_mini_bytes(
    data: bytes, header: CfbHeader, fat: Sequence[int], root: CfbEntry, body_sectors: int, work: Work
) -> "tuple[bytes, ChainWalk]":
    """The root entry's mini stream: the FAT chain's bytes, cut to its declared size."""
    walk = chain_sectors(fat, root.start, body_sectors, work=work)
    payload = bytearray()
    for index in walk.sectors:
        payload += _sector_bytes(data, header.sector_size, index)
    return bytes(payload[: root.size]), walk


def _chain_and_bytes(
    data: bytes,
    header: CfbHeader,
    fat: Sequence[int],
    minifat: Sequence[int],
    mini_bytes: bytes,
    mini_sector_count: int,
    start: int,
    size: int,
    mini: bool,
    body_sectors: int,
    work: Work,
) -> "tuple[tuple[int, ...], bytes, str]":
    """One stream's chain and its available bytes, with a closed fault.

    Never sized from ``size``: the payload is whatever the chain actually holds, and a
    chain fault wins over the length comparison.
    """
    if size == 0:
        work.tick(1)
        return (), b"", FAULT_OK
    if mini:
        walk = chain_sectors(minifat, start, mini_sector_count, work=work)
        parts = bytearray()
        for index in walk.sectors:
            parts += mini_bytes[index * MINI_SECTOR_BYTES : (index + 1) * MINI_SECTOR_BYTES]
        payload = bytes(parts)
    else:
        walk = chain_sectors(fat, start, body_sectors, work=work)
        parts = bytearray()
        for index in walk.sectors:
            parts += _sector_bytes(data, header.sector_size, index)
        payload = bytes(parts)
    if walk.fault != FAULT_OK:
        return walk.sectors, payload, walk.fault
    if len(payload) < size:
        return walk.sectors, payload, FAULT_SHORT_CHAIN
    return walk.sectors, payload, FAULT_OK


def _stream_results(
    data: bytes,
    header: CfbHeader,
    fat: Sequence[int],
    minifat: Sequence[int],
    entries: Sequence[CfbEntry],
    body_sectors: int,
    work: Work,
) -> tuple[StreamResult, ...]:
    """Every live stream's chain walk, the root's mini stream included."""
    root = entries[0] if entries else None
    mini_bytes = b""
    mini_sector_count = 0
    results: list[StreamResult] = []
    if root is not None and root.size and root.start not in (ENDOFCHAIN, FREESECT):
        mini_bytes, root_walk = _root_mini_bytes(data, header, fat, root, body_sectors, work)
        mini_sector_count = (root.size + MINI_SECTOR_BYTES - 1) // MINI_SECTOR_BYTES
        results.append(
            StreamResult(
                path="<root>",
                mini=False,
                start=root.start,
                size=root.size,
                sectors=root_walk.sectors,
                available=len(mini_bytes),
                fault=root_walk.fault
                if root_walk.fault != FAULT_OK
                else (FAULT_SHORT_CHAIN if len(mini_bytes) < root.size else FAULT_OK),
            )
        )
    for entry in entries:
        if not entry.is_stream or not entry.path:
            continue
        mini = 0 < entry.size < header.mini_cutoff
        sectors, payload, fault = _chain_and_bytes(
            data,
            header,
            fat,
            minifat,
            mini_bytes,
            mini_sector_count,
            entry.start,
            entry.size,
            mini,
            body_sectors,
            work,
        )
        results.append(
            StreamResult(
                path=entry.path,
                mini=mini,
                start=entry.start,
                size=entry.size,
                sectors=sectors,
                available=len(payload),
                fault=fault,
            )
        )
    return tuple(results)


def read_stream(cfb: CfbFile, target: "str | CfbEntry") -> "tuple[bytes, str]":
    """One stream's bytes and its closed fault, for either stream kind.

    ``target`` is a posix path (``"__substg1.0_007D001F"``, or ``"<root>"`` for the root
    entry's mini stream) or an entry from :attr:`CfbFile.entries`. An unknown path is an
    empty stream with ``out_of_range``. The bytes are **never** fabricated to the declared
    length: a ``2**40`` claim on a one-sector chain returns that sector plus
    ``short_chain``.
    """
    entry: "CfbEntry | None" = None
    if isinstance(target, CfbEntry):
        entry = target
    elif target == "<root>":
        entry = cfb.root
    else:
        entry = lookup_entry(cfb.entries, target)
    if entry is None:
        return b"", FAULT_OUT_OF_RANGE
    if target == "<root>" or (isinstance(target, CfbEntry) and target.index == 0):
        payload, walk = _root_mini_bytes(
            cfb.data, cfb.header, cfb.fat, entry, cfb.body_sectors, cfb.work
        )
        fault = walk.fault if walk.fault != FAULT_OK else (
            FAULT_SHORT_CHAIN if len(payload) < entry.size else FAULT_OK
        )
        return payload[: entry.size], fault
    mini_bytes, _ = _root_mini_bytes(cfb.data, cfb.header, cfb.fat, cfb.root, cfb.body_sectors, cfb.work)
    mini_sector_count = (cfb.root.size + MINI_SECTOR_BYTES - 1) // MINI_SECTOR_BYTES
    mini = 0 < entry.size < cfb.header.mini_cutoff
    _sectors, payload, fault = _chain_and_bytes(
        cfb.data,
        cfb.header,
        cfb.fat,
        cfb.minifat,
        mini_bytes,
        mini_sector_count,
        entry.start,
        entry.size,
        mini,
        cfb.body_sectors,
        cfb.work,
    )
    return payload[: entry.size], fault


# --------------------------------------------------------------- accounting


def classify_sectors(cfb: CfbFile) -> "tuple[tuple[tuple[str, int], ...], int]":
    """Every sector-sized window's class, and the bytes no class claims.

    Windows are classified in a fixed priority (``header`` first, then ``difat``, ``fat``,
    ``minifat``, ``directory``, ``stream``), keyed on the header-declared miniFAT range,
    the DIFAT walk's FAT/DIFAT sectors and the entries' chains -- **not** on the FAT's
    ``FATSECT``/``DIFSECT`` markers. An unclaimed window is ``free`` when the FAT marks it
    ``FREESECT``, ``slack`` when it is the file's partial tail, and otherwise
    ``unaccounted`` (the sectors a cyclic or broken chain put out of reach). The eight
    classes plus ``unaccounted`` sum to the file length, on any input.
    """
    work = cfb.work
    work.tick(1)
    size = cfb.header.sector_size
    count = cfb.sector_count
    claims: dict[int, str] = {}

    def claim(index: int, name: str) -> None:
        # Sector ids count from the file's first sector *after* the header's window
        # (`_sector_bytes`: window ``index + 1``), so the ids that can be claimed run
        # ``0 .. body_sectors - 1``.
        if 0 <= index < max(count - 1, 0) and index not in claims:
            claims[index] = name

    declared_minifat = min(cfb.header.num_mini_fat_sectors, max(count - 1, 0))
    for offset in range(declared_minifat):
        claim(cfb.header.first_mini_fat_sector + offset, "minifat")
    for index in cfb.difat_sectors:
        claim(index, "difat")
    for index in cfb.fat_sector_ids:
        claim(index, "fat")
    for index in cfb.directory_sectors:
        claim(index, "directory")
    for stream in cfb.streams:
        # A mini stream's ``sectors`` are *mini* sector indices -- positions inside the root's
        # mini stream -- so they are not sector ids of the file and claim nothing; the root's
        # own chain (the ``<root>`` result) claims the real sectors that hold them.
        if stream.mini:
            continue
        for index in stream.sectors:
            claim(index, "stream")

    totals = {name: 0 for name in SECTOR_CLASSES}
    totals["header"] = _window_bytes(cfb.data, size, 0)
    unaccounted = 0
    for index in range(max(count - 1, 0)):
        present = _window_bytes(cfb.data, size, index + 1)
        if not present:
            continue
        name = claims.get(index)
        if name is None:
            slot = cfb.fat[index] if index < len(cfb.fat) else FREESECT
            if slot == FREESECT:
                name = "free"
            elif present < size:
                name = "slack"
            else:
                name = "unaccounted"
                unaccounted += present
                continue
        totals[name] += present
    return tuple((name, totals[name]) for name in SECTOR_CLASSES), unaccounted


# --------------------------------------------------------------- the opener


def open_cfb(
    data: bytes,
    *,
    limits: CfbLimits = DEFAULT_CFB_LIMITS,
    require_properties: bool = True,
    work: "Work | None" = None,
) -> "CfbFile | CfbRefusal":
    """Open one CFB container, returning a :class:`CfbFile` or a closed refusal.

    Never raises, never hangs and never allocates from a declared length. The order is the
    contract's: the header, then the sector-count cap, then the DIFAT (with the
    chain-length cap), then the FAT and the miniFAT, then the directory (with the
    entry-count cap and the loop checks), then ``not_a_message``, then every stream's chain
    and the sector accounting.

    ``require_properties`` is the ``not_a_message`` check ("CFB magic but no top-level
    ``__properties_version1.0``", D14). It is on by default, because a CFB file is a
    message only if it carries that stream; the ``olefile`` cross-check turns it off to
    read a well-formed container that is not a message (Turn 1b.2's
    ``msg_mini_cutoff_boundary`` has three plain streams and no property stream).
    """
    if work is None:
        work = Work()
    work.tick(1)
    parsed = parse_header(data)
    if isinstance(parsed, CfbRefusal):
        return parsed
    header = parsed
    sector_count = sector_windows(len(data), header.sector_size)
    body_sectors = max(sector_count - 1, 0)

    hits = check_caps(limits, sector_count=sector_count)
    if hits:
        return CfbRefusal(hits[0].cap_id, _cap_detail(hits[0]), hits[0])

    difat = walk_difat(header, data, limits=limits, body_sectors=body_sectors, work=work)
    if isinstance(difat, CfbRefusal):
        return difat
    fat = read_fat(data, header, difat.fat_sector_ids, body_sectors=body_sectors, work=work)
    minifat = read_minifat(data, header, body_sectors=body_sectors, work=work)
    directory = walk_directory(
        data, header, fat, limits=limits, body_sectors=body_sectors, work=work
    )
    if isinstance(directory, CfbRefusal):
        return directory
    if _has_loop(directory):
        return CfbRefusal(CFB_DIRECTORY_LOOP, "a directory link re-enters its own child tree")
    entries = directory.entries
    if require_properties and lookup_entry(entries, PROPERTIES_STREAM) is None:
        return CfbRefusal(
            NOT_A_MESSAGE,
            f"CFB container without a top-level {PROPERTIES_STREAM!r} stream",
        )

    streams = _stream_results(data, header, fat, minifat, entries, body_sectors, work)
    faults = tuple(
        (stream.path, stream.fault, FAULT_REASON_IDS[stream.fault])
        for stream in streams
        if stream.fault != FAULT_OK
    )
    cfb = CfbFile(
        data=data,
        header=header,
        fat_sector_ids=difat.fat_sector_ids,
        difat_sectors=difat.difat_sectors,
        extended_difat=difat.extended,
        difat_fault=difat.fault,
        fat=fat,
        minifat=minifat,
        entries=entries,
        directory_sectors=directory.sectors,
        directory_entries=directory.directory_entries,
        sector_count=sector_count,
        streams=streams,
        faults=faults,
        accounting=(),
        unaccounted=0,
        work=work,
    )
    accounting, unaccounted = classify_sectors(cfb)
    return replace(cfb, accounting=accounting, unaccounted=unaccounted)
