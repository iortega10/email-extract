"""Turn 1.0d: the parse entry point, ``Limits``, the container sniff, the named errors.

``parse(data, container_kind=None, *, limits)`` is the one door hostile bytes come
through (decision 10, D1 amended). It does three things and nothing else: it checks
``limits`` against the input, it decides the container kind (a caller's assertion, or
a sniff), and it returns a frozen :class:`ParseResult`. **It parses no header, no
body, no quote and no HTML, and it never calls the walker** -- Turn 1.1 wires ``parse``
to the walker; the Phase 0 walker's own public entry point is untouched here.

Two contracts this module fixes:

* **The input never raises.** For **any** ``bytes`` -- random, truncated, hostile --
  ``parse`` returns a ``ParseResult``; a failure is a :class:`NamedError` carried in
  ``result.error``, never an exception. A non-``bytes`` ``data`` is the named error
  ``invalid_input``, also carried, not raised.
* **A bad ``Limits`` is a programming error, not input.** ``Limits(...)`` is the only
  place a ``NamedError`` is raised -- as an ``Exception`` subclass -- because a caller
  who passes ``max_parts=0`` has a bug, whereas a caller who passes hostile bytes does
  not.

The named-error reason ids are a **closed tuple** and they are **not** gap ids and
**not** status reasons: they never enter the design's gap registry, ``phase0-gaps.md``
or :mod:`emailextract.ids`, and they are not members of the D6 status vocabulary.

The sniff (decision 10, decision 14): the first eight bytes ``D0CF11E0A1B11AE1`` are a
CFB (``cfb_msg``), which Phase 1 has no reader for, so it is the named error
``cfb_msg_unsupported`` -- never a guess, never an exception from mid-parse. Otherwise
the bytes are ``rfc822`` iff, after an **optional** UTF-8 BOM and an **optional** mbox
``From `` line, at least one ``name: value`` header line appears before the first blank
line or the end of input; otherwise the named error ``not_a_message`` (a text file with
no header line is not a message, and a message of only a blank line is not a message).
An explicit ``container_kind`` **overrides** the sniff -- the caller asserts the format,
and a wrong assertion is the caller's problem, not re-sniffed (a claimed or sniffed CFB
is still ``cfb_msg_unsupported``).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Final

from docextract_core.codec import CodecError

__all__ = [
    "Limits",
    "NAMED_ERROR_REASONS",
    "NamedError",
    "ParseResult",
    "parse",
]

#: The CFB (compound file binary) signature that opens a ``.msg`` (D14).
_CFB_MAGIC: Final[bytes] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
#: A leading UTF-8 BOM (decision 14): tolerated by the sniff, accounted as a prelude.
_UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"
#: An mbox ``From `` envelope line (decision 14): also a tolerated prelude.
_MBOX_PREFIX: Final[bytes] = b"From "
#: ``name: value`` field-name bounds -- RFC 5322 ftext is %d33-57 / %d59-126, i.e.
#: printable ASCII with space and the colon itself excluded.
_NAME_MIN: Final[int] = 33
_NAME_MAX: Final[int] = 126
_COLON: Final[int] = 58

#: The **closed** tuple of named-error reason ids. These are the entry point's own
#: vocabulary; they are neither gap ids (the design registry) nor status reasons (D6).
NAMED_ERROR_REASONS: Final[tuple[str, ...]] = (
    "invalid_input",
    "input_over_cap",
    "invalid_container_kind",
    "cfb_msg_unsupported",
    "not_a_message",
    "invalid_limits",
)

#: The three legal ``container_kind`` values (``None`` means "sniff it").
_CONTAINER_KINDS: Final[tuple[str | None, ...]] = (None, "rfc822", "cfb_msg")


@dataclass(frozen=True)
class NamedError(Exception):
    """A named failure: a closed ``reason_id`` and an optional human ``detail``.

    It is an ``Exception`` subclass so that a bad :class:`Limits` can be *raised*
    (a programming error); ``parse`` never raises one -- it carries this record in
    :attr:`ParseResult.error`. ``detail`` is a caller-facing note, never a library or
    exception message that a test could mistake for a contract.
    """

    reason_id: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.reason_id not in NAMED_ERROR_REASONS:
            raise NamedError(
                "invalid_limits",
                f"reason_id {self.reason_id!r} is not one of {NAMED_ERROR_REASONS}",
            )
        if self.detail is not None and not isinstance(self.detail, str):
            raise NamedError("invalid_limits", "detail must be a str or None")

    def __str__(self) -> str:
        return self.reason_id if self.detail is None else f"{self.reason_id}: {self.detail}"


def _positive_int(value: object, name: str) -> int:
    """``value`` as a strictly positive ``int``, else raise ``invalid_limits``.

    A ``bool`` is refused even though it is an ``int`` subclass; a ``float``, ``str``,
    zero and a negative are all refused -- and always as the named error, never as a
    bare ``ValueError``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise NamedError("invalid_limits", f"{name} must be a positive int, got {value!r}")
    if value <= 0:
        raise NamedError("invalid_limits", f"{name} must be positive, got {value}")
    return value


