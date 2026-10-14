"""Turn 1b.0c: the committed ``.eml`` golden -- the net under the eight frozen-module edits.

Build rule 2 says no measured ``.eml`` value may move in Phase 1b except the direct
consequences of the one schema bump. The behavior ledger's ``walk``/``decode_chain``
fingerprints pin the ``WalkResult``, but nothing pinned the **assembled
``EmailDocument``**, the ``resolve_span`` answers, the ``CapRecord``s, the store
artifacts or the ``ParseResult``. This tool records ``tests/golden/eml_golden.json``:
one record per committed ``.eml`` fixture, each pinning six things:

* ``parse`` -- the whole :class:`~emailextract.parse.ParseResult`;
* ``document`` -- ``assemble`` serialized through the core codec (the whole record);
* ``walk`` -- the ``WalkResult`` the walker returns, encoded without the codec
  envelope (so its bytes carry no schema version);
* ``caps`` -- every :class:`~emailextract.model.CapRecord`, in order;
* ``span_samples`` -- the ``resolve_span`` answers for every ``PartRecord``'s own
  span (and the first, the last and one interior sub-span), plus every
  ``HeaderField``'s own raw span;
* ``store`` -- the walk and document artifacts' **bytes** (hex) and the keys
  ``artifact_key`` / ``document_key`` compute.

Recording is explicit and the only way the file is written::

    python tools/update_eml_golden.py            # record tests/golden/eml_golden.json
    python tools/update_eml_golden.py --check    # exit 1 and name every moved fixture/key
    python tools/update_eml_golden.py --list     # print the pinned fixtures

The comparison applies the recorded **waiver** (the exact key paths the two
interpreters legitimately differ in), so ``--check`` is green on both. Nothing here
reads a clock, a path into the record, the environment or the network: recording
twice produces identical bytes.

It enumerates the corpus exactly as ``tools/behavior_ledger.py`` does (the committed
``.eml`` fixtures under ``fixtures/``, ``fixtures/real/`` excluded) -- it imports that
tool's enumeration rather than forking a second rule for "which files".
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(_ROOT), str(_ROOT / "tools")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import behavior_ledger  # noqa: E402  (the corpus enumeration, imported not forked)
from docextract_core.codec import encode  # noqa: E402
from emailextract import versions  # noqa: E402
from emailextract.assemble import Unresolvable, assemble, resolve_span  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.model import record_to_bytes  # noqa: E402
from emailextract.parse import Limits, parse  # noqa: E402
from emailextract.store import document_artifact, walk_artifact  # noqa: E402
from emailextract.walk import PartShape, walk  # noqa: E402
from emailextract.text import analyse_part  # noqa: E402

__all__ = [
    "GOLDEN_PATH",
    "GOLDEN_VERSION",
    "WAIVER",
    "canonical_bytes",
    "compare",
    "load",
    "record",
    "write",
]

GOLDEN_PATH = _ROOT / "tests" / "golden" / "eml_golden.json"

#: The golden format's own version. Moves only when the file's *shape* moves.
GOLDEN_VERSION = "1"

#: The one declared ``Limits`` every pin is measured under; the header records it.
#:
#: It is ``Limits.untrusted()`` with ``max_header_bytes`` lowered to 4096. Under the
#: untouched untrusted set **no** committed fixture hits a cap, so the ``caps`` pin
#: would be empty for all 126 and could not fail -- a decorative pin. 4096 is the
#: smallest measured header cap that fires on the corpus's own ``cap_*`` fixture
#: (``cap_enormous_header_block``): exactly one fixture caps, and every other
#: fixture's parts, headers and caps are byte-identical to the untrusted run.
LIMITS = replace(Limits.untrusted(), max_header_bytes=4096)

#: The exact key paths the two interpreters legitimately differ in, as path
#: **patterns** over the golden's own key tree. ``"*"`` matches exactly one segment
#: -- the fixture's corpus-relative name -- so one pattern names the same path in
#: every fixture. Every entry is a recorded-only input or a value derived from one:
#:
#: * ``header/recorded_on`` -- the interpreter the file was recorded on (metadata);
#: * ``.../run_record/projection_versions/HTMLTEXT_VERSION`` -- the CPython minor the
#:   HTML projection ran under (decision 1: ``HTMLTEXT_VERSION`` stamps it);
#: * ``store/document/{key,path,bytes_hex}`` -- the document artifact's key, its store
#:   path and its bytes, all three of which name every projection version.
#:
#: All of them are the one recorded-only input (``HTMLTEXT_VERSION``) or a value
#: derived from it; the spec's "a recorded-heading field" understates the reach.
#: Nothing a measured value carries (a ``part_id``, a ``sha256``, a span, a cap) is
#: ever waived, and on the recording interpreter **no** path is waived at all -- the
#: committed file is reproduced byte for byte. The walk artifact carries no
#: recorded-only stamp, so its bytes never appear here.
WAIVER: tuple[tuple[str, ...], ...] = (
    ("header", "recorded_on"),
    (
        "fixtures",
        "*",
        "document",
        "record",
        "run_record",
        "projection_versions",
        "HTMLTEXT_VERSION",
    ),
    ("fixtures", "*", "store", "document", "key"),
    ("fixtures", "*", "store", "document", "path"),
    ("fixtures", "*", "store", "document", "bytes_hex"),
)

#: The header key naming how the store pin's bytes are encoded.
STORE_BYTES_ENCODING = "hex of emailextract.model.record_to_bytes(artifact)"


def canonical_bytes(obj: Any) -> bytes:
    """Strict canonical JSON, as bytes: sorted keys, compact, LF, no BOM, no trailing space."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8") + b"\n"


