# Turn 1b.1: the one schema bump (`"5"` -> `"6"`), the eight provenance points and the `value_codec` seam, built against `FakeMsgContainer`

Status: brief for one build turn. Author: reviewer session, 2026-10-13. Builder: hearth. Builds on `33f1409` (Turn
1b.0c: the `.eml` golden is committed) and `5a4cc06` (Turn 1b.0b: A'' ratified structurally). Run hearth in
`C:\Users\ivan_\App_repos\email-extract`, fresh session. Keep tool calls small. **Do not commit.**

This is the riskiest turn of Phase 1b: it is the first to edit frozen modules (`model.py`, `versions.py`, `ids.py`,
`walk.py`, `text.py`, `assemble.py`, `parse.py`, `store.py`, `container.py`). The net under it is the golden
(`tests/golden/eml_golden.json`). No CFB reader exists yet and none is written here: everything is built against a
hand-made `FakeMsgContainer`, as Phase 0 did with `FakeContainer`.

Read first, in this order: `phase1b-contract.md` (all of it; sections 1, 8, 9, 10, 11 are the spec of this turn),
`phase1b-build-spec.md` ("Operating rules", "The architecture decision"), `msg-architecture.md` (sections 2 E4-E8, 5, 6,
7), `phase1b-ledgers.md` (the `declaration turn=1b.1` block and section (d)), then the code: `model.py`
(`PartRecord`, `HeaderField`, `AttachmentOccurrence`, `REASON_TABLE`, `_check_axis_pair`), `assemble.py`, `walk.py`
(`_walk_visit`, `header_fields_at`, `header_region`, `CAP_REASONS`), `ids.py`, `text.py` (`analyse_part`,
`VERBATIM_REASONS`), `store.py`, `parse.py`, `container.py`, `tests/test_eml_golden.py` and `tools/update_eml_golden.py`.
The 1b.0b scratch prototypes (`C:\Users\ivan_\AppData\Local\Temp\msg-spike\`: `cfbproto.py`, `idents.py`,
`headerseam.py`, `precision.py`, `storeprobe.py`, `compare.py`) may still exist: read them as **evidence, not code to
copy** (rule 1 of the 1b.0b brief: a prototype is not the implementation).

## Owner decisions in force

The six 1b.0b questions are taken at their recommended defaults (the owner may overrule any before this turn is
committed): **Q1** the lazy `raw_bytes()` is in this turn's scope; **Q2** P1's one extra property-stream read stands
(amend `phase1b-probes.md` rule 2 to name it, docs only); **Q3** extended DIFAT is read through (O1); **Q4** the
`max_input_bytes` asymmetry is recorded as designed; **Q5** the 3x memory budget stands; **Q6** a truncated CFB whose FAT
is missing stays `OUT_OF_RANGE` (no `cfb_file_truncated` name). O1-O8 of the build spec stand.

## Three decisions the reviewer made because the contract does not survive contact with the code

Each was found by reading the code and the committed golden. They are **decisions, not suggestions**; if you disagree
with one, stop and say so with the evidence rather than building around it. All three are recorded in the note.

**D1. `limits_fingerprint` forbids adding fields to `Limits` in this turn.** Contract section 1(Y) says `Limits` gains
`max_sector_count`, `max_directory_entries`, `max_difat_chain_length`. But `assemble.limits_fingerprint` hashes
**every** field of `Limits` in declaration order (`assemble.py`, `limits_fingerprint`) and that fingerprint is part of
`document_key`, so a new field would change the store key of **every `.eml` document**, beyond "the version string
only" (contract section 10, rule 2). It would also break every call that builds a `Limits` with all seven fields
(`Limits` has no defaults, by design). Therefore **`Limits` does not change in this turn.**
* `REASON_TABLE[Status.SKIPPED]` gains the three reasons, as the contract says.
* `walk.CAP_REASONS` stays the walker's **five**; add `CFB_CAP_REASONS` (the three new ids) beside it, and amend
  `tests/test_limits.py:271` from `set(CAP_REASONS) == set(REASON_TABLE[Status.SKIPPED])` to
  `set(CAP_REASONS) | set(CFB_CAP_REASONS) == set(REASON_TABLE[Status.SKIPPED])` (and `len(CAP_REASONS) == 5` stays
  true). This row is **not** on the contract's section 11 list; it is the first of the extra breakages.
* Where the CFB limits live is **Turn 1b.3's** decision, under one binding constraint written into the note now:
  *`limits_fingerprint(L)` and `document_key` must be byte-identical for every existing `Limits` value* (the golden
  proves it). A separate `CfbLimits` published by the container is the expected shape.
* Add `test_limits_fingerprint_is_unchanged_by_the_bump`: pin the fingerprint of `Limits.untrusted()` and of the
  golden's declared `Limits` to the **pre-bump value computed on `33f1409`** (a characterization pin; say so in the
  test's docstring).

**D2. The permitted golden diff is larger than contract section 10 says.** Part (Z) adds `AttachmentOccurrence.embedded`,
and `AttachmentOccurrence` records are inside every `.eml` document that has attachments (verified in the golden:
`attach_manifest_baseline.eml` has an `attachments` list of full occurrence records). So the re-recorded document gains
`"embedded": null` per occurrence, in addition to `"stream_ref": null` per `PartRecord`/`HeaderField` and the
`output_schema_version` value. `test_the_bump_moved_only_the_version_and_the_null_keys` must permit **exactly these
three** classes of difference and nothing else (a stray fourth must fail; build the falsifier). Update contract section
10 and `phase1b-ledgers.md` section (d) to say so (docs only).

**D3. `parse` cannot honestly "open a CFB container" in this turn, and `ingest` must not regress.** `parse` returns a
`ParseResult` whose success kind is asserted to be `"rfc822"`, and `ingest._row_for` builds an `EmlContainer` from every
non-error result (`ingest.py:238-246`); with no CFB reader, letting a CFB magic succeed would turn CFB bytes into a junk
rfc822 document. So point 8 is built as a **seam**, finished in 1b.5:
* `parse(data, container_kind=None, *, limits, open_cfb=None)`. `open_cfb` is `Callable[[bytes, Limits], ParseResult]
  | None`. With `open_cfb=None` (every existing caller, `ingest` included) a CFB magic or a claimed `cfb_msg` is
  refused **exactly as today**, with `cfb_msg_unsupported`. With an `open_cfb` supplied (the test's
  `FakeMsgContainer`-based opener) its result is returned.
* `ParseResult` accepts kind `"rfc822"` **or** `"cfb_msg"` on success (update its `__post_init__` and docstring).
* `NAMED_ERROR_REASONS` **adds** `cfb_directory_loop` and `cfb_header_unsupported` and **keeps**
  `cfb_msg_unsupported`, marked in a comment "interim: deleted in Turn 1b.5 when the real opener is wired".
* Consequences: `test_ingest.py:217` and `test_parse_entry.py:92,97,140-142` keep passing **unchanged** in this turn; only
  the exact tuple at `test_parse_entry.py:189-196` changes. The declared test
  `test_named_error_reasons_drop_cfb_msg_unsupported` is **renamed**
  `test_named_error_reasons_gain_the_two_cfb_faults` (it asserts the new tuple, with `cfb_msg_unsupported` still a
  member); update the declaration in **both** `phase1b-ledgers.md` and the mirror block in
  `phase1-turn-declarations.md`. Turn 1b.5's brief will own the deletion and the `test_ingest`/`test_parse_entry` flips.

## What to build

### A. The contract (`model.py`, `versions.py`; export from `emailextract/__init__.py` as the file already does)

1. `OUTPUT_SCHEMA_VERSION` `"5"` -> `"6"`. **`EMAIL_PARSER_VERSION` does not move, and no `CFB_VERSION` /
   `MSG_READER_VERSION` / `MSG_PROJECTION_VERSION` is added** (those arrive with their components in 1b.3 to 1b.5 and
   the ledger in 1b.10). If `tools/update_behavior_ledger.py --check` demands any other bump, **stop and say so**.
2. (X) `ContainerStreamAxis`, `StreamFault`, `ContainerStreamRef` exactly as contract section 1(X), with the four
   invariants raised as `CodecError` in the parent's `__post_init__` (`PartRecord`, `HeaderField`), and `stream_ref:
   ContainerStreamRef | None = None` as the **last** field of both. Strict-codec round trip for a real ref, a synthetic
   ref and `None`.
3. (Y) `REASON_TABLE[Status.SKIPPED]` += `sector_count_cap`, `directory_entries_cap`, `difat_chain_length_cap`;
   `walk.CFB_CAP_REASONS` per D1. `NAMED_ERROR_REASONS` per D3. `text.VERBATIM_REASONS` += `container_stream`
   (`REASON_CONTAINER_STREAM`).
4. (Z) `EmbeddedSummary` and `AttachmentOccurrence.embedded: EmbeddedSummary | None = None` (last field), validators per
   the contract. The "only on an `embedded_message` occurrence" invariant is Turn 1b.7's; do not enforce it here.
5. Contract section 11 rows that belong to **this** turn (verified list; each is a pinned literal that must move, and
   nothing else may): `test_status_reasons.py` (the `skipped` tuple; the `11` -> `14` owner count),
   `test_contract_phase1.py` (the `SKIPPED` tuple; the `"5"` -> `"6"` test, renamed
   `test_output_schema_version_is_six` and moved to `test_contract_msg.py` if that is where the declaration puts it),
   `test_parse_entry.py:189-196` (D3), `test_assemble.py:187,196` and `test_store.py:166,169,209` (the version),
   `test_behavior_ledger.py` + `tests/ledger/behavior_ledger.json` (a `"6"` `contracts` line, appended by the updater),
   `test_turn_declarations.py` (declare every new test; add `1b.1` to `BUILT_TURNS`), `test_limits.py:271` (D1).
   Rows that belong to **later** turns stay untouched here: the `olefile` rows (1b.2), `test_phase1_scope` library and
   import rows (1b.3 to 1b.5), `test_ingest`/`test_parse_entry` CFB rows (1b.5). If a test **not** named here fails,
   it is a finding: report it with the evidence, do not edit it to pass.

### B. The eight provenance points (contract section 8; each gated, each default branch the current expression **verbatim**)

For every point: the `.eml` path is byte-identical (the golden is the judge) and a unit test proves the default branch
by calling it with no span table and comparing to the pre-edit result.

1. **Assembler fills `stream_ref`.** `_header_fields` and `_part_records` gain a `span_table=None` keyword; with a
   table they set `stream_ref` and `size_bytes`/`sha256` per contract section 5. Without one, the constructors are
   today's, untouched.
2. **Kind-gated `part_id`** (`walk.py:730,799`; `ids.py`). With a span table the id is over
   `(container_hash, source-keyed {stream, byte_off, byte_len} or synthetic:<role>:<ordinal>, sha256(real source
   bytes))`, so it does not depend on the virtual framing length. The `.eml` expression
   `part_id(container_id, span, content_hash(span.slice(raw)))` stays as the default branch.
3. **`resolve_span`** returns the part's `ContainerStreamRef` (a source span) or `Unresolvable(span_not_resolvable,
   part_id)` for a span-table container; **never** a virtual offset. The return type widens to
   `RawSpan | ContainerStreamRef | Unresolvable`.
4. **`analyse_part`** gets a `container_stream=False` keyword. When `True`: `reason = REASON_CONTAINER_STREAM` before the
   `if reason is None` and no offset map is built; `analyse_parts`/`resolve_span` pass it for a span-table container.
5. **Charset provenance.** After the walk, the **assembler** overwrites `PartRecord.encoding_source` and
   `decode_chain.used_charset`/`declared_charset` from `getattr(container, "charset_sources", None)`; the walker only
   ever says `declared_charset`.
6. **Cap records carry real counts.** `_caps` and the attach cap-skip helper build `CapRecord`s from the container's
   published observed counts when present (`getattr(container, "cap_observations", None)`), never a virtual region
   length; the defaults are unchanged.
7. **Store.** For a container with `span_provenance`/`sector_accounting`, `walk_artifact` persists the eight-class
   sector accounting plus the **source-only** span table (`PersistedSpanRow`; never `virtual_offset`/`virtual_len`),
   not the walker's virtual `Region`s. The `.eml` artifact bytes are untouched. A test proves the persisted table
   recomputes the virtual offsets deterministically from the fake's source bytes and `projection` label.
8. **`parse` seam** per D3.

**The re-open trigger (contract section 8, spec A2).** If, to make `walk(msg)` equal `walk(eml-twin)` modulo
provenance, you find you must change **tiling or ordering inside `_walk_visit`**, **stop**. Do not build the
`MsgContainer`-builds-`PartShape` fallback. Write the evidence into the note and let the owner re-open A''. Points 2, 4
and 5 are keyword/default additions; if one cannot be, that is the signal.

### C. The `value_codec` seam (contract section 9)

`header_fields_at(raw, start, end, *, value_codec="latin-1")` and `header_region(raw, result, *, max_work_units,
value_codec="latin-1")`; the default is the current `.decode("latin-1")` expression at all four sites
(`walk.py:483-485,510,525,551`). A test: the default produces the same result as before on every header fixture
(compare against the golden's `document.headers`); `value_codec="utf-8"` on a UTF-8 virtual header returns the real
text in `raw_value` and `text_decodes`.

### D. The lazy `raw_bytes()` (Q1; experiment E4 failed its 3x budget at 4.0x)

Goal, measured exactly as E4 measured it: a synthetic 40 MiB pass-through attachment through `walk()` **and**
`assemble()` has a peak RSS delta **<= 3x the stream**. Do it in this order, and stop at the first step that meets the
goal:
1. **Profile first** (`tracemalloc` or the E4 harness idea; the harness itself is scratch, outside the repo): name the
   copies that make 4.0x. E4 saw: the virtual string once, the walker's leaf copy, `assemble()`'s second walk/copy.
2. **Smallest change that removes copies**: hash from a `memoryview` slice (`hashlib.sha256(view[a:b])` copies
   nothing), compute lengths without slicing, and let `assemble()` reuse the walker's result instead of re-walking
   where it already can. Only if that is not enough:
3. **A lazy view** on the `Container` protocol (for example an optional `raw_view() -> memoryview`, with
   `raw_bytes()` kept for every existing caller). `EmlContainer`/`FakeContainer` stay valid (the protocol is
   `@runtime_checkable`; adding a **required** member breaks structural checks, so it must be optional via `getattr`
   like `span_provenance`).
`bytes`-only operations (`.find`, `.split`, `.startswith`, `.decode`, regex on slices) do not all exist on
`memoryview`; if the lazy view forces edits to those call sites inside `_walk_visit`'s control flow, that is the
re-open trigger above, not a licence to restructure. **If the 3x goal cannot be met without that, stop** and report
the measured number and the smallest design that would meet 5x: the owner then decides Q5 (re-declare the budget; the
spec already bounds the worst case by `max_input_bytes`, 64 MiB -> ~256 MB). Re-run the E4 measurement at the end and
record both numbers (before 4.0x, after) in the note. A pass-through-only goal; the re-encoded case (7.05x) is recorded,
not gated, in this turn.

### E. `tests/support/fake_msg_container.py` (hand-made; hand-typed expectations)

A `Container`-protocol class with `container_kind == CFB_MSG` that returns **hand-written virtual RFC 822 bytes** and
publishes, via `getattr`: `span_provenance` (a tuple of `SpanRow`, contract section 7, written by hand, not computed),
`charset_sources`, `sector_accounting` (eight classes, summing to a stated file length) and `cap_observations`. It takes
a `framing` parameter (extra padding in the synthetic regions) so a test can vary the virtual length without changing
any source byte. Two constructed messages, each with an `.eml` **twin** (a hand-written equivalent `EmlContainer`
message): (1) headers + an HTML body; (2) the same plus one pass-through attachment and one re-encoded header field.
Every expected id, offset, digest and stream name in the tests is **typed by hand** from the construction (rule 5): no
value is pasted from running the code. Add `tests/support/fake_msg_container.py` to `tests/ledger/label_ledger.json` via
`tools/update_label_ledger.py` (additions only).

### F. Tests (the declared set, exactly these names; plus the extras below)

The 24 declared in `phase1b-ledgers.md` (`test_contract_msg.py` x8 with the D3 rename, `test_provenance_points.py` x15,
`test_eml_golden.py::test_the_bump_moved_only_the_version_and_the_null_keys`). What the less obvious ones must prove:
* `test_two_framing_lengths_give_identical_part_ids`: the fake at `framing=0` and `framing=500` gives the same
  `part_id`s, `PartRecord`s (modulo nothing) and citations (C2).
* `test_the_eml_part_ids_are_byte_identical`: every `part_id` of every golden fixture equals the golden's.
* `test_walk_msg_matches_walk_of_the_equivalent_eml_modulo_provenance`: for both constructed messages, tiling, ordering,
  part count, header fields and decode chains equal the twin's; the **only** differing fields are the provenance ones
  (list them in the test, so an extra difference fails).
* `test_resolve_span_still_refuses_a_virtual_offset`: no return value of `resolve_span` for the fake carries a virtual
  offset (assert on every field and on the serialized form).
* `test_the_bump_moved_only_the_version_and_the_null_keys`: re-recorded golden vs the 1b.0c golden: the `walk` pins
  byte-identical; `document` differs by the three classes of D2 only; store keys/paths by the version string only;
  `parse_result`, `caps`, every `container_hash`/`part_id`/`sha256`/span byte-identical. Include the falsifier (a stray
  fourth difference fails).
Extras: `test_limits_fingerprint_is_unchanged_by_the_bump` (D1); a test that adding a `cfb_msg` document to the fake store
changes no `.eml` store byte; a mutation test for each of the eight points' **gate** (remove the gate; the `.eml`
default branch test must fail).

### G. Golden re-record and ledgers (same commit as the bump, by the owner)

Run `python tools/update_eml_golden.py` **once**, after everything else is green, and show the diff summary (counts of
the three permitted classes, zero of anything else) in the note. `python tools/update_eml_golden.py --check`,
`tools/update_behavior_ledger.py` (record the `contracts` `"6"` line; it must not ask for any other bump),
`tools/update_label_ledger.py --check`, `tools/make_fixtures.py --check` all exit 0. Allow-list: the modules in the
`declaration turn=1b.1` block **plus** `emailextract/container.py`, `emailextract/__init__.py`, the existing tests in A5,
`tests/test_limits.py`, `tests/ledger/behavior_ledger.json`, `tests/ledger/label_ledger.json`,
`docs/design/phase1b-ledgers.md`, `docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-contract.md` (the D2
correction and the D1 note only), `docs/design/phase1b-probes.md` (Q2's rule-2 amendment only). **Not** `fixtures/**`,
any sidecar, `pyproject.toml`, `CLAUDE.md`, `emailextract/ingest.py`.

## What must NOT be done

No edit to a measured `.eml` value; the golden re-records **only** the three permitted classes. No field added to
`Limits`. No CFB reader, no `cfb.py`/`mapi.py`/`msgcontainer.py`, no `olefile` anywhere in `emailextract/`. No
restructuring of `_walk_visit`. No change to `ingest.py`. No version bump other than `OUTPUT_SCHEMA_VERSION`. No `msg.*`
gap emitted (they are first emitted in 1b.3 to 1b.7). Do not edit a hand-typed expectation to make a test pass; a
disagreement is a finding. Do not weaken the golden comparator to hide a diff. Do not commit.

## Checks and report

1. `python -m pytest` green (the full suite), on both interpreters (3.14 and the repo's 3.11; the sibling
   `docextract_core` must be **installed** for the subprocess tests: a `PYTHONPATH` shim makes five unrelated tests fail,
   which is an environment artefact, not a finding).
2. The memory goal of section D: before and after numbers.
3. The outcome note in `phase1b-ledgers.md` (this turn's section only): the three decisions and any you changed; the
   golden diff summary; the list of tests you edited and why, each tied to a row of section A5 or reported as an extra;
   every place a pinned number moved; the E4 numbers; anything the contract got wrong that this brief did not catch.
4. The next turn's inputs: what 1b.2 (the `tools/cfb_writer.py` and first fixtures) and 1b.3 (`cfb.py`, where the CFB
   limits must live under D1's constraint) need from this turn's seams.

Stop at the turn boundary: the bump is green and the golden re-check passes. Do not start 1b.2.
