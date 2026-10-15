"""Turn 1b.10b: the hostile ``.msg`` run -- one inventory, the whole pipeline, one file.

Every hostile ``.msg`` input this phase knows is gathered here as an **inventory** and driven
through ``parse`` -> ``MsgContainer`` -> ``assemble`` -> ``store_document`` under
``Limits.untrusted()``: the whole committed ``.msg`` corpus (the well-formed fixtures and the three
hostile mutants), the test-built seeds the earlier turns typed (the size lies and the directory
self-loop, the recipient-count mismatch, the two hostile UTF-16 shapes and the attachment-no-data
shapes) and one mutant per ``(base, operator)`` of the seeded mutation operators the CFB and MAPI
fuzzes use.

The builders and operators are **imported, never copied** -- this file is an aggregation, and it
reduces no existing test. The outcome contract is the one those tests state: every input yields a
document or a named refusal, nothing raises, the caps hold, no published string fails UTF-8, and
the digest of the outcomes is identical under two ``PYTHONHASHSEED``\\ s.

**One FINDING**, pinned below and reported in ``docs/phase1b-report.md``:
``ingest_path`` cannot ingest a ``.msg`` at all (``ingest._container_for`` hands ``MsgContainer``
a material it refuses). The store step is exercised directly and the entry point's raise is pinned
so the finding cannot be lost or silently pass; ``ingest.py`` is not on this turn's allow-list, so
it is reported, not fixed.

``inventory()`` is the run itself; the report embeds the table it returns.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import make_msg_fixtures  # noqa: E402
import test_cfb  # noqa: E402
import test_cfb_fuzz as cfb_fuzz  # noqa: E402
import test_mapi_hostile as mapi_hostile  # noqa: E402
import test_msg_attachments as attachments  # noqa: E402
import test_msg_encodings as encodings  # noqa: E402

from emailextract import cfb, store  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.ingest import OUTCOMES, SKIP_REASONS, ingest_path  # noqa: E402
from emailextract.model import StatusOutcome  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402
from emailextract.parse import Limits, parse  # noqa: E402
from emailextract.walk import CAP_REASONS  # noqa: E402

MESSAGES = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()

#: How far the operator scan may go looking for each distinct operator per base.
OPERATOR_SCAN_CAP = 200

#: FINDING (Turn 1b.10b): ``ingest_path`` cannot ingest a ``.msg`` at all.
#:
#: ``ingest._container_for`` hands ``MsgContainer`` a ``MemoryMaterial`` while
#: ``MsgContainer.__init__`` takes ``bytes`` and raises ``TypeError`` for anything else, so the
#: first ``cfb_msg`` file in a directory aborts the whole ``ingest_path`` run. This substring is
#: the raise the test pins; the finding is reported in the outcome note and the report.
INGEST_MSG_DEFECT = "msgcontainer takes bytes"

#: The container kinds ``parse`` can decide on.
DECISIONS = ("rfc822", "cfb_msg")


def _recipient_mismatch_bytes() -> bytes:
    """The 1b.4 recipient-count mismatch, reused from the gap gate's seed builder."""
    import test_phase1b_gap_gate as gap_gate

    return gap_gate._recipient_count_mismatch()


def _each_operator(
    base: object, mutant: object, base_name: str, operators: tuple[str, ...]
) -> list[tuple[str, bytes]]:
    """One mutant per distinct operator: scan the fuzz's committed seeds until all are seen."""
    seen: dict[str, bytes] = {}
    for seed in range(OPERATOR_SCAN_CAP):
        operator, data = mutant(base, base_name, seed)  # type: ignore[operator]
        seen.setdefault(operator, data)
        if len(seen) == len(operators):
            break
    assert set(seen) == set(operators), sorted(set(operators) - set(seen))
    return sorted(seen.items())


