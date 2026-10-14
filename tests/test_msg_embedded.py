"""Turn 1b.7: an embedded message (method 5) -- the summary, the canonical digest, the cap.

An embedded-message attachment is read at **depth 1 only**: its own property table (24-byte
header, D4) yields an :class:`~emailextract.model.EmbeddedSummary` without recursing, and a
canonical walk over its storage yields ``storage_tree_sha256``. A method-5 attachment *inside*
that message is **not** descended: the registered ``msg.embedded_depth_cap`` gap names it and
its row still counts in the embedded message's ``attachment_count`` (D4).

The three declared tests are ``test_an_embedded_message_carries_an_embedded_summary``,
``test_the_storage_tree_sha256_is_a_canonical_walk`` and ``test_beyond_depth_one_is_the_depth_cap``;
the extras are the measured embedded-table header size and the fact that no deeper
``EmbeddedSummary`` descent happens below depth one.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from emailextract import cfb, mapi  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.model import ContainerStreamAxis, EmbeddedSummary  # noqa: E402
from emailextract.msgcontainer import (  # noqa: E402
    EMBEDDED_STORAGE_NAME,
    GAP_EMBEDDED_DEPTH_CAP,
    ContainerGap,
    MsgContainer,
)
from emailextract.parse import Limits  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()

#: The outer attachment's storage and the embedded storage's own path, hand-typed.
OUTER = "__attach_version1.0_#00000000"
EMBEDDED = f"{OUTER}/{EMBEDDED_STORAGE_NAME}"
#: The embedded message of ``msg_embedded_depth_two`` embeds one more, at index 0.
NESTED = f"{EMBEDDED}/__attach_version1.0_#00000000"


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str) -> MsgContainer:
    return MsgContainer(_bytes(name))


def _open(name: str) -> cfb.CfbFile:
    opened = cfb.open_cfb(_bytes(name))
    assert isinstance(opened, cfb.CfbFile)
    return opened


def _canonical_tree(cfb_file: cfb.CfbFile, storage: str) -> str:
    """D4's canonical walk, typed from the brief (a second, independent implementation)."""
    marker = f"{storage}/"
    under = [
        (entry.path[len(marker):], entry)
        for entry in cfb_file.entries
        if entry.path and entry.path.upper().startswith(marker.upper()) and entry.path != marker
    ]
    under.sort(key=lambda pair: pair[0].encode("utf-8"))
    digest = hashlib.sha256()
    for relative, entry in under:
        name = relative.encode("utf-8")
        digest.update(b"T" if entry.is_stream else b"S")
        digest.update(struct.pack(">I", len(name)))
        digest.update(name)
        digest.update(struct.pack(">Q", entry.size if entry.is_stream else 0))
        if entry.is_stream:
            payload, status = cfb.read_stream(cfb_file, entry)
            assert status == cfb.FAULT_OK, relative
            digest.update(payload)
    return digest.hexdigest()


# ------------------------------------------------------------ the declared tests


def test_an_embedded_message_carries_an_embedded_summary() -> None:
    """D4: a method-5 leaf is a zero-length synthetic part with an ``EmbeddedSummary``."""
    container = _container("msg_embedded_message")
    (fact,) = container.attachment_facts
    assert fact.method == 5
    assert fact.filename_raw == "forwarded.msg" and fact.filename_source == "long"
    assert fact.size is None and fact.sha256 is None
    assert fact.embedded_summary == EmbeddedSummary(
        message_class="IPM.Note",
        has_transport_headers=True,
        subject="Fwd: hello",
        recipient_count=1,
        attachment_count=0,
    )
    assert fact.storage_tree_sha256 is not None

    document = assemble(container, limits=LIMITS)
    (occurrence,) = document.attachments
    # The leaf is a synthetic, zero-length body, recorded through the same attach stage.
    assert occurrence.embedded == fact.embedded_summary
    assert occurrence.size_bytes == 0 and occurrence.sha256 == hashlib.sha256(b"").hexdigest()
    leaf = next(part for part in document.parts if part.role == "attachment")
    assert leaf.content_type == "application/octet-stream"
    assert leaf.size_bytes is None and leaf.sha256 is None
    assert leaf.stream_ref is not None
    assert leaf.stream_ref.stream == "synthetic:attachment:1"
    assert leaf.stream_ref.axis is ContainerStreamAxis.SYNTHETIC
    # Nothing in the leaf claims RFC 822 bytes (never ``message/rfc822``).
    assert leaf.content_type != "message/rfc822"
    assert container.container_gaps == ()


