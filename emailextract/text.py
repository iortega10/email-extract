"""Turn 1.4: per-part text, the charset alias table, offset maps, the one line model.

This is the part that turns one part's **body bytes** into the part's **decoded text** and
says, in the recorded vocabulary of decision 8, how far that text can be traced back into the
raw message.

The three recorded facts (D12, decision 8):

* the MIME part's raw span is always exact and always carried -- that is the walker's
  ``part.regions`` / ``part.body_span``, untouched here;
* the decoded char span is always exact **within its named, versioned projection**
  (:data:`~emailextract.versions.TEXTPART_VERSION`);
* the **within-part byte span** is ``exact`` only for a *strict* decode of the **used**
  charset (never the declared one) over a **stateless** charset (single-byte or UTF-8) whose
  CTE was **identity**; every other case is ``part_level`` with a closed
  ``verbatim_reason`` and **no within-part byte span at all**.

The coordinate space is the part's decoded text in code points, **un-normalised**: no CRLF or
LF folding, no NFC, no BOM strip for plain ``utf-8``. CRLF stays two code points.

Design decisions this module owns, and the labels that forced them (the bytes are the judge):

1. **``verbatim_reason`` precedence.** ``cte_not_identity`` is keyed on the CTE that
   *actually ran* (the walker's ``used_cte``), not the declared one -- the labels force this:
   ``base64_with_whitespace_and_bad_padding`` declares ``base64`` whose decoding *failed*
   (``used_cte is None``) and the sidecar types ``decode_fallback``, while
   ``cap_very_long_base64_run``'s ``base64`` decodes and the sidecar types
   ``cte_not_identity``. Precedence: **cte_not_identity, then decode_fallback, then
   multibyte_without_offset_map**. ``qp_raw_8bit`` (``quoted-printable`` ->
   ``cte_not_identity``), ``gb2312_declared_gbk_bytes`` (identity CTE, the declared charset
   fell to the ``windows-1252`` rung -> ``decode_fallback``) and ``iso_2022_jp_stateful``
   (identity CTE, strictly decoded, stateful -> ``multibyte_without_offset_map``) each
   reproduce their typed reason under this one order.
2. **No alias widens a charset.** ``windows_1252_declared_iso_8859_1`` declares
   ``iso-8859-1`` over C1 bytes and the sidecar types ``U+0093``/``U+0094`` (an exact
   ``iso-8859-1`` decode): a ``iso-8859-1 -> windows-1252`` substitution would contradict it.
   ``gb2312`` declared over non-gb2312 bytes falls to the walker's ``windows-1252`` rung with
   the fallback recorded; a ``gb2312 -> gbk`` widening alias would contradict that.
3. **RFC 3676 space-unstuffing is applied to the stored ``body.text``** for a part declaring
   ``format=flowed`` (the label's own provenance note:
   ``flowed_unstuffed_soft_break`` types ``A soft break ends here \r\nand this line was
   space-stuffed.\r\n`` -- the stuffing space of the second line is gone). The **soft-break
   join is deferred, never performed**, and the part records
   :data:`GAP_BODY_FLOWED_REFLOW_UNRESOLVED`. A dropped stuffing byte is a real byte of the
   body that produces no character, so the offset map carries it as a **zero-character
   span**; that is what keeps the map's partition of ``[0, len(raw))`` and
   ``[0, len(text))`` honest.
4. **The offset map is one entry per run**, not per code point: a maximal run of code points
   that each consume the same number of bytes is one entry (so a 1 MB single-byte body is one
   entry, not a million). A code point consuming ``k > 1`` bytes is its own entry; a run of
   dropped bytes (a stuffing space) is its own zero-character entry. The entry is
   ``(byte_offset, byte_length, char_offset, char_length)`` and the entries are strictly
   increasing and partition both ranges.
5. **No map is claimed unless it validates**: a charset is map-eligible unless its canonical
   codec name is in the closed :data:`NOT_OFFSET_MAPPABLE` set (the stateful/multibyte charsets,
   plus ``utf-8-sig``, whose encode is not the decode's inverse), and the map *then* has to pass
   a structural check -- the byte runs must consume the body exactly and the char runs must
   cover the text exactly -- before it is emitted; a map that fails is dropped and the part
   falls back to ``multibyte_without_offset_map`` rather than being emitted unsound.

The one line model (decision 8, the lone-CR finding): :func:`line_bounds` is the **public
accessor** to ``walk.iter_lines``. Nothing here splits lines a second way -- in particular
``bytes.splitlines``/``str.splitlines`` are forbidden for body text, because they also break
on form feed, vertical tab, U+2028 and (after decoding) U+0085, which are not line breaks in
RFC 5322 or in the walker's model.

Caps (decision 9) are caller parameters and this stage takes none: the decode and the map are
linear in the part's body, and the body is already bounded at the entry point
(``Limits.max_input_bytes``, ``emailextract.parse``), so a second cap here could only change
the *text*, which the labels type in full.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from .versions import TEXTPART_VERSION
from .walk import PartShape, WalkResult, _decode_cte, _split_params, iter_lines

__all__ = [
    "CHARSET_ALIASES",
    "GAP_BODY_FLOWED_REFLOW_UNRESOLVED",
    "GAP_IDS",
    "OffsetSpan",
    "PartText",
    "REASON_CTE_NOT_IDENTITY",
    "REASON_DECODE_FALLBACK",
    "REASON_MULTIBYTE_WITHOUT_OFFSET_MAP",
    "STATEFUL_OR_MULTIBYTE",
    "VERBATIM_EXACT",
    "VERBATIM_PART_LEVEL",
    "VERBATIM_REASONS",
    "analyse_part",
    "analyse_parts",
    "body_gaps",
    "canonical_charset",
    "charset_known",
    "decoded_payload",
    "flowed_declared",
    "line_bounds",
    "part_text_rows",
]


#: The closed ``verbatim_precision`` vocabulary (decision 8, the facts doc).
VERBATIM_EXACT: Final[str] = "exact"
VERBATIM_PART_LEVEL: Final[str] = "part_level"

#: The closed ``verbatim_reason`` vocabulary; ``None`` (not a member) means ``exact``.
REASON_CTE_NOT_IDENTITY: Final[str] = "cte_not_identity"
REASON_DECODE_FALLBACK: Final[str] = "decode_fallback"
REASON_MULTIBYTE_WITHOUT_OFFSET_MAP: Final[str] = "multibyte_without_offset_map"
VERBATIM_REASONS: Final[tuple[str, ...]] = (
    REASON_CTE_NOT_IDENTITY,
    REASON_DECODE_FALLBACK,
    REASON_MULTIBYTE_WITHOUT_OFFSET_MAP,
)

#: The non-identity CTEs the walker's ``_decode_cte`` records as **having run**.
NON_IDENTITY_CTES: Final[frozenset[str]] = frozenset({"base64", "quoted-printable"})

#: The Phase 1 gap this stage records: a ``format=flowed`` part whose soft line breaks are
#: **not** joined (RFC 3676 4.4 unstuffing runs; 4.5 reflow does not, in v1).
GAP_BODY_FLOWED_REFLOW_UNRESOLVED: Final[str] = "body.flowed_reflow_unresolved"

#: Every gap id this stage can emit. A catalogue test fails if one of these has no
#: anti-vacuity case, and if the analyser emits an id that is not here (the same rule
#: ``evals/falsify.py`` holds for the walker's own gaps).
GAP_IDS: Final[tuple[str, ...]] = (GAP_BODY_FLOWED_REFLOW_UNRESOLVED,)

#: The **closed** set of canonical codec names that are stateful or multibyte, so no 1:1
#: code-point map exists over their bytes. Sources: the IANA "Character Sets" registry's
#: stateful/multibyte entries (ISO-2022-*, EUC-*, Shift_JIS, GB2312/GBK/GB18030, Big5, HZ) as
#: spelled by the Python ``codecs`` canonical names (``codecs.lookup(name).name``).
STATEFUL_OR_MULTIBYTE: Final[frozenset[str]] = frozenset(
    {
        "big5",
        "big5hkscs",
        "cp932",
        "cp949",
        "cp950",
        "cp1361",
        "euc_jis_2004",
        "euc_jisx0213",
        "euc_jp",
        "euc_kr",
        "gb18030",
        "gb2312",
        "gbk",
        "hz",
        "iso2022_jp",
        "iso2022_jp_1",
        "iso2022_jp_2",
        "iso2022_jp_2004",
        "iso2022_jp_3",
        "iso2022_jp_ext",
        "iso2022_kr",
        "johab",
        "shift_jis",
        "shift_jis_2004",
        "shift_jisx0213",
        "utf-16",
        "utf-16-be",
        "utf-16-le",
        "utf-32",
        "utf-32-be",
        "utf-32-le",
        "utf-7",
    }
)

#: The UTF-8 family whose code-point byte lengths come from the lead byte (RFC 3629) **and**
#: whose encode is the decode's inverse, which is what ``exact`` needs.
UTF8_FAMILY: Final[frozenset[str]] = frozenset({"utf-8"})

#: The charsets for which **no** offset map is claimed. ``utf-8-sig`` is here on purpose and
#: not because it is multibyte: it consumes a leading BOM and its ``encode`` re-adds one, so
#: ``text.encode(used) == body`` is not the identity -- "a UTF-8 BOM stays exact for plain
#: ``utf-8`` and breaks only under ``utf-8-sig`` or a U+FEFF strip" (decision 8). It needs a
#: reason from the closed vocabulary, and ``multibyte_without_offset_map`` is the one that
#: means "there is no map here".
NOT_OFFSET_MAPPABLE: Final[frozenset[str]] = STATEFUL_OR_MULTIBYTE | frozenset({"utf-8-sig"})

#: **The charset alias table** (decision 8, this turn's item 4): spelling -> canonical codec
#: name, always lowercased, with the RFC 2231 ``*language`` suffix stripped first.
#:
#: It is for **spellings only** and it never widens a charset: no ``gb2312 -> gbk``, no
#: ``iso-8859-1 -> windows-1252``, no ``ascii -> utf-8``. Every value is already canonical
#: (``codecs.lookup(value).name == value``), so no two rows collide on a codec, and every key
#: is sorted. A name that is not in the table is **not an alias**: resolution then falls back
#: to ``codecs.lookup`` exactly as it did before this turn (so an unknown name stays unknown,
#: never an exception), which is how the walker's charset ladder already handles it.
#: Each row cites its source: an IANA registry name, or a Python ``codecs`` alias.
CHARSET_ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "ansi_x3.4-1968": "ascii",  # IANA US-ASCII alias; Python codecs alias
        "ascii": "ascii",  # IANA US-ASCII; Python canonical name
        "big5": "big5",  # IANA Big5; Python canonical name
        "cp1252": "cp1252",  # Python canonical name (IANA Windows-1252)
        "euc-jp": "euc_jp",  # IANA EUC-JP; Python canonical name
        "gb18030": "gb18030",  # IANA GB18030; Python canonical name
        "gb2312": "gb2312",  # IANA GB2312; Python canonical name
        "gbk": "gbk",  # IANA GBK; Python canonical name
        "hz-gb-2312": "hz",  # IANA HZ-GB-2312; Python canonical name
        "iso-2022-jp": "iso2022_jp",  # IANA ISO-2022-JP; Python canonical name
        "iso-8859-1": "iso8859-1",  # IANA ISO-8859-1; Python canonical name
        "iso-8859-15": "iso8859-15",  # IANA ISO-8859-15; Python canonical name
        "iso-8859-2": "iso8859-2",  # IANA ISO-8859-2; Python canonical name
        "iso-8859-9": "iso8859-9",  # IANA ISO-8859-9; Python canonical name
        "koi8-r": "koi8-r",  # IANA KOI8-R; Python canonical name
        "latin-1": "iso8859-1",  # Python codecs alias for ISO-8859-1
        "latin1": "iso8859-1",  # Python codecs alias for ISO-8859-1
        "shift_jis": "shift_jis",  # IANA Shift_JIS; Python canonical name
        "us-ascii": "ascii",  # IANA US-ASCII; Python codecs alias
        "utf-16": "utf-16",  # IANA UTF-16; Python canonical name
        "utf-16-be": "utf-16-be",  # IANA UTF-16BE; Python canonical name
        "utf-32": "utf-32",  # IANA UTF-32; Python canonical name
        "utf-8": "utf-8",  # IANA UTF-8; Python canonical name
        "utf-8-sig": "utf-8-sig",  # Python codecs name (a BOM-consuming UTF-8)
        "utf8": "utf-8",  # Python codecs alias for UTF-8
        "windows-1252": "cp1252",  # IANA Windows-1252; Python canonical name
    }
)


def canonical_charset(charset: str) -> str | None:
    """The canonical codec name ``charset`` resolves to, or ``None`` when it does not.

    This is the package's **one** charset resolution point (Turn 1.4):
    :func:`emailextract.rfc2047.canonical_charset` delegates here. An RFC 2231 section 5
    language suffix (``utf-8*en``) is not part of the charset and is stripped first. The
    closed :data:`CHARSET_ALIASES` table answers the spellings it names; anything else goes to
    ``codecs.lookup`` exactly as before, so a name Python does not know is unknown here too
    (``None``), and a name that is merely a spelling of a known codec still resolves. Never
    raises: a NUL, a space, a quote or an absurd length is an unknown name, not an exception.
    """
    name = charset.split("*", 1)[0]
    if not name:
        return None
    aliased = CHARSET_ALIASES.get(name.lower())
    if aliased is not None:
        return aliased
    try:
        return codecs.lookup(name).name
    except (LookupError, ValueError, TypeError):
        return None


def charset_known(charset: str) -> bool:
    """Whether ``charset`` resolves to a codec (the same resolution the walker's ladder uses)."""
    return canonical_charset(charset) is not None


def line_bounds(raw: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    """The one line model's lines over ``[start, end)``: ``(line_start, content_end, term_end)``.

    A public accessor over :func:`emailextract.walk.iter_lines` -- one implementation, never a
    copy. ``term_end`` is ``content_end + 1`` for LF or a lone CR and ``content_end + 2`` for
    CRLF; the last line at EOF may have ``term_end == content_end``.
    """
    return list(iter_lines(raw, start, end))


@dataclass(frozen=True)
class OffsetSpan:
    """One entry of an offset map: a byte run and the code-point run it produces.

    ``char_length`` is ``0`` for a byte run that produces **no** character -- the byte is real
    and must still be accounted for (a dropped RFC 3676 stuffing space, a ``utf-8-sig`` BOM),
    which is why a zero-character entry exists at all: the entries partition
    ``[0, len(raw))`` *and* ``[0, len(text))``.
    """

    byte_offset: int
    byte_length: int
    char_offset: int
    char_length: int

    def __post_init__(self) -> None:
        if self.byte_offset < 0 or self.byte_length < 1:
            raise ValueError("an offset-map entry claims at least one byte at a non-negative offset")
        if self.char_offset < 0 or self.char_length < 0:
            raise ValueError("an offset-map entry has a non-negative char offset and length")

    @property
    def byte_end(self) -> int:
        return self.byte_offset + self.byte_length

    @property
    def char_end(self) -> int:
        return self.char_offset + self.char_length

    def as_row(self) -> list[int]:
        """The entry as the plain ``[byte_offset, byte_length, char_offset, char_length]`` row."""
        return [self.byte_offset, self.byte_length, self.char_offset, self.char_length]


@dataclass(frozen=True)
class PartText:
    """One text part's decoded text, its ``verbatim_precision`` and its offset map.

    ``offset_map`` is ``None`` **absent** when the precision is ``part_level`` (a within-part
    byte span is not emitted at all); it is an empty tuple only for an ``exact`` part whose
    body is empty (there is a map, it has no entries). ``flowed``/``delsp`` are the parsed
    ``format=flowed``/``delsp`` parameters -- ``delsp`` is **recorded, never applied**.
    """

    path: str
    text: str
    verbatim_precision: str
    verbatim_reason: str | None
    declared_charset: str | None
    used_charset: str | None
    used_cte: str | None
    offset_map: tuple[OffsetSpan, ...] | None = None
    flowed: bool = False
    delsp: bool = False
    gaps: tuple[str, ...] = ()
    projection_version: str = TEXTPART_VERSION

    def as_fact_row(self) -> list[object]:
        """The ``body.text`` row: ``[part, text, verbatim_precision, verbatim_reason]``."""
        return [self.path, self.text, self.verbatim_precision, self.verbatim_reason]


def flowed_declared(raw: bytes, part: PartShape) -> tuple[bool, bool]:
    """``(flowed, delsp)`` from the part's **parsed** ``Content-Type`` parameters.

    The parameter names and values are compared case-insensitively, exactly as
    ``walk._split_params`` lowercases the names; the walker's own parser is reused so there is
    one Content-Type split in the package. ``delsp`` is recorded and never applied (RFC 3676
    4.4: v1 does not reflow, so there is nothing for DelSp to change).
    """
    for item in part.header_fields:
        if item.parse_status != "ok" or item.name.lower() != "content-type":
            continue
        value = raw[item.value_span.offset : item.value_span.end].decode("latin-1")
        _media, params = _split_params(value)
        return params.get("format", "").lower() == "flowed", "delsp" in params
    return False, False


def _unstuff(plain: str) -> tuple[str, frozenset[int]]:
    """RFC 3676 4.4 space-unstuffing over already-decoded text: drop one leading stuffed space.

    Returns the unstuffed text and the set of **character indices of ``plain``** that were
    dropped, so the offset map can record those bytes as zero-character spans. A line whose
    content begins with a single space has that one space removed (a line whose content really
    began with a space was stuffed to two spaces and so keeps one). Line boundaries come from
    the one line model over the *bytes*; a stuffing space is always the first character of an
    ASCII-compatible line, which is the only place this can fire.
    """
    if " " not in plain:
        return plain, frozenset()
    dropped: set[int] = set()
    for index, char in enumerate(plain):
        if char != " ":
            continue
        if index == 0 or plain[index - 1] in "\r\n":
            dropped.add(index)
    if not dropped:
        return plain, frozenset()
    text = "".join(char for index, char in enumerate(plain) if index not in dropped)
    return text, frozenset(dropped)


def _utf8_byte_lengths(body: bytes) -> list[int] | None:
    """The byte length of each UTF-8 code point in ``body``, or ``None`` if it is not UTF-8.

    From the lead byte only (RFC 3629); the bytes were already decoded **strictly**, so a
    sequence here cannot be malformed -- but a truncated tail still returns ``None`` rather
    than guessing.
    """
    lengths: list[int] = []
    index = 0
    while index < len(body):
        lead = body[index]
        if lead < 0x80:
            size = 1
        elif lead >> 5 == 0b110:
            size = 2
        elif lead >> 4 == 0b1110:
            size = 3
        elif lead >> 3 == 0b11110:
            size = 4
        else:
            return None
        if index + size > len(body):
            return None
        lengths.append(size)
        index += size
    return lengths


def _byte_runs(
    body: bytes, plain_length: int, canonical: str
) -> list[tuple[int, int, int]] | None:
    """``(byte_offset, byte_length, char_length)`` per code point over a strict decode.

    Or ``None`` when the charset is not one whose code points can be located in the bytes.
    ``utf-8-sig`` consumes a leading BOM and emits no character for its three bytes, so that
    run is reported with ``char_length = 0``. ``plain_length`` is the length of the decoded
    text (the BOM is not in it); the runs' ``char_length`` must sum to exactly that, which is
    the structural check that catches a codec the single-byte assumption is wrong for.
    """
    if canonical in UTF8_FAMILY:
        lengths = _utf8_byte_lengths(body)
        if lengths is None:
            return None
        runs: list[tuple[int, int, int]] = []
        offset = 0
        for size in lengths:
            runs.append((offset, size, 1))
            offset += size
        if offset != len(body):
            return None
        if sum(char_length for _bo, _bl, char_length in runs) != plain_length:
            return None
        return runs
    if canonical in NOT_OFFSET_MAPPABLE:
        return None
    # A single-byte charmap: one byte per code point, and every byte decodes (Python's
    # single-byte codecs map all 256). A length mismatch means the assumption is wrong for
    # this codec, so no map is claimed.
    if len(body) != plain_length:
        return None
    return [(index, 1, 1) for index in range(len(body))]


def _merge(spans: list[OffsetSpan]) -> list[OffsetSpan]:
    """Merge adjacent entries that each consume bytes 1:1 (or that each produce no character)."""
    merged: list[OffsetSpan] = []
    for span in spans:
        if merged:
            last = merged[-1]
            one_to_one = last.char_length == last.byte_length and span.char_length == span.byte_length
            no_character = last.char_length == 0 and span.char_length == 0
            if last.char_end == span.char_offset and last.byte_end == span.byte_offset and (
                one_to_one or no_character
            ):
                merged[-1] = OffsetSpan(
                    last.byte_offset,
                    last.byte_length + span.byte_length,
                    last.char_offset,
                    last.char_length + span.char_length,
                )
                continue
        merged.append(span)
    return merged


def _build_offset_map(
    body: bytes, plain_length: int, dropped: frozenset[int], canonical: str
) -> tuple[OffsetSpan, ...] | None:
    """Build the offset map, or ``None`` when no sound 1:1 map exists over these bytes.

    Sound means: the byte runs consume ``body`` exactly, the char runs cover the unstuffed
    text exactly, and the entries are strictly increasing and contiguous in both ranges.

    Two cases are answered without walking the body byte by byte: a body with nothing dropped
    whose bytes are all one byte per code point is a single entry (that is the whole 1 MB
    linearity case). Everything else -- a dropped RFC 3676 stuffing space, a multibyte body --
    takes the per-code-point path.
    """
    if not dropped and canonical:
        if canonical in UTF8_FAMILY:
            lengths = _utf8_byte_lengths(body)
            if lengths is None:
                return None
            if all(size == 1 for size in lengths):
                return (OffsetSpan(0, len(body), 0, len(body)),) if body else ()
        elif canonical not in NOT_OFFSET_MAPPABLE and len(body) == plain_length:
            return (OffsetSpan(0, len(body), 0, len(body)),) if body else ()
    runs = _byte_runs(body, plain_length, canonical)
    if runs is None:
        return None
    spans: list[OffsetSpan] = []
    char_offset = 0
    plain_index = 0
    for byte_offset, byte_length, char_length in runs:
        kept = 0 if (char_length == 1 and plain_index in dropped) else char_length
        spans.append(OffsetSpan(byte_offset, byte_length, char_offset, kept))
        plain_index += char_length
        char_offset += kept
    if not spans:
        return () if not body and plain_length == 0 else None
    merged = _merge(spans)
    expected_chars = plain_length - len(dropped)
    if merged[0].byte_offset != 0 or merged[-1].byte_end != len(body):
        return None
    if merged[0].char_offset != 0 or merged[-1].char_end != expected_chars:
        return None
    previous_byte = 0
    previous_char = 0
    for span in merged:
        if span.byte_offset != previous_byte or span.char_offset != previous_char:
            return None
        previous_byte = span.byte_end
        previous_char = span.char_end
    return tuple(merged)


def analyse_part(raw: bytes, part: PartShape) -> PartText | None:
    """The part's text and precision, or ``None`` when the part is not a text part.

    The walker's **existing** text-part decision is reused, not widened: only a part that ran
    the charset ladder has a ``used_charset``, so ``used_charset is None`` is exactly "the
    walker did not treat this as text" (a multipart, a pdf, a png, an office zip).
    """
    chain = part.decode_chain
    used = chain.used_charset
    if used is None:
        return None
    payload = raw[part.body_span.offset : part.body_span.end]
    used_cte, decoded, _cte_fired, _cte_gap = _decode_cte(payload, chain.declared_cte)
    if part.encoding_source is not None and part.encoding_source.value == "fallback":
        # The recorded last resort: windows-1252 with errors="replace". It never round-trips.
        decoded_text = decoded.decode("windows-1252", "replace")
    else:
        decoded_text = decoded.decode(used, "strict")
    flowed, delsp = flowed_declared(raw, part)

    plain = decoded_text
    dropped: frozenset[int] = frozenset()
    if flowed:
        plain, dropped = _unstuff(decoded_text)
    canonical = canonical_charset(used)

    gaps: list[str] = []
    if flowed:
        gaps.append(GAP_BODY_FLOWED_REFLOW_UNRESOLVED)

    reason = _verbatim_reason(
        used_cte=used_cte,
        fallback_fired=chain.fallback_fired,
        encoding_source=part.encoding_source,
        canonical=canonical,
    )
    offset_map: tuple[OffsetSpan, ...] | None = None
    if reason is None:
        offset_map = _build_offset_map(decoded, len(decoded_text), dropped, canonical or "")
        if offset_map is None:
            reason = REASON_MULTIBYTE_WITHOUT_OFFSET_MAP
    return PartText(
        path=part.path,
        text=plain,
        verbatim_precision=VERBATIM_EXACT if reason is None else VERBATIM_PART_LEVEL,
        verbatim_reason=reason,
        declared_charset=chain.declared_charset,
        used_charset=used,
        used_cte=used_cte,
        offset_map=offset_map,
        flowed=flowed,
        delsp=delsp,
        gaps=tuple(gaps),
    )


def _verbatim_reason(
    *,
    used_cte: str | None,
    fallback_fired: bool,
    encoding_source: object,
    canonical: str | None,
) -> str | None:
    """The closed ``verbatim_reason``, or ``None`` for ``exact`` (the precedence in the module doc).

    1. ``cte_not_identity`` -- the CTE that **ran** was base64 or quoted-printable;
    2. ``decode_fallback`` -- the walker's ladder fired a fallback rung
       (``fallback_fired``), or the recorded last resort (``encoding_source=fallback``) was
       taken;
    3. ``multibyte_without_offset_map`` -- the used charset is stateful or multibyte.
    """
    if used_cte in NON_IDENTITY_CTES:
        return REASON_CTE_NOT_IDENTITY
    source = getattr(encoding_source, "value", None)
    if fallback_fired or source == "fallback":
        return REASON_DECODE_FALLBACK
    if canonical is None or canonical in NOT_OFFSET_MAPPABLE:
        return REASON_MULTIBYTE_WITHOUT_OFFSET_MAP
    return None


def decoded_payload(raw: bytes, part: PartShape) -> bytes | None:
    """The part's transfer-decoded **payload bytes**, or ``None`` when it has none to give.

    Turn 1.8's narrow exposure (the attachment stage reads a bounded prefix of a part's payload
    and its decoded size): this is the same decode the walker ran and hashed, through the same
    ``walk._decode_cte`` `analyse_part` uses, so nothing here is a second decode *rule*.

    ``None`` has exactly one cause: the walker **skipped** the part for a size cap and left
    ``part.body_sha256 = None`` (Turn 1.5c: nothing was decoded, so there are no payload bytes and
    a caller must never decode them again). A multipart's ``body_sha256`` is also ``None``; its
    bytes are its children's regions rather than a payload, so ``None`` is the honest answer there
    too. A leaf whose decode produced no bytes returns ``b""`` -- not ``None``: the bytes exist and
    are empty, which is a different fact from "the part was not read".
    """
    if part.body_sha256 is None:
        return None
    payload = raw[part.body_span.offset : part.body_span.end]
    _used_cte, decoded, _fired, _gap = _decode_cte(payload, part.decode_chain.declared_cte)
    return decoded


def analyse_parts(raw: bytes, result: WalkResult) -> tuple[PartText, ...]:
    """Every text part of ``result``, in the walker's part order."""
    records: list[PartText] = []
    for part in result.parts:
        record = analyse_part(raw, part)
        if record is not None:
            records.append(record)
    return tuple(records)


def part_text_rows(raw: bytes, result: WalkResult) -> list[list[object]]:
    """The ``body.text`` rows: ``[part, text, verbatim_precision, verbatim_reason]`` per text part."""
    return [record.as_fact_row() for record in analyse_parts(raw, result)]


def body_gaps(raw: bytes, result: WalkResult) -> list[tuple[str, str]]:
    """The ``(gap_id, locator)`` pairs this stage records for ``gaps.later``.

    The Phase 1 gap channel, never the walker's Phase 0 ``part.gaps`` (decision 3): a
    ``format=flowed`` part's deferred reflow is recorded beside it, exactly as the header
    stage records its own gaps (and the oracle reads both through ``gaps.later``).
    """
    return [
        (gap_id, record.path)
        for record in analyse_parts(raw, result)
        for gap_id in record.gaps
    ]
