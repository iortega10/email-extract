"""Turn 1.0c, Family B: the body/HTML fixtures' hand-typed labels.

This is the family's own check (the Phase 0 structure test is not extended for the new
fact shapes). It proves, without importing the walker:

* every Family B sidecar loads through the independent loader (`emailextract.evals.labels`,
  which imports nothing from the package) and is pinned in the label ledger;
* every fact id a Family B sidecar names is declared in the oracle's `FACTS` at the phase
  the label claims;
* every typed span slices the fixture's raw bytes to the text the label claims -- a
  byte-level check that does not parse anything (the header field spans, the region tiling,
  the part tree partition, every `exact` body.text row, every html tag, every cid and every
  boundary parameter);
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

#: The twenty-two Family B catalogue rows (docs/design/phase1-fixtures.md, "Family B").
FAMILY_B = frozenset(
    {
        "body_plain_multipart_baseline",
        "plain_effectively_empty",
        "nested_alternative_in_related_in_mixed",
        "content_location_in_related",
        "text_calendar_alternative",
        "html_style_and_script",
        "html_href_img_remote_and_cid",
        "html_data_uri_and_tracking_pixel",
        "base64_with_whitespace_and_bad_padding",
        "qp_raw_8bit",
        "iso_2022_jp_stateful",
        "gb2312_declared_gbk_bytes",
        "windows_1252_declared_iso_8859_1",
        "boundary_with_tspecials",
        "multipart_with_cte",
        "multipart_signed",
        "multipart_digest_content_type_less_child",
        "flowed_unstuffed_soft_break",
        "preamble_only_message",
        "body_no_text_part",
        "inline_interleaved_reply_body",
        "text_part_with_body_parts_tree",
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

#: How many Family B sidecars carry each fact -- the family's own plan, read off the
#: catalogue's "Phase 1 facts / gap ids" column. The whole-corpus floors in
#: docs/design/phase1-facts.md span all three families and the quote catalogue, so a
#: 22-fixture family cannot meet them on its own; what this test fixes is that the family
#: carries each fact where the catalogue says it does, with at least one non-trivial value.
FAMILY_PLAN = {
    "document.axes": 22,
    "part.tree": 22,
    "decode.chain": 22,
    "body.text": 7,
    "body.alternative_group": 3,
    "body.selection": 3,
    "body.html_spans": 4,
    "body.cid_refs": 1,
    "body.plain_effectively_empty": 1,
    "headers.parameters": 1,
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
    return {stem: sidecar for stem, sidecar in sidecars.items() if stem in FAMILY_B}


def _facts(sidecar: Sidecar) -> dict:
    return {fact_id: fact.value for fact_id, fact in sidecar.facts.items()}


def _registry_ids() -> set[str]:
    """The design's known-gap ids, fully qualified (`family.name`).

    The registry lists each id bare under a `- **family**:` bullet (often wrapped onto
    indented continuation lines), so the scan is line-by-line with a current family.
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


