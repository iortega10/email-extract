"""Turn 1.8: the attachment manifest -- occurrences, identity, classification, verdicts, hints.

An **occurrence** is one attachment part in one message: a leaf MIME part that is *not* a
body view (:func:`emailextract.selection.is_body_view`: a ``text/*`` leaf, or a leaf that
declares no ``Content-Type`` outside a ``multipart/digest``, is a view, never an attachment)
and not a multipart container. A ``message/rfc822`` part **is** an occurrence and is
**recorded, never recursed** (Phase 1 does not descend into it). Two parts with the same
filename in one message are two occurrences; the same bytes under two filenames are one
identity and two occurrences (:data:`GAP_ATTACH_OCCURRENCE_REPEATED`).

Identity is the sha256 of the **decoded payload bytes**, which is the walker's own
``part.body_sha256`` -- reused, never recomputed as a different hash -- and never the path or
the filename (a path is a non-stable locator, D12).

Classification is D4's axis and comes from ``Content-Disposition`` and the filename only:
``attachment`` (a disposition of ``attachment``, or no disposition at all *with* a filename),
``inline`` (a disposition of ``inline``), else ``unknown`` (D4: "genuinely undeterminable").
It is never derived from size or content (D6: "status is never derived from classification and
never from size"). The manifest's ``disposition`` **column** is the header's own disposition
token (``null`` when the part carries no ``Content-Disposition``): the two are separate axes,
which is what the frozen ``attach_message_rfc822_no_filename`` sidecar types.

The three type verdicts (decision 6, D4) are :class:`~emailextract.model.TriValue`:
``declared_mime`` (the media type the part's ``Content-Type`` writes, parameters dropped),
``magic`` (a match on the closed table below, the sentinel ``VALUE("unrecognized")`` when the
table was **consulted** and nothing matched, or ``UNKNOWN(reason)`` when it could **not** be
computed) and ``container_introspection`` (always ``UNKNOWN(not_built_in_phase1)`` in Phase 1).
The winner and the disagreement are the model's pure functions
(:func:`~emailextract.model.type_winner`, :func:`~emailextract.model.type_disagreement`),
called, never reimplemented.

**Finding (the declared media type; the bytes are the judge).** The turn brief says the
``declared_mime`` verdict is lowercased. The walker lowercases ``part.content_type`` and the
frozen ``part.tree`` labels type that lowercased form, but the frozen ``attach_macro_docm``
``attach.manifest`` row types ``application/vnd.ms-word.document.macroEnabled.12`` -- the case
the ``Content-Type`` header **writes**. The verdict (and so the manifest column, D4: "the
projected value of the verdict") is therefore taken from the raw field value: bytes beat a
normalisation nothing froze.

**Finding (the disagreement set).** Decision 6 and the brief say the disagreement fires iff at
least two ``VALUE`` verdicts name a media-type family and the families number >= 2, and the model's
:func:`~emailextract.model.type_disagreement` implements that over the verdicts' **subtypes**.
Two frozen labels show that reading firing where the bytes do not support a contradiction:
``attach_ole_cfb_magic``'s ``attach.types`` row (declared ``application/octet-stream``, magic
``ole-cfb``, ``disagreement`` **false**) and ``attach_macro_docm``'s ``gaps.later`` (declared
``application/vnd.ms-word.document.macroEnabled.12``, magic ``zip``, and **no**
``attach.type_disagreement`` row, while ``attach_zip_magic_declared_disagree`` -- declared
``application/pdf``, magic ``zip`` -- does type one). One reading reproduces every frozen row and
D4's own example (``declared_mime=text/plain`` with a ``PK\\x03\\x04`` prefix *is* a disagreement):
the verdicts are compared at the **container** level D4 discusses ("DOCX/XLSX/PPTX are all zip and
``.xls``/``.doc``/``.msg`` are all OLE-CFB"). So
:func:`container_family` maps the model's family through two closed declared-media-type tables --
a declared OOXML type names the zip container it *is*, a declared ``.doc``/``.xls``/``.msg`` type
names OLE-CFB -- and a generic ``application/octet-stream`` claim, which names no specific type,
names no family and so **cannot contradict** anything. :func:`disagrees` then applies the model's
own set rule (>= 2 families). Recorded as build-spec decision 25 and reported as a finding; no
label was edited and the model was not changed.

The magic decision reads the **first :data:`MAGIC_PREFIX_BYTES` bytes** of the decoded payload
(a bounded read, never the whole part), and the closed table is hand-typed here, one comment per
signature naming its source. Deliberately **excluded** (decision 7): WebP and WAV/AVI (``RIFF``
needs bytes 8-11), TIFF, ``.ics`` and ``.eml`` (text) and any text sniffing; ``.msg`` is OLE-CFB
and needs no row. A zip is never guessed to be a docx/xlsx (family ``zip`` only).

The magic verdict's not-computed reasons are the closed :data:`MAGIC_NOT_COMPUTED_REASONS`, and
they are **not** gap ids, **not** status reasons and **not** in the gap registry -- they are the
closed reason ids of this one ``TriValue`` (build-spec decision 25):

* :data:`MAGIC_SKIPPED_CAP` -- the walker skipped the part for a size cap: nothing was decoded,
  so nothing can be sniffed (item 7);
* :data:`MAGIC_UNDECODABLE` -- the part has body bytes and the transfer decode produced none;
* :data:`MAGIC_ENCRYPTED` -- the bytes are known to be encrypted and unreadable. Phase 1 has no
  encrypted-OOXML detection (the bounded prefix check the design names needs the introspection
  decision 6 defers), so the id is **defined and never emitted**, with a test;
* :data:`MAGIC_EMPTY` -- a zero-length body decoded fine and there are no bytes to sniff. It is
  ``UNKNOWN(magic_body_empty)``: not ``unrecognized`` (bytes were consulted and nothing matched)
  and not ``absent`` (the part has an own body). The plan debate's earlier row said a
  zero-length leaf is consulted and ``UNRECOGNIZED``; the owner-delegated decision recorded in
  build-spec decision 25 replaces that for this turn.

**Size caps are the walker's** (Turn 1.5c, commit ``45a4c91``): ``walk()`` enforces
``Limits.max_decoded_part_bytes`` / ``max_decoded_total_bytes`` while it decodes, records one
:class:`~emailextract.walk.Region` whose ``kind`` **is** the closed cap reason and one
:class:`~emailextract.walk.UnknownSection` for the skipped locator, and leaves
``part.body_sha256 = None``. This module enforces **no** cap of its own and truncates nothing:
it *consumes* that channel -- the occurrence is still listed, its content sha256 is the walker's
unknown (``None``), its decoded size is unknown (the walker records no decoded size for a
skipped part; it records the *raw* span, which is not this column's unit), its magic verdict is
``UNKNOWN(magic_part_skipped_cap)``, and its ``declared_mime`` verdict is read from the headers
as usual. The cap hit is returned alongside as :class:`CapSkip`, so Turn 1.9's manifest/status
layer can build the run's cap records: ``cap_id`` is the reason, ``cap_value_bytes`` is the
caller's own ``Limits`` field and ``declared_size`` is the skipped region's span length. The
``limits`` parameter exists **only** to re-state that value -- it may be ``None`` (an unbounded
walk, which can hit no cap) and it never decides anything.

**The decorative hint is a hint, never a removal** (D4): every occurrence is always present, in
the manifest, in ``attach.types`` and in ``attach.cid_use``.

.. rubric:: Gaps this module emits

* :data:`GAP_ATTACH_FILENAME_ABSENT` -- a ``message/rfc822`` occurrence with no filename and
  none derivable. It is keyed on the **declared** ``message/rfc822``: a digest child that
  declares no ``Content-Type`` is its own recorded gap (``body.digest_default_not_applied``),
  never this one;
* :data:`GAP_ATTACH_TYPE_DISAGREEMENT` -- the disagreement derivation above fired;
* :data:`GAP_ATTACH_DUPLICATE_CONTENT_ID` -- two occurrences carry the same ``Content-ID`` (the
  one gap id this turn first emits): both occurrences and both cids are kept, and the locator is
  the comma-joined occurrence paths;
* :data:`GAP_ATTACH_OCCURRENCE_REPEATED` -- two occurrences share one content sha256 (one
  identity, two occurrences, never merged; D4/D12);
* :data:`GAP_ATTACH_CID_UNREFERENCED` -- an **inline** occurrence whose cid no view references
  (D4: inline only);
* :data:`GAP_ATTACH_TNEF_PRESENT` -- the decoded payload begins with the TNEF signature
  ``78 9F 3E 22``: recorded, **never** unpacked;
* :data:`GAP_ATTACH_OLE_CONTAINER_UNKNOWN` -- the magic verdict is OLE-CFB and Phase 1 has no
  introspection;
* :data:`GAP_SECURITY_MACRO_PRESENT` -- a ``.docm``/``.xlsm`` container filename beside zip
  magic: recorded, **never** opened or executed (D10). The frozen ``attach_macro_docm`` row
  types this id, not ``attach.macro_present_inert``, so only this one is emitted.

**``attach.cid_dangling`` is measured and not emitted** (a finding of its own: it is the one gap id
whose frozen corpus cannot carry it). ``attach_cid_dangling`` types the row -- a view references a
cid no part's ``Content-ID`` carries, locator the **referencing part's** path -- but
``html_href_img_remote_and_cid`` references ``cid:logo@example.test`` with no matching part too
(its own ``not_yet_labelled`` annotation names "the Family C ``attach_cid_dangling`` case") and
types **no** such row, and the oracle compares ``gaps.later`` exactly over live ids for every
sidecar that labels it: emitting the row anywhere is a mismatch against a frozen label, which is
never edited. So the dangling cids are carried on
:attr:`Attachments.dangling` (measured, and pinned by a test) while :func:`_gaps` emits no pair for
them, and the row ``attach_cid_dangling`` types stays ``not_yet`` for its turn.

Registered ids this module **defines but never emits**, each because the frozen corpus types no
row for it *and* the rule that would fire it also fires inside a fixture whose ``gaps.later`` is
typed without that row (emitting it would contradict a frozen label):
:data:`GAP_ATTACH_ZIP_UNEXPANDED` (``attach_zip_magic_declared_disagree`` types only
``attach.type_disagreement`` while its part's magic is ``zip``),
:data:`GAP_ATTACH_DISPOSITION_ABSENT`, and :data:`GAP_ATTACH_FILENAME_UNPARSABLE` (every
committed filename parameter decodes: the continuation pair and the empty-charset fallback both
yield a value). The registry's read-only-detection ids
(``attach.encrypted_ooxml``, ``attach.legacy_office_password``) are not named here at all: no
sidecar types them and no detection exists in this turn.

The decorative rule (D4, the undetermined entry 6 the Turn 1.0c review left open, decided here
by recommendation and recorded as build-spec decision 25):
:data:`HINT_INLINE_UNREFERENCED_TRACKING_PIXEL` fires iff the occurrence is **inline**, its cid
is **unreferenced**, its magic verdict is ``png`` or ``gif`` (never ``jpeg``: JPEG dimensions
are not read at all), and the image's declared pixel dimensions in the **first
:data:`IMAGE_HEADER_BYTES` bytes** are exactly 1 x 1 (a PNG ``IHDR`` width/height at bytes
16-23, a GIF logical screen width/height at bytes 6-9 little-endian).
:data:`HINT_INLINE_UNREFERENCED_SMALL_IMAGE` is the **empty** closed set in Phase 1 -- no size
threshold is fixed by the design -- so the id is in the vocabulary, never fires, and a test
asserts it never fires. A referenced image is never a hint, a non-inline image is never a hint
and nothing is hinted from size alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Final, Mapping, Sequence

from . import text as text_stage
from .model import (
    UNRECOGNIZED,
    AttachmentOccurrence,
    Classification,
    DecorativeHint,
    DecorativeHintState,
    TriState,
    TriValue,
    TypeVerdicts,
    not_built_in_phase1,
    type_family_of,
    type_winner,
)
from .rfc2231 import parse_parameters
from .selection import cid_ref_rows, dangling_and_unreferenced, is_body_view
from .walk import (
    CAP_LIMIT_FIELDS,
    CAP_REASON_SIZE,
    CAP_REASON_TOTAL_SIZE,
    PartShape,
    WalkResult,
)

__all__ = [
    "Attachments",
    "CapSkip",
    "CID_USE_STATES",
    "DEFINED_NOT_EMITTED_GAP_IDS",
    "EMITTED_GAP_IDS",
    "FILENAME_DECODE_STATES",
    "GAP_ATTACH_CID_DANGLING",
    "GAP_ATTACH_CID_UNREFERENCED",
    "GAP_ATTACH_DISPOSITION_ABSENT",
    "GAP_ATTACH_DUPLICATE_CONTENT_ID",
    "GAP_ATTACH_FILENAME_ABSENT",
    "GAP_ATTACH_FILENAME_UNPARSABLE",
    "GAP_ATTACH_OCCURRENCE_REPEATED",
    "GAP_ATTACH_OLE_CONTAINER_UNKNOWN",
    "GAP_ATTACH_TNEF_PRESENT",
    "GAP_ATTACH_TYPE_DISAGREEMENT",
    "GAP_ATTACH_ZIP_UNEXPANDED",
    "GAP_SECURITY_MACRO_PRESENT",
    "GENERIC_MEDIA_TYPE",
    "HINT_INLINE_UNREFERENCED_SMALL_IMAGE",
    "HINT_INLINE_UNREFERENCED_TRACKING_PIXEL",
    "HINT_RULES",
    "IMAGE_HEADER_BYTES",
    "MAGIC_EMPTY",
    "MAGIC_ENCRYPTED",
    "MAGIC_NOT_COMPUTED_REASONS",
    "MAGIC_PREFIX_BYTES",
    "MAGIC_SKIPPED_CAP",
    "MAGIC_TABLE",
    "MAGIC_UNDECODABLE",
    "OLE_CONTAINER_MEDIA_TYPES",
    "TNEF_SIGNATURE",
    "ZIP_CONTAINER_MEDIA_TYPES",
    "attachments",
    "cid_use_rows",
    "container_family",
    "decoded_payload",
    "decorative_rows",
    "disagrees",
    "filename_rows",
    "gap_pairs",
    "is_attachment_part",
    "magic_name",
    "manifest_rows",
    "normalized_cid",
    "read_prefix",
    "type_rows",
]

# --------------------------------------------------------------- the magic table

#: The bounded read every magic decision is made from, and the bound the fuzz instruments:
#: the table's longest signature is 8 bytes (PNG), so 16 is comfortable and fixed.
MAGIC_PREFIX_BYTES: Final[int] = 16

#: The bounded read the *decorative* image-header check is made from: a PNG ``IHDR``
#: width/height sits at bytes 16-23, so 24 bytes is the whole of it (a GIF's needs only 10).
IMAGE_HEADER_BYTES: Final[int] = 24

#: The closed magic table: ``(name, signatures)`` in the spec's own order (decision 7). One
#: comment per row names the signature's source. A signature is a byte prefix of the decoded
#: payload; the first matching row in this order wins (no two rows can overlap).
MAGIC_TABLE: Final[tuple[tuple[str, tuple[bytes, ...]], ...]] = (
    # PKWARE APPNOTE.TXT 4.3.6: a local file header begins "PK\003\004". The design lists only
    # this form: the empty-archive "PK\005\006" end-of-central-directory and the "PK\007\008"
    # spanning record are *not* listed, so an empty archive reads as unrecognized, which is
    # honest rather than a guess.
    ("zip", (b"PK\x03\x04",)),
    # MS-CFB 2.2: the compound file binary header signature (the design's D4 row; a `.msg` is
    # this container and needs no row of its own).
    ("ole-cfb", (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)),
    # PDF 32000-1 7.5.2: the file header line is "%PDF-" followed by the version.
    ("pdf", (b"%PDF-",)),
    # PNG (second edition) 5.2: the 8-byte signature, CRLF and SUB-LF included.
    ("png", (b"\x89PNG\r\n\x1a\n",)),
    # JPEG/JFIF: the two-byte SOI marker followed immediately by any marker's 0xFF byte (a JFIF
    # APP0 segment is 0xFFD8FFE0), so the three-byte prefix is the shortest unambiguous one.
    ("jpeg", (b"\xff\xd8\xff",)),
    # GIF89a specification 17 (and its 87a predecessor): the six-byte versioned header.
    ("gif", (b"GIF87a", b"GIF89a")),
    # RTF 1.9.1: an RTF file begins "{\rtf" plus a version digit, which is not part of the row.
    ("rtf", (b"{\\rtf",)),
    # RFC 1952 2.3.1: the gzip member header's ID1 / ID2 / CM octets.
    ("gzip", (b"\x1f\x8b\x08",)),
    # The 7-Zip archive format's signature header: 37 7A BC AF 27 1C.
    ("7z", (b"7z\xbc\xaf'\x1c",)),
    # The RAR technote's 4-byte marker is shared by RAR 4 (the 5th byte 0x00) and RAR 5 (the 5th
    # byte 0x01 and a 6th 0x00), so this one prefix covers both variants the design lists.
    ("rar", (b"Rar!\x1a\x07",)),
)

#: The magic verdict's **not-computed** reasons: a closed tuple of this ``TriValue``. They are
#: not gap ids, not status reasons and not in the gap registry (build-spec decision 25).
MAGIC_SKIPPED_CAP: Final[str] = "magic_part_skipped_cap"
MAGIC_UNDECODABLE: Final[str] = "magic_body_undecodable"
MAGIC_ENCRYPTED: Final[str] = "magic_body_encrypted"
MAGIC_EMPTY: Final[str] = "magic_body_empty"
MAGIC_NOT_COMPUTED_REASONS: Final[tuple[str, ...]] = (
    MAGIC_SKIPPED_CAP,
    MAGIC_UNDECODABLE,
    MAGIC_ENCRYPTED,
    MAGIC_EMPTY,
)

#: The generic opaque media type: a claim of no specific type, which cannot contradict the bytes.
GENERIC_MEDIA_TYPE: Final[str] = "application/octet-stream"

#: The declared media types whose **container is a zip**: D4's own sentence, "DOCX/XLSX/PPTX are
#: all zip". A declared OOXML type and zip magic therefore name the *same* container family and
#: cannot be a disagreement (the frozen macro-bearing-container sidecar is the row that fixes
#: this). The mapping is a **container-level** claim -- Phase 1 identifies the container, never the
#: document inside it (that is Phase 2's introspection, decision 6) -- so no docx/xlsx is ever
#: *inferred* from it and ``magic`` still reads ``zip``.
ZIP_CONTAINER_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/zip",
        "application/x-zip-compressed",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.presentationml.template",
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/vnd.ms-excel.template.macroenabled.12",
        "application/vnd.ms-word.document.macroenabled.12",
        "application/vnd.ms-word.template.macroenabled.12",
        "application/vnd.ms-powerpoint.presentation.macroenabled.12",
        "application/vnd.ms-powerpoint.template.macroenabled.12",
    }
)

#: The declared media types whose **container is an OLE-CFB**: D4's "``.xls``/``.doc``/``.msg``
#: are all OLE-CFB", on the same container-level reading as the zip set above.
OLE_CONTAINER_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.ms-outlook",
        "application/x-ole-storage",
    }
)

#: The container family a declared media type names, read off the two tables above.
_CONTAINER_BY_MEDIA_TYPE: Final[Mapping[str, str]] = MappingProxyType(
    {
        **{media_type: "zip" for media_type in ZIP_CONTAINER_MEDIA_TYPES},
        **{media_type: "ole-cfb" for media_type in OLE_CONTAINER_MEDIA_TYPES},
    }
)

#: The TNEF encapsulation signature (``78 9F 3E 22``): recorded, never unpacked (D4/D9).
TNEF_SIGNATURE: Final[bytes] = b"\x78\x9f\x3e\x22"

#: The macro-bearing OOXML container extensions (D4/D10): matched on the **container filename**
#: beside zip magic, and the document is never opened.
_MACRO_EXTENSIONS: Final[tuple[str, ...]] = (".docm", ".xlsm")

# ------------------------------------------------------------------- the gaps

GAP_ATTACH_CID_UNREFERENCED: Final[str] = "attach.cid_unreferenced"
GAP_ATTACH_CID_DANGLING: Final[str] = "attach.cid_dangling"
GAP_ATTACH_DUPLICATE_CONTENT_ID: Final[str] = "attach.duplicate_content_id"
GAP_ATTACH_OCCURRENCE_REPEATED: Final[str] = "attach.occurrence_repeated"
GAP_ATTACH_FILENAME_ABSENT: Final[str] = "attach.filename_absent"
GAP_ATTACH_FILENAME_UNPARSABLE: Final[str] = "attach.filename_unparsable"
GAP_ATTACH_DISPOSITION_ABSENT: Final[str] = "attach.disposition_absent"
GAP_ATTACH_TYPE_DISAGREEMENT: Final[str] = "attach.type_disagreement"
GAP_ATTACH_TNEF_PRESENT: Final[str] = "attach.tnef_present"
GAP_ATTACH_OLE_CONTAINER_UNKNOWN: Final[str] = "attach.ole_container_unknown"
GAP_ATTACH_ZIP_UNEXPANDED: Final[str] = "attach.zip_unexpanded"
GAP_SECURITY_MACRO_PRESENT: Final[str] = "security.macro_present"

#: The gap ids this module can actually emit, in the order :func:`_gaps` builds them. A test
#: holds the module's ``GAP_*`` constants against this tuple plus
#: :data:`DEFINED_NOT_EMITTED_GAP_IDS` in both directions, so a new constant cannot be
#: forgotten, and the mutation catalogue is keyed by it.
EMITTED_GAP_IDS: Final[tuple[str, ...]] = (
    GAP_ATTACH_FILENAME_ABSENT,
    GAP_ATTACH_TYPE_DISAGREEMENT,
    GAP_ATTACH_OLE_CONTAINER_UNKNOWN,
    GAP_SECURITY_MACRO_PRESENT,
    GAP_ATTACH_DUPLICATE_CONTENT_ID,
    GAP_ATTACH_OCCURRENCE_REPEATED,
    GAP_ATTACH_CID_UNREFERENCED,
    GAP_ATTACH_TNEF_PRESENT,
)

#: The registered ids this module defines and never emits (see the module docstring).
DEFINED_NOT_EMITTED_GAP_IDS: Final[tuple[str, ...]] = (
    GAP_ATTACH_CID_DANGLING,
    GAP_ATTACH_FILENAME_UNPARSABLE,
    GAP_ATTACH_DISPOSITION_ABSENT,
    GAP_ATTACH_ZIP_UNEXPANDED,
)

#: ``attach.filename``'s closed ``decode_state`` vocabulary (the facts document). ``absent`` is
#: in the vocabulary and is never emitted: an occurrence with no filename has no row at all.
FILENAME_DECODE_STATES: Final[tuple[str, ...]] = ("decoded", "fallback", "absent", "unparsable")

#: ``attach.cid_use``'s closed ``referenced`` vocabulary.
CID_USE_STATES: Final[tuple[str, ...]] = ("referenced", "unreferenced", "n/a")

#: The decorative rule vocabulary (D4): one rule that fires, one that is the empty set.
HINT_INLINE_UNREFERENCED_SMALL_IMAGE: Final[str] = "inline_unreferenced_small_image"
HINT_INLINE_UNREFERENCED_TRACKING_PIXEL: Final[str] = "inline_unreferenced_tracking_pixel"
HINT_RULES: Final[tuple[str, ...]] = (
    HINT_INLINE_UNREFERENCED_SMALL_IMAGE,
    HINT_INLINE_UNREFERENCED_TRACKING_PIXEL,
)

#: The image formats the tracking-pixel rule reads dimensions from. JPEG is deliberately absent:
#: a JPEG's dimensions need its SOF segment, which is not in the first bytes, so a JPEG never
#: fires the rule (item 6).
_MEASURABLE_IMAGE_MAGIC: Final[tuple[str, ...]] = ("png", "gif")

#: The two decoded-byte cap reasons a skipped *leaf* can be skipped by (the walker's own ids).
_DECODED_CAP_REASONS: Final[tuple[str, ...]] = (CAP_REASON_SIZE, CAP_REASON_TOTAL_SIZE)


# ------------------------------------------------------------------- the records


@dataclass(frozen=True)
class CapSkip:
    """One size-cap hit the walker recorded, **re-stated** for a later turn's cap record.

    This module enforces no cap and truncates nothing: the walker (Turn 1.5c) skipped the part,
    accounted its bytes and left the reason on the result. ``cap_id`` is that closed reason
    (``size_cap`` or ``total_size_cap``), ``cap_value_bytes`` is the **caller's** own ``Limits``
    field for it (never a module default: there is none) and ``declared_size`` is the skipped
    region's span length -- so the triple is reconstructible from the result and the ``Limits``
    that produced it.
    """

    locator: str
    cap_id: str
    cap_value_bytes: int
    declared_size: int


@dataclass(frozen=True)
class _Parts:
    """One occurrence's derived facts: everything the five fact rows are built from."""

    part: PartShape
    index: int
    classification: Classification
    filename_raw: str | None
    filename_decoded: TriValue
    filename_state: str
    filename_fallback: str | None
    cid: str | None
    disposition: str | None
    size_bytes: int | None
    sha256: str | None
    verdicts: TypeVerdicts
    hint: DecorativeHint
    referenced: str
    normalized_cid: str | None


