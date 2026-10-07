"""Turn 1.9: ``ingest_path`` -- paths, order, symlinks, outcomes and the manifest.

The rules under test are the six policies in ``emailextract/ingest.py``: directory
order is UTF-8 bytewise over the POSIX-normalised relative path; a symlinked
directory is never recursed and a symlinked file is read as its target; an
unreadable or over-cap file is a recorded outcome and the run continues; re-ingest
of unchanged bytes is a no-op; the same bytes under two paths are **one document and
two manifest rows**; and the same Message-ID with different bytes is **not merged**
and records nothing about the relation.

The determinism test runs one self-contained program under two ``PYTHONHASHSEED``
values and under the second pinned interpreter, and compares its digest against the
constant recorded in ``docs/design/phase1-empirical.md``.
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import subprocess
import sys
from pathlib import Path

import docextract_core
import pytest
from docextract_core import Collection

from emailextract import ids, store
from emailextract.ingest import (
    HIT,
    SKIP_REASONS,
    SKIPPED,
    WRITTEN,
    ManifestRow,
    ingest_path,
    manifest_store,
    read_manifest,
)
from emailextract.model import Status, TriState
from emailextract.parse import Limits

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

ingest_module = importlib.import_module("emailextract.ingest")
store_module = importlib.import_module("emailextract.store")

MESSAGE = (
    b"From: Ada <ada@example.com>\r\n"
    b"To: Ben <ben@example.com>\r\n"
    b"Subject: one\r\n"
    b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
    b"Message-ID: <shared@example.com>\r\n"
    b"\r\n"
    b"Hello Ben.\r\n"
)

OTHER = MESSAGE.replace(b"Hello Ben.", b"A different body entirely.")


def _limits(**overrides: int) -> Limits:
    base = dict(
        max_input_bytes=64 * 1024 * 1024,
        max_depth=16,
        max_parts=1000,
        max_header_bytes=256 * 1024,
        max_decoded_part_bytes=32 * 1024 * 1024,
        max_decoded_total_bytes=128 * 1024 * 1024,
        max_field_work_units_per_byte=64,
    )
    base.update(overrides)
    return Limits(**base)


def _store(tmp_path: Path) -> Collection:
    return store.document_store(tmp_path / "store")


def _write(root: Path, name: str, payload: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _documents(collection: Collection) -> list[str]:
    return sorted(collection.list())


# --------------------------------------------------------------- order and outcome


def test_ingest_of_a_directory_is_sorted_and_deterministic(tmp_path: Path) -> None:
    """A directory ingest returns rows in bytewise path order, and twice the same."""
    root = tmp_path / "mail"
    _write(root, "b.eml", MESSAGE)
    _write(root, "a.eml", OTHER)
    _write(root, "nested/c.eml", MESSAGE)
    collection = _store(tmp_path)
    limits = _limits()
    first = ingest_path(root, collection, limits=limits)
    assert [row.path for row in first.rows] == ["a.eml", "b.eml", "nested/c.eml"]
    # ``b.eml`` and ``nested/c.eml`` carry the same bytes: the second is a hit, not a
    # second document (policy 5 -- a path is never identity).
    assert [row.outcome for row in first.rows] == [WRITTEN, WRITTEN, HIT]
    assert all(row.reason_id is None for row in first.rows)
    # A second run over the same tree is the same rows, and writes no document at all.
    documents_before = store.store_snapshot(tmp_path / "store" / "documents")
    second = ingest_path(root, collection, limits=limits)
    assert [row.path for row in second.rows] == [row.path for row in first.rows]
    assert [row.outcome for row in second.rows] == [HIT, HIT, HIT]
    assert [row.container_hash for row in second.rows] == [
        row.container_hash for row in first.rows
    ]
    assert second.written == 0
    assert store.store_snapshot(tmp_path / "store" / "documents") == documents_before
    assert len(_documents(collection)) == 2  # two distinct byte strings, three paths
    # The manifest is itself a stored, codec-encoded record.
    stored = read_manifest(manifest_store(tmp_path / "store"), first)
    assert stored == first


def test_the_sort_order_is_bytewise_including_a_non_ascii_name(tmp_path: Path) -> None:
    """``A.eml`` sorts before ``a.eml``, and a non-ASCII name sorts by its bytes."""
    root = tmp_path / "mail"
    _write(root, "a.eml", MESSAGE)
    _write(root, "ünïcode.eml", MESSAGE)
    collection = _store(tmp_path)

    def listing(_root: Path) -> list[str]:
        return ["a.eml", "A.eml", "ünïcode.eml"]

    manifest = ingest_path(root, collection, limits=_limits(), listing=listing)
    # The seam drives the order, so the case-differing pair needs no such files on disk
    # (they cannot coexist on Windows): ``A`` (0x41) sorts before ``a`` (0x61), and a
    # non-ASCII name sorts by its UTF-8 bytes, after both ASCII names.
    assert [row.path for row in manifest.rows] == ["A.eml", "a.eml", "ünïcode.eml"]
    assert "ünïcode.eml".encode("utf-8") > b"a.eml"
    # On a case-insensitive filesystem both names resolve to the one file, so the rows
    # show one document written and the other a hit -- and on a case-sensitive one the
    # missing name is a recorded skip; either way the order is what the seam said.
    assert manifest.rows[0].outcome in (WRITTEN, SKIPPED)
    assert manifest.rows[0].path < manifest.rows[1].path


def test_the_same_bytes_under_two_paths_are_one_document_and_two_rows(tmp_path: Path) -> None:
    """A path never enters the document: one document, two manifest rows (policy 5)."""
    root = tmp_path / "mail"
    _write(root, "one.eml", MESSAGE)
    _write(root, "two.eml", MESSAGE)
    collection = _store(tmp_path)
    manifest = ingest_path(root, collection, limits=_limits())
    assert [row.path for row in manifest.rows] == ["one.eml", "two.eml"]
    assert {row.container_hash for row in manifest.rows} == {ids.container_hash(MESSAGE)}
    assert [row.outcome for row in manifest.rows] == [WRITTEN, HIT]
    assert len(_documents(collection)) == 1


def test_re_ingest_of_unchanged_bytes_is_a_no_op(tmp_path: Path) -> None:
    """Re-ingesting the same bytes writes no document: every row is a hit."""
    root = tmp_path / "mail"
    _write(root, "one.eml", MESSAGE)
    collection = _store(tmp_path)
    limits = _limits()
    ingest_path(root, collection, limits=limits)
    before = store.store_snapshot(tmp_path / "store" / "documents")
    second = ingest_path(root, collection, limits=limits)
    after = store.store_snapshot(tmp_path / "store" / "documents")
    assert all(row.outcome == HIT for row in second.rows)
    assert before == after, "a re-ingest of unchanged bytes wrote a document"
    assert second.written == 0 and second.hits == 1 and second.skipped == 0
    # The same bytes through a different path are still the one document.
    _write(root, "copy.eml", MESSAGE)
    third = ingest_path(root, collection, limits=limits)
    assert [row.outcome for row in third.rows] == [HIT, HIT]
    assert store.store_snapshot(tmp_path / "store" / "documents") == before


def test_an_unreadable_file_and_an_over_cap_file_are_recorded_and_the_run_continues(
    tmp_path: Path,
) -> None:
    """A vanished path is ``file_unreadable``; an over-cap file is ``file_over_cap``."""
    root = tmp_path / "mail"
    _write(root, "good.eml", MESSAGE)
    _write(root, "huge.eml", MESSAGE + b"x" * 4096)
    collection = _store(tmp_path)
    # A listing seam names a file that does not exist: the read is what fails, which is
    # the policy under test (and is OS-independent, unlike a permission bit on Windows).
    def listing(_root: Path) -> list[str]:
        return ["good.eml", "huge.eml", "gone.eml"]

    manifest = ingest_path(
        root, collection, limits=_limits(max_input_bytes=1024), listing=listing
    )
    outcomes = {row.path: (row.outcome, row.reason_id) for row in manifest.rows}
    assert outcomes["huge.eml"] == (SKIPPED, ids.FILE_OVER_CAP)
    assert outcomes["gone.eml"] == (SKIPPED, ids.FILE_UNREADABLE)
    assert outcomes["good.eml"][0] == WRITTEN
    for row in manifest.rows:
        if row.outcome == SKIPPED:
            assert row.reason_id in SKIP_REASONS
            assert row.container_hash == ""
    # The run continued: the good file is stored.
    assert len(_documents(collection)) == 1


def test_a_non_message_file_is_a_recorded_skip_from_the_entry_point(tmp_path: Path) -> None:
    """A file the entry point refuses is a recorded skip with its closed named reason."""
    root = tmp_path / "mail"
    _write(root, "note.txt", b"just text, no header line at all\n")
    _write(root, "cfb.msg", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40)
    collection = _store(tmp_path)
    manifest = ingest_path(root, collection, limits=_limits())
    reasons = {row.path: row.reason_id for row in manifest.rows}
    assert reasons["note.txt"] == "not_a_message"
    assert reasons["cfb.msg"] == "cfb_msg_unsupported"
    assert _documents(collection) == []


def test_a_symlinked_directory_is_skipped_and_a_symlinked_file_is_read(tmp_path: Path) -> None:
    """No symlinked directory is recursed; a symlinked file is read as its target."""
    root = tmp_path / "mail"
    _write(root, "real.eml", MESSAGE)
    (root / "target").mkdir()
    _write(root, "target/inside.eml", OTHER)
    try:
        os.symlink(root / "target", root / "linkdir", target_is_directory=True)
        os.symlink(root / "real.eml", root / "linkfile.eml")
    except (OSError, NotImplementedError) as error:  # pragma: no cover - environment
        pytest.skip(f"this OS refuses to create a symlink: {error}")
    collection = _store(tmp_path)
    manifest = ingest_path(root, collection, limits=_limits())
    rows = {row.path: row for row in manifest.rows}
    assert rows["linkdir"].outcome == SKIPPED
    assert rows["linkdir"].reason_id == ids.SYMLINKED_DIRECTORY
    # The symlinked file is read as its target: same container hash, same one document.
    assert rows["linkfile.eml"].outcome in (WRITTEN, HIT)
    assert rows["linkfile.eml"].container_hash == ids.container_hash(MESSAGE)
    # The symlinked directory was not descended: its contents are not rows.
    assert "linkdir/inside.eml" not in rows
    assert "target/inside.eml" in rows


# --------------------------------------------------------------- no merge


def test_the_same_message_id_with_different_bytes_is_not_merged(tmp_path: Path) -> None:
    """Equal Message-ID, different bytes: both stored, neither merged, nothing recorded."""
    # That sentence is the module docstring's policy 6: "not merged" must never be read
    # as "recorded" -- ``same_message_candidates`` stays not built.
    assert "not merged" in ingest_module.__doc__
    assert "same_message_candidates" in ingest_module.__doc__
    root = tmp_path / "mail"
    _write(root, "one.eml", MESSAGE)
    _write(root, "two.eml", OTHER)
    collection = _store(tmp_path)
    manifest = ingest_path(root, collection, limits=_limits())
    hashes = {row.container_hash for row in manifest.rows}
    assert len(hashes) == 2, "both documents are stored"
    assert [row.outcome for row in manifest.rows] == [WRITTEN, WRITTEN]
    assert len(_documents(collection)) == 2
    # Nothing about the relation is recorded: the manifest has no relation column, and
    # neither document's ``same_message_candidates`` axis is built.
    assert {field.name for field in dataclasses.fields(ManifestRow)} == {
        "path",
        "container_hash",
        "outcome",
        "reason_id",
    }
    for record_id in _documents(collection):
        document = collection.load(record_id).document
        assert document.same_message_candidates == []
        assert document.same_message_candidates_axis.state is TriState.UNKNOWN
        assert document.same_message_candidates_axis.reason_id == ids.NOT_BUILT_IN_PHASE1
        assert document.status.status is Status.PARSED


# --------------------------------------------------------------- the manifest shape


def test_a_manifest_row_refuses_an_impossible_outcome() -> None:
    """A skipped row carries a closed reason and no hash; the other outcomes carry one."""
    with pytest.raises(ValueError):
        ManifestRow(path="a.eml", container_hash="", outcome=WRITTEN)
    with pytest.raises(ValueError):
        ManifestRow(path="a.eml", container_hash="a" * 64, outcome=SKIPPED, reason_id="who")
    with pytest.raises(ValueError):
        ManifestRow(path="a.eml", container_hash="a" * 64, outcome=HIT, reason_id="who")
    with pytest.raises(ValueError):
        ManifestRow(path="/abs/a.eml", container_hash="a" * 64, outcome=WRITTEN)
    with pytest.raises(ValueError):
        ManifestRow(path="a\\b.eml", container_hash="a" * 64, outcome=WRITTEN)
    with pytest.raises(ValueError):
        ManifestRow(path="a.eml", container_hash="a" * 64, outcome="merged")


# --------------------------------------------------------------- mutations


def test_a_path_leaking_into_a_document_key_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutation: mix the source path into the key; two identical files stop being one.

    The ingested container is content-addressed, so the path never reaches the key on
    its own. The harness therefore tags each in-memory material with the path it was
    read from (which is what a ``PathMaterial`` carries anyway) and mixes that path's
    name into the key -- the leak a "key by path" bug would be.

    The anti-vacuity triple: (a) the patched symbols exist, (b) the patch is reached
    (the counter), (c) the observation differs -- the clean run stores **one** document
    for the same bytes under two paths, the mutated run stores two.
    """
    root = tmp_path / "mail"
    _write(root, "one.eml", MESSAGE)
    _write(root, "two.eml", MESSAGE)

    clean = _store(tmp_path / "clean")
    ingest_path(root, clean, limits=_limits())
    assert len(_documents(clean)) == 1  # the unmutated observation

    real_artifact = store_module.document_artifact
    real_memory_bytes = ingest_module.memory_bytes
    assert callable(real_artifact) and callable(real_memory_bytes)
    reached = {"count": 0}
    origins = iter(["one.eml", "two.eml"])

    def tagged_memory_bytes(data: bytes):
        material = real_memory_bytes(data)
        material.path = next(origins, None)
        return material

    def leaky_store_document(container, docstore, *, limits):
        reached["count"] += 1
        artifact = real_artifact(container, limits=limits)
        origin = getattr(getattr(container, "_material", None), "path", None)
        if origin is None:
            return artifact, docstore.save(artifact)[1]
        leaked = dataclasses.replace(artifact, key=f"{artifact.key}-{origin}")
        _saved, created = docstore.save(leaked)
        return leaked, created

    mutated = _store(tmp_path / "mutated")
    monkeypatch.setattr(ingest_module, "memory_bytes", tagged_memory_bytes)
    monkeypatch.setattr(ingest_module, "store_document", leaky_store_document)
    manifest = ingest_path(root, mutated, limits=_limits())
    assert reached["count"] > 0, "the mutation's patch was never entered (vacuous)"
    assert len(_documents(mutated)) == 2, "the leaked key stopped de-duplicating"
    assert len({row.container_hash for row in manifest.rows}) == 1
    assert [row.outcome for row in manifest.rows] == [WRITTEN, WRITTEN]


