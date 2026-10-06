"""Turn 1.11 A: the walker is iterative, and it is still the recursive walker byte for byte.

``emailextract/walk.py::_walk_part`` used to call itself to descend into a nested multipart child
(``walk.py:709`` at Turn 1.10b), which the Phase 1 exit criteria's "the walkers are iterative" does
not allow. It now drains an explicit stack. This module is the proof that the rewrite changed
nothing anyone can observe:

* :func:`test_the_iterative_walker_matches_the_recursive_reference_over_every_fixture` runs the new
  walker and the **frozen recursive reference** (``tests/support/legacy_walk.py``) over every
  committed fixture container, at the unbounded walk and at two capped sets, and compares the two
  :class:`~emailextract.walk.WalkResult` trees **field by field**;
* :func:`test_the_iterative_walker_matches_the_recursive_reference_over_seeded_trees` does the same
  over a seeded corpus of **500 generated nested multipart trees** (random depth up to 12, random
  siblings, random :class:`~emailextract.parse.Limits`);
* :func:`test_a_child_order_mutation_fails_the_differential` proves the differential is not vacuous:
  the anti-vacuity triple (the patched symbol exists, the patch is reached, the observation differs)
  over a mutation that swaps the child order.

The second half is behaviour **under raised caps**: at ``max_depth`` above CPython's recursion limit
the frozen recursive walker raises ``RecursionError`` (and ``assemble`` records the
``failed(extractor_error)`` document that follows), while the iterative walker returns the whole
tree. A test-injected step counter proves the traversal is linear in the tree's size, and
``tracemalloc`` proves peak memory stays a small multiple of the input -- no per-depth copy of the
raw bytes.

Honest limit (reported, not hidden): a nested multipart is **quadratic in the bytes scanned**,
because every level's ``_segment`` scans its whole body and a level's body contains all its
descendants. That is the walker's pre-existing byte-level cost, unchanged by Turn 1.11, so the
recursion fix is proven at a depth that comfortably exceeds the interpreter's stack limit rather
than at 20,000 (which the whole-body rescan would take minutes to reach). The nested
``message/rfc822`` chain -- which the walker never descends into -- **is** exercised at 20,000.
"""

from __future__ import annotations

import ast
import random
import sys
import tracemalloc
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import legacy_walk  # noqa: E402

from emailextract import walk as walk_module  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.model import Status  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from emailextract.walk import walk  # noqa: E402

#: Every committed fixture, as the differential's container corpus (``fixtures/real/`` is ignored
#: and never read).
FIXTURES = tuple(
    sorted(path for path in (ROOT / "fixtures").rglob("*.eml") if "real" not in path.parts)
)

#: The caps the fixture differential also runs at, so the cap paths (part count, header bytes,
#: depth, size, total size) are compared and not only the unbounded walk.
_TIGHT = Limits(
    max_input_bytes=64 * 1024 * 1024,
    max_depth=1,
    max_parts=3,
    max_header_bytes=64,
    max_decoded_part_bytes=16,
    max_decoded_total_bytes=32,
    max_field_work_units_per_byte=1,
)

#: The depth a raised-cap walk is proven at: past CPython's default recursion limit (1000), so the
#: frozen recursive walker cannot finish it, but small enough that the quadratic whole-body rescan
#: (see the module docstring) stays quick.
_DEEP_LEVELS = 1200

#: The depth the ``tracemalloc`` peak is measured at. ``tracemalloc`` traces every allocation, and
#: the walker allocates proportionally to the quadratic whole-body rescan, so this is far shallower
#: than :data:`_DEEP_LEVELS`; the memory claim (peak is a small multiple of the input, never a
#: per-depth copy of it) is depth-independent.
_MEMORY_LEVELS = 300

#: The factor a doubled depth may grow the traversal step count by: 2.0 for the doubling plus slack.
_LINEAR_FACTOR = 2.5

#: The highest ``tracemalloc`` peak a walk may reach, as a multiple of the raw message size. A
#: per-depth copy of the raw bytes would be ``depth * len(raw)`` (~300x here); the frozen output
#: (one record per part) is ~44x, so 120 leaves room and still catches a per-depth copy.
_MEMORY_FACTOR = 120


# ---------------------------------------------------------------- the field-by-field comparison


