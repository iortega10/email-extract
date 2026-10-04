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

import dataclasses
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


def _shape_copy(cls: type, *, types: dict[str, str] | None, defaults: dict[str, object] | None) -> type:
    """A copy of a frozen record with some field types/defaults replaced.

    It keeps ``cls``'s ``__qualname__``, so ``contracts_fingerprint`` sees it as the
    same record: the copy stands in for the shape the record would have after the
    edit it models (a version bump, a retype).
    """
    entries: list[tuple[str, object, object]] = []
    for field_ in dataclasses.fields(cls):
        field_type: object = (types or {}).get(field_.name, field_.type)
        if field_.name in (defaults or {}):
            default: object = (defaults or {})[field_.name]
        elif field_.default is not dataclasses.MISSING:
            default = field_.default
        elif field_.default_factory is not dataclasses.MISSING:
            default = dataclasses.field(default_factory=field_.default_factory)
        else:
            default = dataclasses.MISSING
        entries.append((field_.name, field_type, default))
    copy = dataclasses.make_dataclass(cls.__name__, entries, frozen=True)
    copy.__qualname__ = cls.__qualname__
    return copy


def _retuned(cls: type, **defaults: object) -> type:
    """``cls`` with the named fields' defaults replaced (a version bump's effect)."""
    return _shape_copy(cls, types=None, defaults=defaults)


def _retyped(cls: type, **types: str) -> type:
    """``cls`` with the named fields' type text replaced (a retype)."""
    return _shape_copy(cls, types=types, defaults=None)


def _swapped(records: tuple[type, ...], cls: type, replacement: type) -> tuple[type, ...]:
    """``records`` with ``cls`` replaced (by qualname, since ``cls`` is the identity)."""
    return tuple(replacement if record is cls else record for record in records)


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


def test_the_corpus_manifest_lists_each_version_oldest_first() -> None:
    corpora = behavior_ledger.load_corpora()
    assert [entry["version"] for entry in corpora] == list(range(1, len(corpora) + 1))
    # Corpus version 1 is the Turn 0.2 inline corpus and never moves. The Turn
    # 0.3 switch made the committed fixtures the corpus source, so the newest
    # version lists exactly today's fixture paths -- 8 generated, the raw 3 and
    # the 5 conflict fixtures (16), which is the Turn 0.3 exit criterion.
    assert corpora[0] == {"version": 1, "files": sorted(behavior_ledger.INLINE_CORPUS)}
    names = behavior_ledger.discovered()
    assert corpora[-1]["files"] == names
    assert {name.split("/", 1)[0] for name in names} == {"generated", "raw", "time"}
    assert len(names) == 68


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
    assert strings["contracts"] == versions.OUTPUT_SCHEMA_VERSION
    assert behavior_ledger.VERSION_CONSTANTS["walk"].startswith("EMAIL_PARSER_VERSION")
    assert behavior_ledger.VERSION_CONSTANTS["contracts"] == "OUTPUT_SCHEMA_VERSION"
    # The core codec's version is not this package's to bump: no component is keyed
    # by it any more (Turn 0.5's re-key).
    assert all("docextract_core" not in name for name in behavior_ledger.VERSION_CONSTANTS.values())


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
        p.startswith("contracts:") and "OUTPUT_SCHEMA_VERSION" in p for p in problems
    )


def test_a_retyped_field_moves_the_contracts_fingerprint() -> None:
    """Retyping is a real shape change: the fingerprint must move for it."""
    baseline = behavior_ledger.contracts_fingerprint()
    records = _swapped(
        behavior_ledger.contract_records(),
        model.TypeVerdicts,
        _retyped(model.TypeVerdicts, declared_mime="bytes | None"),
    )
    assert behavior_ledger.contracts_fingerprint(records) != baseline


def test_a_parser_version_bump_is_not_a_contract_change() -> None:
    """The Turn 0.5 defect: the defaults are written from the constants.

    ``EmailDocument``/``RunRecord`` default ``email_parser_version`` (and
    ``output_schema_version``) to the version constants, so a bump used to read as
    a contract change. The fingerprint records those defaults symbolically now.
    """
    baseline = behavior_ledger.contracts_fingerprint()
    bumped = _swapped(
        behavior_ledger.contract_records(),
        model.RunRecord,
        _retuned(model.RunRecord, email_parser_version="99", output_schema_version="99"),
    )
    bumped = _swapped(bumped, model.EmailDocument, _retuned(model.EmailDocument, output_schema_version="99"))
    assert behavior_ledger.contracts_fingerprint(bumped) == baseline


def test_the_recorded_default_is_the_constant_name_not_its_value() -> None:
    shapes = {
        field.name: shape
        for field, shape in (
            (field_, behavior_ledger._field_shape(field_))
            for field_ in dataclasses.fields(model.RunRecord)
        )
    }
    assert shapes["email_parser_version"][2] == {"version_constant": "EMAIL_PARSER_VERSION"}
    assert shapes["output_schema_version"][2] == {"version_constant": "OUTPUT_SCHEMA_VERSION"}


def test_the_contracts_refusal_names_this_packages_constant() -> None:
    """The re-key's point: a contract change is recorded by bumping *our* constant."""
    ledger = behavior_ledger.load_ledger()
    key = behavior_ledger.entry_key(
        "contracts", versions.OUTPUT_SCHEMA_VERSION, behavior_ledger.latest_corpus(behavior_ledger.load_corpora())
    )
    assert key in ledger["contracts"]
    tampered = {**ledger, "contracts": {**ledger["contracts"], key: "0" * 64}}
    with pytest.raises(ValueError) as refused:
        behavior_ledger.record(tampered)
    assert "OUTPUT_SCHEMA_VERSION" in str(refused.value)
    problems = behavior_ledger.check(tampered)
    assert any("OUTPUT_SCHEMA_VERSION" in p for p in problems)


def test_the_legacy_contracts_line_is_kept_and_never_compared() -> None:
    """Turn 0.5 re-keyed 'contracts' from the core's SCHEMA_VERSION ('7') to ours.

    The old line stays in the file (append-only) and is never compared again: a
    tampered '7' is invisible to both ``check`` and ``record``.
    """
    ledger = behavior_ledger.load_ledger()
    assert behavior_ledger.LEGACY_KEYS["contracts"] == ("7",)
    assert "7" in ledger["contracts"], "the legacy line is kept, not deleted"
    tampered = {**ledger, "contracts": {**ledger["contracts"], "7": "0" * 64}}
    assert behavior_ledger.check(tampered) == []
    updated, _lines = behavior_ledger.record(tampered)
    assert updated["contracts"]["7"] == "0" * 64
    # The ledger header says so, in the file a reviewer reads.
    header = json.loads(behavior_ledger.LEDGER_PATH.read_text(encoding="utf-8"))["_comment"]
    assert "LEGACY" in header and "OUTPUT_SCHEMA_VERSION" in header


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
    next_version = behavior_ledger.latest_corpus(behavior_ledger.load_corpora()) + 1
    (tmp_path / "a.eml").write_bytes(EXTRA_MESSAGE)
    (tmp_path / "b.eml").write_bytes(EXTRA_MESSAGE + b"second\r\n")
    corpora, changed = behavior_ledger.add_corpus_version(fixtures_dir=tmp_path)
    assert changed is True
    assert corpora[-1] == {"version": next_version, "files": ["a.eml", "b.eml"]}
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
