"""Turn 1b.4: the MAPI property layer of a ``.msg``, on top of ``cfb.py``.

``mapi.py`` is a **leaf** like ``cfb.py``: it imports the stdlib and the sibling
``cfb`` module only -- never ``model``/``walk``/``parse``/``olefile``. It takes an
opened :class:`cfb.CfbFile` and returns *plain data*: the property tables, the strings
(the code-page ladder), the class gate, named-property recognition and the recipient
tables. It is **not** wired into ``parse``/``container``/``walk`` (Turn 1b.5) and it
never builds a header, body, attachment, time fact or any ``EmailDocument`` field.

**The failure convention (D1).** :func:`read_message` *returns*, it never raises, on
any input. A value whose bytes cannot be decoded is ``None`` with a ``fault`` from the
closed tuple :data:`FAULTS`, and the sha256 of the raw bytes is always carried so the
original is never lost. There is **no** replacement character, no ``errors="replace"``,
no ``surrogatepass`` and no latin-1 fallback: a byte that cannot be decoded is a named
fault, never a repaired string. Faults:

* ``stream_cycle`` / ``stream_out_of_range`` / ``stream_short_chain`` -- a
  ``__substg1.0_*`` stream's chain fault carried from :func:`cfb.read_stream`
  (``cfb.FAULT_CYCLE``/``FAULT_OUT_OF_RANGE``/``FAULT_SHORT_CHAIN``).
* ``stream_absent`` -- the named stream is not in the container.
* ``utf16_odd_length`` -- a ``001F`` value whose byte length is not a whole number of
  UTF-16 code units.
* ``utf16_lone_surrogate`` -- a ``001F`` value that strict ``utf-16-le`` will not
  decode (a lone surrogate).
* ``cp1252_undefined_byte`` -- the last ladder rung: bytes ``0x81 0x8D 0x8F 0x90 0x9D``
  that windows-1252 does not define.
* ``entry_truncated`` / ``table_size_misfit`` -- a property table shorter than its
  header, or whose ``(size - header)`` is not a multiple of the 16-byte entry.

A text value returned by ``mapi`` is always encodable as UTF-8 (a test asserts it for
every value of every fixture and every fuzz mutant).

**The string ladder (D2).** The input is a ``001E`` (PT_STRING8) value's raw bytes plus
the two code pages read from the **fixed entries** ``0x3FDE`` (internet) and ``0x3FFD``
(message) of the top-level table (never from streams: ``email-spike.md`` B4). The rungs,
each recording ``encoding_source``: the internet code page (if it resolves and decodes
strictly), else the message code page, else all-bytes-ASCII, else strict UTF-8, else
strict windows-1252. "Resolves" means the number is in :data:`CODEPAGES`; any other
number does not resolve and the ladder falls through. One trailing ``U+0000`` is stripped
and recorded (:attr:`TextValue.trailing_nul`); a second one stays. The raw digest is of
the bytes **before** the strip. ``001F`` is UTF-16LE with no ladder.

**Named properties (D5)** are recognised, never resolved: a tag id in ``0x8000-0xFFFE``
is flagged ``named=True`` (still decoded per its own type), the presence and stream sizes
of ``__nameid_version1.0`` are recorded, and its contents are never parsed.

**The class gate (D6)** reads ``0x001A`` first; for any verdict but ``ipm_note`` nothing
past the class is opened.

**The work bound.** Work is counted in *steps* through :class:`cfb.Work` (one per table
entry decode, ladder rung, substream read, recipient row, and per directory visit in the
one-pass stream index). Every counted loop is bounded by the bytes present -- a table's
length, the directory's entries -- never a declared count, so a full ``read_message`` adds
at most :data:`MAPI_WORK_PER_BYTE` * ``len(cfb.data)`` + :data:`MAPI_WORK_BASE` steps,
measured over every fixture and fuzz mutant by ``tests/test_mapi_hostile.py``. Stream
*resolution* is ``cfb.read_stream``'s and is uncounted there too.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import NamedTuple

from . import cfb

__all__ = [
    "CLASS_VERDICTS",
    "CODEPAGES",
    "ENCODING_SOURCES",
    "FAULTS",
    "FIXED_TYPES",
    "HEADER_SIZE_SUB",
    "HEADER_SIZE_TOP",
    "KNOWN_TAGS",
    "MAPI_WORK_BASE",
    "MAPI_WORK_PER_BYTE",
    "MV_FLAG",
    "NAMED_TAG_MAX",
    "NAMED_TAG_MIN",
    "OBSERVATION_IDS",
    "PROPERTY_TYPES",
    "AttachmentRow",
    "EmbeddedTable",
    "MapiMessage",
    "Property",
    "PropertyTable",
    "RawEntry",
    "RecipientRow",
    "TextValue",
    "classify_class",
    "decode_entry",
    "decode_string8",
    "decode_unicode",
    "declared_counts",
    "named_properties",
    "parse_property_table",
    "read_attachments",
    "read_message",
    "read_recipients",
    "render_unknown_tags",
]

# --- the closed fault vocabulary (D1) -----------------------------------------
FAULT_STREAM_CYCLE = "stream_cycle"
FAULT_STREAM_OUT_OF_RANGE = "stream_out_of_range"
FAULT_STREAM_SHORT_CHAIN = "stream_short_chain"
FAULT_STREAM_ABSENT = "stream_absent"
FAULT_UTF16_ODD_LENGTH = "utf16_odd_length"
FAULT_UTF16_LONE_SURROGATE = "utf16_lone_surrogate"
FAULT_CP1252_UNDEFINED_BYTE = "cp1252_undefined_byte"
FAULT_ENTRY_TRUNCATED = "entry_truncated"
FAULT_TABLE_SIZE_MISFIT = "table_size_misfit"

FAULTS = (
    FAULT_STREAM_CYCLE,
    FAULT_STREAM_OUT_OF_RANGE,
    FAULT_STREAM_SHORT_CHAIN,
    FAULT_STREAM_ABSENT,
    FAULT_UTF16_ODD_LENGTH,
    FAULT_UTF16_LONE_SURROGATE,
    FAULT_CP1252_UNDEFINED_BYTE,
    FAULT_ENTRY_TRUNCATED,
    FAULT_TABLE_SIZE_MISFIT,
)
#: ``cfb.read_stream``'s chain faults, mapped into this module's closed vocabulary.
STREAM_FAULTS = {
    cfb.FAULT_CYCLE: FAULT_STREAM_CYCLE,
    cfb.FAULT_OUT_OF_RANGE: FAULT_STREAM_OUT_OF_RANGE,
    cfb.FAULT_SHORT_CHAIN: FAULT_STREAM_SHORT_CHAIN,
}

# --- the two properties-table header sizes (B2) -------------------------------
#: The top-level ``__properties_version1.0`` header (the counts live at ``@16``/``@20``).
HEADER_SIZE_TOP = 32
#: A recipient, attachment or embedded-message table's header (B2: 8 bytes, 26/26).
HEADER_SIZE_SUB = 8
#: An embedded message's own property table header ([MS-OXMSG]; decided by the
#: ``(size - header) % 16 == 0`` rule and the ``olefile`` oracle -- D4).
EMBEDDED_HEADER_SIZE = 24
#: One property entry: ``(tag << 16) | type``, ``flags``, then 8 value bytes.
ENTRY_BYTES = 16

# --- property types ([MS-OXMSG] 2.2.1.1) --------------------------------------
PT_NULL = 0x0001
PT_I2 = 0x0002
PT_LONG = 0x0003
PT_R4 = 0x0004
PT_DOUBLE = 0x0005
PT_CURRENCY = 0x0006
PT_APPTIME = 0x0007
PT_ERROR = 0x000A
PT_BOOLEAN = 0x000B
PT_OBJECT = 0x000D
PT_I8 = 0x0014
PT_STRING8 = 0x001E
PT_UNICODE = 0x001F
PT_SYSTIME = 0x0040
PT_BINARY = 0x0102

#: [MS-OXMSG] 2.2.1.1: the multi-valued flag; the base type is ``type & 0x0FFF``.
MV_FLAG = 0x1000

#: The property types whose value decodes from the entry's inline eight bytes, and the
#: little-endian struct each narrows them with.
FIXED_TYPES = {
    PT_I2: "<h",
    PT_LONG: "<i",
    PT_R4: "<f",
    PT_DOUBLE: "<d",
    PT_CURRENCY: "<q",
    PT_APPTIME: "<d",
    PT_ERROR: "<i",
    PT_BOOLEAN: "<H",
    PT_I8: "<q",
    PT_SYSTIME: "<Q",
}
#: The property types whose value is a ``__substg1.0_*`` stream (single-valued name uses
#: the full type; multi-valued uses the base type plus a ``-NNNNNNNN`` suffix, B1).
VARIABLE_TYPES = (PT_STRING8, PT_UNICODE, PT_BINARY)
#: The human names, for the docstrings and the tests (no tag is identified by a number).
PROPERTY_TYPES = {
    PT_NULL: "null",
    PT_I2: "i2",
    PT_LONG: "long",
    PT_R4: "r4",
    PT_DOUBLE: "double",
    PT_CURRENCY: "currency",
    PT_APPTIME: "apptime",
    PT_ERROR: "error",
    PT_BOOLEAN: "boolean",
    PT_OBJECT: "object",
    PT_I8: "i8",
    PT_STRING8: "string8",
    PT_UNICODE: "unicode",
    PT_SYSTIME: "systime",
    PT_BINARY: "binary",
}

# --- the subscriber vocabulary ([MS-OXPROPS], observed in B3) -----------------

#: The code pages the ladder may resolve (D2). A number outside this table does not
#: resolve; widening it is a one-line change after a probe, not a guess now.
CODEPAGES = {1252: "cp1252", 20127: "ascii", 28591: "iso-8859-1", 65001: "utf-8"}

#: The message code page's two fixed entries (B4): the internet value first.
PROP_INTERNET_CODEPAGE = 0x3FDE
PROP_MESSAGE_CODEPAGE = 0x3FFD
#: The transport-header stream (Phase 1b's headers part) and the class.
PROP_MESSAGE_CLASS = 0x001A
PROP_SUBJECT = 0x0037
PROP_TRANSPORT_HEADERS = 0x007D

#: The recipient-row property tags (D7, B3 / probe P4).
PROP_RECIPIENT_TYPE = 0x0C15
PROP_RECIPIENT_DISPLAY = 0x3001
PROP_RECIPIENT_ADDRESS_TYPE = 0x3002
PROP_RECIPIENT_EMAIL = 0x3003
PROP_RECIPIENT_SMTP = 0x39FE

#: The attachment-row property tags (Turn 1b.7 D7, [MS-OXPROPS], probe P4 not yet run on
#: real mail). ``0x3701`` is the data tag; ``0x3705`` the method word.
PROP_ATTACH_DATA = 0x3701
PROP_ATTACH_METHOD = 0x3705
PROP_ATTACH_FILENAME_SHORT = 0x3704
PROP_ATTACH_FILENAME_LONG = 0x3707
#: The ladder's third rung: the display-name tag (``0x3001``), shared with a recipient row.
PROP_ATTACH_FILENAME_DISPLAY = PROP_RECIPIENT_DISPLAY
PROP_ATTACH_EXTENSION = 0x3703
PROP_ATTACH_MIME_TAG = 0x370E
PROP_ATTACH_CONTENT_ID = 0x3712
PROP_ATTACH_FLAGS = 0x3714
PROP_ATTACH_HIDDEN = 0x7FFE

#: The three attachment methods Turn 1b.7 handles specially; every other number (and a
#: reference method 2/3/4 or a web reference) is recorded and dropped unsupported.
METHOD_BY_VALUE = 1
METHOD_BY_REFERENCE = 2
METHOD_BY_REFERENCE_RESOLVE = 3
METHOD_BY_REFERENCE_ONLY = 4
METHOD_EMBEDDED_MESSAGE = 5
METHOD_OLE = 6
REFERENCE_METHODS = (
    METHOD_BY_REFERENCE,
    METHOD_BY_REFERENCE_RESOLVE,
    METHOD_BY_REFERENCE_ONLY,
)
#: ``0x3714``'s ``ATT_MHTML_REF`` bit: the body references the attachment (D2's ``inline``).
ATT_MHTML_REF = 0x4

#: ``EncodingSource`` values (``model.EncodingSource``), as strings; pinned by a test.
ENCODING_SOURCES = ("internet_cpid", "message_cpid", "ascii", "utf8_strict", "windows_1252")
#: The ladder rungs that *are* the fall-through (D2: the gap fires only for these).
LADDER_FALLTHROUGH = ("ascii", "utf8_strict", "windows_1252")

#: The named-property tag range (D5); the number alone is never an identity.
NAMED_TAG_MIN = 0x8000
NAMED_TAG_MAX = 0xFFFE

#: The class-gate verdicts (D6), a closed tuple.
CLASS_VERDICTS = ("ipm_note", "signed_or_encrypted", "not_ipm_note", "class_absent", "class_unreadable")
CLASS_IPM_NOTE = "ipm_note"
CLASS_SIGNED = "signed_or_encrypted"
CLASS_NOT_IPM_NOTE = "not_ipm_note"
CLASS_ABSENT = "class_absent"
CLASS_UNREADABLE = "class_unreadable"
#: The signed/encrypted prefixes (O8: class recorded, body never opened, never verified).
SIGNED_PREFIXES = ("IPM.NOTE.SMIME", "IPM.NOTE.SECURE")

#: The recipient-kind vocabulary (D7) and the address-type vocabulary.
RECIPIENT_KINDS = ("to", "cc", "bcc", "unknown")
ADDRESS_TYPES = ("smtp", "ex", "unknown")

# --- the stream / storage names (B1) ------------------------------------------
SUBSTG_PREFIX = "__substg1.0_"
RECIPIENT_PREFIX = "__recip_version1.0_#"
ATTACHMENT_PREFIX = "__attach_version1.0_#"
NAMEID_STORAGE = "__nameid_version1.0"
#: The three ``__nameid_version1.0`` binary streams B1 records (contents never parsed).
NAMEID_STREAMS = (
    "__substg1.0_00020102",
    "__substg1.0_00030102",
    "__substg1.0_00040102",
)

#: A tag/type pair is rendered as ``tag:type``, four lowercase hex digits each (B3).
#: Every id here is a registry id (``tests/test_phase0_gaps.registry_ids``); every one
#: but ``msg.property_tag_unknown`` is raised once at message level.
MSG_CLASS_NOT_IPM_NOTE = "msg.class_not_ipm_note"
MSG_PROPERTY_TAG_UNKNOWN = "msg.property_tag_unknown"
MSG_NAMED_PROPERTY_UNRESOLVED = "msg.named_property_unresolved"
MSG_CODEPAGE_UNRESOLVED_LADDER_USED = "msg.codepage_unresolved_ladder_used"
MSG_RECIPIENT_TABLE_UNREADABLE = "msg.recipient_table_unreadable"

#: The gap ids this module can name, pinned equal to the registered ids by a test.
OBSERVATION_IDS = (
    MSG_CLASS_NOT_IPM_NOTE,
    MSG_PROPERTY_TAG_UNKNOWN,
    MSG_NAMED_PROPERTY_UNRESOLVED,
    MSG_CODEPAGE_UNRESOLVED_LADDER_USED,
    MSG_RECIPIENT_TABLE_UNREADABLE,
)

#: The known tags (D4). Each row is ``(tag, name, expected types, source)``; ``source``
#: is ``"B3"`` (observed in the eleven-file spike) or ``"MS-OXPROPS"`` (public spec only,
#: not yet probed). Every other tag is unknown, hex only -- nothing is frozen by a doc.
KNOWN_TAGS = (
    (0x001A, "message_class", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (0x0037, "subject", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (0x007D, "transport_headers", (PT_STRING8, PT_UNICODE), "B3"),
    (0x1000, "body_plain", (PT_STRING8, PT_UNICODE), "B3"),
    (0x1009, "body_rtf", (PT_BINARY,), "B3"),
    (0x1013, "body_html", (PT_BINARY,), "B3"),
    (0x3FDE, "internet_codepage", (PT_LONG,), "B3"),
    (0x3FFD, "message_codepage", (PT_LONG,), "B3"),
    (0x0039, "client_submit_time", (PT_SYSTIME,), "MS-OXPROPS"),
    (0x0E06, "message_delivery_time", (PT_SYSTIME,), "MS-OXPROPS"),
    (0x3007, "creation_time", (PT_SYSTIME,), "MS-OXPROPS"),
    (0x3008, "last_modification_time", (PT_SYSTIME,), "MS-OXPROPS"),
    (0x0C1A, "sender_name", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (0x0C1E, "sender_address_type", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (0x0C1F, "sender_email_address", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (0x5D01, "sender_smtp_address", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (PROP_RECIPIENT_TYPE, "recipient_type", (PT_LONG,), "B3"),
    (PROP_RECIPIENT_DISPLAY, "recipient_display_name", (PT_STRING8, PT_UNICODE), "B3"),
    (PROP_RECIPIENT_ADDRESS_TYPE, "recipient_address_type", (PT_STRING8, PT_UNICODE), "B3"),
    (PROP_RECIPIENT_EMAIL, "recipient_email_address", (PT_STRING8, PT_UNICODE), "B3"),
    (PROP_RECIPIENT_SMTP, "recipient_smtp_address", (PT_STRING8, PT_UNICODE), "B3"),
    (PROP_ATTACH_DATA, "attach_data", (PT_OBJECT, PT_BINARY), "MS-OXPROPS"),
    (PROP_ATTACH_EXTENSION, "attach_extension", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (PROP_ATTACH_FILENAME_SHORT, "attach_filename_short", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (PROP_ATTACH_METHOD, "attach_method", (PT_LONG,), "MS-OXPROPS"),
    (PROP_ATTACH_FILENAME_LONG, "attach_filename_long", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (PROP_ATTACH_MIME_TAG, "attach_mime_tag", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (PROP_ATTACH_CONTENT_ID, "attach_content_id", (PT_STRING8, PT_UNICODE), "MS-OXPROPS"),
    (PROP_ATTACH_FLAGS, "attach_flags", (PT_LONG,), "MS-OXPROPS"),
    (PROP_ATTACH_HIDDEN, "attach_hidden", (PT_BOOLEAN,), "MS-OXPROPS"),
)
_KNOWN_BY_TAG = {tag: (name, types, source) for tag, name, types, source in KNOWN_TAGS}

# --- the declared work bound (see the module docstring) -----------------------
MAPI_WORK_PER_BYTE = 8
MAPI_WORK_BASE = 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fault_of(status: str) -> "str | None":
    """A ``cfb.read_stream`` fault as this module's fault, or ``None`` for ``ok``."""
    if status == cfb.FAULT_OK:
        return None
    return STREAM_FAULTS.get(status, FAULT_STREAM_OUT_OF_RANGE)


