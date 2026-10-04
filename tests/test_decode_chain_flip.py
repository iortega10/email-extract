"""Decode-chain flip-one-input (design D11, build spec Turn 0.4).

The spec sentence is ambiguous: *"change the declared charset of one part and assert the
part's projection hash changes while the raw message hash does not"*. Changing a declared
charset means changing a **header byte**, so the raw message bytes -- and therefore the
container hash -- must change too; the reading taken here is the one that is both checkable
and honest:

* take a message and build a variant whose **only** difference is one part's declared
  charset (everything else byte-identical);
* (a) the part's **raw body bytes**, and the walker's ``body_sha256`` over them, are
  unchanged -- only a header moved;
* (b) the **decoded-text projection hash** -- sha256 of the charset-decoded text, computed
  here test-side because the skeleton does not emit one -- **changes**, because the two
  declared charsets read the same bytes as different text;
* (c) the recorded decode chain's ``declared_charset``/``used_charset`` change accordingly;
* (d) the **container hash changes**, and only because the header bytes changed (the body
  bytes are identical, so the walker would need no new output to say so).

The converse is shown too: changing a byte of the **body** changes the body hash and the
container hash but leaves the decode chain verdicts alone. No new walker output is needed, so
nothing is added to the walker.
"""

from __future__ import annotations

import hashlib

from emailextract.container import EmlContainer, memory_bytes
from emailextract.walk import walk

#: A single-part message whose body is one 0x80 octet: valid in windows-1252 (EURO SIGN) and
#: valid in iso-8859-1 (a C1 control), so the two declared charsets decode it to different text.
FLIP = b"Content-Type: text/plain; charset=windows-1252\r\n\r\n\x80\r\n"
#: The same bytes with only the declared charset changed (a header byte).
VARIANT = FLIP.replace(b"windows-1252", b"iso-8859-1")
#: The same bytes with only one body byte changed (0x80 -> 'A'), the declared charset untouched.
CONVERSE = FLIP.replace(b"\x80", b"A")


def _only(result):
    (part,) = result.parts
    return part


def _raw_body(result, message: bytes) -> bytes:
    return _only(result).body_span.slice(message)


def _projection_hash(result, message: bytes) -> str:
    """sha256 of the charset-decoded body text -- computed here, since the skeleton emits none."""
    text = _raw_body(result, message).decode(_only(result).decode_chain.used_charset)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_flipping_the_declared_charset_moves_the_projection_not_the_body() -> None:
    base = walk(EmlContainer(memory_bytes(FLIP)))
    variant = walk(EmlContainer(memory_bytes(VARIANT)))

    # (a) the raw body bytes, and the walker's hash over them, are unchanged: only a header moved.
    assert _raw_body(base, FLIP) == _raw_body(variant, VARIANT) == b"\x80\r\n"
    assert _only(base).body_sha256 == _only(variant).body_sha256

    # (b) the decoded-text projection hash changes: 0x80 is EURO SIGN in windows-1252, U+0080
    #     in iso-8859-1.
    assert _projection_hash(base, FLIP) != _projection_hash(variant, VARIANT)

    # (c) the recorded decode chain verdicts change accordingly.
    assert _only(base).decode_chain.declared_charset == "windows-1252"
    assert _only(base).decode_chain.used_charset == "windows-1252"
    assert _only(variant).decode_chain.declared_charset == "iso-8859-1"
    assert _only(variant).decode_chain.used_charset == "iso-8859-1"

    # (d) the container hash changes, and only because a header byte changed (the body is equal).
    assert base.container_hash != variant.container_hash
    assert _raw_body(base, FLIP) == _raw_body(variant, VARIANT)


def test_changing_a_body_byte_moves_the_hashes_but_not_the_decode_chain() -> None:
    base = walk(EmlContainer(memory_bytes(FLIP)))
    converse = walk(EmlContainer(memory_bytes(CONVERSE)))

    # The body byte changed, so the body hash and the container hash move ...
    assert _raw_body(base, FLIP) != _raw_body(converse, CONVERSE)
    assert _only(base).body_sha256 != _only(converse).body_sha256
    assert base.container_hash != converse.container_hash

    # ... but the decode chain verdicts (declared -> used) are unchanged: no header moved.
    assert _only(base).decode_chain == _only(converse).decode_chain
    assert _projection_hash(base, FLIP) != _projection_hash(converse, CONVERSE)