def _recorded_on() -> str:
    return f"{platform.python_implementation()} {platform.python_version()}"


def _limits_header() -> dict[str, Any]:
    return {name: getattr(LIMITS, name) for name in LIMITS.__dataclass_fields__}


def _answer(container: EmlContainer, part_id: str, view: str, start: int, end: int) -> dict[str, Any]:
    """The ``resolve_span`` answer, as plain JSON-ready data."""
    span = resolve_span(container, part_id, view, start, end)
    if isinstance(span, Unresolvable):
        return {"kind": "unresolvable", "reason_id": span.reason_id, "part_id": span.part_id}
    return {"kind": "raw_span", "offset": span.offset, "length": span.length, "locator": span.locator}


def _span(span: Any) -> dict[str, Any]:
    return {"offset": span.offset, "length": span.length, "locator": span.locator}


def _samples(container: EmlContainer, part_id: str, length: int) -> list[dict[str, Any]]:
    """The four ``resolve_span`` samples over one part's own plain view.

    ``own`` is the whole view, ``first`` its first code point, ``last`` its last and
    ``interior`` one interior sub-span -- so the C2 identity guard covers the start,
    the end and the middle, not only a trivial prefix.
    """
    first_end = min(1, length)
    interior_start = max(0, length // 2 - 1)
    interior_end = min(length, max(interior_start, length // 2 + 1))
    ranges = (
        ("own", 0, length),
        ("first", 0, first_end),
        ("last", max(0, length - 1), length),
        ("interior", interior_start, interior_end),
    )
    return [
        {
            "range": name,
            "start": start,
            "end": end,
            "answer": _answer(container, part_id, "plain", start, end),
        }
        for name, start, end in ranges
    ]


def _span_samples(
    raw: bytes,
    container: EmlContainer,
    walked: Any,
    document: Any,
) -> dict[str, Any]:
    """``resolve_span`` samples for every part, and every header field's own span.

    ``resolve_span`` addresses a **part's view code points**; a header field has no
    view, so its own span (``name_span``/``value_span``) is pinned directly and its
    ``answer`` is an explicit ``null`` with the reason. A failed part still gets its
    four samples (each an ``unresolvable`` answer), never an omitted key.
    """
    shapes: dict[str, PartShape] = {part.part_id: part for part in walked.parts}
    parts = []
    for record in document.parts:
        shape = shapes.get(record.part_id)
        length = 0
        if shape is not None:
            analysed = analyse_part(raw, shape)
            length = len(analysed.text) if analysed is not None else 0
        parts.append(
            {
                "part_id": record.part_id,
                "locator": shape.path if shape is not None else None,
                "view": "plain",
                "samples": _samples(container, record.part_id, length),
            }
        )
    root = walked.parts[0] if walked.parts else None
    by_field = {}
    if root is not None:
        for item in root.header_fields:
            by_field[(item.name, item.ordinal)] = item
    headers = []
    for field in document.headers:
        item = by_field.get((field.name, field.ordinal))
        headers.append(
            {
                "name": field.name,
                "ordinal": field.ordinal,
                "part_id": root.part_id if root is not None else None,
                "name_span": _span(item.name_span) if item is not None else None,
                "value_span": _span(item.value_span) if item is not None else None,
                "answer": None,
                "answer_reason": "resolve_span addresses a part's view code points, not a header span",
            }
        )
    return {
        "answer_encoding": "raw_span | unresolvable | null-with-reason",
        "parts": parts,
        "headers": headers,
    }


def _store_pin(container: EmlContainer) -> dict[str, Any]:
    """The two store artifacts: their bytes (hex) and the keys that name them."""
    walk_art = walk_artifact(container)
    doc_art = document_artifact(container, limits=LIMITS)
    return {
        "bytes_encoding": STORE_BYTES_ENCODING,
        "walk": {
            "key": walk_art.key,
            "path": f"walks/{walk_art.key}.json",
            "bytes_hex": record_to_bytes(walk_art).hex(),
        },
        "document": {
            "key": doc_art.key,
            "path": f"documents/{doc_art.key}.json",
            "bytes_hex": record_to_bytes(doc_art).hex(),
        },
    }


def _fixture_pins(data: bytes) -> dict[str, Any]:
    container = EmlContainer(memory_bytes(data))
    parsed = parse(data, limits=LIMITS)
    document = assemble(container, limits=LIMITS)
    walked = walk(container)
    caps = document.run_record.caps if document.run_record is not None else None
    return {
        "parse_result": encode(parsed),
        "document": json.loads(record_to_bytes(document).decode("utf-8")),
        "walk": encode(walked),
        "caps": None if caps is None else [encode(cap) for cap in caps],
        "span_samples": _span_samples(data, container, walked, document),
        "store": _store_pin(container),
    }


def _corpus() -> tuple[int, dict[str, bytes]]:
    """``(corpus version, {name: bytes})``, enumerated the way the behavior ledger is."""
    corpora = behavior_ledger.load_corpora()
    if not corpora:
        raise RuntimeError("no corpus manifest (tests/ledger/corpus.json): nothing to pin")
    corpus_version = behavior_ledger.latest_corpus(corpora)
    members = behavior_ledger.corpus()
    if not members:
        raise RuntimeError("the corpus enumeration returned zero files: refusing to write an empty golden")
    named = next(entry["files"] for entry in corpora if entry["version"] == corpus_version)
    if sorted(named) != sorted(members):
        raise RuntimeError(
            "the corpus manifest and the fixtures disagree about which files are in "
            f"corpus version {corpus_version}: re-record the behavior ledger's corpus first"
        )
    return corpus_version, members


def record() -> dict[str, Any]:
    """A fresh recording of the whole golden, as plain JSON-ready data."""
    corpus_version, members = _corpus()
    fixtures = {name: _fixture_pins(members[name]) for name in sorted(members)}
    header = {
        "golden_version": GOLDEN_VERSION,
        "corpus_version": corpus_version,
        "schema_version": versions.OUTPUT_SCHEMA_VERSION,
        "email_parser_version": versions.EMAIL_PARSER_VERSION,
        "fixture_count": len(fixtures),
        "recorded_on": _recorded_on(),
        "limits": _limits_header(),
        "store_bytes": STORE_BYTES_ENCODING,
        "waiver": [list(path) for path in WAIVER],
    }
    return {"header": header, "fixtures": fixtures}


def load(path: str | Path | None = None) -> dict[str, Any]:
    """The committed golden, parsed; ``{}`` when there is none yet."""
    golden_path = Path(path) if path is not None else GOLDEN_PATH
    if not golden_path.is_file():
        return {}
    return json.loads(golden_path.read_text(encoding="utf-8"))


def write(golden: dict[str, Any], path: str | Path | None = None) -> Path:
    """Write the golden as strict canonical JSON, in binary mode (LF, no BOM)."""
    golden_path = Path(path) if path is not None else GOLDEN_PATH
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    with golden_path.open("wb") as handle:
        handle.write(canonical_bytes(golden))
    return golden_path


def _matches(path: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    return len(path) == len(pattern) and all(
        want == "*" or want == got for want, got in zip(pattern, path)
    )


def _walk_diff(
    path: tuple[str, ...],
    committed: Any,
    fresh: Any,
    waiver: tuple[tuple[str, ...], ...],
    out: list[tuple[tuple[str, ...], Any, Any]],
) -> None:
    if committed == fresh:
        return
    if any(_matches(path, pattern) for pattern in waiver):
        return
    if isinstance(committed, dict) and isinstance(fresh, dict):
        for key in sorted(set(committed) | set(fresh)):
            _walk_diff(path + (key,), committed.get(key), fresh.get(key), waiver, out)
        return
    if isinstance(committed, list) and isinstance(fresh, list) and len(committed) == len(fresh):
        for index, (old, new) in enumerate(zip(committed, fresh)):
            _walk_diff(path + (str(index),), old, new, waiver, out)
        return
    out.append((path, committed, fresh))


def compare(
    committed: Any,
    fresh: Any,
    waiver: tuple[tuple[str, ...], ...] = (),
) -> list[tuple[tuple[str, ...], Any, Any]]:
    """Every (key path, committed value, fresh value) the waiver does not cover."""
    out: list[tuple[tuple[str, ...], Any, Any]] = []
    _walk_diff((), committed, fresh, waiver, out)
    return out


def _waiver_from(golden: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    header = golden.get("header") or {}
    return tuple(tuple(str(segment) for segment in path) for path in header.get("waiver") or ())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the committed golden to a fresh recording (applying the waiver); write nothing",
    )
    parser.add_argument("--list", action="store_true", help="print the pinned fixtures")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list:
        committed = load()
        for name in sorted((committed.get("fixtures") or {})):
            print(name)
        return 0
    fresh = record()
    if args.check:
        committed = load()
        if not committed:
            print(f"{GOLDEN_PATH}: not recorded", file=sys.stderr)
            return 1
        differences = compare(committed, fresh, _waiver_from(committed))
        for path, old, new in differences:
            print(f"{'/'.join(path)}: committed={old!r} fresh={new!r}", file=sys.stderr)
        return 1 if differences else 0
    write(fresh)
    print(f"{GOLDEN_PATH}: written ({len(fresh['fixtures'])} fixtures)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
