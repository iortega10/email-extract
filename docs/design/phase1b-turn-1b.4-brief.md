# Turn 1b.4: `mapi.py` -- property tables, the string ladder, the class gate, named-property recognition and recipients

Status: brief for one build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `3b1d33a` (Turn 1b.3
committed: `cfb.py`, the hostile set, the seeded fuzz). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session.
**Do not commit.**

**Pace this turn.** While iterating run only the files you are touching (`pytest -q tests/test_mapi.py ...`), not the suite.
Run the full suite once on the primary interpreter when the work is done, then once on 3.11, then the three mutations. Do not
rerun the full suite after every edit. The first full-suite run in 1b.3 was ~140 s; the whole turn should be a fraction of 1b.3's.

## What this turn is

`mapi.py` reads the MAPI layer of a `.msg` **on top of `cfb.py`**: it takes an opened `CfbFile` and returns plain data. It is
a **leaf** like `cfb.py` (stdlib plus `cfb` only; no `model`, `walk`, `parse` or `olefile`), it is **not wired** into `parse()`
or any container (1b.5), and it **never raises**. It decodes the property tables, the strings (the code-page ladder), the class
gate, named-property recognition and the recipient tables. It does **not** build headers, bodies, attachments, time facts or
any `EmailDocument` field; those are 1b.5-1b.9, and `msg.recipients` as a *fact* is 1b.6 (here you only read the rows).

