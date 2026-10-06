"""Turn 1.5c: the structural caps, enforced and recorded (``walk(container, *, limits=...)``).

Seven caps are defined on :class:`~emailextract.parse.Limits`; before this turn only
``max_input_bytes`` (at the entry point), the HTML tree's depth/element caps and the
per-field RFC 2047 budget did anything. Here every cap is enforced by the walker **as the
structure is discovered**, never after the fact, and every hit is recorded with the
vocabulary that already exists:

* one :class:`~emailextract.walk.Region` whose ``kind`` *is* the closed cap reason
  (``model.REASON_TABLE[Status.SKIPPED]``), whose ``path`` is the locator of the part the
  cap stopped and whose ``span`` is the exact byte range -- so the regions still tile the
  message and the no-silent-drop gate needs no change to know about them;
* one :class:`~emailextract.walk.UnknownSection` on ``unknown_sections`` carrying the same
  reason as ``unknown(reason_id)`` and the same locator as its ``section``.

A cap hit is therefore the **existing** pair ``skipped(<cap reason>)`` plus a ``CapRecord``
triple (``cap_id`` is the reason id, ``cap_value_bytes`` is **the caller's** ``Limits``
field, ``declared_size_bytes`` is the bytes the cap stopped). No new reason id, no new
record, no exception, no ``Truncation``.

The boundary rule is one rule for all five caps: **a value equal to the cap is allowed, one
over is a hit**.

``walk(container)`` -- no ``limits`` -- stays unbounded, so the frozen corpus, the behaviour
ledger's ``walk``/``decode_chain`` lines and L1 cannot move; the tests below prove that too.
"""

from __future__ import annotations

import base64
import hashlib
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

