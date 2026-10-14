# Turn 1b.8: the RTF minimum -- decompress, check, record; no body view

Status: brief for one small build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `3adfd3d` (Turn 1b.7
committed: attachments and embedded messages). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session.
**Do not commit.**

**Pace this turn.** It is a small, self-contained turn: a decoder, a handful of fixtures, one wiring change. While iterating run only
the files you touch; run the full suite once at the end on the primary interpreter, once on 3.11, then the mutations.

## What this turn is, and is not

Owner decision **O2** (build spec) cut RTF **de-encapsulation** and kept the **decompress-and-record minimum**: the reader decompresses
a `0x1009` stream (`LZFu` compressed, `MELA` uncompressed), checks it, **records what it found**, lists `rtf` in `body_streams`
(already done in 1b.5) and emits the registered gap `msg.rtf_to_text_unsupported`. **No body view is produced from RTF**: `BodyView`
is `HTML`/`PLAIN` only, a view derived from RTF and labelled either would be the mislabelled digest D14 forbids, and no `BodyView`
member is added. `msg.rtf_encapsulation_refused` is **not created** (the declared test
`test_no_rtf_encapsulation_refused_id_exists` asserts exactly that absence, despite its name). There is **no RTF-to-text, no
`\fromhtml`/`\fromtext` interpretation, no `\htmlrtf` handling, no code-page extraction from the RTF header**: the decompressed bytes
are checked, hashed and counted, never read as RTF.

Read first: `phase1b-build-spec.md` (decision 7, O2, the RTF lines), `phase0-gaps.md` (`msg.rtf_to_text_unsupported`,
`msg.stream_truncated`), `phase1b-contract.md` sections 2 and 6, `phase1b-fixtures.md` (Family F, the three RTF rows), the 1b.5 and 1b.7
outcome notes in `phase1b-ledgers.md` (**especially "What 1b.8 needs" and how a body-stream fault is mapped after the D0.1 fix**),
`emailextract/msgcontainer.py` (`_has_stream` for `0x1009`, `body_streams`, `_project`, the fault-gap code), `emailextract/mapi.py`
and `emailextract/cfb.py` (read-only; `cfb.read_stream` returns `(bytes, fault)`).

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. A new pure module, `emailextract/rtf.py`, not more `mapi.py`.** `mapi.py` is already over a thousand lines and the decoder has no
message knowledge, exactly like `cfb.py`. `rtf.py` takes `bytes` and returns a frozen result; it never raises, never touches a file,
and has a declared work bound. The declaration block lists `mapi.py` and `msgcontainer.py`; add `emailextract/rtf.py` to the ledger's
allow-list line in the same turn, and update `tests/test_phase1_scope.py` (`EXPECTED_LIBRARY` and the import probes: 1b.5 needed it
for `msgcontainer.py`; it is not optional) naming each line. Touch `mapi.py` only if the container needs a helper it lacks, and say why.

**D2. The format, typed from the specification, not from memory.** [MS-OXRTFCP] section 2.1: a 16-byte header of four little-endian
`u32`s, `COMPSIZE` (the size of the stream **after** this first field, i.e. `stream_length - 4`), `RAWSIZE` (the decompressed length),
`COMPTYPE` (`LZFu` = `0x75465A4C` compressed, `MELA` = `0x414C454D` uncompressed), `CRC` (for `LZFu` the CRC-32 of the compressed
bytes after the header; for `MELA` it is `0`), followed by the data. `LZFu` data: a 4096-byte circular dictionary pre-loaded with the
207-byte prebuf text at the specification's initial write position; a control byte of eight flags (LSB first), a clear flag meaning one
literal byte, a set flag meaning a 2-byte big-endian reference of a 12-bit dictionary offset and a 4-bit length (stored length minus 2);
a reference whose offset equals the current write position is the **end marker**. **Type the prebuf bytes, the initial write position,
the reference layout and the CRC definition from [MS-OXRTFCP] itself**; if you cannot verify any of them against the specification
text, **stop and say which**, because a decoder built on a half-remembered constant would accept or reject real mail by accident. The
CRC: verify (and say) whether the specification's table-driven CRC-32 equals `zlib.crc32` over the same bytes (assert it on samples in
`tests/support`); if it does, the decoder may use `zlib`.

