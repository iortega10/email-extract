"""Turn 0.3: the label loader reads sidecars without the library (D11).

The independence rule is enforced here, not assumed: ``emailextract.evals.labels``
is loaded in a bare interpreter (no ``emailextract`` import at all), every sidecar
under ``fixtures/`` loads through it, and the corpus is paired both ways -- a
fixture with no sidecar fails, and a sidecar naming no fixture fails. Nothing
here compares a label with the walker: that is the L1 oracle's job (Turn 0.4),
and the labels are never edited to match output.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from emailextract.evals.labels import (
    PROVENANCES,
    LabelError,
    Sidecar,
    load_sidecar,
    load_sidecars,
    sidecar_paths,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
LABELS_MODULE = ROOT / "emailextract" / "evals" / "labels.py"
FIXTURE_DIRS = (FIXTURES / "generated", FIXTURES / "raw", FIXTURES / "time")

LOADER_SCRIPT = r"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("labels_standalone", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert "emailextract" not in sys.modules, "the loader imported the package"
assert "emailextract.walk" not in sys.modules, "the loader imported the parser"
sidecars = module.load_sidecars(sys.argv[2])
print(json.dumps({"loaded": len(sidecars), "stems": sorted(sidecars)}))
"""


def test_the_loader_loads_in_a_bare_interpreter_without_the_parser() -> None:
    result = subprocess.run(
        [sys.executable, "-c", LOADER_SCRIPT, str(LABELS_MODULE), str(FIXTURES)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={"PATH": "", "PYTHONPATH": str(ROOT), "SYSTEMROOT": "C:\\Windows"},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["loaded"] == 90, f"expected 90 sidecars (85 messages + 5 time), got {report}"


def test_every_sidecar_under_fixtures_loads() -> None:
    loaded = load_sidecars(FIXTURES)
    assert len(loaded) == 90
    for stem, sidecar in loaded.items():
        assert isinstance(sidecar, Sidecar)
        assert sidecar.stem == stem
        assert sidecar.labels_provenance in PROVENANCES
        assert sidecar.facts


def test_every_fixture_has_a_sidecar_and_every_sidecar_a_fixture() -> None:
    fixtures = sorted(
        path.name
        for directory in FIXTURE_DIRS
        for path in directory.glob("*.eml")
    )
    sidecars = sorted(
        path.name.removesuffix(".expected.json")
        for directory in FIXTURE_DIRS
        for path in directory.glob("*.expected.json")
    )
    assert [f.removesuffix(".eml") for f in fixtures] == sidecars, (
        "every fixture needs a sidecar and every sidecar a fixture (D11)"
    )


def test_a_sidecar_naming_a_missing_fixture_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "ghost.expected.json"
    path.write_text(
        json.dumps(
            {
                "fixture": "ghost.eml",
                "labels_provenance": "spec",
                "facts": {"container.sha256": {"phase": 0, "value": "0" * 64}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LabelError, match="does not exist beside it"):
        load_sidecar(path)


def test_a_sidecar_over_an_unknown_suffix_is_refused(tmp_path: Path) -> None:
    (tmp_path / "thing.txt").write_text("x", encoding="utf-8")
    path = tmp_path / "thing.expected.json"
    path.write_text(
        json.dumps(
            {
                "fixture": "thing.txt",
                "labels_provenance": "spec",
                "facts": {"container.sha256": {"phase": 0, "value": "0" * 64}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LabelError, match="unknown suffix"):
        load_sidecar(path)


def test_two_sidecars_for_one_stem_are_refused(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    payload = json.dumps(
        {
            "fixture": "x.eml",
            "labels_provenance": "spec",
            "facts": {"container.sha256": {"phase": 0, "value": "0" * 64}},
        }
    )
    (tmp_path / "a" / "x.eml").write_bytes(b"From: a@b\r\n\r\nx\r\n")
    (tmp_path / "a" / "x.expected.json").write_text(payload, encoding="utf-8")
    (tmp_path / "b" / "x.eml").write_bytes(b"From: a@b\r\n\r\ny\r\n")
    (tmp_path / "b" / "x.expected.json").write_text(payload, encoding="utf-8")
    with pytest.raises(LabelError, match="already labelled"):
        load_sidecars(tmp_path)


def test_a_repeated_key_is_refused_not_dropped(tmp_path: Path) -> None:
    (tmp_path / "x.eml").write_bytes(b"From: a@b\r\n\r\nx\r\n")
    path = tmp_path / "x.expected.json"
    path.write_text(
        '{"fixture": "x.eml", "labels_provenance": "spec", '
        '"facts": {"container.sha256": {"phase": 0, "value": "a"}, '
        '"container.sha256": {"phase": 0, "value": "b"}}}',
        encoding="utf-8",
    )
    with pytest.raises(LabelError, match="duplicate key"):
        load_sidecar(path)


def test_human_is_a_valid_token_but_no_sidecar_here_claims_it() -> None:
    """``human`` means a person typed the label; every label here was typed by a model
    from the design rules (labels_provenance: spec), and saying otherwise would hide how
    much a mismatch is worth. The build spec's ``hand`` wording is a documented
    discrepancy: the sibling's token set (human | generator | spec) is used."""
    assert "human" in PROVENANCES
    for path in sidecar_paths(FIXTURES):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["labels_provenance"] != "human", f"{path} claims human"
        assert payload["labels_provenance"] in ("spec", "generator")
