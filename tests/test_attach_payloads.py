"""Turn BODY1: ``iter_attachment_payloads`` -- bounded, ordered, refused rather than dropped.

The typed labels are ``tests/support/body_text_labels.py`` (hand-typed from each fixture's
construction before the accessor ran). This file compares against them and asserts what the
brief names:

* the occurrence order and the ``occurrence_ref`` are the **manifest's** own, and a payload's
  size and digest are the occurrence's ``size_bytes``/``sha256`` (the join the hub cites on);
* every occurrence yields exactly one result -- payload or refusal -- so nothing is dropped;
* the per-attachment and total byte ceilings, and the count ceiling, refuse instead of
  returning, and a refused attachment is refused **before** its payload is decoded;
* an attachment that is itself a message is returned as its own bytes and never opened;
* an occurrence the decorative rule skipped is reported, never returned;
* a source that is not a message yields one refusal with the entry point's reason;
* the bounds are validated, and no payload byte reaches a record.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from support import body_text_labels as labels  # noqa: E402

import behavior_ledger  # noqa: E402
from emailextract import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_COUNT,
    AttachmentPayload,
    AttachmentRefusal,
    iter_attachment_payloads,
)
from emailextract.assemble import assemble  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.ids import sha256_hex  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402
from emailextract.model import TriState, record_to_bytes  # noqa: E402
from emailextract.parse import Limits  # noqa: E402

FIXTURES = ROOT / "fixtures"
LIMITS = Limits.untrusted()
LABELLED = sorted(labels.ATTACHMENT_LABELS)
_CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _container(source):
    """The container for one source, decided the way the entry point decides it."""
    data = EmlContainer(source).raw_bytes()
    return MsgContainer(data) if data[:8] == _CFB_MAGIC else EmlContainer(data)


def _results(source, **bounds):
    """The iterator's whole output, as a list (the order is part of the contract)."""
    return list(iter_attachment_payloads(source, **bounds))


def _payloads(results):
    return [item for item in results if isinstance(item, AttachmentPayload)]


def _refusals(results):
    return [item for item in results if isinstance(item, AttachmentRefusal)]


@pytest.mark.parametrize("stem", LABELLED)
def test_each_labelled_fixture_returns_its_typed_payloads(stem: str) -> None:
    """The typed payload list and the typed skip list, in the typed order."""
    label = labels.ATTACHMENT_LABELS[stem]
    results = _results(FIXTURES / str(label["fixture"]))
    got_payloads = [
        (item.occurrence_ref, item.filename, item.media_type, item.size) for item in _payloads(results)
    ]
    got_refusals = [(item.occurrence_ref, item.reason_id) for item in _refusals(results)]
    assert got_payloads == [tuple(row) for row in label["payloads"]]
    assert got_refusals == [tuple(row) for row in label["skipped"]]


def test_the_payload_matches_the_occurrence_the_manifest_carries() -> None:
    """``occurrence_ref``/``size``/digest are the document's own attachment facts."""
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    document = assemble(EmlContainer(path), limits=LIMITS)
    by_path = {occurrence.occurrence_path: occurrence for occurrence in document.attachments}
    results = _results(path)
    assert [item.occurrence_ref for item in results] == [
        occurrence.occurrence_path for occurrence in document.attachments
    ]
    for item in _payloads(results):
        occurrence = by_path[item.occurrence_ref]
        assert item.size == occurrence.size_bytes
        assert sha256_hex(item.data) == occurrence.sha256
        assert occurrence.decode_chain.used_charset is not None or occurrence.sha256 is not None


def test_every_occurrence_of_every_committed_message_yields_one_result() -> None:
    """Over the whole committed corpus: the refs are the manifest's, in its order, one each."""
    names = behavior_ledger.discovered() + behavior_ledger.discovered_messages()
    assert len(names) >= 170, len(names)
    total_occurrences = 0
    refused_messages = 0
    for name in names:
        path = FIXTURES / name
        source = path.read_bytes()
        document = assemble(_container(source), limits=LIMITS)
        expected = [occurrence.occurrence_path for occurrence in document.attachments]
        results = _results(source)
        if len(results) == 1 and results[0].occurrence_ref == "":
            # The message itself was refused (a hostile CFB): one refusal, no occurrence list,
            # and the reason is the one the entry point records -- the body accessor agrees.
            assert isinstance(results[0], AttachmentRefusal), name
            assert expected == [], name
            refused_messages += 1
            continue
        assert [item.occurrence_ref for item in results] == expected, name
        assert len(results) == len(expected), name
        total_occurrences += len(expected)
    assert total_occurrences >= 20, total_occurrences
    assert refused_messages >= 1, "the hostile CFB fixtures must go through the refusal path"


