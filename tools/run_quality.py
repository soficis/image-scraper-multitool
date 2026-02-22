"""Run formatting, linting, type-checking, and tests with one command."""

from __future__ import annotations

import subprocess
import sys

CHECKS = [
    [sys.executable, "-m", "ruff", "format", "--check", "."],
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "mypy"],
    [sys.executable, "-m", "pytest", "-q"],
]


def main() -> int:
    for command in CHECKS:
        print(f"\n$ {' '.join(command)}", flush=True)
        completed = subprocess.run(command)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
