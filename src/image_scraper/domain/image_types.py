"""Image file typing helpers."""

from __future__ import annotations

import mimetypes
import os
from urllib.parse import urlsplit

from image_scraper.constants import ALLOWED_IMAGE_EXTENSIONS


def best_extension(
    *, original_name: str = "", fallback_url: str = "", content_type: str = ""
) -> str:
    """Resolve best image extension using filename, URL, and content type hints."""
    candidates: list[str] = []
    for source in (original_name, fallback_url):
        if not source:
            continue
        _, extension = os.path.splitext(urlsplit(source).path)
        if extension:
            candidates.append(extension.lower())

    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            candidates.append(guessed.lower())

    for extension in candidates:
        normalized = ".jpg" if extension == ".jpe" else extension
        if normalized in ALLOWED_IMAGE_EXTENSIONS:
            return normalized

    return ".jpg"
