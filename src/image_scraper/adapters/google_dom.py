"""Google Images DOM helpers: locating cards, previews, and banners with Selenium."""

from __future__ import annotations

import contextlib
from typing import Any

from image_scraper.domain.models import DownloadCandidate

from .google_parsing import extract_candidate_name, extract_triple_candidates


def dismiss_cookie_banner(driver: Any) -> None:
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


def find_cards(driver: Any) -> list[Any]:
    from selenium.webdriver.common.by import By

    selectors = [
        "div.VifEQd",
        "div.RmwKgd.klScif",
        "div.offbPb",
        "div.q1MG4e",
    ]
    for selector in selectors:
        cards = driver.find_elements(By.CSS_SELECTOR, selector)
        if cards:
            return cards
    return []


def find_preview_images(driver: Any) -> list[Any]:
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


def card_key(card: Any) -> str:
    key = (
        card.get_attribute("data-docid")
        or card.get_attribute("data-ved")
        or card.get_attribute("data-id")
        or ""
    )
    return key or card.id


def harvest_triples(
    *,
    driver: Any,
    candidates: list[DownloadCandidate],
    seen_sources: set[str],
    limit: int,
    min_resolution: tuple[int, int] = (0, 0),
    max_resolution: tuple[int, int] = (0, 0),
) -> None:
    # Fail-safe: page_source raising means a dead session; return so the
    # empty-cards block recheck downstream surfaces the failure.
    try:
        page_source = driver.page_source
    except Exception:
        return
    for url in extract_triple_candidates(
        page_source=page_source,
        seen_sources=seen_sources,
        limit=limit - len(candidates),
        min_resolution=min_resolution,
        max_resolution=max_resolution,
    ):
        if len(candidates) >= limit:
            break
        seen_sources.add(url)
        candidates.append(
            DownloadCandidate(
                url=url,
                name=extract_candidate_name(url, len(candidates) + 1),
                referrer="https://www.google.com/",
            )
        )
