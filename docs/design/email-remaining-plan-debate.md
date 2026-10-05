# Remaining Phase 1 plan: the debate with the hearth-cli model (outcome of five rounds)

Status: **the outcome of a read-only design debate about the turns still to run in Phase 1.** It edits no
spec, no declaration and no code; it is the input to the next revision of
`docs/design/phase1-turn-declarations.md` and to the owner's decisions. The design
(`docs/design/email-extraction-design.md`) wins on any conflict.

Method. Claude (this file's author) and the hearth-cli model (backing model is whatever the project
resolves; not assumed) argued five live rounds through `hearth --json`, hearth session `s45bfd20a` in
`email-extract/.hearth/sessions/`. Hearth was read-only: one `gate_paused` fired (round 3: it tried a plan
tool; auto-denied; nothing changed). Hearth read the repo and cited code; where this document gives a
`file:line` it is hearth's reading, and **was not re-verified by Claude** unless it says so. Claude's tree
had uncommitted in-flight work (catalogue, Turn 1.8) which neither side touched. **No real or employer mail
was opened or described**, `Downloads` was not touched, and nothing below is mail content: every
statement is design-level or aggregate.

## 0. Headline outcomes

1. **No thin 1.9 shell before 1.6.** The quote records already exist (`QuoteBoundary` `model.py:688`,
   `ViewLevel` `:730`); what is missing is only the holder on the document. Land the holder in 1.9 (one
   `OUTPUT_SCHEMA_VERSION` bump, after 1.7 has shown the folding shape).
2. **A new turn 1.5c (limits) is needed and is not in the table.** Of seven `Limits.untrusted()` fields only
   two do anything (section 4, item 5).
3. **The catalogue has a hole the owner review must see**: no fixture has a hard-wrapped `On ... wrote:`
   attribution (section 3). It is a row to add before the gate closes.
4. **1.4b (flowed reflow) is not built.** Quote detection needs only per-physical-line depth; joining
   would edit a frozen sidecar and cannot give a byte span anyway.
5. **The only breakers of common-mode quote error are producer-generated fixtures and the structure
   probe**; a second typing and a differential oracle are weaker than they look (section 6).
6. **Split 1.10** into 1.10a (do the corpus and gates agree) and 1.10b (does hostile input behave).
7. **Declared order must change in the document**: the old table runs 1.6, 1.7, 1.8; the agreed order
   below runs 1.8 earlier (it is free, nothing depends either way, but it must be declared).

## 1. Agreed order and per-turn exit criteria

| # | turn | exit criterion |
|---|---|---|
| 0 | **quote catalogue** (in flight) | 26 + new rows each carry expected `(rule_id, kind, ordinal, level)`; owner-reviewed and signed before any rule is written; the rule-writing agent has not seen the labels; includes the hard-wrap row and the producer-generated rows if available |
| 1 | **1.5c limits** (new, declared) | `Limits` threaded into `walk` and the stages; each cap emits an existing `skipped(<cap>_cap)` status plus a `CapRecord` (statuses `model.py:246-250`); no new reason id; per-field-value work limit renamed; runs while the owner reviews the catalogue |
| 2 | **1.8 attach** | declared 1.8 tests green; three magic not-computed reason ids registered; `absent` iff the part has no own body; decoded-part and total caps enforced here |
| 3 | **1.6 text quote rules** | declared tests green; 2-line hard-wrap join with its negative (3 lines not joined); read-only grouping for the attribution search only; single-pass scanner with a per-part step budget; 10 MB single-line and 100k `>` line cases |
| 4 | **1.7 DOM rules + resolution** | DOM rules and mixed-origin resolution green; disagreement observable in the oracle (section 3); `body.html_quote_rule_gap` for not-v1 shapes; a documented **emission shape** test pinning the L1 fact rows (`l1.py:679`, `:686`), not just the dataclasses |
| 5 | **1.9 assemble/ingest/store** | holder field on the document (one schema bump); sharpened `stop:` with the policies in section 5 and an ingest manifest |
| 6 | **1.10a corpus agreement** | every gap id has a mutation case; each fact meets its floor; scope test passes; committed golden projection hashes; report committed last |
| 7 | **1.10b hostile set** | socket guard fails loudly on any fetch; step-counter superlinearity test; filename test; seeded fuzz folded in unless it has its own corpus |

