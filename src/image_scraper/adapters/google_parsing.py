"""Google Images pure parsing: block detection, URL extraction, resolution filters.

No Selenium here — every function is a pure function of its inputs, which
keeps bot-challenge detection and candidate filtering unit-testable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

_BLOCKED_PAGE_HOSTS = ("google.com", "gstatic.com", "googleusercontent.com")

_TRIPLE_PATTERN = re.compile(r'\["(https?://[^"\[\]]+?)",(\d+),(\d+)\]')
_OU_PATTERN = re.compile(r'"ou":"(https?://[^"]+)"')


def _is_denylisted(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in _BLOCKED_PAGE_HOSTS)


def _decode_json_string(raw: str) -> str:
    # Page-source URLs are JSON string bodies: `=` and `&` arrive as =
    # and &. Undecodable bodies are dropped rather than downloaded broken.
    try:
        decoded = json.loads(f'"{raw}"')
    except ValueError:
        return ""
    return decoded if isinstance(decoded, str) else ""


def is_block_page(*, page_source: str, current_url: str, card_count: int | None = None) -> bool:
    # URL stays the primary signal: a good results page embeds a sorry/index
    # JavaScript reference in its DOM, so page_source must never be scanned
    # for the sorry path (100% false-positive rate on good pages).
    if urlsplit(current_url).path.startswith("/sorry"):
        return True
    lowered = page_source.lower()
    challenged = "captcha-form" in lowered or "unusual traffic" in lowered
    if not challenged:
        return False
    if card_count is None:
        return True
    return card_count == 0


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


def extract_triple_candidates(
    *,
    page_source: str,
    seen_sources: set[str],
    limit: int,
    min_resolution: tuple[int, int] = (0, 0),
    max_resolution: tuple[int, int] = (0, 0),
) -> list[str]:
    """Harvest full-size URLs from Google's embedded `["url",height,width]` data.

    Triples carry real dimensions, so the resolution bounds apply to them;
    `"ou"` entries have none and pass the (dimension-less) check unfiltered.
    """
    if limit <= 0:
        return []
    found: list[str] = []
    seen = set(seen_sources)

    def accept(url: str) -> bool:
        if not url or _is_denylisted(url) or url in seen:
            return False
        seen.add(url)
        found.append(url)
        return len(found) >= limit

    for match in _TRIPLE_PATTERN.finditer(page_source):
        height, width = int(match.group(2)), int(match.group(3))
        if not resolution_allowed(
            width=width,
            height=height,
            min_resolution=min_resolution,
            max_resolution=max_resolution,
        ):
            continue
        if accept(_decode_json_string(match.group(1))):
            return found
    for raw in _OU_PATTERN.findall(page_source):
        if accept(_decode_json_string(raw)):
            break
    return found


def extract_url_from_page_source(*, page_source: str, seen_sources: set[str]) -> str:
    pattern = r'\["(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp))(?:\?[^"]*)?"(?:,|\])'
    for match in re.findall(pattern, page_source, re.IGNORECASE):
        if _is_denylisted(match):
            continue
        if match in seen_sources:
            continue
        return match
    return ""
