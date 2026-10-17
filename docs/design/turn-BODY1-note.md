# Turn BODY1 note: the body text and the attachment bytes, on demand and never stored

Status: built (uncommitted, unreleased). Interpreter for every measurement below:
CPython **3.11.15** (`%LOCALAPPDATA%\Temp\wbv311b\Scripts\python.exe`, which has
`olefile` 0.47 and imports `emailextract` from this checkout). Suite and `--check` results on
both interpreters the prompt named are in "Verification".

## What changed

| file | change |
|---|---|
| `emailextract/bodytext.py` | **new.** `body_text(source, *, max_chars=...)` and `iter_attachment_payloads(source, *, max_count=..., max_bytes=...)`, the four frozen records (`BodyText`, `BodyRefusal`, `AttachmentPayload`, `AttachmentRefusal`) and the documented bounds. |
| `emailextract/assemble.py` | `_content_fingerprint`'s view choice extracted to a public `selected_body_text(raw, result, *, limits)` and used by both it and `body_text`, so the digest and the accessor cannot choose different views. **No output moves** (the digest and every golden are byte-identical). |
| `emailextract/versions.py` | `BODY_TEXT_VERSION = "1"`, `ATTACHMENT_ACCESSOR_VERSION = "1"`, each with a "what moves it" docstring. |
| `emailextract/__init__.py` | exports the two functions, the four records, the two constants and the four bound constants (`__all__` kept case-insensitively sorted). |
| `tools/behavior_ledger.py` | two new corpus components `body_text` / `attachment_payloads`, keyed by the two constants, plus their shape functions and a header sentence naming them. |
| `tests/ledger/behavior_ledger.json` | the two components recorded (corpora 1-8 for both). **No existing component's line moved** -- the recorded tool run appended only these. |
| `tests/support/body_text_labels.py` | **new.** The hand-typed labels (13 committed fixtures + one hand-built message), frozen under `tests/support/` so the label ledger fingerprints them. |
| `tests/test_body_text.py`, `tests/test_attach_payloads.py` | **new.** 66 + 20 collected tests (34 declared test functions, the rest parametrized over the labels). |
| `tests/test_phase1_scope.py` | `bodytext.py` joins `EXPECTED_LIBRARY`. |
| `tests/test_phase0_gaps.py` | `bodytext.py` joins the gap registry's `_LIBRARY`, so the two dotted reason ids it names (`body.no_text_part`, `attach.cid_unreferenced`) are held to `docs/design/phase0-gaps.md` -- both are already documented, and the registry stays at 88 ids. |
| `tests/test_versions.py` | the two constants join `EXPECTED_FROZEN`. |
| `tests/test_turn_declarations.py`, `docs/design/phase1-turn-declarations.md` | the `BODY1` declaration block and `BUILT_TURNS`. |
| `tests/ledger/label_ledger.json` | one appended line (`tests/support/body_text_labels.py`); nothing edited. |

No body text, no attachment byte and no new field reached any record: `OUTPUT_SCHEMA_VERSION`
stays `6`, `EMAIL_PARSER_VERSION` stays `2`, and the recorded `contracts` fingerprint is
unchanged (it is asserted by `tests/test_body_text.py::test_no_manifest_byte_changes` and by the
committed `tests/golden/eml_golden.json`).

## The public signatures

```python
body_text(source: object, *, max_chars: int = 1_000_000) -> BodyText | BodyRefusal
iter_attachment_payloads(
    source: object, *, max_count: int = 50, max_bytes: int = 8 * 1024 * 1024
) -> Iterator[AttachmentPayload | AttachmentRefusal]
```

`source` is a path, `bytes`, a `FileMaterial` or an already-built container -- the same inputs
`ingest_path` takes, read through the entry point's own bytes-to-container rule
(`ingest._container_for`) and its own sniff (`parse.parse`), so an `.eml` and a `.msg` are read
exactly as the ingest path reads them. Both functions build `parse.Limits.untrusted()`
internally, so `max_input_bytes` (64 MiB), the walker's decoded-byte caps (32 MiB per part,
128 MiB total), `max_depth` and `max_parts` bound the work and none of them is a caller knob yet.

