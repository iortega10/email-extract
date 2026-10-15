"""Turn 1b.10b: the Phase 1b scope guard -- no ``olefile``, no GPL, no real ``.msg``.

Three guards and one emptiness proof:

* :func:`test_the_library_imports_with_no_olefile_and_no_gpl` -- a bare interpreter imports every
  module with ``olefile``/``extract_msg``/``chardet``/the siblings blocked (reusing
  ``tests/test_phase1_scope.py``'s probe), and a scan of ``pyproject.toml`` and ``NOTICE`` shows
  ``olefile`` declared under ``[dev]`` only, named in ``NOTICE`` as BSD-3-Clause, and no declared
  distribution naming a GPL-family licence;
* :func:`test_no_real_msg_is_in_the_repository` -- every ``.msg`` in the tree is under
  ``fixtures/msg/``, listed in ``SHA256SUMS`` with matching bytes, and **reproduced** by
  ``tools/make_msg_fixtures.py``, so a hand-dropped real message fails; and every ``.msg`` sidecar
  carries ``labels_provenance: spec`` (nothing here claims ``human``);
* :func:`test_fixtures_real_is_empty` -- the machine-local ``fixtures/real/`` is an ignore rule,
  not a directory; if the owner creates it, it must hold nothing.

``tests/test_phase1_scope.py``'s helpers are reused (its blocked-import probe); none of its
assertions is weakened and no module was added to its scans this turn.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import make_msg_fixtures  # noqa: E402
from test_phase1_scope import _IMPORT_PROBE  # noqa: E402

from emailextract.evals.labels import load_sidecar  # noqa: E402

FIXTURES = ROOT / "fixtures"
MESSAGES = FIXTURES / "msg"
SUMS = MESSAGES / "SHA256SUMS"
PYPROJECT = ROOT / "pyproject.toml"
NOTICE = ROOT / "NOTICE"

#: Subtrees that are machine-local, generated or tool scratch: never a committed fixture.
_SKIPPED_PARTS = {".git", ".venv", "__pycache__", ".hearth", ".exec-mcp", "build", "dist", ".scratch"}


def _sums() -> dict[str, str]:
    """``{name: sha256}`` from ``fixtures/msg/SHA256SUMS``."""
    entries: dict[str, str] = {}
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            entries[name.strip()] = digest.strip()
    return entries


def _tree_messages() -> list[Path]:
    """Every ``*.msg`` in the working tree, outside the machine-local and generated subtrees."""
    found: list[Path] = []
    for path in ROOT.rglob("*.msg"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & _SKIPPED_PARTS or "real" in parts:
            continue
        found.append(path)
    return sorted(found)


def test_the_library_imports_with_no_olefile_and_no_gpl() -> None:
    """A bare interpreter imports every module with ``olefile`` blocked; the manifests are clean.

    The probe is ``tests/test_phase1_scope.py``'s (blocked meta-path finder, then every package
    module imported); the manifest scan is the one this turn adds: ``olefile`` is a *dev* extra,
    and no declared requirement names a GPL-family licence.
    """
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert result.stdout.strip() == "clean", result.stdout + result.stderr

    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]
    assert len(dependencies) == 1, dependencies
    assert dependencies[0].split(">")[0].strip() == "docextract-core", dependencies
    assert not any("olefile" in spec for spec in dependencies)
    groups = project.get("optional-dependencies", {})
    dev = groups.get("dev") or []
    assert any(spec.split(">")[0].split("=")[0].split("[")[0].strip() == "olefile" for spec in dev), dev
    for group, specs in groups.items():
        if group == "dev":
            continue
        assert not any("olefile" in spec for spec in specs), (group, specs)
    declared = [*dependencies, *(spec for specs in groups.values() for spec in specs)]
    offenders = [spec for spec in declared if re.search(r"gpl", spec, re.IGNORECASE)]
    assert not offenders, f"a declared requirement names a GPL-family licence: {offenders}"

    notice = NOTICE.read_text(encoding="utf-8")
    assert "olefile" in notice, "NOTICE must name the dev-only comparator"
    assert "BSD 3-Clause" in notice, "NOTICE must name olefile's licence id"
    assert "No GPL dependency" in notice, "NOTICE must state the no-GPL rule"
    assert "fixtures/real/" in notice, "NOTICE must record the machine-local fixture rule"


def test_no_real_msg_is_in_the_repository() -> None:
    """Every ``.msg`` is a generated, checksummed, spec-labelled fixture under ``fixtures/msg/``.

    Three independent proofs per file: it is *under* ``fixtures/msg/``, its sha256 is *listed* in
    ``SHA256SUMS``, and ``tools/make_msg_fixtures.py`` *reproduces* its bytes. A hand-dropped real
    message fails the second and third; a message in any other directory fails the first.
    """
    messages = _tree_messages()
    assert messages, "no .msg is in the tree: the guard would be vacuous"
    sums = _sums()
    for path in messages:
        relative = path.relative_to(ROOT).as_posix()
        assert path.parent == MESSAGES, f"{relative} is not under fixtures/msg/"
        name = f"{path.stem}.msg"
        assert name in sums, f"{relative} is not listed in fixtures/msg/SHA256SUMS"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == sums[name], f"{relative}: sha256 {digest} != SHA256SUMS {sums[name]}"
        assert make_msg_fixtures.build_fixture(path.stem) == path.read_bytes(), (
            f"{relative} is not reproduced by tools/make_msg_fixtures.py"
        )
    assert sorted(f"{path.stem}.msg" for path in messages) == sorted(sums), (
        "the messages and SHA256SUMS disagree about the corpus"
    )

    # Every .msg sidecar is a spec label; the hostile three deliberately have none (their
    # expectations are typed in tests/support/msg_construction.py).
    sidecars = sorted(MESSAGES.glob("*.expected.json"))
    assert sidecars, "no .msg sidecar: the guard would be vacuous"
    for sidecar_path in sidecars:
        sidecar = load_sidecar(sidecar_path)
        assert sidecar.fixture.endswith(".msg"), sidecar_path
        assert sidecar.labels_provenance == "spec", (sidecar_path, sidecar.labels_provenance)
    hostile = {"msg_fat_cycle", "msg_directory_loop", "msg_truncated_stream"}
    assert hostile <= {path.stem for path in messages}


def test_fixtures_real_is_empty() -> None:
    """``fixtures/real/`` is machine-local: an ignore rule, and an empty directory if it exists.

    There is **no** marker file in this checkout -- the ``.gitignore`` rule and this test are the
    marker -- so the check is that the rule is present and that nothing real sits under the path.
    """
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "fixtures/real/" in ignore, ignore
    real = FIXTURES / "real"
    if real.exists():
        assert [path.name for path in real.iterdir()] == [], (
            "fixtures/real/ holds files; real email must never enter the repository"
        )
    assert not list(FIXTURES.glob("real/**/*.msg")), "a real .msg is under fixtures/real/"
    assert not list(FIXTURES.glob("real/**/*.eml")), "a real .eml is under fixtures/real/"
