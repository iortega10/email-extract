# Turn 1b.9: the cross-container pair, the Outlook-layout proof, and the encodings

Status: brief for one build turn. Author: reviewer session, 2026-10-14. Builder: hearth. Builds on `d3d20aa` (Turn 1b.8 committed:
the RTF minimum, with the prebuf and CRC corrected against a real vector). Run hearth in `C:\Users\ivan_\App_repos\email-extract`,
fresh session. **Do not commit.**

**Pace this turn.** It is mostly fixtures and tests over code that already exists, so most of the risk is in the expectations, not the
implementation. While iterating run only the files you touch; run the full suite once at the end on the primary interpreter, once on
3.11, then the mutations.

## What this turn is

Three proofs, no new architecture:

1. **The cross-container pair (D14, C5).** One synthetic message built twice, as RFC 822 and as `.msg`, proves the relation the design
   promises: a **different `container_hash`**, an **equal `content_fingerprint.body_digest`** when both carry the same HTML, one document
   shape differing only where D14 says, and "never dedupe on raw hash, never pretend to".
2. **The Outlook-layout proof.** `msg_outlook_layout_handbuilt` (built in 1b.2, corrected in 1b.5) is the one fixture meant to follow
   Outlook's observed layout rather than the writer's defaults. Two tests prove it is what it claims.
3. **The encodings.** The 8-bit string paths (`001E`) under each code page and each ladder rung, internet versus message code page
   disagreement, non-BMP text, multi-valued strings, a UTF-8 BOM and LF-only transport headers, plus the two hostile UTF-16 shapes.

It changes `msgcontainer.py` or `mapi.py` **only to fix a defect a test finds** (name it, show the failing expectation first). Any such
defect is a finding, reported with the typed expectation that exposed it.

Read first: `phase1b-build-spec.md` ("Further decisions": D13 encodings, D14, rule 3), `phase1b-fixtures.md` (Families H and I and the
construction-table sections), `phase1b-contract.md` sections 4, 5 and 13, `phase1b-ledgers.md` (the `declaration turn=1b.9` block, the 1b.4
outcome note for the ladder, the 1b.5 C5 test, and "What 1b.9 needs" in the 1b.7 and 1b.8 notes), `emailextract/model.py`
(`ContentFingerprint`, `SameMessageCandidate`), `emailextract/assemble.py` (`_content_fingerprint`), `emailextract/mapi.py` (the ladder:
`decode_string8`, `TextValue`, `CODEPAGES`) and `tests/test_msg_body.py` (the existing C5 test, `test_the_same_message_as_eml_and_msg_differs_only_where_d14_says`).

## Decisions the reviewer made (the owner may overrule; say so with evidence rather than building around one)

**D1. The pair's `.eml` is built in the test, not committed.** The catalogue lists `pair_gmail_reply.eml` as a committed fixture. A new
`.eml` under `fixtures/` is not free: `tools/update_eml_golden.py` pins **every** `.eml` there (a new record), the behavior ledger's
corpus-dependent components are keyed by a corpus version (a new `fixtures/` `.eml` appends a corpus version and new ledger lines), the
labels and gates expect a hand-typed `*.expected.json` for every `.eml` fixture, and `tests/ledger/corpus.json` is outside this turn's
allow-list. All of that is Turn 1b.10's, and none of it is needed to prove D14. So: **commit only `fixtures/msg/pair_gmail_reply.msg`**,
and build the `.eml` half as bytes in `tests/support/msg_construction.py` from the **same single message definition** (the headers, the
plain text, the HTML), so the two cannot drift. The pair test writes those bytes to `tmp_path`. State this deviation, and the owner
alternative (commit the `.eml` and take the corpus-version and golden churn in 1b.10), in the note. If you find a way to commit it that
leaves `update_eml_golden.py --check`, the behavior ledger and the corpus file untouched, say so; otherwise take the default.

**D2. The pair's message, and what "equal" means.** The `.eml` is a `multipart/alternative` (`text/plain` then `text/html`). The `.msg`
holds `0x007D` with the same original headers and a `0x1013` HTML body that is the **same HTML**, no plain stream (the measured 10-of-11
real shape). Expected, all hand-typed before running: `container_hash` differs (the file bytes differ); `content_fingerprint.body_digest`
is **equal** and `body_digest_view` is `HTML` for both (the digest is over the selected HTML view's code points as UTF-8, never over
transfer bytes); the `.eml` has a plain view and the `.msg` has none; and the HTML text the two documents project is identical. Compute
the expected digest in the test **independently** (`hashlib.sha256(expected_text.encode("utf-8"))` over a hand-typed text), not by calling
`_content_fingerprint`.

