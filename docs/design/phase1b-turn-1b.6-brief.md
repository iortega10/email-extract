# Turn 1b.6: message-level facts -- subject, sender, recipients, time properties, and the observation gaps

Status: brief for one build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `fbdbe84` (Turn 1b.5
committed: `msgcontainer.py`, headers and one HTML body end to end). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh
session. **Do not commit.**

**Pace this turn.** It is a medium turn with no new architecture. While iterating run only the files you touch; run the full suite
once at the end on the primary interpreter, once on 3.11, then the mutations. (1b.5's 3.11 pass took 20 minutes under machine load and
2.8 s per file in isolation: if the full run is slow, say so and do not chase it.)

## What this turn is

A `.msg` already becomes an `EmailDocument`. This turn records the **MAPI-side facts about the message** as evidence beside the
headers, never merged into them (build spec D2/D13): the **subject**, the **sender**, the **recipient rows**, the **time properties**,
and it finishes the **observation-to-gap mapping** that 1b.5 left half done. It adds no body, no attachment, no embedded message
(1b.7), no RTF (1b.8). It emits **no `TimeEvent`** (`times_axis` keeps its not-built marker) and does not compare a MAPI time with the
`Date` header (Phase 3 does).

Read first: `phase1b-turn-1b.5-brief.md` (D1-D10: the layout this turn must not disturb) and the 1b.5 outcome note in
`phase1b-ledgers.md` (**especially "What Turn 1b.6 and 1b.7 need from this turn" and "Reported, not bent"**),
`phase1b-contract.md` section 6 (the `container_facts` table) and section 13, `phase1b-facts.md` (the `msg.recipients` and
`msg.time_facts` value shapes: they are fixed, typed in advance), `phase1b-build-spec.md` ("Further decisions" 5, 6, 11 and the
"What a `.msg` document carries" section), `phase0-gaps.md` (the entries for `headers.mapi_header_property_disagree`,
`msg.recipient_table_unreadable`, `msg.property_tag_unknown`, `msg.named_property_unresolved`, `msg.codepage_unresolved_ladder_used`),
`emailextract/msgcontainer.py`, and `emailextract/mapi.py` (read-only except D2 below): `Property`, `RecipientRow`, `MapiMessage`,
`KNOWN_TAGS`, `read_recipients`, `declared_counts`.

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. Where a message-level fact lives: a container attribute, not a new `EmailDocument` field.** `EmailDocument` has no field for
subject, sender, recipients or times, and the schema does not move this turn (no `OUTPUT_SCHEMA_VERSION` bump; 1b.1 did the one bump).
The established channel is the container attribute the assembler or a later consumer reads with `getattr` (the 1b.1 `cap_observations`
and 1b.5 `container_gaps` pattern). So `MsgContainer` publishes one frozen `message_facts` attribute (a `NamedTuple`/frozen dataclass
you design, fully typed, all-`str | None`/`int`/tuple, no `Property` objects inside) holding: the subject fact, the sender fact, the
recipient rows and the time rows. **Nothing consumes it in this turn**: the oracle measurers (`msg.recipients`, `msg.time_facts`,
sidecars) are Turn 1b.10, and `emailextract/evals/**` stays out of the allow-list. The tests read the attribute directly, and
`container_facts` carries the two flat key families below. Do not add the facts to `EmailDocument`, `ContainerFacts` beyond D4, or
`to_json` output.

