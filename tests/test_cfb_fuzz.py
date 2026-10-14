"""Turn 1b.3: the seeded fuzz -- every mutant of a fixture returns a closed outcome.

The fuzz is deterministic and clock-free: ``random.Random`` over a fixed, committed list
of integer seeds, one mutant per ``(base, seed)``, with no ``os.urandom`` and no wall
clock. It exists because the reader's author also wrote the writer, so a self-consistent
wrong reader would pass the table tests; random byte-level mutants are the breakers that
do not share an author.

Three bases (the v3 headers file, the v4 file and the mini-cutoff trio), 300 seeds each.
Every mutant must be exactly one of: a ``CfbRefusal`` with a reason in
``cfb.CFB_REFUSAL_REASONS``, an opened file whose every stream returns ``(bytes, fault)``
with ``fault in cfb.FAULT_KINDS``, or the same reading as the unmutated base. Any other
outcome -- an exception, ``MemoryError`` or ``RecursionError`` specifically -- fails with
the base, the seed and the operator in the message. The sector sum and the work-per-byte
budget are asserted on every mutant, not only on the fixtures.

The two declared tests are ``test_every_mutant_returns_a_closed_failure_or_the_same_document``
and ``test_the_work_per_byte_budget_holds``; ``test_the_numbers_are_stable_across_hash_seeds``
is the determinism check.
"""

from __future__ import annotations

import hashlib
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import make_msg_fixtures  # noqa: E402

from emailextract import cfb  # noqa: E402
from support import cfb_raw  # noqa: E402

#: The three bases: a v3 file, a v4 file, and the mini-cutoff trio.
BASES: tuple[str, ...] = ("msg_headers_only", "msg_v4_sectors", "msg_mini_cutoff_boundary")
#: The fixed, committed seed list -- one mutant per ``(base, seed)``.
MUTANT_SEEDS: tuple[int, ...] = tuple(range(300))
#: The mutation operators (build spec: at least these seven).
OPERATORS: tuple[str, ...] = (
    "fat_entry",
    "minifat_entry",
    "directory_link",
    "entry_start",
    "entry_size",
    "header_count",
    "sector_shift",
    "truncate",
)
#: The [MS-CFB] 2.2 header fields the count/start operator overwrites.
HEADER_COUNT_OFFSETS = (40, 44, 48, 60, 64, 68, 72)
#: The directory entry's left / right / child link offsets ([MS-CFB] 2.6.1).
DIRECTORY_LINK_OFFSETS = (68, 72, 76)
DIRECTORY_START_OFFSET = 116
DIRECTORY_SIZE_OFFSETS = (120, 124)
SECTOR_SHIFT_OFFSET = 26


def _rng(base_name: str, seed: int) -> random.Random:
    """A deterministic generator from the base index and the committed seed."""
    return random.Random(BASES.index(base_name) * 100_000 + seed)