**D3. The decoder is streaming and keeps nothing it does not need.** Output is **not retained**: the decoder keeps the 4096-byte
dictionary, the running sha256 and the running length. The result records (frozen, plain data) `comptype` (`"LZFu"`, `"MELA"`, or the
raw `u32` as 8-digit lowercase hex when unknown), `stream_length`, `compsize_declared`, `rawsize_declared`, `crc_declared`,
`crc_ok`, `decompressed_length`, `decompressed_sha256` (`None` when faulted) and `fault` (`None` or a name from the closed list in D5).
Nothing in the result is the RTF text. `MELA` is accepted when `COMPSIZE`/`RAWSIZE` agree with the stream length, the data length
equals `RAWSIZE`, and `CRC == 0` (record `crc_ok` accordingly; report what a nonzero CRC on a `MELA` stream does and which way you
resolved it, citing the specification).

**D4. Bounded work, hostile-safe.** The input is bounded by the CFB layer's stream cap. Output is bounded by the format itself: one
2-byte reference expands to at most 18 bytes, so total output is at most about 9x the compressed data; the decoder additionally stops at
`RAWSIZE` (a stream that tries to write more than the declared raw size is a fault) and charges the container's work counter (the
`cfb`/`mapi` `work.tick` pattern) per output byte, with the same kind of declared bound, so a hostile stream hits a bound and not the
clock. A reference that **reads a dictionary byte that has not yet been written** is a fault (`rtf_dictionary_underrun`), never a
guessed fill byte; a reference that overlaps the bytes it is itself writing (run-length behaviour, offset = write position - 1) is
valid and must work byte by byte. Add a test with the maximal-expansion stream and assert the work bound and the memory (the decoder
must not allocate the declared `RAWSIZE`: a header declaring `0xFFFFFFFF` over 20 bytes of data returns a fault quickly).

**D5. Faults, and how they map (no new ids).** The closed fault list: `rtf_header_short` (fewer than 16 bytes, including an empty
stream), `rtf_comptype_unknown`, `rtf_compsize_mismatch`, `rtf_rawsize_mismatch` (decompressed length differs from `RAWSIZE`, or the
decoder would exceed it), `rtf_crc_mismatch`, `rtf_data_short` (input ends before the end marker), `rtf_dictionary_underrun`. Each is
recorded in the result and raises the **existing** `msg.stream_truncated` gap with the detail `0x1009:<fault>` (the form 1b.5's D0.1
fix gave body faults), and the document `Status` is `TRUNCATED`, with the reason from the contract-section-2 table:
`declared_length_mismatch` for `rtf_header_short`, `rtf_comptype_unknown`, `rtf_compsize_mismatch`, `rtf_rawsize_mismatch`;
`stream_ended_early` for `rtf_crc_mismatch`, `rtf_data_short`, `rtf_dictionary_underrun` (the catalogue says a bad CRC is
`TRUNCATED`/`stream_ended_early`). **`msg.rtf_to_text_unsupported` is emitted whenever a `0x1009` stream is present, faulted or not**
(it says the body is not converted; `stream_truncated` says it is damaged; both can be true). The reviewer's mapping for the
unknown comptype and the size mismatches is a choice, not a fact; list it in the note as an owner question rather than treating it as
settled.

**D6. No body view.** A message with `0x1009` and no plain and no HTML (`msg_rtf_only`) yields a document whose body projection is
whatever 1b.5 already does for "no body stream" (headers, no body leaf): no `PartRecord` for the RTF, no `BodyView`, no selection
result, `body_streams` = `rtf`, and the gap. A message with `0x1000` plus `0x1009` (`msg_rtf_compressed_body`) projects the plain body
exactly as in 1b.5, and the RTF adds only the record and the gap. **The projection's virtual bytes for every existing fixture are
unchanged** (pin the sha256 of the virtual bytes and span rows of the existing fixtures before you change anything, as in 1b.7 D0.3;
a fixture that already carries a `0x1009` stream is the only one allowed to differ, and only in its gap list, never its bytes).

