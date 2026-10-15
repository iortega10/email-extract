# Turn 1b.0b: the architecture spike -- the eight experiments, the comparison and the probe

Status: spike record. Author: builder session (hearth), 2026-10-11. Builds on `c6728c0` (Turn 1b.0a committed).
Every input is hand-built synthetic bytes; every measurement carries its command and the sha256 of its output
(rule 5). The experiments import `emailextract` **read-only** from the repo and run in
`C:\Users\ivan_\AppData\Local\Temp\msg-spike`; no package file, test or fixture is touched by this turn.

## 0. Pre-registered criteria (written before any experiment ran; not changed after a result)

The pass/fail criterion and the deciding number of each experiment, as required by brief rule 4. A criterion that
turns out wrong is reported as such with the corrected one beside it (section 2).

| exp | pass criterion | the deciding number | budget / bound declared first |
|---|---|---|---|
| E1 | every case of the hostile set terminates within a **10 s** per-case wall-clock timeout in its own subprocess, and each maps to exactly one outcome class of `{raised, hung, clamped, silent, issue-recorded}`; for every case that opens, `ole.fat` / `ole.minifat` / `ole.direntries` are reachable so a per-sector classification is reconstructible | cases terminating = **all**; cases that hang = **0** | timeout 10 s/case |
| E2 | `read_stream(file_bytes, start, size, ...)` returns `(bytes, fault)` with `fault in {OK, CYCLE, OUT_OF_RANGE, SHORT_CHAIN}` and never raises or hangs; every input maps to exactly one outcome of the whole-file/per-stream vocabulary (`cfb_directory_loop`, `cfb_header_unsupported`, a per-stream fault, or clean); work is bounded by a declared per-input counter | inputs that raise or hang = **0**; inputs mapping to exactly one outcome = **all** | chain steps per `read_stream` call <= `4 * total_sectors + 16`; whole-file validation <= one pass over header + directory sectors |
| E3 | the **eight** sector classes (header, DIFAT, FAT, miniFAT, directory, stream, free, slack) sum to the file length on every well-formed fixture; a cyclic chain is visible as an explicit unaccounted or double-claimed range | `abs(sum(8) - file_length)` = **0** on all well-formed fixtures; `unaccounted + double_claimed` > **0** on the cyclic mutant | -- |
| E4 | a 40 MiB attachment stream, projected pass-through, has peak RSS delta under the declared budget; one extra copy max | peak RSS delta <= **3 x 40 MiB = 120 MiB** (pass-through) | 3 x stream size above baseline, pass-through |
| E5 | at two framing lengths the kind-gated `part_id`/`parent_part_id` are identical and the `WalkResult` matches modulo provenance fields; the `.eml` ids are byte-identical to the committed corpus | differing `part_id`s: unmodified **> 0** (the finding), kind-gated **= 0**; differing `.eml` part_ids **= 0** | -- |
| E6 | `raw_value` and `text_decodes` equal the hand-typed expected text for every case; the default codec path on the `.eml` corpus is byte-identical; a trailing NUL, a UTF-8 BOM, LF-only endings and an odd-length UTF-16 stream are each handled without raising | wrong cases **= 0**; `.eml` fields differing from default **= 0**; edge cases raising **= 0 of 4** | -- |
| E7 | every `.msg` leaf is `part_level` / `container_stream` with no offset map and never `exact`; `resolve_span` for a span-table container returns a stream span or `Unresolvable`, never a virtual offset | leaves not `part_level`/`container_stream` **= 0**; unmodified leaves returning `exact` **> 0** (the finding) | -- |
| E8 | re-ingest is byte-identical; persisted bytes hold no `virtual_offset`/`virtual_len`; the `.eml` artifact bytes are untouched; the persisted source-only table recomputes the virtual offsets deterministically | re-ingest identical = **yes**; `virtual_*` tokens persisted **= 0**; `.eml` artifact byte diffs **= 0**; recomputation equals the hand-written rows | -- |
| compare | `walk(msg-virtual)` vs `walk(EmlContainer(equivalent synthetic .eml))` show no difference in tiling, ordering, part count, header fields or decode chains, modulo the provenance fields | differing fields **= 0** | -- |

**Re-opening trigger (contract section 8).** If the comparison forces an edit to tiling or ordering inside
`_walk_visit`, A'' is re-opened (named fallback: a `MsgContainer` that builds `PartShape` itself, ~200 duplicated
lines).

## 1. Environment

- Interpreter: `Python 3.14.3 (tags/v3.14.3:323c59a, Feb 3 2026)` on `Windows-11-10.0.26200-SP0` (the primary
  interpreter; `python -VV`).
- `olefile`: **scratch only**, `python -m pip install --target C:\Users\ivan_\AppData\Local\Temp\msg-spike\site olefile`
  -> **0.47**. Never added to `pyproject.toml` or the repo's environment.
- Scratch root: `C:\Users\ivan_\AppData\Local\Temp\msg-spike`; scripts `mini_cfb.py` (the hand-typed CFB writer,
  ~250 lines, **not** `tools/cfb_writer.py`), `msg_build.py`, `cfbproto.py`, `cases.py`, `harness.py`, `idents.py`,
  `headerseam.py`, `precision.py`, `storeprobe.py`, `compare.py`, `e4_mem.py`, `probe_fixtures.py`,
  `probe_evidence.py`; outputs under `out/`.
- Every command below ran from the scratch root with
  `PYTHONPATH='C:/Users/ivan_/AppData/Local/Temp/msg-spike;C:/Users/ivan_/App_repos/email-extract'`.
- `mini_cfb.py` hand-types the MS-CFB layout (header + DIFAT-in-header + FAT + miniFAT + a 128-byte directory with
  right-spine child chains + the mini stream); the **message** layout it builds follows `email-spike.md` B1-B4
  (`__properties_version1.0` 32/8-byte headers, `(tag<<16)|type` entries, `__substg1.0_<tag><type>` streams,
  `__recip_version1.0_#%08X` / `__attach_version1.0_#%08X`). `olefile` reads every well-formed output with no
  parsing issues (E1).

## 2. Per-experiment record

Each entry names the input, the command, the result, the sha256 of the output file, the verdict against the
pre-registered criterion, and the later turn whose test will re-run it. Every `file:line` cited below was opened.

### E1 -- `olefile` on the hostile set