def mutant(base: bytes, base_name: str, seed: int) -> "tuple[str, bytes]":
    """One mutant of ``base``: the operator that made it and its bytes."""
    rng = _rng(base_name, seed)
    operator = rng.choice(OPERATORS)
    fields = cfb_raw.header(base)
    size = fields["sector_size"]
    if operator == "truncate":
        return operator, base[: rng.randrange(1, len(base) + 1)]
    if operator == "sector_shift":
        return operator, cfb_raw.patch_u32(base, SECTOR_SHIFT_OFFSET, rng.randrange(0, 21))
    if operator == "header_count":
        value = rng.choice((0, 1, 2, 3, 0xFFFFFFFF, 2**31))
        return operator, cfb_raw.patch_u32(base, rng.choice(HEADER_COUNT_OFFSETS), value)
    if operator in ("fat_entry", "minifat_entry"):
        sector = (
            fields["difat"][0] if operator == "fat_entry" else fields["first_mini_fat_sector"]
        )
        window = (sector + 1) * size
        slot = rng.randrange(size // 4)
        value = rng.choice((0, 1, slot, cfb_raw.ENDOFCHAIN, cfb_raw.FREESECT, 2**31))
        return operator, cfb_raw.patch_u32(base, window + 4 * slot, value)
    directory = (fields["first_dir_sector"] + 1) * size
    entry = rng.randrange(size // 128)
    if operator == "directory_link":
        offset = rng.choice(DIRECTORY_LINK_OFFSETS)
        value = rng.choice((0, entry, cfb_raw.NOSTREAM, 10**6, 2**31))
        return operator, cfb_raw.patch_u32(base, directory + entry * 128 + offset, value)
    if operator == "entry_start":
        value = rng.choice((0, 1, 999, cfb_raw.ENDOFCHAIN, cfb_raw.FREESECT))
        return operator, cfb_raw.patch_u32(base, directory + entry * 128 + DIRECTORY_START_OFFSET, value)
    value = rng.choice((0, 1, 4096, 2**31, 0xFFFFFFFF))
    offset = rng.choice(DIRECTORY_SIZE_OFFSETS)
    return operator, cfb_raw.patch_u32(base, directory + entry * 128 + offset, value)


def _cases() -> "Iterator[tuple[str, int, str, bytes, bytes]]":
    """Every ``(base_name, seed, operator, base_bytes, mutant_bytes)`` in a fixed order."""
    for base_name in BASES:
        base = make_msg_fixtures.build_fixture(base_name)
        for seed in MUTANT_SEEDS:
            operator, data = mutant(base, base_name, seed)
            yield base_name, seed, operator, base, data


def _total(opened: cfb.CfbFile) -> int:
    return sum(bytes_ for _, bytes_ in opened.accounting) + opened.unaccounted


def classify(base_name: str, seed: int, operator: str, data: bytes) -> str:
    """Open ``data``, read every stream and return a closed tag; never raises.

    An exception, ``MemoryError`` or ``RecursionError`` becomes an ``AssertionError``
    naming the base, the seed and the operator -- the fuzz's failure message.
    """
    label = f"base={base_name} seed={seed} op={operator}"
    work = cfb.Work()
    try:
        opened = cfb.open_cfb(data, require_properties=False, work=work)
    except MemoryError as exc:  # pragma: no cover - the point is that it must not happen
        raise AssertionError(f"{label}: MemoryError") from exc
    except RecursionError as exc:  # pragma: no cover
        raise AssertionError(f"{label}: RecursionError") from exc
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"{label}: {type(exc).__name__}: {exc}") from exc
    if isinstance(opened, cfb.CfbRefusal):
        assert opened.reason in cfb.CFB_REFUSAL_REASONS, f"{label}: {opened.reason}"
        return f"refusal:{opened.reason}"

    assert [name for name, _ in opened.accounting] == list(cfb.SECTOR_CLASSES), label
    assert _total(opened) == len(data), f"{label}: {_total(opened)} != {len(data)}"
    for stream in opened.streams:
        try:
            payload, fault = cfb.read_stream(opened, stream.path)
        except MemoryError as exc:  # pragma: no cover
            raise AssertionError(f"{label}: MemoryError reading {stream.path}") from exc
        except RecursionError as exc:  # pragma: no cover
            raise AssertionError(f"{label}: RecursionError reading {stream.path}") from exc
        except Exception as exc:  # pragma: no cover
            raise AssertionError(f"{label}: {type(exc).__name__} reading {stream.path}") from exc
        assert isinstance(payload, bytes), f"{label}: {stream.path} not bytes"
        assert fault in cfb.FAULT_KINDS, f"{label}: {stream.path} fault {fault}"
        # No allocation is ever sized from a declared length.
        assert len(payload) <= len(data), f"{label}: {stream.path} fabricated {len(payload)} bytes"
    return f"opened:{opened.unaccounted}:{len(opened.streams)}:{opened.steps}"


def steps_and_sectors(data: bytes) -> "tuple[int, int]":
    """The steps a full open-plus-read takes and the sector count they are bounded by."""
    work = cfb.Work()
    opened = cfb.open_cfb(data, require_properties=False, work=work)
    if isinstance(opened, cfb.CfbFile):
        for stream in opened.streams:
            cfb.read_stream(opened, stream.path)
        return opened.steps, opened.sector_count
    header = cfb.parse_header(data)
    size = header.sector_size if isinstance(header, cfb.CfbHeader) else 512
    return work.steps, cfb.sector_windows(len(data), size)


def budget_for(sectors: int) -> int:
    """The declared bound: ``WORK_PER_SECTOR * sector_count + WORK_BASE``."""
    return cfb.WORK_PER_SECTOR * sectors + cfb.WORK_BASE


def digest() -> str:
    """A hex digest of every mutant's closed outcome, for the determinism check."""
    rows = [f"{base}|{seed}|{op}|{classify(base, seed, op, data)}" for base, seed, op, _, data in _cases()]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_every_mutant_returns_a_closed_failure_or_the_same_document() -> None:
    bases = {name: make_msg_fixtures.build_fixture(name) for name in BASES}
    base_tags = {name: classify(name, -1, "none", data) for name, data in bases.items()}
    seen = 0
    for base_name, seed, operator, base, data in _cases():
        tag = classify(base_name, seed, operator, data)
        if data == base:
            # A mutation that changed nothing must read exactly as the base does.
            assert tag == base_tags[base_name], (base_name, seed, operator)
        seen += 1
    assert seen >= 300 * len(BASES), seen


def test_the_work_per_byte_budget_holds() -> None:
    # The declared bound, stated from the structure in ``cfb``'s docstring, holds for every
    # fixture and every mutant -- the check runs before the fuzz, not after the numbers.
    assert cfb.WORK_PER_SECTOR > 0 and cfb.WORK_BASE > 0
    worst = 0.0
    for name in make_msg_fixtures.ALL_FIXTURE_NAMES:
        worst = max(worst, _check_budget(name, -1, "fixture", make_msg_fixtures.build_fixture(name)))
    for base_name, seed, operator, _base, data in _cases():
        worst = max(worst, _check_budget(base_name, seed, operator, data))
    # The bound is not vacuous: the measured maximum is strictly under it.
    assert 0 < worst < 1.0, worst


def _check_budget(base_name: str, seed: int, operator: str, data: bytes) -> float:
    steps, sectors = steps_and_sectors(data)
    budget = budget_for(sectors)
    assert steps <= budget, (base_name, seed, operator, steps, budget)
    return steps / budget


def test_the_numbers_are_stable_across_hash_seeds() -> None:
    baseline = digest()
    assert _hash_seed_run("0") == baseline
    assert _hash_seed_run("1234567") == baseline


def _hash_seed_run(seed: str) -> str:
    script = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "sys.path.insert(0, sys.argv[3])\n"
        "import test_cfb_fuzz as fuzz\n"
        "print(fuzz.digest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()
