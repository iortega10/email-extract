"""Turn 1b.7: a ``.msg`` attachment becomes an ``AttachmentOccurrence`` through the attach stage.

The container projects each ``__attach_version1.0_#XXXXXXXX`` storage as a MIME leaf of the
virtual multipart/mixed (D1): a by-value attachment's bytes are a pass-through ``STREAM`` span,
and the MAPI-side properties become the synthetic part headers ``attach.py`` already reads. The
filename ladder (D3) is long over short over display; a hostile name is **data, never a path**.
Reference methods (2/3/4) and OLE (6) are recorded and dropped (D5); the leaf is a zero-length
synthetic part. The attachment facts live on ``MsgContainer.attachment_facts`` (D6), one record
per directory row, joined to its span row by ``source_stream``.

The six declared tests are ``test_a_by_value_attachment_is_read``,
``test_the_filename_ladder_is_long_over_short_over_display``,
``test_a_hostile_filename_is_never_a_path``, ``test_cid_and_hidden_flags_feed_the_attach_stage``,
``test_reference_methods_are_recorded_and_dropped_unsupported`` and
``test_zero_size_and_the_mini_cutoff_trio``; the extras are the no-attachment byte identity,
the C2/C5 pairs, the span agreement, the filename round trip, the duplicate gaps, the hostile
cases through the container, the no-follow guard, determinism and a seeded fuzz.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
import urllib.request
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb  # noqa: E402
from emailextract.assemble import assemble, resolve_span  # noqa: E402
from emailextract.container import EmlContainer, PersistedSpanRow, memory_bytes  # noqa: E402
from emailextract.ids import sha256_hex, source_part_id  # noqa: E402
from emailextract.container import source_key_of, span_lookup  # noqa: E402
from emailextract.model import Classification, ContainerStreamAxis  # noqa: E402
from emailextract.msgcontainer import (  # noqa: E402
    GAP_ATTACHMENT_METHOD_UNSUPPORTED,
    GAP_STREAM_TRUNCATED,
    AttachmentFact,
    ContainerGap,
    MsgContainer,
)
from emailextract.parse import Limits, parse  # noqa: E402
from emailextract.walk import walk  # noqa: E402
from support import mapi_table, olefile_oracle  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()
PT_UNICODE = mapi_table.PT_UNICODE
PT_BINARY = mapi_table.PT_BINARY
PT_BOOLEAN = mapi_table.PT_BOOLEAN
IPM_NOTE = mapi_table.utf16("IPM.Note")

#: The attachment tags (D7, [MS-OXPROPS]), typed here -- the independent side.
PROP_ATTACH_DATA = 0x3701
PROP_ATTACH_METHOD = 0x3705
PROP_ATTACH_FILENAME_SHORT = 0x3704
PROP_ATTACH_FILENAME_LONG = 0x3707
PROP_ATTACH_FILENAME_DISPLAY = 0x3001
PROP_ATTACH_MIME_TAG = 0x370E
PROP_ATTACH_CONTENT_ID = 0x3712
PROP_ATTACH_FLAGS = 0x3714
PROP_ATTACH_HIDDEN = 0x7FFE
ATT_MHTML_REF = 0x4

#: The by-value data stream and its digest, typed from the generator's description.
BY_VALUE = "__attach_version1.0_#00000000/__substg1.0_37010102"
G_ATTACH_BYTES = b"turn 1b.7 synthetic attachment bytes\r\n"
G_ATTACH_SHA = "21f4757e6806c73e03589d6486a8af3b259e95c395bda263127f948543aa6375"
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: The transport header every Family G fixture carries, hand-typed.
G_TRANSPORT = (
    "Subject: synthetic turn 1b.7 fixture\r\n"
    "From: Ada Lovelace <ada@example.test>\r\n"
    "To: Grace Hopper <grace@example.test>\r\n"
    "Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
    "Message-ID: <turn-1b7-0001@example.test>\r\n"
    "\r\n"
)
G_HTML = b"<html><body><p>synthetic turn 1b.7 body</p></body></html>\r\n"

#: The virtual bytes of every earlier committed fixture with **no** attachment storage, pinned
#: from the pre-Turn-1b.7 tree (D0.3). ``msg_outlook_layout_handbuilt`` is deliberately absent:
#: it is the one fixture that *has* an attachment, so its projection is expected to change.
NO_ATTACHMENT_PINS = {
    "msg_codepage_disagree": "dd7c319d99a334a1f03a55762f0439bf0659a2a3a7c360ffc9a45862528b6209",
    "msg_difat_extended": "d51b6baa676b37e573c6d1a8174fb1db2d61152d637f939b1e4e40c8ebdaacc0",
    "msg_directory_loop": EMPTY_SHA,
    "msg_fat_cycle": "d6c571f95fbd27c4b448a3b543bca58888a480d7704c655956d1f2c2ad3019fa",
    "msg_headers_html": "d51b6baa676b37e573c6d1a8174fb1db2d61152d637f939b1e4e40c8ebdaacc0",
    "msg_headers_only": "232ffea0c8f40632c5eca6cae6c3a255d56e5aa479595136881c5f3ffd848ee2",
    "msg_html_meta_charset_contradicts": "c12b9ce39d0fb3a31d676e6428ef86f9ae32441c1ee7ca5a04a4fdd3058fc00c",
    "msg_html_only_no_plain": "b304c32108ca51e15879052e39ad9994f1dc5a50ccc6a81f410d9ab3e1b68e63",
    "msg_mini_cutoff_boundary": EMPTY_SHA,
    "msg_named_properties": "dd7c319d99a334a1f03a55762f0439bf0659a2a3a7c360ffc9a45862528b6209",
    "msg_no_transport_headers": "25921d868de8efeb1317ec6e1222505b7814cd110025d22755f4b289acc04177",
    "msg_non_ipm_note": EMPTY_SHA,
    "msg_plain_and_html": "61d37abefbd357288848ed260b8cd603c06e6093efbee33b12ecd4546a6490d8",
    "msg_plain_only": "e459119cb0c3274ed286af8994f7e1f54e593fdeab0dafa9e6787f3ccea38173",
    "msg_property_vs_header_conflict": "b304c32108ca51e15879052e39ad9994f1dc5a50ccc6a81f410d9ab3e1b68e63",
    "msg_recipients_bcc_duplicates": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_recipients_display_only": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_recipients_ex_no_smtp": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_signed_class": EMPTY_SHA,
    "msg_time_property_vs_date_header": "5bf53d199b894acefa53987b0a9671455b240a2c829391d52e1b2b0378a71de7",
    "msg_transport_headers_lf_only": "82638c1e425f463539bbb583ea9f1f7a9a7869b196864b57b910a20fcf3d4b6a",
    "msg_transport_headers_utf8_bom": "a4b331bac0c2649db13d2af22f7fad8c63d5d485db31305d412dafec36994560",
    "msg_truncated_stream": "d6c571f95fbd27c4b448a3b543bca58888a480d7704c655956d1f2c2ad3019fa",
    "msg_unicode_subject": "4c81fdd3b92478f19824f9944f1d12c0e8c1b1c6f474dce6dc54d3d399c6df22",
    "msg_unknown_tags": "dd7c319d99a334a1f03a55762f0439bf0659a2a3a7c360ffc9a45862528b6209",
    "msg_v4_sectors": "d51b6baa676b37e573c6d1a8174fb1db2d61152d637f939b1e4e40c8ebdaacc0",
    "msg_zero_length_body": "44952f8f996b24ee74dd48b837520fcb2c216241c90a6afb76f9bfc97a0e4c1d",
}


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str, **kwargs: object) -> MsgContainer:
    return MsgContainer(_bytes(name), **kwargs)  # type: ignore[arg-type]


def _open(name: str) -> cfb.CfbFile:
    opened = cfb.open_cfb(_bytes(name))
    assert isinstance(opened, cfb.CfbFile)
    return opened


def _filler(size: int, seed: int) -> bytes:
    """The generator's deterministic filler, typed from its description (never read back)."""
    return bytes((seed + index) % 251 for index in range(size))


