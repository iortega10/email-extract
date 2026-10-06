"""Turn 1.6: the TEXT half of the resolution rule -- ordinals, levels and the disagreement.

The rules under test are decision 2 (signed Q2/Q3): **only** ``kind = quote`` boundaries advance
the ordinal, in document order within the view; the per-view level is the highest of any
boundary's ordinal and the deepest per-line ``>`` depth, and it carries the ``rule_id`` of the
boundary that determined it; ``view.quote_level_disagreement`` is recorded iff the view has a
prefix line and a structural quote ordinal and the two resolved ranks differ, so an all-zero
depth beside a fired structural rule is a **normal state**. A view with nothing to record --
no boundary of any kind and no prefix line -- has no ``body.view_levels`` row at all.

The last test pins the **label-blind** evidence format: the comparison names the fixture, the
fact, the view, the row, the column and the MEASURED value, and never the labelled one
(independence rule 3 of the turn: running L1 must not reveal a label).
"""

from __future__ import annotations

from emailextract.container import EmlContainer, memory_bytes
from emailextract.evals.l1 import _quote_rows_compare
from emailextract.quote import resolve, text_rules
from emailextract.walk import walk


def _walk(body: bytes):
    message = (
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n" + body
    )
    result = walk(EmlContainer(memory_bytes(message)))
    return message, result


def _rows(body: bytes):
    message, result = _walk(body)
    return resolve.quote_boundary_rows(message, result)


def _levels(body: bytes):
    message, result = _walk(body)
    return resolve.view_level_rows(message, result)


def test_quote_rows_carry_per_line_depths_and_ordinals_in_document_order() -> None:
    """Rows are in span order, each carrying its own per-line depth list and its own ordinal."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"> first quoted\r\n"
        b">> deeper\r\n"
        b"\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender wrote:\r\n"
        b"\r\n"
        b">> the second block\r\n"
    )
    rows = _rows(body)
    assert [row[2] for row in rows] == ["gt_family", "on_wrote_en", "gt_family"], rows
    assert [row[4] for row in rows] == [1, 2, 3], f"document order decides the ordinals: {rows}"
    assert [row[5] for row in rows] == [[1, 2], [0], [2]], (
        f"one depth per covered line, per boundary: {[row[5] for row in rows]}"
    )
    assert [row[3] for row in rows] == ["quote"] * 3, rows
    for index, row in enumerate(rows):
        assert row[6] >= 0 and row[7] > 0, f"row {index}: spans are inside the view"
        assert len(row[5]) > 0, f"row {index}: a quote boundary covers at least one line"


def test_the_view_level_is_the_higher_of_the_ordinal_and_the_deepest_depth() -> None:
    """``level = ordinal`` where a structural quote rule fired, else the deepest depth."""
    deep = b"Hi Ben.\r\n\r\n> one\r\n>> two\r\n>>> three\r\n"
    assert _levels(deep) == [["1", "plain", 3, "gt_family"]], _levels(deep)

    structural = (
        b"Hi Ben.\r\n\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"\r\nThe earlier note body.\r\n"
    )
    assert _levels(structural) == [["1", "plain", 1, "outlook_flat_en"]], _levels(structural)

    both = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender wrote:\r\n"
        b"\r\n"
        b"> the earlier line\r\n"
    )
    rows = _rows(both)
    assert [row[4] for row in rows] == [1, 2], "both families fire and both advance the ordinal"
    assert _levels(both) == [["1", "plain", 2, "on_wrote_en"]], _levels(both)


def test_a_view_with_no_quote_boundary_and_no_prefix_line_has_no_level_row() -> None:
    """Nothing fires (no boundary of any kind, no ``>`` line) -- so nothing is recorded."""
    assert _rows(b"Hi Ben.\r\n\r\nJust a plain note.\r\n") == []
    assert _levels(b"Hi Ben.\r\n\r\nJust a plain note.\r\n") == []
    message, result = _walk(b"Hi Ben.\r\n\r\nJust a plain note.\r\n")
    _message, scan, _view = (message, resolve.scan_views(message, result)[0], None)
    assert scan.scan.no_boundary is True, "the absence answer is the only thing recorded here"
    assert resolve.quote_boundary_rows(message, result) == []


def test_the_disagreement_predicate_is_false_beside_an_all_zero_depth() -> None:
    """The pure predicate: an all-zero depth beside a structural rule is a normal state."""
    assert resolve.disagreement(1, 0) is False
    assert resolve.disagreement(0, 3) is False, "depth alone is one family: nothing disagrees"
    assert resolve.disagreement(2, 2) is False
    assert resolve.disagreement(2, 1) is True, "ordinal 2 against depth 1: the ranks differ"

    flat = (
        b"Hi Ben.\r\n\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"\r\nThe earlier note body.\r\n"
    )
    message, result = _walk(flat)
    _message, view = message, resolve.scan_views(message, result)[0]
    assert view.disagreement is False, "the plain alternative carries no `>` at all (D3)"
    assert resolve.gap_pairs(message, result) == [], (
        "an all-zero depth beside the structural rule records no gap"
    )


def test_the_label_blind_evidence_names_the_row_and_column_only() -> None:
    """A mismatch names the view, the row index, the column's NAME and the measured value."""
    compare = _quote_rows_compare("body.view_levels")
    labelled = [["1", "plain", 1, "on_wrote_en"]]
    measured = [["1", "plain", 2, "gt_family"]]
    agrees, detail = compare(labelled, measured)
    assert agrees is False
    assert detail == (
        "view 'plain' row 0: column 'level' -- measured 2 "
        "(the labelled value is never printed: independence rule 3)"
    ), detail
    assert "on_wrote_en" not in detail, "the labelled value must never appear in the evidence"
    assert "1" not in detail.split("--")[1], "and not beside the measured value either"

    agrees, detail = compare(labelled, labelled)
    assert agrees is True and detail is None

    # Turn 1.7 measures the html view too, so a labelled html row is compared like any other:
    # with no measured html row the count differs, and with a matching one it agrees.
    with_html = [["1", "plain", 1, "on_wrote_en"], ["1.1", "html", 1, "gmail_quote"]]
    agrees, detail = compare(with_html, [["1", "plain", 1, "on_wrote_en"]])
    assert agrees is False and "row count" in detail, detail
    assert "'html'" in detail, detail
    agrees, detail = compare(
        with_html, [["1", "plain", 1, "on_wrote_en"], ["1.1", "html", 1, "gmail_quote"]]
    )
    assert agrees is True and detail is None

    # A view neither family measures is still reported by name, never silently dropped.
    later = [["1.2", "calendar", 1, "gmail_quote"]]
    agrees, detail = compare(later, [])
    assert agrees is True, "an unmeasured view's row is a later turn's, reported by name"
    assert detail == "1 labelled row(s) name a view of a later turn (calendar, not compared)"

    agrees, detail = compare(labelled, [])
    assert agrees is False and "row count" in detail, detail

    agrees, detail = compare(labelled, [["1", "plain", 2, "gt_family"], ["1", "plain", 2, "x"]])
    assert agrees is False and "row count" in detail, detail

    assert text_rules.GAP_NO_BOUNDARY_FOUND == "body.no_boundary_found"


