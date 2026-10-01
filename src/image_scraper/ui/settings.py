"""User settings persistence for Image Scraper Multitool."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_settings_path() -> Path:
    """Return the platform-specific settings file path."""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "ImageScraperMultitool" / "settings.json"
        return Path.home() / "AppData" / "Roaming" / "ImageScraperMultitool" / "settings.json"
    return Path.home() / ".config" / "image-scraper-multitool" / "settings.json"


def save_settings(data: dict[str, Any], path: Path | None = None) -> None:
    """Atomically save settings data to disk."""
    target = path or get_settings_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_file = target.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, target)
    except Exception as exc:
        logger.warning("Failed to save settings to %s: %s", target, exc)


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load settings data from disk, returning an empty dict on error."""
    target = path or get_settings_path()
    if not target.exists():
        return {}
    try:
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning("Corrupt settings in %s: not a JSON object", target)
            return {}
    except Exception as exc:
        logger.warning("Could not read settings from %s: %s", target, exc)
        return {}
