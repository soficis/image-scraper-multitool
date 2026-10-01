"""Openverse image scraper adapter (free, no key, REST+JSON, no browser).

Anonymous tier: ~1 request/second, page_size capped at 20 (larger values
are rejected), pagination depth capped at 240 results (deeper pages return
401), openly-licensed images only. Most Creative Commons licences require
attribution, so every saved file gets a row in ATTRIBUTION.csv.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions

from .downloader import DownloadOptions, download_candidates
from .stock_api import fetch_paginated_urls, urls_to_candidates

SEARCH_URL = "https://api.openverse.org/v1/images/"
PER_PAGE = 20
ANONYMOUS_MAX_RESULTS = 240
MAX_PAGES = ANONYMOUS_MAX_RESULTS // PER_PAGE
MIN_INTERVAL_SECONDS = 1.0

ATTRIBUTION_FILENAME = "ATTRIBUTION.csv"
ATTRIBUTION_FIELDS = (
    "file",
    "title",
    "creator",
    "license",
    "license_version",
    "license_url",
    "source_page",
    "attribution",
)


def _extract_url(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    url = result.get("url")
    if isinstance(url, str) and url:
        return url
    thumbnail = result.get("thumbnail")
    return thumbnail if isinstance(thumbnail, str) else ""


def _attribution_row(result: dict[str, Any]) -> dict[str, str]:
    def text(key: str) -> str:
        value = result.get(key)
        if not isinstance(value, str):
            return ""
        # Titles and creators are untrusted: neutralise spreadsheet formulas.
        return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value

    return {
        "title": text("title"),
        "creator": text("creator"),
        "license": text("license"),
        "license_version": text("license_version"),
        "license_url": text("license_url"),
        "source_page": text("foreign_landing_url"),
        "attribution": text("attribution"),
    }


def _collect_candidates(
    *,
    query: str,
    limit: int,
    timeout: float,
    metadata: dict[str, dict[str, str]] | None = None,
) -> list[DownloadCandidate]:
    def extract(result: Any) -> str:
        url = _extract_url(result)
        if url and metadata is not None and isinstance(result, dict):
            metadata.setdefault(url, _attribution_row(result))
        return url

    urls = fetch_paginated_urls(
        operation="openverse_collect",
        query=query,
        search_url=SEARCH_URL,
        base_params={"q": query, "page_size": str(PER_PAGE)},
        extra_headers=None,
        limit=min(limit, ANONYMOUS_MAX_RESULTS),
        timeout=timeout,
        items_key="results",
        extract_url=extract,
        min_interval=MIN_INTERVAL_SECONDS,
        max_pages=MAX_PAGES,
        per_page=PER_PAGE,
    )
    return urls_to_candidates(urls, fallback_prefix="openverse", referrer="https://openverse.org/")


def _attribution_writer(
    destination: Path, metadata: dict[str, dict[str, str]]
) -> Callable[[DownloadCandidate, Path], None]:
    path = destination / ATTRIBUTION_FILENAME

    def write(candidate: DownloadCandidate, saved_path: Path) -> None:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ATTRIBUTION_FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow({"file": saved_path.name, **metadata.get(candidate.url, {})})

    return write


def scrape_openverse(
    *,
    query: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    timeout: float,
    stop_event: Event | None = None,
    on_saved: Callable[[DownloadCandidate, Path], None] | None = None,
) -> ScrapeResult:
    metadata: dict[str, dict[str, str]] = {}
    candidates = _collect_candidates(query=query, limit=limit, timeout=timeout, metadata=metadata)
    attrib_writer = _attribution_writer(destination, metadata)

    def combined_on_saved(candidate: DownloadCandidate, path: Path) -> None:
        attrib_writer(candidate, path)
        if on_saved is not None:
            on_saved(candidate, path)

    batch = download_candidates(
        candidates,
        DownloadOptions(
            destination=destination,
            filename_prefix="openverse",
            keep_filenames=keep_filenames,
            timeout=timeout,
            transform=transform,
        ),
        stop_event=stop_event,
        on_saved=combined_on_saved,
    )
    errors = list(batch.errors)
    if limit > ANONYMOUS_MAX_RESULTS:
        errors.append(
            f"openverse anonymous access is capped at {ANONYMOUS_MAX_RESULTS} results; "
            f"requested {limit}"
        )
    return ScrapeResult(
        engine="openverse",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=errors,
        destination=destination,
    )