def _cases() -> list[tuple[str, str, bytes]]:
    """Every hostile input as ``(class, name, bytes)``, in a fixed order.

    The classes:
    * ``committed`` -- every committed ``.msg`` fixture (hostile mutants included);
    * ``cfb_seed`` -- ``tests/test_cfb.py::_seeds`` (the three test-only seeds);
    * ``utf16`` -- ``tests/test_msg_encodings.py::_subject_only`` over the two hostile shapes;
    * ``recipient_mismatch`` -- the 1b.4 recipient-count mismatch;
    * ``attachment`` -- the attachment-no-data shapes (``test_msg_attachments``);
    * ``cfb_mutant`` / ``mapi_mutant`` -- one mutant per ``(base, operator)``.
    """
    cases: list[tuple[str, str, bytes]] = []
    for path in sorted(MESSAGES.glob("*.msg")):
        cases.append(("committed", path.stem, path.read_bytes()))
    for name, data in sorted(test_cfb._seeds().items()):
        cases.append(("cfb_seed", name, data))
    for label, payload in (("lone_surrogate", b"A\x00\x00\xd8"), ("odd_length", b"\x41\x00\x42")):
        cases.append(("utf16", label, encodings._subject_only(payload)))
    cases.append(("recipient_mismatch", "seed_recipient_count_mismatch", _recipient_mismatch_bytes()))
    ghost = attachments._message(
        attachments._attachment(0, method=1, long="ghost.bin", declared_data=5)
    )
    short = attachments._message(
        attachments._attachment(0, method=1, long="short.bin", data=b"0123456789")
    )
    cases.append(("attachment", "stream_absent", ghost))
    cases.append(
        (
            "attachment",
            "stream_out_of_range",
            attachments._patch_stream_size(short, attachments.BY_VALUE, 4096),
        )
    )
    for base_name in cfb_fuzz.BASES:
        base = make_msg_fixtures.build_fixture(base_name)
        for operator, data in _each_operator(base, cfb_fuzz.mutant, base_name, cfb_fuzz.OPERATORS):
            cases.append(("cfb_mutant", f"{base_name}_{operator}", data))
    for base_name, factory in mapi_hostile.BASES:
        for operator, data in _each_operator(
            factory(), mapi_hostile.mutant, base_name, mapi_hostile.OPERATORS
        ):
            cases.append(("mapi_mutant", f"{base_name}_{operator}", data))
    return cases


def _strings(document, container) -> list[str]:
    """Every string the pipeline published for one input, for the UTF-8 check."""
    strings = [field.raw_value for field in document.headers]
    strings.extend(
        value for value in container.container_facts().values() if isinstance(value, str)
    )
    strings.extend(
        fact.filename_raw for fact in container.attachment_facts if isinstance(fact.filename_raw, str)
    )
    return strings


def _ingest_state(root: Path) -> str:
    """The ingest entry point's state over a directory of ``.msg`` files, or the pinned FINDING."""
    try:
        ingest_path(root, store.document_store(root / "_ingest_store"), limits=LIMITS)
    except TypeError as defect:
        assert INGEST_MSG_DEFECT in str(defect), defect
        return f"raise:TypeError({INGEST_MSG_DEFECT})"
    raise AssertionError(
        "FINDING is stale: ingest_path ingested a .msg -- update tests/test_phase1b_hostile_run.py "
        "and docs/phase1b-report.md (the .msg half of the ingest path works now)"
    )


