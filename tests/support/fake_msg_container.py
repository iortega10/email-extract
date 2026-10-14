"""Turn 1b.1: the hand-made ``.msg`` stand-in -- virtual RFC 822 bytes plus a hand-written
span table, and the equivalent ``.eml`` twin of each.

No CFB reader exists in this phase (it arrives in Turn 1b.3/1b.5), so the eight provenance
points are exercised against a container built in memory, as Phase 0 exercised the walker
against :class:`~emailextract.container.FakeContainer`. This module is a **test-only**
fixture: the library never imports it, it imports only the library's public shapes, and it
reads no reader and no ``olefile``.

Two constructed messages, each with an ``.eml`` twin whose bytes are exactly the fake's
virtual bytes (so ``walk(msg)`` and ``walk(twin)`` differ only in the container-addressed
provenance):

* :func:`html_message` -- a non-multipart ``text/html`` message whose single part is the
  projection's own framing (a ``SYNTHETIC`` region) and whose ``Subject`` is re-encoded
  from a ``001F`` stream (a ``REENCODED`` region);
* :func:`attach_message` -- the same plus a multipart ``text/html`` child (``REENCODED``)
  and one pass-through ``application/octet-stream`` attachment (a ``STREAM`` region).

Every value here is derived from the **construction**: the virtual offsets come from the
segment map the builder returns, the source streams and their digests are typed from the
bytes the projection claims to come from, and nothing is pasted from running the reader.
The ``framing`` parameter pads one **synthetic** region (the ``X-Pad`` header), so a test
can lengthen the virtual message without changing a single source byte -- which is exactly
the C2 property the kind-gated ids must survive.
"""

from __future__ import annotations

from emailextract.container import (
    CharsetOrigin,
    EmlContainer,
    PersistedSpanRow,
    SpanRow,
    memory_bytes,
)
from emailextract.ids import sha256_hex
from emailextract.model import ContainerKind, ContainerStreamAxis, EncodingSource

__all__ = [
    "ATTACH_ROWS",
    "HTML_ROWS",
    "SECTOR_ACCOUNTING",
    "SOURCE_STREAMS",
    "CharsetOrigin",
    "FakeMsgContainer",
    "attach_message",
    "attach_twin",
    "html_message",
    "html_twin",
    "persisted_rows",
]

#: The one declared caller ``Limits`` every construction is measured under (the walker's
#: five caps, none of which fires on a message this small).
CALLER_VALUES = {
    "max_input_bytes": 64 * 1024 * 1024,
    "max_depth": 16,
    "max_parts": 1000,
    "max_header_bytes": 256 * 1024,
    "max_decoded_part_bytes": 32 * 1024 * 1024,
    "max_decoded_total_bytes": 128 * 1024 * 1024,
    "max_field_work_units_per_byte": 64,
}

#: The readable text and the "CFB" bytes the projection claims to come from. A ``001F``
#: stream is UTF-16LE with a trailing NUL (MS-OXPROPS), which is why the re-encoded body
#: is twice its UTF-8 length plus two.
SUBJECT_TEXT = "Rapport trimestriel Caf\u00e9 Z\u00fcrich"
SUBJECT_STREAM = SUBJECT_TEXT.encode("utf-16-le") + b"\x00\x00"
HTML_TEXT = "<html><body>Rapport trimestriel</body></html>"
HTML_STREAM = HTML_TEXT.encode("utf-16-le") + b"\x00\x00"
BINARY_PAYLOAD = b"\x00\x01\x02binary-attachment"

#: ``stream name -> (bytes, sha256)`` -- the file the projection is derived from. Two
#: messages share it, so a test can hash the same source under two framings.
SOURCE_STREAMS: dict[str, bytes] = {
    "__substg1.0_0037001F": SUBJECT_STREAM,
    "__substg1.0_10130102": HTML_STREAM,
    "__substg1.0_37010102": BINARY_PAYLOAD,
}

#: The eight CFB sector classes (contract section 6), summing to the synthetic file length
#: (a hand-typed account; the sum is asserted by the test, never by the reader).
SECTOR_ACCOUNTING: dict[str, int] = {
    "sectors.header": 512,
    "sectors.difat": 512,
    "sectors.fat": 512,
    "sectors.minifat": 512,
    "sectors.directory": 512,
    "sectors.stream": 4096,
    "sectors.free": 1024,
    "sectors.slack": 137,
}


def _digest(stream: str) -> str:
    return sha256_hex(SOURCE_STREAMS[stream])