@dataclass(frozen=True)
class Limits:
    """The structural and size caps, as **caller parameters** -- no defaults anywhere.

    Every field is a caller-supplied positive ``int``; there is no module-level default
    set and no default argument, because "untrusted" is the caller's knowledge and not
    the function's.

    :meth:`untrusted` returns the **recommended untrusted defaults the design owner
    approved** (decision 10's ``Limits.untrusted()``): 64 MiB input, 16-deep multipart
    nesting, 1000 parts, a 256 KiB header region, 32 MiB decoded per part, 128 MiB
    decoded in total, and a work budget of 64 work units per byte of one **header field
    value** (Turn 1.5c renamed it from ``max_work_units_per_input_byte``: the budget is
    per field value, not message-wide, and unit kinds are not commensurable, so there is
    deliberately no message-scope work accumulator). These numbers are **reasoned, not
    measured** (``docs/design/phase1-empirical.md`` records them as such).

    **Turn 1.5c enforces** every one of them: ``parse`` checks :attr:`max_input_bytes`
    before any sniff (Turn 1.0d) and ``walk`` checks the other six as the structure is
    discovered (before Turn 1.5c only the HTML tree's depth/element caps and the per-field
    RFC 2047 budget were enforced). A cap fixture's sidecar never asserts a status: a
    ``Limits`` is a parameter of the test, not of the label.
    """

    max_input_bytes: int
    max_depth: int
    max_parts: int
    max_header_bytes: int
    max_decoded_part_bytes: int
    max_decoded_total_bytes: int
    max_field_work_units_per_byte: int

    def __post_init__(self) -> None:
        for field_ in fields(self):
            _positive_int(getattr(self, field_.name), f"limits.{field_.name}")

    @classmethod
    def untrusted(cls) -> "Limits":
        """The approved untrusted default set (reasoned-not-measured; see the class)."""
        return cls(
            max_input_bytes=64 * 1024 * 1024,
            max_depth=16,
            max_parts=1000,
            max_header_bytes=256 * 1024,
            max_decoded_part_bytes=32 * 1024 * 1024,
            max_decoded_total_bytes=128 * 1024 * 1024,
            max_field_work_units_per_byte=64,
        )


@dataclass(frozen=True)
class ParseResult:
    """What ``parse`` returns: the decided kind, the prelude it skipped, or the error.

    On success ``kind`` is ``"rfc822"``, ``error`` is ``None`` and the two prelude
    lengths are the bytes ``parse`` skipped before the header region -- an optional
    UTF-8 BOM (:attr:`prelude_bom_bytes`) and an optional mbox ``From `` line
    (:attr:`prelude_mbox_bytes`) -- so Turn 1.1 can account for them (decision 14). On a
    failure ``kind`` is ``None``, the preludes are zero and ``error`` carries the named
    failure.

    ``parse`` returns **nothing else**: no part span, no header, no body, no walker
    result -- Turn 1.1 builds the document.
    """

    kind: str | None
    prelude_bom_bytes: int
    prelude_mbox_bytes: int
    error: NamedError | None

    def __post_init__(self) -> None:
        if self.error is None:
            if self.kind != "rfc822":
                raise CodecError("parse_result: a result with no error is kind='rfc822'")
            if self.prelude_bom_bytes < 0 or self.prelude_mbox_bytes < 0:
                raise CodecError("parse_result: prelude lengths must be >= 0")
        else:
            if not isinstance(self.error, NamedError):
                raise CodecError("parse_result.error must be a NamedError")
            if self.kind is not None:
                raise CodecError("parse_result: an error carries no kind")
            if self.prelude_bom_bytes or self.prelude_mbox_bytes:
                raise CodecError("parse_result: an error skips no prelude")


