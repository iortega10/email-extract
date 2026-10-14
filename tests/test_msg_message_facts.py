"""Turn 1b.6: the message-level facts -- subject, sender and the mapped observations.

A ``.msg`` now publishes one frozen ``message_facts`` attribute beside the headers (D1):
the subject fact (D3), the sender fact (D4) and, in ``tests/test_msg_recipients.py`` and
``tests/test_msg_time.py``, the recipient and time facts. Nothing consumes the attribute
yet (the oracle measurers are Turn 1b.10); these tests hold it against the fixtures and
against the independent ``mapi`` records, and check the observation-to-gap mapping (D8)
that Turn 1b.5 left half done.

The three declared tests are:

* ``test_subject_sender_and_class_are_mapi_properties`` -- D3/D4/D6: the property texts,
  the canonical subject and the sender's raw fields, all ``value_source=mapi_property``;
* ``test_the_property_versus_header_conflict_pair_is_recorded`` -- D3 and the 1b.5 gap
  ``headers.mapi_header_property_disagree`` unchanged;
* ``test_message_class_is_recorded_verbatim`` -- the class beside the facts;

plus four extras: the class gate leaving no facts, the D8 observation mapping with its
deterministic order, determinism under two ``PYTHONHASHSEED`` values, and a seeded fuzz
of the recipient tables and the time entries.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402
from emailextract import cfb, mapi  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.msgcontainer import (  # noqa: E402
    GAP_MAPI_HEADER_PROPERTY_DISAGREE,
    GAP_TRANSPORT_HEADERS_ABSENT,
    MessageFacts,
    MsgContainer,
    SenderFact,
    SubjectFact,
)
from emailextract.parse import Limits  # noqa: E402
from support import mapi_table  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()
PT_UNICODE = mapi_table.PT_UNICODE
_IPM_NOTE = mapi_table.utf16("IPM.Note")

#: The hand-typed subject texts (from ``tools/make_msg_fixtures.py``).
UNICODE_SUBJECT = "synthetic \u00fcnicode \u4e16\u754c subject \U0001f30d"
T16_HEADER_SUBJECT = " turn 1b.6 synthetic"
CONFLICT_PROPERTY_SUBJECT = "synthetic turn 1b.5 property subject"
CONFLICT_HEADER_SUBJECT = " turn 1b.5 synthetic"


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _container(name: str) -> MsgContainer:
    return MsgContainer(_bytes(name))


def _open(data: bytes) -> cfb.CfbFile:
    opened = cfb.open_cfb(data)
    assert isinstance(opened, cfb.CfbFile)
    return opened


def _message(*entries, children=(), recipients=0, codepages=None) -> bytes:
    """A hand-built ``IPM.Note`` message with the given top-level entries."""
    table = mapi_table.message_table(
        [
            mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE)),
            *entries,
        ],
        recipients=recipients,
        codepages=codepages,
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), _IPM_NOTE),
            *children,
        )
    )


def _sender_message() -> bytes:
    """A sender with all four tags: the ``/O=`` address and a distinct SMTP form (D4)."""
    name = mapi_table.utf16("Ada Lovelace")
    address_type = mapi_table.utf16("EX")
    address = mapi_table.utf16("/O=EXCHANGELABS/CN=RECIPIENTS/CN=ada")
    smtp = mapi_table.utf16("ada@example.test")
    return _message(
        mapi_table.variable_entry(0x0C1A, PT_UNICODE, len(name)),
        mapi_table.variable_entry(0x0C1E, PT_UNICODE, len(address_type)),
        mapi_table.variable_entry(0x0C1F, PT_UNICODE, len(address)),
        mapi_table.variable_entry(0x5D01, PT_UNICODE, len(smtp)),
        children=[
            stream("__substg1.0_0C1A001F", name),
            stream("__substg1.0_0C1E001F", address_type),
            stream("__substg1.0_0C1F001F", address),
            stream("__substg1.0_5D01001F", smtp),
        ],
    )


# ------------------------------------------------------------ the declared tests


def test_subject_sender_and_class_are_mapi_properties() -> None:
    """D3/D4: the subject, sender and class are MAPI-side facts, not header records."""
    # A subject that exists only as the 0x0037 property: canonical is the property itself.
    unicode_fact = _container("msg_unicode_subject").message_facts.subject
    assert unicode_fact == SubjectFact(
        property_text=UNICODE_SUBJECT,
        property_fault=None,
        header_text=None,
        canonical="mapi_property",
        value_source="mapi_property",
    )
    # ... and the message class is beside it, verbatim (D6's message_class fact).
    assert _container("msg_unicode_subject").container_facts()["message_class"] == "IPM.Note"

    # A subject that also has a header field: the header text is recorded verbatim
    # (leading space kept) and it is canonical, while no property exists.
    header_fact = _container("msg_recipients_display_only").message_facts.subject
    assert header_fact == SubjectFact(
        property_text=None,
        property_fault=None,
        header_text=T16_HEADER_SUBJECT,
        canonical="transport_header",
        value_source="transport_header",
    )

    # The sender: raw fields, and ``smtp_address`` is only ever the 0x5D01 value -- it is
    # never derived from ``address`` (D4).
    sender = MsgContainer(_sender_message()).message_facts.sender
    assert sender == SenderFact(
        name="Ada Lovelace",
        address_type="EX",
        address="/O=EXCHANGELABS/CN=RECIPIENTS/CN=ada",
        smtp_address="ada@example.test",
        value_source="mapi_property",
    )

    # A message with no sender tags still publishes the fact, with every field None.
    empty = _container("msg_plain_and_html").message_facts.sender
    assert empty == SenderFact(None, None, None, None, value_source="mapi_property")

    # The facts sit *beside* the headers: the recipient fixture's headers are still the
    # 0x007D fields, and nothing from the recipient rows leaked into them (D2/D13).
    document = assemble(_container("msg_recipients_display_only"), limits=LIMITS)
    assert [field.name for field in document.headers] == ["Subject", "From", "Date"]
    assert _container("msg_recipients_display_only").message_facts.recipients[0].value_source == (
        "mapi_property"
    )


def test_the_property_versus_header_conflict_pair_is_recorded() -> None:
    """D3: both texts are kept verbatim and the 1b.5 disagreement gap is unchanged."""
    container = _container("msg_property_vs_header_conflict")
    fact = container.message_facts.subject
    assert fact.property_text == CONFLICT_PROPERTY_SUBJECT
    assert fact.header_text == CONFLICT_HEADER_SUBJECT
    assert fact.canonical == "transport_header"
    assert fact.value_source == "transport_header"
    assert fact.property_fault is None

    # The property text is carried by the fact and by the gap -- one id, unchanged.
    gaps = {gap.gap_id: gap.detail for gap in container.container_gaps}
    assert gaps[GAP_MAPI_HEADER_PROPERTY_DISAGREE] == CONFLICT_PROPERTY_SUBJECT


def test_message_class_is_recorded_verbatim() -> None:
    """The class is verbatim in the facts for every readable message, ipm or not."""
    for name, expected in (
        ("msg_unicode_subject", "IPM.Note"),
        ("msg_recipients_ex_no_smtp", "IPM.Note"),
        ("msg_non_ipm_note", "IPM.Appointment"),
        ("msg_signed_class", "IPM.Note.SMIME.MultipartSigned"),
    ):
        assert _container(name).container_facts()["message_class"] == expected, name


# -------------------------------------------------------------------- the extras


def test_the_class_gate_leaves_no_message_facts() -> None:
    """D6: a stopped message publishes no subject, sender, recipient or time record."""
    for name in ("msg_non_ipm_note", "msg_signed_class"):
        container = _container(name)
        assert container.message_facts == MessageFacts(None, None, (), ())
        facts = container.container_facts()
        assert "recipient_count" not in facts
        assert not [key for key in facts if key.startswith("time.")]
        assert facts["message_class"]  # the class itself is still recorded
        assert [gap for gap in container.container_gaps if gap.gap_id == "msg.class_not_ipm_note"]


def _gap_message() -> bytes:
    """One message carrying all four message-level observations at once (D8)."""
    named = mapi_table.utf16("named property value")
    transport = b"synthetic 1b.6 header text"
    table = mapi_table.message_table(
        [
            mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE)),
            mapi_table.long_entry(0x6200, 7),
            mapi_table.variable_entry(0x8005, PT_UNICODE, len(named)),
            mapi_table.variable_entry(0x007D, mapi_table.PT_STRING8, len(transport)),
        ],
        recipients=5,
        codepages=(9999, 9999),
    )
    row = storage(
        "__recip_version1.0_#00000000",
        stream("__properties_version1.0", mapi_table.sub_table([mapi_table.long_entry(0x0C15, 1)])),
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), _IPM_NOTE),
            stream("__substg1.0_8005001F-00000000", named),
            stream("__substg1.0_007D001E", transport),
            row,
        )
    )


def test_the_observation_gaps_are_mapped_once_each() -> None:
    """D8: the four message-level observations become gaps, in ``OBSERVATION_IDS`` order."""
    container = MsgContainer(_gap_message())
    assert [(gap.gap_id, gap.detail) for gap in container.container_gaps] == [
        # ``mapi.OBSERVATION_IDS`` order: the class gate's own is absent (the gate opened).
        ("msg.property_tag_unknown", "6200:0003"),
        ("msg.named_property_unresolved", "8005"),
        ("msg.codepage_unresolved_ladder_used", ""),
        ("msg.recipient_table_unreadable", "declared=5 rows=1"),
    ]
    # Each is emitted once, never per property or per pair.
    ids = [gap.gap_id for gap in container.container_gaps]
    assert len(ids) == len(set(ids))

    # A fixture with a 1b.5 gap too: the mapped gaps follow the 1b.5 ones.
    unknown = _container("msg_unknown_tags")
    assert [(gap.gap_id, gap.detail) for gap in unknown.container_gaps] == [
        (GAP_TRANSPORT_HEADERS_ABSENT, ""),
        ("msg.property_tag_unknown", "6200:0003,6523:0102,6748:0014,6827:001f"),
    ]

    # A clean message carries none of the four (its own 1b.5 gaps, if any, stay theirs).
    clean = _container("msg_plain_and_html")
    assert [gap.gap_id for gap in clean.container_gaps if gap.gap_id.startswith("msg.")] == []


def test_the_facts_are_deterministic_across_hash_seeds() -> None:
    """The key order and every value are identical under two ``PYTHONHASHSEED`` values."""
    script = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from pathlib import Path\n"
        "from emailextract.msgcontainer import MsgContainer\n"
        "msg = Path(sys.argv[1]) / 'fixtures' / 'msg'\n"
        "out = {}\n"
        "for name in ('msg_recipients_bcc_duplicates', 'msg_time_property_vs_date_header',\n"
        "             'msg_unicode_subject', 'msg_unknown_tags'):\n"
        "    c = MsgContainer((msg / (name + '.msg')).read_bytes())\n"
        "    facts = c.container_facts()\n"
        "    out[name] = [list(facts.items()),\n"
        "                 [list(r) for r in c.message_facts.recipients],\n"
        "                 list(c.message_facts.subject),\n"
        "                 [list(t) for t in c.message_facts.times],\n"
        "                 [[g.gap_id, g.detail] for g in c.container_gaps]]\n"
        "print(json.dumps(out, sort_keys=True, ensure_ascii=False))\n"
    )
    baseline = None
    for seed in ("0", "1234567"):
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"},
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        if baseline is None:
            baseline = payload
        else:
            assert payload == baseline, seed


def test_a_seeded_fuzz_of_the_message_facts_closes() -> None:
    """Mutants of the recipient tables and the time entries never raise; all strings encode."""
    seeds = (3, 11, 29)
    rng = random.Random(20261014)
    names = (
        "msg_recipients_bcc_duplicates",
        "msg_recipients_ex_no_smtp",
        "msg_time_property_vs_date_header",
    )
    produced = 0
    mutants = 0
    for name in names:
        data = _bytes(name)
        for _ in range(50):
            mutant = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                mutant[rng.randrange(len(mutant))] = rng.randrange(256)
            mutant = bytes(mutant)
            mutants += 1
            container = MsgContainer(mutant)
            document = assemble(container, limits=LIMITS)
            assert document.container_kind.value == "cfb_msg"
            for value in container.container_facts().values():
                value.encode("utf-8")
            assert document.status.status is not None
            assert container.message_facts.subject is None or isinstance(
                container.message_facts.subject.property_text, (str, type(None))
            )
            produced += 1
    assert mutants >= 100, mutants
    assert produced > 0, "the fuzz produced no mutant that reached the facts"
    assert len(seeds) == 3

    # A ``PT_SYSTIME`` entry whose table is cut mid-entry is a recorded fault, never a
    # ``struct.error`` (the entry loop is bounded by the bytes present). The fixed value is
    # always eight bytes, so the only wrong-length form is a truncated table.
    entry = mapi_table.fixed_entry(0x0039, mapi_table.PT_SYSTIME, (1).to_bytes(8, "little"))
    table = mapi_table.message_table(
        [mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE)), entry],
        codepages=None,
    )
    truncated = build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table[:-4]),
            stream(mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE), _IPM_NOTE),
        )
    )
    container = MsgContainer(truncated)
    assert container.message_facts.times == ()
    opened = _open(truncated)
    message = mapi.read_message(opened)
    assert message.property_fault == mapi.FAULT_TABLE_SIZE_MISFIT
    document = assemble(container, limits=LIMITS)
    assert document.container_kind.value == "cfb_msg"
    assert hashlib.sha256(container.raw_bytes()).hexdigest()