@dataclass(frozen=True)
class Attachments:
    """The whole attachment stage's output for one message: records, facts, gaps and cap hits.

    ``dangling`` is the **measured** dangling-cid list (a reference no part's ``Content-ID``
    carries) and ``unreferenced`` the measured unreferenced-cid list; see :func:`_gaps` for why
    ``dangling`` produces no gap pair in this turn.
    """

    occurrences: tuple[AttachmentOccurrence, ...]
    facts: tuple[_Parts, ...]
    gaps: tuple[tuple[str, str], ...]
    caps: tuple[CapSkip, ...]
    dangling: tuple[str, ...] = ()
    unreferenced: tuple[str, ...] = ()

    def rows(self, fact_id: str) -> list[list[object]]:
        """One fact's rows, by fact id (``attach.manifest`` and the four beside it)."""
        return _ROW_BUILDERS[fact_id](self)


# ------------------------------------------------------------------- the read


def read_prefix(decoded: bytes, length: int) -> bytes:
    """At most ``length`` bytes of ``decoded``: the **one** bounded-read seam.

    Every magic decision goes through here with :data:`MAGIC_PREFIX_BYTES` and every image-header
    decision with :data:`IMAGE_HEADER_BYTES`, so a caller (the fuzz) instruments the bound by
    replacing this one function and asserting that no read asked for more. Nothing in this module
    ever reads a whole payload: no attachment is opened, decompressed or parsed.
    """
    return decoded[:length]


