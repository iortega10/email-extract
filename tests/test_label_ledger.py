"""Turn 1.0b: the label ledger (``docs/design/phase1-ledgers.md`` section (a)).

Additions-only sha256 fingerprints of the hand-typed labels and the oracle that reads
them. The committed ledger covers every current ``*.expected.json``, every file under
``tests/support/**`` and every file under ``emailextract/evals/**``; the three failure
modes -- a changed recorded file, a removed recorded file, a new unrecorded file --
are each proved on a temporary copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import update_label_ledger as label_ledger  # noqa: E402

SIDECAR = "fixtures/generated/one.expected.json"
SUPPORT = "tests/support/helper.py"
EVAL = "emailextract/evals/gate.py"


def _temp_tree(root: Path) -> None:
    for rel, text in (
        (SIDECAR, "{\"fixture\": \"one.eml\"}\n"),
        (SUPPORT, "def compare(a, b):\n    return a == b\n"),
        (EVAL, "def gate():\n    return True\n"),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_every_covered_path_is_recorded() -> None:
    """The committed ledger and the committed tree agree, and it covers all three sets."""
    files = label_ledger.covered_files()
    assert any(rel.endswith(".expected.json") for rel in files), "no sidecar is covered"
    assert any(rel.startswith("tests/support/") for rel in files), "tests/support is not covered"
    assert any(rel.startswith("emailextract/evals/") for rel in files), "evals is not covered"
    assert label_ledger.check(label_ledger.load_ledger()) == []
    # The CLI's test form exits zero on an unmodified tree.
    assert label_ledger.main(["--check"]) == 0


def test_a_changed_label_is_refused(tmp_path: Path) -> None:
    _temp_tree(tmp_path)
    ledger, _lines = label_ledger.record({"files": {}}, root=tmp_path)
    (tmp_path / SIDECAR).write_text("{\"fixture\": \"one.eml\", \"tweak\": 1}\n", encoding="utf-8")
    problems = label_ledger.check(ledger, root=tmp_path)
    assert any(problem.startswith(f"label_ledger: {SIDECAR} changed") for problem in problems)
    with pytest.raises(ValueError, match=f"{SIDECAR} changed"):
        label_ledger.record(ledger, root=tmp_path)


def test_a_removed_label_is_refused(tmp_path: Path) -> None:
    _temp_tree(tmp_path)
    ledger, _lines = label_ledger.record({"files": {}}, root=tmp_path)
    (tmp_path / SUPPORT).unlink()
    problems = label_ledger.check(ledger, root=tmp_path)
    assert any(problem.startswith(f"label_ledger: {SUPPORT} is recorded but not present") for problem in problems)
    with pytest.raises(ValueError, match=f"{SUPPORT} is recorded but not present"):
        label_ledger.record(ledger, root=tmp_path)


def test_an_unrecorded_label_is_refused(tmp_path: Path) -> None:
    _temp_tree(tmp_path)
    ledger, _lines = label_ledger.record({"files": {}}, root=tmp_path)
    new_rel = "fixtures/generated/two.expected.json"
    (tmp_path / new_rel).write_text("{\"fixture\": \"two.eml\"}\n", encoding="utf-8")
    problems = label_ledger.check(ledger, root=tmp_path)
    assert any(problem.startswith(f"label_ledger: {new_rel} is a new label") for problem in problems)
    # ... and recording it is what clears the problem.
    updated, _lines = label_ledger.record(ledger, root=tmp_path)
    assert label_ledger.check(updated, root=tmp_path) == []
    assert new_rel in updated["files"]
