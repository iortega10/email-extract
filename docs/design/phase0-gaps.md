# Phase 0 known-gap registry

Every gap id this package can record, one entry each, resolved from the design's
"Known-gap ids (v1 registry)" section (`docs/design/email-extraction-design.md`) at build
spec Turn 0.6. The registry is the authority: the ids below are the registry's ids
**verbatim** -- none is invented, renamed or merged -- and `tests/test_phase0_gaps.py` runs the
correspondence both ways. The design listed **81** ids; Phase 0.6 **prunes two**
(`attach.size_cap_hit`, `attach.nesting_cap_hit`) leaving **79** entries (see "The prune").

A gap is a thing the package **declines to claim**, recorded in the manifest (never in a log).
Each entry answers four questions:

- **Missing:** what the package does not know, or did not do, when it records this gap.
- **A reader must not infer:** the wrong conclusion a consumer of the manifest could draw if the
  gap were invisible -- "unknown is a state, not an absence" (`CLAUDE.md`).
- **First emitted by:** the first phase whose code can produce the gap (design "Phasing").
- **Committed fixture:** whether a committed fixture or sidecar exercises it today -- recorded as
  a `part.gaps` entry, named by a `gaps.later` row, or proven against inline hand-typed bytes in
  `tests/test_gap_falsifiability.py`. "None yet" is not a defect: the registry is the v1 target
  and the corpus grows toward it.

## How this vocabulary relates to the status reasons

There are three distinct vocabularies, and this document is only the first:

1. **Gap ids** (`<family>.<name>`, this registry): a thing the package declines to **claim**
   about a message it did read. A gap rides on the record it is about (`part.gaps`) or is named
   for a later phase (`gaps.later`).
2. **Status reasons** (D6, the closed table in `emailextract/model.py`): `size_cap`,
   `total_size_cap`, `depth_cap` for `skipped`; `extractor_error`, `decode_failed`,
   `sibling_contract_error` for `failed`; `stream_ended_early`, `declared_length_mismatch`,
   `cap_hit_mid_stream` for `truncated`. These answer "why is this part not parsed", belong to
   exactly one status, and are **not** copied into this registry.
3. **Tri-state unknown reasons** (`unknown(reason)` on a value or a section): the reason a field
   or section is `unknown`. `emailextract/ids.py`'s `NOT_BUILT_IN_PHASE0` is one: it names the
   not-yet-built sections, not a gap. It has no `family.name` shape and is not a registry id.

A gap id and a status reason can describe the same *shape* of trouble without being the same fact:
a `skipped` part carries status `skipped` + a cap reason, and the run record keeps the cap id, the
cap value and the declared size. That is exactly why the two cap-flavoured candidate gap ids were
pruned: a gap id that says nothing the status reason and the run record do not is a second place to
disagree with the first.

## The prune (Turn 0.6)

The design flagged a **candidate prune**: `attach.size_cap_hit` and `attach.nesting_cap_hit`
versus the `skipped` reasons. Decided: **both are pruned from the registry.**

- `attach.size_cap_hit` duplicated the `skipped` reason `size_cap` (and `total_size_cap`);
  `attach.nesting_cap_hit` duplicated `depth_cap`. In v1 every cap is checked **before** the
  extractor starts (D6), so the cap's only reachable effect *is* the `skipped` status plus its
  reason; the run record already carries the cap id, the cap value and the declared size.
- A gap id adds nothing the status reason and the run record do not: it would be a second place to
  record the same fact, free to disagree with the first.
- No committed fixture or sidecar named either id, so the prune changes nothing on disk -- **no
  fixture, sidecar or label was edited** to make this decision.

The registry in `docs/design/email-extraction-design.md` was edited to drop the two ids and to
state the decision; `tests/test_phase0_gaps.py` holds both the registry and this document and
asserts the pruned pair appears in neither.

Phases named below: **0** the skeleton walker; **1** the RFC 822 parser (header projection, body
views, attachment manifest); **1b** the `.msg` reader; **2** routing, statuses and recursion;
**3** header threading and time evidence; **4** flags and rollups; **5** quote reconstruction;
**6** the read-only query API.

## headers

