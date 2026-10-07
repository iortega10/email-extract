"""Turn 1.0c: the fixture census -- every catalogue row names a committed fixture, by family.

The design (`docs/design/email-extraction-design.md`, the Phase 1 paragraph of "Phasing")
names ten fixtures. `docs/design/phase1-fixtures.md` is the catalogue: a row per fixture,
grouped into Family A (headers/date/address), Family B (body/HTML), Family C
(attachments/caps) and the quote catalogue. This test keeps the two in step, scoped by
**family** so the commits that land one family at a time can share it:

* every design fixture must have a catalogue row (a design fixture silently dropped from
  the catalogue fails by name);
* every catalogue row whose family **has landed** must have a committed `.eml` and a
  sidecar beside it (Families A, B and C have all landed, so their rows are all committed);
* every catalogue row whose family has **not** landed is on a frozen **pending** list, and
  a pending row whose fixture file already exists fails by name (a family lands as a whole;
  the family-pending list is now EMPTY, and the quote catalogue is carried by its own
  `PENDING_QUOTE` list until its own increment);
* every committed fixture that is not one of the sixteen Phase 0 fixtures must be a
  catalogue row (a fixture committed without a catalogue row fails by name).

Both checks are proved able to fail on doctored inputs below, so a green run means the
census compared something.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE_PATH = ROOT / "docs" / "design" / "phase1-fixtures.md"
DESIGN_PATH = ROOT / "docs" / "design" / "email-extraction-design.md"
FIXTURES = ROOT / "fixtures"
FIXTURE_DIRS = (FIXTURES / "generated", FIXTURES / "raw", FIXTURES / "time")

#: The sixteen fixtures Phase 0 committed (see `tests/test_fixtures.py`). They predate the
#: Phase 1 catalogue and are deliberately not catalogue rows.
PHASE0_STEMS = frozenset(
    {
        "plain_simple",
        "alternative_text_html",
        "multipart_mixed_wraps_alternative",
        "rfc2047_folded_duplicate_received",
        "attachments_mixed",
        "inline_cid_referenced_and_not",
        "thread_three_refs_chain",
        "preamble_epilogue",
        "bad_charset",
        "truncated_base64",
        "malformed_mime",
        "date_before_hops",
        "received_clock_skew",
        "date_no_zone",
        "date_vs_mtime",
        "future_date_in_text",
    }
)

#: The catalogue rows whose family has NOT been committed yet. This list SHRINKS as each
#: family lands: Families A, B and C are all committed by the three 1.0c commits, so it is
#: **empty** now; the quote catalogue is typed by its own increment (after Turn 1.5) and is
#: carried by PENDING_QUOTE below until then.
PENDING = frozenset()

#: The quote catalogue rows (`docs/design/phase1-fixtures.md`, "The quote catalogue"): typed
#: after Turn 1.5 and owner-reviewed before any quote rule is written. They landed in their own
#: increment, so this list is now **empty**: every one of the 29 rows has a committed fixture
#: and a sidecar (the increment that empties it is the quote catalogue; the owner review is the
#: hard gate before Turn 1.6).
PENDING_QUOTE = frozenset()


def design_phase1_names(text: str) -> list[str]:
    """The fixtures the design's "Phase 1" paragraph names, in order."""
    start = text.index("**Phase 1:")
    end = text.index("**Phase 1b")
    return re.findall(r"`([a-z][a-z0-9_]*)`", text[start:end])


def catalogue_rows(text: str) -> dict[str, str]:
    """`name -> family` for every catalogue row, in catalogue order.

    A row is a table line that opens with a backticked fixture name. The sections are
    bounded so the "NOT v1" table and the topic-6 coverage table (which are not catalogue
    rows) are not read as ones.
    """
    rows: dict[str, str] = {}
    sections = (
        ("## Family A:", "A", None),
        ("## Family B:", "B", None),
        ("## Family C:", "C", None),
        ("## The quote catalogue", "quote", "**NOT v1"),
        ("## Turn 1.12:", "D", None),
    )
    for header, family, stop in sections:
        start = text.index(header)
        if stop is not None:
            end = text.index(stop, start)
        else:
            end = text.index("\n## ", start + 1)
        for name in re.findall(r"^\| `([a-z][a-z0-9_]*)`", text[start:end], re.M):
            rows.setdefault(name, family)
    return rows


def committed_stems() -> set[str]:
    return {path.stem for directory in FIXTURE_DIRS for path in directory.glob("*.eml")}


def sidecar_stems() -> set[str]:
    return {
        path.name.removesuffix(".expected.json")
        for directory in FIXTURE_DIRS
        for path in directory.glob("*.expected.json")
    }


def fixture_exists(name: str) -> bool:
    return any((directory / f"{name}.eml").is_file() for directory in FIXTURE_DIRS)