```python
@dataclass(frozen=True)
class BodyText:
    view: str                                   # "plain" | "html": D14's view, not a preference
    text: str                                   # the decoded text, in code points
    segments: tuple[tuple[int, int, HitLocation], ...]   # (start, end, locator) per physical line
    truncated: bool
    char_count: int                             # len(text) after truncation
    reason_id: str | None                       # "body.no_text_part" when no text body view
    email_parser_version: str
    decode_chain_version: str
    htmltext_version: str
    body_text_version: str

@dataclass(frozen=True)
class BodyRefusal:
    reason_id: str; detail: str | None
    email_parser_version: str; body_text_version: str

@dataclass(frozen=True)
class AttachmentPayload:
    occurrence_ref: str; filename: str | None; media_type: str; size: int; data: bytes
    attachment_accessor_version: str

@dataclass(frozen=True)
class AttachmentRefusal:
    occurrence_ref: str; reason_id: str; detail: str | None
    attachment_accessor_version: str
```

`segments` uses the library's existing `model.HitLocation` (`part`, `view`, `span` as
`timeevent.Span`, `unit`), not `siblings.Locator`: `Locator` is the sibling-store config in
this package and `ids.RawSpan` is a **byte** span into the raw message, which an HTML view does
not have (decision 8: HTML is `part_level` for the byte side). A hit therefore cites as
`part 1.1, view html, span [a, b), unit <line>` and the two integers beside it are the same
`[a, b)`, asserted in both directions.

## Every disagreement with the typed labels

**None on the values.** 13 committed fixtures (plain, HTML-only, multipart/alternative, `.msg`
plain, `.msg` with both bodies, quoted-printable, a non-UTF-8 charset, an empty body, a
tracking-pixel HTML body, a forwarded message, and three attachment-bearing messages) plus one
hand-built zero-width/tracking-pixel message were typed from their constructions in
`tests/support/body_text_labels.py` and compared **after**; all 14 body texts, all 5 attachment
lists (payloads and skips, in order, with sizes) agree exactly.

Three protocol facts, reported rather than hidden:

1. **One label was wrong and was corrected before the accessor ran.** `body_no_text_part`'s pdf
   is `b"%PDF-1.4\nfixture\n%%EOF\n"`, 23 bytes; I typed 22 and the construction's own `len()`
   corrected it. The correction is recorded in the label's `provenance`.
2. **Two values leaked before the label file was frozen.** In the first smoke run of the new
   module (before the label file existed) `body_text` printed `plain_simple`'s text and
   `iter_attachment_payloads` printed `attachments_mixed`'s four sizes and occurrence refs. Both
   were then typed independently (text from `make_fixtures._fixture_plain_simple`, sizes from
   `len(tiny_pdf(...))`/`len(tiny_xlsx())`/`len(tiny_docx())`/`len(tiny_png(...))`), so the
   label's provenance is the construction and not the accessor's output -- but the comparison
   for those two entries is not blind, and every other entry is.
3. **One expectation in a test (not a label) was wrong and was fixed from the bytes.**
   `headers_only.eml` declares `Content-Type: text/plain; charset=us-ascii` with a zero-length
   body, so it **has** a body view that is empty: `text == ""`, `reason_id is None`. Only a
   message with no text body view at all (`body_no_text_part`) carries
   `body.no_text_part`. The test now asserts the two cases apart.

## Findings (not fixed: reported)

