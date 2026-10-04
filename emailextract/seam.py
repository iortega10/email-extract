"""The matcher seam (design D8): a Protocol over ``(text, view_id, runs)``, and a trivial stub.

Term flagging is a **track S** concern (the shared matcher, ``docextract_core.match``, is D8's
destination and is **not built here**). What Phase 0 freezes is the **seam** -- the shape a matcher
consumes and the shape of what it returns -- so the later physical move is a move, not a rewrite.

The seam is ``(text, view_id, runs)``, bundled in :class:`MatchUnit` with the producer-shaped
locator a hit carries:

* **text** is one reading of one part (a body view or the header part) and **runs** are the
  caller-supplied **closable runs** -- the contiguous, same-quote-level spans of that reading --
  with their ``[start, end)`` offsets into ``text`` (contiguous from 0; the concatenation *is*
  ``text``). A plain body with no quoting is one run.
* **view_id** is which reading was scanned: ``plain``, ``html`` or ``headers``. A hit **names the
  view that fired**; an id outside the vocabulary is refused, never defaulted.
* a hit's **location** is email's own address space -- ``part`` / ``view`` / ``span`` / ``unit``
  (:class:`emailextract.model.HitLocation`) -- and is never a page, cell, sheet or slide (D8: those
  are the siblings' space).

One rule the seam carries because it is the point of D3:

* **``view.gap_closing_contiguous`` -- closing is contiguous.** word-extract *bridges* excluded
  text inside a unit; email must **not** bridge a quoted interruption. So closing is not a matcher
  constant: **the caller supplies the closable runs, and a match may not span a run boundary.** A
  term is searched *within* a run, never across one: the same text that matches as one run does not
  match when the caller splits it at a boundary.

A flag is a hit with its view named; the matcher **flags, never filters** -- there is no ``excluded``
field anywhere (:class:`~emailextract.model.FlagHit` has none, and neither do these records). Every
hit is stamped with ``matcher_version`` (this stub's own constant,
:data:`emailextract.versions.MATCHER_VERSION`) and the ``term_list_hash`` it was found under (D12: a
record is meaningless without its versions).

The stub (:class:`StubMatcher`) does the least that lets the contract be exercised: **whole-token
exact** match, no stemming, no synonyms, no scoring, no fuzzy matching. Frozen dataclasses over the
core codec, strict decoding, unknown keys refused, like every other record in this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Iterator, Protocol, Sequence, runtime_checkable

from docextract_core.codec import CodecError

from .ids import sha256_hex
from .model import FlagHit, HitLocation, MatchType
from .timeevent import Span
from .versions import MATCHER_VERSION

__all__ = [
    "MatchRules",
    "MatchUnit",
    "Matcher",
    "MatcherView",
    "StubMatcher",
    "TermHit",
    "TermList",
    "TextRun",
    "UnitLocation",
    "runs_from_texts",
    "term_list_hash",
]


class MatcherView(str, Enum):
    """Which reading of a part a match ran over (D8).

    A body alternative is its own evidence family and a flag in the header part is just another
    view (D2/D3). The vocabulary is closed: a value outside it is refused, never defaulted.
    """

    PLAIN = "plain"
    HTML = "html"
    HEADERS = "headers"


def _view(value: object, *, field_name: str) -> MatcherView:
    """Coerce ``value`` to a :class:`MatcherView`, or raise -- like every record's enum field."""
    if isinstance(value, MatcherView):
        return value
    try:
        return MatcherView(value)
    except ValueError:
        allowed = ", ".join(member.value for member in MatcherView)
        raise CodecError(f"seam.{field_name}: {value!r} is not one of: {allowed}") from None


def _match_type(value: object) -> MatchType:
    """Coerce ``value`` to a :class:`MatchType`, or raise."""
    if isinstance(value, MatchType):
        return value
    try:
        return MatchType(value)
    except ValueError:
        allowed = ", ".join(member.value for member in MatchType)
        raise CodecError(f"seam.match_type: {value!r} is not one of: {allowed}") from None


