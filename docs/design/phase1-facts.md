# Phase 1 sidecar facts (Turn 1.0a specification; built in Turn 1.0b)

A sidecar cannot name a fact the oracle has not declared: `emailextract/evals/l1.py`'s `check` raises
`OracleError` on "a label naming a fact the oracle does not model at all", and
`labels.load_sidecar` validates a fact id's shape only. So **Turn 1.0b declares every fact id below in
`FACTS`** (with its phase and, for a fact whose producer has not shipped, no measurer) before Turn 1.0c
types a single sidecar. This document is that list, written in Turn 1.0a so 1.0b has an exact brief and
1.0c has an exact set of value shapes to type against.

Rules this document fixes (they match the Phase 0 conventions in `docs/design/phase0-build-spec.md`):

- **A phase is one `int`.** Phase 0 = the skeleton walker; Phase 1 = the RFC 822 parser (header
  projection, body views, attachment manifest); Phase 3 = threading and time evidence. No fact's phase
  moves in this turn except where a section below says so, and a change to `FACTS`' phases fails the
  suite unless the **pinned fact-id ledger** changes in the same commit (Turn 1.0b;
  `docs/design/phase1-ledgers.md`).
- **A fact's value is compared by plain equality** unless its `Measure` names a `compare`; the only
  non-equality comparison in Phase 0 is `body.preamble_epilogue`'s sparse-row rule. **The sparse-fact
  convention is not used for any new fact**: every new Phase 1 fact's sidecar names the rows it asserts,
  in full, and a fact with an empty corpus of rows is written `[]` (an empty list keeps its single
  meaning -- genuinely empty).
- **A gap ids fact keeps the row shape of the gap registry** (`docs/design/phase0-gaps.md`): `part.gaps`
  is `[[part, [gap_id, ...]], ...]` and `gaps.later` is `[[gap_id, locator, phase, reason], ...]`.
- **Nothing here is measured in Turn 1.0a.** Every "measured by" turn is a later turn; every row is a
  *declaration*.

## The Phase 1 fact table

`scope` is **message** (one row-set for the whole message) or **part** (one row per addressable part, so
the rows tile the parts tree). `floor` is the **coverage floor per (fact x phase 1)**: the minimum number
of committed sidecars that carry the fact, with at least one carrying a **non-trivial, non-empty** value
(the required corpus is sized in `docs/design/phase1-fixtures.md`, whose families comfortably exceed every
floor). `—` in *measured by* means the fact is declared with no measurer until its turn ships.

| fact id | phase | scope | measured by | closed vocabularies | floor |
|---|---|---|---|---|---|
| `document.axes` | 1 | message | 1.9 | axis ids; `state`; axis reason ids | 80 |
| `headers.projection` | 1 | message | 1.1 | `parsed_kind` | 60 |
| `headers.addresses` | 1 | message | 1.2 | `state`; `reason_id` | 20 |
| `headers.date` | 1 | message | 1.3 | `zone_state` | 12 |
| `headers.decoded` *(existing)* | 1 | message | 1.1 | — | 8 |
| `headers.parameters` | 1 | message | 1.1 | `decode_state`; `fallback_reason` | 4 |
| `body.text` | 1 | part | 1.4 | `verbatim_precision`; `verbatim_reason` | 60 |
| `body.alternative_group` | 1 | part | 1.5 | — | 10 |
| `body.selection` *(existing)* | 1 | part | 1.5 | `Selection` | 10 |
| `body.html_spans` | 1 | part | 1.5 | — | 8 |
| `body.cid_refs` | 1 | part | 1.5 | — | 5 |
| `body.plain_effectively_empty` | 1 | part | 1.5 | `emptiness_rule` | 2 |
| `body.quote_boundaries` | 1 | part | 1.6 / 1.7 | `kind`; `rule_id` | 15 |
| `body.view_levels` | 1 | part | 1.6 / 1.7 | `rule_id` | 15 |
| `attach.manifest` *(existing)* | 1 | part | 1.8 | `Classification`; CTE names | 10 |
| `attach.types` | 1 | part | 1.8 | `state`; `winner`; reason ids | 12 |
| `attach.filename` | 1 | part | 1.8 | `decode_state`; `fallback_reason` | 10 |
| `attach.decorative` | 1 | part | 1.8 | `DecorativeHintState`; `rule_id` | 4 |
| `attach.cid_use` | 1 | part | 1.8 | `referenced` | 5 |
| `gaps.later` *(existing)* | 1 | message | — | gap ids | 5 |

