"""Phase 1 scope: the package is the RFC 822 parser -- no CFB/`.msg`, routing, threading or recursion.

This replaces ``tests/test_phase0_scope.py`` (Turn 1.10a). The scope assertion is the same *kind*
of negative -- a later phase's machinery must not exist yet -- but the module list is Phase 1's, the
import bans add ``chardet`` (the exit criterion: the package imports with no sibling and no
``chardet``), and the scans name the two things the exit criteria fix:

* no module imports ``threading``/``concurrent``/``multiprocessing``/``socket``/``http`` (or
  ``urllib.request``): the package is single-threaded and never fetches;
* no function **recurses over the parts tree**. Turn 1.10a recorded the walker's ``walk._walk_part``
  as a named FINDING (``KNOWN_SELF_RECURSION``); Turn 1.11 rewrote it as an explicit-stack loop, so
  the allow-list is now **empty** and the scan must find no self-recursive function at all: a *new*
  recursion fails, and a stale exemption fails too.

The module list, the import bans and the name scan are kept from the Phase 0 file; the report-sections
test is Turn 1.10b, and the phase-1 report it checks is ``docs/phase1-report.md``.
"""

from __future__ import annotations

import ast
import re
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
    "mediatype.py",
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

#: The functions that recurse, as ``(module path relative to the repo, function name)``. Turn 1.10a
#: recorded exactly one -- ``_walk_part``, which called itself to descend into a nested multipart
#: child -- as a FINDING against the exit criteria's "the walkers are iterative". Turn 1.11 rewrote
#: it as an explicit-stack loop (``tests/test_walk_iterative.py`` proves it byte for byte against the
#: frozen recursive reference in ``tests/support/legacy_walk.py``), so the list is now **empty**: the
#: scan below still asserts it exact in both directions, so a *new* recursion fails here rather than
#: being tolerated.
KNOWN_SELF_RECURSION: dict[tuple[str, str], str] = {}

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
    """No later-phase name exists, and no function self-recurses at all.

    The self-recursion half is exact in both directions: a function that starts recursing fails, and
    an exemption that stops being real fails. Turn 1.11 made the walker iterative, so the allow-list
    is empty and the exit criteria's "the walkers are iterative" holds.
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


# ------------------------------------------------------------------ the final report

#: ``docs/phase1-report.md``: the phase's closing artifact, committed last (Turn 1.10b).
REPORT = ROOT / "docs" / "phase1-report.md"

#: The sections ``docs/design/phase1-ledgers.md`` (f) requires of the report, in its order, plus the
#: **Exit criteria** walk Turn 1.11 added (the build spec's "Exit criteria for Phase 1", bullet by
#: bullet). ``docs/design/phase1-ledgers.md`` names the checking test ``tests/test_phase1_report.py``;
#: the frozen declaration block names this file instead, and the declaration is the enforced record,
#: so the test lives here (recorded as the deviation in the report's named resolutions).
REQUIRED_REPORT_SECTIONS = (
    "## What was built",
    "## Named resolutions",
    "## Coverage",
    "## Gap gate",
    "## Label-versus-parser findings",
    "## Licences",
    "## Not done",
    "## Exit criteria",
)

#: Every ``tests/<file>.py::<name>`` the report cites. A citation is a claim that a test or a pinned
#: constant exists, so a renamed symbol must leave the report stale rather than wrong-but-plausible.
_CITATION = re.compile(r"(tests/[A-Za-z0-9_/.]+\.py)::([A-Za-z0-9_]+)")

#: A level-2 heading line, whatever its text: the boundary between one section's body and the next.
_REPORT_HEADING = re.compile(r"^(## .+)$", re.MULTILINE)


def _report_problems(text: str) -> list[str]:
    """Every way ``text`` is not a report: a missing or repeated heading, or an empty body.

    A section's body is everything between its heading line and the next level-2 heading (or the
    end of the file), so a heading with nothing under it -- a stub -- is caught, and the problem
    names the section. The content is not judged: that is the owner's review.
    """
    headings = [match.group(1).strip() for match in _REPORT_HEADING.finditer(text)]
    problems: list[str] = []
    for section in REQUIRED_REPORT_SECTIONS:
        seen = headings.count(section)
        if seen == 0:
            problems.append(f"the required section {section!r} is missing")
        elif seen > 1:
            problems.append(f"the required section {section!r} appears {seen} times")
    if problems:
        return problems
    matches = list(_REPORT_HEADING.finditer(text))
    for index, match in enumerate(matches):
        section = match.group(1).strip()
        if section not in REQUIRED_REPORT_SECTIONS:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if not text[match.end():end].strip():
            problems.append(f"the required section {section!r} has an empty body")
    return problems


def _module_level_names(path: Path) -> set[str]:
    """Every name a test module defines at its top level: a function, a class or a pinned constant."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _citation_problems(text: str) -> list[str]:
    """Every ``tests/...py::name`` the report cites that is not a real symbol in that file.

    A static AST scan of the cited file -- not a live collection -- because a report cites both test
    functions and pinned constants (``FINDING_ROWS``, ``KNOWN_SELF_RECURSION``) and a constant is
    collected by nothing. A renamed test or a moved constant therefore makes the report stale rather
    than plausible: the citation stops resolving.
    """
    problems: list[str] = []
    for path, name in sorted(set(_CITATION.findall(text))):
        source = ROOT / path
        if not source.is_file():
            problems.append(f"the report cites {path}::{name}, but {path} does not exist")
        elif name not in _module_level_names(source):
            problems.append(f"the report cites {path}::{name}, but {name} is not defined there")
    return problems


