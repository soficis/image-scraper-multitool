"""Google Images pure parsing: block detection, URL extraction, resolution filters.

No Selenium here — every function is a pure function of its inputs, which
keeps bot-challenge detection and candidate filtering unit-testable.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit


def is_block_page(*, page_source: str, current_url: str) -> bool:
    if "/sorry/index" in current_url:
        return True
    lowered = page_source.lower()
    return "captcha-form" in lowered or "unusual traffic" in lowered


def resolution_allowed(
    *, width: int, height: int, min_resolution: tuple[int, int], max_resolution: tuple[int, int]
) -> bool:
    min_width, min_height = min_resolution
    max_width, max_height = max_resolution

    if min_width and width and width < min_width:
        return False
    if min_height and height and height < min_height:
        return False
    if max_width and width and width > max_width:
        return False
    if max_height and height and height > max_height:
        return False
    return True


def extract_candidate_name(source_url: str, index: int) -> str:
    if source_url.startswith("data:image"):
        return f"google_data_{index}.jpg"
    return Path(urlsplit(source_url).path).name or f"google_{index}.jpg"


def is_preview_source(url: str, thumb_src: str) -> bool:
    if not url:
        return False
    if url == thumb_src:
        return False
    if url.startswith("http"):
        return True
    if url.startswith("data:image"):
        return True
    return False


def extract_url_from_page_source(*, page_source: str, seen_sources: set[str]) -> str:
    pattern = r'\["(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp))(?:\?[^"]*)?"(?:,|\])'
    for match in re.findall(pattern, page_source, re.IGNORECASE):
        lowered = match.lower()
        if (
            "google.com" in lowered
            or "gstatic.com" in lowered
            or "googleusercontent.com" in lowered
        ):
            continue
        if match in seen_sources:
            continue
        return match
    return ""
