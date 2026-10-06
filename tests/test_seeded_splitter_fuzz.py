"""Turn 1.10b B: the seeded differential fuzz of the independent byte-level splitter.

The third independent check (build spec, "The independent checks"): ``tests/support/
boundary_splitter.py`` reads a message's multipart framing from **RFC 2046 5.1** alone and
knows nothing about ``emailextract``. This module is the *fuzz* that runs it against the
walker: a seeded stream of mutated messages, and for each mutant a comparison of the four
quantities the spec names --

* the ordered list of part byte spans (locator -> ``(start, end)``);
* the part count;
* the preamble and epilogue **length** per multipart;
* the boundary-delimiter **line spans**.

The corpus is the frozen fixture set itself (never new fixtures): every fixture whose
top-level part the splitter reads as a multipart, mutated **in memory** by the seeded
generator below. Mutants are grouped into four classes, because the RFC is not equally
clear about all of them and the spec says which is which:

``GATED``
    The RFC is decisive: both readers must report the same four quantities. Covers
    flipping a ``--``, inserting or deleting the CRLF before a delimiter line,
    truncating mid-boundary, duplicating a delimiter line, transport padding on a
    delimiter line, appending after the close delimiter, and injecting a *valid*
    delimiter line inside a part body (content that really does contain the boundary --
    both readers must agree about what it does, which is the gate).
``INVARIANT``
    Byte-for-byte length-preserving edits **inside an encoded body** (a base64 character
    swapped for another, a space for a tab): they must leave *all four* quantities
    identical to the unmutated fixture, offsets included. Transport padding is checked
    the same way but only in its offset-free *shape* (a padding byte is inserted, so
    later offsets legitimately shift; RFC 2046 5.1.1 says the padding itself is ignored).
``NO_CLOSE``
    Removing the closing delimiter's ``--`` is **not** compared as four quantities: the
    rule the spec names is the gap, so this class gates ``body.boundary_disagreement``
    (and the splitter's ``closed is False``) instead.
``EXCLUDED``
    Run -- they must not crash -- but their quantities are **not** compared, with the
    reason recorded in :data:`EXCLUDED_REASONS`: rotating a delimiter line's line ending
    (the splitter's own line model is CRLF-only, decision 17's honest limit) and a
    delimiter line followed by anything but LWSP (RFC-ambiguous).

Honest limit, restated from the spec: this check's independence is **code lineage, not a
different author**. It shares the RFC with ``walk.py`` and was written from the same
paragraph of the build spec, so a misreading common to both would agree here and still be
wrong; the owner's structure-only probe is the strongest common-mode breaker.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import boundary_splitter as bs  # noqa: E402

from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.parse import NAMED_ERROR_REASONS, Limits, NamedError, parse  # noqa: E402
from emailextract.walk import GAP_BODY_BOUNDARY_DISAGREEMENT, walk  # noqa: E402

#: The fuzz seed: the same mutants on every run and on every interpreter, so a failure is
#: reproducible from the printed seed and case id alone. `<turn>_<serial>`, the repo's
#: convention for a seeded fuzz (``15_0300`` is the limits turn, this is 1.10b).
FUZZ_SEED = 10_1002

#: The mutant classes. Only the first two are compared as four quantities.
GATED = "gated"
INVARIANT = "invariant"
NO_CLOSE = "no_close"
EXCLUDED = "excluded"

#: Why an ``EXCLUDED`` mutant is run but never gated on the four quantities. Each reason is
#: the spec's own wording, so a reader can check the exclusion rather than trust it.
EXCLUDED_REASONS = {
    "rotate_line_endings": "line framing: the splitter's line model is CRLF-only (decision 17)",
    "inject_delimiter_like_text": "a delimiter line followed by non-LWSP is RFC-ambiguous",
}

#: Every mutation kind this generator can emit, and the class each one belongs to.
KIND_CLASS = {
    "flip_dashes": GATED,
    "insert_crlf": GATED,
    "delete_crlf": GATED,
    "truncate_mid_boundary": GATED,
    "duplicate_delimiter": GATED,
    "transport_padding": GATED,
    "append_after_close": GATED,
    "inject_valid_delimiter": GATED,
    "remove_close": NO_CLOSE,
    "rotate_line_endings": EXCLUDED,
    "inject_delimiter_like_text": EXCLUDED,
    "base64_char_swap": INVARIANT,
    "whitespace_swap": INVARIANT,
}

_CRLF = b"\r\n"
_DASH = b"--"
_BASE64 = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

#: The four quantities, as the keys both readings use.
_FOUR = ("spans", "count", "preamble", "epilogue", "delimiters")


@dataclass(frozen=True)
class Mutant:
    """One generated mutant: where it came from, what it is, and how it may be gated."""

    fixture: str
    kind: str
    raw: bytes
    klass: str

    @property
    def where(self) -> str:
        return f"{self.fixture}#{self.kind}"


# --------------------------------------------------------------- the two readings


def splitter_reading(raw: bytes) -> dict:
    """The four quantities as the **independent splitter** reads them, keyed by locator."""
    out: dict = {
        "spans": {},
        "count": 0,
        "preamble": {},
        "epilogue": {},
        "delimiters": {},
        "closed": {},
    }

    def visit(node: "bs.Split | bs.Leaf", locator: str) -> None:
        out["spans"][locator] = (node.start, node.end)
        out["count"] += 1
        if isinstance(node, bs.Leaf):
            return
        # The walker emits a region only when it has bytes, so an empty preamble, an empty
        # epilogue and an empty delimiter list are *absent* keys on its side: record the
        # same shape here, or the two readings differ by representation, not by bytes.
        if node.preamble[1] > node.preamble[0]:
            out["preamble"][locator] = node.preamble[1] - node.preamble[0]
        if node.epilogue[1] > node.epilogue[0]:
            out["epilogue"][locator] = node.epilogue[1] - node.epilogue[0]
        if node.delimiters:
            out["delimiters"][locator] = sorted(node.delimiters)
        out["closed"][locator] = node.closed
        for index, child in enumerate(node.parts):
            visit(child, f"{locator}.{index + 1}")

    node = bs.split_message(raw)
    visit(node, "1")
    return out


def walker_reading(raw: bytes) -> dict:
    """The same four quantities as the **walker** reads them, from ``WalkResult``.

    The walk is unbounded: the splitter has no caps, so a bounded walk would be comparing
    a capped reading against an uncapped one and any disagreement would be the cap's.
    """
    result = walk(EmlContainer(memory_bytes(raw)))
    out: dict = {
        "spans": {},
        "count": 0,
        "preamble": {},
        "epilogue": {},
        "delimiters": {},
        "closed": {},
    }
    for part in result.parts:
        out["spans"][part.path] = (part.raw_span.offset, part.raw_span.end)
        out["count"] += 1
    for region in result.regions:
        if region.kind == "preamble":
            out["preamble"][region.path] = out["preamble"].get(region.path, 0) + region.span.length
        elif region.kind == "epilogue":
            out["epilogue"][region.path] = out["epilogue"].get(region.path, 0) + region.span.length
        elif region.kind == "delimiter":
            out["delimiters"].setdefault(region.path, []).append(
                (region.span.offset, region.span.end)
            )
    for locator in out["delimiters"]:
        out["delimiters"][locator] = sorted(out["delimiters"][locator])
    return out


def _disagreements(left: dict, right: dict) -> list[str]:
    """Every quantity the two readings disagree about, as printable lines."""
    problems: list[str] = []
    for key in _FOUR:
        if left[key] != right[key]:
            problems.append(f"{key}: splitter={left[key]!r} walker={right[key]!r}")
    return problems


def _shape(reading: dict) -> dict:
    """The same quantities with **no absolute offsets**: lengths and counts only.

    A mutation that inserts bytes (transport padding) shifts every later offset for both
    readers, and the padding byte is inside the delimiter line, so that line's own size
    grows: only this offset-free shape is padding-invariant, and RFC 2046 5.1.1 says the
    padding must not create a delimiter, drop a part or move a body byte. The root part
    (locator ``1``) is left out because its span **is** the message, so it grows by the
    padded byte by construction; every contained part's length is padding-invariant.
    """
    return {
        "part_lengths": {
            locator: end - start
            for locator, (start, end) in reading["spans"].items()
            if locator != "1"
        },
        "count": reading["count"],
        "preamble": dict(reading["preamble"]),
        "epilogue": dict(reading["epilogue"]),
        "delimiter_counts": {
            locator: len(spans) for locator, spans in reading["delimiters"].items()
        },
        "closed": dict(reading["closed"]),
    }


# ---------------------------------------------------------------- the corpus


def _multipart_fixtures() -> list[Path]:
    """Every fixture the splitter reads as a top-level multipart, in a stable order.

    ``fixtures/real/`` is git-ignored and never read (privacy); the corpus is the frozen
    synthetic set, so this fuzz needs no fixture and adds none.
    """
    found: list[Path] = []
    for directory in ("generated", "raw"):
        for path in sorted((ROOT / "fixtures" / directory).glob("*.eml")):
            try:
                node = bs.split_message(path.read_bytes())
            except Exception as error:  # noqa: BLE001 -- a corpus that cannot be read is the finding
                pytest.fail(f"the splitter cannot read the corpus fixture {path.name}: {error}")
            if isinstance(node, bs.Split):
                found.append(path)
    return found


def _leaves(node: "bs.Split | bs.Leaf", locator: str = "1") -> list[tuple[str, "bs.Leaf"]]:
    if isinstance(node, bs.Leaf):
        return [(locator, node)]
    out: list[tuple[str, bs.Leaf]] = []
    for index, child in enumerate(node.parts):
        out.extend(_leaves(child, f"{locator}.{index + 1}"))
    return out


def _leaf_body(raw: bytes, leaf: "bs.Leaf") -> tuple[int, int] | None:
    """The byte region of a leaf's **body** (after its blank line), or ``None``."""
    blank = raw.find(b"\r\n\r\n", leaf.start, leaf.end)
    if blank == -1:
        return None
    return blank + 4, leaf.end


