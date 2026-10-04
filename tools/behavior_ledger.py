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

from emailextract import ids as ids_module  # noqa: E402
from emailextract import model, seam, siblings, store, timeevent, versions  # noqa: E402
from emailextract import walk as walk_module  # noqa: E402
from emailextract.container import EmlContainer  # noqa: E402

#: The component names, in the ledger's own order.
COMPONENTS = ("walk", "decode_chain", "contracts")

#: Which constant a component's version string is built from -- what to bump.
VERSION_CONSTANTS = {
    "walk": "EMAIL_PARSER_VERSION (or DECODE_CHAIN_VERSION)",
    "decode_chain": "DECODE_CHAIN_VERSION",
    "contracts": "OUTPUT_SCHEMA_VERSION",
}

#: The components whose fingerprint is over the corpus. ``contracts`` is over the
#: record definitions alone, so it is keyed by its version and nothing else.
CORPUS_DEPENDENT = ("walk", "decode_chain")

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
    "(the .eml files under fixtures/, excluding local-only real/; --fixtures DIR "
    "points elsewhere), and tests/ledger/corpus.json lists each corpus version's "
    "message names. Adding a message or a fixture adds a corpus version and NEW "
    "LINES under the SAME component versions "
    "-- it is not a behavior change and bumps nothing; the tool refuses to record a "
    "new corpus if any older corpus's fingerprint moved (that is a behavior change "
    "that needs a bump). 'contracts' does not depend on the corpus and is keyed by "
    "this package's OUTPUT_SCHEMA_VERSION alone; before Turn 0.5 it was keyed by the "
    "core codec's SCHEMA_VERSION, so the '7' line under 'contracts' is LEGACY -- kept "
    "in place (append-only) and never compared again. Fingerprints are identical on "
    "CPython 3.14.3 and "
    "3.11.15 (measured in Turn 0.2; re-measured unchanged over the Turn 0.3 "
    "fixtures in Turn 0.3); a cross-interpreter difference is recorded "
    "here, never hidden. The history before this file is not reconstructed. Record "
    "lines with tools/update_behavior_ledger.py in the same commit as the change "
    "that caused them."
)

_CORPUS_HEADER = (
    "The ledger's corpora, oldest first: each version lists the message names its "
    "fingerprints were taken over (tools/behavior_ledger.INLINE_CORPUS names for "
    "corpus version 1; relative paths under the fixtures corpus source since the "
    "Turn 0.3 switch, --fixtures DIR for another source). Growing the corpus adds "
    "a version here -- the tool detects a changed file list and appends it "
    "automatically; it never bumps a component version."
)


# ------------------------------------------------------------------ the corpus


def corpus(fixtures_dir: str | Path | None = None) -> dict[str, bytes]:
    """Every corpus message, by name: the ``.eml`` files under the corpus source.

    The source is the committed fixtures since the Turn 0.3 switch (``--fixtures``
    points elsewhere); ``INLINE_CORPUS`` is history and is reachable through
    :func:`_resolve`, never listed here.
    """
    root = Path(fixtures_dir) if fixtures_dir is not None else FIXTURES
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.eml"))
        if _LOCAL_ONLY not in path.relative_to(root).parts
    }


def discovered(fixtures_dir: str | Path | None = None) -> list[str]:
    """The corpus message names, in a machine-independent order."""
    return sorted(corpus(fixtures_dir))


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


def load_corpora(path: str | Path | None = None) -> list[dict]:
    """The corpus versions on disk, oldest first; ``[]`` when there is none yet."""
    manifest = Path(path) if path is not None else CORPUS_PATH
    if not manifest.is_file():
        return []
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    return [
        {"version": int(entry["version"]), "files": list(entry["files"])}
        for entry in loaded.get("corpora", [])
    ]


def write_corpora(corpora: list[dict], path: str | Path | None = None) -> Path:
    manifest = Path(path) if path is not None else CORPUS_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    body = {"_comment": _CORPUS_HEADER, "corpora": corpora}
    with manifest.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return manifest


def latest_corpus(corpora: list[dict]) -> int:
    return max((entry["version"] for entry in corpora), default=0)


def add_corpus_version(
    fixtures_dir: str | Path | None = None, corpora: list[dict] | None = None
) -> tuple[list[dict], bool]:
    """Append a corpus version for today's message list; ``False`` when unchanged."""
    corpora = load_corpora() if corpora is None else corpora
    files = discovered(fixtures_dir)
    if corpora and sorted(corpora[-1]["files"]) == files:
        return corpora, False
    return [*corpora, {"version": latest_corpus(corpora) + 1, "files": files}], True


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
    """One message's measured output, as plain JSON-ready data."""
    result = walk_module.walk(EmlContainer(payload))
    return {
        "name": name,
        "walk": encode(result),
        "decode_chain": [encode(part.decode_chain) for part in result.parts],
    }


def fingerprints(
    fixtures_dir: str | Path | None = None, corpus_version: int | None = None
) -> dict[str, str]:
    """Every component's fingerprint over one corpus (the latest by default)."""
    corpora = load_corpora()
    if not corpora:
        corpora = [{"version": 1, "files": discovered(fixtures_dir)}]
    version = latest_corpus(corpora) if corpus_version is None else corpus_version
    return all_fingerprints(fixtures_dir, [version], corpora)[version]


