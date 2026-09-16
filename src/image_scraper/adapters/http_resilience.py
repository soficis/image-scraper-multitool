"""HTTP resilience primitives shared by the download pipeline.

Retry policy, per-host throttling, and size/timeout budgets live here so the
download adapter stays focused on fetching and storing bytes.
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterator
from urllib.parse import urlsplit

import requests

from image_scraper.errors import DownloadError

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_ATTEMPTS = 3
HOST_MIN_INTERVAL_SECONDS = 0.2
MAX_BACKOFF_SECONDS = 10.0

# HTTP statuses worth retrying: rate limits, gateway/proxy failures, overload.
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class HostThrottler:
    """Enforce a minimum interval between requests to the same host."""

    def __init__(self, min_interval: float = HOST_MIN_INTERVAL_SECONDS) -> None:
        self._min_interval = min_interval
        self._last_request: dict[str, float] = {}

    def wait(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        if not host:
            return
        now = time.monotonic()
        wait_for = self._min_interval - (now - self._last_request.get(host, 0.0))
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_request[host] = time.monotonic()


def retry_delay(*, attempt: int, response: requests.Response | None) -> float:
    """Exponential backoff with jitter; honors Retry-After when present."""
    if response is not None:
        raw = response.headers.get("Retry-After", "").strip()
        if raw:
            try:
                return min(max(0.0, float(raw)), MAX_BACKOFF_SECONDS) + random.uniform(0, 0.3)
            except ValueError:
                pass
    return min(0.5 * (2**attempt), MAX_BACKOFF_SECONDS) + random.uniform(0, 0.3)


def iter_capped_chunks(
    response: requests.Response,
    chunk_size: int = 8192,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> Iterator[bytes]:
    """Yield response chunks, failing closed if the payload exceeds `max_bytes`."""
    total = 0
    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:
            total += len(chunk)
            if total > max_bytes:
                raise DownloadError(
                    "download_too_large",
                    "image payload exceeds size limit",
                    context={"max_bytes": max_bytes},
                )
            yield chunk
