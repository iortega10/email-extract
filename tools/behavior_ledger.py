"""Turn 0.2: the behavior ledger -- a version bump as a failing test, not a habit.

Fingerprints over a **versioned corpus** (``tests/ledger/corpus.json``), keyed by
the version constants in :mod:`emailextract.versions`:

* **walk**, ``EMAIL_PARSER_VERSION|DECODE_CHAIN_VERSION``: the skeleton
  walker's full output over every corpus message -- parts, spans, header fields,
  decode chains, accounted regions, gaps, unknown sections.
* **decode_chain**, ``DECODE_CHAIN_VERSION``: the recorded decode chains alone,
  so a chain-rule change is named as itself and not as a walker change.
* **contracts**, this package's ``OUTPUT_SCHEMA_VERSION``: every persisted
  dataclass shape -- name, field names, types and defaults -- of the contract and
  walker records. A field added, removed, renamed or retyped changes this
  fingerprint, which is exactly the contract change a schema bump is for. It is
  keyed by that version **alone** and depends on no corpus.

  **Re-keyed in Turn 0.5.** It was keyed by the core codec's ``SCHEMA_VERSION``
  (``"7"``) before, which this package does not own: a contract change here could
  never be recorded, because a change would have needed a bump of a constant owned
  by ``docextract-core`` and the tool refuses to overwrite a recorded line. The old
  ``7`` line stays in the ledger as **LEGACY** (append-only; see ``LEGACY_KEYS``)
  and is never compared again.

``tests/ledger/behavior_ledger.json`` is an **append-only** map
``{component: {key: fingerprint}}`` where a key is ``"<version string>|corpus:<N>"``
(both halves matter: a behavior change hiding in a new fixture is refused).
:func:`check` is the test half; :func:`record` is
``tools/update_behavior_ledger.py``'s, and it refuses to overwrite a version
already recorded with a different fingerprint -- naming the constant to bump.

**The corpus is a tiny INLINE corpus** (``INLINE_CORPUS``, hand-written byte
strings in this file) because the Turn 0.3 fixtures do not exist yet; the ledger
header says so. When they land, ``--fixtures`` points the corpus at the
committed ``.eml`` files and adding one adds a corpus version (bumping no
component version). ``fixtures/real/`` is machine-local and never corpus.

**Deliberate false positive:** the contracts fingerprint is over each field's
written *type text*, so a purely cosmetic re-spelling (``str | None`` versus
``Optional[str]``) moves it. That is accepted -- a resolved-types fingerprint
would hide a re-spelling a reviewer may still want to see -- and it is the same
trade-off word-extract's ledger makes.

**Version-constant defaults are symbolic, not literal.** A field that defaults to
a version constant (``output_schema_version = OUTPUT_SCHEMA_VERSION``,
``email_parser_version = EMAIL_PARSER_VERSION``, ``decode_chain_version``,
``flag_schema_version``) is recorded as the constant's **name**. Bumping the
parser version would otherwise read as a contract change -- the default is
written from the constant, so its value moves with it -- while a real shape change
still moves the fingerprint. The rule keys off the field *name*, so it cannot
quietly stop applying when a value changes.

**Cross-interpreter:** the fingerprints are reproducible across interpreters
(stdlib ``email`` is never serialized back out; spans come from this package's
own scanner). They are required to be identical on CPython 3.14 and 3.11 -- run
both and compare; a difference is recorded in this header, never hidden.
"""
from __future__ import annotations

import json
import sys
from dataclasses import MISSING, Field, fields, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

_ROOT = Path(__file__).resolve().parent.parent
for _path in (_ROOT,):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from docextract_core import encode, sha256_json  # noqa: E402

from emailextract import bodytext  # noqa: E402
from emailextract import cfb as cfb_module  # noqa: E402
from emailextract import ids as ids_module  # noqa: E402
from emailextract import mapi as mapi_module  # noqa: E402
from emailextract import model, seam, siblings, store, timeevent, versions  # noqa: E402
from emailextract import walk as walk_module  # noqa: E402
from emailextract.container import EmlContainer  # noqa: E402
from emailextract.ids import sha256_hex  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402

#: The component names, in the ledger's own order. The first three are Phase 1's; the next
#: three are Phase 1b's (Turn 1b.10b) and fingerprint the committed ``.msg`` corpus; the last
#: two are Turn BODY1's on-demand accessors, over the ``.eml`` corpus.
COMPONENTS = (
    "walk",
    "decode_chain",
    "contracts",
    "cfb",
    "msg_reader",
    "msg_projection",
    "body_text",
    "attachment_payloads",
)

#: Which constant a component's version string is built from -- what to bump.
VERSION_CONSTANTS = {
    "walk": "EMAIL_PARSER_VERSION (or DECODE_CHAIN_VERSION)",
    "decode_chain": "DECODE_CHAIN_VERSION",
    "contracts": "OUTPUT_SCHEMA_VERSION",
    "cfb": "CFB_VERSION",
    "msg_reader": "MSG_READER_VERSION",
    "msg_projection": "MSG_PROJECTION_VERSION",
    "body_text": "BODY_TEXT_VERSION",
    "attachment_payloads": "ATTACHMENT_ACCESSOR_VERSION",
}