The table lists **20 distinct fact ids**. The four marked *(existing)* (`headers.decoded`,
`body.selection`, `attach.manifest`, `gaps.later`) are the Phase 1 facts Phase 0 already declared in
`emailextract/evals/l1.py`; the other **16 are new in Turn 1.0b**.

## Value shapes, with a hand-typed JSON example each

The examples are **synthetic** (no real or employer mail); they are what a sidecar's `value` looks like,
not what any committed fixture currently holds. A `part` is the `1.2.3` locator (non-stable, D12); a span
is `[offset, length]` in **decoded code points** unless a fact says bytes.

### `document.axes` — the per-record axis fields (decision 6)

Shape: `[[axis_id, state, reason_id | null], ...]`, one row per axis the record carries. `axis_id` is the
closed tuple `attachment.status`, `attachment.route`, `document.times`, `document.thread_edges`,
`document.children`, `document.same_message_candidates` (a wildcard id is banned); `state` is
`value | absent | unknown`; `reason_id` is a member of `{not_built_in_phase1, "built"}` when
`state = unknown`, else `null`.

```json
[["document.times", "unknown", "not_built_in_phase1"],
 ["document.thread_edges", "unknown", "not_built_in_phase1"],
 ["document.children", "unknown", "not_built_in_phase1"],
 ["document.same_message_candidates", "unknown", "not_built_in_phase1"]]
```

In Phase 1 every document axis is `unknown(not_built_in_phase1)` (decisions 6 and 11), and every
attachment's `attachment.status`/`attachment.route` is likewise not-built (its rows live in
`attach.types`/the manifest, not here). The fact exists so the honesty rule is checkable: a Phase 1
record never presents a not-built axis as empty.

### `headers.projection` — raw beside parsed, one row per field

Shape: `[[ordinal, name, raw_value, parsed_kind, parsed_value], ...]`. The **raw value is the verbatim
field value** (folds kept, latin-1 view, D2); `parsed_kind` is `text | address_list | date_time |
message_id | message_id_list | unparsed`; `parsed_value` is the parsed scalar (or `null` where
`parsed_kind = unparsed`). The richer shapes are their own facts (`headers.addresses`, `headers.date`).

```json
[[0, "From", " Ada Sender <ada@example.test>", "address_list", "ada@example.test"],
 [2, "Subject", " Hello =?utf-8?B?4piF?=", "text", "Hello ★"],
 [3, "Date", " Tue, 4 Mar 2025 08:05:00 +0000", "date_time", "2025-03-04T08:05:00+00:00"],
 [5, "Received", " from relay.example.test by mx.example.test; Tue, 4 Mar 2025 08:05:01 +0000", "unparsed", null],
 [7, "References", " <a@example.test> <b@example.test>", "message_id_list", "<b@example.test>"]]
```

### `headers.addresses` — one span per address

Shape: `[[ordinal, field_name, [[raw_offset, raw_length, display_name, addr_spec, state, reason_id],
...]], ...]`. `raw_offset`/`raw_length` are **byte** spans into the raw message (D2: byte offsets are the
verbatim layer); `state` is `parsed | group | unparsed`; a group's members are the nested rows and a
zero-member group (`undisclosed-recipients:;`) is `[]`; `reason_id` is `null` unless `state = unparsed`
(`headers.address_unparsable`). IDN and SMTPUTF8 are verbatim (never IDNA-normalised).

```json
[[1, "To", [[40, 32, "Ben Receiver", "ben@example.test", "parsed", null]]],
 [1, "To", [[80, 24, null, null, "group", null], [90, 12, null, "cara@example.test", "parsed", null]]],
 [1, "Bcc", [[120, 30, null, "undisclosed-recipients:;", "group", null]]]]
```

### `headers.date` — the three zone states, offset and UTC

Shape: `[[ordinal, raw, zone_state, offset, utc], ...]`. `zone_state` is the **closed triple**
`zone_stated | zone_stated_minus_zero | zone_absent`; `offset` is the stated offset as `"+HHMM"`/`"-HHMM"`
or `null`; `utc` is the RFC 3339 UTC instant or a `["unknown", reason_id]` pair
(`headers.no_date`/`headers.invalid_date`) -- a missing or invalid date **never** sorts as an epoch.