# ------------------------------------------------------------------- the values


class TextValue(NamedTuple):
    """One decoded text, its ladder provenance, and the raw bytes' digest.

    ``text`` is ``None`` exactly when ``fault`` is not (D1). ``encoding_source`` is the
    ladder rung (``internet_cpid``/``message_cpid``/``ascii``/``utf8_strict``/
    ``windows_1252``) for an 8-bit value and ``None`` for a ``001F`` value (no ladder).
    ``source_kind`` is ``internet``/``message``/``none`` and ``declared_cp`` the number
    the rung used (``None`` when ``source_kind == "none"``), so ``msg.codepage_ladder``'s
    ``[surface, source_kind, declared_cp, encoding_source]`` row is a pure projection.
    """

    text: "str | None"
    encoding_source: "str | None"
    source_kind: "str | None"
    declared_cp: "int | None"
    trailing_nul: bool
    fault: "str | None"
    raw_sha256: str

    @property
    def resolved(self) -> bool:
        return self.text is not None


class RawEntry(NamedTuple):
    """One 16-byte property-table entry before its value is decoded (D3)."""

    offset: int
    tag: int
    prop_type: int
    flags: int
    value: bytes


class PropertyTable(NamedTuple):
    """A parsed ``__properties_version1.0`` table: its raw entries and its table fault."""

    header: bytes
    header_size: int
    entries: tuple[RawEntry, ...]
    fault: "str | None"

    def first(self, tag: int) -> "RawEntry | None":
        for entry in self.entries:
            if entry.tag == tag:
                return entry
        return None


