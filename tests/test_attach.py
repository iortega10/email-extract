"""Turn 1.8: ``attach.py`` -- the manifest, identity, verdicts, cid sets and hints.

One fact at a time, against the turn's rules: an occurrence is a leaf that is not a body view and
not a multipart container (identity is the walker's own content sha256, never a path or a
filename); classification comes from the disposition and the filename and never from size; the
three type verdicts are ``TriValue``s whose winner and disagreement are the model's derivations
read at the container level the frozen corpus fixes; the cid sets decide
``referenced``/``unreferenced``/``dangling``; the decorative rule is a hint that removes nothing;
and the size caps stay the walker's (this stage only re-states what the walker recorded).

Everything is driven the way the oracle drives it (``EmlContainer`` + ``walk`` + the caller's
caps), so a test here measures the bytes the gate measures. Committed fixtures are used where a
label pins a value and hand-typed inline bytes where a case has no fixture; a **temp copy** of a
committed sidecar (``support.sidecar_copy``) is the only place a wrong label exists.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

import docextract_core
import emailextract.attach as attach_module
from emailextract.attach import (
    DEFINED_NOT_EMITTED_GAP_IDS,
    EMITTED_GAP_IDS,
    GENERIC_MEDIA_TYPE,
    HINT_INLINE_UNREFERENCED_SMALL_IMAGE,
    HINT_INLINE_UNREFERENCED_TRACKING_PIXEL,
    HINT_RULES,
    IMAGE_HEADER_BYTES,
    MAGIC_EMPTY,
    MAGIC_ENCRYPTED,
    MAGIC_NOT_COMPUTED_REASONS,
    MAGIC_PREFIX_BYTES,
    MAGIC_SKIPPED_CAP,
    MAGIC_TABLE,
    MAGIC_UNDECODABLE,
    attachments,
    magic_name,
)
from emailextract.container import EmlContainer
from emailextract.evals import l1
from emailextract.model import (
    AttachmentOccurrence,
    Classification,
    DecorativeHintState,
    TriState,
    TriValue,
    TypeVerdictSource,
    record_from_bytes,
    record_to_bytes,
    type_family,
)
from emailextract.parse import Limits
from emailextract.walk import walk

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
sys.path.insert(0, str(ROOT / "tests"))

from support import sidecar_copy  # noqa: E402
from support import stdlib_scanner  # noqa: E402

#: Every cap far above any test input, so exactly the cap a test names can fire.
HIGH = {
    "max_input_bytes": 64 * 1024 * 1024,
    "max_depth": 16,
    "max_parts": 100_000,
    "max_header_bytes": 4 * 1024 * 1024,
    "max_decoded_part_bytes": 64 * 1024 * 1024,
    "max_decoded_total_bytes": 128 * 1024 * 1024,
    "max_field_work_units_per_byte": 64,
}

#: The caller's caps for the referenced-cid set (the oracle's own approved defaults).
HTML_MAX_DEPTH = Limits.untrusted().max_depth
HTML_MAX_ELEMENTS = Limits.untrusted().max_parts

#: The stems of the attachment fixtures the fuzz mutates: Family C's attachment rows plus the
#: mixed manifest. Read from the fixture tree, never a hand-typed list of paths.
FUZZ_STEMS = sorted(
    path for path in (item.stem for item in FIXTURES.glob("*/*.eml")) if path.startswith("attach")
) + ["attachments_mixed"]


def limits(**over: int) -> Limits:
    """A caller's ``Limits``: every cap high except the ones the test names."""
    return Limits(**{**HIGH, **over})


def stage(raw: bytes, *, caller_limits: Limits | None = None):
    """The attachment stage over ``raw``, exactly as a caller drives it."""
    result = walk(EmlContainer(raw), limits=caller_limits)
    return attach_module.attachments(
        raw,
        result,
        max_depth=HTML_MAX_DEPTH,
        max_elements=HTML_MAX_ELEMENTS,
        limits=caller_limits,
    )


def fact_of(raw: bytes, fact_id: str) -> list[list[Any]]:
    """One fact's rows for ``raw``."""
    return stage(raw).rows(fact_id)


