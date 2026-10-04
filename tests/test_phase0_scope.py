"""Phase 0 scope: the package is contracts, protocols, documents and tests -- nothing else.

**PHASE 1 DELETES OR UPDATES THIS TEST ON PURPOSE.** It asserts a *negative* -- that no quote
segmenter, no attachment router, no thread builder, no `.msg`/CFB reader and no term matcher beyond
the seam stub exists -- so the turn that first builds one must edit this file in the same commit
(adding the new module to the expected set, and moving its import ban to that module). That is the
point: the scope is checked where it can be, and the check is loud when it is no longer true.

What is asserted here:

* the modules under ``emailextract/`` are exactly the Phase 0 set plus the Phase 1 entry
  point (``versions``, ``model``, ``timeevent``, ``container``, ``ids``, ``walk``,
  ``parse``, ``siblings``, ``store``, ``seam`` and ``evals/*``);
* no **library** module imports a CFB reader, an HTML parser, a quote/thread library, ``openpyxl``
  or a GPL package;
* no function or class anywhere in the package is named like a later phase's machinery;
* the package imports and works with ``olefile``, ``wordextract`` and ``formextract`` all blocked at
  import time.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "emailextract"
EVALS = PACKAGE / "evals"

#: The Phase 0 library modules, and the eval harness modules, as file names.
EXPECTED_LIBRARY = {
    "__init__.py",
    "container.py",
    "headers.py",
    "ids.py",
    "model.py",
    "parse.py",
    "rfc2047.py",
    "rfc2231.py",
    "seam.py",
    "siblings.py",
    "store.py",
    "timeevent.py",
    "versions.py",
    "walk.py",
}
EXPECTED_EVALS = {
    "__init__.py",
    "__main__.py",
    "falsify.py",
    "gates.py",
    "l1.py",
    "labels.py",
    "metrics.py",
}

#: A library module may import none of these: a CFB/`.msg` reader, an HTML parser, a quote or thread
#: library, the workbook writer, or a GPL package (``extract_msg`` is GPL; the design forbids it
#: being a dependency even for spot checks).
BANNED_IMPORTS = {
    "olefile",
    "extract_msg",
    "cfb",
    "compoundfiles",
    "lxml",
    "bs4",
    "html5lib",
    "html",
    "openpyxl",
    "talon",
    "tnefparse",
    "email_reply_parser",
}

#: Substrings that name a piece of later-phase machinery in a function or class name.
FORBIDDEN_NAME_PARTS = (
    "quote_segment",
    "segment_quote",
    "quotesegment",
    "router",
    "threading",
    "thread_build",
    "build_thread",
    "cfb",
    "olefile",
    "msg_reader",
    "read_msg",
)

_IMPORT_PROBE = """
import importlib.abc
import sys

BLOCKED = {"olefile", "wordextract", "formextract"}


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError("blocked at import time: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

from emailextract.container import EmlContainer, memory_bytes
from emailextract.model import FlagSection
from emailextract.seam import MatchUnit, MatcherView, StubMatcher, TermList, UnitLocation, runs_from_texts
from emailextract import record_to_bytes
import emailextract.evals.l1  # noqa: F401  the harness imports too
import emailextract.walk as walk

result = walk.walk(EmlContainer(memory_bytes(b"From: a@example.test\\r\\n\\r\\nbody\\r\\n")))
assert result.parts
unit = MatchUnit(
    view_id=MatcherView.PLAIN,
    text="revenue",
    runs=runs_from_texts(["revenue"]),
    location=UnitLocation(part="1", view="plain", unit=0),
)
assert StubMatcher().match(unit, TermList(terms=["revenue"]))
assert record_to_bytes(FlagSection())

leaked = sorted(name for name in sys.modules if name.split(".")[0] in BLOCKED)
print("clean" if not leaked else "leaked:" + ",".join(leaked))
"""


def _py_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.py"))


def _all_modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_the_modules_are_exactly_the_phase_0_set() -> None:
    """No module exists that the Phase 0 layout does not name, and none it names is missing."""
    library = {path.name for path in _py_files(PACKAGE)}
    evals = {path.name for path in _py_files(EVALS)}
    assert library == EXPECTED_LIBRARY, (
        f"library modules not in the Phase 0 set: {sorted(library - EXPECTED_LIBRARY)}; "
        f"Phase 0 modules missing: {sorted(EXPECTED_LIBRARY - library)}"
    )
    assert evals == EXPECTED_EVALS, (
        f"eval modules not in the Phase 0 set: {sorted(evals - EXPECTED_EVALS)}; "
        f"Phase 0 eval modules missing: {sorted(EXPECTED_EVALS - evals)}"
    )
    # Only the package root and ``evals/`` exist; a new subpackage is a Phase 0 scope change.
    subpackages = sorted(
        path.name for path in PACKAGE.iterdir() if path.is_dir() and "__pycache__" not in path.name
    )
    assert subpackages == ["evals"], subpackages


def test_no_library_module_imports_later_phase_machinery() -> None:
    """The library is contracts: it never opens a CFB, parses HTML, reads `.msg`, or routes."""
    offenders: list[str] = []
    for path in _all_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in BANNED_IMPORTS:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}")
    assert not offenders, f"a module imports later-phase machinery: {offenders}"


def test_no_quote_segmenter_router_thread_builder_or_msg_reader_exists() -> None:
    """No function or class anywhere in the package is named like a later phase's machinery."""
    offenders: list[str] = []
    for path in _all_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                lowered = node.name.lower()
                if any(part in lowered for part in FORBIDDEN_NAME_PARTS):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.name}")
    assert not offenders, f"a later-phase name exists: {offenders}"


def test_the_package_imports_with_olefile_and_the_siblings_blocked() -> None:
    """The library and the eval harness import and run with no CFB reader and neither sibling."""
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert result.stdout.strip() == "clean", result.stdout + result.stderr
