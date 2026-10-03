"""Turn 0.1 frozen contract layer for email-extract.

One dataclass = one design contract (D1-D16); everything frozen. Records encode
and decode through the strict core codec (:mod:`docextract_core.codec`): the
versioned envelope ``{"schema_version", "record"}``, strict decoding, unknown
keys raise ``CodecError`` -- a drifted reader fails loudly instead of silently
dropping a field. No validator or hand-rolled ``to_dict``/``from_dict`` lives
next to the codec; construction-time invariants (the D6 reason table, the
tri-state and the value-or-unknown shapes) are enforced in ``__post_init__``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Mapping

from docextract_core.codec import (
    MIN_SUPPORTED_VERSION,
    SCHEMA_VERSION,
    CodecError,
    from_json,
    to_json,
)

from .timeevent import Span, TimeEvent, Trust
from .versions import EMAIL_PARSER_VERSION, FLAG_SCHEMA_VERSION, OUTPUT_SCHEMA_VERSION

__all__ = [
    "AttachmentOccurrence",
    "BodyView",
    "ChildLink",
    "ChildLinkState",
    "Classification",
    "ClassificationClaim",
    "ContainerFacts",
    "ContainerKind",
    "ContentFingerprint",
    "CryptoKind",
    "DecodeChain",
    "DecorativeHint",
    "DecorativeHintState",
    "EmailDocument",
    "EncodingSource",
    "FlagHit",
    "FlagRollup",
    "FlagSection",
    "GroupCount",
    "HeaderField",
    "HitLocation",
    "MatchType",
    "PartRecord",
    "QuoteCrossCheck",
    "REASON_TABLE",
    "RollupScope",
    "RunRecord",
    "Selection",
    "SameMessageCandidate",
    "Span",
    "Status",
    "StatusOutcome",
    "ThreadEdge",
    "ThreadSource",
    "TimeEvent",
    "TriState",
    "TriValue",
    "TypeVerdicts",
    "TypeVerdictSource",
    "reason_required",
    "reasons_for",
    "record_from_bytes",
    "record_to_bytes",
]


# --------------------------------------------------------------------------
# Closed enums (D6 axes and the Turn 0.1 contract enums)
# --------------------------------------------------------------------------


class ContainerKind(str, Enum):
    """What opened the file (D14). ``cfb_msg`` exists in the contract; Phase 0 produces nothing."""

    RFC822 = "rfc822"
    CFB_MSG = "cfb_msg"


class Classification(str, Enum):
    """D6/D4: what the part is, never derived from size."""

    ATTACHMENT = "attachment"
    INLINE = "inline"
    UNKNOWN = "unknown"


class Selection(str, Enum):
    """D6: which alternative was selected for display (the recorded display rule)."""

    SELECTED = "selected"
    ALTERNATIVE_NOT_SELECTED = "alternative_not_selected"
    NOT_APPLICABLE = "n/a"


class Status(str, Enum):
    """D6: closed, exactly nine members; never derived from classification or size."""

    PARSED = "parsed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    NOT_INSTALLED = "not_installed"
    FAILED = "failed"
    PASSWORD_PROTECTED = "password_protected"
    ENCRYPTED = "encrypted"
    EMPTY = "empty"
    TRUNCATED = "truncated"


class EncodingSource(str, Enum):
    """Where a charset decision came from (D14/D16)."""

    INTERNET_CPID = "internet_cpid"
    MESSAGE_CPID = "message_cpid"
    ASCII = "ascii"
    UTF8_STRICT = "utf8_strict"
    WINDOWS_1252 = "windows_1252"
    DECLARED_CHARSET = "declared_charset"
    FALLBACK = "fallback"


class ChildLinkState(str, Enum):
    """The four ChildLink states, exactly (Turn 0.1)."""

    RESOLVED = "resolved"
    STORE_ABSENT = "store_absent"
    CHILD_ABSENT = "child_absent"
    VERSION_MISMATCH = "version_mismatch"


class BodyView(str, Enum):
    """Which body view a digest was taken over (D14: HTML if present, else plain)."""

    HTML = "html"
    PLAIN = "plain"


class CryptoKind(str, Enum):
    """D6: password = opens with a secret the user could hold; the rest = no held secret."""

    PASSWORD = "password"
    CERTIFICATE = "certificate"
    DRM = "drm"
    UNKNOWN = "unknown"


class TypeVerdictSource(str, Enum):
    """Which of the three type verdicts is recorded as the winner."""

    DECLARED_MIME = "declared_mime"
    MAGIC = "magic"
    CONTAINER_INTROSPECTION = "container_introspection"


class TriState(str, Enum):
    """The three states of the tri-state value type."""

    VALUE = "value"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class DecorativeHintState(str, Enum):
    """``decorative_hint`` is ``rule_id | absent`` -- never a boolean."""

    RULE_ID = "rule_id"
    ABSENT = "absent"


class ThreadSource(str, Enum):
    """Which header a threading edge was claimed from (D7)."""

    REFERENCES = "references"
    IN_REPLY_TO = "in_reply_to"


class QuoteCrossCheck(str, Enum):
    """D7: a cross-check against the D3 boundary map; never an override."""

    CONSISTENT_WITH_BODY_QUOTE = "consistent_with_body_quote"
    CONFLICTS = "conflicts"


class MatchType(str, Enum):
    """D8: how a flag term matched."""

    EXACT = "exact"
    SYNONYM = "synonym"
    STEM = "stem"


class RollupScope(str, Enum):
    """D8: rollup is per view, never across views."""

    MESSAGE = "message"
    PART = "part"
    ATTACHMENT = "attachment"
    BODY_VIEW = "body_view"


# --------------------------------------------------------------------------
# D6 reason table: string reasons, one status per reason, enforced at construction
# --------------------------------------------------------------------------

REASON_TABLE: Final[Mapping[Status, tuple[str, ...]]] = {
    Status.PARSED: (),
    Status.SKIPPED: ("size_cap", "total_size_cap", "depth_cap"),
    Status.UNSUPPORTED: (),
    Status.NOT_INSTALLED: (),
    Status.FAILED: ("extractor_error", "decode_failed", "sibling_contract_error"),
    Status.PASSWORD_PROTECTED: (),
    Status.ENCRYPTED: (),
    Status.EMPTY: (),
    Status.TRUNCATED: ("stream_ended_early", "declared_length_mismatch", "cap_hit_mid_stream"),
}


def reasons_for(status: Status) -> tuple[str, ...]:
    """Legal reasons for ``status``; empty means the status takes no reason."""
    if not isinstance(status, Status):
        raise CodecError(f"unknown status: {status!r}")
    return REASON_TABLE[status]


def reason_required(status: Status) -> bool:
    """True when the status cannot be built without a reason (D6: skipped/failed/truncated)."""
    return bool(reasons_for(status))


def _non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CodecError(f"{name} must be a non-empty str")
    return value


# --------------------------------------------------------------------------
# Shared value shapes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TriValue:
    """The tri-state value type: ``value | absent | unknown(reason_id)``.

    An unknown cannot be built without its reason id; a value and an absent carry
    none.
    """

    state: TriState = TriState.ABSENT
    value: str | None = None
    reason_id: str | None = None

    def __post_init__(self) -> None:
        if self.state is TriState.VALUE:
            if self.value is None:
                raise CodecError("tri-state value: state=value requires a value")
            _non_empty(self.value, "tri-state value")
            if self.reason_id is not None:
                raise CodecError("tri-state value: state=value takes no reason_id")
        elif self.state is TriState.ABSENT:
            if self.value is not None or self.reason_id is not None:
                raise CodecError("tri-state value: state=absent carries neither value nor reason_id")
        elif self.state is TriState.UNKNOWN:
            if self.value is not None:
                raise CodecError("tri-state value: state=unknown carries no value")
            if self.reason_id is None:
                raise CodecError("tri-state value: state=unknown cannot be built without its reason_id")
            _non_empty(self.reason_id, "tri-state reason_id")
        else:
            raise CodecError(f"tri-state value: unknown state {self.state!r}")


@dataclass(frozen=True)
class DecorativeHint:
    """``decorative_hint``: ``rule_id | absent`` -- never a boolean."""

    state: DecorativeHintState = DecorativeHintState.ABSENT
    rule_id: str | None = None

    def __post_init__(self) -> None:
        if self.state is DecorativeHintState.RULE_ID:
            if self.rule_id is None:
                raise CodecError("decorative_hint: state=rule_id requires a rule_id")
            _non_empty(self.rule_id, "decorative_hint.rule_id")
        elif self.state is DecorativeHintState.ABSENT:
            if self.rule_id is not None:
                raise CodecError("decorative_hint: state=absent carries no rule_id")
        else:
            raise CodecError(f"decorative_hint: unknown state {self.state!r}")


@dataclass(frozen=True)
class StatusOutcome:
    """D6 status + reason pairing, enforced at construction.

    A reason that belongs to another status raises; a status that needs a reason
    cannot be built without one; a status that takes none rejects one. The
    explainers ride along: ``needed_sibling`` for ``not_installed`` (environmental),
    ``crypto_kind`` for the two crypto statuses; ``unsupported`` is explained by
    the record's ``detected_type`` verdicts.
    """

    status: Status
    reason: str | None = None
    needed_sibling: str | None = None
    crypto_kind: CryptoKind | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, Status):
            raise CodecError(f"status must be a Status, got {self.status!r}")
        allowed = reasons_for(self.status)
        if allowed:
            if self.reason is None:
                raise CodecError(f"status {self.status.value!r} requires a reason from {allowed}")
            if self.reason not in allowed:
                raise CodecError(
                    f"reason {self.reason!r} does not belong to status {self.status.value!r}; "
                    f"allowed: {allowed}"
                )
        elif self.reason is not None:
            raise CodecError(f"status {self.status.value!r} takes no reason, got {self.reason!r}")
        if self.status is Status.NOT_INSTALLED:
            if self.needed_sibling is None:
                raise CodecError("status not_installed carries needed_sibling")
            _non_empty(self.needed_sibling, "needed_sibling")
        elif self.needed_sibling is not None:
            raise CodecError(f"status {self.status.value!r} carries no needed_sibling")
        if self.status is Status.PASSWORD_PROTECTED:
            if self.crypto_kind is not CryptoKind.PASSWORD:
                raise CodecError("status password_protected carries crypto_kind=password")
        elif self.status is Status.ENCRYPTED:
            if self.crypto_kind not in (
                CryptoKind.CERTIFICATE,
                CryptoKind.DRM,
                CryptoKind.UNKNOWN,
            ):
                raise CodecError("status encrypted carries crypto_kind=certificate|drm|unknown")
        elif self.crypto_kind is not None:
            raise CodecError(f"status {self.status.value!r} carries no crypto_kind")


@dataclass(frozen=True)
class ClassificationClaim:
    """A recorded CLAIM for ``msip_labels``: an open string plus where the claim came from."""

    hint: str
    source: str

    def __post_init__(self) -> None:
        _non_empty(self.hint, "classification_hint.hint")
        _non_empty(self.source, "classification_hint.source")


@dataclass(frozen=True)
class DecodeChain:
    """The decode chain recorded per part / per filename (D6/D16)."""

    declared_cte: str | None = None
    declared_charset: str | None = None
    used_cte: str | None = None
    used_charset: str | None = None
    fallback_fired: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.fallback_fired, bool):
            raise CodecError("decode_chain.fallback_fired must be bool")


@dataclass(frozen=True)
class TypeVerdicts:
    """The three type verdicts plus winner plus disagreement (Turn 0.1)."""

    declared_mime: str | None = None
    magic: str | None = None
    container_introspection: str | None = None
    winner: TypeVerdictSource | None = None
    disagreement: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.disagreement, bool):
            raise CodecError("type_verdicts.disagreement must be bool")
        if self.winner is not None and getattr(self, self.winner.value) is None:
            raise CodecError(f"type_verdicts: winner {self.winner.value!r} has no verdict")


@dataclass(frozen=True)
class ContainerFacts:
    """Kind-specific container facts (D14).

    ``rfc822`` records the MIME tree facts; ``cfb_msg`` records sector size,
    streams and the property set. An open str->str mapping: Phase 0 produces
    neither container, so the fact names stay producer-owned.
    """

    facts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentFingerprint:
    """D14: separate from container_hash and labeled -- neither is "the" identity."""

    body_digest: str
    body_digest_view: BodyView

    def __post_init__(self) -> None:
        _non_empty(self.body_digest, "content_fingerprint.body_digest")


@dataclass(frozen=True)
class SameMessageCandidate:
    """D14 cross-container relation: equal claimed Message-ID and equal body_digest.

    A plain-only versus HTML-only pair surfaces as no candidate (different
    ``body_digest_view``); quote and signature stripping are never in the digest
    key.
    """

    left_container_hash: str
    right_container_hash: str
    message_id_claimed: str
    body_digest: str
    body_digest_view: BodyView

    def __post_init__(self) -> None:
        _non_empty(self.left_container_hash, "same_message_candidate.left_container_hash")
        _non_empty(self.right_container_hash, "same_message_candidate.right_container_hash")
        _non_empty(self.message_id_claimed, "same_message_candidate.message_id_claimed")
        _non_empty(self.body_digest, "same_message_candidate.body_digest")


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HeaderField:
    """One header field: name and raw value always recorded; the decoded value is tri-state."""

    name: str
    raw_value: str
    ordinal: int
    value: TriValue = field(default_factory=TriValue)
    flags: "FlagSection" = field(default_factory=lambda: FlagSection())

    def __post_init__(self) -> None:
        _non_empty(self.name, "header_field.name")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise CodecError("header_field.ordinal must be an int >= 0")


@dataclass(frozen=True)
class PartRecord:
    """One node of the parts tree. ``part_id`` is an explicitly non-stable locator.

    Container and body parts carry a ``role`` and are never attachment
    occurrences, so they have no status (``status`` is None there).
    """

    part_id: str
    content_type: str | None = None
    parent_part_id: str | None = None
    role: str | None = None
    classification: Classification = Classification.UNKNOWN
    selection: Selection = Selection.NOT_APPLICABLE
    status: StatusOutcome | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    encoding_source: EncodingSource | None = None
    decode_chain: DecodeChain = field(default_factory=DecodeChain)
    decorative_hint: DecorativeHint = field(default_factory=DecorativeHint)
    type_verdicts: TypeVerdicts | None = None
    flags: "FlagSection" = field(default_factory=lambda: FlagSection())

    def __post_init__(self) -> None:
        _non_empty(self.part_id, "part_record.part_id")


@dataclass(frozen=True)
class AttachmentOccurrence:
    """One attachment occurrence (D12): ``attachment_id`` is the sha256, the
    ``occurrence_path`` is the part path @ occurrence ordinal -- recorded as an
    explicitly non-stable locator only.
    """

    attachment_id: str
    occurrence_path: str
    part_id: str
    classification: Classification = Classification.UNKNOWN
    selection: Selection = Selection.NOT_APPLICABLE
    status: StatusOutcome | None = None
    filename_raw: str | None = None
    filename_decoded: TriValue = field(default_factory=TriValue)
    cid: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    route: str | None = None
    encoding_source: EncodingSource | None = None
    decode_chain: DecodeChain = field(default_factory=DecodeChain)
    decorative_hint: DecorativeHint = field(default_factory=DecorativeHint)
    type_verdicts: TypeVerdicts | None = None
    flags: "FlagSection" = field(default_factory=lambda: FlagSection())

    def __post_init__(self) -> None:
        _non_empty(self.attachment_id, "attachment_occurrence.attachment_id")
        _non_empty(self.occurrence_path, "attachment_occurrence.occurrence_path")
        _non_empty(self.part_id, "attachment_occurrence.part_id")


@dataclass(frozen=True)
class ChildLink:
    """A link to a child result; the four states, exactly."""

    state: ChildLinkState
    child_id: str
    store_id: str | None = None
    expected_version: str | None = None
    found_version: str | None = None
    flags: "FlagSection" = field(default_factory=lambda: FlagSection())

    def __post_init__(self) -> None:
        if not isinstance(self.state, ChildLinkState):
            raise CodecError(f"child_link.state must be a ChildLinkState, got {self.state!r}")
        _non_empty(self.child_id, "child_link.child_id")


@dataclass(frozen=True)
class ThreadEdge:
    """A threading edge claimed from ``References``/``In-Reply-To`` (D7).

    Edges are recorded ``claimed`` (attacker-controlled headers); the quote
    cross-check is a sibling observation, never an override.
    """

    child_message_id: str
    parent_message_id: str | None
    source: ThreadSource
    trust: Trust = Trust.CLAIMED
    cross_check: QuoteCrossCheck | None = None
    flags: "FlagSection" = field(default_factory=lambda: FlagSection())

    def __post_init__(self) -> None:
        _non_empty(self.child_message_id, "thread_edge.child_message_id")
        if self.parent_message_id is not None:
            _non_empty(self.parent_message_id, "thread_edge.parent_message_id")


@dataclass(frozen=True)
class HitLocation:
    """Opaque, producer-shaped location (D8): part / view / span / unit."""

    part: str | None = None
    view: str | None = None
    span: Span | None = None
    unit: int | None = None


@dataclass(frozen=True)
class FlagHit:
    """D8 FlagHit, shape only: there is no ``excluded`` field."""

    term_group_id: str
    term_form: str
    match_type: MatchType
    location: HitLocation
    view_id: str
    quote_boundary_ordinal: int | None = None
    quote_kind: str | None = None
    matcher_version: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.term_group_id, "flag_hit.term_group_id")
        _non_empty(self.term_form, "flag_hit.term_form")
        _non_empty(self.view_id, "flag_hit.view_id")
        if not isinstance(self.location, HitLocation):
            raise CodecError("flag_hit.location must be a HitLocation")


@dataclass(frozen=True)
class GroupCount:
    """One rollup count; each count carries its ordinal and quote_kind (D8)."""

    term_group_id: str
    count: int
    ordinal: int | None = None
    quote_kind: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.term_group_id, "group_count.term_group_id")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 0:
            raise CodecError("group_count.count must be an int >= 0")


@dataclass(frozen=True)
class FlagRollup:
    """D8 rollup: derived, recomputable, per view never across views, never a filter."""

    scope: RollupScope
    counts_by_group: list[GroupCount] = field(default_factory=list)
    quoted_counts_by_group: list[GroupCount] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RollupScope):
            raise CodecError(f"flag_rollup.scope must be a RollupScope, got {self.scope!r}")


@dataclass(frozen=True)
class FlagSection:
    """D8 reserved flag section: present-but-empty on every record and round-tripping."""

    terms: list[str] = field(default_factory=list)
    term_list_hash: str | None = None
    matcher_version: str | None = None
    flag_schema_version: str = FLAG_SCHEMA_VERSION
    hits: list[FlagHit] = field(default_factory=list)
    rollup: FlagRollup | None = None


@dataclass(frozen=True)
class RunRecord:
    """Run metadata (D6): the run record keeps cap id, cap value and declared size,
    so a raised cap is a different run. ``not_installed``/``unsupported`` are
    environmental and live here: re-running with an extra installed flips them
    without changing content.
    """

    run_id: str
    email_parser_version: str = EMAIL_PARSER_VERSION
    output_schema_version: str = OUTPUT_SCHEMA_VERSION
    cap_id: str | None = None
    cap_value_bytes: int | None = None
    declared_size_bytes: int | None = None
    environment: dict[str, str] = field(default_factory=dict)
    flags: FlagSection = field(default_factory=FlagSection)

    def __post_init__(self) -> None:
        _non_empty(self.run_id, "run_record.run_id")


@dataclass(frozen=True)
class EmailDocument:
    """One email record: container identity (D14) plus the per-axis evidence.

    ``container_hash`` addresses the file; ``content_fingerprint`` is separate and
    labeled (D14). Neither is "the" identity of the email.
    """

    container_kind: ContainerKind
    container_hash: str
    container_facts: ContainerFacts
    content_fingerprint: ContentFingerprint
    status: StatusOutcome
    headers: list[HeaderField] = field(default_factory=list)
    parts: list[PartRecord] = field(default_factory=list)
    attachments: list[AttachmentOccurrence] = field(default_factory=list)
    children: list[ChildLink] = field(default_factory=list)
    thread_edges: list[ThreadEdge] = field(default_factory=list)
    times: list[TimeEvent] = field(default_factory=list)
    same_message_candidates: list[SameMessageCandidate] = field(default_factory=list)
    classification_hint: ClassificationClaim | None = None
    run_record: RunRecord | None = None
    output_schema_version: str = OUTPUT_SCHEMA_VERSION
    flags: FlagSection = field(default_factory=FlagSection)

    def __post_init__(self) -> None:
        if not isinstance(self.container_kind, ContainerKind):
            raise CodecError(f"container_kind must be a ContainerKind, got {self.container_kind!r}")
        _non_empty(self.container_hash, "container_hash")
        if not isinstance(self.content_fingerprint, ContentFingerprint):
            raise CodecError("content_fingerprint must be a ContentFingerprint")
        if not isinstance(self.status, StatusOutcome):
            raise CodecError("status must be a StatusOutcome")


# --------------------------------------------------------------------------
# Codec entry points (the core codec is the only codec)
# --------------------------------------------------------------------------


def record_to_bytes(record: Any) -> bytes:
    """Encode through the core codec: versioned envelope + strict dataclass encoding."""
    return to_json(record, schema_version=SCHEMA_VERSION, indent=None).encode("utf-8")


def record_from_bytes(cls: type, payload: bytes) -> Any:
    """Decode through the core codec: unknown keys anywhere raise CodecError."""
    return from_json(
        cls,
        payload.decode("utf-8"),
        strict=True,
        schema_version=SCHEMA_VERSION,
        min_version=MIN_SUPPORTED_VERSION,
    )
