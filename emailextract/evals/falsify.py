"""Per-gap falsifiability by mutation (design D14, build spec Turn 0.4).

Design D14 asks for a falsifiability case per named gap: a case a **careless implementation
would get wrong**. Unlike the workbook (where phase 0 had no reader, so a case was written
against the oracle's override point), the walker here **exists**, so the case is written
against the walker itself: ``mutated`` monkeypatches exactly **one rule** -- the same shape
as the ledger sensitivity tests -- to do what a careless implementation would, and the claim
is that the L1 gate then **fails** on the sidecar carrying that gap, naming the fact, the gap
id and the fixture.

Six gaps are exercised by a committed fixture today (``malformed_mime``,
``preamble_epilogue``, ``truncated_base64``, ``bad_charset``); the two the sidecars do not
carry (``body.headers_only``, ``body.no_boundary_found``) are proven detectable against
**inline hand-typed bytes** built in the test, so the mutant is still caught without adding
a fixture or editing a sidecar.

The catalogue is keyed by the walker's own ``GAP_*`` constants
(:data:`WALKER_GAPS`), and ``tests/test_gap_falsifiability.py`` holds it against them in both
directions: a walker that gains a gap id with no case here fails, and a case for a gap no
fixture exercises has to carry its own inline bytes.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping

from .. import walk as walk_module
from ..ids import RawSpan
from ..walk import (
    GAP_BODY_BOUNDARY_DISAGREEMENT,
    GAP_BODY_DECODE_DESTROYED_BYTES,
    GAP_BODY_DECODE_FALLBACK_USED,
    GAP_BODY_EPILOGUE_BYTES,
    GAP_BODY_HEADERS_ONLY,
    GAP_BODY_NO_BOUNDARY_FOUND,
    GAP_BODY_PREAMBLE_BYTES,
    GAP_HEADERS_MALFORMED_LINE,
)

__all__ = [
    "CASES",
    "GapCase",
    "WALKER_GAPS",
    "describe",
    "exercised_gaps",
    "inline_sidecar",
    "mutated",
    "uncovered_gaps",
]

#: Every gap id the walker can emit, read off the module so a new ``GAP_*`` constant shows
#: up here (and then fails the catalogue test) instead of being forgotten.
WALKER_GAPS: tuple[str, ...] = tuple(
    sorted(
        value
        for name, value in vars(walk_module).items()
        if name.startswith("GAP_") and isinstance(value, str)
    )
)

#: The two inline byte strings for the gaps no committed fixture carries. Hand-typed here,
#: small, and paired with the minimal sidecar ``inline_sidecar`` builds from ``expected_gaps``.
NO_BOUNDARY_BYTES = (
    b"Content-Type: multipart/mixed; boundary=missing\r\n"
    b"\r\n"
    b"--other\r\n"
    b"\r\n"
    b"body\r\n"
)

HEADERS_ONLY_BYTES = b"Subject: no blank line follows\r\nX-Last: to end of file"


# ------------------------------------------------------------------- mutants
#: A mutant patches ONE walker rule and returns a restore callable. Each does what a
#: careless walker would: it drops the gap (and, where the design says so, invents the
#: reading the gap exists to refuse).


def _patch(module: Any, name: str, replacement: Any) -> Callable[[], None]:
    original = getattr(module, name)
    setattr(module, name, replacement)
    return lambda: setattr(module, name, original)


def _drop_malformed_line(module: Any) -> Callable[[], None]:
    """Swallow the malformed line into the previous field: no paragraph, no gap (D2)."""
    original = module.header_fields_at

    def naive(raw: bytes, start: int, end: int):
        fields, _gaps = original(raw, start, end)
        return [item for item in fields if item.parse_status == "ok"], []

    return _patch(module, "header_fields_at", naive)


def _drop_boundary_disagreement(module: Any) -> Callable[[], None]:
    """Accept a missing close delimiter silently, as if the multipart were closed."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, _closed, gaps = result
        kept = [gap for gap in gaps if gap != GAP_BODY_BOUNDARY_DISAGREEMENT]
        return preamble, delimiters, chunks, epilogue, True, kept

    return _patch(module, "_segment", naive)