Read first: `phase1b-build-spec.md` (the D13 lines, "Further decisions" items 4, 5 and 10, the 1b.4 row), `phase1b-facts.md`
(`msg.message_class`, `msg.codepage_ladder`, `msg.recipients`), `phase0-gaps.md` (`msg.class_not_ipm_note`,
`msg.property_tag_unknown`, `msg.named_property_unresolved`, `msg.codepage_unresolved_ladder_used`,
`msg.recipient_table_unreadable`: **read each entry's exact text; they are the contract**), `email-spike.md` **B1-B4** (the
measured layout: 32-byte and 8-byte headers, 16-byte entries, the code pages as fixed entries), `phase1b-ledgers.md` (the
`declaration turn=1b.4` block, and the 1b.3 outcome note's "What Turn 1b.4 and 1b.5 need from this turn"), the public
**[MS-OXMSG]** spec (property stream layout; cite section numbers in comments, never copy another library's code), and
`emailextract/cfb.py` (`CfbFile`, `read_stream`, `lookup_entry`, `FAULT_REASON_IDS`; **do not edit it**: a defect you find there
is reported, not fixed).

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. One failure convention: a value is `None` with a named fault, never a guess and never an exception.** A property whose
bytes cannot be decoded returns `value = None`, a `fault` from a **closed tuple** you define and docstring
(at least: the three stream faults carried from `cfb.read_stream` as `stream_cycle` / `stream_out_of_range` /
`stream_short_chain`, `stream_absent`, `utf16_odd_length`, `utf16_lone_surrogate`, `cp1252_undefined_byte`, `entry_truncated`,
`table_size_misfit`), and the **sha256 of the raw bytes** so the original is never lost. No U+FFFD, no `errors="replace"`, no
`surrogatepass`, no latin-1 fallback (the workbook package's 3.2b precedent: a malformed escape is `unknown`, not a repaired
string; the CSV ladder's rule: a byte cp1252 cannot decode is a named fault, never a latin-1 guess). A text value returned by
`mapi.py` must be encodable as UTF-8; a test asserts it for every value of every fixture and every fuzz mutant.

**D2. The string ladder, exactly.** Input: the raw bytes of a `001E` (PT_STRING8) value (including a `001E` body), plus the
two code pages read from the **fixed entries** `0x3FDE` (internet) and `0x3FFD` (message) of the top-level table (never from
streams: B4). Rungs, in order, each recording `encoding_source`:
1. the internet code page, if it **resolves** and decodes the bytes **strictly** -> `internet_cpid`;
2. else the message code page, same test -> `message_cpid`;
3. else all bytes `< 0x80` -> `ascii`;
4. else strict UTF-8 -> `utf8_strict`;
5. else strict windows-1252 -> `windows_1252`; if that fails (bytes `0x81 0x8D 0x8F 0x90 0x9D`) the value is `None` with
   `cp1252_undefined_byte`.
"Resolves" means the code page is in a **small hand-typed table** `CODEPAGES` that you cite: the four observed values
`1252 -> cp1252`, `20127 -> ascii`, `28591 -> iso-8859-1`, `65001 -> utf-8` and nothing else. **Any other number does not
resolve** (it falls through and is recorded; widening the table is a one-line change after a probe, not a guess now). The gap
`msg.codepage_unresolved_ladder_used` is emitted **only when rung 3, 4 or 5 fired** (read the registry text: "neither code
page resolved the bytes"). When rung 1 or 2 fires the gap is **not** emitted, even when the two code pages disagree. Record which
rung and which code pages were declared, so `msg.codepage_ladder`'s `[surface, source_kind, declared_cp, encoding_source]`
row is a pure projection later. `001F` is UTF-16LE with no ladder. **One** trailing U+0000 is stripped and recorded
(`trailing_nul=True`); a second one stays in the text. The raw digest is of the bytes **before** the strip.
*Note for the reviewer's record:* the registry names `msg_codepage_disagree` and the `msg_string8_*` family as the gap's
fixtures, but with the internet code page resolving the bytes the gap would not fire for `msg_codepage_disagree`. Do not bend the
ladder to fit the registry sentence: drive the gap with an in-memory `001E` value that no declared code page resolves (built
in the test), keep `msg_codepage_disagree` as the "internet wins, no gap" case, and **report the discrepancy** in the outcome
note so the registry sentence can be corrected.

**D3. Property tables.** `parse_property_table(data, *, header_size)` over a `__properties_version1.0` stream: header **32 bytes
for the top-level table, 8 for a recipient, attachment or embedded-message table** (B2, 26/26 measured); entries are 16 bytes:
`u32 = (tag << 16) | type`, `u32 flags`, then 8 value bytes. If `(size - header) % 16 != 0` decode every complete entry and
record `table_size_misfit`; never iterate beyond the bytes present (the table's length, not a declared count, bounds the loop).
Fixed types (`PT_I2`, `PT_LONG`, `PT_R4`, `PT_DOUBLE`, `PT_CURRENCY`, `PT_APPTIME`, `PT_ERROR`, `PT_BOOLEAN`, `PT_I8`,
`PT_SYSTIME`) decode from the inline value; `PT_SYSTIME` is kept as the raw `u64` and its 16-digit lowercase hex (lossless;
the UTC rendering is 1b.6's). Variable types (`001E`, `001F`, `0102`) read the stream `__substg1.0_<TAG:04X><TYPE:04X>` in the
same storage through `cfb.read_stream` and carry any stream fault. A storage-backed entry (`000D`) is a `StorageRef` to
`__substg1.0_<TAG><TYPE>` and is **not** read (1b.7). Multi-valued types (`0x1000` flag, e.g. `101F`) follow [MS-OXMSG]'s
multi-value layout (cite the section); **iterate the streams that exist, never a declared count** (a hostile count must not
drive a loop). Tags and types are kept as 4-digit lowercase hex strings next to their integers.

**D4. Known versus unknown tags; no tag is frozen by a document.** `KNOWN_TAGS` is a small table, each row `(tag, name,
expected types, source)` where `source` is `"B3"` (observed in the eleven-file spike) or `"MS-OXPROPS"` (public spec only,
not yet probed). The minimum: `001A` (message class), `0037` (subject), `007D` (transport headers), `1000`, `1009`, `1013`
(bodies), `3FDE`, `3FFD`, and the recipient tags `0C15` (recipient type), `3001` (display name), `3002` (address type), `3003`
(email address), `39FE` (SMTP address). **Everything else is unknown, hex only**: `mapi.py` returns, per table, the sorted tuple of
distinct unknown `tag:type` hex strings (the attachment tags `3701`/`3704`/`3707`/`370E`/`3712` are 1b.7's and are correctly
unknown *today*). Do **not** emit one gap per unknown property: report in the note how many distinct unknown pairs
`msg_outlook_layout_handbuilt` yields (B3 saw 236 across eleven real files, so one record per pair would be noise) and leave the
aggregation into gap records to 1b.5.

**D5. Named properties are recognised, never resolved.** A tag id in `0x8000-0xFFFE` is flagged `named=True` (still decoded
per its own type; the number alone is **not** an identity, B1/B3: 54 of 63 observed named tags changed type across samples).
The presence of `__nameid_version1.0` and the sizes of its three streams are recorded; **its contents are never parsed or used**.
Result: the observation `msg.named_property_unresolved` for the message, listing the named tags in hex.

**D6. The class gate.** Read `0x001A` from the top-level table (`001F`, or `001E` through the ladder) **first**. Verdicts, a
closed tuple: `ipm_note`, `signed_or_encrypted`, `not_ipm_note`, `class_absent`, `class_unreadable`. The match is ASCII
case-insensitive: `ipm_note` is exactly `IPM.Note` or `IPM.Note.` followed by anything **other than** the signed/encrypted
prefixes; `signed_or_encrypted` is a class starting `IPM.Note.SMIME` or `IPM.Note.Secure` (O8: class recorded, body never
opened, never verified); a string that merely *starts with* `IPM.Note` without a dot boundary (`IPM.Notebook`, `IPM.NoteX`) is
**`not_ipm_note`** (this boundary is the reviewer's reading of `IPM.Note*`; say if the owner's corpus shows otherwise).
The class string is returned **verbatim**. For any verdict other than `ipm_note`, `read_message` **stops after the class**: it
does not decode recipients, named properties or the other tags ("nothing past the class is opened"). Map nothing to a `Status`
here: `UNSUPPORTED` versus `PARSED` for the signed case is 1b.5's and the owner's (O8); return the verdict and the observation
`msg.class_not_ipm_note` (for `not_ipm_note` and `signed_or_encrypted`). A message with **no** readable class is `class_absent`,
not an exception and not `ipm_note`.

**D7. Recipients.** The rows are the directory's `__recip_version1.0_#XXXXXXXX` storages (**trust the directory**), ordered by
the hex index; a suffix that is not hex makes that row unreadable. Each row is read with the 8-byte-header table decoder and
returns `kind` (`0C15`: `1 -> to`, `2 -> cc`, `3 -> bcc`, anything else `unknown` with the raw integer kept), `display_name`
(`3001`), `address_type` (`3002`: `SMTP -> smtp`, `EX -> ex`, ASCII case-insensitive, else `unknown`), `address` (`39FE` if
present and non-empty, else `3003`), and its own faults and unknown tags. The top-level header's recipient count (`@16`) is
compared with the number of storages the directory holds: a **mismatch** is recorded and emits `msg.recipient_table_unreadable`
(read the registry text: it covers "a count that disagrees with the real rows"); the rows are still returned from the directory.
`msg.recipients` as a fact is **not** built here.

## What to build

1. `emailextract/mapi.py` (stdlib + `cfb`), with `read_message(cfb) -> MapiMessage` and the building blocks the declaration block
   names (property table, entry decode, ladder, class gate, named-property recognition, recipients). Frozen dataclasses or
   named tuples; **gap ids appear only as string constants** in an `OBSERVATION_IDS` tuple pinned equal to the registered ids
   (find the registry the existing gap tests read; do not add a second list). `EncodingSource` values appear as the strings
   `internet_cpid`, `message_cpid`, `ascii`, `utf8_strict`, `windows_1252`, pinned equal to `model.EncodingSource` by a test (the
   module itself must not import `model`).
2. Fixtures (committed, typed **before** `mapi.py` runs, built by `tools/make_msg_fixtures.py` with the construction tables in
   `tests/support/msg_construction.py`, frozen in `SHA256SUMS`): `msg_unknown_tags`, `msg_named_properties`, `msg_non_ipm_note`
   (`IPM.Appointment`), `msg_signed_class` (`IPM.Note.SMIME.MultipartSigned`), `msg_codepage_disagree` (internet 28591 against
   message 1252). A test-support builder `tests/support/mapi_table.py` writes property-table bytes **from the spec, not from
   `mapi.py`** (reuse the byte layout already typed for `msg_outlook_layout_handbuilt` where it fits). **No `.msg` sidecars**
   (`evals/labels.py` still accepts only `.eml`; 1b.10's file set): expectations are hand-typed in
   `HOSTILE_EXPECTATIONS`-style literals in `msg_construction.py`.
3. The tests of the declaration block (15, names exactly as declared) plus the extras below.

## Tests

`tests/test_mapi.py`: `test_property_tables_use_the_32_and_8_byte_headers`, `test_entry_decode_fixed_variable_and_storage_backed`,
`test_the_class_gate_records_the_class_verbatim` (include `IPM.Notebook`, `IPM.NoteX`, mixed case, `IPM.Note.SMIME`, an empty
class and a missing class), `test_named_properties_are_recognised_not_resolved`, `test_recipients_are_read_from_the_recipient_tables`,
`test_an_unknown_tag_is_hex_only`. `tests/test_mapi_ladder.py`: `test_the_ladder_reads_both_code_pages_as_fixed_entries`,
`test_internet_cpid_wins_over_message_cpid`, `test_the_trailing_nul_is_stripped_and_recorded`,
`test_001e_goes_through_the_ladder_and_001f_is_utf16le`, `test_ascii_and_utf8_rungs_record_their_source`,
`test_multivalued_strings_keep_every_value`. `tests/test_mapi_hostile.py`: `test_a_lone_surrogate_is_recorded_not_raised`,
`test_an_odd_length_utf16_stream_is_recorded_not_raised`, `test_a_recipient_count_mismatch_is_recorded`.

Extras (declare them in the same block, as 1b.3 did): (a) **the independent breaker**: `msg_outlook_layout_handbuilt`, decoded by
`mapi.py`, equals values **typed from B1-B4 before the code ran** (its recipient and attachment counts, the 160/440/3090-byte
`__nameid` streams, `0x3FDE`/`0x3FFD` as fixed entries, the `0102` HTML body present, one recipient);
(b) a **seeded fuzz of the property streams**: `random.Random(seed)` over a committed seed list, at least 300 mutants over at least
three base fixtures, operators on the *properties* and `__substg1.0_*` bytes (flip a tag/type, a flags word, a size field, a
count, truncate a table, mutate a code-page entry, a stream's bytes), every mutant returns a `MapiMessage` whose every value is
either decoded or `None` with a fault **from the closed tuple**, text always UTF-8-encodable, **no exception of any kind
(`MemoryError`/`RecursionError` named)**, failures print the seed and operator; the work done is bounded by the bytes present
(assert a stated step bound, declared in the docstring before the fuzz runs, as 1b.3 did); (c) a **parity test**: `OBSERVATION_IDS`
equals the registered ids, `EncodingSource` strings equal `model.EncodingSource`, `import emailextract.mapi` in a fresh interpreter
loads no `olefile`, `walk`, `model`, `parse`; (d) `msg_non_ipm_note` and `msg_signed_class` prove the gate **stops**: monkeypatch
or count so the recipient and property decoders are never called; (e) determinism under two `PYTHONHASHSEED` values.

**Mutations** (each must make a named test fail; run them, restore, report the failing test names): (1) swap the internet and
message rungs; (2) use the 32-byte header for a recipient table (or 8 for the top-level); (3) match the class with a bare
`startswith("IPM.Note")`.

## Allow-list

The ledger's block for `turn=1b.4` (`emailextract/mapi.py`, `emailextract/versions.py`, `fixtures/msg/`, `tests/test_mapi.py`,
`tests/test_mapi_ladder.py`, `tests/test_mapi_hostile.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`)
**plus these named additions, which you must also write into the ledger's allow-list line in the same turn**:
`tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`, `tests/support/mapi_table.py` (new),
`tests/test_msg_fixtures.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`tests/test_phase1_scope.py` (`EXPECTED_LIBRARY` and the import-ban list only; name each line you change, as 1b.3 did),
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`. **`versions.py` is on the list but the default is
do not touch it**: the three `msg` ledger components and their constants belong to a later turn (the ledgers document says which);
if a pinned test forces a constant, it must not move any `.eml` value. **Not**: `emailextract/cfb.py`, `tools/cfb_writer.py`,
`walk.py`, `model.py`, `parse.py`, `container.py`, `assemble.py`, `emailextract/evals/**`, `tests/ledger/corpus.json`,
`tests/ledger/behavior_ledger.json`, the golden, any existing fixture, `CLAUDE.md`.

## What must NOT be done

No `msgcontainer.py`, no wiring into `parse()`/`ingest`/`walk`, no headers, bodies, attachments, time facts or `Status`. No
resolution of a named property, ever. No `chardet`, `charset-normalizer`, `olefile` or GPL code in `emailextract/`. No exception
from `mapi.py` on any input; no loop bounded by a declared count; no replacement character, `errors="replace"`, `surrogatepass`
or latin-1 fallback. No real or employer message in any fixture; no `.msg` sidecar. No change to a measured `.eml` value: the
golden, the behavior ledger and every Phase 1 gate stay green and untouched. Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (with `docextract_core` and `olefile` installed). Note the
   interpreter hearth actually used.
2. `python tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1-D7 and whether you changed any, with evidence; the
   registry-sentence discrepancy of D2; the distinct-unknown-pair count of D4; the ladder table for every fixture and every
   in-memory ladder case; the three mutation results (failing test names); every disagreement between `mapi.py`, the typed tables
   and the hand-built layout fixture and how it resolved; the exact set of existing tests edited and why.
4. What 1b.5 needs: `mapi.py`'s public API, how an observation becomes a gap record, how a `None` value becomes `unknown` text
   in a document, and the open question of aggregating unknown tags.

## Not this turn, but the owner should decide before 1b.5

* **The `IPM.Note*` boundary** (D6) and **what a signed message's `Status` is** (O8: `UNSUPPORTED` versus `PARSED`; the
  fixtures table leaves it open).
* **A missing class** (`class_absent`) is returned, not decided: 1b.5 chooses whether it is `not_a_message`, a gap or a document.
* **Widening `CODEPAGES`** (D2) once the owner's probe P4 reports which other code pages their real mail declares.

Stop at the turn boundary: the ladder, the class gate and the recipients are green, the mutations fail as named and the outcome
note is written. Do not start 1b.5.
