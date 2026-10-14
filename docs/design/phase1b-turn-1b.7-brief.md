# Turn 1b.7: attachments and embedded messages -- the MIME projection of attachments, the MAPI attachment facts, the depth cap

Status: brief for one build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `d50b3e2` (Turn 1b.6
committed: `message_facts`, `recipient_count`, `time.*`, the four observation gaps). Run hearth in
`C:\Users\ivan_\App_repos\email-extract`, fresh session. **Do not commit.**

This is the second-heaviest turn of Phase 1b (1b.5 was the first). **Work in the order below and run only the files you touch** until
the last step. The clean boundary, if the turn runs long, is the end of **step 4** (by-value attachments end to end): stop there and
report; embedded, OLE and reference methods are then the next turn.

## What this turn is

A `.msg` attachment becomes an `AttachmentOccurrence` through the **same Phase 1 attach stage** a `.eml` attachment goes through. That
is the A'' point (build spec, "The architecture decision"): the container publishes one deterministic virtual RFC 822 message, and the
one walker and the one `attach.py` read it. So this turn **projects each attachment as a MIME leaf of the virtual message**, with the
attachment's bytes as a pass-through `STREAM` span row, and the MAPI-side properties (method, filename ladder, MIME tag, Content-ID,
flags, sizes) as the synthetic part headers the attach stage already knows how to read. It also reads the **embedded message**
(method 5) into an `EmbeddedSummary` without recursing, computes its `storage_tree_sha256`, enforces the **depth cap**, and records OLE
(6) and the reference methods (2, 3, 4, and a web reference) **without reading or following anything**. It does not build RTF (1b.8),
encodings fixtures (1b.9), or the `evals/` measurers and `msg` ledger components (1b.10).

