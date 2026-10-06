"""Turn 1.0d: the ``parse`` entry point, ``Limits`` and the named errors (decision 10).

Every test names the bytes it uses. The negative cases are proven able to fail by
planting a wrong predicate (:func:`emailextract.parse._sniff`) rather than editing the
module -- a test that could never fail is not a check. ``parse`` never raises for any
``bytes``: a failure is a named error **carried** in the result, and ``Limits(...)`` is
the only place a ``NamedError`` is raised.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import random
from pathlib import Path

import pytest

import emailextract.parse as parse_module
from emailextract.parse import (
    NAMED_ERROR_REASONS,
    Limits,
    NamedError,
    ParseResult,
    parse,
)

#: The CFB signature (a ``.msg``): no reader in Phase 1, so a named error.
CFB_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
CFB_FILE = CFB_SIGNATURE + b"\x00\x01\x02\x03\x04\x05\x06\x07payload bytes here"
#: A plain RFC 822 message: two header lines, a blank line, a body.
RFC822_PLAIN = b"From: ada@example.test\r\nSubject: plain\r\n\r\nbody line\r\n"
#: The same message behind an optional UTF-8 BOM (decision 14).
RFC822_BOM = b"\xef\xbb\xbf" + RFC822_PLAIN
#: The same message behind a BOM and an mbox ``From `` envelope line (decision 14).
MBOX_LINE = b"From ada@example.test Mon Jan  1 00:00:00 2024\r\n"
RFC822_BOM_MBOX = b"\xef\xbb\xbf" + MBOX_LINE + b"Subject: after mbox\r\n\r\nbody\r\n"
#: Bytes that are not a message: no ``name: value`` line at all.
GARBAGE = b"just some bytes with no field line at all\n"
#: A message of only a blank line is not a message either.
BLANK_ONLY = b"\r\n"
#: A line with a colon but space in the field name is not a field line.
SPACE_IN_NAME = b"Not A Field: value\r\n\r\nbody\r\n"

ALL_FIELDS = tuple(field.name for field in dataclasses.fields(Limits))


def _limits(**overrides: int) -> Limits:
    """An :meth:`Limits.untrusted` with named fields overridden (a test parameter)."""
    values = {
        field.name: getattr(Limits.untrusted(), field.name)
        for field in dataclasses.fields(Limits)
    }
    values.update(overrides)
    return Limits(**values)


# --------------------------------------------------------------- item 1: Limits


def test_parse_requires_limits_with_no_default() -> None:
    """``limits`` is keyword-only and required: calling without it is a ``TypeError``."""
    with pytest.raises(TypeError):
        parse(RFC822_PLAIN)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        parse(RFC822_PLAIN, None)  # type: ignore[call-arg]
    signature = inspect.signature(parse)
    parameter = signature.parameters["limits"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_limits_untrusted_constructor_supplies_the_caps() -> None:
    """``untrusted()`` returns the owner-approved set, field for field."""
    limits = Limits.untrusted()
    assert limits.max_input_bytes == 64 * 1024 * 1024
    assert limits.max_depth == 16
    assert limits.max_parts == 1000
    assert limits.max_header_bytes == 256 * 1024
    assert limits.max_decoded_part_bytes == 32 * 1024 * 1024
    assert limits.max_decoded_total_bytes == 128 * 1024 * 1024
    assert limits.max_field_work_units_per_byte == 64
    # No field carries a default: every one is a caller parameter.
    for field in __import__("dataclasses").fields(Limits):
        assert field.default is __import__("dataclasses").MISSING


# ------------------------------------------------------ item 1: the container sniff


def test_parse_sniffs_cfb_msg_as_a_named_error() -> None:
    """The CFB signature is a named error -- never a guess, never an exception."""
    result = parse(CFB_FILE, limits=Limits.untrusted())
    assert isinstance(result, ParseResult)
    assert result.kind is None and result.error is not None
    assert result.error.reason_id == "cfb_msg_unsupported"
    assert result.prelude_bom_bytes == 0 and result.prelude_mbox_bytes == 0


def test_parse_sniffs_rfc822_after_an_optional_bom() -> None:
    """The plain case, the BOM case and the BOM+mbox case all read as rfc822.

    The prelude bytes each skipped are carried so Turn 1.1 can account for them.
    """
    plain = parse(RFC822_PLAIN, limits=Limits.untrusted())
    assert (plain.kind, plain.error) == ("rfc822", None)
    assert (plain.prelude_bom_bytes, plain.prelude_mbox_bytes) == (0, 0)

    with_bom = parse(RFC822_BOM, limits=Limits.untrusted())
    assert (with_bom.kind, with_bom.error) == ("rfc822", None)
    assert (with_bom.prelude_bom_bytes, with_bom.prelude_mbox_bytes) == (3, 0)

    with_both = parse(RFC822_BOM_MBOX, limits=Limits.untrusted())
    assert (with_both.kind, with_both.error) == ("rfc822", None)
    assert (with_both.prelude_bom_bytes, with_both.prelude_mbox_bytes) == (3, len(MBOX_LINE))


def test_parse_returns_a_named_error_on_garbage() -> None:
    """No ``name: value`` line before a blank line or EOF is ``not_a_message``.

    The negative case is proven able to fail: with the field predicate replaced by one
    that accepts anything, the very same garbage parses as rfc822 -- so the assertion
    below rests on the real predicate, not on an unfalsifiable claim.
    """
    for bad in (GARBAGE, BLANK_ONLY, SPACE_IN_NAME, b""):
        result = parse(bad, limits=Limits.untrusted())
        assert result.kind is None, bad
        assert result.error is not None and result.error.reason_id == "not_a_message", bad
    # The planted predicate: garbage is now accepted, so the test above is non-vacuous.
    planted = parse_module._sniff(GARBAGE, lambda _data, _start: True)
    assert planted.kind == "rfc822" and planted.error is None


def test_parse_container_kind_overrides_the_sniff() -> None:
    """An explicit kind asserts the format -- the sniff is not consulted."""
    claimed_rfc822 = parse(CFB_FILE, container_kind="rfc822", limits=Limits.untrusted())
    assert (claimed_rfc822.kind, claimed_rfc822.error) == ("rfc822", None)

    claimed_cfb = parse(RFC822_PLAIN, container_kind="cfb_msg", limits=Limits.untrusted())
    assert claimed_cfb.kind is None and claimed_cfb.error is not None
    assert claimed_cfb.error.reason_id == "cfb_msg_unsupported"


# ------------------------------------------------- item 1: the named errors and limits


def test_parse_carries_invalid_input_for_a_non_bytes_input() -> None:
    """A non-bytes ``data`` is ``invalid_input`` -- carried, not raised."""
    for bad in ("a string", 123, bytearray(b"From: a\r\n\r\nb"), None):
        result = parse(bad, limits=Limits.untrusted())
        assert result.kind is None and result.error is not None, bad
        assert result.error.reason_id == "invalid_input", bad


def test_parse_returns_input_over_cap_before_any_sniff() -> None:
    """Over-cap is decided first: even CFB bytes over the cap are ``input_over_cap``."""
    tight = _limits(max_input_bytes=8)
    over_cap_plain = parse(RFC822_PLAIN, limits=tight)
    assert over_cap_plain.error is not None and over_cap_plain.error.reason_id == "input_over_cap"
    over_cap_cfb = parse(CFB_FILE, limits=tight)
    assert over_cap_cfb.error is not None and over_cap_cfb.error.reason_id == "input_over_cap"
    # Exactly at the cap is under it (the comparison is ``>``).
    at_cap = _limits(max_input_bytes=len(RFC822_PLAIN))
    assert parse(RFC822_PLAIN, limits=at_cap).kind == "rfc822"


def test_parse_returns_invalid_container_kind() -> None:
    """A ``container_kind`` outside the closed set is ``invalid_container_kind``."""
    for bad in ("emlx", "RFC822", "", 0, object()):
        result = parse(RFC822_PLAIN, container_kind=bad, limits=Limits.untrusted())
        assert result.kind is None and result.error is not None, bad
        assert result.error.reason_id == "invalid_container_kind", bad


@pytest.mark.parametrize("field", ALL_FIELDS)
@pytest.mark.parametrize("bad_value", [0, -1, 1.5, True, "16", None])
def test_every_invalid_limits_field_raises_the_named_error(field: str, bad_value) -> None:
    """Every field is validated: a bool, a float, zero, a negative, a str, ``None``."""
    with pytest.raises(NamedError) as caught:
        _limits(**{field: bad_value})
    assert caught.value.reason_id == "invalid_limits"
    assert field in (caught.value.detail or "")


def test_limits_construction_is_the_only_named_error_raised() -> None:
    """``parse`` returns for bytes; only ``Limits`` raises -- and it is an Exception."""
    assert issubclass(NamedError, Exception)
    assert NAMED_ERROR_REASONS == (
        "invalid_input",
        "input_over_cap",
        "invalid_container_kind",
        "cfb_msg_unsupported",
        "not_a_message",
        "invalid_limits",
    )
    # A valid Limits constructs; an invalid one raises.
    assert isinstance(Limits.untrusted(), Limits)
    with pytest.raises(NamedError):
        _limits(max_parts=0)
    # parse never raises: every one of these returns.
    for data in (GARBAGE, RFC822_PLAIN, CFB_FILE, b""):
        assert isinstance(parse(data, limits=Limits.untrusted()), ParseResult)


def test_parse_never_raises_on_hostile_bytes() -> None:
    """A seeded fuzz of random and truncated bytes: ``parse`` always returns a result."""
    limits = Limits.untrusted()
    rng = random.Random(20250304)
    inputs: list[bytes] = []
    for length in (0, 1, 2, 3, 5, 8, 9, 17, 64, 257):
        inputs.append(bytes(rng.randrange(256) for _ in range(length)))
    # Truncations of real message shapes, at every prefix and suffix.
    for base in (RFC822_PLAIN, RFC822_BOM, RFC822_BOM_MBOX, CFB_FILE, MBOX_LINE):
        for cut in range(len(base) + 1):
            inputs.append(base[:cut])
        for cut in range(len(base) + 1):
            inputs.append(base[cut:])
    for data in inputs:
        result = parse(data, limits=limits)
        assert isinstance(result, ParseResult)
        if result.error is None:
            assert result.kind == "rfc822"
        else:
            assert result.error.reason_id in NAMED_ERROR_REASONS
            assert result.kind is None


def test_parse_module_does_not_import_the_stdlib_email_module() -> None:
    """``parse.py`` owns its bytes: it imports no ``email`` (source-level check)."""
    source = Path(parse_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [name for name in imported if name.split(".")[0] == "email"]
