"""Turn 0.2: the container interface, the ``.eml`` adapter and the in-memory FAKE.

The rules under test (build spec, Turn 0.2; D13/D14): the walker measures a
container, not a file; the ``.eml`` adapter serves the bytes verbatim; and the
second ``container_kind`` is a hand-built FAKE -- no CFB code, no ``olefile``
import, and no invented facts. Inputs are exercised through ``Path`` and
``memory_bytes``, both routes.
"""

from __future__ import annotations

import sys

from emailextract.container import (
    EmlContainer,
    FakeContainer,
    FileMaterial,
    MemoryMaterial,
    PathMaterial,
    memory_bytes,
)
from emailextract.ids import sha256_hex
from emailextract.model import ContainerKind
from emailextract.walk import walk

MESSAGE = b"From: a@example.com\r\nSubject: container\r\n\r\nbody line\r\n"


def test_file_material_reads_the_same_bytes_through_path_and_memory(tmp_path) -> None:
    path = tmp_path / "one.eml"
    path.write_bytes(MESSAGE)
    for material in (PathMaterial(path), memory_bytes(MESSAGE)):
        assert isinstance(material, FileMaterial)
        assert isinstance(material, (PathMaterial, MemoryMaterial))
        assert material.size() == len(MESSAGE)
        assert material.read_bytes() == MESSAGE
        with material.open_text() as handle:
            assert handle.read() == MESSAGE.decode("utf-8")


def test_the_eml_adapter_is_rfc822_and_its_raw_bytes_are_verbatim(tmp_path) -> None:
    path = tmp_path / "one.eml"
    path.write_bytes(MESSAGE)
    for container in (EmlContainer(path), EmlContainer(memory_bytes(MESSAGE))):
        assert container.kind is ContainerKind.RFC822
        assert container.raw_bytes() == MESSAGE
        assert container.container_hash() == sha256_hex(MESSAGE)
        facts = container.container_facts()
        assert facts["adapter"] == "eml"
        assert facts["size_bytes"] == str(len(MESSAGE))
        assert facts["raw_sha256"] == sha256_hex(MESSAGE)


def test_the_same_bytes_hash_the_same_over_both_routes(tmp_path) -> None:
    path = tmp_path / "one.eml"
    path.write_bytes(MESSAGE)
    assert EmlContainer(path).container_hash() == EmlContainer(memory_bytes(MESSAGE)).container_hash()
    assert EmlContainer(path).container_hash() == sha256_hex(MESSAGE)


def test_the_walk_is_identical_over_path_and_memory(tmp_path) -> None:
    path = tmp_path / "one.eml"
    path.write_bytes(MESSAGE)
    on_disk = walk(EmlContainer(path))
    in_memory = walk(EmlContainer(memory_bytes(MESSAGE)))
    assert on_disk.container_hash == in_memory.container_hash
    assert on_disk.parts == in_memory.parts
    assert on_disk.regions == in_memory.regions
    assert on_disk.total_bytes == in_memory.total_bytes


def test_the_fake_container_is_a_second_container_kind_without_cfb_code() -> None:
    fake = FakeContainer(MESSAGE)
    assert fake.kind is ContainerKind.CFB_MSG
    assert fake.raw_bytes() == MESSAGE
    assert fake.container_hash() == sha256_hex(MESSAGE)
    assert fake.container_facts()["adapter"] == "fake"
    assert fake.container_facts()["synthetic"] == "in_memory"
    # The whole point of the fake: no CFB dependency anywhere in the import path.
    assert "olefile" not in sys.modules
    assert "compoundfiles" not in sys.modules


def test_the_fake_never_claims_a_real_container_fact() -> None:
    result = walk(FakeContainer(MESSAGE))
    assert result.container_kind is ContainerKind.CFB_MSG
    assert result.container_facts["synthetic"] == "in_memory"
    root = result.parts[0]
    # Nothing measured means nothing reported: no Content-Type was read, so the
    # content type is absent -- never a guessed text/plain.
    assert root.content_type is None
    assert root.decode_chain.declared_cte is None
    assert root.decode_chain.declared_charset is None
    assert walk(FakeContainer(MESSAGE)).parts == walk(EmlContainer(memory_bytes(MESSAGE))).parts
