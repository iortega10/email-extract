"""Turn 1.2: the package's own RFC 5322 3.4 address-list tokenizer (decision 4, D2/D9).

The package **owns** address parsing: this module is a byte-oriented, hand-written
scanner over one field's **value bytes**, with no regex with nested quantifiers (a
linear scan, proved by a doubling test) and no import of the stdlib ``email`` (the
Phase 0.1 source guard). It reads the value the walker already measured
(``RawHeaderField.value_span``, Turn 1.1) and emits **one row per address**, in
order, each carrying a **byte span into the raw message** (D2: the byte offset is
the verbatim layer).

Grammar (RFC 5322 3.4 with the obs- forms of 4.4):

* a **mailbox** is a name-addr (optional display-name and angle-addr) or a bare
  addr-spec (3.2.3: dot-atom/quoted local part, ``@``, dot-atom/domain-literal);
* a **group** is ``display-name ":" [mailbox-list] ";"``; a zero-member group
  (``undisclosed-recipients:;``) is a group row with no members -- an **empty
  list**, never absent and never unparsed;
* **obs-route** (``<@a,@b:user@host>``) is recorded: the route text is kept
  verbatim beside the final addr-spec;
* **CFWS** (3.2.4: comments, which nest and take a quoted-pair, and folding
  whitespace, obs-fold included) never splits an address: a comment inside one is
  dropped from the display-name and the addr-spec but stays inside the span.

Non-ASCII bytes (SMTPUTF8 local parts, IDN domains, raw 8-bit display names) are
accepted as atom text verbatim and are **never** IDNA- or NFC-normalised: the
text is exactly the bytes between the tokens, decoded UTF-8 where they are valid
UTF-8, else latin-1 (a lossless byte->str map). Display-name encoded words are
decoded by :mod:`emailextract.rfc2047` -- there is no second decoder here.

Nothing here raises on input content (D9): a structurally impossible address is
**not repaired and not guessed**, it is a row whose ``state`` is ``unparsed`` with
the closed reason :data:`GAP_HEADERS_ADDRESS_UNPARSABLE` and the raw fragment bytes
beside it, and the scanner **resynchronises** at the next top-level ``,`` or ``;``
outside quotes, comments and brackets, so one bad address never swallows its
neighbours. A recorded failure carries no library or exception text.

The frozen :class:`AddressRow` is the fact row this turn's oracle projects onto
``headers.addresses`` (``docs/design/phase1-facts.md``): ``[raw_offset,
raw_length, display_name, addr_spec, state, reason_id]`` plus this module's own
``route`` (the fact shape has no slot for it; a row with no obs-route carries
``None``). A group's members are the **flat** rows that follow the group row --
the sidecars type them flat (and record the ambiguity in their own
``labels.undetermined``); see the Turn 1.2 report finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .rfc2047 import decode_encoded_words

__all__ = [
    "ADDRESS_STATES",
    "AddressRow",
    "GAP_HEADERS_ADDRESS_UNPARSABLE",
    "parse_address_list",
]

#: The closed ``state`` vocabulary of an address row (facts doc, ``headers.addresses``).
ADDRESS_STATES: Final[tuple[str, ...]] = ("parsed", "group", "unparsed")

#: The **closed** reason id a recorded failure carries (``docs/design/phase0-gaps.md``,
#: ``headers.address_unparsable``): an address field whose structure does not parse; the
#: raw value is kept verbatim and no address list is claimed for that fragment.
GAP_HEADERS_ADDRESS_UNPARSABLE: Final[str] = "headers.address_unparsable"

#: RFC 5322 3.2.3 atext: the bytes an atom may carry. Non-ASCII (>= 0x80) bytes are
#: atom text verbatim too (SMTPUTF8), so they are accepted beside atext.
_ATEXT: Final[frozenset[int]] = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    b"!#$%&'*+-/=?^_`{|}~"
)

#: The single-byte RFC 5322 specials that are not handled as their own multi-byte token
#: (``(`` ``"`` ``[`` are consumed by :func:`_tokenize`). Everything else is ``other``.
_SPECIALS: Final[dict[int, str]] = {
    0x29: "rparen",
    0x3C: "lt",
    0x3E: "gt",
    0x3A: "colon",
    0x3B: "semicolon",
    0x40: "at",
    0x5C: "backslash",
    0x2C: "comma",
    0x2E: "dot",
    0x5D: "rbracket",
}

_CFWS_KINDS: Final[frozenset[str]] = frozenset({"wsp", "comment"})


@dataclass(frozen=True)
class AddressRow:
    """One address of one field, as a byte span plus what the tokenizer read from it.

    ``offset``/``length`` are the byte span into the **raw message** (already the field
    value's base offset plus the offset inside the value). ``state`` is one of
    :data:`ADDRESS_STATES`; ``reason_id`` is ``None`` unless ``state == "unparsed"``,
    when it is :data:`GAP_HEADERS_ADDRESS_UNPARSABLE`. ``route`` is an obs-route's text
    kept verbatim (``None`` for an address with no route) -- it is this module's own
    field because the fact row's shape has no route slot.
    """

    offset: int
    length: int
    display_name: str | None
    addr_spec: str | None
    state: str
    reason_id: str | None
    route: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("offset", self.offset), ("length", self.length)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"address_row.{name} must be an int >= 0, got {value!r}")
        if self.state not in ADDRESS_STATES:
            raise ValueError(f"address_row.state must be one of {ADDRESS_STATES}, got {self.state!r}")
        if self.state == "unparsed":
            if self.reason_id != GAP_HEADERS_ADDRESS_UNPARSABLE:
                raise ValueError(
                    "an unparsed address row must carry the closed reason id "
                    f"{GAP_HEADERS_ADDRESS_UNPARSABLE!r}, got {self.reason_id!r}"
                )
        elif self.reason_id is not None:
            raise ValueError(f"a {self.state!r} address row carries no reason_id")

    @property
    def end(self) -> int:
        return self.offset + self.length

    def as_fact_row(self) -> list[object]:
        """The ``headers.addresses`` row: ``[offset, length, display_name, addr_spec, state,
        reason_id]`` -- the record's first six members, with ``route`` carried beside them."""
        return [self.offset, self.length, self.display_name, self.addr_spec, self.state, self.reason_id]


@dataclass(frozen=True)
class _Token:
    kind: str
    start: int
    end: int


def _tokenize(value: bytes) -> list[_Token]:
    """The bytes as a **linear** token stream (no regex; one pass, no backtracking).

    Tokens: ``wsp`` (a run of SP/HTAB/CR/LF -- obs-fold included), ``comment`` (``(`` to the
    matching ``)``, nested, quoted-pair aware), ``quoted`` (a quoted-string), ``domain_literal``
    (``[`` to ``]``), ``atom`` (a run of atext / byte >= 0x80), a one-byte special token, or
    ``other``. An unterminated comment/string/literal runs to the end of the value.
    """
    tokens: list[_Token] = []
    index = 0
    size = len(value)
    while index < size:
        byte = value[index]
        if byte in (0x20, 0x09, 0x0D, 0x0A):
            end = index + 1
            while end < size and value[end] in (0x20, 0x09, 0x0D, 0x0A):
                end += 1
            tokens.append(_Token("wsp", index, end))
            index = end
        elif byte == 0x28:  # '(' -- a comment, nested, quoted-pair aware
            end = index + 1
            depth = 1
            while end < size and depth:
                here = value[end]
                if here == 0x5C:  # quoted-pair: skip the escaped byte
                    end += 2
                    continue
                if here == 0x28:
                    depth += 1
                elif here == 0x29:
                    depth -= 1
                end += 1
            end = min(end, size)
            tokens.append(_Token("comment", index, end))
            index = end
        elif byte == 0x22:  # '"' -- a quoted-string
            end = index + 1
            while end < size and value[end] != 0x22:
                if value[end] == 0x5C:
                    end += 2
                    continue
                end += 1
            end = min(end + 1, size)
            tokens.append(_Token("quoted", index, end))
            index = end
        elif byte == 0x5B:  # '[' -- a domain-literal
            end = index + 1
            while end < size and value[end] != 0x5D:
                if value[end] == 0x5C:
                    end += 2
                    continue
                end += 1
            end = min(end + 1, size)
            tokens.append(_Token("domain_literal", index, end))
            index = end
        elif byte >= 0x80 or byte in _ATEXT:
            end = index + 1
            while end < size and (value[end] >= 0x80 or value[end] in _ATEXT):
                end += 1
            tokens.append(_Token("atom", index, end))
            index = end
        else:
            tokens.append(_Token(_SPECIALS.get(byte, "other"), index, index + 1))
            index += 1
    return tokens


def _skip_cfws(tokens: list[_Token], index: int) -> int:
    """Advance past comment/whitespace tokens (CFWS never splits an address)."""
    while index < len(tokens) and tokens[index].kind in _CFWS_KINDS:
        index += 1
    return index


def _decode_verbatim(data: bytes) -> str:
    """The bytes as text: UTF-8 where they are valid UTF-8, else latin-1 (lossless).

    Never IDNA- or NFC-normalised: the text is exactly the bytes between the tokens.
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _unquote(data: bytes) -> bytes:
    """A quoted-string token's content, quotes removed and quoted-pairs unescaped."""
    inner = data[1:-1] if len(data) >= 2 and data[:1] == b'"' and data[-1:] == b'"' else data[1:]
    out = bytearray()
    index = 0
    while index < len(inner):
        if inner[index] == 0x5C and index + 1 < len(inner):
            out.append(inner[index + 1])
            index += 2
        else:
            out.append(inner[index])
            index += 1
    return bytes(out)


def _phrase_text(value: bytes, words: list[tuple[str, int, int]], max_work_units: int) -> str | None:
    """A display-name phrase's text: words joined by single spaces, encoded words decoded.

    A ``quoted`` word contributes its unquoted content; a bare word its bytes. The joined
    bytes go through :func:`emailextract.rfc2047.decode_encoded_words`; when no encoded word
    decoded, the bytes are raw text (UTF-8 where valid, else latin-1) -- a raw 8-bit display
    name is kept verbatim, never mojibake.
    """
    parts = [
        _unquote(value[start:end]) if kind == "quoted" else value[start:end]
        for kind, start, end in words
    ]
    raw = b" ".join(parts)
    decoded = decode_encoded_words(raw, max_work_units=max_work_units)
    text = decoded.text if decoded.decoded else _decode_verbatim(raw)
    return text.strip() or None


def _parse_phrase(tokens: list[_Token], index: int) -> tuple[list[tuple[str, int, int]], int]:
    """A phrase: words (atom/dot runs and quoted-strings) separated by CFWS.

    Returns ``(words, next_index)`` where ``next_index`` is right after the last word token
    (not past trailing CFWS); an empty phrase returns ``([], index)``.
    """
    words: list[tuple[str, int, int]] = []
    cursor = index
    while True:
        here = _skip_cfws(tokens, cursor)
        if here >= len(tokens):
            break
        token = tokens[here]
        if token.kind == "quoted":
            words.append(("quoted", token.start, token.end))
            cursor = here + 1
        elif token.kind in ("atom", "dot"):
            start = token.start
            end = token.end
            probe = here + 1
            while probe < len(tokens) and tokens[probe].kind in ("atom", "dot"):
                end = tokens[probe].end
                probe += 1
            words.append(("word", start, end))
            cursor = probe
        else:
            break
    return words, cursor


def _parse_local_part(tokens: list[_Token], index: int) -> tuple[int, int, int]:
    """A local-part (dot-atom / quoted-string / obs-local-part): ``(first, last, next)``.

    ``first``/``last`` are the first and last **word** token indices; ``(-1, -1, index)`` when
    there is none.
    """
    if index >= len(tokens) or tokens[index].kind not in ("atom", "quoted"):
        return -1, -1, index
    first = last = index
    cursor = index + 1
    while True:
        here = _skip_cfws(tokens, cursor)
        if here < len(tokens) and tokens[here].kind == "dot":
            after = _skip_cfws(tokens, here + 1)
            if after < len(tokens) and tokens[after].kind in ("atom", "quoted"):
                last = after
                cursor = after + 1
                continue
        break
    return first, last, cursor


def _parse_domain(tokens: list[_Token], index: int) -> tuple[int, int, int]:
    """A domain (dot-atom / domain-literal / obs-domain): ``(first, last, next)``.

    ``(-1, -1, index)`` when there is none.
    """
    if index >= len(tokens):
        return -1, -1, index
    if tokens[index].kind == "domain_literal":
        return index, index, index + 1
    if tokens[index].kind != "atom":
        return -1, -1, index
    first = last = index
    cursor = index + 1
    while True:
        here = _skip_cfws(tokens, cursor)
        if here < len(tokens) and tokens[here].kind == "dot":
            after = _skip_cfws(tokens, here + 1)
            if after < len(tokens) and tokens[after].kind == "atom":
                last = after
                cursor = after + 1
                continue
        break
    return first, last, cursor


def _parse_addr_spec(
    value: bytes,
    tokens: list[_Token],
    index: int,
) -> tuple[int, int, int, bytes] | None:
    """An addr-spec: ``(start, end, next_index, text)`` or ``None`` when there is none.

    ``text`` is the local-part + ``@`` + domain with CFWS **dropped** (a comment inside an
    address does not split it and does not enter the addr-spec text; it stays inside the
    row's byte span).
    """
    cursor = _skip_cfws(tokens, index)
    local_first, _local_last, cursor = _parse_local_part(tokens, cursor)
    if local_first < 0:
        return None
    at = _skip_cfws(tokens, cursor)
    if at >= len(tokens) or tokens[at].kind != "at":
        return None
    domain_first, domain_last, cursor = _parse_domain(tokens, _skip_cfws(tokens, at + 1))
    if domain_first < 0:
        return None
    text = b"".join(
        value[token.start : token.end]
        for token in tokens[local_first : domain_last + 1]
        if token.kind not in _CFWS_KINDS
    )
    return tokens[local_first].start, tokens[domain_last].end, cursor, text


@dataclass(frozen=True)
class _Parsed:
    """An address the scanner read: its significant bytes and what they mean."""

    state: str
    sig_start: int
    sig_end: int
    display_name: str | None = None
    addr_spec: str | None = None
    route: str | None = None
    group_start: int = 0
    group_end: int = 0


def _mailbox(
    value: bytes,
    tokens: list[_Token],
    index: int,
    max_work_units: int,
) -> tuple[_Parsed | None, int]:
    """A mailbox at ``index``: name-addr (display-name and/or angle-addr) or addr-spec."""
    words, after_words = _parse_phrase(tokens, index)
    if words:
        look = _skip_cfws(tokens, after_words)
        if look < len(tokens) and tokens[look].kind == "lt":
            return _angle(value, tokens, look, words[0][1], words, max_work_units)
    if index < len(tokens) and tokens[index].kind == "lt":
        return _angle(value, tokens, index, tokens[index].start, [], max_work_units)
    spec = _parse_addr_spec(value, tokens, index)
    if spec is not None:
        start, end, cursor, text = spec
        return (
            _Parsed(
                state="parsed",
                sig_start=start,
                sig_end=end,
                display_name=None,
                addr_spec=_decode_verbatim(text),
            ),
            cursor,
        )
    return None, index


def _angle(
    value: bytes,
    tokens: list[_Token],
    lt_index: int,
    sig_start: int,
    words: list[tuple[str, int, int]],
    max_work_units: int,
) -> tuple[_Parsed | None, int]:
    """A name-addr's angle-addr: ``<`` [obs-route] addr-spec ``>``.

    The display-name (``words``) is decoded by RFC 2047; an obs-route before the addr-spec is
    kept verbatim beside the final mailbox. ``(None, lt_index)`` when the angle-addr is not
    well formed -- the caller then treats the whole segment as one ``unparsed`` fragment.
    """
    cursor = _skip_cfws(tokens, lt_index + 1)
    route: str | None = None
    if cursor < len(tokens) and tokens[cursor].kind == "at":
        route_start = tokens[cursor].start
        while cursor < len(tokens) and tokens[cursor].kind != "colon":
            cursor += 1
        if cursor >= len(tokens):
            return None, lt_index
        route = _decode_verbatim(value[route_start : tokens[cursor].start]).strip() or None
        cursor = _skip_cfws(tokens, cursor + 1)
    spec = _parse_addr_spec(value, tokens, cursor)
    if spec is None:
        return None, lt_index
    start, end, after, text = spec
    close = _skip_cfws(tokens, after)
    if close >= len(tokens) or tokens[close].kind != "gt":
        return None, lt_index
    display = _phrase_text(value, words, max_work_units) if words else None
    return (
        _Parsed(
            state="parsed",
            sig_start=sig_start,
            sig_end=tokens[close].end,
            display_name=display,
            addr_spec=_decode_verbatim(text),
            route=route,
        ),
        close + 1,
    )


def _group(
    value: bytes,
    tokens: list[_Token],
    words: list[tuple[str, int, int]],
    colon_index: int,
    max_work_units: int,
) -> tuple[list[_Parsed], int]:
    """A group: ``display-name ":" [mailbox-list] ";"`` -- the group row, then its members'."""
    name_start = words[0][1]
    colon_end = tokens[colon_index].end
    members: list[_Parsed] = []
    semicolon_end = -1
    cursor = colon_index + 1
    while True:
        cursor = _skip_cfws(tokens, cursor)
        if cursor >= len(tokens):
            break
        kind = tokens[cursor].kind
        if kind == "semicolon":
            semicolon_end = tokens[cursor].end
            cursor += 1
            break
        if kind == "comma":
            cursor += 1
            continue
        member, after = _mailbox(value, tokens, cursor, max_work_units)
        if member is None:
            end_of_fragment = _resync(tokens, cursor)
            fragment_end = _last_significant_end(tokens, cursor, end_of_fragment)
            fragment_start = tokens[cursor].start
            members.append(
                _Parsed(
                    state="unparsed",
                    sig_start=fragment_start,
                    sig_end=fragment_end,
                    addr_spec=_decode_verbatim(value[fragment_start:fragment_end]),
                )
            )
            cursor = end_of_fragment
            continue
        members.append(member)
        cursor = after
    if members:
        group_end = colon_end
    elif semicolon_end >= 0:
        group_end = semicolon_end
    else:
        group_end = colon_end
    text = _decode_verbatim(value[name_start:group_end]) if not members else None
    group = _Parsed(
        state="group",
        sig_start=name_start,
        sig_end=group_end,
        display_name=None,
        addr_spec=text,
        group_start=name_start,
        group_end=group_end,
    )
    return [group, *members], cursor


def _resync(tokens: list[_Token], index: int) -> int:
    """The index of the next top-level ``,`` or ``;`` (or the end) at or after ``index``."""
    while index < len(tokens) and tokens[index].kind not in ("comma", "semicolon"):
        index += 1
    return index


def _last_significant_end(tokens: list[_Token], start: int, stop: int) -> int:
    """The offset just past the last non-CFWS token in ``tokens[start:stop]`` (0 when none)."""
    end = 0
    for token in tokens[start:stop]:
        if token.kind not in _CFWS_KINDS:
            end = token.end
    return end


def _one_address(
    value: bytes,
    tokens: list[_Token],
    index: int,
    max_work_units: int,
) -> tuple[list[_Parsed] | None, int]:
    """One top-level address at ``index``: its rows (a group plus its members, or one
    mailbox), or ``(None, index)`` when nothing well formed starts here."""
    words, after_words = _parse_phrase(tokens, index)
    if words:
        look = _skip_cfws(tokens, after_words)
        if look < len(tokens) and tokens[look].kind == "colon":
            return _group(value, tokens, words, look, max_work_units)
        if look < len(tokens) and tokens[look].kind == "lt":
            parsed, after = _angle(value, tokens, look, words[0][1], words, max_work_units)
            return ([parsed], after) if parsed is not None else (None, index)
    if index < len(tokens) and tokens[index].kind == "lt":
        parsed, after = _angle(value, tokens, index, tokens[index].start, [], max_work_units)
        return ([parsed], after) if parsed is not None else (None, index)
    spec = _parse_addr_spec(value, tokens, index)
    if spec is not None:
        start, end, cursor, text = spec
        return (
            [
                _Parsed(
                    state="parsed",
                    sig_start=start,
                    sig_end=end,
                    display_name=None,
                    addr_spec=_decode_verbatim(text),
                )
            ],
            cursor,
        )
    return None, index


def _rows(
    value: bytes,
    tokens: list[_Token],
    base_offset: int,
    max_work_units: int,
) -> list[AddressRow]:
    """The value's top-level addresses, with the span each row carries.

    A single top-level address that is not a group spans the **whole value** (leading CFWS
    included -- the sidecars' span convention); a group row spans ``name ":"`` (plus ``";"``
    when it has no members); any other row spans its own significant bytes.
    """
    parsed: list[_Parsed] = []
    index = 0
    size = len(tokens)
    while index < size:
        index = _skip_cfws(tokens, index)
        if index >= size:
            break
        kind = tokens[index].kind
        if kind in ("comma", "semicolon"):  # obs-addr-list empty element: never an empty address
            index += 1
            continue
        segment_start = index
        found, after = _one_address(value, tokens, index, max_work_units)
        stop = _skip_cfws(tokens, after) if found is not None else index
        if found is not None and (stop >= size or tokens[stop].kind in ("comma", "semicolon")):
            parsed.extend(found)
            index = after
            continue
        # Not a well-formed segment: one unparsed row over the fragment, resynchronise after.
        end_of_fragment = _resync(tokens, index)
        fragment_start = tokens[segment_start].start
        fragment_end = _last_significant_end(tokens, segment_start, end_of_fragment)
        parsed.append(
            _Parsed(
                state="unparsed",
                sig_start=fragment_start,
                sig_end=fragment_end,
                addr_spec=_decode_verbatim(value[fragment_start:fragment_end]),
            )
        )
        index = end_of_fragment

    if not parsed:
        return []

    single = len(parsed) == 1
    rows: list[AddressRow] = []
    for item in parsed:
        if item.state == "group":
            start, end = item.group_start, item.group_end
        elif single:
            start, end = 0, len(value)
        else:
            start, end = item.sig_start, item.sig_end
        rows.append(
            AddressRow(
                offset=base_offset + start,
                length=end - start,
                display_name=item.display_name,
                addr_spec=item.addr_spec,
                state=item.state,
                reason_id=GAP_HEADERS_ADDRESS_UNPARSABLE if item.state == "unparsed" else None,
                route=item.route,
            )
        )
    return rows


def parse_address_list(
    value: bytes,
    *,
    base_offset: int,
    max_work_units: int,
) -> list[AddressRow]:
    """The address rows of one field's **value bytes**, spans absolute in the raw message.

    ``value`` is the verbatim value bytes (``RawHeaderField.value_span`` slice); ``base_offset``
    is where it starts in the raw message, so every row's ``offset`` is a raw-message offset.
    ``max_work_units`` is the caller's RFC 2047 work budget (``Limits``), passed through to
    the display-name decoder. The function is **total**: it never raises on input content and
    returns a fresh, unaliased list.
    """
    if not isinstance(value, bytes):
        raise TypeError(f"value must be bytes, got {type(value).__name__}")
    if isinstance(base_offset, bool) or not isinstance(base_offset, int) or base_offset < 0:
        raise ValueError(f"base_offset must be an int >= 0, got {base_offset!r}")
    tokens = _tokenize(value)
    return _rows(value, tokens, base_offset, max_work_units)
