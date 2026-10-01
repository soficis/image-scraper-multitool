#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".venv/bin/python" ] || ! ".venv/bin/python" -c "import sys" >/dev/null 2>&1; then
    echo "[ERROR] Virtual environment not found or broken."
    echo "Please run ./setup.sh first to set up or repair dependencies."
    exit 1
fi

exec ".venv/bin/python" image_scraper_gui.py "$@"