@dataclass(frozen=True)
class Property:
    """One decoded property entry (D3/D4/D5).

    ``value``/``value_hex`` carry a fixed-size type's decode (``PT_SYSTIME`` keeps the
    raw ``u64`` and its 16-digit lowercase hex); ``text`` a single 8-bit or UTF-16 value;
    ``texts`` every value of a multi-valued string; ``storage`` a storage-backed target
    (``000D``, never read). ``known``/``named`` are D4/D5's two flags; ``fault`` is one
    of :data:`FAULTS` and is set exactly when the value could not be decoded.
    """

    tag: int
    prop_type: int
    tag_hex: str
    type_hex: str
    name: "str | None"
    known: bool
    named: bool
    flags: int
    multi_valued: bool
    storage: "str | None"
    value: "int | float | None"
    value_hex: "str | None"
    text: "TextValue | None"
    texts: "tuple[TextValue, ...]"
    byte_length: "int | None"
    raw_sha256: "str | None"
    fault: "str | None"

    @property
    def key(self) -> str:
        """The ``tag:type`` pair, four lowercase hex digits each (D4)."""
        return f"{self.tag:04x}:{self.prop_type:04x}"

    @property
    def encoding_source(self) -> "str | None":
        if self.text is not None:
            return self.text.encoding_source
        if self.texts:
            return self.texts[0].encoding_source
        return None


