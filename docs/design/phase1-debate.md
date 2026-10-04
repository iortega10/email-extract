# Phase 1 build spec: the debate with the hearth-cli model (outcome of six rounds)

Status: **the outcome of a read-only design debate over `docs/design/phase1-build-spec.md` (draft
revision 1).** Nothing here edits the spec or the design; it is the input to **revision 2** of the
spec. The design (`docs/design/email-extraction-design.md`) wins on any conflict. The sibling's
`workbook-extract/docs/design/phase1-debate.md` is the model for the shape of this file.

Method. Two models argued from RFC text, producer behaviour and the repo: Claude (this file's
author) and the hearth-cli model (its backing model is whatever the project resolves; not
assumed). Six live rounds through `hearth --json`, hearth's session `s00611884` in
`email-extract/.hearth/sessions/`. Hearth was read-only: five `gate_paused` events fired (it tried a
plan or todo tool; each was auto-denied and nothing in the repo changed; `git status` after the
debate shows only the untracked draft spec). **No code was run by either side**: every claim below
that needs a measurement is marked **verify empirically** with the exact experiment (section
"Verify empirically"). Where a citation was checked by Claude against the file it is given as
`file:line`; where it rests on hearth's reading alone it is marked "(hearth)". No real or employer
mail was opened, and `Downloads` was not touched; no input was missing for this debate.

Material that neither side could settle without real mail is in "Open questions only the owner can
answer".

## 0. The headline findings