def test_the_count_ceiling_refuses_the_rest_and_names_the_reason() -> None:
    """``max_count`` bounds the payloads; the occurrences left over are refusals, not gaps."""
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    results = _results(path, max_count=1)
    payloads = _payloads(results)
    refusals = _refusals(results)
    assert len(payloads) == 1
    assert len(refusals) == 3
    assert {item.reason_id for item in refusals} == {"part_count_cap"}
    assert [item.occurrence_ref for item in payloads] == ["1.2@0"]
    # ... and the occurrences are still all accounted for.
    assert [item.occurrence_ref for item in results] == ["1.2@0", "1.3@1", "1.4@2", "1.5@3"]
    none = _results(path, max_count=0)
    assert _payloads(none) == []
    assert len(_refusals(none)) == 4


def test_an_attachment_larger_than_the_ceiling_is_refused_not_returned() -> None:
    """``max_bytes`` refuses an oversized attachment, and its budget is the total too.

    With a 600-byte ceiling: ``tiny.pdf`` (583) fits and leaves 17 bytes, so the two
    attachments that are individually over the ceiling are refused ``size_cap`` and the 82-byte
    png, which fits on its own but not in what is left, is refused ``total_size_cap`` -- the two
    ceilings are distinguishable, not one blurred reason.
    """
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    results = _results(path, max_bytes=600)
    payloads = _payloads(results)
    assert [item.filename for item in payloads] == ["tiny.pdf"]
    refusals = _refusals(results)
    assert [item.reason_id for item in refusals] == ["size_cap", "size_cap", "total_size_cap"]
    assert all(item.size <= 600 for item in payloads)


def test_the_total_ceiling_stops_the_iteration_within_the_budget() -> None:
    """The second ``max_bytes`` ceiling: the running total never exceeds it."""
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    results = _results(path, max_bytes=650)
    payloads = _payloads(results)
    assert sum(item.size for item in payloads) <= 650
    assert [item.filename for item in payloads] == ["tiny.pdf"]
    reasons = [item.reason_id for item in _refusals(results)]
    assert reasons == ["size_cap", "size_cap", "total_size_cap"]


def test_a_fifty_attachment_message_stays_within_the_ceiling() -> None:
    """Fifty attachments: every one returns under the default, and the budget still holds.

    The message is hand-built (no committed fixture has fifty parts) so the cost of the
    measurement is the accessor's alone; each part's payload is 4096 bytes, so the default
    ``max_bytes`` covers the lot and a 10 000-byte ceiling covers two.
    """
    message = _many_attachment_message(count=50, size=4096)
    results = _results(memory_bytes(message))
    assert len(results) == 50
    assert all(isinstance(item, AttachmentPayload) for item in results)
    assert sum(item.size for item in results) == 50 * 4096
    assert [item.occurrence_ref for item in results] == [f"1.{index + 2}@{index}" for index in range(50)]
    tight = _results(memory_bytes(message), max_bytes=10_000)
    payloads = _payloads(tight)
    assert len(payloads) == 2
    assert sum(item.size for item in payloads) <= 10_000
    assert len(tight) == 50, "every occurrence is still reported, refused or not"
    assert {item.reason_id for item in _refusals(tight)} == {"total_size_cap"}


def test_a_large_base64_blob_is_refused_without_returning_its_bytes() -> None:
    """A 3 MiB base64 attachment under a 1 KiB ceiling: refused, and nothing decoded is kept."""
    message = _many_attachment_message(count=1, size=3 * 1024 * 1024)
    results = _results(memory_bytes(message), max_bytes=1024)
    assert results and all(isinstance(item, AttachmentRefusal) for item in results)
    assert [item.reason_id for item in results] == ["size_cap"]
    assert not _payloads(results)
    # Under a ceiling that fits it, the same message returns the bytes and their length.
    roomy = _results(memory_bytes(message), max_bytes=4 * 1024 * 1024)
    assert [item.size for item in roomy] == [3 * 1024 * 1024]


def test_an_oversized_message_is_refused_by_the_entry_point_before_any_decode() -> None:
    """A message over ``max_input_bytes`` is one refusal with the entry point's own reason."""
    oversized = memory_bytes(b"Subject: big\r\n\r\n" + b"a" * (64 * 1024 * 1024))
    results = _results(oversized)
    assert len(results) == 1
    assert isinstance(results[0], AttachmentRefusal)
    assert results[0].reason_id == "input_over_cap"
    assert results[0].occurrence_ref == ""


