# Turn 1b.10b: the Phase 1b close -- the gap gate, the hostile run, the scope test, the three ledger components, the report, `0.2.0`

Status: brief for the last build turn of Phase 1b. Author: reviewer session, 2026-10-15. Builder: hearth. Builds on `71c8304` (Turn 1b.10a
committed). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session. **Do not commit and do not tag** (the owner commits, then
tags `v0.2.0`).

**Pace this turn.** Most of the risk is in two places: the ledger components (a new fingerprint must not move any `.eml` line or the
golden) and the report (every number sourced, nothing invented). Iterate on the files you touch; run the full suite once at the end on
the primary interpreter and once on 3.11, then the mutations.

## What this turn is

The close. Phase 1b's code, facts and labels exist (1b.1-1b.10a); this turn adds what **proves and records** them and ships them:

1. **The Phase 1b gap gate** (`tests/test_phase1b_gap_gate.py`): every `msg.*` gap id has a working mutation case and a named fixture.
2. **The hostile run**: one consolidated, committed inventory-and-test of the hostile `.msg` inputs through the whole pipeline.
3. **The scope test** (`tests/test_phase1b_scope.py`): the library never imports `olefile`; no real `.msg` is in the repository.
4. **The three ledger components** (`cfb`, `msg_reader`, `msg_projection`) with their version constants, over the committed `.msg` corpus.
5. **The report** `docs/phase1b-report.md` and the **`0.2.0` release preparation**.

It changes **no behaviour** of `cfb.py`, `mapi.py`, `msgcontainer.py`, `rtf.py`, `attach.py`, `walk.py`, `assemble.py` or any measurer. A
defect a new test finds is a **finding**, reported with the failing expectation and left unfixed unless the owner says otherwise (the one
exception: a defect that makes a component fingerprint nondeterministic; name it, show the failing check, fix the minimum).

## State at `71c8304`, so you do not redo it

* **The twelve `msg.*` gap ids are already live** (`l1.LIVE_GAP_IDS`); **eleven mutation cases are already in
  `falsify._PHASE1_CASES`** and the twelfth (`msg.recipient_table_unreadable`) is named in `UNEXERCISED_GAP_IDS` (its only trigger is the
  test-built seed `seed_recipient_count_mismatch`). 1b.10a built these early because registering the ids required them (its finding 1).
  The phase-1 gate (`tests/test_phase1_gap_gate.py`) already tiles `EMITTABLE_GAP_IDS` against them.
* The eleven `msg.*` facts are declared, measured, pinned in `facts_ledger.json`, and floored. Two floors are **unmet** and recorded in
  `declared_unmet`: `msg.recipients` 4 of 10, `msg.time_facts` 1 of 4.
* `behavior_ledger.json`, `corpus.json`, `versions.py`, `gates.py`, `phase1_exit.json` and the `.eml` golden are **untouched** so far.
  `tools/behavior_ledger.py` has `COMPONENTS = ("walk", "decode_chain", "contracts")`; none of `CFB_VERSION`, `MSG_READER_VERSION`,
  `MSG_PROJECTION_VERSION` exists.
* `emailextract/__init__.py:129` carries `__version__ = "0.1.0"` as well as `pyproject.toml:7`; `docs/releasing.md` names `0.1.0` in its
  steps. `NOTICE` already names `olefile` (BSD-3-Clause) as a dev-only comparator, and `pyproject.toml` lists it only under `dev`.

