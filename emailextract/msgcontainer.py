"""Turn 1b.5: the A'' projection -- a ``.msg`` opened as a container the one walker reads.

``MsgContainer`` is the first *real* producer of Turn 1b.1's provenance shapes. It opens
an ``.msg`` through :mod:`emailextract.cfb`, reads its MAPI layer through
:mod:`emailextract.mapi`, and builds a deterministic **virtual RFC 822 byte string** --
the projection -- plus a :class:`~emailextract.container.SpanRow` table saying which CFB
stream every region came from. The one existing walker then measures that virtual string
exactly as it measures an ``.eml``, and the assembler fills the records' provenance from
the span table (contract section 8, points 1-8).

Layout of the virtual message (D1), in this order:

1. the projection's own **structural header lines** -- ``MIME-Version``, ``Content-Type``
   with the chosen ``charset``, ``Content-Transfer-Encoding``, or a synthetic
   ``multipart/alternative`` with a synthetic boundary -- each a ``SYNTHETIC`` row;
2. the ``0x007D`` transport-header text, re-encoded to UTF-8, as one ``REENCODED`` row per
   header line, so each :class:`~emailextract.model.HeaderField` carries its own source
   range (contract section 8, point 1);
3. one synthetic blank line (a ``SYNTHETIC`` row), then the body leaves -- a pass-through
   ``0x1013`` HTML leaf (``STREAM``), a re-encoded ``0x1000`` plain leaf (``REENCODED``),
   or both as a ``multipart/alternative`` whose delimiters are ``SYNTHETIC`` rows.

**Why the synthetic structure goes first.** The transport headers' ``Content-Type``
describes the *original* MIME message, never the ``.msg``'s own structure (build spec,
"Measured facts"); constraint C1 says the ``.msg``'s own streams decide the structure. The
walker's header reader (and every consumer that reads a field by name) takes the **first**
``Content-Type``/``Content-Transfer-Encoding``/``MIME-Version``, so the projection's own
lines go first and win; the original's structural lines stay verbatim afterwards, as
ordinary header fields about the original.

**Structure comes from the streams, not the property table (C1).** A body stream and the
transport-header stream are found by name in the directory, never through a property
entry: a real message's ``0x007D`` may or may not carry a table entry, and the ``.msg``'s
own streams are the truth about its structure.

**headers is evidence only (D2).** The ``HeaderField`` records are the fields of the
``0x007D`` text; the synthetic structural lines are scaffolding, not evidence, and do not
appear in ``headers`` (C6). A ``.msg`` with no ``0x007D`` has ``headers == []``.

Class outcomes (D7). A ``not_ipm_note`` or ``signed_or_encrypted`` class opens nothing
past the class: the document is ``UNSUPPORTED`` (through ``status_outcome``), the class is
verbatim in ``container_facts``, and the virtual message is empty. A ``class_absent`` (or
``class_unreadable``) message has no class to stop on, so it is projected and parsed --
the owner's suggested reading, reported in the turn's outcome note.

Nothing here raises on input: :func:`cfb.open_cfb` returns a refusal, :func:`mapi.read_message`
returns a message, and a value that cannot be decoded is a recorded fault, never a repaired
string. The container publishes only what it read; every fact value is a ``str``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, NamedTuple, Sequence

from . import cfb, mapi
from .container import CharsetOrigin, SpanRow
from .ids import sha256_hex
from .model import (
    ContainerKind,
    ContainerStreamAxis,
    EncodingSource,
    Status,
    StatusOutcome,
)

__all__ = ["ContainerGap", "LABEL_BY_CODEPAGE", "LABEL_BY_RUNG", "MsgContainer", "PROJECTION"]

#: The projection's own name in ``container_facts`` (D6).
PROJECTION = "virtual_rfc822"

#: The code page number -> the charset label the virtual bytes declare (D4).
LABEL_BY_CODEPAGE: Mapping[int, str] = {
    1252: "windows-1252",
    20127: "us-ascii",
    28591: "iso-8859-1",
    65001: "utf-8",
}
#: The ``mapi`` ladder rungs 3-5 -> their label (D4).
LABEL_BY_RUNG: Mapping[str, str] = {
    "ascii": "us-ascii",
    "utf8_strict": "utf-8",
    "windows_1252": "windows-1252",
}
#: ``mapi``'s ``encoding_source`` strings -> the record's own enum.
_ENCODING_SOURCES: Mapping[str, EncodingSource] = {
    "internet_cpid": EncodingSource.INTERNET_CPID,
    "message_cpid": EncodingSource.MESSAGE_CPID,
    "ascii": EncodingSource.ASCII,
    "utf8_strict": EncodingSource.UTF8_STRICT,
    "windows_1252": EncodingSource.WINDOWS_1252,
}

#: The property tags this turn reads out of the container.
TRANSPORT_HEADERS = 0x007D
BODY_PLAIN = 0x1000
BODY_RTF = 0x1009
BODY_HTML = 0x1013
PROP_SUBJECT = 0x0037

#: The registered document-level gaps this container can record.
GAP_TRANSPORT_HEADERS_ABSENT = "msg.transport_headers_absent"
GAP_MAPI_HEADER_PROPERTY_DISAGREE = "headers.mapi_header_property_disagree"
GAP_STREAM_TRUNCATED = "msg.stream_truncated"

_SUB = "__substg1.0_"
#: The synthetic boundary's alphabet: a boundary must not occur in any body, so it is built
#: from a counter until it is absent -- deterministic, so the same bytes give the same one.
_BOUNDARY_BASE = b"=_msg_alt_"
_BLANK = b"\r\n"


class ContainerGap(NamedTuple):
    """One document-level gap the container recorded: its id and its detail.

    Producer-internal, like :class:`~emailextract.container.SpanRow`: the L1 layer reads it
    (Turn 1b.10) and no record a consumer cites carries it. ``detail`` is ``""`` when the
    gap has none, and the property text verbatim where D8 says to record it.
    """

    gap_id: str
    detail: str = ""


class _Body(NamedTuple):
    """One body stream's reading: whether it is present, its text, and its fault."""

    present: bool
    text: "str | None"
    fault: "str | None"


