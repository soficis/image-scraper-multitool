"""CLI entrypoint for image scraper."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from image_scraper.app.scrape import scrape_images
from image_scraper.domain.models import (
    CustomPageOptions,
    GoogleOptions,
    ScrapeOptions,
    TransformOptions,
)
from image_scraper.errors import ImageScraperError

LOGGER = logging.getLogger("image_scraper")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape images from Bing, Google, or a custom URL."
    )
    parser.add_argument("query", help="Search term or URL to scrape.")
    parser.add_argument(
        "--num-images", type=int, default=10, help="Images to download per engine (default: 10)."
    )
    parser.add_argument(
        "--engine",
        dest="engines",
        action="append",
        choices=("bing", "google", "custom"),
        help="Specify one or more engines. Defaults to bing + google.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("downloads"),
        help="Base output directory (default: ./downloads).",
    )
    parser.add_argument(
        "--keep-filenames",
        action="store_true",
        help="Keep original source filenames when possible.",
    )
    parser.add_argument(
        "--convert-webp", action="store_true", help="Convert WebP images to JPG after download."
    )
    parser.add_argument(
        "--compression-quality",
        type=int,
        default=0,
        help="JPEG quality (1-100). 0 disables compression.",
    )
    parser.add_argument(
        "--resize-width", type=int, default=0, help="Max output width (0 = no limit)."
    )
    parser.add_argument(
        "--resize-height", type=int, default=0, help="Max output height (0 = no limit)."
    )

    parser.add_argument(
        "--bing-timeout", type=float, default=15.0, help="Bing request timeout in seconds."
    )

    parser.add_argument(
        "--google-chromedriver",
        type=Path,
        default=None,
        help="Optional explicit path to chromedriver. If omitted, auto-download is used.",
    )
    parser.add_argument(
        "--google-show-browser",
        action="store_true",
        help="Run Selenium with visible Chrome window.",
    )
    parser.add_argument(
        "--google-min-resolution",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(0, 0),
        help="Minimum Google image resolution.",
    )
    parser.add_argument(
        "--google-max-resolution",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(0, 0),
        help="Maximum Google image resolution (0 0 disables max).",
    )
    parser.add_argument(
        "--google-max-missed",
        type=int,
        default=10,
        help="Stop Google collection after this many empty passes.",
    )

    parser.add_argument(
        "--custom-recursion-depth",
        type=int,
        default=0,
        help="Recursion depth for custom URL mode.",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity.",
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper()), format="[%(levelname)s] %(message)s")


def _build_options(args: argparse.Namespace) -> ScrapeOptions:
    engines = args.engines or ["bing", "google"]
    deduped_engines = list(dict.fromkeys(engines))

    return ScrapeOptions(
        query=args.query,
        engines=deduped_engines,
        limit=args.num_images,
        output_dir=args.output_dir,
        keep_filenames=args.keep_filenames,
        bing_timeout=args.bing_timeout,
        transform=TransformOptions(
            convert_webp=args.convert_webp,
            compression_quality=args.compression_quality,
            resize_width=args.resize_width,
            resize_height=args.resize_height,
        ),
        google=GoogleOptions(
            chromedriver_path=args.google_chromedriver,
            headless=not args.google_show_browser,
            min_resolution=tuple(args.google_min_resolution),
            max_resolution=tuple(args.google_max_resolution),
            max_missed=args.google_max_missed,
        ),
        custom_page=CustomPageOptions(recursion_depth=args.custom_recursion_depth),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    try:
        options = _build_options(args)
        results = scrape_images(options)
    except ImageScraperError as error:
        LOGGER.error("%s", error)
        return 1
    except Exception as error:  # pragma: no cover - unexpected boundary errors
        LOGGER.exception("Unhandled CLI error: %s", error)
        return 1

    LOGGER.info("Scraping complete")
    for result in results:
        LOGGER.info(
            "%s: requested=%d saved=%d skipped=%d destination=%s",
            result.engine,
            result.requested,
            result.saved,
            result.skipped,
            result.destination,
        )
        if result.errors:
            LOGGER.warning("%s errors: %d", result.engine, len(result.errors))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
