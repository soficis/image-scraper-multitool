"""Application use-case: scrape images from selected engines."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from image_scraper.adapters.bing import scrape_bing
from image_scraper.adapters.custom_page import scrape_custom_page
from image_scraper.adapters.google import scrape_google
from image_scraper.adapters.openverse import scrape_openverse
from image_scraper.adapters.pexels import scrape_pexels
from image_scraper.adapters.pixabay import scrape_pixabay
from image_scraper.domain.expansion import expand_query
from image_scraper.domain.models import DownloadCandidate, EngineName, ScrapeOptions, ScrapeResult
from image_scraper.domain.naming import slugify
from image_scraper.errors import ImageScraperError


def _destination_for_engine(base_dir: Path, engine: str, query: str) -> Path:
    slug = slugify(query)
    folder = "custom_url" if engine == "custom" else engine
    return base_dir / folder / slug


def _error_result(
    *, engine: EngineName, requested: int, destination: Path, message: str
) -> ScrapeResult:
    return ScrapeResult(
        engine=engine,
        requested=requested,
        saved=0,
        skipped=0,
        errors=[message],
        destination=destination,
    )


def scrape_images(
    options: ScrapeOptions,
    *,
    stop_event: Event | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> list[ScrapeResult]:
    options.validate()

    base_dir = options.output_dir.expanduser().resolve()
    results: list[ScrapeResult] = []

    for engine in options.engines:
        if stop_event and stop_event.is_set():
            break

        destination = _destination_for_engine(base_dir, engine, options.query)
        if progress is not None:
            progress(engine, 0, options.limit)

        saved_count = 0

        def make_on_saved(eng: str) -> Callable[[DownloadCandidate, Path], None]:
            def _on_saved(_cand: DownloadCandidate, _path: Path) -> None:
                nonlocal saved_count
                saved_count += 1
                if progress is not None:
                    progress(eng, saved_count, options.limit)

            return _on_saved

        eng_on_saved = make_on_saved(engine)

        try:
            if engine == "bing":
                result = scrape_bing(
                    query=options.query,
                    limit=options.limit,
                    destination=destination,
                    keep_filenames=options.keep_filenames,
                    transform=options.transform,
                    timeout=options.bing_timeout,
                    stop_event=stop_event,
                    variants=expand_query(options.query) if options.expand_queries else None,
                    on_saved=eng_on_saved,
                )
            elif engine == "google":

                def on_google_collecting() -> None:
                    if progress is not None:
                        progress("google", -1, options.limit)

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
                    on_saved=eng_on_saved,
                    on_collecting=on_google_collecting,
                )
            elif engine == "pexels":
                result = scrape_pexels(
                    query=options.query,
                    limit=options.limit,
                    destination=destination,
                    keep_filenames=options.keep_filenames,
                    transform=options.transform,
                    timeout=options.api_timeout,
                    api_key=options.pexels_api_key or None,
                    stop_event=stop_event,
                    on_saved=eng_on_saved,
                )
            elif engine == "pixabay":
                result = scrape_pixabay(
                    query=options.query,
                    limit=options.limit,
                    destination=destination,
                    keep_filenames=options.keep_filenames,
                    transform=options.transform,
                    timeout=options.api_timeout,
                    api_key=options.pixabay_api_key or None,
                    stop_event=stop_event,
                    on_saved=eng_on_saved,
                )
            elif engine == "openverse":
                result = scrape_openverse(
                    query=options.query,
                    limit=options.limit,
                    destination=destination,
                    keep_filenames=options.keep_filenames,
                    transform=options.transform,
                    timeout=options.api_timeout,
                    stop_event=stop_event,
                    on_saved=eng_on_saved,
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
                    on_saved=eng_on_saved,
                )
            else:
                raise ValueError(f"Unsupported engine: {engine}")
        except ImageScraperError as error:
            result = _error_result(
                engine=engine,
                requested=options.limit,
                destination=destination,
                message=str(error),
            )
        except Exception as error:
            result = _error_result(
                engine=engine,
                requested=options.limit,
                destination=destination,
                message=f"{error.__class__.__name__}: {error}",
            )

        results.append(result)

    return results
