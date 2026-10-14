# Turn 1b.0c: the `.eml` golden, captured before any frozen-module edit

Status: brief for one build turn. Author: reviewer session, 2026-10-13. Builder: hearth. Builds on `c6728c0` (Turn
1b.0a) **plus the Turn 1b.0b files, which the owner commits first** (see "Before you start"). Run hearth in
`C:\Users\ivan_\App_repos\email-extract`, fresh session. Keep tool calls small. **Do not commit.**

## What this turn is

Build rule 2 (`phase1b-build-spec.md`, "Operating rules") says no measured `.eml` value may move in Phase 1b except
the direct consequences of the one schema bump (`"5"` -> `"6"`, Turn 1b.1). The behavior ledger's `walk` and
`decode_chain` fingerprints pin the `WalkResult`, but **nothing today pins the assembled `EmailDocument`**, the
`resolve_span` answers, the `CapRecord`s, the store artifact bytes or the `ParseResult`. Turn 1b.1 edits eight
places in frozen modules (`ids.py`, `walk.py`, `text.py`, `assemble.py`, `parse.py`, `store.py`, `model.py`,
`versions.py`). This turn builds the net **before** those edits: a committed golden file, an explicit recording
command, and a test that compares bytes and never regenerates silently.

This turn changes **no package code**. If you find yourself editing `emailextract/**`, stop: the golden must
describe the code as it is now, at schema `"5"`.

Allow-list (`turn=1b.0c`, from `phase1b-ledgers.md`): `tests/golden/`, `tools/update_eml_golden.py`,
`tests/test_eml_golden.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md` (outcome note only).
**Not** `emailextract/**`, `fixtures/**`, any sidecar, `pyproject.toml`, `CLAUDE.md`, `tests/ledger/behavior_ledger.json`,
`tests/ledger/corpus.json`.

Read first: `phase1b-contract.md` section 10 (the golden, in full) and section 11's first rows;
`phase1b-ledgers.md` section (d) and the `declaration turn=1b.0c` block (the ten tests you must name, exactly);
`phase1b-build-spec.md` rules 2 and 4; then the code the golden calls: `emailextract/parse.py` (`parse`,
`ParseResult`, `Limits`), `assemble.py` (`assemble`, `resolve_span`, `document_key`), `walk.py`, `store.py`
(`walk_artifact`, `document_artifact`, `artifact_key`), `container.py` (`EmlContainer`, `memory_bytes`), and
`tests/ledger/corpus.json`, `tools/behavior_ledger.py` (how the ledger enumerates the corpus, so the golden
enumerates it the same way).

## Before you start (owner)

1. **Commit the Turn 1b.0b files** (`docs/design/msg-architecture.md`, `docs/design/phase1b-turn-1b.0b-brief.md`,
   `tools/msg_probe.py`, the edit to `docs/design/phase1b-ledgers.md`). The golden must be captured on a clean tree.
2. **Answer the six questions at the end of `msg-architecture.md`.** They gate Turn 1b.1, not this turn, but the
   defaults below are what the 1b.1 brief will assume unless you say otherwise:

   | # | question | recommended default |
   |---|---|---|
   | Q1 | accept the lazy `raw_bytes()` (a `container.py` protocol change) in 1b.1 | **yes**: bounded, does not touch `_walk_visit` |
   | Q2 | P1 reads one property stream (the message class) beyond the properties table | **accept**, and amend `phase1b-probes.md` rule 2 to name it |
   | Q3 | extended DIFAT is read through (O1) | **confirm** |
   | Q4 | the `max_input_bytes` asymmetry (a 50 MB `.msg` passes the gate its ~67 MB base64 `.eml` twin fails) | **record as designed** |
   | Q5 | keep the 3x memory budget (so Q1 stands) | **keep** |
   | Q6 | a truncated CFB whose FAT is missing | keep `OUT_OF_RANGE`; no `cfb_file_truncated` name |

   Nothing in this turn depends on the answers. Record them in the commit message or in `phase1b-ledgers.md`, not in code.