### `headers.malformed_line`
- **Missing:** a line in the header region that is neither `name: value` nor a fold (obs-fold); the
  walker records it as its own paragraph with `parse_status: unknown` and does **not** end the
  header region (D2 fail-open).
- **A reader must not infer:** that the header region ended there, or that the fields after the bad
  line are body. The region fails open, so `X-After` and friends are still fields (D2).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** recorded as a gap by `fixtures/raw/malformed_mime` (part 1).

### `headers.unknown_field`
- **Missing:** a field the package does not interpret specially; it is recorded verbatim with its
  decoded value as a claim and given no meaning beyond "a header named this".
- **A reader must not infer:** that the field was dropped or that it is semantically inert. It is
  present, verbatim, in the header part (D2).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.no_message_id`
- **Missing:** no `Message-ID` field; the message has no claimed identity, so nothing may be joined
  by it (D2/D7).
- **A reader must not infer:** that the message is the only one, or that a derived hash is its
  identity. Identity is content-addressed; a missing `Message-ID` is a missing *claim*.
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.duplicate_message_id`
- **Missing:** more than one `Message-ID` on one message; both are kept in order and neither is
  chosen as "the" id (D2).
- **A reader must not infer:** that the first (or last) wins, or that the message has one identity.
  The ambiguity is recorded, never resolved by position (D2/D5).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.no_date`
- **Missing:** no `Date` field; the message carries no claimed send date.
- **A reader must not infer:** that the message has no time, or that the filesystem time is its
  date. The absence of a claim is not a time (D2/D15).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.invalid_date`
- **Missing:** a `Date` field that does not parse as an RFC 5322 date; the raw value is recorded
  and no UTC moment is derived.
- **A reader must not infer:** that the message has no date, or that a nearby time is it. A value
  that does not parse is never repaired into one (D2/D15).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.date_no_zone`
- **Missing:** a `Date` field with no zone; the raw value is kept and the UTC moment is unknown
  rather than assumed to be the reader's own zone (D2).
- **A reader must not infer:** that the local zone applied, or that the moment is the wall-clock
  string read as UTC. `offset` is `unknown`, not `+00:00` (D15).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.address_unparsable`
- **Missing:** an address field (`From`, `To`, ...) whose structure does not parse; the raw value is
  recorded verbatim and no address list is claimed.
- **A reader must not infer:** that the field has no addresses, or that a best-effort split is the
  real list. Verbatim survives; the interpretation is declined (D2/D9).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.smtputf8_not_resolved`
- **Missing:** an address or display name carrying non-ASCII bytes with no declared encoding the
  package can resolve; the bytes are kept verbatim.
- **A reader must not infer:** that the non-ASCII is a display artefact, or that a guessed
  charset is the name. Verbatim is the claim; the resolution is declined (D9).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.encoded_word_invalid`
- **Missing:** an RFC 2047 encoded word (`=?charset?...?=`) whose charset or encoding does not
  decode; the raw value is kept and the decoded value is `unknown(reason)`.
- **A reader must not infer:** that the field is plain text, or that a replacement decode is the
  name. The fallback never destroys the raw bytes (D9).
- **First emitted by:** Phase 1 (the header projection).
- **Committed fixture:** none yet.

### `headers.received_chain_unverified`
- **Missing:** the `Received` trace is recorded as **claims** in header order and is never verified
  against anything (D2/D7). The standing gap: a chain that has not been checked is not a chain
  that is right.
- **A reader must not infer:** that the hops are authentic, ordered by time, or complete. They are
  claims in header order (D15: hops are ordered by header order, never by timestamp).
- **First emitted by:** Phase 3 (header threading and time evidence).
- **Committed fixture:** named by `fixtures/generated/rfc2047_folded_duplicate_received` and
  `fixtures/generated/thread_three_refs_chain` in their `gaps.later` rows (phase 3).

### `headers.mapi_header_property_disagree`
- **Missing:** in a `.msg`, the MAPI transport-header property and a header written elsewhere
  disagree; the transport header is selected for the canonical view (`value_source=transport_header`)
  and the property is kept verbatim beside it (D2/D13).
- **A reader must not infer:** that one of the two is the truth, or that the disagreement was
  resolved. Both are recorded; the conflict stands (D2).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

## body

### `body.no_boundary_found`
- **Missing:** a multipart part declares a boundary that appears nowhere in its body, so no
  delimiters are found; the whole body is kept as one region and nothing is split.
