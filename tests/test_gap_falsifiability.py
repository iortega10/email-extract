"""Falsifiability per named gap (design D14, build spec Turn 0.4).

The walker exists, so the per-gap cases are written against it directly: each monkeypatches
**one** walker rule (``emailextract.evals.falsify.mutated``) to do what a careless
implementation would, and the claim is that the L1 gate then fails on the sidecar carrying
that gap, with the fixture, the fact and the gap id named. A faithful run -- no mutation --
passes the same case, so the mutation is what is caught, not the fixture.

Six gaps are carried by a committed fixture; the two the sidecars do not carry
(``body.headers_only``, ``body.no_boundary_found``) are proven against inline hand-typed bytes,
built here into a temporary corpus, so no fixture is added and no sidecar edited.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402

from emailextract.evals import falsify  # noqa: E402
from emailextract.evals.falsify import (  # noqa: E402
    CASES,
    WALKER_GAPS,
    describe,
    exercised_gaps,
    mutated,
    uncovered_gaps,
)
from emailextract.evals.gates import l1_gate  # noqa: E402
from emailextract.evals.l1 import Status, check, load_sidecar  # noqa: E402
from emailextract.evals.labels import load_sidecars  # noqa: E402

SIDECARS = load_sidecars()
SIDECAR_PATHS = {stem: sidecar.path for stem, sidecar in SIDECARS.items()}
INLINE_ONLY = {"body.headers_only", "body.no_boundary_found"}


def _outcome(report, fact_id: str):
    outcomes = [outcome for outcome in report.outcomes if outcome.fact_id == fact_id]
    assert len(outcomes) == 1, f"{fact_id}: {len(outcomes)} outcomes"
    return outcomes[0]


def _case_corpus(case, tmp_path: Path):
    """A one-fixture corpus for ``case`` (a committed copy, or the inline bytes), loaded."""
    directory = tmp_path / "case"
    if case.fixture is not None:
        source = SIDECAR_PATHS[case.fixture]
        sidecar_path = sidecar_copy.write(
            directory, sidecar_copy.payload_of(source), source=source
        )
    else:
        name = case.gap_id.replace(".", "_")
        sidecar_path = sidecar_copy.write_inline(
            directory, name, case.inline, falsify.inline_sidecar(case, case.inline)
        )
    return sidecar_path.parent, load_sidecar(sidecar_path)


def test_the_catalogue_covers_every_walker_gap() -> None:
    assert len(WALKER_GAPS) == 8, WALKER_GAPS
    assert set(CASES) == set(WALKER_GAPS), (
        "a walker gap with no case, or a case for a gap the walker cannot emit: "
        f"walker {sorted(WALKER_GAPS)}, cases {sorted(CASES)}"
    )


def test_the_gaps_no_fixture_carries_are_the_inline_cases() -> None:
    """Both directions: the corpus's six, and the two that need inline bytes -- reported, not hidden."""
    uncovered = uncovered_gaps(SIDECARS)
    assert uncovered == INLINE_ONLY, uncovered
    for gap_id, case in CASES.items():
        if gap_id in INLINE_ONLY:
            assert case.inline is not None and case.fixture is None
            assert case.expected_gaps
        else:
            assert case.fixture is not None
    assert exercised_gaps(SIDECARS) == set(WALKER_GAPS) - INLINE_ONLY
    assert len(CASES) == 8


@pytest.mark.parametrize("gap_id", sorted(CASES))
def test_a_faithful_case_passes_and_the_mutant_is_caught(gap_id: str, tmp_path: Path) -> None:
    case = CASES[gap_id]
    directory, sidecar = _case_corpus(case, tmp_path)

    faithful = check(sidecar)
    outcome = _outcome(faithful, case.fact_id)
    assert outcome.status is Status.OK, describe(case, sidecar.stem, outcome)
    assert l1_gate(directory).passed is True, l1_gate(directory).lines()

    with mutated(case):
        careless = check(sidecar)
        gate = l1_gate(directory)
    outcome = _outcome(careless, case.fact_id)
    assert outcome.status is Status.MISMATCH, describe(case, sidecar.stem, outcome)
    assert gate.passed is False
    assert any(case.fact_id in line for line in gate.evidence), gate.evidence

    message = describe(case, sidecar.stem, outcome)
    for piece in (case.fact_id, case.gap_id, sidecar.stem, case.naive):
        assert piece in message, message


def test_the_mutation_is_restored_after_each_case() -> None:
    """``mutated`` is a context manager: the walker is exactly as it was once the block ends."""
    from emailextract import walk as walk_module

    case = CASES["body.preamble_bytes"]
    original = walk_module._segment
    with mutated(case):
        assert walk_module._segment is not original
    assert walk_module._segment is original