**D2. Known tags (a small, named edit in `mapi.py`, the one the allow-list adds).** `KNOWN_TAGS` currently lacks the time and sender
tags, so a message that carries them would raise `msg.property_tag_unknown` for properties this turn is about to read. Add, **table
rows only** (no logic, `READER` behaviour for every existing fixture unchanged): `0x0039` client submit time, `0x0E06` message
delivery time, `0x3007` creation time, `0x3008` last modification time (all `(PT_SYSTIME,)`), `0x0C1A` sender name, `0x0C1E` sender
address type, `0x0C1F` sender email address, `0x5D01` sender SMTP address (all `(PT_STRING8, PT_UNICODE)`). `0x0037` (subject) is
already known. The `source` column is `"MS-OXPROPS"` (not observed in the real eleven-file spike except `0039`/`0e06`, per
`msg-architecture.md`; P2 is the owner's to run). **Do not** add any other tag. Run `tests/test_mapi.py` after this edit alone and
list any pin that moves (none is expected: no committed fixture carries these tags). If one does, stop and report.

**D3. The subject fact.** Fields: `property_text` (the decoded `0x0037` text, `None` if absent or faulted), `property_fault`,
`header_text` (the decoded `0x007D` `Subject:` field text, `None` if there is no such field), `canonical` (`"transport_header"` when
a header text exists, else `"mapi_property"` when only the property exists, else `None`), and `value_source` equal to `canonical`
(**this is the fact-level `value_source` attribute 1b.5 reported it could not carry**: the registry entry for
`headers.mapi_header_property_disagree` asks for it, and it arrives here). Both texts are kept **verbatim**: no stripping, no case
folding, no whitespace normalisation, **including any leading control character** (Outlook can store a prefix marker in `0x0037`; a
mismatch caused by it is reported as the data it is, never repaired). The 1b.5 gap `headers.mapi_header_property_disagree`
(`0x0037` against the header's `Subject:` text, detail = the property text) is unchanged in behaviour; the fact is now its second
carrier. A message with the property and no header: canonical `mapi_property`, no gap (nothing disagrees). `msg_unicode_subject` pins
non-ASCII and a `001F` string.

**D4. The sender fact, and no sender comparison.** Fields: `name` (`0x0C1A`), `address_type` (`0x0C1E`, raw string, `None` if
absent), `address` (`0x0C1F` as stored), `smtp_address` (`0x5D01`), each a decoded text or `None`, plus `value_source` =
`"mapi_property"`. Kept raw: an Exchange sender (`EX`) keeps its `/O=...` form in `address`, and `smtp_address` is only ever the
`0x5D01` value, never derived from `address`. **This turn does not compare the sender with the `From` header and emits no sender
gap**: the disagreement semantics for display names and address forms are not measured, and a noisy gap here would be a guess. Say in
the note that this is deliberate, and what a future comparison would need.

**D5. Recipients: rows from the directory, kept in index order, duplicates kept.** One record per `RecipientRow`, in the order
`mapi.read_recipients` returns them (directory index order): `kind` (`to`/`cc`/`bcc`/`unknown`), `kind_raw`, `display_name`,
`address` (`0x3003`, as stored), `address_type` (`smtp`/`ex`/`unknown`), `address_type_raw`, `smtp_address` (`0x39FE` if present),
`fault`, and `value_source = "mapi_property"`. The sidecar shape in `phase1b-facts.md` is `[kind, display_name | null, address |
null, address_type]`; the extra fields are the container record's, and 1b.10 projects the four. If you believe the sidecar shape
should carry `smtp_address`, **report it as a finding**: editing the shape is the owner's, before any sidecar uses it. A duplicated
row (`msg_recipients_bcc_duplicates`) is **two records**, never merged, never reordered, never de-duplicated. `address` is `None` when
the stored text is empty or faulted, never an invented value. These are distinct from the header stage's address rows: nothing in
`headers` changes.

**D6. `recipient_count` is the number of directory rows, not the declared count.** `container_facts["recipient_count"]` is
`str(len(message.recipients))` (the registry: "the reader trusts the directory for the recipient rows"). The declared count
(`MapiMessage.declared_recipient_count`) is **not** published as a fact; a disagreement between the two is the
`msg.recipient_table_unreadable` observation (D8). For a message the class gate stopped (`stopped`), `recipient_count` and every
`time.*` key are **absent** (nothing past the class was opened), not `0`; say so in the note and test it.

**D7. Time properties: raw, lossless, canonical, flat.** For each of `0x0039`, `0x0E06`, `0x3007`, `0x3008` that is **present with
type `PT_SYSTIME` and decoded without a fault**, publish exactly two `container_facts` keys, in ascending tag order:
`time.<tag>.filetime_hex` (16-digit **lowercase** hex of the raw `u64`, no `0x`; `Property.value_hex` already is this, verify and use
it) and `time.<tag>.utc` (the FILETIME rendered as ISO-8601 UTC with a `Z` suffix, **whole seconds, truncated** from 100 ns ticks,
using integer arithmetic from the FILETIME epoch 1601-01-01; the rendering is a convenience, `filetime_hex` is the compared value).
A tag that is absent, of another type, or faulted gets **no keys** (never a placeholder). A FILETIME whose rendering would leave the
range the rendering can express (year > 9999) gets `utc = "unrepresentable"` and the hex still present; do not raise, do not clamp,
do not invent a gap id (the budget of new ids is spent). A value of `0` renders as `1601-01-01T00:00:00Z`: **no sentinel is
interpreted** ("zero means unset" is a Phase 3 reading, not evidence). The MAPI times and the `Date` header stay distinct; no `Date`
parsing changes (`msg_time_property_vs_date_header` pins that both are present and unreconciled). `times_axis` and `times` stay as
they are.

**D8. Finish the observation-to-gap mapping (the half 1b.5 left).** `mapi.read_message` raises message-level observations; 1b.5
mapped only the class gate's. Map the remaining four into `MsgContainer.container_gaps` (same `ContainerGap` type, same publication
channel, still **not persisted**: the persistence is 1b.10, which owns `evals/`):
* `msg.recipient_table_unreadable` -- detail names the cause: `"declared=<n> rows=<n>"` for a count disagreement, else the row/table
  fault. Emitted once per message.
* `msg.property_tag_unknown` -- **one gap per message** (the reviewer's resolution of 1b.4's open aggregation question: per message,
  not per table or per pair), detail = the sorted distinct `tag:type` pairs from `MapiMessage.unknown_tags`, joined by `,`.
* `msg.named_property_unresolved` -- once per message when `mapi` raises it, detail = the sorted distinct named `tag:type` pairs from
  `MapiMessage.named_tags`.
* `msg.codepage_unresolved_ladder_used` -- once per message when `mapi` raises it. Detail = the surface set it fired on, if `mapi`
  exposes it; otherwise empty, and report that the surface set is not available without a `mapi.py` change.
Every gap id is a registry id; read each registry entry and make the emission match its text. If an entry's text does not match what
`mapi` can know (as 1b.4's `msg_codepage_disagree` sentence did), **report it and do not bend the code**; `phase0-gaps.md` may be
edited only for a sentence that is wrong, each edit listed. The gap order inside `container_gaps` is deterministic (the order of
`mapi.OBSERVATION_IDS`, after the 1b.5 gaps). `class_absent` stays as 1b.5 left it (a `PARSED` document, no invented gap): unchanged.

**D9. Nothing in the 1b.5 layout moves.** The virtual bytes, span rows, `part_id`s and every 1b.5 test result are unchanged by this
turn: a recipient or time property adds no region to the projection (they are not in the RFC 822 framing). If a 1b.5 test needs an
edit, that is a finding: stop and say why.

## Order of work

1. **D2** (the `KNOWN_TAGS` rows) and `tests/test_mapi.py` alone; confirm nothing moved.
2. Fixtures, construction tables **typed first** in `tests/support/msg_construction.py` from MS-OXPROPS and the layouts B1-B4 already
   encoded there (property table entries, recipient storages), then `tools/make_msg_fixtures.py`, `fixtures/msg/SHA256SUMS`. Add the
   five catalogue fixtures this turn owns: `msg_recipients_display_only`, `msg_recipients_ex_no_smtp`, `msg_recipients_bcc_duplicates`,
   `msg_time_property_vs_date_header`, `msg_unicode_subject`. **No `.msg` sidecars** (`evals/labels.py` still accepts only `.eml`).
   A hand-typed expectation for each (what the facts must be) is written before the code, in the test file.
3. `msgcontainer.py`: `message_facts` (D1), the sender/subject/recipient records (D3-D5), `recipient_count` and `time.*` (D6, D7).
   Tests: `tests/test_msg_message_facts.py` (3 declared), `tests/test_msg_recipients.py` (2), `tests/test_msg_time.py` (3).
4. **D8** (the gap mapping) and its tests (put them in `tests/test_msg_message_facts.py` and `tests/test_msg_recipients.py`).
5. Hostile and boundary cases (below), the extras, then full suites, `--check` tools, mutations, the outcome note.

If the turn runs long, the clean boundary is the end of **step 3**.

## Tests

The 8 declared tests of the `declaration turn=1b.6` block, **names exactly as declared** (`phase1b-ledgers.md`):
`test_subject_sender_and_class_are_mapi_properties`, `test_the_property_versus_header_conflict_pair_is_recorded`,
`test_message_class_is_recorded_verbatim`, `test_recipients_are_facts_beside_the_headers`,
`test_display_only_and_ex_recipients_are_recorded`, `test_time_properties_are_flat_hex_keys`,
`test_the_filetime_hex_is_lossless_and_canonical`, `test_no_timeevent_is_emitted`. Plus these extras (declare them in the same
block in `phase1b-ledgers.md` and add to `tests/test_turn_declarations.py` as 1b.5 did):
* **Recipient rows, hand-typed.** For each of the three recipient fixtures the expected record list is typed by hand in the test
  (kind, display name, address, address type), including: display-only has `address is None` and `address_type` as stored; the EX row
  keeps its `/O=` form in `address` and its raw type `EX`; the bcc fixture yields **two** records for the duplicated row, in
  directory index order, plus a `bcc` kind. The `olefile` oracle cross-check reads the same rows independently (the 1b.4 pattern) and
  agrees.
* **`recipient_count` is the directory count.** Build a message whose recipient-count header field (`@16`) disagrees with its real
  rows (do it in the test by editing the construction, not as a committed fixture): `recipient_count` is the real row count and the
  `msg.recipient_table_unreadable` gap is present with `declared=<n> rows=<n>`.
* **FILETIME, hand-computed.** Pick at least three raw `u64` values with a hand-derived UTC (document the arithmetic in the test
  comment): one with a non-zero sub-second part (proves truncation, not rounding), one at the epoch (`0`, proves no sentinel), one
  above year 9999 (`unrepresentable`, no raise). The hex string is asserted for exact case and width.
* **Time: Date header untouched.** For `msg_time_property_vs_date_header`: the document's `headers` has the `Date` field verbatim, the
  `time.*` keys are present and different, `times == []` and `times_axis` is still the not-built marker.
* **Class gate.** `msg_non_ipm_note` and `msg_signed_class`: `message_facts` has no subject, sender, recipient or time record,
  `recipient_count` and `time.*` absent from `container_facts`, `message_class` present (D6).
* **Gap mapping (D8).** One fixture or constructed message per gap id; the detail strings are asserted exactly; order deterministic.
* **Determinism** of `container_facts` (key order and values) and `message_facts` under two `PYTHONHASHSEED` values.
* **Seeded fuzz extension.** Extend the 1b.5 fuzz (`random.Random(seed)`, the committed seed list) with operators on the recipient
  property tables and the time property entries; at least 100 more mutants; every mutant yields a document or a named refusal, every
  published string is UTF-8 encodable, and no exception of any kind escapes (a `PT_SYSTIME` entry of the wrong length must be a
  recorded fault, not an `struct.error`).
* **The `.eml` path.** `update_eml_golden.py --check` and the behavior ledger stay green and untouched.

**Mutations** (each must make a named test fail; run, restore, report the failing test names): (1) render `filetime_hex` with
`x` rather than `016x` (or upper-case it); (2) de-duplicate or re-sort the recipient records; (3) take `recipient_count` from the
declared count instead of the directory rows.

## Allow-list

The ledger's block for `turn=1b.6` (`emailextract/msgcontainer.py`, `emailextract/assemble.py`, `tests/test_msg_message_facts.py`,
`tests/test_msg_recipients.py`, `tests/test_msg_time.py`, `tests/ledger/label_ledger.json`, `docs/design/phase1b-ledgers.md`) **plus
these named additions, which you must also write into the ledger's allow-list line in the same turn**: `emailextract/mapi.py` (the
`KNOWN_TAGS` rows of D2 only), `fixtures/msg/`, `tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`,
`tests/support/mapi_table.py` (only if a table shape needs it), `tests/support/olefile_oracle.py` (only if the cross-check needs a
field), `tests/test_msg_fixtures.py`, `tests/test_mapi.py` (a pin only if D2 forces one), `tests/test_fixture_census.py`,
`tests/test_turn_declarations.py`, `docs/design/phase1-turn-declarations.md`, `docs/design/phase1b-fixtures.md`,
`docs/design/msg-architecture.md` (a short section on where the facts plug in, for 1b.7/1b.10), `docs/design/phase0-gaps.md` (only
if a registry sentence is wrong; list each edit). `assemble.py` is permitted, not expected: if the facts need no change there, do not
touch it. **`behavior_ledger.json` and `versions.py` are permissions, not duties**: the three `msg` ledger components belong to
1b.10; do **not** add them, and if the behavior ledger or a `--check` tool demands a change anyway, stop and say so.
**Not**: `emailextract/cfb.py`, `emailextract/walk.py`, `emailextract/attach.py`, `emailextract/model.py`, `emailextract/ingest.py`,
`emailextract/parse.py`, `emailextract/evals/**`, `tools/cfb_writer.py`, `tests/ledger/corpus.json`, the `.eml` golden, any `.eml`
fixture, `CLAUDE.md`.

