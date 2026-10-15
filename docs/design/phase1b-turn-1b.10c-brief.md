# Turn 1b.10c: `ingest_path` ingests a `.msg` -- the one-line defect found by the Phase 1b hostile run, and the tests that should have caught it

Status: brief for one small fix turn, before the `0.2.0` tag. Author: reviewer session, 2026-10-15. Builder: hearth. Builds on `1f91802`
(Turn 1b.10b committed). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session. **Do not commit and do not tag.**

**Pace this turn.** One production line and a set of tests. Iterate on the ingest tests; run the full suite once per interpreter at the end.

## What this turn is

Turn 1b.10b's hostile run found, and the reviewer reproduced, that **directory ingest of any `.msg` crashes**:

```
ingest_path(dir_with_a_msg, store, limits=Limits.untrusted())
  -> ingest._row_for -> ingest._container_for(raw, "cfb_msg")
  -> MsgContainer(memory_bytes(raw))
  -> TypeError: msgcontainer takes bytes, got MemoryMaterial     (msgcontainer.py:465)
```

`emailextract/ingest.py:256` passes `memory_bytes(raw)` (a `MemoryMaterial`) to `MsgContainer`, whose `__init__` takes plain `bytes` and
raises `TypeError` for anything else. `EmlContainer` accepts both (`container._material_of`), which is why the `.eml` path works and the
line was written that way. The defect has been in the tree since Turn 1b.5 (`fbdbe84`, "parse/ingest wired"). **No test ever ingested a
`.msg` through `ingest_path`**: `tests/test_ingest.py`'s only `.msg` case (`cfb.msg`) is refused by `parse` as `not_a_message` **before**
a container is built, and 1b.9/1b.10b ingested through `store_document` directly. `ingest_path` is the README's headline entry point
(`README.md:108-116`, `:256`), so `0.2.0` must not ship with it unable to read the format `0.2.0` adds.

This turn fixes the call site, proves it end to end, finds out whether anything **else** was hiding behind the same crash, and corrects
the Phase 1b report and CHANGELOG that currently record it as an open finding.