#: The components whose fingerprint is over the corpus. ``contracts`` is over the
#: record definitions alone, so it is keyed by its version and nothing else.
CORPUS_DEPENDENT = (
    "walk",
    "decode_chain",
    "cfb",
    "msg_reader",
    "msg_projection",
    "body_text",
    "attachment_payloads",
)

#: The three Phase 1b components: each reads the committed ``.msg`` fixtures and never an
#: ``.eml`` one, so a corpus version that carries both kinds gives each its own subset and
#: the two readers never fingerprint the same input.
MSG_COMPONENTS = ("cfb", "msg_reader", "msg_projection")

#: The suffix that separates the two corpora inside one corpus version, and the suffixes
#: the corpus source carries (``.eml`` for the walker's components, ``.msg`` for the three
#: Phase 1b ones).
_MESSAGE_SUFFIX = ".msg"

#: The committed ``.msg`` fixtures that are **hostile mutants** rather than messages. The
#: ``cfb`` component fingerprints the CFB primitives over the well-formed fixtures only
#: (``docs/design/phase1b-ledgers.md`` section (c)); the hostile three are the seeded
#: fuzz's and the fault classification's. Kept in step with ``tools/make_msg_fixtures``'s
#: ``HOSTILE_FIXTURE_NAMES`` by ``tests/test_behavior_ledger.py``.
MSG_HOSTILE_STEMS: frozenset[str] = frozenset(
    {"msg_fat_cycle", "msg_directory_loop", "msg_truncated_stream"}
)

#: Keys a component recorded under a version this package no longer keys by: the
#: re-key history, kept in the file (append-only) and **never compared again**.
#: ``contracts`` was keyed by the core codec's ``SCHEMA_VERSION`` (``"7"``) before
#: Turn 0.5; the tool appends under the current key and never looks at these.
LEGACY_KEYS: Mapping[str, tuple[str, ...]] = {"contracts": ("7",)}

LEDGER_PATH = _ROOT / "tests" / "ledger" / "behavior_ledger.json"
CORPUS_PATH = _ROOT / "tests" / "ledger" / "corpus.json"
#: The corpus source since the Turn 0.3 switch: the committed fixtures. The
#: inline corpus below is history -- corpus version 1 -- and stays resolvable
#: so every recorded fingerprint can still be recomputed.
FIXTURES = _ROOT / "fixtures"
_LOCAL_ONLY = "real"

#: The tiny inline corpus: hand-written byte strings only, no real mail, no
#: generated fixtures (Turn 0.3 replaces this corpus; it does not extend it).
INLINE_CORPUS: dict[str, bytes] = {
    "plain_simple": (
        b"From: sender@example.com\r\n"
        b"To: receiver@example.com\r\n"
        b"Subject: plain simple\r\n"
        b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"Message-ID: <plain-simple@example.com>\r\n"
        b"\r\n"
        b"one plain body line\r\n"
    ),
    "folded_and_duplicate_headers": (
        b"Received: from a.example by b.example; Tue, 4 Mar 2025 08:59:00 +0000\r\n"
        b"Received: from c.example by a.example; Tue, 4 Mar 2025 08:58:00 +0000\r\n"
        b"Subject: folded\r\n"
        b" value here\r\n"
        b"Thread-Index: AQHbase64ish==\r\n"
        b"\r\n"
        b"body after folds\r\n"
    ),
    "malformed_header_line": (
        b"Subject: before the bad line\r\n"
        b"this line has no colon\r\n"
        b"X-After: still a header (fail-open)\r\n"
        b"\r\n"
        b"body text\r\n"
    ),
    "headers_only": b"Subject: no blank line follows\r\nX-Last: to end of file",
    "multipart_preamble_epilogue": (
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=\"B-1\"\r\n"
        b"\r\n"
        b"this is the preamble\r\n"
        b"--B-1\r\n"
        b"Content-Type: text/plain; charset=us-ascii\r\n"
        b"\r\n"
        b"part one\r\n"
        b"--B-1\r\n"
        b"Content-Type: text/plain; charset=us-ascii\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"cGFydCB0d28=\r\n"
        b"--B-1--\r\n"
        b"this is the epilogue\r\n"
    ),
    "nested_multipart": (
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=OUTER\r\n"
        b"\r\n"
        b"--OUTER\r\n"
        b"Content-Type: text/plain; charset=iso-8859-1\r\n"
        b"\r\n"
        b"Caf\xe9 na\xefve\r\n"
        b"--OUTER\r\n"
        b"Content-Type: multipart/alternative; boundary=INNER\r\n"
        b"\r\n"
        b"--INNER\r\n"
        b"Content-Type: text/html\r\n"
        b"\r\n"
        b"<p>html view</p>\r\n"
        b"--INNER--\r\n"
        b"--OUTER--\r\n"
    ),
    "bad_cte_fallback": (
        b"Content-Type: text/plain; charset=us-ascii\r\n"
        b"Content-Transfer-Encoding: x-no-such-cte\r\n"
        b"\r\n"
        b"payload left verbatim\r\n"
    ),
    "lossy_charset": (
        b"Content-Type: text/plain; charset=x-no-such-charset\r\n"
        b"\r\n"
        b"byte \x81 destroys round trip\r\n"
    ),
}