def _stream_name(tag: int, prop_type: int) -> str:
    return f"{_SUB}{tag:04X}{prop_type:04X}"


def _strip_one_trailing_blank(text: str) -> str:
    """Drop one trailing blank line (``\\r\\n\\r\\n`` or ``\\n\\n``) from header text.

    The projection owns the blank line that ends its header block, so the transport text's
    own trailing blank line is removed and replaced by the synthetic separator (D1). One
    only: a body cannot begin here, so a second blank line is kept verbatim.
    """
    if text.endswith("\r\n\r\n"):
        return text[:-2]
    if text.endswith("\n\n"):
        return text[:-1]
    return text


def _line_spans(text: str) -> list[tuple[int, str]]:
    """``(char offset, line including its terminator)`` for each line of ``text``."""
    spans: list[tuple[int, str]] = []
    start = 0
    length = len(text)
    while start < length:
        newline = text.find("\n", start)
        if newline == -1:
            spans.append((start, text[start:]))
            break
        spans.append((start, text[start : newline + 1]))
        start = newline + 1
    return spans


def _byte_lines(raw: bytes) -> list[tuple[int, int]]:
    """``(byte offset, byte length)`` for each ``LF``-terminated line of ``raw``."""
    spans: list[tuple[int, int]] = []
    start = 0
    length = len(raw)
    while start < length:
        newline = raw.find(b"\n", start)
        if newline == -1:
            spans.append((start, length - start))
            break
        spans.append((start, newline + 1 - start))
        start = newline + 1
    return spans


def _label_of(text: "mapi.TextValue") -> tuple[str, EncodingSource]:
    """The charset label and ``EncodingSource`` for one HTML leaf (D4)."""
    if text.text is None:
        return "windows-1252", EncodingSource.FALLBACK
    if text.encoding_source in ("internet_cpid", "message_cpid"):
        label = LABEL_BY_CODEPAGE.get(text.declared_cp or -1, "windows-1252")
        return label, _ENCODING_SOURCES[text.encoding_source]
    if text.encoding_source in LABEL_BY_RUNG:
        return LABEL_BY_RUNG[text.encoding_source], _ENCODING_SOURCES[text.encoding_source]
    return "utf-8", EncodingSource.DECLARED_CHARSET


