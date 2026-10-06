"""Turn 1.10a: the phase-1 gap gate, and the mutation catalogue that proves it can fail.

``gaps.later`` is Phase 1's gap channel: the stage channels (headers, dates, text, selection,
attachment, addresses, quote) each record their own gaps, and the oracle reads them through
:func:`emailextract.evals.gates.gap_gate`. This module is the gate's evidence:

* every phase-1 gap id a wired channel can emit has a mutation case in
  :mod:`emailextract.evals.falsify` (``PHASE1_CASES``), or is named in the committed
  ``UNEXERCISED_GAP_IDS`` list -- never silently tolerated;
* dropping one emission makes the gate fail, naming the gap id and the fixture, with the
  anti-vacuity triple (the patched symbol exists, the patch was reached, the baseline passes);
* the unlabelled emissions are reported, not counted as agreed.

The temporary corpora are built under ``tmp_path``; nothing here shares a file between processes.
The Phase 0 walker catalogue (``emailextract.evals.falsify.CASES``) is untouched and still stands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support.sidecar_copy import payload_of, write  # noqa: E402

from emailextract.evals import gap_gate  # noqa: E402
from emailextract.evals.falsify import (  # noqa: E402
    CASES,
    EMITTABLE_GAP_IDS,
    GAP_CHANNELS,
    PHASE1_CASES,
    UNEXERCISED_GAP_IDS,
    WALKER_GAPS,
    mutated,
)
from emailextract.evals.l1 import LIVE_GAP_IDS, emitted_gap_ids  # noqa: E402
from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars  # noqa: E402
from emailextract.evals.metrics import render  # noqa: E402

FIXTURES = DEFAULT_FIXTURES


def _one_fixture(tmp_path: Path, stem: str) -> Path:
    """A corpus of just ``stem``, in its own directory, so a mutation runs against one fixture."""
    source = next(FIXTURES.rglob(f"{stem}.expected.json"))
    directory = tmp_path / stem
    write(directory, payload_of(source), source=source)
    return directory


def test_the_committed_corpus_passes_the_gap_gate() -> None:
    gate = gap_gate()
    assert gate.passed is True, gate.lines()
    assert gate.data["exercised"] > 0
    assert gate.data["problems"] == 0


def test_every_phase1_gap_id_has_a_mutation_case() -> None:
    """Every emittable id is cased or named; the two sets tile ``EMITTABLE_GAP_IDS`` exactly."""
    assert EMITTABLE_GAP_IDS, "an empty emittable set proves nothing"
    cased = set(PHASE1_CASES)
    named = set(UNEXERCISED_GAP_IDS)
    assert not (cased & named), sorted(cased & named)
    assert cased | named == set(EMITTABLE_GAP_IDS), {
        "cased or named but not emittable": sorted((cased | named) - set(EMITTABLE_GAP_IDS)),
        "emittable but neither": sorted(set(EMITTABLE_GAP_IDS) - cased - named),
    }
    for gap_id, case in PHASE1_CASES.items():
        assert case.fact_id == "gaps.later", case
        assert case.gap_id == gap_id
        assert case.fixture and case.naive.strip()


def test_the_ids_no_fixture_exercises_are_named() -> None:
    """``UNEXERCISED_GAP_IDS`` is exactly the emittable ids no sidecar labels at a live phase-1 row.

    Re-derived from the corpus, so a fixture that starts (or stops) labelling one of them moves it
    in or out of the list rather than being tolerated.
    """
    live_labelled: set[str] = set()
    for sidecar in load_sidecars().values():
        fact = sidecar.facts.get("gaps.later")
        for row in fact.value if fact is not None else []:
            if row[2] == 1 and row[0] in LIVE_GAP_IDS:
                live_labelled.add(row[0])
    exercised = set(PHASE1_CASES)
    assert live_labelled == exercised, {
        "labelled live but not cased": sorted(live_labelled - exercised),
        "cased but not labelled live": sorted(exercised - live_labelled),
    }
    assert set(UNEXERCISED_GAP_IDS) == set(EMITTABLE_GAP_IDS) - live_labelled


def test_the_unlabelled_emissions_are_reported() -> None:
    """A live id the code emits that no sidecar labels is reported, never counted as agreed."""
    gate = gap_gate()
    unlabelled = set(gate.data["unlabelled"])
    assert unlabelled == {"body.html_quote_rule_gap"}, sorted(unlabelled)
    assert any("body.html_quote_rule_gap" in line for line in gate.evidence), gate.evidence


@pytest.mark.parametrize("gap_id", sorted(PHASE1_CASES))
def test_a_dropped_phase1_gap_fails_the_gate(gap_id: str, tmp_path: Path) -> None:
    """Dropping one emission fails the gate, naming the gap id and the fixture."""
    case = PHASE1_CASES[gap_id]
    directory = _one_fixture(tmp_path, case.fixture)
    assert gap_gate(directory).passed is True
    with mutated(case):
        gate = gap_gate(directory)
    assert gate.passed is False, gate.lines()
    assert gate.data["problems"] >= 1, gate.data
    joined = "\n".join(gate.evidence)
    assert f"gaps.later {gap_id}" in joined, joined
    assert case.fixture in joined, joined


def test_the_mutation_patch_is_reached(tmp_path: Path) -> None:
    """The anti-vacuity triple for the catalogue's most-used mechanism."""
    gap_id = "headers.leading_bom"
    case = PHASE1_CASES[gap_id]
    directory = _one_fixture(tmp_path, case.fixture)
    # (1) the patched symbol exists: every channel the mutation touches is a callable attribute.
    originals = {}
    for module, name in GAP_CHANNELS:
        assert callable(getattr(module, name)), (module, name)
        originals[(module, name)] = getattr(module, name)
    baseline = gap_gate(directory)
    assert baseline.passed is True, baseline.lines()  # (3) the unpached observation passes

    sidecar = load_sidecars(directory)[case.fixture]
    assert gap_id in emitted_gap_ids(sidecar)
    with mutated(case):
        assert any(getattr(module, name) is not originals[(module, name)]
                   for module, name in GAP_CHANNELS)  # (1) the patch was installed
        # (2) the patch was reached: the emission the gate reads lost the id.
        assert gap_id not in emitted_gap_ids(sidecar)
        assert gap_gate(directory).passed is False
    assert gap_id in emitted_gap_ids(sidecar)  # restored


