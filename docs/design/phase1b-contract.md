# Phase 1b contract: the one schema bump, the compiled provenance and the closed vocabularies (Turn 1b.0a specification; built in Turns 1b.1 to 1b.10)

Status: **decided in Turn 1b.0a, documents only.** This is the exact brief the later Phase 1b turns build
against, in the form Turn 1.0a gave `phase1-build-spec.md` / `phase1-facts.md` / `phase1-fixtures.md` /
`phase1-ledgers.md` / `phase1-turn-declarations.md`. Nothing in `emailextract/`, `tests/`, `tools/`, `fixtures/`
or any sidecar or ledger JSON is touched by this turn. The design is revised **once**, in `email-extraction-design.md`
revision 4, written in the same turn.

Authorities, in order (CLAUDE.md): the design (`email-extraction-design.md`) wins; then
`docs/design/phase1b-build-spec.md` (revision 2); then `docs/design/phase1b-debate.md`. Conflicts found between
them and the code are collected in section 12 rather than papered over.

Evidence labels: **`(C)`** = a `file:line` this turn opened and read; a fact marked **(unverified)** was taken
from the spec or the debate and not re-opened against the code in this turn.

Tasks performed in this turn:

1. Decide every "decide in 1b.0a" item of the spec: the exact `ContainerStreamRef` shape and **where it lives**;
   the `EmbeddedSummary` shape and placement; the `REASON_TABLE` additions and their `Status` pairings; the
   `NAMED_ERROR_REASONS` edits; `text.VERBATIM_REASONS`; the `sha256`/`size_bytes` rule for a pass-through versus
   a re-encoded leaf and where the stream's own digest lives; the `container_facts` key list for `cfb_msg`; the
   span-table row shape; the eight provenance points with the verbatim default expression each; the `value_codec`
   seam signature; the `.eml` golden re-record rule; and the exact list of existing tests that must change.
2. Fix the `phase` int of a Phase 1b fact and its consequences (`phase1b-facts.md`).
3. Fix the fixture catalogue (`phase1b-fixtures.md`), the ledgers/declarations/golden (`phase1b-ledgers.md`)
   and the owner's probes (`phase1b-probes.md`), and revise the design (`email-extraction-design.md` revision 4),
   the registry (`phase0-gaps.md`) and the open-inputs file once each.

## 0. The resolution list (each "decide in 1b.0a" item, the decision, the one-line reason)

| # | item (spec §) | decision | one-line reason |
|---|---|---|---|
| R1 | `ContainerStreamRef` placement (`:177`, "picked in 1b.0a") | **optional field** `stream_ref` on `PartRecord` **and** `HeaderField` | the records are what the store persists and the strict codec already round-trips nested optional records (`TriValue`, `StatusOutcome`); a side table is a second index free to disagree |
| R2 | `ContainerStreamRef` shape (`:176`) | `{stream, byte_offset, byte_len, axis, fault}` exactly, with `byte_offset`/`byte_len` typed `int \| None` and the synthetic invariant (section 1) | C2 forbids a virtual offset in a record; a synthetic region has none, so the offsets are `None` and the presence of a ref is honest |
| R3 | `EmbeddedSummary` shape/placement (`:180-181`) | `{message_class, subject: str \| None, has_transport_headers: bool, recipient_count: int, attachment_count: int}` as optional `embedded` on `AttachmentOccurrence` | the occurrence is the record that owns an embedded-message attachment; `None` keeps its single "absent" meaning (Phase 1 decision 6) |
| R4 | `REASON_TABLE` additions (`:178-179`) | `sector_count_cap`, `directory_entries_cap`, `difat_chain_length_cap` join `Status.SKIPPED` | a CFB limit stretched onto `part_count_cap`/`depth_cap` makes a reader of the reason infer the wrong cause (O3) |
| R5 | `NAMED_ERROR_REASONS` (`:40-41`) | add `cfb_directory_loop`, `cfb_header_unsupported`; delete `cfb_msg_unsupported`; CFB magic without `__properties_version1.0` -> `not_a_message` | the entry point now opens CFB; a `.doc`/`.xls`/`.ppt`/`.msi` is simply `not_a_message` |
| R6 | `text.VERBATIM_REASONS` (`:42`) | gains the fourth member `container_stream` | every `.msg` leaf is `part_level` even when its bytes equal the stream's (the virtual offset is a false `exact`) |
| R7 | leaf `sha256`/`size_bytes` (`:43-44`) | pass-through: the stream's own size/digest; re-encoded: the UTF-8 re-encoding's size/digest; synthetic: `None`/`None`; the stream's own digest/size live in the span-table row | the digest is over the bytes a consumer can read, and D13 wants the raw bytes/digest "beside the decode" (the persisted table is the source-only form, section 7) |
| R8 | `container_facts` names (`:45-46`) | the fixed list in section 6, `str -> str`, with worked examples | `ContainerFacts.facts` is an open `dict[str, str]`; a producer must be pinned so the ledger and the facts agree |
| R9 | span-table row shape (`:47-50`) | `SpanRow` in section 7, published as `getattr(container, "span_provenance", None)`; the persisted form is the source-only `PersistedSpanRow` | it is producer-internal (not a `Container` Protocol member), so `EmlContainer`/`FakeContainer` stay valid; a persisted virtual offset would make the store bytes depend on the framing length (C2) |
| R10 | eight provenance points (`:49-50`) | section 8, each with its file, function and **verbatim** default expression | the only edits to frozen modules; each default branch is the current expression unchanged |
| R11 | `value_codec` seam (`:51`) | `header_fields_at(..., *, value_codec="latin-1")` and `header_region(..., *, value_codec="latin-1")` | one seam, both call sites, `.eml` default byte-identical |
| R12 | existing tests that change (`:52-55`) | section 11; **23** rows verified (22 test functions/files plus the one `behavior_ledger.json` data row), list complete | a test not on the list that fails later is a defect |
| R13 | Phase 1b fact `phase` int (`phase1b-facts`) | **`phase = 1`**, the same int as Phase 1's facts | Phase 1b is the container half of the phase-1 parse layer, before routing (Phase 2); there is no `phase 1.5` |
| R14 | `msg.*` gap rows (brief §2) | **no new gap fact**: they ride `part.gaps` (part-level) and `gaps.later` (document-level) | Phase 1 rule "no new gaps fact type is introduced" (`phase1-facts.md`); a duplicate fact is a second place to disagree |
| R15 | the "seven sector classes" (spec `:63,:156, :311`) | **eight** ordered classes (section 6), not seven | the spec lists eight names; "seven" is a miscount (section 12, C3) |

