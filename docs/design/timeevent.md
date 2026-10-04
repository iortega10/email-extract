# The TimeEvent shape -- FROZEN (Phase 0, Turn 0.6)

Status: **doc-frozen**. This is the shape D15 calls for; the code type lives in
`emailextract/timeevent.py` and is checked field-for-field against the machine-readable block
below by `tests/test_timeevent.py`, so the document cannot drift from the code. The type mirrors
`workbookextract/timeevent.py` (the second producer, its D10): neither package imports the other,
and the two are **shape-equal** (same dataclasses, same fields, same enums). Promotion to
`docextract-core` waits for a third producer or a cross-package consumer (D15).

Source of truth for the decisions: `docs/design/email-extraction-design.md` D15. This document
freezes the *shape* and the *rules* those decisions call for.

## 1. The shape

```json
{
  "shape": "TimeEvent",
  "version_constant": "TIMEEVENT_VERSION",
  "duplicated_on_purpose": true,
  "shared_reference": "email-extract docs/design/email-extraction-design.md D15; workbookextract/timeevent.py mirrors emailextract/timeevent.py. Neither package imports the other; promotion to docextract-core waits for a third producer or a cross-package consumer.",
  "dataclasses": {
    "Span": {
      "fields": ["start", "end"],
      "invariant": "0 <= start <= end; ints, never bools"
    },
    "TimeValue": {
      "fields": ["value", "unknown_reason"],
      "tri_state": true,
      "invariant": "exactly one of value|unknown_reason; both is an error, neither is an error; the present one is a non-empty str",
      "used_by": ["when_utc", "offset"]
    },
    "TimeSource": {
      "fields": ["ordinal", "field", "property", "part", "span"],
      "one_of": ["field", "property", "part"],
      "invariant": "ordinal is an int >= 0; exactly one of field|property|part is present"
    },
    "TimeEvent": {
      "fields": [
        "event_id",
        "doc_id",
        "kind",
        "when_raw",
        "when_utc",
        "offset",
        "offset_origin",
        "precision",
        "ambiguity",
        "source",
        "trust",
        "usable_for_arrival_ordering",
        "parent_event_id"
      ]
    }
  },
  "enums": {
    "OffsetOrigin": ["stated_in_text", "derived_by_named_rule", "absent"],
    "Precision": ["year", "month", "day", "second"],
    "Ambiguity": ["none", "day_month", "timezone", "relative"],
    "Trust": ["claimed", "derived", "user_supplied", "filesystem"]
  },
  "open_vocabularies": {
    "kind": {
      "closed": false,
      "shared_members": [
        "sent",
        "received_hop",
        "authored",
        "modified",
        "revision",
        "comment",
        "calendar_start",
        "calendar_end",
        "calendar_stamp",
        "mentioned_in_text",
        "fs_mtime",
        "..."
      ],
      "email_members": ["sent", "received_hop", "calendar_start", "calendar_end", "calendar_stamp", "mentioned_in_text", "fs_mtime"]
    }
  },
  "invariants": [
    "when_utc and offset are each a value OR an unknown with a named reason, never both and never neither",
    "a value type is a str; a time never travels as a JSON number",
    "a relative time carries when_utc = unknown(relative) and is never resolved",
    "offset_origin == absent requires offset to be unknown",
    "a filesystem time (trust == filesystem) is never usable_for_arrival_ordering",
    "the shape is emitted first by email-extract (email D15) and second by workbook-extract (design D10); no cross-import"
  ]
}
```

Field notes (one line each):

- `event_id` -- this claim's id (content-addressed when the producer can; non-empty).
- `doc_id` -- the message or document the claim belongs to.
- `parent_event_id` -- `null`, or another event's id; a claim can sit under another (e.g. a hop's
  chain parent).
- `kind` -- the open vocabulary of §3.
- `when_raw` -- the claimed timestamp **exactly as written**; never parsed into `when_utc`.
- `when_utc` -- a `TimeValue`: a canonical UTC string, or `unknown(reason)`.
- `offset` -- a `TimeValue`: the stated/derived offset, or `unknown`.
- `offset_origin` -- one of the three `OffsetOrigin` members.
- `precision` -- how fine the timestamp is; **ambiguity is not precision** (D15).
- `ambiguity` -- what is unresolved about the timestamp.
- `source` -- a `TimeSource`: which field/property/part, its ordinal and its span.
- `trust` -- who or what asserts the timestamp.
- `usable_for_arrival_ordering` -- whether any policy **may place** this event in an arrival order.
- the four enum fields (`offset_origin`, `precision`, `ambiguity`, `trust`) coerce from their string
  values at construction, so a value outside the vocabulary raises there, not only when a record is
  decoded from JSON.