- **A reader must not infer:** that the message has no parts, or that the body is empty. The bytes
  are all there; only the declared structure is absent (D3).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** none yet -- proven against inline hand-typed bytes in
  `tests/test_gap_falsifiability.py` (no committed fixture carries it).

### `body.boundary_disagreement`
- **Missing:** the declared boundary grammar and the bytes disagree -- an open delimiter with no
  close. The boundary **is** found; its close is not (the reading the labels took; see
  `docs/design/label-questions.md` Q4).
- **A reader must not infer:** that parts are missing, or that the last part ended at a delimiter
  that is not there. Nothing is guessed; the disagreement is recorded (D3).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** recorded as a gap by `fixtures/raw/malformed_mime` (part 1) and named as
  an open question there (`labels.undetermined`).

### `body.html_quote_rule_gap`
- **Missing:** an HTML quoting construct no committed DOM rule names; the text is recorded and the
  quoting is not classified (D3).
- **A reader must not infer:** that the text is unquoted new text. An unrecognised container is a
  gap in the rule list, not evidence of level 0 -- the worst failure for this tool (D3).
- **First emitted by:** Phase 1 (body views and the DOM quote rules).
- **Committed fixture:** none yet.

### `body.i18n_reply_marker`
- **Missing:** a reply marker in a language the named rule list does not cover (e.g. `Am ... schrieb`,
  `Le ... a ecrit`); the line is recorded and the boundary is not classified.
- **A reader must not infer:** that there is no quote boundary, or that the message is all new
  text. An English-only list must never present as "no boundary found" (D3).
- **First emitted by:** Phase 1 (body views and the reply-marker rules).
- **Committed fixture:** none yet.

### `body.preamble_bytes`
- **Missing:** bytes before the first boundary delimiter; they are their own accounted region, not
  a part and not new text (D3).
- **A reader must not infer:** that the preamble is a part, or that it is irrelevant. In broken
  mail the preamble can be the whole message; it is recorded, never dropped.
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** recorded as a gap by `fixtures/generated/preamble_epilogue`.

### `body.epilogue_bytes`
- **Missing:** bytes after the final boundary delimiter; they are their own accounted region, not a
  part (D3).
- **A reader must not infer:** that the epilogue is a part or that it was dropped. It is present
  and accounted for, byte for byte (the no-silent-drop rule).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** recorded as a gap by `fixtures/generated/preamble_epilogue`.

### `body.inline_reply_interleaved`
- **Missing:** new text interleaved between quoted blocks (a bottom-posted, interleaved reply); the
  view is non-contiguous and the new text is not one contiguous run (D3).
- **A reader must not infer:** that the new text is contiguous, or that a quoted block between two
  new blocks was dropped. Non-contiguous views are legal (D3).
- **First emitted by:** Phase 1 (body views).
- **Committed fixture:** none yet.

### `body.empty_new_text`
- **Missing:** a top-posted reply whose new text is empty (the whole body is quoted history); there
  is no new text to claim.
- **A reader must not infer:** that the body is empty or that the message is malformed. An empty new
  text is a legal state, not a gap (D3) -- recorded so a reader does not mistake it for a dropped
  body.
- **First emitted by:** Phase 1 (body views).
- **Committed fixture:** none yet.

### `body.signature_undelimited`
- **Missing:** a signature or list footer detected as a **candidate** only; it is never stripped
  (stripping is fact loss) and its boundary may be undelimited (D3).
- **A reader must not infer:** that the candidate is a real signature, or that the text below it was
  removed. The text is kept and labelled a candidate (D3).
- **First emitted by:** Phase 1 (body views).
- **Committed fixture:** none yet.

### `body.decode_fallback_used`
- **Missing:** the declared transfer decoding could not run (unknown CTE, or undecodable base64),
  so the raw payload was kept verbatim with `used_cte=None` and `fallback_fired=True` (D3/D9).
- **A reader must not infer:** that the payload was decoded, or that `used_cte=None` means the part
  was never transfer-decoded. It means the declared decoding could not be applied (D9;
  `label-questions.md` Q3).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** recorded as a gap by `fixtures/raw/truncated_base64` (part 1) and
  `fixtures/raw/bad_charset` (part 1.1).

