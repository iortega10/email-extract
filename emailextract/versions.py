"""Frozen version stamps for the email-extract contracts (Turn 0.1).

Each constant is stamped onto the artifacts its contract produces (D12: a record
or citation is meaningless without its versions). Every docstring names what
moves that constant; nothing else in the package bumps it.

Resolved ambiguity 2 (schema-version relationship): the core codec envelope's
``schema_version`` is the core's own and stays untouched; ``OUTPUT_SCHEMA_VERSION``
is an ordinary field of the record and part of every cache key.
"""

from __future__ import annotations

import sys
from typing import Final

OUTPUT_SCHEMA_VERSION: Final[str] = "5"
"""Version of the output record shapes (EmailDocument and everything it carries).

Moves when a record's serialized shape changes in a way that invalidates cached
sidecars. It is an ordinary field of every document and is part of every cache
key; it never bumps the core codec envelope's ``schema_version``.

It is also the version the behavior ledger keys the ``contracts`` fingerprint by
(Turn 0.5): the fingerprint is over this package's own record shapes, so the
constant this package owns is the one that moves it.

2: Turn 0.5 added the child-result shape and the three-bucket citation
(``emailextract/siblings.py``): a sibling's stored result, the sibling-derived
``page_count``/``sheet_count`` facts, and the citation nesting (via / verbatim /
stamped). No existing record's fields changed.

3: Turn 0.6 added the matcher seam's contract records
(``emailextract/seam.py``): ``TextRun``, ``UnitLocation``, ``MatchUnit``,
``MatchRules``, ``TermList`` and ``TermHit``. The seam module joined the set the
ledger's contracts fingerprint hashes, so the fingerprint moved; no existing
record's fields changed and the walker's output did not move. Those records carry
their own matcher version, not this constant.

4: Turn 1.0b (Phase 1 contract turn) declared the not-built axis fields
(``AttachmentOccurrence.status_axis``/``route_axis`` and the four
``EmailDocument`` axes), turned the three type verdicts into ``TriValue``, added
the quote-boundary and view-level records, and replaced ``RunRecord``'s single
cap with a list of ``CapRecord``. The walker's output did not move.

5: Turn 1.9 (assemble, ingest, store) added the document's quote holder -- the
``EmailDocument.quote_boundaries`` and ``EmailDocument.view_levels`` rows the stage
already produced -- and the run record's ``projection_versions`` map, so the
documented record shapes moved and a cached sidecar is invalidated. No stage's
output moved: the walker, the decode chain and every measured fact are unchanged.
"""

TEXTMODEL_VERSION: Final[str] = "1"
"""Version of the text-model projection (union stream and views).

Moves when the text model's coordinate space or segmentation changes.
"""

HEADERTEXT_VERSION: Final[str] = "1"
"""Version of the header-text projection.

Moves when header rendering or normalization changes.
"""

TEXTPART_VERSION: Final[str] = "1"
"""Version of the per-part text projection (``emailextract/text.py``, Turn 1.4).

Moves when the part's decoded text changes for unchanged body bytes: the strict/fallback
decode rule, the RFC 3676 space-unstuffing rule, the ``format=flowed`` detection, or the
charset alias table's canonicalisation. The offset map's *coordinate space* (the part's
decoded code points, un-normalised) moving would move this too, because the text and the map
are one projection.

Nothing emits output through this constant yet: ``text.py``'s records are internal to the
package (like ``headers.HeaderRegion``), so no contract record and no behavior-ledger line
keys on it. It ships so a later turn that *does* stamp a citation with the projection has the
constant already owned by the module that defines the projection.
"""

