# Phase 1 empirical constants

One place for every constant Phase 1 **measures** or **fixes**, so a later turn appends
here rather than scattering numbers through the code and the docs. Every entry says
plainly whether its number is **measured** (a command produced it and its output is
recorded) or **reasoned** (the design owner approved it; it is not measured). Operating
rule 7: a measured number carries the command that produced it; anything not re-runnable
is marked "verify empirically" and is not a gate input.

This file is started in **Turn 1.0d**; later turns append their own sections.

## `Limits.untrusted()` — reasoned, not measured

The recommended untrusted default cap set (decision 10,
`emailextract/parse.py`):

| field | value | bytes |
|---|---|---|
| `max_input_bytes` | 64 MiB | 67 108 864 |
| `max_depth` | 16 | — |
| `max_parts` | 1000 | — |
| `max_header_bytes` | 256 KiB | 262 144 |
| `max_decoded_part_bytes` | 32 MiB | 33 554 432 |
| `max_decoded_total_bytes` | 128 MiB | 134 217 728 |
| `max_field_work_units_per_byte` | 64 | — |

**Reasoned, not measured.** No corpus measurement produced these numbers; the design
owner approved them as the recommended defaults. The reasoning: a real message the size of
the largest fixtures is orders of magnitude below 64 MiB, so the input cap is generous
enough never to bite a genuine message while still bounding a hostile one; 16-deep
multipart nesting and 1000 parts exceed any producer's legitimate tree (real mail nests a
handful deep) by a wide margin; the per-part and total decoded caps bound the base64/QP
expansion of a small input to a few times its size; and `max_field_work_units_per_byte`
is a per-**field-value** **work** budget (never a time) for the encoded-word and base64
expansions that a later turn asserts against.

**Enforcement is staged.** Turn 1.0d enforced **only** `max_input_bytes` (`parse` checks
it before any sniff); **Turn 1.5c enforces the other six** in the walker, as the structure
is discovered. The cap fixtures' sidecars never assert a status: a `Limits` is a parameter
of the test, not of the label.

## The HTML parser decision (Turn 1.0d)

Measured by `tools/html_experiment.py`; recorded in full in
`docs/design/html-parser-experiment.md`. Both runs:

```
python tools/html_experiment.py --json                        # CPython 3.14.3
py -V:Astral/CPython3.11.15 tools/html_experiment.py --json   # CPython 3.11.15
```

* **Decision:** candidate **A** — the stdlib `html.parser` plus the own stack-based element
  tree. B (lxml) matches A on every *closed* quote container but, like A, lets an unclosed
  `<blockquote>` swallow the following text, so **neither is clean** and decision 1's named
  unclosed-container rule applies (gap `body.html_quote_rule_gap`).
* **Interpreters the runs used (recorded run inputs, measured):** CPython **3.14.3** and
  CPython **3.11.15**. Candidate A's per-input event/tree/projection hashes are
  **byte-identical** across the two.
* **The lxml wheel (measured, for candidate B only):** lxml **6.1.3.0** on libxml2
  **2.11.9**, identical under both interpreters. B is pinned by the wheel, not the
  interpreter, so the two-interpreter identity says nothing about libxml2.
* **Fingerprints:** the two JSON outputs' sha256 are
  `0aa5114256c157757efbe73ccde0c2786c857f9fd2366f8a2b0ddff652db49ea` (3.14.3) and
  `1a9b21e0f7f1b5cc85e2ae510bcc3205df12cb7f6f0fedc3bbe0bca9ab736657` (3.11.15); the
  per-input hashes are in the experiment document. A is identical on both; the outputs
  differ only in the recorded interpreter string.

**`HTMLTEXT_VERSION` (Turn 1.0d).** Because A was chosen, the key is
`1+htmlparser+<cpython-major.minor>+verbatim-non-style-script+recorded-not-closed`, built
at import from `sys.version_info[:2]` (`emailextract/versions.py`). The lxml wheel is
**not** a key input, because the chosen candidate does not use it. The constant ships
symbolically only (`htmltext.py` is Turn 1.5) and the behavior ledger keys nothing by it.

## Turn 1.1 — the header stage, its live facts and the walker tolerance

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.1; the
command and its output are the record.