```json
[[3, " Tue, 4 Mar 2025 08:05:00 +0000", "zone_stated", "+0000", "2025-03-04T08:05:00+00:00"],
 [3, " Tue, 4 Mar 2025 08:05:00 -0000", "zone_stated_minus_zero", "-0000", "2025-03-04T08:05:00+00:00"],
 [3, " Tue, 4 Mar 2025 08:05:00", "zone_absent", null, ["unknown", "headers.date_no_zone"]]]
```

`-0000` is recorded `zone_stated_minus_zero` and is **never read as `+0000`** (D2): the offset token is
kept, and the `utc` instant is the same instant a `+0000` would give only because there is no local-time
information to apply -- the *state* is what a reader must not lose.

### `headers.decoded` — the encoded-word decode (existing; shape unchanged)

Shape: `[[ordinal, decoded_text], ...]` -- already typed by
`fixtures/generated/rfc2047_folded_duplicate_received.expected.json` as `[[5, "Hello ★ folded subject"]]`
and **kept exactly as typed** (decision 12). A field whose encoded word is invalid additionally records
the gap `headers.encoded_word_invalid` (decision 5), which rides in `part.gaps`, not here.

### `headers.parameters` — RFC 2231 / RFC 2047 parameter decoding with the recorded fallback

Shape: `[[ordinal, field_name, parameter, decoded_value, decode_state, fallback_reason], ...]`, one row
per **structured parameter** the reader decodes (a `boundary`, a `charset`, a `name`, a `filename`).
`decode_state` is `decoded | fallback | undecodable`; `fallback_reason` is `null` unless
`decode_state = fallback`, when it is a member of `{encoded_word_in_parameter, empty_charset,
missing_continuation_index, duplicate_continuation_index}`. RFC 2231 continuations reassemble by index;
`name*` shadows `name` with the conflict recorded (decision 5).

```json
[[6, "Content-Type", "boundary", "b0-alt-20250304", "decoded", null],
 [6, "Content-Disposition", "filename", "résumé.pdf", "decoded", null],
 [6, "Content-Disposition", "filename", "run.log", "fallback", "empty_charset"]]
```

### `body.text` — per-part text and `verbatim_precision`

Shape: `[[part, text, verbatim_precision, verbatim_reason], ...]`. `verbatim_precision` is the closed pair
`exact | part_level`; `verbatim_reason` is `null` when `exact`, else a member of
`{cte_not_identity, multibyte_without_offset_map, decode_fallback}` (decision 8). **When `part_level` the
row carries no within-part byte span** -- that is the whole point of the state (D12): the MIME part's raw
span is always exact and lives in `part.regions`/`part.tree`, and the decoded char span is exact within
the named projection.

```json
[["1.1", "Hello there.\n\nOn Mon, Ada wrote:\n> earlier\n", "exact", null],
 ["1.2", "<html><body>Hi</body></html>", "part_level", "cte_not_identity"]]
```

The **coordinate space is the decoded text in code points, un-normalised** (no CRLF/LF folding); `text`
is the part's decoded text verbatim, so a reader cannot mistake a projection for the bytes.

### `body.alternative_group` — the alternative grouping (selection is `body.selection`)

