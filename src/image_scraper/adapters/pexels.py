"""Pexels image scraper adapter (free API key, REST+JSON, no browser)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions

from .downloader import DownloadOptions, download_candidates
from .stock_api import fetch_paginated_urls, resolve_api_key, urls_to_candidates

SEARCH_URL = "https://api.pexels.com/v1/search"
PER_PAGE = 80
SIGNUP_URL = "https://www.pexels.com/api/"
ENV_VAR = "PEXELS_API_KEY"


def _extract_url(photo: Any) -> str:
    if not isinstance(photo, dict):
        return ""
    sources = photo.get("src")
    if isinstance(sources, dict):
        original = sources.get("original")
        return original if isinstance(original, str) else ""
    return ""


def _collect_candidates(
    *, query: str, limit: int, timeout: float, api_key: str
) -> list[DownloadCandidate]:
    urls = fetch_paginated_urls(
        operation="pexels_collect",
        query=query,
        search_url=SEARCH_URL,
        base_params={"query": query, "per_page": str(PER_PAGE)},
        extra_headers={"Authorization": api_key},
        limit=limit,
        timeout=timeout,
        items_key="photos",
        extract_url=_extract_url,
    )
    return urls_to_candidates(urls, fallback_prefix="pexels", referrer="https://www.pexels.com/")


def scrape_pexels(
    *,
    query: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    timeout: float,
    api_key: str | None = None,
    stop_event: Event | None = None,
    on_saved: Callable[[DownloadCandidate, Path], None] | None = None,
) -> ScrapeResult:
    resolved_key = resolve_api_key(
        engine="pexels", explicit_key=api_key, env_var=ENV_VAR, signup_url=SIGNUP_URL
    )
    candidates = _collect_candidates(
        query=query, limit=limit, timeout=timeout, api_key=resolved_key
    )
    batch = download_candidates(
        candidates,
        DownloadOptions(
            destination=destination,
            filename_prefix="pexels",
            keep_filenames=keep_filenames,
            timeout=timeout,
            transform=transform,
        ),
        stop_event=stop_event,
        on_saved=on_saved,
    )
    return ScrapeResult(
        engine="pexels",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
