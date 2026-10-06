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

## Turn 1.8 -- the attachment manifest, its five facts and the fuzz

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.8; the
command and a sha256 of its output are the record.

* **The five attachment facts are live and the corpus is green.**
  `python -m pytest -q` -> **1560 passed, 1 skipped** in 61.8 s on CPython 3.14.3, and the same
  **1560 passed, 1 skipped** in 62.6 s under the CPython 3.11.15 venv. `python -m pytest
  tests/test_attach.py -q` -> **65 passed**: 58 test functions, one of them parametrized over
  the eight emitted gap ids (65 collected ids). Command: `python -m emailextract.evals` ->
  `L1 matched=1176 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=163, phase 3=26;
  no-silent-drop pass fixtures=119 bytes=79328 mutation-checks=pass`, output sha256
  `923af1ee4c647b8d788ad06fd8ad6b78f640cb0d4f36565b3566b7f9b26ae723` -- **byte-identical under
  CPython 3.11.15** (same hash). That is **29 more compared facts** than the 1147/0/{1:192, 3:26}
  Turn 1.5c recorded, and 29 fewer `not_yet`: the five facts' 29 committed rows.
* **The attachment rows hash to one value on both interpreters.** Command:
  `python -c "import sys; sys.path.insert(0,'tests'); import test_attach as T;
  print(T.attach_corpus_hash())"` -> `c39325c9cc5ad311b20e2d003a0985febefeeba7fbcb27904c3250a13c29419b`
  (the same string from the CPython 3.11.15 venv). The hash covers the five facts' rows, the gap
  pairs and the cap records of every one of the 119 fixtures.
* **The committed corpus's attachment coverage** (rows per fact over `fixtures/**/*.expected.json`,
  excluding `real/`): `attach.manifest` **9 sidecars / 15 rows**, `attach.types` **5 / 6**,
  `attach.filename` **2 / 2**, `attach.decorative` **1 / 1**, `attach.cid_use` **2 / 2**. Every
  one is below the floor `docs/design/phase1-facts.md` declares for it (10, 12, 10, 4, 5): the
  Turn 1.0c "floors re-based after the quote increment" finding, unchanged by this turn.
* **The independent check compares 115 of 119 fixtures.** Every fixture's attachment leaves are
  compared to the stdlib's own `compat32` walk (count, order, decoded sha256, decoded size and
  declared content type) with four excluded, each under a closed reason: two `no_recursion`
  (the stdlib descends into `message/rfc822` and hands back the nested `Message` list, so it has
  no payload bytes at all), one `digest_default` (the package records `Content-Type` `None` for a
  digest child, the stdlib applies RFC 2046 5.1.5 and calls it `text/plain`) and one
  `text_calendar_view` (the package reads every `text/*` leaf as a body view; this scanner's own
  statement excludes only `text/plain`/`text/html`). A planted wrong size flips it.
* **The fuzz: 48 seeds, one mutation of an attachment fixture each, 0.06 s.** Seed `n` mutates a
  fixed fixture with `random.Random(n)`, twice, from nine mutation kinds (byte flips, truncation,
  a repeated/swapped chunk, a 200-character `filename=` value, a NUL in a header name, an Arabic-
  Indic digit `size=` parameter, a signature one byte late, a truncated PNG signature, a 1x1
  header with a zero height). No seed raises; the recorded read lengths never exceed 24 bytes
  (`IMAGE_HEADER_BYTES`) while the magic reads are exactly 16 (`MAGIC_PREFIX_BYTES`); a planted
  raiser on the third call is reported as `seed 2 on <fixture>: RuntimeError: planted raiser`.
* **The work is linear in the parts, measured with the bounded-read counter (never a clock).**
  Four occurrences request **128** bytes and sixteen occurrences request **512** -- exactly
  `4.00x`, i.e. 32 bytes per occurrence (16 for the magic, 16 for the TNEF prefix; an image
  header adds 24+16 for the candidates), whatever the payload sizes are. Across the whole fuzz,
  `sum(requested) <= 100 x occurrences + 100` holds with no seed near the bound.
