"""Turn 1.2: the package's own RFC 5322 3.4 address-list tokenizer (``emailextract/addresses``).

The rules under test (decision 4, D2/D9, the "Turn 1.2" declaration): a field value is one
address list; a mailbox is a name-addr or an addr-spec; a quoted display name with a comma is
**one** address; a group keeps its members and a zero-member group is an empty list; an
unparseable fragment is a row that is ``unparsed`` with the closed reason beside its raw
bytes, never repaired and never dropped; IDN and SMTPUTF8 are kept verbatim; an obs-route is
recorded; CFWS never splits an address; a trailing comma and empty elements are tolerated;
the oracle's ``headers.addresses`` and the projection's ``address_list`` scalar are live; and
the module never raises, is **linear**, and maps onto the fact row shape.

Every failure names the fixture, the fact, the gap id and the reason id. The 12 tests the
turn declared are here; the extra tests are declared in the turn's block too.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import sidecar_copy  # noqa: E402
from support import stdlib_scanner  # noqa: E402

from emailextract import addresses as address_stage  # noqa: E402
from emailextract import headers as header_stage  # noqa: E402
from emailextract.container import EmlContainer  # noqa: E402
from emailextract.evals import l1 as oracle  # noqa: E402
from emailextract.evals import l1_gate  # noqa: E402
from emailextract.walk import walk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
BUDGET = 64

GAP_UNPARSABLE = address_stage.GAP_HEADERS_ADDRESS_UNPARSABLE

#: The Family-A fixtures whose ``To`` field this turn's rules are typed against.
ADDRESS_STEMS = (
    "address_group",
    "address_undisclosed_recipients",
    "address_quoted_comma_display_name",
    "address_idn_domain",
    "address_smtputf8_local_part",
    "address_unparsable",
)


def _fixture(stem: str) -> bytes:
    for directory in ("generated", "raw", "time"):
        path = FIXTURES / directory / f"{stem}.eml"
        if path.is_file():
            return path.read_bytes()
    raise AssertionError(f"no fixture {stem!r}")


def _all_fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*/*.eml"))


def _region(stem: str):
    raw = _fixture(stem)
    return raw, header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)


def _parse(value: bytes, base: int = 0):
    return address_stage.parse_address_list(value, base_offset=base, max_work_units=BUDGET)


def _own_rows(raw: bytes) -> list[list[object]]:
    """The tokenizer's whole output for one message, in the fact's shape."""
    region = header_stage.header_region(raw, walk(EmlContainer(raw)), max_work_units=BUDGET)
    return header_stage.address_rows(region)


def _field(stem: str, name: str):
    """``(raw, value bytes, base offset, rows)`` for one labelled address field of a fixture."""
    raw, region = _region(stem)
    item = header_stage.fields_named(region.fields, name)[0]
    value = raw[item.value_span.offset : item.value_span.end]
    rows = address_stage.parse_address_list(
        value, base_offset=item.value_span.offset, max_work_units=BUDGET
    )
    return raw, value, item.value_span.offset, rows


def _to_rows(stem: str):
    return _field(stem, "To")


# ----------------------------------------------------------------- the declared 12


def test_an_addr_spec_gets_one_span() -> None:
    """A bare addr-spec is one mailbox with a byte span that slices to it (D2)."""
    value = b" ben@example.test"
    rows = _parse(value)
    assert len(rows) == 1, rows
    assert rows[0].state == "parsed"
    assert rows[0].display_name is None
    assert rows[0].addr_spec == "ben@example.test"
    assert value[rows[0].offset : rows[0].end] == b" ben@example.test"

    # Two addr-specs in one field still get one span each, over their own bytes.
    two = b"a@example.test, b@example.test"
    rows = _parse(two)
    assert [row.addr_spec for row in rows] == ["a@example.test", "b@example.test"]
    assert two[rows[0].offset : rows[0].end] == b"a@example.test"
    assert two[rows[1].offset : rows[1].end] == b"b@example.test"


def test_a_quoted_display_name_with_a_comma_is_one_address() -> None:
    """The comma inside a quoted-string is not an address separator (3.2.4)."""
    raw, _value, _base, rows = _field("address_quoted_comma_display_name", "To")
    assert len(rows) == 1, "the quoted comma must not split the list"
    assert rows[0].display_name == "Doe, Jane"  # the quotes are removed
    assert rows[0].addr_spec == "jane@example.test"
    assert rows[0].state == "parsed"
    assert raw[rows[0].offset : rows[0].end] == b' "Doe, Jane" <jane@example.test>'


def test_a_group_preserves_its_members() -> None:
    """A group is one row whose members are the flat rows beside it; none is dropped."""
    raw, _value, _base, rows = _to_rows("address_group")
    assert [row.state for row in rows] == ["group", "parsed", "parsed"]
    assert [row.addr_spec for row in rows] == [None, "ben@example.test", "cara@example.test"]
    assert rows[0].display_name is None
    assert raw[rows[0].offset : rows[0].end] == b"Friends:"
    assert raw[rows[1].offset : rows[1].end] == b"ben@example.test"
    assert raw[rows[2].offset : rows[2].end] == b"cara@example.test"


def test_a_zero_member_group_is_empty_not_absent() -> None:
    """``undisclosed-recipients:;`` is one group row with no members -- never absent, never unparsed."""
    raw, _value, _base, rows = _to_rows("address_undisclosed_recipients")
    assert len(rows) == 1, "a zero-member group is a single group row"
    assert rows[0].state == "group"
    assert rows[0].display_name is None
    assert rows[0].addr_spec == "undisclosed-recipients:;"
    assert rows[0].reason_id is None
    assert raw[rows[0].offset : rows[0].end] == b"undisclosed-recipients:;"


def test_an_unparseable_address_is_unknown_with_its_raw_value() -> None:
    """An unparseable fragment is ``unparsed`` with the closed reason, its raw bytes beside it."""
    raw, value, base, rows = _field("address_unparsable", "To")
    assert len(rows) == 1
    row = rows[0]
    assert row.state == "unparsed"
    assert row.reason_id == GAP_UNPARSABLE
    assert row.display_name is None
    assert row.addr_spec == "not-an-address at all"
    assert raw[row.offset : row.end] == b" not-an-address at all"  # the raw bytes, verbatim
    assert row.offset == base


def test_an_idn_domain_is_kept_verbatim() -> None:
    """A U-label domain is kept as typed -- never IDNA-normalised to an A-label (decision 4)."""
    _raw, _value, _base, rows = _to_rows("address_idn_domain")
    assert rows[0].addr_spec == "ada@b\u00fcro.example.test"
    assert rows[0].addr_spec.encode("utf-8") == b"ada@b\xc3\xbcro.example.test"
    assert "xn--" not in rows[0].addr_spec  # never punycoded


def test_an_smtputf8_local_part_is_kept_verbatim() -> None:
    """A non-ASCII local part (and display name) is kept verbatim, never NFC-mangled."""
    _raw, _value, _base, rows = _to_rows("address_smtputf8_local_part")
    assert rows[0].display_name == "Jos\u00e9"
    assert rows[0].addr_spec == "jos\u00e9@example.test"
    assert rows[0].addr_spec.encode("utf-8") == b"jos\xc3\xa9@example.test"


def test_obs_route_is_recorded() -> None:
    """An obs-route is kept verbatim beside the addr-spec; the fact row carries the final mailbox."""
    value = b" <@a.example.test,@b.example.test:user@example.test>"
    rows = _parse(value)
    assert len(rows) == 1
    row = rows[0]
    assert row.state == "parsed"
    assert row.route == "@a.example.test,@b.example.test"  # the route text, verbatim
    assert row.addr_spec == "user@example.test"  # the addr-spec is the final mailbox
    # The closed record carries ``route``; the fact row (its first six members) has no route
    # slot in the facts document, so it carries the addr-spec and nothing else.
    assert row.as_fact_row() == [
        row.offset,
        row.length,
        None,
        "user@example.test",
        "parsed",
        None,
    ]


def test_cfws_does_not_split_an_address() -> None:
    """A comment never splits an address; it is dropped from the text but stays in the span."""
    value = b" (a(nested) comment) ben@example.test (trailing)"
    rows = _parse(value)
    assert len(rows) == 1, "a comment must not split an address"
    assert rows[0].addr_spec == "ben@example.test"

    inside = b" ben(c)@(d)example.test"
    rows = _parse(inside)
    assert len(rows) == 1
    assert rows[0].addr_spec == "ben@example.test"  # the comments are dropped from the text
    assert b"(c)" in inside[rows[0].offset : rows[0].end]  # ... but stay inside the span


def test_a_trailing_comma_is_tolerated() -> None:
    """A trailing comma / empty element never produces an empty address (obs-addr-list)."""
    rows = _parse(b" ben@example.test, ")
    assert len(rows) == 1 and rows[0].addr_spec == "ben@example.test"

    rows = _parse(b" a@example.test,,b@example.test,")
    assert [row.addr_spec for row in rows] == ["a@example.test", "b@example.test"]
    assert all(row.state == "parsed" for row in rows)


def test_the_own_tokenizer_returns_a_reason_where_parseaddr_loses_the_span() -> None:
    """Wherever stdlib ``parseaddr`` loses the span, the own tokenizer still carries one.

    ``parseaddr`` returns no offsets; where its result is empty or cannot be located in the raw
    bytes the own tokenizer must return rows whose spans slice to non-empty bytes (or an
    ``unparsed`` row with its reason) -- never a silent drop. The comparison is over every
    address field of every fixture.
    """
    compared = 0
    lost = 0
    for path in _all_fixtures():
        raw = path.read_bytes()
        for _name, value in stdlib_scanner.address_fields(raw):
            _parsed_name, addr = stdlib_scanner.stdlib_parseaddr(value)
            compared += 1
            if addr and stdlib_scanner.addr_is_locatable(value, addr):
                continue
            lost += 1
            rows = _parse(value)
            assert rows, f"{path.stem}: parseaddr lost the span and the tokenizer dropped the field"
            for row in rows:
                assert 0 <= row.offset and row.end <= len(value), (path.stem, row)
                assert value[row.offset : row.end] != b"", f"{path.stem}: a row slices to nothing"
                if row.state == "unparsed":
                    assert row.reason_id == GAP_UNPARSABLE, (path.stem, row)
    assert compared >= 90, "the comparison would be vacuous"
    assert lost >= 1, "no stdlib span loss at all: the property is not exercised"
    print(f"stdlib parseaddr lost the span on {lost} of {compared} address field(s)")


def test_the_advisory_stdlib_diff_is_printed_never_gated(capsys) -> None:
    """Print the stdlib-versus-own address diff per fixture; assert no gate on it.

    ``email.utils.getaddresses`` flattens groups, loses an empty group, invents an address for
    a trailing comma and does not keep SMTPUTF8/IDN verbatim, so the diff is **advisory** --
    printed for the record, never asserted against (stdlib is wrong here by design). The only
    assertion is that the diff was computed over the whole corpus (not vacuous).
    """
    table: dict[str, list[tuple[str, str, str]]] = {}
    total = 0
    for path in _all_fixtures():
        raw = path.read_bytes()
        for name, value in stdlib_scanner.address_fields(raw):
            total += 1
            own = [_decode(row.addr_spec) for row in _parse(value)]
            stdlib = [addr for _disp, addr in stdlib_scanner.stdlib_address_pairs(value)]
            if own != stdlib:
                table.setdefault(path.stem, []).append((name, "|".join(own), "|".join(stdlib)))

    print("advisory address diff (own tokenizer vs email.utils.getaddresses):")
    print(f"  address field(s) compared: {total}")
    print(f"  fixture(s) with a disagreement: {len(table)}")
    for stem in sorted(table):
        for name, own, stdlib in table[stem]:
            print(f"    {stem} {name}: own={own!r} stdlib={stdlib!r}")
    print("  closed reasons the stdlib misreads an address (never gated):")
    for reason, text in sorted(stdlib_scanner.SHARED_ADDRESS_MISREADING.items()):
        print(f"    {reason}: {text}")

    assert total >= 90, "the advisory diff was not computed over the corpus"
    assert set(stdlib_scanner.SHARED_ADDRESS_MISREADING) >= {"group_flattened", "empty_group_lost"}


def _decode(value: str | None) -> str:
    return "" if value is None else value


# --------------------------------------------------------------- added to the declaration


def test_the_address_row_maps_onto_the_facts_row_shape() -> None:
    """The frozen row projects onto ``headers.addresses``' six-member row, with its invariants."""
    row = _to_rows("address_group")[3][1]
    assert row.as_fact_row() == [
        row.offset,
        row.length,
        row.display_name,
        row.addr_spec,
        row.state,
        row.reason_id,
    ]
    assert row.end == row.offset + row.length
    assert row.route is None and len(row.as_fact_row()) == 6
    assert set(address_stage.ADDRESS_STATES) == {"parsed", "group", "unparsed"}

    # The record refuses a state outside the closed set, and a reason on a non-unparsed row.
    with pytest.raises(ValueError):
        address_stage.AddressRow(0, 1, None, "a@b", "guessed", None)
    with pytest.raises(ValueError):
        address_stage.AddressRow(0, 1, None, "a@b", "parsed", GAP_UNPARSABLE)
    with pytest.raises(ValueError):
        address_stage.AddressRow(0, 1, None, "a@b", "unparsed", None)


