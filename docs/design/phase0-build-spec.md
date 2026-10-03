# Phase 0 build spec: contracts, ledger, fixtures, gates, sibling contract

Revision 2. Revision 1 predated the owner's real samples; revision 2 follows the design doc's
"Revision 2" (second hearth round): `.msg` is in v1 (own `olefile` reader, **Phase 1b, not
Phase 0**), the `TimeEvent` contract is frozen in Phase 0 with conflict fixtures, and the
privacy rule about real samples is explicit. What changed is listed in "What revision 2
changed" at the end.

Source of truth: `docs/design/email-extraction-design.md` (decisions D1 to D16). If this file
conflicts with the design doc, the design doc wins; report the conflict. Phase 0 builds **no
email parsing logic beyond a skeleton walker** over a container-neutral interface (see "Resolved
ambiguities"): no quote segmentation, no attachment routing, no threading, no matching, **no
CFB/`.msg` code**.

Siblings (published on PyPI at 0.1.0, Apache-2.0): `docextract-core` (hashing, strict
canonical-JSON codec, `Collection`, raw archive), `word-extract` (`wordextract`),
`form-extract` (`formextract`). Read-only references while building:
`C:\Users\ivan_\App_repos\word-extract` (design D1 to D12, `CLAUDE.md`, the behavior ledger,
`tools/behavior_ledger.py`, the sidecar and L1 pattern) and
`C:\Users\ivan_\App_repos\form-extract`. **Do not edit either sibling in Phase 0**; the
matcher move (track S) needs the owner's approval and is not part of this spec.

Scale target: **about 25 messages**, tens of attachments. Design for correctness and
reproducibility, not scale.

## Decisions made by the user

1. The package is `email-extract` (import `emailextract`), Apache-2.0, copyright Ivan Ortega, a
   sibling of the other two. It depends on `docextract-core>=0.1.0,<0.2` only. `word-extract`
   and `form-extract` are **optional extras** (`emailextract[word]`, `emailextract[form]`) and
   are not imported anywhere in Phase 0 except by tests behind `pytest.importorskip`.
2. v1 input is `.eml` **and `.msg`** (the owner's real mail is both), one file or a directory.
   `.msg` is read by an **own `olefile`-based reader with no GPL dependency anywhere** (code,
   optional extras, tests, dev-dependencies; D1, D13), built in **Phase 1b**; the owner has not yet
   confirmed this policy (see "Blocked on the user"), and **Phase 0 does not depend on it**.
   `.emlx`, `.mht`, mbox and PST are out of v1.
3. **Real email never enters the repo, a fixture, a test, a commit message or a log.** `fixtures/real/`
   is git-ignored. The owner's sample mails live in their Downloads folder and stay there. The owner has
   confirmed that **the sample mails supplied so far carry no confidentiality concern**, so a
   *structure-only* probe (`tools/real_probe.py`: names, counts, sizes, tags, never subjects, addresses,
   bodies or decoded filenames) may be run on them by the build agent. Mail from the owner's employer or
   any other mail is **not** covered by that confirmation and is never probed or read by an agent.
   If a prompt file or an input cannot be found, **stop and ask**; never search the machine for it.
4. The "organizer" is **not built first** (D15): parsers emit `TimeEvent` evidence, the shape is
   frozen as a doc and a dataclass in Phase 0 with conflict fixtures, and a read-only
   `docextract-timeline` layer is a later, separate package. The employer-ownership question is
   the owner's alone and is not asserted in code, docs or package metadata.

## Ground rules

- **Deterministic first; no LLM anywhere in this package.**
- **A default view is a projection of the content, never the content; every projection names
  the rule and version that made it; the raw bytes are the source of truth.**
- **Unknown is recorded as unknown**: tri-state `value | absent | unknown(reason_id)`, named gap
  ids (`docs/design/phase0-gaps.md`), never `None` standing in for "no".
- **No confidence scalars and no fuzzy hits.** A rule fires or it does not, and says which.
  Encoding detection is a **deterministic ladder** (D13), never statistical; `chardet` and
  `charset-normalizer` are banned.
- **Everything in a message is attacker text** (headers, display names, filenames, quoted
  history); thread edges, `Thread-Index`, `msip_labels` and authentication headers are *claims*,
  never verified facts.
- **Hand-typed ground truth is never edited to match output.** Sidecars are typed independently
  of the generator that makes the `.eml` bytes (D11), load without importing the parser, and
  carry `labels_provenance: hand | generator | spec`. If a sidecar contradicts the design, say
  so in the report; do not change the sidecar to make a test pass.
- **Behavior change means version bump plus ledger line**, same commit (the word-extract rule).
- **No network in tests. No GPL code anywhere.** No remote fetch, no macro execution, no
  attachment written under its raw filename, ever (D10).
- Python 3.11 to 3.14 must pass (CI matrix). **The stdlib `email` package changed behavior
  across these versions**; any fixture whose parse differs by version is recorded, not hidden,
  and the ledger fingerprints must hold on all four.
- Style matches the siblings. **Never commit; report the diff and the full test output.** Each
  turn ends green. Use the file-writing tools for test files, not shell heredocs (Windows
  escaping has mangled `\n` and `\t` before).

## Layout to create

```
pyproject.toml                  # name email-extract; deps: docextract-core>=0.1.0,<0.2, olefile
                                # is NOT a Phase 0 dependency (it arrives with Phase 1b);
                                # extras: word, form (both optional), dev (pytest)
LICENSE  NOTICE  README.md  CLAUDE.md  .gitignore   # fixtures/real/ and local-private/ ignored
emailextract/
  __init__.py
  versions.py        # every version constant a key or a citation trusts (see Turn 0.1)
  model.py           # the frozen record contracts over the core codec
  timeevent.py       # the TimeEvent dataclass (D15); stays here until a second producer exists
  container.py       # container-neutral interface (Container, ContainerKind) + an in-memory FAKE
  walk.py            # SKELETON walker over the interface: parts, raw spans, decode chain,
                     # preamble/epilogue accounting (an .eml adapter over bytes + the fake)
  ids.py             # content-addressed ids (sha256 of raw spans); no positional ids as identity
  siblings.py        # sibling discovery, ChildLink, the citation nesting (Turn 0.5)
  seam.py            # the matcher seam protocol + a trivial local stub (Turn 0.6)
  evals/             # L1 oracle, label loader (never imports the parser)
tests/support/timeline_ref.py   # TEST-ONLY reference evaluator of the named ordering policies
tools/
  make_fixtures.py   # declarative .eml generator (pinned dates, boundaries, ids)
  behavior_ledger.py update_behavior_ledger.py   # analogue of word-extract's
  email_spike.py     # Turn 0.0: measures stdlib `email` behavior
  real_probe.py      # structure-only probe of local real samples (prints no content)
fixtures/
  generated/*.eml  *.expected.json        # generator bytes; HAND-TYPED sidecars
  raw/*.eml  *.expected.json  SHA256SUMS  # hand-written bytes; sha256-frozen by a test
  time/*.eml  *.expected.json             # conflict fixtures for the TimeEvent contract
  real/                                   # git-ignored, machine-local
tests/ledger/behavior_ledger.json  tests/ledger/corpus.json
docs/design/email-extraction-design.md  email-spike.md  timeevent.md  phase0-gaps.md  open-inputs.md
```

## Resolved ambiguities (read before Turn 0.1)

1. **"No parser" and the gates.** The gates need *something* that walks bytes. Resolution: Phase 0
   ships a **skeleton walker** (`walk.py`) that runs against the **container-neutral interface**
   (`container.py`) with an `.eml` adapter and an **in-memory fake container**. It records, per
   part, the raw byte span, the declared and used CTE/charset, `fallback_fired` (the decode
   chain), and accounts for preamble and epilogue bytes. It does **not** segment quotes, classify
   attachments, route to siblings, build threads, render headers, match terms, or read a CFB file
   (D13: Phase 0 depending on CFB would put the contracts behind the hardest component).
   Everything beyond that returns `unknown(not_built_in_phase0)`.
2. **Schema versions.** `docextract_core.codec.SCHEMA_VERSION` is core-wide and strict. The design
   also wants an `output_schema_version`. Turn 0.1 must decide, and report, how the two relate
   (recommended: email records use the core codec's envelope unchanged and carry
   `output_schema_version` as an ordinary field that is part of every cache key).
3. **stdlib and MAPI behavior is unmeasured.** Hearth could not run code in the debate. Turn 0.0
   measures stdlib behavior (and, on a local path the owner supplies, `.msg` *structure*) before
   any contract freezes. Where stdlib cannot give what D2 assumes (raw byte offsets per header
   field), the walker owns a small raw-header scanner, and the design stands. **No MAPI property
   tag is frozen by this spec or the design doc**; Phase 1b's first task is to verify them.
4. **`TimeEvent` lives in this package for now** (D15): code type in `emailextract/timeevent.py`,
   shape frozen in `docs/design/timeevent.md`; promotion to `docextract-core` only when a third
   producer or a cross-package consumer exists. Phase 0 freezes the shape and proves it can express
   conflicts; the ordering layer itself is not built.

## Turn 0.0: measure the stdlib (a spike, like word-extract's opc spike)

Write `tools/email_spike.py`, `tools/real_probe.py` and `docs/design/email-spike.md`. With
**hand-written byte strings** (inline in the script; no real mail), measure on all Python versions
present (at least the default plus 3.11) and record in a table, each row *measured* or *not
measurable here*:

- `email.message_from_bytes(..., policy=policy.default)`: obs-fold unfolding; duplicate headers
  (order kept? `Received`); a non-blank line that is not `name: value`; a message with no blank
  line; `-0000` vs `+0000` in `Date` (`email.utils`); `parseaddr`/`getaddresses` on a group
  (`undisclosed-recipients:;`), on IDN and SMTPUTF8 local parts, and on garbage; RFC 2047 encoded
  words invalid and valid; RFC 2231 `filename*=` continuations; a `Thread-Index` header's raw value.
- `msg.defects` content for malformed boundaries, truncated base64, bad charset.
- Whether **raw header bytes and byte offsets** are recoverable from the parsed object (expect:
  no); what `msg.preamble` and `msg.epilogue` contain; whether the raw bytes between boundaries
  can be recovered from the parse (expect: no).
- `get_payload(decode=True)` on a bad charset, on truncated base64, on QP with a stray `=`, on
  `iso-8859-1` quoted-printable.
- `message/rfc822` with no filename; a `text/calendar` part inside `multipart/alternative` next to
  a `.ics` attachment with a `Content-ID`; `iter_attachments`/`iter_parts` on those shapes.
- lxml: `lxml.html` parse of a Gmail quote block, an Outlook `divRplyFwdMsg` block and a
  `blockquote type=cite`; the `parser.error_log` contents; how `<style>`/`<script>` appear.
- **`.msg` structure (D13), structure only:** `tools/real_probe.py` takes a path on the command
  line (never a path inside the repo) and, with `olefile`, prints only stream **names and sizes**,
  the presence of the plain/HTML/RTF body streams, the transport-header stream, attachment and
  recipient storage counts, the string-property type (UTF-16 vs 8-bit). It prints **no content**.
  Record the observed property-tag set and storage layout in `email-spike.md` as measured facts
  with the sample described only by its structure. `olefile` is imported by this dev tool only.
  **Measured on the owner's samples (structure only), to be re-verified by the spike:** the
  **code page properties (internet code page, message code page) are fixed-size properties
  inside the `__properties_version1.0` stream, not separate streams**; a reader that looks for a
  stream named after the property tag will wrongly conclude they are absent. The same applies
  to the compressed-RTF-in-sync flag. Body streams (`PR_BODY`, `PR_RTF_COMPRESSED`, `PR_HTML`)
  are real streams; real messages exist with HTML only, and with plain + compressed RTF and no
  HTML (the RTF generated from text, `\fromtext`). The probe must therefore parse the property
  table for the code page and flag properties and report presence only.

Exit: every assumption stated in the design doc's "Open risks" is marked measured with a
reproducer, or marked unmeasurable with the reason. Report any place stdlib disagrees with the
design and name the fallback. No contract is frozen before this report.

## Turn 0.1: skeleton, contracts and versions

Create the repo skeleton (`pyproject.toml`, `LICENSE`, `NOTICE`, `README`, `CLAUDE.md`, ignore
rules, pytest config; copy the data-hygiene rules from the siblings' `CLAUDE.md`, plus the real
sample and no-GPL rules above). Then the contracts, as **frozen dataclasses over the core codec**
(strict decoding; unknown key raises; do not inherit the word-extract "unknown-key drops" risk):

`EmailDocument`, `PartRecord`, `HeaderField`, `AttachmentOccurrence`, `ChildLink`, `ThreadEdge`,
`FlagHit` (the shape only), `RunRecord`, `TimeEvent` (D15, in `timeevent.py`), and the reserved
`FlagSection {terms, term_list_hash|null, matcher_version|null, flag_schema_version, hits: [],
rollup|null}`, present-but-empty on every record and round-tripping (D8).

Container identity (D14): `container_kind` as the enum `rfc822 | cfb_msg` (the `cfb_msg` value
exists in the contract; nothing produces it in Phase 0), `container_facts`, `container_hash`, and
`content_fingerprint` with `body_digest` and `body_digest_view` recorded; the
`same_message_candidate` relation; `encoding_source` as an enum (`internet_cpid | message_cpid |
ascii | utf8_strict | windows_1252 | declared_charset | fallback`).

Axes exactly as designed: `classification` (`attachment|inline|unknown`), `selection`
(`selected|alternative_not_selected|n/a`), `role`, and `status` as a **closed nine-member enum**
(`parsed, skipped, unsupported, not_installed, failed, password_protected, encrypted, empty,
truncated`) with the table of allowed reasons (D6) encoded in the contract and **rejected at
construction** when a reason does not belong to its status. `classification_hint` (for
`msip_labels`, recorded as a claim); the tri-state value type; `ChildLink` as
`resolved|store_absent|child_absent|version_mismatch`; the three type verdicts (`declared_mime`,
`magic`, `container_introspection`) plus winner plus disagreement; `decorative_hint: rule_id |
absent` (never a boolean); the decode chain (`declared_cte, declared_charset, used_cte,
used_charset, fallback_fired`).

`TimeEvent` fields exactly as D15: `{event_id, doc_id, parent_event_id|null, kind, when_raw,
when_utc | unknown(reason), offset | unknown, offset_origin, precision, ambiguity, source {field|
property|part, ordinal, span}, trust, usable_for_arrival_ordering}`. `SEQUENCE`, `UID` and
`METHOD` are calendar facts and are **not** `TimeEvent`s.

`versions.py`: `OUTPUT_SCHEMA_VERSION`, `TEXTMODEL_VERSION`, `HEADERTEXT_VERSION`,
`HTMLTEXT_VERSION`, `DECODE_CHAIN_VERSION`, `FLAG_SCHEMA_VERSION`, `TIMEEVENT_VERSION`,
`EMAIL_PARSER_VERSION`; each with a docstring saying what moves it.

Tests (hand-typed): every record round-trips byte-identically; an unknown key raises; a reason
that belongs to another status raises; a `value|absent|unknown` field cannot be constructed
without its reason id; the status enum has exactly nine members (a test that fails if one is
added without the design changing); a record with an empty `FlagSection` round-trips; a
`TimeEvent` with `when_utc = unknown(relative)` round-trips and cannot also carry a `when_utc`.

Exit: green; the report states the schema-version relationship decision (Resolved ambiguity 2).

## Turn 0.2: ledger, reproducibility and the skeleton walker

Build `container.py`, `walk.py` and `ids.py`. Identity is content-addressed: the message id is
the sha256 of the raw bytes (`container_hash`); a part is addressed by `(container hash, raw byte
span)` and its own content hash; the `1.2.3` part path is recorded as an explicitly **non-stable
locator** only (it renumbers on insertion). The walker records, per part: raw span `(offset,
length)`, headers span, body span, declared and used CTE/charset, `fallback_fired`; and the
**preamble and epilogue** as their own accounted regions. `errors="replace"` is never the normal
decode path (it destroys byte round-trip); a lossy decode is recorded `body.decode_destroyed_bytes`.
The in-memory fake container proves the walker is container-neutral (a second `container_kind`
exercised without any CFB code).

Build the **behavior ledger** analogue of word-extract's (`tools/behavior_ledger.py`,
`update_behavior_ledger.py --check`, `tests/ledger/`): fingerprints of the walker's output over a
**versioned corpus** (`corpus.json`; growing the fixtures adds a corpus version and bumps no
component version), keyed by the version constants. Include the walker, the contracts (keyed by
schema alone) and the decode chain. Add a **run record** (hashed inputs vs recorded-only inputs,
per-artifact hit/miss) and a **re-ingest-is-a-no-op** harness over a throwaway store built on the
core `Collection`.

Tests: the same bytes give the same ids and a byte-identical store; re-ingest writes nothing; the
ledger `--check` **exits 1** when walker behavior changes without a version bump and exits 0
otherwise (sensitivity tests that monkeypatch one rule, as word-extract's do); the check names the
constant to bump; the walker produces the same part shape over the `.eml` adapter and the fake.

Exit: green; the ledger is recorded on the Turn 0.3 corpus once that exists (until then it runs
over a tiny inline corpus; say which).

## Turn 0.3: fixtures and labels

`tools/make_fixtures.py` is a **declarative** generator: each fixture is a Python description
(headers, parts, boundaries, encodings, attachments as inline bytes) rendered to `.eml` with pinned
dates, boundary strings and `Message-ID`s so regeneration is byte-identical. **The sidecars are
typed by hand and independently**: the generator never writes them and the tests never read them
back from the parser (D11). Every sidecar carries `labels_provenance`. An independent loader
(`emailextract/evals/labels.py`) reads sidecars **without importing the parser**.

Generated (8): `plain_simple`, `alternative_text_html`, `multipart_mixed_wraps_alternative`,
`rfc2047_folded_duplicate_received`, `attachments_mixed` (pdf + xlsx + docx + png, tiny valid
files made in memory; the generator may use python-docx, the library never does),
`inline_cid_referenced_and_not`, `thread_three_refs_chain`, `preamble_epilogue`.
Raw hand-written (3, **sha256-frozen** in `fixtures/raw/SHA256SUMS`, checked by a test):
`bad_charset`, `truncated_base64`, `malformed_mime`. The raw three are non-negotiable: Phase 0's
gates need bytes a generator cannot honestly produce.

**Conflict fixtures for the `TimeEvent` contract (D15), 3 to 5, in `fixtures/time/`**, each a
synthetic `.eml` whose evidence disagrees, with a **hand-typed** expected artifact: the evidence
listing (`TimeEvent`s with kind, trust, `usable_for_arrival_ordering`), the order under each named
policy (`header_date_claimed`, `received_chain_header_order` by header order and never by
timestamp, `owner_manifest` as a labeled total-order override), and the **unresolved conflict
pairs** returned beside any order. Cases at minimum: (1) `Date` earlier than every `Received`
hop; (2) `Received` timestamps out of header order (clock skew); (3) `Date` with `-0000` vs a
`Received` zone; (4) a `Date` header vs a simulated file mtime (`trust=filesystem`); (5) a message
mentioning a future date in its text (must not become an arrival time). A **test-only** reference
evaluator (`tests/support/timeline_ref.py`) computes the orders from the evidence list so the
hand-typed expectations are checked; it is not shipped and is not the timeline layer.

Each sidecar states, for its message, the facts a later phase must reproduce: header fields in
order with raw values, part tree with raw spans, decode-chain verdicts, preamble and epilogue
byte counts, attachment names/types/hashes, expected gaps. Sidecars for later-phase facts (quote
boundaries, statuses beyond the skeleton) are written now where the fixture exists and marked
`phase: <n>`; the L1 oracle skips facts whose phase has not shipped, never silently (it reports
them as `not_yet`).

Tests: regenerate the 8 and get identical sha256; the raw 3 match `SHA256SUMS`; every sidecar
loads without importing `emailextract.walk`; a fixture with no sidecar, or a sidecar with no
fixture, fails; each conflict fixture's expected orders reproduce under the reference evaluator and
**the unresolved pairs are non-empty where the evidence conflicts**.

Exit: green; the ledger corpus is these 11 messages plus the conflict fixtures.

## Turn 0.4: gates

- **L1 exact oracle** (`evals/l1.py`): compares every fact a sidecar asserts that the skeleton
  walker can produce, over all fixtures, gated at **100%**. An L1 that compared nothing **fails**.
- **Falsifiability:** a deliberately wrong copy of one sidecar (in a temp directory, never the
  real one) **fails** the gate; the test proves the gate can fail.
- **No-silent-drop property test** (D9): for every fixture, every input byte is accounted for by
  a part span, the preamble, the epilogue, or a recorded status. Run it on all, including
  `preamble_epilogue`, `truncated_base64` and `malformed_mime`. Add a mutation check: removing one
  accounted region makes the test fail.
- **Decode-chain flip-one-input:** change the declared charset of one part and assert that the
  part's projection hash changes while the raw message hash does not.
- A metrics table (`python -m emailextract.evals`) reporting L1, the invariants, and the corpus
  size; exit 1 when a gate fails.

Exit: green; the report lists what the L1 oracle does and does not yet check (the `not_yet`
facts by phase).

## Turn 0.5: sibling contract freeze

Freeze the **child-result shape** and the **citation nesting** (D12), with a **fake sibling
store** (a tiny in-test store implementing the shape; no real sibling imported):
`siblings.py` provides sibling discovery (`importlib.util.find_spec`, never import-for-side-effect),
`not_installed` carrying `needed_sibling`, the tri-state `ChildLink`, the thin **locator** (a
config of store roots checked in order), and the three-bucket citation (`email-extract's own`,
`verbatim passthrough`, `stamped`) where a missing child store makes the child citation
`unknown` **whole**, never partially filled. A child's `page_count`/`sheet_count` are
`sibling_derived` and `unknown` when the child store is absent; never copied.

Tests: the contract is green against the fake store; the `not_installed` path is green with the
siblings genuinely absent (`sys.modules` patched out) and with them present
(`pytest.importorskip`); a version-mismatched child yields `version_mismatch`; a deleted child
store yields `store_absent` and the manifest stays useful (filename, type, sha256, size).

Exit: green; the report states the child-result shape as frozen text, so a sibling's query API
can be checked against it in Phase 2 (Open risk 1: nothing here tests a *real* sibling).

## Turn 0.6: gaps and the matcher seam

- **`docs/design/phase0-gaps.md`**: every known-gap id from the design doc's registry (including
  the new `msg` and `time` families), one entry each (what is missing, what a reader must not
  infer), resolved by a test that every id the contracts or walker can emit is documented, and the
  reverse. Decide the candidate prune (`attach.size_cap_hit` / `attach.nesting_cap_hit` versus the
  `skipped` reasons) and record why.
- **The matcher seam** (`seam.py`): a protocol for "term set + rules + **caller-supplied closable
  runs**" over `(text, view_id, runs)`, with a trivial local stub (whole-token exact match, no
  stemming, no synonyms) used only to test the contract. Decision `view.gap_closing_contiguous`:
  the matcher bridges excluded text only **inside** a run the caller passed, never across runs.
  No matcher logic beyond the stub; the physical matcher move is track S, not here.