- **A `.msg` body is read out of the projection, not out of the CFB file.** My first cut sliced
  a part's span out of the *file* bytes and `text.analyse_part` raised
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff` on `msg_plain_only`: its `001F`
  stream is UTF-16LE (BOM `ff fe`) in the file, while every recorded span points into
  `container.raw_bytes()` -- the virtual RFC 822 projection. The fix is in the module (it reads
  `container.raw_bytes()`, as `assemble` and `walk` do) and the label for `msg_plain_only`
  (`"\r\n"`) was typed from the construction before that fix, so it is also the proof.
- **Two hostile `.msg` fixtures return mojibake body text**, and the accessor inherits it
  exactly as the recorded digest does: `msg_fat_cycle` and `msg_truncated_stream` answer
  `view="html"`, text `'<\x00h\x00t\x00m\x00l\x00>...'` -- the pass-through `1013` stream's
  UTF-16LE bytes read as 8-bit text. Their documents are `truncated(declared_length_mismatch)`
  and `truncated(stream_ended_early)`, so a consumer has the warning beside the text; the
  projection's charset handling is not this turn's to change (it would move
  `MSG_PROJECTION_VERSION` and every `.msg` fingerprint).
- **A `.msg` whose part bytes cannot be decoded in its declared charset can make
  `text.analyse_part` raise** (`decoded.decode(used, "strict")`). No committed fixture does it
  (all 52 were run: zero raises), but it is reachable, so both accessors carry the same guard
  `assemble` has: an unexpected stage failure is a typed refusal with the D6 reason
  `extractor_error`, never an exception. `tests/test_body_text.py::test_a_body_that_cannot_be_decoded_is_a_typed_refusal`
  plants the failure and proves the refusal.
- **The accessor re-decodes a body up to three times**, because it reuses D14's rule verbatim:
  `selected_body_text` calls `selection.display_text` (one `analyse_parts`), `selection_rows`
  (which re-runs `analyse_parts` for the texts) and `quote_resolve.html_views` (one
  `analyse_part` per html view), and each pass builds the part's offset map. Measured on a
  20 MiB HTML body: `body_text` 18.3 s versus `assemble` 32.7 s on the same message, so the
  accessor is cheaper than the digest path it shares, and 0.9 s / 1.9 s at 1 MiB. Making one
  pass serve all three would be an `assemble` refactor, not an accessor one.
- **`attach.attachments()` decodes every attachment once whether or not the caller's ceiling
  accepts it** (it needs each payload for the magic verdict), and the accessor then decodes the
  accepted ones once more to hand them out. Refusal happens **before the second decode**, so a
  refused attachment is never held twice, and the first decode is bounded by the walker's own
  caps -- but a mid-size attachment under the walker's cap is decoded even when the caller's
  ceiling will refuse it. Measured cost of that: 5.3 s / 171 MiB for a 20 MiB base64 attachment
  whether the default 8 MiB ceiling refuses it or a 32 MiB ceiling returns it.

## Divergences from the brief, with evidence

1. **`max_bytes` is both ceilings.** The brief fixes the signature as
   `(source, *, max_count=..., max_bytes=...)` and asks for "per-attachment **and** total byte
   ceilings". Rather than add a keyword the brief does not name, `max_bytes` is the
   per-attachment ceiling **and** the running total budget for one iteration: an attachment over
   it is refused `size_cap`, and once the yielded payloads reach it the rest are refused
   `total_size_cap`. Both are distinguishable in the result
   (`tests/test_attach_payloads.py::test_an_attachment_larger_than_the_ceiling_is_refused_not_returned`
   shows one of each on one message: 583 fits in 600, the 82-byte png does not fit in the 17
   that are left).
2. **The decorative skip is a refusal, not a filtered-out item.** "yields ... for each
   *non-inline-decorative* attachment ... and expose which were skipped" plus "never silently
   dropped" is satisfiable two ways; I chose one result per occurrence, so a skipped occurrence
   is an `AttachmentRefusal(occurrence_ref, "attach.cid_unreferenced", detail=<the rule id>)`.
   The reason id is the **registered** gap id (`attach.cid_unreferenced`), not a new one.
3. **No new reason id at all.** Everything reuses an existing closed id: the entry point's
   (`not_a_message`, `input_over_cap`, and for the hostile CFB fixtures `cfb_directory_loop`),
   the D6 cap reasons `size_cap` / `total_size_cap` / `part_count_cap` (the design's own home
   for a cap's identity after it pruned `attach.size_cap_hit`), the registered gap id
   `attach.cid_unreferenced`, and D6's `extractor_error`. The registry therefore stays at
   **88** ids and `docs/design/phase0-gaps.md` needed no entry.
4. **`ATTACHMENT_ACCESSOR_VERSION` is separate, and both are behavior-ledger components.** The
   two functions are separate contracts (a body view's text versus an attachment's bytes): a
   rule change in one must not claim a change in the other. Both components fingerprint the
   **`.eml`** corpus, and the `.msg` half is guarded by `msg_projection`/`msg_reader`, because
   the decode chain and the transfer-encoding decoders they read are the same code the
   `.msg` path runs; that reasoning is in the ledger header, which also means a new `.msg`
   fixture adds no line to either new component.
5. **The zero-width-character fixture is hand-built, not committed.** No committed fixture
   carries a zero-width character, and adding one would append a corpus version and move
   `tests/golden/eml_golden.json`. It is a `bytes` literal in the label file driven through
   `memory_bytes` (the second route every input test takes), with its text typed by hand
   (`"Hi\u200bBen.\r\n\r\n"`).
6. **Two tests beyond the declared list are fixture-shaped helpers, not new cases**:
   `_document`, `_container`, `_results`, `_payloads`, `_refusals` and
   `_many_attachment_message` are private helpers in the two new test files; the 34 declared
   functions are the whole contract surface (86 collected tests, 52 of them the label
   parameters).

## The mutation table

Fourteen mutants, each a one-place edit, each run with `PYTHONDONTWRITEBYTECODE=1`, each
restored from the in-memory original and re-hashed (`restored byte for byte: True` for all 14).
Driver: `.scratch/body1_mutations.py`; transcript: `.scratch/body1_mutations.txt`.

| # | mutant | named test that fails |
|---|---|---|
| M01 | `body_text` claims the html view for every message (HTML chosen where the digest's view is plain) | `test_body_text.py::test_every_labelled_fixture_takes_the_view_d14_digests` (+ `test_each_labelled_fixture_returns_its_typed_text`, `test_the_segments_partition_...`, `test_a_message_with_no_text_body_...`) |
| M02 | the plain view returns the **html** projection's text (text for the wrong view) | `test_body_text.py::test_each_labelled_fixture_returns_its_typed_text` (+ `test_max_chars_boundaries_truncate_and_flag`, `test_a_decode_change_moves_the_body_text_fingerprint`) |
| M03 | a CRLF line's next segment starts one code point early (**segments overlap**) | `test_body_text.py::test_the_segments_partition_the_text_and_every_locator_resolves` |
| M04 | every segment's locator span runs one past its line (**a locator off by one**) | `test_body_text.py::test_the_segments_partition_the_text_and_every_locator_resolves` |
| M05 | `kept = text` (**`max_chars` ignored**) | `test_body_text.py::test_max_chars_boundaries_truncate_and_flag` |
| M06 | `truncated = False` (**truncation not flagged**) | `test_body_text.py::test_max_chars_boundaries_truncate_and_flag` |
| M07 | the payload is the raw transfer bytes (**a transfer encoding not decoded**) | `test_attach_payloads.py::test_the_payload_matches_the_occurrence_the_manifest_carries` (+ 6 more, incl. `test_each_labelled_fixture_returns_its_typed_payloads`) |
| M08 | the byte ceiling is never applied (**the byte ceiling removed**) | `test_attach_payloads.py::test_an_attachment_larger_than_the_ceiling_is_refused_not_returned` (+ 3: the total ceiling, the large base64 blob, the fifty-attachment case) |
| M09 | a count-capped occurrence yields nothing (**an attachment dropped silently**) | `test_attach_payloads.py::test_the_count_ceiling_refuses_the_rest_and_names_the_reason` |
| M10 | a `message/rfc822` payload is opened and its body returned (**a nested message recursed**) | `test_attach_payloads.py::test_a_nested_message_is_returned_unrecursed` (+ `test_each_labelled_fixture_returns_its_typed_payloads`) |
| M11 | the occurrences come back reversed (**occurrence order changed**) | `test_attach_payloads.py::test_the_payload_matches_the_occurrence_the_manifest_carries`, `::test_every_occurrence_of_every_committed_message_yields_one_result` (+ 5 more) |
| M12 | the decorative rule's skip is not applied (**a decorative attachment returned**) | `test_attach_payloads.py::test_a_decorative_occurrence_is_skipped_and_reported` (+ `test_each_labelled_fixture_returns_its_typed_payloads`) |
| M13 | the document's `content_fingerprint.body_digest` carries the text instead of its digest (**body text written to a manifest field**) | `test_body_text.py::test_no_manifest_byte_changes` (+ `test_every_labelled_fixture_takes_the_view_d14_digests`, and `test_behavior_ledger.py::test_the_committed_ledger_agrees_with_the_code`) |
| M14 | the strict decode uses `windows-1252`/replace and `BODY_TEXT_VERSION` stays `"1"` (**`BODY_TEXT_VERSION` not bumped when decoding changes**) | `test_behavior_ledger.py::test_the_committed_ledger_agrees_with_the_code` (naming `BODY_TEXT_VERSION`) + the four other `check()`-driven tests |

## Measured cost

`3.11.15`, one call per measurement, wall time median of 3 without `tracemalloc`, peak from one
separately traced run. The file the accessor reads is written to a temp directory first, so the
read is the accessor's own cost, and the message is built before the timer starts.

| case | message | time | peak (traced) | result |
|---|---|---|---|---|
| `body_text`, 20 MiB **plain** body | 20.00 MiB | **149 ms** | **80.0 MiB** | `max_chars` cut it to 1 000 000 chars, 15 874 segments, `truncated=True`; view `plain` |
| `body_text`, 20 MiB **html** body | 20.00 MiB | **18 268 ms** | **252.3 MiB** | 45 908 projected chars, 998 segments; view `html` |
| `iter_attachment_payloads`, one 20 MiB base64 attachment, default 8 MiB ceiling | 27.37 MiB | 6 167 ms | 171.0 MiB | 0 payloads, 1 `size_cap` refusal |
| same, 1 MiB ceiling | 27.37 MiB | 5 284 ms | 171.0 MiB | 0 payloads, 1 `size_cap` refusal |
| same, 32 MiB ceiling (returned) | 27.37 MiB | 5 254 ms | 171.0 MiB | 1 payload, 20 971 520 bytes |
| `iter_attachment_payloads`, **fifty** 4 KiB attachments | 0.28 MiB | **61 ms** | **0.89 MiB** | 50 payloads, 204 800 bytes, 0 refusals |
| `iter_attachment_payloads`, fifty 200 KiB attachments, default 8 MiB ceiling | 13.37 MiB | 2 654 ms | 41.4 MiB | 40 payloads (8 192 000 bytes), 10 `total_size_cap` refusals |

Scaling, for the two numbers that matter (`body_text`, wall time): 1 MiB html 907 ms, 4 MiB
1 891 ms, 20 MiB 18 268 ms; plain bodies are ~150 ms at every size up to 20 MiB because
`max_chars` bounds the text (not the decode). The peak on a large **html** body is ~12x the
message because the part's offset map is built per code point in each of the three passes
above; the peak on a large **plain** body is ~4x, and the attachment peak is ~6x the message
(each accepted payload is held once, in the record handed to the caller).

For comparison on the same 20 MiB html message: `assemble` (the recorded digest path, which the
accessor reuses) takes **32.7 s** -- so the accessor costs about half a document, not a second
measure.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 <python> -m pytest -q`, always run from this directory.
- **`%LOCALAPPDATA%\Temp\wbv311b` (CPython 3.11.15, with `olefile` 0.47): 2701 passed, 2
  skipped, 0 failed** -- the whole suite, nothing ignored (an earlier same-day run of the tree
  before this turn's test files existed collected 2615, so the 86 new tests account for the
  difference).
