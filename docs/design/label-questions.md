# Label questions: what the Turn 0.3 sidecars leave undetermined

Question only. Nothing in this file is resolved, and `docs/design/email-extraction-design.md` is
untouched. Each item below is one `labels.undetermined` entry typed into a fixture sidecar under
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

## Q2. Which rungs does the RFC 822 charset ladder name, in order?

- **Fact id:** `decode.chain`
- **Fixture / locators:** `fixtures/raw/bad_charset.expected.json` -- parts 1.1 and 1.2
- **What the design says:** a deterministic charset ladder (ground rules, D9, D13); the rungs for
  an RFC 822 body are never named.
- **The reading the label took (not a resolution):** the Turn 0.2 order -- declared charset, then
  strict us-ascii, utf-8, windows-1252, then the recorded replacement decode.
- **Why it matters:** part 1.2's verdict is `windows-1252` as the used charset of a *replacement*
  decode, exactly the kind of value a different rung order would render differently.

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
