"""The quote-catalogue increment (between Turns 1.5 and 1.6): the 29 hand-typed rows.

This test has no access to the quote rules (there are none yet). It proves, without importing
the walker or the package:

* **reviewability** -- every one of the 29 catalogue rows has a fixture, a sidecar, a section in
  ``docs/design/quote-catalogue-review.md`` and a non-empty "hinge" quotation that actually
  occurs in the fixture's bytes (a byte-level check that parses nothing);
* **the labels load and are ledgered** -- every sidecar loads through the independent loader
  (``emailextract.evals.labels``, which imports nothing from the package), every fact id is
  declared in the oracle's ``FACTS`` at the phase the label claims, every typed span slices the
  fixture's bytes or the typed ``body.text`` / the HTML projection, only ``kind = quote`` rows
  advance an ordinal, a forward row is level 0, every gap id is a registered one, and every
  sidecar is pinned in the additions-only label ledger;
* **the NOT v1 rows are absent** -- no fixture, no sidecar and no review-document row is named
  ``apple_attribution`` or ``yahoo_quoted``, and the review document names them NOT v1 with the
  gap id;
* the HTML ``body.html_spans`` labels are re-derived by an **independent stdlib projection**
  (``html.parser``) and equal the typed spans -- the second derivation of the second rule;
* the generated rows rebuild byte-identically and the raw rows match their frozen digest.

Every check is proved able to fail: planted wrong spans, a removed hinge quotation, a removed
review row, a baroque forward row.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from support import sidecar_copy  # noqa: E402

import make_fixtures  # noqa: E402
import write_raw_fixtures  # noqa: E402

from emailextract.evals.l1 import FACTS  # noqa: E402
from emailextract.evals.labels import Sidecar, load_sidecars  # noqa: E402

FIXTURES = ROOT / "fixtures"
GENERATED = FIXTURES / "generated"
RAW = FIXTURES / "raw"
LEDGER = ROOT / "tests" / "ledger" / "label_ledger.json"
REVIEW = ROOT / "docs" / "design" / "quote-catalogue-review.md"
DESIGN = ROOT / "docs" / "design" / "email-extraction-design.md"

#: The quote catalogue's 29 rows (docs/design/phase1-fixtures.md, "The quote catalogue"),
#: in the table's order. Names are BINDING. Rows 27-29 are the three "hole" rows the plan
#: debate added after the owner's delegated sign-off.
CATALOGUE: tuple[str, ...] = (
    "quoted_outlook_flat",
    "quoted_prefix_gt_deep",
    "inline_reply_interleaved",
    "html_only",
    "html_gmail_quote",
    "html_outlook_divrplyfwd",
    "no_boundary_found",
    "i18n_reply_marker",
    "forwarded_inline_marker",
    "headers_only",
    "gmail_reply_quoting_outlook_authored",
    "gmail_short_reply_gt_and_on_wrote",
    "mixed_origin_quote",
    "outlook_labels_de",
    "outlook_labels_fr",
    "unknown_language_label_block",
    "gmail_quote_on_blockquote",
    "outlook_com_appendonsend",
    "thunderbird_moz_cite_prefix",
    "thunderbird_moz_forward_container",
    "begin_forwarded_message",
    "original_message_dashes",
    "signature_dash_dash_space",
    "list_footer_underscores",
    "bottom_posted_reply",
    "vendor_prefix_class_no_table_row",
    "on_wrote_hard_wrapped",
    "flowed_quote_depth",
    "gt_spacing_variants",
)

NOT_V1 = ("apple_attribution", "yahoo_quoted")

QUOTE_KINDS = frozenset({"quote", "forward", "signature", "list_footer", "unknown"})

ROW_HEADING = re.compile(r"^###\s+\d+\.\s+`([a-z0-9_]+)`\s+\u2014\s+consuming turn\s+(\S+)", re.M)
HINGE_LINE = re.compile(r"^- \*\*Hinge \(bytes\):\*\* `(.*)`\s*$", re.M)


# ------------------------------------------------------------------ parsing helpers


def _load(name: str) -> Sidecar:
    for directory in (GENERATED, RAW):
        path = directory / f"{name}.expected.json"
        if path.exists():
            from emailextract.evals.labels import load_sidecar

            return load_sidecar(path)
    raise FileNotFoundError(name)


def _facts(sidecar: Sidecar) -> dict:
    return {fact_id: fact.value for fact_id, fact in sidecar.facts.items()}


def review_rows(text: str) -> dict[str, tuple[str, str]]:
    """``name -> (consuming turn, hinge bytes)`` for every section of the review document."""
    rows: dict[str, tuple[str, str]] = {}
    headings = list(ROW_HEADING.finditer(text))
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[match.start():end]
        hinge = HINGE_LINE.search(section)
        rows[match.group(1)] = (match.group(2), hinge.group(1) if hinge else "")
    return rows


def _registry_ids() -> set[str]:
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


# ------------------------------------------------------- the independent HTML projection


class _Projector(HTMLParser):
    """The stated projection rule, re-implemented here: text nodes verbatim, style/script/head
    and comments dropped, nothing inserted; an element's span covers its subtree text and a
    zero-length element sits at its start tag."""

    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                      "meta", "param", "source", "track", "wbr"})
    DROP = frozenset({"style", "script", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.length = 0
        self.elements: list[list] = []
        self.stack: list[int] = []

    def _dropped(self) -> bool:
        return any(self.elements[i][0] in self.DROP for i in self.stack)

    def handle_starttag(self, tag, attrs) -> None:
        idx = len(self.elements)
        self.elements.append([tag, None, None, self.length])
        if tag in self.VOID:
            self.elements[idx][1] = self.length
            self.elements[idx][2] = self.length
        else:
            self.stack.append(idx)

    def handle_startendtag(self, tag, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag) -> None:
        for position in range(len(self.stack) - 1, -1, -1):
            if self.elements[self.stack[position]][0] == tag:
                for k in self.stack[position:]:
                    self._close(k)
                del self.stack[position:]
                return

    def _close(self, idx) -> None:
        tag, start, end, elem_start = self.elements[idx]
        if start is None:
            self.elements[idx] = [tag, elem_start, elem_start, elem_start]
        else:
            self.elements[idx] = [tag, start, end, elem_start]

    def handle_data(self, data) -> None:
        if self._dropped():
            return
        base = self.length
        self.chunks.append(data)
        self.length += len(data)
        for idx in self.stack:
            if self.elements[idx][1] is None:
                self.elements[idx][1] = base
            self.elements[idx][2] = base + len(data)

    def result(self, part: str) -> tuple[str, list[list]]:
        rows = []
        for ordinal, (tag, start, end, _es) in enumerate(self.elements):
            offset = start if start is not None else 0
            length = (end - start) if (start is not None and end is not None) else 0
            rows.append([part, ordinal, tag, offset, length])
        return "".join(self.chunks), rows


def _project(html: str, part: str) -> tuple[str, list[list]]:
    parser = _Projector()
    parser.feed(html)
    parser.close()
    for idx in list(parser.stack):
        parser._close(idx)
    return parser.result(part)


def _part_spans(raw: bytes, facts: dict) -> dict[str, tuple[int, int]]:
    return {row[0]: (row[5][0], row[5][1]) for row in facts.get("part.tree", [])}


def html_span_problems(sidecar: Sidecar) -> list[str]:
    """Every typed html span that the independent projection does not reproduce."""
    problems: list[str] = []
    raw = sidecar.artifact.read_bytes()
    facts = _facts(sidecar)
    if "body.html_spans" not in facts:
        return problems
    bodies = _part_spans(raw, facts)
    ctypes = {row[0]: row[2] for row in facts.get("part.tree", [])}
    typed: dict[str, list[list]] = {}
    for row in facts["body.html_spans"]:
        typed.setdefault(row[0], []).append(row)
    for part, rows in typed.items():
        if part not in bodies or not ctypes.get(part) or "html" not in ctypes[part].lower():
            problems.append(f"{sidecar.stem} html_spans {part}: not an html part")
            continue
        offset, length = bodies[part]
        piece = raw[offset:offset + length].decode("utf-8", "replace")
        _projection, derived = _project(piece, part)
        if derived != rows:
            problems.append(f"{sidecar.stem} html_spans {part}: typed {rows} != derived {derived}")
    return problems


def quote_problems(sidecar: Sidecar) -> list[str]:
    """Every problem with a sidecar's typed quote facts and typed spans."""
    problems: list[str] = []
    raw = sidecar.artifact.read_bytes()
    facts = _facts(sidecar)
    bodies = _part_spans(raw, facts)
    ctypes = {row[0]: row[2] for row in facts.get("part.tree", [])}
    texts = {row[0]: row[1] for row in facts.get("body.text", [])}

    def view_text(part: str, view: str) -> str | None:
        if view == "plain":
            return texts.get(part)
        if view == "html":
            if part not in bodies:
                return None
            offset, length = bodies[part]
            return _project(raw[offset:offset + length].decode("utf-8", "replace"), part)[0]
        return None

    boundaries = facts.get("body.quote_boundaries", [])
    seen_ordinals: dict[tuple[str, str], list[int]] = {}
    for row in boundaries:
        if len(row) != 8:
            problems.append(f"{sidecar.stem} quote_boundaries: row {row!r} is not 8 columns")
            continue
        part, view, rule, kind, ordinal, depths, offset, length = row
        if kind not in QUOTE_KINDS:
            problems.append(f"{sidecar.stem} quote_boundaries: kind {kind!r}")
        text = view_text(part, view)
        if text is None:
            problems.append(f"{sidecar.stem} quote_boundaries {part}/{view}: no such view")
            continue
        if not (0 <= offset and offset + length <= len(text)):
            problems.append(f"{sidecar.stem} quote_boundaries {part}/{view}: span {offset, length} "
                            f"outside the {len(text)}-code-point view")
            continue
        lines = text[offset:offset + length].split("\r\n")
        for line, depth in zip(lines, depths):
            # A `>`-family prefix is a run of `>` characters optionally separated by SP or
            # TAB only; U+00A0 (NBSP) is neither and stops the count (row 29).
            counted = 0
            for char in line:
                if char == ">":
                    counted += 1
                elif char in " \t":
                    continue
                else:
                    break
            if counted != depth:
                problems.append(f"{sidecar.stem} quote_boundaries {part}/{view}: depth {depth} "
                                f"!= counted {counted} on {line!r}")
        if len(depths) != len(lines):
            problems.append(f"{sidecar.stem} quote_boundaries {part}/{view}: {len(depths)} depths "
                            f"for {len(lines)} lines")
        if kind == "quote":
            if ordinal < 1:
                problems.append(f"{sidecar.stem} quote_boundaries {part}/{view}: quote ordinal {ordinal}")
            seen_ordinals.setdefault((part, view), []).append(ordinal)
        elif ordinal != 0:
            problems.append(f"{sidecar.stem} quote_boundaries {part}/{view}: kind {kind} ordinal {ordinal}")
    for key, ordinals in seen_ordinals.items():
        if ordinals != list(range(1, len(ordinals) + 1)):
            problems.append(f"{sidecar.stem} quote_boundaries {key}: quote ordinals {ordinals}")

    levels = facts.get("body.view_levels", [])
    kinds_by_view: dict[tuple[str, str], set[str]] = {}
    for row in boundaries:
        if len(row) == 8:
            kinds_by_view.setdefault((row[0], row[1]), set()).add(row[3])
    for row in levels:
        if len(row) != 4:
            problems.append(f"{sidecar.stem} view_levels: row {row!r} is not 4 columns")
            continue
        part, view, level, _rule = row
        if view_text(part, view) is None:
            problems.append(f"{sidecar.stem} view_levels {part}/{view}: no such view")
        if "quote" not in kinds_by_view.get((part, view), set()) and level != 0:
            problems.append(f"{sidecar.stem} view_levels {part}/{view}: a view with no kind=quote "
                            f"boundary is level 0, typed {level}")
    return problems