def term_list_hash(terms: Sequence[str]) -> str:
    """The hash of a term set (D8): order- and duplicate-independent, so same terms -> same hash."""
    canonical = "\n".join(sorted(set(terms)))
    return sha256_hex(canonical.encode("utf-8"))


@dataclass(frozen=True)
class TextRun:
    """One caller-supplied **closable run**: its ordinal in the unit and its ``[start, end)`` span.

    ``text`` is the run's characters and ``span`` its offsets into the unit's ``text``; the run's
    span must cover exactly its text. A unit's runs tile the unit text with no gap and no overlap.
    """

    ordinal: int
    text: str
    span: Span

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise CodecError(f"seam.text_run.ordinal: {self.ordinal!r} is not a 0-based ordinal")
        if not isinstance(self.text, str):
            raise CodecError("seam.text_run.text: a run's text is a string (it may be empty)")
        if not isinstance(self.span, Span):
            raise CodecError("seam.text_run.span: a run carries a Span")
        if self.span.end - self.span.start != len(self.text):
            raise CodecError(
                f"seam.text_run.span: {self.span} does not cover the run's {len(self.text)} char(s)"
            )


@dataclass(frozen=True)
class UnitLocation:
    """The producer-shaped locator a unit is attached to (D8): email's own address space.

    ``part`` is the content-addressed part locator the unit was read from, ``view`` which reading
    (mirroring :class:`MatcherView`), and ``unit`` the unit's ordinal within that part+view. Never a
    page, cell, sheet or slide -- those are the siblings' space and email cannot fabricate them.
    """

    part: str
    view: str
    unit: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.part, str) or not self.part:
            raise CodecError("seam.unit_location.part: a unit belongs to a part")
        if not isinstance(self.view, str) or not self.view:
            raise CodecError("seam.unit_location.view: a unit carries its view id")
        if self.unit is not None and (
            isinstance(self.unit, bool) or not isinstance(self.unit, int) or self.unit < 0
        ):
            raise CodecError("seam.unit_location.unit: an int >= 0 or None")


@dataclass(frozen=True)
class MatchUnit:
    """The seam: ``(text, view_id, runs)`` plus the locator the hits carry.

    ``text`` is one reading of one part and ``runs`` are its caller-supplied closable runs: they are
    contiguous from 0, ordinals run in order, and their texts concatenate to exactly ``text``. A
    caller with no quoting information passes one run over the whole text (:func:`runs_from_texts`).
    """

    view_id: MatcherView
    text: str
    runs: list[TextRun]
    location: UnitLocation

    def __post_init__(self) -> None:
        object.__setattr__(self, "view_id", _view(self.view_id, field_name="view_id"))
        if not isinstance(self.text, str):
            raise CodecError("seam.match_unit.text: a unit's text is a string")
        if not isinstance(self.location, UnitLocation):
            raise CodecError("seam.match_unit.location: a unit carries a UnitLocation")
        runs = list(self.runs)
        for run in runs:
            if not isinstance(run, TextRun):
                raise CodecError("seam.match_unit.runs: a unit's runs are TextRuns")
        if runs:
            ordinals = [run.ordinal for run in runs]
            if ordinals != list(range(len(runs))):
                raise CodecError(f"seam.match_unit.runs: ordinals are 0..n in order -- got {ordinals}")
            cursor = 0
            for run in runs:
                if run.span.start != cursor:
                    raise CodecError(
                        f"seam.match_unit.runs: run {run.ordinal} starts at {run.span.start}, not "
                        f"at {cursor} -- the runs must tile the text with no gap and no overlap"
                    )
                cursor = run.span.end
            if cursor != len(self.text):
                raise CodecError(
                    f"seam.match_unit.runs: the runs cover {cursor} char(s) but the text is "
                    f"{len(self.text)}"
                )
            joined = "".join(run.text for run in runs)
            if joined != self.text:
                raise CodecError("seam.match_unit.runs: the concatenated run texts must equal the text")
        elif self.text:
            raise CodecError(
                "seam.match_unit.runs: a non-empty text needs at least one run -- pass one run over "
                "the whole text (runs_from_texts)"
            )
        object.__setattr__(self, "runs", runs)

    def run_at(self, offset: int) -> TextRun | None:
        """The run the character at ``offset`` belongs to, or ``None`` if there is no run there."""
        for run in self.runs:
            if run.span.start <= offset < run.span.end:
                return run
        return None