- **Input (14 cases, `out/cases/`)**: one well-formed base; the six debate mutants (cyclic FAT chain, claimed size
  `2**40`, claimed size `0xFFFFFFFF`, start sector out of range, directory self-reference, truncated to 1200 bytes);
  a v4 (4096-byte-sector) file; the 4095/4096/4097 trio at the mini-stream cutoff; plus E2's two bad-header mutants
  and a directory-loop mutant.
- **Command**: `PYTHONPATH=... python e123_run.py` (each case is `python e1_case.py <path>` in its own subprocess,
  `subprocess.run(timeout=10)`).
- **Result** (`out/e123_report.txt`, **sha256
  `3b71d893246128bb09fe3c7b228488d4ef5f414719e1b10a8e4b8d6579b62ea8`**):

  ```
  mutant_bad_header_shift            raised           OleFileError: incomplete OLE sector
  mutant_bad_header_version          issue-recorded   OleFileError:incorrect DllVersion in OLE header  fat=yes direntries=yes
  mutant_directory_loop              issue-recorded   OleFileError:duplicate OLE root entry           fat=yes direntries=yes
  mutant_directory_self_reference    issue-recorded   OleFileError:double reference for OLE stream/storage  fat=yes direntries=yes
  mutant_fat_cycle                   clamped          chain repeats: __substg1.0_37010102             fat=yes direntries=yes
  mutant_size_2_40                   issue-recorded   OleFileError:incorrect OLE stream size          fat=yes direntries=yes
  mutant_size_ffffffff               issue-recorded   OleFileError:malformed OLE document, stream too large  fat=yes direntries=yes
  mutant_start_out_of_range          issue-recorded   OleFileError:incorrect OLE FAT, sector index out of range  fat=yes direntries=yes
  mutant_truncated_1200              raised           OleFileError: incomplete OLE sector
  trio_4095 / trio_4096 / trio_4097  silent           fat=yes direntries=yes
  v4_sector_4096                     silent           fat=yes direntries=yes
  wellformed_base                    silent           fat=yes direntries=yes
  terminated 14/14  hung 0
  ```

- **Verdict: PASS.** 14/14 terminate within 10 s; 0 hang; every case carries exactly one class; `ole.fat`,
  `ole.minifat` and `ole.direntries` are reachable on every case that opens, so a per-sector classification *is*
  reconstructible from the oracle. The pre-registered count was 11 (base + six mutants + v4 + trio); the built set is
  14 because E2's two bad-header mutants and the directory-loop mutant are also run through the oracle -- a
  refinement, not a re-bent criterion.

  **Two findings the owner should see.** (1) `olefile` **does not hang** on the cyclic FAT chain: `OleStream` reads
  with a fixed-length loop (`olefile.py:645,663`, `for i in range(nb_sectors)`), so a self-cycle is read by
  re-reading one sector `nb_sectors` times and returns the declared length with **no signal** -- the E1 class
  `clamped`. A well-formed-input oracle therefore cannot be relied on to *detect* a cyclic chain; it silently
  clamps. (2) Each malformed case is a recorded `parsing_issue` or a raised `OleFileError`, never a hang, so the
  oracle's scope really is "well-formed inputs only" and the own reader's hostile-set behaviour (E2/E3) is the
  contract, not `olefile`'s.
- **Re-run by**: Turn 1b.2 (`tests/support/olefile_oracle.py` over every well-formed fixture) and Turn 1b.3 (the
  hostile set against `cfb.py`).

### E2 -- the `read_stream` fault contract

- **Input**: every E1 case plus the directory loop and the two bad headers (14 inputs).
- **Prototype** (`cfbproto.py`): `parse_header` -> `cfb_header_unsupported` outside v3 shift `{9,10,11,12}` / v4
  shift `!= 12`; `directory_sectors` -> `cfb_directory_loop` on a revisited directory sector; `storage_tree_fault`
  -> `cfb_directory_loop` on a revisited directory entry; `read_stream(data, hdr, fat, start, size, *, bound, minifat,
  ministream) -> (bytes, fault)` with `fault in {OK, CYCLE, OUT_OF_RANGE, SHORT_CHAIN}`; `diagnose` returns exactly
  one outcome. The declared bound is `4 * total_sectors + 16` chain steps per call; a step counter (`N_CHAIN_STEPS`)
  is printed per input.
- **Command**: `PYTHONPATH=... python e123_run.py`.
- **Result** (`out/e123_report.txt`, **sha256 `3b71d893…`**):

  ```
  mutant_bad_header_shift            cfb_header_unsupported     chain_steps=0
  mutant_bad_header_version          cfb_header_unsupported     chain_steps=0
  mutant_directory_loop              cfb_directory_loop         chain_steps=0
  mutant_directory_self_reference    cfb_directory_loop         chain_steps=0
  mutant_fat_cycle                   CYCLE                      chain_steps=15
  mutant_size_2_40                   SHORT_CHAIN                chain_steps=30
  mutant_size_ffffffff               SHORT_CHAIN                chain_steps=30
  mutant_start_out_of_range          OUT_OF_RANGE               chain_steps=14
  mutant_truncated_1200              OUT_OF_RANGE               chain_steps=0
  trio_4095 / trio_4096 / trio_4097  clean                      chain_steps=86 / 22 / 23
  v4_sector_4096                     clean                      chain_steps=16
  wellformed_base                    clean                      chain_steps=103
  raised-or-hung 0/14  (want 0)
  ```

- **Verdict: PASS.** No input raises or hangs; every input maps to exactly one outcome; the maximum observed chain
  work (103 steps on the well-formed base) is far under the declared bound (`4 * 50 + 16 = 216`), and a cycle is
  caught by the bound/visited-set, never by hanging. The prototype's `read_stream` covers both tables (a stream under
  the 4096-byte cutoff is addressed through the miniFAT inside the mini stream), so one function states the fault
  contract for both stream kinds.
