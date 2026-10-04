"""The sidecar loader: hand-typed labels, read without the library.

A *sidecar* is ``<fixture>.expected.json``, sitting next to the fixture it
describes (``plain_simple.eml`` / ``plain_simple.expected.json``), and the labels
in it were typed by hand from the design documents and the fixture's declared
shape -- never read out of ``emailextract``. That is the whole point (D11): the
labels are the independent side of the comparison, so this module must not
import the package it exists to check. Nothing here imports ``emailextract``
(or ``emailextract.walk``, ``emailextract.model``, ``email``); the only imports
are the standard library, and ``tests/test_labels.py`` proves it by loading this
file in a bare interpreter.

The loader is deliberately fact-id agnostic: it knows a fact is
``"<family>.<name>"`` with a phase and a value, not which facts exist. The
registry that decides what a fact *means* and at which phase it becomes
checkable lives in :mod:`emailextract.evals.l1` (Turn 0.4), so a label that no
oracle models is refused there, loudly, instead of being silently skipped.

Provenance tokens are ``human | generator | spec`` (the sibling's token set;
the build spec's ``hand`` wording is a documented discrepancy -- see the Turn 0.3
report). ``spec`` means a model typed the label from the design rules and the
fixture's declared shape, which is what every label in this repository is.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Mapping

#: A sidecar is found by this suffix, next to the fixture.
SIDECAR_SUFFIX = ".expected.json"

#: Where the labels came from. ``human`` and ``spec`` are typed by hand;
#: ``generator`` says the generator's own specification fixed the value. No
#: sidecar in this repository claims ``human`` (tests/test_labels.py).
PROVENANCES: tuple[str, ...] = ("human", "generator", "spec")

#: A fixture the corpus knows about (Turn 0.3: ``.eml`` only; ``.msg`` arrives in
#: Phase 1b).
FIXTURE_SUFFIXES: tuple[str, ...] = (".eml",)

REQUIRED_KEYS: tuple[str, ...] = ("fixture", "labels_provenance", "facts")
OPTIONAL_KEYS: tuple[str, ...] = ("annotations",)
FACT_KEYS: tuple[str, ...] = ("phase", "value")

#: ``<family>.<name>``: a family from the gap registry and a snake_case name. The
#: loader does not check the family against the registry (that is ``l1``'s job
#: for the facts it models), only that a fact id is shaped like one.
FACT_ID = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

#: ``fixtures/`` at the repository root, from this file
#: (``emailextract/evals/labels.py``).
DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


class LabelError(ValueError):
    """A sidecar that cannot be trusted as a label.

    Every failure is this one type so a caller can report "the labels are
    malformed" instead of crashing on a ``KeyError`` deep in a comparison: a
    malformed label is a defect in the labels, not a mismatch to be counted.
    """


@dataclasses.dataclass(frozen=True)
class Fact:
    """One labelled fact: what the sidecar claims about the fixture, and from which phase on."""

    id: str
    phase: int
    value: Any


@dataclasses.dataclass(frozen=True)
class Sidecar:
    """A loaded sidecar and the fixture it is about."""

    path: Path
    artifact: Path
    fixture: str
    labels_provenance: str
    facts: Mapping[str, Fact]
    annotations: Mapping[str, Any]

    @property
    def stem(self) -> str:
        """The key the corpus uses: the fixture stem, sidecar suffix stripped."""
        return self.artifact.stem

    def phase_facts(self, phase: int) -> Mapping[str, Fact]:
        """The facts that claim to be checkable at exactly ``phase``."""
        return {fact.id: fact for fact in self.facts.values() if fact.phase == phase}


def sidecar_paths(root: Path | str = DEFAULT_FIXTURES) -> list[Path]:
    """Every sidecar under ``root``, in a stable order (relative posix path)."""
    base = Path(root)
    return sorted(
        (path for path in base.rglob("*") if path.is_file() and path.name.endswith(SIDECAR_SUFFIX)),
        key=lambda path: path.relative_to(base).as_posix(),
    )


def load_sidecar(path: Path | str) -> Sidecar:
    """Load and validate one sidecar, and the fixture it points at."""
    sidecar_path = Path(path)
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError as error:
        raise LabelError(f"{sidecar_path}: cannot be read ({error})") from error
    payload = _parse(sidecar_path, text)

    unknown = sorted(set(payload) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise LabelError(
            f"{sidecar_path}: unknown top-level key(s) {unknown} -- a sidecar's keys are exactly "
            f"{list(REQUIRED_KEYS)} and optionally {list(OPTIONAL_KEYS)}"
        )
    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise LabelError(f"{sidecar_path}: missing top-level key(s) {missing}")

    fixture = _string(sidecar_path, "fixture", payload["fixture"])
    provenance = payload["labels_provenance"]
    if provenance not in PROVENANCES:
        raise LabelError(
            f"{sidecar_path}: labels_provenance {provenance!r} is not one of {list(PROVENANCES)}"
        )

    artifact = sidecar_path.parent / fixture
    if not artifact.exists():
        raise LabelError(
            f"{sidecar_path}: names the fixture {fixture!r}, which does not exist beside it "
            f"({artifact}) -- a label about a fixture that is not there cannot be checked"
        )
    if artifact.is_file() and artifact.suffix.lower() not in FIXTURE_SUFFIXES:
        raise LabelError(
            f"{sidecar_path}: the fixture {fixture!r} has an unknown suffix -- expected one of "
            f"{list(FIXTURE_SUFFIXES)}"
        )

    facts = _facts(sidecar_path, payload["facts"])
    annotations = payload.get("annotations", {})
    if not isinstance(annotations, dict):
        raise LabelError(f"{sidecar_path}: annotations: {annotations!r} is not an object")
    return Sidecar(
        path=sidecar_path,
        artifact=artifact,
        fixture=fixture,
        labels_provenance=provenance,
        facts=facts,
        annotations=dict(annotations),
    )


def load_sidecars(root: Path | str = DEFAULT_FIXTURES) -> dict[str, Sidecar]:
    """Every sidecar under ``root``, keyed by fixture stem.

    Two sidecars for the same stem (``a/x.expected.json`` and
    ``b/x.expected.json``) would make "the labels for x" ambiguous, so it is
    refused rather than resolved by directory order.
    """
    loaded: dict[str, Sidecar] = {}
    for path in sidecar_paths(root):
        sidecar = load_sidecar(path)
        if sidecar.stem in loaded:
            raise LabelError(
                f"{path}: {sidecar.stem!r} is already labelled by {loaded[sidecar.stem].path} -- "
                "one fixture, one sidecar"
            )
        loaded[sidecar.stem] = sidecar
    return loaded


def _parse(path: Path, text: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(text, object_pairs_hook=_unique)
    except json.JSONDecodeError as error:
        raise LabelError(f"{path}: is not valid JSON ({error})") from error
    if not isinstance(payload, dict):
        raise LabelError(f"{path}: a sidecar is a JSON object, not {type(payload).__name__}")
    return payload


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Refuse a repeated key instead of letting JSON keep the last one.

    A duplicated *fact* is the dangerous case: a hand-edited sidecar with two
    entries for the same id would otherwise silently lose one of them, and the
    oracle would report a pass.
    """
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise LabelError(f"duplicate key {key!r} -- a repeated key silently drops a label")
        seen[key] = value
    return seen