_HEADER = (
    "Append-only behavior fingerprints (build spec, Turn 0.2): {component: {key: "
    "sha256}}. A key is '<version string>|corpus:<N>': the code version and the "
    "corpus version it was fingerprinted on. Corpus version 1 is the TINY INLINE "
    "corpus (INLINE_CORPUS in tools/behavior_ledger.py; hand-written byte strings); "
    "since the Turn 0.3 switch the corpus source is the committed fixtures "
    "(the .eml and .msg files under fixtures/, excluding local-only real/; --fixtures "
    "DIR points elsewhere), and tests/ledger/corpus.json lists each corpus version's "
    "message names. One corpus version may carry both kinds: the walker's two "
    "components fingerprint the .eml names and the three message components "
    "(cfb/msg_reader/msg_projection, Turn 1b.10b) the .msg names, so the two readers "
    "never fingerprint the same input. Turn BODY1's two accessor components (body_text, "
    "attachment_payloads) fingerprint the .eml names as well: the decode chain and the "
    "transfer-encoding decoders they read are shared with the .msg path, which the "
    "msg_projection/msg_reader lines already pin. Adding a message or a fixture adds a corpus "
    "version and NEW "
    "LINES under the SAME component versions "
    "-- it is not a behavior change and bumps nothing; the tool refuses to record a "
    "new corpus if any older corpus's fingerprint moved (that is a behavior change "
    "that needs a bump). 'contracts' does not depend on the corpus and is keyed by "
    "this package's OUTPUT_SCHEMA_VERSION alone; before Turn 0.5 it was keyed by the "
    "core codec's SCHEMA_VERSION, so the '7' line under 'contracts' is LEGACY -- kept "
    "in place (append-only) and never compared again. Fingerprints are identical on "
    "CPython 3.14.3 and "
    "3.11.15 (measured in Turn 0.2; re-measured unchanged over the Turn 0.3 "
    "fixtures in Turn 0.3; re-measured over the .msg corpus in Turn 1b.10b); a "
    "cross-interpreter difference is recorded "
    "here, never hidden. The history before this file is not reconstructed. Record "
    "lines with tools/update_behavior_ledger.py in the same commit as the change "
    "that caused them."
)

_CORPUS_HEADER = (
    "The ledger's corpora, oldest first: each version lists the message names its "
    "fingerprints were taken over (tools/behavior_ledger.INLINE_CORPUS names for "
    "corpus version 1; relative paths under the fixtures corpus source since the "
    "Turn 0.3 switch -- .eml and, since Turn 1b.10b, .msg -- and --fixtures DIR for "
    "another source). Growing the corpus adds "
    "a version here -- the tool detects a changed file list and appends it "
    "automatically; it never bumps a component version."
)


# ------------------------------------------------------------------ the corpus


def _files_under(root: Path, suffixes: tuple[str, ...]) -> dict[str, bytes]:
    """Every file under ``root`` with one of ``suffixes``, local-only ``real/`` skipped."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in suffixes
        and _LOCAL_ONLY not in path.relative_to(root).parts
    }


def corpus(fixtures_dir: str | Path | None = None) -> dict[str, bytes]:
    """Every ``.eml`` corpus message, by name -- the walker's corpus.

    The source is the committed fixtures since the Turn 0.3 switch (``--fixtures`` points
    elsewhere); ``INLINE_CORPUS`` is history and is reachable through :func:`_resolve`,
    never listed here. Deliberately ``.eml``-only: ``tools/update_eml_golden.py``
    enumerates the ``.eml`` golden through this function, so the ``.msg`` corpus lives in
    its own list (:func:`message_corpus`) and neither enumeration moves the other.
    """
    root = Path(fixtures_dir) if fixtures_dir is not None else FIXTURES
    return _files_under(root, (".eml",))


def discovered(fixtures_dir: str | Path | None = None) -> list[str]:
    """The ``.eml`` corpus message names, in a machine-independent order."""
    return sorted(corpus(fixtures_dir))


def message_corpus(fixtures_dir: str | Path | None = None) -> dict[str, bytes]:
    """Every ``.msg`` corpus message, by name -- the three Phase 1b components' corpus."""
    root = Path(fixtures_dir) if fixtures_dir is not None else FIXTURES
    return _files_under(root, (_MESSAGE_SUFFIX,))


def discovered_messages(fixtures_dir: str | Path | None = None) -> list[str]:
    """The ``.msg`` corpus message names, in a machine-independent order."""
    return sorted(message_corpus(fixtures_dir))


def _is_message(name: str) -> bool:
    """Whether a corpus name is a ``.msg`` (the three Phase 1b components' half)."""
    return name.lower().endswith(_MESSAGE_SUFFIX)


