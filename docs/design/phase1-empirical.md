# Phase 1 empirical constants

One place for every constant Phase 1 **measures** or **fixes**, so a later turn appends
here rather than scattering numbers through the code and the docs. Every entry says
plainly whether its number is **measured** (a command produced it and its output is
recorded) or **reasoned** (the design owner approved it; it is not measured). Operating
rule 7: a measured number carries the command that produced it; anything not re-runnable
is marked "verify empirically" and is not a gate input.

This file is started in **Turn 1.0d**; later turns append their own sections.

## `Limits.untrusted()` — reasoned, not measured

The recommended untrusted default cap set (decision 10,
`emailextract/parse.py`):

| field | value | bytes |
|---|---|---|
| `max_input_bytes` | 64 MiB | 67 108 864 |
| `max_depth` | 16 | — |
| `max_parts` | 1000 | — |
| `max_header_bytes` | 256 KiB | 262 144 |
| `max_decoded_part_bytes` | 32 MiB | 33 554 432 |
| `max_decoded_total_bytes` | 128 MiB | 134 217 728 |
| `max_work_units_per_input_byte` | 64 | — |

**Reasoned, not measured.** No corpus measurement produced these numbers; the design
owner approved them as the recommended defaults. The reasoning: a real message the size of
the largest fixtures is orders of magnitude below 64 MiB, so the input cap is generous
enough never to bite a genuine message while still bounding a hostile one; 16-deep
multipart nesting and 1000 parts exceed any producer's legitimate tree (real mail nests a
handful deep) by a wide margin; the per-part and total decoded caps bound the base64/QP
expansion of a small input to a few times its size; and `max_work_units_per_input_byte`
is a per-input-byte **work** budget (never a time) for the encoded-word and base64
expansions that a later turn asserts against.

**Enforcement is staged.** Turn 1.0d enforces **only** `max_input_bytes` (`parse` checks
it before any sniff). The walker and later stages enforce the rest in the turns that build
them; until then the other fields are carried but not read. The cap fixtures' sidecars
never assert a status: a `Limits` is a parameter of the test, not of the label.

## The HTML parser decision (Turn 1.0d)

Measured by `tools/html_experiment.py`; recorded in full in
`docs/design/html-parser-experiment.md`. Both runs:

```
python tools/html_experiment.py --json                        # CPython 3.14.3
py -V:Astral/CPython3.11.15 tools/html_experiment.py --json   # CPython 3.11.15
```

* **Decision:** candidate **A** — the stdlib `html.parser` plus the own stack-based element
  tree. B (lxml) matches A on every *closed* quote container but, like A, lets an unclosed
  `<blockquote>` swallow the following text, so **neither is clean** and decision 1's named
  unclosed-container rule applies (gap `body.html_quote_rule_gap`).
* **Interpreters the runs used (recorded run inputs, measured):** CPython **3.14.3** and
  CPython **3.11.15**. Candidate A's per-input event/tree/projection hashes are
  **byte-identical** across the two.
* **The lxml wheel (measured, for candidate B only):** lxml **6.1.3.0** on libxml2
  **2.11.9**, identical under both interpreters. B is pinned by the wheel, not the
  interpreter, so the two-interpreter identity says nothing about libxml2.
* **Fingerprints:** the two JSON outputs' sha256 are
  `0aa5114256c157757efbe73ccde0c2786c857f9fd2366f8a2b0ddff652db49ea` (3.14.3) and
  `1a9b21e0f7f1b5cc85e2ae510bcc3205df12cb7f6f0fedc3bbe0bca9ab736657` (3.11.15); the
  per-input hashes are in the experiment document. A is identical on both; the outputs
  differ only in the recorded interpreter string.

**`HTMLTEXT_VERSION` (Turn 1.0d).** Because A was chosen, the key is
`1+htmlparser+<cpython-major.minor>+verbatim-non-style-script+recorded-not-closed`, built
at import from `sys.version_info[:2]` (`emailextract/versions.py`). The lxml wheel is
**not** a key input, because the chosen candidate does not use it. The constant ships
symbolically only (`htmltext.py` is Turn 1.5) and the behavior ledger keys nothing by it.

## Turn 1.1 — the header stage, its live facts and the walker tolerance

**Measured, not reasoned.** Every number here is produced by a command run in Turn 1.1; the
command and its output are the record.

* **The L1 oracle now compares 30 more facts, all green.** Command:
  `python -m emailextract.evals`. Output (both interpreters identical):
  `L1 matched=777 mismatched=0 unmeasurable=0 unmodelled=0; not_yet: phase 1=155, phase 3=26`.
  Before this turn the gate was `matched=747`, `not_yet: phase 1=185, phase 3=26`; the 30
  newly-live sidecar facts are `headers.projection` (12 sidecars), `headers.decoded` (6),
  `headers.parameters` (6) and the live `gaps.later` rows (6).
* **The `parsed_value` column is partial by design.** `headers.projection` compares
  `(ordinal, name, raw_value, parsed_kind)` on every row and the parsed scalar only where a
  parser exists this turn. The counts of the deferred column, from
  `emailextract.evals.l1.deferral_counts()`:
  `headers.projection.address_list:1.2 = 25`, `headers.projection.date_time:1.3 = 12`. They
  are deferred **by name** (never computed with a stdlib parser, never silently skipped).
* **The walker tolerance is a versioned behaviour change.** `EMAIL_PARSER_VERSION` 1 to 2;
  the behaviour ledger appended five `walk` lines under the new key `2|2|corpus:N`
  (corpora 1 to 5); the `decode_chain` and `contracts` lines did not move. Command:
  `python tools/update_behavior_ledger.py` (and `--check` exits 0 on both interpreters).
  Only `leading_utf8_bom` (corpus 3 and later) and `mbox_from_line_at_zero` change what the
  walker emits, and by design their sidecars type only `container.sha256` /
  `container.size_bytes` at phase 0, so no frozen phase-0 label moves.
* **The stdlib scanner's disagreements are a closed catalogue.** Command:
  `python -m pytest tests/test_stdlib_header_scanner.py -q` (2 passed). Field-name/order
  disagreements occur only for `leading_utf8_bom` (shared BOM misreading), `malformed_mime`
  and `nul_in_header_name` (the package fails open, the stdlib stops at the malformed line),
  while `mbox_from_line_at_zero` / `lone_cr_in_header_region` agree but prove nothing (listed
  in the shared-misreading catalogue). The content-type tree disagrees only for
  `message/rfc822` nesting (2 fixtures, Phase 2 recursion) and the digest child's
  RFC 2046 5.1.5 default (`body.digest_default_not_applied`). The decoded values agree on
  every fixture with a valid word.
* **The fuzz loops are seeded and bounded.** `Random(11_1001)` / `Random(11_2047)` /
  `Random(11_2231)`; 600 header-region mutations and 1200 + 1200 decoder/parameter inputs.
  No defect found: the three functions never raised on mutated bytes.
