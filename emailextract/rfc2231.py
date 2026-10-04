"""Turn 1.1: RFC 2231 parameter continuations, ext-values and their recorded fallbacks.

The package decodes ``Content-Type`` / ``Content-Disposition`` parameters itself
(decision 5): numbered continuations ``name*0``, ``name*1`` reassemble **by index** (a
missing or duplicated index is a recorded fallback, never a guess); a ``name*0*`` segment
may carry ``charset'language'`` on **segment zero only** (a charset on a later segment is
not legal and is recorded); ``*`` segments are percent-decoded and the ``*`` form
**shadows** the plain name. Producer forms that are not RFC 2231 -- an RFC 2047 word inside
a quoted parameter, an ``filename*=''...`` with an empty charset -- are **decoded with a
recorded fallback** (``decoded | fallback | undecodable``), never "unparsable".

``fallback_reason`` is a member of the **closed** set the facts document fixes
(``encoded_word_in_parameter``, ``empty_charset``, ``missing_continuation_index``,
``duplicate_continuation_index``); this module invents no id. Two producer forms the
fixtures do not carry -- a ``name*`` shadowing a plain ``name``, and a charset on a later
segment -- are handled without a reason id (the ``*`` form wins; the illegal prefix is
kept literal) because the closed set has no member for them.

Nothing here raises on input content: the parser is total over bytes and linear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .rfc2047 import charset_known

__all__ = ["Parameter", "STRUCTURED_PARAMETERS", "parse_parameters"]

#: The structured parameters the reader decodes and records (the closed set the facts
#: document names: a boundary, a charset, a name, a filename).
STRUCTURED_PARAMETERS: Final[tuple[str, ...]] = ("boundary", "charset", "name", "filename")

#: ``decode_state``'s closed vocabulary (``headers.parameters``).
DECODE_STATES: Final[tuple[str, ...]] = ("decoded", "fallback", "undecodable")

#: ``fallback_reason``'s closed vocabulary (``headers.parameters``).
FALLBACK_REASONS: Final[tuple[str, ...]] = (
    "encoded_word_in_parameter",
    "empty_charset",
    "missing_continuation_index",
    "duplicate_continuation_index",
)

_CONTINUATION: Final[re.Pattern[bytes]] = re.compile(rb"([^*]+)\*(\d+)(\*)?")
_EXTENDED: Final[re.Pattern[bytes]] = re.compile(rb"([^*]+)\*")
_HEX_PAIR: Final[re.Pattern[bytes]] = re.compile(rb"[0-9A-Fa-f]{2}")
_ENCODED_WORD: Final[re.Pattern[bytes]] = re.compile(rb"=\?[^?\r\n]*\?[^?\r\n]*\?[^?\r\n]*\?=")


@dataclass(frozen=True)
class Parameter:
    """One structured parameter, decoded, with the byte span of the parameter in the raw message.

    ``name`` is the **lowercased** base name (the labels type ``Boundary`` as ``boundary``);
    ``raw_name`` is the name as written (a continuation keeps its ``*0`` suffix here). The
    span covers every segment of the parameter.
    """

    name: str
    raw_name: str
    value: str
    state: str
    fallback_reason: str | None
    offset: int
    length: int

    def __post_init__(self) -> None:
        if self.state not in DECODE_STATES:
            raise ValueError(f"parameter.state {self.state!r} is not one of {DECODE_STATES}")
        if self.state == "fallback":
            if self.fallback_reason not in FALLBACK_REASONS:
                raise ValueError(
                    f"parameter.fallback_reason {self.fallback_reason!r} is not one of "
                    f"{FALLBACK_REASONS}"
                )
        elif self.fallback_reason is not None:
            raise ValueError("parameter.fallback_reason is set only when state is fallback")


@dataclass(frozen=True)
class _Segment:
    """One physical ``name[...]=value`` piece of a field, with where it sat in the value."""

    base: bytes
    index: int | None
    encoded: bool
    raw_name: bytes
    text: bytes
    start: int
    end: int


def _percent_decode(text: bytes) -> bytes:
    """Decode ``%XX`` escapes to bytes; a stray ``%`` is left literal (total, linear)."""
    out = bytearray()
    index = 0
    while index < len(text):
        if text[index] == 0x25 and _HEX_PAIR.fullmatch(text[index + 1 : index + 3]):
            out.append(int(text[index + 1 : index + 3], 16))
            index += 3
        else:
            out.append(text[index])
            index += 1
    return bytes(out)


def _split_segments(value: bytes) -> list[tuple[int, int, bytes]]:
    """``(start, end, piece)`` for each ``;``-separated segment, quotes respected.

    A ``;`` inside a quoted string is not a separator; a backslash escapes the next byte
    inside a quoted string. The first piece (the media type / disposition) is included and
    the caller ignores it.
    """
    pieces: list[tuple[int, int, bytes]] = []
    start = 0
    current = bytearray()
    quoted = False
    escaped = False
    for index, byte in enumerate(value):
        if escaped:
            current.append(byte)
            escaped = False
        elif byte == 0x5C and quoted:  # backslash
            current.append(byte)
            escaped = True
        elif byte == 0x22:  # double quote
            quoted = not quoted
            current.append(byte)
        elif byte == 0x3B and not quoted:  # ';'
            pieces.append((start, index, bytes(current)))
            current = bytearray()
            start = index + 1
        else:
            current.append(byte)
    pieces.append((start, len(value), bytes(current)))
    return pieces


def _unquote(text: bytes) -> bytes:
    """Strip a surrounding quoted-string and unescape ``\\"`` / ``\\\\`` inside it."""
    if len(text) >= 2 and text[:1] == b'"' and text[-1:] == b'"':
        text = text[1:-1]
        if b"\\" in text:
            out = bytearray()
            index = 0
            while index < len(text):
                if text[index] == 0x5C and index + 1 < len(text):
                    out.append(text[index + 1])
                    index += 2
                else:
                    out.append(text[index])
                    index += 1
            text = bytes(out)
    return text