def inventory() -> dict[str, object]:
    """Run every hostile input through the pipeline; return the outcomes and the inventory table.

    Per input: ``parse`` -> ``MsgContainer`` -> ``assemble`` -> ``store_document`` (the store step
    the ingest path would take). A ``parse`` refusal short-circuits to a named refusal row. The
    ingest entry point's own raise is pinned once (:func:`_ingest_state`).
    """
    cases = _cases()
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as handle:
        root = Path(handle)
        for cls, name, data in cases:
            (root / f"{cls}__{name}.msg").write_bytes(data)
        ingest = _ingest_state(root)
        artifact_store = store.document_store(root / "_artifact_store")
        for cls, name, data in cases:
            rel = f"{cls}__{name}.msg"
            decision = parse(data, limits=LIMITS)
            if decision.error is not None:
                assert decision.error.reason_id, rel
                rows.append(
                    {
                        "class": cls,
                        "name": name,
                        "decision": f"refused:{decision.error.reason_id}",
                        "status": None,
                        "reason": decision.error.reason_id,
                        "ingest": ingest,
                        "store": "skipped",
                    }
                )
                continue
            assert decision.kind in DECISIONS, (rel, decision.kind)
            container = MsgContainer(data)
            document = assemble(container, limits=LIMITS)
            status = document.status
            assert isinstance(status, StatusOutcome), (rel, status)
            assert {cap.cap_id for cap in document.run_record.caps} <= set(CAP_REASONS), rel
            for value in _strings(document, container):
                value.encode("utf-8")
            assert len(data) <= LIMITS.max_input_bytes, rel
            cfb_file = container.cfb_file
            if isinstance(cfb_file, cfb.CfbFile):
                budget = mapi_hostile.budget_for(
                    len(data), cfb.sector_windows(len(data), cfb_file.sector_size)
                )
                assert cfb_file.steps <= budget, (rel, cfb_file.steps, budget)
            artifact, created = store.store_document(container, artifact_store, limits=LIMITS)
            assert artifact.container_hash == container.container_hash(), rel
            rows.append(
                {
                    "class": cls,
                    "name": name,
                    "decision": decision.kind,
                    "status": status.status.value,
                    "reason": status.reason,
                    "ingest": ingest,
                    # A mutant that wrote a word to the value it already held rebuilds the base's
                    # bytes exactly, so the store legitimately reports a hit rather than a write.
                    "store": "written" if created else "hit",
                }
            )
    by_class = Counter(row["class"] for row in rows)
    by_outcome = Counter(f"{row['decision']}/{row['status'] or '-'}" for row in rows)
    return {
        "rows": rows,
        "by_class": dict(by_class),
        "by_outcome": dict(by_outcome),
        "ingest": ingest,
    }


def digest() -> str:
    """A sha256 over every input's outcome: the digest the hash-seed runs compare."""
    payload = "\n".join(
        "|".join(
            str(row[key]) for key in ("class", "name", "decision", "status", "reason", "store")
        )
        for row in inventory()["rows"]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_every_hostile_msg_input_yields_a_document_or_a_named_refusal() -> None:
    """The whole inventory runs the pipeline: no input raises, every outcome is closed.

    The inventory is also the report's table, so this test asserts it is not vacuous: every class
    present, at least one named refusal, every status a known one, and the ingest FINDING pinned
    rather than assumed.
    """
    result = inventory()
    rows = result["rows"]
    assert len(rows) >= 60, len(rows)
    by_class = result["by_class"]
    for cls in ("committed", "cfb_seed", "utf16", "attachment", "recipient_mismatch", "cfb_mutant", "mapi_mutant"):
        assert by_class.get(cls), (cls, by_class)
    known = {"parsed", "skipped", "truncated", "failed", "unsupported"}
    for row in rows:
        if row["status"] is not None:
            assert row["status"] in known, row
            assert row["store"] in ("written", "hit"), row
        else:
            assert str(row["decision"]).startswith("refused:"), row
            assert row["store"] == "skipped", row
        assert row["ingest"] == result["ingest"], row
    refused = {row["decision"] for row in rows if str(row["decision"]).startswith("refused:")}
    assert refused, "the inventory must carry at least one named refusal"
    assert sum(result["by_outcome"].values()) == len(rows)
    assert INGEST_MSG_DEFECT in str(result["ingest"])


def test_the_hostile_inventory_is_stable_across_hash_seeds() -> None:
    """The outcomes do not depend on ``PYTHONHASHSEED``: same digest under two seeds."""
    baseline = digest()
    assert _hash_seed_run("0") == baseline
    assert _hash_seed_run("1234567") == baseline


def _hash_seed_run(seed: str) -> str:
    """``digest()`` in a subprocess with ``PYTHONHASHSEED=seed``."""
    script = (
        "import sys\n"
        "for path in (sys.argv[1], sys.argv[1] + '/tests', sys.argv[1] + '/tools'):\n"
        "    sys.path.insert(0, path)\n"
        "import test_phase1b_hostile_run as run\n"
        "print(run.digest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()
