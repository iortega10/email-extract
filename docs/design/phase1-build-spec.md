# Phase 1 build spec: container-neutral RFC 822 (revision 2)

Status: **revision 2, ready to execute once the owner commits Turn 1.0a's documents.** Revision 1 was a
draft; it was debated for six rounds with the hearth-cli model (`docs/design/phase1-debate.md`, the record
of who changed their mind and why) and every agreed amendment is folded in below, using the debate's
replacement text. The debate's open owner questions are **decided** in "Decisions" (the owner delegated
them to Claude's recommendation); the items that need a measurement are the "verify empirically"
experiments listed at the end. The design (`docs/design/email-extraction-design.md`) wins on any
conflict: report conflicts. The workbook sibling ran the same process (`workbook-extract/docs/design/
phase1-build-spec.md`, `phase1-debate.md`); its lessons are in the operating rules.

Phase 0 is validated: email-extract commits `a80137e` to `9f7d3ab`, 388 tests green on Python 3.14 and 3.11.

## Goal

Turn an RFC 822 message (`.eml` bytes) into the **`EmailDocument` record** of the Phase 0 contracts: the
**headers part** with its structured projection, the **body parts with views and quote boundaries**, the
**attachment manifest** (identity, classification, type verdicts) and the **run record**, over the
container-neutral interface, deterministically, with every input byte accounted for. Re-ingest of unchanged
bytes is a no-op.

Out of scope, and **recorded as not built through one idiom, never as empty**: `.msg` (Phase 1b), routing,
statuses beyond the skeleton, recursion into `message/rfc822`, `.ics` parsing and
`container_introspection` (Phase 2), threading and `TimeEvent` emission (Phase 3), matching and flags
(`FlagSection` stays present-but-empty; Phase 4/5), the query layer and any LLM-facing output. No LLM
anywhere in the package.

## Operating rules for every build turn (Phase 0 and workbook lessons; each turn prompt restates them)

1. **Read each spec section once, then write files.** Work in a stated order, run pytest after each step,
   and **stop and ask** if an input is missing; never search the machine. Each turn **declares the modules
   and the new test function names it will add**, and a **collection test** asserts the declaration (a rule
   without a mechanism is dropped). Every turn names a **pre-declared stop point** the agent reports at
   rather than pushes past (turn table below).
2. **Both interpreters, always, from the first turn** (`tools/runboth.py` ships in Turn 1.0b). The
   interpreter selector is `py -V:Astral/CPython3.11.15` with a documented fallback (any 3.11 on PATH). The
   stdlib `email`, `html.parser` and lxml/libxml2 can change behaviour across versions and **patch levels**
   (the CVE-2023-27043 `getaddresses` change was backported across maintenance releases), so any case that
   differs is **recorded, not hidden**. The generator never uses the stdlib serializer for fixture bytes, and
   nothing writes a compressed zip or png whose bytes depend on the zlib build.
3. **Independence of labels, mechanically enforced.** Sidecars are typed by hand, `labels_provenance: spec`.
   A sha256 **additions-only ledger** covers every existing `*.expected.json`, **and `tests/support/**` and
   `emailextract/evals/**`** (changes to a gate need an explicit allow-list in the turn prompt). After the
   fixtures turns, the prompt allow-list **excludes `fixtures/**` and `*.expected.json`**, and a test asserts
   that no `emailextract/**` file contains a fixture path or filename literal (**label leak guard**: a rule
   written from the bytes the agent just read). A disagreement between a label and the parser is a
   **finding** with both values and the bytes; the bytes are the judge. The parser is never run over a
   fixture to produce a label.
4. **Honesty rule.** Nothing reports a state, status or value for input it has not read. A thing not built
   is recorded by the **one not-built idiom (decision 6)**; every `unknown` state has a fixture that
   exercises it.
5. **Gates are proven able to fail, non-vacuously.** Every gap id has a **mutation** case and a catalogue
   test fails on an uncovered id. The **anti-vacuity triple** is tightened: (a) the patched symbol exists,
   (b) **the patch was reached** (a wrapper sets a flag; a mutant whose patch is never entered fails as
   vacuous), (c) the mutant's observation differs from the baseline and the gate flips to fail. Every gate
   failure names the fixture, the fact and the bytes.
6. **Contracts are enforced, not listed; pairing invariants live in the parent record's `__post_init__`**,
   never in either field's type (a build agent reading "checked at construction" per field checks each in
   isolation and skips the pair). A frozen record never aliases a caller's mutable object. A recorded
   failure carries a **closed reason id and the part name, never library or exception text** (a
   construction invariant of the failure record). Version constants are recorded symbolically in the
   contracts fingerprint.
7. **Every measured number in a document carries the command that produced it and a hash of the output, and a
   test re-runs it**; anything not re-runnable is marked "verify empirically" and is not a gate input.
8. **The review loop.** The build agent never commits. Claude validates adversarially (an independent scan, a
   seeded mutation fuzz of the fixture bodies, a planted defect per gate) and stores the reviewed diff; the
   owner commits each turn before the next.
9. **Privacy.** No real or employer mail in the repo, a fixture, a commit or a log; agents never open the
   owner's Downloads folder.
10. **Run hygiene.** DeepSeek at a 250k compaction trigger; Mimo only with `HEARTH_THINKING=disabled`; prompts
    live outside any repo. The per-turn test ceilings in the turn table are **guidelines reasoned from Phase 0,
    not measured**.

## Decisions already made (do not reopen)

- **D1:** `.eml` is parsed by the package's own scanner (stdlib gives no raw byte offsets); no `html2text`, no
  `chardet`, no GPL.
- **D2:** headers are one part, one paragraph per field, ordered, duplicates kept (identity by ordinal), an
  obs-fold is one field, each field carries `(raw_offset, raw_length)`; the header region ends at the first
  empty line and a malformed line **fails open**; addresses are tri-state; `Date` keeps raw, original offset
  and UTC, `-0000` is not `+0000`, a bad date is never repaired; `Received`, `Authentication-Results`,
  `DKIM-Signature` and `ARC-*` are claimed, never verified.
- **D3:** one text; views are predicates over `quote_level`; `quote_boundary_ordinal` and `quote_prefix_depth`
  are stored separately; every boundary has a rule id and a kind (`quote | forward | signature | list_footer |
  unknown`); two rule families; **per-view levels never reconciled across views**; signatures are candidates,
  never stripped; quoted history is labelled, never dropped; non-contiguous views are legal;
  `multipart/alternative` parts are separate with `selection`.
- **D4:** type is three recorded verdicts plus winner plus disagreement; classification is separate from
  status; size never changes classification; `decorative_hint` is `rule_id | absent`; identity is sha256, an
  occurrence is (filename, message, part path), the `1.2.3` path is a non-stable locator, duplicates are
  separate occurrences.
- **D9/D10:** every byte accounted for; never write an attachment under its raw filename; never fetch remote
  content; `cid:` resolves only to local parts; `data:` URIs are recorded and never expanded; macros inert.
- **D12 (all three rungs):** the MIME part's raw span is always exact and always carried; the decoded char span
  is always exact within its named, versioned projection; the within-part byte span is `exact` only under
  decision 8, else `part_level` with its reason and **no within-part byte span emitted**.
- **D16:** `body.plain_effectively_empty` is a **fact**, not a gap (resolved in 1.0a: it is declared in
  `FACTS` as a fact and `phase0-gaps.md` is amended accordingly).

## Decisions (final; the debate's replacement text is the wording to use)

1. **HTML parser.** Decided in Turn 1.0d by a recorded experiment, not by preference. Candidate A: stdlib
   `html.parser` plus an own stack-based element tree. Candidate B: `lxml.html`. The experiment runs a
   `HTMLParser` subclass that emits the `(event, text, get_starttag_text())` sequence over every HTML fixture,
   the resulting element tree, the fired DOM-rule spans and the projection hash, on **both pinned
   interpreters**, and for B the same plus the **libxml2 version** and `error_log`; the document states that B
   is pinned by the **wheel**, not the interpreter, and that a two-interpreter identity test says nothing
   about libxml2. The CPython version is a recorded-only run input and an input to `HTMLTEXT_VERSION`'s key
   for A. B is chosen only if its tree puts every quote container at the same node as A on the quote
   fixtures. If neither is clean, A is used with a **named unclosed-container rule** that records
   `body.html_quote_rule_gap` rather than silently closing the container (an unclosed `<blockquote>` otherwise
   swallows following new text). The element tree has its own module (`htmltree.py`) and records, per
   element, the **projected-text span** it covers and the **set of `cid:` references**. No claim about
   `html.parser` version differences is made without the fingerprint.
2. **`quote_level` is a derived rank, not a measurement.** Per view and per span: structural rules and the
   `>`-family each produce boundaries with `(rule_id, kind, ordinal)` and per-line `prefix_depth`; **only
   `kind = quote` boundaries advance the ordinal**; `forward`, `signature`, `list_footer` and `unknown`
   boundaries are recorded with their span at level 0. `level = ordinal` where a structural `quote` rule fired
   in the span, else `level = prefix_depth`. **`view.quote_level_disagreement` is recorded iff
   `quote_prefix_depth >= 1` and a structural `quote` ordinal >= 1 on the same span and the two resolved
   ranks differ**; an all-zero depth beside a fired structural rule is a normal state and never a
   disagreement. `quote_level` carries its resolution `rule_id`; nothing may threshold its magnitude (`new` =
   0, `quoted` >= 1, `full` = all are the only tests). Ordinal and depth stay stored, never averaged. A **new
   contract record** holds the per-boundary and per-view facts (`PartRecord` has no quote fields).