def _unstuff(sliced: bytes) -> bytes:
    """RFC 3676 space-unstuffing (drop one leading space per line), for a `format=flowed` body."""
    lines = sliced.split(b"\r\n")
    return b"\r\n".join(line[1:] if line.startswith(b" ") else line for line in lines)


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
        bodies: dict[str, tuple[int, int]] = {}
        for path, _parent, _ctype, raw_span, headers_span, body_span in facts.get("part.tree", []):
            bodies[path] = (body_span[0], body_span[1])
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
        chains = {row[0]: row for row in facts.get("decode.chain", [])}
        for part, text, precision, _reason in facts.get("body.text", []):
            if precision != "exact":
                continue
            span = bodies.get(part)
            if span is None:
                problems.append(f"{stem} body.text {part}: no part.tree row to locate the body")
                continue
            offset, length = span
            sliced = raw[offset : offset + length]
            charset = (chains.get(part) or [None] * 5)[4] or "utf-8"
            try:
                decoded = sliced.decode(charset)
            except (LookupError, UnicodeDecodeError):
                problems.append(f"{stem} body.text {part}: the body bytes do not decode as {charset!r}")
                continue
            if decoded != text and _unstuff(sliced).decode(charset) != text:
                problems.append(f"{stem} body.text {part}: the body bytes do not decode to the label text")
        for part, ordinal, tag, off, length in facts.get("body.html_spans", []):
            span = bodies.get(part)
            body = raw[span[0] : span[0] + span[1]] if span else b""
            if ("<" + tag).encode("ascii") not in body.lower():
                problems.append(f"{stem} html_spans {part}: the body has no <{tag}> element")
            if off < 0 or length < 0:
                problems.append(f"{stem} html_spans {part}: a negative projected span")
        for part, cids in facts.get("body.cid_refs", []):
            span = bodies.get(part)
            body = raw[span[0] : span[0] + span[1]] if span else b""
            for cid in cids:
                if b"cid:" + cid.encode("ascii") not in body:
                    problems.append(f"{stem} cid_refs {part}: the body does not reference {cid!r}")
        for _ordinal, _field, parameter, value, _state, _reason in facts.get("headers.parameters", []):
            needle = (b"--" + value.encode("latin-1")) if parameter == "boundary" else value.encode("latin-1")
            if needle not in raw:
                problems.append(f"{stem} headers.parameters {parameter}: the bytes do not carry {value!r}")
    return problems