def test_an_unsorted_manifest_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: drop the bytewise sort; the manifest refuses to exist unsorted."""
    root = tmp_path / "mail"
    _write(root, "b.eml", MESSAGE)
    _write(root, "a.eml", OTHER)
    collection = _store(tmp_path)
    real = ingest_module._entries
    assert callable(real)
    reached = {"count": 0}

    def unsorted(root_path, listing):
        reached["count"] += 1
        return list(reversed(real(root_path, listing)))

    monkeypatch.setattr(ingest_module, "_entries", unsorted)
    with pytest.raises(ValueError):
        ingest_path(root, collection, limits=_limits())
    assert reached["count"] > 0, "the mutation's patch was never entered (vacuous)"


def test_an_unsorted_manifest_is_sorted_in_the_unmutated_run(tmp_path: Path) -> None:
    """The control for the mutation above: the sort is real, not assumed."""
    root = tmp_path / "mail"
    _write(root, "b.eml", MESSAGE)
    _write(root, "a.eml", OTHER)
    manifest = ingest_path(root, _store(tmp_path), limits=_limits())
    assert [row.path for row in manifest.rows] == ["a.eml", "b.eml"]


def test_a_same_message_id_merge_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: reuse the first document for the second file; the rows lose a writer."""
    root = tmp_path / "mail"
    _write(root, "one.eml", MESSAGE)
    _write(root, "two.eml", OTHER)

    clean = _store(tmp_path / "clean")
    clean_manifest = ingest_path(root, clean, limits=_limits())
    assert len({row.container_hash for row in clean_manifest.rows}) == 2
    assert [row.outcome for row in clean_manifest.rows] == [WRITTEN, WRITTEN]

    real = store_module.store_document
    assert callable(real)
    reached = {"count": 0}
    seen: list = []

    def merging(container, store, *, limits):
        reached["count"] += 1
        if seen:
            return seen[0], False
        artifact, created = real(container, store, limits=limits)
        seen.append(artifact)
        return artifact, created

    mutated = _store(tmp_path / "mutated")
    monkeypatch.setattr(ingest_module, "store_document", merging)
    manifest = ingest_path(root, mutated, limits=_limits())
    assert reached["count"] > 1, "the mutation's patch was never entered (vacuous)"
    assert len({row.container_hash for row in manifest.rows}) == 1, "the two files merged"
    assert len(_documents(mutated)) == 1
    assert [row.outcome for row in manifest.rows] == [WRITTEN, HIT]