import emailextract.walk as walk_module
from emailextract.container import EmlContainer
from emailextract.evals import gates
from emailextract.model import REASON_TABLE, CapRecord, Status, StatusOutcome, TriState, TriValue
from emailextract.parse import Limits
from emailextract.walk import (
    CAP_REASONS,
    CAP_REASON_DEPTH,
    CAP_REASON_HEADER_BYTES,
    CAP_REASON_PART_COUNT,
    CAP_REASON_SIZE,
    CAP_REASON_TOTAL_SIZE,
    UNBUILT_SECTIONS,
    WORK,
    UnknownSection,
    WalkResult,
    walk,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

#: The turn-1.0c cap fixtures, one per walker cap. The encoded-word bomb's own hostile
#: dimension is the RFC 2047 *work budget* (a header-stage parameter), so the walker cap it
#: carries is its enormous header region.
CAP_FIXTURES = {
    CAP_REASON_DEPTH: "generated/cap_deep_nesting.eml",
    CAP_REASON_PART_COUNT: "generated/cap_large_part_count.eml",
    CAP_REASON_HEADER_BYTES: "generated/cap_enormous_header_block.eml",
    CAP_REASON_SIZE: "raw/cap_very_long_base64_run.eml",
}

#: The mutation case that exercises each cap reason (item 7's catalogue).
CAP_MUTATION_CASES = {
    CAP_REASON_DEPTH: "test_the_depth_cap_off_by_one_mutant_is_caught",
    CAP_REASON_PART_COUNT: "test_the_part_count_cap_checked_after_building_the_parts_mutant_is_caught",
    CAP_REASON_HEADER_BYTES: "test_the_header_cap_checked_after_the_fields_mutant_is_caught",
    CAP_REASON_SIZE: "test_a_truncated_body_mutant_is_refused_by_the_gate",
    CAP_REASON_TOTAL_SIZE: "test_a_total_cap_that_does_not_accumulate_mutant_is_caught",
}

#: The five cap fixtures' measured values the boundary tests sit on: the depth reached, the
#: parts emitted, the header region's size and the decoded size of the long base64 run.
MEASURED = {
    "deep_nesting_depth": 6,
    "part_count_parts": 10,
    "enormous_header_bytes": 5982,
    "very_long_base64_decoded": 4096,
    "encoded_word_bomb_header_bytes": 303,
}

#: Every cap far above any test input, so exactly one named cap can fire.
HIGH = {
    "max_input_bytes": 64 * 1024 * 1024,
    "max_depth": 10_000,
    "max_parts": 100_000,
    "max_header_bytes": 4 * 1024 * 1024,
    "max_decoded_part_bytes": 64 * 1024 * 1024,
    "max_decoded_total_bytes": 128 * 1024 * 1024,
    "max_field_work_units_per_byte": 64,
}


def limits(**over: int) -> Limits:
    """A caller's ``Limits``: every cap high except the ones the test names."""
    return Limits(**{**HIGH, **over})


# --------------------------------------------------------------- message builders


def nested(levels: int) -> bytes:
    """``levels`` nested ``multipart/mixed`` parts around one ``text/plain`` leaf.

    The deepest part is at depth ``levels + 1``: the top-level part is depth 1.
    """
    out = bytearray()
    for index in range(levels):
        out += b"Content-Type: multipart/mixed; boundary=B%d\r\n\r\n--B%d\r\n" % (index, index)
    out += b"Content-Type: text/plain\r\n\r\nleaf\r\n"
    for index in range(levels - 1, -1, -1):
        out += b"--B%d--\r\n" % index
    return bytes(out)


def fan_out(children: int) -> bytes:
    """One ``multipart/mixed`` with ``children`` 9-byte ``text/plain`` children."""
    out = bytearray(b"Content-Type: multipart/mixed; boundary=B\r\n\r\n")
    for index in range(children):
        out += b"--B\r\nContent-Type: text/plain\r\n\r\nchild %d\r\n" % index
    out += b"--B--\r\n"
    return bytes(out)


def header_block(fields: int) -> tuple[bytes, int]:
    """A message of ``fields`` ``X-Pad`` header lines, and its header region's size.

    The region includes its closing blank line's CRLF, computed from the bytes, never read
    back out of the walker.
    """
    lines = b"".join(b"X-Pad-%d: %s\r\n" % (index, b"p" * 40) for index in range(fields))
    return lines + b"\r\n" + b"body\r\n", len(lines) + 2


def encoded_part(decoded_bytes: int, *, cte: bytes = b"base64") -> bytes:
    """A one-part message whose body decodes to exactly ``decoded_bytes`` bytes of ``x``."""
    raw = b"x" * decoded_bytes
    payload = base64.b64encode(raw) if cte == b"base64" else b"=78" * decoded_bytes
    return (
        b"Content-Type: text/plain; charset=us-ascii\r\n"
        b"Content-Transfer-Encoding: " + cte + b"\r\n\r\n" + payload + b"\r\n"
    )


def boundary_storm(pairs: int) -> bytes:
    """A ``multipart/mixed`` whose body repeats ``pairs`` delimiter-plus-part line pairs."""
    out = bytearray(b"Content-Type: multipart/mixed; boundary=B\r\n\r\n")
    out += b"--B\r\nContent-Type: text/plain\r\n\r\nx\r\n" * pairs
    out += b"--B--\r\n"
    return bytes(out)


# ------------------------------------------------------------------------ the gate


def cap_regions(result: WalkResult) -> list[Any]:
    """The accounted regions whose kind is a cap reason, in document order."""
    return [region for region in result.regions if region.kind in CAP_REASONS]


def cap_sections(result: WalkResult) -> list[Any]:
    """The walker's unread-and-why entries, in the order the walk recorded them."""
    return [
        section for section in result.unknown_sections if section.value.reason_id in CAP_REASONS
    ]


def recorded(result: WalkResult, limits_: Limits) -> list[tuple[StatusOutcome, CapRecord]]:
    """The closed pair a capped walk records, reconstructed the way Turn 1.9 will.

    Every cap region is the ``skipped`` status with its reason, and its cap record is
    ``CapRecord(cap_id=<the reason>, cap_value_bytes=<the caller's Limits field>,
    declared_size_bytes=<the bytes the cap stopped>)``. Both are the model's own records:
    nothing here is a new shape. The reason-to-field map is read off the module at call time,
    so a mutant of it is seen here rather than cached.
    """
    return [
        (
            StatusOutcome(Status.SKIPPED, region.kind),
            CapRecord(
                cap_id=region.kind,
                cap_value_bytes=getattr(limits_, walk_module.CAP_LIMIT_FIELDS[region.kind]),
                declared_size_bytes=region.span.length,
            ),
        )
        for region in cap_regions(result)
    ]


def cap_gate(
    raw: bytes, *, parts: list[str], caps: list[tuple[str, str]], **over: int
) -> list[str]:
    """The gate every capped case is poured into; ``[]`` means it held.

    Names the cap and the locator on every problem: the walk raises nothing; it emits the
    exact part locators and the exact ``(reason, locator)`` cap pairs; each pair is the
    *existing* vocabulary (a closed ``skipped`` reason, a ``CapRecord`` whose value is the
    caller's own limit); the unknown-section channel carries the same pairs; and the regions
    tile every byte exactly once (no-silent-drop).
    """
    limits_ = limits(**over)
    try:
        result = walk(EmlContainer(raw), limits=limits_)
    except Exception as error:  # noqa: BLE001 -- a raised cap is one of the mutants
        return [f"the walk raised {type(error).__name__}: {error}"]
    problems: list[str] = []
    found = [part.path for part in result.parts]
    if found != parts:
        problems.append(f"parts {found} are not {parts}")
    observed = [(region.kind, region.path) for region in cap_regions(result)]
    if observed != caps:
        problems.append(f"cap regions {observed} are not {caps}")
    sections = [(section.value.reason_id, section.section) for section in cap_sections(result)]
    if sections != caps:
        problems.append(f"unknown sections {sections} are not {caps}")
    for outcome, record in recorded(result, limits_):
        if (
            outcome.status is not Status.SKIPPED
            or outcome.reason not in REASON_TABLE[Status.SKIPPED]
        ):
            problems.append(f"{outcome.reason!r} is not a closed skipped reason")
        if record.cap_value_bytes != getattr(limits_, walk_module.CAP_LIMIT_FIELDS[record.cap_id]):
            problems.append(f"{record.cap_id} records cap value {record.cap_value_bytes}")
    problems.extend(
        f"{hole.kind} bytes {hole.start}..{hole.end}"
        for hole in gates.holes(result.regions, len(raw))
    )
    return problems


def _part(result: WalkResult, path: str):
    return next(part for part in result.parts if part.path == path)


def _fixture(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def _patch(monkeypatch: pytest.MonkeyPatch, name: str, wrapper: Callable[..., Any], flags: dict):
    """Replace ``walk_module.<name>`` with ``wrapper`` (which sets ``flags['reached']``).

    The anti-vacuity triple: ``monkeypatch.setattr`` fails if the symbol does not exist, the
    wrapper proves the patch was *reached*, and the caller asserts the gate flips to fail.
    """
    real = getattr(walk_module, name)

    def counted(*args: Any, **kwargs: Any) -> Any:
        flags["reached"] += 1
        return wrapper(real, *args, **kwargs)

    monkeypatch.setattr(walk_module, name, counted)
    return real


# ------------------------------------------------- item 1: the vocabulary, the pair


def test_the_cap_reasons_are_exactly_the_models_closed_skipped_reasons() -> None:
    """The walker invents no cap vocabulary: its five ids *are* the model's skipped reasons."""
    assert set(CAP_REASONS) == set(REASON_TABLE[Status.SKIPPED])
    assert len(CAP_REASONS) == 5
    assert set(walk_module.CAP_LIMIT_FIELDS) == set(CAP_REASONS)
    # ... and each reason maps to a field a caller's Limits really has, so the value a
    # reader records is the caller's own.
    assert all(
        hasattr(Limits.untrusted(), field) for field in walk_module.CAP_LIMIT_FIELDS.values()
    )


def test_a_cap_hit_is_the_existing_status_reason_and_a_cap_record() -> None:
    """A hit is ``skipped(<cap reason>)`` plus a ``CapRecord``, both the model's own records."""
    raw = nested(2)
    limits_ = limits(max_depth=2)
    result = walk(EmlContainer(raw), limits=limits_)
    pairs = recorded(result, limits_)
    assert [(outcome.status, outcome.reason) for outcome, _ in pairs] == [
        (Status.SKIPPED, CAP_REASON_DEPTH)
    ]
    _, record = pairs[0]
    assert record == CapRecord(
        cap_id=CAP_REASON_DEPTH,
        cap_value_bytes=2,
        declared_size_bytes=cap_regions(result)[0].span.length,
    )
    # A status/reason pair the closed table does not hold cannot even be built, so a walker
    # that invented an id would raise here rather than record one.
    with pytest.raises(Exception):
        StatusOutcome(Status.SKIPPED, "too_deep")


# -------------------------------------------- item 3: the structural cap boundaries


def test_the_depth_cap_boundary_is_at_one_below_and_one_above() -> None:
    """Depth 3 is allowed at cap 3 and a hit at 2; a bigger cap changes nothing."""
    raw = nested(2)
    assert cap_gate(raw, parts=["1", "1.1", "1.1.1"], caps=[], max_depth=3) == []
    assert (
        cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2) == []
    )
    assert cap_gate(raw, parts=["1", "1.1", "1.1.1"], caps=[], max_depth=4) == []


def test_the_part_count_cap_boundary_is_at_one_below_and_one_above() -> None:
    """Three parts are allowed at cap 3, the third is a hit at cap 2."""
    raw = fan_out(2)
    assert cap_gate(raw, parts=["1", "1.1", "1.2"], caps=[], max_parts=3) == []
    assert (
        cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_PART_COUNT, "1.2")], max_parts=2) == []
    )
    assert cap_gate(raw, parts=["1", "1.1", "1.2"], caps=[], max_parts=4) == []


