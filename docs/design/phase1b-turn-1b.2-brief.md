# Turn 1b.2: the deterministic CFB test-file writer, the first `.msg` fixtures and the `olefile` oracle

Status: brief for one build turn. Author: reviewer session, 2026-10-13. Builder: hearth. Builds on `b8e07c1` (Turn 1b.1
committed: the bump, the eight provenance points, the golden re-recorded). Run hearth in
`C:\Users\ivan_\App_repos\email-extract`, fresh session. Keep tool calls small. **Do not commit.**

This turn adds **no library code**. It builds the instruments the CFB reader (1b.3) will be judged by: a writer that
produces valid `.msg` containers from a hand-typed description, fixtures built with it, and an independent comparator
(`olefile`). Rule 3 of the build spec is the reason it exists: *writer and reader share an author, so they can agree on a
wrong layout.* Every check below is aimed at that.

Read first: `phase1b-build-spec.md` (rules 1, 3, 5; the 1b.2 row; O4, O7), `phase1b-fixtures.md` (Family D, the
construction-table convention, "Test-only hostile seeds"), `phase1b-ledgers.md` (the `declaration turn=1b.2` block and its
allow-list), `phase1b-facts.md` (`msg.container_layout`, `msg.sector_accounting`), `msg-architecture.md` (E1 and E3: what
`olefile` does and does not do; the eight sector classes), `email-spike.md` tables B1-B4 (the observed Outlook layout),
MS-CFB (the format spec is public; cite section numbers in your comments, never copy `olefile`'s code), and
`tools/make_fixtures.py` (the pattern: deterministic, `--check`, no clock). The 1b.0b scratch writer
(`C:\Users\ivan_\AppData\Local\Temp\msg-spike\mini_cfb.py`, ~250 lines) may still exist: **read it as evidence only**, it
was a spike and is not the deliverable; this writer is typed fresh from MS-CFB.

## Four decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. `msg_outlook_layout_handbuilt` is built in this turn.** The sources disagree on its turn (the fixtures table says
1b.3, the build spec says 1b.9) but the binding document is the declaration block, which names
`test_the_outlook_layout_fixture_is_typed_from_b1_b4` in **1b.2**, and `test_turn_declarations.py` enforces declarations.
Build it here, update the "turn" column in `phase1b-fixtures.md` to 1b.2, and note the three-way disagreement.