## 1. The schema bump, exactly

`OUTPUT_SCHEMA_VERSION` moves **once**, `"5"` -> `"6"`, in Turn 1b.1, and contains exactly three things.

### (X) `ContainerStreamRef` as a field on `PartRecord` and `HeaderField`

```python
class ContainerStreamAxis(str, Enum):
    """The provenance kind of one virtual region (D13, A'')."""
    STREAM = "stream"          # the bytes ARE a CFB stream (pass-through)
    REENCODED = "reencoded"    # the bytes are a re-encoding of a CFB stream (001F -> UTF-8)
    SYNTHETIC = "synthetic"    # the bytes are the projection's own framing

class StreamFault(str, Enum):
    """The per-stream chain fault `cfb.read_stream` returns (A8), `None` never a member."""
    CYCLE = "cycle"
    OUT_OF_RANGE = "out_of_range"
    SHORT_CHAIN = "short_chain"

@dataclass(frozen=True)
class ContainerStreamRef:
    """One record's provenance: which CFB stream, which bytes of it, how, and whether the chain broke."""
    stream: str
    byte_offset: int | None = None
    byte_len: int | None = None
    axis: ContainerStreamAxis = ContainerStreamAxis.STREAM
    fault: StreamFault | None = None
```

- `stream`: for `STREAM`/`REENCODED` the CFB stream name verbatim (`"__substg1.0_10130102"`); for `SYNTHETIC` a
  synthetic label of the form `"synthetic:<role>:<ordinal>"` (e.g. `"synthetic:boundary:1"`).
- `byte_offset`/`byte_len`: **source** offsets in the stream's own encoding (UTF-16 for a `001F` stream), not
  virtual offsets. Both `int >= 0` for `STREAM`/`REENCODED`; both `None` for `SYNTHETIC` (C2: no virtual offset in
  a record).
- `fault`: `None` when the stream read cleanly; otherwise the CFB chain fault. The **mapped** `Status` reason
  (`stream_ended_early` / `declared_length_mismatch`) rides on the document's or the part's `StatusOutcome`, not
  here; `fault` is the fine-grained stream cause.

**Placement (R1).** `PartRecord` and `HeaderField` each gain `stream_ref: ContainerStreamRef | None = None`
(the last field, so positional construction in tests is unaffected). Chosen over a side table keyed by
`part_id`/ordinal:

- `PartRecord` and `HeaderField` are serialized by the core codec (`model.record_to_bytes`, C). The codec already
  round-trips frozen nested dataclasses with an `X | None` default (`HeaderField.value: TriValue`,
  `AttachmentOccurrence.status: StatusOutcome | None`) (C), so a new optional field is no new codec capability.
- The store persists the **records**: `store.document_artifact` serializes the `EmailDocument` (`store.py:230-273`,
  C). A side table would either not be persisted (silently losing the provenance) or become a second persisted
  structure to keep consistent -- exactly the "second place to disagree" that pruned `attach.size_cap_hit`
  (`phase0-gaps.md:53-68`, C).
- The assembler already fills both records in one pass (`assemble._header_fields`, `assemble._part_records`, C),
  so the producer that knows the span table also writes the field; no consumer has to join a table.

**Invariants, enforced in the parent record's `__post_init__`** (`PartRecord.__post_init__`,
`HeaderField.__post_init__`):

1. `stream_ref is None` is always legal (every `.eml` record, and any `.msg` record with no provenance).
2. `axis is ContainerStreamAxis.SYNTHETIC` requires `byte_offset is None and byte_len is None` and
   `stream.startswith("synthetic:")`.
3. `axis is STREAM or REENCODED` requires `byte_offset` and `byte_len` both `int >= 0` (bools rejected, as the
   codebase rejects bool-as-int everywhere) and `stream` non-empty and **not** starting `synthetic:`.
4. `fault` is `None` or a `StreamFault` member; a `SYNTHETIC` ref carries `fault=None`.

A violation raises `CodecError` naming the invariant, in the style of the existing `_check_axis_pair` /
`TriValue.__post_init__` checks (C).

**Strict-codec round trip, worked.** An `.eml` document is byte-invariant under the bump **except** for the new
`"stream_ref": null` key on every `PartRecord`/`HeaderField` and the `output_schema_version` value:

```json
{"schema_version": "7", "record": {"container_kind": "rfc822", ...,
  "parts": [{"part_id": "9f…", "content_type": "text/plain", ..., "stream_ref": null}]}}
```

The envelope's top-level `"schema_version": "7"` is the **core codec's own** version
(`docextract_core.codec.SCHEMA_VERSION`, C) and is **not** this package's `OUTPUT_SCHEMA_VERSION`: the record's
own `"output_schema_version"` field is the value that moves `"5"` -> `"6"` (section 1). The two numbers are
unrelated (`versions.py:7-9`, C).

A `.msg` leaf carries the ref instead of `null`:

```json
"stream_ref": {"stream": "__substg1.0_10130102", "byte_offset": 0, "byte_len": 4095,
               "axis": "stream", "fault": null}
```

and a re-encoded header field carries the source range of its `001F` stream:

```json
"stream_ref": {"stream": "__substg1.0_007D001F", "byte_offset": 248, "byte_len": 46,
               "axis": "reencoded", "fault": null}
```

