"""Turn 1.6: the TEXT family of the quote rules and the text half of the resolution rule.

Every message here is **built inline** from the design rules -- never copied from a catalogue
fixture or a sidecar. The rules under test are the signed decisions of the turn (build-spec
decision 3 for the families, Q1/Q5/Q7 for the spans, decision 2 for ordinals and levels):

* ``gt_family``: the ``>` ``-family depth **per physical line**, never a per-view scalar, with
  SPACE/TAB as the only separators (NBSP is text);
* ``on_wrote_en``: the single-line attribution and the exact **two**-line hard-wrap window
  (three lines are not joined), the span carrying the quoted block that follows;
* ``outlook_flat_en|de|fr``: a maximal run of >= 2 adjacent labels from **one** language, in
  canonical order as a subsequence, with both date tokens per language and an NBSP separator
  accepted after NFC and only for matching;
* ``forward_banner`` / ``original_message_dashes``: kind ``forward`` at level 0, ordinal 0,
  and no suppression of an inner block;
* ``dash_dash_space``: the exact ``-- `` line, a candidate only, spanning to the part's end;
* ``list_footer_underscores`` / ``list_footer_subscribed``: detection only;
* the absence answers: bottom-posting is **legal** (one quote run), only a non-contiguous
  alternation is ``body.inline_reply_interleaved``, and a label-shaped unknown-language block
  after a boundary-looking line is ``body.i18n_reply_marker``.

Each failure names the rule, the line and the closed reason, and the scanner is asserted to be
single-pass and linear with the deterministic :data:`emailextract.quote.text_rules.WORK`
counter (never a clock).
"""

from __future__ import annotations

import dataclasses
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402

from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.evals import l1  # noqa: E402
from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars  # noqa: E402
from emailextract.quote import i18n, resolve, text_rules  # noqa: E402
from emailextract.walk import iter_lines, walk  # noqa: E402

FIXTURES = ROOT / "fixtures"

HEAD = b"From: Ada Sender <ada@example.test>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"


def _message(body: bytes, content_type: bytes = b"text/plain; charset=utf-8") -> bytes:
    """A minimal one-part message: a Content-Type, then ``body`` exactly as typed."""
    head = b"From: Ada Sender <ada@example.test>\r\n"
    if content_type is not None:
        head += b"Content-Type: " + content_type + b"\r\n"
    return head + b"\r\n" + body


def _walk(body: bytes, content_type: bytes = b"text/plain; charset=utf-8"):
    message = _message(body, content_type)
    result = walk(EmlContainer(memory_bytes(message)))
    assert result.parts, "the inline message has no part"
    return message, result


def _scan(body: bytes, content_type: bytes = b"text/plain; charset=utf-8"):
    """``(message, scan, view)`` for the one plain view of an inline body."""
    message, result = _walk(body, content_type)
    views = resolve.scan_views(message, result)
    assert len(views) == 1, f"expected one plain view, got {len(views)}"
    return message, views[0].scan, views[0]


def _rows(body: bytes, content_type: bytes = b"text/plain; charset=utf-8"):
    message, result = _walk(body, content_type)
    return resolve.quote_boundary_rows(message, result)


def _rhs(body: bytes, content_type: bytes = b"text/plain; charset=utf-8"):
    return [row[2:] for row in _rows(body, content_type)]


def _levels(body: bytes, content_type: bytes = b"text/plain; charset=utf-8"):
    message, result = _walk(body, content_type)
    return resolve.view_level_rows(message, result)


# -------------------------------------------------------------------- gt_family


def test_gt_family_prefix_depth_is_per_line() -> None:
    """Depth is per physical line over the run, one entry per covered line (never a scalar)."""
    body = b"Hi Ben.\r\n\r\n> one\r\n>> two\r\n> \t> three\r\n>>\r\n\r\nThe new bottom line.\r\n"
    rows = _rhs(body)
    assert len(rows) == 1, f"the four `>` lines are ONE run, got {rows}"
    rule, kind, ordinal, depths, offset, length = rows[0]
    assert (rule, kind, ordinal) == ("gt_family", "quote", 1), rows[0]
    assert depths == [1, 2, 2, 2], f"gt_family depths must be per line, got {depths}"
    message, _result = _walk(body)
    text = resolve.scan_views(message, _result)[0].part_text.text
    assert message  # the message bytes are the judge for the span below
    assert text[offset : offset + length] == "> one\r\n>> two\r\n> \t> three\r\n>>", (
        "the run ends mid-message, so its span stops at the last line's content"
    )


def test_gt_family_span_includes_the_final_terminator_at_the_part_end() -> None:
    """A run that reaches the end of the part keeps the final line terminator (decision (a))."""
    body = b"Hi Ben.\r\n\r\n> the tail\r\n"
    rows = _rhs(body)
    assert len(rows) == 1, rows
    offset, length = rows[0][-2:]
    message, result = _walk(body)
    text = resolve.scan_views(message, result)[0].part_text.text
    assert offset + length == len(text), (
        f"the run reaches the part end, so its span ends at {len(text)}, got {offset + length}"
    )
    assert text[offset:] == "> the tail\r\n"


def test_the_lone_cr_line_model_is_the_one_splitter() -> None:
    """The splitter is ``walk.iter_lines``: a lone CR is a terminator, exactly as the walker has it."""
    body = b"Hi.\r\n\r\n> first\r> second\r\nThe tail.\r\n"
    message, scan, view = _scan(body)
    payload = message[message.index(b"\r\n\r\n") + 4 :]
    expected = [start for start, _content, _term in iter_lines(payload, 0, len(payload))]
    assert [line.start for line in scan.lines] == expected, (
        "the splitter's line starts must equal the one line model's"
    )
    assert [line.text for line in scan.lines] == [
        "Hi.",
        "",
        "> first",
        "> second",
        "The tail.",
    ], [line.text for line in scan.lines]
    assert scan.boundaries[0].prefix_depth == (1, 1), scan.boundaries[0].prefix_depth
    assert view.part_text.text.count("\r") == 5, "CRLF and the two lone CRs are five code points"


