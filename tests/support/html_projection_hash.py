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
from emailextract.quote import i18n  # noqa: E402
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


#: The hand-typed inputs the quote-label normalisation table pins. NFC only (decision 3: NFKC is
#: not used, and the label tables are case-sensitive), so a careless implementation that casefolded
#: or NFKC-normalised a head would move one of these rows.
NORMALISATION_INPUTS: tuple[str, ...] = (
    "Am 12.01.2021 schrieb Anna:",  # already NFC
    "A\u0308m 12.01.2021 schrieb Anna:",  # A + combining diaeresis, composes to U+00C4
    "From:\u00a0Anna",  # a no-break space stays a no-break space
    "From:\u202fAnna",  # a narrow no-break space stays itself
    "From: Anna",  # a plain ASCII head
    "from: Anna",  # a lower-case head (the tables are case-sensitive, so it fills no slot)
    "Von: Anna",  # German, as written
)


def normalisation_rows() -> list[list[object]]:
    """``[input, nfc(input), label_shaped, slot_of_line(en), slot_of_line(de)]`` per pinned input."""
    return [
        [
            line,
            i18n.nfc(line),
            i18n.label_shaped(line),
            i18n.slot_of_line(line, "en"),
            i18n.slot_of_line(line, "de"),
        ]
        for line in NORMALISATION_INPUTS
    ]


def normalisation_hash() -> str:
    """The sha256 over the pinned normalisation rows."""
    payload = json.dumps(normalisation_rows(), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def interpreter_label() -> str:
    """A recorded-only run input: the interpreter and patch level this module ran under."""
    return f"CPython {sys.version.split()[0]}"


def as_json(*, ensure_ascii: bool = True) -> str:
    """The whole fingerprint as one machine-readable JSON object (the golden's own shape).

    ``ensure_ascii`` defaults **on** so a bare child interpreter prints it on any stdout encoding
    (a Windows cp1252 console cannot encode a combining mark); the JSON decodes to the same values.
    """
    return json.dumps(
        {
            "interpreter": interpreter_label(),
            "cpython_minor": list(sys.version_info[:2]),
            "corpus_hash": corpus_projection_hash(),
            "rows": [list(row) for row in projection_rows()],
            "normalisation": normalisation_rows(),
            "normalisation_hash": normalisation_hash(),
        },
        ensure_ascii=ensure_ascii,
        sort_keys=True,
    )


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(as_json())
    else:
        print("interpreter:", interpreter_label())
        print("html parts:", len(projection_rows()))
        print("corpus projection hash:", corpus_projection_hash())
        print("quote normalisation hash:", normalisation_hash())
