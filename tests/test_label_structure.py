"""Turn 0.3: the labels' own structure (model: workbook-extract tests/test_label_structure.py).

A mislabelled span or an invented gap id would make every later green run meaningless, so
the structure is verified here -- from the sidecar JSON and from the fixture bytes the
labels cite (reading the bytes a label points at is not reading the parser):

* every span is non-negative, in range, and the bytes under a header field's name and
  value spans are exactly what the row says they are (the label agrees with its own
  fixture);
* the region rows tile the message exactly, with no gap and no overlap (D9);
* the part tree's headers and body spans partition its raw span;
* every gap id is in the design document's known-gap registry **or** one of the walker's
  GAP constants (and the report names any id the two sources disagree about);
* every ``labels.undetermined`` entry names a fact or gap id, a locator and a
  full-sentence reason;
* the time artifacts' evidence rows are real ``TimeEvent`` shapes and their orders are
  consistent permutations of the evidence.

Nothing here compares a label with the walker's output: labels are never edited to match
output, and the comparison is the Turn 0.4 oracle's job.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from emailextract.evals.l1 import FACT_PHASES
from emailextract.evals.labels import load_sidecars
from emailextract.model import EncodingSource
from emailextract.timeevent import TimeEvent
from emailextract.walk import (
    GAP_BODY_BOUNDARY_DISAGREEMENT,
    GAP_BODY_DECODE_DESTROYED_BYTES,
    GAP_BODY_DECODE_FALLBACK_USED,
    GAP_BODY_EPILOGUE_BYTES,
    GAP_BODY_HEADERS_ONLY,
    GAP_BODY_NO_BOUNDARY_FOUND,
    GAP_BODY_PREAMBLE_BYTES,
    GAP_HEADERS_MALFORMED_LINE,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DESIGN = ROOT / "docs" / "design" / "email-extraction-design.md"

WALKER_GAPS = {
    GAP_HEADERS_MALFORMED_LINE,
    GAP_BODY_HEADERS_ONLY,
    GAP_BODY_NO_BOUNDARY_FOUND,
    GAP_BODY_BOUNDARY_DISAGREEMENT,
    GAP_BODY_PREAMBLE_BYTES,
    GAP_BODY_EPILOGUE_BYTES,
    GAP_BODY_DECODE_FALLBACK_USED,
    GAP_BODY_DECODE_DESTROYED_BYTES,
}

SIDECARS = load_sidecars(FIXTURES)
IDS = sorted(SIDECARS)
TIME_IDS = [stem for stem in IDS if SIDECARS[stem].path.parent.name == "time"]
MESSAGE_IDS = [stem for stem in IDS if stem not in TIME_IDS]


def _registry_ids() -> set[str]:
    """``family.name`` ids from the design's registry section.

    A family bullet names its ids bare and often wraps them onto indented
    continuation lines (``- **headers**: ...`` then two wrapped lines), so the
    scan is line-by-line with a current family: a ``- **family**`` bullet opens
    one, indented lines belong to it, any other line closes it.
    """
    text = DESIGN.read_text(encoding="utf-8")
    start = text.index("## Known-gap ids")
    end = text.index("\n## ", start + 1)
    ids: set[str] = set()
    family: str | None = None
    for line in text[start:end].splitlines():
        bullet = re.match(r"- \*\*([a-z_]+)\*\*[^:]*:(.*)$", line)
        if bullet:
            family = bullet.group(1)
            ids.update(f"{family}.{name}" for name in re.findall(r"`([a-z][a-z0-9_]*)`", bullet.group(2)))
        elif line[:2] == "  " and family is not None:
            ids.update(f"{family}.{name}" for name in re.findall(r"`([a-z][a-z0-9_]*)`", line))
        elif line.strip():
            family = None
    return ids


def _facts(stem: str) -> dict:
    return {fact_id: fact.value for fact_id, fact in SIDECARS[stem].facts.items()}


def _raw(stem: str) -> bytes:
    return SIDECARS[stem].artifact.read_bytes()


def _span(row) -> tuple[int, int]:
    offset, length = row
    assert isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0
    assert isinstance(length, int) and not isinstance(length, bool) and length >= 0
    return offset, length


def test_the_registry_the_gap_ids_are_checked_against_is_not_empty() -> None:
    ids = _registry_ids()
    assert len(ids) > 20, "the known-gap registry could not be read from the design document"
    assert WALKER_GAPS <= ids | WALKER_GAPS
    missing = WALKER_GAPS - ids
    assert not missing, f"walker gap constants absent from the design registry: {missing}"


@pytest.mark.parametrize("stem", IDS)
def test_every_span_is_non_negative_and_in_range(stem: str) -> None:
    facts = _facts(stem)
    size = facts["container.size_bytes"]
    for row in facts.get("part.regions", []):
        offset, length = _span(row[2])
        assert offset + length <= size
    for row in facts.get("part.tree", []):
        for span in row[3:6]:
            offset, length = _span(span)
            assert offset + length <= size
    for row in facts.get("headers.fields", []):
        for span in row[4:7]:
            offset, length = _span(span)
            assert offset + length <= size


@pytest.mark.parametrize("stem", MESSAGE_IDS)
def test_a_header_field_span_points_at_the_bytes_it_names(stem: str) -> None:
    raw = _raw(stem)
    # A Turn 1.0c fixture whose phase-0 header spans are deliberately left untyped (the
    # walker's reading of it is about to change) names no headers.fields fact.
    for ordinal, name, value, parse_status, name_span, value_span, raw_span in _facts(stem).get(
        "headers.fields", []
    ):
        name_offset, name_length = _span(name_span)
        value_offset, value_length = _span(value_span)
        raw_offset, raw_length = _span(raw_span)
        assert raw[name_offset : name_offset + name_length] == name.encode("latin-1"), (
            f"{stem} field {ordinal}: name_span does not name {name!r}"
        )
        assert raw[value_offset : value_offset + value_length] == value.encode("latin-1"), (
            f"{stem} field {ordinal}: value_span does not carry {value!r}"
        )
        assert raw_offset <= name_offset < value_offset + value_length <= raw_offset + raw_length
        assert parse_status in ("ok", "unknown")
        if parse_status == "ok":
            assert raw[raw_offset : raw_offset + len(name) + 1] == name.encode("latin-1") + b":"


@pytest.mark.parametrize("stem", IDS)
def test_the_region_rows_tile_the_message_exactly(stem: str) -> None:
    facts = _facts(stem)
    if "part.regions" not in facts:
        return
    size = facts["container.size_bytes"]
    spans = sorted((_span(row[2]) for row in facts["part.regions"]), key=lambda item: item[0])
    position = 0
    for offset, length in spans:
        assert offset == position, f"{stem}: gap or overlap at byte {position}"
        position = offset + length
    assert position == size, f"{stem}: regions end at {position} of {size}"


@pytest.mark.parametrize("stem", IDS)
def test_a_part_tree_row_partitions_its_raw_span(stem: str) -> None:
    facts = _facts(stem)
    if "part.tree" not in facts:
        return
    seen = set()
    for path, parent, _content_type, raw_span, headers_span, body_span in facts["part.tree"]:
        assert path not in seen, f"{stem}: part {path} declared twice"
        seen.add(path)
        raw_offset, raw_length = _span(raw_span)
        headers_offset, headers_length = _span(headers_span)
        body_offset, body_length = _span(body_span)
        assert headers_offset == raw_offset
        assert headers_offset + headers_length == body_offset
        assert body_offset + body_length == raw_offset + raw_length
        if parent is not None:
            assert parent in seen or parent == "1", f"{stem}: part {path} has unknown parent {parent}"


@pytest.mark.parametrize("stem", IDS)
def test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants(stem: str) -> None:
    registry = _registry_ids()
    facts = _facts(stem)
    for path, gap_ids in facts.get("part.gaps", []):
        for gap_id in gap_ids:
            assert gap_id in registry or gap_id in WALKER_GAPS, (
                f"{stem} part {path}: invented gap id {gap_id!r}"
            )
    for gap_id, locator, phase, note in facts.get("gaps.later", []):
        assert gap_id in registry, f"{stem}: gaps.later names {gap_id!r}, not in the registry"
        assert isinstance(locator, str) and locator
        assert isinstance(phase, int) and phase >= 1
        assert isinstance(note, str) and note
    assert facts.get("part.gaps") or "gaps.later" in facts or stem in TIME_IDS, (
        f"{stem}: no gap expectation at all is stated -- silence is not agreement"
    )


@pytest.mark.parametrize("stem", IDS)
def test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason(stem: str) -> None:
    registry = _registry_ids()
    facts = _facts(stem)
    entries = facts.get("labels.undetermined", [])
    for fact_id, locator, reason in entries:
        assert re.match(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", fact_id), fact_id
        # A declared fact id is allowed even when this sidecar types no value for it: that is
        # exactly what "undetermined" says (Turn 1.0c family B: the quote facts of the
        # interleaved-reply fixture wait for the owner-reviewed quote catalogue).
        assert (
            fact_id in registry or fact_id in facts or fact_id in WALKER_GAPS or fact_id in FACT_PHASES
        ), f"{stem}: undetermined names {fact_id!r}, which is neither a declared fact nor a gap"
        assert isinstance(locator, str) and locator, f"{stem}: {fact_id} has no locator"
        assert isinstance(reason, str) and len(reason) > 20, (
            f"{stem}: {fact_id} is undetermined without saying why"
        )


@pytest.mark.parametrize("stem", IDS)
def test_a_decode_chain_row_carries_the_closed_vocabularies(stem: str) -> None:
    for row in _facts(stem).get("decode.chain", []):
        path, declared_cte, declared_charset, used_cte, used_charset, fallback_fired, source = row
        assert isinstance(path, str) and path
        assert declared_cte is None or isinstance(declared_cte, str)
        assert used_cte is None or isinstance(used_cte, str)
        assert declared_charset is None or isinstance(declared_charset, str)
        assert used_charset is None or isinstance(used_charset, str)
        assert isinstance(fallback_fired, bool)
        if source is not None:
            assert source in {member.value for member in EncodingSource}, source


@pytest.mark.parametrize("stem", TIME_IDS)
def test_a_time_evidence_row_is_a_real_timeevent(stem: str) -> None:
    doc_id = _facts(stem)["container.sha256"]
    for row in _facts(stem)["time.evidence"]:
        assert set(row) == {
            "event_id",
            "doc_id",
            "parent_event_id",
            "kind",
            "when_raw",
            "when_utc",
            "offset",
            "offset_origin",
            "precision",
            "ambiguity",
            "source",
            "trust",
            "usable_for_arrival_ordering",
        }, f"{stem}: a TimeEvent row carries exactly timeevent.py's fields"
        assert row["doc_id"] == doc_id, f"{stem}: {row['event_id']} is about another document"
        event = TimeEvent(
            event_id=row["event_id"],
            doc_id=row["doc_id"],
            parent_event_id=row["parent_event_id"],
            kind=row["kind"],
            when_raw=row["when_raw"],
            when_utc=_time_value(row["when_utc"]),
            offset=_time_value(row["offset"]),
            offset_origin=_enum("OffsetOrigin", row["offset_origin"]),
            precision=_enum("Precision", row["precision"]),
            ambiguity=_enum("Ambiguity", row["ambiguity"]),
            source=_source(row["source"]),
            trust=_enum("Trust", row["trust"]),
            usable_for_arrival_ordering=row["usable_for_arrival_ordering"],
        )
        assert event.kind in {
            "sent",
            "received_hop",
            "authored",
            "modified",
            "revision",
            "comment",
            "calendar_start",
            "calendar_end",
            "calendar_stamp",
            "mentioned_in_text",
            "fs_mtime",
        }


def _time_value(raw):
    from emailextract.timeevent import TimeValue

    assert set(raw) in ({"value"}, {"unknown_reason"}), raw
    return TimeValue(value=raw.get("value"), unknown_reason=raw.get("unknown_reason"))


def _enum(name: str, value: str):
    import emailextract.timeevent as module

    members = getattr(module, name)
    return members(value)


def _source(raw):
    from emailextract.timeevent import Span, TimeSource

    named = [key for key in ("field", "property", "part") if raw.get(key) is not None]
    assert len(named) == 1, raw
    span = raw.get("span")
    return TimeSource(
        ordinal=raw["ordinal"],
        field=raw.get("field"),
        property=raw.get("property"),
        part=raw.get("part"),
        span=Span(start=span[0], end=span[1]) if span else None,
    )


@pytest.mark.parametrize("stem", TIME_IDS)
def test_the_orders_are_consistent_permutations_of_the_evidence(stem: str) -> None:
    facts = _facts(stem)
    evidence_ids = sorted(row["event_id"] for row in facts["time.evidence"])
    manifests = facts["time.owner_manifest"]
    assert len(manifests) == 1
    assert sorted(manifests[0]) == sorted(set(manifests[0])) <= evidence_ids
    for policy_id, order_ids, not_placed in facts["time.orders"]:
        assert policy_id in (
            "header_date_claimed",
            "received_chain_header_order",
            "owner_manifest",
        )
        assert sorted(order_ids) == sorted(set(order_ids))
        assert sorted(not_placed) == sorted(set(not_placed))
        assert not set(order_ids) & set(not_placed)
        assert sorted(order_ids + not_placed) == evidence_ids, f"{stem}: {policy_id} loses an event"


@pytest.mark.parametrize("stem", TIME_IDS)
def test_the_unresolved_pairs_are_well_formed_and_match_the_conflict_flag(stem: str) -> None:
    facts = _facts(stem)
    evidence_ids = {row["event_id"] for row in facts["time.evidence"]}
    pairs = facts["time.unresolved_pairs"]
    for left, right, reason in pairs:
        assert left < right and left in evidence_ids and right in evidence_ids, (left, right)
        assert isinstance(reason, str) and len(reason) > 20, "a conflict pair says why"
    assert bool(pairs) is facts["time.evidence_conflicts"], (
        f"{stem}: pairs and the evidence_conflicts flag disagree"
    )