def _subject_bytes() -> bytes:
    return f"Subject: {SUBJECT_TEXT}\r\n".encode("utf-8")


def _build_html(pad: bytes) -> tuple[bytes, dict[str, tuple[int, int]]]:
    """The ``text/html`` virtual message and its labelled segments (padding in ``X-Pad``)."""
    raw = bytearray()
    segments: dict[str, tuple[int, int]] = {}

    def mark(label: str, data: bytes) -> None:
        segments[label] = (len(raw), len(data))
        raw.extend(data)

    mark("subject", _subject_bytes())
    mark("pad", b"X-Pad: " + pad + b"\r\n")
    mark("content_type", b"Content-Type: text/html; charset=utf-8\r\n")
    mark("blank", b"\r\n")
    mark("body", HTML_TEXT.encode("utf-8"))
    return bytes(raw), segments


def _build_attach(pad: bytes) -> tuple[bytes, dict[str, tuple[int, int]]]:
    """The multipart virtual message (an html child plus one pass-through attachment)."""
    raw = bytearray()
    segments: dict[str, tuple[int, int]] = {}

    def mark(label: str, data: bytes) -> None:
        segments[label] = (len(raw), len(data))
        raw.extend(data)

    mark("subject", _subject_bytes())
    mark("pad", b"X-Pad: " + pad + b"\r\n")
    mark("content_type", b'Content-Type: multipart/mixed; boundary="B"\r\n')
    mark("blank", b"\r\n")
    mark("delim1", b"--B\r\n")
    mark("leaf_headers", b"Content-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n")
    mark("leaf_body", HTML_TEXT.encode("utf-8"))
    mark("delim2", b"\r\n--B\r\n")
    mark("att_headers", (
        b'Content-Type: application/octet-stream; name="f.bin"\r\n'
        b'Content-Disposition: attachment; filename="f.bin"\r\n'
        b"Content-Transfer-Encoding: binary\r\n\r\n"
    ))
    mark("att_body", BINARY_PAYLOAD)
    mark("delim3", b"\r\n--B--\r\n")
    return bytes(raw), segments


def _row(
    axis: ContainerStreamAxis,
    stream: str | None,
    source: tuple[int, int] | None,
    digest: str | None,
    virtual: tuple[int, int],
) -> SpanRow:
    return SpanRow(
        axis=axis,
        source_stream=stream,
        source_byte_offset=None if source is None else source[0],
        source_byte_len=None if source is None else source[1],
        source_sha256=digest,
        virtual_offset=virtual[0],
        virtual_len=virtual[1],
        exact=axis is ContainerStreamAxis.STREAM,
    )


def _html_rows(segments: dict[str, tuple[int, int]], total: int) -> tuple[SpanRow, ...]:
    """The ``text/html`` message's span table (by construction, never from a walk)."""
    return (
        # The root part's span is the projection's own framing.
        _row(ContainerStreamAxis.SYNTHETIC, "synthetic:root:1", None, None, (0, total)),
        # The re-encoded Subject, a 001F stream in the source.
        _row(
            ContainerStreamAxis.REENCODED,
            "__substg1.0_0037001F",
            (0, len(SUBJECT_STREAM)),
            _digest("__substg1.0_0037001F"),
            segments["subject"],
        ),
    )


def _attach_rows(segments: dict[str, tuple[int, int]], total: int) -> tuple[SpanRow, ...]:
    """The multipart message's span table: the root, the re-encoded Subject and html child,
    and the pass-through attachment."""
    leaf_start = segments["leaf_headers"][0]
    leaf_len = segments["leaf_headers"][1] + segments["leaf_body"][1]
    att_start = segments["att_headers"][0]
    att_len = segments["att_headers"][1] + segments["att_body"][1]
    return (
        _row(ContainerStreamAxis.SYNTHETIC, "synthetic:multipart:1", None, None, (0, total)),
        _row(
            ContainerStreamAxis.REENCODED,
            "__substg1.0_0037001F",
            (0, len(SUBJECT_STREAM)),
            _digest("__substg1.0_0037001F"),
            segments["subject"],
        ),
        _row(
            ContainerStreamAxis.REENCODED,
            "__substg1.0_10130102",
            (0, len(HTML_STREAM)),
            _digest("__substg1.0_10130102"),
            (leaf_start, leaf_len),
        ),
        _row(
            ContainerStreamAxis.STREAM,
            "__substg1.0_37010102",
            (0, len(BINARY_PAYLOAD)),
            _digest("__substg1.0_37010102"),
            (att_start, att_len),
        ),
    )


