"""The TEXT half of the quote rules (Turn 1.6; build-spec decision 3, signed decisions Q1/Q5/Q7).

One scanner over one line model. The scanner consumes
:func:`emailextract.walk.iter_lines` -- the package's single line model (decision 8) -- and
nothing else: ``str.splitlines``/``bytes.splitlines`` are forbidden for body text, because
they break on form feed, vertical tab, U+2028 and (after decoding) U+0085, none of which is a
line break in RFC 5322 or in the walker's model. The **analysis** text is
:attr:`emailextract.text.PartText.text` (the decoded text, RFC 3676 space-unstuffed for a
``format=flowed`` part) and every span this module returns is in **that text's code points,
un-normalised**: the same coordinate space ``body.text`` is typed in.

The rules, each with the id it is recorded under (the fact's ``rule_id``):

``gt_family``
    The ``>``-family prefix depth, **per physical line**, on the unjoined text. A prefix is a
    run of ``>`` characters optionally separated by SPACE or TAB only: NBSP (U+00A0), NNBSP and
    every other space are **not** separators and are **not** counted (``>\\u00a0> x`` has depth
    1 and the rest is text). A maximal run of consecutive lines with depth >= 1 is **one**
    boundary whose ``prefix_depth`` lists the run's per-line depths in order. Soft-break
    joining is deferred and never performed (the part keeps its
    ``body.flowed_reflow_unresolved`` gap).

``on_wrote_en``
    An English attribution: a line that starts with ``On `` and ends (after trailing
    whitespace) with ``wrote:``, **or** a **two-physical-line window** (a client hard-wrapped
    the attribution). The window is exactly two lines; three wrapped lines are **not** joined
    and are new text at level 0. The span is the attribution line(s) **plus the contiguous
    NON-BLANK block that follows** (decision 35), whether or not that block is ``>``-prefixed:
    every following line up to the first blank line, the end of the part, or the start of
    another boundary of kind forward, signature or list_footer. A blank line directly after
    the attribution ends the span at the attribution (the quoted lines after the blank are
    then their own ``gt_family`` run). The scan is single-pass and anchored on line starts --
    no regex with nested quantifiers.

``outlook_flat_en|de|fr``
    A maximal run of >= 2 adjacent ``Label:`` lines, all from **one** language's set, in
    canonical order as a subsequence (see :mod:`emailextract.quote.i18n`). A single label line
    is not a block; a run that mixes languages matches none. The span is the label block plus
    the whole quoted content that follows it (decision 35): every following line up to the
    next boundary of any kind **other than a ``>`` run** -- a forward banner, the
    original-message dashes, a signature, a list footer, another label block or an attribution
    -- or the end of the part.

``forward_banner`` / ``original_message_dashes``
    ``Begin forwarded message:`` and ``-----Original Message-----``, the two shapes decision 3
    names in its table. Signed Q5: **both** are kind ``forward`` at level 0 and carry ordinal
    0. A forward banner does **not** suppress an Outlook flat block inside the forwarded
    content (signed Q4): that block is still found as ``quote``.

``dash_dash_space``
    Exactly the line ``-- `` (dash dash SPACE, then the line end; RFC 3676 4.3), kind
    ``signature``, a **candidate** only. Signed Q7: the span runs from that line through the
    end of the part.

``list_footer_underscores`` / ``list_footer_subscribed``
    A line of at least 30 ``_``, and the sentence beginning ``You received this message
    because you are subscribed``. Kind ``list_footer``, detection only. Signed Q7: the span
    runs from that line through the end of the part.

Every returned span lies inside the text and is derived from the line model (decision 34): a
span that reaches the end of the part includes the final line terminator, while a span that
ends before another boundary or before a blank line ends at its last NON-BLANK content line --
no terminator and no trailing blank. A ``>`` run lying inside an attribution's or a flat
block's span is part of that boundary, never a second ``gt_family`` boundary (decision 36):
one quote, one ordinal, and the absorbing boundary's per-line depths still record the run's
depths.

Work is counted deterministically on :data:`WORK` -- the :class:`emailextract.walk.WorkCounter`
pattern, a seam a test can reset and read, **never a clock** -- one step per line read and one
per character examined in a prefix run. :func:`work_budget` states the part-level ceiling:
``Limits.max_field_work_units_per_byte`` work units per text code point, the caller's own
number, so a pathological input stops at a recorded bound instead of raising.
"""

