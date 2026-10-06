"""The metrics CLI: ``python -m emailextract.evals`` (build spec Turn 0.4).

The table is reporting, so the tests are about the two things a caller acts on: **what it
says** (the L1 counts by phase, every gate, the corpus size, the gaps a falsifiability case
covers and which fixtures do not exercise, the labels undetermined) and **what it exits
with** -- 0 when every gate passed or could not run, 1 when one failed. Both exit codes are
exercised in a subprocess, which is how a caller sees them.

The committed corpus exits **1**: the seven disagreements the first run reported were resolved in
review, and Turn 1.7's blind DOM rules then re-opened eight red rows on the html view while the
reviewer adjudicates them (the plain rows all stay matched). The other exit cases use a
deliberately tampered copy in a temp directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support.sidecar_copy import PLAIN_SIMPLE, payload_of, tamper, write  # noqa: E402

from emailextract.evals.metrics import (  # noqa: E402
    corpus_size,
    falsifiability,
    main,
    render,
    undetermined,
)

MODULE = "emailextract.evals"


def run_cli(*args: str):
    environment = dict(os.environ) | {"PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


def _clean_corpus(tmp_path: Path) -> Path:
    write(tmp_path / "clean", payload_of(PLAIN_SIMPLE), source=PLAIN_SIMPLE)
    return tmp_path / "clean"


def test_the_cli_exits_zero_on_a_clean_corpus(tmp_path: Path) -> None:
    completed = run_cli("--root", str(_clean_corpus(tmp_path)))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = completed.stdout
    for name in ("L1", "no-silent-drop"):
        assert name in output, name
    assert "matched=" in output and "FAIL" not in output


def test_the_cli_exits_one_on_a_tampered_corpus(tmp_path: Path) -> None:
    def mutate(payload):
        payload["facts"]["container.sha256"]["value"] = "0" * 64

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    completed = run_cli("--root", str(tmp_path))
    assert completed.returncode == 1, completed.stdout + completed.stderr
    output = completed.stdout
    assert "FAIL" in output
    assert "container.sha256 mismatch" in output


def test_the_cli_exits_zero_on_the_committed_corpus_with_the_quote_facts_live() -> None:
    """The committed corpus is green, quote facts included (Turn 1.6 and Turn 1.7b adjudications).

    The html rows are live from Turn 1.7; the reviewer's 1.7b adjudication of the three DOM span
    conventions (decisions 40-42) makes the rules agree with the labels, so the CLI's verdict is
    success and both views are measured.
    """
    completed = run_cli()
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = completed.stdout
    assert "pass matched=1330 mismatched=0" in output, output
    assert "no-silent-drop" in output and "pass fixtures=119" in output, output


def test_the_table_names_every_gate_it_reports() -> None:
    output = render()
    for name in ("L1", "no-silent-drop"):
        assert f"    {name}" in output, name


def test_the_corpus_size_is_counted_by_directory() -> None:
    size = corpus_size()
    assert sum(size["fixtures"].values()) == 119
    assert sum(size["sidecars"].values()) == 119
    assert set(size["fixtures"]) == {"generated", "raw", "time"}
    assert size["fixtures"]["generated"] == 81
    assert size["fixtures"]["time"] == 5


def test_the_undetermined_count_is_read_from_the_labels() -> None:
    assert undetermined() == 20


def test_the_falsifiability_line_names_the_uncovered_gaps() -> None:
    covered, exercised, uncovered = falsifiability()
    assert covered == 8
    assert exercised == 6
    assert uncovered == ("body.headers_only", "body.no_boundary_found")
    assert "not exercised by any fixture: body.headers_only, body.no_boundary_found" in render()


def test_main_returns_zero_on_a_clean_corpus_without_printing_when_quiet(tmp_path, capsys) -> None:
    assert main(["--quiet", "--root", str(_clean_corpus(tmp_path))]) == 0
    assert capsys.readouterr().out == ""


def test_main_returns_one_on_a_tampered_corpus(tmp_path: Path) -> None:
    def mutate(payload):
        payload["facts"]["container.sha256"]["value"] = "0" * 64

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    assert main(["--quiet", "--root", str(tmp_path)]) == 1
