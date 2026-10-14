# Phase 1b build spec: the `.msg` reader (revision 2)

Status: **revision 2, owner decisions O1-O8 recorded 2026-10-11 (section "Owner decisions"); ready for Turn 1b.0a.**
Revision 1 (2026-10-11) was debated for eight rounds with the hearth-cli model (`deepseek-v4-pro`;
`docs/design/phase1b-debate.md` is the record of who changed their mind and why) and every agreed amendment
(A1-A18 there) is folded in below. Where the debate and this document differ, this document wins; where this
document and the design (`docs/design/email-extraction-design.md`) differ, the design wins and the difference is
an owner question. Builds on release `0.1.0` (`0516834`). The measured facts about real `.msg` files are
`docs/design/email-spike.md` (eleven real files, structure only) and `docs/design/open-inputs.md` sections 2, 3
and 8. The process, the operating rules and the independence machinery are Phase 1's
(`phase1-build-spec.md`); this document restates only what changes.

What revision 2 changes, in one paragraph: the "virtual RFC 822 projection" (A) as first written failed three of
its own constraints (part ids hashed virtual offsets, the text stage would claim `exact` spans against virtual
bytes, non-ASCII header text came out as mojibake). It is replaced by **A''**: the same virtual bytes, plus a
serialized provenance layer and a pass-through for binary leaves. That needs **one schema bump**, so the
"`.eml` output is frozen" rule is reworded (it is the measured values that are frozen, not the version
stamps), `cfb.py` is confirmed as the package's own reader with `olefile` demoted to a well-formed-input oracle,
the vocabularies for hostile CFB and the class gate are fixed against the real tables, RTF de-encapsulation
is cut by default, and the turn plan gains a golden-first turn and a split of the container turn.

## Goal

Read an Outlook `.msg` (an OLE/CFB compound file holding a MAPI message) into the **same `EmailDocument`** the
`.eml` parser produces, deterministically, with every byte accounted for and every unreadable construct a
named `msg.*` gap, never a raise and never a guess. The owner's real corpus is `.msg` (open-inputs item 2); `.eml`
was built first only because it can be hand-typed. Phase 1b is **before** routing (Phase 2) and threading
(Phase 3) so those phases see both containers.

Out of scope: routing and recursion (Phase 2: an embedded message is read and **recorded** here, not recursed
into as a child document), threading and `TimeEvent` emission (Phase 3), the matcher and flags, the query layer,
RTF-to-text and RTF de-encapsulation (cut, owner decision O2), resolving named properties, writing or
modifying a `.msg`, `.pst`/`.ost`, `.oft` templates, TNEF (`winmail.dat`), verifying or decrypting signed or
encrypted mail (recorded by class, never opened). No LLM, no network, no GPL anywhere.

## Operating rules (Phase 1's ten, plus these)

1. **Real `.msg` files never enter the repository, a fixture, a commit, a log or hearth's model.** The owner runs
   structure-only probes locally (`tools/real_probe.py` exists; Turn 1b.0a specifies the aggregate probes P1-P6)
   and pastes **aggregates** (counts, sizes, tag sets, never a value). A turn prompt never contains a path under
   the owner's Downloads folder. A listing check asserts `fixtures/real/` is empty (otherwise this is policy only).
2. **No measured `.eml` value moves.** The behavior ledger's `walk` and `decode_chain` fingerprints over the
   committed `.eml` fixtures, every measured value in an `.eml` `EmailDocument` (`container_hash`, every `part_id`,
   every `sha256`, every span, every `CapRecord` value, the `ParseResult`) and the sidecar L1 facts are
   byte-identical before and after Phase 1b. The only permitted moves are the **direct consequences of the one schema
   bump**, recorded in the same commit as the bump: the new `output_schema_version` value, the new optional fields
   serializing as `null` on `.eml` records (`"stream_ref": null` on every `PartRecord` and `HeaderField`, and the
   equivalent for any other new optional field), the grown closed vocabularies (`REASON_TABLE`,
   `NAMED_ERROR_REASONS`, `VERBATIM_REASONS`, the gap registry), the ledger `contracts` line, and any store key or
   path that includes `OUTPUT_SCHEMA_VERSION`. These are record **shape** and version-stamp changes, not changes to
   any measured value, and the golden is re-recorded once, in the bump's commit, with a test asserting that the
   re-recorded golden differs from the pre-bump golden by exactly those and nothing else. Any other move is a
   defect. The golden is **partial, not redundant** against the ledger (the `walk` fingerprint pins the
   `WalkResult`, not the assembled `EmailDocument`): it pins the serialized `EmailDocument`, the `WalkResult`,
   `resolve_span` samples (the identity guard), `CapRecord`s, the store artifact bytes and `ParseResult`. It is a
   committed file the test never regenerates silently, checked on both interpreters with a recorded waiver rather
   than a silent skip. **It is captured in its own turn (1b.0c) before the first frozen-module edit.**
3. **Writer and reader share an author, so they can agree on a wrong layout.** Independent breakers are
   mandatory: (a) `olefile` as a tests-and-tools comparator on **well-formed** fixtures only (it is silent on a
   cyclic FAT chain and clamps a 2**40 size claim to 0 bytes, so it cannot judge hostile mutants); (b) one fixture
   **hand-built to Outlook's observed layout** from the eleven-file structure table, documented as hand-built, not
   real-Outlook provenance; (c) the owner's structure-only probe of the real files; (d) for hostile mutants, a
   falsifiable stream-fault classification, the sector-tiling sum and a seeded fuzz's bounded-work property.
