"""Google Images DOM helpers: locating cards, previews, and banners with Selenium."""

from __future__ import annotations

import contextlib
from typing import Any


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
    key = card.get_attribute("data-id") or card.get_attribute("data-ved") or ""
    return key or card.id