# --------------------------------------------------------------- determinism


#: A self-contained program (no pytest, no test import) that ingests a fixed tree into
#: two fresh stores, re-ingests one of them, and prints the manifest-plus-store digest.
#: Run under two hash seeds and both interpreters; its digest is the constant recorded
#: in the empirical doc.
DIGEST_SCRIPT = r'''
import hashlib, sys, tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, sys.argv[2])  # the parent's own docextract_core: never a sibling checkout

from docextract_core.codec import to_json
from emailextract.assemble import identity_projection
from emailextract.ingest import ingest_path, manifest_store, read_manifest
from emailextract.parse import Limits
from emailextract.store import document_store, store_snapshot

MESSAGE = (
    b"From: Ada <ada@example.com>\r\n"
    b"To: Ben <ben@example.com>\r\n"
    b"Subject: one\r\n"
    b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
    b"Message-ID: <shared@example.com>\r\n"
    b"\r\n"
    b"Hello Ben.\r\n"
)
OTHER = MESSAGE.replace(b"Hello Ben.", b"A different body entirely.")
LIMITS = Limits(
    max_input_bytes=1024,
    max_depth=16,
    max_parts=1000,
    max_header_bytes=262144,
    max_decoded_part_bytes=1024,
    max_decoded_total_bytes=4096,
    max_field_work_units_per_byte=64,
)

work = Path(tempfile.mkdtemp())
mail = work / "mail"
mail.mkdir()
(mail / "b.eml").write_bytes(MESSAGE)
(mail / "a.eml").write_bytes(OTHER)
(mail / "\u00fcn\u00efcode.eml").write_bytes(MESSAGE)
(mail / "note.txt").write_bytes(b"just text, no header line at all\n")


def run(store_root):
    collection = document_store(store_root)
    first = ingest_path(mail, collection, limits=LIMITS)
    parts = [to_json(first)]
    # Sorted by CONTENT, never by store id: the id is the document key, and the key carries
    # HTMLTEXT_VERSION, which stamps the CPython minor, so the ids (and their order) legitimately
    # differ between minors while every identity projection is byte-identical.
    documents = [
        to_json(identity_projection(collection.load(record_id).document))
        for record_id in collection.list()
    ]
    parts.extend(sorted(documents))
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return first, collection, digest


first, collection, digest = run(work / "one")
_second, _collection, other = run(work / "two")
stored = read_manifest(manifest_store(work / "one"), first)
before = store_snapshot(work / "one" / "documents")
again = ingest_path(mail, collection, limits=LIMITS)
after = store_snapshot(work / "one" / "documents")
print("digest", digest)
print("rows", len(first.rows))
print("stores_identical", digest == other)
print("reingest_identical", before == after and stored == first and
      all(row.outcome != "written" for row in again.rows))
print("interpreter", "%d.%d.%d" % sys.version_info[:3])
'''


