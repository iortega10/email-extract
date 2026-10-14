"""Turn 1b.5: the bodies of a projected ``.msg`` through the Phase 1 stages.

The projection carries a pass-through ``0x1013`` HTML leaf (its bytes are the stream's, CTE
``binary``) and a re-encoded ``0x1000`` plain leaf (UTF-8, CTE ``8bit``), either alone or as
a synthetic ``multipart/alternative``. Every leaf is ``part_level`` / ``container_stream``
(contract section 8, point 4): ``resolve_span`` adds the *virtual* framing's offset even when
the leaf bytes equal the stream's, so no `.msg` leaf may ever claim ``exact`` precision (A3).

The four declared tests are:

* ``test_a_pass_through_html_leaf_is_never_exact``;
* ``test_a_plain_leaf_is_reencoded_and_container_stream``;
* ``test_selection_picks_html_over_plain``;
* ``test_sector_accounting_sums_to_the_file_length_end_to_end``;

plus the C5 cross-container comparison as an extra.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from emailextract import cfb  # noqa: E402
from emailextract.assemble import assemble, resolve_span  # noqa: E402
from emailextract.container import ContainerStreamRef, EmlContainer, memory_bytes  # noqa: E402
from emailextract.ids import sha256_hex  # noqa: E402
from emailextract.model import ContainerKind, ContainerStreamAxis, Selection  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from emailextract.text import analyse_part  # noqa: E402
from emailextract.walk import walk  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()
SECTOR_CLASSES = (
    "sectors.header",
    "sectors.difat",
    "sectors.fat",
    "sectors.minifat",
    "sectors.directory",
    "sectors.stream",
    "sectors.free",
    "sectors.slack",
)


def _container(name: str) -> MsgContainer:
    return MsgContainer((MSG / f"{name}.msg").read_bytes())


def _by_path(container: MsgContainer) -> dict[str, object]:
    return {part.path: part for part in walk(container, limits=LIMITS).parts}


def _record(document, part_id: str):
    return next(record for record in document.parts if record.part_id == part_id)


# --------------------------------------------------- the declared tests


def test_a_pass_through_html_leaf_is_never_exact() -> None:
    """The ``0x1013`` leaf is a ``STREAM`` row (C6) but its precision is ``part_level`` (A3)."""
    container = _container("msg_plain_and_html")
    document = assemble(container, limits=LIMITS)
    parts = _by_path(container)
    html = parts["1.2"]
    record = _record(document, html.part_id)
    assert record.stream_ref.axis is ContainerStreamAxis.STREAM
    assert record.stream_ref.stream == "__substg1.0_10130102"
    assert record.size_bytes == record.stream_ref.byte_len  # the stream's own size (section 5)
    opened = cfb.open_cfb((MSG / "msg_plain_and_html.msg").read_bytes())
    assert isinstance(opened, cfb.CfbFile)
    payload, _status = cfb.read_stream(opened, "__substg1.0_10130102")
    assert record.sha256 == sha256_hex(payload)
    # The leaf is never ``exact``: the precompute forces ``container_stream``.
    forced = analyse_part(container.raw_bytes(), html, container_stream=True)
    assert forced is not None
    assert forced.verbatim_precision == "part_level"
    assert forced.verbatim_reason == "container_stream"
    assert forced.offset_map is None
    # The negative case: without the flag the same virtual bytes claim ``exact`` (the finding).
    assert analyse_part(container.raw_bytes(), html).verbatim_precision == "exact"
    # And a citation names the source stream, never a virtual offset.
    answer = resolve_span(container, html.part_id, "plain", 0, 1)
    assert isinstance(answer, ContainerStreamRef)
    assert answer.axis is ContainerStreamAxis.STREAM


def test_a_plain_leaf_is_reencoded_and_container_stream() -> None:
    """The ``0x1000`` leaf is UTF-8 text re-encoded from the stream, and a ``REENCODED`` row."""
    container = _container("msg_plain_and_html")
    document = assemble(container, limits=LIMITS)
    plain = _by_path(container)["1.1"]
    record = _record(document, plain.part_id)
    assert record.stream_ref.axis is ContainerStreamAxis.REENCODED
    assert record.stream_ref.stream == "__substg1.0_1000001F"
    # The leaf's bytes are the UTF-8 re-encoding (the bytes a consumer reads, section 5).
    expected = "\r\n".encode("utf-8")
    assert record.size_bytes == len(expected)
    assert record.sha256 == sha256_hex(expected)
    assert record.stream_ref.byte_len == len("\r\n".encode("utf-16-le"))
    forced = analyse_part(container.raw_bytes(), plain, container_stream=True)
    assert forced is not None
    assert forced.verbatim_precision == "part_level"
    assert forced.verbatim_reason == "container_stream"
    assert forced.text == "\r\n"
    # The charset is the projection's own declared UTF-8, recorded as such (point 5).
    assert record.decode_chain.used_charset == "utf-8"
    assert record.decode_chain.declared_charset == "utf-8"


def test_selection_picks_html_over_plain() -> None:
    """A ``multipart/alternative`` with both bodies selects the HTML leaf (RFC 2046 order)."""
    container = _container("msg_plain_and_html")
    document = assemble(container, limits=LIMITS)
    parts = _by_path(container)
    assert parts["1"].content_type == "multipart/alternative"
    plain = _record(document, parts["1.1"].part_id)
    html = _record(document, parts["1.2"].part_id)
    assert html.selection is Selection.SELECTED
    assert plain.selection is Selection.ALTERNATIVE_NOT_SELECTED
    # The plain leaf comes first in part order (the RFC 2046 order the projection writes).
    assert [record.part_id for record in document.parts] == [
        parts["1"].part_id,
        parts["1.1"].part_id,
        parts["1.2"].part_id,
    ]
    # A single-leaf message has no selection to make.
    only = assemble(_container("msg_html_only_no_plain"), limits=LIMITS)
    assert only.parts[-1].selection is Selection.NOT_APPLICABLE


def test_sector_accounting_sums_to_the_file_length_end_to_end() -> None:
    """The eight ``sectors.*`` facts close to the file length on every fixture and in the store."""
    for name in (
        "msg_html_only_no_plain",
        "msg_plain_and_html",
        "msg_zero_length_body",
        "msg_headers_html",
        "msg_property_vs_header_conflict",
    ):
        data = (MSG / f"{name}.msg").read_bytes()
        container = _container(name)
        facts = container.container_facts()
        total = sum(int(facts[f"sectors.{name_}"]) for name_ in cfb.SECTOR_CLASSES)
        assert total == len(data), (name, total, len(data))
        # ... and it is the CFB reader's own account, class for class.
        opened = cfb.open_cfb(data)
        assert isinstance(opened, cfb.CfbFile)
        assert container.sector_accounting == {
            f"sectors.{key}": value for key, value in opened.accounting
        }
        assert all(f"sectors.{key}" in facts for key in cfb.SECTOR_CLASSES)


# --------------------------------------------------- the extra


def test_the_same_message_as_eml_and_msg_differs_only_where_d14_says() -> None:
    """C5: the projection's virtual bytes as an ``.eml`` give one document shape."""
    container = _container("msg_plain_and_html")
    document = assemble(container, limits=LIMITS)
    twin = EmlContainer(memory_bytes(container.raw_bytes()))
    other = assemble(twin, limits=LIMITS)

    # One shape: the same nested field names, ignoring the optional ``stream_ref`` subtree
    # (its fields are present only when a container publishes source provenance).
    assert {path for path in _shape(document) if "stream_ref" not in path} == {
        path for path in _shape(other) if "stream_ref" not in path
    }
    # D14's document-level differences.
    assert document.container_kind is ContainerKind.CFB_MSG
    assert other.container_kind is ContainerKind.RFC822
    assert document.container_hash == sha256_hex((MSG / "msg_plain_and_html.msg").read_bytes())
    assert other.container_hash != document.container_hash
    assert document.container_facts.facts != other.container_facts.facts
    # The parts tree is the same part for part; only these fields may differ.
    allowed = {"part_id", "parent_part_id", "stream_ref", "encoding_source", "size_bytes", "sha256"}
    assert len(document.parts) == len(other.parts)
    for left, right in zip(document.parts, other.parts):
        assert left.content_type == right.content_type
        assert left.role == right.role
        assert left.selection == right.selection
        for field in dataclasses.fields(left):
            if getattr(left, field.name) != getattr(right, field.name):
                assert field.name in allowed, field.name
    # The header records: the ``.msg`` excludes the projection's own scaffolding (D2, C6),
    # and every shared field is the same value with the ``.msg`` carrying its source ref.
    scaffolding = {"MIME-Version", "Content-Type", "Content-Transfer-Encoding"}
    assert [field.name for field in document.headers] == [
        field.name for field in other.headers if field.name not in scaffolding
    ]
    twin_by_name = {field.name: field for field in other.headers}
    for field in document.headers:
        assert field.raw_value == twin_by_name[field.name].raw_value
        assert field.stream_ref is not None
        assert twin_by_name[field.name].stream_ref is None


def _shape(value: object, prefix: str = "") -> set[str]:
    """The nested field-name set of a record tree (one ``EmailDocument``'s shape)."""
    out: set[str] = set()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            out.add(prefix + "." + field.name)
            out |= _shape(getattr(value, field.name), prefix + "." + field.name)
    elif isinstance(value, (list, tuple)):
        for item in value:
            out |= _shape(item, prefix + "[]")
    return out
