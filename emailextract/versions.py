"""Frozen version stamps for the email-extract contracts (Turn 0.1).

Each constant is stamped onto the artifacts its contract produces (D12: a record
or citation is meaningless without its versions). Every docstring names what
moves that constant; nothing else in the package bumps it.

Resolved ambiguity 2 (schema-version relationship): the core codec envelope's
``schema_version`` is the core's own and stays untouched; ``OUTPUT_SCHEMA_VERSION``
is an ordinary field of the record and part of every cache key.
"""

from __future__ import annotations

from typing import Final

OUTPUT_SCHEMA_VERSION: Final[str] = "2"
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
"""

TEXTMODEL_VERSION: Final[str] = "1"
"""Version of the text-model projection (union stream and views).

Moves when the text model's coordinate space or segmentation changes.
"""

HEADERTEXT_VERSION: Final[str] = "1"
"""Version of the header-text projection.

Moves when header rendering or normalization changes.
"""

HTMLTEXT_VERSION: Final[str] = "1"
"""Version of the HTML text projection.

Moves when HTML-to-text extraction changes.
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
