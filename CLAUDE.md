# email-extract -- CLAUDE.md

This file provides operating guidance to Claude Code when working in this repository.

## What this is

`email-extract` (import `emailextract`) extracts deterministic `.eml`/`.msg` email records.
Phase 0 builds the frozen contract layer and a skeleton walker; Phases 1a/1b/1c build the
eml walker, `.msg` reader and time reconciliation; threading/attachments land in later
phases. Each turn ends with **green pytest**.

Source of truth: `docs/design/email-extraction-design.md` (D1-D16) and
`docs/design/phase0-build-spec.md` (turn-by-turn). Where they conflict, the design doc wins.

## Build / test

```sh
pip install -e ../word-extract/docextract-core   # first local install only
pip install -e .
python -m pytest                                  # green is the gate
```

Run the single file under test with `python -m pytest tests/test_<name>.py -q`.

## Layout

- `emailextract/` -- `versions.py` (frozen constants), `model.py` (contracts), `timeevent.py`
  (D15 `TimeEvent`), `container.py` (the container-neutral interface, the `.eml` adapter and an
  in-memory fake), `ids.py` (content-addressed ids), `walk.py` (the one skeleton walker, over any
  container), `store.py` (the throwaway re-ingest store). There is deliberately no per-format
  walker: format-specific walkers would duplicate the measured rules.
- `tests/` -- hand-typed, one file per contract; `ground_truth/` + `check_ground_truth.py`
  verify fixtures (importance order: tests > fixtures > ground truth > docs).
- `fixtures/synthetic/` -- generated fixtures; `fixtures/real/` is git-ignored forever.
- `probes/`, `tools/` -- throwaway readers; probes print structure only.

## Conventions

- One dataclass = one contract; `frozen=True`; shared frozen constants in `versions.py`;
  `FileMaterial` is the word-extract-style input protocol (`size()` / `open_text()` /
  `read_bytes()`); tests always exercise it through `Path` and `memory_bytes`.
- Strict codec: versioned envelope `{"schema_version", "record"}` through
  `docextract_core.codec` (`to_json`/`from_json`, strict by default), unknown keys raise
  (`CodecError`); the envelope keeps the core's schema_version, and
  `timeevent`'s distinct version (`TIMEEVENT_SECTION_SCHEMA_VERSION`) means its shape
  freeze never bumps the record's.
- `status` is exactly nine members with a reason table; reason ids come from
  `docs/design/reason-ids.md`; never widen a type or enum to make a test pass.
- Never commit real email; no GPL dependency anywhere; license Apache-2.0.

## Before finishing a turn

1. `python -m pytest` green (full suite, not just the new file).
2. `git diff` review -- no junk, no stray prints, no accidental files.
3. Report: files created/changed, full test output, ambiguities resolved and why.
4. **Stop at the turn boundary.** Do not start the next turn.