QUOTE_RULES_VERSION: Final[str] = "5"
"""Version of the quote stage's rules (``emailextract/quote``, Turn 1.6).

Moves when the rule tables, a span convention, or the level rule changes: the closed
label heads and their languages (``quote/i18n.py``), which shapes count as a block, the
signed span conventions of the ``quote_boundaries`` rows (a run to the end of the part
keeps its final terminator, an attribution carries the block that follows it, the
Outlook block runs on), the ordinal rule (only a quote advances it) and the derived
per-view level with its resolution rule. A pure refactor that changes none of those does
not move it.

**"2" (Turn 1.6b)** moves it on the reviewer's adjudication (build-spec decisions 33-39):
the walker's physical lines with no phantom trailing line; a span that ends before another
boundary or before a blank line ends at its last non-blank content line; an attribution's
span is its lines plus the contiguous non-blank block that follows; a ``>`` run inside an
attribution's or a flat block's span is part of that boundary (one quote, one ordinal); the
Outlook flat block's extent ends before the next boundary of any kind; the resolution rule is
the first structural quote boundary's, else ``gt_family``, else the first boundary of any kind;
and a view with **any** recognised boundary has a ``body.view_levels`` row.

**"3" (Turn 1.7)** moves it for the **DOM family and the html view** (``quote/dom_rules.py``):
the DOM rule table (``gmail_quote`` on a ``div`` or a ``blockquote`` by class token,
``blockquote[type=cite]``, Outlook ``divRplyFwdMsg``/``appendonsend`` with the ``x_`` form,
Thunderbird ``moz-cite-prefix``/``moz-forward-container``), the nesting/absorption rule (a quote
container inside another quote boundary's span is one ordinal; a forward container does not
suppress one), the Outlook span convention (the marker plus its following siblings to its
parent's projected end; **amended in "4"**), the Thunderbird prefix-plus-blockquote span, the
vendor-family gap
trigger and the absence answer, and the html view's own per-view level, resolution rule and
disagreement over the projection's physical lines.

**"4" (Turn 1.7b)** moves it for the reviewer's adjudication of the eight html
``body.quote_boundaries`` mismatches against the bytes (build-spec decisions 40-42, amended in
place): a DOM boundary's span is the element's projected extent **exactly**, with no
final-terminator extension (the clause is the line-based families', the plain view's rules and
the html view's ``gt_family``); ``divRplyFwdMsg`` is its own extent while ``appendonsend`` is a
**sentinel** whose span starts at its first following element sibling and ends at its parent's
projected extent (its own extent when there is no following element sibling); and a
``moz-cite-prefix`` pulls in its following element sibling when that sibling is a ``blockquote``,
**with or without** ``type=cite``. The forward container's span is decision 28's, unchanged. The
projection's own constant does not move: only these DOM span conventions changed.

**"5" (Turn 1.12)** moves it because the stage now **scans a header-less text part**: a part
that declares no ``Content-Type`` is ``text/plain`` by default (RFC 2045 5.2) and receives the
same plain-view quote analysis an explicit ``text/plain`` part gets. Before, the stage computed a
part's media type from the raw field with a fallback to the empty string, so a header-less part
read as ``""``, no ``text/plain`` view existed and its quote boundaries and view levels were empty. The
rule table, the span conventions and the level rule are unchanged; only *which parts the stage
reads* moved, and that is a change in the stage's output for header-less messages. No record shape
moved and the walker's bytes did not move.

The walker's parser and decode-chain constants do **not** move with it: this stage reads
the decoded text the body stage already produced and adds no decode rule, so a quote-rule
change cannot move a corpus fingerprint keyed by the walker. The html-text projection's own
constant does not move either: the DOM rules read the tree's node-to-span map and change no
projection.
"""

HTMLTEXT_SCHEMA: Final[str] = "1"


def _htmltext_version_key(
    *, candidate: str, cpython: str, projection: str, unclosed: str
) -> str:
    """The deterministic HTML-text projection key (Turn 1.0d, decision 1).

    The key is a pure function of four recorded inputs: the **parser candidate**
    (``htmlparser`` for the stdlib tree, or the lxml route), the **interpreter or
    wheel** the projection ran under (the CPython ``major.minor`` for the stdlib
    candidate, the pinned lxml wheel / libxml2 for the lxml route), the **projection
    whitespace rule** and the **unclosed-container rule**. Changing any one moves the
    constant, so a reader can see exactly what a projection was rendered by.
    """
    return "+".join((HTMLTEXT_SCHEMA, candidate, cpython, projection, unclosed))