from __future__ import annotations

import bisect
import codecs
from dataclasses import dataclass, field
from typing import Callable, Final, Iterable

from .. import text as text_stage
from ..parse import Limits
from ..walk import PartShape, WorkCounter, iter_lines

from . import i18n

__all__ = [
    "BOUNDARY_KINDS",
    "Boundary",
    "DASH_DASH_SPACE",
    "FORWARD_BANNERS",
    "GAP_I18N_REPLY_MARKER",
    "GAP_INLINE_REPLY_INTERLEAVED",
    "GAP_NO_BOUNDARY_FOUND",
    "Line",
    "ORIGINAL_MESSAGE_DASHES",
    "RULE_DASH_DASH_SPACE",
    "RULE_FORWARD_BANNER",
    "RULE_GT_FAMILY",
    "RULE_LIST_FOOTER_SUBSCRIBED",
    "RULE_LIST_FOOTER_UNDERSCORES",
    "RULE_ON_WROTE_EN",
    "RULE_ORIGINAL_MESSAGE_DASHES",
    "RULE_OUTLOOK_FLAT",
    "SCAN_RULES",
    "SIGNATURE_UNDERSCORE_RUN",
    "SUBSCRIBED_SENTENCE",
    "ScanResult",
    "WORK",
    "WORK_UNITS_PER_CODE_POINT",
    "boundary_looking",
    "is_forward_banner",
    "is_original_message_dashes",
    "prefix_depth",
    "scan_view",
    "view_lines",
    "work_budget",
]

#: The work counter (the :class:`~emailextract.walk.WorkCounter` pattern): deterministic,
#: resettable and readable, never a clock. A test resets it, scans, and reads it back.
WORK: Final[WorkCounter] = WorkCounter()

#: The caller's per-code-point work ceiling: the same field-value budget the header stage
#: hands the RFC 2047 decoder (``Limits.max_field_work_units_per_byte``), reused rather than
#: invented, so a pathological part stops at the caller's number and not at a module default.
WORK_UNITS_PER_CODE_POINT: Final[int] = Limits.untrusted().max_field_work_units_per_byte

#: The rule ids this module emits (the fact's ``rule_id`` column); the DOM family adds its own.
RULE_GT_FAMILY: Final[str] = "gt_family"
RULE_ON_WROTE_EN: Final[str] = "on_wrote_en"
RULE_OUTLOOK_FLAT: Final[str] = "outlook_flat_"
RULE_FORWARD_BANNER: Final[str] = "forward_banner"
RULE_ORIGINAL_MESSAGE_DASHES: Final[str] = "original_message_dashes"
RULE_DASH_DASH_SPACE: Final[str] = "dash_dash_space"
RULE_LIST_FOOTER_UNDERSCORES: Final[str] = "list_footer_underscores"
RULE_LIST_FOOTER_SUBSCRIBED: Final[str] = "list_footer_subscribed"

#: The closed ``kind`` vocabulary this module emits (model.BoundaryKind's values).
BOUNDARY_KINDS: Final[tuple[str, ...]] = (
    "quote",
    "forward",
    "signature",
    "list_footer",
    "unknown",
)

#: The rules whose hits this module can emit, in the order they are tested over a line.
SCAN_RULES: Final[tuple[str, ...]] = (
    RULE_GT_FAMILY,
    RULE_ON_WROTE_EN,
    RULE_OUTLOOK_FLAT,
    RULE_FORWARD_BANNER,
    RULE_ORIGINAL_MESSAGE_DASHES,
    RULE_DASH_DASH_SPACE,
    RULE_LIST_FOOTER_UNDERSCORES,
    RULE_LIST_FOOTER_SUBSCRIBED,
)

#: The two forward shapes decision 3's table names -- and only those (Q5: both kind ``forward``).
FORWARD_BANNERS: Final[tuple[str, ...]] = ("Begin forwarded message:",)
ORIGINAL_MESSAGE_DASHES: Final[str] = "-----Original Message-----"

