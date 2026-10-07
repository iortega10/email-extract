"""Turn 1.1: the independent stdlib header scanner -- the catalogue and the gate.

``tests/support/stdlib_scanner.py`` is a checker that imports nothing from ``emailextract``.
This test drives its comparisons over every fixture and holds the package to them:

1. **field names and order** match the stdlib's compot32 ``raw_items()`` view over every
   fixture that is not in the exclusion catalogue; and
2. every disagreement is confined to the catalogue, each entry carrying a **closed** reason
   id -- the cases where the stdlib shares the misreading (a gate would prove nothing) or is
   simply less permissive than the design (fail-open). A **planted defect** in the package
   (a reordered field, a dropped duplicate) makes the matching comparison fail, so the gate
   is not vacuous.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import stdlib_scanner  # noqa: E402

from emailextract import headers as header_stage  # noqa: E402
from emailextract.container import EmlContainer  # noqa: E402
from emailextract.walk import walk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

#: The **closed** reason ids a catalogue entry may carry.
EXCLUSION_REASONS = {
    "leading_bom": "the stdlib reads the BOM and the first header line as one defect",
    "mbox_from_line": "the stdlib reads the mbox `From ` line as a malformed header",
    "lone_cr_line_break": "the stdlib feedparser splits on a lone CR exactly as the walker does",
    "invalid_encoded_word": "the stdlib decodes an invalid encoded word silently, with defects = []",
    "defects_vs_bytes": "stdlib `defects` and the returned bytes disagree (email-spike b02)",
    "fail_open": "the package fails open past a malformed line (D2); the stdlib stops there",
    "no_recursion": "the package does not recurse into message/rfc822 (Phase 2); the stdlib does",
    "digest_default": "the package records Content-Type None for a digest child; the stdlib applies RFC 2046 5.1.5",
}

#: fixture stem -> closed reason why the **field name/order** comparison is not gated there.
FIELD_EXCLUSIONS = {
    "leading_utf8_bom": "leading_bom",
    "mbox_from_line_at_zero": "mbox_from_line",
    "lone_cr_in_header_region": "lone_cr_line_break",
    "malformed_mime": "fail_open",
    "nul_in_header_name": "fail_open",
}

#: fixture stem -> closed reason why the **content-type tree** comparison is not gated there.
CONTENT_TYPE_EXCLUSIONS = {
    "attach_message_rfc822_no_filename": "no_recursion",
    "text_part_with_body_parts_tree": "no_recursion",
    "multipart_digest_content_type_less_child": "digest_default",
    "headerless_digest_child": "digest_default",
    "malformed_mime": "fail_open",
}


def _fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*/*.eml"))


def _package_field_names(raw: bytes) -> list[str]:
    result = walk(EmlContainer(raw))
    region = header_stage.header_region(raw, result, max_work_units=64)
    return [item.name.lower() for item in region.fields]


def _field_disagreements() -> dict[str, tuple[list[str], list[str]]]:
    found: dict[str, tuple[list[str], list[str]]] = {}
    for path in _fixtures():
        raw = path.read_bytes()
        package = _package_field_names(raw)
        stdlib = [name.lower() for name in stdlib_scanner.scan(raw).field_names]
        if package != stdlib:
            found[path.stem] = (package, stdlib)
    return found


def _content_type_disagreements() -> dict[str, tuple[list[str], list[str]]]:
    found: dict[str, tuple[list[str], list[str]]] = {}
    for path in _fixtures():
        raw = path.read_bytes()
        package = [(part.content_type or "text/plain") for part in walk(EmlContainer(raw)).parts]
        stdlib = list(stdlib_scanner.scan(raw).content_types)
        if package != stdlib:
            found[path.stem] = (package, stdlib)
    return found


def _decoded_disagreements() -> dict[str, tuple[str, str, str]]:
    """``stem -> (field, package, stdlib)`` where a package-decoded value differs from the stdlib."""
    found: dict[str, tuple[str, str, str]] = {}
    for path in _fixtures():
        raw = path.read_bytes()
        region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=64)
        package = {
            item.name.lower(): region.text_decodes[item.ordinal].text.strip()
            for item in region.fields
            if item.ordinal in region.text_decodes and region.text_decodes[item.ordinal].decoded
        }
        for name, value in stdlib_scanner.scan(raw).decoded:
            lowered = name.lower()
            if lowered in package and package[lowered] != value.strip():
                found[path.stem] = (lowered, package[lowered], value.strip())
    return found


def test_field_names_and_order_match_the_stdlib_raw_view() -> None:
    """Over every non-excluded fixture, the package's field names and order match the stdlib."""
    disagreements = _field_disagreements()
    unexpected = {stem: value for stem, value in disagreements.items() if stem not in FIELD_EXCLUSIONS}
    assert unexpected == {}, f"field-order disagreements outside the catalogue: {unexpected}"
    compared = sum(1 for path in _fixtures() if path.stem not in FIELD_EXCLUSIONS)
    assert compared >= 80, "the comparison would be vacuous"


def test_the_scanner_disagrees_only_where_the_stdlib_shares_the_misreading(
    monkeypatch,
) -> None:
    """Every disagreement is catalogued with a closed reason, and a planted defect is caught."""
    disagreements = _field_disagreements()
    assert set(disagreements) <= set(FIELD_EXCLUSIONS), sorted(disagreements)
    for reason in (*FIELD_EXCLUSIONS.values(), *CONTENT_TYPE_EXCLUSIONS.values()):
        assert reason in EXCLUSION_REASONS, reason
    # The excluded fixtures really do disagree (the catalogue is not decoration).
    assert disagreements, "no disagreement at all: the exclusion list is stale"
    # The content-type tree and the decoded values are catalogued too.
    ct = _content_type_disagreements()
    assert set(ct) <= set(CONTENT_TYPE_EXCLUSIONS), sorted(ct)
    assert _decoded_disagreements() == {}, _decoded_disagreements()

    # A **planted defect**: a package that reorders the fields must fail the comparison.
    real = header_stage.header_fields_at
    seen = {"patched": 0}

    def reordered(raw, start, end):
        fields, gaps = real(raw, start, end)
        seen["patched"] += 1
        return list(reversed(fields)), gaps

    monkeypatch.setattr(header_stage, "header_fields_at", reordered)
    planted = _field_disagreements()
    assert seen["patched"] > 0, "the planted defect was never reached (vacuous)"
    assert "duplicate_header_mime_version" in planted, planted
    assert set(planted) - set(disagreements), "the reorder must create a new disagreement"
    monkeypatch.setattr(header_stage, "header_fields_at", real)
    assert set(_field_disagreements()) == set(disagreements), "restoring must restore agreement"