Read first: `phase1b-ledgers.md` (sections (c), (g), (h), the `turn=1b.10b` block, the 1b.10a outcome note in full: its findings 1-9 are
the report's raw material), `phase1b-build-spec.md` (the decisions on the report, rule 6, the `max_input_bytes` asymmetry at ~:164 and
~:382), `msg-architecture.md` (the section list, the `max_input_bytes` asymmetry item 4), `phase1b-contract.md` (sections 8, 11, 12),
`phase1b-facts.md`, `phase1b-fixtures.md` (catalogue, the seeds section), `emailextract/evals/falsify.py` (`_PHASE1_CASES`,
`UNEXERCISED_GAP_IDS`, `GAP_CHANNELS`, the inline-bytes cases), `tests/test_phase1_gap_gate.py`, `tests/test_phase1_scope.py`,
`tests/test_cfb_hostile.py`, `tests/test_mapi_hostile.py`, `tests/test_hostile_set.py`, `tools/behavior_ledger.py`,
`tools/update_behavior_ledger.py`, `tests/ledger/behavior_ledger.json`, `tests/ledger/corpus.json`, `docs/phase1-report.md` (the shape to
follow), `README.md`, `CHANGELOG.md`, `NOTICE`, `docs/releasing.md`.

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. The gap gate adds the Phase 1b layer, not a second copy of the phase-1 tiling.** `tests/test_phase1b_gap_gate.py` (3 declared
tests): `test_every_msg_gap_id_has_a_mutation_case`, `test_the_phase1b_gap_gate_fails_when_a_gap_is_dropped`,
`test_the_msg_ids_are_read_off_live_gap_ids`. The set of `msg.*` ids is **read off** the registry (`phase0-gaps.md`) and
`LIVE_GAP_IDS`, never hand-listed; assert: registry `msg.*` + `headers.mapi_header_property_disagree` == live ids == (cases ∪ the named
unexercised set), each case names the fixture or seed it fires on and that file exists and is in `SHA256SUMS` (or the seed is built in
the test), and a planted drop (a case removed) fails the gate. **Close the twelfth id**: give `msg.recipient_table_unreadable` a
working case, preferring an **inline-bytes case built from the existing 1b.4 recipient-mismatch builder** (the `INLINE_ONLY` mechanism
the phase-1 gate already supports) over a committed fixture; a committed fixture would need `fixtures/msg/`, a sidecar, the census,
`SHA256SUMS` and the label ledger, none of which this turn's allow-list names. If the inline route is impossible, **stop and report**
instead of widening the allow-list. At the end `UNEXERCISED_GAP_IDS` must contain **no** `msg.*` id (or each remaining one carries a
written reason the report repeats).

**D2. The hostile run is one committed test file and one inventory.** `tests/test_phase1b_hostile_run.py` (new; declare it). It takes
every committed `.msg` (the readable fixtures, `msg_directory_loop`, and the hostile CFB fixtures) plus the **test-built seeds** (the
1b.3 `_seeds` patterns, the 1b.7/1b.9 hostile UTF-16 shapes, the recipient-count mismatch, the attachment-no-data shape) plus the
**seeded mutation operators** the existing hostile/fuzz tests use, and runs each through `parse` -> `assemble` -> `ingest` under
`Limits.untrusted()`: every input yields a **document or a named refusal**; none raises; the work-per-byte budget and `max_input_bytes`
hold; no published string fails UTF-8; the result is **identical under two `PYTHONHASHSEED`s on both interpreters**. It is an
aggregation: reuse the existing builders and operators, **do not copy them**, and do not reduce any existing hostile test. Record the
**inventory** (inputs by class, count, outcome by named reason) as a table the report embeds; the numbers come from running it, not from
the earlier turn notes.

**D3. The ledger components, exactly as section (c) specifies, outside anything the `.eml` document hashes.** Add `CFB_VERSION = "1"`,
`MSG_READER_VERSION = "1"`, `MSG_PROJECTION_VERSION = "1"` to `versions.py`, and the `cfb`, `msg_reader`, `msg_projection` components
to `tools/behavior_ledger.py` (`COMPONENTS`, `VERSION_CONSTANTS`, the corpus-dependent set, the probe), keyed
`"<version>|corpus:<N>"` like `walk`/`decode_chain`, each over the committed `.msg` corpus as section (c)'s table says (`cfb`: well-formed
fixtures only, hostile mutants excluded; `msg_reader` and `msg_projection`: every committed `.msg`). **The critical constraint:** the new
constants must **not** enter `RunRecord.projection_versions`, `limits_fingerprint`, any `document_key` or any identity the `.eml` golden
hashes. Check this **first**: add the constants, run `tools/update_eml_golden.py --check` and `tools/update_behavior_ledger.py --check`
and show both unmoved **before** writing any ledger line. If the golden would move, **stop and report**. `EMAIL_PARSER_VERSION` does
not move. The existing `walk`, `decode_chain`, `contracts`, `flatfile`-style lines and every existing corpus-keyed line stay byte-identical;
the `.msg` fixtures entering the corpus must **not** change those components' fingerprints (they fingerprint only a fixture an `.eml`
reader opens: prove it with a before/after comparison). New ledger lines are appended through `tools/update_behavior_ledger.py`; if the
corpus rule requires a new `corpus.json` version for the `.msg` files, name the entry and its fixture list in the note. Fingerprints over
the `.msg` corpus must be **byte-identical across 3.14 and 3.11** (`tools/runboth.py` reused unchanged); a difference is recorded in the
ledger header, never hidden, and is a finding.