def _attachment(
    index: int,
    *,
    method: int,
    long: str | None = None,
    short: str | None = None,
    display: str | None = None,
    mime: str | None = None,
    cid: str | None = None,
    hidden: bool | None = None,
    flags: int | None = None,
    data: bytes | None = None,
    declared_data: int | None = None,
    children: tuple = (),
):
    """One ``__attach_version1.0_#XXXXXXXX`` storage, built from [MS-OXPROPS] (test side)."""
    entries = [mapi_table.long_entry(PROP_ATTACH_METHOD, method)]
    kids = list(children)

    def add_text(tag: int, value: str | None) -> None:
        if value is None:
            return
        payload = value.encode("utf-16-le")
        entries.append(mapi_table.variable_entry(tag, PT_UNICODE, len(payload)))
        kids.append(stream(mapi_table.substg_name(tag, PT_UNICODE), payload))

    add_text(PROP_ATTACH_FILENAME_LONG, long)
    add_text(PROP_ATTACH_FILENAME_SHORT, short)
    add_text(PROP_ATTACH_FILENAME_DISPLAY, display)
    add_text(PROP_ATTACH_MIME_TAG, mime)
    add_text(PROP_ATTACH_CONTENT_ID, cid)
    if hidden is not None:
        entries.append(
            mapi_table.fixed_entry(PROP_ATTACH_HIDDEN, PT_BOOLEAN, struct.pack("<H", 1 if hidden else 0))
        )
    if flags is not None:
        entries.append(mapi_table.long_entry(PROP_ATTACH_FLAGS, flags))
    if declared_data is not None:
        entries.append(mapi_table.variable_entry(PROP_ATTACH_DATA, PT_BINARY, declared_data))
    elif data is not None:
        entries.append(mapi_table.variable_entry(PROP_ATTACH_DATA, PT_BINARY, len(data)))
        kids.append(stream("__substg1.0_37010102", data))
    return storage(
        f"__attach_version1.0_#{index:08X}",
        stream("__properties_version1.0", mapi_table.sub_table(entries)),
        *kids,
    )


