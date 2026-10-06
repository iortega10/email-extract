"""Turn 1.10a: the golden HTML-projection pin, and the quote-normalisation table beside it.

``tests/ledger/html_projection_golden.json`` commits one ``(fixture, locator, sha256)`` row per
committed HTML part's projection, the hash over its projected text and its element spans, plus the
pinned plain-text quote-label normalisation rows. This module recomputes every row **in-process** and
fails naming the fixture and the locator when one moved -- so the pin holds on a **one-interpreter**
machine, where the old cross-interpreter check silently returned.

A second interpreter, when one is present, is an **additional** comparison that must also equal the
golden; it is never a substitute for the in-process comparison and its absence is not a silent skip
of the assertion (it only skips the *extra* run, and says so). The golden is a regression pin: it
never overrides a label.

An intentional interpreter or ``html.parser`` upgrade regenerates the golden with
``python tests/support/html_projection_hash.py --json`` (write it to the ledger, dated, in the same
commit); a second interpreter that still disagrees is recorded as a **waiver** -- a committed entry
with the interpreter label, a date and a reason, never an environment variable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import docextract_core  # noqa: E402
from support import html_projection_hash  # noqa: E402

LEDGER_PATH = Path(__file__).resolve().parent / "ledger" / "html_projection_golden.json"

#: Where the running interpreter found docextract_core (pure Python), handed to a child interpreter
#: so a fresh clone with no sibling checkout still imports it (the same shape tests/test_ingest.py
#: uses).
_CORE_PATH = str(Path(docextract_core.__file__).resolve().parent.parent)


def _load() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _key(row) -> tuple[str, str]:
    return str(row[0]), str(row[1])


def _effective_rows(golden: dict, interpreter: str) -> dict[tuple[str, str], str]:
    """The golden's rows, with any waiver for ``interpreter`` overlaid (a waiver names its rows)."""
    effective = {_key(row): row[2] for row in golden["rows"]}
    for waiver in golden.get("waivers", []):
        if waiver["interpreter"] != interpreter:
            continue
        for row in waiver["rows"]:
            effective[_key(row)] = row[2]
    return effective


def _mismatches(rows, golden: dict, interpreter: str) -> list[str]:
    """Every way the committed rows disagree with ``rows``, naming the fixture and the locator."""
    expected = _effective_rows(golden, interpreter)
    found = {_key(row): row[2] for row in rows}
    problems = [
        f"{fixture}:{locator}: the projection hash moved (golden {expected[key]}, this run {found[key]})"
        for key in sorted(set(expected) & set(found))
        for fixture, locator in [key]
        if expected[key] != found[key]
    ]
    problems.extend(
        f"{fixture}:{locator}: committed in the golden but no longer projected"
        for fixture, locator in sorted(set(expected) - set(found))
    )
    problems.extend(
        f"{fixture}:{locator}: projected but not in the golden"
        for fixture, locator in sorted(set(found) - set(expected))
    )
    return problems


def test_the_golden_recomputes_in_process() -> None:
    """Every committed row recomputes on this interpreter, and the corpus hash matches."""
    golden = _load()
    rows = html_projection_hash.projection_rows()
    assert rows, "the corpus has no HTML part to pin"
    problems = _mismatches(rows, golden, html_projection_hash.interpreter_label())
    assert not problems, problems
    assert html_projection_hash.corpus_projection_hash() == golden["corpus_hash"]
    assert len(golden["rows"]) == len(rows)


def test_a_moved_projection_fails_naming_fixture_and_locator() -> None:
    """The comparison names the fixture and the locator when a row moves -- it is not vacuous."""
    golden = _load()
    rows = html_projection_hash.projection_rows()
    moved = json.loads(json.dumps(golden))
    moved["rows"][0][2] = "0" * 64
    problems = _mismatches(rows, moved, html_projection_hash.interpreter_label())
    assert len(problems) == 1, problems
    assert moved["rows"][0][0] in problems[0] and moved["rows"][0][1] in problems[0], problems
    # And a row the golden carries that this run does not, and one this run carries that the
    # golden does not, are each named.
    extra_golden = json.loads(json.dumps(golden))
    extra_golden["rows"] = [*extra_golden["rows"], ["fixtures/generated/nope.eml", "1", "0" * 64]]
    assert "no longer projected" in _mismatches(rows, extra_golden, "any")[0]
    dropped = json.loads(json.dumps(golden))
    dropped["rows"] = dropped["rows"][1:]
    assert "but not in the golden" in _mismatches(rows, dropped, "any")[0]


