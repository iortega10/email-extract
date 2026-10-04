# The sibling contract -- FROZEN (Phase 0, Turn 0.5)

Status: **frozen**. Every field, type and rule below is what Phase 2 checks a
**real** sibling against. It is proved in Phase 0 against a **fake** sibling store
(`tests/support/fake_store.py`): no real sibling is imported, called, installed or
required, no attachment is routed and no child is ever really extracted. Design
**Open risk 1** stands: nothing in this turn tests a real sibling; the first real
round-trip is Phase 2.

Source of truth for the decisions is `email-extraction-design.md` (D4, D5, D12);
this document freezes the *shape* those decisions call for. Code:
`emailextract/siblings.py` (records + discovery + locator + resolver),
`emailextract/model.py` (`ChildLink`, `ChildLinkState`, `StatusOutcome`,
`TriValue`, `AttachmentOccurrence`).

## 0. The one-sentence contract

Every package keeps its own store; the email store **references children by
content hash** (sha256), a thin **locator** points a hash at the store root that
holds it, and the link to a child is the four-state `ChildLink`. The email
manifest stays useful with **every** sibling store deleted.

## 1. Discovery (D4)

```python
SIBLING_MODULES: Mapping[str, str] = {"word": "wordextract", "form": "formextract"}

module_name(sibling: str) -> str          # "word" -> "wordextract"; unknown family raises ValueError
is_installed(sibling: str) -> bool        # importlib.util.find_spec(module_name(sibling)) is not None
discovery() -> dict[str, bool]            # {sibling: installed}, name order
missing_siblings() -> tuple[str, ...]     # the not-importable families, name order
```

Rules:

* **`find_spec`, never import.** A sibling's presence is a question about the
  environment. Importing a package to ask it runs the package's import side
  effects and makes "not installed" untestable. A test asserts neither sibling
  module is in `sys.modules` after discovery.
* **A missing sibling is a status, not a citation state**:

  ```python
  not_installed(sibling: str) -> StatusOutcome
  # StatusOutcome(status=Status.NOT_INSTALLED, needed_sibling=sibling, reason=None)
  ```

  `Status` is the closed nine-member D6 enum; `not_installed` takes
  `needed_sibling` and **no** reason (`emailextract/model.py:REASON_TABLE`). It is
  environmental: re-running with the extra installed flips it without changing the
  message's content. `sibling.not_installed` is the gap-registry id for it, not a
  citation reason.

## 2. The locator (D5)

```python
@dataclass(frozen=True)
class Locator:
    stores: tuple[SiblingStore, ...] = ()

    def reachable(self) -> tuple[SiblingStore, ...]      # configured stores that answer available()
```

```python
locate(locator: Locator, attachment_id: str) -> tuple[SiblingStore | None, ChildResult | None]
```

Rule: **a config of child-store roots checked in order**; the first reachable
store that has the child wins. At the scale target (about 25 documents) this *is*
the index; a real index is a later optimization (design Open risk 7).

## 3. The child link (D5)

`ChildLink` is **reused, not redefined** (`emailextract/model.py`):

```python
class ChildLinkState(str, Enum):
    RESOLVED = "resolved"
    STORE_ABSENT = "store_absent"
    CHILD_ABSENT = "child_absent"
    VERSION_MISMATCH = "version_mismatch"

@dataclass(frozen=True)
class ChildLink:
    state: ChildLinkState
    child_id: str                 # the attachment's sha256
    store_id: str | None = None   # the child store that was reached
    expected_version: str | None = None
    found_version: str | None = None
    flags: FlagSection = ...
```

| state | when | `store_id` | `expected_version` / `found_version` |
|---|---|---|---|
| `resolved` | a reachable store holds the child at the versions the caller expected | set | not set |
| `store_absent` | **no** configured store is reachable | None | not set |
| `child_absent` | a store is reachable but holds no result for this sha256 | None | not set |
| `version_mismatch` | the child exists, at a `sibling_parser_version` or `core_version` the caller did not expect | set | the pair that disagreed |

`link_child(attachment_id, *, occurrence, route, locator,
expected_sibling_parser_version=None, expected_core_version=None) -> ChildLinkResult`
and `link_occurrence(occurrence, *, route, locator, ...)` (which passes
`occurrence.occurrence_path` as the occurrence) produce the link, the citation and
the child's facts together, held consistent (see §6).