Commits stay serial: every turn is owner-committed before the next, and `versions.py` is on five turns'
allow-lists, so exactly one live bump at a time. `tools/make_fixtures.py` is in no declared allow-list; the
turn that edits it needs an explicit entry. Catalogue and 1.8 allow-lists are otherwise disjoint (1.8's
fixtures and sidecars already exist), so ordering is by commit, with fixture id ranges reserved up front.

## 2. Decisions on the owner's open items

"Owner" marks the ones that need the owner's explicit decision; "recommend" ones may be skipped.

| # | decision | needs owner? |
|---|---|---|
| 1 | Keep the review a hard gate. Review document per fixture: the raw message, the label in plain English, one predicted rule line; mark the 3 or so rows the design distrusts (flat Outlook block, NBSP/French separator, forward banner) and require an **answer** on those, not a nod. Report "owner flagged k of m rows" as a committed number the owner produces. Add the hard-wrap row. Second typing: **disputed** (section 7); Claude keeps it as a cheap typo check, hearth would cut it. Sealed canary rows were rejected by both after argument (section 7). | Owner (gate, hard-wrap row) |
| 2 | Apple attribution and Yahoo stay absent and raise `body.html_quote_rule_gap` until the owner confirms from the probe. | Owner |
| 3 | `.msg` stays the named error `cfb_msg_unsupported` (`parse.py:288-289, 311-312`). Do **not** add a magic prefix to `ParseResult`/`NamedError` (the reason id is the format tag; bytes persist on disk). Mitigation for the real hazard (unknown `.msg` share of the corpus): a per-run census counter in the ingest manifest. A later reader must be non-GPL. | Recommend |
| 4 | Three artefacts in `tests/ledger/facts_ledger.json`: (i) declared floors citing the design's named counts, (ii) an achieved-count regression ratchet, (iii) a list of facts with zero labelled rows (the real gap). Re-base at 1.10a is a **recorded, owner-signed ledger change in the same commit**, never an automatic move; floors never loosened after. Hearth's stricter reading is adopted. | Recommend |
| 5 | Audit and plan in section 4. Rename `max_work_units_per_input_byte` to a per-field-value name (clean rename, no schema bump: `Limits` is a call parameter, never serialised, `parse.py:121-138`), note that the 64 is not comparable across caps. | Owner (rename, defaults) |
| 6 | Accept: Phase 1 spans keep the projection that inserts nothing between blocks. Hearth's addition: the **source-offset gap must be recorded** so "nothing inserted" is distinguishable from "gap dropped". Phase 2: a separate analysis view **derived from the same tree** with block separators, mapped back to projection offsets via the existing zero-width-pre-image idiom (`text.py:44-47`). DOM rules stay pinned to the projection version; a projection change bumps `HTMLTEXT_VERSION` and forces a re-typing of committed DOM span labels. | Recommend |
| 7 | Accept as implemented (`dates.py:339-340`, `:96-104`, `:352-368`); the fact doc must state that `zone_state` + `offset` alone cannot tell a military letter from a literal `-0000`, and that the `raw` column disambiguates. | Recommend |
| 8 | Register before 1.8 freezes only the magic not-computed ids: `magic_part_skipped_cap`, `magic_body_undecodable`, `magic_body_encrypted`. Rule: `absent` iff the part has no own body (container node); a zero-length leaf is consulted and is `UNRECOGNIZED` (a value, not a reason); a cap-skipped or unreadable part is `unknown(reason)`. `part_empty` is dropped; `size_cap`/`decode_failed` are D6 status reasons and are not reused as TriValue reasons. The 2231 malformed escape and later-continuation charset stay in the gap ledger with a named id each. | Owner (new vocabulary) |
| 9 | Keep the status reasons `depth_cap`/`part_count_cap` (`htmltree.py:47-56`); do not register dotted ids (they would duplicate a D6 status). Make the **unit** and scope explicit on the cap record (elements vs parts) and split coverage stats by scope. | Recommend |
| 10 | 1.8 commits first, catalogue rebases onto it, reserved id ranges, serial `versions.py` bumps. | Recommend |
| 11 | See section 6: the probe is not integers only. | Owner (runs it) |