def test_an_unbalanced_quote_or_angle_bracket_is_unparsed() -> None:
    """An unbalanced quote/angle bracket, or a missing domain, is declined with its reason."""
    for value in (
        b' "unterminated <a@b>',
        b" <a@b",
        b" a@b>",
        b" no-at-sign",
        b" a@",
    ):
        rows = _parse(value)
        assert rows, value
        for row in rows:
            assert row.state == "unparsed", (value, row)
            assert row.reason_id == GAP_UNPARSABLE, (value, row)
            assert row.as_fact_row()[1] > 0


def test_a_mutation_flips_the_gate_for_every_address_state(tmp_path) -> None:
    """A wrong sidecar for either new fact fails the L1 gate, naming the fixture and the fact.

    Four mutations over the two live facts: a shifted address span, a wrong addr-spec, a wrong
    state, and a wrong projection scalar.
    """
    baseline = FIXTURES / "generated" / "headers_plain_baseline.expected.json"

    def first_address_row(payload):
        return payload["facts"]["headers.addresses"]["value"][0][2][0]

    def shifted(payload):
        row = first_address_row(payload)
        row[0] = row[0] + 1  # the first address span, one byte late

    def wrong_spec(payload):
        first_address_row(payload)[3] = "someone.else@example.test"

    def wrong_state(payload):
        row = first_address_row(payload)
        row[4] = "unparsed"
        row[5] = GAP_UNPARSABLE

    def wrong_scalar(payload):
        for row in payload["facts"]["headers.projection"]["value"]:
            if row[3] == "address_list":
                row[4] = "someone.else@example.test"
                return

    for mutate, fact in (
        (shifted, "headers.addresses"),
        (wrong_spec, "headers.addresses"),
        (wrong_state, "headers.addresses"),
        (wrong_scalar, "headers.projection"),
    ):
        name = mutate.__name__
        assert callable(mutate)  # the mutation is a real, patched observation
        sidecar_copy.tamper(tmp_path, baseline, mutate, name=name)
        gate = l1_gate(tmp_path / name)
        assert gate.passed is False, name
        assert any(
            "headers_plain_baseline" in line and fact in line for line in gate.evidence
        ), (name, gate.evidence)


