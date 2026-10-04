"""The L1 exact oracle: the skeleton walker's output against the sidecar's labels (Turn 0.4).

L1 is the cheapest level in the eval ladder (D11): the facts a reader can measure from the
fixture bytes with the phase-0 components that exist. Here that is the **skeleton walker**
(``emailextract.walk``): ``container.sha256``, ``container.size_bytes``, ``headers.fields``,
``part.tree``, ``part.regions``, ``part.gaps``, ``body.preamble_epilogue``,
``body.content_sha256`` and ``decode.chain``. Each is measured from the walker's result and
compared, by equality, with the hand-typed value in the sidecar beside the fixture.

A fact whose phase has not shipped (``attach.manifest``, ``body.selection``,
``headers.decoded``, ``gaps.later``, every ``time.*`` fact, ``thread.claims``) is
**declared** in :data:`FACTS` with its phase and no measurer, so a sidecar labelling it is
reported ``not_yet`` with that phase -- never skipped silently. A label naming a fact the
oracle does not model at all is a hard failure (:class:`OracleError`), because a green run
over an unmodelled label would mean nothing.

The independence rule (D11): the labels were typed from the design rules and the fixture's
declared shape, never read out of the walker. So where a label and the walker disagree the
oracle **reports a mismatch** -- it is a finding about one of the two sides, never something
to reconcile by editing a label (``tests/test_label_structure.py`` and the Turn 0.4 report
carry the disagreements found over the committed corpus). ``emailextract.evals.labels`` still
imports nothing from this package; only this module imports the walker.

The oracle measures two facts about the labels rather than the message:

* ``container.sha256`` and ``container.size_bytes`` read the bytes and the walker's own hash;
* ``body.preamble_epilogue`` is a **sparse** fact -- a sidecar names only the parts it wants
  to assert (a leaf cannot hold preamble or epilogue bytes), so the comparison here is
  "every asserted row is right, and no part with non-zero preamble/epilogue is left out",
  not plain equality. This matches the convention the Turn 0.3 sidecars use
  (``plain_simple`` asserts only part ``1`` while ``preamble_epilogue`` asserts two parts);
* ``labels.undetermined`` is a **harness** fact: it names the questions the labels leave
  open, so this oracle measures it against the sidecar's own list (the structural tests and
  ``docs/design/label-questions.md`` decide whether the entries are shaped right).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ..container import EmlContainer
from ..walk import WalkResult, walk
from .labels import DEFAULT_FIXTURES, Fact, Sidecar, load_sidecar, load_sidecars

__all__ = [
    "CURRENT_PHASE",
    "FACTS",
    "FACT_PHASES",
    "Measured",
    "Measure",
    "OracleError",
    "Outcome",
    "Report",
    "Status",
    "check",
    "check_all",
    "check_path",
]

#: The phase this package claims to be at. Bumping it is what turns "not yet measurable"
#: facts into facts the gate compares, and it moves with the build, in the same commit as
#: the code that makes them measurable.
CURRENT_PHASE = 0


def _span(raw_span) -> list[int]:
    """``[offset, length]`` -- the shape every span takes in a sidecar."""
    return [raw_span.offset, raw_span.length]


# ------------------------------------------------------------------ measuring


@dataclass(frozen=True)
class Measured:
    """One fixture, walked once, ready to be measured fact by fact.

    ``result`` is the walker's output, or ``None`` when walking raised: a broken
    measurement is reported ``unmeasurable`` per fact, never allowed to escape as a crash.
    """

    sidecar: Sidecar
    result: WalkResult | None
    problem: str | None = None

    def walked(self) -> WalkResult:
        """The walker's result, or raise the failure walking produced (reported per fact)."""
        if self.result is None:
            raise RuntimeError(self.problem or "the walker produced no result")
        return self.result

    @property
    def parts(self):
        return self.walked().parts


def _container_sha256(measured: Measured) -> str:
    """The message id the walker measured: sha256 over the raw container bytes (D14)."""
    return measured.walked().container_hash


def _container_size_bytes(measured: Measured) -> int:
    """The address space every recorded span points into."""
    return measured.walked().total_bytes


