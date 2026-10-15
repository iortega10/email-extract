# Phase 1b ledgers, allow-lists, declarations and the `.eml` golden (Turn 1b.0a specification; built in Turns 1b.0b to 1b.10)

The four Phase 1 mechanisms keep their shape for Phase 1b; this document fixes only what is new:
the **label-ledger additions**, the **pinned `FACTS` ledger additions**, three new **behavior-ledger
components** (`cfb`, `msg_reader`, `msg_projection`), the **`.eml` golden** (captured in Turn 1b.0c), the
per-turn **allow-lists** and the per-turn **declarations** (Turns 1b.0b to 1b.10). Form and mechanism follow
`docs/design/phase1-ledgers.md` and `docs/design/phase1-turn-declarations.md`; where they say "Phase 1", read
"Phase 1b".

The **thirteen turns** are the spec's table (`phase1b-build-spec.md:292-306`): 1b.0a (this turn, documents
only), 1b.0b (spike, no package code), 1b.0c (the golden), 1b.1 (the bump and the eight provenance points),
1b.2 (writer + first fixtures), 1b.3 (`cfb.py`), 1b.4 (`mapi.py`), 1b.5 (`msgcontainer.py`), 1b.6 (message-level
facts), 1b.7 (attachments), 1b.8 (RTF minimum), 1b.9 (cross-container pair, Outlook layout, encodings),
1b.10 (gates, scope, ledger components, report, release). Each turn is owner-committed before the next; no turn
commits itself. Test ceilings are **guidelines, not measurements**.

## (a) The label ledger — additions

`tests/ledger/label_ledger.json` (append-only) covers three path sets; Phase 1b appends to each:

- **Sidecars** (the label corpus): `fixtures/msg/**/*.expected.json` -- one per Family D-I fixture
  (`docs/design/phase1b-fixtures.md`). Added by Turns 1b.2 to 1b.9 in the same commit as the fixture.
- **Support checkers** (`tests/support/**`): `tests/support/olefile_oracle.py` (the tests-only comparator, Turn
  1b.2) and `tests/support/fake_msg_container.py` (the hand-made virtual bytes and hand-written span table, Turn
  1b.1). Added in their turns.
- **Oracle** (`emailextract/evals/**`): the Phase 1b edits to `gates.py`, `l1.py`, `falsify.py` (Turn 1b.10)
  change recorded files' bytes, so each is re-recorded **in the same commit** and named in that turn's
  allow-list (the additions-only rule refuses an in-place edit otherwise).

No committed `.eml` sidecar or Phase 1 support file changes; the `.msg` additions are new files only.

## (b) The pinned `FACTS` ledger — additions

`tests/ledger/facts_ledger.json`'s `phase1` list gains the **11 new fact ids** of
`docs/design/phase1b-facts.md`; `deferred` stays `[]`. `tests/test_facts_ledger.py` compares `l1.FACT_PHASES`
against it, so a Phase 1b fact added without listing it here fails, and moving a Phase 1b fact's phase to dodge
a floor fails. `tests/test_facts_coverage.py` gains the 11 floors. The consequences are enumerated in
`phase1b-facts.md` ("Consequences for `tests/ledger/facts_ledger.json`").

## (c) The behavior ledger — three new components

`tools/behavior_ledger.py`'s `COMPONENTS` (C `:78`) and `VERSION_CONSTANTS` (C `:81-84`) gain three components;
each is keyed `"<version string>|corpus:<N>"` exactly as `walk`/`decode_chain`, with `contracts` unchanged
(keyed by `OUTPUT_SCHEMA_VERSION` alone). The corpus for the three is the committed `.msg` fixtures (a new corpus
version; adding a fixture adds a corpus version and bumps no component version).

| component | version constant | what it fingerprints | over which corpus |
|---|---|---|---|
| `cfb` | `CFB_VERSION` = `"1"` | the CFB primitives' output: the parsed header (version, sector size, mini cutoff, DIFAT/FAT counts), the directory shape (storage/stream names and sizes), each stream's size and bytes, and the eight-class sector classification | every committed well-formed `.msg` fixture (hostile mutants excluded from the fingerprint; they are covered by the fuzz and the fault classification) |
| `msg_reader` | `MSG_READER_VERSION` = `"1"` | the MAPI layer: property tables decoded, `001E`/`001F`/multi-valued values, the string ladder's chosen code page and `encoding_source`, the class gate, the recipient rows, the attachment rows | every committed `.msg` fixture |
| `msg_projection` | `MSG_PROJECTION_VERSION` = `"1"` | the virtual framing: the virtual RFC 822 byte string's sha256, the span table rows (source offsets, axes), the headers' UTF-8 re-encoding, and the `part_id`s | every committed `.msg` fixture |

`EMAIL_PARSER_VERSION` moves **only** if a measured `.eml` value moves (rule 2; it must not).
`OUTPUT_SCHEMA_VERSION` moves once, `"5"` -> `"6"` (Turn 1b.1).

## (d) The `.eml` golden

- **File:** `tests/golden/eml_golden.json` (committed; captured in **Turn 1b.0c**, before the first
  frozen-module edit).
- **Exactly what it pins:** the serialized `EmailDocument`, the `WalkResult`, `resolve_span` samples (the C2
  identity guard), the `CapRecord`s, the two store artifacts (walk and document) with their keys, and the
  `ParseResult`, over the committed `.eml` corpus.
- **Format:** one JSON object per pinned fixture, with a header naming the corpus version and the schema version
  it was captured at. It is a committed file the test **never regenerates silently**; recording is the explicit
  `tools/update_eml_golden.py` run in the same commit as the change that moved it (Turn 1b.0c creates it at
  schema `"5"`; Turn 1b.1 re-records it at `"6"`, and
  `tests/test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys` asserts the diff is exactly
  the one `phase1b-contract.md` section 10 lists: the walk artifact's `WalkResult` byte-identical; the document
  artifact moved by only the `output_schema_version` value, one `"stream_ref": null` per
  `PartRecord`/`HeaderField` and (D2, Turn 1b.1) one `"embedded": null` per `AttachmentOccurrence`; the store
  keys/paths that name `OUTPUT_SCHEMA_VERSION` moved by that version string; every other pinned value
  byte-identical).
- **Both interpreters:** checked on 3.14 and 3.11 with a **recorded waiver** (a named field that legitimately
  differs, never a silent skip). The waiver is recorded in the golden file's header.
- **It is partial, not redundant, against the behavior ledger:** the ledger's `walk` fingerprint pins the
  `WalkResult` but not the assembled `EmailDocument`; the golden pins the assembled document too.

## (e) The per-turn allow-lists

Every turn prompt carries one fenced allow-list block; nothing else is meant to be touched. Paths are
repo-root-relative, posix; a trailing `/` names a subtree. From Turn 1b.2 onward the allow-list **excludes
`fixtures/**` and `*.expected.json`** except in the fixture turns (1b.2, 1b.3, 1b.7, 1b.9), which run before the
rules that read them. A gate or oracle edit (`emailextract/evals/**`, `tests/support/**`) needs its path named
explicitly.

The allow-lists are given with each declaration block below.

## (f) The declarations (Turns 1b.0b to 1b.10)

Machine-readable, one fenced block per turn: one `module:` line per module created or changed, one `test:`
line per new test function (full `pytest` node id `path::function`), a `stop:` line, and the turn's allow-list.
The collection test — `tests/test_turn_declarations.py`, **extended in Turn 1b.10 to read this file's blocks**
alongside the Phase 1 file — asserts both directions: every declared test is collected, and every collected test
not in the frozen Phase 0 baseline is declared. The Phase 1b blocks are a **first declaration**; each turn's
prompt may refine them (split a module, rename a test) as long as the refinement is declared and the collection
test passes.

```declaration turn=1b.0b
module: docs/design/msg-architecture.md
module: tools/msg_probe.py
stop: after the eight experiments (E1-E8) are recorded in msg-architecture.md and the owner ratifies A''
```

**Turn 1b.0b measures nothing** (no package code, no tests; test ceiling 0; the experiments run on hand-built
bytes outside the repo). Allow-list (`turn=1b.0b`): `docs/design/msg-architecture.md`, `tools/msg_probe.py`,
`docs/design/phase1b-ledgers.md`. **Not** `emailextract/**`, `tests/**`, `fixtures/**`.

**Outcome of Turn 1b.0b** (recorded in `docs/design/msg-architecture.md`). The eight experiments and the
comparison ran on hand-built CFB bytes in the scratch directory; **A'' is ratified structurally** -- the
comparison of `walk(msg-virtual)` against `walk(EmlContainer(equivalent .eml))` differs in **zero** structural
fields, so no edit to tiling or ordering inside `_walk_visit` is forced. E5/E6/E7 show the provenance points are
keyword/default additions that leave the `.eml` path byte-identical (the `.eml` ids, 88/88 committed header
fields, and the `.eml` store artifact all unchanged); E1/E2/E3 confirm the own reader's contract is total,
bounded and account-clean. **One constraint fails as specified: E4's memory budget** -- a `bytes`-valued
`raw_bytes()` costs ~4x a 40 MiB pass-through attachment (167.8 MB, over the declared 3x), so build spec section
7's "unless E4 shows it is needed" clause fires and a **lazy `raw_bytes()`** (`container.py`) is needed for Turn
1b.1 -- a bounded protocol change, not a `_walk_visit` structural edit. `tools/msg_probe.py` (P1-P6) is built and
in the repo; its sentinel test, instrumented reads and expected-output check are recorded in the same document.
Per the turn's rule the build **stops here**: E4's failure is written up, no Turn 1b.0c and no package code is
started.

```declaration turn=1b.0c
module: tests/golden/eml_golden.json
module: tools/update_eml_golden.py
module: tests/test_eml_golden.py
test: tests/test_eml_golden.py::test_the_golden_matches_the_committed_corpus
test: tests/test_eml_golden.py::test_the_golden_pins_the_document_walk_spans_caps_and_store_bytes
test: tests/test_eml_golden.py::test_the_golden_is_not_regenerated_silently
test: tests/test_eml_golden.py::test_the_golden_checks_both_interpreters_with_a_recorded_waiver
test: tests/test_eml_golden.py::test_a_changed_measured_value_fails_the_golden
test: tests/test_eml_golden.py::test_a_changed_schema_version_alone_is_the_permitted_move
test: tests/test_eml_golden.py::test_the_golden_covers_every_committed_eml_fixture
test: tests/test_eml_golden.py::test_the_golden_header_names_the_corpus_and_schema_version
test: tests/test_eml_golden.py::test_resolve_span_samples_are_the_identity_guard
test: tests/test_eml_golden.py::test_the_golden_file_is_listed_in_the_label_ledger
stop: after the golden is captured and committed, before any frozen-module edit (rule 2)
```

Allow-list (`turn=1b.0c`): `tests/golden/`, `tools/update_eml_golden.py`, `tests/test_eml_golden.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`. **Not** `emailextract/**`.

**Outcome of Turn 1b.0c.** `tests/golden/eml_golden.json` is captured on `c6728c0` plus the uncommitted
Turn 1b.0b files: **4,820,988 bytes**, sha256
`ae7e7aa140249c1fe2b9defc442848b2bb91f1b20112c2e0f91e521ae2ac00ca`, **126 fixtures** at corpus version
**8** and schema **`"5"`**, header `recorded_on` CPython 3.14.3. Recording is the explicit
`tools/update_eml_golden.py` (enumerating the corpus through `behavior_ledger`, writing canonical JSON in
binary mode); running it twice leaves `git status` byte-unchanged, and it is byte-identical under
`PYTHONHASHSEED=0` and `12345` on both interpreters. `tools/update_eml_golden.py --check`,
`tools/update_behavior_ledger.py --check` and `tools/update_label_ledger.py --check` all exit 0; the full
suite is green on CPython 3.14.3 and 3.11.15 (2014 passed, 2 skipped each). All ten declared tests are
present; the four cases of `test_a_changed_measured_value_fails_the_golden` were each run and each failed
the comparison: a `part_id` (`address_group.eml` part 0, `68009ece…` -> `1ebb3044…`), a `sha256`
(`7f6709b5…` -> `cbcd9a77…`), a `span_samples` offset (`262` -> `263`) and a `CapRecord`
(`cap_value_bytes` `4096` -> `4097`).

**The waiver is not the spec's "one recorded-heading field".** The two interpreters differ in four
fixture-key paths -- `document/record/run_record/projection_versions/HTMLTEXT_VERSION`,
`store/document/{key,path,bytes_hex}` -- plus `header/recorded_on`. All five are the one recorded-only
input (decision 1: `HTMLTEXT_VERSION` stamps the CPython minor) or a value derived from it; the recorded
stamp reaches the document artifact's **key** (every projection version is in `assemble.document_key`), its
**store path** and its **bytes**. Nothing a measured value carries (a `part_id`, a `sha256`, a span, a cap)
differs, and on the recording interpreter **no** path is waived: the committed file is reproduced byte for
byte, and the walk artifact -- which carries no recorded-only stamp -- is byte-identical unwaived. Because
the `bytes_hex` waiver is coarse, `test_the_golden_checks_both_interpreters_with_a_recorded_waiver` decodes
both artifacts and asserts their JSON differs only in that stamp and the key that names it. The spec's
"the waiver names the field" understates the reach.

**The declared `Limits` is not `untrusted()` verbatim.** Under `Limits.untrusted()` **no** committed fixture
hits a cap, so the `caps` pin would be empty for all 126 and could not fail -- a decorative pin. The
declared set is `Limits.untrusted()` with `max_header_bytes=4096`, the smallest measured header cap that
fires on the corpus's own `cap_enormous_header_block`; exactly one fixture caps
(`header_bytes_cap`, value 4096, declared 6087), and every other fixture's parts, headers and caps are
byte-identical to the untrusted run.

**Two allow-list gaps had to be closed, both outside the brief's list.** (1) The label ledger has no
covered set for `tests/golden/`, so `tools/update_label_ledger.py`'s `covered_files` gains that directory
(a fourth set; the tool is not in the allow-list) -- without it, recording the golden in
`tests/ledger/label_ledger.json` would make it "recorded but not present" and fail
`tests/test_label_ledger.py`. (2) `tests/test_turn_declarations.py` reads only
`docs/design/phase1-turn-declarations.md` until its Turn 1b.10 extension, so the ten new tests would be
"collected tests nobody declared"; the Turn 1b.0c block is **mirrored** into that file (verbatim, so
Turn 1b.10 reading both files sees one block per turn and may drop the mirror).

**Two smaller findings.** No committed fixture is *both* multi-part and folded-header, so the identity
guard test checks the three properties (a multi-part message, a folded header, a nonzero resolved offset)
across the corpus rather than in one fixture. And `resolve_span` addresses a part's **view code points**,
not a header span: a header field's own span is pinned directly in `span_samples`, with an explicit
`null` answer and the reason, per the turn's "a pin that does not apply is an explicit `null`" rule.

```declaration turn=1b.1
module: emailextract/model.py
module: emailextract/versions.py
module: emailextract/ids.py
module: emailextract/walk.py
module: emailextract/text.py
module: emailextract/assemble.py
module: emailextract/parse.py
module: emailextract/store.py
module: emailextract/container.py
module: emailextract/__init__.py
module: tests/support/fake_msg_container.py
module: tests/golden/eml_golden.json
module: tests/test_contract_msg.py
module: tests/test_provenance_points.py
test: tests/test_contract_msg.py::test_container_stream_ref_shape_and_round_trip
test: tests/test_contract_msg.py::test_container_stream_ref_invariants_raise
test: tests/test_contract_msg.py::test_a_synthetic_ref_carries_no_offsets
test: tests/test_contract_msg.py::test_embedded_summary_shape_and_defaults
test: tests/test_contract_msg.py::test_the_cfb_cap_reasons_join_the_skipped_row
test: tests/test_contract_msg.py::test_named_error_reasons_gain_the_two_cfb_faults
test: tests/test_contract_msg.py::test_verbatim_reasons_gain_container_stream
test: tests/test_contract_msg.py::test_output_schema_version_is_six
test: tests/test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys
test: tests/test_provenance_points.py::test_the_assembler_fills_stream_ref_from_the_span_table
test: tests/test_provenance_points.py::test_part_id_is_kind_gated_and_framing_length_independent
test: tests/test_provenance_points.py::test_two_framing_lengths_give_identical_part_ids
test: tests/test_provenance_points.py::test_the_eml_part_ids_are_byte_identical
test: tests/test_provenance_points.py::test_resolve_span_returns_a_stream_ref_for_a_span_table_container
test: tests/test_provenance_points.py::test_resolve_span_still_refuses_a_virtual_offset
test: tests/test_provenance_points.py::test_analyse_part_forces_container_stream_part_level
test: tests/test_provenance_points.py::test_encoding_source_is_overwritten_from_the_ladder_map
test: tests/test_provenance_points.py::test_cap_declared_size_copies_the_real_stream_size
test: tests/test_provenance_points.py::test_the_store_persists_sectors_and_the_source_only_span_table
test: tests/test_provenance_points.py::test_the_source_only_span_table_recomputes_the_virtual_offsets
test: tests/test_provenance_points.py::test_adding_a_cfb_msg_document_changes_no_eml_store_byte
test: tests/test_provenance_points.py::test_parse_opens_a_cfb_container_instead_of_refusing
test: tests/test_provenance_points.py::test_the_eml_default_branch_is_unchanged
test: tests/test_provenance_points.py::test_the_value_codec_seam_defaults_to_latin_1
test: tests/test_provenance_points.py::test_walk_msg_matches_walk_of_the_equivalent_eml_modulo_provenance
test: tests/test_provenance_points.py::test_limits_fingerprint_is_unchanged_by_the_bump
stop: after the golden re-check (the bump and the eight provenance points green against FakeMsgContainer)
```

Allow-list (`turn=1b.1`): the eight `emailextract/` modules above plus `emailextract/container.py`, `emailextract/__init__.py`,
`tests/support/fake_msg_container.py`,
`tests/golden/eml_golden.json`, `tests/test_contract_msg.py`, `tests/test_provenance_points.py`,
`tests/test_eml_golden.py`, `tests/test_status_reasons.py`, `tests/test_contract_phase1.py`,
`tests/test_parse_entry.py`, `tests/test_contracts.py`, `tests/test_closed_enums.py`, `tests/test_container.py`,
`tests/test_assemble.py`, `tests/test_store.py`, `tests/test_ingest.py`, `tests/test_phase1_scope.py`,
`tests/test_limits.py`, `tests/test_walk_iterative.py`, `tests/test_stdlib_header_scanner.py`,
`tests/test_turn_declarations.py`, `tests/ledger/behavior_ledger.json`, `tests/ledger/label_ledger.json`,
`docs/design/phase1b-ledgers.md`, `docs/design/phase1-turn-declarations.md`. Those test paths are the
category-(1)/(2)/(3) edits of `phase1b-contract.md` section 11 plus the four extra breakages the bump forced
(`test_limits.py` per D1, the two gate wrappers `_walk_visit`/`header_fields_at`, and the declaration
baseline `test_turn_declarations.py`).

```declaration turn=1b.2
module: tools/cfb_writer.py
module: tools/make_msg_fixtures.py
module: tests/support/msg_construction.py
module: tests/support/cfb_raw.py
module: tests/support/olefile_oracle.py
module: tests/test_msg_fixtures.py
module: tests/test_olefile_oracle.py
test: tests/test_msg_fixtures.py::test_the_writer_output_is_frozen_by_sha256
test: tests/test_msg_fixtures.py::test_the_writer_rebuilds_the_same_bytes_under_any_hash_seed
test: tests/test_msg_fixtures.py::test_no_real_message_enters_the_repository
test: tests/test_msg_fixtures.py::test_every_fixture_matches_its_construction_table
test: tests/test_msg_fixtures.py::test_the_v4_file_uses_4096_byte_sectors
test: tests/test_msg_fixtures.py::test_the_mini_cutoff_trio_is_4095_4096_4097
test: tests/test_msg_fixtures.py::test_the_outlook_layout_fixture_is_typed_from_b1_b4
test: tests/test_msg_fixtures.py::test_the_writer_imports_no_reader_and_no_olefile
test: tests/test_olefile_oracle.py::test_olefile_agrees_on_every_well_formed_fixture
test: tests/test_olefile_oracle.py::test_the_oracle_scope_excludes_hostile_mutants
test: tests/test_olefile_oracle.py::test_the_oracle_records_where_it_is_lenient
stop: after the writer output is frozen and the oracle test is green
```

