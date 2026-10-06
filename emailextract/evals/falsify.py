"""Per-gap falsifiability by mutation (design D14, build spec Turn 0.4).

Design D14 asks for a falsifiability case per named gap: a case a **careless implementation
would get wrong**. Unlike the workbook (where phase 0 had no reader, so a case was written
against the oracle's override point), the walker here **exists**, so the case is written
against the walker itself: ``mutated`` monkeypatches exactly **one rule** -- the same shape
as the ledger sensitivity tests -- to do what a careless implementation would, and the claim
is that the L1 gate then **fails** on the sidecar carrying that gap, naming the fact, the gap
id and the fixture.

Six gaps are exercised by a committed fixture today (``malformed_mime``,
``preamble_epilogue``, ``truncated_base64``, ``bad_charset``); the two the sidecars do not
carry (``body.headers_only``, ``body.no_boundary_found``) are proven detectable against
**inline hand-typed bytes** built in the test, so the mutant is still caught without adding
a fixture or editing a sidecar.

The catalogue is keyed by the walker's own ``GAP_*`` constants
(:data:`WALKER_GAPS`), and ``tests/test_gap_falsifiability.py`` holds it against them in both
directions: a walker that gains a gap id with no case here fails, and a case for a gap no
fixture exercises has to carry its own inline bytes.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping

from .. import addresses as address_stage
from .. import attach as attach_stage
from .. import dates as date_stage
from .. import headers as header_stage
from .. import selection as selection_stage
from .. import text as text_stage
from .. import walk as walk_module
from ..ids import RawSpan
from ..quote import resolve as quote_stage
from ..quote import text_rules as quote_text_stage
from ..walk import (
    GAP_BODY_BOUNDARY_DISAGREEMENT,
    GAP_BODY_DECODE_DESTROYED_BYTES,
    GAP_BODY_DECODE_FALLBACK_USED,
    GAP_BODY_EPILOGUE_BYTES,
    GAP_BODY_HEADERS_ONLY,
    GAP_BODY_NO_BOUNDARY_FOUND,
    GAP_BODY_PREAMBLE_BYTES,
    GAP_HEADERS_MALFORMED_LINE,
)
from . import l1 as l1_module
from .l1 import LIVE_GAP_IDS

__all__ = [
    "CASES",
    "EMITTABLE_GAP_IDS",
    "GAP_CHANNELS",
    "GapCase",
    "PHASE1_CASES",
    "UNEXERCISED_GAP_IDS",
    "WALKER_GAPS",
    "describe",
    "drop_everywhere",
    "exercised_gaps",
    "inline_sidecar",
    "mutated",
    "uncovered_gaps",
]

#: Every gap id the walker can emit, read off the module so a new ``GAP_*`` constant shows
#: up here (and then fails the catalogue test) instead of being forgotten.
WALKER_GAPS: tuple[str, ...] = tuple(
    sorted(
        value
        for name, value in vars(walk_module).items()
        if name.startswith("GAP_") and isinstance(value, str)
    )
)

#: The two inline byte strings for the gaps no committed fixture carries. Hand-typed here,
#: small, and paired with the minimal sidecar ``inline_sidecar`` builds from ``expected_gaps``.
NO_BOUNDARY_BYTES = (
    b"Content-Type: multipart/mixed; boundary=missing\r\n"
    b"\r\n"
    b"--other\r\n"
    b"\r\n"
    b"body\r\n"
)

HEADERS_ONLY_BYTES = b"Subject: no blank line follows\r\nX-Last: to end of file"


# ------------------------------------------------------------------- mutants
#: A mutant patches ONE walker rule and returns a restore callable. Each does what a
#: careless walker would: it drops the gap (and, where the design says so, invents the
#: reading the gap exists to refuse).


def _patch(module: Any, name: str, replacement: Any) -> Callable[[], None]:
    original = getattr(module, name)
    setattr(module, name, replacement)
    return lambda: setattr(module, name, original)


def _drop_malformed_line(module: Any) -> Callable[[], None]:
    """Swallow the malformed line into the previous field: no paragraph, no gap (D2)."""
    original = module.header_fields_at

    def naive(raw: bytes, start: int, end: int):
        fields, _gaps = original(raw, start, end)
        return [item for item in fields if item.parse_status == "ok"], []

    return _patch(module, "header_fields_at", naive)


def _drop_boundary_disagreement(module: Any) -> Callable[[], None]:
    """Accept a missing close delimiter silently, as if the multipart were closed."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, _closed, gaps = result
        kept = [gap for gap in gaps if gap != GAP_BODY_BOUNDARY_DISAGREEMENT]
        return preamble, delimiters, chunks, epilogue, True, kept

    return _patch(module, "_segment", naive)


