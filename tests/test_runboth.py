"""Turn 1.0b: ``tools/runboth.py`` -- both interpreters, one action.

Exercises the runner end to end with a light command: it must find a second
interpreter, run the command under both, and print the pair (interpreter line, the
3.11 selection source, the output, its sha256 and a verdict) plus the summary and the
cross-interpreter verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import runboth  # noqa: E402


def test_runboth_runs_under_both_interpreters_and_reports_the_pair(capsys) -> None:
    second = runboth.find_python311()
    if second is None:  # a machine without a CPython 3.11: the runner's documented exit 2.
        assert runboth.main(["--", "-c", "print(1)"]) == 2
        assert "no CPython 3.11 found" in capsys.readouterr().err
        pytest.skip("no CPython 3.11 on this machine")
    _prefix, source, version = second
    assert version.startswith("3.11")
    assert source in ("pinned selector", "PATH fallback")

    code = runboth.main(["--", "-c", "import sys; print(sys.version_info[0])"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("sha256:") == 2
    assert out.count("verdict: ok") == 2
    assert f"CPython {version}" in out
    assert f"CPython {sys.version.split()[0]}" in out
    assert source in out
    assert "summary: 2 interpreter(s)" in out
    assert "cross-interpreter:" in out
