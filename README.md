# email-extract

Deterministic extraction from `.eml` (RFC 5322) and `.msg` (CFB) email files: headers,
body views, an attachment manifest, threading claims, flag/visibility sidecars, and
provenance -- as one self-contained `.json` sidecar per input file.

Status: **Phase 0 (Turn 0.1)**. The contract layer is frozen: the record shapes below are
implemented and tested today; the skeleton walker arrives in Turn 0.2.
Most section numbers resolve to `unknown("not_built_in_phase0")` until later turns -- that
is the intended behavior, not a defect.

## What it is (design D1-D16, docs/design/email-extraction-design.md)

| Section | Purpose |
| --- | --- |
| 1 (manifest) | identity, envelope, flags, failure, `runtime`, section table |
| 2 (body views) | rendered / plain / text (detached, each with its own text hash) |
| 3 (parts tree) | RFC 5322 / CFB trees, inline multipart, `ChildLink` edge types |
| 4 (attachments) | attachment *occurrence* manifest, md5/sha256, kind/route/placeholder |
| 5 (threads) | per-message `ThreadEdge` claims (`raw_header` is the source of truth) |
| 6 (times) | `TimeEvent` records (trace/tz, D15; shape frozen later) |
| 7 (visibility) | flag sidecar: frozen-empty `FlagSection` + `FlagHit` positives |
| 8 (claims) | `run_record`, `output_schema_version`, `exchange_route` |
| 9 (cross references) | `CrossReferenceClaim` (sibling routing boundary) |
| 10 (strict non-goals) | no decryption, archive, preview, MIME multipart, indexes, labels |
| D14 | container identity: kind, facts, hash, `content_fingerprint` |
| D15 | `TimeEvent` contract and the deferred timeline layer |
| D16 | empty alternatives and view selection |

## Install

```sh
# local first install: docextract-core ships in lockstep with word-extract
pip install -e ../word-extract/docextract-core
pip install -e .
pip install pytest
```

`olefile` is intentionally absent until Phase 1b (when the `.msg` reader lands); this
release has no third-party runtime dependency beyond `docextract-core`. Optional sibling
parsers install as extras -- `pip install -e ".[word]"` / `.[form]` -- and are only ever
invoked as an alternate route (embedded files with known roots), never imported by the
package itself: `import emailextract` must succeed with neither sibling present.

## Use

There is no extractor yet. Turn 0.2 adds the skeleton walker; until then the package ships the
frozen record contracts, the closed vocabularies and the version stamps, importable with no
sibling installed:

```python
from emailextract import Status, StatusOutcome, EncodingSource

StatusOutcome(status=Status.SKIPPED, reason="size_cap")   # a reason must belong to its status
```

## Record shapes (frozen in Turn 0.1)

`EmailDocument` is a versioned envelope -- `{"schema_version": "7", "record": {...}}`,
the shared core codec's envelope -- decoded strictly: **unknown keys raise**
(`CodecError`), so a drifted reader fails loudly instead of dropping a field
(word-extract's "unknown-key drops" pitfall). `output_schema_version` is an ordinary
field of the record (part of every cache key), separate from the envelope's codec
version; `TIMEEVENT_VERSION` is its own frozen constant (shape frozen here, value
semantics frozen in Turn 0.6), versioned independently of `output_schema_version`.

`status` is exactly nine members: `parsed, skipped, unsupported, not_installed, failed,
password_protected, encrypted, empty, truncated` -- `reason_id` is required exactly for
`skipped`, `failed`, and `truncated` and forbidden otherwise, drawn from the closed reason
table. `container_kind` records what was opened (`rfc822` / `cfb_msg`), `encoding_source`
where an 8-bit body's charset came from, and `classification_hint` the section-4 routing
hint.

## Development

```sh
python -m pytest            # green is the gate for every turn
```

Never commit real email: `fixtures/real/` is git-ignored, probes print structure only,
and no real message content is ever written to a test, a log or a commit. The test
fixtures under `fixtures/synthetic/` are self-generated; no real customer, third-party or
employer data is ever committed. The license is Apache-2.0 and no GPL dependency is
allowed anywhere in this repository, including optional extras and development
dependencies.
