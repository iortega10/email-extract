"""Turn 1b.9: the 8-bit string ladder, the non-BMP text and the transport-header shapes.

The ladder (``mapi.decode_string8``, D2) is: the internet code page, then the message code
page, then all-bytes-ASCII, then strict UTF-8, then strict windows-1252, recording
``encoding_source`` = ``internet_cpid``/``message_cpid``/``ascii``/``utf8_strict``/
``windows_1252``. A fixture whose **internet** code page resolves fires ``internet_cpid`` no
matter which code page it is; the fall-through rungs fire only when no code page resolves.
The rung matrix below is typed before the code runs and every rung is a committed ``.msg``.

The four declared tests are:

* ``test_001e_code_pages_1252_20127_28591_65001``;
* ``test_internet_versus_message_codepage_disagreement``;
* ``test_non_bmp_surrogate_pairs_survive``;
* ``test_the_utf8_bom_and_lf_only_headers``;

plus the extras: the five-rung matrix, the multi-valued values, the ``001E`` body, the two
hostile UTF-16 shapes through the container, and the seeded fuzz.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402

from emailextract import cfb, mapi  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402
from emailextract.parse import Limits, parse  # noqa: E402
from support import mapi_table  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()

#: The rung matrix, typed before the fixtures run (D7): ``(fixture, internet cp, message cp,
#: rung, source_kind, declared_cp, expected text)``. The two code pages and the text are
#: typed from the ladder rules and the fixture's bytes, never read out of the reader.
RUNG_MATRIX = (
    ("msg_string8_1252", 1252, 1252, "internet_cpid", "internet", 1252,
     "synthetic \u201c string8 subject"),
    ("msg_string8_ascii20127", 20127, 20127, "internet_cpid", "internet", 20127,
     "synthetic ascii string8 subject"),
    ("msg_string8_utf8_65001", 65001, 65001, "internet_cpid", "internet", 65001,
     "synthetic \u00fcnicode \u4e16\u754c string8 subject"),
    ("msg_string8_message_cpid", 437, 1252, "message_cpid", "message", 1252,
     "synthetic \u201c string8 subject"),
    ("msg_string8_ascii_no_cp", None, None, "ascii", "none", None,
     "synthetic ascii string8 subject"),
    ("msg_string8_utf8_no_cp", None, None, "utf8_strict", "none", None,
     "synthetic \u00fcnicode \u4e16\u754c string8 subject"),
    ("msg_string8_windows_1252_no_cp", None, None, "windows_1252", "none", None,
     "synthetic \u201c string8 subject"),
)

#: The four numbers ``CODEPAGES`` resolves, each with the fixture that fires its internet rung.
CODE_PAGE_FIXTURES = {
    1252: "msg_string8_1252",
    20127: "msg_string8_ascii20127",
    28591: "msg_codepage_disagree",
    65001: "msg_string8_utf8_65001",
}

_CLASS = "IPM.Note"
_CLASS_BYTES = _CLASS.encode("utf-16-le")


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _subject(name: str) -> "mapi.TextValue":
    """The ``0x0037`` subject's decoded value through ``mapi`` (never the reader's text)."""
    opened = cfb.open_cfb(_bytes(name))
    assert isinstance(opened, cfb.CfbFile), name
    message = mapi.read_message(opened)
    prop = next(prop for prop in message.properties if prop.tag == 0x0037)
    assert prop.text is not None
    return prop.text


def _tool_msg(*, transport_name: str | None, transport_bytes: bytes | None, html: bytes) -> bytes:
    """A tiny ``IPM.Note`` with the named transport stream and a body (a test-built twin)."""
    table = mapi_table.message_table(
        [mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE, len(_CLASS_BYTES))]
    )
    children = [
        stream("__properties_version1.0", table),
        stream("__substg1.0_001A001F", _CLASS_BYTES),
    ]
    if transport_name is not None and transport_bytes is not None:
        children.append(stream(transport_name, transport_bytes))
    children.append(stream("__substg1.0_10130102", html))
    return build_cfb(storage("Root Entry", *children))


def _subject_only(payload: bytes) -> bytes:
    """An ``IPM.Note`` whose whole point is a ``001F`` ``0x0037`` stream of ``payload``."""
    table = mapi_table.message_table(
        [
            mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE, len(_CLASS_BYTES)),
            mapi_table.variable_entry(0x0037, mapi_table.PT_UNICODE, len(payload)),
        ],
        codepages=(1252, 1252),
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream("__substg1.0_001A001F", _CLASS_BYTES),
            stream("__substg1.0_0037001F", payload),
        )
    )


# ------------------------------------------------------- the declared tests


def test_001e_code_pages_1252_20127_28591_65001() -> None:
    """The four resolvable code pages all fire the internet rung, each with its own number."""
    assert set(CODE_PAGE_FIXTURES) == set(mapi.CODEPAGES)
    for number, name in CODE_PAGE_FIXTURES.items():
        opened = cfb.open_cfb(_bytes(name))
        assert isinstance(opened, cfb.CfbFile), name
        message = mapi.read_message(opened)
        assert message.internet_cp == number, (name, message.internet_cp)
        text = _subject(name)
        assert text.encoding_source == "internet_cpid", (name, text.encoding_source)
        assert text.source_kind == "internet", name
        assert text.declared_cp == number, (name, text.declared_cp)
        assert text.fault is None
    # The two code pages disagree on byte ``0x93``; the internet one (28591) wins.
    disagree = _subject("msg_codepage_disagree")
    assert disagree.text == "synthetic \u0093 subject"
    assert disagree.text != b"synthetic \x93 subject".decode("cp1252")


def test_internet_versus_message_codepage_disagreement() -> None:
    """D9: the internet code page wins; the loser is recorded in the facts, both published."""
    container = MsgContainer(_bytes("msg_codepage_disagree"))
    text = _subject("msg_codepage_disagree")
    assert (text.source_kind, text.declared_cp) == ("internet", 28591)
    assert text.text == "synthetic \u0093 subject"
    # The loser is the message code page, and both are published.
    facts = container.container_facts()
    assert facts["internet_codepage"] == "28591"
    assert facts["message_codepage"] == "1252"
    # The value's own record names the winner, so the loser is identifiable from it alone.
    assert text.encoding_source != "message_cpid"
    # The negative case: byte 0x93 under the losing code page is a different character.
    assert text.text != b"synthetic \x93 subject".decode("cp1252")


def test_non_bmp_surrogate_pairs_survive() -> None:
    """D8: a non-BMP code point survives as one code point; offsets count it once."""
    subject = "synthetic \U0001f600 non-bmp subject"
    assert subject.count("\U0001f600") == 1
    assert len(subject.encode("utf-16-le")) == 2 * (len(subject) + 1)  # a surrogate pair
    assert len(subject.encode("utf-8")) == len(subject) + 3  # the emoji is 4 UTF-8 bytes

    container = MsgContainer(_bytes("msg_non_bmp_text"))
    assert container.message_facts.subject.property_text == subject
    assert container.message_facts.subject.property_fault is None
    # The property stream's byte length counts the surrogate pair (2 UTF-16 units).
    prop = next(p for p in _properties("msg_non_bmp_text") if p.tag == 0x0037)
    assert prop.byte_length == 2 * (len(subject) + 1)
    # The transport ``Subject:`` line's span row counts the emoji once as a character and
    # twice as UTF-16 code units (source bytes), so the two units are one code point.
    line = f"Subject: {subject}\r\n"
    row = next(
        r
        for r in container.span_provenance
        if r.source_stream == "__substg1.0_007D001F" and r.decoded_char_offset == 0
    )
    assert row.decoded_char_len == len(line)
    assert row.source_byte_len == 2 * (len(line) + 1)
    assert row.virtual_len == len(line.encode("utf-8"))


def test_the_utf8_bom_and_lf_only_headers() -> None:
    """D9: the BOM and the LF-only transport parse to the twin's field list, byte for byte."""
    import make_msg_fixtures as mk

    html = mk.T15_HTML_BODY
    crlf = mk.T15_TRANSPORT_TEXT
    lf = mk.T15_TRANSPORT_LF_TEXT
    twin = assemble(
        MsgContainer(_tool_msg(transport_name="__substg1.0_007D001F", transport_bytes=crlf.encode("utf-16-le"), html=html)),
        limits=LIMITS,
    )
    twin_container = MsgContainer(
        _tool_msg(transport_name="__substg1.0_007D001F", transport_bytes=crlf.encode("utf-16-le"), html=html)
    )
    bom = assemble(MsgContainer(_bytes("msg_transport_headers_utf8_bom")), limits=LIMITS)
    bom_container = MsgContainer(_bytes("msg_transport_headers_utf8_bom"))
    # The same field list: no field lost, re-split or BOM-prefixed.
    assert [field.name for field in bom.headers] == [field.name for field in twin.headers]
    assert [field.raw_value for field in bom.headers] == [field.raw_value for field in twin.headers]
    assert bom.headers[0].name == "Subject"
    assert "\ufeff" not in bom.headers[0].name
    # The BOM is projected as its own 3-byte prelude region, and the rest is the twin verbatim.
    prelude = next(r for r in bom_container.span_provenance if r.source_stream == "synthetic:prelude:1")
    assert prelude.virtual_offset == 0 and prelude.virtual_len == 3
    assert bom_container.raw_bytes() == "\ufeff".encode("utf-8") + twin_container.raw_bytes()

    # The LF-only transport parses to the CRLF twin's field list; its own terminators stay.
    lf_twin = assemble(
        MsgContainer(
            _tool_msg(
                transport_name="__substg1.0_007D001F",
                transport_bytes=lf.replace("\n", "\r\n").encode("utf-16-le"),
                html=html,
            )
        ),
        limits=LIMITS,
    )
    lf_document = assemble(MsgContainer(_bytes("msg_transport_headers_lf_only")), limits=LIMITS)
    assert [field.name for field in lf_document.headers] == [field.name for field in lf_twin.headers]
    assert [field.raw_value for field in lf_document.headers] == [
        field.raw_value for field in lf_twin.headers
    ]
    assert len(lf_document.headers) == 2  # Subject and From; no third field is invented
    # The bare LF terminators are carried verbatim, so the projection has no CRLF there.
    assert b"Subject: turn 1b.5 synthetic\n" in MsgContainer(_bytes("msg_transport_headers_lf_only")).raw_bytes()


