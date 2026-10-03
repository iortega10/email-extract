"""Turn 0.1 tests: the status/reason table, enforced as hand-typed contract data.

Ground truth typed from the spec's reason set -- not copied from
`emailextract.model.REASON_TABLE`. A tenth status, a widened set, a
missing-mandatory reason, or a reason on the wrong status must all fail here.
"""

from __future__ import annotations

import pytest

from docextract_core.codec import CodecError

from emailextract import (
    CryptoKind,
    REASON_TABLE,
    Status,
    StatusOutcome,
    TriState,
    TriValue,
)
from emailextract.model import reason_required, reasons_for


# Hand-typed: status -> (a reason is mandatory, every allowed reason id).
EXPECTED_REASON_TABLE = {
    "parsed": (False, ()),
    "skipped": (True, ("size_cap", "total_size_cap", "depth_cap")),
    "unsupported": (False, ()),
    "not_installed": (False, ()),
    "failed": (True, ("extractor_error", "decode_failed", "sibling_contract_error")),
    "password_protected": (False, ()),
    "encrypted": (False, ()),
    "empty": (False, ()),
    "truncated": (True, ("stream_ended_early", "declared_length_mismatch", "cap_hit_mid_stream")),
}

ALL_REASON_IDS = tuple(reason for _, reasons in EXPECTED_REASON_TABLE.values() for reason in reasons)

# A status whose reason is mandatory cannot be reached without a sibling or
# crypto-kind explainer; typed here so the row test can satisfy the invariant.
EXPLAINER_FIELDS = {
    "not_installed": {"needed_sibling": "olefile"},
    "password_protected": {"crypto_kind": CryptoKind.PASSWORD},
    "encrypted": {"crypto_kind": CryptoKind.CERTIFICATE},
}


def _outcome(status: Status, reason: str | None = None) -> StatusOutcome:
    return StatusOutcome(status=status, reason=reason, **EXPLAINER_FIELDS.get(status.value, {}))


def test_status_enum_has_exactly_the_nine_members() -> None:
    assert len(Status.__members__) == 9
    assert {s.value for s in Status} == set(EXPECTED_REASON_TABLE)
    assert "superseded" not in {s.value for s in Status}


def test_a_tenth_status_cannot_be_constructed() -> None:
    with pytest.raises(ValueError):
        Status("superseded")


def test_reason_table_has_exactly_the_spec_rows() -> None:
    assert set(REASON_TABLE) == {Status(name) for name in EXPECTED_REASON_TABLE}
    for name, (required, reasons) in EXPECTED_REASON_TABLE.items():
        status = Status(name)
        assert REASON_TABLE[status] == reasons
        assert reasons_for(status) == reasons
        assert reason_required(status) is required


def test_every_reason_belongs_to_exactly_one_status() -> None:
    """D6: a reason belongs to exactly one status -- the three rows hold 3 + 3 + 3."""
    owners: dict[str, str] = {}
    for status_name, (_, reasons) in EXPECTED_REASON_TABLE.items():
        for reason in reasons:
            assert reason not in owners, f"{reason} claimed by both {owners.get(reason)} and {status_name}"
            owners[reason] = status_name
    assert len(owners) == 9


def test_reason_mandatory_rows_reject_a_missing_reason() -> None:
    for status_name, (required, _) in EXPECTED_REASON_TABLE.items():
        status = Status(status_name)
        if required:
            with pytest.raises(CodecError):
                _outcome(status)
        else:
            assert _outcome(status).reason is None


def test_allowed_reasons_build_and_any_other_reason_raises() -> None:
    for status_name, (_, allowed) in EXPECTED_REASON_TABLE.items():
        status = Status(status_name)
        for reason in allowed:
            assert _outcome(status, reason).reason == reason
        for reason in ALL_REASON_IDS:
            if reason not in allowed:
                with pytest.raises(CodecError):
                    _outcome(status, reason)


def test_tri_state_unknown_requires_a_reason_id() -> None:
    with pytest.raises(CodecError):
        TriValue(state=TriState.UNKNOWN)
    assert TriValue(state=TriState.UNKNOWN, reason_id="decode_failed").reason_id == "decode_failed"
    with pytest.raises(CodecError):
        TriValue(state=TriState.VALUE, value="x", reason_id="decode_failed")
    with pytest.raises(CodecError):
        TriValue(state=TriState.ABSENT, reason_id="decode_failed")
    with pytest.raises(CodecError):
        TriValue(state=TriState.UNKNOWN, value="x", reason_id="decode_failed")


def test_not_installed_needs_the_sibling_explainer() -> None:
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.NOT_INSTALLED)
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.NOT_INSTALLED, reason="extractor_error")
    ok = StatusOutcome(status=Status.NOT_INSTALLED, needed_sibling="olefile")
    assert ok.needed_sibling == "olefile"
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.PARSED, needed_sibling="olefile")


def test_crypto_statuses_need_their_crypto_kind() -> None:
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.PASSWORD_PROTECTED)
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.ENCRYPTED)
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.PASSWORD_PROTECTED, crypto_kind=CryptoKind.CERTIFICATE)
    password = StatusOutcome(status=Status.PASSWORD_PROTECTED, crypto_kind=CryptoKind.PASSWORD)
    assert password.crypto_kind is CryptoKind.PASSWORD
    for kind in (CryptoKind.CERTIFICATE, CryptoKind.DRM, CryptoKind.UNKNOWN):
        assert StatusOutcome(status=Status.ENCRYPTED, crypto_kind=kind).crypto_kind is kind
    with pytest.raises(CodecError):
        StatusOutcome(status=Status.PARSED, crypto_kind=CryptoKind.PASSWORD)