def _headers_fields(measured: Measured) -> list[list[Any]]:
    """The top-level part's header fields, in order: ordinal, name, verbatim value, status, spans."""
    parts = measured.parts
    fields = parts[0].header_fields if parts else []
    return [
        [
            item.ordinal,
            item.name,
            item.raw_value,
            item.parse_status,
            _span(item.name_span),
            _span(item.value_span),
            _span(item.raw_span),
        ]
        for item in fields
    ]


def _part_tree(measured: Measured) -> list[list[Any]]:
    """Every part: path, parent path, content type, raw span, headers span, body span."""
    return [
        [
            part.path,
            part.parent_path,
            part.content_type,
            _span(part.raw_span),
            _span(part.headers_span),
            _span(part.body_span),
        ]
        for part in measured.parts
    ]


def _part_regions(measured: Measured) -> list[list[Any]]:
    """Every accounted region: kind, path, span (the regions tile the message, D9)."""
    return [[region.kind, region.path, _span(region.span)] for region in measured.walked().regions]


def _part_gaps(measured: Measured) -> list[list[Any]]:
    """Per part, the gap ids the walker recorded, in first-seen order."""
    return [[part.path, list(part.gaps)] for part in measured.parts]


def _preamble_epilogue(measured: Measured) -> list[list[Any]]:
    """Per part, the preamble and epilogue byte counts the walker accounted for."""
    derived = {
        region.path: [0, 0] for region in measured.walked().regions
    }
    for region in measured.walked().regions:
        if region.kind == "preamble":
            derived[region.path][0] += region.span.length
        elif region.kind == "epilogue":
            derived[region.path][1] += region.span.length
    return [[part.path, derived[part.path][0], derived[part.path][1]] for part in measured.parts]


def _decode_chain(measured: Measured) -> list[list[Any]]:
    """Per part: path, declared/used CTE, declared/used charset, fallback_fired, encoding source."""
    return [
        [
            part.path,
            part.decode_chain.declared_cte,
            part.decode_chain.declared_charset,
            part.decode_chain.used_cte,
            part.decode_chain.used_charset,
            part.decode_chain.fallback_fired,
            part.encoding_source.value if part.encoding_source is not None else None,
        ]
        for part in measured.parts
    ]


def _body_content_sha256(measured: Measured) -> list[list[Any]]:
    """Per leaf part with a transfer-decoded body, the sha256 of those bytes."""
    return [
        [part.path, part.body_sha256] for part in measured.parts if part.body_sha256 is not None
    ]


def _labels_undetermined(measured: Measured) -> Any:
    """The labels' own open questions: measured against themselves (a harness fact, see module doc)."""
    return measured.sidecar.facts["labels.undetermined"].value


# ----------------------------------------------------------- comparison rules


def _equal(expected: Any, actual: Any) -> bool:
    return expected == actual


def _sparse_rows(expected: Any, actual: Any) -> bool:
    """``body.preamble_epilogue``: the label asserts a subset, and no non-zero part is omitted.

    The sidecars name only the parts whose preamble/epilogue they want to assert (a leaf
    part cannot hold either), so plain equality would call every such label a mismatch. The
    rule is the one the Turn 0.3 sidecars were written to: each row the label names must be
    right, and every part the walker measured a non-zero count for must be named.
    """
    if not isinstance(expected, list) or not isinstance(actual, list):
        return expected == actual
    derived = {row[0]: (row[1], row[2]) for row in actual}
    asserted = set()
    for row in expected:
        path = row[0]
        if derived.get(path) != (row[1], row[2]):
            return False
        asserted.add(path)
    return all(
        not (pre or epi) or path in asserted for path, (pre, epi) in derived.items()
    )


# ------------------------------------------------------------- the registry


@dataclass(frozen=True)
class Measure:
    """How (and when) one fact is measured.

    ``function`` is absent for a fact whose phase has not arrived: the fact is still
    *declared*, with its phase, so a sidecar labelling it is checked for agreement instead
    of being skipped, and so a later phase cannot silently forget it. ``compare`` defaults
    to equality; only a fact whose sidecar convention is not plain equality overrides it.
    """

    phase: int
    function: Callable[[Measured], Any] | None = None
    compare: Callable[[Any, Any], bool] = _equal
    note: str | None = None