### `body.decode_destroyed_bytes`
- **Missing:** no rung of the charset ladder decoded the bytes strictly, so the recorded last resort
  (`windows-1252` with `errors="replace"`) was taken with `encoding_source=fallback`; the projection
  no longer round-trips the bytes (D3/D9).
- **A reader must not infer:** that the decoded text is the content, or that the replacement
  characters are in the message. Raw bytes are canonical; this projection is lossy (D9).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** recorded as a gap by `fixtures/raw/bad_charset` (part 1.2).

### `body.part_truncated`
- **Missing:** a part's declared length exceeds the bytes present, so the body ended early; the
  bytes present are kept and the truncation is recorded (D9).
- **A reader must not infer:** that the part is complete, or that the missing bytes were padding.
  The declared length is not fabricated (D9).
- **First emitted by:** Phase 1 (the body and its declared lengths).
- **Committed fixture:** none yet.

### `body.no_text_part`
- **Missing:** a message with no part that reads as text at all; there is no body text view.
- **A reader must not infer:** that the message is empty. It has parts; none of them is text
  (D3/D16).
- **First emitted by:** Phase 1 (body views).
- **Committed fixture:** none yet.

### `body.headers_only`
- **Missing:** a message that is headers only -- no blank line anywhere, so there is no body region
  (D3). The walker records the whole input as the header region and an empty body.
- **A reader must not infer:** that a body was dropped, or that the message is truncated. A
  headers-only message is a legal state (D3, tension with the registry noted in Turn 0.2).
- **First emitted by:** Phase 0 (the skeleton walker).
- **Committed fixture:** none yet -- proven against inline hand-typed bytes in
  `tests/test_gap_falsifiability.py` (no committed fixture carries it).

### `body.inline_data_uri`
- **Missing:** a `data:` URI in an HTML body; it is detected and recorded, never expanded into
  bytes or a part (D4).
- **A reader must not infer:** that the inline content is a part, or that it was routed. Detection
  only; expansion is a named out-of-scope gap (D4).
- **First emitted by:** Phase 1 (the HTML body view).
- **Committed fixture:** none yet.

### `body.plain_effectively_empty`
- **Missing:** a `text/plain` alternative that is present but effectively empty (whitespace or a
  stub), so it carries no new text even though the part exists (D16).
- **A reader must not infer:** that the plain body is the content, or that the alternative is the
  HTML part. Emptiness is a legal alternative state, recorded, never silently swapped (D16).
- **First emitted by:** Phase 1 (view selection).
- **Committed fixture:** none yet.

### `body.mixed_origin_quoting`
- **Missing:** quoting of mixed origin -- e.g. a Gmail container wrapping an Outlook block -- kept
  as one ordinal sequence per view with a per-boundary rule id; the origins are never reconciled
  across views (D3, Revision 2).
- **A reader must not infer:** that the mixed boundaries are one evidence family, or that a single
  quote level is true. Disagreement between families is a recorded conflict (D3).
- **First emitted by:** Phase 1 (body views and the boundary rules).
- **Committed fixture:** none yet.

## view

### `view.quote_level_disagreement`
- **Missing:** the two evidence families (structural ordinal vs literal `>` prefix depth) disagree
  about the quote level, and the named resolution rule decided between them; the conflict is
  recorded, never averaged (D3).
- **A reader must not infer:** that one family is the truth, or that the resolved level erased the
  disagreement. It is a recorded conflict (D3).
- **First emitted by:** Phase 1 (body views and the per-view levels).
- **Committed fixture:** none yet.

### `view.gap_closing_contiguous`
- **Missing:** a term whose occurrence would span a quoted interruption is **not** flagged:
  closing is contiguous. The caller supplies the closable runs (contiguous same-level spans) and
  the matcher bridges only **inside** a run, never across it (D3/D8; the seam's Phase 0 decision,
  `emailextract/seam.py`).
- **A reader must not infer:** that the term is absent, or that the quoted interruption was part of
  a matched phrase. The miss is the contiguity rule, not a missing word (D3).
- **First emitted by:** Phase 4 (the flag layer; the seam freezes the rule in Phase 0).
- **Committed fixture:** none yet.

## attach