def census_problems(
    catalogued: dict[str, str],
    pending: frozenset[str],
    committed: set[str],
    sidecars: set[str],
    design_names: list[str],
) -> list[str]:
    """Every way the catalogue and the committed tree can disagree, all at once."""
    problems: list[str] = []
    for name in design_names:
        if name not in catalogued:
            problems.append(f"design fixture {name!r} has no catalogue row")
    for name in catalogued:
        if name in pending:
            if name in committed:
                problems.append(
                    f"catalogue row {name!r} is still pending but its fixture file exists"
                )
            continue
        if name not in committed:
            problems.append(f"catalogue row {name!r} is committed but has no fixture file")
        elif name not in sidecars:
            problems.append(f"catalogue row {name!r} has a fixture but no sidecar")
    for name in sorted(committed - PHASE0_STEMS):
        if name not in catalogued:
            problems.append(f"committed fixture {name!r} is not a catalogue row")
    return problems


def _real_inputs():
    catalogue_text = CATALOGUE_PATH.read_text(encoding="utf-8")
    return (
        catalogue_rows(catalogue_text),
        PENDING | PENDING_QUOTE,
        committed_stems(),
        sidecar_stems(),
        design_phase1_names(DESIGN_PATH.read_text(encoding="utf-8")),
    )


def test_every_design_phase1_fixture_is_in_the_catalogue() -> None:
    catalogued, pending, committed, sidecars, design_names = _real_inputs()
    assert len(design_names) == 10, f"the design names ten Phase 1 fixtures, found {design_names}"
    missing = [name for name in design_names if name not in catalogued]
    assert not missing, f"design fixture(s) dropped from the catalogue: {missing}"
    # The same check must fail when a catalogue row is doctored away.
    doctored = dict(catalogued)
    doctored.pop(design_names[0])
    problems = census_problems(doctored, pending, committed, sidecars, design_names)
    assert any(design_names[0] in problem for problem in problems), problems


def test_every_catalogue_row_has_a_committed_fixture() -> None:
    catalogued, pending, committed, sidecars, design_names = _real_inputs()
    assert catalogued, "the catalogue could not be read"
    assert not (set(catalogued) & PHASE0_STEMS), "a Phase 0 fixture is a catalogue row"
    assert set(catalogued) == set(pending) | (set(catalogued) - set(pending))
    assert census_problems(catalogued, pending, committed, sidecars, design_names) == []
    # Every landed family's rows are committed; only the quote catalogue's are still pending.
    # Families A, B and C are the families this corpus has landed, so none of their rows is
    # pending and all of them exist.
    family_a = {name for name, family in catalogued.items() if family == "A"}
    assert len(family_a) == 30, sorted(family_a)
    assert not (family_a & pending), sorted(family_a & pending)
    assert family_a <= committed and family_a <= sidecars
    family_b = {name for name, family in catalogued.items() if family == "B"}
    assert len(family_b) == 22, sorted(family_b)
    assert not (family_b & pending), sorted(family_b & pending)
    assert family_b <= committed and family_b <= sidecars
    family_c = {name for name, family in catalogued.items() if family == "C"}
    assert len(family_c) == 22, sorted(family_c)
    assert not (family_c & pending), sorted(family_c & pending)
    assert family_c <= committed and family_c <= sidecars
    assert PENDING == frozenset(), "the family-pending list is empty: all three families landed"
    # The quote catalogue landed in its own increment (after Turn 1.5), so PENDING_QUOTE is now
    # empty too and all 29 of its rows are committed with sidecars.
    assert PENDING_QUOTE == frozenset(), "the quote catalogue landed in its own increment"
    family_quote = {name for name, family in catalogued.items() if family == "quote"}
    assert len(family_quote) == 29, sorted(family_quote)
    assert not (family_quote & pending), sorted(family_quote & pending)
    assert family_quote <= committed and family_quote <= sidecars
    # Turn 1.12's header-less fixtures: their own section, all committed with sidecars.
    family_d = {name for name, family in catalogued.items() if family == "D"}
    assert len(family_d) == 7, sorted(family_d)
    assert not (family_d & pending), sorted(family_d & pending)
    assert family_d <= committed and family_d <= sidecars
    # The same check must fail when a committed fixture is missing, by name -- for every family.
    for family in (family_a, family_b, family_c, family_quote, family_d):
        missing = sorted(family)[0]
        problems = census_problems(catalogued, pending, committed - {missing}, sidecars, design_names)
        assert any(missing in problem for problem in problems), (missing, problems)
    # ... and a pending row whose fixture file has already landed: a doctored pending set names a
    # quote-catalogue row that is committed, which the census refuses by name.
    early = sorted(family_quote)[0]
    problems = census_problems(catalogued, frozenset({early}), committed, sidecars, design_names)
    assert any(early in problem for problem in problems), problems
    # ... and a committed fixture that is not a catalogue row fails by name.
    problems = census_problems(catalogued, pending, committed | {"not_a_catalogue_row"}, sidecars, design_names)
    assert any("not_a_catalogue_row" in problem for problem in problems), problems
