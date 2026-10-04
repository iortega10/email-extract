"""Turn 1.1: RFC 2047 encoded words, **validated before decoding** (decision 5).

The package decodes ``=?charset?B|Q?text?=`` words in unstructured header text (and,
by the callers that own them, in display names). The stdlib decodes an invalid word
**silently** with ``defects = []`` (``docs/design/email-spike.md`` b02), so this module
validates first and reports the invalidity instead of guessing: a charset that does not
resolve, an encoding letter that is not ``B`` or ``Q``, a text part that is not valid for
its encoding, a word over 75 bytes, or a word carrying whitespace inside it is **not
decoded** -- it is kept verbatim and the caller records ``headers.encoded_word_invalid``.

The rules this module fixes (RFC 2047 5(1), RFC 5322 2.2.3):

* **Unfold first, keeping the whitespace.** Unfolding removes the CRLF of an obs-fold and
  keeps the WSP that followed it (RFC 5322 2.2.3), so ``a\\r\\n b`` unfolds to ``a b``.
* **Adjacency.** Whitespace *between* two adjacent encoded words is dropped; text between
  a word and something else is literal.
* **Joining across a split character is same-charset only.** A run of adjacent words that
  share one charset is decoded as the **concatenated bytes** (so a multibyte character split
  across two words joins); a run of different charsets is decoded **per word** and the pieces
  concatenated, never joined at the byte level.
* **Nothing here raises on input content.** The decoder is a pure function of bytes and a
  caller-supplied work budget, and it is **linear** in the input: a bomb-shaped input (an
  encoded word whose decoded text is itself an encoded word) is decoded **once**, never
  recursively. The budget (``max_work_units`` per input byte, no default) bounds the work.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
from dataclasses import dataclass
from typing import Final

__all__ = ["DecodedValue", "charset_known", "decode_encoded_words", "unfold"]

#: RFC 2047 2: an encoded word is at most 75 bytes, ``=?`` and ``?=`` included.
MAX_ENCODED_WORD_BYTES: Final[int] = 75

#: The whole ``=?charset?B|Q?text?=`` token. ``[^?]`` keeps the charset/encoding/text parts
#: free of ``?``; an embedded CR or LF cannot appear after unfolding. Whitespace inside the
#: text part is matched here and then **refused** by the validator (so it is a recorded
#: invalid word rather than silently literal), which is why the text part is ``[^?]*``.
_WORD: Final[re.Pattern[bytes]] = re.compile(rb"=\?([^?\r\n]*)\?([^?\r\n]*)\?([^?\r\n]*)\?=")

_HEX_PAIR: Final[re.Pattern[bytes]] = re.compile(rb"[0-9A-Fa-f]{2}")


@dataclass(frozen=True)
class DecodedValue:
    """One field's decoded text, with the three flags decision 5 asks for.

    ``text`` is the field value after unfolding and decoding (invalid words kept
    verbatim). ``decoded`` is true when at least one word decoded, ``invalid`` when at
    least one word was refused, ``fallback_charset`` when a word's bytes did not decode
    under its declared charset and a recorded latin-1 fallback rung produced the text.
    """

    text: str
    decoded: bool = False
    invalid: bool = False
    fallback_charset: bool = False


def canonical_charset(charset: str) -> str | None:
    """The codec name ``charset`` resolves to, or ``None`` when it does not resolve.

    An RFC 2231 section 5 language suffix (``utf-8*en``) is not part of the charset and is
    stripped first. Two spellings of one charset (``UTF-8``, ``utf8``, ``utf-8``) resolve to
    the same name, which is what "the same charset" means for a split character.
    """
    name = charset.split("*", 1)[0]
    if not name:
        return None
    try:
        return codecs.lookup(name).name
    except (LookupError, ValueError, TypeError):
        return None


def charset_known(charset: str) -> bool:
    """Whether ``charset`` resolves to a codec (the package's one charset resolution point).

    The same resolution the walker's decode chain uses when it calls ``bytes.decode(name)``:
    a name ``Python`` does not know is unknown here too. Turn 1.4's ``text.py`` owns the
    alias table; until then this is the single place a charset name is resolved.
    """
    return canonical_charset(charset) is not None


def unfold(value: bytes) -> bytes:
    """Unfold an obs-fold: remove every CR and LF, keeping the whitespace that follows.

    RFC 5322 2.2.3 unfolds by deleting the CRLF of a fold; the WSP that follows is part of
    the field body and stays. A value byte that is a CR or LF is always a fold here (a lone
    CR terminates a line, so it never reaches a field value).
    """
    if b"\r" not in value and b"\n" not in value:
        return value
    return bytes(byte for byte in value if byte not in (10, 13))


def _decode_bytes(charset: str, data: bytes) -> tuple[str, bool]:
    """Decode ``data`` under ``charset``; on failure a recorded latin-1 fallback rung.

    Returns ``(text, used_fallback)``. A byte string that is not valid under its declared
    charset is decoded as latin-1 (a lossless byte->str mapping), and the fallback is
    reported rather than hidden (D9: declared -> used -> fallback fired).
    """
    try:
        return data.decode(canonical_charset(charset) or charset, "strict"), False
    except (UnicodeDecodeError, LookupError, ValueError):
        return data.decode("latin-1"), True


def _q_decode(text: bytes) -> bytes | None:
    """Decode an RFC 2047 Q-encoded word body, or ``None`` when it is malformed.

    ``_`` is a space; ``=XX`` is one byte; anything else is literal. A ``=`` not followed by
    two hex digits (or a stray ``=`` at the end) makes the whole word invalid.
    """
    out = bytearray()
    index = 0
    while index < len(text):
        byte = text[index]
        if byte == 0x5F:  # '_'
            out.append(0x20)
            index += 1
        elif byte == 0x3D:  # '='
            chunk = text[index + 1 : index + 3]
            if len(chunk) != 2 or _HEX_PAIR.fullmatch(chunk) is None:
                return None
            out.append(int(chunk, 16))
            index += 3
        else:
            out.append(byte)
            index += 1
    return bytes(out)


def _b_decode(text: bytes) -> bytes | None:
    """Strictly base64-decode an RFC 2047 B-encoded word body, or ``None`` when malformed."""
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def _word_body(charset: str, encoding: str, text: bytes) -> bytes | None:
    """The word's decoded **bytes**, or ``None`` when the word is invalid.

    Validation is the whole point (decision 5): the charset must resolve, the encoding letter
    must be ``B`` or ``Q`` (case-insensitive), the text must carry no whitespace and be valid
    for its encoding. None of these raises -- each is a refused word.
    """
    if not charset or not charset_known(charset):
        return None
    if any(byte in b" \t\r\n" for byte in text):
        return None
    letter = encoding.upper()
    if letter == "Q":
        return _q_decode(text)
    if letter == "B":
        return _b_decode(text)
    return None


def decode_encoded_words(value: bytes, *, max_work_units: int) -> DecodedValue:
    """Decode the encoded words in one field value (``value`` is the verbatim value bytes).

    ``max_work_units`` is a per-input-byte **work** budget (never a time; ``Limits`` carries
    it) and has no default: it is a caller parameter. A budget too small to decode every word
    leaves the un-reached words verbatim rather than raising -- the decoder is total.
    """
    if isinstance(max_work_units, bool) or not isinstance(max_work_units, int) or max_work_units <= 0:
        raise ValueError(f"max_work_units must be a positive int, got {max_work_units!r}")
    data = unfold(value)
    budget = max_work_units * max(1, len(data))
    spent = len(data)

    matches = list(_WORD.finditer(data))
    if not matches:
        return DecodedValue(text=data.decode("latin-1"))

    out: list[str] = []
    decoded = False
    invalid = False
    fallback = False
    position = 0
    previous_was_word = False
    index = 0
    while index < len(matches):
        match = matches[index]
        gap = data[position : match.start()]
        if previous_was_word and gap.strip(b" \t\r\n") == b"":
            pass  # RFC 2047 5(1): whitespace between adjacent encoded words is dropped
        else:
            out.append(gap.decode("latin-1"))
        spent += match.end() - match.start()
        if spent > budget:
            out.append(data[match.start() :].decode("latin-1"))
            position = len(data)
            break
        charset = match.group(1).decode("latin-1")
        encoding = match.group(2).decode("latin-1")
        body = match.group(3)
        whole = match.end() - match.start()
        token_bytes = _word_body(charset, encoding, body)
        if token_bytes is None or whole > MAX_ENCODED_WORD_BYTES:
            invalid = True
            out.append(match.group(0).decode("latin-1"))
            position = match.end()
            previous_was_word = True
            index += 1
            continue

        joined = bytearray(token_bytes)
        end = match.end()
        cursor = index + 1
        while cursor < len(matches):
            nxt = matches[cursor]
            between = data[end : nxt.start()]
            if between.strip(b" \t\r\n") != b"":
                break  # not adjacent: the text between them is literal
            nxt_charset = nxt.group(1).decode("latin-1")
            nxt_body = _word_body(nxt_charset, nxt.group(2).decode("latin-1"), nxt.group(3))
            if canonical_charset(nxt_charset) != canonical_charset(charset) or nxt_body is None:
                break  # different charset (decoded separately) or an invalid word
            if nxt.end() - nxt.start() > MAX_ENCODED_WORD_BYTES:
                break
            joined.extend(nxt_body)
            end = nxt.end()
            cursor += 1
        text, used_fallback = _decode_bytes(charset, bytes(joined))
        out.append(text)
        decoded = True
        fallback = fallback or used_fallback
        position = end
        previous_was_word = True
        index = cursor

    out.append(data[position:].decode("latin-1"))
    return DecodedValue(
        text="".join(out), decoded=decoded, invalid=invalid, fallback_charset=fallback
    )