HTMLTEXT_VERSION: Final[str] = _htmltext_version_key(
    candidate="htmlparser",
    cpython=".".join(str(part) for part in sys.version_info[:2]),
    projection="verbatim+drop=style,script,head,comment+noelementtext",
    unclosed="recorded-not-closed",
)
"""Version of the HTML text projection (the key of its four recorded inputs).

Moves when the parser candidate changes (the stdlib tree versus the lxml route), when
the interpreter or wheel the projection ran under changes -- the CPython ``major.minor``
for the stdlib candidate, or the pinned lxml wheel with its libxml2 for the lxml route
-- when the projection whitespace rule changes, or when the unclosed-container rule
changes. A pure refactor of the projection that changes none of those does not move it.

Turn 1.0d recorded the HTML parser decision as the experiment in
``docs/design/html-parser-experiment.md``: the stdlib tree was chosen, so the CPython
minor is one of the key's inputs and the lxml wheel is not.

Turn 1.5 built ``htmltext.py``, the module the projection actually lives in, and moved
the ``projection`` input from the experiment's ``verbatim-non-style-script`` to the
projection's three stated rule ids (``htmltext.PROJECTION_RULE_ID``): the whitespace rule
(``verbatim``, text nodes uncollapsed), the dropped set
(``drop=style,script,head,comment``) and the block rule (``noelementtext``, no element
inserts a character). The frozen ``body.html_spans`` labels decide the whitespace and
block halves: an open ``<p>`` and an ``<img>`` add nothing while the trailing ``\\r\\n``
counts, so a collapse or block-newline rule would contradict them. The parser tree
(``htmltree.py``) and the unclosed rule are unchanged from Turn 1.0d; nothing emits output
through this constant yet, so the behavior ledger keys nothing by it.
"""

DECODE_CHAIN_VERSION: Final[str] = "2"
"""Version of the decode chain (declared/used CTE and charset, fallback rules).

Moves when the decode rules or their recorded fields change.

2: the charset ladder runs only over text parts (no Content-Type, or ``text/*``). Before, a binary
part (pdf, png, an office zip) was given a ``used_charset``, an encoding source, a possible
``fallback_fired`` and a false ``body.decode_destroyed_bytes`` for content that was never text.
"""

FLAG_SCHEMA_VERSION: Final[str] = "1"
"""Version of the FlagSection/FlagHit shape -- a three-package contract
(email-extract, word-extract, form-extract).

Frozen in Phase 0; moves only by three-package agreement.
"""

TIMEEVENT_VERSION: Final[str] = "1"
"""Version of the TimeEvent shape (D15, emailextract/timeevent.py).

Moves when that shape changes.
"""

EMAIL_PARSER_VERSION: Final[str] = "2"
"""Version of the email parser behavior.

Moves when the walker's output changes for unchanged input bytes.

(``EmailDocument`` and ``RunRecord`` default ``email_parser_version`` to this
constant. The contracts fingerprint hashes field defaults, but since Turn 0.5 it
records a version-constant default **symbolically** -- the constant's name, not
its value -- so bumping this is not a contract change. Before that it was: the
binary-part charset fix moved ``DECODE_CHAIN_VERSION`` to 2 and not this one for
exactly that reason.)

2: Turn 1.1 tolerates a leading UTF-8 BOM and/or an mbox ``From `` line as its own
``prelude`` region (decision 14) instead of reading it as a malformed first field, so
the walker's regions and the top-level part's header span move for a message with a
BOM or an mbox line -- the two corpus-3-and-later inputs ``leading_utf8_bom`` and
``mbox_from_line_at_zero``. The decode chain is unchanged.
"""

MATCHER_VERSION: Final[str] = "1"
"""Version of the matcher seam's stub behavior (``emailextract/seam.py``, D8).

Moves when the stub's own matching behavior changes: what it searches, how it
bounds a token, how it orders hits. It is the stub's own constant, kept separate
from every other version constant because the real matcher is a separate track
(track S, in ``docextract_core.match``) with its own constant of the same name
that moves when the shared matcher moves. Every seam record is stamped with it,
never with the output record's version.
"""
