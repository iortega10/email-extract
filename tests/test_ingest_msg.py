"""Turn 1b.10c: ``ingest_path`` ingests a ``.msg`` -- the entry point's own ``cfb_msg`` route.

Turn 1b.10b's hostile run found, and the reviewer reproduced, that directory ingest of **any**
``.msg`` raised: ``ingest._container_for`` handed ``MsgContainer`` a ``MemoryMaterial`` while
``MsgContainer.__init__`` takes ``bytes`` and raises ``TypeError``. No test ever ingested a ``.msg``
through ``ingest_path`` -- the only ``.msg`` case in ``tests/test_ingest.py`` is refused by ``parse``
*before* a container is built, and 1b.9/1b.10b ingested through ``store_document`` directly.

These tests drive the entry point itself, over a directory of real ``.msg`` bytes, and pin:

* every committed readable ``.msg`` (``fixtures/msg/*.msg``) writes a ``cfb_msg`` document whose
  ``container_hash`` is the file's ``sha256``, and the two fixtures ``parse`` refuses by design are a
  **recorded skip with their named reason** -- nothing raises;
* re-ingest of the same directory is a no-op (``hit`` rows, the store's bytes unchanged);
* a mixed ``.eml`` + ``.msg`` directory ingests both kinds and changes no ``.eml`` document's bytes;
* the ``.msg`` manifest and its documents are byte-identical across two hash seeds and two
  interpreters (the digest pattern ``tests/test_ingest.py`` uses);
* every hostile ``.msg`` input (the 1b.10b builders, imported not copied) through ``ingest_path`` is
  a document or a **named** skip, never an exception, under ``Limits.untrusted()``;
* an over-cap ``.msg`` is ``file_over_cap`` **before** any container is built.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import pytest  # noqa: E402

from emailextract import ids, store  # noqa: E402
from emailextract.assemble import document_key, identity_projection  # noqa: E402
from emailextract.ingest import (  # noqa: E402
    HIT,
    SKIP_REASONS,
    SKIPPED,
    WRITTEN,
    ingest_path,
    manifest_store,
    read_manifest,
)
from emailextract.model import ContainerKind  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from support import msg_construction  # noqa: E402

MESSAGES = ROOT / "fixtures" / "msg"

#: The two committed ``.msg`` fixtures ``parse`` refuses by design: a directory self-loop and a
#: well-formed CFB that carries no message. Both are recorded skips with a named reason.
REFUSED = {
    "msg_directory_loop.msg": "cfb_directory_loop",
    "msg_mini_cutoff_boundary.msg": "not_a_message",
}

MESSAGE = (
    b"From: Ada <ada@example.com>\r\n"
    b"To: Ben <ben@example.com>\r\n"
    b"Subject: one\r\n"
    b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
    b"Message-ID: <shared@example.com>\r\n"
    b"\r\n"
    b"Hello Ben.\r\n"
)


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


def _store(root: Path):
    return store.document_store(root / "store")


def _write(root: Path, name: str, payload: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _msg_files() -> dict[str, bytes]:
    """``{name: bytes}`` for every committed ``.msg`` fixture, in bytewise path order."""
    return {path.name: path.read_bytes() for path in sorted(MESSAGES.glob("*.msg"))}


def _document(collection, raw: bytes, *, limits: Limits):
    """The document the store holds for ``raw`` under ``limits`` (by its own hashed key)."""
    return store.read_document(collection, document_key(ids.sha256_hex(raw), limits=limits))


# --------------------------------------------------------------- the committed corpus


def test_ingest_path_ingests_every_committed_msg(tmp_path: Path) -> None:
    """Every readable ``.msg`` writes a ``cfb_msg`` document; the refused two are named skips.

    Nothing raises: before the fix the first ``cfb_msg`` file aborted the whole run with the
    ``TypeError`` this turn removes.
    """
    root = tmp_path / "mail"
    files = _msg_files()
    for name, payload in files.items():
        _write(root, name, payload)
    collection = _store(tmp_path)
    limits = _limits()
    manifest = ingest_path(root, collection, limits=limits)

    assert [row.path for row in manifest.rows] == sorted(files)
    reasons = {row.path: row.reason_id for row in manifest.rows}
    outcomes = {row.path: row.outcome for row in manifest.rows}
    written = [name for name in files if name not in REFUSED]
    for name in written:
        # A readable .msg is WRITTEN with the file's own hash (D14: the container is the file).
        assert outcomes[name] == WRITTEN, (name, outcomes[name])
        expected = hashlib.sha256(files[name]).hexdigest()
        assert ids.sha256_hex(files[name]) == expected
        assert reasons[name] is None
    for name, reason in REFUSED.items():
        assert outcomes[name] == SKIPPED, (name, outcomes[name])
        assert reasons[name] == reason, (name, reasons[name])
    for row in manifest.rows:
        if row.outcome == SKIPPED:
            assert row.reason_id in SKIP_REASONS and row.container_hash == ""
        else:
            assert row.container_hash == ids.sha256_hex(files[row.path])

    # One document per WRITTEN row, and each re-reads to the cfb_msg record its row named.
    assert len(collection.list()) == len(written)
    hashes = {row.container_hash for row in manifest.rows if row.container_hash}
    assert len(hashes) == len(written)
    for name in written:
        raw = files[name]
        document = _document(collection, raw, limits=limits)
        assert document is not None, name
        assert document.container_kind is ContainerKind.CFB_MSG, name
        assert document.container_hash == ids.sha256_hex(raw), name


def test_re_ingesting_a_msg_directory_is_a_no_op(tmp_path: Path) -> None:
    """A second ``ingest_path`` over the same ``.msg`` directory writes nothing at all."""
    root = tmp_path / "mail"
    for name, payload in _msg_files().items():
        _write(root, name, payload)
    collection = _store(tmp_path)
    limits = _limits()
    first = ingest_path(root, collection, limits=limits)
    documents_after_first = store.store_snapshot(tmp_path / "store" / "documents")
    assert documents_after_first  # a fresh store wrote the documents once
    second = ingest_path(root, collection, limits=limits)
    after = store.store_snapshot(tmp_path / "store" / "documents")

    assert [row.path for row in second.rows] == [row.path for row in first.rows]
    for before_row, after_row in zip(first.rows, second.rows):
        assert before_row.container_hash == after_row.container_hash
        assert before_row.reason_id == after_row.reason_id
    assert all(row.outcome != WRITTEN for row in second.rows)
    assert second.written == 0
    assert second.hits == first.written and second.skipped == first.skipped
    # Re-ingest writes no document (the README's promise); the manifest the first run stored is
    # unchanged and still the one this run returns by value (a re-ingest's own hit-row manifest is
    # a *different* record, which the store keeps beside the first).
    assert after == documents_after_first, "a re-ingest of unchanged .msg bytes rewrote a document"
    assert read_manifest(manifest_store(tmp_path / "store"), first) == first


def test_an_oversized_msg_is_skipped_before_a_container_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_row_for`` checks ``max_input_bytes`` first: an over-cap ``.msg`` never builds a container."""
    import emailextract.ingest as ingest_module

    root = tmp_path / "mail"
    big = _msg_files()["msg_difat_extended.msg"]
    _write(root, "big.msg", big)
    collection = _store(tmp_path)

    real = ingest_module._container_for
    assert callable(real)
    reached = {"count": 0}

    def counting(raw, kind):
        reached["count"] += 1
        return real(raw, kind)

    monkeypatch.setattr(ingest_module, "_container_for", counting)
    limits = _limits(max_input_bytes=max(1, len(big) - 1))
    manifest = ingest_path(root, collection, limits=limits)

    assert len(manifest.rows) == 1
    row = manifest.rows[0]
    assert (row.outcome, row.reason_id, row.container_hash) == (
        SKIPPED,
        ids.FILE_OVER_CAP,
        "",
    )
    assert reached["count"] == 0, "a container was built for an over-cap .msg"
    assert collection.list() == []