# ------------------------------------------------------------------ on_wrote_en


def test_on_wrote_en_fires_at_level_one() -> None:
    """A one-line attribution with no quoted block: ordinal 1, level 1, its own rule id."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender <ada@example.test> wrote:\r\n\r\n"
        b"Thanks for the note.\r\n"
    )
    rows = _rhs(body)
    assert len(rows) == 1, f"one attribution, no `>` block, so one boundary: {rows}"
    rule, kind, ordinal, depths, _offset, _length = rows[0]
    assert (rule, kind, ordinal) == ("on_wrote_en", "quote", 1), rows[0]
    assert depths == [0], f"the attribution line carries no prefix depth: {depths}"
    assert _levels(body) == [["1", "plain", 1, "on_wrote_en"]], _levels(body)


def test_a_hard_wrapped_attribution_is_a_two_line_window_and_three_lines_are_not() -> None:
    """The window is exactly two physical lines; a three-line wrap is new text at level 0.

    The attributed block that follows is **absorbed** (decision 36): the ``>`` run inside the
    attribution's span is part of that boundary, not a second ``gt_family`` row.
    """
    two = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender\r\n"
        b"<ada@example.test> wrote:\r\n"
        b"> the earlier line\r\n"
    )
    rows = _rhs(two)
    assert [row[0] for row in rows] == ["on_wrote_en"], rows
    assert rows[0][3] == [0, 0, 1], (
        f"the attribution's span carries the quoted block that follows: {rows[0]}"
    )

    three = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender\r\n"
        b"<ada@example.test>\r\n"
        b"wrote:\r\n"
        b"the new bottom line.\r\n"
    )
    assert _rows(three) == [], "three wrapped lines are never joined into an attribution"


def test_the_scanner_is_single_pass_and_linear_in_the_line_count() -> None:
    """An exact step count for a fixed input, and less than a doubling for a doubled input."""
    small_body = b"".join(b"> line %d\r\n" % index for index in range(1000))
    large_body = b"".join(b"> line %d\r\n" % index for index in range(2000))
    small_message, small_result = _walk(small_body)
    large_message, large_result = _walk(large_body)

    text_rules.WORK.reset()
    resolve.scan_views(small_message, small_result)
    small_steps = text_rules.WORK.count()
    text_rules.WORK.reset()
    resolve.scan_views(large_message, large_result)
    large_steps = text_rules.WORK.count()

    assert small_steps > 0, "the counter must see the scan"
    assert large_steps > small_steps, (small_steps, large_steps)
    ratio = large_steps / small_steps
    assert ratio < 2.2, f"the scan is not linear: {small_steps} -> {large_steps} (ratio {ratio})"


def test_the_scan_is_deterministic_on_a_hostile_single_line() -> None:
    """A giant single line with no terminator: no exception, identical rows twice, bounded work."""
    hostile = b">" * 200_000 + b" tail"
    started = time.monotonic()
    first = _rhs(hostile)
    second = _rhs(hostile)
    elapsed = time.monotonic() - started
    assert first == second, "the scan must be a function of the bytes"
    assert elapsed < 20, f"the hostile line took {elapsed:.1f}s"
    assert first[0][0] == "gt_family" and first[0][3] == [200_000], first[0][3][:1]


# ---------------------------------------------------------------- outlook_flat_*


def test_the_outlook_flat_block_needs_two_adjacent_labels() -> None:
    """One label line is not a block, and a non-label line breaks adjacency."""
    single = b"Hi Ben.\r\n\r\nFrom: Ada Sender <ada@example.test>\r\n\r\n"
    assert _rows(single) == [], "a single label line is NOT a block"

    broken = b"Hi Ben.\r\n\r\nFrom: Ada Sender <ada@example.test>\r\n\r\nSent: now\r\n"
    assert _rows(broken) == [], "a blank line breaks the run of adjacent labels"

    block = (
        b"Hi Ben.\r\n\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"\r\nThe earlier note body.\r\n"
    )
    rows = _rhs(block)
    assert len(rows) == 1, f"two adjacent labels are one block: {rows}"
    assert rows[0][0] == "outlook_flat_en" and rows[0][1:3] == ["quote", 1], rows[0]
    assert rows[0][3] == [0, 0, 0, 0], f"one depth per covered line: {rows[0][3]}"


def test_an_outlook_block_span_runs_to_the_end_of_the_part() -> None:
    """The signed Q1 span: the label block plus the quoted content, to the part's end."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"Subject: the earlier note\r\n"
        b"\r\nThe earlier note body.\r\n"
    )
    rows = _rhs(body)
    assert len(rows) == 1, rows
    offset, length = rows[0][-2:]
    message, result = _walk(body)
    text = resolve.scan_views(message, result)[0].part_text.text
    assert offset + length == len(text), (offset, length, len(text))
    assert text[offset:].startswith("From: Ada Sender"), text[offset:]


def test_the_outlook_language_is_per_block() -> None:
    """Each language's own heads fire that language's rule; a mixed run matches none."""
    english = b"From: a\r\nSent: b\r\n"
    german = "Von: a\r\nGesendet: b\r\n".encode("utf-8")
    french = "De\u00a0: a\r\nEnvoy\u00e9\u00a0: b\r\n".encode("utf-8")
    mixed = "From: a\r\nVon: b\r\n".encode("utf-8")

    assert [row[0] for row in _rhs(english)] == ["outlook_flat_en"]
    assert [row[0] for row in _rhs(german)] == ["outlook_flat_de"]
    assert [row[0] for row in _rhs(french)] == ["outlook_flat_fr"]
    assert _rows(mixed) == [], "a run never mixes languages: no block, and no absence either"