def _body_keeps_the_length(raw: bytes, body: tuple[int, int], kind: str) -> bytes | None:
    """One length-preserving, body-only edit: a base64 character or a space swapped."""
    start, end = body
    if kind == "base64_char_swap":
        for index in range(start, end):
            if raw[index:index + 1] in _BASE64:
                return raw[:index] + bytes([_BASE64[(index + 7) % len(_BASE64)]]) + raw[index + 1:]
        return None
    for index in range(start, end):
        if raw[index:index + 1] == b" ":
            return raw[:index] + b"\t" + raw[index + 1:]
    return None


def _mutants_for_fixture(stem: str, raw: bytes, node: "bs.Split", rng: random.Random) -> list[Mutant]:
    """One mutant per mutation kind this fixture can carry, at rng-chosen positions."""
    delimiters = list(node.delimiters)
    boundary = node.boundary
    out: list[Mutant] = []

    def add(kind: str, mutant: bytes) -> None:
        out.append(Mutant(fixture=stem, kind=kind, raw=mutant, klass=KIND_CLASS[kind]))

    target = rng.choice(delimiters)
    line = raw[target[0]:target[1]]

    # flip a `--` inside a delimiter line
    at = target[0] + line.index(_DASH + boundary)
    add("flip_dashes", raw[:at] + b"-x" + raw[at + 2:])

    # insert an extra CRLF in front of a delimiter line (it lands in the chunk before it)
    add("insert_crlf", raw[:target[0]] + _CRLF + raw[target[0]:])

    # delete the CRLF that opens a delimiter line: the line merges with the one before it
    if raw[target[0]:target[0] + 2] == _CRLF:
        add("delete_crlf", raw[:target[0]] + raw[target[0] + 2:])
    else:
        wrapped = [span for span in delimiters if raw[span[0]:span[0] + 2] == _CRLF]
        if wrapped:
            span = rng.choice(wrapped)
            add("delete_crlf", raw[:span[0]] + raw[span[0] + 2:])

    # truncate the message inside the boundary token (the partial token is no delimiter)
    cut = target[0] + len(_DASH) + max(1, len(boundary) // 2)
    add("truncate_mid_boundary", raw[:cut])

    # duplicate a delimiter line: a copy of an open line in front of the closing one
    close = delimiters[-1]
    openers = [span for span in delimiters if span is not close]
    if openers:
        span = rng.choice(openers)
        copy = raw[span[0]:span[1]] if raw[span[0]:span[0] + 2] == _CRLF else _CRLF + raw[span[0]:span[1]]
        add("duplicate_delimiter", raw[:close[0]] + copy + raw[close[0]:])

    # rotate a delimiter line's line ending (excluded: the splitter is CRLF-only)
    if raw[target[1] - 2:target[1]] == _CRLF:
        add("rotate_line_endings", raw[:target[1] - 2] + b"\n" + raw[target[1]:])

    # change transport padding: a tab between the delimiter line's token(s) and its CRLF
    pad_at = target[1] - 2 if raw[target[1] - 2:target[1]] == _CRLF else target[1]
    add("transport_padding", raw[:pad_at] + b"\t" + raw[pad_at:])

    # append after the close delimiter: it is epilogue for both readers
    add("append_after_close", raw + b"a trailer appended after the close delimiter\r\n")

    # remove the close delimiter's `--`: no close, gate on the gap instead
    head = raw[close[0]:close[1]]
    terminator = _CRLF if head.endswith(_CRLF) else b""
    line_end = head[: len(head) - len(terminator)]
    token = line_end.rstrip(b" \t")
    if token.endswith(_DASH) and len(token) > len(_DASH):
        new_head = token[: -len(_DASH)] + line_end[len(token):] + terminator
        add("remove_close", raw[:close[0]] + new_head + raw[close[1]:])

    # inject a real (gated) and a near-miss (excluded) delimiter line inside a body
    leaves = [leaf for _locator, leaf in _leaves(node)]
    if leaves:
        leaf = rng.choice(leaves)
        body = _leaf_body(raw, leaf)
        if body is not None and body[1] - body[0] > 4:
            spot = rng.randrange(body[0] + 1, body[1] - 3)
            line_in = _CRLF + _DASH + boundary + _CRLF
            add("inject_valid_delimiter", raw[:spot] + line_in + raw[spot:])
            add(
                "inject_delimiter_like_text",
                raw[:spot] + _CRLF + _DASH + boundary + b" x" + raw[spot:],
            )

    # length-preserving edits inside an encoded body: no quantity may move at all
    bodies = [
        body
        for _locator, leaf in _leaves(node)
        if (body := _leaf_body(raw, leaf)) is not None and body[1] - body[0] > 4
    ]
    if bodies:
        body = rng.choice(bodies)
        for kind in ("base64_char_swap", "whitespace_swap"):
            mutant = _body_keeps_the_length(raw, body, kind)
            if mutant is not None:
                add(kind, mutant)
    return out


def _build_mutants() -> list[Mutant]:
    rng = random.Random(FUZZ_SEED)
    mutants: list[Mutant] = []
    for path in _multipart_fixtures():
        raw = path.read_bytes()
        node = bs.split_message(raw)
        assert isinstance(node, bs.Split)
        mutants.extend(_mutants_for_fixture(path.stem, raw, node, rng))
    return mutants


MUTANTS = _build_mutants()

#: The unmutated reading of each corpus fixture: what an ``INVARIANT`` mutant must not move.
BASELINE = {path.stem: splitter_reading(path.read_bytes()) for path in _multipart_fixtures()}


# ------------------------------------------------------------------- the tests


def test_boundary_mutations_change_no_four_quantity() -> None:
    """Every gated mutant: the splitter and the walker agree on all four quantities.

    The two readers disagree about nothing here -- the ordered part spans, the part count,
    the preamble and epilogue length per multipart, and the boundary-delimiter line spans.
    A ``GATED`` mutation may move those quantities (it changes the message), but it must
    move them **identically** for both readers; an ``INVARIANT`` mutation must not move
    them at all, and a transport-padding mutant must not move their offset-free shape.
    """
    problems: list[str] = []
    seen = {GATED: 0, INVARIANT: 0, "transport_padding": 0, NO_CLOSE: 0, EXCLUDED: 0}
    for mutant in MUTANTS:
        if mutant.klass in (EXCLUDED, NO_CLOSE):
            seen[mutant.klass] += 1
            continue
        split = splitter_reading(mutant.raw)
        walked = walker_reading(mutant.raw)
        for line in _disagreements(split, walked):
            problems.append(f"{mutant.where} seed={FUZZ_SEED}: {line}")
        seen[mutant.klass] += 1
        if mutant.klass == INVARIANT and split != BASELINE[mutant.fixture]:
            problems.append(f"{mutant.where} seed={FUZZ_SEED}: a body-only edit moved a quantity")
        if mutant.kind == "transport_padding":
            seen["transport_padding"] += 1
            if _shape(split) != _shape(BASELINE[mutant.fixture]):
                problems.append(f"{mutant.where} seed={FUZZ_SEED}: padding changed the shape")

    assert not problems, "\n".join(problems[:20])
    assert seen[GATED] > 100 and seen[INVARIANT] > 10, seen
    assert seen["transport_padding"] > 10 and seen[NO_CLOSE] > 10, seen


def test_mutants_return_the_declared_failure_type() -> None:
    """Every mutant is bounded: it returns, or it refuses by name -- it never crashes.

    Each mutant is driven through the **real entry path** (``parse``'s sniff, then the
    bounded walk) at :meth:`Limits.untrusted`. What comes back is a result or a
    :class:`NamedError` whose ``reason_id`` is in the closed ``NAMED_ERROR_REASONS``; any
    other ``Exception`` fails with the seed and the case, and ``MemoryError`` and
    ``RecursionError`` are named separately because they are the two ways a bounded
    resource would show up. ``BaseException`` is deliberately **not** caught. The
    ``NO_CLOSE`` class gates ``body.boundary_disagreement`` instead of the four quantities.
    """
    limits = Limits.untrusted()
    failures: list[str] = []
    excluded = {kind: 0 for kind in EXCLUDED_REASONS}
    assert set(KIND_CLASS) <= {mutant.kind for mutant in MUTANTS}, "a mutation kind never fired"
    for mutant in MUTANTS:
        if mutant.klass == EXCLUDED:
            excluded[mutant.kind] += 1
        try:
            decision = parse(mutant.raw, limits=limits)
            if decision.error is not None:
                assert decision.error.reason_id in NAMED_ERROR_REASONS, decision.error.reason_id
                continue
            result = walk(EmlContainer(memory_bytes(mutant.raw)), limits=limits)
        except NamedError as error:
            assert error.reason_id in NAMED_ERROR_REASONS, error.reason_id
            continue
        except (MemoryError, RecursionError) as error:
            failures.append(f"{mutant.where} seed={FUZZ_SEED}: {type(error).__name__}")
            continue
        except Exception as error:  # noqa: BLE001 -- the finding is the input, not a traceback
            failures.append(f"{mutant.where} seed={FUZZ_SEED}: {type(error).__name__}: {error}")
            continue
        if mutant.klass == NO_CLOSE:
            gaps = {gap for part in result.parts for gap in part.gaps}
            if GAP_BODY_BOUNDARY_DISAGREEMENT not in gaps:
                failures.append(
                    f"{mutant.where} seed={FUZZ_SEED}: no close delimiter and no "
                    f"{GAP_BODY_BOUNDARY_DISAGREEMENT} gap ({sorted(gaps)})"
                )

    assert not failures, "\n".join(failures[:20])
    assert sum(excluded.values()) > 10, excluded
    assert all(count > 0 for count in excluded.values()), excluded
