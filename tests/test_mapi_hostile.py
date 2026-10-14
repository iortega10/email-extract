"""Turn 1b.4: the hostile side of ``mapi.py`` -- recorded faults and the seeded fuzz.

A lone surrogate, an odd-length UTF-16 stream and a recipient count that disagrees with
the directory are **recorded**, never raised (D1/D7). Beyond them a seeded fuzz mutates
the *property* and ``__substg1.0_*`` bytes of three base fixtures and demands that every
mutant comes back as a ``MapiMessage`` whose values are decoded or ``None`` with a fault
from :data:`mapi.FAULTS`, whose every text is UTF-8-encodable, and whose work stays
inside the declared bound.

The declared tests are ``test_a_lone_surrogate_is_recorded_not_raised``,
``test_an_odd_length_utf16_stream_is_recorded_not_raised`` and
``test_a_recipient_count_mismatch_is_recorded``. Three checks beyond the declaration:
``test_every_property_mutant_returns_a_closed_message``,
``test_the_mapi_work_bound_holds`` and ``test_the_mutant_numbers_are_stable_across_hash_seeds``,
plus ``test_the_mapi_vocabulary_matches_the_registry_model_and_imports``.

**The declared step bound** (stated before the fuzz runs): a full ``read_message`` costs
at most ``cfb.WORK_PER_SECTOR * sector_count + cfb.WORK_BASE`` (the CFB read) **plus**
``mapi.MAPI_WORK_PER_BYTE * len(data) + mapi.MAPI_WORK_BASE`` (the property layer), and
the measured maximum is strictly under it. Every mapi loop is bounded by the bytes
present -- a table's length, the directory's entries -- never a declared count.
"""

from __future__ import annotations

import ast
import hashlib
import os
import random
import struct
import subprocess
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
MAPI_PATH = ROOT / "emailextract" / "mapi.py"
PT_STRING8 = mapi_table.PT_STRING8
PT_UNICODE = mapi_table.PT_UNICODE
PT_BINARY = mapi_table.PT_BINARY
PT_I8 = mapi_table.PT_I8
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


# ==================================================== 1. the recorded hostile cases


def test_a_lone_surrogate_is_recorded_not_raised() -> None:
    lone = mapi.decode_unicode(b"\x00\xd8")  # U+D800, a lone high surrogate
    assert lone.text is None
    assert lone.fault == mapi.FAULT_UTF16_LONE_SURROGATE

    payload = b"A\x00\x00\xd8"
    msg = mapi.read_message(
        _message(
            entries=[mapi_table.variable_entry(0x0037, PT_UNICODE, len(payload))],
            codepages=(1252, 1252),
            *[stream("__substg1.0_0037001F", payload)],
        )
    )
    subject = _by_tag(msg)[0x0037]
    assert subject.text.text is None
    assert subject.text.fault == mapi.FAULT_UTF16_LONE_SURROGATE
    assert subject.text.raw_sha256 == hashlib.sha256(payload).hexdigest()


def test_an_odd_length_utf16_stream_is_recorded_not_raised() -> None:
    odd = mapi.decode_unicode(b"\x41\x00\x42")
    assert odd.text is None
    assert odd.fault == mapi.FAULT_UTF16_ODD_LENGTH

    payload = b"\x41\x00\x42"
    msg = mapi.read_message(
        _message(
            entries=[mapi_table.variable_entry(0x0037, PT_UNICODE, len(payload))],
            codepages=(1252, 1252),
            *[stream("__substg1.0_0037001F", payload)],
        )
    )
    subject = _by_tag(msg)[0x0037]
    assert subject.text.text is None
    assert subject.text.fault == mapi.FAULT_UTF16_ODD_LENGTH


def test_a_recipient_count_mismatch_is_recorded() -> None:
    row = storage(
        "__recip_version1.0_#00000000",
        stream(
            "__properties_version1.0",
            mapi_table.sub_table([mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 1)]),
        ),
    )
    msg = mapi.read_message(_message(row, recipients=2))
    assert msg.declared_recipient_count == 2
    assert msg.recipient_row_count == 1  # the directory's rows, still returned
    assert msg.recipients[0].kind == "to"
    assert mapi.MSG_RECIPIENT_TABLE_UNREADABLE in msg.observations

    # An unreadable row emits the same id, and the row is still returned (D7).
    broken = storage(
        "__recip_version1.0_#00000000",
        stream("__properties_version1.0", mapi_table.sub_table([]) + b"\x00"),
    )
    broken_msg = mapi.read_message(_message(broken, recipients=1))
    assert broken_msg.recipient_row_count == 1
    assert broken_msg.recipients[0].fault is not None
    assert mapi.MSG_RECIPIENT_TABLE_UNREADABLE in broken_msg.observations


