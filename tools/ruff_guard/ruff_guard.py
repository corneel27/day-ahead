"""Portable console launcher for the repository's version-checked Ruff."""

import runpy
import sys
from pathlib import Path


def main():
    # The dedicated environment lives directly under the checkout. Loading the
    # checkout's implementation also picks up guard improvements after a pull.
    script = Path(sys.prefix).resolve().parent / "scripts/develop.py"
    return runpy.run_path(str(script))["ruff_entry"](sys.argv[1:])