def _component_names(component: str, names: Iterable[str]) -> list[str]:
    """The names one component fingerprints out of a corpus list.

    Each of the two corpora is already one kind, so this filter can never change which
    inputs a component reads: the ``.msg`` corpus feeds the three Phase 1b components and
    never the walker's, and ``cfb`` additionally drops the hostile ``.msg`` mutants
    (:data:`MSG_HOSTILE_STEMS`); ``contracts`` hashes no corpus at all.
    """
    if component in MSG_COMPONENTS:
        selected = [name for name in names if _is_message(name)]
        if component == "cfb":
            selected = [name for name in selected if Path(name).stem not in MSG_HOSTILE_STEMS]
        return selected
    return [name for name in names if not _is_message(name)]


def _resolve(name: str, fixtures_dir: str | Path | None) -> bytes:
    """One corpus message's bytes, for any corpus version's recorded name.

    Older corpus versions must stay recomputable, so a name resolves against the
    source the caller pointed at (``--fixtures``), then the committed fixtures
    (the source since the Turn 0.3 switch), then the inline corpus that corpus
    version 1 was fingerprinted over -- in that order, first hit wins.
    """
    roots = [Path(fixtures_dir)] if fixtures_dir is not None else []
    if FIXTURES not in roots:
        roots.append(FIXTURES)
    for root in roots:
        path = root / name
        if path.is_file():
            return path.read_bytes()
    if name in INLINE_CORPUS:
        return INLINE_CORPUS[name]
    raise ValueError(
        f"corpus message {name!r} is in neither corpus source ({', '.join(map(str, roots))}) "
        "nor the inline corpus"
    )


def _load_versions(manifest: Path, key: str) -> list[dict]:
    """One version list out of the corpus manifest, oldest first; ``[]`` when absent."""
    if not manifest.is_file():
        return []
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    return [
        {"version": int(entry["version"]), "files": list(entry["files"])}
        for entry in loaded.get(key, [])
    ]


def load_corpora(path: str | Path | None = None) -> list[dict]:
    """The ``.eml`` corpus versions on disk, oldest first; ``[]`` when there is none yet."""
    return _load_versions(Path(path) if path is not None else CORPUS_PATH, "corpora")


def load_message_corpora(path: str | Path | None = None) -> list[dict]:
    """The ``.msg`` corpus versions on disk, oldest first; ``[]`` when there is none yet.

    A **second list** in the same manifest, kept apart from ``corpora`` on purpose: the
    ``.eml`` corpus version is what ``tools/update_eml_golden.py`` pins in the golden
    header (and what every existing ledger key counts), so a ``.msg`` fixture is recorded
    here and can never move the golden. Message corpus versions count from 1 in their own
    space; the key's ``corpus:<N>`` half is read against this list for the three Phase 1b
    components and against ``corpora`` for the walker's.
    """
    return _load_versions(Path(path) if path is not None else CORPUS_PATH, "messages")


def write_corpora(
    corpora: list[dict],
    messages: list[dict] | None = None,
    path: str | Path | None = None,
) -> Path:
    manifest = Path(path) if path is not None else CORPUS_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "_comment": _CORPUS_HEADER,
        "corpora": corpora,
        "messages": [] if messages is None else messages,
    }
    with manifest.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return manifest


def latest_corpus(corpora: list[dict]) -> int:
    return max((entry["version"] for entry in corpora), default=0)


def _append_version(versions: list[dict], names: list[str]) -> tuple[list[dict], bool]:
    """Append a corpus version for ``names``; ``False`` when the newest already lists them."""
    if versions and sorted(versions[-1]["files"]) == names:
        return versions, False
    return [*versions, {"version": latest_corpus(versions) + 1, "files": names}], True


def add_corpus_version(
    fixtures_dir: str | Path | None = None, corpora: list[dict] | None = None
) -> tuple[list[dict], bool]:
    """Append an ``.eml`` corpus version for today's message list; ``False`` when unchanged."""
    corpora = load_corpora() if corpora is None else corpora
    return _append_version(corpora, discovered(fixtures_dir))


def add_message_corpus_version(
    fixtures_dir: str | Path | None = None, messages: list[dict] | None = None
) -> tuple[list[dict], bool]:
    """Append a ``.msg`` corpus version for today's message list; ``False`` when unchanged."""
    messages = load_message_corpora() if messages is None else messages
    return _append_version(messages, discovered_messages(fixtures_dir))


def entry_key(component: str, version: str, corpus_version: int) -> str:
    """The ledger key: the version, plus the corpus it was taken over."""
    if component in CORPUS_DEPENDENT:
        return f"{version}|corpus:{corpus_version}"
    return version