def magic_name(decoded: bytes | None) -> str | None:
    """The magic table's name for ``decoded``'s prefix, or ``None`` when nothing matched.

    ``None`` means *consulted and clean* for a caller that had bytes (the sentinel
    ``VALUE("unrecognized")``) and "nothing was consulted" for a caller that had none. Only the
    first :data:`MAGIC_PREFIX_BYTES` bytes are read.
    """
    if decoded is None:
        return None
    prefix = read_prefix(decoded, MAGIC_PREFIX_BYTES)
    for name, signatures in MAGIC_TABLE:
        if any(prefix.startswith(signature) for signature in signatures):
            return name
    return None


def decoded_payload(raw: bytes, part: PartShape) -> bytes | None:
    """The part's transfer-decoded payload bytes, or ``None`` when the walker decoded nothing.

    The decode is the walker's own rule (:func:`emailextract.text.decoded_payload`: the same
    ``walk._decode_cte`` the walker hashed), so the sha256 this module reports is over exactly
    these bytes and the size is theirs. A part the walker skipped for a size cap has
    ``body_sha256 is None`` and is never decoded again (item 7). This is the stage's **one**
    payload read -- the mutation catalogue's truncation case patches it.
    """
    return text_stage.decoded_payload(raw, part)


def _magic_verdict(decoded: bytes | None, *, skipped_cap: bool, own_body: bool) -> TriValue:
    """The ``magic`` verdict: a value, the ``unrecognized`` sentinel, or an unknown with a reason."""
    if decoded is None and skipped_cap:
        return TriValue(state=TriState.UNKNOWN, reason_id=MAGIC_SKIPPED_CAP)
    if decoded is None:  # no own body: a container node, which is never an occurrence here
        return TriValue(state=TriState.ABSENT)
    if not decoded:
        return TriValue(
            state=TriState.UNKNOWN,
            reason_id=MAGIC_EMPTY if not own_body else MAGIC_UNDECODABLE,
        )
    name = magic_name(decoded)
    if name is None:
        return TriValue(state=TriState.VALUE, value=UNRECOGNIZED)
    return TriValue(state=TriState.VALUE, value=name)


