"""Turn 1b.6: the recipient rows as facts, beside the headers and never merged (D5/D6).

One record per ``__recip_version1.0_#XXXXXXXX`` directory row, in index order, duplicates
kept: ``kind``/``kind_raw``, the display name, ``address`` (``0x3003`` as stored),
``address_type``/``address_type_raw``, ``smtp_address`` (``0x39FE`` when present), the
row's fault and ``value_source = mapi_property``. ``recipient_count`` is the number of
directory rows, never the declared count (the disagreement is the registered
``msg.recipient_table_unreadable`` gap).

The two declared tests are ``test_recipients_are_facts_beside_the_headers`` and
``test_display_only_and_ex_recipients_are_recorded``; the three extras are the ``olefile``
cross-check, the count-versus-declared check and a faulted row's gap.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.msgcontainer import ContainerGap, MsgContainer, RecipientFact  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from support import mapi_table, olefile_oracle  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()
PT_UNICODE = mapi_table.PT_UNICODE
_IPM_NOTE = mapi_table.utf16("IPM.Note")
GAP_RECIPIENT_TABLE = "msg.recipient_table_unreadable"

#: The hand-typed records (from ``tools/make_msg_fixtures.py`` and the fixture catalogue,
#: not from the reader).
DISPLAY_ONLY = [
    RecipientFact("to", 1, "Ada Lovelace", None, "smtp", "SMTP", None, None, "mapi_property"),
]
EX_NO_SMTP = [
    RecipientFact(
        "to",
        1,
        "Grace Hopper",
        "/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2",
        "ex",
        "EX",
        None,
        None,
        "mapi_property",
    ),
]
BCC_DUPLICATES = [
    RecipientFact(
        "to", 1, "Ada Lovelace", "ada@example.test", "smtp", "SMTP", None, None, "mapi_property"
    ),
    RecipientFact(
        "bcc", 3, "Grace Hopper", "grace@example.test", "smtp", "SMTP", None, None, "mapi_property"
    ),
    RecipientFact(
        "to", 1, "Ada Lovelace", "ada@example.test", "smtp", "SMTP", None, None, "mapi_property"
    ),
]


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str) -> MsgContainer:
    return MsgContainer(_bytes(name))


def _recipient(index: int, *, kind: int = 1, display=None, address_type=None, email=None,
               with_table: bool = True):
    """One recipient storage, its table and its ``__substg1.0`` streams (test-built)."""
    entries = [mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, kind)]
    children = []
    for tag, text in (
        (mapi_table.PROP_RECIPIENT_DISPLAY, display),
        (mapi_table.PROP_RECIPIENT_ADDRESS_TYPE, address_type),
        (mapi_table.PROP_RECIPIENT_EMAIL, email),
    ):
        if text is None:
            continue
        data = mapi_table.utf16(text)
        entries.append(mapi_table.variable_entry(tag, PT_UNICODE, len(data)))
        children.append(stream(mapi_table.substg_name(tag, PT_UNICODE), data))
    if with_table:
        children.insert(0, stream("__properties_version1.0", mapi_table.sub_table(entries)))
    return storage(f"__recip_version1.0_#{index:08X}", *children)


def _message(*children, recipients: int = 0) -> bytes:
    """A hand-built ``IPM.Note`` message with the given children."""
    table = mapi_table.message_table(
        [mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE))],
        recipients=recipients,
        codepages=None,
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), _IPM_NOTE),
            *children,
        )
    )


# ------------------------------------------------------------ the declared tests


def test_recipients_are_facts_beside_the_headers() -> None:
    """D5/D6: the rows are facts, in index order, duplicates kept, never merged with headers."""
    container = _container("msg_recipients_bcc_duplicates")
    assert list(container.message_facts.recipients) == BCC_DUPLICATES
    # The duplicate is two records, not one; the order is the directory's, not sorted.
    assert [row.display_name for row in container.message_facts.recipients] == [
        "Ada Lovelace",
        "Grace Hopper",
        "Ada Lovelace",
    ]
    # The count is the directory's row count.
    assert container.container_facts()["recipient_count"] == "3"

    # They sit beside the headers, which are still only the 0x007D fields (D2/D13).
    document = assemble(container, limits=LIMITS)
    assert [field.name for field in document.headers] == ["Subject", "From", "Date"]
    assert all(row.value_source == "mapi_property" for row in container.message_facts.recipients)


def test_display_only_and_ex_recipients_are_recorded() -> None:
    """D5: an address-less row and an Exchange row keep their own forms, verbatim."""
    display_only = _container("msg_recipients_display_only").message_facts.recipients
    assert list(display_only) == DISPLAY_ONLY
    assert display_only[0].address is None and display_only[0].smtp_address is None

    exchange = _container("msg_recipients_ex_no_smtp").message_facts.recipients
    assert list(exchange) == EX_NO_SMTP
    # The raw address form is kept in ``address``; ``smtp_address`` is only the 0x39FE tag.
    assert exchange[0].address == "/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2"
    assert exchange[0].smtp_address is None
    assert exchange[0].address_type == "ex" and exchange[0].address_type_raw == "EX"


# -------------------------------------------------------------------- the extras


def test_the_recipient_records_match_the_olefile_oracle() -> None:
    """``olefile`` reads the same rows independently; the two agree field for field."""
    for name, expected in (
        ("msg_recipients_display_only", DISPLAY_ONLY),
        ("msg_recipients_ex_no_smtp", EX_NO_SMTP),
        ("msg_recipients_bcc_duplicates", BCC_DUPLICATES),
    ):
        data = _bytes(name)
        records = _container(name).message_facts.recipients
        assert len(records) == len(expected), name
        for index, record in enumerate(records):
            base = f"__recip_version1.0_#{index:08X}"
            streams = {
                suffix: olefile_oracle.stream_bytes(data, f"{base}/__substg1.0_{suffix}")
                for suffix in ("3001001F", "3002001F", "3003001F")
                if _has_stream(data, f"{base}/__substg1.0_{suffix}")
            }
            display = streams.get("3001001F")
            address_type = streams.get("3002001F")
            address = streams.get("3003001F")
            assert record.display_name == (display.decode("utf-16-le") if display else None), name
            assert record.address_type_raw == (
                address_type.decode("utf-16-le") if address_type else None
            ), name
            assert record.address == (address.decode("utf-16-le") if address else None), name


def _has_stream(data: bytes, path: str) -> bool:
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    return cfb.lookup_entry(opened.entries, path) is not None


def test_recipient_count_is_the_directory_count_not_the_declared_count() -> None:
    """D6/D8: the reader trusts the directory; the disagreement is the registered gap."""
    # Five declared, one real row.
    mismatch = MsgContainer(
        _message(
            _recipient(0, display="Ada Lovelace", address_type="SMTP", email="ada@example.test"),
            recipients=5,
        )
    )
    assert mismatch.container_facts()["recipient_count"] == "1"
    # The 1b.5 transport-header gap comes first (no 0x007D here); the mapped one follows.
    assert [(gap.gap_id, gap.detail) for gap in mismatch.container_gaps] == [
        ("msg.transport_headers_absent", ""),
        (GAP_RECIPIENT_TABLE, "declared=5 rows=1"),
    ]

    # A message whose counts agree carries no such gap.
    agreeing = MsgContainer(
        _message(
            _recipient(0, display="Ada Lovelace", address_type="SMTP", email="ada@example.test"),
            recipients=1,
        )
    )
    assert agreeing.container_facts()["recipient_count"] == "1"
    assert GAP_RECIPIENT_TABLE not in {gap.gap_id for gap in agreeing.container_gaps}


def test_a_faulted_recipient_row_is_the_recipient_table_unreadable_gap() -> None:
    """D8: with no count disagreement, the gap's detail is the row's own fault."""
    faulted = MsgContainer(_message(_recipient(0, with_table=False), recipients=1))
    row = faulted.message_facts.recipients[0]
    assert row.fault == "stream_absent"
    assert faulted.container_gaps == (
        ContainerGap("msg.transport_headers_absent", ""),
        ContainerGap(GAP_RECIPIENT_TABLE, "stream_absent"),
    )
