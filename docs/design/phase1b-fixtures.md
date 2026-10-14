# Phase 1b fixtures (Turn 1b.0a catalogue; built from Turn 1b.2)

The `.msg` corpus, in the form `docs/design/phase1-fixtures.md` uses for Phase 1. Every fixture is synthetic
and tiny, built by the deterministic minimal CFB writer (`tools/cfb_writer.py`, Turn 1b.2) and typed by hand in
`docs/design/msg-architecture.md` and the fixtures themselves, **never** by running the reader. Raw/`writer`less
fixtures (the hostile mutants) are hand-written byte literals frozen in `fixtures/msg/SHA256SUMS`.

Rules for every fixture (matching Phase 1's):

- **Synthetic and tiny.** No real or employer mail, ever. Real `.msg` never enters the repo (`fixtures/real/`
  is git-ignored and checked empty by a listing test).
- **The writer is not the oracle.** `tools/cfb_writer.py` emits only the streams a test needs, imports no reader
  code and no GPL; a sidecar is typed from the construction table, not from the writer's output.
- **A construction table in prose** fixes each fixture's storages, streams (names and sizes), property tags and
  types, code pages, body streams, recipients and attachments, so a wrong writer default cannot make a
  self-consistent wrong fixture (operating rule 3, D11).
- Each sidecar is `labels_provenance: spec`, carries the Phase 0 facts (`container.sha256`,
  `container.size_bytes`, `headers.fields`, `part.tree`, `part.regions`, `part.gaps`, `body.preamble_epilogue`,
  `decode.chain`, `body.content_sha256`), the Phase 1 fact `document.axes` and every applicable
  `msg.*` fact (`docs/design/phase1b-facts.md`); it is pinned in the label ledger.
- **Committed fixture** = built in a fixture turn and committed with a sidecar. **Test-only hostile seed** = a
  named committed byte literal used only by a test (no sidecar), listed at the end.

## Family D — container, layout and hostile CFB (Turns 1b.2 / 1b.3)

| fixture | committed | what it exercises (one thing) | facts / gap ids | turn |
|---|---|---|---|---|
| `msg_headers_only` | yes | a minimal `.msg` with `0x007D` and **no** body stream | `msg.container_layout`, `msg.sector_accounting`, `msg.message_class`, `msg.codepage_ladder` | 1b.2/1b.3 |
| `msg_headers_html` | yes | `0x007D` + a `0x1013` HTML body (the 10-of-11 real shape) | `msg.body_streams`; `body.text`/`body.html_spans` | 1b.2/1b.5 |
| `msg_v4_sectors` | yes | a **v4** file: 4096-byte sectors, `cfb_version=4` | `msg.container_layout` (`sector_size=4096`) | 1b.2/1b.3 |
| `msg_mini_cutoff_boundary` | yes | streams at 4095 / 4096 / 4097 bytes (the miniFAT cutoff) | `msg.container_layout`, `msg.sector_accounting` | 1b.2/1b.3 |
| `msg_difat_extended` | yes | a file large enough to need the **extended DIFAT** chain (read through) | gap `msg.cfb_difat_extended` | 1b.3 |
| `msg_fat_cycle` | yes | a cyclic FAT chain on one stream (hostile) | `msg.stream_faults`; `TRUNCATED`/`declared_length_mismatch` | 1b.3 |
| `msg_directory_loop` | yes | a directory link that points into a cycle (hostile) | NamedError `cfb_directory_loop` | 1b.3 |
| `msg_truncated_stream` | yes | a stream shorter than its declared size (hostile) | `msg.stream_faults`; `TRUNCATED`/`stream_ended_early` | 1b.3 |
| `msg_outlook_layout_handbuilt` | yes | **one** fixture typed from Outlook's observed layout (B1-B4), not the writer's defaults | all `msg.*` layout facts | 1b.2 |
| `msg_unknown_tags` | yes | property entries whose tags are not modelled (hex only) | gap `msg.property_tag_unknown` | 1b.4 |
| `msg_named_properties` | yes | `__nameid_version1.0` present; a named property is not resolved | gap `msg.named_property_unresolved` | 1b.4 |

**Construction table: `msg_outlook_layout_handbuilt` (typed from `email-spike.md` B1-B4, never a writer
default).** Root child `Root Entry`; top-level children `__properties_version1.0` (header **32 bytes**),
`__nameid_version1.0` (three binary streams `__substg1.0_00020102` 160 B, `00030102` 440 B, `00040102` 3090 B),
`__substg1.0_007D001F` (the transport-header stream, a `001F` UTF-16 stream), `__substg1.0_10130102` (an HTML
body, `0102` PT_BINARY), one `__recip_version1.0_#00000000` and one `__attach_version1.0_#00000000`. Entry
encoding `u32 = (tag << 16) | type`; the top-level header's counts at `@16`/`@20` equal the directory-derived
recipient/attachment counts (1/1); `(size - header)` is a multiple of 16. Data streams named
`__substg1.0_%04X%04X`. The one attachment storage holds a by-value file (method `1`, `0x3701:0102`); a
filename via `0x3707:001F`. Code-page properties `0x3FDE` (`internet_codepage`) and `0x3FFD`
(`message_codepage`) as **fixed entries in `__properties_version1.0`, not streams** (B4). Sector size 512,
mini-sector 64, mini-cutoff 4096. **This fixture is documented as hand-built to the observed structure, not
real-Outlook provenance.**

Its turn is recorded here as **1b.2** after a three-way disagreement the reviewer resolved (D1): the build spec's
1b.9 row says "Outlook layout", this table said 1b.3, and the binding `declaration turn=1b.2` block names
`test_the_outlook_layout_fixture_is_typed_from_b1_b4` in 1b.2. The declaration wins, so it is built here.

**Construction tables: the other four Turn 1b.2 fixtures** (hand-typed before any writer output; the writer's
`tools/cfb_writer.py` lays sectors out header, FAT, directory, mini-FAT, mini stream, FAT streams).

- `msg_headers_only`: `Root Entry` with `__properties_version1.0` (64 B: the **32-byte** message-property
  header -- recipient/attachment counts `0/0` at `@16`/`@20` -- plus two 16-byte code-page entries) and
  `__substg1.0_007D001F` (518 B of UTF-16LE transport headers). Both streams are **strictly below** the
  4096-byte cutoff, so both live in the mini stream. Version 3, 512-byte sectors, 64-byte mini sectors:
  FAT 1 sector, directory 1, mini-FAT 1, mini stream 2; file length **3072** (six 512-byte sectors).
- `msg_headers_html`: the same tree plus `__substg1.0_10130102` (160 B, a `0102` PT_BINARY HTML body -- the
  10-of-11 real shape). Still all-mini; file length **3072**.
- `msg_v4_sectors`: the `msg_headers_html` tree as a **version 4** file -- 4096-byte sectors, a 4096-byte
  header sector (the 512-byte header zero-padded), the header's directory-sector count set for v4. File length
  **20480** (five 4096-byte sectors: header, FAT, directory, mini-FAT and mini stream one sector each).
- `msg_mini_cutoff_boundary`: three streams, `boundary_4095` (4095 B), `boundary_4096` (4096 B) and
  `boundary_4097` (4097 B). 4095 is **strictly below** the cutoff so it is a mini stream; 4096 and 4097 are at
  or above it, so they come from the FAT. Version 3, 512-byte sectors, mini-cutoff 4096: the two FAT streams
  are laid out in an explicitly requested order (`boundary_4097` first, at sectors 11-19, then `boundary_4096`
  at 20-27) so the chain lists are pinned; file length **14848** (twenty-nine 512-byte sectors).

**Hostile mutants (`msg_fat_cycle`, `msg_directory_loop`, `msg_truncated_stream`)** are the three of the
debate's six mutants that are *fixtures* (a committed byte literal); the other three (size-lie 2\*\*40, size
0xFFFFFFFF, root self-reference) are test-only hostile seeds (below). `olefile` is **not** the oracle for any
of them (it returns a full stream for a cycle and clamps a size lie; `phase1b-debate.md:325-344`); the
independence is the falsifiable stream-fault classification, the sector-tiling sum and the seeded fuzz.