def coverage(sidecars: dict[str, Sidecar]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sidecar in sidecars.values():
        for fact_id in sidecar.facts:
            counts[fact_id] = counts.get(fact_id, 0) + 1
    return counts


def _load_family(root: Path) -> dict[str, Sidecar]:
    return _family(load_sidecars(root))


def test_the_body_family_labels_load_and_are_ledgered() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    assert set(sidecars) == set(FAMILY_B), sorted(FAMILY_B - set(sidecars))
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
            json.dumps(sorted(FAMILY_B)),
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
    assert report["loaded"] >= len(FAMILY_B), report


def test_every_family_b_fact_id_is_declared() -> None:
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        for fact_id, fact in sidecar.facts.items():
            assert fact_id in FACTS, f"{stem}: {fact_id} is not declared in FACTS"
            assert FACTS[fact_id].phase == fact.phase, (
                f"{stem}: {fact_id} is labelled phase {fact.phase} and declared phase {FACTS[fact_id].phase}"
            )


def test_every_typed_span_slices_the_fixture_bytes() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    assert span_problems(sidecars) == []
    checked = sum(1 for sidecar in sidecars.values() if "body.text" in sidecar.facts)
    assert checked >= 5, "the body.text span check would be vacuous"
    html = sum(1 for sidecar in sidecars.values() if "body.html_spans" in sidecar.facts)
    assert html >= 4, "the html span check would be vacuous"


def test_every_family_b_gap_id_is_a_known_id() -> None:
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
    assert seen_gaps >= 1, "no Family B fixture carries a walker gap"


def test_the_family_meets_the_facts_the_catalogue_names() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    carried = coverage(sidecars)
    for fact_id, minimum in FAMILY_PLAN.items():
        assert carried.get(fact_id, 0) >= minimum, (
            f"{fact_id} is carried by {carried.get(fact_id, 0)} sidecar(s), the catalogue plan is {minimum}"
        )
    assert carried.get("document.axes", 0) == len(FAMILY_B)
    for fact_id in FAMILY_PLAN:
        values = [
            sidecar.facts[fact_id].value for sidecar in sidecars.values() if fact_id in sidecar.facts
        ]
        assert any(value for value in values), f"{fact_id} has only empty values"


def test_the_new_fact_shapes_are_well_formed() -> None:
    """The Family B facts carry the closed vocabularies the FACTS table declares."""
    precisions = {"exact", "part_level"}
    verbatim_reasons = {"cte_not_identity", "multibyte_without_offset_map", "decode_fallback"}
    selections = {"selected", "alternative_not_selected", "n/a"}
    emptiness_rules = {"whitespace_only", "stub_only"}
    parameter_states = {"decoded", "fallback", "undecodable"}
    fallback_reasons = {
        "encoded_word_in_parameter",
        "empty_charset",
        "missing_continuation_index",
        "duplicate_continuation_index",
    }
    seen = set()
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        facts = _facts(sidecar)
        for part, text, precision, reason in facts.get("body.text", []):
            seen.add("body.text")
            assert isinstance(part, str) and isinstance(text, str), f"{stem}: body.text row"
            assert precision in precisions, f"{stem}: verbatim_precision {precision!r}"
            assert (reason is None) is (precision == "exact"), f"{stem}: verbatim_reason {reason!r}"
            if reason is not None:
                assert reason in verbatim_reasons, f"{stem}: verbatim_reason {reason!r}"
        for part, group_id in facts.get("body.alternative_group", []):
            seen.add("body.alternative_group")
            assert isinstance(part, str) and isinstance(group_id, str) and group_id, f"{stem}: group row"
        for part, value in facts.get("body.selection", []):
            seen.add("body.selection")
            assert value in selections, f"{stem}: selection {value!r}"
        for part, ordinal, tag, off, length in facts.get("body.html_spans", []):
            seen.add("body.html_spans")
            assert isinstance(part, str) and isinstance(tag, str) and tag.isalpha(), f"{stem}: html tag"
            assert isinstance(ordinal, int) and not isinstance(ordinal, bool) and ordinal >= 0
            assert off >= 0 and length >= 0
        for part, cids in facts.get("body.cid_refs", []):
            seen.add("body.cid_refs")
            assert isinstance(part, str) and isinstance(cids, list) and cids, f"{stem}: cid row"
            assert len(cids) == len(set(cids)), f"{stem}: cids are not de-duplicated"
        for part, rule in facts.get("body.plain_effectively_empty", []):
            seen.add("body.plain_effectively_empty")
            assert rule in emptiness_rules, f"{stem}: emptiness_rule {rule!r}"
        for ordinal, field_name, parameter, value, state, reason in facts.get("headers.parameters", []):
            seen.add("headers.parameters")
            assert isinstance(ordinal, int) and isinstance(field_name, str) and isinstance(parameter, str)
            assert state in parameter_states, f"{stem}: decode_state {state!r}"
            assert (reason is None) or (state == "fallback" and reason in fallback_reasons), (
                f"{stem}: fallback_reason {reason!r}"
            )
            assert isinstance(value, str) and value
    assert seen == {
        "body.text",
        "body.alternative_group",
        "body.selection",
        "body.html_spans",
        "body.cid_refs",
        "body.plain_effectively_empty",
        "headers.parameters",
    }, f"the shape check would be vacuous: {sorted(seen)}"


def test_the_span_check_fails_on_a_planted_wrong_span(tmp_path: Path) -> None:
    source = FIXTURES / "generated" / "html_href_img_remote_and_cid"
    payload = sidecar_copy.payload_of(Path(f"{source}.expected.json"))
    payload["facts"]["body.cid_refs"]["value"][0][1] = ["nope@example.test"]
    sidecar_copy.write(tmp_path, payload, source=Path(f"{source}.expected.json"))
    problems = span_problems(_load_family(tmp_path))
    assert any("cid_refs" in problem for problem in problems), problems


def test_the_coverage_check_fails_on_a_missing_fact(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "fixtures")
    target = tmp_path / "fixtures" / "generated" / "html_style_and_script.expected.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["facts"].pop("body.html_spans")
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    problems = span_problems(_load_family(tmp_path / "fixtures"))
    carried = coverage(_load_family(tmp_path / "fixtures"))
    assert problems == []
    assert carried.get("body.html_spans", 0) < FAMILY_PLAN["body.html_spans"]