def _message(*attachments, html: bytes = G_HTML, transport: str = G_TRANSPORT) -> bytes:
    """A hand-built ``IPM.Note`` with the Family G transport header, body and attachments."""
    class_bytes = IPM_NOTE
    table = mapi_table.message_table(
        [mapi_table.variable_entry(0x001A, PT_UNICODE, len(class_bytes))],
        attachments=len(attachments),
        codepages=(1252, 1252),
    )
    children = [
        stream("__properties_version1.0", table),
        stream(mapi_table.substg_name(0x001A, PT_UNICODE), class_bytes),
        stream("__substg1.0_007D001F", transport.encode("utf-16-le")),
    ]
    if html is not None:
        children.append(stream("__substg1.0_10130102", html))
    children.extend(attachments)
    return build_cfb(storage("Root Entry", *children))


def _watch(monkeypatch) -> list[str]:
    """Patch every filesystem/network/subprocess entry point; return the calls made."""
    calls: list[str] = []

    def trap(*args, **kwargs):
        calls.append(repr(args[:1]) + repr(kwargs)[:40])
        raise AssertionError("a path/network call was made")

    for name in (
        "stat",
        "lstat",
        "open",
        "listdir",
        "scandir",
        "mkdir",
        "remove",
        "unlink",
        "rename",
    ):
        monkeypatch.setattr(os, name, trap)
    monkeypatch.setattr(Path, "open", trap)
    monkeypatch.setattr(Path, "read_bytes", trap)
    monkeypatch.setattr(urllib.request, "urlopen", trap)
    monkeypatch.setattr(socket, "socket", trap)
    monkeypatch.setattr(subprocess, "run", trap)
    monkeypatch.setattr(subprocess, "Popen", trap)
    return calls


# ------------------------------------------------------------ the declared tests