## Family E — message class, subject, recipients, time and code pages (Turns 1b.4 / 1b.6)

| fixture | committed | what it exercises (one thing) | facts / gap ids | turn |
|---|---|---|---|---|
| `msg_non_ipm_note` | yes | message class `IPM.Appointment` (the class gate) | `msg.message_class`; `UNSUPPORTED`; gap `msg.class_not_ipm_note` | 1b.4 |
| `msg_signed_class` | yes | class `IPM.Note.SMIME.MultipartSigned` (O8: class recorded, no body) | `msg.message_class`; `UNSUPPORTED`/`PARSED` per O8 | 1b.4 |
| `msg_no_transport_headers` | yes | no `0x007D` stream | `headers=[]`; gap `msg.transport_headers_absent` | 1b.5 |
| `msg_transport_headers_utf8_bom` | yes | `0x007D` whose text begins with a UTF-8 BOM | `headers.*` (the BOM handled by the header scan) | 1b.5 |
| `msg_transport_headers_lf_only` | yes | `0x007D` with LF-only line endings | `headers.*`; `part.regions` | 1b.5 |
| `msg_codepage_disagree` | yes | internet cp 28591 against message cp 1252 (they disagree) | `msg.codepage_ladder` | 1b.4 |
| `msg_recipients_display_only` | yes | a recipient row with a display name and no SMTP address | `msg.recipients` (`smtp`/display-only) | 1b.6 |
| `msg_recipients_ex_no_smtp` | yes | a recipient with the Exchange address type and no SMTP form | `msg.recipients` (`ex`) | 1b.6 |
| `msg_recipients_bcc_duplicates` | yes | a `bcc` row and a duplicated recipient row | `msg.recipients` | 1b.6 |
| `msg_time_property_vs_date_header` | yes | a `time.*` property that disagrees with the `Date` header | `msg.time_facts`; `headers.date` (kept distinct) | 1b.6 |
| `msg_property_vs_header_conflict` | yes | the `0x007D` transport header and a MAPI property disagree (the transport header is canonical) | gap `headers.mapi_header_property_disagree` | 1b.5 |
| `msg_unicode_subject` | yes | a `001F` subject with non-ASCII (incl. a surrogate pair in `msg_non_bmp_text`) | `msg.message_class`; subject fact | 1b.6 |

