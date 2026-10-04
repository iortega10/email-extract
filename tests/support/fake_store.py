"""TEST-ONLY fake sibling store (build spec, Turn 0.5).

A tiny in-test store implementing the child-result shape and
:class:`emailextract.siblings.SiblingStore`: a mapping from an attachment's
sha256 to its :class:`~emailextract.siblings.ChildResult`, plus the store's own
stamps. It imports **no sibling** -- that is the whole point of Turn 0.5's scope
line: the contract is proven against a fake, and Phase 2 checks a real sibling
against it (design Open risk 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from emailextract.model import TriState, TriValue
from emailextract.siblings import ChildResult, SiblingDerivedFacts


def count(value: int | None) -> TriValue:
    """A child's count as a tri-state: the child's number, or absent when it has none."""
    if value is None:
        return TriValue()
    return TriValue(state=TriState.VALUE, value=str(value))


@dataclass
class FakeSiblingStore:
    """One fake child store: the store's stamps, a reachability flag and the results.

    ``present=False`` models a **deleted** store root: it still holds results, but
    :meth:`available` says it is not reachable, which is what the locator checks
    (so "deleted" is distinct from "this store has no entry for that hash").
    """

    sibling: str = "word"
    sibling_parser_version: str = "1"
    child_store_id: str = "fake-child-store"
    child_store_revision: str = "1"
    core_version: str = "0.1.0"
    present: bool = True
    results: dict[str, ChildResult] = field(default_factory=dict)

    def available(self) -> bool:
        """Whether this store root is reachable; ``present=False`` is a deleted store."""
        return self.present

    def read(self, attachment_id: str) -> ChildResult | None:
        """The stored result for this sha256, or None when the store has no entry."""
        return self.results.get(attachment_id)

    def add(
        self,
        attachment_id: str,
        *,
        citation: dict[str, Any] | None = None,
        page_count: int | None = None,
        sheet_count: int | None = None,
    ) -> ChildResult:
        """Store one child result under ``attachment_id`` (the attachment's sha256)."""
        result = ChildResult(
            attachment_id=attachment_id,
            sibling=self.sibling,
            sibling_parser_version=self.sibling_parser_version,
            child_store_id=self.child_store_id,
            child_store_revision=self.child_store_revision,
            core_version=self.core_version,
            citation={} if citation is None else citation,
            facts=SiblingDerivedFacts(
                page_count=count(page_count), sheet_count=count(sheet_count)
            ),
        )
        self.results[attachment_id] = result
        return result
