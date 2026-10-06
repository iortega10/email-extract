"""Phase 1 scope: the package is the RFC 822 parser -- no CFB/`.msg`, routing, threading or recursion.

This replaces ``tests/test_phase0_scope.py`` (Turn 1.10a). The scope assertion is the same *kind*
of negative -- a later phase's machinery must not exist yet -- but the module list is Phase 1's, the
import bans add ``chardet`` (the exit criterion: the package imports with no sibling and no
``chardet``), and the scans name the two things the exit criteria fix:

* no module imports ``threading``/``concurrent``/``multiprocessing``/``socket``/``http`` (or
  ``urllib.request``): the package is single-threaded and never fetches;
* no function **recurses over the parts tree** -- with one named, committed exception: the walker's
  ``walk._walk_part`` is recursive today (``KNOWN_SELF_RECURSION``), which the exit criteria's "the
  walkers are iterative" does not hold for. It is a FINDING (the walker is not in this turn's
  allow-list), so the scan names it rather than tolerating it silently: a **new** self-recursive
  function fails, an exempted one must carry a reason, and the list is asserted exact.

The module list, the import bans and the name scan are kept from the Phase 0 file; the report-sections
test is Turn 1.10b.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "emailextract"
EVALS = PACKAGE / "evals"
QUOTE = PACKAGE / "quote"

#: The Phase 1 library modules, the quote stage's subpackage and the eval harness, as file names.
EXPECTED_LIBRARY = {
    "__init__.py",
    "addresses.py",
    "assemble.py",
    "attach.py",
    "container.py",
    "dates.py",
    "headers.py",
    "htmltext.py",
    "htmltree.py",
    "ids.py",
    "ingest.py",
    "model.py",
    "parse.py",
    "rfc2047.py",
    "rfc2231.py",
    "seam.py",
    "selection.py",
    "siblings.py",
    "store.py",
    "text.py",
    "timeevent.py",
    "versions.py",
    "walk.py",
}
EXPECTED_QUOTE = {
    "__init__.py",
    "dom_rules.py",
    "i18n.py",
    "resolve.py",
    "text_rules.py",
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
#: library, the workbook writer, a GPL package (``extract_msg`` is GPL) or ``chardet`` (the exit
#: criterion names it: the package resolves charsets itself).
BANNED_IMPORTS = {
    "olefile",
    "extract_msg",
    "cfb",
    "compoundfiles",
    "lxml",
    "bs4",
    "html5lib",
    "openpyxl",
    "talon",
    "tnefparse",
    "email_reply_parser",
    "chardet",
}

#: The **only** library modules allowed to import the stdlib ``html`` package: the own tree
#: (``htmltree.py``) and the projection (``htmltext.py``), both Turn 1.5.
HTML_MODULES = {"htmltree.py", "htmltext.py"}

#: Import roots no module may name: the package is single-threaded and never fetches.
CONCURRENCY_IMPORTS = {"threading", "concurrent", "multiprocessing", "socket", "http"}
FETCH_IMPORTS = {"urllib.request", "urllib.error", "requests", "httpx"}

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

#: The one function that recurses, as ``(module path relative to the repo, function name)``. The
#: exit criteria say "the walkers are iterative"; ``_walk_part`` is not (it calls itself to descend
#: into a nested multipart child, ``walk.py:709``). The walker is not in Turn 1.10a's allow-list, so
#: this is a recorded FINDING: the scan below fails when the set changes, so a *new* recursion is
#: caught and this one has to keep its name and its reason.
KNOWN_SELF_RECURSION = {
    ("emailextract/walk.py", "_walk_part"): (
        "descends into a nested multipart child by calling itself; the walk-recursion finding of "
        "Turn 1.10a, reported not fixed (walk.py is outside the turn's allow-list)"
    ),
}

_IMPORT_PROBE = """
import importlib
import importlib.abc
import pkgutil
import sys

BLOCKED = {"olefile", "wordextract", "formextract", "chardet", "extract_msg"}


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError("blocked at import time: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

import emailextract

for module in pkgutil.walk_packages(emailextract.__path__, "emailextract."):
    importlib.import_module(module.name)

leaked = sorted(name for name in sys.modules if name.split(".")[0] in BLOCKED)
print("clean" if not leaked else "leaked:" + ",".join(leaked))
"""


def _py_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.py"))


def _all_modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _import_roots(tree: ast.AST) -> list[tuple[str, int]]:
    """Every ``(dotted name, lineno)`` a module's ``import`` statements name."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, node.lineno))
    return found


def _self_recursive(tree: ast.AST) -> list[str]:
    """Module-level functions that call their own bare name (a genuine self-recursion).

    A method calling a *module-level* function of the same name (``container_hash``) is not
    recursion -- a bare ``Name`` inside a method resolves to the module scope -- so only module-level
    functions are scanned, which is exactly the shape the walk exclusion names.
    """
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == node.name
            ):
                offenders.append(node.name)
                break
    return offenders