- `FlagHit`'s location is **opaque and producer-shaped** (D8): email-extract never fabricates a
  page or cell.
- **`docs/design/timeevent.md`**: the frozen `TimeEvent` shape (D15), the kinds, the trust values,
  the three named policies and the rule that **no policy is implicit**, and a pointer to the
  conflict fixtures. This is the doc-freeze the design calls for.

Tests: the seam contract is green against the stub, including that a run boundary stops a match
that would otherwise span it; a `FlagSection` with a stub hit round-trips.

Exit: green.

## Exit criteria for Phase 0

- The spike and six turns are green; the ledger is green; L1 is 100% over all fixtures and fails
  on a wrong sidecar; no-silent-drop and flip-one-input are green; regeneration is byte-identical;
  the raw set is sha256-frozen; the conflict fixtures reproduce under the reference evaluator; the
  siblings are optional and the package imports without them; no CFB code and no GPL dependency
  exist.
- Nothing parses quotes, routes attachments, builds threads, reads `.msg` or matches terms yet; the
  report says so.
- Final report: files created, the full pytest output, each ambiguity resolved and how, each
  contract decision (especially the schema-version relationship), what the spike measured versus
  could not, and anything not done.

## Phases 1 to 3 and later (outline; each gets its own spec after Phase 0 is validated)