def _projected(verdict: TriValue) -> str | None:
    """A verdict's projected value: the value when its state is ``VALUE``, else ``null`` (D4)."""
    return verdict.value if verdict.state is TriState.VALUE else None


def _as_row(verdict: TriValue) -> list[object]:
    """A verdict as the frozen ``[state, value | null, reason | null]`` triple."""
    return [verdict.state.value, verdict.value, verdict.reason_id]


# -------------------------------------------------------------- the derivations


def _generic_family() -> str:
    """The family the generic opaque media type names, read off the model's own function."""
    verdict = TriValue(state=TriState.VALUE, value=GENERIC_MEDIA_TYPE)
    family = type_family_of(verdict)
    if family is None:  # the model changed its mind about the generic type: say so, never guess
        raise ValueError(
            f"the model names no family for {GENERIC_MEDIA_TYPE!r}, so the disagreement's "
            "generic-type exclusion is undefined"
        )
    return family


def container_family(verdict: TriValue) -> str | None:
    """The **container** family a verdict names, or ``None`` when it names none (decision 25).

    The model's :func:`~emailextract.model.type_family_of` is called for the family; this then
    reads it at the container level D4 discusses ("DOCX/XLSX/PPTX are all zip and
    ``.xls``/``.doc``/``.msg`` are all OLE-CFB"): a declared OOXML/vendor type names the container
    it *is*, and a generic ``application/octet-stream`` claim -- a claim of no specific type --
    names none, because a claim that names no container cannot contradict one.
    """
    if verdict.state is not TriState.VALUE or verdict.value is None:
        return None
    family = type_family_of(verdict)
    if family is None:
        return None
    if family == _generic_family():
        return None
    media = verdict.value.split(";", 1)[0].strip().lower()
    return _CONTAINER_BY_MEDIA_TYPE.get(media, family)