def test_the_modules_are_exactly_the_phase_1_set() -> None:
    """The library, the quote subpackage and the evals are exactly the Phase 1 tree."""
    library = {path.name for path in _py_files(PACKAGE)}
    evals = {path.name for path in _py_files(EVALS)}
    quote = {path.name for path in _py_files(QUOTE)}
    assert library == EXPECTED_LIBRARY, (
        f"library modules not in the Phase 1 set: {sorted(library - EXPECTED_LIBRARY)}; "
        f"Phase 1 modules missing: {sorted(EXPECTED_LIBRARY - library)}"
    )
    assert quote == EXPECTED_QUOTE, (
        f"quote modules not in the set: {sorted(quote - EXPECTED_QUOTE)}; "
        f"missing: {sorted(EXPECTED_QUOTE - quote)}"
    )
    assert evals == EXPECTED_EVALS, (
        f"eval modules not in the set: {sorted(evals - EXPECTED_EVALS)}; "
        f"missing: {sorted(EXPECTED_EVALS - evals)}"
    )
    subpackages = sorted(
        path.name for path in PACKAGE.iterdir() if path.is_dir() and "__pycache__" not in path.name
    )
    assert subpackages == ["evals", "quote"], subpackages


def test_no_library_module_imports_later_phase_machinery() -> None:
    """The library never opens a CFB, reads `.msg`, routes, or pulls a third-party parser."""
    offenders: list[str] = []
    for path in _all_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name, lineno in _import_roots(tree):
            root = name.split(".")[0]
            if root in BANNED_IMPORTS:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
            elif root == "html" and path.name not in HTML_MODULES:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    assert not offenders, f"a module imports later-phase machinery: {offenders}"


def test_no_module_imports_threading_concurrency_sockets_or_http() -> None:
    """The package is single-threaded and never fetches: no such import anywhere."""
    offenders: list[str] = []
    for path in _all_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name, lineno in _import_roots(tree):
            root = name.split(".")[0]
            if root in CONCURRENCY_IMPORTS or name in FETCH_IMPORTS:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    assert not offenders, f"a module imports concurrency or fetching machinery: {offenders}"


def test_no_msg_cfb_routing_recursion_or_threading_exists() -> None:
    """No later-phase name exists, and no function self-recurses but the one named finding.

    The self-recursion half is exact in both directions: a function that starts recursing fails, an
    exemption that stops being real fails, and the one exemption (``walk._walk_part``) carries its
    reason -- the walk-recursion finding the exit criteria' "the walkers are iterative" misses.
    """
    offenders: list[str] = []
    recursions: set[tuple[str, str]] = set()
    for path in _all_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if any(part in node.name.lower() for part in FORBIDDEN_NAME_PARTS):
                    offenders.append(f"{relative}:{node.lineno}: {node.name}")
        recursions |= {(relative, name) for name in _self_recursive(tree)}
    assert not offenders, f"a later-phase name exists: {offenders}"
    assert recursions == set(KNOWN_SELF_RECURSION), {
        "recurses but not named": sorted(recursions - set(KNOWN_SELF_RECURSION)),
        "named but does not recurse": sorted(set(KNOWN_SELF_RECURSION) - recursions),
    }
    for reason in KNOWN_SELF_RECURSION.values():
        assert reason.strip(), "an exemption must carry its reason"


def test_no_runtime_dependency_beyond_docextract_core() -> None:
    """``pyproject``'s runtime dependency is docextract-core, and nothing else is imported."""
    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    assert len(dependencies) == 1, dependencies
    assert dependencies[0].split(">")[0].strip() == "docextract-core", dependencies
    # Every import root a library module names is stdlib, the one dependency, or package-local.
    local = {
        path.stem
        for path in _all_modules()
    } | {"evals", "quote"}
    offenders: list[str] = []
    for path in _all_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name, lineno in _import_roots(tree):
            root = name.split(".")[0]
            if root in ("", *BANNED_IMPORTS, "docextract_core") or root in local:
                continue
            if root not in sys.stdlib_module_names:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    assert not offenders, f"a module imports a non-stdlib, non-core package: {offenders}"


def test_the_package_imports_with_no_sibling_and_no_chardet() -> None:
    """A fresh subprocess imports every module with the siblings, ``olefile`` and ``chardet`` blocked."""
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert result.stdout.strip() == "clean", result.stdout + result.stderr
