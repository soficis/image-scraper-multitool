"""Google Images candidate collection: click-loop harvesting over live cards."""

from __future__ import annotations

import contextlib
import time
from threading import Event
from typing import Any
from urllib.parse import quote_plus

from image_scraper.domain.models import DownloadCandidate
from image_scraper.errors import EngineError

from .google_dom import (
    card_key,
    dismiss_cookie_banner,
    find_cards,
    find_preview_images,
    harvest_triples,
)
from .google_errors import error_summary, selenium_exceptions
from .google_parsing import (
    extract_candidate_name,
    extract_url_from_page_source,
    is_block_page,
    is_preview_source,
    resolution_allowed,
)

_EMPTY_CARDS_SLEEP = 0.3
_PREVIEW_SLEEP = 0.2
_SCROLL_STEP = 600
_SCROLL_SETTLE = 0.3
_SHOW_MORE_SETTLE = 0.3


def collect_candidates(
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
    stale_skips = 0
    stale_errors, fatal_errors = selenium_exceptions()

    while len(candidates) < limit and misses < max_missed:
        if stop_event and stop_event.is_set():
            break

        cards = find_cards(driver)
        if not cards:
            harvest_triples(
                driver=driver,
                candidates=candidates,
                seen_sources=seen_sources,
                limit=limit,
                min_resolution=min_resolution,
                max_resolution=max_resolution,
            )
            if len(candidates) >= limit:
                break
            if is_block_page(
                page_source=driver.page_source,
                current_url=driver.current_url or "",
                card_count=0,
            ):
                raise EngineError(
                    "google_blocked",
                    "Google served a bot challenge instead of image results",
                    context={
                        "query": query,
                        "checkpoint": "empty-cards",
                        "cards_collected": len(candidates),
                        "misses": misses,
                        "url": driver.current_url or "",
                        "next_action": "retry later, rerun with --google-show-browser, or use --engine bing",
                    },
                )
            misses += 1
            driver.execute_script(f"window.scrollBy(0, {_SCROLL_STEP});")
            time.sleep(_EMPTY_CARDS_SLEEP)
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
            except stale_errors:
                stale_skips += 1
                continue
            except Exception as error:
                if isinstance(error, fatal_errors):
                    raise EngineError(
                        "google_collect",
                        "browser session died during Google collection",
                        context={
                            "query": query,
                            "cards_collected": len(candidates),
                            "stale_skips": stale_skips,
                            "error": error_summary(error),
                        },
                    ) from error
                # Any other per-card WebDriver error (JS, click, timeout) only
                # loses this card; the session is still usable.
                continue

            time.sleep(_PREVIEW_SLEEP)
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
        time.sleep(_SCROLL_SETTLE)

        with contextlib.suppress(Exception):
            show_more = driver.find_element(By.CSS_SELECTOR, ".mye4qd")
            driver.execute_script("arguments[0].click();", show_more)
            time.sleep(_SHOW_MORE_SETTLE)

    if len(candidates) < limit and not (stop_event and stop_event.is_set()):
        harvest_triples(
            driver=driver,
            candidates=candidates,
            seen_sources=seen_sources,
            limit=limit,
            min_resolution=min_resolution,
            max_resolution=max_resolution,
        )

    return candidates
