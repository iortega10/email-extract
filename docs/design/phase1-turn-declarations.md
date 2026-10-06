# Phase 1 turn declarations (Turn 1.0a specification)

Every Phase 1 turn declares, **before it runs**, the modules it will create or change and the **new test
function names** it will add, and a collection test asserts the declaration
(`docs/design/phase1-ledgers.md`, section (e)). This document holds those declarations. The format is the
machine-readable one: one fenced block per turn, `module:` / `test:` / `stop:` lines, plus an allow-list
block (section (d)).

**Turns 1.0b, 1.0c and 1.0d are exact** -- they run immediately after this document and their prompts
will not change what is declared here. **Turns 1.1 to 1.10 are a first declaration**: each turn's own
prompt **may refine** the list (split a module, rename a test) as long as the refinement is declared in
that prompt and the collection test still passes. The refinement is expected for 1.6/1.7 (the quote
turns), where the owner's catalogue review can move a rule between the text and DOM families.

Every turn below is **owner-committed before the next** ("owner commit: yes"); Turn 1.0c is committed
**per family** (three commits). No turn commits itself.

## Turn 1.0b -- contract plus oracle declarations

```declaration turn=1.0b
module: emailextract/ids.py
module: emailextract/versions.py
module: emailextract/model.py
module: emailextract/walk.py
module: emailextract/evals/l1.py
module: emailextract/evals/labels.py
module: tools/runboth.py
module: tools/update_label_ledger.py
module: tests/ledger/label_ledger.json
module: tests/ledger/facts_ledger.json
test: tests/test_contract_axes.py::test_axis_field_requires_its_value_field
test: tests/test_contract_axes.py::test_phase1_status_is_none_iff_the_axis_is_not_built
test: tests/test_contract_axes.py::test_built_status_carries_the_built_axis_marker
test: tests/test_contract_axes.py::test_an_impossible_axis_pair_raises
test: tests/test_contract_axes.py::test_not_built_in_phase1_is_registered_and_the_axis_ids_are_closed
test: tests/test_type_verdicts.py::test_each_verdict_is_a_tri_value
test: tests/test_type_verdicts.py::test_unrecognized_is_a_value_not_unknown
test: tests/test_type_verdicts.py::test_disagreement_needs_two_families
test: tests/test_type_verdicts.py::test_unknown_iff_no_family_and_magic_wins
test: tests/test_contract_phase1.py::test_quote_boundary_and_view_level_records_freeze
test: tests/test_contract_phase1.py::test_run_record_carries_every_cap_and_the_two_new_reasons
test: tests/test_contract_phase1.py::test_output_schema_version_is_four
test: tests/test_label_ledger.py::test_every_covered_path_is_recorded
test: tests/test_label_ledger.py::test_a_changed_label_is_refused
test: tests/test_label_ledger.py::test_a_removed_label_is_refused
test: tests/test_label_ledger.py::test_an_unrecorded_label_is_refused
test: tests/test_facts_ledger.py::test_the_phase1_fact_ids_match_the_ledger
test: tests/test_facts_ledger.py::test_a_moved_fact_phase_fails_the_ledger
test: tests/test_facts_ledger.py::test_the_deferred_set_is_closed_and_empty
test: tests/test_label_leak.py::test_no_package_file_names_a_fixture_path_or_filename
test: tests/test_turn_declarations.py::test_every_declared_test_is_collected
test: tests/test_turn_declarations.py::test_every_undeclared_test_fails_the_declaration
test: tests/test_benign_flag.py::test_the_benign_reason_ids_are_closed
test: tests/test_benign_flag.py::test_an_unknown_benign_reason_is_a_label_error
test: tests/test_runboth.py::test_runboth_runs_under_both_interpreters_and_reports_the_pair
stop: after the contract and the FACTS declarations are frozen (before any fixtures turn)
```

Allow-list (`turn=1.0b`): `emailextract/ids.py`, `emailextract/versions.py`, `emailextract/model.py`,
`emailextract/walk.py`, `emailextract/evals/l1.py`, `emailextract/evals/labels.py`, `tools/`,
`tests/ledger/`, `tests/test_contract_axes.py`, `tests/test_type_verdicts.py`,
`tests/test_contract_phase1.py`, `tests/test_label_ledger.py`, `tests/test_facts_ledger.py`,
`tests/test_label_leak.py`, `tests/test_turn_declarations.py`, `tests/test_benign_flag.py`,
`tests/test_runboth.py`, `docs/design/phase1-turn-declarations.md`. **Not** `fixtures/**` or
`*.expected.json` (1.0b writes no label).

**Turn 1.0b measures nothing** (its results are declarations and the two ledgers); there is no empirical
result to record.

## Turn 1.0c -- fixtures and hand-typed sidecars, by family

**Three commits, one per family** (`docs/design/phase1-fixtures.md`); each family is at most 30 pairs and
its tests are the family's loader check. The declaration is **split into three blocks -- 1.0c-A, 1.0c-B and
1.0c-C -- so a commit that lands one family can be checked on its own**; the **owner commit point is per
family**. The two later blocks carry a `pending:` line until their family lands: the declaration test
(`tests/test_turn_declarations.py`) honours it by not requiring a pending turn's declared tests to be
collected (they do not exist yet) and by not requiring its declared modules to exist. The `pending:` line is
removed by the commit that lands that family, which also adds the family's structure tests to its block.

```declaration turn=1.0c-A
module: tools/make_fixtures.py
module: tools/write_raw_fixtures.py
module: fixtures/generated/
module: fixtures/raw/
module: tests/ledger/label_ledger.json
test: tests/test_fixture_census.py::test_every_design_phase1_fixture_is_in_the_catalogue
test: tests/test_fixture_census.py::test_every_catalogue_row_has_a_committed_fixture
test: tests/test_phase1_family_a.py::test_the_headers_family_labels_load_and_are_ledgered
test: tests/test_phase1_family_a.py::test_every_family_a_fact_id_is_declared
test: tests/test_phase1_family_a.py::test_every_typed_span_slices_the_fixture_bytes
test: tests/test_phase1_family_a.py::test_every_family_a_gap_id_is_a_known_id
test: tests/test_phase1_family_a.py::test_the_family_meets_the_facts_the_catalogue_names
test: tests/test_phase1_family_a.py::test_the_new_fact_shapes_are_well_formed
test: tests/test_phase1_family_a.py::test_the_span_check_fails_on_a_planted_wrong_span
test: tests/test_phase1_family_a.py::test_the_coverage_check_fails_on_a_missing_fact
stop: after the headers, date and address family (commit 1 of 3)
```