def disagrees(verdicts: Sequence[TriValue]) -> bool:
    """``attach.type_disagreement`` over the verdicts' **container** families (decision 25).

    The rule is the model's own two-line set rule (at least two ``VALUE`` verdicts with a family,
    and the families number >= 2); what decision 25 fixes is only *which* family a verdict names,
    because the frozen corpus shows the model's subtype reading firing on
    ``attach_ole_cfb_magic`` (its ``attach.types`` row types ``disagreement`` false) and on
    ``attach_macro_docm`` (its ``gaps.later`` types no ``attach.type_disagreement`` row at all).
    ``VALUE("unrecognized")`` and any ``UNKNOWN`` name no family, as before.
    """
    families = {
        family for verdict in verdicts if (family := container_family(verdict)) is not None
    }
    return len(families) >= 2



# ------------------------------------------------------------------- the parts


def _by_path(result: WalkResult) -> dict[str, PartShape]:
    return {part.path: part for part in result.parts}


def is_attachment_part(part: PartShape, parts: Mapping[str, PartShape]) -> bool:
    """Whether ``part`` is an attachment occurrence (item 1).

    A leaf MIME part that is not a body view and **not a multipart container** -- a part whose
    declared ``Content-Type`` is ``multipart/*`` is a container whether or not the walker found
    children in it (a declared multipart whose boundary never appears is still not an
    attachment). A ``message/rfc822`` part is an occurrence (and is never recursed); a
    ``text/calendar`` alternative is a view, never an attachment.
    """
    if (part.content_type or "").lower().startswith("multipart/"):
        return False
    if any(other.parent_path == part.path for other in parts.values()):
        return False
    return not is_body_view(part, parts)


