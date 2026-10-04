"""Turn 0.5: the sibling contract -- discovery, the locator, the child link (D5, D12).

The contract points under test: a sibling's presence is asked with ``find_spec``
and never by importing it; a not-installed sibling is an environmental status
carrying ``needed_sibling``; the locator honours its configured order; the child
link is the four-state ``ChildLink``; and the citation has three buckets that are
disjoint, never mixed and never partially filled -- a missing child store makes the
child bucket ``unknown`` **whole**, and a child's ``page_count``/``sheet_count``
are ``unknown`` (never zero, never copied from the email side) exactly then.

Everything runs against ``tests/support/fake_store.py``: no real sibling is
imported, called or required, and no child is ever really extracted. The two
branches of discovery are covered on purpose -- present (``pytest.importorskip``,
which says so when it skips) and genuinely absent (``sys.modules`` patched out and
``find_spec`` forced to None) -- so the path the environment does not exercise is
still the path a test names.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from emailextract import model, siblings, versions
from emailextract.model import (
    AttachmentOccurrence,
    ChildLinkState,
    Status,
    TriState,
    TriValue,
    TypeVerdicts,
    built_axis,
)
from emailextract.siblings import (
    ROUTE_FORM,
    ROUTE_WORD,
    ChildCitationChild,
    ChildCitationStamp,
    ChildCitationVia,
    CitationChildState,
    Locator,
    same_content_hash,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import fake_store  # noqa: E402

HASH = "a" * 64
OTHER_HASH = "b" * 64
OCCURRENCE = "1.2 @ <filing@example.com>"
OTHER_OCCURRENCE = "1.3 @ <filing@example.com>"

#: A sibling-shaped citation payload: word-extract's own address space (a part id
#: and a union offset range), not email coordinates.
PAYLOAD = {"node_id": "n7", "part_id": "officeDocument:1", "start": 10, "end": 24}

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_TYPE = "application/pdf"


def _occurrence(*, attachment_id: str = HASH, occurrence_path: str = OCCURRENCE, **overrides) -> AttachmentOccurrence:
    fields: dict[str, object] = dict(
        attachment_id=attachment_id,
        occurrence_path=occurrence_path,
        part_id="part-1",
        filename_raw="filing.docx",
        size_bytes=2048,
        sha256=attachment_id,
        route=ROUTE_WORD,
        route_axis=built_axis(),
        type_verdicts=TypeVerdicts(
            declared_mime=TriValue(state=TriState.VALUE, value=DOCX_TYPE),
            winner=model.TypeVerdictSource.DECLARED_MIME,
        ),
    )
    fields.update(overrides)
    return AttachmentOccurrence(**fields)  # type: ignore[arg-type]


def _resolved(**store_kwargs) -> tuple[fake_store.FakeSiblingStore, object]:
    store = fake_store.FakeSiblingStore(**store_kwargs)
    store.add(HASH, citation=PAYLOAD, page_count=3, sheet_count=None)
    return store, siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator((store,))
    )


# ------------------------------------------------------- the contract, resolved


def test_the_contract_is_green_against_the_fake_store() -> None:
    store, result = _resolved()
    assert result.link.state is ChildLinkState.RESOLVED
    assert result.link.child_id == HASH
    assert result.link.store_id == store.child_store_id
    # Bucket (b) is the sibling's citation byte for byte: equal in every key and value, in its own
    # coordinates, never translated or renumbered into email coordinates. (It is a SNAPSHOT, not
    # the store's own object: see test_a_linked_citation_does_not_alias_the_stores_own_payload.)
    assert result.citation.child.state is CitationChildState.VERBATIM
    assert result.citation.child.payload == PAYLOAD
    assert result.citation.child.payload == {"node_id": "n7", "part_id": "officeDocument:1", "start": 10, "end": 24}
    # Bucket (a) is email-extract's own coordinates.
    assert result.citation.via.attachment_id == HASH
    assert result.citation.via.occurrence == OCCURRENCE
    assert result.citation.via.route == ROUTE_WORD
    assert result.citation.via.child_store == store.child_store_id
    # Bucket (c) is stamped, including the email-extract version that made the link.
    stamp = result.citation.stamp
    assert stamp.sibling == "word"
    assert stamp.sibling_parser_version == "1"
    assert stamp.child_store_id == store.child_store_id
    assert stamp.child_store_revision == "1"
    assert stamp.core_version == "0.1.0"
    assert stamp.linked_by_email_parser_version == versions.EMAIL_PARSER_VERSION


def test_the_childs_own_counts_come_from_the_child() -> None:
    """``sibling_derived``: the numbers are the child's, not the email side's."""
    _store, result = _resolved()
    assert result.facts.page_count.state is TriState.VALUE
    assert result.facts.page_count.value == "3"
    # word-extract has no sheets: the child says "absent", not zero.
    assert result.facts.sheet_count.state is TriState.ABSENT


def test_the_citation_round_trips_through_the_strict_codec() -> None:
    _store, result = _resolved()
    payload = model.record_to_bytes(result.citation)
    assert model.record_from_bytes(siblings.ChildCitation, payload) == result.citation
    # The child bucket is opaque: its keys are the sibling's business, while our own
    # shape stays strict.
    assert b'"start"' in payload


# ------------------------------------------------------------- the unknown states


def test_a_version_mismatch_child_yields_version_mismatch_with_both_versions() -> None:
    store = fake_store.FakeSiblingStore(sibling_parser_version="2")
    store.add(HASH, citation=PAYLOAD, page_count=1)
    result = siblings.link_child(
        HASH,
        occurrence=OCCURRENCE,
        route=ROUTE_WORD,
        locator=Locator((store,)),
        expected_sibling_parser_version="1",
    )
    assert result.link.state is ChildLinkState.VERSION_MISMATCH
    assert result.link.expected_version == "1"
    assert result.link.found_version == "2"
    assert result.link.store_id == store.child_store_id
    assert result.citation.child.state is CitationChildState.UNKNOWN
    assert result.citation.child.reason_id == "sibling.version_mismatch"
    assert result.facts.page_count.state is TriState.UNKNOWN


def test_a_core_version_mismatch_is_refused_too() -> None:
    store = fake_store.FakeSiblingStore(core_version="0.2.0")
    store.add(HASH, citation=PAYLOAD)
    result = siblings.link_child(
        HASH,
        occurrence=OCCURRENCE,
        route=ROUTE_FORM,
        locator=Locator((store,)),
        expected_core_version="0.1.0",
    )
    assert result.link.state is ChildLinkState.VERSION_MISMATCH
    assert (result.link.expected_version, result.link.found_version) == ("0.1.0", "0.2.0")


def test_a_deleted_child_store_yields_store_absent_and_keeps_the_manifest_useful() -> None:
    store = fake_store.FakeSiblingStore(present=False)
    store.add(HASH, citation=PAYLOAD, page_count=3)
    occurrence = _occurrence()
    result = siblings.link_occurrence(occurrence, route=ROUTE_WORD, locator=Locator((store,)))
    assert result.link.state is ChildLinkState.STORE_ABSENT
    assert result.link.store_id is None
    # The email side's own facts are untouched: filename, type, sha256, size are
    # enough to re-run the sibling (D5).
    assert occurrence.filename_raw == "filing.docx"
    assert occurrence.size_bytes == 2048
    assert occurrence.sha256 == HASH
    assert occurrence.type_verdicts.declared_mime.value == DOCX_TYPE
    # And only the child-derived facts went unknown.
    assert result.facts.page_count.state is TriState.UNKNOWN


def test_a_store_with_no_entry_for_the_hash_yields_child_absent() -> None:
    store = fake_store.FakeSiblingStore()
    result = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator((store,))
    )
    assert result.link.state is ChildLinkState.CHILD_ABSENT
    assert result.link.store_id is None
    assert result.citation.child.reason_id == "sibling.child_absent"
    assert result.facts.page_count.reason_id == "sibling.child_absent"


def test_a_missing_store_makes_the_child_citation_unknown_whole() -> None:
    result = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator(())
    )
    assert result.link.state is ChildLinkState.STORE_ABSENT
    child = result.citation.child
    assert child.state is CitationChildState.UNKNOWN
    assert child.reason_id == "sibling.store_absent"
    # Unknown WHOLE: no field of the child bucket is partially filled.
    populated = {
        field.name: getattr(child, field.name)
        for field in dataclasses.fields(ChildCitationChild)
        if getattr(child, field.name) is not None
    }
    assert populated == {"state": CitationChildState.UNKNOWN, "reason_id": "sibling.store_absent"}
    # No store was reached, so there is nothing to stamp.
    assert result.citation.stamp is None


def test_the_counts_are_unknown_when_the_store_is_absent_never_zero() -> None:
    result = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator(())
    )
    for name in ("page_count", "sheet_count"):
        value = getattr(result.facts, name)
        assert value.state is TriState.UNKNOWN, name
        assert value.value is None, name
        assert value.reason_id == "sibling.store_absent", name
        assert value.state is not TriState.ABSENT and value.value != "0", name
    # Nothing on the email side carries a count to copy: the fields are not a
    # projection of the occurrence.
    assert not hasattr(_occurrence(), "page_count")
    assert not hasattr(_occurrence(), "sheet_count")


# ---------------------------------------------------------------- the buckets


def test_the_three_buckets_are_disjoint() -> None:
    _store, result = _resolved()
    buckets = {
        "via": {field.name for field in dataclasses.fields(ChildCitationVia)},
        "child": set(result.citation.child.payload or {}),
        "stamp": {field.name for field in dataclasses.fields(ChildCitationStamp)},
    }
    shared = (
        buckets["via"] & buckets["child"],
        buckets["via"] & buckets["stamp"],
        buckets["child"] & buckets["stamp"],
    )
    assert shared == (set(), set(), set()), buckets


def test_the_passthrough_is_opaque_and_a_later_change_to_the_siblings_object_changes_nothing() -> None:
    payload = dict(PAYLOAD)
    store = fake_store.FakeSiblingStore()
    store.add(HASH, citation=payload, page_count=1)
    result = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator((store,))
    )
    via_before = result.citation.via
    stamp_before = result.citation.stamp
    facts_before = result.facts
    snapshot = dict(result.citation.child.payload)
    payload["start"] = 999
    payload["email_offset"] = 0  # an email coordinate, added to the SIBLING's object after linking
    # The linked citation is a snapshot: a later change to the sibling's own object changes nothing,
    # in any bucket, and nothing was re-derived into email coordinates.
    assert result.citation.child.payload == snapshot
    assert "email_offset" not in result.citation.child.payload
    assert result.citation.via == via_before
    assert result.citation.stamp == stamp_before
    assert result.facts == facts_before


def test_two_occurrences_of_one_file_are_two_citations_never_merged() -> None:
    store = fake_store.FakeSiblingStore()
    store.add(HASH, citation=PAYLOAD, page_count=1)
    locator = Locator((store,))
    first = siblings.link_child(HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=locator)
    second = siblings.link_child(
        HASH, occurrence=OTHER_OCCURRENCE, route=ROUTE_WORD, locator=locator
    )
    assert first.citation != second.citation, "occurrences are never merged"
    assert first.citation.via.occurrence != second.citation.via.occurrence
    assert first.link.state is second.link.state is ChildLinkState.RESOLVED
    assert same_content_hash(first.citation, second.citation) is True
    # A different content hash is the other side of the boolean.
    other = siblings.link_child(
        OTHER_HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator(())
    )
    assert same_content_hash(first.citation, other.citation) is False


# ---------------------------------------------------------------- the locator


def test_the_locator_order_is_honoured() -> None:
    first = fake_store.FakeSiblingStore(child_store_id="first")
    second = fake_store.FakeSiblingStore(child_store_id="second")
    third = fake_store.FakeSiblingStore(child_store_id="third")
    second.add(HASH, citation=PAYLOAD)
    third.add(HASH, citation=PAYLOAD)
    result = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator((first, second, third))
    )
    assert result.link.store_id == "second", "the first reachable store holding it wins"
    other = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator((third, second))
    )
    assert other.link.store_id == "third"


def test_a_deleted_store_is_skipped_for_the_next_one() -> None:
    deleted = fake_store.FakeSiblingStore(child_store_id="deleted", present=False)
    deleted.add(HASH, citation=PAYLOAD)
    live = fake_store.FakeSiblingStore(child_store_id="live")
    live.add(HASH, citation=PAYLOAD)
    result = siblings.link_child(
        HASH, occurrence=OCCURRENCE, route=ROUTE_WORD, locator=Locator((deleted, live))
    )
    assert result.link.store_id == "live"


# --------------------------------------------------------------- discovery


def test_discovery_asks_find_spec_and_never_imports(monkeypatch) -> None:
    """Importing a sibling to see whether it exists is the defect this avoids."""
    monkeypatch.delitem(sys.modules, "wordextract", raising=False)
    monkeypatch.delitem(sys.modules, "formextract", raising=False)
    report = siblings.discovery()
    assert set(report) == {"word", "form"}
    assert all(isinstance(installed, bool) for installed in report.values())
    assert "wordextract" not in sys.modules
    assert "formextract" not in sys.modules


def test_an_unknown_sibling_family_is_refused() -> None:
    with pytest.raises(ValueError):
        siblings.module_name("spreadsheet")
    with pytest.raises(ValueError):
        siblings.is_installed("spreadsheet")


def test_not_installed_carries_needed_sibling_and_no_reason() -> None:
    status = siblings.not_installed("word")
    assert status.status is Status.NOT_INSTALLED
    assert status.needed_sibling == "word"
    assert status.reason is None and status.crypto_kind is None


def test_the_not_installed_path_with_the_siblings_genuinely_absent(monkeypatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    monkeypatch.delitem(sys.modules, "wordextract", raising=False)
    monkeypatch.delitem(sys.modules, "formextract", raising=False)
    assert siblings.discovery() == {"word": False, "form": False}
    assert siblings.missing_siblings() == ("form", "word")
    assert siblings.is_installed("word") is False
    assert siblings.not_installed("word").needed_sibling == "word"


def test_the_sibling_presence_path_when_the_package_is_installed() -> None:
    """The other branch of discovery, run only where a sibling really is installed."""
    pytest.importorskip(
        "wordextract",
        reason="word-extract is not installed in this environment; the "
        "genuinely-absent test above covers the branch that runs here",
    )
    assert siblings.is_installed("word") is True
    assert siblings.discovery()["word"] is True


def test_the_package_imports_with_neither_sibling_imported() -> None:
    """``emailextract`` (and ``emailextract.siblings``) never pull a sibling in."""
    script = (
        "import sys, emailextract, emailextract.siblings; "
        "assert 'wordextract' not in sys.modules, 'wordextract was imported'; "
        "assert 'formextract' not in sys.modules, 'formextract was imported'"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_a_linked_citation_does_not_alias_the_stores_own_payload() -> None:
    """The verbatim bucket is a snapshot: a record that is frozen must not hold the same mutable dict
    the child store holds, or a later change to the sibling's object would silently change the linked
    citation (and the bytes the email store keeps)."""
    store = fake_store.FakeSiblingStore()
    original = {"start": 10, "end": 20, "nested": {"k": [1, 2]}}
    store.add(HASH, citation=original)
    linked = siblings.link_child(HASH, occurrence="1.2@m", route="word", locator=siblings.Locator(stores=(store,)))
    assert linked.citation.child.payload == original
    assert linked.citation.child.payload is not original
    original["start"] = 999
    original["nested"]["k"].append(3)
    assert linked.citation.child.payload == {"start": 10, "end": 20, "nested": {"k": [1, 2]}}