**D7. Where the record lives.** A frozen `rtf_facts` attribute on `MsgContainer` (the `message_facts` / `attachment_facts` pattern),
`None` when there is no `0x1009` stream. Nothing consumes it until 1b.10; it is not added to `EmailDocument`, to `container_facts`
beyond what exists (`body_streams` already lists `rtf`), or to `to_json`. The facts shape for 1b.10 is the result of D3.

## Order of work

1. **Pins** (D6) and the specification constants, typed and cross-checked (D2). If anything in D2 cannot be verified, stop here.
2. `tests/support/rtf_compress.py` (new): a **test-side compressor** written independently of the decoder (a literal-only encoder and
   a greedy-match encoder, both emitting a valid header, CRC and end marker), and the CRC-32 table from the specification. Hand-typed
   vectors: at least one tiny stream assembled **byte by byte in the test with the expected output derived by hand in a comment**
   (literals only; then one reference; then one overlapping reference; then the end marker), so the decoder is not verified only
   against its own sibling.
3. `emailextract/rtf.py` (D3, D4, D5) and `tests/test_msg_rtf.py`'s decoder tests.
4. Fixtures and wiring: `msgcontainer.py` reads `0x1009` through `cfb.read_stream`, calls the decoder, builds `rtf_facts`, maps the
   faults and the gap (D5, D6, D7). Construction tables **typed first** in `tests/support/msg_construction.py`, then
   `tools/make_msg_fixtures.py` and `fixtures/msg/SHA256SUMS`: `msg_rtf_compressed_body` (`0x1000` plus an `LZFu` `0x1009` whose
   decompressed text contains `\fromtext`; the text is **synthetic and typed in the test**), `msg_rtf_only`, `msg_rtf_bad_crc`. A
   `MELA` stream and the other hostile shapes are built **inside the tests** from a fixture by patching bytes, not committed. **No
   `.msg` sidecars.**
5. Extras, full suites, `--check` tools, mutations, the outcome note.

## Tests

The 6 declared tests of the `declaration turn=1b.8` block, **names exactly as declared** (`phase1b-ledgers.md`):
`test_lzfu_decompresses_and_checks_the_header_size_and_crc`, `test_mela_uncompressed_is_accepted`, `test_a_bad_crc_is_a_truncated_stream`,
`test_the_rtf_stream_is_recorded_with_no_body_view`, `test_rtf_to_text_unsupported_is_emitted`,
`test_no_rtf_encapsulation_refused_id_exists`. Plus extras, declared in the same block and added to `tests/test_turn_declarations.py`:
* **Round trip**: `decode(encode(x)) == x` (by sha256 and length) for a committed seeded set of byte strings, including: empty,
  one byte, a run longer than 18 bytes, a text longer than 4096 bytes (dictionary wrap), and random bytes; both encoders.
* **Each fault in D5**, constructed by patching one field or truncating a valid stream, with the exact fault name, `Status` and reason
  asserted, and the gap detail `0x1009:<fault>`.
* **Overlapping reference** and **end-marker position** vectors (hand-typed).
* **The hostile header**: `RAWSIZE = 0xFFFFFFFF` over a tiny body, and `COMPSIZE` far larger than the stream, return a fault quickly
  without a large allocation (assert the peak allocation, `tracemalloc`, is small).
* **Maximal expansion**: the worst-case stream stays within the declared work bound and ~9x output; assert both.
* **Zero-length and short `0x1009`** (0, 1, 15, 16 bytes): present in `body_streams`, `rtf_header_short` for the first three, the
  16-byte header-only `LZFu` stream is `rtf_data_short`, and `msg.rtf_to_text_unsupported` still emitted.
* **`rtf_facts` is plain data** and deterministic under two `PYTHONHASHSEED` values; it carries no RTF text (assert no substring of the
  decompressed text appears in any published record).
* **No body view**: for `msg_rtf_only` and `msg_rtf_compressed_body`, assert no `PartRecord`, `BodyView` or selection derives from the
  RTF and the virtual bytes contain none of its content.
* **Seeded fuzz extension**: operators on the RTF header words and data; at least 150 more mutants over at least two fixtures; every
  mutant yields a document or a named refusal; every published string is UTF-8 encodable; no exception escapes.
* **Memory**: a synthetic 40 MiB compressed RTF stream through `MsgContainer` + `walk` + `assemble`; report the peak working-set delta
  as a multiple of the stream (expected near the cost of reading the stream once; the decoder retains no output). If it is over 3x,
  report which copy dominates.