# ============================================================== 2. the seeded fuzz


def _s(name: str, data: bytes) -> tuple:
    return ("stream", name, data)


def _st(name: str, children: list) -> tuple:
    return ("storage", name, list(children))


def _build(tree: list) -> bytes:
    def node(child: tuple):
        kind, name, payload = child
        if kind == "stream":
            return stream(name, payload)
        return storage(name, *(node(grand) for grand in payload))

    return build_cfb(storage("Root Entry", *(node(child) for child in tree)))


def _class_entry() -> bytes:
    return mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE, len(_IPM_NOTE))


def _class_stream_name() -> str:
    return mapi_table.substg_name(mapi_table.PROP_MESSAGE_CLASS, PT_UNICODE)


def _base_subject() -> list:
    subject = b"synthetic subject"
    table = mapi_table.message_table(
        [_class_entry(), mapi_table.variable_entry(0x0037, PT_STRING8, len(subject))],
        codepages=(1252, 1252),
    )
    return [
        _s("__properties_version1.0", table),
        _s(_class_stream_name(), _IPM_NOTE),
        _s("__substg1.0_0037001E", subject),
    ]


def _base_unknown() -> list:
    unicode_stream = mapi_table.utf16("unmodelled unicode")
    binary = b"\xde\xad\xbe\xef"
    table = mapi_table.message_table(
        [
            _class_entry(),
            mapi_table.long_entry(0x6200, 7),
            mapi_table.fixed_entry(0x6748, PT_I8, struct.pack("<q", 1234)),
            mapi_table.variable_entry(0x6827, PT_UNICODE, len(unicode_stream)),
            mapi_table.variable_entry(0x6523, PT_BINARY, len(binary)),
        ],
        codepages=(28591, 1252),
    )
    return [
        _s("__properties_version1.0", table),
        _s(_class_stream_name(), _IPM_NOTE),
        _s("__substg1.0_6827001F", unicode_stream),
        _s("__substg1.0_65230102", binary),
    ]


def _base_recipient() -> list:
    ada = mapi_table.utf16("Ada Lovelace")
    smtp = mapi_table.utf16("SMTP")
    address = mapi_table.utf16("ada@example.test")
    recipient = mapi_table.sub_table(
        [
            mapi_table.long_entry(mapi_table.PROP_RECIPIENT_TYPE, 1),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_DISPLAY, PT_UNICODE, len(ada)),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_ADDRESS_TYPE, PT_UNICODE, len(smtp)),
            mapi_table.variable_entry(mapi_table.PROP_RECIPIENT_EMAIL, PT_UNICODE, len(address)),
        ]
    )
    table = mapi_table.message_table(
        [_class_entry()], recipients=1, codepages=(20127, 20127)
    )
    return [
        _s("__properties_version1.0", table),
        _s(_class_stream_name(), _IPM_NOTE),
        _st(
            "__recip_version1.0_#00000000",
            [
                _s("__properties_version1.0", recipient),
                _s("__substg1.0_3001001F", ada),
                _s("__substg1.0_3002001F", smtp),
                _s("__substg1.0_3003001F", address),
            ],
        ),
    ]


#: The three base fixtures, as (name, tree) -- at least three, per the brief.
BASES = (("subject", _base_subject), ("unknown", _base_unknown), ("recipient", _base_recipient))
#: The fixed, committed seed list -- one mutant per ``(base, seed)``.
MUTANT_SEEDS: tuple[int, ...] = tuple(range(150))
#: The mutation operators, on the properties and ``__substg1.0_*`` bytes (the brief's list).
OPERATORS = (
    "tag_or_type",
    "flags_word",
    "size_field",
    "count",
    "truncate_table",
    "codepage",
    "stream_byte",
    "stream_truncate",
)


def _rng(base_name: str, seed: int) -> random.Random:
    return random.Random([name for name, _ in BASES].index(base_name) * 100_000 + seed)


def _streams(tree: list, prefix: str = "") -> list:
    leaves: list = []
    for kind, name, payload in tree:
        path = prefix + name
        if kind == "stream":
            leaves.append((path, payload))
        else:
            leaves.extend(_streams(payload, path + "/"))
    return leaves


def _set(tree: list, target: str, new_bytes: bytes, prefix: str = "") -> list:
    out: list = []
    for kind, name, payload in tree:
        full = prefix + name
        if kind == "stream":
            out.append((kind, name, new_bytes if full == target else payload))
        else:
            out.append((kind, name, _set(payload, target, new_bytes, full + "/")))
    return out