# ------------------------------------------------------- the extras


def _properties(name: str):
    opened = cfb.open_cfb(_bytes(name))
    assert isinstance(opened, cfb.CfbFile), name
    return mapi.read_message(opened).properties


def test_all_five_rungs_are_covered_by_a_committed_msg() -> None:
    """D7: the five ``encoding_source`` rungs are each a committed ``.msg``, rung by rung."""
    assert {row[3] for row in RUNG_MATRIX} == set(mapi.ENCODING_SOURCES)
    for name, internet, message, rung, kind, declared, text in RUNG_MATRIX:
        opened = cfb.open_cfb(_bytes(name))
        assert isinstance(opened, cfb.CfbFile), name
        message_obj = mapi.read_message(opened)
        assert message_obj.internet_cp == internet, (name, message_obj.internet_cp)
        assert message_obj.message_cp == message, (name, message_obj.message_cp)
        value = _subject(name)
        assert value.encoding_source == rung, (name, value.encoding_source, rung)
        assert value.source_kind == kind, (name, value.source_kind)
        assert value.declared_cp == declared, (name, value.declared_cp)
        assert value.text == text, (name, value.text)
        assert value.fault is None
    # The three fall-through rungs are exactly the ones the D2 gap fires for.
    fallthrough_fixtures = {
        row[0] for row in RUNG_MATRIX if row[3] in mapi.LADDER_FALLTHROUGH
    }
    assert fallthrough_fixtures == {
        "msg_string8_ascii_no_cp",
        "msg_string8_utf8_no_cp",
        "msg_string8_windows_1252_no_cp",
    }
    for name in fallthrough_fixtures:
        gaps = {gap.gap_id for gap in MsgContainer(_bytes(name)).container_gaps}
        assert mapi.MSG_CODEPAGE_UNRESOLVED_LADDER_USED in gaps, name
    # ... and the non-fall-through fixtures do not fire it.
    for name in ("msg_string8_1252", "msg_string8_message_cpid"):
        gaps = {gap.gap_id for gap in MsgContainer(_bytes(name)).container_gaps}
        assert mapi.MSG_CODEPAGE_UNRESOLVED_LADDER_USED not in gaps, name