4. **A reader never raises on input content.** Every malformed CFB is a `ParseResult` failure with a closed
   reason id or a document with a status and a `msg.*` gap. A work-per-input-byte budget (operation counts, never
   seconds) is asserted on the hostile set.
5. **Sidecars are typed by hand** from the spec and the fixture's construction table, never by running the reader
   (Phase 1 rule 3, with its additions-only ledger and label-leak guard extended to `.msg` fixtures).
6. **Gates are non-vacuous.** L1 per-family floors are declared from the fixture counts before the turn, not
   derived from the achieved value; "every `msg.*` gap id has a mutation case" runs over the **closed registry**,
   each hostile case produced by a named committed seed; no-silent-drop is asserted on **CFB sectors**, never on
   the virtual bytes (that would test the projection's own bookkeeping).

## Decisions already made (do not reopen)

- **D13 subset:** message-class gate (`IPM.Note*`, else a status and a gap); the transport-header stream;
  body streams (plain, HTML, compressed RTF with a decompress-only reader); subject and sender properties;
  recipient storages; attachment storages (method, filename, MIME tag, Content-ID, data, embedded message,
  depth <= 1 under the shared depth cap). Named properties are never resolved (`msg.named_property_unresolved`);
  every other tag is `msg.property_tag_unknown`, hex only. No GPL (`extract-msg`, `html2text`) in code, extras,
  tests or dev-dependencies; `chardet` and `charset-normalizer` are banned.
- **D13 encodings:** Unicode properties are UTF-16LE; for 8-bit strings and bodies the ladder is internet code
  page (`0x3FDE`) -> message code page (`0x3FFD`) -> all-ASCII -> strict UTF-8 -> windows-1252, with
  `encoding_source` recorded (the `EncodingSource` enum already has `internet_cpid`, `message_cpid`, `ascii`,
  `utf8_strict`, `windows_1252`); one trailing U+0000 is recorded and stripped; the raw bytes' digest is kept
  beside the decode. Both code pages are **fixed entries in `__properties_version1.0`, not streams**, and can
  disagree (measured: internet 28591 or 20127 against message 1252).
- **D13 spans:** a `.msg` citation is `part_level` with `verbatim_reason: container_stream`, carrying
  `{stream, byte_off, byte_len}` as provenance; canonical coordinates are decoded **character** offsets.
  "Verbatim" for `.msg` means the exact post-UTF-16LE string with CRLF kept.
- **D14:** `container_kind` is `cfb_msg`; `container_hash` addresses the CFB file; `content_fingerprint` is
  `sha256(selected body view's code points as UTF-8)` (HTML if present, else plain), so the same message saved
  as `.eml` and `.msg` has a **different** `container_hash` and an **equal** `body_digest` when both carry the
  same HTML. They never dedupe on raw hash and never pretend to.
- **D2/D13:** the MAPI transport-header stream (`0x007D`) is the headers part of a `.msg`; where it and another
  property disagree the transport header is canonical (`value_source=transport_header`) and the property is kept
  beside it with `headers.mapi_header_property_disagree` (registered, first emitted here).
- **D15/Phase 3:** no `TimeEvent` is emitted in Phase 1b (`times_axis` keeps its not-built encoding); raw time
  properties are recorded as facts.

## Measured facts the spec relies on (email-spike.md; eleven real files, structure only)

- 11/11 have `0x007D`; 10/11 are **HTML-only** (`0x1013`, a binary stream, no `0x1000`, no `0x1009`); one has plain
  (`0x1000`) plus compressed RTF (`0x1009`, `LZFu`, `\fromtext`) and no HTML. No plain-only and no RTF-only
  message was observed. Every string property is `001F`; `001E` never appears (older real mail has it, so
  fixtures cover it).
- `__properties_version1.0`: header **32 bytes** at the top level, **8 bytes** for recipient, attachment and
  embedded-message tables; `(size - header)` is a multiple of 16 in 26/26 tables; the top-level header's counts
  at `@16`/`@20` equal the directory-derived recipient and attachment counts in 11/11.
- Entry word `u32 = (tag << 16) | type`; variable-size entries store their size in the first data word; the
  embedded-message storage is `__substg1.0_3701000D`; attachment data is `3701:0102`. Recipient and attachment
  storages are `__recip_version1.0_#%08X` and `__attach_version1.0_#%08X`; named properties live in
  `__nameid_version1.0` and **their tag numbers are per-message** (never key a named property on its tag).
- **The transport headers' `Content-Type` describes the original MIME message**, not the `.msg`'s structure (the
  measured pair: the `.eml` was `multipart/alternative`, the `.msg` kept only the HTML). Structure comes from the
  `.msg`'s own streams; `0x007D`'s structure headers are recorded as claims about the original.
- A v3 file's 109 header DIFAT slots address at most 109 x 128 x 512 = about 7.1 MB; the spike files (<= 450 KB)
  never exercised the extended chain.

## The architecture decision: A'' (virtual bytes + serialized provenance)

Everything built in Phase 1 (`walk.py`, `headers.py`, `text.py`, `attach.py`, `selection.py`, the quote stages,
`assemble.py`) is coupled to RFC 822 bytes: spans are offsets into `raw`, the walker accounts every byte, and part
ids are content-addressed over those spans. A `.msg` has none. Chosen: keep **one walker** over a deterministic
**virtual RFC 822 byte string**, and add what the debate showed was missing.

1. **A span table**, found with `getattr(container, "span_provenance", None)` (not a member of the
   `@runtime_checkable` `Container` Protocol, so `EmlContainer` and `FakeContainer` stay valid): one row per
   virtual region, `kind in {stream, reencoded, synthetic}`, the source stream name, **source** `byte_off` and
   `byte_len` in the stream's own encoding (UTF-16 for `001F`), and for `reencoded` the decoded character range.
   The table is internal to the producer: no record a consumer can cite ever carries a virtual offset.
2. **Pass-through for binary and 8-bit leaves.** An HTML body in `0x1013` (10 of 11 real files) is projected
   unchanged with CTE `binary` and `charset=<chosen code page>`: its `size_bytes` and `sha256` are the stream's
   own and no base64 inflation is paid for attachments. Only `001F` text (the `0x007D` headers, plain `0x1000`)
   is re-encoded to UTF-8 (`_decode_cte` treats `7bit`/`8bit`/`binary` as identity).
3. **Uniform `part_level` / `container_stream` for every `.msg` leaf**, pass-through included
   (`resolve_span` adds `body_span.offset`, a virtual offset, even when the leaf bytes equal the stream bytes).
   `text.VERBATIM_REASONS` gains `container_stream`; `text.analyse_part` must not claim `exact` against virtual
   bytes.
4. **Header text.** `0x007D` is read per its property type (`001F` UTF-16LE, `001E` through the ladder), one
   trailing NUL stripped, then re-encoded UTF-8 for the scanner. `header_fields_at` and `header_region` take a
   `value_codec` seam (default `latin-1`, so `.eml` is unchanged; `utf-8` for `cfb_msg`) so `raw_value` and
   `text_decodes` carry the real text. Rejected: writing non-ASCII as RFC 2047 encoded-words (it makes
   `raw_value` a lie about the stream). Edge cases: bare LF is harmless; a trailing NUL is stripped before the
   scanner; a header truncated mid-line is flushed at EOF; an odd-length UTF-16 stream never reaches the scanner;
   a UTF-8 BOM and LF-only line endings are fixtures.
5. **Eight enumerated provenance points**, the only edits to frozen modules, each gated on `cfb_msg` or on the
   presence of a span table, each with its default branch the current expression **verbatim** (ranked by risk to
   the `.eml` golden):
   (1) the assembler fills `ContainerStreamRef` on `PartRecord` and `HeaderField`; (2) kind-gated `part_id` over
   `(container_hash, stream-keyed span {stream, byte_off, byte_len} or synthetic:<role>:<ordinal>, sha256 of the
   real source bytes)`; (3) `resolve_span` returns a stream span or `Unresolvable`; (4) `text.analyse_part`
   precision precomputed `part_level`/`container_stream`; (5) `encoding_source` overwritten from the MAPI ladder
   (the walker can only say `declared_charset`); (6) cap records' `declared_size_bytes` copy the real stream size,
   not a virtual length; (7) the store persists CFB sectors plus the span table, not virtual `Region`s; (8) entry:
   `parse` opens the container instead of refusing. If a comparison of `walk(msg)` with `walk(EmlContainer(an
   equivalent synthetic eml))` forces an edit to tiling or ordering inside `_walk_visit`, the architecture
   decision is re-opened (a `MsgContainer` that builds `PartShape` itself is the named fallback; it duplicates
   about 200 lines of `_walk_visit` that the golden does not protect, which is why it lost).
6. **Regions and no-silent-drop.** For `.msg`, `WalkResult.regions` describes the reader's own framing and is not
   persisted. Accounting is by CFB sectors: header, DIFAT, FAT, miniFAT, directory, a named stream's sector, free,
   slack; the sum equals the file length.
7. **Caps.** `max_decoded_*` are measured on decoded bytes, so a cap hit is consistent between `.eml` and `.msg`;
   `max_input_bytes` is on the file, so a 50 MB `.msg` passes the 64 MiB gate where its ~67 MB base64 `.eml` twin is
   refused. The asymmetry is recorded in the report, not hidden. Memory: with a `bytes`-valued `raw_bytes()` the
   virtual string materialises once; a lazy view would be a `container.py` protocol change and is out of scope
   unless experiment E4 shows it is needed.

**Constraints the experiments check.** C1: structure comes from the `.msg`'s own streams, never `0x007D`'s
`Content-Type`, boundary or CTE. **C2: no virtual offset is an input to any identity or stored in any record.**
A test builds the same message with two framing lengths and requires identical `part_id`s, `PartRecord`s and
citations; a second test mutates the `.eml` path and requires the `.eml` `part_id`s byte-identical. C3:
no-silent-drop accounts sectors. C4: the `.eml` golden (rule 2). C5: the same message as `.eml` and `.msg` yields one
`EmailDocument` shape with exactly the differences D14 documents. C6: synthetic framing is labelled
(`synthetic`), so a consumer can tell evidence from scaffolding.

## The one schema bump

The default "no schema bump" of revision 1 cannot hold: nothing in `EmailDocument` can carry `{stream, byte_off,
byte_len}`, the CFB cap reasons are not in `REASON_TABLE`, and an embedded message's summary has no field.
`OUTPUT_SCHEMA_VERSION` moves **once**, decided in Turn 1b.0a, containing exactly:
(X) `ContainerStreamRef {stream, byte_offset, byte_len, axis in {stream, reencoded, synthetic}, fault}` as an
optional field on `PartRecord` and `HeaderField` (or a side table keyed by `part_id`/ordinal: picked in 1b.0a);
(Y) the CFB cap reasons in `REASON_TABLE` (`sector_count_cap`, `directory_entries_cap`, `difat_chain_length_cap`;
stream size folds into `size_cap`/`cap_hit_mid_stream`), per owner decision O3;
(Z) an `EmbeddedSummary` (class, subject, has_transport_headers, recipient and attachment counts) on
`AttachmentOccurrence`.
`EncodingSource` and `ContainerKind` already carry every needed member and do not move; per-part stream size and
digest reuse `PartRecord.size_bytes`/`sha256` (a pass-through leaf's `sha256` is the stream's; a re-encoded leaf's
is the UTF-8 re-encoding's, with the stream's own digest in `ContainerStreamRef`: confirmed in 1b.0a).

## Further decisions (recommended defaults; the owner may overrule before the named turn)

1. **`cfb.py` is the package's own reader; `olefile` is a tests-and-tools comparator** on well-formed fixtures.
   D1 literally says "over `olefile`"; D13 mandates an own `cfb.py` with a promotion path to `docextract-core`; the
   design contradicts itself and is resolved toward D13 (owner decision O7: fix D1). Own reader forced by C3 (a
   per-sector classification) and rule 4 (a chain walk the package owns). About ten functions and three frozen
   dataclasses, 350-450 lines (`parse_header`, `walk_difat`, `read_fat`, `read_minifat`, `walk_directory`,
   `lookup_entry`, `chain_sectors`, `read_stream`, `classify_sectors`, `check_caps`).
2. **Hostile-CFB vocabulary (closed, against the real tables).** Directory loop -> NamedError
   `cfb_directory_loop`. Unsupported header/version (sector shift outside {9,10,11,12} for v3, or v4 with shift
   != 12) -> NamedError `cfb_header_unsupported`. CFB magic without `__properties_version1.0` -> the existing
   `not_a_message` (the `.doc`/`.xls`/`.ppt`/`.msi` case; `cfb_msg_unsupported` is deleted). Per-stream chain
   faults (cycle, out-of-range sector, chain shorter than declared size) yield a **document** with
   `Status.TRUNCATED` and the registered `msg.stream_truncated`, the fault recorded per stream.
   `cfb.read_stream` never raises: it returns `(bytes, fault)` with `fault in {OK, CYCLE, OUT_OF_RANGE,
   SHORT_CHAIN}`; out-of-range and short chain -> `stream_ended_early`, cycle -> `declared_length_mismatch`.
   `msg_fat_cycle` and `msg_directory_loop` are hostile fixtures, not gap ids. The entry point sniffs, so a
   renamed `.doc` changes from `skipped(cfb_msg_unsupported)` to `not_a_message`.
3. **Extended DIFAT: read through (bounded), record `msg.cfb_difat_extended` as an observation, fault only on a
   broken chain** (owner decision O1; this exceeds D13's letter "a named gap, not a crash"). Reconcile
   `phase0-gaps.md:615-621` and D13 line 784 with whichever the owner chooses.
4. **Class gate.** Non-`IPM.Note*` -> `Status.UNSUPPORTED` (takes no reason), the class verbatim in
   `container_facts.message_class`, the registered `msg.class_not_ipm_note` kept (gap = what was not read and why;
   status = what the document is). Nothing past the class is opened.
5. **No transport-header stream (`0x007D` absent): no header synthesis.** `headers=[]`; the header field, date and
   address walkers do not run over an empty synthesized block; the only gap is `msg.transport_headers_absent`, once
   at document level (so `headers.no_date` and `headers.no_from` are not emitted as noise); subject, sender,
   recipients and times are still recorded as `value_source=mapi_property` facts (owner decision O6).
6. **Time evidence as facts, not events.** `container_facts` keys `time.<tag-hex>.filetime_hex` and
   `time.<tag-hex>.utc`, the raw 64-bit value as **hex** (lossless), keyed on the hex tag. Candidate tags to verify
   by probe P2: `0x0039` (observed), `0x0E06`, `0x3007`, `0x3008`. The `Date` header and the MAPI properties
   stay distinct; a pair fixture where they disagree feeds Phase 3. A FILETIME carries no UTC offset (a Phase 3
   concern). No `TimeEvent`, no ordering claim.
7. **RTF (de-encapsulation cut, owner decision O2).** The reader decompresses `0x1009` (`LZFu` and
   uncompressed `MELA`, header size and CRC checked; a mismatch is `msg.stream_truncated`), records
   `container_facts.body_streams=rtf`, and emits the registered `msg.rtf_to_text_unsupported`; no body view is
   produced from RTF (`BodyView` is `HTML`/`PLAIN` only; a derived view labelled `html` would be the mislabelled
   digest D14 forbids). `msg.rtf_encapsulation_refused` is not created. If the owner keeps de-encapsulation, it is a
   separate cuttable turn with its own version constant and a new `BodyView` member.
8. **Embedded messages (depth <= 1) are read and recorded, not recursed.** The occurrence carries an
   `EmbeddedSummary`; beyond depth 1, `msg.embedded_depth_cap`. A storage has no file bytes, so its identity is a
   **`storage_tree_sha256`** over a defined canonical walk (entries sorted by name; each name, type, size and stream
   bytes), documented and never claimed to equal any `.msg` file's hash. Recursion into the embedded message as a
   child document is Phase 2 (`children_axis` stays not built).
9. **Attachment methods.** By-value (1) is read; embedded message (5) per decision 8; OLE (6) is recorded (class,
   size, name) without parsing the object; reference methods (2, 3, 4) and web references are recorded with
   `msg.attachment_method_unsupported`, and no path is ever followed or used. Filename ladder: long name
   (`0x3707`) over short (`0x3704`) over display name (`0x3001`); raw and decoded both kept (hostile filename never
   used as a path). Content-ID (`0x3712`), MIME tag (`0x370E`) and the hidden/inline flags feed the existing
   `attach.cid_*` and `decorative_hint` machinery. Every tag here is "verify by probe P4" before Turn 1b.7.
10. **Signed and encrypted mail** (`IPM.Note.SMIME*`, `IPM.Note.Secure*`): default is class recorded, no body, never
    verified (owner decision O8; the layout is not evidenced, probe P1).
11. **New gap ids (budget: three, each costing a registry line, a `phase0-gaps.md` entry, a fixture and a mutation
    case):** `msg.transport_headers_absent`, `msg.attachment_method_unsupported`, `msg.recipient_table_unreadable`.
    The eight registered `msg.*` ids and `headers.mapi_header_property_disagree` are first emitted here.
12. **Versions.** New constants in `versions.py`: `MSG_READER_VERSION = "1"` (the MAPI layer and the ladder),
    `CFB_VERSION = "1"` (primitives), `MSG_PROJECTION_VERSION = "1"` (the framing). Each is a ledger component keyed
    by corpus. `EMAIL_PARSER_VERSION` moves only if a measured `.eml` value moves (it must not, rule 2).
    `OUTPUT_SCHEMA_VERSION` moves once (above).

## What a `.msg` document carries (the contract, not the code)

- `container_kind=cfb_msg`; `container_hash` over the file bytes; `container_facts` (an open `str -> str`
  mapping, names fixed in 1b.0a and listed in the ledger): `adapter`, `cfb_version`, `sector_size`,
  `mini_sector_size`, `mini_cutoff`, `sector_count`, `directory_entries`, `message_class`, `internet_codepage`,
  `message_codepage`, `body_streams`, `has_transport_headers`, `recipient_count`, `attachment_count`,
  `named_property_count`, the `time.*` keys, and `projection=virtual_rfc822`.
- `headers`: the `0x007D` fields in order, duplicates kept, `value_source=transport_header`, decoded by the
  existing header stage with the `utf-8` codec; spans are `part_level` / `container_stream`.
- `parts`: one per body stream present (plain, HTML), `encoding_source` from the ladder, the Phase 1 selection
  rule (HTML over plain where both exist; per-view levels never reconciled across views); one per attachment.
- `attachments`: per decision 9, three type verdicts (`declared_mime` from `0x370E`, `magic` from the bytes,
  `container_introspection` still not built), and the `EmbeddedSummary` where applicable.
- Recipients: **facts** (`To`/`Cc`/`Bcc` rows with display name, SMTP address or the address type's raw form,
  recipient type), `value_source=mapi_property`, distinct from the header's address rows so a disagreement is
  visible, not merged.
- `quote_boundaries`/`view_levels`: the Phase 1 stages over the projected body, unchanged.
- `status`: `parsed`, `skipped(<cap>)`, `truncated` (per-stream fault) or `unsupported` (class gate); the caps
  extend to the CFB caps, each a built observation.

## Layout to create

```
emailextract/
  cfb.py          # primitives: header, DIFAT, FAT, miniFAT, directory, streams, caps, sector classes; no message knowledge
  mapi.py         # property tables, tag/type decode, string ladder, class gate, recipients, attachments
  msgcontainer.py # MsgContainer: the Container for cfb_msg; the virtual bytes and the span table (A'')
tools/
  cfb_writer.py            # the deterministic minimal CFB writer (no reader import, no GPL)
  make_msg_fixtures.py     # builds the .msg fixtures from a construction table
  msg_probe.py             # the owner's structure-only layout probe (extends real_probe.py), prints aggregates
fixtures/msg/              # binary fixtures + SHA256SUMS freeze + hand-typed *.expected.json
tests/support/olefile_oracle.py     # tests-only comparator, well-formed inputs only
tests/support/fake_msg_container.py # FakeMsgContainer: hand-made virtual bytes + hand-written span table
tests/golden/                       # the committed .eml golden (1b.0c)
docs/design/msg-architecture.md     # written by Turn 1b.0b (the eight experiments)
docs/design/phase1b-fixtures.md     # the catalogue, written by Turn 1b.0a
```

## The turns

Each turn declares its modules and new test names; a collection test asserts the declaration; every turn names a
pre-declared stop point; the build agent never commits; the owner commits each turn before the next. Test ceilings
are guidelines, not measurements. The provenance edits (1b.1) are built **before** `cfb.py`, against a
`FakeMsgContainer`, as Phase 0 did with `FakeContainer`, so the riskiest edits do not wait on the CFB work.

| turn | content | new gap ids first emitted | test ceiling | stop point |
|---|---|---|---|---|
| **1b.0a** | **documents only:** design revision 4 (D1/D13 reconciliation, decisions above, `container_facts` names, the exact bump contents (X)(Y)(Z) and the `ContainerStreamRef` placement, the `sha256` rule for re-encoded leaves), the fixture catalogue, the `FACTS` ids and shapes for `.msg`, registry entries for the three new ids, the ledger additions and turn declarations, the probe specification (P1-P6: what the probe prints, what to paste back; the script itself is built in 1b.0b) | none | 0 | owner commits; owner runs the probes |
| **1b.0b** | **spike, no package code, eight closed experiments on hand-built bytes** (below); `msg-architecture.md`; builds `tools/msg_probe.py` (tools only) for the owner's P1-P6 | none | 0 | owner ratifies A'' |
| **1b.0c** | **the `.eml` golden**, captured before any frozen-module edit (rule 2) | none | 10 | golden committed; owner commits |
| **1b.1** | the schema bump, the eight provenance points and the `value_codec` seam, built against `FakeMsgContainer`; C2/C5 tests; the `.eml` golden stays green | none | 55 | after the golden re-check |
| **1b.2** | `tools/cfb_writer.py` and the first fixtures (`msg_headers_only`, `msg_headers_html`, a v4 4096-byte-sector file, the mini-cutoff trio), construction table, hex pins, `SHA256SUMS`; the `olefile` oracle test of every well-formed fixture | none | 25 | writer output frozen; owner commits |
| **1b.3** | `cfb.py`, caps, sector classification, the hostile set and seeded fuzz, the work-per-byte budget | `msg.cfb_difat_extended`, `msg.stream_truncated` | 45 | after the hostile set, before MAPI |
| **1b.4** | `mapi.py`: property tables (32- and 8-byte headers), entry decode (fixed, variable, storage-backed), `001E`/`001F`/multi-valued, the ladder with both code pages, trailing NUL, class gate, named-property recognition, recipients | `msg.class_not_ipm_note`, `msg.property_tag_unknown`, `msg.named_property_unresolved`, `msg.codepage_unresolved_ladder_used`, `msg.recipient_table_unreadable` | 45 | before the container |
| **1b.5** | `msgcontainer.py` over real CFB: the projection, the span table, `parse()` stops refusing CFB, headers from `0x007D`, bodies through the Phase 1 stages, sector accounting; golden green | `msg.transport_headers_absent`, `headers.mapi_header_property_disagree` | 50 | after headers and one HTML body end to end |
| **1b.6** | message-level facts: subject, sender, recipients beside the headers, the `time.*` facts, the property-versus-header conflict pair | none | 25 | |
| **1b.7** | attachments: by-value, cid and hidden flags, filename ladder, type verdicts, embedded message with `storage_tree_sha256` and the depth cap, OLE and reference methods | `msg.embedded_depth_cap`, `msg.attachment_method_unsupported` | 45 | |
| **1b.8** | RTF minimum: decompress, record, `msg.rtf_to_text_unsupported` (cut entirely if O2 says drop the reader) | `msg.rtf_to_text_unsupported` | 20 | |
| **1b.9** | the cross-container pair and D14, the Outlook-layout hand-built fixture, the encoding fixtures (`001E` with code pages 1252, 20127, 28591, 65001; internet-versus-message disagreement) | none | 25 | |
| **1b.10** | gates over real output, the hostile run, the scope test, ledger components, the final report, release preparation (`0.2.0`: CHANGELOG, README "not a `.msg` reader" removed, version) | none | 30 | owner commits; owner tags |

**Turn 1b.0b: the eight experiments** (input, pass/fail, decision settled). E1 `olefile` on the hostile set (the six
mutants of the debate plus a v4 file and the 4095/4096/4097 mini-cutoff trio): every outcome recorded; settles the
oracle's scope. E2 the `cfb.read_stream` fault contract: no exception, `(bytes, fault)` returned, directory and
header faults become NamedErrors, per-stream faults a document. E3 sector accounting: the seven classes sum to the
file length, free/slack explicit, a cyclic chain visible as unaccounted. E4 large-attachment memory (a synthetic
40 MiB stream, pass-through versus re-encoded): peak RSS delta under a declared budget, no more than one extra copy;
settles whether a lazy `raw_bytes()` is needed. E5 identity determinism: `FakeMsgContainer` at two framing lengths
gives identical `PartRecord` ids, citations and `WalkResult` modulo provenance. E6 the 8-bit header seam:
non-ASCII `0x007D` text from `001F` and `001E` gives `raw_value` and `text_decodes` equal to the hand-typed text,
`.eml` default byte-identical. E7 precision precompute: an already-decoded body is `part_level`/`container_stream`,
never `exact`. E8 the store artifact: re-ingest byte-identical, the `.eml` artifact bytes untouched, no virtual
offset persisted. Plus one comparison: `walk(msg)` against `walk(EmlContainer(equivalent synthetic eml))` modulo
provenance fields.

## Fixture catalogue (the 1b.0a document fixes names; this is the floor)

`msg_headers_only`, `msg_headers_html`, `msg_html_only_no_plain`, `msg_plain_only`, `msg_plain_and_html`,
`msg_rtf_compressed_body` (plain + `\fromtext`), `msg_rtf_only` (no plain, no HTML), `msg_rtf_bad_crc`,
`msg_embedded_message`, `msg_embedded_depth_two`, `msg_attachment_with_cid`, `msg_attachment_hidden`,
`msg_attachment_ole`, `msg_attachment_by_reference`, `msg_attachment_hostile_name`, `msg_attachment_zero_size`,
`msg_attachments_4095_4096_4097`, `msg_duplicate_filenames`, `msg_non_ipm_note` (appointment), `msg_signed_class`,
`msg_truncated_stream`, `msg_no_transport_headers`, `msg_transport_headers_utf8_bom`,
`msg_transport_headers_lf_only`, `msg_codepage_disagree`, `msg_string8_1252`, `msg_string8_ascii20127`,
`msg_string8_utf8_65001`, `msg_string8_body`, `msg_zero_length_body` (present-but-empty is not absent),
`msg_unicode_subject`, `msg_non_bmp_text` (surrogate pairs), `msg_multivalued_strings` (keep every value),
`msg_html_meta_charset_contradicts`, `msg_recipients_display_only`, `msg_recipients_ex_no_smtp`,
`msg_recipients_bcc_duplicates`, `msg_time_property_vs_date_header`, `msg_named_properties`, `msg_unknown_tags`,
`msg_v4_sectors`, `msg_mini_cutoff_boundary`, `msg_difat_extended`, `msg_fat_cycle`, `msg_directory_loop`,
`msg_outlook_layout_handbuilt`, and the cross-container pair `pair_gmail_reply.eml` / `pair_gmail_reply.msg`.
Test-only hostile seeds (committed seeds, not fixtures): a lone UTF-16 surrogate and an odd-length UTF-16 stream (the
bounded decoder must record, not raise), a recipient-count property that disagrees with the real rows, an
attachment storage with no data stream. About 50 fixtures, each with a hand-typed sidecar.

## The independent checks

- **`olefile` oracle** (tests only), well-formed fixtures only: stream and storage names, every stream's size and
  bytes, directory shape. Its version is a recorded-only run input; where it is lenient and the reader strict (or
  the reverse), the case is recorded, not hidden.
- **The `.eml` golden** (rule 2).
- **Seeded differential fuzz of the CFB layer:** mutate sector chains, directory links, header counts and sizes;
  every mutant returns a failure with a closed reason, a document with a gap, or the same document; any other
  exception (and `MemoryError`/`RecursionError` specifically) fails with the seed.
- **The writer-versus-layout check:** the hand-built Outlook-layout fixture's construction table is typed from the
  eleven-file structure table, not the writer's defaults; the owner's probe is the final common-mode breaker.
- **No-silent-drop for a container of sectors:** every sector of every fixture and mutant is accounted as header,
  DIFAT, FAT, miniFAT, directory, a named stream's sector, free or slack; the sum equals the file length.

## Exit criteria for Phase 1b

- L1 is 100% over every `.msg` fact family with a per-fact floor declared before the turn; L1 still fails on a wrong
  sidecar; every `msg.*` gap id has a mutation case (the Phase 1 anti-vacuity triple) over the closed registry, each
  from a named committed seed, and a catalogue test fails on an uncovered id; the phase-1b gap gate passes and fails
  when a gap is dropped.
- Rule 2 holds (every measured `.eml` value is byte-identical; only the direct consequences of the one bump, as rule 2 lists them, move).
  Every pre-existing test either passes unedited or is changed only in the owner-agreed categories: (1) Phase 1
  scope pins this release deliberately relaxes; (2) the one `OUTPUT_SCHEMA_VERSION` bump and its direct consequences
  (record shapes, `REASON_TABLE`, the gap registry, `NAMED_ERROR_REASONS`), re-recorded in the same commit; (3) the
  ledger `contracts` line and the store `walk_key`. A failing test in any other category (a changed `.eml` value, a
  `walk`/`decode_chain` fingerprint move, a sidecar fact move) is a defect. Both interpreters; ledger `--check`
  green with additions only.
- The package imports with no sibling, no `olefile`, no `chardet`, no GPL (a fresh subprocess after a full ingest of
  the `.msg` corpus; the "olefile not in `sys.modules`" assertion in `tests/test_container.py` survives: it is the
  real guard). `olefile` appears only under `tests/`, `tools/` and the `[dev]` extra (O4).
- No real `.msg` is in the repository (`fixtures/real/` empty and git-ignored, checked by a listing test); probe
  outputs the owner pasted are aggregates only, recorded in a note, not as fixtures.
- Identity: `.msg` documents are byte-identical across two runs, hash seeds, locales, time zones and both
  interpreters; re-ingest is a no-op; the cross-container pair meets D14; the C2 two-framing-lengths test passes.
- Final report: a committed file with the named resolutions and test ids, every version bump and why, every
  label-versus-parser disagreement, the `max_input_bytes` asymmetry, the licences (`olefile` BSD-3-Clause named in
  `NOTICE` as a test-and-tool dependency), and the open items handed to Phase 2 and Phase 3.

**Tests that will necessarily be edited** (named so the exit wording is honest; most rows are from hearth's
reading and are confirmed in 1b.0a): `tests/test_licence_audit.py:165-169` (`test_olefile_is_not_a_declared_dependency`;
`pyproject.toml:56` has `dev = ["pytest>=8"]`), `tests/test_phase1_scope.py` (module set about :196, banned imports
about :219, forbidden names about :245, runtime dependency about :271), `tests/test_container.py` (fake-container
tests), `tests/test_parse_entry.py` (the NamedError tuple), `tests/test_status_reasons.py`, `tests/test_contracts.py`,
`tests/test_contract_phase1.py`, `tests/test_closed_enums.py`, `tests/test_behavior_ledger.py` (contracts line),
`tests/test_turn_declarations.py`, `tests/test_phase0_gaps.py`, `tests/test_phase1_gap_gate.py`,
`tests/test_gap_falsifiability.py`.

## Owner decisions (2026-10-11: the owner accepted the reviewer's recommendation on every question)

- **O1. Extended DIFAT: read through** the bounded extended chain, record `msg.cfb_difat_extended` as an
  observation, fault only on a broken chain (exceeds D13's letter; D13 line 784 and `phase0-gaps.md:615-621` are
  reconciled in design revision 4). Probe P3 still reports whether the chain ever occurs in the owner's corpus.
- **O2. RTF: de-encapsulation is cut; the decompress-and-record minimum stays** (`LZFu`/`MELA`, header size and
  CRC checked, `container_facts.body_streams=rtf`, `msg.rtf_to_text_unsupported`, no body view). Turn 1b.8 is
  that minimum. `msg.rtf_encapsulation_refused` is not created and no `BodyView` member is added.
- **O3. CFB cap reasons: new `REASON_TABLE` members** (`sector_count_cap`, `directory_entries_cap`,
  `difat_chain_length_cap`), because the bump happens anyway and a CFB limit stretched onto `part_count_cap` or
  `depth_cap` would make a reader of the reason id infer the wrong cause. Contents (Y) of the bump stand.
- **O4. `olefile` is a `[dev]` extra** (BSD-3-Clause, already named in `NOTICE`), used only by the tests-and-tools
  oracle on well-formed fixtures; never imported by `emailextract/`.
- **O5. Process: accepted.** Golden-first (Turn 1b.0c) and the split container turns; thirteen turns including the
  three 1b.0 turns.
- **O6. No synthesized headers** for a `.msg` without `0x007D` (unchanged default).
- **O7. D1 versus D13: resolved toward D13.** The package's own `cfb.py` is the reader; `olefile` is the oracle.
  D1 is corrected in design revision 4.
- **O8. Signed and encrypted mail: class recorded, no body, never verified**, until probe P1 shows the real layout.
  Hearth's proposed split is not adopted.
- **O9. The memory budget is re-declared from 3x to 5x (2026-10-13, after Turn 1b.1's E4 re-run).** The lazy view did
  not move the metered peak (4.0x of a 40 MiB pass-through attachment, before and after), because the peak is
  `assemble()`'s payload read (`text.decoded_payload` consumed by `attach.read_prefix`), not the walker's copy. 4.0x
  meets 5x, and the worst case is bounded by `max_input_bytes` (64 MiB -> ~256 MB peak). The `attach.py` view
  (`decoded_payload` returns a `memoryview`; `read_prefix` materialises only its short prefix) is **not** done in 1b.1:
  it joins Turn 1b.5's allow-list (`emailextract/attach.py`), where experiment E4 is re-run on the real projection. The
  re-encoded case (7.05x) stays recorded, not gated. This answers 1b.0b's Q5 (and settles Q1 as taken).

## Probes the owner runs (structure only, aggregates pasted back; none given to hearth's model)

P1 the signed-mail layout (does a signed item carry a readable body, or an opaque attachment?). P2 time property
tags (`0x0039`, `0x0E06`, `0x3007`, `0x3008`): presence and types. P3 CFB layout aggregate: version, sector size,
miniFAT use, DIFAT length (is the extended chain ever present), directory size, stream-size histogram. P4
attachment and recipient tag sets before Turn 1b.7 (method, `0x3707`/`0x3704`/`0x3001`, `0x3712`, `0x370E`,
flags; recipient address types SMTP versus EX). P5 8-bit prevalence (is `0x007D` ever `001E`; is a `001E` body
ever present). P6 vendor HTML classes (Outlook `divRplyFwdMsg`, the `x_` prefix).

## Risks (ranked) and the watch-list

1. **Same-author agreement on a wrong layout** (writer and reader): the `olefile` oracle on well-formed files, the
   hand-built Outlook-layout fixture and the owner's probe; none is a proof.
2. **A virtual offset leaking into an identity or a citation:** C2, with the two-framing-lengths test and the
   `part_level` rule; the very failure mode that sank revision 1's architecture.
3. **Silent `.eml` change through the eight provenance points:** rule 2, the golden, and "default branch is the
   current expression verbatim".
4. **Trusting `0x007D`'s structure headers:** they describe the original message.
5. **Hostile CFB** (cycles, loops, size lies): the closed vocabulary, `read_stream` never raising, the budget, the
   seeded fuzz; `olefile` is not the judge of hostile input.
6. **Property-tag misidentification:** the Phase 0 spike already corrected one wrong identification; every tag
   here is "verify" until a probe confirms it, and no doc freezes a tag.
7. **The 64 MiB input gate versus a 50 MB `.msg`:** a recorded asymmetry with the base64 `.eml` twin, not a defect.
8. **Quote rules on `.msg` HTML:** Outlook rewrites class names (`x_` prefix, `divRplyFwdMsg`); expect
   `body.html_quote_rule_gap` on real mail, and treat probe P6 as a Phase 1b input.
9. **`olefile` becoming a de-facto dependency:** the import scope test is the guard.
10. **Gates that cannot fail:** floors declared in advance, the closed registry and named seeds, sector-level
    accounting (rule 6).