def test_the_resolution_rule_is_the_first_structural_quote_boundary() -> None:
    """A structural quote rule beats ``gt_family`` even when the ``>`` run comes first (37)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"> the first run\r\n"
        b"\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
    )
    rows = _rows(body)
    assert [row[2] for row in rows] == ["gt_family", "outlook_flat_en"], rows
    assert _levels(body) == [["1", "plain", 2, "outlook_flat_en"]], _levels(body)


def test_the_first_structural_quote_boundary_wins_over_a_later_one() -> None:
    """Two structural quotes: the LEVEL carries the first one's rule, in document order (37)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender <ada@example.test> wrote:\r\n"
        b"\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
    )
    rows = _rows(body)
    assert [row[2] for row in rows] == ["on_wrote_en", "outlook_flat_en"], rows
    assert _levels(body) == [["1", "plain", 2, "on_wrote_en"]], _levels(body)


def test_a_forward_only_view_has_a_level_row_at_zero_with_the_banners_rule() -> None:
    """Any recognised boundary gives a row; a forward-only view is level 0 (38)."""
    cases = (
        (b"Hi Ben.\r\n\r\nBegin forwarded message:\r\nThe forwarded note.\r\n", "forward_banner"),
        (
            b"Hi Ben.\r\n\r\n-----Original Message-----\r\nThe earlier text.\r\n",
            "original_message_dashes",
        ),
        (b"Hi Ben.\r\n\r\n" + b"_" * 30 + b"\r\nAda\r\n", "list_footer_underscores"),
        (b"Hi Ben.\r\n\r\n-- \r\nAda Sender\r\n", "dash_dash_space"),
    )
    for body, rule in cases:
        assert _levels(body) == [["1", "plain", 0, rule]], (rule, _levels(body))
