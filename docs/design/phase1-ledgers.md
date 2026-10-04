# Phase 1 ledgers, allow-lists and declarations (Turn 1.0a specification; built in Turn 1.0b)

Four mechanisms keep Phase 1's independence and honesty **mechanical** rather than promised: the
**label ledger** (a sidecar or a gate cannot be edited in place), the **pinned `FACTS` ledger** (a fact's
phase cannot be redeclared to dodge a coverage obligation), the **turn declaration** (a turn cannot add a
test it did not declare), and the **allow-list** (a turn cannot touch a path its prompt did not name).
Turn 1.0b implements them; this document is their exact shape. The existing behaviour ledger
(`tools/behavior_ledger.py`, `tests/ledger/behavior_ledger.json`) is the template: an **append-only**
map, `--check` as the test half, `tools/update_behavior_ledger.py` as the recording half, and a
fingerprint over the thing that must not drift silently.

## (a) The label ledger — `tests/ledger/label_ledger.json`

**Path:** `tests/ledger/label_ledger.json` (beside `behavior_ledger.json` and `corpus.json`, the same
directory the behaviour ledger already uses).

**Layout** (append-only, exactly like the behaviour ledger):

```json
{
  "_comment": "Additions-only sha256 fingerprints of the hand-typed labels and the oracle that reads them. A path is relative to the repository root and posix; the fingerprint is sha256 of the file's bytes. Adding a file appends a line; changing or removing a recorded file is refused in place (that is a label edit and the rule is the label is never edited). Record lines with tools/update_label_ledger.py in the same commit as the change that caused them.",
  "files": {
    "emailextract/evals/gates.py": "<sha256>",
    "emailextract/evals/l1.py": "<sha256>",
    "emailextract/evals/labels.py": "<sha256>",
    "emailextract/evals/falsify.py": "<sha256>",
    "tests/support/fake_store.py": "<sha256>",
    "tests/support/sidecar_copy.py": "<sha256>",
    "tests/support/timeline_ref.py": "<sha256>",
    "tests/support/stdlib_scanner.py": "<sha256>",
    "fixtures/generated/plain_simple.expected.json": "<sha256>"
  }
}
```

**What it covers** (every file whose bytes are a *label* or the *oracle over labels*):

1. every committed sidecar `*.expected.json` under `fixtures/**` (the label corpus);
2. every file under `tests/support/**` (the independent checkers, the fake store, the sidecar-copy
   helper);
3. every file under `emailextract/evals/**` (the oracle, the gates, the falsifiability catalogue, the
   metrics CLI).

**The additions-only rule.** `tools/update_label_ledger.py` **appends** a line for a file not yet
recorded (and only for a file that exists); it **refuses** to write when a *recorded* file's bytes differ
from its fingerprint, and it **refuses** when a recorded file is gone. So a turn that edits a gate or a
sidecar cannot record its way out of it: the remedy is a **new file**, or an explicit, owner-approved
ledger change in the same commit as the edit and named in the turn prompt's allow-list.