def test_a_multivalued_string_keeps_every_value_in_order() -> None:
    """D8: a multi-valued property keeps every value, in ``-NNNNNNNN`` stream order."""
    expected = ("first multivalued value", "second multivalued value", "third multivalued value")
    prop = next(p for p in _properties("msg_multivalued_strings") if p.tag == 0x0037)
    assert prop.multi_valued is True
    assert prop.text is None
    assert tuple(value.text for value in prop.texts) == expected
    # None is merged or dropped, and each value is its own stream.
    assert len(prop.texts) == 3
    assert all(value.fault is None for value in prop.texts)


def test_a_string8_body_projects_as_utf8_with_the_ladder_rung() -> None:
    """D8: a ``0x1000`` plain body as ``001E`` re-encodes to UTF-8 and carries its rung."""
    container = MsgContainer(_bytes("msg_string8_body"))
    assert container.container_facts()["body_streams"] == "plain"
    document = assemble(container, limits=LIMITS)
    from emailextract.model import ContainerStreamAxis, EncodingSource

    plain = next(part for part in document.parts if part.content_type == "text/plain")
    assert plain.encoding_source is EncodingSource.INTERNET_CPID
    assert plain.decode_chain.used_charset == "utf-8"
    assert plain.decode_chain.declared_charset == "utf-8"
    assert plain.decode_chain.used_cte == "8bit"
    # The leaf's bytes are the UTF-8 re-encoding of the ladder's text.
    record = next(part for part in container.span_provenance if part.source_stream == "__substg1.0_1000001E")
    assert record.axis is ContainerStreamAxis.REENCODED
    assert record.decoded_char_len == len("synthetic turn 1b.9 string8 plain body \u00e9\r\n")