**D3. "One document shape modulo D14" is a field-by-field allow-list, typed by hand.** Extend the pattern of the existing 1b.5 C5 test:
compare the two `EmailDocument`s and assert every field that differs is in a **hand-typed allowed set** with the reason for each
(`container_kind`, `container_hash`, `container_facts`, each part's `part_id`/`stream_ref`/`encoding_source`/`size_bytes`/`sha256`
where the HTML bytes differ in transfer, the header records' `stream_ref`, and the projection-owned scaffolding headers). Any other
difference is a **finding**, not an addition to the allowed set. The plain part exists only on the `.eml` side: assert that exactly, as a
named difference, rather than by length.

**D4. "No candidate" for a plain-only versus HTML-only pair.** `SameMessageCandidate` documents that a plain-only versus HTML-only pair
surfaces as **no candidate** (different `body_digest_view`). No stage builds candidates in Phase 1b (`same_message_candidates_axis` is
not built), so the test asserts the property that *makes* it so: for the same text carried as plain in one container and as HTML in the
other, `body_digest_view` differs (`PLAIN` against `HTML`), and the two `ContentFingerprint`s are **not equal as records** even when the
text is equal. Build the second pair in the test (a plain-only `.eml` against an HTML-only `.msg` of the same words). Do not build
candidate objects.

**D5. Never dedupe on the raw hash.** Ingest both halves into one store through `ingest` (in `tmp_path`): two documents, two
`container_hash`es, both retained, equal `body_digest`, no merge, no cross-reference written, and re-ingesting either is a no-op (the
existing idempotence rule). The store must not treat the equal digest as a reason to drop one.

**D6. The Outlook-layout proof.** `test_the_handbuilt_layout_matches_the_construction_table`: read the committed
`msg_outlook_layout_handbuilt.msg` through the **raw reader** (`cfb.py`) and `olefile`, and assert its directory entries, stream names,
property-table sizes (the 32/8-byte headers), the `0x001A` class, the recipient table tags (`0C15`, `3001`, `3002`, `3003`) and its
attachment storage layout equal the **hand-typed construction table** in `tests/support/msg_construction.py` (the table is typed
from B1-B4 and [MS-OXPROPS], and typed *first*; do not derive it from the file). `test_the_handbuilt_layout_is_not_writer_defaults`:
assert the properties that distinguish it from what `tools/cfb_writer.py` would emit by default (directory order and tree shape, which
streams are mini-resident and which regular, the sector count and any tail slack, named-property storage presence). Pin each
distinguishing property from the **B1-B4 observations the table cites**, and state, for each, the observation it comes from. If the
fixture turns out to equal the writer's defaults on some property, say so: that is a finding about the fixture's claim, not a test to
loosen.

**D7. The encodings: a rung matrix first, typed before any fixture.** The ladder (1b.4) is: internet code page, then message code page,
then ASCII, then strict UTF-8, then Windows-1252, with `encoding_source` one of `internet_cpid`, `message_cpid`, `ascii`, `utf8_strict`,
`windows_1252`, and `CODEPAGES` = {1252, 20127, 28591, 65001}. **Write the matrix first**: for each of the five rungs, which committed
fixture makes it fire, with its two code-page properties, its bytes, and the expected `TextValue` (text, `encoding_source`, `source_kind`,
`declared_cp`). A rung with no fixture gets one (variants are allowed; keep the catalogue names where they fit). **A catalogue sentence
that contradicts the ladder is the catalogue's error**: `msg_string8_ascii20127` says `(ascii)` and `msg_string8_utf8_65001` says
`(utf8_strict)`, but a fixture that sets the internet code page to 20127 or 65001 fires the **`internet_cpid`** rung, not `ascii` or
`utf8_strict` (those two rungs fire only with no usable code page). Type the expectation from the ladder rules, report the disagreement,
and correct the catalogue sentences in `phase1b-fixtures.md` (as 1b.4 did for `msg_codepage_disagree`). Add the extra fixtures needed so
that all five rungs are covered by a committed `.msg` (for example a variant with no code pages and all-ASCII bytes; one with no code
pages and valid multi-byte UTF-8; one with no code pages and bytes that are not valid UTF-8).

**D8. Each Family H fixture, with its hand-typed expectation.** `msg_string8_1252`, `msg_string8_ascii20127`, `msg_string8_utf8_65001`,
`msg_string8_body` (a `0x1000:001E` plain body: it flows through the ladder, is re-encoded to UTF-8 in the projection, and its
`PartRecord`'s `encoding_source` is the ladder's), `msg_non_bmp_text` (a `001F` subject with a non-BMP character: the surrogate pair
survives as one code point, the `message_facts` subject is that one character, the UTF-8 re-encoding of it is 4 bytes, and every
offset in the span row that counts characters counts the character once), `msg_multivalued_strings` (a multi-valued string property:
**every value is kept**, in order). Plus the pair's `.msg`. That is 7 new committed fixtures if the D7 matrix needs no variants; each
new fixture's construction table is typed in `tests/support/msg_construction.py` **before** the generator runs; `tools/make_msg_fixtures.py`
and `fixtures/msg/SHA256SUMS` follow. **No `.msg` sidecars.**

**D9. The two existing header-shape fixtures get their encodings test.** `msg_transport_headers_utf8_bom` and
`msg_transport_headers_lf_only` (committed in 1b.5): `test_the_utf8_bom_and_lf_only_headers` asserts that the headers parse to the
same field list as the CRLF/no-BOM twin built in the test, the BOM is not part of the first field's name, no field is lost or
re-split, and the span rows account for every byte (including the BOM and the bare LFs). `msg_codepage_disagree` (1b.4): add
`test_internet_versus_message_codepage_disagreement` asserting which code page wins per the ladder, that the loser is **recorded**
(`TextValue.source_kind` and `declared_cp`), and that `container_facts` publishes both code pages (`internet_codepage`, `message_codepage`).

**D10. The two hostile UTF-16 shapes, through the container.** The catalogue lists `seed_lone_surrogate` and `seed_odd_length_utf16` as
committed seeds. Build them **inside the test** from a fixture by patching bytes (the 1b.3 `_seeds` pattern), not as committed files: a
`001F` string ending on a lone surrogate, and a `001F` stream of odd length. Through `MsgContainer` + `assemble` + `ingest`: neither
raises, the faulted string is **recorded** (the fault name `mapi` gives it appears as the documented gap or fault), no replacement
character, `surrogatepass` or latin-1 fallback appears in any published record, and the document is still a document (or a named
refusal). If the current behaviour for either differs from what 1b.4 documented, that is a finding.

## Order of work

1. **Matrix and expectations first** (D6, D7): the rung matrix, the pair's expected texts and digests, the layout table's distinguishing
   properties, all typed before any new code runs. Report catalogue contradictions (D7) before editing a sentence.
2. Fixtures (D8) and the pair builder (D1/D2): construction tables typed first, then `tools/make_msg_fixtures.py` and `SHA256SUMS`.
3. `tests/test_msg_encodings.py` (4 declared plus the extras).
4. `tests/test_msg_outlook_layout.py` (2 declared).
5. `tests/test_msg_cross_container.py` (3 declared plus D5).
6. Extras, full suites, `--check` tools, mutations, the outcome note.

## Tests

The 9 declared tests of the `declaration turn=1b.9` block, **names exactly as declared** (`phase1b-ledgers.md`):
`test_the_pair_has_different_container_hash_and_equal_body_digest`, `test_the_pair_is_one_document_shape_modulo_d14`,
`test_the_pair_with_a_plain_only_view_is_no_candidate`, `test_the_handbuilt_layout_matches_the_construction_table`,
`test_the_handbuilt_layout_is_not_writer_defaults`, `test_001e_code_pages_1252_20127_28591_65001`,
`test_internet_versus_message_codepage_disagreement`, `test_non_bmp_surrogate_pairs_survive`, `test_the_utf8_bom_and_lf_only_headers`.
Plus these extras, declared in the same block and added to `tests/test_turn_declarations.py`:
* **All five rungs** are covered by a committed `.msg` (assert the rung of each by name, from the matrix).
* **Multi-valued strings**: every value kept, in order, none merged, none dropped.
* **`msg_string8_body`** through the walker: the projected plain leaf is UTF-8, `charset=utf-8`, and its `encoding_source` is the ladder rung.
* **D5 (never dedupe)** through `ingest`.
* **D10 (hostile UTF-16 shapes)** through the container.
* **Determinism** of the pair's documents and of `container_hash`es under two `PYTHONHASHSEED` values, on both interpreters.
* **Seeded fuzz extension**: operators on the `001E` string bytes, the two code-page properties and the multi-valued length prefixes;
  at least 150 more mutants over at least three of the new fixtures; every mutant yields a document or a named refusal; every
  published string is UTF-8 encodable; no exception of any kind.
* **The `.eml` path**: `update_eml_golden.py --check` and the behavior ledger stay green and untouched.

**Mutations** (each must make a named test fail; run, restore, report the failing test names): (1) compute `body_digest` over the HTML
stream's raw bytes (or the transfer-encoded bytes) instead of the view's code points; (2) decode `001F` text with errors ignored or
`surrogatepass`, or drop the low surrogate of a pair; (3) swap the internet and message code page precedence in the ladder.

## Allow-list

The ledger's block for `turn=1b.9` (`emailextract/msgcontainer.py`, `emailextract/mapi.py`, `fixtures/msg/`,
`tests/test_msg_cross_container.py`, `tests/test_msg_outlook_layout.py`, `tests/test_msg_encodings.py`, `tests/ledger/label_ledger.json`,
`docs/design/phase1b-ledgers.md`) **plus these named additions, which you must also write into the ledger's allow-list line in the same
turn**: `tools/make_msg_fixtures.py`, `tests/support/msg_construction.py`, `tests/support/olefile_oracle.py` (only if a check needs a
field), `tests/test_msg_fixtures.py`, `tests/test_fixture_census.py`, `tests/test_turn_declarations.py`, `tests/test_phase1_scope.py`
(only if a new module or import requires it; name each line), `docs/design/phase1-turn-declarations.md`,
`docs/design/phase1b-fixtures.md` (the D7 corrections and the D1 pair note), `docs/design/msg-architecture.md` (a short section on the
pair and the layout proof), `docs/design/phase0-gaps.md` (only if a registry sentence is wrong; list each edit). **`msgcontainer.py` and
`mapi.py` change only to fix a defect a new test exposes** (name each hunk and the test). **`behavior_ledger.json` and `versions.py` are
permissions, not duties**: the three `msg` ledger components belong to 1b.10; if a `--check` tool demands a change anyway, stop and
say so. **Not**: `emailextract/cfb.py`, `emailextract/walk.py`, `emailextract/attach.py`, `emailextract/model.py`,
`emailextract/assemble.py`, `emailextract/rtf.py`, `emailextract/ingest.py`, `emailextract/parse.py`, `emailextract/evals/**`,
`tools/cfb_writer.py`, `tools/update_eml_golden.py`, `tests/ledger/corpus.json`, `tests/ledger/behavior_ledger.json`, the `.eml` golden,
any committed `.eml` fixture, `CLAUDE.md`.

