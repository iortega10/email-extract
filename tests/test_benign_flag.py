"""Turn 1.0b: the additions-only ``benign`` sidecar flag (``phase1-ledgers.md`` (c)).

``labels.load_sidecar``'s ``OPTIONAL_KEYS`` gains exactly one entry, ``benign``, whose
``reason_id`` is a closed id naming *why* a fixture is expected to be clean. An unknown
``reason_id`` is a ``LabelError`` at load, exactly as an unknown ``labels_provenance``
is. The loader still imports neither the walker nor the model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from emailextract.evals.labels import (
    BENIGN_REASON_IDS,
    OPTIONAL_KEYS,
    LabelError,
    load_sidecar,
)

EXPECTED_REASON_IDS = (
    "no_attachment_expected",
    "no_quote_expected",
    "headers_only_by_design",
    "known_ambiguous_bytes",
)


def _write(tmp_path: Path, payload: dict) -> Path:
    (tmp_path / "case.eml").write_bytes(b"From: a@example.test\r\n\r\nbody\r\n")
    path = tmp_path / "case.expected.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _base(**extra) -> dict:
    payload = {
        "fixture": "case.eml",
        "labels_provenance": "spec",
        "facts": {"container.size_bytes": {"phase": 0, "value": 1}},
    }
    payload.update(extra)
    return payload


def test_the_benign_reason_ids_are_closed() -> None:
    """The flag is an optional key with a closed reason-id set, additions-only."""
    assert "benign" in OPTIONAL_KEYS
    assert tuple(BENIGN_REASON_IDS) == EXPECTED_REASON_IDS
    assert len(BENIGN_REASON_IDS) == len(set(BENIGN_REASON_IDS)) == 4
    # The loader still imports neither the walker nor the model.
    import emailextract.evals.labels as labels_module

    source = Path(labels_module.__file__).read_text(encoding="utf-8")
    assert "from ..model" not in source and "from emailextract.model" not in source
    assert "import walk" not in source


def test_an_unknown_benign_reason_is_a_label_error(tmp_path: Path) -> None:
    sidecar = _write(tmp_path, _base(benign={"reason_id": "no_quote_expected"}))
    loaded = load_sidecar(sidecar)
    assert loaded.benign == {"reason_id": "no_quote_expected"}
    # The default (no flag) is not an assertion of anything.
    assert load_sidecar(_write(tmp_path, _base())).benign is None

    with pytest.raises(LabelError, match="benign.reason_id"):
        load_sidecar(_write(tmp_path, _base(benign={"reason_id": "not_a_reason"})))
    with pytest.raises(LabelError, match="benign.reason_id"):
        load_sidecar(_write(tmp_path, _base(benign={})))
    with pytest.raises(LabelError, match="not an object"):
        load_sidecar(_write(tmp_path, _base(benign="no_quote_expected")))
    with pytest.raises(LabelError, match="unknown key"):
        load_sidecar(_write(tmp_path, _base(benign={"reason_id": "no_quote_expected", "x": 1})))
