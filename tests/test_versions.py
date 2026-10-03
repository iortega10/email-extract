"""Turn 0.1 tests: versions.py keeps its frozen names, and all eight document it.

Docstrings for module-level constants live as attribute docstrings in the source
(PEP 258), so the test parses the file -- stdlib only; docstring-parser is not an
already-available dependency here and S2 allows plain inspection.
"""

from __future__ import annotations

import ast
import pathlib
import re

import emailextract.versions as versions

EXPECTED_FROZEN = {
    "OUTPUT_SCHEMA_VERSION",
    "TIMEEVENT_VERSION",
    "DECODE_CHAIN_VERSION",
    "HEADERTEXT_VERSION",
    "HTMLTEXT_VERSION",
    "TEXTMODEL_VERSION",
    "EMAIL_PARSER_VERSION",
    "FLAG_SCHEMA_VERSION",
}

CONSTANT_NAME = re.compile(r"\b[A-Z][A-Z0-9]*_VERSION\b")


def _attribute_docstrings() -> dict[str, str]:
    source = pathlib.Path(versions.__file__).read_text(encoding="utf-8")
    body = ast.parse(source).body
    docs: dict[str, str] = {}
    for index, node in enumerate(body):
        names: list[str] = []
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not names:
            continue
        following = body[index + 1] if index + 1 < len(body) else None
        if isinstance(following, ast.Expr) and isinstance(following.value, ast.Constant) and isinstance(
            following.value.value, str
        ):
            for name in names:
                docs[name] = following.value.value
    return docs


def test_every_frozen_constant_is_exposed_and_named() -> None:
    exposed = {name for name in dir(versions) if name.endswith("_VERSION")}
    assert exposed == EXPECTED_FROZEN
    for name in EXPECTED_FROZEN:
        value = getattr(versions, name)
        assert isinstance(value, str) and value, name


def test_every_version_constant_documents_itself() -> None:
    """S2: each frozen constant documents itself -- prose, not another field name."""
    docs = _attribute_docstrings()
    for name in sorted(EXPECTED_FROZEN):
        assert name in docs, f"{name} has no attribute docstring"
        prose = docs[name].strip()
        assert len(prose.split()) >= 3, f"{name} docstring is not prose: {prose!r}"
        for token in CONSTANT_NAME.findall(prose):
            assert token == name, f"{name} documents itself as {token}"