## What must NOT be done

No new committed `.eml` anywhere under `fixtures/` (D1). No `.msg` sidecar. No candidate objects and no `same_message_candidates` axis
work. No change to `content_fingerprint`'s definition, to the schema or to any record's serialised shape. No replacement character,
`surrogatepass` or latin-1 fallback to make a hostile string "work". No loosening of a typed expectation: a disagreement between a
hand-typed value and the code is the finding. No real or employer message in any fixture. No `olefile` import under `emailextract/`.
Do not commit.

## Checks and report

1. Full suite green on the primary interpreter and on the repo's 3.11 (with `docextract_core` and `olefile` installed); note the
   interpreter and the wall time by chunk.
2. `tools/make_msg_fixtures.py --check`, `tools/make_fixtures.py --check`, `tools/update_eml_golden.py --check`,
   `tools/update_behavior_ledger.py --check`, `tools/update_label_ledger.py --check` and `python -m emailextract.evals` all exit 0.
3. The outcome note in `phase1b-ledgers.md` (this turn only): D1-D10 and whether you changed any, with evidence; **the rung matrix as
   typed beside the results**; the catalogue contradictions found and the sentences corrected; the pair's expected texts, digests and the
   allowed-differences list with each reason; the layout proof's distinguishing properties and the observation each cites; the hostile
   UTF-16 outcomes; any defect found in `msgcontainer.py`/`mapi.py` with its failing expectation; the three mutation results; every
   existing test edited and why.
4. What 1b.10 needs: the persistence and measurers for every container-side fact (`message_facts`, `attachment_facts`, `rtf_facts`,
   `container_gaps`), the three `msg` ledger components and their version constants, the `.eml` half of the pair if the owner wants it
   committed (and the corpus/golden churn that brings), the final report and the `0.2.0` release prep.

## Not this turn, but the owner should decide

* **Commit the pair's `.eml`?** (D1.) The default builds it in the test; committing it moves the `.eml` golden and the corpus version,
  which 1b.10 would absorb.
* **The `MELA` CRC leniency and the dictionary's unwritten-byte rule** (1b.8 fix note): still open.
* **P1-P6 on the real corpus**: every tag outside the first eleven spike files is public-spec only until the owner runs the probes.

Stop at the turn boundary: the pair proves D14 both ways, the Outlook layout is proven to be what it claims, all five ladder rungs and
the hostile UTF-16 shapes are pinned, the golden is untouched, the outcome note is written. Do not start 1b.10.
