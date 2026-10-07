# Changelog

All notable changes to `email-extract`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0 (2026-10-07)

The first public release: the **Phase 1 `.eml` parser** and the oracle that measures it. Everything
is deterministic -- no LLM, no clock, no network, no third-party runtime dependency beyond
`docextract-core`.

### What it delivers

* **The header projection** (`headers`): the raw fields with their verbatim spans, RFC 2047 encoded
  words, RFC 2231 parameters, and the decoded values as tri-states (`value` / `absent` / `unknown`,
  each `unknown` carrying a closed reason id).
* **Address and date readings** (`headers.addresses`, `headers.date`) as sparse, state-typed rows.
* **Per-part text** and the two body views: the plain view and an HTML projection with a
  node-to-span map, both as `body.text`, `body.cid_refs` and the view levels.
* **Quote boundaries and view levels** (`quote_boundaries`, `view_levels`): text and DOM families,
  each boundary carrying its rule id, kind, span, ordinal and prefix depth.
* **The attachment manifest** (`attachments`): occurrences with a raw and a decoded filename, a cid,
  a size, a sha256, a type verdict and a decorative hint -- a hostile filename is recorded verbatim
  and never used as a path.
* **`EmailDocument`** -- one self-contained, strictly-codec'd record per message -- plus the
  content-addressed store (`document_store`, `store_document`, `read_document`), the ingest manifest
  (`ingest_path`, `read_manifest`) and `resolve_span` for citing a view span back to raw bytes.
* **The caps and the security posture** (`Limits`, `Limits.untrusted()`): five enforced caps, each
  recorded as an accounted region and a `CapRecord`; nothing raises on input content; nothing is
  fetched.
* **The oracle and the gates**: `python -m emailextract.evals` runs the phase-1 L1 comparison, the
  no-silent-drop gate, the phase-1 gap gate and the phase-1 exit accounting over the committed
  corpus.

### Versions

The record is stamped by the constants in `emailextract/versions.py`; a reader needs them to know
what a record means.

| constant | value |
|---|---|
| `OUTPUT_SCHEMA_VERSION` | `5` |
| `EMAIL_PARSER_VERSION` | `2` |
| `DECODE_CHAIN_VERSION` | `2` |
| `QUOTE_RULES_VERSION` | `5` |
| `TEXTPART_VERSION` | `1` |
| `TEXTMODEL_VERSION` | `1` |
| `HEADERTEXT_VERSION` | `1` |
| `HTMLTEXT_SCHEMA` | `1` |
| `HTMLTEXT_VERSION` | `1+htmlparser+<cpython minor>+verbatim+drop=style,script,head,comment+noelementtext+recorded-not-closed` |
| `FLAG_SCHEMA_VERSION` | `1` |
| `TIMEEVENT_VERSION` | `1` |
| `MATCHER_VERSION` | `1` |

### Fixed

* **A part with no `Content-Type` is `text/plain` (RFC 2045 section 5.2).** The first release
  candidate (`0.1.0rc1`) was published **before** this fix, and it read such a part as media type
  `""`: the body got no quote analysis (`quote_boundaries`/`view_levels` were empty) and the content
  fingerprint was the digest of the empty string. A message that spells the default out (`Content-Type:
  text/plain; charset=us-ascii`) worked, so `MIME-Version: 1.0` alone changed nothing. Every stage now
  derives the media type through one helper (`emailextract/mediatype.py`), which supplies the RFC 2045
  section 5.2 default and the RFC 2046 section 5.1.5 `multipart/digest` child default
  (`message/rfc822`). The walker's recorded output is unchanged; the fix moves `QUOTE_RULES_VERSION`
  4 -> 5 and adds seven header-less fixtures to the corpus.

### Known limits

Straight from the Phase 1 report's "Not done" list:

* **Deep nesting is quadratic in wall time at raised caps.** The walker is iterative (no recursion) with
  a linear step counter, but each nesting level scans its body for its boundary: about 2 s at 1,000
  levels, 8 s at 2,000 and 33 s at 4,000 (one machine). `Limits.untrusted()` caps depth at 16; do not
  raise `max_depth` on untrusted input.
* **`.msg`/CFB is unsupported by design.** `parse` returns the named error `cfb_msg_unsupported`; the
  `.msg` reader is Phase 1b, and `olefile` is not a dependency of this release.
* **No threading and no time reconciliation.** The `children`, `thread_edges`, `times` and
  `same_message_candidates` axes ship present-but-empty, each marked `unknown(not_built_in_phase1)`.
* **The matcher is a stub** (`emailextract.seam`), and there is no query layer.
* **Sibling routing is a seam, not a build.** The `[word]`/`[form]` extras are optional and never
  imported; `import emailextract` succeeds with neither sibling installed.
* **Quote detection is English-first**, with named gaps (`body.html_quote_rule_gap`,
  `body.mixed_origin_quoting`, `headers.date_no_zone`, ...) rather than guesses.
* **Within-part spans are identity-CTE only.** A base64/quoted-printable within-part offset map is
  deferred to Phase 4; those parts are `part_level` with a named reason and no byte span.
* **`format=flowed` reflow is not built** (`body.flowed_reflow_unresolved` is recorded instead).
* **Eleven declared coverage floors are unmet by the committed corpus**, recorded as a finding and
  re-based (owner-signed) rather than lowered; the six named `phase1_exit` waits stay waits.
* **No real mail is probed.** `fixtures/real/` is empty and git-ignored; user feedback covers it.
