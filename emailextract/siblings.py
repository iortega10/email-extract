"""Turn 0.5: the sibling contract -- discovery, the locator, and the child link (D5, D12).

Every package keeps its own store and the email store **references children by
content hash** (D5): sha256 is the join key, a thin *locator* points a hash at the
store root that holds it, and the child link is tri-state
(:class:`~emailextract.model.ChildLink`: ``resolved | store_absent | child_absent |
version_mismatch``). The manifest stays useful with every sibling store deleted --
filename, type, sha256 and size are the email side's own facts.

**Nothing here imports a sibling.** Discovery is ``importlib.util.find_spec``: a
sibling's presence is a question about the environment, and importing a package to
ask it would run its import side effects (and make "not installed" untestable).
A sibling that is not installed is an environmental status,
:func:`not_installed` (``Status.not_installed`` carrying ``needed_sibling``), not a
citation state.

**The citation has three buckets, never mixed** (D12):

* *email-extract's own* (:class:`ChildCitationVia`) -- ``attachment_id`` (the
  sha256), the ``occurrence``, the ``route`` and the child store;
* *verbatim passthrough* (:class:`ChildCitationChild`) -- the sibling's citation
  exactly as the child store wrote it, **an opaque payload**: never translated,
  renumbered or re-derived into email coordinates. A missing child makes this
  bucket ``unknown`` **whole** -- no field of it is partially filled;
* *stamped* (:class:`ChildCitationStamp`) -- ``sibling``,
  ``sibling_parser_version``, ``child_store_id``, ``child_store_revision``,
  ``core_version`` and the email-extract version that made the link.

A child's ``page_count``/``sheet_count`` are the *child's* facts
(:class:`SiblingDerivedFacts`), tri-state, and ``unknown`` with a closed
``sibling.*`` reason when no child store is reachable -- never copied from the
email side and never defaulted to zero.

This module is a **contract**: it is proven against a fake store written in the
tests. No real sibling is imported, called, installed or required, no attachment
is routed and no child is ever really extracted (design Open risk 1) -- Phase 2
does the routing, and this gives it a shape to check a real sibling against.
"""

from __future__ import annotations

import copy
import importlib.util
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from docextract_core.codec import CodecError

from .model import (
    AttachmentOccurrence,
    ChildLink,
    ChildLinkState,
    Status,
    StatusOutcome,
    TriState,
    TriValue,
)
from .versions import EMAIL_PARSER_VERSION

__all__ = [
    "CITATION_UNKNOWN_REASONS",
    "ROUTE_FORM",
    "ROUTE_WORD",
    "SIBLING_MODULES",
    "ChildCitation",
    "ChildCitationChild",
    "ChildCitationStamp",
    "ChildCitationVia",
    "ChildLinkResult",
    "ChildResult",
    "CitationChildState",
    "Locator",
    "SiblingDerivedFacts",
    "SiblingStore",
    "discovery",
    "is_installed",
    "link_child",
    "link_occurrence",
    "locate",
    "missing_siblings",
    "module_name",
    "not_installed",
    "same_content_hash",
]

# ---------------------------------------------------------------- the siblings

#: The sibling families this package routes a child to (D4), by route name:
#: ``PDF/XLSX -> form``, ``DOCX -> word``. The value is the import name.
SIBLING_MODULES: Mapping[str, str] = {"word": "wordextract", "form": "formextract"}

ROUTE_WORD: str = "word"
ROUTE_FORM: str = "form"

#: The closed ids an unknown child citation or a child count carries (D12;
#: the design's ``sibling.*`` gap-registry family). An unknown never invents one.
CITATION_UNKNOWN_REASONS: tuple[str, ...] = (
    "sibling.store_absent",
    "sibling.child_absent",
    "sibling.version_mismatch",
)

#: The state -> closed reason id map: the unknown is the *same* fact in the link,
#: the citation's child bucket and the child's counts.
_UNKNOWN_REASON: Mapping[ChildLinkState, str] = {
    ChildLinkState.STORE_ABSENT: "sibling.store_absent",
    ChildLinkState.CHILD_ABSENT: "sibling.child_absent",
    ChildLinkState.VERSION_MISMATCH: "sibling.version_mismatch",
}