def _classify(name: bytes) -> tuple[bytes, int | None, bool]:
    """``(base, index | None, encoded)`` for a parameter name as written."""
    match = _CONTINUATION.fullmatch(name)
    if match is not None:
        return match.group(1), int(match.group(2).decode("ascii")), match.group(3) is not None
    match = _EXTENDED.fullmatch(name)
    if match is not None:
        return match.group(1), None, True
    return name, None, False


def _ext_value(text: bytes) -> tuple[str, str, str | None]:
    """Decode one ``charset'language'value`` ext-value.

    Returns ``(value, state, fallback_reason)``. An empty charset is the recorded fallback
    ``empty_charset`` (the value's bytes are percent-decoded and read as latin-1); an unknown
    charset is ``undecodable``; a well-formed charset decodes the percent-decoded bytes.
    """
    parts = text.split(b"'", 2)
    if len(parts) != 3:
        return text.decode("latin-1"), "undecodable", None
    charset, _language, payload = parts
    decoded_bytes = _percent_decode(payload)
    if charset == b"":
        return decoded_bytes.decode("latin-1"), "fallback", "empty_charset"
    name = charset.decode("latin-1")
    if not charset_known(name):
        return decoded_bytes.decode("latin-1"), "undecodable", None
    try:
        return decoded_bytes.decode(name, "strict"), "decoded", None
    except (UnicodeDecodeError, LookupError, ValueError):
        return decoded_bytes.decode("latin-1"), "undecodable", None


def _decode_group(base: bytes, segments: list[_Segment]) -> tuple[str, str, str | None]:
    """Decode one parameter's segments into ``(value, state, fallback_reason)``."""
    continuations = [segment for segment in segments if segment.index is not None]
    extended = [segment for segment in segments if segment.index is None and segment.encoded]
    plain = [segment for segment in segments if segment.index is None and not segment.encoded]

    if continuations:
        indexes = sorted(segment.index for segment in continuations)
        if len(indexes) != len(set(indexes)):
            return b"", "fallback", "duplicate_continuation_index"
        if indexes != list(range(indexes[0], indexes[-1] + 1)):
            return b"", "fallback", "missing_continuation_index"
        ordered = sorted(continuations, key=lambda segment: segment.index)
        charset = b""
        pieces: list[bytes] = []
        for position, segment in enumerate(ordered):
            text = segment.text
            if segment.encoded and position == 0:
                parts = text.split(b"'", 2)
                if len(parts) == 3:
                    charset, _language, text = parts
            elif segment.encoded and position > 0 and text.count(b"'") >= 2:
                # A charset on a later segment is not legal; the prefix is kept literal.
                pass
            pieces.append(_percent_decode(text) if segment.encoded else text)
        combined = b"".join(pieces)
        if not charset:
            return combined.decode("latin-1"), "decoded", None
        name = charset.decode("latin-1")
        if name == b"":
            return combined.decode("latin-1"), "fallback", "empty_charset"
        if not charset_known(name):
            return combined.decode("latin-1"), "undecodable", None
        try:
            return combined.decode(name, "strict"), "decoded", None
        except (UnicodeDecodeError, LookupError, ValueError):
            return combined.decode("latin-1"), "undecodable", None

    if extended:
        return _ext_value(extended[0].text)

    if plain:
        text = plain[0].text
        if _ENCODED_WORD.search(text) is not None:
            return text.decode("latin-1"), "fallback", "encoded_word_in_parameter"
        return text.decode("latin-1"), "decoded", None

    return b"", "undecodable", None


def parse_parameters(value: bytes, value_offset: int) -> list[Parameter]:
    """Every parameter of one field value, one :class:`Parameter` per base name, in order.

    ``value`` is the verbatim field value bytes; ``value_offset`` is the byte offset of
    ``value`` in the raw message, so each parameter's span points into the message.
    """
    segments: dict[bytes, list[_Segment]] = {}
    order: list[bytes] = []
    pieces = _split_segments(value)
    for start, end, piece in pieces[1:]:  # pieces[0] is the media type / disposition
        if b"=" not in piece:
            continue
        raw_name, _, raw_value = piece.partition(b"=")
        name = raw_name.strip()
        if not name:
            continue
        base, index, encoded = _classify(name)
        key = base.lower()
        # The name's offset within the value: skip leading whitespace of the piece.
        lead = len(piece) - len(piece.lstrip(b" \t"))
        name_start = start + lead
        segment = _Segment(
            base=base,
            index=index,
            encoded=encoded,
            raw_name=name,
            text=_unquote(raw_value.strip()),
            start=name_start,
            end=end,
        )
        if key not in segments:
            segments[key] = []
            order.append(key)
        segments[key].append(segment)
    parameters: list[Parameter] = []
    for key in order:
        group = segments[key]
        decoded, state, reason = _decode_group(group[0].base, group)
        if isinstance(decoded, bytes):
            decoded = decoded.decode("latin-1")
        offset = min(segment.start for segment in group)
        end = max(segment.end for segment in group)
        parameters.append(
            Parameter(
                name=key.decode("latin-1"),
                raw_name=group[0].raw_name.decode("latin-1"),
                value=decoded,
                state=state,
                fallback_reason=reason,
                offset=value_offset + offset,
                length=end - offset,
            )
        )
    return parameters