def version_strings() -> dict[str, str]:
    """Each component's current version string, read off the modules at call time.

    Read dynamically -- not imported by value -- so a test that monkeypatches a
    constant is seen here without a reimport.
    """
    return {
        "walk": f"{versions.EMAIL_PARSER_VERSION}|{versions.DECODE_CHAIN_VERSION}",
        "decode_chain": versions.DECODE_CHAIN_VERSION,
        "contracts": versions.OUTPUT_SCHEMA_VERSION,
        "cfb": versions.CFB_VERSION,
        "msg_reader": versions.MSG_READER_VERSION,
        "msg_projection": versions.MSG_PROJECTION_VERSION,
        "body_text": versions.BODY_TEXT_VERSION,
        "attachment_payloads": versions.ATTACHMENT_ACCESSOR_VERSION,
    }


# ------------------------------------------------------------- the fingerprints


def _version_constant_name(field_name: str) -> str | None:
    """The ``*_VERSION`` constant a field's name mirrors, when there is one.

    ``output_schema_version`` -> ``OUTPUT_SCHEMA_VERSION``,
    ``email_parser_version`` -> ``EMAIL_PARSER_VERSION``, ``decode_chain_version``
    and ``flag_schema_version`` likewise. The rule is by *name*, so it cannot
    silently stop applying when a constant's value changes: a field default written
    from a version constant is a version fact, not a shape fact.
    """
    candidate = field_name.upper()
    if not candidate.endswith("_VERSION"):
        return None
    constant = vars(versions).get(candidate)
    if isinstance(constant, str) and constant:
        return candidate
    return None


def _field_shape(field_: Field) -> list[Any]:
    """One field as ``[name, type, default]``; a factory is named, never called.

    A default written from a version constant is recorded as the constant's
    **name**, so bumping the parser version is not a contract change while a real
    shape change still is (see the module docstring).
    """
    constant = _version_constant_name(field_.name)
    if constant is not None:
        default: Any = {"version_constant": constant}
    elif field_.default is not MISSING:
        default = encode(field_.default)
    elif field_.default_factory is not MISSING:
        factory = field_.default_factory
        default = {"factory": getattr(factory, "__qualname__", type(factory).__name__)}
    else:
        default = None
    return [field_.name, str(field_.type), default]


def contract_records() -> tuple[type, ...]:
    """Every dataclass whose shape is part of the persisted contract, sorted by name."""
    shapes: list[type] = []
    for module in (model, timeevent, ids_module, walk_module, store, siblings, seam):
        shapes.extend(
            obj for obj in vars(module).values() if isinstance(obj, type) and is_dataclass(obj)
        )
    return tuple(sorted(set(shapes), key=lambda cls: cls.__qualname__))


def contracts_fingerprint(records: Iterable[type] | None = None) -> str:
    """The shape of every record: its name, and its fields' names, types and defaults.

    A cosmetic type re-spelling moves this fingerprint on purpose -- see the
    module docstring (deliberate false positive).
    """
    shapes = {
        cls.__qualname__: [_field_shape(field_) for field_ in fields(cls)]
        for cls in sorted(
            list(records) if records is not None else contract_records(),
            key=lambda cls: cls.__qualname__,
        )
    }
    return sha256_json(shapes)


def _walk_pieces(name: str, payload: bytes) -> dict[str, Any]:
    """One ``.eml`` message's measured output, as plain JSON-ready data."""
    result = walk_module.walk(EmlContainer(payload))
    return {
        "name": name,
        "walk": encode(result),
        "decode_chain": [encode(part.decode_chain) for part in result.parts],
        "body_text": _body_text_shape(payload),
        "attachment_payloads": _attachment_payloads_shape(payload),
    }


# ------------------------------------- Turn BODY1: the two accessor components


def _body_text_shape(payload: bytes) -> Any:
    """``body_text``'s answer for one message: the view, the text, the line table, the reason.

    The **version stamps are not in the fingerprint** -- the ledger key already carries the
    version, so a bump records a new line rather than moving an old one -- and neither is the
    ``BodyRefusal``'s prose ``detail`` (the reason id is the contract).
    """
    record = bodytext.body_text(payload)
    if isinstance(record, bodytext.BodyRefusal):
        return {"refused": record.reason_id}
    return {
        "view": record.view,
        "text": record.text,
        "truncated": record.truncated,
        "char_count": record.char_count,
        "reason_id": record.reason_id,
        "segments": [
            [start, end, locator.part, locator.view, locator.span.start, locator.span.end, locator.unit]
            for start, end, locator in record.segments
        ],
    }


def _attachment_payloads_shape(payload: bytes) -> Any:
    """``iter_attachment_payloads``'s answer: one row per occurrence, payload or refusal.

    A payload is fingered by the **digest** of its bytes (never the bytes, and never a hash of
    the whole list's bytes), a refusal by its occurrence reference and its closed reason id --
    not by its prose ``detail``, which is for a human.
    """
    rows: list[list[Any]] = []
    for item in bodytext.iter_attachment_payloads(payload):
        if isinstance(item, bodytext.AttachmentPayload):
            rows.append(
                [
                    "payload",
                    item.occurrence_ref,
                    item.filename,
                    item.media_type,
                    item.size,
                    sha256_hex(item.data),
                ]
            )
        else:
            rows.append(["refused", item.occurrence_ref, item.reason_id])
    return rows


