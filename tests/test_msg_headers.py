"""Turn 1b.5: the headers of a projected ``.msg`` come from the ``0x007D`` transport stream.

The projection's own structural header lines (``MIME-Version``, ``Content-Type``,
``Content-Transfer-Encoding``) are **scaffolding, not evidence** (D2, C6): the walker reads
them for the part's media type and charset, but they never appear in ``headers``. The
``HeaderField`` records are the fields of the ``0x007D`` text, in stream order, each with
its own ``ContainerStreamRef`` into the UTF-16 stream.

The four declared tests are:

* ``test_headers_come_from_the_007d_stream_in_order``;
* ``test_the_utf8_codec_carries_the_real_header_text`` -- the projection's ``value_codec``
  seam, over non-ASCII text built from ``tests/support/mapi_table``;
* ``test_no_transport_headers_yields_no_synthesized_headers`` -- D3/O6;
* ``test_the_transport_header_is_canonical_and_the_property_is_kept`` -- D8;

plus the class-outcome check (D7) as an extra.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb, mapi  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.model import ContainerStreamAxis, Status  # noqa: E402
from emailextract.msgcontainer import (  # noqa: E402
    GAP_MAPI_HEADER_PROPERTY_DISAGREE,
    GAP_TRANSPORT_HEADERS_ABSENT,
    ContainerGap,
    MsgContainer,
)
from emailextract.parse import Limits  # noqa: E402
from support import mapi_table  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()

_CLASS = "IPM.Note"
_CLASS_BYTES = _CLASS.encode("utf-16-le")


def _tool_msg(*, transport: str | None, subject: str | None = None, html: bytes | None = None) -> bytes:
    """A small ``IPM.Note`` ``.msg`` built here, byte for byte (no committed fixture needed)."""
    entries = [
        mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE, len(_CLASS_BYTES))
    ]
    if subject is not None:
        entries.append(
            mapi_table.variable_entry(
                mapi_table.PROP_SUBJECT, mapi_table.PT_UNICODE, len(subject.encode("utf-16-le"))
            )
        )
    children = [
        stream("__properties_version1.0", mapi_table.message_table(entries)),
        stream("__substg1.0_001A001F", _CLASS_BYTES),
    ]
    if subject is not None:
        children.append(stream("__substg1.0_0037001F", subject.encode("utf-16-le")))
    if transport is not None:
        children.append(stream("__substg1.0_007D001F", transport.encode("utf-16-le")))
    if html is not None:
        children.append(stream("__substg1.0_10130102", html))
    return build_cfb(storage("Root Entry", *children))


def _fixture(name: str) -> MsgContainer:
    return MsgContainer((MSG / f"{name}.msg").read_bytes())


# --------------------------------------------------- the declared tests


def test_headers_come_from_the_007d_stream_in_order() -> None:
    """``headers`` is the ``0x007D`` text's fields, in stream order, each with its own ref."""
    container = _fixture("msg_html_only_no_plain")
    document = assemble(container, limits=LIMITS)
    names = [field.name for field in document.headers]
    assert names == ["Subject", "From", "Date"]
    # The projection's own structural lines are scaffolding: never in ``headers`` (C6, D2).
    assert "MIME-Version" not in names
    assert "Content-Transfer-Encoding" not in names
    assert all("Content-Type" != name for name in names)
    offsets = []
    for field in document.headers:
        assert field.stream_ref is not None
        assert field.stream_ref.axis is ContainerStreamAxis.REENCODED
        assert field.stream_ref.stream == "__substg1.0_007D001F"
        offsets.append(field.stream_ref.byte_offset)
    assert offsets == sorted(offsets) and len(set(offsets)) == len(offsets)
    assert document.headers[0].raw_value == " turn 1b.5 synthetic"
    # Every recorded header value is UTF-8 encodable (the projection is UTF-8 by construction).
    for field in document.headers:
        assert field.raw_value.encode("utf-8") is not None


