# Phase 1b sidecar facts (Turn 1b.0a specification; built in Turns 1b.2 to 1b.10)

A sidecar cannot name a fact the oracle has not declared: `emailextract/evals/l1.py`'s `check` raises
`OracleError` on "a label naming a fact the oracle does not model at all" (C), and `labels.load_sidecar`
validates a fact id's shape only. So every fact id below is declared in `FACTS` (with its phase and, until its
producer ships, no measurer) **before** any Turn 1b fixture types a single sidecar. This document is that list,
written in Turn 1b.0a so the fixture turns have an exact brief and the value shapes are fixed in advance. Form
and rigor follow `docs/design/phase1-facts.md`.

Rules this document fixes (the Phase 0/1 conventions, unchanged):

- **A phase is one `int`.** Phase 0 = the skeleton walker; Phase 1 = the RFC 822 parser; Phase 3 = threading
  and time evidence. **A Phase 1b fact declares `phase = 1`** (R13). Reasons: Phase 1b is the **container half
  of the same phase-1 parse layer** (the design calls it "its own phase" for scheduling, not for the fact
  vocabulary); the FACTS ledger has one `phase1` list and the phase1-ledgers rule is explicit -- "there is no
  `phase 1.5`"; and the Phase 1 exit gate is run at `gates.PHASE1_EXIT_PHASE = 1` (C `gates.py:463`) while
  `l1.CURRENT_PHASE` stays `0` (C `l1.py:83`, asserted by `tests/test_facts_ledger.py:51`). Phase 2 (routing)
  is `2`; Phase 1b is **before** routing and is not `2`. A Phase 1b fact therefore joins the `phase1` set
  unchanged, and a change to its phase fails the suite unless the pinned ledger changes in the same commit.
- **A fact's value is compared by plain equality** unless its `Measure` names a `compare`. No new sparse fact:
  every new Phase 1b fact's sidecar names the rows it asserts, in full; an empty corpus of rows is `[]`.
- **A gap id never gets a new fact type.** The `msg.*` gaps ride the existing two channels (R14): part-level
  gaps in `part.gaps` (`[[part, [gap_id, ...]], ...]`) and document-level gaps in `gaps.later`
  (`[[gap_id, locator, phase, reason], ...]`). This matches "no new gaps fact type is introduced"
  (`phase1-facts.md`) and avoids a duplicate fact.
- **Coverage floors are declared from the catalogue's fixture counts** (R-floors below), never "whatever is
  achieved" (spec rule 6 / operating rule 6). A floor with no room is raised here **before** the turn that
  measures it, never loosened silently.

## The Phase 1b fact table

`scope` is **message** (one row-set for the whole message) or **part** (one row per addressable part).
`floor` is the minimum number of committed `.msg` sidecars that carry the fact, with at least one carrying a
non-trivial, non-empty value. `—` in *measured by* means the fact is declared with no measurer until its turn
ships. The corpus is sized in `docs/design/phase1b-fixtures.md`.

| fact id | phase | scope | measured by | closed vocabularies | floor |
|---|---|---|---|---|---|
| `msg.container_layout` | 1 | message | 1b.5 | -- | 45 |
| `msg.sector_accounting` | 1 | message | 1b.5 | the eight sector classes | 45 |
| `msg.message_class` | 1 | message | 1b.4 | -- | 40 |
| `msg.body_streams` | 1 | message | 1b.5 | `plain` / `html` / `rtf` | 20 |
| `msg.recipients` | 1 | message | 1b.6 | `kind`; `address_type` | 10 |
| `msg.time_facts` | 1 | message | 1b.6 | time tag ids | 4 |
| `msg.codepage_ladder` | 1 | message | 1b.4 | `source_kind`; `encoding_source` | 8 |
| `msg.stream_faults` | 1 | message | 1b.3 | `fault`; mapped status reason | 2 |
| `msg.attachments` | 1 | part | 1b.7 | attachment methods; filename source | 8 |
| `msg.embedded_summary` | 1 | part | 1b.7 | -- | 2 |
| `msg.storage_tree_sha256` | 1 | part | 1b.7 | -- | 2 |
| `gaps.later` *(existing)* | 1 | message | -- | gap ids | 5 |

The table lists **11 new fact ids** and one existing (`gaps.later`); the four Phase 0 facts and the Phase 1
facts (`document.axes`, the `headers.*`, `body.*`, `attach.*`) are reused unchanged.

