# Label questions: what the Turn 0.3 sidecars leave undetermined

Question only; each question is kept even after it is settled. `docs/design/email-extraction-design.md` was
untouched by Turn 0.3; **Revision 3 (Phase 1 Turn 1.0a)** now settles some of the questions below, and each
settled entry carries a `Settled by revision 3:` line. A question that revision 3 does **not** close keeps
its text and is listed in "Entries revision 3 does not close" at the end. The sidecar **values are never
edited** (decision 12: a label that contradicts a settled decision is a *finding*, reported with both
values and the bytes). Each item below is one `labels.undetermined` entry typed into a fixture sidecar under
`fixtures/` (Turn 0.3): the design left a reading open, so the label records the fact it *can*
state, names the open question, and refuses to assert the rest. The sidecar text is quoted here
verbatim; the label's tentative reading is reported, never adopted. Settle the question by editing
the design, then update the sidecar -- never the other way round (D11: labels are typed
independently of the walker, and a label that contradicts the walker is a finding).

Eight entries across six sidecars, four distinct questions.

## Q1. Does the charset ladder run over a non-text payload?

- **Fact id:** `decode.chain`
- **Fixtures / locators:**
  - `fixtures/generated/attachments_mixed.expected.json` -- parts 1.2 to 1.5 (PDF, xlsx, docx, png)
  - `fixtures/generated/inline_cid_referenced_and_not.expected.json` -- parts 1.2 and 1.3 (two pngs)
  - `fixtures/generated/multipart_mixed_wraps_alternative.expected.json` -- part 1.2 (PDF)
- **What the design says:** a decode chain per part (D3) and a deterministic charset ladder
  (D9, D13); it never says whether the ladder runs when the payload is not text.
- **The reading the labels took (not a resolution):** the transfer verdict is stated (e.g.
  `base64`) and `used_charset` / `encoding_source` are left `null`, rather than a charset verdict
  invented for binary bytes.
- **Why it matters:** the answer decides a *gap*, not just a field. In `attachments_mixed`, parts
  1.3 (xlsx) and 1.5 (png) contain octets no strict rung decodes (windows-1252 strict rejects
  them) and would record `body.decode_destroyed_bytes`, while the pdf and docx would not. In
  `inline_cid_referenced_and_not`, `logo.png` would record that gap and `spare.png` would decode as
  windows-1252 cleanly -- two sibling png parts disagreeing under one reading.

**Settled by revision 3: decision 8.** The offset map (and `exact`) is built only over a **text part's**
strict decode of its **used** charset; a binary payload has no charset verdict, so the ladder does not run
over it and `used_charset`/`encoding_source` stay `null` -- the reading the labels took. Every part still
carries a decode chain (D3), but a binary part's chain is the identity throughout. This **confirms** the
shipped walker behaviour (`DECODE_CHAIN_VERSION` 2) rather than reopening it; the entry is kept because the
design says so only indirectly.

## Q2. Which rungs does the RFC 822 charset ladder name, in order?

- **Fact id:** `decode.chain`
- **Fixture / locators:** `fixtures/raw/bad_charset.expected.json` -- parts 1.1 and 1.2
- **What the design says:** a deterministic charset ladder (ground rules, D9, D13); the rungs for
  an RFC 822 body are never named.
- **The reading the label took (not a resolution):** the Turn 0.2 order -- declared charset, then
  strict us-ascii, utf-8, windows-1252, then the recorded replacement decode.
- **Why it matters:** part 1.2's verdict is `windows-1252` as the used charset of a *replacement*
  decode, exactly the kind of value a different rung order would render differently.

**Not settled by revision 3.** No decision of revision 3 names the ladder's rungs. The design still says
only "a deterministic charset ladder" (D9/D13); the rung order the labels follow is the Turn 0.2 order
(declared charset, then strict us-ascii, utf-8, windows-1252, then the recorded replacement decode). The
question stays open and is listed at the end: to close it the design must **name the rungs**, which is a
design edit, not a Phase 1 decision. The sidecar is not touched.

## Q3. What is `used_cte` when the declared transfer decoding cannot run?

- **Fact id:** `decode.chain`
- **Fixture / locator:** `fixtures/raw/truncated_base64.expected.json` -- part 1 (a base64 run cut
  mid-quantum, no padding)
- **What the design says:** `used_cte` is recorded beside `declared_cte`; it never says what
  `used_cte` is when the declared transfer decoding cannot be applied to the bytes.
- **The reading the label took (not a resolution):** `null` -- no transfer decoding was used --
  which is what Turn 0.2's walker also records.
- **Why it matters:** `null` versus an explicit identity verdict reads differently: a reader that
  saw `used_cte: null` could equally conclude the part was never transfer-decoded at all.

**Settled by revision 3: decision 8.** `used_cte` stays `null` when the declared transfer decoding cannot
run (no transfer decoding was used), and the part is `part_level` with the reason `cte_not_identity` -- or
`decode_fallback` when the charset ladder's last resort ran -- never `exact`, and **no within-part byte
span is emitted**. Decision 8 names those reason ids and the rule; the label's `null` reading is the
settled one, and the reading a reader should *not* take (that the part was never transfer-decoded) is what
the `body.decode_fallback_used` entry in `docs/design/phase0-gaps.md` already warns against.

## Q4. Is a missing close delimiter `boundary_disagreement` or `no_boundary_found`?

- **Fact id:** `body.boundary_disagreement`
- **Fixture / locator:** `fixtures/raw/malformed_mime.expected.json` -- part 1
- **What the design says:** the gap is recorded when the declared grammar and the bytes disagree
  (D3; the registry's `boundary_disagreement`); it does not say whether a *missing close delimiter*
  is that gap or the sibling `no_boundary_found`.
- **The reading the label took (not a resolution):** missing close is `boundary_disagreement` --
  the boundary *is* found, its close is not.
- **Why it matters:** the two ids lead a reader to different conclusions about what the message
  contains.

**Settled by revision 3: decision 3.** A missing close delimiter is `body.boundary_disagreement` -- the
boundary **is** found, its close is not. `body.no_boundary_found` is the **absence** answer and nothing
else (decision 3's trigger amendment: it fires only when no boundary rule fired and the text is not a
label-shaped unknown-language block). So the reading the labels took is the settled one: missing close is
`boundary_disagreement`, exactly as `docs/design/phase0-gaps.md`'s `body.boundary_disagreement` entry now
records, and the build spec's independent splitter check gates on `body.boundary_disagreement` for a
missing close delimiter rather than on the byte spans.

## Entries revision 3 does not close

One of the four questions stays open; every other question above was settled by revision 3 (the
`Settled by revision 3:` lines), and **no question is deleted and no sidecar is edited**.

- **Q2 -- the RFC 822 charset ladder's rungs, in order.** Not named by any decision (listed above). This
  is a **design gap**: the design says "a deterministic charset ladder" but never names the rungs for an
  RFC 822 body. Closing it needs a design edit naming the rungs (the Turn 0.2 order the labels follow:
  declared charset, then strict us-ascii, utf-8, windows-1252, then the recorded replacement decode), not
  a Phase 1 decision. **OPEN QUESTION** for the owner/designer; the sidecar stays as typed.
