"""Turn 1.10b: the licence audit, repeated as a test rather than as a reading.

Apache-2.0 is a **notice-based** licence: a redistributed copy carries its notices, and a
``NOTICE`` that has drifted from what ``pyproject.toml`` actually declares is exactly the
kind of thing no compiler and no test catches by itself. So the audit is a test with two
sides that are allowed to disagree:

* ``NOTICE`` and ``pyproject.toml`` -- every declared distribution appears in ``NOTICE``
  with a licence id, and ``NOTICE`` names no distribution that is not declared (so adding a
  dependency fails here rather than silently shipping an unattributed one);
* the runtime dependency is **exactly** ``docextract-core`` (the exit criterion), and no
  GPL/LGPL/AGPL licence text or dependency appears in the audited files.

The licence *ids* in :data:`AUDITED_LICENCES` are hand-typed from each project's own
metadata at the time of the audit. A disagreement with a future ``NOTICE`` is the finding;
it is not something to "fix" by editing this table. The one row ``NOTICE`` carries that is
**not** a dependency of this release -- ``olefile`` (the future ``.msg`` reader) -- is a
named, commented exception, and a test below pins that it is not declared.

The AGPL reachable through the optional ``form`` extra is recorded here too: ``form-extract``
is Apache-2.0, but its **own** ``pdf`` extra pulls PyMuPDF (AGPL-3.0). This package's
``form`` extra must not request that extra, so the AGPL stays out of the tree's declared
dependency graph; ``test_the_form_extra_does_not_request_the_agpl_pdf_extra`` pins it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LICENSE = ROOT / "LICENSE"
NOTICE = ROOT / "NOTICE"
PYPROJECT = ROOT / "pyproject.toml"
SUPPORT = ROOT / "tests" / "support"

#: The audit's ground truth: every distribution ``NOTICE`` names, and the licence id its own
#: metadata states (SPDX equivalent in the comment). Read by hand, once (Turn 1.10b).
AUDITED_LICENCES = {
    "docextract-core": "Apache License, Version 2.0",  # Apache-2.0
    "word-extract": "Apache License, Version 2.0",  # Apache-2.0
    "form-extract": "Apache License, Version 2.0",  # Apache-2.0
    "olefile": "BSD 3-Clause",  # BSD-3-Clause
    "pytest": "MIT",  # MIT
}

#: ``NOTICE`` entries that are deliberately **not** dependencies of this release. ``olefile``
#: is the future ``.msg`` reader (Phase 1b): named so a reader can see the plan, never
#: installed by this package, and `test_olefile_is_not_a_declared_dependency` pins that.
NOTICE_ONLY = {"olefile": "the future .msg reader (Phase 1b); not a dependency of this release"}

#: A NOTICE row: two-space indent, the name, then ``(licence-id)``.
_NOTICE_ROW = re.compile(r"^\s{2}([A-Za-z0-9._-]+)\s+\(([^)]+)\)")
#: A PEP 508 requirement's distribution name: everything up to the first version specifier,
#: environment marker or extra.
_REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9._-]+")

#: Licence claims that mean a GPL family licence. The literal token ``GPL`` is **not** one of
#: them: ``NOTICE`` says "no GPL dependency is allowed anywhere" and that sentence must not
#: trip the scan. A GPL is caught as a licence *claim* (a parenthesised id, or the spelled-out
#: name).
_FORBIDDEN_LICENCE = (
    re.compile(r"GNU (?:Lesser |Affero )?General Public License", re.IGNORECASE),
    re.compile(r"\((?:A?LGPL|GPL)[-0-9.]*\)", re.IGNORECASE),
)

#: Distributions known to be GPL/LGPL/AGPL, so a future dependency added by name fails here.
_GPL_DISTRIBUTIONS = frozenset({"pymupdf", "extract-msg", "extract_msg", "pyqt5", "pyqt6"})


def _audited_name(name: str) -> str:
    """PEP 503's normalization: case-insensitive, ``-``/``_``/``.`` interchangeable."""
    return name.lower().replace("_", "-").replace(".", "-")


#: :data:`AUDITED_LICENCES` under the same normalization NOTICE's names are read with.
AUDITED_BY_NAME = {_audited_name(name): licence for name, licence in AUDITED_LICENCES.items()}


def _declared(pyproject: dict) -> dict[str, list[str]]:
    """``{"runtime"|"optional"|"dev": [requirement, ...]}`` from ``pyproject.toml``."""
    project = pyproject["project"]
    groups = {"runtime": list(project.get("dependencies", []))}
    for name, specs in project.get("optional-dependencies", {}).items():
        groups[name] = list(specs)
    return groups


def _declared_distributions(groups: dict[str, list[str]]) -> set[str]:
    names: set[str] = set()
    for specs in groups.values():
        for spec in specs:
            match = _REQUIREMENT_NAME.match(spec)
            assert match, f"unreadable requirement: {spec!r}"
            names.add(_audited_name(match.group(0)))
    return names