# --------------------------------------------------------------- mixed eml + msg


def test_a_mixed_eml_and_msg_directory_ingests_both(tmp_path: Path) -> None:
    """Both container kinds ingest; the ``.eml`` documents' bytes are unchanged by the ``.msg`` half."""
    eml = {
        "plain.eml": MESSAGE,
        "pair.eml": msg_construction.pair_eml_bytes(),
    }
    msg = {
        "pair.msg": (MESSAGES / "pair_gmail_reply.msg").read_bytes(),
        "plain.msg": (MESSAGES / "msg_plain_only.msg").read_bytes(),
    }
    limits = _limits()

    # The ``.eml`` files ingested alone, for the byte-identity comparison.
    alone_root = tmp_path / "alone"
    for name, payload in eml.items():
        _write(alone_root, name, payload)
    alone = _store(tmp_path / "alone_store")
    ingest_path(alone_root, alone, limits=limits)

    root = tmp_path / "mail"
    for name, payload in {**eml, **msg}.items():
        _write(root, name, payload)
    mixed = _store(tmp_path / "mixed_store")
    manifest = ingest_path(root, mixed, limits=limits)

    # The mixed manifest is ordered deterministically (bytewise over the relative path).
    assert [row.path for row in manifest.rows] == sorted([*eml, *msg])

    kinds = {}
    for name, payload in {**eml, **msg}.items():
        document = _document(mixed, payload, limits=limits)
        assert document is not None, name
        kinds[name] = document.container_kind
    for name in eml:
        assert kinds[name] is ContainerKind.RFC822, name
    for name in msg:
        assert kinds[name] is ContainerKind.CFB_MSG, name

    # An ``.eml`` document's bytes are identical whether or not a ``.msg`` sits beside it.
    for name, payload in eml.items():
        alone_doc = _document(alone, payload, limits=limits)
        mixed_doc = _document(mixed, payload, limits=limits)
        assert alone_doc is not None and mixed_doc is not None, name
        assert identity_projection(alone_doc) == identity_projection(mixed_doc), name