def _drop_preamble(module: Any) -> Callable[[], None]:
    """Drop the preamble from the accounting: no region, no ``body.preamble_bytes``."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, closed, gaps = result
        return RawSpan(preamble.offset, 0, ""), delimiters, chunks, epilogue, closed, gaps

    return _patch(module, "_segment", naive)


def _drop_epilogue(module: Any) -> Callable[[], None]:
    """Drop the epilogue from the accounting: no region, no ``body.epilogue_bytes``."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, closed, gaps = result
        return preamble, delimiters, chunks, RawSpan(epilogue.offset, 0, ""), closed, gaps

    return _patch(module, "_segment", naive)


def _drop_decode_fallback(module: Any) -> Callable[[], None]:
    """Let a broken transfer encoding fall back to the raw payload, recording no gap (d03)."""
    original = module._decode_cte

    def naive(payload: bytes, declared: str | None, *, limit: int | None = None):
        used_cte, decoded, fired, _gap = original(payload, declared, limit=limit)
        return used_cte, decoded, fired, None

    return _patch(module, "_decode_cte", naive)


def _drop_decode_destroyed(module: Any) -> Callable[[], None]:
    """Take the ``errors='replace'`` decode and record nothing lost (never the normal path)."""
    original = module._charset_ladder

    def naive(body: bytes, declared_charset: str | None):
        used_charset, source, fired, gap = original(body, declared_charset)
        if gap == GAP_BODY_DECODE_DESTROYED_BYTES:
            gap = None
        return used_charset, source, fired, gap

    return _patch(module, "_charset_ladder", naive)


def _drop_headers_only(module: Any) -> Callable[[], None]:
    """Read a headers-to-EOF message as a bodyless part and record no gap (spike a04)."""
    original = module._split_headers_body

    def naive(raw: bytes, start: int, end: int):
        headers, body, _gaps = original(raw, start, end)
        return headers, body, []

    return _patch(module, "_split_headers_body", naive)


