# Turn BODY1: a public, on-demand body-text accessor and a bounded attachment-payload accessor

Status: brief for one build turn. Author: reviewer session, 2026-10-16. Builder: hearth, run from this repository (`email-extract`), after reading `CLAUDE.md`, `docs/design/email-extraction-design.md` (D14 body views, D1-D16 generally) and the Phase 1b/0.2.0 notes.
Requested by the docextract hub (`../docextract-hub/docs/design/content-index-debate.md` decision 7, and `collection-workflows-idea.md`): the hub cannot search or read email **body** text, nor read an **attachment's** contents (for example an Excel invoice sent in an email), because this
library records digests and structure only ("No body text is stored", `model.py`). Out of scope: storing body text in any record or manifest, any change to `EMAIL_PARSER_VERSION`, `OUTPUT_SCHEMA_VERSION` or any existing manifest byte, any change to
the `.eml`/`.msg` parsing results already recorded, OCR, HTML rendering, thread reconstruction, any network code, and any hub change. **Do not commit.** Do not release (no tag, no version bump of the distribution beyond what the ledger demands; report it).

**Pace this turn.** Iterate on the new test files; run the whole suite once per interpreter at the end (`python -m pytest -q`, your usual 3.11 and 3.14 environments), plus `python tools/update_behavior_ledger.py --check` and the other `--check` tools this repo's CLAUDE.md names.

## Why

A person named only inside a letter body is invisible to the hub's search and to its cited read, and an invoice attached to an email is invisible to everything. The library already decodes bodies (`text.py`, `htmltext.py`, `rfc2047.py`, the decode chain) to compute its digests; this turn exposes that
decoded text **on demand, nothing stored**, and exposes attachment bytes so the hub can route them to the workbook and word families.

## Decisions (reviewer's; say so with evidence rather than building around one)

**D1. `body_text(source, *, max_chars=...)`**, a new public function (export it from `emailextract/__init__.py` and `__all__`; accept a path, `bytes`, and an `.msg` the same way `ingest_path` does, reusing `MsgContainer(bytes)` and the existing readers; do not duplicate parsing). Returns a frozen
`BodyText`: `view` (`"plain"` or `"html"`, the **same body view D14 chooses** for the digest: HTML if present, else plain), `text` (the decoded text, for HTML through the existing `htmltext` path, deterministic), `segments` (a list of `(start, end, locator)` over `text`, using the library's existing `Locator`
types so a hit can be cited "down to the line" as the sibling extractors cite spans), `truncated` (bool, true when `max_chars` cut it), `char_count`, and the stamps (`EMAIL_PARSER_VERSION`, `DECODE_CHAIN_VERSION`, `HTMLTEXT_VERSION`, the new `BODY_TEXT_VERSION`). A message with no body returns an empty
`BodyText` with an explicit reason id, **not** an exception. A message that cannot be decoded returns a typed refusal reusing the library's existing reason ids where they apply (find them; invent a new id only if none fits, and register it in the vocabulary the way the repo requires).
Bounded: a documented default `max_chars` and a hard ceiling; memory bounded by the existing `max_input_bytes` rules. **Nothing is stored or cached; no new field appears in any manifest or record.**

**D2. `iter_attachment_payloads(source, *, max_count=..., max_bytes=...)`**: yields frozen `AttachmentPayload(occurrence_ref, filename, media_type, size, data)` for each **non-inline-decorative** attachment (the library already classifies decorative hints; reuse them and expose which were skipped),
in the manifest's own occurrence order, decoding transfer encodings (base64, quoted-printable) with the existing decode chain, with **per-attachment and total byte ceilings** (a message of 200 attachments or a 2 GB base64 blob must not exhaust memory; a refused attachment yields a typed `AttachmentRefusal` with the reason, never silently dropped
and never an exception for one bad attachment). The `occurrence_ref` is the same identity the manifest's `AttachmentOccurrence` carries, so a hub citation can join them. **Attachments that are themselves messages (`.eml`, `.msg`) are returned as payloads and are not recursed into here** (recursion depth and routing are the hub's concern; say so in the docstring).
No attachment bytes are stored or logged by this library.

**D3. Versions and ledger.** Add `BODY_TEXT_VERSION = "1"` (and `ATTACHMENT_ACCESSOR_VERSION = "1"` if you judge the second function a separate contract; say why) to `versions.py` in that file's style (what each covers; what moves it), and the matching `tools/behavior_ledger.py` components
keyed by them, recorded only with `tools/update_behavior_ledger.py`. **No existing component's fingerprint may move.** If any would, stop and report. The existing eval gates and `make_fixtures.py --check` stay green.

**D4. Labels (the repo's hand-typed protocol).** For a fixed set of **at least ten** existing synthetic fixtures covering plain, HTML-only, multipart/alternative, a `.msg`, a quoted-printable body, a non-UTF-8 charset, an empty body, a body with a tracking pixel and zero-width characters, a forwarded message, and an
attachment-bearing message, hand-type the **expected body text** (and the expected attachment list with sizes) **before** running the accessor, freeze them in a typed file, and compare after; corrections only with construction or spec evidence, findings not fixes, exactly as the repo's earlier label protocols (read how Phase 1b did it). Report every disagreement.

**D5. Tests and mutations.** Tests: each fixture's text equals its typed label; the view chosen equals D14's; segments cover `text` without gaps or overlap and every locator resolves to the segment's text; `truncated` and `max_chars` boundaries; no body; undecodable; `.msg` and `.eml` of the same message agree on text; attachment order and refs equal the manifest's; byte ceilings (a synthetic 50-attachment and a large-base64 message stay within the ceilings and
report refusals); an attachment that is itself a message is returned unrecursed; **no manifest byte changes** (re-run every recorded golden); import audit: no network, no new dependency. Mutations (each fails a named test, restored byte for byte from a backup copy, `PYTHONDONTWRITEBYTECODE=1`): HTML chosen when plain is the digest's view; text returned for the wrong view; segments overlap; a locator off by one; `max_chars` ignored; truncation not flagged; a
transfer encoding not decoded; the byte ceiling removed; an attachment dropped silently; a nested message recursed; occurrence order changed; a decorative attachment returned; body text written to a manifest field; `BODY_TEXT_VERSION` not bumped when decoding changes.

## Reporting

Write `docs/design/turn-BODY1-note.md`: what changed, every disagreement with the typed labels, every divergence from this brief with evidence, the mutation table, the public signatures, the measured cost (time and peak memory) for a 20 MB message and a 50-attachment message, and what the hub will need to do with each result (it routes
`data` by `media_type` to the workbook or word families and cites by `occurrence_ref` plus the child's own citation).
