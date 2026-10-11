# Turn 1b.0a: the `.msg` reader's documents (documents only; no code, no tests, no fixtures)

Status: brief for one build turn. Author: reviewer session, 2026-10-11. Builder: hearth. Builds on `0516834`
(release 0.1.0). **Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session, DeepSeek Pro with a
400,000-token window** (`HEARTH_MODEL=deepseek-v4-pro HEARTH_CONTEXT_WINDOW_TOKENS=400000
HEARTH_STREAM_IDLE_TIMEOUT_SECONDS=600 HEARTH_REQUEST_TIMEOUT_SECONDS=600 HEARTH_MAX_TOKENS=16384`, key from the
environment, never written). Keep tool calls small (search, then read only the lines needed; write long files in
sections). **Do not commit.**

## What this turn is

Phase 1b's contract and plan are written in `docs/design/phase1b-build-spec.md` (revision 2, owner decisions O1-O8
recorded) after a debate recorded in `docs/design/phase1b-debate.md`. This turn turns them into the **exact
documents the later turns build against**, as Turn 1.0a did for Phase 1 (read the "Turn 1.0a" row and the
"settle in 1.0a" paragraph of `phase1-build-spec.md`, `phase1-facts.md`, `phase1-fixtures.md`,
`phase1-ledgers.md` and `phase1-turn-declarations.md` first: they are the models for form and rigor). Nothing in
`emailextract/`, `tests/`, `tools/`, `fixtures/` or any sidecar is touched. The design is revised **once**, here.

Read, in this order: `phase1b-build-spec.md` (all of it), `phase1b-debate.md` (sections 0, 2, 3), then the code
the contract touches: `emailextract/model.py` (`PartRecord`, `HeaderField`, `AttachmentOccurrence`, `ContainerFacts`,
`REASON_TABLE`, `Status`, `EncodingSource`), `parse.py` (`NAMED_ERROR_REASONS`, the CFB sniff and refusals),
`text.py` (`VERBATIM_REASONS`), `ids.py` (`part_id`), `walk.py` (the `header_fields_at` decode, `_charset_ladder`),
`assemble.py`, `store.py`, `versions.py`, `tools/behavior_ledger.py`, `tools/real_probe.py`.

## Documents to write

1. **`docs/design/phase1b-contract.md`: the one schema bump, exactly.**
   - The final shape of `ContainerStreamRef` (field names, types, invariants enforced in the parent record's
     `__post_init__`, how a strict-codec round trip works for it) and **where it lives**: optional field on
     `PartRecord` and `HeaderField`, or a side table keyed by `part_id`/header ordinal. Decide, with the reason, by
     reading how `PartRecord` and `HeaderField` serialize and what the store persists.
   - The `EmbeddedSummary` record (class, subject, has_transport_headers, recipient and attachment counts) and its
     placement on `AttachmentOccurrence`, including the axis/`None` rules of Phase 1 decision 6 (no new "not built"
     idiom; `None` keeps its single meaning).
   - The `REASON_TABLE` additions (owner decision O3: new members `sector_count_cap`, `directory_entries_cap`,
     `difat_chain_length_cap`), which `Status` each pairs with, and the `Status` rules for the class gate
     (`UNSUPPORTED`, no reason), a per-stream fault (`TRUNCATED` with `stream_ended_early` or
     `declared_length_mismatch`) and a CFB cap hit. Any pairing that does not fit the existing table is reported,
     not improvised.
   - `NAMED_ERROR_REASONS` edits: add `cfb_directory_loop` and `cfb_header_unsupported`; delete
     `cfb_msg_unsupported`; CFB magic without `__properties_version1.0` maps to the existing `not_a_message`.
   - `text.VERBATIM_REASONS` gains `container_stream`.
   - The rule for `PartRecord.sha256`/`size_bytes` of a pass-through leaf versus a re-encoded leaf, and where the
     stream's own digest lives for a re-encoded leaf.
   - The `container_facts` key list for `cfb_msg` (names, value formats; the `time.<tag-hex>.filetime_hex` and
     `.utc` convention; `projection=virtual_rfc822`), as a table with the hand-checkable example for each.
   - The span table's exact row shape (it is a producer-internal structure found by
     `getattr(container, "span_provenance", None)`; document it so `FakeMsgContainer` and `MsgContainer` agree), and
     the eight provenance points of the spec with, for each, the file, the function and the **current expression
     that must remain the default branch verbatim** (copy it into the document from the code).
   - The `value_codec` seam signature for `header_fields_at` and `header_region`.
   - The **exact list of existing tests that must change**, each verified by opening the test and naming the
     assertion (the spec's list is from hearth's reading and unverified), plus any the list misses (grep for
     `cfb_msg_unsupported`, `olefile`, `REASON_TABLE`, `NAMED_ERROR_REASONS`, `OUTPUT_SCHEMA_VERSION`, the
     scope-test pins). A test not on this list that fails later is a defect, so completeness matters.