def test_the_header_bytes_cap_boundary_is_at_one_below_and_one_above() -> None:
    """A header region equal to the cap is parsed field by field; one byte over is a hit."""
    raw, size = header_block(20)
    assert walk(EmlContainer(raw)).parts[0].headers_span.length == size
    assert cap_gate(raw, parts=["1"], caps=[], max_header_bytes=size) == []
    assert (
        cap_gate(
            raw, parts=[], caps=[(CAP_REASON_HEADER_BYTES, "1")], max_header_bytes=size - 1
        )
        == []
    )
    assert cap_gate(raw, parts=["1"], caps=[], max_header_bytes=size + 1) == []


def test_the_decoded_part_cap_boundary_is_at_one_below_and_one_above() -> None:
    """One part's decoded size equal to the cap is decoded; one byte over is skipped."""
    raw = encoded_part(4096)
    assert cap_gate(raw, parts=["1"], caps=[], max_decoded_part_bytes=4096) == []
    assert (
        cap_gate(raw, parts=["1"], caps=[(CAP_REASON_SIZE, "1")], max_decoded_part_bytes=4095) == []
    )
    assert cap_gate(raw, parts=["1"], caps=[], max_decoded_part_bytes=4097) == []


def test_the_decoded_total_cap_boundary_is_at_one_below_and_one_above() -> None:
    """Two 7-byte leaves (the CRLF before a delimiter is the delimiter's): total 14."""
    raw = fan_out(2)
    assert cap_gate(raw, parts=["1", "1.1", "1.2"], caps=[], max_decoded_total_bytes=14) == []
    assert (
        cap_gate(
            raw,
            parts=["1", "1.1", "1.2"],
            caps=[(CAP_REASON_TOTAL_SIZE, "1.2")],
            max_decoded_total_bytes=13,
        )
        == []
    )
    assert cap_gate(raw, parts=["1", "1.1", "1.2"], caps=[], max_decoded_total_bytes=15) == []


# ------------------------------------------------ item 4: the decoded-size caps


