"""Turn 1.0c: the fixture census -- every catalogue row names a committed fixture, by family.

The design (`docs/design/email-extraction-design.md`, the Phase 1 paragraph of "Phasing")
names ten fixtures. `docs/design/phase1-fixtures.md` is the catalogue: a row per fixture,
grouped into Family A (headers/date/address), Family B (body/HTML), Family C
(attachments/caps) and the quote catalogue. This test keeps the two in step, scoped by
**family** so the commits that land one family at a time can share it:

* every design fixture must have a catalogue row (a design fixture silently dropped from
  the catalogue fails by name);
* every catalogue row whose family **has landed** must have a committed `.eml` and a
  sidecar beside it;
* every catalogue row whose family has **not** landed is on a frozen **pending** list, and
  a pending row whose fixture file already exists fails by name (a family lands as a whole);
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
#: family lands: Family B's and Family C's rows are committed by the later 1.0c commits and
#: the quote catalogue by its own increment, and each commit removes its names from here.
PENDING = frozenset(
    {
        # Family B: body and HTML (commit 1.0c-B)
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
        # Family C: attachments and caps (commit 1.0c-C)
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
        "cap_deep_nesting",
        "cap_large_part_count",
        "cap_enormous_header_block",
        "cap_encoded_word_bomb",
        "cap_very_long_base64_run",
        "attach_remote_image_only",
        # The quote catalogue (typed after Turn 1.5)
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
    }
)


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
        PENDING,
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
    # A landed family's rows are committed; a later family's are not. Family A is the
    # family this commit lands, so none of its rows is pending and all of them exist.
    family_a = {name for name, family in catalogued.items() if family == "A"}
    assert len(family_a) == 30, sorted(family_a)
    assert not (family_a & pending), sorted(family_a & pending)
    assert family_a <= committed and family_a <= sidecars
    # The same check must fail when a committed fixture is missing, by name.
    problems = census_problems(catalogued, pending, committed - {sorted(family_a)[0]}, sidecars, design_names)
    assert any(sorted(family_a)[0] in problem for problem in problems), problems
    # ... and when a pending row's fixture file has landed early.
    early = sorted(pending)[0]
    problems = census_problems(catalogued, pending, committed | {early}, sidecars, design_names)
    assert any(early in problem for problem in problems), problems