def _media_as_written(part: PartShape) -> str | None:
    """The ``Content-Type`` media type **as the header writes it**, parameters dropped.

    The walker's ``part.content_type`` is lowercased (its own ``_split_params``); the frozen
    ``attach_macro_docm`` ``attach.manifest`` row types the header's own case, so the declared
    verdict -- and so the manifest column, its projection -- is taken from the raw field value
    instead. A media type is a token, so the first ``;`` ends it and no quoted ``;`` can precede
    it.
    """
    for field in part.header_fields:
        if field.parse_status == "ok" and field.name.lower() == "content-type":
            media = field.raw_value.split(";", 1)[0].strip()
            return media or None
    return None


def _header_text(part: PartShape, name: str) -> str | None:
    """The part's own header value, verbatim and stripped (first field wins, as the walker)."""
    wanted = name.lower()
    for field in part.header_fields:
        if field.parse_status == "ok" and field.name.lower() == wanted:
            return field.raw_value.strip()
    return None


def _disposition(part: PartShape) -> str | None:
    """The part's disposition token as written (``attachment`` / ``inline``), or ``None``."""
    value = _header_text(part, "content-disposition")
    if value is None:
        return None
    token = value.split(";", 1)[0].strip()
    return token or None


def _classify(disposition: str | None, filename: str | None) -> Classification:
    """D4's classification axis, from the disposition and the filename and nothing else."""
    if disposition is not None:
        lowered = disposition.lower()
        if lowered == Classification.ATTACHMENT.value:
            return Classification.ATTACHMENT
        if lowered == Classification.INLINE.value:
            return Classification.INLINE
    if filename:
        return Classification.ATTACHMENT
    return Classification.UNKNOWN


def normalized_cid(value: str) -> str:
    """One ``Content-ID``, normalised for comparison: whitespace and one ``<>`` pair stripped.

    Comparison with ``body.cid_refs`` is **case-sensitive** (RFC 2392's addr-spec local part,
    Turn 1.5b's :func:`~emailextract.selection.dangling_and_unreferenced`), so this never folds
    case. The manifest's ``cid`` column keeps the header's own value (angle brackets included);
    only the comparison uses this.
    """
    text = value.strip()
    if len(text) >= 2 and text.startswith("<") and text.endswith(">"):
        text = text[1:-1]
    return text


def _filename(part: PartShape) -> tuple[str | None, str, str | None, str | None]:
    """``(raw, state, decoded, fallback_reason)`` for the part's filename parameter.

    The parameter is parsed by Turn 1.1's parser (:func:`emailextract.rfc2231.parse_parameters`)
    over the part's own field, so the RFC 2231 continuations, the extended forms and the recorded
    fallbacks are the same rules ``headers.parameters`` uses. ``raw`` is the parameter's value text
    as written (``''run.log``), which is the frozen ``attach.filename`` column 2. A parameter the
    parser declines (``state == "undecodable"``) is this module's ``unparsable``
    (``GAP_ATTACH_FILENAME_UNPARSABLE``), and a fallback keeps its decoded value: an empty charset
    is a **recorded fallback**, never unparsable.

    The name is read from ``Content-Disposition``'s ``filename`` first, then from
    ``Content-Type``'s ``name`` -- the second form is what makes D4's "no disposition but a
    filename" reachable at all (a producer that states a name without a disposition).
    """
    for field, parameter_name in (
        ("content-disposition", "filename"),
        ("content-type", "name"),
    ):
        value = _header_text(part, field)
        if value is None:
            continue
        for parameter in parse_parameters(value.encode("latin-1"), 0):
            if parameter.name != parameter_name:
                continue
            raw = value[parameter.offset : parameter.offset + parameter.length]
            _, _, raw_value = raw.partition("=")
            raw_value = raw_value.strip()
            if len(raw_value) >= 2 and raw_value.startswith('"') and raw_value.endswith('"'):
                raw_value = raw_value[1:-1]
            if parameter.state == "undecodable":
                return raw_value, "unparsable", None, None
            return raw_value, parameter.state, parameter.value, parameter.fallback_reason
    return None, "absent", None, None


def _dimensions(decoded: bytes) -> tuple[int, int] | None:
    """A png/gif's declared pixel dimensions, from the first :data:`IMAGE_HEADER_BYTES` bytes.

    A PNG's ``IHDR`` width and height are the two big-endian 4-byte integers at bytes 16-23 (PNG
    5.6); a GIF's logical screen width and height are the two little-endian 2-byte integers at
    bytes 6-9 (GIF89a 17). The read is bounded and nothing else is looked at; an image whose
    header is shorter simply has no dimensions. A JPEG is never read (item 6).
    """
    head = read_prefix(decoded, IMAGE_HEADER_BYTES)
    name = magic_name(head)
    if name == "png":
        if len(head) < IMAGE_HEADER_BYTES or head[12:16] != b"IHDR":
            return None
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if name == "gif":
        if len(head) < 10:
            return None
        return int.from_bytes(head[6:8], "little"), int.from_bytes(head[8:10], "little")
    return None


def _hint(
    *, classification: Classification, referenced: str, magic: TriValue, decoded: bytes | None
) -> DecorativeHint:
    """The decorative hint (D4): ``rule_id | absent``, a hint, never a removal.

    ``HINT_INLINE_UNREFERENCED_TRACKING_PIXEL`` fires iff the occurrence is inline, its cid is
    unreferenced, the magic verdict is ``png`` or ``gif``, and the declared dimensions are 1x1.
    ``HINT_INLINE_UNREFERENCED_SMALL_IMAGE`` is the empty set in Phase 1: no size threshold is
    fixed by the design, so it is in the vocabulary and never fires.
    """
    if classification is not Classification.INLINE:
        return DecorativeHint()
    if referenced != "unreferenced":
        return DecorativeHint()
    if magic.state is not TriState.VALUE or magic.value not in _MEASURABLE_IMAGE_MAGIC:
        return DecorativeHint()
    if decoded is None or _dimensions(decoded) != (1, 1):
        return DecorativeHint()
    return DecorativeHint(
        state=DecorativeHintState.RULE_ID, rule_id=HINT_INLINE_UNREFERENCED_TRACKING_PIXEL
    )