def test_the_utf8_codec_carries_the_real_header_text() -> None:
    """Non-ASCII header text reaches ``raw_value`` as itself, not as latin-1 mojibake."""
    transport = "Subject: Caf\u00e9 Z\u00fcrich\r\nX-Note: na\u00efve fa\u00e7ade\r\n\r\n"
    container = MsgContainer(_tool_msg(transport=transport, html=b"<html><body>x</body></html>"))
    document = assemble(container, limits=LIMITS)
    values = {field.name: field.raw_value for field in document.headers}
    assert values["Subject"] == " Caf\u00e9 Z\u00fcrich"
    assert values["X-Note"] == " na\u00efve fa\u00e7ade"
    assert values["Subject"].encode("utf-8") == " Caf\u00e9 Z\u00fcrich".encode("utf-8")
    # The negative case: the latin-1 default would have produced mojibake for the same bytes.
    assert "Caf\u00e9 Z\u00fcrich" != "Caf\u00e9 Z\u00fcrich".encode("utf-8").decode("latin-1")
    # The projection declares its own codec, and the assembler is what reads it.
    assert container.value_codec == "utf-8"


def test_no_transport_headers_yields_no_synthesized_headers() -> None:
    """D3/O6: no ``0x007D`` gives ``headers == []`` and one document-level gap."""
    container = _fixture("msg_no_transport_headers")
    document = assemble(container, limits=LIMITS)
    assert document.headers == []
    # Not an absence of scaffolding: the virtual bytes still carry the structural lines.
    assert b"MIME-Version: 1.0\r\n" in container.raw_bytes()
    assert b"Content-Type: text/html" in container.raw_bytes()
    assert container.container_facts()["has_transport_headers"] == "false"
    gaps = [gap.gap_id for gap in container.container_gaps]
    assert gaps.count(GAP_TRANSPORT_HEADERS_ABSENT) == 1
    # The part still carries its media type from the projection's own structural line.
    assert [part.content_type for part in document.parts][:1] == ["text/html"]


def test_the_transport_header_is_canonical_and_the_property_is_kept() -> None:
    """D8: the ``0x007D`` ``Subject`` is canonical; the disagreeing property is recorded."""
    container = _fixture("msg_property_vs_header_conflict")
    document = assemble(container, limits=LIMITS)
    values = {field.name: field.raw_value for field in document.headers}
    assert values["Subject"] == " turn 1b.5 synthetic"  # the transport header wins
    gaps = {gap.gap_id: gap.detail for gap in container.container_gaps}
    assert GAP_MAPI_HEADER_PROPERTY_DISAGREE in gaps
    assert gaps[GAP_MAPI_HEADER_PROPERTY_DISAGREE] == "synthetic turn 1b.5 property subject"
    # No fact is invented for the property (it is 1b.6's): the fact key list is unchanged.
    assert "subject" not in container.container_facts()
    # A message whose property agrees carries no gap.
    agreeing = MsgContainer(_tool_msg(transport="Subject: same\r\n\r\n", subject="same"))
    assert GAP_MAPI_HEADER_PROPERTY_DISAGREE not in {
        gap.gap_id for gap in agreeing.container_gaps
    }


# --------------------------------------------------- the extra


def test_msg_non_ipm_note_and_msg_signed_class_through_the_container() -> None:
    """D7: a non-``IPM.Note`` class is UNSUPPORTED, class verbatim, nothing past it read."""
    for name, expected_class in (
        ("msg_non_ipm_note", "IPM.Appointment"),
        ("msg_signed_class", "IPM.Note.SMIME.MultipartSigned"),
    ):
        data = (MSG / f"{name}.msg").read_bytes()
        container = MsgContainer(data)
        document = assemble(container, limits=LIMITS)
        assert document.status.status is Status.UNSUPPORTED
        assert container.container_facts()["message_class"] == expected_class
        assert container.container_facts()["body_streams"] == "none"
        assert container.raw_bytes() == b""  # nothing past the class is projected
        # The gate's own registered gap, with the class verbatim as its detail
        # (``phase0-gaps.md``: the signed fixture is this same gap's second case).
        assert container.container_gaps == (
            ContainerGap(mapi.MSG_CLASS_NOT_IPM_NOTE, expected_class),
        )
        # The gate's own account: the reader stopped before recipients and properties.
        opened = cfb.open_cfb(data)
        assert isinstance(opened, cfb.CfbFile)
        message = mapi.read_message(opened)
        assert message.stopped is True
        assert message.recipients == () and message.properties == ()