* **The `.eml` path**: `update_eml_golden.py --check` and the behavior ledger stay green and untouched.

**Mutations** (each must make a named test fail; run, restore, report the failing test names): (1) skip the CRC check (or compute it
over the header as well); (2) treat a reference to an unwritten dictionary byte as zero/space instead of a fault; (3) emit
`msg.rtf_to_text_unsupported` only when the RTF decodes cleanly.

## Allow-list

The ledger's block for `turn=1b.8` (`emailextract/mapi.py`, `emailextract/msgcontainer.py`, `fixtures/msg/`, `tests/test_msg_rtf.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`) **plus these named additions, which you must also write into the
ledger's allow-list line in the same turn**: `emailextract/rtf.py` (new), `tests/support/rtf_compress.py` (new),
`tests/support/msg_construction.py`, `tools/make_msg_fixtures.py`, `tests/test_phase1_scope.py` (`EXPECTED_LIBRARY` and the import
probes; name each line), `tests/test_msg_fixtures.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`, `docs/design/msg-architecture.md` (a short section: the
RTF record and where 1b.10 projects it), `docs/design/phase0-gaps.md` (only if a registry sentence is wrong; list each edit), and any
existing msg test that pins a fixture count or a `body_streams` value (name each). **`behavior_ledger.json` and `versions.py` are
permissions, not duties**: the `msg` ledger components belong to 1b.10; if a `--check` tool demands a change anyway, stop and say so.
**Not**: `emailextract/cfb.py`, `emailextract/walk.py`, `emailextract/attach.py`, `emailextract/model.py`, `emailextract/ingest.py`,
`emailextract/parse.py`, `emailextract/assemble.py`, `emailextract/evals/**`, `tools/cfb_writer.py`, `tests/ledger/corpus.json`, the
`.eml` golden, any `.eml` fixture, `CLAUDE.md`.

## What must NOT be done

No RTF-to-text, no `\fromhtml`/`\fromtext`/`\htmlrtf` interpretation, no RTF code-page reading, no body view, no `BodyView` member,
no `msg.rtf_encapsulation_refused` id, no new gap id or `container_facts` key. No retention of the decompressed output. No guessed fill
byte for an unwritten dictionary position. No change to a record's serialised shape, to the virtual bytes of any existing fixture, or
to `EmailDocument`/`model.py`. No third-party RTF or LZ library (stdlib `zlib` for the CRC only if D2's check permits it). No real or
employer message in any fixture. No `.msg` sidecar. No `olefile` import under `emailextract/`. Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (with `docextract_core` and `olefile` installed); note the
   interpreter and the wall time by chunk.
2. `tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` and `python -m emailextract.evals` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1-D7 and whether you changed any, with evidence; **the specification
   constants you verified and from where** (the prebuf, the initial write position, the reference layout, the CRC definition, whether it
   equals `zlib.crc32`); what a nonzero CRC on a `MELA` stream does; the fault-to-`Status` mapping you applied; the hand-typed vectors
   beside the decoder's output; the maximal-expansion and hostile-header numbers; the memory number; the three fixtures with their
   hand-typed expectations; the three mutation results; every existing test edited and why.
4. What 1b.9 (encodings, the cross-container pair, D14) and 1b.10 (measurers, persistence of `rtf_facts`, the `msg` ledger components,
   the final report and the `0.2.0` release prep) need from this turn.

## Not this turn, but the owner should decide

* **The fault-to-`Status` mapping in D5** (a size or comptype mismatch as `declared_length_mismatch`): a reading, not a measured fact.
* **Whether RTF de-encapsulation ever comes back** (O2 cut it): an HTML-in-RTF body would then become a real body view. Today an
  `\fromhtml` message with no `0x1013` has no body view, and the gap is the only signal.
* **Probe P1/P5 on real mail**: `0x1009` prevalence and whether real RTF-only messages exist is still evidenced by one spike file.

Stop at the turn boundary: `0x1009` is decompressed, checked and recorded, the faults map to the existing gap and statuses, no body
view derives from RTF, the golden is untouched, the outcome note is written. Do not start 1b.9.