def test_a_by_value_attachment_is_read() -> None:
    """D2: the leaf is the stream's own bytes -- pass-through, a ``STREAM`` row, never ``exact``."""
    container = _container("msg_attachment_with_cid")
    (fact,) = container.attachment_facts
    payload, status = cfb.read_stream(_open("msg_attachment_with_cid"), BY_VALUE)
    assert status == cfb.FAULT_OK
    assert payload == G_ATTACH_BYTES
    assert fact == AttachmentFact(
        index=0,
        method=1,
        filename_raw="report.pdf",
        filename_source="long",
        mime_tag="application/pdf",
        cid="cid1@example.test",
        hidden=False,
        inline=False,
        size=38,
        sha256=G_ATTACH_SHA,
        embedded_summary=None,
        storage_tree_sha256=None,
        fault=None,
        source_stream=BY_VALUE,
    )
    assert container.container_facts()["attachment_count"] == "1"

    document = assemble(container, limits=LIMITS)
    leaf = next(part for part in document.parts if part.role == "attachment")
    assert (leaf.size_bytes, leaf.sha256) == (38, G_ATTACH_SHA)
    assert leaf.stream_ref is not None
    assert (leaf.stream_ref.stream, leaf.stream_ref.byte_offset, leaf.stream_ref.byte_len) == (
        BY_VALUE,
        0,
        38,
    )
    assert leaf.stream_ref.axis is ContainerStreamAxis.STREAM
    (occurrence,) = document.attachments
    assert (occurrence.size_bytes, occurrence.sha256) == (38, G_ATTACH_SHA)
    assert occurrence.filename_raw == "report.pdf"
    assert occurrence.filename_decoded.value == "report.pdf"
    assert occurrence.cid == "<cid1@example.test>"
    assert occurrence.classification is Classification.ATTACHMENT
    # ``embedded`` is non-``None`` only for method 5 (the 1b.1 field's invariant).
    assert occurrence.embedded is None

    # The span row is a whole-stream pass-through: offset 0, the stream's digest, exact.
    row = next(r for r in container.span_provenance if r.source_stream == BY_VALUE)
    assert row.axis is ContainerStreamAxis.STREAM
    assert (row.source_byte_offset, row.source_byte_len) == (0, 38)
    assert row.source_sha256 == G_ATTACH_SHA and row.exact is True

    # The leaf's synthetic headers are what the attach stage reads.
    raw = container.raw_bytes()
    assert b'Content-Type: application/pdf\r\n' in raw
    assert b'Content-Disposition: attachment; filename="report.pdf"\r\n' in raw
    assert b"Content-ID: <cid1@example.test>\r\n" in raw
    assert b"Content-Transfer-Encoding: binary\r\n" in raw
    assert G_ATTACH_BYTES in raw


def test_the_filename_ladder_is_long_over_short_over_display() -> None:
    """D3: long over short over display; the first present, non-empty rung wins."""
    cases = (
        (dict(long="L.txt", short="S.txt", display="D.txt"), ("L.txt", "long")),
        (dict(short="S.txt", display="D.txt"), ("S.txt", "short")),
        (dict(display="D.txt"), ("D.txt", "display")),
        (dict(), (None, "none")),
        # An empty long name falls through to the short one.
        (dict(long="", short="S.txt"), ("S.txt", "short")),
    )
    for kwargs, expected in cases:
        data = _message(_attachment(0, method=1, data=b"x", **kwargs))
        (fact,) = MsgContainer(data).attachment_facts
        assert (fact.filename_raw, fact.filename_source) == expected, kwargs
    # The committed fixtures all carry a long name.
    for name in ("msg_attachment_with_cid", "msg_duplicate_filenames"):
        assert all(
            fact.filename_source == "long" for fact in _container(name).attachment_facts
        ), name


def test_a_hostile_filename_is_never_a_path(monkeypatch) -> None:
    """D3: a hostile name is data; no ``Path``/``open``/``os``/network call touches it."""
    data = _bytes("msg_attachment_hostile_name")  # read before the guard is armed
    calls = _watch(monkeypatch)
    container = MsgContainer(data)
    document = assemble(container, limits=LIMITS)
    assert calls == [], calls
    (fact,) = container.attachment_facts
    # The stored text is kept verbatim -- never sanitised, never repaired.
    assert fact.filename_raw == "..\\evil/../../x\x00y"
    (occurrence,) = document.attachments
    assert occurrence.filename_decoded.value == "..\\evil/../../x\x00y"
    assert occurrence.size_bytes == 7 and occurrence.sha256 == sha256_hex(b"hostile")


def test_cid_and_hidden_flags_feed_the_attach_stage() -> None:
    """D2: the cid reaches the attach stage; ``hidden`` has no MIME equivalent (reported)."""
    cid = _container("msg_attachment_with_cid")
    (fact,) = cid.attachment_facts
    assert fact.cid == "cid1@example.test"
    (occurrence,) = assemble(cid, limits=LIMITS).attachments
    # The attach stage normalises the cid, with the angle brackets the header carries.
    assert occurrence.cid == "<cid1@example.test>"

    hidden = _container("msg_attachment_hidden")
    (hidden_fact,) = hidden.attachment_facts
    assert hidden_fact.hidden is True
    assert hidden_fact.inline is True  # 0x3714's ATT_MHTML_REF bit
    (hidden_occurrence,) = assemble(hidden, limits=LIMITS).attachments
    # What actually reaches the attach stage: the inline disposition, not ``hidden``.
    assert hidden_occurrence.classification is Classification.INLINE
    # No field of the occurrence carries ``hidden`` and the leaf header invents none (D2).
    assert not any("hidden" in field.name for field in dataclasses.fields(hidden_occurrence))
    block = hidden.raw_bytes()
    assert b"Content-Disposition: inline; filename=\"inline-image.png\"\r\n" in block
    assert b"hidden" not in block.lower()