class RecipientRow(NamedTuple):
    """One ``__recip_version1.0_#XXXXXXXX`` row (D7).

    ``index`` is the hex suffix as an int (``None`` when the suffix is not hex, which
    makes the row unreadable). The rows come from the *directory*, never a declared
    count.
    """

    name: str
    index: "int | None"
    kind: str
    kind_raw: "int | None"
    display_name: "TextValue | None"
    address_type: str
    address_type_raw: "str | None"
    address: "TextValue | None"
    properties: tuple[Property, ...]
    unknown_tags: tuple[str, ...]
    fault: "str | None"


@dataclass(frozen=True)
class MapiMessage:
    """Everything ``mapi.py`` reads from one message (D1-D7).

    ``stopped`` is the class gate's short-circuit: for any verdict but ``ipm_note``
    nothing past the class was opened, so ``properties``/``recipients`` are empty.
    ``observations`` are the gap ids raised at message level, in :data:`OBSERVATION_IDS`
    order; building a gap *record* from them is Turn 1b.5's.
    """

    class_verdict: str
    message_class: "str | None"
    stopped: bool
    internet_cp: "int | None"
    message_cp: "int | None"
    properties: tuple[Property, ...]
    recipients: tuple[RecipientRow, ...]
    named_tags: tuple[str, ...]
    unknown_tags: tuple[str, ...]
    nameid_present: bool
    nameid_sizes: tuple[int, ...]
    declared_recipient_count: "int | None"
    declared_attachment_count: "int | None"
    recipient_row_count: int
    property_fault: "str | None"
    observations: tuple[str, ...]


# ------------------------------------------------------------------ the strings


def _with_trailing_nul(text: str, source: "str | None", kind: "str | None", cp: "int | None", digest: str) -> TextValue:
    """Strip one trailing ``U+0000`` (recorded); a second one stays (D2)."""
    trailing = text.endswith("\x00")
    if trailing:
        text = text[:-1]
    return TextValue(text, source, kind, cp, trailing, None, digest)


def decode_string8(
    raw: bytes, *, internet_codepage: "int | None", message_codepage: "int | None"
) -> TextValue:
    """The 8-bit string ladder (D2): internet cp, message cp, ASCII, UTF-8, windows-1252."""
    digest = _sha256(raw)
    for cp, kind, source in (
        (internet_codepage, "internet", "internet_cpid"),
        (message_codepage, "message", "message_cpid"),
    ):
        codec = CODEPAGES.get(cp)
        if codec is None:
            continue
        try:
            text = raw.decode(codec)
        except (UnicodeDecodeError, LookupError, ValueError):
            continue
        return _with_trailing_nul(text, source, kind, cp, digest)
    if all(byte < 0x80 for byte in raw):
        return _with_trailing_nul(raw.decode("ascii"), "ascii", "none", None, digest)
    try:
        return _with_trailing_nul(raw.decode("utf-8"), "utf8_strict", "none", None, digest)
    except UnicodeDecodeError:
        pass
    try:
        return _with_trailing_nul(raw.decode("cp1252"), "windows_1252", "none", None, digest)
    except UnicodeDecodeError:
        return TextValue(None, None, "none", None, False, FAULT_CP1252_UNDEFINED_BYTE, digest)


def decode_unicode(raw: bytes) -> TextValue:
    """A ``001F`` value: strict UTF-16LE, no ladder (D2)."""
    digest = _sha256(raw)
    if len(raw) % 2:
        return TextValue(None, None, None, None, False, FAULT_UTF16_ODD_LENGTH, digest)
    try:
        text = raw.decode("utf-16-le")
    except UnicodeDecodeError:
        return TextValue(None, None, None, None, False, FAULT_UTF16_LONE_SURROGATE, digest)
    return _with_trailing_nul(text, None, None, None, digest)


def _decode_text(raw: bytes, prop_type: int, internet_cp: "int | None", message_cp: "int | None") -> TextValue:
    if prop_type == PT_UNICODE:
        return decode_unicode(raw)
    return decode_string8(raw, internet_codepage=internet_cp, message_codepage=message_cp)


# ------------------------------------------------------------- the class gate


def classify_class(text: "str | None", fault: "str | None" = None) -> str:
    """The class gate (D6): a closed verdict for a class string.

    ``ipm_note`` is exactly ``IPM.Note`` or ``IPM.Note.`` followed by anything but the
    signed/encrypted prefixes; ``signed_or_encrypted`` starts ``IPM.Note.SMIME`` or
    ``IPM.Note.Secure``; a string that merely starts ``IPM.Note`` without a dot boundary
    is ``not_ipm_note``. An undecodable value is ``class_unreadable``; no value at all
    (missing or empty) is ``class_absent``. ASCII case-insensitive.
    """
    if fault is not None:
        return CLASS_UNREADABLE
    if text is None or text == "":
        return CLASS_ABSENT
    upper = text.upper()
    if upper == "IPM.NOTE":
        return CLASS_IPM_NOTE
    if upper.startswith("IPM.NOTE."):
        rest = upper[len("IPM.NOTE.") :]
        if any(rest.startswith(prefix[len("IPM.NOTE.") :]) for prefix in SIGNED_PREFIXES):
            return CLASS_SIGNED
        return CLASS_IPM_NOTE
    return CLASS_NOT_IPM_NOTE


# ---------------------------------------------------------------- the tables


def parse_property_table(data: bytes, *, header_size: int) -> PropertyTable:
    """A ``__properties_version1.0`` stream's entries (D3).

    ``header_size`` is 32 for the top-level table and 8 for a recipient, attachment or
    embedded-message table (B2). Entries are 16 bytes: ``u32 = (tag << 16) | type``,
    ``u32 flags``, then 8 value bytes. A ``(size - header)`` that is not a multiple of 16
    records ``table_size_misfit``; the loop is bounded by the table's length, never a
    declared count, so a hostile count cannot drive it.
    """
    header = data[:header_size]
    if len(data) < header_size:
        return PropertyTable(header, header_size, (), FAULT_TABLE_SIZE_MISFIT)
    remainder = (len(data) - header_size) % ENTRY_BYTES
    fault = FAULT_TABLE_SIZE_MISFIT if remainder else None
    entries: list[RawEntry] = []
    offset = header_size
    while offset + ENTRY_BYTES <= len(data):
        word, flags = struct.unpack_from("<II", data, offset)
        entries.append(
            RawEntry(
                offset=offset,
                tag=word >> 16,
                prop_type=word & 0xFFFF,
                flags=flags,
                value=data[offset + 8 : offset + ENTRY_BYTES],
            )
        )
        offset += ENTRY_BYTES
    return PropertyTable(header, header_size, tuple(entries), fault)