def test_the_outlook_date_slot_accepts_both_tokens() -> None:
    """``Sent:`` and ``Date:`` fill the same slot; so do the German and French pairs."""
    for date_line in (b"Sent: b", b"Date: b"):
        rows = _rhs(b"From: a\r\n" + date_line + b"\r\n")
        assert [row[0] for row in rows] == ["outlook_flat_en"], rows
    for date_line in ("Gesendet: b", "Datum: b"):
        rows = _rhs(("Von: a\r\n" + date_line + "\r\n").encode("utf-8"))
        assert [row[0] for row in rows] == ["outlook_flat_de"], rows
    for date_line in ("Envoy\u00e9 : b", "Date : b"):
        rows = _rhs(("De\u00a0: a\r\n" + date_line + "\r\n").encode("utf-8"))
        assert [row[0] for row in rows] == ["outlook_flat_fr"], rows


def test_a_nbsp_separator_is_accepted_after_nfc() -> None:
    """NBSP separates a label from its colon (matching only); it is NOT a ``>`` separator."""
    french = "De\u00a0: a\r\nEnvoy\u00e9\u00a0: b\r\n".encode("utf-8")
    assert [row[0] for row in _rhs(french)] == ["outlook_flat_fr"]

    decomposed = "De\u00a0: a\r\nEnvoye\u0301\u00a0: b\r\n".encode("utf-8")
    assert [row[0] for row in _rhs(decomposed)] == [
        "outlook_flat_fr"
    ], "NFC makes the decomposed head match, and the stored text is untouched"

    nbsp_prefix = "> \u00a0> text\r\n".encode("utf-8")
    rows = _rhs(nbsp_prefix)
    assert rows[0][3] == [1], (
        f"NBSP is not a prefix separator, so the depth is 1 and the rest is text: {rows[0]}"
    )


# ------------------------------------------------------- forward and signatures


def test_begin_forwarded_message_is_a_forward_banner_at_level_zero() -> None:
    """Kind ``forward``, ordinal 0, and a level row at 0 carrying the banner's rule (decision 38)."""
    body = b"Hi Ben.\r\n\r\nBegin forwarded message:\r\n\r\nThe forwarded note.\r\n"
    rows = _rhs(body)
    assert len(rows) == 1, rows
    assert rows[0][0] == "forward_banner" and rows[0][1] == "forward" and rows[0][2] == 0, rows[0]
    assert _levels(body) == [["1", "plain", 0, "forward_banner"]], (
        f"a forward banner alone is level 0 and still has a level row: {_levels(body)}"
    )


def test_original_message_dashes_is_a_named_shape() -> None:
    """Exactly ``-----Original Message-----``; a different dash count is not the shape."""
    body = b"Hi Ben.\r\n\r\n-----Original Message-----\r\nFrom: Ada Sender\r\n\r\nThe note.\r\n"
    rows = _rhs(body)
    assert [row[:3] for row in rows] == [["original_message_dashes", "forward", 0]], rows
    assert _rhs(b"Hi Ben.\r\n\r\n----Original Message----\r\nx\r\n") == [], (
        "only the named dash shape is a boundary (the dashes count tolerance is the table's)"
    )


def test_a_forward_banner_is_not_suppressed_by_an_inner_block() -> None:
    """Signed Q4: the Outlook flat block inside a forwarded message is still a ``quote``."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"Begin forwarded message:\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"Subject: FYI\r\n"
        b"\r\nThe forwarded note.\r\n"
    )
    rows = _rhs(body)
    kinds = {row[1]: row[2] for row in rows}
    assert kinds == {"forward": 0, "quote": 1}, rows
    assert _levels(body) == [["1", "plain", 1, "outlook_flat_en"]], _levels(body)


def test_the_dash_dash_space_signature_is_a_candidate_only() -> None:
    """Exactly ``-- `` (dash dash SPACE): kind ``signature``, ordinal 0, to the part's end."""
    body = b"Hi Ben.\r\n\r\n-- \r\nAda Sender\r\nada@example.test\r\n"
    rows = _rhs(body)
    assert len(rows) == 1, rows
    assert rows[0][0] == "dash_dash_space" and rows[0][1] == "signature" and rows[0][2] == 0, rows[0]
    offset, length = rows[0][-2:]
    message, result = _walk(body)
    text = resolve.scan_views(message, result)[0].part_text.text
    assert text[offset : offset + length] == "-- \r\nAda Sender\r\nada@example.test\r\n", (
        "the signature span runs from the marker line through the end of the part"
    )
    assert _rhs(b"Hi Ben.\r\n\r\n- \r\nAda\r\n") == [], "one dash is not the RFC 3676 separator"
    assert _rhs(b"Hi Ben.\r\n\r\n-- x\r\nAda\r\n") == [], "``-- x`` is not ``-- ``"


def test_a_list_footer_underscore_run_is_detected() -> None:
    """30 ``_`` on a line is a ``list_footer``; 29 is not. The subscribed sentence too."""
    hit = b"Hi Ben.\r\n\r\n" + b"_" * 30 + b"\r\nAda\r\n"
    rows = _rhs(hit)
    assert [row[:2] for row in rows] == [["list_footer_underscores", "list_footer"]], rows
    assert rows[0][2] == 0, "a list footer carries ordinal 0"
    assert _rhs(b"Hi Ben.\r\n\r\n" + b"_" * 29 + b"\r\nAda\r\n") == [], "29 is under the run"

    subscribed = (
        b"Hi Ben.\r\n\r\n"
        b"You received this message because you are subscribed to the list.\r\n"
    )
    rows = _rhs(subscribed)
    assert [row[:2] for row in rows] == [["list_footer_subscribed", "list_footer"]], rows


# ------------------------------------------------------- absence and interleaving


def test_bottom_posting_is_legal_not_a_gap() -> None:
    """Quoted lines first, the answer after: ONE run, and no gap of any kind."""
    body = b"> The earlier question.\r\n\r\nMy answer to it.\r\n"
    message, scan, _view = _scan(body)
    assert scan.quote_runs == 1, "a bottom-posted reply has exactly one quote run"
    assert scan.interleaved is False
    assert scan.no_boundary is False
    assert resolve.gap_pairs(message, _walk(body)[1]) == [], resolve.gap_pairs(message, _walk(body)[1])
    assert _levels(body) == [["1", "plain", 1, "gt_family"]], _levels(body)