- **Phase 1: container-neutral contract exercised over RFC 822: headers as a part, body views,
  attachment manifest** (D2, D3, D4, D16). Quote boundaries stored as `quote_boundary_ordinal` +
  `quote_prefix_depth` with a rule id and `kind` per boundary, **per view and per evidence family,
  never reconciled across views**; text rules **and** DOM rules (Gmail, Outlook), including the
  mixed Gmail-quoting-Outlook case and plain text with no `>` prefixes; three type verdicts,
  hashes, inline filtering; `message/rfc822` with no filename; a calendar part plus a `.ics`
  attachment with a Content-ID; effectively-empty plain alternatives. Exit: L1 100%; ordinals and
  rule ids stored (the Phase 5 precondition).
- **Phase 1b: the `.msg` reader** (D13): `cfb.py` primitives (miniFAT mandatory), the MAPI layer
  with property tags **verified by the spike**, the encoding ladder, the `tools/` CFB writer, one
  fixture hand-built to Outlook's observed layout, the cross-container pair (D14).
- **Phase 2: routing, statuses, recursion, caps** (D4, D6, D9) to word-extract and form-extract
  as optional extras; every status reachable by a fixture; the first real sibling round-trip.
- **Phase 3: header-based threading and date ordering** (D7, D15): `Received` hops ordered by header
  order, the claimed `Thread-Index` decode, `TimeEvent` emission. The parse is gated; the thread
  join is reported, never gated.