def test_the_two_hostile_utf16_shapes_go_through_the_container() -> None:
    """D10: a lone surrogate and an odd-length ``001F`` are recorded, never raised.

    Built in the test (never committed): a same-length byte patch cannot produce the
    odd-length shape, so both are built through the test-side writer the way
    ``tests/test_mapi_hostile.py`` builds its two. Through ``MsgContainer`` + ``assemble``:
    neither raises, the fault is recorded, and no replacement character appears.
    """
    for payload, fault in (
        (b"A\x00\x00\xd8", mapi.FAULT_UTF16_LONE_SURROGATE),
        (b"\x41\x00\x42", mapi.FAULT_UTF16_ODD_LENGTH),
    ):
        data = _subject_only(payload)
        # The entry point names it a ``.msg`` and the container reads it without raising.
        decision = parse(data, limits=LIMITS)
        assert decision.error is None, (fault, decision.error)
        container = MsgContainer(data)
        document = assemble(container, limits=LIMITS)
        subject = container.message_facts.subject
        assert subject.property_text is None
        assert subject.property_fault == fault, (fault, subject.property_fault)
        assert document.container_kind.value == "cfb_msg"
        assert document.status.status.value == "parsed"
        # No replacement character, and every published string is UTF-8 encodable.
        assert "\ufffd" not in repr(document)
        assert container.raw_bytes().decode("utf-8") is not None
        for key, value in container.container_facts().items():
            key.encode("utf-8")
            value.encode("utf-8")


def test_a_seeded_fuzz_of_the_string8_bytes_closes() -> None:
    """D7/D8: mutants of the ``001E`` bytes, the code pages and the MV prefixes never raise."""
    rng = random.Random(20261014)
    produced = 0
    for name in (
        "msg_string8_1252",
        "msg_string8_windows_1252_no_cp",
        "msg_string8_utf8_65001",
        "msg_multivalued_strings",
        "msg_string8_body",
    ):
        data = _bytes(name)
        for _ in range(45):
            mutant = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                mutant[rng.randrange(len(mutant))] = rng.randrange(256)
            mutant = bytes(mutant)
            decision = parse(mutant, limits=LIMITS)
            if decision.error is not None:
                assert decision.error.reason_id, name
                continue
            container = MsgContainer(mutant)
            for value in container.container_facts().values():
                value.encode("utf-8")
            document = assemble(container, limits=LIMITS)
            assert document.container_kind.value == "cfb_msg"
            for field in document.headers:
                field.name.encode("utf-8")
                field.raw_value.encode("utf-8")
            produced += 1
    assert produced > 150, produced