def _fixture_path(name: str) -> Path:
    for directory in (GENERATED, RAW):
        path = directory / f"{name}.eml"
        if path.exists():
            return path
    raise FileNotFoundError(name)


def reviewability_problems(names, review_text: str) -> list[str]:
    """Fixture + sidecar + review section + hinge-in-bytes, for every catalogue row."""
    problems: list[str] = []
    rows = review_rows(review_text)
    for name in names:
        if not (GENERATED / f"{name}.eml").exists() and not (RAW / f"{name}.eml").exists():
            problems.append(f"{name}: no committed fixture")
            continue
        if not (GENERATED / f"{name}.expected.json").exists() and not (RAW / f"{name}.expected.json").exists():
            problems.append(f"{name}: no sidecar")
        if name not in rows:
            problems.append(f"{name}: no review-document section")
            continue
        hinge = rows[name][1]
        if not hinge:
            problems.append(f"{name}: the review row has no raw line or element quotation")
            continue
        if hinge.encode("utf-8") not in _fixture_path(name).read_bytes():
            problems.append(f"{name}: the quoted line {hinge!r} does not occur in the fixture bytes")
    return problems


# ------------------------------------------------------------------------------ the tests


def test_every_catalogue_row_is_reviewable() -> None:
    assert len(CATALOGUE) == 29, len(CATALOGUE)
    problems = reviewability_problems(CATALOGUE, REVIEW.read_text(encoding="utf-8"))
    assert problems == [], problems
    # The check is not vacuous: it sees the 29 hinges.
    rows = review_rows(REVIEW.read_text(encoding="utf-8"))
    assert set(rows) == set(CATALOGUE), sorted(set(CATALOGUE) ^ set(rows))
    assert all(rows[name][1] for name in CATALOGUE)


