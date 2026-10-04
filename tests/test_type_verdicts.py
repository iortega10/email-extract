"""Turn 1.0b: decision 6 -- the three type verdicts become ``TriValue``.

``declared_mime``, ``magic`` and ``container_introspection`` are each ``value |
unknown`` (design D4). ``magic`` consulted and nothing matched is ``VALUE(
"unrecognized")`` -- a closed sentinel value, never ``UNKNOWN`` -- and not computed
(a zero-length part, a cap hit, a decode failure) is ``UNKNOWN(reason_id)``. The
disagreement and the family derivation are pure functions over the verdicts; they
parse no bytes. The winner order is magic over declared_mime over
container_introspection where known.
"""

from __future__ import annotations

import dataclasses

import pytest
from docextract_core.codec import CodecError

from emailextract.model import (
    TriState,
    TriValue,
    TypeVerdicts,
    TypeVerdictSource,
    UNRECOGNIZED,
    record_from_bytes,
    record_to_bytes,
    type_disagreement,
    type_family,
    type_family_of,
    type_unknown,
    type_winner,
)


def _value(token: str) -> TriValue:
    return TriValue(state=TriState.VALUE, value=token)


def _unknown(reason: str = "not_built_in_phase1") -> TriValue:
    return TriValue(state=TriState.UNKNOWN, reason_id=reason)


def test_each_verdict_is_a_tri_value() -> None:
    """Each of the three verdicts is a ``TriValue`` field with a ``TriValue`` default."""
    by_name = {field.name: field for field in dataclasses.fields(TypeVerdicts)}
    for name in ("declared_mime", "magic", "container_introspection"):
        assert name in by_name, name
        assert by_name[name].type in ("TriValue", TriValue), by_name[name].type
    default = TypeVerdicts()
    for name in ("declared_mime", "magic", "container_introspection"):
        assert isinstance(getattr(default, name), TriValue)
    # A bare string is no longer a verdict.
    with pytest.raises(CodecError):
        TypeVerdicts(declared_mime="text/plain")  # type: ignore[arg-type]

    verdicts = TypeVerdicts(
        declared_mime=_value("application/pdf"),
        magic=_value("pdf"),
        container_introspection=_unknown(),
        winner=TypeVerdictSource.MAGIC,
        disagreement=False,
    )
    payload = record_to_bytes(verdicts)
    assert record_from_bytes(TypeVerdicts, payload) == verdicts
    assert record_to_bytes(record_from_bytes(TypeVerdicts, payload)) == payload


def test_unrecognized_is_a_value_not_unknown() -> None:
    """``unrecognized`` is ``VALUE`` (consulted, nothing matched), never ``UNKNOWN``."""
    unrecognized = _value(UNRECOGNIZED)
    assert unrecognized.state is TriState.VALUE
    assert unrecognized.value == "unrecognized"
    # It names no family: it never fires a disagreement and never supplies a winner.
    assert type_family_of(unrecognized) is None
    assert type_family("unrecognized") is None
    assert type_unknown(unrecognized) is True
    assert type_disagreement(unrecognized, _unknown()) is False
    assert type_winner(unrecognized, _unknown(), _unknown()) is None
    # And it is not the same thing as the not-computed state.
    assert _unknown().state is TriState.UNKNOWN


def test_disagreement_needs_two_families() -> None:
    """``attach.type_disagreement`` iff two state-VALUE verdicts name >= 2 families."""
    # application/pdf declared, magic pdf -> one family -> no disagreement.
    assert (
        type_disagreement(_value("application/pdf"), _value("pdf"), _unknown()) is False
    )
    # text/plain declared, magic zip -> two families -> disagreement.
    assert type_disagreement(_value("text/plain"), _value("zip"), _unknown()) is True
    # ``unrecognized`` and UNKNOWN contribute no family and never fire it.
    assert type_disagreement(_value("text/plain"), _value("unrecognized"), _unknown()) is False
    assert type_disagreement(_unknown(), _unknown(), _unknown()) is False
    # A MIME type with parameters still reduces to its subtype.
    assert type_family("text/plain; charset=utf-8") == "plain"


def test_unknown_iff_no_family_and_magic_wins() -> None:
    """``attach.type_unknown`` iff no verdict yields a family; the winner honours priority."""
    assert type_unknown(_unknown(), _value("unrecognized"), _unknown()) is True
    assert type_unknown(_value("pdf"), _unknown(), _unknown()) is False
    # magic beats declared_mime beats container_introspection, where known.
    assert type_winner(_value("application/pdf"), _value("zip"), _unknown()) is TypeVerdictSource.MAGIC
    assert (
        type_winner(_value("application/pdf"), _value("unrecognized"), _unknown())
        is TypeVerdictSource.DECLARED_MIME
    )
    assert (
        type_winner(_value("unrecognized"), _unknown(), _value("pdf"))
        is TypeVerdictSource.CONTAINER_INTROSPECTION
    )
    assert type_winner(_unknown(), _unknown(), _unknown()) is None
    # The record's own invariant: a winner must name a known verdict.
    with pytest.raises(CodecError):
        TypeVerdicts(magic=_unknown(), winner=TypeVerdictSource.MAGIC)
