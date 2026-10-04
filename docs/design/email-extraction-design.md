# email-extract design

Outcome of a design debate between Claude (opening proposal) and hearth's
configured model, which read `word-extraction-design.md`, the sibling
`CLAUDE.md`, `wordextract/terms.py`, `form-extraction-design.md` and
`docextract_core/__init__.py`. Three rounds, hearth session `s167e2728`. Not a
transcript; the reasoning that changed the design is kept. Nothing here is built.
Hearth's model could not run code (its one probe was auto-denied), so every
claim about stdlib `email` behavior is a design argument, not a measurement;
Phase 0.3/1 fixtures are where those claims get tested.

## Revision 2 (second hearth round, same session `s167e2728`)

Triggered by structure-only measurements of the owner's real mail (no content was read or sent
to hearth's model; no names, addresses or text are in this doc). Two rounds. Changes:

- **D1 rewritten (AC):** `.msg` is **v1**, read by an own `olefile`-based reader, no GPL
  dependency anywhere (not optional, not in tests/dev-deps). Parser entry sniffs the container.
- **D2 amended:** a `.msg` header part is the transport-header stream; `.eml` and `.msg`
  normalize to one `EmailDocument` through `container_kind` + `container_facts` (D14).
- **D3 amended:** quote levels are **per view and per evidence family**; mixed-origin quoting
  is a recorded conflict, never reconciled across views. Plain text with no `>` prefixes is the
  case `quote_prefix_depth` cannot see.
- **D4 amended:** nameless `message/rfc822`; `text/calendar` part plus `.ics` attachment with a
  Content-ID; `.ics` parsed minimally in v1; sensitivity labels as `classification_hint`.
- **D6 amended:** `.msg` and minimal calendar leave the `unsupported` list.
- **D7 amended:** Outlook `Thread-Index`/`Thread-Topic` are claimed evidence, never arrival.
- **D8 unchanged in substance** (matching considers every non-empty alternative, D16).
- **New D13** (`.msg` reader, fixtures, encodings, spans), **D14** (container identity and
  body digest), **D15** (TimeEvent contract and the deferred timeline layer), **D16** (empty
  alternatives, selection).
- Gap registry, phasing (new Phase 1b, Phase 0 additions), open risks, "Blocked on the user"
  and "Where minds changed" updated. `phase0-build-spec.md` is **stale on `.msg`**, the
  TimeEvent doc and its conflict fixtures until Claude revises it from this outcome.

Honesty note: hearth's model still cannot run code; claims about real files were measured
locally by Claude with a structure-only probe and are stated as measurements. Claims about
stdlib `email` behavior remain design arguments until the Phase 0.0 spike.

## Revision 3 (Phase 1 Turn 1.0a): decisions 1 to 20

Phase 1 Turn 1.0a of `docs/design/phase1-build-spec.md` (revision 2) settles twenty decisions. They are
recorded here **in the spec's own wording** -- decisions 1 to 12 are the spec's "Decisions (final; the
debate's replacement text is the wording to use)" and decisions 13 to 20 are its "Owner questions,
decided", copied verbatim -- so this design, the spec and `docs/design/phase1-debate.md` cannot drift.
The **same turn** amends the design text below (D1, D2, D3, D4, D5, D6, D12, D16 and the reason-id text)
and the "Known-gap ids" registry; the design is revised **once**, here, and no later turn revises it
again (spec: "the design is revised **once**, in 1.0a"). This is a documents-only revision: no code, no
test, no fixture, no sidecar and no ledger file changes in Turn 1.0a, so every shape it names is
**specified here and built later** (the contract and the `FACTS` declarations in 1.0b, the fixtures in
1.0c, the entry point and the HTML decision experiment in 1.0d).

Decisions 1 to 12 (verbatim from the spec):

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

Decisions 13 to 20 (verbatim from the spec's "Owner questions, decided"):

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

### Contradictions of revision 1, resolved here (one place each)

The spec listed these as things Turn 1.0a must settle in the design rather than leave to a build agent. Each
is resolved **once**, below:

- **`body.plain_effectively_empty` is a FACT, not a gap** (decision 6, D16). It is declared in `FACTS` with
  the phase it becomes checkable at (Turn 1.0b), and it leaves the "Known-gap ids" registry in this turn;
  `docs/design/phase0-gaps.md` records it as a **fact entry**, in a section that says why. The D16 text below
  is amended accordingly.
- **Gap ids are written fully qualified** (`headers.*`, `body.*`, `view.*`, `attach.*`, `thread.*`, `msg.*`,
  `time.*`, `sibling.*`, `security.*`). Reason ids are compared by exact string, so a bare `boundary_disagreement`
  and a bare `decode_fallback_used` are **not** ids: the registry, `phase0-gaps.md`, a sidecar and a constant
  spell them `body.boundary_disagreement` and `body.decode_fallback_used`. The walker's `GAP_*` constants and
  the design's registry already obey this; this note makes it the rule everywhere.
- **Caps are used as statuses now, not deferred** (decision 6, D6). A cap hit that bites before an extractor
  starts is `Status.SKIPPED` with a cap reason; the run record keeps the cap id and value. The registry's
  pruned pair (`attach.size_cap_hit`, `attach.nesting_cap_hit`) stays pruned and stays out.
- **The registry mechanics are named**: adding a gap id costs a **registry line** in the design, a
  **`phase0-gaps.md` entry** in the four-question format, a **fixture** that exercises it and a **mutation
  case** in the gap gate. `tests/test_phase0_gaps.py` holds the registry and the document to each other both
  ways, so an id added on one side and not the other is a failing test, not a silent drift.
- **Where Phase 1 gap ids live**: the file keeps its name `docs/design/phase0-gaps.md` (its path is asserted
  by `tests/test_phase0_gaps.py`, and renaming it would touch a test for no gain). Phase 1's ids are added to
  the existing **families** in the registry -- `headers.*`, `body.*`, `attach.*` -- and to a new **"Phase 1"**
  section of `phase0-gaps.md`, so a reader still finds every id in one place.

## Goal

Decompose one email message (v1: a `.eml` or `.msg` file, or a directory of them) into an
addressable, stored, reproducible record: headers, a body with named quote views,
and an attachment manifest in which every attachment is routed to the sibling
extractor that owns its format (word-extract for .docx, form-extract for
PDF/XLSX, recursion for nested messages) or recorded with an explicit status.
Flag user-supplied like-terms across all of it without filtering anything.
`email-extract` (import `emailextract`) is a **thin orchestrator, not a fourth
parser, with no LLM inside**. Stakes are those of the siblings: a quoted
exclusion attributed to the wrong sender, or an attachment silently dropped, is
a real failure in a regulated-industry corpus.

Guiding principle, inherited and extended: **a default view is a projection of
the content, never the content; every projection names the rule and version
that made it; the raw bytes are the source of truth.** The email-specific
corollary found in the debate: **everything in a message is attacker text**
(headers, display names, filenames, quoted history), and thread edges and
authentication headers are *claims*, never verified facts.

## Decided

Status key: **A** = agreed by both sides; **AC** = agreed with a change from the
opening proposal (change stated); **D** = standing disagreement.

### D1. Container parsing: `.eml` (stdlib) and `.msg` (own olefile reader) in v1 (AC, revised in Revision 2)
- Revision 1 text (`.eml` only; `.msg` a v2 GPL optional extra) is **superseded**: the owner's
  real corpus is `.msg` (open-inputs item 2), so Revision 1's promotion condition was met.
- `.eml`: stdlib `email`, `policy.default`. `.msg`: an own reader over `olefile` (BSD) for a
  stated subset (D13). **No GPL dependency at all**: not `extract-msg`, not `html2text`, not as
  an optional extra, not in `tests/` or dev-dependencies. Reasons: the owner intends to publish
  under Apache-2.0 and use the tool at work; an optional GPL extra still raises a
  combined-work question the owner would have to resolve; the observed corpus is covered by the
  header-stream plus HTML-stream subset. `extract-msg` may be run by the owner by hand as a
  differential spot check; its output may be recorded as a note, it is never imported.
- **Entry point:** `parse(bytes, container_kind=None, limits=...)`. With `None` it **sniffs**
  (`D0CF11E0A1B11AE1` -> `cfb_msg`; otherwise RFC 822; otherwise a named error), because file
  extensions lie. `limits` (max sectors, directory entries, stream size, nesting depth) is
  mandatory for untrusted bytes. Hearth's addition; accepted. A non-`IPM.Note` CFB (calendar
  item, contact) is recorded with a status and a gap, never raised.
- **Amendment (Revision 3, decision 10).** Fixed as `parse(data: bytes, container_kind=None, *,
  limits)`: `limits` has **no default** (a `Limits.untrusted()` constructor is provided for callers),
  because the function cannot know which bytes are untrusted. Sniffing is `D0CF11E0A1B11AE1` ->
  `cfb_msg` (a named error in Phase 1: no reader, never a guess, never an exception from mid-parse),
  else RFC 822 if the bytes begin, **after an optional UTF-8 BOM**, with at least one `name: value`
  line before a blank line or EOF, else a **named error** (closed reason id). The named error is kept
  -- "any other bytes are RFC 822" would parse garbage as a defectful message and drop D1's named
  error. The BOM is tolerated by the sniff and handled by decision 14 (below, D2/D3).
- `.emlx` and `.mht` remain out of v1 (silent scope is what word-extract D12 was written to
  stop). mbox needs a byte-offset splitter (named gap); PST is a mail store, out.
