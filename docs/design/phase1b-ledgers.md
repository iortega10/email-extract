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
  artifact moved by only the `output_schema_version` value plus one `"stream_ref": null` per
  `PartRecord`/`HeaderField`; the store keys/paths that name `OUTPUT_SCHEMA_VERSION` moved by that version string;
  every other pinned value byte-identical).
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

```declaration turn=1b.1
module: emailextract/model.py
module: emailextract/versions.py
module: emailextract/ids.py
module: emailextract/walk.py
module: emailextract/text.py
module: emailextract/assemble.py
module: emailextract/parse.py
module: emailextract/store.py
module: tests/support/fake_msg_container.py
module: tests/golden/eml_golden.json
module: tests/test_contract_msg.py
module: tests/test_provenance_points.py
test: tests/test_contract_msg.py::test_container_stream_ref_shape_and_round_trip
test: tests/test_contract_msg.py::test_container_stream_ref_invariants_raise
test: tests/test_contract_msg.py::test_a_synthetic_ref_carries_no_offsets
test: tests/test_contract_msg.py::test_embedded_summary_shape_and_defaults
test: tests/test_contract_msg.py::test_the_cfb_cap_reasons_join_the_skipped_row
test: tests/test_contract_msg.py::test_named_error_reasons_drop_cfb_msg_unsupported
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
test: tests/test_provenance_points.py::test_parse_opens_a_cfb_container_instead_of_refusing
test: tests/test_provenance_points.py::test_the_eml_default_branch_is_unchanged
test: tests/test_provenance_points.py::test_the_value_codec_seam_defaults_to_latin_1
test: tests/test_provenance_points.py::test_walk_msg_matches_walk_of_the_equivalent_eml_modulo_provenance
stop: after the golden re-check (the bump and the eight provenance points green against FakeMsgContainer)
```

Allow-list (`turn=1b.1`): the eight `emailextract/` modules above, `tests/support/fake_msg_container.py`,
`tests/golden/eml_golden.json`, `tests/test_contract_msg.py`, `tests/test_provenance_points.py`,
`tests/test_eml_golden.py`, `tests/test_status_reasons.py`, `tests/test_contract_phase1.py`,
`tests/test_parse_entry.py`, `tests/test_contracts.py`, `tests/test_closed_enums.py`, `tests/test_container.py`,
`tests/test_assemble.py`, `tests/test_store.py`, `tests/test_ingest.py`, `tests/test_phase1_scope.py`,
`tests/test_behavior_ledger.py`, `tests/ledger/behavior_ledger.json`, `docs/design/phase1b-ledgers.md`.
Those test paths are the category-(1)/(2)/(3) edits of `phase1b-contract.md` section 11.

