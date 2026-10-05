"""The corpus HTML-projection fingerprint (Turn 1.5b, item 6).

One hash over every committed HTML part's projection, so the cross-interpreter check can
say whether CPython 3.14 and CPython 3.11 read the corpus the same way (``html.parser`` can
differ across CPython patch levels). It imports the package but **no test framework**, so a
bare second interpreter -- one with the package importable and no pytest -- can run it:

    python tests/support/html_projection_hash.py

``tests/test_selection.py`` computes the same hash in-process and runs this module under the
second interpreter ; a disagreement fails loudly, naming both interpreters.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # let a bare interpreter run this file directly
    sys.path.insert(0, str(ROOT))

from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.selection import html_projections  # noqa: E402
from emailextract.walk import walk  # noqa: E402

#: The caller's caps for every projection this fingerprint covers: the approved untrusted
#: defaults (``Limits.untrusted()``), fixed here so both interpreters build the same bound.
CAP_DEPTH = 16
CAP_ELEMENTS = 1000


def _fixture_paths() -> list[Path]:
    """Every committed ``.eml`` under ``fixtures/`` (``fixtures/real/`` is machine-local)."""
    found = [
        path
        for path in sorted((ROOT / "fixtures").rglob("*.eml"))
        if "real" not in path.relative_to(ROOT / "fixtures").parts
    ]
    return found


def projection_rows() -> list[tuple[str, str, str]]:
    """``(fixture, locator, sha256)`` per HTML part, the hash over its text and its spans."""
    rows: list[tuple[str, str, str]] = []
    for path in _fixture_paths():
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        result = walk(EmlContainer(memory_bytes(raw)))
        for locator, projection in html_projections(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        ):
            payload = json.dumps(
                [projection.text, [list(span) for span in projection.spans]],
                ensure_ascii=False,
            )
            rows.append((relative, locator, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
    return rows


def corpus_projection_hash() -> str:
    """The sha256 over every HTML part's ``(fixture, locator, projection hash)`` row."""
    joined = "\n".join(f"{rel}|{loc}|{digest}" for rel, loc, digest in projection_rows())
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def interpreter_label() -> str:
    """A recorded-only run input: the interpreter and patch level this module ran under."""
    return f"CPython {sys.version.split()[0]}"


if __name__ == "__main__":
    print("interpreter:", interpreter_label())
    print("html parts:", len(projection_rows()))
    print("corpus projection hash:", corpus_projection_hash())