def test_a_part_over_the_decoded_cap_is_skipped_and_its_sha256_is_unknown() -> None:
    """Skipped, never truncated: no body, not even a prefix, is reported as the part's."""
    raw = encoded_part(4096)
    result = walk(EmlContainer(raw), limits=limits(max_decoded_part_bytes=1024))
    part = _part(result, "1")
    assert part.body_sha256 is None, "a capped part must not report a content sha256"
    # The two readings a careless decoder would produce are both refused.
    assert hashlib.sha256(b"x" * 1024).hexdigest() != part.body_sha256
    assert hashlib.sha256(b"x" * 4096).hexdigest() != part.body_sha256
    # The header facts the walker *did* read are still reported: only the body is unknown.
    assert part.content_type == "text/plain"
    assert part.decode_chain.used_cte is None and part.decode_chain.declared_cte == "base64"
    assert part.decode_chain.fallback_fired is False
    assert walk_module.GAP_BODY_DECODE_FALLBACK_USED not in part.gaps
    assert gates.holes(result.regions, len(raw)) == []

    # A 1 MB base64 payload (1 333 336 encoded bytes, 163 chunks) under a 1 KiB cap stops in
    # the first chunk: the decode is bounded by the cap, not by the input.
    big = encoded_part(1_000_000)
    WORK.reset()
    bombed = walk(EmlContainer(big), limits=limits(max_decoded_part_bytes=1024))
    steps = WORK.count()
    assert [(region.kind, region.path) for region in cap_regions(bombed)] == [
        (CAP_REASON_SIZE, "1")
    ]
    assert _part(bombed, "1").body_sha256 is None
    assert steps <= 16, f"{steps} steps for a 1 MB base64 bomb"


def test_every_later_part_is_skipped_once_the_total_cap_is_reached() -> None:
    """The cap is a message-wide running sum, and each later part is recorded."""
    raw = fan_out(4)
    result = walk(EmlContainer(raw), limits=limits(max_decoded_total_bytes=9))
    assert [part.path for part in result.parts] == ["1", "1.1", "1.2", "1.3", "1.4"]
    assert [(region.kind, region.path) for region in cap_regions(result)] == [
        (CAP_REASON_TOTAL_SIZE, "1.2"),
        (CAP_REASON_TOTAL_SIZE, "1.3"),
        (CAP_REASON_TOTAL_SIZE, "1.4"),
    ]
    assert _part(result, "1.1").body_sha256 is not None
    for path in ("1.2", "1.3", "1.4"):
        assert _part(result, path).body_sha256 is None, path
    assert gates.holes(result.regions, len(raw)) == []


def test_a_quoted_printable_escape_bomb_is_bounded_and_skipped() -> None:
    """200 000 ``=78`` escapes decode to 200 000 bytes; the cap stops the decode early."""
    raw = encoded_part(200_000, cte=b"quoted-printable")
    WORK.reset()
    result = walk(EmlContainer(raw), limits=limits(max_decoded_part_bytes=64_000))
    steps = WORK.count()
    assert [(region.kind, region.path) for region in cap_regions(result)] == [
        (CAP_REASON_SIZE, "1")
    ]
    assert _part(result, "1").body_sha256 is None
    # A step per escape would be 200 000; a chunk per DECODE_CHUNK input bytes is a handful.
    assert steps <= 64, f"{steps} steps for 200 000 escapes"


# ------------------------------------------------ item 6: the five cap fixtures


def test_cap_deep_nesting_records_the_depth_cap_and_nothing_under_untrusted() -> None:
    raw = _fixture("generated/cap_deep_nesting.eml")
    depth = MEASURED["deep_nesting_depth"]
    assert walk(EmlContainer(raw)).parts[-1].path.count(".") + 1 == depth
    assert (
        cap_gate(
            raw,
            parts=["1", "1.1", "1.1.1", "1.1.1.1", "1.1.1.1.1"],
            caps=[(CAP_REASON_DEPTH, "1.1.1.1.1.1")],
            max_depth=depth - 1,
        )
        == []
    )
    assert walk(EmlContainer(raw), limits=Limits.untrusted()) == walk(EmlContainer(raw))


def test_cap_large_part_count_records_the_part_count_cap_and_nothing_under_untrusted() -> None:
    raw = _fixture("generated/cap_large_part_count.eml")
    count = MEASURED["part_count_parts"]
    assert len(walk(EmlContainer(raw)).parts) == count
    assert (
        cap_gate(
            raw,
            parts=["1"] + [f"1.{index}" for index in range(1, count - 1)],
            caps=[(CAP_REASON_PART_COUNT, f"1.{count - 1}")],
            max_parts=count - 1,
        )
        == []
    )
    assert walk(EmlContainer(raw), limits=Limits.untrusted()) == walk(EmlContainer(raw))


def test_cap_enormous_header_block_records_the_header_bytes_cap_and_nothing_under_untrusted() -> None:
    raw = _fixture("generated/cap_enormous_header_block.eml")
    size = walk(EmlContainer(raw)).parts[0].headers_span.length
    assert size == MEASURED["enormous_header_bytes"]
    assert (
        cap_gate(raw, parts=[], caps=[(CAP_REASON_HEADER_BYTES, "1")], max_header_bytes=size - 1)
        == []
    )
    assert walk(EmlContainer(raw), limits=Limits.untrusted()) == walk(EmlContainer(raw))