def test_the_golden_rows_record_the_interpreter_minor() -> None:
    """The golden records the interpreter it was produced under, and its rows are stable anyway.

    The label is a recorded-only run input (the same discipline the run record's ``environment``
    follows): the golden is produced on one interpreter and the rows must recompute identically on
    whichever interpreter reads them, so this asserts the *shape* of the record -- the rows' own
    equality is ``test_the_golden_recomputes_in_process`` -- and never that this run's interpreter
    matched the one that wrote it.
    """
    golden = _load()
    assert golden["interpreter"].startswith("CPython ")
    minor = golden["cpython_minor"]
    assert isinstance(minor, list) and len(minor) == 2 and minor[0] == 3
    assert golden["interpreter"].startswith(f"CPython {minor[0]}.{minor[1]}.")
    assert all(len(row[2]) == 64 for row in golden["rows"])
    assert golden["corpus_hash"] == html_projection_hash.corpus_projection_hash()


def test_the_quote_label_normalisation_table_is_pinned() -> None:
    """The NFC-only, case-sensitive normalisation table is committed and recomputes byte for byte."""
    golden = _load()
    rows = html_projection_hash.normalisation_rows()
    assert golden["normalisation"] == rows
    assert golden["normalisation_hash"] == html_projection_hash.normalisation_hash()
    # The two facts a careless implementation would break: a combining mark composes, and a
    # lower-case head fills no slot (the tables are case-sensitive -- no casefold path).
    composed = next(row for row in rows if row[0].startswith("A\u0308"))
    assert composed[1] != composed[0], "the combining mark must compose under NFC"
    lower = next(row for row in rows if row[0].startswith("from:"))
    assert lower[3] is None and lower[4] is None, "a lower-case head must fill no slot"


def test_a_second_interpreter_is_an_additional_comparison() -> None:
    """The in-process comparison always runs; a second interpreter, when present, must also equal it."""
    golden = _load()
    mine = html_projection_hash.projection_rows()
    assert not _mismatches(mine, golden, html_projection_hash.interpreter_label())

    sys.path.insert(0, str(ROOT / "tools"))
    import runboth

    second = runboth.find_python311()
    if second is None:
        # The one-interpreter machine: the committed golden is the whole check, and it passed above.
        return
    prefix, source, version = second
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), _CORE_PATH])}
    completed = subprocess.run(
        [*prefix, str(ROOT / "tests" / "support" / "html_projection_hash.py"), "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    theirs = json.loads(completed.stdout)
    assert theirs["interpreter"].startswith("CPython ")
    theirs_rows = [[row[0], row[1], row[2]] for row in theirs["rows"]]
    assert [list(row) for row in mine] == theirs_rows, (
        f"the projections differ between {html_projection_hash.interpreter_label()} and "
        f"CPython {version} ({source})"
    )
    assert not _mismatches(theirs_rows, golden, theirs["interpreter"]), (
        f"the committed golden disagrees with CPython {version}"
    )


def test_a_waiver_is_committed_dated_and_reasoned() -> None:
    """A waiver is a committed, dated, reasoned entry (never an env var); today there are none."""
    golden = _load()
    assert golden["waivers"] == [], "a waiver is only added for an intentional interpreter upgrade"
    for waiver in golden["waivers"]:
        assert set(waiver) == {"interpreter", "date", "reason", "rows"}
        assert waiver["interpreter"].startswith("CPython ")
        assert waiver["date"] and waiver["reason"]
        for fixture, locator, digest in waiver["rows"]:
            assert isinstance(digest, str) and len(digest) == 64


@pytest.mark.parametrize("name", ["interpreter", "corpus_hash", "rows", "normalisation_hash"])
def test_the_golden_carries_its_required_keys(name: str) -> None:
    assert name in _load()
