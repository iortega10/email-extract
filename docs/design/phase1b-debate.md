# Phase 1b build spec: the debate with the hearth-cli model (outcome of eight rounds)

Status: **the outcome of a read-only design debate over `docs/design/phase1b-build-spec.md` (draft
revision 1).** Nothing here edits the spec or the design; it is the input to **revision 2** of the
spec. The design (`docs/design/email-extraction-design.md`) wins on any conflict. Shape follows
`phase1-debate.md`.

Method. Claude (this file's author) and the hearth-cli model, which for this run resolved to
`deepseek-v4-pro` (`hearth doctor`: `model=deepseek-v4-pro [env]`, `context_window_tokens=400000 [env]`).
Eight live rounds through `hearth --json`, session `s50daf7e3` in `email-extract/.hearth/sessions/`.
Hearth was read-only: **no `gate_paused` and no `error` event fired; no invocation stalled** (so no
retry-in-pieces was needed); `git status` after the debate shows only the untracked draft spec. No real
or employer mail was opened, `Downloads` was not touched, and no prompt contained mail content.

Evidence labels. **(C)** = Claude ran or read it itself (a `file:line`, or a scratch experiment on
hand-built bytes in a directory outside the repo). **(H)** = rests on hearth's reading of the file and
was not independently re-read by Claude. Hearth's file:line citations were spot-checked where they
carried a verdict; the rest stay marked (H).

## 0. Headline findings

1. **Architecture A as written (the virtual RFC 822 projection) fails three of its own constraints
   before any code exists.** (i) `ids.part_id` hashes `span.offset` and `span.length` (`ids.py:137-139`
   (C)), so every `PartRecord.part_id`, `parent_part_id` and `AttachmentOccurrence.part_id` is a function of
   the framing length; the root part's span is the whole virtual string, so the root id moves when any
   header grows. Scratch run (C): two otherwise identical messages differing only in an `X-Pad` header length
   got different root part ids. C2 ("no virtual offset in a citable record") is violated through the hash,
   and the C2 mutation test as worded ("every stored span stays stable") would not even notice it.
   (ii) `text.analyse_part` over a projected UTF-8 leaf returns `verbatim_precision=exact`,
   `verbatim_reason=None`, with an `offset_map` against the **virtual** bytes (scratch run (C); `text.py:112-120`
   (C): `VERBATIM_REASONS` has three members and `container_stream` is not one). `resolve_span`
   (`assemble.py:641-648` (C)) then returns `RawSpan(body_span.offset + ...)`, a virtual offset presented as
   verbatim. "The existing stages run unchanged" is false. (iii) `header_fields_at` decodes values latin-1
   (`walk.py:483-485` (C)); raw 8-bit UTF-8 in a value becomes mojibake in `raw_value` and in
   `HeaderRegion.text_decodes` (`decoded=False`) (scratch run (C)). Only the address path decodes the display name.
   A UTF-16 `0x007D` re-encoded as UTF-8 therefore loses its non-ASCII header text unless there is a codec seam.
2. **The agreed replacement is A'' = "A with a serialized provenance layer and a pass-through for binary
   leaves"**, not B and not C (a `MsgContainer` that builds `PartShape` itself). C was hearth's first pick; it
   was dropped when Claude showed that `attach.py:625,635`, `selection.py:290,527` and `text.py:337` read
   `part.header_fields` (and `text.py:340` slices bytes at `value_span`), so C still needs per-part
   synthetic header bytes **and** a duplicated 200-line `_walk_visit` that the `.eml` golden does not protect
   (H, `walk.py:656-817`). A'' keeps one walker.
3. **The spec's "default: no schema bump" cannot hold.** Nothing in `EmailDocument` can carry
   `{stream, byte_off, byte_len}`; the CFB cap reasons are not in `REASON_TABLE`; the embedded-message summary has
   no field. One bump, decided in 1b.0a, containing exactly three things (section 3, A9). Consequently
   **rule 2 and the exit criterion as worded are unsatisfiable** (the ledger `contracts` line and the store
   `walk_key` move with `OUTPUT_SCHEMA_VERSION`); replacement wording is in A15, A16.
4. **`cfb.py` own reader is forced, not merely recommended** (C3 sector accounting and the work-per-byte budget need
   chain ownership). A scratch run (C) of olefile 0.47 on hand-built hostile CFB: hostile-safe in 5 of 5
   (no raise, no hang), but a **cyclic FAT chain returned a full-size stream with an empty `parsing_issues`**, and
   a 2**40 size claim was silently clamped to 0 bytes. See section 4.
5. **Several vocabulary claims in the spec are wrong against the code**: the class gate has no `skipped(...)`
   reason to use; `UNSUPPORTED` takes no reason (`model.py:252` (C)); `NAMED_ERROR_REASONS` is closed
   (`parse.py:67-74` (C)) with only `cfb_msg_unsupported` for CFB; hostile-CFB outcomes (cycle, directory loop,
   out-of-range sector) have no id anywhere; `phase0-gaps.md:615-621` contradicts D13 on extended DIFAT.
6. **Pre-existing tests the spec forgot will necessarily be edited** (section 3, A16); "unedited except the
   scope test" is unrealistic.

## 1. Round log (who changed their mind, and why)

| round | topic | outcome |
|---|---|---|
| 1 | A: part_id, false exact, Region/0x007D | hearth confirmed all three with citations (`ids.py:137-139`, `text.py:116-120`, `walk.py:322-335`). Hearth's two nits (design defect, not shipped bug; the C2 test needs a new id-stability assertion) accepted. It offered the hybrid "A for headers/bodies, direct MAPI path for attachments". |
| 2 | Seam census; headers; embedded message | Hearth counted `raw` consumers: only three real byte-needs (header bytes, body payload bytes, full container for `resolve_span`); everything else works on decoded text. It picked **C**. It confirmed (and Claude re-verified by run) that non-ASCII header values do not survive the UTF-8 re-encode. It showed `AttachmentOccurrence` requires only `attachment_id`, `occurrence_path`, `part_id` (`model.py:787-790` (H)) and that class/subject/counts of an embedded message have no home (`EmbeddedSummary` -> bump). |
| 3 | C costed honestly | **Hearth changed its mind: C -> A''.** Reason (Claude's evidence): header_fields of every part are read by attach/selection/text, so C must synthesize header blocks anyway and also reimplement the walker. Hearth added the store leak: persisting virtual `Region` offsets violates C2 even with `MSG_PROJECTION_VERSION` in the key. |
| 4 | Further leaks; pass-through; DIFAT; memory | Hearth found chokepoints 5-8 (encoding_source, stream sha/size, cap `declared_size_bytes`, store). It proposed pass-through of binary/8-bit leaves. It found D13 says "named gap, not a crash" for extended DIFAT (`email-extraction-design.md:784` (C)) and that `phase0-gaps.md:615-621` says the opposite. |
| 5 | olefile; model fit; RTF | Claude ran olefile on hostile bytes (C); hearth conceded own `cfb.py` is forced. Hearth: class gate = `UNSUPPORTED` without reason; time facts as flat hex keys; **RTF de-encapsulation: cut** (10 of 11 real files have HTML, none RTF-only). Claude challenged two claims; hearth **withdrew both** (signed mail has a readable body -> now a probe item; `msg.fat_cycle` is not a registered id). |
| 6 | Vocabularies; golden; turns; fixtures | Hearth: golden in its own turn before any frozen edit; split 1b.4; added fixtures; gate-vacuity risks. First mapping sent FAT/directory cycles to a NamedError. |
| 7 | Cycle granularity; provenance home; broken tests | **Hearth conceded Claude's pushback**: a FAT cycle is one stream's fault (document + `TRUNCATED`), not a whole-file refusal; only directory-level and header-level faults are NamedErrors. It found the bump contents, the rule-2 problem and the list of tests to edit. |
| 8 | Re-test given the bump; 1b.0b; ranking | Hearth proposed to relabel A'' as "B-lite" (same architecture, provenance in a model field). Claude treats this as the same decision with a better output shape (count stays 8; two chokepoints re-target to model fields). Hearth supplied the 8-experiment list and an 18-item ranking; Claude corrected four of its items (section 5). |

Where hearth changed its mind: C -> A'' (round 3); NamedError for all cycles -> per-stream document (round 7);
MultipartSigned readable body and `msg.fat_cycle` (round 5, withdrawn); "bump is enum vocabulary" -> "bump is
ContainerStreamRef + cap reasons + EmbeddedSummary" (round 7). Where Claude changed its mind: the hybrid
"direct MAPI attachment path" (round 1) was dropped once the header_fields coupling showed it does not avoid
synthesizing per-part MIME headers; the extended-DIFAT stance moved from "follow D13 literally" to "read through
and flag it" after the 7 MB v3 ceiling was worked out (section 3, A7).

## 2. The architecture decision (what the spec should say)

**Decision: A'' in place of A.** Keep a deterministic virtual RFC 822 byte string so `walk.py`,
`header_fields_at`, `headers.py`, `attach.py`, `selection.py` and the quote stages run on one walker. Add:

1. **A span table** (optional attribute on the container, found with `getattr(container, "span_provenance", None)`,
   not a `Container` Protocol member, so `EmlContainer` and `FakeContainer` stay valid), one row per virtual
   region: `kind in {stream, reencoded, synthetic}`, source stream name, **source** `byte_off`/`byte_len` in the
   stream's own encoding (UTF-16 for 001F), and for `reencoded` the decoded character range.
   A consumer can never observe a virtual offset in a *record*; the table is internal to the producer.
2. **Pass-through for binary and 8-bit leaves.** 10 of 11 real files are HTML-only in `0x1013`, a binary
   stream (`email-spike.md`, spec lines 75-76). Such a leaf is projected **unchanged** with CTE `binary` and
   `charset=<chosen code page>`: its `size_bytes` and `sha256` are the stream's own, its span is a true stream
   subrange, and no base64 4/3 inflation is paid for attachments. Only 001F text (the `0x007D` headers, plain
   `0x1000`, subject) is re-encoded. `_decode_cte` treats `7bit`/`8bit`/`binary` as identity
   (`walk.py:920-923` (H)).
3. **Uniform `part_level` / `container_stream` for every `.msg` leaf**, including pass-through ones. The
   walker's `exact` decision is coordinate-space dependent, not byte-identity dependent: `resolve_span` adds
   `body_span.offset`, a virtual offset, even when the leaf bytes equal the stream bytes. Exactness is carried
   only as a flag in the span table.
4. **Eight provenance points, all outside `_walk_visit`'s structural logic** (Hearth's final count: 7 post-walk
   plus 1 entry; none vanish, two re-target to model fields once the bump exists). Ranked by risk to the
   `.eml` golden (all in frozen modules, so each default path must be the current expression verbatim):
   1. assembler fills `ContainerStreamRef` on `PartRecord` and `HeaderField` (`assemble.py`); 2. kind-gated
   `part_id` over `{stream, byte_off, byte_len}` + content hash of the real source bytes + `container_hash`
   (`walk.py:730,799`, `ids.py`; synthetic parts get `synthetic:<role>:<ordinal>`); 3. `resolve_span` returns a
   stream span or `Unresolvable` (`assemble.py:641-648`); 4. `text.analyse_part` precision precomputed
   `part_level`/`container_stream` for `cfb_msg` and new member in `VERBATIM_REASONS` (`text.py:116-120`);
   5. `encoding_source` overwritten from the MAPI ladder (`walk.py` `_charset_ladder`, ~1027-1069; the walker can only
   say `declared_charset`); 6. cap records: `declared_size_bytes` copies a virtual body length
   (`assemble.py:247-264`, `attach.py:782-790` (H)); 7. store persists CFB sectors plus the span table, not virtual
   `Region`s (`store.py:166`); 8. entry: `parse.py:290,313` opens the container instead of refusing.
5. **Header text.** Header text for `0x007D` is decoded UTF-16 and re-encoded UTF-8; add a `value_codec`
   seam (default `latin-1`, so `.eml` is unchanged) to `header_fields_at` and `header_region`. Rejected
   alternative: writing non-ASCII as RFC 2047 encoded-words, because it makes `raw_value` a lie about what the
   stream says (and `text.py:340`, `attach.py:627/637`, `selection.py:292/529` read `raw_value`).
   Edge cases checked (H, `walk.py:432-447`, `:532`): bare LF is harmless; a trailing NUL must be stripped
   before the scanner; a header truncated mid-line is flushed at EOF without raising; an odd-length UTF-16
   stream must never reach the scanner.
6. **Regions and no-silent-drop.** For `.msg`, `WalkResult.regions` describes the reader's own framing and is
   not persisted. Accounting is by CFB sectors (C3); the sum equals the file length. Readers of regions:
   `assemble.py:248`, `attach.py:785` (length only), `evals/l1.py`, `evals/gates.py` (both build
   `EmlContainer`, so they never see a `.msg`) (H).
7. **Caps.** `max_decoded_*` are measured on decoded bytes, so the cap *hit* is consistent between `.eml` and
   `.msg`; `max_input_bytes` is on the file (`parse.py` limits at :158-166 (C)), so a 50 MB `.msg` passes the
   64 MiB gate where its ~67 MB base64 `.eml` twin is refused. Record this asymmetry in the report; it is
   honest, not a defect. Memory peak: with a `bytes`-valued `raw_bytes()` the virtual string materialises once
   (file + virtual string + bounded decode); a lazy view would be a `container.py` protocol change and is out of scope
   unless experiment E4 shows it is needed.

### Unresolved: the label "A'' vs B-lite"
Hearth called the final shape "B-lite" and retired the name A''. Claude considers them one architecture (virtual
bytes + serialized provenance); the only difference is that provenance is now a model field instead of a side
channel. Not material; the spec should pick one name. This doc uses A''.

## 3. Agreed amendments (ranked by severity; replacement text)

Severity: **BLOCKER** = the spec cannot be built as written; **MAJOR** = wrong or unfalsifiable but fixable
in-turn; **minor**. Disposition: **(a)** apply to the spec, **(b)** owner question, **(c)** needs the
structure-only probe. Line anchors are `phase1b-build-spec.md`.

### (a) Amendments to apply to the spec

**A1 BLOCKER. Identity must not depend on virtual offsets.** Amends `:97-107, :114-122`. Replace constraint C2:
> C2. No virtual offset is an input to any identity or stored in any record. For `cfb_msg`, `part_id` is minted
> by a kind-gated function over `(container_hash, stream-keyed span {stream, byte_off, byte_len} or
> synthetic:<role>:<ordinal>, sha256 of the real source bytes)`. A test builds the same message with two framing
> lengths and requires identical `part_id`s, `PartRecord`s and citations; a second test mutates the `.eml` path
> and requires the `.eml` `part_id`s byte-identical.

**A2 BLOCKER. Replace "the existing stages run unchanged".** Amends `:106-109`. Replace with:
> The walker, header stage, attach, selection and quote stages run on the virtual bytes with no change to
> `_walk_visit`'s structure; eight enumerated provenance points (section 2) are the only edits to frozen modules,
> each gated on `cfb_msg`/the presence of a span table, each with its default branch the current expression
> verbatim.

**A3 BLOCKER. `.msg` verbatim precision.** Amends `:60-62`. `text.py:VERBATIM_REASONS` gains `container_stream`
(a closed-vocabulary edit, covered by A9); every `.msg` leaf, pass-through included, is `part_level`; text.py must
not claim `exact` against virtual bytes (scratch evidence above).

**A4 BLOCKER. Header decode fidelity.** Amends `:55-62, :196-197`. Add:
> `0x007D` is read per its property type (001F UTF-16LE, 001E through the ladder), one trailing NUL stripped,
> then re-encoded UTF-8 for the scanner; the header stage takes a `value_codec` (default `latin-1`; `utf-8` for
> `cfb_msg`) so `raw_value` and `text_decodes` carry the real text. Header citations are `part_level` /
> `container_stream` pointing at the UTF-16 byte range.
(Hearth's text added "UTF-16 with BOM"; no BOM is evidenced in `email-spike.md`, so Claude removed it. A test
fixture with a BOM is in A14.)

**A5 MAJOR. Rule 2 (the `.eml` golden) wording.** Amends `:30-33, :267`. Replace:
> No measured `.eml` value moves: the behavior ledger's `walk` and `decode_chain` fingerprints over the committed
> `.eml` fixtures, the `.eml` golden pins and the sidecar L1 facts are byte-identical before and after 1b. The only
> permitted moves are the version-stamp consequences of the one schema bump: the ledger `contracts` line and any
> store `walk_key` that includes `OUTPUT_SCHEMA_VERSION`, recorded in the same commit. Any other move is a defect.

The golden is **partial, not redundant** against the ledger: the `walk` fingerprint pins the `WalkResult`
(incl. `part_id`; `tools/behavior_ledger.py:6-8` (H)) but not the assembled `EmailDocument`. It must pin: the
serialized `EmailDocument`, the `WalkResult`, `resolve_span` samples (the C2 guard), `CapRecord`s, the store
artifact bytes and `ParseResult`. It is a committed file that the test never regenerates silently, checked on
both interpreters with a recorded waiver rather than a silent skip.

**A6 MAJOR. Golden-first.** Amends `:241`. The golden is captured in its own turn (hearth: the end of 1b.0b or a
tiny 1b.0c), before the **first** frozen-module edit, not "before Turn 1b.4".

**A7 MAJOR. Extended DIFAT.** Amends `:53, :239`. A v3 file's 109 header DIFAT slots address at most
109*128*512 = ~7.1 MB (C, arithmetic); any mail with an attachment over ~7 MB needs the extended chain, and
the 11 spike files (<= 450 KB) never exercised it. Recommended replacement: read through the extended chain
(bounded), emit `msg.cfb_difat_extended` as a recorded observation, and fault only on a broken chain. This
**exceeds D13's letter** ("a named gap, not a crash", `email-extraction-design.md:784`); see the owner question
O1. `phase0-gaps.md:615-621` already describes read-through and must be reconciled with whichever the owner
chooses.

**A8 MAJOR. Closed vocabularies for hostile CFB.** Amends `:40-42, :53, :239, :250-258` and `parse.py`:
> Directory loop -> NamedError `cfb_directory_loop`. Unsupported header/version (sector shift outside
> {9,10,11,12} for v3, or v4 with shift != 12) -> NamedError `cfb_header_unsupported`. CFB magic without
> `__properties_version1.0` -> existing `not_a_message` (the `.doc`/`.xls`/`.ppt`/`.msi` case; `cfb_msg_unsupported`
> is deleted). Per-stream chain faults (cycle, out-of-range sector, chain shorter than declared size) yield a
> **document** with `Status.TRUNCATED` and the registered `msg.stream_truncated`, the fault recorded per stream.
> `cfb.read_stream` never raises: it returns `(bytes, fault)` with `fault in {OK, CYCLE, OUT_OF_RANGE, SHORT_CHAIN}`.
> Reason mapping: out-of-range and short chain -> `stream_ended_early`; cycle -> `declared_length_mismatch`.
> `msg_fat_cycle` and `msg_directory_loop` are hostile fixtures, not gap ids.
The entry point sniffs (`ingest.py:238`: `parse.parse(raw, limits=limits)` with no kind (H)); a renamed `.doc` thus
changes from `skipped(cfb_msg_unsupported)` to `not_a_message`.

**A9 BLOCKER. One schema bump, decided in 1b.0a, containing exactly these.** Amends `:179-182`.
> `OUTPUT_SCHEMA_VERSION` moves once. It contains: (X) `ContainerStreamRef {stream, byte_offset, byte_len,
> axis in {stream, reencoded, synthetic}, fault}` as an optional field on `PartRecord` and `HeaderField`;
> (Y) the CFB cap reasons added to `REASON_TABLE` (`sector_count_cap`, `directory_entries_cap`,
> `difat_chain_length_cap`; stream size folds into `size_cap`/`cap_hit_mid_stream`);
> (Z) an `EmbeddedSummary` (class, subject, has_transport_headers, recipient and attachment counts) on
> `AttachmentOccurrence`. `EncodingSource` (`model.py:134-142`) and `ContainerKind` already carry every needed
> member and do not move; per-part stream size and digest reuse `PartRecord.size_bytes`/`sha256`.
Claude's reservation: Y could be avoided by mapping CFB caps onto existing walker cap reasons (`size_cap`,
`part_count_cap`, `depth_cap`) at the cost of semantic stretch; hearth preferred the new reasons. Not resolved
(owner question O3).