**Coverage floors, declared from the catalogue (spec rule 6).** The catalogue
(`docs/design/phase1b-fixtures.md`) has **48 committed `.msg` fixtures** and one `.eml`. Every `.msg` fixture
carries a readable container, so `msg.container_layout` and `msg.sector_accounting` are floored at **45** (room
for hostile fixtures whose layout is deliberately broken before the class is read). `msg.message_class` 40
(the class is read before any body; the two hostile CFB fixtures and the pair's `.eml` are excluded),
`msg.body_streams` 20 (every fixture with a body stream), `msg.recipients` 10, `msg.codepage_ladder` 8,
`msg.attachments` 8 (part-scoped), `msg.time_facts` 4, `msg.embedded_summary` and `msg.storage_tree_sha256` 2
(`msg_embedded_message`, `msg_embedded_depth_two`; `msg_outlook_layout_handbuilt` carries one too, giving room),
`msg.stream_faults` 2 (`msg_fat_cycle`, `msg_truncated_stream`). Each floor is comfortably exceeded by the
catalogue's own counts (below): no floor is a stretch, and every floor is a **declaration**, not an
observation.

## Value shapes, with a hand-typed JSON example each

The examples are **synthetic** (no real or employer mail) and ASCII-only; a `part` is the `1.2.3` locator
(non-stable, D12); `"<hex>"` stands for a lowercase hex sha256.

### `msg.container_layout` — the CFB identity and layout

Shape: `[cfb_version, sector_size, mini_sector_size, mini_cutoff, sector_count, directory_entries]`, all ints.
`cfb_version` is `3` or `4`; the three size fields are byte counts.

```json
[3, 512, 64, 4096, 384, 129]
```

### `msg.sector_accounting` — the eight sector classes, summing to the file length

Shape: `[[class_name, byte_count], ...]`, one row per class in the fixed order
`header, difat, fat, minifat, directory, stream, free, slack`. The eight `byte_count`s sum to the file length;
`free` and `slack` are explicit (never folded into `stream`).

```json
[["header", 512], ["difat", 512], ["fat", 1024], ["minifat", 512],
 ["directory", 2048], ["stream", 186880], ["free", 0], ["slack", 512]]
```

### `msg.message_class` — the message class, verbatim

Shape: a single non-empty string (the class value, never a mapping to a friendlier name).

```json
"IPM.Note"
```

### `msg.body_streams` — the body streams present

Shape: a sorted list over the closed set `plain`, `html`, `rtf` (the design's fixed order). Present-but-empty is
present (`msg_zero_length_body`): a `0x1000` stream of length 0 is `["plain"]`, not `[]`.

```json
["plain", "html"]
```

### `msg.recipients` — the recipient rows (beside the headers, never merged into them)

Shape: `[[kind, display_name | null, address | null, address_type], ...]`, one row per recipient table row.
`kind` is `to` / `cc` / `bcc` (from the recipient-type property); `address_type` is `smtp` (an SMTP address),
`ex` (the Exchange address type, kept verbatim as the raw address form), or `unknown`. `display_name` and
`address` are `null` when absent. Recipient rows are `value_source = mapi_property` facts, distinct from the
header stage's address rows, so a disagreement is visible (D2/D13).

```json
[["to", "Ada Lovelace", "ada@example.test", "smtp"],
 ["bcc", null, "/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2", "ex"]]
```

### `msg.time_facts` — raw time properties, as facts (never events)

Shape: `[[tag_hex, filetime_hex, utc], ...]`, one row per time property present. `tag_hex` is the 4-digit
lowercase hex tag; `filetime_hex` is the 16-digit lowercase hex of the raw `u64` (**lossless, canonical**);
`utc` is the ISO-8601 UTC rendering (a convenience, never the compared value). No `TimeEvent` is emitted.

```json
[["0039", "01da8f3c9a1b2d40", "2026-10-11T12:34:56Z"],
 ["0e06", "01da8f3c9a1b2d40", "2026-10-11T12:34:56Z"]]
```

### `msg.codepage_ladder` — the code pages and the ladder rung that fired

Shape: `[[surface, source_kind, declared_cp, encoding_source], ...]`, one row per decoded 8-bit surface (the
transport-header stream, a plain body, an 8-bit string property). `surface` is the locator (`1.1`, `1.2`) or
`headers`; `source_kind` is `internet`, `message` or `none` (the ladder rung's code page); `declared_cp` is the
code-page number the rung used, or `null` when `source_kind = none`; `encoding_source` is an `EncodingSource`
member (`internet_cpid`, `message_cpid`, `ascii`, `utf8_strict`, `windows_1252`).

```json
[["headers", "internet", 28591, "internet_cpid"],
 ["1.2", "none", null, "utf8_strict"]]
```

### `msg.stream_faults` — the per-stream chain faults

Shape: `[[stream, fault, reason], ...]`, one row per faulted stream. `fault` is the CFB chain fault
(`cycle` / `out_of_range` / `short_chain`); `reason` is the mapped `Status.TRUNCATED` reason
(`declared_length_mismatch` for a cycle, `stream_ended_early` for out-of-range and short chain). An empty list
means no fault (single meaning).

```json
[["__substg1.0_10130102", "cycle", "declared_length_mismatch"]]
```

### `msg.attachments` — the attachment rows (part scope)

Shape: `[[part, method, filename_raw, filename_decoded, mime_tag, cid, hidden, inline, size, sha256], ...]`,
one row per attachment occurrence. `method` is the numeric MAPI attachment method (`1` by-value, `2` by-reference,
`3` by-reference-resolve, `4` by-reference-only, `5` embedded-message, `6` OLE), rendered as an int. `filename_raw`
and `filename_decoded` are `null` when the ladder found none; the filename ladder is long (`0x3707`) over short
(`0x3704`) over display (`0x3001`), and **both** the raw and the decoded name are kept (a hostile name is never a
path). `mime_tag` (`0x370E`) and `cid` (`0x3712`) are `null` when absent. `hidden`/`inline` are the hidden and
inline flags. `size`/`sha256` are the attachment's own bytes (a pass-through's are the stream's).

```json
[["1.2", 1, "report.pdf", "report.pdf", "application/pdf", "<cid1@example.test>", false, true, 4096, "<hex>"]]
```

### `msg.embedded_summary` — the embedded message's own summary (part scope)

Shape: `[part, message_class, subject | null, has_transport_headers, recipient_count, attachment_count]`, one row
per embedded-message attachment (depth 1). The embedded message is **read and recorded, not recursed**
(`children_axis` stays not built). `subject` is `null` when the embedded message has no subject property.

```json
[["1.2", "IPM.Note", "Fwd: hello", true, 1, 0]]
```

### `msg.storage_tree_sha256` — the embedded storage's canonical digest (part scope)

Shape: `[part, "<hex>"]`, one row per embedded-message storage. The digest is over a **defined canonical walk**
of the storage (entries sorted by name; each name, type, size and stream bytes), documented in
`docs/design/msg-architecture.md`, and is **never** claimed to equal any `.msg` file's hash (an embedded
storage has no file bytes).

```json
[["1.2", "<hex>"]]
```

### `gaps.later` — the `msg.*` gaps a later phase records (existing; shape unchanged)

Shape: `[[gap_id, locator, phase, reason], ...]`, kept as typed. Every gap id it names is a registry id
(`docs/design/phase0-gaps.md`); the Phase 1b document-level gaps (`msg.transport_headers_absent`, and the
registered `msg.*` ids first emitted here) ride it, exactly as the Phase 1 gaps do.

## The Phase 0 and Phase 1 facts: unchanged, and what stays

The Phase 0 fact list in `emailextract/evals/l1.py` and the Phase 1 facts
(`docs/design/phase1-facts.md`) are **not edited** by Phase 1b for these ids, and their shapes stay exactly as
the committed sidecars type them: `container.sha256` (0), `container.size_bytes` (0), `headers.fields` (0),
`part.tree` (0), `part.regions` (0), `part.gaps` (0), `body.preamble_epilogue` (0), `decode.chain` (0),
`body.content_sha256` (0), `labels.undetermined` (0), and the 20 phase-1 facts (`document.axes`,
`headers.projection`, `headers.addresses`, `headers.date`, `headers.decoded`, `headers.parameters`,
`body.text`, `body.alternative_group`, `body.selection`, `body.html_spans`, `body.cid_refs`,
`body.plain_effectively_empty`, `body.quote_boundaries`, `body.view_levels`, `attach.manifest`,
`attach.types`, `attach.filename`, `attach.decorative`, `attach.cid_use`, `gaps.later`).

Two Phase 0 facts need a Phase 1b note:

- **`part.regions`**: the walker's `Region` list. For a `cfb_msg`, the walker's regions describe the reader's
  own virtual framing and are **not persisted** (section 8, point 7 of `phase1b-contract.md`); the fact still
  exists (it is a walker fact), but a `.msg` sidecar's `part.regions` is typed from the virtual framing and the
  no-silent-drop assertion for `.msg` is made on **sectors** (`msg.sector_accounting`), never on these regions.
- **`decode.chain`**: for a `.msg` leaf, `used_charset`/`encoding_source` are the **MAPI ladder's** (overwritten
  post-walk, section 8, point 5). The sidecar types the overwritten values; no `declared_charset`-only reading
  is accepted.

## Consequences for `tests/ledger/facts_ledger.json`

The pinned ledger (`docs/design/phase1-ledgers.md` section (b)) is `{"phase1": [...], "deferred": []}`.
`tests/test_facts_ledger.py` compares `l1.FACT_PHASES` (from `l1.FACTS`) against it. In the turn that declares
the Phase 1b facts (Turn 1b.10, the close; the ids may also be declared earlier as they ship):

- `phase1` gains the **11 new ids** above (the 20 existing phase-1 ids stay); `deferred` stays `[]` (a Phase 1b
  fact is not deferred -- it is phase 1).
- `tests/test_facts_coverage.py` (the coverage gate) gains the 11 floors above and the fixture counts from the
  catalogue. The floor for each new id is the table's, read from the same `FLOORS` mapping.
- `l1.LIVE_GAP_IDS` gains the Phase 1b gap ids that the exit gate compares
  (`msg.transport_headers_absent`, `msg.class_not_ipm_note`, `msg.property_tag_unknown`,
  `msg.named_property_unresolved`, `msg.codepage_unresolved_ladder_used`, `msg.recipient_table_unreadable`,
  `msg.attachment_method_unsupported`, `msg.embedded_depth_cap`, `msg.stream_truncated`,
  `msg.rtf_to_text_unsupported`, `msg.cfb_difat_extended`, `headers.mapi_header_property_disagree`), because
  `gates` compares `gaps.later` rows "whose phase column is `PHASE1_EXIT_PHASE`" **only when the id is in
  `LIVE_GAP_IDS`** (C `gates.py:505-525`). `EMITTABLE_GAP_IDS` in `evals/falsify.py` is read off `LIVE_GAP_IDS`
  so a new live id cannot be added silently (C `falsify.py:401`).

No fact's **type shape** moves; only the set of declared phase-1 ids and the floors grow, both in the same
commit as the code that measures them.

## Findings: where a decision meets a typed label

Decision 12 rule: a sidecar is never edited, so a decision that contradicts a typed label is a **finding**.
Phase 1b's new facts are typed fresh (no committed sidecar names any of them: the `msg.*` strings do not appear
in any `fixtures/**/*.expected.json`, `(C)` grep). So the only findings are forward-looking:

