"""Turn 1.0b: run one command under both pinned interpreters and report the pair.

Operating rule 2: "both interpreters, always, from the first turn". The two
interpreters are

1. **primary**: ``py -V:Astral/CPython3.11.15`` (the machine-specific selector the
   project pins);
2. **fallback**: when that selector is absent, the first Python 3.11 on ``PATH`` --
   resolved by asking each candidate for ``sys.version_info`` and taking the first
   that reports 3.11;
3. the **current** interpreter (the 3.14 side the project runs under).

It runs one command under each (default ``python -m pytest -q``), prints each
interpreter's line and the source of the 3.11 selection, the command's combined
stdout+stderr verbatim, the sha256 of that output and a one-line verdict, then a
summary and the cross-interpreter verdict (whether the two outputs are
byte-identical). A difference is printed and reported, never hidden; the fingerprints
that are *required* identical are asserted by their own tests, not here.

If no CPython 3.11 can be found it exits 2 and says so -- it never silently runs 3.14
twice and calls it "both". It writes no stamp file.

Exit code: 0 iff both interpreters' command exits 0; 1 if either exits non-zero; 2 if a
second interpreter could not be found.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent

#: The pinned selector, then the PATH candidates tried in order.
PINNED_SELECTOR = ("py", "-V:Astral/CPython3.11.15")
PATH_CANDIDATES = ("python3.11", "python3", "python", "py")

DEFAULT_COMMAND = ("-m", "pytest", "-q")

NO_SECOND_INTERPRETER = (
    "runboth: no CPython 3.11 found (tried py -V:Astral/CPython3.11.15 and PATH) -- "
    "recording-only run skipped"
)


def _probe(prefix: Sequence[str]) -> tuple[str, tuple[int, int, int]] | None:
    """``(version, (major, minor, micro))`` for a candidate interpreter, or ``None``."""
    try:
        result = subprocess.run(
            [*prefix, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return version, (int(parts[0]), int(parts[1]), int(parts[2]))


def find_python311() -> tuple[list[str], str, str] | None:
    """``(argv prefix, source, version)`` for a CPython 3.11, or ``None``."""
    probed = _probe(list(PINNED_SELECTOR))
    if probed is not None and probed[1][:2] == (3, 11):
        return list(PINNED_SELECTOR), "pinned selector", probed[0]
    for name in PATH_CANDIDATES:
        path = shutil.which(name)
        if path is None:
            continue
        probed = _probe([path])
        if probed is not None and probed[1][:2] == (3, 11):
            return [path], "PATH fallback", probed[0]
    return None


def _run(prefix: Sequence[str], command: Sequence[str]) -> tuple[int, str]:
    """Run ``command`` under ``prefix``; return ``(exit code, combined output)``."""
    try:
        result = subprocess.run(
            [*prefix, *command], cwd=ROOT, capture_output=True, text=True
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - env
        return 1, f"{type(error).__name__}: {error}\n"
    return result.returncode, result.stdout + result.stderr


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command",
        nargs="*",
        help="the command (interpreter arguments) to run under both interpreters; "
        "default: -m pytest -q",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = tuple(args.command) if args.command else DEFAULT_COMMAND

    second = find_python311()
    if second is None:
        print(NO_SECOND_INTERPRETER, file=sys.stderr)
        return 2
    prefix, source, version = second

    interpreters = (
        (f"CPython {version} ({' '.join(prefix)})", source, prefix),
        (f"CPython {sys.version.split()[0]} ({sys.executable})", "current interpreter", (sys.executable,)),
    )

    results: list[tuple[str, int, str, str]] = []
    for line, where, prefix_i in interpreters:
        code, output = _run(prefix_i, command)
        digest = sha256_hex(output.encode("utf-8"))
        results.append((line, code, output, digest))

    print(f"runboth: { ' '.join(command) } under {len(results)} interpreter(s)")
    for line, code, output, digest in results:
        print(f"--- {line} [{_source_of(line, interpreters)}]")
        print(output.rstrip("\n"))
        print(f"sha256: {digest}")
        print(f"verdict: {'ok' if code == 0 else f'exit {code}'}")

    identical = results[0][2] == results[1][2]
    verdicts = ", ".join("ok" if code == 0 else f"exit {code}" for _line, code, _o, _d in results)
    print(f"summary: {len(results)} interpreter(s): {verdicts}")
    print(f"cross-interpreter: outputs {'byte-identical' if identical else 'differ'}")

    if any(code != 0 for _line, code, _o, _d in results):
        return 1
    return 0


def _source_of(line: str, interpreters: Sequence[tuple[str, str, Sequence[str]]]) -> str:
    for candidate, source, _prefix in interpreters:
        if candidate == line:
            return source
    return "?"


if __name__ == "__main__":
    raise SystemExit(main())