def _invent_part(module: Any) -> Callable[[], None]:
    """Invent a child covering the whole body when the declared boundary never appears."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is not None:
            return result
        whole = RawSpan(body.offset, body.length, "")
        return RawSpan(body.offset, 0, ""), [RawSpan(body.offset, 0, "")], [whole], RawSpan(
            body.end, 0, ""
        ), True, []

    return _patch(module, "_segment", naive)


@dataclass(frozen=True)
class GapCase:
    """One gap's falsifiability case.

    ``fixture`` is a committed stem; ``inline`` is hand-typed bytes for a gap no committed
    fixture carries, with ``expected_gaps`` the ``part.gaps`` rows that bytes' minimal
    sidecar asserts (built by :func:`inline_sidecar`). ``patch`` performs the one-rule
    mutation; ``naive`` is what the careless walker did, for the failure text.
    """

    gap_id: str
    fact_id: str
    naive: str
    patch: Callable[[Any], Callable[[], None]]
    fixture: str | None = None
    inline: bytes | None = None
    expected_gaps: tuple[tuple[str, tuple[str, ...]], ...] = field(default=())

    def __post_init__(self) -> None:
        if (self.fixture is None) == (self.inline is None):
            raise ValueError(
                f"{self.gap_id}: exactly one of a committed fixture or inline bytes is needed"
            )
        if self.inline is not None and not self.expected_gaps:
            raise ValueError(f"{self.gap_id}: an inline case needs its expected part.gaps rows")


#: gap id -> its case. Kept in one block so the catalogue reads as a list, which it is.
_CASES: tuple[GapCase, ...] = (
    GapCase(
        gap_id=GAP_HEADERS_MALFORMED_LINE,
        fact_id="part.gaps",
        fixture="malformed_mime",
        patch=_drop_malformed_line,
        naive=(
            "swallowed the non-blank line that is neither a field nor a fold into the previous "
            "field, so the paragraph and the gap both vanished (D2 fails open and records it)"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_BOUNDARY_DISAGREEMENT,
        fact_id="part.gaps",
        fixture="malformed_mime",
        patch=_drop_boundary_disagreement,
        naive=(
            "accepted a missing close delimiter silently as if the multipart were closed, "
            "recording no gap for the grammar the bytes do not match"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_PREAMBLE_BYTES,
        fact_id="part.gaps",
        fixture="preamble_epilogue",
        patch=_drop_preamble,
        naive="padded the preamble away: no region and no body.preamble_bytes gap for those bytes",
    ),
    GapCase(
        gap_id=GAP_BODY_EPILOGUE_BYTES,
        fact_id="part.gaps",
        fixture="preamble_epilogue",
        patch=_drop_epilogue,
        naive="padded the epilogue away: no region and no body.epilogue_bytes gap for those bytes",
    ),
    GapCase(
        gap_id=GAP_BODY_DECODE_FALLBACK_USED,
        fact_id="part.gaps",
        fixture="truncated_base64",
        patch=_drop_decode_fallback,
        naive=(
            "fell back to the raw payload for a broken base64 run silently, as stdlib does, "
            "with no body.decode_fallback_used gap"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_DECODE_DESTROYED_BYTES,
        fact_id="part.gaps",
        fixture="bad_charset",
        patch=_drop_decode_destroyed,
        naive=(
            "took the errors='replace' decode and recorded nothing lost, so a byte the ladder "
            "destroyed looks like a clean round trip"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_HEADERS_ONLY,
        fact_id="part.gaps",
        inline=HEADERS_ONLY_BYTES,
        expected_gaps=(("1", (GAP_BODY_HEADERS_ONLY,)),),
        patch=_drop_headers_only,
        naive=(
            "read a headers-to-EOF message as an ordinary bodyless part and recorded no "
            "body.headers_only gap (no committed fixture carries this shape)"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_NO_BOUNDARY_FOUND,
        fact_id="part.gaps",
        inline=NO_BOUNDARY_BYTES,
        expected_gaps=(("1", (GAP_BODY_NO_BOUNDARY_FOUND,)),),
        patch=_invent_part,
        naive=(
            "invented a child covering the whole body when the declared boundary never "
            "appeared, instead of recording body.no_boundary_found and reading the body as a leaf"
        ),
    ),
)

#: gap id -> its case, in the order above.
CASES: Mapping[str, GapCase] = MappingProxyType({case.gap_id: case for case in _CASES})


@contextlib.contextmanager
def mutated(case: GapCase) -> Iterator[None]:
    """Run the walker with ``case``'s one-rule mutation applied, then restore it."""
    restore = case.patch(walk_module)
    try:
        yield
    finally:
        restore()


def exercised_gaps(sidecars: Mapping[str, Any]) -> set[str]:
    """Every gap id the given loaded sidecars record in ``part.gaps``."""
    found: set[str] = set()
    for sidecar in sidecars.values():
        fact = sidecar.facts.get("part.gaps")
        if fact is None or not isinstance(fact.value, list):
            continue
        for entry in fact.value:
            found |= set(entry[1])
    return found


def uncovered_gaps(sidecars: Mapping[str, Any]) -> set[str]:
    """The walker's gap ids that no committed fixture's ``part.gaps`` records."""
    return set(WALKER_GAPS) - exercised_gaps(sidecars)


def inline_sidecar(case: GapCase, raw: bytes) -> dict[str, Any]:
    """The minimal hand-typed sidecar for an inline case: the size and the expected gaps."""
    return {
        "fixture": f"{case.gap_id.replace('.', '_')}.eml",
        "labels_provenance": "spec",
        "facts": {
            "container.size_bytes": {"phase": 0, "value": len(raw)},
            "part.gaps": {
                "phase": 0,
                "value": [[path, list(gaps)] for path, gaps in case.expected_gaps],
            },
        },
    }


def describe(case: GapCase, stem: str, outcome: Any) -> str:
    """The failure text: the fixture, the fact and the gap id, then what the naive case did.

    This is the message a reviewer is handed when a careless implementation slips past the
    gate, so it names all three rather than leaving the reader to reassemble them.
    """
    status = getattr(outcome, "status", outcome)
    return (
        f"{stem}: fact {case.fact_id!r}: gap {case.gap_id!r}: "
        f"status={getattr(status, 'value', status)}, -- {case.naive}"
    )