def _diff(live: object, reference: object, path: str = "$") -> str | None:
    """The first field (by name, recursively) where two records differ, or ``None``.

    Both walkers return the *live* record classes (the reference imports them), so this walks the
    dataclasses' own ``fields`` rather than comparing opaque objects: "field by field", named.
    """
    if is_dataclass(live) and not isinstance(live, type):
        for field_ in fields(live):
            found = _diff(
                getattr(live, field_.name), getattr(reference, field_.name), f"{path}.{field_.name}"
            )
            if found is not None:
                return found
        return None
    if isinstance(live, (list, tuple)):
        if len(live) != len(reference):  # type: ignore[arg-type]
            return f"{path}: length {len(live)} != {len(reference)}"  # type: ignore[arg-type]
        for index, (left, right) in enumerate(zip(live, reference)):  # type: ignore[arg-type]
            found = _diff(left, right, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    if live != reference:
        return f"{path}: {live!r} != {reference!r}"
    return None


def _assert_same_field(live: object, reference: object, label: str) -> None:
    found = _diff(live, reference)
    assert found is None, f"{label}: {found}"


# ---------------------------------------------------------------- the generated tree corpus


def _random_leaf(rng: random.Random) -> bytes:
    """A random leaf part: a content type, an optional CTE, and a small payload."""
    content_type = rng.choice(
        [
            b"text/plain",
            b"text/plain; charset=utf-8",
            b"text/html; charset=windows-1252",
            b"application/octet-stream",
            b'image/png; name="x.png"',
        ]
    )
    headers = b"Content-Type: " + content_type + b"\r\n"
    if rng.random() < 0.4:
        headers += (
            b"Content-Transfer-Encoding: "
            + rng.choice([b"7bit", b"8bit", b"base64", b"quoted-printable", b"x-unknown"])
            + b"\r\n"
        )
    if rng.random() < 0.3:
        headers += b'Content-Disposition: attachment; filename="f.bin"\r\n'
    payload = rng.choice(
        [b"hello\r\n", b"", b"aGVsbG8gd29ybGQ=\r\n", b"line=20with=3Dbreak\r\n", rng.randbytes(8)]
    )
    return headers + b"\r\n" + payload


def _random_part(rng: random.Random, depth: int, budget: list[int]) -> bytes:
    """A random MIME part: a leaf, or a multipart around 0-3 random children."""
    if depth <= 0 or budget[0] >= 180 or rng.random() < 0.45:
        budget[0] += 1
        return _random_leaf(rng)
    boundary = f"B{budget[1]}".encode()
    budget[1] += 1
    subtype = rng.choice([b"mixed", b"alternative", b"related", b"digest"])
    headers = b"Content-Type: multipart/" + subtype + b'; boundary="' + boundary + b'"\r\n'
    if rng.random() < 0.2:
        headers += b"Content-Transfer-Encoding: 8bit\r\n"
    body = bytearray()
    if rng.random() < 0.3:
        body += b"a preamble line\r\n"
    for _ in range(rng.randint(0, 3)):
        body += b"--" + boundary + b"\r\n"
        body += _random_part(rng, depth - 1, budget)
        body += b"\r\n"
    if rng.random() < 0.85:
        body += b"--" + boundary + b"--\r\n"
    if rng.random() < 0.3:
        body += b"an epilogue line\r\n"
    return headers + b"\r\n" + bytes(body)


def _random_message(rng: random.Random) -> bytes:
    return _random_part(rng, rng.randint(0, 12), [0, 0])


def _random_limits(rng: random.Random) -> Limits | None:
    """A random cap set (or ``None`` for the unbounded walk), skewed small so caps fire."""
    if rng.random() < 0.25:
        return None
    return Limits(
        max_input_bytes=rng.choice([64 * 1024, 1 << 20]),
        max_depth=rng.choice([1, 2, 3, 4, 6, 12, 1000]),
        max_parts=rng.choice([1, 2, 3, 5, 10, 50, 1000]),
        max_header_bytes=rng.choice([8, 32, 128, 4096, 1 << 20]),
        max_decoded_part_bytes=rng.choice([4, 16, 1024, 1 << 20]),
        max_decoded_total_bytes=rng.choice([4, 16, 2048, 1 << 20]),
        max_field_work_units_per_byte=rng.choice([1, 8, 64]),
    )


# ------------------------------------------------------------------------- the differentials


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_the_iterative_walker_matches_the_recursive_reference_over_every_fixture(path: Path) -> None:
    """Every committed fixture container walks identically, unbounded and under tight caps."""
    raw = path.read_bytes()
    for label, caps in (("unbounded", None), ("untrusted", Limits.untrusted()), ("tight", _TIGHT)):
        container = EmlContainer(memory_bytes(raw))
        live = walk(container, limits=caps)
        reference = legacy_walk.walk(container, limits=caps)
        _assert_same_field(live, reference, f"{path.name} [{label}]")


def test_the_iterative_walker_matches_the_recursive_reference_over_seeded_trees() -> None:
    """500 seeded random nested multipart trees, with random cap settings, walk identically."""
    compared = 0
    for seed in range(500):
        rng = random.Random(seed)
        raw = _random_message(rng)
        caps = _random_limits(rng)
        container = EmlContainer(memory_bytes(raw))
        live = walk(container, limits=caps)
        reference = legacy_walk.walk(container, limits=caps)
        _assert_same_field(live, reference, f"seed {seed} ({len(raw)} bytes, limits={caps})")
        compared += 1
    assert compared == 500, compared


def _self_recursive_functions(path: str | Path) -> set[str]:
    """Module-level functions that call their own bare name (the scope test's scan)."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    offenders: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == node.name
            ):
                offenders.add(node.name)
                break
    return offenders


def test_the_recursive_reference_really_is_recursive() -> None:
    """The reference descends by self-call and the live walker does not -- so the pair is the point."""
    assert "_walk_part" in _self_recursive_functions(legacy_walk.__file__)
    assert _self_recursive_functions(walk_module.__file__) == set()


# ---------------------------------------------------------------------------- the mutation


def test_a_child_order_mutation_fails_the_differential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swapping the child order must move the walk -- the differential is not vacuous.

    The anti-vacuity triple: (1) the symbol the mutation patches exists; (2) the patch is reached
    (the wrapper runs); (3) the observation differs from the frozen reference, which binds its own
    ``_segment`` at import so only the new walker is mutated.
    """
    raw = (
        b"Content-Type: multipart/mixed; boundary=B\r\n\r\n"
        b"--B\r\nContent-Type: text/plain\r\n\r\nfirst\r\n"
        b"--B\r\nContent-Type: text/plain\r\n\r\nsecond\r\n"
        b"--B\r\nContent-Type: text/plain\r\n\r\nthird\r\n"
        b"--B--\r\n"
    )
    container = EmlContainer(memory_bytes(raw))

    # The unmutated differential agrees, so a "differs" result below is the mutation's doing.
    reference = legacy_walk.walk(container)
    _assert_same_field(walk(container), reference, "baseline")

    assert hasattr(walk_module, "_segment"), "the mutation's symbol is gone"  # (1)
    original = walk_module._segment
    reached = {"calls": 0}

    def reversed_segment(raw_bytes: bytes, body, boundary):
        reached["calls"] += 1
        result = original(raw_bytes, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, closed, gaps = result
        return preamble, delimiters, list(reversed(chunks)), epilogue, closed, gaps

    with monkeypatch.context() as patch:
        patch.setattr(walk_module, "_segment", reversed_segment)
        mutated = walk(container)
    assert reached["calls"] > 0, "the mutation never ran"  # (2)
    assert _diff(mutated, reference) is not None, "the mutation changed nothing"  # (3)


# ------------------------------------------------------------- behaviour under raised caps


def _deep_multipart(levels: int) -> bytes:
    """``levels`` nested ``multipart/mixed`` declarations around one leaf (the hostile builder)."""
    out = bytearray()
    for index in range(levels):
        out += b"Content-Type: multipart/mixed; boundary=B%d\r\n\r\n--B%d\r\n" % (index, index)
    out += b"Content-Type: text/plain\r\n\r\nleaf\r\n"
    for index in reversed(range(levels)):
        out += b"\r\n--B%d--\r\n" % index
    return bytes(out)


def _deep_rfc822(depth: int) -> bytes:
    """A chain of ``depth`` ``message/rfc822`` parts around one leaf."""
    body = b"Content-Type: text/plain\r\n\r\nleaf\r\n"
    for _ in range(depth):
        body = b"Content-Type: message/rfc822\r\n\r\n" + body
    return body


def _raised() -> Limits:
    """The raised caps: ``max_depth`` far above CPython's recursion limit, the rest generous."""
    return Limits(
        max_input_bytes=256 * 1024 * 1024,
        max_depth=100_000,
        max_parts=1_000_000,
        max_header_bytes=16 * 1024 * 1024,
        max_decoded_part_bytes=256 * 1024 * 1024,
        max_decoded_total_bytes=512 * 1024 * 1024,
        max_field_work_units_per_byte=64,
    )


def _visit_counter(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Inject a step counter around the traversal: one step per part the loop visits.

    The walker's own ``WORK`` counter measures byte-level work (its ``_iter_lines`` counts every
    line, and every level re-scans its whole body), so it is quadratic in depth for this input
    shape. The traversal -- the thing the rewrite controls -- is counted here instead.
    """
    original = walk_module._walk_visit
    counter = {"steps": 0}

    def counted(raw, container_id, item, parts, regions, state, stack):
        counter["steps"] += 1
        return original(raw, container_id, item, parts, regions, state, stack)

    monkeypatch.setattr(walk_module, "_walk_visit", counted)
    return counter


def test_a_raised_depth_cap_walks_deep_multipart_without_recursing() -> None:
    """A depth above the recursion limit walks whole and assembles to a normal record.

    The frozen recursive walker raises ``RecursionError`` on the same input (so the fix is the
    point), and the document is ``parsed`` -- never ``failed(extractor_error)``, which is what a
    recursion blow-up produced before.
    """
    raw = _deep_multipart(_DEEP_LEVELS)
    container = EmlContainer(memory_bytes(raw))
    caps = _raised()

    with pytest.raises(RecursionError):
        legacy_walk.walk(container, limits=caps)

    result = walk(container, limits=caps)
    assert len(result.parts) == _DEEP_LEVELS + 1, len(result.parts)

    document = assemble(container, limits=caps)
    assert document.status.status is Status.PARSED, document.status
    assert document.status.reason is None, document.status
    assert len(document.parts) == _DEEP_LEVELS + 1, len(document.parts)


def test_a_raised_depth_cap_walks_a_deep_rfc822_chain() -> None:
    """A 20,000-deep ``message/rfc822`` chain walks and assembles without a failure.

    The walker records the top-level part and never descends into a ``message/rfc822`` part, so this
    is one part with a large body -- the same "a raised cap must not fail the record" claim, at the
    full 20,000 the turn names.
    """
    raw = _deep_rfc822(20_000)
    container = EmlContainer(memory_bytes(raw))
    caps = _raised()
    result = walk(container, limits=caps)
    assert result.parts, "no part measured"
    assert all(part.path == "1" for part in result.parts), [part.path for part in result.parts]
    document = assemble(container, limits=caps)
    assert document.status.status is Status.PARSED, document.status


def test_the_deep_walk_takes_exact_linear_steps_and_bounded_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The traversal is exactly one step per part, linear in the doubling, and bounded in memory."""
    caps = _raised()
    small = EmlContainer(memory_bytes(_deep_multipart(_DEEP_LEVELS // 2)))
    large = EmlContainer(memory_bytes(_deep_multipart(_DEEP_LEVELS)))

    with monkeypatch.context() as patch:
        counter = _visit_counter(patch)
        small_result = walk(small, limits=caps)
        assert counter["steps"] == _DEEP_LEVELS // 2 + 1, counter["steps"]
        assert len(small_result.parts) == _DEEP_LEVELS // 2 + 1
        small_steps = counter["steps"]

        counter["steps"] = 0
        large_result = walk(large, limits=caps)
        assert counter["steps"] == _DEEP_LEVELS + 1, counter["steps"]
        assert len(large_result.parts) == _DEEP_LEVELS + 1
        big_steps = counter["steps"]

    ratio = big_steps / small_steps
    assert ratio < _LINEAR_FACTOR, f"doubling the depth grew the steps {small_steps} -> {big_steps}"

    measured = EmlContainer(memory_bytes(_deep_multipart(_MEMORY_LEVELS)))
    raw = measured.raw_bytes()
    tracemalloc.start()
    try:
        walk(measured, limits=caps)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < _MEMORY_FACTOR * len(raw), f"peak {peak} for {len(raw)} input bytes"
