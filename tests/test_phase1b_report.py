"""Turn 1b.10b: ``docs/phase1b-report.md`` -- the eight sections, the versions, the asymmetry.

The report is the phase's closing artifact and a report is not a gate, so this module checks only
what a report can be *wrong* about:

* the eight sections the ledgers require (``docs/design/phase1b-ledgers.md`` section (g)) are each
  present exactly once with a non-empty body, and every ``tests/...py::name`` the report cites
  resolves (reusing ``tests/test_phase1_scope.py``'s helpers -- none of its assertions changes);
* it names the version bumps (``OUTPUT_SCHEMA_VERSION`` ``"5"`` -> ``"6"`` in Turn 1b.1, the three
  new constants at ``"1"``, the release ``0.2.0``) **and they match the code**;
* it records the ``max_input_bytes`` asymmetry (a ~50 MB ``.msg`` passes the 64 MiB gate its ~67 MB
  base64 ``.eml`` twin fails; peak bounded by ``max_input_bytes``).

The content itself is the owner's review.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _path in (ROOT, ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from test_phase1_scope import _citation_problems, _report_problems  # noqa: E402

import emailextract  # noqa: E402
from emailextract import versions  # noqa: E402

REPORT = ROOT / "docs" / "phase1b-report.md"

#: The sections ``docs/design/phase1b-ledgers.md`` section (g) requires, in its order.
SECTIONS = (
    "## What was built",
    "## Named resolutions",
    "## Coverage",
    "## Gap gate",
    "## Label-versus-parser findings",
    "## Licences",
    "## The max_input_bytes asymmetry",
    "## Not done",
)


def _text() -> str:
    assert REPORT.is_file(), f"the Phase 1b report is not committed at {REPORT}"
    return REPORT.read_text(encoding="utf-8")


def test_the_phase1b_report_sections_are_present_and_non_empty() -> None:
    """Each required section appears exactly once with a body, and every citation resolves."""
    text = _text()
    assert _report_problems(text, SECTIONS) == [], _report_problems(text, SECTIONS)
    cited = sorted({match for match in _citations(text)})
    assert cited, "the report cites no test id at all"
    assert _citation_problems(text) == [], _citation_problems(text)
    # The check can fail, in both directions, on a stub: an empty body, a repeated heading and a
    # missing section are each named, and a citation to a missing symbol is caught.
    stub = "\n".join(f"{section}\n\nbody\n" for section in SECTIONS[:-1])
    stub += f"\n{SECTIONS[-1]}\n\n"
    assert _report_problems(stub, SECTIONS) == [
        f"the required section {SECTIONS[-1]!r} has an empty body"
    ]
    repeated = "\n".join(f"{section}\n\nbody\n" for section in SECTIONS)
    repeated += f"\n{SECTIONS[3]}\n\nbody\n"
    assert _report_problems(repeated, SECTIONS) == [
        f"the required section {SECTIONS[3]!r} appears 2 times"
    ]
    for section in SECTIONS:
        missing = "\n".join(f"{other}\n\nbody\n" for other in SECTIONS if other != section)
        assert _report_problems(missing, SECTIONS) == [f"the required section {section!r} is missing"]
    assert _citation_problems(text + "\n`tests/test_phase1b_report.py::test_no_such_case`\n") == [
        "the report cites tests/test_phase1b_report.py::test_no_such_case, but "
        "test_no_such_case is not defined there"
    ]


def _citations(text: str) -> set[str]:
    from test_phase1_scope import _CITATION

    return {f"{path}::{name}" for path, name in _CITATION.findall(text)}


def test_the_phase1b_report_names_the_version_bumps_and_the_licences() -> None:
    """The bumps the phase made are named in the report **and** match the code."""
    text = _text()
    # The bumps, named the way the report names them.
    assert "`OUTPUT_SCHEMA_VERSION` `\"5\"` -> `\"6\"`" in text
    for constant in ("`CFB_VERSION`", "`MSG_READER_VERSION`", "`MSG_PROJECTION_VERSION`"):
        assert constant in text, constant
    assert "`EMAIL_PARSER_VERSION`" in text
    assert "0.2.0" in text, "the release version must be named"
    # ... and they are the code's own values.
    assert versions.OUTPUT_SCHEMA_VERSION == "6"
    assert versions.CFB_VERSION == "1"
    assert versions.MSG_READER_VERSION == "1"
    assert versions.MSG_PROJECTION_VERSION == "1"
    assert versions.EMAIL_PARSER_VERSION == "2", "Phase 1b moves no .eml behaviour"
    # The release is 0.2.0; its TestPyPI dry run (docs/releasing.md) is 0.2.0rcN of the same release.
    assert re.fullmatch(r"0\.2\.0(rc\d+)?", emailextract.__version__), emailextract.__version__
    # The licence rows.
    assert "olefile" in text and "BSD-3-Clause" in text
    assert "Apache-2.0" in text
    assert "No GPL" in text or "no GPL" in text


def test_the_phase1b_report_records_the_max_input_bytes_asymmetry() -> None:
    """The asymmetry is a recorded section, with its two sides and the bounded peak."""
    text = _text()
    assert "max_input_bytes" in text
    assert "64 MiB" in text and "50 MB" in text
    assert "base64" in text and ".msg" in text
    assert "peak" in text
    assert "asymmetry" in text