Shape: `[[part, group_id], ...]`, one row per part inside a `multipart/alternative`. `group_id` is a
message-local stable id for the alternative group (the multipart's `part` locator plus an ordinal).
The **selection** is the retained fact `body.selection` (`[[part, "selected" |
"alternative_not_selected" | "n/a"], ...]`), kept as typed; the two facts are complementary, not
duplicates.

```json
[["1.1", "1"], ["1.2", "1"]]
```

### `body.selection` — the display rule (existing; shape unchanged)

Shape: `[[part, "selected" | "alternative_not_selected" | "n/a"], ...]`, kept exactly as typed by
`fixtures/generated/alternative_text_html.expected.json` and
`fixtures/generated/multipart_mixed_wraps_alternative.expected.json` (decision 12). Values are the
`Selection` enum's members.

### `body.html_spans` — the HTML element-to-projected-span map and the referenced cid set

Shape: `[[part, element_ordinal, tag, projected_offset, projected_length], ...]`, one row per **element**
of the own element tree (`htmltree.py`), where `projected_offset`/`projected_length` is the span the
element covers in the **HTML projection** (`htmltext.py`) -- the same code-point space the `>`-depth
spans live in, so "structural wins" has something to win against (decision 1). `element_ordinal` is the
element's document order. This fact is what a DOM quote rule locates itself by.

```json
[["1.2", 0, "html", 0, 34], ["1.2", 1, "body", 6, 28],
 ["1.2", 2, "blockquote", 11, 23], ["1.2", 3, "a", 12, 10]]
```

### `body.cid_refs` — the referenced-cid set

Shape: `[[part, [cid, ...]], ...]`, one row per part that references any `cid:` (an HTML `img src` or
`a href`); the list is the **set of cids the part references**, deduplicated. `attach.cid_dangling` and
`attach.cid_unreferenced` are decided against this set (they need it, decision-2 debate).

```json
[["1.2", ["logo@example.test"]]]
```

### `body.plain_effectively_empty` — the fact D16 resolves from a gap to a fact

Shape: `[[part, emptiness_rule], ...]`, one row per `text/plain` alternative that is **present but
effectively empty**. `emptiness_rule` is the closed pair `whitespace_only | stub_only`. Removing the gap
id from the registry (decision 6/D16; `docs/design/phase0-gaps.md`) does not change that the alternative
*is* present: the fact records the legal state, and matching and `body_digest` (D14) still consider every
non-empty alternative (D16).

```json
[["1.1", "whitespace_only"]]
```

### `body.quote_boundaries` — per boundary: rule id, kind, ordinal, per-line prefix depth, span

Shape: `[[part, view, rule_id, kind, ordinal, [prefix_depth, ...], span_offset, span_length], ...]`, one
row per boundary **per view** (D3). `kind` is the closed five `quote | forward | signature | list_footer
| unknown`; **only `kind = quote` rows advance `ordinal`** and `ordinal` is the rank within the view;
`prefix_depth` is the per-line `>`-family depth over the boundary's lines (decision 2/3: per line, never a
per-view scalar); `rule_id` is one of the named table rules (`gt_family`, `on_wrote_en`,
`outlook_flat_en|de|fr`, `forward_banner`, `original_message_dashes`, `dash_dash_space`,
`list_footer_underscores`, `list_footer_subscribed`, `gmail_quote`, `blockquote_type_cite`,
`outlook_divrplyfwd`, `outlook_appendonsend`, `thunderbird_moz_cite_prefix`,
`thunderbird_moz_forward_container`). `span_offset`/`span_length` are in the view's code points.

```json
[["1.1", "plain", "on_wrote_en", "quote", 1, [0, 0, 0, 0], 30, 260],
 ["1.1", "plain", "dash_dash_space", "signature", 0, [0, 0], 290, 18],
 ["1.2", "html", "gmail_quote", "quote", 1, [0, 0], 11, 23]]
```

A `forward` row is level 0 (owner decision 15): an inline forward is never the sender's quoted prior
words, so a message with only a forward banner has no `quote` row and no `quoted` span.

### `body.view_levels` — per view, the resolved level and its resolution rule id

Shape: `[[part, view, level, resolution_rule_id], ...]`, one row per **view** (not per span). `level` is
the derived rank (`level = ordinal` where a structural `quote` rule fired in the span, else
`level = prefix_depth`, decision 2) and `resolution_rule_id` names the rule that resolved it. Ordinal and
depth are **stored, never averaged**; the level carries its rule id so no consumer has to re-derive it.

```json
[["1.1", "plain", 1, "on_wrote_en"], ["1.2", "html", 1, "gmail_quote"]]
```

`view.quote_level_disagreement` (the predicate of decision 2) rides in `part.gaps`, not here.

### `attach.manifest` — the attachment occurrences (existing; shape unchanged)

Shape: `[[part, filename, declared_mime, cid, disposition, transfer_encoding, content_sha256, size],
...]`, kept exactly as typed by the three committed sidecars (decision 12). `declared_mime` is the
**projected value** of the `TriValue` verdict: the verdict's `value` when its state is `VALUE`, else
`null` (see the Findings below -- this is what keeps the three labels valid under decision 6). `cid` is
`null` when there is no Content-ID.