def test_a_non_contiguous_alternation_is_inline_reply_interleaved() -> None:
    """Two separate runs separated by real text: the gap, never on bottom-posting."""
    body = (
        b"My answers are inline.\r\n\r\n"
        b"> first question\r\n\r\nMy first answer.\r\n\r\n"
        b"> second question\r\n\r\nMy second answer.\r\n"
    )
    message, scan, _view = _scan(body)
    assert scan.quote_runs == 2, scan.quote_runs
    assert scan.interleaved is True
    # Both quoted runs are depth 1 but carry ordinals 1 and 2, so the two evidence families
    # resolve to different ranks and the decision-2 predicate records the disagreement as well
    # (reported as a finding of this turn: the literal per-view reading of the predicate).
    assert resolve.gap_pairs(message, _walk(body)[1]) == [
        ("body.inline_reply_interleaved", "1"),
        ("view.quote_level_disagreement", "1"),
    ], resolve.gap_pairs(message, _walk(body)[1])
    assert [row[2] for row in _rhs(body)] == [1, 2], "each run advances the ordinal in turn"


def test_an_unknown_language_label_block_is_the_i18n_gap() -> None:
    """A label-shaped run in no named language, after a boundary-looking line, is the gap."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"Dne 4.3.2025 napsal Ada Sender:\r\n"
        b"Od: Ada Sender\r\nKomu: Ben Receiver\r\nPredmet: the earlier note\r\n"
        b"\r\nThe earlier text.\r\n"
    )
    message, scan, _view = _scan(body)
    assert scan.i18n_line == 3, f"the gap is keyed on the label run's first line: {scan.i18n_line}"
    assert resolve.gap_pairs(message, _walk(body)[1]) == [
        ("body.i18n_reply_marker", "1")
    ], resolve.gap_pairs(message, _walk(body)[1])
    assert _rows(body) == [], "a run in no named language is never a block"

    english = (
        b"Hi Ben.\r\n\r\n"
        b"Begin forwarded message:\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"Subject: FYI\r\n"
    )
    message, scan, _view = _scan(english)
    assert scan.i18n_line is None, "a named-language block is a block, never the i18n gap"


def test_only_quote_boundaries_advance_the_ordinal() -> None:
    """A signature and a forward carry 0 while the quote boundaries rank 1, 2, ..."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"Begin forwarded message:\r\n" b"The forwarded note.\r\n\r\n"
        b"> first quoted\r\n\r\n"
        b"> second quoted\r\n\r\n"
        b"-- \r\nAda Sender\r\n"
    )
    rows = _rows(body)
    assert [row[3] for row in rows] == ["forward", "quote", "quote", "signature"], rows
    assert [row[4] for row in rows] == [0, 1, 2, 0], (
        f"only quotes advance, in document order: {rows}"
    )
    assert all(row[4] == 0 for row in rows if row[3] != "quote"), rows


# ------------------------------------------- decisions 33-36: spans and absorption


def test_the_line_model_has_no_phantom_trailing_line() -> None:
    """A body that ends in a terminator is N physical lines, never N + 1 (decision 33)."""
    body = b"Hi Ben.\r\n> one\r\n> two\r\n"
    _message, scan, _view = _scan(body)
    assert [line.text for line in scan.lines] == ["Hi Ben.", "> one", "> two"], [
        line.text for line in scan.lines
    ]
    assert scan.boundaries[0].prefix_depth == (1, 1), scan.boundaries[0].prefix_depth


def test_an_attribution_span_carries_the_unprefixed_block_that_follows() -> None:
    """The attribution spans the contiguous non-blank block after it (decision 35)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender <ada@example.test> wrote:\r\n"
        b"An unprefixed quoted line.\r\n"
    )
    rows = _rhs(body)
    assert [row[0] for row in rows] == ["on_wrote_en"], rows
    assert rows[0][3] == [0, 0], f"the block after the attribution is covered: {rows[0]}"
    message, result = _walk(body)
    text = resolve.scan_views(message, result)[0].part_text.text
    offset, length = rows[0][-2:]
    assert text[offset : offset + length] == (
        "On Mon, 3 Mar 2025 at 09:15, Ada Sender <ada@example.test> wrote:\r\n"
        "An unprefixed quoted line.\r\n"
    ), "the span reaches the end of the part, terminator included"


def test_a_gt_run_inside_an_attribution_is_one_boundary_with_recorded_depths() -> None:
    """A `>` run inside an attribution's span is part of it: one quote, one ordinal (36)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender <ada@example.test> wrote:\r\n"
        b"> quoted one\r\n"
        b">> quoted two\r\n"
    )
    rows = _rhs(body)
    assert [row[0] for row in rows] == ["on_wrote_en"], rows
    assert rows[0][1:3] == ["quote", 1], rows[0]
    assert rows[0][3] == [0, 1, 2], f"the absorbing boundary records the run's depths: {rows[0]}"


def test_a_blank_line_after_an_attribution_leaves_the_gt_run_its_own_boundary() -> None:
    """A blank line directly after the attribution ends its span there (decision 35)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"On Mon, 3 Mar 2025 at 09:15, Ada Sender <ada@example.test> wrote:\r\n"
        b"\r\n"
        b"> the quoted line\r\n"
    )
    rows = _rhs(body)
    assert [row[0] for row in rows] == ["on_wrote_en", "gt_family"], rows
    assert rows[0][3] == [0], f"the attribution alone: {rows[0]}"
    assert rows[1][3] == [1], f"the run after the blank is its own boundary: {rows[1]}"
    message, result = _walk(body)
    text = resolve.scan_views(message, result)[0].part_text.text
    offset, length = rows[0][-2:]
    assert text[offset : offset + length].endswith("wrote:"), (
        "the span ends at the attribution's own line, with no terminator and no blank"
    )


def test_a_flat_block_stops_before_a_later_forward_banner() -> None:
    """A flat block's extent ends before the next boundary of any kind (decision 35)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"\r\n"
        b"Begin forwarded message:\r\n"
        b"The forwarded note.\r\n"
    )
    rows = _rhs(body)
    assert [row[0] for row in rows] == ["outlook_flat_en", "forward_banner"], rows
    assert rows[0][3] == [0, 0], f"the flat block stops before the banner: {rows[0]}"
    assert rows[1][3] == [0, 0], f"the banner runs to the end of the part: {rows[1]}"


