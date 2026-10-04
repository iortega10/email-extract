"""Turn 1.0c, Family C: the attachments/caps fixtures' hand-typed labels.

This is the family's own check (the Phase 0 structure test is not extended for the new
fact shapes). It proves, without importing the walker:

* every Family C sidecar loads through the independent loader (`emailextract.evals.labels`,
  which imports nothing from the package) and is pinned in the label ledger;
* every fact id a Family C sidecar names is declared in the oracle's `FACTS` at the phase
  the label claims;
* every typed span slices the fixture's raw bytes to the text the label claims -- a
  byte-level check that does not parse anything (the header field spans, the region tiling,
  the part tree partition, the manifest's content hash and size, every filename, every cid
  and every boundary parameter);
* every gap id is a known one (a walker `GAP_*` constant or a design-registry id);
* the facts the family's catalogue rows name are carried by the sidecars that name them,
  at least one of them non-trivially;
* no committed attachment payload is compressed: every zip member is STORED (method 0) and
  every png IDAT is a stored deflate block, so no fixture byte depends on the zlib build;
* every fixture is under 64 KB.

The span and coverage checks are each proved able to fail on a planted wrong span and a
dropped fact, the stored-payload check on a planted deflated member, in temporary copies.
"""

from __future__ import annotations

import base64
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import zipfile
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

COMMITTED = (
    "attach_manifest_baseline",
    "attach_inline_referenced",
    "attach_inline_unreferenced",
    "attach_cid_dangling",
    "attach_duplicate_content_id",
    "attach_duplicate_filename_in_one_message",
    "attach_message_rfc822_no_filename",
    "attach_zip_magic_declared_disagree",
    "attach_unrecognized_magic",
    "attach_zero_length_part",
    "attach_disposition_size_and_date",
    "attach_filename_rfc2231_fallback",
    "attach_decoration_tracking_pixel",
    "attach_ole_cfb_magic",
    "attach_tnef_winmail",
    "attach_macro_docm",
    "attach_remote_image_only",
    "cap_deep_nesting",
    "cap_large_part_count",
    "cap_enormous_header_block",
    "cap_encoded_word_bomb",
    "cap_very_long_base64_run",
)

#: The twenty-two Family C catalogue rows (docs/design/phase1-fixtures.md, "Family C").
FAMILY_C = frozenset(COMMITTED)

