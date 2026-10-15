# Turn 1b.10a: persist and measure the container-side facts, read `.msg` labels, type the sidecars

Status: brief for one build turn. Author: reviewer session, 2026-10-15. Builder: hearth. Builds on `261c005` (Turn 1b.9 committed).
Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session. **Do not commit.**

**Pace this turn.** The risk is in the sidecars' expectations (hand-typed, independent of the code), not the plumbing. Iterate on the files
you touch; run the full suite once at the end on the primary interpreter and once on 3.11, then the mutations.

## Why 1b.10 is split, and what this turn is

`phase1b-build-spec.md` and the `declaration turn=1b.10` block put "gates, hostile run, scope test, ledger components, report, release" in
one turn. Checking the tree at `261c005` shows that block **omits the work everything else depends on**:

* 52 `.msg` fixtures are committed and **0 sidecars** (`*.expected.json`); `evals/labels.py` accepts `.eml` only (`FIXTURE_SUFFIXES`).
* None of the 11 new facts has a measurer; `l1.FACTS` does not declare them; `facts_ledger.json` lists none.
* Nothing persists `message_facts`, `attachment_facts`, `rtf_facts` or `container_gaps` (each turn since 1b.5 left them "container-side until
  1b.10"), and `tools/behavior_ledger.py` has no `cfb`/`msg_reader`/`msg_projection` component.
* The declared 1b.10 allow-list names none of `labels.py`, `tools/behavior_ledger.py`, `fixtures/msg/**/*.expected.json`, or the
  `msgcontainer`/`mapi` projection edits.

So the close is **two turns**: **1b.10a (this one)** makes the facts exist, measurable and labelled; **1b.10b** adds the gates, the hostile
run, the scope test, the three ledger components, the report and `0.2.0`. If you disagree, say so with evidence; do not build 1b.10b's
parts here. The ledger's 1b.10 declaration block is **split** into `1b.10a`/`1b.10b` blocks as part of this turn (see Allow-list).

## Read first

`phase1b-facts.md` (the whole table, every value shape and the "Consequences for facts_ledger.json" section), `phase1b-ledgers.md` (sections
(a)(b)(e), the 1b.5/1b.6/1b.7/1b.8 "What 1b.10 needs" notes, the 1b.9 outcome note), `msg-architecture.md` (the sections naming 1b.10 as
consumer: message facts, the RTF record, the span-table join), `phase1b-contract.md` (sections 8 and 11), `phase1b-fixtures.md` (the
catalogue and counts), `emailextract/evals/l1.py` (`Measured`, `Measure`, `FACTS`, `_part_gaps`, the `gaps.later` measurer, `LIVE_GAP_IDS`),
`emailextract/evals/labels.py`, `emailextract/msgcontainer.py` (`message_facts`, `attachment_facts`, `rtf_facts`, `container_gaps`,
`container_facts`), `docs/design/phase1-facts.md` (sidecar conventions, decision 12).

## Decisions the reviewer made (the owner may overrule; say so with evidence)

**D1. Measurers read the container, not a new document field.** `EmailDocument`, `to_json`, `ContainerFacts` and the schema do **not**
change (no second bump). The `msg.*` measurers live in `evals/l1.py` and read the `MsgContainer` that produced the walk. Extend `Measured`
with an optional container handle (`None` for `.eml`); `evals` already imports the package, `labels.py` still must not. State how the
container reaches `Measured` (the `evals` runner constructing it beside the walk is the expected shape) and prove `.eml` measurement is
byte-identical (the `.eml` golden stays untouched).

**D2. Measure the 11 facts, project exactly the shapes in `phase1b-facts.md`.** One measurer per fact id, value shape exactly as
documented, including the `msg.recipients` projection (drop `smtp_address`/`fault`/`value_source`), `msg.time_facts` as the `TimeFact`
triple, and `msg.rtf` as the sidecar section 1b.8 promised (the doc names a `msg.rtf` section: **decide** whether it is a 12th fact id or
rides `msg.body_streams`; the facts table lists 11, so default to *no new id*: report the RTF record as part of the `msg.body_streams`
row's detail only if the shape allows, else raise it as a finding and stop on that one item). `msg.container_layout` and
`msg.sector_accounting` come from the CFB reader; `msg.stream_faults` from the per-stream faults.

**D3. `part.gaps` and `gaps.later` carry the `msg.*` gaps through the existing measurers.** `container_gaps` is persisted by the existing
channels; no new fact type. `LIVE_GAP_IDS` gains exactly the twelve ids listed in `phase1b-facts.md`; `EMITTABLE_GAP_IDS` in `falsify.py`
reads off it (so `falsify.py` is **not** edited unless that derivation is not already live; check, and say which).

**D4. `labels.py` learns `.msg`, and stays import-free.** `FIXTURE_SUFFIXES` becomes `(".eml", ".msg")`; the loader change is the suffix and
nothing about fact ids. `tests/test_labels.py` (the bare-interpreter proof) must still pass. The `.eml` corpus, `corpus.json` and the
`.eml` golden are untouched.

**D5. Sidecars are hand-typed, from the construction tables, never from the code (decision 12).** For each committed `.msg` fixture, type
its `*.expected.json` from `tests/support/msg_construction.py`'s construction table and the facts doc, **before** running the measurer
against it. A disagreement between a typed label and the measurer is a **finding**, reported with both values; the sidecar is not edited
to match. Sidecars carry only the facts that fixture is meant to exercise (`msg.container_layout`/`msg.sector_accounting`/`msg.message_class`
on every readable one, the rest where the fixture's family says so) with `provenance: spec`. The two hostile fixtures whose layout is
deliberately broken, and the pair's `.eml` (not committed, D1 of 1b.9), carry no sidecar for facts they cannot produce. Work in
**families** (D-I of the catalogue), one family at a time, and report counts per fact against the floors as you go.

**D6. Floors: declare, then meet.** Add the 11 ids to `l1.FACTS` (phase 1, `live` as measurers ship; `CURRENT_PHASE` stays 0), the 11 ids
to `tests/ledger/facts_ledger.json`'s `phase1` list (`deferred` stays `[]`), and the 11 floors to `FLOORS` in `tests/test_facts_coverage.py`
**from the facts table** (45/45/40/20/10/4/8/2/8/2/2 and `gaps.later` 5). If a floor is not met by the sidecars the catalogue supports,
that is a finding about the catalogue, not a floor to lower: report each shortfall with the fixtures that could close it.

**D7. Facts coverage test only; the gap gate is 1b.10b.** `tests/test_facts_coverage.py` is extended here (floors, observed counts, "a
fact below its floor fails", "a fact that moves its phase fails against the pinned ledger"). `tests/test_phase1b_gap_gate.py`, the scope
test, the report and the ledger components are **1b.10b**.

## Order of work

1. **Plumbing and declarations**: `Measured` container handle (D1), `labels.py` suffix (D4), the 11 declared facts and ledger entries (D6),
   `LIVE_GAP_IDS` (D3). `.eml` suite and golden still green before anything else.
2. **Measurers (D2)**, fact by fact, each with a unit test over a small fixture it is typed for.
3. **Sidecars (D5)** family by family: type, then run, then reconcile findings. Do not run the measurer first.
4. `tests/test_facts_coverage.py` floors and the pinned-ledger test (D6/D7).
5. Full suites, `--check` tools, mutations, the outcome note.

## Tests

Declare a `declaration turn=1b.10a` block (names exact, in `phase1b-ledgers.md`, mirrored in `phase1-turn-declarations.md` and wired into
`tests/test_turn_declarations.py::BUILT_TURNS`). At minimum:

* One measurer test per new fact id (11), each asserting the **hand-typed** value for a named fixture, not a recomputation.
* `test_every_msg_sidecar_loads_and_names_only_declared_facts`: every `.msg` sidecar loads through `labels.py` and every fact id it names is
  declared in `FACTS` with phase 1.
* `test_every_msg_fixture_has_a_sidecar_or_a_recorded_exemption` (an explicit, typed exemption list with the reason per fixture).
* `test_the_eml_measurement_is_unchanged_by_the_container_handle`: a sample of `.eml` fixtures measures byte-identically to before.
* `test_msg_gaps_ride_part_gaps_and_gaps_later`: each emitted `msg.*` id appears through the existing channels only.
* `test_every_phase1b_fact_meets_its_floor` and `test_a_fact_below_its_floor_fails` (planted: a floor raised past the observed count).
* `test_the_facts_ledger_pins_the_eleven_ids` (a phase change or a dropped id fails).
* Determinism of the measured values under two `PYTHONHASHSEED`s on both interpreters.
* Hostile and fuzz inputs through the measurers: no exception, per-fact `unmeasurable` rather than a crash.

**Mutations** (each must make a named test fail; run, restore, report): (1) a measurer that reads a value from the code path the sidecar is
supposed to be independent of (e.g. reuse the projected `message_class` where the label is typed) must still be caught by a typed-label
disagreement planted in a copy of one sidecar; (2) drop one `msg.*` id from `LIVE_GAP_IDS`; (3) raise one floor past the observed count.

## Allow-list

New `declaration turn=1b.10a` and `turn=1b.10b` blocks replace the single `turn=1b.10` block in `docs/design/phase1b-ledgers.md` (1b.10b
keeps the original 1b.10 module list minus what lands here; do not build any of it). 1b.10a's files: `emailextract/evals/l1.py`,
`emailextract/evals/labels.py`, `emailextract/evals/__main__.py` or `emailextract/evals/__init__.py` (only if the runner must hand the
container to `Measured`; name each line), `emailextract/evals/falsify.py` (only if `EMITTABLE_GAP_IDS` is not already derived), the
`msgcontainer.py`/`mapi.py` read-only accessors the measurers need (**no** behaviour change; each hunk named, with the measurer that needs
it), `fixtures/msg/**/*.expected.json` (new files only), `tests/ledger/facts_ledger.json`, `tests/ledger/label_ledger.json` (re-recorded
for the recorded files), `tests/test_labels.py` (only the suffix expectation), `tests/test_facts_coverage.py`, `tests/test_msg_measurers.py`
(new), `tests/test_turn_declarations.py`, `tests/test_fixture_census.py`, `docs/design/phase1b-ledgers.md`,
`docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-facts.md` (only to correct a sentence a finding proves wrong; list each).
**Not**: `emailextract/model.py`, `assemble.py`, `walk.py`, `cfb.py`, `rtf.py`, `ingest.py`, `parse.py`, `versions.py`,
`tools/behavior_ledger.py`, `tests/ledger/behavior_ledger.json`, `tests/ledger/corpus.json`, the `.eml` golden, any `.eml` fixture or
sidecar, `emailextract/evals/gates.py`, `pyproject.toml`, `CHANGELOG.md`, `README.md`, `NOTICE`, `CLAUDE.md`.

## What must NOT be done

No schema bump and no new `EmailDocument`/`to_json`/`ContainerFacts` field. No change to any projection, hash, span or ladder behaviour (a
measurer that needs a different value is a finding). No sidecar generated from the code, and no sidecar edited to make a check pass. No
lowered floor. No `.msg` sidecar for a `.eml`-only fact. No `olefile` import under `emailextract/`. No real or employer message. No gap
gate, scope test, report, ledger component, version bump or release prep (1b.10b). Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on 3.11; wall time by chunk.
2. `tools/make_msg_fixtures.py --check`, `make_fixtures.py --check`, `update_eml_golden.py --check`, `update_behavior_ledger.py --check`,
   `update_label_ledger.py --check` and `python -m emailextract.evals` exit 0 (`behavior_ledger.json` **untouched**).
3. The outcome note in `phase1b-ledgers.md`: D1-D7 and whether you changed any, with evidence; the container-to-`Measured` mechanism; the
   per-fact observed count against each floor; every finding (typed label versus measurer, catalogue shortfall, the `msg.rtf` question);
   the fixtures carrying no sidecar and why; the three mutation results; every existing test edited and why.
4. What 1b.10b needs: the 12 live gap ids' mutation cases (one per `msg.*` id, with the fixture or seed that triggers it), the hostile run
   inventory, the three ledger components' corpus and version constants, the report's section inputs (counts, findings, the `max_input_bytes`
   asymmetry facts, licences), and the release edits (`pyproject.toml` `0.2.0`, CHANGELOG, README lines 23-24 and 65, `NOTICE`).

## Not this turn, but the owner should decide

* **Split 1b.10 into 1b.10a/1b.10b?** (Above.) Recommended; the original single turn cannot be built inside its own allow-list.
* **Commit the pair's `.eml`?** Still open from 1b.9; absorbing it would move the golden and corpus version, which belongs with 1b.10b if at
  all.
* **`MELA` CRC leniency, the dictionary's unwritten-byte rule, `CODEPAGES` width** (fixture `msg_string8_message_cpid` uses cp 437): open.
* **P1-P6 on the real corpus**: every tag outside the first eleven spike files is public-spec only until the owner runs the probes; the
  report (1b.10b) will say so.

Stop at the turn boundary: every Phase 1b fact is declared, pinned, measured and labelled, floors are met or each shortfall is a finding,
the `.eml` side and `behavior_ledger.json` are untouched. Do not start 1b.10b.