- HTML-to-text is lxml only, as a **named projection with its own `htmltext_version`**
  (libxml2's HTML parser is not the HTML5 algorithm): pin lxml, record `parser.error_log` as
  defects, drop `<style>`/`<script>`, explicit rules for `<a href>`, `<img src>`,
  `<blockquote>`. Hearth also proposed stdlib `html.parser` for structural quote-container
  detection; one parser for both the text projection and the DOM rules is preferred and the
  choice is made in Phase 1 by fixture (both pinned). No `html2text`, no chardet.
- **Amendment (Revision 3, decision 1).** The sentence above is **superseded**: "lxml only" is no
  longer the decision. The parser is chosen in Turn 1.0d by a **recorded experiment**, not by
  preference -- candidate A (stdlib `html.parser` plus an own stack-based element tree) versus
  candidate B (`lxml.html`) -- and B is chosen only if its tree puts every quote container at the
  same node as A on the quote fixtures. B is pinned by the **wheel** (the libxml2 build), not the
  interpreter, so a two-interpreter identity test says nothing about libxml2; for A the CPython
  version is a recorded-only run input and an input to `HTMLTEXT_VERSION`'s key. If neither is clean,
  A ships with a **named unclosed-container rule** that records `body.html_quote_rule_gap` rather
  than silently closing the container (an unclosed `<blockquote>` otherwise swallows following new
  text). The element tree has its own module `htmltree.py` and records, per element, the
  **projected-text span** it covers and the **set of `cid:` references**.
- Rejected: an optional GPL `emailextract[msg]`; keeping `.msg` in v2.
- Status **AC** (hearth agreed to the own reader and tightened the no-GPL rule to include tests).

### D2. Model: headers are a *part* in the canonical address space (AC; hearth's
most load-bearing correction)
- The opening proposal kept headers as a parallel structured record. Rejected:
  every view, offset, location, citation and flag path would need a second
  implementation. Headers are instead **one part, one paragraph per header field**
  (word-extract D2: canonical address space is per part), so the matcher, views
  and citations are reused unchanged; the structured projection (From/To/Cc/Date/
  Subject/Message-ID/In-Reply-To/References, with raw value beside parsed) is a
  *projection over that part*.
- Ordered list, duplicates kept (`Received` repeats); identity is by ordinal,
  never name. A folded field (obs-fold) is ONE field. Each field carries
  `(raw_offset, raw_length)` into the content-addressed raw message; the byte
  offset is the verbatim layer and the rendered text (`headertext_version`) is a
  projection. A citation never points at the rendering when raw bytes exist.
- Field text is the rendering of name + value with the name and value as separate
  sub-spans, so a term can hit either. Matching never crosses a field boundary
  (the analogue of "never across a paragraph").
- Header region ends at the first empty line (a named rule). A non-blank line that
  is neither `name: value` nor a fold becomes its own paragraph with
  `parse_status: unknown` and gap `headers.malformed_line`; the region does **not**
  end (fail-open: ending silently loses real headers).
- Addresses are tri-state: parsed / unparseable (raw kept, `headers.address_unparsable`)
  / group syntax (`undisclosed-recipients:;`). IDN and SMTPUTF8 local parts are kept
  verbatim, never IDNA-converted (`headers.smtputf8_not_resolved`). Display names are
  attacker text and sit on the email-sourced side (D10).
- `Date`: keep raw, original offset and UTC; `-0000` ("no local time known") is
  not `+0000`; never repair bad dates; missing date sorts at one *named* end with
  a reason, never as epoch. Missing `Message-ID` is `unknown`, not `None`.
  `References` is a list (parent = last id; the whole chain is a fact).
- **Amendment (Revision 3, decision 4).** The package **owns** address and date parsing. Addresses: an
  own RFC 5322 3.4 address-list tokenizer (addr-spec per 3.2.3, quoted-string, CFWS per 3.2.4, group
  per 3.4, obs-route per 4) emitting **one span per address**, preserving group members, yielding a
  group with zero members for `undisclosed-recipients:;`, recording IDN and SMTPUTF8 verbatim, and
  making an unparseable address tri-state `unknown(reason_id)` with the raw value beside it. Dates: an
  own RFC 5322 3.3 date-time parser (optional day name, obs-zone table, range checks, offset limit
  +/-9959) in one file, **never raising on input content**; the zone has **three recorded states**,
  `zone_stated`, `zone_stated_minus_zero` (`-0000`, never read as UTC) and `zone_absent`, and a missing
  or invalid date sorts at one named end with a reason, never as an epoch. `email.utils` and
  `email.headerregistry` appear **only in tests**, as an advisory comparator (its disagreement is
  printed, never a gate), because none of `parseaddr`/`getaddresses`/`AddressHeader` returns offsets
  (D2 needs a span per address), `parsedate_tz` rewrites `-0000` to `0`, and `getaddresses`/`parseaddr`
  changed across **patch levels** with the CVE-2023-27043 backport. A test asserts the own parser
  returns a reason id exactly where `parsedate_to_datetime` raises.
- `Reply-To`, the `Received` chain, `Authentication-Results`, `DKIM-Signature`,
  `ARC-*` are recorded as **claimed**, never verified. `msg.defects` is recorded
  (free, deterministic, citable).
- **`.msg` headers (Revision 2):** the header part is the **transport-header stream**
  (the transport-headers property; tag to be verified by the Phase 0.0 spike before freezing)
  fed to the *same* RFC 822 header parser; MAPI properties are a fallback and cross-check.
  Where both exist, the **transport header is selected for the canonical view**
  (`value_source=transport_header`) and the property is kept verbatim beside it
  (`value_source=mapi_property`, `relation=agrees_after_normalization | disagrees`); where only
  the property exists (message class, sender/recipient tables when the stream lacks them) it is
  `relation=sole_source`. Header-authoritative-where-present, property-authoritative-where-absent,
  disagreement always surfaced (`headers.mapi_header_property_disagree`), the loser never dropped.
- Uniform tri-state everywhere: `value | absent | unknown(reason_id)`, with an
  `output_schema_version` (word-extract D10(A) applied).
- **Amendment (Revision 3, decision 6): the not-built reason ids.** A section that is not built yet is
  recorded as `unknown(not_built_in_phaseN)` -- the constants `NOT_BUILT_IN_PHASE0` (Phase 0) and
  **`NOT_BUILT_IN_PHASE1`** = `not_built_in_phase1` (new in Turn 1.0b, beside it in
  `emailextract/ids.py`), registered in this reason-id text. `None` keeps its single meaning (the record
  family has no such axis, or the input did not exercise the field) and an empty list keeps its single
  meaning (genuinely empty); **neither is ever the encoding of "not built"**. The closed set an axis
  reason may come from is `{not_built_in_phaseN, "built"}` plus `UNKNOWN(reason_id)` for
  consulted-and-unknown -- a contract invariant that never depends on the current phase. A union
  `X | NotBuilt` is forbidden (the core codec decodes a union by its first non-`None` member, so it
  would not round-trip); the not-built idiom is per-record `TriValue` **axis fields**
  (`AttachmentOccurrence.status_axis`/`route_axis` and `EmailDocument.times_axis`/`thread_edges_axis`/
  `children_axis`/`same_message_candidates_axis`), with the closed axis-id tuple
  `attachment.status`, `attachment.route`, `document.times`, `document.thread_edges`,
  `document.children`, `document.same_message_candidates` (a wildcard id is banned).

### D3. Body: views over one text, quote boundaries as typed facts (AC)
- The opening proposal had three flat masks. Changed: quoted text is recursive
  and arrives with **different evidence families**, so spans carry two stored
  quantities, never averaged:
  - `quote_boundary_ordinal`: structural boundaries crossed (Outlook flat
    "From/Sent/To" blocks, "On ... wrote:", HTML quote containers), with a rule id
    per boundary;
  - `quote_prefix_depth`: literal `>`-family prefix count.
  - `quote_level` is computed by a **named resolution rule** (outlook-flat uses
    ordinal; prefix family uses depth; both present has a named winner).
    Disagreement is recorded as `view.quote_level_disagreement`.
- Views are named predicates over `quote_level`: `new` = level 0, `quoted` = level
  >= 1, `full` = all. Quoted history is labeled, never dropped.
