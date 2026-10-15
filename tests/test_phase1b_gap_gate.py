"""Turn 1b.10b: the Phase 1b gap gate, and the mutation catalogue that proves it can fail.

``docs/design/phase0-gaps.md`` registers eleven ``msg.*`` ids and the one
``headers.mapi_header_property_disagree`` the ``.msg`` reader owns; this module is the gate's
evidence for them, a layer over ``tests/test_phase1_gap_gate.py`` rather than a second copy of it:

* every one of the twelve has a working mutation case -- the eleven a committed ``.msg`` fixture
  labels at a live phase-1 row are the phase-1 catalogue's (``falsify.PHASE1_CASES`` for the ten
  message ids and the header/property disagreement), and the last
  (``msg.recipient_table_unreadable``) is the registry's own hostile seed
  ``seed_recipient_count_mismatch`` (``phase0-gaps.md:943``), built here from the 1b.4
  recipient-count-mismatch shape because no committed fixture carries it;
* the id set is **read off** the registry document and ``LIVE_GAP_IDS``, never hand-listed;
* dropping one emission makes the phase-1 gate fail, naming the gap id and the fixture or seed.

The temporary corpora are built under ``tmp_path``; nothing here shares a file between processes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from support import mapi_table  # noqa: E402
from support.sidecar_copy import payload_of, write  # noqa: E402

from emailextract.evals import gap_gate  # noqa: E402
from emailextract.evals.falsify import (  # noqa: E402
    PHASE1_CASES,
    UNEXERCISED_GAP_IDS,
    GapCase,
    drop_everywhere,
    mutated,
)
from emailextract.evals.l1 import LIVE_GAP_IDS  # noqa: E402
from emailextract.evals.labels import DEFAULT_FIXTURES  # noqa: E402
from test_phase0_gaps import documented_ids, registry_ids  # noqa: E402

FIXTURES = DEFAULT_FIXTURES
MESSAGES = ROOT / "fixtures" / "msg"
SUMS = MESSAGES / "SHA256SUMS"

#: The one non-``msg.*`` id the reader owns: its message-level header/property rule.
MAPI_DISAGREE = "headers.mapi_header_property_disagree"

#: The reader's registered ids, read off ``docs/design/phase0-gaps.md`` (never hand-listed).
REGISTRY_MSG_IDS: frozenset[str] = frozenset(
    gap_id for gap_id in documented_ids() if gap_id.startswith("msg.")
) | {MAPI_DISAGREE}

#: The reader's live ids, read off the oracle's own live set.
LIVE_MSG_IDS: frozenset[str] = frozenset(
    gap_id for gap_id in LIVE_GAP_IDS if gap_id.startswith("msg.")
) | {MAPI_DISAGREE}

#: The twelfth id: no committed fixture labels it at a live row, so it is closed with a seed.
SEED_ID = "msg.recipient_table_unreadable"
#: The registry's fixture for it and the seed's own stem (``phase0-gaps.md:943``).
SEED_FIXTURE_STEM = "msg_recipients_display_only"
SEED_STEM = "seed_recipient_count_mismatch"
SEED_FIXTURE = f"{SEED_STEM}.msg"

_IPM_NOTE = mapi_table.utf16("IPM.Note")


def _recipient_count_mismatch() -> bytes:
    """The 1b.4 recipient-count mismatch as a ``.msg`` byte string (the registry's seed).

    One ``__recip_version1.0_#00000000`` row whose table declares the recipient kind, and a
    top-level header declaring **two** recipients: ``mapi.read_message`` trusts the directory,
    records ``declared=2 rows=1`` and raises ``msg.recipient_table_unreadable``.
    """
    row = storage(
        "__recip_version1.0_#00000000",
        stream(
            "__properties_version1.0",
            mapi_table.sub_table([mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 1)]),
        ),
    )
    table = mapi_table.message_table(
        [
            mapi_table.variable_entry(
                mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE, len(_IPM_NOTE)
            )
        ],
        recipients=2,
        codepages=(1252, 1252),
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(
                mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE),
                _IPM_NOTE,
            ),
            row,
        )
    )


#: The seed's mutation case: the same one-gap drop the committed cases use.
SEED_CASE = GapCase(
    gap_id=SEED_ID,
    fact_id="gaps.later",
    naive=(
        "took the declared recipient count as the truth instead of trusting the directory, "
        "recording no msg.recipient_table_unreadable row"
    ),
    patch=drop_everywhere(SEED_ID),
    fixture=SEED_STEM,
)

#: gap id -> its case: the twelve the phase-1 catalogue already holds, plus the seed.
CASES: dict[str, GapCase] = {
    **{
        gap_id: PHASE1_CASES[gap_id]
        for gap_id in sorted(REGISTRY_MSG_IDS)
        if gap_id in PHASE1_CASES
    },
    SEED_ID: SEED_CASE,
}


def _committed(directory: Path, stem: str) -> None:
    """A corpus of just the committed fixture ``stem`` (its bytes and its sidecar)."""
    source = next(FIXTURES.rglob(f"{stem}.expected.json"))
    write(directory, payload_of(source), source=source)


def _seed(directory: Path) -> None:
    """A corpus of just the seed: the bytes built in this test and a hand-typed sidecar."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SEED_FIXTURE).write_bytes(_recipient_count_mismatch())
    payload = {
        "fixture": SEED_FIXTURE,
        "labels_provenance": "spec",
        "facts": {"gaps.later": {"phase": 1, "value": [[SEED_ID, "1", 1, ""]]}},
    }
    (directory / f"{SEED_STEM}.expected.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


#: gap id -> the corpus builder that produces the one fixture (or seed) it fires on.
CORPUS_FOR = {
    gap_id: (_seed if gap_id == SEED_ID else (lambda directory, stem=case.fixture: _committed(directory, stem)))
    for gap_id, case in CASES.items()
}


def _sums_names() -> set[str]:
    return {
        line.split("  ", 1)[1].strip()
        for line in SUMS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def test_every_msg_gap_id_has_a_mutation_case() -> None:
    """The registry ids, the live ids and the catalogue all agree; each case names its input.

    Every case names the committed fixture it fires on -- which must exist and be in
    ``fixtures/msg/SHA256SUMS`` -- or the seed this test builds. A case dropped from the
    catalogue is a non-empty difference (the tiling is exact, so the plant fails).
    """
    assert LIVE_MSG_IDS, "an empty live set proves nothing"
    assert REGISTRY_MSG_IDS == LIVE_MSG_IDS, {
        "registered but not live": sorted(REGISTRY_MSG_IDS - LIVE_MSG_IDS),
        "live but not registered": sorted(LIVE_MSG_IDS - REGISTRY_MSG_IDS),
    }
    assert set(CORPUS_FOR) == REGISTRY_MSG_IDS, {
        "cased or seeded but not registered": sorted(set(CORPUS_FOR) - REGISTRY_MSG_IDS),
        "registered but neither cased nor seeded": sorted(REGISTRY_MSG_IDS - set(CORPUS_FOR)),
    }
    sums = _sums_names()
    for gap_id, case in sorted(CASES.items()):
        assert case.fact_id == "gaps.later", case
        assert case.gap_id == gap_id, case
        assert case.naive.strip(), case
        if gap_id == SEED_ID:
            assert case.fixture == SEED_STEM
            assert SEED_FIXTURE not in sums, "the seed is built in this test, never committed"
        else:
            assert f"{case.fixture}.msg" in sums, (gap_id, case.fixture)
    # The plant: dropping one case leaves a non-empty difference, so the tiling can fail.
    dropped = {gap_id for gap_id in CORPUS_FOR if gap_id != sorted(REGISTRY_MSG_IDS)[0]}
    assert dropped != REGISTRY_MSG_IDS


def test_the_msg_ids_are_read_off_live_gap_ids() -> None:
    """The ids come from the registry document and ``LIVE_GAP_IDS``, never a literal here."""
    documented = {gap_id for gap_id in documented_ids() if gap_id.startswith("msg.")}
    registered = {gap_id for gap_id in registry_ids() if gap_id.startswith("msg.")}
    live = {gap_id for gap_id in LIVE_GAP_IDS if gap_id.startswith("msg.")}
    assert documented == registered, {
        "documented only": sorted(documented - registered),
        "registry only": sorted(registered - documented),
    }
    assert live == documented, {
        "live but not documented": sorted(live - documented),
        "documented but not live": sorted(documented - live),
    }
    assert len(live) == 11, sorted(live)
    assert MAPI_DISAGREE in documented_ids() and not MAPI_DISAGREE.startswith("msg.")
    assert REGISTRY_MSG_IDS == documented | {MAPI_DISAGREE}
    assert LIVE_MSG_IDS == live | {MAPI_DISAGREE}
    # The twelfth id is the only reader id the phase-1 gate cannot exercise over a committed
    # sidecar; the report repeats this reason (D1).
    assert {gap_id for gap_id in UNEXERCISED_GAP_IDS if gap_id.startswith("msg.")} == {SEED_ID}


@pytest.mark.parametrize("gap_id", sorted(CASES))
def test_the_phase1b_gap_gate_fails_when_a_gap_is_dropped(gap_id: str, tmp_path: Path) -> None:
    """Dropping one emission fails the phase-1 gate, naming the id and the fixture or seed."""
    case = CASES[gap_id]
    directory = tmp_path / gap_id.replace(".", "_")
    CORPUS_FOR[gap_id](directory)
    assert gap_gate(directory).passed is True, gap_gate(directory).lines()
    with mutated(case):
        gate = gap_gate(directory)
    assert gate.passed is False, gate.lines()
    joined = "\n".join(gate.evidence)
    assert f"gaps.later {gap_id}" in joined, joined
    assert case.fixture in joined, joined
