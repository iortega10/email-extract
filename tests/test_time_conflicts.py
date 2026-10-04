"""Turn 0.3: the TimeEvent conflict fixtures and the test-only reference evaluator (D15).

Each conflict fixture carries a hand-typed expected artifact: the evidence listing in
``emailextract.timeevent``'s shape, the order under each named policy and the unresolved
conflict pairs returned beside any order. ``tests/support/timeline_ref.py`` computes
those from the evidence list, so the hand-typed rows are checked against an independent
implementation -- it is not shipped and is not the timeline layer (that is
``docextract-timeline``, later, after Phase 3).

The contract points under test: ``received_chain_header_order`` runs by header order and
never by timestamp (the clock-skew fixture pins it); ``owner_manifest`` is a labelled
total-order override and not evidence-ranked; no policy is implicit; and the unresolved
pairs are non-empty exactly where the evidence conflicts -- an evidence list where every
claim names the same moment produces none.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from emailextract.evals.labels import load_sidecars

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import timeline_ref  # noqa: E402

SIDECARS = load_sidecars(ROOT / "fixtures")
TIME_STEMS = sorted(stem for stem in SIDECARS if SIDECARS[stem].path.parent.name == "time")


def _facts(stem: str) -> dict:
    return {fact_id: fact.value for fact_id, fact in SIDECARS[stem].facts.items()}


@pytest.mark.parametrize("stem", TIME_STEMS)
def test_the_hand_typed_orders_reproduce_under_the_reference_evaluator(stem: str) -> None:
    facts = _facts(stem)
    evidence = facts["time.evidence"]
    manifest = facts["time.owner_manifest"][0]
    result = timeline_ref.evaluate(evidence, timeline_ref.POLICIES, manifest)
    for policy_id, order_ids, not_placed in facts["time.orders"]:
        computed_order, computed_not_placed = result["orders"][policy_id]
        assert computed_order == order_ids, f"{stem}: {policy_id} order"
        assert computed_not_placed == not_placed, f"{stem}: {policy_id} not_placed"


@pytest.mark.parametrize("stem", TIME_STEMS)
def test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts(stem: str) -> None:
    facts = _facts(stem)
    evidence = facts["time.evidence"]
    manifest = facts["time.owner_manifest"][0]
    result = timeline_ref.evaluate(evidence, timeline_ref.POLICIES, manifest)
    computed = sorted(result["conflict_pairs"])
    typed = sorted((left, right) for left, right, _reason in facts["time.unresolved_pairs"])
    assert computed == typed, f"{stem}: conflict pairs"
    assert bool(computed) is facts["time.evidence_conflicts"]
    assert computed, f"{stem}: this fixture's evidence conflicts, so its pair list is not empty"


def test_agreeing_evidence_produces_no_unresolved_pairs() -> None:
    """The 'exactly where' half: a clean evidence list yields no pairs at all."""
    doc = "0" * 64
    clean = [
        {
            "event_id": "e_date",
            "doc_id": doc,
            "parent_event_id": None,
            "kind": "sent",
            "when_raw": "Tue, 4 Mar 2025 12:05:00 +0000",
            "when_utc": {"value": "2025-03-04T12:05:00Z"},
            "offset": {"value": "+0000"},
            "offset_origin": "stated_in_text",
            "precision": "second",
            "ambiguity": "none",
            "source": {"field": "Date", "ordinal": 4, "span": None},
            "trust": "claimed",
            "usable_for_arrival_ordering": True,
        },
        {
            "event_id": "e_hop",
            "doc_id": doc,
            "parent_event_id": None,
            "kind": "received_hop",
            "when_raw": "Tue, 4 Mar 2025 12:05:00 +0000",
            "when_utc": {"value": "2025-03-04T12:05:00Z"},
            "offset": {"value": "+0000"},
            "offset_origin": "stated_in_text",
            "precision": "second",
            "ambiguity": "none",
            "source": {"field": "Received", "ordinal": 2, "span": None},
            "trust": "claimed",
            "usable_for_arrival_ordering": True,
        },
    ]
    assert timeline_ref.conflict_pairs(clean) == []
    single = [clean[0]]
    assert timeline_ref.conflict_pairs(single) == []


def test_the_chain_runs_by_header_order_and_never_by_timestamp() -> None:
    facts = _facts("received_clock_skew")
    evidence = facts["time.evidence"]
    order_ids, not_placed = timeline_ref.order(
        "received_chain_header_order", evidence, facts["time.owner_manifest"][0]
    )
    assert order_ids == ["e_hop_first", "e_hop_last"]
    assert not_placed == ["e_date"]
    times = {row["event_id"]: row["when_utc"]["value"] for row in evidence}
    assert times["e_hop_first"] > times["e_hop_last"], "this fixture only works with the skew in place"


def test_owner_manifest_is_a_total_order_override_not_evidence_ranked() -> None:
    facts = _facts("date_vs_mtime")
    evidence = facts["time.evidence"]
    manifest = facts["time.owner_manifest"][0]
    order_ids, not_placed = timeline_ref.order("owner_manifest", evidence, manifest)
    assert order_ids == ["e_mtime", "e_date"], "the owner may place what no evidence policy may"
    assert not_placed == []
    evidence_order, evidence_not_placed = timeline_ref.order("header_date_claimed", evidence, manifest)
    assert evidence_order == ["e_date"]
    assert evidence_not_placed == ["e_mtime"], "filesystem time is not arrival evidence (D15)"


def test_an_unusable_in_text_date_never_becomes_an_arrival_time() -> None:
    facts = _facts("future_date_in_text")
    evidence = facts["time.evidence"]
    manifest = facts["time.owner_manifest"][0]
    for policy_id in ("header_date_claimed", "received_chain_header_order", "owner_manifest"):
        order_ids, not_placed = timeline_ref.order(policy_id, evidence, manifest)
        assert "e_mentioned" not in order_ids, f"{policy_id} promoted an in-text date to arrival"
    _, not_placed = timeline_ref.order("header_date_claimed", evidence, manifest)
    assert not_placed == ["e_mentioned"]


def test_no_policy_is_implicit_an_empty_policy_list_is_an_error() -> None:
    facts = _facts("date_before_hops")
    with pytest.raises(ValueError, match="no order exists by omission"):
        timeline_ref.evaluate(facts["time.evidence"], [], facts["time.owner_manifest"][0])
    with pytest.raises(ValueError, match="unknown policy"):
        timeline_ref.order("the_right_order", facts["time.evidence"], [])


def test_an_owner_manifest_that_names_an_unknown_event_is_refused() -> None:
    facts = _facts("date_before_hops")
    with pytest.raises(ValueError, match="distinct known events"):
        timeline_ref.order("owner_manifest", facts["time.evidence"], ["e_nobody"])