- Each boundary carries a **`kind`**: `quote | forward | signature | list_footer |
  unknown` (added in round 3). An inline "Forwarded message" is not a quote (those
  are not the sender's prior words) and is never labeled quoted. Signatures and
  list footers are detected as *candidates* only, never stripped (`body.signature_undelimited`);
  stripping is fact loss.
- **Two rule families, both recorded by id:** text rules and **DOM rules** (Gmail
  `div.gmail_quote`, `blockquote[type=cite]`, Outlook `div#divRplyFwdMsg`/`<hr>`
  plus "From:"). A text-only list cannot see HTML quoting and would attribute all
  of it to `new`, the worst failure for this tool. As in word-extract D3: record
  every rule that fired, the winner and the disagreements; no confidence scalar.
  `>` inside pasted code needs blank-line-run context, covered by the per-boundary
  rule id.
- **Per-view levels (Revision 2).** HTML and plain-text alternatives are different evidence
  families and are **never reconciled across views**. Each view emits
  `(view_id, level, rule_id, span)`; disagreement between views is a recorded conflict, not a
  resolved number. Measured real case: a Gmail client reply quoting an Outlook-authored message
  has HTML with Gmail `gmail_quote` containers plus a `blockquote` plus Outlook's
  `divRplyFwdMsg`, while the plain alternative has an `On ... wrote:` line, Outlook
  `From:/Sent:` blocks and a forward banner with **no `>` prefix at all**. `quote_prefix_depth`
  alone reads that plain text as level 0 (the worst failure for this tool); only the structural
  boundary rules see it, so an all-zero `quote_prefix_depth` next to fired structural rules is
  a normal state, not an error. A separate short Gmail reply carries both `>` prefixes and
  `On ... wrote:` in the plain part: both families fire and the named resolution rule decides,
  with the disagreement recorded. Boundaries of **mixed origin** (a Gmail container wrapping an
  Outlook block) keep one ordinal sequence per view with a per-boundary rule id and
  `body.mixed_origin_quoting`.
- Reply-marker i18n (`Am ... schrieb`, `Le ... a ecrit`) is a **named rule list or
  a named gap** (`body.i18n_reply_marker`); an English-only list must never present
  as "no boundary found" (`body.no_boundary_found`).
- **Non-contiguous views are legal** (inline replies interleave new text between
  quoted blocks). Consequence for the matcher seam (D8): word-extract *bridges*
  excluded text inside a unit (`right of [del transfer][ins termination]` is a
  true hit there); email must **not** bridge a quoted interruption. So closing is
  not a matcher constant: **the caller supplies the closable runs; the matcher
  bridges only inside a run, never across.** word-extract passes paragraphs; email
  passes contiguous same-level spans. Recorded decision `view.gap_closing_contiguous`.
- `multipart/alternative`: both parts stored as separate addressable parts with an
  `alternative_group_id` and a `selection` axis (`selected | alternative_not_selected
  | n/a`); display preference is a named recorded rule (text/plain preferred); never merged.
- Preamble and epilogue bytes are recorded (`body.preamble_bytes`,
  `body.epilogue_bytes`); sometimes the preamble is the whole message in broken mail.
- Legal states, not gaps: headers-only message, empty new text on a top-posted reply.
- Decode chain is a first-class recorded fact per part: declared CTE, declared
  charset, used CTE, used charset, `fallback_fired` (`decode_chain_version`).
  Raw bytes are canonical; decoded text is a projection. `errors='replace'` is never
  the normal path (it destroys byte round-trip).
- **Amendment (Revision 3, decisions 2, 3).** The quote model is settled. Per view and per span the
  structural rules and the `>`-family each produce boundaries carrying `(rule_id, kind, ordinal)` and
  per-line `prefix_depth`, and **only `kind = quote` boundaries advance the ordinal** -- `forward`,
  `signature`, `list_footer` and `unknown` boundaries are recorded with their span at **level 0**, so a
  message with only a forward banner has no `quoted` span. `quote_level` is a **derived rank**:
  `level = ordinal` where a structural `quote` rule fired in the span, else `level = prefix_depth`; it
  carries its resolution `rule_id`, and nothing may threshold its magnitude (`new` = 0, `quoted` >= 1,
  `full` = all are the only tests). `view.quote_level_disagreement` is recorded **iff**
  `quote_prefix_depth >= 1` **and** a structural `quote` ordinal >= 1 on the same span **and** the two
  resolved ranks differ; an all-zero depth beside a fired structural rule is a **normal state**, never a
  disagreement. Ordinal and depth stay stored, never averaged. A **new contract record** holds the
  per-boundary and per-view facts (`PartRecord` has no quote fields; it moves `OUTPUT_SCHEMA_VERSION`).
  The `>`-family (alphabet `> >`, `>>`, bare `>`) is counted on decoded text **after RFC 3676
  space-unstuffing when the part declares `format=flowed`**. The Outlook flat block keys on a maximal
  run of >= 2 adjacent labels, all from **one language's set, in canonical order as a subsequence**,
  with the date slot accepting both tokens per language (EN `Sent:`/`Date:`, DE `Gesendet:`/`Datum:`,
  FR `Envoyé:`/`Date:`) and separators accepting any whitespace run before `:` including U+00A0/U+202F
  after NFC; the language (English, German, French) is **per block**. `Begin forwarded message:` and
  `-----Original Message-----` are named shapes (kind `forward` for the banner); the `-- ` signature
  (exactly dash dash space plus the line end, RFC 3676 4.3) is a **candidate only**; a line of at least
  30 `_` is a `list_footer` candidate (detection only). The DOM rules are `gmail_quote` (on a `div`
  **or a `blockquote`**; the attribution wrapper adds no second ordinal), `blockquote[type=cite]`,
  Outlook `divRplyFwdMsg` and `#appendonsend` (with the **`x_` prefix** Outlook adds on rewrite), and
  Thunderbird `moz-cite-prefix`/`moz-forward-container`. A **forward banner reads as level 0 (`new`)**
  with a `kind = forward` boundary recorded; a class or id matching a known vendor prefix family
  (`gmail_`, `moz-`, `yahoo_`, `RplyFwdMsg`) with no table row is `body.html_quote_rule_gap`, never
  `body.no_boundary_found`. `body.i18n_reply_marker` fires **only on a label-shaped unknown-language
  block** (a header-like run of short `Label:` lines directly after a boundary-looking line), never on
  any absence. Bottom-posting is legal; only a non-contiguous alternation is
  `body.inline_reply_interleaved`. Declined with **no id**: disclaimers/confidentiality footers, client
  taglines ("Sent from my iPhone"), quoting inside a `message/rfc822` attachment. The Apple attribution
  row and Yahoo `yahoo_quoted` are **not v1** (owner decision 13) and raise `body.html_quote_rule_gap`
  meanwhile; every vendor class and id name is "verify against a structure-only probe by the owner".

### D4. Attachments: routing, identity, statuses (AC)
- **Type is three separate recorded verdicts**: `declared_mime`, `magic`,
  `container_introspection` (each `value | unknown`), plus the winner and the
  disagreement (`attach.type_disagreement`). Magic bytes alone are not enough:
  DOCX/XLSX/PPTX are all zip and `.xls`/`.doc`/`.msg` are all OLE-CFB; OOXML type
  comes from `[Content_Types].xml` plus the main part's relationship type (the
  word-extract D1 rule), OLE needs stream/CLSID introspection. An encrypted OOXML
  is a CFB, so `password_protected` is only knowable after introspection.
- **Amendment (Revision 3, decisions 6, 7).** Each of the three verdicts becomes a **`TriValue`**, not
  `str | None`: `declared_mime`, `magic`, `container_introspection`. `magic` **consulted and nothing
  matched** is `VALUE("unrecognized")` -- a closed sentinel *value*, not `UNKNOWN`; **not computed**
  (zero-length part, cap hit, decode failed) is `UNKNOWN(reason_id)`; `container_introspection` is
  `UNKNOWN(not_built_in_phase1)` until Phase 2. `attach.type_disagreement` fires **iff** at least two
  verdicts are in state `VALUE` with a media-type family and the set of families has size >= 2
  (`"unrecognized"` and `UNKNOWN` contribute no family and never fire it); `attach.type_unknown` fires
  **iff** no verdict yields a family; the **winner order is `magic` over `declared_mime` over
  `container_introspection` where known**, and a winner must name a known verdict (the existing
  construction invariant). The closed **magic table**: zip, OLE-CFB, pdf, png, jpeg, gif, RTF (`{\rtf`),
  gzip (`1F 8B 08`), 7z (`37 7A BC AF 27 1C`), rar (`Rar!\x1a\x07`). Excluded deliberately: WebP and
  WAV/AVI (`RIFF` needs bytes 8-11), TIFF, `.ics` and `.eml` (text), and **any text sniffing**; `.msg`
  is OLE-CFB and needs no row. `declared_mime=text/plain` with a `PK\x03\x04` prefix is a disagreement
  whose winner is `magic` (bytes beat claims), and a zip is never guessed to be docx or xlsx.
- Routing: PDF/XLSX -> form-extract, DOCX -> word-extract, `message/rfc822`
  recurses. Siblings are **optional extras** (PyMuPDF is AGPL-3.0 and flows through
  form-extract; email-extract itself must stay importable without either).
- **Classification** is an axis separate from status: `attachment` (disposition
  attachment, or no disposition but a filename), `inline`, `unknown` (neither;
  genuinely undeterminable, e.g. most `message/rfc822`). It defaults to **visible**
  for a legal tool, never silently promoted. `inline` + unreferenced cid ->
  `attach.cid_unreferenced`; dangling cid -> `attach.cid_dangling`.