def test_reference_methods_are_recorded_and_dropped_unsupported() -> None:
    """D5: methods 2/3/4 are recorded (method, ladder, no bytes) and the gap is emitted."""
    container = _container("msg_attachment_by_reference")
    facts = container.attachment_facts
    assert [fact.method for fact in facts] == [2, 3, 4]
    assert [fact.filename_raw for fact in facts] == ["ref-2.txt", "ref-3.txt", "ref-4.txt"]
    assert all(fact.size is None and fact.sha256 is None for fact in facts)
    assert all(fact.mime_tag == "text/plain" for fact in facts)
    assert container.container_gaps == (
        ContainerGap(GAP_ATTACHMENT_METHOD_UNSUPPORTED, "0:2"),
        ContainerGap(GAP_ATTACHMENT_METHOD_UNSUPPORTED, "1:3"),
        ContainerGap(GAP_ATTACHMENT_METHOD_UNSUPPORTED, "2:4"),
    )
    # No path or URL property is read: no ``0x3701`` data stream exists under any storage.
    opened = _open("msg_attachment_by_reference")
    assert not any(
        entry.is_stream and entry.path.endswith("__substg1.0_37010102")
        for entry in opened.entries
    )
    document = assemble(container, limits=LIMITS)
    assert [o.size_bytes for o in document.attachments] == [0, 0, 0]
    assert all(o.sha256 == EMPTY_SHA for o in document.attachments)
    leaf = next(part for part in document.parts if part.role == "attachment")
    assert leaf.size_bytes is None and leaf.sha256 is None
    assert leaf.stream_ref is not None and leaf.stream_ref.axis is ContainerStreamAxis.SYNTHETIC


def test_zero_size_and_the_mini_cutoff_trio() -> None:
    """D2: a zero-length stream reads as empty; the 4095/4096/4097 trio crosses the mini cutoff."""
    zero = _container("msg_attachment_zero_size")
    (zero_fact,) = zero.attachment_facts
    assert (zero_fact.size, zero_fact.sha256) == (0, EMPTY_SHA)
    (zero_occurrence,) = assemble(zero, limits=LIMITS).attachments
    assert zero_occurrence.size_bytes == 0

    trio = _container("msg_attachments_4095_4096_4097")
    facts = trio.attachment_facts
    assert [fact.size for fact in facts] == [4095, 4096, 4097]
    payloads = [_filler(size, seed) for size, seed in ((4095, 1), (4096, 2), (4097, 3))]
    assert [fact.sha256 for fact in facts] == [sha256_hex(payload) for payload in payloads]

    # The independent sides: ``cfb.read_stream`` and the ``olefile`` oracle agree byte for byte,
    # and the cutoff picks the mini stream for 4095 only.
    data = _bytes("msg_attachments_4095_4096_4097")
    opened = _open("msg_attachments_4095_4096_4097")
    sizes = olefile_oracle.stream_sizes(data)
    mini = olefile_oracle.mini_flags(data)
    for fact, payload in zip(facts, payloads):
        stream_path = fact.source_stream
        read, status = cfb.read_stream(opened, stream_path)
        assert status == cfb.FAULT_OK and read == payload
        assert olefile_oracle.stream_bytes(data, stream_path) == payload
        assert sizes[stream_path] == fact.size
        assert mini[stream_path] is (fact.size < 4096)


# -------------------------------------------------------------------- the extras


def test_a_message_without_attachments_projects_as_before() -> None:
    """D0.3/D1: a message with no attachment storage keeps its pre-turn virtual bytes."""
    for name, digest in NO_ATTACHMENT_PINS.items():
        container = _container(name)
        assert hashlib.sha256(container.raw_bytes()).hexdigest() == digest, name
        # ... and it publishes no attachment channel at all.
        assert container.attachment_facts == ()
        assert "attachment_count" not in container.container_facts()
    # The one earlier fixture that *has* an attachment did change -- by design (D1).
    assert _container("msg_outlook_layout_handbuilt").container_facts()["attachment_count"] == "1"