* **The two ledgers.** `python tools/update_behavior_ledger.py --check` exits **0** before and
  after with no new lines: the `walk`, `decode_chain` and `contracts` fingerprints do not move
  (no version constant changed and no fingerprinted module changed). `python
  tools/update_label_ledger.py --check` exits **0** after an explicit one-off rewrite of exactly
  two entries -- `emailextract/evals/l1.py`
  `c99cff7edb54...` -> `b144a81900b8...` and `tests/support/stdlib_scanner.py`
  `7d65f5400e98...` -> `b905e9580126...` -- with **all 119** `fixtures/**/*.expected.json`
  entries byte-identical (proved: the ledger diff is two `-`/`+` line pairs and no other line
  moves; every sidecar's recorded hash equals its file's bytes).

## Turn 1.6 -- the TEXT quote families, the level rule and the work budget

The rules are the build spec's decision 3 (families v1, text half), the signed spans Q1/Q5/Q7
and decision 2 (ordinals, the derived level, the disagreement predicate). This section records
the **recorded-only run inputs**, the **measured numbers** and the **work budget**; every
number carries the command that produced it.

* **Recorded-only run inputs.** CPython 3.14.3 (`python`, the interpreter the numbers below
  come from) has `unicodedata.unidata_version` **16.0.0**; CPython 3.11.15 (the second pinned
  interpreter, `C:/Users/ivan_/AppData/Local/Temp/wbv311/Scripts/python.exe`) has **14.0.0**.
  The full suite is green on both (1591 passed, 1 skipped on each), and
  `tests/test_quote_text.py::test_the_quote_rows_are_identical_on_both_interpreters` pins the
  quote output over the whole corpus with one digest, so an NFC or `str.lower()` difference
  between the two Unicode databases would be a failure, not a silent difference:
  sha256 of `{stem: [quote_boundary_rows, view_level_rows, gap_pairs]}` over the 119 fixtures
  (`json.dumps(..., sort_keys=True, ensure_ascii=False)`) =
  **eb635f72cf17dab7c0a2469f2f7133ecfd010d2a73b8301087ebc4b44a78bf7d**.
* **The L1 result against the quote catalogue, as measured (label-blind).** `python -m
  emailextract.evals` reports `matched=1197 mismatched=27 unmeasurable=0 unmodelled=0`, with
  `not_yet: phase 1=115, phase 3=26`; 19 of the mismatches are `body.quote_boundaries` and 8
  `body.view_levels`, over the 19 catalogue stems named in `tests/test_l1_gate.py`. The evidence
  names the stem, the fact, the row index, the differing column's **name** and this turn's
  measured value and never a labelled one, so the numbers can be recorded without revealing a
  label. The four patterns are the turn's findings for the reviewer (the rules were written
  without reading any catalogue label, per decision 13); no rule, threshold or span convention
  was adjusted to move one.
* **The work budget and its exact counts (item 8a).** `text_rules.WORK` is the walker's own
  `WorkCounter` pattern (reset/read by a test, never a clock): one step per line read and one
  per character examined in a prefix run. Measured with `.scratch/quote_work.py` (inline
  messages, one text part each, CRLF, `text/plain; charset=utf-8`):

  | input | 1000 lines | 2000 lines | 4000 lines | ratio |
  |---|---|---|---|---|
  | `> line N` (a `>` run) | 4000 steps | 8000 | 16000 | exactly 2.0000 |
  | `On day N, nobody ...` (never `wrote:`) | 2000 | 4000 | 8000 | exactly 2.0000 |
  | `Novel: value N` (label-shaped, unblocked) | 2000 | 4000 | 8000 | exactly 2.0000 |

  A single line of 200 000 `>` characters costs exactly **200 003** steps in 0.071 s; one line
  of 1 000 000 characters that is not a prefix costs **2** steps in 0.211 s. The part-level
  ceiling is `Limits.max_field_work_units_per_byte` (**64**) work units per text code point --
  the caller's own number, re-used rather than invented -- so a 1e6-code-point part has a budget
  of 64 000 000 and every input above is far inside it. **Not done this turn:** the budget's
  *hit* is not yet recorded in the closed cap vocabulary (there is no quote-stage reason id;
  `Limits` has no field for it either), the mutation catalogue (item 8b) and the seeded fuzz
  (item 8c) are not built, and the assembled record does not yet carry the quote facts (Turn
  1.9). The turn reported these as open.
* **The two ledgers.** `python tools/update_behavior_ledger.py --check` exits **0** before and
  after with no new lines: `walk`, `decode_chain` and `contracts` do not move (the quote stage
  is not one of `contract_records()`'s fingerprinted modules, and no version constant it keys
  changed). `python tools/update_label_ledger.py --check` exits **0** after an explicit one-off
  rewrite of exactly **one** entry -- `emailextract/evals/l1.py` `b144a81900b8...` ->
  `7f6d3d8c2392...` -- with **all 119** `fixtures/**/*.expected.json` entries byte-identical
  (proved: the ledger diff is one `-`/`+` line pair and no other line moves).