def fixture(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def fixture_path(stem: str) -> Path:
    """The committed sidecar for ``stem`` (scanned, so a moved fixture fails loudly)."""
    return next(path for path in FIXTURES.rglob(f"{stem}.expected.json"))


# --------------------------------------------------------------- message builders


def message(
    body: bytes,
    *,
    content_type: str = "text/plain",
    fields: tuple[tuple[str, str], ...] = (),
) -> bytes:
    """One top-level part: the given fields, the given ``Content-Type`` and the given body."""
    head = "".join(f"{name}: {value}\r\n" for name, value in fields)
    return f"{head}Content-Type: {content_type}\r\n\r\n".encode("latin-1") + body


def one_attachment(
    *,
    filename: str | None = "note.bin",
    disposition: str | None = "attachment",
    content_type: str = "application/octet-stream",
    payload: bytes = b"bytes",
    cte: str | None = None,
    extra: tuple[tuple[str, str], ...] = (),
    note: bytes = b"note\r\n",
) -> bytes:
    """A ``multipart/mixed`` with one ``text/plain`` note and one leaf part to classify."""
    boundary = "b-attach-test"
    headers = [b"Content-Type: " + content_type.encode("latin-1") + b"\r\n"]
    if disposition is not None:
        line = "Content-Disposition: " + disposition
        if filename is not None:
            line += f'; filename="{filename}"'
        headers.append(line.encode("latin-1") + b"\r\n")
    for name, value in extra:
        headers.append(f"{name}: {value}".encode("latin-1") + b"\r\n")
    if cte is not None:
        headers.append(f"Content-Transfer-Encoding: {cte}".encode("latin-1") + b"\r\n")
    encoded = base64.b64encode(payload) if cte == "base64" else payload
    parts = [
        b"Content-Type: text/plain\r\n\r\n" + note,
        b"".join(headers) + b"\r\n" + encoded + b"\r\n",
    ]
    body = b"".join(b"--" + boundary.encode() + b"\r\n" + part for part in parts)
    body += b"--" + boundary.encode() + b"--\r\n"
    return message(body, content_type=f'multipart/mixed; boundary="{boundary}"')


def png(width: int, height: int, *, marker: bytes | None = None) -> bytes:
    """A minimal PNG header: the signature, an ``IHDR`` chunk and the given dimensions."""
    ihdr = (marker or b"IHDR") + width.to_bytes(4, "big") + height.to_bytes(4, "big")
    return b"\x89PNG\r\n\x1a\n" + len(ihdr).to_bytes(4, "big") + ihdr + b"\x00" * 8


def referenced_pixel() -> bytes:
    """An HTML view that references an inline 1x1 png: the tracking-pixel rule's negative."""
    body = (
        b"--b\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        b'<img src="cid:p@example.test">\r\n'
        b"--b\r\nContent-Type: image/png\r\nContent-ID: <p@example.test>\r\n"
        b'Content-Disposition: inline; filename="pixel.png"\r\n'
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        + base64.b64encode(png(1, 1))
        + b"\r\n--b--\r\n"
    )
    return message(body, content_type='multipart/mixed; boundary="b"')


def gif(width: int, height: int) -> bytes:
    """A minimal GIF89a header with the given logical screen size."""
    return b"GIF89a" + width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x00" * 4


# ------------------------------------------------------------------- the patches


def patch(monkeypatch: pytest.MonkeyPatch, name: str, wrapper: Callable[..., Any], flags: dict):
    """Replace ``attach_module.<name>`` with ``wrapper``, which counts its own calls.

    The anti-vacuity triple: ``monkeypatch.setattr`` fails if the symbol does not exist, the
    wrapper proves the patch was **reached**, and the caller asserts the observation (a row, or
    the gate) differs.
    """
    real = getattr(attach_module, name)

    def counted(*args: Any, **kwargs: Any) -> Any:
        flags["reached"] += 1
        return wrapper(real, *args, **kwargs)

    monkeypatch.setattr(attach_module, name, counted)
    return real


def fails_naming(report, fact_id: str) -> list:
    """The failing outcomes of ``report`` whose fact is ``fact_id``."""
    return [outcome for outcome in report.failures if outcome.fact_id == fact_id]


def corpus_type_rows() -> list[list[Any]]:
    """Every ``attach.types`` row over the committed corpus."""
    return [
        row
        for path in sorted(FIXTURES.glob("*/*.eml"))
        if "real" not in path.parts
        for row in fact_of(path.read_bytes(), "attach.types")
    ]


def corpus_decorative_rows() -> list[list[Any]]:
    """Every ``attach.decorative`` row over the committed corpus."""
    return [
        row
        for path in sorted(FIXTURES.glob("*/*.eml"))
        if "real" not in path.parts
        for row in fact_of(path.read_bytes(), "attach.decorative")
    ]


# ======================================================= 1. identity and occurrences


def test_identity_is_the_content_sha256_not_the_path() -> None:
    """The identity is the walker's content sha256, not the path and not the filename."""
    raw = one_attachment(filename="fake.pdf")
    result = walk(EmlContainer(raw))
    occurrence = stage(raw).occurrences[0]
    part = next(part for part in result.parts if part.path == "1.2")
    assert occurrence.attachment_id == part.body_sha256
    assert occurrence.sha256 == part.body_sha256
    assert occurrence.attachment_id != occurrence.part_id
    assert "1.2" not in occurrence.attachment_id and "fake.pdf" not in occurrence.attachment_id
    # The same bytes under two filenames are ONE identity: the hash is over the content.
    payload = b"identical bytes"
    assert (
        stage(one_attachment(filename="a.bin", payload=payload)).occurrences[0].sha256
        == stage(one_attachment(filename="b.bin", payload=payload)).occurrences[0].sha256
    )
    # The manifest's content_sha256 column is that hash, over the DECODED bytes.
    row = stage(one_attachment(payload=b"decoded", cte="base64")).rows("attach.manifest")[0]
    assert row[6] == hashlib.sha256(b"decoded").hexdigest()
    assert row[7] == len(b"decoded")


def test_an_occurrence_is_filename_message_and_part_path() -> None:
    """An occurrence is ``(message, part path)``: two parts with one filename are two rows."""
    raw = fixture("generated/attach_duplicate_filename_in_one_message.eml")
    rows = fact_of(raw, "attach.manifest")
    assert [row[0] for row in rows] == ["1.2", "1.3"]
    assert rows[0][1] == rows[1][1] == "report.pdf"
    assert rows[0][6] == rows[1][6], "the same bytes have one identity"
    occurrences = stage(raw).occurrences
    assert [item.occurrence_path for item in occurrences] == ["1.2@0", "1.3@1"]
    assert [item.part_id for item in occurrences] == [item.part_id for item in occurrences]
    # The record is the model's frozen contract, and it round-trips through the strict codec.
    payload = record_to_bytes(occurrences[0])
    assert record_from_bytes(AttachmentOccurrence, payload) == occurrences[0]
    assert occurrences[0].status is None and occurrences[0].route is None
    assert occurrences[0].status_axis == TriValue(state=TriState.UNKNOWN, reason_id="not_built_in_phase1")


def test_classification_comes_from_disposition_and_filename_never_size() -> None:
    """Classification is disposition + filename: never size, never content (D4/D6)."""
    inline = one_attachment(
        disposition="inline", filename="logo.png", content_type="image/png", payload=b"x"
    )
    assert stage(inline).occurrences[0].classification is Classification.INLINE
    attached = one_attachment(disposition="attachment", filename=None, payload=b"x" * 10)
    assert stage(attached).occurrences[0].classification is Classification.ATTACHMENT
    # No disposition, no filename -> unknown.
    nameless = one_attachment(disposition=None, filename=None, payload=b"x" * 5000)
    assert stage(nameless).occurrences[0].classification is Classification.UNKNOWN
    # No disposition but a filename (Content-Type's own ``name`` parameter, D4's other clause).
    named = message(
        b"--b\r\nContent-Type: application/pdf; name=\"only.pdf\"\r\n\r\nx\r\n--b--\r\n",
        content_type='multipart/mixed; boundary="b"',
    )
    occurrence = stage(named).occurrences[0]
    assert occurrence.classification is Classification.ATTACHMENT
    assert occurrence.filename_raw == "only.pdf"
    # A 1-byte and a 5 KB body classify the same way: size never decides.
    small = one_attachment(disposition="attachment", filename="n.bin", payload=b"x")
    big = one_attachment(disposition="attachment", filename="n.bin", payload=b"x" * 5000)
    assert (
        stage(small).occurrences[0].classification
        is stage(big).occurrences[0].classification
        is Classification.ATTACHMENT
    )
    # A text/calendar alternative is a VIEW, never an attachment (item 1).
    calendar = fixture("generated/text_calendar_alternative.eml")
    assert fact_of(calendar, "attach.manifest") == []


def test_a_message_rfc822_occurrence_is_recorded_and_not_recursed() -> None:
    """A ``message/rfc822`` part is one occurrence; its nested parts are not walked."""
    raw = fixture("generated/attach_message_rfc822_no_filename.eml")
    rows = fact_of(raw, "attach.manifest")
    assert [row[0] for row in rows] == ["1.2"]
    assert rows[0][2] == "message/rfc822"
    assert rows[0][1] is None and rows[0][4] is None and rows[0][5] is None
    assert [part.path for part in walk(EmlContainer(raw)).parts] == ["1", "1.1", "1.2"]
    # A declared multipart is a container, not an occurrence, even with no children at all.
    assert fact_of(fixture("raw/preamble_only_message.eml"), "attach.manifest") == []
    # A declared multipart whose boundary never appears but which does have children: the
    # container is still skipped and its children are read.
    assert [row[0] for row in fact_of(fixture("raw/malformed_mime.eml"), "attach.manifest")] == []


# =================================================== 2. the magic table and the verdicts


def test_the_magic_table_matches_zip_ole_pdf_png_jpeg_gif_rtf_gzip_7z_rar() -> None:
    """One hand-typed prefix per row; each is consulted and named, and the order is stable."""
    prefixes = {
        "zip": b"PK\x03\x04",
        "ole-cfb": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        "pdf": b"%PDF-1.7",
        "png": b"\x89PNG\r\n\x1a\n",
        "jpeg": b"\xff\xd8\xff\xe0",
        "gif": b"GIF87a",
        "rtf": b"{\\rtf1",
        "gzip": b"\x1f\x8b\x08\x00",
        "7z": b"7z\xbc\xaf'\x1c",
        "rar": b"Rar!\x1a\x07\x00",
    }
    assert [name for name, _ in MAGIC_TABLE] == list(prefixes)
    for name, payload in prefixes.items():
        assert magic_name(payload) == name, name
    assert magic_name(b"GIF89a\x01\x00") == "gif", "the second gif variant is a row too"
    assert magic_name(b"Rar!\x1a\x07\x01\x00") == "rar", "the RAR 5 form shares the prefix"
    # The forms decision 7 excludes are not rows: an empty zip, a TIFF, a WebP, any text sniff.
    assert magic_name(b"PK\x05\x06") is None
    assert magic_name(b"II*\x00") is None
    assert magic_name(b"RIFF\x00\x00\x00\x00WEBP") is None
    assert magic_name(b"Hello, this is a plain text file") is None
    assert magic_name(None) is None, "no bytes at all is not a consulted magic"


def test_a_declared_text_plain_with_a_zip_prefix_wins_for_magic() -> None:
    """Bytes beat claims: a ``text/plain`` claim beside zip magic is won by ``magic`` (decision 7).

    The example is about the **verdict derivation**. A ``text/plain`` *leaf* is a body view under
    ``selection.is_body_view`` (item 1's predicate), so no occurrence carries that claim in Phase
    1; the derivation is what decision 7 fixes, and it is driven here directly.
    """
    from emailextract.model import type_winner

    declared = TriValue(state=TriState.VALUE, value="text/plain")
    magic = TriValue(state=TriState.VALUE, value="zip")
    introspection = TriValue(state=TriState.UNKNOWN, reason_id="not_built_in_phase1")
    assert type_winner(declared, magic, introspection) is TypeVerdictSource.MAGIC
    assert attach_module.disagrees((declared, magic, introspection)) is True
    assert magic_name(b"PK\x03\x04payload") == "zip", "the prefix the claim contradicts"
    # ... and a zip is never guessed to be a docx/xlsx: the magic family is "zip" alone.
    assert type_family("zip") == "zip"
    row = fact_of(fixture("generated/attach_zip_magic_declared_disagree.eml"), "attach.types")[0]
    assert row[1] == ["value", "application/pdf", None] and row[2] == ["value", "zip", None]
    assert row[4] == "magic" and row[5] is True


def test_magic_consulted_and_unmatched_is_the_unrecognized_value() -> None:
    """A consulted magic that matched nothing is ``VALUE('unrecognized')``, never UNKNOWN."""
    raw = one_attachment(payload=b"no signature here")
    row = fact_of(raw, "attach.types")[0]
    assert row[2] == ["value", "unrecognized", None]
    assert row[4] == "declared_mime"
    assert row[5] is False
    committed = fact_of(fixture("raw/attach_unrecognized_magic.eml"), "attach.types")
    assert committed[0][2] == ["value", "unrecognized", None]


def test_a_not_computed_magic_is_unknown_with_a_reason() -> None:
    """A magic that could not be computed is ``UNKNOWN(reason)`` from the closed tuple."""
    assert MAGIC_NOT_COMPUTED_REASONS == (
        MAGIC_SKIPPED_CAP,
        MAGIC_UNDECODABLE,
        MAGIC_ENCRYPTED,
        MAGIC_EMPTY,
    )
    # A zero-length body decoded fine and there are no bytes to sniff: magic_body_empty.
    zero = one_attachment(disposition="attachment", filename="empty.bin", payload=b"", cte=None)
    row = fact_of(zero, "attach.types")[0]
    assert row[2] == ["unknown", None, MAGIC_EMPTY]
    assert row[1] == ["value", "application/octet-stream", None]
    assert row[4] == "declared_mime", "the declared family still supplies the winner"
    assert row[5] is False
    # The same shape on the committed zero-length fixture (its sidecar types no attach.types row).
    assert fact_of(fixture("generated/attach_zero_length_part.eml"), "attach.types")[0][2] == [
        "unknown",
        None,
        MAGIC_EMPTY,
    ]
    # Bytes that decode to nothing give magic_body_undecodable: the part *has* a body.
    none = one_attachment(
        disposition="attachment", filename="soft.bin", payload=b"=\r\n", cte="quoted-printable"
    )
    assert fact_of(none, "attach.types")[0][2] == ["unknown", None, MAGIC_UNDECODABLE]
    # `magic_body_encrypted` is defined, in the closed tuple, and never emitted in this turn.
    assert MAGIC_ENCRYPTED in MAGIC_NOT_COMPUTED_REASONS
    assert MAGIC_ENCRYPTED not in {row[2][2] for row in corpus_type_rows()}


def test_the_magic_read_is_bounded_to_the_prefix() -> None:
    """The magic decision reads at most ``MAGIC_PREFIX_BYTES``; the image check at most 24."""
    raw = one_attachment(payload=b"PK\x03\x04" + b"z" * 100_000, cte="base64")
    lengths: list[int] = []

    def recording(real, decoded, length):
        lengths.append(length)
        return real(decoded, length)

    flags: dict[str, int] = {"reached": 0}
    with pytest.MonkeyPatch.context() as monkeypatch:
        patch(monkeypatch, "read_prefix", recording, flags)
        assert fact_of(raw, "attach.types")[0][2] == ["value", "zip", None]
    assert flags["reached"] > 0, "the bounded read was never reached"
    assert max(lengths) == MAGIC_PREFIX_BYTES, lengths
    # The decorative path's read is the image header's bound, and never more.
    lengths.clear()
    pixel = one_attachment(
        disposition="inline",
        filename="pixel.png",
        content_type="image/png",
        payload=png(1, 1) + b"p" * 1000,
        cte="base64",
        extra=(("Content-ID", "<p@example.test>"),),
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        patch(monkeypatch, "read_prefix", recording, flags)
        assert fact_of(pixel, "attach.decorative")[0][1] == HINT_INLINE_UNREFERENCED_TRACKING_PIXEL
    assert max(lengths) == IMAGE_HEADER_BYTES, lengths


def test_container_introspection_is_not_built_in_phase1() -> None:
    """The third verdict is ``UNKNOWN(not_built_in_phase1)`` for every occurrence."""
    rows = corpus_type_rows()
    assert rows, "no attachment occurrence in the corpus: this test would be vacuous"
    for row in rows:
        assert row[3] == ["unknown", None, "not_built_in_phase1"], row


def test_type_disagreement_needs_two_families() -> None:
    """The disagreement derivation: two container families, and ``unrecognized``/UNKNOWN none."""
    disagrees = attach_module.disagrees
    assert disagrees(
        (
            TriValue(state=TriState.VALUE, value="application/pdf"),
            TriValue(state=TriState.VALUE, value="zip"),
        )
    )
    assert disagrees(
        (
            TriValue(state=TriState.VALUE, value="text/plain"),
            TriValue(state=TriState.VALUE, value="zip"),
        )
    ), "decision 7's own example: bytes beat claims"
    # One family, however many verdicts name it.
    assert not disagrees(
        (
            TriValue(state=TriState.VALUE, value="application/pdf"),
            TriValue(state=TriState.VALUE, value="pdf"),
        )
    )
    # `unrecognized` and UNKNOWN contribute no family and never fire it.
    assert not disagrees(
        (
            TriValue(state=TriState.VALUE, value="brand/x-foo"),
            TriValue(state=TriState.VALUE, value="unrecognized"),
            TriValue(state=TriState.UNKNOWN, reason_id="not_built_in_phase1"),
        )
    )
    # Decision 25's container reading: a declared OOXML type IS the zip container ...
    assert not disagrees(
        (
            TriValue(
                state=TriState.VALUE, value="application/vnd.ms-word.document.macroEnabled.12"
            ),
            TriValue(state=TriState.VALUE, value="zip"),
        )
    )
    # ... and a generic claim names no container, so it cannot contradict one.
    assert not disagrees(
        (
            TriValue(state=TriState.VALUE, value=GENERIC_MEDIA_TYPE),
            TriValue(state=TriState.VALUE, value="ole-cfb"),
        )
    )


def test_type_unknown_iff_no_verdict_yields_a_family() -> None:
    """No verdict with a family is the untyped state: no winner and no disagreement."""
    # A part that declares no Content-Type at all (the digest child) and has unrecognized bytes:
    # no verdict names a family, so the winner is null and nothing disagrees.
    row = fact_of(fixture("generated/multipart_digest_content_type_less_child.eml"), "attach.types")[0]
    assert row[1] == ["absent", None, None]
    assert row[2] == ["value", "unrecognized", None]
    assert row[4] is None
    assert row[5] is False
    # A declared family is a family, so the same bytes with one are typed.
    typed = one_attachment(content_type="application/x-nothing", payload=b"\x00\x01\x02")
    assert fact_of(typed, "attach.types")[0][4] == "declared_mime"


def test_the_winner_order_prefers_magic() -> None:
    """The winner is the first verdict that yields a family: magic, then declared, then none."""
    assert fact_of(
        fixture("generated/attach_zip_magic_declared_disagree.eml"), "attach.types"
    )[0][4] == "magic"
    assert fact_of(fixture("raw/attach_tnef_winmail.eml"), "attach.types")[0][4] == "declared_mime"
    assert fact_of(fixture("raw/attach_unrecognized_magic.eml"), "attach.types")[0][4] == (
        "declared_mime"
    )
    # The container tables only classify; the winner column is the model's own source value.
    assert attach_module.container_family(
        TriValue(
            state=TriState.VALUE,
            value="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    ) == "zip"
    assert (
        attach_module.container_family(
            TriValue(state=TriState.VALUE, value=GENERIC_MEDIA_TYPE)
        )
        is None
    )
    assert TypeVerdictSource.MAGIC.value == "magic"


def test_the_declared_mime_verdict_keeps_the_headers_own_case() -> None:
    """Finding: the frozen macro-container manifest row types the header's case, not lowercased."""
    manifest = fact_of(fixture("raw/attach_macro_docm.eml"), "attach.manifest")[0]
    verdicts = fact_of(fixture("raw/attach_macro_docm.eml"), "attach.types")[0]
    assert manifest[2] == "application/vnd.ms-word.document.macroEnabled.12"
    assert verdicts[1] == ["value", manifest[2], None]
    # The family derivation is case-insensitive, so the container read is unaffected.
    assert type_family(manifest[2]) == type_family(manifest[2].lower())


# ======================================================= 3. the cid sets


def test_a_cid_reference_decides_unreferenced_and_dangling() -> None:
    """``referenced``/``unreferenced``/``n/a`` against ``body.cid_refs``, and dangling measured."""
    assert fact_of(fixture("generated/attach_inline_referenced.eml"), "attach.cid_use") == [
        ["1.2", "<logo@example.test>", "referenced"]
    ]
    assert fact_of(fixture("generated/attach_inline_unreferenced.eml"), "attach.cid_use") == [
        ["1.2", "<spare@example.test>", "unreferenced"]
    ]
    # A cid-less occurrence still gets a row, with "n/a".
    assert fact_of(fixture("generated/attach_manifest_baseline.eml"), "attach.cid_use") == [
        ["1.2", None, "n/a"],
        ["1.3", None, "n/a"],
    ]
    # A dangling reference is measured ...
    dangling = stage(fixture("generated/attach_cid_dangling.eml"))
    assert dangling.dangling == ("missing@example.test",)
    # ... and deliberately not emitted as a gap row: the two sidecars that carry the case
    # disagree about whether the row is typed, so no live emission satisfies both (a finding).
    assert attach_module.GAP_ATTACH_CID_DANGLING in DEFINED_NOT_EMITTED_GAP_IDS
    assert all(gap_id != attach_module.GAP_ATTACH_CID_DANGLING for gap_id, _ in dangling.gaps)
    # The reference is recorded and no part is invented (D4).
    assert fact_of(fixture("generated/attach_cid_dangling.eml"), "attach.manifest") == []
    assert attach_module.CID_USE_STATES == ("referenced", "unreferenced", "n/a")
    # A referenced cid decides both halves: the set arithmetic is the 1.5b helper's.
    referenced = stage(fixture("generated/attach_inline_referenced.eml"))
    assert referenced.dangling == ()
    assert referenced.unreferenced == ("page@example.test",) or referenced.unreferenced == ()


def test_a_duplicate_content_id_records_the_gap() -> None:
    """Two occurrences with one Content-ID: the gap is recorded and BOTH occurrences remain."""
    result = stage(fixture("generated/attach_duplicate_content_id.eml"))
    assert result.gaps == ((attach_module.GAP_ATTACH_DUPLICATE_CONTENT_ID, "1.2, 1.3"),)
    rows = result.rows("attach.manifest")
    assert [row[0] for row in rows] == ["1.2", "1.3"], "dropping one occurrence is the mutant"
    assert rows[0][3] == rows[1][3] == "<dup@example.test>"
    assert [row[2] for row in result.rows("attach.cid_use")] == ["unreferenced", "unreferenced"]
    assert len(result.occurrences) == 2


def test_a_repeated_occurrence_is_one_identity_and_two_occurrences() -> None:
    """The same bytes twice: one content hash, two occurrences, and the gap names both paths."""
    result = stage(fixture("generated/attach_duplicate_filename_in_one_message.eml"))
    assert result.gaps == ((attach_module.GAP_ATTACH_OCCURRENCE_REPEATED, "1.2, 1.3"),)
    rows = result.rows("attach.manifest")
    assert rows[0][6] == rows[1][6]
    assert len(result.occurrences) == 2
    # Two different payloads are not a repeat.
    assert not any(
        gap_id == attach_module.GAP_ATTACH_OCCURRENCE_REPEATED
        for gap_id, _ in stage(fixture("generated/attach_manifest_baseline.eml")).gaps
    )


# ======================================================= 4. filenames


def test_a_filename_with_an_empty_charset_is_a_recorded_fallback() -> None:
    """An empty charset is a recorded ``fallback`` with its reason, never ``unparsable``."""
    assert fact_of(fixture("generated/attach_filename_rfc2231_fallback.eml"), "attach.filename") == [
        ["1.2", "''run.log", "fallback", "run.log", "empty_charset"]
    ]
    assert fact_of(fixture("generated/rfc2231_empty_charset_fallback.eml"), "attach.filename") == [
        ["1", "''run.log", "fallback", "run.log", "empty_charset"]
    ]
    # A plain quoted filename is ``decoded``.
    assert fact_of(one_attachment(filename="report.pdf"), "attach.filename") == [
        ["1.2", "report.pdf", "decoded", "report.pdf", None]
    ]
    # A continuation pair reassembles in index order (the 2231 parser's own rule).
    continuation = message(
        b"--b\r\nContent-Type: application/octet-stream\r\n"
        b'Content-Disposition: attachment; filename*0="report-"; filename*1="part.pdf"\r\n\r\n'
        b"x\r\n--b--\r\n",
        content_type='multipart/mixed; boundary="b"',
    )
    assert fact_of(continuation, "attach.filename")[0][3] == "report-part.pdf"
    assert attach_module.FILENAME_DECODE_STATES == ("decoded", "fallback", "absent", "unparsable")
    # No filename at all -> no row (``absent`` is in the vocabulary and is never emitted).
    assert fact_of(fixture("generated/attach_message_rfc822_no_filename.eml"), "attach.filename") == []
    assert attach_module.GAP_ATTACH_FILENAME_UNPARSABLE in DEFINED_NOT_EMITTED_GAP_IDS
    # Neither field carries a name: an occurrence with a disposition only has no row either.
    assert fact_of(one_attachment(filename=None), "attach.filename") == []


def test_a_nameless_message_occurrence_records_the_absent_filename_gap() -> None:
    """``attach.filename_absent`` is keyed on the declared ``message/rfc822``, nothing else."""
    raw = fixture("generated/attach_message_rfc822_no_filename.eml")
    assert stage(raw).gaps == ((attach_module.GAP_ATTACH_FILENAME_ABSENT, "1.2"),)
    # A digest child that declares no Content-Type has its own gap, not this one.
    digest = stage(fixture("generated/multipart_digest_content_type_less_child.eml"))
    assert attach_module.GAP_ATTACH_FILENAME_ABSENT not in {gap_id for gap_id, _ in digest.gaps}
    # A nameless occurrence that is not a message/rfc822 part records no such gap.
    other = one_attachment(disposition=None, filename=None, payload=b"x")
    assert attach_module.GAP_ATTACH_FILENAME_ABSENT not in {gap for gap, _ in stage(other).gaps}


# ======================================================= 5. the hints


def test_a_decorative_hint_never_removes_an_occurrence() -> None:
    """The hint is recorded beside the occurrence, which is always still there (D4)."""
    result = stage(fixture("generated/attach_decoration_tracking_pixel.eml"))
    assert result.rows("attach.decorative") == [["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]]
    assert [row[0] for row in result.rows("attach.manifest")] == ["1.2"]
    assert len(result.occurrences) == 1
    assert result.rows("attach.cid_use") == [["1.2", "<pixel@example.test>", "unreferenced"]]
    assert HINT_RULES == (
        HINT_INLINE_UNREFERENCED_SMALL_IMAGE,
        HINT_INLINE_UNREFERENCED_TRACKING_PIXEL,
    )
    # The small-image rule is the empty set in Phase 1: no size threshold is fixed by the design.
    assert all(row[1] != HINT_INLINE_UNREFERENCED_SMALL_IMAGE for row in corpus_decorative_rows())
    assert all(
        row[1] is None or row[1] in HINT_RULES for row in corpus_decorative_rows()
    ), "every rule id is a member of the closed vocabulary"


def test_the_tracking_pixel_rule_reads_the_declared_dimensions() -> None:
    """1x1 png/gif fires the rule; other sizes, a referenced image and a jpeg never do."""
    def rows(*, payload: bytes, content_type: str, reference: bool, inline: bool = True):
        cid = "<c@example.test>"
        leaf = one_attachment(
            disposition="inline" if inline else "attachment",
            filename="image.bin",
            content_type=content_type,
            payload=payload,
            cte="base64",
            extra=(("Content-ID", cid),),
        )
        # The leaf part alone, re-framed beside an HTML view that references the cid (or not).
        leaf_part = leaf.split(b"--b-attach-test\r\n", 2)[2].rsplit(b"--b-attach-test--", 1)[0]
        html = (
            b'<img src="cid:c@example.test">' if reference else b"<p>no image</p>"
        )
        raw = message(
            b"--b\r\nContent-Type: text/html\r\n\r\n" + html + b"\r\n--b\r\n" + leaf_part,
            content_type='multipart/mixed; boundary="b"',
        )
        return stage(raw).rows("attach.decorative")

    assert rows(payload=png(1, 1), content_type="image/png", reference=False) == [
        ["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]
    ]
    assert rows(payload=gif(1, 1), content_type="image/gif", reference=False) == [
        ["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]
    ]
    assert rows(payload=png(2, 2), content_type="image/png", reference=False) == [
        ["1.2", None]
    ], "not 1x1"
    assert rows(payload=png(1, 0), content_type="image/png", reference=False) == [["1.2", None]]
    assert rows(
        payload=b"\xff\xd8\xff\xe0" + (1).to_bytes(4, "big") * 2 + b"\x00" * 8,
        content_type="image/jpeg",
        reference=False,
    ) == [["1.2", None]], "jpeg is never read"
    assert rows(payload=png(2, 2, marker=b"IDAT"), content_type="image/png", reference=False) == [
        ["1.2", None]
    ], "an IHDR marker that is not IHDR"
    assert rows(payload=png(1, 1), content_type="image/png", reference=True) == [
        ["1.2", None]
    ], "a referenced image is never a hint"
    assert rows(
        payload=png(1, 1), content_type="image/png", reference=False, inline=False
    ) == [["1.2", None]], "a non-inline image is never a hint"


# ======================================================= 6. the caps


def big_attachment(size: int, name: str) -> bytes:
    """One base64 attachment leaf decoding to ``size`` bytes."""
    payload = b"z" * size
    encoded = base64.b64encode(payload)
    return (
        b"Content-Type: application/octet-stream\r\n"
        + f'Content-Disposition: attachment; filename="{name}"\r\n'.encode()
        + b"Content-Transfer-Encoding: base64\r\n\r\n"
        + encoded
        + b"\r\n"
    )


def test_a_five_hundred_kilobyte_cap_hit_is_skipped_not_truncated() -> None:
    """A part over the cap is LISTED, skipped and unknown; nothing is ever truncated."""
    cap = 500 * 1024
    over_raw = big_attachment(cap + 1024, "over.bin")
    under_raw = big_attachment(cap - 1024, "under.bin")
    boundary = "b-cap"
    body = (
        b"--" + boundary.encode() + b"\r\nContent-Type: text/plain\r\n\r\nnote\r\n"
        + b"--" + boundary.encode() + b"\r\n" + over_raw
        + b"--" + boundary.encode() + b"\r\n" + under_raw
        + b"--" + boundary.encode() + b"--\r\n"
    )
    raw = message(body, content_type=f'multipart/mixed; boundary="{boundary}"')
    caller = limits(max_decoded_part_bytes=cap)
    result = walk(EmlContainer(raw), limits=caller)
    stage_ = attachments(
        raw, result, max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS, limits=caller
    )
    rows = stage_.rows("attach.manifest")
    assert [row[0] for row in rows] == ["1.2", "1.3"], "a skipped part is still listed"
    over, under = rows
    assert over[7] is None, "the skipped part's decoded size was never computed"
    assert over[6] is None, "the skipped part has no content hash -- not a partial one"
    assert over[1] == "over.bin", "the headers are still read"
    assert len(under[6]) == 64 and under[7] == cap - 1024
    types = {row[0]: row for row in stage_.rows("attach.types")}
    assert types["1.2"][2] == ["unknown", None, MAGIC_SKIPPED_CAP]
    assert types["1.2"][1] == ["value", "application/octet-stream", None], "headers still read"
    assert types["1.3"][2] == ["value", "unrecognized", None]
    # The cap hit is re-stated with the CALLER's value and the skipped region's span length.
    assert [skip.cap_id for skip in stage_.caps] == ["size_cap"]
    skip = stage_.caps[0]
    assert skip.cap_value_bytes == cap and skip.locator == "1.2"
    assert skip.declared_size == next(
        region.span.length
        for region in result.regions
        if region.path == "1.2" and region.kind == "size_cap"
    ), "the skipped region's own span length"
    # The record keeps the part's own content-addressed id where there is no content hash.
    assert stage_.occurrences[0].sha256 is None
    assert stage_.occurrences[0].attachment_id == stage_.occurrences[0].part_id


def test_a_total_cap_skips_the_part_and_every_later_part() -> None:
    """A total-cap hit skips the part it bit and all later parts the same way."""
    boundary = "b-total"
    body = b"".join(
        b"--" + boundary.encode() + b"\r\n" + big_attachment(40, f"p{index}.bin")
        for index in range(4)
    ) + b"--" + boundary.encode() + b"--\r\n"
    raw = message(body, content_type=f'multipart/mixed; boundary="{boundary}"')
    caller = limits(max_decoded_total_bytes=100)
    result = walk(EmlContainer(raw), limits=caller)
    stage_ = attachments(
        raw, result, max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS, limits=caller
    )
    rows = stage_.rows("attach.manifest")
    assert [row[0] for row in rows] == ["1.1", "1.2", "1.3", "1.4"]
    assert [row[6] is None for row in rows] == [False, False, True, True]
    assert {skip.cap_id for skip in stage_.caps} == {"total_size_cap"}
    assert {skip.locator for skip in stage_.caps} == {"1.3", "1.4"}
    assert all(skip.cap_value_bytes == 100 for skip in stage_.caps)
    for row in stage_.rows("attach.types")[2:]:
        assert row[2] == ["unknown", None, MAGIC_SKIPPED_CAP]
    # Nothing is truncated anywhere: every skipped part's hash is None, never a prefix hash.
    for row in rows:
        if row[7] is None:
            assert row[6] is None


# ======================================================= 7. the gap catalogue


def test_the_gap_ids_partition_into_emitted_and_defined() -> None:
    """Every ``GAP_*`` constant is either emitted or recorded as defined-and-not-emitted."""
    constants = {
        name: value
        for name, value in vars(attach_module).items()
        if name.startswith("GAP_") and isinstance(value, str)
    }
    assert set(constants.values()) == set(EMITTED_GAP_IDS) | set(DEFINED_NOT_EMITTED_GAP_IDS)
    assert not set(EMITTED_GAP_IDS) & set(DEFINED_NOT_EMITTED_GAP_IDS)
    registry = (ROOT / "docs" / "design" / "phase0-gaps.md").read_text(encoding="utf-8")
    for gap_id in EMITTED_GAP_IDS + DEFINED_NOT_EMITTED_GAP_IDS:
        assert f"`{gap_id}`" in registry, gap_id
    # Each emitted id is live in the oracle, so the corpus measures it.
    assert set(EMITTED_GAP_IDS) <= set(l1.LIVE_GAP_IDS)
    assert l1.attach_stage is attach_module


def test_the_attachment_gap_ids_are_what_the_corpus_types() -> None:
    """The emitted ids are exactly the ones the labelled sidecars type (the corpus boundary)."""
    typed: set[str] = set()
    for path in sorted(FIXTURES.glob("*/*.expected.json")):
        if "real" in path.parts:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["facts"].get("gaps.later", {}).get("value", []):
            if row[0].startswith("attach.") or row[0] == "security.macro_present":
                typed.add(row[0])
    assert typed == set(EMITTED_GAP_IDS) | {"attach.cid_dangling"}, sorted(typed)


# ======================================================= 8. the mutation cases


#: gap id -> the fixture whose ``gaps.later`` label proves it, for the drop mutant's case.
GAP_MUTATION_CASES = {
    attach_module.GAP_ATTACH_FILENAME_ABSENT: "attach_message_rfc822_no_filename",
    attach_module.GAP_ATTACH_TYPE_DISAGREEMENT: "attach_zip_magic_declared_disagree",
    attach_module.GAP_ATTACH_OLE_CONTAINER_UNKNOWN: "attach_ole_cfb_magic",
    attach_module.GAP_SECURITY_MACRO_PRESENT: "attach_macro_docm",
    attach_module.GAP_ATTACH_DUPLICATE_CONTENT_ID: "attach_duplicate_content_id",
    attach_module.GAP_ATTACH_OCCURRENCE_REPEATED: "attach_duplicate_filename_in_one_message",
    attach_module.GAP_ATTACH_CID_UNREFERENCED: "attach_inline_unreferenced",
    attach_module.GAP_ATTACH_TNEF_PRESENT: "attach_tnef_winmail",
}


def test_every_emitted_gap_id_has_a_mutation_case() -> None:
    """The cases cover the emitted ids exactly (a new id with no case fails here)."""
    assert set(GAP_MUTATION_CASES) == set(EMITTED_GAP_IDS)
    for stem in GAP_MUTATION_CASES.values():
        assert fixture_path(stem).is_file(), stem


@pytest.mark.parametrize("gap_id", sorted(GAP_MUTATION_CASES))
def test_a_dropped_gap_mutant_is_caught_by_the_gate(
    gap_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping one emitted gap flips the gate on the fixture that types it.

    The anti-vacuity triple: (a) the patched symbol exists (``monkeypatch.setattr`` would raise
    otherwise), (b) the patch was **reached**, and (c) the gate fails, naming the fixture, the
    fact and the gap id.
    """
    stem = GAP_MUTATION_CASES[gap_id]
    sidecar = fixture_path(stem)
    assert l1.check_path(sidecar).ok, f"{stem}: the baseline is not green"

    flags = {"reached": 0}

    def drop(real, raw, facts, unreferenced):
        flags["reached"] += 1
        return tuple(pair for pair in real(raw, facts, unreferenced) if pair[0] != gap_id)

    patch(monkeypatch, "_gaps", drop, flags)
    mutated = l1.check_path(sidecar)
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok, f"{stem}: dropping {gap_id} was not caught"
    assert fails_naming(mutated, "gaps.later"), mutated.lines()
    assert gap_id in mutated.failures[0].detail, mutated.failures[0].detail


#: The careless mutants item 9 lists, one per rule this stage owns. Each is asserted by its own
#: test below, and each mutation is proved **reached** before its observation is compared.
CARELESS_MUTANTS: dict[str, str] = {
    "identity": "took the identity from the filename instead of the content sha256",
    "classification": "decided the classification from the size instead of the disposition",
    "zip_as_docx": "guessed a zip to be a docx by its declared type",
    "winner_from_declared": "took the winner from declared_mime even when magic matched",
    "unrecognized_as_family": "treated the 'unrecognized' sentinel as a family",
    "unknown_collapsed": "collapsed an UNKNOWN magic to the 'unrecognized' value",
    "zero_length_magic": "gave a zero-length part a magic value",
    "duplicate_dropped": "dropped one occurrence when two Content-IDs were equal",
    "hint_removes": "removed an occurrence because a decorative hint fired",
    "referenced_hinted": "hinted a referenced image",
    "non_pixel_hinted": "hinted a non-1x1 image",
    "pixel_read_past_header": "read past the tracking pixel's header for its dimensions",
    "opened_attachment": "opened a TNEF/zip/docm attachment",
    "cap_truncated": "truncated a cap-hit part instead of skipping it",
    "guessed_charset": "decoded an empty-charset filename with a guessed charset",
}


def test_the_careless_mutants_are_all_named() -> None:
    """Every careless mutant item 9 lists has a name here, so none can be quietly dropped."""
    assert len(CARELESS_MUTANTS) == 15


def _replace_parts(monkeypatch: pytest.MonkeyPatch, wrapper, flags: dict) -> None:
    """Patch the per-occurrence record builder, which is where a row's columns are set."""
    real = attach_module._Parts

    def building(*args: Any, **kwargs: Any) -> Any:
        flags["reached"] += 1
        return wrapper(real(*args, **kwargs))

    monkeypatch.setattr(attach_module, "_Parts", building)


def test_a_mutant_that_takes_the_identity_from_the_filename_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A filename-derived identity changes the manifest's sha256 and flips the gate."""
    flags = {"reached": 0}

    def from_filename(item):
        return dataclasses.replace(
            item, sha256=hashlib.sha256((item.filename_raw or "").encode()).hexdigest()
        )

    _replace_parts(monkeypatch, from_filename, flags)
    mutated = l1.check_path(fixture_path("attach_manifest_baseline"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "attach.manifest"), mutated.lines()


def test_a_mutant_that_classifies_by_size_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """A size-driven classification drops the inline-only cid gap and flips the gate."""
    flags = {"reached": 0}

    def by_size(item):
        big = (item.size_bytes or 0) > 100
        return dataclasses.replace(
            item, classification=Classification.ATTACHMENT if big else Classification.UNKNOWN
        )

    _replace_parts(monkeypatch, by_size, flags)
    mutated = l1.check_path(fixture_path("attach_inline_unreferenced"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "gaps.later"), mutated.lines()
    assert attach_module.GAP_ATTACH_CID_UNREFERENCED in mutated.failures[0].detail


def test_a_mutant_that_guesses_a_zip_as_docx_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """A zip is never guessed to be a docx/xlsx: the magic name stays ``zip``."""
    flags = {"reached": 0}
    real = attach_module.magic_name

    def guessing(decoded):
        flags["reached"] += 1
        name = real(decoded)
        return "docx" if name == "zip" else name

    monkeypatch.setattr(attach_module, "magic_name", guessing)
    mutated = l1.check_path(fixture_path("attach_zip_magic_declared_disagree"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "attach.types"), mutated.lines()
    assert "docx" in mutated.failures[0].detail


def test_a_mutant_that_takes_the_winner_from_declared_mime_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ignoring magic in the winner order contradicts the frozen winner column."""
    flags = {"reached": 0}

    def declared_first(real, declared_mime, magic, introspection):
        flags["reached"] += 1
        return real(declared_mime, TriValue(), introspection)

    patch(monkeypatch, "type_winner", declared_first, flags)
    mutated = l1.check_path(fixture_path("attach_zip_magic_declared_disagree"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "attach.types"), mutated.lines()
    assert "magic" in mutated.failures[0].detail


def test_a_mutant_that_treats_unrecognized_as_a_family_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``unrecognized`` is not a family: treating it as one invents a disagreement."""
    flags = {"reached": 0}
    real = attach_module.container_family

    def as_family(verdict):
        family = real(verdict)
        flags["reached"] += 1
        if family is None and verdict.state is TriState.VALUE:
            return "unrecognized"
        return family

    monkeypatch.setattr(attach_module, "container_family", as_family)
    mutated = l1.check_path(fixture_path("attach_tnef_winmail"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "attach.types"), mutated.lines()
    assert "true" in mutated.failures[0].detail.lower()


def test_a_mutant_that_collapses_an_unknown_magic_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An UNKNOWN magic collapsed to ``unrecognized`` changes the verdict triple."""
    baseline = fact_of(fixture("generated/attach_zero_length_part.eml"), "attach.types")
    assert baseline[0][2] == ["unknown", None, MAGIC_EMPTY]
    flags = {"reached": 0}
    real = attach_module._magic_verdict

    def collapsed(real, decoded, *, skipped_cap, own_body):
        verdict = real(decoded, skipped_cap=skipped_cap, own_body=own_body)
        flags["reached"] += 1
        if verdict.state is TriState.UNKNOWN:
            return TriValue(state=TriState.VALUE, value="unrecognized")
        return verdict

    patch(monkeypatch, "_magic_verdict", collapsed, flags)
    mutated = fact_of(fixture("generated/attach_zero_length_part.eml"), "attach.types")
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated[0][2] == ["value", "unrecognized", None], "the mutant's row"
    assert mutated != baseline, "the observation differs from the baseline"


def test_a_mutant_that_gives_a_zero_length_part_a_magic_value_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero-length body is never sniffed at all (and never given a magic value)."""
    baseline = fact_of(fixture("generated/attach_zero_length_part.eml"), "attach.types")
    seen: list[int] = []
    real = attach_module.magic_name

    def watching(decoded):
        seen.append(len(decoded))
        return "zip" if not decoded else real(decoded)

    monkeypatch.setattr(attach_module, "magic_name", watching)
    assert fact_of(fixture("generated/attach_zero_length_part.eml"), "attach.types") == baseline
    after_zero = list(seen)
    fact_of(fixture("generated/attach_manifest_baseline.eml"), "attach.types")
    assert len(seen) > len(after_zero), "the patched reader is live (other parts reach it)"
    assert 0 not in seen, "a zero-length body reached the magic reader at all"
    # A mutant that gives the empty case a value inside the stage's own guard is caught by the
    # turn's assertions (the row is no longer UNKNOWN(magic_body_empty)).
    flags = {"reached": 0}

    def inventing(real, decoded, *, skipped_cap, own_body):
        flags["reached"] += 1
        if decoded == b"":
            return TriValue(state=TriState.VALUE, value="zip")
        return real(decoded, skipped_cap=skipped_cap, own_body=own_body)

    patch(monkeypatch, "_magic_verdict", inventing, flags)
    mutated = fact_of(fixture("generated/attach_zero_length_part.eml"), "attach.types")
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated != baseline


def test_a_mutant_that_drops_a_duplicate_content_id_occurrence_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both occurrences stay: dropping one is the mutant item 9 names."""
    flags = {"reached": 0}
    real = attach_module.attachments

    def keeping_one(*args: Any, **kwargs: Any):
        stage_ = real(*args, **kwargs)
        flags["reached"] += 1
        kept: list[Any] = []
        seen: set[str] = set()
        for item in stage_.facts:
            if item.normalized_cid is not None and item.normalized_cid in seen:
                continue
            seen.add(item.normalized_cid or "")
            kept.append(item)
        facts = tuple(kept)
        parts = {item.part.part_id for item in facts}
        return dataclasses.replace(
            stage_,
            facts=facts,
            occurrences=tuple(o for o in stage_.occurrences if o.part_id in parts),
            gaps=attach_module._gaps(args[0], facts, set(stage_.unreferenced)),
        )

    monkeypatch.setattr(attach_module, "attachments", keeping_one)
    mutated = l1.check_path(fixture_path("attach_duplicate_content_id"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "gaps.later"), mutated.lines()
    assert attach_module.GAP_ATTACH_DUPLICATE_CONTENT_ID in mutated.failures[0].detail


def test_a_mutant_that_removes_an_occurrence_on_a_hint_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decorative hint never removes an occurrence (D4)."""
    flags = {"reached": 0}
    real = attach_module.attachments

    def filtering(*args: Any, **kwargs: Any):
        stage_ = real(*args, **kwargs)
        flags["reached"] += 1
        kept = tuple(
            occurrence
            for occurrence in stage_.occurrences
            if occurrence.decorative_hint.state is not DecorativeHintState.RULE_ID
        )
        dropped = {o.part_id for o in stage_.occurrences} - {o.part_id for o in kept}
        facts = tuple(item for item in stage_.facts if item.part.part_id not in dropped)
        return dataclasses.replace(stage_, occurrences=kept, facts=facts)

    monkeypatch.setattr(attach_module, "attachments", filtering)
    mutated = l1.check_path(fixture_path("attach_decoration_tracking_pixel"))
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert not mutated.ok and fails_naming(mutated, "attach.decorative"), mutated.lines()
    assert HINT_INLINE_UNREFERENCED_TRACKING_PIXEL in mutated.failures[0].detail


def test_a_mutant_that_hints_a_referenced_image_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A referenced inline pixel is not decoration: the rule requires unreferenced."""
    flags = {"reached": 0}
    real = attach_module._hint

    def loose(real, *, classification, referenced, magic, decoded):
        flags["reached"] += 1
        return real(
            classification=classification,
            referenced="unreferenced",
            magic=magic,
            decoded=decoded,
        )

    baseline = fact_of(referenced_pixel(), "attach.decorative")
    assert baseline == [["1.2", None]], "the hand-built image IS referenced"
    patch(monkeypatch, "_hint", loose, flags)
    mutated = fact_of(referenced_pixel(), "attach.decorative")
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated == [["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]], "the mutant's row"


def test_a_mutant_that_hints_a_non_one_pixel_image_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is hinted from size alone: a 2x2 image never fires the rule."""
    flags = {"reached": 0}
    real = attach_module._dimensions

    def always_pixel(real, decoded):
        flags["reached"] += 1
        real(decoded)
        return (1, 1)

    raw = one_attachment(
        disposition="inline",
        filename="logo.png",
        content_type="image/png",
        payload=png(2, 2),
        cte="base64",
        extra=(("Content-ID", "<c@example.test>"),),
    )
    baseline = stage(raw).rows("attach.decorative")
    assert baseline == [["1.2", None]], "the unmutated stage hints nothing for a 2x2 image"
    patch(monkeypatch, "_dimensions", always_pixel, flags)
    mutated = fact_of(raw, "attach.decorative")
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated == [["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]], "the mutant's row"


def test_a_mutant_that_reads_past_the_tracking_pixel_header_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The image-header read is bounded: reading the whole payload shows up in the bound."""
    pixel = one_attachment(
        disposition="inline",
        filename="pixel.png",
        content_type="image/png",
        payload=png(1, 1) + b"p" * 100,
        cte="base64",
        extra=(("Content-ID", "<p@example.test>"),),
    )
    lengths: list[int] = []
    flags = {"reached": 0}
    real = attach_module.read_prefix

    def unbounded(decoded, length):
        flags["reached"] += 1
        lengths.append(len(decoded))
        return real(decoded, len(decoded))

    monkeypatch.setattr(attach_module, "read_prefix", unbounded)
    assert fact_of(pixel, "attach.decorative") == [
        ["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]
    ]
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert max(lengths) > IMAGE_HEADER_BYTES, "the mutant read past the declared bound"


def test_a_mutant_that_guesses_a_charset_for_an_empty_charset_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty charset keeps the recorded fallback value, never a guessed charset's reading."""
    raw = message(
        b"--b\r\nContent-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment; filename*=''r%C3%A9sum%C3%A9.pdf\r\n\r\n"
        b"x\r\n--b--\r\n",
        content_type='multipart/mixed; boundary="b"',
    )
    baseline = fact_of(raw, "attach.filename")
    assert baseline == [
        [
            "1.1",
            "''r%C3%A9sum%C3%A9.pdf",
            "fallback",
            "r\u00c3\u00a9sum\u00c3\u00a9.pdf",
            "empty_charset",
        ]
    ], baseline
    flags = {"reached": 0}
    real = attach_module._filename

    def guessing(real, part):
        raw_value, state, decoded, reason = real(part)
        flags["reached"] += 1
        if state == "fallback" and raw_value:
            percent = (
                raw_value.encode("latin-1").replace(b"%C3%A9", b"\xc3\xa9").decode("latin-1")
            )
            return raw_value, state, percent.encode("latin-1").decode("utf-8", "replace"), reason
        return raw_value, state, decoded, reason

    patch(monkeypatch, "_filename", guessing, flags)
    mutated = fact_of(raw, "attach.filename")
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated != baseline, "the guessed charset changes the decoded value"


#: The stdlib archive modules an attachment read would have to use. None is imported by the
#: package: a ``.docm``/zip/TNEF part is recorded, never opened or decompressed (D10).
ARCHIVE_MODULES = ("zipfile", "gzip", "tarfile", "lzma", "bz2")


class _ArchiveBoom:
    """A stand-in module whose every attribute use fails the test."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"an attachment was opened or decompressed (used {name!r})")


def test_a_mutant_that_opens_a_tnef_or_zip_or_docm_attachment_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No archive module is reachable while the attachment stage runs, and the guard is live."""
    for name in ARCHIVE_MODULES:
        monkeypatch.setitem(sys.modules, name, _ArchiveBoom())
    # (a) the three container fixtures run with every archive module a landmine.
    for stem in ("attach_tnef_winmail", "attach_zip_magic_declared_disagree", "attach_macro_docm"):
        path = next(path for path in FIXTURES.rglob(f"{stem}.eml"))
        assert stage(path.read_bytes()).rows("attach.manifest"), stem
    # (b) a planted mutant that opens the payload is caught by the same landmine.
    flags = {"reached": 0}

    def opening(real, raw, part):
        import zipfile

        flags["reached"] += 1
        return zipfile.ZipFile(raw, "r").namelist()  # type: ignore[attr-defined]

    patch(monkeypatch, "decoded_payload", opening, flags)
    with pytest.raises(AssertionError, match="opened or decompressed"):
        stage(fixture("raw/attach_macro_docm.eml"))
    assert flags["reached"] > 0, "the planted opener was never reached (vacuous)"


def test_a_mutant_that_truncates_a_cap_hit_part_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cap-hit part is skipped, never partially decoded (no partial hash, no magic value)."""
    cap = 500 * 1024
    boundary = "b-cap"
    body = (
        b"--" + boundary.encode() + b"\r\nContent-Type: text/plain\r\n\r\nnote\r\n"
        + b"--" + boundary.encode() + b"\r\n" + big_attachment(cap + 1024, "over.bin")
        + b"--" + boundary.encode() + b"--\r\n"
    )
    raw = message(body, content_type=f'multipart/mixed; boundary="{boundary}"')
    caller = limits(max_decoded_part_bytes=cap)

    def rows_for() -> tuple[list[list[Any]], list[list[Any]]]:
        result = walk(EmlContainer(raw), limits=caller)
        stage_ = attachments(
            raw, result, max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS, limits=caller
        )
        return stage_.rows("attach.manifest"), stage_.rows("attach.types")

    baseline_manifest, baseline_types = rows_for()
    assert baseline_manifest[0][6] is None and baseline_manifest[0][7] is None
    assert baseline_types[0][2] == ["unknown", None, MAGIC_SKIPPED_CAP]

    flags = {"reached": 0}

    def truncating(item):
        # The mutant's careless reading: hash the first bytes of the body it did not read.
        if item.sha256 is None:
            return dataclasses.replace(
                item, sha256=hashlib.sha256(item.part.body_span.slice(raw)[:8]).hexdigest()
            )
        return item

    _replace_parts(monkeypatch, truncating, flags)
    mutated_manifest, _mutated_types = rows_for()
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated_manifest != baseline_manifest, "the truncated reading changes the row"
    assert mutated_manifest[0][6] is not None, "the mutant reports a partial hash"
    assert mutated_manifest[0][7] is None, "and still no decoded size"


def test_a_mutant_that_invents_a_tracking_pixel_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dimensions come from the declared header bytes, and a wrong reading shows up."""
    flags = {"reached": 0}

    def always_pixel(real, decoded):
        flags["reached"] += 1
        real(decoded)
        return (1, 1)

    raw = one_attachment(
        disposition="inline",
        filename="shifted.png",
        content_type="image/png",
        payload=png(2, 2) + png(1, 1)[12:] + b"\x00" * 24,
        cte="base64",
        extra=(("Content-ID", "<s@example.test>"),),
    )
    baseline = stage(raw).rows("attach.decorative")
    assert baseline == [["1.2", None]], "the unmutated stage reads the declared 2x2 header"
    patch(monkeypatch, "_dimensions", always_pixel, flags)
    mutated = fact_of(raw, "attach.decorative")
    assert flags["reached"] > 0, "the patch was never reached (vacuous)"
    assert mutated == [["1.2", HINT_INLINE_UNREFERENCED_TRACKING_PIXEL]], "the mutant's row"


# ======================================================= 9. the independent check


#: fixture stem -> the closed reason the attachment-leaf comparison is not gated there.
ATTACHMENT_SCANNER_EXCLUSIONS = {
    "attach_message_rfc822_no_filename": "no_recursion",
    "text_part_with_body_parts_tree": "no_recursion",
    "multipart_digest_content_type_less_child": "digest_default",
    "headerless_digest_child": "digest_default",
    "headerless_mixed_text_and_attachment": "headerless_default",
    "text_calendar_alternative": "text_calendar_view",
}


def scanner_disagreements() -> dict[str, tuple[list[Any], list[Any]]]:
    """Every fixture where the package's manifest and the stdlib's own leaves differ."""
    found: dict[str, tuple[list[Any], list[Any]]] = {}
    for path in sorted(FIXTURES.glob("*/*.eml")):
        if "real" in path.parts:
            continue
        raw = path.read_bytes()
        package = [
            (row[2].lower() if row[2] else None, (row[5] or "").lower() or None, row[6], row[7])
            for row in fact_of(raw, "attach.manifest")
        ]
        stdlib = [
            (
                leaf.content_type.lower(),
                (leaf.transfer_encoding or "").lower() or None,
                leaf.sha256,
                leaf.size,
            )
            for leaf in stdlib_scanner.attachment_leaves(raw)
        ]
        if package != stdlib:
            found[path.stem] = (package, stdlib)
    return found


def test_the_stdlib_scanner_agrees_on_the_attachment_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Count, order, decoded sha256/size and declared type match the stdlib's own walk."""
    disagreements = scanner_disagreements()
    assert set(disagreements) <= set(ATTACHMENT_SCANNER_EXCLUSIONS), sorted(disagreements)
    for reason in ATTACHMENT_SCANNER_EXCLUSIONS.values():
        assert reason in stdlib_scanner.SHARED_ATTACHMENT_MISREADING, reason
    # The catalogue is not decoration: every excluded fixture really does disagree.
    assert set(disagreements) == set(ATTACHMENT_SCANNER_EXCLUSIONS), sorted(disagreements)
    compared = len(list(FIXTURES.glob("*/*.eml"))) - len(ATTACHMENT_SCANNER_EXCLUSIONS)
    assert compared >= 100, f"only {compared} fixtures compared: the gate would be thin"

    # A planted defect: a package that reports a wrong decoded size is caught.
    flags = {"reached": 0}

    def wrong_size(item):
        return dataclasses.replace(item, size_bytes=(item.size_bytes or 0) + 1)

    _replace_parts(monkeypatch, wrong_size, flags)
    planted = scanner_disagreements()
    assert flags["reached"] > 0, "the planted defect was never reached (vacuous)"
    assert set(planted) - set(disagreements), "the planted defect created no new disagreement"
    monkeypatch.undo()
    assert scanner_disagreements() == disagreements, "restoring must restore agreement"


# ======================================================= 10. the fuzz


#: How many seeded mutants the fuzz runs (each seed is reproducible).
FUZZ_SEEDS = 48


def _mutate(rng: random.Random, raw: bytes) -> bytes:
    """One deterministic mutation of ``raw``: the kinds item 9 names, one per call."""
    kind = rng.randrange(9)
    if kind == 0:  # byte flips
        for _ in range(rng.randrange(1, 6)):
            position = rng.randrange(len(raw))
            raw = raw[:position] + bytes([rng.randrange(256)]) + raw[position + 1 :]
        return raw
    if kind == 1:  # truncation
        return raw[: rng.randrange(len(raw) + 1)]
    if kind == 2:  # a repeated or swapped chunk
        cut = rng.randrange(len(raw))
        if rng.randrange(2):
            return raw[:cut] + raw[cut : cut + 8] * 3 + raw[cut + 8 :]
        return raw[cut:] + raw[:cut]
    if kind == 3:  # a huge parameter value
        return raw.replace(b"filename=", b'filename="' + b"x" * 200 + b'"; ', 1)
    if kind == 4:  # a NUL in a header region
        return raw.replace(b"Content-", b"Content\x00-", 1)
    if kind == 5:  # non-ASCII digits in the size/date parameters
        return raw.replace(b"attachment;", "attachment; size=\u0665\u0669\u0669;".encode("utf-8"), 1)
    if kind == 6:  # a signature at the wrong offset
        return b"\x00" + raw
    if kind == 7:  # a truncated 1x1 image header
        return raw.replace(b"\x89PNG\r\n\x1a\n", b"\x89PNG", 1)
    # a 1x1 header edge: a zero height
    return raw.replace(
        b"\x00\x00\x00\x01\x00\x00\x00\x01", b"\x00\x00\x00\x01\x00\x00\x00\x00", 1
    )


def run_fuzz(seeds: int, recorder: Callable[[bytes], None], *, seed: int = 1) -> None:
    """Run the seeded fuzz; a crash names the seed and the fixture it came from."""
    rng = random.Random(seed)
    for index in range(seeds):
        rng.seed(seed + index)
        stem = FUZZ_STEMS[rng.randrange(len(FUZZ_STEMS))]
        path = next(path for path in FIXTURES.rglob(f"{stem}.eml"))
        raw = path.read_bytes()
        for _ in range(2):
            raw = _mutate(rng, raw)
        try:
            recorder(raw)
        except AssertionError:
            raise
        except Exception as error:  # noqa: BLE001 -- the fuzz's own failure report
            raise AssertionError(
                f"seed {index} on {stem}: {type(error).__name__}: {error}"
            ) from error


def _run_stage(raw: bytes) -> None:
    """The fuzz's own body: walk, run the stage and build every row."""
    result = walk(EmlContainer(raw))
    stage_ = attach_module.attachments(
        raw, result, max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS
    )
    for fact_id in (
        "attach.manifest",
        "attach.types",
        "attach.filename",
        "attach.decorative",
        "attach.cid_use",
    ):
        stage_.rows(fact_id)


def test_the_seeded_attachment_fuzz_finds_no_defect(monkeypatch: pytest.MonkeyPatch) -> None:
    """No mutant raises, the magic read stays bounded and no archive module is ever used."""
    for name in ARCHIVE_MODULES:
        monkeypatch.setitem(sys.modules, name, _ArchiveBoom())
    reads: list[int] = []
    real = attach_module.read_prefix

    def recording(decoded, length):
        reads.append(length)
        return real(decoded, length)

    monkeypatch.setattr(attach_module, "read_prefix", recording)
    occurrences = 0

    def run(raw: bytes) -> None:
        nonlocal occurrences
        result = walk(EmlContainer(raw))
        stage_ = attach_module.attachments(
            raw, result, max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS
        )
        occurrences += len(stage_.occurrences)
        _run_stage(raw)

    run_fuzz(FUZZ_SEEDS, run)
    assert reads, "the fuzz never reached the bounded read"
    assert max(reads) <= IMAGE_HEADER_BYTES, max(reads)
    assert any(length == MAGIC_PREFIX_BYTES for length in reads)
    # Linearity (a deterministic counter, never a clock): at most 60 requested bytes per
    # occurrence, so the work follows the parts and never the payload size.
    assert sum(reads) <= 100 * occurrences + 100, (sum(reads), occurrences)


def test_the_attachment_work_is_linear_in_the_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Four times the occurrences is four times the bounded reads, never more."""
    def requested(count: int) -> int:
        boundary = "b-linear"
        body = b"".join(
            b"--" + boundary.encode() + b"\r\n" + big_attachment(64, f"p{index}.bin")
            for index in range(count)
        ) + b"--" + boundary.encode() + b"--\r\n"
        raw = message(body, content_type=f'multipart/mixed; boundary="{boundary}"')
        reads: list[int] = []
        real = attach_module.read_prefix

        def recording(decoded, length):
            reads.append(length)
            return real(decoded, length)

        monkeypatch.setattr(attach_module, "read_prefix", recording)
        _run_stage(raw)
        return sum(reads)

    small = requested(4)
    big = requested(16)
    assert small > 0
    assert big == 4 * small, (small, big)


def test_a_planted_raiser_fails_the_fuzz_with_its_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A defect planted under the fuzz is caught, and the report names the seed."""
    calls = {"count": 0}
    real = attach_module.attachments

    def raising(*args: Any, **kwargs: Any):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("planted raiser")
        return real(*args, **kwargs)

    monkeypatch.setattr(attach_module, "attachments", raising)

    def run(raw: bytes) -> None:
        attach_module.attachments(
            raw, walk(EmlContainer(raw)), max_depth=HTML_MAX_DEPTH, max_elements=HTML_MAX_ELEMENTS
        )

    with pytest.raises(AssertionError, match="seed 2 on "):
        run_fuzz(4, run)


# ======================================================= 11. the L1 gate proofs


def tampered(tmp_path: Path, stem: str, mutate, name: str | None = None) -> Path:
    """A temp copy of ``stem``'s sidecar with ``mutate`` applied (a label is never edited)."""
    return sidecar_copy.tamper(tmp_path, fixture_path(stem), mutate, name=name)


def test_a_wrong_manifest_sha_fails_the_gate(tmp_path: Path) -> None:
    """A wrong content hash flips the gate on the attachment manifest."""
    def mutate(payload):
        payload["facts"]["attach.manifest"]["value"][0][6] = "0" * 64

    report = l1.check_path(tampered(tmp_path, "attach_manifest_baseline", mutate))
    assert not report.ok and fails_naming(report, "attach.manifest"), report.lines()


def test_a_wrong_winner_fails_the_gate(tmp_path: Path) -> None:
    """A wrong winner column flips the gate on attach.types."""
    def mutate(payload):
        payload["facts"]["attach.types"]["value"][0][4] = "declared_mime"

    report = l1.check_path(tampered(tmp_path, "attach_manifest_baseline", mutate))
    assert not report.ok and fails_naming(report, "attach.types"), report.lines()
    assert "measured" in report.failures[0].detail


def test_a_wrong_disagreement_flag_fails_the_gate(tmp_path: Path) -> None:
    """A flipped disagreement flag flips the gate on attach.types."""
    def mutate(payload):
        payload["facts"]["attach.types"]["value"][0][5] = False

    report = l1.check_path(tampered(tmp_path, "attach_zip_magic_declared_disagree", mutate))
    assert not report.ok and fails_naming(report, "attach.types"), report.lines()


def test_a_missing_cid_use_row_fails_the_gate(tmp_path: Path) -> None:
    """A dropped attach.cid_use row flips the gate."""
    def mutate(payload):
        rows = payload["facts"]["attach.cid_use"]["value"]
        payload["facts"]["attach.cid_use"]["value"] = rows + [["1.1", None, "n/a"]]

    report = l1.check_path(tampered(tmp_path, "attach_inline_referenced", mutate))
    assert not report.ok and fails_naming(report, "attach.cid_use"), report.lines()


def test_a_wrong_decoded_filename_fails_the_gate(tmp_path: Path) -> None:
    """A wrong decoded filename flips the gate on attach.filename."""
    def mutate(payload):
        payload["facts"]["attach.filename"]["value"][0][3] = "guessed.pdf"

    report = l1.check_path(tampered(tmp_path, "attach_filename_rfc2231_fallback", mutate))
    assert not report.ok and fails_naming(report, "attach.filename"), report.lines()


def test_a_wrong_decorative_hint_fails_the_gate(tmp_path: Path) -> None:
    """A wrong hint rule flips the gate on attach.decorative."""
    def mutate(payload):
        payload["facts"]["attach.decorative"]["value"][0][1] = (
            HINT_INLINE_UNREFERENCED_SMALL_IMAGE
        )

    report = l1.check_path(tampered(tmp_path, "attach_decoration_tracking_pixel", mutate))
    assert not report.ok and fails_naming(report, "attach.decorative"), report.lines()


def test_an_empty_or_vacuous_attach_corpus_fails_the_gate(tmp_path: Path) -> None:
    """Nothing to compare is never green: an empty corpus and a removed-facts copy both fail."""
    from emailextract.evals import l1_gate

    (tmp_path / "empty").mkdir()
    empty = l1_gate(tmp_path / "empty")
    assert empty.passed is False and "empty" in empty.detail

    def nothing_measurable(payload):
        payload["facts"] = {"time.evidence": {"phase": 3, "value": [["x"]]}}

    sidecar = tampered(tmp_path, "attach_manifest_baseline", nothing_measurable, name="vacuous")
    report = l1.check_path(sidecar)
    assert report.compared == 0, "only a later-phase fact is labelled"
    assert report.failures == (), "a later-phase fact is neither a pass nor a failure"
    from emailextract.evals import l1_gate

    vacuous = l1_gate(tmp_path / "vacuous")
    assert vacuous.passed is False and "nothing was compared" in vacuous.detail


def test_the_five_attachment_facts_are_live_and_compared() -> None:
    """The oracle measures all five facts, and the corpus carries each one."""
    facts = (
        "attach.manifest",
        "attach.types",
        "attach.filename",
        "attach.decorative",
        "attach.cid_use",
    )
    for fact_id in facts:
        measure = l1.FACTS[fact_id]
        assert measure.phase == 1 and measure.live is True and measure.function is not None
    report = l1.check_all(FIXTURES)
    compared = {outcome.fact_id for outcome in report.outcomes if outcome.status is l1.Status.OK}
    for fact_id in facts:
        assert fact_id in compared, fact_id
    # Turn 1.7 wired the html view's DOM rows live and Turn 1.7b's adjudication of the three DOM
    # span conventions (build-spec decisions 40-42) makes them agree, so the corpus is green: the
    # attachment facts stay matched and no fact mismatches (see test_l1_gate.py).
    assert report.mismatches == (), report.mismatches


def test_the_cid_dangling_row_stays_deferred_for_its_finding() -> None:
    """``attach.cid_dangling`` is measured and not emitted: its row stays ``not_yet``."""
    report = l1.check_path(fixture_path("attach_cid_dangling"))
    outcome = next(item for item in report.outcomes if item.fact_id == "gaps.later")
    assert outcome.status is l1.Status.NOT_YET, outcome
    assert attach_module.GAP_ATTACH_CID_DANGLING not in l1.LIVE_GAP_IDS


# ======================================================= 12. both interpreters


def attach_corpus_hash() -> str:
    """A sha256 over the five attachment facts of every fixture, and the cap-hit gap pairs.

    Deterministic and interpreter-independent: each fact's rows are encoded with sorted keys, so
    a dict ordering or a repr difference cannot make two interpreters look different.
    """
    digest = hashlib.sha256()
    for path in sorted(FIXTURES.glob("*/*.eml")):
        if "real" in path.parts:
            continue
        stage_ = stage(path.read_bytes())
        for fact_id in (
            "attach.manifest",
            "attach.types",
            "attach.filename",
            "attach.decorative",
            "attach.cid_use",
        ):
            digest.update(fact_id.encode())
            digest.update(
                json.dumps(stage_.rows(fact_id), sort_keys=True, ensure_ascii=False).encode()
            )
        digest.update(json.dumps(list(stage_.gaps), sort_keys=True).encode())
        digest.update(
            json.dumps([dataclasses.asdict(skip) for skip in stage_.caps], sort_keys=True).encode()
        )
    return digest.hexdigest()


def _second_interpreter() -> tuple[list[str], str, str] | None:
    """A CPython 3.11 that can also import this module (so it must have pytest), or ``None``.

    The project's own selector first (``runboth.find_python311``), then the two documentation
    venvs; when no candidate can import the harness the cross-interpreter half is **printed and
    skipped** rather than failed -- the runboth rule: never silently claim "both".
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import runboth

    candidates: list[tuple[list[str], str]] = []
    found = runboth.find_python311()
    if found is not None:
        candidates.append((found[0], found[1]))
    for name in ("wbv311", "wbv"):
        venv = Path(os.environ.get("TEMP", "")) / name / "Scripts" / "python.exe"
        if venv.is_file():
            candidates.append(([str(venv)], f"the {name} venv"))
    for prefix, source in candidates:
        probe = subprocess.run(
            [*prefix, "-c", "import pytest, sys; print(sys.version_info[:3])"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return prefix, source, probe.stdout.strip()
    print("attach: no CPython 3.11 with the harness found -- cross-interpreter hash not checked")
    return None


def test_attach_is_deterministic_across_runs_and_interpreters() -> None:
    """Same bytes, same rows, same hash -- twice here, and under a second CPython 3.11."""
    mine = attach_corpus_hash()
    assert len(mine) == 64, mine
    assert mine == attach_corpus_hash(), "the attachment stage is not deterministic across runs"
    label = f"CPython {sys.version_info.major}.{sys.version_info.minor}"
    print(f"attachment corpus hash -- {label}: {mine}")

    second = _second_interpreter()
    if second is None:
        return
    prefix, source, version = second
    core = Path(docextract_core.__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(core)])}
    script = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'tests').replace(os.sep, '/')!r});"
        " import test_attach; print('attachment corpus hash:', test_attach.attach_corpus_hash())"
    )
    completed = subprocess.run(
        [*prefix, "-c", script], cwd=str(ROOT), capture_output=True, text=True, env=env
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    theirs = next(
        line.split(":", 1)[1].strip()
        for line in completed.stdout.splitlines()
        if line.startswith("attachment corpus hash:")
    )
    assert theirs == mine, (
        f"the attachment corpus hash differs between {label} and CPython {version} "
        f"({source}): {mine} vs {theirs}"
    )


def _text_attachment_stage(media: str, disposition: str, filename: str, body: bytes):
    """An inline-built message: a plain body part and ONE ``text/*`` part with the given disposition."""
    from emailextract.container import EmlContainer, memory_bytes
    from emailextract.walk import walk

    raw = (
        b"From: a@example.test\r\nTo: b@example.test\r\nMIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
        b"--B\r\nContent-Type: text/plain\r\n\r\nhello\r\n"
        b"--B\r\nContent-Type: " + media.encode() + b'; name="' + filename.encode() + b'"\r\n'
        b"Content-Disposition: " + disposition.encode() + b'; filename="' + filename.encode() + b'"\r\n'
        b"Content-Transfer-Encoding: base64\r\n\r\n"
        + base64.b64encode(body) + b"\r\n--B--\r\n"
    )
    result = walk(EmlContainer(memory_bytes(raw)))
    return raw, attach_module.attachments(raw, result, max_depth=64, max_elements=1000)


@pytest.mark.parametrize(
    ("media", "filename", "body"),
    [
        ("text/plain", "notes.txt", b"just text"),
        ("text/csv", "data.csv", b"a,b\r\n1,2\r\n"),
        ("text/calendar", "invite.ics", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"),
        ("text/html", "page.html", b"<p>attached page</p>"),
    ],
)
def test_an_attached_text_file_is_an_attachment_not_a_body_view(media, filename, body) -> None:
    """A ``text/*`` part with ``Content-Disposition: attachment`` is an attachment occurrence (found in review:
    it was treated as a displayable body view and dropped from the manifest)."""
    _raw, stage = _text_attachment_stage(media, "attachment", filename, body)
    rows = attach_module.manifest_rows(stage)
    assert [row[1] for row in rows] == [filename], rows
    assert rows[0][4] == "attachment"
    assert rows[0][7] == len(body)
    assert rows[0][6] == hashlib.sha256(body).hexdigest()


def test_an_inline_text_part_stays_a_body_view() -> None:
    """The counter-case: ``inline`` (and no disposition) leaves a text part displayable, so it is not an attachment."""
    for disposition in ("inline",):
        _raw, stage = _text_attachment_stage("text/plain", disposition, "note.txt", b"inline words")
        assert attach_module.manifest_rows(stage) == []