* **The L1 oracle now compares 30 more facts, all green.** Command:
  `python -m emailextract.evals`. Output (both interpreters identical):
  `L1 matched=777 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=155, phase 3=26`.
  Before this turn the gate was `matched=747`, `not_yet: phase 1=185, phase 3=26`; the 30
  newly-live sidecar facts are `headers.projection` (12 sidecars), `headers.decoded` (6),
  `headers.parameters` (6) and the live `gaps.later` rows (6).
* **The `parsed_value` column is partial by design.** `headers.projection` compares
  `(ordinal, name, raw_value, parsed_kind)` on every row and the parsed scalar only where a
  parser exists this turn. The counts of the deferred column, from
  `emailextract.evals.l1.deferral_counts()`:
  `headers.projection.address_list:1.2 = 25`, `headers.projection.date_time:1.3 = 12`. They
  are deferred **by name** (never computed with a stdlib parser, never silently skipped).
* **The walker tolerance is a versioned behaviour change.** `EMAIL_PARSER_VERSION` 1 to 2;
  the behaviour ledger appended five `walk` lines under the new key `2|2|corpus:N`
  (corpora 1 to 5); the `decode_chain` and `contracts` lines did not move. Command:
  `python tools/update_behavior_ledger.py` (and `--check` exits 0 on both interpreters).
  Only `leading_utf8_bom` (corpus 3 and later) and `mbox_from_line_at_zero` change what the
  walker emits, and by design their sidecars type only `container.sha256` /
  `container.size_bytes` at phase 0, so no frozen phase-0 label moves.
* **The stdlib scanner's disagreements are a closed catalogue.** Command:
  `python -m pytest tests/test_stdlib_header_scanner.py -q` (2 passed). Field-name/order
  disagreements occur only for `leading_utf8_bom` (shared BOM misreading), `malformed_mime`
  and `nul_in_header_name` (the package fails open, the stdlib stops at the malformed line),
  while `mbox_from_line_at_zero` / `lone_cr_in_header_region` agree but prove nothing (listed
  in the shared-misreading catalogue). The content-type tree disagrees only for
  `message/rfc822` nesting (2 fixtures, Phase 2 recursion) and the digest child's
  RFC 2046 5.1.5 default (`body.digest_default_not_applied`). The decoded values agree on
  every fixture with a valid word.
* **The fuzz loops are seeded and bounded.** `Random(11_1001)` / `Random(11_2047)` /
  `Random(11_2231)`; 600 header-region mutations and 1200 + 1200 decoder/parameter inputs.
  No defect found: the three functions never raised on mutated bytes.

## Turn 1.2 — the address tokenizer, its two live comparisons and the advisory diff

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.2; the
command and its output are the record. Both interpreters run the suite; the values below are
identical on CPython **3.14.3** and **3.11.15** (the code imports the stdlib `email` nowhere,
so the address rules cannot drift between them).

* **The L1 oracle now compares 7 more facts, all green.** Command:
  `python -m emailextract.evals`. Output (both interpreters identical):
  `L1 matched=784 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=148, phase 3=26`.
  Before this turn the gate was `matched=777`, `not_yet: phase 1=155`; the 7 newly-live
  sidecar facts are `headers.addresses` (the 6 Family-A `address_*` fixtures and
  `headers_plain_baseline`). The turn also **turned on** the `headers.projection`
  `address_list` `parsed_value` comparison that Turn 1.1 deferred.
* **The `parsed_value` column is now complete except `date_time`.** From
  `emailextract.evals.l1.deferral_counts()`: `headers.projection.address_list:1.2` is **empty**
  (it was 25) and `headers.projection.date_time:1.3 = 12` remains (Turn 1.3).
