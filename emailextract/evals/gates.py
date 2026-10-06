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

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Mapping

from ..container import EmlContainer
from ..walk import Region, walk
from .l1 import (
    CURRENT_PHASE,
    FACTS,
    LIVE_GAP_IDS,
    OracleError,
    Status,
    check,
    emitted_gap_ids,
)
from .labels import DEFAULT_FIXTURES, LabelError, Sidecar, load_sidecars

__all__ = [
    "COUNTED",
    "GateResult",
    "Hole",
    "PHASE1_EXIT_LEDGER",
    "PHASE1_EXIT_PHASE",
    "gap_gate",
    "holes",
    "l1_gate",
    "load_phase1_exit",
    "no_silent_drop_gate",
    "phase1_exit",
    "wait_key",
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


# ---------------------------------------------------------- the phase-1 gap gate


def _is_committed_corpus(root: Path | str) -> bool:
    """Whether ``root`` is the committed fixture corpus the phase-1 exit criteria are stated over.

    A caller may report on another corpus (``--root``, a reviewer's subset). There the
    *completeness* rules -- does the corpus exercise the named rows, does it label any live gap at
    all -- are reported but not fatal, because a subset legitimately carries neither. Every rule
    about a row that **waits** or an emission that was **dropped** is fatal everywhere.
    """
    try:
        return Path(root).resolve() == Path(DEFAULT_FIXTURES).resolve()
    except OSError:  # pragma: no cover -- an unresolvable path is simply not the committed corpus
        return False


def gap_gate(root: Path | str = DEFAULT_FIXTURES) -> GateResult:
    """Turn 1.10a: every phase-1 gap a sidecar labels is one the code records.

    The set of *emittable* phase-1 ids lives in :mod:`emailextract.evals.falsify`
    (``EMITTABLE_GAP_IDS``): the ids the oracle compares (``LIVE_GAP_IDS``) plus the three the quote
    stage emits but the frozen labels cannot satisfy. This gate is the check that the code actually
    records each id its sidecars label at a **live** phase-1 row -- read through
    :func:`~emailextract.evals.l1.emitted_gap_ids`, the public seam, never a private walk.

    It **fails**:

    * when a labelled live phase-1 row's id is not recorded (a dropped emission, which the Turn 1.10a
      mutation catalogue proves detectable, naming the fact, the id, the locator and the fixture);
    * when the corpus exercises none of the live ids (a corpus that proves nothing);
    * when the corpus is empty.

    It reports -- never fails on -- the **unlabelled emissions** (a live id the code emits that no
    sidecar labels: ``body.html_quote_rule_gap`` today) and the fixtures it must skip, so neither is
    silently counted as agreed.
    """
    name = "phase-1 gaps"
    try:
        sidecars = load_sidecars(root)
    except LabelError as error:
        return GateResult(
            name=name,
            passed=False,
            detail="the labels could not be loaded, so no gap was checked",
            evidence=(str(error),),
        )
    if not sidecars:
        return GateResult(
            name=name,
            passed=False,
            detail="the corpus is empty: a gate that compares nothing is a failure, not a pass",
            evidence=("no sidecar was found under the corpus root",),
        )

    problems: list[str] = []
    skipped: list[str] = []
    exercised = 0
    labelled_all: set[str] = set()
    emitted_all: set[str] = set()
    for stem, sidecar in sorted(sidecars.items()):
        fact = sidecar.facts.get("gaps.later")
        rows = [
            (row[0], row[1], row[2])
            for row in (fact.value if fact is not None else [])
            if isinstance(row, list) and len(row) >= 3
        ]
        labelled_all |= {row[0] for row in rows}
        try:
            emitted = emitted_gap_ids(sidecar)
        except OracleError as error:
            skipped.append(f"skipped {stem}: {error}")
            continue
        emitted_all |= emitted
        for gap_id, locator, phase in rows:
            if phase != 1 or gap_id not in LIVE_GAP_IDS:
                continue
            exercised += 1
            if gap_id not in emitted:
                problems.append(
                    f"{stem}: gaps.later {gap_id} at {locator} is labelled but the code recorded "
                    "no such gap"
                )

    unlabelled = sorted(emitted_all - labelled_all)
    evidence = [
        f"{exercised} live phase-1 gap label(s) over {len(sidecars)} sidecar(s)"
    ]
    if unlabelled:
        evidence.append("unlabelled emissions (the code emits them, no sidecar labels them):")
        evidence.extend(f"  {gap_id}" for gap_id in unlabelled)
    evidence.extend(problems)
    evidence.extend(skipped)
    if not problems and not unlabelled and not skipped:
        evidence.append("every labelled live phase-1 gap is recorded")

    passed = not problems and (exercised > 0 or not _is_committed_corpus(root))
    if exercised == 0 and _is_committed_corpus(root):
        detail = "the corpus exercises none of the live phase-1 gap ids: nothing was checked"
    else:
        detail = (
            f"checked {exercised} live phase-1 gap label(s); {len(problems)} not recorded; "
            f"{len(unlabelled)} unlabelled emission(s); skipped {len(skipped)}"
        )
    return GateResult(
        name=name,
        passed=passed,
        detail=detail,
        evidence=tuple(evidence),
        data={
            "exercised": exercised,
            "sidecars": len(sidecars),
            "problems": len(problems),
            "unlabelled": tuple(unlabelled),
            "skipped": len(skipped),
        },
    )


# ------------------------------------------------------ the phase-1 exit gate
#: Turn 1.10a: the committed, closed set of **phase-1 waits** -- the ``tests/ledger/phase1_exit.json``
#: rows, each a row a frozen sidecar asserts but no emission can satisfy (class ``b``) together with
#: its reason and the bytes that evidence it. Resolved from the repository root (the same way
#: :mod:`tools` resolves its ledgers) so ``python -m emailextract.evals`` finds it in a fresh clone.
PHASE1_EXIT_LEDGER: Final[Path] = (
    Path(__file__).resolve().parents[2] / "tests" / "ledger" / "phase1_exit.json"
)

#: The phase whose exit is being accounted for. Phase 1 = the RFC 822 parser, the axe the design
#: closes here; phase 3 (time and thread) is still deferred and not this gate's business.
PHASE1_EXIT_PHASE: Final[int] = 1

#: A wait row's identity: ``(fixture stem, fact id, gap id, locator)``. ``gap_id``/``locator`` are
#: empty for a wait on a fact other than ``gaps.later`` (which is the only per-row fact).
WaitKey = tuple[str, str, str, str]


def load_phase1_exit(path: str | Path | None = None) -> list[dict[str, Any]]:
    """The phase-1 exit ledger's ``wait`` rows, as written on disk."""
    ledger_path = Path(path) if path is not None else PHASE1_EXIT_LEDGER
    loaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    rows = loaded.get("wait")
    if not isinstance(rows, list):
        raise ValueError("the phase-1 exit ledger must carry a 'wait' list")
    return [dict(row) for row in rows]


def wait_key(row: Mapping[str, Any]) -> WaitKey:
    """The :data:`WaitKey` a ledger row or an observed wait is identified by."""
    return (
        str(row["fixture"]),
        str(row["fact"]),
        str(row.get("gap_id") or ""),
        str(row.get("locator") or ""),
    )


def _describe_wait(row: WaitKey) -> str:
    """One wait row as the reviewer reads it: ``fixture: gap at locator`` (or ``fixture: fact``)."""
    stem, fact, gap_id, locator = row
    if gap_id or locator:
        return f"{stem}: {gap_id or fact} at {locator}"
    return f"{stem}: {fact}"


def _observed_waits(
    sidecars: Mapping[str, Sidecar],
) -> tuple[dict[WaitKey, str], list[str], int]:
    """Every phase-1 wait the committed corpus actually carries, as ``(waits, problems, compared)``.

    Two sources, in the order the fact design gives them:

    * a ``gaps.later`` **label row** whose phase column is :data:`PHASE1_EXIT_PHASE` and whose gap id
      is outside :data:`~emailextract.evals.l1.LIVE_GAP_IDS` -- the row is neither compared (it is
      not live) nor deferred to a later phase (its own phase column says 1), so it waits;
    * any other outcome ``not_yet`` at :data:`PHASE1_EXIT_PHASE` -- a phase-1 fact with no measurer.
      A ``gaps.later`` outcome is excluded here: its per-row accounting is the first source.

    ``problems`` names a sidecar the ``check`` harness refuses (an unmodelled fact id, a phase
    disagreement) and ``compared`` counts the outcomes that were actually measured, so a vacuous
    corpus cannot pass by having nothing to say.
    """
    waits: dict[WaitKey, str] = {}
    problems: list[str] = []
    compared = 0
    for stem, sidecar in sorted(sidecars.items()):
        gaps = sidecar.facts.get("gaps.later")
        if gaps is not None and isinstance(gaps.value, list):
            for row in gaps.value:
                if not (isinstance(row, list) and len(row) >= 3):
                    continue
                gap_id, locator, phase = row[0], row[1], row[2]
                if phase != PHASE1_EXIT_PHASE or gap_id in LIVE_GAP_IDS:
                    continue
                waits[(stem, "gaps.later", str(gap_id), str(locator))] = f"{gap_id} at {locator}"
        try:
            report = check(sidecar)
        except OracleError as error:
            problems.append(f"{stem}: {error}")
            continue
        compared += report.compared
        for outcome in report.outcomes:
            if outcome.status is not Status.NOT_YET or outcome.fact_id == "gaps.later":
                continue
            if outcome.phase == PHASE1_EXIT_PHASE:
                waits[(stem, outcome.fact_id, "", "")] = outcome.detail or "no measurer"
    return waits, problems, compared


def phase1_exit(
    root: Path | str = DEFAULT_FIXTURES,
    *,
    ledger: str | Path | None = None,
    named: frozenset[WaitKey] | None = None,
) -> GateResult:
    """The Phase 1 exit, accounting for every phase-1 wait by name (build spec, Exit criteria).

    A phase-1 fact that is not measured is a **wait**, and the exit criterion is that the wait is
    *exactly* a closed, named, committed set: :data:`PHASE1_EXIT_LEDGER` (class ``b`` rows -- a frozen
    sidecar asserting a row no emission can satisfy, each carrying its reason and the bytes that
    evidence it; see the Turn 1.10a finding in :data:`~emailextract.evals.l1.LIVE_GAP_IDS`). Today
    that set is the six rows of :data:`~emailextract.evals.l1.LIVE_GAP_IDS`'s over-emission and
    no-emission findings; every other phase-1 fact is measured.

    The gate **fails**:

    * when a row waits that the named set does not carry (``extra``) -- the gates-must-fail half,
      which re-adding a live id exercises;
    * when a named row no longer waits (``missing``) -- vacuity, the corpus stopped exercising it;
    * when the corpus is empty, or when it compared nothing at all (rule 10: a gate that accounts
      for nothing is a failure, not a pass);
    * when a sidecar names a fact the oracle does not model or the phases disagree (a harness defect
      is caught, not raised).

    ``named`` (the ledger path) and ``ledger`` (a pre-loaded key set) are keywords so a test can hand
    the gate another set -- the accounting is by name, not by a count that would accept any row.
    """
    name = "phase1 exit"
    try:
        sidecars = load_sidecars(root)
    except LabelError as error:
        return GateResult(
            name=name,
            passed=False,
            detail="the labels could not be loaded, so nothing was accounted for",
            evidence=(str(error),),
        )
    if not sidecars:
        return GateResult(
            name=name,
            passed=False,
            detail="the corpus is empty: a gate that accounts for nothing is a failure, not a pass",
            evidence=("no sidecar was found under the corpus root",),
        )
    if named is None:
        try:
            named = frozenset(wait_key(row) for row in load_phase1_exit(ledger))
        except (OSError, ValueError, KeyError) as error:
            return GateResult(
                name=name,
                passed=False,
                detail="the phase-1 exit ledger could not be read, so the named set is unknown",
                evidence=(f"{type(error).__name__}: {error}",),
            )

    waits, problems, compared = _observed_waits(sidecars)
    extra = sorted(set(waits) - set(named))
    missing = sorted(set(named) - set(waits))

    evidence = [
        f"phase-1 wait row(s): {len(waits)} (named {len(named)}), over {len(sidecars)} sidecar(s); "
        f"{compared} fact(s) compared"
    ]
    evidence.extend(f"  {_describe_wait(row)}" for row in sorted(waits))
    if extra:
        evidence.append("phase-1 wait row(s) the named set does not carry:")
        evidence.extend(f"  {_describe_wait(row)}" for row in extra)
    if missing:
        evidence.append("named row(s) the corpus no longer waits on:")
        evidence.extend(f"  {_describe_wait(row)}" for row in missing)
    evidence.extend(problems)
    if not problems and not extra and not missing:
        evidence.append("the phase-1 wait is exactly the named, committed set")

    passed = (
        compared > 0 and not problems and not extra and not (missing and _is_committed_corpus(root))
    )
    if compared == 0:
        detail = "the corpus compared nothing: a gate that accounts for nothing is a failure"
    elif missing and not _is_committed_corpus(root):
        detail = (
            f"wait={len(waits)} (named={len(named)}), compared={compared}; extra={len(extra)} "
            f"(a subset corpus: {len(missing)} named row(s) are not carried here)"
        )
    else:
        detail = (
            f"wait={len(waits)} (named={len(named)}), compared={compared}; "
            f"extra={len(extra)} missing={len(missing)}"
        )
    return GateResult(
        name=name,
        passed=passed,
        detail=detail,
        evidence=tuple(evidence),
        data={
            "phase": PHASE1_EXIT_PHASE,
            "wait": tuple(sorted(waits)),
            "named": tuple(sorted(named)),
            "extra": tuple(extra),
            "missing": tuple(missing),
            "compared": compared,
            "sidecars": len(sidecars),
        },
    )
