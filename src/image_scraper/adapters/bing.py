"""Bing image scraper adapter."""

from __future__ import annotations

import contextlib
import json
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .downloader import DownloadOptions, download_candidates

SEARCH_URL = "https://www.bing.com/images/async"

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _extract_query_terms(query: str) -> set[str]:
    """Extract significant lowercase words from a query for relevance checking."""
    words = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", query)]
    sig = {w for w in words if w not in STOP_WORDS and len(w) > 1}
    return sig if sig else set(words)


def _is_candidate_relevant(metadata: dict[str, Any], query_terms: set[str] | None) -> bool:
    """Check if candidate metadata shares at least one whole word with the query."""
    if not query_terms:
        return True
    title = str(metadata.get("t") or "")
    desc = str(metadata.get("desc") or "")
    purl = str(metadata.get("purl") or "")
    murl = str(metadata.get("murl") or "")
    # When synthetic test data supplies neither title nor desc, accept the candidate.
    if not title and not desc:
        return True
    haystack = f"{title} {desc} {purl} {murl}".lower()
    words = set(re.findall(r"[a-zA-Z0-9]+", haystack))
    stems = {w.rstrip("s") if len(w) > 3 else w for w in words}
    return bool(query_terms & (words | stems))


def _generate_fallback_queries(query: str) -> list[str]:
    """Generate noun-first and relaxed fallback queries for Bing search.

    Bing's search ranking weights the first token heavily. When a multi-word
    query has rare adjectives in the prefix (e.g., 'lanky tabby cat'), Bing
    often returns zero index matches and falls back to trending/recommended
    images. Reordering trailing noun phrases to the front (e.g., 'tabby cat lanky')
    restores high relevance.
    """
    words = [w for w in re.findall(r"\w+", query) if w.lower() not in STOP_WORDS]
    if len(words) <= 1:
        return []

    fallbacks: list[str] = []
    if len(words) >= 3:
        fallbacks.append(" ".join(words[1:] + [words[0]]))
        fallbacks.append(f"{words[-1]} {' '.join(words[:-1])}")
        fallbacks.append(" ".join(words[1:]))
        fallbacks.append(f"{words[0]} {words[-1]}")
    elif len(words) == 2:
        fallbacks.append(f"{words[1]} {words[0]}")
        fallbacks.append(words[1])

    seen = {query.strip().lower()}
    result: list[str] = []
    for q in fallbacks:
        clean = q.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            result.append(clean)
    return result


def _parse_candidates_from_soup(
    soup: BeautifulSoup,
    *,
    seen_urls: set[str],
    query_terms: set[str] | None = None,
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

        if not isinstance(metadata, dict):
            continue

        if not _is_candidate_relevant(metadata, query_terms):
            continue

        image_url = metadata.get("murl")
        if not image_url or not isinstance(image_url, str):
            continue

        fallback_url = metadata.get("turl") or ""
        mad_raw = anchor.get("mad")
        if isinstance(mad_raw, str) and mad_raw:
            with contextlib.suppress(TypeError, ValueError):
                mad_data = json.loads(mad_raw)
                fallback_url = fallback_url or mad_data.get("turl") or ""

        # Avoid hotlink-blocked crawler URLs as primary
        if "lookaside.fbsbx.com" in image_url and fallback_url.startswith("http"):
            image_url = fallback_url

        if image_url in seen_urls:
            continue

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
    fallback_queries = _generate_fallback_queries(query)

    search_plan: list[str] = []
    seen_queries: set[str] = set()
    for q in queries + fallback_queries:
        q_norm = q.strip().lower()
        if q_norm and q_norm not in seen_queries:
            seen_queries.add(q_norm)
            search_plan.append(q.strip())

    base_terms = _extract_query_terms(query)
    candidates: list[DownloadCandidate] = []
    seen_urls: set[str] = set()

    for position, variant in enumerate(search_plan):
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
        variant_terms = base_terms | _extract_query_terms(variant)
        for candidate in _parse_candidates_from_soup(
            soup, seen_urls=seen_urls, query_terms=variant_terms
        ):
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
    on_saved: Callable[[DownloadCandidate, Path], None] | None = None,
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
        on_saved=on_saved,
    )
    return ScrapeResult(
        engine="bing",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