**Failure messages** (mirroring the behaviour ledger's, so a reader sees the same voice):

- a recorded file's bytes moved:
  `label_ledger: fixtures/generated/plain_simple.expected.json changed (recorded <a>, found <b>) -- a
  label is never edited; if this is a deliberate oracle change, it needs an allow-list entry and the
  ledger updated in the same commit`;
- a recorded file is missing:
  `label_ledger: tests/support/timeline_ref.py is recorded but not present -- a label or a gate was
  removed, which is a change, not a cleanup`;
- a new, unrecorded file under a covered path:
  `label_ledger: fixtures/raw/new_case.expected.json is a new label and is not recorded -- run
  tools/update_label_ledger.py in this commit`;
- the test form: `python -m pytest tests/test_label_ledger.py` and
  `python tools/update_label_ledger.py --check` both exit **1** on any of the above.

**How a new file is added.** A turn creates the file, then runs `tools/update_label_ledger.py` (which
appends its fingerprint) **in the same commit**. A file created but not recorded is the "unrecorded"
failure above; so is a file recorded with a different fingerprint.

## (b) The pinned `FACTS` ledger — `tests/ledger/facts_ledger.json`

The spec's exit criterion is that the **declared phase-1 fact-id list is pinned** and the **deferred set
is a closed list, empty by default**. Both live here:

```json
{
  "_comment": "The declared facts of Phase 1 and the closed deferred set. 'phase1' is the exact set of fact ids whose FACTS phase is 1; 'deferred' is the closed list of fact ids deliberately filed at a later phase than 1 (empty by default). A change to a fact's phase in emailextract/evals/l1.py fails tests/test_facts_ledger.py unless this file changes in the same commit.",
  "phase1": [
    "document.axes", "headers.projection", "headers.addresses", "headers.date",
    "headers.decoded", "headers.parameters", "body.text", "body.alternative_group",
    "body.selection", "body.html_spans", "body.cid_refs", "body.plain_effectively_empty",
    "body.quote_boundaries", "body.view_levels", "attach.manifest", "attach.types",
    "attach.filename", "attach.decorative", "attach.cid_use", "gaps.later"
  ],
  "deferred": []
}
```

**The rule:** `tests/test_facts_ledger.py` compares `emailextract/evals/l1.py`'s `FACT_PHASES` against
this file and fails, naming the id, unless they agree. So:

- adding a phase-1 fact in `l1.py` without listing it here fails;
- **moving a fact's phase to dodge a coverage obligation** (the gameable draft) fails, because the
  phase-1 set changed while the ledger did not;
- `deferred` is a **closed list** and empty by default: a fact is deferred by putting its id here, and
  the coverage floor (below) is required for every id in `phase1`, never for a deferred one. There is no
  `phase 1.5`.

`phase1`'s twenty ids are exactly `docs/design/phase1-facts.md`'s table.

**The coverage floor.** `tests/test_facts_coverage.py` (Turn 1.10) asserts, for every id in
`phase1`, that **(i)** at least `floor` committed sidecars carry it, and **(ii)** at least one of those
carries a **non-trivial, non-empty** value. The floors are the table's in `docs/design/phase1-facts.md`;
they are read from a `FLOORS` mapping in that test (kept beside the ids so a floor and an id move
together). A fact labelled on one fixture only fails; a fact never labelled fails.

## (c) The `benign` sidecar flag

`labels.load_sidecar`'s `OPTIONAL_KEYS` gains exactly one entry, `benign`, so a sidecar may be:

```json
{ "fixture": "plain_simple.eml", "labels_provenance": "spec",
  "benign": { "reason_id": "no_quote_expected" },
  "facts": { "...": { "phase": 0, "value": 0 } } }
```

- **Additions-only.** The flag may only be **added to a new sidecar**. Because the label ledger is
  additions-only, an existing sidecar cannot gain the flag without its bytes changing -- which is
  refused. A fixture that was not flagged benign when typed stays not-flagged.
- **`reason_id` is a closed id** from `{"no_attachment_expected", "no_quote_expected",
  "headers_only_by_design", "known_ambiguous_bytes"}`. The id is what makes the exclusion auditable: the
  exit criterion says "on every benign fixture the stdlib scanner's three comparisons agree and a planted
  defect makes each fail", and the reason id names *why* this fixture is expected to be clean rather than
  quietly skipping it. An unknown `reason_id` is a `LabelError` at load, exactly as an unknown
  `labels_provenance` is today.
- A **non-benign** sidecar is the default; its absence is not an assertion of anything.

## (d) The per-turn prompt ALLOW-LIST and the label-leak test

**The allow-list template.** Every Phase 1 turn prompt carries one fenced block, and nothing else is
meant to be touched by that turn:

```
```allow-list turn=1.1
docs/design/phase1-turn-declarations.md
docs/design/phase1-build-spec.md
emailextract/headers.py
emailextract/rfc2047.py
tests/test_headers.py
tests/support/stdlib_scanner.py
tests/ledger/label_ledger.json
```
```

- The paths are repo-root-relative, posix, and a directory entry (ending `/`) names a whole subtree.
- **After the fixtures turns** (from Turn 1.1 onward) the allow-list **excludes `fixtures/**` and
  `*.expected.json` entirely**: a rule may not be written from the bytes the agent just read. The fixtures
  turns (1.0c) are the only turns whose allow-list names them, and they run **before** any rule code.
- A gate or an oracle edit (`emailextract/evals/**`, `tests/support/**`) needs its path named
  explicitly, so the extension of the label ledger to those paths (rule g) can never be a silent edit.

**The label-leak test** (`tests/test_label_leak.py`, Turn 1.0b) is the mechanical half the allow-list
cannot be: it scans every file under `emailextract/**` and asserts that **no string literal names a
fixture path or a fixture filename**. Concretely, it reads the corpus file list from
`tests/ledger/corpus.json` (all versions, stem and basename), plus the literal substrings `fixtures/` and
`.expected.json`, and fails, naming the file and line, when any appears in `emailextract/**`.
`.eml`/`.msg` extensions alone are not scanned (a media type legitimately contains `.eml` in a docstring
elsewhere); the check is on the **names and paths** the fixture corpus actually uses. This is the guard
against "a parser rule written from the fixture bytes the agent just read" (the build spec's failure mode
2); the per-rule flip-one-input test is its per-rule companion.

## (e) The declaration-and-collection mechanism

**Where a turn declares.** `docs/design/phase1-turn-declarations.md` (deliverable 6) holds one fenced
block per turn, in a machine-readable form:

```
```declaration turn=1.1
module: emailextract/headers.py
module: emailextract/rfc2047.py
test: tests/test_headers.py::test_header_fields_keep_ordinals_and_duplicate_identity
test: tests/test_headers.py::test_obs_fold_is_one_field
...
```
```

- one `module:` line per module created or changed by the turn (repo-relative posix path);
- one `test:` line per **new** test function, written as the full `pytest` node id
  `path::function` (the format `pytest --collect-only -q` prints for a plain function test);
- the block's `turn=` names the turn; the block is the turn's **ceiling** (the spec's per-turn test
  ceiling: `<= 40`, `<= 25` for the quote turns).

**The test that diffs it** (`tests/test_turn_declarations.py`, Turn 1.0b): it runs
`python -m pytest --collect-only -q` in a subprocess, parses the node ids, and asserts

1. **every declared `test:` id is collected** (a declared-but-absent test fails, so a declaration cannot
   over-promise); and
2. **every collected id that is not in the frozen Phase 0 baseline is declared** (an undeclared new test
   fails, so a turn cannot add a test it did not declare).

The **Phase 0 baseline** is a literal list of the node ids collected at the moment the test is written
(Turn 1.0b); it is frozen there and never edited. The two rules together make the declaration binding in
both directions, which is what "a rule without a mechanism is dropped" (operating rule 1) means. The
`module:` lines are checked the same way but weakly (the file exists); the strong check is on the tests,
because that is what a turn is tempted to slip in.

**Pre-declared stop point.** Each turn's block ends with a `stop:` line naming where the turn stops and
reports rather than pushing past (the spec's turn table: 1.1 after headers/folds/raw spans; 1.5 after
`htmltree.py` and the node-to-span map, before selection and the cid set). The `stop:` line is not
enforced by a test -- it is the boundary the prompt restates -- but it is part of the declaration so a
reviewer compares it against the diff.

## (f) The committed final report

**Path:** `docs/phase1-report.md`, committed as the **last** artifact of Turn 1.10 (the phase's close).

**Required sections** (the test below checks the headings are present and each has non-empty body text):

1. `## What was built` -- the modules, the turns, and the version bumps with their reasons.
2. `## Named resolutions` -- every ambiguity resolved, each with the **test id** that pins it (the
   debate's replacement for "every ambiguity resolved", which is unverifiable).
3. `## Coverage` -- the per-(fact x phase) coverage table, with the floors and the observed counts.
4. `## Gap gate` -- every Phase 1 gap id with its mutation case and the fixture that proves it.
5. `## Label-versus-parser findings` -- every disagreement between a typed label and the parser, with
   the failing test id and the bytes (a finding is never resolved by editing the label, decision 12).
6. `## Licences` -- every dependency and its licence; the no-GPL statement.
7. `## Not done` -- what Phase 1 deliberately left to a later phase.

**The test that checks it** (`tests/test_phase1_report.py`, Turn 1.10) reads the file, asserts each of
the seven headings is present **exactly once** and that the text under each (up to the next heading) is
non-empty, and fails naming the missing or empty section. It does not judge the *content* -- that is the
owner's review -- only that the report is a real report, not a stub.

## `tools/runboth.py`

**What it does.** Runs one command under **both pinned interpreters** and reports both, so "green on both"
is a single action rather than a habit (operating rule 2). The two interpreters:

1. **primary:** `py -V:Astral/CPython3.11.15` (the machine-specific selector the project pins);
2. **fallback:** when that selector is absent (a machine without the Astral build, or a CI image), the
   first Python 3.11 on `PATH` -- resolved by asking each candidate for `sys.version_info` and taking the
   first that reports 3.11. If neither exists, `runboth.py` **exits 2** and prints
   `runboth: no CPython 3.11 found (tried py -V:Astral/CPython3.11.15 and PATH) -- recording-only run
   skipped`; it never silently runs 3.14 twice and calls it "both".
3. The **current** interpreter is the 3.14 side (the one the project runs under), recorded by version.

**What it prints.** For each interpreter, in order:

- the **interpreter line** (`CPython 3.14.3 (<sys.executable>)`, `CPython 3.11.15 (py -V:...)`) and the
  **source** of the 3.11 selection (`pinned selector` or `PATH fallback`);
- the command's **combined stdout+stderr**, verbatim;
- the **sha256 of that output** (rule 7: a measured number carries the command and a hash of its output);
- a one-line **per-interpreter verdict** (`ok` / `exit 1` / `timeout`).

Finally it prints a **summary line** and the **cross-interpreter verdict**: whether the two outputs are
**byte-identical**. A difference is **printed and reported, never hidden** (the design's rule for a
cross-interpreter difference) -- and, per the exit criteria, the fingerprints that are *required* to be
identical (the ledger fingerprints over this package's own scanner) are asserted identical by their own
test, not by `runboth.py`.

**Exit code:** `0` iff **both interpreters exit 0** and the required-identical output matched; `1` if
either interpreter's command exits non-zero; `2` if a second interpreter could not be found. It never
rewrites or filters a command's output, so a caller can hash what it printed.

## Turn 1.0b's implementation checklist (the exact brief)

- `tools/update_label_ledger.py` + `tests/test_label_ledger.py`, over the three covered path sets, with
  the four failure messages above.
- `tests/ledger/label_ledger.json` seeded with every current `*.expected.json`, `tests/support/**` and
  `emailextract/evals/**` file's fingerprint **as they are at the end of Turn 1.0b**.
- `tests/ledger/facts_ledger.json` with the twenty `phase1` ids and `deferred: []`; plus
  `tests/test_facts_ledger.py` comparing it to `FACT_PHASES`.
- `benign` added to `labels.OPTIONAL_KEYS` with its closed `reason_id` set and a `LabelError` on an
  unknown id (and the structure test for it).
- `tests/test_turn_declarations.py` with the frozen Phase 0 baseline and the two-direction diff.
- `tests/test_label_leak.py`.
- `tools/runboth.py`.
- `docs/design/phase1-turn-declarations.md` populated (declarations 1.0b to 1.10; see deliverable 6).

Nothing above is built in Turn 1.0a: this turn only fixes the shapes.