Ambiguity resolved here: `ChildLink` carries **one** expected/found pair, while two
versions can disagree. The sibling parser version is checked first (it decides what
the child's facts mean) and the pair carried is that mismatch; a core-only
mismatch carries the core pair. Both are `version_mismatch`.

## 4. The child-result shape (D5) -- what a sibling store holds

```python
@dataclass(frozen=True)
class ChildResult:
    attachment_id: str            # the attachment's sha256 -- the join key, and the store's key
    sibling: str                  # "word" | "form"
    sibling_parser_version: str
    child_store_id: str
    child_store_revision: str
    core_version: str
    citation: dict[str, Any] = {} # the sibling's OWN citation object, opaque
    facts: SiblingDerivedFacts = SiblingDerivedFacts()
```

```python
@dataclass(frozen=True)
class SiblingDerivedFacts:
    page_count: TriValue = TriValue()    # the CHILD's fact, sibling_derived
    sheet_count: TriValue = TriValue()   # never copied, never defaulted to zero
```

`TriValue` is the package's tri-state (`emailextract/model.py`):
`state: TriState = value | absent | unknown`, `value: str | None`,
`reason_id: str | None`. A count is carried as its **decimal text** in the value
slot. A count's `unknown` reason is one of the closed ids in §7 (`absent` means the
child has no such count -- a `.docx` has no pages in word-extract).

The store seam a real sibling must satisfy:

```python
@runtime_checkable
class SiblingStore(Protocol):
    sibling: str
    sibling_parser_version: str
    child_store_id: str
    child_store_revision: str
    core_version: str
    def available(self) -> bool: ...                       # is this root reachable?
    def read(self, attachment_id: str) -> ChildResult | None: ...
```

`read` is keyed by the attachment's sha256 and returns None when the store holds
no result for it (which is `child_absent`, distinct from an unreachable root).

## 5. The three-bucket citation (D12) -- never mixed

```python
class CitationChildState(str, Enum):
    VERBATIM = "verbatim"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class ChildCitationVia:            # bucket (a): email-extract's own
    attachment_id: str             # the sha256
    occurrence: str                # part path @ message id (see the ambiguity note)
    route: str                     # "word" | "form"
    child_store: str | None = None

@dataclass(frozen=True)
class ChildCitationChild:          # bucket (b): verbatim passthrough | unknown WHOLE
    state: CitationChildState = CitationChildState.UNKNOWN
    payload: dict[str, Any] | None = None    # the sibling's citation, exactly as written
    reason_id: str | None = None             # closed reason id, only when unknown

@dataclass(frozen=True)
class ChildCitationStamp:          # bucket (c): the versions a citation is meaningless without
    sibling: str
    sibling_parser_version: str
    child_store_id: str
    child_store_revision: str
    core_version: str
    linked_by_email_parser_version: str      # the email-extract version that made the link

@dataclass(frozen=True)
class ChildCitation:
    via: ChildCitationVia
    child: ChildCitationChild
    stamp: ChildCitationStamp | None = None  # populated exactly when a store was reached
```

```python
same_content_hash(left: ChildCitation, right: ChildCitation) -> bool
    # left.via.attachment_id == right.via.attachment_id
```

The design states the shape as `{via, child}`; `stamp` is the third bucket it
names, carried as its own field so the three stay **disjoint**. `stamp` is `None`
exactly when no store was reached (there is nothing to stamp), so it is fully
filled or absent -- never partial.

### The rules, each one a test

1. **`unknown` is WHOLE.** A missing child makes the child bucket `unknown` -- no
   field of it is partially filled (`payload is None` and the only populated
   fields are `state` and `reason_id`), and the citation's `stamp` is `None`.
2. **The buckets are never mixed.** No key of bucket (a) or (c) appears in bucket
   (b), and vice versa (tested over a sibling payload with real citations keys).