- **Size and dimensions never change status or classification.** Size is for caps
  and warnings. A stated deterministic threshold is not a confidence scalar
  (Claude's point, conceded by hearth) but a boolean `likely_decorative` conflates
  "no rule fired" with "rule fired and said no" (hearth's point, accepted): the
  manifest carries `decorative_hint: <rule_id> | absent`, with at least
  `inline_unreferenced_small_image` and `inline_unreferenced_tracking_pixel` (a 1x1
  remote image is a security fact, not decoration). Dimensions need a recorded
  image-header decode. A decorative hint never removes an occurrence.
- **Identity**: sha256 is the content address. An *occurrence* (filename, message,
  part path) points at it; dedupe collapses storage, never occurrence. Positional
  part paths (`1.2.3`) renumber on insertion (word-extract D3's path-id problem),
  so they are recorded as an explicitly non-stable locator. Duplicate filenames
  within one message are separate occurrences (`same_name_same_message`).
  Same-filename versions across a thread are a *relation* (`same_name_versions`,
  message-date order) plus a `same_content_hash` fact. email-extract never embeds
  word-extract's `compare()` result; `compare()` is a delegating tool.
- `page_count`/`sheet_count` are the **child's facts**: shown as `sibling_derived`
  stamped with the child's version, and `unknown` when the child store is absent.
  Never copied.
- Zip: `unsupported` in v1, but the **member listing** (names, sizes, count) is
  recorded; "unsupported" must not mean "invisible". Macro-bearing files
  (.docm/.xlsm) are inert: `macro_present` fact, `macro_execution: never`, no status.
- **Revision 2 additions (measured shapes):**
  - **`message/rfc822` with no filename** (an Outlook-attached message): classification
    `unknown`; identity = part path plus content sha256; a display name may be derived from
    the nested Subject **only as a labeled projection** (`projection_rule`, derived, attacker
    text); `attach.filename_absent` recorded; it recurses as a nested message.
  - **`text/calendar` part inside `multipart/alternative` AND an `application/ics` attachment
    that has a Content-ID** in one message: both recorded, as a body-alternative part and an
    attachment occurrence. A Content-ID on an attachment does **not** change classification
    (disposition and filename decide, as before); it is recorded as `cid`, and
    `attach.cid_unreferenced` applies only to `inline`. Content-ID and Content-Location are
    different headers, both recorded, neither a type signal.
  - **`.ics` is parsed minimally in v1** (after transport decoding, with unfolding spans):
    `METHOD`, `UID`, `SEQUENCE`, `ORGANIZER`, `ATTENDEE`, `DTSTART`, `DTEND`, `DTSTAMP`,
    `CREATED`, `LAST-MODIFIED` as **claimed** structured facts. `RRULE`, `VTIMEZONE` offset
    resolution, floating times and recurrence are named gaps (D15). Status `parsed` for the
    structured subset (it was `unsupported`), unparsed constructs listed as gaps.
  - **Sensitivity labels** (`msip_labels` and similar): recorded as claimed headers verbatim
    and surfaced in the manifest as `classification_hint` (a hint, never a verdict); never
    redacted, interpreted or used to filter.
- `multipart/signed` is parsed as ordinary structure, nothing verified
  (`signature_claimed_not_verified`). `multipart/report`/DSN: `message/delivery-status` parsed
  structurally, fields recorded as claims, semantics a named gap. TNEF/`winmail.dat`
  is `unsupported`, `attach.tnef_present`.

### D5. Output contract and store: referenced stores plus a locator (AC)
- One structured result per email: headers part, body parts (with views and
  boundaries), attachment manifest, run record, `FlagSection` (D8, empty in v1).
- **Each package keeps its own store; the email store references children by
  content hash**, plus a thin *locator* (hash -> which store root has it). It is
  "referenced stores + a locator", not "one store". Reasons, by weight:
  1. a merged store must know every record schema, so email-extract would import
     the siblings' models and the "optional extra" stops being optional at the
     store layer;
  2. each sibling already stamps its own parser/codec versions (word-extract D10);
     a merged store must union them, and a shared store is exactly where
     word-extract Open risk #1 (unknown-key drop -> false cache hit) bites under
     producer skew;
  3. sha256 is already the join key;
  4. it matches the existing per-package store shape.
- Price, accepted and recorded: cross-store links are not atomic. Every child link
  is tri-state `ChildLink`: `resolved | store_absent | child_absent | version_mismatch`.
  The email manifest must stay useful with **every sibling store deleted**:
  filename, type, sha256, size are enough to re-run the sibling.
- `read_attachment(id)` resolves `sha256 -> bytes -> sibling store`, so the sibling
  re-derives from the same bytes; email-extract never hands a child *its own*
  parse of the child's format. Locator at the scale target (about 25 documents) may
  be a config of store roots checked in order; a real index is a later optimization.
- `ingest` takes one `.eml` or a directory (walked in sorted order, so
  deterministic). Duplicates across files: same raw hash -> one content address,
  one child parse, N occurrences; same `Message-ID` with different bytes ->
  `thread.duplicate_message_id_bytes_differ`, all occurrences kept, never merged
  (distinct from in-file `headers.duplicate_message_id`).
- **Amendment (Revision 3, decision 10).** The `parse` entry point `ingest` calls is `parse(data: bytes,
  container_kind=None, *, limits)`, with `limits` having **no default** (a `Limits.untrusted()`
  constructor is provided) and the sniffing / named-error rule of decision 10 (D1, amended). The
  `EmailDocument` shape itself gains the per-axis `TriValue` fields of decision 6 (`times_axis`,
  `thread_edges_axis`, `children_axis`, `same_message_candidates_axis`) and moves
  `OUTPUT_SCHEMA_VERSION` **3 to 4** in Turn 1.0b; a document-level `deferred` list is **rejected** (for
  a nested record read out of a store it says nothing).

### D6. Status vocabulary (closed; four orthogonal axes) (A, round 3)
Status is never derived from classification and never from size.
- `classification`: `attachment | inline | unknown` (D4).
- `selection`: `selected | alternative_not_selected | n/a`.
- `role`: container (`multipart/*`) and body parts carry a `role` and are never
  attachment occurrences, so they have no status.
- `status` (closed, nine members; the dead reserved `superseded` was dropped,
  because a closed enum with a dead member invites silent extension):

| status | reason required | allowed reasons / explainer |
|---|---|---|
| `parsed` | no | child result stored (link present) |
| `skipped` | yes | `size_cap`, `total_size_cap`, `depth_cap`, `part_count_cap`, `header_bytes_cap` |
| `unsupported` | no | the `detected_type` is the reason (zip, pptx, tnef; `.msg` and minimal `text/calendar` are parsed in v1, D4/D13) |
| `not_installed` | no | carries `needed_sibling`; environmental |
| `failed` | yes | `extractor_error`, `decode_failed`, `sibling_contract_error` |
| `password_protected` | no | `crypto_kind: password` |
| `encrypted` | no | `crypto_kind: certificate | drm | unknown` |
| `empty` | no | zero-length content |
| `truncated` | yes | `stream_ended_early`, `declared_length_mismatch`, `cap_hit_mid_stream` |

- A reason belongs to exactly one status. `password_protected` = opens with a
  secret the user could hold (document/zip/OOXML password); `encrypted` = no held
  secret (S/MIME, PGP, IRM/DRM). Test: does detection require identifying a
  document container that is itself gated? Yes -> `password_protected`. An opaque
  crypto blob with no document identity -> `encrypted`.
- Caps decide status by where they bite: checked **before** the extractor starts
  (v1: every extractor is whole-buffer, the only reachable path) -> `skipped` +
  cap reason; the run record keeps cap id, cap value and declared size, so a raised
  cap is a different run. `cap_hit_mid_stream` is reserved for streaming and v1
  ships no test pretending it fires. The raw message is archived whole either way,
  so caps never lose bytes.
- **Amendment (Revision 3, decisions 6, 9).** A cap hit is a **built observation, used now**, not
  deferred: `Status.SKIPPED(size_cap | total_size_cap | depth_cap)`, `Status.TRUNCATED(cap_hit_mid_stream)`,
  `RunRecord.cap_id` and `RunRecord.cap_value_bytes` are the Phase 1 vocabulary. Two real defects are
  **registered as contract work in Turn 1.0b**: `RunRecord` models **one** cap (a run that hits depth
  and total bytes records only one), and the reason table has **no id for a part-count cap or a
  header-bytes cap** -- and the multi-cap `RunRecord` plus those two reasons are added there. The
  **structural caps** are caller parameters: maximum nesting depth, part count, header bytes, decoded
  bytes per part, and decoded bytes in total. A `skipped` part carries the cap reason and the run
  record keeps the cap id and value (this is why the two cap-flavoured candidate gap ids stay pruned).
- `not_installed` and `unsupported` are **environmental** and live in the run
  record: re-running with an extra installed flips them without changing content.
- Recorded alongside, not statuses: `route`, `decorative_hint`, `size_bytes`,
  `sha256`, `occurrence_path`, `filename_raw`/`filename_decoded` (RFC 2231
  `filename*=` continuations decoded with their own decode chain), `cid`,
  `decode_chain`, `detected_type` verdicts.
- Every non-`parsed` status names a reason or a `detected_type`; nothing is
  silently dropped.

### D7. Threading: header edges are claims; no quote reconstruction in v1 (A)
- Edges come from `Message-ID`/`In-Reply-To`/`References`; date is only a sort key
  within a thread. Edges are recorded `claimed` (attacker-controlled headers) with
  `consistent_with_body_quote | conflicts` as a cross-check from the D3 boundary
  map, never an override. `parent = last id in References`; a disagreeing
  `In-Reply-To` is recorded (`thread.references_vs_in_reply_to_disagree`).
- `parent_not_in_corpus` is normal (list mail, export window). Duplicate ids ->
  `ambiguous_parent`, not a coin flip. Cycles -> `thread.cyclic`. No subject-line
  or fuzzy threading in v1 (`thread.subject_threading_not_used`, a named
  non-decision).
- **Outlook `Thread-Topic` / `Thread-Index` (Revision 2):** the raw header is canonical; a
  deterministic decode of the `Thread-Index` block (base64; 22-byte header, then 5-byte child
  blocks) is a **labeled `claimed` projection** with its own version; per-reply time deltas
  are derived from a claim. It is conversation-seed evidence only: **never an arrival time,
  never a threading override.** A *new* thread (no `In-Reply-To`/`References`) that carries
  `Thread-Topic`/`Thread-Index`/`X-MS-TNEF-Correlator` proves presence, not threading (measured
  real case). Gap `thread.thread_index_claimed_not_used_for_edges`.
- **No reconstruction of messages from quoted text in v1.** Hearth agreed and made
  the condition that makes the deferral safe: D3 must store the boundary ordinal
  and per-boundary rule id **in Phase 1**, so Phase 5 is a pure function of stored
  data (no re-parse) and each reconstructed edge is labeled with the rule that
  fired. If Phase 1 shipped only flat masks, Phase 5 would be a re-parse.
- Gating: only the header -> chain **parse** is gated (synthetic fixtures). The
  *join* needs real mail we do not have (L2 principle), so threads are **reported,
  never gated**.

### D8. Flagging and the shared matcher (AC)
- **One registry format, one `term_list_hash`, one `matcher_version`; per-store
  term lists.** "One shared config" was refined: word-extract D12 says the term
  list is the caller's or the store's only one (zero or several is an error naming
  the candidates), so a single global list would break that rule.
- Flag, never filter. `FlagHit`: `{term_group_id, term_form, match_type:
  exact|synonym|stem, location (producer-shaped: part/view/span/unit), view_id,
  quote_boundary_ordinal, quote_kind, matcher_version}`. There is no `excluded`
  field. Location is **opaque and producer-shaped**: "cell" and "page" are
  form-extract's address space; email-extract cannot produce them without
  re-deriving sibling facts. A flag in headers is just another view (D2).
- **Home: `docextract_core.match`** (hearth first leaned to a new `docmatch`
  package, then switched: path/editable deps mean a fifth repo buys isolation the
  owner cannot use, and D6 already declares the matcher generic, which by D9's own
  test is substrate). Conditions: its own `MATCHER_VERSION` (core's `CORE_VERSION`
  does not move when the matcher does), matcher names **not** re-exported in
  `docextract_core.__all__`, its own ledger entries, the core's form-extract contract
  test untouched, and word-extract D9 rewritten deliberately: *"substrate plus the
  text matcher; both frozen-by-ledger, separately versioned."*
- **The cut:** `normalize/tokenize/_fold/_token_offsets` (`wordextract/terms.py`
  ~140-187), `TermRegistry`, `term_list_hash`, `compile_registry`, and span
  scanning over `(text, view_id, runs)` move. `match_projection`/`match_part`/
  `match_document`/`_merge_views`/move/comment logic (~486-1016) know about
  part_id/views/nodes and stay in word-extract. The seam is "text + view + closable
  runs", not "a document" (see D3).
- **This is a word-extract behavior change** (matcher_version is hashed there).
  It is a separate **track S** in the word-extract repo, not an email-extract
  phase: a no-behavior-change move + re-export shim, word-extract suite green,
  `wordextract` version bump and ledger line. **Freeze the seam in email-extract
  Phase 0 (protocol + local stub); do the physical move any time before Phase 4.
  Freeze early, move late.** Phases 0-3 are not blocked on it.
- **Acceptance test for track S** (matcher_version is hashed into provenance, so
  "byte-identical hit lists" cannot be literal):
  1. serialized `TermHit` records modulo provenance/version fields byte-identical
     across every existing word-extract fixture (group, spans, view_spans, location);
  2. `term_list_hash` identical for the same registry bytes;
  3. L2 eval unchanged: recall 1.0 and identical false-positive classification counts;
  4. `tools/update_behavior_ledger.py --check` **fails** until the bump lands (the
     gate bites);
  5. shim equality: old and new import path yield equal objects; no fixture, store
     or sidecar mtime changes.
  Residual risk: if normalization shifts one code point (NFC handling), `term_list_hash`
  stays identical while hits change; only the ledger and the L2 gate catch it.
- **Rollup shape frozen in v1 so Phase 4 never bumps `output_schema_version`:**
  every record carries a `FlagSection {terms, term_list_hash|null,
  matcher_version|null, flag_schema_version, hits: [], rollup|null}`, present-but-empty
  and round-tripping. `flag_schema_version` is a **three-package contract** frozen in
  Phase 0. `rollup` is derived, recomputable, **per view never across views**
  (`scope: message|part|attachment|body_view`, `counts_by_group`,
  `quoted_counts_by_group`; each count carries ordinal and `quote_kind`), never
  authoritative, never a filter.

### D9. Robustness (A)
- Charset fallback chain and RFC 2047 decoding for headers and filenames, each
  recorded (declared -> used -> fallback fired); `headers.encoded_word_invalid`,
  `body.decode_fallback_used`, `body.decode_destroyed_bytes` when bytes were lost.
- Recursion depth and total-extracted-size caps; a cap is a *state* with the cap id,
  never silent truncation. `message/rfc822` guards self-containment.
- One bad attachment never fails the email. Per-attachment failure is a status.
- **No-silent-drop** is an invariant: every input byte is accounted for by a part
  or a recorded status (a property test; catches preamble/epilogue and
  unknown-encoding holes).

### D10. Security and privacy (A)
- All content is untrusted, headers included. The boundary is **structural, not
  prompt hygiene**: the output schema separates `source` (verbatim email content:
  subject, display names, filenames, body text, never interpreted) from `tool`
  (schema-typed values produced by the package), so no field can be mistaken for an
  instruction. It lives in the query/MCP output contract, where filenames and
  subjects are the carrier (`security.injection_boundary_applied`).
- Never write an attachment under its raw filename (content-addressed path only).
  Never fetch remote content; `cid:` resolves only to local parts; `data:` URIs are
  recorded (`body.inline_data_uri`), never expanded; `Content-Location` is never
  fetched (`security.remote_content_present`).
- Never execute macros; `.docm`/`.xlsm` are inert (D4).
- Synthetic fixtures only. Real mail (this owner works in insurance; it may be
  confidential) lives outside the repo; `fixtures/real/` is git-ignored.

### D11. Fixtures and evals (AC)
- **L1** exact oracle over **hand-typed sidecars** (header fields, body boundaries,
  attachment manifest, statuses). Gated at 100%. **Label provenance**
  (`labels_provenance: hand | generator | spec`) on every sidecar; sidecars load
  without importing the parser and are never edited to match output.
- `.eml` bytes come from a declarative generator, **but** sidecars are typed
  independently. Hearth's opening idea (one source generating both bytes and
  `expected.json`) was withdrawn: it lets a wrong MIME emitter produce a
  self-consistent wrong fixture that passes its own gate.
- A **raw hand-written `.eml` set** (sha256-frozen by test) is required wherever
  the generator would be encoding the assumption under test: malformed MIME, broken
  charset, folding, preamble-only, truncated base64, TNEF, encrypted.
- **`.msg` fixtures (Revision 2, D13):** a deterministic minimal CFB writer in `tools/`
  builds the streams a test needs; hand-typed sidecars stay independent of the writer; outputs
  are sha256-frozen. Honest limit: writer and reader share an author, so frozen digests prove
  **stability, not third-party interop**; the fixture says so beside itself. Real owner `.msg`
  files never enter the repo.
- Invariants: **no-silent-drop** (D9); **flip-one-input on the decode chain**
  (change the declared charset -> the part's projection hash changes, the raw message
  hash does not); re-ingest of unchanged input is a no-op; a deliberately wrong
  sidecar **fails** the L1 gate (falsifiability); the ledger `--check` exits 1 on an
  unledgered behavior change.
- Retrieval and thread joins are scored only against **human** labels, reported
  and not gated until such labels exist.

### D13. The `.msg` reader: subset, encodings, spans, fixtures (AC, Revision 2)
- **Primitives vs MAPI split.** `emailextract/cfb.py` holds **container primitives only**
  (v3/v4 sectors, FAT **and miniFAT** (mandatory: property streams are mostly under 4096
  bytes), directory, case-insensitive lookup, stream read, `limits`) with **no** message
  knowledge (`IPM.Note`, property ids live in a layer above). Then promotion to
  `docextract-core` when word/form-extract need legacy OLE (`attach.ole_container_unknown`) is
  a move, not a redesign. It is **not** pre-homed in core now (hearth proposed it on the
  `.doc/.xls/.ppt` argument, then withdrew: core is frozen-by-ledger substrate and the second
  consumer is speculative). Extended DIFAT is a named gap, not a crash.
- **v1 subset:** message-class gate (`IPM.Note*`; else status + gap, never raised); transport
  headers stream; body streams (plain, HTML, compressed RTF with a named **decompress-only**
  reader, RTF-to-text a named gap); subject and sender properties; recipient storages;
  attachment storages (method, filename, MIME tag, Content-ID, data, **embedded message**,
  depth <= 1 under the shared depth cap). Property ids are verified by the Phase 0.0 spike;
  **no tag is frozen by this doc**. Unreadable constructs -> status + named `msg.*` gap, never
  silently dropped.
- **String encoding ladder (deterministic, never statistical):** Unicode-typed properties are
  UTF-16LE; for 8-bit strings and body bytes: internet code page property -> message code page
  property -> all-ASCII -> strict UTF-8 -> windows-1252, with `encoding_source` recorded as an
  enum. `chardet`/`charset-normalizer` are **banned** (version-dependent output breaks
  sha256-frozen fixtures). One trailing U+0000 is recorded and stripped; raw bytes and digest
  are kept beside the decode.
- **Spans and `verbatim_precision`:** for a `.msg` the "raw message" is the CFB file and a
  header field lives in a UTF-16 stream inside it, so an offset into RFC 822 bytes does not
  exist. v1 citations for `.msg` headers and bodies are **`part_level`** with
  `verbatim_reason: container_stream`, carrying `raw_span = {stream, byte_off, byte_len}` as
  provenance. Canonical coordinates are decoded character offsets. "Verbatim" for `.msg` means
  the exact post-UTF-16LE string with CRLF kept, never wire-byte-identical. An exact
  stream-relative span is possible later (UTF-16LE is a tracked mapping); not v1.
- **Fixtures:** a deterministic **minimal CFB writer in `tools/`** (no GPL, no reader import)
  builds only the streams a test needs. Sidecars are hand-typed, independent of the writer.
  Writer and reader from one author can agree on a wrong layout, so the set includes **one
  fixture authored to Outlook's observed layout** (sector size, miniFAT placement,
  property-id set, stream names), documented as hand-built to the observed structure, **not**
  real-Outlook provenance. Real files stay outside the repo.
- **Phase 0 walker needs no CFB:** it runs against the container-neutral interface and an
  in-memory fake container; Phase 0 depending on CFB would be contracts blocked on the
  hardest component.
- Gap family `msg`: `cfb_difat_extended`, `class_not_ipm_note`, `rtf_to_text_unsupported`,
  `property_tag_unknown`, `stream_truncated`, `codepage_unresolved_ladder_used`,
  `embedded_depth_cap`, `named_property_unresolved`.

### D14. Container identity: one `EmailDocument`, honest about bytes (A, Revision 2)
- Measured: one real message exists as `.eml` and `.msg` with identical header names and
  identical HTML body bytes, but the `.eml` is `multipart/alternative` (plain + HTML) and the
  `.msg` kept only the HTML. **The container changes what a message contains**; the two cannot
  dedupe by raw hash and must not pretend to.
- `container_kind` is an enum `rfc822 | cfb_msg` plus `container_facts` (MIME tree vs sector
  size/streams/property set). `container_hash(raw)` addresses the file; `content_fingerprint`
  is separate and labeled: `body_digest = sha256(selected body bytes)` with `body_digest_view`
  recorded (HTML if present, else plain). Neither is "the" identity of the email.
- **Cross-container relation:** equal `Message-ID` (claimed) and equal `body_digest` ->
  `same_message_candidate`; equal Message-ID, different digest ->
  `thread.duplicate_message_id_bytes_differ` (D5), never a silent merge; equal digest,
  different Message-ID -> a reported conflict. A plain-only versus HTML-only pair surfaces as
  **no candidate**, not "different". Quote and signature stripping are **never** in the digest
  key (the `.msg` lost the plain part).

### D15. Time evidence and the deferred timeline layer (AC, Revision 2)
Owner question: first build an "organizer" over email, Word, Excel and PDF that tracks what
arrived first and helps an LLM understand order? **Decision: not first. Freeze a contract now,
emit evidence from parsers, build a thin read-only layer later, with named policies.**
- **Why not first:** it consumes the parsers' timestamps (email `Date`/`Received`/
  `Thread-Index`, word-extract comment/revision/core dates, xlsx/pdf metadata). Building it
  first repeats the mistake of freezing contracts before measuring. Hearth's correction,
  accepted: "thin" understates it, because ordering and conflict semantics drive what parsers
  must emit; a frozen shape is necessary, not sufficient, hence the conflict fixtures below.