- **Track S (the word-extract repo, blocks Phase 4 only; needs the owner's approval):** move the
  text-level matcher into `docextract_core.match` (D8).
- **`docextract-timeline` (named):** the read-only merge/query layer with caller-named ordering
  policies, after Phase 3 and after word-extract emits at least one real `TimeEvent`.
- Phase 4 (flags and rollups), 5 (quote-reconstructed messages, a separately labeled layer) and
  6 (read-only query API and MCP server) are named only.

## Blocked on the user (do not fake)

1. **Confirm the `.msg` policy:** an own `olefile` reader, **no GPL anywhere** (including optional
   extras and dev-dependencies), and that running `extract-msg` by hand locally for spot checks is
   acceptable but never a dependency.
2. **Confirm the organizer plan:** not first, shape frozen in Phase 0, a separate
   `docextract-timeline` after Phase 3. **Supply an arrival manifest** for non-email files (when
   each came in): filesystem times are not evidence of arrival.
3. **Choose the first named ordering policies** and say whether **in-text date extraction** is wanted
   and under which locale (day-first or month-first).
4. **More redacted real samples**, kept outside the repo: `.msg` with attachments, an embedded
   message, an RTF-only body, and a quoted reply composed in desktop Outlook; ideally also a
   non-English reply marker and a bounce or auto-reply.
5. **Real term lists**, shared with word-extract's open inputs; built from public sources or a list
   the owner may use; kept outside the repo.
6. **Approval to touch the sibling repos** for track S.
7. The employer-ownership question is the owner's alone and is not asserted anywhere in this repo.

## Watch-list

- Hand-typed sidecars: if a test needs a sidecar edited to pass, stop and report the contradiction.
- A fixture whose parse differs across Python 3.11 to 3.14: record it as a named difference with the
  version, never skip it.
- Anything that quietly resolves a header or a date ("repairing" it, or choosing which timestamp is
  true) or drops a part: that is the class of defect this design exists to prevent.
- Keep `emailextract` importable with neither sibling installed and with no `olefile`; a stray
  top-level import of `wordextract`, `formextract`, `pymupdf` or `olefile` in the library is a bug.
- Never read real sample *content* into a prompt, a log or a test; probes print structure only. Never search the machine for a missing file; ask.

## What revision 2 changed

- `.msg` is v1 (own `olefile` reader, Phase 1b), but **Phase 0 contains no CFB code**: the walker
  runs on a container-neutral interface with an in-memory fake container (D13).
- Turn 0.0 adds the structure-only `.msg` probe (`tools/real_probe.py`) and measurements for the new
  shapes seen in real mail (nameless `message/rfc822`, calendar part plus `.ics` with a Content-ID,
  `iso-8859-1` quoted-printable, an effectively empty plain alternative, `Thread-Index`).
- Turn 0.1 adds the container identity fields (D14), `encoding_source`, `classification_hint` and
  the `TimeEvent` contract; Turn 0.3 adds the conflict fixtures and a test-only reference evaluator;
  Turn 0.6 adds `timeevent.md`.
- Privacy: real samples are never given to hearth's model, and no real content is ever printed.
- Blocked-on-the-user items replaced: the `.msg` question is answered (it is the owner's format);
  the license policy, organizer plan, ordering policies and more samples are now the open items.