def test_cap_very_long_base64_run_records_the_size_cap_and_nothing_under_untrusted() -> None:
    raw = _fixture("raw/cap_very_long_base64_run.eml")
    decoded = MEASURED["very_long_base64_decoded"]
    assert (
        cap_gate(
            raw,
            parts=["1"],
            caps=[(CAP_REASON_SIZE, "1")],
            max_decoded_part_bytes=decoded - 1,
        )
        == []
    )
    assert (
        _part(
            walk(EmlContainer(raw), limits=limits(max_decoded_part_bytes=decoded)), "1"
        ).body_sha256
        is not None
    )
    assert walk(EmlContainer(raw), limits=Limits.untrusted()) == walk(EmlContainer(raw))


def test_cap_encoded_word_bomb_records_the_header_bytes_cap_and_nothing_under_untrusted() -> None:
    """The bomb's own dimension is the RFC 2047 work budget; its walker cap is the block."""
    raw = _fixture("raw/cap_encoded_word_bomb.eml")
    size = walk(EmlContainer(raw)).parts[0].headers_span.length
    assert size == MEASURED["encoded_word_bomb_header_bytes"]
    assert (
        cap_gate(raw, parts=[], caps=[(CAP_REASON_HEADER_BYTES, "1")], max_header_bytes=size - 1)
        == []
    )
    assert walk(EmlContainer(raw), limits=Limits.untrusted()) == walk(EmlContainer(raw))


def test_every_capped_result_accounts_for_every_byte() -> None:
    """The no-silent-drop gate over every capped result: the skipped bytes are accounted."""
    cases: list[tuple[str, bytes, dict[str, int]]] = [
        ("cap_deep_nesting", _fixture("generated/cap_deep_nesting.eml"), {"max_depth": 5}),
        (
            "cap_large_part_count",
            _fixture("generated/cap_large_part_count.eml"),
            {"max_parts": 9},
        ),
        (
            "cap_enormous_header_block",
            _fixture("generated/cap_enormous_header_block.eml"),
            {"max_header_bytes": 5981},
        ),
        (
            "cap_very_long_base64_run",
            _fixture("raw/cap_very_long_base64_run.eml"),
            {"max_decoded_part_bytes": 4095},
        ),
        (
            "cap_encoded_word_bomb",
            _fixture("raw/cap_encoded_word_bomb.eml"),
            {"max_header_bytes": 302},
        ),
        ("nested_3_at_1", nested(3), {"max_depth": 1}),
        ("fan_out_3_at_2", fan_out(3), {"max_parts": 2}),
        ("header_block_at_1", header_block(5)[0], {"max_header_bytes": 1}),
        ("base64_at_1", encoded_part(64), {"max_decoded_part_bytes": 1}),
        ("total_at_1", fan_out(2), {"max_decoded_total_bytes": 1}),
    ]
    problems: list[str] = []
    for name, raw, over in cases:
        result = walk(EmlContainer(raw), limits=limits(**over))
        problems.extend(f"{name}: {hole}" for hole in gates.holes(result.regions, len(raw)))
        pairs = {(section.value.reason_id, section.section) for section in cap_sections(result)}
        problems.extend(
            f"{name}: {region.kind} at {region.path} has no reason entry"
            for region in cap_regions(result)
            if (region.kind, region.path) not in pairs
        )
    assert problems == []


def test_two_caps_in_one_run_are_both_recorded() -> None:
    """A run that hits two caps records both -- each on its own bytes."""
    raw = fan_out(9)
    assert (
        cap_gate(
            raw,
            parts=["1"] + [f"1.{index}" for index in range(1, 9)],
            caps=[
                (CAP_REASON_TOTAL_SIZE, "1.3"),
                (CAP_REASON_TOTAL_SIZE, "1.4"),
                (CAP_REASON_TOTAL_SIZE, "1.5"),
                (CAP_REASON_TOTAL_SIZE, "1.6"),
                (CAP_REASON_TOTAL_SIZE, "1.7"),
                (CAP_REASON_TOTAL_SIZE, "1.8"),
                (CAP_REASON_PART_COUNT, "1.9"),
            ],
            max_parts=9,
            max_decoded_total_bytes=18,
        )
        == []
    )