def _failure(reason_id: str, detail: str) -> ParseResult:
    return ParseResult(
        kind=None,
        prelude_bom_bytes=0,
        prelude_mbox_bytes=0,
        error=NamedError(reason_id=reason_id, detail=detail),
    )


def _success(bom_bytes: int, mbox_bytes: int) -> ParseResult:
    return ParseResult(
        kind="rfc822",
        prelude_bom_bytes=bom_bytes,
        prelude_mbox_bytes=mbox_bytes,
        error=None,
    )


def _line_terminator_end(data: bytes, start: int) -> int | None:
    """The index just past the LF that ends the line at ``start``, or ``None`` at EOF.

    ``LF`` and ``CRLF`` both end the line (the ``\\r`` of a CRLF is included in the
    returned length); a line with no terminator before the end of input has none.
    """
    newline = data.find(b"\n", start)
    return None if newline == -1 else newline + 1


def _prelude(data: bytes) -> tuple[int, int]:
    """``(bom_bytes, mbox_bytes)`` for the tolerated leading prelude (decision 14)."""
    start = len(_UTF8_BOM) if data[: len(_UTF8_BOM)] == _UTF8_BOM else 0
    mbox = 0
    if data[start : start + len(_MBOX_PREFIX)] == _MBOX_PREFIX:
        end = _line_terminator_end(data, start)
        if end is not None:
            mbox = end - start
    return start, mbox


def _iter_lines(data: bytes, start: int):
    """Yield each line's content (its terminator stripped) from ``start`` to EOF.

    ``LF`` and ``CRLF`` end a line; a final line with no terminator is yielded once.
    An empty line yields ``b""`` -- the caller stops the header region there.
    """
    position = start
    end = len(data)
    while position < end:
        newline = data.find(b"\n", position)
        if newline == -1:
            content, position = data[position:], end
        else:
            content, position = data[position:newline], newline + 1
        if content.endswith(b"\r"):
            content = content[:-1]
        yield content


def _is_header_line(content: bytes) -> bool:
    """True for ``name: value`` -- RFC 5322 ftext, a colon, then anything."""
    colon = content.find(b":")
    if colon <= 0:
        return False
    for byte in content[:colon]:
        if byte < _NAME_MIN or byte > _NAME_MAX or byte == _COLON:
            return False
    return True


def _has_field_before_blank(data: bytes, start: int) -> bool:
    """True iff a header line appears before the first blank line or the end of input."""
    for content in _iter_lines(data, start):
        if content == b"":
            return False
        if _is_header_line(content):
            return True
    return False


def _sniff(data: bytes, has_field) -> ParseResult:
    """The ``container_kind=None`` decision, with the field predicate taken as an argument.

    ``has_field(data, region_start)`` is the "is this a message" predicate; separating it
    from the sniff is what lets a test plant a wrong predicate and prove the sniff's
    negative cases are non-vacuous, without editing this module.
    """
    if data[: len(_CFB_MAGIC)] == _CFB_MAGIC:
        return _failure("cfb_msg_unsupported", "Phase 1 has no CFB reader")
    bom_bytes, mbox_bytes = _prelude(data)
    if not has_field(data, bom_bytes + mbox_bytes):
        return _failure("not_a_message", "no name: value header line before a blank line")
    return _success(bom_bytes, mbox_bytes)


def parse(data, container_kind=None, *, limits: Limits) -> ParseResult:
    """Decide the container kind of ``data`` under ``limits``; never raise for bytes.

    ``limits`` is **keyword-only and required** (there is no default: the function
    cannot know which bytes are untrusted). See the module docstring for the sniff.
    """
    if not isinstance(data, bytes):
        return _failure("invalid_input", f"data must be bytes, got {type(data).__name__}")
    if len(data) > limits.max_input_bytes:
        return _failure(
            "input_over_cap",
            f"{len(data)} bytes exceeds max_input_bytes={limits.max_input_bytes}",
        )
    if container_kind not in _CONTAINER_KINDS:
        return _failure("invalid_container_kind", f"container_kind={container_kind!r}")
    if container_kind == "cfb_msg":
        return _failure("cfb_msg_unsupported", "Phase 1 has no CFB reader")
    if container_kind == "rfc822":
        bom_bytes, mbox_bytes = _prelude(data)
        return _success(bom_bytes, mbox_bytes)
    return _sniff(data, _has_field_before_blank)