### `attach.type_unknown`
- **Missing:** none of the three type verdicts (declared MIME, magic, container introspection)
  identified the attachment's type (D4).
- **A reader must not infer:** that the type is absent or dangerous, or that the declared MIME is
  the truth. All three are recorded; the disagreement stays (D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.type_disagreement`
- **Missing:** the three type verdicts disagree; the winner is recorded with its source and the
  disagreement flag is set (D4).
- **A reader must not infer:** that the winner is the true type, or that a losing verdict was
  dropped. Every verdict is kept (D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.ole_container_unknown`
- **Missing:** the bytes are a CFB/OLE container but its contents are not one of the recognised
  office documents (D4).
- **A reader must not infer:** that the container is empty, or that it is a `.msg`. It is an OLE
  container of an unclassified kind (D4/D13).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.zip_unexpanded`
- **Missing:** the attachment is a zip whose entries were not expanded (out of scope in v1 beyond
  the ooxml/document probes); it is recorded as a zip (D4).
- **A reader must not infer:** that the archive is empty, or that its members were read. Only the
  container was identified (D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.tnef_present`
- **Missing:** a `application/ms-tnef` body is present (a transport-neutral encapsulation); its
  contents are not expanded and the message's real body may live inside it (D4/D9).
- **A reader must not infer:** that there is no body, or that the TNEF contents were read. Presence
  is recorded; the encapsulation is a named gap.
- **First emitted by:** Phase 1 (the attachment manifest / the body type).
- **Committed fixture:** none yet.

### `attach.encrypted_ooxml`
- **Missing:** an ooxml document is encrypted (ECMA-376 `EncryptionInfo`/`EncryptedPackage`); it is
  detected and not opened (D4/D6).
- **A reader must not infer:** that it opens with a user-held password, or that it is corrupt.
  This is `encrypted` (no held secret), distinct from `legacy_office_password` (D6).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.legacy_office_password`
- **Missing:** a Word/Excel 97-2003 file is password protected (`FilePass`/RC4); it is detected and
  not opened (D4/D6).
- **A reader must not infer:** that it is corrupt, or that it is the modern ooxml encryption. This
  is `password_protected` (a held secret may open it) (D6).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.filename_absent`
- **Missing:** an attachment occurrence carries no filename (e.g. a nameless `message/rfc822`);
  the occurrence is recorded with no name.
- **A reader must not infer:** that the part has no identity, or that a name was dropped. The part
  is addressed content-first; the name may simply be absent (D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.filename_unparsable`
- **Missing:** a filename (often an RFC 2231 `filename*=` continuation) does not decode; the raw
  form is kept and the decoded name is `unknown(reason)` (D9).
- **A reader must not infer:** that a best-effort name is the filename, or that the part is
  nameless. Raw is kept; the interpretation is declined (D9/D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.disposition_absent`
- **Missing:** no `Content-Disposition`; disposition is inferred from context and recorded as a
  claim, never assumed (D4).
- **A reader must not infer:** that the part is an attachment, or that it is inline. The absence is
  recorded, not filled (D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.cid_unreferenced`
- **Missing:** a part carries a `Content-ID` that no body view references; the occurrence is
  recorded and the unreferenced cid is noted (D4).
- **A reader must not infer:** that the part is dead or should be dropped. It is present and
  recorded; "unreferenced" is not "absent" (D4).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** named by `fixtures/generated/inline_cid_referenced_and_not` in a
  `gaps.later` row (part 1.3, phase 1).

### `attach.cid_dangling`
- **Missing:** a body view references a `cid:` that no part defines; the reference is recorded and
  no part is invented (D4).
- **A reader must not infer:** that a part is missing, or that the reference is text. The dangling
  reference is its own fact (D4).
- **First emitted by:** Phase 1 (the attachment manifest / the HTML body view).
- **Committed fixture:** none yet.

### `attach.occurrence_repeated`
- **Missing:** the same content appears more than once (two occurrences of one file); each occurrence
  is recorded separately with a `same_content_hash` boolean and never merged (D4/D12).
- **A reader must not infer:** that the repeats are one attachment, or that one was dropped. Two
  occurrences are two occurrences (D12).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `attach.macro_present_inert`
- **Missing:** an office document contains a macro; it is detected and **never executed** (D10).
- **A reader must not infer:** that the document is safe, or that the macro ran. Presence is
  recorded; execution never happens (D10).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

## thread

### `thread.no_references`
- **Missing:** a message with no `References` field; it is a thread root with no claimed ancestry
  (D7).
- **A reader must not infer:** that the message is unrelated to the others, or that it is the
  earliest. No claim is not a claim of "first" (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.parent_not_in_corpus`
- **Missing:** a `References`/`In-Reply-To` parent id points outside the ingested corpus; the edge
  is recorded as a claim whose parent is absent (D7).
- **A reader must not infer:** that the parent does not exist, or that the message is a root. The
  parent is absent *from this corpus*, not absent (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** named by `fixtures/generated/thread_three_refs_chain` in a `gaps.later`
  row (phase 3).

### `thread.references_vs_in_reply_to_disagree`
- **Missing:** the `References` chain and `In-Reply-To` disagree about the parent; both claims are
  recorded and neither overrides the other (D7).
- **A reader must not infer:** that one header is authoritative, or that the disagreement was
  resolved. The conflict is recorded (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.duplicate_message_id_ambiguous_parent`
- **Missing:** two messages claim the same `Message-ID`, so a child's parent id is ambiguous; the
  ambiguity is recorded and no parent is chosen (D5/D7).
- **A reader must not infer:** that the join happened, or that the first candidate won. Duplicates
  are recorded, never merged by position (D5).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.duplicate_message_id_bytes_differ`
- **Missing:** two messages claim the same `Message-ID` but their bytes differ; both are kept and
  the equality of content is not assumed (D5).
- **A reader must not infer:** that the duplicates are the same message, or that one is a copy. The
  bytes are compared; the claim is only the id (D5).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.cyclic`
- **Missing:** the header edges form a cycle (a message claims itself as an ancestor); the cycle is
  detected and never traversed as an ordering (D7).
- **A reader must not infer:** that there is a root, or that the loop was walked to a fixed point.
  The cycle is recorded (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.date_only_ordering`
- **Missing:** a group of messages whose only ordering evidence is `Date` (no usable header edges);
  a date-only order is recorded as a claim, never as a join (D7).
- **A reader must not infer:** that the messages form a thread, or that the dates are arrival
  times. A date is not a threaded edge (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.subject_threading_not_used`
- **Missing:** messages share a normalised subject but no header edge; subject threading is **not**
  used to join them (D7).
- **A reader must not infer:** that a shared subject means one thread, or that the messages are
  related. Subject is not evidence of an edge (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.quote_reconstruction_deferred`
- **Missing:** reconstructing thread order from quoted history is deferred to a separately labelled
  layer (Phase 5); the quote-based join is not made here (D7).
- **A reader must not infer:** that the quoted text was parsed into edges, or that the deferral
  means the quoting is absent. It is recorded and the join is deferred (D7).
- **First emitted by:** Phase 5 (quote reconstruction).
- **Committed fixture:** none yet.

### `thread.thread_index_claimed_not_used_for_edges`
- **Missing:** an Outlook `Thread-Index`/`Thread-Topic` is recorded as a **claim** and is never used
  to build a thread edge (D7, Revision 2).
- **A reader must not infer:** that the index produced the edges, or that the claimed decode is
  verified. It is a claim, kept beside the real edges (D7).
- **First emitted by:** Phase 3 (header threading).
- **Committed fixture:** none yet.

### `thread.same_message_candidate_across_containers`
- **Missing:** a `.eml` and a `.msg` carry the same claimed `Message-ID` and the same body digest,
  so they are a **candidate** same message; the candidate is recorded and never merged (D14).
- **A reader must not infer:** that the two containers are one message, or that the plain-only and
  html-only pair is a candidate (different `body_digest_view` -> no candidate). It is a candidate
  (D14).
- **First emitted by:** Phase 1b (the cross-container pair, D14).
- **Committed fixture:** none yet.

## msg (Revision 2; the `.msg` reader)

### `msg.cfb_difat_extended`
- **Missing:** the CFB container uses the extended DIFAT (more than 109 FAT sectors); the walker
  records the extended form and reads through it (D13).
- **A reader must not infer:** that the ordinary DIFAT suffices, or that the file is corrupt. The
  extended form is a legal CFB state (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.class_not_ipm_note`
- **Missing:** the message class is not `IPM.Note` (a contact, appointment or other item); the class
  is recorded and the message is not read as ordinary mail (D13).
- **A reader must not infer:** that the item has no body, or that it is junk. The class is a fact
  (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.rtf_to_text_unsupported`
- **Missing:** the body is RTF-only (compressed-RTF); RTF-to-text is a named gap and the body is
  not rendered (D13/D4).
- **A reader must not infer:** that the message has no body, or that the RTF is the text. The body
  is present but not converted (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.property_tag_unknown`
- **Missing:** a MAPI property tag the reader does not recognise; the property is recorded as
  unknown rather than interpreted (D13).
- **A reader must not infer:** that the property is absent, or that a guess is its value. Unknown
  tags are kept verbatim (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.stream_truncated`
- **Missing:** a CFB stream is shorter than its declared size; the bytes present are kept and the
  truncation is recorded (D13).
- **A reader must not infer:** that the stream is complete, or that absent bytes were padding. The
  declared length is not fabricated (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.codepage_unresolved_ladder_used`
- **Missing:** neither the internet codepage nor the message codepage resolved the bytes, so the
  encoding ladder's later rungs were used; the source of the decision is recorded (D13).
- **A reader must not infer:** that the declared codepage applied, or that the text is wrong. The
  ladder rung that fired is recorded (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.embedded_depth_cap`
- **Missing:** embedded messages nest deeper than the configured cap; the embed is recorded and not
  descended past the cap (D13/D6).
- **A reader must not infer:** that the embed is empty, or that the rule was applied mid-stream.
  The cap and the declared depth are recorded on the run (D6).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

### `msg.named_property_unresolved`
- **Missing:** a named MAPI property's name-to-id mapping could not be resolved; the property is
  recorded as unresolved rather than dropped (D13).
- **A reader must not infer:** that the property is absent, or that an id stands for a name. The
  unresolved mapping is recorded (D13).
- **First emitted by:** Phase 1b (the `.msg` reader).
- **Committed fixture:** none yet.

## time (Revision 2)

### `time.hop_timestamp_unparsable`
- **Missing:** a `Received` hop's timestamp does not parse; the hop is still ordered by **header
  position** and its moment is `unknown(reason)` (D15).
- **A reader must not infer:** that the hop has a time, or that the chain reordered around it.
  Header order is fixed; the moment is unknown (D15).
- **First emitted by:** Phase 3 (time evidence).
- **Committed fixture:** none yet.

### `time.calendar_rrule_unparsed`
- **Missing:** an `.ics` `RRULE` (recurrence) is not expanded; the rule is recorded as unparsed and
  only the minimal calendar facts are read (D4/D15).
- **A reader must not infer:** that the event happens once, or that the occurrences were
  materialised. Recurrence is a named gap (D15).
- **First emitted by:** Phase 1 (minimal `.ics`), recorded in the time registry.
- **Committed fixture:** none yet.

### `time.calendar_vtimezone_unresolved`
- **Missing:** a `VTIMEZONE` definition is not resolved into concrete offsets; local times stay
  local and `offset` is `unknown` (D15).
- **A reader must not infer:** that the local time is UTC, or that the zone was applied. The zone
  is unresolved (D15).
- **First emitted by:** Phase 1 (minimal `.ics`), recorded in the time registry.
- **Committed fixture:** none yet.

### `time.calendar_floating_time`
- **Missing:** a calendar time with no zone (a floating time); it is recorded with `offset` unknown
  and is never placed against zoned evidence (D15).
- **A reader must not infer:** that the floating time is the reader's local zone, or that it sorts
  with zoned events. A floating time is not placed (D15).
- **First emitted by:** Phase 1 (minimal `.ics`), recorded in the time registry.
- **Committed fixture:** none yet.

### `time.thread_index_undecodable`
- **Missing:** an Outlook `Thread-Index` value cannot be decoded into its claimed timestamps; it is
  recorded as an undecodable claim (D7/D15).
- **A reader must not infer:** that the index is empty, or that a partial decode is the claim. The
  failure is recorded (D15).
- **First emitted by:** Phase 3 (time evidence).
- **Committed fixture:** none yet.

### `time.in_text_dates_not_extracted_v1`
- **Missing:** dates mentioned in the text ("01/02/2026", "next Friday") are **not extracted** in
  v1; the in-text extractor is a separate, labelled, rule-based layer with its own version (D15).
- **A reader must not infer:** that a mentioned date is arrival evidence, or that a date-like
  string is a `TimeEvent`. In-text dates are excluded from arrival ordering (D15).
- **First emitted by:** Phase 3 (time evidence; the extractor itself is not in v1).
- **Committed fixture:** named by `fixtures/time/future_date_in_text` in a `gaps.later` row
  (phase 3).

### `time.arrival_unknown_non_email`
- **Missing:** a non-email file's arrival has no evidence beyond filesystem timestamps; the arrival
  is `unknown` unless the owner supplies a manifest (`trust=user_supplied`) (D15).
- **A reader must not infer:** that a filesystem time is the arrival, or that the file has no
  arrival. Filesystem time is not arrival evidence (D15).
- **First emitted by:** Phase 3 (time evidence; the owner manifest is a later input).
- **Committed fixture:** none yet.

## sibling

### `sibling.store_absent`
- **Missing:** the child's content hash resolved to no store root the locator knows; the child
  citation is `unknown` **whole** (D12).
- **A reader must not infer:** that the child was never extracted, or that a partial citation is
  usable. A missing store makes the whole child bucket unknown (D12).
- **First emitted by:** Phase 2 (routing to siblings).
- **Committed fixture:** none yet (proved against the fake sibling store in
  `tests/test_siblings.py`).

### `sibling.child_absent`
- **Missing:** the store root exists but holds no child for that hash; the child citation is
  `unknown` whole (D12).
- **A reader must not infer:** that the store is missing, or that the child is empty. The store is
  present; this child is not in it (D12).
- **First emitted by:** Phase 2 (routing to siblings).
- **Committed fixture:** none yet (proved against the fake sibling store).

### `sibling.version_mismatch`
- **Missing:** the child store's revision does not match the version the link expects; the citation
  is `unknown` whole (D12).
- **A reader must not infer:** that the child is corrupt, or that a near-miss revision is usable.
  The mismatch is recorded (D12).
- **First emitted by:** Phase 2 (routing to siblings).
- **Committed fixture:** none yet (proved against the fake sibling store).

### `sibling.not_installed`
- **Missing:** the sibling package is not importable in this environment; the child is recorded
  `not_installed` with `needed_sibling` (D4/D6, environmental).
- **A reader must not infer:** that the attachment is unextractable, or that the message changed.
  Re-running with the extra installed flips it (D6).
- **First emitted by:** Phase 2 (routing to siblings).
- **Committed fixture:** none yet (the `not_installed` path is proved with the siblings genuinely
  absent in `tests/test_siblings.py`).

### `sibling.contract_unknown`
- **Missing:** the child store speaks a contract shape this package does not know; the citation is
  `unknown` and no field is guessed (D12).
- **A reader must not infer:** that the child has no result, or that a partial decode is the
  citation. An unknown contract is unknown whole (D12).
- **First emitted by:** Phase 2 (routing to siblings).
- **Committed fixture:** none yet.

## security

### `security.remote_content_present`
- **Missing:** a body references remote content (a tracking pixel, an external image); the reference
  is recorded and nothing is fetched -- no network, ever (D10).
- **A reader must not infer:** that the content was retrieved, or that its absence means the body
  is complete. Remote content is recorded, never loaded (D10).
- **First emitted by:** Phase 1 (the HTML body view).
- **Committed fixture:** none yet.

### `security.macro_present`
- **Missing:** an office attachment contains a macro; it is recorded and never executed (D10).
- **A reader must not infer:** that the document is safe to open, or that the macro ran. Presence
  is the claim (D10).
- **First emitted by:** Phase 1 (the attachment manifest).
- **Committed fixture:** none yet.

### `security.injection_boundary_applied`
- **Missing:** text that could be read as instructions to a model (prompt-injection boundaries) was
  flagged; the boundary is applied so a downstream consumer sees it as data (D10).
- **A reader must not infer:** that the text was altered or removed. It is present and labelled; the
  flag is the claim (D10).
- **First emitted by:** Phase 1 (the body views).
- **Committed fixture:** none yet.