3. **The passthrough is opaque.** The payload is the store's own object: never
   translated, renumbered or re-derived into email coordinates (offsets stay in the
   child's space). Mutating it changes that bucket and nothing else.
4. **Never merged.** Two occurrences of one file are two `ChildCitation`s with two
   occurrences and a `same_content_hash` boolean, never one merged citation.
5. **Unknown is recorded as unknown.** An unknown count carries a closed
   `sibling.*` reason id and is never `absent` and never `"0"`.

### Ambiguity resolved: the occurrence string

D12 says `occurrence = part path @ message id`. `AttachmentOccurrence` records
`occurrence_path = part path @ occurrence ordinal` (its own docstring: "an
explicitly non-stable locator"). `link_occurrence` passes `occurrence_path`
through as the occurrence string, because it is the email side's own locator and
D12's message-id half is already the link's `attachment_id`-adjacent context. If
Phase 2 wants the literal message id appended, that is a `ChildCitationVia` value
change, not a shape change.

## 6. `ChildLinkResult` -- the three records held consistent

```python
@dataclass(frozen=True)
class ChildLinkResult:
    link: ChildLink
    citation: ChildCitation
    facts: SiblingDerivedFacts
```

Invariants, enforced at construction:

* `link.child_id == citation.via.attachment_id`;
* `resolved` **iff** the child bucket is `verbatim`;
* a `resolved` result carries its `stamp` and the child's own counts;
* otherwise the child bucket and **both** counts are `unknown` with the **same**
  closed reason, the one named by the link state:

| `ChildLinkState` | closed reason id (the gap registry's `sibling.*` family) |
|---|---|
| `store_absent` | `sibling.store_absent` |
| `child_absent` | `sibling.child_absent` |
| `version_mismatch` | `sibling.version_mismatch` |

Those three ids are the closed set `CITATION_UNKNOWN_REASONS`; nothing here
invents a fourth. (The registry also has `sibling.not_installed`, which is the
environmental `StatusOutcome` of §1, and `sibling.contract_unknown`, which no code
in this turn emits.)

## 7. Version stamps and the ledger

`ChildCitationStamp` is what makes a citation meaningful: the sibling, its parser
version, the store id and revision, the core version, and the email-extract parser
version that made the link. Two facts ride the behavior ledger (Turn 0.5):

* the **contracts** fingerprint is now keyed by this package's
  `OUTPUT_SCHEMA_VERSION` (moved to `"2"` by this turn), not by the core codec's
  `SCHEMA_VERSION`; the old `"7"` line is a marked LEGACY entry that is never
  compared again;
* a field default written from a version constant is fingerprinted **symbolically**
  (the constant's name), so a parser-version bump is not a contract change.

The walker's output did **not** move: the `walk` and `decode_chain` lines were
re-recorded as `unchanged` in the same run that appended the `contracts` `"2"`
line.

## Phase 2 conformance checklist

What the contract needs from a **real** sibling, what was found by reading the two
sibling repositories (read-only; neither was edited), whether it is provided
today, and what is missing. **This is a finding list, not a change, and nothing
below claims a real sibling satisfies the contract.**

| # | Property the contract needs | word-extract (`C:\Users\ivan_\App_repos\word-extract`) | form-extract (`C:\Users\ivan_\App_repos\form-extract`) | Provided? |
|---|---|---|---|---|
| 1 | keyed by the child's content hash | `wordextract/versions.py:HashedInputs.source_content_hash`; `wordextract/store.py:_key`, `parse_key`, `artifact_keys` (the `raw` artifact *is* `source_content_hash`); `Store.__init__` collections keyed by their own key | `formextract/model.py:SourceInfo.content_hash`; `InstanceRecord.idempotency_key` (`f"{content_hash}:{pipeline_version}"`, `model.py:328`); `formextract/store.py:Store.find_instance` / `save_instance`; `formextract/pipeline.py:run` looks the hash up | **yes**, both |
| 2 | a stable store id | none: `wordextract/store.py:Store.__init__` is a directory; `wordextract/model.py:RunRecord.run_id` is per run | none: `formextract/store.py:Store.__init__` is a directory; `InstanceRecord.instance_id` / `run_id` are `uuid4` per record (`pipeline.py:139`) | **no** -- see finding A |
| 3 | a stable store revision | none found | none found | **no** -- finding A |
| 4 | a sibling parser version | `wordextract/versions.py`: `SPEC_PARSER_VERSION`, `TEXTMODEL_VERSION`, `HEADING_RULESET_VERSION`, `CHUNKER_VERSION`, `MATCHER_VERSION`; carried in `HashedInputs` and filled by `store.hashed_inputs` | `formextract/model.py:SourceInfo.parser_version` (set from `ing.parser_version`, `pipeline.py:88`) plus `PIPELINE_VERSION` (`model.py:10`) in the key | **yes**, but the meaning differs -- finding B |
| 5 | a core version | recorded: `wordextract/store.py:recorded_inputs` includes `CORE_VERSION` (`from docextract_core import CORE_VERSION`) | not recorded anywhere (`SourceInfo`/`InstanceRecord` carry `schema_version` and `parser_version` only) | **word: yes; form: no** -- finding C |
| 6 | a way to read a **verbatim citation** | yes, in the child's own space: `wordextract/model.py:Span` (`part_id`, `start`, `end`, `fragment_id`), `ViewSpan`, `TermHit.spans`/`view_spans`; stored under the hits key by `HitsArtifact` | yes, in the child's own space: `formextract/model.py:Span` (`text`, `bbox`, `element_id`), `BBox` (`page`, `x0..y1`), `Region`, `InstanceRecord.residuals`/`regions` | **yes**, both -- but no single "citation for this hash" call; the caller reaches it through the store's artifacts / `instances/index.json` |
| 7 | `page_count` | not a word-extract fact; absent (`SiblingDerivedFacts.page_count.state == absent`) | `formextract/model.py:SourceInfo.page_count: int \| None`; also `LayoutResult.page_count` (`model.py:258`) | **form: yes; word: absent by nature** |
| 8 | `sheet_count` | n/a | not a field: `formextract/model.py:SourceInfo.sheet_names: list[str]` (and `InstanceRecord.tabs`); a count is *derivable*, not recorded | **missing as a count** -- finding D |

### Findings (Phase 2, not edited here)

**A. Neither sibling has a store id or a store revision.** The stamp bucket's
`child_store_id` / `child_store_revision` have no producer today. Phase 2 must
either add a store-level identity to each sibling's store, let the owner's config
supply it, or record both as unknown with a registry id -- it must not be faked
from a `run_id` or a directory path.

**B. "`sibling_parser_version`" means a different thing in each sibling.**
word-extract's `SPEC_PARSER_VERSION` is the *spec* parser; its matching/stemming
identity is `MATCHER_VERSION`, and the chunker/heading rules are separate. The
"hits" artifact's meaning is only pinned by the `hits` key, which nests the parse
key. form-extract's `parser_version` is a backend string plus `PIPELINE_VERSION`.
Phase 2 must fix, per sibling, which stamp is the one whose change invalidates a
child citation (probably the key of the artifact the citation is read out of).

**C. form-extract records no core version.** `core_version` is part of the stamp
bucket and part of the `version_mismatch` check. For a form child the check would
have to be skipped (`expected_core_version=None`), which is a silent hole: a
`docextract-core` change could move a form child's meaning without a mismatch.
word-extract does record it (`store.recorded_inputs`).

**D. `sheet_count` is not recorded by either sibling.** form-extract records
`sheet_names`; a count is derivable but the contract asks the child for the fact.
Phase 2 either records the count in form-extract or the contract treats
`sheet_count` as derivable and says so.

**E. No real sibling is exercised** (design Open risk 1). Every rule above is
proved against `tests/support/fake_store.py`. A real sibling library answers
`importlib.util.find_spec` only where it is installed: in this environment
word-extract is **not** installed, so the "sibling present" test
(`pytest.importorskip`) skips with its reason while the "genuinely absent" test
(`sys.modules` patched out, `find_spec` forced to `None`) runs. Phase 2 must
re-run the same contract against a real store.

**F. The locator is a config of store roots** (design Open risk 7): correct at
about 25 documents, not beyond. No index is built here.

## What this document does and does not prove

**Does:** the shape and its invariants, against a fake store -- the four
`ChildLink` states and the reason ids they map to, the three disjoint buckets, the
verbatim passthrough, unknown-whole, the two occurrences of one file, the locator
order, the discovery path with the siblings genuinely absent, and that
`emailextract` imports with neither sibling present.

**Does not:** anything about a real sibling's query API, store layout, citation
stability or version stamps (findings A to D above and design Open risk 1). No
attachment is routed and no child is extracted; that is Phase 2.
