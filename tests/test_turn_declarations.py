"""Turn 1.0b: the turn declaration and the collection test (``phase1-ledgers.md`` (e)).

Every Phase 1 turn declares, before it runs, the modules it will change and the new
test function names it will add; this test makes that declaration binding in both
directions. It reads the fenced ``declaration`` blocks from
``docs/design/phase1-turn-declarations.md`` and asserts:

1. every declared ``test:`` id of a **built, non-pending** turn is collected (a
   declared-but-absent test fails, so a declaration cannot over-promise); and
2. every collected test that neither the frozen Phase 0 baseline nor any declaration
   accounts for fails (an undeclared new test fails, so a turn cannot add a test it
   did not declare).

A declaration names a test **function** (``path::function``, the format
``pytest --collect-only -q`` prints for a plain function test); the comparison is on that
function part, because a test parametrized over the fixture corpus prints one id per
parameter set and the corpus grows without a turn adding a function. A block whose body
carries a ``pending:`` line names a turn that has not landed yet: its declared tests are
not required to be collected and its declared modules are not required to exist.

The Phase 0 baseline is the literal list of the node ids collected before Turn 1.0b
wrote any test; it is frozen here and never edited.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECLARATIONS = ROOT / "docs" / "design" / "phase1-turn-declarations.md"

#: The turns whose declaration must be fully collected. A later turn appends its own
#: turn name here, in the same commit as its tests (this file is in every Phase 1
#: turn's allow-list), so "a declaration cannot over-promise" stays true as turns land.
#: A turn whose block carries a ``pending:`` line is skipped until its family lands: its
#: declared tests do not exist yet, and the line is removed by the commit that lands it.
BUILT_TURNS = ("1.0b", "1.0c-A", "1.0c-B", "1.0c-C", "1.0d", "1.1", "1.2")

#: The frozen Phase 0 baseline: the node ids collected before Turn 1.0b wrote a test.
#: Captured at Turn 1.0b and never edited.
PHASE0_BASELINE = (
    'tests/test_behavior_ledger.py::test_the_committed_ledger_agrees_with_the_code',
    'tests/test_behavior_ledger.py::test_the_cli_check_exits_zero_on_unmodified_code',
    'tests/test_behavior_ledger.py::test_the_ledger_header_names_the_corpus_and_the_cross_interpreter_fact',
    'tests/test_behavior_ledger.py::test_the_corpus_manifest_lists_each_version_oldest_first',
    'tests/test_behavior_ledger.py::test_the_fingerprints_are_stable_and_look_like_hashes',
    'tests/test_behavior_ledger.py::test_the_version_strings_point_at_the_names_to_bump',
    'tests/test_behavior_ledger.py::test_a_header_scanner_rule_change_is_caught',
    'tests/test_behavior_ledger.py::test_a_decode_rule_change_is_caught',
    'tests/test_behavior_ledger.py::test_a_charset_ladder_change_is_caught',
    'tests/test_behavior_ledger.py::test_a_part_identity_rule_change_is_caught',
    'tests/test_behavior_ledger.py::test_a_contract_record_change_is_caught',
    'tests/test_behavior_ledger.py::test_a_retyped_field_moves_the_contracts_fingerprint',
    'tests/test_behavior_ledger.py::test_a_parser_version_bump_is_not_a_contract_change',
    'tests/test_behavior_ledger.py::test_the_recorded_default_is_the_constant_name_not_its_value',
    'tests/test_behavior_ledger.py::test_the_contracts_refusal_names_this_packages_constant',
    'tests/test_behavior_ledger.py::test_the_legacy_contracts_line_is_kept_and_never_compared',
    'tests/test_behavior_ledger.py::test_a_version_bump_without_a_recorded_line_names_the_constant',
    'tests/test_behavior_ledger.py::test_the_cli_exits_one_when_a_rule_changes_without_a_bump',
    'tests/test_behavior_ledger.py::test_record_is_append_only_and_names_the_constant_to_bump',
    'tests/test_behavior_ledger.py::test_check_and_record_accept_the_payload_with_its_comment_key',
    'tests/test_behavior_ledger.py::test_growing_the_corpus_adds_a_corpus_version_and_bumps_nothing',
    'tests/test_behavior_ledger.py::test_the_interpreter_is_recorded_but_never_keyed',
    'tests/test_closed_enums.py::test_body_view_is_exactly_two_states',
    'tests/test_closed_enums.py::test_encoding_source_is_exactly_seven_members',
    'tests/test_closed_enums.py::test_child_link_is_exactly_four_states',
    'tests/test_closed_enums.py::test_container_kind_is_exactly_two',
    'tests/test_closed_enums.py::test_closed_enum_signatures_are_exactly_the_spec_values',
    'tests/test_closed_enums.py::test_decorative_hint_is_rule_id_or_absent_never_a_bool',
    'tests/test_container.py::test_file_material_reads_the_same_bytes_through_path_and_memory',
    'tests/test_container.py::test_the_eml_adapter_is_rfc822_and_its_raw_bytes_are_verbatim',
    'tests/test_container.py::test_the_same_bytes_hash_the_same_over_both_routes',
    'tests/test_container.py::test_the_walk_is_identical_over_path_and_memory',
    'tests/test_container.py::test_the_fake_container_is_a_second_container_kind_without_cfb_code',
    'tests/test_container.py::test_the_fake_never_claims_a_real_container_fact',
    'tests/test_contracts.py::test_every_record_round_trips_byte_identically',
    'tests/test_contracts.py::test_every_dataclass_contract_has_a_round_trip_test',
    'tests/test_contracts.py::test_envelope_is_the_core_schema_version',
    'tests/test_contracts.py::test_unknown_key_at_top_level_raises',
    'tests/test_contracts.py::test_unknown_key_inside_a_nested_record_raises',
    'tests/test_contracts.py::test_unknown_key_inside_a_timeevent_raises',
    'tests/test_contracts.py::test_empty_flag_section_round_trips',
    'tests/test_contracts.py::test_flag_section_present_on_every_record',
    'tests/test_contracts.py::test_hit_location_is_opaque_and_producer_shaped',
    'tests/test_contracts.py::test_no_email_module_declares_a_sibling_address_field',
    'tests/test_decode_chain_flip.py::test_flipping_the_declared_charset_moves_the_projection_not_the_body',
    'tests/test_decode_chain_flip.py::test_changing_a_body_byte_moves_the_hashes_but_not_the_decode_chain',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[alternative_text_html]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[attachments_mixed]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[inline_cid_referenced_and_not]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[multipart_mixed_wraps_alternative]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[plain_simple]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[preamble_epilogue]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[rfc2047_folded_duplicate_received]',
    'tests/test_fixtures.py::test_regeneration_is_byte_identical[thread_three_refs_chain]',
    'tests/test_fixtures.py::test_the_conflict_fixtures_regenerate_byte_identically[date_before_hops]',
    'tests/test_fixtures.py::test_the_conflict_fixtures_regenerate_byte_identically[date_no_zone]',
    'tests/test_fixtures.py::test_the_conflict_fixtures_regenerate_byte_identically[date_vs_mtime]',
    'tests/test_fixtures.py::test_the_conflict_fixtures_regenerate_byte_identically[future_date_in_text]',
    'tests/test_fixtures.py::test_the_conflict_fixtures_regenerate_byte_identically[received_clock_skew]',
    'tests/test_fixtures.py::test_the_raw_three_match_sha256sums',
    'tests/test_fixtures.py::test_every_attachment_zip_member_is_stored_never_compressed',
    'tests/test_fixtures.py::test_the_png_uses_stored_deflate_blocks_never_a_compressed_one',
    'tests/test_fixtures.py::test_the_pdf_has_no_compressed_stream',
    'tests/test_gap_falsifiability.py::test_the_catalogue_covers_every_walker_gap',
    'tests/test_gap_falsifiability.py::test_the_gaps_no_fixture_carries_are_the_inline_cases',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.boundary_disagreement]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.decode_destroyed_bytes]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.decode_fallback_used]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.epilogue_bytes]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.headers_only]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.no_boundary_found]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[body.preamble_bytes]',
    'tests/test_gap_falsifiability.py::test_a_faithful_case_passes_and_the_mutant_is_caught[headers.malformed_line]',
    'tests/test_gap_falsifiability.py::test_the_mutation_is_restored_after_each_case',
    'tests/test_ids.py::test_the_container_hash_is_the_sha256_of_the_raw_bytes',
    'tests/test_ids.py::test_the_part_id_ignores_the_locator_and_its_three_members_are_all_identity',
    'tests/test_ids.py::test_a_part_id_cannot_be_built_without_its_three_members',
    'tests/test_ids.py::test_a_raw_span_slices_the_message_verbatim',
    'tests/test_ids.py::test_a_raw_span_rejects_a_negative_or_non_int_member[-1-3]',
    'tests/test_ids.py::test_a_raw_span_rejects_a_negative_or_non_int_member[0--1]',
    'tests/test_ids.py::test_a_raw_span_rejects_a_negative_or_non_int_member[0-True]',
    'tests/test_ids.py::test_a_raw_span_rejects_a_negative_or_non_int_member[True-3]',
    'tests/test_ids.py::test_a_raw_span_rejects_a_negative_or_non_int_member[0-1.5]',
    'tests/test_ids.py::test_a_walk_key_is_built_from_the_hashed_inputs_only',
    'tests/test_ids.py::test_the_not_built_reason_id_is_the_registry_value',
    'tests/test_l1_gate.py::test_the_gate_compares_the_whole_corpus_and_counts_not_yet_by_phase',
    'tests/test_l1_gate.py::test_the_committed_corpus_is_green_with_no_label_walker_disagreement',
    'tests/test_l1_gate.py::test_the_gate_reports_every_phase_the_corpus_waits_on',
    'tests/test_l1_gate.py::test_an_untampered_copy_is_green',
    'tests/test_l1_gate.py::test_a_wrong_sha256_fails_the_gate',
    'tests/test_l1_gate.py::test_a_shifted_header_span_fails_the_gate',
    'tests/test_l1_gate.py::test_a_wrong_part_span_fails_the_gate',
    'tests/test_l1_gate.py::test_a_missing_region_fails_the_gate',
    'tests/test_l1_gate.py::test_a_wrong_decode_chain_verdict_fails_the_gate',
    'tests/test_l1_gate.py::test_a_missing_fixture_fails_the_gate',
    'tests/test_l1_gate.py::test_a_sidecar_naming_an_unmodelled_fact_fails_the_gate',
    'tests/test_l1_gate.py::test_an_empty_corpus_fails_the_gate',
    'tests/test_l1_gate.py::test_a_corpus_that_compares_nothing_fails_the_gate',
    'tests/test_l1_gate.py::test_every_committed_sidecar_is_discovered_by_the_gate',
    'tests/test_label_structure.py::test_the_registry_the_gap_ids_are_checked_against_is_not_empty',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[alternative_text_html]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[attachments_mixed]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[bad_charset]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[date_before_hops]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[date_no_zone]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[date_vs_mtime]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[future_date_in_text]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[malformed_mime]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[plain_simple]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[preamble_epilogue]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[received_clock_skew]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_every_span_is_non_negative_and_in_range[truncated_base64]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[alternative_text_html]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[attachments_mixed]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[bad_charset]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[malformed_mime]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[plain_simple]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[preamble_epilogue]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_a_header_field_span_points_at_the_bytes_it_names[truncated_base64]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[alternative_text_html]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[attachments_mixed]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[bad_charset]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[date_before_hops]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[date_no_zone]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[date_vs_mtime]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[future_date_in_text]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[malformed_mime]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[plain_simple]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[preamble_epilogue]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[received_clock_skew]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_the_region_rows_tile_the_message_exactly[truncated_base64]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[alternative_text_html]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[attachments_mixed]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[bad_charset]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[date_before_hops]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[date_no_zone]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[date_vs_mtime]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[future_date_in_text]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[malformed_mime]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[plain_simple]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[preamble_epilogue]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[received_clock_skew]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_a_part_tree_row_partitions_its_raw_span[truncated_base64]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[alternative_text_html]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[attachments_mixed]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[bad_charset]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[date_before_hops]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[date_no_zone]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[date_vs_mtime]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[future_date_in_text]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[malformed_mime]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[plain_simple]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[preamble_epilogue]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[received_clock_skew]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_every_recorded_gap_id_is_in_the_design_registry_or_the_walker_constants[truncated_base64]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[alternative_text_html]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[attachments_mixed]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[bad_charset]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[date_before_hops]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[date_no_zone]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[date_vs_mtime]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[future_date_in_text]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[malformed_mime]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[plain_simple]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[preamble_epilogue]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[received_clock_skew]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason[truncated_base64]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[alternative_text_html]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[attachments_mixed]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[bad_charset]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[date_before_hops]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[date_no_zone]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[date_vs_mtime]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[future_date_in_text]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[inline_cid_referenced_and_not]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[malformed_mime]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[multipart_mixed_wraps_alternative]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[plain_simple]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[preamble_epilogue]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[received_clock_skew]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[rfc2047_folded_duplicate_received]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[thread_three_refs_chain]',
    'tests/test_label_structure.py::test_a_decode_chain_row_carries_the_closed_vocabularies[truncated_base64]',
    'tests/test_label_structure.py::test_a_time_evidence_row_is_a_real_timeevent[date_before_hops]',
    'tests/test_label_structure.py::test_a_time_evidence_row_is_a_real_timeevent[date_no_zone]',
    'tests/test_label_structure.py::test_a_time_evidence_row_is_a_real_timeevent[date_vs_mtime]',
    'tests/test_label_structure.py::test_a_time_evidence_row_is_a_real_timeevent[future_date_in_text]',
    'tests/test_label_structure.py::test_a_time_evidence_row_is_a_real_timeevent[received_clock_skew]',
    'tests/test_label_structure.py::test_the_orders_are_consistent_permutations_of_the_evidence[date_before_hops]',
    'tests/test_label_structure.py::test_the_orders_are_consistent_permutations_of_the_evidence[date_no_zone]',
    'tests/test_label_structure.py::test_the_orders_are_consistent_permutations_of_the_evidence[date_vs_mtime]',
    'tests/test_label_structure.py::test_the_orders_are_consistent_permutations_of_the_evidence[future_date_in_text]',
    'tests/test_label_structure.py::test_the_orders_are_consistent_permutations_of_the_evidence[received_clock_skew]',
    'tests/test_label_structure.py::test_the_unresolved_pairs_are_well_formed_and_match_the_conflict_flag[date_before_hops]',
    'tests/test_label_structure.py::test_the_unresolved_pairs_are_well_formed_and_match_the_conflict_flag[date_no_zone]',
    'tests/test_label_structure.py::test_the_unresolved_pairs_are_well_formed_and_match_the_conflict_flag[date_vs_mtime]',
    'tests/test_label_structure.py::test_the_unresolved_pairs_are_well_formed_and_match_the_conflict_flag[future_date_in_text]',
    'tests/test_label_structure.py::test_the_unresolved_pairs_are_well_formed_and_match_the_conflict_flag[received_clock_skew]',
    'tests/test_labels.py::test_the_loader_loads_in_a_bare_interpreter_without_the_parser',
    'tests/test_labels.py::test_every_sidecar_under_fixtures_loads',
    'tests/test_labels.py::test_every_fixture_has_a_sidecar_and_every_sidecar_a_fixture',
    'tests/test_labels.py::test_a_sidecar_naming_a_missing_fixture_is_refused',
    'tests/test_labels.py::test_a_sidecar_over_an_unknown_suffix_is_refused',
    'tests/test_labels.py::test_two_sidecars_for_one_stem_are_refused',
    'tests/test_labels.py::test_a_repeated_key_is_refused_not_dropped',
    'tests/test_labels.py::test_human_is_a_valid_token_but_no_sidecar_here_claims_it',
    'tests/test_metrics_cli.py::test_the_cli_exits_zero_on_a_clean_corpus',
    'tests/test_metrics_cli.py::test_the_cli_exits_one_on_a_tampered_corpus',
    'tests/test_metrics_cli.py::test_the_cli_exits_zero_on_the_committed_corpus',
    'tests/test_metrics_cli.py::test_the_table_names_every_gate_it_reports',
    'tests/test_metrics_cli.py::test_the_corpus_size_is_counted_by_directory',
    'tests/test_metrics_cli.py::test_the_undetermined_count_is_read_from_the_labels',
    'tests/test_metrics_cli.py::test_the_falsifiability_line_names_the_uncovered_gaps',
    'tests/test_metrics_cli.py::test_main_returns_zero_on_a_clean_corpus_without_printing_when_quiet',
    'tests/test_metrics_cli.py::test_main_returns_one_on_a_tampered_corpus',
    'tests/test_no_silent_drop.py::test_every_committed_fixture_accounts_for_every_byte',
    'tests/test_no_silent_drop.py::test_the_named_fixtures_tile_with_no_hole[preamble_epilogue]',
    'tests/test_no_silent_drop.py::test_the_named_fixtures_tile_with_no_hole[truncated_base64]',
    'tests/test_no_silent_drop.py::test_the_named_fixtures_tile_with_no_hole[malformed_mime]',
    'tests/test_no_silent_drop.py::test_dropping_a_region_leaves_the_range_unaccounted',
    'tests/test_no_silent_drop.py::test_a_duplicated_region_is_an_overlap',
    'tests/test_no_silent_drop.py::test_a_widened_region_is_an_overlap',
    'tests/test_no_silent_drop.py::test_the_gate_names_a_fixture_and_a_range_when_a_region_vanishes',
    'tests/test_phase0_gaps.py::test_the_registry_and_the_document_agree_both_ways',
    'tests/test_phase0_gaps.py::test_the_registry_in_force_is_85_ids_and_the_prune_holds',
    'tests/test_phase0_gaps.py::test_every_walker_gap_is_documented',
    'tests/test_phase0_gaps.py::test_every_sidecar_gap_id_is_documented',
    'tests/test_phase0_gaps.py::test_every_contract_gap_id_is_documented',
    'tests/test_phase0_gaps.py::test_the_falsifiability_ids_are_documented',
    'tests/test_phase0_gaps.py::test_the_check_would_catch_an_undocumented_id',
    'tests/test_phase0_scope.py::test_the_modules_are_exactly_the_phase_0_set',
    'tests/test_phase0_scope.py::test_no_library_module_imports_later_phase_machinery',
    'tests/test_phase0_scope.py::test_no_quote_segmenter_router_thread_builder_or_msg_reader_exists',
    'tests/test_phase0_scope.py::test_the_package_imports_with_olefile_and_the_siblings_blocked',
    'tests/test_seam.py::test_the_seam_records_round_trip_through_the_core_codec',
    'tests/test_seam.py::test_an_undeclared_key_is_refused_strictly',
    'tests/test_seam.py::test_the_stub_matcher_satisfies_the_protocol',
    'tests/test_seam.py::test_a_hit_names_the_view_that_fired',
    'tests/test_seam.py::test_a_run_boundary_stops_a_match_that_would_span_it',
    'tests/test_seam.py::test_a_hit_span_lies_inside_one_run_and_names_its_view',
    'tests/test_seam.py::test_the_stub_is_whole_token_exact_only',
    'tests/test_seam.py::test_the_stub_refuses_a_rule_it_does_not_implement',
    'tests/test_seam.py::test_a_stub_hit_round_trips_and_so_does_a_flag_section_holding_it',
    'tests/test_seam.py::test_an_unknown_view_id_is_refused_never_defaulted',
    'tests/test_seam.py::test_runs_must_tile_the_text',
    'tests/test_seam.py::test_no_seam_record_has_an_excluded_field',
    'tests/test_seam.py::test_the_walker_does_not_import_the_stub',
    'tests/test_siblings.py::test_the_contract_is_green_against_the_fake_store',
    'tests/test_siblings.py::test_the_childs_own_counts_come_from_the_child',
    'tests/test_siblings.py::test_the_citation_round_trips_through_the_strict_codec',
    'tests/test_siblings.py::test_a_version_mismatch_child_yields_version_mismatch_with_both_versions',
    'tests/test_siblings.py::test_a_core_version_mismatch_is_refused_too',
    'tests/test_siblings.py::test_a_deleted_child_store_yields_store_absent_and_keeps_the_manifest_useful',
    'tests/test_siblings.py::test_a_store_with_no_entry_for_the_hash_yields_child_absent',
    'tests/test_siblings.py::test_a_missing_store_makes_the_child_citation_unknown_whole',
    'tests/test_siblings.py::test_the_counts_are_unknown_when_the_store_is_absent_never_zero',
    'tests/test_siblings.py::test_the_three_buckets_are_disjoint',
    'tests/test_siblings.py::test_the_passthrough_is_opaque_and_a_later_change_to_the_siblings_object_changes_nothing',
    'tests/test_siblings.py::test_two_occurrences_of_one_file_are_two_citations_never_merged',
    'tests/test_siblings.py::test_the_locator_order_is_honoured',
    'tests/test_siblings.py::test_a_deleted_store_is_skipped_for_the_next_one',
    'tests/test_siblings.py::test_discovery_asks_find_spec_and_never_imports',
    'tests/test_siblings.py::test_an_unknown_sibling_family_is_refused',
    'tests/test_siblings.py::test_not_installed_carries_needed_sibling_and_no_reason',
    'tests/test_siblings.py::test_the_not_installed_path_with_the_siblings_genuinely_absent',
    'tests/test_siblings.py::test_the_sibling_presence_path_when_the_package_is_installed',
    'tests/test_siblings.py::test_the_package_imports_with_neither_sibling_imported',
    'tests/test_siblings.py::test_a_linked_citation_does_not_alias_the_stores_own_payload',
    'tests/test_status_reasons.py::test_status_enum_has_exactly_the_nine_members',
    'tests/test_status_reasons.py::test_a_tenth_status_cannot_be_constructed',
    'tests/test_status_reasons.py::test_reason_table_has_exactly_the_spec_rows',
    'tests/test_status_reasons.py::test_every_reason_belongs_to_exactly_one_status',
    'tests/test_status_reasons.py::test_reason_mandatory_rows_reject_a_missing_reason',
    'tests/test_status_reasons.py::test_allowed_reasons_build_and_any_other_reason_raises',
    'tests/test_status_reasons.py::test_tri_state_unknown_requires_a_reason_id',
    'tests/test_status_reasons.py::test_not_installed_needs_the_sibling_explainer',
    'tests/test_status_reasons.py::test_crypto_statuses_need_their_crypto_kind',
    'tests/test_stdlib_untouched.py::test_no_module_modifies_pathlib_or_any_stdlib_class',
    'tests/test_store.py::test_a_run_record_separates_hashed_inputs_from_recorded_only_inputs',
    'tests/test_store.py::test_each_artifact_reports_hit_or_miss',
    'tests/test_store.py::test_an_outcome_is_exactly_one_of_hit_and_wrote',
    'tests/test_store.py::test_re_ingest_is_a_no_op_over_a_throwaway_store',
    'tests/test_store.py::test_the_same_bytes_give_the_same_ids_and_a_byte_identical_store',
    'tests/test_store.py::test_an_artifact_round_trips_through_the_strict_codec',
    'tests/test_store.py::test_a_version_bump_is_a_new_key_never_an_overwrite',
    'tests/test_store.py::test_a_run_inputs_shape_is_frozen',
    'tests/test_time_conflicts.py::test_the_hand_typed_orders_reproduce_under_the_reference_evaluator[date_before_hops]',
    'tests/test_time_conflicts.py::test_the_hand_typed_orders_reproduce_under_the_reference_evaluator[date_no_zone]',
    'tests/test_time_conflicts.py::test_the_hand_typed_orders_reproduce_under_the_reference_evaluator[date_vs_mtime]',
    'tests/test_time_conflicts.py::test_the_hand_typed_orders_reproduce_under_the_reference_evaluator[future_date_in_text]',
    'tests/test_time_conflicts.py::test_the_hand_typed_orders_reproduce_under_the_reference_evaluator[received_clock_skew]',
    'tests/test_time_conflicts.py::test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts[date_before_hops]',
    'tests/test_time_conflicts.py::test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts[date_no_zone]',
    'tests/test_time_conflicts.py::test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts[date_vs_mtime]',
    'tests/test_time_conflicts.py::test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts[future_date_in_text]',
    'tests/test_time_conflicts.py::test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts[received_clock_skew]',
    'tests/test_time_conflicts.py::test_agreeing_evidence_produces_no_unresolved_pairs',
    'tests/test_time_conflicts.py::test_the_chain_runs_by_header_order_and_never_by_timestamp',
    'tests/test_time_conflicts.py::test_owner_manifest_is_a_total_order_override_not_evidence_ranked',
    'tests/test_time_conflicts.py::test_an_unusable_in_text_date_never_becomes_an_arrival_time',
    'tests/test_time_conflicts.py::test_no_policy_is_implicit_an_empty_policy_list_is_an_error',
    'tests/test_time_conflicts.py::test_an_owner_manifest_that_names_an_unknown_event_is_refused',
    'tests/test_timeevent.py::test_timeevent_shape_is_frozen_field_for_field',
    'tests/test_timeevent.py::test_unknown_relative_event_round_trips_byte_identically',
    'tests/test_timeevent.py::test_when_utc_cannot_also_carry_a_value',
    'tests/test_timeevent.py::test_when_utc_requires_exactly_one_of_value_or_unknown_reason',
    'tests/test_timeevent.py::test_offset_requires_exactly_one_of_value_or_unknown_reason',
    'tests/test_timeevent.py::test_offset_origin_absent_requires_an_unknown_offset',
    'tests/test_timeevent.py::test_offset_origin_is_one_of_three_states',
    'tests/test_timeevent.py::test_source_requires_exactly_one_of_field_property_part',
    'tests/test_timeevent.py::test_source_signatures_are_closed',
    'tests/test_timeevent.py::test_calendar_facts_are_not_timeevents',
    'tests/test_timeevent.py::test_timeevent_shape_has_its_own_version_constant',
    'tests/test_timeevent.py::test_a_relative_time_is_never_resolved',
    'tests/test_timeevent.py::test_a_filesystem_time_is_never_usable_for_arrival_ordering',
    'tests/test_timeevent.py::test_enum_fields_coerce_from_strings_at_construction',
    'tests/test_timeevent.py::test_a_value_outside_the_vocabulary_raises_at_construction',
    'tests/test_timeevent.py::test_the_dataclass_is_field_for_field_the_documented_shape',
    'tests/test_timeevent.py::test_every_enum_is_member_for_member_the_documented_shape',
    'tests/test_timeevent.py::test_the_document_states_the_tri_state_the_one_of_and_the_version',
    'tests/test_timeevent.py::test_the_document_lists_the_open_kind_vocabulary',
    'tests/test_timeevent.py::test_the_document_names_the_three_policies_and_no_implicit_policy',
    'tests/test_versions.py::test_every_frozen_constant_is_exposed_and_named',
    'tests/test_versions.py::test_every_version_constant_documents_itself',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Received: from a.example by b.example; Tue, 4 Mar 2025 08:59:00 +0000\\r\\nReceived: from c.example by a.example; Tue, 4 Mar 2025 08:58:00 +0000\\r\\nSubject: a folded value\\r\\n\\tcontinues here\\r\\nnot a header line\\r\\nX-After: still recorded\\r\\n\\r\\nbody after the headers\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[MIME-Version: 1.0\\r\\nContent-Type: multipart/mixed; boundary="B-1"\\r\\n\\r\\npreamble text\\r\\n--B-1\\r\\nContent-Type: text/plain; charset=us-ascii\\r\\nContent-Transfer-Encoding: base64\\r\\n\\r\\ncGFydCB0d28=\\r\\n--B-1--\\r\\nepilogue text\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[MIME-Version: 1.0\\r\\nContent-Type: multipart/alternative; boundary=OUTER\\r\\n\\r\\n--OUTER\\r\\nContent-Type: text/plain; charset=iso-8859-1\\r\\n\\r\\nCaf\\xe9 na\\xefve\\r\\n--OUTER\\r\\nContent-Type: multipart/alternative; boundary=INNER\\r\\n\\r\\n--INNER\\r\\nContent-Type: text/html\\r\\n\\r\\n<p>view</p>\\r\\n--INNER--\\r\\n--OUTER--\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: multipart/mixed; boundary="x;y"\\r\\n\\r\\n--x;y\\r\\n\\r\\npart\\r\\n--x;y--\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: text/plain; charset=us-ascii\\r\\nContent-Transfer-Encoding: x-no-such-cte\\r\\n\\r\\npayload kept verbatim\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: text/plain; charset=us-ascii\\r\\nContent-Transfer-Encoding: base64\\r\\n\\r\\nnot*valid*base64==\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: text/plain; charset=x-no-such-charset\\r\\n\\r\\nbyte \\x81 broke the round trip\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: text/plain; charset=utf-8\\r\\nContent-Transfer-Encoding: quoted-printable\\r\\n\\r\\nCaf=C3=A9 na=C3=AFve\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: text/plain\\r\\n\\r\\nCaf\\xc3\\xa9 na\\xc3\\xafve\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: text/plain\\r\\n\\r\\nprice \\x80 9\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Subject: no blank line follows\\r\\nX-Last: to end of file]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: multipart/mixed\\r\\n\\r\\n--missing\\r\\n\\r\\nbody\\r\\n]',
    'tests/test_walk.py::test_every_byte_is_accounted_for_by_exactly_one_region[Content-Type: multipart/mixed; boundary=B\\r\\n\\r\\n--B\\r\\nContent-Type: text/plain\\r\\n\\r\\none\\r\\n--B\\r\\nContent-Type: text/plain\\r\\n\\r\\ntwo\\r\\n]',
    'tests/test_walk.py::test_the_same_part_shape_over_the_eml_adapter_and_the_fake',
    'tests/test_walk.py::test_a_fold_is_one_field_with_duplicates_kept_and_the_region_failing_open',
    'tests/test_walk.py::test_the_header_scanner_reports_fields_with_their_spans_into_the_raw_message',
    'tests/test_walk.py::test_the_decode_chain_records_what_was_declared_against_what_ran',
    'tests/test_walk.py::test_quoted_printable_is_decoded_and_recorded',
    'tests/test_walk.py::test_the_charset_ladder_uses_its_named_rungs_when_nothing_was_declared',
    'tests/test_walk.py::test_an_unknown_cte_records_the_fallback_and_keeps_the_payload',
    'tests/test_walk.py::test_a_broken_base64_payload_is_not_a_quiet_partial_decode',
    'tests/test_walk.py::test_a_lossy_decode_is_recorded_and_replacement_is_never_the_normal_path',
    'tests/test_walk.py::test_the_preamble_and_the_epilogue_are_their_own_accounted_regions',
    'tests/test_walk.py::test_a_quoted_boundary_is_one_parameter_not_a_semicolon_split',
    'tests/test_walk.py::test_nested_parts_carry_their_path_and_parent_as_locators',
    'tests/test_walk.py::test_a_part_id_is_the_content_addressed_triple_not_the_locator',
    'tests/test_walk.py::test_a_headers_only_message_records_its_state_by_name',
    'tests/test_walk.py::test_a_multipart_without_a_boundary_names_the_gap_and_invents_no_parts',
    'tests/test_walk.py::test_a_missing_close_boundary_is_a_named_disagreement_not_a_guessed_stop',
    'tests/test_walk.py::test_every_unbuilt_section_is_unknown_with_its_reason_id',
    'tests/test_walk.py::test_a_binary_part_has_no_charset_reading_and_no_false_destroyed_bytes[Content-Type: application/pdf\\r\\n]',
    'tests/test_walk.py::test_a_binary_part_has_no_charset_reading_and_no_false_destroyed_bytes[Content-Type: image/png\\r\\n]',
    'tests/test_walk.py::test_a_binary_part_has_no_charset_reading_and_no_false_destroyed_bytes[Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\\r\\n]',
    'tests/test_walk.py::test_a_text_part_and_a_part_with_no_content_type_still_get_the_ladder',
    'tests/test_walk_malformed.py::test_adjacent_delimiters_are_an_empty_part_not_a_crash[0\\nContent-Type:multipart/;boundary=b\\n\\n--b\\n--b--]',
    'tests/test_walk_malformed.py::test_adjacent_delimiters_are_an_empty_part_not_a_crash[0\\r\\nContent-Type:multipart/;boundary=b\\r\\n\\r\\n--b\\r\\n--b--]',
    'tests/test_walk_malformed.py::test_adjacent_delimiters_are_an_empty_part_not_a_crash[0\\nContent-Type:multipart/;boundary="a.+*?[b"\\n\\n--a.+*?[b\\n--a.+*?[b--]',
    'tests/test_walk_malformed.py::test_adjacent_delimiters_are_an_empty_part_not_a_crash[From: a@example.test\\r\\nSubject: s\\r\\nMIME-Version: 1.0\\r\\nContent-Type: multipart/mixed; boundary=b\\r\\n\\r\\n--b\\r\\n--b\\r\\n--b\\r\\n\\r\\nx\\r\\n--b--\\r\\n]',
    'tests/test_walk_malformed.py::test_adjacent_delimiters_are_an_empty_part_not_a_crash[From: a@example.test\\r\\nSubject: s\\r\\nMIME-Version: 1.0\\r\\nContent-Type: multipart/mixed; boundary=b\\r\\n\\r\\n--b\\r\\n--b\\r\\n]',
    'tests/test_walk_malformed.py::test_a_seeded_mutation_fuzz_never_crashes_and_never_loses_a_byte',
    'tests/test_walk_malformed.py::test_the_same_mutant_walks_to_the_same_result_twice',
)

_BLOCK = re.compile(r"```declaration turn=(?P<turn>[^\s]+)\n(?P<body>.*?)```", re.DOTALL)


def _parse_declarations(text: str) -> dict[str, dict[str, list[str]]]:
    """``turn -> {'tests': [...], 'modules': [...], 'pending': str | None}``."""
    blocks: dict[str, dict[str, list[str]]] = {}
    for match in _BLOCK.finditer(text):
        tests: list[str] = []
        modules: list[str] = []
        pending: str | None = None
        for line in match.group("body").splitlines():
            line = line.strip()
            if line.startswith("test:"):
                tests.append(line[len("test:"):].strip())
            elif line.startswith("module:"):
                modules.append(line[len("module:"):].strip())
            elif line.startswith("pending:"):
                pending = line[len("pending:"):].strip()
        blocks[match.group("turn")] = {"tests": tests, "modules": modules, "pending": pending}
    return blocks


def _collected() -> list[str]:
    """The node ids ``pytest --collect-only -q`` prints, in order."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    ids: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("tests/") and "::" in line:
            ids.append(line)
    return ids


