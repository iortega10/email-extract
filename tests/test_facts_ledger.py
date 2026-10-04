"""Turn 1.0b: the pinned ``FACTS`` ledger (``docs/design/phase1-ledgers.md`` section (b)).

The declared phase-1 fact-id list is pinned and the deferred set is a closed list,
empty by default. ``tests/ledger/facts_ledger.json`` holds both; this test compares it
to ``emailextract.evals.l1.FACT_PHASES`` and fails, naming the id, unless they agree --
so a fact's phase cannot be redeclared to dodge a coverage obligation.
"""

from __future__ import annotations

import json
from pathlib import Path

from emailextract.evals.l1 import CURRENT_PHASE, FACT_PHASES, FACTS

LEDGER_PATH = Path(__file__).resolve().parent / "ledger" / "facts_ledger.json"


def _load() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _ledger_problems(phases: dict[str, int], ledger: dict) -> list[str]:
    """Every way ``phases`` disagrees with the ledger; ``[]`` means they agree."""
    phase1 = sorted(fact_id for fact_id, phase in phases.items() if phase == 1)
    pinned = sorted(ledger.get("phase1", []))
    deferred = list(ledger.get("deferred", []))
    problems: list[str] = []
    if phase1 != pinned:
        moved_out = sorted(set(pinned) - set(phase1))
        moved_in = sorted(set(phase1) - set(pinned))
        problems.append(
            f"facts_ledger: the phase-1 fact set changed (not pinned any more: {moved_out}; "
            f"newly phase 1: {moved_in}) -- change the ledger in the same commit as the phase"
        )
    overlap = sorted(set(deferred) & set(phase1))
    if overlap:
        problems.append(f"facts_ledger: deferred ids are also phase 1: {overlap}")
    if len(deferred) != len(set(deferred)):
        problems.append("facts_ledger: the deferred set has duplicates")
    return problems


def test_the_phase1_fact_ids_match_the_ledger() -> None:
    """The pinned ids are exactly the phase-1 ids of ``FACTS``, and there are twenty."""
    ledger = _load()
    assert _ledger_problems(dict(FACT_PHASES), ledger) == []
    assert len(ledger["phase1"]) == len(set(ledger["phase1"])) == 20
    assert set(ledger["phase1"]) <= set(FACTS)
    # The oracle is at phase 0, so every pinned fact is declared ahead of the oracle.
    assert CURRENT_PHASE == 0


def test_a_moved_fact_phase_fails_the_ledger() -> None:
    """Moving a fact's phase to dodge a coverage obligation is caught, naming the id."""
    ledger = _load()
    moved = dict(FACT_PHASES)
    moved["body.quote_boundaries"] = 3
    problems = _ledger_problems(moved, ledger)
    assert any("body.quote_boundaries" in problem for problem in problems)
    # And adding a new phase-1 fact without listing it fails the same way.
    added = {**FACT_PHASES, "body.brand_new": 1}
    assert _ledger_problems(added, ledger)


def test_the_deferred_set_is_closed_and_empty() -> None:
    """``deferred`` is a closed list, empty by default, disjoint from ``phase1``."""
    ledger = _load()
    assert ledger["deferred"] == []
    assert set(ledger["deferred"]).isdisjoint(ledger["phase1"])
    # A non-empty deferred set that overlaps phase 1 is itself a problem.
    broken = {**ledger, "deferred": [ledger["phase1"][0]]}
    assert _ledger_problems(dict(FACT_PHASES), broken)
