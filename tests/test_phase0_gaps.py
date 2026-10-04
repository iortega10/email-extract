"""The known-gap registry is a closed vocabulary, and ``docs/design/phase0-gaps.md`` is it.

Turn 0.6 resolves the design's "Known-gap ids (v1 registry)" into one entry per id (81 listed,
two pruned, 79 in force). This test is that resolution's enforcement, and it runs the
correspondence **both ways** so neither side can drift:

* (a) every id in the design document's registry has an entry in ``phase0-gaps.md``, and every
  entry is in the registry -- no invented id, no renamed one, no two merged into one;
* (b) every gap id the walker can emit (the ``GAP_*`` constants in ``emailextract/walk.py``, read
  off the module through :data:`WALKER_GAPS`) is documented;
* (c) every gap id a committed sidecar names is documented. A sidecar names a gap id in a
  ``part.gaps`` row, in a ``gaps.later`` row, or as the **subject** of a ``labels.undetermined``
  entry whose first element is not a fact the oracle models. The failure message names each id
  that is not documented, so a sidecar naming an id outside the registry is a *finding*, reported
  and never silently added;
* (d) every id the contracts can emit is documented: the closed unknown reasons in
  ``emailextract/siblings.py`` and any reason id a contract constant names;
* (e) every gap id in the falsifiability catalogue (``emailextract/evals/falsify.py``) is
  documented.

The registry's own ids are read from the design document's registry section, so the two documents
are held to each other rather than to a literal copied here. The **pruned** pair
(``attach.size_cap_hit``, ``attach.nesting_cap_hit``) is asserted absent from both sides: a prune
that quietly came back would be caught.

Status reasons are **not** gap ids: the D6 reasons live in ``model.REASON_TABLE`` and are checked
by ``tests/test_status_reasons.py``, not here.
"""

from __future__ import annotations

import re
from pathlib import Path

from emailextract import container, ids, model, siblings, store, timeevent, walk as walk_module
from emailextract.evals.falsify import CASES, WALKER_GAPS
from emailextract.evals.l1 import FACTS
from emailextract.evals.labels import load_sidecars
from emailextract import seam

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "docs" / "design" / "email-extraction-design.md"
GAPS_DOC = ROOT / "docs" / "design" / "phase0-gaps.md"

#: The candidate pair the design flagged and Turn 0.6 pruned (they duplicated the ``skipped``
#: reasons). They must appear on the "documented" side of nothing: not in the registry, not here.
PRUNED = {"attach.size_cap_hit", "attach.nesting_cap_hit"}

#: A gap id is ``<family>.<name>`` -- lowercase, dotted. The same shape the registry uses.
_GAP_ID = re.compile(r"^[a-z]+\.[a-z0-9_]+$")
#: A family bullet in the registry: ``- **headers**: ...`` (or ``- **msg** (Revision 2): ...``)
#: plus its indented continuation lines.
_FAMILY_BULLET = re.compile(r"^- \*\*([a-z]+)\*\*")
_BACKTICKED = re.compile(r"`([^`]+)`")
#: An entry is a level-three heading whose whole text is one backticked id.
_ENTRY = re.compile(r"^### `([^`]+)`$", re.MULTILINE)

#: The library modules whose module-level constants could name a reason or a gap id.
_LIBRARY = (container, ids, model, seam, siblings, store, timeevent, walk_module)


def _registry_section() -> str:
    """The design document's "Known-gap ids" section, heading line excluded."""
    text = DESIGN.read_text(encoding="utf-8")
    start = text.index("## Known-gap ids")
    start = text.index("\n", start) + 1  # skip the heading line, whose own backticks name this file
    end = text.index("\n## ", start)
    return text[start:end]


def registry_ids() -> set[str]:
    """The ids the design document's registry lists, as ``family.name``, verbatim.

    The registry's bullets are ``- **family**: name, name, ...`` with the family name in bold and
    the member names bare, so a member is qualified with its bullet's family here. Only the family
    bullets are read: the trailing prune note (which names the pruned ids in plain text) cannot leak
    them back in.
    """
    ids_found: set[str] = set()
    family: str | None = None
    for line in _registry_section().splitlines():
        bullet = _FAMILY_BULLET.match(line)
        if bullet:
            family = bullet.group(1)
        elif not (line[:1] in (" ", "\t") and family is not None):
            family = None  # a non-indented line that is not a bullet ends the family
        if family is not None:
            ids_found.update(f"{family}.{name}" for name in _BACKTICKED.findall(line))
    return ids_found


def documented_ids() -> set[str]:
    """The ids ``phase0-gaps.md`` gives an entry to."""
    return set(_ENTRY.findall(GAPS_DOC.read_text(encoding="utf-8")))


