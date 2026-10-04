"""Turn 1.0c, Family A: the headers/date/address fixtures' hand-typed labels.

This is the family's own check (the Phase 0 structure test is not extended for the new
fact shapes). It proves, without importing the walker:

* every Family A sidecar loads through the independent loader (`emailextract.evals.labels`,
  which imports nothing from the package) and is pinned in the label ledger;
* every fact id a Family A sidecar names is declared in the oracle's `FACTS` at the phase
  the label claims;
* every typed span slices the fixture's raw bytes to the text the label claims -- a
  byte-level check that does not parse anything;
* every gap id is a known one (a walker `GAP_*` constant or a design-registry id);
* the facts the family's catalogue rows name are carried by the sidecars that name them,
  at least one of them non-trivially.

The span and coverage checks are each proved able to fail on a planted wrong span and a
dropped fact, in a temporary copy of the corpus.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402

from emailextract.evals.l1 import FACTS  # noqa: E402
from emailextract.evals.labels import Sidecar, load_sidecars, sidecar_paths  # noqa: E402

FIXTURES = ROOT / "fixtures"
LEDGER = ROOT / "tests" / "ledger" / "label_ledger.json"
DESIGN = ROOT / "docs" / "design" / "email-extraction-design.md"

#: The thirty Family A catalogue rows (docs/design/phase1-fixtures.md, "Family A").
FAMILY_A = frozenset(
    {
        "headers_plain_baseline",
        "duplicate_header_mime_version",
        "duplicate_content_type_header",
        "mime_version_missing",
        "leading_utf8_bom",
        "mbox_from_line_at_zero",
        "lone_cr_in_header_region",
        "header_line_over_998_bytes",
        "nul_in_header_value",
        "nul_in_header_name",
        "header_8bit_raw_bytes",
        "mixed_case_header_and_param_names",
        "encoded_word_valid",
        "encoded_word_invalid",
        "encoded_word_mixed_charsets",
        "encoded_word_split_across_fold",
        "rfc2231_segment0_charset",
        "rfc2231_continuations",
        "rfc2231_empty_charset_fallback",
        "date_stated_zone",
        "date_minus_zero",
        "date_absent",
        "date_invalid",
        "date_offset_out_of_range",
        "address_group",
        "address_undisclosed_recipients",
        "address_unparsable",
        "address_quoted_comma_display_name",
        "address_idn_domain",
        "address_smtputf8_local_part",
    }
)

#: The gap ids the skeleton walker emits today (walk.GAP_*), which ride in `part.gaps`.
WALKER_GAPS = frozenset(
    {
        "headers.malformed_line",
        "body.headers_only",
        "body.no_boundary_found",
        "body.boundary_disagreement",
        "body.preamble_bytes",
        "body.epilogue_bytes",
        "body.decode_fallback_used",
        "body.decode_destroyed_bytes",
    }
)

#: How many Family A sidecars carry each fact -- the family's own plan, read off the
#: catalogue's "Phase 1 facts / gap ids" column. The whole-corpus floors in
#: docs/design/phase1-facts.md (document.axes 80, headers.projection 60, headers.addresses
#: 20, headers.date 12, headers.decoded 8, headers.parameters 4, attach.filename 10) span
#: all three families and the quote catalogue, so a 30-fixture family cannot meet them on
#: its own; what this test fixes is that the family carries each fact where the catalogue
#: says it does, with at least one non-trivial value.
FAMILY_PLAN = {
    "document.axes": 30,
    "headers.projection": 12,
    "headers.addresses": 7,
    "headers.date": 6,
    "headers.decoded": 4,
    "headers.parameters": 4,
    "attach.filename": 1,
}

LOADER_SCRIPT = r"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("labels_standalone", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert "emailextract" not in sys.modules, "the loader imported the package"
assert "emailextract.walk" not in sys.modules, "the loader imported the walker"
sidecars = module.load_sidecars(sys.argv[2])
family = set(json.loads(sys.argv[3]))
missing = sorted(name for name in family if name not in sidecars)
print(json.dumps({"loaded": len(sidecars), "missing": missing}))
"""


