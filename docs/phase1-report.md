# Phase 1 report

The close of `email-extract` Phase 1: the deterministic `.eml` parser (headers, addresses, dates,
per-part text, the HTML and plain views, the quote boundaries, the attachment manifest, the
assembled document, the ingest/store path) and the oracle that measures it. This file is committed
as the **last** artifact of the phase (`docs/design/phase1-turn-declarations.md`, turn 1.10's
`stop:` line). It is a report, not a gate: `tests/test_phase1_scope.py::
test_the_phase1_report_sections_are_present_and_non_empty` checks that the eight sections below are
present and non-empty, and names the missing or empty one; the content is the owner's review.

Inputs the sections cite, so a reader can re-run rather than trust:

* the committed corpus: **119** fixtures (81 `generated`, 33 `raw`, 5 `time`) with **119**
  sidecars; `fixtures/real/` is git-ignored and never read;
* the two pinned interpreters: CPython **3.14.3** and CPython **3.11.15**;
* the ledgers: `tests/ledger/{facts_ledger,phase1_exit,html_projection_golden,label_ledger,
  behavior_ledger,corpus}.json`;
* the tests named in each section.

`python -m emailextract.evals` (CPython 3.14.3; the counts are identical on 3.11.15), stdout
sha256 `443f30276480ddaf81fd308f3d781b872df3b1a9519ca3bdf7c05f9b5f5c22c9`:

```
email-extract: L1 gate metrics at phase 0 (corpus: <repo>/fixtures)
  L1              matched=1330 mismatched=0 unmeasurable=0 unmodelled=0
                 not_yet: phase 1=9, phase 3=26
  labels.undetermined=20 question(s) the labels leave open
  gates:
    L1             pass matched=1330 mismatched=0 unmeasurable=0 unmodelled=0 not_yet=35
    no-silent-drop pass fixtures=119 bytes=79328 mutation-checks=pass
    phase-1 gaps   pass checked 30 live phase-1 gap label(s); 0 not recorded; 1 unlabelled emission(s); skipped 0
    phase1 exit    pass wait=6 (named=6), compared=1330; extra=0 missing=0
  corpus: 119 fixture(s), 119 sidecar(s)
    generated      81 fixture(s), 81 sidecar(s)
    raw            33 fixture(s), 33 sidecar(s)
    time            5 fixture(s), 5 sidecar(s)
  falsifiability: 8 gap(s) covered by cases, 6 recorded by sidecars
  not exercised by any fixture: body.headers_only, body.no_boundary_found
```

The first line carries the absolute corpus path, so that hash reproduces on the machine that
recorded it; the counts are the portable part (they are the same on both interpreters). The
headline's own wording, "at phase 0", is a one-word label in `emailextract/evals/metrics.py:92`
that no turn has moved; it is recorded under **Not done** rather than edited, because that file is
a recorded oracle (the label ledger is additions-only).

## What was built

### The turns

Each turn's declaration block (`docs/design/phase1-turn-declarations.md`) is the binding record of
its `module:` and `test:` lines; `tests/test_turn_declarations.py` enforces both directions.

| turn | the modules it built (new in that turn in bold) | what it decided |
|---|---|---|
| 1.0b | `ids.py`, `versions.py`, `model.py`, `walk.py`, `evals/l1.py`, `evals/labels.py`, `tools/runboth.py`, `tools/update_label_ledger.py` | the Phase 1 contract shapes, the oracle, the label ledger |
| 1.0c | `tools/make_fixtures.py`, `tools/write_raw_fixtures.py`, `fixtures/**` | the fixture families and their hand-typed sidecars |
| 1.0d | `parse.py`, `versions.py`, `tools/html_experiment.py` | the entry point, `Limits`, the six named errors, the HTML parser decision (candidate A) |
| 1.1 | `headers.py`, `rfc2047.py`, `walk.py`, `tests/support/stdlib_scanner.py` | the header projection, encoded words, the BOM/mbox prelude |
| 1.2 | `addresses.py` | the address rows and the three states |
| 1.3 | `dates.py`, `headers.py` | the `Date` reading and the date gaps |
| 1.4 | `text.py` | per-part text, the alias table, the offset maps, the one line model |
| 1.5 | `htmltree.py`, `htmltext.py`, `selection.py` | the HTML tree, the projection and its node-to-span map, the selection state |
| 1.5c | `walk.py`, `parse.py` | the six remaining `Limits` caps enforced as `CapRecord`s |
| 1.6 / 1.6b | `quote/__init__.py`, `quote/i18n.py`, `quote/text_rules.py`, `quote/resolve.py` | the TEXT quote families, then the adjudicated span conventions |
| 1.7 / 1.7b | `quote/dom_rules.py`, `quote/resolve.py` | the DOM quote families, mixed-origin resolution, then the adjudicated DOM spans |
| 1.8 | `attach.py` | the attachment manifest, the type verdicts, the filename, the cid use |
| 1.9 | `assemble.py`, `ingest.py`, `store.py`, `model.py`, `__init__.py` | the document holder, the run record, the ingest manifest, the store |
| 1.10a | `evals/{l1,gates,falsify,metrics,__init__}.py`, `tests/support/html_projection_hash.py` | corpus agreement: `document.axes` measured, the phase1-exit and phase-1 gap gates, the coverage ratchet, the golden projection, the Phase 1 scope test |
| 1.10b | `tests/test_hostile_set.py`, `tests/support/boundary_splitter.py`, `tests/test_seeded_splitter_fuzz.py`, `tests/test_licence_audit.py`, `selection.py`'s work-counter seam, this report | the hostile set, the superlinearity gate, the raw-filename rule, the independent splitter fuzz, the licence audit, the close |