# ------------------------------------------------------------- the entries


def _substg_name(tag: int, prop_type: int) -> str:
    return f"{SUBSTG_PREFIX}{tag:04X}{prop_type:04X}"


def _substg_streams(cfb_file: cfb.CfbFile) -> dict:
    """Every ``__substg1.0_*`` stream, indexed in **one** directory pass.

    The key is ``(storage path, "TAGTYPE" upper hex)`` and the value a list of
    ``(index, entry)``: ``index`` is ``None`` for a plain name and the parsed ``-NNNNNNNN``
    suffix for B1's named-property / multi-valued layout. One pass, so each variable
    property's lookup is O(1) and the whole read stays bounded by the bytes present --
    never a declared count.
    """
    index: dict = {}
    for entry in cfb_file.entries:
        cfb_file.work.tick(1)
        path = entry.path
        if not entry.is_stream or not path:
            continue
        storage, _separator, name = path.rpartition("/")
        upper = name.upper()
        if not upper.startswith(SUBSTG_PREFIX.upper()):
            continue
        rest = upper[len(SUBSTG_PREFIX) :]
        number: "int | None" = None
        if "-" in rest:
            rest, _dash, suffix = rest.partition("-")
            try:
                number = int(suffix, 16)
            except ValueError:
                continue
        index.setdefault((storage, rest), []).append((number, entry))
    for rows in index.values():
        rows.sort(key=lambda row: (row[0] is not None, row[0] or 0))
    return index


def _plain_stream(index: dict, storage: str, tag: int, prop_type: int) -> "cfb.CfbEntry | None":
    for number, entry in index.get((storage, f"{tag:04X}{prop_type:04X}"), ()):
        if number is None:
            return entry
    return None


def _multi_streams(index: dict, storage: str, tag: int, base_type: int) -> "list[tuple[int, cfb.CfbEntry]]":
    rows = index.get((storage, f"{tag:04X}{base_type:04X}"), ())
    return [(number, entry) for number, entry in rows if number is not None]


def decode_entry(
    entry: RawEntry,
    cfb_file: cfb.CfbFile,
    *,
    internet_codepage: "int | None" = None,
    message_codepage: "int | None" = None,
    storage: str = "",
    index: "dict | None" = None,
) -> Property:
    """One table entry decoded by its own type (D3/D4/D5); never raises.

    ``storage`` is the posix path of the storage the table belongs to (empty for the
    top-level table; a recipient's path inside ``read_recipients``), so a variable value's
    ``__substg1.0_*`` stream is resolved in the right place. ``index`` is the shared
    directory index (:func:`_substg_streams`); a standalone call builds its own.
    """
    work = cfb_file.work
    work.tick(1)
    if index is None:
        index = _substg_streams(cfb_file)
    tag, prop_type = entry.tag, entry.prop_type
    multi = bool(prop_type & MV_FLAG)
    base = prop_type & 0x0FFF
    known = tag in _KNOWN_BY_TAG
    named = NAMED_TAG_MIN <= tag <= NAMED_TAG_MAX
    name = _KNOWN_BY_TAG[tag][0] if known else None
    tag_hex = f"{tag:04x}"
    type_hex = f"{prop_type:04x}"

    def build(**kwargs: object) -> Property:
        fields: dict[str, object] = dict(
            tag=tag,
            prop_type=prop_type,
            tag_hex=tag_hex,
            type_hex=type_hex,
            name=name,
            known=known,
            named=named,
            flags=entry.flags,
            multi_valued=multi,
            storage=None,
            value=None,
            value_hex=None,
            text=None,
            texts=(),
            byte_length=None,
            raw_sha256=None,
            fault=None,
        )
        fields.update(kwargs)
        return Property(**fields)  # type: ignore[arg-type]

    if not multi and base == PT_OBJECT:
        return build(storage=_substg_name(tag, prop_type))

    if base in VARIABLE_TYPES:
        if multi:
            texts: list[TextValue] = []
            digest: "str | None" = None
            length: "int | None" = None
            fault: "str | None" = None
            for index_number, stream_entry in _multi_streams(index, storage, tag, base):
                work.tick(1)
                payload, status = cfb.read_stream(cfb_file, stream_entry)
                stream_fault = _fault_of(status)
                if stream_fault is not None:
                    fault = fault or stream_fault
                    continue
                length = (length or 0) + len(payload)
                if base in (PT_STRING8, PT_UNICODE):
                    texts.append(_decode_text(payload, base, internet_codepage, message_codepage))
            if texts:
                digest = texts[0].raw_sha256
            return build(texts=tuple(texts), byte_length=length, raw_sha256=digest, fault=fault)
        stream_entry = _plain_stream(index, storage, tag, prop_type)
        if stream_entry is None and named:
            # A named property's stream carries the ``-00000000`` suffix (B1); fall back
            # to the streams that exist rather than guessing an index.
            substreams = _multi_streams(index, storage, tag, base)
            if substreams:
                stream_entry = substreams[0][1]
        if stream_entry is None:
            payload, status = b"", cfb.FAULT_OUT_OF_RANGE
        else:
            payload, status = cfb.read_stream(cfb_file, stream_entry)
        stream_fault = _fault_of(status)
        if stream_fault is not None:
            # An absent stream and a faulted one are distinct (D1).
            fault = FAULT_STREAM_ABSENT if status == cfb.FAULT_OUT_OF_RANGE else stream_fault
            return build(byte_length=None, fault=fault)
        if base in (PT_STRING8, PT_UNICODE):
            text = _decode_text(payload, base, internet_codepage, message_codepage)
            return build(text=text, byte_length=len(payload), raw_sha256=text.raw_sha256, fault=text.fault)
        return build(byte_length=len(payload), raw_sha256=_sha256(payload))

    fmt = FIXED_TYPES.get(prop_type)
    if fmt is not None:
        number = struct.unpack_from(fmt, entry.value, 0)[0]
        value_hex = f"{number:016x}" if prop_type == PT_SYSTIME else None
        return build(value=number, value_hex=value_hex)
    # An unmodelled type (e.g. PT_NULL): recognised as an entry, not decoded.
    return build()


def render_unknown_tags(properties: "tuple[Property, ...]") -> tuple[str, ...]:
    """The sorted distinct unknown ``tag:type`` pairs (D4); named tags are D5's, not here."""
    pairs = {prop.key for prop in properties if not prop.known and not prop.named}
    return tuple(sorted(pairs))


def _ladder_observation(texts: "tuple[TextValue, ...]") -> bool:
    return any(text.encoding_source in LADDER_FALLTHROUGH and text.text is not None for text in texts)


def _any_ladder(properties: "tuple[Property, ...]") -> bool:
    """Whether any property's text fired a fall-through ladder rung (D2)."""
    for prop in properties:
        if prop.text is not None and _ladder_observation((prop.text,)):
            return True
        if _ladder_observation(prop.texts):
            return True
    return False


# ------------------------------------------------------------- the recipients