Allow-list (`turn=1b.2`): `tools/cfb_writer.py`, `tools/make_msg_fixtures.py`, `fixtures/msg/`,
`tests/support/olefile_oracle.py`, `tests/support/msg_construction.py`, `tests/support/cfb_raw.py`,
`tests/test_msg_fixtures.py`, `tests/test_olefile_oracle.py`, `tests/test_licence_audit.py`,
`tests/test_container.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`tests/ledger/label_ledger.json`, `pyproject.toml`, `NOTICE`,
`docs/design/phase1b-fixtures.md`, `docs/design/phase1b-ledgers.md`, `docs/design/phase1-turn-declarations.md`.

```declaration turn=1b.3
module: emailextract/cfb.py
module: tools/make_msg_fixtures.py
module: tests/support/msg_construction.py
module: tests/support/cfb_raw.py
module: tests/support/olefile_oracle.py
module: tests/test_cfb.py
module: tests/test_cfb_hostile.py
module: tests/test_cfb_fuzz.py
module: tests/test_sector_accounting.py
test: tests/test_cfb.py::test_parse_header_reads_v3_and_v4
test: tests/test_cfb.py::test_walk_difat_and_read_fat
test: tests/test_cfb.py::test_read_minifat_and_the_cutoff
test: tests/test_cfb.py::test_walk_directory_and_case_insensitive_lookup
test: tests/test_cfb.py::test_read_stream_returns_bytes_and_fault
test: tests/test_cfb.py::test_read_stream_never_raises
test: tests/test_cfb.py::test_classify_sectors_assigns_every_sector
test: tests/test_cfb.py::test_check_caps_reports_the_three_cfb_caps
test: tests/test_cfb.py::test_the_cfb_reader_and_olefile_agree_on_every_well_formed_fixture
test: tests/test_cfb.py::test_the_cfb_vocabulary_matches_the_walk_and_parse_contract
test: tests/test_cfb_hostile.py::test_a_fat_cycle_is_one_streams_fault
test: tests/test_cfb_hostile.py::test_a_directory_loop_is_a_named_error
test: tests/test_cfb_hostile.py::test_an_unsupported_header_is_a_named_error
test: tests/test_cfb_hostile.py::test_magic_without_properties_is_not_a_message
test: tests/test_cfb_hostile.py::test_the_extended_difat_is_read_through_and_flagged
test: tests/test_cfb_fuzz.py::test_every_mutant_returns_a_closed_failure_or_the_same_document
test: tests/test_cfb_fuzz.py::test_the_work_per_byte_budget_holds
test: tests/test_cfb_fuzz.py::test_the_numbers_are_stable_across_hash_seeds
test: tests/test_sector_accounting.py::test_the_eight_classes_sum_to_the_file_length
test: tests/test_sector_accounting.py::test_free_and_slack_are_explicit
test: tests/test_sector_accounting.py::test_a_cyclic_chain_is_visible_as_unaccounted
stop: after the hostile set and the seeded fuzz, before MAPI
```

Allow-list (`turn=1b.3`): the block's list -- `emailextract/cfb.py`, `emailextract/versions.py`,
`fixtures/msg/`, `tests/test_cfb.py`, `tests/test_cfb_hostile.py`, `tests/test_cfb_fuzz.py`,
`tests/test_sector_accounting.py`, `tests/support/olefile_oracle.py`, `tests/ledger/label_ledger.json`,
`docs/design/phase1b-ledgers.md` -- **plus** the brief's named additions, written here in the same turn:
`tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`, `tests/support/cfb_raw.py`,
`tests/test_msg_fixtures.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`.

```declaration turn=1b.4
module: emailextract/mapi.py
module: tools/make_msg_fixtures.py
module: tests/support/msg_construction.py
module: tests/support/mapi_table.py
module: tests/test_mapi.py
module: tests/test_mapi_ladder.py
module: tests/test_mapi_hostile.py
test: tests/test_mapi.py::test_property_tables_use_the_32_and_8_byte_headers
test: tests/test_mapi.py::test_entry_decode_fixed_variable_and_storage_backed
test: tests/test_mapi.py::test_the_class_gate_records_the_class_verbatim
test: tests/test_mapi.py::test_named_properties_are_recognised_not_resolved
test: tests/test_mapi.py::test_recipients_are_read_from_the_recipient_tables
test: tests/test_mapi.py::test_an_unknown_tag_is_hex_only
test: tests/test_mapi.py::test_the_class_gate_stops_before_recipients_and_properties
test: tests/test_mapi.py::test_the_handbuilt_outlook_layout_matches_the_b1_b4_values
test: tests/test_mapi_ladder.py::test_the_ladder_reads_both_code_pages_as_fixed_entries
test: tests/test_mapi_ladder.py::test_internet_cpid_wins_over_message_cpid
test: tests/test_mapi_ladder.py::test_the_trailing_nul_is_stripped_and_recorded
test: tests/test_mapi_ladder.py::test_001e_goes_through_the_ladder_and_001f_is_utf16le
test: tests/test_mapi_ladder.py::test_ascii_and_utf8_rungs_record_their_source
test: tests/test_mapi_ladder.py::test_multivalued_strings_keep_every_value
test: tests/test_mapi_hostile.py::test_a_lone_surrogate_is_recorded_not_raised
test: tests/test_mapi_hostile.py::test_an_odd_length_utf16_stream_is_recorded_not_raised
test: tests/test_mapi_hostile.py::test_a_recipient_count_mismatch_is_recorded
test: tests/test_mapi_hostile.py::test_every_property_mutant_returns_a_closed_message
test: tests/test_mapi_hostile.py::test_the_mapi_work_bound_holds
test: tests/test_mapi_hostile.py::test_the_mutant_numbers_are_stable_across_hash_seeds
test: tests/test_mapi_hostile.py::test_the_mapi_vocabulary_matches_the_registry_model_and_imports
stop: after the ladder, the class gate and the recipients, before the container
```

Allow-list (`turn=1b.4`): the block's list -- `emailextract/mapi.py`, `emailextract/versions.py`,
`fixtures/msg/`, `tests/test_mapi.py`, `tests/test_mapi_ladder.py`, `tests/test_mapi_hostile.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md` -- **plus** the brief's named
additions, written here in the same turn: `tools/make_msg_fixtures.py`,
`tests/support/msg_construction.py`, `tests/support/mapi_table.py` (new), `tests/test_msg_fixtures.py`,
`tests/test_fixture_census.py`, `tests/test_turn_declarations.py`, `tests/test_phase1_scope.py`
(one changed line: `EXPECTED_LIBRARY` gains `"mapi.py"`; the import-ban list is unchanged, because
`mapi.py` reaches its sibling as `from . import cfb`, which names no banned import root),
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`.

```declaration turn=1b.5
module: emailextract/msgcontainer.py
module: emailextract/attach.py
module: emailextract/parse.py
module: tests/test_msgcontainer.py
module: tests/test_msg_headers.py
module: tests/test_msg_body.py
test: tests/test_msgcontainer.py::test_the_virtual_bytes_and_the_span_table_agree
test: tests/test_msgcontainer.py::test_the_container_publishes_no_virtual_offset_to_a_record
test: tests/test_msgcontainer.py::test_container_hash_addresses_the_cfb_file
test: tests/test_msgcontainer.py::test_container_facts_carry_the_fixed_key_list
test: tests/test_msgcontainer.py::test_the_span_table_row_shape_is_the_contract
test: tests/test_msg_headers.py::test_headers_come_from_the_007d_stream_in_order
test: tests/test_msg_headers.py::test_the_utf8_codec_carries_the_real_header_text
test: tests/test_msg_headers.py::test_no_transport_headers_yields_no_synthesized_headers
test: tests/test_msg_headers.py::test_the_transport_header_is_canonical_and_the_property_is_kept
test: tests/test_msg_body.py::test_a_pass_through_html_leaf_is_never_exact
test: tests/test_msg_body.py::test_a_plain_leaf_is_reencoded_and_container_stream
test: tests/test_msg_body.py::test_selection_picks_html_over_plain
test: tests/test_msg_body.py::test_sector_accounting_sums_to_the_file_length_end_to_end
stop: after headers and one HTML body end to end, with the golden still green
```

Allow-list (`turn=1b.5`): `emailextract/msgcontainer.py`, `emailextract/parse.py`, `emailextract/assemble.py`,
`emailextract/walk.py`, `fixtures/msg/`, `tests/test_msgcontainer.py`, `tests/test_msg_headers.py`,
`tests/test_msg_body.py`, `tests/ledger/label_ledger.json`, `tests/ledger/behavior_ledger.json`,
`docs/design/phase1b-ledgers.md`.

```declaration turn=1b.6
module: tests/test_msg_message_facts.py
module: tests/test_msg_recipients.py
module: tests/test_msg_time.py
test: tests/test_msg_message_facts.py::test_subject_sender_and_class_are_mapi_properties
test: tests/test_msg_message_facts.py::test_the_property_versus_header_conflict_pair_is_recorded
test: tests/test_msg_message_facts.py::test_message_class_is_recorded_verbatim
test: tests/test_msg_recipients.py::test_recipients_are_facts_beside_the_headers
test: tests/test_msg_recipients.py::test_display_only_and_ex_recipients_are_recorded
test: tests/test_msg_time.py::test_time_properties_are_flat_hex_keys
test: tests/test_msg_time.py::test_the_filetime_hex_is_lossless_and_canonical
test: tests/test_msg_time.py::test_no_timeevent_is_emitted
test: tests/test_msg_message_facts.py::test_the_class_gate_leaves_no_message_facts
test: tests/test_msg_message_facts.py::test_the_observation_gaps_are_mapped_once_each
test: tests/test_msg_message_facts.py::test_the_facts_are_deterministic_across_hash_seeds
test: tests/test_msg_message_facts.py::test_a_seeded_fuzz_of_the_message_facts_closes
test: tests/test_msg_recipients.py::test_the_recipient_records_match_the_olefile_oracle
test: tests/test_msg_recipients.py::test_recipient_count_is_the_directory_count_not_the_declared_count
test: tests/test_msg_recipients.py::test_a_faulted_recipient_row_is_the_recipient_table_unreadable_gap
test: tests/test_msg_time.py::test_the_filetime_rendering_truncates_the_sub_second_part
test: tests/test_msg_time.py::test_the_filetime_epoch_renders_with_no_sentinel
test: tests/test_msg_time.py::test_a_filetime_beyond_the_year_range_is_unrepresentable
test: tests/test_msg_time.py::test_the_date_header_is_kept_distinct_from_the_time_properties
stop: after the message-level facts and the time facts
```

Allow-list (`turn=1b.6`): `emailextract/msgcontainer.py`, `emailextract/assemble.py`,
`tests/test_msg_message_facts.py`, `tests/test_msg_recipients.py`, `tests/test_msg_time.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md` -- **plus** the brief's named
additions, written here in the same turn: `emailextract/mapi.py` (the D2 `KNOWN_TAGS` rows only),
`fixtures/msg/`, `tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`,
`tests/support/mapi_table.py`, `tests/support/olefile_oracle.py`, `tests/test_msg_fixtures.py`,
`tests/test_mapi.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`,
`docs/design/msg-architecture.md`, `docs/design/phase0-gaps.md`.

```declaration turn=1b.7
module: emailextract/mapi.py
module: emailextract/msgcontainer.py
module: tests/test_msg_attachments.py
module: tests/test_msg_embedded.py
test: tests/test_msg_attachments.py::test_a_by_value_attachment_is_read
test: tests/test_msg_attachments.py::test_the_filename_ladder_is_long_over_short_over_display
test: tests/test_msg_attachments.py::test_a_hostile_filename_is_never_a_path
test: tests/test_msg_attachments.py::test_cid_and_hidden_flags_feed_the_attach_stage
test: tests/test_msg_attachments.py::test_reference_methods_are_recorded_and_dropped_unsupported
test: tests/test_msg_attachments.py::test_zero_size_and_the_mini_cutoff_trio
test: tests/test_msg_embedded.py::test_an_embedded_message_carries_an_embedded_summary
test: tests/test_msg_embedded.py::test_the_storage_tree_sha256_is_a_canonical_walk
test: tests/test_msg_embedded.py::test_beyond_depth_one_is_the_depth_cap
test: tests/test_msgcontainer.py::test_a_body_or_transport_stream_fault_is_the_registered_truncated_gap
test: tests/test_msg_attachments.py::test_a_message_without_attachments_projects_as_before
test: tests/test_msg_attachments.py::test_two_framing_lengths_give_identical_part_ids_and_records_with_an_attachment
test: tests/test_msg_attachments.py::test_the_cross_container_pair_differs_only_where_d14_says
test: tests/test_msg_attachments.py::test_every_attachment_stream_row_agrees_with_the_read_stream
test: tests/test_msg_attachments.py::test_the_filename_round_trips_through_the_attach_stage
test: tests/test_msg_attachments.py::test_duplicate_filenames_and_cids_reach_the_existing_gaps
test: tests/test_msg_attachments.py::test_the_hostile_attachment_cases_go_through_the_container
test: tests/test_msg_attachments.py::test_no_reference_is_followed
test: tests/test_msg_attachments.py::test_the_attachment_facts_are_deterministic_across_hash_seeds
test: tests/test_msg_attachments.py::test_a_seeded_fuzz_of_the_attachment_tables_closes
test: tests/test_msg_embedded.py::test_the_embedded_table_header_size_is_the_oxmsg_24
test: tests/test_msg_embedded.py::test_no_deeper_embedded_table_is_read
stop: after attachments and the embedded summary
```

Allow-list (`turn=1b.7`): `emailextract/mapi.py`, `emailextract/msgcontainer.py`, `emailextract/attach.py`,
`fixtures/msg/`, `tests/test_msg_attachments.py`, `tests/test_msg_embedded.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md` -- **plus** the brief's named
additions, written here in the same turn: `emailextract/assemble.py` (the D6 gated edit only),
`tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`, `tests/support/mapi_table.py`,
`tests/support/olefile_oracle.py`, `tests/test_mapi.py`, `tests/test_msg_fixtures.py`,
`tests/test_msgcontainer.py` and `tests/test_msg_body.py` (**only** for the D0.1 fault-gap id fix,
each line named), `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`,
`docs/design/phase1b-ledgers.md`, `docs/design/phase1b-facts.md` (the method-2 sentence only),
`docs/design/msg-architecture.md`, `docs/design/phase0-gaps.md` (only if a registry sentence is wrong).

```declaration turn=1b.8
module: emailextract/mapi.py
module: tests/test_msg_rtf.py
test: tests/test_msg_rtf.py::test_lzfu_decompresses_and_checks_the_header_size_and_crc
test: tests/test_msg_rtf.py::test_mela_uncompressed_is_accepted
test: tests/test_msg_rtf.py::test_a_bad_crc_is_a_truncated_stream
test: tests/test_msg_rtf.py::test_the_rtf_stream_is_recorded_with_no_body_view
test: tests/test_msg_rtf.py::test_rtf_to_text_unsupported_is_emitted
test: tests/test_msg_rtf.py::test_no_rtf_encapsulation_refused_id_exists
stop: after the RTF decompress-and-record minimum (RTF-to-text stays a gap)
```

Allow-list (`turn=1b.8`): `emailextract/mapi.py`, `emailextract/msgcontainer.py`, `fixtures/msg/`,
`tests/test_msg_rtf.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md` -- **plus** the
brief's named additions, written here in the same turn: `emailextract/rtf.py` (new),
`tests/support/rtf_compress.py` (new), `tests/support/msg_construction.py`, `tools/make_msg_fixtures.py`,
`tests/test_phase1_scope.py` (`EXPECTED_LIBRARY`, +`rtf.py`), `tests/test_msg_fixtures.py`,
`tests/test_fixture_census.py`, `tests/test_turn_declarations.py`, `docs/design/phase1-turn-declarations.md`,
`docs/design/phase1b-fixtures.md`, `docs/design/msg-architecture.md`, `docs/design/phase0-gaps.md` (only if a
registry sentence is wrong). **`behavior_ledger.json` and `versions.py` are permissions, not duties.**

```declaration turn=1b.9
module: tests/test_msg_cross_container.py
module: tests/test_msg_outlook_layout.py
module: tests/test_msg_encodings.py
test: tests/test_msg_cross_container.py::test_the_pair_has_different_container_hash_and_equal_body_digest
test: tests/test_msg_cross_container.py::test_the_pair_is_one_document_shape_modulo_d14
test: tests/test_msg_cross_container.py::test_the_pair_with_a_plain_only_view_is_no_candidate
test: tests/test_msg_outlook_layout.py::test_the_handbuilt_layout_matches_the_construction_table
test: tests/test_msg_outlook_layout.py::test_the_handbuilt_layout_is_not_writer_defaults
test: tests/test_msg_encodings.py::test_001e_code_pages_1252_20127_28591_65001
test: tests/test_msg_encodings.py::test_internet_versus_message_codepage_disagreement
test: tests/test_msg_encodings.py::test_non_bmp_surrogate_pairs_survive
test: tests/test_msg_encodings.py::test_the_utf8_bom_and_lf_only_headers
test: tests/test_msg_encodings.py::test_all_five_rungs_are_covered_by_a_committed_msg
test: tests/test_msg_encodings.py::test_a_multivalued_string_keeps_every_value_in_order
test: tests/test_msg_encodings.py::test_a_string8_body_projects_as_utf8_with_the_ladder_rung
test: tests/test_msg_encodings.py::test_the_two_hostile_utf16_shapes_go_through_the_container
test: tests/test_msg_encodings.py::test_a_seeded_fuzz_of_the_string8_bytes_closes
test: tests/test_msg_cross_container.py::test_the_pair_is_never_deduped_by_raw_hash
test: tests/test_msg_cross_container.py::test_the_pair_is_deterministic_across_hash_seeds
stop: after the cross-container pair, the Outlook layout and the encodings
```

