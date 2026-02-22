"""Custom URL page image scraper adapter."""

from __future__ import annotations

import contextlib
import time
from collections import deque
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urljoin, urlsplit

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .chromedriver import create_chrome_driver, resolve_chromedriver_path
from .downloader import DownloadOptions, download_candidates

IGNORE_LINK_KEYWORDS = {
    "login",
    "signup",
    "signin",
    "register",
    "help",
    "about",
    "policy",
}


def _normalized_url(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def _extract_image_url(image_element: Any) -> str:
    src = image_element.get_attribute("src") or ""
    if src:
        return src

    data_src = (
        image_element.get_attribute("data-src")
        or image_element.get_attribute("data-original")
        or ""
    )
    if data_src:
        return data_src

    srcset = image_element.get_attribute("srcset") or ""
    if srcset:
        candidates = [entry.strip().split(" ")[0] for entry in srcset.split(",") if entry.strip()]
        if candidates:
            return candidates[-1]

    return ""


def _collect_candidates(
    *,
    driver: Any,
    start_url: str,
    recursion_depth: int,
    stop_event: Event | None,
) -> list[DownloadCandidate]:
    from selenium.webdriver.common.by import By

    normalized_start = _normalized_url(start_url)
    base_domain = urlsplit(normalized_start).netloc

    queue: deque[tuple[str, int]] = deque([(normalized_start, 0)])
    visited: set[str] = set()
    image_records: dict[str, DownloadCandidate] = {}

    while queue:
        if stop_event and stop_event.is_set():
            break

        current_url, depth = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        driver.get(current_url)

        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(2):
            if stop_event and stop_event.is_set():
                break
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            next_height = driver.execute_script("return document.body.scrollHeight")
            if next_height == last_height:
                break
            last_height = next_height

        for image in driver.find_elements(By.TAG_NAME, "img"):
            source = _extract_image_url(image)
            if not source:
                continue

            absolute_source = urljoin(current_url, source)
            if not absolute_source.startswith("http") and not absolute_source.startswith(
                "data:image"
            ):
                continue

            name = Path(urlsplit(absolute_source).path).name
            image_records.setdefault(
                absolute_source,
                DownloadCandidate(url=absolute_source, name=name, referrer=current_url),
            )

        if depth >= recursion_depth:
            continue

        for link in driver.find_elements(By.TAG_NAME, "a"):
            href = link.get_attribute("href") or ""
            if not href:
                continue
            absolute_href = urljoin(current_url, href)
            parsed = urlsplit(absolute_href)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc != base_domain:
                continue

            lowered = absolute_href.lower()
            if any(keyword in lowered for keyword in IGNORE_LINK_KEYWORDS):
                continue

            if absolute_href not in visited:
                queue.append((absolute_href, depth + 1))

    return list(image_records.values())


def scrape_custom_page(
    *,
    url: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    headless: bool,
    recursion_depth: int,
    chromedriver_path: Path | None,
    stop_event: Event | None = None,
) -> ScrapeResult:
    resolved_driver_path = resolve_chromedriver_path(chromedriver_path)
    driver = create_chrome_driver(
        chromedriver_path=resolved_driver_path,
        headless=headless,
        page_load_timeout=30,
    )

    try:
        candidates = _collect_candidates(
            driver=driver,
            start_url=url,
            recursion_depth=recursion_depth,
            stop_event=stop_event,
        )
    except Exception as error:
        raise EngineError(
            "custom_collect",
            "failed collecting image candidates from custom page",
            context={"url": url, "error": str(error)},
        ) from error
    finally:
        with contextlib.suppress(Exception):
            driver.quit()

    limited_candidates = candidates[:limit] if limit > 0 else candidates
    batch = download_candidates(
        limited_candidates,
        DownloadOptions(
            destination=destination,
            filename_prefix="custom",
            keep_filenames=keep_filenames,
            timeout=15.0,
            transform=transform,
        ),
        stop_event=stop_event,
    )

    return ScrapeResult(
        engine="custom",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