# ------------------------------------------------------------------- the stage


def _cap_skip(part: PartShape, result: WalkResult, limits: object | None) -> CapSkip | None:
    """The :class:`CapSkip` for a part the walker skipped for a decoded-byte cap, or ``None``.

    The walker records the reason on an ``UnknownSection`` whose ``section`` is the part's
    locator and on a ``Region`` whose ``kind`` is the same reason; the region's span length is
    the declared size. ``limits`` is the caller's own object, consulted **only** to re-state the
    cap value (``walk.CAP_LIMIT_FIELDS`` maps the reason to its field); an unbounded walk
    (``limits=None``) can hit no cap, so there is nothing to re-state.
    """
    reason = next(
        (
            section.value.reason_id
            for section in result.unknown_sections
            if section.section == part.path and section.value.reason_id in _DECODED_CAP_REASONS
        ),
        None,
    )
    if reason is None:
        return None
    value = getattr(limits, CAP_LIMIT_FIELDS[reason], None)
    if not isinstance(value, int):
        return None
    declared_size = next(
        (
            region.span.length
            for region in result.regions
            if region.path == part.path and region.kind == reason
        ),
        0,
    )
    return CapSkip(
        locator=part.path, cap_id=reason, cap_value_bytes=value, declared_size=declared_size
    )


def attachments(
    raw: bytes,
    result: WalkResult,
    *,
    max_depth: int,
    max_elements: int,
    limits: object | None = None,
) -> Attachments:
    """Every attachment occurrence of ``result``, with its records, rows, gaps and cap hits.

    ``max_depth`` / ``max_elements`` are the caller's caps for the HTML projection the referenced
    cid set is read from (decision 9: caps are caller parameters). ``limits`` is the caller's own
    :class:`~emailextract.parse.Limits`, or ``None`` for the unbounded walk, and is **only**
    re-stated in a :class:`CapSkip`: this stage enforces nothing.
    """
    parts = _by_path(result)
    referenced_cids: list[str] = []
    for _locator, cids in cid_ref_rows(
        raw, result, max_depth=max_depth, max_elements=max_elements
    ):
        referenced_cids.extend(cids)
    referenced_set = set(referenced_cids)
    content_ids = [
        normalized
        for part in result.parts
        if (value := _header_text(part, "content-id")) is not None
        and (normalized := normalized_cid(value))
    ]
    dangling, unreferenced = dangling_and_unreferenced(referenced_cids, content_ids)
    unreferenced_set = set(unreferenced)

    facts: list[_Parts] = []
    for part in result.parts:
        if not is_attachment_part(part, parts):
            continue
        filename_raw, filename_state, filename_text, filename_fallback = _filename(part)
        cid = _header_text(part, "content-id")
        disposition = _disposition(part)
        decoded = decoded_payload(raw, part)
        media = _media_as_written(part)
        declared = (
            TriValue(state=TriState.VALUE, value=media)
            if media is not None
            else TriValue(state=TriState.ABSENT)
        )
        magic = _magic_verdict(
            decoded,
            skipped_cap=part.body_sha256 is None,
            own_body=part.body_span.length > 0,
        )
        introspection = not_built_in_phase1()
        classifications = (
            TriValue(state=TriState.VALUE, value=filename_text)
            if filename_state in ("decoded", "fallback")
            else TriValue()
        )
        normalized = normalized_cid(cid) if cid is not None else None
        if normalized is None:
            state = "n/a"
        elif normalized in referenced_set:
            state = "referenced"
        else:
            state = "unreferenced"
        classification = _classify(disposition, filename_raw)
        facts.append(
            _Parts(
                part=part,
                index=len(facts),
                classification=classification,
                filename_raw=filename_raw,
                filename_decoded=classifications,
                filename_state=filename_state,
                filename_fallback=filename_fallback,
                cid=cid,
                disposition=disposition,
                size_bytes=None if decoded is None else len(decoded),
                sha256=part.body_sha256,
                verdicts=TypeVerdicts(
                    declared_mime=declared,
                    magic=magic,
                    container_introspection=introspection,
                    winner=type_winner(declared, magic, introspection),
                    disagreement=disagrees((declared, magic, introspection)),
                ),
                hint=_hint(
                    classification=classification,
                    referenced=state,
                    magic=magic,
                    decoded=decoded,
                ),
                referenced=state,
                normalized_cid=normalized,
            )
        )

    caps = tuple(
        skip
        for item in facts
        if item.sha256 is None and (skip := _cap_skip(item.part, result, limits)) is not None
    )
    return Attachments(
        occurrences=tuple(_occurrence(item) for item in facts),
        facts=tuple(facts),
        gaps=_gaps(raw, facts, unreferenced_set),
        caps=caps,
        dangling=tuple(dangling),
        unreferenced=tuple(unreferenced),
    )


def _occurrence(item: _Parts) -> AttachmentOccurrence:
    """The frozen contract record for one occurrence (D12).

    ``attachment_id`` is the content sha256 (the identity); when the walker skipped the part for
    a size cap there is no content hash, and the record carries the part's own content-addressed
    ``part_id`` instead -- the only honest identity for content that was never decoded -- while
    ``sha256`` stays ``None``. ``occurrence_path`` is the part's non-stable locator plus the
    occurrence's ordinal in the message (``1.3@0``).
    """
    return AttachmentOccurrence(
        attachment_id=item.sha256 or item.part.part_id,
        occurrence_path=f"{item.part.path}@{item.index}",
        part_id=item.part.part_id,
        classification=item.classification,
        filename_raw=item.filename_raw,
        filename_decoded=item.filename_decoded,
        cid=item.cid,
        size_bytes=item.size_bytes,
        sha256=item.sha256,
        encoding_source=item.part.encoding_source,
        decode_chain=item.part.decode_chain,
        decorative_hint=item.hint,
        type_verdicts=item.verdicts,
    )