## Family F — body streams (Turns 1b.5 / 1b.8)

| fixture | committed | what it exercises (one thing) | facts / gap ids | turn |
|---|---|---|---|---|
| `msg_html_only_no_plain` | yes | `0x1013` only (the 10-of-11 real shape) | `msg.body_streams` (`html`) | 1b.5 |
| `msg_plain_only` | yes | `0x1000` only | `msg.body_streams` (`plain`) | 1b.5 |
| `msg_plain_and_html` | yes | `0x1000` + `0x1013` (selection picks HTML) | `msg.body_streams`; `body.selection` | 1b.5 |
| `msg_rtf_compressed_body` | yes | `0x1000` + `0x1009` (`LZFu`, `\fromtext`), no HTML | `msg.body_streams`; gap `msg.rtf_to_text_unsupported` | 1b.8 |
| `msg_rtf_only` | yes | `0x1009` only (no plain, no HTML) | `msg.body_streams` (`rtf`); gap `msg.rtf_to_text_unsupported` | 1b.8 |
| `msg_rtf_bad_crc` | yes | `LZFu` with a wrong CRC (hostile) | `TRUNCATED`/`stream_ended_early`; no body view | 1b.8 |
| `msg_zero_length_body` | yes | a `0x1000` stream of length 0 (present-but-empty, not absent) | `msg.body_streams` (`plain`); `body.plain_effectively_empty` | 1b.5 |
| `msg_html_meta_charset_contradicts` | yes | HTML whose `<meta charset>` contradicts the internet code page | `msg.codepage_ladder`; `body.text` | 1b.5 |