def test_two_framing_lengths_give_identical_part_ids_and_records_with_an_attachment() -> None:
    """C2 with an attachment: a longer synthetic pad leaves every id and record identical."""
    data = _bytes("msg_attachment_with_cid")
    short = MsgContainer(data)
    long = MsgContainer(data, framing=64)
    assert short.raw_bytes() != long.raw_bytes()
    assert short.container_hash() == long.container_hash()
    assert short.attachment_facts == long.attachment_facts

    document_short = assemble(short, limits=LIMITS)
    document_long = assemble(long, limits=LIMITS)
    assert [record.part_id for record in document_short.parts] == [
        record.part_id for record in document_long.parts
    ]
    assert document_short.attachments == document_long.attachments
    for record in document_short.parts:
        assert resolve_span(short, record.part_id, "plain", 0, 1) == resolve_span(
            long, record.part_id, "plain", 0, 1
        )
    # No ``virtual_*`` value reaches a record or the span-keyed id.
    lookup = span_lookup(short)
    assert lookup is not None
    for part in walk(short, limits=LIMITS).parts:
        row = lookup[(part.raw_span.offset, part.raw_span.length)]
        assert part.part_id == source_part_id(
            short.container_hash(), source_key_of(row), row.source_sha256
        ), part.part_id


def test_the_cross_container_pair_differs_only_where_d14_says() -> None:
    """C5 with an attachment: one message shape as ``.msg`` and as ``.eml`` (D14)."""
    container = MsgContainer(_bytes("msg_attachment_with_cid"))
    eml = EmlContainer(memory_bytes(container.raw_bytes()))

    def shape(document):
        return {
            "status": (document.status.status.value, document.status.reason),
            "body": (
                document.content_fingerprint.body_digest,
                document.content_fingerprint.body_digest_view.value,
            ),
            "headers": [(field.name, field.raw_value) for field in document.headers],
            "parts": [
                (
                    part.content_type,
                    part.role,
                    part.size_bytes,
                    part.sha256,
                    part.stream_ref.stream if part.stream_ref else None,
                    part.stream_ref.axis.value if part.stream_ref else None,
                )
                for part in document.parts
            ],
            "occurrences": [
                (
                    occurrence.occurrence_path,
                    occurrence.size_bytes,
                    occurrence.sha256,
                    occurrence.filename_raw,
                    occurrence.filename_decoded.value,
                    occurrence.cid,
                    occurrence.classification.value,
                )
                for occurrence in document.attachments
            ],
        }

    msg_shape = shape(assemble(container, limits=LIMITS))
    eml_shape = shape(assemble(eml, limits=LIMITS))
    differing = {key for key in msg_shape if msg_shape[key] != eml_shape[key]}
    # Hand-typed: the projection-owned header lines and the container-neutral stream refs are
    # the only field-level differences D14 leaves for an attachment's message.
    assert differing == {"headers", "parts"}, differing
    assert msg_shape["occurrences"] == eml_shape["occurrences"]
    assert msg_shape["body"] == eml_shape["body"]
    assert msg_shape["status"] == eml_shape["status"]
    assert container.kind.value == "cfb_msg" and eml.kind.value == "rfc822"
    assert container.container_hash() != eml.container_hash()
    assert container.container_hash() == sha256_hex(_bytes("msg_attachment_with_cid"))


def test_every_attachment_stream_row_agrees_with_the_read_stream() -> None:
    """The span table's attachment rows are the named stream's own digests, recomputed."""
    for name in (
        "msg_attachment_with_cid",
        "msg_attachment_hidden",
        "msg_attachment_zero_size",
        "msg_attachments_4095_4096_4097",
        "msg_duplicate_filenames",
    ):
        container = _container(name)
        opened = _open(name)
        streams = {fact.source_stream for fact in container.attachment_facts}
        rows = [
            row
            for row in container.span_provenance
            if row.source_stream in streams and row.axis is ContainerStreamAxis.STREAM
        ]
        assert len(rows) == len(streams), name
        for row in rows:
            payload, status = cfb.read_stream(opened, row.source_stream)
            assert status == cfb.FAULT_OK
            assert row.source_sha256 == sha256_hex(payload), (name, row.source_stream)
            assert (row.source_byte_offset, row.source_byte_len) == (0, len(payload))
            assert row.exact is True
            persisted = PersistedSpanRow.of(row)
            assert persisted.source_sha256 == row.source_sha256
            assert not any("virtual" in field.name for field in dataclasses.fields(persisted))


