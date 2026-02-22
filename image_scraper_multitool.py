"""Compatibility entrypoint for CLI usage from repo root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def main() -> int:
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from image_scraper.cli.main import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
