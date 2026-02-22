"""Bing image scraper adapter."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .downloader import DownloadOptions, download_candidates

SEARCH_URL = "https://www.bing.com/images/search"


def _collect_candidates(*, query: str, limit: int, timeout: float) -> list[DownloadCandidate]:
    session = requests.Session()
    session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    session.headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    session.headers.setdefault("Referer", "https://www.bing.com/")

    params = {
        "q": query,
        "form": "HDRSC2",
        "first": "0",
        "tsc": "ImageBasicHover",
    }

    try:
        response = session.get(SEARCH_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as error:
        raise EngineError(
            "bing_collect",
            "failed to fetch Bing image results",
            context={"query": query, "error": str(error)},
        ) from error

    soup = BeautifulSoup(response.text, "html.parser")

    candidates: list[DownloadCandidate] = []
    seen_urls: set[str] = set()
    for anchor in soup.select("a.iusc"):
        metadata_raw = anchor.get("m")
        if not metadata_raw:
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
        if mad_raw:
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
        if len(candidates) >= limit:
            break

    return candidates


def scrape_bing(
    *,
    query: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    timeout: float,
    stop_event: Event | None = None,
) -> ScrapeResult:
    candidates = _collect_candidates(query=query, limit=limit, timeout=timeout)
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
