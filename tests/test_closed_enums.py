"""Turn 0.1 tests: all closed enums and tri-state shapes are closed as typed here."""

from __future__ import annotations

import pytest

from docextract_core.codec import CodecError

from emailextract import (
    BodyView,
    ChildLinkState,
    Classification,
    ContainerKind,
    CryptoKind,
    DecorativeHint,
    DecorativeHintState,
    EncodingSource,
    MatchType,
    RollupScope,
    Selection,
    ThreadSource,
    TypeVerdictSource,
)


def test_body_view_is_exactly_two_states() -> None:
    assert {v.value for v in BodyView} == {"html", "plain"}
    assert len(BodyView.__members__) == 2


def test_encoding_source_is_exactly_seven_members() -> None:
    assert {v.value for v in EncodingSource} == {
        "internet_cpid",
        "message_cpid",
        "ascii",
        "utf8_strict",
        "windows_1252",
        "declared_charset",
        "fallback",
    }
    assert len(EncodingSource.__members__) == 7


def test_child_link_is_exactly_four_states() -> None:
    assert {v.value for v in ChildLinkState} == {
        "resolved",
        "store_absent",
        "child_absent",
        "version_mismatch",
    }
    assert len(ChildLinkState.__members__) == 4


def test_container_kind_is_exactly_two() -> None:
    assert {v.value for v in ContainerKind} == {"rfc822", "cfb_msg"}
    assert len(ContainerKind.__members__) == 2


def test_closed_enum_signatures_are_exactly_the_spec_values() -> None:
    assert {v.value for v in Selection} == {"selected", "alternative_not_selected", "n/a"}
    assert {v.value for v in Classification} == {"unknown", "inline", "attachment"}
    assert {v.value for v in TypeVerdictSource} == {
        "declared_mime",
        "magic",
        "container_introspection",
    }
    assert {v.value for v in ThreadSource} == {"references", "in_reply_to"}
    assert {v.value for v in MatchType} == {"exact", "synonym", "stem"}
    assert {v.value for v in RollupScope} == {"message", "part", "attachment", "body_view"}
    assert {v.value for v in CryptoKind} == {"password", "certificate", "drm", "unknown"}


def test_decorative_hint_is_rule_id_or_absent_never_a_bool() -> None:
    assert {v.value for v in DecorativeHintState} == {"rule_id", "absent"}
    assert len(DecorativeHintState.__members__) == 2
    empty = DecorativeHint()
    assert empty.state is DecorativeHintState.ABSENT
    assert empty.rule_id is None
    assert isinstance(empty.state, DecorativeHintState)
    with pytest.raises(CodecError):
        DecorativeHint(state=DecorativeHintState.ABSENT, rule_id="decorative.rule.border")
    with pytest.raises(CodecError):
        DecorativeHint(state=DecorativeHintState.RULE_ID)
