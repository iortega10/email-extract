# Phase 1b report

The close of `email-extract` **Phase 1b**: the deterministic Outlook `.msg` reader -- the CFB
primitives, the MAPI layer, the projection into the one virtual RFC 822 message the same walker
reads, the RTF minimum and the attachment/embedded-message facts -- and the gates that measure it.
This file is committed as the **last** artifact of Phase 1b.

It is a report, not a gate: `tests/test_phase1b_report.py` checks that the eight sections below are
present exactly once and non-empty, that the version bumps and the licence rows are named, and that
the `max_input_bytes` asymmetry is recorded; the content is the owner's review.

Inputs the sections cite, so a reader can re-run rather than trust:

* the committed corpus: **126** `.eml` fixtures (88 `generated`, 33 `raw`, 5 `time`) and **52**
  `.msg` fixtures with **51** `msg/*.expected.json` sidecars (`msg_directory_loop` deliberately has
  none -- it refuses); `fixtures/real/` is git-ignored and never read;
* the two pinned interpreters: CPython **3.14.3** (`python`) and CPython **3.11.15**
  (`%LOCALAPPDATA%/Temp/wbv311b`);
* the ledgers: `tests/ledger/{facts_ledger,phase1_exit,behavior_ledger,corpus,label_ledger}.json`
  and the `.eml` golden `tests/golden/eml_golden.json`;
* the tests named in each section.

**The final walls (measured at this turn's boundary, Turn 1b.10b).** `python -m pytest` is
**2609 passed, 2 skipped** on CPython **3.14.3** (`python`, 3m56s) and on CPython **3.11.15**
(5m47s); all five `--check` tools (`make_msg_fixtures`, `make_fixtures`, `update_eml_golden`,
`update_behavior_ledger`, `update_label_ledger`) and `python -m emailextract.evals` exit 0 on both
interpreters; and the three message components' behavior fingerprints are byte-identical across the
two (`tools/update_behavior_ledger.py --check` recomputes them on each).

**Honesty rules this report keeps.** The corpus is **synthetic** (hand-typed byte strings, no real
message content); **no real `.msg` was ever read** by the package -- real mail stays outside the
repository and the six probes P1-P6 are the owner's to run. Every MAPI tag, every CFB field and
every layout claim outside the first **eleven spike files** (`S01-S11`,
`docs/design/email-spike.md` section B) is **public-spec only** until the owner runs those probes.
And **Phase 1b changes no `.eml` behaviour**: `EMAIL_PARSER_VERSION` is unmoved (`"2"`), the `.eml`
golden is byte-identical, and the new version constants enter no `RunRecord`, no
`limits_fingerprint` and no document key.

## What was built

### The turns

Each turn's declaration block (`docs/design/phase1b-ledgers.md` section (f)) is the binding record
of its `module:` and `test:` lines; `tests/test_turn_declarations.py` enforces both directions.

| turn | what it built | what it decided |
|---|---|---|
| 1b.0a | documents only | the design revision 4: D1/D13 reconciliation, `container_facts` names, the fixture catalogue, the 11 fact ids, the ledger additions, the P1-P6 probe spec |
| 1b.0b | `docs/design/msg-architecture.md`, `tools/msg_probe.py` | the architecture and the probe script (spike, no package code) |
| 1b.0c | `tests/golden/eml_golden.json` | the `.eml` golden, captured before the first frozen-module edit |
| 1b.1 | `versions.py`, `model.py`, `walk.py`, `container.py`, `assemble.py` | `OUTPUT_SCHEMA_VERSION` `"5"` -> `"6"`, the eight provenance points, the `value_codec` seam, the span table |
| 1b.2 | `tools/cfb_writer.py`, the first `fixtures/msg/*.msg` | the deterministic minimal CFB writer, the `olefile` oracle |
| 1b.3 | `emailextract/cfb.py`, `tools/make_msg_fixtures.py` | the CFB primitives, the caps, the eight-class sector accounting, the hostile set and the seeded fuzz |
| 1b.4 | `emailextract/mapi.py` | the property tables, `001E`/`001F`/multi-valued, the string ladder, the class gate, recipients |
| 1b.5 | `emailextract/msgcontainer.py` | the virtual RFC 822 projection, `0x007D` headers, one HTML body end to end |
| 1b.6 | `msgcontainer.py`, `mapi.py` | the five message-level facts (subject/sender/recipients/time) and the four mapped observations |
| 1b.7 | `mapi.py`, `msgcontainer.py`, `assemble.py` | attachments: the MIME projection, the attachment rows, the depth-1 embedded message, the depth cap |
| 1b.8 | `emailextract/rtf.py` | the RTF minimum: LZFu/`MELA` decompress, header/CRC check, record -- no body view |
| 1b.9 | `rtf.py`, `msgcontainer.py`, fixtures | the cross-container pair, the Outlook-layout proof, the encodings |
| 1b.10a | `emailextract/evals/{l1,labels}.py`, `msgcontainer.py` | the 11 `msg.*` measurers, the `.msg` sidecars and the coverage floors |
| 1b.10b | `tests/test_phase1b_*.py`, `tools/behavior_ledger.py`, this report | the Phase 1b gap gate, the hostile run, the scope test, the three behavior-ledger components, `0.2.0` |

### The reader

`cfb.py` is the package's own [MS-CFB] reader (never `olefile`: that is the tests-and-tools
comparator, pinned by `tests/test_phase1b_scope.py::test_the_library_imports_with_no_olefile_and_no_gpl`).
`mapi.py` reads the property tables, the code-page ladder, the class and the recipient/attachment
rows. `msgcontainer.py` projects the MAPI record into **one virtual RFC 822 message** with a span
table back to the CFB streams, and the one walker (`walk.py`) reads that projection -- there is
deliberately **no** second walker. `rtf.py` decompresses `0x1009` and records it without producing a
body view. `assemble.py` fills attachment occurrences through the same span table it uses for
`.eml`.