Allow-list (`turn=1.0c-A`): `fixtures/generated/`, `fixtures/raw/` (`SHA256SUMS` appended only),
`tools/make_fixtures.py`, `tools/write_raw_fixtures.py`, `tests/ledger/label_ledger.json`,
`tests/test_fixture_census.py`, `tests/test_phase1_family_a.py`, `docs/design/phase1-turn-declarations.md`.
The `fixtures/**` and `*.expected.json` paths are **only** allowed in the three 1.0c commits and in no later
turn.

```declaration turn=1.0c-B
module: tools/make_fixtures.py
module: tools/write_raw_fixtures.py
module: fixtures/generated/
module: fixtures/raw/
module: tests/ledger/label_ledger.json
test: tests/test_phase1_family_b.py::test_the_body_family_labels_load_and_are_ledgered
test: tests/test_phase1_family_b.py::test_every_family_b_fact_id_is_declared
test: tests/test_phase1_family_b.py::test_every_typed_span_slices_the_fixture_bytes
test: tests/test_phase1_family_b.py::test_every_family_b_gap_id_is_a_known_id
test: tests/test_phase1_family_b.py::test_the_family_meets_the_facts_the_catalogue_names
test: tests/test_phase1_family_b.py::test_the_new_fact_shapes_are_well_formed
test: tests/test_phase1_family_b.py::test_the_span_check_fails_on_a_planted_wrong_span
test: tests/test_phase1_family_b.py::test_the_coverage_check_fails_on_a_missing_fact
stop: after the body and HTML family (commit 2 of 3)
```

Allow-list (`turn=1.0c-B`): `fixtures/generated/`, `fixtures/raw/` (`SHA256SUMS` appended only),
`tools/make_fixtures.py`, `tools/write_raw_fixtures.py`, `tests/ledger/label_ledger.json`,
`tests/test_fixture_census.py`, `tests/test_phase1_family_b.py`, `docs/design/phase1-turn-declarations.md`.

```declaration turn=1.0c-C
module: tools/make_fixtures.py
module: tools/write_raw_fixtures.py
module: fixtures/generated/
module: fixtures/raw/
module: tests/ledger/label_ledger.json
module: tests/ledger/corpus.json
module: tests/ledger/behavior_ledger.json
module: tests/test_phase1_family_c.py
module: tests/test_fixture_census.py
module: docs/design/phase1-turn-declarations.md
test: tests/test_phase1_family_c.py::test_the_attachments_family_labels_load_and_are_ledgered
test: tests/test_phase1_family_c.py::test_every_family_c_fact_id_is_declared
test: tests/test_phase1_family_c.py::test_every_typed_span_slices_the_fixture_bytes
test: tests/test_phase1_family_c.py::test_every_family_c_gap_id_is_a_known_id
test: tests/test_phase1_family_c.py::test_the_family_meets_the_facts_the_catalogue_names
test: tests/test_phase1_family_c.py::test_the_new_fact_shapes_are_well_formed
test: tests/test_phase1_family_c.py::test_the_span_check_fails_on_a_planted_wrong_span
test: tests/test_phase1_family_c.py::test_the_coverage_check_fails_on_a_missing_fact
test: tests/test_phase1_family_c.py::test_every_zip_payload_is_stored_and_no_png_is_compressed
test: tests/test_phase1_family_c.py::test_every_fixture_is_under_64_kb
stop: after the attachments/caps family (the last of the three), before Turn 1.0d
```

Allow-list (`turn=1.0c-C`): `fixtures/generated/`, `fixtures/raw/` (`SHA256SUMS` appended only),
`tools/make_fixtures.py`, `tools/write_raw_fixtures.py`, `tests/ledger/label_ledger.json`,
`tests/test_fixture_census.py`, `tests/test_phase1_family_c.py`, `docs/design/phase1-turn-declarations.md`.

## Turn 1.0d -- entry point, limits, named errors, the HTML decision experiment

```declaration turn=1.0d
module: emailextract/parse.py
module: emailextract/versions.py
module: tools/html_experiment.py
module: docs/design/html-parser-experiment.md
module: docs/design/phase1-empirical.md
test: tests/test_parse_entry.py::test_parse_requires_limits_with_no_default
test: tests/test_parse_entry.py::test_limits_untrusted_constructor_supplies_the_caps
test: tests/test_parse_entry.py::test_parse_sniffs_cfb_msg_as_a_named_error
test: tests/test_parse_entry.py::test_parse_sniffs_rfc822_after_an_optional_bom
test: tests/test_parse_entry.py::test_parse_returns_a_named_error_on_garbage
test: tests/test_parse_entry.py::test_parse_container_kind_overrides_the_sniff
test: tests/test_parse_entry.py::test_parse_carries_invalid_input_for_a_non_bytes_input
test: tests/test_parse_entry.py::test_parse_returns_input_over_cap_before_any_sniff
test: tests/test_parse_entry.py::test_parse_returns_invalid_container_kind
test: tests/test_parse_entry.py::test_every_invalid_limits_field_raises_the_named_error
test: tests/test_parse_entry.py::test_limits_construction_is_the_only_named_error_raised
test: tests/test_parse_entry.py::test_parse_never_raises_on_hostile_bytes
test: tests/test_parse_entry.py::test_parse_module_does_not_import_the_stdlib_email_module
test: tests/test_html_parser_experiment.py::test_the_experiment_runs_over_every_html_fixture
test: tests/test_html_parser_experiment.py::test_the_experiment_records_the_libxml2_version_and_error_log
test: tests/test_html_parser_experiment.py::test_the_chosen_candidate_places_quote_containers_identically
test: tests/test_html_parser_experiment.py::test_an_unclosed_blockquote_is_recorded_not_closed
test: tests/test_html_parser_experiment.py::test_the_experiment_document_names_the_pinned_wheel
test: tests/test_html_parser_experiment.py::test_htmltext_version_gates_the_projection
test: tests/test_html_parser_experiment.py::test_the_package_imports_with_lxml_blocked
stop: after the HTML decision document and the entry point's named errors
```

Allow-list (`turn=1.0d`): `emailextract/parse.py`, `emailextract/versions.py`,
`docs/design/html-parser-experiment.md`, `docs/design/phase1-empirical.md`,
`tests/test_parse_entry.py`, `tests/test_html_parser_experiment.py`,
`docs/design/phase1-turn-declarations.md`. Not `fixtures/**`.

## Turn 1.1 -- `headers.py`, `rfc2047.py`, the walker tolerance, the header scanner