def test_the_phase1_report_sections_are_present_and_non_empty() -> None:
    """The report carries its eight sections, each exactly once and non-empty, and cites live ids.

    The citation half can actually rot: a renamed test or a moved constant leaves the report stale
    rather than wrong-but-plausible, so every ``tests/...py::name`` it names must resolve.
    """
    assert REPORT.is_file(), f"the phase-1 report is not committed at {REPORT}"
    text = REPORT.read_text(encoding="utf-8")
    problems = _report_problems(text)
    assert not problems, problems
    cited = sorted(set(_CITATION.findall(text)))
    assert cited, "the report cites no test id or pinned constant at all"
    assert _citation_problems(text) == [], _citation_problems(text)
    # The check can fail, in both directions, on a stub: a heading with no body is named ...
    stub = "\n".join(f"{section}\n\nbody\n" for section in REQUIRED_REPORT_SECTIONS[:-1])
    stub += f"\n{REQUIRED_REPORT_SECTIONS[-1]}\n\n"
    assert _report_problems(stub) == [
        f"the required section {REQUIRED_REPORT_SECTIONS[-1]!r} has an empty body"
    ]
    # ... a repeated heading is named ...
    repeated = "\n".join(f"{section}\n\nbody\n" for section in REQUIRED_REPORT_SECTIONS)
    repeated += f"\n{REQUIRED_REPORT_SECTIONS[2]}\n\nbody\n"
    assert _report_problems(repeated) == [
        f"the required section {REQUIRED_REPORT_SECTIONS[2]!r} appears 2 times"
    ]
    # ... a missing section is reported rather than ignored ...
    for section in REQUIRED_REPORT_SECTIONS:
        missing = "\n".join(
            f"{other}\n\nbody\n" for other in REQUIRED_REPORT_SECTIONS if other != section
        )
        assert _report_problems(missing) == [f"the required section {section!r} is missing"]
    # ... and so is a citation to a symbol that is not there, or to a file that is not there.
    assert _citation_problems(text + "\n`tests/test_phase1_scope.py::test_no_such_case`\n") == [
        "the report cites tests/test_phase1_scope.py::test_no_such_case, but "
        "test_no_such_case is not defined there"
    ]
    assert _citation_problems(text + "\n`tests/test_no_such_file.py::test_x`\n") == [
        "the report cites tests/test_no_such_file.py::test_x, but "
        "tests/test_no_such_file.py does not exist"
    ]