Allow-list (`turn=1b.9`): `emailextract/msgcontainer.py`, `emailextract/mapi.py`, `fixtures/msg/`,
`tests/test_msg_cross_container.py`, `tests/test_msg_outlook_layout.py`, `tests/test_msg_encodings.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md` -- **plus** the brief's named
additions, written here in the same turn: `tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`,
`tests/test_msg_fixtures.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`, `docs/design/msg-architecture.md`.
**`emailextract/msgcontainer.py` changes only to fix the one defect the non-BMP test exposes** (the
transport row's UTF-16 source span). **`behavior_ledger.json` and `versions.py` are permissions, not duties.**

```declaration turn=1b.10
module: emailextract/evals/gates.py
module: emailextract/evals/l1.py
module: emailextract/evals/falsify.py
module: tests/test_phase1b_gap_gate.py
module: tests/test_facts_coverage.py
module: tests/test_phase1b_scope.py
module: tests/test_phase1b_report.py
module: tests/test_turn_declarations.py
module: docs/phase1b-report.md
module: CHANGELOG.md
module: README.md
module: pyproject.toml
module: tests/ledger/facts_ledger.json
module: tests/ledger/behavior_ledger.json
test: tests/test_phase1b_gap_gate.py::test_every_msg_gap_id_has_a_mutation_case
test: tests/test_phase1b_gap_gate.py::test_the_phase1b_gap_gate_fails_when_a_gap_is_dropped
test: tests/test_phase1b_gap_gate.py::test_the_msg_ids_are_read_off_live_gap_ids
test: tests/test_facts_coverage.py::test_every_phase1b_fact_meets_its_floor
test: tests/test_facts_coverage.py::test_a_fact_below_its_floor_fails
test: tests/test_phase1b_scope.py::test_the_library_imports_with_no_olefile_and_no_gpl
test: tests/test_phase1b_scope.py::test_no_real_msg_is_in_the_repository
test: tests/test_phase1b_scope.py::test_fixtures_real_is_empty
test: tests/test_phase1b_report.py::test_the_report_has_every_required_section_once
test: tests/test_phase1b_report.py::test_the_report_names_the_version_bumps_and_the_licences
test: tests/test_phase1b_report.py::test_the_max_input_bytes_asymmetry_is_recorded
test: tests/test_turn_declarations.py::test_every_phase1b_declared_test_is_collected
test: tests/test_turn_declarations.py::test_every_undeclared_phase1b_test_fails_the_declaration
stop: after the gates, the scope test, the ledger components and the report; owner commits and tags 0.2.0
```

Allow-list (`turn=1b.10`): `emailextract/evals/gates.py`, `emailextract/evals/l1.py`,
`emailextract/evals/falsify.py`, `tests/test_phase1b_gap_gate.py`, `tests/test_facts_coverage.py`,
`tests/test_phase1b_scope.py`, `tests/test_phase1b_report.py`, `tests/test_turn_declarations.py`,
`tests/ledger/facts_ledger.json`, `tests/ledger/behavior_ledger.json`, `tests/ledger/label_ledger.json`,
`docs/phase1b-report.md`, `docs/design/phase1b-ledgers.md`, `CHANGELOG.md`, `README.md`, `pyproject.toml`,
`NOTICE`, `emailextract/versions.py`.

## (g) The committed final report

**Path:** `docs/phase1b-report.md`, committed as the **last** artifact of Turn 1b.10. Required sections (a test
checks each heading is present exactly once with non-empty body text): `## What was built`,
`## Named resolutions` (each with the test id that pins it), `## Coverage` (per-fact floors and observed
counts), `## Gap gate` (every `msg.*` id with its mutation case and fixture), `## Label-versus-parser
findings`, `## Licences` (including `olefile` BSD-3-Clause named in `NOTICE` as a test-and-tool dependency),
`## The max_input_bytes asymmetry`, `## Not done` (what Phase 1b leaves to Phase 2/3).

## (h) `tools/runboth.py`

Reused unchanged. The Phase 1b turns run the full suite and `python tools/update_behavior_ledger.py --check` on
both pinned interpreters (`py -V:Astral/CPython3.11.15`, with the PATH fallback), and the behavior-ledger
fingerprints over the `.msg` corpus are required to be **byte-identical** across interpreters; a difference is
recorded in the ledger header, never hidden.

## Turn 1b.1 -- outcome (the bump, the eight provenance points, the `value_codec` seam)

**Green.** `python -m pytest` on both interpreters: **2039 passed, 2 skipped** on 3.14.3 and on 3.11.15.
`tools/update_eml_golden.py --check`, `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check`
and `tools/make_fixtures.py --check` all exit 0 on both.

### The three reviewer decisions, applied

- **D1 (`Limits` unchanged).** `Limits` gained **no** field; the three CFB reasons joined `walk.CFB_CAP_REASONS`
  (a new tuple beside the walker's five) and `REASON_TABLE[Status.SKIPPED]`. `walk.CAP_LIMIT_FIELDS` stays the
  walker's five. This keeps `limits_fingerprint(L)` and every `.eml` `document_key` byte-identical:
  `tests/test_provenance_points.py::test_limits_fingerprint_is_unchanged_by_the_bump` pins
  `Limits.untrusted()` = `3475b245…` and the golden's declared `Limits` = `2238d89d…` (both computed on the
  pre-bump tree). Recorded in `phase1b-contract.md` (the D1 correction in section 1(Y)): the CFB limits live
  where Turn 1b.3's CFB reader publishes them (a separate `CfbLimits` is the expected shape), under the binding
  byte-identical-fingerprint constraint.
- **D2 (the permitted diff is three classes).** The re-recorded document moved by exactly the version value,
  one `"stream_ref": null` per `PartRecord`/`HeaderField` and one `"embedded": null` per
  `AttachmentOccurrence`. `phase1b-contract.md` section 10 and `phase1b-ledgers.md` section (d) were corrected.
  The bump test is `tests/test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys`.
- **D3 (the `parse` seam).** `parse(data, container_kind=None, *, limits, open_cfb=None)`; `ParseResult` accepts
  `"cfb_msg"` on success; `NAMED_ERROR_REASONS` adds `cfb_directory_loop`/`cfb_header_unsupported` and **keeps**
  `cfb_msg_unsupported` (interim). Every existing caller and `emailextract/ingest.py` is unchanged: with
  `open_cfb=None` a CFB magic is still `cfb_msg_unsupported`. `tests/test_provenance_points.py::test_parse_opens_a_cfb_container_instead_of_refusing`
  drives it with a fake opener.

### The golden diff summary (the one permitted re-record)

Re-recorded once with `python tools/update_eml_golden.py`. 126 fixtures; the diff is exactly: the header
`schema_version` `"5"` -> `"6"`; **1132** `"stream_ref": null` keys (parts + top-level headers); **34**
`"embedded": null` keys (27 fixtures carry attachments); **126** `record.output_schema_version` and 126
`run_record.output_schema_version` values; and the store keys/paths/bytes that name `OUTPUT_SCHEMA_VERSION`.
**Zero** of anything else: every `walk` pin (the `WalkResult`), every `parse_result`, every `CapRecord`, every
`container_hash`/`part_id`/`sha256`/span is byte-identical (the falsifier in the bump test fails on a stray
fourth class). Golden size 4,820,988 -> 4,888,412 bytes; digest `0d0dca4d…`.

### Tests edited, each tied to a row of section A5 (or reported as an extra)

Section A5 rows: `test_status_reasons.py` (the `skipped` tuple, `11` -> `14`); `test_contract_phase1.py` (the
`SKIPPED` tuple; `test_output_schema_version_is_four` removed -- renamed/moved to `test_contract_msg.py` per
D3); `test_parse_entry.py` (the `NAMED_ERROR_REASONS` tuple); `test_assemble.py`/`test_store.py` (the `"5"` ->
`"6"` literals); `test_limits.py` (D1's union assertion); `test_turn_declarations.py` (`1b.1` added to
`BUILT_TURNS`); `tests/ledger/behavior_ledger.json` (a `"6"` `contracts` line appended by the updater);
`tests/ledger/label_ledger.json` (the new support file + the deliberate golden re-record).

**Extra breakages the brief did not name** (all reported, none a weakened assertion):

1. `tests/test_contracts.py::test_every_dataclass_contract_has_a_round_trip_test` -- the new
   `ContainerStreamRef`/`EmbeddedSummary` need hand-typed round-trip instances (the test's whole point). Added.
2. `tests/ingest.py::test_the_manifest_and_the_store_are_byte_identical_across_seeds_and_interpreters` -- its
   `EXPECTED_DIGEST` hashes the identity projection, which now carries the bump's new keys, so the digest
   moved (`76bea6e3…` -> `8fec0ad1…`). The same digest is quoted in `docs/design/phase1-empirical.md`, which
   is **not** in this turn's allow-list, so that doc line is now stale -- flagged for the owner.
3. `tests/test_walk_iterative.py` -- its `_walk_visit` step-counter wrapper took exactly the seven positional
   arguments; the new `span_lookup` parameter made it eight. The wrapper now takes `*args, **kwargs`.
4. `tests/test_stdlib_header_scanner.py` -- its planted-defect wrapper monkeypatched `header_fields_at` with a
   three-argument function; the new `value_codec` keyword needed `**kwargs`.
5. `tests/test_phase1_scope.py::test_no_msg_cfb_routing_recursion_or_threading_exists` -- the helper that hands a
   CFB magic to the opener was named `_open_cfb`, and `FORBIDDEN_NAME_PARTS` still contains `"cfb"` (the
   contract's own section 11 row defers dropping it to 1b.3-1b.5). Renamed `_open_projected` so the frozen scope
   test is untouched. `CFB_CAP_REASONS` is a module constant (not a function/class name), so it is not flagged.

### Pinned numbers that moved

`OUTPUT_SCHEMA_VERSION` `"5"` -> `"6"`; `REASON_TABLE[Status.SKIPPED]` 5 -> 8 reasons (owner count 11 -> 14);
`NAMED_ERROR_REASONS` 6 -> 8; `VERBATIM_REASONS` 3 -> 4; the two `limits_fingerprint` characterization pins (D1);
`tests/test_ingest.py::EXPECTED_DIGEST`; the golden digest. `EMAIL_PARSER_VERSION` stays `"2"`; no
`CFB_VERSION`/`MSG_READER_VERSION`/`MSG_PROJECTION_VERSION` was added.

### The E4 numbers (section D)

Measured with the E4 harness (scratch, outside the repo) on a 40 MiB synthetic attachment, `walk()` **and**
`assemble()`, one subprocess per case:

- **before** (the unchanged tree): pass-through `delta/stream = 4.0` (167,817,216 B), `peak_after_walk +125.9 MB`;
  re-encoded `7.02`;
- **after** (the walker's leaf slice is a `memoryview`, and `text._decode_cte` materialises a buffer only where a
  decode actually needs one): pass-through `delta/stream = 4.0` (167,817,216 B), `peak_after_walk +83.9 MB`;
  re-encoded `7.05`.

**The 3x goal is not met, and this is the re-open-trigger stop.** The walker's own copy is gone (the walk stage's
peak fell by 42 MB), but the **metered** peak is `assemble()`'s: the attachment stage's one payload read
(`text.decoded_payload`, consumed by `attach.read_prefix`) still materialises a 40 MiB buffer, and the harness's
own `payload` + `raw` already cost 2x. The smallest design that would meet the goal is to extend the same view to
that read -- make `text.decoded_payload` return a `memoryview` and `attach.read_prefix` materialise only its
short prefix -- which touches `attach.py`, **outside this turn's allow-list**; the full fix is a lazy
`raw_view()` threaded through `_walk_visit`, whose `bytes`-only call sites (`.find`/`.startswith` in
`_split_headers_body`/`_segment`/`_header_fields_at`) make it the A2 re-open trigger, not a licence to
restructure. Per the brief this turn stops and reports: the owner decides Q5 (re-declare the budget to 5x, which
4.0x already meets, or accept the `attach.py` view).

**Owner decision (2026-10-13): the budget is re-declared to 5x** (build spec O9). 4.0x meets it, so Turn 1b.1's memory
goal is satisfied as re-declared and nothing else in this turn changes. The `attach.py` view is deferred to Turn 1b.5,
whose allow-list gains `emailextract/attach.py` and whose E4 re-run is gated at 5x on the real projection.

### What the contract got wrong that this brief did not catch

- **Section 7's `SpanRow.source_stream` cannot be `None` for a `SYNTHETIC` row** if the kind-gated `part_id`
  (point 2) and the record's `stream_ref` (point 1) are to carry the `synthetic:<role>:<ordinal>` label the same
  section names: the label has to live somewhere in the row, and the row has no other field for it. Carried in
  `source_stream` (the shape is unchanged; only that one comment is loose). `ContainerStreamRef` itself keeps the
  `synthetic:`-label invariant. Reported for the contract's section 7 comment.
- **The section 5 synthetic rule is a leaf rule.** A synthetic **container** (the multipart root) has body bytes
  in the walker's own reading, so applying `None`/`None` to it would contradict the section's own rationale
  ("a synthetic leaf has no bytes"). Built as written (`SYNTHETIC` -> `None`/`None`), which is why the twin test
  lists `size_bytes`/`sha256` as provenance differences for the framed root.
- **`tests/test_ingest.py`'s store digest and `phase1-empirical.md`'s copy of it** are a section-11 row the
  brief's list missed (extra breakage 2 above).
- **`test_contract_phase1.py::test_output_schema_version_is_four` was declared by two earlier turns ('1.0b' and
  '1.9') as well as 1b.1**: removing it from `test_contract_phase1.py` failed direction 1, so both earlier
  declaration blocks were refined to the new node id (the sanctioned "a later turn refines a declaration" path in
  section (f)).

### Inputs for the next turns

- **1b.2 (`tools/cfb_writer.py`, the first `.msg` fixtures):** the span-table vocabulary is
  `emailextract.container.SpanRow` / `PersistedSpanRow` / `CharsetOrigin` and the helper seams
  `source_key_of`/`stream_ref_of`/`span_lookup`; a container publishes `span_provenance`,
  `charset_sources`, `sector_accounting` and `cap_observations` through `getattr`, so `Container`'s Protocol is
  unchanged and `EmlContainer`/`FakeContainer` stay valid. `tests/support/fake_msg_container.py` is the shape a
  real fixture double must match to reuse the 1b.1 provenance tests.
- **1b.3 (`cfb.py`, where the CFB limits live):** the one binding constraint, recorded in the contract now --
  `limits_fingerprint(L)` and `document_key` must stay byte-identical for every existing `Limits` value (the
  golden proves it), so the three CFB caps' `Limits` fields cannot go on `assemble.parse.Limits`; publish a
  separate `CfbLimits`/observations channel and keep `walk.CFB_CAP_REASONS` as the reason vocabulary.

## Turn 1b.2 -- outcome (the CFB writer, the first `.msg` fixtures and the `olefile` oracle)

Built: `tools/cfb_writer.py` (a stdlib-only MS-CFB writer), `tools/make_msg_fixtures.py` and
`fixtures/msg/` (five fixtures + `SHA256SUMS`), `tests/support/olefile_oracle.py` (the tests-only
comparator), `tests/support/msg_construction.py` (the hand-typed construction tables) and
`tests/support/cfb_raw.py` (a raw-bytes inspector for the tests). No library code: `emailextract/**` is
untouched. Green both interpreters: **2050 passed, 2 skipped** on 3.14.3 and on the repo's 3.11.15, and
`make_msg_fixtures.py --check`, `make_fixtures.py --check`, `update_eml_golden.py --check`,
`update_behavior_ledger.py --check`, `update_label_ledger.py --check` all exit 0.

### The four reviewer decisions

- **D1 (applied).** `msg_outlook_layout_handbuilt` is built **this turn**. Its turn column in
  `phase1b-fixtures.md` moved `1b.3 -> 1b.2`, and the three-way disagreement is recorded there: the fixtures
  table said 1b.3, the build spec's 1b.9 row says "Outlook layout", the binding `declaration turn=1b.2` block
  names `test_the_outlook_layout_fixture_is_typed_from_b1_b4` in 1b.2. The declaration wins.
- **D2 (this is the stop-and-report finding; changed, with evidence).** The `.msg` sidecars **cannot be
  committed this turn**. `emailextract/evals/labels.py:43` is `FIXTURE_SUFFIXES = (".eml",)` and
  `load_sidecar` (`labels.py:150-154`) raises `LabelError` for any sidecar whose fixture does not end in
  `.eml`; `load_sidecars()` walks all of `fixtures/` by default and several tests call it at import time
  (`tests/test_gap_falsifiability.py:39`, `tests/test_label_structure.py:61`, `tests/test_phase1_exit_gate.py:197`,
  `tests/test_phase1_gap_gate.py:85`, `tests/test_phase0_gaps.py:111`). Probed directly before writing anything:
  a `fixtures/msg/x.expected.json` naming `x.msg` gives
  `LabelError: the fixture 'x.msg' has an unknown suffix -- expected one of ['.eml']`, and the same file makes
  `load_sidecars()` raise, so the whole suite would go red at collection. The only way to keep the gates green
  is the one-line `FIXTURE_SUFFIXES = (".eml", ".msg")` in `emailextract/evals/**` -- forbidden by D2 and the
  allow-list (that is 1b.10's file set). **So no sidecars and no label-ledger sidecar rows are committed this
  turn**, and `tests/test_fixture_census.py` checks the `.msg` files only. The smallest edit that would lift it
  is that one line in `labels.py`; it is not made here. Fact-id side was checked too and is fine: `msg.container_layout`
  and `msg.sector_accounting` are declared in `l1.FACTS` at phase 1 with no measurer, so a sidecar naming them at
  `CURRENT_PHASE = 0` reports `not_yet` (the declared-but-not-yet path), never an `OracleError`.
- **D3 (applied, to the extent D2 allows).** No sidecar is committed, so nothing carries a reader-derived value;
  the construction tables in `tests/support/msg_construction.py` carry exactly what a hand can type
  (`msg.container_layout`/`msg.sector_accounting` shapes and the raw directory/chain layout), typed from MS-CFB
  and B1-B4. Later turns add sidecars (once the loader accepts `.msg`) and extend them additively.
- **D4 (applied).** `olefile` moved to `pyproject.toml`'s `[dev]` extra (`olefile>=0.47,<1`), its `NOTICE` row
  moved from "optional/future reader" to "development dependency, never imported by the package", and the
  licence-audit test's assertion flipped from "not declared at all" to "declared under `[dev]` only, never a
  runtime dependency".

### The mutation results (three mutations, each must fail the table test *and* the oracle test)

Run against `tools/cfb_writer.py` (patched, then restored; both tests re-run per mutation):

| mutation | construction-table test | oracle test |
|---|---|---|
| mini-FAT cutoff written `<=` instead of `<` | FAILED (file length/sector count/directory rows) | FAILED (`fat length`, root/stream mismatch) |
| a wrong directory-tree colour (every colour inverted) | FAILED ("the child tree's root is not black", black-height) | FAILED (same, via the oracle's tree check) |
| off-by-one in a FAT chain | FAILED ("sectors [4] are in no class at all", classes) | FAILED (IndexError walking the bad chain) |

The oracle's colour/order check (`_child_tree_problems`) exists for the second row: `olefile` re-walks the
tree without checking it, so a plain read cannot see a wrong colour and the oracle has to validate the child
tree itself to be a real second opinion on the *directory shape*.

### Disagreements between writer, table and `olefile`

**None survived.** Every fixture agrees across all three: `olefile` reads every committed fixture with zero
`parsing_issues`, and `olefile_oracle.compare(...)` is `[]` for all five, on the in-memory build and on the
bytes on disk. The hand-typed sizes (3072/3072/20480/14848/8704 bytes; six/five/twenty-nine/seventeen sectors
at 512-byte or 4096-byte sectors) were typed from the construction tables before the writer ran and matched.
One detail that first looked like a disagreement and was not: a table's stream **paths** must be full posix
paths (`__nameid_version1.0/__substg1.0_00020102`), because three streams are all named
`__properties_version1.0` at different depths; the table was corrected to paths while it was still being typed,
before any writer output was consulted.

### Existing tests edited, and why

- `tests/test_licence_audit.py` -- `NOTICE_ONLY` shrinks to `{}`; `AUDITED_LICENCES["olefile"]` stays
  `BSD 3-Clause`; the olefile test's assertion flips to "declared under `[dev]` only". Its **name is kept**
  (`test_olefile_is_not_a_declared_dependency`): a rename failed `tests/test_phase1_scope.py`, which checks that
  every `tests/...py::name` cited by `docs/phase1-report.md` still resolves, and that report is not in this
  turn's allow-list.
- `tests/test_container.py` -- `test_the_fake_container_is_a_second_container_kind_without_cfb_code`: the
  in-process `"olefile" not in sys.modules` assertion (order-dependent the moment a test imports the oracle) is
  reworked into a fresh-subprocess check that `import emailextract` loads no `olefile`/`compoundfiles`.
- `tests/test_fixture_census.py` -- extended to the Phase 1b Family D `.msg` rows built this turn (the five rows
  whose turn names 1b.2 have committed `.msg` files; no `.msg` exists that is not a Family D row).
- `tests/test_turn_declarations.py` -- `BUILT_TURNS` gains `1b.2`.
- `docs/design/phase1-turn-declarations.md` -- the 1b.2 block is mirrored here (verbatim with the ledger's copy),
  the only file outside the brief's allow-list that this turn touches: `test_turn_declarations.py` reads only this
  file, and the two `tests/support/` modules and the two extra tests beyond the block's nine (the determinism
  check and the real-message listing check) are declared there.

### What Turn 1b.3 needs from this turn

- **The writer's API.** `tools/cfb_writer.py` exposes `storage(name, *children)` / `stream(name, data)`,
  `build_cfb(root, *, version=3, mini_cutoff=4096, mini_sector_size=64, sector_order=None) -> bytes`, the
  sentinels (`FREESECT`/`ENDOFCHAIN`/`FATSECT`/`DIFSECT`/`NOSTREAM`), the object types and the colour
  constants. `tools/make_msg_fixtures.py` exposes `FIXTURE_NAMES`, `build_fixture(name)`, `build_all()`.
  A fixture's construction table is `tests/support/msg_construction.CONSTRUCTION[stem]`; the raw-bytes
  inspector is `tests/support/cfb_raw.py`; the oracle is `tests/support/olefile_oracle.compare(bytes, table)`.
- **Hostile byte literals.** 1b.3's mutants are **not** writer output: they are hand-written byte literals
  frozen in `fixtures/msg/SHA256SUMS`, built by taking a well-formed fixture's bytes and patching a hand-typed
  offset (`tests/support/cfb_raw.patch_u32` models it), exactly as `tests/test_olefile_oracle.py` builds its two
  mutants. `cfb_raw` gained no mutation entry point beyond `patch_u32`, deliberately.
- **`msg_difat_extended`.** The writer deliberately emits no extended DIFAT chain (needs > 109 FAT sectors,
  ~7.1 MB at 512-byte sectors). That fixture must come from 1b.3: either a hand-written byte literal that adds
  one DIFAT sector to a writer output, or a deliberate extension of the writer, and 1b.3's allow-list owns the
  choice. `olefile` reads a DIFAT chain (`loadfat`, lines 1596-1637) but the writer's `_render_header` fixes
  `num_difat_sectors = 0` and `first_difat = ENDOFCHAIN`, so 1b.3 must not assume the writer can reach it.

## Turn 1b.3 -- outcome (`cfb.py`, the caps, sector classification, the hostile set and the seeded fuzz)

Built: `emailextract/cfb.py` (the package's own CFB reader -- stdlib only, a leaf), the four committed fixtures
(`msg_difat_extended`, `msg_fat_cycle`, `msg_directory_loop`, `msg_truncated_stream`, with their four new
`fixtures/msg/SHA256SUMS` lines), the hostile expectations (`tests/support/msg_construction.HOSTILE_EXPECTATIONS`),
the sixth construction table (`MSG_DIFAT_EXTENDED`), the extended-DIFAT helper
(`tests/support/cfb_raw.difat_sectors`), the `cfb`-versus-`olefile` cross-check
(`tests/support/olefile_oracle.cross_check`) and the four declared test files (`tests/test_cfb.py`,
`tests/test_cfb_hostile.py`, `tests/test_cfb_fuzz.py`, `tests/test_sector_accounting.py`; 21 test functions --
the 18 the block names plus the three checks the brief asks for beyond it, declared in the same block).
Green both interpreters: **2071 passed, 2 skipped** on 3.14.3 and on the repo's 3.11.15, and
`make_msg_fixtures.py --check`, `make_fixtures.py --check`, `update_eml_golden.py --check`,
`update_behavior_ledger.py --check`, `update_label_ledger.py --check` all exit 0 on both.

### The four reviewer decisions

- **D1 (applied, unchanged).** `Limits` gained no field: `update_eml_golden.py --check` exits 0, so the `.eml`
  golden (and `limits_fingerprint`) is byte-identical. The caps live in `cfb.py` as the frozen `CfbLimits`
  (`max_sector_count = 1_048_576`, `max_directory_entries = 65_536`, `max_difat_chain_length = 256`, arithmetic
  in the module docstring) with `DEFAULT_CFB_LIMITS`. `check_caps` reports a hit only when `observed > cap`
  (the boundary itself is legal); a hit carries the caller's value and the real observed count as a
  `CapObservation` (a `CapRecord` is 1b.5's). The three ids are exactly `walk.CFB_CAP_REASONS`, and both sides of
  each boundary are pinned by `tests/test_cfb.py::test_check_caps_reports_the_three_cfb_caps`; a real hit is a
  `CfbRefusal` at that cap id. `test_the_cfb_vocabulary_matches_the_walk_and_parse_contract` pins the ids against
  the walker.
- **D2 (applied, unchanged).** No `.msg` sidecar is committed and `emailextract/evals/**` is untouched
  (`labels.py` still accepts only `.eml`). The four hostile fixtures carry no `*.expected.json`; their behaviour
  is the hand-typed `HOSTILE_EXPECTATIONS`, typed from [MS-CFB] and the E2 table before `cfb.py` ran.
  `tests/test_fixture_census.py` needed **no** edit: its Family D check drives off the `phase1b-fixtures.md`
  rows (which already name all four fixtures at turn 1b.3) and the committed `fixtures/msg/*.msg` files, not off
  a hard-coded count.
- **D3 (applied; the smallest legal construction -- under 100 KB, as required).** `msg_difat_extended` is
  **59392 bytes / 116 sectors**, not ~7.1 MB. It is not a writer default: `tools/make_msg_fixtures.py`'s
  `_fixture_difat_extended` reassembles `_fixture_headers_html`'s bytes so the header declares **110 FAT
  sectors** of which only the first is real (the other 109 are `FREESECT` padding the file does not hold), the
  directory / miniFAT / mini stream shift to 110 / 111 / 112, and the **110th** FAT id lives in **one** extended
  DIFAT sector at 114. `olefile` reads it with zero `parsing_issues` (`fat_length = 115`); `cfb.py` reports
  `extended_difat=True`, `difat_sectors=(114,)`, `fat_sector_ids = range(110)`, `unaccounted = 0`.
- **D4 (applied, unchanged).** `open_cfb` returns, never raises; the whole-file result is `CfbFile | CfbRefusal`
  with a reason in `CFB_REFUSAL_REASONS` (the three names plus the three cap ids); a per-stream result is
  `read_stream(...) -> (bytes, fault)` with `fault in FAULT_KINDS`. The two named reasons are already members of
  `parse.NAMED_ERROR_REASONS`; `cfb.py` is a leaf (stdlib imports only, no `olefile`/`walk`/`model`/`parse`), and
  a fresh interpreter that loads the module pulls in nothing else.

### The declared work bound and the measured maximum

The bound is stated in the module docstring **before** the fuzz: `WORK_PER_SECTOR = 300`, `WORK_BASE = 4096`, so
`open_cfb` plus a full read of every stream is at most `300 * sector_count + 4096` steps. Over every fixture and
all **900** fuzz mutants the measured maximum is **317 steps** (`msg_outlook_layout_handbuilt`, 17 sectors,
budget 9196 -- 3.4% of it); the worst fixture-or-mutant ratio is the same **0.034**, so the bound holds with
~29x headroom. It is deliberately loose: the per-call chain bound derived in the docstring is E2's
`4 * sector_count + 16`, and the cap/table terms are upper bounds, not observed costs.

### The 14 E2 regression inputs (re-run beside the E2 table, `msg-architecture.md` 6.E2)

Every input's outcome class equals the E2 result; `cfb.py` spells the per-stream faults in lower case
(`cycle` for E2's `CYCLE`). `mutant_truncated_1200` is the one that first differed -- see the next section.

| E2 input | E2 outcome | `cfb.py` outcome |
|---|---|---|
| `mutant_bad_header_shift` | `cfb_header_unsupported` | `cfb_header_unsupported` |
| `mutant_bad_header_version` | `cfb_header_unsupported` | `cfb_header_unsupported` |
| `mutant_directory_loop` | `cfb_directory_loop` | `cfb_directory_loop` |
| `mutant_directory_self_reference` | `cfb_directory_loop` | `cfb_directory_loop` |
| `mutant_fat_cycle` | `CYCLE` | opens, `big` stream `cycle` |
| `mutant_size_2_40` | `SHORT_CHAIN` | opens, `short_chain` |
| `mutant_size_ffffffff` | `SHORT_CHAIN` | opens, `short_chain` |
| `mutant_start_out_of_range` | `OUT_OF_RANGE` | opens, `out_of_range` |
| `mutant_truncated_1200` | `OUT_OF_RANGE` | opens, `out_of_range` (+ downstream `short_chain`) |
| `trio_4095` / `trio_4096` / `trio_4097` | clean / clean / clean | clean / clean / clean |
| `v4_sector_4096` | clean | clean |
| `wellformed_base` | clean | clean |

### The three mutations (run against `cfb.py`, then restored; each must fail a named test)

| mutation | failing test(s) |
|---|---|
| the visited-set check removed in `chain_sectors` | `tests/test_cfb_hostile.py::test_a_fat_cycle_is_one_streams_fault` |
| a cap check `>=` instead of `>` | `tests/test_cfb.py::test_check_caps_reports_the_three_cfb_caps` |
| `classify_sectors` counts the mini stream's sectors as `free` | `tests/test_sector_accounting.py::test_the_eight_classes_sum_to_the_file_length`, `::test_free_and_slack_are_explicit`, `::test_a_cyclic_chain_is_visible_as_unaccounted` |

**A finding, reported not papered over.** The visited-set mutation was *invisible* at first: with the check
removed, a cyclic chain still returns `CYCLE`, caught by the E2 step bound (`4 * sector_count + 16`) rather than
by the visited set, so the outcome class was identical and no test failed. The visited set is what stops the
chain at the *revisit* instead of at the bound; `test_a_fat_cycle_is_one_streams_fault` now asserts that
(`big_stream.sectors == (4,)`, `available == 512`), which is the invariant that distinguishes the two guards.
With that assertion the mutation fails the named test as the brief requires; the two guards are now both
load-bearing and both tested.

### Disagreements between `cfb.py`, the typed tables and `olefile`

- **`olefile` cross-check (`cross_check`), 6 well-formed fixtures: none survived.** The two readers agree on the
  layout numbers, every stream's path, size and **bytes**, and the directory's entries, on the in-memory build
  and the bytes on disk. One real, benign difference was found and is handled, not hidden: `olefile` skips EMPTY
  directory slots (its `direntries` holds `None` for them) while `cfb.py` returns them, so `cross_check` compares
  only the non-empty entries. `msg_mini_cutoff_boundary` is a well-formed CFB that is **not a message** -- it has
  three plain streams and no `__properties_version1.0` -- so it is cross-checked with `require_properties=False`;
  `open_cfb`'s default still refuses it `not_a_message`.
- **E2's `mutant_truncated_1200`: `cfb_directory_loop` -> `out_of_range` (fixed).** The first run of the 14 gave
  `cfb_directory_loop` where E2 says `OUT_OF_RANGE`. Cause: `_entry_paths` set the directory-loop flag for a link
  pointing *outside* the directory (`node >= total`), not only for a revisit; the truncated file's last
  right-link points one past the three loaded entries, which is a lie, not a loop. Fixed: a stray link is now the
  observation `directory_link_out_of_range` (recorded on the root entry) instead of the whole-file loop, so the
  file opens and the per-stream class is E2's `out_of_range` -- which is also what the brief's `walk_directory`
  row names (a *revisit*, a self-reference or a duplicate root is `cfb_directory_loop`; a stray link is not). The
  other 13 inputs matched on the first run.
- **Tables: none survived.** The DIFAT-extended table (`MSG_DIFAT_EXTENDED`) and the hostile expectations are
  what `cfb.py` is compared to; nothing was read back from `cfb.py` and pasted in.

### `classify_sectors` closing the sum

Never failed to close: `sum(eight classes) + unaccounted == len(data)` on every fixture, every seed, every cut
length of `msg_headers_only` from 0 to its size, all 900 mutants, and the two `free`/`slack` probes; `unaccounted`
is **0** on every well-formed fixture and non-zero, never absorbed, on a cyclic chain (3584 bytes on
`msg_fat_cycle`) and on a directory loop (a refusal). `slack` needs a partial tail window no chain reaches -- no
*cut* of a committed fixture can produce one (the last body window is always a used sector), so the check builds
it by extending `msg_headers_only` with 100 bytes; the `free` check clears two FAT slots so a whole unreached
sector is `free`, not `unaccounted`.

### `msg_difat_extended` -- size and construction

**59392 bytes, 116 sectors (115 body + the header's own 4096-byte window is a v4 thing -- here 512).** Built as
described in D3: `_fixture_headers_html`'s bytes moved past a 109-sector padding run, with the extended DIFAT
sector (114) holding the 110th FAT id and `ENDOFCHAIN`, the header's 109 inline DIFAT slots all used (0..108),
and the header's FAT count, directory/miniFAT starts and DIFAT start/count patched to match. Every hand-typed
offset is asserted against the bytes before the patch. `fixtures/msg/SHA256SUMS` freezes it.

### Existing tests edited, and why

- `tests/test_msg_fixtures.py` -- the SHA256SUMS, real-message-listing and hash-seed determinism checks now
  enumerate `ALL_FIXTURE_NAMES` (all nine committed fixtures, hostile included); the DIFAT-padding check no
  longer demands a `FREESECT` tail when the inline DIFAT is **full** (the extended-DIFAT fixture); and
  `_class_problems` gained a `difat` group and subtracts the DIFAT sectors from `free`, so the DIFAT sector is
  not double-counted. The construction-table loop still runs over `CONSTRUCTION` (the six well-formed fixtures).
- `tests/test_turn_declarations.py` -- `BUILT_TURNS` gains `1b.3`.
- `tests/test_phase1_scope.py` -- **not in the brief's allow-list, but it cannot stay green otherwise**: the
  module census gains `cfb.py` in `EXPECTED_LIBRARY`, and `FORBIDDEN_NAME_PARTS` loses `cfb` (Turn 1b.3 is the
  turn that adds the CFB reader, so a `cfb`-named class is this phase's, not a later one's). Every other
  forbidden part (`olefile`, `msg_reader`, `read_msg`, the routing/threading names) still holds.
- `tests/ledger/label_ledger.json` -- the three changed `tests/support/*.py` hashes hand-edited (the ledger is
  additions-only and refuses a changed recorded file).
- `docs/design/phase1-turn-declarations.md` -- the `turn=1b.3` block mirrored (identical to the ledger's copy),
  with the three extra tests declared so the "an undeclared test fails" rule holds.
- `tests/test_fixture_census.py` -- **not edited** (green unchanged).

### What Turn 1b.4 and 1b.5 need from this turn

- **`cfb.py`'s public API.** `open_cfb(data: bytes, *, limits=DEFAULT_CFB_LIMITS, require_properties=True,
  work=None) -> CfbFile | CfbRefusal`; the frozen dataclasses `CfbLimits`, `CfbRefusal(reason, detail,
  observation)` and `CfbFile` (with `.layout()`, `.accounting_map()`, `.faults`, `.unaccounted`, `.extended_difat`,
  `.difat_sectors`, `.difat_fault`, `.root`, `.streams`); the named tuples `CfbHeader`, `CfbEntry`, `ChainWalk`,
  `DifatWalk`, `DirectoryWalk`, `StreamResult`, `CapObservation`; the functions `parse_header`, `walk_difat`,
  `read_fat`, `read_minifat`, `walk_directory`, `lookup_entry`, `chain_sectors`, `read_stream`, `classify_sectors`,
  `check_caps`. `read_stream(cfb, path_or_entry)` takes a posix path (`"<root>"` for the root's mini stream) or a
  `CfbEntry`.
- **`CfbRefusal` -> `NamedError`.** `refused.reason` is already a `parse.NAMED_ERROR_REASONS` member for the two
  whole-file names (`cfb_header_unsupported`, `cfb_directory_loop`) and `not_a_message`; the three cap ids are
  `walk.CFB_CAP_REASONS`, so 1b.5 builds the `CapRecord`s from `refused.observation` (`cap_id`, `value`,
  `observed`).
- **A stream fault -> `Status.TRUNCATED`.** `cfb.FAULT_REASON_IDS[fault]` is the reason id
  (`cycle -> declared_length_mismatch`, `out_of_range`/`short_chain -> stream_ended_early`), `cfb.FAULT_STATUS`
  is `"TRUNCATED"`, and `CfbFile.faults` is already the `msg.stream_faults` shape `(stream, fault, reason)`.
- **`msg.cfb_difat_extended`** is exposed as `CfbFile.extended_difat` (the read-through observation), with
  `difat_sectors` (the extended-chain sector ids) and `difat_fault` (only a broken chain faults, O1).

## Turn 1b.4 -- outcome (`mapi.py`, the string ladder, the class gate, named properties and recipients)

Built: `emailextract/mapi.py` (the MAPI property layer -- stdlib plus the sibling `cfb`, a **leaf**, never
raises, not wired into `parse`/`container`/`walk`), `tests/support/mapi_table.py` (property-table bytes typed
from [MS-OXMSG] 2.2.1.1 -- the *independent* builder the fixtures and the tests both use), the five committed
fixtures (`msg_non_ipm_note`, `msg_signed_class`, `msg_unknown_tags`, `msg_named_properties`,
`msg_codepage_disagree`, with their `fixtures/msg/SHA256SUMS` lines and five new construction tables in
`tests/support/msg_construction.py`), the `MAPI_EXPECTATIONS` literals (there are still no `.msg` sidecars:
`evals/labels.py` accepts only `.eml`, 1b.10's file set), and the three declared test files (**21** test
functions: the 15 the block names plus the six checks the brief asks for beyond them, declared in the same
block). Green both interpreters: **2092 passed, 2 skipped** on 3.14.3 and on the repo's 3.11.15, and
`make_msg_fixtures.py --check`, `make_fixtures.py --check`, `update_eml_golden.py --check`,
`update_behavior_ledger.py --check`, `update_label_ledger.py --check` all exit 0 on both. Interpreter hearth
used: CPython 3.14.3 (the `python` on PATH).

### D1-D7: the reviewer's decisions, applied (no decision changed)

- **D1 (applied, unchanged).** One failure convention: a value that cannot be decoded is `None` with a
  `fault` from the closed tuple `mapi.FAULTS` (**nine**: `stream_cycle`, `stream_out_of_range`,
  `stream_short_chain` -- carried from `cfb.read_stream` --, `stream_absent`, `utf16_odd_length`,
  `utf16_lone_surrogate`, `cp1252_undefined_byte`, `entry_truncated`, `table_size_misfit`) and the sha256 of
  the raw bytes is always carried beside it. No U+FFFD, no `errors="replace"`, no `surrogatepass`, no latin-1
  fallback. `mapi.py` never raises: the fuzz (450 mutants) and the three hostile cases prove it, and every
  text of every fixture and mutant UTF-8-encodes (a `_strings` walk asserts it; a lone surrogate would raise).
- **D2 (applied, unchanged).** `CODEPAGES` is the four hand-typed rows (`1252`, `20127`, `28591`, `65001`)
  and nothing else resolves. The two code pages come from the **fixed entries** `0x3FDE`/`0x3FFD` of the
  top-level table (B4) -- `msg_codepage_disagree` has no `__substg1.0_3FDE*`/`__substg1.0_3FFD*` stream at
  all. One trailing U+0000 is stripped and `trailing_nul=True` recorded (a second stays); the raw digest is of
  the bytes before the strip. `001F` is strict UTF-16LE with no ladder (`encoding_source=None`).
- **D3 (applied, unchanged).** `parse_property_table(data, *, header_size)` over the stream: 32 bytes at the
  top level, 8 for a recipient table (B2); entries 16 bytes, `u32 = (tag << 16) | type`; `(size-header) % 16
  != 0` records `table_size_misfit` and every complete entry still decodes; a stream shorter than its header
  records the misfit with no entries. Fixed types decode inline (`PT_SYSTIME` keeps the raw `u64` plus its
  16-digit lowercase hex); a varible type reads its `__substg1.0_<TAG><TYPE>` stream and carries any stream
  fault; `000D` is a `StorageRef`-style name in `Property.storage` and is **not** read; multi-valued types
  iterate the streams that **exist** (one directory pass, `_substg_streams`), never a declared count.
- **D4 (applied, unchanged).** `KNOWN_TAGS` is 13 rows `(tag, name, expected types, source)` with `source` in
  `{"B3", "MS-OXPROPS"}`; everything else is unknown, hex only -- nothing is frozen by a document. **`mapi.py`
  does not emit a gap per unknown property.** The distinct-unknown-pair counts: `msg_outlook_layout_handbuilt`
  yields **0** unknown pairs from the tables 1b.4 reads (its top-level table holds only the two code pages; its
  recipient table is `3001:0003`/`3002:001F`/`3003:001F`, all known) and its attachment storage's table would
  add **4** (`3705:0003`, `3707:001f`, `370b:0003`, `370e:001f`) -- that table is 1b.7's and is correctly not
  read here; `msg_unknown_tags` yields exactly **4** (`6200:0003`, `6523:0102`, `6748:0014`, `6827:001f`).
  B3 saw 236 across eleven real files, so one record per pair would be noise.
- **D5 (applied, unchanged).** A tag in `0x8000-0xFFFE` is flagged `named=True` and still decoded per its own
  type; `__nameid_version1.0`'s presence and its three streams' sizes are recorded and its contents are
  **never** parsed. `msg_named_properties` records `(True, (160, 440, 3090))` and the observation
  `msg.named_property_unresolved` with `["8005"]`; `8005:001F` (stream `__substg1.0_8005001F-00000000`, B1's
  named-property suffix, resolved by a fallback that never guesses an index) decodes to `"named property
  value"`.
- **D6 (applied; one reading spelled out).** `0x001A` is read first (`001F`, or `001E` through the ladder) and
  classified ASCII case-insensitively; the class string is returned **verbatim**. `ipm_note` is exactly
  `IPM.Note` or `IPM.Note.` + anything but the signed/encrypted prefixes; `signed_or_encrypted` starts
  `IPM.Note.SMIME`/`IPM.Note.Secure`; `IPM.Notebook`/`IPM.NoteX` are `not_ipm_note`. **`class_absent` covers
  both a missing `0x001A` and an empty one** (the brief's "no readable class"), and `class_unreadable` is a
  present class whose bytes fault (`decode_unicode`/ladder fault). For any verdict but `ipm_note`,
  `read_message` stops: no recipient, named-property or other-tag decode (the gate is proved by
  `test_the_class_gate_stops_before_recipients_and_properties`, which monkeypatches `decode_entry` and
  `read_recipients` to raise). `msg.class_not_ipm_note` is raised only for `not_ipm_note` and
  `signed_or_encrypted`. No `Status` is chosen here (O8 stays the owner's).
- **D7 (applied, unchanged).** The rows are the directory's `__recip_version1.0_#XXXXXXXX` storages, ordered by
  the hex index; a non-hex suffix makes that row unreadable (and raises `msg.recipient_table_unreadable`). Each
  row is decoded with the 8-byte-header table: `kind` (`0C15`: `1/2/3 -> to/cc/bcc`, else `unknown` with the
  raw integer kept), `display_name` (`3001`), `address_type` (`3002`: `SMTP -> smtp`, `EX -> ex`, else
  `unknown`, with the raw string kept), `address` (`39FE` if present and non-empty, else `3003`). The
  top-level header's `@16` count is compared with the directory's storages: a mismatch records the
  disagreement and raises `msg.recipient_table_unreadable`, and the rows are still returned. `msg.recipients`
  as a **fact** is not built here.

### The D2 registry-sentence discrepancy (reported, not worked around)

`docs/design/phase0-gaps.md:673-674` names `msg_codepage_disagree` as a committed fixture for
`msg.codepage_unresolved_ladder_used`. It cannot be one: with internet **28591** resolving the bytes, ladder
rung 1 fires, `encoding_source = internet_cpid`, and the gap is **not** emitted -- which is exactly what
`test_internet_cpid_wins_over_message_cpid` asserts (and why the registry also cannot use the `msg_string8_*`
family, whose internet code page resolves too). The brief predicted this. As instructed, the ladder was
**not** bent to fit the sentence: the gap is driven by an in-memory table whose two declared code pages do not
resolve (`test_ascii_and_utf8_rungs_record_their_source`, `codepages=(99999, 99998)`), and
`msg_codepage_disagree` is kept as the "internet wins, no gap" counter-example. **The registry sentence should
be corrected** (the fixture list for that id should keep the `msg_string8_*` family only if a
non-resolving-code-page member is added there; today the in-memory case is the driver).

### The ladder table (every fixture and every in-memory case)

Fixtures: only `msg_codepage_disagree` decodes a laddered value -- `0037:001e` ->
`[internet, 28591, internet_cpid]`, text `"synthetic \u0093 subject"` (iso-8859-1 keeps `0x93` as U+0093; the
message page 1252 would make it U+201C). The other fixtures' string properties are all `001F` (no ladder);
`msg_non_ipm_note`/`msg_signed_class` also carry a `0037:001e`, but the class gate stops before it. Every
fixture's recorded code pages: `1252/1252`, except `msg_codepage_disagree` at `28591/1252`.

In-memory cases (each asserted): internet wins forward (`28591/1252` -> `internet_cpid`, 28591) and reversed
(`1252/28591` -> `internet_cpid`, 1252, U+201C); the `001F` case records no ladder;
`codepages=(99999, 99998)` + all-ASCII -> `[none, null, ascii]`; + a UTF-8 byte sequence ->
`[none, null, utf8_strict]`; a multi-valued `001E` (`0x101E`) keeps all three values, each
`internet_cpid` with the resolving cp.

### The three mutations (run, reported, restored)

1. **Swap the internet and message rungs** -> 3 fail:
   `tests/test_mapi_ladder.py::test_internet_cpid_wins_over_message_cpid`,
   `::test_001e_goes_through_the_ladder_and_001f_is_utf16le`, `::test_multivalued_strings_keep_every_value`.
2. **32-byte header for a recipient table** -> 2 fail:
   `tests/test_mapi.py::test_recipients_are_read_from_the_recipient_tables`,
   `tests/test_mapi_hostile.py::test_a_recipient_count_mismatch_is_recorded`.
3. **A bare `startswith("IPM.NOTE")`** -> 1 fails:
   `tests/test_mapi.py::test_the_class_gate_records_the_class_verbatim`.

### Disagreements between `mapi.py`, the typed tables and the hand-built layout fixture

There was **no** disagreement between `mapi.py` and the typed tables: `tests/support/olefile_oracle.py`
agreed with all five new construction tables and with the decoded values on the first run
(`test_olefile_agrees_on_every_well_formed_fixture` and `test_every_fixture_matches_its_construction_table`
green unchanged). One real disagreement is worth recording, and its resolution is a **fixture is left alone**:

- **`msg_outlook_layout_handbuilt`'s recipient tags are named per its own 1b.2 typing, not per MS-OXPROPS.**
  That fixture's recipient table is `3001:0003 = 1` (its "type"), `3003:001F = ""` (its "email type") and
  `3002:001F = "Ada"` (its "display"), whereas `mapi.py` decodes by the MS-OXPROPS names (`0x3001` is the
  display name, `0x3002` the address type, `0x3003` the email address, `0x0C15` the recipient type). The
  reader therefore reads that row as `kind=unknown` (no `0C15`), `address_type=unknown` (`"ADA"`), `display_name=None`
  and `address=""`. The brief forbids editing an existing fixture and the tag identification is
  "verify by probe P4" until Turn 1b.7, so the fixture was **not** touched: the breaker test
  (`test_the_handbuilt_outlook_layout_matches_the_b1_b4_values`) checks the values B1-B4 type for that fixture
  -- the `@16`/`@20` counts `(1, 1)`, `0x3FDE`/`0x3FFD` as fixed entries at 1252, the `0102` HTML stream at 160
  bytes, **one** recipient row and the 160/440/3090 nameid sizes -- through the building blocks, not through
  `read_message`. The fixture has no `0x001A` at all, so its gate stops at `class_absent`; that is why the
  breaker uses `parse_property_table`/`decode_entry`/`read_recipients`/`named_properties` directly.
- Minor: the reader's `MapiMessage` fields for the two code pages are `internet_cp`/`message_cp`, not
  `internet_codepage`/`message_codepage`. `tests/test_contracts.py::test_no_email_module_declares_a_sibling_address_field`
  bans the substring `page` (the sibling address words are `page`/`cell`/`sheet`/`slide`) in any class-level
  field name in `emailextract/**`, and that test is **not** in this turn's allow-list -- so the field was
  renamed rather than the test edited. The `container_facts` keys `internet_codepage`/`message_codepage`
  (1b.5's, an open `str -> str` mapping) are unaffected and keep their spec names.

### Existing tests and non-test files edited, and why

- `tests/test_fixture_census.py` -- `_msg_family_d_rows` split into `_msg_family_rows(text, header)` plus the
  `D`/`E` wrappers; the `.msg` census block now unions the Family E rows (three of the five new fixtures are
  Family E) and asserts the five 1b.4 rows are committed. `committed_msg <= set(D) | set(E)`.
- `tests/test_turn_declarations.py` -- `BUILT_TURNS` gains `"1b.4"`.
- `tests/test_phase1_scope.py` -- **one** line: `EXPECTED_LIBRARY` gains `"mapi.py"`. The import-ban list is
  unchanged: `mapi.py` reaches its sibling as `from . import cfb` (an `ImportFrom` with no module), so no
  banned root (`cfb` above all) is named and the ban needs no exception.
- `tests/ledger/label_ledger.json` -- `tests/support/mapi_table.py` appended; `tests/support/msg_construction.py`'s
  hash line updated (the ledger is additions-only and refuses a changed recorded file; label_ledger.json is in
  the allow-list).
- `docs/design/phase1-turn-declarations.md` -- the `turn=1b.4` block appended, verbatim the ledger's copy, so
  the four extras are declared and "an undeclared test fails" stays true.
- `docs/design/phase1b-fixtures.md` -- the five fixtures' construction-table paragraph; the counts table's
  Family D turn range (`1b.2-1b.3` -> `1b.2-1b.4`).
- `tests/test_msg_fixtures.py` and `tests/test_olefile_oracle.py` -- **not edited**: green unchanged once the
  five fixtures were added to `FIXTURE_NAMES`/`CONSTRUCTION`.
- `tests/test_contracts.py` -- **not edited** (see the field rename above).

### The declared work bound

`MAPI_WORK_PER_BYTE = 8`, `MAPI_WORK_BASE = 1024`; a full `read_message` costs at most
`cfb.WORK_PER_SECTOR * sector_count + cfb.WORK_BASE + 8 * len(data) + 1024`. Measured worst over every fixture
and the 450 mutants: **0.0038** (`msg_named_properties`) and **0.0024** (the fuzz's worst, a 3072-byte
recipient base) -- a real read costs something and stays strictly under the bound. Every counted loop iterates
the bytes present (a table's 16-byte entries, the directory's entries, the substreams that exist); stream
*resolution* is `cfb.read_stream`'s and is uncounted there too. The multi-valued lookup is **one** directory
pass per read (`_substg_streams`), not a scan per entry, so the read stays linear in the bytes present.

### The five committed fixtures

- `msg_non_ipm_note` -- `IPM.Appointment`, plus a `001E` subject and one `__recip_version1.0_#00000000`
  (`0C15:0003 = 1`) the gate must not reach. `class_not_ipm_note` verdict, `msg.class_not_ipm_note`.
- `msg_signed_class` -- `IPM.Note.SMIME.MultipartSigned`, the same shape. `signed_or_encrypted` verdict,
  `msg.class_not_ipm_note`; no `Status` chosen (O8).
- `msg_unknown_tags` -- `IPM.Note` plus `6200:0003`, `6748:0014`, `6827:001F`, `6523:0102`; four distinct
  unknown pairs, one `msg.property_tag_unknown`.
- `msg_named_properties` -- `__nameid_version1.0` (160/440/3090) and one named property `8005:001F`;
  `msg.named_property_unresolved`.
- `msg_codepage_disagree` -- internet 28591 against message 1252 and one `001E` subject; **no** gap.

### What Turn 1b.5 needs from this turn

- **`mapi.py`'s public API.** `read_message(cfb_file) -> MapiMessage`; the building blocks
  `parse_property_table(data, *, header_size) -> PropertyTable` (`.header`, `.header_size`, `.entries`,
  `.fault`, `.first(tag)`), `decode_entry(entry, cfb_file, *, internet_codepage, message_codepage, storage,
  index) -> Property`, `decode_string8(raw, *, internet_codepage, message_codepage) -> TextValue`,
  `decode_unicode(raw) -> TextValue`, `classify_class(text, fault=None) -> str`,
  `read_recipients(cfb_file, *, ...) -> tuple[RecipientRow, ...]`,
  `named_properties(cfb_file) -> (bool, tuple[int, ...])`,
  `declared_counts(table) -> (recipients, attachments)`, `render_unknown_tags(properties)`; the records
  `MapiMessage`, `Property`, `RecipientRow`, `TextValue`, `RawEntry`, `PropertyTable`; the constants
  `FAULTS`, `OBSERVATION_IDS`, `ENCODING_SOURCES`, `CODEPAGES`, `KNOWN_TAGS`, `CLASS_VERDICTS`,
  `PROPERTY_TYPES`, `FIXED_TYPES`, `MV_FLAG`, `NAMED_TAG_MIN/MAX`, `HEADER_SIZE_TOP/SUB`, `MAPI_WORK_*`.
  The id constants are `mapi.MSG_*_*` (e.g. `MSG_CLASS_NOT_IPM_NOTE`), each a registered id.
- **An observation is a string id, not a record.** `MapiMessage.observations` is the tuple of gap ids raised
  at message level, in `OBSERVATION_IDS` order (`msg.class_not_ipm_note`, `msg.named_property_unresolved`,
  `msg.codepage_unresolved_ladder_used`, `msg.recipient_table_unreadable`, and `msg.property_tag_unknown`
  **once**); building a `gaps.later` row from one (its locator, phase, reason) is 1b.5's. Per-property detail
  rides the records: `MapiMessage.unknown_tags` (sorted distinct `tag:type` pairs), `MapiMessage.named_tags`
  (sorted tag hex), each `Property.key`, and each `TextValue`'s `source_kind`/`declared_cp`/
  `encoding_source` (the `msg.codepage_ladder` row is `[surface, source_kind, declared_cp, encoding_source]`
  -- a pure projection).
- **A `None` value becomes `unknown` text.** Every record carries `fault` (from `FAULTS`) exactly when the
  value is `None`; 1b.5 maps a faulted text to the document's `unknown(reason)` form, and the raw
  `raw_sha256`/`byte_length` are there so nothing is lost. A faulted stream maps via
  `cfb.FAULT_REASON_IDS`/`FAULT_STATUS` to `Status.TRUNCATED` (1b.3's contract, unchanged here).
- **The open question.** `msg.property_tag_unknown` is raised **once per message** here (this turn's reading
  of D4's "do not emit one gap per unknown property"), with the pairs on `unknown_tags`. 1b.5 must decide the
  `gaps.later` granularity: one aggregate row per message, or one row per distinct pair (B3's 236 would be
  noise), or a `container_facts` count. The pairs and their count are available either way.

## Turn 1b.5 -- outcome (`msgcontainer.py`: the projection over real CFB, headers from `0x007D`, one HTML body end to end)

The turn where a `.msg` first becomes an `EmailDocument`. `emailextract/msgcontainer.py` is **new** (`MsgContainer(data, *,
cfb_limits=...)`, the A'' projection over an opened `CfbFile` + `mapi.read_message`, the `Container` Protocol,
`span_provenance`, `charset_sources`, `cap_observations`, `sector_accounting`, `container_gaps`); `parse.py` gains the
default CFB opener and loses `cfb_msg_unsupported`; `ingest.py::_row_for` builds a `MsgContainer` for `cfb_msg`;
`assemble.py::_header_fields` gains the two `cfb_msg`-gated refinements D2 names. Nine `.msg` fixtures land (five
Family F, four Family E) plus the D9 correction to `msg_outlook_layout_handbuilt`; 19 declared tests. The `.eml`
golden, `behavior_ledger.json`, `versions.py`/`EMAIL_PARSER_VERSION` and every Phase 1 gate are untouched (all five
`--check` tools exit 0 on 3.12 and 3.11).

### D1-D10: the reviewer's decisions, applied (no decision changed)

- **D1 (layout: synthetic structure first)** -- applied as specified: `MIME-Version`/`Content-Type`/
  `Content-Transfer-Encoding` (and, for plain+HTML, `multipart/alternative` with a synthetic boundary) as
  `SYNTHETIC` rows `synthetic:structure:<n>` **first**; then the whole `0x007D` stream as one `REENCODED` row (its
  UTF-16LE source bytes are the span; the UTF-8 re-encoding is what the scanner reads; one trailing NUL stripped,
  line endings untouched); then one synthetic blank line and the body leaves, the multipart delimiters and the
  projection's separator being `SYNTHETIC` rows. A UTF-8 BOM on the transport text is projected first as its own
  `synthetic:prelude:1` region, so `headers.leading_bom` fires exactly as it does for an `.eml`.
- **D1's re-measurement (the ask that could have stopped the layout).** Measured, not assumed, on the walker's own
  resolution and on every consumer that reads a header by name -- probe with duplicated `Content-Type`,
  `Content-Transfer-Encoding`, `MIME-Version`, `Content-Disposition`, `Content-Location`, where the duplicate
  `Content-Type` is a `multipart/alternative` that would split the part if it won:

  | reader | expression | winner |
  |---|---|---|
  | `walk._header_value` (`content-type`, `content-transfer-encoding`) | first `parse_status == "ok"` field | **first** (`text/plain`, `8bit`) |
  | `walk` structural decision (`media.startswith("multipart/")`) | same call | **first** (one part; the second `multipart/alternative` line split nothing) |
  | `attach._media_as_written`, `attach._header_text` | first matching field | **first** (`text/plain`, `8bit`, `inline`) |
  | `selection._is_explicit_attachment`, `_content_location`, `_content_type` | first matching field | **first** |
  | `text.flowed_declared` | first `content-type` | **first** |

  No consumer reads the last or all occurrences, and `MIME-Version` has no by-name reader at all (the header stage
  classifies it as a `text` field, nothing else). So the layout stands and no stop was needed. `headers.fields` still
  records **every** occurrence in stream order -- that is a list, not a lookup, so it does not conflict.
- **D2 (`headers` is evidence only)** -- applied as the smallest `cfb_msg`-gated edit: inside
  `assemble._header_fields`, `value_codec` becomes `"utf-8"` for the projection and a field whose span row's `axis`
  is `SYNTHETIC` is skipped. Both sit under `if span_table is not None:`; the default branch (every `.eml`
  container) is the previous expression verbatim, so the `.eml` path is unchanged field for field -- evidence:
  `tools/update_eml_golden.py --check` exits 0, the behavior ledger does not move, and
  `tests/test_provenance_points.py::test_adding_a_cfb_msg_document_changes_no_eml_store_byte` is green. So a `.msg`
  whose virtual bytes carry structural lines still has `headers == []` without `0x007D` (no synthesis, O6).
- **D3 (no `0x007D`)** -- `headers == []`, the walkers do not run over an empty block, and the only gap is one
  document-level `msg.transport_headers_absent` (no `headers.no_date`/`headers.no_from` noise).
- **D4 (HTML pass-through)** -- the `0x1013` leaf is the stream's own bytes, unchanged, with CTE `binary` and
  `charset=<label>`, a `STREAM` row; `size_bytes`/`sha256` are the stream's. The label and `encoding_source` come
  from the mapi ladder run on the HTML bytes (the decoded text discarded) and are published through
  `charset_sources`. Code page -> label: `1252 -> windows-1252`, `20127 -> us-ascii`, `28591 -> iso-8859-1`,
  `65001 -> utf-8`; rungs 3-5 -> `us-ascii`, `utf-8`, `windows-1252`. `msg_html_meta_charset_contradicts`: the
  container's declared charset is the evidence the text stage already uses; that stage is untouched.
- **D5 (plain body)** -- `001F` re-encoded to UTF-8 (`REENCODED` row, `decoded_char_offset`/`decoded_char_len`,
  `charset=utf-8`, CTE `8bit`); both bodies -> `multipart/alternative`, plain first, the boundary a deterministic
  counter chosen against both body parts (so the same bytes always give the same boundary); a present-but-empty
  `0x1000` is **present** (`msg_zero_length_body`); a body whose bytes cannot be decoded records its fault and
  projects no view (no replacement string anywhere). `0x1009` is listed in `body_streams` and not projected (1b.8).
- **D6 (`container_facts`)** -- exactly the declared key list (`adapter`, `cfb_version`, `sector_size`,
  `mini_sector_size`, `mini_cutoff`, `sector_count`, `directory_entries`, `message_class`, `internet_codepage`,
  `message_codepage`, `body_streams`, `has_transport_headers`, `named_property_count`, `projection`, the eight
  `sectors.*` counts) -- no `recipient_count`/`attachment_count`/`time.*` yet. `container_hash` is the sha256 of the
  **CFB file bytes**; `raw_bytes()` is the virtual message.
- **D7 (outcomes and refusals)** -- `parse()` now opens CFB by default (`parse._default_open_cfb`:
  `cfb_header_unsupported`/`cfb_directory_loop`/`not_a_message` are the named errors); `cfb_msg_unsupported` is
  deleted from `NAMED_ERROR_REASONS` and from every site that produced it. A CFB **cap** hit is *not* a named error
  -- it is a `SKIPPED` document with the matching reason and a `CapRecord` carrying the caller's value and the real
  observed count (`cfb_limits` accepted). A non-`IPM.Note` class is a document with `Status.UNSUPPORTED`, the class
  verbatim in `container_facts`, nothing past the class opened, and the gate's registered gap
  `msg.class_not_ipm_note` (the class as its detail). **The signed class (`IPM.Note.SMIME.MultipartSigned`) is
  `Status.UNSUPPORTED`** -- the conservative reading the brief names, because nothing past the class is opened and
  no body is projected; the owner's open question (O8: `UNSUPPORTED` versus `PARSED`) stands. A per-stream chain
  fault is `TRUNCATED` (`msg.stream_truncated`, naming stream and fault). A `class_absent`/`class_unreadable`
  message has no class to stop on, so it is projected and parsed (a `PARSED` document, the owner's suggested
  reading) -- **no gap is invented for it**; say if it should carry one.
- **D8 (the disagreement gap, narrowly)** -- only `0x0037` (subject) against the decoded `0x007D` `Subject:` field;
  when both exist and differ, the transport header is canonical (it is in `headers`) and the gap
  `headers.mapi_header_property_disagree` is emitted **with the property text in its detail**. The registry entry
  (`phase0-gaps.md:192-198`) additionally asks for `value_source=transport_header` on the header's *fact*;
  `value_source` is a fact-level attribute no `headers` record carries today and the subject fact is Turn 1b.6's,
  so nothing was invented and no `container_facts` key was added -- reported here instead (the "do not invent one"
  branch of D8).
- **D9 (the hand-built fixture, corrected in one move)** -- the construction table in
  `tests/support/msg_construction.py` was retyped **first** (`001A:001F = "IPM.Note"` in the top-level table; the
  recipient table to `0C15` type / `3001` display name / `3002` address type / `3003` email address), then the
  generator, `fixtures/msg/SHA256SUMS`, `tests/test_cfb.py`'s mini-sector pin (`nested.start` 1 -> 2: the bigger
  top-level table shifts the root's mini stream), `tests/test_msg_fixtures.py` (the table is `32 + 3*16` and the
  recipient tags/streams are asserted), and `tests/test_mapi.py`'s breaker now goes through `read_message` (no
  building-block workaround) asserting `kind == "to"`/`kind_raw == 1`, `address_type == "smtp"`/
  `address_type_raw == "SMTP"`, the display name and the address. The `olefile` cross-check is green unchanged: one
  disagreement, and it is gone.
- **D10 (memory)** -- **over the re-declared 5x**: 5.05x (container + `walk` + `assemble`, the built `.msg` excluded)
  and 6.07x with the file in the delta; the container's own share is 2.0x and container + `walk` is 2.9x. The copy
  inventory and the dominant copy (the HTML projection over a 40 MiB HTML body) are in `msg-architecture.md`
  section 9; `attach.py` is untouched and the lazy `raw_bytes()` view is left to the owner, as the brief directs.

### The three mutations (run, restored, each fails by name)

1. **The synthetic structural lines moved after the `0x007D` text** -> 4 fail:
   `tests/test_msg_headers.py::test_no_transport_headers_yields_no_synthesized_headers`,
   `tests/test_msg_body.py::test_a_pass_through_html_leaf_is_never_exact`,
   `::test_a_plain_leaf_is_reencoded_and_container_stream`, `::test_selection_picks_html_over_plain`.
2. **A synthetic span row no longer excluded from `headers`** (`assemble._header_fields`'s skip dropped) -> 3 fail:
   `tests/test_msg_headers.py::test_headers_come_from_the_007d_stream_in_order`,
   `::test_no_transport_headers_yields_no_synthesized_headers`,
   `tests/test_msg_body.py::test_the_same_message_as_eml_and_msg_differs_only_where_d14_says`.
3. **A leaf allowed to claim `exact`** (`text.analyse_part`'s `container_stream` precompute dropped) -> 3 fail:
   `tests/test_msg_body.py::test_a_pass_through_html_leaf_is_never_exact`,
   `::test_a_plain_leaf_is_reencoded_and_container_stream`,
   `tests/test_provenance_points.py::test_analyse_part_forces_container_stream_part_level`.

### Existing tests edited, and why (10 files, no `.eml` fixture and no golden)

- `tests/test_parse_entry.py` -- the CFB case is no longer a refusal: the sniff opens a real fixture (`cfb_msg`, no
  error) and a damaged CFB is `cfb_header_unsupported`; the closed tuple loses `cfb_msg_unsupported`.
- `tests/test_provenance_points.py` -- `test_parse_opens_a_cfb_container_instead_of_refusing` rewritten for the same
  reason (a CFB opens; the caller's opener seam still overrides; the deleted id is gone).
- `tests/test_ingest.py` -- the recorded-skip case now uses a well-formed non-message CFB
  (`msg_mini_cutoff_boundary`), whose reason is `not_a_message`.
- `tests/test_contract_msg.py` -- the `NAMED_ERROR_REASONS` tuple loses `cfb_msg_unsupported`.
- `tests/test_mapi.py` -- D9's breaker through `read_message` (above).
- `tests/test_msg_fixtures.py` -- D9's pins (`32 + 3*16`, `0x001A` in the tag set, the recipient table's four tags
  and three streams).
- `tests/test_cfb.py` -- the named-property mini-sector pin 1 -> 2 (D9's bigger top-level table).
- `tests/test_fixture_census.py` -- the Family F rows are parsed and the 1b.5 count asserted (10 catalogue rows
  name this turn: four Family E, five Family F, plus the body half of `msg_headers_html`).
- `tests/test_phase1_scope.py` -- `EXPECTED_LIBRARY` gains `"msgcontainer.py"` (one line; nothing else in that file
  moved).
- `tests/test_turn_declarations.py` -- `BUILT_TURNS` gains `"1b.5"`.

### Q3 (contract section 13): does a synthetic leaf carry a `stream_ref`?

**It carries one.** A synthetic leaf's `PartRecord` publishes
`ContainerStreamRef(stream='synthetic:root:1', byte_offset=None, byte_len=None, axis=SYNTHETIC, fault=None)`: the
axis alone is C6's "scaffolding, not evidence" test, `model.py` already validates exactly that shape (no offsets, a
`synthetic:<role>:<ordinal>` label), and `None` would conflate "synthetic scaffolding" with "a `.eml` part with no
container". Stated with the alternative in `msg-architecture.md` section 9.

### Reported, not bent

- **A per-stream chain fault and a body fault both ride the same `msg.stream_truncated` id** (`TRUNCATED`, with the
  stream and fault in the detail). The registry names one id; if the owner wants the body fault distinguishable, it
  is a second id, not a wider one.
- **Container-level `msg.*` gaps are published, not yet persisted.** `MsgContainer.container_gaps` carries
  `msg.class_not_ipm_note`, `msg.transport_headers_absent`, `headers.mapi_header_property_disagree` and
  `msg.stream_truncated`, but nothing consumes it yet: R14 says `msg.*` rows ride `part.gaps`/`gaps.later`, and the
  only producer/consumer of that fact is `emailextract/evals/**`, which this turn's allow-list **excludes**. The
  hook is the container attribute (the 1b.1 `cap_observations` pattern); the wiring and the sidecar belong to the
  turn that owns `evals/` (1b.10), and `phase1b-facts.md:231` already lists these ids as live.
- **`mapi`'s message-level `observations` are not all mapped to gaps.** Only the class gate's is (D7 names it);
  `msg.property_tag_unknown`'s granularity is the owner's open question the brief defers to before 1b.6, so it was
  deliberately not decided here.
- **`msg.no_display_name_only_recipient`-style recipient facts are untouched**: recipients are 1b.6's, and the
  container reads only the class, the two code pages, `named_tags` and the body/subject properties.

### What Turn 1b.6 and 1b.7 need from this turn

- **Where a message-level fact plugs in.** `container_facts()` is the only fact surface a container has, and it is
  a flat `dict[str, str]`: 1b.6 adds `recipient_count` and the `time.*` keys, 1b.7 adds `attachment_count`, in the
  same commit as the data (D6's additive rule). The richer facts (`msg.recipients`, `msg.time_facts`) are the
  assembler's, built from `mapi` records the container does not yet publish.
- **What `mapi.read_message` returns that the container does not use.** `MapiMessage.recipients` (`RecipientRow`:
  `index`, `name`, `kind`/`kind_raw`, `display_name`, `address_type`/`address_type_raw`, `address`),
  `declared_recipient_count`, `declared_attachment_count`, `unknown_tags`, the property time tags
  (`0x0039`/`0x0E06`/`0x0E07`), and `observations` other than the class one. The container opens the message once,
  in `__init__`, so 1b.6 needs no second read.
- **Where an attachment row plugs in.** The attachments live in the **CFB directory** (`__attach_version1.0_#*`
  storages and their `__substg1.0_3701*` streams), not in the projection: 1b.7 reads them through `cfb`/`mapi`
  beside the projection and adds their rows to `container_facts`/the document, with a `STREAM`-axis span row per
  attachment stream if it wants `resolve_span` citations. `mapi.declared_counts` already gives the declared
  (recipient, attachment) pair for the mismatch check.
- **The projection's own re-open points.** A `.msg` attachment body would have to become a *virtual sub-message* if
  1b.7 wants the walker to see it; this turn deliberately keeps `raw_bytes()` to one message, so an attachment leaf
  is a `STREAM` row, not a nested part.


## Turn 1b.6 -- outcome (message-level facts: subject, sender, recipients, time, and the four mapped observations)

**Built, uncommitted (the brief says do not commit).** `emailextract/mapi.py` gains eight
`KNOWN_TAGS` rows and nothing else (D2, table rows only). `emailextract/msgcontainer.py`
publishes one frozen `message_facts` attribute (D1) and maps `mapi`'s four remaining
message-level observations into `container_gaps` (D8). Five new `.msg` fixtures with their
construction tables, and three new test files (19 functions: the 8 declared plus 11 extras).
`assemble.py` is untouched (the facts need no change there), as are `cfb.py`, `walk.py`,
`attach.py`, `model.py`, `parse.py`, `ingest.py` and `emailextract/evals/**`.

### D1-D9: the reviewer's decisions, applied

- **D1 (where the fact lives).** Applied. `MsgContainer.message_facts` is one frozen
  `MessageFacts` NamedTuple, all plain data; nothing consumes it (the measurers are Turn
  1b.10) and no `EmailDocument`/`to_json`/`ContainerFacts` field is added beyond D6's two flat
  key families in `container_facts()`.
- **D2 (known tags).** Applied, rows only, source `"MS-OXPROPS"`. `tests/test_mapi.py` alone
  after the edit: 8 passed, nothing moved (no committed fixture carries these tags).
  `tests/test_mapi_hostile.py`'s vocabulary/leaf checks stay green (no import and no
  `OBSERVATION_IDS` change).
- **D3 (subject).** Applied. `property_text`/`property_fault` from `0x0037`,
  `header_text` the verbatim `0x007D` `Subject:` field text (the line's trailing CR dropped,
  the field's own leading space kept), `canonical`/`value_source` = `transport_header` iff a
  header text exists, else `mapi_property` iff only the property exists, else `None`. Both
  texts verbatim: no strip, no case fold, no repair. The 1b.5
  `headers.mapi_header_property_disagree` gap is byte-for-byte unchanged (same detail, same
  condition) and the fact is now its second carrier.
- **D4 (sender).** Applied. Four raw fields + `value_source="mapi_property"`. `address` is
  `0x0c1f` as stored and `smtp_address` is only ever `0x5d01`, never derived. **No sender
  gap and no sender-versus-`From` comparison** (deliberate: the display-name/address-form
  disagreement semantics are unmeasured, and a noisy gap would be a guess). A future
  comparison would need a probe of the observed `From`/`0x0c1f`/`0x5d01` shapes before any
  gap id.
- **D5 (recipients).** Applied, with one reading stated in the code: `address` is `0x3003`
  as stored and `smtp_address` is `0x39fe` when present -- **two separate fields**, never the
  merged `RecipientRow.address` (which prefers `0x39fe`). So `msg_recipients_display_only`
  (a `to` row typed `SMTP` with neither tag) is `address=None`/`smtp_address=None`, and
  `msg_recipients_ex_no_smtp` keeps `/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2` in `address` with
  `smtp_address=None`. Index order, duplicates kept (never merged, never re-sorted).
- **D6 (`recipient_count`).** Applied with a deviation; see "Reported, not bent".
- **D7 (time).** Applied. Exactly two keys per present, unfaulted `PT_SYSTIME` tag, ascending
  tag order: `time.<tag>.filetime_hex` (the raw `u64` as 16-digit lowercase hex, `Property.value_hex`
  itself, verified equal to `format(value, "016x")`) and `time.<tag>.utc` (whole seconds
  truncated from the 100 ns ticks, integer arithmetic from the FILETIME epoch, `Z` suffix). A
  tag absent, of another type or faulted gets **no keys**. A rendering past the year range is
  `unrepresentable` (hex still present); `0` is `1601-01-01T00:00:00Z` with no sentinel
  interpreted. `times_axis` keeps `not_built_in_phase1` and `times == []`.
- **D8 (the mapping).** Applied: the four observations become `ContainerGap`s in
  `mapi.OBSERVATION_IDS` order, after the 1b.5 gaps, each emitted once per message. The
  class gate's own id stays where 1b.5 put it.
- **D9 (nothing moves).** Applied: no 1b.5 test, no virtual byte, no span row and no
  `part_id` changed. The only 1b.5-visible effect is D6's new fact key, handled by the
  deviation below so that `test_container_facts_carry_the_fixed_key_list` needed no edit.

### The exact `message_facts` type

`emailextract/msgcontainer.py`, five frozen `NamedTuple`s (my design, D1's constraints):

```python
class SubjectFact(NamedTuple):
    property_text: str | None; property_fault: str | None; header_text: str | None
    canonical: str | None; value_source: str | None

class SenderFact(NamedTuple):
    name: str | None; address_type: str | None; address: str | None
    smtp_address: str | None; value_source: str

class RecipientFact(NamedTuple):
    kind: str; kind_raw: int | None; display_name: str | None; address: str | None
    address_type: str; address_type_raw: str | None; smtp_address: str | None
    fault: str | None; value_source: str

class TimeFact(NamedTuple):
    tag_hex: str; filetime_hex: str; utc: str

class MessageFacts(NamedTuple):
    subject: SubjectFact | None; sender: SenderFact | None
    recipients: tuple[RecipientFact, ...]; times: tuple[TimeFact, ...]
```

No `Property`/`TextValue` object is published. A message whose class gate stopped gets
`MessageFacts(None, None, (), ())` (tested).

### The five fixtures, hand-typed beside what the code produced

Every expectation below was typed in the test file (and the construction table) **before** the
reader ran, and the `olefile` oracle cross-check reads the recipient rows independently.

| fixture | hand-typed | produced |
|---|---|---|
| `msg_recipients_display_only` | one `to`(1) row, "Ada Lovelace", `address=None`, `smtp=None`, `smtp`/`SMTP` | identical |
| `msg_recipients_ex_no_smtp` | one `to`(1) row, "Grace Hopper", `address="/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2"`, `ex`/`EX`, `smtp=None` | identical |
| `msg_recipients_bcc_duplicates` | three rows: `to` Ada, `bcc`(3) Grace, `to` Ada (byte-identical duplicate); `recipient_count="3"` | identical |
| `msg_time_property_vs_date_header` | `time.0039.*` and `time.0e06.*`, both `01dd597cebed5800` / `2026-10-11T12:34:56Z` | identical |
| `msg_unicode_subject` | `property_text="synthetic ünicode 世界 subject 🌍"`, `header_text=None`, `canonical="mapi_property"` | identical |

### The FILETIME cases (hand-computed in `tests/test_msg_time.py`)

- **Truncation, not rounding.** `13_436_195_696 s + 0.9999999 s` -> `2026-10-11T12:34:56Z`
  (rounding would be `12:34:57Z`).
- **The epoch.** raw `0` -> `0000000000000000` / `1601-01-01T00:00:00Z`, no sentinel.
- **Beyond the year range.** `0xffffffffffffffff` -> `ffffffffffffffff` /
  `unrepresentable`, no raise and no clamp.
- The fixture value's hex is asserted exact in case and width and cross-checked against
  `mapi`'s own `Property.value_hex`.

### The four D8 gaps: the registry text, what `mapi` can know, what was emitted

- **`msg.recipient_table_unreadable`** -- registry: "a recipient storage's table could not be
  read (a broken chain, a truncated table, or a count that disagrees with the real rows); the
  reader trusts the directory". Emitted once, detail `declared=<n> rows=<n>` for a count
  disagreement (built in a test by editing the construction: `declared=5 rows=1`), else the
  row/table fault (`stream_absent` for a row whose table stream is absent). Matches.
- **`msg.property_tag_unknown`** -- registry: "a property tag the reader does not recognise;
  recorded as unknown, hex only". Emitted once, detail the sorted distinct `tag:type` pairs
  from `MapiMessage.unknown_tags` joined by `,`
  (`msg_unknown_tags`: `6200:0003,6523:0102,6748:0014,6827:001f`). Matches.
- **`msg.named_property_unresolved`** -- registry: "a named property's name-to-id mapping
  could not be resolved". Emitted once. **Deviation**: the brief asks for "`tag:type` pairs
  from `MapiMessage.named_tags`", but `named_tags` carries the **tag hex only** (it is
  `sorted({prop.tag_hex ...})`, e.g. `8005`), not a `tag:type` pair; `unknown_tags` is the
  one that carries pairs. D2 restricts `mapi.py` to `KNOWN_TAGS` rows, so the detail is the
  tag hexes joined by `,` (`8005`) -- the record is not padded with a type it does not know.
  Reported, not bent; if the owner wants `tag:type`, it is a `named_tags` change in `mapi.py`.
- **`msg.codepage_unresolved_ladder_used`** -- registry: "the encoding ladder's later rungs
  were used; the rung that fired is recorded as `encoding_source`". Emitted once, detail
  **empty**: `mapi` exposes no surface set (it records only the aggregate observation), so
  the surface set is not available without a `mapi.py` change. Reported, not bent.

### The three mutations (run, restored, each fails by name)

1. `filetime_hex` upper-cased instead of the 16-digit lowercase form -> **4 fail**:
   `tests/test_msg_time.py::test_time_properties_are_flat_hex_keys`,
   `::test_the_filetime_hex_is_lossless_and_canonical`,
   `::test_the_filetime_rendering_truncates_the_sub_second_part`,
   `::test_a_filetime_beyond_the_year_range_is_unrepresentable`.
2. The recipient records de-duplicated (`dict.fromkeys`) -> **2 fail**:
   `tests/test_msg_recipients.py::test_recipients_are_facts_beside_the_headers`,
   `::test_the_recipient_records_match_the_olefile_oracle`.
3. `recipient_count` taken from the declared count instead of the directory rows -> **1 fails**:
   `tests/test_msg_recipients.py::test_recipient_count_is_the_directory_count_not_the_declared_count`.

### Existing tests edited, and why

Exactly the four the brief expects, all in the allow-list: `tests/test_fixture_census.py` (the
five Family E rows and the 1b.6 count), `tests/test_turn_declarations.py` (`BUILT_TURNS` gains
`"1b.6"`), the mirrored block in `docs/design/phase1-turn-declarations.md`, and
`tests/ledger/label_ledger.json` (the hand-edited `tests/support/msg_construction.py` hash, the
only changed covered file). **No 1b.5 test was edited.** `tests/test_msg_fixtures.py` needed no
edit: its picks iterate the generated tables and `ALL_FIXTURE_NAMES`, so the five new files are
covered automatically.

### Reported, not bent

- **D6 vs D9 (a real collision, resolved narrowly).** D6's literal reading -- "`recipient_count`
  is `str(len(message.recipients))`", absent only for a stopped message -- would add
  `recipient_count="0"` to the four zero-recipient Turn 1b.5 fixtures and break
  `tests/test_msgcontainer.py::test_container_facts_carry_the_fixed_key_list`, which D9 says
  must not change and the allow-list excludes. I resolved it by publishing `recipient_count`
  **only when the directory yields at least one recipient row** (absent when there are none,
  exactly as absent for a stopped message). That keeps D9 literally true and is the same rule
  1b.7's `attachment_count` will need to keep the pin true. If the owner prefers the literal
  reading, it is a one-line change plus a one-line `FACT_KEYS` edit in `test_msgcontainer.py`.
- **A dormant 1b.5 gap-id anomaly, found while mapping (not changed, out of scope).** The 1b.5
  outcome note ("Reported, not bent") says a body fault rides `msg.stream_truncated`, but
  `msgcontainer._project` emits `ContainerGap(plain.fault)`/`ContainerGap(html_fault)` -- the
  fault **name** as the gap id, not a registry id. No committed fixture has an undecodable body,
  so nothing reds; a hostile body fixture would expose it. D9 forbids the edit this turn, so it
  is reported, not touched.
- **No `.msg` sidecar** (as directed): `emailextract/evals/labels.py` still accepts only `.eml`,
  so the five fixtures have no `*.expected.json`; the census checks the `.msg` files only.

### What Turn 1b.7 and Turn 1b.10 need from this turn

- **The hook.** `MsgContainer.message_facts` (plain data) and `MsgContainer.container_gaps` (the
  1b.5 gaps plus the four mapped here). `container_facts()` now carries `recipient_count` and the
  `time.<tag>.*` pair-family; 1b.7 adds `attachment_count` under the same "only when the
  directory yields one" rule.
- **Unpersisted.** Nothing writes these to a record: the `msg.*` gap rows, `msg.recipients`,
  `msg.time_facts` and the container facts stay container-side until 1b.10 wires `evals/` and
  projects them (the `msg.recipients` sidecar shape drops `smtp_address`/`fault`/`value_source`;
  `msg.time_facts` is the `TimeFact` triple). The `Date` header and the MAPI times are still
  distinct and unreconciled (Phase 3).

## Turn 1b.7 -- outcome (attachments: the MIME projection, the MAPI attachment facts, the depth cap)

Built on `d50b3e2` (Turn 1b.6). Not committed (the brief's instruction). The turn's code
(`mapi.read_attachments`, the `msgcontainer` projection and facts, the one `assemble.py` gate)
landed in the working tree; this note is its outcome.

### D0-D8: the reviewer's decisions, applied (no decision changed)

- **D0.1 -- the body/transport fault-gap id, fixed.** `_project` no longer emits
  `ContainerGap(fault_name)`; a body, HTML or transport stream fault is now
  `msg.stream_truncated` with `<stream>:<fault>` in the detail, and the document is `TRUNCATED`
  with the mapped reason (`stream_cycle` -> `declared_length_mismatch`, else `stream_ended_early`,
  contract section 2). A `0x007D` transport fault that was dropped silently now raises the same
  gap. Pinned by `tests/test_msgcontainer.py::test_a_body_or_transport_stream_fault_is_the_registered_truncated_gap`
  (three patched streams, exactly one gap each, no duplicate from the cfb-level scan).
- **D0.2 -- the facts-doc typo, corrected.** `phase1b-facts.md` (`msg.attachments`) now reads
  `1` by-value, `2` by-reference, `3` by-reference-resolve, `4` by-reference-only, `5` embedded,
  `6` OLE (the build spec / registry / MS-OXCMSG reading). One sentence, as directed.
- **D0.3 -- the pin.** Every committed `.msg` fixture's virtual bytes and span rows were pinned
  before the projection changed (`.scratch/pins_1b7_pre.json`); the pre-turn virtual sha256 of
  **every openable fixture with no attachment storage** is now a hand-typed dict in
  `tests/test_msg_attachments.py::test_a_message_without_attachments_projects_as_before` (27
  entries). All 25 no-attachment fixtures are **byte-identical** after the turn. The one earlier
  fixture that *has* an attachment, `msg_outlook_layout_handbuilt`, changes by design (D1) and is
  excluded from the pin; a line in that test asserts its `attachment_count == "1"`.
- **D1 -- the multipart/mixed projection.** Re-measured: the virtual message opens
  `MIME-Version: 1.0` / `Content-Type: multipart/mixed; boundary="=_msg_alt_0"` / the transport
  headers, and the root part's `content_type` is `multipart/mixed`, so the 1b.5 first-wins layout
  holds. A message with no attachment storage still produces exactly the 1b.5 bytes.
- **D2 -- a by-value leaf.** The data stream's bytes are the leaf body (pass-through `binary`),
  `PartRecord.size_bytes`/`sha256` are the stream's, and one `STREAM` span row carries the
  stream's digest. The headers are as D2 says. **Defaulted versus declared MIME:** with no
  `0x370E`, the projected `Content-Type` is `application/octet-stream` and `mime_tag` is `None`
  in the facts; the attach stage's `declared_mime` verdict reads
  `application/octet-stream` **either way** (measured on `msg_outlook_layout_handbuilt`'s
  attachment, whose tag is absent: `declared_mime=VALUE application/octet-stream`), so only the
  container fact distinguishes defaulted from declared -- reported below.
- **D3 -- the filename ladder and the raw/decoded pair.** Long over short over display, first
  present non-empty wins; the rung is recorded. The parameter is a plain quoted string only for
  printable ASCII outside `"` `\` `/` `;`, else RFC 2231. The hostile fixture round-trips:
  property text `..\evil/../../x\x00y` -> header `filename*=utf-8''..%5Cevil%2F..%2F..%2Fx%00y`
  -> `attach.py` recovers `..\evil/../../x\x00y` (the occurrence's `filename_decoded`). No
  `Path`/`open`/`os.*`/network call is made while it is read (the guard test patches them and
  records nothing). The name is never sanitised.
- **D4 -- embedded, OLE, the digest, the cap.** An embedded message gets an `EmbeddedSummary`
  on `AttachmentOccurrence.embedded` (non-`None` only for method 5) and a `storage_tree_sha256`;
  the embedded table's header measured **24 bytes** (below). OLE (6) is recorded (method, name,
  `mime_tag`, no bytes) with no parsing; **`cfb.CfbEntry` exposes no CLSID** (its fields are
  index/name/entry_type/colour/left/right/child/start/size/path/faults), so no class is recorded
  -- reported as D4 allows. The depth cap fires `msg.embedded_depth_cap` (detail `2>0`); the
  nested row still counts in the embedded message's `attachment_count`.
- **D5 -- the reference methods and the faults.** Methods 2/3/4 are recorded (method, ladder, no
  bytes) and emit `msg.attachment_method_unsupported` (detail `<index>:<method>`); no path or URL
  property is read (`0x3701` is never looked for: the fixture has no data stream). A by-value
  attachment with **no** data stream (`stream_absent`) or a **faulted** one (`stream_out_of_range`)
  emits `msg.stream_truncated` with detail `attach:<index>:<fault>` and gives the document
  `Status.TRUNCATED` (`stream_ended_early`) -- the per-document default the brief named, no new
  id.
- **D6 -- where the facts live.** `MsgContainer.attachment_facts`, a frozen tuple of
  `AttachmentFact` named tuples (plain data; no `Property`/`TextValue`), one per directory row in
  index order; `container_facts["attachment_count"]` published only when at least 1 (the 1b.6
  rule). `assemble.py`'s one `cfb_msg`-gated edit fills `AttachmentOccurrence.embedded` from the
  facts, joined through the span table; every `.eml` container keeps the current expression.
- **D7 -- `mapi.py`.** Nine `KNOWN_TAGS` rows added (`0x3701/0x3703/0x3704/0x3705/0x3707/0x370E/
  0x3712/0x3714/0x7FFE`, `source = "MS-OXPROPS"`, P4 not run on real mail) and `read_attachments`
  reads one row per directory storage (8-byte sub-table, same fault discipline, never raises, a
  work tick per row). `mapi.py` stays free of `olefile`. Attachment-row unknown tags feed
  `msg.property_tag_unknown` through the 1b.6 mapping (so `msg_outlook_layout_handbuilt`'s
  attachment `0x370B` now appears in that observation's detail: `370b:0003`).
- **D8 -- E4 with an attachment.** See the E4 numbers (6x budget held).

### The embedded table's header size (D4), measured

The embedded `__properties_version1.0` under `msg_embedded_message` is 56 bytes. `(56 - 24) % 16
== 0` leaves exactly the two constructed entries (`001A` class, `0037` subject); `(56 - 8) % 16`
also divides, but an 8-byte header injects a spurious `0000:0000` entry
(`mapi.parse_property_table(..., header_size=8)` yields three entries). **24** is taken as the
`[MS-OXMSG]` embedded-message header and pinned by
`tests/test_msg_embedded.py::test_the_embedded_table_header_size_is_the_oxmsg_24`, which reads the
constructing table's size from `tests/support/msg_construction.py` independently.

### The ten fixtures, hand-typed beside what the code produced

All are version 3, 512-byte sectors, a 4096-byte mini cutoff. `method`/`size`/`sha256` are the
fact's; the header is the projected leaf's first line.

| fixture | method | filename (rung) | mime | size / sha256 (8) | gap |
|---|---|---|---|---|---|
| `msg_embedded_message` | 5 | forwarded.msg (long) | - | - / - | none; `EmbeddedSummary(IPM.Note, ts=True, "Fwd: hello", 1, 0)` |
| `msg_embedded_depth_two` | 5 | outer.msg (long) | - | - / - | `msg.embedded_depth_cap` `2>0` |
| `msg_attachment_with_cid` | 1 | report.pdf (long) | application/pdf | 38 / 21f4757e | none |
| `msg_attachment_hidden` | 1 | inline-image.png (long) | image/png | 17 / 1f967b6f | none (hidden=True, inline=True) |
| `msg_attachment_ole` | 6 | object.bin (long) | application/octet-stream | - / - | none |
| `msg_attachment_by_reference` | 2,3,4 | ref-2/3/4.txt | text/plain | - / - | three `msg.attachment_method_unsupported` |
| `msg_attachment_hostile_name` | 1 | `..\evil/../../x\x00y` | application/octet-stream | 7 / 8f383ccd | none |
| `msg_attachment_zero_size` | 1 | empty.bin | application/octet-stream | 0 / e3b0c442 | none |
| `msg_attachments_4095_4096_4097` | 1 x3 | a/b/c.bin | application/octet-stream | 4095/4096/4097 | none |
| `msg_duplicate_filenames` | 1 x2 | same.txt x2 | text/plain | 5 / 6 | none |

`msg_embedded_message`'s tree digest is `8681c596...`; `msg_embedded_depth_two`'s is
`a943515e...` (both recomputed by an independent canonical walk in the test).

### The three mutations (run, restored, each fails by name)

1. **Read a reference method (2) as by-value** (`if row.method in (1, 2)`) ->
   `tests/test_msg_attachments.py::test_reference_methods_are_recorded_and_dropped_unsupported`
   fails (a spurious `msg.stream_truncated` `attach:0:stream_absent` replaces the unsupported gap).
2. **Take the short name before the long name** (swap the ladder rungs) ->
   `tests/test_msg_attachments.py::test_the_filename_ladder_is_long_over_short_over_display`
   fails (`'S.txt' != 'L.txt'`).
3. **Hash the storage tree without sorting** (drop `under.sort(...)`) ->
   `tests/test_msg_embedded.py::test_the_storage_tree_sha256_is_a_canonical_walk` fails (the
   digest moves to `ba774a37...`).

### The E4 numbers (D8), 40 MiB by-value attachment, 6x budget

| step | peak-WS delta | x stream |
|---|---|---|
| container only | 85,020,672 | 2.03 |
| container + walk | 104,435,712 | 2.49 |
| container + walk + assemble | 129,208,320 | 3.08 |
| with the built `.msg` in the delta | 172,158,976 | 4.10 |

All within the 6x budget. Copy inventory: (1) the `.msg` bytes (the container's input, like a file
on disk), (2) `cfb.read_stream`'s returned payload -- one full copy of the stream, (3)
`raw_bytes()`'s `b"".join(chunks)` -- the virtual message, one more full copy, (4) the span row
holds a **reference** to the payload (no copy), (5) `sha256_hex` retains nothing. The dominant
extra copies are (2) and (3); the lazy `raw_bytes()` view the brief reserves for the owner would
address (3).

### Existing tests edited, and why

- `tests/test_msgcontainer.py` -- **one added test** (the D0.1 fault-gap id fix). No existing line
  touched; `FACT_KEYS` unchanged (the `recipient_count`/`attachment_count` "only when >= 1" rule
  keeps the 1b.5 pin literally true).
- `tests/test_fixture_census.py` -- the `Family G` rows and the `built_in_1b7 == 10` count added.
- `tests/test_turn_declarations.py` -- `BUILT_TURNS` gains `"1b.7"`.
- `tests/support/msg_construction.py` -- the ten `MSG_*` layout tables and their `CONSTRUCTION`
  rows (typed from the built bytes and the [MS-CFB] layout, not from the reader); its hand-edited
  `label_ledger.json` hash was updated in the same change (the ledger's additions-only rule).
- `tools/make_msg_fixtures.py` -- the ten Family G builders and their `FIXTURES` rows.
- `fixtures/msg/SHA256SUMS` -- the ten new lines.
- `tests/ledger/label_ledger.json` -- the `tests/support/msg_construction.py` fingerprint only.
- `docs/design/phase1-turn-declarations.md` / `phase1b-ledgers.md` -- the `turn=1b.7` block
  (declared tests plus the extras) and the allow-list additions.
- `docs/design/msg-architecture.md` -- new section 11 (the layout, the ladder, the digest, the
  embedded header, the facts).
- `docs/design/phase1b-facts.md` -- the one D0.2 sentence.

### Reported, not bent

- **The depth-cap detail form.** The brief's example is `1.2>1` (the occurrence path of the outer
  embed); `msgcontainer._build_attachment_facts` emits `<leaf ordinal>><nested index>` (`2>0`).
  The occurrence path is a walker-layer name not known at the container layer; the emitted form
  names the nested storage by leaf ordinal. A one-line change if the owner wants the path printed
  by 1b.10 instead.
- **"the nested storage's stream bytes were never requested" is not attainable as written.** The
  canonical digest (D4) covers every entry under the embedded storage, so computing it **must**
  read the nested embedded message's streams; the cap stops the *summary* descent, not the digest
  walk. `tests/test_msg_embedded.py::test_no_deeper_embedded_table_is_read` asserts instead that
  `mapi._embedded_table` is called exactly once (the depth-1 summary, no depth-2 descent).
- **`declared_mime` cannot tell defaulted from declared.** For an absent `0x370E`, the attach
  stage reports `declared_mime = application/octet-stream` exactly as for a declared one; only the
  container's `mime_tag = None` distinguishes them (the D2 reason for recording it).
- **`verbatim_reason = container_stream` is a text-stage field.** It lives on `text.py`'s
  `TextRecord` (surfaced in 1b.10's `body.text` rows), not on `PartRecord`; the test asserts the
  observable part: `size_bytes`/`sha256` are the stream's and the span row is `STREAM`/`exact`.
- **`hidden` reaches nothing at the attach stage.** `0x7FFE` has no MIME equivalent; the fact
  records it, the occurrence carries no `hidden` field and the leaf invents no header. The
  declared test name `test_cid_and_hidden_flags_feed_the_attach_stage` is kept, and the test
  documents that only the cid and the `0x3714` inline bit reach the stage.
- **A `phase0-gaps.md` sentence left alone.** `msg.embedded_depth_cap`'s entry says "the cap and
  the declared depth are recorded on the run (D6)"; this turn emits the gap into `container_gaps`
  (persisted by 1b.10) and nothing records a "declared depth" anywhere. No registry sentence is
  wrong enough to edit; reported.
- **`msg_outlook_layout_handbuilt`'s gaps moved.** Its attachment (`0x370B` rendering position)
  now raises `msg.property_tag_unknown` `370b:0003` through the attachment-row mapping (D7), and
  its projection grows the mixed leaf. No test pinned either; both are the turn's intended
  behaviour.

### What Turn 1b.8, 1b.9 and 1b.10 need from this turn

- **1b.8 (RTF):** the attachment layer is method/leaf-complete; the RTF body (`0x1009`) is a body
  stream and stays the 1b.5 surface. An RTF *attachment* would be method 1 and needs nothing new.
- **1b.9 (encodings, the cross-container pair):** `storage_tree_sha256` and the ladder are ready
  for the pair; the C5 extra in this turn is the template (the same message as `.eml`/`.msg`,
  differing only in container kind/hash/facts, the projection-owned headers, and the stream refs).
- **1b.10 (measurers, persistence, the three `msg` components):** `attachment_facts` is the
  hook, exactly as `message_facts` was for 1b.6. It must project the facts into the `msg.attachments`
  sidecar (`phase1b-facts.md`'s shape: `[part, method, filename_raw, filename_decoded, mime_tag,
  cid, hidden, inline, size, sha256]`, one row per occurrence), persist `container_gaps` (the
  attachment gaps included) under `part.gaps`/`gaps.later`, and join each row through the span
  table. The `msg.embedded_summary` / `msg.storage_tree_sha256` facts are the two new value shapes.
  No `.msg` sidecar exists yet (as directed); `evals/labels.py` still accepts `.eml` only.

## Turn 1b.8 -- outcome (the RTF minimum: decompress, check, record; no body view)

One new module (`emailextract/rtf.py`), the test-side compressor (`tests/support/rtf_compress.py`),
the `msgcontainer` wiring (`rtf_facts`, the two gaps), three fixtures and their construction tables
landed in the working tree; this note is its outcome. Full suite: **2170 passed, 2 skipped** on
`python` (3.14.3, 3m45s) and on the repo's 3.11 (3.11.15, 5m58s); the six `--check` tools and
`python -m emailextract.evals` all exit 0.

### D1-D7: the reviewer's decisions, applied (no decision changed)

- **D1 -- `emailextract/rtf.py`, a new pure module.** `mapi.py` is untouched: the decoder needs no
  MAPI helper. `tests/test_phase1_scope.py::EXPECTED_LIBRARY` gains `rtf.py` (line 54) and the import
  probe picks it up by the `pkgutil.walk_packages` sweep (no per-module line). The ledger's allow-list
  line is updated in this same turn.
- **D2 -- the format, typed from [MS-OXRTFCP] 2.1.** See "The specification constants" below: four of
  the five are verified, one (the prebuf tail) is not.
- **D3 -- streaming, output not retained.** `RtfResult` is a frozen dataclass of primitives:
  `comptype`, `stream_length`, `compsize_declared`, `rawsize_declared`, `crc_declared`, `crc_ok`,
  `decompressed_length`, `decompressed_sha256` (`None` on a fault), `fault`. The decoder keeps a
  4096-byte dictionary, a 64 KiB hash buffer, the running sha256 and the length. Nothing is the RTF
  text (the test asserts no decompressed substring reaches `container_facts`).
- **D4 -- bounded work, hostile-safe.** `rtf.decode(data, work=...)` charges the container's
  `cfb.Work` counter one step per output byte; `rtf.work_bound(n) = 16 + 9 * n`. A reference to an
  unwritten dictionary byte is `rtf_dictionary_underrun`; an overlapping reference (offset = write
  position - 1) works byte by byte. The decoder never allocates `RAWSIZE`: a header declaring
  `0xFFFFFFFF` over the committed 226-byte stream faults in 6,738 bytes of `tracemalloc` peak; a
  `COMPSIZE` of `0xFFFFFF` in 544 bytes.
- **D5 -- faults, and how they map (no new ids).** The closed list is
  `rtf_header_short`, `rtf_comptype_unknown`, `rtf_compsize_mismatch`, `rtf_rawsize_mismatch`,
  `rtf_crc_mismatch`, `rtf_data_short`, `rtf_dictionary_underrun`. Each raises the existing
  `msg.stream_truncated` with the detail `0x1009:<fault>` and sets `Status.TRUNCATED` with:
  `declared_length_mismatch` for the header-short, unknown-comptype and two size faults;
  `stream_ended_early` for a bad CRC, a short input and a dictionary underrun. `msg.rtf_to_text_unsupported`
  is emitted whenever a `0x1009` stream is present, faulted or not. The fault-to-reason mapping is a
  choice (an owner question, below).
- **D6 -- no body view; existing projections pinned.** `tests/test_msg_rtf.py` pins the sha256 of
  every existing committed fixture's virtual bytes and asserts none moved (the three new rows are the
  only additions). `msg_rtf_only` projects exactly as a no-body-stream message does in 1b.5 (the
  synthetic `text/plain; charset=us-ascii` scaffold, no leaf body), `body_streams = rtf`;
  `msg_rtf_compressed_body` projects its plain body as in 1b.5 and adds only the record and the gap.
  No `PartRecord`, `BodyView` or selection result derives from the RTF.
- **D7 -- the record lives on `MsgContainer.rtf_facts`.** A frozen `RtfResult` (or `None`), beside
  `message_facts`/`attachment_facts`; not on `EmailDocument`, not in `container_facts` beyond the
  existing `body_streams`, not in `to_json`. Nothing consumes it until 1b.10.

### The specification constants, and where each came from

- **The 16-byte header** (four little-endian `u32`: `COMPSIZE`, `RAWSIZE`, `COMPTYPE`, `CRC`):
  verified structurally and by the round trip; `COMPSIZE == stream_length - 4`, `LZFu == 0x75465A4C`,
  `MELA == 0x414C454D`.
- **The reference layout** (LSB-first control byte of eight flags; clear = one literal; set = a
  2-byte big-endian reference of a 12-bit offset and a 4-bit stored length = length - 2; end marker =
  a reference whose offset equals the write position): verified by hand-typed, byte-by-byte vectors
  -- literals-only `AB`, one non-overlapping reference `ABAB`, one overlapping (run-length) reference
  `AAAAA`, and a marker-off-by-one stream that faults `rtf_rawsize_mismatch`.
- **The CRC**: the specification's table-driven CRC-32 (poly `0xEDB88320`) equals `zlib.crc32` over
  the same bytes (asserted on samples), so the decoder uses `zlib`. It is over the compressed bytes
  after the header.
- **The prebuf and the initial write position -- NOT verified against [MS-OXRTFCP].** There is no copy
  of the specification in the repository and no network in this environment, so the 4096-byte
  dictionary's pre-load could not be typed from the spec text as D2 requires. The first 80 bytes (the
  `{\rtf1\ansi\ansicpg1252\deff0\deflang1033{\fonttbl{\f0\fnil\fcharset0 Calibri;}}` prelude) are
  certain; the tail is the best-known form, and `len(PREBUF)` is **167**, not the brief's **207**. The
  initial write position is set to `len(PREBUF)`, so the decoder is self-consistent and every
  fixture/vector here round-trips, but a *real* `0x1009` stream whose references read the prebuf would
  decode against the wrong bytes. **This is the turn's one unverified constant and the top owner
  question; flagged, never guessed at silently.**
- **A nonzero CRC on a `MELA` stream**: refused as `rtf_crc_mismatch` (the spec says `MELA`'s CRC is
  always 0), which maps to `TRUNCATED`/`stream_ended_early`.

### The fixtures, with their hand-typed expectations

All three are version 3, 512-byte sectors, all-mini, `001A:001F = "IPM.Note"`, a 218-byte `0x007D`
transport stream, and a 226-byte `0x1009` stream (the literal-only compression of a typed
`{\rtf1...\fromtext...}` text, 184 decompressed bytes).

- `msg_rtf_compressed_body`: `0x1000` (64 bytes) + `0x1009`; `body_streams = plain+rtf`; one gap
  (`msg.rtf_to_text_unsupported`); `rtf_facts.fault is None`.
- `msg_rtf_only`: `0x1009` only; `body_streams = rtf`; one gap; no body leaf.
- `msg_rtf_bad_crc`: the same layout as `msg_rtf_only` with the CRC field inverted; `TRUNCATED`/
  `stream_ended_early`; gaps `msg.stream_truncated` `0x1009:rtf_crc_mismatch` and
  `msg.rtf_to_text_unsupported`.

The `MELA` form and the hostile shapes are built in-memory in the tests
(`tools/make_msg_fixtures.rtf_message`), never committed.

### Numbers

- **Maximal expansion**: a 155-byte stream of `0xFF` references expands to 1,088 bytes (7.02x, under
  the 9x `work_bound`); `work.steps == decompressed_length` exactly.
- **Hostile header**: `RAWSIZE = 0xFFFFFFFF` faults (`rtf_rawsize_mismatch`) in a 6,738-byte
  `tracemalloc` peak; `COMPSIZE = 0xFFFFFF` faults (`rtf_compsize_mismatch`) in 544 bytes.
- **Memory**: the decoder's own peak on an 8 MiB stream is 75,378 bytes -- it retains no output. A
  40 MiB stream reads once: peak 98,524,797 bytes over a 47,185,939-byte stream = **2.09x** (the
  container's own copy of the stream dominates; the decoder adds a bounded buffer).
- **The three mutations** (each run, restored, and re-run green): (1) skip the CRC check -- fails
  `test_lzfu_decompresses_and_checks_the_header_size_and_crc`,
  `test_a_bad_crc_is_a_truncated_stream`, `test_each_fault_is_named_with_its_reason_and_gap`;
  (2) treat an unwritten dictionary byte as zero -- fails
  `test_each_fault_is_named_with_its_reason_and_gap`; (3) emit `msg.rtf_to_text_unsupported` only when
  the RTF decodes cleanly -- fails `test_rtf_to_text_unsupported_is_emitted`,
  `test_each_fault_is_named_with_its_reason_and_gap`, `test_zero_and_short_rtf_streams`.

### Existing tests edited, and why

- `tests/support/msg_construction.py` -- the three `MSG_RTF_*` construction tables added (allowed by
  the brief; `tests/ledger/label_ledger.json` records the new fingerprint in the same turn, an
  allow-listed change).
- `tests/test_phase1_scope.py` -- `EXPECTED_LIBRARY` gains `rtf.py`.
- `tests/test_fixture_census.py` -- the `built_in_1b8 == 3` set added.
- `tests/test_turn_declarations.py` -- `BUILT_TURNS` gains `"1b.8"`.
- `tests/msg_fixtures.py` / no other existing test was edited; no fixture count or `body_streams`
  value moved.
- `tests/ledger/label_ledger.json` -- `tests/support/rtf_compress.py` appended and
  `tests/support/msg_construction.py` re-recorded (both named in the allow-list).

### Owner questions

1. **The prebuf (above)** -- the specification's 207-byte pre-load could not be verified offline; the
   decoder ships the best-known 167-byte form. Confirm the exact bytes (and the write position) from
   [MS-OXRTFCP] 2.1, or accept the risk for real mail.
2. **The fault-to-`Status` reason mapping** (D5): a size or comptype mismatch as
   `declared_length_mismatch` is a reading, not a measured fact.
3. **Whether RTF de-encapsulation ever comes back** (O2 cut it): an HTML-in-RTF body would then become
   a real body view.
4. **Probe P1/P5 on real mail**: `0x1009` prevalence is still evidenced by one spike file.

### A deviation to report

The brief's memory test asks for the 40 MiB stream **through the pipeline under `tracemalloc`**. That
run costs ~65s on this machine (a `tracemalloc` accounting artifact: the *same* decode work, wrapping
the container, is ~4x the standalone cost, and ~5.8s without `tracemalloc`), so the pipeline
measurement is taken on the brief's 40 MiB stream while the decoder-only (scale-invariant) peak is
measured on an 8 MiB stream. The pipeline multiple, 2.09x, is reported above.

## Turn 1b.8 -- fix (reviewer correction, 2026-10-14): the prebuf and the CRC were both wrong

The 1b.8 note above shipped two constants it could not verify offline. The reviewer had network
access, checked the format against a public independent implementation (`delimitry/compressed_rtf`,
its `INIT_DICT` and README examples) and found **both wrong**; this subsection is the fix. Nothing
else in the turn changed: `emailextract/msgcontainer.py` is untouched, the shape of the record is the
same (plus one field), and no decision (D1-D7) moved.

### The two constants: old value, new value, and why a round trip could never have seen it

| constant | old (wrong) | new (the specification's) |
| --- | --- | --- |
| `PREBUF` | 167 bytes, `sha256 3e8ff567a8a531364af81b6a515411ec32b3585139c1cdca56c29c18edd5ff2b` | **207** bytes, `sha256 64949fe166f29da3ab21d1739247557565795c7cfed9227f377e890ce5cfa92d` |
| the CRC | `zlib.crc32` (init `0xFFFFFFFF`, final XOR) | the raw table-driven CRC-32 (init `0`, **no** final XOR) |

The 167-byte text was not a prefix of the real pre-load (an Outlook-generated RTF header, not the
prebuf), so the module docstring's "the first 80 bytes are certain" was itself false. Every real
Outlook `LZFu` stream references the prebuf, so a real stream decoded to wrong bytes or faulted. And
because `zlib.crc32` differs from the raw form on every non-empty input, **every real `LZFu` stream
would have raised `rtf_crc_mismatch` and truncated its document**.

Neither was visible to the 2111+ round-trip assertions: `tests/support/rtf_compress.py` carried its
own copy of the same wrong `PREBUF` and the same wrong CRC, so encode-then-decode agreed with itself
whatever the constants were. The tell the fix adds is that `rtf_compress` now **imports the constants
from exactly one place** (`emailextract/rtf.py`) and two **real** streams are asserted against
:func:`emailextract.rtf.decode` **alone**, with no encoder in the loop. The two real streams were
decoded first in a throwaway script before any code was changed, and the 207-byte prebuf needed **no
space fill** -- every reference reads a byte the prebuf actually holds, so the module's stricter
`rtf_dictionary_underrun` rule (below) never fired on real data.

### How the corrected decoder handles each real vector

Both are one-line `bytes` literals in `tests/test_msg_rtf.py`, provenance in the comment.

- **`REAL_LZFU_STREAM`** (39 bytes, from the reference README): header `COMPSIZE` 35, `RAWSIZE` 34,
  `LZFu`, stored `CRC 0x74E85C33`. `rtf.crc32(payload)` equals the stored CRC; the decompression
  reads prebuf slots `0-11, 121-122, 175-179` and produces exactly the 34 bytes
  `{\rtf1\ansi\ansicpg1252\pard test}` (`decompressed_length` 34, `crc_kind` `"payload"`). Through a
  built `.msg` the document is `PARSED`, `msg.rtf_to_text_unsupported` is present, no
  `msg.stream_truncated`, and `rtf_facts` carries the 34 bytes' length and sha256.
- **`REAL_MELA_STREAM`** (50 bytes): header `COMPSIZE` 46, `RAWSIZE` 34, `MELA`, stored
  `CRC 0xCE12DF20`, which **is** the payload's raw-table CRC. Accepted (`crc_kind` `"payload"`), same
  34 bytes and the same `PARSED` document shape as the `LZFu` vector.

### The `MELA` CRC rule (a reading, and an owner question)

[MS-OXRTFCP] says an uncompressed stream's CRC is `0`. The reference writer stores the payload's raw
CRC instead. Rather than guess, a `MELA` stream is now accepted when its CRC field is **either** `0`
**or** equal to `rtf.crc32(payload)`, and `rtf_facts.crc_kind` records which: `"zero"`, `"payload"`,
or `"none"` (no CRC checked, or the check failed -- a plain-data `str`, added to `RtfResult` after
`crc_ok`). Any other value is still `rtf_crc_mismatch`. This is a **leniency chosen because the
format's own reference writer produces the second form**; it is a reading, not a measured fact, and
the top owner question for this fix.

### Which tests were re-derived, and how

The reviewer's rule is that a hand-built literal which now disagrees with the code is a **finding**,
not a value to patch; each surviving literal was re-derived by hand from `INITIAL_WRITE_POSITION` = 207
and left as typed bytes so a disagreement fails:

- `test_hand_typed_vectors_decode_byte_for_byte` is now typed in bytes with the arithmetic in the
  comment: vector 1 marker `(207 + 2) << 4 = 0x0D10`; vector 2 reference `(207 << 4) | 0 = 0x0CF0`
  and marker `(211 << 4) = 0x0D30`; vector 3 reference `(207 << 4) | 2 = 0x0CF2` and marker
  `(212 << 4) = 0x0D40`; vector 4 (marker one short) `(208 << 4) = 0x0D00`. It also asserts
  `INITIAL_WRITE_POSITION == 207` so the derivations cannot silently float.
- Every other hand-built vector derives its offsets from `rtf.INITIAL_WRITE_POSITION` symbolically
  (the maximal-expansion, dictionary-underrun and literal-stream helpers), so 207 flows through
  without a typed literal to re-derive.
- `_lzfu_header` now stamps `rtf.crc32(payload)`, not `zlib.crc32`.
- `test_the_decoder_and_compressor_agree_on_the_constants` asserts **identity** (the compressor
  imports the constants) and that the CRC is the raw form, **not** `zlib.crc32`, on every non-empty
  sample.
- `test_mela_uncompressed_is_accepted` gained the `"zero"` and `"payload"` acceptance cases and the
  `crc_kind` assertions.
- Four new tests: the prebuf (`len`, first 40, last 20, the CR LF pair and the whole sha256 typed in
  the test), the CRC (`0x74E85C33` is the raw CRC and differs from `zlib`'s `0x06487877`; a second,
  different check value `rtf.crc32(b"123456789") == 0x2DFD2D88` against `zlib`'s `0xCBF43926`), and
  the two real vectors through `rtf.decode` and (again) through a built `.msg`.

### The rebuilt artifacts

The three committed fixtures changed only in their `0x1009` stream (the CRC field and the end-marker
bytes); the stream stays 226 bytes, so the CFB layout and `tests/support/msg_construction.py`'s
construction tables are unchanged. `fixtures/msg/SHA256SUMS` re-recorded the three lines:

```
fc76d1d4b0d27708dbc3b5e541ebfcbcff682507cb52eeddfdfcc9d995d0bc89  msg_rtf_compressed_body.msg
1817fa620742a2b12f878acccd5179c7f78c563ce79e1e5b09316db38dd2a6b2  msg_rtf_only.msg
1ac4d9dd38f0646d518f456a1dc3892cbd4e3afd17429036c64ccf06fca0543d  msg_rtf_bad_crc.msg
```

`msg_rtf_bad_crc` flips every bit of the header CRC **of the corrected raw CRC**, so it stays a
stream whose CRC is wrong under the corrected definition. `tests/ledger/label_ledger.json` re-recorded
the one changed covered file (`tests/support/rtf_compress.py`; `tests/support/msg_construction.py` is
byte-identical, so it is untouched). The four new test ids were added to the `turn=1b.8` declaration
block.

### The four mutations (each run, restored, and re-run green)

1. **Skip the CRC check** (`crc_ok = True`) -- fails
   `test_lzfu_decompresses_and_checks_the_header_size_and_crc`, `test_a_bad_crc_is_a_truncated_stream`,
   `test_each_fault_is_named_with_its_reason_and_gap`.
2. **Treat an unwritten dictionary byte as zero** -- fails
   `test_each_fault_is_named_with_its_reason_and_gap`.
3. **Emit `msg.rtf_to_text_unsupported` only when the RTF decodes cleanly** -- fails
   `test_rtf_to_text_unsupported_is_emitted`, `test_each_fault_is_named_with_its_reason_and_gap`,
   `test_zero_and_short_rtf_streams`.
4. **(new) change one byte of `PREBUF`** (slot 0, `{` -> `X`, length unchanged) -- fails
   `test_the_prebuf_is_the_207_byte_text_of_the_specification` and
   `test_a_real_lzfu_vector_decodes_exactly`.

### Owner questions (the fix's two)

1. **The `MELA` CRC leniency** (above): accept `0`, or the payload's raw CRC, or only `0`? Chosen to
   accept both, because the format's own reference writer produces the second form.
2. **The dictionary's unwritten-byte rule versus the reference's space fill.** This package treats a
   reference to a not-yet-written dictionary byte as the fault `rtf_dictionary_underrun`; the reference
   implementation fills the rest of the 4096-byte dictionary with spaces. The real vectors above never
   need the fill, so the stricter rule stands -- but a real stream that does read the tail would fault
   here where the reference returns spaces.

### Green after the fix

Full suite **2174 passed, 2 skipped** on `python` (3.14.3, 4m00s) and on the repo's 3.11 (3.11.15,
5m29s) -- the four new tests are the only addition. `make_msg_fixtures --check`, `make_fixtures
--check`, `update_eml_golden --check`, `update_behavior_ledger --check`, `update_label_ledger --check`
and `python -m emailextract.evals` all exit 0. Not committed; 1b.9 not started.

## Turn 1b.9 -- outcome (the cross-container pair, the Outlook-layout proof, the encodings)

No new architecture: three proofs over code that already existed, plus **one defect the non-BMP
fixture exposed**. Full suite **2190 passed, 2 skipped** (16 new test functions over the 1b.8 fix
baseline's 2174) on both `python` (3.14.3, 3m44s) and the repo's 3.11 (3.11.15, 5m22s). All five
`--check` tools (`make_msg_fixtures`, `make_fixtures`, `update_eml_golden`,
`update_behavior_ledger`, `update_label_ledger`) and `python -m emailextract.evals` exit 0 on both.

### D1-D10: the reviewer's decisions, applied

- **D1 -- the pair's `.eml` is built in the test, not committed.** Only `fixtures/msg/pair_gmail_reply.msg`
  is committed; the `.eml` half is `tests/support/msg_construction.pair_eml_bytes()`, built from the
  **same** `PAIR_HEADERS`/`PAIR_PLAIN_TEXT`/`PAIR_HTML_BODY` the generator builds the `.msg` from, so
  `update_eml_golden --check`, the behavior ledger and `tests/ledger/corpus.json` are untouched. The
  owner alternative (commit the `.eml` and absorb the corpus-version + golden churn in 1b.10) stands.
- **D2 -- the pair's message and "equal".** `.eml` = `multipart/alternative` (plain + HTML); `.msg` =
  `IPM.Note` with `0x007D` (the same original headers) and a `0x1013` HTML body of the **same HTML**,
  no plain stream. The expected `body_digest` is `hashlib.sha256(PAIR_HTML_TEXT.encode("utf-8"))`
  computed **in the test**, independent of `_content_fingerprint`.
- **D3 -- one document shape modulo a hand-typed allow-list.** The test walks every dataclass field,
  asserts each difference is in `ALLOWED_DOCUMENT_FIELDS`/`ALLOWED_PART_FIELDS` with its reason, and
  asserts the plain part exists only on the `.eml` side as a named difference.
- **D4 -- "no candidate".** A plain-only `.eml` against an HTML-only `.msg` of the same words: the
  `body_digest_view`s differ (`PLAIN`/`HTML`) and the two `ContentFingerprint`s are **not equal** even
  though the text is. No candidate objects are built (the axis is not built in Phase 1b).
- **D5 -- never dedupe on the raw hash.** Both halves ingested into one store: two documents, two
  `container_hash`es, equal `body_digest`, no merge, no cross-reference, and re-ingesting either is
  byte-for-byte a no-op (`store.store_snapshot` before/after).
- **D6/D7/D8/D9/D10** -- the layout proof, the rung matrix, the Family H fixtures, the header shapes
  and the two hostile UTF-16 shapes, below.

### The fixtures (11 new committed `.msg`, no sidecar)

Ten Family H: `msg_string8_1252`, `msg_string8_ascii20127`, `msg_string8_utf8_65001`,
`msg_string8_message_cpid`, `msg_string8_ascii_no_cp`, `msg_string8_utf8_no_cp`,
`msg_string8_windows_1252_no_cp` (the five ladder rungs, each a committed file), `msg_string8_body`
(a `0x1000:001E` plain body), `msg_non_bmp_text` (a `001F` subject with an astral emoji) and
`msg_multivalued_strings` (a `0037:101F` entry with three `-NNNNNNNN` streams). Plus
`pair_gmail_reply.msg`. Every construction table is typed in `tests/support/msg_construction.py`
**before** the generator runs; `tools/make_msg_fixtures.py` and `fixtures/msg/SHA256SUMS` follow.

### The tests (3 new files, 16 functions)

- `tests/test_msg_cross_container.py` (5): the three declared pair tests, D5 (never dedupe) and the
  pair's determinism of both `container_hash`es and digests under two `PYTHONHASHSEED` values.
- `tests/test_msg_outlook_layout.py` (2): the fixture's layout equals the hand-typed construction
  table, read through **both** `cfb.py` and `olefile`; and its distinguishing properties are pinned to
  the B1-B4 observation each cites.
- `tests/test_msg_encodings.py` (9): the four declared tests, the five-rung matrix, the multi-valued
  values, the `001E` body through the walker, the two hostile UTF-16 shapes through the container, and
  the seeded fuzz (225 mutants, 5 of the new fixtures, `produced > 150`).

### The one code fix (a finding)

`MsgContainer._transport_rows` computed a line's source byte span as `2 * len(line)`. On a UTF-16LE
transport stream a **non-BMP** code point is two code units, so that is two bytes short per astral
character and shifts every later line's `source_byte_offset`. `msg_non_bmp_text` exposed it; the fix
encodes the line to UTF-16LE and uses its real length with a running cursor. `mapi.py` was **not**
changed (the block allow-lists it, but no test demanded an edit).

### Reported, not bent

- **The D7 catalogue contradiction.** `msg_string8_ascii20127` said `(ascii)` and
  `msg_string8_utf8_65001` said `(utf8_strict)`, but a fixture whose **internet** code page is 20127 or
  65001 fires the `internet_cpid` rung; `ascii`/`utf8_strict` fire only with no usable code page. The
  rung column is corrected in `phase1b-fixtures.md`, and the three new no-code-page variants carry the
  `ascii`/`utf8_strict`/`windows_1252` rungs, so all five are committed.
- **The Outlook-layout "not writer defaults" is about the declaration, not the CFB scaffold.** The
  fixture **shares** the writer's layout arithmetic (19 sectors, no tail slack, every non-root stream
  mini-resident) -- the test states these rather than hiding them; what distinguishes it is the
  `__nameid_version1.0`/`__recip_version1.0_#00000000`/`__attach_version1.0_#00000000` storages, the
  `1/1` top-level counts (the default is `0/0`) and the sub-tables.
- **D10's lone-surrogate/odd-length shapes are built in the test**, not committed (a same-length byte
  patch cannot produce the odd-length shape), through the same test-side writer
  `tests/test_mapi_hostile.py` uses. Both go through `MsgContainer` + `assemble`: no exception, the
  fault is recorded (`mapi.FAULT_UTF16_LONE_SURROGATE`/`FAULT_UTF16_ODD_LENGTH`), no replacement
  character, and every published string is UTF-8 encodable.
- **A line-ending fix on `tests/support/msg_construction.py` and `fixtures/msg/SHA256SUMS`.** The
  prior session wrote both with CRLF (a Windows `write_text` artifact). `.gitattributes` pins
  `* text=auto eol=lf`, so git would normalise them to LF at commit while the label ledger recorded
  the **CRLF** hash -- `update_label_ledger --check` would then fail on the release job's LF checkout.
  Both files are now LF and `msg_construction.py`'s ledger fingerprint is re-recorded over the LF
  bytes, so the committed blob and the recorded hash agree.

### Mutations (each run, restored, reported)

1. `assemble._content_fingerprint` over `raw` instead of the view's code points ->
   `test_the_pair_has_different_container_hash_and_equal_body_digest`,
   `test_the_pair_is_one_document_shape_modulo_d14`,
   `test_the_pair_with_a_plain_only_view_is_no_candidate`,
   `test_the_pair_is_never_deduped_by_raw_hash` (4 fail).
2. `mapi.decode_unicode` with `errors="surrogatepass"` ->
   `test_the_two_hostile_utf16_shapes_go_through_the_container` and
   `tests/test_mapi_hostile.py::test_a_lone_surrogate_is_recorded_not_raised` (2 fail).
3. Swap the internet/message code page precedence in `mapi.decode_string8` ->
   `test_001e_code_pages_1252_20127_28591_65001`,
   `test_internet_versus_message_codepage_disagreement`,
   `test_all_five_rungs_are_covered_by_a_committed_msg`,
   `test_a_string8_body_projects_as_utf8_with_the_ladder_rung` (4 fail).

### Files changed (all on the allow-list)

New: `tests/test_msg_cross_container.py`, `tests/test_msg_outlook_layout.py`,
`tests/test_msg_encodings.py`, 11 `fixtures/msg/*.msg`.
Edited: `emailextract/msgcontainer.py` (the one fix), `tools/make_msg_fixtures.py`,
`tests/support/msg_construction.py`, `tests/test_fixture_census.py` (`built_in_1b9`),
`tests/test_turn_declarations.py` (`BUILT_TURNS += "1b.9"`), `tests/ledger/label_ledger.json`
(`msg_construction.py`'s fingerprint), `fixtures/msg/SHA256SUMS`,
`docs/design/phase1-turn-declarations.md` (the `declaration turn=1b.9` block),
`docs/design/phase1b-fixtures.md` (the D7 corrections + the D1 pair note),
`docs/design/msg-architecture.md` (the pair + layout + encodings section),
`docs/design/phase1b-ledgers.md` (the declaration block + the allow-list line, this note).
Unchanged/untouched: `mapi.py`, `assemble.py`, `cfb.py`, `walk.py`, `model.py`, `versions.py`,
`behavior_ledger.json`, `tests/ledger/corpus.json`, the `.eml` golden, `docs/design/phase0-gaps.md`,
`tests/test_phase1_scope.py`.

### Owner questions

1. Commit the pair's `.eml` (D1)? The default keeps it in the test; committing it moves the `.eml`
   golden and the corpus version, which 1b.10 would absorb.
2. `msg_string8_message_cpid` uses internet cp `437` as its unresolvable internet code page -- 437 is a
   real code page that is simply **not** in `CODEPAGES` (`{1252, 20127, 28591, 65001}`); if the owner
   widens `CODEPAGES` this fixture's rung changes.
3. The `MELA` CRC leniency and the dictionary's unwritten-byte rule (1b.8 fix note) -- still open.