#: The RFC 3676 4.3 signature separator: dash, dash, SPACE, then the line end.
DASH_DASH_SPACE: Final[str] = "-- "

#: A list-footer underscore run: at least this many ``_`` on the line and nothing else.
SIGNATURE_UNDERSCORE_RUN: Final[int] = 30

#: The list-footer sentence. "The sentence beginning ..." -- a phrase, not a full line.
SUBSCRIBED_SENTENCE: Final[str] = "You received this message because you are subscribed"

#: The closed gap ids this module can report (registry: ``docs/design/phase0-gaps.md``).
GAP_I18N_REPLY_MARKER: Final[str] = "body.i18n_reply_marker"
GAP_NO_BOUNDARY_FOUND: Final[str] = "body.no_boundary_found"
GAP_INLINE_REPLY_INTERLEAVED: Final[str] = "body.inline_reply_interleaved"

#: The ONE whitespace pair that separates two ``>`` characters of a prefix: SPACE and TAB.
_PREFIX_SEPARATORS: Final[str] = " \t"


@dataclass(frozen=True)
class Line:
    """One physical line of the view's text: its code-point bounds and its prefix depth.

    ``start``/``content_end``/``term_end`` are offsets into the view's text; ``text`` is the
    content **without** its terminator (``CRLF``, ``LF`` or a lone ``CR``, the one line model)
    and ``depth`` is the ``>``-family depth of that content.
    """

    index: int
    start: int
    content_end: int
    term_end: int
    text: str
    depth: int

    @property
    def blank(self) -> bool:
        """A line whose content is whitespace only (the blank line the window rule skips)."""
        return not self.text.strip()