3. **Rule families v1** (each rule has an id and a fixture; **every vendor class and id name is "verify by the
   owner's structure-only probe"**). *Text:* the `>`-family prefix depth (the alphabet `> >`, `>>`, bare `>`,
   counted on decoded text, after RFC 3676 space-unstuffing when the part declares `format=flowed`); the
   English `On ... wrote:` marker; the Outlook flat block, keyed by **a maximal run of >= 2 adjacent labels, all
   from one language's set, in canonical order as a subsequence**, with the date slot accepting both tokens per
   language (EN `Sent:`/`Date:`, DE `Gesendet:`/`Datum:`, FR `Envoyé:`/`Date:`), separators accepting any
   whitespace run before `:` including U+00A0 and U+202F after NFC, **the language per block**, named tables
   for **English, German and French**; `Begin forwarded message:` and `-----Original Message-----` shapes
   named in a table (kind `forward` for the banner); the `-- ` signature (exactly dash dash space plus the line
   end, RFC 3676 4.3, **candidate only**); list footers (a line of at least 30 `_`, and the "You received this
   message because you are subscribed" sentence, kind `list_footer`, detection only). *DOM:* `gmail_quote` (on a
   `div` **or a `blockquote`**; the attribution wrapper adds no second ordinal), `blockquote[type=cite]`,
   Outlook `divRplyFwdMsg` and `#appendonsend` (with the **`x_` prefix** Outlook adds on rewrite),
   Thunderbird `moz-cite-prefix` and `moz-forward-container`. `body.i18n_reply_marker` fires **only on a
   label-shaped unknown-language block** (a header-like run of short `Label:` lines directly after a
   boundary-looking line), never on any absence, otherwise `body.no_boundary_found`. A class or id matching a
   known vendor prefix family (`gmail_`, `moz-`, `yahoo_`, `RplyFwdMsg`) with no table row is
   `body.html_quote_rule_gap`, never `body.no_boundary_found`. *Not v1 (owner decision 13):* the Apple
   attribution table row and Yahoo `yahoo_quoted`, until the owner confirms them from a structure-only probe;
   both still raise `body.html_quote_rule_gap`. *Declined, no id:* disclaimers and confidentiality footers, client
   taglines ("Sent from my iPhone"), quoting inside a `message/rfc822` attachment (recorded, not recursed).
   *Bottom-posting is legal, not a gap:* only a non-contiguous alternation is `body.inline_reply_interleaved`.
4. **Header projection engine: the package owns it.** Addresses: an own RFC 5322 3.4 address-list tokenizer
   (addr-spec per 3.2.3, quoted-string, CFWS per 3.2.4, group per 3.4, obs-route per 4) that emits **one span
   per address**, preserves group members, yields a group with zero members for `undisclosed-recipients:;`,
   records IDN and SMTPUTF8 verbatim (never IDNA-normalised), and makes an unparseable address tri-state
   `unknown(reason_id)` with the raw value beside it. Dates: an own RFC 5322 3.3 date-time parser (optional day
   name, obs-zone table, range checks, offset limit +/-9959) in one file, one entry point, no timezone database,
   **never raising on input content**; the zone has three recorded states, `zone_stated`,
   `zone_stated_minus_zero` (`-0000`, never read as UTC) and `zone_absent`, and a missing or invalid date sorts
   at one named end with a reason, never as an epoch. `email.utils` and `email.headerregistry` appear **only in
   tests**, as an advisory comparator (its disagreement is recorded and printed, never a gate); a test asserts
   that the own parser returns a reason id exactly where `parsedate_to_datetime` raises. Version differences
   between interpreters or patch levels are recorded-only run inputs.
5. **Encoded words and RFC 2231.** The package validates (the stdlib decodes invalid words silently with
   `defects = []`): `headers.encoded_word_invalid` on a charset that does not resolve, a B-encoding that is not
   well-formed base64 or has wrong padding, a Q-encoding with a stray `=`, bad hex or a raw `?`. Unfold first
   (RFC 5322 2.2.3 keeps the whitespace), then RFC 2047 5(1) (no adjacency to non-whitespace; whitespace
   between encoded words dropped); join across a split character only for the **same charset**, else
   `headers.encoded_word_invalid`. RFC 2231 continuations reassemble by index (a missing or duplicate index is an
   error); `name*` shadows `name` with the conflict recorded; a charset on segment 0 only is legal. Wild forms
   producers emit (an RFC 2047 word inside a quoted parameter; `filename*=''...` with an empty charset) are
   **decode with a recorded fallback**, not "unparsable"; `attach.filename_unparsable` is for what cannot be
   decoded.
6. **One "not built" idiom, one schema bump.** There is exactly one: `TriValue(state=UNKNOWN,
   reason_id=NOT_BUILT_IN_PHASE1)`, where `NOT_BUILT_IN_PHASE1 = "not_built_in_phase1"` is a new constant in
   `ids.py` beside `NOT_BUILT_IN_PHASE0`, registered in the design's reason-id text. `None` keeps its single
   meaning (the record family has no such axis, or the input did not exercise the field) and an empty list keeps
   its single meaning (genuinely empty). **Neither is ever the encoding of "not built".** A union `X | NotBuilt`
   is forbidden: the core codec decodes a union by its first non-`None` member, so it would not round-trip.
   *Per-record axis fields.* `AttachmentOccurrence` gains `status_axis: TriValue` and `route_axis: TriValue`;
   `EmailDocument` gains `times_axis`, `thread_edges_axis`, `children_axis` and
   `same_message_candidates_axis` (all `TriValue`). The closed axis-id tuple is `attachment.status`,
   `attachment.route`, `document.times`, `document.thread_edges`, `document.children`,
   `document.same_message_candidates`; a wildcard id is banned. The value fields keep their types. A
   document-level `deferred` list was **rejected** (it says nothing for a nested record read from a store).
   *Invariants, enforced in the parent record's `__post_init__`.* (I1) a record has an axis field iff it has the
   value field. (I2) Phase 1: `status is None` iff `status_axis` is the not-built `TriValue`; symmetric for
   `route` and the document axes. (I3) built: `status` is a `StatusOutcome` iff `status_axis == TriValue(VALUE,
   "built")`; absent keeps meaning "no such axis". (I4) any other pair raises `CodecError`; the axis reason is a
   member of the closed set `{not_built_in_phaseN, "built"}` plus `UNKNOWN(reason_id)` for
   consulted-and-unknown, so **no contract invariant depends on the current phase**. A test constructs
   `AttachmentOccurrence(status=StatusOutcome(Status.PARSED), status_axis=<not built>)` and asserts it raises; a
   scope test asserts that a build marked Phase 2 emits no record whose reason id is `NOT_BUILT_IN_PHASE1`.
   *Type verdicts.* `declared_mime`, `magic` and `container_introspection` all become `TriValue` (design D4:
   "each `value | unknown`"). `magic` consulted and nothing matched is **`VALUE("unrecognized")`**; not computed
   (zero-length part, cap hit, decode failed) is `UNKNOWN(reason_id)`; `container_introspection` is
   `UNKNOWN(not_built_in_phase1)`. `attach.type_disagreement` iff at least two verdicts are in state `VALUE`
   with a media-type family and the set of families has size >= 2 (`"unrecognized"` and `UNKNOWN` contribute no
   family and never fire it); `attach.type_unknown` iff no verdict yields a family; the winner order is `magic`
   over `declared_mime` over `container_introspection` where known, and a winner must name a known verdict.
   *Not merged: caps.* A cap hit is a **built observation**: Phase 1 **uses** the existing reasons now
   (`Status.SKIPPED(size_cap | total_size_cap | depth_cap)`, `Status.TRUNCATED(cap_hit_mid_stream)`,
   `RunRecord.cap_id` and `cap_value_bytes`). Two real defects are registered as contract work in the contract
   turn: `RunRecord` models **one** cap (a run that hits depth and total bytes records one), and the reason
   table has **no id for a part-count cap or a header-bytes cap**. *Not merged:* `FlagSection` (a reserved
   present-but-empty contract versioned by `FLAG_SCHEMA_VERSION`) and `selection` (built in Phase 1).
   *Version.* `OUTPUT_SCHEMA_VERSION` **3 to 4**; the core codec envelope is untouched; the contracts ledger
   line moves; the walk ledger line moves only in the commit that shrinks `walk.UNBUILT_SECTIONS`.
7. **Type verdicts and the magic table.** `declared_mime=text/plain` with a `PK\x03\x04` prefix is a
   disagreement and the winner is `magic` (bytes beat claims); "zip" is an honest family and a zip is never
   guessed to be docx or xlsx. The closed magic table: **zip, OLE-CFB, pdf, png, jpeg, gif, RTF (`{\rtf`),
   gzip (`1F 8B 08`), 7z (`37 7A BC AF 27 1C`), rar (`Rar!\x1a\x07`)**. Excluded deliberately: WebP and WAV/AVI
   (`RIFF` needs bytes 8-11), TIFF, `.ics` and `.eml` (text), and any text sniffing. `.msg` is OLE-CFB and needs
   no row.
