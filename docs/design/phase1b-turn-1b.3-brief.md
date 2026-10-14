# Turn 1b.3: `cfb.py`, the caps, sector classification, the hostile set and the seeded fuzz

Status: brief for one build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `ca48278` (Turn 1b.2
committed: the writer, five fixtures, the `olefile` oracle). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh
session. Keep tool calls small. **Do not commit.**

This is the first turn that adds **library code for `.msg`**: `emailextract/cfb.py`, the package's own CFB reader. It does
not read MAPI (1b.4) and it is **not wired into `parse.py`, `container.py` or `walk.py`** (1b.5): after this turn
`parse()` still refuses CFB exactly as it does now. What this turn proves is that the reader is *total* (never raises,
never hangs, never allocates from a lie) and *accounted* (every byte of every file is classified), against the writer's
fixtures, `olefile` and a hostile set. Rule 3 of the build spec is again the reason for the checks: the reader's author
also wrote the writer, so agreement between them proves little; the independent breakers are `olefile` (well-formed files),
hand-patched hostile byte literals, and the typed expectations.

Read first: `phase1b-build-spec.md` (rules 2-5; "Further decisions" items 1-3; the 1b.3 row; "The independent checks"),
`msg-architecture.md` (E1, E2, E3 and their numbers; open point 6 on `FATSECT`/`DIFSECT` markers), `phase1b-contract.md`
(section 1Y and its D1 correction on cap homes; the `container_facts` table, rows marked 1b.3), `phase1b-facts.md`
(`msg.container_layout`, `msg.sector_accounting`, `msg.stream_faults`), `phase0-gaps.md` (`msg.cfb_difat_extended`,
`msg.stream_truncated`), `phase1b-ledgers.md` (the `declaration turn=1b.3` block and the 1b.2 outcome note, especially
"What Turn 1b.3 needs from this turn"), MS-CFB (public; cite section numbers in comments, never copy `olefile`'s code), and
the layout of `tools/cfb_writer.py`, `tests/support/cfb_raw.py`, `tests/support/olefile_oracle.py`. The 1b.0b spike
(`C:\Users\ivan_\AppData\Local\Temp\msg-spike\cfbproto.py`, 361 lines, and `e123_run.py`) may still exist: **read it as
evidence of the E2/E3 numbers only**; `cfb.py` is typed fresh from MS-CFB and the contract below.

## Reviewer decisions (the owner may overrule; say so with evidence rather than building around one)

**D1. Where the caps live and what they default to.** `Limits` must not move (`limits_fingerprint` is part of
`document_key`; the `.eml` golden is the proof). So `cfb.py` defines a frozen `CfbLimits(max_sector_count,
max_directory_entries, max_difat_chain_length)` and `DEFAULT_CFB_LIMITS`. Defaults, derived in the module docstring with
the arithmetic: `max_sector_count = 1_048_576` (512 MiB of 512-byte sectors, comfortably above the 64 MiB input gate, so
the cap is a guard against a lying header, not a second size gate), `max_directory_entries = 65_536` (an 8 MiB directory;
the eleven real files have a few hundred), `max_difat_chain_length = 256` (a chain that long addresses over four million
sectors, far past the sector cap). `cfb.py` is a **leaf**: it imports only the stdlib and **not** `walk`/`model`. It
reports cap hits by the three string ids `sector_count_cap`, `directory_entries_cap`, `difat_chain_length_cap`, and a test
pins that these equal `walk.CFB_CAP_REASONS` (already present from 1b.1). Building `CapRecord`s is 1b.5's job; here a cap hit
is an observation carrying the caller's value and the **real observed count**.

**D2. No `.msg` sidecars again.** `emailextract/evals/labels.py` still accepts only `.eml` (`FIXTURE_SUFFIXES`), and
`evals/**` is still 1b.10's file set. So the new hostile fixtures are committed **without** `.expected.json`, exactly like
the five from 1b.2, and their expected behaviour is a hand-typed literal in `tests/support/msg_construction.py`
(`HOSTILE_EXPECTATIONS`), typed from MS-CFB and the E2 table before `cfb.py` runs. Do not edit `emailextract/evals/**`.

**D3. `msg_difat_extended` must not be a 7 MB file.** A naive file that needs more than 109 FAT sectors is ~7.1 MB at 512-byte
sectors. Do not commit that. Find the **smallest legal construction**: a header declaring 110 FAT sectors whose FAT sectors
are mostly `FREESECT` entries (the FAT may describe sectors past the end of the file), the 110th FAT sector's id held in
one real extended-DIFAT sector (127 FAT ids + the next pointer, chain ends with `ENDOFCHAIN`). Target under 100 KB. Build
it as a hand-patched byte literal (or a clearly separate builder in `tests/support/`; **do not** extend
`tools/cfb_writer.py`, whose docstring says it never emits an extended DIFAT) and require `olefile` to read it with zero
`parsing_issues` via the oracle. If no small legal form exists, **stop and report** what you tried; do not commit a multi-MB
file and do not weaken the fixture.

**D4. `cfb.py` returns, it does not raise.** There is no exception on any input. The whole-file result is a closed union:
`open_cfb(data, limits=DEFAULT_CFB_LIMITS)` returns either a `CfbFile` or a `CfbRefusal` whose `reason` is one of exactly
`cfb_header_unsupported`, `cfb_directory_loop`, `not_a_message` (CFB magic but no top-level `__properties_version1.0`), or
one of the three cap ids. Per-stream faults come back from `read_stream` as `(bytes, fault)`. Mapping a refusal to a
`NamedError`/`ParseResult` is 1b.5; this turn only fixes the vocabulary and pins it against `parse.NAMED_ERROR_REASONS`
(the two named reasons must be members; `not_a_message` is already one).

## What to build

### A. `emailextract/cfb.py` (stdlib only; ~350-450 lines, three frozen dataclasses)

Ten functions, signatures yours to design but each must satisfy its row; the names are fixed because the declaration block
cites them:

| function | contract |
|---|---|
| `parse_header` | the 512-byte header: signature, version, byte order, sector shift (v3: one of 9, 10, 11, 12; v4: exactly 12), mini shift, FAT/directory/miniFAT/DIFAT counts and starts, mini cutoff. Anything else is `cfb_header_unsupported`. v4: the header sector is 4096 bytes. |
| `walk_difat` | the 109 inline entries, then the extended chain, **bounded** by `max_difat_chain_length`, with a visited set; a chain longer than the cap is `difat_chain_length_cap`; a repeated or out-of-range DIFAT sector is a **broken chain**, which is a fault, not a crash. Returns the FAT sector ids and whether an extended chain was present (the observation behind `msg.cfb_difat_extended`; owner decision O1: read through, fault only on a broken chain). |
| `read_fat`, `read_minifat` | the two tables as tuples of ints; a FAT sector past the end of the file is an out-of-range **entry**, not an exception. |
| `walk_directory` | the directory chain with a visited set (`cfb_directory_loop` on a revisited sector), then every entry; the red-black links are walked with a visited set too (a link back into the tree, a self-reference, or a duplicate root is `cfb_directory_loop`). Entry names decode from UTF-16LE with the declared length; a bad length is a recorded entry fault, not an exception. |
| `lookup_entry` | case-insensitive by [MS-CFB] 2.6.4 (uppercase compare, length first), by posix path; `None` when absent. |
| `chain_sectors` | a bounded, visited-set chain walk yielding sector ids and a closed fault `OK / CYCLE / OUT_OF_RANGE`; the step bound is `4 * total_sectors + 16` (E2's declared bound). |
| `read_stream` | `(bytes, fault)` with `fault in {OK, CYCLE, OUT_OF_RANGE, SHORT_CHAIN}`, **for both stream kinds** (a stream under `mini_cutoff` is addressed through the miniFAT inside the mini stream; the boundary is `size < cutoff`). **Never raises, never hangs, and never allocates from the declared size**: the result is at most the bytes the chain actually holds, so a `2**40` or `0xFFFFFFFF` size on a one-sector chain returns that one sector's bytes plus `SHORT_CHAIN`. The declared length is never fabricated. |
| `classify_sectors` | every sector of the file gets exactly one of the **eight** classes `header, difat, fat, minifat, directory, stream, free, slack` (the root entry's mini-stream chain counts as `stream`), plus an explicit `unaccounted` count that is **0 on every well-formed file** and non-zero, never absorbed, on a cyclic chain or a directory loop. It keys on the header-declared FAT/miniFAT/DIFAT ranges and the entries' chains, **not** on `FATSECT`/`DIFSECT` markers (`msg-architecture.md`, point 6). A partial tail sector is `slack`, so the byte sum equals the file length (`phase1b-facts.md`, the truncated-file note: if a real mutant shows this is false, report it, do not paper over it). |
| `check_caps` | the three cap observations (`cap_id`, caller's value, real observed count), evaluated **before** the structure they guard is allocated or walked (the sector count before the FAT is read, the directory entry count before entries are parsed, the DIFAT length as the chain is walked). Use `>` against the cap, and pin both sides of the boundary in a test. |

Also expose `msg.container_layout`'s six values from the opened file (`cfb_version`, `sector_size`, `mini_sector_size`,
`mini_cutoff`, `sector_count`, `directory_entries`) and the per-stream fault list shaped like `msg.stream_faults`
(`[stream, fault, reason]`, with `cycle -> declared_length_mismatch`, `out_of_range`/`short_chain -> stream_ended_early`), so
1b.5 projects rather than recomputes. The module docstring states the fault contract, the cap defaults with their
arithmetic, and what it deliberately does not do (no MAPI, no wiring, no `olefile`).

**The work-per-byte budget.** Count work in steps (chain steps, DIFAT steps, directory-entry visits, table-entry reads), never
wall clock. **State the bound in the docstring before you run the fuzz**: total steps for `open_cfb` plus a full read of every
stream is at most `K * sector_count + C`, with `K` and `C` chosen from the structure (E2 observed 103 steps on a 50-sector
file against a per-stream bound of 216). Then show the measured maximum over every fixture and every fuzz mutant is under it.
A bound you choose after seeing the numbers is not a bound; if you must revise it, say so in the outcome note and why.

### B. The hostile and large fixtures

Committed byte literals, built by patching hand-typed offsets of a writer output (`tests/support/cfb_raw.patch_u32` is the
model), generated by `tools/make_msg_fixtures.py`, frozen in `fixtures/msg/SHA256SUMS`, with a construction/expectation row
each in `tests/support/msg_construction.py` typed **before** `cfb.py` runs:

* `msg_difat_extended` (D3).
* `msg_fat_cycle`: one stream's FAT chain points back into itself. Expected: that stream is `CYCLE`, every other stream
  reads `OK`, the file opens, `unaccounted > 0` in `classify_sectors`.
* `msg_directory_loop`: a directory red-black link points into a cycle. Expected: `CfbRefusal(cfb_directory_loop)`.
* `msg_truncated_stream`: the declared size of one stream exceeds its chain (the `SHORT_CHAIN` case), other streams intact.

Test-only seeds (built in the test from a fixture, **not committed**, named as in `phase1b-fixtures.md`):
`seed_size_lie_2pow40`, `seed_size_lie_ffffffff`, `seed_root_self_reference`; plus the two bad-header mutants (a sector shift
of 13; a v4 header with shift 9) and a file cut mid-sector (the `slack` case) and one cut at 1200 bytes (E1's
`mutant_truncated_1200`). A CFB with no `__properties_version1.0` (build it with the writer in the test) is the
`not_a_message` case. The 1b.0b spike's 14 inputs are the **regression set**: for each, the outcome class must equal the E2
table's (`msg-architecture.md`, E2 result); report the 14 results beside the table.

### C. `tests/support/olefile_oracle.py`

Add a cross-check **between `cfb.py` and `olefile`** on every well-formed fixture (all five from 1b.2 plus
`msg_difat_extended`): the same stream and storage names, the same size and **bytes** per stream, the same directory shape.
Where `olefile` is lenient and `cfb.py` strict, or the reverse, **record the case**; do not hide it and do not make
`cfb.py` agree with `olefile`'s clamping (E1: it reads a cyclic chain as a clamped stream with no signal). The oracle never
judges a hostile file.

### D. Packaging

No dependency changes. `emailextract/versions.py` is on the allow-list **only if** a pinned test forces a version constant; the
default is **do not touch it**. If you do, it must not move any `.eml` value, and the golden must stay byte-identical.

## Tests (the declared seventeen, exactly these names, plus the extras below)

`tests/test_cfb.py`: `test_parse_header_reads_v3_and_v4`, `test_walk_difat_and_read_fat`,
`test_read_minifat_and_the_cutoff` (4095 / 4096 / 4097 on the committed trio, each on the side the construction table says),
`test_walk_directory_and_case_insensitive_lookup`, `test_read_stream_returns_bytes_and_fault`,
`test_read_stream_never_raises` (every fixture, every seed, every cut length of one fixture from 0 to its size),
`test_classify_sectors_assigns_every_sector`, `test_check_caps_reports_the_three_cfb_caps` (both sides of each boundary).
`tests/test_cfb_hostile.py`: `test_a_fat_cycle_is_one_streams_fault`, `test_a_directory_loop_is_a_named_error`,
`test_an_unsupported_header_is_a_named_error`, `test_magic_without_properties_is_not_a_message`,
`test_the_extended_difat_is_read_through_and_flagged`. `tests/test_cfb_fuzz.py`:
`test_every_mutant_returns_a_closed_failure_or_the_same_document`, `test_the_work_per_byte_budget_holds`.
`tests/test_sector_accounting.py`: `test_the_eight_classes_sum_to_the_file_length`, `test_free_and_slack_are_explicit`,
`test_a_cyclic_chain_is_visible_as_unaccounted`.

**The seeded fuzz.** Deterministic: `random.Random(seed)` over a fixed, committed list of seeds (at least 300 mutants per base
fixture over at least three bases: the v3 headers file, the v4 file and the mini-cutoff trio), no clock, no `os.urandom`.
Mutation operators, at minimum: overwrite a FAT entry, a miniFAT entry, a directory link, a directory entry's start sector
and size, a header count, a header sector shift, and truncate the file. Every mutant must produce exactly one of: a
`CfbRefusal` with a closed reason, an opened file whose streams each return `(bytes, fault)`, or the same document as the
unmutated base. Any other outcome, any exception, and `MemoryError`/`RecursionError` specifically, fails **with the seed and
operator in the message**. The sector sum and the budget are asserted on every mutant, not only on the fixtures.

Beyond the declared seventeen, add the checks that make this turn honest:

* **Writer-independent expectations.** `HOSTILE_EXPECTATIONS` and the existing construction tables are what `cfb.py` is
  compared to; nothing is read back from `cfb.py` and pasted into a table. If `cfb.py` and a table disagree, the
  disagreement is the finding; do not edit the table to match.
* **The `olefile` cross-check** (C) as a test over every well-formed fixture.
* **A parity test** that `cfb.py`'s cap ids equal `walk.CFB_CAP_REASONS`, that its refusal reasons are members of
  `parse.NAMED_ERROR_REASONS` or the cap vocabulary, and that `import emailextract.cfb` in a fresh interpreter loads no
  `olefile`, no `walk`, no `model` and no `parse`.
* **Three mutations**, each must make a named test fail (run them, restore, report the failing test names): (1) remove the
  visited-set check in `chain_sectors`; (2) write a cap check `>=` instead of `>`; (3) have `classify_sectors` count the
  mini-stream's sectors as `free`.
* **Determinism**: every number the tests assert is identical under two `PYTHONHASHSEED` values and on both interpreters.

## Allow-list

The ledger's block for `turn=1b.3` (`emailextract/cfb.py`, `emailextract/versions.py`, `fixtures/msg/`, `tests/test_cfb.py`,
`tests/test_cfb_hostile.py`, `tests/test_cfb_fuzz.py`, `tests/test_sector_accounting.py`,
`tests/support/olefile_oracle.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`) **plus these named
additions, which the reviewer adds in this brief and which you must also write into the ledger's allow-list line in the same
turn**: `tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`, `tests/support/cfb_raw.py`,
`tests/test_msg_fixtures.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`. **Not**: `tools/cfb_writer.py`,
`emailextract/walk.py`, `model.py`, `parse.py`, `container.py`, `assemble.py`, `emailextract/evals/**`,
`tests/ledger/corpus.json`, `tests/ledger/behavior_ledger.json`, the golden, any existing fixture, `CLAUDE.md`.

## What must NOT be done

No `mapi.py`, no `msgcontainer.py`, no wiring into `parse()`/`ingest`/`walk`. No `olefile` import under `emailextract/`. No
exception from `cfb.py` on any input. No allocation sized from a declared length. No wall-clock assertion. No edit to the
writer, to `Limits`, or to any `.eml` value; the golden, the behavior ledger and every Phase 1 gate stay green and untouched.
No real or employer message in any fixture. No multi-megabyte fixture. No `.msg` sidecar (D2). Do not commit.

## Checks and report

1. `python -m pytest` green (full suite) on 3.14 and the repo's 3.11, with `docextract_core` installed (editable) and
   `olefile` installed. Run the suite serially or with generous timeouts; the 1b.2 run saw a CPU-contention flake in
   `tests/test_addresses.py::test_the_tokenizer_is_linear_in_the_input` while other agents ran, which is not this turn's.
2. `python tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1 to D4 and whether you changed any, with evidence; the
   declared work bound and the measured maximum; the 14 regression inputs beside the E2 table; the three mutation results
   (the failing test names); every disagreement between `cfb.py`, the typed tables and `olefile` and how it resolved; any
   case where `classify_sectors` could not close the sum; the size of `msg_difat_extended` and how it was built; the exact
   set of existing tests edited and why.
4. What 1b.4 and 1b.5 need from this turn: `cfb.py`'s public API, how `CfbRefusal` maps to `NamedError`, how a stream fault
   maps to `Status.TRUNCATED`, and where the `msg.cfb_difat_extended` observation is exposed.

Stop at the turn boundary: the hostile set and the seeded fuzz are green and the outcome note is written. Do not start 1b.4.