- **`TimeEvent` (shape frozen in a doc in Phase 0; the code type lives in
  `emailextract/timeevent.py` until a second producer exists; promotion to `docextract-core`
  only when a third producer or a cross-package consumer appears. Doc-freeze is cheap,
  code-freeze is not):**
  `{event_id, doc_id, parent_event_id|null, kind, when_raw, when_utc | unknown(reason),
  offset | unknown, offset_origin (stated_in_text | derived_by_named_rule | absent),
  precision (year|month|day|second), ambiguity (none|day_month|timezone|relative),
  source {field|property|part, ordinal, span}, trust (claimed|derived|user_supplied|filesystem),
  usable_for_arrival_ordering}`. `kind`: `sent | received_hop | authored | modified | revision |
  comment | calendar_start | calendar_end | calendar_stamp | mentioned_in_text | fs_mtime | ...`.
  Hearth's additions: `precision` (ambiguity is not precision), structured `source.span`,
  `offset_origin`, ids. **`SEQUENCE`, `UID`, `METHOD` are calendar facts, not TimeEvents**;
  only `DTSTART/DTEND/DTSTAMP/CREATED/LAST-MODIFIED` emit events.
- **What email-extract emits in v1 (evidence only):** every `Received` hop with its timestamp
  and header ordinal, ordered by **header order, never timestamp** (clock skew); `Date` raw,
  offset, UTC (D2); the `Thread-Index` claimed decode (D7); minimal `.ics` facts (D4);
  `fs_mtime` with `trust=filesystem, usable_for_arrival_ordering=false`.