At the close the package tree is exactly the Phase 1 set
(`tests/test_phase1_scope.py::test_the_modules_are_exactly_the_phase_1_set`): 23 library modules,
the 5-module `emailextract/quote` subpackage, the 7-module `emailextract/evals` harness, and
`tests/support/` as the independent checkers.

### Version stamps, and why each moved

`emailextract/versions.py` is the single owner of every stamp; a stamp moves only in the commit
that changes what it names.

| constant | at close | moved by | why |
|---|---|---|---|
| `EMAIL_PARSER_VERSION` | `2` | Turn 1.1 | the walker tolerates a leading UTF-8 BOM and/or an mbox `From ` line as its own prelude region (decision 14), so the regions and the top-level header span move for those inputs |
| `DECODE_CHAIN_VERSION` | `2` | the Turn 0.4 finding | the charset ladder runs only over a text part; before, it ran over a binary payload and reported a charset, a fallback and a false `body.decode_destroyed_bytes` |
| `TEXTPART_VERSION` | `1` | — | new in Turn 1.4; the per-part projection's rule set has not changed since |
| `QUOTE_RULES_VERSION` | `4` | 1.6 → 1.6b → 1.7 → 1.7b | the TEXT rule table, then the adjudicated TEXT spans (decisions 33-39), then the DOM family and the html view, then the adjudicated DOM spans (decisions 40-42) |
| `HTMLTEXT_VERSION` | `1+htmlparser+<cpython minor>+verbatim+drop=style,script,head,comment+noelementtext+recorded-not-closed` | 1.0d, 1.5 | the projection's own key: the parser candidate, the interpreter minor, the whitespace rule, the dropped set and the unclosed-container rule (decision 1) |
| `OUTPUT_SCHEMA_VERSION` | `5` | Turn 1.9 | the document gained its quote holder; `4` was the not-built axis fields (1.0b) |
| `TEXTMODEL_VERSION`, `HEADERTEXT_VERSION`, `HTMLTEXT_SCHEMA`, `FLAG_SCHEMA_VERSION`, `TIMEEVENT_VERSION`, `MATCHER_VERSION` | `1` | — | unchanged through Phase 1 |

A stamp that did **not** move is as reportable as one that did: the quote turns moved
`QUOTE_RULES_VERSION` only, never the walker's parser or decode-chain constants, because the quote
stage reads the decoded text the body stage already produced and adds no decode rule
(`emailextract/versions.py`, `QUOTE_RULES_VERSION`).

## Named resolutions

Every ambiguity Phase 1 resolved, with the artifact that pins it. "Resolved" means a decision in
`docs/design/email-extraction-design.md` (revision 3) or an owner adjudication recorded in
`docs/design/phase1-build-spec.md`; a question that stays open is listed in **Not done**.