- **Re-run by**: Turn 1b.3 (`cfb.py`'s fault contract, the hostile set and seeded fuzz, the work-per-byte budget).

### E3 -- sector accounting

- **Input**: the five well-formed fixtures (`wellformed_base`, `v4_sector_4096`, the trio) plus the cyclic-chain and
  directory-loop mutants.
- **Command**: `PYTHONPATH=... python e123_run.py`.
- **Result** (`out/e123_report.txt`, **sha256 `3b71d893…`**): all five well-formed fixtures have
  `delta = sum(8 classes) - file_length = 0`:

  ```
  wellformed_base   sum=26112 file=26112 delta=0  {header:512, difat:0, fat:6656, minifat:512, directory:3072, stream:14336, free:1024, slack:0}
  v4_sector_4096    sum=32768 file=32768 delta=0  {header:4096, difat:0, fat:4096, minifat:4096, directory:4096, stream:16384, free:0, slack:0}
  trio_4095/6/7     delta=0  (three rows)
  mutant_fat_cycle  sum=8704  file=16384 delta=-7680 issues=['unaccounted']
  mutant_directory_loop sum=3584 file=4608 delta=-1024 issues=['unaccounted']
  ```

- **Verdict: PASS.** On every well-formed fixture the eight counts sum **exactly** to the file length (the `free`
  class is exercised by `n_free=2` in the base; `header` is one sector, so 4096 for the v4 file). On the cyclic-chain
  and directory-loop mutants the unreachable sectors show as an explicit **`unaccounted`** range (delta negative),
  never silently absorbed. (The pre-registration said "the seven classes"; the manifest is **eight** -- header,
  DIFAT, FAT, miniFAT, directory, stream, free, slack -- as the build spec lists it; corrected here, and the
  criterion below is written against eight.)
- **Re-run by**: Turn 1b.3 (sector classification and the no-silent-drop sum) and Turn 1b.5 (the projection).

### E4 -- large-attachment memory

- **Input**: a synthetic 40 MiB (`41943040`-byte) attachment stream, (a) pass-through (`CTE: binary`) and
  (b) re-encoded (`CTE: base64`), through `walk()` **and** `assemble()` with a `bytes`-valued `container.FakeContainer`.
- **Command**: `PYTHONPATH=... python e4_mem.py passthrough` and `... e4_mem.py reencoded` (one subprocess per case;
  peak RSS via the Windows `psapi` `GetProcessMemoryInfo` `PeakWorkingSetSize`/`WorkingSetSize`, `psutil` is not a
  dependency).
- **Result** (`out/e4_passthrough.txt` sha256
  `5f7118f135e24789073e38f92f5ce72a09938e1b3a3f399decbc2c888522483d`; `out/e4_reencoded.txt` sha256
  `ada9833f71ef3ccefb0afaf1eb276686d7e62e519c4373e8e6ace6adb48a3ae5`):

  ```
  passthrough  raw=41943167  baseline=26669056  after_raw=+83894272  after_walk=+125861888  peak_delta=167821312  delta/stream=4.0  budget=125829120  within_budget=false
  reencoded    raw=55924183  baseline=26701824  after_raw=+153804800 after_walk=+294580224 peak_delta=295587840  delta/stream=7.05 budget=125829120  within_budget=false
  ```

- **Verdict: FAIL (the criteria are not changed to fit).** Pass-through peak RSS delta is **167.8 MB = 4.0 x the
  stream** for a 40 MiB attachment, over the declared 3 x budget (125.8 MB). The staged peaks show why: the virtual
  string materialises once (`+84 MB` after `raw`), the walker copies the leaf payload (`+126 MB` after `walk`), and
  `assemble()` walks/copies it a second time (`+194 MB`). Re-encoded base64 is worse (7.05 x).

  **Finding (a constraint, not a re-open).** A `bytes`-valued `raw_bytes()` costs ~4x a pass-through attachment
  because both `walk()` and `assemble()` slice the leaf into a fresh `bytes`. Build spec section 7 says a lazy view
  "is out of scope unless experiment E4 shows it is needed"; **E4 shows it is needed**. The named fix is a lazy
  `raw_bytes()` view (a `container.py` `Container` protocol addition: e.g. a `memoryview`/window object with a
  `bytes()`-equivalent), to be added in Turn 1b.1 before the projection lands in 1b.5. The cost is bounded (the
  `Container` Protocol is `@runtime_checkable` and `EmlContainer`/`FakeContainer` both change) and it does not touch
  `_walk_visit`'s structure. Whether to accept the scope addition or re-declare the budget is the owner's call
  (section 7, Q1/Q5).
- **Re-run by**: Turn 1b.1 (the `container.py` view) and Turn 1b.5 (the projection and its memory).

### E5 -- identity determinism

- **Input**: one scratch `FakeMsgContainer` (a 3-part multipart projection with a fixed "CFB source" and a
  hand-written source-only span table) built at two framing lengths (the `X-Pad` header is 1 vs 8 bytes). The
  contract's `synthetic:<role>:<ordinal>` / `{stream, byte_off, byte_len}` + source-sha256 key is prototyped by
  **monkeypatching `walk.part_id`** (`ids.py:125`); `container_hash` is the hash of the *source* bytes, per D14
  (it addresses the file, not the projection).
- **Command**: `PYTHONPATH=... python idents.py`.
- **Result** (`out/idents.txt`, **sha256
  `fb5a10c490970097772f43a6f89ac78459f2e5c3ecbc461f9a1ae0e32dd955d5`**):

  ```
  unmodified differing part_ids = 3 (want > 0)     # the debate's finding, reproduced
  kind-gated differing part_ids = 0 (want 0)
  kind-gated differing PartRecords = 0 ; differing parent_part_ids = 0
  .eml default: gated == unmodified -> True (want True)
  citation, unmodified resolve_span -> RawSpan(offset=138, length=5, locator='1.1')   # a virtual offset
  citation, span-table source key   -> stream=S_text off=0 len=32
  ```

- **Verdict: PASS.** With the unmodified code the two framing lengths move **all three** `part_id`s (the finding);
  with the kind-gated `part_id` they are byte-identical, as are the `PartRecord` ids and `parent_part_id`s. The
  empty-table default branch leaves the committed `.eml` ids byte-identical (checked on
  `fixtures/generated/alternative_text_html.eml`). The citation confirms C2: unmodified `resolve_span` returns a span
  at **virtual** offset 138; the span-table path returns the **source** `S_text:0:32` and never the virtual offset.
- **Re-run by**: Turn 1b.1 (the C2 identity tests: two framing lengths -> identical ids; a mutated `.eml` path ->
  byte-identical `.eml` ids).

### E6 -- the 8-bit header seam

- **Input**: non-ASCII header text from a `001F` stream (UTF-16LE, trailing NUL) and a `001E` stream (cp1252 and
  UTF-8 cases), each projected to UTF-8. Expected `raw_value`/`text_decodes` were typed before running.
- **Prototype**: `header_fields_at_codec` in `headerseam.py` -- a copy of `walk.header_fields_at` (`walk.py:463-533`)
  with a pluggable decode at every `.decode("latin-1")` site, installed as `headers.header_fields_at` (a wrapper,
  **not** an edit; `headers.py:222` calls the module-global name).
- **Command**: `PYTHONPATH=... python headerseam.py`.
- **Result** (`out/headerseam.txt`, **sha256
  `ba07ab0a580d22ee12ba9055b042fa36cbcc6ac1a2b16550dad91d13bb8ac5cb`**):

  ```
  utf16      fields=[('Subject',' Café Zürich'),('X-Note',' naïve façade')]  expected=…  ok=True
  utf16      text_decodes=[' Café Zürich',' naïve façade']
  cp1252     fields=[('Subject',' Café'),('From',' x@y.example')]  ok=True
  utf8-8bit  fields=[('Subject',' Zürich'),('X-A',' é')]  ok=True
  edge trailing_nul: True   edge utf8_bom: True   edge lf_only: True   edge odd_utf16: True
  .eml default codec: 88 fixtures, differing = 0 (want 0)
  ```

- **Verdict: PASS.** Every case's `raw_value` and `text_decodes` match the hand-typed expected text; the four edge
  cases (one trailing NUL stripped, a UTF-8 BOM treated as the tolerated prelude, LF-only line endings, an odd-length
  UTF-16 stream truncated by one byte before decode) all run without raising; and the default `latin-1` path is
  byte-identical to the committed behaviour over all **88** committed `.eml` fixtures (name, `raw_value`, `name_span`,
  `value_span` compared). How each edge is handled: the odd-length stream is shortened to an even length *before* the
  scanner (it never arrives), the trailing UTF-16 NUL is stripped once, the BOM stays the walker's `headers.leading_bom`
  prelude, and a bare LF is already one line terminator in `walk._iter_lines`.
- **Re-run by**: Turn 1b.1 (the `value_codec` seam, `header_fields_at`/`header_region`) and Turn 1b.5 (headers from
  `0x007D`).

### E7 -- precision

- **Input**: a body already decoded to text, projected pass-through (a `text/html` `windows-1252` `binary` leaf) and
  re-encoded (a `text/plain` `utf-8` `8bit` leaf), run through `text.analyse_part` and, with the contract's
  precompute, through `analyse_part_cs(..., container_stream=True)`; plus `resolve_span` against a span-table
  container.
- **Prototype**: `precision.py` -- `analyse_part_cs` copies `text.analyse_part` (`text.py:506-559`) and sets
  `reason = "container_stream"` before the `if reason is None` offset-map build (contract section 8 point 4);
  `resolve_span_span_table` is the point-3 prototype.
- **Command**: `PYTHONPATH=... python precision.py`.
- **Result** (`out/precision.txt`, **sha256
  `9121e9621d2a7444ec3b08b393f04fae1c937cf0a292a199a9e58850f7137904`**):

  ```
  leaf 1.1: unmodified precision=exact reason=None; container_stream -> precision=part_level reason=container_stream offset_map=None ok=True
  leaf 1.2: unmodified precision=exact reason=None; container_stream -> precision=part_level reason=container_stream offset_map=None ok=True
  resolve_span, unmodified -> RawSpan(offset=138, length=5, locator='1.1')   (a virtual offset: the finding)
  resolve_span, span table -> SourceSpan(stream='S_text', byte_offset=0, byte_len=32)
  ```

- **Verdict: PASS.** Both `.msg` leaves come out `part_level`/`container_stream` with **no** offset map under the
  precompute, while the unmodified code claims `verbatim_precision = exact` against the virtual bytes for both (the
  finding A3 predicted). `resolve_span` returns the real source span (never an offset in the virtual framing) for a
  span-table container.
- **Re-run by**: Turn 1b.1 (the precision precompute) and Turn 1b.5 (the projected leaves end to end).

### E8 -- the store artifact

- **Input**: one scratch `FakeMsgContainer` document with the contract's **source-only** `PersistedSpanRow`
  (section 7) plus the eight-way CFB sector accounting from the well-formed base; stored through a core
  `Collection` (the same `docextract_core` substrate `store.py:170-178,273-281` uses).
- **Command**: `PYTHONPATH=... python storeprobe.py`.
- **Result** (`out/storeprobe.txt`, **sha256
  `fd724f42ecb9dd66d03ef3299c4db1864dd935daf83dbc82c23b5a6aa1a781b8`**):

  ```
  first ingest created=True  re-ingest created=False  byte-identical=True
  persisted virtual_offset/virtual_len tokens = 0 (want 0)
  recomputed rows = [('synthetic:multipart:1',0,262), ('S_text',62,91), ('S_bin',160,93)]
  original rows   = [('synthetic:multipart:1',0,262), ('S_text',62,91), ('S_bin',160,93)]
  recomputation reproduces the rows -> True
  .eml artifact: byte-identical across re-ingest -> True; virtual_* tokens = 0
  ```

- **Verdict: PASS.** Re-ingest is byte-identical (the core `Collection` is idempotent by key, `store.py:181-197`); the
  persisted bytes contain no `virtual_offset`/`virtual_len` (C2); the `.eml` artifact bytes are untouched across
  re-ingest; and re-projecting the source with the same `MSG_PROJECTION_VERSION` reproduces the persisted rows'
  virtual offsets exactly (the source-only table loses nothing).
- **Re-run by**: Turn 1b.1/1b.5 (the store artifact) and Turn 1b.10 (the `.eml` golden's byte-equality test).

## 3. The comparison

- **Input**: the E5/E7 virtual message served first by `FakeMsgContainer` (`container_kind=cfb_msg`) and then by
  `EmlContainer` (the same bytes, `container_kind=rfc822`); every structural field compared, modulo
  `container_kind`/`container_hash`/`container_facts` and `part_id` (container-addressed).
- **Command**: `PYTHONPATH=... python compare.py`.
- **Result** (`out/compare.txt`, **sha256
  `8be99250f2d72bfa75c32952606445ad40e0104d7ca432838c76939571aa976f`**): `parts 3, regions 8, total_bytes 262,
  differing fields = 0` -- nothing differs in tiling, ordering, part count, spans, header fields, decode chains,
  `encoding_source`, `body_sha256` or gaps.
- **Verdict: PASS.** No edit to tiling or ordering inside `_walk_visit` is forced, so the architecture is **not**
  re-opened by the comparison. The same walker measures a `.msg` projection and its `.eml` twin identically; only
  the provenance fields differ.
- **Re-run by**: Turn 1b.1 (the C5 cross-container test) and Turn 1b.9 (the durable cross-container pair / D14).

## 4. The probe script's evidence (`tools/msg_probe.py`)

`tools/msg_probe.py` implements the P1-P6 schema of `docs/design/phase1b-probes.md` exactly, extends
`tools/real_probe.py` (it keeps the `is_relative_to(REPO_ROOT)` refusal, `real_probe.py:254`, and adds the
`fixtures/` tree), and uses `olefile` as a **dev tool** only. Evidence is in the scratch dir; the script itself is
in the repo.

- **Sentinel test** (`PYTHONPATH=... python probe_evidence.py`; `out/probe_evidence.txt`, **sha256
  `ccd4306fdab898fad8ef2ff2e5173f1e4725edc32721d3e599f1dda540d06ae9`**): a synthetic `.msg` whose subject
  (`SENTINELSUBJECT`), sender (`SENTINELSENDER`), recipient (`SENTINELRECIP`), attachment filename
  (`SENTINELFILENAME`) and body (`SENTINELBODY`) are sentinels is placed in a 4-file directory; **all six probes**
  run over it; `sentinels leaked = 0`.
- **Instrumented reads** (same file): `olefile.OleFileIO.openstream` is wrapped to log every stream opened while all
  six probes run over the fixture dir. Result: three distinct `__properties_version1.0` tables, plus exactly two
  named property streams -- `__substg1.0_001A001F` (P1's class bucket) and `__substg1.0_10130102` (P6's
  literal-token counts) -- and **no** body or header stream (`0x1000`/`0x1009`/`0x007D`) is ever opened: `[]`.
- **Expected-output check** (`out/probe_expected.txt`, **sha256
  `31cf9ea834000592a3e203ea179f47c7787d98c0432ba8f75e633f71e1c88fa6`**): a three-file synthetic dir (f1 = an
  `IPM.Note` with HTML `divRplyFwdMsg`/`x_`, one method-1 attachment of 8214 B and one SMTP recipient; f2 = an
  `IPM.Note.SMIME` plain-only with four time tags, a method-5 attachment of 16384 B and one EX recipient; f3 = a v4
  `IPM.Appointment` with `appendonsend`). The hand-typed expected text and the observed text agree line for line:

  ```
  P1 ... class buckets: IPM.Note=1  IPM.Note.SMIME*=1  IPM.Note.Secure*=0  other=1
         body streams:  0x1000 present=1  0x1009 present=0  0x1013 present=2
         attachments:   method=1:1  method=2:0  method=3:0  method=4:0  method=5:1  method=6:0
         attachment sizes (bytes, sorted): 8214 16384
  P2 ... 0039: present=2  types=0040   0e06: present=2  types=0040
         3007: present=1  types=0040   3008: present=1  types=0040
  P3 ... version: 3=2 4=1   sector size: 512=2 4096=1   miniFAT used: 3/3
         difat length histogram: 1=3   (>1 = extended present: 0)
         directory entries histogram: 16=1  20=1  32=1
         stream size buckets: <4KiB=1  4KiB-1MiB=2  1-8MiB=0  >8MiB=0
  P4 ... attach tag:type union: 3701:0102 3705:0003 3707:001f
         recip  tag:type union: 0c15:0003 3002:001f 3003:001f
         attach methods: 1=1 2=0 3=0 4=0 5=1 6=0
         recipient address types: 3002=001F(smtp)=1  3003=001F(ex)=1
  P5 ... 007D type census: 001F=3  001E=0  other=0
         1000 type census: 001F=1  001E=0  other=0
         1013 type census: 001F=0  001E=0  other=2
  P6 ... divRplyFwdMsg: 1/2   appendonsend: 1/2   x_ prefix: 1/2   blockquote: 0/2
  ```

  The `directory entries histogram` values (16/20/32) are the directory-stream entry counts the writer's per-sector
  packing yields (4, 5 and 32 entries per 512/512/4096-byte directory sector); the `stream size buckets` are keyed
  per file on its **largest** stream (the spec's worked example sums to N, so it is a per-file bucket).
- **Refusals and robustness** (`out/probe_refusals.txt`, **sha256
  `6e396250fee83a52887f18bb21eacd1e1708ef5920121076e5342e4847f82389`**): a path inside the repo -> exit **2** one
  line; the `fixtures/` tree -> exit **2**; a missing path -> exit **2**; an empty dir -> exit **2**; a non-OLE
  `bad.msg` in a directory -> the good files are probed and `unreadable: 1  [not_ole:1]` is printed, exit **0**;
  `--limit 1` restricts the scan.
- The script **is not run on any real file by this turn** -- that is the owner's step.

## 5. Decision

**A'' is ratified structurally.** No experiment re-opens it: the comparison (section 3) forces **no** edit to tiling
or ordering inside `_walk_visit`, and E5/E6/E7 show the eight provenance points are keyword/default additions that
leave the `.eml` path byte-identical (E5: `.eml` ids unchanged; E6: 88/88 fixtures unchanged; E8: the `.eml`
artifact unchanged). E1-E3 confirm the own-reader contract is total, bounded and account-clean.

**One constraint fails as specified: E4's memory budget.** A `bytes`-valued `raw_bytes()` costs ~4x a 40 MiB
pass-through attachment (167.8 MB), over the declared 3x budget, because `walk()` and `assemble()` each slice the
leaf into a fresh `bytes`. Build spec section 7's "unless E4 shows it is needed" clause therefore fires: a **lazy
`raw_bytes()`** (a `container.py` `Container` protocol addition) is needed. This is a bounded protocol change, **not**
a `_walk_visit` structural change, so it does not re-open A''; it does add one item to Turn 1b.1's scope. Per brief
rule 6 and the "Checks and report" clause, this turn **stops here**: no Turn 1b.0c and no package code is started.

If the owner prefers not to take the lazy-view scope addition now, the alternative is to re-declare the budget
(section 7, Q5) and carry the ~4x cost as a recorded limitation (`max_input_bytes` already bounds the worst case at
64 MiB -> ~256 MB peak) -- a decision the owner makes, not a build turn.

## 6. Deviations from the contract

1. **P1 reads one property stream beyond the properties tables.** The probes spec's privacy rule 2 says the only
   stream read is the structural `__properties_version1.0` table, but P1's own requirement (bucket the message class
   by its `IPM.Note*` prefix) cannot be met without reading the class value, which lives in
   `__substg1.0_001A001F` (a PT_UNICODE property stream). The script reads it **only to bucket it** and never prints
   it; the instrumented-read demonstration (section 4) shows exactly this one extra stream plus P6's HTML stream.
   Reported, not bent -- owner's call (section 7, Q2).
2. **E4 fails its budget** (section 2); the named fix is a `container.py` lazy view, not a contract change.
3. **E2's whole-file vocabulary is exactly the two named faults.** A *truncated* file whose directory sector chain
   cannot be walked (its FAT is missing) is classified as `OUT_OF_RANGE` (a per-stream code) rather than a third
   whole-file name, because the contract names only `cfb_directory_loop` and `cfb_header_unsupported`. If the owner
   wants a distinct `cfb_file_truncated` whole-file fault, it is a one-line addition -- noted.
4. **`stream_kind` == `axis`.** The round-4 debate agreement's `stream_kind` axis (`stream | reencoded`) is the
   contract's `ContainerStreamAxis`; the prototype uses the contract's `axis` name everywhere, as section 7 requires.
5. **`mini_cfb.py` and the P3 histograms.** The scratch writer is ~250 lines, not the brief's "about 150"; it
   hand-types the MS-CFB layout (it does **not** import or copy `olefile`, and it is not `tools/cfb_writer.py`).
   P3's `directory entries` = `len(ole.direntries)` and its `stream size buckets` are per-file on the largest stream;
   both choices are stated in section 4 because the probes spec fixes the histories only by a worked example.
6. **`ole.fat` marks.** E3's classifier uses the header-declared FAT/miniFAT ranges plus the stream chains, not the
   FAT's `FATSECT`/`DIFSECT` markers, because `olefile` does not validate them and the own reader (1b.3) may differ;
   noted so 1b.3's classification is not assumed to key on the markers.

## 7. Questions for the owner

1. **Ratify A'' with the E4 scope addition?** Accept the lazy `raw_bytes()` (a `container.py` protocol change) as
   part of Turn 1b.1, or re-open the memory decision? (Recommended: accept -- it is bounded and does not touch
   `_walk_visit`.)
2. **P1's class read.** Accept the one extra property-stream read (and amend the probes spec's rule 2 to name it), or
   drop the class bucket so P1 reports only body-stream presence, methods and sizes?
3. **Extended DIFAT.** The `.msg_difat_extended` path is unexercised (no fixture reaches >~7.14 MB); P3's DIFAT-length
   histogram will settle whether the owner's corpus needs it. The reading is already recorded as **read-through**
   (owner decision O1: `email-extraction-design.md:272-273` and `:887-888`, which `:841`'s legacy D13 "a named gap,
   not a crash" line is superseded by; `phase0-gaps.md:616-623`). Confirm this stands before Turn 1b.3 emits
   `msg.cfb_difat_extended` (a presence *observation*, faulting only on a broken chain).
4. **`max_input_bytes` asymmetry.** A ~50 MB `.msg` passes the 64 MiB gate its ~67 MB base64 `.eml` twin fails.
   Confirm this is recorded as designed (contract section 7), not treated as a defect.
5. **The E4 budget.** Is 3x the right declared budget, or should it be re-declared (e.g. 5x) so the lazy view can be
   deferred? If re-declared, the peak is bounded by `max_input_bytes` (64 MiB -> ~256 MB peak).
6. **E2's truncated-file class** (deviation 6.3): keep `OUT_OF_RANGE`, or add a `cfb_file_truncated` whole-file name?

**Answers (2026-10-13).** Q1 accepted (the lazy `raw_bytes()` was attempted in Turn 1b.1); Q5: the budget is
**re-declared to 5x** (build spec O9) after the 1b.1 re-run measured 4.0x; the `attach.py` payload view moves to Turn
1b.5. Q2, Q3, Q4 and Q6 were taken at their recommended defaults (the P1 class read stands, extended DIFAT is read
through, the `max_input_bytes` asymmetry is designed, `OUT_OF_RANGE` stays).

## 8. Experiment verdicts at a glance

| exp | verdict | deciding number | later turn that re-runs it |
|---|---|---|---|
| E1 | PASS | 14/14 terminate, 0 hang; oracle is well-formed-only and clamps a cyclic chain silently | 1b.2, 1b.3 |
| E2 | PASS | 0 raise/hang; every input one outcome; max work 103 << bound 216 | 1b.3 |
| E3 | PASS | sum - file = 0 on 5 fixtures; cyclic mutants show `unaccounted` | 1b.3, 1b.5 |
| E4 | **FAIL** | 167.8 MB = 4.0x stream > 3x budget; lazy `raw_bytes()` needed. 1b.5 re-run on the real projection: 5.05x > the re-declared 5x (section 9) | 1b.1, 1b.5 |
| E5 | PASS | unmodified diffs 3 (>0); gated diffs 0; `.eml` ids unchanged | 1b.1 |
| E6 | PASS | 0 wrong cases; 0 edge raises; 88/88 `.eml` fields unchanged | 1b.1, 1b.5 |
| E7 | PASS | 2/2 leaves `part_level`/`container_stream`; unmodified claims `exact` (finding) | 1b.1, 1b.5 |
| E8 | PASS | re-ingest identical; 0 `virtual_*` tokens; recompute == rows; `.eml` untouched | 1b.1, 1b.5, 1b.10 |
| compare | PASS | 0 differing fields; no `_walk_visit` edit forced | 1b.1, 1b.9 |
| probe | built | sentinels 0; body/header streams opened 0; refusals exit 2 | owner runs it; feeds 1b.6/1b.7/1b.9 |

## 9. Turn 1b.5: the `synthetic` record ref (contract Q3), and the E4 re-run

**Q3, answered: a synthetic leaf carries a `stream_ref` on its `PartRecord`.** The projection's root
region -- and, later, any synthesized MIME boundary -- is a `SYNTHETIC` span row, and
`assemble._part_records` publishes `stream_ref_of(row)` for it, so a document from a `.msg` looks like:

```
root : stream_ref = ContainerStreamRef(stream='synthetic:root:1', byte_offset=None,
                                       byte_len=None, axis=SYNTHETIC, fault=None)
```

The ref is carried (not `None`) because C6's "a consumer can tell scaffolding from evidence" is then a
single field check, `axis is SYNTHETIC`, and `model.py` already validates exactly that shape: a
synthetic ref must have `byte_offset is None`/`byte_len is None` and a `synthetic:<role>:<ordinal>`
stream label. Carrying `None` instead would make "no ref at all" and "a `.eml` part with no container"
indistinguishable, and every consumer would have to consult the span table to know which. The cost is
that the `synthetic:` label is a *labelling convention*, not a stream name; `model.py`'s validator
enforces the convention, and no consumer opens a ref by name (`cfb.read_stream` is only reached from
`msgcontainer`).

**E4 re-run at the re-declared 5x budget (brief D10; this turn's declaration).** A synthetic 40 MiB
`0x1013` (`PT_BINARY`) stream in a version-4 `.msg`, driven through `MsgContainer` -> `walk` ->
`assemble`, peak working-set delta, the same `GetProcessMemoryInfo` harness as E4:

| measure | delta | over the stream |
|---|---|---|
| container + walk + assemble (the built `.msg` excluded) | 211.8 MB | **5.05x -- over** |
| the same, with the built `.msg` bytes in the delta | 254.8 MB | **6.07x -- over** |
| container construction alone | 83.5 MB | 2.0x |
| container + `walk` (cumulative) | 120.5 MB | 2.9x |

**Still over, and the dominant copy is not in `attach.py`.** The copies, in order of size (all ~40 MiB,
tracemalloc stage peaks): (1) `cfb.read_stream` of the `0x1013` payload out of the file; (2) the
materialised virtual message -- `raw_bytes()` is a `bytes` value, so the projection's own string exists
once (this pair is the container's whole share, 83.5 MB = 2.0x); (3) the walker's decode of the leaf for
the charset ladder (`text.py` needs `bytes`, not a `memoryview`); (4)-(5) the HTML projection inside
`assemble`/`selection`/`htmltext`, which needs the 40 MiB text twice (the parsed node text and its
normalised projection). So the overshoot is **the HTML projection over a 40 MiB HTML body**, plus the
walker's one decode copy; the container copies a pass-through HTML leaf exactly once more than the
virtual string itself requires, which is what D10 asked for. The named fix for the remainder is the
lazy `raw_bytes()` view (protocol) plus a view-based HTML text stage -- both owner decisions, so
`attach.py` is untouched and nothing was bent to reach the number. (The `.eml` control at 1b.1
measured 4.0x with the same harness on the same stream size; the `.msg` projection adds the container's
own pair, which is why 5x and not 3x is the re-declared budget.)

## 10. Turn 1b.6: where the message-level facts plug in

`MsgContainer` publishes one more producer-internal attribute beside `container_gaps`: `message_facts`
(a `NamedTuple` in `msgcontainer.py`), the MAPI-side facts about the message -- `subject` (D3),
`sender` (D4), `recipients` (D5, one `RecipientFact` per directory row, in index order, duplicates
kept) and `times` (D7, one `TimeFact` per present `PT_SYSTIME` tag). It holds plain data only
(`str | None`, `int`, tuples); no `Property`/`TextValue` object leaves the container. It is
`None`/empty for a message whose class gate stopped (nothing past the class was opened).

`container_facts()` carries the two flat key families the contract section 6 table names for 1b.6:
`recipient_count` (the directory row count) and `time.<tag>.filetime_hex`/`time.<tag>.utc` (one pair
per present, unfaulted `PT_SYSTIME` tag, in ascending tag order). Both are published only for a
message the gate opened, and `recipient_count` only when the directory yields at least one row, so the
four zero-recipient Turn 1b.5 fixtures keep the exact key set
`tests/test_msgcontainer.py::test_container_facts_carry_the_fixed_key_list` pins (and the 1b.7
`attachment_count` is expected to follow the same rule). The `mapi` message-level observations are
mapped into `container_gaps` (D8), in `mapi.OBSERVATION_IDS` order after the 1b.5 gaps:
`msg.property_tag_unknown` (the sorted distinct `tag:type` pairs joined by `,`),
`msg.named_property_unresolved` (the sorted tag hexes from `MapiMessage.named_tags` joined by `,` --
the record carries tag hex only, never a type, a brief-versus-`mapi` mismatch reported in the outcome
note), `msg.codepage_unresolved_ladder_used` (empty detail: `mapi` exposes no surface set) and
`msg.recipient_table_unreadable` (`declared=<n> rows=<n>` for a count disagreement, else the row/table
fault).

**What Turn 1b.7 and Turn 1b.10 need.** An attachment row (1b.7) joins the same way: read through
`cfb`/`mapi` beside the projection and publish `attachment_count` in `container_facts` (again only
when the directory yields one), with the subject/sender/recipient rows untouched. 1b.10 is the
consumer: it projects `MessageFacts.subject`/`sender`/`recipients`/`times` into the `msg.*` sidecars
(the `msg.recipients` shape drops the container record's `smtp_address`/`fault`/`value_source`; the
`msg.time_facts` shape is the `TimeFact` triple) and persists `container_gaps` under
`part.gaps`/`gaps.later`. Nothing in this turn persists them: the attribute is the hook, exactly as
`cap_observations` was for Turn 1b.1.


## 11. Turn 1b.7: the attachment layout and the storage-tree digest

A `.msg` with at least one `__attach_version1.0_#XXXXXXXX` storage projects as a
`multipart/mixed` (D1): the first child is the body as Turn 1b.5 builds it (plain, HTML, the
`multipart/alternative` of both, or an empty `text/plain` leaf when there is no body), then one
leaf per attachment in **attachment-storage index order** (the directory's `#XXXXXXXX` order,
never a declared count). A message with **no** attachment storage produces exactly the 1b.5 bytes.
The top-level `Content-Type` structure line is still first, so the 1b.5 first-wins layout holds:
re-measured with `multipart/mixed`, the virtual message opens
`MIME-Version: 1.0` / `Content-Type: multipart/mixed; boundary="..."` / then the transport headers,
and the root part's `content_type` is `multipart/mixed`.

Each leaf's part-header lines are `SYNTHETIC` rows (`synthetic:attachment:<ordinal>` for a leaf
with no readable bytes); a by-value leaf (method 1, `0x3701:0102`) folds its header lines into the
`STREAM` row the way the HTML leaf of 1b.5 does, so the record's span-table join, `stream_ref`, and
the pass-through size/digest all come from one row (`source_sha256` is the stream's own digest).
`Content-Type` is the `0x370E` MIME tag **as stored**, or `application/octet-stream` when absent
(the fact's `mime_tag = None` records "defaulted", the only place the two are distinguished -- the
attach stage's `declared_mime` verdict reads `application/octet-stream` either way);
`Content-Disposition` is `inline` when `0x3714` has the `ATT_MHTML_REF` bit (`0x4`), else
`attachment`, with the filename parameter from the ladder; `Content-ID` is `0x3712` wrapped in
`<...>` only if it is not already; the CTE is `binary`. The `0x7FFE` hidden flag has no MIME
equivalent: it is recorded in the facts and no header is invented for it. A method-5 (embedded),
method-6 (OLE) or reference (2/3/4) leaf is a zero-length `SYNTHETIC` body with the part's
`size_bytes`/`sha256` `None` (`0`/the empty digest at the occurrence); `message/rfc822` is never
used (the embedded storage has no RFC 822 bytes to back the claim).

**The filename ladder (D3).** Long `0x3707` over short `0x3704` over display `0x3001`: the first
present, non-empty value wins and its rung (`long`/`short`/`display`/`none`) is recorded. The
projected parameter is a plain quoted string only for printable ASCII outside `"` `\` `/` `;`;
anything else (a control character, NUL, a separator, a quote) uses RFC 2231's
`filename*=utf-8''<percent-encoded>`, so `attach.py` recovers the property text byte for byte. The
name is **data**: no `Path`/`open`/`os.*` call touches it and it is never sanitised.

**`storage_tree_sha256` (D4), the canonical walk.** Over the entries under an embedded-message
storage (not the storage entry itself): sort them ascending by their **full relative path** as
UTF-8 bytes (separator `/`); for each entry append `b"S"` (a storage) or `b"T"` (a stream), the
path length as a 4-byte big-endian integer, the path's UTF-8 bytes, the stream size as an 8-byte
big-endian integer (`0` for a storage), and, for a stream, its bytes (`cfb.read_stream`). The digest
is the sha256 of that concatenation. A stream under the storage that faults publishes **no** digest
(`None`) and records `msg.stream_truncated`. It is never claimed to equal any file's hash. It does
cover a nested embedded message's streams -- computing it reads them -- though the nested message is
never read into an `EmbeddedSummary` (the depth cap; `msg.embedded_depth_cap`).

**The embedded table's header (D4).** An embedded message's own `__properties_version1.0` opens on
a **24-byte** header (`[MS-OXMSG]`'s embedded-message value), neither the top-level 32 nor the
sub-table 8: measured by the entry count -- `(size - 24) % 16 == 0` leaves exactly the declared
entries, while an 8-byte header injects a spurious `0000:0000` entry. It is read with
`mapi.parse_property_table(..., header_size=24)`.

**`attachment_facts` (D6).** `MsgContainer.attachment_facts` is a frozen tuple of `AttachmentFact`
named tuples (plain data -- `index`, `method`, `filename_raw`, `filename_source`, `mime_tag`,
`cid`, `hidden`, `inline`, `size`, `sha256`, `embedded_summary`, `storage_tree_sha256`, `fault`,
`source_stream`), one per directory row in index order. The join between a record and its
`PartRecord` is through the span table (`source_stream`), never through a virtual offset in a record
or a `part_id`. `container_facts["attachment_count"]` is the directory row count, published only
when it is at least 1 (the 1b.6 `recipient_count` rule). The attachment gaps ride `container_gaps`
after the 1b.6 gaps: `msg.attachment_method_unsupported` (detail `<index>:<method>`),
`msg.stream_truncated` (detail `attach:<index>:<fault>`) and `msg.embedded_depth_cap` (detail
`<leaf ordinal>><nested index>`, e.g. `2>0` -- the brief's example form `1.2>1` names the
occurrence path, which is not known at the container layer; reported in the outcome note).
`assemble.py` gains one `cfb_msg`-gated edit: it fills `AttachmentOccurrence.embedded` from the
facts, joined through the span table; every `.eml` container keeps the current expression verbatim.

## The RTF record (Turn 1b.8) and where 1b.10 projects it

**The ``0x1009`` stream is decompressed, checked and recorded -- never a body view (owner decision
O2).** ``emailextract/rtf.py`` takes the stream's bytes and returns a frozen ``RtfResult``: the
``comptype`` (``"LZFu"``/``"MELA"``/hex), ``stream_length``, the three declared header words
(``compsize``, ``rawsize``, ``crc``), whether the CRC matched, the decompressed length and its
sha256 (``None`` when faulted) and a fault from a closed list. Nothing in it is the RTF text: the
decoder keeps a 4096-byte dictionary, a bounded hash buffer and the running length, and never
retains the output. The format is [MS-OXRTFCP] 2.1: a 16-byte header, an ``LZFu`` data stream of
LSB-first control-byte flags with 12-bit-offset/4-bit-length references, and an end marker whose
offset equals the current write position.

**``MsgContainer.rtf_facts``.** A frozen ``RtfResult`` (or ``None`` with no ``0x1009`` stream),
beside ``message_facts``/``attachment_facts``. It is not on ``EmailDocument``, not in
``container_facts`` beyond the existing ``body_streams`` (which already lists ``rtf``), and not in
``to_json``: nothing consumes it until **Turn 1b.10**, which projects it (a ``msg.rtf`` sidecar
section and the two gaps below). A present ``0x1009`` stream adds **no** ``PartRecord``, no
``BodyView``, no selection result and no virtual byte; ``msg_rtf_only`` projects exactly as a
message with no body stream does in 1b.5.

**The gaps.** Every present ``0x1009`` stream raises the registered ``msg.rtf_to_text_unsupported``
(it says the body is not converted), faulted or not. A damaged stream -- a CFB chain fault or a
decoder fault -- *also* raises the existing ``msg.stream_truncated`` with the detail
``0x1009:<fault>`` (the form 1b.5's D0.1 fix gave body faults) and sets the document ``Status`` to
``TRUNCATED`` with the contract-section-2 reason. No new gap id and no ``BodyView`` member is added;
``msg.rtf_encapsulation_refused`` is **not** created (O2).