def _function(node_id: str) -> str:
    """The ``path::function`` part of a node id: a parametrized id names one case.

    A declared test is written ``path::function`` (the format the design fixes for a
    declaration), while ``--collect-only -q`` prints one id **per parameter set**. A test
    parametrized over the fixture corpus therefore grows new collected ids as the corpus
    grows, without a turn adding a test function; comparing the function part keeps the
    declaration bindable in both directions.
    """
    return node_id.split("[", 1)[0]


def _missing_declared(
    blocks: dict[str, dict[str, list[str]]], collected: list[str], turns: tuple[str, ...]
) -> list[str]:
    """Every declared test of a built turn that is not collected (direction 1).

    A turn whose block carries a ``pending:`` line has not landed yet, so its declared
    tests are not required to be collected.
    """
    present = {_function(node_id) for node_id in collected}
    problems: list[str] = []
    for turn in turns:
        block = blocks.get(turn)
        if block is None:
            problems.append(f"turn {turn!r} has no declaration block in the document")
            continue
        if block.get("pending"):
            continue
        for test_id in block["tests"]:
            if _function(test_id) not in present:
                problems.append(f"{test_id} is declared by turn {turn!r} but not collected")
    return problems


def _undeclared(
    collected: list[str], blocks: dict[str, dict[str, list[str]]], baseline: tuple[str, ...]
) -> list[str]:
    """Every collected test that neither the baseline nor a declaration accounts for (2)."""
    allowed = {_function(node_id) for node_id in baseline}
    for block in blocks.values():
        allowed.update(_function(test_id) for test_id in block["tests"])
    return [test_id for test_id in collected if _function(test_id) not in allowed]


