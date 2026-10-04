"""The Turn 0.4 gates: a callable pass/fail verdict per property, each able to fail.

A gate is not a test. A test is a claim about one property, written by whoever changed the
code; a gate is the *same* claim with a verdict a caller can print, count and exit on --
which is what ``python -m emailextract.evals`` reports. So every gate here:

* returns a :class:`GateResult` -- ``passed`` plus the evidence it was decided on, never
  just a boolean;
* fails when it compared **nothing**: a gate that passes because the corpus is empty stays
  green through any regression, which is exactly the emptiness the ledger and the corpus
  exist to make visible (build spec ground rules, Exit criteria);
* can be *shown* to fail, which is why each gate has falsification tests over deliberately
  wrong copies in a temporary directory -- never over a committed label, fixture or sidecar.

Two gates live here:

* :func:`l1_gate` -- the L1 oracle (``emailextract.evals.l1``) at 100% over the facts the
  current phase claims, with every later-phase fact counted ``not_yet`` by phase. A
  label/walker disagreement is a **mismatch**, reported with the fixture and both values;
  it is a finding, never something to reconcile by editing a label.
* :func:`no_silent_drop_gate` -- design D9's accounting invariant: in every fixture, every
  input byte lies in exactly one accounted region, regions neither overlap nor leave a gap.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..container import EmlContainer
from ..walk import Region, walk
from .l1 import CURRENT_PHASE, FACTS, OracleError, check
from .labels import DEFAULT_FIXTURES, LabelError, load_sidecars

__all__ = [
    "COUNTED",
    "GateResult",
    "Hole",
    "holes",
    "l1_gate",
    "no_silent_drop_gate",
]

#: The statuses a fact can end at, as the printed counts name them. ``not_yet`` is not here:
#: it is counted per phase instead, because "due at phase 1" and "due at phase 3" are
#: different claims about the future, and a single total would hide which one is missing.
COUNTED = ("ok", "mismatch", "unmeasurable")


@dataclass(frozen=True)
class GateResult:
    """One gate's verdict, with the evidence it was reached on.

    ``skip_reason`` is how a gate says "this could not run, and here is why" without either
    passing silently or failing for the wrong reason. :attr:`skipped` is therefore not a
    pass: a caller that treats it as one has to say so itself, and the metrics table prints
    the reason either way.
    """

    name: str
    passed: bool
    detail: str = ""
    evidence: tuple[str, ...] = ()
    skip_reason: str | None = None
    #: The counts the verdict was reached on, for a caller that prints them (the metrics
    #: table). Never a substitute for ``passed``: a gate decides, and this says what it
    #: decided on.
    data: Mapping[str, Any] = field(default_factory=dict)

    @property
    def skipped(self) -> bool:
        return self.skip_reason is not None

    @property
    def failed(self) -> bool:
        """A gate that is neither passed nor skipped. A skipped gate is not a failure."""
        return not self.passed and not self.skipped

    @property
    def status(self) -> str:
        if self.skipped:
            return "skip"
        return "pass" if self.passed else "FAIL"

    def lines(self) -> list[str]:
        """The gate as printed lines: the verdict, then the evidence, indented."""
        lines = [f"{self.name}: {self.status}"]
        if self.detail:
            lines.append(f"  {self.detail}")
        if self.skip_reason:
            lines.append(f"  skipped: {self.skip_reason}")
        lines.extend(f"  {entry}" for entry in self.evidence)
        return lines


# ------------------------------------------------------------------- the L1 gate


def l1_gate(root: Path | str = DEFAULT_FIXTURES, *, phase: int = CURRENT_PHASE) -> GateResult:
    """The L1 oracle as a gate, at 100% over every fact available at ``phase``.

    Passes only when **something was compared and none of it failed**: at least one sidecar,
    at least one compared fact, no mismatch, no unmeasurable measurement, no label naming a
    fact the oracle does not model, and no harness defect (a malformed sidecar, a missing
    fixture, a phase the labels and the oracle disagree about). An empty corpus fails.
    """
    try:
        sidecars = load_sidecars(root)
    except LabelError as error:
        return GateResult(
            name="L1",
            passed=False,
            detail="the labels could not be loaded, so nothing was compared",
            evidence=(str(error),),
        )

    unmodelled = sorted(
        {
            fact.id
            for sidecar in sidecars.values()
            for fact in sidecar.facts.values()
            if fact.id not in FACTS
        }
    )
    counts: Counter[str] = Counter()
    not_yet: Counter[int] = Counter()
    problems: list[str] = []
    mismatches: list[str] = []
    for stem, sidecar in sidecars.items():
        try:
            report = check(sidecar, phase=phase)
        except OracleError as error:
            problems.append(f"{stem}: {error}")
            continue
        counts.update(report.counts())
        for due, count in report.not_yet_by_phase().items():
            not_yet[due] += count
        for outcome in report.failures:
            line = (
                f"{outcome.where}: {outcome.fact_id} {outcome.status.value}"
                + (f" -- {outcome.detail}" if outcome.detail else "")
            )
            mismatches.append(line)
            problems.append(line)

    evidence = [f"compared {counts['ok']} fact(s) over {len(sidecars)} sidecar(s)"]
    evidence.extend(f"not_yet, phase {due}: {count} fact(s)" for due, count in sorted(not_yet.items()))
    if unmodelled:
        evidence.append(f"unmodelled label(s): {', '.join(unmodelled)}")
    evidence.extend(problems or ["no mismatch, no unmeasurable measurement, no harness defect"])

    passed = (
        bool(sidecars)
        and counts["ok"] > 0
        and counts["mismatch"] == 0
        and counts["unmeasurable"] == 0
        and not unmodelled
        and not problems
    )
    detail = (
        f"matched={counts['ok']} mismatched={counts['mismatch']} "
        f"unmeasurable={counts['unmeasurable']} unmodelled={len(unmodelled)} "
        f"not_yet={sum(not_yet.values())}"
    )
    if not sidecars:
        detail = "the corpus is empty: a gate that compares nothing is a failure, not a pass"
    elif counts["ok"] == 0:
        detail = f"nothing was compared at this phase: {detail}"
    return GateResult(
        name="L1",
        passed=passed,
        detail=detail,
        evidence=tuple(evidence),
        data={
            "matched": counts["ok"],
            "mismatched": counts["mismatch"],
            "unmeasurable": counts["unmeasurable"],
            "unmodelled": len(unmodelled),
            "not_yet": dict(sorted(not_yet.items())),
            "sidecars": len(sidecars),
            "phase": phase,
            "unmodelled_ids": tuple(unmodelled),
            "mismatches": tuple(mismatches),
        },
    )


# ---------------------------------------------------- the no-silent-drop gate


@dataclass(frozen=True)
class Hole:
    """A byte range the regions do not account for exactly once.

    ``kind`` is ``unaccounted`` (no region covers it) or ``overlap`` (two regions claim it).
    """

    kind: str
    start: int
    end: int

    def __str__(self) -> str:
        return f"{self.kind} bytes {self.start}..{self.end}"


def holes(regions: Iterable[Region], total_bytes: int) -> list[Hole]:
    """Every byte range ``regions`` fail to account for exactly once (D9 no-silent-drop).

    A single left-to-right sweep: each region must start where the previous one ended (a
    later start is an ``unaccounted`` hole, an earlier one an ``overlap``), and the last
    region must reach the end of the message. Pure over its inputs, so a test can hand it a
    mutated region list -- the two mutation checks in ``tests/test_no_silent_drop.py``.
    """
    ordered = sorted(regions, key=lambda region: (region.span.offset, region.span.end))
    found: list[Hole] = []
    position = 0
    for region in ordered:
        start, end = region.span.offset, region.span.end
        if start > position:
            found.append(Hole("unaccounted", position, start))
            position = start
        elif start < position:
            found.append(Hole("overlap", start, min(position, end)))
            position = max(position, end)
            continue
        position = end
    if position < total_bytes:
        found.append(Hole("unaccounted", position, total_bytes))
    return found


def _fixture_paths(root: Path | str) -> list[Path]:
    base = Path(root)
    return sorted(
        (path for path in base.rglob("*.eml") if "real" not in path.relative_to(base).parts),
        key=lambda path: path.relative_to(base).as_posix(),
    )


def no_silent_drop_gate(root: Path | str = DEFAULT_FIXTURES) -> GateResult:
    """Every byte of every fixture accounted for exactly once (D9), over the walker's regions.

    Runs on all fixtures (generated, raw and time), including ``preamble_epilogue``,
    ``truncated_base64`` and ``malformed_mime``. The gate also proves its own sensitivity
    in-process -- a dropped region and an overlapped region are both shown to be detected on
    a sample fixture -- so a caller reading the table sees the check can fail, not just that
    it passed.
    """
    fixtures = _fixture_paths(root)
    if not fixtures:
        return GateResult(
            name="no-silent-drop",
            passed=False,
            detail="no fixture to account for: a gate that compares nothing is a failure",
        )

    problems: list[str] = []
    total_bytes = 0
    for path in fixtures:
        raw = path.read_bytes()
        total_bytes += len(raw)
        try:
            result = walk(EmlContainer(raw))
        except Exception as error:  # noqa: BLE001 -- reported as an unaccounted fixture
            problems.append(f"{path.stem}: walking raised {type(error).__name__}: {error}")
            continue
        found = holes(result.regions, len(raw))
        problems.extend(f"{path.stem}: {hole}" for hole in found)

    mutations = _mutation_checks(fixtures[0])
    details = []
    if not mutations["dropped_region"]:
        details.append("dropping a region was NOT detected")
    if not mutations["overlap"]:
        details.append("an overlapped region was NOT detected")
    problems.extend(details)

    passed = not problems
    mutations_passed = all(mutations.values())
    evidence = (
        f"accounted {total_bytes} byte(s) over {len(fixtures)} fixture(s)",
        f"mutation checks: dropped-region={mutations['dropped_region']} overlap={mutations['overlap']}",
    )
    evidence += tuple(problems) if problems else ("every byte in exactly one region",)
    return GateResult(
        name="no-silent-drop",
        passed=passed,
        detail=(
            f"fixtures={len(fixtures)} bytes={total_bytes} "
            f"mutation-checks={'pass' if mutations_passed else 'FAIL'}"
        ),
        evidence=evidence,
        data={
            "fixtures": len(fixtures),
            "bytes": total_bytes,
            "holes": len(problems),
            "mutations": dict(mutations),
        },
    )


def _mutation_checks(sample: Path) -> dict[str, bool]:
    """Prove, on one fixture, that a dropped region and an overlap are both caught."""
    raw = sample.read_bytes()
    regions: list[Region] = list(walk(EmlContainer(raw)).regions)
    if len(regions) < 2:
        return {"dropped_region": False, "overlap": False}
    dropped = regions[1:]
    duplicated = [regions[0], *regions]
    return {
        "dropped_region": bool(holes(dropped, len(raw))),
        "overlap": bool(holes(duplicated, len(raw))),
    }