def test_the_gate_fails_on_an_empty_corpus(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    gate = gap_gate(tmp_path / "empty")
    assert gate.passed is False
    assert "empty" in gate.detail


def test_a_subset_corpus_is_reported_but_not_failed_on_completeness(tmp_path: Path) -> None:
    """Turn 1.10a decision: the phase-1 completeness rules are stated over the committed corpus.

    ``plain_simple`` labels no live phase-1 gap, so the gate checks nothing -- which over the
    committed corpus is a failure (nothing was proved) but over a reviewer's subset is reported,
    not fatal. ``gap_gate()`` over the committed corpus is the anti-vacuity control.
    """
    directory = _one_fixture(tmp_path, "plain_simple")
    subset = gap_gate(directory)
    assert subset.data["exercised"] == 0
    assert subset.passed is True, subset.lines()
    assert gap_gate().data["exercised"] > 0, "the committed corpus must exercise live gap ids"


def test_the_metrics_table_reports_the_gap_gate() -> None:
    output = render()
    assert "phase-1 gaps" in output
    assert "phase-1 gaps" in output and "pass" in output


def test_the_walker_catalogue_still_stands() -> None:
    """The existing 1.5-1.8 falsifiability machinery is untouched (build spec D14, Turn 0.4)."""
    assert set(CASES) == set(WALKER_GAPS), sorted(set(CASES) ^ set(WALKER_GAPS))
    assert not (set(PHASE1_CASES) & set(CASES)), "the two catalogues must not collide"
