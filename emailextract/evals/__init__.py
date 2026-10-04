"""The eval harness: hand-typed labels, the oracle that measures the fixtures against them, and the
gates that decide whether the corpus is in the state the phase claims (D11).

``labels`` reads the sidecars and imports nothing from this package; ``l1`` walks each fixture and
measures the facts the current phase claims, reporting the rest as ``not_yet``. Keeping the two
apart is what makes the labels independent: the side that knows the answer never touches the side
that produces one.

The Turn 0.4 gates, each a callable verdict with the evidence it was reached on
(:mod:`emailextract.evals.gates`):

* ``l1_gate`` -- the oracle at 100% over the facts the current phase claims, ``not_yet`` by phase;
* ``no_silent_drop_gate`` -- every byte of every fixture in exactly one accounted region, and the
  gate shows a dropped region and an overlap are both detected;
* ``falsify`` -- one falsifiability case per walker gap, by monkeypatching one rule;
* ``metrics`` -- ``python -m emailextract.evals``, the table over all of them and its exit code.

Nothing here is a reader: the gates measure the fixtures with the walker and read the labels as
data, and a label/walker disagreement is a finding, never something to reconcile by editing a label.
"""

from __future__ import annotations

from .falsify import CASES, GapCase, WALKER_GAPS, describe, mutated, uncovered_gaps
from .gates import GateResult, Hole, holes, l1_gate, no_silent_drop_gate
from .l1 import (
    CURRENT_PHASE,
    FACTS,
    FACT_PHASES,
    Measure,
    OracleError,
    Outcome,
    Report,
    Status,
    check,
    check_all,
    check_path,
)
from .labels import Fact, LabelError, Sidecar, load_sidecar, load_sidecars, sidecar_paths

__all__ = [
    "CASES",
    "CURRENT_PHASE",
    "FACTS",
    "FACT_PHASES",
    "GapCase",
    "GateResult",
    "Hole",
    "Fact",
    "LabelError",
    "Measure",
    "OracleError",
    "Outcome",
    "Report",
    "Sidecar",
    "Status",
    "WALKER_GAPS",
    "check",
    "check_all",
    "check_path",
    "describe",
    "holes",
    "l1_gate",
    "load_sidecar",
    "load_sidecars",
    "mutated",
    "no_silent_drop_gate",
    "sidecar_paths",
    "uncovered_gaps",
]
