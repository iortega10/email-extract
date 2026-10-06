"""The Phase 1 exit gate: the phase-1 wait is exactly a closed, named, committed set.

Turn 1.10a closes Phase 1's accounting: every phase-1 fact is either measured or a **wait**, and a
wait is acceptable only when it is a named, committed row the package cannot satisfy without
editing a frozen label. ``tests/ledger/phase1_exit.json`` is that set -- the six rows Turn 1.10a's
classification found (four over-emissions: ``body.no_boundary_found`` on 102 fixtures,
``view.quote_level_disagreement`` on 6 and ``body.inline_reply_interleaved`` on 3; two no-emissions:
``attach.cid_dangling`` and ``body.mixed_origin_quoting``, typed but emitted by nothing) -- and
:func:`emailextract.evals.phase1_exit` is the gate over it.

This module is its evidence: the gate passes over the committed corpus; the ledger's rows are
exactly the rows the corpus waits on; and every way it can fail is exercised, each with the
anti-vacuity triple (the patched symbol exists, the patch was reached, the observation differs from
baseline) -- dropping a named row, adding an unnamed phase-1 wait, an empty corpus and a corpus that
compares nothing.
"""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402
from support.sidecar_copy import tamper  # noqa: E402

from emailextract.evals import gates as gates_module  # noqa: E402
from emailextract.evals import phase1_exit  # noqa: E402
from emailextract.evals.gates import (  # noqa: E402
    PHASE1_EXIT_LEDGER,
    PHASE1_EXIT_PHASE,
    load_phase1_exit,
    wait_key,
)
from emailextract.evals.l1 import LIVE_GAP_IDS  # noqa: E402
from emailextract.evals.labels import load_sidecars  # noqa: E402
from emailextract.evals.metrics import render  # noqa: E402
from emailextract.quote import text_rules  # noqa: E402

FIXTURES = sidecar_copy.FIXTURES

#: A sidecar whose only non-phase-0 facts are phase 3: stripping its phase-0 facts leaves a corpus
#: that loads but compares nothing (the vacuity case).
TIME_SIDECAR = FIXTURES / "time" / "date_before_hops.expected.json"


def _named_keys() -> frozenset:
    return frozenset(wait_key(row) for row in load_phase1_exit())


def test_the_gate_passes_over_the_committed_corpus() -> None:
    """The exit criterion, as a verdict: the wait is exactly the named set, nothing else."""
    gate = phase1_exit()
    assert gate.passed is True, gate.lines()
    assert gate.skipped is False
    assert gate.data["extra"] == () and gate.data["missing"] == ()
    assert gate.data["phase"] == PHASE1_EXIT_PHASE
    assert any("exactly the named, committed set" in line for line in gate.evidence), gate.evidence


def test_the_named_wait_set_matches_the_observed_rows() -> None:
    """The ledger is the corpus's wait, both ways -- no extra row, no named row the corpus does not wait on."""
    gate = phase1_exit()
    assert set(gate.data["wait"]) == _named_keys(), gate.data["wait"]
    assert set(gate.data["named"]) == _named_keys()
    assert len(gate.data["wait"]) == 6, gate.data["wait"]


def test_a_dropped_named_row_fails_the_gate() -> None:
    """Drop one row from the named set: the corpus still waits on it, so it is an ``extra``.

    The gates-must-be-able-to-fail half, with the anti-vacuity triple: (1) the named set is what
    the gate reads, so a smaller one is a smaller set; (2) the gate was reached (it returned a
    verdict); (3) the same call with the committed set passes, so the failure is the dropped row's.
    """
    baseline = phase1_exit()
    assert baseline.passed is True, baseline.lines()
    keys = sorted(_named_keys())
    dropped = keys[0]
    gate = phase1_exit(named=frozenset(keys[1:]))
    assert gate.passed is False, gate.lines()
    assert gate.data["extra"] == (dropped,), gate.data
    assert not gate.data["missing"]
    assert any("does not carry" in line for line in gate.evidence), gate.evidence


def test_a_named_row_the_corpus_does_not_wait_on_fails_the_gate() -> None:
    """Vacuity the other way: hand the gate a named row nothing is ``not_yet`` for, and it is ``missing``."""
    bogus = ("a_fixture_that_does_not_wait", "gaps.later", "body.made_up", "1")
    gate = phase1_exit(named=_named_keys() | {bogus})
    assert gate.passed is False, gate.lines()
    assert gate.data["missing"] == (bogus,), gate.data
    assert gate.data["extra"] == ()