```declaration turn=1.1
module: emailextract/headers.py
module: emailextract/rfc2047.py
module: emailextract/walk.py
module: emailextract/versions.py
module: tests/support/stdlib_scanner.py
test: tests/test_headers.py::test_field_paragraphs_keep_order_and_duplicates
test: tests/test_headers.py::test_an_obs_fold_is_one_field
test: tests/test_headers.py::test_each_field_carries_its_raw_byte_span
test: tests/test_headers.py::test_the_header_region_ends_at_the_first_empty_line
test: tests/test_headers.py::test_a_malformed_line_fails_open
test: tests/test_headers.py::test_leading_bom_is_a_prelude_and_the_first_field_is_read
test: tests/test_headers.py::test_mbox_from_line_is_a_prelude_and_the_first_field_is_read
test: tests/test_headers.py::test_a_duplicate_header_records_the_gap
test: tests/test_headers.py::test_eight_bit_header_bytes_render_verbatim
test: tests/test_headers.py::test_mixed_case_names_are_lowercased_for_lookup_not_for_display
test: tests/test_rfc2047.py::test_a_valid_word_decodes
test: tests/test_rfc2047.py::test_an_invalid_word_records_the_gap
test: tests/test_rfc2047.py::test_whitespace_between_encoded_words_is_dropped
test: tests/test_rfc2047.py::test_a_split_character_joins_only_for_the_same_charset
test: tests/test_rfc2047.py::test_a_split_character_joins_across_spellings_of_one_charset
test: tests/test_rfc2047.py::test_an_rfc2231_language_suffix_on_the_charset_is_accepted
test: tests/test_rfc2047.py::test_unfold_keeps_the_whitespace
test: tests/test_rfc2231.py::test_continuations_reassemble_by_index
test: tests/test_rfc2231.py::test_a_missing_or_duplicate_index_is_an_error
test: tests/test_rfc2231.py::test_a_charset_on_segment_zero_only_is_legal
test: tests/test_rfc2231.py::test_a_star_name_shadows_the_plain_name
test: tests/test_rfc2231.py::test_an_encoded_word_in_a_parameter_is_a_recorded_fallback
test: tests/test_headers.py::test_the_lone_cr_gap_is_recorded_in_the_header_region
test: tests/test_headers.py::test_the_walker_tolerance_bumps_the_parser_version
test: tests/test_stdlib_header_scanner.py::test_field_names_and_order_match_the_stdlib_raw_view
test: tests/test_stdlib_header_scanner.py::test_the_scanner_disagrees_only_where_the_stdlib_shares_the_misreading
test: tests/test_headers.py::test_gap_falsification_duplicate_header_and_leading_bom
test: tests/test_headers.py::test_a_seeded_fuzz_of_the_header_stage_never_raises
test: tests/test_rfc2047.py::test_a_seeded_fuzz_of_the_word_decoder_never_raises
test: tests/test_rfc2231.py::test_a_seeded_fuzz_of_the_parameter_parser_never_raises
stop: after headers, folds and raw spans; rfc2047.py becomes its own turn if it grows past its ceiling
```

Allow-list (`turn=1.1`): `emailextract/headers.py`, `emailextract/rfc2047.py`, `emailextract/walk.py`,
`emailextract/versions.py`, `tests/support/stdlib_scanner.py`, `tests/test_headers.py`,
`tests/test_rfc2047.py`, `tests/test_rfc2231.py`, `tests/test_stdlib_header_scanner.py`,
`tests/ledger/label_ledger.json`, `docs/design/phase1-empirical.md`,
`docs/design/phase1-turn-declarations.md`. **Not** `fixtures/**` or `*.expected.json`.

## Turn 1.2 -- `addresses.py`

```declaration turn=1.2
module: emailextract/addresses.py
test: tests/test_addresses.py::test_an_addr_spec_gets_one_span
test: tests/test_addresses.py::test_a_quoted_display_name_with_a_comma_is_one_address
test: tests/test_addresses.py::test_a_group_preserves_its_members
test: tests/test_addresses.py::test_a_zero_member_group_is_empty_not_absent
test: tests/test_addresses.py::test_an_unparseable_address_is_unknown_with_its_raw_value
test: tests/test_addresses.py::test_an_idn_domain_is_kept_verbatim
test: tests/test_addresses.py::test_an_smtputf8_local_part_is_kept_verbatim
test: tests/test_addresses.py::test_obs_route_is_recorded
test: tests/test_addresses.py::test_cfws_does_not_split_an_address
test: tests/test_addresses.py::test_a_trailing_comma_is_tolerated
test: tests/test_addresses.py::test_the_own_tokenizer_returns_a_reason_where_parseaddr_loses_the_span
test: tests/test_addresses.py::test_the_advisory_stdlib_diff_is_printed_never_gated
test: tests/test_addresses.py::test_the_address_row_maps_onto_the_facts_row_shape
test: tests/test_addresses.py::test_an_unbalanced_quote_or_angle_bracket_is_unparsed
test: tests/test_addresses.py::test_a_mutation_flips_the_gate_for_every_address_state
test: tests/test_addresses.py::test_the_group_with_a_mutation_dropping_a_member_fails_the_gate
test: tests/test_addresses.py::test_every_emitted_gap_id_has_a_mutation_case
test: tests/test_addresses.py::test_a_seeded_fuzz_of_the_tokenizer_never_raises
test: tests/test_addresses.py::test_the_tokenizer_is_linear_in_the_input
test: tests/test_addresses.py::test_the_address_facts_are_live_over_the_corpus
stop: after the address tokenizer and its advisory comparator (the disagreements are recorded, not gated)
```