def _family(sidecars: dict[str, Sidecar]) -> dict[str, Sidecar]:
    return {stem: sidecar for stem, sidecar in sidecars.items() if stem in FAMILY_A}


def _facts(sidecar: Sidecar) -> dict:
    return {fact_id: fact.value for fact_id, fact in sidecar.facts.items()}


def _registry_ids() -> set[str]:
    """The design's known-gap ids, fully qualified (`family.name`).

    The registry lists each id bare under a `- **family**:` bullet (often wrapped onto
    indented continuation lines), so the scan is line-by-line with a current family.
    """
    import re

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


def span_problems(sidecars: dict[str, Sidecar]) -> list[str]:
    """Every label span that does not slice the fixture bytes to the text it claims."""
    problems: list[str] = []
    for stem, sidecar in sidecars.items():
        raw = sidecar.artifact.read_bytes()
        facts = _facts(sidecar)
        size = facts.get("container.size_bytes")
        if size is not None and size != len(raw):
            problems.append(f"{stem}: container.size_bytes {size} != {len(raw)}")
        for raised, name, value, _status, name_span, value_span, raw_span in facts.get("headers.fields", []):
            n_off, n_len = name_span
            v_off, v_len = value_span
            r_off, r_len = raw_span
            if raw[n_off : n_off + n_len] != name.encode("latin-1"):
                problems.append(f"{stem} field {raised}: name_span does not name {name!r}")
            if raw[v_off : v_off + v_len] != value.encode("latin-1"):
                problems.append(f"{stem} field {raised}: value_span does not carry {value!r}")
            if not (r_off <= n_off and v_off + v_len <= r_off + r_len):
                problems.append(f"{stem} field {raised}: raw_span does not cover the field")
        for path, _parent, _ctype, raw_span, headers_span, body_span in facts.get("part.tree", []):
            if headers_span[0] != raw_span[0] or headers_span[0] + headers_span[1] != body_span[0]:
                problems.append(f"{stem} part {path}: headers/body do not partition the raw span")
            if body_span[0] + body_span[1] != raw_span[0] + raw_span[1]:
                problems.append(f"{stem} part {path}: the raw span does not end at the body's end")
        spans = sorted(tuple(row[2]) for row in facts.get("part.regions", []))
        position = 0
        for offset, length in spans:
            if offset != position:
                problems.append(f"{stem}: regions leave a gap or overlap at byte {position}")
                break
            position = offset + length
        if spans and position != len(raw):
            problems.append(f"{stem}: regions end at {position} of {len(raw)}")
        for raised, field_name, rows in facts.get("headers.addresses", []):
            for offset, length, display, addr, _state, _reason in rows:
                sliced = raw[offset : offset + length]
                if offset + length > len(raw):
                    problems.append(f"{stem} {field_name} {raised}: address span out of range")
                    continue
                claimed = [text for text in (display, addr) if text]
                if not claimed:
                    continue
                as_utf8 = sliced.decode("utf-8", "replace")
                as_latin = sliced.decode("latin-1")
                if not any(text in as_utf8 or text in as_latin for text in claimed):
                    problems.append(
                        f"{stem} {field_name} {raised}: the address span does not carry {claimed}"
                    )
    return problems