* **`headers.addresses`' comparison is the sparse-row rule, and that is a FINDING.** The six
  Family-A `address_*` sidecars label **only their `To` field**, while `headers_plain_baseline`
  labels `From, To, Cc`. Every fixture carries the identical `From: Ada Sender
  <ada@example.test>` mailbox (`value_span [5, 30]`), so no uniform measurer can include the
  `From` entry for the one fixture and omit it for the others. The facts document says a new
  fact's sidecar names its rows **in full**, so the sidecars and the document disagree; the
  bytes are the judge and the labels stay untouched, so the oracle compares every field entry
  the label **names** (`body.preamble_epilogue`'s sparse convention) and reports the measured
  entries the label omits. See the turn report; the label ledger proves the sidecars are
  byte-identical.
* **The advisory stdlib address diff (printed, never gated).** Command:
  `python -m pytest tests/test_addresses.py::test_the_advisory_stdlib_diff_is_printed_never_gated -q -s`.
  Over **179** address fields (every fixture, every `From`/`To`/`Cc`…), the own tokenizer and
  `email.utils.getaddresses` disagree on **5** fields, each a catalogued shared misreading:
  `address_group` (`group_flattened`: the stdlib hoists the members and drops the group row),
  `address_undisclosed_recipients` (`empty_group_lost`: `''`), `address_unparsable`
  (`garbage_passthrough`: `not-an-address`), `address_idn_domain` and
  `address_smtputf8_local_part` (`smtputf8_mangled`: the stdlib is fed latin-1 and does not
  keep a non-ASCII local part or IDN domain verbatim). Every other field agrees. `parseaddr`
  loses the byte span on **2 of 179** fields (D2 needs one), and the one asserted property --
  the own tokenizer never drops an address the stdlib cannot locate -- holds.
* **The fuzz loop is seeded and bounded.** `Random(12_1002)`; **7520** seeds (179 mutated
  address-field values + 9 adversarial inputs, 40 mutations each). No defect found: the
  tokenizer never raised, every span lay inside the value, sliced to non-empty bytes, and the
  top-level spans stayed ordered and disjoint. Runtime ~0.4 s.
* **The tokenizer is linear.** `tests/test_addresses.py::test_the_tokenizer_is_linear_in_the_input`
  doubles a 30 000-byte run of `(`, `\`, `<`, `"` and a 30 000-byte address list and measures
  the best of five; every ratio is ~2.0 (a quadratic scanner would show ~4.0), so no run of a
  repeated delimiter blows up. Runtime ~2.7 s.

## Turn 1.3 — the date parser, its two live facts and the advisory stdlib diff

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.3; the
command and its output are the record. Both interpreters run the suite; the values below are
identical on CPython **3.14.3** and **3.11.15** (the code imports the stdlib `email` nowhere and
uses only its own integer calendar arithmetic, so the date rules cannot drift between them).

* **The L1 oracle now compares 8 more facts, all green.** Command:
  `python -m emailextract.evals`. Output (both interpreters identical):
  `L1 matched=792 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=140, phase 3=26`.
  Before this turn the gate was `matched=784`, `not_yet: phase 1=148`; the 8 newly-live sidecar
  facts are `headers.date` (the 6 fixtures that carry it: `date_stated_zone`, `date_minus_zero`,
  `date_absent`, `date_invalid`, `date_offset_out_of_range`, `headers_plain_baseline`) and the
  two `gaps.later` rows (`headers.no_date` on `date_absent`, `headers.invalid_date` on
  `date_invalid`).
* **The `parsed_value` column is now complete.** From `emailextract.evals.l1.deferral_counts()`:
  `{}` — Turn 1.2 emptied the `address_list` half and Turn 1.3 the `date_time` half, so every
  `headers.projection` row is compared in full (the 12 `date_time` rows included).
* **The advisory stdlib date diff (printed, never gated).** Command:
  `python -m pytest tests/test_dates.py::test_the_stdlib_date_diff_is_recorded_only -q -s`.
  Over **89** Date fields (every fixture, including the five `fixtures/time/` ones), the own
  parser and `email.utils.parsedate_to_datetime` disagree on **4** fields, each a catalogued
  shared misreading: `date_invalid` and `date_offset_out_of_range` (`invalid_repaired` /
  `offset_out_of_range_applied`: the stdlib raises `ValueError` where the design declines with a
  reason), and `date_minus_zero` and `time/date_no_zone` (`minus_zero_read_as_plus_zero` /
  `no_zone_is_naive`: the stdlib returns a **naive** datetime because `parsedate_tz` rewrote the
  `-0000` token to offset 0, while the own parser keeps `zone_stated_minus_zero` with the instant
  a `+0000` would give). Every one of the other **85** fields agrees. The one asserted property —
  `tests/test_dates.py::test_a_reason_id_where_parsedate_to_datetime_raises` — holds over the
  **4** raising/naive fields: the own parser never raises and never returns an epoch.
* **The fuzz loop is seeded and bounded.** `Random(13_1003)`; **4000** seeds (89 mutated
  Date-field values + 11 adversarial inputs, 40 mutations each). No defect found: the parser
  never raised, every result was a record, and every `utc` was a well-formed RFC 3339 `+00:00`
  instant (a leap second's `:60` allowed) or an `["unknown", reason]` pair with a registered
  reason. Runtime ~0.1 s.
* **The parser is linear.** `tests/test_dates.py::test_the_parser_is_linear_in_the_input` doubles
  a 100 000-byte run of `(` (one nested comment), `(a)` (many comments) and `9` (one huge word)
  and measures the best of five; the ratios are **1.97**, **1.87** and **2.05** (a quadratic
  scanner would show ~4.0), so no run of a repeated delimiter blows up. Runtime ~0.9 s.
* **The interpreter and patch level** (`CPython 3.14.3` / `CPython 3.11.15`) are a recorded-only
  run input, never keyed on; the two runs' date results are identical.

## Turn 1.4 — the per-part text projection, the alias table and the offset map

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.4; the
command and its output are the record. Both interpreters run the suite and the values below are
identical on CPython **3.14.3** and **3.11.15** (the module imports no stdlib ``email``, and its
only version-sensitive input is the ``codecs`` table, which is the same on both).

* **The L1 oracle now compares 9 more facts, all green.** Command:
  `python -m emailextract.evals` (output sha256
  `3409d6f51ed5f74f2121239a79e81aac2be38119cb9387736fc860a119eaaa10`). Output: `L1 matched=801
  mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=131, phase 3=26`. Before this turn
  the gate was `matched=792`, `not_yet: phase 1=140`; the 9 newly-live sidecar facts are
  `body.text` (8 sidecars: `body_plain_multipart_baseline` 2 rows and 6 raw-body fixtures) and
  the one `gaps.later` row (`body.flowed_reflow_unresolved` on `flowed_unstuffed_soft_break`).
* **The corpus's text projection, counted.** Over the 90 committed fixtures the walker measures
  **180 parts**; **103** of them are text parts and carry a `body.text` row. **95** are `exact`
  (identity CTE, stateless charset, strict decode, and a map that validates structurally) and
  **8** are `part_level`: 4 `cte_not_identity`, 3 `decode_fallback`,
  1 `multibyte_without_offset_map`. Command: the `corpus_text_parts` sweep in
  `tests/test_text.py` (walking the corpus once) plus `python -m emailextract.evals`.
* **The stdlib text comparison, extended (the third comparison's text half).** Command:
  `python -m pytest tests/test_text.py -q`. Over the 90 fixtures, **73** benign leaf texts are
  comparable and **every one agrees**, byte for byte, between
  `tests/support/stdlib_scanner.py`'s own reading and `text.py`. **11** closed exclusion reasons
  fire over the corpus (`non_identity_cte` 18 fixtures, `decode_fallback` 4, `truncated_base64`
  3, `leaf_count_mismatch` 3, `no_recursion` 2, `flowed` 1, `malformed_qp` 1,
  `stateful_charset` 1, `leading_bom` 1, `malformed_header_line` 1, `unknown_charset` 0-but-
  registered): each is a case where the two read different bytes or the stdlib shares the
  misreading, so a comparison would prove nothing. Two of them were found by *running* the
  comparison rather than by reasoning: the stdlib reads a leading UTF-8 BOM plus the first
  header line as the body (`leading_bom`), and a NUL in a field name ends its header block
  earlier than the walker's fail-open rule does (`malformed_header_line`).
* **The fuzz loop is seeded and bounded.** `Random(20250304)`; **3536** seeds (34 charset
  spellings — the alias table's 26 rows plus 8 junk/unknown names — × 4 CTEs including
  `x-uuencode` × flowed on/off × 13 bodies, with per-seed byte mutations and truncations). No
  defect found: the analyser never raised, every `exact` result satisfied all five properties,
  every `part_level` result carried no map, and decoding twice gave an identical record. A
  planted raiser in `_merge` makes the fuzz fail with the seed, so the loop is not vacuous.
  Runtime ~1 s.
* **The decode and the map are linear.** `tests/test_text.py::test_the_decode_and_the_map_are_linear_on_a_megabyte_body`
  doubles a 1 MB body of `A` and a 1 MB body of `€` and measures one pass each:
  ascii **0.289 s → 0.556 s** (1.92×) and multibyte **0.987 s → 2.209 s** (2.24×). A quadratic
  map would show ~4× or worse, so no body size blows the map up; the map is one entry per run,
  and the all-one-byte-per-code-point case (the 1 MB ASCII body) is a single entry.
* **The interpreter and patch level** (`CPython 3.14.3` / `CPython 3.11.15`) are a recorded-only
  run input, never keyed on; the two runs' text results are identical.

## Turn 1.5b — the referenced-cid set, the alternative grouping and the display rule

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.5b; the
command and its output are the record. Both interpreters run the suite and the values below are
identical on CPython **3.14.3** and **3.11.15** (`selection.py`, `htmltree.py` and `htmltext.py`
import only the stdlib `html.parser`/`html`, which is the interpreter-sensitive input here).

* **The L1 oracle now compares 23 more facts, all green.** Command:
  `python -m emailextract.evals` (output sha256
  `936776b42a105a559112315457b9511d999d346aa46b8cd084761d848e058fc7`). Output:
  `L1 matched=824 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=108, phase 3=26`.
  Before this turn the gate was `matched=801`, `not_yet: phase 1=131`. The 23 newly-live
  sidecar facts are `body.html_spans` (9 rows over 4 fixtures), `body.selection` (4 fixtures),
  `body.alternative_group` (3 fixtures), `body.cid_refs` (3 fixtures),
  `body.plain_effectively_empty` (2 fixtures) and the four `gaps.later` rows this turn's gap
  channel emits (`security.remote_content_present` on 3 fixtures, `body.inline_data_uri` on 1,
  `body.digest_default_not_applied` on 1, `body.no_text_part` on 1).
* **The five frozen `body.html_spans` rows were corrected before this turn.** Commit `b46949c`
  fixed the two sidecars the Turn 1.5a finding named (`html_style_and_script` rows 0 and 4,
  `html_href_img_remote_and_cid` rows 1, 2 and 3) and updated
  `tests/test_htmltext.py::FINDING_ROWS` to assert agreement. So the oracle compares **every**
  row: there is no `UNCOMPARABLE` mapping and the gate is `mismatched=0` over the whole corpus.
* **The HTML corpus, counted.** Command: the `corpus_html_parts` sweep in
  `tests/test_selection.py` (walking the corpus once). Over the 90 committed fixtures there are
  **15** parts the walker reads as `text/html` (exactly one per fixture) and **8** parts it reads
  as `multipart/alternative`. The selection stage emits **17** `body.alternative_group` rows,
  **102** `body.selection` rows (8 `selected`, 9 `alternative_not_selected`, 85 `n/a`),
  **5** `body.cid_refs` rows and **2** `body.plain_effectively_empty` rows; the oracle compares
  only the rows a sidecar types (the labels are the judge where they exist).
* **The stdlib HTML comparison (the third comparison's HTML half).** Command:
  `python -m pytest tests/test_selection.py -q`. All **15** HTML parts are comparable and every
  one agrees, tag multiset and `id` set, between `tests/support/stdlib_scanner.py`'s own
  start-tag events and the own tree. **0** closed exclusion reasons fire over the corpus
  (`element_count_cap`, `duplicate_id_attribute`, `misnested_input`, `unclosed_container`); each
  of the four is reachable on hand-typed input, so the exclusion list is exercised, not decorative.
* **The fuzz loop is seeded and bounded.** `Random(20250315)`; **1140** seeds (19 bases — the 15
  corpus HTML texts plus empty, an element-count bomb and two 2 000-character attribute values —
  × 60 mutants, with byte flips, truncations, repeats and swaps, injected unclosed tags and
  quotes, NULs and an Arabic-Indic digit in a numeric position). No defect found: projecting never
  raised, every span nested and stayed in range, projecting twice gave an identical projection,
  the walk/selection path never raised, and every gap a fuzzed input emitted was registered. A
  **100 000**-deep `<div>` bomb is a recorded cap (`depth_cap`) and a 100 000-character attribute
  value is one element with a long value. A planted raiser in `_TreeBuilder._apply_implied_end`
  makes the fuzz fail with the seed, so the loop is not vacuous. Runtime ~2.6 s.
* **The projection is linear.** `tests/test_selection.py::test_the_html_stages_are_linear_on_a_megabyte_body`
  projects a 1 MB and a 2 MB body of `<p>x</p>` at 131 072 and 262 144 elements:
  **1.544 s → 2.989 s** (1.94×). A quadratic pass would show ~4× or worse, so no body size blows
  the tree up.
* **The corpus projection hash is interpreter-stable.** Command:
  `python tests/support/html_projection_hash.py` and the same file under
  `py -V:Astral/CPython3.11.15` both print the sha256
  `c7862f370d94066222e041b2769d9aeb250f693eb0d3fc77915bafc686b8b566` over the 15 HTML parts'
  projections. The check runs the file under a second CPython and fails loudly on any
  disagreement (it never silently runs one interpreter twice and calls it "both").
* **The interpreter and patch level** (`CPython 3.14.3` / `CPython 3.11.15`) are a recorded-only
  run input, never keyed on; the two runs build byte-identical projections over the whole corpus.

## Turn 1.5c -- limits enforcement (all seven caps live)

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.5c; the
command and its output are the record.

* **Every cap is now enforced and recorded.** Commands: `python -m pytest tests/test_limits.py -q`
  (**32 passed**) and `python -m pytest -q` (**1495 passed, 1 skipped**, 38.8 s on CPython 3.14.3
  and the same 1495/1 in 44.3 s under the CPython 3.11.15 venv). The 32 tests cover each cap's
  boundary at / one below / one above, the five cap fixtures, the two caps in one run, the seeded
  mutated-fixture × random-Limits loop, the tiling of every capped result, and the nine
  mutation cases with the anti-vacuity triple.
* **The frozen reading does not move.** `python tools/update_behavior_ledger.py --check` exits
  **0** before and after, with **no new ledger lines**: the `walk` and `decode_chain` lines and
  the `contracts` fingerprint (`786b311fe418b90f84f7634c4edec111d92796395929295e46225feea8c91f59`,
  the recorded `OUTPUT_SCHEMA_VERSION` 4) are byte-identical. `python -m emailextract.evals`:
  `L1 matched=1147 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=192, phase 3=26`
  before and after; `no-silent-drop pass fixtures=119 bytes=79328 mutation-checks=pass`.
  The turn's own proof: for **all 119** fixtures, `walk(container)` and
  `walk(container, limits=Limits.untrusted())` compare **equal** -- which also proves the
  streamed decoder equals the whole-buffer one over the whole corpus.
* **The five cap fixtures' measured values** (from the walker, uncapped): `cap_deep_nesting`
  reaches depth **6** in **6** parts; `cap_large_part_count` has **10** parts;
  `cap_enormous_header_block`'s header region is **5 982** bytes; `cap_very_long_base64_run`
  decodes its **5 466**-byte body to **4 096** bytes; `cap_encoded_word_bomb`'s header region
  is **303** bytes. Each records its cap at one below the measured value and **nothing** under
  `Limits.untrusted()`.
* **Work is linear under a cap, measured with the step counter (never a clock).** A boundary
  storm of 50 000 delimiter+part line pairs costs **250 082** steps and 100 000 pairs
  **500 082** (exactly 2.00×, ~1.1 s); a 1 000-level nested-multipart bomb costs **31 936**
  steps and a 20 000-level one **639 936** (20.0× the input, 20.0× the steps) -- because the
  depth cap of 8 stops the descent, both emit the same **8** parts and one `depth_cap`. The
  per-level cost is the level's own body scan, so the bound is `4 × (cap + 1) × lines`, not
  the input's depth squared.
* **The capped walk is interpreter-stable.** The same capped walks (the five cap fixtures under
  the cap each was built for, plus inline boundary messages) hash to
  `07ff3869031ff40e9fd5f36592b268dd8ec91bd97ad290b226f72b4ab7a65f05` under CPython 3.14.3 and
  under CPython 3.11.15, and the test fails loudly on a disagreement.
* **The contract shapes did not move, and could not.** `behavior_ledger.contract_records()`
  hashes the dataclasses of `model`, `timeevent`, `ids`, `walk`, `store`, `siblings` and
  `seam` -- so a new field on `WalkResult` moves the `contracts` fingerprint, and so does
  **importing a contract dataclass into a fingerprinted module** (Turn 1.5c's `walk.py` reaches
  `Limits` as `parse.Limits` for exactly that reason). The cap hit therefore rides the existing
  `Region`/`UnknownSection` shapes and `evals/gates.py` is unchanged.
* **Decode chunk size: `walk.DECODE_CHUNK` = 8 192 input bytes**, and the recorded
  `declared_size_bytes` of a decoded cap is the skipped region's span length -- the part's
  **encoded** body length, an exact, already-measured bound on its decoded size.