def test_the_reviewability_check_fails_on_a_missing_quotation() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    # Drop a hinge quotation and the whole section: the check names the row.
    doctored = re.sub(r"^- \*\*Hinge \(bytes\):\*\* .*$", "- **Hinge (bytes):**", text, count=1, flags=re.M)
    problems = reviewability_problems(CATALOGUE, doctored)
    assert any("no raw line or element quotation" in problem for problem in problems), problems
    dropped = ROW_HEADING.sub("", text, count=1)
    problems = reviewability_problems(CATALOGUE, dropped)
    assert any("no review-document section" in problem for problem in problems), problems


def test_the_catalogue_labels_load_and_are_ledgered() -> None:
    loaded = load_sidecars(FIXTURES)
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))["files"]
    registry = _registry_ids()
    for name in CATALOGUE:
        sidecar = loaded[name]
        assert sidecar.labels_provenance == "spec", name
        relative = sidecar.path.relative_to(ROOT).as_posix()
        assert relative in ledger, f"{name}: {relative} is not in the label ledger"
        for fact_id, fact in sidecar.facts.items():
            assert fact_id in FACTS, f"{name}: {fact_id} is not declared in FACTS"
            assert FACTS[fact_id].phase == fact.phase, (name, fact_id)
        problems = quote_problems(sidecar)
        assert problems == [], problems
        for gap_id, locator, phase, reason in _facts(sidecar).get("gaps.later", []):
            assert gap_id in registry, f"{name}: gaps.later names {gap_id!r}, not a registry id"
            assert isinstance(locator, str) and locator
            assert isinstance(phase, int) and phase >= 1
            assert isinstance(reason, str) and reason
    # Non-vacuous: only quote rows advance ordinals, and the catalogue has both quote and
    # non-quote kind rows (so the rule is exercised in both directions).
    kinds = {
        kind
        for name in CATALOGUE
        for row in _facts(loaded[name]).get("body.quote_boundaries", [])
        for kind in [row[3]]
    }
    assert "quote" in kinds and kinds - {"quote"}, kinds