def read_recipients(
    cfb_file: cfb.CfbFile,
    *,
    internet_codepage: "int | None" = None,
    message_codepage: "int | None" = None,
) -> tuple[RecipientRow, ...]:
    """Every ``__recip_version1.0_#XXXXXXXX`` row, ordered by the hex index (D7).

    The rows come from the directory (trust the directory); a suffix that is not hex
    makes that row unreadable. Each row is read with the 8-byte-header decoder.
    """
    work = cfb_file.work
    substg = _substg_streams(cfb_file)
    rows: "list[tuple[int, str]]" = []
    for entry in cfb_file.entries:
        path = entry.path
        if not path or "/" in path or not path.upper().startswith(RECIPIENT_PREFIX.upper()):
            continue
        suffix = path[len(RECIPIENT_PREFIX) :]
        try:
            number = int(suffix, 16)
        except ValueError:
            number = -1
        rows.append((number, path))
    rows.sort(key=lambda pair: (pair[0], pair[1]))

    result: list[RecipientRow] = []
    for number, path in rows:
        work.tick(1)
        table_path = f"{path}/__properties_version1.0"
        data, status = cfb.read_stream(cfb_file, table_path)
        stream_fault = _fault_of(status)
        if stream_fault is not None or number < 0:
            fault = FAULT_STREAM_ABSENT if stream_fault == FAULT_STREAM_OUT_OF_RANGE else stream_fault
            fault = fault or FAULT_ENTRY_TRUNCATED
            result.append(_recipient_row(path, number if number >= 0 else None, (), fault))
            continue
        table = parse_property_table(data, header_size=HEADER_SIZE_SUB)
        properties = tuple(
            decode_entry(
                entry,
                cfb_file,
                internet_codepage=internet_codepage,
                message_codepage=message_codepage,
                storage=path,
                index=substg,
            )
            for entry in table.entries
        )
        fault = table.fault
        result.append(_recipient_row(path, number, properties, fault))
    return tuple(result)


def _recipient_row(
    name: str, index: "int | None", properties: "tuple[Property, ...]", fault: "str | None"
) -> RecipientRow:
    by_tag: dict[int, Property] = {}
    for prop in properties:
        by_tag.setdefault(prop.tag, prop)
    kind_raw = by_tag[PROP_RECIPIENT_TYPE].value if PROP_RECIPIENT_TYPE in by_tag else None
    kind = {1: "to", 2: "cc", 3: "bcc"}.get(kind_raw, "unknown") if isinstance(kind_raw, int) else "unknown"
    display = by_tag.get(PROP_RECIPIENT_DISPLAY)
    address_type_prop = by_tag.get(PROP_RECIPIENT_ADDRESS_TYPE)
    address_type_raw = address_type_prop.text.text if address_type_prop and address_type_prop.text else None
    normalized = (address_type_raw or "").upper()
    address_type = {"SMTP": "smtp", "EX": "ex"}.get(normalized, "unknown")
    smtp = by_tag.get(PROP_RECIPIENT_SMTP)
    email = by_tag.get(PROP_RECIPIENT_EMAIL)
    if smtp is not None and smtp.text is not None and smtp.text.text:
        address = smtp.text
    elif email is not None and email.text is not None:
        address = email.text
    else:
        address = None
    return RecipientRow(
        name=name,
        index=index,
        kind=kind,
        kind_raw=kind_raw if isinstance(kind_raw, int) else None,
        display_name=display.text if display is not None else None,
        address_type=address_type,
        address_type_raw=address_type_raw,
        address=address,
        properties=properties,
        unknown_tags=render_unknown_tags(properties),
        fault=fault,
    )


# ------------------------------------------------------------- the attachments


def _text_of(properties: "tuple[Property, ...]", tag: int) -> "TextValue | None":
    """The first decoded text of ``tag``, or ``None`` (D7)."""
    for prop in properties:
        if prop.tag == tag and prop.text is not None:
            return prop.text
    return None


def _int_of(properties: "tuple[Property, ...]", tag: int) -> "int | None":
    """The first fixed-integer value of ``tag``, or ``None`` (D7)."""
    for prop in properties:
        if prop.tag == tag and isinstance(prop.value, int) and not isinstance(prop.value, bool):
            return prop.value
    return None


def _child_storages(cfb_file: cfb.CfbFile, parent: str, prefix: str) -> list[cfb.CfbEntry]:
    """The immediate children of ``parent`` whose own name starts ``prefix`` (a directory walk)."""
    wanted = prefix.upper()
    marker = f"{parent}/" if parent else ""
    found: list[cfb.CfbEntry] = []
    for entry in cfb_file.entries:
        path = entry.path
        if not path:
            continue
        if marker:
            if not path.upper().startswith(marker.upper()):
                continue
            rest = path[len(marker):]
        else:
            rest = path
        if "/" in rest:
            continue
        if rest.upper().startswith(wanted):
            found.append(entry)
    return found


class EmbeddedTable(NamedTuple):
    """An embedded message's own summary, read at depth 1 and **never** recursed (D4).

    ``nested_embedded_index`` is set when the embedded message itself carries a method-5
    attachment: its storage is **not** opened (the depth cap), and the index names the row
    the cap report cites. ``fault`` is one of :data:`FAULTS` when the embedded table could
    not be read.
    """

    message_class: "str | None"
    subject: "str | None"
    has_transport_headers: bool
    recipient_count: int
    attachment_count: int
    nested_embedded_index: "int | None"
    fault: "str | None"


class AttachmentRow(NamedTuple):
    """One ``__attach_version1.0_#XXXXXXXX`` row (Turn 1b.7 D7).

    The rows come from the *directory*, never a declared count. ``index`` is the hex suffix
    as an int (``None`` when the suffix is not hex). ``method`` is the raw ``0x3705`` word.
    The three filename rungs, the MIME tag and the Content-ID are the decoded value texts;
    ``hidden`` is ``0x7FFE`` and ``flags``/``inline`` are ``0x3714`` and its
    ``ATT_MHTML_REF`` bit. ``data_stream`` names the by-value data stream; ``embedded`` the
    embedded-message summary. No path or URL property is ever read.
    """

    name: str
    index: "int | None"
    method: "int | None"
    filename_long: "TextValue | None"
    filename_short: "TextValue | None"
    filename_display: "TextValue | None"
    mime_tag: "TextValue | None"
    cid: "TextValue | None"
    hidden: bool
    flags: "int | None"
    inline: bool
    data_stream: "str | None"
    embedded: "EmbeddedTable | None"
    properties: tuple[Property, ...]
    unknown_tags: tuple[str, ...]
    fault: "str | None"