### `attach.types` — the three `TriValue` verdicts, the winner and the disagreement

Shape: `[[part, declared_mime, magic, container_introspection, winner, disagreement], ...]`, one row per
attachment occurrence. Each verdict is a triple `[state, value | null, reason_id | null]` where `state`
is `value | absent | unknown`. `magic` consulted with nothing matched is `["value", "unrecognized",
null]`; not computed is `["unknown", null, reason_id]`; `container_introspection` is `["unknown", null,
"not_built_in_phase1"]` until Phase 2. `winner` is `magic | declared_mime | container_introspection |
null` (order: magic over declared_mime over container_introspection where known); `disagreement` is a
bool, **true iff at least two verdicts are `value` with a media-type family and the families number >= 2**.

```json
[["1.2", ["value", "application/pdf", null], ["value", "pdf", null],
  ["unknown", null, "not_built_in_phase1"], "magic", false],
 ["1.3", ["value", "text/plain", null], ["value", "zip", null],
  ["unknown", null, "not_built_in_phase1"], "magic", true]]
```

### `attach.filename` — the raw filename and its RFC 2231 decode with the recorded fallback

Shape: `[[part, filename_raw, decode_state, decoded_value, fallback_reason], ...]`, one row per
attachment occurrence that carries a filename. `decode_state` is `decoded | fallback | absent |
unparsable`; `fallback_reason` is `null` unless `decode_state = fallback`, when it is a member of
`{encoded_word_in_parameter, empty_charset, missing_continuation_index, duplicate_continuation_index}`
(decision 5: the wild forms producers emit are **decode-with-recorded-fallback**, not "unparsable").
`attach.filename_unparsable` (a gap in `part.gaps`) is for what genuinely cannot be decoded;
`attach.filename_absent` for a missing filename.

```json
[["1.2", "=?utf-8?B?csOpc3Vtw6kucGRm?=", "decoded", "résumé.pdf", null],
 ["1.3", "report.pdf", "decoded", "report.pdf", null]]
```

### `attach.decorative` — the `decorative_hint`

Shape: `[[part, rule_id | null], ...]`, one row per attachment occurrence. `rule_id` is a member of the
recorded hint rules (`inline_unreferenced_small_image`, `inline_unreferenced_tracking_pixel`) or `null`
(absent). A decorative hint **never removes an occurrence** (D4): the fact records the hint, not a
filter.

```json
[["1.2", "inline_unreferenced_tracking_pixel"], ["1.3", null]]
```

### `attach.cid_use` — the cid and whether the body references it

Shape: `[[part, cid, referenced], ...]`, one row per attachment occurrence that carries a Content-ID.
`referenced` is the closed triple `referenced | unreferenced | n/a`: `referenced` when the cid appears in
`body.cid_refs`, `unreferenced` when it does not (`attach.cid_unreferenced`, which applies only to an
`inline` occurrence, D4), and `n/a` when there is no cid (in which case `cid` is `null`).

```json
[["1.2", "<logo@example.test>", "referenced"], ["1.3", "<spare@example.test>", "unreferenced"],
 ["1.4", null, "n/a"]]
```

### `gaps.later` — the gaps a later phase records (existing; shape unchanged)

Shape: `[[gap_id, locator, phase, reason], ...]`, kept as typed. Every gap id it names is a registry id
(`docs/design/phase0-gaps.md`); the four committed sidecars that carry it are unchanged.

## The Phase 0 facts: unchanged, and what stays

The Phase 0 fact list in `emailextract/evals/l1.py` is **not edited in Phase 1** for these ids, and their
shapes stay exactly as the committed sidecars type them:

| fact id | phase | shape (unchanged) |
|---|---|---|
| `container.sha256` | 0 | `"<hex>"` |
| `container.size_bytes` | 0 | `int` |
| `headers.fields` | 0 | `[[ordinal, name, raw_value, parse_status, [name_span], [value_span], [raw_span]], ...]` |
| `part.tree` | 0 | `[[part, parent | null, content_type | null, [raw_span], [headers_span], [body_span]], ...]` |
| `part.regions` | 0 | `[[region_kind, part, [span]], ...]` |
| `part.gaps` | 0 | `[[part, [gap_id, ...]], ...]` -- the **gaps fact in the existing row shape** |
| `body.preamble_epilogue` | 0 | `[[part, preamble_bytes, epilogue_bytes], ...]` (sparse-row compare) |
| `decode.chain` | 0 | `[[part, declared_cte, declared_charset, used_cte, used_charset, fallback_fired, encoding_source], ...]` |
| `body.content_sha256` | 0 | `[[part, "<hex>"], ...]` |
| `labels.undetermined` | 0 | `[[fact_id, locator, what_is_undecided], ...]` (the labels' own review) |

**The gaps a Phase 1 fixture records** are the Phase 0 conventions reused: `part.gaps` (a gap that rides
on the record it is about) and `gaps.later` (a gap named for a later phase). A Phase 1 fixture's new gap
ids -- the seven of Turn 1.0a -- ride in `part.gaps`; the two that fire from the headers family
(`headers.leading_bom`, `headers.mbox_from_line`) and `body.lone_cr_line_terminator` ride on the part
that owns the header region, exactly as `headers.malformed_line` does today. No new gaps fact type is
introduced.

## Findings: where a decision meets a typed Phase 0 label

Decision 12: the sidecar is **never edited**, so a decision that contradicts a typed label is a
**finding**, reported here with both values and the bytes.

1. **`attach.manifest`'s `declared_mime` column versus decision 6 (the three verdicts become `TriValue`).**
   The three committed labels type column 3 as a **bare MIME string** (`"application/pdf"`,
   `"image/png"`, `"application/vnd.openxmlformats-...sheet"`); decision 6 makes `declared_mime` a
   `TriValue`. **Resolution (a projection rule, so the labels stay as typed):** the `attach.manifest`
   measurer returns the verdict's projected **value** -- the `TriValue.value` when the state is `VALUE`,
   else `null` -- so column 3 stays a plain string and the three labels are unchanged. The full triples
   live in the new `attach.types` fact. This is a finding *recorded in advance*, not a live mismatch: no
   committed sidecar's bytes change, and the projected value of each committed label is the same string.
2. **`body.selection` versus decision 3/D16.** The retained values
   (`selected`/`alternative_not_selected`) are the `Selection` enum's members and the display rule is
   unchanged. No contradiction.
3. **`headers.decoded` versus decisions 4/5.** The retained row `[[5, "Hello ★ folded subject"]]` is the
   package's own encoded-word decode of the same bytes; decision 5 adds *validation* (and a possible
   `headers.encoded_word_invalid` gap) but does not change a valid word's decode. No contradiction.
4. **`gaps.later` versus decision 19.** The four committed rows name `attach.cid_unreferenced`,
   `headers.received_chain_unverified`, `thread.parent_not_in_corpus` and
   `time.in_text_dates_not_extracted_v1` at phase 3/1 -- all registry ids, all still correct.
5. **`body.plain_effectively_empty` leaving the gap registry (decision 6/D16) contradicts no typed
   label.** No committed sidecar names the id, in `part.gaps`, `gaps.later` or `labels.undetermined`
   (checked: the string does not appear in any `fixtures/**/*.expected.json`). The registry entry is
   converted to a **fact entry**, not edited away silently.

No other decision meets a typed Phase 0 label. `attach.manifest`, `body.selection` and `headers.decoded`
stay declared with their current shapes; `gaps.later` likewise; no Phase 0 fact's phase moves.

## Open questions

- **The exact row shapes of `headers.addresses` and `attach.types` are specified here but are the
  shapes Turn 1.2 and Turn 1.8 will implement.** They are typed in **byte** spans
  (`headers.addresses`) or `TriValue` triples (`attach.types`), and the fixtures that first type them
  are in `docs/design/phase1-fixtures.md`. If the 1.2/1.8 implementation finds a shape that carries the
  same information more directly, the remedy is a deliberate relabel of the not-yet-typed fixture (there
  are none in 1.0a) plus a note in `l1.py`'s `FACTS` -- not a silent drift.
- **`headers.parameters`'s `fallback_reason` vocabulary** (`encoded_word_in_parameter`, `empty_charset`,
  `missing_continuation_index`, `duplicate_continuation_index`) is the closed set decision 5 names; if a
  real producer form in the fixture set needs a fifth, it is added here **before** any sidecar uses it.
