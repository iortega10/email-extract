"""Phase 1b: the owner's structure-only probe of a local real ``.msg`` sample (P1-P6).

The owner runs this over their own mail folder; the output is **counts, sizes, tag sets
and presence lines only** and is pasted back as an aggregate note in
``docs/design/open-inputs.md``.  Nothing here prints a value: no subject, address,
header text, filename, body or stream content, and no raw tag value other than the
code-page numbers and the closed vocabularies ``docs/design/phase1b-probes.md`` names.
``docs/design/phase1b-probes.md`` is the specification; this script prints exactly the
schema there and nothing more.

Privacy rules kept from ``tools/real_probe.py`` and extended:

* it **refuses a path inside this repository** (``is_relative_to`` -> exit 2) and
  additionally refuses the ``fixtures/`` tree;
* the only streams it reads for their bytes are the structural
  ``__properties_version1.0`` tables (tag words, types, sizes -- values are not
  interpreted), plus exactly two named property streams, read only to *bucket* and
  never to print: ``__substg1.0_001A001F`` (the message class, P1's three buckets) and
  ``__substg1.0_10130102`` (the HTML body, P6's literal-token counts, in-process); it
  never opens a body stream (``0x1000``/``0x1009``) or the transport-header stream
  (``0x007D``) for reading;
* a malformed ``.msg`` never raises: it is counted in an ``unreadable`` tally with a
  closed reason and the probe continues.

``olefile`` is a **dev tool** used by this script alone; the library never imports it
and it is not a dependency (see ``tools/real_probe.py``).

Run:  python tools/msg_probe.py --probe <P1..P6> <DIR> [--limit N]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PROBES = ("P1", "P2", "P3", "P4", "P5", "P6")

SUBSTG_PREFIX = "__substg1.0_"
TOP_LEVEL_HEADER = 32
SUB_STORAGE_HEADER = 8

BODY_TAGS = (0x1000, 0x1009, 0x1013)
ATTACH_METHOD_TAG = 0x3705
MESSAGE_CLASS_TAG = 0x001A
TIME_TAGS = (0x0039, 0x0E06, 0x3007, 0x3008)
RECIP_TYPE_TAGS = (0x3002, 0x3003)
HTML_LITERALS = (b"divRplyFwdMsg", b"appendonsend", b"x_", b"blockquote")

#: the closed set of why one file is counted unreadable.
UNREADABLE_REASONS = ("not_ole", "ole_open_failed", "no_properties_table")


def u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def _substg(tag: int, vt: int) -> str:
    return f"{SUBSTG_PREFIX}{tag:04X}{vt:04X}"


def read_property_table(ole, storage: list[str] | None) -> list[tuple[int, int, int]] | None:
    """``(tag, type, data_word)`` rows of one ``__properties_version1.0`` table, or ``None``.

    ``storage`` is the storage path (a list, top-level ``None``).  ``data_word`` is the
    first data word: for a fixed-size ``PT_LONG`` it is the value itself (the only value
    this probe interprets, and only for its closed 1-to-6 attachment-method census); a
    variable-size entry's first data word is its stream size.  No other value is read.
    """
    path = (list(storage) + ["__properties_version1.0"]) if storage else ["__properties_version1.0"]
    try:
        data = ole.openstream(path).read()
    except Exception:  # noqa: BLE001 -- a missing table is a recorded absence, not a crash
        return None
    header = SUB_STORAGE_HEADER if storage else TOP_LEVEL_HEADER
    body = data[header:]
    return [(u32(body, i * 16) >> 16, u32(body, i * 16) & 0xFFFF, u32(body, i * 16 + 8))
            for i in range(len(body) // 16)]


def stream_paths(ole) -> list[list[str]]:
    return sorted(ole.listdir(streams=True, storages=False))


def storage_paths(ole) -> list[list[str]]:
    return sorted(ole.listdir(streams=False, storages=True))


def size_of(ole, path: list[str]) -> int | None:
    try:
        return ole.get_size(path)
    except Exception:  # noqa: BLE001
        return None


def message_class_bucket(ole) -> str:
    """The P1 class bucket -- read the class stream only to bucket it, never printed."""
    try:
        raw = ole.openstream([_substg(MESSAGE_CLASS_TAG, 0x001F)]).read()
    except Exception:  # noqa: BLE001
        return "other"
    text = raw.decode("utf-16-le", "replace").rstrip("\x00")
    if text.startswith("IPM.Note.SMIME"):
        return "smime"
    if text.startswith("IPM.Note.Secure"):
        return "secure"
    if text.startswith("IPM.Note"):
        return "note"
    return "other"


# --------------------------------------------------------------------- probes


def probe_p1(files, olefile) -> list[str]:
    scanned = 0
    buckets = {"note": 0, "smime": 0, "secure": 0, "other": 0}
    body_present = {0x1000: 0, 0x1009: 0, 0x1013: 0}
    methods = {n: 0 for n in range(1, 7)}
    sizes: list[int] = []
    scanned = sum(1 for _ in files)
    for path in files:
        ole = olefile.OleFileIO(str(path))
        try:
            buckets[message_class_bucket(ole)] += 1
            top = read_property_table(ole, None) or []
            top_tags = {tag for tag, _vt, _d0 in top}
            for tag in BODY_TAGS:
                if tag in top_tags:
                    body_present[tag] += 1
            for storage in (s for s in storage_paths(ole) if s[0].startswith("__attach_version1.0")):
                entries = read_property_table(ole, storage) or []
                for tag, vt, d0 in entries:
                    if tag == ATTACH_METHOD_TAG and vt == 0x0003:
                        value = d0 & 0xFFFFFFFF
                        if value in methods:
                            methods[value] += 1
                for sub in stream_paths(ole):
                    if sub[: len(storage)] == storage and sub[-1].startswith(_substg(0x3701, 0x0102)):
                        size = size_of(ole, sub)
                        if size is not None:
                            sizes.append(size)
        finally:
            ole.close()
    return [
        f"P1 signed/encrypted layout -- {scanned} files scanned",
        f"class buckets: IPM.Note={buckets['note']}  IPM.Note.SMIME*={buckets['smime']}  "
        f"IPM.Note.Secure*={buckets['secure']}  other={buckets['other']}",
        f"body streams:  0x1000 present={body_present[0x1000]}  "
        f"0x1009 present={body_present[0x1009]}  0x1013 present={body_present[0x1013]}",
        "attachments:   " + "  ".join(f"method={n}:{methods[n]}" for n in range(1, 7)),
        "attachment sizes (bytes, sorted): " + " ".join(str(s) for s in sorted(sizes)),
    ]


def probe_p2(files, olefile) -> list[str]:
    present = {tag: 0 for tag in TIME_TAGS}
    types: dict[int, set[int]] = {tag: set() for tag in TIME_TAGS}
    lines = []
    count = sum(1 for _ in files)
    for path in files:
        ole = olefile.OleFileIO(str(path))
        try:
            entries = read_property_table(ole, None)
            if entries is None:
                continue
            seen: dict[int, set[int]] = {}
            for tag, vt, _d0 in entries:
                seen.setdefault(tag, set()).add(vt)
            for tag in TIME_TAGS:
                if tag in seen:
                    present[tag] += 1
                    types[tag] |= seen[tag]
        finally:
            ole.close()
    lines.append(f"P2 time property tags -- {count} files")
    for tag in TIME_TAGS:
        joined = ",".join(f"{vt:04x}" for vt in sorted(types[tag])) or "-"
        lines.append(f"{tag:04x}: present={present[tag]}  types={joined}")
    return lines


def probe_p3(files, olefile) -> list[str]:
    versions: dict[int, int] = {}
    sector_sizes: dict[int, int] = {}
    minifat_used = 0
    difat_lengths: dict[int, int] = {}
    dir_entries: dict[int, int] = {}
    size_buckets = {"<4KiB": 0, "4KiB-1MiB": 0, "1-8MiB": 0, ">8MiB": 0}
    count = 0
    for path in files:
        count += 1
        ole = olefile.OleFileIO(str(path))
        try:
            sector_size = ole.sectorsize
            version = 4 if sector_size == 4096 else 3
            versions[version] = versions.get(version, 0) + 1
            sector_sizes[sector_size] = sector_sizes.get(sector_size, 0) + 1
            if ole.num_mini_fat_sectors:
                minifat_used += 1
            length = 1 + int(ole.num_difat_sectors or 0)
            difat_lengths[length] = difat_lengths.get(length, 0) + 1
            n_entries = len(ole.direntries or [])
            dir_entries[n_entries] = dir_entries.get(n_entries, 0) + 1
            largest = max((size_of(ole, s) or 0 for s in stream_paths(ole)), default=0)
            if largest < 4 * 1024:
                size_buckets["<4KiB"] += 1
            elif largest < 1024 * 1024:
                size_buckets["4KiB-1MiB"] += 1
            elif largest <= 8 * 1024 * 1024:
                size_buckets["1-8MiB"] += 1
            else:
                size_buckets[">8MiB"] += 1
        finally:
            ole.close()
    return [
        f"P3 CFB layout -- {count} files",
        "version:      " + "  ".join(f"{k}={v}" for k, v in sorted(versions.items())),
        "sector size:  " + "  ".join(f"{k}={v}" for k, v in sorted(sector_sizes.items())),
        f"miniFAT used: {minifat_used}/{count}",
        "difat length histogram: " + "  ".join(f"{k}={v}" for k, v in sorted(difat_lengths.items()))
        + f"   (>1 = extended present: {sum(v for k, v in difat_lengths.items() if k > 1)})",
        "directory entries histogram: " + "  ".join(f"{k}={v}" for k, v in sorted(dir_entries.items())),
        "stream size buckets: " + "  ".join(f"{k}={v}" for k, v in size_buckets.items()),
    ]


def probe_p4(files, olefile) -> list[str]:
    attach_union: set[tuple[int, int]] = set()
    recip_union: set[tuple[int, int]] = set()
    methods = {n: 0 for n in range(1, 7)}
    recip_types = {0x3002: 0, 0x3003: 0}
    count = 0
    for path in files:
        count += 1
        ole = olefile.OleFileIO(str(path))
        try:
            for storage in storage_paths(ole):
                entries = read_property_table(ole, storage)
                if entries is None:
                    continue
                if storage[0].startswith("__attach_version1.0"):
                    for tag, vt, d0 in entries:
                        attach_union.add((tag, vt))
                        if tag == ATTACH_METHOD_TAG and vt == 0x0003:
                            value = d0 & 0xFFFFFFFF
                            if value in methods:
                                methods[value] += 1
                elif storage[0].startswith("__recip_version1.0"):
                    for tag, vt, _d0 in entries:
                        recip_union.add((tag, vt))
                        if tag in recip_types:
                            recip_types[tag] += 1
        finally:
            ole.close()
    return [
        f"P4 attachment/recipient tags -- {count} files",
        "attach tag:type union: " + " ".join(f"{t:04x}:{v:04x}" for t, v in sorted(attach_union)),
        "recip  tag:type union: " + " ".join(f"{t:04x}:{v:04x}" for t, v in sorted(recip_union)),
        "attach methods: " + "  ".join(f"{n}={methods[n]}" for n in range(1, 7)),
        f"recipient address types: 3002=001F(smtp)={recip_types[0x3002]}  "
        f"3003=001F(ex)={recip_types[0x3003]}",
    ]


def probe_p5(files, olefile) -> list[str]:
    censuses = {tag: {0x001F: 0, 0x001E: 0, "other": 0} for tag in BODY_TAGS + (0x007D,)}
    count = 0
    for path in files:
        count += 1
        ole = olefile.OleFileIO(str(path))
        try:
            entries = read_property_table(ole, None)
            if entries is None:
                continue
            seen: dict[int, set[int]] = {}
            for tag, vt, _d0 in entries:
                seen.setdefault(tag, set()).add(vt)
            for tag in censuses:
                for vt in seen.get(tag, set()):
                    if vt in (0x001F, 0x001E):
                        censuses[tag][vt] += 1
                    else:
                        censuses[tag]["other"] += 1
        finally:
            ole.close()
    lines = [f"P5 8-bit prevalence -- {count} files"]
    for tag in (0x007D, 0x1000, 0x1013):
        census = censuses[tag]
        lines.append(f"{tag:04X} type census: 001F={census[0x001F]}  001E={census[0x001E]}  "
                     f"other={census['other']}")
    return lines


def probe_p6(files, olefile) -> list[str]:
    counts = {lit: 0 for lit in HTML_LITERALS}
    with_html = 0
    for path in files:
        ole = olefile.OleFileIO(str(path))
        try:
            try:
                html = ole.openstream([_substg(0x1013, 0x0102)]).read()
            except Exception:  # noqa: BLE001
                continue
            with_html += 1
            for lit in HTML_LITERALS:
                if lit in html:
                    counts[lit] += 1
        finally:
            ole.close()
    return [
        f"P6 vendor HTML classes -- {with_html} files with 0x1013",
        f"divRplyFwdMsg: {counts[b'divRplyFwdMsg']}/{with_html}   "
        f"appendonsend: {counts[b'appendonsend']}/{with_html}   "
        f"x_ prefix: {counts[b'x_']}/{with_html}   "
        f"blockquote: {counts[b'blockquote']}/{with_html}",
    ]


PROBE_FUNCS = {"P1": probe_p1, "P2": probe_p2, "P3": probe_p3, "P4": probe_p4, "P5": probe_p5, "P6": probe_p6}


def main(argv: list[str]) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[0])
        print("usage: python tools/msg_probe.py --probe <P1..P6> <DIR> [--limit N]")
        return 0
    probe = None
    target = None
    limit = None
    rest = list(argv)
    while rest:
        token = rest.pop(0)
        if token == "--probe" and rest:
            probe = rest.pop(0).upper()
        elif token == "--limit" and rest:
            limit = int(rest.pop(0))
        elif target is None:
            target = token
        else:
            print(f"unexpected argument: {token}")
            return 2
    if probe not in PROBES or target is None:
        print("usage: python tools/msg_probe.py --probe <P1..P6> <DIR> [--limit N]")
        return 2
    try:
        import olefile
    except ImportError:
        print("olefile is not installed (dev tool only): python -m pip install olefile")
        return 3

    directory = Path(target).expanduser()
    try:
        directory = directory.resolve()
    except OSError as exc:
        print(f"cannot resolve {target!r}: {exc}")
        return 2
    if directory.is_relative_to(REPO_ROOT):
        print(f"refused: {directory} is inside the repository; point msg_probe at a folder outside it")
        return 2
    if not directory.is_dir():
        print(f"not a directory: {directory}")
        return 2
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() == ".msg")
    if not files:
        print(f"no .msg files under {directory}")
        return 2
    if limit is not None:
        files = files[:limit]

    readable = []
    unreadable: dict[str, int] = {}
    for path in files:
        try:
            if not olefile.isOleFile(str(path)):
                unreadable["not_ole"] = unreadable.get("not_ole", 0) + 1
                continue
            readable.append(path)
        except Exception:  # noqa: BLE001
            unreadable["not_ole"] = unreadable.get("not_ole", 0) + 1

    lines: list[str] = []
    try:
        lines = PROBE_FUNCS[probe](readable, olefile)
    except Exception as exc:  # noqa: BLE001 -- a malformed file is a tally, never a crash
        lines = [f"{probe}: aborted on a malformed file: {type(exc).__name__}"]
    for line in lines:
        print(line)
    if unreadable:
        joined = "  ".join(f"{reason}:{count}" for reason, count in sorted(unreadable.items()))
        print(f"unreadable: {sum(unreadable.values())}  [{joined}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