# -------------------------------------------- Turn 1b.10b: the three .msg components


def _stream_digest(opened: "cfb_module.CfbFile", path: str) -> list[Any]:
    """One stream's bytes as ``[length, fault, sha256]`` -- read, never fabricated."""
    data, fault = cfb_module.read_stream(opened, path)
    return [len(data), fault, sha256_hex(data)]


def _cfb_shape(payload: bytes) -> Any:
    """The CFB primitives' output for one file (the ``cfb`` component).

    The header (version, sector and mini-sector shift, mini cutoff, the DIFAT/FAT/
    directory counts, the 109 inline DIFAT entries), the DIFAT/FAT walks, the directory
    shape (each entry's index, name, type, size, path and faults), every stream's size,
    bytes digest and chain fault, and the eight-class sector classification. Opened with
    ``require_properties=False``: this is the **primitives'** fingerprint, not the message
    check, so a well-formed CFB that carries no ``__properties_version1.0``
    (``msg_mini_cutoff_boundary``) is fingerprinted rather than refused.
    """
    opened = cfb_module.open_cfb(payload, require_properties=False)
    if not isinstance(opened, cfb_module.CfbFile):
        return {"refused": opened.reason}
    header = opened.header
    return {
        "header": [
            header.version,
            header.byte_order,
            header.sector_shift,
            header.mini_sector_shift,
            header.mini_cutoff,
            header.num_dir_sectors,
            header.num_fat_sectors,
            header.first_dir_sector,
            header.first_mini_fat_sector,
            header.num_mini_fat_sectors,
            header.first_difat_sector,
            header.num_difat_sectors,
            list(header.difat),
        ],
        "fat_sectors": list(opened.fat_sector_ids),
        "difat_sectors": list(opened.difat_sectors),
        "extended_difat": opened.extended_difat,
        "difat_fault": opened.difat_fault,
        "sector_count": opened.sector_count,
        "directory_entries": opened.directory_entries,
        "directory": [
            [entry.index, entry.name, entry.entry_type, entry.size, entry.path, list(entry.faults)]
            for entry in opened.entries
        ],
        "streams": [
            [
                stream.path,
                stream.mini,
                stream.size,
                stream.available,
                stream.fault,
                _stream_digest(opened, stream.path),
            ]
            for stream in opened.streams
        ],
        "accounting": [[name, value] for name, value in opened.accounting],
        "unaccounted": opened.unaccounted,
    }


def _msg_reader_shape(payload: bytes) -> Any:
    """The MAPI layer's output for one file (the ``msg_reader`` component).

    ``mapi``'s whole record: the class gate's verdict and the verbatim class, the two
    code pages, the decoded property table (``001E``/``001F``/multi-valued values, each
    value's ladder rung and ``encoding_source``), the recipient rows, the named/unknown
    tag sets, the declared counts and the attachment rows -- read straight from the
    reader, never projected to a sidecar column.
    """
    opened = cfb_module.open_cfb(payload)
    if not isinstance(opened, cfb_module.CfbFile):
        return {"refused": opened.reason}
    message = mapi_module.read_message(opened)
    attachments = mapi_module.read_attachments(
        opened, internet_codepage=message.internet_cp, message_codepage=message.message_cp
    )
    return {"message": encode(message), "attachments": encode(attachments)}


def _msg_projection_shape(payload: bytes) -> Any:
    """The virtual framing's output for one file (the ``msg_projection`` component).

    The projected virtual RFC 822 bytes' digest and length, the span table rows (source
    stream, byte offsets, digests, axes; the virtual offsets the persisted row drops, C2),
    the headers' UTF-8 re-encoding and the ``part_id``s the one walker measured over the
    projection. A container that refused projects empty bytes, and that is recorded as it
    is -- this component fingerprints every committed ``.msg``.
    """
    container = MsgContainer(payload)
    raw = container.raw_bytes()
    walked = walk_module.walk(container)
    parts = walked.parts
    fields = parts[0].header_fields if parts else []
    return {
        "virtual_sha256": sha256_hex(raw),
        "virtual_bytes": len(raw),
        "spans": encode(container.span_provenance),
        "headers": [
            [field.ordinal, field.name, field.raw_value.encode("utf-8").hex(), field.parse_status]
            for field in fields
        ],
        "part_ids": [part.part_id for part in parts],
    }


def _msg_pieces(payload: bytes) -> dict[str, Any]:
    """One ``.msg`` file's three measured outputs, as plain JSON-ready data."""
    return {
        "cfb": _cfb_shape(payload),
        "msg_reader": _msg_reader_shape(payload),
        "msg_projection": _msg_projection_shape(payload),
    }


def _pieces(name: str, payload: bytes) -> dict[str, Any]:
    """One message's measured outputs, for whichever components read its kind."""
    if _is_message(name):
        return _msg_pieces(payload)
    return _walk_pieces(name, payload)