def _embedded_table(
    cfb_file: cfb.CfbFile,
    storage: str,
    *,
    internet_codepage: "int | None",
    message_codepage: "int | None",
    substg: dict,
) -> EmbeddedTable:
    """Read an embedded message's own property table (D4): the header is
    :data:`EMBEDDED_HEADER_SIZE` bytes, decided by the ``(size - header) % 16 == 0`` rule."""
    path = f"{storage}/{_substg_name(PROP_ATTACH_DATA, PT_OBJECT)}"
    data, status = cfb.read_stream(cfb_file, f"{path}/__properties_version1.0")
    stream_fault = _fault_of(status)
    if stream_fault is not None:
        return EmbeddedTable(None, None, False, 0, 0, None, stream_fault)
    table = parse_property_table(data, header_size=EMBEDDED_HEADER_SIZE)
    properties = tuple(
        decode_entry(
            entry,
            cfb_file,
            internet_codepage=internet_codepage,
            message_codepage=message_codepage,
            storage=path,
            index=substg,
        )
        for entry in table.entries
    )
    class_text = _text_of(properties, PROP_MESSAGE_CLASS)
    subject = _text_of(properties, PROP_SUBJECT)
    has_transport = (
        cfb.lookup_entry(cfb_file.entries, f"{path}/__substg1.0_007D001F") is not None
        or cfb.lookup_entry(cfb_file.entries, f"{path}/__substg1.0_007D001E") is not None
    )
    recipients = _child_storages(cfb_file, path, RECIPIENT_PREFIX)
    attachments = _child_storages(cfb_file, path, ATTACHMENT_PREFIX)
    nested: "int | None" = None
    for entry in sorted(attachments, key=lambda item: item.path):
        row_table, row_status = cfb.read_stream(cfb_file, f"{entry.path}/__properties_version1.0")
        if _fault_of(row_status) is not None:
            continue
        row_props = parse_property_table(row_table, header_size=HEADER_SIZE_SUB)
        method = None
        for raw in row_props.entries:
            if raw.tag == PROP_ATTACH_METHOD:
                method = struct.unpack_from(FIXED_TYPES[PT_LONG], raw.value, 0)[0]
                break
        if method == METHOD_EMBEDDED_MESSAGE:
            suffix = entry.path.rsplit("#", 1)[-1]
            try:
                nested = int(suffix, 16)
            except ValueError:
                nested = -1
            break
    return EmbeddedTable(
        class_text.text if class_text is not None else None,
        subject.text if subject is not None else None,
        has_transport,
        len(recipients),
        len(attachments),
        nested,
        table.fault,
    )


def _attachment_row(
    cfb_file: cfb.CfbFile,
    path: str,
    index: "int | None",
    properties: "tuple[Property, ...]",
    fault: "str | None",
    *,
    internet_codepage: "int | None",
    message_codepage: "int | None",
    substg: dict,
) -> AttachmentRow:
    work = cfb_file.work
    method = _int_of(properties, PROP_ATTACH_METHOD)
    flags = _int_of(properties, PROP_ATTACH_FLAGS)
    hidden_prop = next((prop for prop in properties if prop.tag == PROP_ATTACH_HIDDEN), None)
    hidden = bool(hidden_prop.value) if hidden_prop is not None and isinstance(hidden_prop.value, int) else False
    data_stream: "str | None" = None
    embedded: "EmbeddedTable | None" = None
    if method == METHOD_BY_VALUE:
        data_stream = _substg_name(PROP_ATTACH_DATA, PT_BINARY)
        if cfb.lookup_entry(cfb_file.entries, f"{path}/{data_stream}") is None:
            data_stream = None
    elif method == METHOD_EMBEDDED_MESSAGE:
        work.tick(1)
        embedded = _embedded_table(
            cfb_file,
            path,
            internet_codepage=internet_codepage,
            message_codepage=message_codepage,
            substg=substg,
        )
    return AttachmentRow(
        name=path,
        index=index,
        method=method,
        filename_long=_text_of(properties, PROP_ATTACH_FILENAME_LONG),
        filename_short=_text_of(properties, PROP_ATTACH_FILENAME_SHORT),
        filename_display=_text_of(properties, PROP_ATTACH_FILENAME_DISPLAY),
        mime_tag=_text_of(properties, PROP_ATTACH_MIME_TAG),
        cid=_text_of(properties, PROP_ATTACH_CONTENT_ID),
        hidden=hidden,
        flags=flags,
        inline=bool(flags is not None and flags & ATT_MHTML_REF),
        data_stream=data_stream,
        embedded=embedded,
        properties=properties,
        unknown_tags=render_unknown_tags(properties),
        fault=fault,
    )


def read_attachments(
    cfb_file: cfb.CfbFile,
    *,
    internet_codepage: "int | None" = None,
    message_codepage: "int | None" = None,
) -> tuple[AttachmentRow, ...]:
    """Every ``__attach_version1.0_#XXXXXXXX`` row, ordered by the hex index (D7).

    The rows come from the directory (trust the directory); a suffix that is not hex makes
    that row unreadable. Each row is read with the 8-byte-header decoder, and its own
    embedded message (method 5) is read at depth 1 and **not** descended.
    """
    work = cfb_file.work
    substg = _substg_streams(cfb_file)
    rows: "list[tuple[int, str]]" = []
    for entry in cfb_file.entries:
        path = entry.path
        if not path or "/" in path or not path.upper().startswith(ATTACHMENT_PREFIX.upper()):
            continue
        suffix = path[len(ATTACHMENT_PREFIX):]
        try:
            number = int(suffix, 16)
        except ValueError:
            number = -1
        rows.append((number, path))
    rows.sort(key=lambda pair: (pair[0], pair[1]))

    result: list[AttachmentRow] = []
    for number, path in rows:
        work.tick(1)
        data, status = cfb.read_stream(cfb_file, f"{path}/__properties_version1.0")
        stream_fault = _fault_of(status)
        if stream_fault is not None or number < 0:
            fault = FAULT_STREAM_ABSENT if stream_fault == FAULT_STREAM_OUT_OF_RANGE else stream_fault
            fault = fault or FAULT_ENTRY_TRUNCATED
            result.append(
                AttachmentRow(
                    name=path,
                    index=number if number >= 0 else None,
                    method=None,
                    filename_long=None,
                    filename_short=None,
                    filename_display=None,
                    mime_tag=None,
                    cid=None,
                    hidden=False,
                    flags=None,
                    inline=False,
                    data_stream=None,
                    embedded=None,
                    properties=(),
                    unknown_tags=(),
                    fault=fault,
                )
            )
            continue
        table = parse_property_table(data, header_size=HEADER_SIZE_SUB)
        properties = tuple(
            decode_entry(
                entry,
                cfb_file,
                internet_codepage=internet_codepage,
                message_codepage=message_codepage,
                storage=path,
                index=substg,
            )
            for entry in table.entries
        )
        result.append(
            _attachment_row(
                cfb_file,
                path,
                number,
                properties,
                table.fault,
                internet_codepage=internet_codepage,
                message_codepage=message_codepage,
                substg=substg,
            )
        )
    return tuple(result)


# ------------------------------------------------------- named properties (D5)


def named_properties(cfb_file: cfb.CfbFile) -> "tuple[bool, tuple[int, ...]]":
    """Whether ``__nameid_version1.0`` is present and its three streams' sizes.

    Its contents are **never** parsed or used (D5).
    """
    if cfb.lookup_entry(cfb_file.entries, NAMEID_STORAGE) is None:
        return False, ()
    sizes: list[int] = []
    for stream_name in NAMEID_STREAMS:
        entry = cfb.lookup_entry(cfb_file.entries, f"{NAMEID_STORAGE}/{stream_name}")
        if entry is None:
            continue
        payload, status = cfb.read_stream(cfb_file, entry)
        sizes.append(len(payload) if status == cfb.FAULT_OK else 0)
    return True, tuple(sizes)