- **The two interpreters the prompt names have no `olefile` and no `lxml`**, so six test files
  fail to **collect** there (`ModuleNotFoundError: No module named 'olefile'`):
  `tests/test_cfb.py`, `test_msg_attachments.py`, `test_msg_outlook_layout.py`,
  `test_msg_recipients.py`, `test_olefile_oracle.py`, `test_phase1b_hostile_run.py`. That is a
  property of those venvs, not of this turn. To get a usable cross-interpreter run I ran both
  with those six files ignored **and ran the identical command against a clean `git worktree` at
  `HEAD`** (`4c74c56`) so the failure sets are comparable:
  - `hub-venv-311` (3.11.15): **2658 passed, 1 skipped, 6 failed**; `HEAD`: 2573 passed, 1
    skipped, **the same 5 failures, plus one I can account for**:
    `tests/test_dates.py::test_the_parser_is_linear_in_the_input` failed *only* in this run,
    where three suites ran concurrently on the same machine, and passes on both interpreters when
    run alone (`2 passed`). It is a wall-clock linearity assertion, not a value. The 5 baseline
    failures are
    `test_ingest_msg.py::test_a_hostile_msg_directory_yields_documents_or_named_skips`,
    `test_msg_fixtures.py::test_the_mini_cutoff_trio_is_4095_4096_4097`,
    `::test_the_outlook_layout_fixture_is_typed_from_b1_b4` and the two
    `test_turn_declarations.py` collection tests (the latter two are caused by the `--ignore`
    list: their declared tests live in the ignored files).
  - `hub-venv-314` (3.14.4): **2653 passed, 1 skipped, 11 failed**; `HEAD`: 2568 passed, 1
    skipped, **the same 10 failures plus the same load artefact**, here
    `tests/test_addresses.py::test_the_tokenizer_is_linear_in_the_input` (also `2 passed` when run
    alone on both interpreters). The baseline 10 are the 5 above plus
    `test_html_parser_experiment.py::test_the_experiment_runs_over_every_html_fixture`,
    `test_html_projection_golden.py::test_a_second_interpreter_is_an_additional_comparison`,
    `test_ingest.py::test_the_manifest_and_the_store_are_byte_identical_across_seeds_and_interpreters`,
    `test_ingest_msg.py::test_the_msg_manifest_is_byte_identical_across_seeds_and_interpreters`
    and `test_selection.py::test_the_corpus_projection_hash_is_interpreter_stable` -- all of them
    comparisons that need `lxml` or a second interpreter, absent from that venv.
  - **No value-level failure is attributable to this turn**: the before/after `FAILED` sets
    differ only by those two timing assertions, and the pass count grows by 85 on 311 and 85 on
    314 (the 86 new tests, less the one timing test that was already counted as passing in the
    baseline).