def module_name(sibling: str) -> str:
    """The import name of a sibling family (``"word"`` -> ``"wordextract"``)."""
    try:
        return SIBLING_MODULES[sibling]
    except KeyError:
        raise ValueError(
            f"unknown sibling {sibling!r}; known: {sorted(SIBLING_MODULES)}"
        ) from None


def is_installed(sibling: str) -> bool:
    """Whether a sibling is importable -- asked with ``find_spec``, never an import.

    Importing a package to see whether it exists is the defect this avoids: it runs
    the package's import side effects and makes "not installed" untestable.
    """
    return importlib.util.find_spec(module_name(sibling)) is not None


def discovery() -> dict[str, bool]:
    """``{sibling: installed}`` for every family, in name order."""
    return {sibling: is_installed(sibling) for sibling in sorted(SIBLING_MODULES)}


def missing_siblings() -> tuple[str, ...]:
    """The siblings that are not importable here, in name order."""
    return tuple(sibling for sibling in sorted(SIBLING_MODULES) if not is_installed(sibling))


def not_installed(sibling: str) -> StatusOutcome:
    """The status for a routed child whose sibling is not installed (D4/D6).

    ``not_installed`` is **environmental**: it carries ``needed_sibling`` and takes
    no reason, and re-running with the extra installed flips it without changing
    the message's content.
    """
    return StatusOutcome(status=Status.NOT_INSTALLED, needed_sibling=sibling)


# --------------------------------------------------------------- the child shape


@dataclass(frozen=True)
class SiblingDerivedFacts:
    """The child's own facts (D4): ``sibling_derived``, never copied.

    A ``value`` is the sibling's count, trustworthy only with the stamp on the
    citation that carries it. ``absent`` says the child has no such count
    (word-extract has no pages); ``unknown`` says the child store could not be
    read, and carries one of :data:`CITATION_UNKNOWN_REASONS`. A count is never
    defaulted to zero, and a count is text in the tri-state's value slot.
    """

    page_count: TriValue = field(default_factory=TriValue)
    sheet_count: TriValue = field(default_factory=TriValue)

    def __post_init__(self) -> None:
        for name in ("page_count", "sheet_count"):
            value = getattr(self, name)
            if not isinstance(value, TriValue):
                raise CodecError(f"sibling_derived_facts.{name} must be a TriValue")
            if value.state is TriState.UNKNOWN and value.reason_id not in CITATION_UNKNOWN_REASONS:
                raise CodecError(
                    f"sibling_derived_facts.{name}: unknown reason {value.reason_id!r} is not "
                    f"one of: {CITATION_UNKNOWN_REASONS}"
                )


def _facts_unknown(reason_id: str) -> SiblingDerivedFacts:
    """Both counts unknown with the same closed reason: the whole child is unknown."""
    unknown = TriValue(state=TriState.UNKNOWN, reason_id=reason_id)
    return SiblingDerivedFacts(page_count=unknown, sheet_count=unknown)