def mutant(tree: list, base_name: str, seed: int) -> "tuple[str, bytes]":
    """One mutant of ``tree``: the operator that made it and the rebuilt container bytes."""
    rng = _rng(base_name, seed)
    operator = rng.choice(OPERATORS)
    streams = dict(_streams(tree))
    substg = sorted(path for path in streams if "/__substg1.0_" in "/" + path)
    if operator in ("tag_or_type", "flags_word", "size_field", "count", "truncate_table", "codepage"):
        target = "__properties_version1.0"
    else:
        target = rng.choice(substg) if substg else "__properties_version1.0"

    data = bytearray(streams[target])
    if operator in ("truncate_table", "stream_truncate"):
        cut = rng.randrange(0, len(data) + 1) if data else 0
        data = data[:cut]
    elif operator == "count":
        struct.pack_into("<I", data, rng.choice((16, 20, 24, 28)), rng.choice((0, 1, 2, 2**31, 0xFFFFFFFF)))
    elif operator == "codepage":
        offset = 32 + rng.choice((0, 1)) * 16 + 8
        struct.pack_into("<I", data, offset, rng.choice((0, 1252, 20127, 28591, 65001, 99999, 0xFFFFFFFF)))
    elif operator == "stream_byte":
        offset = rng.randrange(len(data)) if data else 0
        if data:
            data[offset] = rng.randrange(256)
    else:
        entries = max((len(data) - 32) // 16, 1)
        entry = rng.randrange(entries)
        column = {
            "tag_or_type": rng.randrange(0, 4),
            "flags_word": rng.randrange(4, 8),
            "size_field": rng.randrange(8, 16),
        }[operator]
        offset = 32 + entry * 16 + column
        if offset < len(data):
            data[offset] = rng.randrange(256)

    return operator, _build(_set(tree, target, bytes(data)))


def _cases():
    """Every ``(base_name, seed, operator, base_bytes, mutant_bytes)`` in a fixed order."""
    for base_name, make in BASES:
        tree = make()
        base = _build(tree)
        for seed in MUTANT_SEEDS:
            operator, data = mutant(tree, base_name, seed)
            yield base_name, seed, operator, base, data


def _walk(value, cls):
    """Every ``cls`` instance reachable through dataclasses, named tuples and sequences."""
    if isinstance(value, cls):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk(item, cls)
    elif hasattr(value, "__dataclass_fields__"):
        for name in value.__dataclass_fields__:
            yield from _walk(getattr(value, name), cls)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _strings(item)
    elif hasattr(value, "__dataclass_fields__"):
        for name in value.__dataclass_fields__:
            yield from _strings(getattr(value, name))


def _check_message(msg: "mapi.MapiMessage", label: str) -> None:
    for text in _walk(msg, mapi.TextValue):
        assert (text.text is None) != (text.fault is None), (label, text)
        assert text.fault is None or text.fault in mapi.FAULTS, (label, text.fault)
    for prop in _walk(msg, mapi.Property):
        assert prop.fault is None or prop.fault in mapi.FAULTS, (label, prop.fault)
    for row in msg.recipients:
        assert row.fault is None or row.fault in mapi.FAULTS, (label, row.fault)
    for string in _strings(msg):
        string.encode("utf-8")  # a lone surrogate would raise here


def classify(base_name: str, seed: int, operator: str, data: bytes) -> str:
    """Read one mutant and return a closed tag; an exception becomes a named failure."""
    label = f"base={base_name} seed={seed} op={operator}"
    try:
        opened = cfb.open_cfb(data)
    except (MemoryError, RecursionError) as exc:  # pragma: no cover - the point is it must not
        raise AssertionError(f"{label}: {type(exc).__name__}") from exc
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"{label}: {type(exc).__name__}: {exc}") from exc
    if isinstance(opened, cfb.CfbRefusal):
        return f"refusal:{opened.reason}"
    try:
        msg = mapi.read_message(opened)
    except (MemoryError, RecursionError) as exc:  # pragma: no cover
        raise AssertionError(f"{label}: {type(exc).__name__}") from exc
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"{label}: {type(exc).__name__}: {exc}") from exc
    _check_message(msg, label)
    return f"message:{msg.class_verdict}:{len(msg.properties)}:{len(msg.recipients)}:{len(msg.unknown_tags)}"


def steps_and_sectors(data: bytes) -> "tuple[int, int]":
    work = cfb.Work()
    opened = cfb.open_cfb(data, work=work)
    if isinstance(opened, cfb.CfbRefusal):
        return work.steps, cfb.sector_windows(len(data), 512)
    mapi.read_message(opened)
    return opened.work.steps, opened.sector_count