def all_fingerprints(
    fixtures_dir: str | Path | None = None,
    corpus_versions: list[int] | None = None,
    corpora: list[dict] | None = None,
) -> dict[int, dict[str, str]]:
    """Fingerprints per corpus version, walking each message exactly once."""
    corpora = load_corpora() if corpora is None else corpora
    if not corpora:
        corpora = [{"version": 1, "files": discovered(fixtures_dir)}]
    wanted = corpus_versions if corpus_versions is not None else [latest_corpus(corpora)]
    by_version = {entry["version"]: entry["files"] for entry in corpora}
    needed = sorted({name for version in wanted for name in by_version[version]})
    pieces = {name: _walk_pieces(name, _resolve(name, fixtures_dir)) for name in needed}
    out: dict[int, dict[str, str]] = {}
    for version in wanted:
        names = by_version[version]
        out[version] = {
            "walk": sha256_json({name: pieces[name]["walk"] for name in names}),
            "decode_chain": sha256_json({name: pieces[name]["decode_chain"] for name in names}),
            "contracts": contracts_fingerprint(),
        }
    return out


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
) -> list[str]:
    """Every way the ledger disagrees with the code; ``[]`` means the guard holds.

    Both halves of the discipline are here: a component whose *current* version
    string is missing from the ledger is a bump nobody recorded, and one whose
    recorded fingerprint differs from the recomputed one is a behavior change
    nobody bumped for. Every problem names the constant to bump. A payload loaded
    straight from the file is accepted, ``_comment`` and all -- names starting
    with ``_`` are skipped, never interpreted as components.
    """
    ledger = load_ledger() if ledger is None else {k: v for k, v in ledger.items() if not k.startswith("_")}
    if corpora is None:
        corpora = load_corpora() or [{"version": 1, "files": discovered(fixtures_dir)}]
    latest = latest_corpus(corpora)
    problems: list[str] = []
    if not load_corpora():
        problems.append(
            "corpus: tests/ledger/corpus.json is missing -- run "
            "tools/update_behavior_ledger.py to write corpus version 1"
        )
    elif sorted(discovered(fixtures_dir)) != sorted(
        next(entry["files"] for entry in corpora if entry["version"] == latest)
    ):
        problems.append(
            "corpus: today's messages differ from corpus "
            f"{latest} in tests/ledger/corpus.json -- growing the corpus adds a corpus "
            "version (tools/update_behavior_ledger.py records it; it bumps no component "
            "version)"
        )
    if computed is None:
        current_versions = version_strings()
        wanted = sorted(
            {
                entry["version"]
                for entry in corpora
                for component, version in current_versions.items()
                if entry_key(component, version, entry["version"]) in (ledger.get(component) or {})
            }
            | {latest}
        )
        by_corpus = all_fingerprints(fixtures_dir, wanted, corpora)
    else:
        by_corpus = {latest: dict(computed)}
    for component, version in version_strings().items():
        entry = ledger.get(component)
        entry = entry if isinstance(entry, Mapping) else {}
        key = entry_key(component, version, latest)
        if key not in entry:
            problems.append(
                f"{component}: {key!r} is not in the ledger -- record it "
                f"(tools/update_behavior_ledger.py) in the same commit as the change; "
                f"if the behavior changed, bump {VERSION_CONSTANTS[component]} first"
            )
        for corpus_version, current in sorted(by_corpus.items()):
            recorded_key = entry_key(component, version, corpus_version)
            if recorded_key in entry and entry[recorded_key] != current[component]:
                problems.append(
                    f"{component}: {recorded_key!r} was recorded with fingerprint "
                    f"{entry[recorded_key]} but the code now computes {current[component]} "
                    f"-- the behavior changed without a bump: bump "
                    f"{VERSION_CONSTANTS[component]} and record the new version"
                )
    return problems


def record(
    ledger: Mapping[str, Mapping[str, str]],
    *,
    computed: Mapping[str, str] | None = None,
    fixtures_dir: str | Path | None = None,
    corpora: list[dict] | None = None,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Append each component's current version and fingerprint for every corpus.

    Appends only: a key already recorded with the fingerprint the code still
    computes is left alone, and one recorded with a *different* fingerprint is a
    :class:`ValueError` naming the constant to bump -- that is the case where the
    change needs a bump, not a new line under the old version. Names starting
    with ``_`` in the payload are skipped, so a ledger loaded straight from the
    file (``_comment`` included) can be passed in as-is.
    """
    if corpora is None:
        corpora = load_corpora() or [{"version": 1, "files": discovered(fixtures_dir)}]
    latest = latest_corpus(corpora)
    if computed is None:
        by_corpus = all_fingerprints(
            fixtures_dir, [entry["version"] for entry in corpora], corpora
        )
    else:
        by_corpus = {latest: dict(computed)}
    updated = {
        name: dict(entry) for name, entry in ledger.items() if not name.startswith("_")
    }
    lines: list[str] = []
    for component, version in version_strings().items():
        entry = updated.setdefault(component, {})
        for corpus_version, current in sorted(by_corpus.items()):
            key = entry_key(component, version, corpus_version)
            recorded = entry.get(key)
            if recorded == current[component]:
                lines.append(f"{component} {key}: unchanged ({recorded})")
            elif recorded is not None:
                raise ValueError(
                    f"{component}: {key!r} is already recorded with fingerprint "
                    f"{recorded}, but the code now computes {current[component]}. Bump "
                    f"{VERSION_CONSTANTS[component]} and record the new version -- an "
                    f"existing key is never overwritten."
                )
            else:
                entry[key] = current[component]
                lines.append(f"{component} {key}: appended {current[component]}")
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
    "VERSION_CONSTANTS",
    "add_corpus_version",
    "all_fingerprints",
    "check",
    "contract_records",
    "contracts_fingerprint",
    "corpus",
    "discovered",
    "entry_key",
    "fingerprints",
    "latest_corpus",
    "load_corpora",
    "load_ledger",
    "record",
    "render",
    "version_strings",
    "write_corpora",
    "write_ledger",
]