8. **Offset maps and `verbatim_precision`.** The coordinate space is the part's decoded text in code points,
   **un-normalised** (no CRLF or LF folding). An offset map is built, and a span is `exact`, only for a
   **strict** decode of the **used** charset (never the declared one), over a stateless charset (single-byte or
   UTF-8), where the CTE is identity; every other case is `part_level` with `cte_not_identity |
   multibyte_without_offset_map | decode_fallback`, and **no within-part byte span is emitted**. The property
   test is independent of how the map is stored: (1) spans are strictly increasing and **partition** both
   `[0, len(raw))` and `[0, len(text))`; (2) for every span `raw[bo:be].decode(used_charset) == text[cs:ce]` (a
   fresh re-decode of the slice); (3) for strict decodes `text.encode(used_charset) == raw`; (4)
   `b"".join(slices) == raw`; (5) an anti-vacuity mutant that breaks one entry's byte length must fail the gate.
   Assertions (2)-(4) are made only for stateless charsets. Exactness is a property of the **actual decode
   function** (a UTF-8 BOM stays exact for plain `utf-8` and breaks only under `utf-8-sig` or a U+FEFF strip).
   **The quote splitter, the `>`-depth counter, the offset map and the quote rules consume one line model
   (`walk._iter_lines`)**, with a test that the splitter's line starts equal `_iter_lines` over a body containing
   CR.
9. **Structural caps** are caller parameters (maximum nesting depth, part count, header bytes, decoded bytes per
   part and in total). A hit is a recorded built observation using the existing status reasons (decision 6,
   "not merged: caps"); the part-count and header-bytes reasons and the multi-cap `RunRecord` are added in the
   contract turn.
10. **The entry point.** `parse(data: bytes, container_kind=None, *, limits)`: `limits` has **no default** (a
    `Limits.untrusted()` constructor is provided for callers). With `container_kind=None` it sniffs:
    `D0CF11E0A1B11AE1` is `cfb_msg` (a named error in Phase 1: no reader, never a guess, never an exception from
    mid-parse); otherwise **RFC 822 if the bytes begin, after an optional UTF-8 BOM, with at least one `name:
    value` line before a blank line or EOF**; otherwise a **named error** (closed reason id). The BOM is
    tolerated by the sniff and handled by decision 14.
11. **`TimeEvent`s are not emitted in Phase 1**, and `times_axis` records exactly that (decision 6). The `Date`
    projection and the raw `Received` headers are recorded as header facts; the evidence layer and the conflict
    policies are Phase 3.
12. **Retained labels.** The Phase 0 sidecars' `attach.manifest`, `body.selection` and `headers.decoded` stay as
    typed. A label that contradicts a settled decision **fails the suite as a finding** (both values and the
    bytes) and the sidecar is **never edited**.

### Owner questions, decided (Claude's recommendation, delegated by the owner)

13. **The quote catalogue** is reviewed by the owner before any quote rule is written (it is the only check not
    from the same model family). v1 contains the rows of decision 3; **the Apple attribution table row and
    Yahoo `yahoo_quoted` are NOT v1** until the owner confirms them from a structure-only probe of their own
    mail (class and id names, never content); they trigger `body.html_quote_rule_gap` meanwhile. Every vendor
    class name is "verify by probe".
14. **A leading UTF-8 BOM and an mbox `From ` envelope line are tolerated**, not left as a malformed first
    field (which loses the first real header). Each is accounted as its own leading `prelude` region of the
    message (so spans still tile exactly), recorded by the new gap ids `headers.leading_bom` and
    `headers.mbox_from_line`, and the header scan starts after it. This is a **versioned walker behaviour
    change** (`EMAIL_PARSER_VERSION` 2; the symbolic fingerprint rule means it is not a contract change) made
    in Turn 1.1 with its ledger lines; no existing corpus input contains either, so the corpus fingerprints do
    not move.
15. **A forward banner reads as level 0 (`new`)**, with a `kind = forward` boundary recorded (D3: an inline
    forward is never the sender's quoted prior words). The catalogue review confirms it row by row.
16. **Localized label tables:** English, German, French. More only when the owner's mail needs them.
17. **Lone CR:** the walker's line model **stays** (changing it would invalidate frozen spans, the ledger and
    the sidecars with no design mandate). `body.lone_cr_line_terminator` is recorded as a gap, emitted in the
    header region; decision 8's single line model is the Phase 1 consequence; the independent splitter fuzz
    (below) cannot see a lone-CR framing bug and the document says so.
18. **`exact` precision is built only as decision 8 states** (identity CTE, strict stateless decode). The
    QP and base64 offset maps are **deferred to the phase that builds citations** (Phase 4): `cte_not_identity`
    is an honest, recorded choice, not a permanent one, and real mail being mostly QP or base64 means `exact`
    will rarely fire in v1.
19. **`thread.duplicate_message_id_bytes_differ`** keeps the design's id (same `Message-ID`, different bytes,
    detected at ingest); the document says why a `thread.*` id appears in a phase that defers threading: it is
    an ingest-level fact about two files, not a thread edge.
20. **Test ceilings per turn** (<= 40; <= 25 for quote turns) are guidelines (decision: operating rule 10).

### Turn 1.5c -- limits enforcement (decided by the "limits audit", `email-remaining-plan-debate.md`)

21. **A cap hit is the existing closed pair, recorded on the walk result.** `walk(container, *, limits=None)`:
    `None` is the **unbounded** walk and exists only so the Phase 0 callers, the frozen corpus and every
    pre-cap test read the bytes they always read (the entry point always passes a `Limits`). A hit is recorded,
    never raised and never truncated: the skipped bytes become **one `Region` whose `kind` is the closed cap
    reason** (`size_cap`, `total_size_cap`, `depth_cap`, `part_count_cap`, `header_bytes_cap`) with the stopped
    locator as its `path`, and one `UnknownSection(section=<that locator>, value=unknown(<that reason>))` joins
    the walker's own `unknown_sections` channel. `cap_id` is the reason id (the model's convention,
    `CapRecord(cap_id="depth_cap", ...)`), `cap_value_bytes` is the caller's `Limits` field and
    `declared_size_bytes` is the skipped region's span length, so Turn 1.9 builds `RunRecord.caps` from the
    result. **No new reason id, no new record, no contract-shape change:** a new field on `WalkResult` would
    move the behaviour ledger's `contracts` fingerprint (`behavior_ledger.contract_records()` hashes this
    module's dataclasses -- and, as Turn 1.5c found, importing a contract dataclass *into* a fingerprinted
    module moves it too), and this turn may not bump `OUTPUT_SCHEMA_VERSION`. `evals/gates.py` is unchanged:
    the regions still tile, so no-silent-drop already sees the skipped bytes.
22. **One boundary rule for all five caps: a value equal to the cap is allowed, one over is a hit.** A part is
    skipped (not emitted, `depth_cap`/`part_count_cap`/`header_bytes_cap`) or its body is skipped (`size_cap`,
    `total_size_cap`) and, for the decoded caps, its `body_sha256` is `None` -- the walker's existing idiom for
    a body it did not read, so a skipped part can never look complete or truncated. The checks run in one
    stated order: the parent's depth test, then the part-count test, then the header-bytes test (all before the
    part is read further), then the decoded budget.
23. **The decoded caps are enforced in the walker, streamed.** It is the one place a body is CTE-decoded, so
    `max_decoded_part_bytes` and `max_decoded_total_bytes` are checked there, in chunks of `walk.DECODE_CHUNK`
    (8192) input bytes, stopping the moment the decoded count would exceed the budget -- a base64 or
    quoted-printable bomb is never expanded past the cap. The budget is the tighter of the part's cap and what
    is left of the message-wide total, and the reason is the tighter one (a tie is the part's own `size_cap`);
    once the total is exactly reached, the budget is 0 and every later part with any decoded bytes is skipped
    with `total_size_cap`. `limit=None` keeps the whole-buffer decode byte for byte, so the frozen corpus and
    the two ledger lines cannot move; a test proves the streamed decode equals it over all 119 fixtures.
24. **`max_work_units_per_input_byte` is renamed `max_field_work_units_per_byte`.** A per-**field-value** budget,
    not a message-wide one (the plan debate drops the message-scope accumulator: unit kinds are not
    commensurable and a counter threaded through five layers is cross-cutting state). `Limits` is a call
    parameter, never serialised, so this is a clean rename with **no schema bump and no behaviour change**; the
    callers' `max_work_units` keyword keeps its name. `EMAIL_PARSER_VERSION` does **not** move (no corpus output
    moves under `limits=None`) and no `LIMITS_VERSION` is introduced: nothing emits it and no ledger line keys
    it.

### Turn 1.8 -- the attachment stage (the choices items 3 and 6 of the turn force)