- **In-text dates** ("01/02/2026", "next Friday") are a **separate, labeled, rule-based
  extractor** with its own version, span and sentence id, `kind=mentioned_in_text`, **excluded
  from arrival ordering** (a mail mentioning next year must not mis-sort the corpus). No LLM,
  no confidence score; numeric locale-ambiguous forms carry `ambiguity=day_month`, relative
  dates `when_utc=unknown(relative)`. **Not in email v1.**
- **Arrival of non-email files** has no evidence beyond filesystem timestamps (copy time,
  unreliable): an input **only the owner can supply** (a manifest, `trust=user_supplied`).
- **Timeline layer (later):** package **`docextract-timeline`** (hearth's name; "organizer"
  implies the LLM-understands-order framing, argued out: the deliverable is a read-only
  merge/query layer, query API plus optional MCP like word-extract D12). Depends on core;
  **not inside email-extract** (else email-extract becomes the umbrella and cycles when Word
  lands). Sequenced **after email Phase 3 and after word-extract emits at least one real
  event** (the second producer proves the shape is not email-shaped).
- **No privileged ordering.** `order(policies=[...])`; **the caller must name policies, no
  implicit "all policies"**, so no order exists by omission. Each result carries `policy_id`
  plus a rule trace, and every unresolved conflict (header `Date` vs `Received` chain vs
  filesystem mtime vs authored date) is returned in a sibling list whichever policies ran.
  Candidates: `header_date_claimed`, `received_chain_header_order`, and `owner_manifest`,
  labeled distinctly as a **total-order override**, not evidence-ranked ordering. Evidence is
  never merged into one "true time". (Claude first said "never resolves conflicts, no
  default"; hearth wanted one explicit default policy; settled on several named policies and
  no default.)
- **Phase 0 gate:** 3 to 5 worked **conflict fixtures** ("Date X, Received chain Y, mtime Z")
  with hand-typed expected artifacts: the evidence listing, the named-policy order, the
  unresolved pairs. Without them the contract is unfalsifiable (hearth's hardest push,
  accepted).

### D16. Empty alternatives and view selection (A, Revision 2)
- Measured: a `text/plain` alternative of 2 bytes (effectively empty) next to a real HTML
  body. `selected` follows the recorded **display rule** (D3), unchanged;
  `body.plain_effectively_empty` is recorded as a **fact**, not a gap: a legal state, and not
  "empty new text". Matching and `body_digest` (D14) consider **every non-empty alternative**,
  never one chosen "the body".
- **Amendment (Revision 3, decision 6).** Resolved: `body.plain_effectively_empty` is a **FACT**, not a
  gap. It is **declared in `FACTS`** (Turn 1.0b) with the phase it becomes checkable at, and it
  **leaves the "Known-gap ids" registry** in this turn; `docs/design/phase0-gaps.md` records it as a
  **fact entry** (in a section that says why), not a gap entry. Turn 1.0c ships the fixture
  `plain_effectively_empty`, typed in `docs/design/phase1-fixtures.md`.
- `iso-8859-1` declared charset is **no special case**: the decode chain and `encoding_source`
  record it as for UTF-8. The real samples show quoted-printable bodies only, no base64 bodies
  and no defects; base64 and truncated-base64 behavior stays covered by synthetic raw fixtures.

### D12. Citations (A, round 2)
- **Email-level citation**: `{email: source_content_hash, part: part_id (the
  `1.2.3` path is a non-stable locator only), view: named view_id, span: [start,
  end], unit: block ordinal in part, verbatim: raw byte span}`. Header citations:
  `part = headers`, `unit = field ordinal`, span within the field, plus the field's
  raw byte span.
- **`verbatim_precision`** has three rungs:
  - the MIME part's raw span (between boundaries) is always exact and always carried;
  - a within-part raw byte span is `exact` only when the CTE is identity
    (7bit/8bit/binary) and the char->byte mapping is tracked (single-byte charset or
    a recorded offset map); otherwise `part_level`;
  - the decoded char span is always exact within its named, versioned projection.
  When `part_level`, the citation carries `verbatim_precision: part_level`,
  `verbatim_reason` (`cte_not_identity | multibyte_without_offset_map | decode_fallback`),
  `part_raw_span`, `decoded_span`, `projection_id` and version, and **must not emit
  a within-part byte span**.
- **Amendment (Revision 3, decision 8).** The three rungs above are **all kept and fixed**. A span is
  `exact` only for a **strict** decode of the **used** charset (never the declared one), over a
  **stateless** charset (single-byte or UTF-8), where the CTE is identity; every other case is
  `part_level` with `cte_not_identity | multibyte_without_offset_map | decode_fallback` (the third
  reason is **added here**) and no within-part byte span is emitted. The coordinate space is the part's
  decoded text in **code points, un-normalised** (no CRLF or LF folding); a UTF-8 BOM stays exact for
  plain `utf-8` and breaks only under `utf-8-sig` or a U+FEFF strip, because exactness is a property of
  the **actual decode function**, not the charset name. The tested property is not the circular "an
  exact span slices to the right bytes" but five independent assertions: (1) spans strictly increase and
  **partition** both `[0, len(raw))` and `[0, len(text))`; (2) for every span
  `raw[bo:be].decode(used_charset) == text[cs:ce]`; (3) for strict decodes
  `text.encode(used_charset) == raw`; (4) `b"".join(slices) == raw`; (5) an anti-vacuity mutant that
  breaks one entry's byte length fails the gate. Assertions (2)-(4) are made only for stateless
  charsets. QP and base64 offset maps are **deferred to Phase 4** (owner decision 18): `cte_not_identity`
  is an honest, recorded choice, not a permanent one. **The quote splitter, the `>`-depth counter, the
  offset map and the quote rules consume one line model, `walk._iter_lines`**, with a test that the
  splitter's line starts equal `_iter_lines` over a body containing CR.
- **Stamped with version** (a citation is meaningless without): `textmodel_version`,
  `headertext_version`, `htmltext_version`, `decode_chain_version`,
  `output_schema_version`, plus `matcher_version` on flag hits. View id is always
  explicit; no silent default.