# --------------------------------------------------------------- the reader


def _ordered_observations(found: "set[str]") -> tuple[str, ...]:
    return tuple(obs for obs in OBSERVATION_IDS if obs in found)


def _stopped_message(
    verdict: str,
    message_class: "str | None",
    internet_cp: "int | None",
    message_cp: "int | None",
    property_fault: "str | None",
    found: "set[str]",
) -> MapiMessage:
    return MapiMessage(
        class_verdict=verdict,
        message_class=message_class,
        stopped=True,
        internet_cp=internet_cp,
        message_cp=message_cp,
        properties=(),
        recipients=(),
        named_tags=(),
        unknown_tags=(),
        nameid_present=False,
        nameid_sizes=(),
        declared_recipient_count=None,
        declared_attachment_count=None,
        recipient_row_count=0,
        property_fault=property_fault,
        observations=_ordered_observations(found),
    )


def read_message(cfb_file: cfb.CfbFile) -> MapiMessage:
    """Read the MAPI layer of an opened container (D1-D7); never raises.

    Order: the top-level property table, the two code pages (fixed entries), the class
    (the gate; stop for any verdict but ``ipm_note``), then recipients, named properties
    and every remaining tag.
    """
    work = cfb_file.work
    work.tick(1)
    data, status = cfb.read_stream(cfb_file, cfb.PROPERTIES_STREAM)
    stream_fault = _fault_of(status)
    if stream_fault is not None:
        return _stopped_message(CLASS_ABSENT, None, None, None, stream_fault, set())

    table = parse_property_table(data, header_size=HEADER_SIZE_TOP)
    internet_cp = _fixed_long(table, PROP_INTERNET_CODEPAGE)
    message_cp = _fixed_long(table, PROP_MESSAGE_CODEPAGE)
    found: "set[str]" = set()
    substg = _substg_streams(cfb_file)

    class_text, class_fault = _class_value(table, cfb_file, internet_cp, message_cp, found, substg)
    verdict = classify_class(class_text, class_fault)
    if verdict != CLASS_IPM_NOTE:
        if verdict in (CLASS_NOT_IPM_NOTE, CLASS_SIGNED):
            found.add(MSG_CLASS_NOT_IPM_NOTE)
        return _stopped_message(verdict, class_text, internet_cp, message_cp, table.fault, found)

    properties = tuple(
        decode_entry(
            entry,
            cfb_file,
            internet_codepage=internet_cp,
            message_codepage=message_cp,
            index=substg,
        )
        for entry in table.entries
    )
    recipients = read_recipients(
        cfb_file, internet_codepage=internet_cp, message_codepage=message_cp
    )

    declared_recipients = _header_count(table.header, 16)
    declared_attachments = _header_count(table.header, 20)

    # D2: the ladder gap fires only when a fall-through rung decoded a value.
    if _any_ladder(properties) or any(_any_ladder(row.properties) for row in recipients):
        found.add(MSG_CODEPAGE_UNRESOLVED_LADDER_USED)

    named_tags = tuple(sorted({prop.tag_hex for prop in properties if prop.named}))
    named_tags += tuple(
        sorted({prop.tag_hex for row in recipients for prop in row.properties if prop.named})
    )
    named_tags = tuple(sorted(set(named_tags)))
    if named_tags:
        found.add(MSG_NAMED_PROPERTY_UNRESOLVED)

    unknown = render_unknown_tags(properties)
    row_unknown = tuple(sorted({pair for row in recipients for pair in row.unknown_tags}))
    if unknown or row_unknown:
        found.add(MSG_PROPERTY_TAG_UNKNOWN)

    if _recipient_table_problem(declared_recipients, recipients):
        found.add(MSG_RECIPIENT_TABLE_UNREADABLE)

    nameid_present, nameid_sizes = named_properties(cfb_file)

    return MapiMessage(
        class_verdict=verdict,
        message_class=class_text,
        stopped=False,
        internet_cp=internet_cp,
        message_cp=message_cp,
        properties=properties,
        recipients=recipients,
        named_tags=named_tags,
        unknown_tags=tuple(sorted(set(unknown) | set(row_unknown))),
        nameid_present=nameid_present,
        nameid_sizes=nameid_sizes,
        declared_recipient_count=declared_recipients,
        declared_attachment_count=declared_attachments,
        recipient_row_count=len(recipients),
        property_fault=table.fault,
        observations=_ordered_observations(found),
    )


def _recipient_table_problem(declared: "int | None", rows: "tuple[RecipientRow, ...]") -> bool:
    """A declared count that disagrees with the directory's rows, or an unreadable row."""
    if any(row.fault is not None for row in rows):
        return True
    return declared is not None and declared != len(rows)


def _fixed_long(table: PropertyTable, tag: int) -> "int | None":
    entry = table.first(tag)
    if entry is None:
        return None
    fmt = FIXED_TYPES.get(entry.prop_type)
    if fmt is None:
        return None
    return struct.unpack_from(fmt, entry.value, 0)[0]


def _header_count(header: bytes, offset: int) -> "int | None":
    if offset + 4 > len(header):
        return None
    return struct.unpack_from("<I", header, offset)[0]


def declared_counts(table: PropertyTable) -> "tuple[int | None, int | None]":
    """The top-level header's ``@16`` recipient and ``@20`` attachment counts (B2)."""
    return _header_count(table.header, 16), _header_count(table.header, 20)


def _class_value(
    table: PropertyTable,
    cfb_file: cfb.CfbFile,
    internet_cp: "int | None",
    message_cp: "int | None",
    found: "set[str]",
    substg: dict,
) -> "tuple[str | None, str | None]":
    """The class string (verbatim) and its fault, if any (D6).

    Read straight from ``0x001A`` (``001F``, or ``001E`` through the ladder) so the gate
    never touches :func:`decode_entry`: for any verdict but ``ipm_note`` nothing past the
    class is decoded.
    """
    entry = table.first(PROP_MESSAGE_CLASS)
    if entry is None:
        return None, None
    cfb_file.work.tick(1)
    base = entry.prop_type & 0x0FFF
    if entry.prop_type & MV_FLAG or base not in (PT_STRING8, PT_UNICODE):
        return None, FAULT_ENTRY_TRUNCATED
    stream_entry = _plain_stream(substg, "", entry.tag, entry.prop_type)
    if stream_entry is None:
        payload, status = b"", cfb.FAULT_OUT_OF_RANGE
    else:
        payload, status = cfb.read_stream(cfb_file, stream_entry)
    stream_fault = _fault_of(status)
    if stream_fault is not None:
        return None, FAULT_STREAM_ABSENT if status == cfb.FAULT_OUT_OF_RANGE else stream_fault
    text = _decode_text(payload, base, internet_cp, message_cp)
    if text.text is None:
        return None, text.fault
    if _ladder_observation((text,)):
        found.add(MSG_CODEPAGE_UNRESOLVED_LADDER_USED)
    return text.text, None
