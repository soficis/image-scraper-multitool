"""Naming and slug helpers."""

from __future__ import annotations

import re


def sanitize_filename(candidate: str) -> str:
    """Return a filesystem-safe filename fragment."""
    collapsed = re.sub(r"[^\w.\-]+", "_", candidate.strip())
    return collapsed[:255] or "image"


def slugify(value: str) -> str:
    """Return a URL/path-friendly slug from arbitrary text."""
    cleaned = re.sub(r"[^\w\s-]", "", value.lower())
    cleaned = re.sub(r"[\s-]+", "-", cleaned).strip("-")
    return cleaned or "query"
