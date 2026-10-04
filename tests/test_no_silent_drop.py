"""No-silent-drop (design D9, build spec Turn 0.4): every input byte accounted for exactly once.

The invariant: in every fixture, each byte lies in exactly one accounted region -- a part's
headers, a body, a delimiter, the preamble or the epilogue -- and the regions neither overlap
nor leave a gap. The gate runs over all 16 fixtures, including the three that stress it
(``preamble_epilogue``, ``truncated_base64`` and ``malformed_mime``).

Two mutation checks prove the gate can fail: dropping one accounted region and duplicating
(widening) one both go unaccounted, and the failure names the fixture and the byte range. The
gate performs both in-process (``GateResult.data["mutations"]``); the tests here also drive
them through :func:`holes` directly and through a monkeypatched walker.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402

from emailextract.container import EmlContainer  # noqa: E402
from emailextract.evals import gates  # noqa: E402
from emailextract.evals.gates import Hole, holes, no_silent_drop_gate  # noqa: E402
from emailextract.walk import walk  # noqa: E402

FIXTURES = sidecar_copy.FIXTURES

NAMED = ["preamble_epilogue", "truncated_base64", "malformed_mime"]


def test_every_committed_fixture_accounts_for_every_byte() -> None:
    gate = no_silent_drop_gate()
    assert gate.passed is True, gate.lines()
    assert gate.data["fixtures"] == 46
    assert gate.data["bytes"] == 25729
    # The gate proves its own sensitivity: a dropped region and an overlap are both detected.
    assert gate.data["mutations"] == {"dropped_region": True, "overlap": True}


@pytest.mark.parametrize("stem", NAMED)
def test_the_named_fixtures_tile_with_no_hole(stem: str) -> None:
    path = _find(stem)
    raw = path.read_bytes()
    result = walk(EmlContainer(raw))
    assert holes(result.regions, len(raw)) == []


def test_dropping_a_region_leaves_the_range_unaccounted() -> None:
    raw = _find("plain_simple").read_bytes()
    regions = walk(EmlContainer(raw)).regions
    dropped = [region for region in regions if region.kind != "body"]
    found = holes(dropped, len(raw))
    assert found == [Hole("unaccounted", 246, 295)], found
    assert str(found[0]) == "unaccounted bytes 246..295"


def test_a_duplicated_region_is_an_overlap() -> None:
    raw = _find("plain_simple").read_bytes()
    regions = walk(EmlContainer(raw)).regions
    found = holes([regions[0], *regions], len(raw))
    assert found, "a duplicated region must be an overlap"
    assert all(hole.kind == "overlap" for hole in found), found


def test_a_widened_region_is_an_overlap() -> None:
    raw = _find("plain_simple").read_bytes()
    regions = walk(EmlContainer(raw)).regions
    first = regions[0]
    widened = [
        dataclasses.replace(first, span=dataclasses.replace(first.span, length=first.span.length + 1)),
        *regions[1:],
    ]
    found = holes(widened, len(raw))
    assert any(hole.kind == "overlap" for hole in found), found


def test_the_gate_names_a_fixture_and_a_range_when_a_region_vanishes(monkeypatch) -> None:
    """A walker that drops the body regions fails the gate, naming the fixture and the range."""
    real = gates.walk

    def dropping(container):
        result = real(container)
        return dataclasses.replace(
            result, regions=[region for region in result.regions if region.kind != "body"]
        )

    monkeypatch.setattr(gates, "walk", dropping)
    gate = no_silent_drop_gate()
    assert gate.passed is False
    assert any("unaccounted bytes" in line for line in gate.evidence), gate.evidence
    assert any("plain_simple" in line for line in gate.evidence), gate.evidence


def _find(stem: str) -> Path:
    for directory in ("generated", "raw", "time"):
        path = FIXTURES / directory / f"{stem}.eml"
        if path.exists():
            return path
    raise AssertionError(f"no fixture {stem!r}")