Read first: `phase1b-turn-1b.5-brief.md` and `phase1b-turn-1b.6-brief.md` (the layout and the fact channels you extend) and their
outcome notes in `phase1b-ledgers.md` (**especially "What Turn 1b.7 and Turn 1b.10 need from this turn"** and "Reported, not
bent"), `phase1b-build-spec.md` ("Further decisions" 8 and 9, the E4 lines, P4), `phase1b-contract.md` (sections 1(Z), 5, 6, 7, 13),
`phase1b-facts.md` (`msg.attachments`, `msg.embedded_summary`, `msg.storage_tree_sha256`: fixed value shapes), `phase1b-fixtures.md`
(Family G and the seeds section), `phase0-gaps.md` (`msg.attachment_method_unsupported`, `msg.embedded_depth_cap`,
`msg.stream_truncated`), `emailextract/attach.py` (what it reads: `_filename`, `_disposition`, `normalized_cid`, `_hint`,
`_declares_message_rfc822`, `decoded_payload`), `emailextract/msgcontainer.py`, `emailextract/mapi.py`, and `emailextract/cfb.py`
(read-only: `lookup_entry`, `read_stream`, the entries tuple with full paths).

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D0. Three corrections to earlier turns, first.**
1. **The body-fault gap id (a 1b.5 defect I missed in review; hearth reported it in 1b.6).** `msgcontainer._project` appends
   `ContainerGap(plain.fault)` and `ContainerGap(html_fault)`, i.e. the fault *name* (`stream_cycle`, ...) as the gap id. The registry
   id is `msg.stream_truncated` with the stream and fault in the detail (the form the per-stream chain fault already uses at
   `msgcontainer.py:246`). Fix both, and make a **transport-header (`0x007D`) stream fault** raise the same gap (today it is dropped
   silently). Check what `Status` a body or transport fault gives and that it matches contract section 2 (`TRUNCATED`,
   `declared_length_mismatch` for a cycle, `stream_ended_early` otherwise); if it does not, that is a finding to report, not to
   paper over. A test pins the id, the detail and the status for each of the three streams.
2. **A fact-table typo.** `phase1b-facts.md` (`msg.attachments`) says method `2` is "by-value"; the build spec, the registry and
   MS-OXCMSG say `1` is by-value, `2` by-reference, `3` by-reference-resolve, `4` by-reference-only, `5` embedded message, `6` OLE.
   Correct that one sentence in `phase1b-facts.md` (before any sidecar uses it) and list the edit.
3. **Pin before changing.** Before you touch the projection, record the sha256 of the virtual bytes and the span rows of every
   existing committed `.msg` fixture (a test fixture file or a computed pin). The projection of a message **with no attachments must
   stay byte-identical** (D1); this is the guard.

**D1. The projection of attachments.** A message with attachments is a `multipart/mixed` whose first child is the body as 1b.5 builds
it (plain, HTML, or the `multipart/alternative` of both; or an empty text leaf if there is no body, as you decide and report), followed
by one leaf per attachment, in **attachment-storage index order** (the directory's `__attach_version1.0_#XXXXXXXX` order, never a
declared count). The multipart structure lines, boundaries and each leaf's synthetic part-header lines are `SYNTHETIC` rows, labelled
`synthetic:<role>:<ordinal>`; the boundary is chosen deterministically (a counter until absent from every payload, as in 1b.5). A
message with **no** attachment storages produces exactly the 1b.5 bytes. The top-level `Content-Type` structure line is still first, so
D1's first-wins layout from 1b.5 holds; re-measure it with `multipart/mixed` and report.

**D2. A by-value attachment's leaf (method 1, `0x3701:0102`).** Body = the stream's own bytes, pass-through, CTE `binary`, a `STREAM`
span row (`source_sha256` = the stream's digest, read through `cfb.read_stream`). `PartRecord.size_bytes` and `sha256` are the stream's
(contract section 5), `verbatim_reason = container_stream` (never `exact`). Part headers, each a synthetic line:
* `Content-Type`: the `0x370E` MIME tag as stored; **if absent, `application/octet-stream`**. Record `mime_tag = None` in the
  attachment facts (D5) so the sidecar-side projection (1b.10) can tell "declared" from "defaulted", and measure what the attach
  stage's `declared_mime` verdict then reports and say so in the note.
* `Content-Disposition`: `inline` when the attachment-flags property `0x3714` has bit `0x4` set (`ATT_MHTML_REF`: referenced by the
  body), else `attachment`; with the filename parameter from the ladder (D3).
* `Content-ID`: from `0x3712` as stored, wrapped in `<...>` only if it is not already.
* `Content-Transfer-Encoding: binary`.
**Hidden** (`0x7FFE`) has no MIME equivalent: record it in the attachment facts, and do **not** invent a header for it. The 1b.4/ledger
test name `test_cid_and_hidden_flags_feed_the_attach_stage` stays as declared, but assert what actually reaches the attach stage and
**report the name mismatch as a finding** if hidden reaches nothing.

**D3. The filename ladder, raw and decoded.** Long name `0x3707` over short `0x3704` over display name `0x3001`; the first that is
present and non-empty wins and its source (`long`/`short`/`display`/`none`) is recorded. The property text is the **decoded** name
and is kept **verbatim** in the attachment facts (`filename_raw` is the property text exactly as stored, `filename_decoded` is what the
attach stage derives from the projected header; for a property string the two are equal unless the header encoding could not carry
it). The projected header must encode any name so `attach.py` recovers the original text byte-for-byte: RFC 2231 percent-encoding of
UTF-8 (`filename*=utf-8''...`) for anything outside printable ASCII, **and for `"`, `\`, `/`, `;`, control characters and NUL**. A
hostile name (path separators, `..`, NUL) is **data, never a path**: no `Path`, `open`, `os.*` call anywhere on it; a test patches the
filesystem entry points and shows none is called while the name is read. Do not "sanitise" the stored text: sanitising is a consumer's
job.

**D4. Embedded message (method 5, `0x3701:000D`) and OLE (method 6).** Neither has bytes a consumer can read as a stream: the leaf is a
**zero-length `SYNTHETIC` body** with `Content-Type: application/octet-stream`; `PartRecord.size_bytes`/`sha256` are `None` (contract
section 5, synthetic). **Do not use `message/rfc822`** for the embedded leaf: `attach.py` treats a declared `message/rfc822` as an
occurrence with its own filename rule (`attach.filename_absent` gap) and the embedded storage has no RFC 822 bytes to back the claim.
(Read `attach.py` `_declares_message_rfc822` and confirm; if you find a better-evidenced choice, take it and say why.)
* **Embedded**: read the embedded storage's own property table through `mapi` into an `EmbeddedSummary` (`message_class` verbatim,
  `subject`, `has_transport_headers`, `recipient_count`, `attachment_count`, the two counts being **directory-derived** rows of that
  storage). **The embedded message's property-table header size is not the top-level 32 bytes**: decide it from the fixture by the
  `(size - header) % 16 == 0` rule and the `olefile` oracle, with [MS-OXMSG]'s embedded-message value (24) as the hypothesis, and
  report what you found. The summary lands on `AttachmentOccurrence.embedded` (the field exists since 1b.1; the invariant is that it is
  non-`None` **only** for method 5).
* **Depth cap**: depth 1 (the embedded message) is read. If that embedded message itself has a method-5 attachment, that nested embed is
  **not descended**: record `msg.embedded_depth_cap` (detail names the nested attachment's path, e.g. `1.2>1`), and the nested one
  still counts in the embedded message's `attachment_count`. Read the registry entry: the occurrence "carries an `EmbeddedSummary` and
  a `storage_tree_sha256`".
* **`storage_tree_sha256`** over a **defined canonical walk**, documented in `msg-architecture.md` **before** it is coded and checked
  by an independent construction in the test: the entries under the embedded storage (not the storage entry itself), sorted ascending
  by their full relative path as UTF-8 bytes (separator `/`); for each entry append `b"S"` (storage) or `b"T"` (stream), the path
  length as 4-byte big-endian, the path UTF-8, the stream size as 8-byte big-endian (0 for a storage), and for a stream its bytes; the
  digest is the sha256 of that concatenation. If a stream under the storage faults, no digest is published (`None`) and the fault is
  recorded as `msg.stream_truncated`. It is **never** claimed to equal any file's hash.
* **OLE (6)**: recorded (method, name, size where a stream size exists) with **no parsing of the object**; if `CfbEntry` exposes the
  storage CLSID, record it as the class; if not, say so and record nothing.

**D5. Reference methods and everything unsupported (2, 3, 4, and a web reference, method 7).** Recorded (method, filename ladder, no
bytes), the leaf is a zero-length `SYNTHETIC` body as in D4, and the gap `msg.attachment_method_unsupported` is emitted with the detail
`<index>:<method>`. **No path or URL property is read at all** (`0x3708` pathname, `0x3707`-style fields on a reference attachment are
read only as the filename ladder; `0x3701` is not looked for on a reference method). An unknown method number is recorded raw and
treated the same way. A by-value (1) attachment with **no data stream** (`seed_attachment_no_data`) or a **faulted** data stream: the
reviewer's default, which you may overrule with evidence, is the same rule as a body stream: gap `msg.stream_truncated` (detail
`attach:<index>:<fault>`, `stream_absent` for a missing stream), document `Status.TRUNCATED`, no leaf bytes claimed. Do not invent a
new gap id: the budget of new ids is spent.

**D6. Where the facts live.** As in 1b.6: a frozen `attachment_facts` attribute on `MsgContainer` (plain data, no `Property` objects),
one record per attachment storage in index order with: `index`, `method` (int, raw), `filename_raw`, `filename_source`,
`mime_tag`, `cid`, `hidden`, `inline`, `size`, `sha256`, `embedded_summary` (or `None`), `storage_tree_sha256` (or `None`), `fault`,
and the `source_stream` name that joins it to its span row. The `msg.attachments` sidecar row (`phase1b-facts.md`) is a projection
of these in 1b.10. `container_facts["attachment_count"]` is the **directory row count**, published only when it is at least 1 (the
rule 1b.6 settled for `recipient_count`; absent for a stopped message). The join between a record and its `PartRecord` is through the
span table (the same mechanism `stream_ref_of` uses), **never** through a virtual offset published in a record or `part_id`.
`assemble.py` gains one `cfb_msg`-gated edit: it builds `AttachmentOccurrence.embedded` from `attachment_facts`; the default branch
(every `.eml`) stays the current expression verbatim.

**D7. Reading the attachment tables (`mapi.py`).** Add, to `KNOWN_TAGS` as table rows: `0x3703`, `0x3704`, `0x3705`, `0x3707`,
`0x370E`, `0x3712`, `0x3714`, `0x7FFE`, `0x3701` (the data tag), each with its expected type(s), `source = "MS-OXPROPS"` (P4 has not
been run on real mail: say so). Add the attachment-row reader beside `read_recipients` (rows from the **directory**, never a declared
count; each row's table uses the 8-byte header; same fault discipline, never raises, a bounded work tick per row). The reader returns
the per-attachment record, the embedded-storage summary, and the method. `mapi.py` stays free of `olefile`. Every observation raised
(`msg.property_tag_unknown` etc.) goes through the 1b.6 mapping unchanged.

**D8. Memory (E4) with an attachment.** A synthetic 40 MiB by-value attachment through `MsgContainer` + `walk` + `assemble`: report the
peak working-set delta as a multiple of the stream, with the container, container + walk and container + walk + assemble steps and the
copy inventory (the 1b.5 note's form). The budget for this turn is the 6x the owner is treating as the ceiling for pass-through
streams; if you exceed it, **stop and report which copy dominates** (the lazy `raw_bytes()` view is a protocol change the owner
decides). `attach.py` stays untouched.

## Order of work

1. **D0**: the pins, the body/transport fault-gap fix and its test, the facts-doc sentence. The suites for the touched files stay green.
2. `mapi.py` (D7): the tag rows and the attachment-row reader; `tests/test_mapi.py` additions for the reader (hand-typed expectations
   first; the `olefile` oracle cross-checks the same rows). The embedded table's header size is decided here by measurement.
3. Fixtures: construction tables **typed first** in `tests/support/msg_construction.py` from MS-OXPROPS and the layouts already
   encoded, then `tools/make_msg_fixtures.py` and `fixtures/msg/SHA256SUMS`. The ten Family G fixtures
   (`msg_embedded_message`, `msg_embedded_depth_two`, `msg_attachment_with_cid`, `msg_attachment_hidden`, `msg_attachment_ole`,
   `msg_attachment_by_reference`, `msg_attachment_hostile_name`, `msg_attachment_zero_size`, `msg_attachments_4095_4096_4097`,
   `msg_duplicate_filenames`), each with a hand-typed expectation written before the code. The remaining named seed
   `seed_attachment_no_data` is built **inside the test** from a fixture by patching one field (the 1b.3 `_seeds` pattern), not
   committed. **No `.msg` sidecars.** The mini-cutoff trio (4095/4096/4097) is where the mini-stream and the regular-sector read meet:
   assert sizes and digests against the `olefile` oracle.
4. `msgcontainer.py` D1-D3, D6 for **by-value** attachments (`attachment_facts`, `attachment_count`, the projection, the headers).
   Tests: `tests/test_msg_attachments.py` (6 declared). **Stop here if the turn is long.**
5. D4 and D5: embedded, OLE, reference, the unsupported and faulted cases, the depth cap, the digest; `assemble.py` D6 edit.
   Tests: `tests/test_msg_embedded.py` (3 declared) and the reference/fault tests in `tests/test_msg_attachments.py`.
6. D8 (E4), the extras below, full suites, `--check` tools, mutations, the outcome note.

## Tests

The 9 declared tests of the `declaration turn=1b.7` block, **names exactly as declared** (`phase1b-ledgers.md`):
`test_a_by_value_attachment_is_read`, `test_the_filename_ladder_is_long_over_short_over_display`,
`test_a_hostile_filename_is_never_a_path`, `test_cid_and_hidden_flags_feed_the_attach_stage`,
`test_reference_methods_are_recorded_and_dropped_unsupported`, `test_zero_size_and_the_mini_cutoff_trio`,
`test_an_embedded_message_carries_an_embedded_summary`, `test_the_storage_tree_sha256_is_a_canonical_walk`,
`test_beyond_depth_one_is_the_depth_cap`. Plus extras, declared in the same block and added to `tests/test_turn_declarations.py`:
* **No-attachment byte identity** (D0.3): every earlier committed `.msg` fixture projects to the same virtual bytes and span rows as
  before this turn.
* **C2 again, with attachments**: build the same message with two framing lengths and require identical `part_id`s, `PartRecord`s and
  citations; no `virtual_*` value appears in any record, `part_id`, or `attachment_facts`.
* **C5 again, with an attachment**: the same message as `.eml` and `.msg` differs only where D14 says (container kind, hash, facts,
  `stream_ref`s, `encoding_source`, plus the filename/MIME fields that D2/D3 define), compared field by field against a hand-typed list.
* **The span table agrees**: every attachment `STREAM` row's `source_sha256` equals the sha256 of the named stream read through
  `cfb.read_stream` (not through `msgcontainer`); the persisted form is recomputed and equal.
* **Filename round trip**: for a table of names (ASCII, non-ASCII with a surrogate pair, `a/b`, `..\x00x`, `"quoted"`, a name with
  `;`) the attach stage's decoded name equals the property text.
* **Duplicate filenames and duplicate cids** reach the existing attach-stage duplicate gaps unchanged (no new id).
* **Hostile through the container**: `seed_attachment_no_data`, a faulted attachment data stream, a zero-size stream, and a tiny
  `CfbLimits` cap hit each yield the specified status, gap and `CapRecord`; none raises; `msg_embedded_depth_two` yields the gap and
  nothing deeper is read (assert the nested storage's stream bytes were never requested).
* **No reference is followed**: patch `open`, `os.stat`, `urllib`, `socket`, and `subprocess` entry points and run every reference
  fixture; none is called.
* **Determinism** of `attachment_facts`, `container_facts` and the virtual bytes under two `PYTHONHASHSEED` values.
* **Seeded fuzz extension**: operators on the attachment tables, the filename streams, the method word and the embedded storage; at
  least 150 more mutants over at least three fixtures; every mutant yields a document or a named refusal, every published string is
  UTF-8 encodable, no exception escapes.
* **The `.eml` path**: `update_eml_golden.py --check` and the behavior ledger stay green and untouched.

**Mutations** (each must make a named test fail; run, restore, report the failing test names): (1) read a reference method (2) as
by-value (follow `0x3701`, project its bytes); (2) take the short name before the long name; (3) hash the embedded storage tree without
sorting, or without the stream bytes.

## Allow-list

The ledger's block for `turn=1b.7` (`emailextract/mapi.py`, `emailextract/msgcontainer.py`, `tests/test_msg_attachments.py`,
`tests/test_msg_embedded.py`) **plus these named additions, which you must also write into the ledger's allow-list line in the same
turn**: `emailextract/assemble.py` (the D6 gated edit only), `fixtures/msg/`, `tools/make_msg_fixtures.py`,
`tests/support/msg_construction.py`, `tests/support/mapi_table.py`, `tests/support/olefile_oracle.py`, `tests/test_mapi.py`,
`tests/test_msg_fixtures.py`, `tests/test_msgcontainer.py` and `tests/test_msg_body.py` (**only** for the D0.1 fault-gap id fix, each
line named), `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`, `tests/ledger/label_ledger.json`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`, `docs/design/phase1b-ledgers.md`,
`docs/design/phase1b-facts.md` (the method-2 sentence only), `docs/design/msg-architecture.md` (the digest definition and the
attachment layout), `docs/design/phase0-gaps.md` (only if a registry sentence is wrong; list each edit). **`behavior_ledger.json` and
`versions.py` are permissions, not duties**: the three `msg` ledger components belong to 1b.10; do not add them, and if a `--check`
tool demands a change anyway, stop and say so. **Not**: `emailextract/cfb.py`, `emailextract/walk.py`, `emailextract/attach.py`,
`emailextract/model.py`, `emailextract/ingest.py`, `emailextract/parse.py`, `emailextract/evals/**`, `tools/cfb_writer.py`,
`tests/ledger/corpus.json`, the `.eml` golden, any `.eml` fixture, `CLAUDE.md`. If `attach.py` cannot read a projected leaf as D2 and
D3 intend (for example a NUL-bearing filename), **stop and report**: that is an owner decision, not an edit to `attach.py`.

## What must NOT be done

No `Path`/`open`/`os.*`/network call on any attachment name or reference property. No reading of `0x3708` or any path/URL property. No
descent below the embedded message at depth 1; no recursion into an embedded message as a child document (`children_axis` stays
not built). No parsing of an OLE object. No new gap id, no new `container_facts` key beyond `attachment_count`. No change to a record's
serialised shape (`EmbeddedSummary` and `AttachmentOccurrence.embedded` exist). No change to the virtual bytes of a message without
attachments. No virtual offset in any record, `part_id`, cap record or stored artifact. No sanitising or repair of a filename, a
Content-ID or any string (no replacement character, `surrogatepass` or latin-1 fallback). No `.msg` sidecar. No real or employer
message in any fixture. No `olefile` import under `emailextract/`. Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (with `docextract_core` and `olefile` installed); note the
   interpreter and the wall time by chunk.
2. `tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D0-D8 and whether you changed any, with evidence; the D1 first-wins
   re-measurement with `multipart/mixed`; what the attach stage reported for a defaulted versus a declared MIME type (D2); the embedded
   table's measured header size (D4); what `CfbEntry` exposes for an OLE class; the E4 number and copy inventory (D8); the ten fixtures
   with their hand-typed expectations beside the code's output; the three mutation results; the `Status` you gave a faulted or missing
   attachment stream; every existing test edited and why.
4. What 1b.8 (RTF), 1b.9 (encodings) and 1b.10 (measurers, persistence of `message_facts`, `attachment_facts` and `container_gaps`, the
   three `msg` ledger components, the L1 sidecars) need from this turn.

## Not this turn, but the owner should decide

* **Run probe P4** (`tools/msg_probe.py --probe P4`) on the real corpus: every attachment tag here is public-spec only until it runs.
* **`hidden` has no MIME equivalent** (D2): whether it should affect the decorative hint, and how.
* **A missing or faulted attachment stream**: `TRUNCATED` for the whole document (D5) or a per-occurrence status only.
* **The lazy `raw_bytes()` view** for large pass-through streams (E4), and the re-declared memory budget, for 1b.10.
* **A signed message's `Status`** (`UNSUPPORTED` as built, O8) and the **`IPM.Note*` boundary**: unchanged.

Stop at the turn boundary: by-value, embedded, OLE and reference attachments are read and tested, the depth cap holds, a message
without attachments projects exactly as before, the `.eml` golden is untouched, the outcome note is written. Do not start 1b.8.