#: The published fact ids and the phase each becomes checkable at -- the one place allowed
#: to decide that. A label naming an id that is not here is a hard failure (see
#: :func:`check`), not a skipped fact. Kept in one block so the fact list reads as a list.
FACTS: Mapping[str, Measure] = MappingProxyType(
    {
        # Phase 0: what the skeleton walker measures today (D2/D9/D14).
        "container.sha256": Measure(0, _container_sha256),
        "container.size_bytes": Measure(0, _container_size_bytes),
        "headers.fields": Measure(0, _headers_fields),
        "part.tree": Measure(0, _part_tree),
        "part.regions": Measure(0, _part_regions),
        "part.gaps": Measure(0, _part_gaps),
        "body.preamble_epilogue": Measure(
            0,
            _preamble_epilogue,
            compare=_sparse_rows,
            note="[[path, preamble_bytes, epilogue_bytes]]; the label may name a subset "
            "(a leaf cannot hold either), but every non-zero part must be named",
        ),
        "decode.chain": Measure(0, _decode_chain),
        "body.content_sha256": Measure(0, _body_content_sha256),
        # A harness fact, not a message fact: the questions the labels leave open. Labelled
        # phase 0 by the sidecars and measured against themselves; the structure tests and
        # docs/design/label-questions.md own whether the entries are shaped right.
        "labels.undetermined": Measure(
            0,
            _labels_undetermined,
            note="[['<fact id>', '<locator>', '<what is undecided>']] the questions this "
            "sidecar does not settle -- a harness fact (the labels' own review)",
        ),
        # Phase 1: the parser's facts (identity, then body views and the attachment manifest).
        "attach.manifest": Measure(
            1,
            note="[[part, filename, declared_mime, cid, disposition, transfer_encoding, "
            "content_sha256, size]] the attachment occurrences (D4; needs the parser)",
        ),
        "body.selection": Measure(
            1,
            note="[[part, 'selected'|'alternative_not_selected'|'n/a']] the recorded "
            "alternative display rule (D3/D16; needs the parser)",
        ),
        "headers.decoded": Measure(
            1, note="[[ordinal, decoded_text]] the RFC 2047-decoded header values (needs the parser)"
        ),
        "gaps.later": Measure(
            1,
            note="[[gap_id, locator, phase, reason]] gaps a later phase records, named so a "
            "later phase cannot mistake silence for agreement",
        ),
        # Phase 1: the parser's fact ids (Turn 1.0b declaration). Every one is declared
        # here at phase 1 with its exact value shape and **no measurer** until its turn
        # ships, so a sidecar that labels it is reported ``not_yet`` (CURRENT_PHASE is 0)
        # instead of being skipped, and an unmodelled label is still a hard failure.
        "document.axes": Measure(
            1,
            note="[[axis_id, state, reason_id | null], ...] one row per axis the record carries; "
            "axis_id is one of attachment.status/attachment.route/document.times/"
            "document.thread_edges/document.children/document.same_message_candidates (a wildcard "
            "id is banned); state is value|absent|unknown; reason_id is not_built_in_phase1 or "
            "'built' when state=unknown, else null",
        ),
        "headers.projection": Measure(
            1,
            note="[[ordinal, name, raw_value, parsed_kind, parsed_value], ...] raw beside parsed, "
            "one row per field; the raw value keeps its folds (latin-1 view); parsed_kind is "
            "text|address_list|date_time|message_id|message_id_list|unparsed; parsed_value is null "
            "where parsed_kind=unparsed",
        ),
        "headers.addresses": Measure(
            1,
            note="[[ordinal, field_name, [[raw_offset, raw_length, display_name, addr_spec, state, "
            "reason_id], ...]], ...]; raw spans are BYTES into the raw message; state is "
            "parsed|group|unparsed; a group's members are the nested rows and a zero-member group "
            "is []; reason_id is null unless state=unparsed (headers.address_unparsable); IDN and "
            "SMTPUTF8 stay verbatim",
        ),
        "headers.date": Measure(
            1,
            note="[[ordinal, raw, zone_state, offset, utc], ...]; zone_state is "
            "zone_stated|zone_stated_minus_zero|zone_absent; offset is '+HHMM'/'-HHMM' or null; "
            "utc is the RFC 3339 instant or ['unknown', reason_id] (headers.no_date/"
            "headers.invalid_date) -- a missing or invalid date never sorts as an epoch",
        ),
        "headers.parameters": Measure(
            1,
            note="[[ordinal, field_name, parameter, decoded_value, decode_state, fallback_reason], "
            "...] one row per structured parameter (a boundary, a charset, a name, a filename); "
            "decode_state is decoded|fallback|undecodable; fallback_reason is null unless "
            "decode_state=fallback, then encoded_word_in_parameter|empty_charset|"
            "missing_continuation_index|duplicate_continuation_index",
        ),
        "body.text": Measure(
            1,
            note="[[part, text, verbatim_precision, verbatim_reason], ...]; verbatim_precision is "
            "exact|part_level; verbatim_reason is null when exact, else cte_not_identity|"
            "multibyte_without_offset_map|decode_fallback; a part_level row carries no within-part "
            "byte span; the coordinate space is the decoded text in code points, un-normalised",
        ),
        "body.alternative_group": Measure(
            1,
            note="[[part, group_id], ...] one row per part inside a multipart/alternative; group_id "
            "is a message-local stable id (the multipart's part locator plus an ordinal)",
        ),
        "body.html_spans": Measure(
            1,
            note="[[part, element_ordinal, tag, projected_offset, projected_length], ...] one row "
            "per element of the own element tree, in document order; the span is the element's span "
            "in the HTML projection",
        ),
        "body.cid_refs": Measure(
            1,
            note="[[part, [cid, ...]], ...] one row per part that references any cid: (an HTML img "
            "src or a href); the list is the de-duplicated set of cids the part references",
        ),
        "body.plain_effectively_empty": Measure(
            1,
            note="[[part, emptiness_rule], ...] one row per text/plain alternative present but "
            "effectively empty; emptiness_rule is whitespace_only|stub_only",
        ),
        "body.quote_boundaries": Measure(
            1,
            note="[[part, view, rule_id, kind, ordinal, [prefix_depth, ...], span_offset, "
            "span_length], ...] one row per boundary per view; kind is quote|forward|signature|"
            "list_footer|unknown and only kind=quote advances ordinal (the rank within the view); "
            "prefix_depth is per line; span is in the view's code points",
        ),
        "body.view_levels": Measure(
            1,
            note="[[part, view, level, resolution_rule_id], ...] one row per view (not per span); "
            "level is the derived rank and carries the rule that resolved it; ordinal and depth are "
            "stored, never averaged",
        ),
        "attach.types": Measure(
            1,
            note="[[part, declared_mime, magic, container_introspection, winner, disagreement], ...] "
            "one row per attachment occurrence; each verdict is a triple [state, value | null, "
            "reason_id | null] with state value|absent|unknown (magic consulted and clean is "
            "['value', 'unrecognized', null]); winner is magic|declared_mime|"
            "container_introspection|null; disagreement is a bool",
        ),
        "attach.filename": Measure(
            1,
            note="[[part, filename_raw, decode_state, decoded_value, fallback_reason], ...] one row "
            "per occurrence that carries a filename; decode_state is decoded|fallback|absent|"
            "unparsable; fallback_reason is null unless decode_state=fallback",
        ),
        "attach.decorative": Measure(
            1,
            note="[[part, rule_id | null], ...] one row per attachment occurrence; rule_id is a "
            "recorded hint rule (inline_unreferenced_small_image|inline_unreferenced_tracking_pixel) "
            "or null; the hint never removes an occurrence",
        ),
        "attach.cid_use": Measure(
            1,
            note="[[part, cid, referenced], ...] one row per occurrence that carries a Content-ID; "
            "referenced is referenced|unreferenced|n/a, decided against body.cid_refs; a cid-less "
            "occurrence is ['<part>', null, 'n/a']",
        ),
        # Phase 3: threading and time evidence (D7/D15).
        "thread.claims": Measure(
            3, note="[[message_id, [references], parent_claim_or_null]] header edges as claims (needs D7)"
        ),
        "time.evidence": Measure(
            3, note="[<TimeEvent shape, emailextract/timeevent.py>] (D15; needs the time layer)"
        ),
        "time.owner_manifest": Measure(3, note="[[event_id, ...]] the caller's labelled total order (D15)"),
        "time.orders": Measure(
            3, note="[[policy, [event_id], [not_placed]]] the order under each named policy (D15)"
        ),
        "time.unresolved_pairs": Measure(
            3, note="[[event_a, event_b, reason]] every pair of claims that disagrees (D15)"
        ),
        "time.evidence_conflicts": Measure(
            3, note="bool: whether the fixture's evidence conflicts at all (D15)"
        ),
    }
)