2. **`docs/design/phase1b-facts.md`: the `.msg` `FACTS`** in the form of `phase1-facts.md`: each fact id, its
   scope (message or part), the closed vocabularies, the exact value shape typed as a worked example, who measures
   it (turn), and its **coverage floor, declared here from the catalogue's fixture counts** (spec rule 6; never
   "whatever is achieved"). At minimum: container identity and layout (CFB version, sector size, mini cutoff),
   message class, code pages and the ladder's chosen source, the body streams present, recipients (rows), the
   attachment rows (method, names, mime tag, cid, flags, size, sha256), the embedded summary,
   `storage_tree_sha256`, the `time.*` facts, the sector accounting (the seven classes summing to the file
   length), the stream faults, and the `msg.*` gap rows. **Decide and state how a Phase 1b fact's `phase` int
   relates to the existing phase numbers and to `CURRENT_PHASE`/`LIVE`/`LIVE_TURN`** (the pinned `FACTS` ledger and the
   Phase 1 exit gate depend on it), with the consequences for `tests/ledger/facts_ledger.json`.
3. **`docs/design/phase1b-fixtures.md`: the fixture catalogue** in the form of `phase1-fixtures.md`. Start from the
   spec's list (about 50 names) and, for each: the family, a **construction table in prose** (storages and streams
   with names and sizes, property tags and types, code pages, body streams, recipients, attachments), what it
   exercises, the expected document status, the gap ids it must produce, and the consuming turn. State counts per
   family and check that they exceed every floor in `phase1b-facts.md`. Mark which are committed fixtures and which are
   test-only hostile seeds (named committed seeds). Include the hand-built Outlook-layout fixture's construction
   table **typed from `email-spike.md`'s tables B1-B4, not from any writer default**, and the cross-container pair
   (a `.eml` and a `.msg` of one synthetic message with the same HTML; `container_hash` differs, `body_digest`
   equal).