def coverage(sidecars: dict[str, Sidecar]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sidecar in sidecars.values():
        for fact_id in sidecar.facts:
            counts[fact_id] = counts.get(fact_id, 0) + 1
    return counts


def _load_family(root: Path) -> dict[str, Sidecar]:
    return _family(load_sidecars(root))


def test_the_headers_family_labels_load_and_are_ledgered() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    assert set(sidecars) == set(FAMILY_A), sorted(FAMILY_A - set(sidecars))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["files"]
    for stem, sidecar in sidecars.items():
        relative = sidecar.path.relative_to(ROOT).as_posix()
        assert relative in ledger, f"{stem}: {relative} is not in the label ledger"
        assert sidecar.labels_provenance == "spec", stem
    # The loader imports nothing from the package: proved in a bare interpreter.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            LOADER_SCRIPT,
            str(ROOT / "emailextract" / "evals" / "labels.py"),
            str(FIXTURES),
            json.dumps(sorted(FAMILY_A)),
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={"PATH": "", "PYTHONPATH": str(ROOT), "SYSTEMROOT": "C:\\Windows"},
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["missing"] == [], report
    assert report["loaded"] >= len(FAMILY_A), report


def test_every_family_a_fact_id_is_declared() -> None:
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        for fact_id, fact in sidecar.facts.items():
            assert fact_id in FACTS, f"{stem}: {fact_id} is not declared in FACTS"
            assert FACTS[fact_id].phase == fact.phase, (
                f"{stem}: {fact_id} is labelled phase {fact.phase} and declared phase {FACTS[fact_id].phase}"
            )


def test_every_typed_span_slices_the_fixture_bytes() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    assert span_problems(sidecars) == []
    checked = sum(1 for sidecar in sidecars.values() if "headers.fields" in sidecar.facts)
    assert checked >= 20, "the span check would be vacuous"


def test_every_family_a_gap_id_is_a_known_id() -> None:
    registry = _registry_ids()
    seen_gaps = 0
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        facts = _facts(sidecar)
        for path, gap_ids in facts.get("part.gaps", []):
            for gap_id in gap_ids:
                assert gap_id in WALKER_GAPS, f"{stem} part {path}: {gap_id} is not a walker gap"
                seen_gaps += 1
        for gap_id, locator, phase, reason in facts.get("gaps.later", []):
            assert gap_id in registry, f"{stem}: gaps.later names {gap_id!r}, not a registry id"
            assert isinstance(locator, str) and locator
            assert isinstance(phase, int) and phase >= 1
            assert isinstance(reason, str) and reason
    assert seen_gaps >= 1, "no Family A fixture carries a walker gap"


def test_the_family_meets_the_facts_the_catalogue_names() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    carried = coverage(sidecars)
    for fact_id, minimum in FAMILY_PLAN.items():
        assert carried.get(fact_id, 0) >= minimum, (
            f"{fact_id} is carried by {carried.get(fact_id, 0)} sidecar(s), the catalogue plan is {minimum}"
        )
    assert carried.get("document.axes", 0) == len(FAMILY_A)
    for fact_id in FAMILY_PLAN:
        values = [
            sidecar.facts[fact_id].value for sidecar in sidecars.values() if fact_id in sidecar.facts
        ]
        assert any(value for value in values), f"{fact_id} has only empty values"


def test_the_new_fact_shapes_are_well_formed() -> None:
    """The Family A facts carry the closed vocabularies the FACTS table declares."""
    axis_ids = {
        "attachment.status",
        "attachment.route",
        "document.times",
        "document.thread_edges",
        "document.children",
        "document.same_message_candidates",
    }
    projection_kinds = {"text", "address_list", "date_time", "message_id", "message_id_list", "unparsed"}
    zone_states = {"zone_stated", "zone_stated_minus_zero", "zone_absent"}
    address_states = {"parsed", "group", "unparsed"}
    parameter_states = {"decoded", "fallback", "undecodable"}
    filename_states = {"decoded", "fallback", "absent", "unparsable"}
    fallback_reasons = {
        "encoded_word_in_parameter",
        "empty_charset",
        "missing_continuation_index",
        "duplicate_continuation_index",
    }
    seen = set()
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        facts = _facts(sidecar)
        for axis_id, state, reason in facts.get("document.axes", []):
            seen.add("document.axes")
            assert axis_id in axis_ids, f"{stem}: axis {axis_id!r} is not a closed axis id"
            assert state in {"value", "absent", "unknown"}, f"{stem}: axis state {state!r}"
            assert (reason is None) is (state != "unknown"), f"{stem}: axis {axis_id} reason/state"
            if state == "unknown":
                assert reason == "not_built_in_phase1", f"{stem}: {axis_id} reason {reason!r}"
        for row in facts.get("headers.projection", []):
            seen.add("headers.projection")
            ordinal, name, raw_value, kind, parsed = row
            assert isinstance(ordinal, int) and isinstance(name, str) and isinstance(raw_value, str)
            assert kind in projection_kinds, f"{stem}: parsed_kind {kind!r}"
            assert (parsed is None) == (kind == "unparsed"), f"{stem}: parsed_value for {kind!r}"
        for ordinal, field_name, rows in facts.get("headers.addresses", []):
            seen.add("headers.addresses")
            assert isinstance(ordinal, int) and isinstance(field_name, str)
            for offset, length, display, addr, state, reason in rows:
                assert state in address_states, f"{stem} {field_name}: address state {state!r}"
                assert (reason is None) or state == "unparsed", f"{stem}: reason outside unparsed"
                if state == "unparsed":
                    assert reason == "headers.address_unparsable", f"{stem}: reason {reason!r}"
                assert offset >= 0 and length >= 0
        for ordinal, raw, zone_state, offset, utc in facts.get("headers.date", []):
            seen.add("headers.date")
            assert zone_state in zone_states, f"{stem}: zone_state {zone_state!r}"
            assert (offset is None) or re.match(r"^[+-]\d{4}$", offset), f"{stem}: offset {offset!r}"
            assert isinstance(utc, str) or (utc[0] == "unknown" and isinstance(utc[1], str)), (
                f"{stem}: utc {utc!r}"
            )
        for ordinal, decoded in facts.get("headers.decoded", []):
            seen.add("headers.decoded")
            assert isinstance(ordinal, int) and isinstance(decoded, str)
        for ordinal, field_name, parameter, value, state, reason in facts.get("headers.parameters", []):
            seen.add("headers.parameters")
            assert state in parameter_states, f"{stem}: decode_state {state!r}"
            assert (reason is None) or (state == "fallback" and reason in fallback_reasons), (
                f"{stem}: fallback_reason {reason!r}"
            )
        for part, filename_raw, state, decoded, reason in facts.get("attach.filename", []):
            seen.add("attach.filename")
            assert state in filename_states, f"{stem}: filename decode_state {state!r}"
            assert (reason is None) or (state == "fallback" and reason in fallback_reasons), (
                f"{stem}: filename fallback_reason {reason!r}"
            )
    assert seen == {
        "document.axes",
        "headers.projection",
        "headers.addresses",
        "headers.date",
        "headers.decoded",
        "headers.parameters",
        "attach.filename",
    }, f"the shape check would be vacuous: {sorted(seen)}"


def test_the_span_check_fails_on_a_planted_wrong_span(tmp_path: Path) -> None:
    source = FIXTURES / "generated" / "headers_plain_baseline"
    payload = sidecar_copy.payload_of(Path(f"{source}.expected.json"))
    payload["facts"]["headers.fields"]["value"][0][4] = [
        payload["facts"]["headers.fields"]["value"][0][4][0] + 1,
        payload["facts"]["headers.fields"]["value"][0][4][1],
    ]
    sidecar_copy.write(tmp_path, payload, source=Path(f"{source}.expected.json"))
    problems = span_problems(_load_family(tmp_path))
    assert any("name_span" in problem for problem in problems), problems


def test_the_coverage_check_fails_on_a_missing_fact(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "fixtures")
    target = tmp_path / "fixtures" / "generated" / "date_stated_zone.expected.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["facts"].pop("document.axes")
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    problems = span_problems(_load_family(tmp_path / "fixtures"))
    carried = coverage(_load_family(tmp_path / "fixtures"))
    assert problems == []
    assert carried.get("document.axes", 0) < len(FAMILY_A)