25. **The attachment stage's two forced choices, both from the frozen corpus and both recorded as
    findings in the turn's report.** *(a) The magic verdict's not-computed reasons.* The closed
    tuple in `attach.py` is exactly four members: `magic_part_skipped_cap` (the walker skipped the
    part for a size cap: nothing was decoded, so nothing can be sniffed), `magic_body_undecodable`
    (the part has body bytes and the transfer decode produced none), `magic_body_encrypted`
    (defined and **never emitted** in Phase 1: the encrypted-OOXML prefix check needs the
    introspection decision 6 defers) and `magic_body_empty` (a zero-length body decoded fine and
    there are no bytes to sniff, so it is `UNKNOWN(magic_body_empty)` and not the
    consulted-and-clean sentinel `VALUE("unrecognized")` -- the earlier plan-debate row that made a
    zero-length leaf `UNRECOGNIZED` is replaced here). They are *not* gap ids, *not* status reasons
    and *not* in the gap registry: they are the closed reason ids of that one `TriValue`.
    *(b) The disagreement and the declared media type are read at the **container** level.* The
    frozen `attach_ole_cfb_magic` `attach.types` row (declared `application/octet-stream`, magic
    `ole-cfb`, `disagreement` false) and the frozen macro-container `gaps.later` (declared
    `application/vnd.ms-word.document.macroEnabled.12`, magic `zip`, **no** disagreement row, while
    the pdf/zip fixture does type one) are both reproduced only by reading the verdicts the way D4
    itself discusses them ("DOCX/XLSX/PPTX are all zip and `.xls`/`.doc`/`.msg` are all OLE-CFB"):
    `attach.container_family` maps the model's `type_family_of` through two closed declared-media-type
    tables (a declared OOXML type names the zip container it *is*; a declared `.doc`/`.xls`/`.msg`
    type names OLE-CFB) and a generic `application/octet-stream` claim names no family, because a
    claim of no specific type cannot contradict anything. `attach.disagrees` then applies the model's
    own set rule (>= 2 families); the design's own example (`declared_mime=text/plain` with a
    `PK\x03\x04` prefix **is** a disagreement) still holds. The winner and the families stay the
    model's functions, and the manifest's `declared_mime` column is the media type **as the header
    writes it** (the frozen macro-container row types `macroEnabled.12`, while the walker's
    `part.content_type` is lowercased and its `part.tree` label types that lowercased form).
    The turn reports both as label-versus-brief findings with their bytes; no label was edited and
    neither `model.py` nor `walk.py` was changed.
26. **The decorative hint's rule, decided by recommendation** (the undetermined entry 6 of
    `attach_decoration_tracking_pixel` the Turn 1.0c review left open; D4). `attach.decorative`
    carries `rule_id | null` per occurrence and never removes one.
    `inline_unreferenced_tracking_pixel` fires iff the occurrence is **inline**, its cid is
    **unreferenced**, its magic verdict is `png` or `gif` (never `jpeg`: JPEG dimensions are not
    read), and the image's declared pixel dimensions in the **first 24 bytes** of the decoded
    payload are exactly 1 x 1 (a PNG `IHDR` width/height at bytes 16-23, a GIF logical screen
    width/height at bytes 6-9 little-endian). `inline_unreferenced_small_image` is the **empty**
    closed set in Phase 1 -- no size threshold is fixed by the design -- so the id is in the
    vocabulary, never fires, and a test asserts it never fires. A referenced image is never a hint,
    a non-inline image is never a hint, and nothing is hinted from size alone.