#: fact id -> its phase, for callers that report ``not_yet`` by phase.
FACT_PHASES: Mapping[str, int] = MappingProxyType(
    {fact_id: measure.phase for fact_id, measure in FACTS.items()}
)


class OracleError(ValueError):
    """The oracle and the labels disagree about what is being checked.

    Raised for an unmodelled fact id and for a phase disagreement. Both are harness defects:
    with either, a green run would mean nothing, so the oracle refuses to report at all.
    """


class Status(enum.Enum):
    """What happened to one fact."""

    OK = "ok"
    MISMATCH = "mismatch"
    NOT_YET = "not_yet"
    UNMEASURABLE = "unmeasurable"


@dataclass(frozen=True)
class Outcome:
    """One fact, measured (or not) and compared."""

    fact_id: str
    phase: int
    status: Status
    where: str = ""
    expected: Any = None
    actual: Any = None
    detail: str | None = None

    @property
    def failed(self) -> bool:
        """A mismatch, or a measurement that blew up. ``not_yet`` is neither pass nor failure."""
        return self.status in (Status.MISMATCH, Status.UNMEASURABLE)


@dataclass(frozen=True)
class Report:
    """Every outcome for one fixture (or for a whole corpus), plus the verdict."""

    fixture: str
    phase: int
    outcomes: tuple[Outcome, ...] = ()

    @property
    def compared(self) -> int:
        """How many facts were actually measured and compared."""
        return sum(1 for outcome in self.outcomes if outcome.status in (Status.OK, Status.MISMATCH))

    @property
    def not_yet(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is Status.NOT_YET)

    def not_yet_by_phase(self) -> dict[int, int]:
        """``not_yet`` counted by the phase each fact is due at, never as one total."""
        counts: dict[int, int] = {}
        for outcome in self.outcomes:
            if outcome.status is Status.NOT_YET:
                counts[outcome.phase] = counts.get(outcome.phase, 0) + 1
        return counts

    @property
    def failures(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.failed)

    @property
    def mismatches(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.status is Status.MISMATCH)

    @property
    def ok(self) -> bool:
        """Green means *something was compared*, and none of it failed.

        A report that compared nothing is not green: a gate that passes because no label was
        due would stay green through any regression, which is exactly the emptiness the
        ledger and the corpus exist to make visible.
        """
        return self.compared > 0 and not self.failures

    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for outcome in self.outcomes:
            counts[outcome.status.value] += 1
        return counts

    def lines(self) -> list[str]:
        """The report, one line per fact, for a terminal or a log."""
        lines = [f"L1 phase {self.phase}: {self.fixture} ({len(self.outcomes)} fact(s))"]
        for outcome in self.outcomes:
            line = f"  {outcome.status.value:<13} {outcome.fact_id}"
            if outcome.detail:
                line += f" -- {outcome.detail}"
            lines.append(line)
        counts = ", ".join(f"{name}={count}" for name, count in sorted(self.counts().items()))
        lines.append(f"  compared={self.compared} ({counts})")
        lines.append("  ok" if self.ok else "  NOT OK -- see the failures above")
        return lines


