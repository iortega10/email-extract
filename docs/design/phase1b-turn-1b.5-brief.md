# Turn 1b.5: `msgcontainer.py` -- the projection over real CFB, headers from `0x007D`, one HTML body end to end

Status: brief for one build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `d419c88` (Turn 1b.4
committed: `mapi.py`, five more fixtures). Run hearth in `C:\Users\ivan_\App_repos\email-extract`, fresh session.
**Do not commit.**

This is the turn where a `.msg` first becomes an `EmailDocument`. It is the heaviest of Phase 1b, so work **in the order below and
run only the files you are touching** until step 7. Run the full suite once on the primary interpreter at step 7, then on 3.11,
then the mutations. If the turn is running long, the clean boundary is the end of **step 4** (container, wiring, facts, headers): stop
there and report rather than rushing bodies; the owner will schedule the rest.

## What this turn is

`emailextract/msgcontainer.py` builds the **A'' projection** (`phase1b-build-spec.md`, "The architecture decision") over an opened
`CfbFile` and `mapi.read_message`: a deterministic **virtual RFC 822 byte string** that the one existing walker reads, a **span
table** (`SpanRow`, already defined in `container.py` by 1b.1) saying which source stream every region came from, and the fixed
`container_facts` set. It then wires `parse()` and `ingest` so a `.msg` is opened instead of refused. The eight provenance
points, the `value_codec` seam, `FakeMsgContainer` and the schema bump (5 -> 6) are **already built** (Turn 1b.1); this turn is
their first real producer. It builds headers from the `0x007D` transport-header stream and the **plain and HTML bodies**.
It does **not** build recipients, subject/sender/time facts (1b.6), attachments, embedded messages or `msg.attachments` (1b.7), or
RTF (1b.8).

Read first: `phase1b-build-spec.md` (rules 2 and 3, "The architecture decision", D13/D14 lines, "Further decisions" 4-9, O9),
`phase1b-contract.md` (**sections 2, 3, 4, 5, 6, 7, 8, 9, 11, 13**: they are the contract; read the `SpanRow` rules and the "existing
tests that must change" table in full), `emailextract/container.py` (`SpanRow`, `PersistedSpanRow`, `CharsetOrigin`,
`stream_ref_of`, `span_lookup`), `tests/support/fake_msg_container.py` (**the shape your container must publish**: its virtual
framing, its rows, `charset_sources`, `cap_observations`, `SECTOR_ACCOUNTING`), `tests/test_provenance_points.py`,
`emailextract/assemble.py` (`_compose`, `_header_fields`, `_part_records`, `_failed_document`), `emailextract/parse.py`
(`_open_projected`, `open_cfb`), `emailextract/ingest.py` (`_row_for`), `emailextract/mapi.py` and `cfb.py` (read-only APIs; **do not
edit them**: a defect there is reported), `phase1b-ledgers.md` (the `declaration turn=1b.5` block and the 1b.1/1b.3/1b.4 outcome
notes, especially each "what the next turn needs" section) and `msg-architecture.md` (E4 to E8).

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. The projection's layout, and why synthetic structure goes first.** The virtual message is, in this order:
1. the projection's own **structural header lines** (`MIME-Version`, `Content-Type` with `charset`, `Content-Transfer-Encoding`
   as the body needs; and, for plain + HTML together, `multipart/alternative` with a synthetic boundary), each a `SYNTHETIC` row
   labelled `synthetic:<role>:<ordinal>`;
2. the **`0x007D` text**, one `REENCODED` row over the whole stream (UTF-16LE source bytes; the UTF-8 re-encoding is what the
   scanner reads), trailing NUL stripped, its own line endings and any BOM handling untouched except as the header scan already
   treats them;