def _declared_licences(notice_text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in notice_text.splitlines():
        match = _NOTICE_ROW.match(line)
        if match:
            rows[_audited_name(match.group(1))] = match.group(2).strip()
    return rows


def _audit(declared: set[str], notice: dict[str, str]) -> list[str]:
    """Every way the two sides disagree. Empty means the notice matches what is declared."""
    problems: list[str] = []
    for name in sorted(declared - set(notice)):
        problems.append(f"NOTICE: {name!r} is declared but carries no licence entry")
    for name in sorted(set(notice) - declared):
        problems.append(
            f"NOTICE: {name!r} carries a licence entry but is not a declared dependency"
        )
    for name in sorted(set(notice) & declared):
        expected = AUDITED_BY_NAME.get(name)
        if expected is None:
            problems.append(f"NOTICE: {name!r} is declared but absent from AUDITED_LICENCES")
        elif notice[name] != expected:
            problems.append(
                f"NOTICE: {name!r} states {notice[name]!r}, the audit recorded {expected!r}"
            )
    return problems


def _notice_rows() -> dict[str, str]:
    return _declared_licences(NOTICE.read_text(encoding="utf-8"))


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# the licence and the notice
# ---------------------------------------------------------------------------------------------


def test_the_licence_is_the_apache_2_0_text_and_notice_states_the_holder() -> None:
    text = LICENSE.read_text(encoding="utf-8")
    assert "Apache License" in text and "Version 2.0, January 2004" in text
    notice = NOTICE.read_text(encoding="utf-8")
    assert notice.startswith("email-extract\n")
    assert "Copyright 2026 Ivan Ortega" in notice
    assert "Apache License, Version 2.0 (see LICENSE)" in notice


def test_pyproject_declares_the_same_licence_and_ships_both_files() -> None:
    project = _pyproject()["project"]
    assert project["license"] == "Apache-2.0"
    assert sorted(project["license-files"]) == ["LICENSE", "NOTICE"]
    assert project["authors"] == [{"name": "Ivan Ortega"}]


def test_the_runtime_dependency_is_exactly_docextract_core() -> None:
    """The exit criterion names it: runtime dependencies are exactly ``docextract-core``."""
    groups = _declared(_pyproject())
    runtime = {_audited_name(_REQUIREMENT_NAME.match(spec).group(0)) for spec in groups["runtime"]}
    assert runtime == {"docextract-core"}, runtime


def test_olefile_is_not_a_declared_dependency() -> None:
    """The one NOTICE-only row is honest: ``olefile`` is named and is not installed."""
    names = _declared_distributions(_declared(_pyproject()))
    assert "olefile" not in names, "olefile is a future dependency, not this release's"
    assert "olefile" in _notice_rows(), "the future .msg reader must stay named in NOTICE"


def test_notice_and_the_declared_dependencies_agree_both_ways() -> None:
    """The audit: no dependency without a licence entry, and no stale entry without a dependency."""
    declared = _declared_distributions(_declared(_pyproject())) | set(NOTICE_ONLY)
    assert _audit(declared, _notice_rows()) == []


def test_the_audit_records_the_same_licence_ids_as_notice() -> None:
    """NOTICE lists exactly the audited set, with the audited ids -- so a new dependency or a
    new licence claim fails here instead of shipping."""
    rows = _notice_rows()
    assert rows == {_audited_name(name): licence for name, licence in AUDITED_LICENCES.items()}


def test_the_audit_fails_on_an_unattributed_dependency_and_on_a_stale_entry() -> None:
    """Teeth: the audit is shown able to fail in every direction, naming the distribution."""
    rows = _notice_rows()
    declared = _declared_distributions(_declared(_pyproject()))
    audit_set = declared | set(NOTICE_ONLY)
    assert _audit(audit_set, rows) == []

    problems = _audit(audit_set | {"invented-package"}, rows)
    assert len(problems) == 1, problems
    assert "'invented-package' is declared but carries no licence entry" in problems[0]

    # A wrong id is the third direction: the notice and the audit disagree about the licence.
    problems = _audit(audit_set, {**rows, "olefile": "MIT"})
    assert len(problems) == 1, problems
    assert "states 'MIT'" in problems[0] and "BSD 3-Clause" in problems[0]

    # And a stale NOTICE entry, which is how a removed dependency would show up.
    problems = _audit(audit_set, {**rows, "removed-package": "MIT"})
    assert len(problems) == 1, problems
    assert "'removed-package' carries a licence entry but is not a declared dependency" in problems[0]


# ---------------------------------------------------------------------------------------------
# no GPL anywhere
# ---------------------------------------------------------------------------------------------


def _audited_files() -> list[Path]:
    """Every file the GPL scan reads: pyproject, NOTICE, LICENSE and ``tests/support/**``."""
    files = [PYPROJECT, NOTICE, LICENSE]
    files.extend(sorted(SUPPORT.rglob("*.py")))
    return files


def test_no_gpl_lgpl_or_agpl_licence_appears_in_the_audited_files() -> None:
    offenders: list[str] = []
    for path in _audited_files():
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_LICENCE:
            for match in pattern.finditer(text):
                offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)!r}")
    assert not offenders, f"a GPL licence claim appears in the tree: {offenders}"


def test_no_declared_dependency_is_a_gpl_distribution() -> None:
    names = {_audited_name(name) for name in AUDITED_LICENCES} | _declared_distributions(
        _declared(_pyproject())
    )
    offenders = sorted(names & _GPL_DISTRIBUTIONS)
    assert not offenders, f"a GPL distribution is declared or named: {offenders}"


def test_the_form_extra_does_not_request_the_agpl_pdf_extra() -> None:
    """``form-extract`` is Apache-2.0; its own ``pdf`` extra pulls PyMuPDF (AGPL-3.0).

    This package must request ``form-extract`` **plain**, so the AGPL is never reachable
    through a dependency this tree declares. The finding is recorded in the Phase 1 report.
    """
    groups = _declared(_pyproject())
    form = groups.get("form", [])
    assert form, "the form extra is gone; this test's premise moved"
    assert all("[" not in spec for spec in form), f"the form extra requests an extra: {form}"
    assert all(_audited_name(_REQUIREMENT_NAME.match(spec).group(0)) == "form-extract" for spec in form)