def _facts(path: Path, payload: Any) -> dict[str, Fact]:
    if not isinstance(payload, dict):
        raise LabelError(f"{path}: facts: {type(payload).__name__} is not an object")
    if not payload:
        raise LabelError(f"{path}: facts: a sidecar with no facts labels nothing")
    facts: dict[str, Fact] = {}
    for fact_id, raw in payload.items():
        if not isinstance(fact_id, str) or not FACT_ID.match(fact_id):
            raise LabelError(
                f"{path}: fact id {fact_id!r} is not '<family>.<name>' with snake_case parts"
            )
        if not isinstance(raw, dict):
            raise LabelError(f"{path}: facts[{fact_id!r}]: {raw!r} is not an object")
        unknown = sorted(set(raw) - set(FACT_KEYS))
        missing = [key for key in FACT_KEYS if key not in raw]
        if unknown or missing:
            raise LabelError(
                f"{path}: facts[{fact_id!r}]: the keys are exactly {list(FACT_KEYS)} -- "
                f"missing {missing}, unknown {unknown}"
            )
        phase = raw["phase"]
        if isinstance(phase, bool) or not isinstance(phase, int) or phase < 0:
            raise LabelError(
                f"{path}: facts[{fact_id!r}].phase: {phase!r} is not a non-negative int -- "
                "a phase is a number, never a name or a string"
            )
        value = raw["value"]
        if _empty(value):
            raise LabelError(
                f"{path}: facts[{fact_id!r}].value: {value!r} says nothing -- an absent "
                "expectation is not a label"
            )
        facts[fact_id] = Fact(id=fact_id, phase=phase, value=value)
    return facts


def _string(path: Path, key: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise LabelError(f"{path}: {key}: {value!r} is not a non-empty string")
    return value


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
