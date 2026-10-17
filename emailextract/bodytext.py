"""Turn BODY1: the body text and the attachment bytes, on demand and never stored.

The library has always *decoded* bodies -- ``text.py``'s charset ladder and transfer-encoding
decode, ``htmltext.py``'s HTML projection -- because it computes a digest over them. Nothing
handed the text back: ``model.py``'s contract says "no body text is stored", and a consumer
(the docextract hub) can therefore neither search a letter's body nor read an attached
invoice. This module exposes what is already computed, twice, without changing a record:

* :func:`body_text` -- the **same body view D14 digests** (HTML if present, else plain),
  its decoded text, a line-by-line segment table with a locator each, a truncation flag and
  the stamps. A message with no text body view returns an empty record with
  ``reason_id="body.no_text_part"``; a message that cannot be decoded at all returns an
  :class:`BodyRefusal` carrying the closed reason the entry point already records.
* :func:`iter_attachment_payloads` -- every non-decorative attachment occurrence's decoded
  payload bytes, in the manifest's own occurrence order, joined to the manifest by the same
  ``occurrence_ref`` an ``AttachmentOccurrence`` carries, under a per-attachment and a
  total byte ceiling and a count ceiling.

The rules this module owns, each with its own named test
-------------------------------------------------------

1. **One view rule.** The view is not re-derived here: :func:`emailextract.assemble.selected_body_text`
   is the function ``_content_fingerprint`` uses, so ``body_text(...).view`` **is**
   ``document.content_fingerprint.body_digest_view`` for every message, and the text is over
   the same code points the digest is taken over.
2. **Nothing is stored or cached.** Both functions read the container, measure, return and
   forget. No field is added to any record, no byte of either result reaches a manifest, and
   a second call re-reads the message.
3. **The bounds are the library's own.** Both functions build ``parse.Limits.untrusted()``
   -- the approved caps -- so ``max_input_bytes`` bounds the input, ``max_size`` /
   ``max_total_size`` bound what the walker ever decodes, and ``max_depth`` / ``max_parts``
   bound the HTML projection. This module adds its own output bounds on top (below) and
   enforces none of the walker's again.
4. **A refusal is a value, never an exception and never a silent drop.** Every occurrence of
   an attachment yields exactly one result -- a payload or a refusal naming the closed
   reason -- so a caller can tell "this message had four attachments and one was refused"
   from "this message had three attachments". Reason ids are **reused**, never invented: the
   entry point's (``not_a_message``, ``input_over_cap``), the D6 cap reasons of
   ``model.REASON_TABLE[Status.SKIPPED]`` (``size_cap``, ``total_size_cap``,
   ``part_count_cap``) -- which is where the design put a cap's identity when it pruned
   ``attach.size_cap_hit`` -- the registered gap id ``attach.cid_unreferenced`` for an
   occurrence the decorative rule skipped, and ``extractor_error`` (D6, ``failed``) for the
   one case ``assemble`` already records it for: a stage raised on this message's content.
5. **A nested message is a payload, not a recursion.** An attachment that is itself a
   message (``message/rfc822``, an attached ``.msg``) is returned as its own bytes; this
   accessor never opens it. Recursion depth and routing are the caller's concern.
6. **The line table covers the text exactly.** The segments partition ``[0, len(text))``:
   contiguous, non-overlapping, gapless, each one a physical line **including its
   terminator** (``\\r\\n``, ``\\r`` or ``\\n``, the walker's own three), and each carrying a
   :class:`~emailextract.model.HitLocation` whose ``part``, ``view``, ``span`` and ``unit``
   name the same characters, so a hit can be cited down to the line and to the code point
   range inside it.

The site note in ``docs/design/turn-BODY1-note.md`` carries the hand-typed labels, the
mutation table and the measured cost.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from . import attach as attach_stage
from . import ingest as ingest_module
from . import parse
from . import walk as walk_module
from .assemble import selected_body_text
from .container import EmlContainer
from .mediatype import effective_media_type_in
from .model import BodyView, DecorativeHintState, HitLocation, Span, TriState
from .versions import (
    ATTACHMENT_ACCESSOR_VERSION,
    BODY_TEXT_VERSION,
    DECODE_CHAIN_VERSION,
    EMAIL_PARSER_VERSION,
    HTMLTEXT_VERSION,
)

__all__ = [
    "ATTACHMENT_ACCESSOR_VERSION",
    "AttachmentPayload",
    "AttachmentRefusal",
    "BODY_TEXT_VERSION",
    "BodyRefusal",
    "BodyText",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_CHARS",
    "DEFAULT_MAX_COUNT",
    "MAX_CHARS_CEILING",
    "body_text",
    "iter_attachment_payloads",
]

#: The documented default for ``body_text``'s ``max_chars``: one million code points, which is
#: larger than every body any measured corpus message carries and small enough that a
#: pathological message cannot hand a caller a gigabyte of text.
DEFAULT_MAX_CHARS: Final[int] = 1_000_000

#: The hard ceiling ``max_chars`` may be raised to. A caller asking for more is a caller
#: error (``ValueError``), not a silently clamped bound: the bound exists so that this
#: accessor cannot be used to materialise an unbounded string.
MAX_CHARS_CEILING: Final[int] = 2_000_000

#: The documented default for ``iter_attachment_payloads``'s ``max_count``.
DEFAULT_MAX_COUNT: Final[int] = 50

#: The documented default for ``iter_attachment_payloads``'s ``max_bytes``, which is **both**
#: the per-attachment ceiling and the running total budget for one iteration (see the
#: function's docstring): eight mebibytes.
DEFAULT_MAX_BYTES: Final[int] = 8 * 1024 * 1024

#: The closed reason a message with no text body view returns (a registered ``body`` gap id,
#: emitted by the selection stage for the same condition).
REASON_NO_TEXT_PART: Final[str] = "body.no_text_part"

#: The three D6 cap reasons this accessor re-states (``model.REASON_TABLE[Status.SKIPPED]``).
REASON_SIZE_CAP: Final[str] = "size_cap"
REASON_TOTAL_SIZE_CAP: Final[str] = "total_size_cap"
REASON_PART_COUNT_CAP: Final[str] = "part_count_cap"

#: The registered gap id the decorative rule's skip is recorded under: the occurrence is inline
#: and its ``cid`` is referenced by nobody, which is exactly what that id means.
REASON_CID_UNREFERENCED: Final[str] = "attach.cid_unreferenced"

#: The D6 failed reason, re-used for "a stage raised on this message's content": exactly the
#: reason ``assemble`` records for the same condition (its one guard), so a caller sees one
#: vocabulary for one fact.
REASON_EXTRACTOR_ERROR: Final[str] = "extractor_error"


# ------------------------------------------------------------------------- the records


@dataclass(frozen=True)
class BodyText:
    """One message's body text: D14's view, its text, the line table and the stamps.

    ``view`` is ``"plain"`` or ``"html"`` and is **the view the digest was taken over**, not a
    preference of this accessor. ``text`` is that view's decoded text, in code points, the
    same coordinate space the digest is over (CRLF stays two code points, nothing is
    normalised). ``segments`` is ``(start, end, locator)`` per physical line: ``start``/
    ``end`` index ``text`` and ``locator`` is a :class:`~emailextract.model.HitLocation`
    naming the same range.

    ``truncated`` is true **iff** ``max_chars`` cut the text; ``char_count`` is the length of
    the ``text`` returned (so ``truncated and char_count == max_chars``, and a caller that
    wants to know the original length knows it is larger than ``char_count``).
    ``reason_id`` is ``None`` when text was found and ``"body.no_text_part"`` when the message
    has no text body view at all (then ``text`` is empty and ``segments`` is empty).
    """

    view: str
    text: str
    segments: tuple[tuple[int, int, HitLocation], ...] = ()
    truncated: bool = False
    char_count: int = 0
    reason_id: str | None = None
    email_parser_version: str = EMAIL_PARSER_VERSION
    decode_chain_version: str = DECODE_CHAIN_VERSION
    htmltext_version: str = HTMLTEXT_VERSION
    body_text_version: str = BODY_TEXT_VERSION


@dataclass(frozen=True)
class BodyRefusal:
    """A typed refusal: the message could not be read as a message at all.

    ``reason_id`` is the entry point's own closed reason (``parse.NAMED_ERROR_REASONS``:
    ``invalid_input``, ``input_over_cap``, ``not_a_message``, ``cfb_msg_unsupported``,
    ``invalid_limits``), verbatim -- never a new id, and never an exception.
    """

    reason_id: str
    detail: str | None = None
    email_parser_version: str = EMAIL_PARSER_VERSION
    body_text_version: str = BODY_TEXT_VERSION


@dataclass(frozen=True)
class AttachmentPayload:
    """One attachment occurrence's decoded payload.

    ``occurrence_ref`` is the ``occurrence_path`` the manifest's ``AttachmentOccurrence``
    carries for the same occurrence (``part path @ ordinal``), so a citation can join the
    two records. ``filename`` is the decoded filename when the library decoded one, else the
    raw field value, else ``None``. ``media_type`` is the **effective** media type (RFC 2045
    5.2 defaults applied, ``mediatype.effective_media_type_in``) -- the value to route on.
    ``size`` is ``len(data)``: the decoded byte count the manifest's ``size_bytes`` also
    carries.
    """

    occurrence_ref: str
    filename: str | None
    media_type: str
    size: int
    data: bytes
    attachment_accessor_version: str = ATTACHMENT_ACCESSOR_VERSION


@dataclass(frozen=True)
class AttachmentRefusal:
    """One occurrence this accessor refused, with the closed reason it refused it for.

    ``reason_id`` is one of ``size_cap`` (over ``max_bytes``), ``total_size_cap`` (the
    running total would exceed ``max_bytes``), ``part_count_cap`` (``max_count`` payloads
    were already yielded), ``attach.cid_unreferenced`` (the decorative rule skipped it;
    ``detail`` is that rule's id) or the entry point's own reason when the message itself
    could not be read (then ``occurrence_ref`` is ``""`` -- nothing was enumerated).
    ``detail`` is prose for a human, never a value a caller should parse.
    """

    occurrence_ref: str
    reason_id: str
    detail: str | None = None
    attachment_accessor_version: str = ATTACHMENT_ACCESSOR_VERSION


# ----------------------------------------------------------------------- the one open


def _open(source: object, limits: parse.Limits) -> tuple[bytes, object] | BodyRefusal:
    """``(raw bytes, container)`` for a path, ``bytes``, a ``FileMaterial`` or a container.

    The bytes-to-container decision is the entry point's own (``ingest._container_for``: a
    ``cfb_msg`` projection for a CFB, the ``.eml`` adapter otherwise) and the sniff is
    ``parse.parse`` -- neither is re-implemented here, so an ``.eml`` and a ``.msg`` are read
    exactly as ``ingest_path`` reads them, and a file over ``max_input_bytes`` is refused
    before any decode.

    The bytes returned are ``container.raw_bytes()``, **not** the source's file bytes: every
    recorded span points into that address space, which for a ``.msg`` is the virtual RFC 822
    projection rather than the CFB file (a part's span sliced out of the CFB bytes is a
    different byte string, and decoding it fails -- the reason this accessor reads it the way
    ``assemble`` and ``walk`` do).
    """
    if hasattr(source, "raw_bytes") and hasattr(source, "container_facts"):
        return source.raw_bytes(), source
    data = EmlContainer(source).raw_bytes()
    decision = parse.parse(data, limits=limits)
    if decision.error is not None:
        return BodyRefusal(reason_id=decision.error.reason_id, detail=decision.error.detail)
    container = ingest_module._container_for(data, decision.kind)
    return container.raw_bytes(), container


def _limits() -> parse.Limits:
    """The approved caps, built per call (a caller cannot move them, and nothing is cached)."""
    return parse.Limits.untrusted()


# -------------------------------------------------------------------------- the segments


def _line_bounds(text: str) -> list[tuple[int, int]]:
    """The physical lines of ``text`` as ``(start, end)`` pairs that partition it exactly.

    CRLF, a lone CR and a lone LF are the three terminators -- the walker's own line model
    (``walk.iter_lines``), applied to the decoded text instead of raw bytes because this
    text has no byte map of its own (an HTML projection has none by design, decision 8). A
    line keeps its terminator, so the pairs are contiguous and gapless; a text that ends with
    a terminator has no empty final line, and an empty text has no lines.
    """
    bounds: list[tuple[int, int]] = []
    length = len(text)
    start = 0
    index = 0
    while index < length:
        character = text[index]
        if character == "\r":
            end = index + 2 if index + 1 < length and text[index + 1] == "\n" else index + 1
        elif character == "\n":
            end = index + 1
        else:
            index += 1
            continue
        bounds.append((start, end))
        start = end
        index = end
    if start < length:
        bounds.append((start, length))
    return bounds


def _segments(
    text: str, *, part: str | None, view: str
) -> tuple[tuple[int, int, HitLocation], ...]:
    """The line table: one ``(start, end, HitLocation)`` per physical line of ``text``.

    ``unit`` is the line's ordinal (0-based, in document order) so a hit can be named as
    "line 3 of part 1.1's html view" without re-splitting the text.
    """
    return tuple(
        (start, end, HitLocation(part=part, view=view, span=Span(start, end), unit=ordinal))
        for ordinal, (start, end) in enumerate(_line_bounds(text))
    )


# ------------------------------------------------------------------------- the accessor


def body_text(
    source: object, *, max_chars: int = DEFAULT_MAX_CHARS
) -> BodyText | BodyRefusal:
    """The message's body text, under D14's view and this accessor's own bounds.

    ``source`` is a path, ``bytes``, a ``FileMaterial`` or an already-built container -- the
    same inputs ``ingest_path`` accepts, read through the same container decision.

    ``max_chars`` truncates the text (``truncated`` says so) and may not exceed
    :data:`MAX_CHARS_CEILING`; a value outside ``1..MAX_CHARS_CEILING`` is a caller error and
    raises ``ValueError``. The walker's own caps still apply underneath: a body the walker
    skipped for a size cap is not in ``text`` and the document records that on its own
    ``part.gaps``/``status`` -- this accessor adds no reason for it.
    """
    if isinstance(max_chars, bool) or not isinstance(max_chars, int):
        raise ValueError(f"max_chars must be an int, got {max_chars!r}")
    if not 1 <= max_chars <= MAX_CHARS_CEILING:
        raise ValueError(
            f"max_chars must be in 1..{MAX_CHARS_CEILING}, got {max_chars}"
        )
    limits = _limits()
    opened = _open(source, limits)
    if isinstance(opened, BodyRefusal):
        return opened
    raw, container = opened
    try:
        result = walk_module.walk(container, limits=limits)
        view, locator, text = selected_body_text(raw, result, limits=limits)
    except Exception:  # noqa: BLE001 - a stage must never raise on input *content*
        return BodyRefusal(
            reason_id=REASON_EXTRACTOR_ERROR,
            detail="the walker or the body stages raised on this message's content",
        )
    truncated = len(text) > max_chars
    kept = text[:max_chars]
    return BodyText(
        view=view.value,
        text=kept,
        segments=_segments(kept, part=locator, view=view.value),
        truncated=truncated,
        char_count=len(kept),
        reason_id=None if locator is not None else REASON_NO_TEXT_PART,
    )


def iter_attachment_payloads(
    source: object,
    *,
    max_count: int = DEFAULT_MAX_COUNT,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Iterator[AttachmentPayload | AttachmentRefusal]:
    """Every attachment occurrence's payload, in the manifest's order, under two ceilings.

    ``source`` is what :func:`body_text` accepts. The occurrence list, the occurrence order
    and the decorative classification are the **attachment stage's own**
    (``attach.attachments``): ``occurrence_ref`` is the occurrence's ``occurrence_path`` on
    the ``AttachmentOccurrence`` the document carries, so a hub citation joins the two.

    **Every occurrence yields exactly one result**, so a refusal is never a silent drop:
    a :class:`AttachmentPayload` for an occurrence that is returned, an
    :class:`AttachmentRefusal` naming the closed reason for one that is not.

    ``max_bytes`` is **both** ceilings, so the signature the brief fixes is enough: an
    attachment whose decoded size exceeds it is refused ``size_cap``, and once the payloads
    already yielded total it, the rest are refused ``total_size_cap``. ``max_count`` is the
    number of payloads yielded; further occurrences are refused ``part_count_cap`` without
    being decoded. Both are per iteration, both are caller parameters, and neither is
    enforced by reading an attachment twice: a refused occurrence is refused **before** its
    payload is decoded.

    Payloads are the walker's own decode (``text.decoded_payload``: base64, quoted-printable
    or identity), so ``data`` is exactly what the manifest hashed for that occurrence. An
    attachment that is itself a message (``message/rfc822``, an attached ``.msg``) **is
    returned as its own bytes and never opened here**: recursion depth, routing and nesting
    are the caller's concern. No byte of any payload is stored, logged or cached by this
    library.
    """
    if isinstance(max_count, bool) or not isinstance(max_count, int) or max_count < 0:
        raise ValueError(f"max_count must be an int >= 0, got {max_count!r}")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError(f"max_bytes must be an int >= 0, got {max_bytes!r}")
    limits = _limits()
    opened = _open(source, limits)
    if isinstance(opened, BodyRefusal):
        yield AttachmentRefusal(occurrence_ref="", reason_id=opened.reason_id, detail=opened.detail)
        return
    raw, container = opened
    try:
        result = walk_module.walk(container, limits=limits)
        stage = attach_stage.attachments(
            raw,
            result,
            max_depth=limits.max_depth,
            max_elements=limits.max_parts,
            limits=limits,
        )
    except Exception:  # noqa: BLE001 - a stage must never raise on input *content*
        yield AttachmentRefusal(
            occurrence_ref="",
            reason_id=REASON_EXTRACTOR_ERROR,
            detail="the walker or the attachment stage raised on this message's content",
        )
        return
    by_path = {part.path: part for part in result.parts}
    capped = {skip.locator: skip for skip in stage.caps}
    remaining_bytes = max_bytes
    yielded = 0
    for item in stage.facts:
        occurrence = stage.occurrences[item.index]
        reference = occurrence.occurrence_path
        if item.hint.state is DecorativeHintState.RULE_ID:
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=REASON_CID_UNREFERENCED,
                detail=item.hint.rule_id,
            )
            continue
        if yielded >= max_count:
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=REASON_PART_COUNT_CAP,
                detail=f"max_count={max_count} payloads already yielded",
            )
            continue
        skip = capped.get(item.part.path)
        if skip is not None:
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=skip.cap_id,
                detail=(
                    f"the walker skipped this part: cap_value_bytes={skip.cap_value_bytes}, "
                    f"declared_size={skip.declared_size}"
                ),
            )
            continue
        size = item.size_bytes
        if size is None:
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=REASON_SIZE_CAP,
                detail="the walker decoded no payload for this part",
            )
            continue
        if size > remaining_bytes:
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=(REASON_SIZE_CAP if size > max_bytes else REASON_TOTAL_SIZE_CAP),
                detail=f"size={size}, remaining_budget={remaining_bytes}, max_bytes={max_bytes}",
            )
            continue
        try:
            data = attach_stage.decoded_payload(raw, item.part)
        except Exception:  # noqa: BLE001 - one bad attachment must never raise
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=REASON_EXTRACTOR_ERROR,
                detail="the decode raised for this occurrence",
            )
            continue
        if data is None:
            yield AttachmentRefusal(
                occurrence_ref=reference,
                reason_id=REASON_SIZE_CAP,
                detail="the walker decoded no payload for this part",
            )
            continue
        remaining_bytes -= len(data)
        yielded += 1
        yield AttachmentPayload(
            occurrence_ref=reference,
            filename=(
                item.filename_decoded.value
                if item.filename_decoded.state is TriState.VALUE
                else item.filename_raw
            ),
            media_type=effective_media_type_in(item.part, by_path),
            size=len(data),
            data=data,
        )