| ambiguity | resolution | pinned by |
|---|---|---|
| Does the charset ladder run over a non-text payload? (`label-questions.md` Q1) | No: the ladder and the offset map are built only over a **text part's** strict decode of its **used** charset, so a binary part's chain is the identity and `used_charset`/`encoding_source` stay `null` (decision 8). This **confirms** the shipped walker and is why `DECODE_CHAIN_VERSION` is 2, not a reopened defect. | `tests/test_text.py` (the five-part offset-map property test); `tests/test_l1_gate.py::test_the_committed_corpus_is_green_with_the_quote_facts_live` |
| What is `used_cte` when the declared decoding cannot run? (`label-questions.md` Q3) | `null` -- no transfer decoding was used -- and the part is `part_level` with `cte_not_identity` (or `decode_fallback` when the ladder's last resort ran), never `exact`, and no within-part byte span is emitted (decision 8). | `tests/test_text.py`; `tests/test_l1_gate.py::test_a_wrong_decode_chain_verdict_fails_the_gate` |
| Is a missing close delimiter `body.boundary_disagreement` or `body.no_boundary_found`? (`label-questions.md` Q4) | `body.boundary_disagreement`: the boundary **is** found, its close is not. `body.no_boundary_found` is the absence answer and fires only when no boundary rule fired and the text is not a label-shaped unknown-language block (decision 3). | `tests/test_seeded_splitter_fuzz.py::test_mutants_return_the_declared_failure_type` (the `NO_CLOSE` class gates the gap); `tests/test_l1_gate.py`; the registry entry in `docs/design/phase0-gaps.md` |
| Does a label-shaped unknown-language block read as "no boundary found"? | No: it records `body.i18n_reply_marker` (decision 3's trigger amendment), which is why `body.no_boundary_found`'s emission count over the corpus dropped. | `tests/test_phase1_gap_gate.py::test_the_unlabelled_emissions_are_reported`; `tests/ledger/phase1_exit.json` (`no_boundary_found`, `over-emission`) |
| Where does the report-sections test live? | `docs/design/phase1-ledgers.md` (f) names `tests/test_phase1_report.py`; the frozen declaration block names `tests/test_phase1_scope.py::test_the_phase1_report_sections_are_present_and_non_empty`. The declaration wins -- it is the enforced record -- so the test is in `tests/test_phase1_scope.py`, and this line is the deviation. | `tests/test_turn_declarations.py::test_every_declared_test_is_collected` |
| Do the design's coverage floors match the committed corpus? | They do not: the floors predate the catalogue and 11 of the 20 phase-1 facts fall short. Turn 1.10a **re-bases** each floor to the count the corpus achieves -- a ratchet, coverage may never fall -- and records every unmet declared floor rather than lowering it silently. The rebase is owner-signed. | `tests/test_facts_coverage.py::test_the_rebase_record_is_proposed_or_signed`, `::test_the_effective_floor_is_the_achieved_count_at_the_rebase`, `::test_the_declared_floors_the_corpus_does_not_meet_are_recorded` |
| Is the `.msg`/CFB route reachable in Phase 1? | No: `parse` returns `cfb_msg_unsupported` for the CFB magic and `olefile` is named in `NOTICE` but is not a dependency. | `tests/test_parse_entry.py::test_limits_construction_is_the_only_named_error_raised`; `tests/test_licence_audit.py::test_olefile_is_not_a_declared_dependency` |
| May a turn edit a label or a gate to make a gate pass? | No: the label ledger is additions-only, so a sidecar or an oracle file cannot be edited in place; the remedy is a new file or an owner-approved ledger change in the same commit. A label/parser disagreement is a finding. | `tools/update_label_ledger.py --check`; `tests/test_label_ledger.py` |
| Does the walker's lone-CR line model change to match the splitter's? | No: a lone CR is a line terminator and its use is recorded as `body.lone_cr_line_terminator` (decision 17). The independent splitter's own model is CRLF-only, so the fuzz **cannot** see a lone-CR framing bug and `tests/test_seeded_splitter_fuzz.py` records that as its own honest limit rather than pretending to cover it. | `tests/test_limits.py`; `tests/test_seeded_splitter_fuzz.py` (the `EXCLUDED` class's reason) |
| Do the quoted `body.quote_boundaries` spans follow the *label's* reading where the bytes disagree? | No: the owner adjudicated each mismatch from the bytes (decisions 33-39, 40-42) and the rule tables moved (`QUOTE_RULES_VERSION` 2 and 4); the labels are never edited. | `tests/test_l1_gate.py::test_the_committed_corpus_is_green_with_the_quote_facts_live`; `tests/test_quote_text.py`; `tests/test_quote_dom.py` |
| Is a per-stage projection version needed on the stored record? | Yes: the assembled document carries the projection versions, so a consumer can tell which version produced a stored view (the debate's risk 9, landed in Turn 1.9). | `tests/test_assemble.py`; `test_html_projection_golden.py::test_the_golden_carries_its_required_keys` |
| Which interpreter is the HTML projection keyed on? | The stdlib candidate and the CPython **minor**, not the lxml wheel (candidate A was chosen), so a projection rendered under a different minor is a different key. | `test_html_projection_golden.py::test_the_golden_rows_record_the_interpreter_minor` |

## Coverage

`tests/ledger/facts_ledger.json` is the coverage artefact (`tests/test_facts_coverage.py` re-derives
it and ratchets against it): `declared` is the floor `docs/design/phase1-facts.md` names, `floors`
is the **effective** floor the test enforces, and `achieved` is the committed corpus's count of
sidecars that label the fact and of sidecars the oracle measured.

| phase-1 fact | declared floor | effective floor | sidecars labelling | sidecars compared |
|---|---|---|---|---|
| `document.axes` | 80 | 103 | 103 | 103 |
| `headers.projection` | 60 | 12 | 12 | 12 |
| `headers.addresses` | 20 | 7 | 7 | 7 |
| `headers.date` | 12 | 6 | 6 | 6 |
| `headers.decoded` | 8 | 6 | 6 | 6 |
| `headers.parameters` | 4 | 6 | 6 | 6 |
| `body.text` | 60 | 37 | 37 | 37 |
| `body.alternative_group` | 10 | 13 | 13 | 13 |
| `body.selection` | 10 | 15 | 15 | 15 |
| `body.html_spans` | 8 | 15 | 15 | 15 |
| `body.cid_refs` | 5 | 3 | 3 | 3 |
| `body.plain_effectively_empty` | 2 | 2 | 2 | 2 |
| `body.quote_boundaries` | 15 | 24 | 24 | 24 |
| `body.view_levels` | 15 | 24 | 24 | 24 |
| `attach.manifest` | 10 | 9 | 9 | 9 |
| `attach.types` | 12 | 5 | 5 | 5 |
| `attach.filename` | 10 | 2 | 2 | 2 |
| `attach.decorative` | 4 | 1 | 1 | 1 |
| `attach.cid_use` | 5 | 2 | 2 | 2 |
| `gaps.later` | 5 | 38 | 38 | 29 |

Totals: declared **355**, effective **330**, labelling **330**, compared **321**. The declared
phase-1 fact-id list is pinned at **20** ids (`facts_ledger.json:phase1`) and the deferred set is a
closed list that is **empty** (`deferred: []`). The 11 declared-but-unmet floors are recorded in
`declared_unmet` (`attach.cid_use`, `attach.decorative`, `attach.filename`, `attach.manifest`,
`attach.types`, `body.cid_refs`, `body.text`, `headers.addresses`, `headers.date`, `headers.decoded`,
`headers.projection`); `zero_labelled` is empty, so no phase-1 fact is unlabelled. The
"at least one sidecar carries a non-trivial, non-empty value" floor and the "the sparse-fact
convention is not used for new facts" rule are asserted by
`tests/test_facts_coverage.py::test_at_least_one_sidecar_carries_a_non_trivial_value`.

The `compared` count is below `labelling` for `gaps.later` only (38 vs 29): the nine rows a frozen
sidecar asserts that no comparison can satisfy without editing a label -- the six named waits of
**Gap gate** below, plus the three whose own phase column is 3 (decision 63's class (c):
`future_date_in_text`, `rfc2047_folded_duplicate_received`, `thread_three_refs_chain`). That is
also the `not_yet: phase 1=9` the metrics table reports.

## Gap gate

`gaps.later` is the phase's gap channel. The gate (`emailextract/evals/gates.py::gap_gate`) passes
over the committed corpus (`checked 30 live phase-1 gap label(s); 0 not recorded; 1 unlabelled
emission(s); skipped 0`), and every emittable phase-1 gap id is either **cased** in
`emailextract/evals/falsify.py::PHASE1_CASES` or **named** in `UNEXERCISED_GAP_IDS` -- the two sets
tile `EMITTABLE_GAP_IDS` exactly (27 ids: 22 cased + 5 named). Each case is a mutation of a real
stage callable that drops that one emission; `tests/test_phase1_gap_gate.py::
test_a_dropped_phase1_gap_fails_the_gate` runs the gate on a one-fixture corpus, applies the
mutation, and requires the failure to name the gap id and the fixture.

| gap id | mutation case fixture | what the naive reading would do instead |
|---|---|---|
| `attach.cid_unreferenced` | `attach_decoration_tracking_pixel` | record a cid no view references without an `attach.cid_unreferenced` row |
| `attach.duplicate_content_id` | `attach_duplicate_content_id` | keep two parts with one Content-ID silently |
| `attach.filename_absent` | `attach_message_rfc822_no_filename` | invent a filename for a part that carries none |
| `attach.occurrence_repeated` | `attach_duplicate_filename_in_one_message` | record one attachment for two parts with the same filename |
| `attach.ole_container_unknown` | `attach_ole_cfb_magic` | claim the OLE container's contents (introspection declines it) |
| `attach.tnef_present` | `attach_tnef_winmail` | claim the TNEF attachment's contents (a decline, not an extraction) |
| `attach.type_disagreement` | `attach_zip_magic_declared_disagree` | prefer the declared media type over the magic |
| `body.digest_default_not_applied` | `multipart_digest_content_type_less_child` | apply the `multipart/digest` `message/rfc822` default to a Content-Type-less child |
| `body.flowed_reflow_unresolved` | `flowed_quote_depth` | reflow a `format=flowed` part's soft breaks into a joined paragraph (the v1 deferral) |
| `body.i18n_reply_marker` | `i18n_reply_marker` | present a label-shaped unknown-language block as "no boundary found" |
| `body.inline_data_uri` | `html_data_uri_and_tracking_pixel` | treat a `data:` URI as an ordinary reference |
| `body.lone_cr_line_terminator` | `lone_cr_in_header_region` | treat a lone CR as whitespace rather than a line terminator |
| `body.no_text_part` | `body_no_text_part` | claim an empty body for a message with no text part |
| `headers.address_unparsable` | `address_unparsable` | accept an unparseable address list silently |
| `headers.duplicate_header` | `duplicate_content_type_header` | take the first field's value and keep the duplicate silently |
| `headers.encoded_word_invalid` | `encoded_word_invalid` | decode the malformed encoded word as if well formed |
| `headers.invalid_date` | `date_invalid` | take a `Date` the parser cannot read as if it parsed |
| `headers.leading_bom` | `leading_utf8_bom` | strip the leading U+FEFF into the first field's name |
| `headers.mbox_from_line` | `mbox_from_line_at_zero` | read the mbox `From ` line as an ordinary field |
| `headers.no_date` | `date_absent` | invent a `Date` value for a message with no `Date` field |
| `security.macro_present` | `attach_macro_docm` | record a macro-enabled document without a `security.macro_present` row |
| `security.remote_content_present` | `attach_remote_image_only` | record a remote reference as fetched content |

The five **named** ids no sidecar labels at a live phase-1 row are `headers.date_no_zone`,
`body.html_quote_rule_gap`, `body.inline_reply_interleaved`, `body.no_boundary_found` and
`view.quote_level_disagreement`; `tests/test_phase1_gap_gate.py::
test_the_ids_no_fixture_exercises_are_named` re-derives the list from the corpus, so a fixture that
starts or stops labelling one of them moves it rather than being tolerated. One live emission is
unlabelled -- `body.html_quote_rule_gap` (an unclosed HTML quote container, decision 1's named
not-v1 shape) -- and the gate **reports** it instead of counting it as agreed
(`tests/test_phase1_gap_gate.py::test_the_unlabelled_emissions_are_reported`). Two further gaps no
fixture exercises at all are reported by the metrics table: `body.headers_only` and
`body.no_boundary_found`.

## Label-versus-parser findings

A disagreement between a typed label and the parser is a **finding**: it is reported with its bytes
and the failing test id, and it is never resolved by editing the label (decision 12). Every one
Phase 1 found:

* **Turn 0.4: seven label/walker disagreements over four fixtures, from two root causes, both
  resolved in review.** The `alternative_text_html` sidecar typed its first delimiter 21 bytes long
  and part `1.1` two bytes late (the delimiter line plus its CRLF is 19 bytes) -- a hand-typing
  error, corrected in the label from the bytes; and the walker ran the TEXT charset ladder over
  binary parts (a PDF, a PNG, an office zip), reporting a charset, a fallback and a false
  `body.decode_destroyed_bytes` -- a walker defect, fixed (`DECODE_CHAIN_VERSION` 2). The corpus is
  now green. Bytes and the full diagnosis: `tests/test_l1_gate.py` module docstring;
  `tests/test_l1_gate.py::test_the_committed_corpus_is_green_with_the_quote_facts_live`.
* **Turn 1.5: five frozen `body.html_spans` rows typed the wrong span, over two fixtures, corrected
  in the labels (owner-approved, sidecars annotated `html_spans_correction`, ledger hashes updated in
  the same commit).** `html_style_and_script` rows 0 (`html`) and 4 (`body`) typed length 12 where
  the tree gives 10 -- they counted the trailing `\r\n`, a text node after `</html>`, as inside the
  element. `html_href_img_remote_and_cid` row 1 (`a`) typed length 6 where the bytes give 3
  (`"Ben"`), and rows 2/3 (`img`) typed offsets 6/8 where the bytes give 8/10 -- the `\r\n` between
  `</p>` and the first `<img>` was not counted. Both the original and the corrected values are
  pinned in `tests/test_htmltext.py::FINDING_ROWS`, and
  `::test_the_committed_html_spans_labels_agree_with_the_bytes_row_for_row` asserts agreement.
* **Turn 1.6: the first (label-blind) run of the TEXT quote rules disagreed with the catalogue.**
  The rules were written without the labels; the mismatch set is kept as
  `tests/test_l1_gate.py::QUOTE_MISMATCH_STEMS`, emptied rather than deleted, because the owner
  adjudicated the conventions from the bytes (decisions 33-39) and `QUOTE_RULES_VERSION` moved to
  `2`. Bytes: `tests/test_quote_text.py`; the catalogue review: `docs/design/quote-catalogue-review.md`.
* **Turn 1.7: eight html `body.quote_boundaries` rows disagreed -- six `span_length` (the DOM span
  carried the projection's final line terminator) and two `prefix_depth` (the Outlook marker's own
  line; the bare `blockquote` sibling of a `moz-cite-prefix`).** Kept as
  `tests/test_l1_gate.py::QUOTE_HTML_MISMATCH_STEMS`, emptied after the adjudication (decisions
  40-42, `QUOTE_RULES_VERSION` `4`). Bytes: `tests/test_quote_dom.py`.
* **`attach.cid_dangling` is still a finding, and it is why that gap id is deferred.** The two
  sidecars that carry the case disagree about whether the row is typed at all, so no live emission
  satisfies both and the label cannot be edited; the reference is recorded and no part is invented
  (D4). Reason and bytes: `tests/ledger/phase1_exit.json`; the stage's own note:
  `tests/test_attach.py` (the `GAP_ATTACH_CID_DANGLING` case).
* **Six further rows are *named waits*, not comparisons** (`tests/ledger/phase1_exit.json`, rewritten
  from the live corpus and compared both ways by `tests/test_phase1_exit_gate.py::
  test_the_named_wait_set_matches_the_observed_rows`): the frozen labels assert a `gaps.later` row
  that the package either does not emit at all (**no-emission**: `attach.cid_dangling` at
  `attach_cid_dangling:1`; `body.mixed_origin_quoting` at `gmail_reply_quoting_outlook_authored:1.2`
  and `mixed_origin_quote:1.2`) or emits on a superset of the sidecars that label it
  (**over-emission**: `view.quote_level_disagreement` at `gmail_short_reply_gt_and_on_wrote:1.1`
  -- 6 emissions over the corpus against 1 labelled row; `body.inline_reply_interleaved` at
  `inline_reply_interleaved:1` -- 3 against 1; `body.no_boundary_found` at `no_boundary_found:1` --
  102 against 1, the decision-3 trigger amendment). Each row carries its reason and its bytes:
  fixture sha256, the labelled rows, the stage's emissions. The gate fails on an unnamed or a
  dropped row (`::test_a_dropped_named_row_fails_the_gate`, `::test_an_unnamed_phase1_wait_fails_the_gate`).
* **Three time-evidence conflicts stay unresolved by design** (label-versus-parser over the `Date`
  chain: `date_vs_mtime`, `future_date_in_text`, `received_clock_skew`). They are asserted as exact,
  named, non-empty sets rather than reconciled:
  `tests/test_time_conflicts.py::test_the_unresolved_pairs_reproduce_and_are_non_empty_where_the_evidence_conflicts`.
* **`headers.addresses` is compared by the sparse-row rule, and that is a finding.** Six sidecars
  label the fact sparsely (only the rows they state), so the comparison is over the labelled rows;
  the reading is recorded, not treated as agreement: `docs/design/phase1-empirical.md`
  (Turn 1.2, "the sparse-row rule ... is a FINDING"); `tests/test_addresses.py`.
* **The walker recursed, against the exit criteria; Turn 1.11 closed it.** At Turn 1.10a
  `emailextract/walk.py::_walk_part` called itself to descend into a nested multipart child, so "the
  walkers are iterative" did not hold, and the scan named it with its reason
  (`tests/test_phase1_scope.py::KNOWN_SELF_RECURSION`). Turn 1.11 rewrote `_walk_part` as an
  explicit-stack loop -- byte-for-byte identical output, proven against the frozen recursive
  reference `tests/support/legacy_walk.py` by
  `tests/test_walk_iterative.py::test_the_iterative_walker_matches_the_recursive_reference_over_every_fixture`
  and `::test_the_iterative_walker_matches_the_recursive_reference_over_seeded_trees` -- so the
  allow-list is empty and `::test_no_msg_cfb_routing_recursion_or_threading_exists` now finds no
  self-recursive function in the package. A raised `max_depth` no longer blows the interpreter stack:
  `::test_a_raised_depth_cap_walks_deep_multipart_without_recursing` (the frozen recursive walker
  raises `RecursionError` on the same input; the iterative one assembles a `parsed` document).
* **`labels.undetermined=20`: twenty rows, over eighteen sidecars, that the labels leave open** --
  12 distinct fact or gap ids (`decode.chain` 5, `document.axes` 3, `headers.addresses` 2,
  `headers.date` 2, and one each of `attach.decorative`, `attach.types`, `body.boundary_disagreement`,
  `body.decode_destroyed_bytes`, `body.quote_boundaries`, `body.view_levels`, `gaps.later`,
  `headers.parameters`). They are the design's own unknowns, typed into sidecars rather than guessed.
  `docs/design/label-questions.md` types the four distinct questions of the Turn 0.3 family (Q1-Q4);
  three are settled by revision 3 (see **Named resolutions**) and the fourth, Q2 (the RFC 822
  ladder's rungs, in order), is **not**, because it needs a design edit naming the rungs. The count
  is pinned by `tests/test_metrics_cli.py::test_the_undetermined_count_is_read_from_the_labels` and
  the shape of each entry by
  `tests/test_label_structure.py::test_every_undetermined_entry_names_a_fact_or_gap_a_locator_and_a_reason`.

## Licences

`email-extract` is **Apache-2.0** (`LICENSE`, and `pyproject.toml`'s `license = "Apache-2.0"` with
`license-files = ["LICENSE", "NOTICE"]`). Apache-2.0 is notice-based, so `NOTICE` carries every
distribution's licence id and is cross-checked against what `pyproject.toml` actually declares --
in both directions, so an unattributed new dependency and a stale entry both fail. **No GPL, LGPL or
AGPL dependency or licence claim exists anywhere in the tree** (operating rule and exit criterion).

| distribution | how it is reached | licence |
|---|---|---|
| `docextract-core` | the **only** runtime dependency | Apache-2.0 |
| `word-extract` | the `[word]` extra (DOCX routing) | Apache-2.0 |
| `form-extract` | the `[form]` extra (PDF/XLSX routing) | Apache-2.0 |
| `olefile` | **not** a dependency of this release: named for the future `.msg` reader (Phase 1b) | BSD-3-Clause |
| `pytest` | the `[dev]` extra | MIT |

Two findings are recorded with the audit rather than fixed:

* **the AGPL is reachable through `form-extract`'s own `pdf` extra** (PyMuPDF is AGPL-3.0), so this
  package must request `form-extract` **plain**. It does, and
  `tests/test_licence_audit.py::test_the_form_extra_does_not_request_the_agpl_pdf_extra` pins it;
* **`olefile` is named in `NOTICE` and is not declared**, which is the honest way to say "planned,
  not shipped": `::test_olefile_is_not_a_declared_dependency`.

The audit is a test, not a reading: `tests/test_licence_audit.py` (10 tests) checks the licence text
and holder, the declared licence files, that the runtime dependency set is exactly
`{docextract-core}`, the two-way `NOTICE`/`pyproject` agreement, that the hand-typed
`AUDITED_LICENCES` table equals `NOTICE`, that the audit can fail in all three directions
(unattributed dependency, wrong id, stale entry), and that no GPL/LGPL/AGPL licence text or GPL
distribution appears in the audited files.

## Not done

What Phase 1 deliberately left to a later phase, and what it found but did not fix.

* **Deep nesting is quadratic in wall time at raised caps (found while validating Turn 1.11).** The walker
  is now iterative and its step counter is linear, but each nesting level scans its own body for its
  boundary, so the bytes scanned grow with the square of the depth: measured by the reviewer on one
  machine, a nested `multipart/mixed` took 1.9 s at 1,000 levels, 8.3 s at 2,000 and 33 s at 4,000. The
  default `Limits.untrusted()` caps depth at 16, so the default path is bounded; a caller who raises
  `max_depth` owns the cost. The step counter does not see per-level byte scanning, so the
  "work-per-input-byte" claim is a claim about steps. A single-pass nested-boundary scan is later work.
* **Phase 1b: the `.msg`/CFB reader.** `parse` returns `cfb_msg_unsupported` for the CFB magic;
  `olefile` is named in `NOTICE` and is not installed. The walker's `cfb_msg` route is exercised only
  through the in-memory `FakeContainer` (D13).
* **Threading and the time/thread phase.** No thread builder exists (no `build_thread`, no routing,
  no `ThreadEdge` producer); the oracle still waits on **26** phase-3 facts. `TimeEvent` is a frozen
  contract with no emitter (`TIMEEVENT_VERSION` 1).
* **The sibling routing is a seam, not a build.** `siblings.py` holds the citation shapes and the
  import test; the package must import with neither `word-extract` nor `form-extract` installed
  (`tests/test_phase1_scope.py::test_the_package_imports_with_no_sibling_and_no_chardet`).
* **The matcher and the query layer.** `seam.py` is the stub (`MATCHER_VERSION` 1, the real matcher
  is a separate track); the query layer and any LLM-facing output are out of Phase 1's scope by the
  design. `FlagSection` stays present-but-empty (Phase 4/5).
* **The QP and base64 within-part offset maps are deferred to Phase 4** (decision 18): only
  identity-CTE strict stateless decodes produce `exact` spans today, and every other case is
  `part_level` with `cte_not_identity | multibyte_without_offset_map | decode_fallback` and **no**
  within-part byte span.
* **Turn 1.4b (flowed reflow) is not built.** Quote detection needs only per-physical-line depth, and
  joining would edit a frozen sidecar and still give no byte span, so `format=flowed` soft breaks are
  recorded as `body.flowed_reflow_unresolved` instead (the debate's item 4).
* **`body.html_quote_rule_gap` has no label.** An unclosed HTML quote container is decision 1's named
  not-v1 shape; the gate reports the emission as unlabelled rather than counting it as agreed. Two
  gap ids no fixture exercises at all are reported by the metrics table: `body.headers_only`,
  `body.no_boundary_found`. Five further emittable ids have no live labelled row and are named in
  `UNEXERCISED_GAP_IDS` (see **Gap gate**).
* **The nine-row wait set is still a wait.** The six rows named in
  `tests/ledger/phase1_exit.json` -- three **no-emission** (`attach.cid_dangling`,
  `body.mixed_origin_quoting` twice) and three **over-emission** (`view.quote_level_disagreement`,
  `body.inline_reply_interleaved`, `body.no_boundary_found`) -- cannot be compared without editing a
  frozen label, and neither can the three rows whose own phase column is 3. Nothing is tuned to
  satisfy a label another frozen label contradicts.
* **The `.msg`-shaped absences in the model are unfilled**: the not-built axis fields
  (`AttachmentOccurrence`'s `.msg` fields, `ContainerFacts`) ship declared and empty, and the
  walker's `UNBUILT_SECTIONS` still records `unknown("not_built_in_phase0")` for them.
* **The walker recursed -- closed by Turn 1.11, no longer an open item.** The Turn 1.10a finding that
  `walk.py::_walk_part` called itself (`KNOWN_SELF_RECURSION`) is fixed: `_walk_part` is an
  explicit-stack loop, the scope scan's allow-list is empty, and a raised `max_depth` no longer
  produces a `RecursionError` or a `failed(extractor_error)` document. See **Label-versus-parser
  findings**; tests `tests/test_walk_iterative.py` (the fixture, seeded-tree, mutation and
  deep-nesting cases).
* **The metrics table's headline still says "at phase 0"** (`emailextract/evals/metrics.py:92`). It
  is a recorded oracle file, and the label ledger is additions-only, so the wording is recorded here
  rather than edited; the tables it prints are the phase-1 ones.
* **`fixtures/real/` is empty by design and stays git-ignored.** No real or employer mail enters the
  repository, so the corpus's one honest gap -- there is no producer-generated, real-world fixture
  set yet -- remains: the strongest available common-mode breaker for the quote rules is the owner's
  structure-only probe, and the independent splitter's independence is **code lineage, not a
  different author**.

## Exit criteria

The build spec's "Exit criteria for Phase 1" (`docs/design/phase1-build-spec.md`) is the phase's
contract. This section walks it **bullet by bullet**, saying whether each is CLOSED or OPEN and
naming the test or gate line that fails the moment the claim stops being true. Every status and every
number below was **recomputed this turn** (Turn 1.11); nothing is copied from an earlier draft of the
report.

### The re-run this turn

`python -m emailextract.evals` (CPython 3.14.3; the counts are identical on CPython 3.11.15):

```
email-extract: L1 gate metrics at phase 0 (corpus: <repo>/fixtures)
  L1              matched=1330 mismatched=0 unmeasurable=0 unmodelled=0
                 not_yet: phase 1=9, phase 3=26
  labels.undetermined=20 question(s) the labels leave open
  gates:
    L1             pass matched=1330 mismatched=0 unmeasurable=0 unmodelled=0 not_yet=35
    no-silent-drop pass fixtures=119 bytes=79328 mutation-checks=pass
    phase-1 gaps   pass checked 30 live phase-1 gap label(s); 0 not recorded; 1 unlabelled emission(s); skipped 0
    phase1 exit    pass wait=6 (named=6), compared=1330; extra=0 missing=0
  corpus: 119 fixture(s), 119 sidecar(s)
    generated      81 fixture(s), 81 sidecar(s)
    raw            33 fixture(s), 33 sidecar(s)
    time            5 fixture(s), 5 sidecar(s)
  falsifiability: 8 gap(s) covered by cases, 6 recorded by sidecars
  not exercised by any fixture: body.headers_only, body.no_boundary_found
```

The three ledgers, run `--check` on **both** interpreters (`<repo>` is the corpus path on the
machine that ran them; the exit codes are the portable part):

```
tools/update_behavior_ledger.py --check   exit 0   (behaviour fingerprints unmoved)
tools/update_label_ledger.py --check      exit 0   (additions-only: sidecars + tests/support/** + evals/**)
tools/make_fixtures.py --check            exit 0   (the generated corpus reproduces byte for byte)
```

The full suite, `python -m pytest -q`, run sequentially on both pinned interpreters:

```
CPython 3.14.3:  1920 passed, 2 skipped
CPython 3.11.15: 1920 passed, 2 skipped
```

### The bullets

| # | the spec's claim (quoted, abridged) | status | the test or gate line that fails without it |
|---|---|---|---|
| 1 | "the declared phase-1 fact-id list is pinned in the ledger ... a closed list in the ledger, empty by default; L1 is 100% over every phase-1 fact with a per-(fact x phase) coverage floor ... the phase-1 gap gate passes and fails when a phase-1 gap is dropped" | **CLOSED** for the pin, the 100%, the ratchet and the gates; **OPEN** for the literal declared floors | `tests/test_facts_ledger.py` (the pin), `tests/test_facts_coverage.py` (the ratchet), `tests/test_phase1_gap_gate.py`, `tests/test_l1_gate.py`; the evals lines `L1 pass matched=1330 mismatched=0` and `phase-1 gaps pass ...`. **Open:** 11 of the 20 declared floors are unmet by the committed corpus (`tests/ledger/facts_ledger.json` `declared_unmet`), recorded as a FINDING and re-based rather than lowered -- see **Open and partly-open items**. |
| 2 | "`benign` is an additions-only sidecar flag with closed reason ids ... on every benign fixture the stdlib scanner's three comparisons agree and a planted defect makes each fail; stdlib version differences are recorded" | **CLOSED** | `tests/test_benign_flag.py`; `tests/support/stdlib_scanner.py`; `tests/test_stdlib_header_scanner.py`. |
| 3 | "every Phase 1 gap id has a mutation case (the tightened triple) that fails the gate naming the fixture, the fact and the bytes, and a catalogue test fails on an uncovered id" | **CLOSED** | `tests/test_gap_falsifiability.py`; `tests/test_quote_catalogue.py`; the tightened triple in `emailextract/evals/falsify.py`. |
| 4 | "no-silent-drop passes on every fixture and mutation; boundary ordinal, prefix depth, rule id and kind are stored per boundary per view; every `exact` span passes the five-part property" | **CLOSED** | `tests/test_no_silent_drop.py`; the five-part property in `tests/test_text.py`; the boundary fields in `tests/test_quote_text.py` / `tests/test_quote_dom.py`; the evals line `no-silent-drop pass fixtures=119 bytes=79328 mutation-checks=pass`. |
| 5 | "the identity projection is named and documents are byte-identical ... across two runs, hash seeds, locales, time zones and both interpreters ... re-ingest is a no-op; ledger fingerprints are identical on both interpreters; a behaviour change without a bump makes `--check` exit 1 and names the constant" | **CLOSED** | `tests/test_assemble.py::test_the_identity_projection_drops_the_recorded_only_inputs`; `tests/test_store.py::test_re_ingest_is_a_no_op_over_a_throwaway_store`; `tests/test_behavior_ledger.py::test_the_cli_check_exits_zero_on_unmodified_code` and its refusal cases; this turn's identical fingerprints and identical evals output on both interpreters. |
| 6 | "the additions-only ledger passes over sidecars, `tests/support/**` and `emailextract/evals/**`; no existing sidecar is modified across the phase; the label-leak test passes; the fixture set is a superset of the design's Phase 1 list (a census test)" | **CLOSED** | `tests/test_label_ledger.py`; `tests/test_label_leak.py`; `tests/test_fixture_census.py`; `tools/update_label_ledger.py --check` exit 0. |
| 7 | "the seeded fuzz and the independent splitter fuzz pass ... any other `Exception` (and `MemoryError` or `RecursionError` specifically) fails with the seed. The hostile set ... is recorded at the caps with a work-per-input-byte budget asserted non-superlinear ... nothing is fetched ... no attachment is written under its raw filename" | **CLOSED** | `tests/test_seeded_splitter_fuzz.py`; `tests/test_hostile_set.py` (the caps, the socket guard and the raw-filename rule); `tests/test_hostile_set.py::test_work_per_input_byte_is_not_superlinear`; `tests/test_walk_iterative.py` (a raised `max_depth` no longer raises `RecursionError`). |
| 8 | "the package imports with no sibling, no `olefile`, no `chardet` (a fresh subprocess after a full ingest); no `.msg`, CFB, routing, recursion, matching, threading or `TimeEvent` emission exists; no GPL anywhere" | **CLOSED** | `tests/test_phase1_scope.py` (the import probe and the self-recursion scan, whose allow-list Turn 1.11 emptied); `tests/test_licence_audit.py`. Turn 1.11 closed the one exception -- the walker's recursion. |
| 9 | "final report: a committed file with required sections (a test checks it non-empty), a list of named resolutions each with a test id, every version bump and why, the licences, and every label-versus-parser disagreement citing the failing test" | **CLOSED** | `tests/test_phase1_scope.py::test_the_phase1_report_sections_are_present_and_non_empty` (the eight required sections, each present, non-empty and unique, and every `tests/...::name` citation resolvable). |

### Open and partly-open items

Stated plainly, so a reader does not have to infer them:

* **The 11 declared coverage floors (bullet 1).** `tests/ledger/facts_ledger.json`'s `declared_unmet`
  lists eleven phase-1 facts whose floor in `docs/design/phase1-facts.md` the committed corpus does
  not meet (`attach.cid_use`, `attach.decorative`, `attach.filename`, `attach.manifest`,
  `attach.types`, `body.cid_refs`, `body.text`, `headers.addresses`, `headers.date`,
  `headers.decoded`, `headers.projection`). They are recorded, never lowered silently; the re-base to
  the achieved counts is **owner-signed** (`rebase.status = "signed"`), so the effective floor is the
  achieved count and is pinned by `tests/test_facts_coverage.py`.
* **The 6 named `phase1_exit` waits and the 3 rows filed under a later phase.** The evals line
  `phase1 exit pass wait=6 (named=6), compared=1330; extra=0 missing=0` is a **wait set**, not a
  comparison: three no-emission rows (`attach.cid_dangling`, `body.mixed_origin_quoting` twice) and
  three over-emission rows (`view.quote_level_disagreement`, `body.inline_reply_interleaved`,
  `body.no_boundary_found`) cannot be compared without editing a frozen label another frozen label
  contradicts, and three further rows carry phase 3. See **Label-versus-parser findings** and
  `tests/test_phase1_exit_gate.py`.
* **No real mail was probed.** The owner's decision: `fixtures/real/` stays empty and git-ignored, and
  user feedback will cover it. The corpus's real-world common-mode breaker is therefore missing (see
  **Not done**).
* **The walker recursion (bullet 8) is CLOSED by Turn 1.11.** It was the one exit criterion that did
  not hold at Turn 1.10b; `_walk_part` is now iterative and the scope scan's allow-list is empty
  (`tests/test_walk_iterative.py`).
* **The symlink test skips on Windows.** `tests/test_ingest.py::test_a_symlinked_directory_is_skipped_and_a_symlinked_file_is_read`
  skips when the OS refuses to create a symlink (the default on a non-elevated Windows box); it runs
  on Linux, which is where CI proves it.
* **`.msg`/CFB is unsupported by design.** `parse` returns the named error `cfb_msg_unsupported` for
  the CFB magic; the `.msg` reader is Phase 1b (`emailextract/parse.py`).
