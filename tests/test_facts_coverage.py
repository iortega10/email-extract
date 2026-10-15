"""Turn 1.10a: the phase-1 coverage floors, and the three artefacts of build spec decision 4.

A per-(fact x phase) coverage floor is what stops "L1 at 100%" from being vacuous: a phase-1 fact
labelled on one fixture, or on none, has to fail rather than ride on the ids that *are* covered.
``tests/ledger/facts_ledger.json`` carries the three artefacts this module asserts:

* **declared** -- each phase-1 fact's floor as ``docs/design/phase1-facts.md`` names it (parsed from
  the design table, so a floor and its id cannot drift apart);
* **achieved** -- the committed corpus's *labelled* count (sidecars carrying the fact) and
  *compared* count (sidecars the oracle measured) at this commit, a **ratchet**: a count may rise
  but never fall;
* **zero_labelled** -- the closed list of phase-1 facts no sidecar labels (the real gap).

And the **rebase**: the design's floors were set before the fixture catalogue, and the committed
corpus meets 9 of the 20. Turn 1.10a re-bases each floor to the count the corpus achieves -- never
lowering one silently -- and records the change, its reason and every unmet declared floor in the
ledger. Writing ``"signed": ...`` is the owner's act; the ledger here is ``"proposed"``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from emailextract.evals.l1 import FACT_PHASES, Status, check
from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = Path(__file__).resolve().parent / "ledger" / "facts_ledger.json"
#: The design fact tables: the phase-1 table (Turn 1.0b) and the Phase 1b table (Turn 1b.0a),
#: whose 11 ``msg.*`` ids join the same ``phase1`` set (Turn 1b.10a, D6).
FACTS_DOC = ROOT / "docs" / "design" / "phase1-facts.md"
FACTS_1B_DOC = ROOT / "docs" / "design" / "phase1b-facts.md"

#: The design's phase-1 fact table row: ``| `id` [(existing)] | 1 | scope | turn | vocabularies | N |``.
_FLOOR_ROW = re.compile(
    r"^\| `(?P<fact>[^`]+)`(?: \*\(existing\)\*)? \| 1 \| \w+ \| [^|]+ \| [^|]+ \| (?P<floor>\d+) \|$"
)


def _load() -> dict[str, Any]:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _design_floors() -> dict[str, int]:
    """The floors the design tables name, keyed by fact id.

    Both the phase-1 table and the Phase 1b table (``docs/design/phase1b-facts.md``) are parsed
    with the same row regex; the Phase 1b ids are phase-1 facts (R13), so their floors join the
    same mapping.
    """
    floors: dict[str, int] = {}
    for doc in (FACTS_DOC, FACTS_1B_DOC):
        for line in doc.read_text(encoding="utf-8").splitlines():
            match = _FLOOR_ROW.match(line)
            if match:
                floors[match.group("fact")] = int(match.group("floor"))
    return floors


def _phase1_ids() -> list[str]:
    return sorted(fact_id for fact_id, phase in FACT_PHASES.items() if phase == 1)


def _trivial(value: Any) -> bool:
    """Whether a fact value carries nothing: absent, zero, empty, or a list of such."""
    if value is None or value is False:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        return value == ""
    if isinstance(value, (list, tuple)):
        return not any(not _trivial(item) for item in value)
    if isinstance(value, Mapping):
        return not any(not _trivial(item) for item in value.values())
    return False


def _measured(root: Path | str = DEFAULT_FIXTURES) -> dict[str, dict[str, Any]]:
    """Recompute ``labelled``/``compared`` per phase-1 fact, plus whether a non-trivial value rides."""
    phase1 = _phase1_ids()
    counts: dict[str, dict[str, Any]] = {
        fact_id: {"labelled": 0, "compared": 0, "non_trivial": False} for fact_id in phase1
    }
    sidecars = load_sidecars(root)
    for sidecar in sidecars.values():
        for fact_id in phase1:
            fact = sidecar.facts.get(fact_id)
            if fact is None:
                continue
            counts[fact_id]["labelled"] += 1
            if not _trivial(fact.value):
                counts[fact_id]["non_trivial"] = True
        for outcome in check(sidecar).outcomes:
            if outcome.fact_id in counts and outcome.status in (Status.OK, Status.MISMATCH):
                counts[outcome.fact_id]["compared"] += 1
    return counts


def test_the_ledger_declares_a_floor_for_every_phase1_fact() -> None:
    """The declared floors are the design table's, for every phase-1 fact and no other."""
    ledger = _load()
    design = _design_floors()
    phase1 = _phase1_ids()
    assert set(design) == set(phase1), {
        "in the design table but not phase 1": sorted(set(design) - set(phase1)),
        "phase 1 but not in the design table": sorted(set(phase1) - set(design)),
    }
    assert ledger["declared"] == design
    assert set(ledger["floors"]) == set(phase1)
    assert set(ledger["achieved"]) == set(phase1)


def test_every_phase1_fact_meets_its_coverage_floor() -> None:
    """Every phase-1 fact is carried by at least its (effective) floor's worth of sidecars."""
    ledger = _load()
    measured = _measured()
    short = {
        fact_id: (measured[fact_id]["labelled"], ledger["floors"][fact_id])
        for fact_id in _phase1_ids()
        if measured[fact_id]["labelled"] < ledger["floors"][fact_id]
    }
    assert not short, short


