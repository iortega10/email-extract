"""Turn 0.1 gate: no module under emailextract/ modifies pathlib or any stdlib class."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPT = r"""
import datetime, email.message, json, os, pathlib, pkgutil
import emailextract

WATCH = (
    pathlib.Path, pathlib.PurePath, pathlib.PurePosixPath, pathlib.PureWindowsPath,
    os.PathLike, os.DirEntry,
    str, bytes, bytearray, int, float, complex, dict, list, set, tuple,
    datetime.datetime, datetime.date, datetime.time, datetime.timedelta,
    email.message.Message, email.message.EmailMessage,
)


def snapshot():
    return {f"{cls.__module__}.{cls.__qualname__}": sorted(dir(cls)) for cls in WATCH}


before = snapshot()
import importlib

for module in pkgutil.walk_packages(emailextract.__path__, "emailextract."):
    importlib.import_module(module.name)
after = snapshot()

changed = [name for name in before if before[name] != after[name]]
print(json.dumps({"changed": changed}))
"""


def test_no_module_modifies_pathlib_or_any_stdlib_class() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["changed"] == []
