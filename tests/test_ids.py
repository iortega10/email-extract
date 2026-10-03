"""Turn 0.2: content-addressed identity (build spec, Turn 0.2; D12).

The rules under test: the message id is the sha256 of the raw bytes; a part id is
the triple (container hash, raw span, content hash); and the ``1.2.3`` locator is
explicitly *not* an identity -- renumbering it changes nothing, which is the
whole reason the id exists as its own member.
"""

from __future__ import annotations

import pytest

from emailextract.ids import (
    NOT_BUILT_IN_PHASE0,
    RawSpan,
    container_hash,
    content_hash,
    part_id,
    sha256_hex,
    walk_key,
)

MESSAGE = b"From: a@example.com\r\nSubject: identity\r\n\r\nhello\r\n"


def test_the_container_hash_is_the_sha256_of_the_raw_bytes() -> None:
    assert container_hash(MESSAGE) == sha256_hex(MESSAGE)
    assert container_hash(MESSAGE) == container_hash(bytes(MESSAGE))
    assert container_hash(MESSAGE) != container_hash(MESSAGE + b"!")


def test_the_part_id_ignores_the_locator_and_its_three_members_are_all_identity() -> None:
    span = RawSpan(20, 5, "1.2.3")
    renumbered = RawSpan(20, 5, "1.7")
    own = content_hash(span.slice(MESSAGE))
    ident = container_hash(MESSAGE)

    # The locator renumbered: the id did not move (it is not an identity).
    assert part_id(ident, span, own) == part_id(ident, renumbered, own)
    # Any member of the triple changed: a different part of a different message.
    assert part_id(ident, span, own) != part_id(ident, RawSpan(21, 5, "1.2.3"), own)
    assert part_id(ident, span, own) != part_id(ident, RawSpan(20, 6, "1.2.3"), own)
    assert part_id(ident, span, own) != part_id(ident, span, content_hash(b"different"))
    assert part_id(ident, span, own) != part_id(container_hash(MESSAGE + b"!"), span, own)


def test_a_part_id_cannot_be_built_without_its_three_members() -> None:
    span = RawSpan(0, 1, "1")
    with pytest.raises(ValueError):
        part_id("", span, "abc")
    with pytest.raises(ValueError):
        part_id("abc", span, "")
    with pytest.raises(ValueError):
        part_id("abc", "not-a-span", "abc")  # type: ignore[arg-type]


def test_a_raw_span_slices_the_message_verbatim() -> None:
    span = RawSpan(5, 6, "1.1")
    assert span.end == 11
    assert span.slice(MESSAGE) == MESSAGE[5:11]
    with pytest.raises(ValueError):
        RawSpan(0, len(MESSAGE) + 1).slice(MESSAGE)
    assert RawSpan(3, 0, "1.2").slice(MESSAGE) == b""


@pytest.mark.parametrize("offset,length", [(-1, 3), (0, -1), (0, True), (True, 3), (0, 1.5)])
def test_a_raw_span_rejects_a_negative_or_non_int_member(offset: int, length: int) -> None:
    with pytest.raises(ValueError):
        RawSpan(offset, length)  # type: ignore[arg-type]


def test_a_walk_key_is_built_from_the_hashed_inputs_only() -> None:
    ident = container_hash(MESSAGE)
    key = walk_key(ident, "1", "1", "1")
    assert key == walk_key(ident, "1", "1", "1")
    # A version bump is a NEW key, never an overwrite of a cached shape.
    assert key != walk_key(ident, "2", "1", "1")
    assert key != walk_key(container_hash(MESSAGE + b"\r\n"), "1", "1", "1")
    with pytest.raises(ValueError):
        walk_key("", "1", "1", "1")


def test_the_not_built_reason_id_is_the_registry_value() -> None:
    assert NOT_BUILT_IN_PHASE0 == "not_built_in_phase0"
