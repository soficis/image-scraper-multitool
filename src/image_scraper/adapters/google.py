"""Google Images adapter: driver lifecycle and retry orchestration."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

from image_scraper.domain.models import DownloadCandidate, ScrapeResult, TransformOptions
from image_scraper.errors import EngineError

from .chromedriver import create_chrome_driver, resolve_chromedriver_path
from .downloader import DownloadOptions, download_candidates
from .google_collect import collect_candidates
from .google_errors import error_summary, selenium_exceptions
from .http_resilience import MAX_ATTEMPTS, retry_delay


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
    on_saved: Callable[[DownloadCandidate, Path], None] | None = None,
    on_collecting: Callable[[], None] | None = None,
) -> ScrapeResult:
    resolved_driver_path = resolve_chromedriver_path(chromedriver_path)
    driver = create_chrome_driver(
        chromedriver_path=resolved_driver_path,
        headless=headless,
        page_load_timeout=30,
    )

    try:
        if on_collecting is not None:
            on_collecting()
        candidates: list[DownloadCandidate] | None = None
        last_error: Exception | None = None
        stale_errors, _ = selenium_exceptions()
        for attempt in range(MAX_ATTEMPTS):
            try:
                candidates = collect_candidates(
                    driver=driver,
                    query=query,
                    limit=limit,
                    min_resolution=min_resolution,
                    max_resolution=max_resolution,
                    max_missed=max_missed,
                    stop_event=stop_event,
                )
                break
            except EngineError:
                raise
            except stale_errors as error:
                last_error = error
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(retry_delay(attempt=attempt, response=None))

        if candidates is None:
            assert last_error is not None
            raise last_error
    except EngineError:
        raise
    except Exception as error:
        raise EngineError(
            "google_collect",
            "failed during Google image candidate collection",
            context={"query": query, "error": error_summary(error)},
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
        on_saved=on_saved,
    )

    return ScrapeResult(
        engine="google",
        requested=limit,
        saved=batch.saved,
        skipped=batch.skipped,
        errors=batch.errors,
        destination=destination,
    )
