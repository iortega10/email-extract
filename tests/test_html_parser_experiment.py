"""Turn 1.0d: the HTML decision experiment (build spec decision 1).

The experiment script is exercised end to end: it runs over every committed
``text/html`` fixture through its own walker-independent extractor, records the event
sequence, tree and projection hash per candidate, records the libxml2 version and
``error_log`` for lxml, and decides A versus B by decision 1's rule. Candidate A's
results are asserted identical across the two interpreters (the interpreter can change
``html.parser``; lxml's answer is pinned by the wheel, which this test cannot check).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import html_experiment as experiment  # noqa: E402
import runboth  # noqa: E402

from emailextract import versions  # noqa: E402

EXPERIMENT_DOC = ROOT / "docs" / "design" / "html-parser-experiment.md"

#: The tag path each quote-container selector must land on (wrapper tags dropped).
EXPECTED_PATHS = {
    "blockquote": ["blockquote"],
    "gmail_quote": ["div"],
    "outlook_divRplyFwdMsg": ["div"],
    "unclosed_blockquote": ["blockquote"],
    "table_in_blockquote": ["blockquote"],
}

#: The HTML fixtures the experiment must cover, in the walker-independent scan below.
#: This names no fixture file: the scan finds them by their ``Content-Type`` bytes.
_CONTENT_TYPE = b"content-type:"
_TEXT_HTML = b"text/html"


def _fixtures_with_html_body() -> set[str]:
    """Committed ``.eml`` fixtures whose bytes carry a ``text/html`` Content-Type line."""
    found: set[str] = set()
    for path in sorted((ROOT / "fixtures").rglob("*.eml")):
        relative = path.relative_to(ROOT / "fixtures")
        if "real" in relative.parts:
            continue
        lowered = path.read_bytes().lower()
        for line in lowered.splitlines():
            if line.startswith(_CONTENT_TYPE) and _TEXT_HTML in line:
                found.add(path.relative_to(ROOT).as_posix())
                break
    return found


def test_the_experiment_runs_over_every_html_fixture() -> None:
    """Every ``text/html`` fixture is covered, the hashes are stable, and A is identical
    on both interpreters."""
    report = experiment.run()
    fixture_inputs = [item["name"] for item in report["inputs"] if item["name"].startswith("fixture:")]
    covered = {name.split("#", 1)[0][len("fixture:") :] for name in fixture_inputs}
    assert covered == _fixtures_with_html_body()
    assert covered, "the experiment covered no HTML fixture: it would be vacuous"

    for item in report["inputs"]:
        assert len(item["A"]["event_sequence_hash"]) == 64, item["name"]
        assert len(item["A"]["projection_hash"]) == 64, item["name"]
        assert len(item["A"]["tree_hash"]) == 64, item["name"]

    # Determinism: a second run over the same bytes is byte-identical.
    again = experiment.run()
    assert again["inputs"] == report["inputs"]

    # Candidate A under the second interpreter: the results must be identical.
    second = runboth.find_python311()
    if second is None:
        print("html_experiment: no CPython 3.11 found -- cross-interpreter A not checked")
        return
    prefix, source, version = second
    completed = subprocess.run(
        [*prefix, "tools/html_experiment.py", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    other = json.loads(completed.stdout)

    def a_map(record: dict) -> dict:
        return {
            item["name"]: (
                item["A"]["event_sequence_hash"],
                item["A"]["tree_hash"],
                item["A"]["projection_hash"],
            )
            for item in record["inputs"]
        }

    assert a_map(other) == a_map(report), (
        f"candidate A differs between CPython {report['cpython']} and {version} ({source})"
    )
    assert other["decision"] == report["decision"]


def test_the_experiment_records_the_libxml2_version_and_error_log() -> None:
    """Candidate B records the libxml2 and lxml versions and the parser ``error_log``."""
    report = experiment.run()
    if not report["lxml"]["available"]:
        pytest.skip(f"lxml not installed: B not run ({report['lxml']['reason']})")
    b_records = [item["B"] for item in report["inputs"] if item["B"] is not None]
    assert b_records
    import lxml.etree as etree

    for record in b_records:
        assert record["libxml2_version"] == list(etree.LIBXML_VERSION)
        assert record["lxml_version"] == ".".join(str(part) for part in etree.LXML_VERSION)
        assert isinstance(record["error_log"], str)
    assert report["lxml"]["libxml2_version"] == list(etree.LIBXML_VERSION)
    assert report["lxml"]["lxml_version"] == ".".join(str(part) for part in etree.LXML_VERSION)


def test_the_chosen_candidate_places_quote_containers_identically() -> None:
    """The chosen candidate lands every quote container on the expected node.

    If B had been chosen it would have to equal A on every container (decision 1);
    since neither is clean on the unclosed case, A is chosen and B matches A on the
    closed containers only.
    """
    report = experiment.run()
    decision = report["decision"]
    assert decision in {"A", "B"}
    for name, expected_path in EXPECTED_PATHS.items():
        locator = report["quote_containers"][name][decision]
        assert locator is not None, name
        assert locator["path"] == expected_path, name
        assert len(locator["span"]) == 2 and locator["span"][0] <= locator["span"][1], name
    if decision == "B":
        assert all(
            result["match"] for result in report["quote_containers"].values()
        ), "B was chosen but does not place every container at A's node"
    else:
        assert report["closed_snippets_match"] is True
        assert report["neither_clean"] is True


def test_an_unclosed_blockquote_is_recorded_not_closed() -> None:
    """An unclosed ``<blockquote>`` keeps the following text inside a span A leaves open."""
    report = experiment.run()
    chosen = report["decision"]
    key = "snippet:unclosed_blockquote"
    item = next(entry for entry in report["inputs"] if entry["name"] == key)
    locator = report["quote_containers"]["unclosed_blockquote"][chosen]
    projection = item[chosen]["projection"]
    # The following new text is inside the container's span -- recorded, never dropped.
    assert locator["span"][1] == len(projection)
    assert "New reply after the unclosed container." in projection[
        locator["span"][0] : locator["span"][1]
    ]
    assert report["gap_id"] == "body.html_quote_rule_gap"
    rule = report["unclosed_container_rule"]
    assert rule is not None and "recorded, never closed" in rule
    assert experiment.GAP_HTML_QUOTE_RULE_GAP in rule
    if chosen == "A":
        # A's node for the unclosed container is left open: --closed is False.
        blockquotes = [node for node in item["A"]["tree"] if node["tag"] == "blockquote"]
        assert blockquotes and blockquotes[-1]["closed"] is False


def test_the_experiment_document_names_the_pinned_wheel() -> None:
    """The document records the lxml wheel and libxml2 versions B ran under."""
    report = experiment.run()
    text = EXPERIMENT_DOC.read_text(encoding="utf-8")
    if report["lxml"]["available"]:
        assert report["lxml"]["lxml_version"] in text, "the document omits the lxml wheel version"
        libxml2 = ".".join(str(part) for part in report["lxml"]["libxml2_version"])
        assert libxml2 in text, "the document omits the libxml2 version"
    else:
        assert report["lxml"]["reason"] in text, "the document omits the closed reason B did not run"


def test_htmltext_version_gates_the_projection() -> None:
    """``HTMLTEXT_VERSION`` is the key of the four recorded inputs; changing one moves it."""
    cpython = ".".join(str(part) for part in sys.version_info[:2])
    key = versions._htmltext_version_key
    assert versions.HTMLTEXT_VERSION == key(
        candidate="htmlparser",
        cpython=cpython,
        projection="verbatim-non-style-script",
        unclosed="recorded-not-closed",
    )
    assert versions.HTMLTEXT_VERSION.startswith("1+htmlparser+")
    base = dict(
        candidate="htmlparser",
        cpython=cpython,
        projection="verbatim-non-style-script",
        unclosed="recorded-not-closed",
    )
    for change in (
        {"candidate": "lxml"},
        {"cpython": "9.9"},
        {"projection": "collapsed-whitespace"},
        {"unclosed": "synthetic-end-tag"},
    ):
        assert key(**{**base, **change}) != versions.HTMLTEXT_VERSION, change


_PROBE = """
import importlib.abc
import sys


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] == "lxml":
            raise ImportError("blocked at import time: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

from emailextract.parse import Limits, parse

result = parse(b"From: a@b\\r\\nSubject: s\\r\\n\\r\\nbody", limits=Limits.untrusted())
assert result.kind == "rfc822"
leaked = sorted(name for name in sys.modules if name.split(".")[0] == "lxml")
print("clean" if not leaked else "leaked:" + ",".join(leaked))
"""


def test_the_package_imports_with_lxml_blocked() -> None:
    """``lxml`` stays optional and unimported: the package imports and parses without it."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean", result.stdout + result.stderr