Allow-list (`turn=1.2`): `emailextract/addresses.py` (new), `emailextract/headers.py` (only the
narrow wiring that calls `addresses.py` for the `address_list` kinds), `emailextract/evals/l1.py`
(the two measurers), `tests/test_addresses.py`, `tests/support/stdlib_scanner.py` (the advisory
address diff, never imported by the package), `tests/ledger/label_ledger.json` (only the hashes of
the oracle files changed), `tests/ledger/behavior_ledger.json` (appended lines only),
`tests/test_turn_declarations.py` and `tests/test_l1_gate.py` and `tests/test_phase0_scope.py`
(narrow edits the turn's changes force), `docs/design/phase1-empirical.md`,
`docs/design/phase1-turn-declarations.md`. Not `fixtures/**` or `*.expected.json`.

## Turn 1.3 -- `dates.py`

```declaration turn=1.3
module: emailextract/dates.py
module: emailextract/headers.py
module: emailextract/evals/l1.py
module: tests/support/stdlib_scanner.py
module: tests/ledger/label_ledger.json
test: tests/test_dates.py::test_a_stated_zone_is_recorded_with_its_offset
test: tests/test_dates.py::test_minus_zero_is_not_plus_zero
test: tests/test_dates.py::test_an_absent_zone_is_zone_absent
test: tests/test_dates.py::test_an_optional_day_name_is_accepted
test: tests/test_dates.py::test_the_obs_zone_table_is_applied
test: tests/test_dates.py::test_an_offset_out_of_range_is_recorded_not_repaired
test: tests/test_dates.py::test_an_invalid_date_returns_a_reason_never_an_epoch
test: tests/test_dates.py::test_the_parser_never_raises_on_input_content
test: tests/test_dates.py::test_a_reason_id_where_parsedate_to_datetime_raises
test: tests/test_dates.py::test_the_stdlib_date_diff_is_recorded_only
test: tests/test_dates.py::test_the_rfc5322_examples_and_obs_forms_parse
test: tests/test_dates.py::test_a_leap_second_is_recorded_not_silently_rolled
test: tests/test_dates.py::test_cfws_and_comments_do_not_split_or_supply_the_zone
test: tests/test_dates.py::test_the_calendar_table_matches_hand_checked_dates
test: tests/test_dates.py::test_the_date_row_maps_onto_the_facts_row_shape
test: tests/test_dates.py::test_a_mutation_flips_the_gate_for_every_date_fact
test: tests/test_dates.py::test_every_emitted_date_gap_id_has_a_mutation_case
test: tests/test_dates.py::test_a_seeded_fuzz_of_the_parser_never_raises
test: tests/test_dates.py::test_the_parser_is_linear_in_the_input
test: tests/test_dates.py::test_the_date_facts_are_live_over_the_corpus
stop: after the date parser and its advisory comparator
```

**Refinement declared by the Turn 1.3 prompt (allowed: "add any extra to the block, which is
allowed, and say so").** The frozen block named one module and ten tests. The turn adds the
four modules the oracle wiring needs -- `emailextract/headers.py` (the narrow wiring that calls
`dates.py` for the `date_time` kinds and the Date-absent case), `emailextract/evals/l1.py` (the
two measurers), `tests/support/stdlib_scanner.py` (the advisory date diff) and
`tests/ledger/label_ledger.json` (the oracle hashes) -- plus the ten extra test names above
(RFC examples and obs-forms, the leap second, CFWS/comments, the calendar table, the fact row
shape, the per-fact mutation, the per-gap anti-vacuity triple, the fuzz, linearity, and the
live-fact sweep). Twenty tests, under the turn's ceiling of 25.

Allow-list (`turn=1.3`): `emailextract/dates.py`, `emailextract/headers.py`,
`emailextract/evals/l1.py`, `tests/support/stdlib_scanner.py`, `tests/ledger/label_ledger.json`,
`tests/ledger/behavior_ledger.json`, `tests/test_dates.py`, `docs/design/phase1-empirical.md`,
`docs/design/phase1-turn-declarations.md`, and the narrow forced edits to the existing tests
named in the turn report (`tests/test_turn_declarations.py`, `tests/test_l1_gate.py`,
`tests/test_addresses.py`, `tests/test_phase0_scope.py`). Not `fixtures/**` or `*.expected.json`.

## Turn 1.4 -- `text.py`: per-part text, alias table, offset maps, the one line model

```declaration turn=1.4
module: emailextract/text.py
module: emailextract/versions.py
test: tests/test_text.py::test_a_strict_identity_decode_builds_an_exact_offset_map
test: tests/test_text.py::test_spans_partition_the_raw_bytes_and_the_text
test: tests/test_text.py::test_a_fresh_redecode_of_a_slice_equals_the_text_slice
test: tests/test_text.py::test_a_strict_decode_round_trips_by_encoding_back
test: tests/test_text.py::test_a_joined_slice_rebuilds_the_raw_bytes
test: tests/test_text.py::test_an_anti_vacuity_mutant_on_a_span_length_fails
test: tests/test_text.py::test_a_bom_stays_exact_for_plain_utf8
test: tests/test_text.py::test_a_qp_or_base64_part_is_part_level_with_a_reason
test: tests/test_text.py::test_a_stateful_charset_is_multibyte_without_offset_map
test: tests/test_text.py::test_a_part_level_row_emits_no_within_part_byte_span
test: tests/test_text.py::test_the_used_charset_not_the_declared_one_keys_the_map
test: tests/test_text.py::test_the_coordinate_space_does_not_normalise_crlf
test: tests/test_text.py::test_the_charset_ladder_only_runs_over_text_parts
test: tests/test_text.py::test_the_splitter_line_starts_equal_iter_lines_over_a_cr_body
test: tests/test_text.py::test_flowed_space_unstuffing_runs_before_gt_counting
test: tests/test_text.py::test_flowed_soft_break_join_is_the_recorded_gap
test: tests/test_text.py::test_the_splitter_does_not_break_on_form_feed_or_u2028
test: tests/test_text.py::test_no_second_line_splitter_in_text_py
test: tests/test_text.py::test_the_text_part_decision_is_not_widened
test: tests/test_text.py::test_the_alias_table_is_closed_sorted_and_collision_free
test: tests/test_text.py::test_an_unknown_charset_name_is_unknown_not_an_exception
test: tests/test_text.py::test_an_alias_never_widens_a_charset
test: tests/test_text.py::test_the_alias_table_is_the_single_charset_resolution_point
test: tests/test_text.py::test_every_emitted_gap_id_has_an_anti_vacuity_case
test: tests/test_text.py::test_every_gap_emitted_over_the_corpus_is_catalogued
test: tests/test_text.py::test_the_flowed_declaration_is_read_case_insensitively
test: tests/test_text.py::test_text_properties_hold_over_a_seeded_fuzz
test: tests/test_text.py::test_a_planted_raiser_makes_the_fuzz_fail
test: tests/test_text.py::test_the_decode_and_the_map_are_linear_on_a_megabyte_body
test: tests/test_text.py::test_the_committed_body_text_labels_are_green_on_a_copy
test: tests/test_text.py::test_a_wrong_body_text_fails_the_gate
test: tests/test_text.py::test_a_wrong_body_text_precision_fails_the_gate
test: tests/test_text.py::test_a_wrong_body_text_reason_fails_the_gate
test: tests/test_text.py::test_a_missing_body_text_row_fails_the_gate
test: tests/test_text.py::test_the_stdlib_scanner_agrees_on_benign_leaf_text
test: tests/test_text.py::test_the_stdlib_text_exclusions_are_closed_and_reachable
stop: after the offset map and the shared line model, before the alias table's full sweep
```

The block above is Turn 1.4 as executed. The last twenty `test:` lines are the **extras the
turn's own prompt allowed** ("add any extra to the block, which is allowed, and say so"): the
source test that forbids a second line splitter, the form-feed/U+2028 anti-`splitlines` test,
the no-widening tests for the text-part decision and the alias table, the alias-table closure
and single-resolution-point tests, the gap catalogue with its anti-vacuity case, the seeded
fuzz with its planted raiser, the 1 MB linearity test and the five L1 falsifiability tests for
`body.text`. They are declared here and collected.

Allow-list (`turn=1.4`): `emailextract/text.py`, `emailextract/walk.py`, `emailextract/versions.py`,
`emailextract/rfc2047.py`, `emailextract/evals/l1.py`, `tests/test_text.py`,
`tests/support/stdlib_scanner.py`, `tests/ledger/label_ledger.json`, `tests/ledger/behavior_ledger.json`,
`docs/design/phase1-empirical.md`, `docs/design/phase1-turn-declarations.md`, and the narrow forced
edits the turn reports (`tests/test_phase0_scope.py`, `tests/test_turn_declarations.py`,
`tests/test_versions.py`, `tests/test_l1_gate.py`). Not `fixtures/**` or `*.expected.json`.

## Turn 1.5 -- selection, `htmltree.py`, `htmltext.py`

```declaration turn=1.5
module: emailextract/htmltree.py
module: emailextract/htmltext.py
module: emailextract/selection.py
module: emailextract/versions.py
test: tests/test_htmltree.py::test_the_tree_records_a_projected_span_per_element
test: tests/test_htmltree.py::test_the_tree_records_the_referenced_cid_set
test: tests/test_htmltree.py::test_an_unclosed_container_is_recorded_not_closed
test: tests/test_htmltree.py::test_style_and_script_are_dropped_from_the_projection
test: tests/test_htmltree.py::test_the_tree_is_bounded_and_a_cap_hit_is_a_recorded_state
test: tests/test_htmltree.py::test_a_stray_end_tag_a_mis_nesting_and_a_duplicate_attribute_are_recorded
test: tests/test_htmltree.py::test_the_implied_end_table_closes_the_open_element
test: tests/test_htmltree.py::test_the_tree_never_raises_over_a_seeded_mutation_set
test: tests/test_htmltext.py::test_the_projection_is_stamped_with_htmltext_version
test: tests/test_htmltext.py::test_an_img_and_an_href_projection_match_the_tree_spans
test: tests/test_htmltext.py::test_the_projection_rule_id_is_the_htmltext_versions_projection_input
test: tests/test_htmltext.py::test_the_node_to_span_map_nests_and_siblings_are_ordered
test: tests/test_htmltext.py::test_the_committed_html_spans_labels_agree_with_the_bytes_row_for_row
test: tests/test_htmltext.py::test_the_projection_never_touches_the_network_or_the_filesystem
test: tests/test_htmltext.py::test_a_remote_or_data_uri_alt_is_not_projected
test: tests/test_htmltext.py::test_a_project_cap_is_a_recorded_state_not_an_exception
test: tests/test_htmltext.py::test_odd_inputs_project_without_raising
test: tests/test_selection.py::test_the_display_rule_selects_the_plain_alternative
test: tests/test_selection.py::test_a_selected_html_alternative_marks_the_plain_unselected
test: tests/test_selection.py::test_an_alternative_group_id_is_message_local
test: tests/test_selection.py::test_a_plain_effectively_empty_alternative_is_the_fact
test: tests/test_selection.py::test_a_digest_child_without_content_type_is_the_gap
test: tests/test_selection.py::test_a_text_calendar_alternative_is_a_view_not_an_attachment
test: tests/test_selection.py::test_the_cid_helper_is_deterministic_for_sets
test: tests/test_selection.py::test_a_message_with_no_text_part_selects_none_and_records_the_gap
test: tests/test_selection.py::test_the_cid_reference_set_comes_from_the_tree_and_is_deduplicated_in_order
test: tests/test_selection.py::test_a_cid_a_remote_url_and_a_data_uri_are_three_distinct_kinds
test: tests/test_selection.py::test_the_cid_helper_is_set_arithmetic_and_case_sensitive
test: tests/test_selection.py::test_the_selection_path_touches_no_socket_and_no_open
test: tests/test_selection.py::test_every_emitted_gap_id_has_an_anti_vacuity_case
test: tests/test_selection.py::test_every_gap_emitted_over_the_corpus_is_catalogued
test: tests/test_selection.py::test_the_stdlib_scanner_agrees_on_html_shape
test: tests/test_selection.py::test_the_stdlib_html_exclusions_are_closed_and_reachable
test: tests/test_selection.py::test_the_html_shape_comparison_can_fail
test: tests/test_selection.py::test_the_html_and_selection_stages_never_raise_over_a_seeded_fuzz
test: tests/test_selection.py::test_a_planted_raiser_makes_the_html_fuzz_fail
test: tests/test_selection.py::test_the_html_stages_are_linear_on_a_megabyte_body
test: tests/test_selection.py::test_the_corpus_projection_hash_is_interpreter_stable
test: tests/test_selection.py::test_an_untampered_html_copy_is_green
test: tests/test_selection.py::test_a_wrong_sidecar_for_each_new_body_fact_fails_the_gate
test: tests/test_htmltree.py::test_the_cid_reference_set_feeds_cid_dangling_and_unreferenced
stop: after htmltree.py and the node-to-span map, before selection and the cid set
```

**Turn 1.5 as executed, in two halves.** Turn 1.5a landed ``htmltree.py`` and ``htmltext.py``
(the element tree, the projection, the node-to-span map) and stopped at the block's ``stop:``
line; Turn 1.5b landed ``selection.py`` (the referenced-cid set, the alternative grouping, the
display rule, the D16 emptiness fact) and the Phase 1 gap channel beside it, plus the oracle
rows and the five new facts' gate proofs. The extras declared in the block -- the four extra
``tests/test_htmltree.py`` cases, the six extra ``tests/test_htmltext.py`` cases (Turn 1.5a)
and the sixteen ``tests/test_selection.py`` extras (the fact's neighbours, the cid helpers, the
gap catalogue with its anti-vacuity triple, the stdlib HTML shape comparison with its closed
exclusions, the seeded fuzz with its planted raiser, the 1 MB linearity test, the
interpreter-stability hash and the L1 falsifiability proofs for the five new facts) -- are the
extras both halves' prompts allowed ("add any extra to the block, which is allowed, and say
so"). They are declared here and collected, so the turn is appended to ``BUILT_TURNS``.

**Turn 1.5a as executed.** The four extra `tests/test_htmltree.py` cases (the cap state, the
stray/mis-nesting/duplicate records, the implied-end table, the seeded mutation sweep) and
the six extra `tests/test_htmltext.py` cases (the rule-id key, the nesting/ordering map,
the label-agreement sweep with its pinned findings, the no-network/no-file guard, the
remote/`data:` projection, the cap state and the odd-input sweep) are the **extras the
half's own prompt allowed** ("add any extra to the block, which is allowed, and say so").
Turn 1.5a stopped at its pre-declared stop point (after ``htmltree.py`` and the node-to-span
map), so the ``selection.py`` cases and
``test_the_cid_reference_set_feeds_cid_dangling_and_unreferenced`` were **declared but not
collected** at that commit.

Allow-list (`turn=1.5`): `emailextract/htmltree.py`, `emailextract/htmltext.py`,
`emailextract/selection.py`, `emailextract/versions.py`, `tests/test_htmltree.py`,
`tests/test_htmltext.py`, `tests/test_selection.py`, `tests/support/stdlib_scanner.py`,
`tests/support/html_projection_hash.py`, `tests/ledger/label_ledger.json`,
`tests/ledger/behavior_ledger.json`, `docs/design/phase1-empirical.md`,
`docs/design/phase1-turn-declarations.md`, and the narrow forced edits the turn reports
(`tests/test_phase0_scope.py`, `tests/test_html_parser_experiment.py`,
`tests/test_turn_declarations.py`, `tests/test_l1_gate.py`). Not `fixtures/**`.

## The quote catalogue increment (between 1.5 and 1.6)

```declaration turn=quote-catalogue
module: fixtures/generated/
module: fixtures/raw/
module: docs/design/quote-catalogue-review.md
test: tests/test_quote_catalogue.py::test_every_catalogue_row_is_reviewable
test: tests/test_quote_catalogue.py::test_the_catalogue_labels_load_and_are_ledgered
test: tests/test_quote_catalogue.py::test_the_not_v1_rows_are_absent_from_the_rules
test: tests/test_quote_catalogue.py::test_the_reviewability_check_fails_on_a_missing_quotation
test: tests/test_quote_catalogue.py::test_the_quote_span_check_fails_on_a_planted_wrong_span
test: tests/test_quote_catalogue.py::test_every_quote_html_span_is_rederived_by_an_independent_projection
test: tests/test_quote_catalogue.py::test_the_html_projection_check_fails_on_a_planted_wrong_span
test: tests/test_quote_catalogue.py::test_the_quote_catalogue_fixtures_regenerate_byte_identically
test: tests/test_quote_catalogue.py::test_the_three_hole_rows_exist_and_type_the_decided_rules
stop: after the owner's row-by-row review (delegated 2026-10-05) and the three hole rows (27-29), before any quote rule is written
```

Allow-list (`turn=quote-catalogue`): `fixtures/generated/`, `tests/ledger/label_ledger.json`,
`tests/test_quote_catalogue.py`, `docs/design/quote-catalogue-review.md`,
`docs/design/phase1-turn-declarations.md`. **Owner review is a hard gate**: the increment does not
proceed to 1.6 until the owner has reviewed the rows (decision 13).

## Turn 1.5c -- limits enforcement (the new declared turn)

```declaration turn=1.5c
module: emailextract/walk.py
module: emailextract/parse.py
module: emailextract/evals/l1.py
module: emailextract/evals/falsify.py
module: tests/test_limits.py
module: tests/test_parse_entry.py
module: tests/test_behavior_ledger.py
module: tests/test_turn_declarations.py
module: docs/design/phase1-empirical.md
module: docs/design/phase1-build-spec.md
module: tests/ledger/label_ledger.json
test: tests/test_limits.py::test_the_cap_reasons_are_exactly_the_models_closed_skipped_reasons
test: tests/test_limits.py::test_a_cap_hit_is_the_existing_status_reason_and_a_cap_record
test: tests/test_limits.py::test_the_depth_cap_boundary_is_at_one_below_and_one_above
test: tests/test_limits.py::test_the_part_count_cap_boundary_is_at_one_below_and_one_above
test: tests/test_limits.py::test_the_header_bytes_cap_boundary_is_at_one_below_and_one_above
test: tests/test_limits.py::test_the_decoded_part_cap_boundary_is_at_one_below_and_one_above
test: tests/test_limits.py::test_the_decoded_total_cap_boundary_is_at_one_below_and_one_above
test: tests/test_limits.py::test_a_part_over_the_decoded_cap_is_skipped_and_its_sha256_is_unknown
test: tests/test_limits.py::test_every_later_part_is_skipped_once_the_total_cap_is_reached
test: tests/test_limits.py::test_a_quoted_printable_escape_bomb_is_bounded_and_skipped
test: tests/test_limits.py::test_cap_deep_nesting_records_the_depth_cap_and_nothing_under_untrusted
test: tests/test_limits.py::test_cap_large_part_count_records_the_part_count_cap_and_nothing_under_untrusted
test: tests/test_limits.py::test_cap_enormous_header_block_records_the_header_bytes_cap_and_nothing_under_untrusted
test: tests/test_limits.py::test_cap_very_long_base64_run_records_the_size_cap_and_nothing_under_untrusted
test: tests/test_limits.py::test_cap_encoded_word_bomb_records_the_header_bytes_cap_and_nothing_under_untrusted
test: tests/test_limits.py::test_every_capped_result_accounts_for_every_byte
test: tests/test_limits.py::test_two_caps_in_one_run_are_both_recorded
test: tests/test_limits.py::test_a_capped_walk_is_deterministic_across_runs_and_interpreters
test: tests/test_limits.py::test_no_mutated_fixture_and_random_limits_raises_and_the_bytes_tile
test: tests/test_limits.py::test_the_unbounded_walk_records_no_cap_and_equals_the_untrusted_walk
test: tests/test_limits.py::test_a_boundary_storm_is_linear_under_a_cap
test: tests/test_limits.py::test_a_deep_nesting_bomb_is_bounded_by_the_depth_cap
test: tests/test_limits.py::test_the_depth_cap_off_by_one_mutant_is_caught
test: tests/test_limits.py::test_the_part_count_cap_checked_after_building_the_parts_mutant_is_caught
test: tests/test_limits.py::test_the_header_cap_checked_after_the_fields_mutant_is_caught
test: tests/test_limits.py::test_a_truncated_body_mutant_is_refused_by_the_gate
test: tests/test_limits.py::test_a_total_cap_that_does_not_accumulate_mutant_is_caught
test: tests/test_limits.py::test_a_cap_hit_that_raises_mutant_is_caught
test: tests/test_limits.py::test_a_dropped_cap_region_mutant_fails_no_silent_drop
test: tests/test_limits.py::test_a_wrong_reason_id_mutant_is_caught
test: tests/test_limits.py::test_a_cap_value_not_the_callers_mutant_is_caught
test: tests/test_limits.py::test_every_cap_reason_has_a_mutation_case
stop: after every cap is enforced and recorded and the ledgers are green, before Turn 1.8
```

**Turn 1.5c is the "limits enforcement" turn** (`email-remaining-plan-debate.md` section 1 row 1 and
section 4's limits audit): `Limits` threaded into the walker, each of the seven caps enforced as the
structure is discovered, and each hit recorded as the closed `skipped(<cap>_cap)` status plus a
`CapRecord` triple -- no new reason id, no new record, no exception. The three forced edits in existing
tests (`tests/test_parse_entry.py` and `tests/test_behavior_ledger.py`, whose `_decode_cte` stand-in
gained the `limit` keyword) and `emailextract/evals/falsify.py` (the same stand-in) are the signature
change's, and `tests/test_turn_declarations.py` gains `"1.5c"` in `BUILT_TURNS`; each is reported by the
turn, none is loosened.

Allow-list (`turn=1.5c`): `emailextract/walk.py`, `emailextract/parse.py`, `emailextract/evals/l1.py`
(one attribute read), `emailextract/evals/falsify.py` (one mutant stand-in), `tests/test_limits.py`
(new), the narrow signature-forced edits reported above, `tests/ledger/label_ledger.json` (only the two
oracle files' hashes), `docs/design/phase1-turn-declarations.md`, `docs/design/phase1-empirical.md`,
`docs/design/phase1-build-spec.md`. Not `fixtures/**`, not `*.expected.json`, not `model.py`, not
`emailextract/evals/gates.py`.

## Turn 1.6 -- quote boundaries, text family

```declaration turn=1.6
module: emailextract/quote/__init__.py
module: emailextract/quote/text_rules.py
module: emailextract/quote/i18n.py
module: emailextract/quote/resolve.py
test: tests/test_quote_text.py::test_gt_family_prefix_depth_is_per_line
test: tests/test_quote_text.py::test_on_wrote_en_fires_at_level_one
test: tests/test_quote_text.py::test_the_outlook_flat_block_needs_two_adjacent_labels
test: tests/test_quote_text.py::test_the_outlook_language_is_per_block
test: tests/test_quote_text.py::test_the_outlook_date_slot_accepts_both_tokens
test: tests/test_quote_text.py::test_a_nbsp_separator_is_accepted_after_nfc
test: tests/test_quote_text.py::test_begin_forwarded_message_is_a_forward_banner_at_level_zero
test: tests/test_quote_text.py::test_original_message_dashes_is_a_named_shape
test: tests/test_quote_text.py::test_the_dash_dash_space_signature_is_a_candidate_only
test: tests/test_quote_text.py::test_a_list_footer_underscore_run_is_detected
test: tests/test_quote_text.py::test_bottom_posting_is_legal_not_a_gap
test: tests/test_quote_text.py::test_a_non_contiguous_alternation_is_inline_reply_interleaved
test: tests/test_quote_text.py::test_an_unknown_language_label_block_is_the_i18n_gap
test: tests/test_quote_text.py::test_only_quote_boundaries_advance_the_ordinal
stop: after the text family and the resolution rule
```

Allow-list (`turn=1.6`): `emailextract/quote/`, `emailextract/versions.py`, `tests/test_quote_text.py`,
`tests/test_quote_resolve.py`, `docs/design/phase1-turn-declarations.md`. Not `fixtures/**`.

## Turn 1.7 -- quote boundaries, DOM family and resolution

```declaration turn=1.7
module: emailextract/quote/dom_rules.py
module: emailextract/quote/resolve.py
test: tests/test_quote_dom.py::test_gmail_quote_on_a_div_fires_once
test: tests/test_quote_dom.py::test_gmail_quote_on_a_blockquote_adds_no_second_ordinal
test: tests/test_quote_dom.py::test_the_attribution_wrapper_adds_no_second_ordinal
test: tests/test_quote_dom.py::test_outlook_divrplyfwd_fires
test: tests/test_quote_dom.py::test_appendonsend_and_the_x_prefix_fire
test: tests/test_quote_dom.py::test_thunderbird_moz_cite_prefix_fires
test: tests/test_quote_dom.py::test_thunderbird_moz_forward_container_is_a_forward_banner
test: tests/test_quote_dom.py::test_a_known_vendor_prefix_without_a_row_is_the_html_gap
test: tests/test_quote_dom.py::test_structural_and_prefix_ranks_resolve_per_span
test: tests/test_quote_dom.py::test_an_all_zero_depth_beside_a_structural_rule_is_normal
test: tests/test_quote_dom.py::test_the_disagreement_predicate_fires_only_when_the_ranks_differ
test: tests/test_quote_dom.py::test_the_view_level_carries_its_resolution_rule_id
stop: after the DOM family and the cross-family resolution
```

Allow-list (`turn=1.7`): `emailextract/quote/`, `emailextract/versions.py`, `tests/test_quote_dom.py`,
`tests/test_quote_resolve.py`, `docs/design/phase1-turn-declarations.md`. Not `fixtures/**`.

## Turn 1.8 -- `attach.py`

```declaration turn=1.8
module: emailextract/attach.py
module: emailextract/text.py
test: tests/test_attach.py::test_identity_is_the_content_sha256_not_the_path
test: tests/test_attach.py::test_an_occurrence_is_filename_message_and_part_path
test: tests/test_attach.py::test_classification_comes_from_disposition_and_filename_never_size
test: tests/test_attach.py::test_a_decorative_hint_never_removes_an_occurrence
test: tests/test_attach.py::test_the_magic_table_matches_zip_ole_pdf_png_jpeg_gif_rtf_gzip_7z_rar
test: tests/test_attach.py::test_a_declared_text_plain_with_a_zip_prefix_wins_for_magic
test: tests/test_attach.py::test_magic_consulted_and_unmatched_is_the_unrecognized_value
test: tests/test_attach.py::test_a_not_computed_magic_is_unknown_with_a_reason
test: tests/test_attach.py::test_container_introspection_is_not_built_in_phase1
test: tests/test_attach.py::test_type_disagreement_needs_two_families
test: tests/test_attach.py::test_type_unknown_iff_no_verdict_yields_a_family
test: tests/test_attach.py::test_the_winner_order_prefers_magic
test: tests/test_attach.py::test_a_duplicate_content_id_records_the_gap
test: tests/test_attach.py::test_a_cid_reference_decides_unreferenced_and_dangling
test: tests/test_attach.py::test_a_filename_with_an_empty_charset_is_a_recorded_fallback
test: tests/test_attach.py::test_a_five_hundred_kilobyte_cap_hit_is_skipped_not_truncated
stop: after the manifest, identity, verdicts and cid sets
```

Allow-list (`turn=1.8`): `emailextract/attach.py`, `emailextract/text.py`, `emailextract/versions.py`,
`tests/test_attach.py`, `docs/design/phase1-turn-declarations.md`. Not `fixtures/**`.

## Turn 1.9 -- `assemble.py`, `ingest.py`, `store.py`

```declaration turn=1.9
module: emailextract/assemble.py
module: emailextract/ingest.py
module: emailextract/store.py
test: tests/test_assemble.py::test_every_document_axis_is_not_built_in_phase1
test: tests/test_assemble.py::test_a_built_axis_is_not_the_not_built_marker
test: tests/test_assemble.py::test_the_record_round_trips_through_the_strict_codec
test: tests/test_assemble.py::test_no_record_claims_a_phase2_axis
test: tests/test_ingest.py::test_ingest_of_a_directory_is_sorted_and_deterministic
test: tests/test_ingest.py::test_re_ingest_of_unchanged_bytes_is_a_no_op
test: tests/test_ingest.py::test_the_same_message_id_with_different_bytes_is_not_merged
test: tests/test_store.py::test_a_walk_artifact_is_keyed_by_its_versions
test: tests/test_assemble.py::test_a_nested_record_read_from_a_store_carries_its_own_axes
stop: after assemble, ingest and store are green end to end
```

Allow-list (`turn=1.9`): `emailextract/assemble.py`, `emailextract/ingest.py`, `emailextract/store.py`,
`tests/test_assemble.py`, `tests/test_ingest.py`, `tests/test_store.py`,
`docs/design/phase1-turn-declarations.md`. Not `fixtures/**`.

## Turn 1.10 -- gates over real output, the hostile set, the scope test, close

```declaration turn=1.10
module: emailextract/evals/gates.py
module: emailextract/evals/falsify.py
module: tests/test_phase1_scope.py
module: docs/phase1-report.md
test: tests/test_phase1_gap_gate.py::test_every_phase1_gap_id_has_a_mutation_case
test: tests/test_phase1_gap_gate.py::test_a_dropped_phase1_gap_fails_the_gate
test: tests/test_phase1_gap_gate.py::test_the_mutation_patch_is_reached
test: tests/test_facts_coverage.py::test_every_phase1_fact_meets_its_coverage_floor
test: tests/test_facts_coverage.py::test_at_least_one_sidecar_carries_a_non_trivial_value
test: tests/test_phase1_scope.py::test_no_msg_cfb_routing_recursion_or_threading_exists
test: tests/test_phase1_scope.py::test_the_package_imports_with_no_sibling_and_no_chardet
test: tests/test_phase1_scope.py::test_the_phase1_report_sections_are_present_and_non_empty
test: tests/test_hostile_set.py::test_a_socket_guard_fails_loudly_on_any_fetch
test: tests/test_hostile_set.py::test_work_per_input_byte_is_not_superlinear
test: tests/test_hostile_set.py::test_no_attachment_is_written_under_its_raw_filename
test: tests/test_seeded_splitter_fuzz.py::test_mutants_return_the_declared_failure_type
test: tests/test_seeded_splitter_fuzz.py::test_boundary_mutations_change_no_four_quantity
stop: at the phase's close; the report is the last artifact committed
```

Allow-list (`turn=1.10`): `emailextract/evals/`, `tests/test_phase1_gap_gate.py`,
`tests/test_facts_coverage.py`, `tests/test_phase1_scope.py`, `tests/test_hostile_set.py`,
`tests/test_seeded_splitter_fuzz.py`, `docs/phase1-report.md`,
`docs/design/phase1-turn-declarations.md`. Not `fixtures/**`.

## The verify-empirically experiments: which turn runs each, and where it is recorded

Per operating rule 7, **every measured number carries the command that produced it and a sha256 of the
output**, and a test re-runs it; anything not re-runnable is marked "verify empirically" and is not a
gate input. The eleven experiments of the spec's "Verify empirically" list are assigned below. Unless a
row says otherwise, the result is recorded as a fenced block (command, interpreter, output, output
sha256) in **`docs/design/phase1-empirical.md`**, which the turn appends to. `1.0d` creates that file.

| # | experiment | turn | exact inputs | recorded in | re-run by a test? |
|---|---|---|---|---|---|
| 1 | the HTML parser fingerprint | 1.0d | every HTML fixture, both pinned interpreters | `docs/design/html-parser-experiment.md` (+ the raw run in `phase1-empirical.md`) | **yes** -- `test_the_experiment_runs_over_every_html_fixture` re-runs and compares the hash |
| 2 | a leading BOM: expected a malformed first field today | 1.0d | one inline byte string `EF BB BF` + `From: a@b\r\n\r\n` | `phase1-empirical.md` | no (it describes the *pre*-1.1 walker, which 1.1 changes; recorded-only) |
| 3 | NUL in a header value (one field, `ok`) | 1.0d | `Subject: a\x00b\r\n\r\n` | `phase1-empirical.md` | no (recorded-only; 1.1's test is the gate) |
| 4 | NUL in a name (`unknown`, `headers.malformed_line`) | 1.0d | `Su\x00bject: x\r\n\r\n` | `phase1-empirical.md` | no (recorded-only) |
| 5 | lone CR: the walker, `_iter_lines` and `email.feedparser` split identically | 1.0d | one inline byte string `a\rb\r\nc` through all three | `phase1-empirical.md` | **yes** -- `test_the_splitter_line_starts_equal_iter_lines_over_a_cr_body` (1.4) is the gate; the feedparser half is advisory |
| 6 | an mbox `From ` line at byte 0 | 1.0d | `From ada@example.test Tue Mar  4 08:05:00 2025\r\nFrom: a@b\r\n\r\n` | `phase1-empirical.md` | no (recorded-only; 1.1's `leading_bom`/`mbox_from_line` tests are the gate) |
| 7 | `parsedate_to_datetime` raising on invalid input; naive for `-0000` and a missing zone | 1.3 | four date strings, on 3.11.15 and 3.14.3 | `phase1-empirical.md` | **yes** -- `test_a_reason_id_where_parsedate_to_datetime_raises` |
| 8 | `getaddresses` across patch levels (CVE-2023-27043 `strict`) | 1.2 | the group / empty-group / garbage / trailing-comma inputs, on both interpreters | `phase1-empirical.md` | no (recorded-only; advisory per decision 4) |
| 9 | `headerregistry.AddressHeader` on the same inputs | 1.2 | the same four inputs | `phase1-empirical.md` | no (advisory; fills the spike's missing row) |
| 10 | the offset-map property on the stateless-charset fixtures | 1.4 | the stateless-charset fixtures, both interpreters | `phase1-empirical.md` | **yes** -- the five-part property test in `tests/test_text.py` |
| 11 | the walker's `_header_value` first-win on a duplicate `Content-Type` | 1.1 | `duplicate_content_type_header`'s bytes | `phase1-empirical.md` | **yes** -- `test_a_duplicate_header_records_the_gap` |

Experiments 1 and 10 are **gate inputs** (a test re-runs them); 5 and 11 become gates in their own
turns; 2, 3, 4, 6, 8 and 9 are **recorded-only** -- they describe behaviour that a later turn *changes*
(2, 3, 4, 6) or an advisory comparator (8, 9), so they are not gate inputs and the documents say so.

## Not built in Turn 1.0a

Nothing above runs in Turn 1.0a. This turn writes **documents only**: the design revision
(`email-extraction-design.md`), the registry (`phase0-gaps.md` + the design's registry), this file,
`phase1-facts.md`, `phase1-ledgers.md` and `phase1-fixtures.md`, plus the `label-questions.md`
annotations. No module, test, fixture, sidecar, ledger file or tool is created or changed.