**D4. The scope test is two guards and one emptiness proof.** `tests/test_phase1b_scope.py` (3 declared):
`test_the_library_imports_with_no_olefile_and_no_gpl` (a bare-interpreter import of `emailextract` with `olefile` blocked, as
`tests/test_phase1_scope.py`'s `BLOCKED` probe does; plus a scan of `pyproject.toml` and `NOTICE` that no GPL/AGPL/LGPL dependency is
named and `olefile` appears only under `dev`), `test_no_real_msg_is_in_the_repository` (every tracked `.msg` is under `fixtures/msg/`,
is listed in `SHA256SUMS` and is **reproduced by `tools/make_msg_fixtures.py`**, so a hand-dropped real message fails; every `.msg`
sidecar carries `provenance: spec`), `test_fixtures_real_is_empty` (`fixtures/real/` holds nothing tracked other than its ignore/readme
marker, if one exists; name it). Reuse `tests/test_phase1_scope.py`'s helpers; do not weaken any of its assertions, and extend its
`FORBIDDEN_NAME_PARTS`/scan only if a new module requires it (name each line).

**D5. The report follows `docs/phase1-report.md`'s shape and the required headings of ledger section (g).** `docs/phase1b-report.md`,
**exactly one** each, non-empty: `## What was built`, `## Named resolutions` (each with the test id that pins it), `## Coverage`
(per-fact declared floor, effective floor and observed count, **including the two unmet floors as findings**), `## Gap gate` (every
`msg.*` id with its mutation case and fixture or seed, from the gate itself), `## Label-versus-parser findings`, `## Licences`,
`## The max_input_bytes asymmetry`, `## Not done`. `tests/test_phase1b_report.py` (3 declared) checks the headings, that it names the
version bumps (`OUTPUT_SCHEMA_VERSION` `"5"`→`"6"` in 1b.1, the three new constants at `"1"`, `0.2.0`) and the licences (`olefile`
BSD-3-Clause, no GPL), and that the `max_input_bytes` asymmetry is recorded (a ~50 MB `.msg` passes the 64 MiB gate that its ~67 MB
base64 `.eml` twin fails; peak bounded by `max_input_bytes`). Every number in the report is **sourced**: from a gate output, a ledger
file or a turn note (cite it); re-measure only the final suite walls, the hostile-run inventory and the coverage table. **Honesty rules:**
state that the corpus is **synthetic**, that no real `.msg` was ever read, that every tag outside the first eleven spike files is
public-spec only until the owner runs the P1-P6 probes (`phase1b-probes.md`), and that Phase 1b changes **no** `.eml` behaviour
(golden untouched, `EMAIL_PARSER_VERSION` unmoved). `## Not done` lists, from the notes: RTF-to-text (the `msg.rtf` record stays
container-side, not a 12th fact id), embedded-message recursion (`children_axis` not built), `TimeEvent`/`times_axis`, the pair's
committed `.eml`, the `MELA` CRC leniency and the dictionary's unwritten-byte rule, `CODEPAGES` width (`msg_string8_message_cpid` uses
cp 437), the projection's stage gaps not persisted in `.msg` `gaps.later`, the two floors' missing fixtures.

