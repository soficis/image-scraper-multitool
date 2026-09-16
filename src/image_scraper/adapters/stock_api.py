"""Shared helpers for key-authenticated JSON image APIs (Pexels, Pixabay).

Both engines are the same shape: REST+JSON search with page/per_page params,
a free API key, and a list of photo objects per page. Engine-specific bits
(auth scheme, item envelope, URL extraction) stay in the engine adapters.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

import requests

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.errors import ConfigurationError, EngineError

from .http_resilience import HOST_MIN_INTERVAL_SECONDS, HostThrottler


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
) -> list[str]:
    """Walk pages until `limit` unique URLs are collected or a page runs short."""
    session = requests.Session()
    session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    if extra_headers:
        session.headers.update(extra_headers)
    throttler = HostThrottler(min_interval=HOST_MIN_INTERVAL_SECONDS)

    urls: list[str] = []
    seen: set[str] = set()
    page = 1
    per_page = int(base_params.get("per_page", "80"))

    while len(urls) < limit:
        throttler.wait(search_url)
        try:
            response = session.get(
                search_url,
                params={**base_params, "page": str(page)},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise EngineError(
                operation,
                "failed to fetch image results",
                context={"query": query, "page": page, "error": str(error)},
            ) from error
        except ValueError as error:
            raise EngineError(
                operation,
                "API returned an unreadable response",
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

        if len(items) < per_page:
            break
        page += 1

    return urls[:limit]