def _drop_preamble(module: Any) -> Callable[[], None]:
    """Drop the preamble from the accounting: no region, no ``body.preamble_bytes``."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, closed, gaps = result
        return RawSpan(preamble.offset, 0, ""), delimiters, chunks, epilogue, closed, gaps

    return _patch(module, "_segment", naive)


def _drop_epilogue(module: Any) -> Callable[[], None]:
    """Drop the epilogue from the accounting: no region, no ``body.epilogue_bytes``."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is None:
            return None
        preamble, delimiters, chunks, epilogue, closed, gaps = result
        return preamble, delimiters, chunks, RawSpan(epilogue.offset, 0, ""), closed, gaps

    return _patch(module, "_segment", naive)


def _drop_decode_fallback(module: Any) -> Callable[[], None]:
    """Let a broken transfer encoding fall back to the raw payload, recording no gap (d03)."""
    original = module._decode_cte

    def naive(payload: bytes, declared: str | None, *, limit: int | None = None):
        used_cte, decoded, fired, _gap = original(payload, declared, limit=limit)
        return used_cte, decoded, fired, None

    return _patch(module, "_decode_cte", naive)


def _drop_decode_destroyed(module: Any) -> Callable[[], None]:
    """Take the ``errors='replace'`` decode and record nothing lost (never the normal path)."""
    original = module._charset_ladder

    def naive(body: bytes, declared_charset: str | None):
        used_charset, source, fired, gap = original(body, declared_charset)
        if gap == GAP_BODY_DECODE_DESTROYED_BYTES:
            gap = None
        return used_charset, source, fired, gap

    return _patch(module, "_charset_ladder", naive)


def _drop_headers_only(module: Any) -> Callable[[], None]:
    """Read a headers-to-EOF message as a bodyless part and record no gap (spike a04)."""
    original = module._split_headers_body

    def naive(raw: bytes, start: int, end: int):
        headers, body, _gaps = original(raw, start, end)
        return headers, body, []

    return _patch(module, "_split_headers_body", naive)


def _invent_part(module: Any) -> Callable[[], None]:
    """Invent a child covering the whole body when the declared boundary never appears."""
    original = module._segment

    def naive(raw: bytes, body: RawSpan, boundary: bytes):
        result = original(raw, body, boundary)
        if result is not None:
            return result
        whole = RawSpan(body.offset, body.length, "")
        return RawSpan(body.offset, 0, ""), [RawSpan(body.offset, 0, "")], [whole], RawSpan(
            body.end, 0, ""
        ), True, []

    return _patch(module, "_segment", naive)


@dataclass(frozen=True)
class GapCase:
    """One gap's falsifiability case.

    ``fixture`` is a committed stem; ``inline`` is hand-typed bytes for a gap no committed
    fixture carries, with ``expected_gaps`` the ``part.gaps`` rows that bytes' minimal
    sidecar asserts (built by :func:`inline_sidecar`). ``patch`` performs the one-rule
    mutation; ``naive`` is what the careless walker did, for the failure text.
    """

    gap_id: str
    fact_id: str
    naive: str
    patch: Callable[[Any], Callable[[], None]]
    fixture: str | None = None
    inline: bytes | None = None
    expected_gaps: tuple[tuple[str, tuple[str, ...]], ...] = field(default=())

    def __post_init__(self) -> None:
        if (self.fixture is None) == (self.inline is None):
            raise ValueError(
                f"{self.gap_id}: exactly one of a committed fixture or inline bytes is needed"
            )
        if self.inline is not None and not self.expected_gaps:
            raise ValueError(f"{self.gap_id}: an inline case needs its expected part.gaps rows")