## 2. The tri-state and the invariants ENFORCED at construction

`when_utc` and `offset` are each `TimeValue`, a **value OR an unknown with a named reason, never
both and never neither**. The invariants below are enforced in `__post_init__`, not merely
documented (`emailextract/timeevent.py`), so a record is canonical the moment it is built:

1. `TimeValue`: `value` and `unknown_reason` are mutually exclusive; one of them is required, and
   the present one is a non-empty string.
2. `Span`: `0 <= start <= end`, both ints, never bools.
3. `TimeSource`: `ordinal` is an int `>= 0`; **exactly one** of `field | property | part` is present.
4. `offset_origin == absent` requires `offset` to be `unknown`.
5. `ambiguity == relative` requires `when_utc` to be `unknown(reason)` -- a relative time is **never
   resolved**.
6. `trust == filesystem` forbids `usable_for_arrival_ordering` -- a filesystem time is never usable
   for arrival ordering (it is not arrival evidence, D15).

## 3. The open vocabulary of kinds

`kind` is an **open identifier-shaped vocabulary**, not a closed enum. The shared list ends in
`...`; a producer may add a kind, and a consumer must not assume it has seen every one. As of v1:

`sent`, `received_hop`, `authored`, `modified`, `revision`, `comment`, `calendar_start`,
`calendar_end`, `calendar_stamp`, `mentioned_in_text`, `fs_mtime`, `...`

**What email-extract emits in v1 (D15, evidence only):** every `Received` hop as `received_hop`
(with its header ordinal), the `Date` as `sent`, the minimal `.ics` timestamps as
`calendar_start`/`calendar_end`/`calendar_stamp`, in-text dates as `mentioned_in_text` (a
**separate** extractor that is **not in email v1**), and `fs_mtime` for a file's own mtime.

## 4. Facts that are NOT TimeEvents

**`SEQUENCE`, `UID` and `METHOD` are calendar facts, not TimeEvents.** They are recorded on the
calendar part; only `DTSTART/DTEND/DTSTAMP/CREATED/LAST-MODIFIED` emit events. A timestamp the
shape does not carry is never smuggled into a `TimeEvent`.

## 5. The three named policies, and the rule that NOTHING is implicit

There is **no privileged ordering and no default** (D15). `order(policies=[...])` requires the
caller to **name** the policies it wants: nothing runs by omission, so no order exists that a
caller did not ask for, and **every unresolved conflict is returned beside any order** whichever
policies ran. Evidence is never merged into one "true time".

The three named policies (their mechanics are frozen by the test-only evaluator,
`tests/support/timeline_ref.py`):

1. **`header_date_claimed`** -- orders the events that are usable for arrival ordering and carry a
   known `when_utc` by their claimed UTC (ties by event id). Everything else is reported
   `not_placed`; nothing is repaired into a time and nothing is sorted as epoch.
2. **`received_chain_header_order`** -- orders the `received_hop` events by **header order and never
   by timestamp** (the clock-skew fixture pins it), bottom-up: the last-listed `Received` is the
   first hop. Non-hop events are `not_placed`. Timestamps never reorder the chain.
3. **`owner_manifest`** -- returns the caller's labelled **total-order override** verbatim and
   reports the events it does not cover as `not_placed`. It is labelled distinctly as an override,
   **not** an evidence-ranked ordering: the owner may place what no evidence policy may.

`emailextract` ships **no** implementation of these policies in Phase 0: the evaluator is test-only
and is not the timeline layer. The read-only merge/query layer is `docextract-timeline`, a later
package, after Phase 3 and after a second producer exists (D15).

## 6. The conflict fixtures and the reference evaluator

The **five** conflict fixtures live under `fixtures/time/`: `date_before_hops`, `date_no_zone`,
`date_vs_mtime`, `future_date_in_text`, `received_clock_skew`. Each carries a hand-typed expected
artifact: the evidence listing in this shape, the order under each named policy, and the unresolved
pair list. They are checked by `tests/test_time_conflicts.py` against the **test-only** reference
evaluator `tests/support/timeline_ref.py` (which is not shipped and is not the timeline layer).

## 7. Version

The shape is versioned by `TIMEEVENT_VERSION` in `emailextract/versions.py` -- its **own** constant,
never the record's `OUTPUT_SCHEMA_VERSION`. It moves when this shape changes; that change never
bumps the record's schema version.