def test_the_filename_round_trips_through_the_attach_stage() -> None:
    """D3: the projected header encodes any name so ``attach.py`` recovers it byte for byte."""
    names = (
        "plain.txt",
        "a b c.txt",
        "snowman \u2603.txt",
        "emoji \U0001f600.txt",
        "a/b.txt",
        "..\x00x",
        '"quoted".txt',
        "semi;colon.txt",
        "back\\slash.txt",
        "caf\u00e9.txt",
    )
    for name in names:
        data = _message(_attachment(0, method=1, long=name, mime="text/plain", data=b"x"))
        container = MsgContainer(data)
        (fact,) = container.attachment_facts
        assert fact.filename_raw == name
        (occurrence,) = assemble(container, limits=LIMITS).attachments
        assert occurrence.filename_decoded.value == name, name
        # The decoded name equals the property text: the header carried it faithfully.
        assert occurrence.filename_raw == name or occurrence.filename_decoded.value == name


def test_duplicate_filenames_and_cids_reach_the_existing_gaps() -> None:
    """D2/D5: duplicates reach the attach stage's own gaps; no new id is invented."""
    from emailextract import attach as attach_stage

    def gaps_for(data: bytes):
        result = walk(MsgContainer(data), limits=LIMITS)
        return attach_stage.attachments(
            MsgContainer(data).raw_bytes(),
            result,
            max_depth=LIMITS.max_depth,
            max_elements=LIMITS.max_parts,
            limits=LIMITS,
        ).gaps

    # Two same-named attachments with different bytes: names are not an identity, so no gap.
    duplicate_names = MsgContainer(_bytes("msg_duplicate_filenames"))
    assert [o.filename_decoded.value for o in assemble(duplicate_names, limits=LIMITS).attachments] == [
        "same.txt",
        "same.txt",
    ]
    assert duplicate_names.container_gaps == ()
    assert not [g for g in gaps_for(_bytes("msg_duplicate_filenames")) if "attach." in str(g)]

    # Two byte-identical attachments: one identity, two occurrences -> occurrence_repeated.
    same = _message(
        _attachment(0, method=1, long="twin.txt", mime="text/plain", data=b"identical"),
        _attachment(1, method=1, long="twin.txt", mime="text/plain", data=b"identical"),
    )
    ids = [str(gap) for gap in gaps_for(same)]
    assert any("occurrence_repeated" in one for one in ids), ids

    # Two same-cid attachments: duplicate_content_id.
    cids = _message(
        _attachment(0, method=1, long="a.txt", mime="text/plain", cid="dup@x", data=b"a"),
        _attachment(1, method=1, long="b.txt", mime="text/plain", cid="dup@x", data=b"b"),
    )
    dup = [str(gap) for gap in gaps_for(cids)]
    assert any("duplicate_content_id" in one for one in dup), dup


def test_the_hostile_attachment_cases_go_through_the_container() -> None:
    """D5: a missing/faulted data stream, a zero-size stream and a cap each behave; none raises."""
    # A by-value attachment whose 0x3701 entry has no data stream: ``stream_absent``.
    absent = MsgContainer(_message(_attachment(0, method=1, long="ghost.bin", declared_data=5)))
    (absent_fact,) = absent.attachment_facts
    assert absent_fact.fault == "stream_absent"
    assert absent_fact.size is None and absent_fact.sha256 is None
    assert (
        ContainerGap(GAP_STREAM_TRUNCATED, "attach:0:stream_absent") in absent.container_gaps
    )
    assert assemble(absent, limits=LIMITS).status.status.value == "truncated"

    # A faulted data stream (a declared size beyond its chain): a chain fault in the same gap.
    data = _message(_attachment(0, method=1, long="short.bin", data=b"0123456789"))
    patched = _patch_stream_size(data, BY_VALUE, 4096)
    faulted = MsgContainer(patched)
    (faulted_fact,) = faulted.attachment_facts
    assert faulted_fact.fault == "stream_out_of_range"
    assert (
        ContainerGap(GAP_STREAM_TRUNCATED, "attach:0:stream_out_of_range")
        in faulted.container_gaps
    )

    # A zero-size stream is a valid empty attachment, not a fault.
    assert _container("msg_attachment_zero_size").attachment_facts[0].fault is None

    # A tiny CFB cap is a SKIPPED document with the caller's value, and no attachment facts.
    capped = MsgContainer(_bytes("msg_attachment_with_cid"), cfb_limits=cfb.CfbLimits(max_sector_count=3))
    capped_document = assemble(capped, limits=LIMITS)
    assert capped_document.status.status.value == "skipped"
    assert capped_document.status.reason == "sector_count_cap"
    assert capped.attachment_facts == ()

    # The depth cap: nothing raises and the gap is the registered one.
    depth = _container("msg_embedded_depth_two")
    assert "msg.embedded_depth_cap" in {gap.gap_id for gap in depth.container_gaps}
    assert assemble(depth, limits=LIMITS).status.status.value == "parsed"


