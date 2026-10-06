"""``python -m emailextract.evals`` -- the phase-0 metrics table, and its exit code (Turn 0.4).

One command answers "where does the harness stand": the L1 oracle's counts (matched,
mismatched, unmeasurable, unmodelled, ``not_yet`` by phase), every gate's verdict, the
corpus size by directory, how many of the walker's gaps a falsifiability case covers and
which no fixture exercises, and how many questions the labels leave open.

Exit status is 1 when **any gate fails** (a skipped gate is not a failure; it could not run,
and says why), 0 otherwise. A gate that compared nothing is a failure, not a pass.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from .falsify import CASES, uncovered_gaps, WALKER_GAPS
from .gates import GateResult, gap_gate, l1_gate, no_silent_drop_gate, phase1_exit
from .labels import DEFAULT_FIXTURES, LabelError, load_sidecars

#: Fixture files the corpus is made of: the message bytes, never a sidecar (which describes
#: a fixture) and never a raw fixture's SHA256SUMS (which freezes it).
FIXTURE_SUFFIX = ".eml"

SIDECAR_SUFFIX = ".expected.json"

#: A fixture tree that is never committed (real mail, machine-local), so never corpus.
LOCAL_ONLY = frozenset({"real"})


def corpus_size(root: Path | str = DEFAULT_FIXTURES) -> dict[str, Counter]:
    """Fixtures and sidecars, counted by the directory they sit in under ``root``."""
    base = Path(root)
    counts: dict[str, Counter] = {"fixtures": Counter(), "sidecars": Counter()}
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        if LOCAL_ONLY & set(relative.parts):
            continue
        where = relative.parts[0] if len(relative.parts) > 1 else "."
        if path.name.endswith(SIDECAR_SUFFIX):
            counts["sidecars"][where] += 1
        elif path.suffix.lower() == FIXTURE_SUFFIX:
            counts["fixtures"][where] += 1
    return counts


def undetermined(root: Path | str = DEFAULT_FIXTURES) -> int:
    """How many ``labels.undetermined`` entries the corpus carries: the questions left open."""
    try:
        sidecars = load_sidecars(root)
    except LabelError:
        return 0
    total = 0
    for sidecar in sidecars.values():
        fact = sidecar.facts.get("labels.undetermined")
        if fact is not None and isinstance(fact.value, list):
            total += len(fact.value)
    return total


def falsifiability(root: Path | str = DEFAULT_FIXTURES) -> tuple[int, int, tuple[str, ...]]:
    """``(covered, exercised, uncovered)``: cases the catalogue holds, gaps the corpus records, gaps it does not."""
    try:
        sidecars = load_sidecars(root)
    except LabelError:
        sidecars = {}
    uncovered = tuple(sorted(uncovered_gaps(sidecars)))
    exercised = len(WALKER_GAPS) - len(uncovered)
    return len(CASES), exercised, uncovered


def gates(root: Path | str = DEFAULT_FIXTURES, *, ledger: str | Path | None = None) -> list[GateResult]:
    """Every gate, in the order the design lists them."""
    return [
        l1_gate(root),
        no_silent_drop_gate(root),
        gap_gate(root),
        phase1_exit(root, ledger=ledger),
    ]


def render(root: Path | str = DEFAULT_FIXTURES, results: Sequence[GateResult] | None = None) -> str:
    """The whole table as text: one block per concern, the gates' evidence indented under them."""
    results = list(results if results is not None else gates(root))
    size = corpus_size(root)
    covered, exercised, uncovered = falsifiability(root)
    lines = [f"email-extract: L1 gate metrics at phase 0 (corpus: {root})"]

    l1 = results[0]
    counts = l1.data
    if counts:
        not_yet = ", ".join(f"phase {phase}={count}" for phase, count in counts["not_yet"].items())
        lines.append(
            f"  L1              matched={counts['matched']} mismatched={counts['mismatched']} "
            f"unmeasurable={counts['unmeasurable']} unmodelled={counts['unmodelled']}"
        )
        lines.append(f"  {'':<14} not_yet: {not_yet or 'none'}")
    lines.append(f"  labels.undetermined={undetermined(root)} question(s) the labels leave open")

    lines.append("  gates:")
    for result in results:
        lines.append(f"    {result.name:<14} {result.status:<4} {result.detail}")
        if result.skipped:
            lines.append(f"    {'':<14} skipped: {result.skip_reason}")
        elif result.failed:
            lines.extend(f"    {'':<14} {entry}" for entry in result.evidence)

    lines.append(
        f"  corpus: {sum(size['fixtures'].values())} fixture(s), "
        f"{sum(size['sidecars'].values())} sidecar(s)"
    )
    for where in sorted(set(size["fixtures"]) | set(size["sidecars"])):
        lines.append(
            f"    {where:<14} {size['fixtures'][where]} fixture(s), "
            f"{size['sidecars'][where]} sidecar(s)"
        )

    lines.append(
        f"  falsifiability: {covered} gap(s) covered by cases, {exercised} recorded by sidecars"
    )
    lines.append(
        "  not exercised by any fixture: "
        + (", ".join(uncovered) if uncovered else "none (every gap has a committed fixture or inline bytes)")
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m emailextract.evals", description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument("--root", default=str(DEFAULT_FIXTURES), help="the fixture corpus to report on")
    parser.add_argument("--quiet", action="store_true", help="print nothing, only exit on the verdict")
    arguments = parser.parse_args(argv)
    results = gates(arguments.root)
    if not arguments.quiet:
        print(render(arguments.root, results))
    return 1 if any(result.failed for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