#: The digest the script prints, recorded (with its command) in
#: ``docs/design/phase1-empirical.md`` -- the same on both interpreters and both
#: hash seeds.
EXPECTED_DIGEST = "76bea6e31264fb4b52c9a52ad9b6a8838d6bd1d0a15ae7e0e1e293fb93468c1d"


def _second_interpreter() -> list[str] | None:
    sys.path.insert(0, str(ROOT / "tools"))
    import runboth

    found = runboth.find_python311()
    return None if found is None else list(found[0])


#: Where the running interpreter found docextract_core (pure Python), handed to the child so a
#: fresh clone needs no sibling checkout beside it.
_CORE_PATH = str(Path(docextract_core.__file__).resolve().parent.parent)


def _run_digest_script(prefix: list[str], seed: str) -> dict[str, str]:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    completed = subprocess.run(
        [*prefix, "-c", DIGEST_SCRIPT, str(ROOT), _CORE_PATH],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return dict(
        line.split(" ", 1) for line in completed.stdout.splitlines() if " " in line
    )


def test_the_manifest_and_the_store_are_byte_identical_across_seeds_and_interpreters() -> None:
    """Two runs, two hash seeds and two interpreters agree with the recorded digest."""
    current = [sys.executable]
    seed0 = _run_digest_script(current, "0")
    seed1 = _run_digest_script(current, "1")
    assert seed0["stores_identical"] == seed1["stores_identical"] == "True"
    assert seed0["reingest_identical"] == seed1["reingest_identical"] == "True"
    assert seed0["rows"] == seed1["rows"] == "4"
    assert seed0["digest"] == seed1["digest"] == EXPECTED_DIGEST, (seed0, seed1)

    second = _second_interpreter()
    if second is None:
        pytest.skip("no CPython 3.11 found: the cross-interpreter run is skipped, not faked")
    theirs = _run_digest_script(second, "0")
    assert theirs["digest"] == EXPECTED_DIGEST, (
        f"the identity projection digest differs between {seed0['interpreter']} and "
        f"{theirs['interpreter']}: {EXPECTED_DIGEST} vs {theirs['digest']}"
    )
    assert theirs["stores_identical"] == "True" and theirs["reingest_identical"] == "True"