@dataclass(frozen=True)
class ChildResult:
    """What a sibling's store holds for one extracted attachment (D5).

    Keyed by the attachment's sha256 (``attachment_id``). ``citation`` is the
    sibling's **own citation object, exactly as written** -- opaque to this
    package, kept verbatim by :class:`ChildCitationChild`; it is never read as
    email coordinates. The stamps identify the store and the code that wrote the
    result, so a link can be refused when the caller expects other versions.
    """

    attachment_id: str
    sibling: str
    sibling_parser_version: str
    child_store_id: str
    child_store_revision: str
    core_version: str
    citation: dict[str, Any] = field(default_factory=dict)
    facts: SiblingDerivedFacts = field(default_factory=SiblingDerivedFacts)

    def __post_init__(self) -> None:
        for name in (
            "attachment_id",
            "sibling",
            "sibling_parser_version",
            "child_store_id",
            "child_store_revision",
            "core_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise CodecError(f"child_result.{name} must be a non-empty str")
        if not isinstance(self.citation, dict):
            raise CodecError("child_result.citation must be a mapping (the sibling's own citation)")
        if not isinstance(self.facts, SiblingDerivedFacts):
            raise CodecError("child_result.facts must be a SiblingDerivedFacts")


# ------------------------------------------------------------ the citation


class CitationChildState(str, Enum):
    """Which of D12's two shapes the child bucket holds."""

    VERBATIM = "verbatim"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChildCitationVia:
    """Bucket (a): email-extract's own coordinates (D12)."""

    attachment_id: str
    occurrence: str
    route: str
    child_store: str | None = None

    def __post_init__(self) -> None:
        for name in ("attachment_id", "occurrence", "route"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise CodecError(f"child_citation.via.{name} must be a non-empty str")
        if self.child_store is not None and not self.child_store:
            raise CodecError("child_citation.via.child_store must be non-empty when present")


@dataclass(frozen=True)
class ChildCitationChild:
    """Bucket (b): the sibling's citation, verbatim, or unknown **whole** (D12).

    ``payload`` is the child store's citation object as written -- never
    translated, renumbered or re-derived into email coordinates. When the child is
    unknown the whole bucket is empty: ``payload`` is None and the only thing
    present is the closed ``reason_id``.
    """

    state: CitationChildState = CitationChildState.UNKNOWN
    payload: dict[str, Any] | None = None
    reason_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, CitationChildState):
            raise CodecError(f"child_citation.child.state must be a CitationChildState, got {self.state!r}")
        if self.state is CitationChildState.VERBATIM:
            if not isinstance(self.payload, dict):
                raise CodecError("child_citation.child: state=verbatim requires the sibling's payload")
            if self.reason_id is not None:
                raise CodecError("child_citation.child: state=verbatim carries no reason_id")
            # A frozen record must not alias the store's own mutable dict: copy at construction so a
            # later change to the sibling's citation object cannot change a linked citation (and the
            # bytes the email store holds). The copy is deep and keeps every key and value as written.
            object.__setattr__(self, "payload", copy.deepcopy(self.payload))
        else:
            if self.payload is not None:
                raise CodecError("child_citation.child: unknown is WHOLE, never partially filled")
            if self.reason_id not in CITATION_UNKNOWN_REASONS:
                raise CodecError(
                    f"child_citation.child: reason_id {self.reason_id!r} is not one of: "
                    f"{CITATION_UNKNOWN_REASONS}"
                )


@dataclass(frozen=True)
class ChildCitationStamp:
    """Bucket (c): the versions a citation is meaningless without (D12).

    Built from the store that was reached, plus the email-extract version that
    made the link. It is populated exactly when a store was reached -- with no
    store there is nothing to stamp.
    """

    sibling: str
    sibling_parser_version: str
    child_store_id: str
    child_store_revision: str
    core_version: str
    linked_by_email_parser_version: str

    def __post_init__(self) -> None:
        for name in (
            "sibling",
            "sibling_parser_version",
            "child_store_id",
            "child_store_revision",
            "core_version",
            "linked_by_email_parser_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise CodecError(f"child_citation.stamp.{name} must be a non-empty str")


@dataclass(frozen=True)
class ChildCitation:
    """D12's three-bucket citation: never mixed, never partially filled.

    The design states the shape as ``{via, child}``; ``stamp`` is the third bucket
    it names (the version stamp the other two are meaningless without), carried as
    its own field so the three stay disjoint. A citation is never merged with
    another: two occurrences of one file are two citations and a
    :func:`same_content_hash` boolean.
    """

    via: ChildCitationVia
    child: ChildCitationChild
    stamp: ChildCitationStamp | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.via, ChildCitationVia):
            raise CodecError("child_citation.via must be a ChildCitationVia")
        if not isinstance(self.child, ChildCitationChild):
            raise CodecError("child_citation.child must be a ChildCitationChild")
        if self.stamp is not None and not isinstance(self.stamp, ChildCitationStamp):
            raise CodecError("child_citation.stamp must be a ChildCitationStamp or None")
        if self.child.state is CitationChildState.VERBATIM and self.stamp is None:
            raise CodecError("child_citation: a verbatim child requires the stamp it came with")


def same_content_hash(left: ChildCitation, right: ChildCitation) -> bool:
    """D4/D12: two occurrences of one content hash -- storage dedupes, occurrence never does.

    Two versions of one *name* are two occurrences with two citations and this
    boolean ``False``; they are never merged.
    """
    return left.via.attachment_id == right.via.attachment_id


# ------------------------------------------------------------ the store seam


@runtime_checkable
class SiblingStore(Protocol):
    """What the locator and the resolver need from a child store (D5, D12).

    Attribute access and two methods, so a real sibling's query layer can satisfy
    it without importing anything of ours. ``read`` returns the child result for a
    sha256, or None when the store has no result for it; ``available`` says whether
    this configured root is actually reachable.
    """

    sibling: str
    sibling_parser_version: str
    child_store_id: str
    child_store_revision: str
    core_version: str

    def available(self) -> bool:
        """Whether this store root is reachable at all (a deleted store is not)."""

    def read(self, attachment_id: str) -> ChildResult | None:
        """The stored child result for this sha256, or None when there is none."""


@dataclass(frozen=True)
class Locator:
    """The thin locator (D5): a config of child-store roots, checked in order.

    At the scale target (about 25 documents) this is the whole "index"; a real
    index is a later optimization. The order is the contract: the first reachable
    store that has the child wins.
    """

    stores: tuple[SiblingStore, ...] = ()

    def reachable(self) -> tuple[SiblingStore, ...]:
        """The configured stores that are reachable, in configured order."""
        return tuple(store for store in self.stores if store.available())


def locate(locator: Locator, attachment_id: str) -> tuple[SiblingStore | None, ChildResult | None]:
    """The first reachable store holding this child, and the result it holds (D5)."""
    for store in locator.reachable():
        result = store.read(attachment_id)
        if result is not None:
            return store, result
    return None, None


@dataclass(frozen=True)
class ChildLinkResult:
    """One attachment's child link, its citation and the child's facts.

    The three records say the same thing from three sides and are held consistent
    here: a ``resolved`` link has a verbatim child bucket and the child's own
    counts; anything else has the child bucket unknown **whole** and the counts
    unknown with the same closed reason.
    """

    link: ChildLink
    citation: ChildCitation
    facts: SiblingDerivedFacts

    def __post_init__(self) -> None:
        if not isinstance(self.link, ChildLink):
            raise CodecError("child_link_result.link must be a ChildLink")
        if not isinstance(self.citation, ChildCitation):
            raise CodecError("child_link_result.citation must be a ChildCitation")
        if not isinstance(self.facts, SiblingDerivedFacts):
            raise CodecError("child_link_result.facts must be a SiblingDerivedFacts")
        if self.link.child_id != self.citation.via.attachment_id:
            raise CodecError("child_link_result: the link and the citation name different children")
        resolved = self.link.state is ChildLinkState.RESOLVED
        verbatim = self.citation.child.state is CitationChildState.VERBATIM
        if resolved is not verbatim:
            raise CodecError(
                "child_link_result: a resolved link has the verbatim child bucket and nothing "
                "else does"
            )
        if resolved:
            if self.citation.stamp is None:
                raise CodecError("child_link_result: a resolved link carries its stamp")
            return
        reason = _UNKNOWN_REASON[self.link.state]
        if self.citation.child.reason_id != reason:
            raise CodecError(
                f"child_link_result: {self.link.state.value} carries unknown({reason}), "
                f"got unknown({self.citation.child.reason_id})"
            )
        for name in ("page_count", "sheet_count"):
            value = getattr(self.facts, name)
            if value.state is not TriState.UNKNOWN or value.reason_id != reason:
                raise CodecError(
                    f"child_link_result: {name} is unknown({reason}) when the child is unknown"
                )


def _unknown_citation(
    attachment_id: str, occurrence: str, route: str, reason: str
) -> ChildCitation:
    return ChildCitation(
        via=ChildCitationVia(attachment_id=attachment_id, occurrence=occurrence, route=route),
        child=ChildCitationChild(state=CitationChildState.UNKNOWN, reason_id=reason),
    )


def link_child(
    attachment_id: str,
    *,
    occurrence: str,
    route: str,
    locator: Locator,
    expected_sibling_parser_version: str | None = None,
    expected_core_version: str | None = None,
) -> ChildLinkResult:
    """Link one attachment (by sha256) to its child result (D5, D12).

    ``store_absent`` means no configured store is reachable; ``child_absent``
    means a store is reachable but holds no result for this sha256;
    ``version_mismatch`` means the child exists but at a version the caller did not
    expect (``expected_version``/``found_version`` carry the pair that disagreed).
    A caller that finds the sibling not installed emits :func:`not_installed`
    instead -- that is an environment fact, not a citation state.
    """
    store, result = locate(locator, attachment_id)
    if store is None or result is None:
        state = ChildLinkState.CHILD_ABSENT if locator.reachable() else ChildLinkState.STORE_ABSENT
        reason = _UNKNOWN_REASON[state]
        return ChildLinkResult(
            link=ChildLink(state=state, child_id=attachment_id),
            citation=_unknown_citation(attachment_id, occurrence, route, reason),
            facts=_facts_unknown(reason),
        )

    mismatch = _version_mismatch(store, expected_sibling_parser_version, expected_core_version)
    store_id = store.child_store_id
    if mismatch is not None:
        expected, found = mismatch
        reason = _UNKNOWN_REASON[ChildLinkState.VERSION_MISMATCH]
        return ChildLinkResult(
            link=ChildLink(
                state=ChildLinkState.VERSION_MISMATCH,
                child_id=attachment_id,
                store_id=store_id,
                expected_version=expected,
                found_version=found,
            ),
            citation=ChildCitation(
                via=ChildCitationVia(
                    attachment_id=attachment_id,
                    occurrence=occurrence,
                    route=route,
                    child_store=store_id,
                ),
                child=ChildCitationChild(state=CitationChildState.UNKNOWN, reason_id=reason),
            ),
            facts=_facts_unknown(reason),
        )

    return ChildLinkResult(
        link=ChildLink(state=ChildLinkState.RESOLVED, child_id=attachment_id, store_id=store_id),
        citation=ChildCitation(
            via=ChildCitationVia(
                attachment_id=attachment_id,
                occurrence=occurrence,
                route=route,
                child_store=store_id,
            ),
            child=ChildCitationChild(state=CitationChildState.VERBATIM, payload=result.citation),
            stamp=ChildCitationStamp(
                sibling=store.sibling,
                sibling_parser_version=store.sibling_parser_version,
                child_store_id=store.child_store_id,
                child_store_revision=store.child_store_revision,
                core_version=store.core_version,
                linked_by_email_parser_version=EMAIL_PARSER_VERSION,
            ),
        ),
        facts=result.facts,
    )


def _version_mismatch(
    store: SiblingStore,
    expected_sibling_parser_version: str | None,
    expected_core_version: str | None,
) -> tuple[str, str] | None:
    """The first (expected, found) version pair the caller did not expect, or None.

    ``ChildLink`` carries one expected/found pair. Two versions can disagree; the
    sibling parser version is checked first because it is the one that decides what
    the child's facts mean.
    """
    pairs = (
        (expected_sibling_parser_version, store.sibling_parser_version),
        (expected_core_version, store.core_version),
    )
    for expected, found in pairs:
        if expected is not None and expected != found:
            return expected, found
    return None


def link_occurrence(
    occurrence: AttachmentOccurrence,
    *,
    route: str,
    locator: Locator,
    expected_sibling_parser_version: str | None = None,
    expected_core_version: str | None = None,
) -> ChildLinkResult:
    """:func:`link_child` for an attachment occurrence (D5, D12).

    The occurrence's own facts -- filename, type, sha256, size -- stay the email
    side's and are not part of the link; only the child bucket and the child's
    counts are unknown when no store is reachable, which is what keeps the
    manifest useful with every sibling store deleted.
    """
    return link_child(
        occurrence.attachment_id,
        occurrence=occurrence.occurrence_path,
        route=route,
        locator=locator,
        expected_sibling_parser_version=expected_sibling_parser_version,
        expected_core_version=expected_core_version,
    )