def check(sidecar: Sidecar, *, phase: int = CURRENT_PHASE) -> Report:
    """Measure every fact the sidecar labels, at ``phase``.

    Raises :class:`OracleError` if a label is unmodelled or the phases disagree; a measurer
    (or the walk itself) that raises is reported ``unmeasurable`` rather than allowed to
    escape, because "the measurement itself is broken" is a gate failure and has to be
    visible in the report.
    """
    if not isinstance(sidecar, Sidecar):
        raise OracleError(f"check(): {sidecar!r} is not a loaded Sidecar")
    measured = _measure(sidecar)
    outcomes = [_check_one(measured, fact, phase=phase) for fact in _ordered(sidecar)]
    return Report(fixture=sidecar.stem, phase=phase, outcomes=tuple(outcomes))


def check_all(root: Path | str = DEFAULT_FIXTURES, *, phase: int = CURRENT_PHASE) -> Report:
    """Measure every sidecar under ``root`` and merge them into one corpus report."""
    sidecars = load_sidecars(root)
    outcomes = tuple(
        outcome
        for sidecar in sidecars.values()
        for outcome in check(sidecar, phase=phase).outcomes
    )
    return Report(fixture=f"corpus ({len(sidecars)} sidecar(s))", phase=phase, outcomes=outcomes)