## What must NOT be done

No `TimeEvent`; no comparison of a MAPI time with the `Date` header; no interpretation of any time value (zero, sentinel, local
versus UTC). No sender gap and no sender-versus-`From` comparison. No new gap id, no new `container_facts` key beyond
`recipient_count` and the `time.<tag>.*` pair. No edit to `EmailDocument`, `model.py` or the schema version. No recipient merged
into, or derived from, `headers`; no `headers` record gains or loses anything. No attachment, embedded or RTF work. No change to the
virtual bytes, span rows or `part_id`s (D9). No string repair: a subject with a control prefix, an invalid recipient name or an
undecodable value is recorded or faulted as it is, never replaced (no replacement character, `surrogatepass` or latin-1 fallback). No
`.msg` sidecar. No real or employer message in any fixture. No `olefile` import under `emailextract/`. Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (with `docextract_core` and `olefile` installed); note the
   interpreter and the wall time by chunk.
2. `tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1-D9 and whether you changed any, with evidence; the exact
   `message_facts` type you chose; the five fixtures with their hand-typed expectations beside what the code produced; the FILETIME
   cases; for each of the four D8 gaps the registry text against what `mapi` can know and what you emitted; the three mutation
   results; every existing test edited and why (none expected beyond census/declarations/fixture pins).
4. What 1b.7 (attachments, embedded) and 1b.10 (measurers, persistence, ledger components, the `msg.*` gap sidecar wiring) need from
   this turn: where `message_facts` and `container_gaps` plug in, which keys exist, and what is still unpersisted.

## Not this turn, but the owner should decide

* **Run probe P2** on the real corpus (`tools/msg_probe.py --probe P2`): only `0039` and `0e06` are evidenced in real mail; `3007`/
  `3008` and the sender tags are public-spec only.
* **Sender-versus-`From` comparison**, and whether a sender gap should exist at all (D4).
* **The sidecar shape for `msg.recipients`**: whether `smtp_address` joins the four fields (D5), before any sidecar uses it.
* **E4 (1b.5 carry-over)**: the HTML projection over a 40 MiB body measured 5.05x against the 5x declaration. Treated here as a known
  stress shape; the lazy `raw_bytes()` view and a re-declared budget are decisions for 1b.10 or later, not this turn.
* **A signed message's `Status`** (`UNSUPPORTED` as built, O8) and the **`IPM.Note*` boundary**: unchanged.

Stop at the turn boundary: the subject, sender, recipient and time facts are published and tested, the four observation gaps are
mapped, the `.eml` golden is untouched, the outcome note is written. Do not start 1b.7.
