"""Turn 1.11 C: the README's examples are real, tested code -- not decoration that drifts.

Every fenced **python** block in ``README.md`` is preceded by a ``<!-- example:NAME -->`` marker, and
this module extracts each marked block and runs it in a temporary directory against a small multipart
message (``MESSAGE_BYTES`` / ``MESSAGE_PATH``, the two names the README documents). A block that stops
working fails here, named.

One more assertion, because a README rots from the middle: no python block escapes the markers, and
no fenced block is in a language the README has no reason to use.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

#: ``<!-- example:NAME -->`` immediately before a fenced block: the block is an example the test runs.
_MARKER = re.compile(r"<!--\s*example:(?P<name>[A-Za-z0-9_.-]+)\s*-->")

#: A fenced block, floor to closing fence: its info string and its body.
_FENCE = re.compile(r"^```(?P<lang>[A-Za-z0-9_+-]*)\n(?P<body>.*?)^```", re.DOTALL | re.MULTILINE)

#: The message every example runs against: a multipart/alternative whose plain part carries an
#: ``On ... wrote:`` quote (so the quote rows and a citable span are real, not empty).
MESSAGE = (
    b"From: Alice <alice@example.com>\r\n"
    b"To: Bob <bob@example.com>\r\n"
    b"Subject: Lunch?\r\n"
    b"Date: Mon, 06 Oct 2026 09:00:00 +0000\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/alternative; boundary="B"\r\n'
    b"\r\n"
    b"--B\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Hi Bob,\r\n\r\nAre we still on for lunch?\r\n\r\n"
    b"On Mon, 05 Oct 2026, Bob wrote:\r\n> Sure!\r\n"
    b"--B\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"<html><body><p>Hi Bob,</p><p>Are we still on for lunch?</p>"
    b"<blockquote>Sure!</blockquote></body></html>\r\n"
    b"--B--\r\n"
)


def _fences(text: str) -> list[tuple[str, str]]:
    return [(match.group("lang"), match.group("body")) for match in _FENCE.finditer(text)]


def _examples(text: str) -> list[tuple[str, str]]:
    """``[(name, code)]`` for each marker-delimited python block, in document order."""
    examples: list[tuple[str, str]] = []
    for match in _MARKER.finditer(text):
        rest = text[match.end():]
        fence = re.match(r"\s*```python\n(?P<body>.*?)^```", rest, re.DOTALL | re.MULTILINE)
        assert fence is not None, (
            f"the marker {match.group('name')!r} is not followed by a ```python block"
        )
        examples.append((match.group("name"), fence.group("body")))
    return examples


def test_every_python_block_in_the_readme_is_a_marked_example() -> None:
    """No example escapes the runners: every python block is marked, and every block is a known form."""
    text = README.read_text(encoding="utf-8")
    marked = [code for _name, code in _examples(text)]
    python_blocks = [body for lang, body in _fences(text) if lang in {"python", "py"}]
    assert python_blocks, "the README carries no python example"
    unmarked = [body for body in python_blocks if body not in marked]
    assert not unmarked, f"a python block is not a marked example: {unmarked}"
    languages = {lang for lang, _body in _fences(text)} - {"python", "py", "sh"}
    assert not languages, f"the README has a fenced block in an unexpected language: {languages}"


def test_every_readme_example_runs(tmp_path: Path) -> None:
    """Each marked block runs to completion, in its own directory, against the message."""
    examples = _examples(README.read_text(encoding="utf-8"))
    assert len(examples) >= 4, f"only {len(examples)} marked example(s)"
    names = [name for name, _code in examples]
    assert len(names) == len(set(names)), f"a duplicate example name: {names}"
    for name, code in examples:
        work = tmp_path / name
        work.mkdir()
        message = work / "message.eml"
        message.write_bytes(MESSAGE)
        namespace = {"__name__": "__main__", "MESSAGE_BYTES": MESSAGE, "MESSAGE_PATH": message}
        previous = os.getcwd()
        os.chdir(work)
        try:
            exec(compile(code, f"README example {name!r}", "exec"), namespace)  # noqa: S102
        except Exception as error:  # noqa: BLE001 - the failure has to name the block
            raise AssertionError(f"the README example {name!r} failed: {error!r}") from error
        finally:
            os.chdir(previous)