def budget_for(data_len: int, sectors: int) -> int:
    """The declared bound: the CFB budget plus the property layer's own."""
    return (
        cfb.WORK_PER_SECTOR * sectors
        + cfb.WORK_BASE
        + mapi.MAPI_WORK_PER_BYTE * data_len
        + mapi.MAPI_WORK_BASE
    )


def digest() -> str:
    """A hex digest of every mutant's closed outcome, for the determinism check."""
    rows = [f"{base}|{seed}|{op}|{classify(base, seed, op, data)}" for base, seed, op, _, data in _cases()]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_every_property_mutant_returns_a_closed_message() -> None:
    bases = {name: _build(make()) for name, make in BASES}
    base_tags = {name: classify(name, -1, "none", data) for name, data in bases.items()}
    seen = 0
    for base_name, seed, operator, base, data in _cases():
        tag = classify(base_name, seed, operator, data)
        if data == base:
            assert tag == base_tags[base_name], (base_name, seed, operator)
        seen += 1
    # At least 300 mutants, over at least three base fixtures (the brief's floor).
    assert seen >= 300, seen
    assert len(BASES) >= 3, len(BASES)


def test_the_mapi_work_bound_holds() -> None:
    assert mapi.MAPI_WORK_PER_BYTE > 0 and mapi.MAPI_WORK_BASE >= 0
    worst = 0.0
    for base_name, seed, operator, _base, data in _cases():
        steps, sectors = steps_and_sectors(data)
        budget = budget_for(len(data), sectors)
        assert steps <= budget, (base_name, seed, operator, steps, budget)
        worst = max(worst, steps / budget)
    # Not vacuous: a real read costs something, and every mutant stays strictly under it.
    assert 0 < worst < 1.0, worst


def test_the_mutant_numbers_are_stable_across_hash_seeds() -> None:
    baseline = digest()
    assert _hash_seed_run("0") == baseline
    assert _hash_seed_run("1234567") == baseline


def _hash_seed_run(seed: str) -> str:
    script = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "sys.path.insert(0, sys.argv[3])\n"
        "import test_mapi_hostile as fuzz\n"
        "print(fuzz.digest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": seed}
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


# ======================================================= 3. the parity and import ban


def _top_level_imports(path: Path) -> "set[str]":
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("<relative>" if node.level else (node.module or "").split(".")[0])
    return names


def _relative_imports(path: Path) -> "set[str]":
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            names.update(alias.name for alias in node.names)
    return names


def test_the_mapi_vocabulary_matches_the_registry_model_and_imports() -> None:
    from emailextract import model

    # (c1) Every id this module can name is a registered gap id -- read from the registry
    # the existing gap tests read, so there is no second list.
    from test_phase0_gaps import registry_ids

    assert set(mapi.OBSERVATION_IDS) <= registry_ids()
    assert set(mapi.OBSERVATION_IDS) == {
        "msg.class_not_ipm_note",
        "msg.property_tag_unknown",
        "msg.named_property_unresolved",
        "msg.codepage_unresolved_ladder_used",
        "msg.recipient_table_unreadable",
    }

    # (c2) Every ladder string is a model.EncodingSource value, and the five rungs are the
    # enum's own five (the module itself never imports model).
    assert set(mapi.ENCODING_SOURCES) <= {member.value for member in model.EncodingSource}
    assert mapi.ENCODING_SOURCES == (
        model.EncodingSource.INTERNET_CPID.value,
        model.EncodingSource.MESSAGE_CPID.value,
        model.EncodingSource.ASCII.value,
        model.EncodingSource.UTF8_STRICT.value,
        model.EncodingSource.WINDOWS_1252.value,
    )

    # (c3) ``mapi.py`` is a leaf: stdlib plus the sibling ``cfb`` module only.
    assert _top_level_imports(MAPI_PATH) <= {
        "__future__", "hashlib", "struct", "dataclasses", "typing", "<relative>"
    }
    assert _relative_imports(MAPI_PATH) == {"cfb"}

    # (c4) A fresh interpreter that loads ``mapi.py`` (without the package's ``__init__``,
    # which imports model/walk by design) pulls in no olefile, walk, model or parse.
    script = (
        "import sys, types\n"
        "pkg = types.ModuleType('emailextract')\n"
        "pkg.__path__ = [sys.argv[1]]\n"
        "sys.modules['emailextract'] = pkg\n"
        "import emailextract.mapi\n"
        "print(sorted(m for m in sys.modules if m == 'olefile' or m.startswith('emailextract')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT / "emailextract")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "['emailextract', 'emailextract.cfb', 'emailextract.mapi']", result.stdout
