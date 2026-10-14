"""Turn 1b.0c: the committed ``.eml`` golden, and the net under the frozen-module edits.

``tests/golden/eml_golden.json`` is the recorded golden ``tools/update_eml_golden.py``
writes: over the committed ``.eml`` corpus it pins the ``ParseResult``, the serialized
``EmailDocument``, the ``WalkResult``, every ``CapRecord``, the ``resolve_span`` samples
(the C2 identity guard) and the two store artifacts' bytes and keys.

This module only ever **reads** the committed file and recomputes the pins; it never
records. Recording is the explicit command ``python tools/update_eml_golden.py`` run in
the same commit as the change that moved a value (build rule 2).

The 1b.1-style comparator (``_classify``) lives **here in the test module**, not in
``tests/support/``: it is the classification Turn 1b.1's
``test_the_bump_moved_only_the_version_and_the_null_keys`` reuses, and it needs no
shared fixture -- a support module would add a file the label ledger has to cover for
no gain.
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(ROOT / "tools"), str(ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import behavior_ledger  # noqa: E402  (the corpus enumeration, the same one the golden used)
from docextract_core.codec import from_json  # noqa: E402
from emailextract import versions  # noqa: E402
from emailextract.assemble import assemble, document_key  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.model import record_to_bytes  # noqa: E402
from emailextract.store import (  # noqa: E402
    DocumentArtifact,
    WalkArtifact,
    artifact_key,
    document_artifact,
    walk_artifact,
)

#: Imported by name -- deliberately **not** ``update_eml_golden.write``: the recorder's
#: write path is never reachable from this module (see ``test_the_golden_is_not_
#: regenerated_silently``).
from update_eml_golden import (  # noqa: E402
    GOLDEN_VERSION,
    LIMITS,
    WAIVER,
    canonical_bytes,
    compare,
    record,
)

GOLDEN_PATH = ROOT / "tests" / "golden" / "eml_golden.json"
LEDGER_PATH = ROOT / "tests" / "ledger" / "label_ledger.json"
GOLDEN_REL = "tests/golden/eml_golden.json"

#: The six pins every fixture record must carry.
PINS = ("parse_result", "document", "walk", "caps", "span_samples", "store")

#: The leaves a waiver pattern may name. Every one is a recorded-only input or a value
#: derived from one; a waiver may never name a measured value (a part id, a sha256, a
#: span, a cap).
WAIVABLE_LEAVES = frozenset({"recorded_on", "HTMLTEXT_VERSION", "key", "path", "bytes_hex"})

#: The keys the one permitted re-record (Turn 1b.1) may add with a ``null`` value.
PERMITTED_ADDED_KEYS = frozenset({"stream_ref"})


def _read_golden_bytes() -> bytes:
    """The committed golden's bytes, opened **read-only** and never written here."""
    with open(GOLDEN_PATH, "rb") as handle:
        return handle.read()


def _load() -> dict:
    return json.loads(_read_golden_bytes().decode("utf-8"))


def _fixture_bytes(name: str) -> bytes:
    return (ROOT / "fixtures" / name).read_bytes()


def _waiver(golden: dict) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(str(segment) for segment in path) for path in golden["header"]["waiver"])


#: The only per-key moves a **decoded** document artifact may show across interpreters:
#: the recorded-only projection stamp and the key that names it.
_ARTIFACT_STAMP_PATHS = frozenset(
    {
        ("record", "key"),
        ("record", "projection_versions", "HTMLTEXT_VERSION"),
        ("record", "document", "run_record", "projection_versions", "HTMLTEXT_VERSION"),
    }
)


def _assert_only_the_stamp_moved(name: str, committed_bytes: bytes, other_bytes: bytes) -> None:
    """The coarse ``bytes_hex`` waiver hides nothing: only the stamp and its key moved."""
    old = json.loads(committed_bytes.decode("utf-8"))
    new = json.loads(other_bytes.decode("utf-8"))
    for path, _old, _new in compare(old, new, ()):
        assert path in _ARTIFACT_STAMP_PATHS, (name, path)


def _describe(differences: list) -> str:
    lines = [f"{'/'.join(path)}: {old!r} -> {new!r}" for path, old, new in differences[:20]]
    return f"{len(differences)} difference(s):\n" + "\n".join(lines)