@dataclass(frozen=True)
class MatchRules:
    """The rules a term search runs under (D8). Nothing here is a default the caller did not ask for.

    ``match_types`` is the D8 ``exact | synonym | stem`` vocabulary the caller permits;
    ``whole_token`` and ``case_sensitive`` say how a term is bounded. The stub honours ``whole_token``
    and ``case_sensitive`` and implements ``exact`` alone.
    """

    whole_token: bool = True
    case_sensitive: bool = True
    match_types: list[MatchType] = field(default_factory=lambda: [MatchType.EXACT])

    def __post_init__(self) -> None:
        if not isinstance(self.whole_token, bool):
            raise CodecError("seam.match_rules.whole_token must be bool")
        if not isinstance(self.case_sensitive, bool):
            raise CodecError("seam.match_rules.case_sensitive must be bool")
        object.__setattr__(self, "match_types", [_match_type(value) for value in self.match_types])


@dataclass(frozen=True)
class TermList:
    """The terms to flag, and the rules they are searched under (D8).

    There is no excluded view and no excluded field: what is scanned is the runs the caller passed,
    nothing else. The set is hashed for every hit (:func:`term_list_hash`).
    """

    terms: list[str]
    rules: MatchRules = field(default_factory=MatchRules)

    def __post_init__(self) -> None:
        terms = list(self.terms)
        for term in terms:
            if not isinstance(term, str) or not term:
                raise CodecError(f"seam.term_list.terms: {term!r} is not a non-empty string")
        object.__setattr__(self, "terms", terms)
        if not isinstance(self.rules, MatchRules):
            raise CodecError("seam.term_list.rules: a TermList carries MatchRules")

    def hash(self) -> str:
        """The ``term_list_hash`` of this term set."""
        return term_list_hash(self.terms)