def test_the_storage_tree_sha256_is_a_canonical_walk() -> None:
    """D4: the digest is the sha256 of the brief's canonical concatenation, independently built."""
    for name in ("msg_embedded_message", "msg_embedded_depth_two"):
        container = _container(name)
        (fact,) = container.attachment_facts
        expected = _canonical_tree(_open(name), EMBEDDED)
        assert fact.storage_tree_sha256 == expected, name
        # It is never claimed to be a file's hash.
        assert fact.storage_tree_sha256 != hashlib.sha256(_bytes(name)).hexdigest()
    # The two trees differ (the depth-two one nests a second message).
    assert (
        _container("msg_embedded_message").attachment_facts[0].storage_tree_sha256
        != _container("msg_embedded_depth_two").attachment_facts[0].storage_tree_sha256
    )


def test_beyond_depth_one_is_the_depth_cap() -> None:
    """D4: the nested method-5 storage is not descended; the gap names it and the row still counts."""
    container = _container("msg_embedded_depth_two")
    (fact,) = container.attachment_facts
    assert fact.method == 5 and fact.embedded_summary is not None
    # The nested row still counts in the embedded message's own directory-derived attachment_count.
    assert fact.embedded_summary.attachment_count == 1
    assert fact.storage_tree_sha256 is not None
    assert container.container_gaps == (ContainerGap(GAP_EMBEDDED_DEPTH_CAP, "2>0"),)
    # Exactly one EmbeddedSummary exists -- the depth-one one -- and it names no nested message.
    document = assemble(container, limits=LIMITS)
    assert len(document.attachments) == 1
    assert document.attachments[0].embedded == fact.embedded_summary
    assert document.attachments[0].embedded.subject == "inner"


# -------------------------------------------------------------------- the extras


def test_the_embedded_table_header_size_is_the_oxmsg_24() -> None:
    """D4: the embedded table's header is 24 bytes, measured by the entry count, not assumed."""
    opened = _open("msg_embedded_message")
    entry = cfb.lookup_entry(opened.entries, f"{EMBEDDED}/__properties_version1.0")
    assert entry is not None
    data, status = cfb.read_stream(opened, entry)
    assert status == cfb.FAULT_OK
    # The [MS-OXMSG] hypothesis (24) satisfies the modular rule...
    assert (len(data) - mapi.EMBEDDED_HEADER_SIZE) % 16 == 0
    # ... and leaves exactly the two constructed entries (class, subject), no padding entry.
    at_24 = mapi.parse_property_table(data, header_size=24)
    at_8 = mapi.parse_property_table(data, header_size=8)
    assert len(at_24.entries) == 2
    assert {item.tag for item in at_24.entries} == {0x001A, 0x0037}
    # An 8-byte header would inject a spurious ``0000:0000`` entry -- the measured reason 24 wins.
    assert len(at_8.entries) == 3
    assert 0x0000 in {item.tag for item in at_8.entries}

    # The constructed table's stream size, from the independent side (the construction table):
    # 56 bytes = the 24-byte header plus exactly two property entries (class and subject).
    from support import msg_construction

    declared = msg_construction.MSG_EMBEDDED_MESSAGE["streams"][
        f"{EMBEDDED}/__properties_version1.0"
    ]
    assert declared["size"] == len(data) == 56
    assert (declared["size"] - 24) // 16 == 2


def test_no_deeper_embedded_table_is_read(monkeypatch) -> None:
    """The cap stops the summary descent: the embedded-table reader runs once, at depth 1."""
    seen: list[str] = []
    original = mapi._embedded_table

    def counting(cfb_file, storage, **kwargs):
        seen.append(storage)
        return original(cfb_file, storage, **kwargs)

    monkeypatch.setattr(mapi, "_embedded_table", counting)
    container = _container("msg_embedded_depth_two")
    # One call, for the top-level method-5 row: the nested embed is never read into a summary.
    assert seen == [OUTER], seen
    assert container.attachment_facts[0].embedded_summary.subject == "inner"