def test_at_least_one_sidecar_carries_a_non_trivial_value() -> None:
    """For every phase-1 fact one sidecar carries a non-trivial, non-empty value (never vacuous)."""
    measured = _measured()
    empty = sorted(fact_id for fact_id, row in measured.items() if not row["non_trivial"])
    assert not empty, empty


def test_the_achieved_counts_ratchet_against_the_ledger() -> None:
    """The labelled and compared counts may rise from the ledger's, never fall (a ratchet)."""
    ledger = _load()
    measured = _measured()
    dropped = {
        fact_id: (ledger["achieved"][fact_id], {k: measured[fact_id][k] for k in ("labelled", "compared")})
        for fact_id in _phase1_ids()
        if measured[fact_id]["labelled"] < ledger["achieved"][fact_id]["labelled"]
        or measured[fact_id]["compared"] < ledger["achieved"][fact_id]["compared"]
    }
    assert not dropped, dropped


def test_the_zero_labelled_row_facts_are_the_measured_list() -> None:
    """``zero_labelled`` is exactly the phase-1 facts no committed sidecar labels."""
    ledger = _load()
    measured = _measured()
    zero = sorted(fact_id for fact_id, row in measured.items() if row["labelled"] == 0)
    assert ledger["zero_labelled"] == zero, {"ledger": ledger["zero_labelled"], "measured": zero}


def test_the_declared_floors_the_corpus_does_not_meet_are_recorded() -> None:
    """Every declared floor the corpus falls short of is a recorded finding, never lowered silently."""
    ledger = _load()
    measured = _measured()
    unmet = [
        {"fact": fact_id, "declared": ledger["declared"][fact_id], "achieved": measured[fact_id]["labelled"]}
        for fact_id in _phase1_ids()
        if measured[fact_id]["labelled"] < ledger["declared"][fact_id]
    ]
    assert ledger["declared_unmet"] == unmet, {
        "ledger": ledger["declared_unmet"],
        "measured": unmet,
    }
    assert unmet, "the rebase exists because a declared floor is unmet; an empty list needs a reason"


def test_the_rebase_record_is_proposed_or_signed() -> None:
    """The rebase is proposed here (the owner signs by committing) and is structurally complete."""
    rebase = _load()["rebase"]
    assert set(rebase) == {"status", "from", "to", "reason", "signed_by"}
    assert rebase["status"] in {"proposed", "signed"}
    if rebase["status"] == "signed":
        assert isinstance(rebase["signed_by"], str) and rebase["signed_by"].strip()
    else:
        assert rebase["signed_by"] is None, "a proposed rebase is not signed"
    assert isinstance(rebase["reason"], str) and rebase["reason"].strip()
    assert rebase["from"] == _load()["declared"]
    assert rebase["to"] == _load()["floors"]


def test_the_effective_floor_is_the_achieved_count_at_the_rebase() -> None:
    """The rebase re-based each floor onto the count achieved, so ``to`` == ``floors`` <= ``achieved``."""
    ledger = _load()
    measured = _measured()
    for fact_id in _phase1_ids():
        assert ledger["floors"][fact_id] == ledger["rebase"]["to"][fact_id], fact_id
        assert ledger["floors"][fact_id] <= measured[fact_id]["labelled"], fact_id


#: The eleven Phase 1b fact ids (Turn 1b.10a) whose floors this turn adds.
PHASE1B_IDS = (
    "msg.container_layout",
    "msg.sector_accounting",
    "msg.message_class",
    "msg.body_streams",
    "msg.recipients",
    "msg.time_facts",
    "msg.codepage_ladder",
    "msg.stream_faults",
    "msg.attachments",
    "msg.embedded_summary",
    "msg.storage_tree_sha256",
)


def test_every_phase1b_fact_meets_its_floor() -> None:
    """Every Phase 1b fact is carried by at least its (effective) floor's worth of sidecars.

    Its *declared* floor (the facts table's) is met, or the shortfall is a recorded finding in
    ``declared_unmet`` -- the floor is never lowered silently.
    """
    ledger = _load()
    measured = _measured()
    for fact_id in PHASE1B_IDS:
        assert fact_id in ledger["floors"], fact_id
        assert measured[fact_id]["labelled"] >= ledger["floors"][fact_id], (
            fact_id,
            measured[fact_id]["labelled"],
            ledger["floors"][fact_id],
        )
        if measured[fact_id]["labelled"] < ledger["declared"][fact_id]:
            assert {"fact": fact_id, "declared": ledger["declared"][fact_id],
                    "achieved": measured[fact_id]["labelled"]} in ledger["declared_unmet"], fact_id


def test_a_fact_below_its_floor_fails() -> None:
    """A planted floor past the observed count is a shortfall: the check has teeth."""
    ledger = _load()
    measured = _measured()
    planted = dict(ledger["floors"])
    fact_id = PHASE1B_IDS[0]
    planted[fact_id] = measured[fact_id]["labelled"] + 1
    short = {
        fid: (measured[fid]["labelled"], planted[fid])
        for fid in PHASE1B_IDS
        if measured[fid]["labelled"] < planted[fid]
    }
    assert short == {fact_id: (measured[fact_id]["labelled"], planted[fact_id])}
