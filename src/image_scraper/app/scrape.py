"""Application use-case: scrape images from selected engines."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from image_scraper.adapters.bing import scrape_bing
from image_scraper.adapters.custom_page import scrape_custom_page
from image_scraper.adapters.google import scrape_google
from image_scraper.domain.models import ScrapeOptions, ScrapeResult
from image_scraper.domain.naming import slugify


def _destination_for_engine(base_dir: Path, engine: str, query: str) -> Path:
    slug = slugify(query)
    folder = "custom_url" if engine == "custom" else engine
    return base_dir / folder / slug


def scrape_images(options: ScrapeOptions, *, stop_event: Event | None = None) -> list[ScrapeResult]:
    options.validate()

    base_dir = options.output_dir.expanduser().resolve()
    results: list[ScrapeResult] = []

    for engine in options.engines:
        if stop_event and stop_event.is_set():
            break

        destination = _destination_for_engine(base_dir, engine, options.query)

        if engine == "bing":
            result = scrape_bing(
                query=options.query,
                limit=options.limit,
                destination=destination,
                keep_filenames=options.keep_filenames,
                transform=options.transform,
                timeout=options.bing_timeout,
                stop_event=stop_event,
            )
        elif engine == "google":
            result = scrape_google(
                query=options.query,
                limit=options.limit,
                destination=destination,
                keep_filenames=options.keep_filenames,
                transform=options.transform,
                chromedriver_path=options.google.chromedriver_path,
                headless=options.google.headless,
                min_resolution=options.google.min_resolution,
                max_resolution=options.google.max_resolution,
                max_missed=options.google.max_missed,
                stop_event=stop_event,
            )
        elif engine == "custom":
            result = scrape_custom_page(
                url=options.query,
                limit=options.limit,
                destination=destination,
                keep_filenames=options.keep_filenames,
                transform=options.transform,
                headless=options.google.headless,
                recursion_depth=options.custom_page.recursion_depth,
                chromedriver_path=options.google.chromedriver_path,
                stop_event=stop_event,
            )
        else:
            raise ValueError(f"Unsupported engine: {engine}")

        results.append(result)

    return results