def test_the_three_hole_rows_exist_and_type_the_decided_rules(tmp_path: Path) -> None:
    """Rows 27-29: the plan debate's three holes, typed by the signed-off reading."""
    loaded = load_sidecars(FIXTURES)

    # 27 -- the hard-wrapped attribution: the TWO-line window fires and spans the
    # attribution plus the quoted line; the THREE-line attribution must NOT fire.
    hard = _facts(loaded["on_wrote_hard_wrapped"])
    rules = [(row[2], row[3], row[4], row[6], row[7]) for row in hard["body.quote_boundaries"]]
    assert rules == [("on_wrote_en", "quote", 1, 11, 86), ("gt_family", "quote", 2, 170, 16)], rules
    text = hard["body.text"][0][1]
    fired = text[11:11 + 86]
    assert fired.startswith("On Mon, 3 Mar 2025 at 09:15, Ada Sender"), fired
    assert fired.endswith("> the earlier line"), fired
    # the three-line attribution is inside no boundary: it is new text (level 0).
    unwrapped = "On Tue, 4 Mar 2025 at 11:30, Zoe Sender\r\n<zoe@example.test>\r\nwrote:"
    position = text.index(unwrapped)
    assert not any(
        row[6] <= position < row[6] + row[7] for row in hard["body.quote_boundaries"]
    ), hard["body.quote_boundaries"]

    # 28 -- a flowed part: depth is per PHYSICAL line on the unjoined text (two lines,
    # each depth 1) and the soft-break join is deferred to gaps.later.
    flowed = _facts(loaded["flowed_quote_depth"])
    row = flowed["body.quote_boundaries"][0]
    assert row[3] == "quote" and row[5] == [1, 1], row
    span = flowed["body.text"][0][1][row[6]:row[6] + row[7]]
    assert span.count("\r\n") == 1, span  # unjoined: the two quoted lines stay physical
    assert {gap[0] for gap in flowed["gaps.later"]} == {"body.flowed_reflow_unresolved"}

    # 29 -- the spacing variants: TAB separates `>` runs, U+00A0 does NOT.
    gt = _facts(loaded["gt_spacing_variants"])
    row = gt["body.quote_boundaries"][0]
    assert row[5] == [1, 2, 2, 2, 3, 1], row[5]
    lines = gt["body.text"][0][1][row[6]:row[6] + row[7]].split("\r\n")
    assert lines[3].startswith(">\t>") and row[5][3] == 2, lines[3]
    assert lines[5].startswith(">\u00a0>") and row[5][5] == 1, lines[5]

    # The check is not vacuous: counting NBSP as a separator fails the depth check.
    source = RAW / "gt_spacing_variants"
    payload = sidecar_copy.payload_of(Path(f"{source}.expected.json"))
    payload["facts"]["body.quote_boundaries"]["value"][0][5][5] = 2  # NBSP counted
    sidecar_copy.write(tmp_path, payload, source=Path(f"{source}.expected.json"))
    from emailextract.evals.labels import load_sidecar

    written = sorted(tmp_path.rglob("*.expected.json"))[0]
    problems = quote_problems(load_sidecar(written))
    assert any("quote_boundaries" in problem for problem in problems), problems


