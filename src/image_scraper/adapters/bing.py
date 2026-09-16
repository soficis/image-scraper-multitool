"""Bing image scraper adapter."""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Sequence
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .downloader import DownloadOptions, download_candidates

SEARCH_URL = "https://www.bing.com/images/async"


def _parse_candidates_from_soup(
    soup: BeautifulSoup, *, seen_urls: set[str]
) -> list[DownloadCandidate]:
    candidates: list[DownloadCandidate] = []
    for anchor in soup.select("a.iusc"):
        metadata_raw = anchor.get("m")
        if not isinstance(metadata_raw, str) or not metadata_raw:
            continue

        try:
            metadata = json.loads(metadata_raw)
        except (TypeError, ValueError):
            continue

        image_url = metadata.get("murl")
        if not image_url:
            continue

        if image_url in seen_urls:
            continue

        fallback_url = metadata.get("turl") or ""
        mad_raw = anchor.get("mad")
        if isinstance(mad_raw, str) and mad_raw:
            with contextlib.suppress(TypeError, ValueError):
                mad_data = json.loads(mad_raw)
                fallback_url = fallback_url or mad_data.get("turl") or ""

        name = Path(urlsplit(image_url).path).name
        candidates.append(
            DownloadCandidate(
                url=image_url,
                name=name,
                referrer="https://www.bing.com/",
                fallback_url=fallback_url if fallback_url.startswith("http") else "",
            )
        )
        seen_urls.add(image_url)

    return candidates


def _collect_candidates(
    *,
    query: str,
    limit: int,
    timeout: float,
    variants: Sequence[str] | None = None,
) -> list[DownloadCandidate]:
    session = requests.Session()
    session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    session.headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    session.headers.setdefault("Referer", "https://www.bing.com/")

    queries = list(variants) if variants else [query]

    candidates: list[DownloadCandidate] = []
    seen_urls: set[str] = set()

    for position, variant in enumerate(queries):
        if len(candidates) >= limit:
            break
        if position > 0:
            time.sleep(0.5)

        params = {
            "q": variant,
            "async": "1",
            "first": "1",
            "count": "35",
        }

        try:
            response = session.get(SEARCH_URL, params=params, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as error:
            if candidates:
                break
            raise EngineError(
                "bing_collect",
                "failed to fetch Bing image results",
                context={"query": variant, "error": str(error)},
            ) from error

        soup = BeautifulSoup(response.text, "html.parser")
        for candidate in _parse_candidates_from_soup(soup, seen_urls=seen_urls):
            candidates.append(candidate)
            if len(candidates) >= limit:
                break

    return candidates[:limit]


def scrape_bing(
    *,
    query: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    timeout: float,
    stop_event: Event | None = None,
    variants: Sequence[str] | None = None,
) -> ScrapeResult:
    candidates = _collect_candidates(query=query, limit=limit, timeout=timeout, variants=variants)
    batch = download_candidates(
        candidates,
        DownloadOptions(
            destination=destination,
            filename_prefix="bing",
            keep_filenames=keep_filenames,
            timeout=timeout,
            transform=transform,
        ),
        stop_event=stop_event,
    )
    return ScrapeResult(
        engine="bing",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
