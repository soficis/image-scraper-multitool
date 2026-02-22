"""Google Images scraper adapter."""

from __future__ import annotations

import contextlib
import re
import time
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import quote_plus, urlsplit

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .chromedriver import create_chrome_driver, resolve_chromedriver_path
from .downloader import DownloadOptions, download_candidates


def _resolution_allowed(
    *, width: int, height: int, min_resolution: tuple[int, int], max_resolution: tuple[int, int]
) -> bool:
    min_width, min_height = min_resolution
    max_width, max_height = max_resolution

    if min_width and width and width < min_width:
        return False
    if min_height and height and height < min_height:
        return False
    if max_width and width and width > max_width:
        return False
    if max_height and height and height > max_height:
        return False
    return True


def _dismiss_cookie_banner(driver: Any) -> None:
    from selenium.webdriver.common.by import By

    selectors = [
        "//button[.='I agree' or .='Accept all']",
        "//button[.//div[text()='I agree' or text()='Accept all']]",
        "//button[.='Reject all']",
    ]
    for selector in selectors:
        with contextlib.suppress(Exception):
            button = driver.find_element(By.XPATH, selector)
            button.click()
            return


def _find_cards(driver: Any) -> list[Any]:
    from selenium.webdriver.common.by import By

    selectors = [
        "div.isv-r.PNCib.MSM1fd.BUooTd",
        "div.isv-r.PNCib.MSM1fd",
        "div.isv-r",
        "div.q1MG4e",
        "div.F0uyec",
    ]
    for selector in selectors:
        cards = driver.find_elements(By.CSS_SELECTOR, selector)
        if cards:
            return cards
    return []


def _find_preview_images(driver: Any) -> list[Any]:
    from selenium.webdriver.common.by import By

    selectors = [
        "img.n3VNCb",
        "img.sFlh5c",
        "img.pT0Scc",
        "img.iPVvYb",
        "img.r48jcc",
        "img.gy84bd",
    ]

    for selector in selectors:
        images = driver.find_elements(By.CSS_SELECTOR, selector)
        if images:
            return images

    return driver.find_elements(By.TAG_NAME, "img")


def _extract_candidate_name(source_url: str, index: int) -> str:
    if source_url.startswith("data:image"):
        return f"google_data_{index}.jpg"
    return Path(urlsplit(source_url).path).name or f"google_{index}.jpg"


def _is_preview_source(url: str, thumb_src: str) -> bool:
    if not url:
        return False
    if url == thumb_src:
        return False
    if url.startswith("http"):
        return True
    if url.startswith("data:image"):
        return True
    return False


def _extract_url_from_page_source(*, page_source: str, seen_sources: set[str]) -> str:
    pattern = r'\["(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp))(?:\?[^"]*)?"(?:,|\])'
    for match in re.findall(pattern, page_source, re.IGNORECASE):
        lowered = match.lower()
        if (
            "google.com" in lowered
            or "gstatic.com" in lowered
            or "googleusercontent.com" in lowered
        ):
            continue
        if match in seen_sources:
            continue
        return match
    return ""


def _card_key(card: Any) -> str:
    key = card.get_attribute("data-id") or card.get_attribute("data-ved") or ""
    return key or card.id


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
    _dismiss_cookie_banner(driver)

    candidates: list[DownloadCandidate] = []
    seen_sources: set[str] = set()
    processed_cards: set[str] = set()
    misses = 0

    while len(candidates) < limit and misses < max_missed:
        if stop_event and stop_event.is_set():
            break

        cards = _find_cards(driver)
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
                card_key = _card_key(card)
                if card_key in processed_cards:
                    continue
                processed_cards.add(card_key)

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
            preview_images = _find_preview_images(driver)

            accepted_url = ""
            accepted_name = ""
            for image in preview_images:
                src = ""
                with contextlib.suppress(Exception):
                    src = image.get_attribute("src") or ""
                if not src:
                    continue
                if not _is_preview_source(src, thumb_src):
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

                if not _resolution_allowed(
                    width=width,
                    height=height,
                    min_resolution=min_resolution,
                    max_resolution=max_resolution,
                ):
                    continue

                accepted_url = src
                accepted_name = _extract_candidate_name(src, len(candidates) + 1)
                break

            if not accepted_url:
                with contextlib.suppress(Exception):
                    candidate_from_source = _extract_url_from_page_source(
                        page_source=driver.page_source,
                        seen_sources=seen_sources,
                    )
                    if candidate_from_source:
                        accepted_url = candidate_from_source
                        accepted_name = _extract_candidate_name(accepted_url, len(candidates) + 1)

            if not accepted_url and thumb_src and thumb_src not in seen_sources:
                accepted_url = thumb_src
                accepted_name = _extract_candidate_name(accepted_url, len(candidates) + 1)

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
