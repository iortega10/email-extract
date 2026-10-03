"""Turn 0.2: the walker fails open on malformed multipart bytes (design D2/D9).

A malformed message must be *recorded*, never crash the run and never lose a byte. The first case
here is a defect found by mutation fuzzing in review: two adjacent delimiters (an empty part) made
the walker attach the line ending in front of the second delimiter twice, so the regions overlapped
and a span length went negative (``ValueError: raw_span.length must be an int >= 0``).

The seeded fuzz below is deterministic (a fixed seed and a fixed mutation recipe) and small enough
to stay fast; its seeds are hand-written byte strings, never mail.
"""

from __future__ import annotations

import random

import pytest

from emailextract.container import EmlContainer
from emailextract.walk import walk

HEAD = b"From: a@example.test\r\nSubject: s\r\nMIME-Version: 1.0\r\n"


def _tiles(raw: bytes) -> None:
    result = walk(EmlContainer(raw))
    position = 0
    for region in sorted(result.regions, key=lambda r: r.span.offset):
        assert region.span.offset == position, f"{region.kind}: gap or overlap at {position}"
        assert region.span.length >= 0
        position = region.span.end
    assert position == len(raw), f"regions end at {position} of {len(raw)}"


@pytest.mark.parametrize(
    "raw",
    [
        # The minimal repro: LF-only endings, an empty part between two delimiters.
        b"0\nContent-Type:multipart/;boundary=b\n\n--b\n--b--",
        # The same with CRLF, and with a boundary full of regex metacharacters.
        b"0\r\nContent-Type:multipart/;boundary=b\r\n\r\n--b\r\n--b--",
        b'0\nContent-Type:multipart/;boundary="a.+*?[b"\n\n--a.+*?[b\n--a.+*?[b--',
        # Several empty parts in a row, then a real one.
        HEAD + b"Content-Type: multipart/mixed; boundary=b\r\n\r\n--b\r\n--b\r\n--b\r\n\r\nx\r\n--b--\r\n",
        # An empty part with no close delimiter at all.
        HEAD + b"Content-Type: multipart/mixed; boundary=b\r\n\r\n--b\r\n--b\r\n",
    ],
)
def test_adjacent_delimiters_are_an_empty_part_not_a_crash(raw: bytes) -> None:
    _tiles(raw)


SEEDS = (
    HEAD + b"Content-Type: text/plain\r\n\r\nhello\r\n",
    b"From: a@x.test\nSubject: s\n\nbody\n",
    HEAD
    + b"Content-Type: multipart/mixed; boundary=b1\r\n\r\npre\r\n--b1\r\nContent-Type: text/plain\r\n\r\nx"
    + b"\r\n--b1\r\nContent-Type: text/html\r\n\r\n<p>y</p>\r\n--b1--\r\nepi\r\n",
    HEAD
    + b"Content-Type: multipart/mixed; boundary=b\r\n\r\n--b\r\nContent-Type: multipart/alternative;"
    + b" boundary=b\r\n\r\n--b\r\nContent-Type: text/plain\r\n\r\nx\r\n--b--\r\n--b--\r\n",
    HEAD + b"Content-Type: multipart/mixed; boundary=b\r\n\r\n--b\r\nContent-Type: text/plain\r\n\r\nx\r\n",
    HEAD + b"Content-Type: text/plain\r\nContent-Transfer-Encoding: base64\r\n\r\n!!!!notb64\r\n",
)


def _mutate(raw: bytes, rng: random.Random) -> bytes:
    data = bytearray(raw)
    for _ in range(rng.randint(1, 4)):
        operation = rng.choice("dis")
        index = rng.randrange(len(data)) if data else 0
        if operation == "d" and data:
            del data[index : index + rng.randint(1, 3)]
        elif operation == "i":
            data[index:index] = bytes(
                rng.choice([13, 10, 45, 0, 255, 58, 32, 9]) for _ in range(rng.randint(1, 3))
            )
        elif data:
            data[index] = rng.randrange(256)
    return bytes(data)


def test_a_seeded_mutation_fuzz_never_crashes_and_never_loses_a_byte() -> None:
    """Every mutant either walks with regions that tile the message exactly or the test names it.

    1,800 mutants (six seeds, 300 each) from a fixed seed: the same mutants on every run and on
    every interpreter, so a failure is reproducible from the printed mutant alone."""
    rng = random.Random(20261003)
    for seed in SEEDS:
        for _ in range(300):
            mutant = _mutate(seed, rng)
            try:
                _tiles(mutant)
            except Exception as error:  # noqa: BLE001 -- report the input, not a bare traceback
                pytest.fail(f"{type(error).__name__}: {error} for {mutant!r}")


def test_the_same_mutant_walks_to_the_same_result_twice() -> None:
    rng = random.Random(7)
    for seed in SEEDS:
        mutant = _mutate(seed, rng)
        assert walk(EmlContainer(mutant)) == walk(EmlContainer(mutant))
