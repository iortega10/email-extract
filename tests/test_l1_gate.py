"""The L1 gate: explicit pass/fail, at 100%, and able to fail (build spec Turn 0.4).

``l1_gate`` is the oracle as a verdict: the counts a human reads (matched, mismatched,
unmeasurable, unmodelled, ``not_yet`` by phase) and the one bit a caller exits on. The
falsification cases run against a **copy** of a committed sidecar in ``tmp_path`` -- a wrong
sha256, a shifted header span, a wrong part span, a missing region, a wrong decode-chain
verdict, a missing fixture, an unmodelled fact, an empty corpus and a corpus that compares
nothing -- plus a control: an untampered copy is green, so the wrong copies prove something.

The committed corpus is **not** green, and that is the honest state of the turn: the labels
and the walker disagree on seven facts across four fixtures (a 2-byte first-delimiter slip in
``alternative_text_html`` and the "does the charset ladder run over a non-text payload"
reading in three fixtures, the one ``docs/design/label-questions.md`` Q1 leaves open). Those
are FINDINGS -- a label and the walker disagreeing is never reconciled by editing a label --
so they are asserted here as the exact, named set, and the report carries them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402
from support.sidecar_copy import ALTERNATIVE, ATTACHMENTS, PLAIN_SIMPLE, payload_of, tamper, write  # noqa: E402

from emailextract.evals import GateResult, l1_gate  # noqa: E402

FIXTURES = sidecar_copy.FIXTURES

#: The Turn 0.4 gate found seven label/walker disagreements, from two root causes, both resolved
#: in review (the bytes were the judge, per the independence rule): the ``alternative_text_html``
#: sidecar had the first delimiter 21 bytes long and part 1.1 two bytes late (the delimiter
#: line ``--b0-alt-20250304`` plus its CRLF is 19 bytes), a hand-typing error corrected in the
#: label; and the walker ran the TEXT charset ladder over binary parts (a pdf, a png, an office zip), reporting a
#: charset, a fallback and a false ``body.decode_destroyed_bytes``, a walker defect fixed
#: (``DECODE_CHAIN_VERSION`` 2). The committed corpus is now green.


def _facts(payload):
    return payload["facts"]


def test_the_gate_compares_the_whole_corpus_and_counts_not_yet_by_phase() -> None:
    gate = l1_gate()
    assert isinstance(gate, GateResult)
    assert gate.skipped is False
    assert gate.data["sidecars"] == 119
    assert gate.data["matched"] > 0
    # not_yet is by phase, never a single total: phase 1 (parser) and phase 3 (time/thread).
    # Turn 1.1 made headers.projection, headers.decoded, headers.parameters and its live
    # gaps.later facts measurable, so 30 phase-1 sidecar facts moved from not_yet to compared.
    # Turn 1.2 made headers.addresses measurable, moving its 7 sidecar facts to compared.
    # Turn 1.3 made headers.date measurable (6 sidecar facts) and turned the two date-gap
    # gaps.later facts live, moving 8 more phase-1 facts to compared.
    # Turn 1.4 made body.text measurable (8 sidecar facts) and turned its one gap
    # (body.flowed_reflow_unresolved) live, moving 9 more phase-1 facts to compared.
    # Turn 1.5b made body.html_spans, body.alternative_group, body.selection, body.cid_refs
    # and body.plain_effectively_empty measurable and turned the four new gap ids
    # (body.digest_default_not_applied, body.no_text_part, security.remote_content_present,
    # body.inline_data_uri) live, moving 23 more phase-1 facts to compared.
    # The quote-catalogue follow-up (rows 27-29) adds three sidecars whose quote facts
    # are still not_yet, moving 9 more phase-1 facts to not_yet.
    assert gate.data["not_yet"] == {1: 192, 3: 26}


def test_the_committed_corpus_is_green_with_no_label_walker_disagreement() -> None:
    """Every fact the skeleton walker can produce matches its hand-typed label, over all 16 fixtures."""
    gate = l1_gate()
    assert list(gate.data["mismatches"]) == [], gate.data["mismatches"]
    assert gate.data["mismatched"] == 0
    assert gate.passed is True


def test_the_gate_reports_every_phase_the_corpus_waits_on() -> None:
    gate = l1_gate()
    phases = {line.split(",")[1].split(":")[0].strip() for line in gate.evidence if "not_yet, phase" in line}
    assert phases == {"phase 1", "phase 3"}


def test_an_untampered_copy_is_green(tmp_path: Path) -> None:
    """The control: the wrong copies below fail because they are wrong, not because they are copies."""
    write(tmp_path / "clean", payload_of(PLAIN_SIMPLE), source=PLAIN_SIMPLE)
    gate = l1_gate(tmp_path / "clean")
    assert gate.passed is True, gate.lines()


def test_a_wrong_sha256_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        _facts(payload)["container.sha256"]["value"] = "0" * 64

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert "mismatched=1" in gate.detail
    assert any("container.sha256 mismatch" in line for line in gate.evidence), gate.evidence


def test_a_shifted_header_span_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        row = _facts(payload)["headers.fields"]["value"][0]
        row[4] = [row[4][0] + 1, row[4][1]]  # name_span shifted one byte

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert any("headers.fields mismatch" in line for line in gate.evidence), gate.evidence


def test_a_wrong_part_span_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        row = _facts(payload)["part.tree"]["value"][0]
        row[5] = [row[5][0], row[5][1] + 1]  # body_span one byte long

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert any("part.tree mismatch" in line for line in gate.evidence), gate.evidence


def test_a_missing_region_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        _facts(payload)["part.regions"]["value"].pop()

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert any("part.regions mismatch" in line for line in gate.evidence), gate.evidence


def test_a_wrong_decode_chain_verdict_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        row = _facts(payload)["decode.chain"]["value"][0]
        row[4] = "utf-8"  # used_charset

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert any("decode.chain mismatch" in line for line in gate.evidence), gate.evidence


def test_a_missing_fixture_fails_the_gate(tmp_path: Path) -> None:
    payload = payload_of(PLAIN_SIMPLE)
    payload["fixture"] = "not_here.eml"
    (tmp_path / "gone").mkdir()
    (tmp_path / "gone" / PLAIN_SIMPLE.name).write_text(json.dumps(payload), encoding="utf-8")
    gate = l1_gate(tmp_path / "gone")
    assert gate.passed is False
    assert any("does not exist beside it" in line for line in gate.evidence), gate.evidence


def test_a_sidecar_naming_an_unmodelled_fact_fails_the_gate(tmp_path: Path) -> None:
    def mutate(payload):
        _facts(payload)["bogus.thing"] = {"phase": 0, "value": "whatever"}

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert "unmodelled=1" in gate.detail
    assert any("bogus.thing" in line for line in gate.evidence), gate.evidence


def test_an_empty_corpus_fails_the_gate(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    gate = l1_gate(tmp_path / "empty")
    assert gate.passed is False
    assert "empty" in gate.detail


def test_a_corpus_that_compares_nothing_fails_the_gate(tmp_path: Path) -> None:
    """A sidecar labelling only a later-phase fact: nothing is compared, so nothing is green."""

    def mutate(payload):
        facts = payload["facts"]
        for fact_id in list(facts):
            if facts[fact_id]["phase"] == 0:
                del facts[fact_id]

    tamper(tmp_path, PLAIN_SIMPLE, mutate)
    gate = l1_gate(tmp_path)
    assert gate.passed is False
    assert "nothing was compared" in gate.detail


def test_every_committed_sidecar_is_discovered_by_the_gate() -> None:
    """The gate reads the corpus the way the tests do, never a hand-typed subset of it."""
    corpus = sorted(
        path
        for path in FIXTURES.rglob("*.expected.json")
        if "real" not in path.relative_to(FIXTURES).parts
    )
    assert len(corpus) == 119
    assert [path for path in corpus if path == ATTACHMENTS] == [ATTACHMENTS]
    assert ALTERNATIVE.is_file()