def sidecar_gap_ids() -> dict[str, set[str]]:
    """gap id -> the sidecar stems that name it (``part.gaps`` / ``gaps.later`` / undetermined).

    ``part.gaps`` rows are ``[part, [gap_id, ...]]``; ``gaps.later`` rows are
    ``[gap_id, locator, phase, reason]``; a ``labels.undetermined`` entry whose first element is not
    a fact the oracle models names a gap id.
    """
    found: dict[str, set[str]] = {}

    def record(gap_id: object, stem: str) -> None:
        if isinstance(gap_id, str):
            found.setdefault(gap_id, set()).add(stem)

    for stem, sidecar in load_sidecars().items():
        part_gaps = sidecar.facts.get("part.gaps")
        if part_gaps is not None and isinstance(part_gaps.value, list):
            for _part, gaps in part_gaps.value:
                for gap_id in gaps:
                    record(gap_id, stem)
        later = sidecar.facts.get("gaps.later")
        if later is not None and isinstance(later.value, list):
            for row in later.value:
                record(row[0], stem)
        undetermined = sidecar.facts.get("labels.undetermined")
        if undetermined is not None and isinstance(undetermined.value, list):
            for row in undetermined.value:
                if row[0] not in FACTS:  # a fact the oracle models is not a gap id
                    record(row[0], stem)
    return found


def _strings_in(value: object) -> set[str]:
    """Every string a module-level constant holds, at one level of nesting."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, (tuple, list, set, frozenset)):
        return {item for item in value if isinstance(item, str)}
    if isinstance(value, dict):
        return {item for item in value.values() if isinstance(item, str)}
    return set()


def contract_gap_ids() -> dict[str, str]:
    """gap id -> the constant that names it, over every library module's module-level constants."""
    found: dict[str, str] = {}
    for module in _LIBRARY:
        for name, value in vars(module).items():
            for token in _strings_in(value):
                if _GAP_ID.match(token) and token.split(".")[0] in _families():
                    found.setdefault(token, name)
    return found


def _families() -> set[str]:
    return {gap_id.split(".")[0] for gap_id in registry_ids()}


def test_the_registry_and_the_document_agree_both_ways() -> None:
    """(a) The registry's ids and the document's entries are the same set, and it is not empty."""
    registry = registry_ids()
    entries = documented_ids()
    assert len(registry) > 70, "the known-gap registry could not be read from the design document"
    assert registry == entries, (
        f"registry ids with no entry: {sorted(registry - entries)}; "
        f"entries with no registry id: {sorted(entries - registry)}"
    )


def test_the_registry_in_force_is_79_ids_and_the_prune_holds() -> None:
    """The count: the design listed 81; Turn 0.6 pruned two, so 79 are in force.

    A change here is a deliberate registry change, not a drift, and it has to be made on purpose.
    """
    registry = registry_ids()
    assert len(registry) == 79, sorted(registry)
    assert documented_ids() == registry
    assert PRUNED.isdisjoint(registry), sorted(PRUNED & registry)
    assert PRUNED.isdisjoint(documented_ids()), sorted(PRUNED & documented_ids())
    # The design document still *states* the prune (append-only reasoning), so a reader is told why.
    design = DESIGN.read_text(encoding="utf-8")
    assert "pruned from this registry" in design


def test_every_walker_gap_is_documented() -> None:
    """(b) Every ``GAP_*`` constant the walker can emit has an entry."""
    entries = documented_ids()
    undocumented = sorted(set(WALKER_GAPS) - entries)
    assert not undocumented, f"walker gaps with no entry: {undocumented}"


def test_every_sidecar_gap_id_is_documented() -> None:
    """(c) A sidecar's gap ids are all documented; the failure names any that is not."""
    entries = documented_ids()
    emitted = sidecar_gap_ids()
    assert emitted, "no sidecar names a gap id: this test would be vacuous"
    undocumented = sorted(set(emitted) - entries)
    assert not undocumented, (
        "a committed sidecar names a gap id no entry documents (report it; do not add it to the "
        f"registry silently): {undocumented} -- from "
        f"{ {gap: sorted(stems) for gap, stems in emitted.items() if gap in undocumented} }"
    )


def test_every_contract_gap_id_is_documented() -> None:
    """(d) The closed sibling reasons and every dotted reason id a constant names are documented."""
    entries = documented_ids()
    from_constants = contract_gap_ids()
    for reason_id in siblings.CITATION_UNKNOWN_REASONS:
        assert reason_id in entries, f"{reason_id} is emitted by the contracts but is not documented"
    undocumented = sorted(set(from_constants) - entries)
    assert not undocumented, (
        f"a contract constant names an undocumented gap id: "
        f"{ {gap: from_constants[gap] for gap in undocumented} }"
    )


def test_the_falsifiability_ids_are_documented() -> None:
    """(e) Every gap id ``evals/falsify.py`` defends is documented."""
    entries = documented_ids()
    assert len(CASES) == len(WALKER_GAPS), sorted(CASES)
    undocumented = sorted(set(CASES) - entries)
    assert not undocumented, f"falsifiability cases for undocumented gaps: {undocumented}"


def test_the_check_would_catch_an_undocumented_id() -> None:
    """The mechanism: a planted id is a non-empty difference, not a pass."""
    entries = documented_ids()
    planted = {"body.brand_new_refusal", "body.no_boundary_found"}
    assert planted - entries == {"body.brand_new_refusal"}