3. one synthetic blank line, then the body leaves (D4/D5), the multipart delimiters being `SYNTHETIC` rows.
**Why first.** The transport headers' `Content-Type` describes the *original* MIME message, not the `.msg` (build spec "Measured
facts": the `.eml` was `multipart/alternative`, the `.msg` kept only the HTML); constraint C1 says structure comes from the `.msg`'s
own streams. The reviewer measured, before writing this, that on duplicate `Content-Type` lines the walker takes **the first**
(a probe on `EmlContainer` bytes returned `multipart/alternative` from the first of two lines). So the projection's structure
lines go first and win, and the original's structural lines stay verbatim, afterwards, as ordinary header fields (claims about the
original). **Re-measure** that first-wins rule for `Content-Transfer-Encoding` and `MIME-Version` and for every consumer that reads
a header by name (`attach.py`, `selection.py`, `text.py` read `raw_value`), and report what you find; if any consumer reads the
*last* or *all* occurrences, **stop and report**: the layout needs another answer, which is the owner's. If the walker needs an
edit inside tiling or ordering to make this work, **stop**: that is the A'' re-open trigger (build spec, point 5).

**D2. `headers` is evidence only.** The `HeaderField` records are the fields of the `0x007D` text, in stream order, each with its
`ContainerStreamRef` (`REENCODED`, source offsets in the UTF-16 stream). The synthetic structural lines are **scaffolding, not
evidence**: they must not appear in `headers` (C6: a consumer can tell scaffolding from evidence), so a `.msg` with no `0x007D` has
`headers == []` (O6, no header synthesis) even though its virtual bytes carry structural lines. Check how 1b.1's point 1 and
`assemble._header_fields` treat a field that has **no span row** (the fake's `X-Pad` and `Content-Type` have none) and make the
smallest `cfb_msg`-gated edit that excludes synthetic lines, with the default branch the current expression **verbatim**. The
`.eml` golden stays byte-identical; the walker's per-part `content_type` etc. still come from the structural lines.

**D3. No `0x007D`.** `headers=[]`; the header-field, date and address walkers do not run over an empty block; the only gap is
`msg.transport_headers_absent`, once at document level (so `headers.no_date` and `headers.no_from` are **not** emitted as noise).
Subject, sender, recipients and times are 1b.6's facts. This is a registered gap (registry text in `phase0-gaps.md`); read it.

**D4. HTML body (`0x1013`, `PT_BINARY`): pass-through.** The leaf bytes are the stream's own bytes, unchanged, with CTE `binary` and
`charset=<label>`: a `STREAM` row. `size_bytes`/`sha256` are the stream's (contract section 5). The charset label and
`encoding_source` come from the **mapi ladder run on the HTML bytes** (internet code page, then message code page, then ascii,
strict UTF-8, windows-1252), the decoded text being discarded: the container only needs the rung and the label. Publish the rung
through the `charset_sources` hook (`CharsetOrigin`, 1b.1 point 5). Code page -> label: `1252 -> windows-1252`,
`20127 -> us-ascii`, `28591 -> iso-8859-1`, `65001 -> utf-8`; for rungs 3-5 the label is `us-ascii`, `utf-8`, `windows-1252`.
`msg_html_meta_charset_contradicts`: the container's declared charset is the evidence the text stage uses; the HTML's own
`<meta charset>` is left to whatever Phase 1's text stage already does with a declared charset. Do not change that stage.

**D5. Plain body (`0x1000`).** `001F` is re-encoded to UTF-8 (`REENCODED` row, `decoded_char_offset`/`decoded_char_len` recorded,
`charset=utf-8`, CTE `8bit`); `001E` goes through the ladder and then to UTF-8 the same way. A present-but-empty `0x1000` is
**present** (`body_streams` includes `plain`; `msg_zero_length_body`). A body whose bytes cannot be decoded (a `None` value from
`mapi`, with a fault) is **not** projected as text: record the fault, produce no body view for it, and never a replacement
string. Both bodies present -> `multipart/alternative`, plain first then HTML (RFC 2046 order, the selection stage prefers HTML:
declared test). The synthetic boundary must not occur in any body: choose it **deterministically** (a counter until absent), so
the same bytes always give the same boundary. `0x1009` (RTF) is **listed** in `body_streams` and **not projected** (1b.8).

**D6. `container_facts`, exactly this turn's set.** `adapter`, `cfb_version`, `sector_size`, `mini_sector_size`, `mini_cutoff`,
`sector_count`, `directory_entries`, `message_class`, `internet_codepage`, `message_codepage`, `body_streams`,
`has_transport_headers`, `named_property_count`, `projection`, and the eight `sectors.*` counts (contract section 6; `absent` for
a code page that is not there). **Not yet**: `recipient_count` (1b.6), `attachment_count` (1b.7), `time.*` (1b.6): the key list
grows additively in those turns, in the same commit as the data. `container_hash` is the sha256 of the **CFB file bytes**; the
document's `raw_bytes()` for the walker is the virtual message (build spec D14).

**D7. Outcomes and refusals (contract sections 2-3), through `parse()` and the assembler.** `parse()` opens CFB by default:
`cfb_header_unsupported` and `cfb_directory_loop` and `not_a_message` (CFB magic without `__properties_version1.0`; `.doc`, `.xls`,
`.msi`) are `NamedError`s; delete `cfb_msg_unsupported` from `NAMED_ERROR_REASONS` and every site that produced it. A non-`IPM.Note`
class is a **document** with `Status.UNSUPPORTED` (takes no reason), the class verbatim in `container_facts`, and
`msg.class_not_ipm_note`; nothing past the class is opened (the 1b.4 gate already stops). A `signed_or_encrypted` class follows
O8: class recorded, **no body**, never verified; its `Status` (`UNSUPPORTED` versus `PARSED`) is the owner's open question, so
use `UNSUPPORTED` as the conservative reading **and say so in the outcome note**. A CFB cap hit is a `SKIPPED` document with the
matching reason (`sector_count_cap` etc.) and a `CapRecord` carrying the caller's value and the **real** observed count; the
container accepts `cfb_limits` (default `DEFAULT_CFB_LIMITS`) so a test can force it with tiny numbers. A per-stream chain fault is a
`TRUNCATED` document (`declared_length_mismatch` for a cycle, `stream_ended_early` otherwise) with `msg.stream_truncated`. **Nothing
raises**: every committed hostile fixture (`msg_fat_cycle`, `msg_directory_loop`, `msg_truncated_stream`) goes through
`assemble(MsgContainer)` / `ingest` to a document or a named refusal.

**D8. The disagreement gap, narrowly.** `headers.mapi_header_property_disagree`: in this turn compare **only** `0x0037` (subject)
against the `0x007D` `Subject:` field's decoded text; if both exist and differ, the transport header is canonical, the document
carries the gap, and the property text is kept where the registry entry says. Read the registry entry and
`phase1b-facts.md`: if it demands a *fact* or a `container_facts` key that does not exist until 1b.6, **do not invent one**; record
the property text in the gap's detail, and report the mismatch. Sender and other properties are 1b.6.

**D9. Fix `msg_outlook_layout_handbuilt` now (an owner-requested correction).** Turn 1b.4 found that this 1b.2 fixture names its
recipient properties per its own typing (`3001` as the type, `3002` as the display name, `3003` as the address type) and carries no
`0x001A`, so the one fixture meant to follow Outlook's observed layout stops at `class_absent` and the reader reads its recipient as
`kind=unknown`. B3 shows `0C15:0003` in real messages. Correct it **in one move**: the recipient table uses `0C15` (type),
`3001` (display name), `3002` (address type), `3003` (email address); the top-level table gains `0x001A` (`IPM.Note`); update the
construction table in `tests/support/msg_construction.py` **first, typed from B1-B4 and [MS-OXPROPS], before regenerating**; then the
generator, the `SHA256SUMS` line, the hex pins and `tests/test_msg_fixtures.py`. The brief's usual "no edit to an existing fixture"
is **lifted for this one fixture only**. Then change `tests/test_mapi.py::
test_the_handbuilt_outlook_layout_matches_the_b1_b4_values` to go through `read_message` (remove the building-blocks workaround) and
assert the recipient row's kind and address type. The olefile cross-check and every other test that reads it must stay green; list each
edit.

**D10. Memory (build spec O9): re-run E4 at 5x on the real projection.** A synthetic 40 MiB `0x1013` stream through
`MsgContainer` + `walk` + `assemble`: peak RSS delta must be at most **5x** the stream (the re-declared budget). A pass-through HTML
leaf should not be copied more than the virtual string requires. If it is under 5x, `attach.py` stays untouched; if over, **stop and
report** the number and which copy dominates (the lazy `raw_bytes()` view is a protocol change the owner decides).

## Order of work

1. **D9** (the fixture correction) and its tests; the other suites stay green.
2. `msgcontainer.py`: `MsgContainer(data, *, cfb_limits=...)` implementing the `Container` Protocol plus `span_provenance`,
   `charset_sources`, `cap_observations`; `container_hash`, `container_facts`, the virtual bytes and the rows, for **headers only**
   (no body yet). Tests: `test_msgcontainer.py` (5 declared).
3. Wiring: `parse.py` (default opener, `NAMED_ERROR_REASONS`), `ingest.py` (`_row_for` builds a `MsgContainer` for `cfb_msg`),
   `assemble.py`/`walk.py` only if D2 forces a gated edit, and the existing tests that contract section 11 lists for the
   `cfb_msg_unsupported` deletion (`tests/test_parse_entry.py`, `tests/test_ingest.py`; verify each by opening it, do not trust the
   line numbers).
4. Headers: `tests/test_msg_headers.py` (4 declared): `0x007D` in stream order, the UTF-8 `value_codec` carrying the real text, no
   `0x007D` gives `headers == []`, the transport header canonical with the property kept.
5. Bodies: D4/D5, selection, `tests/test_msg_body.py` (4 declared). Add the body fixtures the catalogue assigns to this turn
   (`msg_html_only_no_plain`, `msg_plain_only`, `msg_plain_and_html`, `msg_zero_length_body`, `msg_html_meta_charset_contradicts`,
   `msg_no_transport_headers`, `msg_transport_headers_utf8_bom`, `msg_transport_headers_lf_only`, `msg_property_vs_header_conflict`),
   each with a construction table typed before the code runs. **No `.msg` sidecars** (`evals/labels.py` still accepts only `.eml`).
6. Sector accounting end to end, the hostile fixtures through the container, the E4 re-run (D10), the two C2 tests.
7. Full suites, `--check` tools, the three mutations, the outcome note.

## Tests

The 13 declared tests of the `declaration turn=1b.5` block, **names exactly as declared** (see `phase1b-ledgers.md`), plus these
extras, declared in the same block:
* **C2, both directions** (build spec "Constraints"): build the same message with two framing lengths (a longer synthetic region,
  the fake's `framing` idea) and require identical `part_id`s, `PartRecord`s and citations; and mutate the `.eml` path and require its
  `part_id`s byte-identical.
* **C5**: the same message as `.eml` and `.msg` gives one `EmailDocument` shape differing exactly where D14 says (container kind,
  hash, `container_facts`, `stream_ref`s, `encoding_source`), compared field by field against a hand-typed list of the allowed
  differences.
* **The span table and the virtual bytes agree** with the source: every `STREAM`/`REENCODED` row's `source_sha256` equals the sha256
  of the named stream's real bytes, read through `cfb.read_stream` and **not** through `msgcontainer`; the persisted form
  (`PersistedSpanRow`) is recomputed and equal; no `virtual_*` value appears in any record, `part_id` or stored artifact.
* **Hostile through the container** (D7): the three hostile fixtures and a tiny-`CfbLimits` cap hit each yield the specified
  `Status`/reason/`CapRecord` or named refusal; none raises.
* **`msg_non_ipm_note` and `msg_signed_class` through the container**: `UNSUPPORTED`, the class verbatim, no body, no recipient decode.
* **Determinism** under two `PYTHONHASHSEED` values and on both interpreters (the virtual bytes' sha256 and the span rows).
* **A seeded fuzz of the projection** (`random.Random(seed)`, a committed seed list, at least 200 mutants over at least three
  fixtures, operators on the `0x007D`, body and property streams): every mutant yields a document or a named refusal; text in every
  record is UTF-8 encodable; no exception of any kind.

**Mutations** (each must make a named test fail; run them, restore, report the failing test names): (1) put the synthetic structural
header lines **after** the `0x007D` text; (2) make a synthetic line appear in `headers`; (3) let the HTML leaf claim `exact`
precision (or carry a virtual offset into a `part_id`).

## Allow-list

The ledger's block for `turn=1b.5` (`emailextract/msgcontainer.py`, `emailextract/attach.py`, `emailextract/parse.py`,
`emailextract/assemble.py`, `emailextract/walk.py`, `fixtures/msg/`, `tests/test_msgcontainer.py`, `tests/test_msg_headers.py`,
`tests/test_msg_body.py`, `tests/ledger/label_ledger.json`, `tests/ledger/behavior_ledger.json`, `docs/design/phase1b-ledgers.md`)
**plus these named additions, which you must also write into the ledger's allow-list line in the same turn**:
`emailextract/ingest.py`, `tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`, `tests/support/mapi_table.py`,
`tests/support/olefile_oracle.py` (only if a fixture shape needs it), `tests/test_msg_fixtures.py`, `tests/test_mapi.py` (the D9 test
only), `tests/test_parse_entry.py`, `tests/test_ingest.py`, `tests/test_phase1_scope.py` (`EXPECTED_LIBRARY` and the import/name
lists; name each line), `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`, `docs/design/phase1-turn-declarations.md`,
`docs/design/phase1b-fixtures.md`, `docs/design/msg-architecture.md` (the Q3 answer below), `docs/design/phase0-gaps.md` (only if a
registry sentence is wrong, as 1b.4's `msg_codepage_disagree` one is: list each edit). **`behavior_ledger.json` and `versions.py` are
permissions, not duties**: the three `msg` ledger components (`cfb`, `msg_reader`, `msg_projection`) and their version constants
belong to Turn 1b.10 (build-spec turn table); do **not** add them here, and if the behavior ledger or a `--check` tool demands a
change anyway, stop and say so. **Not**: `emailextract/cfb.py`, `emailextract/mapi.py` (a defect there is reported, not fixed),
`tools/cfb_writer.py`, `emailextract/evals/**`, `tests/ledger/corpus.json`, the `.eml` golden, any `.eml` fixture, `CLAUDE.md`.

## What must NOT be done

No recipients, subject/sender/time facts, attachments, embedded messages or RTF. No edit inside `walk.py`'s tiling or ordering (the
A'' re-open trigger: stop and report). No measured `.eml` value moves: `update_eml_golden.py --check`, the behavior ledger and every
Phase 1 gate stay green and untouched; `EMAIL_PARSER_VERSION` does not move. No virtual offset in any record, `part_id`, cap record or
stored artifact. No header synthesis for a `.msg` without `0x007D`. No `olefile` import under `emailextract/`. No new
`container_facts` key beyond D6. No replacement character, `surrogatepass` or latin-1 fallback anywhere. No `.msg` sidecar. No real or
employer message in any fixture. Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (with `docextract_core` and `olefile` installed); note the
   interpreter used. A clean `.eml` golden.
2. `python tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1-D10 and whether you changed any, with evidence; the first-wins
   re-measurement for each structural header and each consumer (D1); how D2's edit is gated and why the `.eml` path is untouched; the
   `Status` chosen for the signed class (D7); what D8's registry entry demanded and what you did; the E4 number against 5x (D10);
   the three mutation results; every existing test edited and why; the answer to **Q3** (contract section 13: whether a synthetic
   leaf carries a `stream_ref` on its `PartRecord`, or `None` with `synthetic` only in the span table), stated also in
   `msg-architecture.md`.
4. What 1b.6 and 1b.7 need: where a message-level fact or an attachment row plugs into the container, which `container_facts` keys
   they add, and what `mapi.read_message` returns that the container does not yet use.

## Not this turn, but the owner should decide before 1b.6

* **A signed message's `Status`** (D7), now that the body is not opened: `UNSUPPORTED` or `PARSED`.
* **Aggregating `msg.property_tag_unknown`** (1b.4's open point): one gap record per message, per table, or per pair.
* **`class_absent`**: `mapi` returns it; the container maps it (suggested: a `PARSED` document with a gap, not `not_a_message`); say
  what you did.

Stop at the turn boundary: headers and one HTML body work end to end, the golden is green, the sector sum closes on every fixture
and the outcome note is written. Do not start 1b.6.
