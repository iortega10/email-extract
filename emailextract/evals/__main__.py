"""``python -m emailextract.evals``: the metrics table, and the exit code a caller checks."""

from __future__ import annotations

import sys

from .metrics import main

if __name__ == "__main__":
    sys.exit(main())