def test_a_capped_walk_is_deterministic_across_runs_and_interpreters() -> None:
    """Same bytes, same Limits, same result -- twice here, and under a second CPython 3.11."""
    mine = capped_corpus_hash()
    assert len(mine) == 64, mine
    assert mine == capped_corpus_hash(), "a capped walk is not deterministic across runs"
    label = f"CPython {sys.version_info.major}.{sys.version_info.minor}"
    print(f"capped walk hash -- {label}: {mine}")

    second = _second_interpreter()
    if second is None:
        return
    prefix, source, version = second
    core = ROOT.parent / "word-extract" / "docextract-core"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(core)])}
    script = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'tests').replace(os.sep, '/')!r});"
        " import test_limits; print('capped walk hash:', test_limits.capped_corpus_hash())"
    )
    completed = subprocess.run(
        [*prefix, "-c", script], cwd=str(ROOT), capture_output=True, text=True, env=env
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    theirs = next(
        line.split(":", 1)[1].strip()
        for line in completed.stdout.splitlines()
        if line.startswith("capped walk hash:")
    )
    assert theirs == mine, (
        f"the capped walk hash differs between {label} and CPython {version} ({source}): "
        f"{mine} vs {theirs}"
    )


def _second_interpreter() -> tuple[list[str], str, str] | None:
    """A CPython 3.11 that can also run *this* module (so it must import pytest), or ``None``.

    ``runboth.find_python311`` is the project's own selector; on a machine whose 3.11 is a
    bare interpreter (no pytest) the two documentation venvs are tried next, and when no
    candidate can import the harness the cross-interpreter half is **printed and skipped**
    rather than failed -- the runboth rule: never silently claim "both".
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import runboth

    candidates: list[tuple[list[str], str]] = []
    found = runboth.find_python311()
    if found is not None:
        candidates.append((found[0], found[1]))
    for name in ("wbv311", "wbv"):
        venv = Path(os.environ.get("TEMP", "")) / name / "Scripts" / "python.exe"
        if venv.is_file():
            candidates.append(([str(venv)], f"the {name} venv"))
    for prefix, source in candidates:
        probe = subprocess.run(
            [*prefix, "-c", "import pytest, sys; print(sys.version_info[:3])"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return prefix, source, probe.stdout.strip()
        print(f"limits: {source} cannot import pytest -- trying the next interpreter")
    print("limits: no CPython 3.11 with the harness found -- cross-interpreter hash not checked")
    return None


def capped_corpus_hash() -> str:
    """A sha256 over the capped walks that must reproduce byte for byte.

    Every cap fixture under the cap it was built for, plus inline messages at each boundary
    -- parts, spans, decode chains, gaps, regions and unknown sections.
    """
    cases: list[tuple[bytes, dict[str, int]]] = [
        (_fixture(path), over) for over in _cap_fixture_limits() for path in _cap_fixture_paths()
    ]
    cases += [
        (nested(4), {"max_depth": 3}),
        (fan_out(4), {"max_parts": 3}),
        (header_block(8)[0], {"max_header_bytes": 8}),
        (encoded_part(256), {"max_decoded_part_bytes": 255}),
        (encoded_part(256, cte=b"quoted-printable"), {"max_decoded_total_bytes": 100}),
        (nested(4), {"max_depth": 2, "max_parts": 2}),
    ]
    digest = hashlib.sha256()
    for raw, over in cases:
        result = walk(EmlContainer(raw), limits=limits(**over))
        digest.update(repr(sorted(over.items())).encode())
        digest.update(repr(result).encode())
    return digest.hexdigest()


def _cap_fixture_paths() -> list[str]:
    return sorted(CAP_FIXTURES.values()) + ["raw/cap_encoded_word_bomb.eml"]


def _cap_fixture_limits() -> list[dict[str, int]]:
    return [
        {"max_depth": 5},
        {"max_parts": 9},
        {"max_header_bytes": 5981},
        {"max_decoded_part_bytes": 4095},
        {"max_header_bytes": 302},
    ]


def test_no_mutated_fixture_and_random_limits_raises_and_the_bytes_tile() -> None:
    """A seeded loop: mutated fixture bytes under random limits never raise and always tile."""
    rng = random.Random(15_0300)
    paths = sorted(
        path for path in FIXTURES.rglob("*.eml") if "real" not in path.relative_to(FIXTURES).parts
    )
    problems: list[str] = []
    for path in paths:
        raw = bytearray(path.read_bytes())
        if raw:
            start = rng.randrange(len(raw))
            raw[start : start + 3] = bytes(rng.randrange(256) for _ in range(3))
        mutated = bytes(raw)
        for _ in range(2):
            over = {
                "max_depth": rng.choice([1, 2, 5, 40]),
                "max_parts": rng.choice([1, 2, 6, 200]),
                "max_header_bytes": rng.choice([1, 7, 500, 65536]),
                "max_decoded_part_bytes": rng.choice([1, 5, 900, 1 << 20]),
                "max_decoded_total_bytes": rng.choice([1, 5, 900, 1 << 20]),
            }
            try:
                result = walk(EmlContainer(mutated), limits=limits(**over))
            except Exception as error:  # noqa: BLE001 -- the property is "never raises"
                problems.append(f"{path.name} {over}: raised {type(error).__name__}: {error}")
                continue
            problems.extend(
                f"{path.name} {over}: {hole}" for hole in gates.holes(result.regions, len(mutated))
            )
            pairs = {(section.value.reason_id, section.section) for section in cap_sections(result)}
            problems.extend(
                f"{path.name} {over}: {region.kind} at {region.path} has no reason entry"
                for region in cap_regions(result)
                if (region.kind, region.path) not in pairs
            )
            problems.extend(
                f"{path.name} {over}: {section.section} has no cap region"
                for section in cap_sections(result)
                if (section.value.reason_id, section.section)
                not in {(region.kind, region.path) for region in cap_regions(result)}
            )
    assert problems == []


def test_the_unbounded_walk_records_no_cap_and_equals_the_untrusted_walk() -> None:
    """``limits=None`` is unbounded, and the shipped defaults record nothing on the corpus.

    This is also the proof that the bounded (streamed) decoder agrees with the whole-buffer
    one on every fixture: the approved defaults leave every decode under its cap.
    """
    for path in sorted(FIXTURES.rglob("*.eml")):
        if "real" in path.relative_to(FIXTURES).parts:
            continue
        raw = path.read_bytes()
        unbounded = walk(EmlContainer(raw))
        assert cap_regions(unbounded) == [] and cap_sections(unbounded) == [], path.name
        assert unbounded.unknown_sections[-1].section == UNBUILT_SECTIONS[-1], path.name
        assert walk(EmlContainer(raw), limits=Limits.untrusted()) == unbounded, path.name


# ----------------------------------------------- item 3: work stays linear under a cap


def test_a_boundary_storm_is_linear_under_a_cap() -> None:
    """100 000 boundary lines are one linear pass, never quadratic in the delimiters."""
    small = boundary_storm(50_000)
    large = boundary_storm(100_000)
    WORK.reset()
    walk(EmlContainer(small), limits=limits(max_parts=20))
    cheap = WORK.count()
    WORK.reset()
    result = walk(EmlContainer(large), limits=limits(max_parts=20))
    dear = WORK.count()
    lines = large.count(b"\n")
    assert cheap > 4 * 50_000, f"the counter is not counting: {cheap}"
    assert dear <= 8 * lines, f"{dear} steps for {lines} lines"
    assert dear <= 5 * cheap, f"doubling the storm cost {cheap} -> {dear} steps"
    assert len(result.parts) == 20, "the part cap does not bound the parts emitted"


def test_a_deep_nesting_bomb_is_bounded_by_the_depth_cap() -> None:
    """20 000 nested multipart declarations cost the cap's levels, not the input's depth."""
    small = nested(1_000)
    large = nested(20_000)
    WORK.reset()
    walk(EmlContainer(small), limits=limits(max_depth=8))
    cheap_work = WORK.count()
    WORK.reset()
    result = walk(EmlContainer(large), limits=limits(max_depth=8))
    dear_work = WORK.count()
    assert [part.path for part in result.parts] == [
        "1",
        "1.1",
        "1.1.1",
        "1.1.1.1",
        "1.1.1.1.1",
        "1.1.1.1.1.1",
        "1.1.1.1.1.1.1",
        "1.1.1.1.1.1.1.1",
    ], "the depth cap, not the input, must bound the parts"
    assert [(region.kind, region.path) for region in cap_regions(result)] == [
        (CAP_REASON_DEPTH, "1.1.1.1.1.1.1.1.1")
    ]
    # Each level's body is scanned once, so the work is at most (lines per level) x (levels
    # walked) = 4 x 9 x N; the bound doubles that for slack. A quadratic pass would be 4e8.
    assert dear_work <= 4 * 2 * (8 + 1) * 20_000, f"{dear_work} steps for 20 000 levels"
    assert dear_work <= 25 * cheap_work, f"20x the input cost {cheap_work} -> {dear_work} steps"


# ------------------------------------------- item 7: the mutants, one per gate


def test_the_depth_cap_off_by_one_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allowing one level over the cap emits one more part and drops the reason."""
    raw = nested(2)
    assert cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2) == []
    flags = {"reached": 0}

    def one_over(real, limits_, depth):
        return limits_ is None or depth <= limits_.max_depth + 1

    _patch(monkeypatch, "_depth_allows", one_over, flags)
    problems = cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2)
    assert flags["reached"] > 0, "the depth seam was never reached"
    assert problems, "the off-by-one depth cap was NOT caught"
    assert any(CAP_REASON_DEPTH in problem for problem in problems), problems
    assert any("1.1.1" in problem for problem in problems), problems