**A10 MAJOR. Class gate vocabulary.** Amends `:169-171, :207`. Non-`IPM.Note*` -> `Status.UNSUPPORTED`
(takes no reason; `skipped` would need a new reason, i.e. a table change), the class verbatim in
`container_facts.message_class`, the registered `msg.class_not_ipm_note` kept (see section 5, D2, for hearth's
dissenting item). Nothing past the class is opened.

**A11 MAJOR. Gate and exit vacuity.** Amends `:280-282`. L1 per-family floors are declared from the fixture
counts **before** the turn, not derived from the achieved value; "every `msg.*` gap id has a mutation case" runs over
the **closed registry**, each hostile case produced by a **named committed seed**; the gap-drop gate is falsified
against that list; no-silent-drop is asserted on **sectors**, never on virtual bytes (the latter tests the
projection's own bookkeeping); "no real `.msg` in the repository" gets a listing check that `fixtures/real/` is
empty (otherwise it is policy only).

**A12 MAJOR. Turn split.** Amends `:241`. 1b.4a: `MsgContainer`, the projection and the span table, no walker
edits; 1b.4b: the eight provenance points, re-check of the golden; 1b.4c: MAPI content (headers, bodies,
recipients, attachments). Build 1b.4b **before** `cfb.py` against a `FakeMsgContainer` (hand-made virtual bytes
and a hand-written span table), as Phase 0 did with `FakeContainer` (`container.py`), so the riskiest edits
do not wait on the CFB spike.

**A13 minor. Time facts.** Amends `:142-147`. `container_facts` keys of the form `time.<tag-hex>.filetime_hex`
and `time.<tag-hex>.utc`, raw u64 as **hex** (lossless), keyed on the hex tag, not a display name. The Date header
and the MAPI properties stay distinct (Phase 3 policies). Hearth noted `Precision` tops out at `SECOND` and a
FILETIME carries no UTC offset (`timeevent.py:54-78` (H)); this is for Phase 3, not 1b.

**A14 minor. Fixture catalogue additions** (`:248-259`). *Committed fixtures:* multi-valued string properties
(keep every value); `0x007D` with a UTF-8 BOM, and with LF-only line endings; a `0x001E` string8 body; a
zero-length body stream (present-but-empty != absent); recipients: display-name only, EX address type with no
SMTP, Bcc, duplicates; attachments of 4095/4096/4097 bytes (mini-cutoff) and zero size; duplicated filenames; HTML
whose `<meta charset>` contradicts the internet code page; non-BMP characters (UTF-16 surrogate pairs).
*Test-only hostile seeds:* a lone UTF-16 surrogate and an odd-length UTF-16 stream (strict `utf-16-le` raises, so
the bounded decoder must record, not raise); recipient-count property vs real rows mismatch; an attachment
storage with no data stream.

**A15 minor. No-header gap suppression.** Amends `:138-141`. Absent `0x007D` -> `headers=[]`; the header
field/date/address walkers do not run over an empty synthesized block (an empty `headers` list passes model
validation, `model.py:987` (H)); the only gap is `msg.transport_headers_absent`, once at document level, so
`headers.no_date`/`headers.no_from` are not emitted as noise.

**A16 MAJOR. Replace the "unedited" exit wording and list the tests that will be edited.** Amends `:283-285`:
> Every pre-existing test either passes unedited or is changed only in the named, owner-agreed categories:
> (1) Phase 1 scope pins that this release deliberately relaxes; (2) the one `OUTPUT_SCHEMA_VERSION` bump and its
> direct consequences (record shapes, `REASON_TABLE`, the gap registry, `NAMED_ERROR_REASONS`), re-recorded in the
> same commit; (3) the ledger `contracts` line and the store `walk_key`. A failing test in any other category
> (a changed `.eml` value, a `walk`/`decode_chain` fingerprint move, a sidecar fact move) is a defect.

Tests that must change (verified by name in Claude's own grep where marked (C)):
`tests/test_licence_audit.py:165-169` `test_olefile_is_not_a_declared_dependency` (C: spec puts olefile in `[dev]`;
`pyproject.toml:56` has `dev = ["pytest>=8"]`); `tests/test_phase1_scope.py:196` module-set,
`:219` banned imports (`cfb`, `olefile`), `:245` forbidden names (`cfb`, `msg_reader`, `read_msg`), `:271` runtime
dependency; `tests/test_container.py` fake-container tests; `tests/test_parse_entry.py` NamedError tuple;
`tests/test_status_reasons.py`, `tests/test_contracts.py`, `tests/test_contract_phase1.py`,
`tests/test_closed_enums.py`; `tests/test_behavior_ledger.py` (contracts line); `tests/test_turn_declarations.py`;
`tests/test_phase0_gaps.py` / `tests/test_phase1_gap_gate.py` / `tests/test_gap_falsifiability.py`. The
"olefile not in sys.modules" assertion in `test_container.py` must survive; it is the real guard keeping olefile
out of the library import path. (Most rows are (H) from hearth's reading.)

**A17 MAJOR. Rewrite Turn 1b.0b** as a closed list of at most eight hand-built-byte experiments (section 6),
each with input, pass/fail criterion and the decision it settles, not an open "prototype A".

**A18 minor. Optional provenance via `getattr`.** Amends `:103-107`. The span table is discovered by
`getattr(container, "span_provenance", None)`; it is not a member of the `@runtime_checkable` `Container`
Protocol (`container.py` ~83), because `EmlContainer` would otherwise have to publish an empty map. No
production `isinstance(x, Container)` was found (H).

### (b) Owner questions (cannot be settled by experiment)

- **O1. Extended DIFAT: read through (recommended) or named gap and stop (D13's letter)?** Practical effect:
  v3 `.msg` with an attachment over ~7 MB. Also fix whichever of `phase0-gaps.md:615-621` and D13 line 784 loses.
- **O2. RTF `\fromhtml1` de-encapsulation (1b.7): cut (recommended) or keep?** Evidence for cut: 10 of 11 real
  files have `0x1013` HTML, none is RTF-only. The honest minimum if cut: decompress (LZFu/MELA, CRC and header size
  checked), record `container_facts.body_streams=rtf`, emit the registered `msg.rtf_to_text_unsupported`, no body
  view. Cutting frees one of the four new gap-id slots (`msg.rtf_encapsulation_refused`) and avoids any new
  `BodyView` member (`BodyView` is `HTML`/`PLAIN` only, `model.py:155-159` (C); a derived view labelled
  `html` in `ContentFingerprint.body_digest_view` would be the mislabelled digest D14 forbids). Claude's own
  doubt, not settled: a decompress step with no consumer is dead code with a test; the owner may prefer
  "record the stream's presence and header fields only", but D13 names a "decompress-only reader".
- **O3. Cap reasons: new `REASON_TABLE` members (hearth) or reuse the existing five walker cap reasons (Claude's
  alternative)?**
- **O4. olefile as a `[dev]` extra** (supply chain; it is BSD-3-Clause and already named in `NOTICE` and
  `test_licence_audit.py:44-51`), versus a hand-built-only oracle (the spec's own breaker (a)).
- **O5. Golden-first ordering and the number of turns** (process; 1b.4 split makes 11 turns).
- **O6. Whether a `.msg` with no transport headers should ever get synthesized headers** (default no, unchanged).
- **O7. D1 vs D13 wording.** D1 (`email-extraction-design.md:275-278`) says "own reader over `olefile`"; D13
  (`:777-785`) mandates an own `cfb.py` with a promotion path to `docextract-core`. The design contradicts
  itself; the debate resolves it toward D13 (own reader, olefile as oracle). The owner should confirm and fix D1.
- **O8. Signed-only vs encrypted split** (decision 8). See (c).

### (c) Items needing the structure-only probe (owner runs; aggregates only)

- **P1. Signed mail layout.** Hearth first asserted that `IPM.Note.SMIME.MultipartSigned` carries a readable
  `0x1013`/`0x1009` body; Claude believes (from memory, not the repo) that Outlook stores signed mail as a body-less
  item with an opaque `smime.p7m`/`data.dat` attachment. **Neither is evidenced**: `open-inputs.md:97` says
  signed/encrypted are deferred, none available. Default: decision 8 verbatim (class recorded, no body, never
  verified). Hearth's split (encrypted-only-when-opaque -> `Status.ENCRYPTED`, signed-only readable -> `PARSED`)
  is **proposed, not agreed**; do not adopt until a probe shows the layout.
- **P2. Time property tags** (`0x0039`, `0x0E06`, `0x3007`, `0x3008`): verify presence and types.
- **P3. CFB layout aggregate:** version, sector size, miniFAT use, DIFAT length (is the extended chain
  ever present in the owner's corpus? this settles how much O1 matters), directory size, stream-size histogram.
- **P4. Attachment and recipient tag sets** before 1b.6 (method, `0x3707`/`0x3704`/`0x3001`, `0x3712`, `0x370E`,
  flags); recipient address types (SMTP vs EX).
- **P5. 8-bit prevalence:** is `0x007D` ever `001E`? are bodies `0x1000` 001E ever present? (all 11 files are
  001F).
- **P6. Vendor HTML classes** (Outlook `divRplyFwdMsg`, `x_` prefix), spec risk 8.

## 4. cfb.py versus olefile (spec further-decision 1)

**Decision: own `cfb.py`; olefile as a tests-only comparator** (spec default ratified, but now forced).
Reasons: (1) C3 needs a per-sector classification (header/DIFAT/FAT/miniFAT/directory/stream/free/slack summing
to file length), which olefile does not expose (H); (2) rule 4's operation-count budget needs a chain walk the
package owns (olefile's `openstream()` is a black box, no per-step hook) (H); (3) olefile's leniency is silent in
at least one case.

Scratch evidence (C; olefile 0.47 installed with `pip --target` in a scratch directory, hand-built v3 CFB bytes,
never a real file):

| mutant | olefile result | `parsing_issues` |
|---|---|---|
| cyclic FAT chain (data sectors 2->3->2) | returned a 5000-byte stream, no raise, no hang | **empty list** |
| claimed size 2**40 | stream clamped to **0** bytes | "stream too large", "incomplete OLE stream", "sector index out of range", "size is less than declared" |
| claimed size 0xFFFFFFFF | 5120 bytes (sector padded) | same four |
| start sector out of range | 0 bytes | "sector index out of range", "size less than declared" |
| directory self-reference | enumerated normally | "double reference", "Entry referenced more than once" |
| file truncated to 1200 bytes | empty listing | "DirEntry index out of range" |
| root child pointing to itself; storage child pointing at root | empty listing, no raise | (not checked) |

So olefile is hostile-safe in the cases tried (no exception, no hang), but it **cannot be the oracle for hostile
mutants**: its silent cycle read would "agree" with an incorrect reader. The oracle compares only the non-hostile
facets on the well-formed fixtures (stream/storage names, sizes, bytes, directory shape); hostile mutants are
excluded from byte comparison and are independently broken by (a) the falsifiable stream-fault classification,
(b) the sector-tiling sum, and (c) the seeded fuzz's bounded-work/no-exception property. A caveat on the experiment:
the cyclic-chain test used uniform `A` data, so "returned wrong bytes" was not demonstrated, only "no issue
recorded".

Size estimate of `cfb.py` (hearth, H): about ten functions and three frozen dataclasses (`parse_header`,
`walk_difat`, `read_fat`, `read_minifat`, `walk_directory`, `lookup_entry`, `chain_sectors`, `read_stream`,
`classify_sectors`, `check_caps`), 350-450 lines.

## 5. Disagreements and corrections, material and not

### D1. (Resolved by Claude's correction) Hearth's items that Claude does not accept as written
- **Hearth's item 11** says an RTF-only body yields `msg.rtf_encapsulation_refused`. That id belongs to the
  de-encapsulator, which the same item cuts. If 1b.7 is cut, an RTF-only body yields the registered
  `msg.rtf_to_text_unsupported` and no `rtf_encapsulation_refused` id exists.
- **Hearth's item 2** says "`0x007D` is UTF-16 with BOM". The BOM is not evidenced anywhere in the repo; Claude
  removed it (A4).
- **Hearth's item 7** re-scopes `cfb_difat_extended` to "extended DIFAT chain faulted, never present". Claude
  keeps this as owner question O1: the registry text (`phase0-gaps.md:615-621`) already says "records the extended
  form and reads through it", so the id means an *observation*, and both readings of D13 are defensible.

### D2. (Open, small) The class gate and `msg.class_not_ipm_note`
Hearth's final ranking says the gap id "leaves the registry (it is a status, not a gap)". Claude keeps it:
the id is registered in the design (`email-extraction-design.md:814, :979`) and `phase0-gaps.md:623-629`, the
design wins, and the gap and the status carry different information (gap = what was not read and why; status =
what the document is). Hearth in round 5 agreed with Claude's reading (UNSUPPORTED plus gap plus class fact);
the round-8 wording is its own drift. Left to the owner only if they want the gap removed from the design.

### D3. (Open, small) A'' vs "B-lite" naming; see section 2.

### D4. (Unresolved, not material to correctness) Whether CFB caps need new `REASON_TABLE` members (O3).

## 6. Turn 1b.0b rewritten: eight experiments (hand-built bytes, outside the repo)

Hearth's list, edited by Claude (E1 and E3 as written by hearth were underspecified; Claude's versions below).
Outputs go into `docs/design/msg-architecture.md`.

| # | experiment | input | pass / fail | settles |
|---|---|---|---|---|
| E1 | olefile on the hostile set | the six mutants of section 4 plus a v4 file and a 4095/4096/4097 mini-cutoff trio | every outcome (raise/clamp/issue/silent) recorded; sectors reconstructable from `ole.fat`/`minifat`/`direntries` or not | own `cfb.py` confirmed; oracle scope |
| E2 | `cfb.read_stream` fault contract | FAT cycle, out-of-range sector, short chain, directory loop, bad header | no exception; `(bytes, fault)` returned; directory/header faults become NamedErrors; per-stream faults a document | A8 |
| E3 | sector accounting | the E1 fixtures | seven sector classes sum to file length; free/slack explicit; a cyclic chain visible as unaccounted | C3, rule 4 |
| E4 | large attachment memory | synthetic 40 MiB attachment stream, pass-through vs re-encoded | peak RSS delta under a declared budget; no more than one extra copy | whether a lazy `raw_bytes()` is needed; cap location |
| E5 | determinism of identity | `FakeMsgContainer`, two framing lengths | identical `PartRecord` ids, citations, `WalkResult` modulo provenance fields | C2 / A1 |
| E6 | 8-bit header seam | non-ASCII `0x007D` text from 001F and 001E | `raw_value` and `text_decodes` equal the hand-typed text; `.eml` default path byte-identical | A4, `value_codec` |
| E7 | precision precompute | `FakeMsgContainer` body, already decoded | `part_level`/`container_stream`; never `exact` | A3 |
| E8 | store artifact | one `FakeMsgContainer` document | re-ingest byte-identical; `.eml` artifact bytes untouched; no virtual offset persisted | store decision, rule 2 |

Not experiment-settled (owner): O1 to O8.

The A'' experiment (a)-(c) proposed in round 3 is covered by E5 + E6 + E7 plus one more assertion: `walk(msg)`
compared with `walk(EmlContainer(equivalent synthetic eml))` modulo provenance fields, with **no** edit outside the
eight provenance points; if that comparison forces an edit to tiling or ordering in `_walk_visit`, C becomes
competitive again and the decision is re-opened.

## 7. Facts established (so the spec can cite them)

- `part_id` inputs: `ids.py:125-140` (C). Root part span = whole raw (`walk.py:379`, H).
- `Status.UNSUPPORTED` takes no reason; `SKIPPED` takes only five cap reasons (`model.py:245-252`, C).
- `NAMED_ERROR_REASONS` closed tuple (`parse.py:67-74`, C); CFB magic sniff at `parse.py:290`, explicit
  `container_kind='cfb_msg'` refusal at `:313` (C).
- `EncodingSource` already includes `internet_cpid`, `message_cpid`, `ascii`, `utf8_strict`, `windows_1252`
  (`model.py:134-142`, C).
- Walker defaults: `Limits.untrusted()` `max_input_bytes=64 MiB`, `max_decoded_part_bytes=32 MiB`,
  `max_decoded_total_bytes=128 MiB`, `max_header_bytes=256 KiB` (`parse.py:158-166`, C).
- `walk(` library call sites: `assemble.py:420`, `assemble.py:618`, `store.py:166` (C).
- `tools/real_probe.py` exists (C), so spec line 28 is correct.
- `FakeContainer` exists (`container.py`, C) as the Phase 0 precedent for A12.

## 8. What this debate did not settle

- The exact `ContainerStreamRef` shape and whether it sits on `PartRecord`/`HeaderField` or in a side table
  keyed by `part_id`/`ordinal` (either is a new field; picked in 1b.0a).
- Whether `PartRecord.sha256` for a pass-through leaf equals the stream sha (hearth: yes; stands, since the leaf is
  unchanged) while for a re-encoded leaf it is the UTF-8 re-encoding's digest and the stream's own digest lives in
  `ContainerStreamRef` or the span table (D13 "raw bytes and digest are kept beside the decode"). Needs a
  decision in 1b.0a.
- No code was run by hearth. Claude ran only: the `part_id`/precision/header-mojibake experiments against the
  committed code via `FakeContainer`, and the olefile mutants. Everything else is reading.