@pytest.fixture(scope="module")
def fresh() -> dict:
    """One fresh recording, shared by the module's tests (the recorder is not cheap)."""
    return record()


# --------------------------------------------------------------- the golden vs the corpus


def test_the_golden_matches_the_committed_corpus(fresh: dict) -> None:
    """Recompute every pin from the fixture bytes and compare it to the committed file."""
    committed = _load()
    differences = compare(committed, fresh, _waiver(committed))
    assert differences == [], _describe(differences)
    # ... and the committed file is exactly the canonical bytes a recording produces.
    assert _read_golden_bytes() == canonical_bytes(committed)


def test_the_golden_pins_the_document_walk_spans_caps_and_store_bytes(fresh: dict) -> None:
    """Every fixture carries the six pins, and ``store`` carries real artifact bytes."""
    committed = _load()
    fixtures = committed["fixtures"]
    assert fixtures
    sample = sorted(fixtures)[:3] + ["generated/cap_enormous_header_block.eml"]
    for name, payload in fixtures.items():
        assert set(PINS) <= set(payload), name
        store = payload["store"]
        walk_bytes = bytes.fromhex(store["walk"]["bytes_hex"])
        document_bytes = bytes.fromhex(store["document"]["bytes_hex"])
        # The bytes are not a hash of the artifact: they decode to the artifact itself,
        # and re-encoding that artifact reproduces them byte for byte.
        walk_art = from_json(WalkArtifact, walk_bytes.decode("utf-8"))
        document_art = from_json(DocumentArtifact, document_bytes.decode("utf-8"))
        assert record_to_bytes(walk_art) == walk_bytes, name
        assert record_to_bytes(document_art) == document_bytes, name
        assert store["walk"]["key"] == walk_art.key, name
        assert store["document"]["key"] == document_art.key, name
        assert store["walk"]["path"] == f"walks/{walk_art.key}.json", name
        assert store["document"]["path"] == f"documents/{document_art.key}.json", name
        # A sample is recomputed from the fixture bytes: the pinned bytes are the ones
        # this container's artifacts really produce.
        if name in sample:
            container = EmlContainer(memory_bytes(_fixture_bytes(name)))
            # The walk artifact carries no recorded-only stamp: its bytes are the same
            # on every interpreter, so this is an exact comparison.
            assert store["walk"]["bytes_hex"] == record_to_bytes(walk_artifact(container)).hex(), name
            # The document artifact names the projection versions, so across
            # interpreters it may move only in the recorded-only stamp and its key.
            _assert_only_the_stamp_moved(
                name,
                document_bytes,
                record_to_bytes(document_artifact(container, limits=LIMITS)),
            )
            assert payload["caps"] == [
                _encoded(cap) for cap in assemble(container, limits=LIMITS).run_record.caps
            ], name
        assert isinstance(payload["span_samples"]["parts"], list), name
        assert isinstance(payload["span_samples"]["headers"], list), name
        assert payload["caps"] is None or isinstance(payload["caps"], list), name
    # Non-vacuity: at least one fixture really resolves a part's own span.
    assert any(payload["span_samples"]["parts"] for payload in fixtures.values())


def _encoded(record_: object) -> dict:
    from docextract_core.codec import encode

    return encode(record_)


def test_the_golden_is_not_regenerated_silently() -> None:
    """Recording is the recorder's job: this module only reads the golden."""
    source = Path(__file__).read_text(encoding="utf-8")
    # The recorder's write path is not even bound here (it is not imported by name).
    assert "write" not in globals(), "the test module imported the recorder's write path"
    # The golden is opened read-only ...
    assert 'open(GOLDEN_PATH, "rb")' in source, "the golden must be opened read-only"
    # ... and there is no write-mode open of it, anywhere in the module.
    write_open = "open(GOLDEN_PATH, " + '"w'
    assert write_open not in source
    # No file is written at all from this module: no write call, no temp file.
    assert ("write" + "(") not in source, "the test module writes a file"
    assert ("tmp" + "_path") not in source, "the test module must not stage a golden on disk"
    # The recording command is named, so a reader knows how to re-record.
    assert "update_eml_golden" in source
    assert GOLDEN_REL in LEDGER_PATH.read_text(encoding="utf-8")