def test_the_quote_span_check_fails_on_a_planted_wrong_span(tmp_path: Path) -> None:
    source = GENERATED / "html_gmail_quote"
    payload = sidecar_copy.payload_of(Path(f"{source}.expected.json"))
    payload["facts"]["body.quote_boundaries"]["value"][0][6] += 1  # shift the html span
    sidecar_copy.write(tmp_path, payload, source=Path(f"{source}.expected.json"))
    from emailextract.evals.labels import load_sidecar

    written = sorted(tmp_path.rglob("*.expected.json"))[0]
    problems = quote_problems(load_sidecar(written))
    assert any("quote_boundaries" in problem for problem in problems), problems


def test_the_not_v1_rows_are_absent_from_the_rules() -> None:
    catalogue_text = (ROOT / "docs" / "design" / "phase1-fixtures.md").read_text(encoding="utf-8")
    review_text = REVIEW.read_text(encoding="utf-8")
    present = set(load_sidecars(FIXTURES))
    for name in NOT_V1:
        assert name not in CATALOGUE
        assert not (GENERATED / f"{name}.eml").exists() and not (RAW / f"{name}.eml").exists()
        assert not (GENERATED / f"{name}.expected.json").exists()
        assert not (RAW / f"{name}.expected.json").exists()
        assert name not in present
        assert not any(name == heading for heading in review_rows(review_text))
        # The review document names it as NOT v1 with the gap id.
        assert re.search(rf"`{name}`: \*\*NOT v1\*\*", review_text), name
    assert review_text.count("body.html_quote_rule_gap") >= 2
    assert "NOT v1" in catalogue_text and "apple_attribution" in catalogue_text


def test_every_quote_html_span_is_rederived_by_an_independent_projection() -> None:
    problems: list[str] = []
    checked = 0
    loaded = load_sidecars(FIXTURES)
    for name in CATALOGUE:
        sidecar = loaded[name]
        problems.extend(html_span_problems(sidecar))
        if "body.html_spans" in sidecar.facts:
            checked += 1
    assert problems == [], problems
    assert checked >= 10, f"the projection check would be vacuous: {checked} html parts"


def test_the_html_projection_check_fails_on_a_planted_wrong_span(tmp_path: Path) -> None:
    source = GENERATED / "html_gmail_quote"
    payload = sidecar_copy.payload_of(Path(f"{source}.expected.json"))
    payload["facts"]["body.html_spans"]["value"][0][4] += 1  # the html element one longer
    sidecar_copy.write(tmp_path, payload, source=Path(f"{source}.expected.json"))
    from emailextract.evals.labels import load_sidecar

    written = sorted(tmp_path.rglob("*.expected.json"))[0]
    problems = html_span_problems(load_sidecar(written))
    assert any("html_spans" in problem for problem in problems), problems


def test_the_quote_catalogue_fixtures_regenerate_byte_identically() -> None:
    import hashlib

    for name in CATALOGUE:
        path = _fixture_path(name)
        if path.read_bytes() == write_raw_fixtures.FIXTURES.get(name):
            continue
        assert make_fixtures.build_fixture(name) == path.read_bytes(), f"{name} differs"
    # The raw rows match their frozen digest and the raw set.
    sums = {}
    for line in (RAW / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, _, file_name = line.partition("  ")
        sums[file_name] = digest
    for name in CATALOGUE:
        if (RAW / f"{name}.eml").exists():
            assert hashlib.sha256((RAW / f"{name}.eml").read_bytes()).hexdigest() == sums[f"{name}.eml"]