4. **`docs/design/phase1b-ledgers.md`: ledgers, allow-lists, declarations, golden** in the form of
   `phase1-ledgers.md` and `phase1-turn-declarations.md`. For every turn 1b.0b to 1b.10: the modules it adds or
   edits, the **new test function names it declares** (the collection test asserts them), its allow-list of paths, its
   pre-declared stop point and test ceiling (reconcile with the spec's table; the ceilings are guidelines). The label
   ledger additions (new support files and evals files), the `FACTS` ledger additions, the behavior-ledger
   components `cfb`, `msg_reader` and `msg_projection` (what each fingerprints and over which corpus, keyed
   `<version>|corpus:<N>`), and **the `.eml` golden**: its file path, exactly what it pins (serialized
   `EmailDocument`, `WalkResult`, `resolve_span` samples, `CapRecord`s, the store artifact bytes, `ParseResult`), its
   format, that nothing regenerates it silently, and how both interpreters are checked (a recorded waiver, not a
   silent skip).
5. **`docs/design/phase1b-probes.md`: the owner's structure-only probes P1-P6.** For each: the question, the exact
   command, what the output prints (counts, sizes and tag sets only; **never a value, a subject, an address, a
   filename or a stream's content**), what to paste back, and a worked fake example output so the owner can see the
   shape. Say plainly what each answer decides (P1 signed-mail layout -> owner decision O8; P2 time tags; P3 CFB
   layout incl. whether the extended DIFAT ever occurs -> decision O1's weight; P4 attachment and recipient tags
   before Turn 1b.7; P5 8-bit prevalence; P6 vendor HTML classes). The script `tools/msg_probe.py` is built in
   Turn 1b.0b; this document is its specification (its output schema is the contract). State the privacy rules: the
   probe refuses a path inside the repository, prints nothing it was not specified to print, and its output is
   pasted by the owner, never read by hearth's model from the owner's files.
6. **`docs/design/email-extraction-design.md`: revision 4, once.** Mark the revision at the top as the earlier
   revisions were marked. Correct D1 (own `cfb.py` reader; `olefile` is a tests-and-tools oracle only), amend D13
   (A'' architecture, the span table and pass-through, uniform `part_level`/`container_stream`, extended DIFAT read
   through, the hostile-CFB vocabulary, the class gate, RTF decompress-and-record with de-encapsulation cut, no
   synthesized headers, `storage_tree_sha256`, time facts), add the note to D14 about the `max_input_bytes`
   asymmetry, update the Phase 1b phasing paragraph to the thirteen turns, the gap registry list (three new ids,
   `msg.rtf_encapsulation_refused` not created), the open risks and the "Blocked on the user" list, and record
   owner decisions O1-O8 with the date 2026-10-11. List every changed line range in the report.
7. **`docs/design/phase0-gaps.md`:** register the three new ids (`msg.transport_headers_absent`,
   `msg.attachment_method_unsupported`, `msg.recipient_table_unreadable`) in the registry's exact entry form
   (Missing / A reader must not infer / First emitted by / Committed fixture); update the eight registered `msg.*`
   entries and `headers.mapi_header_property_disagree` with their first-emitting turn and committed fixture names from
   the catalogue; rewrite `msg.cfb_difat_extended` (observation, read through, owner decision O1) and reconcile it with
   D13; rewrite `msg.rtf_to_text_unsupported` (decompress-and-record; no body view from RTF, owner decision O2);
   note that a FAT cycle is a per-stream `msg.stream_truncated`, not a gap id of its own. **None is emitted by any
   code this turn.**
8. **`docs/design/open-inputs.md`:** record the owner decisions and the pending probes (a short edit in the style of
   the file). Do not edit `phase1b-build-spec.md` or `phase1b-debate.md`; if a contradiction between them and the
   design or the code is found, write it in the report and in the section "Contradictions found" of
   `phase1b-contract.md`, with both sides quoted.

## Checks before reporting

- `python -m pytest -q` before you start (record the count) and after: a documents-only turn must leave the suite
  exactly as green. Some tests read `phase0-gaps.md` and the design (the registry clauses); if adding the three ids
  to the registry makes one fail because the code registry lacks them, **stop and report it with the test name**: do
  not add code and do not edit the test. Run on 3.14 and 3.11 if both interpreters are available (the repo's
  `tools/runboth.py`).
- `git status` shows only files under `docs/design/` (and the three untracked Phase 1b files already there). No
  `emailextract/`, `tests/`, `tools/`, `fixtures/` change.
- Every file:line or test name you cite was opened, not recalled. Mark anything you took from the spec or the debate
  without re-reading the code as (unverified).
- No real or employer mail, no Downloads, no path outside the repo. Do not run the probes (they are the owner's).

## Rules

- Documents only. Do not write or edit Python, tests, fixtures, sidecars or ledgers' JSON.
- The design wins over the spec; the spec wins over the debate; report conflicts, do not paper over them.
- Every closed vocabulary you write is complete (no "etc."); every shape has a worked example; every number that is
  a guideline says so.
- If a decision cannot be made from the evidence, write it as an open question with the options and stop for the
  reviewer; do not pick silently.

## Deliverable

The eight documents above; a **resolution list** (each "decide in 1b.0a" item of the spec with the decision and the
one-line reason); the list of existing tests that must change (verified); the "Contradictions found" section; the
suite counts before and after; the exact `git status`; and anything not covered that needs the owner. Leave the tree
uncommitted for the reviewer.