def test_the_golden_checks_both_interpreters_with_a_recorded_waiver(fresh: dict) -> None:
    """The waiver names the recorded-only paths the two interpreters differ in -- nothing else."""
    committed = _load()
    header = committed["header"]
    waiver = _waiver(committed)
    # The recorded waiver is exactly the tool's declared waiver; every entry is a
    # recorded-only leaf, never a measured value.
    assert header["waiver"] == [list(path) for path in WAIVER]
    for path in waiver:
        assert path[0] in {"header", "fixtures"}, path
        assert path[-1] in WAIVABLE_LEAVES, path

    observed = compare(committed, fresh, ())
    recording_here = header["recorded_on"] == fresh["header"]["recorded_on"]
    if recording_here:
        # On the recording interpreter nothing is waived: the committed file is
        # reproduced byte for byte, so no pinned value can hide behind a waiver.
        assert observed == [], _describe(observed)
    else:
        # On the other interpreter every difference is a declared waiver path, and
        # every declared pattern really fires (a stale pattern is a defect).
        assert observed, "a non-recording interpreter with no difference is suspicious"
        for path, _old, _new in observed:
            assert any(_matches(path, pattern) for pattern in waiver), path
        for pattern in waiver:
            assert any(_matches(path, pattern) for path, _a, _b in observed), pattern

    # The walk artifact carries no recorded-only stamp: it is byte-identical, unwaived.
    for name, payload in committed["fixtures"].items():
        assert payload["store"]["walk"]["bytes_hex"] == fresh["fixtures"][name]["store"]["walk"]["bytes_hex"], name
    # The document artifact's coarse byte-waiver hides nothing: its decoded JSON
    # differs only in the recorded-only projection stamp and the key that names it.
    for name, payload in committed["fixtures"].items():
        _assert_only_the_stamp_moved(
            name,
            bytes.fromhex(payload["store"]["document"]["bytes_hex"]),
            bytes.fromhex(fresh["fixtures"][name]["store"]["document"]["bytes_hex"]),
        )