`stream_ref` is `null` on both records for every `.eml` fixture, so the bump adds only `null` keys on the
frozen container (section 10).

### (Y) `REASON_TABLE` additions

`model.REASON_TABLE[Status.SKIPPED]` becomes (C, current at `model.py:245-251`):

```python
Status.SKIPPED: (
    "size_cap", "total_size_cap", "depth_cap", "part_count_cap", "header_bytes_cap",
    "sector_count_cap", "directory_entries_cap", "difat_chain_length_cap",
),
```

Stream size does **not** get a new reason: an oversized stream folds into `size_cap` / `cap_hit_mid_stream`
(already in the table, C). `EncodingSource` and `ContainerKind` already carry every needed member (C) and do not
move.

**D1 correction (Turn 1b.1, docs only).** The three new reasons do **not** join `walk.CAP_REASONS`, and
`Limits` does **not** gain `max_sector_count`/`max_directory_entries`/`max_difat_chain_length` in Turn 1b.1.
`assemble.limits_fingerprint` hashes **every** field of `Limits` in declaration order and that fingerprint is
part of `document_key`, so a new field would move the store key of **every** `.eml` document -- beyond "the
version string only", and outside what the `.eml` golden permits (section 10). Instead the three reasons join
`walk.CFB_CAP_REASONS` (a separate tuple beside the walker's five) and their `Limits` fields live wherever the
CFB reader publishes them: **Turn 1b.3** decides that, under one binding constraint recorded here -- an
unchanged `Limits` value must keep `limits_fingerprint(L)` and `document_key` byte-identical (the golden is the
proof). A separate `CfbLimits` published by the container is the expected shape. `tests/test_limits.py`'s
cap-vocabulary assertion becomes
`set(CAP_REASONS) | set(CFB_CAP_REASONS) == set(REASON_TABLE[Status.SKIPPED])` (and `len(CAP_REASONS) == 5`
stays true).

### (Z) `EmbeddedSummary` on `AttachmentOccurrence`

```python
@dataclass(frozen=True)
class EmbeddedSummary:
    """What an embedded-message attachment's own message is, without recursing (Phase 2 reads it)."""
    message_class: str                 # verbatim, e.g. "IPM.Note"
    has_transport_headers: bool
    subject: str | None = None         # None = the embedded message has no subject property
    recipient_count: int = 0
    attachment_count: int = 0

    def __post_init__(self) -> None:
        _non_empty(self.message_class, "embedded_summary.message_class")
        for name, value in (("recipient_count", self.recipient_count),
                            ("attachment_count", self.attachment_count)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CodecError(f"embedded_summary.{name} must be an int >= 0")
```

`AttachmentOccurrence` gains `embedded: EmbeddedSummary | None = None` (the last field).
**Axis rules (Phase 1 decision 6, spec `:33-34`):** `embedded` is a value, **not** an axis; `None` keeps its
single meaning ("this occurrence is not an embedded message"), and there is **no** new "not built" idiom -- the
not-built marker stays `TriValue(state=UNKNOWN, reason_id=not_built_in_phase1)` on `status_axis`/`route_axis`
(Turn 1.0b). Invariant: `embedded is not None` only on an occurrence whose attachment method is
`embedded_message` (`0x3701:000D`); Turn 1b.7 enforces it.

The bump is exactly (X)+(Y)+(Z). Nothing else in a record's serialized shape moves.

## 2. `Status` rules for the four Phase 1b outcomes

| outcome | `Status` | reasons (`REASON_TABLE`) | note |
|---|---|---|---|
| the message class is not `IPM.Note*` | `UNSUPPORTED` | **none** (`Status.UNSUPPORTED` takes no reason, C `model.py:252`) | the class verbatim in `container_facts.message_class`; the gap `msg.class_not_ipm_note`; nothing past the class is opened |
| a CFB cap was hit (`sector_count_cap` etc.) | `SKIPPED` | the matching new reason (section 1Y) | a built observation; the `CapRecord` carries the caller's value and the **real** observed count (never a virtual length) |
| a per-stream chain fault (cycle / out-of-range / short chain) | `TRUNCATED` | `declared_length_mismatch` (cycle) or `stream_ended_early` (out-of-range, short chain) | the base flow per the field | 
| any other readable `.msg` | `PARSED` | -- | |

Every pairing fits the existing table (the caps under `SKIPPED`, the faults under `TRUNCATED`, the class under
`UNSUPPORTED`); **nothing is improvised** and no reason is stretched across statuses. The class gate does **not**
produce a `skipped` -- there is no `skipped` reason a class refusal could use without a table change (the debate
found this, `phase1b-debate.md:52-55`).

## 3. `NAMED_ERROR_REASONS` edits

Current closed tuple (C `parse.py:66-73`): `invalid_input`, `input_over_cap`, `invalid_container_kind`,
`cfb_msg_unsupported`, `not_a_message`, `invalid_limits`. Becomes:

```python
NAMED_ERROR_REASONS: Final[tuple[str, ...]] = (
    "invalid_input",
    "input_over_cap",
    "invalid_container_kind",
    "cfb_directory_loop",       # a directory link points into a cycle -> NamedError
    "cfb_header_unsupported",   # sector shift outside {9,10,11,12} for v3, or v4 with shift != 12
    "not_a_message",            # CFB magic without __properties_version1.0 (.doc/.xls/.ppt/.msi)
    "invalid_limits",
)
```

- **Deleted:** `cfb_msg_unsupported`. `parse` now opens the container (section 8, point 8), so the name is a lie.
- **Added:** `cfb_directory_loop`, `cfb_header_unsupported` (the whole-file CFB faults of A8).
- CFB **magic without `__properties_version1.0`** maps to the **existing** `not_a_message` (a `.doc`, `.xls`,
  `.ppt`, `.msi`), not to a new id.
- Per-stream faults are **not** named errors: they are a document with `Status.TRUNCATED` (section 2).

The values stay `Final[tuple[str, ...]]` in this order, so `tests/test_parse_entry.py:189-196`'s exact-tuple
assertion can be updated in place (section 11).

## 4. `text.VERBATIM_REASONS` gains `container_stream`

`text.py` (C `text.py:110-120`) adds one member and one constant:

```python
REASON_CONTAINER_STREAM: Final[str] = "container_stream"
VERBATIM_REASONS: Final[tuple[str, ...]] = (
    REASON_CTE_NOT_IDENTITY,
    REASON_DECODE_FALLBACK,
    REASON_MULTIBYTE_WITHOUT_OFFSET_MAP,
    REASON_CONTAINER_STREAM,
)
```

`verbatim_reason = container_stream` (hence `verbatim_precision = part_level`, never `exact`) is set for **every
`.msg` leaf, pass-through included**, because `resolve_span` adds `body_span.offset` (a virtual offset, C
`assemble.py:646`) even when the leaf bytes equal the stream's (A3). The closed `verbatim_reason` set is now the
four members above; `None` still means `exact`.

## 5. The leaf `sha256` / `size_bytes` rule

`PartRecord.size_bytes` and `PartRecord.sha256` describe **the bytes a consumer can read for the part** (C
`assemble.py:396-397`: today `size_bytes=part.body_span.length`, `sha256=part.body_sha256`):

| leaf kind (`axis`) | `size_bytes` | `sha256` | where the stream's own size/digest live |
|---|---|---|---|
| pass-through (`STREAM`) | the CFB stream's byte length | sha256 of the stream's bytes (= the leaf bytes) | the value itself -- no duplication needed |
| re-encoded (`REENCODED`) | `len(utf-8 re-encoding)` | sha256(utf-8 re-encoding) | the span-table row (`source_byte_len`, `source_sha256`) |
| synthetic (`SYNTHETIC`) | `None` | `None` | not applicable (no stream) |

Reason: D13 says the raw bytes and digest are kept "beside the decode" (the stream's own digest is the
`source_sha256` of the `REENCODED` row, which is persisted -- section 7); the leaf's own digest stays over the
bytes the leaf actually carries, so a consumer hashing the part gets the bytes it can read. A `SYNTHETIC` leaf
has no bytes, so `None`/`None` is the honest value (the same idiom the walker already uses for a body it did not
read, C `walk.py:814`: `body_sha256=None if decoded is None else …`).

## 6. `container_facts` for `cfb_msg`

`ContainerFacts.facts` is an open `dict[str, str]` (C `model.py:594-603`); a producer must publish a **fixed**
name set so the sidecar ledger and the facts agree. For `cfb_msg` the keys are exactly:

| key | value format | hand-checkable example | who writes it |
|---|---|---|---|
| `adapter` | the literal `cfb_msg` | `cfb_msg` | 1b.5 |
| `cfb_version` | `"3"` or `"4"` | `3` | 1b.3 |
| `sector_size` | decimal bytes | `512` | 1b.3 |
| `mini_sector_size` | decimal bytes | `64` | 1b.3 |
| `mini_cutoff` | decimal bytes | `4096` | 1b.3 |
| `sector_count` | decimal count | `384` | 1b.3 |
| `directory_entries` | decimal count | `129` | 1b.3 |
| `message_class` | verbatim class string | `IPM.Note` | 1b.4 |
| `internet_codepage` | decimal (cp number) or `absent` | `65001` | 1b.4 |
| `message_codepage` | decimal or `absent` | `1252` | 1b.4 |
| `body_streams` | `+`-joined over the fixed order `plain,html,rtf`; `none` when empty | `html` | 1b.5 |
| `has_transport_headers` | `"true"` / `"false"` | `true` | 1b.5 |
| `recipient_count` | decimal | `1` | 1b.6 |
| `attachment_count` | decimal | `0` | 1b.7 |
| `named_property_count` | decimal | `4` | 1b.4 |
| `time.<tag-hex>.filetime_hex` | 16-digit **lowercase** hex of the raw `u64`, no `0x` | `01da8f3c9a1b2d40` | 1b.6 |
| `time.<tag-hex>.utc` | ISO-8601 UTC from the FILETIME, `Z` suffix | `2026-10-11T12:34:56Z` | 1b.6 |
| `projection` | the literal `virtual_rfc822` | `virtual_rfc822` | 1b.5 |

- `<tag-hex>` is the property tag as **4-digit lowercase hex** with no `0x`: `0x0039` -> `time.0039.filetime_hex`.
  Candidate time tags to confirm by probe P2: `0x0039`, `0x0E06`, `0x3007`, `0x3008`.
- `filetime_hex` is **canonical and lossless**; `utc` is a convenience rendering and is *never* the compared
  value when the two could disagree (a FILETIME carries no offset). Both are `<str>` because `facts` is
  `str -> str`.
- The **eight sector classes** (R15) are `sectors.header`, `sectors.difat`, `sectors.fat`, `sectors.minifat`,
  `sectors.directory`, `sectors.stream`, `sectors.free`, `sectors.slack`, each a decimal byte count; their sum
  equals the file length (the no-silent-drop property, asserted on sectors, never on virtual bytes). Example:
  `sectors.minifat` = `512`.
- `sector_count` is the total sector count; `directory_entries` the count of directory entries (the spec's
  `directory_entries` name, R8).

`time.*` facts are raw evidence only: **no `TimeEvent` is emitted in Phase 1b** (`times_axis` keeps the not-built
marker, C `assemble.py:462-463`).

## 7. The span table (`SpanRow`), the producer-internal structure

The span table is discovered with `getattr(container, "span_provenance", None)` (not a member of the
`@runtime_checkable` `Container` Protocol, so `EmlContainer` and `FakeContainer` stay valid, C `container.py`).
It is a `tuple[SpanRow, ...]`, one row per virtual region:

```python
@dataclass(frozen=True)
class SpanRow:
    """One virtual region's provenance.  Producer-internal: no record a consumer cites carries `virtual_*`."""
    axis: ContainerStreamAxis        # stream | reencoded | synthetic (the record field's own vocabulary)
    source_stream: str | None        # the CFB stream name; None for SYNTHETIC
    source_byte_offset: int | None   # offset in the stream's own encoding (UTF-16 for 001F); None for SYNTHETIC
    source_byte_len: int | None      # length in the stream's own encoding; None for SYNTHETIC
    source_sha256: str | None        # sha256 of the source bytes; None for SYNTHETIC
    virtual_offset: int              # the region's offset in the virtual RFC 822 framing (INTERNAL ONLY)
    virtual_len: int                 # its length there (INTERNAL ONLY)
    decoded_char_offset: int | None  # for REENCODED: the decoded character start; else None
    decoded_char_len: int | None     # for REENCODED: the decoded character length; else None
    exact: bool                      # whether source<->virtual is an exact 1:1 map (a flag, never a citation)
```

Rules:

- `virtual_offset`/`virtual_len` **never leave the producer**: `ContainerStreamRef` (the record field) and every
  citation carry only `source_*` (C2). The two virtual columns exist so the producer can address its own framing;
  nothing a consumer cites, and nothing the store writes, carries them.
- **The persisted table is the source-only form.** What the store writes for a `cfb_msg` document is
  `PersistedSpanRow` -- the same rows **without** `virtual_offset`/`virtual_len` (section 8, point 7); it is what
  section 10's golden covers for a `cfb_msg` document. `PersistedSpanRow` is:

  ```python
  @dataclass(frozen=True)
  class PersistedSpanRow:
      """The stored span row: source-only, no virtual framing.  C2: a persisted virtual offset would make the
      stored bytes depend on the projection's framing length."""
      axis: ContainerStreamAxis       # stream | reencoded | synthetic
      source_stream: str | None
      source_byte_offset: int | None
      source_byte_len: int | None
      source_sha256: str | None
      decoded_char_offset: int | None
      decoded_char_len: int | None
      exact: bool
  ```

  The virtual offsets are **recomputed deterministically** from the CFB bytes and `MSG_PROJECTION_VERSION` (the
  projection is deterministic) whenever they are needed, so nothing is lost; a test declared for Turn 1b.1/1b.5
  asserts the recomputation reproduces the same source-only table (`phase1b-ledgers.md`).
- `exact=True` is recorded only here, as a provenance **flag**; `text.analyse_part` never reads it to claim
  `verbatim_precision = exact` against virtual bytes (A3).
- `kind` in the debate is the same closed vocabulary as `axis`; the wire name is `axis`, one name everywhere.
- This is what makes `FakeMsgContainer` and `MsgContainer` able to agree: both publish the same `SpanRow` shape,
  one built by hand and one built from real CFB.

## 8. The eight provenance points (the only edits to frozen modules)

Each is gated on `cfb_msg` or on the presence of a span table, and each default branch is the **current
expression verbatim** (quoted from the code, `(C)`). Ranked by risk to the `.eml` golden.

| # | file | function | current expression that stays the default branch verbatim | the new branch (gated) |
|---|---|---|---|---|
| 1 | `assemble.py:203-236` `_header_fields` and `:337-405` `_part_records` | `_header_fields`, `_part_records` | `HeaderField(name=item.name, raw_value=item.raw_value, ordinal=item.ordinal, value=value, flags=FlagSection(),)` and `PartRecord(part_id=part.part_id, …, flags=FlagSection(),)` | when the container publishes a span table, add `stream_ref=<ContainerStreamRef or None>` (and set `size_bytes`/`sha256` per section 5); the two helpers gain a `span_table=None` keyword |
| 2 | `walk.py:730` and `:799`; `ids.py:125-140` | `_walk_visit` (two `PartShape` builds) | `part_id=part_id(container_id, span, content_hash(span.slice(raw))),` | kind-gated `part_id` over `(container_hash, source-keyed {stream, byte_off, byte_len} or synthetic:<role>:<ordinal>, sha256(real source bytes))`; the default expression is unchanged |
| 3 | `assemble.py:641-648` `_map_span`, reached from `:597` `resolve_span` | `_map_span`, `resolve_span` | `offset = part.body_span.offset + byte_at[start]` / `length = byte_at[end] - byte_at[start]` / `return RawSpan(offset=offset, length=length, locator=part.path)` | for a span-table container, `resolve_span` returns the part's `ContainerStreamRef` (a source span) or `Unresolvable(span_not_resolvable, part_id)`; return type widens to `RawSpan \| ContainerStreamRef \| Unresolvable` |
| 4 | `text.py:542-551` | `analyse_part` | `offset_map: tuple[OffsetSpan, ...] \| None = None` / `if reason is None: offset_map = _build_offset_map(decoded, len(decoded_text), dropped, canonical or "")` / `verbatim_precision=VERBATIM_EXACT if reason is None else VERBATIM_PART_LEVEL` | a `container_stream=False` keyword: when `True`, set `reason = REASON_CONTAINER_STREAM` before the `if reason is None` and build no offset map; `analyse_parts` / `resolve_span` pass `container_stream=True` for a span-table container |
| 5 | `walk.py:785-790` (`_walk_visit` charset branch) and `walk.py:1027-1069` `_charset_ladder` | `_charset_ladder` call site | `used_charset, encoding_source, charset_fired, charset_gap = _charset_ladder(decoded, declared_charset)` | post-walk, the **assembler** overwrites `PartRecord.encoding_source` and `decode_chain.used_charset`/`declared_charset` from the producer's published ladder map (`getattr(container, "charset_sources", None)`); the walker can only ever say `declared_charset`, so `internet_cpid`/`message_cpid` must be written from the MAPI ladder here |
| 6 | `assemble.py:239-264` `_caps` (`declared_size_bytes=declared.get((reason, section.section)),`) and `attach.py:782-789` `declared_size = next((region.span.length … ), 0)` | `_caps`, the attach cap-skip helper | `declared_size_bytes=declared.get((reason, section.section)),` / `declared_size = next((region.span.length for region in result.regions if region.path == part.path and region.kind == reason), 0,)` | when the container publishes CFB caps, build `CapRecord`s from the producer's **real** observed counts (stream length / sector count), never a virtual region length; the default expressions are unchanged |
| 7 | `store.py:158-167` `walk_artifact` (`walk=walk(container),`) | `walk_artifact` | `walk=walk(container),` | for a `cfb_msg` container, persist the CFB sector accounting (the eight classes) plus the **source-only** span table (`PersistedSpanRow`, section 7 -- never `virtual_offset`/`virtual_len`), **not** the walker's virtual `Region`s; the `.eml` artifact bytes are untouched |
| 8 | `parse.py:291` (`_sniff`) and `:313-314` (`parse`) | `_sniff`, `parse` | `return _failure("cfb_msg_unsupported", "Phase 1 has no CFB reader")` (both sites) | open the container instead of refusing: a `cfb_msg` magic (sniffed or claimed) yields a real container, and a non-`__properties_version1.0` CFB yields `not_a_message` |

**Re-opening trigger (A2 / spec `:150-153`).** If a comparison of `walk(msg)` with
`walk(EmlContainer(an equivalent synthetic eml))` forces an edit to tiling or ordering inside `_walk_visit`, the
architecture decision is re-opened (the named fallback is a `MsgContainer` that builds `PartShape` itself, which
duplicates ~200 lines of `_walk_visit` and which the golden does not protect). Points 2, 4 and 5 above are the
only edits that touch the walker's own code, and each is a keyword/default addition, not a structural change.

## 9. The `value_codec` seam

```python
def header_fields_at(raw: bytes, start: int, end: int, *, value_codec: str = "latin-1") -> tuple[list[RawHeaderField], list[str]]:
    ...

def header_region(raw: bytes, result: WalkResult, *, max_work_units: int, value_codec: str = "latin-1") -> HeaderRegion:
    ...
```

- The default `"latin-1"` is the **current expression verbatim** at every decode site in `header_fields_at`
  (C `walk.py:483-485`, `:510`, `:525`, `:551`: `….decode("latin-1")`), so `.eml` is byte-identical.
- For `cfb_msg`, `header_region` is called with `value_codec="utf-8"` and `raw` is the virtual UTF-8 string, so
  `raw_value` and `HeaderRegion.text_decodes` carry the real text (A4). `header_region` passes the codec through to
  `header_fields_at`; its other readers (`decode_encoded_words`, `parse_address_list`, `parse_date`) already slice
  `raw` bytes and are unaffected.
- Rejected alternative (A4): writing non-ASCII as RFC 2047 encoded-words, because it makes `raw_value` a lie
  about the stream -- and `raw_value` is read by `text.py:340`, `attach.py:627/637`, `selection.py:292/529`.

## 10. The `.eml` golden: capture, and the one permitted re-record

- **File:** `tests/golden/eml_golden.json` (new; captured in **Turn 1b.0c**, before the first frozen-module edit,
  rule 2 / A6).
- **What it pins:** the serialized `EmailDocument`, the `WalkResult`, `resolve_span` samples (the C2 identity
  guard), the `CapRecord`s, the two store artifacts (the walk artifact and the document artifact) with their keys,
  and the `ParseResult`, over the committed `.eml` corpus.
- **Format:** a single committed JSON file, one record per pinned fixture, with a header naming the corpus
  version and the schema version it was captured at (`"6"` once 1b.1 lands; `"5"` when 1b.0c writes it).
- **Nothing regenerates it silently:** the test compares bytes and fails on any diff; recording is an explicit,
  named command (`tools/update_eml_golden.py`, built in 1b.0c) run in the same commit as the change that caused it.
- **Both interpreters:** checked on 3.14 and 3.11 with a **recorded waiver**, not a silent skip (the two
  interpreters differ only in a recorded-heading field, never a pinned value; the waiver names the field).
- **The one permitted re-record (1b.1):** the bump in section 1 changes the serialized shape, so the golden is
  re-recorded in **1b.1, the same commit as the bump**. A test
  (`tests/test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys`) asserts the diff between
  the 1b.0c golden and the 1b.1 golden is **exactly** the following, and nothing else:

  - the **walk artifact's pinned value** (the `WalkResult`) is **byte-identical**: it carries the walker's shapes
    and no `PartRecord`/`HeaderField`, so it holds no schema version in its bytes (C `walk.py:351-361`);
  - the **document artifact** differs by exactly the `output_schema_version` value (`"5"` -> `"6"`), one
    `"stream_ref": null` key per `PartRecord` and `HeaderField`, and (D2 correction, Turn 1b.1) one
    `"embedded": null` key per `AttachmentOccurrence` -- no fourth class of difference (C `store.py:229-270`);
  - the **store keys/paths that name `OUTPUT_SCHEMA_VERSION`** move by exactly that version string
    (`store.artifact_key`'s `walk_key`, C `store.py:148-155`; `assemble.document_key`, C `assemble.py:130-147`);
  - `ParseResult`, every `CapRecord` value, `container_hash`, every `part_id`, every `sha256` and every span are
    **byte-identical**.

  **D2 (Turn 1b.1).** Part (Z) adds `AttachmentOccurrence.embedded`, and `AttachmentOccurrence` records are
  inside every `.eml` document that has attachments, so the re-recorded document gains `"embedded": null` per
  occurrence **in addition to** the `"stream_ref": null` keys and the version value. Those three classes are the
  whole permitted diff; the falsifier in
  `tests/test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys` fails on a stray fourth.

  For a `cfb_msg` document the store artifact additionally carries the CFB sector accounting and the **source-only**
  span table (`PersistedSpanRow`, section 7); no `virtual_offset`/`virtual_len` is persisted (C2). Any other diff
  is a defect.

## 11. Existing tests that must change (each verified by opening the test)

Verified in this turn `(C)`; line numbers are 1-based in the current tree. This list is **complete**: a test not
here that fails after the bump is a defect. One rule underlies the scope rows below: **the library never imports
`olefile`; only `tests/` and `tools/` do** (O4/O7).

| test | line | assertion / constant that changes | why |
|---|---|---|---|
| `tests/test_licence_audit.py::test_olefile_is_not_a_declared_dependency` | 165, 168-169 | `assert "olefile" not in names` / `assert "olefile" in _notice_rows()` | `olefile` becomes a `[dev]` extra (O4); the test flips to "olefile is declared, under `[dev]` only, and never under runtime dependencies" |
| `tests/test_licence_audit.py` (`NOTICE_ONLY`, module) | 44, 51 | `NOTICE_ONLY = {"olefile": "the future .msg reader …"}` | `NOTICE_ONLY` shrinks to `{}`; `AUDITED_LICENCES["olefile"]` stays `BSD 3-Clause` |
| `tests/test_phase1_scope.py::test_the_modules_are_exactly_the_phase_1_set` | 196, 201 | `assert library == EXPECTED_LIBRARY` | `EXPECTED_LIBRARY` (34-59) gains `cfb.py`, `mapi.py`, `msgcontainer.py` |
| `tests/test_phase1_scope.py::test_no_library_module_imports_later_phase_machinery` | 81, 83, 219, 230 | `BANNED_IMPORTS` drops `"cfb"`; `"olefile"` **stays** | the library now owns `emailextract/cfb.py`, and the three new modules (`cfb`, `mapi`, `msgcontainer`) import only package-local names, so `"cfb"` comes off; `"olefile"` stays banned -- the library never imports it (O4/O7) |
| `tests/test_phase1_scope.py::test_no_msg_cfb_routing_recursion_or_threading_exists` | 112-115, 245, 262 | `FORBIDDEN_NAME_PARTS` drops `"cfb"` (and `"msg_reader"`/`"read_msg"` **only if** the build names such a function); `"olefile"` **stays** | the library now owns a CFB reader, so the CFB name fragment is no longer later-phase machinery; Turn 1b.5 names and justifies each `msg_reader`/`read_msg` fragment it actually adds; `"olefile"` stays pinned -- the library never names it |
| `tests/test_phase1_scope.py::test_no_runtime_dependency_beyond_docextract_core` | 271, 276-277 | `assert len(dependencies) == 1` … `== "docextract-core"` | stays valid only because `olefile` goes to `[dev]`, never runtime |
| `tests/test_parse_entry.py::test_parse_sniffs_cfb_msg_as_a_named_error` | 92, 97 | `assert result.error.reason_id == "cfb_msg_unsupported"` | the sniff no longer refuses (point 8) |
| `tests/test_parse_entry.py::test_parse_container_kind_overrides_the_sniff` | 140-142 | `assert claimed_cfb.error.reason_id == "cfb_msg_unsupported"` | a claimed `cfb_msg` now opens |
| `tests/test_parse_entry.py::test_limits_construction_is_the_only_named_error_raised` | 189-196 | `assert NAMED_ERROR_REASONS == (…, "cfb_msg_unsupported", …)` | the tuple swaps to `cfb_directory_loop`, `cfb_header_unsupported` (section 3) |
| `tests/test_status_reasons.py::test_reason_table_has_exactly_the_spec_rows` | 28-30, 67, 71-72 | `"skipped": ("size_cap", …, "header_bytes_cap")` | `EXPECTED_REASON_TABLE` gains the three CFB reasons |
| `tests/test_status_reasons.py::test_every_reason_belongs_to_exactly_one_status` | 76, 83 | `assert len(owners) == 11` | count `11` -> `14` |
| `tests/test_contract_phase1.py::test_run_record_carries_every_cap_and_the_two_new_reasons` | 99, 102-108 | `assert REASON_TABLE[Status.SKIPPED] == (…)` | the `SKIPPED` tuple grows |
| `tests/test_contract_phase1.py::test_output_schema_version_is_four` | 149, 151, 156 | `assert versions.OUTPUT_SCHEMA_VERSION == "5"` | the bump; the test name is already stale and is renamed |
| `tests/test_contracts.py` (`_email_document` helper) | 239 | `environment={"olefile": "installed"}` | the `olefile` environment literal; `output_schema_version="1"` at 241 stays (it is not the constant) |
| `tests/test_container.py::test_the_fake_container_is_a_second_container_kind_without_cfb_code` | 72, 80, 81 | `assert "olefile" not in sys.modules` / `"compoundfiles" not in sys.modules` | survives as the real guard, but must be reworked so a fresh import of `emailextract` still excludes `olefile` |
| `tests/test_behavior_ledger.py` (`contracts` lines) | 125, 127, 192, 233, 240, 246, 248, 258, 266 | `assert strings["contracts"] == versions.OUTPUT_SCHEMA_VERSION` etc. | the `contracts` fingerprint is keyed by `OUTPUT_SCHEMA_VERSION` (C `behavior_ledger.py:84`); a `"6"` line is appended |
| `tests/ledger/behavior_ledger.json` (`contracts` data) | 7 | `"5": "71cca1bc…"` | a `"6"` line is appended in the same commit (category 3) |
| `tests/test_ingest.py::test_a_non_message_file_is_a_recorded_skip_from_the_entry_point` | 208, 212, 217 | `assert reasons["cfb.msg"] == "cfb_msg_unsupported"` | a CFB magic is no longer a skip reason; the case becomes `not_a_message` (a non-message CFB) |
| `tests/test_assemble.py::test_the_projection_versions_are_the_constants_names_and_values` | 187, 196 | `assert document.output_schema_version == versions.OUTPUT_SCHEMA_VERSION == "5"` | the bump |
| `tests/test_store.py::test_a_walk_artifact_is_keyed_by_its_versions` | 166, 169 | `assert versions.OUTPUT_SCHEMA_VERSION == "5"` / `assert artifact.output_schema_version == "5"` | the bump |
| `tests/test_store.py::test_the_document_key_is_the_hashed_inputs_and_nothing_else` | 209 | `assert artifact.output_schema_version == "5"` | the bump |
| `tests/test_turn_declarations.py::test_every_undeclared_test_fails_the_declaration` | 581, 584-585 | `assert not problems, f"collected tests nobody declared: {problems}"` | every new 1b `def test_*` must be declared (section `phase1b-ledgers.md`) and its turn added to `BUILT_TURNS` |
| `tests/test_phase0_gaps.py::test_the_registry_in_force_is_85_ids_and_the_prune_holds` | 166, 175 | `assert len(registry) == 88` (was `85`) | the registry in force grows by exactly the three new `msg.*` ids (`85` -> `88`) -- this turn's deliberate `phase0-gaps.md` edit; the function keeps `85` in its name because it is in the frozen `PHASE0_BASELINE` of `tests/test_turn_declarations.py` (`:314`), so the name stays. **This is the one test already edited in 1b.0a.** |

Also verified, and **not** on the change list (so a failure there is a defect):

- `tests/test_closed_enums.py::test_container_kind_is_exactly_two` (`:54-56`) -- `ContainerKind` keeps exactly
  `rfc822`/`cfb_msg`, so it does not move.
- `tests/test_phase1_scope.py::test_the_package_imports_with_no_sibling_and_no_chardet` (`:133`, `:295`, `:305`) --
  the import probe keeps `"olefile"` in its `BLOCKED` set (C `:133`), which is exactly the "the library never
  imports `olefile`" guard; with `olefile` staying blocked for the library the probe's own constant does not move.
- `tests/test_phase0_gaps.py::test_the_registry_and_the_document_agree_both_ways` (`:155`, `:159-160`) -- holds
  once the three `### \`msg.*\`` entries exist.
- `tests/test_parse_entry.py:225`, `tests/test_seeded_splitter_fuzz.py:441,445` (`in NAMED_ERROR_REASONS`),
  `tests/test_text.py:730` (`in VERBATIM_REASONS`), `tests/test_ingest.py:202` and
  `tests/test_hostile_set.py:338` (`in SKIP_REASONS`) are membership checks and are **tolerant** of the swap.
- `tests/test_phase1_gap_gate.py` and `tests/test_gap_falsifiability.py` are unaffected unless the new reasons
  or CFB error ids are surfaced in `evals/falsify.py`'s catalogues; the Phase 1b gap gate is a new file
  (`tests/test_phase1b_gap_gate.py`, Turn 1b.10).

## 12. Contradictions found

- **C1. Rule 2 versus the exit criterion (spec-internal).** `phase1b-build-spec.md:42-51` (rule 2) permits only
  "the version-stamp consequences of the one schema bump" to move, but the exit criterion at `:361-365` lists
  category (2) as "the one `OUTPUT_SCHEMA_VERSION` bump and its **direct consequences (record shapes,**
  `REASON_TABLE`, the gap registry, `NAMED_ERROR_REASONS`), re-recorded in the same commit". A new optional
  field is a record-shape change, not a version stamp, so the golden (which pins the serialized `EmailDocument`)
  **necessarily** moves. **Resolution:** the exit criterion wins (it is the later, more specific wording); the
  golden is re-recorded in 1b.1 and section 10 pins the exact permitted diff. The design does not address the
  golden, so it does not arbitrate.
- **C2. `cfb_difat_extended`: design D13 vs `phase0-gaps.md`.** `email-extraction-design.md:784` says "Extended
  DIFAT is a named gap, not a crash"; `phase0-gaps.md:615-621` says the reader "records the extended form and
  reads through it". Owner decision **O1** resolves it toward read-through (exceeds D13's letter); design
  revision 4 rewrites both. Recorded again here so a later reader sees it was deliberate.
- **C3. "seven sector classes" (spec `:63`, `:156`, `:311`).** The spec lists **eight** classes
  (`header, DIFAT, FAT, miniFAT, directory, a named stream's sector, free, slack`) and then calls them "seven".
  Section 6 defines eight and the sum-of-eight equals the file length; "seven" is a miscount.
- **C4. `msg.fat_cycle` / `msg.directory_loop` as gap ids.** The spec's risk list and several draft statements
  call them gap ids; A8 says they are hostile **fixtures**, not ids. Section 2 and `phase0-gaps.md` follow A8:
  a FAT cycle is a per-stream `Status.TRUNCATED`, never a gap id of its own.
- **C5. `ContainerStreamRef` side table vs field.** The spec (`:30-31`, `:177`) leaves it open ("optional field
  ... or a side table"); the debate (`:412-413`) leaves it open too. R1 decides **field**; no contradiction to
  report beyond the fact that both options were live until now.

## 13. Open questions left to the owner

- **Q1 (P1 layout).** Signed/encrypted mail: owner decision O8 is "class recorded, no body, never verified"
  until probe P1 shows whether a signed item carries a readable body or an opaque attachment. If P1 shows a
  readable body, O8's split (encrypted-only -> `Status.ENCRYPTED`; signed-only readable -> `PARSED`) is
  re-opened for the owner, not decided here.
- **Q2 (P3 aggregate).** Whether the extended DIFAT chain occurs in the owner's corpus decides how much O1's
  read-through path matters; the path is built either way (it is bounded), but the fixture's real-versus-synthetic
  weight moves.
- **Q3 (`synthetic` record refs).** The shape includes `axis = synthetic` on a **record**. In practice the root
  part and any synthesized MIME boundary are synthetic; whether the build should attach a `stream_ref` to a
  `PartRecord` for a synthetic leaf at all (versus leaving it `None` and carrying `synthetic` only in the span
  table) is a build-turn judgment. The contract allows both; Turn 1b.5 picks one and states it in
  `docs/design/msg-architecture.md`.

Anything further that the evidence does not settle is written here rather than picked silently.