Read first: `emailextract/ingest.py` (`_row_for`, `_container_for`, `ingest_path`), `emailextract/container.py` (`memory_bytes`,
`_material_of`, `EmlContainer`), `emailextract/msgcontainer.py` (`MsgContainer.__init__`, `read_bytes`), `tests/test_ingest.py`,
`tests/test_phase1b_hostile_run.py` (the lines that pin the defect: the `INGEST_MSG_DEFECT` constant, the comment at ~63, the handler at
~155), `docs/phase1b-report.md` (the sentence at ~195 and the table row at ~111), `CHANGELOG.md` (the `0.2.0` entry),
`phase1b-ledgers.md` (the 1b.10b outcome note's finding).

## Decisions (reviewer's; the owner may overrule; say so with evidence rather than building around one)

**D1. Fix the call site, not the container's contract.** Change `_container_for` so the `cfb_msg` branch hands `MsgContainer` the plain
`bytes` it asks for (`MsgContainer(raw)`), leaving `EmlContainer(memory_bytes(raw))` as is. Do **not** widen `MsgContainer.__init__` to
accept `MemoryMaterial`/`Path` (that would change a module whose behaviour is frozen by the three `msg_*` ledger components and by the
walk's byte-identity proofs; if you believe widening is the right fix, say so and **stop**, do not do it). Show that the change moves
no ledger fingerprint (`tools/update_behavior_ledger.py --check`) and no `.eml` golden byte. Remove an import only if it becomes unused;
keep the diff to the line (and the import) and say so.

**D2. Prove it end to end before and after.** First reproduce the failure as a **failing test** (it must fail on `1f91802` with exactly
the `TypeError` above), then fix, then show it green. The new tests (declare the names in the note; put them in a new
`tests/test_ingest_msg.py` unless `tests/test_ingest.py` is clearly the better home):
* `ingest_path` over a directory of **every committed readable `.msg`** (`fixtures/msg/*.msg`, excluding the fixtures `parse` refuses by
  design, which must instead be a **recorded skip with their named reason**, not an exception): each row is `WRITTEN` with a
  `container_hash` equal to `sha256` of the file bytes, or `SKIPPED` with a closed reason id; **none raises**; the document store holds
  exactly one document per `WRITTEN` row and each re-reads (`read_document`/the store's loader) to an `EmailDocument` whose
  `container_kind` is `cfb_msg` and whose `container_hash` matches its row;
* **re-ingest is a no-op**: a second `ingest_path` over the same directory writes nothing (`HIT` rows, store bytes unchanged, manifest
  bytes unchanged), as the README promises (`README.md:256`);
* **a mixed directory** (`.eml` fixtures and `.msg` fixtures together, including the cross-container pair's `.msg` half and an `.eml`
  built the way `pair_eml_bytes` builds it): both kinds ingest, the manifest is ordered deterministically, and the `.eml` documents'
  bytes are **identical** to what they were ingested alone (the `.msg` presence changes nothing about an `.eml`);
* **the same bytes under two `PYTHONHASHSEED`s and on both interpreters** give a byte-identical manifest and byte-identical document
  artifacts for the `.msg` set (extend the digest pattern `tests/test_ingest.py`'s `EXPECTED_DIGEST` test uses; type the **expected
  digest** only after reading the value from one interpreter, then require the other to match);
* **hostile `.msg` through `ingest_path`**: the hostile CFB fixtures and the test-built seeds the 1b.10b hostile-run file already builds
  (reuse its builders, do not copy them), written into a temp directory, give a document or a **named** `SKIPPED` reason per file, never
  an exception, within `Limits.untrusted()`; and an oversized file is `SKIPPED` with `file_over_cap` before any container is built
  (`ingest._row_for` checks `max_input_bytes` first; pin it for a `.msg`).

**D3. Find what the crash was hiding.** Once the `TypeError` is gone, `ingest_path` runs the **whole** pipeline over a `.msg` for the first
time through its own entry point. Run **every committed `.msg`** through it and report **anything else that surfaces** (a different
exception, a nondeterministic store key, a skipped row whose reason is wrong, a document that fails to re-read, a manifest row whose
`container_hash` is not the file's hash). Each is a **finding** for the owner: report it with the input, the traceback or the two values,
and **do not fix** anything beyond D1's line unless it is the same root cause in a second call site. Grep first: the only other
`MsgContainer(` constructions in the tree are `evals/l1.py:1592` and `tools/behavior_ledger.py:603`, and both pass bytes; say that
you checked, and check `tools/` and `emailextract/__init__.py`'s public helpers for any other path that builds a container from
`memory_bytes`.

**D4. Flip the test that pins the defect, and correct the record.** `tests/test_phase1b_hostile_run.py` currently **pins the raise**
(`INGEST_MSG_DEFECT`, the comment at ~63, the `except TypeError` at ~155) so that the run stays green around a known crash. After the
fix that pin is wrong: replace it so the hostile run exercises **`ingest_path`** (not `store_document` around it) for the `.msg`
inventory, and so a reintroduced `TypeError` fails it. Keep the inventory's other expectations and its inventory table's structure;
recompute the table's numbers by running it and say which rows changed. Then correct, **in place and minimally**:
`docs/phase1b-report.md` (the table row at ~111 and the open-finding paragraph at ~195: state that the finding was **resolved in Turn
1b.10c**, with the root cause in one sentence, the fix, and the test ids; do not rewrite history or other sections), `CHANGELOG.md`'s
`0.2.0` entry (a `Fixed`/notes line is enough: `ingest_path` ingests `.msg`), and `tests/test_phase1b_report.py` **only if** it asserts the
old finding's wording (name the line). If `README.md` says anything about `.msg` and ingest that is now untrue or newly true, correct it
and list the lines.

## Order of work

1. Write the failing end-to-end test; run it on the current tree and capture the exact `TypeError` (the note records it).
2. Grep for any other call site (D3) before editing.
3. The one-line fix (D1); the new tests green; the ledger and golden checks.
4. D3's run over every `.msg`; collect findings.
5. D4: flip the pinned expectation, recompute the inventory, correct the report/CHANGELOG.
6. Full suites on both interpreters, `--check` tools, mutations, the note.

## Mutations (each must make a named test fail; run, restore, report)

(1) Reintroduce `MsgContainer(memory_bytes(raw))` -- the new directory-ingest test **and** the flipped hostile-run test fail. (2) Make
`_container_for` build an `EmlContainer` for a `cfb_msg` kind -- the `container_kind == cfb_msg` assertion fails. (3) Skip the
`max_input_bytes` check for a `.msg` -- the oversize test fails. (4) Let a second ingest rewrite a `.msg` document -- the re-ingest
no-op test fails.

## Allow-list

`emailextract/ingest.py` (the `cfb_msg` branch of `_container_for`, and the import only if it becomes unused), `tests/test_ingest_msg.py`
(new) or `tests/test_ingest.py` (added cases only), `tests/test_phase1b_hostile_run.py` (the flip, D4), `tests/test_phase1b_report.py`
(only if it pins the old wording), `tests/test_turn_declarations.py` (declare the new tests: `BUILT_TURNS` gains `"1b.10c"`),
`docs/phase1b-report.md`, `CHANGELOG.md`, `README.md` (only if untrue), `docs/design/phase1b-ledgers.md` (a `declaration turn=1b.10c`
block and the outcome note), `docs/design/phase1-turn-declarations.md` (only if the mirror is kept), `tests/ledger/label_ledger.json`
(re-recorded **only** if `update_label_ledger --check` says a recorded file changed). **Not**: `msgcontainer.py`, `container.py`,
`cfb.py`, `mapi.py`, `rtf.py`, `attach.py`, `walk.py`, `assemble.py`, `parse.py`, `store.py`, `model.py`, `versions.py`, `pyproject.toml`
(`0.2.0` stays), `evals/**`, `tools/**`, `tests/ledger/behavior_ledger.json`, `corpus.json`, `facts_ledger.json`, the `.eml` golden, any
fixture or sidecar, `docs/releasing.md`, `CLAUDE.md`. No new `.msg`, `.eml` or sidecar.

## What must NOT be done

No change to `MsgContainer`'s contract or any reader/projection behaviour (D1). No version bump, ledger line, schema change or golden
change. No fix beyond the one call site unless it is the same root cause (D3): everything else is a reported finding. No weakening or
deletion of any existing assertion (the flipped pin in D4 is replaced by a stronger one, not removed). No `try/except TypeError` to
make a test pass. No tag, no commit, and no edit to `docs/releasing.md` (the owner's release checklist from 1b.10b stands).

## Checks and report

1. Full suite green on the primary interpreter and on 3.11; the masked/no-extra run is **not** applicable to email-extract.
2. All five `--check` tools and `python -m emailextract.evals` exit 0 on both; `git diff` shows the golden, every ledger file except a
   possible `label_ledger.json` re-record, and `versions.py` untouched.
3. The outcome note in `phase1b-ledgers.md`: the failing-first output (exact `TypeError`), the call-site grep (D3), the one-line diff, the
   new tests and what each pins, the D3 run's findings (or "none", stated as a result), the hostile-run inventory before/after, the
   report/CHANGELOG edits (lines), the four mutations, and every existing test edited and why.
4. What the owner still decides before tagging: the `docs/releasing.md` `0.1.0` lines (31-32, 37, 41), the commit, the `v0.2.0` tag,
   plus the standing items (the two unmet floors, `msg.rtf`, the pair's committed `.eml`, the `MELA` CRC leniency, `CODEPAGES` width, P1-P6
   on real mail).

Stop at the turn boundary: `ingest_path` ingests every committed `.msg` or records a named skip, re-ingest is a no-op, the hostile run
goes through `ingest_path`, the report and CHANGELOG say the finding was fixed, and nothing is committed or tagged.