class FakeMsgContainer:
    """A hand-made ``cfb_msg`` container: virtual bytes, a hand-written span table, and the
    optional producer channels (``charset_sources``, ``sector_accounting``,
    ``cap_observations``) a real ``MsgContainer`` will publish (Turn 1b.5).

    ``container_hash()`` hashes the **source** bytes (D14: the file, not the projection), so
    a part's kind-gated id (point 2) is identical at two framing lengths even though the
    virtual bytes differ. ``raw_bytes()`` is the virtual RFC 822 string the walker measures.
    """

    kind = ContainerKind.CFB_MSG

    def __init__(
        self,
        raw: bytes,
        span_rows: tuple[SpanRow, ...],
        *,
        source_bytes: bytes | None = None,
        charset_sources: dict[str, CharsetOrigin] | None = None,
        sector_accounting: dict[str, int] | None = None,
        cap_observations: dict[str, int] | None = None,
    ) -> None:
        self._raw = raw
        self._source = raw if source_bytes is None else source_bytes
        self.span_provenance = tuple(span_rows)
        self.charset_sources = charset_sources
        self.sector_accounting = sector_accounting
        self.cap_observations = cap_observations
        self._facts = {
            "adapter": "cfb_msg",
            "synthetic": "in_memory",
            "projection": "virtual_rfc822",
        }

    def raw_bytes(self) -> bytes:
        return self._raw

    def container_hash(self) -> str:
        return sha256_hex(self._source)

    def container_facts(self) -> dict[str, str]:
        return dict(self._facts)


#: The charset provenance the walker's ladder cannot produce (a MAPI code page): the
#: assembler must overwrite the record from it (point 5). Keyed by part path.
_CHARSET_SOURCES = {
    "1": CharsetOrigin(
        used_charset="utf-8",
        declared_charset="utf-8",
        encoding_source=EncodingSource.INTERNET_CPID,
    ),
}


def _source_bytes() -> bytes:
    return b"".join(SOURCE_STREAMS[name] for name in sorted(SOURCE_STREAMS))


def html_message(framing: int = 0) -> FakeMsgContainer:
    """The ``text/html`` message: the root is synthetic, the Subject is re-encoded."""
    raw, segments = _build_html(b"P" * framing)
    rows = _html_rows(segments, len(raw))
    return FakeMsgContainer(
        raw,
        rows,
        source_bytes=_source_bytes(),
        charset_sources=dict(_CHARSET_SOURCES),
        sector_accounting=dict(SECTOR_ACCOUNTING),
        cap_observations={
            "size_cap": len(HTML_STREAM),
            "sector_count_cap": 512,
        },
    )


def attach_message(framing: int = 0) -> FakeMsgContainer:
    """The multipart message: a synthetic root, a re-encoded html child, a stream attachment."""
    raw, segments = _build_attach(b"P" * framing)
    rows = _attach_rows(segments, len(raw))
    charset = dict(_CHARSET_SOURCES)
    charset["1.1"] = CharsetOrigin(
        used_charset="windows-1252",
        declared_charset="windows-1252",
        encoding_source=EncodingSource.MESSAGE_CPID,
    )
    return FakeMsgContainer(
        raw,
        rows,
        source_bytes=_source_bytes(),
        charset_sources=charset,
        sector_accounting=dict(SECTOR_ACCOUNTING),
        cap_observations={
            "size_cap": len(BINARY_PAYLOAD),
        },
    )


def html_twin(framing: int = 0) -> EmlContainer:
    """The equivalent ``.eml`` message: the fake's virtual bytes, served verbatim."""
    raw, _segments = _build_html(b"P" * framing)
    return EmlContainer(memory_bytes(raw))


def attach_twin(framing: int = 0) -> EmlContainer:
    raw, _segments = _build_attach(b"P" * framing)
    return EmlContainer(memory_bytes(raw))


def html_rows_segments(framing: int = 0) -> dict[str, tuple[int, int]]:
    """The labelled segment map of the html construction (a test reads offsets from here)."""
    return _build_html(b"P" * framing)[1]


def attach_rows_segments(framing: int = 0) -> dict[str, tuple[int, int]]:
    """The labelled segment map of the multipart construction."""
    return _build_attach(b"P" * framing)[1]


def persisted_rows(container: FakeMsgContainer) -> tuple[PersistedSpanRow, ...]:
    """The source-only projection of a fake's span table (the store's form, point 7)."""
    return tuple(PersistedSpanRow.of(row) for row in container.span_provenance)
