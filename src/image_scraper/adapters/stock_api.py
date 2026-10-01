"""Shared helpers for key-authenticated JSON image APIs (Pexels, Pixabay).

Both engines are the same shape: REST+JSON search with page/per_page params,
a free API key, and a list of photo objects per page. Engine-specific bits
(auth scheme, item envelope, URL extraction) stay in the engine adapters.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.domain.models import DownloadCandidate
from image_scraper.errors import ConfigurationError, EngineError

from .http_resilience import HOST_MIN_INTERVAL_SECONDS, HostThrottler

LOGGER = logging.getLogger(__name__)


def resolve_api_key(*, engine: str, explicit_key: str | None, env_var: str, signup_url: str) -> str:
    key = (explicit_key or os.environ.get(env_var) or "").strip()
    if not key:
        raise ConfigurationError(
            f"{engine}_auth",
            f"{engine.capitalize()} API key is required",
            context={
                "next_action": f"get a free key at {signup_url} and pass it explicitly or set {env_var}"
            },
        )
    return key


def fetch_paginated_urls(
    *,
    operation: str,
    query: str,
    search_url: str,
    base_params: Mapping[str, str],
    extra_headers: Mapping[str, str] | None,
    limit: int,
    timeout: float,
    items_key: str,
    extract_url: Callable[[Any], str],
    min_interval: float = HOST_MIN_INTERVAL_SECONDS,
    max_pages: int = 100,
    per_page: int | None = None,
) -> list[str]:
    """Walk pages until `limit` unique URLs are collected or a page runs short.

    `max_pages` bounds the walk so an endpoint that always returns full
    pages cannot spin forever; callers asking for huge limits raise it.
    `per_page` is the page size used for the short-page check; it defaults to
    the `per_page` request param for APIs that name it that way.

    A failure on the first page raises; a failure on a later page keeps the
    URLs already collected and logs a warning instead of discarding them.
    """
    session = requests.Session()
    session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    if extra_headers:
        session.headers.update(extra_headers)
    throttler = HostThrottler(min_interval=min_interval)

    urls: list[str] = []
    seen: set[str] = set()
    page = 1
    page_size = per_page if per_page is not None else int(base_params.get("per_page", "80"))

    while len(urls) < limit and page <= max_pages:
        throttler.wait(search_url)
        try:
            response = session.get(
                search_url,
                params={**base_params, "page": str(page)},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            message = (
                "API returned an unreadable response"
                if isinstance(error, ValueError)
                else "failed to fetch image results"
            )
            if urls:
                LOGGER.warning(
                    "%s: %s on page %d; keeping %d collected URLs (%s)",
                    operation,
                    message,
                    page,
                    len(urls),
                    error,
                )
                break
            raise EngineError(
                operation,
                message,
                context={"query": query, "page": page, "error": str(error)},
            ) from error

        items = payload.get(items_key) if isinstance(payload, dict) else None
        if not items:
            break

        for item in items:
            if len(urls) >= limit:
                break
            image_url = extract_url(item)
            if not image_url or image_url in seen:
                continue
            seen.add(image_url)
            urls.append(image_url)

        if len(items) < page_size:
            break
        page += 1

    return urls[:limit]


def urls_to_candidates(
    urls: Iterable[str], *, fallback_prefix: str, referrer: str
) -> list[DownloadCandidate]:
    """Map collected image URLs to download candidates with fallback names."""
    candidates: list[DownloadCandidate] = []
    for position, image_url in enumerate(urls, start=1):
        name = Path(urlsplit(image_url).path).name
        candidates.append(
            DownloadCandidate(
                url=image_url,
                name=name or f"{fallback_prefix}_{position}.jpg",
                referrer=referrer,
            )
        )
    return candidates
