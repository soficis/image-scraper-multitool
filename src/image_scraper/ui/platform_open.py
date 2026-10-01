"""Open files or directories in the system file manager."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox


def open_in_file_manager(path: Path) -> bool:
    """Open a folder in the native file manager (Explorer, Finder, xdg-open)."""
    target = path.resolve()
    if target.is_file():
        target = target.parent
    if not target.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=True)
        else:
            subprocess.run(["xdg-open", str(target)], check=True)
        return True
    except Exception as exc:
        messagebox.showerror("Cannot open folder", f"Failed to open folder '{target}': {exc}")
        return False