def _fingerprint(component: str, names: Iterable[str], pieces: Mapping[str, Any]) -> str:
    """One component's fingerprint over its subset of a corpus version."""
    if component == "contracts":
        return contracts_fingerprint()
    names = list(names)
    if component == "decode_chain":
        return sha256_json({name: pieces[name]["decode_chain"] for name in names})
    return sha256_json({name: pieces[name][component] for name in names})


def _corpus_lists(
    fixtures_dir: str | Path | None,
    corpora: list[dict] | None,
    messages: list[dict] | None,
) -> tuple[list[dict], list[dict]]:
    """The two version lists, read from the manifest when the caller passes none."""
    if corpora is None:
        corpora = load_corpora() or [{"version": 1, "files": discovered(fixtures_dir)}]
    if messages is None:
        messages = load_message_corpora()
    return corpora, messages


def _version_space(component: str, corpora: list[dict], messages: list[dict]) -> list[dict]:
    """The version list a component's ``corpus:<N>`` half counts in."""
    return messages if component in MSG_COMPONENTS else corpora


def fingerprints(
    fixtures_dir: str | Path | None = None, corpus_version: int | None = None
) -> dict[str, str]:
    """Every component's fingerprint over the newest version of **its own** corpus.

    ``corpus_version``, when given and present in a component's space, picks that version
    instead.
    """
    by_component = all_fingerprints(fixtures_dir)
    out: dict[str, str] = {}
    for component in COMPONENTS:
        versions = sorted(by_component[component])
        if not versions:
            raise ValueError(f"{component}: its corpus has no version to fingerprint")
        chosen = corpus_version if corpus_version in versions else versions[-1]
        out[component] = by_component[component][chosen]
    return out