## Turn 1.6b -- the adjudicated conventions, the mutation catalogue, the fuzz and the budget stop

This turn implements the reviewer's adjudication of Turn 1.6's 27-row disagreement against the
bytes (build-spec decisions 33-39) and finishes 1.6's items 8b/8c/8d. The rules stay label-blind:
the conventions are prose from the decisions and the catalogue is never read. Every number below
carries the command that produced it.

* **Recorded-only run inputs.** The same two interpreters (CPython 3.14.3 and 3.11.15, Unicode
  16.0.0 / 14.0.0). The full suite is green on both (**1626 passed, 1 skipped** on each), and the
  quote output's single digest over the 119 fixtures
  (`tests/test_quote_text.py::test_the_quote_rows_are_identical_on_both_interpreters`,
  sha256 of `{stem: [quote_boundary_rows, view_level_rows, gap_pairs]}` with `sort_keys=True`,
  `ensure_ascii=False`) is **a171f158888bc927087fc596835e953f9f6749cf24981a2fe40b9902b7d5dbbe** --
  identical on both, so no rule of this turn moves with the Unicode database.
  `QUOTE_RULES_VERSION` moves **"1" -> "2"** (span conventions, absorption and the resolution
  rule changed); the walker's constants do not move with it (the walk/decode fingerprints below).
* **The L1 result against the quote catalogue, as measured (label-blind).** This turn's rules left
  `matched=1217 mismatched=7 unmeasurable=0 unmodelled=0` with `not_yet: phase 1=115, phase 3=26`,
  identically on 3.14.3 and 3.11.15: all 7 were `body.quote_boundaries` rows, with
  `body.view_levels` matching on every stem and the evidence carrying stem + fact + row + column +
  this turn's **measured** value, never a labelled one. **Finding.** Each of the 7 was a hand-typed
  `prefix_depth` counting one line more than the body has: four (`gmail_quote_on_blockquote`,
  `html_gmail_quote`, `outlook_com_appendonsend`, `vendor_prefix_class_no_table_row`) carry
  **byte-identical** plain text to `mixed_origin_quote`, whose label the correction did reach, and
  `html_outlook_divrplyfwd` is byte-identical to `quoted_outlook_flat`; no rule can satisfy two
  labels that disagree on the same bytes. The catalogue's own consistency checker
  (`tests/test_quote_catalogue.py::quote_problems`, corrected this turn to the walker's physical
  lines -- no phantom trailing line) reported those 7 stems (8 rows) **and** a ninth, html-view row
  (`thunderbird_moz_forward_container` part 1.2 typed 2 depths for the one-line span
  `"The forwarded note.\r\n"`). The reviewer's label correction fixed the 8 from the bytes and this
  correction pass took the ninth with them, so `python -m emailextract.evals` now reports
  **`matched=1224 mismatched=0 unmeasurable=0 unmodelled=0`, `not_yet: phase 1=115, phase 3=26`** on
  both interpreters: the corpus is green with the quote facts live, and
  `tests/test_l1_gate.py::test_the_committed_corpus_is_green_with_the_quote_facts_live` pins it.
* **The mutation catalogue (item 7a).** `tests/test_quote_text.py`'s `MUTANTS` holds **20**
  careless readings, keyed by the rule each breaks. All **8** rule ids the TEXT stage can emit
  (`text_rules.SCAN_RULES`) have at least one case
  (`test_every_quote_rule_id_has_a_mutation_case` asserts the coverage); the extras cover the
  interleaving, i18n, resolution-rule and view-row rules and the two anti-patterns
  (`str.splitlines` as the line model; a nested-quantifier regex, which a 26-`>` ReDoS input
  defeats in ~2 s while the anchored scanner takes microseconds). Each case names the fixture
  that types the rule (the L1 gate must flip, naming a quote fact) or an inline label-blind
  observation (which must move), and the **anti-vacuity triple** is asserted: the patched symbol
  exists (`monkeypatch.setattr`), the patch was **reached** (a counter), and the observation
  differs from the baseline.