def test_the_part_count_cap_checked_after_building_the_parts_mutant_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cap that never skips a part emits every part and records no reason."""
    raw = fan_out(2)
    assert (
        cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_PART_COUNT, "1.2")], max_parts=2) == []
    )
    flags = {"reached": 0}
    _patch(monkeypatch, "_part_count_allows", lambda real, limits_, emitted: True, flags)
    problems = cap_gate(
        raw, parts=["1", "1.1"], caps=[(CAP_REASON_PART_COUNT, "1.2")], max_parts=2
    )
    assert flags["reached"] > 0, "the part-count seam was never reached"
    assert problems, "a part cap that emits every part was NOT caught"
    assert any(CAP_REASON_PART_COUNT in problem for problem in problems), problems


def test_the_header_cap_checked_after_the_fields_mutant_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the cap off, the enormous header block is parsed field by field."""
    raw, size = header_block(200)
    assert (
        cap_gate(raw, parts=[], caps=[(CAP_REASON_HEADER_BYTES, "1")], max_header_bytes=size - 1)
        == []
    )
    flags = {"reached": 0}
    _patch(monkeypatch, "_header_bytes_allows", lambda real, limits_, length: True, flags)
    parsed = walk(EmlContainer(raw), limits=limits(max_header_bytes=size - 1))
    problems = cap_gate(
        raw, parts=[], caps=[(CAP_REASON_HEADER_BYTES, "1")], max_header_bytes=size - 1
    )
    assert flags["reached"] > 0, "the header-bytes seam was never reached"
    assert problems, "a header cap that parses every field was NOT caught"
    assert len(parsed.parts) == 1 and len(parsed.parts[0].header_fields) == 200