class MsgContainer:
    """A ``.msg`` projected into a virtual RFC 822 message the one walker reads.

    ``container_hash()`` addresses the **CFB file** (D14: the file, not the projection);
    ``raw_bytes()`` is the virtual message. ``span_provenance``, ``charset_sources``,
    ``sector_accounting``, ``cap_observations`` and ``container_gaps`` are the producer
    channels; ``cap_observation`` carries the CFB cap that stopped the open, and
    ``status_outcome`` is the document status the container already knows (a non-``IPM.Note``
    class is ``UNSUPPORTED``; a CFB cap is ``SKIPPED``) -- both ``None`` for an ordinary
    message, so the assembler's default is exactly its current expression.
    """

    kind = ContainerKind.CFB_MSG
    #: The virtual header bytes are UTF-8, so the header stage reads them as such (D1).
    value_codec = "utf-8"

    def __init__(
        self,
        data: bytes,
        *,
        cfb_limits: cfb.CfbLimits = cfb.DEFAULT_CFB_LIMITS,
        framing: int = 0,
    ) -> None:
        if not isinstance(data, bytes):
            raise TypeError(f"msgcontainer takes bytes, got {type(data).__name__}")
        self._data = data
        self._framing = framing if isinstance(framing, int) and framing > 0 else 0
        self._cfb: "cfb.CfbFile | None" = None
        self._message: "mapi.MapiMessage | None" = None
        self.cap_observation: "cfb.CapObservation | None" = None
        self.status_outcome: "StatusOutcome | None" = None
        self.container_gaps: tuple[ContainerGap, ...] = ()
        self.span_provenance: tuple[SpanRow, ...] = ()
        self.charset_sources: Mapping[str, CharsetOrigin] = {}
        self.cap_observations: Mapping[str, int] = {}
        self.sector_accounting: Mapping[str, int] = {}
        self._raw = b""
        self._facts: dict[str, str] = {"adapter": "cfb_msg", "projection": PROJECTION}

        opened = cfb.open_cfb(data, limits=cfb_limits)
        if isinstance(opened, cfb.CfbFile):
            self._cfb = opened
            self._message = mapi.read_message(opened)
            self.sector_accounting = {
                f"sectors.{name}": value for name, value in opened.accounting
            }
            self._project()
            if opened.faults and self.status_outcome is None:
                # A per-stream chain fault (D7): the document is TRUNCATED with the mapped
                # reason, and the registered gap names the faulted stream and its fault.
                path, fault, reason = opened.faults[0]
                self.status_outcome = StatusOutcome(status=Status.TRUNCATED, reason=reason)
                self.container_gaps = self.container_gaps + (
                    ContainerGap(GAP_STREAM_TRUNCATED, f"{path}:{fault}"),
                )
        else:
            self.cap_observation = opened.observation
            self._facts["refusal"] = opened.reason
            if opened.observation is not None:
                self.status_outcome = StatusOutcome(
                    status=Status.SKIPPED, reason=opened.observation.cap_id
                )
                self.cap_observations = {
                    opened.observation.cap_id: opened.observation.observed
                }

    # ------------------------------------------------------- the Container Protocol

    def container_hash(self) -> str:
        return sha256_hex(self._data)

    def raw_bytes(self) -> bytes:
        return self._raw

    def container_facts(self) -> dict[str, str]:
        return dict(self._facts)

    # --------------------------------------------------------------------- the build

    def _project(self) -> None:
        """Build the virtual message, the span table, the charset map and the facts."""
        assert self._cfb is not None and self._message is not None
        message = self._message
        self._facts.update(self._layout_facts())
        self._facts.update(
            {
                "message_class": message.message_class or "absent",
                "named_property_count": str(len(message.named_tags)),
                "internet_codepage": (
                    "absent" if message.internet_cp is None else str(message.internet_cp)
                ),
                "message_codepage": (
                    "absent" if message.message_cp is None else str(message.message_cp)
                ),
                "body_streams": "none",
                "has_transport_headers": "false",
            }
        )
        self._facts.update({key: str(value) for key, value in self.sector_accounting.items()})

        if message.class_verdict in (mapi.CLASS_NOT_IPM_NOTE, mapi.CLASS_SIGNED):
            # Nothing past the class is opened (D7): the class is verbatim in the facts, and
            # the gate's own registered gap rides with it. ``msg.class_absent`` /
            # ``msg.class_unreadable`` are *not* gaps here: nothing stopped, so the message is
            # projected and parsed (the owner's suggested reading, in the outcome note).
            if mapi.MSG_CLASS_NOT_IPM_NOTE in message.observations:
                self.container_gaps = (
                    ContainerGap(mapi.MSG_CLASS_NOT_IPM_NOTE, message.message_class),
                )
            self.status_outcome = StatusOutcome(status=Status.UNSUPPORTED)
            return

        plain = self._read_body(BODY_PLAIN)
        html, html_fault = self._binary_body(BODY_HTML)
        rtf = self._has_stream(((BODY_RTF, mapi.PT_BINARY),))
        transport = self._read_transport()
        transport_text = transport.text if transport.present else None
        gaps: list[ContainerGap] = []
        if plain.fault is not None:
            gaps.append(ContainerGap(plain.fault))
        if html_fault is not None:
            gaps.append(ContainerGap(html_fault))

        chunks: list[bytes] = []
        size = 0
        rows: list[SpanRow] = []

        def emit_segments(row: SpanRow, *segments: bytes) -> None:
            """Append ``segments`` as one virtual region (D3's offsets are over the sum).

            Big source bytes are appended by reference and concatenated once, by
            ``raw_bytes``: a per-part ``header + body`` copy would double a large leaf
            (D10's memory budget).
            """
            nonlocal size
            length = sum(len(segment) for segment in segments)
            rows.append(replace(row, virtual_offset=size, virtual_len=length))
            chunks.extend(segments)
            size += length

        def emit(chunk: bytes, row: SpanRow) -> None:
            emit_segments(row, chunk)

        def synthetic(role: str, ordinal: int, chunk: bytes) -> None:
            emit(
                chunk,
                SpanRow(
                    axis=ContainerStreamAxis.SYNTHETIC,
                    source_stream=f"synthetic:{role}:{ordinal}",
                    source_byte_offset=None,
                    source_byte_len=None,
                    source_sha256=None,
                    virtual_offset=0,
                    virtual_len=0,
                ),
            )

        boundary = self._choose_boundary((plain.text or "").encode("utf-8"), html or b"")
        ordinal = 0
        if transport_text is not None and transport_text.startswith("\ufeff"):
            # A UTF-8 BOM at the head of the transport-header text is the tolerated leading
            # prelude the header scan already knows (E6); it is projected first, as its own
            # region, so ``headers.leading_bom`` fires exactly as it does for an ``.eml``.
            synthetic("prelude", 1, "\ufeff".encode("utf-8"))
            transport_text = transport_text[1:]
        for line in self._structural_lines(plain.present, html is not None, boundary, html):
            ordinal += 1
            synthetic("structure", ordinal, line)
        if self._framing:
            # The C2 seam: a synthetic pad line lengthens the virtual framing without
            # changing a single source byte (the fake's ``X-Pad`` idea), so a test can
            # require identical ``part_id``s at two framing lengths.
            synthetic("pad", 1, b"X-Pad: " + b"P" * self._framing + b"\r\n")

        if transport_text is None:
            gaps.append(ContainerGap(GAP_TRANSPORT_HEADERS_ABSENT))
        else:
            # The transport text's own trailing blank line is replaced by the projection's
            # synthetic separator, so the header region ends at exactly one blank line and
            # the body leaf begins at its first byte.
            for chunk, row in self._transport_rows(_strip_one_trailing_blank(transport_text)):
                emit(chunk, row)
        synthetic("separator", 1, _BLANK)

        charset_sources: dict[str, CharsetOrigin] = {}
        if plain.present and html is not None:
            synthetic("delimiter", 1, b"--" + boundary + b"\r\n")
            emit(
                b"Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
                + (plain.text or "").encode("utf-8"),
                self._reencoded_row(self._stream_name_for(BODY_PLAIN), decoded=plain.text or ""),
            )
            charset_sources["1.1"] = self._plain_origin()
            synthetic("delimiter", 2, b"\r\n--" + boundary + b"\r\n")
            emit_segments(
                self._stream_row(self._stream_name_for(BODY_HTML), exact=True, payload=html),
                self._html_leaf_header(html),
                html,
            )
            charset_sources["1.2"] = self._html_origin(html)
            synthetic("delimiter", 3, b"\r\n--" + boundary + b"--\r\n")
        elif html is not None:
            emit(
                html,
                self._stream_row(self._stream_name_for(BODY_HTML), exact=True, payload=html),
            )
            charset_sources["1"] = self._html_origin(html)
        elif plain.present:
            emit(
                (plain.text or "").encode("utf-8"),
                self._reencoded_row(self._stream_name_for(BODY_PLAIN), decoded=plain.text or ""),
            )
            charset_sources["1"] = self._plain_origin()

        rows.insert(
            0,
            SpanRow(
                axis=ContainerStreamAxis.SYNTHETIC,
                source_stream="synthetic:root:1",
                source_byte_offset=None,
                source_byte_len=None,
                source_sha256=None,
                virtual_offset=0,
                virtual_len=size,
            ),
        )

        self._raw = b"".join(chunks)
        self.span_provenance = tuple(rows)
        self.charset_sources = charset_sources
        self._facts["body_streams"] = "+".join(
            name
            for name, present in (
                ("plain", plain.present),
                ("html", html is not None),
                ("rtf", rtf),
            )
            if present
        ) or "none"
        self._facts["has_transport_headers"] = "true" if transport.present else "false"
        conflict = self._header_conflict(
            _strip_one_trailing_blank(transport_text) if transport_text is not None else None
        )
        if conflict is not None:
            gaps.append(ContainerGap(GAP_MAPI_HEADER_PROPERTY_DISAGREE, conflict))
        self.container_gaps = tuple(gaps)

    # ------------------------------------------------------------------- the pieces

    def _layout_facts(self) -> dict[str, str]:
        assert self._cfb is not None
        opened = self._cfb
        return {
            "cfb_version": str(opened.version),
            "sector_size": str(opened.sector_size),
            "mini_sector_size": str(opened.mini_sector_size),
            "mini_cutoff": str(opened.mini_cutoff),
            "sector_count": str(opened.sector_count),
            "directory_entries": str(opened.directory_entries),
        }

    def _property(self, tag: int) -> "mapi.Property | None":
        assert self._message is not None
        for prop in self._message.properties:
            if prop.tag == tag:
                return prop
        return None

    def _stream_name_for(self, tag: int) -> str:
        """The stream name of the present stream for ``tag`` (001F before 001E)."""
        candidates = (
            (tag, mapi.PT_UNICODE),
            (tag, mapi.PT_STRING8),
        ) if tag in (TRANSPORT_HEADERS, BODY_PLAIN) else ((tag, mapi.PT_BINARY),)
        for candidate in candidates:
            name = _stream_name(*candidate)
            assert self._cfb is not None
            if cfb.lookup_entry(self._cfb.entries, name) is not None:
                return name
        return _stream_name(*candidates[0])

    def _has_stream(self, candidates: Sequence[tuple[int, int]]) -> bool:
        assert self._cfb is not None
        return any(
            cfb.lookup_entry(self._cfb.entries, _stream_name(tag, prop_type)) is not None
            for tag, prop_type in candidates
        )

    def _read_body(self, tag: int) -> "_Body":
        """One ``001F``/``001E`` string stream decoded, or absent (never raised).

        A UTF-8 BOM heading an 8-bit stream is re-attached as ``U+FEFF`` in the text, so
        the projection can reinstate it as the tolerated leading prelude (E6).
        """
        assert self._cfb is not None
        for prop_type in (mapi.PT_UNICODE, mapi.PT_STRING8):
            name = _stream_name(tag, prop_type)
            if cfb.lookup_entry(self._cfb.entries, name) is None:
                continue
            payload, status = cfb.read_stream(self._cfb, name)
            if status != cfb.FAULT_OK:
                return _Body(False, None, mapi.STREAM_FAULTS.get(status))
            prefix = ""
            if prop_type == mapi.PT_STRING8 and payload[:3] == b"\xef\xbb\xbf":
                payload, prefix = payload[3:], "\ufeff"
            text = self._decode(payload, prop_type)
            if text.text is None:
                return _Body(False, None, text.fault)
            return _Body(True, prefix + text.text, None)
        return _Body(False, None, None)

    def _read_transport(self) -> "_Body":
        return self._read_body(TRANSPORT_HEADERS)

    def _binary_body(self, tag: int) -> "tuple[bytes | None, str | None]":
        assert self._cfb is not None
        name = _stream_name(tag, mapi.PT_BINARY)
        if cfb.lookup_entry(self._cfb.entries, name) is None:
            return None, None
        payload, status = cfb.read_stream(self._cfb, name)
        if status != cfb.FAULT_OK:
            return None, mapi.STREAM_FAULTS.get(status)
        return payload, None

    def _decode(self, payload: bytes, prop_type: int) -> "mapi.TextValue":
        assert self._message is not None
        if prop_type == mapi.PT_UNICODE:
            return mapi.decode_unicode(payload)
        return mapi.decode_string8(
            payload,
            internet_codepage=self._message.internet_cp,
            message_codepage=self._message.message_cp,
        )

    # --------------------------------------------------------- the structural lines

    def _structural_lines(
        self, plain: bool, html: bool, boundary: bytes, html_bytes: "bytes | None"
    ) -> list[bytes]:
        if plain and html:
            return [
                b"MIME-Version: 1.0\r\n",
                b'Content-Type: multipart/alternative; boundary="' + boundary + b'"\r\n',
            ]
        if html:
            label = self._html_origin(html_bytes or b"").declared_charset
            return [
                b"MIME-Version: 1.0\r\n",
                f"Content-Type: text/html; charset={label}\r\n".encode("utf-8"),
                b"Content-Transfer-Encoding: binary\r\n",
            ]
        if plain:
            return [
                b"MIME-Version: 1.0\r\n",
                b"Content-Type: text/plain; charset=utf-8\r\n",
                b"Content-Transfer-Encoding: 8bit\r\n",
            ]
        return [
            b"MIME-Version: 1.0\r\n",
            b"Content-Type: text/plain; charset=us-ascii\r\n",
            b"Content-Transfer-Encoding: 7bit\r\n",
        ]

    def _html_leaf_header(self, html_bytes: bytes) -> bytes:
        label = self._html_origin(html_bytes).declared_charset
        return (
            f"Content-Type: text/html; charset={label}\r\n"
            "Content-Transfer-Encoding: binary\r\n\r\n"
        ).encode("utf-8")

    def _choose_boundary(self, *parts: bytes) -> bytes:
        """A deterministic boundary that occurs in none of ``parts`` (D5).

        Compared against each part separately: concatenating them would copy a large body
        for no reason (D10's memory budget).
        """
        counter = 0
        while True:
            candidate = _BOUNDARY_BASE + str(counter).encode("ascii")
            if all(candidate not in part for part in parts):
                return candidate
            counter += 1

    # ------------------------------------------------------------ the transport rows

    def _transport_rows(self, text: str) -> list[tuple[bytes, SpanRow]]:
        assert self._cfb is not None
        name = self._stream_name_for(TRANSPORT_HEADERS)
        prop_type = mapi.PT_UNICODE if name.endswith("001F") else mapi.PT_STRING8
        raw, status = cfb.read_stream(self._cfb, name)
        if status != cfb.FAULT_OK:
            return []
        digest = sha256_hex(raw)
        utf16 = prop_type == mapi.PT_UNICODE
        # A UTF-8 BOM heads the *8-bit* transport stream when the fixture carries one; it
        # is projected as the leading prelude, so the rows that follow start after it.
        bom = 3 if (not utf16 and raw[:3] == b"\xef\xbb\xbf") else 0
        body = raw[bom:]
        stripped = self._decode(body, prop_type).trailing_nul
        payload = body[: len(body) - (2 if utf16 else 1)] if stripped else body
        byte_lines = _byte_lines(payload)
        rows: list[tuple[bytes, SpanRow]] = []
        for index, (char_offset, line) in enumerate(_line_spans(text)):
            if utf16:
                source_offset, source_len = 2 * char_offset, 2 * len(line)
            elif index < len(byte_lines):
                source_offset, source_len = byte_lines[index]
            else:  # pragma: no cover - the two splits always agree on LF
                source_offset, source_len = 0, len(payload)
            rows.append(
                (
                    line.encode("utf-8"),
                    SpanRow(
                        axis=ContainerStreamAxis.REENCODED,
                        source_stream=name,
                        source_byte_offset=bom + source_offset,
                        source_byte_len=source_len,
                        source_sha256=digest,
                        virtual_offset=0,
                        virtual_len=0,
                        decoded_char_offset=char_offset,
                        decoded_char_len=len(line),
                    ),
                )
            )
        return rows

    # ------------------------------------------------------------------- the rows

    def _stream_row(
        self, name: str, *, exact: bool, payload: bytes | None = None
    ) -> SpanRow:
        """A row for a CFB stream, keyed by its ``__substg1.0_...`` name (D3).

        ``payload`` lets a caller that has already read the stream hand the bytes over
        instead of reading them a second time (D10's memory budget).
        """
        assert self._cfb is not None
        if payload is None:
            payload, _status = cfb.read_stream(self._cfb, name)
        return SpanRow(
            axis=ContainerStreamAxis.STREAM,
            source_stream=name,
            source_byte_offset=0,
            source_byte_len=len(payload),
            source_sha256=sha256_hex(payload),
            virtual_offset=0,
            virtual_len=0,
            exact=exact,
        )

    def _reencoded_row(self, name: str, *, decoded: str) -> SpanRow:
        assert self._cfb is not None
        payload, _status = cfb.read_stream(self._cfb, name)
        return SpanRow(
            axis=ContainerStreamAxis.REENCODED,
            source_stream=name,
            source_byte_offset=0,
            source_byte_len=len(payload),
            source_sha256=sha256_hex(payload),
            virtual_offset=0,
            virtual_len=0,
            decoded_char_offset=0,
            decoded_char_len=len(decoded),
        )

    # -------------------------------------------------------------- the charsets

    def _html_origin(self, html_bytes: bytes) -> CharsetOrigin:
        assert self._message is not None
        text = mapi.decode_string8(
            html_bytes,
            internet_codepage=self._message.internet_cp,
            message_codepage=self._message.message_cp,
        )
        label, source = _label_of(text)
        return CharsetOrigin(used_charset=label, declared_charset=label, encoding_source=source)

    def _plain_origin(self) -> CharsetOrigin:
        prop = self._property(BODY_PLAIN)
        text = prop.text if prop is not None else None
        if text is not None and text.encoding_source in _ENCODING_SOURCES:
            source = _ENCODING_SOURCES[text.encoding_source]
        else:
            source = EncodingSource.DECLARED_CHARSET
        return CharsetOrigin(used_charset="utf-8", declared_charset="utf-8", encoding_source=source)

    # ---------------------------------------------------------- the D8 conflict

    def _header_conflict(self, transport_text: "str | None") -> "str | None":
        """The ``0x0037`` property against the ``0x007D`` ``Subject`` field (D8), or ``None``."""
        if transport_text is None:
            return None
        subject = self._property(PROP_SUBJECT)
        if subject is None or subject.text is None or subject.text.text is None:
            return None
        header_subject: "str | None" = None
        for line in transport_text.split("\n"):
            if line.lower().startswith("subject:"):
                header_subject = line[len("subject:") :].rstrip("\r").lstrip(" \t")
                break
        if header_subject is None or header_subject == subject.text.text:
            return None
        return subject.text.text
