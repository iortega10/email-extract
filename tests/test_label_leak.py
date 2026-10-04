"""Turn 1.0b: the label-leak guard (``docs/design/phase1-ledgers.md`` section (d)).

The allow-list cannot stop a parser rule written from the bytes the agent just read;
this can. It scans every file under ``emailextract/**`` and asserts no string literal
names a fixture path or a fixture filename. The forbidden set is built from the
fixture tree at test time (stem-carrying paths and filenames), never hard-coded.
"""

from __future__ import annotations

from pathlib import Path

import emailextract

ROOT = Path(emailextract.__file__).resolve().parent.parent
PACKAGE = ROOT / "emailextract"
FIXTURES = ROOT / "fixtures"
_LOCAL_ONLY = "real"


def _forbidden() -> set[str]:
    """Every fixture path and filename under ``fixtures/**`` (``real/`` excluded).

    A fixture is a ``.eml`` and its sidecar is an ``*.expected.json``; a
    ``SHA256SUMS`` manifest is neither and is not a name a rule may be written from.
    """
    names: set[str] = set()
    for pattern in ("*.eml", "*.expected.json"):
        for path in FIXTURES.rglob(pattern):
            rel = path.relative_to(FIXTURES)
            if _LOCAL_ONLY in rel.parts:
                continue
            names.add(rel.as_posix())
            names.add(path.name)
    return names


def _leaks(root: Path, forbidden: set[str]) -> list[str]:
    """Every ``*.py`` under ``root`` that names a forbidden literal, with file and line."""
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            hits = sorted(token for token in forbidden if token in line)
            if hits:
                try:
                    where = path.relative_to(ROOT).as_posix()
                except ValueError:
                    where = str(path)
                offenders.append(f"{where}:{lineno}: {', '.join(hits)}")
    return offenders


def test_no_package_file_names_a_fixture_path_or_filename(tmp_path: Path) -> None:
    forbidden = _forbidden()
    assert forbidden, "no fixtures under fixtures/: this test would be vacuous"
    offenders = _leaks(PACKAGE, forbidden)
    assert not offenders, f"a package file names a fixture path or filename: {offenders}"

    # Prove the guard can fail: a planted file naming a fixture filename is caught.
    planted = tmp_path / "planted.py"
    planted.write_text(f"PATH = {sorted(forbidden)[0]!r}\n", encoding="utf-8")
    assert _leaks(tmp_path, forbidden)
