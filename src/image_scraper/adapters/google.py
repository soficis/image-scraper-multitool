"""Google Images scraper adapter: Selenium click-loop collection orchestration."""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import quote_plus

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .chromedriver import create_chrome_driver, resolve_chromedriver_path
from .downloader import DownloadOptions, download_candidates
from .google_dom import card_key, dismiss_cookie_banner, find_cards, find_preview_images
from .google_parsing import (
    extract_candidate_name,
    extract_url_from_page_source,
    is_block_page,
    is_preview_source,
    resolution_allowed,
)


def _error_summary(error: Exception) -> str:
    first_line = str(error).splitlines()[0].strip()
    if not first_line:
        return error.__class__.__name__
    return f"{error.__class__.__name__}: {first_line}"


def _collect_candidates(
    *,
    driver: Any,
    query: str,
    limit: int,
    min_resolution: tuple[int, int],
    max_resolution: tuple[int, int],
    max_missed: int,
    stop_event: Event | None,
) -> list[DownloadCandidate]:
    from selenium.webdriver.common.by import By

    search_url = f"https://www.google.com/search?tbm=isch&hl=en&q={quote_plus(query)}"
    driver.get(search_url)
    dismiss_cookie_banner(driver)

    if is_block_page(page_source=driver.page_source, current_url=driver.current_url or ""):
        raise EngineError(
            "google_blocked",
            "Google served a bot challenge instead of image results",
            context={
                "query": query,
                "next_action": "retry later, rerun with --google-show-browser, or use --engine bing",
            },
        )

    candidates: list[DownloadCandidate] = []
    seen_sources: set[str] = set()
    processed_cards: set[str] = set()
    misses = 0

    while len(candidates) < limit and misses < max_missed:
        if stop_event and stop_event.is_set():
            break

        cards = find_cards(driver)
        if not cards:
            misses += 1
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(0.3)
            continue

        new_in_pass = 0

        for card in cards:
            if len(candidates) >= limit:
                break
            if stop_event and stop_event.is_set():
                break

            try:
                key = card_key(card)
                if key in processed_cards:
                    continue
                processed_cards.add(key)

                thumb_src = ""
                with contextlib.suppress(Exception):
                    thumb_src = card.find_element(By.TAG_NAME, "img").get_attribute("src") or ""

                click_target = card
                with contextlib.suppress(Exception):
                    anchor = card.find_element(By.XPATH, "./ancestor::a")
                    click_target = anchor

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                driver.execute_script("arguments[0].click();", click_target)
            except Exception:
                continue

            time.sleep(0.2)
            preview_images = find_preview_images(driver)

            accepted_url = ""
            accepted_name = ""
            for image in preview_images:
                src = ""
                with contextlib.suppress(Exception):
                    src = image.get_attribute("src") or ""
                if not src:
                    continue
                if not is_preview_source(src, thumb_src):
                    continue
                if src in seen_sources:
                    continue

                try:
                    width, height = driver.execute_script(
                        "return [arguments[0].naturalWidth || 0, arguments[0].naturalHeight || 0];",
                        image,
                    )
                    width = int(width)
                    height = int(height)
                except Exception:
                    width, height = 0, 0

                if not resolution_allowed(
                    width=width,
                    height=height,
                    min_resolution=min_resolution,
                    max_resolution=max_resolution,
                ):
                    continue

                accepted_url = src
                accepted_name = extract_candidate_name(src, len(candidates) + 1)
                break

            if not accepted_url:
                with contextlib.suppress(Exception):
                    candidate_from_source = extract_url_from_page_source(
                        page_source=driver.page_source,
                        seen_sources=seen_sources,
                    )
                    if candidate_from_source:
                        accepted_url = candidate_from_source
                        accepted_name = extract_candidate_name(accepted_url, len(candidates) + 1)

            if not accepted_url and thumb_src and thumb_src not in seen_sources:
                accepted_url = thumb_src
                accepted_name = extract_candidate_name(accepted_url, len(candidates) + 1)

            if accepted_url:
                seen_sources.add(accepted_url)
                candidates.append(
                    DownloadCandidate(
                        url=accepted_url,
                        name=accepted_name,
                        referrer="https://www.google.com/",
                    )
                )
                new_in_pass += 1

        if new_in_pass == 0:
            misses += 1
        else:
            misses = 0

        with contextlib.suppress(Exception):
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
        time.sleep(0.3)

        with contextlib.suppress(Exception):
            show_more = driver.find_element(By.CSS_SELECTOR, ".mye4qd")
            driver.execute_script("arguments[0].click();", show_more)
            time.sleep(0.3)

    return candidates


def scrape_google(
    *,
    query: str,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    transform: TransformOptions,
    chromedriver_path: Path | None,
    headless: bool,
    min_resolution: tuple[int, int],
    max_resolution: tuple[int, int],
    max_missed: int,
    stop_event: Event | None = None,
) -> ScrapeResult:
    resolved_driver_path = resolve_chromedriver_path(chromedriver_path)
    driver = create_chrome_driver(
        chromedriver_path=resolved_driver_path,
        headless=headless,
        page_load_timeout=30,
    )

    try:
        candidates: list[DownloadCandidate] | None = None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                candidates = _collect_candidates(
                    driver=driver,
                    query=query,
                    limit=limit,
                    min_resolution=min_resolution,
                    max_resolution=max_resolution,
                    max_missed=max_missed,
                    stop_event=stop_event,
                )
                break
            except Exception as error:
                last_error = error
                if attempt == 0 and "stale element reference" in str(error).lower():
                    time.sleep(0.25)
                    continue
                break

        if candidates is None:
            assert last_error is not None
            raise last_error
    except EngineError:
        raise
    except Exception as error:
        raise EngineError(
            "google_collect",
            "failed during Google image candidate collection",
            context={"query": query, "error": _error_summary(error)},
        ) from error
    finally:
        with contextlib.suppress(Exception):
            driver.quit()

    batch = download_candidates(
        candidates,
        DownloadOptions(
            destination=destination,
            filename_prefix="google",
            keep_filenames=keep_filenames,
            timeout=15.0,
            transform=transform,
        ),
        stop_event=stop_event,
    )

    return ScrapeResult(
        engine="google",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