**D6. Release preparation `0.2.0`, edits only.** `pyproject.toml` `version = "0.2.0"` and `emailextract/__init__.py` `__version__ =
"0.2.0"` together (a test already links or should link them: find it, and if none exists add one assertion in
`tests/test_phase1b_report.py`); `CHANGELOG.md` gets a `## 0.2.0` entry in the 0.1.0 entry's form (what it delivers, the schema bump
`"5"`→`"6"`, the three components, what it is not); `README.md`: remove the "not a `.msg`/CFB reader" bullet (lines ~23-24) and the
"`olefile` is *not* a dependency of 0.1" sentence (~65), and replace them with an **accurate** statement of what `.msg` support is and is
not (no RTF-to-text, no embedded recursion, no threading/time reconciliation, synthetic-corpus-only evidence); `NOTICE`: confirm
`olefile` BSD-3-Clause is named as dev-only (it already is; say so rather than editing without need); `docs/releasing.md` is **not** in the
allow-list: if it needs a version edit, list the lines for the owner. Do **not** tag, build or publish. The `docextract-core` pin in
`pyproject.toml` does not change.

**D7. The two unmet floors and `msg.rtf` are owner decisions, not build items.** Default: neither gets code or fixtures this turn. The
floors (`msg.recipients` 4/10, `msg.time_facts` 1/4) stay recorded in `declared_unmet` and the report's `## Coverage`, with the fixtures
that would close them (six recipient-carrying, three time-carrying) named for a possible fixture turn. `msg.rtf` stays a finding. If
you believe either blocks the release, say so with evidence; do not build around it.

## Order of work

1. **The ledger components first (D3)**, because they are the one piece that can move a frozen artifact: constants, check the golden and
   the existing ledger lines are unmoved, **then** the components and their appended lines, both interpreters.
2. The gap gate and the twelfth case (D1).
3. The hostile run (D2) and its inventory.
4. The scope test (D4).
5. Run everything once; collect the numbers.
6. The report (D5), then the release edits (D6), then `tests/test_turn_declarations.py` and the declaration/allow-list text in
   `phase1b-ledgers.md`, then the outcome note.

## Tests

The `declaration turn=1b.10b` block's names, **exactly as declared**, plus the hostile-run file. Declared: the three gap-gate tests
(D1), the three scope tests (D4), the three report tests (D5). `tests/test_turn_declarations.py` also gains the two tests the original
1b.10 block named: `test_every_phase1b_declared_test_is_collected` and `test_every_undeclared_phase1b_test_fails_the_declaration`
(reading **both** `phase1b-ledgers.md` and `phase1-turn-declarations.md`, so each turn has one block; the mirror may then be dropped only
if nothing else reads it: say which). Declare the hostile-run test names in the block in the same turn. Add, with names of your choosing
declared in the block: the ledger components' own tests (a fingerprint moves with a planted change to a `.msg` reader/projection/cfb
value; the components are keyed by their constants; the three are byte-identical across interpreters); and `tests/test_facts_coverage.py`
is **not** edited (done in 1b.10a).

