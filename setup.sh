#!/usr/bin/env bash
set -e

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================"
echo "      Image Scraper Multitool - Automated Setup"
echo "======================================================"
echo ""

# 1. Detect Python 3
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Python 3.8 or higher was not found on your system."
    echo "Please install Python 3.8+ using your package manager (e.g., sudo apt install python3 python3-venv python3-pip) or from https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION="$("$PYTHON_BIN" --version 2>&1)"
echo "[+] Found $PY_VERSION at $(command -v "$PYTHON_BIN")"

# 2. Check/create virtual environment (.venv)
if [ -d ".venv" ]; then
    if ! ".venv/bin/python" -c "import sys" >/dev/null 2>&1; then
        echo "[!] Existing virtual environment is broken or points to missing Python. Recreating..."
        rm -rf .venv
    else
        echo "[+] Existing healthy virtual environment found (.venv)."
    fi
fi

if [ ! -f ".venv/bin/python" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    if ! "$PYTHON_BIN" -m venv .venv 2>/dev/null; then
        echo "[ERROR] Failed to create virtual environment."
        echo "On Debian/Ubuntu systems, you may need to install python3-venv:"
        echo "    sudo apt install python3-venv"
        exit 1
    fi
    echo "[+] Virtual environment created successfully."
fi

# 3. Upgrade pip and install dependencies
echo "[*] Upgrading pip..."
".venv/bin/python" -m pip install --upgrade pip --quiet

echo "[*] Installing dependencies from requirements.txt..."
if ! ".venv/bin/python" -m pip install -r requirements.txt; then
    echo "[ERROR] Failed to install dependencies from requirements.txt."
    exit 1
fi
echo "[+] Dependencies installed successfully."

# 4. Optional developer tools
echo ""
read -r -p "Would you like to install developer/test tools (pytest, ruff, mypy)? [y/N]: " INSTALL_DEV
if [[ "$INSTALL_DEV" =~ ^[Yy]$ ]]; then
    echo "[*] Installing dev dependencies from requirements-dev.txt..."
    if ".venv/bin/python" -m pip install -r requirements-dev.txt; then
        echo "[+] Developer dependencies installed."
    else
        echo "[!] Warning: Dev dependencies could not be fully installed."
    fi
fi

# 5. Set executable permissions
chmod +x run.sh setup.sh 2>/dev/null || true

echo ""
echo "======================================================"
echo "                 Setup Completed!"
echo "======================================================"
echo "You can run the application anytime using: ./run.sh"
echo ""

# 6. Launch prompt
read -r -p "Would you like to launch the GUI now? [Y/n]: " LAUNCH_NOW
if [[ ! "$LAUNCH_NOW" =~ ^[Nn]$ ]]; then
    echo "[*] Launching Image Scraper Multitool..."
    exec ".venv/bin/python" image_scraper_gui.py "$@"
fi