- **Child nesting, three buckets, never mixed**:
  - *email-extract's own*: `attachment_id = sha256`, `occurrence = part path @
    message id`, `message_id`, email content hash, `route`;
  - *verbatim passthrough*: the sibling's citation exactly as the child store wrote
    it, never translated, renumbered or re-derived into email coordinates (offsets
    stay in the child's space);
  - *stamped*: `sibling`, `sibling_parser_version`, `child_store_id`,
    `child_store_revision`, `core_version`, and the email-extract version that made
    the link.
  Shape: `{via: {attachment_id, occurrence, route, child_store}, child: <verbatim
  sibling citation> | unknown(sibling.store_absent | child_absent | version_mismatch)}`.
  A missing child store makes the child citation `unknown` **whole**, never
  partially filled. Two versions of one file are two occurrences with two
  citations and a `same_content_hash` boolean; never merged.

## Known-gap ids (v1 registry; resolved by `docs/design/phase0-gaps.md` in Phase 0.6, extended in Phase 1 Turn 1.0a)

- **headers**: `malformed_line`, `unknown_field`, `no_message_id`,
  `duplicate_message_id`, `no_date`, `invalid_date`, `date_no_zone`,
  `address_unparsable`, `smtputf8_not_resolved`, `encoded_word_invalid`,
  `received_chain_unverified`, `mapi_header_property_disagree`,
  `duplicate_header`, `leading_bom`, `mbox_from_line`.
- **body**: `no_boundary_found`, `boundary_disagreement`, `html_quote_rule_gap`,
  `i18n_reply_marker`, `preamble_bytes`, `epilogue_bytes`,
  `inline_reply_interleaved`, `empty_new_text`, `signature_undelimited`,
  `decode_fallback_used`, `decode_destroyed_bytes`, `part_truncated`,
  `no_text_part`, `headers_only`, `inline_data_uri`, `mixed_origin_quoting`,
  `digest_default_not_applied`, `flowed_reflow_unresolved`, `lone_cr_line_terminator`.
- **view**: `quote_level_disagreement`, `gap_closing_contiguous`.
- **attach**: `type_unknown`, `type_disagreement`, `ole_container_unknown`,
  `zip_unexpanded`, `tnef_present`, `encrypted_ooxml`, `legacy_office_password`
  (Word/Excel 97-2003 FilePass/RC4; distinct from `encrypted_ooxml`, ECMA-376
  EncryptionInfo/EncryptedPackage), `filename_absent`, `filename_unparsable`,
  `disposition_absent`, `cid_unreferenced`, `cid_dangling`, `occurrence_repeated`,
  `macro_present_inert`, `duplicate_content_id`.
- **thread**: `no_references`, `parent_not_in_corpus`,
  `references_vs_in_reply_to_disagree`, `duplicate_message_id_ambiguous_parent`,
  `duplicate_message_id_bytes_differ`, `cyclic`, `date_only_ordering`,
  `subject_threading_not_used`, `quote_reconstruction_deferred`,
  `thread_index_claimed_not_used_for_edges`, `same_message_candidate_across_containers`.
- **msg** (Revision 2): `cfb_difat_extended`, `class_not_ipm_note`,
  `rtf_to_text_unsupported`, `property_tag_unknown`, `stream_truncated`,
  `codepage_unresolved_ladder_used`, `embedded_depth_cap`, `named_property_unresolved`.
- **time** (Revision 2): `hop_timestamp_unparsable`, `calendar_rrule_unparsed`,
  `calendar_vtimezone_unresolved`, `calendar_floating_time`, `thread_index_undecodable`,
  `in_text_dates_not_extracted_v1`, `arrival_unknown_non_email`.
- **sibling**: `store_absent`, `child_absent`, `version_mismatch`, `not_installed`,
  `contract_unknown`.
- **security**: `remote_content_present`, `macro_present`,
  `injection_boundary_applied`.
- Phase 0.6 prune (resolved): attach.size_cap_hit and attach.nesting_cap_hit are
  **pruned from this registry**. They duplicated the `skipped` reasons (D6:
  size_cap / total_size_cap / depth_cap), and the run record already keeps the cap
  id, the cap value and the declared size, so a gap id there said nothing the
  status reason did not -- a second place to disagree with the first. No committed
  fixture or sidecar named either id, so nothing on disk changed. Resolved by
  `docs/design/phase0-gaps.md`.
- Phase 1 additions (Turn 1.0a, Revision 3): the **seven** ids `headers.duplicate_header`,
  `headers.leading_bom`, `headers.mbox_from_line`, `body.digest_default_not_applied`,
  `attach.duplicate_content_id`, `body.flowed_reflow_unresolved` and
  `body.lone_cr_line_terminator` join the families above, and `body.plain_effectively_empty`
  **leaves** this registry because decision 6/D16 resolve it as a **fact**, not a gap -- so the
  registry goes from 79 to **85** ids. Each of the seven costs a registry line here, a
  `phase0-gaps.md` entry, a fixture and a mutation case (Revision 3, "the registry mechanics are
  named"). **None is emitted by any code in Turn 1.0a**: this turn only registers them, and the turn
  named beside each entry in `phase0-gaps.md` first emits it.

## Triage of items surfaced beyond the opening list

In v1: S/MIME signed (structure only, unverified); S/MIME/PGP encrypted
(status `encrypted`); calendar invites (`unsupported` part); auto-replies/DSN
(structural parse, claims, semantics a gap); duplicates across files (both kinds,
D5); directory ingest; large attachments via caps; IDN/SMTPUTF8 (verbatim);
RFC 2231 filenames; duplicate filenames in one message; cid vs `data:`;
forwarded-as-attachment (`message/rfc822` recursion); forwarded-inline (a `forward`
boundary). Named gap, detection only: signatures, list footers, mbox, `data:` URI
expansion, DSN semantics, streaming decode. Also in v1 (Revision 2): `.msg` (own reader, D13), minimal `.ics`, Outlook `Thread-Index` and sensitivity labels as claims, nameless `message/rfc822`. Out: PST, `.emlx`, `.mht`, RTF-to-text (named gap).

## Phasing

Hearth's changes to the opening order are marked.

**Phase 0: contracts, ledger, fixtures, gates, sibling contract (no parser),
six turns** (hearth's split; one turn was too much):
| turn | deliver | exit |
|---|---|---|
| 0.1 Contracts and versions | 8 frozen dataclasses over the core codec (`EmailDocument`, `PartRecord`, `HeaderField`, `AttachmentOccurrence`, `ChildLink`, `ThreadEdge`, `FlagHit` shape, `RunRecord`); all version constants; `output_schema_version` | round-trip green; **unknown key raises** (do not inherit word-extract Open risk #1; ship the strict flag locally if core has not) |
| 0.2 Ledger and reproducibility | behavior ledger + update/`--check` analogue; run record; re-ingest-no-op harness | `--check` exits 1 on an unledgered change; same bytes -> same ids on a stub |
| 0.3 Fixtures and labels | declarative `.eml` generator; 8 generated + 3 raw fixtures; hand-typed sidecars with `labels_provenance`; independent sidecar loader | regenerate -> identical sha256; raw set sha256-frozen; sidecars load without importing the parser |
| 0.4 Gates | L1 oracle; no-silent-drop property test; decode-chain flip-one-input | wrong sidecar fails the gate; no-silent-drop green over 8+3; flip-one-input green |
| 0.5 Sibling contract freeze | child-result shape; store discovery; `not_installed`; tri-state `ChildLink`; citation nesting (D12); a **fake** sibling store | contract test green against the fake; `not_installed` path green |
| 0.6 Gaps and matcher seam | gap registry + `phase0-gaps.md`; matcher seam protocol (term set + rules + caller-supplied closable runs) with a trivial local stub | every gap id resolves; seam contract test green; no matcher logic beyond the stub |

Phase 0 fixtures. Generated: `plain_simple`, `alternative_text_html`,
`multipart_mixed_wraps_alternative`, `rfc2047_folded_duplicate_received`,
`attachments_mixed` (pdf+xlsx+docx+png), `inline_cid_referenced_and_not`,
`thread_three_refs_chain`, `preamble_epilogue`. Raw hand-written: `bad_charset`,
`truncated_base64`, `malformed_mime`. The raw three are non-negotiable because the
Phase 0 gates need bytes a generator cannot honestly produce. The remaining
fixtures arrive with the phase that makes them testable, **sidecar first**.

**Phase 0 additions (Revision 2):** (a) the 0.0 spike also probes `.msg` structure with
`olefile` (transport-header property tag, body stream names, message-class property,
attachment storage layout), structure only, no content committed; (b) the container-neutral
interface plus an in-memory fake container for the skeleton walker, **no CFB in Phase 0**;
(c) `container_kind` / `container_facts` / `container_hash` / `content_fingerprint` in the 0.1
contracts; (d) the **`TimeEvent` shape frozen in a doc** (D15) and **3 to 5 conflict fixtures**
with hand-typed expected artifacts in 0.3; (e) the CFB writer is **not** Phase 0 (Phase 1b).
Spec impact: `phase0-build-spec.md` "Decisions made by the user" item 2 and the `.msg`
blocked-on-user items are stale.

**Phase 1: container-neutral contract exercised over RFC 822: headers part, body views, attachment manifest.** Fixtures:
`quoted_outlook_flat`, `quoted_prefix_gt_deep`, `inline_reply_interleaved`,
`html_only`, `html_gmail_quote`, `html_outlook_divrplyfwd`, `no_boundary_found`,
`i18n_reply_marker`, `forwarded_inline_marker`, `headers_only`. Exit: L1 100%;
boundary ordinal + rule id per boundary stored (the Phase 5 precondition); re-ingest
is a no-op; no-silent-drop green.

**Phase 1b (new, Revision 2): `.msg` reader.** Its own phase, **after** the container-neutral
Phase 1 and **before** routing (Phase 2) and threading (Phase 3), so later phases see both
containers. Deliver: `cfb.py` primitives, the MAPI layer, the `tools/` CFB writer, the sniffing
entry, `container_kind`. Fixtures: `msg_headers_only`, `msg_headers_html`,
`msg_html_only_no_plain`, `msg_rtf_compressed_body`, `msg_embedded_message`,
`msg_attachment_with_cid`, `msg_non_ipm_note`, `msg_truncated_stream`,
`msg_outlook_layout_handbuilt`, and a synthetic **cross-container pair** (same message as
`.eml` and `.msg`). Exit: L1 100% over hand-typed sidecars; the pair yields one `EmailDocument`
shape with the documented differences (`container_hash` differs, `body_digest` equal for the
HTML view); sha256 freeze on writer output; no-silent-drop green on `.msg`.

**Phase 2: routing, statuses, recursion, caps.** Fixtures: `type_lies`,
`ole_container_ambiguous`, `nested_eml_single`, `nested_eml_depth_chain`,
`zip_member_listing`, `winmail_tnef`, `encrypted_pkcs7`, `encrypted_ooxml_attachment`,
`macros_inert_docm`, `oversized_attachment`, `duplicate_filename_inline`,
`nested_eml_no_filename`, `calendar_part_plus_ics_attachment_cid`. Sibling
extras optional; every status reachable by a fixture.

**Phase 3: header-based threading and date ordering.** Fixtures:
`thread_parent_not_in_corpus`, `thread_duplicate_message_id`,
`dup_message_id_bytes_differ`, `thread_index_new_thread`, `received_hops_header_order`. Parse gated; join reported.

**Timeline layer (named, Revision 2):** `docextract-timeline`, **after Phase 3 and after
word-extract emits at least one real `TimeEvent`**; read-only merge/query, caller-named
policies only (D15). Not otherwise scheduled.

**Track S (parallel, in the word-extract repo; blocks Phase 4 only):** the D8
matcher move with its five-part acceptance test.

**Phase 4: flags and rollups** (needs track S). Fills the `FlagSection` reserved in
v1; flag fixtures arrive here.

**Phase 5 (named):** quote-reconstructed pseudo-messages as a separately labeled
layer, per-edge rule id, consuming the stored ordinals.

**Phase 6 (named):** read-only query API and optional-extra MCP server mirroring
word-extract D12: `read_email` (headers + body + manifest), `read_attachment(id)`
delegating to the sibling query API. Not finalized in the debate beyond the
citation and `source`/`tool` contracts above; ingest stays on the CLI.

## Open risks (ranked)

1. **Sibling contract drift.** The `ChildLink` and verbatim-citation passthrough
   assume the siblings' query APIs and citation shapes are stable. Phase 0.5 tests
   only a fake store; the first real round-trip is Phase 2.
2. **Track S changes shipped word-extract behavior.** The acceptance test catches
   hit differences on existing fixtures; it cannot catch a normalization shift on
   inputs no fixture covers.
3. **HTML quote rules are the weakest L1 coverage.** Synthetic Gmail/Outlook
   markup is repo-authored, so DOM rules are `spec_derived`-style unverified until
   real client output is checked (blocked on the user).
4. **stdlib `email` behavior is unmeasured** (hearth could not run a probe).
   `policy.default` defect handling, obs-fold, and raw header recovery are assumed;
   Phase 0.3 raw fixtures are where this is tested, and the design stands
   (byte offsets into raw) even if stdlib disagrees.
5. **Within-part verbatim citations** degrade to `part_level` for base64/QP bodies,
   which is most real mail. Callers see coarse spans for most citations.
6. **Non-contiguous view closing** (D3) is a new matcher-API decision made without
   a real inline-reply corpus; `view.gap_closing_contiguous` is recorded wherever it
   changes a hit so a wrong choice is findable.
7. **Locator is a config of store roots** at v1; correct at about 25 documents, not
   beyond.
8. **Streaming caps** (`cap_hit_mid_stream`) are reserved but unreachable; a future
   streaming extractor changes the cap semantics.
9. **`.msg` reader correctness** (Revision 2). Writer and reader share an author; frozen
   digests prove stability, not interop; the only third-party signal is the owner running
   `extract-msg` by hand. Property tags unverified until the Phase 0.0 spike. RTF-only
   bodies, embedded messages and attachments in `.msg` are **not** exercised by any real
   sample (the real `.msg` samples are HTML-only, attachment-less).
10. **`TimeEvent` shape is designed from one producer** (email) and its conflict fixtures are
    hand-typed by the contract's author; the word-extract second-producer gate in D15 is the
    check, and it is later.
11. **Real-corpus coverage is narrow** (five-plus messages): real broken-charset and truncated
    base64 cases are absent; DOM quote rules are now checked against the **structure** of real
    Gmail/Outlook output (container classes, not content), better than synthetic and still thin.
12. Edge cases not exercised: TNEF contents, calendar semantics, DSN semantics,
   i18n reply markers beyond the named list.

## Where minds changed

- **hearth changed Claude on:** headers as a part, not a parallel record (the
  largest change); quote *level* split into boundary ordinal + prefix depth with
  boundary `kind`; DOM rule family for HTML quoting; `multipart/alternative` stored
  as two parts; size is not a classifier (but conceded that a deterministic stated
  rule is not a scalar; settled on `decorative_hint` as `rule_id | absent`);
  three separate type verdicts; page/sheet counts are the child's facts; part-path
  renumbering; decode chain as recorded fact; thread edges are claims and joins
  not gated; seam frozen in Phase 0 and moved late; the closable-runs matcher seam;
  the three-rung `verbatim_precision`; the Phase 0 six-turn split; the tri-state
  `ChildLink`; the `source`/`tool` structural injection boundary.
- **Claude changed hearth on:** `docextract_core.match` over a new `docmatch`
  package (hearth switched); independent hand-typed sidecars (hearth withdrew its
  single-source generator idea); matcher extraction is a separate track S that does
  not block Phases 0-3 (hearth first wanted it early, then accepted freeze early /
  move late); a stated size/dimension rule is deterministic, not a confidence
  scalar; `.msg` is an owner policy question, not a technical one.

### Revision 2
- **hearth changed Claude on:** container-neutral Phase 1 then own Phase 1b (not `.msg`-first,
  not blended); sniffing entry with `limits`; the deterministic encoding ladder and chardet
  ban; `body_digest` with a recorded view; `cfb.py` scoped to primitives so promotion is a move;
  `precision` and `offset_origin` on `TimeEvent`; calendar facts are not TimeEvents;
  caller-must-name-policies and `owner_manifest` as a distinct override; `.ics` in v1;
  conflict fixtures as the contract's falsifier; the name `docextract-timeline`; "thin
  understates it"; header-authoritative-where-present for `.msg`; no GPL in tests.
- **Claude changed hearth on:** CFB reader not pre-homed in core (withdrawn); no single default
  ordering policy (withdrawn); TimeEvent type email-local until a second producer; and a
  correction of hearth's one-line claim that CID is a Content-Location fact (different headers).

## Disagreements

- **Revision 2: none standing.** Everything raised was settled in two rounds. One hearth tool
  call was auto-denied as a write attempt and the discussion stayed read-only afterwards.
- Revision 1: effectively none standing. Two stated differences that were resolved but should
  be visible: hearth wanted the matcher extraction scheduled "early"; the agreed
  position is seam early, move late (track S, before Phase 4). Hearth's
  `likely_decorative` objection was accepted in full. A closing round (a fourth
  exchange) to confirm the Phase 6 tool list and the fate of
  `attach.size_cap_hit`/`nesting_cap_hit` was not run; both are flagged above as
  open for the owner or the first build turn.

## Blocked on the user (only the owner can supply)

Nothing blocks Phase 0. Each item changes what later phases can claim, not what can
be built.

1. **Real sample emails.** Stay outside the repo (`fixtures/real/` is ignored).
   Needed for: HTML quote rules (Gmail/Outlook/Apple Mail real output), the
   thread join, i18n reply markers, whether the real corpus is `.msg`, and L2
   must-find labels with `labels_provenance: human`. Fallback: those paths are
   recorded unverified and the thread join is reported, not gated.
2. **Is the real corpus `.msg`?** ANSWERED (Revision 2): yes; `.msg` is v1. Still needed:
   `.msg` samples **with** attachments, an embedded message, an RTF-only body and a quoted
   reply (redacted, outside the repo); the real `.msg` seen are HTML-only and attachment-less.
3. **`.msg` license policy.** Revision 2 **recommends** the own reader with no GPL dependency
   at all; it is the owner's call. Confirm: (a) no GPL import in code, tests or dev-deps,
   (b) running `extract-msg` by hand for spot checks is acceptable, (c) the Apache-2.0
   publication intent.
4. **Real term lists** (shared with word-extract; `open-inputs.md` there). Flag L2
   recall cannot be gated without human must-find labels from real documents.
   Build them from public sources or a list the owner is explicitly permitted to
   use; keep them outside the repo.
5. **Employer ownership question.** This is the owner's alone to resolve. It is not
   asserted in code, docs or package metadata, and no real or employer email
   enters the repo.
6. **Approval to touch the sibling repos for track S** (a `wordextract` version
   bump, a `docextract-core` addition, a rewritten word-extract D9 line). Not
   started here.
7. **Timeline layer (D15).** (a) Confirm: not built first; `TimeEvent` shape frozen in a doc
   in Phase 0; `docextract-timeline` after email Phase 3 and a second producer. (b) An
   **owner-supplied arrival manifest** for non-email files (file hash -> date the owner
   asserts, with a note); the tool cannot invent it. (c) Which named ordering policies come
   first. (d) Whether in-text date extraction is wanted at all, and the locale for ambiguous
   numeric dates (the owner's, never a guess).
8. **More real `.msg` structure measurements** (structure-only, same privacy rule).
9. **Scope confirmations**: v1 ingest = single `.eml`/`.msg` or a directory; mbox a named
   gap; `.emlx`/`.mht`/PST out; RTF-to-text a named gap.