**Mutations** (each must make a named test fail; run, restore, report the failing test names): (1) remove one `msg.*` case from
`falsify` (the gap gate fails naming the id); (2) change one measured `.msg` reader value (for example the ladder's chosen rung) and show
the `msg_reader` check names `MSG_READER_VERSION`; change one projection byte and show `msg_projection` names
`MSG_PROJECTION_VERSION`; change one CFB classification and show `cfb` names `CFB_VERSION`; (3) add `import olefile` to a module under
`emailextract/` (the scope test fails); (4) hand-drop a `.msg` into `fixtures/msg/` that the generator does not produce (the
no-real-msg test fails); (5) remove one required heading from `docs/phase1b-report.md` (the report test fails).

## Allow-list

`tests/test_phase1b_gap_gate.py`, `tests/test_phase1b_hostile_run.py`, `tests/test_phase1b_scope.py`, `tests/test_phase1b_report.py`,
`tests/test_turn_declarations.py`, `tests/test_phase1_scope.py` (only if a helper must be shared or a scan extended; name each line),
`emailextract/evals/falsify.py` (only the twelfth case, `UNEXERCISED_GAP_IDS` and nothing else), `emailextract/evals/gates.py` and
`tests/ledger/phase1_exit.json` (**only if a check proves they must change**; name the evidence, otherwise untouched),
`emailextract/versions.py` (the three constants only), `tools/behavior_ledger.py` and `tools/update_behavior_ledger.py` (the three
components only), `tests/ledger/behavior_ledger.json` (new lines **appended by the updater**, no hand edit), `tests/ledger/corpus.json`
(only the new corpus version the rule requires, if any, appended by the updater), `tests/ledger/facts_ledger.json` and
`tests/ledger/label_ledger.json` (re-recorded **only** for files this turn changes), `tests/test_behavior_ledger.py` (only to extend its
component list/expectations; name each edit), `docs/phase1b-report.md` (new), `docs/design/phase1b-ledgers.md` (the block, the allow-list
line, the outcome note), `docs/design/phase1-turn-declarations.md` (only if the mirror is kept), `CHANGELOG.md`, `README.md`,
`NOTICE` (only if a sentence is wrong), `pyproject.toml` (the `version` line only), `emailextract/__init__.py` (the `__version__` line
only). **Not**: `cfb.py`, `mapi.py`, `msgcontainer.py`, `rtf.py`, `attach.py`, `walk.py`, `assemble.py`, `model.py`, `ingest.py`,
`parse.py`, `container.py`, `emailextract/evals/l1.py`, `labels.py`, `docs/releasing.md`, the `.eml` golden, any `.eml` fixture or sidecar,
any `.msg` fixture or sidecar, `tools/make_msg_fixtures.py`, `tools/update_eml_golden.py`, `docs/design/phase0-gaps.md` (unless a registry
sentence is wrong; list it), `CLAUDE.md`.

## What must NOT be done

No behaviour change to any reader or projection (D3 aside, one nondeterminism fix if proven). No schema bump. No new `msg.*` gap id, no
new fact id, no `msg.rtf` fact. No new committed `.msg`, `.eml` or sidecar. No change to the `.eml` golden, `EMAIL_PARSER_VERSION`,
`OUTPUT_SCHEMA_VERSION` or any existing ledger line. No lowered floor and no edit to an owner-signed record (the `rebase` block's `reason`
and `signed_by` in `facts_ledger.json`): if a ledger edit seems to need one, stop and report. No invented number in the report. No
`olefile` import under `emailextract/`. No real or employer message anywhere. No tag, build, publish or commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (`docextract_core` and `olefile` installed); wall times by chunk.
2. All five `--check` tools and `python -m emailextract.evals` exit 0 on both; `git diff` shows the `.eml` golden, `corpus.json` (unless
   D3 named an appended version), the existing `behavior_ledger.json` lines and `phase1_exit.json` untouched, and the new ledger lines
   byte-identical across interpreters.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1-D7 and whether you changed any, with evidence; the order-1 evidence
   that the new constants moved nothing the `.eml` side hashes; the before/after proof that existing components did not move when the
   `.msg` corpus entered; the twelfth gap case and where it fires; the hostile-run inventory table; the scope test's evidence; the five
   mutation results; every existing test edited and why; every deviation from this brief.
4. A short **release checklist for the owner** at the end of the note: files changed, `docs/releasing.md` lines that name `0.1.0`, and the
   exact commit/tag steps the owner takes (not done by you).
5. What the owner still decides: the two unmet floors (a fixture turn?), `msg.rtf`, the committed pair `.eml`, the `MELA` CRC leniency,
   `CODEPAGES` width, and running P1-P6 on real mail before trusting any tag outside the first eleven spike files.

Stop at the turn boundary: the gap gate closes all twelve `msg.*` ids, the hostile run and scope test are green, the three components are
recorded and cross-interpreter identical, the report and `0.2.0` edits are in the working tree, and **nothing is committed or tagged**.
