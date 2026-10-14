# Turn 1b.0b: the architecture spike (eight experiments) and the owner's probe script

Status: brief for one build turn. Author: reviewer session, 2026-10-11. Builder: hearth. Builds on `c6728c0` (Turn
1b.0a committed). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session, DeepSeek Pro with the
400,000-token window (`HEARTH_MODEL=deepseek-v4-pro HEARTH_CONTEXT_WINDOW_TOKENS=400000
HEARTH_STREAM_IDLE_TIMEOUT_SECONDS=600 HEARTH_REQUEST_TIMEOUT_SECONDS=600 HEARTH_MAX_TOKENS=16384`, key from the
environment). Keep tool calls small. **Do not commit.**

## What this turn is

A spike, as Turn 1.0d was: **no package code, no tests, no fixtures**. It answers the questions the Phase 1b contract
(`docs/design/phase1b-contract.md`, committed) left to measurement, so the owner can ratify architecture **A''** (virtual
RFC 822 bytes plus a serialized provenance layer) or re-open it **before** Turn 1b.1 edits frozen modules. It also builds
the owner's structure-only probe script. Allow-list: `docs/design/msg-architecture.md` (new), `tools/msg_probe.py`
(new), `docs/design/phase1b-ledgers.md` (only to record this turn's outcome). **Not** `emailextract/**`, `tests/**`,
`fixtures/**`, any sidecar or ledger JSON, `pyproject.toml`, `CLAUDE.md`.

Read first: `phase1b-build-spec.md` ("The architecture decision", "Turn 1b.0b: the eight experiments"),
`phase1b-contract.md` (sections 1, 5, 7, 8, 9, 10), `phase1b-probes.md` (the probe specification, in full), and the
code the prototypes lean on: `emailextract/ids.py` (`part_id`), `walk.py` (`header_fields_at`, `_walk_visit`,
`_charset_ladder`), `text.py` (`analyse_part`), `assemble.py` (`resolve_span`, `_part_records`), `store.py`,
`container.py` (`FakeContainer`), `tools/real_probe.py`.

## Rules

1. **All experiments run in a scratch directory outside the repo**
   (`C:\Users\ivan_\AppData\Local\Temp\msg-spike`, create it). They **import** `emailextract` from the repo read-only
   and **never modify it**; where a prototype needs a seam that does not exist yet (a `value_codec`, a span table, a
   kind-gated `part_id`, a `container_stream` precision), build it in scratch by **subclassing or monkeypatching**, and
   say so. A prototype is evidence about the design, not the implementation (that is 1b.1 to 1b.5).
2. **Synthetic bytes only.** No real or employer mail, nothing from Downloads. A scratch `mini_cfb.py` (about 150
   lines, **not** the later `tools/cfb_writer.py`) builds the CFB files these experiments need; hand-type every layout
   from `docs/design/email-spike.md`'s tables B1 to B4, not from a writer default.
3. **`olefile` is installed only in scratch** (`pip install --target <scratch>\site olefile`), recorded with its
   version; never added to `pyproject.toml` or the repo's environment.
4. **Pre-register.** Before running any experiment, write its pass/fail criterion and the number that would decide it
   into `msg-architecture.md` (commit nothing; just write it first) and **do not change a criterion after seeing a
   result**. A criterion that turns out wrong is reported as such with the corrected one beside it.
5. **Every measured number carries the command that produced it and a sha256 of the output** (build-spec rule 7);
   anything you cannot re-run is marked "verify empirically" and is not a decision input. Name, for each result, the
   later turn whose test will re-run it.
6. **A result that contradicts the contract is a finding**, written with both sides quoted; do not bend a criterion or
   the contract to make the architecture look good. If A'' fails a constraint, say which and name the fallback.

## The eight experiments (inputs are hand-built; criteria are pre-registered as above)

- **E1: `olefile` on the hostile set.** Build: the six mutants of the debate (cyclic FAT chain, claimed size 2**40,
  claimed size 0xFFFFFFFF, start sector out of range, directory self-reference, file truncated to 1200 bytes), plus a
  v4 (4096-byte sector) file and a 4095/4096/4097-byte stream trio at the mini-stream cutoff. Run `olefile` on each
  with a hard per-case timeout. **Record** the outcome class of each (raised, hung, clamped, silent, issue recorded) and
  whether `ole.fat`/`minifat`/`direntries` let you reconstruct a per-sector classification. Settles: the oracle's
  scope (well-formed inputs only is the expected result; confirm or refute with the new mutants).
- **E2: the `read_stream` fault contract.** Prototype `read_stream(file_bytes, start, size, ...) -> (bytes, fault)` in
  scratch with `fault in {OK, CYCLE, OUT_OF_RANGE, SHORT_CHAIN}` and header/directory validation that classifies a
  directory loop and an unsupported header (sector shift outside {9,10,11,12} for v3, or v4 with shift != 12) as
  whole-file faults. Run it on every E1 mutant plus a directory loop and a bad header. **Pass:** no input raises or
  hangs (hard timeout); every mutant maps to exactly one outcome of the contract vocabulary
  (`cfb_directory_loop`, `cfb_header_unsupported`, a per-stream fault, or clean); work is bounded by a counter you
  declare per input byte (state the bound).
- **E3: sector accounting.** On every E1 fixture classify every sector into the **eight** classes (header, DIFAT, FAT,
  miniFAT, directory, stream, free, slack). **Pass:** the eight byte counts sum to the file length on every well-formed
  fixture; on a cyclic-chain mutant the cycle is visible as an explicit unaccounted or double-claimed range, never
  silently absorbed.
- **E4: large-attachment memory.** A synthetic 40 MiB attachment stream, projected (a) pass-through and (b)
  re-encoded to UTF-8/base64, through the existing `walk()`/`assemble` path with a `bytes`-valued container. Measure
  peak RSS delta (process-level, one subprocess per case, `psutil` is **not** a dependency: use the OS API or
  `tracemalloc` plus `resource`/`ctypes` on Windows and say which). **Declare the budget before measuring** (propose:
  at most 3 times the stream size above baseline for pass-through). **Settles:** whether a lazy `raw_bytes()` (a
  `container.py` protocol change) is needed or `bytes` is acceptable.
- **E5: identity determinism.** With a scratch `FakeMsgContainer` (hand-made virtual bytes plus a hand-written
  source-only span table in the contract's `SpanRow` shape), build the **same** message at two framing lengths (for
  example an `X-Pad` header that differs in length). Show first, with the **unmodified** code, that `part_id` and
  `parent_part_id` move (this reproduces the debate's finding), then with a scratch kind-gated `part_id` (over
  `{stream, byte_offset, byte_len}` and the real source bytes' sha256, per contract section 8 point 2) show they do
  **not**. **Pass:** identical `PartRecord`-level ids, citations and `WalkResult` modulo provenance fields at both
  lengths; the `.eml` ids are byte-identical to the committed corpus for the default branch.
- **E6: the 8-bit header seam.** Non-ASCII header text from a `001F` stream and from a `001E` stream (cp1252 and
  UTF-8 cases) projected to UTF-8, run through the existing header stage with a scratch `value_codec`
  (`header_fields_at(..., value_codec="utf-8")` prototyped by a wrapper, not an edit). **Pass:** `raw_value` and
  `text_decodes` equal the hand-typed expected text for every case (typed before running); the default codec path
  on the `.eml` corpus is byte-identical to the committed behaviour; a trailing NUL, a UTF-8 BOM, LF-only line endings
  and an odd-length UTF-16 stream are each handled without raising (state how).
- **E7: precision.** A body already decoded to text and projected pass-through and re-encoded, run through
  `text.analyse_part` with a scratch `container_stream=True` precompute. **Pass:** every `.msg` leaf comes out
  `part_level`/`container_stream` with **no** offset map and never `exact`; `resolve_span` for a span-table container
  returns a stream-keyed span or `Unresolvable` and never a virtual offset (prototype the contract's section 8
  point 3). Show the unmodified code returning `exact` against the virtual bytes (the finding).
- **E8: the store artifact.** One scratch `FakeMsgContainer` document through the real store path with the contract's
  **source-only** `PersistedSpanRow`. **Pass:** re-ingest is byte-identical; the persisted bytes contain no
  `virtual_offset`/`virtual_len` (assert by scanning); the `.eml` artifact bytes are untouched; the persisted table
  **recomputes** the virtual offsets deterministically from the CFB bytes and a projection version (show the
  recomputation reproduces the same rows).
- **The comparison.** `walk(msg-virtual)` versus `walk(EmlContainer(an equivalent synthetic .eml of the same
  structure))`, compared field by field modulo the provenance fields. **Pass:** no difference in tiling, ordering,
  part count, header fields or decode chains. **If it forces an edit inside `_walk_visit`'s structure, stop and say so
  plainly: the architecture decision is re-opened** (named fallback: a `MsgContainer` that builds `PartShape` itself,
  costed honestly with the ~200 duplicated lines).

## The probe script: `tools/msg_probe.py` (in the repo)

Implement exactly the specification in `docs/design/phase1b-probes.md` (P1 to P6; read the "Privacy rules" first):
`python tools/msg_probe.py --probe <P1..P6> <DIR> [--limit N]`, plain-text paste-ready output of **counts, sizes, tag
sets and presence lines only**. Start from `tools/real_probe.py` (keep its refusal of a path inside the repository and
add the `fixtures/` tree). `olefile` is allowed here because it is a dev tool outside the package (say so in the
docstring and keep the existing "requires olefile" note). Hard rules, each demonstrated in scratch:
1. It prints **no** value: no subject, address, header text, filename, body or stream content, and no raw tag value
   other than the code-page numbers and the closed vocabularies the probes spec names. **Sentinel test (in scratch,
   evidence in the note):** build a synthetic `.msg` whose subject, sender, recipient, attachment filename and body
   contain sentinel strings; run every probe on it; assert none of the sentinels appears in any output.
2. The only stream it reads is the structural `__properties_version1.0` table (and directory entries/sizes); it never
   opens a body or header stream for reading. Demonstrate by instrumenting the file reads in the scratch run.
3. It refuses a path inside the repository or under `fixtures/` (exit 2, one-line message), and a missing/empty
   directory (exit 2). It never raises on a malformed `.msg`: that file is counted in an `unreadable` tally with a closed
   reason, and the probe continues.
4. Expected-output check: run each probe on a small synthetic directory of hand-built `.msg` files with known tags and
   compare to the **hand-typed** expected text (typed before running); paste both in the note.
Do not run the probe on any real file: that is the owner's step.

## `docs/design/msg-architecture.md` (the deliverable)

Sections: the pre-registered criteria (written first); per experiment the input description, the command, the result,
the sha256 of its output, the verdict against the criterion and the later turn whose test will re-run it; the
**comparison** result; the probe script's evidence (sentinel test, instrumented reads, expected-output diffs); an
explicit **Decision**: "A'' is ratified" or "re-open, because ...", with any constraint (C1 to C6 of the build spec) that
failed named; every deviation from the contract; and a list of questions for the owner. Also add a short "Outcome of
Turn 1b.0b" paragraph to `phase1b-ledgers.md` (only that file's turn-record section).

## Checks and report

`python -m pytest -q` before and after: identical results (this turn changes no test and no package file). `git status`
shows only `docs/design/msg-architecture.md`, `docs/design/phase1b-ledgers.md` and `tools/msg_probe.py`. Every
`file:line` you cite was opened. **Report:** the decision, the table of experiment verdicts, the memory numbers with
their declared budget, the sentinel-test result, and anything that needs the owner. If any experiment fails its
criterion or the comparison forces a `_walk_visit` edit, write it up and **stop**; do not start Turn 1b.0c or build
anything. Leave the tree uncommitted.