**D2. `fixtures/msg/` must not enter the `.eml` corpus.** Verified in the code: `tools/behavior_ledger.py` builds its corpus
as `root.rglob("*.eml")` and runs `EmlContainer`/`walk` over it, so a `.msg` is not at risk (wrong suffix) but the later
`pair_gmail_reply.eml` (1b.9) would be; and `emailextract/evals/labels.py` loads **every** `*.expected.json` under
`fixtures/` with `rglob`. Therefore: (a) do **not** edit `tests/ledger/corpus.json` or append a corpus version in this
turn (the three new ledger components do not exist yet; their `.msg` corpus is defined in 1b.3 to 1b.10); (b) before
writing any sidecar, find out what the Phase 1 oracle (`labels`, `l1`, `gates`, the accounting and gap gates, the metrics
CLI, `check_ground_truth.py`) does with a sidecar that has no `.eml` next to it and with fact ids it has no measurer for;
(c) make the sidecars satisfy whatever that is **without editing `emailextract/evals/**`** (that is 1b.10's file set). If
the only way to keep the Phase 1 gates green is to edit `emailextract/evals/**`, **stop** and report the exact failing
gate and the smallest edit that would fix it; do not edit it and do not weaken a gate.

**D3. The sidecars carry only what a hand can type from the construction table now.** `labels_provenance: "spec"`,
`container.sha256`, `container.size_bytes`, `msg.container_layout` and `msg.sector_accounting` (shapes in
`phase1b-facts.md`; the eight classes sum to the file length). No `headers.*`, `part.*`, `decode.chain` or `body.*` fact
is typed in this turn: those need the reader (1b.5), and typing them early is exactly the "label pasted from the code"
failure rule 5 forbids. Later turns extend the sidecars additively, in the same commit as the fixture change.

**D4. The `olefile` rows of the licence audit flip in this turn.** `olefile` becomes a **`[dev]` extra** (O4), never a
runtime dependency. That moves the existing pinned tests listed under "Existing tests that change" below.

## What to build

### A. `tools/cfb_writer.py` (stdlib only; imports no `emailextract` module and no `olefile`)

A pure function `build_cfb(tree, *, version=3, ...) -> bytes` over a hand-typed description of a storage tree:
storages and streams by name, stream bytes, optional explicit sector ordering where a fixture needs a specific layout.
Requirements, each of which is a test:
* **Valid MS-CFB**, versions 3 (512-byte sectors, shift 9) and 4 (4096-byte sectors, shift 12; the header sector is 4096
  bytes with the 512-byte header zero-padded; the directory-sector-count field is set for v4). Header, DIFAT (the 109
  inline entries; the extended chain is **not** needed here, it is 1b.3's `msg_difat_extended`), FAT, miniFAT and the
  mini stream (streams **smaller than** the 4096 mini-cutoff live in the mini stream; the boundary is the point of the
  trio), and the directory with a **correct red-black tree** (siblings ordered by name length then case-insensitive
  code-point comparison; node colours valid; document in a comment how the tree is shaped for n entries). Unused
  sectors are explicit `FREESECT` and slack is explicit (the eight-class accounting must close).
* **Deterministic and clock-free**: zero timestamps and CLSIDs, no randomness, no dict-order dependence; the same input is
  byte-identical on 3.11 and 3.14 and on any platform (write with explicit little-endian `struct`, binary mode).
* **It can describe a layout, not only a message.** The Outlook-layout fixture needs the writer to emit exactly the
  property-stream header sizes and stream names of B1-B4; give the caller a way to supply raw stream bytes (a
  `__properties_version1.0` is just bytes to the writer). The writer never "knows" MAPI.
* A module docstring stating what it deliberately does **not** produce (hostile files, extended DIFAT) and that the
  hostile mutants of 1b.3 are hand-written byte literals frozen in `SHA256SUMS`, not writer output.

### B. `tools/make_msg_fixtures.py` and `fixtures/msg/`

Generator with `--check` (exit 1 if committed bytes moved) in the style of `make_fixtures.py`, and
`fixtures/msg/SHA256SUMS` freezing every output. Fixtures (hand-typed construction tables in
`docs/design/phase1b-fixtures.md`, one per fixture: storages, stream names and sizes, property tags and types, code pages,
sector size, mini-cutoff, the expected FAT chains and file length, **typed before looking at any output**):
* `msg_headers_only`: a minimal `.msg` with `__properties_version1.0` and `__substg1.0_007D001F` and no body stream.
* `msg_headers_html`: the same plus a `__substg1.0_10130102` HTML body (the 10-of-11 real shape).
* `msg_v4_sectors`: version 4, 4096-byte sectors.
* `msg_mini_cutoff_boundary`: three streams of exactly 4095, 4096 and 4097 bytes (4095 in the mini stream, 4096 and 4097
  in the FAT; assert the boundary with hand-typed chain lists).
* `msg_outlook_layout_handbuilt` (D1): typed from `phase1b-fixtures.md`'s construction table and B1-B4, **not from the
  writer's defaults**: the 32-byte top-level property header with the recipient/attachment counts at `@16`/`@20`,
  `__nameid_version1.0` with its three binary streams (160, 440, 3090 bytes), the `001F` transport-header stream, the
  `0102` HTML body, one recipient and one by-value attachment storage, `0x3FDE`/`0x3FFD` as **fixed entries in the
  property table, not streams**. Document it in the file's table as hand-built to the observed structure, not
  real-Outlook provenance.
Synthetic content only: no real or employer mail, no text from a real message. Real `.msg` never enters the repo and
`fixtures/real/` stays empty. Build-spec rule 1 says a listing check asserts that; **verify one exists** (I did not), and
if none does, add one in `tests/test_msg_fixtures.py` rather than relying on policy.

### C. `tests/support/olefile_oracle.py` (tests-only; the only place `olefile` is imported)

`compare(file_bytes, expectation) -> list[str]` returns the disagreements between `olefile`'s reading and the hand-typed
construction table (stream names and sizes, directory shape, sector size and version, mini-cutoff behaviour). Scope is
**well-formed fixtures only**: `olefile` is silent on a cyclic FAT chain and clamps a `2**40` size to 0 (1b.0b, E1), so it
cannot judge hostile files. `olefile` is imported nowhere under `emailextract/` or `tools/cfb_writer.py`.

### D. Packaging and legal

`pyproject.toml`: `dev = ["pytest>=8", "olefile>=0.47,<1"]` (BSD-3-Clause; the 1b.0b spike used 0.47). `NOTICE`: the olefile
row changes from "the future .msg reader" to what it now is (a test-and-tools dev dependency, never imported by the
library). No runtime dependency is added; `docextract-core` stays the only one.

### E. Existing tests that change in this turn (and only these)

`tests/test_licence_audit.py`: `test_olefile_is_not_a_declared_dependency` flips to "olefile is declared, under `[dev]`
only, never under runtime `dependencies`"; `NOTICE_ONLY` shrinks to `{}`; `AUDITED_LICENCES["olefile"]` stays
`BSD 3-Clause` (the file is not in the ledger allow-list; add it). `tests/test_container.py::
test_the_fake_container_is_a_second_container_kind_without_cfb_code`: it asserts `"olefile" not in sys.modules` in-process,
which becomes order-dependent the moment another test imports the oracle; rework it as a **fresh-subprocess** check that
`import emailextract` loads no `olefile` (the real guard). `tests/test_fixture_census.py`: extend to the `.msg` Family D
rows built this turn. `tests/test_turn_declarations.py`: declare the new tests and add `1b.2` to `BUILT_TURNS`. Anything
else that fails is a finding: report it, do not edit it to pass.

## Tests (the declared nine, exactly these names)

`test_msg_fixtures.py`: `test_the_writer_output_is_frozen_by_sha256` (every fixture equals `SHA256SUMS`, and `--check`
exits 0); `test_every_fixture_matches_its_construction_table` (the hand-typed table is a Python/JSON literal in
`tests/support/`, not prose, and the test checks raw bytes at hand-typed offsets: header signature, version, sector shift,
mini-cutoff, FAT/miniFAT/directory sector counts, the directory entries' names and sizes, and that the eight sector classes
sum to the file length); `test_the_v4_file_uses_4096_byte_sectors`; `test_the_mini_cutoff_trio_is_4095_4096_4097` (which
side of the cutoff each lands on); `test_the_outlook_layout_fixture_is_typed_from_b1_b4` (every number in it traces to a
B1-B4 row: assert against the spike tables' values, not against the writer); `test_the_writer_imports_no_reader_and_no_olefile`
(AST scan of `tools/cfb_writer.py` plus a fresh-subprocess import with `emailextract` and `olefile` blocked).
`test_olefile_oracle.py`: `test_olefile_agrees_on_every_well_formed_fixture`; `test_the_oracle_scope_excludes_hostile_mutants`
(build two mutants in the test by patching hand-typed offsets of a well-formed fixture: a cyclic FAT chain and a `2**40`
size; show the oracle is not asked to judge them, and say why in the assertion message);
`test_the_oracle_records_where_it_is_lenient` (assert and document the two E1 leniencies so a future `olefile` that changes
them is noticed).

Add, beyond the declared nine, the checks that make this turn honest: a **mutation** for each of (1) writing the miniFAT
cutoff comparison as `<=` instead of `<`, (2) a wrong directory-tree colour, (3) an off-by-one in a FAT chain; each must
make the construction-table test **and** the oracle test fail (run them, report that they failed). And a **determinism**
test: build every fixture twice under two `PYTHONHASHSEED` values and on both interpreters, byte-identical.

## Allow-list

`tools/cfb_writer.py`, `tools/make_msg_fixtures.py`, `fixtures/msg/` (new), `tests/support/olefile_oracle.py`,
`tests/support/` (the hand-typed construction-table literals), `tests/test_msg_fixtures.py`, `tests/test_olefile_oracle.py`,
`tests/test_licence_audit.py`, `tests/test_container.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`tests/ledger/label_ledger.json` (via `tools/update_label_ledger.py`; the new sidecars and `olefile_oracle.py`),
`pyproject.toml`, `NOTICE`, `docs/design/phase1b-fixtures.md` (construction tables and the turn column),
`docs/design/phase1b-ledgers.md` (this turn's outcome note). **Not** `emailextract/**` (including `evals/`), `tests/ledger/
corpus.json`, `tests/ledger/behavior_ledger.json`, any existing fixture or sidecar, `CLAUDE.md`.

## What must NOT be done

No library module and no `cfb.py`/`mapi.py`/`msgcontainer.py`. No `olefile` import in `emailextract/` or in the writer. No
reader-derived value in any sidecar or construction table: every number is typed from MS-CFB, B1-B4 or the construction
table, never pasted from running the writer or the oracle (if the writer and the table disagree, the disagreement is the
finding; do not edit the table to match). No change to a measured `.eml` value: the golden, the behavior ledger and the
Phase 1 gates stay green and untouched. No hostile fixtures yet (1b.3). Do not commit.

## Checks and report

1. `python -m pytest` green (full suite) on 3.14 and the repo's 3.11 (with `docextract_core` installed, not shimmed;
   `olefile` installed in the dev environment for this turn).
2. `python tools/make_msg_fixtures.py --check`, `tools/update_eml_golden.py --check`, `tools/update_behavior_ledger.py
   --check`, `tools/update_label_ledger.py --check`, `tools/make_fixtures.py --check` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1 to D4 and whether you changed any; what the Phase 1
   oracle does with the new sidecars (the D2 finding, with evidence); the three mutation results; every disagreement
   between writer, table and `olefile` you found and how it resolved; the exact set of existing tests edited and why.
4. What 1b.3 needs from this turn: the writer's API, how a hostile byte literal is added and frozen, and where the
   `msg_difat_extended` fixture (which needs the extended DIFAT chain the writer does not emit) should come from.

Stop at the turn boundary: the writer output is frozen and the oracle test is green. Do not start 1b.3.