* **The seeded fuzz (item 7b).** `tests/test_quote_text.py::_fuzz_fixtures`, seed **20250304**,
  **8** mutations per fixture over all **119** fixtures = **952** cases, **0** failures in
  **0.30 s** on 3.14.3 (mutation kinds: byte flips, truncation, a repeated chunk, swapped chunks,
  an injected `>` run, NBSP + NULs, a giant line, non-ASCII digits). The invariants: no exception,
  every returned span inside the view's text, and quote ordinals that strictly increase from 1.
  `test_a_planted_raiser_fails_the_fuzz_with_the_seed` patches the scanner to raise and asserts
  the fuzz reports the failure **with its seed**, so the harness is able to fail.
* **The work budget's hit (item 7c) -- the owner's ruling.** `tests/test_quote_text.py::
  test_the_work_budget_stops_the_scan_and_the_stop_is_reported` pins today's behaviour: the
  scanner stops cleanly, `ScanResult.truncated` reports the stop and every span stays inside the
  text. It is **not** recorded in the closed cap vocabulary: the five `Status.SKIPPED` reasons
  (`size_cap`, `total_size_cap`, `depth_cap`, `part_count_cap`, `header_bytes_cap`) are keyed on
  `Limits` fields (`CAP_LIMIT_FIELDS`) and none of them is the quote stage's per-code-point step
  ceiling (`Limits.max_field_work_units_per_byte`), so no existing closed id fits. Asked, the
  owner ruled **keep today's behaviour** (the stop is reported and tested; no
  `UnknownSection`/`CapRecord` until an owner names a reason id, which is a `model.REASON_TABLE`
  decision for a later turn), and no id was invented.
* **The two ledgers.** `python tools/update_behavior_ledger.py --check` exits **0** on both
  interpreters, with no new lines: `walk`, `decode_chain` and `contracts` do not move (a
  `QUOTE_RULES_VERSION` bump is not one of the fingerprinted components). `python
  tools/update_label_ledger.py --check` exits **0** over **131** entries with **none added, none
  removed and 20 changed** (the tool refuses to write a changed recorded file, so each rewrite is
  explicit and named in an allow-list): `emailextract/evals/l1.py` (this turn's evidence; the hash
  the correction left is `8f530e48bfdc...`) and **19** sidecars -- the **18** the reviewer's label
  correction recorded, plus
  `fixtures/generated/thunderbird_moz_forward_container.expected.json` for the ninth phantom row
  (recorded `7adb326ad1c3...`, rewritten to `d8241ca586d2...`). Proof, the same shape the 1.6
  section used: a script diff of the ledger against `HEAD` reports exactly those 20 keys, and
  `git diff --name-only HEAD -- fixtures` reports exactly those 19 sidecars.

## Turn 1.7 -- the DOM family on the html view, its span conventions and the red rows

The rules are the DOM half of build-spec decision 3 and decisions 2/15/28-39, read on the HTML
projection; the choices the prompt left open are the new decisions 40-47. The rules were written
**blind** (no quote-catalogue sidecar, no `body.quote_boundaries`/`body.view_levels` entry was
read). Every number below carries the command that produced it.

