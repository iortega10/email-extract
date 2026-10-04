"""Copy a committed sidecar (and its fixture's bytes) into a temporary directory and tamper it.

The falsification tests never touch a committed label: they work on a *copy*, in a directory the
test owns, so a deliberately wrong sidecar cannot be mistaken -- later, out of context -- for
ground truth. The copy keeps the fixture's real bytes, so a measurement over the bytes is a real
measurement rather than a file that fails to open. ``write_inline`` builds a fixture and its
sidecar from hand-typed bytes, for the gaps no committed fixture carries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"

#: Sidecars the tampering helpers are used on, named once so a test does not repeat the path.
PLAIN_SIMPLE = FIXTURES / "generated" / "plain_simple.expected.json"
ALTERNATIVE = FIXTURES / "generated" / "alternative_text_html.expected.json"
ATTACHMENTS = FIXTURES / "generated" / "attachments_mixed.expected.json"


def payload_of(sidecar: Path) -> MutableMapping[str, Any]:
    return json.loads(sidecar.read_text(encoding="utf-8"))


def write(directory: Path, payload: Mapping[str, Any], *, source: Path) -> Path:
    """Write ``payload`` beside a copy of ``source``'s fixture bytes, and return the sidecar path."""
    directory.mkdir(parents=True, exist_ok=True)
    fixture = payload["fixture"]
    original = source.parent / fixture
    (directory / fixture).write_bytes(original.read_bytes())
    sidecar = directory / source.name
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar


def tamper(
    tmp_path: Path,
    source: Path,
    mutate: Callable[[MutableMapping[str, Any]], None],
    *,
    name: str | None = None,
) -> Path:
    """A copy of ``source`` with ``mutate`` applied to its JSON, in ``tmp_path/<name>``."""
    payload = payload_of(source)
    mutate(payload)
    return write(tmp_path / (name or source.name.removesuffix(".expected.json")), payload, source=source)


def write_inline(
    directory: Path,
    name: str,
    raw: bytes,
    payload: Mapping[str, Any],
) -> Path:
    """Write hand-typed ``raw`` bytes as ``<name>.eml`` and ``payload`` as its sidecar."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.eml").write_bytes(raw)
    sidecar = directory / f"{name}.expected.json"
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar
