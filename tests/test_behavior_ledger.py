"""Turn 0.2: the behavior ledger (build spec, Turn 0.2; the byte fingerprint lesson).

The rules under test: unmodified code is a clean ``--check``; one changed rule is
caught and named with the constant to bump -- the scanner, the decode chain, the
charset ladder, part identity and the contract registry each on their own;
``record`` is append-only and refuses to overwrite; the payload is accepted with
its ``_comment``; growing the corpus adds a corpus version and bumps nothing; and
the interpreter is recorded, never keyed (the cross-interpreter comparison runs
the whole suite and ``--check`` on both interpreters -- see the refusal test).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import behavior_ledger  # noqa: E402
import update_behavior_ledger  # noqa: E402
from emailextract import model, store, versions, walk as walk_module  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402

EXTRA_MESSAGE = (
    b"From: new@example.com\r\n"
    b"Subject: a new corpus entry\r\n"
    b"\r\n"
    b"new body\r\n"
)


def test_the_committed_ledger_agrees_with_the_code() -> None:
    assert behavior_ledger.check() == []


def test_the_cli_check_exits_zero_on_unmodified_code(capsys) -> None:
    assert update_behavior_ledger.main(["--check"]) == 0
    assert capsys.readouterr().err == ""


def test_the_ledger_header_names_the_corpus_and_the_cross_interpreter_fact() -> None:
    text = behavior_ledger.LEDGER_PATH.read_text(encoding="utf-8")
    assert "INLINE_CORPUS" in text
    assert "3.14.3" in text and "3.11.15" in text
    # Written with LF only: the bytes are the same on every platform (newline="\n").
    assert b"\r\n" not in behavior_ledger.LEDGER_PATH.read_bytes()
    assert "_comment" in json.loads(text)


def test_the_corpus_manifest_lists_the_inline_corpus_names() -> None:
    corpora = behavior_ledger.load_corpora()
    assert corpora == [{"version": 1, "files": sorted(behavior_ledger.INLINE_CORPUS)}]


def test_the_fingerprints_are_stable_and_look_like_hashes() -> None:
    first = behavior_ledger.fingerprints()
    assert set(first) == set(behavior_ledger.COMPONENTS)
    for name, value in first.items():
        assert re.fullmatch(r"[0-9a-f]{64}", value), name
    assert behavior_ledger.fingerprints() == first
    assert len(set(first.values())) == len(behavior_ledger.COMPONENTS)


def test_the_version_strings_point_at_the_names_to_bump() -> None:
    strings = behavior_ledger.version_strings()
    assert strings["walk"] == f"{versions.EMAIL_PARSER_VERSION}|{versions.DECODE_CHAIN_VERSION}"
    assert strings["decode_chain"] == versions.DECODE_CHAIN_VERSION
    assert behavior_ledger.VERSION_CONSTANTS["walk"].startswith("EMAIL_PARSER_VERSION")


# ------------------------------------------------------------------ sensitivity


def test_a_header_scanner_rule_change_is_caught(monkeypatch) -> None:
    scanner = walk_module._split_field

    def names_uppercased(content, line_start):
        name, value_start = scanner(content, line_start)
        return (name.upper() if name is not None else None), value_start

    monkeypatch.setattr(walk_module, "_split_field", names_uppercased)
    problems = behavior_ledger.check()
    assert any(p.startswith("walk:") and "EMAIL_PARSER_VERSION" in p for p in problems)
    # Field names moved; declared values are looked up case-insensitively, so the
    # decode chain is untouched -- that component must stay clean (sensitivity
    # is per component, not one blob).
    assert not any(p.startswith("decode_chain:") for p in problems)


def test_a_decode_rule_change_is_caught(monkeypatch) -> None:
    monkeypatch.setattr(
        walk_module, "_decode_cte", lambda payload, declared: ("7bit", payload, False, None)
    )
    problems = behavior_ledger.check()
    assert any(p.startswith("decode_chain:") and "DECODE_CHAIN_VERSION" in p for p in problems)
    assert any(p.startswith("walk:") and "EMAIL_PARSER_VERSION" in p for p in problems)


def test_a_charset_ladder_change_is_caught(monkeypatch) -> None:
    monkeypatch.setattr(
        walk_module,
        "_charset_ladder",
        lambda body, declared: ("us-ascii", model.EncodingSource.ASCII, False, None),
    )
    problems = behavior_ledger.check()
    assert any(p.startswith("decode_chain:") and "DECODE_CHAIN_VERSION" in p for p in problems)


def test_a_part_identity_rule_change_is_caught(monkeypatch) -> None:
    monkeypatch.setattr(walk_module, "part_id", lambda *arguments: "one-fixed-id")
    problems = behavior_ledger.check()
    assert any(p.startswith("walk:") and "EMAIL_PARSER_VERSION" in p for p in problems)
    assert not any(p.startswith("decode_chain:") for p in problems)


def test_a_contract_record_change_is_caught(monkeypatch) -> None:
    recorded = behavior_ledger.contract_records()

    @dataclass(frozen=True)
    class ExtraRecord:
        line: str

    monkeypatch.setattr(
        behavior_ledger, "contract_records", lambda: recorded + (ExtraRecord,)
    )
    problems = behavior_ledger.check()
    assert any(
        p.startswith("contracts:") and "docextract_core.SCHEMA_VERSION" in p for p in problems
    )


def test_a_version_bump_without_a_recorded_line_names_the_constant(monkeypatch) -> None:
    monkeypatch.setattr(
        versions, "EMAIL_PARSER_VERSION", versions.EMAIL_PARSER_VERSION + ".bumped"
    )
    problems = behavior_ledger.check()
    assert any("is not in the ledger" in p and "EMAIL_PARSER_VERSION" in p for p in problems)


def test_the_cli_exits_one_when_a_rule_changes_without_a_bump(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        walk_module, "_decode_cte", lambda payload, declared: ("7bit", payload, False, None)
    )
    assert update_behavior_ledger.main(["--check"]) == 1
    assert "DECODE_CHAIN_VERSION" in capsys.readouterr().err


# ------------------------------------------------------------------ the discipline


def test_record_is_append_only_and_names_the_constant_to_bump() -> None:
    ledger = behavior_ledger.load_ledger()
    corpora = behavior_ledger.load_corpora()
    key = behavior_ledger.entry_key(
        "walk", behavior_ledger.version_strings()["walk"], behavior_ledger.latest_corpus(corpora)
    )
    assert key in ledger["walk"]
    tampered = {**ledger, "walk": {**ledger["walk"], key: "0" * 64}}
    with pytest.raises(ValueError) as refused:
        behavior_ledger.record(tampered)
    message = str(refused.value)
    assert "EMAIL_PARSER_VERSION" in message
    assert key in message
    # The untampered ledger records nothing new -- appending is the only motion.
    updated, lines = behavior_ledger.record(ledger)
    assert updated == ledger
    assert lines and all("unchanged" in line for line in lines)


def test_check_and_record_accept_the_payload_with_its_comment_key() -> None:
    raw = json.loads(behavior_ledger.LEDGER_PATH.read_text(encoding="utf-8"))
    assert "_comment" in raw
    assert behavior_ledger.check(raw) == []
    updated, _lines = behavior_ledger.record(raw)
    assert "_comment" not in updated
    assert updated["walk"] == raw["walk"]


def test_growing_the_corpus_adds_a_corpus_version_and_bumps_nothing(tmp_path) -> None:
    before = behavior_ledger.version_strings()
    (tmp_path / "a.eml").write_bytes(EXTRA_MESSAGE)
    (tmp_path / "b.eml").write_bytes(EXTRA_MESSAGE + b"second\r\n")
    corpora, changed = behavior_ledger.add_corpus_version(fixtures_dir=tmp_path)
    assert changed is True
    assert corpora[-1] == {"version": 2, "files": ["a.eml", "b.eml"]}
    # Fixtures are corpus, not behavior: no component version moves.
    assert behavior_ledger.version_strings() == before
    problems = behavior_ledger.check(behavior_ledger.load_ledger(), fixtures_dir=tmp_path)
    corpus_problems = [p for p in problems if p.startswith("corpus:")]
    assert corpus_problems and "bumps no component version" in corpus_problems[0]


def test_the_interpreter_is_recorded_but_never_keyed(monkeypatch) -> None:
    """The lesson that does not hold, kept refused.

    "Snapshot dicts compare equal across interpreters" does not hold on its own --
    the earlier byte-identity lesson failed exactly there. Cross-interpreter
    identity is verified by running this suite and ``--check`` on **both**
    interpreters and comparing, and any difference is recorded in the ledger
    header. An in-process claim about another interpreter is therefore refused
    outright unless the process is mono-interpreter
    (``sys.platform == "win32"`` and not PyPy): it is refused, never skipped,
    because a silent skip would read as checked.
    """
    if not (sys.platform == "win32" and not hasattr(sys, "pypy_version_info")):
        raise RuntimeError(
            "refused: this is not a mono-interpreter process; run the suite and "
            "tools/update_behavior_ledger.py --check on each interpreter instead"
        )
    container = EmlContainer(memory_bytes(b"From: a@example.com\r\n\r\nbody\r\n"))
    baseline = behavior_ledger.fingerprints()
    key = store.artifact_key(container)
    monkeypatch.setattr(
        store,
        "recorded_only_inputs",
        lambda: {"python": "3.99.0", "implementation": "Other", "platform": "elsewhere"},
    )
    assert behavior_ledger.fingerprints() == baseline
    assert store.artifact_key(container) == key