## Family G — attachments and embedded messages (Turn 1b.7)

| fixture | committed | what it exercises (one thing) | facts / gap ids | turn |
|---|---|---|---|---|
| `msg_embedded_message` | yes | a `0x3701:000D` embedded-message storage (depth 1) | `msg.embedded_summary`, `msg.storage_tree_sha256` | 1b.7 |
| `msg_embedded_depth_two` | yes | an embedded message that itself embeds one (beyond depth 1) | gap `msg.embedded_depth_cap` | 1b.7 |
| `msg_attachment_with_cid` | yes | a by-value attachment carrying a `0x3712` Content-ID | `msg.attachments`; `attach.cid_*` | 1b.7 |
| `msg_attachment_hidden` | yes | an attachment with the hidden and inline flags | `msg.attachments`; `attach.decorative` | 1b.7 |
| `msg_attachment_ole` | yes | method 6 (OLE object), recorded without parsing | `msg.attachments` | 1b.7 |
| `msg_attachment_by_reference` | yes | methods 2/3/4 (referenced; no path followed) | `msg.attachments`; gap `msg.attachment_method_unsupported` | 1b.7 |
| `msg_attachment_hostile_name` | yes | a filename with path separators and NUL bytes (raw + decoded kept) | `msg.attachments` (never a path) | 1b.7 |
| `msg_attachment_zero_size` | yes | a zero-length by-value attachment | `msg.attachments` | 1b.7 |
| `msg_attachments_4095_4096_4097` | yes | three attachments at the mini-cutoff sizes | `msg.attachments` | 1b.7 |
| `msg_duplicate_filenames` | yes | two attachments with the same filename | `msg.attachments` | 1b.7 |

## Family H — encodings and text (Turn 1b.9)

| fixture | committed | what it exercises (one thing) | facts / gap ids | turn |
|---|---|---|---|---|
| `msg_string8_1252` | yes | a `001E` string8 decoded through internet cp 1252 | `msg.codepage_ladder` | 1b.9 |
| `msg_string8_ascii20127` | yes | a `001E` string8 that is all-ASCII (cp 20127) | `msg.codepage_ladder` (`ascii`) | 1b.9 |
| `msg_string8_utf8_65001` | yes | a `001E` string8 decoded strict UTF-8 (cp 65001) | `msg.codepage_ladder` (`utf8_strict`) | 1b.9 |
| `msg_string8_body` | yes | a `0x1000` plain **body** as `001E` (8-bit), not `001F` | `msg.body_streams`; `msg.codepage_ladder` | 1b.9 |
| `msg_non_bmp_text` | yes | a `001F` string with a non-BMP character (a UTF-16 surrogate pair) | `msg.message_class`; subject fact | 1b.9 |
| `msg_multivalued_strings` | yes | a multi-valued string property (every value kept) | subject/`msg.*` facts | 1b.9 |

## Family I — the cross-container pair (Turn 1b.9)

| fixture | committed | what it exercises (one thing) | facts / gap ids | turn |
|---|---|---|---|---|
| `pair_gmail_reply.eml` | yes | one synthetic message as RFC 822 (multipart/alternative, plain + HTML) | `container_hash`, `body_digest` | 1b.9 |
| `pair_gmail_reply.msg` | yes | **the same message** as `.msg` (HTML kept, plain dropped) | `container_hash` differs, `body_digest` equal (HTML view) | 1b.9 |