- Five `--check` tools exit **0 on all three interpreters** (the two named ones and `wbv311b`):
  `tools/make_fixtures.py --check`, `tools/make_msg_fixtures.py --check`,
  `tools/update_eml_golden.py --check` (no recorded golden byte moved),
  `tools/update_behavior_ledger.py --check` (no existing component's fingerprint moved, and the
  two new ones are byte-identical across 3.11/3.14) and `tools/update_label_ledger.py --check`
  (the new label file appended, nothing edited).
- Mutation run: `PYTHONDONTWRITEBYTECODE=1 .scratch/body1_mutations.py` -- 14/14 caught, 14/14
  restored byte for byte (sha256 compared before and after).

## What the hub has to do with each result

- **`body_text`** gives searchable text and the citation: index `text`, and cite a hit as
  `parts[locator.part]` + `locator.view` + `locator.span` (+ `locator.unit` for the line), which
  `assemble.resolve_span` resolves to the message's bytes where the view allows it (`plain` is
  byte-exact for a strict single-byte/UTF-8 identity part; `html` is `part_level` by decision 8
  and its span is exact **inside** the projection this accessor returns). Treat
  `reason_id="body.no_text_part"` as "no letter body to index" and a `BodyRefusal` as "the file
  is not a message this library reads" -- both are values, so neither needs an exception path.
  `truncated=True` means the stored text is the first `char_count` characters only.
- **`iter_attachment_payloads`** is what makes an attached invoice readable: route `data` by
  `media_type` to the workbook family (`.xlsx`, `...spreadsheetml.sheet`) or the word family
  (`.docx`, `...wordprocessingml.document`), and cite through `occurrence_ref` -- the same
  `occurrence_path` the document's `AttachmentOccurrence` carries -- plus the child extractor's
  own citation, so one hub citation resolves to the email occurrence **and** to the paragraph of
  the invoice. A `message/rfc822` (or attached `.msg`) payload is the child **message's file
  bytes**: the hub decides whether to recurse (this library will not). A refusal with
  `reason_id="attach.cid_unreferenced"` is a decorative inline image (a tracking pixel): do not
  index it. `size_cap`/`total_size_cap`/`part_count_cap` mean "raise the ceiling and re-run",
  and `detail` names the numbers.