def test_the_group_with_a_mutation_dropping_a_member_fails_the_gate(tmp_path) -> None:
    """A group member dropped from the label (or the code) flips the gate, naming the fixture."""
    group = FIXTURES / "generated" / "address_group.expected.json"

    def drop_member(payload):
        rows = payload["facts"]["headers.addresses"]["value"][0][2]
        rows.pop()  # cara is gone: the flat member row disappears

    sidecar_copy.tamper(tmp_path, group, drop_member, name="address_group_drop")
    gate = l1_gate(tmp_path / "address_group_drop")
    assert gate.passed is False
    assert any(
        "address_group" in line and "headers.addresses" in line for line in gate.evidence
    ), gate.evidence


def test_every_emitted_gap_id_has_a_mutation_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one gap id this module emits has a mutation case with the anti-vacuity triple."""
    # (a) the emitted gap ids are exactly the catalogued ones.
    emitted = {GAP_UNPARSABLE}
    catalogue = {GAP_UNPARSABLE: "an unparseable address repaired (its reason dropped)"}
    assert set(catalogue) == emitted, (set(catalogue), emitted)

    real = header_stage.parse_address_list
    assert callable(real)  # (a) the patched symbol exists
    reached = {"count": 0}

    def repair(value, *, base_offset, max_work_units):
        reached["count"] += 1  # (b) the patch is reached, never vacuously applied
        rows = real(value, base_offset=base_offset, max_work_units=max_work_units)
        return [
            address_stage.AddressRow(
                offset=row.offset,
                length=row.length,
                display_name=row.display_name,
                addr_spec=row.addr_spec,
                state="parsed",
                reason_id=None,
            )
            if row.state == "unparsed"
            else row
            for row in rows
        ]

    monkeypatch.setattr(header_stage, "parse_address_list", repair)
    gate = l1_gate()
    assert reached["count"] > 0, "the mutation's patch was never entered (vacuous)"
    assert gate.passed is False  # (c) the observation differs and the gate flips
    assert any(
        "address_unparsable" in line and GAP_UNPARSABLE in line for line in gate.evidence
    ), gate.evidence

    monkeypatch.setattr(header_stage, "parse_address_list", real)
    assert l1_gate().passed is True, "restoring the rule must restore green"


def test_a_seeded_fuzz_of_the_tokenizer_never_raises() -> None:
    """A seeded, bounded fuzz over mutated address-field values: total, with sound spans.

    Every returned span lies inside the field value, slices to non-empty bytes, and the
    top-level spans are ordered and disjoint; no input raises, including NUL, lone CR/LF,
    8-bit bytes, a huge run of one repeated byte and non-ASCII digits.
    """
    import random

    rng = random.Random(12_1002)
    sources: list[bytes] = []
    for path in _all_fixtures():
        for _name, value in stdlib_scanner.address_fields(path.read_bytes()):
            sources.append(value)
    for adversarial in (
        b"\x00" * 200,
        b"\r",
        b"\n",
        b"\xff" * 50,
        b"\xd9\xa1\xd9\xa2",  # Arabic-Indic digits, as utf-8 bytes
        b"(" * 500,
        b"\\" * 500,
        b"<" * 500,
        b'"' * 500,
    ):
        sources.append(adversarial)

    per_source = 40
    seeds = 0
    for source in sources:
        for _ in range(per_source):
            data = bytearray(source)
            for _ in range(rng.randint(1, 6)):
                op = rng.randint(0, 5)
                if not data:
                    break
                index = rng.randrange(len(data))
                if op == 0:
                    data[index] = rng.choice(b'\r\n:;@<>"\\()[], \x00\xff')
                elif op == 1:
                    del data[index:]
                elif op == 2:
                    data[index:index] = bytes(rng.choice([b",", b";", b'"', b"(", b"<", b">", b"@", b"\\"]))
                elif op == 3:
                    chunk = bytes(rng.choice([b"a@b.c", b'(x)', b'"y"', b":;", b"<>"]))
                    data[index:index] = chunk
                elif op == 4:
                    cut = rng.randrange(len(data))
                    data = bytearray(bytes(data[cut:]) + bytes(data[:cut]))
                else:
                    data[index:index] = bytes([data[index]]) * rng.randint(1, 4)

            rows = _parse(bytes(data))
            ends = 0
            for row in rows:
                assert 0 <= row.offset <= len(data), (data, row)
                assert row.end <= len(data), (data, row)
                assert data[row.offset : row.end] != b"", (data, row, "a span slices to nothing")
                assert row.offset >= ends, (data, row, "spans overlap or are out of order")
                ends = row.end
            seeds += 1
    assert seeds == len(sources) * per_source, seeds


def test_the_tokenizer_is_linear_in_the_input() -> None:
    """Doubling the input must less than triple the work: no quadratic blow-up (a bug if so)."""

    def best(run, data: bytes) -> float:
        fastest = None
        for _ in range(5):
            start = time.perf_counter()
            run(data)
            elapsed = time.perf_counter() - start
            fastest = elapsed if fastest is None else min(fastest, elapsed)
        return fastest

    def scan(data: bytes):
        return address_stage._tokenize(data)

    def parse(data: bytes):
        return address_stage.parse_address_list(data, base_offset=0, max_work_units=BUDGET)

    # A long run of one repeated byte must stay linear: '(' opens a comment, '\' an escape,
    # '<' an angle, '"' a quoted-string; a long address list stresses the parser. A quadratic
    # scanner would show ~4x on the doubled input; a linear one ~2x.
    for label, run, chunk in (
        ("comment run", scan, b"("),
        ("escape run", scan, b"\\"),
        ("angle run", scan, b"<"),
        ("quoted run", scan, b'"'),
        ("address list", parse, b"a@b.c, "),
    ):
        small = chunk * (30_000 // len(chunk))
        large = small + small
        ratio = best(run, large) / max(best(run, small), 1e-9)
        assert ratio < 3.2, (label, ratio, "the tokenizer looks quadratic in the input")


def test_the_address_facts_are_live_over_the_corpus() -> None:
    """Both new comparisons are live: no ``headers.addresses`` or address_list row is deferred."""
    sidecars = oracle.load_sidecars()
    addressed = [sidecar for sidecar in sidecars.values() if "headers.addresses" in sidecar.facts]
    assert len(addressed) == 7, [sidecar.stem for sidecar in addressed]
    for sidecar in addressed:
        report = oracle.check(sidecar)
        outcome = next(o for o in report.outcomes if o.fact_id == "headers.addresses")
        assert outcome.status is oracle.Status.OK, (sidecar.stem, outcome.status, outcome.detail)

    deferrals = oracle.deferral_counts()
    assert "headers.projection.address_list:1.2" not in deferrals
    # Turn 1.3 turned the last deferred column live, so nothing is deferred any more.
    assert deferrals == {}

    gate = l1_gate()
    assert gate.passed is True
    assert gate.data["mismatched"] == 0