## What to build

### 1. `tools/update_eml_golden.py` (the only way the golden is written)

* `python tools/update_eml_golden.py` records `tests/golden/eml_golden.json`; `--check` exits 1 if the committed file
  differs from a fresh recording and prints which fixture and which key moved; `--list` prints the pinned fixtures.
* It enumerates the corpus **exactly as `tools/behavior_ledger.py` does** (the current corpus version, 126 files at
  corpus version 8: `fixtures/generated` 88, `fixtures/raw` 33, `fixtures/time` 5). Do not hand-list fixtures. If the
  ledger's enumeration is not importable, say so and reuse its logic, do not fork a second rule for "which files".
* Output is **strict canonical JSON**: sorted keys, compact separators, `ensure_ascii=False`, `\n` newline, no BOM,
  no trailing whitespace, identical on Windows and Linux (CLAUDE.md-style: nothing may depend on dict order from a
  hash seed or the platform's newline translation). Write it in binary mode.
* No clock, no environment, no network, no randomness. Running it twice produces identical bytes (the test below
  asserts it).

### 2. `tests/golden/eml_golden.json` (committed)

A header object, then one record per fixture, keyed by the fixture's corpus-relative path.

**Header:** `golden_version` (`"1"`), `corpus_version` (the ledger's current corpus version), `schema_version`
(`OUTPUT_SCHEMA_VERSION`, which is `"5"` now), `email_parser_version`, `fixture_count`, the interpreter the file was
recorded on, and the **waiver** (below).

**Per fixture, exactly these six pins** (all derived by calling the public functions with the fixture's bytes through
`EmlContainer` / `memory_bytes`, under one declared `Limits`, which the header also records):

| pin | source | what it must contain |
|---|---|---|
| `parse_result` | `parse(data, ..., limits=...)` | the whole `ParseResult` (ok, reason id, detail, BOM and mbox byte counts) |
| `document` | `assemble(container, limits=...)` serialized with the codec | the whole `EmailDocument`, every field, including `container_hash`, every `part_id`, every `sha256`, every span |
| `walk` | the `WalkResult` the walker returns | the walker's shapes, ordering and tiling; this carries no schema version in its bytes |
| `caps` | `document.caps` | every `CapRecord` value, in order |
| `span_samples` | `resolve_span` | for every `PartRecord` and every `HeaderField` of the document, the `resolve_span` answer for its own span, plus the first, the last and one interior sub-span (this is the C2 identity guard Turn 1b.1 must keep byte-identical) |
| `store` | `walk_artifact` + `document_artifact` | the two store artifacts' **bytes** (as hex or base64 in the JSON, stated in the header) **and** their keys/paths as `artifact_key` / `document_key` compute them |

A failed parse (a fixture the parser refuses) still gets all six pins; a pin that does not apply is an explicit
`null` with the reason, never an omitted key.

**The waiver.** The spec says 3.14 and 3.11 differ "only in a recorded-heading field". Do not assume which field:
**run the recording on both interpreters** (the repo's two; find them the way `tools/behavior_ledger.py` /
`.scratch` do), diff the two outputs, and write the **exact** differing key paths into the header's `waiver` list.
If the interpreters differ in anything that is a pinned *value* (an id, a hash, a span, a cap), that is a **finding**:
stop and report it; do not waive it. If they are byte-identical, the waiver is the empty list and the test asserts
that it stays empty.

### 3. `tests/test_eml_golden.py` (the ten declared tests, exactly these names)

```
test_the_golden_matches_the_committed_corpus
test_the_golden_pins_the_document_walk_spans_caps_and_store_bytes
test_the_golden_is_not_regenerated_silently
test_the_golden_checks_both_interpreters_with_a_recorded_waiver
test_a_changed_measured_value_fails_the_golden
test_a_changed_schema_version_alone_is_the_permitted_move
test_the_golden_covers_every_committed_eml_fixture
test_the_golden_header_names_the_corpus_and_schema_version
test_resolve_span_samples_are_the_identity_guard
test_the_golden_file_is_listed_in_the_label_ledger
```

What each must actually prove (a test that cannot fail is a defect):

* **matches the corpus**: recompute every pin from the fixture bytes and compare bytes to the committed file; a diff
  names the fixture and the key.
* **pins the six things**: assert the six keys exist on every record and that `store` really carries artifact
  *bytes*, not a hash of them.
* **not regenerated silently**: the test module never writes the golden, never imports the recorder's `write`
  path, and a grep-style assertion confirms `tests/golden/eml_golden.json` is opened read-only in the test.
* **both interpreters**: runs on whichever interpreter executes it, applies the recorded waiver paths only, and
  fails if a differing path is not in the waiver. It must **not skip** on the other interpreter; the waiver *is*
  the recorded difference.
* **a changed measured value fails**: take a copy of the recorded golden in memory, change one `part_id`, one
  `sha256`, one span offset and one `CapRecord` value (four separate cases), and require the comparison to fail
  each time. This is the falsifier; it is the test that stops the golden being decorative.
* **schema version alone is the permitted move**: take the in-memory golden, change only `schema_version` and the
  `output_schema_version` values and the store keys that name it, and require the 1b.1-style comparison to classify
  that as "permitted"; then add one stray change and require it to be classified "not permitted". (This builds the
  comparator Turn 1b.1's `test_the_bump_moved_only_the_version_and_the_null_keys` will reuse; put the comparator in
  `tests/support/` only if you must, otherwise in the test module, and say which.)
* **covers every fixture**: the golden's keys equal the ledger's corpus file list for the current corpus version;
  a new fixture added without re-recording fails here.
* **header**: names the corpus version and the schema version and they equal the live constants.
* **`resolve_span` samples**: for a fixture with a multi-part message, a header with a folded line and a part with a
  nonzero offset, assert the samples are present and non-trivial (not all `Unresolvable`).
* **label ledger**: `tests/ledger/label_ledger.json` lists the golden file, hashed, the way it lists other
  committed expected-value files (open `tests/test_label_ledger.py` to see the rule; add the entry the same way).

### 4. Determinism and the empty-case rule

Recording twice must give identical bytes, on both interpreters, under two different `PYTHONHASHSEED` values. A
golden that pins zero fixtures, or a corpus enumeration that returns zero files, must **fail loudly**, not pass.

## What must NOT be done

* Do not edit `emailextract/**`, a fixture, a sidecar, or the behavior ledger. The golden describes the code as it is.
* Do not hand-type or hand-edit the golden file. It is produced only by the recorder.
* Do not weaken the comparison to hashes of hashes: the store pin carries the artifact **bytes**.
* Do not skip on the second interpreter and call it a waiver; a waiver names exact key paths.
* Do not pin anything that depends on the clock, the machine, the path of the checkout or `PYTHONHASHSEED`. If a
  value does, that is a finding about the code: report it, do not paper over it.
* Do not start Turn 1b.1 and do not touch `OUTPUT_SCHEMA_VERSION`.

## Checks and report

1. `python -m pytest` green (the full suite, not only the new file), on the primary interpreter, and the new file
   on the second interpreter too.
2. `python tools/update_eml_golden.py --check` exits 0; running the recorder twice leaves `git status` unchanged.
3. `python tools/update_behavior_ledger.py --check` (the existing ledger tool) still green: this turn moves no
   version and no fingerprint.
4. Mutation: say, for each of `test_a_changed_measured_value_fails_the_golden`'s four cases, that you ran it and saw
   it fail, and what you changed.
5. Write the outcome into `phase1b-ledgers.md` (the turn's section only): the golden's size in bytes, the fixture
   count, the waiver paths (or "none"), and any finding. State anything that surprised you, especially any
   non-determinism the recording exposed.

Stop at the turn boundary: the golden is captured and green, before any frozen-module edit. Do not commit. The owner
commits, then the Turn 1b.1 brief is written against the recorded golden and the six answers above.