def _read_blocks() -> dict[str, dict[str, list[str]]]:
    return _parse_declarations(DECLARATIONS.read_text(encoding="utf-8"))


def test_every_declared_test_is_collected() -> None:
    blocks = _read_blocks()
    assert blocks, "the declarations document has no fenced declaration blocks"
    collected = _collected()
    problems = _missing_declared(blocks, collected, BUILT_TURNS)
    assert not problems, problems
    # The module lines are checked weakly: the declared file exists. A pending turn's
    # modules are not required to exist yet.
    missing = [
        module
        for turn in BUILT_TURNS
        if not blocks[turn].get("pending")
        for module in blocks[turn]["modules"]
        if not (ROOT / module).exists()
    ]
    assert not missing, missing
    # Direction 1 can fail: a declared-but-absent test is a problem, not a pass.
    fake = {"1.0b": {"tests": ["tests/test_nope.py::test_absent"], "modules": [], "pending": None}}
    assert _missing_declared(fake, collected, ("1.0b",)) == [
        "tests/test_nope.py::test_absent is declared by turn '1.0b' but not collected"
    ]
    # ... still for a NON-pending turn (so an undeclared family cannot hide behind the flag)...
    landed = "1.0c-A"
    assert not blocks[landed].get("pending"), f"{landed} must be a landed, checked turn"
    fake_landed = {
        landed: {"tests": ["tests/test_nope.py::test_absent"], "modules": [], "pending": None}
    }
    assert _missing_declared(fake_landed, collected, (landed,)) == [
        f"tests/test_nope.py::test_absent is declared by turn {landed!r} but not collected"
    ]
    # ... and the flag does exempt a pending turn.
    fake_pending = {
        "1.0c-C": {"tests": ["tests/test_nope.py::test_absent"], "modules": [], "pending": "not yet"}
    }
    assert _missing_declared(fake_pending, collected, ("1.0c-C",)) == []


def test_every_undeclared_test_fails_the_declaration() -> None:
    blocks = _read_blocks()
    collected = _collected()
    problems = _undeclared(collected, blocks, PHASE0_BASELINE)
    assert not problems, f"collected tests nobody declared: {problems}"
    # Direction 2 can fail: a collected test the baseline and the document both miss.
    planted = "tests/test_gone.py::test_undeclared"
    assert _undeclared([*collected, planted], blocks, PHASE0_BASELINE) == [planted]
    # ... and a declared id is accounted for by its declaration alone.
    declared = blocks[BUILT_TURNS[0]]["tests"][0]
    assert _undeclared([declared], blocks, ()) == []