* **Recorded-only run inputs.** The same two interpreters (CPython 3.14.3, Unicode 16.0.0, from
  which the numbers below come -- `python` on this machine -- and CPython 3.11.15, Unicode 14.0.0,
  `C:/Users/ivan_/AppData/Local/Temp/wbv311/Scripts/python.exe`). The full suite is
  green on both (**1664 passed, 1 skipped** on each); `dom_rules` uses no
  `unicodedata` and no `str.lower()` on the projection, so the two are expected to agree, and the
  cross-interpreter test pins it: `tests/test_quote_dom.py::test_the_dom_rows_are_identical_on_both_interpreters`
  is sha256 of `{stem: [all_quote_boundary_rows, all_view_level_rows]}` (both views) over the 119
  fixtures with `json.dumps(..., sort_keys=True, ensure_ascii=False)` =
  **c563380b409d0cc51b89c7eb7fce8bd6912638fa0e6c237576eedeb5a23bd99b**, identical on both.
  (**Turn 1.7b moves this digest** -- the three amended DOM span conventions below -- and this line
  records 1.7's value.)
  The plain-view digest of Turn 1.6b (`a171f158888bc927087fc596835e953f9f6749cf24981a2fe40b9902b7d5dbbe`,
  `tests/test_quote_text.py`) is **unchanged**: the plain rules were not touched.
  `QUOTE_RULES_VERSION` moves **"2" -> "3"**; `HTMLTEXT_VERSION`, `EMAIL_PARSER_VERSION` and
  `OUTPUT_SCHEMA_VERSION` do **not** move. (**Turn 1.7b moves it "3" -> "4"**, above.)
* **The L1 result against the quote catalogue, as measured (label-blind).** `python -m
  emailextract.evals` reports `matched=1216 mismatched=8 unmeasurable=0 unmodelled=0` with
  `not_yet: phase 1=115, phase 3=26`, identically on 3.14.3 and 3.11.15, and the CLI exits **1**.
  (**Turn 1.7b: `matched=1224 mismatched=0` and the CLI exits **0**, below** -- the reviewer's
  adjudication corrects the three conventions.)
  All 8 are `body.quote_boundaries` mismatches on **html** rows, one per stem, over
  `gmail_quote_on_blockquote`, `gmail_reply_quoting_outlook_authored`,
  `gmail_short_reply_gt_and_on_wrote`, `html_gmail_quote`, `html_outlook_divrplyfwd`,
  `mixed_origin_quote`, `outlook_com_appendonsend`, `thunderbird_moz_cite_prefix`. `body.view_levels`
  matches on every stem, and every html ``ordinal``/``rule_id``/``prefix_depth``-count judgment
  agrees except the two noted below. The evidence carries stem + fact + view + row + column +
  this turn's **measured** value and never a labelled one. **Finding (the turn's honest red state):**
  the prompt names decision 34 for the DOM span ends and the code applies it (decision 40), so a
  boundary whose last covered line is the projection's final line carries that line's terminator;
  **6** differences are that convention on ``span_length`` -- measured 65 (`gmail_quote_on_blockquote`),
  112 (`gmail_reply_quoting_outlook_authored`), 64 (`gmail_short_reply_gt_and_on_wrote`),
  67 (`html_gmail_quote`), 95 (`html_outlook_divrplyfwd`) and 71 (`mixed_origin_quote`) -- and **2**
  are ``prefix_depth`` on the Outlook span convention of decision 41
  (`outlook_com_appendonsend` measured `[0, 0]`) and on the bare-``blockquote`` sibling of
  decision 42 (`thunderbird_moz_cite_prefix` measured `[0]`). No rule, threshold or span convention
  was adjusted to move one; the plain rows all still match, so the pre-existing 1224 matches do not
  regress (1216 matched + 8 mismatched = 1224 compared).
* **The step budget (item 7a).** `dom_rules.WORK` is the same `WorkCounter` pattern (one step per
  element, one per class token, one per projection line read), measured by
  `tests/test_quote_dom.py::test_the_dom_walk_step_count_is_exact_and_linear`: the single
  1,000,000-character class attribute costs exactly **3** steps; 1,000 / 2,000 sibling
  `blockquote.gmail_quote` elements cost **2001 / 4001** (ratio 1.9995, below the stated 2.2
  factor); 500 / 250 elements each with a 1,000-token class cost **500501 / 250251**; 1,000 bare
  `blockquote` elements cost **1000** (no tokens, no projection text); 1,000 `moz-cite-prefix`
  elements cost **2001**; and 1,000 **nested** `div`s cost **64**, because the tree's recorded depth
  cap (64) stops the tree and the walk with it -- the walk itself is a loop over the element tuple,
  never recursion (mutant `recursive_walk` fails a 2,000-deep nest with `RecursionError`).
* **The mutation catalogue (item 7a).** `tests/test_quote_dom.py`'s `MUTANTS` holds **15** careless
  readings (**Turn 1.7b makes it 18**: one per amended convention), keyed by the rule each breaks.
  All **7** rule ids the DOM stage can emit
  (`dom_rules.DOM_RULES`) have at least one case
  (`test_every_dom_rule_id_has_a_mutation_case` asserts the coverage); the extras cover the nesting,
  the raw-HTML span source, the recursion hazard and the resolution/view-row rules. Each case names
  an inline label-blind observation that must move, and the **anti-vacuity triple** is asserted: the
  patched symbol exists (`monkeypatch.setattr`), the patch was **reached** (a counter), and the
  observation differs from the baseline.