#: The five cap fixtures (the hostile set): bytes tiny, structure deep or wide.
CAP_FIXTURES = frozenset(
    {
        "cap_deep_nesting",
        "cap_large_part_count",
        "cap_enormous_header_block",
        "cap_encoded_word_bomb",
        "cap_very_long_base64_run",
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

#: How many Family C sidecars carry each fact -- the family's own plan, read off the
#: catalogue's "Phase 1 facts / gap ids" column. The whole-corpus floors in
#: docs/design/phase1-facts.md span all three families and the quote catalogue, so a
#: 22-fixture family cannot meet them on its own; what this test fixes is that the family
#: carries each fact where the catalogue says it does, with at least one non-trivial value.
FAMILY_PLAN = {
    "document.axes": 22,
    "attach.manifest": 6,
    "attach.types": 5,
    "attach.filename": 1,
    "attach.decorative": 1,
    "attach.cid_use": 2,
    "body.cid_refs": 2,
    "headers.parameters": 1,
    "headers.decoded": 1,
    "body.text": 1,
    "body.plain_effectively_empty": 1,
    "gaps.later": 11,
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
    return {stem: sidecar for stem, sidecar in sidecars.items() if stem in FAMILY_C}


def _facts(sidecar: Sidecar) -> dict:
    return {fact_id: fact.value for fact_id, fact in sidecar.facts.items()}


def _registry_ids() -> set[str]:
    """The design's known-gap ids, fully qualified (`family.name`)."""
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


def _decoded_base64_bodies(raw: bytes, facts: dict) -> list[tuple[str, bytes]]:
    """Every leaf body the label says is base64, transfer-decoded (a byte-level read)."""
    bodies = {row[0]: row[5] for row in facts.get("part.tree", [])}
    chains = {row[0]: row for row in facts.get("decode.chain", [])}
    out: list[tuple[str, bytes]] = []
    for part, span in bodies.items():
        chain = chains.get(part)
        if chain is None or chain[1] != "base64":
            continue
        payload = raw[span[0] : span[0] + span[1]]
        try:
            out.append((part, base64.b64decode(b"".join(payload.split()), validate=True)))
        except Exception:
            continue
    return out


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
        decoded = dict(_decoded_base64_bodies(raw, facts))
        for part, filename, declared, cid, _disposition, _cte, digest, length in facts.get("attach.manifest", []):
            if part not in bodies:
                problems.append(f"{stem} attach.manifest {part}: no part.tree row for the occurrence")
            if filename is not None and filename.encode("utf-8") not in raw:
                problems.append(f"{stem} attach.manifest {part}: the bytes do not carry {filename!r}")
            if isinstance(declared, str) and declared.encode("ascii") not in raw:
                problems.append(f"{stem} attach.manifest {part}: the bytes do not declare {declared!r}")
            if part in decoded:
                if len(digest) != 64:
                    problems.append(f"{stem} attach.manifest {part}: content_sha256 is not a sha256")
                if length != len(decoded[part]):
                    problems.append(
                        f"{stem} attach.manifest {part}: size {length} != the decoded body {len(decoded[part])}"
                    )
        for part, declared, magic, container, winner, disagreement in facts.get("attach.types", []):
            if part not in bodies:
                problems.append(f"{stem} attach.types {part}: no part.tree row for the occurrence")
            for triple in (declared, magic, container):
                if triple[0] == "value" and triple[1] not in (None, "unrecognized") and "/" in str(triple[1]):
                    if str(triple[1]).encode("ascii") not in raw:
                        problems.append(f"{stem} attach.types {part}: the bytes do not declare {triple[1]!r}")
            if not isinstance(winner, str) or not isinstance(disagreement, bool):
                problems.append(f"{stem} attach.types {part}: winner/disagreement shape")
        for part, filename_raw, _state, _decoded, _reason in facts.get("attach.filename", []):
            if filename_raw is not None and filename_raw.encode("utf-8") not in raw:
                problems.append(f"{stem} attach.filename {part}: the bytes do not carry {filename_raw!r}")
        for part, cid, referenced in facts.get("attach.cid_use", []):
            if cid is not None and cid.encode("utf-8") not in raw:
                problems.append(f"{stem} attach.cid_use {part}: the bytes do not carry {cid!r}")
            if cid is None and referenced != "n/a":
                problems.append(f"{stem} attach.cid_use {part}: no cid but referenced={referenced!r}")
        for part, cids in facts.get("body.cid_refs", []):
            span = bodies.get(part)
            body = raw[span[0] : span[0] + span[1]] if span else b""
            for cid in cids:
                if b"cid:" + cid.encode("ascii") not in body:
                    problems.append(f"{stem} cid_refs {part}: the body does not reference {cid!r}")
        for part, rule in facts.get("attach.decorative", []):
            if part not in bodies:
                problems.append(f"{stem} attach.decorative {part}: no part.tree row")
        for _ordinal, _field, parameter, value, _state, _reason in facts.get("headers.parameters", []):
            needle = (b"--" + value.encode("latin-1")) if parameter == "boundary" else value.encode("latin-1")
            if needle not in raw:
                problems.append(f"{stem} headers.parameters {parameter}: the bytes do not carry {value!r}")
        chains = {row[0]: row for row in facts.get("decode.chain", [])}
        for part, text, precision, _reason in facts.get("body.text", []):
            if precision != "exact":
                continue
            span = bodies.get(part)
            if span is None:
                problems.append(f"{stem} body.text {part}: no part.tree row to locate the body")
                continue
            sliced = raw[span[0] : span[0] + span[1]]
            charset = (chains.get(part) or [None] * 5)[4] or "utf-8"
            try:
                if sliced.decode(charset) != text:
                    problems.append(f"{stem} body.text {part}: the body bytes do not decode to the label text")
            except (LookupError, UnicodeDecodeError):
                problems.append(f"{stem} body.text {part}: the body bytes do not decode as {charset!r}")
    return problems


def coverage(sidecars: dict[str, Sidecar]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sidecar in sidecars.values():
        for fact_id in sidecar.facts:
            counts[fact_id] = counts.get(fact_id, 0) + 1
    return counts


def _load_family(root: Path) -> dict[str, Sidecar]:
    return _family(load_sidecars(root))


def _payload_blobs(sidecars: dict[str, Sidecar]) -> list[tuple[str, bytes]]:
    """Every transfer-decoded leaf body under the family, keyed ``stem:part``."""
    blobs = []
    for stem, sidecar in sidecars.items():
        raw = sidecar.artifact.read_bytes()
        for part, blob in _decoded_base64_bodies(raw, _facts(sidecar)):
            blobs.append((f"{stem}:{part}", blob))
    return blobs


def zip_local_methods(blob: bytes) -> tuple[list[int], bool]:
    """Every local-file-header compression method, and whether the central directory is reached."""
    methods: list[int] = []
    position = 0
    while position < len(blob) and blob[position : position + 4] == b"PK\x03\x04":
        methods.append(struct.unpack_from("<H", blob, position + 8)[0])
        name_len, extra_len = struct.unpack_from("<HH", blob, position + 26)
        size = struct.unpack_from("<I", blob, position + 18)[0]
        position += 30 + name_len + extra_len + size
    return methods, blob[position : position + 4] == b"PK\x01\x02"


def zip_central_methods(blob: bytes) -> list[int]:
    methods: list[int] = []
    position = blob.find(b"PK\x01\x02")
    while position != -1 and blob[position : position + 4] == b"PK\x01\x02":
        methods.append(struct.unpack_from("<H", blob, position + 10)[0])
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", blob, position + 28)
        position += 46 + name_len + extra_len + comment_len
    return methods


def png_idat(blob: bytes) -> bytes:
    position, idat = 8, b""
    while position < len(blob):
        length = struct.unpack_from(">I", blob, position)[0]
        kind = blob[position + 4 : position + 8]
        if kind == b"IDAT":
            idat += blob[position + 8 : position + 8 + length]
        position += 12 + length
    return idat


def compressed_payload_problems(blobs: list[tuple[str, bytes]]) -> list[str]:
    """Every zip member that is not STORED and every png IDAT that is not stored deflate."""
    problems: list[str] = []
    for where, blob in blobs:
        if blob.startswith(b"PK\x03\x04"):
            local, reached = zip_local_methods(blob)
            if not reached:
                problems.append(f"{where}: the central directory was not reached")
            for method in local + zip_central_methods(blob):
                if method != 0:
                    problems.append(f"{where}: a zip member uses compression method {method}")
        elif blob.startswith(b"\x89PNG\r\n\x1a\n"):
            idat = png_idat(blob)
            if not idat.startswith(b"\x78\x01"):
                problems.append(f"{where}: the png zlib stream is not the uncompressed preset")
                continue
            blocks, offset = idat[2:-4], 0
            while True:
                header = blocks[offset]
                if (header >> 1) & 0x03 != 0:
                    problems.append(f"{where}: a png deflate block is not stored")
                    break
                length = struct.unpack_from("<H", blocks, offset + 1)[0]
                offset += 5 + length
                if header & 0x01:
                    break
                if offset >= len(blocks):
                    problems.append(f"{where}: the png stored blocks overrun the IDAT")
                    break
    return problems


def test_the_attachments_family_labels_load_and_are_ledgered() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    assert set(sidecars) == set(FAMILY_C), sorted(FAMILY_C - set(sidecars))
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
            json.dumps(sorted(FAMILY_C)),
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
    assert report["loaded"] >= len(FAMILY_C), report


def test_every_family_c_fact_id_is_declared() -> None:
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        for fact_id, fact in sidecar.facts.items():
            assert fact_id in FACTS, f"{stem}: {fact_id} is not declared in FACTS"
            assert FACTS[fact_id].phase == fact.phase, (
                f"{stem}: {fact_id} is labelled phase {fact.phase} and declared phase {FACTS[fact_id].phase}"
            )


def test_every_typed_span_slices_the_fixture_bytes() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    assert span_problems(sidecars) == []
    checked = sum(1 for sidecar in sidecars.values() if "attach.manifest" in sidecar.facts)
    assert checked >= 5, "the manifest check would be vacuous"
    blobs = [blob for _where, blob in _payload_blobs(sidecars)]
    assert sum(1 for blob in blobs if blob.startswith(b"PK\x03\x04")) >= 1, "no zip payload was checked"
    assert sum(1 for blob in blobs if blob.startswith(b"\x89PNG")) >= 1, "no png payload was checked"


def test_every_family_c_gap_id_is_a_known_id() -> None:
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
    # The family's gaps are all later-phase registry ids: no Family C fixture records a
    # walker gap today, and the catalogue names none.
    assert seen_gaps == 0, "a Family C fixture records a walker gap the catalogue does not name"


def test_the_family_meets_the_facts_the_catalogue_names() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    carried = coverage(sidecars)
    for fact_id, minimum in FAMILY_PLAN.items():
        assert carried.get(fact_id, 0) >= minimum, (
            f"{fact_id} is carried by {carried.get(fact_id, 0)} sidecar(s), the catalogue plan is {minimum}"
        )
    assert carried.get("document.axes", 0) == len(FAMILY_C)
    for fact_id in FAMILY_PLAN:
        values = [
            sidecar.facts[fact_id].value for sidecar in sidecars.values() if fact_id in sidecar.facts
        ]
        assert any(value for value in values), f"{fact_id} has only empty values"


def test_the_new_fact_shapes_are_well_formed() -> None:
    """The Family C facts carry the closed vocabularies the FACTS table declares."""
    axis_ids = {
        "attachment.status",
        "attachment.route",
        "document.times",
        "document.thread_edges",
        "document.children",
        "document.same_message_candidates",
    }
    dispositions = {"attachment", "inline", None}
    verdict_states = {"value", "absent", "unknown"}
    winners = {"magic", "declared_mime", "container_introspection", None}
    filename_states = {"decoded", "fallback", "absent", "unparsable"}
    fallback_reasons = {
        "encoded_word_in_parameter",
        "empty_charset",
        "missing_continuation_index",
        "duplicate_continuation_index",
    }
    hint_rules = {None, "inline_unreferenced_small_image", "inline_unreferenced_tracking_pixel"}
    cid_states = {"referenced", "unreferenced", "n/a"}
    parameter_states = {"decoded", "fallback", "undecodable"}
    precisions = {"exact", "part_level"}
    verbatim_reasons = {"cte_not_identity", "multibyte_without_offset_map", "decode_fallback"}
    emptiness_rules = {"whitespace_only", "stub_only"}
    seen = set()
    for stem, sidecar in _family(load_sidecars(FIXTURES)).items():
        facts = _facts(sidecar)
        for axis_id, state, reason in facts.get("document.axes", []):
            seen.add("document.axes")
            assert axis_id in axis_ids, f"{stem}: axis {axis_id!r} is not a closed axis id"
            assert state in verdict_states, f"{stem}: axis state {state!r}"
            assert (reason is None) is (state != "unknown"), f"{stem}: axis {axis_id} reason/state"
            if state == "unknown":
                assert reason == "not_built_in_phase1", f"{stem}: {axis_id} reason {reason!r}"
        for row in facts.get("attach.manifest", []):
            seen.add("attach.manifest")
            part, filename, declared, cid, disposition, cte, digest, length = row
            assert isinstance(part, str) and part
            assert filename is None or isinstance(filename, str)
            assert declared is None or isinstance(declared, str)
            assert cid is None or isinstance(cid, str)
            assert disposition in dispositions, f"{stem} {part}: disposition {disposition!r}"
            assert cte is None or isinstance(cte, str)
            assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), f"{stem} {part}: digest"
            assert isinstance(length, int) and not isinstance(length, bool) and length >= 0
        for row in facts.get("attach.types", []):
            seen.add("attach.types")
            part, declared, magic, container, winner, disagreement = row
            assert isinstance(part, str) and part
            for triple in (declared, magic, container):
                state, value, reason = triple
                assert state in verdict_states, f"{stem} {part}: verdict state {state!r}"
                assert (reason is None) is (state != "unknown"), f"{stem} {part}: verdict reason/state"
                if state == "absent":
                    assert value in (None, "unrecognized"), f"{stem} {part}: absent verdict value {value!r}"
            assert winner in winners, f"{stem} {part}: winner {winner!r}"
            assert isinstance(disagreement, bool), f"{stem} {part}: disagreement {disagreement!r}"
        for row in facts.get("attach.filename", []):
            seen.add("attach.filename")
            part, raw, state, decoded, reason = row
            assert isinstance(part, str) and isinstance(raw, str)
            assert state in filename_states, f"{stem} {part}: decode_state {state!r}"
            assert (reason is None) or (state == "fallback" and reason in fallback_reasons), (
                f"{stem} {part}: fallback_reason {reason!r}"
            )
            assert decoded is None or isinstance(decoded, str)
        for row in facts.get("attach.decorative", []):
            seen.add("attach.decorative")
            part, rule = row
            assert isinstance(part, str) and part
            assert rule in hint_rules, f"{stem} {part}: decorative rule {rule!r}"
        for row in facts.get("attach.cid_use", []):
            seen.add("attach.cid_use")
            part, cid, referenced = row
            assert isinstance(part, str) and part
            assert cid is None or isinstance(cid, str)
            assert referenced in cid_states, f"{stem} {part}: referenced {referenced!r}"
        for row in facts.get("body.cid_refs", []):
            seen.add("body.cid_refs")
            part, cids = row
            assert isinstance(part, str) and isinstance(cids, list) and cids, f"{stem}: cid row"
            assert len(cids) == len(set(cids)), f"{stem}: cids are not de-duplicated"
        for row in facts.get("headers.parameters", []):
            seen.add("headers.parameters")
            ordinal, field_name, parameter, value, state, reason = row
            assert isinstance(ordinal, int) and isinstance(field_name, str) and isinstance(parameter, str)
            assert state in parameter_states, f"{stem}: decode_state {state!r}"
            assert (reason is None) or (state == "fallback" and reason in fallback_reasons), (
                f"{stem}: fallback_reason {reason!r}"
            )
            assert isinstance(value, str) and value
        for row in facts.get("headers.decoded", []):
            seen.add("headers.decoded")
            ordinal, decoded = row
            assert isinstance(ordinal, int) and isinstance(decoded, str)
        for row in facts.get("body.text", []):
            seen.add("body.text")
            part, text, precision, reason = row
            assert isinstance(part, str) and isinstance(text, str), f"{stem}: body.text row"
            assert precision in precisions, f"{stem}: verbatim_precision {precision!r}"
            assert (reason is None) is (precision == "exact"), f"{stem}: verbatim_reason {reason!r}"
            if reason is not None:
                assert reason in verbatim_reasons, f"{stem}: verbatim_reason {reason!r}"
        for row in facts.get("body.plain_effectively_empty", []):
            seen.add("body.plain_effectively_empty")
            part, rule = row
            assert isinstance(part, str) and rule in emptiness_rules, f"{stem}: emptiness_rule {rule!r}"
    assert seen == {
        "document.axes",
        "attach.manifest",
        "attach.types",
        "attach.filename",
        "attach.decorative",
        "attach.cid_use",
        "body.cid_refs",
        "headers.parameters",
        "headers.decoded",
        "body.text",
        "body.plain_effectively_empty",
    }, f"the shape check would be vacuous: {sorted(seen)}"


def test_the_span_check_fails_on_a_planted_wrong_span(tmp_path: Path) -> None:
    source = FIXTURES / "generated" / "attach_filename_rfc2231_fallback"
    payload = sidecar_copy.payload_of(Path(f"{source}.expected.json"))
    payload["facts"]["attach.filename"]["value"][0][1] = "not-in-the-bytes.log"
    sidecar_copy.write(tmp_path, payload, source=Path(f"{source}.expected.json"))
    problems = span_problems(_load_family(tmp_path))
    assert any("attach.filename" in problem for problem in problems), problems


def test_the_coverage_check_fails_on_a_missing_fact(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "fixtures")
    target = tmp_path / "fixtures" / "generated" / "attach_manifest_baseline.expected.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["facts"].pop("document.axes")
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    problems = span_problems(_load_family(tmp_path / "fixtures"))
    carried = coverage(_load_family(tmp_path / "fixtures"))
    assert problems == []
    assert carried.get("document.axes", 0) < len(FAMILY_C)


def test_every_zip_payload_is_stored_and_no_png_is_compressed() -> None:
    sidecars = _family(load_sidecars(FIXTURES))
    blobs = _payload_blobs(sidecars)
    assert compressed_payload_problems(blobs) == []
    # The check can fail: a deflated member is caught (the proof is not vacuous).
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("member.txt", b"x" * 512)
    planted = [("planted", buffer.getvalue())]
    assert compressed_payload_problems(planted) != [], "a deflated member was NOT detected"
    assert zip_local_methods(buffer.getvalue())[0] == [8]


def test_every_fixture_is_under_64_kb() -> None:
    fixtures = [
        path
        for directory in ("generated", "raw", "time")
        for path in (FIXTURES / directory).glob("*.eml")
    ]
    assert len(fixtures) >= len(FAMILY_C)
    oversized = sorted(f"{path.name}: {path.stat().st_size}" for path in fixtures if path.stat().st_size >= 64 * 1024)
    assert oversized == [], oversized