@dataclass(frozen=True)
class Boundary:
    """One rule hit: what fired, what kind it is, and the code-point span it covers.

    ``lines`` are the line indices the span covers, so ``prefix_depth`` can be checked against
    the span (one depth per covered line) and a caller can re-read the bytes.
    """

    rule_id: str
    kind: str
    start: int
    end: int
    lines: tuple[int, ...] = ()
    prefix_depth: tuple[int, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class ScanResult:
    """Everything the text family measured for one view, and the absence answers.

    ``quote_runs`` is the number of separate ``>`` runs (the bottom-posting test);
    ``no_boundary`` is the ``body.no_boundary_found`` answer (no rule fired **and** no prefix
    line exists); ``i18n_line`` is the line index a ``body.i18n_reply_marker`` block starts at;
    ``interleaved`` is the ``body.inline_reply_interleaved`` answer; ``truncated`` says the
    work budget stopped the scan (a recorded stop, never an exception).
    """

    boundaries: tuple[Boundary, ...] = ()
    quote_runs: int = 0
    no_boundary: bool = False
    i18n_line: int | None = None
    interleaved: bool = False
    truncated: bool = False
    lines: tuple[Line, ...] = field(default=())


@dataclass(frozen=True)
class LineModel:
    """One view's lines, the work they cost, and whether the work budget stopped the read.

    ``steps`` is the deterministic count the scan spent on this view (one per line read, one
    per character examined in a prefix run) -- read off :data:`WORK` around the read, which is
    the same number a test sees when it resets the counter itself.
    """

    lines: tuple[Line, ...] = ()
    steps: int = 0
    truncated: bool = False


# ------------------------------------------------------------------ the line model


def work_budget(text_length: int) -> int:
    """The part-level work ceiling: the caller's units per code point, at least one unit.

    A quote rule can only look at a line a bounded number of times (a prefix run walks each
    ``>`` and each separator once), so the scanner is linear in the text; this ceiling is what
    turns "linear" into a **stopping** bound a hostile input cannot walk past. The constant is
    the caller's own ``Limits.max_field_work_units_per_byte`` -- no new default is invented.
    """
    return WORK_UNITS_PER_CODE_POINT * max(text_length, 1)


def prefix_depth(content: str) -> int:
    """The ``>``-family depth of one line's content (SPACE/TAB-separated ``>`` runs only).

    A prefix must start at the line's first character: any other character -- a space, a
    letter, NBSP -- makes the depth 0. NBSP is literal text, not a separator (build-spec
    decision 3 and the plan debate's section 3.2).
    """
    index = 0
    depth = 0
    length = len(content)
    while index < length:
        WORK.add()
        if content[index] != ">":
            break
        depth += 1
        index += 1
        while index < length and content[index] in _PREFIX_SEPARATORS:
            WORK.add()
            index += 1
    return depth


def _map_reader(spans) -> object:
    """A byte-offset (into the part's body) -> code-point reader over an exact offset map."""

    starts = [span.byte_offset for span in spans]
    ends = [span.byte_end for span in spans]
    chars = [span.char_offset for span in spans]
    lengths = [span.char_length for span in spans]

    def read(offset: int) -> int:
        index = bisect.bisect_right(starts, offset) - 1
        if index < 0:
            return 0
        if offset >= ends[index]:
            return chars[index] + lengths[index]
        return chars[index] + min(offset - starts[index], lengths[index])

    return read


def _decoder_reader(payload: bytes, codec: str, errors: str):
    """A payload-byte-offset -> code-point reader that decodes the payload as it walks it.

    Used only when the part's within-part byte span is **not** exact (a non-identity CTE, a
    stateful/multibyte charset, a decode fallback): the map that would make the translation
    exact does not exist, so the same decode the package already ran is replayed
    incrementally, one increasing offset at a time. This is not a second decode *rule* -- the
    codec and the error policy are the ones ``text.analyse_part`` used.
    """
    decoder = codecs.getincrementaldecoder(codec)(errors)
    state = {"position": 0, "characters": 0}

    def read(offset: int) -> int:
        position = state["position"]
        if offset < position:  # non-monotonic: restart, so the answer is still a function
            decoder.reset()
            state["position"] = 0
            state["characters"] = 0
            position = 0
        state["characters"] += len(decoder.decode(payload[position:offset]))
        state["position"] = offset
        return state["characters"]

    return read


def _codec_of(part_text: text_stage.PartText, part: PartShape) -> tuple[str, str]:
    """The ``(codec, errors)`` pair ``text.analyse_part`` used to produce the view's text."""
    source = getattr(part.encoding_source, "value", None)
    if source == "fallback":
        return "windows-1252", "replace"
    return part_text.used_charset or "windows-1252", "strict"


def view_lines(
    part_text: text_stage.PartText, part: PartShape, raw: bytes
) -> LineModel:
    """The view's physical lines, from the one line model, with code-point offsets.

    Two routes, both over :func:`emailextract.walk.iter_lines`:

    * the part's text is locatable in its bytes (an **exact** within-part span: an identity
      CTE and a stateless charset), so the line model runs over the part's raw body bytes and
      the exact offset map translates each byte offset into the view's code points (a dropped
      RFC 3676 stuffing byte becomes a zero-character entry, so the text offset is still
      right);
    * it is not (a base64 or quoted-printable CTE, a stateful/multibyte charset, a decode
      fallback): the line model runs over the part's **decoded payload** -- the walker's own
      ``_decode_cte``, never a second decode rule -- and the code points are counted with the
      codec that decode used.

    A part the walker skipped for a size cap has no decoded payload and therefore no lines.

    **Recorded limitation.** For a ``format=flowed`` part on the second route the text is
    space-unstuffed while the payload is not, so the code-point offsets are shifted by the
    stuffing spaces before them. No committed fixture reaches that case (the flowed fixture
    is an identity CTE, which takes the exact route) and the repair -- an unstuffing-aware
    reader -- belongs to the turn that needs it.
    """
    body = raw[part.body_span.offset : part.body_span.end]
    spans = part_text.offset_map
    if spans and spans[-1].byte_end == len(body) and spans[0].byte_offset == 0:
        payload: bytes | None = body
        reader = _map_reader(spans)
    else:
        payload = text_stage.decoded_payload(raw, part)
        if payload is None:
            return LineModel()
        codec, errors = _codec_of(part_text, part)
        reader = _decoder_reader(payload, codec, errors)

    if not payload:
        return LineModel()
    budget = work_budget(len(part_text.text))
    before = WORK.count()
    lines: list[Line] = []
    truncated = False
    for index, (start, content_end, term_end) in enumerate(iter_lines(payload, 0, len(payload))):
        WORK.add()
        char_start = reader(start)
        text = part_text.text[char_start : reader(content_end)]
        lines.append(
            Line(
                index=index,
                start=char_start,
                content_end=reader(content_end),
                term_end=reader(term_end),
                text=text,
                depth=prefix_depth(text),
            )
        )
        if WORK.count() - before > budget:
            truncated = True
            break
    steps = WORK.count() - before
    return LineModel(lines=tuple(lines), steps=steps, truncated=truncated)


# --------------------------------------------------------------- the rule detectors


def _covered_last(lines: tuple[Line, ...], limit: int) -> int:
    """The last line index a span covers when it stops before ``limit`` (decision 34).

    ``limit`` is an **exclusive** line index; ``len(lines)`` means the span reaches the end of
    the part, so the final line is covered (and, at the part's end, its terminator too). A
    span that ends before another boundary or before a blank line ends at the last NON-BLANK
    content line: a trailing blank line is never covered.
    """
    if limit >= len(lines):
        return len(lines) - 1
    last = limit - 1
    while last > 0 and lines[last].blank:
        last -= 1
    return last


def _bounds(lines: tuple[Line, ...], first: int, last: int) -> tuple[int, int]:
    """The signed span convention (decision 34): ``first`` line's start .. ``last`` line's end.

    A span that reaches the **end of the part** includes the final line terminator (which is
    what makes ``body.quote_boundaries`` tile the tail of the view); a span that ends
    mid-message ends at its last covered line's content -- no terminator, no trailing blank.
    """
    start = lines[first].start
    if last == len(lines) - 1:
        return start, lines[last].term_end
    return start, lines[last].content_end


def _gt_runs(lines: tuple[Line, ...]) -> list[tuple[int, int]]:
    """The maximal runs of consecutive lines with depth >= 1, as ``(first, last)`` pairs."""
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if lines[index].depth < 1:
            index += 1
            continue
        last = index
        while last + 1 < len(lines) and lines[last + 1].depth >= 1:
            last += 1
        runs.append((index, last))
        index = last + 1
    return runs


def _depths(lines: tuple[Line, ...], first: int, last: int) -> tuple[int, ...]:
    return tuple(line.depth for line in lines[first : last + 1])


def _block_limit(lines: tuple[Line, ...], structural: set[int], last: int) -> int:
    """The first line after an attribution's last line that ends its contiguous block.

    Decision 35: the first blank line, the start of another boundary of kind forward, signature
    or list_footer, or the end of the part.
    """
    index = last + 1
    while index < len(lines):
        if lines[index].blank or index in structural:
            return index
        index += 1
    return len(lines)


def _flat_limit(lines: tuple[Line, ...], barriers: set[int], first: int) -> int:
    """The first boundary line after a flat block's first line, or the end of the part."""
    later = [index for index in barriers if index > first]
    return min(later) if later else len(lines)


def _tail(lines: tuple[Line, ...], index: int) -> int:
    """The last line a span that runs from ``index`` to the end of the part covers (34)."""
    return _covered_last(lines, len(lines))


def _absorbed(first: int, last: int, absorbing: list[tuple[int, int]]) -> bool:
    """Whether a ``>`` run lies inside an attribution's or a flat block's extent (36)."""
    return any(first >= span_first and last <= span_last for span_first, span_last in absorbing)


def _interleaved(lines: tuple[Line, ...], runs: tuple[tuple[int, int], ...]) -> bool:
    """``body.inline_reply_interleaved``: two or more ``>`` runs separated by real text."""
    return len(runs) >= 2 and _separated_by_text(lines, runs)


def _i18n_gap_line(
    lines: tuple[Line, ...], label_runs: list[tuple[int, int, str | None]]
) -> int | None:
    """The line a ``body.i18n_reply_marker`` block starts at, or ``None`` (decision 29)."""
    for first, last, language in label_runs:
        if language is not None or first == 0:
            continue
        if not boundary_looking(lines[first - 1]):
            continue
        if not i18n.labels_from_one_known_set([line.text for line in lines[first : last + 1]]):
            return first
    return None


def boundary_looking(line: Line) -> bool:
    """Whether a line looks like a boundary this rule list does not name.

    The registry's trigger for ``body.i18n_reply_marker`` is "a header-like run of short
    ``Label:`` lines directly after a **boundary-looking line**", and the design does not
    define that term (resolved here, reported): a non-blank line that is not itself a
    ``Label:`` line, ends with ``:`` and carries at least two tokens (``Am ... schrieb Ada
    Sender:``, ``Dne ... napsal Ada Sender:``, ``Begin forwarded message:``). A single-token
    ``Subject:`` is a label, not a boundary.
    """
    content = line.text.rstrip()
    if not content or i18n.label_shaped(line.text):
        return False
    return content.endswith(":") and len(content.split()) >= 2


def is_forward_banner(line: Line) -> bool:
    """Whether the line is one of the two named forward shapes (kind ``forward``)."""
    return line.text.rstrip() in FORWARD_BANNERS


def is_original_message_dashes(line: Line) -> bool:
    """Whether the line is exactly ``-----Original Message-----`` (kind ``forward``)."""
    return line.text.rstrip() == ORIGINAL_MESSAGE_DASHES


def _on_wrote_windows(lines: tuple[Line, ...]) -> list[tuple[int, int]]:
    """The English attributions, as ``(first, last)`` line pairs: single line or a 2-line window.

    Single-pass, anchored on the line start (``startswith("On ")``), never a regex over the
    text: a hard-wrapped attribution is found by looking at the line **after** the ``On `` line
    and at nothing else, so a three-line wrap is never joined.
    """
    windows: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.text.startswith("On ") and not line.blank:
            if line.text.rstrip().endswith("wrote:"):
                windows.append((index, index))
                index += 1
                continue
            if index + 1 < len(lines):
                following = lines[index + 1]
                if not following.blank and following.text.rstrip().endswith("wrote:"):
                    windows.append((index, index + 1))
                    index += 2
                    continue
        index += 1
    return windows


def _label_runs(lines: tuple[Line, ...]) -> list[tuple[int, int, str | None]]:
    """The maximal runs of >= 2 adjacent label lines, with the one language they belong to."""
    runs: list[tuple[int, int, str | None]] = []
    index = 0
    while index < len(lines):
        if not i18n.label_shaped(lines[index].text):
            index += 1
            continue
        last = index
        while last + 1 < len(lines) and i18n.label_shaped(lines[last + 1].text):
            last += 1
        if last > index:
            run = [line.text for line in lines[index : last + 1]]
            runs.append((index, last, i18n.language_of_run(run)))
        index = last + 1
    return runs


def _list_footer_hits(lines: tuple[Line, ...]) -> list[tuple[int, str]]:
    """The list-footer candidate lines with the rule each fired (detection only)."""
    hits: list[tuple[int, str]] = []
    for line in lines:
        content = line.text.rstrip()
        if content.startswith("_"):
            if len(content) >= SIGNATURE_UNDERSCORE_RUN and set(content) == {"_"}:
                hits.append((line.index, RULE_LIST_FOOTER_UNDERSCORES))
            continue
        if line.text.startswith(SUBSCRIBED_SENTENCE):
            hits.append((line.index, RULE_LIST_FOOTER_SUBSCRIBED))
    return hits


def scan_view(lines: tuple[Line, ...], *, truncated: bool = False) -> ScanResult:
    """Run every TEXT rule over the view's lines, once, in one pass order.

    The scan is a single walk over ``lines``: the prefix depth was measured when each line was
    built (:func:`view_lines`), the detectors look at a line and its immediate neighbours, and
    no rule re-scans the text. ``truncated`` is the line read's own work-budget stop, carried
    through so a caller can record it.
    """
    if not lines:
        return ScanResult(truncated=truncated, lines=lines)

    runs = _gt_runs(lines)
    windows = _on_wrote_windows(lines)
    label_runs = _label_runs(lines)
    flats = [
        (first, last, language)
        for first, last, language in label_runs
        if language is not None
    ]
    forward_lines = [
        (line.index, RULE_FORWARD_BANNER if is_forward_banner(line) else RULE_ORIGINAL_MESSAGE_DASHES)
        for line in lines
        if is_forward_banner(line) or is_original_message_dashes(line)
    ]
    signature_lines = [line.index for line in lines if line.text == DASH_DASH_SPACE]
    footer_hits = _list_footer_hits(lines)

    # A boundary of kind forward, signature or list_footer: an attribution's contiguous block
    # stops at one of these (decision 35).
    structural = (
        {index for index, _rule in forward_lines}
        | set(signature_lines)
        | {index for index, _rule in footer_hits}
    )

    # A flat block runs on to the next boundary of ANY kind but a `>` run, which its extent
    # absorbs as content (decisions 35 and 36).
    flat_barriers = (
        structural
        | {first for first, _last in windows}
        | {first for first, _last, _language in flats}
    )

    # ``(rule_id, kind, first, last)`` per hit, in the order the rules are stated; each span is
    # resolved against decision 34 and the list is sorted into document order below.
    found: list[tuple[str, str, int, int]] = []
    found.extend(
        (
            RULE_ON_WROTE_EN,
            "quote",
            first,
            _covered_last(lines, _block_limit(lines, structural, last)),
        )
        for first, last in windows
    )
    found.extend(
        (
            RULE_OUTLOOK_FLAT + str(language),
            "quote",
            first,
            _covered_last(lines, _flat_limit(lines, flat_barriers, first)),
        )
        for first, _last, language in flats
    )
    for index, rule_id in forward_lines:
        later = [line_index for line_index, _rule in forward_lines if line_index > index]
        found.append(
            (rule_id, "forward", index, _covered_last(lines, min(later) if later else len(lines)))
        )
    found.extend(
        (RULE_DASH_DASH_SPACE, "signature", index, _tail(lines, index))
        for index in signature_lines
    )
    found.extend(
        (rule_id, "list_footer", index, _tail(lines, index))
        for index, rule_id in footer_hits
    )

    # Absorption (decision 36): a `>` run inside an attribution's or a flat block's extent is
    # part of that boundary, never a second ``gt_family`` boundary -- one quote, one ordinal.
    absorbing = [
        (first, last)
        for rule_id, _kind, first, last in found
        if rule_id == RULE_ON_WROTE_EN or rule_id.startswith(RULE_OUTLOOK_FLAT)
    ]
    for first, last in runs:
        if _absorbed(first, last, absorbing):
            continue
        found.append((RULE_GT_FAMILY, "quote", first, last))

    boundaries: list[Boundary] = []
    for rule_id, kind, first, last in found:
        start, end = _bounds(lines, first, last)
        boundaries.append(
            Boundary(
                rule_id=rule_id,
                kind=kind,
                start=start,
                end=end,
                lines=tuple(range(first, last + 1)),
                prefix_depth=_depths(lines, first, last),
            )
        )

    boundaries.sort(key=lambda item: (item.start, item.end, item.rule_id))

    i18n_line = _i18n_gap_line(lines, label_runs)

    has_prefix = any(line.depth >= 1 for line in lines)
    no_boundary = not boundaries and not has_prefix and i18n_line is None

    return ScanResult(
        boundaries=tuple(boundaries),
        quote_runs=len(runs),
        no_boundary=no_boundary,
        i18n_line=i18n_line,
        interleaved=_interleaved(lines, runs),
        truncated=truncated,
        lines=lines,
    )


def _separated_by_text(lines: tuple[Line, ...], runs: Iterable[tuple[int, int]]) -> bool:
    """Whether two quote runs are separated by at least one non-blank level-0 line.

    This is the ``body.inline_reply_interleaved`` definition the turn states: after a quote run
    ends, new level-0 **text** follows and then another quote run appears. Two runs are always
    separated (adjacent ``>`` lines are one run), so the test is whether the gap between them
    holds real text: a blank line alone is not "new text", and a bottom-posted reply -- quoted
    lines first, the answer after, **one** run -- is legal and records nothing.
    """
    pairs = list(runs)
    for (first_last, next_first) in zip(pairs, pairs[1:]):
        between = lines[first_last[1] + 1 : next_first[0]]
        if any(not line.blank for line in between):
            return True
    return False