def test_a_forward_banner_nests_a_flat_block_and_covers_every_line_to_the_end() -> None:
    """A flat block inside a forward span is still found; both run to the end (28, 39)."""
    body = (
        b"Hi Ben.\r\n\r\n"
        b"Begin forwarded message:\r\n"
        b"From: Ada Sender <ada@example.test>\r\n"
        b"Sent: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
        b"\r\n"
        b"The forwarded note.\r\n"
    )
    rows = _rhs(body)
    kinds = {row[0]: row for row in rows}
    assert set(kinds) == {"forward_banner", "outlook_flat_en"}, rows
    assert kinds["forward_banner"][3] == [0, 0, 0, 0, 0], (
        f"the banner's depths cover every line through the end: {kinds['forward_banner']}"
    )
    assert kinds["outlook_flat_en"][3] == [0, 0, 0, 0], (
        f"the nested flat block keeps its own extent: {kinds['outlook_flat_en']}"
    )
    assert kinds["outlook_flat_en"][2] == 1, "the flat block is the view's one quote ordinal"


def test_a_span_stopping_before_a_blank_line_ends_at_the_last_content_line() -> None:
    """A span that ends before a blank line covers no terminator and no trailing blank (34)."""
    body = b"> one\r\n> two\r\n\r\nAfter it.\r\n"
    rows = _rhs(body)
    assert rows[0][3] == [1, 1], rows[0]
    message, result = _walk(body)
    text = resolve.scan_views(message, result)[0].part_text.text
    offset, length = rows[0][-2:]
    assert text[offset : offset + length] == "> one\r\n> two", (
        "the run ends at its last content line"
    )
    assert text[offset : offset + length] != "> one\r\n> two\r\n\r\n", (
        "and never covers the blank line that follows"
    )


# ------------------------------------------------------------- determinism (item 8d)

#: sha256 of the JSON of ``{stem: [quote_boundary_rows, view_level_rows, gap_pairs]}`` over the
#: 126 committed fixtures under the pinned corpus, with ``sort_keys=True`` and ``ensure_ascii``
#: False. NFC and ``str.lower()`` depend on the interpreter's Unicode database (16.0.0 on
#: CPython 3.14.3, 14.0.0 on 3.11.15, both recorded in ``docs/design/phase1-empirical.md``), so
#: this digest is the check that no rule of this turn moves with it: it must be **identical**
#: on both interpreters, and it is recorded in that document with the command that produced it.
#: Turn 1.12 re-recorded it: ``QUOTE_RULES_VERSION`` moved 4 -> 5 (a header-less part is
#: ``text/plain`` by RFC 2045 5.2 and now gets its quote analysis) and the seven header-less
#: fixtures joined the corpus.
QUOTE_ROWS_DIGEST = "f497828f01a04a3711fc0a9d459423e5f6fee7f43cb7e5b611c52edb7282a5b7"


def test_the_quote_rows_are_identical_on_both_interpreters() -> None:
    """The whole corpus's quote output has one digest, so no rule moves with the Unicode data."""
    import hashlib
    import json

    from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars

    rows: dict[str, list[object]] = {}
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        rows[stem] = [
            resolve.quote_boundary_rows(raw, result),
            resolve.view_level_rows(raw, result),
            [[gap, locator] for gap, locator in resolve.gap_pairs(raw, result)],
        ]
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
    assert len(rows) == 126, len(rows)
    digest = hashlib.sha256(blob).hexdigest()
    assert digest == QUOTE_ROWS_DIGEST, (
        f"the quote output moved: {digest} != {QUOTE_ROWS_DIGEST}; if a rule changed on purpose, "
        "record the new digest in docs/design/phase1-empirical.md and bump QUOTE_RULES_VERSION"
    )


# ============================================ item 7a: the mutation catalogue


def _patch(monkeypatch, name, wrapper, flags, module=text_rules):
    """Replace ``module.<name>`` with a wrapper that counts its own calls.

    The anti-vacuity triple: ``monkeypatch.setattr`` raises when the symbol does not exist, the
    wrapper proves the patch was **reached**, and the caller asserts the observation differs
    from the baseline.
    """
    real = getattr(module, name)

    def counted(*args: Any, **kwargs: Any) -> Any:
        flags["reached"] += 1
        return wrapper(real, *args, **kwargs)

    monkeypatch.setattr(module, name, counted)
    return real


@dataclasses.dataclass(frozen=True)
class Mutant:
    """One careless reading: the rule it breaks, how, and the observation it must move."""

    rule_id: str
    description: str
    apply: Callable[[pytest.MonkeyPatch, dict], None]
    sidecar: Path | None = None
    observe: Callable[[], Any] | None = None


def _quote_sidecar(stem: str) -> Path:
    """The committed sidecar for ``stem`` (scanned, so a moved fixture fails loudly)."""
    return next(path for path in FIXTURES.rglob(f"{stem}.expected.json"))


def _rank(boundaries, *, forward: bool = False, everything: bool = False) -> list[int]:
    """An ordinal per boundary with the wrong rule applied (a mutant's ``_ordinals``)."""
    rank = 0
    out: list[int] = []
    for boundary in boundaries:
        kind = boundary.kind.value
        if everything or kind == "quote" or (forward and kind == "forward"):
            rank += 1
            out.append(rank)
        else:
            out.append(0)
    return out


