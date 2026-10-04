"""TEST-ONLY reference evaluator of the named ordering policies (build spec, Turn 0.3).

This module exists so the **hand-typed** expected artifacts under ``fixtures/time/``
can be checked against an independent computation: it reads an evidence list (rows
in :mod:`emailextract.timeevent`'s shape) and computes the order under each named
policy plus the unresolved conflict pairs beside them. It is **not shipped**, it is
not the timeline layer, and nothing in ``emailextract`` imports it (D15: the
read-only merge/query layer is ``docextract-timeline``, a later package, after
Phase 3 and after a second producer exists).

The semantics it freezes -- stated here because the design names the policies but
not their mechanics:

* ``header_date_claimed`` -- orders the events that are **usable for arrival
  ordering and carry a known ``when_utc``** by their claimed UTC (ties by event
  id). Everything else is reported ``not_placed``: it is never repaired into a
  time and never sorted as epoch (D2).
* ``received_chain_header_order`` -- orders the ``received_hop`` events by header
  position alone, **bottom-up**: the last-listed ``Received`` is the first hop,
  so the chain sequence is fixed by the headers and timestamps never reorder it
  (D15: clock skew). Non-hop events are ``not_placed``.
* ``owner_manifest`` -- returns the caller's labelled total-order override
  verbatim and reports the events it does not cover as ``not_placed``. It is an
  override, not evidence ranking (D15: ``owner_manifest`` is labelled distinctly).
* **unresolved conflict pairs** -- every pair of evidence claims that disagrees or
  cannot be compared, whichever policies ran (D15: evidence is never merged into
  one ``true`` time): claims whose ``when_utc`` values are equal agree (no pair);
  any claim with an unknown ``when_utc`` is unplaceable against any other (pair);
  two hops conflict exactly when their claimed times order them opposite to their
  header positions (clock skew); any other pair with different claimed moments
  conflicts (two source families, nothing reconciles them).

No policy is implicit: every call names the policies it wants (D15: no default).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

POLICIES: tuple[str, ...] = (
    "header_date_claimed",
    "received_chain_header_order",
    "owner_manifest",
)


def _when_utc(event: Mapping[str, Any]) -> str | None:
    value = event["when_utc"]
    return value.get("value") if isinstance(value, Mapping) else getattr(value, "value", None)


def _usable(event: Mapping[str, Any]) -> bool:
    return bool(event["usable_for_arrival_ordering"])


def _ordinal(event: Mapping[str, Any]) -> int:
    source = event["source"]
    return int(source["ordinal"] if isinstance(source, Mapping) else source.ordinal)


def order(
    policy_id: str,
    evidence: Sequence[Mapping[str, Any]],
    owner_manifest: Sequence[str] = (),
) -> tuple[list[str], list[str]]:
    """``(order, not_placed)`` under one named policy; every policy is named."""
    if policy_id not in POLICIES:
        raise ValueError(f"unknown policy {policy_id!r}; name one of {list(POLICIES)}")
    ids = [event["event_id"] for event in evidence]

    if policy_id == "header_date_claimed":
        placed = [event for event in evidence if _usable(event) and _when_utc(event) is not None]
        placed.sort(key=lambda event: (_when_utc(event), event["event_id"]))
        order_ids = [event["event_id"] for event in placed]
    elif policy_id == "received_chain_header_order":
        hops = [
            event
            for event in evidence
            if event["kind"] == "received_hop" and _usable(event) and _when_utc(event) is not None
        ]
        hops.sort(key=lambda event: (-_ordinal(event), event["event_id"]))
        order_ids = [event["event_id"] for event in hops]
    else:
        order_ids = list(owner_manifest)
        if sorted(order_ids) != sorted(set(order_ids)) or not set(order_ids) <= set(ids):
            raise ValueError(f"owner_manifest must name distinct known events, got {order_ids}")

    not_placed = sorted(set(ids) - set(order_ids))
    return order_ids, not_placed


def conflict_pairs(evidence: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """Every pair of claims that disagrees or cannot be compared (see the module docstring)."""
    pairs: list[tuple[str, str]] = []
    for index, left in enumerate(evidence):
        for right in evidence[index + 1 :]:
            a, b = sorted((left["event_id"], right["event_id"]))
            left_time, right_time = _when_utc(left), _when_utc(right)
            if left_time is None or right_time is None:
                pairs.append((a, b))
                continue
            if left_time == right_time:
                continue
            if left["kind"] == right["kind"] == "received_hop":
                chain_a, chain_b = sorted((left, right), key=lambda event: -_ordinal(event))
                time_a, time_b = sorted((left, right), key=lambda event: _when_utc(event))
                if chain_a["event_id"] != time_a["event_id"]:
                    pairs.append((a, b))
                continue
            pairs.append((a, b))
    return pairs


def evaluate(
    evidence: Sequence[Mapping[str, Any]],
    policies: Iterable[str],
    owner_manifest: Sequence[str] = (),
) -> dict[str, Any]:
    """Every named policy's order plus the conflict pairs returned beside them."""
    named = list(policies)
    if not named:
        raise ValueError("no policy named: no order exists by omission (D15)")
    orders = {policy_id: order(policy_id, evidence, owner_manifest) for policy_id in named}
    return {"orders": orders, "conflict_pairs": conflict_pairs(evidence)}