### The three behavior-ledger components

`tools/behavior_ledger.py` gains `cfb`, `msg_reader` and `msg_projection`, keyed
`"<version>|corpus:<N>"` over a **second corpus list** (the committed `.msg` fixtures) so that the
walker's `walk`/`decode_chain`/`contracts` lines and the `.eml` golden cannot move when a `.msg`
fixture lands. `cfb` fingerprints the CFB primitives over the **well-formed** fixtures only (the
three hostile mutants are the fuzz's), `msg_reader` the whole MAPI record, `msg_projection` the
virtual bytes, span table, headers and `part_id`s. `tests/test_behavior_ledger.py` pins the
fingerprints, the keys and the cross-interpreter identity.

### The gates and the guards

`tests/test_phase1b_gap_gate.py` proves every reader gap id has a working mutation case;
`tests/test_phase1b_hostile_run.py` drives one inventory of hostile inputs through the pipeline;
`tests/test_phase1b_scope.py` proves the package never imports `olefile` and that no real `.msg` is
anywhere in the tree.

## Named resolutions

Each row is a question the Phase 1b turns had to settle, and the test (or ledger line) that pins
the answer.

| resolution | pinned by |
|---|---|
| `OUTPUT_SCHEMA_VERSION` `"5"` -> `"6"` (the `stream_ref`/`embedded` null keys) | `tests/test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys` |
| `CFB_VERSION`, `MSG_READER_VERSION`, `MSG_PROJECTION_VERSION` = `"1"` | `tests/test_behavior_ledger.py::test_the_version_strings_point_at_the_names_to_bump` |
| the reader is the package's own `cfb.py`; `olefile` is a dev-only comparator | `tests/test_phase1b_scope.py::test_the_library_imports_with_no_olefile_and_no_gpl` |
| no real `.msg` is in the repository; every `.msg` is generated, checksummed and spec-labelled | `tests/test_phase1b_scope.py::test_no_real_msg_is_in_the_repository` |
| every reader gap id has a working mutation case (including the registry's seed for the last) | `tests/test_phase1b_gap_gate.py::test_every_msg_gap_id_has_a_mutation_case` |
| the reader's ids are read off the registry and `LIVE_GAP_IDS`, never hand-listed | `tests/test_phase1b_gap_gate.py::test_the_msg_ids_are_read_off_live_gap_ids` |
| dropping one emission fails the phase-1 gap gate, naming the id and the fixture | `tests/test_phase1b_gap_gate.py::test_the_phase1b_gap_gate_fails_when_a_gap_is_dropped` |
| every hostile `.msg` input yields a document or a named refusal | `tests/test_phase1b_hostile_run.py::test_every_hostile_msg_input_yields_a_document_or_a_named_refusal` |
| the hostile inventory is identical under two `PYTHONHASHSEED`s | `tests/test_phase1b_hostile_run.py::test_the_hostile_inventory_is_stable_across_hash_seeds` |
| `msg.recipient_table_unreadable` is closed with the 1b.4 recipient-count-mismatch seed, not a new committed fixture | `tests/test_phase1b_gap_gate.py::test_every_msg_gap_id_has_a_mutation_case` (the seed branch) |
| the `.msg` corpus is a second ledger list, so no `.eml` line and no golden key moves | `tests/test_behavior_ledger.py::test_the_committed_ledger_agrees_with_the_code` |
| the runtime dependency is exactly `docextract-core`; `olefile` is a `[dev]` extra | `tests/test_phase1_scope.py::test_no_runtime_dependency_beyond_docextract_core` |
| no GPL/AGPL/LGPL is reachable through this tree's declared dependencies | `tests/test_licence_audit.py::test_the_form_extra_does_not_request_the_agpl_pdf_extra` |
| `ingest_path` ingests every committed `.msg` (fixed in Turn 1b.10c; see the hostile run) | `tests/test_ingest_msg.py::test_ingest_path_ingests_every_committed_msg` |

## Coverage

Per-fact declared floor, effective floor and observed count. The effective floor is the ratchet
value recorded in `tests/ledger/facts_ledger.json` (`floors`); the observed count is what the
committed corpus exercises (`docs/design/phase1b-facts.md`, Turn 1b.10a).

| fact id | declared floor | effective floor | observed | verdict |
|---|---|---|---|---|
| `msg.container_layout` | 45 | 51 | 51 | met |
| `msg.sector_accounting` | 45 | 50 | 50 | met |
| `msg.message_class` | 40 | 44 | 44 | met |
| `msg.body_streams` | 20 | 33 | 33 | met |
| `msg.codepage_ladder` | 8 | 8 | 8 | met (exactly) |
| `msg.stream_faults` | 2 | 2 | 2 | met |
| `msg.attachments` | 8 | 11 | 11 | met |
| `msg.embedded_summary` | 2 | 2 | 2 | met |
| `msg.storage_tree_sha256` | 2 | 2 | 2 | met |
| **`msg.recipients`** | **10** | **4** | **4** | **UNMET (shortfall 6) -- finding** |
| **`msg.time_facts`** | **4** | **1** | **1** | **UNMET (shortfall 3) -- finding** |
| `gaps.later` (existing) | 5 | 63 | 63 | met |

The two unmet floors are recorded in `facts_ledger.json`'s `declared_unmet` as
`{"fact": "msg.recipients", "declared": 10, "achieved": 4}` and
`{"fact": "msg.time_facts", "declared": 4, "achieved": 1}`. Only four committed fixtures carry a
recipient table (`msg_recipients_display_only`, `msg_recipients_ex_no_smtp`,
`msg_recipients_bcc_duplicates`, `msg_outlook_layout_handbuilt`) and only one carries time
properties (`msg_time_property_vs_date_header`): closing them needs **six more recipient-carrying
fixtures and three more time-carrying fixtures**, which is a fixture turn the owner must decide to
spend (see **Not done**).

## Gap gate

The reader owns **eleven `msg.*` ids plus `headers.mapi_header_property_disagree`**. The set is
read off `docs/design/phase0-gaps.md` and `l1.LIVE_GAP_IDS`
(`tests/test_phase1b_gap_gate.py::test_the_msg_ids_are_read_off_live_gap_ids`); eleven of the twelve
have a committed fixture and a mutation case in the phase-1 catalogue, and the twelfth is closed
with the registry's own seed.

| gap id | mutation case | fires on |
|---|---|---|
| `msg.transport_headers_absent` | `drop_everywhere` | `msg_no_transport_headers` |
| `headers.mapi_header_property_disagree` | `drop_everywhere` | `msg_property_vs_header_conflict` |
| `msg.stream_truncated` | `drop_everywhere` | `msg_fat_cycle` |
| `msg.attachment_method_unsupported` | `drop_everywhere` | `msg_attachment_by_reference` |
| `msg.embedded_depth_cap` | `drop_everywhere` | `msg_embedded_depth_two` |
| `msg.rtf_to_text_unsupported` | `drop_everywhere` | `msg_rtf_only` |
| `msg.class_not_ipm_note` | `drop_everywhere` | `msg_non_ipm_note` |
| `msg.property_tag_unknown` | `drop_everywhere` | `msg_unknown_tags` |
| `msg.named_property_unresolved` | `drop_everywhere` | `msg_named_properties` |
| `msg.codepage_unresolved_ladder_used` | `drop_everywhere` | `msg_string8_ascii_no_cp` |
| `msg.cfb_difat_extended` | `drop_everywhere` | `msg_difat_extended` |
| `msg.recipient_table_unreadable` | `drop_everywhere` | **built seed** `seed_recipient_count_mismatch` (the registry's fixture is `msg_recipients_display_only`) |

`msg.recipient_table_unreadable` stays the one `msg.*` id in
`falsify.UNEXERCISED_GAP_IDS` -- no committed sidecar labels it at a live phase-1 row -- and the
report repeats that reason: its only trigger is the test-built count-disagreement seed, and giving
it a committed fixture would have widened this turn's allow-list (`fixtures/msg/`, a sidecar, the
census, `SHA256SUMS`, the label ledger). The gate closes it with a case built in the test instead
(`tests/test_phase1b_gap_gate.py::test_every_msg_gap_id_has_a_mutation_case`).

### The hostile run

One inventory, **108** hostile inputs, each driven through `ingest_path` (which runs `parse` ->
`MsgContainer` -> `assemble` -> `store_document`) under `Limits.untrusted()`; the entry point
ingested the whole inventory in one run -- **89** written, **3** hit, **16** named skips
(`tests/test_phase1b_hostile_run.py::test_every_hostile_msg_input_yields_a_document_or_a_named_refusal`):

| class | count | outcome |
|---|---|---|
| `committed` (every committed `.msg`) | 52 | mixed |
| `cfb_seed` (the 1b.3 test-only seeds) | 3 | mixed |
| `utf16` (the 1b.9 hostile UTF-16 shapes) | 2 | `cfb_msg/parsed` |
| `recipient_mismatch` (the 1b.4 count mismatch) | 1 | `cfb_msg/parsed` |
| `attachment` (the 1b.7 no-data shapes) | 2 | `cfb_msg/parsed` |
| `cfb_mutant` (one per base x operator) | 24 | mixed |
| `mapi_mutant` (one per base x operator) | 24 | mixed |

By outcome: `cfb_msg/parsed` **81**, `cfb_msg/truncated` **9**, `cfb_msg/unsupported` **2**,
`refused:not_a_message` **9**, `refused:cfb_directory_loop` **4**,
`refused:cfb_header_unsupported` **3** -- every input a document or a **named** refusal. The digest
of the outcomes is identical under `PYTHONHASHSEED=0` and `PYTHONHASHSEED=1234567`
(`tests/test_phase1b_hostile_run.py::test_the_hostile_inventory_is_stable_across_hash_seeds`).

**The one finding this run carried (resolved in Turn 1b.10c):** `ingest_path` could not ingest a
`.msg` at all. Root cause: `emailextract/ingest.py::_container_for` handed `MsgContainer` a
`MemoryMaterial`, while `MsgContainer.__init__` takes `bytes` and raises
`TypeError("msgcontainer takes bytes, got MemoryMaterial")`, so the first `cfb_msg` file aborted the
whole run. The defect landed in Turn 1b.5 and survived because no test ever ingested a `.msg`
through the entry point (`tests/test_ingest.py`'s only `.msg` case is refused by `parse` before a
container is built). The fix is one line (`MsgContainer(raw)`, leaving `EmlContainer` as it was); the
hostile run now drives `ingest_path` itself, and the new `.msg` ingest tests
(`tests/test_ingest_msg.py`, declared by Turn 1b.10c) pin the readable corpus, the re-ingest no-op,
the mixed directory, the cross-seed/interpreter digest and the over-cap skip.

## Label-versus-parser findings

Disagreements between a hand-typed label (or a catalogue claim) and what the code measured, as each
Phase 1b turn recorded them. None was bent to make a label pass.

* **1b.4** -- `msg_outlook_layout_handbuilt`'s recipient tags are typed from its own 1b.2 layout,
  not from MS-OXPROPS, so the reader records `kind=unknown`, `address_type=unknown`,
  `display_name=None`, `address=""`. The fixture is **left alone** (a finding, not a fixture edit).
  The same turn recorded `phase0-gaps.md` naming `msg_codepage_disagree` as the fixture for
  `msg.codepage_unresolved_ladder_used`, which it cannot be (its internet code page 28591 resolves
  on the first rung).
* **1b.5** -- a per-stream chain fault and a body fault both ride the same `msg.stream_truncated`
  id; container-level `msg.*` gaps are published but not yet persisted into the record.
* **1b.6** -- a **dormant** anomaly: `msgcontainer._project` can emit `ContainerGap(plain.fault)` /
  `ContainerGap(html_fault)` -- a bare fault name where a registry id belongs. No committed fixture
  has an undecodable body, so nothing reds; recorded, not fixed.
* **1b.7** -- the depth-cap detail is `2>0` (leaf-ordinal) rather than the brief's `1.2>1` example;
  the brief's "nested storage bytes never requested" is unattainable (the digest must read them);
  `declared_mime` cannot separate a defaulted from a declared MIME; `msg_outlook_layout_handbuilt`
  legitimately gains `msg.property_tag_unknown` (`370b:0003`).
* **1b.8 fix turn** -- the pre-buffer and the `MELA` CRC were both wrong; the reviewer's rule is
  that a hand-built literal now disagreeing with the code is a **finding**. The `MELA` CRC leniency
  stays an owner question.
* **1b.9** -- `msg_string8_ascii20127` and `msg_string8_utf8_65001` were labelled `(ascii)` /
  `(utf8_strict)` but a usable **internet** code page fires the `internet_cpid` rung first; the
  ladder column was corrected and three no-code-page variants were added. Also: a real code fix --
  `_transport_rows` computed a UTF-16LE line's source span as `2 * len(line)`, which shifted every
  later line for a non-BMP character; `msg_non_bmp_text` exposed it.
* **1b.10a** -- `container.size_bytes` for a `.msg` is the **virtual** message length, not the file
  length, so a `.msg` sidecar carries no `container.size_bytes`; the `msg.message_class` flat fact
  is `message_class or "absent"`, so the six class-less CFB-layout fixtures carry no class row and
  the catalogue's claim that `msg_headers_only` carries it is wrong; a bare `001E` string property
  is a ladder surface with no locator (`` prop:<tag hex> ``); `msg.storage_tree_sha256` is a digest
  and cannot be hand-typed (it was produced by an **independent** canonical-walk implementation).

## Licences

Apache-2.0 (the repository's own licence). The runtime dependency graph is exactly
`docextract-core` (Apache-2.0). `olefile` (BSD-3-Clause, https://github.com/decalage2/olefile) is
the tests-and-tools comparator for the `.msg` fixtures, declared **only** under
`[project.optional-dependencies].dev` in `pyproject.toml` and named in `NOTICE` as a development
dependency; it is never imported by the `emailextract` package
(`tests/test_phase1b_scope.py::test_the_library_imports_with_no_olefile_and_no_gpl` runs a bare
interpreter with `olefile` blocked and every module imported). The `word` and `form` extras request
the siblings plain, so the AGPL reachable through `form-extract`'s own `pdf` extra never enters this
tree (`tests/test_licence_audit.py::test_the_form_extra_does_not_request_the_agpl_pdf_extra`).
**No GPL, LGPL or AGPL dependency is declared or named anywhere in this repository**, and the
package imports with neither sibling installed.

## The max_input_bytes asymmetry

`max_decoded_*` caps are measured on **decoded** bytes, so a cap hit is consistent between `.eml`
and `.msg`. `max_input_bytes` is measured on the **file**: a roughly **50 MB `.msg`** passes the
**64 MiB** input gate, while its **~67 MB base64 `.eml` twin** -- the same message, base64-encoded
-- is refused by that gate. This is an **asymmetry, not a defect**: the `.msg` file is the whole
container, and its base64 twin is an encoding artifact of the `.eml` form. Peak memory stays
bounded by `max_input_bytes` (the E4 measurement: a 40 MiB by-value attachment costs 4.0x a
pass-through build), i.e. a ~256 MB worst-case peak at the 64 MiB cap. `tests/test_phase1b_report.py`
pins that the asymmetry is recorded here.

## Not done

What Phase 1b deliberately leaves to the owner or to a later phase:

* **The two floors' fixtures.** `msg.recipients` (4 of 10) and `msg.time_facts` (1 of 4) stay
  recorded as unmet; closing them needs six recipient-carrying and three time-carrying fixtures --
  a fixture turn, not this one.
* **`msg.rtf` is not a fact id.** RTF stays container-side (`body_streams=rtf` plus
  `msg.rtf_to_text_unsupported`): no RTF-to-text, no derived body view, and
  `msg.rtf_encapsulation_refused` was never created (O2).
* **The pair's committed `.eml`.** The cross-container pair ships as `.msg` +
  a regenerated `.eml` in memory; the `.eml` beside it is not committed.
* **Embedded-message recursion.** A depth-1 embedded message is **read and recorded**;
  `children_axis` stays not built (Phase 2).
* **`TimeEvent` / `times_axis`.** Time facts are recorded; no ordering claim and no `TimeEvent`
  emission until Phase 3.
* **The `MELA` CRC leniency and the dictionary's unwritten-byte rule** -- a reading, left as an
  owner question.
* **`CODEPAGES` width.** `msg_string8_message_cpid` uses code page 437; the message code page's
  full width is not claimed.
* **The projection's stage gaps are not persisted** into a `.msg` record: `gaps.later` carries the
  container's document-level gaps, never the virtual framing's stage gaps (contract section 8).
* **Every tag outside the first eleven spike files is public-spec only** until the owner runs the
  probes P1-P6 over real mail; **no real `.msg` has been read** by this package.