1. **The "not built" mechanism the draft relies on does not exist in the contract** (proposals 6, 7,
   11 and the Goal's `FlagSection` line): `AttachmentOccurrence.status` is `StatusOutcome | None`
   (`model.py:499`) over a closed nine-member `Status` (`model.py:104-115`);
   `TypeVerdicts.declared_mime/magic/container_introspection` are `str | None` (`model.py:381-383`);
   the only "not built" token is `NOT_BUILT_IN_PHASE0`, legal only as a `TriValue.reason_id`. A
   `StatusOutcome | NotBuilt` union (Claude's own first proposal) **would not round-trip**: the core
   codec decodes a union by its first non-`None` member (`docextract_core/codec.py`, `decode`,
   checked by Claude in `word-extract/docextract-core`). One idiom, one schema bump (section 6).
2. **Turn 1.0a is self-contradictory and mis-ordered.** It is headed "NO CODE" but ships a ledger
   test and a contract change; and **a sidecar cannot name a fact the oracle has not declared**
   (`l1.py` module docstring: "a label naming a fact the oracle does not model at all is a hard
   failure"; `labels.load_sidecar` validates against `FACTS`). So the order is docs, then the
   contract plus `FACTS` declarations, then fixtures and sidecars, and only then code.
3. **The draft's reference scanner is not independent where it matters** (it sits on the same stdlib
   `email` as the header engine in decision 4), and **line framing is a candidate common-mode
   error**: the walker (`walk.py:197-220`, `_iter_lines`) treats a lone CR as a line terminator, and
   the stdlib `feedparser` does the same (hearth read `Lib/email/feedparser.py`; verify
   empirically), whereas RFC 5322 2.2 and 2.3 allow CR and LF only as CRLF.
4. **Quote detection has a decision bug in the draft**: the ordinal counts every structural
   boundary, so a forward banner or a `-- ` signature would be labelled "quoted", contradicting D3
   (an inline forward is never labelled quoted).

## 1. Summary per numbered topic: the twelve proposals

Status key: **AGREED**; **AGREED WITH AMENDMENT** (exact replacement text follows); **DISAGREEMENT**
(both positions and the settling evidence). "H" is hearth, "C" is Claude.

### P1. HTML parser: AGREED WITH AMENDMENT

Both sides: stdlib `html.parser` plus a small own element tree is the lean, decided in the entry-point
turn by a pinned experiment; lxml wins only if its output is identical across a **pinned libxml2**
and its tree repair does not relocate `blockquote` or `div` boundaries on the quote fixtures.

Evidence. `email-spike.md` rows f01-f03 measured lxml on 3.14.3 only ("lxml not installed" on 3.11.15),
so the draft's "identical across interpreters" is **untestable for lxml**: a two-interpreter test would
run one interpreter twice. The identity that matters for lxml is the **libxml2 build in the wheel**,
which the interpreter does not determine. For `html.parser` the interpreter *is* the pin, so the same
test is meaningful. Neither parser is "correct" on misnested HTML: `html.parser` does not imply
`html`/`body`, does not reparent a misnested table or `p` and **does not close an unclosed
`<blockquote>`**, so an unclosed Gmail quote swallows all following new text in a naive own tree
(new text attributed to quoted text: the worst failure); libxml2 repairs and **relocates** the
boundary instead. The choice is which misnest failure is preferred, decided on fixtures.

Claude's overreach, conceded: C asserted that `html.parser` "changed behaviour in recent CPython
security releases". H would not sign a specific tokenizer diff from memory and neither side can cite
one from the repo. It is recorded as **unmeasured**, never as a changelog fact.

Replacement text for spec decision 1:

> **1. HTML parser.** Decided in the entry-point turn by a recorded experiment, not by preference.
> Candidate A: stdlib `html.parser` plus an own stack-based element tree. Candidate B: `lxml.html`.
> The experiment runs a `HTMLParser` subclass that emits the `(event, text, get_starttag_text())`
> sequence over every HTML fixture, the resulting element tree, the fired DOM-rule spans and the
> projection hash, on **both pinned interpreters**, and for B the same plus the **libxml2 version**
> and `error_log`; the doc states that B is pinned by the **wheel**, not the interpreter, and that the
> two-interpreter identity test says nothing about libxml2. The stdlib (CPython) version is recorded
> as a recorded-only run input and an input to `HTMLTEXT_VERSION`'s key for A. B is chosen only if its
> tree puts every quote container at the same node as A on the quote fixtures. If neither is clean,
> A is used with a **named unclosed-container rule** that records `body.html_quote_rule_gap` rather
> than silently closing the container. The element tree has its own module (`htmltree.py`) and records,
> per element, the **projected-text span** it covers and the **set of `cid:` references** (decision
> text in turn 1.5 below). No claim about CPython html.parser version differences is made without the
> fingerprint.

### P2. `quote_level` resolution: AGREED WITH AMENDMENT

C's opening prediction ("the gap fires on every ordinary Outlook mail") was **wrong**: the draft's
rule 2 already exempts the all-zero-depth case, and D3 names the winner (so "hidden reconciliation"
was also wrong; D3's "never reconciled" is about *across views*, a different axis). What survives, and
is agreed:

- "the two numbers differ" compares **unlike units** (ordinal counts boundaries crossed; depth counts
  literal `>`) and `prefix_depth` is **per line**, not a per-view scalar, so the comparison must be per
  span;
- `quote_level` therefore denotes a boundary count in one branch and a prefix depth in the other;
  consumers must not read its magnitude;
- there is **no contract slot** for the per-boundary and per-view facts (`PartRecord` has no quote
  fields, `model.py:460-481`): a new record type, which moves `OUTPUT_SCHEMA_VERSION`;
- **the ordinal counts `kind = quote` boundaries only.** Forward, signature and list_footer boundaries
  are recorded with span, rule id and kind and contribute level 0 (D3: an inline forward is not the
  sender's prior words; a signature is never stripped). A message with only a forward banner has no
  `quoted` span. This was H's catch; C accepted it.

Replacement text for spec decision 2:

> **2. `quote_level` is a derived rank, not a measurement.** Per view and per span: structural rules and
> the `>`-family each produce boundaries with `(rule_id, kind, ordinal)` and per-line `prefix_depth`;
> **only `kind = quote` boundaries advance the ordinal**; `forward`, `signature`, `list_footer` and
> `unknown` boundaries are recorded with their span at level 0. `level = ordinal` where a structural
> `quote` rule fired in the span, else `level = prefix_depth`. **`view.quote_level_disagreement` is
> recorded iff `quote_prefix_depth >= 1` and a structural `quote` ordinal >= 1 on the same span and the
> two resolved ranks differ**; an all-zero depth beside a fired structural rule is a normal state and
> never a disagreement. `quote_level` carries its resolution `rule_id`; nothing may threshold its
> magnitude (`new` = 0, `quoted` >= 1, `full` = all are the only tests). Ordinal and depth stay
> stored, never averaged.

Residual for the owner: "a forward banner reads as `new` (level 0)" is the design's stated intent
(D3) and the highest-judgment call in the package; the owner should confirm it from the catalogue.

### P3. Text and DOM rule family v1, localized label tables: AGREED WITH AMENDMENT

"Named table or named gap" **is** implementable without heuristics, on these terms (H and C agree):

- the table is keyed by a **language's label set**, but the match key is a **maximal run of >= 2
  adjacent labels, all from one language's set, in canonical order as a subsequence**; a full
  five-tuple is too strict (`Cc:` is omitted when empty, `Subject:` is absent from some forward
  forms), and `Cc` is shared by EN/DE/FR so single words cannot identify a language;
- the **date slot accepts both tokens per language** (EN `Sent:`/`Date:`, DE `Gesendet:`/`Datum:`,
  FR `Envoyé:`/`Date:`);
- label separators accept any whitespace run before `:` including `U+00A0` and `U+202F` (French
  typography), after NFC normalisation;
- the language is **per block** (it follows the replying client's UI language, not the message);
- smallest honest set: English, German, French named; every other language is the gap
  `body.i18n_reply_marker`, **fired only on a label-shaped unknown-language block** (a header-like run
  of short `Label:` lines directly after a boundary-looking line), never on any absence, otherwise it
  is `body.no_boundary_found`.

Not folded into the Outlook rule (separate named rules): Thunderbird, Apple Mail, Yahoo.

### P4. Header projection engine: DISAGREEMENT RESOLVED to "own the rule" (AGREED WITH AMENDMENT)

H wavered once (round 3 recommended `headerregistry.AddressHeader` and called decision 4 "not a
decision") and **withdrew it in round 4 as a self-correction**; C's position held:

- the spike measured only `email.utils` (rows a05, a06); **no row measured `headerregistry`**, so
  "where the spike measured it stable" is nearly empty;
- `parseaddr`/`getaddresses` changed with `strict` in the CVE-2023-27043 fix, backported across
  **maintenance** releases of 3.11/3.12/3.13, so behaviour differs across patch levels of one minor
  and the two-interpreter rule does not guard it;
- none of `parseaddr`, `getaddresses`, `AddressHeader` returns offsets; D2 needs a span per address;
- on the exact inputs the draft's fixtures use the stdlib entry points disagree with each other
  (group flattened by `getaddresses`, first address by `parseaddr`; `undisclosed-recipients:;` gives
  `[('', '')]`; garbage and trailing commas; spike a06);
- `parsedate_tz` rewrites `-0000` to `0` (spike a05), so the public surface cannot honour "`-0000` is
  not `+0000`"; `parsedate_to_datetime('-0000')` is naive, as is a missing zone; and from 3.10 it
  **raises** `ValueError` on an invalid date (from memory: verify empirically);
- RFC 2047 encoded words are legal in a *phrase* but not in an addr-spec, so the own tokenizer calls
  the encoded-word rule for display names only and keeps local part and domain verbatim.

H's useful narrowing, accepted by C: an **owned-rule stop rule** (own a rule only where a phase-1
fixture exercises a measured difference). Under it, address cases needing an owned **tokenizer**
(group, empty group, unparseable, quoted comma) and cases needing only a **policy** (IDN verbatim,
SMTPUTF8 flag) differ, and **all five date cases need an owned rule**.

Replacement text for spec decision 4:

> **4. Header projection engine: the package owns it.** Addresses: an own RFC 5322 3.4 address-list
> tokenizer (addr-spec per 3.2.3, quoted-string, CFWS per 3.2.4, group per 3.4, obs-route per 4) that
> emits **one span per address**, preserves group members, yields a group with zero members for
> `undisclosed-recipients:;`, records IDN and SMTPUTF8 verbatim (never IDNA-normalised), and makes an
> unparseable address tri-state `unknown(reason_id)` with the raw value beside it. Dates: an own RFC
> 5322 3.3 date-time parser (optional day name, obs-zone table, range checks, offset limit
> +/-9959) in one file, one entry point, no timezone database, **never raising on input content**;
> the zone has three recorded states, `zone_stated`, `zone_stated_minus_zero` (`-0000`, never read as
> UTC) and `zone_absent`, and a missing or invalid date sorts at one named end with a reason, never as
> an epoch. `email.utils` and `email.headerregistry` appear **only in tests**, as an advisory comparator
> (its disagreement is recorded and printed, never a gate, because on garbage and empty groups the
> stdlib is less correct than the contract); a test asserts that the own parser returns a reason id
> exactly where `parsedate_to_datetime` raises. Version differences between interpreters or patch
> levels are recorded-only run inputs.

### P5. Encoded words and RFC 2231: AGREED WITH AMENDMENT

Both agree with the draft's direction. Amendments (stdlib decodes invalid words silently with
`defects = []`, spike a07, so the package must **validate**):

- `headers.encoded_word_invalid` triggers on a validated failure: charset not resolvable; B-encoding
  not well-formed base64 or wrong padding; Q-encoding with a stray `=`, bad hex or a raw `?`;
- unfold first (RFC 5322 2.2.3 removes CRLF and keeps the WSP; the stdlib collapse to two spaces is
  **not** a misreading, spike a01), then RFC 2047 5(1): an encoded word may not be adjacent to
  non-whitespace text and whitespace between encoded words is dropped; join across a split character
  only for the **same charset**, otherwise `headers.encoded_word_invalid` (RFC 2047 2 forbids a
  character split across words, but it is real);
- RFC 2231 4: continuations reassemble by index 0,1,2...; a missing or duplicate index is an error;
  `name*` shadows `name` (5) with the conflict recorded; a charset carried on segment 0 only is legal;
- the **wild forms producers emit** are decode-with-recorded-fallback plus the existing gap, not
  "unparsable": an RFC 2047 word inside a quoted MIME parameter (`filename="=?utf-8?B?...?="`) and
  `filename*=''...` with an empty charset;
- the package owns the decoder because it keeps raw spans and must not re-serialise, not because the
  stdlib join is broken.

### P6, P7, P9, P11. The "not built" idiom: ONE merged decision (AGREED WITH AMENDMENT)

The four proposals are one contract decision. Final position, after three corrections of both sides
(section 8): per-record axis fields, `TriValue` for the type verdicts, and caps **not** merged.

Replacement text, one decision replacing 6, 7, 9 and 11:

> **6. One "not built" idiom, one schema bump.** There is exactly one: `TriValue(state=UNKNOWN,
> reason_id=NOT_BUILT_IN_PHASE1)`, where `NOT_BUILT_IN_PHASE1 = "not_built_in_phase1"` is a new constant
> in `ids.py` beside `NOT_BUILT_IN_PHASE0` (`ids.py:26`), registered in the design's reason-id text.
> `None` keeps its single meaning (the record family has no such axis, or the input did not exercise the
> field) and an empty list keeps its single meaning (genuinely empty). **Neither is ever the encoding of
> "not built".** A union `X | NotBuilt` is forbidden: the core codec decodes a union by its first
> non-`None` member, so it would not round-trip.
>
> *Per-record axis fields.* `AttachmentOccurrence` gains `status_axis: TriValue` and `route_axis:
> TriValue`; `EmailDocument` gains `times_axis`, `thread_edges_axis`, `children_axis` and
> `same_message_candidates_axis` (all `TriValue`). The closed axis-id tuple is
> `attachment.status`, `attachment.route`, `document.times`, `document.thread_edges`,
> `document.children`, `document.same_message_candidates`; a wildcard id is banned. The value fields
> keep their types (`status: StatusOutcome | None`, `route`, `times: list[TimeEvent]`).
> A document-level `deferred` list was **rejected**: for a nested record read out of a store it says
> nothing.
>
> *Invariants, enforced in the parent record's `__post_init__`, never in either field's type.*
> (I1) a record has an axis field iff it has the value field. (I2) Phase 1: `status is None` iff
> `status_axis` is the not-built `TriValue`; symmetric for `route` and the document axes, so "forgot the
> marker" and "empty but built" are both unrepresentable. (I3) built: `status` is a `StatusOutcome` iff
> `status_axis == TriValue(VALUE, "built")`; absent keeps meaning "no such axis". (I4) any other pair
> raises `CodecError`. The "unknown reason is not the current phase marker" clause is **replaced** by
> membership in a closed set `{not_built_in_phaseN, "built"}` plus `UNKNOWN(reason_id)` for
> consulted-and-unknown: a contract invariant must not depend on the current phase (Claude's
> amendment, hearth had written it phase-relative). A test constructs
> `AttachmentOccurrence(status=StatusOutcome(Status.PARSED), status_axis=<not built>)` and asserts it
> **raises**; a scope test asserts that a build marked Phase 2 emits no record whose reason id is
> `NOT_BUILT_IN_PHASE1`.
>
> *Type verdicts.* `declared_mime`, `magic` and `container_introspection` all become `TriValue`
> (design D4 says "each `value | unknown`" and D2 mandates uniform tri-state). `magic` consulted and
> nothing matched is **`VALUE("unrecognized")`** (a closed sentinel *value*, not `UNKNOWN`);
> not computed (zero-length part, cap hit, decode failed) is `UNKNOWN(reason_id)`;
> `container_introspection` is `UNKNOWN(not_built_in_phase1)` until Phase 2. `attach.type_disagreement`
> iff at least two verdicts are in state `VALUE` with a media-type family and the set of families has
> size >= 2; `"unrecognized"` and `UNKNOWN` contribute no family and never fire it;
> `attach.type_unknown` iff no verdict yields a family; the winner order is
> `magic` over `declared_mime` over `container_introspection` where known, and a winner must name a
> known verdict (the existing construction invariant at `model.py:390-391`).
>
> *Not merged: caps (old proposal 9).* A cap hit is a **built observation**, not a not-built one, and
> the contract already carries it: `Status.SKIPPED(size_cap | total_size_cap | depth_cap)`,
> `Status.TRUNCATED(cap_hit_mid_stream)` (`model.py` `REASON_TABLE`, (hearth)), `RunRecord.cap_id` and
> `cap_value_bytes` (`model.py:638-639`). The draft's sentence "caps-as-statuses are Phase 2"
> (spec:21) and "a recorded `truncated(cap_id)` state" (spec:158-161) contradict each other; the
> corrected rule is that Phase 1 **uses** the existing reasons now. Two real defects remain and are
> registered as contract work in the contract turn: `RunRecord` models **one** cap (a run that hits
> depth and total-bytes records one), and the reason table has **no id for a part-count cap or a
> header-bytes cap**.
>
> *Not merged: `FlagSection`* (a reserved present-but-empty contract, versioned by
> `FLAG_SCHEMA_VERSION`; its emptiness is a contract default, not a not-built claim) and `selection`
> (built in Phase 1; `NOT_APPLICABLE` is a real value).
>
> *Version.* `OUTPUT_SCHEMA_VERSION` **3 to 4** (types and fields change). The core codec envelope
> `SCHEMA_VERSION` is untouched. The contracts ledger line moves (`behavior_ledger.py` records field
> types); the walk ledger line does **not** move in the contract turn and moves only in the commit that
> shrinks `walk.UNBUILT_SECTIONS` as producers land. Phase 0 sidecars are unaffected (`l1.py` imports
> only the walker, not `model`; `attach.manifest`, `body.selection`, `headers.decoded` stay declared with
> no measurer until their producers land) ((hearth), not re-read by Claude).

Honesty versus stability: the draft's alternative (read `status = None` as not built, no shape change)
is the only option that does not move the version, and it is the dishonest overload (`None` already means
"this node has no status axis", `model.py:464-465`). Honesty wins; the bump is the price.

### P7. Type verdicts (remaining points): AGREED WITH AMENDMENT

Beyond the idiom above: `declared_mime=text/plain` with a `PK\x03\x04` prefix is a disagreement and the
winner is `magic` (bytes beat claims); "zip" is an honest family (a docx is zip by design, D4), and a zip is
never guessed to be docx or xlsx. The closed magic table grows from the draft's six: **zip, OLE-CFB, pdf,
png, jpeg, gif, RTF (`{\rtf`), gzip (`1F 8B 08`), 7z (`37 7A BC AF 27 1C`), rar (`Rar!\x1a\x07`)**. Excluded
deliberately: WebP and WAV/AVI (`RIFF` needs bytes 8-11, not a prefix magic), TIFF (rare), `.ics` and
`.eml` (text, no magic), and any text sniffing. `.msg` is OLE-CFB and needs no row.

### P8. Offsets and `verbatim_precision`: AGREED WITH AMENDMENT

C's four counter-examples, resolved by H and checked against `walk.py`:

- single-byte plus identity CTE is a 1:1 map **only for a strict decode**: any path that fires
  `fallback_fired` or `decode_destroyed_bytes` (the replacement decode) forces `part_level`;
- a UTF-8 BOM is **not** a break for plain `utf-8` (EF BB BF decodes to one U+FEFF and the map stays
  exact); it breaks only if the projection uses `utf-8-sig` or strips U+FEFF, so exactness is a property of
  the **actual decode function**, not of the charset name;
- us-ascii declared with 8-bit bytes: the ladder (`walk.py:23-26`, `602-618` (hearth)) already moves to
  windows-1252, so the map is keyed to the **used charset**, never the declared one (the draft says
  "the charset" without saying which);
- the coordinate space **must not normalise** CRLF/LF (spike c02: stdlib never round-trips CRLF; a reader
  will wrongly assume the projection does).

QP and base64 are not impossible, only untracked: `cte_not_identity` names a choice, and one generic
offset-map generator should serve identity, QP and base64.

The property test "an exact span slices to the right bytes" is **circular** if the map stores `(char,
byte)` pairs. Replacement text:

> **8. Offset maps and `verbatim_precision`.** The coordinate space is the part's decoded text in code
> points, **un-normalised** (no CRLF or LF folding). An offset map is built, and a span is `exact`, only
> for a **strict** decode of the **used** charset (never the declared one), over a stateless charset
> (single-byte or UTF-8), where the CTE is identity; every other case is `part_level` with
> `cte_not_identity | multibyte_without_offset_map | decode_fallback`, and **no within-part byte span is
> emitted**. The property test is independent of how the map is stored: (1) spans are strictly increasing
> and **partition** both `[0, len(raw))` and `[0, len(text))`; (2) for every span `raw[bo:be].decode(
> used_charset) == text[cs:ce]` (a fresh re-decode of the slice, which catches an off-by-N cumulative
> table); (3) for strict decodes `text.encode(used_charset) == raw`; (4) `b"".join(slices) == raw`; (5) an
> anti-vacuity mutant that breaks one entry's byte length must fail the gate. Assertions (2)-(4) are made
> only for stateless charsets (a slice of ISO-2022-JP is not independently decodable), which is also the
> honest boundary of what `exact` may claim. `exact` is a **fixture-checked** claim, but not a statement
> about real mail (section "Open questions").

### P10. Entry point: AGREED WITH AMENDMENT

The draft's rule 10 regresses D1 (`design:75-79`: CFB magic, **otherwise RFC 822, otherwise a named
error**): "any other bytes are RFC 822" drops the named error, so garbage would parse as a defectful
message. Also, "`limits` is mandatory for untrusted bytes" is unenforceable as written (the function
cannot know which bytes are untrusted).

> **10. The entry point.** `parse(data: bytes, container_kind=None, *, limits)`: `limits` has **no
> default** (a `Limits.untrusted()` constructor is provided for callers). With `container_kind=None` it
> sniffs: `D0CF11E0A1B11AE1` is `cfb_msg` (a named error in Phase 1: no reader, never a guess, never an
> exception from mid-parse); otherwise **RFC 822 if the bytes begin, after an optional UTF-8 BOM, with at
> least one `name: value` line before a blank line or EOF**; otherwise a **named error** (closed reason
> id). The BOM is tolerated by the sniff only; whether the walker then reads the first field is the
> separate BOM decision (section "Open questions").

### P12. Retained labels: AGREED WITH AMENDMENT

> **12.** The Phase 0 sidecars' `attach.manifest`, `body.selection` and `headers.decoded` stay as typed. A
> label that contradicts a settled decision **fails the suite as a finding** (both values and the bytes)
> and the sidecar is **never edited**; "unless it contradicts" is not permission to revise a label.

Phase 0 fixtures carry no attachments, so a collision is unlikely; the mechanism matters, not the
probability.

## 2. Topic 2: the turn split

**Status: AGREED WITH AMENDMENT; one residual DISAGREEMENT (1.0a bundling), below.**

Premise corrected: **Phase 0 had no docs-only turn** (C asserted one; H showed Turn 0.3 shipped about 11
fixture pairs with code, and the whole phase has no documents-only commit). What Phase 0 proves is a
**ceiling of about 11 fixture pairs with code in one turn**, and about 65 tests per contract-only turn.

Ordering defects in the draft (all adopted):

- 1.0a "NO CODE" ships a ledger test and a contract change, and **about 40 fixtures plus 40 sidecars**
  (three to four times the Phase 0 ceiling, all hand-typed; a missing sidecar cannot be caught until a
  reader exists). A half-finished doc turn looks incomplete; a half-finished label turn looks fine.
- 1.0b assembles an `EmailDocument` (the "assembly seam") before the not-built shape exists, which is the
  empty-versus-not-built trap rule 4 forbids.
- **Sidecars need `FACTS` declarations first** (contract plus oracle code), so fixtures cannot precede it.
- The HTML decision needs the HTML fixtures, but must also decide **where the element tree lives**; the
  draft's layout has `htmltext.py` and `quote/dom_rules.py` and nothing between.
- **The node-to-projected-text-span map is missing.** DOM rules in the quote turn must locate
  `div.gmail_quote` in the same code-point space as the prefix-depth spans, or "structural wins" has
  nothing to win against; the HTML projection must **record a span per element**.
- `attach.cid_dangling` and `cid_unreferenced` need the **referenced-cid set** from the HTML parse, which
  the draft's text turn omits (only `inline_data_uri` and `remote_content_present`).
- `quote` rules operate on projected text offsets, so the offset map is a dependency of the text rules,
  and **the quote splitter must use the same line model as the offset map** (see lone CR, section 7).
- 1.1 (four modules, a scanner, every `headers.*` gap) and 1.2 (alias rules, CTE decode, offset maps,
  property test, selection, HTML projection) are too large; 1.3 stays whole.
- `runboth.py` ships in 1.0b but rule 2 requires both interpreters "always" from the first turn.

**The agreed order** (Claude's merge of hearth's final table with the 1.0a/1.0b correction below):

| turn | content | new gap ids first emitted | test-fn ceiling | owner commits |
|---|---|---|---|---|
| **1.0a** | documents only: design revision 3, spec revision 2, the fixture catalogue with every name and the consuming turn, exact `FACTS` ids and value shapes, registry entries (all new ids registered, none emitted), the ledger format and the allow-list | registers five | 0; row ceiling | yes, before 1.0b |
| **1.0b** | **contract plus oracle declarations**: the not-built idiom, `QuoteBoundary`/view-level records, three `TriValue` verdicts, `NOT_BUILT_IN_PHASE1`, `OUTPUT_SCHEMA_VERSION` 3 to 4, ledger keys, `FACTS` declarations (phase, no measurer), the additions-only ledger test, `runboth.py` | none | 25 | yes |
| **1.0c** | fixtures and hand-typed sidecars, **by fact family, non-quote first** (headers/date/address, body/HTML, attachments/caps); about 30 pairs at most per commit | none | 5 | yes, per family |
| **1.0d** | entry point, limits, named errors, the HTML decision experiment (a spike plus a doc; ships `htmltext_version` only, not `htmltext.py`) | none | 15 | yes |
| **1.1** | `headers.py`, `rfc2047.py`; header reference scanner in `tests/support/` (see topic 3) | `headers.duplicate_header`, `body.lone_cr_line_terminator` | 40 | yes |
| **1.2** | `addresses.py` | none (existing ids) | 30 | yes |
| **1.3** | `dates.py` | none | 25 | yes |
| **1.4** | `text.py`: per-part text, alias table, offset maps, shared line model | `body.flowed_reflow_unresolved` | 40 | yes |
| **1.5** | selection, `htmltree.py`, `htmltext.py` with the **node-to-span map and the referenced-cid set** | `body.digest_default_not_applied` | 40 | yes |
| *quote catalogue* | the quote fixtures and sidecars, typed and **owner-reviewed before any quote rule is written**, ledger-pinned, `A` only | none | 3 | yes |
| **1.6** | quote boundaries, text family (`text_rules.py`, `i18n.py`, `resolve.py` text half) | none | 25 | yes |
| **1.7** | quote boundaries, DOM family and resolution | none | 25 | yes |
| **1.8** | `attach.py` | `attach.duplicate_content_id` | 40 | yes |
| **1.9** | `assemble.py`, `ingest.py`, `store.py` (absorbs the `assemble.py` half the draft left dangling) | none | 30 | yes |
| **1.10** | gates over real output, hostile set, scope test, close | none | 30 | yes |

Test ceilings: hearth argued that Phase 0's about 65 per turn was a contract-only artefact; <= 40 for any
turn that also writes a parser, <= 25 for the two judgment-heavy quote turns (the owner-reviewed catalogue
**is** the check there), and the binding limit is the 250k compaction trigger. Every turn carries a
**pre-declared stop point** the agent reports at rather than pushes past:
1.5 (after `htmltree.py` and the node-to-span map, before selection and the cid set) and 1.1 (headers, folds
and raw spans first; `rfc2047.py` becomes its own turn if large).

**DISAGREEMENT (minor): 1.0a bundling.** Hearth's own final table kept docs, contract, ledger **and** the
non-quote fixtures in one 1.0a, with a pre-declared split point (stop when the contract is frozen). Claude
holds that the split must be **decided now**, not deferred to an agent's judgment under context pressure:
(i) the contract and `FACTS` declarations are code and belong in their own turn; (ii) the fixtures depend on
them; (iii) a bundle that "may be split" is the failure the operating rules exist to prevent. Hearth's
split point shows it concedes the risk. Evidence that would settle it: how many tokens Turn 0.3 (about 11
pairs plus code) actually consumed; if a 30-pair fixture turn is below the compaction trigger by a wide
margin the bundle is survivable, otherwise split. **Recommendation: split as in the table.**

## 3. Topic 3: the independent check

**Status: AGREED WITH AMENDMENT.**

The draft's scanner is not independent: decision 4 delegates addresses and dates to stdlib and the scanner
(`tests/support/`, spec:191) is on the stdlib parser, so the comparison is **tautological for exactly the
fields decision 4 delegated**. Under the settled decision 4 the problem reduces to scope. Agreed design:

- **What the stdlib scanner compares (three comparisons, and no more):** field **names and order** from
  `raw_items`/compat32 raw view only (never `policy.default`'s `headerregistry`); the **content-type tree**;
  the **decoded text of benign leaves**. Addresses and dates are an **advisory** diff, printed, never a
  gate. Part spans are **never** compared against stdlib (it has no offsets, spike c01, c04).
- **What it must not share:** no import of `emailextract` at all (not `ids.py`, `versions.py`, the label
  loader, `walk.py`, `tools/make_fixtures.py`); hash with `hashlib` directly; its own header/body split and
  field split; **no shared boundary regex** (RFC 2046 5.1.1 is a foundation fact, where reader and checker
  sharing a regex fail together); its own charset resolution through `codecs.lookup` (divergence between
  declared and used is **expected** on the alias fixtures); for HTML it compares element counts and ids,
  never projected text.
- **Where stdlib is authoritative** (disagreement is the package's bug): field order and duplicates, the RFC
  2045 5.2 default `text/plain; charset=us-ascii`, RFC 2046 5.1.5 digest children defaulting to
  `message/rfc822`, `message/rfc822` nesting, valid RFC 2047 decode, benign base64 and QP, RFC 2231
  continuations.
- **Where stdlib shares the misreading** (agreement proves nothing; excluded from any gate): unknown CTE
  silently returns the bytes (d03); truncated base64 and malformed QP decode leniently with no signal (b02,
  d01); an unknown charset raises or falls back (b03); an invalid encoded word decodes silently (a07);
  `defects` and returned bytes disagree (b02), so `defects` is not a defect oracle; `parseaddr` and
  `getaddresses` disagree on garbage; **lone CR is a line break** (see section 7). One correction of C's
  list: obs-fold collapse (a01) is **not** a stdlib misreading.
- **A third check, adopted:** an independent byte-level delimiter splitter in `tests/support/` (~60 lines),
  never a library, run as a **seeded differential fuzz** against the parser. It earns its keep on
  **unlabelled** inputs, where Phase 0's hand-typed spans cannot reach; against labelled fixtures it adds
  little. Compared quantities: the **ordered list of part byte spans**, the **part count**, the
  **preamble and epilogue length** per multipart, and the **boundary-delimiter line spans**. Mutations
  (seeded from the fixtures): flip a `--`; insert or delete a CRLF before a delimiter; truncate mid-boundary;
  duplicate a delimiter; rotate line endings on delimiter lines; change transport padding; append after the
  close delimiter; remove the close delimiter; inject delimiter-like text **inside** a part body; and
  base64/whitespace mutations inside encoded bodies, which **must not** change any of the four quantities.
  Excluded as RFC-ambiguous (recorded, not gated): a boundary that is a prefix of another in the same
  message (RFC 2046 5.1.1 forbids it); a delimiter line followed by anything but LWSP; a **missing close
  delimiter** (gate on `body.boundary_disagreement` instead of the span); a message with no `Content-Type`
  that merely resembles a boundary; content that contains the boundary on purpose.
- **Rejected as third checks:** compat32 versus default policy (same `feedparser`, near-zero independence;
  keep as a unit test) and the re-encode round trip (circular: it reuses the package's CTE and charset path,
  impossible where bytes are destroyed).
- **Honest limit:** a splitter written by the same model family as the walker shares the reading of RFC 2046
  with it. Its independence is **code lineage, not a different author**. The strongest common-mode breaker
  remains the owner's structure-only probe over real mail.

## 4. Topic 4: quote detection

**Status: AGREED WITH AMENDMENT.** C's position (labels typed by the same model family as the rules are only
partially independent, so the owner's review of a catalogue is load-bearing) is accepted by H and stated in the
spec.

**v1 text and DOM rules the draft missed** (each needs a fixture; the test column is what makes it v1):

| rule | one-line test |
|---|---|
| Gmail: `class="gmail_quote"` may be on a `blockquote`, not only a `div`; the attribution wrapper must not add a second ordinal | is the class on a `blockquote`? is the attribution its own element? |
| Outlook.com `#appendonsend` and `#x_appendonsend`, with the **`x_` prefix** on ids and classes after Outlook rewrites HTML (`x_divRplyFwdMsg`) | does exactly one anchor mark the insertion point? |
| Thunderbird `div.moz-cite-prefix`, `blockquote[type=cite]` with `cite="mid:"`, `div.moz-forward-container` | vendor class verbatim? |
| Apple attribution shape (`On 3 Jun 2024, at 10:12, X <a@b> wrote:`) and `Begin forwarded message:` plus a From/Date/Subject block | are the accepted line shapes named in a table? |
| `-----Original Message-----` family (name the accepted shapes; "dashed lines" in the draft is a guess) | is the regex in the table? |
| Yahoo `div.yahoo_quoted` and `----- Original Message -----` / `From:/To:/Sent:` | vendor class or named line shape? |
| `-- ` signature: exactly dash dash space plus the line end (RFC 3676 4.3), **candidate only** | exact delimiter? |
| RFC 3676 **space-unstuffing** before counting `>` when `format=flowed` | does the part declare `format=flowed`? |
| the `>`-family alphabet spelled out (`> >`, `>>`, bare `>`), counted on decoded text | alphabet in the table? |
| **bottom-posting is legal, not a gap**: a quoted-first message with a later level-0 span is not "no new text"; only a non-contiguous alternation is `body.inline_reply_interleaved` | is the first non-empty span >= 1 and a level-0 span present later? |
| **list footers** (the design put them in v1, "detection only"; draft turn 1.3 dropped them): a line of at least 30 `_` begins a `list_footer` candidate; a second rule for the "You received this message because you are subscribed" sentence | a line of >= 30 `_` at line start? |

**Named gaps added:** `body.flowed_reflow_unresolved` (the soft-break **join**; only unstuffing is v1) and the
**trigger** for the existing `body.html_quote_rule_gap` (a class or id matching a known prefix family such as
`gmail_`, `moz-`, `yahoo_`, `...RplyFwdMsg` with no table row is that gap, never `body.no_boundary_found`).

**Explicit declines (no id, and the spec says so):** disclaimers and confidentiality footers (no structural
marker; a trailing block is legally level 0, and recording it as a signature would over-claim); client
taglines ("Sent from my iPhone": unbounded, i18n, attacker text; v1 holds no string list, only the `-- `
rule); quoting inside a `message/rfc822` attachment (recorded, not recursed).

**Trust ranking** (H's own): the least-trusted row is **Apple attribution** (it is H's own construction from
the producer, locale-variable, not named in the design), then Yahoo `yahoo_quoted`. **Every vendor class and
id name is "verify against a structure-only probe by the owner"**: neither side can verify any of them from
the repo, and Claude did not accept any class name on the strength of recall alone. Locale reply markers stay
the named gap, not a rule list (design:174-176).

**The review artefact.** The owner reviews a catalogue of about 15-20 rows, one screen per fixture: fixture,
the raw line or element the fact hinges on, the expected `(rule_id, kind, ordinal)` and level, one line of why.
Three questions per row, minutes not hours: does the marked line actually look like the boundary in the bytes;
is the **kind** right (a forward read as a quote is the failure that mislabels the sender's own words); is any
**new** text at level >= 1. The catalogue is typed as its own small increment before the first quote rule is
written, and the agent that writes the rules does not see the labels it typed.

## 5. Topic 5: exit criteria and operating rules

**Status: AGREED WITH AMENDMENT.** Problems in the draft, each with its replacement mechanism. (a) to (h) are
Claude's list; H agreed to all with two objections noted.

| # | problem in draft | amendment |
|---|---|---|
| a | "no `not_yet` at phase 1 beyond a named deferred set (none expected)" is gameable by redeclaring a fact's phase | **pin the declared phase-1 fact-id list in the ledger**; a change to `FACTS` phases fails the suite unless the ledger changes in the same commit. The deferred set is a **closed list in the ledger**, empty by default |
| b | "L1 at 100% over every phase-1 fact on every fixture" is vacuous if a new fact is labelled on one fixture | a **per-(fact x phase) coverage floor** (H's objection: per fact alone, a phase-0 fact with a measurer masks a phase-1 fact without one): at least N sidecars, at least one with a non-trivial, non-empty value; the sparse-fact convention (`body.preamble_epilogue`) is **not used** for new facts |
| c | "agree on every benign fixture": benign is undefined | `benign` is an **additions-only sidecar flag**; the exclusions list carries closed reason ids |
| d | spec:285 puts interpreter, platform and library versions outside the identity projection; exit criterion 5 says documents are byte-identical across both interpreters | name the **identity projection** in the criterion and list the recorded-only fields; the full record differs only in those |
| e | the fuzz "never raises" is a crash property; it does not bound time (nested quantifiers in the quote rules, `html.parser` quadratic behaviour on unterminated tags, attributes or comments) | a **work-per-input-byte budget** in the hostile set asserted non-superlinear (operation counts or a length-scaled ratio, **never absolute seconds**); H's objection accepted: operation budgets still depend on scheduling, so state a **single-threaded assumption**; a source scan of `quote/*.py` for nested unbounded quantifiers is kept as a weak proxy only |
| f | "every ambiguity resolved" is unverifiable | replace with a **list of named resolutions, each with a test id** |
| g | the additions-only ledger covers `*.expected.json` only; fixture bytes are already pinned twice (`tests/test_fixtures.py` regeneration plus `fixtures/raw/SHA256SUMS`, (hearth)) | **extend the ledger to `tests/support/**` and `emailextract/evals/**`**, additions-only; changes to gates require an explicit **turn-prompt allow-list** |
| h | "`pytest --collect-only` is diffed against the declaration" (spec:47-50) names no mechanism | a **test**, not a promise: a collection assertion against the per-turn declaration, or drop the rule |

Further defects found by H's line-by-line re-read (all adopted; none disputed):

- `body.plain_effectively_empty` is listed at spec:36 as "first emitted in this phase" (a gap), while spec:111
  and design D16 call it a **fact**, not a gap, and `phase0-gaps.md` carries a section for it: resolve in
  1.0a, and declare it in `FACTS` as a fact;
- unqualified gap ids at spec:40-42 (`boundary_disagreement`, `decode_fallback_used`, ...) while the rest are
  `body.*`/`headers.*`-qualified; reason ids are compared by exact string;
- the draft's D12 bullet compresses design `verbatim_precision` to two values; the design has **three
  rungs** (the MIME part's raw span always exact; the decoded char span; the within-part byte span): restore
  all three or a `part_level` citation looks like it has no exact span at all;
- `thread.duplicate_message_id_bytes_differ` (spec:288) is a `thread.*` id in a phase that declares
  threading out of scope; the finding is real but the namespace is wrong for Phase 1 (decision for 1.0a:
  keep the design's id and say why, or move it);
- "settled in 1.0a" for decision 6 but "approval needed before 1.1" (spec:337): decision 6 is needed before
  **1.0a**;
- rule 2 hard-codes `py -V:Astral/CPython3.11.15`, which is machine-specific; give a documented fallback;
- `limits` mandatory (see P10); `runboth.py` too late;
- spec:309 updates the design again in the last turn after 1.0a revised it: two revisions or a stale clause.

**What the workbook debate found that the draft has not (fully) adopted:** the **phase-1 gap gate** is in the
draft's 1.7 but not tied to a pinned fact list (a); **recorded failures with closed reason ids rather than
library text** appears only in 1.6's tests: it must be a construction invariant of the failure record;
**run-record fields out of the identity projection** is in 1.6 but contradicted by exit criterion 5 (d);
the **anti-vacuity triple** is adopted but proves only that the patched symbol **exists**; see below.

**The top five failure modes of a long autonomous build still unguarded** (H, ranked by "silently corrupts an
oracle and the suite stays green"; the mechanical guard in each case):

1. **The agent edits `tests/support/**` or a gate to make a failure disappear.** Guard: the extended ledger
   (g), additions-only; hashing the gate's inputs catches mutating the expectation, not only the assertion;
   the allow-list in the turn prompt.
2. **A parser rule written from the fixture bytes the agent just read (label leak).** Guard: per-turn prompt
   allow-list that **excludes `fixtures/**` and `*.expected.json`** after the fixtures turn; a test asserting
   no `emailextract/**` file contains a fixture path or filename literal; a flip-one-input test per rule
   (re-render with one marker changed and assert the level moves).
3. **Silently narrowing a fixture so it parses.** Guard: fixture hashes in the same additions-only ledger; the
   byte-level no-silent-drop gate; a census test that the fixture set is a **superset of the design's Phase-1
   list**.
4. **Vacuous anti-vacuity**: a mutation test whose monkeypatch is off the executed path. Guard: tighten the
   triple from "the patched symbol **exists**" to "**was reached**": patch with a wrapper that sets a flag and
   assert the flag on the fixture's path (a mutant whose patch is never entered fails as vacuous).
5. **A document claims a measurement that was never run.** Guard: every measured number in a doc carries the
   command that produced it and a hash of the output, and a test re-runs the command and compares; anything
   not re-runnable is marked "verify empirically" and is **not** a gate input.

Also adopted: the **construction-invariant wording** must state that the pairing invariant lives in the
record's `__post_init__`, not in either field's type (a build agent reading "a shape invariant is checked at
construction" per field will check each field in isolation and skip the pair), and the Phase 1 turn prompt for
1.0b must say so.

## 6. Topic 6: what the draft missed entirely

Hearth was asked for RFC clause, producer, walker behaviour, proposed state and fixture per item.
Its first two tables were weak (generic rows, many items skipped); the third round answered the items. The
outcome, reduced by hearth's own concession ("I over-minted: ten new gap ids is not defensible") to **five
new gap ids**, each of which costs a registry line, a `phase0-gaps.md` entry, a fixture and a mutation case:

| new gap id | the reader must not infer |
|---|---|
| `headers.duplicate_header` (generalises `headers.duplicate_message_id`; first-win in `walk._header_value` is silent) | that the first (or last) repeat of a header is the authoritative value |
| `body.digest_default_not_applied` | that a Content-Type-less part in `multipart/digest` is `text/plain` (RFC 2046 5.1.5: `message/rfc822`) |
| `attach.duplicate_content_id` | that a Content-ID names exactly one part |
| `body.flowed_reflow_unresolved` | that `format=flowed` text was unstuffed and reflowed |
| `body.lone_cr_line_terminator` | that a bare CR is an RFC-legal line break (see section 7) |

Everything else is a **FACT** (a recorded property: header line over 998 bytes, boundary over 70 characters or
non-latin-1, NUL in a value, Content-Disposition `size`/`date` parameters recorded verbatim and never trusted
against `size_bytes`) or a **DECLINE** (named, no id: DSN semantics, TNEF, mbox splitting, a stateful-charset
offset map beyond `verbatim_reason`, `application/ics` semantics). **Deleted as wrong:** `rfc2231_unhandled`
(contradicts decision 5, which decodes RFC 2231; the remainder is `attach.filename_unparsable`) and `nested_claim`
(not a registered concept).

Fixtures (tiny, single-purpose; every one synthetic) recommended for the fixtures turn from this list, each
with the item's disposition: nested `multipart/alternative` in `related` in `mixed` and the `selection` rule when
`text/html` is inside `related` (design fixture `multipart_mixed_wraps_alternative`); `Content-Location` in
related (recorded, never fetched); missing and duplicate `MIME-Version` (duplicate is the `duplicate_header`
mutation); 8-bit raw bytes in header values (the walker's latin-1 value decode is **lossless, not mojibake**:
`walk.py:307-312`, `raw_value` is the latin-1 view of the raw bytes; the headers part's text must still
render the verbatim bytes); base64 with embedded whitespace and a wrong padding (existing `truncated_base64`);
QP raw 8-bit; `iso-2022-jp` (stateful: `verbatim_reason=multibyte_without_offset_map`, no new id); `gb2312`
declared with `gbk` bytes (Python's `gb2312` codec is strict: the ladder lands on a lower rung; `bad_charset`);
`windows-1252` declared `iso-8859-1` (C1 bytes, no special case, design:573 (hearth)); RFC 2231 charset on
segment 0 only; a multibyte character split across two adjacent encoded words; Content-Disposition
`size`/`date`; the **same Content-ID twice**; `text/calendar` alternative beside plain and html (a view with
`selection`, **not** an attachment; spike e02 shows it does not leak into `iter_attachments`); mixed-case
header and parameter names (the walker lower-cases, correct); a boundary with tspecials or quotes (the
walker's `_split_params` is quote-aware, (hearth)); a multipart with a `Content-Transfer-Encoding` (recorded as
a claim, never decoded); `multipart/signed` (the signature part is **never repaired**; claims are not
verified); NUL and BOM (below, as experiments).

**Never covered at all by hearth, listed here so the next round does not lose them:** MIME `boundary` that
equals a prefix of another (covered by the exclusion list in topic 3); a header line over 998 bytes (FACT);
mbox `>From ` mangling in bodies (a FACT of the text, not a rule); quoted-printable soft line breaks (the
`exact` map's boundary); and **a UTF-8 BOM** and **an mbox "From " line at byte 0**, whose walker behaviour
hearth reads from source as follows (**verify empirically**, pinned experiments in section 9): neither is
stripped, each becomes a `parse_status: unknown` paragraph with `headers.malformed_line`, the header region does
not end. The consequence neither side likes: a BOM-prefixed message loses its **first real field** (visible
as a malformed paragraph, so not a silent drop, but `From` or `Received` is not read as a field). That is an
owner question.

## 7. Lone CR: a candidate common-mode error (new finding)

`walk._iter_lines` (`walk.py:197-220`, read by Claude) yields CRLF, LF **and** CR as line terminators. RFC
5322 2.2 and 2.3 allow CR and LF only as CRLF. The stdlib `feedparser` splits on lone CR as well (its `NLCRE` is
`\r\n|\r|\n`; **verify empirically**). Therefore the walker, the stdlib scanner and a model's label can share
the same misreading, and a differential test can never see a lone-CR framing bug. Rulings (H and C agree):

- **Decline to change the Phase 0 line model** (it would invalidate frozen spans, the ledger and the sidecars
  for a case with no design mandate) and record `body.lone_cr_line_terminator` as a gap, emitted in the header
  region;
- **the Phase 1 consequence is the important half:** the `>`-depth splitter, the text offset map and the
  quote rules must consume **the same line model** (`_iter_lines`), or a boundary's quote depth and its cited
  byte span will disagree about which bytes are a line. One function, one test asserting the splitter's line
  starts equal `_iter_lines`' over a body that contains CR;
- what a header value with a lone CR should do (stay in the field, a gap, or split) and what a CR-only body
  (old Mac mailers, mangled gateways) should do are **open**: the walker splits today, the gap makes it
  visible, and the experiments in section 9 settle the facts. Whether to fix the walker is the owner's call
  because it is a versioned Phase 0 behaviour change.

## 8. Where each side was wrong (the record)

**Hearth was wrong or weak on:**

- round 3 recommending `headerregistry.AddressHeader` for addresses and calling decision 4 "not a decision"
  (withdrawn in round 4);
- its first D6 proposal, a document-level `deferred` list, which is unsound for a nested record
  (superseded by per-record axes); and `magic` staying `str | None` against D4 and D2's tri-state
  (conceded);
- minting about ten new gap ids in its first T6 table, including `rfc2231_unhandled` (contradicts decision 5)
  and `nested_claim` (conceded, deleted);
- the first two T6 tables were generic and skipped most of the requested items; the walker claims (BOM, NUL)
  were stated as facts and had to be re-asked as source citations plus pinned experiments;
- its turn table kept the contract, ledger and all non-quote fixtures in one 1.0a, contradicting its own
  finding that sidecars need the contract first;
- it also made an invariant phase-relative (I4: "an UNKNOWN axis reason that is not the current phase
  marker") that a contract must not depend on.

**Claude was wrong on:**

- P2: the draft already exempted the all-zero depth case, and D3 already names the winner within a view
  (the real defects were the units, the two-quantity `quote_level`, and the missing contract slot);
- P1: "html.parser changed behaviour in recent security releases" asserted without a citation (now
  "unmeasured");
- P6: proposing `Status | NotBuilt` / `StatusOutcome | NotBuilt` (does not round-trip through the codec);
- the claim that Phase 0 had a docs-only turn;
- calling obs-fold collapse a stdlib misreading (RFC 5322 2.2.3 keeps the WSP);
- listing compat32-versus-default and a re-encode round trip as candidates for a third check;
- assuming 13 turns was the draft's count (the draft has nine; thirteen was Claude's table).

**Hearth changed the plan on:** the cross-cutting not-built finding (four proposals collapse into one decision);
the `FACTS` ordering dependency (hearth's reading of `l1.py`; Claude drew the order); the stdlib scanner's
non-independence; `kind = quote` only for the ordinal; the independent splitter as third check and what it must
compare; the lone-CR common-mode error; the coverage floor per fact x phase; construction invariants
(I1-I4) living in the parent record; the closed axis-id tuple; the walker/producer table.

## 9. Verify empirically (no code was run by either side)

Each experiment is a few lines of bytes in a scratch directory, never a fixture, never the repo; record the
output and the interpreter.

1. **HTML parser fingerprint (1.0d).** For each HTML fixture, on 3.11 and 3.14 and for lxml under a recorded
   libxml2: the `HTMLParser`-subclass event sequence `(event, text, get_starttag_text())`, the own tree, the
   fired DOM-rule spans, the projection hash; focus areas `convert_charrefs`, `<script>`/`<style>` CDATA,
   comment, PI and bogus-comment handling, an unterminated tag, attribute or comment, and an unclosed
   `blockquote` inside `div.gmail_quote`.
2. **BOM.** `b"\xef\xbb\xbfFrom: a@b\r\nSubject: s\r\n\r\nbody"`: expected (hearth's reading of `walk.py:296-304`)
   field 0 name `""`, `parse_status: unknown`, gap `headers.malformed_line`, `raw_value ==
   "\xef\xbb\xbfFrom: a@b"`; field 1 `Subject` `ok`.
3. **NUL in a value.** `b"X-A: a\x00b\r\n\r\nbody"`: one field `X-A`, `ok`, `raw_value == "a\x00b"`.
4. **NUL in a name.** `b"X\x00A: v\r\n\r\nbody"`: `unknown`, `headers.malformed_line`.
5. **Lone CR.** (i) `b"Subject: a\rb\nFrom: x\n\nbody"` through the walker: expected two fields from the lone-CR
   split; (ii) `b"From: x\r\n\r\na\rb\rc"` through `_iter_lines`: expected three body lines; (iii) the same
   input through `email.feedparser`: expected an identical split (proving the common mode, so no test may rely
   on a differential here).
6. **mbox "From " line at byte 0.** `b"From a@b Mon Jan  1 00:00:00 2024\r\nSubject: s\r\n\r\nbody"`: expected a
   malformed first field and `headers.malformed_line`.
7. **`parsedate_to_datetime` raise.** Inputs `"31 Feb 2024 10:00:00 +0000"`, `"x"`, `"Mon, 1 Jan 2024 10:00:00
   -0000"`, `"... +9999"` on 3.11.15 and 3.14.3: record return, exception type, and whether the zone is naive.
8. **`getaddresses` across patch levels.** `"undisclosed-recipients:;"`, `"a@b, , c@d"`, a group with members,
   `'"Last, First" <a@b>'` on 3.11.15, 3.14.3 and, if available, an unpatched older 3.11 patch release: record
   the delta (CVE-2023-27043 `strict`).
9. **`headerregistry.AddressHeader`** on the same inputs, as the missing spike row (a06 analogue), recording
   defects and the group shape.
10. **Offset map property** on the stateless-charset fixtures, with the five-part independent assertion of P8.
11. **Walker `_header_value` first-win on a duplicate `Content-Type`** (hearth reads it as silent).

## 10. Recommended spec changes, ordered by importance

1. **Replace proposals 6, 7, 9 and 11 with the single not-built idiom** (section 1, "One 'not built' idiom"):
   `NOT_BUILT_IN_PHASE1`, per-record `*_axis` `TriValue` fields, parent-record invariants I1-I4, three
   `TriValue` verdicts with `"unrecognized"`, caps not merged, `OUTPUT_SCHEMA_VERSION` 3 to 4. Without it the
   spec cannot be implemented.
2. **Re-split 1.0** into docs, then contract plus `FACTS` declarations plus ledger, then fixtures by fact
   family (quote catalogue last and owner-reviewed before any quote rule), then the entry point; move
   `runboth.py` to the contract turn. Retitle: no turn called "NO CODE" ships tests.
3. **Fix the quote ordinal** (`kind = quote` only; disagreement predicate with both families at depth/ordinal
   >= 1 and differing ranks; `quote_level` a derived rank; a new record for the per-boundary and per-view
   facts, in the contract turn).
4. **Move address and date parsing to owned code** (decision 4 replacement) and **shrink the stdlib scanner**
   to three comparisons plus an advisory; add the independent byte-level splitter as a seeded differential
   fuzz with an explicit exclusion list.
5. **Add the missing producer-side records**: the node-to-projected-text-span map and the referenced-cid
   set in the HTML projection turn; the same line model (`_iter_lines`) for the offset map, depth splitter and
   quote rules; the three `verbatim_precision` rungs; the RFC 2045 5.2 `text/plain` default as an explicit
   projection.
6. **Tighten the exit criteria** (section 5, a to h): pinned `FACTS` phases, per-(fact x phase) coverage floor,
   `benign` flag, identity projection named, a work-per-byte budget, ledger over `tests/support/**` and
   `emailextract/evals/**`, a collect-only test, and the "reached, not just exists" anti-vacuity.
7. **Replace the P8 property test** with the five-part independent version and the strict-decode, used-charset,
   stateless-only rule for `exact`.
8. **The v1 quote rules** of section 4 plus the five new gap ids of section 6; every vendor class name marked
   "verify by structure-only probe".
9. **Settle the draft's internal contradictions in 1.0a**: `body.plain_effectively_empty` fact versus gap,
   unqualified gap ids, `thread.*` namespace, caps-as-statuses, decision 6 timing, `limits` default, the
   machine-specific interpreter selector, the two design revisions.
10. **Entry point sniff** with BOM tolerance and a named error for non-messages (P10); `limits` with no
    default.

## 11. Open questions only the owner can answer

1. **The quote catalogue** (the only check not from the same model family): do the rows look like what Outlook,
   Gmail, Apple Mail, Thunderbird and Yahoo really write in your mail? In particular the Apple attribution shape
   and the Yahoo `yahoo_quoted` class, which neither side could verify. A structure-only probe on your own
   corpus (container classes and ids, not content) is the cheapest answer. Real mail never enters the repo.
2. **A forward banner reads as `new` (level 0)**: is that what you want in the views, given the design's intent
   that an inline forward is never "quoted"?
3. **Which localized label tables beyond English, German and French does your mail need?**
4. **BOM-prefixed and mbox-"From "-prefixed mail**: should Phase 1 tolerate a leading BOM or an envelope `From `
   line (strip with a recorded fact, so the real first header is read) or leave both as a malformed first field?
   The latter loses `From` or `Received` as a field on affected mail.
5. **Lone CR**: should the walker's line model change (a versioned Phase 0 behaviour change, invalidating spans
   and sidecars) or stay with the gap?
6. **Is `exact` verbatim precision** for single-byte and UTF-8 identity-CTE parts worth the cost versus
   `part_level` everywhere in v1? Real mail is mostly QP or base64, so `exact` will rarely fire; the owner
   might prefer building the QP/base64 offset map in this phase rather than leaving `cte_not_identity` as a
   permanent choice.
7. **`thread.duplicate_message_id_bytes_differ` in Phase 1**: keep the design id in a phase that declares
   threading out of scope, or rename it `headers.*`?
8. **Test ceilings per turn** (<= 40, <= 25 for quote turns) were reasoned from Phase 0, not measured against
   the actual 250k compaction trigger: if the owner has token counts from Phase 0 turns, they should replace
   the guess.

## 12. What hearth raised that the draft missed entirely

- The not-built mechanism does not exist in the contract (`StatusOutcome.status` required and closed;
  `TypeVerdicts` is `str | None`; `RunRecord` has one cap; the reason table has no part-count or header-bytes
  cap); `AttachmentOccurrence.route` has the identical defect to `status` and the draft never says what `route`
  is in Phase 1; `EmailDocument.times = []` is the same overload.
- `FACTS` declarations must precede sidecars; the oracle hard-fails on an unmodelled fact.
- The RFC 2045 5.2 default `text/plain; charset=us-ascii` is unassigned: the walker deliberately records
  `content_type = None` for a part with no Content-Type, so the Phase 1 reader must supply the default as a
  **projection**, never into the raw field.
- The ordinal and the kind contradict D3; the all-zero-depth normal state is mis-stated by a per-view scalar
  depth.
- The span map (HTML element to projected text) and the cid-reference set are missing from the text turn.
- Same-stdlib-both-sides: the scanner and decision 4 share `email`, so the exit-criterion-2 comparison is
  tautological for the delegated fields.
- Lone CR is shared by the walker, stdlib and likely the labels.
- RFC 2047 and 2231 real-world forms (an encoded word inside a quoted parameter, an empty-charset `filename*=`).
- RFC 3676 `format=flowed` unstuffing before `>` counting, and `-- ` as exactly dash dash space; list footers
  were dropped from the turns although the design put them in v1.
- RFC 2046 5.1.1 boundary ambiguity (a boundary that is a prefix of another) needs an exclusion list, or the
  third check fails the package for being right.
- The anti-vacuity triple proves only that a symbol **exists**; "reached" is the property needed.
- `limits` has no mechanism for "untrusted"; the entry point regresses D1's named error.
- Duplicate `Content-Type` and `MIME-Version`, `multipart/digest` default, duplicate Content-ID: first-win is
  silent in `walk._header_value`.
- Registry mechanics are a real per-gap cost (`tests/test_phase0_gaps.py` reads the design's bullets and
  requires an entry by the filename `phase0-gaps.md`, both ways): every named gap costs a registry line, a doc
  entry, a fixture and a mutation case, so the new ids must be few; and "Phase 1 ids living in a file called
  `phase0-gaps.md`" is itself a 1.0a decision.

## 13. What this debate could not settle

- Any claim about real producers' class names, ids and text (Outlook.com, Apple Mail, Thunderbird, Yahoo,
  mobile): no real mail is in the repo, and recall by two models of one family is not evidence.
- The html.parser, libxml2 and `email` behaviour deltas across 3.11 and 3.14 and across patch levels (section 9).
- Whether the five-id gap budget is enough for real mail; the owner's corpus probe is the only answer.
- Test-per-turn ceilings (section 11, item 8).
