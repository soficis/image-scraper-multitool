"""Pixabay image scraper adapter (free API key, REST+JSON, no browser)."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urlsplit

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions

from .downloader import DownloadOptions, download_candidates
from .stock_api import fetch_paginated_urls, resolve_api_key

SEARCH_URL = "https://pixabay.com/api/"
PER_PAGE = 80
SIGNUP_URL = "https://pixabay.com/api/docs/"
ENV_VAR = "PIXABAY_API_KEY"


def _extract_url(hit: Any) -> str:
    if not isinstance(hit, dict):
        return ""
    image_url = hit.get("largeImageURL")
    return image_url if isinstance(image_url, str) else ""


def _collect_candidates(
    *, query: str, limit: int, timeout: float, api_key: str
) -> list[DownloadCandidate]:
    urls = fetch_paginated_urls(
        operation="pixabay_collect",
        query=query,
        search_url=SEARCH_URL,
        base_params={
            "key": api_key,
            "q": query,
            "image_type": "photo",
            "per_page": str(PER_PAGE),
        },
        extra_headers=None,
        limit=limit,
        timeout=timeout,
        items_key="hits",
        extract_url=_extract_url,
    )
    candidates: list[DownloadCandidate] = []
    for position, image_url in enumerate(urls, start=1):
        name = Path(urlsplit(image_url).path).name
        candidates.append(
            DownloadCandidate(
                url=image_url,
                name=name or f"pixabay_{position}.jpg",
                referrer="https://pixabay.com/",
            )
        )
    return candidates


def scrape_pixabay(
    *,
    query: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    timeout: float,
    api_key: str | None = None,
    stop_event: Event | None = None,
) -> ScrapeResult:
    resolved_key = resolve_api_key(
        engine="pixabay", explicit_key=api_key, env_var=ENV_VAR, signup_url=SIGNUP_URL
    )
    candidates = _collect_candidates(
        query=query, limit=limit, timeout=timeout, api_key=resolved_key
    )
    batch = download_candidates(
        candidates,
        DownloadOptions(
            destination=destination,
            filename_prefix="pixabay",
            keep_filenames=keep_filenames,
            timeout=timeout,
            transform=transform,
        ),
        stop_event=stop_event,
    )
    return ScrapeResult(
        engine="pixabay",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