**Construction table: the pair.** The `.eml` is a `multipart/alternative` with a `text/plain` and a
`text/html` part; the `.msg` is an `IPM.Note` with `0x007D` (the original headers) and a `0x1013` HTML body
whose bytes are the **same HTML** (no plain stream). By D14 the two have **different** `container_hash` (the
file bytes differ) and an **equal** `body_digest` (the selected HTML view's code points as UTF-8), and the
`.msg` surfaces as **no plain view**. This is the one fixture that proves the D14 cross-container relation.

## Test-only hostile seeds (committed seeds, not fixtures)

Named committed byte literals (in `fixtures/msg/seeds/`, frozen in `SHA256SUMS`), used only by tests; no
sidecar, no ledger label. The Phase 1b gap gate (Turn 1b.10) gives each `msg.*` id a mutation case from one of
these.

- `seed_lone_surrogate`: a `001F` stream ending on a lone UTF-16 surrogate (strict `utf-16-le` raises; the
  bounded decoder must **record**, not raise).
- `seed_odd_length_utf16`: a `001F` stream with an odd byte length (the same rule).
- `seed_recipient_count_mismatch`: the top-level header's recipient count disagrees with the real recipient
  rows (the reader trusts the directory, records the disagreement).
- `seed_attachment_no_data`: an attachment storage with no data stream.
- `seed_size_lie_2pow40`: a stream whose declared size is `2**40` (olefile clamps it to 0; the reader must not).
- `seed_size_lie_ffffffff`: a declared size of `0xFFFFFFFF`.
- `seed_root_self_reference`: the root's child pointing to itself.

**Turn 1b.3 builds `seed_size_lie_2pow40`, `seed_size_lie_ffffffff` and `seed_root_self_reference` inside
`tests/test_cfb.py::_seeds`** (from a fixture, by patching one field at a `cfb_raw.header` offset) rather than
committing them: the reader's fault contract is what they exercise, and a built seed cannot drift from its
base. They are the same named seeds this catalogue lists; the committed `fixtures/msg/seeds/` files, and the
other four seeds, are the later turns' (1b.7).

## Census: the fixture set is a superset of the design's Phase 1b list

The design's Phase 1b paragraph (`email-extraction-design.md`, "Phasing") names ten fixtures:
`msg_headers_only`, `msg_headers_html`, `msg_html_only_no_plain`, `msg_rtf_compressed_body`,
`msg_embedded_message`, `msg_attachment_with_cid`, `msg_non_ipm_note`, `msg_truncated_stream`,
`msg_outlook_layout_handbuilt` and the cross-container pair. All ten are rows above; the union of the seven
families is therefore a **superset** of the design's list. A census test (`tests/test_fixture_census.py`,
extended in Turn 1b.2) parses the backticked names out of the design's Phase 1b "Fixtures:" line and asserts a
catalogue row exists for each and, once built, a committed fixture with that stem exists.

## Counts, and the coverage floors

| family | committed fixtures | turn |
|---|---|---|
| D container / layout / hostile | 11 | 1b.2-1b.3 |
| E class / recipients / time / code pages | 12 | 1b.4/1b.6 |
| F body streams | 8 | 1b.5/1b.8 |
| G attachments / embedded | 10 | 1b.7 |
| H encodings / text | 6 | 1b.9 |
| I cross-container pair | 1 pair (2 files) | 1b.9 |
| **total committed `.msg` sidecars** | **48** `.msg` + **1** `.eml` | |
| test-only hostile seeds | 7 | 1b.3/1b.7 |

Every floor in `docs/design/phase1b-facts.md` is met with room: the tightest are `msg.container_layout` and
`msg.sector_accounting` (floor 45, on all 47 `.msg` fixtures), `msg.message_class` (floor 40), and
`msg.embedded_summary` / `msg.storage_tree_sha256` / `msg.stream_faults` (floor 2 each, carried by the named
fixtures with room to spare). The floor for each fact and the observed count are checked by
`tests/test_facts_coverage.py` (Turn 1b.10); a fact below its floor fails, and a fact that moves its phase
fails against the pinned ledger.

## Probe items as Phase 1b inputs (P1-P6)

Not fixtures; the owner's structure-only probes (`docs/design/phase1b-probes.md`). They gate nothing in this
catalogue's construction (the fixtures are hand-built from B1-B4), but they decide weight: P1 the signed-mail
layout (O8), P2 the time tags (`msg_time_property_vs_date_header`), P3 whether the extended DIFAT ever occurs
(`msg_difat_extended`), P4 the attachment/recipient tag sets (`msg_attachments`, `msg.recipients`), P5 8-bit
prevalence (`msg_string8_*`), P6 vendor HTML classes (the HTML fixtures and the quote rules).