1. **`part.regions` on a `.msg`** is the one Phase 0 fact whose *meaning* shifts for the new container (the
   walker's virtual framing, not a persisted address space). It is recorded here so the sidecar author does not
   read a virtual offset as a citable one; the fact's shape and phase do not move.
2. **`decode.chain.encoding_source` on a `.msg` leaf** is overwritten from the MAPI ladder (section 8, point 5).
   The `EncodingSource` enum already has every needed member (`internet_cpid`, `message_cpid`, `ascii`,
   `utf8_strict`, `windows_1252`; C `model.py:134-143`), so no enum moves and no label is invalidated.
3. **The `attach.*` facts** for a `.msg` are the same facts (a `.msg` attachment is an attachment); the
   `msg.attachments` fact is the MAPI-side row set, and the two are complementary, not duplicates.

## Open questions

- **The `msg.codepage_ladder` row key.** The shape uses `surface = headers | <locator>`. If Turn 1b.4 finds a
  surface that is neither (e.g. a string property outside the header stream and outside a body), a third label
  form is added here **before** any sidecar uses it, never silently. **Decided in Turn 1b.10a:** a decoded
  **8-bit string property** (a `001E` value outside the transport stream and outside a body -- the `0037`
  subject of every `msg_string8_*` fixture is one) is a surface, and its label is `prop:<tag hex>` (the
  property tag, four lowercase hex digits, e.g. `prop:0037`). The rows are, in order: `headers` (the
  transport-header stream), the body leaves by their locator, then the string properties in property order,
  and a `001F` value (no ladder) has no row. Without this form `msg_string8_1252` -- a bare `001E` subject and
  no body -- would have an empty ladder, which the loader refuses to label at all.
- **`msg.attachments.method` as an int.** The MAPI method is an int in the stream (`0x3705`); the fact renders it
  as an int, not a name, so no method is frozen by a friendly string (spec risk 6). If a later turn wants a name,
  it is a projection over the int, added here first.
- **`msg.sector_accounting` and a `cfb_msg` whose file is truncated.** A file truncated mid-sector has a partial
  tail; the eighth class `slack` covers the bytes to the next sector boundary and the tail is recorded as
  `slack`, so the sum still equals the file length. If Turn 1b.3 finds this is not true for a real mutant, it is
  reported, not papered over.