def all_fingerprints(
    fixtures_dir: str | Path | None = None,
    corpora: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> dict[str, dict[int, str]]:
    """Every component's fingerprint per version of its own corpus, measuring once.

    The walker's components fingerprint the ``.eml`` corpus versions and the three Phase 1b
    components the ``.msg`` corpus versions (:func:`load_message_corpora`), each message
    measured at most once (the pieces are shared). So a ``.msg`` fixture entering its
    corpus adds lines for the three alone and moves no walker fingerprint, and an ``.eml``
    one the reverse -- which is what an unchanged ``--check`` over the committed corpora
    proves.
    """
    corpora, messages = _corpus_lists(fixtures_dir, corpora, messages)
    spaces: dict[str, dict[int, list[str]]] = {
        "eml": {entry["version"]: entry["files"] for entry in corpora},
        "msg": {entry["version"]: entry["files"] for entry in messages},
    }
    needed = sorted(
        {name for files in spaces.values() for names in files.values() for name in names}
    )
    pieces = {name: _pieces(name, _resolve(name, fixtures_dir)) for name in needed}
    return {
        component: {
            version: _fingerprint(component, _component_names(component, names), pieces)
            for version, names in spaces["msg" if component in MSG_COMPONENTS else "eml"].items()
        }
        for component in COMPONENTS
    }


# ------------------------------------------------------------- ledger file I/O


def load_ledger(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """The ledger as it stands on disk; ``{}`` when the file does not exist yet."""
    ledger_path = Path(path) if path is not None else LEDGER_PATH
    if not ledger_path.is_file():
        return {}
    return _read_ledger(ledger_path.read_text(encoding="utf-8"))


def _read_ledger(text: str) -> dict[str, dict[str, str]]:
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("the ledger must be a JSON object")
    return {name: dict(entry) for name, entry in loaded.items() if not name.startswith("_")}


def render(ledger: Mapping[str, Mapping[str, str]]) -> str:
    """The canonical file text: the header first, sorted keys, one trailing newline."""
    body = {"_comment": _HEADER, **{name: dict(entry) for name, entry in ledger.items()}}
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_ledger(ledger: Mapping[str, Mapping[str, str]], path: str | Path | None = None) -> Path:
    ledger_path = Path(path) if path is not None else LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    # `newline="\n"`: the ledger's bytes are then the same on every platform, which is
    # the property the file exists to carry.
    with ledger_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(ledger))
    return ledger_path


# --------------------------------------------------------------- check / record


def check(
    ledger: Mapping[str, Mapping[str, str]] | None = None,
    *,
    computed: Mapping[str, str] | None = None,
    fixtures_dir: str | Path | None = None,
    corpora: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> list[str]:
    """Every way the ledger disagrees with the code; ``[]`` means the guard holds.

    Both halves of the discipline are here: a component whose *current* version
    string is missing from the ledger is a bump nobody recorded, and one whose
    recorded fingerprint differs from the recomputed one is a behavior change
    nobody bumped for. Every problem names the constant to bump. A payload loaded
    straight from the file is accepted, ``_comment`` and all -- names starting
    with ``_`` are skipped, never interpreted as components.

    Each component is compared in **its own** corpus space: the walker's against the
    ``.eml`` corpus versions and the three Phase 1b components against the ``.msg`` ones
    (:func:`_version_space`).
    """
    ledger = load_ledger() if ledger is None else {k: v for k, v in ledger.items() if not k.startswith("_")}
    corpora, messages = _corpus_lists(fixtures_dir, corpora, messages)
    problems: list[str] = []
    if not load_corpora():
        problems.append(
            "corpus: tests/ledger/corpus.json is missing -- run "
            "tools/update_behavior_ledger.py to write corpus version 1"
        )
    else:
        problems.extend(_corpus_drift("corpus", discovered(fixtures_dir), corpora))
    if messages:
        problems.extend(
            _corpus_drift("message corpus", discovered_messages(fixtures_dir), messages)
        )
    if computed is None:
        by_component = all_fingerprints(fixtures_dir, corpora, messages)
    else:
        by_component = {
            component: {latest_corpus(_version_space(component, corpora, messages)): value}
            for component, value in computed.items()
        }
    for component, version in version_strings().items():
        entry = ledger.get(component)
        entry = entry if isinstance(entry, Mapping) else {}
        latest = latest_corpus(_version_space(component, corpora, messages))
        key = entry_key(component, version, latest)
        if key not in entry:
            problems.append(
                f"{component}: {key!r} is not in the ledger -- record it "
                f"(tools/update_behavior_ledger.py) in the same commit as the change; "
                f"if the behavior changed, bump {VERSION_CONSTANTS[component]} first"
            )
        for corpus_version, current in sorted(by_component[component].items()):
            recorded_key = entry_key(component, version, corpus_version)
            if recorded_key in entry and entry[recorded_key] != current:
                problems.append(
                    f"{component}: {recorded_key!r} was recorded with fingerprint "
                    f"{entry[recorded_key]} but the code now computes {current} "
                    f"-- the behavior changed without a bump: bump "
                    f"{VERSION_CONSTANTS[component]} and record the new version"
                )
    return problems


def _corpus_drift(what: str, found: list[str], versions: list[dict]) -> list[str]:
    """The "today's files differ from the newest version" problem for one corpus, or ``[]``."""
    latest = latest_corpus(versions)
    named = next(entry["files"] for entry in versions if entry["version"] == latest)
    if sorted(found) == sorted(named):
        return []
    noun = "today's .msg messages" if what == "message corpus" else "today's messages"
    return [
        f"corpus: {noun} differ from {what} {latest} in tests/ledger/corpus.json -- "
        "growing the corpus adds a corpus version (tools/update_behavior_ledger.py "
        "records it; it bumps no component version)"
    ]


def record(
    ledger: Mapping[str, Mapping[str, str]],
    *,
    computed: Mapping[str, str] | None = None,
    fixtures_dir: str | Path | None = None,
    corpora: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Append each component's current version and fingerprint for every corpus of its kind.

    Appends only: a key already recorded with the fingerprint the code still
    computes is left alone, and one recorded with a *different* fingerprint is a
    :class:`ValueError` naming the constant to bump -- that is the case where the
    change needs a bump, not a new line under the old version. Names starting
    with ``_`` in the payload are skipped, so a ledger loaded straight from the
    file (``_comment`` included) can be passed in as-is.
    """
    corpora, messages = _corpus_lists(fixtures_dir, corpora, messages)
    if computed is None:
        by_component = all_fingerprints(fixtures_dir, corpora, messages)
    else:
        by_component = {
            component: {latest_corpus(_version_space(component, corpora, messages)): value}
            for component, value in computed.items()
        }
    updated = {
        name: dict(entry) for name, entry in ledger.items() if not name.startswith("_")
    }
    lines: list[str] = []
    for component, version in version_strings().items():
        entry = updated.setdefault(component, {})
        for corpus_version, current in sorted(by_component[component].items()):
            key = entry_key(component, version, corpus_version)
            recorded = entry.get(key)
            if recorded == current:
                lines.append(f"{component} {key}: unchanged ({recorded})")
            elif recorded is not None:
                raise ValueError(
                    f"{component}: {key!r} is already recorded with fingerprint "
                    f"{recorded}, but the code now computes {current}. Bump "
                    f"{VERSION_CONSTANTS[component]} and record the new version -- an "
                    f"existing key is never overwritten."
                )
            else:
                entry[key] = current
                lines.append(f"{component} {key}: appended {current}")
            if component not in CORPUS_DEPENDENT:
                break  # corpus-independent: one line is the whole fact
    return updated, lines


__all__ = [
    "COMPONENTS",
    "CORPUS_DEPENDENT",
    "CORPUS_PATH",
    "FIXTURES",
    "INLINE_CORPUS",
    "LEDGER_PATH",
    "LEGACY_KEYS",
    "MSG_COMPONENTS",
    "MSG_HOSTILE_STEMS",
    "VERSION_CONSTANTS",
    "add_corpus_version",
    "add_message_corpus_version",
    "all_fingerprints",
    "check",
    "contract_records",
    "contracts_fingerprint",
    "corpus",
    "discovered",
    "discovered_messages",
    "entry_key",
    "fingerprints",
    "latest_corpus",
    "load_corpora",
    "load_ledger",
    "load_message_corpora",
    "message_corpus",
    "record",
    "render",
    "version_strings",
    "write_corpora",
    "write_ledger",
]
