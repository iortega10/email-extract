# email-extract

Deterministic extraction from **`.eml`** (RFC 5322 / MIME) messages: the header projection, the plain
and HTML body views, the quote boundaries and view levels, the attachment manifest, and one
self-contained JSON record per message (plus a content-addressed store and an ingest manifest).

No LLM, no clock, no network: the same bytes always produce the same record, on any machine, in any
hash-seeded process, on either pinned interpreter.

Status: **0.1.0 (unreleased)** -- Phase 1, the `.eml` parser and its oracle.

## What it is, and what it is not

**It is** a deterministic `.eml` parser. It measures a message into frozen records --
`EmailDocument` and everything it carries -- with byte spans that cite the raw bytes, a tri-state
(`value` / `absent` / `unknown`) for every field that can honestly be undecided, and a closed reason
id wherever it is `unknown`. It is importable with **no sibling repository** installed.

**It is not**, in 0.1:

* **not an LLM and not a service** -- no model, no network call, nothing fetched. A remote reference
  (`<img src="https://...">`) is recorded, never dereferenced;
* **not a `.msg`/CFB reader.** A CFB (`D0CF11E0...`) input is refused by name: `parse` returns the
  named error `cfb_msg_unsupported`. The `.msg` reader is Phase 1b;
* **not a threading or time-reconciliation engine.** No thread is built and no `TimeEvent` is
  emitted yet; the `children`, `thread_edges`, `times` and `same_message_candidates` axes ship
  present-but-empty, each marked `unknown(not_built_in_phase1)` -- a built observation, never a
  silent blank;
* **not a matcher or a query layer.** `emailextract.seam` is a stub seam with a separate constant;
* **not language-complete for quotes.** Quote detection is **English-first**: the reply-marker
  families it recognises are named and gated, and a shape it does not recognise is recorded as a gap
  (`body.html_quote_rule_gap`, `body.mixed_origin_quoting`, ...), never guessed at;
* **not a replacement for reading the bytes.** Every claim it makes is anchored to a span, and the
  spans are what a citation resolves to.

## Install

```sh
pip install email-extract
```