def check_path(
    path: Path | str, *, phase: int = CURRENT_PHASE
) -> Report:
    """Convenience: load one sidecar from a path and check it."""
    return check(load_sidecar(path), phase=phase)


def _measure(sidecar: Sidecar) -> Measured:
    """Walk the fixture once; a failure walking is recorded, not raised."""
    try:
        result = walk(EmlContainer(sidecar.artifact.read_bytes()))
    except Exception as error:  # noqa: BLE001 -- reported per fact, see Measured
        return Measured(sidecar=sidecar, result=None, problem=f"{type(error).__name__}: {error}")
    return Measured(sidecar=sidecar, result=result)


def _ordered(sidecar: Sidecar) -> list[Fact]:
    return [sidecar.facts[fact_id] for fact_id in sorted(sidecar.facts)]


def _check_one(measured: Measured, fact: Fact, *, phase: int) -> Outcome:
    sidecar = measured.sidecar
    measure = FACTS.get(fact.id)
    if measure is None:
        raise OracleError(
            f"{sidecar.path}: the sidecar labels {fact.id!r}, which the oracle does not model -- "
            "add it to FACTS with the phase it becomes checkable at (an unmodelled label is "
            "never skipped, because that would report a pass for something nothing measured)"
        )
    if fact.phase != measure.phase:
        raise OracleError(
            f"{sidecar.path}: {fact.id!r} is labelled phase {fact.phase} and the oracle says "
            f"phase {measure.phase} -- the labels and the harness are out of step, so neither "
            "the pass nor the failure would mean anything"
        )
    if fact.phase > phase:
        return Outcome(
            fact_id=fact.id,
            phase=fact.phase,
            status=Status.NOT_YET,
            where=sidecar.stem,
            expected=fact.value,
            detail=f"due at phase {fact.phase}, the oracle is at phase {phase}",
        )
    if measure.function is None:
        raise OracleError(
            f"{sidecar.path}: {fact.id!r} is due at phase {fact.phase}, which the oracle claims "
            f"to be at, but nothing measures it ({measure.note or 'no measurer registered'})"
        )
    try:
        actual = measure.function(measured)
    except Exception as error:  # noqa: BLE001 -- reported, not swallowed: see Measured
        return Outcome(
            fact_id=fact.id,
            phase=fact.phase,
            status=Status.UNMEASURABLE,
            where=sidecar.stem,
            expected=fact.value,
            detail=f"{type(error).__name__}: {error}",
        )
    return _compare(measured, fact, measure, actual)


def _compare(measured: Measured, fact: Fact, measure: Measure, actual: Any) -> Outcome:
    if measure.compare(fact.value, actual):
        status = Status.OK
        detail = None
    else:
        status = Status.MISMATCH
        detail = f"labelled {_short(fact.value)}, measured {_short(actual)}"
    return Outcome(
        fact_id=fact.id,
        phase=fact.phase,
        status=status,
        where=measured.sidecar.stem,
        expected=fact.value,
        actual=actual,
        detail=detail,
    )


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 200 else text[:197] + "..."