@dataclass(frozen=True)
class TermHit:
    """One exact occurrence of a term in a unit (D8). It **states which view fired**.

    ``span`` is the ``[start, end)`` of the match in the unit's text and ``location`` the unit's own
    locator; :meth:`to_flag_hit` maps it into the D8 :class:`~emailextract.model.FlagHit` shape.
    """

    term: str
    match_type: MatchType
    view_id: MatcherView
    span: Span
    location: UnitLocation
    term_list_hash: str
    matcher_version: str = MATCHER_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.term, str) or not self.term:
            raise CodecError("seam.term_hit.term: a hit names the term it matched")
        object.__setattr__(self, "match_type", _match_type(self.match_type))
        object.__setattr__(self, "view_id", _view(self.view_id, field_name="view_id"))
        if not isinstance(self.span, Span):
            raise CodecError("seam.term_hit.span: a hit carries its Span")
        if not isinstance(self.location, UnitLocation):
            raise CodecError("seam.term_hit.location: a hit carries a UnitLocation")
        for name in ("term_list_hash", "matcher_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise CodecError(f"seam.term_hit.{name} must be a non-empty str")

    def to_flag_hit(
        self,
        *,
        term_group_id: str | None = None,
        quote_boundary_ordinal: int | None = None,
        quote_kind: str | None = None,
    ) -> FlagHit:
        """This hit as the D8 :class:`~emailextract.model.FlagHit` the manifest stores.

        ``term_group_id`` defaults to the matched term (the stub's term set is flat); the caller's
        registry supplies the real group. The location is email's own address space, never a page or
        a cell.
        """
        return FlagHit(
            term_group_id=term_group_id or self.term,
            term_form=self.term,
            match_type=self.match_type,
            location=HitLocation(
                part=self.location.part,
                view=self.location.view,
                span=self.span,
                unit=self.location.unit,
            ),
            view_id=self.view_id.value,
            quote_boundary_ordinal=quote_boundary_ordinal,
            quote_kind=quote_kind,
            matcher_version=self.matcher_version,
        )


@runtime_checkable
class Matcher(Protocol):
    """The matcher seam (D8). The physical home is track S; this Protocol is what Phase 0 freezes.

    A matcher scans one :class:`MatchUnit` -- the seam triple ``(text, view_id, runs)`` plus its
    locator -- under one :class:`TermList` and returns the :class:`TermHit` records it found. It
    flags, never filters, and it never invents a location the unit did not carry. A hit is searched
    **within** a run and never across a run boundary (``view.gap_closing_contiguous``).
    """

    def match(self, unit: MatchUnit, terms: TermList) -> list[TermHit]:
        """Return every hit ``terms`` produces in ``unit``, in terms order then left to right."""
        ...


def _token_character(character: str) -> bool:
    """Whether ``character`` is part of a whole token (alphanumeric or ``_``)."""
    return character.isalnum() or character == "_"


def _occurrences(haystack: str, needle: str, *, whole_token: bool) -> Iterator[int]:
    """Every start offset of ``needle`` in ``haystack``, whole-token-bounded when asked."""
    if not needle:
        return
    start = haystack.find(needle)
    while start != -1:
        if not whole_token:
            yield start
        else:
            before = haystack[start - 1] if start > 0 else ""
            end = start + len(needle)
            after = haystack[end] if end < len(haystack) else ""
            if not _token_character(before) and not _token_character(after):
                yield start
        start = haystack.find(needle, start + 1)


class StubMatcher:
    """The least matcher that exercises the contract: whole-token exact, nothing else (D8).

    No stemming, no synonyms, no case folding (unless the rules ask), no fuzzy matching, no score --
    each of those would be a decision the real matcher (track S) must make deliberately. A match is
    searched **within one run** and never spans a run boundary; hits come back in terms order, and
    within a term left to right by start offset.
    """

    #: The match types the stub implements; the real matcher may support more.
    SUPPORTED_MATCH_TYPES: tuple[MatchType, ...] = (MatchType.EXACT,)

    def match(self, unit: MatchUnit, terms: TermList) -> list[TermHit]:
        """Every whole-token occurrence of each term inside a single run, or nothing spanning runs."""
        unsupported = [
            match_type
            for match_type in terms.rules.match_types
            if match_type not in self.SUPPORTED_MATCH_TYPES
        ]
        if unsupported:
            names = ", ".join(match_type.value for match_type in unsupported)
            raise CodecError(f"the stub implements exact only; the rules ask for: {names}")
        digest = terms.hash()
        hits: list[TermHit] = []
        for term in terms.terms:
            for run in unit.runs:  # a match may not cross a run boundary: search each run alone
                if terms.rules.case_sensitive:
                    haystack, needle = run.text, term
                else:
                    haystack, needle = run.text.casefold(), term.casefold()
                for offset in _occurrences(haystack, needle, whole_token=terms.rules.whole_token):
                    local = run.span.start + offset
                    hits.append(
                        TermHit(
                            term=term,
                            match_type=MatchType.EXACT,
                            view_id=unit.view_id,
                            span=Span(local, local + len(term)),
                            location=unit.location,
                            term_list_hash=digest,
                        )
                    )
        return hits


def runs_from_texts(texts: Iterable[str]) -> list[TextRun]:
    """The runs of a unit: contiguous offsets over the concatenation of ``texts``."""
    runs: list[TextRun] = []
    cursor = 0
    for ordinal, text in enumerate(texts):
        if not isinstance(text, str):
            raise CodecError(f"seam.runs_from_texts: {text!r} is not a string")
        runs.append(TextRun(ordinal=ordinal, text=text, span=Span(cursor, cursor + len(text))))
        cursor += len(text)
    return runs