# --------------------------------------------------------------- determinism


#: A self-contained program (no pytest, no test import) that ingests the committed ``.msg`` corpus
#: into two fresh stores, re-ingests one of them, and prints the manifest-plus-store digest. Run
#: under two hash seeds and both interpreters; its digest is a constant in this file.
DIGEST_SCRIPT = r'''
import hashlib, sys, tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, sys.argv[2])  # the parent's own docextract_core: never a sibling checkout
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from docextract_core.codec import to_json
from emailextract.assemble import identity_projection
from emailextract.ingest import ingest_path, manifest_store, read_manifest
from emailextract.parse import Limits
from emailextract.store import document_store, store_snapshot
from emailextract import ids

LIMITS = Limits(
    max_input_bytes=64 * 1024 * 1024,
    max_depth=16,
    max_parts=1000,
    max_header_bytes=262144,
    max_decoded_part_bytes=33554432,
    max_decoded_total_bytes=134217728,
    max_field_work_units_per_byte=64,
)

work = Path(tempfile.mkdtemp())
mail = work / "mail"
mail.mkdir()
for path in sorted((ROOT / "fixtures" / "msg").glob("*.msg")):
    (mail / path.name).write_bytes(path.read_bytes())


def run(store_root):
    collection = document_store(store_root)
    first = ingest_path(mail, collection, limits=LIMITS)
    parts = [to_json(first)]
    # Sorted by CONTENT, never by store id: the id is the document key, whose bytes carry
    # HTMLTEXT_VERSION, stamping the CPython minor, so the ids legitimately differ between minors
    # while every identity projection is byte-identical.
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


#: The digest the script prints -- identical on both interpreters and both hash seeds. Recorded
#: from a CPython 3.14.3 run and required of every other interpreter (Turn 1b.10c).
EXPECTED_DIGEST = "e3e431c3bcc770a30d22927467a0087cc39cf36e865028a613c523b9bc868311"


def _second_interpreter() -> list[str] | None:
    sys.path.insert(0, str(ROOT / "tools"))
    import runboth

    found = runboth.find_python311()
    return None if found is None else list(found[0])


import docextract_core  # noqa: E402

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
        timeout=600,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return dict(line.split(" ", 1) for line in completed.stdout.splitlines() if " " in line)


def test_the_msg_manifest_is_byte_identical_across_seeds_and_interpreters() -> None:
    """Two runs, two hash seeds and two interpreters agree with the recorded ``.msg`` digest."""
    current = [sys.executable]
    seed0 = _run_digest_script(current, "0")
    seed1 = _run_digest_script(current, "1")
    assert seed0["stores_identical"] == seed1["stores_identical"] == "True"
    assert seed0["reingest_identical"] == seed1["reingest_identical"] == "True"
    assert seed0["rows"] == seed1["rows"] == str(len(_msg_files()))
    assert seed0["digest"] == seed1["digest"] == EXPECTED_DIGEST, (seed0, seed1)

    second = _second_interpreter()
    if second is None:
        pytest.skip("no CPython 3.11 found: the cross-interpreter run is skipped, not faked")
    theirs = _run_digest_script(second, "0")
    assert theirs["digest"] == EXPECTED_DIGEST, (
        f"the .msg digest differs between {seed0['interpreter']} and "
        f"{theirs['interpreter']}: {EXPECTED_DIGEST} vs {theirs['digest']}"
    )


# --------------------------------------------------------------- the hostile corpus


def test_a_hostile_msg_directory_yields_documents_or_named_skips(tmp_path: Path) -> None:
    """Every hostile ``.msg`` input through ``ingest_path`` is a document or a named skip.

    The builders are the 1b.10b hostile run's own (imported, never copied), written into a temp
    directory so the entry point -- not ``store_document`` -- sees them.
    """
    import test_phase1b_hostile_run as hostile

    root = tmp_path / "hostile"
    cases = hostile._cases()
    assert len(cases) >= 60, len(cases)
    for cls, name, data in cases:
        _write(root, f"{cls}__{name}.msg", data)
    collection = _store(tmp_path)
    manifest = ingest_path(root, collection, limits=Limits.untrusted())

    assert len(manifest.rows) == len(cases)
    for row in manifest.rows:
        if row.outcome == SKIPPED:
            assert row.reason_id in SKIP_REASONS, row
            assert row.container_hash == "", row
        else:
            assert row.outcome in (WRITTEN, HIT), row
            assert row.container_hash, row
