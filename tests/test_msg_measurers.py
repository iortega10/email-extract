"""Turn 1b.10a: the eleven ``msg.*`` measurers, the ``.msg`` sidecars and their floors.

The measurers read the :class:`~emailextract.msgcontainer.MsgContainer` a ``.msg`` fixture was
walked through (D1); each asserts the **hand-typed** value of a named fixture (a value typed
from ``docs/design/phase1b-fixtures.md`` and ``tests/support/msg_construction.py``, never read
out of the measurer). The rest of the file is the corpus rules: every ``.msg`` sidecar loads and
names only declared facts, every ``.msg`` fixture has a sidecar or a recorded exemption, the
``.eml`` measurement is unchanged, the ``msg.*`` gaps ride the existing ``gaps.later`` channel,
the pinned ledger carries the eleven ids, the measured values are deterministic, and hostile or
fuzzed bytes never raise out of a measurer.

Declared by the ``turn=1b.10a`` block in ``docs/design/phase1b-ledgers.md``.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from emailextract.evals import l1  # noqa: E402
from emailextract.evals.labels import (  # noqa: E402
    DEFAULT_FIXTURES,
    Fact,
    Sidecar,
    load_sidecar,
    load_sidecars,
)

MSG = ROOT / "fixtures" / "msg"
LEDGER_PATH = ROOT / "tests" / "ledger" / "facts_ledger.json"

#: The eleven phase-1b fact ids, in the facts-doc order.
NEW_FACT_IDS = (
    "msg.container_layout",
    "msg.sector_accounting",
    "msg.message_class",
    "msg.body_streams",
    "msg.recipients",
    "msg.time_facts",
    "msg.codepage_ladder",
    "msg.stream_faults",
    "msg.attachments",
    "msg.embedded_summary",
    "msg.storage_tree_sha256",
)

#: ``fixture stem -> why it carries no sidecar`` (an explicit, typed exemption list, D5).
EXEMPT_FIXTURES = {
    "msg_directory_loop": "the CFB open refuses with cfb_directory_loop, so no fact can be produced",
}


def _measure(name: str) -> l1.Measured:
    return l1._measure(load_sidecar(MSG / f"{name}.expected.json"))


def _fact(name: str, fact_id: str):
    """The measured value of one fact for a named fixture, through the registered measurer."""
    return l1.FACTS[fact_id].function(_measure(name))


# --------------------------------------------------- the eleven declared measurer tests


def test_measurer_msg_container_layout() -> None:
    assert _fact("msg_v4_sectors", "msg.container_layout") == [4, 4096, 64, 4096, 5, 32]
    assert _fact("msg_headers_only", "msg.container_layout") == [3, 512, 64, 4096, 6, 4]


def test_measurer_msg_sector_accounting() -> None:
    rows = _fact("msg_headers_only", "msg.sector_accounting")
    assert rows == [
        ["header", 512],
        ["difat", 0],
        ["fat", 512],
        ["minifat", 512],
        ["directory", 512],
        ["stream", 1024],
        ["free", 0],
        ["slack", 0],
    ]
    assert [name for name, _ in rows] == list("header difat fat minifat directory stream free slack".split())
    # The eight counts sum to the file length (the catalogue's own numbers).
    assert sum(count for _, count in rows) == 3072


def test_measurer_msg_message_class() -> None:
    assert _fact("msg_non_ipm_note", "msg.message_class") == "IPM.Appointment"
    assert _fact("msg_signed_class", "msg.message_class") == "IPM.Note.SMIME.MultipartSigned"
    assert _fact("msg_unicode_subject", "msg.message_class") == "IPM.Note"
    # A CFB-layout fixture with no class stream reads the reader's "absent" sentinel.
    assert _fact("msg_headers_only", "msg.message_class") == "absent"


def test_measurer_msg_body_streams() -> None:
    assert _fact("msg_plain_and_html", "msg.body_streams") == ["plain", "html"]
    assert _fact("msg_rtf_compressed_body", "msg.body_streams") == ["plain", "rtf"]
    assert _fact("msg_zero_length_body", "msg.body_streams") == ["plain"]


def test_measurer_msg_recipients() -> None:
    assert _fact("msg_recipients_ex_no_smtp", "msg.recipients") == [
        ["to", "Grace Hopper", "/O=EXCHANGELABS/CN=RECIPIENTS/CN=9f2", "ex"]
    ]
    assert _fact("msg_recipients_display_only", "msg.recipients") == [["to", "Ada Lovelace", None, "smtp"]]


def test_measurer_msg_time_facts() -> None:
    assert _fact("msg_time_property_vs_date_header", "msg.time_facts") == [
        ["0039", "01dd597cebed5800", "2026-10-11T12:34:56Z"],
        ["0e06", "01dd597cebed5800", "2026-10-11T12:34:56Z"],
    ]


def test_measurer_msg_codepage_ladder() -> None:
    assert _fact("msg_string8_message_cpid", "msg.codepage_ladder") == [
        ["prop:0037", "message", 1252, "message_cpid"]
    ]
    assert _fact("msg_string8_ascii_no_cp", "msg.codepage_ladder") == [
        ["prop:0037", "none", None, "ascii"]
    ]


def test_measurer_msg_stream_faults() -> None:
    assert _fact("msg_fat_cycle", "msg.stream_faults") == [
        ["big_stream", "cycle", "declared_length_mismatch"]
    ]
    assert _fact("msg_truncated_stream", "msg.stream_faults") == [
        ["big_stream", "short_chain", "stream_ended_early"]
    ]


def test_measurer_msg_attachments() -> None:
    assert _fact("msg_attachment_with_cid", "msg.attachments") == [
        [
            "1.2",
            1,
            "report.pdf",
            "report.pdf",
            "application/pdf",
            "cid1@example.test",
            False,
            False,
            38,
            "21f4757e6806c73e03589d6486a8af3b259e95c395bda263127f948543aa6375",
        ]
    ]
    # Method 2/3/4 (referenced) carry no readable bytes.
    reference = _fact("msg_attachment_by_reference", "msg.attachments")
    assert [row[1] for row in reference] == [2, 3, 4]
    assert all(row[8] is None and row[9] is None for row in reference)


def test_measurer_msg_embedded_summary() -> None:
    assert _fact("msg_embedded_message", "msg.embedded_summary") == [
        ["1.2", "IPM.Note", "Fwd: hello", True, 1, 0]
    ]
    assert _fact("msg_embedded_depth_two", "msg.embedded_summary") == [
        ["1.2", "IPM.Note", "inner", False, 0, 1]
    ]


def test_measurer_msg_storage_tree_sha256() -> None:
    rows = _fact("msg_embedded_message", "msg.storage_tree_sha256")
    assert rows == [["1.2", "8681c5965318db9566eaebd887bb289f3796b00251ed8e5001c27bc6b2623d46"]]
    # It is never claimed to equal the file's own hash.
    import hashlib

    assert rows[0][1] != hashlib.sha256((MSG / "msg_embedded_message.msg").read_bytes()).hexdigest()


# --------------------------------------------------------------- the corpus rules


def test_every_msg_sidecar_loads_and_names_only_declared_facts() -> None:
    for path in sorted(MSG.glob("*.expected.json")):
        sidecar = load_sidecar(path)
        assert sidecar.labels_provenance == "spec"
        for fact_id, fact in sidecar.facts.items():
            measure = l1.FACTS.get(fact_id)
            assert measure is not None, f"{path.name} names unmodelled {fact_id!r}"
            assert fact.phase == measure.phase, f"{path.name}: {fact_id!r} phase disagrees"
            if fact_id.startswith("msg."):
                assert measure.phase == 1, f"{path.name}: {fact_id!r} is not declared phase 1"


def test_every_msg_fixture_has_a_sidecar_or_a_recorded_exemption() -> None:
    stems = {path.stem for path in MSG.glob("*.msg")}
    labelled = {path.name.removesuffix(".expected.json") for path in MSG.glob("*.expected.json")}
    assert labelled | set(EXEMPT_FIXTURES) == stems, sorted(stems ^ (labelled | set(EXEMPT_FIXTURES)))
    assert not (labelled & set(EXEMPT_FIXTURES)), "a fixture cannot be both labelled and exempt"
    # The exemption list is typed and each entry states a reason.
    assert all(reason for reason in EXEMPT_FIXTURES.values())


def test_the_eml_measurement_is_unchanged_by_the_container_handle() -> None:
    sample = [p for p in sorted((ROOT / "fixtures" / "generated").glob("*.expected.json"))][:25]
    for path in sample:
        measured = l1._measure(load_sidecar(path))
        assert measured.container is None, path.name
        assert l1.check(load_sidecar(path)).ok, path.name


def test_msg_gaps_ride_the_existing_gaps_later_channel() -> None:
    """Each emitted ``msg.*`` id rides ``gaps.later`` -- the existing channel, no new fact type.

    The walker's ``part.gaps`` fact is unchanged (it never carries a ``msg.*`` id), and every
    ``.msg`` gap id the sidecars label is live (compared), so the rows are real emissions.
    """
    seen: set[str] = set()
    for stem in sorted(p.stem for p in MSG.glob("*.msg")):
        if stem in EXEMPT_FIXTURES:
            continue
        sidecar = load_sidecar(MSG / f"{stem}.expected.json")
        measured = l1._measure(sidecar)
        for _part, gaps in l1.FACTS["part.gaps"].function(measured):
            assert not any(g.startswith("msg.") for g in gaps), stem
        for outcome in l1.check(sidecar).outcomes:
            if outcome.fact_id == "gaps.later" and outcome.status is l1.Status.OK:
                for row in outcome.actual:
                    seen.add(row[0])
    assert "msg.cfb_difat_extended" in seen and "msg.transport_headers_absent" in seen
    assert seen <= set(l1.LIVE_GAP_IDS)


def test_the_facts_ledger_pins_the_eleven_ids() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    phase1 = set(ledger["phase1"])
    for fact_id in NEW_FACT_IDS:
        assert fact_id in phase1, fact_id
        assert l1.FACT_PHASES[fact_id] == 1, fact_id
    # A dropped id (or a moved phase) would break the pin: the ledger's `phase1` and the
    # registry must agree, and `l1.FACT_PHASES` is the registry's own view of that.
    assert l1.FACT_PHASES[NEW_FACT_IDS[0]] == 1
    assert set(NEW_FACT_IDS) <= phase1
    assert ledger["deferred"] == []


# ------------------------------------------------------------- determinism and hostility


_DETERMINISM_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from emailextract.evals import l1
from emailextract.evals.labels import load_sidecar
MSG = Path(sys.argv[1]) / "fixtures" / "msg"
fact_ids = ["msg.container_layout", "msg.sector_accounting", "msg.message_class",
            "msg.body_streams", "msg.recipients", "msg.time_facts", "msg.codepage_ladder",
            "msg.stream_faults", "msg.attachments", "msg.embedded_summary", "msg.storage_tree_sha256"]
out = {}
for name in ("msg_embedded_depth_two", "msg_attachments_4095_4096_4097", "msg_recipients_bcc_duplicates"):
    measured = l1._measure(load_sidecar(MSG / (name + ".expected.json")))
    out[name] = {fid: l1.FACTS[fid].function(measured) for fid in fact_ids}
json.dump(out, sys.stdout, sort_keys=True)
"""


def test_the_measured_values_are_deterministic_under_two_hash_seeds() -> None:
    runs = []
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT))
        result = subprocess.run(
            [sys.executable, "-c", _DETERMINISM_SNIPPET, str(ROOT)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr
        runs.append(json.loads(result.stdout))
    assert runs[0] == runs[1]


def test_hostile_and_fuzzed_bytes_never_raise_out_of_a_measurer() -> None:
    """A broken measurement is reported ``unmeasurable``, never allowed to escape (D1)."""
    fixtures = sorted(p for p in MSG.glob("*.msg") if p.stem in {"msg_fat_cycle", "msg_directory_loop"})
    rng = random.Random(20261015)
    mutants = []
    for _ in range(30):
        raw = bytearray((MSG / "msg_headers_only.msg").read_bytes())
        for _ in range(rng.randrange(1, 5)):
            raw[rng.randrange(len(raw))] = rng.randrange(256)
        mutants.append(bytes(raw))

    for raw in mutants:
        container = l1.MsgContainer(raw)
        measured = l1.Measured(sidecar=None, result=l1.walk(container), raw=raw, container=container)  # type: ignore[arg-type]
        for fact_id in NEW_FACT_IDS:
            try:
                l1.FACTS[fact_id].function(measured)
            except Exception:  # noqa: BLE001 -- the per-fact guard reports it, not the caller
                pass

    # The registered path: a broken fixture's facts report ``unmeasurable``, never a raise.
    for path in fixtures:
        sidecar = Sidecar(
            path=path,
            artifact=path,
            fixture=path.name,
            labels_provenance="spec",
            facts={fid: Fact(id=fid, phase=1, value=["sentinel"]) for fid in NEW_FACT_IDS},
            annotations={},
        )
        report = l1.check(sidecar)
        assert not any(o.status is not None and o.detail and "Traceback" in o.detail for o in report.outcomes)