```declaration turn=1b.2
module: tools/cfb_writer.py
module: tools/make_msg_fixtures.py
module: tests/support/olefile_oracle.py
module: tests/test_msg_fixtures.py
module: tests/test_olefile_oracle.py
test: tests/test_msg_fixtures.py::test_the_writer_output_is_frozen_by_sha256
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
`tests/support/olefile_oracle.py`, `tests/test_msg_fixtures.py`, `tests/test_olefile_oracle.py`,
`tests/ledger/label_ledger.json`, `tests/ledger/corpus.json`, `tests/test_fixture_census.py`,
`pyproject.toml`, `NOTICE`, `docs/design/phase1b-ledgers.md`.

```declaration turn=1b.3
module: emailextract/cfb.py
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
test: tests/test_cfb_hostile.py::test_a_fat_cycle_is_one_streams_fault
test: tests/test_cfb_hostile.py::test_a_directory_loop_is_a_named_error
test: tests/test_cfb_hostile.py::test_an_unsupported_header_is_a_named_error
test: tests/test_cfb_hostile.py::test_magic_without_properties_is_not_a_message
test: tests/test_cfb_hostile.py::test_the_extended_difat_is_read_through_and_flagged
test: tests/test_cfb_fuzz.py::test_every_mutant_returns_a_closed_failure_or_the_same_document
test: tests/test_cfb_fuzz.py::test_the_work_per_byte_budget_holds
test: tests/test_sector_accounting.py::test_the_eight_classes_sum_to_the_file_length
test: tests/test_sector_accounting.py::test_free_and_slack_are_explicit
test: tests/test_sector_accounting.py::test_a_cyclic_chain_is_visible_as_unaccounted
stop: after the hostile set and the seeded fuzz, before MAPI
```

Allow-list (`turn=1b.3`): `emailextract/cfb.py`, `emailextract/versions.py`, `fixtures/msg/`,
`tests/test_cfb.py`, `tests/test_cfb_hostile.py`, `tests/test_cfb_fuzz.py`, `tests/test_sector_accounting.py`,
`tests/support/olefile_oracle.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`.

```declaration turn=1b.4
module: emailextract/mapi.py
module: tests/test_mapi.py
module: tests/test_mapi_ladder.py
module: tests/test_mapi_hostile.py
test: tests/test_mapi.py::test_property_tables_use_the_32_and_8_byte_headers
test: tests/test_mapi.py::test_entry_decode_fixed_variable_and_storage_backed
test: tests/test_mapi.py::test_the_class_gate_records_the_class_verbatim
test: tests/test_mapi.py::test_named_properties_are_recognised_not_resolved
test: tests/test_mapi.py::test_recipients_are_read_from_the_recipient_tables
test: tests/test_mapi.py::test_an_unknown_tag_is_hex_only
test: tests/test_mapi_ladder.py::test_the_ladder_reads_both_code_pages_as_fixed_entries
test: tests/test_mapi_ladder.py::test_internet_cpid_wins_over_message_cpid
test: tests/test_mapi_ladder.py::test_the_trailing_nul_is_stripped_and_recorded
test: tests/test_mapi_ladder.py::test_001e_goes_through_the_ladder_and_001f_is_utf16le
test: tests/test_mapi_ladder.py::test_ascii_and_utf8_rungs_record_their_source
test: tests/test_mapi_ladder.py::test_multivalued_strings_keep_every_value
test: tests/test_mapi_hostile.py::test_a_lone_surrogate_is_recorded_not_raised
test: tests/test_mapi_hostile.py::test_an_odd_length_utf16_stream_is_recorded_not_raised
test: tests/test_mapi_hostile.py::test_a_recipient_count_mismatch_is_recorded
stop: after the ladder, the class gate and the recipients, before the container
```

Allow-list (`turn=1b.4`): `emailextract/mapi.py`, `emailextract/versions.py`, `fixtures/msg/`,
`tests/test_mapi.py`, `tests/test_mapi_ladder.py`, `tests/test_mapi_hostile.py`, `tests/ledger/label_ledger.json`,
`docs/design/phase1b-ledgers.md`.

```declaration turn=1b.5
module: emailextract/msgcontainer.py
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
stop: after the message-level facts and the time facts
```

Allow-list (`turn=1b.6`): `emailextract/msgcontainer.py`, `emailextract/assemble.py`,
`tests/test_msg_message_facts.py`, `tests/test_msg_recipients.py`, `tests/test_msg_time.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`.

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
stop: after attachments and the embedded summary
```

Allow-list (`turn=1b.7`): `emailextract/mapi.py`, `emailextract/msgcontainer.py`, `emailextract/attach.py`,
`fixtures/msg/`, `tests/test_msg_attachments.py`, `tests/test_msg_embedded.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`.

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
`tests/test_msg_rtf.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`.

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
stop: after the cross-container pair, the Outlook layout and the encodings
```

Allow-list (`turn=1b.9`): `emailextract/msgcontainer.py`, `emailextract/mapi.py`, `fixtures/msg/`,
`tests/test_msg_cross_container.py`, `tests/test_msg_outlook_layout.py`, `tests/test_msg_encodings.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`.

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
