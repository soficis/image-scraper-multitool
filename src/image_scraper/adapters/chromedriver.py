"""ChromeDriver and Selenium bootstrap helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.errors import ConfigurationError, DependencyError, EngineError


def resolve_chromedriver_path(explicit_path: Path | None) -> Path | None:
    if explicit_path is None:
        return None

    resolved = explicit_path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ConfigurationError(
            "resolve_chromedriver",
            "chromedriver path does not exist",
            context={"path": str(resolved)},
        )
    return resolved


def create_chrome_driver(
    *, chromedriver_path: Path | None, headless: bool, page_load_timeout: float
) -> Any:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError as error:
        raise DependencyError(
            "selenium",
            "selenium is required for Google/custom scraping",
            context={"install": "pip install selenium"},
        ) from error

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--enable-unsafe-swiftshader")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

    # If chromedriver_path is None, Selenium Manager auto-resolves a compatible driver.
    service = Service(executable_path=str(chromedriver_path)) if chromedriver_path else Service()

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as error:
        error_message = str(error)
        if (
            chromedriver_path is not None
            and "This version of ChromeDriver only supports Chrome version" in error_message
        ):
            raise EngineError(
                "create_chrome_driver",
                "configured chromedriver is incompatible with installed Chrome",
                context={
                    "chromedriver_path": str(chromedriver_path),
                    "next_action": "clear the chromedriver path to use Selenium Manager auto-resolution",
                },
            ) from error

        raise EngineError(
            "create_chrome_driver",
            "failed to start Chrome WebDriver session",
            context={"error": error_message},
        ) from error

    driver.set_page_load_timeout(page_load_timeout)
    return driver
