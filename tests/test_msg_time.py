"""Turn 1b.6: the MAPI time properties as flat, lossless facts -- never ``TimeEvent``s (D7).

Each present ``PT_SYSTIME`` time property is exactly two ``container_facts`` keys, in
ascending tag order: ``time.<tag>.filetime_hex`` (the 16-digit lowercase hex of the raw
``u64``, the compared value) and ``time.<tag>.utc`` (an ISO-8601 rendering, whole seconds
truncated). A tag that is absent, of another type or faulted gets no keys. No time value is
interpreted (zero, sentinel, local versus UTC) and no ``TimeEvent`` is emitted: the MAPI
times and the ``Date`` header stay distinct.

The three declared tests are ``test_time_properties_are_flat_hex_keys``,
``test_the_filetime_hex_is_lossless_and_canonical`` and ``test_no_timeevent_is_emitted``;
the four extras are the three hand-computed FILETIME renderings (truncation, the epoch,
beyond the year range) and the untouched ``Date`` header.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb, mapi  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.ids import NOT_BUILT_IN_PHASE1  # noqa: E402
from emailextract.model import TriState  # noqa: E402
from emailextract.msgcontainer import MsgContainer, TimeFact  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from support import mapi_table  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()
PT_UNICODE = mapi_table.PT_UNICODE
PT_SYSTIME = mapi_table.PT_SYSTIME
_IPM_NOTE = mapi_table.utf16("IPM.Note")

#: 2026-10-11T12:34:56Z: 13_436_195_696 seconds after 1601-01-01, times 10^7 ticks/second.
SUBMIT_TICKS = 13_436_195_696 * 10_000_000
SUBMIT_HEX = "01dd597cebed5800"
#: The same value plus 0.9999999 s: truncation gives 12:34:56Z, rounding would give 12:34:57Z.
SUB_SECOND_TICKS = SUBMIT_TICKS + 9_999_999
#: The ``Date`` header of ``msg_time_property_vs_date_header``, deliberately disagreeing.
#: The field text is verbatim -- including the space after the colon.
DATE_HEADER = " Tue, 4 Mar 2025 08:00:00 +0000"


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str) -> MsgContainer:
    return MsgContainer(_bytes(name))


def _time_message(*entries) -> bytes:
    """A hand-built ``IPM.Note`` message carrying the given top-level table entries."""
    table = mapi_table.message_table(
        [
            mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE)),
            *entries,
        ],
        codepages=None,
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), _IPM_NOTE),
        )
    )


def _time_keys(container: MsgContainer) -> list[str]:
    return [key for key in container.container_facts() if key.startswith("time.")]


# ------------------------------------------------------------ the declared tests


def test_time_properties_are_flat_hex_keys() -> None:
    """D7: two flat keys per present time tag, in ascending tag order; nothing invented."""
    container = _container("msg_time_property_vs_date_header")
    facts = container.container_facts()
    assert _time_keys(container) == [
        "time.0039.filetime_hex",
        "time.0039.utc",
        "time.0e06.filetime_hex",
        "time.0e06.utc",
    ]
    assert facts["time.0039.filetime_hex"] == SUBMIT_HEX
    assert facts["time.0039.utc"] == "2026-10-11T12:34:56Z"
    assert facts["time.0e06.filetime_hex"] == SUBMIT_HEX
    assert list(container.message_facts.times) == [
        TimeFact("0039", SUBMIT_HEX, "2026-10-11T12:34:56Z"),
        TimeFact("0e06", SUBMIT_HEX, "2026-10-11T12:34:56Z"),
    ]

    # Only the tags that are *present* get keys: 0x0039 absent -> no ``time.0039.*`` key.
    only_delivery = MsgContainer(
        _time_message(mapi_table.fixed_entry(0x0E06, PT_SYSTIME, SUBMIT_TICKS.to_bytes(8, "little")))
    )
    assert _time_keys(only_delivery) == ["time.0e06.filetime_hex", "time.0e06.utc"]

    # A tag present with another type is not a time fact (no keys, no raise).
    wrong_type = MsgContainer(_time_message(mapi_table.long_entry(0x0039, 1234)))
    assert _time_keys(wrong_type) == []
    assert wrong_type.message_facts.times == ()


def test_the_filetime_hex_is_lossless_and_canonical() -> None:
    """D7: the hex is the raw ``u64``, 16 lowercase digits -- and it is the compared value."""
    container = _container("msg_time_property_vs_date_header")
    fact = container.container_facts()["time.0039.filetime_hex"]
    assert fact == SUBMIT_HEX == format(SUBMIT_TICKS, "016x")
    assert len(fact) == 16 and fact == fact.lower() and not fact.startswith("0x")

    # ... and it is ``Property.value_hex`` itself, over the same source bytes.
    opened = cfb.open_cfb(_bytes("msg_time_property_vs_date_header"))
    assert isinstance(opened, cfb.CfbFile)
    message = mapi.read_message(opened)
    prop = {entry.tag: entry for entry in message.properties}[0x0039]
    assert prop.value == SUBMIT_TICKS and prop.value_hex == fact


def test_no_timeevent_is_emitted() -> None:
    """D7: no ``TimeEvent`` and no ordering claim; ``times_axis`` keeps the not-built marker."""
    document = assemble(_container("msg_time_property_vs_date_header"), limits=LIMITS)
    assert document.times == []
    assert document.times_axis.state is TriState.UNKNOWN
    assert document.times_axis.reason_id == NOT_BUILT_IN_PHASE1
    assert document.times_axis.value is None


# -------------------------------------------------------------------- the extras


def test_the_filetime_rendering_truncates_the_sub_second_part() -> None:
    """A 0.9999999 s fraction truncates to the whole second, never rounds up to the next."""
    container = MsgContainer(
        _time_message(
            mapi_table.fixed_entry(0x0039, PT_SYSTIME, SUB_SECOND_TICKS.to_bytes(8, "little"))
        )
    )
    facts = container.container_facts()
    # 1601-01-01 + 13_436_195_696.9999999 s: the 100 ns remainder is dropped.
    assert facts["time.0039.filetime_hex"] == format(SUB_SECOND_TICKS, "016x")
    assert facts["time.0039.utc"] == "2026-10-11T12:34:56Z"


def test_the_filetime_epoch_renders_with_no_sentinel() -> None:
    """A raw ``0`` renders as the FILETIME epoch: no sentinel is interpreted (D7)."""
    container = MsgContainer(
        _time_message(mapi_table.fixed_entry(0x0039, PT_SYSTIME, (0).to_bytes(8, "little")))
    )
    facts = container.container_facts()
    assert facts["time.0039.filetime_hex"] == "0000000000000000"
    assert facts["time.0039.utc"] == "1601-01-01T00:00:00Z"


def test_a_filetime_beyond_the_year_range_is_unrepresentable() -> None:
    """A rendering past the year range is ``unrepresentable``; the hex is still present."""
    huge = 0xFFFFFFFFFFFFFFFF
    container = MsgContainer(
        _time_message(mapi_table.fixed_entry(0x0039, PT_SYSTIME, huge.to_bytes(8, "little")))
    )
    facts = container.container_facts()
    assert facts["time.0039.filetime_hex"] == "ffffffffffffffff"
    assert facts["time.0039.utc"] == "unrepresentable"


def test_the_date_header_is_kept_distinct_from_the_time_properties() -> None:
    """The ``Date`` header is verbatim and unreconciled: no ``Date`` parsing, no comparison."""
    container = _container("msg_time_property_vs_date_header")
    document = assemble(container, limits=LIMITS)
    dates = [field for field in document.headers if field.name == "Date"]
    assert len(dates) == 1 and dates[0].raw_value == DATE_HEADER
    # The MAPI time disagrees with it, and both are simply kept.
    assert document.times == []
    assert container.container_facts()["time.0039.utc"] == "2026-10-11T12:34:56Z"
    assert container.message_facts.recipients == ()