def _three_line_window(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Join up to three physical lines into one attribution (the window extended to three)."""

    def windows(lines):
        flags["reached"] += 1
        found = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.text.startswith("On ") and not line.blank:
                for span in (1, 2, 3):
                    end = index + span - 1
                    if (
                        end < len(lines)
                        and not lines[end].blank
                        and lines[end].text.rstrip().endswith("wrote:")
                    ):
                        found.append((index, end))
                        index = end + 1
                        break
                else:
                    index += 1
                continue
            index += 1
        return found

    monkeypatch.setattr(text_rules, "_on_wrote_windows", windows)


def _single_label_blocks(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Key an Outlook block on a single label line instead of a run of two."""

    def label_runs(lines):
        flags["reached"] += 1
        runs = []
        index = 0
        while index < len(lines):
            if not i18n.label_shaped(lines[index].text):
                index += 1
                continue
            last = index
            while last + 1 < len(lines) and i18n.label_shaped(lines[last + 1].text):
                last += 1
            run = [line.text for line in lines[index : last + 1]]
            runs.append((index, last, i18n.language_of_run(run)))
            index = last + 1
        return runs

    monkeypatch.setattr(text_rules, "_label_runs", label_runs)


def _i18n_without_a_boundary_line(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Fire the i18n gap on any unknown-language label run, boundary-looking line or not."""

    def gap_line(lines, label_runs):
        flags["reached"] += 1
        for first, last, language in label_runs:
            if language is not None or first == 0:
                continue
            if not i18n.labels_from_one_known_set([line.text for line in lines[first : last + 1]]):
                return first
        return None

    monkeypatch.setattr(text_rules, "_i18n_gap_line", gap_line)


def _splitlines_line_model(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Run the line model over ``str.splitlines``, which also breaks on form feed and ``\\v``."""

    def splitlines_iter(payload, start, end):
        flags["reached"] += 1
        text = payload[start:end].decode("latin-1")
        position = 0
        for piece in text.splitlines(keepends=True):
            length = len(piece)
            content = len(piece.rstrip("\r\n"))
            yield (start + position, start + position + content, start + position + length)
            position += length

    monkeypatch.setattr(text_rules, "iter_lines", splitlines_iter)


_RE_NESTED_QUANTIFIER = re.compile(r"^(>+)+x$")


def _nested_quantifier_prefix(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Measure the prefix with a regex with nested quantifiers (a ReDoS-prone reading)."""

    def greedy(content: str) -> int:
        flags["reached"] += 1
        match = _RE_NESTED_QUANTIFIER.match(content)
        return len(match.group(0)) if match else 0

    monkeypatch.setattr(text_rules, "prefix_depth", greedy)


def _view_row_dropped(monkeypatch: pytest.MonkeyPatch, flags: dict) -> None:
    """Drop the ``body.view_levels`` row when every boundary is a forward/signature/footer."""
    real = resolve.scan_view

    def dropping(raw, part, part_text):
        flags["reached"] += 1
        view = real(raw, part, part_text)
        if any(boundary.kind.value == "quote" for boundary in view.boundaries):
            return view
        return dataclasses.replace(view, level=None)

    monkeypatch.setattr(resolve, "scan_view", dropping)


def _redos_observation() -> bool:
    """Whether the scan of a 26-``>`` line completes inside a quarter of a second."""
    message, result = _walk(b">" * 26 + b" tail")
    began = time.monotonic()
    resolve.scan_views(message, result)
    return time.monotonic() - began < 0.25


#: mutant id -> the case. Every rule id the TEXT stage can emit has at least one case
#: (:func:`test_every_quote_rule_id_has_a_mutation_case`); the extras cover the view's
#: interleaving, i18n, resolution and level-row rules and the two anti-patterns.
MUTANTS: dict[str, Mutant] = {
    "gt_nbsp_separator": Mutant(
        text_rules.RULE_GT_FAMILY,
        "counted NBSP as a `>` separator",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "prefix_depth",
            lambda real, content: real(content.replace("\u00a0", " ")),
            flags,
        ),
        sidecar=_quote_sidecar("gt_spacing_variants"),
    ),
    "gt_depth_scalar": Mutant(
        text_rules.RULE_GT_FAMILY,
        "kept one scalar depth per view instead of one per line",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_depths",
            lambda real, lines, first, last: (max(real(lines, first, last)),),
            flags,
        ),
        sidecar=_quote_sidecar("quoted_prefix_gt_deep"),
    ),
    "gt_phantom_line": Mutant(
        text_rules.RULE_GT_FAMILY,
        "counted a phantom trailing line",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_depths",
            lambda real, lines, first, last: real(lines, first, last) + (0,),
            flags,
        ),
        sidecar=_quote_sidecar("quoted_prefix_gt_deep"),
    ),
    "on_wrote_three_line": Mutant(
        text_rules.RULE_ON_WROTE_EN,
        "joined a three-line wrapped attribution (the two-line window extended to three)",
        _three_line_window,
        sidecar=_quote_sidecar("on_wrote_hard_wrapped"),
    ),
    "on_wrote_own_line": Mutant(
        text_rules.RULE_ON_WROTE_EN,
        "spanned the attribution's own line only",
        lambda monkeypatch, flags: _patch(
            monkeypatch, "_block_limit", lambda real, lines, structural, last: last + 1, flags
        ),
        sidecar=_quote_sidecar("gmail_reply_quoting_outlook_authored"),
    ),
    "on_wrote_run_kept": Mutant(
        text_rules.RULE_ON_WROTE_EN,
        "counted a `>` run inside an attribution as a second boundary",
        lambda monkeypatch, flags: _patch(
            monkeypatch, "_absorbed", lambda real, first, last, absorbing: False, flags
        ),
        sidecar=_quote_sidecar("gmail_short_reply_gt_and_on_wrote"),
    ),
    "outlook_single_label": Mutant(
        text_rules.RULE_OUTLOOK_FLAT,
        "keyed an Outlook block on a single label line",
        _single_label_blocks,
        sidecar=_quote_sidecar("original_message_dashes"),
    ),
    "outlook_mixed_languages": Mutant(
        text_rules.RULE_OUTLOOK_FLAT,
        "took a run's language from its first line, so a mixed run is a block",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "language_of_run",
            lambda real, run: next(
                (
                    language
                    for language in i18n.LANGUAGES
                    if i18n.slot_of_line(run[0], language) is not None
                ),
                real(run),
            ),
            flags,
            module=i18n,
        ),
        observe=lambda: _rhs(b"Hi Ben.\r\n\r\nFrom: a\r\nVon: b\r\n"),
    ),
    "forward_banner_ordinal": Mutant(
        text_rules.RULE_FORWARD_BANNER,
        "gave a forward banner an ordinal",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_ordinals",
            lambda real, boundaries: _rank(boundaries, forward=True),
            flags,
            module=resolve,
        ),
        sidecar=_quote_sidecar("begin_forwarded_message"),
    ),
    "dashes_unread": Mutant(
        text_rules.RULE_ORIGINAL_MESSAGE_DASHES,
        "read the original-message dashes as ordinary text",
        lambda monkeypatch, flags: _patch(
            monkeypatch, "is_original_message_dashes", lambda real, line: False, flags
        ),
        sidecar=_quote_sidecar("original_message_dashes"),
    ),
    "signature_span_marker_only": Mutant(
        text_rules.RULE_DASH_DASH_SPACE,
        "ended the signature span at the marker line",
        lambda monkeypatch, flags: _patch(
            monkeypatch, "_tail", lambda real, lines, index: index, flags
        ),
        sidecar=_quote_sidecar("signature_dash_dash_space"),
    ),
    "footer_ordinal": Mutant(
        text_rules.RULE_LIST_FOOTER_UNDERSCORES,
        "advanced the ordinal for a signature or a list footer",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_ordinals",
            lambda real, boundaries: _rank(boundaries, everything=True),
            flags,
            module=resolve,
        ),
        sidecar=_quote_sidecar("signature_dash_dash_space"),
    ),
    "underscores_undetected": Mutant(
        text_rules.RULE_LIST_FOOTER_UNDERSCORES,
        "did not detect the 30-underscore footer run",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_list_footer_hits",
            lambda real, lines: [
                hit for hit in real(lines) if hit[1] != text_rules.RULE_LIST_FOOTER_UNDERSCORES
            ],
            flags,
        ),
        sidecar=_quote_sidecar("list_footer_underscores"),
    ),
    "subscribed_undetected": Mutant(
        text_rules.RULE_LIST_FOOTER_SUBSCRIBED,
        "did not detect the subscribed-sentence footer",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_list_footer_hits",
            lambda real, lines: [
                hit for hit in real(lines) if hit[1] != text_rules.RULE_LIST_FOOTER_SUBSCRIBED
            ],
            flags,
        ),
        sidecar=_quote_sidecar("list_footer_underscores"),
    ),
    "bottom_posted_interleaved": Mutant(
        "view.inline_reply_interleaved",
        "called a bottom-posted reply interleaved",
        lambda monkeypatch, flags: _patch(
            monkeypatch, "_interleaved", lambda real, lines, runs: len(runs) >= 1, flags
        ),
        observe=lambda: _scan(b"> The earlier question.\r\n\r\nMy answer to it.\r\n")[1].interleaved,
    ),
    "i18n_on_absence": Mutant(
        "body.i18n_reply_marker",
        "fired the i18n gap without a boundary-looking line",
        _i18n_without_a_boundary_line,
        observe=lambda: _scan(b"Hi Ben.\r\n\r\nSubject: a note\r\nBetreff: b\r\n")[1].i18n_line,
    ),
    "resolution_from_last_boundary": Mutant(
        "body.view_levels",
        "took the resolution rule from the LAST boundary",
        lambda monkeypatch, flags: _patch(
            monkeypatch,
            "_resolution_rule",
            lambda real, boundaries: boundaries[-1].rule_id,
            flags,
            module=resolve,
        ),
        sidecar=_quote_sidecar("gmail_reply_quoting_outlook_authored"),
    ),
    "view_row_dropped": Mutant(
        "body.view_levels",
        "dropped the view row for a forward-only view",
        _view_row_dropped,
        sidecar=_quote_sidecar("list_footer_underscores"),
    ),
    "splitlines_line_model": Mutant(
        "line model",
        "used `bytes.splitlines` for the line model (U+2028 and form feed must not split a line)",
        _splitlines_line_model,
        observe=lambda: [line.text for line in _scan(b"Hi Ben.\r\n> one\x0ctwo\r\n")[1].lines],
    ),
    "regex_nested_quantifier": Mutant(
        "line model",
        "used a regex with nested quantifiers; a ReDoS input must fail it",
        _nested_quantifier_prefix,
        observe=_redos_observation,
    ),
}


def test_every_quote_rule_id_has_a_mutation_case() -> None:
    """No rule id the TEXT stage can emit is left without a careless reading (item 7a)."""
    covered = {mutant.rule_id for mutant in MUTANTS.values()}
    missing = sorted(set(text_rules.SCAN_RULES) - covered)
    assert not missing, f"rule id(s) with no mutation case: {missing}"
    assert len(MUTANTS) == 20, sorted(MUTANTS)


@pytest.mark.parametrize("mutant_id", sorted(MUTANTS))
def test_a_careless_quote_mutant_is_caught(
    mutant_id: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Each careless reading is reached, and it moves a label-blind observation.

    The anti-vacuity triple: (a) the patched symbol exists, (b) it was **reached**, and (c)
    either the L1 gate flips on the fixture that types the rule or the measured observation
    differs from the baseline.
    """
    mutant = MUTANTS[mutant_id]
    flags = {"reached": 0}
    copy: Path | None = None
    if mutant.sidecar is not None:
        copy = sidecar_copy.tamper(tmp_path, mutant.sidecar, lambda payload: None)
        baseline_report = l1.check_path(copy)
        # Turn 1.7 wired the html view's DOM rows live, so a fixture that carries an html part is
        # already red on the quote facts while the reviewer adjudicates (see test_l1_gate.py). The
        # baseline is therefore that named state -- **quote facts only** -- never a red elsewhere,
        # and the mutant must move the label-blind evidence *beyond* it.
        assert all(
            outcome.fact_id in l1.QUOTE_FACT_IDS for outcome in baseline_report.failures
        ), f"{mutant_id}: the baseline is red outside the quote facts"
        baseline: Any = [outcome.detail for outcome in baseline_report.failures]
    else:
        baseline = mutant.observe()

    mutant.apply(monkeypatch, flags)

    if copy is not None:
        mutated = l1.check_path(copy)
        assert mutated.failures, f"{mutant_id}: {mutant.description} was not caught"
        assert any(
            outcome.fact_id in l1.QUOTE_FACT_IDS for outcome in mutated.failures
        ), f"{mutant_id}: the gate did not name a quote fact: {mutated.lines()}"
        assert [outcome.detail for outcome in mutated.failures] != baseline, (
            f"{mutant_id}: {mutant.description} did not move the label-blind evidence"
        )
    else:
        mutated = mutant.observe()
        assert mutated != baseline, (
            f"{mutant_id}: {mutant.description} did not move the observation"
        )
    assert flags["reached"] > 0, f"{mutant_id}: the patch was never reached (vacuous)"


# ================================================ item 7b: the seeded fuzz

#: The seed of the fuzz's positions and lengths (the mutation KINDS are fixed, not seeded).
FUZZ_SEED = 20250304

#: How many mutated text parts each fixture contributes.
FUZZ_SEEDS = 8


def _mutated_variants(raw: bytes, rng: random.Random) -> list[bytes]:
    """The eight seeded mutations of one fixture's bytes (the text-part fuzz corpus)."""
    if not raw:
        return []
    data = bytearray(raw)
    index = lambda: rng.randrange(len(data))  # noqa: E731 - a seeded position

    flipped = bytearray(data)
    for _ in range(3):
        flipped[index()] = rng.randrange(256)
    repeated = bytearray(data)
    start = index()
    repeated[start:start] = bytes(data[start : start + rng.randint(1, 64)])
    cut = index()
    injected = bytearray(data)
    injected[index():0] = b">" * rng.randint(1, 40) + b" "
    weird = bytearray(data)
    weird[index():0] = "\u00a0".encode("utf-8") + b"\x00" * rng.randint(1, 8)
    digits = bytearray(data)
    digits[index():0] = "\u0661\u0662\u0663".encode("utf-8") * rng.randint(1, 4)
    return [
        bytes(flipped),  # byte flips
        bytes(data[: rng.randrange(len(data) + 1)]),  # truncation
        bytes(repeated),  # a repeated chunk
        bytes(data[cut:] + data[:cut]),  # swapped chunks
        bytes(injected),  # an injected `>` run
        bytes(weird),  # NBSP and NULs
        bytes(data) + b">" * rng.randint(1, 4096) + b" tail",  # a giant line
        bytes(digits),  # non-ASCII digits
    ]


def _fuzz_fixtures() -> tuple[int, list[tuple]]:
    """Scan every fixture's mutated bytes; return ``(case count, failures)``.

    Each failure names the fixture, the mutation number and the seed, so a planted raiser is
    reported **with its seed**.
    """
    rng = random.Random(FUZZ_SEED)
    cases = 0
    failures: list[tuple] = []
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        for number, data in enumerate(_mutated_variants(sidecar.artifact.read_bytes(), rng)):
            cases += 1
            where = f"{stem}#{number} seed={FUZZ_SEED}"
            try:
                result = walk(EmlContainer(memory_bytes(data)))
                for view in resolve.scan_views(data, result):
                    length = len(view.part_text.text)
                    for boundary in view.boundaries:
                        if not 0 <= boundary.span.start <= boundary.span.end <= length:
                            failures.append((where, "span outside the text", boundary))
                    ordinals = [
                        boundary.ordinal
                        for boundary in view.boundaries
                        if boundary.kind.value == "quote"
                    ]
                    if ordinals != list(range(1, len(ordinals) + 1)):
                        failures.append((where, "ordinals do not increase from 1", ordinals))
            except Exception as error:  # noqa: BLE001 - the fuzz must catch anything
                failures.append((where, type(error).__name__, str(error)))
    return cases, failures


def test_the_seeded_fuzz_over_mutated_text_parts_is_bounded() -> None:
    """No exception, every span inside the text, every quote ordinal a 1-based rank."""
    began = time.monotonic()
    cases, failures = _fuzz_fixtures()
    elapsed = time.monotonic() - began
    assert cases >= 126 * FUZZ_SEEDS, cases
    assert not failures, failures[:3]
    assert elapsed < 60, f"the seeded fuzz took {elapsed:.1f}s"


def test_a_planted_raiser_fails_the_fuzz_with_the_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fuzz is able to fail: a planted raiser is reported, with the seed that found it."""

    def raising(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("planted raiser")

    monkeypatch.setattr(resolve, "scan_view", raising)
    cases, failures = _fuzz_fixtures()
    assert cases, "the fuzz ran no case"
    assert failures, "the planted raiser must fail the fuzz"
    assert any("RuntimeError" in failure for failure in failures), failures[:3]
    assert f"seed={FUZZ_SEED}" in failures[0][0], failures[0]


# ================================================ item 7c: the work budget's hit


def test_the_work_budget_stops_the_scan_and_the_stop_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-part budget hit stops the scan cleanly and is reported, never raised (item 7c)."""
    monkeypatch.setattr(text_rules, "work_budget", lambda text_length: 1)
    body = b"> a\r\n> b\r\n> c\r\n> d\r\n"
    message, result = _walk(body)
    view = resolve.scan_views(message, result)[0]
    assert view.scan.truncated is True, "the stop is reported on the scan"
    assert len(view.scan.lines) < 4, "the scan stopped before reading every line"
    for boundary in view.boundaries:
        assert 0 <= boundary.span.start <= boundary.span.end <= len(view.part_text.text)