def _matches(path: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    return len(path) == len(pattern) and all(
        want == "*" or want == got for want, got in zip(pattern, path)
    )


# --------------------------------------------------------------- the falsifier


def _mutate_part_id(golden: dict) -> tuple[tuple[str, ...], object]:
    name = next(
        n for n in sorted(golden["fixtures"]) if golden["fixtures"][n]["document"]["record"]["parts"]
    )
    parts = golden["fixtures"][name]["document"]["record"]["parts"]
    old = parts[0]["part_id"]
    parts[0]["part_id"] = hashlib.sha256(b"not the part's content").hexdigest()
    return ("fixtures", name, "document", "record", "parts", "0", "part_id"), old


def _mutate_sha256(golden: dict) -> tuple[tuple[str, ...], object]:
    for name in sorted(golden["fixtures"]):
        parts = golden["fixtures"][name]["document"]["record"]["parts"]
        for index, part in enumerate(parts):
            if part.get("sha256"):
                old = part["sha256"]
                part["sha256"] = hashlib.sha256(b"not the part's bytes").hexdigest()
                return ("fixtures", name, "document", "record", "parts", str(index), "sha256"), old
    raise AssertionError("the golden pins no sha256")


def _mutate_span_offset(golden: dict) -> tuple[tuple[str, ...], object]:
    for name in sorted(golden["fixtures"]):
        parts = golden["fixtures"][name]["span_samples"]["parts"]
        for part_index, part in enumerate(parts):
            for sample_index, sample in enumerate(part["samples"]):
                answer = sample["answer"]
                if answer.get("kind") == "raw_span" and answer.get("offset", 0) > 0:
                    old = answer["offset"]
                    answer["offset"] = old + 1
                    return (
                        "fixtures", name, "span_samples", "parts", str(part_index),
                        "samples", str(sample_index), "answer", "offset",
                    ), old
    raise AssertionError("the golden resolves no nonzero-offset span")


def _mutate_cap_value(golden: dict) -> tuple[tuple[str, ...], object]:
    for name in sorted(golden["fixtures"]):
        caps = golden["fixtures"][name]["caps"]
        if caps:
            old = caps[0]["cap_value_bytes"]
            caps[0]["cap_value_bytes"] = old + 1
            return ("fixtures", name, "caps", "0", "cap_value_bytes"), old
    raise AssertionError("the golden pins no CapRecord to mutate")


def test_a_changed_measured_value_fails_the_golden() -> None:
    """The falsifier: a moved part id, sha256, span offset or cap value must be caught."""
    committed = _load()
    waiver = _waiver(committed)
    for mutate in (_mutate_part_id, _mutate_sha256, _mutate_span_offset, _mutate_cap_value):
        mutated = copy.deepcopy(committed)
        path, old = mutate(mutated)
        assert mutated["fixtures"] != committed["fixtures"], "the mutation changed nothing"
        differences = compare(committed, mutated, waiver)
        assert differences, f"the golden did not fail for {path}"
        assert any(tuple(changed) == path for changed, _o, _n in differences), (
            path,
            _describe(differences),
        )
        assert old is not None


# --------------------------------------------------------------- the 1b.1 comparator


def _is_permitted_move(path: tuple[str, ...], old: object, new: object) -> bool:
    """The one permitted re-record: a version stamp, its derived keys, a new null key."""
    leaf = path[-1]
    if leaf in {"schema_version", "output_schema_version"}:
        return isinstance(old, str) and isinstance(new, str) and old != new
    if leaf in {"key", "path"} and "store" in path:
        return isinstance(old, str) and isinstance(new, str) and old != new
    if leaf == "bytes_hex" and "store" in path:
        return isinstance(old, str) and isinstance(new, str) and old != new
    if leaf in PERMITTED_ADDED_KEYS:
        return old is None
    return False


def _classify(old: dict, new: dict) -> str:
    """``identical``, ``permitted`` (the bump and nothing else) or ``not_permitted``."""
    differences = compare(old, new, ())
    if not differences:
        return "identical"
    for path, old_value, new_value in differences:
        if not _is_permitted_move(path, old_value, new_value):
            return "not_permitted"
    return "permitted"


def _bump_only_the_version(golden: dict) -> dict:
    """The in-memory bump: the two version stamps and the store keys that name them."""
    bumped = copy.deepcopy(golden)
    new_version = str(int(bumped["header"]["schema_version"]) + 1)
    bumped["header"]["schema_version"] = new_version
    for name, payload in bumped["fixtures"].items():
        payload["document"]["record"]["output_schema_version"] = new_version
        payload["document"]["record"]["run_record"]["output_schema_version"] = new_version
        for kind in ("walk", "document"):
            moved = hashlib.sha256((payload["store"][kind]["key"] + new_version).encode()).hexdigest()
            payload["store"][kind]["key"] = moved
            payload["store"][kind]["path"] = f"{kind}s/{moved}.json"
    return bumped


def test_a_changed_schema_version_alone_is_the_permitted_move() -> None:
    """The comparator Turn 1b.1 reuses: a bump alone is permitted, anything else is not."""
    committed = _load()
    assert _classify(committed, copy.deepcopy(committed)) == "identical"

    bumped = _bump_only_the_version(committed)
    assert bumped["fixtures"] != committed["fixtures"], "the bump moved nothing"
    assert _classify(committed, bumped) == "permitted"

    stray = copy.deepcopy(bumped)
    parts = stray["fixtures"][sorted(stray["fixtures"])[0]]["document"]["record"]["parts"]
    parts[0]["part_id"] = hashlib.sha256(b"a stray move").hexdigest()
    assert _classify(committed, stray) == "not_permitted"


def _pre_bump(golden: dict) -> dict:
    """The committed golden with the three permitted classes reversed (an in-memory 1b.0c form).

    Undoes exactly what the bump added: the version stamps, one ``stream_ref`` key per
    ``PartRecord``/``HeaderField`` and one ``embedded`` key per ``AttachmentOccurrence``.
    The store keys/paths/bytes are left as recorded (their move is checked against the
    re-computed keys instead, so the reconstruction cannot hide one).
    """
    pre = copy.deepcopy(golden)
    pre["header"]["schema_version"] = "5"
    for payload in pre["fixtures"].values():
        record = payload["document"]["record"]
        record["output_schema_version"] = "5"
        if record.get("run_record"):
            record["run_record"]["output_schema_version"] = "5"
        for part in record["parts"]:
            part.pop("stream_ref", None)
        for field in record["headers"]:
            field.pop("stream_ref", None)
        for occurrence in record["attachments"]:
            occurrence.pop("embedded", None)
    return pre


def test_the_bump_moved_only_the_version_and_the_null_keys(
    fresh: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-recorded golden vs the 1b.0c form: the bump moved exactly three classes, nothing else.

    The three are (contract section 1): the ``"5"`` -> ``"6"`` value and every store key/path
    that names it; one ``"stream_ref": null`` per ``PartRecord``/``HeaderField``; and one
    ``"embedded": null`` per ``AttachmentOccurrence`` (D2's correction). Everything a measured
    value carries -- the ``WalkResult`` pins, every ``part_id``/``sha256``/span, the
    ``CapRecord``s, the ``ParseResult`` -- is byte-identical.
    """
    committed = _load()
    assert committed["header"]["schema_version"] == versions.OUTPUT_SCHEMA_VERSION == "6"
    # The committed file is a fresh recording of the current code: nothing else moved.
    assert compare(committed, fresh, _waiver(committed)) == []

    pre_bump = _pre_bump(committed)

    # Every value difference is one of the permitted moves (the version, or a store byte/key).
    differences = compare(pre_bump, committed, ())
    assert differences, "the bump moved nothing"
    for path, old, new in differences:
        assert _is_permitted_move(path, old, new), path

    # The added keys really are present, and exactly one per record: the only added key is
    # ``stream_ref`` on a PartRecord/HeaderField and ``embedded`` on an AttachmentOccurrence.
    for name, payload in committed["fixtures"].items():
        record = payload["document"]["record"]
        before = pre_bump["fixtures"][name]["document"]["record"]
        assert pre_bump["fixtures"][name]["walk"] == payload["walk"], name  # WalkResult byte-identical
        for old, new in zip(before["parts"], record["parts"]):
            assert new.get("stream_ref", "MISSING") is None, name
            assert set(new) - set(old) == {"stream_ref"}, name
            assert set(old) - set(new) == set(), name
        for old, new in zip(before["headers"], record["headers"]):
            assert new.get("stream_ref", "MISSING") is None, name
            assert set(new) - set(old) == {"stream_ref"}, name
        for old, new in zip(before["attachments"], record["attachments"]):
            assert new.get("embedded", "MISSING") is None, name
            assert set(new) - set(old) == {"embedded"}, name

    # The store keys/paths move by exactly the version string, and by nothing else: the live
    # key is the live function of the live constant, and the pre-bump key differs from it.
    # The *walk* key names no projection version, so it is interpreter-independent and pinned
    # by value; the *document* key names ``HTMLTEXT_VERSION`` (the CPython minor), so it is
    # compared freshly here (its cross-interpreter waiver is
    # ``test_the_golden_checks_both_interpreters_with_a_recorded_waiver``'s).
    for name, payload in committed["fixtures"].items():
        container = EmlContainer(memory_bytes(_fixture_bytes(name)))
        live_walk = artifact_key(container)
        assert payload["store"]["walk"]["key"] == live_walk
        assert payload["store"]["walk"]["path"] == f"walks/{live_walk}.json"
        live_doc = document_key(container.container_hash(), limits=LIMITS)
        monkeypatch.setattr(versions, "OUTPUT_SCHEMA_VERSION", "5")
        old_walk = artifact_key(container)
        old_doc = document_key(container.container_hash(), limits=LIMITS)
        monkeypatch.setattr(versions, "OUTPUT_SCHEMA_VERSION", "6")
        assert old_walk != live_walk and old_doc != live_doc

    # Every measured value is byte-identical: part ids, sha256s, spans, caps and the ParseResult.
    for name, payload in committed["fixtures"].items():
        assert payload["parse_result"] == pre_bump["fixtures"][name]["parse_result"], name
        assert payload["caps"] == pre_bump["fixtures"][name]["caps"], name
        assert payload["span_samples"] == pre_bump["fixtures"][name]["span_samples"], name
        # ... and the freshly recomputed ones, so the pins are not decorative.
        container = EmlContainer(memory_bytes(_fixture_bytes(name)))
        assert payload["caps"] == [
            _encoded(cap) for cap in assemble(container, limits=LIMITS).run_record.caps
        ], name

    # The falsifier: a stray fourth difference fails the classification.
    stray = copy.deepcopy(committed)
    parts = stray["fixtures"][sorted(stray["fixtures"])[0]]["document"]["record"]["parts"]
    if parts:
        parts[0]["part_id"] = hashlib.sha256(b"a stray fourth move").hexdigest()
    else:
        stray["fixtures"][sorted(stray["fixtures"])[0]]["document"]["record"]["headers"][0][
            "raw_value"
        ] = "a stray fourth move"
    assert _classify(pre_bump, stray) == "not_permitted"


# --------------------------------------------------------------- the coverage and header


def test_the_golden_covers_every_committed_eml_fixture() -> None:
    """The golden's keys are exactly the ledger's corpus file list for the current version."""
    names = sorted(_load()["fixtures"])
    assert names, "the golden pins no fixture"
    corpus = behavior_ledger.discovered()
    assert corpus, "the corpus enumeration returned zero files"
    assert names == corpus, "a fixture was added or removed without re-recording the golden"
    corpora = behavior_ledger.load_corpora()
    manifest = next(entry["files"] for entry in corpora if entry["version"] == behavior_ledger.latest_corpus(corpora))
    assert names == sorted(manifest)


def test_the_golden_header_names_the_corpus_and_schema_version() -> None:
    """The header's corpus and schema versions are the live ones."""
    header = _load()["header"]
    assert header["corpus_version"] == behavior_ledger.latest_corpus(behavior_ledger.load_corpora())
    assert header["schema_version"] == versions.OUTPUT_SCHEMA_VERSION
    assert header["email_parser_version"] == versions.EMAIL_PARSER_VERSION
    assert header["golden_version"] == GOLDEN_VERSION
    assert header["fixture_count"] == len(_load()["fixtures"])
    assert header["limits"] == {name: getattr(LIMITS, name) for name in LIMITS.__dataclass_fields__}
    assert header["recorded_on"].startswith(platform.python_implementation())


# --------------------------------------------------------------- the identity guard


def test_resolve_span_samples_are_the_identity_guard() -> None:
    """The ``resolve_span`` samples are present, non-trivial and carry nonzero offsets."""
    fixtures = _load()["fixtures"]

    # A multi-part message whose parts resolve at a nonzero raw offset.
    resolved = [
        (name, part, sample)
        for name, payload in fixtures.items()
        if len(payload["document"]["record"]["parts"]) >= 2
        for part in payload["span_samples"]["parts"]
        for sample in part["samples"]
        if sample["answer"].get("kind") == "raw_span" and sample["answer"].get("offset", 0) > 0
    ]
    assert resolved, "no multi-part fixture resolves a part at a nonzero offset"

    # The four ranges are present for every part, and one resolved part's ranges differ
    # (the guard covers the start, the end and the middle, not only a prefix).
    for payload in fixtures.values():
        for part in payload["span_samples"]["parts"]:
            assert [sample["range"] for sample in part["samples"]] == [
                "own", "first", "last", "interior",
            ], part["part_id"]
    for name, part, _sample in resolved[:1]:
        offsets = {sample["answer"]["offset"] for sample in part["samples"]}
        assert len(offsets) > 1, (name, part["part_id"])

    # A fixture with a folded header: its top-level fields' own spans are pinned.
    folded = [
        name
        for name, payload in fixtures.items()
        if any("\n " in (field["raw_value"] or "") for field in payload["document"]["record"]["headers"])
    ]
    assert folded, "the corpus must carry a folded header"
    headers = fixtures[folded[0]]["span_samples"]["headers"]
    assert headers, folded[0]
    assert all(entry["name_span"] and entry["value_span"] for entry in headers), folded[0]
    assert any(entry["value_span"]["length"] > 0 for entry in headers), folded[0]

    # Not all answers are refusals: the guard really resolves.
    answers = [
        sample["answer"]["kind"]
        for payload in fixtures.values()
        for part in payload["span_samples"]["parts"]
        for sample in part["samples"]
    ]
    assert answers.count("raw_span") > 50, answers.count("raw_span")


# --------------------------------------------------------------- the label ledger


def test_the_golden_file_is_listed_in_the_label_ledger() -> None:
    """The committed golden is recorded, hashed, the way the other expected-value files are."""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    assert GOLDEN_REL in ledger["files"], f"{GOLDEN_REL} is not in the label ledger"
    digest = hashlib.sha256(_read_golden_bytes()).hexdigest()
    assert ledger["files"][GOLDEN_REL] == digest, "the recorded digest is not the committed file's"