#: gap id -> its case. Kept in one block so the catalogue reads as a list, which it is.
_CASES: tuple[GapCase, ...] = (
    GapCase(
        gap_id=GAP_HEADERS_MALFORMED_LINE,
        fact_id="part.gaps",
        fixture="malformed_mime",
        patch=_drop_malformed_line,
        naive=(
            "swallowed the non-blank line that is neither a field nor a fold into the previous "
            "field, so the paragraph and the gap both vanished (D2 fails open and records it)"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_BOUNDARY_DISAGREEMENT,
        fact_id="part.gaps",
        fixture="malformed_mime",
        patch=_drop_boundary_disagreement,
        naive=(
            "accepted a missing close delimiter silently as if the multipart were closed, "
            "recording no gap for the grammar the bytes do not match"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_PREAMBLE_BYTES,
        fact_id="part.gaps",
        fixture="preamble_epilogue",
        patch=_drop_preamble,
        naive="padded the preamble away: no region and no body.preamble_bytes gap for those bytes",
    ),
    GapCase(
        gap_id=GAP_BODY_EPILOGUE_BYTES,
        fact_id="part.gaps",
        fixture="preamble_epilogue",
        patch=_drop_epilogue,
        naive="padded the epilogue away: no region and no body.epilogue_bytes gap for those bytes",
    ),
    GapCase(
        gap_id=GAP_BODY_DECODE_FALLBACK_USED,
        fact_id="part.gaps",
        fixture="truncated_base64",
        patch=_drop_decode_fallback,
        naive=(
            "fell back to the raw payload for a broken base64 run silently, as stdlib does, "
            "with no body.decode_fallback_used gap"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_DECODE_DESTROYED_BYTES,
        fact_id="part.gaps",
        fixture="bad_charset",
        patch=_drop_decode_destroyed,
        naive=(
            "took the errors='replace' decode and recorded nothing lost, so a byte the ladder "
            "destroyed looks like a clean round trip"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_HEADERS_ONLY,
        fact_id="part.gaps",
        inline=HEADERS_ONLY_BYTES,
        expected_gaps=(("1", (GAP_BODY_HEADERS_ONLY,)),),
        patch=_drop_headers_only,
        naive=(
            "read a headers-to-EOF message as an ordinary bodyless part and recorded no "
            "body.headers_only gap (no committed fixture carries this shape)"
        ),
    ),
    GapCase(
        gap_id=GAP_BODY_NO_BOUNDARY_FOUND,
        fact_id="part.gaps",
        inline=NO_BOUNDARY_BYTES,
        expected_gaps=(("1", (GAP_BODY_NO_BOUNDARY_FOUND,)),),
        patch=_invent_part,
        naive=(
            "invented a child covering the whole body when the declared boundary never "
            "appeared, instead of recording body.no_boundary_found and reading the body as a leaf"
        ),
    ),
)

#: gap id -> its case, in the order above.
CASES: Mapping[str, GapCase] = MappingProxyType({case.gap_id: case for case in _CASES})


@contextlib.contextmanager
def mutated(case: GapCase) -> Iterator[None]:
    """Run the walker with ``case``'s one-rule mutation applied, then restore it."""
    restore = case.patch(walk_module)
    try:
        yield
    finally:
        restore()


def exercised_gaps(sidecars: Mapping[str, Any]) -> set[str]:
    """Every gap id the given loaded sidecars record in ``part.gaps``."""
    found: set[str] = set()
    for sidecar in sidecars.values():
        fact = sidecar.facts.get("part.gaps")
        if fact is None or not isinstance(fact.value, list):
            continue
        for entry in fact.value:
            found |= set(entry[1])
    return found


def uncovered_gaps(sidecars: Mapping[str, Any]) -> set[str]:
    """The walker's gap ids that no committed fixture's ``part.gaps`` records."""
    return set(WALKER_GAPS) - exercised_gaps(sidecars)


def inline_sidecar(case: GapCase, raw: bytes) -> dict[str, Any]:
    """The minimal hand-typed sidecar for an inline case: the size and the expected gaps."""
    return {
        "fixture": f"{case.gap_id.replace('.', '_')}.eml",
        "labels_provenance": "spec",
        "facts": {
            "container.size_bytes": {"phase": 0, "value": len(raw)},
            "part.gaps": {
                "phase": 0,
                "value": [[path, list(gaps)] for path, gaps in case.expected_gaps],
            },
        },
    }


def describe(case: GapCase, stem: str, outcome: Any) -> str:
    """The failure text: the fixture, the fact and the gap id, then what the naive case did.

    This is the message a reviewer is handed when a careless implementation slips past the
    gate, so it names all three rather than leaving the reader to reassemble them.
    """
    status = getattr(outcome, "status", outcome)
    return (
        f"{stem}: fact {case.fact_id!r}: gap {case.gap_id!r}: "
        f"status={getattr(status, 'value', status)}, -- {case.naive}"
    )


# ---------------------------------------------------- Turn 1.10a: the phase-1 gaps
#
# The walker catalogue above covers Phase 0's ``part.gaps``; Turn 1.10a adds the **Phase 1** gap
# channel, ``gaps.later``. The mutation is a different shape: a phase-1 gap is emitted by a stage
# channel (not by the walker's one rule), so the careless case is a stage function that returns
# every pair *except* one -- and the claim is that the gap gate then fails on the sidecar that
# labels it, naming the gap id and the fixture.


#: The channels the oracle's ``gaps.later`` reads, ``(module, attribute name)``. Patching an
#: attribute on the module (not a name imported into ``l1``) is what reaches the oracle, because
#: ``l1._gaps_later`` looks each up at call time.
GAP_CHANNELS: tuple[tuple[Any, str], ...] = (
    (header_stage, "later_gaps"),
    (text_stage, "body_gaps"),
    (selection_stage, "body_gaps"),
    (attach_stage, "gap_pairs"),
    (quote_stage, "gap_pairs"),
    (quote_stage, "html_gap_pairs"),
    (l1_module, "_address_gap_pairs"),
)

#: Every phase-1 gap id a wired channel can emit: the ids the oracle compares (``LIVE_GAP_IDS``)
#: plus the three the quote stage emits but the frozen labels cannot satisfy (see the Turn 1.10a
#: finding in ``l1.LIVE_GAP_IDS``). Read off :data:`LIVE_GAP_IDS` so a new live id cannot be
#: forgotten here.
EMITTABLE_GAP_IDS: frozenset[str] = frozenset(LIVE_GAP_IDS) | frozenset(
    {
        quote_text_stage.GAP_NO_BOUNDARY_FOUND,
        quote_text_stage.GAP_INLINE_REPLY_INTERLEAVED,
        quote_stage.GAP_VIEW_QUOTE_LEVEL_DISAGREEMENT,
    }
)

#: Emittable ids **no committed fixture exercises against the gate** -- no sidecar labels them at a
#: phase-1 *live* row, so a dropped emission changes no verdict. Named here so they are never
#: silently tolerated (the workbook's "unlabelled emissions" list). Each reason:
#:
#: * ``body.html_quote_rule_gap`` -- emitted on ``vendor_prefix_class_no_table_row``, which its
#:   sidecar does not label (an unlabelled emission);
#: * ``body.inline_reply_interleaved``, ``body.no_boundary_found``, ``view.quote_level_disagreement``
#:   -- emitted on committed fixtures, but the only sidecars that label them assert rows the code
#:   cannot satisfy, so they wait in ``tests/ledger/phase1_exit.json`` (class ``b``);
#: * ``headers.date_no_zone`` -- live, but no committed fixture emits it and no sidecar labels it.
UNEXERCISED_GAP_IDS: frozenset[str] = frozenset(
    {
        "body.html_quote_rule_gap",
        "body.inline_reply_interleaved",
        "body.no_boundary_found",
        "headers.date_no_zone",
        "view.quote_level_disagreement",
    }
)


def _drop_id(module: Any, name: str, gap_id: str) -> Callable[[], None]:
    """Patch ``module.name`` to return every ``(gap_id, locator)`` pair except ``gap_id``'s."""
    original = getattr(module, name)

    def naive(*args: Any, **kwargs: Any) -> Any:
        returned = original(*args, **kwargs)
        if not isinstance(returned, list):
            return returned
        return [pair for pair in returned if pair[0] != gap_id]

    return _patch(module, name, naive)


def drop_everywhere(gap_id: str) -> Callable[[Any], Callable[[], None]]:
    """A one-gap mutation: every wired channel stops returning ``gap_id``.

    Dropping the id on *every* channel (not just the one the chosen fixture happens to use) is
    what makes the gate's failure the mutation's: an id emitted by two channels would otherwise
    survive on the other, and the case would pass vacuously.
    """

    def patch(_module: Any) -> Callable[[], None]:
        restores = [_drop_id(module, name, gap_id) for module, name in GAP_CHANNELS]
        return lambda: [restore() for restore in restores]

    return patch


def _phase1_case(gap_id: str, fixture: str, naive: str) -> GapCase:
    return GapCase(
        gap_id=gap_id,
        fact_id="gaps.later",
        fixture=fixture,
        patch=drop_everywhere(gap_id),
        naive=naive,
    )


#: gap id -> the committed fixture that labels it at a live phase-1 row. Kept in one block so the
#: catalogue reads as a list, which it is. Every id here is in :data:`EMITTABLE_GAP_IDS`; the ids
#: that are not are named in :data:`UNEXERCISED_GAP_IDS`.
_PHASE1_CASES: tuple[GapCase, ...] = (
    _phase1_case(
        address_stage.GAP_HEADERS_ADDRESS_UNPARSABLE,
        "address_unparsable",
        "accepted an unparseable address list silently, recording no headers.address_unparsable "
        "row (D2/D9: the raw fragment is kept and its state recorded)",
    ),
    _phase1_case(
        header_stage.GAP_HEADERS_DUPLICATE_HEADER,
        "duplicate_content_type_header",
        "took the first field's value and kept the duplicate silently, as the walker's first-win "
        "does, recording no headers.duplicate_header row",
    ),
    _phase1_case(
        header_stage.GAP_HEADERS_LEADING_BOM,
        "leading_utf8_bom",
        "stripped the leading U+FEFF into the first field's name and recorded no headers.leading_bom",
    ),
    _phase1_case(
        header_stage.GAP_HEADERS_MBOX_FROM_LINE,
        "mbox_from_line_at_zero",
        "read the mbox `From ` line as an ordinary field and recorded no headers.mbox_from_line",
    ),
    _phase1_case(
        header_stage.GAP_BODY_LONE_CR_LINE_TERMINATOR,
        "lone_cr_in_header_region",
        "treated a lone CR as whitespace rather than a line terminator, recording no "
        "body.lone_cr_line_terminator",
    ),
    _phase1_case(
        header_stage.GAP_HEADERS_ENCODED_WORD_INVALID,
        "encoded_word_invalid",
        "decoded the malformed encoded word as if it were well formed and recorded no "
        "headers.encoded_word_invalid",
    ),
    _phase1_case(
        date_stage.GAP_HEADERS_NO_DATE,
        "date_absent",
        "invented a Date value for a message with no Date field instead of recording "
        "headers.no_date",
    ),
    _phase1_case(
        date_stage.GAP_HEADERS_INVALID_DATE,
        "date_invalid",
        "took a Date the parser cannot read as if it parsed, recording no headers.invalid_date",
    ),
    _phase1_case(
        text_stage.GAP_BODY_FLOWED_REFLOW_UNRESOLVED,
        "flowed_quote_depth",
        "reflowed a format=flowed part's soft breaks into a joined paragraph (the v1 deferral) "
        "and recorded no body.flowed_reflow_unresolved",
    ),
    _phase1_case(
        selection_stage.GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED,
        "multipart_digest_content_type_less_child",
        "applied the multipart/digest message/rfc822 default to a Content-Type-less child and "
        "recorded no body.digest_default_not_applied",
    ),
    _phase1_case(
        selection_stage.GAP_BODY_NO_TEXT_PART,
        "body_no_text_part",
        "claimed an empty body for a message with no text part instead of recording "
        "body.no_text_part",
    ),
    _phase1_case(
        selection_stage.GAP_SECURITY_REMOTE_CONTENT_PRESENT,
        "attach_remote_image_only",
        "recorded a remote reference as fetched content and raised no "
        "security.remote_content_present",
    ),
    _phase1_case(
        selection_stage.GAP_BODY_INLINE_DATA_URI,
        "html_data_uri_and_tracking_pixel",
        "treated a data: URI as an ordinary reference and recorded no body.inline_data_uri",
    ),
    _phase1_case(
        quote_text_stage.GAP_I18N_REPLY_MARKER,
        "i18n_reply_marker",
        "presented a label-shaped unknown-language block as `no boundary found` instead of "
        "recording body.i18n_reply_marker (decision 3)",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_CID_UNREFERENCED,
        "attach_decoration_tracking_pixel",
        "recorded a cid no body view references without an attach.cid_unreferenced row",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_DUPLICATE_CONTENT_ID,
        "attach_duplicate_content_id",
        "kept two parts with one Content-ID without recording attach.duplicate_content_id",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_FILENAME_ABSENT,
        "attach_message_rfc822_no_filename",
        "invented a filename for a part that carries none instead of recording "
        "attach.filename_absent",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_OCCURRENCE_REPEATED,
        "attach_duplicate_filename_in_one_message",
        "recorded one attachment for two parts with the same filename instead of "
        "attach.occurrence_repeated",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_OLE_CONTAINER_UNKNOWN,
        "attach_ole_cfb_magic",
        "claimed the OLE container's contents instead of recording attach.ole_container_unknown "
        "(introspection declines it)",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_TNEF_PRESENT,
        "attach_tnef_winmail",
        "claimed the TNEF attachment's contents instead of recording attach.tnef_present (a "
        "decline, not an extraction)",
    ),
    _phase1_case(
        attach_stage.GAP_ATTACH_TYPE_DISAGREEMENT,
        "attach_zip_magic_declared_disagree",
        "preferred the declared media type over the magic and recorded no "
        "attach.type_disagreement",
    ),
    _phase1_case(
        attach_stage.GAP_SECURITY_MACRO_PRESENT,
        "attach_macro_docm",
        "recorded a macro-enabled document without a security.macro_present row",
    ),
)

#: gap id -> its phase-1 case, in the order above.
PHASE1_CASES: Mapping[str, GapCase] = MappingProxyType(
    {case.gap_id: case for case in _PHASE1_CASES}
)
