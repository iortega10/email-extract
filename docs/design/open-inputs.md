# Open inputs: things only the owner can supply

Nothing here blocks Phase 0. Each item changes what later phases can *claim*, not what can
be built, and each has a defined fallback so work continues without it. Update this file when an
input arrives or a fallback changes.

## 1. Real sample emails: OPEN

- **What it is:** a small set of real messages (Outlook, Gmail, Apple Mail, a reply chain with
  quoted history, a forward, messages with PDF/XLSX/DOCX attachments), kept **outside the repo**
  (`fixtures/real/` is git-ignored and machine-local). Redact before use; real mail from an
  employer or a client may be confidential and must never be committed, pasted into an issue or
  quoted in a commit message.
- **Why it matters:** every fixture is generated or hand-written in this repository. Specifically
  unverified without real mail: the HTML quote rules (Gmail, Outlook, Apple Mail DOM), i18n reply
  markers, the thread join, how real clients fold and encode headers.
- **Fallback:** those paths stay recorded as unverified (`spec_derived`) and the thread join is
  reported, not gated.

## 2. Is the real corpus `.msg`? ANSWERED: yes (first look at 3 samples)

- The owner supplied three real `.msg` files (kept outside the repo, in the owner's Downloads
  folder; never copied here). Structure only, no content: all three are OLE/CFB `IPM.Note`
  messages with Unicode (UTF-16) string properties; **HTML-only bodies** (the HTML stream is
  present, no plain-text and no RTF body); a **full transport-header stream** (6 to 19 KB: the
  `Received` chain, `Authentication-Results`, `DKIM-Signature`, `Message-ID`, `Date`, the
  Exchange `X-MS-*` headers); one recipient each; **no attachments**; no `In-Reply-To` or
  `References` (bulk and system mail, not threads).
- **Consequence:** `.msg` is promoted into v1 (D1's condition is met). What these three do **not**
  exercise: quoted reply chains, forwards, attachments (PDF/XLSX/DOCX), embedded messages, an
  RTF-only body, calendar items, encrypted mail. More samples are needed for those (redacted;
  outside the repo).
- **Design consequence to settle in Phase 0.0/1:** the "raw message" for a `.msg` is the CFB file,
  and header text lives in a UTF-16 stream inside it, so a header field's byte span is relative to
  that stream and citations to it are `part_level` (D12), not offsets into RFC 822 bytes.
- **Still blocked:** the license policy for the reader (item 3).

## 3. `.msg` reader license policy: CONFIRMED by the owner

- Decision (D1, D13), confirmed: an own `olefile`-based reader (BSD) with **no GPL anywhere**: not
  in code, optional extras, tests or dev-dependencies. `extract-msg` (GPL) and `html2text`
  (GPL-3.0) are never dependencies; running `extract-msg` by hand locally for a spot check is fine.
- The cost is fixtures: a `.msg` cannot be hand-typed, so Phase 1b builds a minimal deterministic
  CFB writer in `tools/`, plus one fixture hand-built to Outlook's observed layout.

## 4. Real term lists: OPEN (shared with word-extract)

- See `word-extract/docs/design/open-inputs.md` section 1. Build them from public sources or a list
  the owner is explicitly permitted to use; keep them outside the repo. Flag recall cannot be gated
  without human must-find labels from real documents.

## 5. Approval to touch the sibling repos for track S: OPEN

- The matcher move (`docextract_core.match`) is a behavior-preserving change to shipped
  word-extract code (a `wordextract` version bump, a `docextract-core` addition). It blocks Phase 4
  only. Not started.

## 6. The employer-ownership question

- The owner's alone to resolve. It is not asserted in code, docs or package metadata, and no real
  or employer email enters the repo.

## 7. Arrival manifest and ordering policies for the timeline layer: PARTLY ANSWERED

- **Answered:** the owner accepted the organizer plan (not first; `TimeEvent` frozen in Phase 0;
  a later `docextract-timeline`) and the design's candidate ordering policies
  (`header_date_claimed`, `received_chain_header_order`, `owner_manifest`). In-text date
  extraction stays **out of v1**.
- **Still open:** the arrival manifest for non-email files (when each came in; filesystem times are
  copy times, not evidence of arrival), and the day-first or month-first locale for in-text dates
  when that extractor is built (suggested default for US mail: month-first, recorded as
  `ambiguity=day_month` wherever it is not unambiguous).
- **Fallback:** the timeline layer is not built until word-extract emits a real `TimeEvent`;
  parsers emit time evidence meanwhile.

## 8. More redacted real samples: MOSTLY ANSWERED, a few deferred

- **Received (structure only; the files stay in the owner's Downloads folder):** eleven `.msg` and
  four `.eml` messages. Covered now: Gmail replies in both containers; a calendar-invite forward
  (`.eml`); an Outlook-authored message with an **embedded message attachment** (also saved
  standalone, so embedded and standalone forms can be compared locally); a `.msg` with an
  **ordinary file attachment (a 376 KB PDF) that carries a Content-ID**; a native **desktop-Outlook
  reply** (`.eml`: plain text has an Outlook `From:`/`Sent:` block, the HTML has `divRplyFwdMsg`
  and no `blockquote`); a small legacy `.xls` file for typing tests; and HTML-only `.msg` bodies
  throughout (the plain-text alternative is dropped on conversion).
- **The two messages named "rtf" turned out to carry no RTF stream** (HTML only, like the rest), so
  the compressed-RTF body path remains **unverified against real mail** (it stays covered by
  synthetic fixtures only; a named gap).
- **Deferred by the owner (none available):** non-English reply markers, encrypted or signed
  messages, auto-replies and bounces. Left for later; the design records them as named gaps.
- Probes of real samples print structure only and are never given to hearth's model.