def test_an_unnamed_phase1_wait_fails_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-un-live a gap id: its rows wait again, outside the named set, so the gate fails.

    The anti-vacuity triple: (1) ``gates.LIVE_GAP_IDS`` is what :func:`_observed_waits` reads at
    call time, so removing ``body.i18n_reply_marker`` makes its two rows waits; (2) the gate's
    default named set (the ledger) does not carry them, so they come back as ``extra``; (3) the
    same call with the committed live set passes, so the failure is the patch's.
    """
    baseline = phase1_exit()
    assert baseline.passed is True, baseline.lines()
    i18n = text_rules.GAP_I18N_REPLY_MARKER
    assert i18n in LIVE_GAP_IDS
    assert i18n not in {row[2] for row in _named_keys()}
    monkeypatch.setattr(gates_module, "LIVE_GAP_IDS", frozenset(LIVE_GAP_IDS - {i18n}))

    gate = phase1_exit()
    assert gate.passed is False, gate.lines()
    extra = {row[2] for row in gate.data["extra"]}
    assert extra == {i18n}, gate.data["extra"]
    assert gate.data["extra"] == (
        ("i18n_reply_marker", "gaps.later", i18n, "1"),
        ("unknown_language_label_block", "gaps.later", i18n, "1"),
    ), gate.data["extra"]
    assert any("does not carry" in line for line in gate.evidence), gate.evidence


def test_an_empty_corpus_fails_the_gate(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    gate = phase1_exit(tmp_path / "empty")
    assert gate.passed is False
    assert "empty" in gate.detail


def test_a_vacuous_corpus_fails_the_gate(tmp_path: Path) -> None:
    """A corpus that compares nothing cannot pass even with an empty named set (rule 10)."""

    def mutate(payload):
        facts = payload["facts"]
        for fact_id in list(facts):
            if facts[fact_id]["phase"] == 0:
                del facts[fact_id]

    tamper(tmp_path, TIME_SIDECAR, mutate)
    gate = phase1_exit(
        tmp_path / TIME_SIDECAR.name.removesuffix(".expected.json"), named=frozenset()
    )
    assert gate.passed is False
    assert "compared nothing" in gate.detail, gate.detail
    assert gate.data["compared"] == 0


def test_the_named_set_carries_a_reason_and_the_bytes_evidence() -> None:
    """Every named row is a class-``b`` finding with its reason and the bytes that evidence it."""
    rows = load_phase1_exit()
    assert len(rows) == 6, rows
    for row in rows:
        assert row["class"] == "b", row
        assert row["finding"] in {"over-emission", "no-emission"}, row
        assert isinstance(row["reason"], str) and row["reason"].strip(), row
        evidence = row["evidence"]
        assert isinstance(evidence["labelled_rows"], list) and evidence["labelled_rows"], row
        # The two findings, each carrying the counts that name it:
        if row["finding"] == "no-emission":
            assert evidence["quote_stage_emission_count_over_corpus"] == 0, row
        else:
            assert evidence["quote_stage_emission_count_over_corpus"] > (
                evidence["label_row_count_over_corpus"]
            ), row
            assert row["gap_id"] in {emitted[0] for emitted in evidence["quote_stage_emissions"]}, row
        # The bytes' evidence is real: the recorded sha256 is the committed fixture's own.
        fixture = next(FIXTURES.rglob(f"{row['fixture']}.eml"))
        assert sha256(fixture.read_bytes()).hexdigest() == evidence["fixture_sha256"], row


def test_the_ledger_is_shaped_for_a_json_round_trip() -> None:
    loaded = json.loads(PHASE1_EXIT_LEDGER.read_text(encoding="utf-8"))
    assert loaded["phase"] == PHASE1_EXIT_PHASE
    assert json.loads(json.dumps(loaded)) == loaded
    gate = phase1_exit()
    round_tripped = json.loads(json.dumps(gate.data))
    assert set(round_tripped) == set(gate.data)
    assert round_tripped["wait"] == [list(row) for row in gate.data["wait"]]
    assert round_tripped["extra"] == [] and round_tripped["missing"] == []


def test_the_metrics_table_reports_the_phase1_exit_gate() -> None:
    output = render()
    assert "phase1 exit" in output
    assert "phase1 exit    pass" in output


def test_the_gate_reads_the_corpus_the_tests_read() -> None:
    gate = phase1_exit()
    assert gate.data["sidecars"] == len(load_sidecars())
    assert gate.data["sidecars"] >= 1
