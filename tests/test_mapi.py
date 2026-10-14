"""Turn 1b.4: ``emailextract.mapi`` reads the property layer of a ``.msg``.

``mapi.py`` and ``tools/make_msg_fixtures.py`` share an author, so these tests do not take
the reader's word: the values are held against ``tests/support/mapi_table.py`` (property
bytes typed from [MS-OXMSG], built here in memory) and ``tests/support/msg_construction.py``
(``MAPI_EXPECTATIONS``, typed from ``email-spike.md`` B1-B4 before ``mapi.py`` ran). The
seeded fuzz (``tests/test_mapi_hostile.py``) is the third, unshared breaker.

The declared tests are:

* ``test_property_tables_use_the_32_and_8_byte_headers`` -- the two header sizes (B2) and
  the entry offsets they imply, plus the size-misfit fault;
* ``test_entry_decode_fixed_variable_and_storage_backed`` -- an inline fixed value, a
  ``__substg1.0_*`` variable value, and a ``000D`` storage ref that is never read (D3);
* ``test_the_class_gate_records_the_class_verbatim`` -- the D6 verdicts, the verbatim
  class, an empty class and a missing class;
* ``test_named_properties_are_recognised_not_resolved`` -- D5: recognised, still decoded,
  never resolved;
* ``test_recipients_are_read_from_the_recipient_tables`` -- D7's rows, kinds and address
  types, from the directory;
* ``test_an_unknown_tag_is_hex_only`` -- D4: unknown tags are hex only, one aggregate
  observation, no per-property gap.

Two checks beyond the declaration: the independent breaker over the hand-built Outlook
layout, and the gate-stops proof (the recipient and property decoders are never called).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb, mapi  # noqa: E402
from support import mapi_table, msg_construction  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
PT_STRING8 = mapi_table.PT_STRING8
PT_UNICODE = mapi_table.PT_UNICODE
PT_OBJECT = mapi_table.PT_OBJECT
PT_BINARY = mapi_table.PT_BINARY
_IPM_NOTE = mapi_table.utf16("IPM.Note")


def _open(*children) -> cfb.CfbFile:
    """Open a hand-built ``Root Entry`` tree (these inputs never refuse)."""
    opened = cfb.open_cfb(build_cfb(storage("Root Entry", *children)))
    assert isinstance(opened, cfb.CfbFile), opened
    return opened


def _fixture(name: str) -> cfb.CfbFile:
    opened = cfb.open_cfb((MSG / f"{name}.msg").read_bytes())
    assert isinstance(opened, cfb.CfbFile), name
    return opened


def _message(*children, entries=(), recipients=0, codepages=None) -> cfb.CfbFile:
    """A container whose top-level table carries the ``IPM.Note`` class and ``entries``."""
    table = mapi_table.message_table(
        [
            mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE)),
            *entries,
        ],
        recipients=recipients,
        codepages=codepages,
    )
    return _open(
        stream("__properties_version1.0", table),
        stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), _IPM_NOTE),
        *children,
    )


# ============================================================ 1. the property tables


def test_property_tables_use_the_32_and_8_byte_headers() -> None:
    top = mapi_table.message_table(
        [mapi_table.long_entry(0x6200, 7), mapi_table.long_entry(0x6201, 9)],
        recipients=2,
        attachments=3,
        codepages=None,
    )
    table = mapi.parse_property_table(top, header_size=32)
    assert table.header_size == 32
    assert len(table.header) == 32
    assert [entry.offset for entry in table.entries] == [32, 48]
    assert mapi.declared_counts(table) == (2, 3)
    assert table.fault is None

    sub = mapi_table.sub_table([mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 1)])
    parsed = mapi.parse_property_table(sub, header_size=8)
    assert parsed.header_size == 8
    assert len(parsed.header) == 8
    assert [entry.offset for entry in parsed.entries] == [8]

    # ``(size - header) % 16 != 0`` records the misfit and decodes every complete entry;
    # the loop is bounded by the bytes present, never a declared count (D3).
    misfit = mapi.parse_property_table(top + b"\x00" * 5, header_size=32)
    assert misfit.fault == mapi.FAULT_TABLE_SIZE_MISFIT
    assert [entry.offset for entry in misfit.entries] == [32, 48]

    # A stream shorter than its header is a misfit too, with no entries.
    short = mapi.parse_property_table(b"\x00" * 16, header_size=32)
    assert short.fault == mapi.FAULT_TABLE_SIZE_MISFIT
    assert short.entries == ()


def test_entry_decode_fixed_variable_and_storage_backed() -> None:
    payload = mapi_table.utf16("subject value")
    binary = b"\x01\x02\x03\x04"
    table_bytes = mapi_table.message_table(
        [
            mapi_table.long_entry(0x6200, 7),
            mapi_table.variable_entry(0x0037, PT_UNICODE, len(payload)),
            mapi_table.storage_entry(0x3701, PT_OBJECT),
            mapi_table.variable_entry(0x6523, PT_BINARY, len(binary)),
        ],
        codepages=None,
    )
    opened = _open(
        stream("__properties_version1.0", table_bytes),
        stream("__substg1.0_0037001F", payload),
        stream("__substg1.0_65230102", binary),
    )
    table = mapi.parse_property_table(table_bytes, header_size=32)
    props = {prop.tag: prop for prop in (mapi.decode_entry(e, opened) for e in table.entries)}

    fixed = props[0x6200]
    assert fixed.value == 7
    assert fixed.type_hex == "0003"
    assert fixed.text is None and fixed.storage is None and fixed.fault is None

    variable = props[0x0037]
    assert variable.text.text == "subject value"
    assert variable.type_hex == "001f"
    assert variable.byte_length == len(payload)
    assert variable.raw_sha256 == hashlib.sha256(payload).hexdigest()

    backing = props[0x3701]
    assert backing.storage == "__substg1.0_3701000D"
    assert backing.value is None and backing.text is None and backing.fault is None

    blob = props[0x6523]
    assert blob.byte_length == len(binary)
    assert blob.raw_sha256 == hashlib.sha256(binary).hexdigest()
    assert blob.text is None and blob.value is None and blob.fault is None


# =============================================================== 2. the class gate


#: (class text, expected verdict) -- D6's boundary cases, the empty class included.
CLASS_CASES = (
    ("IPM.Note", "ipm_note"),
    ("ipm.note", "ipm_note"),
    ("iPm.NoTe", "ipm_note"),
    ("IPM.Note.Subject", "ipm_note"),
    ("IPM.Notebook", "not_ipm_note"),
    ("IPM.NoteX", "not_ipm_note"),
    ("IPM.Note.SMIME", "signed_or_encrypted"),
    ("IPM.Note.SMIME.MultipartSigned", "signed_or_encrypted"),
    ("IPM.Note.Secure", "signed_or_encrypted"),
    ("IPM.Appointment", "not_ipm_note"),
    ("", "class_absent"),
)


def _class_message(class_text: "str | None") -> cfb.CfbFile:
    """A container carrying exactly one class value (``None`` = no class entry at all)."""
    if class_text is None:
        return _open(stream("__properties_version1.0", mapi_table.message_table([], codepages=None)))
    raw = mapi_table.utf16(class_text) if class_text else b"\x00\x00"
    table = mapi_table.message_table(
        [mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(raw))],
        codepages=None,
    )
    return _open(
        stream("__properties_version1.0", table),
        stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), raw),
    )


def test_the_class_gate_records_the_class_verbatim() -> None:
    for text, verdict in CLASS_CASES:
        assert mapi.classify_class(text) == verdict, text

    for text, verdict in CLASS_CASES:
        msg = mapi.read_message(_class_message(text))
        assert msg.class_verdict == verdict, text
        assert msg.message_class == text, (text, msg.message_class)
        assert msg.stopped == (verdict != "ipm_note")
        raised = mapi.MSG_CLASS_NOT_IPM_NOTE in msg.observations
        assert raised == (verdict in ("not_ipm_note", "signed_or_encrypted")), text

    # The verdict vocabulary is closed and each of its five members is reachable.
    assert set(CLASS_CASES) and {v for _, v in CLASS_CASES} <= set(mapi.CLASS_VERDICTS)

    # An unreadable class value is its own verdict, not an exception (D1/D6).
    assert mapi.classify_class(None, mapi.FAULT_UTF16_ODD_LENGTH) == "class_unreadable"

    # A message with no class at all is ``class_absent`` (D6), not ``ipm_note``.
    missing = mapi.read_message(_class_message(None))
    assert missing.class_verdict == "class_absent"
    assert missing.message_class is None
    assert missing.observations == ()


def test_the_class_gate_stops_before_recipients_and_properties(monkeypatch) -> None:
    """D6: for any verdict but ``ipm_note`` nothing past the class is opened."""

    def boom(*args, **kwargs):
        raise AssertionError("the class gate let a recipient or property decoder run")

    monkeypatch.setattr(mapi, "decode_entry", boom)
    monkeypatch.setattr(mapi, "read_recipients", boom)
    for name in ("msg_non_ipm_note", "msg_signed_class"):
        msg = mapi.read_message(_fixture(name))
        assert msg.stopped is True, name
        assert msg.class_verdict in ("not_ipm_note", "signed_or_encrypted"), name
        assert msg.properties == () and msg.recipients == (), name


# ========================================================== 3. named properties (D5)


def test_named_properties_are_recognised_not_resolved() -> None:
    expected = msg_construction.MAPI_EXPECTATIONS["msg_named_properties"]
    msg = mapi.read_message(_fixture("msg_named_properties"))
    assert list(msg.named_tags) == expected["named_tags"]
    assert msg.nameid_present is expected["nameid_present"]
    assert list(msg.nameid_sizes) == expected["nameid_sizes"]
    assert list(msg.observations) == expected["observations"]

    # Recognised, never resolved: the tag number is not an identity (D5), so it is hex
    # only and it is *not* an unknown tag either.
    assert msg.unknown_tags == ()
    named = [prop for prop in msg.properties if prop.named]
    assert [prop.tag_hex for prop in named] == ["8005"]
    assert named[0].name is None
    # ... and it is still decoded per its own type (D5).
    assert named[0].text.text == "named property value"

    # The nameid storage's three streams' sizes are recorded; contents never parsed.
    assert mapi.named_properties(_fixture("msg_named_properties")) == (True, (160, 440, 3090))
    assert mapi.named_properties(_fixture("msg_unknown_tags")) == (False, ())


# =============================================================== 4. recipients (D7)


def _recipient(index: int, entries, children) -> object:
    return storage(
        f"__recip_version1.0_#{index:08X}",
        stream("__properties_version1.0", mapi_table.sub_table(entries)),
        *children,
    )


def test_recipients_are_read_from_the_recipient_tables() -> None:
    ada = mapi_table.utf16("Ada Lovelace")
    smtp_type = mapi_table.utf16("SMTP")
    ada_smtp = mapi_table.utf16("ada@example.test")
    exchange = mapi_table.utf16("/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2")
    first = _recipient(
        0,
        [
            mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 1),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_DISPLAY, PT_UNICODE, len(ada)),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_ADDRESS_TYPE, PT_UNICODE, len(smtp_type)),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_SMTP, PT_UNICODE, len(ada_smtp)),
        ],
        [
            stream("__substg1.0_3001001F", ada),
            stream("__substg1.0_3002001F", smtp_type),
            stream("__substg1.0_39FE001F", ada_smtp),
        ],
    )
    second = _recipient(
        1,
        [
            mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 3),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_DISPLAY, PT_UNICODE, len(mapi_table.utf16("Grace"))),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_ADDRESS_TYPE, PT_UNICODE, len(mapi_table.utf16("EX"))),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_EMAIL, PT_UNICODE, len(exchange)),
        ],
        [
            stream("__substg1.0_3001001F", mapi_table.utf16("Grace")),
            stream("__substg1.0_3002001F", mapi_table.utf16("EX")),
            stream("__substg1.0_3003001F", exchange),
        ],
    )
    msg = mapi.read_message(_message(first, second, recipients=2))

    assert msg.declared_recipient_count == 2
    assert msg.recipient_row_count == 2
    assert [row.index for row in msg.recipients] == [0, 1]
    assert [row.kind for row in msg.recipients] == ["to", "bcc"]
    assert msg.recipients[0].display_name.text == "Ada Lovelace"
    assert msg.recipients[0].address_type == "smtp"
    assert msg.recipients[0].address.text == "ada@example.test"
    assert msg.recipients[1].address_type == "ex"
    assert msg.recipients[1].address.text == "/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2"
    assert mapi.MSG_RECIPIENT_TABLE_UNREADABLE not in msg.observations

    # An unmodelled recipient type keeps the raw integer with ``kind = unknown`` (D7).
    odd = _recipient(
        0,
        [mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 9)],
        [],
    )
    odd_msg = mapi.read_message(_message(odd, recipients=1))
    assert odd_msg.recipients[0].kind == "unknown"
    assert odd_msg.recipients[0].kind_raw == 9


# =========================================================== 5. unknown tags (D4)


def test_an_unknown_tag_is_hex_only() -> None:
    expected = msg_construction.MAPI_EXPECTATIONS["msg_unknown_tags"]
    msg = mapi.read_message(_fixture("msg_unknown_tags"))
    assert list(msg.unknown_tags) == expected["unknown_tags"]
    assert list(msg.observations) == expected["observations"]

    names = {prop.key: prop.name for prop in msg.properties}
    for pair in msg.unknown_tags:
        tag_hex, separator, type_hex = pair.partition(":")
        assert separator == ":"
        assert len(tag_hex) == 4 and len(type_hex) == 4
        assert pair == pair.lower()
        assert prop_known(msg, pair) is False
        assert names[pair] is None

    # One aggregate observation for the message, never one gap per property (D4).
    assert msg.observations.count(mapi.MSG_PROPERTY_TAG_UNKNOWN) == 1
    assert len(msg.unknown_tags) == 4


def prop_known(msg: "mapi.MapiMessage", pair: str) -> bool:
    """Whether the message decoded a property with this ``tag:type`` key as known."""
    for prop in msg.properties:
        if prop.key == pair:
            return prop.known
    raise AssertionError(f"no property with key {pair!r}")


# ======================================== the hand-built Outlook layout (the breaker)


def test_the_handbuilt_outlook_layout_matches_the_b1_b4_values() -> None:
    """The values typed from B1-B4 before ``mapi.py`` ran, on the hand-built fixture.

    The fixture carries no class, so its gate stops: the reading is taken from the
    building blocks (the table, the entries, the recipients, the nameid sizes).
    """
    opened = _fixture("msg_outlook_layout_handbuilt")
    data, status = cfb.read_stream(opened, cfb.PROPERTIES_STREAM)
    assert status == cfb.FAULT_OK
    table = mapi.parse_property_table(data, header_size=32)

    # The header's counts at @16/@20 (B2): one recipient and one attachment.
    assert mapi.declared_counts(table) == (1, 1)
    # 0x3FDE / 0x3FFD are fixed entries (B4), not streams.
    assert mapi.decode_entry(table.first(0x3FDE), opened).value == 1252
    assert mapi.decode_entry(table.first(0x3FFD), opened).value == 1252
    assert [entry.path for entry in opened.entries if entry.path.startswith("__substg1.0_3FDE")] == []
    assert [entry.path for entry in opened.entries if entry.path.startswith("__substg1.0_3FFD")] == []

    # The ``0102`` HTML body stream is present at its typed size (B1/B3).
    html = cfb.lookup_entry(opened.entries, "__substg1.0_10130102")
    assert html is not None and html.size == 160

    # One recipient, read from the directory.
    rows = mapi.read_recipients(opened)
    assert len(rows) == 1
    assert rows[0].index == 0
    assert rows[0].name == "__recip_version1.0_#00000000"

    # ``__nameid_version1.0``'s three streams at B1's sizes (contents never parsed, D5).
    assert mapi.named_properties(opened) == (True, (160, 440, 3090))



