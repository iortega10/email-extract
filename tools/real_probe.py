"""Phase 0 Turn 0.0: structure-only probe of a local real ``.msg`` sample (D13).

Prints **structure only**: stream names and sizes, storage layout, plain/HTML/RTF body
stream presence, the transport-header stream, recipient and attachment storage counts,
the string-property type (UTF-16 vs 8-bit), the observed property-tag set, and the
presence of the code-page / flag properties that live *inside* ``__properties_version1.0``
(as fixed-size entries, not streams -- the design's measured claim).  No property value
and no stream content is ever printed; only the fixed-size property tables are read, and
their values are parsed and discarded (tags, types and sizes only).

Takes a path on the command line.  Refuses any path inside this repository: real samples
stay outside the repo (e.g. the owner's own export), and no real mail enters this tool's
input, output, logs or the spike table.

Run:  python tools/real_probe.py C:\\path\\to\\sample.msg

Requires: olefile (dev tool only; the parser itself never imports it).

Layout assumptions are self-checked at run time (see ``SELF CHECK`` lines): every
16-byte property entry is read as ``u32 = (tag << 16) | type`` (the same encoding the
``__substg1.0_<tag><type>`` stream names use), and each variable-size entry must resolve
to an existing stream with the recorded size -- a wrong assumption is visible in the
output instead of silent.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

VT_NAMES = {
    0x0001: "PT_NULL",
    0x0002: "PT_I2",
    0x0003: "PT_LONG",
    0x0004: "PT_R4",
    0x0005: "PT_DOUBLE",
    0x0006: "PT_CURRENCY",
    0x0007: "PT_APPTIME",
    0x000A: "PT_ERROR",
    0x000B: "PT_BOOLEAN",
    0x000D: "PT_OBJECT",
    0x0014: "PT_I8",
    0x001E: "PT_STRING8",
    0x001F: "PT_UNICODE",
    0x0040: "PT_SYSTIME",
    0x0048: "PT_CLSID",
    0x0102: "PT_BINARY",
    0x1003: "PT_MV_LONG",
    0x100B: "PT_MV_BOOLEAN",
    0x1014: "PT_MV_I8",
    0x101E: "PT_MV_STRING8",
    0x101F: "PT_MV_UNICODE",
    0x1040: "PT_MV_SYSTIME",
    0x1048: "PT_MV_CLSID",
    0x1102: "PT_MV_BINARY",
}
MV_VT = {0x1003, 0x100B, 0x1014, 0x101E, 0x101F, 0x1040, 0x1048, 0x1102}
VARIABLE_VT = {0x001E, 0x001F, 0x0048, 0x000D, 0x0102} | MV_VT
STRING_VT = {0x001E, 0x001F, 0x101E, 0x101F}

KNOWN_TAG_NAMES = {
    0x0037: "Subject",
    0x007D: "TransportMessageHeaders",
    0x1000: "Body",
    0x1009: "RtfCompressed",
    0x1013: "Html",
    0x3FDE: "InternetCodepage",    # PidTagInternetCodepage (PT_LONG)
    0x3FFD: "MessageCodepage",     # PidTagMessageCodepage (PT_LONG)
}

BODY_TAGS = (0x1000, 0x1009, 0x1013)
CODE_PAGE_TAGS = (0x3FDE, 0x3FFD)

TOP_LEVEL_HEADER = 32   # MS-OXMSG: 8 reserved + 4+4+4+4 counts + 8 reserved
SUB_STORAGE_HEADER = 8   # MS-OXMSG: 8 reserved


SUBSTG_PREFIX = "__substg1.0_"


def parse_substg_name(name: str) -> tuple[int, int, bool] | None:
    """``__substg1.0_<tag><type>[-suffix]`` -> (tag, vt, has_suffix) or None."""
    if not name.startswith(SUBSTG_PREFIX):
        return None
    rest = name[len(SUBSTG_PREFIX):]
    has_suffix = False
    if "-" in rest:
        rest = rest.partition("-")[0]
        has_suffix = True
    if len(rest) != 8:
        return None
    try:
        return int(rest[:4], 16), int(rest[4:], 16), has_suffix
    except ValueError:
        return None


def vt_name(vt: int) -> str:
    return VT_NAMES.get(vt, f"vt=0x{vt:04X}")


def tag_name(tag: int) -> str:
    name = KNOWN_TAG_NAMES.get(tag)
    return f"{name}(0x{tag:04X})" if name else f"0x{tag:04X}"


def u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "little")


class StorageIndex:
    """Names and sizes only -- the probe never reads stream bodies."""

    def __init__(self, ole):
        self.ole = ole
        self.streams = sorted(ole.listdir(streams=True, storages=False))
        self.storages = sorted(ole.listdir(streams=False, storages=True))
        self.stream_sizes = {"/".join(p): ole.get_size(p) for p in self.streams}
        self.storage_names = {"/".join(p) for p in self.storages}

    def size_of(self, posix_path: str) -> int | None:
        return self.stream_sizes.get(posix_path)

    def is_storage(self, posix_path: str) -> bool:
        return posix_path in self.storage_names


def parse_property_table(
    data: bytes, header_size: int, index: StorageIndex, storage_path: list[str]
) -> tuple[list[str], list[dict]]:
    """Parse a ``__properties_version1.0`` table; emit tags/types/sizes only."""
    lines: list[str] = []
    body = data[header_size:]
    n_entries = len(body) // 16
    if len(body) % 16:
        lines.append(
            f"    note: {len(body)}B after {header_size}B header is not a multiple "
            f"of 16 ({len(body) % 16}B trailing)"
        )

    entries: list[dict] = []
    composite_ok = 0
    size_orientation = {"d0=size": 0, "d1=size": 0, "unresolved": 0,
                        "storage-backed": 0, "stream absent": 0}
    for i in range(n_entries):
        off = i * 16
        w0 = u32(body, off)
        tag, vt = w0 >> 16, w0 & 0xFFFF
        d0, d1 = u32(body, off + 8), u32(body, off + 12)
        if tag and vt in VT_NAMES:
            composite_ok += 1
        entry = {"tag": tag, "vt": vt, "d0": d0, "d1": d1, "kind": "fixed",
                 "where": None, "size": None}
        if vt in VARIABLE_VT:
            entry["kind"] = "variable"
            stream_path = "/".join(
                storage_path + [f"__substg1.0_{tag:04X}{vt:04X}"]
            )
            size = index.size_of(stream_path)
            if size is not None:
                entry["where"] = "stream"
                entry["size"] = size
            else:
                suffixed = sorted(
                    k for k in index.stream_sizes if k.startswith(stream_path + "-")
                )
                if suffixed:
                    entry["where"] = "stream"
                    entry["size"] = sum(index.stream_sizes[k] for k in suffixed)
                    entry["suffixed"] = len(suffixed)
                elif index.is_storage(stream_path) or any(
                    k.startswith(stream_path + "-") for k in index.storage_names
                ):
                    entry["where"] = "storage"
                else:
                    entry["where"] = "absent"
            if entry["where"] == "stream":
                if d0 == entry["size"]:
                    size_orientation["d0=size"] += 1
                elif d1 == entry["size"]:
                    size_orientation["d1=size"] += 1
                else:
                    size_orientation["unresolved"] += 1
            elif entry["where"] == "storage":
                size_orientation["storage-backed"] += 1
            else:
                size_orientation["stream absent"] += 1
        entries.append(entry)

    lines.append(
        f"    SELF CHECK entry encoding: (tag<<16)|type matches a known type in "
        f"{composite_ok}/{n_entries} entries"
    )
    odd = [f"{e['tag']:04X}:{e['vt']:04X}" for e in entries
           if not (e["tag"] and e["vt"] in VT_NAMES)]
    if odd:
        shown = ", ".join(odd[:6]) + (" ..." if len(odd) > 6 else "")
        lines.append(f"    entries with non-standard tag/type word: {shown}")
    n_var = sum(1 for e in entries if e["kind"] == "variable")
    if n_var:
        lines.append(
            f"    SELF CHECK variable entries: {n_var}; data position "
            f"{size_orientation}"
        )
        odd_size = [
            f"{e['tag']:04X}:{vt_name(e['vt'])}(d0={e['d0']},d1={e['d1']},size={e['size']})"
            for e in entries
            if e["kind"] == "variable" and e["where"] == "stream"
            and e["d0"] != e["size"] and e["d1"] != e["size"]
        ]
        if odd_size:
            shown = ", ".join(odd_size[:4]) + (" ..." if len(odd_size) > 4 else "")
            lines.append(f"    size field not at d0/d1: {shown}")
    return lines, entries


def fmt_entry(e: dict) -> str:
    tag, vt = e["tag"], e["vt"]
    if e["kind"] == "fixed":
        return f"{tag:04X}:{vt_name(vt)}"
    where = e["where"]
    if where == "stream":
        extra = f" in {e['suffixed']} suffixed streams" if e.get("suffixed") else ""
        return f"{tag:04X}:{vt_name(vt)}(stream {e['size']}B{extra})"
    if where == "storage":
        return f"{tag:04X}:{vt_name(vt)}(nested storage)"
    return f"{tag:04X}:{vt_name(vt)}(stream ABSENT)"


def main(argv: list[str]) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if len(argv) != 1:
        print("usage: python tools/real_probe.py <path-outside-the-repo>")
        return 2
    if argv[0] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[0])
        print("usage: python tools/real_probe.py <path-outside-the-repo>")
        return 0
    try:
        import olefile
    except ImportError:
        print("olefile is not installed (dev tool only): python -m pip install olefile")
        return 3

    target = Path(argv[0]).expanduser()
    try:
        target = target.resolve()
    except OSError as exc:
        print(f"cannot resolve {argv[0]!r}: {exc}")
        return 2
    if target.is_relative_to(REPO_ROOT):
        print(
            f"refused: {target} is inside the repository {REPO_ROOT}. "
            "real_probe takes a real sample kept outside the repo."
        )
        return 2
    if not target.is_file():
        print(f"no such file: {target}")
        return 2
    if not olefile.isOleFile(str(target)):
        print(f"not an OLE/CFB file: {target}")
        return 4

    print("real_probe: structure only -- no content is printed")
    print(f"python {platform.python_version()} on {platform.system().lower()}")
    print(f"olefile {olefile.__version__}")
    print(f"file: {target} ({target.stat().st_size} bytes)")

    ole = olefile.OleFileIO(str(target))
    try:
        index = StorageIndex(ole)
        print(f"\nstreams: {len(index.streams)}")
        for path in index.streams:
            print(f"  {'/'.join(path)}  {index.stream_sizes['/'.join(path)]}")
        print(f"storages: {len(index.storages)}")
        for path in index.storages:
            print(f"  {'/'.join(path)}")

        recip_storages = [p for p in index.storages if p[0].startswith("__recip_version1.0")]
        attach_storages = [p for p in index.storages if p[0].startswith("__attach_version1.0")]
        top_recip = [p for p in recip_storages if len(p) == 1]
        top_attach = [p for p in attach_storages if len(p) == 1]
        recip_any = [p for p in index.storages if p[-1].startswith("__recip_version1.0")]
        attach_any = [p for p in index.storages if p[-1].startswith("__attach_version1.0")]
        nested_objects = [
            p for p in index.storages
            if (parsed := parse_substg_name(p[-1])) and parsed[1] == 0x000D
        ]
        print(f"recipient storages: {len(recip_any)} (top-level {len(top_recip)})")
        print(f"attachment storages: {len(attach_any)} (top-level {len(top_attach)})")
        print(f"nested object storages (embedded message / attach data): {len(nested_objects)}")
        for p in nested_objects:
            print(f"  {'/'.join(p)}")

        stream_tag_type: dict[int, set[int]] = {}
        suffixed_streams: list[str] = []
        for path in index.streams:
            parsed = parse_substg_name(path[-1])
            if parsed is None:
                continue
            tag, vt, has_suffix = parsed
            stream_tag_type.setdefault(tag, set()).add(vt)
            if has_suffix:
                suffixed_streams.append(path[-1])

        def sizes_for_basename(basename: str) -> list[int]:
            return [
                index.stream_sizes["/".join(p)]
                for p in index.streams
                if p[-1] == basename or p[-1].startswith(basename + "-")
            ]

        print("\nbody streams:")
        for tag in BODY_TAGS:
            vts = stream_tag_type.get(tag, set())
            if not vts:
                print(f"  {tag_name(tag)}: absent")
            else:
                for vt in sorted(vts):
                    sizes = sizes_for_basename(f"__substg1.0_{tag:04X}{vt:04X}")
                    print(
                        f"  {tag_name(tag)} {vt_name(vt)}: present "
                        f"({len(sizes)} stream(s), {sum(sizes)} bytes)"
                    )
        header_vts = stream_tag_type.get(0x007D, set())
        if header_vts:
            for vt in sorted(header_vts):
                sizes = sizes_for_basename(f"__substg1.0_007D{vt:04X}")
                print(
                    f"transport headers {tag_name(0x007D)} {vt_name(vt)}: "
                    f"present ({len(sizes)} stream(s), {sum(sizes)} bytes)"
                )
        else:
            print(f"transport headers {tag_name(0x007D)}: absent")
        print(
            f"streams with '-NNNNNNNN' suffix (named-property / multi-valued layout): "
            f"{len(suffixed_streams)}"
            + ("" if not suffixed_streams else f"; e.g. {suffixed_streams[0]}"))

        string_tags: dict[int, set[int]] = {}
        binary_tags: set[int] = set()
        object_tags: set[int] = set()
        for tag, vts in stream_tag_type.items():
            for vt in vts:
                if vt in STRING_VT:
                    string_tags.setdefault(vt, set()).add(tag)
                elif vt == 0x0102:
                    binary_tags.add(tag)
                elif vt == 0x000D:
                    object_tags.add(tag)
        n_unicode = sum(
            1 for p in index.streams
            if (parsed := parse_substg_name(p[-1])) and parsed[1] == 0x001F
        )
        n_string8 = sum(
            1 for p in index.streams
            if (parsed := parse_substg_name(p[-1])) and parsed[1] == 0x001E
        )
        print("\nstring-property types (UTF-16 vs 8-bit):")
        print(
            "  PT_UNICODE(001F): "
            f"{n_unicode} stream(s); tags: "
            + (", ".join(f"{t:04X}" for t in sorted(string_tags.get(0x001F, ()))) or "-")
        )
        print(
            "  PT_STRING8(001E): "
            f"{n_string8} stream(s); tags: "
            + (", ".join(f"{t:04X}" for t in sorted(string_tags.get(0x001E, ()))) or "-")
        )
        print("  PT_BINARY(0102) tags: " + (", ".join(f"{t:04X}" for t in sorted(binary_tags)) or "-"))
        print("  PT_OBJECT(000D) tags: " + (", ".join(f"{t:04X}" for t in sorted(object_tags)) or "-"))

        all_tags: set[tuple[int, int]] = set()
        for tag, vts in stream_tag_type.items():
            for vt in vts:
                all_tags.add((tag, vt))

        tables: list[tuple[str, list[str], int]] = [("message", [], TOP_LEVEL_HEADER)]
        for p in recip_storages + attach_storages:
            tables.append(("/".join(p), p, SUB_STORAGE_HEADER))

        code_page_presence: dict[int, list[str]] = {t: [] for t in CODE_PAGE_TAGS}
        boolean_tags_seen: set[int] = set()

        for label, storage_path, header_size in tables:
            prop_path = storage_path + ["__properties_version1.0"]
            if not ole.exists(prop_path):
                print(f"\nproperties [{label}]: __properties_version1.0 ABSENT")
                continue
            data = ole.openstream(prop_path).read()
            print(
                f"\nproperties [{label}]: {len(data)} bytes, header {header_size}B, "
                f"{(len(data) - header_size) // 16} entries"
            )
            if label == "message" and len(data) >= TOP_LEVEL_HEADER:
                print(
                    f"    header counts: @16 = {u32(data, 16)}, @20 = {u32(data, 20)} "
                    f"(directory: {len(top_recip)} recipient / "
                    f"{len(top_attach)} attachment storages)"
                )
            lines, entries = parse_property_table(data, header_size, index, storage_path)
            for line in lines:
                print(line)
            for e in entries:
                all_tags.add((e["tag"], e["vt"]))
                if e["kind"] == "fixed":
                    if e["tag"] in code_page_presence:
                        code_page_presence[e["tag"]].append(label)
                    if e["vt"] == 0x000B:
                        boolean_tags_seen.add(e["tag"])
            fixed = [e for e in entries if e["kind"] == "fixed"]
            var = [e for e in entries if e["kind"] == "variable"]
            print(f"    fixed-size entries ({len(fixed)}): " + ", ".join(fmt_entry(e) for e in fixed))
            print(f"    stream-backed entries ({len(var)}): " + ", ".join(fmt_entry(e) for e in var))

        print("\ncode-page / flag properties (design claim: fixed-size inside the table):")
        for tag in CODE_PAGE_TAGS:
            where = code_page_presence[tag]
            if where:
                print(f"  {tag_name(tag)}: PRESENT as fixed-size entry in [{', '.join(where)}]")
            else:
                print(f"  {tag_name(tag)}: not observed")
        if boolean_tags_seen:
            print(
                "  PT_BOOLEAN flag entries: "
                + ", ".join(f"0x{t:04X}" for t in sorted(boolean_tags_seen))
                + " (presence only)"
            )
        else:
            print("  PT_BOOLEAN flag entries: none observed")

        print("\nobserved property-tag set (tag:type):")
        for tag, vt in sorted(all_tags):
            print(f"  {tag:04X}:{vt:04X}  {tag_name(tag)} {vt_name(vt)}")
        print("\n(structure only: no property value, no stream content printed)")
    finally:
        ole.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