def test_a_truncated_body_mutant_is_refused_by_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body truncated at the cap instead of skipped would report a content sha256."""
    raw = encoded_part(4096)
    limits_ = limits(max_decoded_part_bytes=1024)
    assert (
        cap_gate(raw, parts=["1"], caps=[(CAP_REASON_SIZE, "1")], max_decoded_part_bytes=1024) == []
    )
    flags = {"reached": 0}
    real_decode = walk_module._decode_cte

    def truncating(payload, declared, *, limit=None):
        used, decoded, fired, gap = real_decode(payload, declared, limit=limit)
        if decoded is None and limit is not None:
            flags["reached"] += 1
            _whole, full, _fired, _gap = real_decode(payload, declared, limit=None)
            return used or _whole, full[:limit], fired, gap
        return used, decoded, fired, gap

    monkeypatch.setattr(walk_module, "_decode_cte", truncating)
    result = walk(EmlContainer(raw), limits=limits_)
    assert flags["reached"] > 0, "the truncating decoder was never reached"
    problems = [
        f"1: content_sha256 {part.body_sha256} is not unknown"
        for part in result.parts
        if part.path == "1" and part.body_sha256 is not None
    ]
    assert problems, "a truncated body was accepted as the part's"
    assert "content_sha256" in problems[0]


def test_a_total_cap_that_does_not_accumulate_mutant_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A total cap that forgets what it already decoded skips no later part."""
    raw = fan_out(3)
    caps = [(CAP_REASON_TOTAL_SIZE, "1.3")]
    assert (
        cap_gate(raw, parts=["1", "1.1", "1.2", "1.3"], caps=caps, max_decoded_total_bytes=18) == []
    )
    flags = {"reached": 0}

    def no_accumulator(real, state):
        return (
            None if state.limits is None else state.limits.max_decoded_part_bytes,
            CAP_REASON_SIZE,
        )

    _patch(monkeypatch, "_decode_budget", no_accumulator, flags)
    problems = cap_gate(
        raw, parts=["1", "1.1", "1.2", "1.3"], caps=caps, max_decoded_total_bytes=18
    )
    assert flags["reached"] > 0, "the decode-budget seam was never reached"
    assert problems, "a total cap that never accumulates was NOT caught"


def test_a_cap_hit_that_raises_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cap hit is a recorded state: raising instead fails the gate loudly."""
    raw = nested(2)
    assert cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2) == []
    flags = {"reached": 0}

    def raiser(real, regions, caps, reason, locator, span):
        raise RuntimeError(f"cap {reason} at {locator}")

    _patch(monkeypatch, "_cap_hit", raiser, flags)
    problems = cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2)
    assert flags["reached"] > 0, "the cap seam was never reached"
    assert problems and "raised" in problems[0], problems


def test_a_dropped_cap_region_mutant_fails_no_silent_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dropping the skipped bytes from the regions leaves a hole the gate reports."""
    raw = nested(2)
    assert cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2) == []
    flags = {"reached": 0}

    def records_only_the_reason(real, regions, caps, reason, locator, span):
        flags["reached"] += 1
        caps.append(
            UnknownSection(
                section=locator, value=TriValue(state=TriState.UNKNOWN, reason_id=reason)
            )
        )

    _patch(monkeypatch, "_cap_hit", records_only_the_reason, flags)
    result = walk(EmlContainer(raw), limits=limits(max_depth=2))
    assert flags["reached"] > 0, "the cap seam was never reached"
    holes = gates.holes(result.regions, len(raw))
    assert holes, "dropping the skipped region was NOT caught"
    assert "unaccounted" in str(holes[0])


def test_a_wrong_reason_id_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recording the wrong closed reason for a cap flips the gate naming the cap."""
    raw = nested(2)
    assert cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2) == []
    flags = {"reached": 0}

    def wrong(real, regions, caps, reason, locator, span):
        return real(regions, caps, CAP_REASON_PART_COUNT, locator, span)

    _patch(monkeypatch, "_cap_hit", wrong, flags)
    problems = cap_gate(raw, parts=["1", "1.1"], caps=[(CAP_REASON_DEPTH, "1.1.1")], max_depth=2)
    assert flags["reached"] > 0, "the cap seam was never reached"
    assert problems and CAP_REASON_PART_COUNT in problems[0], problems


def test_a_cap_value_not_the_callers_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reason mapped to another Limits field records a cap value the caller never set."""
    raw = nested(2)
    limits_ = limits(max_depth=2, max_parts=7)
    assert [
        record.cap_value_bytes
        for _, record in recorded(walk(EmlContainer(raw), limits=limits_), limits_)
    ] == [2]

    class Counting(dict):
        def __init__(self, source: dict) -> None:
            super().__init__(source)
            self.reached = 0

        def __getitem__(self, key: str) -> str:
            self.reached += 1
            return super().__getitem__(key)

    mutant = Counting({**walk_module.CAP_LIMIT_FIELDS, CAP_REASON_DEPTH: "max_parts"})
    monkeypatch.setattr(walk_module, "CAP_LIMIT_FIELDS", mutant)
    values = [
        record.cap_value_bytes
        for _, record in recorded(walk(EmlContainer(raw), limits=limits_), limits_)
    ]
    assert mutant.reached > 0, "the reason-to-field map was never reached"
    assert values == [7] and values != [2], "a cap value that is not the caller's was NOT caught"


def test_every_cap_reason_has_a_mutation_case() -> None:
    """The catalogue: each of the five closed cap reasons has a mutation case above."""
    assert set(CAP_MUTATION_CASES) == set(CAP_REASONS)
    missing = [name for name in CAP_MUTATION_CASES.values() if name not in globals()]
    assert missing == [], f"cap reasons whose case does not exist: {missing}"
    # The five fixtures cover four caps by construction (the bomb's cap is its header block).
    assert set(CAP_FIXTURES) == {
        CAP_REASON_DEPTH,
        CAP_REASON_PART_COUNT,
        CAP_REASON_HEADER_BYTES,
        CAP_REASON_SIZE,
    }