The only runtime dependency is [`docextract-core`](https://pypi.org/project/docextract-core/). The
sibling parsers are **optional extras**, routed to only as an alternate read of an already-extracted
child, and never imported by this package:

```sh
pip install "email-extract[word]"   # route a child .docx to word-extract
pip install "email-extract[form]"   # route a child .pdf/.xlsx to form-extract
```

The `form` extra requests `form-extract` **plain** on purpose: its own `[pdf]` extra pulls PyMuPDF
(AGPL-3.0), which this package must never request. `olefile` (BSD) is *not* a dependency of 0.1 --
it arrives with the `.msg` reader.

## Quick start

The blocks below are run verbatim by `tests/test_readme_examples.py`. That test supplies two names --
`MESSAGE_BYTES` (a small multipart `.eml`) and `MESSAGE_PATH` (the same message on disk) -- and runs
each block in a temporary directory. Point those at your own message and the blocks run as written.

### Assemble one message into an `EmailDocument`

<!-- example:assemble-one-message -->

```python
from emailextract import assemble
from emailextract.container import EmlContainer, memory_bytes
from emailextract.model import Status
from emailextract.parse import Limits

document = assemble(EmlContainer(memory_bytes(MESSAGE_BYTES)), limits=Limits.untrusted())

assert document.status.status is Status.PARSED and document.status.reason is None
print("schema", document.output_schema_version, "kind", document.container_kind.value)
print("headers:", [header.name for header in document.headers])
print("parts:", [part.content_type for part in document.parts])
```

`assemble` is a pure function of the container bytes and `limits`: no clock, no path, no environment,
and it never raises for input *content* (a stage that cannot finish records a failure instead).

### Ingest a directory into a store and read the manifest back

<!-- example:ingest-a-directory -->

```python
from pathlib import Path

from emailextract import document_store, ingest_path, manifest_store, read_manifest
from emailextract.parse import Limits

inbox = Path("inbox")
inbox.mkdir(exist_ok=True)
(inbox / "message.eml").write_bytes(MESSAGE_BYTES)

store = document_store("store")
manifest = ingest_path(inbox, store, limits=Limits.untrusted())
for row in manifest.rows:
    print(row.path, row.outcome, row.container_hash[:12])

# The manifest is stored beside the documents, keyed by its own content: read it back by value.
assert read_manifest(manifest_store("store"), manifest) == manifest
```

A row's `outcome` is `written` or `hit` (the store already held those bytes) or `skipped` with the
named reason (`file_over_cap`, `file_unreadable`, `not_a_message`, ...).

### Cite a span

<!-- example:cite-a-span -->

```python
from emailextract import assemble, resolve_span
from emailextract.container import EmlContainer, memory_bytes
from emailextract.parse import Limits

container = EmlContainer(memory_bytes(MESSAGE_BYTES))
document = assemble(container, limits=Limits.untrusted())

text_part = next(part for part in document.parts if part.content_type == "text/plain")
quote = next(
    boundary for boundary in document.quote_boundaries if boundary.span.end > boundary.span.start
)

# `resolve_span` maps a span of the *view text* back to raw bytes of the message, or refuses with
# a closed reason. It answers only where a within-part byte map exists.
span = resolve_span(container, text_part.part_id, "plain", quote.span.start, quote.span.end)
print("quote text at", (span.offset, span.offset + span.length), "locator", span.locator)
```

### Read a record: status, caps, tri-states and the not-built axes

<!-- example:read-a-record -->

```python
from emailextract import assemble
from emailextract.container import EmlContainer, memory_bytes
from emailextract.model import Status, TriState
from emailextract.parse import Limits

document = assemble(EmlContainer(memory_bytes(MESSAGE_BYTES)), limits=Limits.untrusted())

# The status is a closed nine-member set; a reason id is present only where the status needs one.
assert document.status.status is Status.PARSED

# A tri-state field is `value`, `absent` or `unknown` -- and an `unknown` always names a reason.
for header in document.headers:
    if header.value.state is TriState.UNKNOWN:
        print(header.name, "unknown:", header.value.reason_id)

# Axes this phase does not build are marked, never empty:
print("children axis:", document.children_axis.state.value, document.children_axis.reason_id)

# The quote rows: a boundary is a rule id plus a span in a named view; a view level is the depth.
for boundary in document.quote_boundaries:
    print("boundary", boundary.rule_id, boundary.kind.value, (boundary.span.start, boundary.span.end))
for level in document.view_levels:
    print("view level", level.view_id, level.quote_level)

# Caps are the caller's own: assemble at a deliberately small part cap and read them back.
tight = Limits(
    max_input_bytes=1 << 20,
    max_depth=4,
    max_parts=1,
    max_header_bytes=1 << 20,
    max_decoded_part_bytes=1 << 20,
    max_decoded_total_bytes=1 << 20,
    max_field_work_units_per_byte=64,
)
capped = assemble(EmlContainer(memory_bytes(MESSAGE_BYTES)), limits=tight)
print("caps:", [(cap.cap_id, cap.cap_value_bytes) for cap in capped.run_record.caps])
```

A `TriValue` is never an empty string standing in for "I don't know": `state` is the answer, `value`
is the reading, and `reason_id` is drawn from a closed table (`emailextract.model.REASON_TABLE`).

## Limits and the security posture

`Limits` (in `emailextract.parse`) is the caller's, with no defaults -- `Limits.untrusted()` is the
reviewed set for bytes from anywhere else. Every cap is enforced and **recorded**: a cap hit never
raises, never truncates silently, and never produces a part that looks complete. It leaves one
accounted region (whose `kind` is the cap's own closed reason) and one `CapRecord` on
`run_record.caps`, carrying your cap value. The five caps are `max_input_bytes`, `max_depth`,
`max_parts`, `max_header_bytes`, and the decoded-byte pair (`max_decoded_part_bytes` /
`max_decoded_total_bytes`).

**Do not raise `max_depth` on untrusted input.** The walker is iterative (no recursion, so no stack
overflow at any depth), but each nesting level scans its own body for its boundary, so wall time grows
with the **square** of the depth even though the walker's step counter is linear. At `Limits.untrusted()`
(`max_depth=16`) the cost is bounded and a deeper message is recorded as a `depth_cap`. Raised caps are
the caller's risk: on one development machine a nested `multipart/mixed` took about 2 s at 1,000
levels, 8 s at 2,000 and 33 s at 4,000 (measured, not a guarantee). A single-pass nested-boundary scan
is later work.

The posture the caps serve:

* **hostile input is measured, not trusted.** A part-count bomb, an enormous header block, 20,000
  levels of nesting and a decoy `data:` URI are recorded at the caps with a deterministic
  work-per-input-byte budget -- never in seconds;
* **nothing is fetched.** There is no socket, no HTTP client and no SSL anywhere in the package;
* **an attachment is never written under its raw filename.** A hostile `filename` (a path, a drive
  letter, a reserved Windows name, a right-to-left override) is recorded verbatim in the record and
  is never used as a path;
* **a citation is checked, not assumed.** `resolve_span` returns a refusal with a closed reason
  (`span_not_resolvable`) wherever the bytes cannot be mapped, rather than a plausible offset.

## Determinism

The record is a function of the input bytes and the caller's `Limits` -- nothing else. Two runs,
two `PYTHONHASHSEED` values, two locales, two time zones and the two pinned interpreters
(CPython 3.14 and 3.11) produce byte-identical documents under the **identity projection**
(`assemble.identity_projection`, which strips only the recorded-only `environment` and
`projection_versions`).

Three committed ledgers make that falsifiable rather than asserted:

* `tests/ledger/behavior_ledger.json` -- one fingerprint per behaviour component over the corpus,
  keyed by the version constant that names it. A behaviour change without a version bump makes
  `tools/update_behavior_ledger.py --check` exit 1 and name the constant;
* `tests/ledger/label_ledger.json` -- additions-only hashes over the hand-typed sidecars,
  `tests/support/**` and `emailextract/evals/**`;
* `tests/ledger/corpus.json` -- the corpus manifest, appended version by version.

Re-ingesting the same bytes is a no-op: the store writes nothing and the stored record wins.

## How an agent should use it

Read the **record**, not the message: call `assemble`, then cite with `resolve_span`. The record is
small, fixed-shape and safe to load whole; the message is not.

* **do not paste whole messages into context** -- the record's spans and its attachment manifest are
  what a citation needs, and they are small;
* **trust `unknown` over a blank.** A field is `value`, `absent` or `unknown`; `unknown` names why,
  and an axis marked `not_built_in_phase1` is a phase boundary, not a defect;
* **quote the span.** `resolve_span(container, part_id, view, start, end)` returns raw byte offsets
  you can show a reader, or a refusal you can report honestly;
* **re-ingest is cheap and safe.** Point `ingest_path` at a directory and read `read_manifest` back;
  unchanged bytes write nothing.

## The oracle and the gates

`python -m emailextract.evals` runs the phase-1 oracle over the committed corpus and prints the
gates:

```sh
python -m emailextract.evals
```

It reports the L1 comparison (matched / mismatched / unmeasurable), the no-silent-drop gate, the
phase-1 gap gate, the phase-1 exit accounting, the corpus census and the falsifiability summary.
A non-zero exit is a real disagreement, not a warning.

## Development

```sh
python -m venv .venv
.venv/Scripts/activate           # Windows;  source .venv/bin/activate  on Linux/macOS
pip install -e ../word-extract/docextract-core   # local first install of the one dependency
pip install -e ".[dev]"
```

```sh
python -m pytest                                   # green is the gate
python -m emailextract.evals                       # the oracle and the gates
python tools/update_behavior_ledger.py --check     # behaviour fingerprints must not move
python tools/update_label_ledger.py --check        # the additions-only label ledger
python tools/make_fixtures.py --check              # the generated corpus reproduces
```

**Never commit real email.** `fixtures/real/` is git-ignored and stays empty; the corpus is
self-generated and hand-labelled, and the labels are verified against the bytes.

## Licence

Apache-2.0 (`LICENSE`, `NOTICE`). No GPL, LGPL or AGPL dependency or licence claim exists anywhere in
the tree -- including the optional extras.