27. **`attach.cid_dangling` is measured and not emitted by this phase's corpus** (a finding, not a
    preference). The registry gives the id first emission to Turn 1.8 and `attach_cid_dangling`
    types its row (locator: the **referencing part's** path), but `html_href_img_remote_and_cid`
    references `cid:logo@example.test` with no part carrying it -- its own `not_yet_labelled`
    annotation names "the Family C `attach_cid_dangling` case" -- and types no such row, while the
    oracle's `gaps.later` comparison is **exact over live ids** for every sidecar that labels it.
    No live emission can satisfy both frozen sidecars and no label is ever edited, so the measured
    dangling cids ride `attach.Attachments.dangling` (pinned by a test) and the row
    `attach_cid_dangling` types stays `not_yet`. The other eight attachment gap ids are live, which
    is exactly the set the labelled sidecars type.

### Turn 1.6 -- the TEXT quote families (the choices the turn forced)

28. **The forward banner's span (a gap in Q5).** Q5 signs the banner's kind (`forward`) and its
    level (0), not its span. Decided: the banner line through the end of the part, or to the next
    forward-family hit -- the same convention Q1 gives the Outlook block, because the content
    after the banner **is** the forwarded message. Measured consequence: a banner followed by a
    blank line, an Outlook flat block and a body is one 7-line span of depth 0.
29. **The "boundary-looking line" the i18n gap is keyed on.** The registry's trigger for
    `body.i18n_reply_marker` names it without defining it. Decided: a non-blank line that is not
    itself a short `Label:` line, ends with `:`, and carries at least two tokens
    (`Am ... schrieb Ada Sender:`, `Dne ... napsal Ada Sender:`); a bare `Subject:` is a label,
    not a boundary.
30. **A list footer fires per rule, not once per view.** The 30-`_` run and the subscribed
    sentence are separate named shapes, so a message carrying both records two `list_footer`
    rows (ordinal 0, level 0), each spanning from its own line to the end of the part.
31. **`view.quote_level_disagreement` is per view, over the view's two resolved ranks.** It fires
    iff the view's deepest prefix depth >= 1 **and** its highest `quote` ordinal >= 1 **and** those
    two ranks differ, so the design's stated Gmail case (ordinal 2 beside depth 1) records it and
    a bottom-posted single run (1 and 1) does not. Consequence, reported as a finding: a deep
    `>`-only view (ordinal 1, depth 3) and an interleaved reply (ordinals 1 and 2, depth 1) also
    record it.
32. **The quote stage's gaps are implemented but not wired into the oracle's `gaps.later` this
    turn.** `body.no_boundary_found` fires for nearly every plain view with no quoting, so wiring
    it (or the interleaving/i18n/disagreement ids) would add a corpus-wide row to fixtures whose
    labels predate the turn. The predicates are pure functions in `quote/resolve.py`, tested and
    reported with the turn; the wiring is the turn that has the reviewer's adjudication and the
    assembled record (1.7/1.9).

### Turn 1.6 adjudication (the reviewer's rulings against the bytes, after the blind run)

Turn 1.6's rules were written WITHOUT the catalogue labels; the label-blind oracle then reported 27
row differences over 19 stems (9 stems agreed outright, including the flowed, `>`-spacing,
interleaving, bottom-posting and unknown-language cases). The reviewer, who may see both, judged each
difference against the bytes and the signed decisions. Some were LABEL errors (a hand-typed
phantom trailing line, a stale row, inconsistent span ends); some were RULE differences. The
conventions below are the adjudicated reading, derived from the labels where the labels agree with
each other and with the walker's line model, and they are what 1.6b implements. The independence of
the rules from the labels held for the first run (it found real differences in both directions); it
does not hold for 1.6b, which implements stated prose conventions and is then checked again.

33. **Lines are the walker's physical lines; there is no phantom trailing line.** The walker's line
    model yields no empty line after a final terminator (`b"a\r\nb\r\n"` is two lines). A
    boundary's `prefix_depth` list has one entry per physical line it covers. Eight plain-view
    catalogue labels counted one phantom line too many (a hand-typing error) and are corrected from
    the bytes; the catalogue's own checker (`tests/test_quote_catalogue.py::quote_problems`) then
    found the same error on a ninth, **html-view** row
    (`thunderbird_moz_forward_container` part 1.2: one line, `[0, 0]` -> `[0]`), corrected with them.
34. **Span ends.** A span that reaches the end of the part includes the final line terminator; a span
    that ends before another boundary or before a blank line ends at the last NON-BLANK content line
    (no terminator, no trailing blank). Two labels typed a run at the end of the part as content-only
    and are corrected.
35. **An `On ... wrote:` attribution spans the CONTIGUOUS NON-BLANK block after it** (Q1's "whole quoted
    block"), whether the block is `>`-prefixed or not: the attribution line(s) plus every following
    line up to the first blank line, the end of the part, or the start of another boundary of kind
    forward, signature or list_footer. A blank line directly after the attribution ends the span at
    the attribution (the quoted lines that follow are then their own `gt_family` run). The Q1 rule for
    an Outlook flat block is unchanged in kind: the label block plus the content after it up to the next
    boundary of any kind or the end of the part, ending per decision 34.
36. **A `>` run lying inside an attribution's or an Outlook flat block's span is part of that boundary,
    not a second `gt_family` boundary** (one quote, one ordinal). A `>` run elsewhere (after a blank
    line, after a three-line wrapped attribution, or inside a forward span) is its own `gt_family`
    boundary. The per-line depths of the absorbing boundary still record the run's depths.
37. **`resolution_rule_id` is the rule of the FIRST structural quote boundary** (any rule other than
    `gt_family` with kind `quote`) in document order; if there is none, `gt_family` when the view has a
    quote run; if the view has no quote boundary at all, the rule of the FIRST boundary of any other kind.
38. **A view with any recognised boundary has a `body.view_levels` row**, level 0 when every boundary is a
    forward, signature or list footer (the labels of the signature, list-footer and
    `-----Original Message-----` rows type exactly that); a view with no boundary and no `>` line has no
    row (the controls). This supersedes the "no row unless a quote or `>` line" reading of turn 1.6's
    first run.
39. **A forward banner does not suppress an Outlook flat block inside it** (Q4, restated): the banner
    (decision 28: through the end of the part) and the flat block nest; both are recorded. The
    `forwarded_inline_marker` label predates Q4 and is corrected to carry the nested flat block.

**1.6b's reading of 35/36 (recorded because the prose leaves it open, and implemented as stated).**
Read together, 35's "up to the next boundary of ANY kind" and 36's "a `>` run lying inside ... is
part of that boundary" say that a `>` run is content a flat block's extent **absorbs**, not a
boundary that truncates it, while a blank line **does** end an attribution's span. So: an
attribution covers the contiguous non-blank block that follows it (a blank line directly after it
ends the span at the attribution); a flat block covers every following line up to the next forward
banner, original-message dashes, signature, list footer, other label block or attribution, or the
end of the part, and a `>` run inside that extent is part of the flat block -- one quote, one
ordinal. No committed fixture carries both a flat block and a `>` run in one view, so the
catalogue does not adjudicate the flat-block half; the inline tests of `tests/test_quote_text.py`
do. **The work-budget hit (item 8c), as the owner ruled 1.6b.** A per-part work-budget hit is
reported (`ScanResult.truncated`) and tested; it is **not** recorded in the closed cap vocabulary,
because none of the five `Status.SKIPPED` reasons fits `Limits.max_field_work_units_per_byte`, and
no id was invented. Asked, the owner ruled: **keep today's behaviour** -- the scanner stops cleanly
and the stop is reported and tested; no `UnknownSection`/`CapRecord` until an owner names a reason
id (a later turn's `model.REASON_TABLE` decision).

### Turn 1.7 -- the DOM family, the html view and the cross-family resolution

The turn's prompt states the DOM rule table and the nesting/level rules; the choices it left open,
or that the code had to fix, are recorded here as decisions 40 to 47. ``QUOTE_RULES_VERSION`` moves
**"2" -> "3"** for the DOM table, the nesting/absorption rule, the html view's span conventions and
its own level/resolution/disagreement.

40. **The DOM boundary's span is the element's projected extent, exactly** -- the element's
    ``body.html_spans`` rectangle verbatim from the tree's node-to-span map, with **no**
    final-terminator adjustment. Decision 34's clause is the **line-based** families' (the plain
    view's rules and the html view's ``gt_family``); a DOM boundary is an element extent, not a
    run, so it is **not** applied here. This is what every DOM quote span does (``gmail_quote``,
    ``blockquote_type_cite``, the Thunderbird prefix, the ``divRplyFwdMsg`` marker and the two
    composites of 41/42). **Amended in 1.7b** (was: "... with decision 34's clause applied 'where
    it applies to projection lines': when the boundary's last covered line is the **final**
    projection line, the span reaches the end of the projection and includes that line's
    terminator"): the reviewer adjudicated the first blind run's 6 ``span_length`` differences
    against the bytes, and in every one the labelled span equals the element's own ``body.html_spans``
    rectangle exactly -- e.g. ``html_gmail_quote`` part 1.2's ``div.gmail_quote`` is offset 9 length
    65 and the labelled span ends there, **before** the projection's final line terminator. The
    one DOM span that still reaches the final terminator is the **forward container**, and not by
    this clause: decision 28 gives a forward banner the banner line **through the end of the
    part**, which the plain ``forward_banner`` label does too, so change 1 does not touch it.
41. **The Outlook span.** ``divRplyFwdMsg`` / ``x_divRplyFwdMsg`` is the marker element's own
    projected extent (decision 40). ``appendonsend`` / ``x_appendonsend`` is a **sentinel** that
    carries no quoted words: its span **starts** at the projected offset of the marker's first
    following **element** sibling (the quoted history is the marker's following siblings) and
    **ends** at the end of the marker's parent's projected extent -- the parent element's own
    extent, or, the marker being a top-level ``body`` child, the block of top-level **elements**
    (the trailing text outside every element, the part's last newline, is not part of the quoted
    block). A marker with **no** following element sibling spans its own extent (possibly zero
    length, recorded and never invented away). Decision 40 applies on top. **Amended in 1.7b**
    (was: both Outlook ids spanned "from the marker element's projected offset to the end of its
    parent element's projected span -- the marker plus its following siblings ... or to the end of
    the projection when the marker has no parent element"): the reviewer adjudicated the first
    blind run's 2 ``prefix_depth`` differences against the bytes -- in ``outlook_com_appendonsend``
    the marker is an empty ``div`` at offset 9, the quoted ``div`` starts at 11, and the labelled
    boundary starts at 11 (depth ``[0]``), so the empty marker is not quoted words; and
    ``divRplyFwdMsg`` is unchanged, its own extent already covering the header block
    (``html_outlook_divrplyfwd``: the ``div`` at offset 9 length 93).
42. **A ``moz-cite-prefix`` covers the prefix element and its immediately following element
    sibling when that sibling is a ``blockquote``, with or without ``type=cite``** (one boundary,
    one ordinal). The pulled-in blockquote adds no second boundary and no second ordinal (rule 43
    keeps a standalone bare ``blockquote`` out of the table). A following sibling that is **not** a
    ``blockquote`` leaves the boundary at the prefix element alone. **Amended in 1.7b** (was:
    "... its following ``blockquote[type=cite]`` sibling ... a bare ``blockquote`` is not a table
    row either (rule 43), so it is not pulled into the boundary"): real Thunderbird emits
    ``type=cite``; the committed ``thunderbird_moz_cite_prefix`` fixture's blockquote is bare, and
    the reviewer adjudicated its html row against the bytes -- the labelled span (offset 9 length
    57) and depth ``[0, 0]`` cover the prefix **and** the bare blockquote (offset 49 length 17), so
    the ``type=cite`` requirement was the code's error, not the label's.
43. **A bare ``blockquote`` (no ``type=cite``, no ``gmail_quote`` token) is not a table row.** It
    raises no boundary and no gap; the tree's unclosed-container gap still fires for an *unclosed*
    one. The closed container list in ``htmltree`` (``blockquote``, ``div.gmail_quote``,
    ``div#divRplyFwdMsg``) is the **unclosed** rule's, not the table's.
44. **The html view's line model is the walker's one line model over the projection's UTF-8
    bytes.** No second splitter: ``dom_rules.projection_lines`` feeds ``walk.iter_lines`` the
    projection encoded as UTF-8 (no code point's UTF-8 bytes are CR/LF, so the lines are the
    text's) and maps the byte offsets back with an incremental UTF-8 reader. The projection itself
    is unchanged, so ``HTMLTEXT_VERSION`` does **not** move.
45. **A ``>`` run inside a DOM quote boundary's span is part of that boundary** (one quote, one
    ordinal), the html-side reading of decisions 35/36: the boundary's ``prefix_depth`` still
    records the run's per-line depths. A ``>`` run with no enclosing boundary is its own
    ``gt_family`` boundary.
46. **The vendor-family trigger and the one named helper.** A class **token** starting with
    ``gmail_``/``moz-``/``yahoo_``, or an id/class containing ``RplyFwdMsg``, on an element that is
    **not** a table row is ``body.html_quote_rule_gap``. ``gmail_attr`` is the single named helper
    that is part of a row (rule ``gmail_quote`` names it): it is never a gap even though its token
    starts with ``gmail_``. This reading is reported because the prompt's rule (e) says only "not
    one of the table rows above".
47. **The html rows are wired LIVE into the two quote facts, so the committed corpus is red for
    exactly the html rows of 8 stems while the reviewer adjudicates** (the same convention Turn 1.6
    used for its blind run): the measurers return both views, the comparison partitions by view and
    the gate's named red set is asserted in ``tests/test_l1_gate.py``. The **plain** rows all stay
    matched, so no pre-existing match regresses. The html gaps (``body.html_quote_rule_gap`` from
    the vendor-family trigger, ``body.no_boundary_found``, ``view.quote_level_disagreement``) stay
    **unwired** into ``gaps.later`` (decision 32's reading).

**Turn 1.7b -- the adjudication of the first blind run.** The reviewer read the 8 html
``body.quote_boundaries`` mismatches against the fixture bytes and the labels and found three DOM span
conventions wrong (all three from the 1.7 prompt, not from its reading); decisions 40, 41 and 42 are
**amended in place** above, each marked "amended in 1.7b". ``QUOTE_RULES_VERSION`` moves **"3" ->
"4"** for the three amended span conventions (the DOM spans changed); ``HTMLTEXT_VERSION`` and the
contract line do **not** move. The 1.7 tests and mutation cases are restated for them (a mutant is
added for each: the terminator extension re-added to a DOM span, the appendonsend span starting at the
marker, and the ``moz-cite-prefix`` requiring ``type=cite``), the html quote rows are live, and L1 is
now ``matched=1224 mismatched=0``.

### Turn 1.9 -- assemble, ingest, store

The turn's prompt fixes the composition and the ingest policies; the choices it left open, or that
the code had to fix, are recorded here as decisions 48 to 54. `OUTPUT_SCHEMA_VERSION` moves
**"4" -> "5"** (the record shapes changed); `EMAIL_PARSER_VERSION`, `DECODE_CHAIN_VERSION` and every
stage's own version do **not** move -- no stage's bytes changed. The **walk artifact's** key moves
with it, because the walk artifact names `output_schema_version`; a key moves with every version it
names, and that is stated in `store.py`'s module docstring.

48. **`times` is not built in Phase 1.** Decision 6 lists the four `EmailDocument` axes; the phase-1
    exit criteria say no `TimeEvent` emission exists yet (only `dates.py`'s own parser does), so all
    four are `TriValue(UNKNOWN, not_built_in_phase1)` with an **empty** value list and an **empty**
    value list is never the encoding of "not built". A built axis is `built_axis()`.
49. **`assemble` composes and computes nothing new.** It reuses `walk`, `headers.header_region`,
    `attach.attachments`, `selection.selection_rows`, `selection.display_text`,
    `quote.resolve.all_views` and `htmltext` through `quote.resolve.html_views`. It adds three pure
    re-shapings the frozen records need and no stage emits: `HeaderField` rows from the header
    region, `PartRecord` rows from the walker's parts (with the attachment stage's own
    classification/hint/verdicts for an occurrence and the walker's cap reason as the part's
    status), and the D14 `ContentFingerprint` from the selected body view.
50. **No body text is stored on the document.** A view is derived on demand from the container bytes,
    so `resolve_span` takes the **container** (an `EmailDocument` is refused with a `TypeError`: a
    citation must be made against the bytes). The document keeps the per-view evidence
    (`quote_boundaries`, `view_levels`), never the text.
51. **`RunRecord.projection_versions`, keyed by the constant's own name**, records what produced each
    derived view, and is part of the document artifact's key (it is behaviour). `run_id` is
    deliberately **not** the key: `HTMLTEXT_VERSION` stamps the CPython minor the projection ran
    under (decision 1), a recorded-only input, so a `run_id` carrying it would make one run two runs
    across interpreters.
52. **The document key and the identity projection.** The key is the container hash +
    `OUTPUT_SCHEMA_VERSION` + `EMAIL_PARSER_VERSION` + all six projection versions + the canonical
    `Limits` fingerprint (every field, in declaration order: a raised cap is a different run). A path
    and the interpreter are recorded-only and never enter it. `identity_projection` strips the run
    record's `environment` and its `projection_versions` -- the two inputs that depend on *who*
    rendered the record -- and nothing else, so two runs, two hash seeds and two interpreters agree
    on it byte for byte.
53. **Ingest policies and the manifest.** Directory order is the POSIX-normalised relative path
    compared as **UTF-8 bytes**; a symlinked directory is a `skipped(symlinked_directory)` row and is
    never recursed, while a symlinked file is read as its target; an unreadable file is
    `skipped(file_unreadable)` and one over `max_input_bytes` is `skipped(file_over_cap)`, and the
    run continues; a file the **entry point** refuses is `skipped(<named error>)` (the existing
    `parse.NAMED_ERROR_REASONS`: `not_a_message`, `cfb_msg_unsupported`, ...) -- "check what exists
    first" -- so the ingest-side skip vocabulary is the three new `ids` ids plus that closed set. The
    manifest (`path -> container_hash -> outcome`) is deterministic, is itself stored and
    codec-encoded (its id is the sha256 of its own codec bytes, so a re-ingest writes one), and no
    path ever enters a document or a cache key.
54. **`resolve_span` refuses, with one closed reason.** A positive answer is a `RawSpan` into the raw
    message and is given only where the part has a within-part byte map (an identity-decoded,
    statically-decodable text part). The `html` view, a `format=flowed` part (its map covers the
    unstuffing, but RFC 3676 reflow is deferred, so the view's coordinate space is not final), a
    non-identity transport decode, a non-stateless charset, an unknown part id, an unknown view and a
    span outside the view all return `Unresolvable(span_not_resolvable, part_id)` -- never a guess.

**Two findings this section records.** (1) `HeaderField.name` must be non-empty, so the walker's
**malformed paragraph** (a non-blank line that is neither a field nor a fold -- `parse_status !=
"ok"`, `name == ""`) cannot be a header field and is not in `EmailDocument.headers`. It is not
silently dropped from the system: the paragraph's bytes are still accounted by the walker's regions
(the no-silent-drop property, which stays green) and the header stage records
`headers.malformed_line` on its own gap channel -- but the **frozen record has no home for a
malformed line**, so a consumer reading only the record cannot see it. Reported, not fixed.
(2) `QuoteBoundary` carries `rule_id/kind/span/ordinal/prefix_depth` and **no part or view**, so
`EmailDocument.quote_boundaries` is a flat document-order sequence: its pairing to a part is the
order of `quote.resolve.all_views` (parts in tree order, boundaries in span order), which the
drift test checks against the resolver's own row functions. A consumer that needs the part of a
boundary has to re-derive the order. Reported, not fixed: the type is frozen and 1.9's allow-list
does not include its shape.

### Turn 1.10a -- corpus agreement (the choices the turn forces)

The plan (`email-remaining-plan-debate.md` table row 6) splits 1.10; 1.10a is the corpus/gate/floor
agreement. No stage output changes: `EMAIL_PARSER_VERSION`, `OUTPUT_SCHEMA_VERSION`,
`DECODE_CHAIN_VERSION` and every stage version stay. The choices the turn forced:

55. **`document.axes` is measured from the assembled record, not re-derived.** The oracle calls
    `assemble.assemble(EmlContainer(raw), limits=Limits.untrusted())` -- the caller's own bound, as
    every other measurer does -- and reads the four document-level `TriValue` axes off it, so the
    fact reports exactly what a caller stores. The attachment axes ride each occurrence, not the
    document, so they are **not** rows: the fact's rows are the four `document.*` ids in
    `model.AXIS_IDS` order.
56. **The quote stage's gap channel is wired into `gaps.later` -- filtered to `LIVE_GAP_IDS`.**
    Decision 32 recorded that 1.6/1.7 implemented the predicates and did not wire them; Turn 1.10a
    wires them, and the fact's docstring ("rows for this turn's live gap ids") is made literal by
    the filter. Exactly **one** quote id becomes live: `body.i18n_reply_marker`, the only one whose
    emission over the committed corpus is exactly the rows the frozen labels type (two sidecars, two
    rows). The rest leave the live set and are named in the phase-1 exit ledger (decision 57).
    The **address** channel joins in the same edit: `l1._gaps_later` reads `_address_gap_pairs`, so
    `headers.address_unparsable` -- labelled at phase 1 since Turn 1.2 and never measured, because
    the id was never in `LIVE_GAP_IDS` -- is compared (one sidecar). Those two are the class-`a`
    rows of the turn's classification (decision 63): now measurable, so made live.
57. **The phase-1 wait is a closed, named, committed set; the `phase1 exit` gate enforces it.**
    `tests/ledger/phase1_exit.json` holds six rows, each a class-`b` finding -- an **over-emission**
    (`body.no_boundary_found` on 102 fixtures, `view.quote_level_disagreement` on 6,
    `body.inline_reply_interleaved` on 3, each labelled on one) or a **no-emission**
    (`attach.cid_dangling`, `body.mixed_origin_quoting`, typed but emitted by nothing) -- with the
    label's own reason and the fixture bytes' sha256. The gate fails on a wait outside the set, a
    named row the corpus stops waiting on, an empty corpus and a corpus that compared nothing.
58. **The phase-1 gap gate and its mutation catalogue.** `EMITTABLE_GAP_IDS` (`evals/falsify.py`) is
    the ids a wired channel can emit: `LIVE_GAP_IDS` plus the three quote ids of decision 56.
    `PHASE1_CASES` has one mutation case per emittable id a committed fixture labels at a live row
    (22); the five no fixture exercises against the gate are **named** in `UNEXERCISED_GAP_IDS`
    (`body.html_quote_rule_gap` -- an unlabelled emission -- plus `headers.date_no_zone` and the
    three decision-57 quote ids). The mutation drops the id on **every** channel, so an id emitted
    twice cannot survive and pass the case vacuously.
59. **The corpus-completeness rules are stated over the committed corpus.** A caller may report on
    another corpus (`--root`); there, "does the corpus exercise the named rows", "does it compare
    anything" and "does it label any live gap" are **reported but not fatal**, because a subset
    legitimately carries neither. Every rule about a row that *waits* unnamed or an emission that was
    *dropped* is fatal everywhere. (Without this, no one-fixture corpus could exit 0, and the metrics
    CLI's clean-corpus contract -- a subset run -- would break.)
60. **The coverage floors: declared, achieved, ratchet.** `tests/ledger/facts_ledger.json` gains each
    phase-1 fact's `declared` floor (parsed from `docs/design/phase1-facts.md`, so the ledger and the
    design cannot drift), the `achieved` labelled and compared counts at this commit, the
    `zero_labelled` closed list (empty), the `declared_unmet` findings (11 of 20 facts fall short:
    the corpus was sized before the floors) and the `rebase` record -- `status: "proposed"`,
    `signed_by: null`, the owner signs by committing. The effective floor (`floors`) is the achieved
    count, a ratchet: a count may rise, never fall.
61. **The golden HTML projection is a committed regression pin.** One `(fixture, locator, sha256)`
    row per committed HTML part in `tests/ledger/html_projection_golden.json`, recomputed
    **in-process** on whatever interpreter reads it (so the pin holds on a one-interpreter machine);
    a second interpreter, when present, is an **additional** comparison. The interpreter label is a
    recorded-only input, like the run record's `environment`. Regeneration is
    `python tests/support/html_projection_hash.py --json` in the same commit; a second interpreter
    that still disagrees is a committed, dated, reasoned `waivers` entry, never an environment
    variable. The same shape pins the plain-text quote-label normalisation (NFC only, case-sensitive).
62. **The Phase 1 scope test replaces the Phase 0 one, and the walk-recursion finding is named.**
    `tests/test_phase1_scope.py` keeps the Phase 0 assertions (module set, import bans, name scan)
    and adds the concurrency/fetch import scan and a self-recursion scan. The scan finds
    `emailextract/walk.py::_walk_part` recursing over the parts tree (`walk.py:709`) -- which the
    exit criteria's "the walkers are iterative" does not hold for. `walk.py` is outside this turn's
    allow-list, so it is recorded, with its reason, in `KNOWN_SELF_RECURSION`: a new recursion fails,
    and the exemption cannot outlive the fact.
63. **The phase-1 waits are classified (a)/(b)/(c).** Before Turn 1.10a twelve sidecars labelled
    `gaps.later` without a comparison (a `not_yet` row each; `thread_three_refs_chain` carries two).
    Three became measurable and are live -- class **(a)**: `headers.address_unparsable` on one sidecar
    (the address channel) and `body.i18n_reply_marker` on two (the quote channel; decisions 56/57).
    Six are class **(b)**: a frozen label asserts a row no emission can satisfy without editing one,
    so they are named in `tests/ledger/phase1_exit.json` and the exit gate accepts them. Three are
    class **(c)**: their row's own phase column is 3 (`future_date_in_text`,
    `rfc2047_folded_duplicate_received`, `thread_three_refs_chain` -- `time.in_text_dates_not_extracted_v1`,
    `headers.received_chain_unverified`, `thread.parent_not_in_corpus`), so the labels themselves defer
    them and the exit gate does not count them as phase-1 waits. Nothing is tuned to satisfy a label
    another frozen label contradicts.

### Turn 1.10b -- hostile input, the licence audit and the close (the choices the turn forces)

The plan's split makes 1.10b the second half: does hostile input behave, and what does the phase
report. No stage output changes: every version constant stays where 1.10a left it, and the
selection work counter below is an observability seam, not a rule change. The choices the turn
forces:

64. **The independent splitter fuzz compares four quantities, in four named mutation classes.**
    `tests/support/boundary_splitter.py` reads a message's framing from RFC 2046 5.1 alone (its own
    line scan, its own header/body split, its own parameter reader) and is run against the walker by
    `tests/test_seeded_splitter_fuzz.py` over every fixture the splitter reads as a top-level
    multipart (49 of 119), mutated in memory at a seeded `Random(10_1002)` -- 614 mutants, no new
    fixture. The compared quantities are the four the spec names: the ordered part spans, the part
    count, the preamble/epilogue **length** per multipart, and the boundary-delimiter line spans.
    The classes are the spec's own reading of RFC ambiguity, and each is named rather than tuned:
    **gated** (the RFC is decisive -- flip a `--`, insert or delete the CRLF before a delimiter,
    truncate mid-boundary, duplicate a delimiter, transport padding, append after the close, inject a
    valid delimiter line into a body); **invariant** (a length-preserving edit inside an encoded
    body -- a base64 character or a space swapped -- must move *no* quantity, and transport padding
    must not move the offset-free shape, RFC 2046 5.1.1); **no_close** (removing the closing `--` is
    gated on `body.boundary_disagreement` and the splitter's `closed is False`, per decision 3, not
    on the four quantities); **excluded** (run, never gated: rotating a delimiter line's line ending,
    because the splitter's own line model is CRLF-only -- decision 17's honest limit, restated -- and
    a delimiter line followed by anything but LWSP, which is RFC-ambiguous). Each excluded mutant
    carries its reason in `EXCLUDED_REASONS`; the census asserts every declared kind actually fired.
65. **The fuzz's failure rule is a crash and bounded-resource property, not a correctness one.**
    Every mutant goes through the **real entry path** -- `parse`'s sniff, then the bounded walk at
    `Limits.untrusted()` -- and must return or refuse **by name**: a `NamedError` whose `reason_id`
    is in the closed `NAMED_ERROR_REASONS`. Any other `Exception` fails the test with the seed and
    the case id; `MemoryError` and `RecursionError` are named separately because they are how a
    bounded resource would show up; `BaseException` is deliberately **not** caught. A planted crash
    and a dropped `body.boundary_disagreement` each make the test fail with the seed, so the loop is
    not vacuous.
66. **The hostile set is typed in the test, never committed as fixtures, and its numbers are step
    counts.** Twelve hostile inputs (deep nesting, a part-count bomb, an enormous header block, an
    encoded-word bomb, a 10 MB single base64 run, ...) are built inline and driven end to end
    through `assemble` and `ingest_path` at caller-chosen caps; each is recorded as a `CapRecord`
    with a **closed** reason id, no input raises, and `gates.holes` is empty over the capped walk
    (D9). Three further assertions the turn owns: a **socket guard** patches every
    socket/http/urllib/ssl entry point, a full ingest runs under it, and the anti-vacuity triple
    proves the guard can fail; **no attachment is ever written under its raw filename** (the hostile
    filenames land only in recorded fields, never on a path); and the superlinearity check reads
    each stage's **deterministic step count** (doubling the input must grow it by less than the
    stated factor), never seconds -- single-threaded, which is the assumption the module-level
    counters need.
67. **The selection stage gets the work-counter seam the other stages have, and the one wall-clock
    test goes with it.** `selection.WORK` is a `walk.WorkCounter` (one step per projected element
    examined, one per `URL_ATTRIBUTES` row compared), so `tests/test_selection.py::test_the_html_stages_are_linear_on_a_megabyte_body`
    asserts an **exact** operation count on a 1 MB and a 2 MB body instead of a `perf_counter`
    timing. The operating rules forbid a clock as a gate input; the seam is observability only and
    moves no stage version.
68. **The licence audit is a test, not a reading.** `tests/test_licence_audit.py` checks the
    Apache-2.0 text and the notice holder, that `pyproject.toml` ships `LICENSE` and `NOTICE`,
    that the runtime dependency set is **exactly** `{docextract-core}` (the exit criterion), that
    `NOTICE` and the declared dependencies agree **both ways** (so an unattributed new dependency
    and a stale entry both fail), that the hand-typed `AUDITED_LICENCES` table equals `NOTICE`, and
    that no GPL/LGPL/AGPL licence text or GPL distribution appears in the audited files. Two
    findings are recorded, not fixed: the AGPL reachable through `form-extract`'s own `pdf` extra
    (so this package must request `form-extract` **plain**, and a test pins it) and `olefile`, named
    in `NOTICE` for the future `.msg` reader while **not** being a dependency of this release.
69. **The report is seven sections, and the checking test lives where the declaration says.** The
    report's required sections are the ledgers document's (f) list; `docs/design/phase1-ledgers.md`
    names the checking test `tests/test_phase1_report.py`, while the frozen declaration block names
    `tests/test_phase1_scope.py::test_the_phase1_report_sections_are_present_and_non_empty`. The
    declaration is the enforced record (both directions, `tests/test_turn_declarations.py`), so the
    test lives in the scope module; the deviation is recorded as a named resolution in the report
    itself. The test asserts each of the seven headings exactly once with a non-empty body and
    **fails naming the missing, repeated or empty section**; it does not judge the content. One
    recorded, unedited observation belongs with it: the metrics table's headline still reads "at
    phase 0" (`emailextract/evals/metrics.py:92`) -- a recorded oracle file, and the label ledger is
    additions-only, so the wording is reported in the report's "Not done" rather than edited.

### New gap ids (budget: seven; each costs a registry line, a `phase0-gaps.md` entry, a fixture and a mutation case)

`headers.duplicate_header` (generalises `duplicate_message_id`; first-win in `walk._header_value` is silent),
`headers.leading_bom`, `headers.mbox_from_line`, `body.digest_default_not_applied` (a Content-Type-less part in
`multipart/digest` is `message/rfc822`, RFC 2046 5.1.5), `attach.duplicate_content_id`,
`body.flowed_reflow_unresolved` (the soft-break **join**; only unstuffing is v1),
`body.lone_cr_line_terminator`. Deleted as wrong: `rfc2231_unhandled` (contradicts decision 5), `nested_claim`.
Everything else hearth raised is a **fact** (header line over 998 bytes, boundary over 70 characters, NUL in a
value, Content-Disposition `size`/`date` parameters recorded verbatim and never trusted) or a **decline**
(DSN semantics, TNEF, mbox splitting, a stateful-charset offset map beyond `verbatim_reason`). Existing ids stay
fully qualified (`body.*`, `headers.*`).

## Layout to create (additions)

```
emailextract/
  parse.py  headers.py  addresses.py  dates.py  rfc2047.py
  text.py              # per-part text, charset-alias table, offset maps, the one line model
  htmltree.py          # own element tree, projected-text span per element, referenced-cid set
  htmltext.py          # the HTML projection, its own htmltext_version
  quote/  __init__.py  text_rules.py  dom_rules.py  resolve.py  i18n.py
  attach.py  assemble.py  ingest.py
tools/        runboth.py    # plain runner for both interpreters (documented fallback)
tests/support/  # header scanner (stdlib, 3 comparisons) + the independent byte-level splitter
docs/design/  email-extraction-design.md (revision 3)  phase1-build-spec.md  phase1-debate.md
```

## The turns (the debate's agreed order)

| turn | content | new gap ids first emitted | test ceiling | pre-declared stop point |
|---|---|---|---|---|
| **1.0a** | **documents only**: design revision 3, the fixture catalogue (every name and the consuming turn), exact `FACTS` ids and value shapes, registry entries (all new ids registered, none emitted), the ledger format and allow-list, the contradictions of "settle in 1.0a" below | registers seven | 0 | owner commits before 1.0b |
| **1.0b** | **contract plus oracle declarations**: decision 6 (axes, `NOT_BUILT_IN_PHASE1`, three `TriValue` verdicts), the quote-boundary and view-level records, the multi-cap `RunRecord` and the part-count and header-bytes reasons, `OUTPUT_SCHEMA_VERSION` 3 to 4, ledger keys and the **pinned `FACTS` phases**, `FACTS` declarations (phase, no measurer), the additions-only label ledger and its test, `runboth.py` | none | 25 | owner commits |
| **1.0c** | fixtures and hand-typed sidecars **by fact family, non-quote first**: (1) headers/date/address, (2) body/HTML, (3) attachments/caps; at most ~30 pairs per commit; the **quote catalogue is NOT here** | none | 5 | owner commits **per family** |
| **1.0d** | entry point, limits, named errors, the HTML decision experiment (a spike plus a document; ships `htmltext_version` only) | none | 15 | owner commits |
| **1.1** | `headers.py`, `rfc2047.py`; the walker tolerance of decision 14; the header scanner (3 comparisons) | `headers.duplicate_header`, `body.lone_cr_line_terminator`, `headers.leading_bom`, `headers.mbox_from_line` | 40 | after headers, folds and raw spans; `rfc2047.py` becomes its own turn if large |
| **1.2** | `addresses.py` (own tokenizer) | none | 30 | |
| **1.3** | `dates.py` (own parser) | none | 25 | |
| **1.4** | `text.py`: per-part text, alias table, offset maps, the one line model | `body.flowed_reflow_unresolved` | 40 | |
| **1.5** | selection, `htmltree.py`, `htmltext.py` with the **node-to-span map and the referenced-cid set** | `body.digest_default_not_applied` | 40 | after `htmltree.py` and the node-to-span map, before selection and the cid set |
| *quote catalogue* | the quote fixtures and sidecars (~15-20 rows), typed and **owner-reviewed before any quote rule is written**, ledger-pinned, `A` only | none | 3 | owner reviews, then commits |
| **1.6** | quote boundaries, text family (`text_rules.py`, `i18n.py`, `resolve.py` text half) | none | 25 | |
| **1.7** | quote boundaries, DOM family and resolution | none | 25 | |
| **1.8** | `attach.py` (the manifest, identity, occurrences, classification, three verdicts, cid sets, hints) | `attach.duplicate_content_id` | 40 | |
| **1.9** | `assemble.py`, `ingest.py`, `store.py` | none | 30 | |
| **1.10** | gates over real output, the hostile set, the Phase 1 scope test, close | none | 30 | |

Contradictions of revision 1 that Turn 1.0a settles in the design revision (not left to an agent):
`body.plain_effectively_empty` is a fact (D16), not a gap; gap ids are written fully qualified; decision 6's
representation is fixed above; caps-as-statuses are used now (decision 6) and not deferred; the registry
mechanics (a new id needs a registry line, a `phase0-gaps.md` entry, a fixture and a mutation case) are named;
"Phase 1 ids living in a file called `phase0-gaps.md`" is resolved by keeping that file and adding a Phase 1
section; the design is revised **once**, in 1.0a (no second revision in the last turn).

## The independent checks

- **Stdlib scanner, three comparisons and no more** (`tests/support/`): field **names and order** from the
  compat32 raw view only (never `policy.default`'s `headerregistry`); the **content-type tree**; the **decoded
  text of benign leaves**. Addresses and dates are an **advisory** diff (printed, never a gate). Part spans are
  never compared against stdlib. It imports nothing from `emailextract`; its own header/body split and field
  split; **no shared boundary regex**; its own charset resolution through `codecs.lookup`; for HTML it compares
  element counts and ids, never projected text. Where stdlib is authoritative (disagreement is the package's
  bug): field order and duplicates, the RFC 2045 5.2 default, RFC 2046 5.1.5 digest children, `message/rfc822`
  nesting, valid RFC 2047, benign base64 and QP, RFC 2231 continuations. Where stdlib **shares the
  misreading** (agreement proves nothing; excluded from any gate): unknown CTE, truncated base64, malformed QP,
  an unknown charset, an invalid encoded word, `defects` versus returned bytes, `parseaddr`/`getaddresses` on
  garbage, **lone CR as a line break**.
- **A third check: an independent byte-level delimiter splitter** (~60 lines, `tests/support/`, never a
  library) run as a **seeded differential fuzz** against the parser, comparing the ordered list of part byte
  spans, the part count, the preamble and epilogue length per multipart, and the boundary-delimiter line
  spans. Mutations: flip a `--`; insert or delete a CRLF before a delimiter; truncate mid-boundary; duplicate a
  delimiter; rotate line endings on delimiter lines; change transport padding; append after the close
  delimiter; remove the close delimiter; inject delimiter-like text inside a part body; base64/whitespace
  mutations inside encoded bodies (which must not change any quantity). **Excluded as RFC-ambiguous** (recorded,
  not gated): a boundary that is a prefix of another in the same message; a delimiter line followed by anything
  but LWSP; a missing close delimiter (gate on `body.boundary_disagreement` instead); a message with no
  `Content-Type` that merely resembles a boundary; content that contains the boundary on purpose. Honest
  limit: its independence is **code lineage, not a different author**; the owner's probe is the strongest
  common-mode breaker.

## Exit criteria for Phase 1

- The **declared phase-1 fact-id list is pinned in the ledger** (a change to `FACTS` phases fails unless the
  ledger changes in the same commit); the **deferred set is a closed list in the ledger, empty by default**;
  L1 is 100% over every phase-1 fact with a **per-(fact x phase) coverage floor** (at least N sidecars, at
  least one with a non-trivial, non-empty value; the sparse-fact convention is not used for new facts); L1
  still fails on a wrong sidecar and on an empty or vacuous corpus; the **phase-1 gap gate** passes and fails
  when a phase-1 gap is dropped.
- `benign` is an **additions-only sidecar flag** with closed reason ids for exclusions; on every benign fixture
  the stdlib scanner's three comparisons agree and a planted defect makes each fail; stdlib version
  differences are recorded.
- Every Phase 1 gap id has a mutation case (the tightened triple) that fails the gate naming the fixture, the
  fact and the bytes, and a catalogue test fails on an uncovered id.
- No-silent-drop passes on every fixture and mutation; **boundary ordinal, prefix depth, rule id and kind are
  stored per boundary per view** (the Phase 5 precondition); every `exact` span passes the five-part property.
- **The identity projection is named** and documents are byte-identical in it across two runs, hash seeds,
  locales, time zones and **both interpreters**; the recorded-only fields (interpreter, platform, parser
  library versions) are listed and are the only difference in the full record; re-ingest is a no-op; ledger
  fingerprints are identical on both interpreters; a behaviour change without a bump makes `--check` exit 1 and
  names the constant.
- The additions-only ledger passes over sidecars, `tests/support/**` and `emailextract/evals/**`; no existing
  sidecar is modified across the phase; the label-leak test passes; the fixture set is a **superset of the
  design's Phase 1 list** (a census test).
- The seeded fuzz and the **independent splitter fuzz** pass: every mutant returns or raises the parser's
  declared failure type with a closed reason id; any other `Exception` (and `MemoryError` or `RecursionError`
  specifically, never `BaseException`) fails with the seed. This is a crash and bounded-resource property, not a
  correctness property. The hostile set (deep nesting, a part-count bomb, an enormous header block, an
  encoded-word bomb, a very long base64 run, a `data:` URI, a remote image reference) is recorded at the caps
  with a **work-per-input-byte budget** asserted non-superlinear (operation counts or a length-scaled ratio,
  **never absolute seconds**, a single-threaded assumption stated); nothing is fetched (a socket guard fails
  loudly); no attachment is written under its raw filename.
- The package imports with no sibling, no `olefile`, no `chardet` (a fresh subprocess after a full ingest); no
  `.msg`, CFB, routing, recursion, matching, threading or `TimeEvent` emission exists; no GPL anywhere.
- Final report: a **committed file** with required sections (a test checks it non-empty), a **list of named
  resolutions each with a test id**, every version bump and why, the licences, and every label-versus-parser
  disagreement citing the failing test.

## Verify empirically (no code has been run for these; each is a few lines in a scratch directory, never a
fixture; record the output and the interpreter)

1. The HTML parser fingerprint (Turn 1.0d). 2. A leading BOM: expected a malformed first field today.
3. NUL in a header value (one field, `ok`). 4. NUL in a name (`unknown`, `headers.malformed_line`).
5. Lone CR: the walker, `_iter_lines` and `email.feedparser` split identically (so no differential test may
rely on it). 6. An mbox `From ` line at byte 0. 7. `parsedate_to_datetime` raising on invalid input and
returning naive for `-0000` and a missing zone, on 3.11.15 and 3.14.3. 8. `getaddresses` across patch levels
(CVE-2023-27043 `strict`). 9. `headerregistry.AddressHeader` on the same inputs (the missing spike row).
10. The offset-map property on the stateless-charset fixtures. 11. The walker's `_header_value` first-win on a
duplicate `Content-Type`.

## Blocked on the owner (do not fake)

- **Committing each turn before the next, and 1.0a before 1.0b**; the quote catalogue review before any quote
  rule is written.
- **The owner's structure-only probe** of their own mail for vendor class and id names (the Apple and Yahoo
  rows are not v1 until then).
- **Localized label tables** beyond English, German and French, if the owner's mail needs them.
- **Real mail** never enters the repo; the unmeasured items (html.parser, libxml2 and `email` deltas across
  patch levels; whether five gap ids suffice for real mail; the test-per-turn ceilings) are settled only by
  measurement or by the owner's corpus.

## Watch-list

- **Quote detection is where the tool fails worst** (new text attributed to quoted text, or the reverse). The
  design's measured case, a Gmail reply whose plain alternative has no `>`, is the template.
- **HTML parsing is the least stable input**: the decision, the pin and the fingerprint exist so a library bump
  is a visible ledger event; an unclosed `<blockquote>` is the worst misnest.
- **A model writing the labels and a model writing the rules share misreadings** (lone CR, RFC 2046 reading):
  real producer files and the owner's probe are the only common-mode breakers.
- **Phase 1b (`.msg`) and Phase 2 (routing) reuse this phase's text and attachment records**; the shapes frozen in
  1.4 and 1.8 are what they consume.
