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

OUTPUT_SCHEMA_VERSION: Final[str] = "4"
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
"""

TEXTMODEL_VERSION: Final[str] = "1"
"""Version of the text-model projection (union stream and views).

Moves when the text model's coordinate space or segmentation changes.
"""

HEADERTEXT_VERSION: Final[str] = "1"
"""Version of the header-text projection.

Moves when header rendering or normalization changes.
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
    projection="verbatim-non-style-script",
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
minor is one of the key's inputs and the lxml wheel is not. This constant ships here
**symbolically only**; the module the projection lives in (``htmltext.py``) is Turn 1.5,
and nothing emits output through this constant yet, so the behavior ledger keys nothing
by it.
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

EMAIL_PARSER_VERSION: Final[str] = "1"
"""Version of the email parser behavior.

Moves when the walker's output changes for unchanged input bytes.

(``EmailDocument`` and ``RunRecord`` default ``email_parser_version`` to this
constant. The contracts fingerprint hashes field defaults, but since Turn 0.5 it
records a version-constant default **symbolically** -- the constant's name, not
its value -- so bumping this is not a contract change. Before that it was: the
binary-part charset fix moved ``DECODE_CHAIN_VERSION`` to 2 and not this one for
exactly that reason.)
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
