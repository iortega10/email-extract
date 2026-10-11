# Turn 1b.0a-fix: four corrections to the Phase 1b documents (documents only)

Status: brief for one small build turn. Author: reviewer session, 2026-10-11. Builder: hearth. Builds on the
uncommitted Turn 1b.0a work in `C:\Users\ivan_\App_repos\email-extract` (the documents under `docs/design/`, the
design revision 4, the registry and the one test edit; baseline **2004 passed, 2 skipped**). Run hearth in that
directory, fresh session, DeepSeek Pro with the 400,000-token window (`HEARTH_MODEL=deepseek-v4-pro
HEARTH_CONTEXT_WINDOW_TOKENS=400000 HEARTH_STREAM_IDLE_TIMEOUT_SECONDS=600 HEARTH_REQUEST_TIMEOUT_SECONDS=600
HEARTH_MAX_TOKENS=16384`, key from the environment). Keep tool calls small. **Do not commit.** **Documents only**:
no Python, no tests, no fixtures, no sidecars, no JSON ledgers. The one exception already made is
`tests/test_phase0_gaps.py` (85 -> 88); do not touch any other test. Do not edit `phase1b-build-spec.md` or
`phase1b-debate.md` (the reviewer edits the spec). No real or employer mail; nothing outside the repo.

The reviewer found these in the 1b.0a deliverables. Fix each in every document where it appears (grep, do not rely
on the section named), and list in the report each file and line range changed.

## 1. The library-scope tests must keep `olefile` banned (contract section 11, rows for `test_phase1_scope.py`)

`phase1b-contract.md` section 11 says the new modules "legitimately import `olefile`" and carves `olefile` out of
`BANNED_IMPORTS` and of `FORBIDDEN_NAME_PARTS`. That contradicts owner decisions O4 and O7 and the design
revision 4: **`emailextract/` never imports `olefile`** (it is a tests-and-tools oracle and a `[dev]` extra only).

Rewrite those rows so that:
- only the **module names** that the Phase 1b library legitimately adds (`cfb`, `mapi`, `msgcontainer`, and the
  function-name fragments a real reader now needs, for example `read_msg`/`msg_reader` if and only if the build really
  adds such names; justify each) are carved out of the scope pins;
- `olefile` **stays** in `BANNED_IMPORTS`, in `FORBIDDEN_NAME_PARTS` where it is today, and in the import-probe
  `BLOCKED` set, for the library (`emailextract/`); the only thing that changes is that `tests/` and `tools/` may
  import it, which the scope test already does not scan;
- the `test_olefile_is_not_a_declared_dependency` row stays as written (it flips to "olefile is declared, under
  `[dev]` only, and never under runtime dependencies");
- every other document that repeats the carve-out (`phase1b-ledgers.md`, `phase1b-facts.md`, `phase1b-fixtures.md`,
  the design revision 4, the `phase1b-turn-declarations`-style sections) says the same thing. State the rule once, in
  one sentence, in the contract: "the library never imports `olefile`; only `tests/` and `tools/` do".

## 2. Do not persist virtual offsets (contract sections 7 and 8 point 7; wherever `SpanRow` is described)

`SpanRow` carries `virtual_offset` and `virtual_len`, and sections 7 and 8 (point 7) say the store persists the span
table. The Phase 1b spec (Turn 1b.0b, experiment E8: "no virtual offset persisted") and constraint C2 say the opposite:
a persisted virtual offset makes stored bytes depend on the projection's framing length.

Decide and document, in the contract, **one** of the following, with the reason, and make every document agree:
- **(recommended)** the persisted table is the **source-only** form: the same rows without `virtual_offset` and
  `virtual_len` (name the persisted shape, for example `PersistedSpanRow`, and list its fields); the virtual offsets
  are recomputed deterministically from the CFB bytes and `MSG_PROJECTION_VERSION` whenever they are needed, and a
  test declared for Turn 1b.5/1b.1 asserts that the recomputation reproduces the same source-only table; or
- keep the virtual columns in the store and state precisely why that does not violate C2 (which identities or
  citations could still depend on them), and add the test that proves it.
Also state in the golden section (10) that the store artifact for a `cfb_msg` document is covered by this rule.

## 3. Describe the golden's permitted diff exactly (contract section 10)

Section 10 says that after the schema bump "every measured value (..., the store artifact bytes, ...) is
byte-identical". But the **document** artifact embeds the serialized `EmailDocument`, which gains the
`"stream_ref": null` keys and a new `output_schema_version`; and the store's keys include the schema version. Rewrite
the passage and its test description so that it distinguishes:
- the **walk artifact** (the `WalkResult`: no records, no schema version in its bytes): byte-identical;
- the **document artifact**: differs from the 1b.0c golden by exactly the `output_schema_version` value and one
  `"stream_ref": null` per `PartRecord`/`HeaderField`, nothing else;
- the **store keys/paths** that include `OUTPUT_SCHEMA_VERSION`: move by exactly that version string;
- `ParseResult`, `CapRecord` values, `container_hash`, every `part_id`, every `sha256` and every span: byte-identical.
Open the store code (`store.py`) to confirm which artifact embeds what before you write it, and mark anything you did
not verify "(unverified)".

## 4. The change list must include the one test already edited (contract section 11, and the report)

Hearth edited `tests/test_phase0_gaps.py::test_the_registry_in_force_is_85_ids_and_the_prune_holds` (the literal 85
-> 88, forced because the registry document gained three ids) although the 1b.0a brief said to stop and report
instead. The edit is correct and stays, but section 11 lists that test under "not on the change list (so a failure
there is a defect)" while the test **was** edited. Move it into the "must change" table (with the reason: the
registry in force grows by exactly the three `msg.*` ids; the function keeps `85` in its name because it is in the
frozen baseline of `test_turn_declarations.py`, so the name stays), keep the "list is complete" claim true, and
correct the count in the resolution list (R12 says 17; count the table rows and state the real number, including
this test).

## Minor corrections

- `email-extraction-design.md`, the revision-4 D1 amendment: replace the garbled phrase "credit-card-grade hostile
  check, olefile returned ..." with plain wording ("on a hostile-input check, olefile returned ..."). Grep the other
  revision-4 text for similar odd phrases and fix any you find.
- Contract section 1 (X), the worked JSON: the example shows `"schema_version": "7"` next to
  `OUTPUT_SCHEMA_VERSION` "5" -> "6". Open the strict codec in `docextract-core` (or `model.record_to_bytes`) and say
  what that `"schema_version"` field is (the codec's own number, not `OUTPUT_SCHEMA_VERSION`); correct the example or
  add one sentence so a reader does not confuse the two.
- If the three documents you did not rewrite (`phase1b-fixtures.md`, `phase1b-ledgers.md`, `phase1b-probes.md`) repeat
  any of the four corrections above, fix them there too.

## Checks and report

- `python -m pytest -q` before and after: the same 2004 passed, 2 skipped; the only test file changed in the whole
  1b.0a work remains `tests/test_phase0_gaps.py`.
- `git status`: only `docs/design/` files and that one test file.
- Every file:line you cite was opened, not recalled.
- **Report:** per correction, the files and line ranges changed; the choice you made in correction 2 and why; the
  real row count for correction 4; anything the evidence did not settle, as an open question for the reviewer rather
  than a silent pick. Leave the tree uncommitted.