## 3. Quote design: the holes found

1. **Hard-wrapped attribution is unhandled and untested.** The rule is stated as a single line (design
   `:81`, build-spec `:128`, declarations `:487-500`), and all catalogue rows with an `On ...` line keep
   `wrote:` on one physical line (hearth). Bounded rule agreed: window `N = 2` physical lines, a named
   constant; line 1 begins `On ` (after optional `>` and spaces) with no ` wrote:`; the last line of the
   window ends with `wrote:`; a leading `>` on the continuation is stripped for the match and is **not** a
   depth fact and advances no ordinal; `N >= 3` is not joined and yields `body.no_boundary_found`, with a
   negative test.
2. **`>` depth** is defined as the count of `>` tokens separated by runs of ASCII SP/TAB only, so `> >`,
   `>  >`, `>\t>` and `>>` are all depth 2; NBSP does not count toward depth (it is literal text in QP
   bodies); an NBSP separator is accepted for **labels** after NFC only. Add rows for the spacing variants.
3. **Flowed (RFC 3676).** Depth only needs per-physical-line reads; a soft-joined line has one depth. 1.6
   counts depth on the stored, unstuffed, **unjoined** `body.text` and reports spans on physical lines.
   Any join is a read-only grouping used for the attribution search, never new span arithmetic
   (`text.py:61-65` forbids a second line model). The one flowed fixture pins `body.text` unjoined and
   `body.flowed_reflow_unresolved` in `gaps.later`, so a real reflow would relabel a frozen sidecar:
   **not built unless Phase 2 needs joined text as text.** Needs a new fixture: a flowed quoted line
   ending in a soft break and continuing at the same depth (today's flowed fixture has no quote).
4. **The disagreement predicate** (`view.quote_level_disagreement` iff prefix depth >= 1 and structural
   ordinal >= 1 and the ranks differ) is **complete in direction**: structural wins, so `>` text inside a
   non-quoted div resolves by depth and is silent and correct (design `:71-72`). Its flaw is that it is
   **unobservable**: `body.view_levels` has four columns and no disagreement (`l1.py:686-690`) and
   `ViewLevel.span` is mandatory in the model (`:742`) but dropped from the fact. Agreed: per-view bool;
   "prefix depth >= 1" means any line >= 1; disagreement means any span; add a fifth column to
   `body.view_levels`; `span` is the view-wide union (or marked record-only). A per-span fact only if a
   fixture justifies it.
5. **Signature / list-footer: cut variants, not the mechanism.** Both are frozen `BoundaryKind` members
   and are recorded at level 0 with no ordinal, so a false positive adds a spurious level-0 row, never
   promotes text to `quoted`. Keep one signature and one list-footer fixture; drop exotic localised
   list-footer variants if budget forces it.

## 4. Risk register (ranked) and the limits audit

| # | risk | note / mitigation |
|---|---|---|
| 1 | DOM spans coupled to the projection: committed DOM labels typed against one `HTMLTEXT_VERSION` can go silently wrong when `html.parser` moves while the suite stays green | commit golden `(fixture, locator, sha256)` rows plus `interpreter_label()` and a waiver path (section 8) |
| 2 | Limits unenforced; 1.6 then consumes unbounded hostile structure | turn 1.5c; a scheduling risk, not a difficulty risk |
| 3 | Common-mode quote errors (rules and labels from one reading, no real mail) | producer-generated fixtures and the structure probe (section 6) |
| 4 | Owner review fatigue / rubber-stamp on 26+ rows freezes a wrong label above the code | review-document design, distrust rows needing an answer, flagged-count |
| 5 | Flowed seam | contained by section 3 item 3 |
| 6 | Ledger/floor tautology: floor = achieved count ratifies whatever exists | three artefacts, never two; re-base owner-signed |
| 7 | Producer-fixture export leaking tenant, address or vendor blobs | never export from a work account (section 6) |
| 8 | `versions.py` bump contention (five turns) | serial commits; one live bump at a time |
| 9 | Per-stage projection versions not on the stored record: a consumer cannot tell which version produced a stored `body.text` | add to 1.9 (section 9) |
| 10 | `html.parser` / NFC drift enters the quote layer at 1.6 (casefold exists at `seam.py:387`; NFC arrives with the NBSP label test `:492`) | extend the fingerprint to quote labels |

**Limits audit** (hearth, cited; **not re-verified by Claude**):

| limit | enforced today? | where |
|---|---|---|
| `max_input_bytes` | yes | `parse.py:304-308` |
| `max_depth`, `max_parts` | HTML tree only, as recorded caps (`htmltree.py:53-55`); the MIME walk is not bounded (`walk(container)` takes no limits, `walk.py:175`) | 1.5c |
| `max_header_bytes` | no (defined and defaulted, never read) | 1.5c |
| `max_decoded_part_bytes`, `max_total_bytes` | no | 1.8 (decoded) and 1.5c (total) |
| `max_work_units_per_input_byte` | per field value only, inside RFC 2047 (`rfc2047.py:179-180`) | rename; per-part step budget in the 1.6 scanner |

A cap hit is `skipped(<cap>_cap)` with a `CapRecord`, all five reasons already exist; `Truncation` is for
streams that end short and `NamedError` is for entry-point failures with no record. So 1.5c is
vocabulary-free. **The message-scope work accumulator is dropped** (unit kinds are incommensurable, and a
counter threaded through five layers is cross-cutting state): structural caps plus the per-field budget, plus
a per-scanner step budget if 1.6 proves superlinear. The superlinearity gate (1.10b) is deterministic: the
scanner takes an injected counter behind a test seam; assert an **exact** reproducible step count for a fixed
input and that doubling the hostile input grows steps by less than a fixed factor. The current
`time.perf_counter()` gate (`test_selection.py:748-761`) is exactly what the rules forbid and should be
replaced.

## 5. Hostile set and 1.9 hazards

**1.10b / earlier coverage beyond the five cap fixtures.** The build-spec already names deep nesting, part
bomb, header bomb, encoded-word bomb, long base64 run, `data:` URI, remote image (`:377-381`); boundary storms
fold into the part bomb. Additions: **nested `message/rfc822` is a bounded non-recursion assertion** (N-deep
costs O(N) at the top level and never descends, since Phase 1 does not recurse; a zip bomb is only a magic
read), a 10 MB single line with no newline, 100k `>` lines, an `On ... wrote:` search that must be
single-pass or anchored. The last three belong in 1.6/1.7 exit criteria, not only 1.10b.

**1.9 policies** (the declared block stops at "green end to end", `turn-declarations.md:557-577`):

- Directory ingest sorts by the POSIX-normalised relative path **as UTF-8 bytes compared bytewise**; add
  `a.eml` vs `A.eml` and a non-ASCII name fixture.
- Do not recurse symlinked directories (no loops possible); a symlinked file is read as its target.
- Unreadable file: a recorded per-file outcome with a named id; the run continues.
- Re-ingest of unchanged bytes is already a no-op (`store.py:185-198`, keyed by `walk_key`).
- Same bytes under two paths is **one document, two manifest rows**; a path never enters a cache key, so
  the document carries no path and **path provenance needs an ingest manifest** (path to container hash to
  outcome; `container_facts` holds none, `container.py:132-139`).
- Same Message-ID, different bytes: both stored, neither merged, and **nothing is recorded** (the
  `same_message_candidates` axis is not built); 1.9 must say that explicitly so "not merged" is not read as
  "recorded".

## 6. Independent checks proposed, with cost

| check | catches | cost / leak | verdict |
|---|---|---|---|
| **Producer-generated fixtures**: the owner composes mails with **invented** content from real Gmail, Outlook, Thunderbird and Apple clients (reply, forward, top-post, bottom-post, 3-deep), saved as `.eml`; labels typed from the client's visible rendering | spec-level common-mode error for the four named vendors (real producer bytes, label no model wrote) | hours to set up, minutes to repeat; Outlook desktop saves `.msg`, so use Outlook on the web "Download original" or drag-to-folder; **leak: nil on throwaway accounts, severe from a corporate account** (tenant ids, SMTP address, vendor blobs), so never export from a work account | do |
| **Structure-only probe** run by the owner (`tools/real_probe.py`) | un-ruled vendors; the real distribution of containers | owner minutes; leak controlled in-probe | do |
| Second independent typing of a sample | typing errors only (the five wrong HTML span rows were typos) | one seat-hour | **disputed** |
| Differential against a "dumb structural oracle" | implementation bugs only; a spec bug is shared (code lineage is not author independence, build-spec `:348-349`) | moderate | not recommended for the DOM family |

**What the probe must report.** Integers alone are insufficient: a wrong class name is the failure being
hunted and an integer cannot falsify it. The probe reports **names and counts**, keyed by
`(tag, id, class, parent)` (ids matter as much as classes: `divRplyFwdMsg` and Gmail's `:xyz` ids are what
the DOM rules key on), with top-N names as the default output. It filters in-probe, **before disk**, emails,
`@`, GUIDs and `x_` Exchange patterns; an allow-list of known producer tokens is a second net; unfiltered
top-N goes to a file outside the repo that the owner redacts and hand-commits. The output is a doc artifact,
not a fixture, and must never land under `fixtures/**` (the census test would see it). Also report integer
aggregates: per-vendor message counts, boundary-kind counts, depth histograms, and the share of messages with
zero boundaries found.

**Ordering.** Probe first (it is where vendor names come from), but type at least one producer fixture
from the client's rendering **before reading the probe's conclusions**, or the fixtures merely re-encode the
probe. (Hearth said producer-first in round 2 and probe-first in round 5 with this caveat; Claude accepts the
caveat. Both are owner-run, so they can run in parallel.)

**Label provenance for producer fixtures.** `labels.py:39` fixes provenance to `human | generator | spec`
and `:38` asserts no sidecar claims `human`; a rendering-typed label fits none cleanly. Decision needed:
a new token, or an explicit "stays `spec`" rule. Producer fixtures are **not** excluded from the "rule
writer never sees labels" rule; the label-typer (ideally the owner, from the rendering) must differ from the
rule-writing agent. Ship committed bytes with recorded client and version, never a render script.

## 7. What hearth disagreed with and why

- **1.9 shell before 1.6**: Claude proposed it; hearth showed the records are already frozen, that 1.6/1.7
  allow-lists exclude `model.py`, and that a holder frozen before 1.7 risks a second schema bump. Claude
  conceded.
- **A second typing and a structural oracle are common-mode breakers**: hearth argued they are not (same
  family, same document); Claude conceded for spec errors and kept the second typing as a typo check only.
- **Probe integers-only**: hearth showed integers cannot falsify class names; Claude conceded and moved to
  names and counts with in-probe redaction.
- **Reverse-direction disagreement (prefix >= 1, structure 0)**: Claude had it backwards; it is silent and
  correct. Hearth located the real flaw (unobservable in L1).
- **Local reflow in 1.6**: hearth showed it breaks span honesty and then preferred not to build any reflow;
  Claude accepted.
- **`magic` cap-skipped = `absent`**: hearth had said so; Claude objected (absent must mean "looked, no
  evidence") and hearth conceded to `unknown(reason)`.
- **Work-unit accumulator**: Claude proposed one; hearth showed it incommensurable and cross-cutting and
  Claude accepted dropping it.
- **`magic_prefix` on the named error, new `html.*` cap ids, keep-the-name limits semantics, sealed canary
  rows**: hearth refused each (second place a magic lives; D6 duplicate; a false statement in a frozen name;
  an unverifiable number that conflicts with the reproducibility rules and burdens a tired reviewer).
  Claude accepted all four.
- **Re-basing floors**: hearth argued an automatic ratchet drifts silently; Claude accepted an owner-signed,
  recorded re-base.

## 8. Determinism (question f)

Hearth's grep of the package (**not re-verified**): no `import email`, no `unicodedata`, no `locale`, no
`datetime`/`time`, no `random`; rule tables are `frozenset`s used for membership and output-emitting
iteration is `sorted(...)`. So the real surviving risks are:

- **`html.parser`** (`htmltree.py:295`): real; tokenization changes between patch levels alter trees and so
  spans. The existing control `tests/support/html_projection_hash.py` compares in-process against a second
  interpreter and **silently returns when CPython 3.11 or the core is absent** (`test_selection.py:764-801`),
  so on a one-interpreter machine it asserts nothing, and no golden constant exists. **Phase 1 exit
  criterion (new):** commit `(fixture, locator, sha256)` rows, recording `interpreter_label()`, failing with the
  moved fixture named, with a documented regeneration/waiver path for an intentional upgrade. The golden is a
  regression pin; the label is the oracle; the golden never overrides a label.
- **Unicode normalisation**: enters at 1.6 (NFC for label matching; `casefold` already at `seam.py:387`).
  Extend the cross-interpreter fingerprint to cover quote labels once 1.6 lands.
- A runtime stamp (`RunRecord.environment`, `model.py:948`) records provenance but does not detect drift;
  the fingerprint detects; a CI matrix is a nice-to-have (there is no `.github/`).
- Not real today: stdlib `email` use, set/dict ordering, locale, hash randomisation.

## 9. Handoff to Phase 2 (question g)

Exists (hearth): document id `container_hash` (`model.py:967`); the not-built representation
`TriValue(UNKNOWN, NOT_BUILT_IN_PHASE1)`, never `None` or `[]` (`ids.py:33-38`, `model.py:975-981`);
Message-ID / In-Reply-To / References as parsed facts (`l1.py:595-600`; only the resolved edges are Phase 3);
`output_schema_version`, `email_parser_version`, `environment`; content-addressed `attachment_id`; byte
spans `RawSpan.slice`.

Missing and to add to 1.9 (or declare as not built): (1) **stable per-part id**: `PartRecord.part_id` is
explicitly non-stable (`model.py:662`) and `ids.part_id` (`ids.py:89`) is never stamped on a part; (2)
**per-stage projection versions on the record** (`TEXTPART_VERSION`, `HTMLTEXT_VERSION`, `TEXTMODEL_VERSION`,
`HEADERTEXT_VERSION`, `DECODE_CHAIN_VERSION`) so a consumer knows what produced a stored `body.text`; (3) a
documented `resolve(view_span) -> RawSpan | unresolvable(reason)` citation function (flowed and non-identity
parts have no within-part byte map and must return the reason); (4) the ingest manifest (section 5); (5) the
statement that `same_message_candidates` records nothing in Phase 1.

## 10. What to cut

Agreed cuts: no 1.4b; no message-scope work accumulator; no `magic_prefix`; no sealed canaries; no new
`html.*` ids; localised list-footer **variants** (not the mechanism); `part_empty` as a reason; the separate
seeded-fuzz test file unless it has its own corpus; the structural differential oracle for the DOM family.
Split 1.10 rather than cut it.

## 11. Dissent that remains

1. **Second typing of a catalogue sample.** Hearth would cut it (same model shares misreadings; the probe
   and producer fixtures already break common mode). Claude keeps it as a typo check at one seat-hour, since
   the known failure class (five wrong span rows) was typing, not misreading. The owner decides; it does not
   block anything.
2. **Probe vs producer fixtures order.** Compatible given the caveat in section 6, but hearth leans
   probe-first and Claude producer-first; both are owner-run so the owner may simply run both.
3. **Coverage floors.** Resolved to owner-signed re-base; Claude's original "re-base to achieved at 1.10"
   survives only in that form.

No other material disagreement remains.

## 12. Owner decisions needed

1. Catalogue gate: sign-off after adding the hard-wrap row, the flowed-quote row and the `>` spacing rows.
2. Producer-generated fixtures: whether to do them, from which clients, never from a work account; and the
   label-provenance token (new token or stays `spec`).
3. The structure-only probe: run it, review and redact the top-N output, commit the redacted copy.
4. Apple and Yahoo: confirm shapes from the probe before they become v1.
5. `Limits` rename (`max_work_units_per_input_byte` to a per-field-value name) and the defaults; new turn
   1.5c declared.
6. The three magic reason ids.
7. The 1.9 policy triad plus ingest manifest, and the golden-hash exit criterion with its waiver path.
8. The re-ordered turn table (1.8 before 1.6; 1.10 split).
9. Optional: second typing; `.msg` census counter; floors re-base at 1.10a.
