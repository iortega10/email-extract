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

from .ids import NOT_BUILT_IN_PHASE1
from .timeevent import Span, TimeEvent, Trust
from .versions import EMAIL_PARSER_VERSION, FLAG_SCHEMA_VERSION, OUTPUT_SCHEMA_VERSION

__all__ = [
    "AXIS_IDS",
    "AttachmentOccurrence",
    "BodyView",
    "BoundaryKind",
    "BUILT_AXIS",
    "CapRecord",
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
    "QuoteBoundary",
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
    "UNRECOGNIZED",
    "ViewLevel",
    "axis_id",
    "built_axis",
    "not_built_in_phase1",
    "reason_required",
    "reasons_for",
    "record_from_bytes",
    "record_to_bytes",
    "type_disagreement",
    "type_family",
    "type_family_of",
    "type_unknown",
    "type_winner",
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


class BoundaryKind(str, Enum):
    """D3: what a quote boundary is; only ``quote`` is quoted history (decision 15).

    An inline forward, a signature, a list footer and an unrecognised boundary are
    recorded at level 0 and never advance the quote ordinal.
    """

    QUOTE = "quote"
    FORWARD = "forward"
    SIGNATURE = "signature"
    LIST_FOOTER = "list_footer"
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
    Status.SKIPPED: (
        "size_cap",
        "total_size_cap",
        "depth_cap",
        "part_count_cap",
        "header_bytes_cap",
    ),
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


# --------------------------------------------------------------------------
# Decision 6: the not-built idiom and the per-record axis fields
# --------------------------------------------------------------------------

#: The closed axis-id tuple (decision 6): a wildcard id is banned.
AXIS_IDS: Final[tuple[str, ...]] = (
    "attachment.status",
    "attachment.route",
    "document.times",
    "document.thread_edges",
    "document.children",
    "document.same_message_candidates",
)

#: The value a built axis carries: ``TriValue(state=VALUE, value=BUILT_AXIS)``.
BUILT_AXIS: Final[str] = "built"


def axis_id(value: str) -> str:
    """Return ``value`` when it is a member of the closed axis-id tuple, else raise."""
    if value not in AXIS_IDS:
        raise CodecError(f"axis id {value!r} is not one of the closed axis ids {AXIS_IDS}")
    return value


def not_built_in_phase1() -> TriValue:
    """The single encoding of "not built": ``TriValue(UNKNOWN, not_built_in_phase1)``."""
    return TriValue(state=TriState.UNKNOWN, reason_id=NOT_BUILT_IN_PHASE1)


def built_axis() -> TriValue:
    """The axis marker a present value field carries: ``TriValue(VALUE, "built")``."""
    return TriValue(state=TriState.VALUE, value=BUILT_AXIS)


def _axis_present(value: object) -> bool:
    """Whether a value field carries something: a non-``None`` scalar, or a non-empty list."""
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return bool(value)
    return True


def _check_axis_pair(value: object, axis: object, *, value_name: str, axis_name: str) -> None:
    """Decision 6's pairing invariant (I3/I4), enforced at construction.

    A value field and its axis field agree in exactly one of two ways and nothing
    else: a **present** value carries ``TriValue(VALUE, BUILT_AXIS)``, and a value
    that is **not present** (``None``, or a genuinely empty list) carries
    ``UNKNOWN(reason)`` -- ``not_built_in_phase1`` in a Phase 1 build, or another
    reason for a consulted-and-unknown axis. The rule is structural and never
    depends on the current phase: I2 is what a Phase 1 build *does*, not what the
    contract forbids. ``None`` (no such axis, or the input did not exercise the
    field) and an empty list (genuinely empty) both keep their single meaning and
    are never the encoding of "not built"; a union ``X | NotBuilt`` is not used,
    because the core codec decodes a union by its first non-``None`` member and
    would not round-trip (see :mod:`emailextract.ids`).
    """
    if not isinstance(axis, TriValue):
        raise CodecError(f"{axis_name} must be a TriValue, got {axis!r}")
    if _axis_present(value):
        if axis.state is not TriState.VALUE or axis.value != BUILT_AXIS:
            raise CodecError(
                f"{value_name} is set, so {axis_name} must be "
                f"TriValue(state=value, value={BUILT_AXIS!r}); got {axis!r} -- a present "
                "value and the not-built marker are mutually exclusive"
            )
    elif axis.state is not TriState.UNKNOWN:
        raise CodecError(
            f"{value_name} is not set, so {axis_name} must be "
            f"TriValue(state=unknown, reason_id=...); got {axis!r} -- neither None nor an "
            "empty list is ever the encoding of 'not built'"
        )


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


#: The magic verdict's sentinel for "consulted and nothing matched" (decision 7): a
#: closed value, never ``UNKNOWN``, so a consulted-and-clean part is not confused
#: with a part nothing looked at.
UNRECOGNIZED: Final[str] = "unrecognized"


def type_family(token: str) -> str | None:
    """The media-type family a verdict value names, or ``None`` when it names none.

    A MIME type reduces to its subtype (``application/pdf`` -> ``pdf``,
    ``text/plain`` -> ``plain``); a short magic name is already a family
    (``pdf`` -> ``pdf``). Parameters are dropped, and the closed
    ``UNRECOGNIZED`` sentinel names no family, so it never fires a disagreement and
    never supplies a winner. A pure function over a string: it parses no bytes.
    """
    if not isinstance(token, str):
        raise CodecError(f"type family: {token!r} is not a str")
    head = token.split(";", 1)[0].strip().lower()
    if not head or head == UNRECOGNIZED:
        return None
    return head.rsplit("/", 1)[-1] if "/" in head else head


def type_family_of(verdict: TriValue) -> str | None:
    """A verdict's media-type family when ``state = VALUE``; else ``None`` (D4)."""
    if not isinstance(verdict, TriValue):
        raise CodecError(f"type family: {verdict!r} is not a TriValue")
    if verdict.state is not TriState.VALUE:
        return None
    return type_family(verdict.value)  # type: ignore[arg-type]


def type_disagreement(*verdicts: TriValue) -> bool:
    """``attach.type_disagreement`` (decision 6): two families, at least.

    True iff at least two verdicts are in state ``VALUE`` with a media-type family
    and the set of families has size >= 2. ``UNRECOGNIZED`` and ``UNKNOWN``
    contribute no family and so never fire it.
    """
    families = {
        family for verdict in verdicts if (family := type_family_of(verdict)) is not None
    }
    return len(families) >= 2


def type_unknown(*verdicts: TriValue) -> bool:
    """``attach.type_unknown`` (decision 6): true iff no verdict yields a family."""
    return all(type_family_of(verdict) is None for verdict in verdicts)


def type_winner(
    declared_mime: TriValue,
    magic: TriValue,
    container_introspection: TriValue,
) -> TypeVerdictSource | None:
    """The winning verdict source: ``magic`` over ``declared_mime`` over introspection.

    The first verdict, in that priority order, that names a media-type family wins
    (decision 7: bytes beat claims), so a consulted ``UNRECOGNIZED`` magic yields no
    winner. ``None`` when no verdict names a family (``attach.type_unknown``).
    """
    for source, verdict in (
        (TypeVerdictSource.MAGIC, magic),
        (TypeVerdictSource.DECLARED_MIME, declared_mime),
        (TypeVerdictSource.CONTAINER_INTROSPECTION, container_introspection),
    ):
        if type_family_of(verdict) is not None:
            return source
    return None


@dataclass(frozen=True)
class TypeVerdicts:
    """The three type verdicts plus winner plus disagreement (Turn 0.1; decision 6).

    Each verdict is a :class:`TriValue` (design D4: ``value | unknown``). A verdict
    consulted with nothing matching is ``VALUE(UNRECOGNIZED)``; not computed (a
    zero-length part, a cap hit, a decode failure) is ``UNKNOWN(reason_id)``; the
    container introspection is ``UNKNOWN(not_built_in_phase1)`` until Phase 2.
    """

    declared_mime: TriValue = field(default_factory=TriValue)
    magic: TriValue = field(default_factory=TriValue)
    container_introspection: TriValue = field(default_factory=TriValue)
    winner: TypeVerdictSource | None = None
    disagreement: bool = False

    def __post_init__(self) -> None:
        for name in ("declared_mime", "magic", "container_introspection"):
            verdict = getattr(self, name)
            if not isinstance(verdict, TriValue):
                raise CodecError(f"type_verdicts.{name} must be a TriValue, got {verdict!r}")
        if not isinstance(self.disagreement, bool):
            raise CodecError("type_verdicts.disagreement must be bool")
        if self.winner is not None:
            if not isinstance(self.winner, TypeVerdictSource):
                raise CodecError(
                    f"type_verdicts.winner must be a TypeVerdictSource, got {self.winner!r}"
                )
            if getattr(self, self.winner.value).state is not TriState.VALUE:
                raise CodecError(
                    f"type_verdicts: winner {self.winner.value!r} names no known verdict"
                )


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
    """One node of the parts tree. ``part_id`` is a **stable, content-addressed** id.

    It is ``ids.part_id(container_hash, raw span, content hash)``: identical for
    identical bytes at the same tree position, unique within the document and
    independent of the non-stable ``1.2.3`` locator, which renumbers when a sibling
    is inserted (Turn 1.9; build-spec "part ids are content-addressed").
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
class QuoteBoundary:
    """One quote boundary in one body view (D3; decision 2).

    ``rule_id`` names the table rule that fired, ``kind`` what it found, ``span`` the
    view's code points it covers and ``prefix_depth`` the ``>``-family depth **per
    line** (never averaged into a per-view scalar). Only ``kind = quote`` advances
    ``ordinal`` (the rank within the view): a ``forward``, ``signature``,
    ``list_footer`` or ``unknown`` boundary carries ordinal 0 (or None) at level 0.
    """

    rule_id: str
    kind: BoundaryKind
    span: Span
    ordinal: int | None = None
    prefix_depth: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        _non_empty(self.rule_id, "quote_boundary.rule_id")
        if not isinstance(self.kind, BoundaryKind):
            raise CodecError(f"quote_boundary.kind must be a BoundaryKind, got {self.kind!r}")
        if not isinstance(self.span, Span):
            raise CodecError(f"quote_boundary.span must be a Span, got {self.span!r}")
        if self.ordinal is not None and (
            isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int)
        ):
            raise CodecError("quote_boundary.ordinal must be an int or None")
        if self.kind is BoundaryKind.QUOTE:
            if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal < 1:
                raise CodecError(
                    "quote_boundary: a quote boundary advances the ordinal, so its ordinal is >= 1"
                )
        elif self.ordinal not in (0, None):
            raise CodecError(
                f"quote_boundary: only kind=quote advances the ordinal; {self.kind.value!r} "
                f"carries ordinal 0 or None, got {self.ordinal!r}"
            )
        for depth in self.prefix_depth:
            if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
                raise CodecError(f"quote_boundary.prefix_depth must be ints >= 0, got {depth!r}")


@dataclass(frozen=True)
class ViewLevel:
    """One body view's resolved quote level and the rule that resolved it (decision 2).

    ``quote_level`` is a **derived rank** (``level = ordinal`` where a structural
    quote rule fired in the span, else ``level = prefix_depth``); it carries its
    resolution ``rule_id`` so no consumer has to re-derive it, and nothing may
    threshold its magnitude. ``disagreement`` is ``view.quote_level_disagreement``:
    recorded iff a non-zero prefix depth and a structural quote ordinal resolve to
    different ranks on the same span.
    """

    view_id: str
    span: Span
    quote_level: int
    resolution_rule_id: str
    disagreement: bool = False

    def __post_init__(self) -> None:
        _non_empty(self.view_id, "view_level.view_id")
        if not isinstance(self.span, Span):
            raise CodecError(f"view_level.span must be a Span, got {self.span!r}")
        if isinstance(self.quote_level, bool) or not isinstance(self.quote_level, int):
            raise CodecError("view_level.quote_level must be an int (a derived rank)")
        _non_empty(self.resolution_rule_id, "view_level.resolution_rule_id")
        if not isinstance(self.disagreement, bool):
            raise CodecError("view_level.disagreement must be bool")


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
    status_axis: TriValue = field(default_factory=not_built_in_phase1)
    filename_raw: str | None = None
    filename_decoded: TriValue = field(default_factory=TriValue)
    cid: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    route: str | None = None
    route_axis: TriValue = field(default_factory=not_built_in_phase1)
    encoding_source: EncodingSource | None = None
    decode_chain: DecodeChain = field(default_factory=DecodeChain)
    decorative_hint: DecorativeHint = field(default_factory=DecorativeHint)
    type_verdicts: TypeVerdicts | None = None
    flags: "FlagSection" = field(default_factory=lambda: FlagSection())

    def __post_init__(self) -> None:
        _non_empty(self.attachment_id, "attachment_occurrence.attachment_id")
        _non_empty(self.occurrence_path, "attachment_occurrence.occurrence_path")
        _non_empty(self.part_id, "attachment_occurrence.part_id")
        _check_axis_pair(
            self.status, self.status_axis, value_name="status", axis_name="status_axis"
        )
        _check_axis_pair(self.route, self.route_axis, value_name="route", axis_name="route_axis")


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
class CapRecord:
    """One structural cap a run hit (decision 6, "not merged: caps").

    ``cap_id`` names the cap, ``cap_value_bytes`` the value the caller set and
    ``declared_size_bytes`` the declared size that exceeded it. Phase 0 could record
    only one; a run that hits depth and total bytes records both.
    """

    cap_id: str
    cap_value_bytes: int
    declared_size_bytes: int | None = None

    def __post_init__(self) -> None:
        _non_empty(self.cap_id, "cap_record.cap_id")
        if isinstance(self.cap_value_bytes, bool) or not isinstance(self.cap_value_bytes, int):
            raise CodecError("cap_record.cap_value_bytes must be an int")
        if self.cap_value_bytes < 0:
            raise CodecError("cap_record.cap_value_bytes must be >= 0")
        if self.declared_size_bytes is not None:
            if isinstance(self.declared_size_bytes, bool) or not isinstance(
                self.declared_size_bytes, int
            ):
                raise CodecError("cap_record.declared_size_bytes must be an int or None")
            if self.declared_size_bytes < 0:
                raise CodecError("cap_record.declared_size_bytes must be >= 0")


@dataclass(frozen=True)
class RunRecord:
    """Run metadata (D6): the run record keeps **every** cap it hit, so a raised cap is
    a different run. ``not_installed``/``unsupported`` are environmental and live here:
    re-running with an extra installed flips them without changing content.

    Migrated in Turn 1.0b: the single ``cap_id``/``cap_value_bytes``/
    ``declared_size_bytes`` triple is now a list of :class:`CapRecord`, each carrying
    those three members' meaning; a run that hit one cap (the only shape Phase 0 could
    produce) is ``caps=[CapRecord(cap_id=..., cap_value_bytes=..., declared_size_bytes=...)]``.

    ``projection_versions`` (Turn 1.9) names the projection that produced each derived
    view -- keyed by the version constant's own name (``TEXTMODEL_VERSION``,
    ``TEXTPART_VERSION``, ``HEADERTEXT_VERSION``, ``HTMLTEXT_VERSION``,
    ``DECODE_CHAIN_VERSION``, ``QUOTE_RULES_VERSION``) -- so a consumer reading a
    stored record knows what rendered it. They are behaviour, so they are also part
    of the document artifact's key.
    """

    run_id: str
    email_parser_version: str = EMAIL_PARSER_VERSION
    output_schema_version: str = OUTPUT_SCHEMA_VERSION
    caps: list[CapRecord] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    projection_versions: dict[str, str] = field(default_factory=dict)
    flags: FlagSection = field(default_factory=FlagSection)

    def __post_init__(self) -> None:
        _non_empty(self.run_id, "run_record.run_id")
        for cap in self.caps:
            if not isinstance(cap, CapRecord):
                raise CodecError(f"run_record.caps must hold CapRecords, got {cap!r}")
        for name, value in self.projection_versions.items():
            _non_empty(name, "run_record.projection_versions key")
            _non_empty(value, f"run_record.projection_versions[{name!r}]")


@dataclass(frozen=True)
class EmailDocument:
    """One email record: container identity (D14) plus the per-axis evidence.

    ``container_hash`` addresses the file; ``content_fingerprint`` is separate and
    labeled (D14). Neither is "the" identity of the email. **No body text is stored
    here** (Turn 1.9): a view is derived on demand from the container bytes, and
    what the record keeps is the per-view evidence about it (``quote_boundaries``
    and ``view_levels``), never the text itself.
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
    children_axis: TriValue = field(default_factory=not_built_in_phase1)
    thread_edges: list[ThreadEdge] = field(default_factory=list)
    thread_edges_axis: TriValue = field(default_factory=not_built_in_phase1)
    times: list[TimeEvent] = field(default_factory=list)
    times_axis: TriValue = field(default_factory=not_built_in_phase1)
    same_message_candidates: list[SameMessageCandidate] = field(default_factory=list)
    same_message_candidates_axis: TriValue = field(default_factory=not_built_in_phase1)
    quote_boundaries: list[QuoteBoundary] = field(default_factory=list)
    view_levels: list[ViewLevel] = field(default_factory=list)
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
        for boundary in self.quote_boundaries:
            if not isinstance(boundary, QuoteBoundary):
                raise CodecError(f"quote_boundaries must hold QuoteBoundaries, got {boundary!r}")
        for level in self.view_levels:
            if not isinstance(level, ViewLevel):
                raise CodecError(f"view_levels must hold ViewLevels, got {level!r}")
        for value_name, axis_name in (
            ("times", "times_axis"),
            ("thread_edges", "thread_edges_axis"),
            ("children", "children_axis"),
            ("same_message_candidates", "same_message_candidates_axis"),
        ):
            _check_axis_pair(
                getattr(self, value_name),
                getattr(self, axis_name),
                value_name=value_name,
                axis_name=axis_name,
            )


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
