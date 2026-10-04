"""Turn 1.0b: the label ledger -- a sidecar or a gate cannot be edited in place.

An **additions-only** sha256 map of the hand-typed labels and the oracle over them,
the same discipline ``tools/behavior_ledger.py`` uses for versions. It covers every
file whose bytes are a *label* or the *oracle over labels*:

1. every committed sidecar ``*.expected.json`` under ``fixtures/**`` (the label
   corpus; ``fixtures/real/`` is machine-local and never covered);
2. every file under ``tests/support/**`` (the independent checkers, the fake store,
   the sidecar-copy helper);
3. every file under ``emailextract/evals/**`` (the oracle, the gates, the
   falsifiability catalogue, the metrics CLI).

**The additions-only rule.** ``tools/update_label_ledger.py`` appends a line for a
file not yet recorded (and only for a file that exists); it refuses to write when a
*recorded* file's bytes differ from its fingerprint and refuses when a recorded file
is gone. So a turn that edits a gate or a sidecar cannot record its way out of it:
the remedy is a new file, or an explicit, owner-approved ledger change in the same
commit as the edit and named in the turn prompt's allow-list.

Run it in the same commit as the change that caused it::

    python tools/update_label_ledger.py

``--check`` reports every disagreement and exits non-zero without writing anything,
which is what ``tests/test_label_ledger.py`` and a reviewer both need.
"""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Mapping

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

LEDGER_PATH = _ROOT / "tests" / "ledger" / "label_ledger.json"

#: The three covered path sets, relative to the repository root.
FIXTURES = _ROOT / "fixtures"
SUPPORT = _ROOT / "tests" / "support"
EVALS = _ROOT / "emailextract" / "evals"

#: A directory that is machine-local and never part of the corpus (``fixtures/real/``).
_LOCAL_ONLY = "real"

_HEADER = (
    "Additions-only sha256 fingerprints of the hand-typed labels and the oracle that "
    "reads them. A path is relative to the repository root and posix; the fingerprint "
    "is sha256 of the file's bytes. Adding a file appends a line; changing or removing "
    "a recorded file is refused in place (that is a label edit and the rule is the "
    "label is never edited). Record lines with tools/update_label_ledger.py in the "
    "same commit as the change that caused them."
)


def sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def covered_files(root: Path | str = _ROOT) -> dict[str, Path]:
    """Every covered file, keyed by its posix path relative to ``root``.

    Discovered at call time so a file added under a covered path is a *new* file the
    ledger has not recorded, not something silently ignored.
    """
    base = Path(root)
    found: dict[str, Path] = {}

    def add(path: Path) -> None:
        found[path.relative_to(base).as_posix()] = path

    fixtures = base / "fixtures"
    if fixtures.is_dir():
        for path in sorted(fixtures.rglob("*.expected.json")):
            if _LOCAL_ONLY not in path.relative_to(fixtures).parts:
                add(path)
    for directory in (base / "tests" / "support", base / "emailextract" / "evals"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                add(path)
    return found


def fingerprints(root: Path | str = _ROOT) -> dict[str, str]:
    """The current fingerprint of every covered file, keyed by its posix relative path."""
    return {rel: sha256_hex(path.read_bytes()) for rel, path in covered_files(root).items()}


def load_ledger(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """The ledger as it stands on disk; ``{}`` (no ``files``) when there is none yet."""
    ledger_path = Path(path) if path is not None else LEDGER_PATH
    if not ledger_path.is_file():
        return {"files": {}}
    loaded = json.loads(ledger_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("the label ledger must be a JSON object")
    files = loaded.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("the label ledger's 'files' must be a JSON object")
    return {"files": {str(name): str(digest) for name, digest in files.items()}}


def changed_message(rel: str, recorded: str, found: str) -> str:
    return (
        f"label_ledger: {rel} changed (recorded {recorded}, found {found}) -- a label is "
        "never edited; if this is a deliberate oracle change, it needs an allow-list "
        "entry and the ledger updated in the same commit"
    )


def missing_message(rel: str) -> str:
    return (
        f"label_ledger: {rel} is recorded but not present -- a label or a gate was "
        "removed, which is a change, not a cleanup"
    )


def unrecorded_message(rel: str) -> str:
    return (
        f"label_ledger: {rel} is a new label and is not recorded -- run "
        "tools/update_label_ledger.py in this commit"
    )


def check(
    ledger: Mapping[str, Mapping[str, str]] | None = None,
    *,
    root: Path | str = _ROOT,
    covered: Mapping[str, Path] | None = None,
) -> list[str]:
    """Every way the ledger disagrees with the tree; ``[]`` means the guard holds."""
    if ledger is None:
        ledger = load_ledger()
    recorded = dict(ledger.get("files") or {})
    files = dict(covered) if covered is not None else covered_files(root)
    problems: list[str] = []
    for rel, path in sorted(files.items()):
        found = sha256_hex(path.read_bytes())
        if rel not in recorded:
            problems.append(unrecorded_message(rel))
        elif recorded[rel] != found:
            problems.append(changed_message(rel, recorded[rel], found))
    for rel in sorted(recorded):
        if rel not in files:
            problems.append(missing_message(rel))
    return problems


def record(
    ledger: Mapping[str, Mapping[str, str]],
    *,
    root: Path | str = _ROOT,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Append every covered file's fingerprint.

    Appends only: a recorded file whose bytes moved (or that is gone) is a
    :class:`ValueError`, never a silent rewrite.
    """
    recorded = dict(ledger.get("files") or {})
    found = fingerprints(root)
    for rel, digest in recorded.items():
        if rel not in found:
            raise ValueError(missing_message(rel))
        if found[rel] != digest:
            raise ValueError(changed_message(rel, digest, found[rel]))
    updated = dict(recorded)
    lines: list[str] = []
    for rel in sorted(found):
        if rel in updated:
            lines.append(f"{rel}: unchanged ({updated[rel]})")
        else:
            updated[rel] = found[rel]
            lines.append(f"{rel}: appended {found[rel]}")
    return {"files": updated}, lines


def render(ledger: Mapping[str, Mapping[str, str]]) -> str:
    """The canonical file text: the header first, sorted keys, one trailing newline."""
    body = {"_comment": _HEADER, "files": dict(ledger.get("files") or {})}
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_ledger(ledger: Mapping[str, Mapping[str, str]], path: str | Path | None = None) -> Path:
    ledger_path = Path(path) if path is not None else LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(ledger))
    return ledger_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ledger", default=None, help="the ledger JSON (default: tests/ledger/label_ledger.json)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report every disagreement and exit non-zero, writing nothing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    ledger_path = Path(args.ledger) if args.ledger else LEDGER_PATH
    ledger = load_ledger(ledger_path)
    if args.check:
        problems = check(ledger)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    try:
        updated, lines = record(ledger)
    except ValueError as refused:
        print(refused, file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    on_disk = ledger_path.read_bytes() if ledger_path.is_file() else b""
    if on_disk == render(updated).encode("utf-8"):
        print(f"{ledger_path}: unchanged", file=sys.stderr)
        return 0
    write_ledger(updated, ledger_path)
    print(f"{ledger_path}: written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
