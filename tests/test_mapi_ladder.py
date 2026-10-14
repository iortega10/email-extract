"""Turn 1b.4: the D2 string ladder -- the two code pages, the trailing NUL, the rungs.

The ladder's inputs are the raw bytes of an ``001E`` value plus the two code pages read
from the **fixed entries** ``0x3FDE`` (internet) and ``0x3FFD`` (message) of the
top-level table (``email-spike.md`` B4). The tests build both in memory with
``tests/support/mapi_table.py`` and read the fixture ``msg_codepage_disagree``, whose two
code pages disagree on one byte.

The declared tests are:

* ``test_the_ladder_reads_both_code_pages_as_fixed_entries``;
* ``test_internet_cpid_wins_over_message_cpid``;
* ``test_the_trailing_nul_is_stripped_and_recorded``;
* ``test_001e_goes_through_the_ladder_and_001f_is_utf16le``;
* ``test_ascii_and_utf8_rungs_record_their_source``;
* ``test_multivalued_strings_keep_every_value``.
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
from support import mapi_table  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
PT_STRING8 = mapi_table.PT_STRING8
PT_UNICODE = mapi_table.PT_UNICODE
_IPM_NOTE = mapi_table.utf16("IPM.Note")


def _open(*children) -> cfb.CfbFile:
    opened = cfb.open_cfb(build_cfb(storage("Root Entry", *children)))
    assert isinstance(opened, cfb.CfbFile), opened
    return opened


def _fixture(name: str) -> cfb.CfbFile:
    opened = cfb.open_cfb((MSG / f"{name}.msg").read_bytes())
    assert isinstance(opened, cfb.CfbFile), name
    return opened


def _message(*children, entries=(), recipients=0, codepages=None) -> cfb.CfbFile:
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


def _by_tag(msg: "mapi.MapiMessage") -> dict[int, "mapi.Property"]:
    return {prop.tag: prop for prop in msg.properties}


# ====================================================== 1. the code pages and the rungs


def test_the_ladder_reads_both_code_pages_as_fixed_entries() -> None:
    opened = _fixture("msg_codepage_disagree")
    msg = mapi.read_message(opened)
    assert msg.internet_cp == 28591
    assert msg.message_cp == 1252

    # Fixed entries, not streams (B4): no ``__substg1.0_3FDE*`` or ``__substg1.0_3FFD*``
    # stream exists in the container at all.
    assert [e.path for e in opened.entries if e.path.startswith("__substg1.0_3FDE")] == []
    assert [e.path for e in opened.entries if e.path.startswith("__substg1.0_3FFD")] == []

    data, _ = cfb.read_stream(opened, cfb.PROPERTIES_STREAM)
    table = mapi.parse_property_table(data, header_size=32)
    assert mapi.decode_entry(table.first(0x3FDE), opened).value == 28591
    assert mapi.decode_entry(table.first(0x3FFD), opened).value == 1252


def test_internet_cpid_wins_over_message_cpid() -> None:
    # The fixture: internet 28591 (iso-8859-1) against message 1252, disagreeing on 0x93.
    msg = mapi.read_message(_fixture("msg_codepage_disagree"))
    subject = _by_tag(msg)[0x0037]
    assert subject.text.encoding_source == "internet_cpid"
    assert subject.text.source_kind == "internet"
    assert subject.text.declared_cp == 28591
    # iso-8859-1 keeps 0x93 as U+0093 (cp1252 would make it U+201C).
    assert subject.text.text == "synthetic \u0093 subject"
    # Rung 1 fired, so the fall-through gap does not (D2), code pages notwithstanding.
    assert mapi.MSG_CODEPAGE_UNRESOLVED_LADDER_USED not in msg.observations

    # The other way round: internet 1252, message 28591, the same byte -- the internet
    # code page still wins and cp1252's curly quote is the one recorded.
    reversed_msg = mapi.read_message(
        _message(
            entries=[mapi_table.variable_entry(0x0037, PT_STRING8, len(b"synthetic \x93 subject"))],
            codepages=(1252, 28591),
            *[stream("__substg1.0_0037001E", b"synthetic \x93 subject")],
        )
    )
    other = _by_tag(reversed_msg)[0x0037]
    assert other.text.encoding_source == "internet_cpid"
    assert other.text.declared_cp == 1252
    assert other.text.text == "synthetic \u201c subject"


def test_the_trailing_nul_is_stripped_and_recorded() -> None:
    one = mapi.decode_string8(b"abc\x00", internet_codepage=1252, message_codepage=1252)
    assert one.text == "abc"
    assert one.trailing_nul is True
    # The digest is of the bytes *before* the strip.
    assert one.raw_sha256 == hashlib.sha256(b"abc\x00").hexdigest()

    two = mapi.decode_string8(b"abc\x00\x00", internet_codepage=1252, message_codepage=1252)
    assert two.text == "abc\x00"
    assert two.trailing_nul is True

    none = mapi.decode_string8(b"abc", internet_codepage=1252, message_codepage=1252)
    assert none.text == "abc"
    assert none.trailing_nul is False

    # A 001F value gets the same one-NUL strip (D2).
    unicode_one = mapi.decode_unicode("ab\x00".encode("utf-16-le"))
    assert unicode_one.text == "ab"
    assert unicode_one.trailing_nul is True


def test_001e_goes_through_the_ladder_and_001f_is_utf16le() -> None:
    string8 = b"ladder \xe9 text"
    unicode_bytes = mapi_table.utf16("unicode \u00e9 text")
    msg = mapi.read_message(
        _message(
            entries=[
                mapi_table.variable_entry(0x0037, PT_STRING8, len(string8)),
                mapi_table.variable_entry(0x0040, PT_UNICODE, len(unicode_bytes)),
            ],
            codepages=(28591, 1252),
            *[
                stream("__substg1.0_0037001E", string8),
                stream("__substg1.0_0040001F", unicode_bytes),
            ],
        )
    )
    props = _by_tag(msg)
    laddered = props[0x0037]
    assert laddered.type_hex == "001e"
    assert laddered.text.encoding_source == "internet_cpid"
    assert laddered.text.text == "ladder \u00e9 text"
    direct = props[0x0040]
    assert direct.type_hex == "001f"
    assert direct.text.encoding_source is None
    assert direct.text.source_kind is None
    assert direct.text.text == "unicode \u00e9 text"


def test_ascii_and_utf8_rungs_record_their_source() -> None:
    ascii_bytes = b"plain ascii"
    utf8_bytes = "\u00e9 utf8".encode("utf-8")
    msg = mapi.read_message(
        _message(
            entries=[
                mapi_table.variable_entry(0x0037, PT_STRING8, len(ascii_bytes)),
                mapi_table.variable_entry(0x0040, PT_STRING8, len(utf8_bytes)),
            ],
            # Neither code page resolves, so the ladder falls through (D2).
            codepages=(99999, 99998),
            *[
                stream("__substg1.0_0037001E", ascii_bytes),
                stream("__substg1.0_0040001E", utf8_bytes),
            ],
        )
    )
    props = _by_tag(msg)
    assert props[0x0037].text.encoding_source == "ascii"
    assert props[0x0037].text.source_kind == "none"
    assert props[0x0037].text.declared_cp is None
    assert props[0x0040].text.encoding_source == "utf8_strict"
    assert props[0x0040].text.text == "\u00e9 utf8"
    # Rungs 3 and 4 fired, so the gap fires once for the message (D2).
    assert msg.observations.count(mapi.MSG_CODEPAGE_UNRESOLVED_LADDER_USED) == 1


def test_multivalued_strings_keep_every_value() -> None:
    values = [b"first", b"second", b"third"]
    msg = mapi.read_message(
        _message(
            entries=[mapi_table.variable_entry(0x0037, PT_STRING8 | mapi_table.MV_FLAG, 0)],
            codepages=(20127, 20127),
            *[
                stream(mapi_table.multi_substg_name(0x0037, PT_STRING8, index), value)
                for index, value in enumerate(values)
            ],
        )
    )
    subject = _by_tag(msg)[0x0037]
    assert subject.multi_valued is True
    assert subject.text is None
    assert [text.text for text in subject.texts] == ["first", "second", "third"]
    assert all(text.encoding_source == "internet_cpid" for text in subject.texts)