def test_a_nested_message_is_returned_unrecursed() -> None:
    """A ``message/rfc822`` attachment is its own bytes -- never opened, never recursed into."""
    path = FIXTURES / "generated" / "attach_message_rfc822_no_filename.eml"
    payloads = _payloads(_results(path))
    nested = [item for item in payloads if item.media_type == "message/rfc822"]
    assert len(nested) == 1
    data = nested[0].data
    # The payload is the whole nested message, headers included...
    assert data.startswith(b"From: Cara Copy <cara@example.test>\r\n")
    assert b"Nested body line.\r\n" in data
    # ... not the inner body alone, which is what recursing into it would return.
    assert data != b"Nested body line.\r\n"
    assert nested[0].size == len(data) == 163


def test_a_decorative_occurrence_is_skipped_and_reported() -> None:
    """The inline 1x1 unreferenced png is a refusal naming ``attach.cid_unreferenced``."""
    path = FIXTURES / "generated" / "attach_decoration_tracking_pixel.eml"
    results = _results(path)
    assert _payloads(results) == []
    assert len(results) == 1
    refusal = results[0]
    assert isinstance(refusal, AttachmentRefusal)
    assert refusal.reason_id == "attach.cid_unreferenced"
    assert refusal.detail == "inline_unreferenced_tracking_pixel"
    assert refusal.occurrence_ref == "1.2@0"


def test_a_source_that_is_not_a_message_yields_one_refusal() -> None:
    """A non-message is one refusal with the entry point's reason; nothing is silently empty."""
    results = _results(memory_bytes(b"not a message\r\n"))
    assert len(results) == 1
    assert isinstance(results[0], AttachmentRefusal)
    assert results[0].reason_id == "not_a_message"


def test_a_message_with_no_attachment_yields_nothing() -> None:
    """A plain message has no occurrence at all -- an empty iteration, not a refusal."""
    assert _results(FIXTURES / "generated" / "plain_simple.eml") == []


def test_the_bounds_are_validated() -> None:
    """A negative or non-int bound is a caller error, before a byte is read."""
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    for bad in (-1, "3", 1.5, True):
        with pytest.raises(ValueError):
            _results(path, max_count=bad)
        with pytest.raises(ValueError):
            _results(path, max_bytes=bad)


def test_the_defaults_are_documented_numbers() -> None:
    """The two documented defaults are the module's, and both are positive."""
    assert DEFAULT_MAX_COUNT == 50
    assert DEFAULT_MAX_BYTES == 8 * 1024 * 1024
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    assert _results(path) == _results(path, max_count=DEFAULT_MAX_COUNT, max_bytes=DEFAULT_MAX_BYTES)


def test_no_attachment_byte_reaches_a_record() -> None:
    """The document serialized for the same message carries none of the payload bytes."""
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    document = assemble(EmlContainer(path), limits=LIMITS)
    serialized = record_to_bytes(document)
    for item in _payloads(_results(path)):
        assert item.data not in serialized
        assert sha256_hex(item.data).encode("ascii") in serialized, "the digest is what the record keeps"
    # Every occurrence the document carries is decidable: no 'unknown' payload state.
    for occurrence in document.attachments:
        assert occurrence.filename_decoded.state in (TriState.VALUE, TriState.ABSENT, TriState.UNKNOWN)


def _many_attachment_message(*, count: int, size: int) -> bytes:
    """A hand-built ``multipart/mixed`` with ``count`` base64 attachments of ``size`` bytes.

    Deterministic and dependency-free: each payload is a repeated byte pattern, wrapped the way
    ``make_fixtures._attachment_leaf`` wraps one, so the message exercises the base64 decode and
    nothing else.
    """
    import base64

    boundary = "b0-body1-attachments"
    head = (
        b"From: Ada Sender <ada@example.test>\r\n"
        b"To: Ben Receiver <ben@example.test>\r\n"
        b"Subject: body1 many attachments\r\n"
        b"Date: Tue, 4 Mar 2025 08:00:00 +0000\r\n"
        b"Message-ID: <body1-many@example.test>\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="' + boundary.encode("ascii") + b'"\r\n'
        b"\r\n"
    )
    body = b"Hello Ben.\r\n"
    chunks = [
        b"--" + boundary.encode("ascii") + b"\r\n"
        b"Content-Type: text/plain; charset=us-ascii\r\n"
        b"\r\n" + body + b"\r\n"
    ]
    payload = bytes((index % 251 for index in range(size)))
    encoded = base64.b64encode(payload)
    wrapped = b"\r\n".join(
        encoded[index : index + 76] for index in range(0, len(encoded), 76)
    ) + b"\r\n"
    for index in range(count):
        chunks.append(
            b"--" + boundary.encode("ascii") + b"\r\n"
            b"Content-Type: application/octet-stream\r\n"
            b'Content-Disposition: attachment; filename="part-'
            + str(index).encode("ascii")
            + b'.bin"\r\n'
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n" + wrapped + b"\r\n"
        )
    chunks.append(b"--" + boundary.encode("ascii") + b"--")
    return head + b"".join(chunks)