def _gaps(
    raw: bytes, facts: Sequence[_Parts], unreferenced: set[str]
) -> tuple[tuple[str, str], ...]:
    """The attachment gap pairs ``(gap_id, locator)``, in the order of :data:`EMITTED_GAP_IDS`.

    **``attach.cid_dangling`` is measured and deliberately not turned into a row here** (its
    finding): the turn brief has it as a gap this stage records and the registry gives it first
    emission to Turn 1.8, but the frozen corpus cannot carry it. ``attach_cid_dangling`` types the
    row; ``html_href_img_remote_and_cid`` references ``cid:logo@example.test`` with no part
    carrying it -- its own ``not_yet_labelled`` annotation names "the Family C
    ``attach_cid_dangling`` case" -- and types no such row, and the oracle's ``gaps.later``
    comparison is exact over live ids for every sidecar that labels it. Emitting it anywhere is a
    mismatch against ``html_href_img_remote_and_cid``; the measured dangling list is therefore
    carried on :class:`Attachments` instead of in this tuple, and a test pins both halves. No
    label is edited.

    The unreferenced-cid rule is D4's: it applies **only to an inline occurrence**.
    """
    pairs: list[tuple[str, str]] = []

    for item in facts:
        if item.filename_raw is None and _declares_message_rfc822(item.part):
            pairs.append((GAP_ATTACH_FILENAME_ABSENT, item.part.path))
        if item.verdicts.disagreement:
            pairs.append((GAP_ATTACH_TYPE_DISAGREEMENT, item.part.path))
        if item.verdicts.magic.state is TriState.VALUE:
            if item.verdicts.magic.value == "ole-cfb":
                pairs.append((GAP_ATTACH_OLE_CONTAINER_UNKNOWN, item.part.path))
            if item.verdicts.magic.value == "zip" and _macro_container(item):
                pairs.append((GAP_SECURITY_MACRO_PRESENT, item.part.path))
        if _is_tnef(raw, item.part):
            pairs.append((GAP_ATTACH_TNEF_PRESENT, item.part.path))

    pairs.extend(_duplicate_pairs(GAP_ATTACH_DUPLICATE_CONTENT_ID, facts, "normalized_cid"))
    pairs.extend(_duplicate_pairs(GAP_ATTACH_OCCURRENCE_REPEATED, facts, "sha256"))

    for item in facts:
        if (
            item.classification is Classification.INLINE
            and item.normalized_cid is not None
            and item.normalized_cid in unreferenced
        ):
            pairs.append((GAP_ATTACH_CID_UNREFERENCED, item.part.path))

    return tuple(pairs)


def _declares_message_rfc822(part: PartShape) -> bool:
    """Whether the part's **declared** ``Content-Type`` is ``message/rfc822`` (never a default)."""
    return (part.content_type or "").lower() == "message/rfc822"


def _macro_container(item: _Parts) -> bool:
    """Whether the occurrence's **container filename** names a macro-bearing OOXML document."""
    value = item.filename_decoded.value
    return bool(value) and value.lower().endswith(_MACRO_EXTENSIONS)


def _is_tnef(raw: bytes, part: PartShape) -> bool:
    """Whether the part's decoded payload begins with the TNEF signature."""
    decoded = decoded_payload(raw, part)
    if decoded is None:
        return False
    return read_prefix(decoded, MAGIC_PREFIX_BYTES).startswith(TNEF_SIGNATURE)


def _duplicate_pairs(gap_id: str, facts: Sequence[_Parts], attribute: str) -> list[tuple[str, str]]:
    """One ``(gap_id, "path, path")`` pair per repeated value of ``attribute``, in path order.

    A key of ``None`` (no cid, or an unknown content hash) is never a duplicate: two parts with
    no ``Content-ID`` do not carry "the same" one, and two parts the walker skipped have no
    identity to share.
    """
    groups: dict[str, list[str]] = {}
    for item in facts:
        key = getattr(item, attribute)
        if key is None:
            continue
        groups.setdefault(key, []).append(item.part.path)
    return [(gap_id, ", ".join(paths)) for _key, paths in groups.items() if len(paths) >= 2]


# ------------------------------------------------------------------- the rows


def manifest_rows(stage: Attachments) -> list[list[object]]:
    """``attach.manifest``: ``[part, filename, declared_mime, cid, disposition, cte, sha, size]``.

    ``filename`` is the decoded name (``null`` when the occurrence carries none), ``declared_mime``
    is the declared verdict's projected value (D4), ``cid`` keeps the header's own value,
    ``disposition`` is the header's disposition token, ``transfer_encoding`` is the declared CTE
    (``null`` when absent) and ``size`` is the decoded payload size in bytes.
    """
    return [
        [
            item.part.path,
            _projected(item.filename_decoded),
            _projected(item.verdicts.declared_mime),
            item.cid,
            item.disposition,
            item.part.decode_chain.declared_cte,
            item.sha256,
            item.size_bytes,
        ]
        for item in stage.facts
    ]


def type_rows(stage: Attachments) -> list[list[object]]:
    """``attach.types``: ``[part, declared_mime, magic, introspection, winner, disagreement]``."""
    return [
        [
            item.part.path,
            _as_row(item.verdicts.declared_mime),
            _as_row(item.verdicts.magic),
            _as_row(item.verdicts.container_introspection),
            item.verdicts.winner.value if item.verdicts.winner is not None else None,
            item.verdicts.disagreement,
        ]
        for item in stage.facts
    ]


def filename_rows(stage: Attachments) -> list[list[object]]:
    """``attach.filename``: ``[part, raw, decode_state, decoded_value, fallback_reason]``.

    One row per occurrence that carries a filename (``decode_state == "absent"`` has no row).
    """
    return [
        [
            item.part.path,
            item.filename_raw,
            item.filename_state,
            _projected(item.filename_decoded),
            item.filename_fallback,
        ]
        for item in stage.facts
        if item.filename_state != "absent"
    ]


def decorative_rows(stage: Attachments) -> list[list[object]]:
    """``attach.decorative``: ``[part, rule_id | null]`` per occurrence (never a removal)."""
    return [
        [
            item.part.path,
            item.hint.rule_id if item.hint.state is DecorativeHintState.RULE_ID else None,
        ]
        for item in stage.facts
    ]


def cid_use_rows(stage: Attachments) -> list[list[object]]:
    """``attach.cid_use``: ``[part, cid, referenced]`` per occurrence (``n/a`` when cid-less)."""
    return [[item.part.path, item.cid, item.referenced] for item in stage.facts]


def gap_pairs(stage: Attachments) -> list[tuple[str, str]]:
    """The stage's ``(gap_id, locator)`` pairs, for the Phase 1 gap channel."""
    return list(stage.gaps)


#: fact id -> its row builder, so a caller iterates the facts instead of the functions.
_ROW_BUILDERS: Final[Mapping[str, Callable[[Attachments], list[list[object]]]]] = {
    "attach.manifest": manifest_rows,
    "attach.types": type_rows,
    "attach.filename": filename_rows,
    "attach.decorative": decorative_rows,
    "attach.cid_use": cid_use_rows,
}