* **The seeded fuzz (item 7b).** `tests/test_quote_dom.py::_fuzz_html_parts`, seed **20250304**,
  **9** mutations per ``text/html`` part over the **26** fixtures that carry one = **234** cases,
  **0** failures in **0.12 s** on 3.14.3 (mutation kinds: byte flips, truncation, a repeated chunk,
  swapped chunks, an injected ``<div class=`` fragment, an unclosed container, NULs + an injected
  ``id=``, a giant attribute value, non-ASCII digits). The invariants: no exception, every span
  inside the projection, and quote ordinals that strictly increase from 1.
  `test_a_planted_raiser_fails_the_fuzz_with_the_seed` patches the html view's scanner to raise and
  asserts the fuzz reports the failure **with its seed**.
* **The two ledgers.** `python tools/update_behavior_ledger.py --check` exits **0** on both
  interpreters, before and after, with no new lines: `walk`, `decode_chain` and `contracts` do not
  move (a `QUOTE_RULES_VERSION` bump is not one of the fingerprinted components, and no record
  shape changed). `python tools/update_label_ledger.py --check` exits **0** after an explicit one-off
  rewrite of exactly **one** entry -- `emailextract/evals/l1.py` `8f530e48bfdc...` ->
  `0153da3a94f3...` (this turn's html-row measurers and per-view evidence) -- with **all 119**
  `fixtures/**/*.expected.json` entries byte-identical: no fixture, no `*.expected.json` and no
  other oracle file moved.

**Not done this turn (reported).** The html gaps are implemented and reported but not wired into the
oracle's `gaps.later` (decision 32); the reviewer's adjudication of the 8 rows is Turn 1.7b, and
nothing here was tuned to avoid a mismatch.

## Turn 1.7b -- the adjudicated DOM span conventions

The reviewer read the 8 html `body.quote_boundaries` mismatches above against the fixture bytes and the
signed labels and found the three span conventions of decisions 40-42 wrong (all three typed by the 1.7
prompt's prose, not read from a label). The three edits and the numbers **after** them:

* **Decision 40 amended** -- a DOM boundary's span is the element's projected extent exactly, with **no**
  final-terminator extension; decision 34's terminator clause is the line-based families' only (the
  plain view's rules and the html view's `gt_family`). This fixes the 6 `span_length` differences above:
  the label equals the element's own `body.html_spans` rectangle (`html_gmail_quote` part 1.2's
  `div.gmail_quote` is `span_offset=9 span_length=65`, its own extent, before the projection's final
  terminator). The **forward container** keeps decision 28's through-the-end-of-the-part span -- its span
  still reaches the final terminator, as the plain `forward_banner` label does -- which is why it was
  never one of the 8.
* **Decision 41 amended** -- `divRplyFwdMsg` is its own projected extent; `appendonsend`/`x_appendonsend`
  is a sentinel carrying no quoted words, so its span **starts** at its first following **element**
  sibling and **ends** at the end of its parent's projected extent (`outlook_com_appendonsend`: the
  marker is an empty `div` at offset 9, the span `span_offset=11 span_length=63 depth=[0]`). A marker with
  no following element sibling spans its own extent (zero length kept).
* **Decision 42 amended** -- a `moz-cite-prefix` pulls in its immediately following element sibling when
  that sibling is a `blockquote`, **with or without** `type=cite` (`thunderbird_moz_cite_prefix`:
  `span_offset=9 span_length=57 depth=[0, 0]`), adding no second boundary and no second ordinal; a
  following sibling that is not a `blockquote` leaves the boundary at the prefix alone.

Numbers after: `python -m emailextract.evals` reports `matched=1224 mismatched=0 unmeasurable=0
unmodelled=0` with `not_yet: phase 1=115, phase 3=26` (the html gaps stay unwired, decision 32),
identically on CPython 3.14.3 and 3.11.15. The cross-interpreter DOM digest moves
`c563380b409d0cc51b89c7eb7fce8bd6912638fa0e6c237576eedeb5a23bd99b` ->
`7e4c417a64fb6563b33200c010d43180c7f79ebdeb7d7e71183f0c75889e72f7` (identical on both), so
`QUOTE_RULES_VERSION` moves **"3" -> "4"**; `HTMLTEXT_VERSION` and the contract line do **not** move (the
projection and every record shape are untouched). The 1.7 mutation catalogue's **15** cases become **18**
(one per amended convention: the terminator extension re-added to a DOM span, the appendonsend span
starting at the marker, and the `moz-cite-prefix` requiring `type=cite`), and the 1.7 tests that encoded
the old conventions are restated for the new ones. Both ledgers are checked in the turn's report.