def _patch_stream_size(data: bytes, stream_path: str, size: int) -> bytes:
    """A copy of ``data`` with ``stream_path``'s directory-entry declared size replaced."""
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    entry = cfb.lookup_entry(opened.entries, stream_path)
    assert entry is not None
    offset = (
        (opened.header.first_dir_sector + 1) * opened.header.sector_size
        + 128 * entry.index
        + 120
    )
    patched = bytearray(data)
    struct.pack_into("<I", patched, offset, size)
    return bytes(patched)


def test_no_reference_is_followed(monkeypatch) -> None:
    """D5: no path or URL is read for any reference/OLE fixture -- no entry point is called."""
    datas = [
        _bytes(name)
        for name in (
            "msg_attachment_by_reference",
            "msg_attachment_ole",
            "msg_attachment_hostile_name",
        )
    ]
    calls = _watch(monkeypatch)
    # Fixture bytes are read above; from here no entry point may be touched.
    for data in datas:
        assemble(MsgContainer(data), limits=LIMITS)
    assert calls == [], calls


def test_the_attachment_facts_are_deterministic_across_hash_seeds() -> None:
    """The facts, the container facts and the virtual bytes are identical under any hash seed."""
    script = (
        "import hashlib, json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "from emailextract.msgcontainer import MsgContainer\n"
        "msg = Path(sys.argv[1]) / 'fixtures' / 'msg'\n"
        "out = {}\n"
        "for name in ('msg_attachment_with_cid', 'msg_embedded_message', 'msg_attachments_4095_4096_4097'):\n"
        "    c = MsgContainer((msg / (name + '.msg')).read_bytes())\n"
        "    out[name] = [hashlib.sha256(c.raw_bytes()).hexdigest(),\n"
        "                 sorted(repr(f) for f in c.attachment_facts),\n"
        "                 sorted(c.container_facts().items())]\n"
        "print(json.dumps(out, sort_keys=True))\n"
    )
    baseline = None
    for seed in ("0", "1234567"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        if baseline is None:
            baseline = payload
        else:
            assert payload == baseline, seed


def test_a_seeded_fuzz_of_the_attachment_tables_closes() -> None:
    """Every mutant of an attachment table yields a document or a named refusal; nothing raises."""
    rng = random.Random(20261014)
    produced = 0
    for name in (
        "msg_attachment_with_cid",
        "msg_attachment_zero_size",
        "msg_attachments_4095_4096_4097",
        "msg_duplicate_filenames",
    ):
        data = _bytes(name)
        for _ in range(45):
            mutant = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                mutant[rng.randrange(len(mutant))] = rng.randrange(256)
            mutant = bytes(mutant)
            decision = parse(mutant, limits=LIMITS)
            if decision.error is not None:
                assert decision.error.reason_id, name
                continue
            container = MsgContainer(mutant)
            for fact in container.attachment_facts:
                if fact.filename_raw is not None:
                    fact.filename_raw.encode("utf-8")
                if fact.filename_source not in ("long", "short", "display", "none"):
                    raise AssertionError((name, fact.filename_source))
            document = assemble(container, limits=LIMITS)
            assert document.container_kind.value == "cfb_msg"
            for occurrence in document.attachments:
                if occurrence.filename_decoded.value is not None:
                    occurrence.filename_decoded.value.encode("utf-8")
            produced += 1
    assert produced > 150, produced
